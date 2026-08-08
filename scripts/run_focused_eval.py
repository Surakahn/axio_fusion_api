#!/usr/bin/env python3
"""Focused benchmark evaluation: Axio Fusion vs Single-Model Baselines.
Tests across 14 available benchmark suites, comparing axio models against
single-model baselines via CPA Plus direct API.

Usage:
  source config/current_channels.env
  export AXIO_FUSION_NETWORK_MODE=off
  # Start server first: PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli serve --port 19000 --live
  PYTHONPATH=src .venv/bin/python scripts/run_focused_eval.py
"""
import json, os, sys, time, re, hashlib, requests
from pathlib import Path
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────
AXIO_URL = os.environ.get("AXIO_EVAL_URL", "http://127.0.0.1:19000")
BENCHMARK_DIR = Path("/mnt/storage/axio_fusion_benchmarks/standardized")
RESULTS_DIR = Path("data/evaluation_results/focused_v1")
CPA_BASE = "https://cpa.co6.click/v1"
CPA_KEY = os.environ.get("AXIO_CPA_PLUS_API_KEY", "")
MAX_SAMPLES = 30  # Per model per benchmark
TIMEOUT = 120

# Baseline: single models with reasoning=max
BASELINES = {
    "gpt-5.6-sol": "max",    # rank 1 → vs axio-pro
    "gpt-5.6-terra": "max",  # rank 2 → vs axio-terra
    "gpt-5.6-luna": "max",   # rank 3 → vs axio-fast
}

AXIO_TIERS = {
    "axio-pro": "gpt-5.6-sol",
    "axio-terra": "gpt-5.6-terra",
    "axio-fast": "gpt-5.6-luna",
}

# Benchmark suites available
BENCHMARKS = [
    ("math_500.jsonl", "Math-MATH500", "math"),
    ("aime_recent.jsonl", "Math-AIME", "math"),
    ("arc_challenge.jsonl", "Logic-ARC", "mcq"),
    ("bbh.jsonl", "Logic-BBH", "mcq"),
    ("truthfulqa.jsonl", "Hallucination-TruthfulQA", "mcq"),
    ("halueval.jsonl", "Hallucination-HaluEval", "binary"),
    ("global_mmlu_lite.jsonl", "Multilingual-GlobalMMLU", "mcq"),
    ("mmmu_text_science.jsonl", "Science-MMMU-Pro", "mcq"),
    ("medqa_usmle.jsonl", "Vertical-MedQA", "mcq"),
    ("financebench.jsonl", "Vertical-FinanceBench", "math"),
    ("legalbench.jsonl", "Vertical-LegalBench", "mcq"),
    ("bizbench.jsonl", "Vertical-BizBench", "mcq"),
    ("policyllm_policybench.jsonl", "Vertical-PolicyBench", "mcq"),
    ("flores_translation_instruction.jsonl", "Multilingual-FLORES", "translation"),
]

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────────
def call_axio(model: str, messages: list, max_tokens: int = 256,
              reasoning_effort: str = "max") -> tuple[str | None, str | None]:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
        "reasoning_effort": reasoning_effort,
    }
    try:
        r = requests.post(f"{AXIO_URL}/v1/chat/completions", json=payload, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return data["choices"][0]["message"]["content"], None
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)[:200]

def call_cpa_baseline(model: str, messages: list, max_tokens: int = 256,
                      reasoning_effort: str = "max") -> tuple[str | None, str | None]:
    """Call single model directly via CPA Plus Responses API."""
    input_items = []
    for m in messages:
        input_items.append({"role": m["role"], "content": m["content"]})
    payload = {
        "model": model,
        "input": input_items,
        "max_output_tokens": max_tokens,
        "reasoning": {"effort": reasoning_effort},
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {CPA_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(f"{CPA_BASE}/responses", json=payload, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            output = data.get("output", [])
            if isinstance(output, list):
                texts = [item.get("content", []) for item in output if item.get("type") == "message"]
                all_text = []
                for t in texts:
                    if isinstance(t, list):
                        all_text.extend(part.get("text", "") for part in t if part.get("type") == "output_text")
                    elif isinstance(t, str):
                        all_text.append(t)
                return "\n".join(all_text) if all_text else str(output), None
            return str(output), None
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)[:200]

# ── Scoring ────────────────────────────────────────────────────────────────
def norm_ans(text: str) -> str:
    if not text: return ""
    text = str(text).strip().upper()
    # Try patterns: A), (A), ANSWER: A, etc.
    for pat in [r'\bANSWER\s*(?:IS\s*)?[:\-]?\s*([A-J])\b',
                r'\b([A-J])\b\s*(?:is\s+correct)',
                r'\(([A-J])\)', r'\b([A-J])\)',
                r'^([A-J])[\s\.\,\)]', r'\b([A-J])\b']:
        m = re.search(pat, text, re.IGNORECASE)
        if m: return m.group(1).upper()
    return text[:20]

def ext_math(text: str) -> str:
    if not text: return ""
    # boxed
    boxed = re.findall(r'\\boxed\{([^}]+)\}', str(text))
    if boxed: return boxed[-1].strip()
    # Last number
    nums = re.findall(r'-?\d+\.?\d*', str(text))
    if nums: return nums[-1]
    return str(text).strip()

def norm_math(text: str) -> str:
    text = re.sub(r'[,%\$\s]', '', str(text).strip())
    try: return str(float(text))
    except: return text.strip()

def score_prediction(pred: str, gold: str, ttype: str) -> float:
    if not pred: return 0.0
    if ttype == "mcq":
        p, g = norm_ans(pred), norm_ans(str(gold))
        return 1.0 if p and g and p == g else 0.0
    elif ttype == "math":
        p, g = norm_math(ext_math(pred)), norm_math(str(gold))
        return 1.0 if p and g and p == g else 0.0
    elif ttype == "binary":
        p = str(pred).strip().lower()
        g = str(gold).strip().lower()
        return 1.0 if p == g else 0.0
    elif ttype == "translation":
        return 1.0 if len(str(pred)) > 10 else 0.0  # Basic sanity
    return 0.0

# ── Main ───────────────────────────────────────────────────────────────────
def run_benchmark(bench_file: str, bench_name: str, ttype: str):
    filepath = BENCHMARK_DIR / bench_file
    if not filepath.exists():
        print(f"  SKIP: {filepath} not found")
        return None

    cases = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                try: cases.append(json.loads(line))
                except: pass
    if not cases:
        print(f"  SKIP: no cases in {bench_file}")
        return None

    limit = min(MAX_SAMPLES, len(cases))
    cases = cases[:limit]
    print(f"  {bench_name}: {len(cases)} cases | type={ttype}")

    results = {}
    all_models = list(AXIO_TIERS.keys()) + list(BASELINES.keys())

    for model in all_models:
        scores = []
        errors = 0
        for i, case in enumerate(cases):
            # Extract prompt
            messages = case.get("messages", [])
            if not messages:
                prompt = case.get("prompt", case.get("question", case.get("input", "")))
                if prompt:
                    messages = [{"role": "user", "content": str(prompt)}]
            gold = case.get("answer", case.get("gold", case.get("label", case.get("target", ""))))

            if not messages:
                errors += 1
                continue

            # Call model
            if model in AXIO_TIERS:
                pred, err = call_axio(model, messages)
            else:
                pred, err = call_cpa_baseline(model, messages)

            if err:
                errors += 1
                if errors <= 3:
                    print(f"    [{model}] error[{i}]: {err[:100]}")
                continue

            s = score_prediction(str(pred), str(gold), ttype)
            scores.append(s)

            if i % 10 == 0 and i > 0:
                print(f"    [{model}] {i}/{limit} avg={sum(scores)/len(scores):.3f}")

        avg = sum(scores) / len(scores) if scores else 0.0
        results[model] = {
            "avg_score": round(avg, 4),
            "samples": len(scores),
            "errors": errors,
            "total": limit,
        }
        print(f"    [{model}] final: {avg:.4f} ({len(scores)}/{limit}, {errors} errs)")

    return {"benchmark": bench_name, "type": ttype, "cases": limit, "results": results}


def main():
    print("=" * 70)
    print("Axio Fusion Focused Benchmark Evaluation")
    print(f"Axio URL: {AXIO_URL}")
    print(f"CPA Key: {'***' + CPA_KEY[-4:] if CPA_KEY else 'MISSING'}")
    print("=" * 70)

    all_results = {}
    for bench_file, bench_name, ttype in BENCHMARKS:
        print(f"\n[{bench_name}]")
        result = run_benchmark(bench_file, bench_name, ttype)
        if result:
            all_results[bench_name] = result

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Per-tier comparison
    for axio, baseline in AXIO_TIERS.items():
        print(f"\n{axio} vs {baseline}:")
        axio_wins = 0
        baseline_wins = 0
        for bench_name, result in all_results.items():
            r = result["results"]
            axio_score = r.get(axio, {}).get("avg_score", 0)
            base_score = r.get(baseline, {}).get("avg_score", 0)
            winner = "axio" if axio_score > base_score else ("base" if base_score > axio_score else "tie")
            if winner == "axio": axio_wins += 1
            elif winner == "base": baseline_wins += 1
            print(f"  {bench_name:30s} axio={axio_score:.4f} base={base_score:.4f}  [{winner}]")
        print(f"  TOTAL: axio wins={axio_wins} base wins={baseline_wins}")

    # Save results
    output_path = RESULTS_DIR / "focused_eval_results.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
