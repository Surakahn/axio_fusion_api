from axio_fusion_api.call_cost import (
    product_call_cost_contract,
    provider_call_cost_receipt,
)
from axio_fusion_api.compat import canonicalize_payload, public_route_summary
from axio_fusion_api.router import build_route_plan
from axio_fusion_api.schemas import PUBLIC_MODELS, FusionRequest, canonical_public_model
from axio_fusion_api.trace_store import safe_execution_trace
from axio_fusion_api.orchestrator import FusionEngine


def test_public_models_are_three_independent_products_with_ordered_contracts():
    assert PUBLIC_MODELS == ("axio-luna", "axio-terra", "axio-sol")
    contracts = [product_call_cost_contract(model) for model in PUBLIC_MODELS]
    assert [row["intelligence_rank"] for row in contracts] == [3, 2, 1]
    assert [row["cost_rank"] for row in contracts] == [1, 2, 3]
    assert [row["algorithm"] for row in contracts] == [
        "fast_direct_cascade",
        "terra_selective_fusion",
        "pro_panel_judge_synthesis",
    ]
    assert all(row["usd_comparison_used"] is False for row in contracts)


def test_legacy_public_names_are_compatibility_aliases_only():
    assert canonical_public_model("axio-fast") == "axio-luna"
    assert canonical_public_model("axio-pro") == "axio-sol"
    assert canonicalize_payload({"model": "axio-fast", "messages": [{"role": "user", "content": "x"}]}).public_model == "axio-luna"
    assert canonicalize_payload({"model": "axio-pro", "messages": [{"role": "user", "content": "x"}]}).public_model == "axio-sol"


def test_each_product_keeps_distinct_route_algorithm_and_call_contract():
    for model, expected_strategy_prefix in (
        ("axio-luna", "fast_"),
        ("axio-terra", "terra_"),
        ("axio-sol", "pro_"),
    ):
        request = FusionRequest(model=model, prompt="short task")
        route = build_route_plan(request, [])
        assert route["public_model"] == model
        assert route["strategy"].startswith(expected_strategy_prefix)
        assert route["call_cost_contract"]["public_model"] == model
        assert route["call_cost_contract"]["admitted_call_cap"] >= 1
        assert public_route_summary(route)["call_cost_contract"]["public_model"] == model


def test_call_cost_counts_attempts_and_does_not_claim_cheaper_without_benchmark():
    receipt = provider_call_cost_receipt(
        "axio-sol",
        attempted_calls=6,
        retry_calls=2,
        judge_calls=1,
        synthesizer_calls=1,
    )
    assert receipt["measurement"] == "attempted_provider_calls"
    assert receipt["provider_call_count_total"] == 6
    assert receipt["relative_call_count_ratio"] == 6.0
    assert receipt["cheaper_than_baseline"] is None
    assert receipt["cheaper_claim_status"] == "unverified_without_paired_benchmark"
    assert receipt["usd_comparison_used"] is False


def test_safe_trace_exposes_relative_call_count_without_absolute_price_claim():
    request = FusionRequest(model="axio-luna", prompt="short task")
    response = FusionEngine([]).complete(request, live=False)
    receipt = safe_execution_trace(response)
    assert receipt["call_cost"]["public_model"] == "axio-luna"
    assert receipt["call_cost"]["measurement"] == "attempted_provider_calls"
    assert receipt["call_cost"]["usd_comparison_used"] is False
    assert receipt["call_cost"]["cheaper_than_baseline"] is None
