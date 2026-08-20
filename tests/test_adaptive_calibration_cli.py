"""自适应渠道校准 CLI 功能测试。"""
from __future__ import annotations

import hashlib
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


def _run_cli(
    previous: Path,
    current: Path,
    output: Path,
    *,
    fusion_scores: Path | None = None,
    baseline_scores: Path | None = None,
    binding_artifacts: dict[str, Path] | None = None,
) -> dict:
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent.parent / "scripts/run_adaptive_calibration.py"),
        "--previous-manifest",
        str(previous),
        "--current-manifest",
        str(current),
        "--output",
        str(output),
    ]
    if fusion_scores is not None:
        command.extend(["--fusion-scores", str(fusion_scores)])
    if baseline_scores is not None:
        command.extend(["--baseline-scores", str(baseline_scores)])
    for option, key in (
        ("--registry-binding-artifact", "registry"),
        ("--rollback-binding-artifact", "rollback"),
        ("--prompt-pack-binding-artifact", "prompt_pack"),
        ("--workflow-binding-artifact", "workflow"),
        ("--contamination-audit-binding-artifact", "contamination"),
    ):
        if binding_artifacts is not None:
            command.extend([option, str(binding_artifacts[key])])
    result = subprocess.run(
        command,
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
    assert "recalibration_prompt" not in payload
    assert payload["recalibration_prompt_sha256"] == ""
    assert payload["recalibration_prompt_persisted"] is False
    assert payload["recalibration_receipt"]["status"] == "blocked"
    assert "adaptive_calibration_operational_evidence_missing" in payload[
        "recalibration_receipt"
    ]["blockers"]
    assert payload["raw_scores_persisted"] is False
    assert payload["secrets_persisted"] is False


def test_cli_does_not_recalibrate_on_identical_channel(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "result.json"
    _write_manifest(manifest, "cpa")

    payload = _run_cli(manifest, manifest, output)

    assert payload["decision"]["channel_changed"] is False
    assert payload["decision"]["needs_recalibration"] is False
    assert payload["recalibration_receipt"]["status"] == "not_required"
    assert payload["recalibration_prompt_sha256"] == ""
    assert payload["recalibration_prompt_persisted"] is False
    assert payload["recalibration_receipt"]["blockers"] == []


def test_cli_scores_emit_hash_only_blocked_receipt(tmp_path: Path) -> None:
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    fusion_scores = tmp_path / "fusion_scores.json"
    baseline_scores = tmp_path / "baseline_scores.json"
    output = tmp_path / "result.json"
    _write_manifest(previous, "nvidia")
    _write_manifest(current, "cpa")
    fusion_scores.write_text(json.dumps({"axio-pro": 0.8}), encoding="utf-8")
    baseline_scores.write_text(json.dumps({"axio-pro": 1.0}), encoding="utf-8")

    payload = _run_cli(
        previous,
        current,
        output,
        fusion_scores=fusion_scores,
        baseline_scores=baseline_scores,
    )

    receipt = payload["recalibration_receipt"]
    assert payload["decision"]["needs_recalibration"] is True
    assert receipt["status"] == "blocked"
    assert len(receipt["prompt_sha256"]) == 64
    assert payload["recalibration_prompt_sha256"] == receipt["prompt_sha256"]
    assert payload["recalibration_prompt_persisted"] is False
    assert receipt["raw_prompt_persisted"] is False
    assert receipt["raw_provider_names_persisted"] is False
    assert receipt["raw_provider_model_ids_persisted"] is False
    assert receipt["raw_provider_outputs_persisted"] is False
    assert receipt["activation_ready"] is False
    assert receipt["promotion_gate"]["automatic_activation_allowed"] is False
    assert "axio-pro" not in json.dumps(payload, ensure_ascii=False)


def test_cli_complete_binding_artifacts_emit_shadow_candidate(tmp_path: Path) -> None:
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    fusion_scores = tmp_path / "fusion_scores.json"
    baseline_scores = tmp_path / "baseline_scores.json"
    output = tmp_path / "result.json"
    _write_manifest(previous, "nvidia")
    _write_manifest(current, "cpa")
    fusion_scores.write_text(json.dumps({"axio-pro": 0.8}), encoding="utf-8")
    baseline_scores.write_text(json.dumps({"axio-pro": 1.0}), encoding="utf-8")
    names = ("registry", "rollback", "prompt_pack", "workflow", "contamination")
    binding_artifacts = {}
    for index, name in enumerate(names):
        path = tmp_path / f"{name}.json"
        path.write_text(f"binding-{index}", encoding="utf-8")
        binding_artifacts[name] = path

    payload = _run_cli(
        previous,
        current,
        output,
        fusion_scores=fusion_scores,
        baseline_scores=baseline_scores,
        binding_artifacts=binding_artifacts,
    )

    receipt = payload["recalibration_receipt"]
    assert receipt["status"] == "shadow_candidate"
    assert receipt["ready_for_review"] is True
    assert receipt["activation_ready"] is False
    assert receipt["blockers"] == []
    expected_digests = {
        key: hashlib.sha256(binding_artifacts[name].read_bytes()).hexdigest()
        for key, name in (
            ("registry_profile_set_sha256", "registry"),
            ("rollback_policy_digest_sha256", "rollback"),
            ("prompt_pack_digest_sha256", "prompt_pack"),
            ("workflow_digest_sha256", "workflow"),
            ("contamination_audit_digest_sha256", "contamination"),
        )
    }
    assert {
        key: receipt[key] for key in expected_digests
    } == expected_digests
    assert receipt["promotion_gate"]["automatic_activation_allowed"] is False


def test_cli_rejects_partial_binding_artifacts(tmp_path: Path) -> None:
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    output = tmp_path / "result.json"
    binding = tmp_path / "registry.json"
    _write_manifest(previous, "nvidia")
    _write_manifest(current, "cpa")
    binding.write_text("registry", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parent.parent
                / "scripts/run_adaptive_calibration.py"
            ),
            "--previous-manifest",
            str(previous),
            "--current-manifest",
            str(current),
            "--registry-binding-artifact",
            str(binding),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "五类校准绑定必须全部提供" in result.stderr
    assert not output.exists()
