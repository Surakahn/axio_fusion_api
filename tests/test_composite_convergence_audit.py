import argparse
import json
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_composite_convergence as audit


def _args(tmp_path: Path) -> argparse.Namespace:
    def path(name: str) -> Path:
        value = tmp_path / name
        value.write_text("{}", encoding="utf-8")
        return value

    return argparse.Namespace(
        registry=path("registry.json"),
        plan=path("plan.json"),
        state=path("state.json"),
        transport_admission=None,
        ranking=None,
        provider_baseline_freeze=None,
        harness_pin=None,
        execution_plan=None,
        acquisition_status=None,
        official_import_audit=None,
        target_campaign=None,
        final_audit=None,
        output=tmp_path / "audit.json",
    )


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_running_screening_is_visible_without_claim_admission(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.plan, {"ready": True, "plan_digest_sha256": "plan-digest"})
    _write(
        args.state,
        {
            "status": "running",
            "plan_digest_sha256": "plan-digest",
            "campaign_digest_sha256": "campaign-digest",
        },
    )
    result = audit.audit_cohort(args)
    assert result["status"] == "running"
    assert result["next_gate"] == "screening"
    assert result["target_suite_calls_allowed"] is False
    encoded = json.dumps(result)
    assert str(args.registry) not in encoded


def test_binding_drift_blocks_even_when_state_is_terminal(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.plan, {"ready": True, "plan_digest_sha256": "expected"})
    _write(args.state, {"status": "completed", "plan_digest_sha256": "drifted"})
    result = audit.audit_cohort(args)
    assert result["status"] == "blocked"
    assert "screening_plan_digest_mismatch" in result["reason_codes"]
    assert result["next_gate"] == "screening"


def test_all_gates_ready_allows_target_calls(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.plan, {"ready": True, "plan_digest_sha256": "plan-digest"})
    _write(
        args.state,
        {
            "status": "completed",
            "ready_for_ranking": True,
            "plan_digest_sha256": "plan-digest",
        },
    )
    args.transport_admission = tmp_path / "transport.json"
    _write(args.transport_admission, {"status": "ready"})
    args.ranking = tmp_path / "ranking.json"
    _write(args.ranking, {"screening_conversion_ready": True})
    args.provider_baseline_freeze = tmp_path / "freeze.json"
    _write(args.provider_baseline_freeze, {"final_claim_freeze_ready": True})
    args.harness_pin = tmp_path / "pin.json"
    _write(
        args.harness_pin,
        {
            "suite_count": 1,
            "ready_suite_count": 1,
            "blocked_suite_count": 0,
            "raw_local_paths_persisted": False,
            "raw_prompts_persisted": False,
            "raw_labels_persisted": False,
        },
    )
    args.execution_plan = tmp_path / "execution.json"
    _write(
        args.execution_plan,
        {
            "status": "ready_to_execute",
            "all_tasks_ready_to_execute": True,
            "all_required_outputs_are_hash_only_import_sources": True,
        },
    )
    args.acquisition_status = tmp_path / "acquisition.json"
    _write(
        args.acquisition_status,
        {
            "ready_to_assemble_manifest": True,
            "official_import_missing_count": 0,
            "ready_suite_count": 1,
            "required_suite_count": 1,
        },
    )
    args.official_import_audit = tmp_path / "import.json"
    _write(
        args.official_import_audit,
        {
            "ready_for_campaign_import_stage": True,
            "blocked_official_suite_count": 0,
            "ready_official_suite_count": 1,
            "official_suite_count": 1,
        },
    )
    args.target_campaign = tmp_path / "campaign.json"
    _write(args.target_campaign, {"final_claims_allowed": True})
    args.final_audit = tmp_path / "final.json"
    _write(args.final_audit, {"completion_ready": True})
    result = audit.audit_cohort(args)
    assert result["status"] == "ready"
    assert result["next_gate"] == "complete"
    assert result["target_suite_calls_allowed"] is True
    assert result["final_claim_allowed"] is True


def test_pre_target_gates_authorize_campaign_but_not_final_claim(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.plan, {"ready": True, "plan_digest_sha256": "plan-digest"})
    _write(args.state, {"status": "completed", "ready_for_ranking": True, "plan_digest_sha256": "plan-digest"})
    args.transport_admission = tmp_path / "transport.json"
    _write(args.transport_admission, {"status": "ready"})
    args.ranking = tmp_path / "ranking.json"
    _write(args.ranking, {"screening_conversion_ready": True})
    args.provider_baseline_freeze = tmp_path / "freeze.json"
    _write(args.provider_baseline_freeze, {"final_claim_freeze_ready": True})
    args.harness_pin = tmp_path / "pin.json"
    _write(args.harness_pin, {"suite_count": 1, "ready_suite_count": 1, "blocked_suite_count": 0, "raw_local_paths_persisted": False, "raw_prompts_persisted": False, "raw_labels_persisted": False})
    args.execution_plan = tmp_path / "execution.json"
    _write(args.execution_plan, {"status": "ready_to_execute", "all_tasks_ready_to_execute": True, "all_required_outputs_are_hash_only_import_sources": True})
    args.acquisition_status = tmp_path / "acquisition.json"
    _write(args.acquisition_status, {"ready_to_assemble_manifest": True, "official_import_missing_count": 0, "ready_suite_count": 1, "required_suite_count": 1})
    args.official_import_audit = tmp_path / "import.json"
    _write(args.official_import_audit, {"ready_for_campaign_import_stage": True, "blocked_official_suite_count": 0, "ready_official_suite_count": 1, "official_suite_count": 1})
    result = audit.audit_cohort(args)
    assert result["status"] == "ready_for_target_campaign"
    assert result["next_gate"] == "target_campaign"
    assert result["target_suite_calls_allowed"] is True
    assert result["final_claim_allowed"] is False
