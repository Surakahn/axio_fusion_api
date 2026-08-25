from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_composite_harness_binding as binding


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _inputs(tmp_path: Path) -> argparse.Namespace:
    registry = tmp_path / "registry.json"
    _write(registry, {})
    plan = tmp_path / "plan.json"
    _write(
        plan,
        {
            "schema": binding.SCREENING_PLAN_SCHEMA,
            "ready": True,
            "plan_digest_sha256": "plan-digest",
            "registry_file_sha256": binding._sha256_file(registry),
        },
    )
    state = tmp_path / "state.json"
    _write(
        state,
        {
            "schema": binding.SCREENING_STATE_SCHEMA,
            "status": "completed",
            "ready_for_ranking": True,
            "target_suite_calls_performed": False,
            "plan_digest_sha256": "plan-digest",
            "plan_file_content_sha256": binding._sha256_file(plan),
            "registry_file_sha256": binding._sha256_file(registry),
            "campaign_digest_sha256": "c" * 64,
        },
    )
    transport = tmp_path / "transport.json"
    _write(
        transport,
        {
            "schema": binding.TRANSPORT_SCHEMA,
            "status": "ready",
            "source_plan_file_sha256": binding._sha256_file(plan),
            "source_campaign_state_file_sha256": binding._sha256_file(state),
            "registry_file_sha256": binding._sha256_file(registry),
            "plan_digest_sha256": "plan-digest",
            "campaign_digest_sha256": "c" * 64,
            "selection_basis": "transport_failure_rate_only",
            "quality_fields_used_for_selection": [],
        },
    )
    ranking = tmp_path / "ranking.json"
    _write(
        ranking,
        {
            "schema": binding.RANKING_SCHEMA,
            "screening_conversion_ready": True,
            "screening_campaign_state_sha256": binding._sha256_file(state),
            "registry_file_sha256": binding._sha256_file(registry),
        },
    )
    freeze = tmp_path / "freeze.json"
    _write(
        freeze,
        {
            "schema": binding.FREEZE_SCHEMA,
            "final_claim_freeze_ready": True,
            "provider_baseline_selection": "externally_ranked_top_three_pre_registered",
            "selected_all_available_provider_baselines": False,
            "selected_provider_baseline_count": 3,
            "required_provider_baseline_count": 3,
            "provider_registry_receipt": {"registry_file_sha256": binding._sha256_file(registry)},
            "external_ranking_receipt": {
                "ready": True,
                "input_content_sha256": binding._sha256_file(ranking),
            },
            "freeze_digest_sha256": "f" * 64,
        },
    )
    pin = tmp_path / "pin.json"
    _write(pin, {"schema": binding.PIN_SCHEMA, "suite_count": 1, "ready_suite_count": 1, "blocked_suite_count": 0, "all_paths_hashed_only": True})
    execution = tmp_path / "execution.json"
    _write(
        execution,
        {
            "schema": binding.EXECUTION_PLAN_SCHEMA,
            "status": "ready_to_execute",
            "execution_authorized": True,
            "matrix_mode": "formal_top_three_cohort",
            "formal_top_three_cohort_complete": True,
            "formal_cohort_binding_reason_codes": [],
            "all_tasks_ready_to_execute": True,
            "all_required_outputs_are_hash_only_import_sources": True,
            "harness_pin_manifest_path_sha256": binding._sha256_text(str(pin)),
            "acquisition_status_path_sha256": "placeholder",
            "provider_baseline_freeze_path_sha256": binding._sha256_text(str(freeze)),
            "provider_baseline_freeze_content_sha256": binding._sha256_file(freeze),
            "execution_plan_digest_sha256": "e" * 64,
        },
    )
    acquisition = tmp_path / "acquisition.json"
    _write(
        acquisition,
        {
            "schema": binding.ACQUISITION_SCHEMA,
            "ready_to_assemble_manifest": True,
            "official_import_missing_count": 0,
            "ready_suite_count": 1,
            "required_suite_count": 1,
        },
    )
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    execution_payload["acquisition_status_path_sha256"] = binding._sha256_text(str(acquisition))
    _write(execution, execution_payload)
    import_audit = tmp_path / "import-audit.json"
    _write(
        import_audit,
        {
            "schema": binding.IMPORT_AUDIT_SCHEMA,
            "ready_for_campaign_import_stage": True,
            "blocked_official_suite_count": 0,
            "ready_official_suite_count": 1,
            "official_suite_count": 1,
            "audit_digest_sha256": "a" * 64,
        },
    )
    return argparse.Namespace(
        registry=registry,
        plan=plan,
        state=state,
        transport_admission=transport,
        ranking=ranking,
        provider_baseline_freeze=freeze,
        harness_pin=pin,
        execution_plan=execution,
        acquisition_status=acquisition,
        official_import_audit=import_audit,
        output=tmp_path / "binding.json",
    )


def test_binding_is_ready_only_for_one_complete_cohort(tmp_path: Path) -> None:
    args = _inputs(tmp_path)
    result = binding.build_binding(args)
    assert result["status"] == "ready"
    assert result["target_suite_calls_allowed"] is True
    encoded = json.dumps(result, sort_keys=True)
    assert str(tmp_path) not in encoded


def test_binding_rejects_ranking_content_drift(tmp_path: Path) -> None:
    args = _inputs(tmp_path)
    args.ranking.write_text("{\"changed\": true}\n", encoding="utf-8")
    result = binding.build_binding(args)
    assert result["status"] == "blocked"
    assert "provider_baseline_freeze_ranking_binding_mismatch" in result["reason_codes"]
