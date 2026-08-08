#!/usr/bin/env python3
"""Non-formal local diagnostic sampler; never use it for an Axio quality claim."""
import json, os, sys, time, re, hashlib
from pathlib import Path
from urllib import request as urllib_request

# Remove proxy for localhost access
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

AXIO_URL = "http://127.0.0.1:18900"
CPA_URL = os.environ.get("AXIO_CPA_PLUS_BASE_URL", "https://cpa.co6.click/v1").rstrip("/")
CPA_KEY = os.environ.get("AXIO_CPA_PLUS_API_KEY", "").strip()
BENCHMARK_DIR = "data/benchmarks"
RESULTS_DIR = "data/evaluation_results"
MAX_SAMPLES = 15
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
    if not CPA_KEY:
        return None, "AXIO_CPA_PLUS_API_KEY is not configured"
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CPA_KEY}"}
    return call_api(f"{CPA_URL}/chat/completions", payload, headers)

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
    if task_type == "mcq": return str(case.get("answer", case.get("label", ""))).strip().upper()
    elif task_type == "math": return str(case.get("answer", case.get("solution", "")))
    elif task_type == "binary": return str(case.get("answer", case.get("label", ""))).strip().upper()
    return str(case.get("answer", case.get("label", "")))

def run_model(model_name, call_func, is_axio):
    bench_results = {}
    total_score, total_cases, total_lat = 0, 0, 0
    t0 = time.time()
    for filename, label, task_type in BENCHMARKS:
        cases = load_benchmark(filename)[:MAX_SAMPLES]
        if not cases:
            print(f"  [{label}] No cases, skip", flush=True)
            continue
        scores, latencies, errors = [], [], 0
        for case in cases:
            prompt = format_prompt(case, task_type)
            gold = get_gold(case, task_type)
            messages = [{"role": "user", "content": prompt}]
            max_tok = 512 if task_type in ("code", "math") else 256
            t1 = time.time()
            response, error = call_func(model_name, messages, max_tok)
            elapsed = time.time() - t1
            if response and not error:
                scores.append(score_answer(response, gold, task_type))
                latencies.append(elapsed)
            else:
                scores.append(0.0)
                latencies.append(elapsed)
                errors += 1
        acc = sum(scores) / max(len(scores), 1)
        avg_lat = sum(latencies) / max(len(latencies), 1)
        bench_results[label] = {"accuracy": round(acc, 4), "correct": sum(scores), "total": len(scores), "avg_latency_s": round(avg_lat, 2), "errors": errors}
        total_score += sum(scores)
        total_cases += len(scores)
        total_lat += sum(latencies)
        print(f"  [{label}] {sum(scores):.1f}/{len(scores)} ({acc:.1%}) avg={avg_lat:.1f}s err={errors}", flush=True)
    overall = {"total_accuracy": round(total_score / max(total_cases, 1), 4), "total_correct": total_score, "total_cases": total_cases, "avg_latency_s": round(total_lat / max(total_cases, 1), 2), "wall_time_s": round(time.time() - t0, 1)}
    return bench_results, overall

def main():
    if os.environ.get("AXIO_ALLOW_NONFORMAL_DIAGNOSTIC") != "1":
        raise SystemExit(
            "This sampler is diagnostic-only. Use the frozen official campaign "
            "for benchmark evidence, or set AXIO_ALLOW_NONFORMAL_DIAGNOSTIC=1 "
            "for a local, non-claim diagnostic run."
        )
    print("=" * 70, flush=True)
    print(
        f"Axio Fusion API - NON-FORMAL DIAGNOSTIC | "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}",
        flush=True,
    )
    print(f"Benchmarks: {len(BENCHMARKS)}, Samples: {MAX_SAMPLES}", flush=True)
    print("This output is not valid benchmark evidence or a quality claim.", flush=True)
    print("=" * 70, flush=True)
    all_results = {
        "schema": "axio_fusion_api.nonformal_diagnostic_sampler.v1",
        "formal_evaluation": False,
        "quality_claim_eligible": False,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "axio_models": {},
        "baseline_models": {},
        "comparisons": {},
    }
    
    print("\n=== AXIO MODELS ===", flush=True)
    for model in AXIO_MODELS:
        print(f"\n--- {model} ---", flush=True)
        bench_results, overall = run_model(model, call_axio, True)
        all_results["axio_models"][model] = {"benchmarks": bench_results, "overall": overall}
        print(f"  OVERALL: {overall['total_accuracy']:.1%} ({overall['total_correct']:.1f}/{overall['total_cases']}) avg={overall['avg_latency_s']:.1f}s wall={overall['wall_time_s']:.0f}s", flush=True)
    
    print("\n=== BASELINE MODELS ===", flush=True)
    for model, tier in BASELINE_MODELS:
        print(f"\n--- {model} ({tier}) ---", flush=True)
        bench_results, overall = run_model(model, call_provider, False)
        all_results["baseline_models"][model] = {"tier": tier, "benchmarks": bench_results, "overall": overall}
        print(f"  OVERALL: {overall['total_accuracy']:.1%} ({overall['total_correct']:.1f}/{overall['total_cases']}) avg={overall['avg_latency_s']:.1f}s wall={overall['wall_time_s']:.0f}s", flush=True)
    
    print("\n=== COMPARISON ===", flush=True)
    for axio_m, base_m, tier_label in [("axio-pro","gpt-5.6-sol","Strongest"),("axio-terra","gpt-5.6-terra","Second"),("axio-fast","gpt-5.6-luna","Third")]:
        ao = all_results["axio_models"].get(axio_m, {}).get("overall", {})
        bo = all_results["baseline_models"].get(base_m, {}).get("overall", {})
        aa, ba = ao.get("total_accuracy",0), bo.get("total_accuracy",0)
        al, bl = ao.get("avg_latency_s",0), bo.get("avg_latency_s",0)
        delta, lr = aa - ba, al / max(bl, 0.001)
        lat_ok = "OK" if lr <= 3.0 else "EXCEEDS 3x"
        print(
            f"{tier_label}: {axio_m} vs {base_m} | Axio: {aa:.1%} "
            f"Base: {ba:.1%} | Delta: {delta:+.1%} Lat: {lr:.1f}x {lat_ok} "
            "(diagnostic only)",
            flush=True,
        )
        all_results["comparisons"][f"{axio_m}_vs_{base_m}"] = {
            "axio_accuracy": aa,
            "baseline_accuracy": ba,
            "delta": round(delta, 4),
            "axio_latency_s": al,
            "baseline_latency_s": bl,
            "latency_ratio": round(lr, 2),
            "latency_ok": lr <= 3.0,
            "quality_claim_eligible": False,
        }
    
    output_path = os.path.join(RESULTS_DIR, f"full_evaluation_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_path, 'w') as f: json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {output_path}", flush=True)

if __name__ == "__main__": main()
