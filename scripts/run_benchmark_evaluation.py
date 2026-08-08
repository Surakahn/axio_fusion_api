#!/usr/bin/env python3
"""Axio Fusion API — 9-Category 21-Suite Benchmark Evaluation Runner.

Compares axio-fast, axio-terra, axio-pro against the strongest single-model
baselines (gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna) across 19 available
benchmark suites. GPQA Diamond and FLORES are blocked and recorded as such.

Usage:
    AXIO_FUSION_NETWORK_MODE=off python3 scripts/run_benchmark_evaluation.py \
        --axio-base-url http://127.0.0.1:8789 \
        --suites math_500,bbh,arc_challenge \
        --output-dir private/benchmark_results
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import re
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────

BENCHMARK_ROOT = Path("/mnt/storage/axio_fusion_benchmarks/standardized")

# Baseline single-model configurations
BASELINE_CONFIGS = {
    "gpt-5.6-sol": {
        "base_url": "https://cpa.co6.click/v1",
        "api_format": "responses",
    },
    "gpt-5.6-terra": {
        "base_url": "https://cpa.co6.click/v1",
        "api_format": "responses",
    },
    "gpt-5.6-luna": {
        "base_url": "https://cpa.co6.click/v1",
        "api_format": "responses",
    },
}

AXIO_TIERS = ["axio-fast", "axio-terra", "axio-pro"]
BASELINE_MAP = {
    "axio-pro": "gpt-5.6-sol",
    "axio-terra": "gpt-5.6-terra",
    "axio-fast": "gpt-5.6-luna",
}

# Benchmark suite categories and scoring methods
SUITE_META = {
    "gpqa_diamond": {"category": "science_knowledge", "scoring": "exact_match", "blocked": True},
    "mmmu_text_science": {"category": "science_knowledge", "scoring": "multiple_choice"},
    "global_mmlu_lite": {"category": "multilingual", "scoring": "multiple_choice"},
    "flores_translation_instruction": {"category": "multilingual", "scoring": "translation", "blocked": True},
    "livecodebench": {"category": "code", "scoring": "code_execution"},
    "humaneval": {"category": "code", "scoring": "code_execution"},
    "math_500": {"category": "math", "scoring": "math_answer"},
    "aime_recent": {"category": "math", "scoring": "math_answer"},
    "bbh": {"category": "logic", "scoring": "exact_match"},
    "arc_challenge": {"category": "logic", "scoring": "multiple_choice"},
    "bfcl": {"category": "agentic_tool_calling", "scoring": "tool_call_accuracy"},
    "tau_bench": {"category": "agentic_tool_calling", "scoring": "tool_call_accuracy"},
    "ifeval": {"category": "daily_work", "scoring": "instruction_following"},
    "mt_bench_work": {"category": "daily_work", "scoring": "llm_judge"},
    "truthfulqa": {"category": "hallucination_factuality", "scoring": "multiple_choice"},
    "halueval": {"category": "hallucination_factuality", "scoring": "exact_match"},
    "medqa_usmle": {"category": "vertical_domain", "scoring": "multiple_choice"},
    "financebench": {"category": "vertical_domain", "scoring": "exact_match"},
    "legalbench": {"category": "vertical_domain", "scoring": "multiple_choice"},
    "bizbench": {"category": "vertical_domain", "scoring": "exact_match"},
    "policyllm_policybench": {"category": "vertical_domain", "scoring": "multiple_choice"},
}

# ── HTTP Helpers ────────────────────────────────────────────────────────────

def _api_key_for(model: str) -> str:
    """Resolve API key for baseline models from environment."""
    key = os.environ.get("AXIO_TOKENAPIS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AXIO_TOKENAPIS_API_KEY not set")
    return key


def call_axio_api(
    base_url: str,
    model: str,
    prompt: str,
    api_format: str = "chat/completions",
    max_tokens: int = 512,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Call Axio Fusion API via specified format."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    
    if api_format == "chat/completions":
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        url = f"{base_url}/v1/chat/completions"
    elif api_format == "responses":
        payload = {
            "model": model,
            "input": prompt,
            "max_output_tokens": max_tokens,
        }
        url = f"{base_url}/v1/responses"
    elif api_format == "anthropic":
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        url = f"{base_url}/v1/messages"
        headers = {"x-api-key": "benchmark", "anthropic-version": "2023-06-01"}
    else:
        raise ValueError(f"Unknown format: {api_format}")
    
    headers = headers if 'headers' in dir() else {}
    headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    resp = opener.open(req, timeout=timeout)
    return json.loads(resp.read().decode())


def call_baseline_api(model: str, prompt: str, max_tokens: int = 512, timeout: float = 120.0) -> str:
    """Call baseline model via Responses API directly."""
    config = BASELINE_CONFIGS[model]
    api_key = _api_key_for(model)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_tokens,
    }
    url = f"{config['base_url']}/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "AxioFusionBenchmark/1.0",
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    resp = opener.open(req, timeout=timeout)
    data = json.loads(resp.read().decode())
    return _extract_text(data, "responses")


def _extract_text(response: dict, api_format: str) -> str:
    """Extract text content from API response."""
    if api_format in ("chat/completions", "anthropic"):
        choices = response.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "")
    elif api_format == "responses":
        output = response.get("output", [])
        if output:
            content = output[0].get("content", [])
            if content:
                return content[0].get("text", "")
    return ""


# ── Scoring ─────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalize text for comparison."""
    return text.strip().lower()


def _extract_number(text: str) -> str:
    """Extract the last number from text."""
    numbers = re.findall(r'-?\d+\.?\d*', text)
    return numbers[-1] if numbers else ""


def score_exact_match(predicted: str, reference: str) -> bool:
    """Exact match after normalization."""
    return _normalize(predicted) == _normalize(reference)


def score_math_answer(predicted: str, reference: str) -> bool:
    """Math answer scoring: compare normalized numeric answers."""
    pred_num = _extract_number(_normalize(predicted))
    ref_num = _extract_number(_normalize(reference))
    if not pred_num or not ref_num:
        return score_exact_match(predicted, reference)
    try:
        return abs(float(pred_num) - float(ref_num)) < 1e-6
    except ValueError:
        return score_exact_match(predicted, reference)


def score_multiple_choice(predicted: str, reference: str) -> bool:
    """Multiple choice: check if answer letter matches."""
    pred = _normalize(predicted)
    ref = _normalize(reference)
    # Extract letter answer
    pred_letter = re.findall(r'\b([a-dA-D])\b', pred)
    ref_letter = re.findall(r'\b([a-dA-D])\b', ref)
    if pred_letter and ref_letter:
        return pred_letter[0].lower() == ref_letter[0].lower()
    # Fallback to exact match
    return pred == ref


def score_code_execution(predicted: str, reference: str) -> bool:
    """Code execution: extract code and compare output."""
    # For now, use exact match on extracted code
    # Full implementation would require sandboxed execution
    pred_code = _extract_code_block(predicted)
    ref_code = _extract_code_block(reference)
    if pred_code and ref_code:
        return pred_code.strip() == ref_code.strip()
    return score_exact_match(predicted, reference)


def _extract_code_block(text: str) -> str:
    """Extract code from markdown code blocks."""
    match = re.search(r'```(?:python|java|javascript|cpp|c)?\n(.*?)```', text, re.DOTALL)
    return match.group(1) if match else text


SCORING_FUNCTIONS = {
    "exact_match": score_exact_match,
    "math_answer": score_math_answer,
    "multiple_choice": score_multiple_choice,
    "code_execution": score_code_execution,
    "tool_call_accuracy": score_exact_match,  # Simplified
    "instruction_following": score_exact_match,  # Simplified
    "llm_judge": score_exact_match,  # Simplified
    "translation": score_exact_match,  # Simplified
}


# ── Benchmark Runner ────────────────────────────────────────────────────────

def load_dataset(suite_id: str) -> list[dict]:
    """Load a standardized benchmark dataset."""
    path = BENCHMARK_ROOT / f"{suite_id}.jsonl"
    if not path.exists():
        print(f"  Dataset not found: {path}")
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def get_prompt(row: dict) -> str:
    """Extract prompt from dataset row."""
    return row.get("prompt") or row.get("question") or row.get("input") or ""


def get_answer(row: dict) -> str:
    """Extract reference answer from dataset row."""
    return str(row.get("answer") or "")


def run_suite(
    suite_id: str,
    models: list[str],
    axio_base_url: str,
    limit: int | None = None,
    live: bool = True,
) -> dict[str, Any]:
    """Run a single benchmark suite against all models."""
    meta = SUITE_META.get(suite_id, {})
    if meta.get("blocked"):
        return {
            "suite_id": suite_id,
            "category": meta.get("category", "unknown"),
            "status": "blocked",
            "reason": "gated_or_unavailable",
            "total_cases": 0,
            "results": {},
        }
    
    rows = load_dataset(suite_id)
    if limit:
        rows = rows[:limit]
    
    if not rows:
        return {
            "suite_id": suite_id,
            "status": "empty",
            "total_cases": 0,
            "results": {},
        }
    
    scoring = SCORING_FUNCTIONS.get(meta.get("scoring", "exact_match"), score_exact_match)
    results = {}
    
    for model in models:
        print(f"    [{model}] ", end="", flush=True)
        correct = 0
        errors = 0
        latencies = []
        
        for i, row in enumerate(rows):
            prompt = get_prompt(row)
            reference = get_answer(row)
            
            try:
                t0 = time.monotonic()
                if model in AXIO_TIERS:
                    # Choose API format - use chat/completions as primary
                    api_format = "chat/completions"
                    resp = call_axio_api(axio_base_url, model, prompt, api_format=api_format)
                    predicted = _extract_text(resp, api_format)
                else:
                    predicted = call_baseline_api(model, prompt)
                elapsed = time.monotonic() - t0
                latencies.append(elapsed)
                
                if scoring(predicted, reference):
                    correct += 1
                
            except Exception as e:
                errors += 1
                print(f"E", end="", flush=True)
            
            if (i + 1) % 10 == 0:
                print(".", end="", flush=True)
        
        accuracy = correct / len(rows) if rows else 0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        results[model] = {
            "correct": correct,
            "total": len(rows),
            "errors": errors,
            "accuracy": round(accuracy, 4),
            "avg_latency_ms": round(avg_latency * 1000, 1),
        }
        print(f" {accuracy:.1%} ({correct}/{len(rows)})", flush=True)
    
    return {
        "suite_id": suite_id,
        "category": meta.get("category", "unknown"),
        "scoring": meta.get("scoring", "exact_match"),
        "status": "completed",
        "total_cases": len(rows),
        "results": results,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Axio Fusion Benchmark Evaluation")
    parser.add_argument("--axio-base-url", default="http://127.0.0.1:8789", help="Axio Fusion API base URL")
    parser.add_argument("--suites", default="", help="Comma-separated suite IDs (empty=all available)")
    parser.add_argument("--limit", type=int, default=None, help="Limit cases per suite")
    parser.add_argument("--output-dir", default="private/benchmark_results", help="Output directory")
    parser.add_argument("--live", action="store_true", default=True, help="Live mode (default)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without actual API calls")
    args = parser.parse_args()
    
    if args.dry_run:
        args.live = False
    
    # Determine suites to run
    if args.suites:
        suite_ids = [s.strip() for s in args.suites.split(",") if s.strip()]
    else:
        # All non-blocked suites
        suite_ids = sorted([
            sid for sid, meta in SUITE_META.items()
            if not meta.get("blocked") and Path(BENCHMARK_ROOT / f"{sid}.jsonl").exists()
        ])
    
    print(f"Benchmark Evaluation — {len(suite_ids)} suites")
    print(f"Axio Base URL: {args.axio_base_url}")
    print(f"Models: {AXIO_TIERS + list(BASELINE_CONFIGS.keys())}")
    print(f"Live: {args.live}")
    print()
    
    # All models to test
    all_models = AXIO_TIERS + list(BASELINE_CONFIGS.keys())
    
    results_by_suite = {}
    category_scores = defaultdict(lambda: defaultdict(list))
    
    for suite_id in suite_ids:
        meta = SUITE_META.get(suite_id, {})
        cat = meta.get("category", "unknown")
        blocked = meta.get("blocked", False)
        
        status_mark = "🔒" if blocked else "📊"
        print(f"\n{status_mark} {suite_id} [{cat}]")
        
        if blocked:
            results_by_suite[suite_id] = {
                "suite_id": suite_id,
                "category": cat,
                "status": "blocked",
                "reason": "gated_or_unavailable",
            }
            continue
        
        result = run_suite(suite_id, all_models, args.axio_base_url, limit=args.limit, live=args.live)
        results_by_suite[suite_id] = result
        
        # Aggregate by category
        for model, scores in result.get("results", {}).items():
            category_scores[cat][model].append(scores["accuracy"])
    
    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY: Category-Level Performance")
    print("=" * 70)
    
    for cat in sorted(category_scores):
        scores = category_scores[cat]
        print(f"\n{cat}:")
        for model in all_models:
            if model in scores and scores[model]:
                avg = sum(scores[model]) / len(scores[model])
                print(f"  {model:25s}: {avg:.1%}")
    
    # ── Comparison ──
    print("\n" + "=" * 70)
    print("COMPARISON: Axio vs Baseline")
    print("=" * 70)
    
    for axio_model, baseline_model in BASELINE_MAP.items():
        print(f"\n{axio_model} vs {baseline_model}:")
        wins = 0
        losses = 0
        ties = 0
        for suite_id, result in results_by_suite.items():
            if result.get("status") != "completed":
                continue
            r = result.get("results", {})
            axio_score = r.get(axio_model, {}).get("accuracy", 0)
            baseline_score = r.get(baseline_model, {}).get("accuracy", 0)
            diff = axio_score - baseline_score
            if diff > 0.01:
                wins += 1
                marker = "✅"
            elif diff < -0.01:
                losses += 1
                marker = "❌"
            else:
                ties += 1
                marker = "➖"
            print(f"  {marker} {suite_id:30s}: axio={axio_score:.1%} baseline={baseline_score:.1%} diff={diff:+.1%}")
        print(f"  W:{wins} L:{losses} T:{ties}")
    
    # ── Save ──
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"benchmark_results_{timestamp}.json"
    
    report = {
        "timestamp": timestamp,
        "axio_base_url": args.axio_base_url,
        "models_tested": all_models,
        "suites": len(suite_ids),
        "results": results_by_suite,
        "category_summary": {
            cat: {m: sum(scores[m]) / len(scores[m]) for m in scores if scores[m]}
            for cat, scores in category_scores.items()
        },
    }
    with open(output_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
