from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SRC = Path(__file__).resolve().parents[1] / "src"
for path in (SCRIPTS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import verify_screening_preflight as verifier


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_inputs(tmp_path: Path) -> argparse.Namespace:
    registry = tmp_path / "registry.json"
    plan = tmp_path / "plan.json"
    source = tmp_path / "source.json"
    admission = tmp_path / "admission.json"
    state = tmp_path / "state.json"
    receipt = tmp_path / "receipt.json"
    credential_state = tmp_path / "credential-state.json"
    credential_receipt = tmp_path / "credential-receipt.json"
    _write(registry, {"schema": "registry"})
    _write(source, {
        "schema": verifier.SOURCE_SCHEMA,
        "contains_api_keys": False,
        "contains_labels": False,
        "secrets_persisted": False,
        "pre_registration": {
            "declared_before_target_campaign": True,
            "target_benchmark_results_used": False,
            "target_suite_results_used": False,
        },
        "scientific_contract": {
            "retry_on_wrong_answer": False,
            "retry_on_low_score": False,
            "retry_on_parseable_answer": False,
            "ranking_uses_target_suite_material": False,
        },
    })
    _write(admission, {
        "schema": verifier.ADMISSION_SCHEMA,
        "status": "ready",
        "mode": "live",
        "target_benchmark_cases_or_labels_used": False,
        "formal_baseline_eligible_count": 3,
        "secrets_persisted": False,
        "raw_provider_outputs_persisted": False,
    })
    plan_payload = {
        "schema": verifier.PLAN_SCHEMA,
        "ready": True,
        "execution_mode": "remote_provider_api_only",
        "max_workers": 1,
        "source_family_count": 2,
        "minimum_independent_source_count": 2,
        "canonical_model_group_count": 3,
        "replica_profile_count": 3,
        "task_count": 2,
        "registry_file_sha256": _sha(registry),
        "source_manifest_content_sha256": _sha(source),
        "operational_admission": {"status": "ready", "formal_baseline_eligible_count": 3},
        "fail_fast_policy": {
            "enabled": True,
            "requires_max_workers": 1,
            "unattempted_cases_are_transport_failures": True,
        },
        "no_cheat_contract": {
            "target_suite_labels_used": False,
            "target_suite_prompts_used": False,
            "target_suite_results_used": False,
            "retry_on_wrong_answer": False,
            "registry_capability_priors_used_for_strength_ranking": False,
        },
        "secrets_persisted": False,
        "raw_provider_outputs_persisted": False,
    }
    plan_payload["plan_digest_sha256"] = hashlib.sha256(b"plan-digest").hexdigest()
    _write(plan, plan_payload)
    plan_sha = _sha(plan)
    state_payload = {
        "schema": verifier.CAMPAIGN_SCHEMA,
        "status": "preflight_ready",
        "mode": "preflight",
        "network_calls_performed": False,
        "target_suite_calls_performed": False,
        "ready_for_ranking": False,
        "planned_task_count": 2,
        "selected_task_count": 2,
        "plan_digest_sha256": plan_payload["plan_digest_sha256"],
        "plan_file_content_sha256": plan_sha,
        "source_manifest_content_sha256": _sha(source),
        "registry_file_sha256": _sha(registry),
        "secrets_persisted": False,
        "raw_provider_outputs_persisted": False,
    }
    credential_readiness = {
        "ready": True,
        "credential_ready_profile_count": 3,
        "required_profile_count": 3,
        "secrets_persisted": False,
        "raw_api_keys_persisted": False,
    }
    credential_payload = dict(state_payload)
    credential_payload["live_credential_readiness"] = credential_readiness
    _write(state, state_payload)
    _write(receipt, state_payload)
    _write(credential_state, credential_payload)
    _write(credential_receipt, credential_payload)
    return argparse.Namespace(
        registry=registry,
        plan=plan,
        source_manifest=source,
        operational_admission=admission,
        preflight_state=state,
        preflight_receipt=receipt,
        credential_preflight_state=credential_state,
        credential_preflight_receipt=credential_receipt,
        pid=None,
        expected_transport="proxy",
        output=tmp_path / "out.json",
    )


def test_ready_preflight_never_means_authorization(monkeypatch, tmp_path: Path) -> None:
    args = _base_inputs(tmp_path)
    monkeypatch.setattr(
        verifier,
        "_network_summary",
        lambda: {
            "mode": "auto",
            "valid": True,
            "listener_detected": True,
            "selected_transport": "proxy",
            "reason_code": "proxy_listener_detected",
            "raw_proxy_url_persisted": False,
            "secrets_persisted": False,
        },
    )
    result = verifier.verify_preflight(args)
    assert result["status"] == "ready_for_operator_authorization"
    assert result["ready_for_operator_authorization"] is True
    assert result["authorization_required"] is True
    assert result["provider_calls_performed"] is False
    assert result["pid"]["status"] == "not_started"


def test_plan_drift_and_transport_mismatch_fail_closed(monkeypatch, tmp_path: Path) -> None:
    args = _base_inputs(tmp_path)
    payload = json.loads(args.plan.read_text(encoding="utf-8"))
    payload["max_workers"] = 2
    _write(args.plan, payload)
    monkeypatch.setattr(
        verifier,
        "_network_summary",
        lambda: {
            "mode": "auto",
            "valid": True,
            "listener_detected": False,
            "selected_transport": "direct",
            "reason_code": "proxy_listener_not_detected",
            "raw_proxy_url_persisted": False,
            "secrets_persisted": False,
        },
    )
    result = verifier.verify_preflight(args)
    assert result["status"] == "blocked"
    assert "plan_contract_invalid" in result["reason_codes"]
    assert "network_transport_mismatch" in result["reason_codes"]


def test_unrelated_pid_is_rejected_without_persisting_command(monkeypatch, tmp_path: Path) -> None:
    args = _base_inputs(tmp_path)
    args.pid = 42
    monkeypatch.setattr(verifier, "_proc_cmdline", lambda _pid: "python unrelated-worker")
    monkeypatch.setattr(
        verifier,
        "_network_summary",
        lambda: {
            "mode": "auto",
            "valid": True,
            "listener_detected": True,
            "selected_transport": "proxy",
            "reason_code": "proxy_listener_detected",
            "raw_proxy_url_persisted": False,
            "secrets_persisted": False,
        },
    )
    result = verifier.verify_preflight(args)
    assert result["status"] == "blocked"
    assert "pid_not_matching" in result["reason_codes"]
    assert "unrelated-worker" not in json.dumps(result)


def test_missing_credential_ready_state_is_an_input_error(tmp_path: Path) -> None:
    args = _base_inputs(tmp_path)
    payload = json.loads(args.credential_preflight_state.read_text(encoding="utf-8"))
    payload["live_credential_readiness"]["ready"] = False
    _write(args.credential_preflight_state, payload)
    result = verifier.verify_preflight(args)
    assert result["status"] == "blocked"
    assert "credential_preflight_not_ready" in result["reason_codes"]


def test_malformed_numeric_plan_fails_closed(tmp_path: Path) -> None:
    args = _base_inputs(tmp_path)
    payload = json.loads(args.plan.read_text(encoding="utf-8"))
    payload["source_family_count"] = "two"
    _write(args.plan, payload)
    result = verifier.verify_preflight(args)
    assert result["status"] == "blocked"
    assert "plan_contract_invalid" in result["reason_codes"]
