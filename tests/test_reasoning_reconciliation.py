from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.cli import main as fusion_cli_main
from axio_fusion_api.providers import reasoning_transport_probe_binding
from axio_fusion_api.reasoning_reconciliation import (
    apply_reasoning_transport_reconciliation,
    build_reasoning_transport_reconciliation,
)
from axio_fusion_api.registry import normalize_profile


def _profile(*, status: str = "candidate"):
    return normalize_profile(
        {
            "provider": "reasoning-reconcile-provider",
            "model": "reasoning-reconcile-model",
            "canonical_model_id": "reasoning-reconcile-family-v1",
            "api_format": "responses",
            "base_url_env": "RECONCILE_BASE_URL",
            "api_key_env": "RECONCILE_API_KEY",
            "reasoning_transport": {
                "status": status,
                "transport": "responses_reasoning",
                "supported_efforts": ["low", "medium"],
                "effort_map": {"high": "medium"},
            },
        }
    )


def _registry(profile) -> dict:
    row = profile.safe_dict()
    row["canonical_model_id"] = profile.canonical_model_id
    return {
        "schema": "axio_fusion_api.registry.v1",
        "models": [row],
        "model_count": 1,
        "readiness": {"status": "ready", "ready": True},
        "secrets_persisted": False,
    }


def _accepted_attempt() -> dict:
    return {
        "status": "accepted",
        "marker_observed": True,
        "strict_streaming_contract_valid": True,
        "stream_requested": True,
        "strict_streaming_requested": True,
        "stream_observed": True,
        "stream_fallback_used": False,
        "stream_protocol": "sse",
        "stream_frame_count": 2,
        "latency_ms": 12,
    }


def _probe(profile, *, binding: dict | None = None) -> dict:
    attempt = _accepted_attempt()
    return {
        "schema": "axio_fusion_api.provider_reasoning_probe.v1",
        "probe_kind": "reasoning_transport",
        "mode": "live",
        "network_calls_performed": True,
        "timeout_seconds": 90,
        "candidate_model_count_before_selection": 1,
        "model_count": 1,
        "selection_policy": {
            "profile_hash_filter_enabled": False,
            "max_models": None,
            "max_models_per_provider": None,
            "selected_model_count": 1,
        },
        "probes": [
            {
                "profile_id": profile.profile_id,
                "provider": profile.provider,
                "model": profile.model,
                "api_format": profile.api_format,
                "probe_kind": "reasoning_transport",
                "probe_mode": "live",
                "live_probe_evidence": True,
                "status": "verified",
                "strict_wire_shape_preserved": True,
                "all_declared_efforts_strict_streaming": True,
                "transport": "responses_reasoning",
                "declared_efforts": ["low", "medium"],
                "control": attempt,
                "effort_results": [
                    {"effort": "low", **attempt},
                    {"effort": "medium", **attempt},
                ],
                "reasoning_transport_binding": binding
                if binding is not None
                else reasoning_transport_probe_binding(profile),
            }
        ],
        "secrets_persisted": False,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("RECONCILE_BASE_URL", "https://reconcile.example/v1")
    monkeypatch.setenv("RECONCILE_API_KEY", "fixture-key")
    source_profile = _profile(status="candidate")
    calibration_profile = _profile(status="verified")
    source_path = tmp_path / "source.private.json"
    calibration_path = tmp_path / "calibration.private.json"
    probe_path = tmp_path / "probe.private.json"
    _write_json(source_path, _registry(source_profile))
    _write_json(calibration_path, _registry(calibration_profile))
    _write_json(probe_path, _probe(source_profile))
    return source_profile, source_path, calibration_path, probe_path


def test_reconciliation_updates_only_endpoint_bound_reasoning_status(tmp_path, monkeypatch):
    profile, source_path, calibration_path, probe_path = _artifacts(tmp_path, monkeypatch)
    original_source = source_path.read_text(encoding="utf-8")

    reconciliation = build_reasoning_transport_reconciliation(
        source_registry_path=source_path,
        calibration_registry_path=calibration_path,
        reasoning_probe_path=probe_path,
    )

    receipt = reconciliation["receipt"]
    updated = reconciliation["updated_registry"]
    assert receipt["status"] == "ready"
    assert receipt["updated_profile_count"] == 1
    assert receipt["outcome_status_counts"]["verified"] == 1
    assert updated["models"][0]["reasoning_transport"]["status"] == "verified"
    assert updated["models"][0]["canonical_model_id"] == profile.canonical_model_id
    assert updated["reasoning_transport_reconciliation"]["model_ranking_changed"] is False
    assert updated["reasoning_transport_reconciliation"]["benchmark_results_used"] is False
    assert source_path.read_text(encoding="utf-8") == original_source

    output_path = tmp_path / "reconciled.private.json"
    applied = apply_reasoning_transport_reconciliation(
        reconciliation,
        source_registry_path=source_path,
        output_registry_path=output_path,
    )
    serialized = json.dumps(applied, ensure_ascii=False)
    assert applied["status"] == "ready"
    assert applied["registry_output_written"] is True
    assert output_path.is_file()
    assert "https://reconcile.example" not in serialized
    assert "fixture-key" not in serialized


def test_reconciliation_rejects_probe_when_endpoint_has_changed(tmp_path, monkeypatch):
    profile, source_path, calibration_path, probe_path = _artifacts(tmp_path, monkeypatch)
    old_binding = reasoning_transport_probe_binding(profile)
    _write_json(probe_path, _probe(profile, binding=old_binding))
    monkeypatch.setenv("RECONCILE_BASE_URL", "https://retargeted.example/v1")

    reconciliation = build_reasoning_transport_reconciliation(
        source_registry_path=source_path,
        calibration_registry_path=calibration_path,
        reasoning_probe_path=probe_path,
    )

    assert reconciliation["receipt"]["status"] == "blocked"
    assert "reasoning_reconciliation_probe_endpoint_binding_mismatch" in reconciliation["receipt"]["blockers"]
    assert reconciliation["updated_registry"] == {}
    output_path = tmp_path / "must-not-write.private.json"
    applied = apply_reasoning_transport_reconciliation(
        reconciliation,
        source_registry_path=source_path,
        output_registry_path=output_path,
    )
    assert applied["status"] == "blocked"
    assert applied["registry_output_written"] is False
    assert not output_path.exists()


def test_reconciliation_rejects_nonpositive_probe_timeout(tmp_path, monkeypatch):
    profile, source_path, calibration_path, probe_path = _artifacts(tmp_path, monkeypatch)
    invalid_timeout_probe = _probe(profile)
    invalid_timeout_probe["timeout_seconds"] = 0
    _write_json(probe_path, invalid_timeout_probe)

    reconciliation = build_reasoning_transport_reconciliation(
        source_registry_path=source_path,
        calibration_registry_path=calibration_path,
        reasoning_probe_path=probe_path,
    )

    assert reconciliation["receipt"]["status"] == "blocked"
    assert "reasoning_reconciliation_probe_timeout_invalid" in reconciliation["receipt"][
        "blockers"
    ]


def test_reconciliation_rejects_legacy_unbound_probe_and_in_place_output(tmp_path, monkeypatch):
    profile, source_path, calibration_path, probe_path = _artifacts(tmp_path, monkeypatch)
    legacy_probe = _probe(profile)
    legacy_probe["probes"][0].pop("reasoning_transport_binding")
    _write_json(probe_path, legacy_probe)

    reconciliation = build_reasoning_transport_reconciliation(
        source_registry_path=source_path,
        calibration_registry_path=calibration_path,
        reasoning_probe_path=probe_path,
    )
    assert reconciliation["receipt"]["status"] == "blocked"
    assert "reasoning_reconciliation_probe_endpoint_binding_missing" in reconciliation["receipt"]["blockers"]

    valid_probe = _probe(profile)
    _write_json(probe_path, valid_probe)
    ready = build_reasoning_transport_reconciliation(
        source_registry_path=source_path,
        calibration_registry_path=calibration_path,
        reasoning_probe_path=probe_path,
    )
    applied = apply_reasoning_transport_reconciliation(
        ready,
        source_registry_path=source_path,
        output_registry_path=source_path,
    )
    assert applied["status"] == "blocked"
    assert "reasoning_reconciliation_in_place_overwrite_forbidden" in applied["blockers"]


def test_reconciliation_cli_writes_only_safe_receipt_and_private_registry(tmp_path, monkeypatch):
    _, source_path, calibration_path, probe_path = _artifacts(tmp_path, monkeypatch)
    output_registry = tmp_path / "reconciled.private.json"
    receipt_path = tmp_path / "reconciliation.safe.json"

    assert fusion_cli_main(
        [
            "reconcile-reasoning-transport",
            "--source-registry",
            str(source_path),
            "--calibration-registry",
            str(calibration_path),
            "--reasoning-probe",
            str(probe_path),
            "--output-registry",
            str(output_registry),
            "--output",
            str(receipt_path),
        ]
    ) == 0

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    serialized = json.dumps(receipt, ensure_ascii=False)
    assert receipt["status"] == "ready"
    assert receipt["registry_output_written"] is True
    assert output_registry.is_file()
    assert "reasoning-reconcile-provider" not in serialized
    assert "reasoning-reconcile-model" not in serialized
    assert "https://reconcile.example" not in serialized
    assert "fixture-key" not in serialized
