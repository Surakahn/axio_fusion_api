#!/usr/bin/env python3
"""
Axio Fusion Comprehensive HTTP Benchmark Evaluation
Direct HTTP API calls to the running Fusion server + provider baselines.
Incremental save, retry logic, all 14 ready suites.
"""
import json, os, sys, time, re, random, hashlib
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime

# ── Config ──
AXIO_URL = "http://127.0.0.1:18900/v1/chat/completions"
CPA_URL = "https://cpa.co6.click/v1/responses"
CPA_KEY = "sk-S9APc6QARCPCC4AeM"
BENCH_DIR = Path("/mnt/storage/axio_fusion_benchmarks/standardized")
OUTPUT_FILE = Path("/home/he/axio_fusion_api/private/bench_results_http_v2.json")
PROXY = "http://127.0.0.1:10808"
SAMPLES_PER_SUITE = 15  # Sample size per suite per model
MAX_TOKENS = 512
TIMEOUT = 120
MAX_RETRIES = 2
SEED = 42

os.environ['http_proxy'] = PROXY
os.environ['https_proxy'] = PROXY
random.seed(SEED)

# ── Models to test ──
AXIO_MODELS = ["axio-fast", "axio-terra", "axio-pro"]
BASELINE_MODELS = {
    "gpt-5.6-luna": "responses",
    "gpt-5.6-terra": "responses", 
    "gpt-5.6-sol": "responses",
}

# ── Suite metadata ──
SUITES = {
    "arc_challenge": {"category": "logic", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "bbh": {"category": "logic", "task_format": "open", "question_key": "prompt"},
    "math_500": {"category": "math", "task_format": "math", "question_key": "prompt"},
    "aime_recent": {"category": "math", "task_format": "math", "question_key": "prompt"},
    "global_mmlu_lite": {"category": "multilingual", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "flores_translation_instruction": {"category": "multilingual", "task_format": "translation", "question_key": "source"},
    "truthfulqa": {"category": "hallucination", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "halueval": {"category": "hallucination", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "mmmu_text_science": {"category": "science", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "medqa_usmle": {"category": "vertical", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "financebench": {"category": "vertical", "task_format": "open", "question_key": "prompt"},
    "legalbench": {"category": "vertical", "task_format": "mcq", "question_key": "question", "options_key": "options"},
    "bizbench": {"category": "vertical", "task_format": "open", "question_key": "prompt"},
    "policyllm_policybench": {"category": "vertical", "task_format": "mcq", "question_key": "question", "options_key": "options"},
}

# ── Helpers ──
def load_suite(name):
    path = BENCH_DIR / f"{name}.jsonl"
    if not path.exists():
        return []
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases

def build_prompt(case, meta):
    tf = meta["task_format"]
    q = case.get(meta["question_key"], "")
    
    if tf == "mcq" and "options_key" in meta:
        opts = case.get(meta["options_key"], {})
        if isinstance(opts, str):
            try: opts = eval(opts)
            except: opts = {}
        opt_str = "\n".join(f"{k}. {v}" for k, v in sorted(opts.items()) if k and v)
        return f"{q}\n\nOptions:\n{opt_str}\n\nAnswer with just the letter (A, B, C, D, etc)."
    elif tf == "translation":
        src_lang = case.get("source_language", "Source")
        tgt_lang = case.get("target_language", "Target")
        return f"Translate the following from {src_lang} to {tgt_lang}. Output ONLY the translation, nothing else:\n\n{q}"
    elif tf == "math":
        return f"Solve this math problem. Put your final answer within \\boxed{{}}.\n\n{q}"
    else:
        return f"Answer concisely:\n\n{q}"

def call_axio(model, prompt, max_tok=MAX_TOKENS):
    """Call Axio model via HTTP API"""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tok,
        "temperature": 0.0,
        "stream": False
    }
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = Request(AXIO_URL, data=json.dumps(body).encode(), headers={
                "Content-Type": "application/json"
            })
            resp = urlopen(req, timeout=TIMEOUT)
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            return content, None
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(3)
    return "", last_err

def call_cpa(model, prompt, max_tok=MAX_TOKENS):
    """Call provider baseline via CPA Plus Responses API"""
    body = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_tok,
        "reasoning": {"effort": "max"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CPA_KEY}"
    }
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = Request(CPA_URL, data=json.dumps(body).encode(), headers=headers)
            resp = urlopen(req, timeout=TIMEOUT)
            data = json.loads(resp.read())
            # Extract text from responses API format
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        if c.get("type") == "output_text":
                            return c["text"], None
            return str(data), None
        except HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode()[:200]}"
            if attempt < MAX_RETRIES:
                time.sleep(5)
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(3)
    return "", last_err

def extract_answer(text, task_format):
    """Extract answer from model output"""
    if not text:
        return ""
    text = text.strip()
    
    # Try JSON extraction first
    if text.startswith("{"):
        try:
            d = json.loads(text)
            if "answer" in d:
                text = str(d["answer"])
            elif "output" in d:
                text = str(d["output"])
        except:
            pass
    
    if task_format == "mcq":
        # Extract letter
        m = re.search(r'(?:answer\s*(?:is|:)?\s*)?([A-J])', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        # Try first letter
        for ch in text:
            if ch.isalpha() and ch.upper() in 'ABCDEFGHIJ':
                return ch.upper()
        return text[:1].upper()
    
    elif task_format == "math":
        # Extract boxed answer
        m = re.search(r'\\boxed\{([^}]+)\}', text)
        if m:
            return m.group(1).strip()
        # Extract last math expression
        nums = re.findall(r'-?\d+\.?\d*', text)
        return nums[-1] if nums else text.strip()
    
    elif task_format == "translation":
        # Just return the text directly
        return text.strip()
    
    else:
        return text.strip()

def score_answer(pred, gold, task_format):
    """Score a prediction against gold answer"""
    if not pred or not gold:
        return 0.0
    
    pred_clean = str(pred).strip()
    gold_clean = str(gold).strip()
    
    if task_format == "mcq":
        # Compare first letter
        p = pred_clean[0].upper() if pred_clean else ""
        g = gold_clean[0].upper() if gold_clean else ""
        return 1.0 if p == g else 0.0
    
    elif task_format == "math":
        # Numeric comparison
        try:
            pn = float(pred_clean.replace(",", ""))
            gn = float(gold_clean.replace(",", ""))
            return 1.0 if abs(pn - gn) < 1e-4 else 0.0
        except:
            return 1.0 if pred_clean.lower() == gold_clean.lower() else 0.0
    
    else:
        return 1.0 if pred_clean.lower() == gold_clean.lower() else 0.0

def load_existing_results():
    """Load existing results for incremental save"""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            return json.load(f)
    return {"runs": [], "summary": {}, "started": str(datetime.now()), "completed": False}

def save_results(results):
    """Save results incrementally"""
    results["last_updated"] = str(datetime.now())
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  [SAVED] {OUTPUT_FILE}")

# ── Main ──
def main():
    results = load_existing_results()
    completed = {(r["suite"], r["model"]) for r in results["runs"]}
    
    print("=" * 80)
    print("AXIO FUSION HTTP BENCHMARK EVALUATION")
    print(f"Server: {AXIO_URL}")
    print(f"Provider: CPA Plus (gpt-5.6-luna/terra/sol)")
    print(f"Suites: {len(SUITES)}, Samples: {SAMPLES_PER_SUITE}/suite/model")
    print(f"Models: {AXIO_MODELS + list(BASELINE_MODELS.keys())}")
    print("=" * 80)
    
    for suite_name, meta in SUITES.items():
        cases = load_suite(suite_name)
        if not cases:
            print(f"\n[SKIP] {suite_name}: no data")
            continue
        
        # Sample
        if len(cases) > SAMPLES_PER_SUITE:
            sampled = random.sample(cases, SAMPLES_PER_SUITE)
        else:
            sampled = cases
        
        all_models = AXIO_MODELS + list(BASELINE_MODELS.keys())
        
        for model in all_models:
            if (suite_name, model) in completed:
                print(f"  [SKIP] {suite_name}/{model} already done")
                continue
            
            print(f"\n[{suite_name}] {model} ({meta['task_format']}, {len(sampled)} cases)")
            
            correct = 0
            errors = 0
            case_results = []
            start_time = time.time()
            
            for i, case in enumerate(sampled):
                prompt = build_prompt(case, meta)
                gold = case.get("answer", case.get("reference", ""))
                
                # Call model
                if model in BASELINE_MODELS:
                    pred, err = call_cpa(model, prompt)
                else:
                    pred, err = call_axio(model, prompt)
                
                if err:
                    errors += 1
                    case_results.append({"i": i, "error": err, "score": 0.0})
                    print(f"    [{i+1}/{len(sampled)}] ERROR: {err[:80]}")
                else:
                    ans = extract_answer(pred, meta["task_format"])
                    score = score_answer(ans, gold, meta["task_format"])
                    correct += score
                    case_results.append({"i": i, "pred": pred[:200], "gold": str(gold)[:100], "extracted": ans[:50], "score": score})
                    status = "✓" if score > 0 else "✗"
                    print(f"    [{i+1}/{len(sampled)}] {status} pred='{ans[:40]}' gold='{str(gold)[:40]}'")
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
            
            elapsed = time.time() - start_time
            accuracy = correct / len(sampled) if sampled else 0
            
            run_record = {
                "suite": suite_name,
                "model": model,
                "category": meta["category"],
                "task_format": meta["task_format"],
                "samples": len(sampled),
                "correct": int(correct),
                "errors": errors,
                "accuracy": round(accuracy, 4),
                "elapsed_s": round(elapsed, 1),
                "avg_latency_s": round(elapsed / len(sampled), 1) if sampled else 0,
                "timestamp": str(datetime.now()),
            }
            results["runs"].append(run_record)
            
            print(f"    → Accuracy: {accuracy:.2%} ({int(correct)}/{len(sampled)}) in {elapsed:.1f}s")
            
            # Save after each run
            save_results(results)
            completed.add((suite_name, model))
    
    # ── Summary ──
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    # Group by model
    from collections import defaultdict
    model_scores = defaultdict(list)
    for r in results["runs"]:
        model_scores[r["model"]].append(r["accuracy"])
    
    for model in all_models:
        scores = model_scores.get(model, [])
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  {model:20s}: avg={avg:.2%} across {len(scores)} suites, scores={[f'{s:.2%}' for s in scores]}")
    
    # Group by category
    cat_scores = defaultdict(lambda: defaultdict(list))
    for r in results["runs"]:
        cat_scores[r["category"]][r["model"]].append(r["accuracy"])
    
    print("\nBy Category:")
    for cat, models in sorted(cat_scores.items()):
        print(f"  {cat}:")
        for model, scores in sorted(models.items()):
            print(f"    {model:20s}: {sum(scores)/len(scores):.2%}")
    
    results["completed"] = True
    results["finished"] = str(datetime.now())
    save_results(results)
    print(f"\nDone. Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
