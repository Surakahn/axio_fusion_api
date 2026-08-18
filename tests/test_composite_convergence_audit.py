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
        cohort_binding=None,
        target_campaign=None,
        final_audit=None,
        output=tmp_path / "audit.json",
    )


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_binding(args: argparse.Namespace, tmp_path: Path) -> None:
    names = (
        "registry",
        "plan",
        "state",
        "transport_admission",
        "ranking",
        "provider_baseline_freeze",
        "harness_pin",
        "execution_plan",
        "acquisition_status",
        "official_import_audit",
    )
    bindings = {
        name: {
            "content_sha256": audit._sha256_file(getattr(args, name)),
            "path_sha256": audit._sha256_text(str(getattr(args, name))),
        }
        for name in names
    }
    declarations = {
        "screening_plan_digest_sha256": json.loads(args.plan.read_text(encoding="utf-8")).get("plan_digest_sha256", ""),
        "screening_campaign_digest_sha256": json.loads(args.state.read_text(encoding="utf-8")).get("campaign_digest_sha256", ""),
        "provider_baseline_freeze_digest_sha256": json.loads(args.provider_baseline_freeze.read_text(encoding="utf-8")).get("freeze_digest_sha256", ""),
        "execution_plan_digest_sha256": json.loads(args.execution_plan.read_text(encoding="utf-8")).get("execution_plan_digest_sha256", ""),
        "official_import_audit_digest_sha256": json.loads(args.official_import_audit.read_text(encoding="utf-8")).get("audit_digest_sha256", ""),
        "target_suite_calls_performed": False,
    }
    digest_input = {"stage_content_sha256": {name: row["content_sha256"] for name, row in bindings.items()}, "declarations": declarations}
    digest_input["schema"] = "test"
    binding = {
        "schema": "axio_fusion_api.composite_harness_cohort_binding.v1",
        "status": "ready",
        "cohort_binding_digest_sha256": audit._sha256_text(audit._stable_json(digest_input)),
        "cohort_id_sha256": audit._sha256_text(audit._stable_json(digest_input)),
        "stage_bindings": bindings,
        "declarations": declarations,
        "binding_digest_input": digest_input,
        "target_suite_calls_allowed": True,
        "target_suite_calls_performed": False,
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }
    args.cohort_binding = tmp_path / "cohort-binding.json"
    _write(args.cohort_binding, binding)


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


def test_missing_screening_state_does_not_imply_target_calls(tmp_path: Path) -> None:
    args = _args(tmp_path)
    args.state.unlink()

    result = audit.audit_cohort(args)

    assert result["status"] == "blocked"
    assert result["target_suite_calls_allowed"] is False
    assert "artifact_missing" in result["reason_codes"]
    assert "screening_target_suite_calls_present" not in result["reason_codes"]


def test_missing_binding_inputs_fail_closed_without_exception(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.plan, {"ready": True, "plan_digest_sha256": "plan-digest"})
    _write(
        args.state,
        {
            "status": "completed",
            "ready_for_ranking": False,
            "plan_digest_sha256": "plan-digest",
            "campaign_digest_sha256": "campaign-digest",
            "target_suite_calls_performed": False,
        },
    )
    args.cohort_binding = tmp_path / "cohort-binding.json"
    _write(args.cohort_binding, {"status": "blocked"})
    result = audit.audit_cohort(args)
    assert result["status"] == "blocked"
    assert "cohort_binding_not_ready" in result["reason_codes"]


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
            "target_suite_calls_performed": False,
        },
    )
    args.transport_admission = tmp_path / "transport.json"
    _write(args.transport_admission, {"status": "ready"})
    args.ranking = tmp_path / "ranking.json"
    _write(args.ranking, {"screening_conversion_ready": True})
    args.provider_baseline_freeze = tmp_path / "freeze.json"
    _write(
        args.provider_baseline_freeze,
        {
            "schema": "axio_fusion_api.provider_baseline_freeze_manifest.v1",
            "final_claim_freeze_ready": True,
            "provider_baseline_selection": "externally_ranked_top_three_pre_registered",
            "selected_all_available_provider_baselines": False,
            "selected_provider_baseline_count": 3,
            "required_provider_baseline_count": 3,
            "external_ranking_receipt": {"ready": True, "pre_registered_before_campaign": True},
            "provider_registry_receipt": {"registry_file_sha256": audit._sha256_file(args.registry)},
            "raw_provider_outputs_persisted": False,
            "raw_provider_urls_persisted": False,
            "secrets_persisted": False,
        },
    )
    args.harness_pin = tmp_path / "pin.json"
    _write(
        args.harness_pin,
        {
            "suite_count": 1,
            "ready_suite_count": 1,
            "blocked_suite_count": 0,
            "raw_local_paths_persisted": False,
            "all_paths_hashed_only": True,
            "raw_dataset_content_persisted": False,
            "raw_prompts_persisted": False,
            "raw_labels_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
    )
    args.execution_plan = tmp_path / "execution.json"
    _write(
        args.execution_plan,
        {
            "status": "ready_to_execute",
            "all_tasks_ready_to_execute": True,
            "all_required_outputs_are_hash_only_import_sources": True,
            "secrets_persisted": False,
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
            "secrets_persisted": False,
            "raw_provider_outputs_persisted": False,
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
            "secrets_persisted": False,
            "raw_provider_outputs_persisted": False,
        },
    )
    _write_ready_binding(args, tmp_path)
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
    _write(args.state, {"status": "completed", "ready_for_ranking": True, "plan_digest_sha256": "plan-digest", "target_suite_calls_performed": False})
    args.transport_admission = tmp_path / "transport.json"
    _write(args.transport_admission, {"status": "ready"})
    args.ranking = tmp_path / "ranking.json"
    _write(args.ranking, {"screening_conversion_ready": True})
    args.provider_baseline_freeze = tmp_path / "freeze.json"
    _write(
        args.provider_baseline_freeze,
        {
            "schema": "axio_fusion_api.provider_baseline_freeze_manifest.v1",
            "final_claim_freeze_ready": True,
            "provider_baseline_selection": "externally_ranked_top_three_pre_registered",
            "selected_all_available_provider_baselines": False,
            "selected_provider_baseline_count": 3,
            "required_provider_baseline_count": 3,
            "external_ranking_receipt": {"ready": True, "pre_registered_before_campaign": True},
            "provider_registry_receipt": {"registry_file_sha256": audit._sha256_file(args.registry)},
            "raw_provider_outputs_persisted": False,
            "raw_provider_urls_persisted": False,
            "secrets_persisted": False,
        },
    )
    args.harness_pin = tmp_path / "pin.json"
    _write(args.harness_pin, {"suite_count": 1, "ready_suite_count": 1, "blocked_suite_count": 0, "raw_local_paths_persisted": False, "all_paths_hashed_only": True, "raw_dataset_content_persisted": False, "raw_prompts_persisted": False, "raw_labels_persisted": False, "raw_provider_outputs_persisted": False, "secrets_persisted": False})
    args.execution_plan = tmp_path / "execution.json"
    _write(args.execution_plan, {"status": "ready_to_execute", "all_tasks_ready_to_execute": True, "all_required_outputs_are_hash_only_import_sources": True, "secrets_persisted": False})
    args.acquisition_status = tmp_path / "acquisition.json"
    _write(args.acquisition_status, {"ready_to_assemble_manifest": True, "official_import_missing_count": 0, "ready_suite_count": 1, "required_suite_count": 1, "secrets_persisted": False, "raw_provider_outputs_persisted": False})
    args.official_import_audit = tmp_path / "import.json"
    _write(args.official_import_audit, {"ready_for_campaign_import_stage": True, "blocked_official_suite_count": 0, "ready_official_suite_count": 1, "official_suite_count": 1, "secrets_persisted": False, "raw_provider_outputs_persisted": False})
    _write_ready_binding(args, tmp_path)
    result = audit.audit_cohort(args)
    assert result["status"] == "ready_for_target_campaign"
    assert result["next_gate"] == "target_campaign"
    assert result["target_suite_calls_allowed"] is True
    assert result["final_claim_allowed"] is False


def test_prior_target_calls_close_every_claim_gate(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.plan, {"ready": True, "plan_digest_sha256": "plan-digest"})
    _write(
        args.state,
        {
            "status": "completed",
            "ready_for_ranking": True,
            "plan_digest_sha256": "plan-digest",
            "target_suite_calls_performed": True,
        },
    )
    result = audit.audit_cohort(args)
    assert result["status"] == "blocked"
    assert result["target_suite_calls_allowed"] is False
    assert result["final_claim_allowed"] is False
    assert "screening_target_suite_calls_present" in result["reason_codes"]
