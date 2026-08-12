#!/usr/bin/env python3.11
"""Corrected paired benchmark: Axio via public gateway, baselines via registry.

Fixes the critical defect in run_suite_bench.py where gpt-5.6-* model names
sent to the Axio public API were canonicalized to axio-terra, making the
"baseline" comparisons actually compare axio-terra against itself.

Usage:
  PYTHONPATH=src python3.11 scripts/bench_pair.py arc_challenge --n 15
  PYTHONPATH=src python3.11 scripts/bench_pair.py all --n 10 --output private/bench_pair_results.json
"""
from __future__ import annotations

import argparse, json, hashlib, os, sys, time, traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from axio_fusion_api.registry import load_registry
from axio_fusion_api.providers import HTTPProviderClient
from axio_fusion_api.schemas import (
    FusionRequest, FusionPolicy, normalize_reasoning_effort,
    sha256_text, stable_json,
)
from axio_fusion_api.compat import canonicalize_payload

BENCH_ROOT = Path("/mnt/storage/axio_fusion_benchmarks/standardized")

PAIRINGS = [
    ("axio-pro", "provider::cpa-plus/gpt-5.6-sol"),
    ("axio-terra", "provider::cpa-plus/gpt-5.6-terra"),
    ("axio-fast", "provider::cpa-plus/gpt-5.6-luna"),
]

SUITE_SPECS = {
    "arc_challenge":       {"cat": "logic",           "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "truthfulqa":          {"cat": "hallucination",   "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "medqa_usmle":         {"cat": "vertical",        "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "math_500":            {"cat": "math",            "fmt": "math", "qk": "prompt",   "ok": None,    "ak": "answer"},
    "global_mmlu_lite":    {"cat": "multilingual",    "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "bbh":                 {"cat": "logic",           "fmt": "open", "qk": "prompt",   "ok": None,    "ak": "answer"},
    "policyllm_policybench":{"cat": "vertical",       "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "mmmu_text_science":   {"cat": "science",         "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "halueval":            {"cat": "hallucination",   "fmt": "open", "qk": "question", "ok": "options", "ak": "answer"},
    "flores_translation_instruction": {"cat": "multilingual", "fmt": "translation", "qk": "source", "ok": None, "ak": "reference"},
    "legalbench":          {"cat": "vertical",        "fmt": "mcq",  "qk": "question", "ok": "options", "ak": "answer"},
    "financebench":        {"cat": "vertical",        "fmt": "open", "qk": "prompt",   "ok": None,    "ak": "answer"},
}

REASONING = "max"
TIMEOUT_SEC = 90

def load_suite(name: str, n: int) -> list[dict]:
    path = BENCH_ROOT / f"{name}.jsonl"
    if not path.exists():
        return []
    items = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return items[:min(n, len(items))]


def build_prompt(case: dict, spec: dict) -> str:
    q = str(case.get(spec["qk"], ""))
    if spec["fmt"] == "mcq":
        opts = case.get(spec["ok"], {})
        if isinstance(opts, dict):
            lines = [q, ""]
            for k, v in sorted(opts.items()):
                lines.append(f"{k}) {v}")
            lines.append("")
            lines.append("Answer with only the letter.")
            return "\n".join(lines)
        return f"{q}\n\n{opts}\n\nAnswer with only the letter."
    if spec["fmt"] == "translation":
        src_lang = case.get("source_language", "source")
        tgt_lang = case.get("target_language", "target")
        return f"Translate the following {src_lang} text into {tgt_lang}. Output only the translation.\n\n{q}"
    if spec["fmt"] == "math":
        return f"{q}\n\nProvide the final answer in LaTeX format within \\boxed{{}}."
    return q


def score_exact(pred: str, gold: str) -> bool:
    p, g = pred.strip().upper(), gold.strip().upper()
    if not p or not g:
        return False
    if len(g) == 1 and g.isalpha():
        return g in p[:10]
    return g.lower() in p.lower()


def score_math(pred: str, gold: str) -> bool:
    import re
    p, g = pred.strip(), gold.strip()
    if not p or not g:
        return False
    m = re.findall(r'\\boxed\{([^}]+)\}', p)
    extracted = m[-1].strip() if m else p
    return g.lower().replace(" ", "") in extracted.lower().replace(" ", "")


def score_open(pred: str, gold: str) -> bool:
    p, g = pred.strip().lower(), gold.strip().lower()
    if not p or not g:
        return False
    return g in p


def get_scorer(fmt: str):
    if fmt == "math":
        return score_math
    if fmt in ("open", "translation"):
        return score_open
    return score_exact


def call_axio_public(model: str, prompt: str, max_tokens: int = 256) -> tuple[str | None, float]:
    """Call Axio model through the public API gateway (in-process)."""
    t0 = time.monotonic()
    payload = canonicalize_payload({
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "reasoning_effort": REASONING, "stream": False,
    })
    from axio_fusion_api.registry import load_registry as _lr
    from axio_fusion_api.orchestrator import FusionEngine
    profiles = _lr(os.environ.get("AXIO_FUSION_REGISTRY_PATH", ""), require_prefusion=False)
    engine = FusionEngine(profiles, client=HTTPProviderClient(require_streaming=True))
    try:
        resp = engine.complete(payload, live=True)
        elapsed = time.monotonic() - t0
        return resp.text, elapsed
    except Exception:
        return None, time.monotonic() - t0


def call_provider_direct(profile_id: str, prompt: str, profiles: list, client: HTTPProviderClient, max_tokens: int = 256) -> tuple[str | None, float]:
    """Call provider baseline directly through registry profile."""
    t0 = time.monotonic()
    suffix = profile_id.replace("provider::", "")
    profile = next((p for p in profiles if p.profile_id == suffix), None)
    if profile is None:
        return None, 0.0
    request = FusionRequest(
        model=profile.model, prompt=prompt, max_output_tokens=max_tokens,
        reasoning_effort=REASONING, policy=FusionPolicy(live=True),
    )
    try:
        result = client.complete_turn(profile, request, prompt=prompt,
            system="You are a helpful assistant.", timeout=TIMEOUT_SEC)
        elapsed = time.monotonic() - t0
        return result.text, elapsed
    except Exception:
        return None, time.monotonic() - t0


def run_pair(suite_name: str, axio_model: str, baseline_id: str,
             cases: list[dict], spec: dict, profiles: list, client: HTTPProviderClient) -> dict:
    scorer = get_scorer(spec["fmt"])
    gold_key = spec["ak"]
    
    axio_correct = 0
    baseline_correct = 0
    axio_latencies = []
    baseline_latencies = []
    paired_cases = []
    both = 0
    neither = 0
    
    for i, case in enumerate(cases):
        prompt = build_prompt(case, spec)
        gold = str(case.get(gold_key, ""))
        
        axio_text, axio_lat = call_axio_public(axio_model, prompt)
        base_text, base_lat = call_provider_direct(baseline_id, prompt, profiles, client)
        
        axio_ok = scorer(axio_text or "", gold)
        base_ok = scorer(base_text or "", gold)
        
        if axio_ok: axio_correct += 1
        if base_ok: baseline_correct += 1
        if axio_ok and base_ok: both += 1
        if not axio_ok and not base_ok: neither += 1
        
        if axio_lat: axio_latencies.append(axio_lat)
        if base_lat: baseline_latencies.append(base_lat)
        
        paired_cases.append({
            "case_idx": i,
            "case_id": sha256_text(json.dumps({"suite": suite_name, "idx": i, "q_prefix": case.get(spec["qk"], "")[:60]}, sort_keys=True)),
            "axio_correct": axio_ok,
            "baseline_correct": base_ok,
            "axio_latency_s": round(axio_lat, 2) if axio_lat else None,
            "baseline_latency_s": round(base_lat, 2) if base_lat else None,
        })
        
        status = "✓✓" if axio_ok and base_ok else ("A✓" if axio_ok else ("B✓" if base_ok else "✗✗"))
        sys.stderr.write(f"  [{i+1}/{len(cases)}] {status} axio={axio_ok} base={base_ok} ({axio_lat:.1f}s/{base_lat:.1f}s)\n")
        sys.stderr.flush()
        time.sleep(0.5)
    
    n = len(cases)
    axio_acc = axio_correct / n if n else 0
    base_acc = baseline_correct / n if n else 0
    avg_axio_lat = sum(axio_latencies) / len(axio_latencies) if axio_latencies else 0
    avg_base_lat = sum(baseline_latencies) / len(baseline_latencies) if baseline_latencies else 0
    
    return {
        "suite": suite_name,
        "category": spec["cat"],
        "axio_model": axio_model,
        "baseline_id": baseline_id,
        "n": n,
        "axio_correct": axio_correct,
        "baseline_correct": baseline_correct,
        "axio_accuracy": round(axio_acc, 4),
        "baseline_accuracy": round(base_acc, 4),
        "delta": round(axio_acc - base_acc, 4),
        "both_correct": both,
        "neither_correct": neither,
        "axio_avg_latency_s": round(avg_axio_lat, 2),
        "baseline_avg_latency_s": round(avg_base_lat, 2),
        "axio_only": axio_correct - both,
        "baseline_only": baseline_correct - both,
        "paired_cases": paired_cases,
        "reasoning_effort": REASONING,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "raw_prompts_persisted": False,
        "raw_outputs_persisted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=list(SUITE_SPECS) + ["all"], help="Suite to run")
    parser.add_argument("--n", type=int, default=15, help="Samples per suite")
    parser.add_argument("--output", default="private/bench_pair_corrected.json", help="Output file")
    parser.add_argument("--pairs", choices=["all", "terra", "pro", "fast"], default="all")
    args = parser.parse_args()
    
    registry_path = os.environ.get("AXIO_FUSION_REGISTRY_PATH", "")
    if not registry_path:
        print("FATAL: AXIO_FUSION_REGISTRY_PATH not set", file=sys.stderr)
        sys.exit(1)
    
    profiles = load_registry(registry_path, require_prefusion=False)
    client = HTTPProviderClient(require_streaming=True)
    
    suites = list(SUITE_SPECS) if args.suite == "all" else [args.suite]
    
    pairings = PAIRINGS
    if args.pairs == "terra":
        pairings = [p for p in PAIRINGS if p[0] == "axio-terra"]
    elif args.pairs == "pro":
        pairings = [p for p in PAIRINGS if p[0] == "axio-pro"]
    elif args.pairs == "fast":
        pairings = [p for p in PAIRINGS if p[0] == "axio-fast"]
    
    all_results = []
    
    for suite_name in suites:
        spec = SUITE_SPECS.get(suite_name)
        if not spec:
            continue
        cases = load_suite(suite_name, args.n)
        if not cases:
            print(f"SKIP {suite_name}: no data", file=sys.stderr)
            continue
        
        for axio_model, baseline_id in pairings:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"  {suite_name} [{spec['cat']}] — {axio_model} vs {baseline_id}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            
            result = run_pair(suite_name, axio_model, baseline_id, cases, spec, profiles, client)
            all_results.append(result)
            
            delta_str = f"+{result['delta']:.1%}" if result['delta'] > 0 else f"{result['delta']:.1%}"
            print(f"\n  {axio_model}: {result['axio_accuracy']:.2%}  |  baseline: {result['baseline_accuracy']:.2%}  |  Δ={delta_str}", file=sys.stderr)
    
    # Summary
    print(f"\n{'='*70}", file=sys.stderr)
    print("SUMMARY", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    
    summary = {}
    for r in all_results:
        key = f"{r['axio_model']} vs {r['baseline_id'].replace('provider::cpa-plus/', '')}"
        if key not in summary:
            summary[key] = {"total_n": 0, "axio_correct": 0, "baseline_correct": 0, "suites": []}
        summary[key]["total_n"] += r["n"]
        summary[key]["axio_correct"] += r["axio_correct"]
        summary[key]["baseline_correct"] += r["baseline_correct"]
        summary[key]["suites"].append(r)
    
    for key, stats in sorted(summary.items()):
        n = stats["total_n"]
        axio_acc = stats["axio_correct"] / n if n else 0
        base_acc = stats["baseline_correct"] / n if n else 0
        delta = axio_acc - base_acc
        delta_str = f"+{delta:.1%}" if delta > 0 else f"{delta:.1%}"
        print(f"  {key}: {axio_acc:.2%} vs {base_acc:.2%} Δ={delta_str} ({n}题)", file=sys.stderr)
    
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "axio_fusion_api.bench_pair_run.v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reasoning_effort": REASONING,
        "suites_run": suites,
        "results": all_results,
        "summary": {
            key: {
                "total_n": stats["total_n"],
                "axio_accuracy": round(stats["axio_correct"] / max(stats["total_n"], 1), 4),
                "baseline_accuracy": round(stats["baseline_correct"] / max(stats["total_n"], 1), 4),
                "delta": round(
                    stats["axio_correct"] / max(stats["total_n"], 1) -
                    stats["baseline_correct"] / max(stats["total_n"], 1), 4),
            }
            for key, stats in sorted(summary.items())
        },
        "raw_prompts_persisted": False,
        "raw_outputs_persisted": False,
    }
    with open(args.output, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nResults → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
