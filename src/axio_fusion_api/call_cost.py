"""Provider-call cost accounting for the three independent Axio products.

The public products are compared with their corresponding single-model
provider baselines by attempted provider calls, not by provider-specific USD
prices.  This module only defines bounded accounting receipts; it deliberately
does not infer a quality or "cheaper" claim without paired benchmark evidence.
"""

from __future__ import annotations

from typing import Any, Mapping


_PRODUCT_CONTRACTS: Mapping[str, Mapping[str, Any]] = {
    "axio-luna": {
        "intelligence_rank": 3,
        "cost_rank": 1,
        "algorithm": "fast_direct_cascade",
        "baseline_rank": 3,
        "default_call_cap": 2,
    },
    "axio-terra": {
        "intelligence_rank": 2,
        "cost_rank": 2,
        "algorithm": "terra_selective_fusion",
        "baseline_rank": 2,
        "default_call_cap": 6,
    },
    "axio-sol": {
        "intelligence_rank": 1,
        "cost_rank": 3,
        "algorithm": "pro_panel_judge_synthesis",
        "baseline_rank": 1,
        "default_call_cap": 9,
    },
}

_ALIASES = {
    "axio-fast": "axio-luna",
    "fast": "axio-luna",
    "luna": "axio-luna",
    "axio-pro": "axio-sol",
    "pro": "axio-sol",
    "sol": "axio-sol",
    "terra": "axio-terra",
}


def canonical_cost_model(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _PRODUCT_CONTRACTS:
        return normalized
    return _ALIASES.get(normalized, "axio-terra")


def product_call_cost_contract(
    public_model: str | None,
    *,
    admitted_call_cap: int | None = None,
) -> dict[str, Any]:
    """Return the static, bounded contract for one independent product."""

    model = canonical_cost_model(public_model)
    source = _PRODUCT_CONTRACTS[model]
    cap = max(1, int(admitted_call_cap or source["default_call_cap"]))
    return {
        "schema": "axio_fusion_api.product_call_cost_contract.v1",
        "public_model": model,
        "algorithm": str(source["algorithm"]),
        "intelligence_rank": int(source["intelligence_rank"]),
        "cost_rank": int(source["cost_rank"]),
        "corresponding_baseline_rank": int(source["baseline_rank"]),
        "baseline_call_count_per_case": 1,
        "admitted_call_cap": cap,
        "measurement": "attempted_provider_calls",
        "usd_comparison_used": False,
        "quality_gate_required_for_cheaper_claim": True,
        "cheaper_claim_status": "unverified",
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def provider_call_cost_receipt(
    public_model: str | None,
    *,
    attempted_calls: int,
    successful_calls: int | None = None,
    failed_calls: int | None = None,
    retry_calls: int = 0,
    judge_calls: int = 0,
    synthesizer_calls: int = 0,
    baseline_calls: int = 1,
    quality_score: float | None = None,
    baseline_quality_score: float | None = None,
    admitted_call_cap: int | None = None,
) -> dict[str, Any]:
    """Build a safe relative call-count receipt for one completed request.

    ``attempted_calls`` counts every provider attempt, including failures and
    retries.  A successful/failed split is optional because some runtime paths
    cannot prove it without provider-specific receipts.  Quality efficiency is
    emitted only when both quality scores are supplied by a paired evaluator.
    """

    total = max(0, int(attempted_calls))
    baseline = max(1, int(baseline_calls))
    successful = None if successful_calls is None else max(0, min(total, int(successful_calls)))
    failed = None if failed_calls is None else max(0, min(total, int(failed_calls)))
    quality = None if quality_score is None else max(0.0, min(1.0, float(quality_score)))
    baseline_quality = (
        None
        if baseline_quality_score is None
        else max(0.0, min(1.0, float(baseline_quality_score)))
    )
    quality_per_call = None if quality is None or total <= 0 else round(quality / total, 8)
    baseline_quality_per_call = (
        None
        if baseline_quality is None or baseline <= 0
        else round(baseline_quality / baseline, 8)
    )
    efficiency = None
    if quality_per_call is not None and baseline_quality_per_call and baseline_quality_per_call > 0:
        efficiency = round(quality_per_call / baseline_quality_per_call, 8)
    contract = product_call_cost_contract(public_model, admitted_call_cap=admitted_call_cap)
    return {
        **contract,
        "schema": "axio_fusion_api.provider_call_cost_receipt.v1",
        "provider_call_count_total": total,
        "provider_call_count_attempted": total,
        "provider_call_count_successful": successful,
        "provider_call_count_failed": failed,
        "provider_call_count_retry": max(0, int(retry_calls)),
        "provider_call_count_judge": max(0, int(judge_calls)),
        "provider_call_count_synthesizer": max(0, int(synthesizer_calls)),
        "baseline_call_count": baseline,
        "relative_call_count_ratio": round(total / baseline, 8),
        "quality_score": quality,
        "baseline_quality_score": baseline_quality,
        "quality_per_provider_call": quality_per_call,
        "baseline_quality_per_call": baseline_quality_per_call,
        "relative_quality_per_call": efficiency,
        "cheaper_than_baseline": None,
        "cheaper_claim_status": "unverified_without_paired_benchmark",
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }
