from __future__ import annotations

import json

import pytest

from axio_fusion_api.providers import (
    ProviderCompletion,
    _record_provider_request_receipt,
)
from axio_fusion_api.calibration import build_registry_calibration
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.vision_probe import (
    VISION_PROBE_MARKER,
    build_vision_probe_bound_registry,
    probe_provider_vision_support,
    redact_vision_probe_artifact,
    vision_input_probe_binding,
    vision_input_probe_status,
)


class _FakeVisionClient:
    def __init__(
        self,
        *,
        text: str = VISION_PROBE_MARKER,
        stream_observed: bool = True,
        stream_fallback_used: bool = False,
        stream_protocol: str = "sse",
        stream_frame_count: int | None = None,
    ):
        self.text = text
        self.stream_observed = stream_observed
        self.stream_fallback_used = stream_fallback_used
        self.stream_protocol = stream_protocol
        self.stream_frame_count = stream_frame_count
        self.requests = []

    def complete_turn(self, profile, request, **kwargs):
        self.requests.append((profile, request, dict(kwargs)))
        _record_provider_request_receipt(
            status="success",
            key_attempt_count=1,
            transport_attempt_count=1,
            retry_attempt_count=0,
            stream_requested=True,
            stream_observed=self.stream_observed,
            stream_fallback_used=self.stream_fallback_used,
            stream_protocol=self.stream_protocol,
            stream_frame_count=(
                self.stream_frame_count
                if self.stream_frame_count is not None
                else (2 if self.stream_observed else 0)
            ),
            strict_streaming_requested=True,
        )
        return ProviderCompletion(self.text)


def _profile(api_format: str, *, provider: str = "vision-provider"):
    return normalize_profile(
        {
            "provider": provider,
            "model": f"vision-{api_format}",
            "api_format": api_format,
            "supports_vision": True,
            "base_url_env": "VISION_TEST_BASE_URL",
            "api_key_env": "VISION_TEST_API_KEY",
            "capabilities": {"daily_work": 0.8, "structured_output": 0.8},
        }
    )


def test_vision_probe_requires_live_and_selects_only_declared_text_candidates():
    profiles = [
        _profile("chat/completions"),
        normalize_profile(
            {
                "provider": "text-only",
                "model": "text-only",
                "api_format": "chat/completions",
                "supports_vision": False,
            }
        ),
        normalize_profile(
            {
                "provider": "image-only",
                "model": "gpt-image-2",
                "api_format": "responses",
                "supports_vision": True,
                "model_kind": "image",
            }
        ),
    ]

    payload = probe_provider_vision_support(profiles, live=False)

    assert payload["model_count"] == 1
    assert payload["passed_count"] == 0
    assert payload["probes"][0]["status"] == "skipped"
    assert payload["network_calls_performed"] is False


@pytest.mark.parametrize(
    ("api_format", "expected_transport"),
    [
        ("chat/completions", "chat_image_url"),
        ("responses", "responses_input_image"),
        ("anthropic", "anthropic_image_base64"),
        ("gemini", "gemini_inline_data"),
    ],
)
def test_vision_probe_requires_exact_marker_and_strict_stream(api_format, expected_transport):
    client = _FakeVisionClient()
    payload = probe_provider_vision_support(
        [_profile(api_format)],
        live=True,
        client=client,
    )

    row = payload["probes"][0]
    assert row["status"] == "passed"
    assert row["marker_valid"] is True
    assert row["stream_observed"] is True
    assert row["strict_streaming_requested"] is True
    assert row["vision_transport"] == expected_transport
    assert client.requests[0][1].has_visual_input is True
    assert client.requests[0][2]["strict_wire"] is True


def test_vision_probe_rejects_text_only_or_unframed_responses():
    wrong_marker = probe_provider_vision_support(
        [_profile("chat")],
        live=True,
        client=_FakeVisionClient(text="AXIO_VISION_COLOR_RED"),
    )
    unframed = probe_provider_vision_support(
        [_profile("responses", provider="unframed")],
        live=True,
        client=_FakeVisionClient(stream_observed=False),
    )

    assert wrong_marker["probes"][0]["status"] == "failed"
    assert wrong_marker["probes"][0]["reason_code"] == "visual_marker_invalid"
    assert unframed["probes"][0]["status"] == "failed"
    assert unframed["probes"][0]["reason_code"] == "strict_stream_not_observed"


@pytest.mark.parametrize(
    ("client_kwargs", "reason_code"),
    [
        ({"stream_fallback_used": True}, "ordinary_json_stream_fallback_used"),
        ({"stream_protocol": "json"}, "stream_protocol_unverified"),
        ({"stream_frame_count": 0}, "stream_frame_evidence_missing"),
    ],
)
def test_vision_probe_rejects_non_strict_stream_evidence(client_kwargs, reason_code):
    payload = probe_provider_vision_support(
        [_profile("responses")],
        live=True,
        client=_FakeVisionClient(**client_kwargs),
    )

    row = payload["probes"][0]
    assert row["status"] == "failed"
    assert row["reason_code"] == reason_code


def test_vision_probe_treats_slow_response_as_reprobeable_not_unsupported(monkeypatch):
    monkeypatch.setattr(
        "axio_fusion_api.vision_probe._elapsed_ms",
        lambda _started: 90_001.0,
    )
    profile = _profile("responses")
    payload = probe_provider_vision_support(
        [profile],
        live=True,
        client=_FakeVisionClient(),
    )

    row = payload["probes"][0]
    assert row["status"] == "latency_ineligible"
    assert row["reason_code"] == "provider_response_latency_exceeded_90s"
    assert vision_input_probe_status(profile, [row]) == "indeterminate"


def test_redacted_vision_probe_does_not_persist_identifiers_or_probe_material():
    client = _FakeVisionClient()
    payload = probe_provider_vision_support(
        [_profile("chat")],
        live=True,
        client=client,
    )
    redacted = redact_vision_probe_artifact(payload)
    serialized = json.dumps(redacted, ensure_ascii=False)

    assert "vision-provider" not in serialized
    assert "vision-chat/completions" not in serialized
    assert VISION_PROBE_MARKER not in serialized
    assert redacted["probes"][0]["profile_id_sha256"]
    assert redacted["raw_image_bytes_persisted"] is False
    assert redacted["raw_probe_prompt_persisted"] is False


def test_vision_probe_binding_promotes_only_matching_endpoint_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_TEST_BASE_URL", "https://vision.example.test/v1")
    profile = _profile("chat/completions")
    source_path = tmp_path / "source.json"
    probe_path = tmp_path / "probe.json"
    output_path = tmp_path / "bound.json"
    source_path.write_text(
        json.dumps({"schema": "axio_fusion_api.registry.v1", "models": [profile.safe_dict()]}),
        encoding="utf-8",
    )
    probe = probe_provider_vision_support([profile], live=True, client=_FakeVisionClient())
    probe_path.write_text(json.dumps(probe), encoding="utf-8")

    bound = build_vision_probe_bound_registry(
        registry_path=source_path,
        probe_path=probe_path,
    )
    output_path.write_text(json.dumps(bound["registry"]), encoding="utf-8")

    assert bound["status"] == "ready"
    assert bound["receipt"]["promoted_profile_count"] == 1
    assert bound["registry"]["vision_capability_registry_ready"] is True
    promoted = bound["registry"]["models"][0]
    assert promoted["vision_probe_status"] == "passed"
    assert promoted["vision_capability_source"] == "operational_probe"


def test_vision_probe_binding_fails_closed_when_endpoint_binding_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_TEST_BASE_URL", "https://vision.example.test/v1")
    profile = _profile("responses")
    source_path = tmp_path / "source.json"
    probe_path = tmp_path / "probe.json"
    source_path.write_text(
        json.dumps({"schema": "axio_fusion_api.registry.v1", "models": [profile.safe_dict()]}),
        encoding="utf-8",
    )
    probe = probe_provider_vision_support([profile], live=True, client=_FakeVisionClient())
    probe["probes"][0]["endpoint_binding"] = vision_input_probe_binding(
        normalize_profile(
            {
                "provider": profile.provider,
                "model": profile.model,
                "api_format": profile.api_format,
                "supports_vision": True,
                "base_url_env": "VISION_TEST_BASE_URL_2",
            }
        )
    )
    probe_path.write_text(json.dumps(probe), encoding="utf-8")

    bound = build_vision_probe_bound_registry(
        registry_path=source_path,
        probe_path=probe_path,
    )

    assert bound["status"] == "blocked"
    assert "vision_probe_endpoint_binding_mismatch" in bound["receipt"]["blockers"]
    assert bound["registry"]["vision_capability_registry_ready"] is False


def test_calibration_preserves_quality_scores_while_recording_vision_capability(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("VISION_TEST_BASE_URL", "https://vision.example.test/v1")
    profile = _profile("responses")
    source_path = tmp_path / "source.json"
    probe_path = tmp_path / "vision_probe.json"
    source_path.write_text(
        json.dumps({"schema": "axio_fusion_api.registry.v1", "models": [profile.safe_dict()]}),
        encoding="utf-8",
    )
    probe_path.write_text(
        json.dumps(
            probe_provider_vision_support(
                [profile],
                live=True,
                client=_FakeVisionClient(),
            )
        ),
        encoding="utf-8",
    )

    calibration = build_registry_calibration(
        registry_path=source_path,
        probe_paths=[probe_path],
    )

    patch = calibration["patches"][0]
    updated = calibration["updated_registry"]["models"][0]
    assert calibration["input_artifacts"]["vision_probe_row_count"] == 1
    assert patch["capabilities_patch"] == {}
    assert patch["vision_input_patch"]["vision_probe_status"] == "passed"
    assert updated["capabilities"] == profile.safe_dict()["capabilities"]
    assert updated["vision_probe_status"] == "passed"
    assert updated["vision_capability_source"] == "operational_probe"
