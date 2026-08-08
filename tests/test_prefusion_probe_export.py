from __future__ import annotations

import json

import pytest

from axio_fusion_api.cli import main as fusion_cli_main
from axio_fusion_api import model_screening
from axio_fusion_api.model_screening import (
    ModelScreeningError,
    build_prefusion_generation_probe_artifact,
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


def _generation_payload() -> dict:
    models = []
    bindings = []
    for api_format, model in (("chat", "fixture-chat"), ("responses", "fixture-responses")):
        profile_id = f"fixture-provider/{model}"
        models.append(
            {
                "profile_id": profile_id,
                "provider": "fixture-provider",
                "model": model,
                "api_format": api_format,
                "model_kind": "text",
            }
        )
        bindings.append(
            {
                "profile_id_sha256": sha256_text(profile_id),
                "status": "available",
                "probe_mode": "live",
                "live_probe_evidence": True,
                "output_sha256": sha256_text(f"output:{model}"),
                "latency_ms": 120,
                "p50_latency_ms": 100,
                "p95_latency_ms": 140,
                "latency_eligibility": {"eligible": True},
                "stream_requested": True,
                "strict_streaming_requested": True,
                "stream_observed": True,
                "stream_fallback_used": False,
                "stream_protocol": "sse",
                "stream_frame_count": 2,
                "stability_sample_count": 3,
                "stability_completed_sample_count": 3,
                "stability_success_count": 3,
                "stability_failure_count": 0,
                "stability_success_rate": 1.0,
                "all_samples_eligible": True,
                "sample_receipts_sha256": sha256_text(f"samples:{model}"),
            }
        )
    registry = {
        "schema": "axio_fusion_api.registry.v1",
        "generated_from_prefusion_screening": True,
        "binding_status": "ready",
        "models": models,
        "prefusion_screening": {
            "screening_status": "ready",
            "max_response_seconds": 90.0,
            "multi_sample_stream_stability_required": True,
            "stream_stability_contract": {
                "schema": "axio_fusion_api.provider_probe_stability_contract.v1",
                "samples_per_profile": 3,
                "requires_all_samples_success": True,
                "requires_each_sample_latency_at_or_below_90_seconds": True,
                "requires_each_sample_strict_streaming": True,
            },
            "eligible_profile_bindings": bindings,
        },
    }
    return {
        "schema": "axio_fusion_api.available_model_generation.v1",
        "status": "ready",
        "provider_catalog_attestation": {
            "schema": "axio_fusion_api.provider_catalog_attestation.v1",
            "status": "ready",
            "source": "prefusion_provider_discovery",
            "network_calls_performed": True,
            "provider_report_count": 1,
            "provider_reports": [
                {
                    "provider": "fixture-provider",
                    "model_ids": ["fixture-chat", "fixture-responses"],
                    "status": "ok",
                    "model_count": 2,
                    "base_url_sha256": sha256_text("https://fixture.invalid/v1"),
                    "models_endpoint": "/models",
                    "network_calls_performed": True,
                    "raw_provider_response_persisted": False,
                    "secrets_persisted": False,
                }
            ],
            "raw_provider_response_persisted": False,
            "raw_provider_body_persisted": False,
            "secrets_persisted": False,
        },
        "fusion_handoff": {
            "status": "ready",
            "private_registry_included": True,
            "fusion_registry": registry,
        },
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


def test_generation_probe_export_revalidates_nested_bindings_and_redacts(
    monkeypatch,
):
    monkeypatch.setattr(
        model_screening,
        "validate_prefusion_registry_handoff",
        lambda payload, require_ready: {"valid": True, "reason_codes": []},
    )
    generation = _generation_payload()

    payload = build_prefusion_generation_probe_artifact(generation)

    assert payload["schema"] == "axio_fusion_api.provider_probe.v1"
    assert payload["generated_from_available_model_generation"] is True
    assert payload["source_projection"] == "nested_prefusion_registry_bindings"
    assert payload["network_calls_performed"] is True
    assert payload["projection_network_calls_performed"] is False
    assert payload["available_count"] == 2
    assert len(payload["probes"]) == 2
    assert all(row["stream_protocol"] == "sse" for row in payload["probes"])
    assert len(payload["provider_reports"]) == 1
    assert payload["provider_catalog_attestation"]["status"] == "ready"

    redacted = build_prefusion_generation_probe_artifact(
        generation,
        redact_provider_identifiers=True,
    )
    serialized = json.dumps(redacted, ensure_ascii=False)
    assert "fixture-provider" not in serialized
    assert "fixture-chat" not in serialized
    assert redacted["provider_identifier_redaction"]["enabled"] is True
    assert redacted["projection_network_calls_performed"] is False
    assert redacted["secrets_persisted"] is False
    redacted_serialized = json.dumps(redacted["provider_catalog_attestation"])
    assert "fixture-provider" not in redacted_serialized
    assert "fixture-chat" not in redacted_serialized


def test_generation_probe_export_cli_is_offline_and_schema_explicit(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        model_screening,
        "validate_prefusion_registry_handoff",
        lambda payload, require_ready: {"valid": True, "reason_codes": []},
    )
    generation_path = tmp_path / "generation.json"
    output_path = tmp_path / "probe.safe.json"
    generation_path.write_text(
        json.dumps(_generation_payload()),
        encoding="utf-8",
    )

    assert (
        fusion_cli_main(
            [
                "prefusion-generation-probe-export",
                "--generation-file",
                str(generation_path),
                "--redact-provider-identifiers",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["generated_from_available_model_generation"] is True
    assert payload["projection_network_calls_performed"] is False
    assert payload["available_count"] == 2


@pytest.mark.parametrize(
    "mutator, error_code",
    [
        (
            lambda value: value.update({"status": "blocked"}),
            "prefusion_generation_probe_export_generation_not_ready",
        ),
        (
            lambda value: value["fusion_handoff"].update({"status": "blocked"}),
            "prefusion_generation_probe_export_handoff_not_ready",
        ),
    ],
)
def test_generation_probe_export_rejects_non_ready_wrappers(mutator, error_code):
    payload = _generation_payload()
    mutator(payload)
    with pytest.raises(ModelScreeningError, match=error_code):
        build_prefusion_generation_probe_artifact(payload)
