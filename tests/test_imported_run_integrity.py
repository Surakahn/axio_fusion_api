from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.evaluation import (  # noqa: E402
    _decoding_config_sha256_for_suite,
    _imported_run_integrity_receipt,
    _prompt_protocol_sha256_for_suite,
    _validate_imported_runs,
)
from axio_fusion_api.schemas import sha256_text  # noqa: E402


SUITE_ID = "mt_bench_work"
TASK_FORMAT = "external_pairwise_judge"


def _valid_imported_run() -> dict:
    prompt_hash = _prompt_protocol_sha256_for_suite(SUITE_ID, TASK_FORMAT)
    decoding_hash = _decoding_config_sha256_for_suite(SUITE_ID, TASK_FORMAT)
    rows = [
        {"case_id": sha256_text("case-one"), "status": "completed", "provider_call_count": 2},
        {"case_id": sha256_text("case-two"), "status": "completed", "provider_call_count": 1},
    ]
    return {
        "schema": "axio_fusion_api.benchmark_run.v2",
        "suite_id": SUITE_ID,
        "candidate_id": "axio-sol",
        "task_format": TASK_FORMAT,
        "mode": "official_import",
        "case_count": 2,
        "attempted_count": 2,
        "provider_call_count": 3,
        "prompt_protocol_sha256": prompt_hash,
        "decoding_config_sha256": decoding_hash,
        "case_results": rows,
        "harness_receipt": {
            "schema": "axio_fusion_api.harness_receipt.v1",
            "suite_id": SUITE_ID,
            "task_format": TASK_FORMAT,
            "official_harness_required": True,
            "official_or_audited_harness": True,
            "final_claim_eligible": True,
            "harness_name_sha256": sha256_text("harness"),
            "harness_version_sha256": sha256_text("version"),
            "dataset_snapshot_sha256": sha256_text("dataset"),
            "evaluator_config_sha256": sha256_text("evaluator"),
            "prompt_protocol_sha256": prompt_hash,
            "decoding_config_sha256": decoding_hash,
            "position_balanced": True,
        },
    }


def _validate_payload(tmp_path: Path, payload: dict) -> dict:
    path = tmp_path / "imported.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return _validate_imported_runs(
        {"imported_runs": {"axio-sol": str(path)}},
        ["axio-sol"],
        suite_id=SUITE_ID,
        task_format=TASK_FORMAT,
    )


def test_imported_run_integrity_accepts_complete_hash_bound_accounting(tmp_path):
    payload = _valid_imported_run()
    receipt = _imported_run_integrity_receipt(payload, suite_id=SUITE_ID, task_format=TASK_FORMAT)

    assert receipt["valid"] is True
    assert receipt["case_count"] == receipt["case_result_count"] == 2
    assert receipt["attempted_count"] == receipt["completed_case_count"] == 2
    assert receipt["provider_call_count"] == receipt["case_provider_call_count"] == 3
    assert receipt["case_hash_count"] == 2
    assert receipt["duplicate_case_hash_count"] == 0
    assert receipt["harness_prompt_protocol_match"] is True
    assert receipt["harness_decoding_config_match"] is True

    validation = _validate_payload(tmp_path, payload)
    assert validation["valid_import_count"] == 1
    assert validation["invalid_import_count"] == 0
    assert validation["receipts"][0]["integrity"]["valid"] is True


def test_imported_run_integrity_rejects_truncation_duplicates_and_call_mismatch(tmp_path):
    cases = (
        ("case_count", lambda run: run.update(case_count=3), "case_result_count_incomplete"),
        (
            "duplicate_hash",
            lambda run: run["case_results"].__setitem__(1, dict(run["case_results"][0])),
            "duplicate_case_hashes",
        ),
        ("attempted", lambda run: run.update(attempted_count=1), "attempted_count_receipt_mismatch"),
        ("provider_calls", lambda run: run.update(provider_call_count=2), "provider_call_count_receipt_mismatch"),
    )
    for _, mutate, expected_reason in cases:
        payload = copy.deepcopy(_valid_imported_run())
        mutate(payload)
        validation = _validate_payload(tmp_path, payload)
        receipt = validation["receipts"][0]
        assert validation["invalid_import_count"] == 1
        assert expected_reason in receipt["reason_codes"]
        assert receipt["integrity"]["valid"] is False


def test_imported_run_integrity_rejects_prompt_binding_and_unsafe_persistence(tmp_path):
    payload = _valid_imported_run()
    payload["prompt_protocol_sha256"] = sha256_text("forged-prompt")
    payload["raw_provider_outputs_persisted"] = True

    validation = _validate_payload(tmp_path, payload)
    receipt = validation["receipts"][0]
    assert validation["invalid_import_count"] == 1
    assert "prompt_protocol_hash_receipt_mismatch" in receipt["reason_codes"]
    assert "raw_content_persisted" in receipt["reason_codes"]
    serialized = json.dumps(receipt, ensure_ascii=False)
    assert "forged-prompt" not in serialized
    assert receipt["integrity"]["raw_provider_outputs_persisted"] is False


def test_imported_run_integrity_rejects_empty_json_object(tmp_path):
    validation = _validate_payload(tmp_path, {})

    assert validation["invalid_import_count"] == 1
    assert validation["valid_import_count"] == 0
    assert "import_payload_unavailable" in validation["receipts"][0]["reason_codes"]
