from __future__ import annotations

from axio_fusion_api.evaluation import _final_campaign_summary


def _campaign(status: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "mode": "live",
        "expected_run_count": 1,
        "completed_or_resumed_run_count": 1,
        "candidate_count": 1,
        "run_unit_count": 1,
        "missing_suite_count": 0,
        "policy": {
            "provider_baseline_selection": "externally_ranked_top_three_pre_registered",
            "available_provider_baseline_count": 3,
        },
        "claim_summary": {"all_final_claims_allowed": True},
        "readiness_preflight_receipt": {
            "schema": "axio_fusion_api.benchmark_readiness_preflight_receipt.v1",
            "readiness_digest_sha256": "a" * 64,
            "all_required_suites_ready": True,
            "will_claim_audit_be_possible": True,
            "registry_final_claim_ready": True,
            "registry_live_probe_proven": True,
            "final_claim_provider_baselines_pre_registered": True,
        },
    }
    if status is not None:
        payload["status"] = status
    return payload


def test_final_campaign_requires_live_complete_terminal_state() -> None:
    summary, missing = _final_campaign_summary(_campaign("partial"))

    assert summary["status"] == "partial"
    assert {row["kind"] for row in missing} >= {"campaign_not_live_complete"}


def test_final_campaign_rejects_missing_or_blocked_status() -> None:
    for status in (None, "blocked"):
        _summary, missing = _final_campaign_summary(_campaign(status))
        reason = next(row for row in missing if row["kind"] == "campaign_not_live_complete")
        assert reason["status"] == (status or "missing")


def test_final_campaign_accepts_live_complete_status() -> None:
    summary, missing = _final_campaign_summary(_campaign("live_complete"))

    assert summary["status"] == "live_complete"
    assert not any(row["kind"] == "campaign_not_live_complete" for row in missing)
