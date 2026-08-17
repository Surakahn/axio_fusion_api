from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import create_screening_successor_manifest as successor


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _source() -> dict:
    return {
        "schema": successor.SOURCE_MANIFEST_SCHEMA,
        "private_artifact": True,
        "secrets_persisted": False,
        "contains_questions": True,
        "sources": [{"source_id": "source-a", "cases": [{"private": True}]}],
        "pre_registration": {
            "declared_before_target_campaign": True,
            "registered_on": "2026-08-14",
            "selection_seed": "old-seed",
            "target_benchmark_results_used": False,
            "target_suite_results_used": False,
        },
    }


def test_successor_changes_only_registration_fields(tmp_path: Path) -> None:
    source = tmp_path / "source.private.json"
    output = tmp_path / "successor.private.json"
    receipt_path = tmp_path / "successor.safe.json"
    original = _source()
    _write(source, original)

    receipt = successor.create_successor_manifest(
        source_manifest=source,
        output=output,
        receipt_output=receipt_path,
        selection_seed="new-seed",
        registered_on="2026-08-17",
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(source.read_text(encoding="utf-8")) == original
    assert result["sources"] == original["sources"]
    assert result["pre_registration"]["selection_seed"] == "new-seed"
    assert result["pre_registration"]["registered_on"] == "2026-08-17"
    assert receipt["status"] == "ready"
    assert receipt["successor_manifest_file_sha256"]
    assert all(
        value is False
        for key, value in receipt.items()
        if key.endswith("_persisted")
    )


def test_successor_rejects_reusing_seed(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    _write(source, _source())
    with pytest.raises(ValueError, match="selection_seed_must_change"):
        successor.create_successor_manifest(
            source_manifest=source,
            output=tmp_path / "out.json",
            receipt_output=tmp_path / "receipt.json",
            selection_seed="old-seed",
            registered_on="2026-08-17",
        )


def test_successor_rejects_target_material(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    payload = _source()
    payload["pre_registration"]["target_suite_results_used"] = True
    _write(source, payload)
    with pytest.raises(ValueError, match="target_suite_results_used"):
        successor.create_successor_manifest(
            source_manifest=source,
            output=tmp_path / "out.json",
            receipt_output=tmp_path / "receipt.json",
            selection_seed="new-seed",
            registered_on="2026-08-17",
        )
