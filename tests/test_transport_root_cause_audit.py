from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_screening_transport as audit


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _telemetry(
    *,
    attempts: int,
    failed: int,
    classes: list[dict[str, object]] | None = None,
    errors: list[dict[str, object]] | None = None,
    statuses: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "attempt_count": attempts,
        "failed_attempt_count": failed,
        "retryable_failed_attempt_count": failed,
        "retry_round_count": 0,
        "transport_failure_class_counts": classes or [],
        "provider_error_code_counts": errors or [],
        "http_status_counts": statuses or [],
        "retry_receipts": [],
    }


def _case(status: str, telemetry: dict[str, object], *, fail_fast: bool = False) -> dict[str, object]:
    return {
        "status": status,
        "fail_fast_unattempted": fail_fast,
        "failure_telemetry": telemetry,
        "output": "DO_NOT_SERIALIZE_THIS_PROVIDER_OUTPUT",
        "prompt": "DO_NOT_SERIALIZE_THIS_PROMPT",
        "label": "DO_NOT_SERIALIZE_THIS_LABEL",
    }


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    plan = tmp_path / "plan.json"
    state = tmp_path / "state.json"
    transport = tmp_path / "transport.json"
    unit_root = tmp_path / "units"
    unit_root.mkdir()
    _write(
        plan,
        {
            "schema": audit.PLAN_SCHEMA,
            "plan_digest_sha256": "plan-digest",
            "ready": True,
        },
    )
    _write(
        state,
        {
            "schema": audit.CAMPAIGN_SCHEMA,
            "status": "partial",
            "selected_task_count": 1,
            "completed_unit_count": 0,
            "plan_digest_sha256": "plan-digest",
            "network_calls_performed": True,
            "target_suite_calls_performed": False,
        },
    )
    unit = {
        "schema": audit.UNIT_SCHEMA,
        "task_id": "task-1",
        "source_id": "source-a",
        "canonical_identity_sha256": "canonical-a",
        "case_results": [
            _case(
                "transport_failed",
                _telemetry(
                    attempts=1,
                    failed=1,
                    classes=[{"transport_failure_class": "timeout", "count": 1}],
                    errors=[{"provider_error_code": "provider_request_timeout", "count": 1}],
                ),
            ),
            {
                "status": "transport_failed",
                "fail_fast_unattempted": True,
                "transport_failure_class": "screening_fail_fast_gate",
                "output": "DO_NOT_SERIALIZE_THIS_PROVIDER_OUTPUT",
            },
        ],
    }
    unit_path = unit_root / ("a" * 64 + ".private.json")
    _write(unit_path, unit)
    _write(
        transport,
        {
            "schema": audit.TRANSPORT_SCHEMA,
            "status": "blocked",
            "source_plan_file_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
            "source_campaign_state_file_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
            "plan_digest_sha256": "plan-digest",
            "selection_basis": "transport_failure_rate_only",
            "quality_fields_used_for_selection": [],
            "unit_transport_evidence": [
                {
                    "task_id_sha256": _hash("task-1"),
                    "source_id_sha256": _hash("source-a"),
                    "canonical_identity_sha256": _hash("canonical-a"),
                    "transport_failure_count": 2,
                    "transport_failure_rate": 1.0,
                    "fail_fast_unattempted_case_count": 1,
                }
            ],
            "blockers": ["transport_admission_fewer_than_minimum_models"],
        },
    )
    return plan, state, transport, unit_root


def test_audit_is_hash_safe_and_keeps_admission_status_separate(tmp_path: Path) -> None:
    plan, state, transport, unit_root = _inputs(tmp_path)

    result = audit.audit_transport(
        plan_path=plan,
        campaign_state_path=state,
        transport_admission_path=transport,
        unit_root=unit_root,
    )

    encoded = json.dumps(result, ensure_ascii=True)
    assert result["status"] == "ready"
    assert result["transport_admission_status"] == "blocked"
    assert result["case_count"] == 2
    assert result["fail_fast_unattempted_case_count"] == 1
    assert result["provider_attempt_count"] == 1
    assert result["failed_attempt_count"] == 1
    assert result["failure_class_counts"] == [
        {"transport_failure_class": "timeout", "count": 1}
    ]
    assert result["fail_fast_reason_counts"] == [
        {"transport_failure_class": "screening_fail_fast_gate", "count": 1}
    ]
    assert result["source_groups"][0]["failure_class_counts"] == [
        {"transport_failure_class": "timeout", "count": 1}
    ]
    assert result["source_groups"][0]["fail_fast_reason_counts"] == [
        {"transport_failure_class": "screening_fail_fast_gate", "count": 1}
    ]
    assert "DO_NOT_SERIALIZE_THIS_PROVIDER_OUTPUT" not in encoded
    assert "DO_NOT_SERIALIZE_THIS_PROMPT" not in encoded
    assert "DO_NOT_SERIALIZE_THIS_LABEL" not in encoded
    assert result["raw_provider_outputs_persisted"] is False
    assert result["network_calls_performed"] is False


def test_binding_drift_blocks_without_network_or_partial_receipt(tmp_path: Path) -> None:
    plan, state, transport, unit_root = _inputs(tmp_path)
    payload = json.loads(transport.read_text(encoding="utf-8"))
    payload["plan_digest_sha256"] = "drifted"
    _write(transport, payload)

    result = audit.audit_transport(
        plan_path=plan,
        campaign_state_path=state,
        transport_admission_path=transport,
        unit_root=unit_root,
    )

    assert result["status"] == "blocked"
    assert "transport_audit_transport_plan_digest_mismatch" in result["reason_codes"]
    assert result["network_calls_performed"] is False


def test_invalid_telemetry_fails_closed(tmp_path: Path) -> None:
    plan, state, transport, unit_root = _inputs(tmp_path)
    unit_path = unit_root / ("a" * 64 + ".private.json")
    payload = json.loads(unit_path.read_text(encoding="utf-8"))
    payload["case_results"][0]["failure_telemetry"]["failed_attempt_count"] = 2
    _write(unit_path, payload)

    with pytest.raises(audit.AuditInputError, match="failure_attempt_count_invalid"):
        audit.audit_transport(
            plan_path=plan,
            campaign_state_path=state,
            transport_admission_path=transport,
            unit_root=unit_root,
        )


def test_non_unit_private_artifacts_are_not_opened(tmp_path: Path) -> None:
    plan, state, transport, unit_root = _inputs(tmp_path)
    (unit_root / "checkpoint.private.json").write_text(
        "this is not JSON and must not be read", encoding="utf-8"
    )

    result = audit.audit_transport(
        plan_path=plan,
        campaign_state_path=state,
        transport_admission_path=transport,
        unit_root=unit_root,
    )

    assert result["status"] == "ready"
