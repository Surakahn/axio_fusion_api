from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import axio_fusion_api.evaluation as evaluation_module
from axio_fusion_api.benchmark_replacements import (
    MMLU_PRO_CATEGORY_ORDER,
    MMLU_PRO_SCREENING_DISJOINT_VERSION,
    BenchmarkReplacementError,
    build_mmlu_pro_screening_exclusion_manifest,
    build_mmlu_pro_stem_replacement,
)
from axio_fusion_api.evaluation import (
    _campaign_suite_specs,
    audit_benchmark_campaign_readiness,
    build_benchmark_case_hash_manifest,
    build_benchmark_dataset_manifest_template,
    build_benchmark_source_manifest_template,
    validate_benchmark_dataset,
)


def _write_parquet(path: Path, *, answer_offset: int = 0) -> str:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    rows = []
    for category_index, category in enumerate(MMLU_PRO_CATEGORY_ORDER):
        for row_index in range(4):
            options = [
                f"{category}-{row_index}-option-{option_index}"
                for option_index in range(4 if row_index == 0 else 10)
            ]
            answer_index = (category_index + row_index + answer_offset) % len(options)
            rows.append(
                {
                    "question_id": category_index * 100 + row_index,
                    "question": f"Public {category} question {row_index}",
                    "options": options,
                    "answer": chr(ord("A") + answer_index),
                    "answer_index": answer_index,
                    "category": category,
                    "src": f"ori_mmlu-{category}",
                }
            )
    table = pyarrow.Table.from_pylist(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_table(table, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _write_base_manifest(path: Path) -> None:
    payload = build_benchmark_dataset_manifest_template(
        base_dir=str(path.parent / "datasets"),
        min_cases_per_suite=4,
    )
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_screening_source_manifest(
    path: Path,
    *,
    raw: Path,
    validation: Path,
    seed: str = "synthetic-screening-seed",
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.non_target_screening_source_manifest.v1",
                "pre_registration": {"selection_seed": seed},
                "sources": [
                    {
                        "source_id": "synthetic_mmlu_pro_non_target_screening",
                        "adapter": "mmlu_pro",
                        "dataset_path": str(raw),
                        "validation_path": str(validation),
                        "selection": {
                            "strategy": "stratified_sha256_order",
                            "max_per_stratum": 1,
                            "max_cases": 6,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_disjoint_replacement(
    tmp_path: Path,
    *,
    stem: str,
    answer_offset: int = 0,
) -> tuple[dict, Path, Path, dict]:
    raw = tmp_path / f"{stem}.test.parquet"
    validation = tmp_path / f"{stem}.validation.parquet"
    digest = _write_parquet(raw, answer_offset=answer_offset)
    _write_parquet(validation, answer_offset=answer_offset)
    screening_manifest = tmp_path / f"{stem}.screening.private.json"
    _write_screening_source_manifest(
        screening_manifest,
        raw=raw,
        validation=validation,
    )
    exclusion_path = tmp_path / f"{stem}.exclusion.private.json"
    exclusion_safe_path = tmp_path / f"{stem}.exclusion.safe.json"
    exclusion_safe = build_mmlu_pro_screening_exclusion_manifest(
        screening_source_manifest_path=screening_manifest,
        output_path=exclusion_path,
        safe_receipt_path=exclusion_safe_path,
    )
    base_manifest = tmp_path / f"{stem}.base.json"
    _write_base_manifest(base_manifest)
    dataset = tmp_path / f"{stem}.jsonl"
    replacement_manifest = tmp_path / f"{stem}.replacement_manifest.json"
    receipt = build_mmlu_pro_stem_replacement(
        raw_parquet_path=raw,
        standardized_dataset_path=dataset,
        base_dataset_manifest_path=base_manifest,
        replacement_dataset_manifest_path=replacement_manifest,
        per_category=2,
        expected_raw_sha256=digest,
        screening_exclusion_manifest_path=exclusion_path,
    )
    return receipt, dataset, replacement_manifest, exclusion_safe


def test_mmlu_pro_v1_replacement_remains_diagnostic_not_formal_ready(tmp_path: Path) -> None:
    raw = tmp_path / "test.parquet"
    digest = _write_parquet(raw)
    base_manifest = tmp_path / "base_manifest.json"
    _write_base_manifest(base_manifest)
    dataset = tmp_path / "mmlu_pro_stem.jsonl"
    replacement_manifest = tmp_path / "replacement_manifest.json"
    receipt_path = tmp_path / "replacement.safe.json"

    receipt = build_mmlu_pro_stem_replacement(
        raw_parquet_path=raw,
        standardized_dataset_path=dataset,
        receipt_path=receipt_path,
        base_dataset_manifest_path=base_manifest,
        replacement_dataset_manifest_path=replacement_manifest,
        per_category=3,
        expected_raw_sha256=digest,
    )

    assert receipt["status"] == "ready"
    assert receipt["explicitly_not_gpqa"] is True
    assert receipt["selection"]["gold_answers_used_for_selection"] is False
    assert receipt["selection"]["selected_case_count"] == 18
    assert receipt["standardized_dataset"]["file_sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()

    validation = validate_benchmark_dataset(
        suite_id="gpqa_diamond",
        dataset_path=dataset,
        task_format="multiple_choice",
    )
    assert validation["ready_for_scoring"] is True
    assert validation["valid_case_count"] == 18

    manifest = json.loads(replacement_manifest.read_text(encoding="utf-8"))
    replacement_row = next(row for row in manifest["suites"] if row["suite_id"] == "mmlu_pro_stem")
    assert manifest["suite_count"] == 21
    assert replacement_row["replaces_suite_id"] == "gpqa_diamond"
    assert replacement_row["explicitly_not_gpqa"] is True
    assert manifest["benchmark_replacement_policy"]["final_reports_must_show_replacement_identity"] is True

    normalized = _campaign_suite_specs(manifest)
    rejected = next(row for row in normalized if row["suite_id"] == "mmlu_pro_stem")
    assert rejected["_replacement_invalid_reason"] == "replacement_screening_disjointness_unverified"
    readiness = audit_benchmark_campaign_readiness(
        dataset_manifest_path=replacement_manifest,
        candidate_ids=["axio-pro"],
        include_provider_baselines=False,
        min_cases_per_suite=1,
    )
    gpqa_row = next(row for row in readiness["rows"] if row["suite_id"] == "gpqa_diamond")
    assert "replacement_screening_disjointness_unverified" in gpqa_row["reason_codes"]

    first_ids = [json.loads(line)["id"] for line in dataset.read_text(encoding="utf-8").splitlines()]
    second_dataset = tmp_path / "mmlu_pro_stem.second.jsonl"
    second_receipt = build_mmlu_pro_stem_replacement(
        raw_parquet_path=raw,
        standardized_dataset_path=second_dataset,
        per_category=3,
        expected_raw_sha256=digest,
    )
    second_ids = [json.loads(line)["id"] for line in second_dataset.read_text(encoding="utf-8").splitlines()]
    assert first_ids == second_ids
    assert second_receipt["standardized_dataset"]["file_sha256"] == receipt["standardized_dataset"]["file_sha256"]


def test_mmlu_pro_screening_disjoint_replacement_is_normalized_and_receipt_bound(
    tmp_path: Path,
) -> None:
    receipt, dataset, replacement_manifest, exclusion_safe = _build_disjoint_replacement(
        tmp_path,
        stem="disjoint",
    )

    proof = receipt["selection"]["screening_case_disjointness"]
    assert receipt["replacement_version"] == MMLU_PRO_SCREENING_DISJOINT_VERSION
    assert proof["status"] == "verified"
    assert proof["enforced"] is True
    assert proof["selected_overlap_count"] == 0
    assert proof["gold_answers_used_for_exclusion"] is False
    assert proof["raw_case_ids_persisted"] is False
    assert exclusion_safe["excluded_source_row_identity_count"] == 6
    assert "mmlu_pro_source_row_identities" not in exclusion_safe

    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 12
    assert all("source_question_id" not in row for row in rows)

    manifest = json.loads(replacement_manifest.read_text(encoding="utf-8"))
    normalized = _campaign_suite_specs(manifest)
    gpqa_slot = next(row for row in normalized if row["suite_id"] == "gpqa_diamond")
    assert gpqa_slot["replacement_active"] is True
    assert gpqa_slot["benchmark_dataset_id"] == "mmlu_pro_stem"
    assert gpqa_slot["replacement_receipt"]["screening_case_disjointness"]["selected_overlap_count"] == 0


def test_explicit_replacement_full_slice_lowers_only_its_case_gate(tmp_path: Path) -> None:
    _receipt, dataset, replacement_manifest, _exclusion_safe = _build_disjoint_replacement(
        tmp_path,
        stem="fixed-slice-gate",
    )

    case_manifest = build_benchmark_case_hash_manifest(
        dataset_manifest_path=replacement_manifest,
        min_cases_per_suite=100,
    )
    gpqa_row = next(row for row in case_manifest["suite_rows"] if row["suite_id"] == "gpqa_diamond")
    replacement_spec = next(
        row for row in _campaign_suite_specs(json.loads(replacement_manifest.read_text(encoding="utf-8")))
        if row["suite_id"] == "gpqa_diamond"
    )
    declared_min_cases = replacement_spec["min_cases"]
    assert gpqa_row["case_hash_count"] == 12
    assert gpqa_row["ready"] is True
    assert gpqa_row["effective_min_cases"] == declared_min_cases
    assert gpqa_row["suite_min_case_policy"]["suite_override_applied"] is True
    assert gpqa_row["suite_min_case_policy"]["suite_override_value"] == declared_min_cases

    source_template = build_benchmark_source_manifest_template(
        base_dir=str(tmp_path / "datasets"),
        dataset_manifest_path=replacement_manifest,
        min_cases_per_suite=100,
    )
    gpqa_source = next(row for row in source_template["suites"] if row["suite_id"] == "gpqa_diamond")
    assert gpqa_source["replacement_active"] is True
    assert gpqa_source["min_cases"] == declared_min_cases
    assert gpqa_source["suite_min_case_policy"]["effective_min_cases"] == declared_min_cases


def test_acquisition_status_uses_replacement_manifest_dataset_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _receipt, dataset, replacement_manifest, _exclusion_safe = _build_disjoint_replacement(
        tmp_path,
        stem="acquisition-manifest-aware",
    )

    monkeypatch.setattr(evaluation_module, "load_registry", lambda _path: [])
    monkeypatch.setattr(
        evaluation_module,
        "build_benchmark_run_matrix",
        lambda **_kwargs: {
            "candidates": [],
            "provider_baseline_selection": "none",
            "available_provider_baseline_count": 0,
        },
    )
    monkeypatch.setattr(
        evaluation_module,
        "validate_benchmark_dataset",
        lambda **kwargs: {
            "dataset_exists": True,
            "valid_case_count": 12 if Path(kwargs["dataset_path"]) == dataset else 100,
            "row_count": 12 if Path(kwargs["dataset_path"]) == dataset else 100,
            "ready_for_scoring": True,
            "invalid_case_count": 0,
            "duplicate_case_hash_count": 0,
            "label_leakage_suspected_count": 0,
            "prompt_contract_violation_count": 0,
        },
    )

    status = evaluation_module.build_benchmark_acquisition_status(
        dataset_dir=tmp_path / "legacy-dataset-dir-must-not-be-used",
        dataset_manifest_path=replacement_manifest,
        include_provider_baselines=False,
        min_cases_per_suite=100,
    )
    gpqa_row = next(row for row in status["suite_rows"] if row["suite_id"] == "gpqa_diamond")
    assert gpqa_row["ready"] is True
    assert gpqa_row["effective_min_cases"] == 4
    assert gpqa_row["dataset_exists"] is True
    assert status["ready_local_dataset_suite_count"] == status["local_dataset_suite_count"]


def test_mmlu_pro_screening_disjoint_dataset_hash_tampering_blocks_readiness(
    tmp_path: Path,
) -> None:
    _receipt, dataset, replacement_manifest, _exclusion_safe = _build_disjoint_replacement(
        tmp_path,
        stem="dataset-hash-tamper",
    )
    rows = dataset.read_text(encoding="utf-8").splitlines()
    first = json.loads(rows[0])
    first["question"] = f"{first['question']} altered"
    rows[0] = json.dumps(first)
    dataset.write_text("\n".join(rows) + "\n", encoding="utf-8")

    readiness = audit_benchmark_campaign_readiness(
        dataset_manifest_path=replacement_manifest,
        candidate_ids=["axio-pro"],
        include_provider_baselines=False,
        min_cases_per_suite=1,
    )
    gpqa_row = next(row for row in readiness["rows"] if row["suite_id"] == "gpqa_diamond")
    assert "replacement_dataset_receipt_hash_mismatch" in gpqa_row["reason_codes"]


def test_mmlu_pro_screening_disjoint_selection_is_label_blind(tmp_path: Path) -> None:
    first, first_dataset, _first_manifest, first_safe = _build_disjoint_replacement(
        tmp_path,
        stem="first",
        answer_offset=0,
    )
    second, second_dataset, _second_manifest, second_safe = _build_disjoint_replacement(
        tmp_path,
        stem="second",
        answer_offset=1,
    )
    first_rows = [json.loads(line) for line in first_dataset.read_text(encoding="utf-8").splitlines()]
    second_rows = [json.loads(line) for line in second_dataset.read_text(encoding="utf-8").splitlines()]

    assert [row["id"] for row in first_rows] == [row["id"] for row in second_rows]
    assert [row["question"] for row in first_rows] == [row["question"] for row in second_rows]
    assert first_safe["excluded_source_row_identity_set_sha256"] == second_safe["excluded_source_row_identity_set_sha256"]
    assert first["selection"]["screening_case_disjointness"]["gold_answers_used_for_exclusion"] is False
    assert second["selection"]["screening_case_disjointness"]["gold_answers_used_for_exclusion"] is False


def test_mmlu_pro_screening_exclusion_manifest_tampering_fails_closed(tmp_path: Path) -> None:
    raw = tmp_path / "test.parquet"
    validation = tmp_path / "validation.parquet"
    digest = _write_parquet(raw)
    _write_parquet(validation)
    source_manifest = tmp_path / "screening.private.json"
    _write_screening_source_manifest(source_manifest, raw=raw, validation=validation)
    exclusion = tmp_path / "exclusion.private.json"
    build_mmlu_pro_screening_exclusion_manifest(
        screening_source_manifest_path=source_manifest,
        output_path=exclusion,
    )
    tampered = json.loads(exclusion.read_text(encoding="utf-8"))
    tampered["mmlu_pro_source_row_identities"] = ["tampered"]
    exclusion.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(BenchmarkReplacementError) as raised:
        build_mmlu_pro_stem_replacement(
            raw_parquet_path=raw,
            standardized_dataset_path=tmp_path / "output.jsonl",
            per_category=2,
            expected_raw_sha256=digest,
            screening_exclusion_manifest_path=exclusion,
        )
    assert raised.value.reason_code == "screening_exclusion_manifest_source_row_identity_digest_mismatch"


def test_mmlu_pro_screening_exclusion_rejects_source_snapshot_mismatch(tmp_path: Path) -> None:
    first_raw = tmp_path / "first.parquet"
    second_raw = tmp_path / "second.parquet"
    validation = tmp_path / "validation.parquet"
    _write_parquet(first_raw, answer_offset=0)
    second_digest = _write_parquet(second_raw, answer_offset=1)
    _write_parquet(validation)
    source_manifest = tmp_path / "screening.private.json"
    _write_screening_source_manifest(source_manifest, raw=first_raw, validation=validation)
    exclusion = tmp_path / "exclusion.private.json"
    build_mmlu_pro_screening_exclusion_manifest(
        screening_source_manifest_path=source_manifest,
        output_path=exclusion,
    )

    with pytest.raises(BenchmarkReplacementError) as raised:
        build_mmlu_pro_stem_replacement(
            raw_parquet_path=second_raw,
            standardized_dataset_path=tmp_path / "output.jsonl",
            per_category=2,
            expected_raw_sha256=second_digest,
            screening_exclusion_manifest_path=exclusion,
        )
    assert raised.value.reason_code == "screening_exclusion_source_snapshot_mismatch"


def test_mmlu_pro_replacement_selection_does_not_depend_on_gold_answers(tmp_path: Path) -> None:
    first_raw = tmp_path / "first.parquet"
    second_raw = tmp_path / "second.parquet"
    first_digest = _write_parquet(first_raw, answer_offset=0)
    second_digest = _write_parquet(second_raw, answer_offset=1)

    first_dataset = tmp_path / "first.jsonl"
    second_dataset = tmp_path / "second.jsonl"
    first = build_mmlu_pro_stem_replacement(
        raw_parquet_path=first_raw,
        standardized_dataset_path=first_dataset,
        per_category=2,
        expected_raw_sha256=first_digest,
    )
    second = build_mmlu_pro_stem_replacement(
        raw_parquet_path=second_raw,
        standardized_dataset_path=second_dataset,
        per_category=2,
        expected_raw_sha256=second_digest,
    )
    first_rows = [json.loads(line) for line in first_dataset.read_text(encoding="utf-8").splitlines()]
    second_rows = [json.loads(line) for line in second_dataset.read_text(encoding="utf-8").splitlines()]

    assert [row["id"] for row in first_rows] == [row["id"] for row in second_rows]
    assert [row["question"] for row in first_rows] == [row["question"] for row in second_rows]
    assert first["selection"]["gold_answers_used_for_selection"] is False
    assert second["selection"]["gold_answers_used_for_selection"] is False


def test_mmlu_pro_replacement_rejects_unpinned_source(tmp_path: Path) -> None:
    raw = tmp_path / "not_the_pinned_snapshot.parquet"
    _write_parquet(raw)
    with pytest.raises(BenchmarkReplacementError) as raised:
        build_mmlu_pro_stem_replacement(
            raw_parquet_path=raw,
            standardized_dataset_path=tmp_path / "output.jsonl",
            expected_raw_sha256="0" * 64,
        )
    assert raised.value.reason_code == "raw_source_sha256_mismatch"
    assert not (tmp_path / "output.jsonl").exists()
