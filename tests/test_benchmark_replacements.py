from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from axio_fusion_api.benchmark_replacements import (
    MMLU_PRO_CATEGORY_ORDER,
    BenchmarkReplacementError,
    build_mmlu_pro_stem_replacement,
)
from axio_fusion_api.evaluation import (
    _campaign_suite_specs,
    build_benchmark_dataset_manifest_template,
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


def test_mmlu_pro_replacement_is_deterministic_and_validator_ready(tmp_path: Path) -> None:
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
    gpqa_slot = next(row for row in normalized if row["suite_id"] == "gpqa_diamond")
    assert gpqa_slot["replacement_active"] is True
    assert gpqa_slot["benchmark_dataset_id"] == "mmlu_pro_stem"

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
