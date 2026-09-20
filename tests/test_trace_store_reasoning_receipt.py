from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.schemas import CandidateResult, FusionRequest, FusionResponse
from axio_fusion_api.trace_store import safe_execution_trace


def _safe_candidate_trace(task_execution: dict[str, object]) -> dict[str, object]:
    response = FusionResponse(
        text="answer",
        request=FusionRequest(model="axio-terra", prompt="trace receipt"),
        route_plan={},
        candidates=(
            CandidateResult(
                candidate_id="candidate-1",
                role="primary_solver",
                profile_id="profile-1",
                provider="provider-1",
                model="model-1",
                answer="answer",
                task_execution=task_execution,
            ),
        ),
    )
    return safe_execution_trace(response)


def test_trace_store_projects_empty_reasoning_receipt_without_private_fields():
    receipt = _safe_candidate_trace({})["candidate_outputs"][0]["task_execution"][
        "reasoning_transport_receipt"
    ]

    assert receipt["schema"] == "axio_fusion_api.reasoning_execution_receipt.v1"
    assert receipt["status"] == "not_recorded"
    assert receipt["transport_verified"] is False
    assert receipt["native_reasoning_effort_verified"] is None
    assert receipt["raw_provider_model_id_persisted"] is False
    assert receipt["raw_provider_url_persisted"] is False
    assert receipt["secrets_persisted"] is False


def test_trace_store_projects_native_mapped_and_unverified_receipts():
    cases = (
        {
            "requested_reasoning_effort": "max",
            "effective_reasoning_effort": "max",
            "transport_status": "verified",
            "transport_verified": True,
            "native_reasoning_effort_verified": True,
            "effort_wire_mode": "native",
            "status": "native_effort_verified",
        },
        {
            "requested_reasoning_effort": "max",
            "effective_reasoning_effort": "high",
            "transport_status": "verified",
            "transport_verified": True,
            "native_reasoning_effort_verified": False,
            "effort_wire_mode": "mapped",
            "reasoning_mapping_applied": True,
            "reasoning_mapping_direction": "max->high",
            "status": "verified_effort_mapping",
        },
        {
            "requested_reasoning_effort": "max",
            "effective_reasoning_effort": "",
            "transport_status": "unknown",
            "transport_verified": False,
            "native_reasoning_effort_verified": None,
            "effort_wire_mode": "unverified_passthrough",
            "status": "unverified_effort_passthrough",
        },
    )

    for expected in cases:
        task_execution = {
            "reasoning_transport_receipt": {
                **expected,
                "api_format": "responses",
                "reasoning_transport": "responses_reasoning",
                "requested_reasoning_budget_tokens": 2048,
                "effective_reasoning_budget_tokens": 2048,
                "native_reasoning_budget_verified": True,
                "reasoning_mapping_scope": "profile",
                "provider_model_id": "private-model-id",
                "provider_url": "https://private.invalid/v1",
                "api_key": "private-secret",
            }
        }
        receipt = _safe_candidate_trace(task_execution)["candidate_outputs"][0][
            "task_execution"
        ]["reasoning_transport_receipt"]

        for key, value in expected.items():
            assert receipt[key] == value
        assert receipt["requested_reasoning_budget_tokens"] == 2048
        assert receipt["effective_reasoning_budget_tokens"] == 2048
        assert receipt["native_reasoning_budget_verified"] is True
        assert receipt["secrets_persisted"] is False
        serialized = json.dumps(receipt, ensure_ascii=False)
        assert "private-model-id" not in serialized
        assert "private.invalid" not in serialized
        assert "private-secret" not in serialized

