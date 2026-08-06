#!/usr/bin/env python3
"""Background benchmark evaluation for Axio Fusion API."""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

AXIO_URL = "http://127.0.0.1:18900"
BENCHMARK_DIR = "data/benchmarks"
RESULTS_DIR = "data/evaluation_results"
MAX_SAMPLES = 10

Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)

def call_axio(model, content, max_tokens=128):
    data = json.dumps({
        "model": model, "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"{AXIO_URL}/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        body = json.loads(resp.read().decode())
        return body["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)[:200]

def load_benchmark(name):
    path = os.path.join(BENCHMARK_DIR, name)
    if not os.path.exists(path): return []
    with open(path) as f:
        return [json.loads(line.strip()) for line in f]

BENCHMARKS = [
    ("math_500.jsonl", "Math-MATH500", lambda r: f"Solve: {r.get('problem', r.get('question', ''))}\nAnswer with just the number."),
    ("aime_recent.jsonl", "Math-AIME", lambda r: f"Solve: {r.get('problem', r.get('question', ''))}\nAnswer with just the number."),
    ("humaneval.jsonl", "Code-HumanEval", lambda r: f"Write Python code:\n{r.get('prompt', r.get('question', ''))}"),
    ("arc_challenge.jsonl", "Logic-ARC", lambda r: f"Question: {r.get('question','')}\nChoices: {r.get('choices',{}).get('text', r.get('choices',{}))}. Answer with the letter."),
    ("truthfulqa.jsonl", "Hallucination-TruthfulQA", lambda r: f"Answer truthfully: {r.get('question','')}"),
    ("ifeval.jsonl", "DailyWork-IFEval", lambda r: str(r.get('prompt', r.get('question', '')))[:500]),
    ("medqa_usmle.jsonl", "Vertical-MedQA", lambda r: f"Medical question: {r.get('question','')}\nA: {r.get('opa','')}, B: {r.get('opb','')}, C: {r.get('opc','')}, D: {r.get('opd','')}"),
    ("global_mmlu_lite.jsonl", "Multilingual-GlobalMMLU", lambda r: f"Question: {r.get('question','')}\nChoices: {r.get('choices', [])}. Answer with the letter."),
]

MODELS = ["axio-fast", "axio-terra"]

print(f"Starting evaluation at {time.strftime('%H:%M:%S')}", flush=True)
print(f"Models: {MODELS}, Benchmarks: {len(BENCHMARKS)}, Samples: {MAX_SAMPLES}", flush=True)

all_results = []
total_start = time.time()

for filename, label, formatter in BENCHMARKS:
    records = load_benchmark(filename)[:MAX_SAMPLES]
    if not records:
        print(f"[{label}] No records, skipping", flush=True)
        continue
    
    model_results = {}
    for model in MODELS:
        successes = 0
        total_time = 0
        for i, record in enumerate(records):
            try:
                prompt = formatter(record)
            except:
                prompt = str(record.get('question', record.get('prompt', '')))[:500]
            
            t0 = time.time()
            response, error = call_axio(model, prompt)
            elapsed = time.time() - t0
            
            if response and not error:
                successes += 1
                total_time += elapsed
        
        model_results[model] = {
            "success_rate": round(successes / len(records) * 100, 1),
            "avg_latency": round(total_time / max(successes, 1), 1),
            "samples": len(records),
        }
        print(f"[{label}] {model}: {successes}/{len(records)} ({model_results[model]['success_rate']}%) avg={model_results[model]['avg_latency']}s", flush=True)
    
    all_results.append({"label": label, "results": model_results})

total_time = time.time() - total_start
print(f"\nEvaluation complete in {total_time:.1f}s", flush=True)

output = {
    "schema": "axio_fusion_api.benchmark_evaluation.v1",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "models": MODELS,
    "total_time_seconds": round(total_time, 1),
    "results": all_results,
}
output_path = os.path.join(RESULTS_DIR, f"eval_{time.strftime('%Y%m%d_%H%M%S')}.json")
with open(output_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"Results saved to: {output_path}", flush=True)
