from __future__ import annotations

import json

import pytest

from axio_fusion_api.cli import main as fusion_cli_main
from axio_fusion_api.model_screening import (
    ModelScreeningError,
    build_prefusion_probe_artifact,
)
from axio_fusion_api.schemas import sha256_text


def _screening_payload(*, mode: str = "live", status: str = "ready") -> dict:
    rows = [
        {
            "profile_id": "fixture-provider/fixture-model-a",
            "provider": "fixture-provider",
            "model": "fixture-model-a",
            "api_format": "chat",
            "status": "available",
            "probe_mode": "live",
            "live_probe_evidence": True,
            "output_sha256": sha256_text("fixture-a"),
            "stream_requested": True,
            "stream_observed": True,
            "stream_fallback_used": False,
            "stream_protocol": "sse",
            "stream_frame_count": 2,
            "raw_provider_output_persisted": False,
            "secrets_persisted": False,
        },
        {
            "profile_id": "fixture-provider/fixture-model-b",
            "provider": "fixture-provider",
            "model": "fixture-model-b",
            "api_format": "responses",
            "status": "available",
            "probe_mode": "live",
            "live_probe_evidence": True,
            "output_sha256": sha256_text("fixture-b"),
            "stream_requested": True,
            "stream_observed": True,
            "stream_fallback_used": False,
            "stream_protocol": "sse",
            "stream_frame_count": 2,
            "raw_provider_output_persisted": False,
            "secrets_persisted": False,
        },
    ]
    return {
        "schema": "axio_fusion_api.pre_fusion_model_screening.v1",
        "status": status,
        "streaming_probe": {
            "mode": mode,
            "network_calls_performed": mode == "live",
            "model_count": len(rows),
            "candidate_model_count_before_selection": len(rows),
            "available_count": len(rows),
            "max_response_seconds": 90.0,
            "max_response_latency_ms": 90_000,
            "samples_per_profile": 3,
            "probes": rows,
        },
        "provider_discovery": {
            "provider_reports": [
                {
                    "provider": "fixture-provider",
                    "status": "ok",
                    "model_count": 2,
                    "model_ids": ["fixture-model-a", "fixture-model-b"],
                    "base_url_sha256": sha256_text("https://fixture.invalid/v1"),
                    "raw_provider_response_persisted": False,
                    "secrets_persisted": False,
                }
            ]
        },
        "secrets_persisted": False,
        "raw_provider_output_persisted": False,
    }


def test_prefusion_probe_export_preserves_live_probe_contract_without_network():
    payload = build_prefusion_probe_artifact(_screening_payload())

    assert payload["schema"] == "axio_fusion_api.provider_probe.v1"
    assert payload["generated_from_prefusion_screening"] is True
    assert payload["network_calls_performed"] is True
    assert payload["model_count"] == 2
    assert payload["available_count"] == 2
    assert len(payload["probes"]) == 2
    assert len(payload["provider_reports"]) == 1
    assert payload["source_screening_content_sha256"]
    assert payload["raw_provider_output_persisted"] is False
    assert payload["secrets_persisted"] is False


def test_prefusion_probe_export_redaction_and_cli_round_trip(tmp_path):
    screening_path = tmp_path / "screening.private.json"
    output_path = tmp_path / "probe.safe.json"
    screening_path.write_text(
        json.dumps(_screening_payload()), encoding="utf-8"
    )

    assert (
        fusion_cli_main(
            [
                "prefusion-probe-export",
                "--screening-file",
                str(screening_path),
                "--redact-provider-identifiers",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["generated_from_prefusion_screening"] is True
    assert payload["provider_identifier_redaction"]["enabled"] is True
    assert payload["available_count"] == 2
    assert payload["provider_reports"][0]["model_count"] == 2
    assert "fixture-provider" not in serialized
    assert "fixture-model-a" not in serialized
    assert "fixture-model-b" not in serialized
    assert payload["raw_provider_output_persisted"] is False
    assert payload["secrets_persisted"] is False


@pytest.mark.parametrize(
    "payload, error_code",
    [
        (_screening_payload(mode="dry_run"), "prefusion_probe_export_requires_live_streaming"),
        (_screening_payload(status="blocked"), "prefusion_probe_export_screening_not_ready"),
    ],
)
def test_prefusion_probe_export_rejects_non_live_or_blocked_inputs(payload, error_code):
    with pytest.raises(ModelScreeningError, match=error_code):
        build_prefusion_probe_artifact(payload)
