from __future__ import annotations

import json
from pathlib import Path

from axio_fusion_api.evaluation import (
    _axio_run_unit,
    _benchmark_run_resume_validation,
    _campaign_progress_run_status,
    _decoding_config_sha256_for_suite,
    _expected_benchmark_case_hashes,
    _prompt_protocol_sha256_for_suite,
    run_benchmark_dataset,
)


def _write_exact_dataset(path: Path) -> list[dict[str, str]]:
    rows = [
        {"prompt": "case one", "answer": "1"},
        {"prompt": "case two", "answer": "2"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return rows


def _complete_run(dataset_path: Path) -> tuple[dict, dict, set[str]]:
    expected_hashes, expected_count = _expected_benchmark_case_hashes(
        dataset_path,
        suite_id="math_500",
        task_format="exact_match",
        limit=None,
    )
    assert expected_hashes is not None
    assert expected_count == 2
    rows = [
        {
            "case_id": case_hash,
            "status": "completed",
            "provider_call_count": 2,
        }
        for case_hash in sorted(expected_hashes)
    ]
    payload = {
        "schema": "axio_fusion_api.benchmark_run.v2",
        "suite_id": "math_500",
        "candidate_id": "axio-luna",
        "api_format": "chat/completions",
        "api_surface_id": "axio-luna@chat_completions",
        "task_format": "exact_match",
        "prompt_protocol_sha256": _prompt_protocol_sha256_for_suite("math_500", "exact_match"),
        "decoding_config_sha256": _decoding_config_sha256_for_suite("math_500", "exact_match"),
        "mode": "live",
        "case_count": 2,
        "attempted_count": 2,
        "provider_call_count": 4,
        "case_results": rows,
    }
    return payload, _axio_run_unit("axio-luna", "chat/completions"), expected_hashes


def test_resume_requires_complete_case_set_and_provider_call_receipt(tmp_path):
    dataset_path = tmp_path / "math.jsonl"
    _write_exact_dataset(dataset_path)
    payload, unit, expected_hashes = _complete_run(dataset_path)

    valid = _benchmark_run_resume_validation(
        payload,
        suite_id="math_500",
        unit=unit,
        task_format="exact_match",
        live=True,
        expected_case_count=2,
        expected_case_hashes=expected_hashes,
    )
    assert valid["valid"] is True
    assert valid["status"] == "ready"

    partial = dict(payload)
    partial["case_results"] = list(payload["case_results"][:1])
    partial["case_count"] = 2
    result = _benchmark_run_resume_validation(
        partial,
        suite_id="math_500",
        unit=unit,
        task_format="exact_match",
        live=True,
        expected_case_count=2,
        expected_case_hashes=expected_hashes,
    )
    assert result["valid"] is False
    assert "case_result_count_incomplete" in result["reason_codes"]
    assert "case_hash_set_mismatch" in result["reason_codes"]

    bad_calls = dict(payload)
    bad_calls["provider_call_count"] = 3
    result = _benchmark_run_resume_validation(
        bad_calls,
        suite_id="math_500",
        unit=unit,
        task_format="exact_match",
        live=True,
        expected_case_count=2,
        expected_case_hashes=expected_hashes,
    )
    assert result["valid"] is False
    assert "provider_call_count_receipt_mismatch" in result["reason_codes"]


def test_progress_plan_reports_schema_and_receipt_repair_without_raw_payload(tmp_path):
    dataset_path = tmp_path / "math.jsonl"
    _write_exact_dataset(dataset_path)
    payload, unit, _ = _complete_run(dataset_path)
    payload["schema"] = "untrusted.partial.schema"
    payload["debug_secret"] = "SHOULD_NOT_BE_RETURNED"
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(payload), encoding="utf-8")
    expected_hashes, expected_count = _expected_benchmark_case_hashes(
        dataset_path,
        suite_id="math_500",
        task_format="exact_match",
        limit=None,
    )

    status, receipt = _campaign_progress_run_status(
        run_path,
        suite_id="math_500",
        unit=unit,
        min_cases_per_suite=1,
        expected_case_count=expected_count,
        expected_case_hashes=expected_hashes,
        task_format="exact_match",
    )
    assert status == "invalid"
    assert receipt["repair_required"] is True
    assert "run_artifact_schema_unrecognized" in receipt["reason_codes"]
    assert "SHOULD_NOT_BE_RETURNED" not in json.dumps(receipt)
    assert receipt["raw_run_payload_persisted"] is False


def test_resume_validation_rejects_unknown_schema_before_calling_provider(tmp_path):
    dataset_path = tmp_path / "math.jsonl"
    _write_exact_dataset(dataset_path)
    payload, unit, expected_hashes = _complete_run(dataset_path)
    payload["schema"] = ""
    payload["case_results"] = []
    result = _benchmark_run_resume_validation(
        payload,
        suite_id="math_500",
        unit=unit,
        task_format="exact_match",
        live=True,
        expected_case_count=2,
        expected_case_hashes=expected_hashes,
    )
    assert result["valid"] is False
    assert result["status"] == "repair_required"
    assert "run_artifact_schema_unrecognized" in result["reason_codes"]
    assert "case_result_count_incomplete" in result["reason_codes"]


def test_generic_run_case_hashes_bind_to_suite_id(tmp_path):
    dataset_path = tmp_path / "math.jsonl"
    _write_exact_dataset(dataset_path)
    run = run_benchmark_dataset(
        suite_id="math_500",
        dataset_path=dataset_path,
        candidate_id="axio-luna",
        task_format="exact_match",
        live=False,
    )
    expected_hashes, expected_count = _expected_benchmark_case_hashes(
        dataset_path,
        suite_id="math_500",
        task_format="exact_match",
        limit=None,
    )
    observed_hashes = {row["case_id"] for row in run["case_results"]}
    assert expected_count == run["case_count"] == 2
    assert observed_hashes == expected_hashes
