#!/usr/bin/env python3
"""
Axio Fusion Direct Engine Benchmark Evaluation
Uses FusionEngine in-process (no HTTP server) for reliability.
Also tests provider baselines via CPA Plus HTTP API.
Incremental save with detailed scoring.
"""
import json, os, sys, time, re, random, hashlib, traceback
from pathlib import Path
import requests
from requests.exceptions import RequestException as HTTPError
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/home/he/axio_fusion_api/src')

# ── Config ──
CPA_URL = "https://cpa.co6.click/v1/responses"
CPA_KEY = "sk-S9APc6QARCPCC4AeM"
BENCH_DIR = Path("/mnt/storage/axio_fusion_benchmarks/standardized")
REG_PATH = "/home/he/axio_fusion_api/private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.probe-bound.r43.private.json"
OUTPUT_FILE = Path("/home/he/axio_fusion_api/private/bench_results_engine_v1.json")
PROXY = "http://127.0.0.1:10808"
SAMPLES_PER_SUITE = 8
MAX_TOKENS = 300
TIMEOUT = 60
MAX_RETRIES = 1
SEED = 42

# os.environ['http_proxy'] = PROXY  # DISABLED: CPA Plus blocks proxy IP
# os.environ['https_proxy'] = PROXY  # DISABLED
random.seed(SEED)

from axio_fusion_api.schemas import FusionRequest, FusionPolicy
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
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line: cases.append(json.loads(line))
    return cases

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

def extract_answer(text, tf):
    if not text: return ""
    text = text.strip()
    if text.startswith("{"):
        try:
            d = json.loads(text)
            if "answer" in d: text = str(d["answer"])
        except: pass
    if tf == "mcq":
        m = re.search(r'(?:answer\s*(?:is|:)?\s*)?([A-J])', text, re.I)
        if m: return m.group(1).upper()
        for ch in text:
            if ch.isalpha() and ch.upper() in 'ABCDEFGHIJ':
                return ch.upper()
        return text[:1].upper()
    elif tf == "math":
        m = re.search(r'\\boxed\{([^}]+)\}', text)
        if m: return m.group(1).strip()
        nums = re.findall(r'-?\d+\.?\d*', text)
        return nums[-1] if nums else text.strip()
    elif tf == "translation":
        return text.strip()
    else:
        # Open-ended: try to extract short answer from verbose output
        # Pattern: "The answer is X", "Answer: X", "X."
        m = re.search(r'(?:answer\s*(?:is|:)?\s*)(.{1,30})$', text, re.I)
        if m:
            ans = m.group(1).strip().rstrip('.')
            return ans
        # Try last line
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            last = lines[-1].rstrip('.')
            if len(last) < 50:
                return last
        return text.strip()

def score_answer(pred, gold, tf):
    if not pred or not gold: return 0.0
    p, g = str(pred).strip(), str(gold).strip()
    if tf == "mcq":
        return 1.0 if p[0].upper() == g[0].upper() else 0.0
    elif tf == "math":
        try:
            return 1.0 if abs(float(p.replace(',','')) - float(g.replace(',',''))) < 1e-4 else 0.0
        except:
            return 1.0 if p.lower() == g.lower() else 0.0
    else:
        return 1.0 if p.lower() == g.lower() else 0.0

def call_axio_engine(model, prompt):
    """Use FusionEngine directly (fresh engine per call for reliability)"""
    for attempt in range(MAX_RETRIES + 1):
        try:
            profiles = load_registry(REG_PATH, require_prefusion=False)
            client = HTTPProviderClient(require_streaming=True)
            engine = FusionEngine(profiles, client=client)
            
            req = FusionRequest(
                model=model,
                prompt=prompt,
                max_output_tokens=MAX_TOKENS,
                
            )
            resp = engine.complete(req)
            if resp and resp.text:
                return resp.text, None
            return "", "empty_response"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt < MAX_RETRIES:
                time.sleep(3)
        except Exception:
            pass
    return "", last_err

def call_cpa(model, prompt):
    """Call provider baseline via CPA Plus using requests (TLS compat)"""
    body = {
        "model": model,
        "input": prompt,
        "max_output_tokens": MAX_TOKENS,
        "reasoning": {"effort": "max"},
    }
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
    print("AXIO FUSION DIRECT ENGINE BENCHMARK")
    print(f"Registry: {REG_PATH}")
    print(f"Provider: CPA Plus (gpt-5.6-luna/terra/sol)")
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
        
        all_models = AXIO_MODELS + BASELINE_MODELS
        
        for model in all_models:
            if (suite_name, model) in completed:
                print(f"  [SKIP] {suite_name}/{model}")
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
                    ans = extract_answer(pred, meta["tf"])
                    score = score_answer(ans, gold, meta["tf"])
                    correct += score
                    s = "✓" if score > 0 else "✗"
                    print(f"    [{i+1}/{len(sampled)}] {s} pred='{ans[:35]}' gold='{str(gold)[:35]}'")
                
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
            
            print(f"    → Accuracy: {acc:.2%} ({int(correct)}/{len(sampled)}) in {elapsed:.1f}s")
            save_results(results)
            completed.add((suite_name, model))
    
    # ── Summary ──
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    model_scores = defaultdict(list)
    for r in results["runs"]:
        model_scores[r["model"]].append(r["accuracy"])
    
    for model in all_models:
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
