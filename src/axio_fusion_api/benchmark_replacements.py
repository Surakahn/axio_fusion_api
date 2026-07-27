"""Deterministic, explicitly labelled replacements for unavailable benchmarks.

The target benchmark matrix is owned by the evaluation control plane.  This
module only prepares a replacement asset when an upstream benchmark is
legally or operationally unavailable; it never relabels the replacement as
the unavailable benchmark and never exposes raw cases in receipts.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .schemas import sha256_text, stable_json


MMLU_PRO_DATASET_ID = "TIGER-Lab/MMLU-Pro"
MMLU_PRO_SOURCE_URL = "https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro"
MMLU_PRO_REVISION = "b189ec765aa7ed75c8acfea42df31fdae71f97be"
MMLU_PRO_SPLIT = "test"
MMLU_PRO_RAW_FILENAME = "test-00000-of-00001.parquet"
MMLU_PRO_EXPECTED_RAW_SHA256 = "0e24a191921c2f453518a537a8b2117bd137e7714d4ef1565e9ba06c1ecb9ad8"
MMLU_PRO_EXPECTED_RAW_BYTES = 4_144_185
MMLU_PRO_REPLACEMENT_ID = "mmlu_pro_stem"
MMLU_PRO_REPLACEMENT_VERSION = "mmlu-pro-stem-v1"
MMLU_PRO_REPLACES_SUITE_ID = "gpqa_diamond"
MMLU_PRO_CATEGORY_ORDER = (
    "biology",
    "chemistry",
    "computer science",
    "engineering",
    "math",
    "physics",
)
MMLU_PRO_DEFAULT_PER_CATEGORY = 100
MMLU_PRO_DEFAULT_SEED = "axio-mmlu-pro-stem-v1"
MMLU_PRO_SCREENING_DISJOINT_VERSION = "mmlu-pro-stem-v2-screening-disjoint"
MMLU_PRO_SCREENING_EXCLUSION_SCHEMA = (
    "axio_fusion_api.mmlu_pro_screening_exclusion_manifest.v1"
)
MMLU_PRO_SCREENING_EXCLUSION_RECEIPT_SCHEMA = (
    "axio_fusion_api.mmlu_pro_screening_exclusion_receipt.v1"
)
MMLU_PRO_DEFAULT_RAW_PATH = "/mnt/storage/axio_fusion_benchmarks/raw/mmlu_pro/test-00000-of-00001.parquet"
MMLU_PRO_DEFAULT_DATASET_PATH = "/mnt/storage/axio_fusion_benchmarks/standardized/mmlu_pro_stem.jsonl"
MMLU_PRO_DEFAULT_RECEIPT_PATH = "/mnt/storage/axio_fusion_benchmarks/manifests/mmlu_pro_stem_replacement.safe.json"

_REQUIRED_COLUMNS = frozenset({"question", "options", "answer", "category"})


class BenchmarkReplacementError(RuntimeError):
    """A replacement build failure with a safe, content-free receipt."""

    def __init__(self, reason_code: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.reason_code = str(reason_code or "replacement_build_failed")
        self.details = dict(details or {})
        super().__init__(f"benchmark_replacement_failed:{self.reason_code}")

    def safe_receipt(self) -> dict[str, Any]:
        return {
            "schema": "axio_fusion_api.benchmark_replacement_receipt.v1",
            "replacement_id": MMLU_PRO_REPLACEMENT_ID,
            "status": "failed",
            "reason_code": self.reason_code,
            "details": {
                key: value
                for key, value in self.details.items()
                if key.endswith("_sha256") or key in {"row_count", "expected_row_count"}
            },
            "raw_dataset_content_persisted": False,
            "raw_labels_persisted": False,
            "raw_prompts_persisted": False,
            "secrets_persisted": False,
        }


def build_mmlu_pro_stem_replacement(
    *,
    raw_parquet_path: str | Path,
    standardized_dataset_path: str | Path,
    receipt_path: str | Path | None = None,
    base_dataset_manifest_path: str | Path | None = None,
    replacement_dataset_manifest_path: str | Path | None = None,
    per_category: int = MMLU_PRO_DEFAULT_PER_CATEGORY,
    seed: str = MMLU_PRO_DEFAULT_SEED,
    expected_raw_sha256: str = MMLU_PRO_EXPECTED_RAW_SHA256,
    screening_exclusion_manifest_path: str | Path | None = None,
    replacement_version: str | None = None,
) -> dict[str, Any]:
    """Build and optionally publish the MMLU-Pro STEM replacement.

    The selection key is derived only from public question material, category,
    source revision, and an explicit seed.  Gold answers are copied for the
    evaluator but never participate in selection, ordering, or the receipt.
    """

    raw_path = Path(raw_parquet_path)
    output_path = Path(standardized_dataset_path)
    selected_per_category = _positive_int(per_category, "per_category")
    selected_seed = str(seed or "").strip()
    if not selected_seed:
        raise BenchmarkReplacementError("selection_seed_missing")
    expected_digest = str(expected_raw_sha256 or "").strip().lower()
    if not _is_sha256(expected_digest):
        raise BenchmarkReplacementError("expected_source_sha256_invalid")
    if not raw_path.is_file():
        raise BenchmarkReplacementError("raw_source_not_found")
    raw_digest, raw_bytes = _sha256_file(raw_path)
    if raw_digest != expected_digest:
        raise BenchmarkReplacementError(
            "raw_source_sha256_mismatch",
            details={"actual_sha256": raw_digest, "expected_sha256": expected_digest},
        )
    if expected_digest == MMLU_PRO_EXPECTED_RAW_SHA256 and raw_bytes != MMLU_PRO_EXPECTED_RAW_BYTES:
        raise BenchmarkReplacementError(
            "raw_source_byte_count_mismatch",
            details={"actual_bytes": raw_bytes, "expected_bytes": MMLU_PRO_EXPECTED_RAW_BYTES},
        )
    exclusion = _load_screening_exclusion_manifest(
        screening_exclusion_manifest_path
    )
    if (
        exclusion["status"] == "verified"
        and exclusion["screening_mmlu_pro_raw_file_sha256"] != raw_digest
    ):
        raise BenchmarkReplacementError(
            "screening_exclusion_source_snapshot_mismatch",
            details={
                "actual_sha256": raw_digest,
                "expected_sha256": exclusion[
                    "screening_mmlu_pro_raw_file_sha256"
                ],
            },
        )
    rows = _read_mmlu_pro_rows(raw_path)
    source_counts = Counter(str(row.get("category") or "") for row in rows)
    missing_categories = [
        category
        for category in MMLU_PRO_CATEGORY_ORDER
        if source_counts.get(category, 0) < selected_per_category
    ]
    if missing_categories:
        raise BenchmarkReplacementError(
            "stem_category_population_insufficient",
            details={
                "row_count": len(rows),
                "expected_row_count": len(MMLU_PRO_CATEGORY_ORDER) * selected_per_category,
            },
        )
    selected_version = _replacement_version(
        replacement_version,
        screening_exclusion_manifest_path=screening_exclusion_manifest_path,
    )
    selected, selection_summary = _select_rows(
        rows,
        per_category=selected_per_category,
        seed=selected_seed,
        replacement_version=selected_version,
        excluded_source_row_identities=exclusion["source_row_identities"],
    )
    selected_source_row_identities = selection_summary[
        "selected_source_row_identities"
    ]
    overlap = selected_source_row_identities & exclusion["source_row_identities"]
    if overlap:
        raise BenchmarkReplacementError(
            "screening_case_overlap_detected_after_selection",
            details={"row_count": len(overlap)},
        )
    _write_jsonl_atomic(output_path, selected)
    standardized_digest, standardized_bytes = _sha256_file(output_path)
    selected_counts = Counter(str(row["category"]) for row in selected)
    receipt = {
        "schema": "axio_fusion_api.benchmark_replacement_receipt.v1",
        "replacement_id": MMLU_PRO_REPLACEMENT_ID,
        "replacement_version": selected_version,
        "status": "ready",
        "benchmark_slot_id": MMLU_PRO_REPLACES_SUITE_ID,
        "explicitly_not_gpqa": True,
        "source": {
            "dataset_id": MMLU_PRO_DATASET_ID,
            "source_url": MMLU_PRO_SOURCE_URL,
            "revision": MMLU_PRO_REVISION,
            "split": MMLU_PRO_SPLIT,
            "filename": MMLU_PRO_RAW_FILENAME,
            "raw_file_sha256": raw_digest,
            "raw_file_bytes": raw_bytes,
        },
        "selection": {
            "seed": selected_seed,
            "categories": list(MMLU_PRO_CATEGORY_ORDER),
            "source_row_count": len(rows),
            "source_counts_by_category": {
                category: int(source_counts.get(category, 0))
                for category in MMLU_PRO_CATEGORY_ORDER
            },
            "per_category": selected_per_category,
            "selected_case_count": len(selected),
            "selected_counts_by_category": {
                category: int(selected_counts.get(category, 0))
                for category in MMLU_PRO_CATEGORY_ORDER
            },
            "ordering": "category_order_then_public_material_selection_key",
            "selection_key": "sha256(seed,revision,category,question,options,source_row_identity)",
            "gold_answers_used_for_selection": False,
            "screening_case_disjointness": {
                "status": exclusion["status"],
                "enforced": exclusion["status"] == "verified",
                "exclusion_manifest_schema": exclusion["schema"],
                "exclusion_manifest_content_sha256": exclusion["content_sha256"],
                "screening_source_manifest_content_sha256": exclusion[
                    "screening_source_manifest_content_sha256"
                ],
                "screening_source_raw_file_sha256": exclusion[
                    "screening_mmlu_pro_raw_file_sha256"
                ],
                "replacement_raw_file_sha256": raw_digest,
                "screening_mmlu_pro_source_count": exclusion[
                    "screening_mmlu_pro_source_count"
                ],
                "excluded_source_row_identity_count": len(
                    exclusion["source_row_identities"]
                ),
                "excluded_source_row_identity_set_sha256": sha256_text(
                    stable_json(sorted(exclusion["source_row_identities"]))
                ),
                "excluded_matching_source_row_count": selection_summary[
                    "excluded_matching_source_row_count"
                ],
                "selected_source_row_identity_count": len(
                    selected_source_row_identities
                ),
                "selected_source_row_identity_set_sha256": sha256_text(
                    stable_json(sorted(selected_source_row_identities))
                ),
                "selected_overlap_count": len(overlap),
                "gold_answers_used_for_exclusion": False,
                "raw_case_ids_persisted": False,
            },
        },
        "standardized_dataset": {
            "path_sha256": sha256_text(str(output_path)),
            "file_sha256": standardized_digest,
            "file_bytes": standardized_bytes,
            "format": "jsonl_multiple_choice",
            "case_id_policy": "stable_public_material_hash_prefix",
        },
        "replacement_contract": {
            "replacement_is_explicit": True,
            "replacement_slot_preserved": True,
            "original_suite_id": MMLU_PRO_REPLACES_SUITE_ID,
            "replacement_suite_id": MMLU_PRO_REPLACEMENT_ID,
            "original_suite_results_must_not_be_labelled_as_replacement_results": True,
            "source_snapshot_and_case_hashes_required_before_model_calls": True,
            "raw_dataset_content_persisted": False,
            "raw_labels_persisted": False,
            "raw_prompts_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_dataset_content_persisted": False,
        "raw_labels_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    _write_json_atomic(receipt_path, receipt)
    if base_dataset_manifest_path or replacement_dataset_manifest_path:
        if not base_dataset_manifest_path or not replacement_dataset_manifest_path:
            raise BenchmarkReplacementError("replacement_manifest_paths_incomplete")
        replacement_manifest = apply_replacement_to_dataset_manifest(
            base_manifest_path=base_dataset_manifest_path,
            standardized_dataset_path=output_path,
            replacement_receipt=receipt,
        )
        _write_json_atomic(replacement_dataset_manifest_path, replacement_manifest)
        receipt["replacement_dataset_manifest"] = {
            "path_sha256": sha256_text(str(replacement_dataset_manifest_path)),
            "file_sha256": _sha256_file(Path(replacement_dataset_manifest_path))[0],
            "raw_dataset_content_persisted": False,
        }
        _write_json_atomic(receipt_path, receipt)
    return receipt


def build_mmlu_pro_screening_exclusion_manifest(
    *,
    screening_source_manifest_path: str | Path,
    output_path: str | Path,
    safe_receipt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Bind selected non-target MMLU-Pro rows as target-set exclusions.

    The private manifest intentionally contains only public source row ids. It
    does not preserve prompts, questions, answer labels, provider outputs, or
    model ranking outcomes. The matching safe receipt contains counts and
    hashes only, allowing the replacement builder to prove disjointness without
    leaking the exclusion set into campaign evidence.
    """

    source_path = Path(screening_source_manifest_path)
    try:
        source_text = source_path.read_text(encoding="utf-8")
        source_manifest = json.loads(source_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkReplacementError("screening_source_manifest_unreadable") from exc
    if not isinstance(source_manifest, Mapping):
        raise BenchmarkReplacementError("screening_source_manifest_schema_invalid")
    if source_manifest.get("schema") != "axio_fusion_api.non_target_screening_source_manifest.v1":
        raise BenchmarkReplacementError("screening_source_manifest_schema_invalid")
    pre_registration = source_manifest.get("pre_registration")
    if not isinstance(pre_registration, Mapping):
        raise BenchmarkReplacementError("screening_source_manifest_pre_registration_missing")
    selection_seed = str(pre_registration.get("selection_seed") or "").strip()
    if not selection_seed:
        raise BenchmarkReplacementError("screening_source_manifest_selection_seed_missing")

    sources = [
        dict(source)
        for source in source_manifest.get("sources", [])
        if isinstance(source, Mapping) and str(source.get("adapter") or "") == "mmlu_pro"
    ]
    if not sources:
        raise BenchmarkReplacementError("screening_source_manifest_mmlu_pro_source_missing")

    # Import locally so ordinary replacement builds do not pull screening
    # mechanics into the dataset-only code path.
    from .baseline_screening import _load_mmlu_pro_cases, _select_screening_cases

    source_rows: list[dict[str, Any]] = []
    source_raw_snapshots: set[tuple[str, int]] = set()
    excluded_source_row_identities: set[str] = set()
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            raise BenchmarkReplacementError("screening_source_manifest_mmlu_pro_source_id_missing")
        try:
            source_dataset_path = Path(str(source.get("dataset_path") or ""))
            source_dataset_digest, source_dataset_bytes = _sha256_file(
                source_dataset_path
            )
            cases = _load_mmlu_pro_cases(source)
            selected_cases = _select_screening_cases(
                cases,
                source.get("selection"),
                selection_seed=selection_seed,
                source_id=source_id,
            )
        except Exception as exc:  # noqa: BLE001 - source paths stay private
            raise BenchmarkReplacementError(
                "screening_source_manifest_mmlu_pro_case_selection_failed"
            ) from exc
        identities = {
            str(case.case_id).removeprefix("mmlu-pro:")
            for case in selected_cases
            if str(case.case_id).startswith("mmlu-pro:")
        }
        if len(identities) != len(selected_cases) or not identities:
            raise BenchmarkReplacementError(
                "screening_source_manifest_mmlu_pro_case_identity_invalid"
            )
        excluded_source_row_identities.update(identities)
        source_raw_snapshots.add((source_dataset_digest, source_dataset_bytes))
        source_rows.append(
            {
                "source_id_sha256": sha256_text(source_id),
                "selected_case_count": len(selected_cases),
                "source_dataset_file_sha256": source_dataset_digest,
                "source_dataset_file_bytes": source_dataset_bytes,
                "source_row_identity_set_sha256": sha256_text(
                    stable_json(sorted(identities))
                ),
            }
        )

    if len(source_raw_snapshots) != 1:
        raise BenchmarkReplacementError(
            "screening_source_manifest_mmlu_pro_raw_snapshot_ambiguous"
        )
    source_raw_digest, source_raw_bytes = next(iter(source_raw_snapshots))
    sorted_identities = sorted(excluded_source_row_identities)
    private_manifest = {
        "schema": MMLU_PRO_SCREENING_EXCLUSION_SCHEMA,
        "status": "ready",
        "screening_source_manifest_content_sha256": sha256_text(source_text),
        "screening_selection_seed_sha256": sha256_text(selection_seed),
        "screening_mmlu_pro_source_count": len(source_rows),
        "screening_mmlu_pro_raw_file_sha256": source_raw_digest,
        "screening_mmlu_pro_raw_file_bytes": source_raw_bytes,
        "sources": sorted(source_rows, key=lambda row: row["source_id_sha256"]),
        "mmlu_pro_source_row_identities": sorted_identities,
        "mmlu_pro_source_row_identity_set_sha256": sha256_text(
            stable_json(sorted_identities)
        ),
        "raw_questions_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    _write_json_atomic(output_path, private_manifest)
    safe_receipt = _screening_exclusion_safe_receipt(
        private_manifest,
        private_manifest_path=Path(output_path),
    )
    _write_json_atomic(safe_receipt_path, safe_receipt)
    return safe_receipt


def apply_replacement_to_dataset_manifest(
    *,
    base_manifest_path: str | Path,
    standardized_dataset_path: str | Path,
    replacement_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a 21-slot manifest with an explicit replacement row.

    The returned row uses ``suite_id=mmlu_pro_stem`` and
    ``replaces_suite_id=gpqa_diamond``.  The evaluation control plane can
    normalize the slot without allowing the replacement to masquerade as
    GPQA.
    """

    base_path = Path(base_manifest_path)
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkReplacementError("base_manifest_unreadable") from exc
    if not isinstance(base, Mapping) or not isinstance(base.get("suites"), list):
        raise BenchmarkReplacementError("base_manifest_schema_invalid")
    suites = [dict(row) for row in base["suites"] if isinstance(row, Mapping)]
    gpqa_rows = [row for row in suites if str(row.get("suite_id") or "") == MMLU_PRO_REPLACES_SUITE_ID]
    if len(gpqa_rows) != 1:
        raise BenchmarkReplacementError("base_manifest_gpqa_slot_missing_or_duplicated")
    if any(str(row.get("suite_id") or "") == MMLU_PRO_REPLACEMENT_ID for row in suites):
        raise BenchmarkReplacementError("replacement_suite_already_present")
    original = gpqa_rows[0]
    replacement_row = _replacement_suite_spec(
        original=original,
        standardized_dataset_path=standardized_dataset_path,
        replacement_receipt=replacement_receipt,
    )
    replaced = [
        replacement_row if str(row.get("suite_id") or "") == MMLU_PRO_REPLACES_SUITE_ID else row
        for row in suites
    ]
    output = dict(base)
    output["suites"] = replaced
    output["suite_count"] = len(replaced)
    output["benchmark_replacement_policy"] = {
        "schema": "axio_fusion_api.benchmark_replacement_policy.v1",
        "status": "explicit_replacement",
        "replacement_count": 1,
        "replacements": [
            {
                "benchmark_slot_id": MMLU_PRO_REPLACES_SUITE_ID,
                "replacement_suite_id": MMLU_PRO_REPLACEMENT_ID,
                "explicitly_not_gpqa": True,
                "replacement_receipt_binding_sha256": _replacement_receipt_binding_sha256(
                    replacement_receipt
                ),
            }
        ],
        "gated_original_remains_unavailable": True,
        "final_reports_must_show_replacement_identity": True,
        "raw_dataset_content_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    output["assembly_receipt"] = {
        "schema": "axio_fusion_api.replacement_dataset_manifest_receipt.v1",
        "base_manifest_sha256": _sha256_file(base_path)[0],
        "suite_count": len(replaced),
        "replacement_count": 1,
        "raw_manifest_content_persisted": False,
        "raw_dataset_content_persisted": False,
        "secrets_persisted": False,
    }
    return output


def _replacement_suite_spec(
    *,
    original: Mapping[str, Any],
    standardized_dataset_path: str | Path,
    replacement_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    selection = replacement_receipt.get("selection") if isinstance(replacement_receipt.get("selection"), Mapping) else {}
    per_category = int(selection.get("per_category") or MMLU_PRO_DEFAULT_PER_CATEGORY)
    case_count = int(selection.get("selected_case_count") or 0)
    return {
        "suite_id": MMLU_PRO_REPLACEMENT_ID,
        "benchmark_slot_id": MMLU_PRO_REPLACES_SUITE_ID,
        "replaces_suite_id": MMLU_PRO_REPLACES_SUITE_ID,
        "benchmark_identity": "MMLU-Pro STEM stratified replacement",
        "explicitly_not_gpqa": True,
        "category": str(original.get("category") or "science_knowledge"),
        "title": "MMLU-Pro STEM (explicit GPQA replacement)",
        "reference": MMLU_PRO_SOURCE_URL,
        "task_format": "multiple_choice",
        "dataset": str(standardized_dataset_path),
        "min_cases": max(1, min(int(original.get("min_cases") or case_count or 1), case_count or 1)),
        "required_jsonl_fields": ["question", "options", "answer"],
        "optional_jsonl_fields": ["id", "category", "subject"],
        "methodology": {
            "suite_id": MMLU_PRO_REPLACEMENT_ID,
            "benchmark_slot_id": MMLU_PRO_REPLACES_SUITE_ID,
            "category": str(original.get("category") or "science_knowledge"),
            "title": "MMLU-Pro STEM (explicit GPQA replacement)",
            "reference": MMLU_PRO_SOURCE_URL,
            "task_format": "multiple_choice",
            "source_type": "official_huggingface_snapshot",
            "source_revision": MMLU_PRO_REVISION,
            "dataset_split": MMLU_PRO_SPLIT,
            "case_selection": f"{per_category} cases per STEM category using deterministic public-material hash ordering",
            "scoring_protocol": "variable-option exact option-letter accuracy (three to ten options)",
            "replacement_disclosure": "This is not GPQA and must be reported as its own replacement dataset.",
            "gold_answers_used_for_selection": False,
            "raw_dataset_content_persisted": False,
            "raw_labels_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "requires_official_harness": False,
        "requires_external_judge_imports": False,
        "imported_runs": None,
        "replacement_receipt": {
            "schema": str(replacement_receipt.get("schema") or ""),
            "replacement_version": str(
                replacement_receipt.get("replacement_version") or ""
            ),
            "file_sha256": str((replacement_receipt.get("standardized_dataset") or {}).get("file_sha256") or ""),
            "case_count": case_count,
            "source_revision": MMLU_PRO_REVISION,
            "raw_file_sha256": str(
                (replacement_receipt.get("source") or {}).get("raw_file_sha256")
                or ""
            ),
            "explicitly_not_gpqa": True,
            "screening_case_disjointness": _replacement_screening_disjointness_summary(
                selection
            ),
        },
        "raw_dataset_content_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _replacement_receipt_binding_sha256(receipt: Mapping[str, Any]) -> str:
    """Hash immutable source/selection/output facts without a self-reference."""

    return sha256_text(
        stable_json(
            {
                "schema": receipt.get("schema"),
                "replacement_id": receipt.get("replacement_id"),
                "replacement_version": receipt.get("replacement_version"),
                "benchmark_slot_id": receipt.get("benchmark_slot_id"),
                "source": receipt.get("source"),
                "selection": receipt.get("selection"),
                "standardized_dataset": receipt.get("standardized_dataset"),
            }
        )
    )


def _read_mmlu_pro_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise BenchmarkReplacementError("pyarrow_required_for_mmlu_pro_parquet") from exc
    try:
        table = parquet.read_table(path)
    except Exception as exc:  # noqa: BLE001 - sanitize optional reader failures
        raise BenchmarkReplacementError("mmlu_pro_parquet_unreadable") from exc
    columns = set(str(name) for name in table.column_names)
    if not _REQUIRED_COLUMNS.issubset(columns):
        raise BenchmarkReplacementError("mmlu_pro_schema_missing_required_columns")
    rows = []
    for index, raw in enumerate(table.to_pylist()):
        if not isinstance(raw, Mapping):
            raise BenchmarkReplacementError("mmlu_pro_row_not_object")
        row = {
            "question": str(raw.get("question") or "").strip(),
            "options": _normalize_options(raw.get("options")),
            "answer": str(raw.get("answer") or "").strip().upper(),
            "category": str(raw.get("category") or "").strip().lower(),
            "question_id": str(raw.get("question_id") or ""),
            "source_row_identity": str(raw.get("question_id") or index),
        }
        if (
            not row["question"]
            or not 3 <= len(row["options"]) <= 10
            or row["answer"] not in _option_labels(len(row["options"]))
        ):
            raise BenchmarkReplacementError("mmlu_pro_row_invalid_multiple_choice_shape")
        rows.append(row)
    if not rows:
        raise BenchmarkReplacementError("mmlu_pro_dataset_empty")
    return rows


def _select_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    per_category: int,
    seed: str,
    replacement_version: str,
    excluded_source_row_identities: set[str] | frozenset[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[tuple[str, Mapping[str, Any]]]] = {category: [] for category in MMLU_PRO_CATEGORY_ORDER}
    excluded_matching_source_row_count = 0
    for index, row in enumerate(rows):
        category = str(row.get("category") or "")
        if category not in grouped:
            continue
        source_row_identity = str(row.get("source_row_identity") or row.get("question_id") or index)
        if source_row_identity in excluded_source_row_identities:
            excluded_matching_source_row_count += 1
            continue
        public_material = {
            "category": category,
            "question": str(row.get("question") or ""),
            "options": list(row.get("options") or []),
            "source_row_identity": source_row_identity,
        }
        selection_key = sha256_text(
            stable_json(
                {
                    "seed": seed,
                    "source_revision": MMLU_PRO_REVISION,
                    "public_material": public_material,
                }
            )
        )
        grouped[category].append((selection_key, row))
    selected: list[dict[str, Any]] = []
    selected_source_row_identities: set[str] = set()
    remaining_counts = {
        category: len(grouped[category]) for category in MMLU_PRO_CATEGORY_ORDER
    }
    if any(count < per_category for count in remaining_counts.values()):
        raise BenchmarkReplacementError(
            "stem_category_population_insufficient_after_screening_exclusion",
            details={
                "row_count": sum(remaining_counts.values()),
                "expected_row_count": len(MMLU_PRO_CATEGORY_ORDER) * per_category,
            },
        )
    for category in MMLU_PRO_CATEGORY_ORDER:
        ordered = sorted(grouped[category], key=lambda item: (item[0], str(item[1].get("question_id") or "")))
        for selection_key, row in ordered[:per_category]:
            source_row_identity = str(
                row.get("source_row_identity") or row.get("question_id") or ""
            )
            if not source_row_identity:
                raise BenchmarkReplacementError("mmlu_pro_source_row_identity_missing")
            selected_source_row_identities.add(source_row_identity)
            selected.append(
                {
                    "id": f"{replacement_version}::{category}::{selection_key[:16]}",
                    "question": str(row["question"]),
                    "options": [str(option) for option in row["options"]],
                    "answer": str(row["answer"]),
                    "category": category,
                    "subject": f"mmlu_pro_{category.replace(' ', '_')}",
                }
            )
    return selected, {
        "excluded_matching_source_row_count": excluded_matching_source_row_count,
        "remaining_source_row_count": sum(remaining_counts.values()),
        "selected_source_row_identities": frozenset(selected_source_row_identities),
    }


def _load_screening_exclusion_manifest(
    path: str | Path | None,
) -> dict[str, Any]:
    if path is None:
        return {
            "status": "unverified",
            "schema": "",
            "content_sha256": "",
            "screening_source_manifest_content_sha256": "",
            "screening_mmlu_pro_source_count": 0,
            "screening_mmlu_pro_raw_file_sha256": "",
            "source_row_identities": frozenset(),
        }
    selected = Path(path)
    try:
        text = selected.read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkReplacementError("screening_exclusion_manifest_unreadable") from exc
    if not isinstance(payload, Mapping):
        raise BenchmarkReplacementError("screening_exclusion_manifest_schema_invalid")
    if payload.get("schema") != MMLU_PRO_SCREENING_EXCLUSION_SCHEMA:
        raise BenchmarkReplacementError("screening_exclusion_manifest_schema_invalid")
    if payload.get("status") != "ready":
        raise BenchmarkReplacementError("screening_exclusion_manifest_not_ready")
    raw_identities = payload.get("mmlu_pro_source_row_identities")
    if (
        not isinstance(raw_identities, list)
        or not raw_identities
        or not all(str(value) for value in raw_identities)
    ):
        raise BenchmarkReplacementError("screening_exclusion_manifest_source_row_identities_invalid")
    identities = [str(value) for value in raw_identities]
    if len(identities) != len(set(identities)):
        raise BenchmarkReplacementError("screening_exclusion_manifest_source_row_identities_duplicate")
    expected_digest = str(payload.get("mmlu_pro_source_row_identity_set_sha256") or "")
    actual_digest = sha256_text(stable_json(sorted(identities)))
    if expected_digest != actual_digest:
        raise BenchmarkReplacementError("screening_exclusion_manifest_source_row_identity_digest_mismatch")
    screening_source_manifest_digest = str(
        payload.get("screening_source_manifest_content_sha256") or ""
    )
    if not _is_sha256(screening_source_manifest_digest):
        raise BenchmarkReplacementError("screening_exclusion_manifest_source_manifest_digest_invalid")
    try:
        source_count = int(payload.get("screening_mmlu_pro_source_count") or 0)
    except (TypeError, ValueError) as exc:
        raise BenchmarkReplacementError(
            "screening_exclusion_manifest_mmlu_pro_source_count_invalid"
        ) from exc
    if source_count < 1:
        raise BenchmarkReplacementError("screening_exclusion_manifest_mmlu_pro_source_missing")
    source_raw_digest = str(
        payload.get("screening_mmlu_pro_raw_file_sha256") or ""
    )
    if not _is_sha256(source_raw_digest):
        raise BenchmarkReplacementError(
            "screening_exclusion_manifest_source_snapshot_digest_invalid"
        )
    return {
        "status": "verified",
        "schema": MMLU_PRO_SCREENING_EXCLUSION_SCHEMA,
        "content_sha256": sha256_text(text),
        "screening_source_manifest_content_sha256": screening_source_manifest_digest,
        "screening_mmlu_pro_source_count": source_count,
        "screening_mmlu_pro_raw_file_sha256": source_raw_digest,
        "source_row_identities": frozenset(identities),
    }


def _screening_exclusion_safe_receipt(
    private_manifest: Mapping[str, Any],
    *,
    private_manifest_path: Path,
) -> dict[str, Any]:
    identities = [
        str(value)
        for value in private_manifest.get("mmlu_pro_source_row_identities", [])
        if str(value)
    ]
    return {
        "schema": MMLU_PRO_SCREENING_EXCLUSION_RECEIPT_SCHEMA,
        "status": "ready",
        "private_manifest_path_sha256": sha256_text(str(private_manifest_path)),
        "private_manifest_content_sha256": _sha256_file(private_manifest_path)[0],
        "screening_source_manifest_content_sha256": str(
            private_manifest.get("screening_source_manifest_content_sha256") or ""
        ),
        "screening_selection_seed_sha256": str(
            private_manifest.get("screening_selection_seed_sha256") or ""
        ),
        "screening_mmlu_pro_source_count": int(
            private_manifest.get("screening_mmlu_pro_source_count") or 0
        ),
        "screening_mmlu_pro_raw_file_sha256": str(
            private_manifest.get("screening_mmlu_pro_raw_file_sha256") or ""
        ),
        "excluded_source_row_identity_count": len(identities),
        "excluded_source_row_identity_set_sha256": sha256_text(
            stable_json(sorted(identities))
        ),
        "raw_case_ids_persisted": False,
        "raw_questions_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _replacement_version(
    value: str | None,
    *,
    screening_exclusion_manifest_path: str | Path | None,
) -> str:
    selected = str(value or "").strip()
    if not selected:
        selected = (
            MMLU_PRO_SCREENING_DISJOINT_VERSION
            if screening_exclusion_manifest_path is not None
            else MMLU_PRO_REPLACEMENT_VERSION
        )
    if not selected or len(selected) > 160:
        raise BenchmarkReplacementError("replacement_version_invalid")
    if (
        screening_exclusion_manifest_path is not None
        and selected != MMLU_PRO_SCREENING_DISJOINT_VERSION
    ):
        raise BenchmarkReplacementError(
            "screening_disjoint_replacement_version_invalid"
        )
    if (
        screening_exclusion_manifest_path is None
        and selected == MMLU_PRO_SCREENING_DISJOINT_VERSION
    ):
        raise BenchmarkReplacementError(
            "screening_disjoint_replacement_requires_exclusion_manifest"
        )
    return selected


def _replacement_screening_disjointness_summary(
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    proof = selection.get("screening_case_disjointness")
    if not isinstance(proof, Mapping):
        return {}
    fields = (
        "status",
        "enforced",
        "exclusion_manifest_schema",
        "exclusion_manifest_content_sha256",
        "screening_source_manifest_content_sha256",
        "screening_source_raw_file_sha256",
        "replacement_raw_file_sha256",
        "screening_mmlu_pro_source_count",
        "excluded_source_row_identity_count",
        "excluded_source_row_identity_set_sha256",
        "excluded_matching_source_row_count",
        "selected_source_row_identity_count",
        "selected_source_row_identity_set_sha256",
        "selected_overlap_count",
        "gold_answers_used_for_exclusion",
        "raw_case_ids_persisted",
    )
    return {field: proof.get(field) for field in fields}


def _normalize_options(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        values = [value[key] for key in sorted(value)]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = list(value)
    else:
        return []
    return [str(item).strip() for item in values]


def _option_labels(count: int) -> set[str]:
    return {chr(ord("A") + index) for index in range(max(0, int(count)))}


def _positive_int(value: Any, name: str) -> int:
    try:
        selected = int(value)
    except (TypeError, ValueError) as exc:
        raise BenchmarkReplacementError(f"{name}_invalid") from exc
    if selected < 1:
        raise BenchmarkReplacementError(f"{name}_invalid")
    return selected


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise BenchmarkReplacementError("artifact_unreadable") from exc
    return digest.hexdigest(), size


def _write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                handle.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_json_atomic(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(output)
        os.chmod(output, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "BenchmarkReplacementError",
    "MMLU_PRO_CATEGORY_ORDER",
    "MMLU_PRO_DATASET_ID",
    "MMLU_PRO_DEFAULT_DATASET_PATH",
    "MMLU_PRO_DEFAULT_RAW_PATH",
    "MMLU_PRO_DEFAULT_RECEIPT_PATH",
    "MMLU_PRO_DEFAULT_SEED",
    "MMLU_PRO_EXPECTED_RAW_BYTES",
    "MMLU_PRO_EXPECTED_RAW_SHA256",
    "MMLU_PRO_REPLACEMENT_ID",
    "MMLU_PRO_REPLACES_SUITE_ID",
    "MMLU_PRO_SCREENING_DISJOINT_VERSION",
    "MMLU_PRO_REVISION",
    "MMLU_PRO_SOURCE_URL",
    "apply_replacement_to_dataset_manifest",
    "build_mmlu_pro_screening_exclusion_manifest",
    "build_mmlu_pro_stem_replacement",
]
