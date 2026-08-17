#!/usr/bin/env python3
"""从私有 screening source manifest 创建不可变 successor manifest。

该工具只允许改变 pre-registration 的日期和 selection seed，保留原始 source
case contract。输入和输出都必须由 operator 放在 private root；receipt 只保存
内容 hash，不复制 prompt、label、provider identity 或 source path。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping


SOURCE_MANIFEST_SCHEMA = "axio_fusion_api.non_target_screening_source_manifest.v1"
SUCCESSOR_RECEIPT_SCHEMA = (
    "axio_fusion_api.non_target_screening_source_manifest_successor_receipt.v1"
)
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt-output", required=True, type=Path)
    parser.add_argument("--selection-seed", required=True)
    parser.add_argument("--registered-on", required=True)
    return parser


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("successor_source_manifest_read_failed") from exc
    if not isinstance(value, Mapping):
        raise ValueError("successor_source_manifest_object_required")
    return dict(value)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, path)
    except OSError as exc:
        raise ValueError("successor_manifest_atomic_write_failed") from exc


def _validate_date(value: str) -> str:
    normalized = str(value or "").strip()
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("successor_registered_on_invalid") from exc
    return normalized


def _validate_source(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("schema") != SOURCE_MANIFEST_SCHEMA:
        raise ValueError("successor_source_manifest_schema_invalid")
    if payload.get("secrets_persisted") is True:
        raise ValueError("successor_source_manifest_secrets_flagged")
    if not isinstance(payload.get("sources"), list) or not payload["sources"]:
        raise ValueError("successor_source_manifest_sources_missing")
    pre_registration = payload.get("pre_registration")
    if not isinstance(pre_registration, Mapping):
        raise ValueError("successor_source_manifest_pre_registration_missing")
    if pre_registration.get("declared_before_target_campaign") is not True:
        raise ValueError("successor_source_manifest_not_pre_registered")
    if pre_registration.get("target_benchmark_results_used") is not False:
        raise ValueError("successor_source_manifest_target_results_used")
    if pre_registration.get("target_suite_results_used") is not False:
        raise ValueError("successor_source_manifest_target_suite_results_used")
    old_seed = str(pre_registration.get("selection_seed") or "").strip()
    if not old_seed:
        raise ValueError("successor_source_manifest_selection_seed_missing")
    return pre_registration


def create_successor_manifest(
    *,
    source_manifest: Path,
    output: Path,
    receipt_output: Path,
    selection_seed: str,
    registered_on: str,
) -> dict[str, Any]:
    """创建 successor，并返回已写入的 hash-only receipt。"""

    source_path = source_manifest.resolve()
    output_path = output.resolve()
    if source_path == output_path:
        raise ValueError("successor_source_and_output_must_differ")
    seed = str(selection_seed or "").strip()
    if not seed:
        raise ValueError("successor_selection_seed_missing")
    registration_date = _validate_date(registered_on)
    original = _read_object(source_path)
    pre_registration = _validate_source(original)
    old_seed = str(pre_registration.get("selection_seed") or "").strip()
    if old_seed == seed:
        raise ValueError("successor_selection_seed_must_change")

    successor = copy.deepcopy(original)
    successor_pre_registration = successor["pre_registration"]
    successor_pre_registration["selection_seed"] = seed
    successor_pre_registration["registered_on"] = registration_date
    _atomic_write_json(output_path, successor)

    receipt = {
        "schema": SUCCESSOR_RECEIPT_SCHEMA,
        "status": "ready",
        "source_manifest_file_sha256": _sha256_file(source_path),
        "successor_manifest_file_sha256": _sha256_file(output_path),
        "selection_seed_sha256": _sha256_text(seed),
        "registered_on": registration_date,
        "changed_fields": [
            "pre_registration.registered_on",
            "pre_registration.selection_seed",
        ],
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }
    _atomic_write_json(receipt_output, receipt)
    return receipt


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = create_successor_manifest(
            source_manifest=args.source_manifest,
            output=args.output,
            receipt_output=args.receipt_output,
            selection_seed=args.selection_seed,
            registered_on=args.registered_on,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "error_code": str(exc)}))
        return 2
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
