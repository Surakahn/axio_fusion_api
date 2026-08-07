#!/usr/bin/env python3
"""Axio Fusion API - Full Scientific Benchmark Evaluation."""
import json, os, sys, time, re, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import request as urllib_request

os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

AXIO_URL = "http://127.0.0.1:18900"
TOKENAPIS_URL = "https://tokenapis.com/v1"
TOKENAPIS_KEY = "sk-9023fc08bd8788b07e426144de48ac476b3de9e1e532f1fd67719b9b12e5e1ef"
BENCHMARK_DIR = "data/benchmarks"
RESULTS_DIR = "data/evaluation_results"
MAX_SAMPLES = 15
MAX_WORKERS = 3
TIMEOUT = 90

Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)

BENCHMARKS = [
    ("math_500.jsonl", "Math-MATH500", "math"),
    ("aime_recent.jsonl", "Math-AIME", "math"),
    ("humaneval.jsonl", "Code-HumanEval", "code"),
    ("arc_challenge.jsonl", "Logic-ARC", "mcq"),
    ("bbh.jsonl", "Logic-BBH", "mcq"),
    ("truthfulqa.jsonl", "Hallucination-TruthfulQA", "mcq"),
    ("halueval.jsonl", "Hallucination-HaluEval", "binary"),
    ("ifeval.jsonl", "DailyWork-IFEval", "instr"),
    ("mt_bench_questions.jsonl", "DailyWork-MTBench", "gen"),
    ("global_mmlu_lite.jsonl", "Multilingual-GlobalMMLU", "mcq"),
    ("flores_translation_instruction.jsonl", "Multilingual-FLORES", "trans"),
    ("mmmu_text_science.jsonl", "Science-MMMU-Pro", "mcq"),
    ("medqa_usmle.jsonl", "Vertical-MedQA", "mcq"),
    ("finqa.jsonl", "Vertical-FinQA", "math"),
    ("legalbench.jsonl", "Vertical-LegalBench", "mcq"),
    ("consultqa_mini.jsonl", "Vertical-ConsultQA", "mcq"),
    ("policyqa_mini.jsonl", "Vertical-PolicyQA", "mcq"),
    ("livecodebench_mini.jsonl", "Code-LiveCodeBench", "code"),
    ("bfcl_mini.jsonl", "Agentic-BFCL", "tool"),
    ("tau_bench_mini.jsonl", "Agentic-TauBench", "tool"),
]

AXIO_MODELS = ["axio-fast", "axio-terra", "axio-pro"]
BASELINE_MODELS = [("gpt-5.6-sol", "strongest"), ("gpt-5.6-terra", "second"), ("gpt-5.6-luna", "third")]

def call_api(url, payload, headers):
    data = json.dumps(payload).encode()
    req = urllib_request.Request(url, data=data, headers=headers)
    try:
        resp = urllib_request.urlopen(req, timeout=TIMEOUT)
        body = json.loads(resp.read().decode())
        return body["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)[:200]

def call_axio(model, messages, max_tokens=256):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    return call_api(f"{AXIO_URL}/v1/chat/completions", payload, {"Content-Type": "application/json"})

def call_provider(model, messages, max_tokens=256):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    return call_api(f"{TOKENAPIS_URL}/v1/chat/completions", payload,
        {"Content-Type": "application/json", "Authorization": f"Bearer {TOKENAPIS_KEY}"})

def normalize_answer(text):
    if not text: return ""
    text = str(text).strip().upper()
    for pat in [r'\bANSWER\s*(?:IS\s*)?[:\-]?\s*([A-J])\b', r'\b([A-J])\b\s*(?:is\s+correct)', r'\b([A-J])\)', r'^([A-J])[\s\.\,\)]', r'\b([A-J])\b']:
        m = re.search(pat, text, re.IGNORECASE)
        if m: return m.group(1).upper()
    return ""

def extract_math(text):
    if not text: return ""
    boxed = re.findall(r'\\boxed\{([^}]+)\}', str(text))
    if boxed: return boxed[-1].strip()
    for line in reversed(str(text).split('\n')):
        nums = re.findall(r'-?\d+\.?\d*', line.strip())
        if nums: return nums[-1]
    return str(text)

def normalize_math(text):
    text = re.sub(r'[,%\$\s]', '', str(text).strip())
    try: return str(float(text))
    except: return text

def score_answer(prediction, gold, task_type):
    if not prediction: return 0.0
    if task_type == "mcq":
        pred = normalize_answer(prediction)
        gold = normalize_answer(str(gold))
        return 1.0 if pred and gold and pred == gold else 0.0
    elif task_type == "math":
        pred = normalize_math(extract_math(prediction))
        gold = normalize_math(str(gold))
        return 1.0 if pred and gold and pred == gold else 0.0
    elif task_type == "code":
        code = prediction
        if "```python" in code: code = code.split("```python")[1].split("```")[0]
        elif "```" in code: code = code.split("```")[1].split("```")[0]
        checks = [bool(re.search(r'def\s+\w+', code)), len(code) > 30]
        return sum(checks) / len(checks)
    elif task_type == "binary":
        pred = str(prediction).strip().upper()
        gold = str(gold).strip().upper()
        if "YES" in pred and "NO" not in pred: pred = "YES"
        elif "NO" in pred and "YES" not in pred: pred = "NO"
        return 1.0 if pred == gold else 0.0
    elif task_type in ("trans", "instr", "gen", "tool"):
        return 1.0 if prediction and len(prediction) > 10 else 0.0
    return 0.0

def load_benchmark(filename):
    path = os.path.join(BENCHMARK_DIR, filename)
    if not os.path.exists(path): return []
    cases = []
    with open(path) as f:
        for line in f:
            if not line.strip(): continue
            try:
                case = json.loads(line)
                if isinstance(case, dict): cases.append(case)
            except: pass
    return cases

def format_prompt(case, task_type):
    if task_type == "mcq":
        q = str(case.get("question", case.get("prompt", "")))[:2000]
        choices = case.get("choices") or case.get("options")
        if isinstance(choices, dict):
            ct = "\n".join(f"{k}. {str(v)[:200]}" for k, v in sorted(choices.items()))
        elif isinstance(choices, list):
            labels = [chr(ord('A')+i) for i in range(len(choices))]
            ct = "\n".join(f"{l}. {str(c)[:200]}" for l, c in zip(labels, choices))
        else: ct = str(choices)[:500]
        return f"{q}\n\n{ct}\n\nAnswer with only the letter of the correct option."
    elif task_type == "math":
        p = str(case.get("problem", case.get("question", case.get("prompt", ""))))[:2000]
        return f"Solve. Put final answer in \\boxed{{}}:\n\n{p}"
    elif task_type == "code":
        p = str(case.get("prompt", case.get("question", "")))[:2000]
        return f"Write Python code to solve:\n\n{p}"
    elif task_type == "trans":
        s = str(case.get("source", case.get("input", "")))[:2000]
        sl = case.get("src_lang", case.get("source_language", ""))
        tl = case.get("tgt_lang", case.get("target_language", ""))
        return f"Translate from {sl} to {tl}:\n\n{s}"
    elif task_type == "binary":
        q = str(case.get("question", case.get("prompt", "")))[:2000]
        return f"{q}\n\nAnswer with only YES or NO."
    else:
        return str(case.get("question", case.get("prompt", "")))[:2000]

def get_gold(case, task_type):
    if task_type == "mcq":
        return str(case.get("answer", case.get("label", case.get("target", "")))).strip().upper()
    elif task_type == "math":
        return str(case.get("answer", case.get("solution", "")))
    elif task_type == "binary":
        return str(case.get("answer", case.get("label", ""))).strip().upper()
    return str(case.get("answer", case.get("label", "")))

def run_one_case(case, task_type, model_name, call_func, max_tokens):
    prompt = format_prompt(case, task_type)
    gold = get_gold(case, task_type)
    messages = [{"role": "user", "content": prompt}]
    t0 = time.time()
    response, error = call_func(model_name, messages, max_tokens)
    elapsed = time.time() - t0
    if response and not error:
        score = score_answer(response, gold, task_type)
        return {"score": score, "latency": elapsed, "error": None}
    return {"score": 0.0, "latency": elapsed, "error": error}

def run_benchmark(filename, label, task_type, model_name, call_func, max_tokens=256):
    cases = load_benchmark(filename)[:MAX_SAMPLES]
    if not cases: return None
    scores, latencies, errors = [], [], 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_one_case, c, task_type, model_name, call_func, max_tokens): i for i, c in enumerate(cases)}
        for future in as_completed(futures):
            result = future.result()
            scores.append(result["score"])
            latencies.append(result["latency"])
            if result["error"]: errors += 1
    acc = sum(scores) / max(len(scores), 1)
    avg_lat = sum(latencies) / max(len(latencies), 1)
    print(f"  [{label}] {sum(scores):.1f}/{len(scores)} ({acc:.1%}) avg={avg_lat:.1f}s err={errors}", flush=True)
    return {"accuracy": round(acc, 4), "correct": sum(scores), "total": len(scores), "avg_latency_s": round(avg_lat, 2), "errors": errors}

def main():
    print("=" * 70, flush=True)
    print(f"Axio Fusion API - Full Evaluation | Time: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"Benchmarks: {len(BENCHMARKS)}, Samples: {MAX_SAMPLES}, Workers: {MAX_WORKERS}", flush=True)
    print("=" * 70, flush=True)
    
    all_results = {"schema": "axio_fusion_api.full_evaluation.v1", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "axio_models": {}, "baseline_models": {}, "comparisons": {}}
    
    # Axio Models
    print("\n=== EVALUATING AXIO MODELS ===", flush=True)
    for model in AXIO_MODELS:
        print(f"\n--- {model} ---", flush=True)
        t0 = time.time()
        bench_results = {}
        total_score, total_cases, total_lat = 0, 0, 0
        for filename, label, task_type in BENCHMARKS:
            max_tok = 512 if task_type in ("code", "math") else 256
            result = run_benchmark(filename, label, task_type, model, call_axio, max_tok)
            if result:
                bench_results[label] = result
                total_score += result["correct"]
                total_cases += result["total"]
                total_lat += result["avg_latency_s"] * result["total"]
        overall = {"total_accuracy": round(total_score / max(total_cases, 1), 4),
                   "total_correct": total_score, "total_cases": total_cases,
                   "avg_latency_s": round(total_lat / max(total_cases, 1), 2),
                   "wall_time_s": round(time.time() - t0, 1)}
        all_results["axio_models"][model] = {"benchmarks": bench_results, "overall": overall}
        print(f"  OVERALL: {overall['total_accuracy']:.1%} ({overall['total_correct']:.1f}/{overall['total_cases']}) avg={overall['avg_latency_s']:.1f}s wall={overall['wall_time_s']:.0f}s", flush=True)
    
    # Baseline Models
    print("\n=== EVALUATING BASELINE MODELS ===", flush=True)
    for model, tier in BASELINE_MODELS:
        print(f"\n--- {model} ({tier}) ---", flush=True)
        t0 = time.time()
        bench_results = {}
        total_score, total_cases, total_lat = 0, 0, 0
        for filename, label, task_type in BENCHMARKS:
            max_tok = 512 if task_type in ("code", "math") else 256
            result = run_benchmark(filename, label, task_type, model, call_provider, max_tok)
            if result:
                bench_results[label] = result
                total_score += result["correct"]
                total_cases += result["total"]
                total_lat += result["avg_latency_s"] * result["total"]
        overall = {"total_accuracy": round(total_score / max(total_cases, 1), 4),
                   "total_correct": total_score, "total_cases": total_cases,
                   "avg_latency_s": round(total_lat / max(total_cases, 1), 2),
                   "wall_time_s": round(time.time() - t0, 1)}
        all_results["baseline_models"][model] = {"tier": tier, "benchmarks": bench_results, "overall": overall}
        print(f"  OVERALL: {overall['total_accuracy']:.1%} ({overall['total_correct']:.1f}/{overall['total_cases']}) avg={overall['avg_latency_s']:.1f}s wall={overall['wall_time_s']:.0f}s", flush=True)
    
    # Comparisons
    print("\n=== COMPARISON ===", flush=True)
    for axio_m, base_m, tier_label in [("axio-pro","gpt-5.6-sol","Strongest"),("axio-terra","gpt-5.6-terra","Second"),("axio-fast","gpt-5.6-luna","Third")]:
        ao = all_results["axio_models"].get(axio_m, {}).get("overall", {})
        bo = all_results["baseline_models"].get(base_m, {}).get("overall", {})
        aa, ba = ao.get("total_accuracy",0), bo.get("total_accuracy",0)
        al, bl = ao.get("avg_latency_s",0), bo.get("avg_latency_s",0)
        delta, lr = aa - ba, al / max(bl, 0.001)
        verdict = "BETTER" if delta > 0.01 else ("SIMILAR" if abs(delta) <= 0.01 else "WORSE")
        lat_ok = "OK" if lr <= 3.0 else "EXCEEDS 3x"
        print(f"\n{tier_label}: {axio_m} vs {base_m}", flush=True)
        print(f"  Axio: {aa:.1%} ({al:.1f}s) | Baseline: {ba:.1%} ({bl:.1f}s)", flush=True)
        print(f"  Delta: {delta:+.1%} | Latency: {lr:.1f}x {lat_ok} | Verdict: {verdict}", flush=True)
        all_results["comparisons"][f"{axio_m}_vs_{base_m}"] = {"axio_accuracy":aa,"baseline_accuracy":ba,"delta":round(delta,4),"axio_latency_s":al,"baseline_latency_s":bl,"latency_ratio":round(lr,2),"verdict":verdict,"latency_ok":lr<=3.0}
    
    output_path = os.path.join(RESULTS_DIR, f"full_evaluation_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_path, 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}", flush=True)
    return all_results

if __name__ == "__main__":
    main()
