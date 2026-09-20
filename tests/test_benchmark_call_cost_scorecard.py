from axio_fusion_api.evaluation import (
    _provider_call_count_per_case,
    _relative_call_cost_comparison,
    _scorecard_candidate_efficiency_reason_codes,
    _scorecard_comparison_efficiency_reason_codes,
    _scorecard_provider_tier_efficiency_reason_codes,
)


def _run(*, candidate_id: str, score: float | None, calls: int, case_ids: list[str], case_count: int | None = None):
    return {
        "candidate_id": candidate_id,
        "suite_id": "arc_challenge",
        "case_count": len(case_ids) if case_count is None else case_count,
        "provider_call_count": calls,
        "accuracy": score,
        "case_results": [
            {"case_id": case_id, "correct": score is not None and score >= 0.5}
            for case_id in case_ids
        ],
    }


def test_call_cost_uses_attempted_calls_per_case_and_proves_only_complete_pair():
    axio = _run(candidate_id="axio-sol", score=0.9, calls=2, case_ids=["a", "b", "c", "d"])
    baseline = _run(candidate_id="provider::rank-1", score=0.9, calls=4, case_ids=["a", "b", "c", "d"])

    receipt = _relative_call_cost_comparison(
        axio,
        baseline,
        axio_score=0.9,
        baseline_score=0.9,
    )

    assert _provider_call_count_per_case(axio) == 0.5
    assert receipt["measurement"] == "attempted_provider_calls_per_case"
    assert receipt["relative_call_count_ratio"] == 0.5
    assert receipt["paired_case_set_complete"] is True
    assert receipt["cheaper_than_baseline"] is True
    assert receipt["cheaper_claim_status"] == "proven"


def test_call_cost_rejects_incomplete_or_different_case_sets():
    axio = _run(candidate_id="axio-terra", score=0.9, calls=2, case_ids=["a", "b", "c", "d"])
    baseline = _run(candidate_id="provider::rank-2", score=0.9, calls=4, case_ids=["a", "b", "x", "y"])

    receipt = _relative_call_cost_comparison(
        axio,
        baseline,
        axio_score=0.9,
        baseline_score=0.9,
    )

    assert receipt["relative_call_count_ratio"] == 0.5
    assert receipt["paired_case_count"] == 2
    assert receipt["paired_case_set_complete"] is False
    assert receipt["cheaper_than_baseline"] is None
    assert receipt["cheaper_claim_status"] == "unverified_missing_paired_call_or_quality_data"


def test_call_cost_quality_and_call_gates_are_fail_closed():
    axio = _run(candidate_id="axio-luna", score=0.4, calls=2, case_ids=["a", "b"])
    baseline = _run(candidate_id="provider::rank-3", score=0.8, calls=2, case_ids=["a", "b"])

    quality_failure = _relative_call_cost_comparison(
        axio,
        baseline,
        axio_score=0.4,
        baseline_score=0.8,
    )
    assert quality_failure["relative_call_count_ratio"] == 1.0
    assert quality_failure["cheaper_than_baseline"] is False
    assert quality_failure["cheaper_claim_status"] == "quality_or_call_gate_not_met"

    missing_quality = _relative_call_cost_comparison(
        axio,
        baseline,
        axio_score=None,
        baseline_score=0.8,
    )
    assert missing_quality["cheaper_than_baseline"] is None
    assert missing_quality["cheaper_claim_status"] == "unverified_missing_paired_call_or_quality_data"


def test_call_cost_does_not_normalize_negative_attempts_as_free_calls():
    run = _run(candidate_id="axio-luna", score=0.8, calls=-1, case_ids=["a"])
    assert _provider_call_count_per_case(run) is None


def test_scorecard_efficiency_audit_requires_relative_call_fields():
    candidate = {
        "total_estimated_cost_usd": 1.0,
        "cost_per_case_usd": 1.0,
        "provider_call_count": 1,
        "average_latency_ms": 10.0,
        "p50_latency_ms": 10.0,
        "p95_latency_ms": 10.0,
    }
    assert "missing_provider_call_count_per_case" in _scorecard_candidate_efficiency_reason_codes(candidate)

    tier = {
        "estimated_cost_usd": 1.0,
        "cost_per_case_usd": 1.0,
        "provider_call_count": 1,
        "p50_case_latency_ms": 10.0,
        "p95_case_latency_ms": 10.0,
    }
    assert "missing_provider_call_count_per_case" in _scorecard_provider_tier_efficiency_reason_codes(tier)

    comparison = {
        "axio_estimated_cost_usd": 1.0,
        "baseline_estimated_cost_usd": 1.0,
        "axio_cost_per_case_usd": 1.0,
        "baseline_cost_per_case_usd": 1.0,
        "axio_p50_latency_ms": 10.0,
        "baseline_p50_latency_ms": 10.0,
        "axio_p95_latency_ms": 10.0,
        "baseline_p95_latency_ms": 10.0,
    }
    reasons = _scorecard_comparison_efficiency_reason_codes(comparison)
    assert "missing_relative_call_count_ratio" in reasons
    assert "missing_paired_case_count" in reasons
    assert "paired_case_set_incomplete" in reasons

    comparison.update(
        {
            "axio_provider_call_count_per_case": 1.0,
            "baseline_provider_call_count_per_case": 1.0,
            "relative_call_count_ratio": 1.0,
            "paired_case_count": 2,
            "paired_case_set_complete": True,
        }
    )
    assert _scorecard_comparison_efficiency_reason_codes(comparison) == []
