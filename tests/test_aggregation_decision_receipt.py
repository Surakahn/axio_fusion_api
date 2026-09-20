from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.orchestrator import _aggregation_decision_receipt
from axio_fusion_api.compat import render_response
from axio_fusion_api.schemas import CandidateResult, FusionRequest, FusionResponse
from axio_fusion_api.trace_store import safe_execution_trace
from axio_fusion_api.compat import _public_trace_summary


def _candidate(
    candidate_id: str,
    *,
    role: str = "primary_solver",
    answer: str = "bounded answer",
    confidence: float = 0.90,
    evidence: tuple[dict[str, object], ...] = ({"source": "fixture"},),
) -> CandidateResult:
    return CandidateResult(
        candidate_id=candidate_id,
        role=role,
        profile_id=f"profile-{candidate_id}",
        provider=f"provider-{candidate_id}",
        model=f"model-{candidate_id}",
        answer=answer,
        confidence=confidence,
        evidence=evidence,
    )


def _quality_route(*, finalization_mode: str = "provider_judge_synthesis") -> dict[str, object]:
    return {
        "budget": {
            "quality_target": 0.90,
            "fusion_finalization_mode": finalization_mode,
        }
    }


def _ready_judge(candidate_id: str, *, score: float = 0.95, confidence: float = 0.90) -> dict[str, object]:
    return {
        "ready_for_synthesis": True,
        "ranked_candidates": [
            {
                "candidate_id": candidate_id,
                "score": score,
                "calibrated_confidence": confidence,
            }
        ],
        "missing_coverage": [],
        "contradictions": [],
        "collective_blind_spots": [],
    }


def test_provider_synthesis_passes_quality_gate():
    receipt = _aggregation_decision_receipt(
        _quality_route(),
        (_candidate("one"), _candidate("two", role="independent_solver")),
        _ready_judge("one"),
        early_exit=None,
        synthesis_provider_call_count=1,
        synthesis_output_accepted=True,
    )

    assert receipt["decision"] == "provider_synthesis"
    assert receipt["quality_gate_status"] == "passed"
    assert receipt["quality_gap_triggered"] is False
    assert receipt["abstention_recommended"] is False
    assert receipt["candidate_count"] == 2


def test_unresolved_quality_gap_requires_repair_and_advisory_abstention():
    receipt = _aggregation_decision_receipt(
        _quality_route(),
        (_candidate("one", answer="answer", evidence=()),),
        {
            "ready_for_synthesis": False,
            "ranked_candidates": [{"candidate_id": "one", "score": 0.60}],
            "missing_coverage": ["independent_check"],
            "contradictions": [],
            "collective_blind_spots": [],
        },
        early_exit=None,
        synthesis_provider_call_count=0,
        synthesis_output_accepted=False,
    )

    assert receipt["decision"] == "degraded_best_candidate"
    assert receipt["quality_gate_status"] == "repair_required"
    assert receipt["repair_required"] is True
    assert receipt["abstention_recommended"] is True
    assert receipt["blocking_gap_counts"]["missing_coverage"] == 1


def test_synthesis_can_deliver_degraded_output_without_passing_quality_gate():
    receipt = _aggregation_decision_receipt(
        _quality_route(),
        (_candidate("one", evidence=()),),
        _ready_judge("one"),
        early_exit=None,
        synthesis_provider_call_count=1,
        synthesis_output_accepted=True,
    )

    assert receipt["decision"] == "provider_synthesis"
    assert receipt["quality_gate_status"] == "degraded"
    assert receipt["quality_gap_triggered"] is True
    assert receipt["abstention_recommended"] is False


def test_local_consensus_is_recorded_as_its_own_finalization_path():
    receipt = _aggregation_decision_receipt(
        _quality_route(finalization_mode="local_consensus"),
        (_candidate("one"), _candidate("two", role="independent_solver")),
        _ready_judge("one"),
        early_exit=None,
        synthesis_provider_call_count=0,
        synthesis_output_accepted=False,
    )

    assert receipt["decision"] == "local_consensus"
    assert receipt["finalization_mode"] == "local_consensus"
    assert receipt["quality_gate_status"] == "passed"
    assert receipt["abstention_recommended"] is False


def test_early_exit_is_recorded_when_consensus_gate_closes_without_synthesis():
    receipt = _aggregation_decision_receipt(
        _quality_route(finalization_mode="direct"),
        (_candidate("one"), _candidate("two", role="independent_solver")),
        _ready_judge("one"),
        early_exit={"triggered": True, "reason": "high_confidence_consensus"},
        synthesis_provider_call_count=0,
        synthesis_output_accepted=False,
    )

    assert receipt["decision"] == "early_exit_best_candidate"
    assert receipt["early_exit_triggered"] is True
    assert receipt["quality_gate_status"] == "passed"
    assert receipt["abstention_recommended"] is False


def test_no_usable_candidate_is_explicit_abstention():
    receipt = _aggregation_decision_receipt(
        _quality_route(),
        (_candidate("failed", answer="", confidence=0.95),),
        _ready_judge("failed"),
        early_exit=None,
        synthesis_provider_call_count=0,
        synthesis_output_accepted=False,
    )

    assert receipt["decision"] == "abstain"
    assert receipt["candidate_count"] == 0
    assert receipt["quality_gate_status"] == "abstain"
    assert receipt["abstention_recommended"] is True
    assert "no_usable_candidate" in receipt["quality_gap_reason_codes"]


def test_safe_trace_bounds_aggregation_receipt_and_drops_sensitive_input():
    response = FusionResponse(
        text="final answer",
        request=FusionRequest(model="axio-sol", prompt="private prompt"),
        route_plan={},
        candidates=(_candidate("one", answer="private candidate answer"),),
        trace={
            "aggregation_decision": {
                "schema": "axio_fusion_api.aggregation_decision.v1",
                "decision": "provider_synthesis",
                "candidate_count": 1,
                "best_candidate_id": "one",
                "best_candidate_id_sha256": "a" * 64,
                "quality_gate_status": "passed",
                "quality_gap_reason_codes": [],
                "blocking_gap_counts": {},
                "best_candidate_text": "private candidate answer",
                "prompt": "private prompt",
                "provider_output": "private provider output",
                "api_key": "private-secret",
            }
        },
    )

    receipt = safe_execution_trace(response)["aggregation_decision"]
    serialized = json.dumps(receipt, ensure_ascii=False)

    assert receipt["decision"] == "provider_synthesis"
    assert receipt["candidate_count"] == 1
    assert receipt["best_candidate_id_sha256"] == "a" * 64
    assert receipt["raw_candidate_text_persisted"] is False
    assert receipt["raw_prompt_persisted"] is False
    assert receipt["raw_provider_output_persisted"] is False
    assert receipt["secrets_persisted"] is False
    assert "private candidate answer" not in serialized
    assert "private prompt" not in serialized
    assert "private provider output" not in serialized
    assert "private-secret" not in serialized


def test_public_protocol_metadata_exposes_same_bounded_aggregation_decision():
    request = FusionRequest(model="axio-sol", prompt="private prompt")
    decision = {
        "schema": "axio_fusion_api.aggregation_decision.v1",
        "decision": "provider_synthesis",
        "finalization_mode": "provider_judge_synthesis",
        "candidate_count": 2,
        "best_candidate_id_sha256": "b" * 64,
        "quality_gate_status": "passed",
        "synthesis_output_accepted": True,
        "raw_candidate_text_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }
    response = FusionResponse(
        text="final answer",
        request=request,
        route_plan={},
        trace={"aggregation_decision": decision},
    )

    summaries = []
    for api_format in ("chat/completions", "responses", "anthropic", "gemini"):
        rendered = render_response(response, api_format=api_format)
        metadata = rendered.get("metadata", {})
        summaries.append(metadata["fusion_trace_summary"]["aggregation_decision"])

    assert {item["decision"] for item in summaries} == {"provider_synthesis"}
    assert {item["candidate_count"] for item in summaries} == {2}
    assert all(item["best_candidate_id_sha256"] == "b" * 64 for item in summaries)
    assert all(item["raw_candidate_text_persisted"] is False for item in summaries)


def test_public_trace_summary_projects_aggregation_decision_without_content():
    summary = _public_trace_summary(
        {
            "aggregation_decision": {
                "schema": "axio_fusion_api.aggregation_decision.v1",
                "decision": "degraded_best_candidate",
                "candidate_count": 1,
                "best_candidate_id_sha256": "b" * 64,
                "quality_gate_status": "repair_required",
                "quality_gap_reason_codes": ["no_explicit_candidate_evidence"],
                "blocking_gap_counts": {"missing_coverage": 1},
                "repair_required": True,
                "abstention_recommended": True,
                "candidate_text": "private candidate",
                "prompt": "private prompt",
            }
        }
    )

    decision = summary["aggregation_decision"]
    serialized = json.dumps(decision, ensure_ascii=False)
    assert decision["decision"] == "degraded_best_candidate"
    assert decision["quality_gate_status"] == "repair_required"
    assert decision["repair_required"] is True
    assert decision["abstention_recommended"] is True
    assert decision["best_candidate_id_sha256"] == "b" * 64
    assert "private candidate" not in serialized
    assert "private prompt" not in serialized
