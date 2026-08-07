#!/usr/bin/env python3
"""Comprehensive benchmark evaluation: Axio Fusion vs Single-Model Baselines.
Tests across 9 categories, 20 benchmarks, comparing axio-fast/terra/pro
against single-model baselines (gpt-5.6-luna/terra/sol).
"""
import json, os, sys, time, urllib.request, urllib.error, re, hashlib
from pathlib import Path
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────
AXIO_URL = "http://127.0.0.1:18900"
BENCHMARK_DIR = "data/benchmarks"
RESULTS_DIR = "data/evaluation_results/comprehensive"
MAX_SAMPLES_PER_BENCH = 20  # Per model, per benchmark
TIMEOUT = 90

# Single-model baselines: call directly via CPA provider
CPA_BASE = "https://cpa.co6.click/v1"
CPA_KEY = os.environ.get("AXIO_TOKENAPIS_API_KEY", "")
if not CPA_KEY:
    # Try to load from env file
    env_file = Path("private/current_channels.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("export AXIO_TOKENAPIS_API_KEY="):
                CPA_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")

BASELINE_MODELS = {
    "rank1": ("gpt-5.6-sol", "max"),     # Strongest → vs axio-pro
    "rank2": ("gpt-5.6-terra", "max"),    # 2nd → vs axio-terra  
    "rank3": ("gpt-5.6-luna", "max"),     # 3rd → vs axio-fast
}

AXIO_MODELS = {
    "axio-pro": "rank1",
    "axio-terra": "rank2", 
    "axio-fast": "rank3",
}

Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)

# ── Provider helpers ───────────────────────────────────────────────────────
def call_cpa_baseline(model: str, messages: list, reasoning_effort: str = "max",
                       max_tokens: int = 256) -> tuple[str | None, str | None]:
    """Call a single model directly via CPA (responses API format)."""
    payload = {
        "model": model,
        "input": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ],
        "max_output_tokens": max_tokens,
        "temperature": 0.0,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    
    data = json.dumps(payload).encode()
    proxy_handler = urllib.request.ProxyHandler({
        "http": "http://127.0.0.1:10808",
        "https": "http://127.0.0.1:10808",
    })
    opener = urllib.request.build_opener(proxy_handler)
    
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                f"{CPA_BASE}/responses",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {CPA_KEY}",
                },
            )
            resp = opener.open(req, timeout=TIMEOUT)
            body = json.loads(resp.read().decode())
            # Extract text from responses API format
            for output_item in body.get("output", []):
                if output_item.get("type") == "message":
                    for content_item in output_item.get("content", []):
                        if content_item.get("type") == "output_text":
                            return content_item["text"], None
            return str(body), None
        except Exception as e:
            if attempt == 1:
                return None, str(e)[:200]
            time.sleep(1)
    return None, "max_retries"

def call_axio(model: str, messages: list, max_tokens: int = 256) -> tuple[str | None, str | None]:
    """Call Axio Fusion API (no proxy - localhost)."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
    }
    data = json.dumps(payload).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{AXIO_URL}/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json", "Authorization": "Bearer test"},
            )
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            body = json.loads(resp.read().decode())
            return body["choices"][0]["message"]["content"], None
        except Exception as e:
            if attempt == 2:
                return None, str(e)[:200]
            time.sleep(2)
    return None, "max_retries"

# ── Benchmark definitions (9 categories, 20 benchmarks) ────────────────────
BENCHMARKS = [
    # Category 1: Science Knowledge
    ("global_mmlu_lite.jsonl", "Science-MMLU-Global", "mcq",
     lambda r: (f"Question: {r.get('question','')}\nChoices: {r.get('choices',[])}. "
                f"Answer with the letter only."),
     lambda r: str(r.get("answer", "")).strip().upper()[:5]),
    
    ("mmmu_text_science.jsonl", "Science-MMMU-Pro", "mcq",
     lambda r: (f"Question: {r.get('question','')}\nOptions: {r.get('options', r.get('choices',[]))}. "
                f"Answer with the letter only."),
     lambda r: str(r.get("answer", "")).strip().upper()[:5]),
    
    # Category 2: Multilingual
    ("flores_translation_instruction.jsonl", "Multilingual-Flores", "translation",
     lambda r: str(r.get("instruction", r.get("prompt", "")))[:500],
     lambda r: str(r.get("reference", r.get("answer", "")))[:200]),
    
    # Category 3: Code
    ("humaneval.jsonl", "Code-HumanEval", "code",
     lambda r: f"Complete this Python function:\n{r.get('prompt','')}\n\nOnly output the completed code.",
     lambda r: str(r.get("canonical_solution", r.get("solution", "")))[:500]),
    
    ("livecodebench_mini.jsonl", "Code-LiveCodeBench", "code",
     lambda r: str(r.get("prompt", r.get("question", "")))[:500],
     lambda r: str(r.get("solution", r.get("canonical_solution", "")))[:500]),
    
    # Category 4: Math
    ("math_500.jsonl", "Math-MATH500", "math",
     lambda r: f"Solve: {r.get('problem', r.get('question',''))}\nOutput only the final answer.",
     lambda r: str(r.get("answer", r.get("solution", ""))).strip()),
    
    ("aime_recent.jsonl", "Math-AIME", "math",
     lambda r: f"Solve: {r.get('problem', r.get('question',''))}\nOutput only the integer answer.",
     lambda r: str(r.get("answer", r.get("solution", ""))).strip()),
    
    # Category 5: Logic & Reasoning
    ("arc_challenge.jsonl", "Logic-ARC", "mcq",
     lambda r: (f"Question: {r.get('question','')}\n"
                f"Choices: {r.get('choices',{}).get('text', r.get('choices',{}))}. "
                f"Answer with the letter only."),
     lambda r: str(r.get("answerKey", r.get("answer", ""))).strip().upper()[:5]),
    
    ("bbh.jsonl", "Logic-BBH", "mcq",
     lambda r: (f"Question: {r.get('input', r.get('question',''))}\n"
                f"Choices: {r.get('choices',[])}. Answer with the letter only."),
     lambda r: str(r.get("target", r.get("answer", ""))).strip().upper()[:5]),
    
    # Category 6: Agentic Tool Calling
    ("bfcl_mini.jsonl", "Agentic-BFCL", "tool",
     lambda r: str(r.get("prompt", r.get("question", "")))[:500],
     lambda r: str(r.get("function_call", r.get("answer", "")))[:200]),
    
    ("tau_bench_mini.jsonl", "Agentic-TauBench", "tool",
     lambda r: str(r.get("prompt", r.get("question", "")))[:500],
     lambda r: str(r.get("reference", r.get("answer", "")))[:200]),
    
    # Category 7: Daily Work Knowledge
    ("ifeval.jsonl", "DailyWork-IFEval", "instr",
     lambda r: str(r.get("prompt", r.get("question", "")))[:500],
     lambda r: str(r.get("answer", r.get("reference", "")))[:200]),
    
    ("mt_bench_questions.jsonl", "DailyWork-MTBench", "qa",
     lambda r: str(r.get("question", r.get("prompt", "")))[:500],
     lambda r: str(r.get("answer", r.get("reference", "")))[:200]),
    
    # Category 8: Hallucination & Factuality
    ("truthfulqa.jsonl", "Hallucination-TruthfulQA", "mcq",
     lambda r: (f"Question: {r.get('question','')}\n"
                f"Choices: {r.get('mc1_targets',{}).get('choices', r.get('choices',[]))}. "
                f"Answer with the letter only."),
     lambda r: str(r.get("best_answer", r.get("answer", ""))).strip().upper()[:5]),
    
    ("halueval.jsonl", "Hallucination-HaluEval", "binary",
     lambda r: f"Is this response hallucinated? {r.get('question','')}\nResponse: {r.get('answer','')}\nAnswer yes or no.",
     lambda r: str(r.get("hallucination", r.get("label", ""))).strip()),
    
    # Category 9: Vertical Domains
    ("medqa_usmle.jsonl", "Vertical-MedQA", "mcq",
     lambda r: (f"Medical question: {r.get('question','')}\n"
                f"A: {r.get('opa','')}, B: {r.get('opb','')}, C: {r.get('opc','')}, D: {r.get('opd','')}. "
                f"Answer with the letter only."),
     lambda r: str(r.get("answer", r.get("answer_idx", ""))).strip().upper()[:5]),
    
    ("finqa.jsonl", "Vertical-FinQA", "math",
     lambda r: f"Financial question: {r.get('question','')}\nAnswer with the number.",
     lambda r: str(r.get("answer", r.get("solution", ""))).strip()),
    
    ("legalbench.jsonl", "Vertical-LegalBench", "mcq",
     lambda r: (f"Legal question: {r.get('question','')}\n"
                f"Choices: {r.get('choices',[])}. Answer with the letter only."),
     lambda r: str(r.get("answer", "")).strip().upper()[:5]),
    
    ("consultqa_mini.jsonl", "Vertical-ConsultQA", "qa",
     lambda r: str(r.get("question", r.get("prompt", "")))[:500],
     lambda r: str(r.get("answer", r.get("reference", "")))[:200]),
    
    ("policyqa_mini.jsonl", "Vertical-PolicyQA", "qa",
     lambda r: str(r.get("question", r.get("prompt", "")))[:500],
     lambda r: str(r.get("answer", r.get("reference", "")))[:200]),
]

# ── Scoring functions ──────────────────────────────────────────────────────
def score_mcq(response: str, ground_truth: str) -> float:
    """Score multiple choice: extract first letter and compare."""
    resp_clean = response.strip().upper()
    gt_clean = ground_truth.strip().upper()
    # Extract first letter from response
    match = re.search(r'[A-E]', resp_clean)
    resp_letter = match.group(0) if match else resp_clean[:5]
    gt_letter = re.search(r'[A-E]', gt_clean)
    gt_letter = gt_letter.group(0) if gt_letter else gt_clean[:5]
    return 1.0 if resp_letter == gt_letter else 0.0

def score_math(response: str, ground_truth: str) -> float:
    """Score math: extract number and compare."""
    resp_nums = re.findall(r'-?\d+\.?\d*', response)
    gt_nums = re.findall(r'-?\d+\.?\d*', ground_truth)
    if not resp_nums or not gt_nums:
        return 1.0 if response.strip().lower() == ground_truth.strip().lower() else 0.0
    try:
        return 1.0 if abs(float(resp_nums[0]) - float(gt_nums[0])) < 1e-6 else 0.0
    except:
        return 0.0

def score_code(response: str, ground_truth: str) -> float:
    """Score code: check if solution contains key elements."""
    # Simple heuristic: check if response is non-empty and contains code-like content
    if not response or len(response) < 10:
        return 0.0
    code_indicators = ["def ", "class ", "import ", "return ", "print(", "=", "{"]
    score = sum(1 for ind in code_indicators if ind in response)
    return min(1.0, score / 3.0)

def score_binary(response: str, ground_truth: str) -> float:
    """Score binary: yes/no match."""
    resp_lower = response.strip().lower()[:10]
    gt_lower = ground_truth.strip().lower()[:10]
    if "yes" in resp_lower and "yes" in gt_lower:
        return 1.0
    if "no" in resp_lower and "no" in gt_lower:
        return 1.0
    if "true" in resp_lower and ("yes" in gt_lower or "true" in gt_lower):
        return 1.0
    if "false" in resp_lower and ("no" in gt_lower or "false" in gt_lower):
        return 1.0
    return 0.0

def score_qa(response: str, ground_truth: str) -> float:
    """Score QA: basic overlap check."""
    if not response or not ground_truth:
        return 0.0
    resp_words = set(response.lower().split())
    gt_words = set(ground_truth.lower().split())
    if not gt_words:
        return 0.0
    overlap = len(resp_words & gt_words) / len(gt_words)
    return min(1.0, overlap)

def score_tool(response: str, ground_truth: str) -> float:
    """Score tool calling: check for function call structure."""
    if not response:
        return 0.0
    tool_indicators = ["function", "call", "arguments", "tool", "{", "}"]
    return sum(1 for ind in tool_indicators if ind.lower() in response.lower()) / len(tool_indicators)

def score_translation(response: str, ground_truth: str) -> float:
    """Score translation: basic length and content check."""
    if not response or len(response) < 5:
        return 0.0
    return min(1.0, len(response.strip()) / max(len(ground_truth.strip()), 1))

SCORERS = {
    "mcq": score_mcq,
    "math": score_math,
    "code": score_code,
    "binary": score_binary,
    "qa": score_qa,
    "tool": score_tool,
    "translation": score_translation,
    "instr": score_qa,
}

# ── Main evaluation ────────────────────────────────────────────────────────
def load_benchmark(name: str) -> list:
    path = os.path.join(BENCHMARK_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line.strip()) for line in f]

def run_benchmark(filename: str, label: str, btype: str, formatter, answer_fn, 
                  models: list[str], limit: int) -> dict:
    """Run one benchmark across all specified models."""
    records = load_benchmark(filename)[:limit]
    if not records:
        return {"label": label, "error": "no_records"}
    
    scorer = SCORERS.get(btype, score_qa)
    results = {"label": label, "type": btype, "total_samples": len(records), "models": {}}
    
    for model_name in models:
        scores = []
        latencies = []
        failures = 0
        
        for i, record in enumerate(records):
            try:
                prompt = formatter(record)
                ground_truth = answer_fn(record)
            except Exception:
                prompt = str(record.get("question", record.get("prompt", "")))[:500]
                ground_truth = str(record.get("answer", ""))
            
            messages = [{"role": "user", "content": prompt}]
            
            t0 = time.time()
            if model_name.startswith("axio-"):
                response, error = call_axio(model_name, messages, max_tokens=256)
            else:
                # Baseline single model
                reasoning = "max" if model_name in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna") else ""
                response, error = call_cpa_baseline(model_name, messages, reasoning_effort=reasoning)
            
            elapsed = time.time() - t0
            
            if response and not error:
                score = scorer(response, ground_truth)
                scores.append(score)
                latencies.append(elapsed)
            else:
                failures += 1
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        
        results["models"][model_name] = {
            "samples_scored": len(scores),
            "failures": failures,
            "avg_score": round(avg_score, 4),
            "avg_latency_s": round(avg_latency, 2),
            "score_rate": round(len(scores) / len(records) * 100, 1),
        }
        
        print(f"  [{model_name}] {label}: score={avg_score:.3f} latency={avg_latency:.1f}s "
              f"({len(scores)}/{len(records)} ok, {failures} fail)", flush=True)
    
    return results


# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== Axio Fusion Comprehensive Evaluation ===", flush=True)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"CPA Key: {'set' if CPA_KEY else 'MISSING'}", flush=True)
    print(f"Samples per benchmark: {MAX_SAMPLES_PER_BENCH}", flush=True)
    print(f"Benchmarks: {len(BENCHMARKS)}", flush=True)
    
    # Models to test
    all_models = ["axio-fast", "axio-terra", "axio-pro", 
                  "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
    
    all_results = []
    total_start = time.time()
    
    for filename, label, btype, formatter, answer_fn in BENCHMARKS:
        print(f"\n[{label}] ({btype}) {filename}", flush=True)
        result = run_benchmark(filename, label, btype, formatter, answer_fn,
                               all_models, MAX_SAMPLES_PER_BENCH)
        all_results.append(result)
    
    total_elapsed = time.time() - total_start
    
    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SUMMARY (total: {total_elapsed:.0f}s)", flush=True)
    print(f"{'='*80}")
    
    # Compute per-model averages across all benchmarks
    model_totals = {m: {"scores": [], "latencies": [], "count": 0} for m in all_models}
    
    for result in all_results:
        for model_name, stats in result.get("models", {}).items():
            if stats["samples_scored"] > 0:
                model_totals[model_name]["scores"].append(stats["avg_score"])
                model_totals[model_name]["latencies"].append(stats["avg_latency_s"])
                model_totals[model_name]["count"] += 1
    
    print(f"\n{'Model':<20} {'Avg Score':>10} {'Avg Latency':>12} {'Benchmarks':>12}")
    print(f"{'-'*56}")
    
    for model_name in all_models:
        mt = model_totals[model_name]
        if mt["count"] > 0:
            avg_s = sum(mt["scores"]) / len(mt["scores"])
            avg_l = sum(mt["latencies"]) / len(mt["latencies"])
            print(f"{model_name:<20} {avg_s:>10.4f} {avg_l:>9.1f}s {mt['count']:>12}")
    
    # ── Comparison ─────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"FUSION vs SINGLE-MODEL COMPARISON")
    print(f"{'='*80}")
    
    pairs = [
        ("axio-pro", "gpt-5.6-sol"),
        ("axio-terra", "gpt-5.6-terra"),
        ("axio-fast", "gpt-5.6-luna"),
    ]
    
    for axio_model, baseline_model in pairs:
        axio_scores = model_totals[axio_model]["scores"]
        base_scores = model_totals[baseline_model]["scores"]
        
        if axio_scores and base_scores:
            axio_avg = sum(axio_scores) / len(axio_scores)
            base_avg = sum(base_scores) / len(base_scores)
            delta = axio_avg - base_avg
            better = "AXIO WINS" if delta > 0 else ("TIE" if delta == 0 else "BASELINE WINS")
            
            axio_lat = sum(model_totals[axio_model]["latencies"]) / len(model_totals[axio_model]["latencies"])
            base_lat = sum(model_totals[baseline_model]["latencies"]) / len(model_totals[baseline_model]["latencies"])
            lat_ratio = axio_lat / base_lat if base_lat > 0 else 0
            
            print(f"\n{axio_model} vs {baseline_model}:")
            print(f"  Score: {axio_avg:.4f} vs {base_avg:.4f} (Δ={delta:+.4f}) → {better}")
            print(f"  Latency: {axio_lat:.1f}s vs {base_lat:.1f}s (ratio={lat_ratio:.1f}x)")
            
            if lat_ratio > 3.0:
                print(f"  ⚠ Latency exceeds 3x guard!")
    
    # Save results
    output_file = os.path.join(RESULTS_DIR, f"eval_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, "w") as f:
        json.dump({
            "config": {
                "max_samples": MAX_SAMPLES_PER_BENCH,
                "timeout": TIMEOUT,
                "models": all_models,
                "benchmark_count": len(BENCHMARKS),
            },
            "total_elapsed_s": round(total_elapsed, 1),
            "results": all_results,
            "model_summary": {
                m: {
                    "avg_score": round(sum(mt["scores"]) / len(mt["scores"]), 4) if mt["scores"] else 0,
                    "avg_latency_s": round(sum(mt["latencies"]) / len(mt["latencies"]), 2) if mt["latencies"] else 0,
                    "benchmarks_completed": mt["count"],
                }
                for m, mt in model_totals.items()
            },
        }, f, indent=2)
    
    print(f"\nResults saved to: {output_file}", flush=True)
