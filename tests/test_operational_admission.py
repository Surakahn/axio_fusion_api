from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api import providers as provider_module
from axio_fusion_api.operational_admission import (
    operational_workload_contract,
    redact_operational_admission,
    run_operational_admission,
)
from axio_fusion_api.providers import ProviderCompletion, ProviderExecutionError
from axio_fusion_api.registry import normalize_profile


def _profile(provider: str = "fixture", model: str = "model"):
    return normalize_profile(
        {
            "provider": provider,
            "model": model,
            "canonical_model_id": model,
            "api_format": "chat",
            "enabled": True,
        }
    )


def _structured_output(workload_id: str) -> str:
    if workload_id == "long_context_structured_output":
        return json.dumps(
            {"record_id": "record-01", "owner": "team-a", "priority": 8, "reason": "synthetic"}
        )
    return json.dumps(
        {"decision": "C", "checks": 4, "risk": "review load", "alternative": "A"}
    )


class _OperationalClient:
    def __init__(self, *, failed_workload: str | None = None, invalid_workload: str | None = None):
        self.failed_workload = failed_workload
        self.invalid_workload = invalid_workload

    def complete_turn(self, _profile, request, *, prompt, system, timeout):
        del prompt, system, timeout
        workload_id = str(request.metadata.get("workload_id") or "")
        provider_module._record_provider_request_receipt(
            status="success" if workload_id != self.failed_workload else "failed",
            key_attempt_count=1,
            transport_attempt_count=1,
            retry_attempt_count=0,
            stream_requested=True,
            stream_observed=True,
            stream_fallback_used=False,
            stream_protocol="sse",
            stream_content_type="text/event-stream",
            stream_frame_count=3,
            strict_streaming_requested=True,
        )
        if workload_id == self.failed_workload:
            raise ProviderExecutionError("fixture timeout", error_code="provider_request_timeout")
        if workload_id == self.invalid_workload:
            return ProviderCompletion("not the required structure")
        if workload_id.endswith("structured_output") or workload_id == "bounded_constraint_reasoning":
            return ProviderCompletion(_structured_output(workload_id))
        if workload_id == "long_form_operational_response":
            return ProviderCompletion("A bounded review policy should inspect the state before promotion. " * 24)
        return ProviderCompletion("record-63 is the largest open quota and belongs to team-d.")


def test_operational_workload_contract_is_fixed_and_prompt_free():
    first = operational_workload_contract()
    second = operational_workload_contract()

    assert first == second
    assert first["workload_count"] == 4
    assert [row["workload_id"] for row in first["workloads"]] == [
        "long_context_short_answer",
        "long_context_structured_output",
        "bounded_constraint_reasoning",
        "long_form_operational_response",
    ]
    serialized = json.dumps(first)
    assert "Synthetic records" not in serialized
    assert "raw_prompts_persisted\": false" in serialized
    assert first["target_benchmark_cases_or_labels_used"] is False


def test_all_fixed_workloads_can_be_formally_admitted_without_raw_material():
    report = run_operational_admission(
        [_profile()],
        live=True,
        max_workers=1,
        client=_OperationalClient(),
    )

    assert report["status"] == "ready"
    row = report["profiles"][0]
    assert row["production_admitted"] is True
    assert row["formal_baseline_eligible"] is True
    assert row["expected_attempt_count"] == 4
    assert row["successful_attempt_count"] == 4
    assert row["failure_rate"] == 0.0
    assert row["transport_failure_rate"] == 0.0
    assert row["p50_latency_ms"] is not None
    assert row["p95_latency_ms"] is not None
    assert row["max_latency_ms"] is not None
    assert all(attempt["streaming_evidence_valid"] for attempt in row["attempts"])
    assert all("prompt" not in attempt and "output" not in attempt for attempt in row["attempts"])


def test_production_admission_tolerates_one_bounded_failure_but_formal_baseline_does_not():
    report = run_operational_admission(
        [_profile()],
        live=True,
        max_workers=1,
        client=_OperationalClient(failed_workload="long_form_operational_response"),
    )

    row = report["profiles"][0]
    assert row["production_admitted"] is True
    assert row["formal_baseline_eligible"] is False
    assert row["failure_count"] == 1
    assert row["transport_failure_count"] == 1
    assert row["failure_rate"] == 0.25
    assert "operational_admission_formal_baseline_requires_all_workloads" in row["blockers"]
    assert report["status"] == "blocked"


def test_output_contract_failure_is_visible_and_not_counted_as_transport_failure():
    report = run_operational_admission(
        [_profile()],
        live=True,
        max_workers=1,
        client=_OperationalClient(invalid_workload="long_context_structured_output"),
    )

    row = report["profiles"][0]
    assert row["production_admitted"] is True
    assert row["formal_baseline_eligible"] is False
    assert row["output_contract_failure_count"] == 1
    assert row["transport_failure_count"] == 0
    assert row["stream_failure_count"] == 0


def test_redacted_admission_hashes_provider_identity_and_keeps_only_safe_evidence():
    report = run_operational_admission(
        [_profile("private-provider", "private-model")],
        live=True,
        max_workers=1,
        client=_OperationalClient(),
    )
    safe = redact_operational_admission(report)
    serialized = json.dumps(safe)

    assert "private-provider" not in serialized
    assert "private-model" not in serialized
    assert safe["profiles"][0]["profile_id_sha256"]
    assert safe["profiles"][0]["provider_sha256"]
    assert safe["profiles"][0]["model_sha256"]
    assert safe["raw_prompts_persisted"] is False
    assert safe["raw_provider_outputs_persisted"] is False


def test_dry_run_never_claims_admission_or_calls_provider():
    class ExplodingClient:
        def complete_turn(self, *_args, **_kwargs):
            raise AssertionError("dry run must not call a provider")

    report = run_operational_admission(
        [_profile()], live=False, client=ExplodingClient()
    )

    assert report["network_calls_performed"] is False
    assert report["status"] == "blocked"
    assert report["profiles"][0]["status"] == "skipped"
    assert report["profiles"][0]["formal_baseline_eligible"] is False

