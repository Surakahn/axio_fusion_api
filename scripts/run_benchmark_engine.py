#!/usr/bin/env python3
import json, os, sys, time, re, random, hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/home/he/axio_fusion_api/src')

CPA_URL = "https://cpa.co6.click/v1/responses"
CPA_KEY = "sk-S9APc6QARCPCC4AeM"
BENCH_DIR = Path("/mnt/storage/axio_fusion_benchmarks/standardized")
REG_PATH = "/home/he/axio_fusion_api/private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.probe-bound.r43.private.json"
OUTPUT_FILE = Path("/home/he/axio_fusion_api/private/bench_results_engine_v1.json")
PROXY = "http://127.0.0.1:10808"
SAMPLES_PER_SUITE = 5
MAX_TOKENS = 300
TIMEOUT = 45
MAX_RETRIES = 0
SEED = 42

random.seed(SEED)

import requests
from axio_fusion_api.schemas import FusionRequest
from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import HTTPProviderClient

AXIO_MODELS = ["axio-fast", "axio-terra", "axio-pro"]
BASELINE_MODELS = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]

SUITES = {
    "arc_challenge": {"category": "logic", "tf": "mcq", "qk": "question", "ok": "options"},
    "bbh": {"category": "logic", "tf": "open", "qk": "prompt"},
    "math_500": {"category": "math", "tf": "math", "qk": "prompt"},
    "aime_recent": {"category": "math", "tf": "math", "qk": "prompt"},
    "global_mmlu_lite": {"category": "multilingual", "tf": "mcq", "qk": "question", "ok": "options"},
    "flores_translation_instruction": {"category": "multilingual", "tf": "translation", "qk": "source"},
    "truthfulqa": {"category": "hallucination", "tf": "mcq", "qk": "question", "ok": "options"},
    "halueval": {"category": "hallucination", "tf": "mcq", "qk": "question", "ok": "options"},
    "mmmu_text_science": {"category": "science", "tf": "mcq", "qk": "question", "ok": "options"},
    "medqa_usmle": {"category": "vertical", "tf": "mcq", "qk": "question", "ok": "options"},
    "financebench": {"category": "vertical", "tf": "open", "qk": "prompt"},
    "legalbench": {"category": "vertical", "tf": "mcq", "qk": "question", "ok": "options"},
    "bizbench": {"category": "vertical", "tf": "open", "qk": "prompt"},
    "policyllm_policybench": {"category": "vertical", "tf": "mcq", "qk": "question", "ok": "options"},
}

def load_suite(name):
    path = BENCH_DIR / f"{name}.jsonl"
    if not path.exists(): return []
    return [json.loads(l) for l in open(path) if l.strip()]

def build_prompt(case, meta):
    tf = meta["tf"]
    q = case.get(meta["qk"], "")
    if tf == "mcq" and "ok" in meta:
        opts = case.get(meta["ok"], {})
        if isinstance(opts, str):
            try: opts = eval(opts)
            except: opts = {}
        opt_str = "\n".join(f"{k}. {v}" for k, v in sorted(opts.items()) if k and v)
        return f"{q}\n\nOptions:\n{opt_str}\n\nAnswer with just the letter."
    elif tf == "translation":
        sl = case.get("source_language", "Source")
        tl = case.get("target_language", "Target")
        return f"Translate from {sl} to {tl}. Output ONLY the translation:\n\n{q}"
    elif tf == "math":
        return f"Solve. Put final answer in \\boxed{{}}.\n\n{q}"
    else:
        return f"Answer concisely:\n\n{q}"

def classify_gold(gold):
    """Classify gold answer format: mcq, boolean, math, or open."""
    g = str(gold).strip()
    if re.match(r'^\([A-J]\)$', g): return "mcq"
    if g.lower() in ('true', 'false', 'yes', 'no'): return "boolean"
    if re.match(r'^-?\d+\.?\d*$', g.replace(',', '')): return "math"
    return "open"

def extract_answer(text, gold=None):
    """Extract answer, using gold format as hint."""
    if not text: return ""
    text = text.strip()
    if text.startswith("{"):
        try:
            d = json.loads(text)
            if "answer" in d: text = str(d["answer"])
        except: pass
    
    fmt = classify_gold(gold) if gold else "open"
    
    if fmt == "mcq":
        m = re.search(r'\(?([A-J])\)?', text, re.I)
        if m: return m.group(1).upper()
        for ch in text:
            if ch.isalpha() and ch.upper() in 'ABCDEFGHIJ':
                return ch.upper()
        return text[:1].upper()
    elif fmt == "boolean":
        t = text.lower().strip()
        for w in ('true', 'false', 'yes', 'no'):
            if t.startswith(w): return w
        return t.split()[0] if t.split() else t
    elif fmt == "math":
        m = re.search(r'\\boxed\{([^}]*)\}', text)
        if m: return m.group(1).strip()
        nums = re.findall(r'-?\d+\.?\d*', text)
        return nums[-1] if nums else text.strip()
    else:
        m = re.search(r'(?:answer\s*(?:is|:)?\s*)(\S[^\n]*?)\s*[.!]?$', text, re.I | re.M)
        if m:
            ans = m.group(1).strip().rstrip('.')
            if len(ans) < 60: return ans
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            last = lines[-1].rstrip('.')
            if len(last) < 50: return last
        return text.strip()

def score_answer(pred, gold):
    """Score based on auto-detected gold format."""
    if not pred or not gold: return 0.0
    p, g = str(pred).strip(), str(gold).strip()
    fmt = classify_gold(g)
    
    if fmt == "mcq":
        pm = re.search(r'\(?([A-J])\)?', p)
        gm = re.search(r'\(?([A-J])\)?', g)
        if pm and gm:
            return 1.0 if pm.group(1).upper() == gm.group(1).upper() else 0.0
        return 1.0 if p and g and p[0].upper() == g[0].upper() else 0.0
    elif fmt == "boolean":
        return 1.0 if p.lower() == g.lower() else 0.0
    elif fmt == "math":
        pn = p.replace(',', '').strip('$').strip()
        gn = g.replace(',', '').strip('$').strip()
        if pn.lower() == gn.lower(): return 1.0
        try: return 1.0 if abs(float(pn) - float(gn)) < 1e-4 else 0.0
        except: return 1.0 if pn == gn else 0.0
    else:
        return 1.0 if p.lower() == g.lower() else 0.0

def call_axio_engine(model, prompt):
    for attempt in range(MAX_RETRIES + 1):
        try:
            profiles = load_registry(REG_PATH, require_prefusion=False)
            client = HTTPProviderClient(require_streaming=True)
            engine = FusionEngine(profiles, client=client)
            req = FusionRequest(model=model, prompt=prompt, max_output_tokens=MAX_TOKENS)
            resp = engine.complete(req)
            if resp and resp.text:
                return resp.text, None
            return "", "empty_response"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt < MAX_RETRIES: time.sleep(3)
    return "", last_err

def call_cpa(model, prompt):
    body = {"model": model, "input": prompt, "max_output_tokens": MAX_TOKENS, "reasoning": {"effort": "max"}}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CPA_KEY}"}
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(CPA_URL, json=body, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("output", []):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                return c["text"], None
                return str(data)[:500], None
            else:
                last_err = f"HTTP{resp.status_code}: {resp.text[:200]}"
                if attempt < MAX_RETRIES: time.sleep(5)
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt < MAX_RETRIES: time.sleep(3)
    return "", last_err

def load_results():
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f: return json.load(f)
    return {"runs": [], "started": str(datetime.now()), "completed": False}

def save_results(r):
    r["last_updated"] = str(datetime.now())
    with open(OUTPUT_FILE, "w") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)

def main():
    results = load_results()
    completed = {(r["suite"], r["model"]) for r in results["runs"]}
    
    print("=" * 80)
    print("AXIO FUSION BENCHMARK v3 (fixed scoring)")
    print(f"Suites: {len(SUITES)}, Samples: {SAMPLES_PER_SUITE}/suite/model")
    print("=" * 80)
    
    for suite_name, meta in SUITES.items():
        cases = load_suite(suite_name)
        if not cases:
            print(f"\n[SKIP] {suite_name}: no data")
            continue
        
        if len(cases) > SAMPLES_PER_SUITE:
            sampled = random.sample(cases, SAMPLES_PER_SUITE)
        else:
            sampled = cases
        
        for model in AXIO_MODELS + BASELINE_MODELS:
            if (suite_name, model) in completed:
                continue
            
            print(f"\n[{suite_name}] {model} ({meta['tf']}, {len(sampled)} cases)")
            sys.stdout.flush()
            
            correct = 0
            errors = 0
            start_time = time.time()
            
            for i, case in enumerate(sampled):
                prompt = build_prompt(case, meta)
                gold = case.get("answer", case.get("reference", ""))
                
                if model in BASELINE_MODELS:
                    pred, err = call_cpa(model, prompt)
                else:
                    pred, err = call_axio_engine(model, prompt)
                
                if err:
                    errors += 1
                    print(f"    [{i+1}/{len(sampled)}] ERR: {err[:80]}")
                else:
                    ans = extract_answer(pred, gold)
                    score = score_answer(ans, gold)
                    correct += score
                    s = "\u2713" if score > 0 else "\u2717"
                    print(f"    [{i+1}/{len(sampled)}] {s} pred='{ans[:30]}' gold='{str(gold)[:30]}'")
                
                sys.stdout.flush()
                time.sleep(0.3)
            
            elapsed = time.time() - start_time
            acc = correct / len(sampled) if sampled else 0
            
            run = {
                "suite": suite_name, "model": model,
                "category": meta["category"], "task_format": meta["tf"],
                "samples": len(sampled), "correct": int(correct),
                "errors": errors, "accuracy": round(acc, 4),
                "elapsed_s": round(elapsed, 1),
                "timestamp": str(datetime.now()),
            }
            results["runs"].append(run)
            print(f"    \u2192 Accuracy: {acc:.2%} ({int(correct)}/{len(sampled)}) in {elapsed:.1f}s")
            save_results(results)
            completed.add((suite_name, model))
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    model_scores = defaultdict(list)
    for r in results["runs"]:
        model_scores[r["model"]].append(r["accuracy"])
    
    for model in AXIO_MODELS + BASELINE_MODELS:
        scores = model_scores.get(model, [])
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  {model:20s}: avg={avg:.2%} across {len(scores)} suites")
    
    results["completed"] = True
    results["finished"] = str(datetime.now())
    save_results(results)
    print(f"\nDone. Results: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
