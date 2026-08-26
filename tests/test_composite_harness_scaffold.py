from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import prepare_composite_harness as scaffold
from axio_fusion_api.evaluation import BENCHMARK_SUITES, _official_import_harness_pin_summary


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _args(tmp_path: Path) -> argparse.Namespace:
    inputs = {}
    for name, payload in {
        "registry": {"registry": True},
        "plan": {"plan_digest_sha256": "p" * 64, "ready": True},
        "state": {"status": "running", "campaign_digest_sha256": "c" * 64},
        "transport_admission": {},
        "ranking": {},
        "provider_baseline_freeze": {},
    }.items():
        path = tmp_path / f"{name}.json"
        _write(path, payload)
        inputs[name] = path
    return argparse.Namespace(
        **inputs,
        output_dir=tmp_path / "out",
        harness_root=None,
        raw_root=None,
        bfcl_harness_root=None,
        harness_pin_manifest=None,
        dataset_dir=tmp_path / "datasets",
        safe_import_dir=tmp_path / "imports",
        dataset_manifest=None,
        source_manifest=None,
        case_hash_manifest=None,
        min_cases_per_suite=100,
    )


def _stub_payload(schema: str) -> dict:
    return {
        "schema": schema,
        "ready": True,
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def test_scaffold_is_fail_closed_and_never_authorizes_target_calls(tmp_path, monkeypatch) -> None:
    args = _args(tmp_path)
    monkeypatch.setattr(
        scaffold,
        "build_benchmark_acquisition_checklist",
        lambda **_: _stub_payload(scaffold.CHECKLIST_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_benchmark_acquisition_status",
        lambda **_: _stub_payload(scaffold.ACQUISITION_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_benchmark_harness_pin_manifest",
        lambda **_: _stub_payload(scaffold.PIN_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_official_harness_execution_plan",
        lambda **_: _stub_payload(scaffold.EXECUTION_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_official_import_audit",
        lambda **_: _stub_payload(scaffold.IMPORT_AUDIT_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_official_import_batch_template",
        lambda **_: _stub_payload(scaffold.IMPORT_TEMPLATE_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold.cohort_binding,
        "build_binding",
        lambda _args: {
            "schema": "axio_fusion_api.composite_harness_cohort_binding.v1",
            "status": "blocked",
            "reason_codes": ["screening_not_terminal"],
            "cohort_binding_digest_sha256": "b" * 64,
            "target_suite_calls_allowed": False,
        },
    )
    monkeypatch.setattr(
        scaffold.convergence_audit,
        "audit_cohort",
        lambda _args: {
            "schema": "axio_fusion_api.composite_convergence_audit.v1",
            "status": "running",
            "next_gate": "screening",
            "reason_codes": ["screening_not_terminal"],
            "target_suite_calls_allowed": False,
            "final_claim_allowed": False,
        },
    )

    receipt = scaffold.run_scaffold(args)

    assert receipt["status"] == "running"
    assert receipt["next_gate"] == "screening"
    assert receipt["target_suite_calls_allowed"] is False
    assert receipt["target_suite_calls_performed"] is False
    assert all(value is False for key, value in receipt.items() if key.endswith("_persisted"))
    assert str(tmp_path) not in json.dumps(receipt, sort_keys=True)
    assert (args.output_dir / "composite_harness_scaffold.safe.json").is_file()
    assert (args.output_dir / "official_harness_execution_plan.composite.successor.safe.json").is_file()


def test_missing_harness_roots_produce_safe_blocked_pin(tmp_path, monkeypatch) -> None:
    args = _args(tmp_path)
    monkeypatch.setattr(
        scaffold,
        "build_benchmark_acquisition_checklist",
        lambda **_: _stub_payload(scaffold.CHECKLIST_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_benchmark_acquisition_status",
        lambda **_: _stub_payload(scaffold.ACQUISITION_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_official_harness_execution_plan",
        lambda **_: _stub_payload(scaffold.EXECUTION_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_official_import_audit",
        lambda **_: _stub_payload(scaffold.IMPORT_AUDIT_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold,
        "build_official_import_batch_template",
        lambda **_: _stub_payload(scaffold.IMPORT_TEMPLATE_SCHEMA),
    )
    monkeypatch.setattr(
        scaffold.cohort_binding,
        "build_binding",
        lambda _args: {"status": "blocked", "reason_codes": [], "cohort_binding_digest_sha256": "b" * 64},
    )
    monkeypatch.setattr(
        scaffold.convergence_audit,
        "audit_cohort",
        lambda _args: {"status": "blocked", "next_gate": "screening", "reason_codes": []},
    )

    scaffold.run_scaffold(args)
    pin_path = args.output_dir / "harness_pin_manifest.composite.successor.safe.json"
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    assert pin["status"] == "blocked"
    assert "harness_root_and_raw_root_required" in pin["reason_codes"]
    assert pin["secrets_persisted"] is False


def test_execution_stage_is_ready_while_post_execution_imports_are_pending(
    tmp_path: Path,
) -> None:
    path = tmp_path / "execution_plan.safe.json"
    payload = {
        "schema": scaffold.EXECUTION_SCHEMA,
        "status": "ready_to_execute",
        "execution_authorized": True,
        "execution_authorization_scope": "official_or_audited_harness_work_queue_only",
        "target_campaign_authorized": False,
        "all_tasks_ready_to_execute": True,
        "formal_cohort_binding_reason_codes": [],
        "planning_reason_codes": [],
        "post_execution_imports_complete": False,
        "post_execution_reason_codes": ["official_import_acquisition_incomplete"],
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    _write(path, payload)

    snapshot = scaffold._stage_snapshot("execution_plan", path, payload)

    assert snapshot["status"] == "ready"
    assert snapshot["reason_codes"] == []
    assert snapshot["execution_authorized"] is True
    assert snapshot["target_campaign_authorized"] is False
    assert snapshot["post_execution_imports_complete"] is False
    assert snapshot["post_execution_reason_codes"] == [
        "official_import_acquisition_incomplete"
    ]


def test_reusable_harness_pin_requires_complete_hash_only_manifest(tmp_path: Path) -> None:
    pin = {
        "schema": scaffold.PIN_SCHEMA,
        "suite_count": 1,
        "ready_suite_count": 1,
        "blocked_suite_count": 0,
        "suites": [{"suite_id": "fixture", "ready": True}],
        "all_paths_hashed_only": True,
        "raw_local_paths_persisted": False,
        "raw_dataset_content_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    pin.update({field: False for field in scaffold.SENSITIVE_FIELDS})
    source = tmp_path / "verified_pin.json"
    _write(source, pin)

    assert scaffold._load_reusable_harness_pin(source) == pin

    pin["secrets_persisted"] = True
    _write(source, pin)
    blocked = scaffold._load_reusable_harness_pin(source)
    assert blocked["schema"] == scaffold.PIN_SCHEMA
    assert "harness_pin_reuse_secrets_persisted" in blocked["reason_codes"]


def test_blocked_pin_manifest_is_audited_fail_closed(tmp_path: Path) -> None:
    pin_path = tmp_path / "blocked_pin.json"
    _write(
        pin_path,
        {
            "schema": scaffold.PIN_SCHEMA,
            "status": "blocked",
            "reason_codes": ["harness_root_and_raw_root_required"],
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
    )

    result = _official_import_harness_pin_summary(
        harness_pin_manifest_path=pin_path,
        source_manifest_path=None,
        official_suites=[BENCHMARK_SUITES[0]],
    )

    assert result["ready_official_suite_count"] == 0
    assert "harness_pin_suite_missing" in result["suite_rows"][0]["reason_codes"]
