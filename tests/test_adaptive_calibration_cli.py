"""自适应渠道校准 CLI 功能测试。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_manifest(path: Path, provider_name: str) -> None:
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "provider": provider_name,
                        "api_format": "responses",
                        "models": [{"model": "gpt-5.6-sol"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _run_cli(previous: Path, current: Path, output: Path) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "scripts/run_adaptive_calibration.py"),
            "--previous-manifest",
            str(previous),
            "--current-manifest",
            str(current),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "结果已保存" in result.stdout
    return json.loads(output.read_text(encoding="utf-8"))


def test_cli_marks_channel_change_when_no_scores(tmp_path: Path) -> None:
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    output = tmp_path / "result.json"
    _write_manifest(previous, "nvidia")
    _write_manifest(current, "cpa")

    payload = _run_cli(previous, current, output)

    assert payload["decision"]["channel_changed"] is True
    assert payload["decision"]["needs_recalibration"] is True
    assert "校准" in payload["recalibration_prompt"]
    assert payload["raw_scores_persisted"] is False
    assert payload["secrets_persisted"] is False


def test_cli_does_not_recalibrate_on_identical_channel(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "result.json"
    _write_manifest(manifest, "cpa")

    payload = _run_cli(manifest, manifest, output)

    assert payload["decision"]["channel_changed"] is False
    assert payload["decision"]["needs_recalibration"] is False
    assert payload["recalibration_prompt"] == "无需重校准。"
