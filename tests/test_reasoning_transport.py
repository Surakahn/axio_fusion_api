from __future__ import annotations

import sys
from pathlib import Path

import pytest


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.channel_config import build_runtime_profiles
from axio_fusion_api.compat import canonicalize_payload
from axio_fusion_api import providers as provider_module
from axio_fusion_api.orchestrator import _provider_request_for_role
from axio_fusion_api.providers import (
    HTTPProviderClient,
    ProviderCompletion,
    ProviderExecutionError,
    probe_provider_reasoning_support,
    redact_provider_reasoning_probe_artifact,
    reasoning_transport_probe_binding,
)
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.schemas import FusionRequest
from axio_fusion_api.provider_enrollment import _apply_runtime_reasoning_probe


def _profile(
    *,
    api_format: str,
    reasoning_transport: dict,
):
    return normalize_profile(
        {
            "provider": f"fixture-{api_format}",
            "model": f"{api_format}-model",
            "api_format": api_format,
            "reasoning_transport": reasoning_transport,
        }
    )


def test_public_payloads_normalize_native_reasoning_effort_before_fallbacks():
    chat = canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "HIGH",
            "reasoning": {"effort": "low"},
        },
        api_format="chat/completions",
    )
    responses = canonicalize_payload(
        {
            "model": "axio-terra",
            "input": "hello",
            "reasoning_effort": "low",
            "reasoning": {"effort": "medium"},
        },
        api_format="responses",
    )
    fallback = canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning": {"effort": "minimal"},
        },
        api_format="chat/completions",
    )
    invalid = canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "provider-private-ultra",
        },
        api_format="chat/completions",
    )

    assert chat.reasoning_effort == "high"
    assert responses.reasoning_effort == "medium"
    assert fallback.reasoning_effort == "minimal"
    assert invalid.reasoning_effort == ""


def test_reasoning_effort_partitions_request_fingerprint_and_safe_summary():
    base = FusionRequest(model="axio-fast", prompt="same task", reasoning_effort="low")
    stronger = FusionRequest(model="axio-fast", prompt="same task", reasoning_effort="high")

    assert base.request_fingerprint != stronger.request_fingerprint
    assert base.prompt_free_dict()["reasoning_effort"] == "low"
    assert stronger.prompt_free_dict()["reasoning_effort"] == "high"


def test_verified_chat_and_responses_profiles_use_only_their_own_wire_shape(monkeypatch):
    chat = _profile(
        api_format="chat",
        reasoning_transport={
            "status": "verified",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    responses = _profile(
        api_format="responses",
        reasoning_transport={
            "status": "verified",
            "transport": "responses_reasoning",
            "supported_efforts": ["low", "medium", "high"],
            "effort_map": {"xhigh": "high", "max": "high"},
        },
    )
    captured: dict[str, dict] = {}

    def fake_post(profile, path, payload, *, timeout, **kwargs):
        del path, timeout, kwargs
        captured[profile.api_format] = payload
        if profile.api_format == "chat":
            return {"choices": [{"message": {"content": "chat-ok"}}]}
        return {"output_text": "responses-ok"}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    client = HTTPProviderClient()
    chat_request = FusionRequest(model="axio-fast", prompt="hello", reasoning_effort="high")
    responses_request = FusionRequest(
        model="axio-terra",
        prompt="hello",
        reasoning_effort="max",
    )

    assert client.complete_turn(
        chat,
        chat_request,
        prompt=chat_request.prompt,
        system=chat_request.system,
    ).text == "chat-ok"
    assert client.complete_turn(
        responses,
        responses_request,
        prompt=responses_request.prompt,
        system=responses_request.system,
    ).text == "responses-ok"

    assert captured["chat"]["reasoning_effort"] == "high"
    assert "reasoning" not in captured["chat"]
    assert captured["responses"]["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in captured["responses"]
    assert responses.resolve_reasoning_transport("xhigh") == ("responses_reasoning", "high")
    assert responses.resolve_reasoning_transport("max") == ("responses_reasoning", "high")


def test_verified_nim_responses_profile_uses_top_level_reasoning_effort(monkeypatch):
    profile = normalize_profile(
        {
            "provider": "nvidia-responses-fixture",
            "model": "nvidia-responses-model",
            "api_format": "responses",
            "reasoning_transport": {
                "status": "verified",
                "transport": "responses_reasoning_effort",
                "supported_efforts": ["low", "medium", "high"],
            },
        }
    )
    captured: dict[str, dict] = {}

    def fake_post(_profile, _path, payload, *, timeout, **_kwargs):
        del timeout
        captured.update(payload)
        return {"output_text": "responses-ok"}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    request = FusionRequest(model="axio-pro", prompt="hello", reasoning_effort="high")

    assert HTTPProviderClient().complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system=request.system,
    ).text == "responses-ok"
    assert captured["reasoning_effort"] == "high"
    assert "reasoning" not in captured
    assert profile.resolve_reasoning_transport("high") == (
        "responses_reasoning_effort",
        "high",
    )


def test_candidate_or_protocol_mismatched_profile_omits_reasoning_fields(monkeypatch):
    candidate = _profile(
        api_format="chat",
        reasoning_transport={
            "status": "candidate",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    mismatched = _profile(
        api_format="responses",
        reasoning_transport={
            "status": "verified",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    captured: dict[str, dict] = {}

    def fake_post(profile, path, payload, *, timeout, **kwargs):
        del path, timeout, kwargs
        captured[profile.api_format] = payload
        if profile.api_format == "chat":
            return {"choices": [{"message": {"content": "chat-ok"}}]}
        return {"output_text": "responses-ok"}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    request = FusionRequest(model="axio-fast", prompt="hello", reasoning_effort="high")
    client = HTTPProviderClient()
    client.complete_turn(candidate, request, prompt=request.prompt, system=request.system)
    client.complete_turn(mismatched, request, prompt=request.prompt, system=request.system)

    assert "reasoning_effort" not in captured["chat"]
    assert "reasoning" not in captured["responses"]
    assert mismatched.safe_dict()["reasoning_transport"]["api_format_compatible"] is False


def test_runtime_channel_configuration_preserves_model_level_reasoning_transport():
    profiles = build_runtime_profiles(
        {
            "providers": [
                {
                    "provider": "runtime-responses",
                    "api_format": "responses",
                    "base_url": "https://runtime.fixture/v1",
                    "api_key": "runtime-test-key",
                    "models": [
                        {
                            "model": "runtime-model",
                            "reasoningTransport": {
                                "status": "verified",
                                "transport": "responses_reasoning",
                                "supportedEfforts": ["low", "medium", "high"],
                            },
                        }
                    ],
                }
            ]
        }
    )

    assert len(profiles) == 1
    assert profiles[0].resolve_reasoning_transport("medium") == (
        "responses_reasoning",
        "medium",
    )


def test_hermes_role_budget_is_capped_by_the_public_reasoning_effort():
    route_plan = {
        "strategy": "fusion",
        "hermes_moa": {
            "enabled": True,
            "stage_cognitive_budget": {
                "slots": {
                    "judge": {"reasoning_effort": "xhigh"},
                    "synthesizer": {"reasoning_effort": "high"},
                }
            },
        },
    }
    capped = FusionRequest(model="axio-pro", prompt="task", reasoning_effort="low")
    defaulted = FusionRequest(model="axio-pro", prompt="task")
    direct_route = {
        "strategy": "fast_direct_cascade",
        "hermes_moa": route_plan["hermes_moa"],
    }

    assert _provider_request_for_role(
        capped,
        "judge",
        route_plan=route_plan,
    ).reasoning_effort == "low"
    assert _provider_request_for_role(
        defaulted,
        "judge",
        route_plan=route_plan,
    ).reasoning_effort == "xhigh"
    assert _provider_request_for_role(
        capped,
        "primary_solver",
        route_plan=direct_route,
    ).reasoning_effort == "low"


class _ReasoningProbeClient:
    def __init__(self, *, reject_effort: str = "", control_fails: bool = False):
        self.reject_effort = reject_effort
        self.control_fails = control_fails
        self.calls: list[tuple[str, str]] = []

    def complete_turn(self, profile, request, *, prompt, system, timeout, strict_wire=False):
        del prompt, system, timeout
        assert strict_wire is True
        transport, effort = profile.resolve_reasoning_transport(request.reasoning_effort)
        self.calls.append((transport, effort))
        if self.control_fails and not effort:
            provider_module._record_provider_request_receipt(
                status="failed",
                key_attempt_count=1,
                transport_attempt_count=1,
                retry_attempt_count=0,
                stream_requested=True,
                strict_streaming_requested=True,
            )
            raise ProviderExecutionError("control failed", error_code="http_error", http_status=503)
        if self.reject_effort and effort == self.reject_effort:
            provider_module._record_provider_request_receipt(
                status="failed",
                key_attempt_count=1,
                transport_attempt_count=1,
                retry_attempt_count=0,
                stream_requested=True,
                strict_streaming_requested=True,
            )
            raise ProviderExecutionError("parameter rejected", error_code="http_error", http_status=400)
        provider_module._record_provider_request_receipt(
            status="success",
            key_attempt_count=1,
            transport_attempt_count=1,
            retry_attempt_count=0,
            stream_requested=True,
            stream_observed=True,
            stream_fallback_used=False,
            stream_protocol="sse",
            stream_content_type="text/event-stream",
            stream_frame_count=2,
            strict_streaming_requested=True,
        )
        return ProviderCompletion(provider_module.REASONING_PROBE_MARKER)


def test_reasoning_probe_uses_protocol_local_wire_controls_and_promotes_only_exact_profile():
    chat = _profile(
        api_format="chat",
        reasoning_transport={
            "status": "candidate",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    responses = _profile(
        api_format="responses",
        reasoning_transport={
            "status": "candidate",
            "transport": "responses_reasoning",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    client = _ReasoningProbeClient()

    report = probe_provider_reasoning_support(
        [chat, responses],
        live=True,
        client=client,
        max_workers=1,
    )

    assert report["verified_count"] == 2
    assert all(row["status"] == "verified" for row in report["probes"])
    assert report["candidate_profile_hashes"] == sorted(
        [
            provider_module.sha256_text(chat.profile_id),
            provider_module.sha256_text(responses.profile_id),
        ]
    )
    assert report["selected_profile_hashes"] == [
        provider_module.sha256_text(chat.profile_id),
        provider_module.sha256_text(responses.profile_id),
    ]
    assert report["candidate_profile_set_sha256"] == provider_module.sha256_text(
        provider_module.stable_json(report["candidate_profile_hashes"])
    )
    assert report["selected_profile_set_sha256"] == provider_module.sha256_text(
        provider_module.stable_json(sorted(report["selected_profile_hashes"]))
    )
    assert ("chat_reasoning_effort", "high") in client.calls
    assert ("responses_reasoning", "high") in client.calls
    assert ("", "") in client.calls

    updated = _apply_runtime_reasoning_probe([chat, responses], report["probes"])
    assert all(profile.reasoning_transport["status"] == "verified" for profile in updated)
    assert updated[0].resolve_reasoning_transport("high") == ("chat_reasoning_effort", "high")
    assert updated[1].resolve_reasoning_transport("high") == ("responses_reasoning", "high")


def test_reasoning_probe_accepts_explicit_responses_top_level_transport():
    profile = normalize_profile(
        {
            "provider": "nvidia-responses-probe-fixture",
            "model": "nvidia-responses-probe-model",
            "api_format": "responses",
            "reasoning_transport": {
                "status": "candidate",
                "transport": "responses_reasoning_effort",
                "supported_efforts": ["low", "high"],
            },
        }
    )
    client = _ReasoningProbeClient()

    report = probe_provider_reasoning_support(
        [profile],
        live=True,
        client=client,
        max_workers=1,
    )

    assert report["verified_count"] == 1
    assert ("responses_reasoning_effort", "low") in client.calls
    assert ("responses_reasoning_effort", "high") in client.calls
    updated = _apply_runtime_reasoning_probe([profile], report["probes"])
    assert updated[0].resolve_reasoning_transport("high") == (
        "responses_reasoning_effort",
        "high",
    )


def test_reasoning_probe_4xx_marks_only_parameterized_transport_unsupported():
    profile = _profile(
        api_format="responses",
        reasoning_transport={
            "status": "candidate",
            "transport": "responses_reasoning",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    report = probe_provider_reasoning_support(
        [profile],
        live=True,
        client=_ReasoningProbeClient(reject_effort="medium"),
        max_workers=1,
    )
    row = report["probes"][0]

    assert row["status"] == "rejected"
    assert row["control"]["status"] == "accepted"
    assert row["rejected_efforts"] == ["medium"]
    assert _apply_runtime_reasoning_probe([profile], [row])[0].reasoning_transport["status"] == "unsupported"


def test_reasoning_probe_captures_endpoint_before_requests_and_rejects_retargeted_result(
    monkeypatch,
):
    monkeypatch.setenv("REASONING_BINDING_BASE_URL", "https://binding-before.example/v1")
    monkeypatch.setenv("REASONING_BINDING_API_KEY", "fixture-key")
    profile = normalize_profile(
        {
            "provider": "binding-fixture",
            "model": "binding-model",
            "api_format": "chat",
            "base_url_env": "REASONING_BINDING_BASE_URL",
            "api_key_env": "REASONING_BINDING_API_KEY",
            "reasoning_transport": {
                "status": "candidate",
                "transport": "chat_reasoning_effort",
                "supported_efforts": ["low"],
            },
        }
    )
    binding_before = reasoning_transport_probe_binding(profile)

    class RetargetingClient(_ReasoningProbeClient):
        def complete_turn(self, *args, **kwargs):
            completion = super().complete_turn(*args, **kwargs)
            monkeypatch.setenv(
                "REASONING_BINDING_BASE_URL",
                "https://binding-after.example/v1",
            )
            return completion

    report = probe_provider_reasoning_support(
        [profile],
        live=True,
        client=RetargetingClient(),
        max_workers=1,
    )
    row = report["probes"][0]

    assert row["reasoning_transport_binding"]["binding_sha256"] == binding_before[
        "binding_sha256"
    ]
    assert row["reasoning_transport_binding"]["binding_sha256"] != reasoning_transport_probe_binding(
        profile
    )["binding_sha256"]
    assert _apply_runtime_reasoning_probe([profile], [row])[0].reasoning_transport[
        "status"
    ] == "candidate"


def test_reasoning_probe_control_failure_and_missing_rows_preserve_candidate_state():
    profile = _profile(
        api_format="chat",
        reasoning_transport={
            "status": "candidate",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    report = probe_provider_reasoning_support(
        [profile],
        live=True,
        client=_ReasoningProbeClient(control_fails=True),
        max_workers=1,
    )
    row = report["probes"][0]

    assert row["status"] == "indeterminate"
    assert row["control"]["status"] == "indeterminate"
    assert _apply_runtime_reasoning_probe([profile], [row])[0].reasoning_transport["status"] == "candidate"
    assert _apply_runtime_reasoning_probe([profile], [])[0].reasoning_transport["status"] == "candidate"


def test_runtime_reasoning_probe_rejects_missing_marker_and_slow_evidence():
    profile = _profile(
        api_format="chat",
        reasoning_transport={
            "status": "candidate",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low"],
        },
    )
    accepted = {
        "status": "accepted",
        "marker_observed": True,
        "strict_streaming_contract_valid": True,
        "stream_requested": True,
        "strict_streaming_requested": True,
        "stream_observed": True,
        "stream_fallback_used": False,
        "stream_protocol": "sse",
        "stream_frame_count": 1,
        "latency_ms": 12,
    }
    for invalid_control in (
        {**accepted, "marker_observed": False},
        {**accepted, "latency_ms": 90_001},
    ):
        row = {
            "profile_id": profile.profile_id,
            "probe_kind": "reasoning_transport",
            "status": "verified",
            "live_probe_evidence": True,
            "strict_wire_shape_preserved": True,
            "all_declared_efforts_strict_streaming": True,
            "transport": "chat_reasoning_effort",
            "declared_efforts": ["low"],
            "control": invalid_control,
            "effort_results": [{"effort": "low", **accepted}],
        }
        updated = _apply_runtime_reasoning_probe([profile], [row])
        assert updated[0].reasoning_transport["status"] == "candidate"


def test_reasoning_probe_redaction_removes_provider_model_prompt_and_output_details():
    payload = {
        "schema": "axio_fusion_api.provider_reasoning_probe.v1",
        "probe_kind": "reasoning_transport",
        "probes": [
            {
                "profile_id": "private-provider/private-model",
                "provider": "private-provider",
                "model": "private-model",
                "api_format": "responses",
                "status": "verified",
                "transport": "responses_reasoning",
                "declared_efforts": ["low"],
                "control": {
                    "status": "accepted",
                    "output_sha256": "output-hash",
                    "raw_prompt": "private prompt",
                    "raw_provider_output": "private answer",
                },
                "effort_results": [],
            }
        ],
    }
    redacted = redact_provider_reasoning_probe_artifact(payload)
    serialized = str(redacted)

    assert "private-provider" not in serialized
    assert "private-model" not in serialized
    assert "private prompt" not in serialized
    assert "private answer" not in serialized
    assert redacted["probes"][0]["raw_probe_prompt_persisted"] is False


def test_reasoning_probe_redaction_keeps_endpoint_binding_hash_without_endpoint_value():
    payload = {
        "schema": "axio_fusion_api.provider_reasoning_probe.v1",
        "probe_kind": "reasoning_transport",
        "probes": [
            {
                "profile_id": "private-provider/private-model",
                "provider": "private-provider",
                "model": "private-model",
                "reasoning_transport_binding": {
                    "schema": "axio_fusion_api.reasoning_transport_probe_binding.v1",
                    "profile_id_sha256": "profile-hash",
                    "canonical_identity_sha256": "canonical-hash",
                    "api_format": "responses",
                    "auth_scheme": "bearer",
                    "base_url_sha256": "endpoint-hash",
                    "endpoint_binding_ready": True,
                    "transport": "responses_reasoning",
                    "supported_efforts": ["low"],
                    "effort_map": {},
                    "api_format_compatible": True,
                    "binding_sha256": "binding-hash",
                    "raw_endpoint": "https://private-gateway.example/v1",
                    "api_key": "private-api-key",
                },
            }
        ],
    }

    redacted = redact_provider_reasoning_probe_artifact(payload)
    serialized = str(redacted)
    binding = redacted["probes"][0]["reasoning_transport_binding"]

    assert binding["base_url_sha256"] == "endpoint-hash"
    assert binding["endpoint_binding_ready"] is True
    assert "https://private-gateway.example" not in serialized
    assert "private-api-key" not in serialized
    assert "private-provider" not in serialized


def test_responses_strict_wire_does_not_retry_as_text_input_after_parameterized_4xx(monkeypatch):
    profile = _profile(
        api_format="responses",
        reasoning_transport={
            "status": "verified",
            "transport": "responses_reasoning",
            "supported_efforts": ["low", "medium", "high"],
        },
    )
    calls: list[dict] = []

    def fake_post(_profile, _path, payload, *, timeout, **_kwargs):
        del timeout
        calls.append(payload)
        raise ProviderExecutionError("field rejected", error_code="http_error", http_status=400)

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    request = FusionRequest(model="axio-fast", prompt="hello", reasoning_effort="high")
    with pytest.raises(ProviderExecutionError):
        HTTPProviderClient().complete_turn(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            strict_wire=True,
        )

    assert len(calls) == 1
    assert isinstance(calls[0]["input"], list)
    assert calls[0]["reasoning"] == {"effort": "high"}


def test_reasoning_transport_does_not_invent_native_efforts_or_escalate_maps():
    profile = _profile(
        api_format="chat",
        reasoning_transport={
            "status": "verified",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["medium"],
            "effort_map": {"low": "medium", "max": "medium"},
        },
    )

    assert profile.resolve_reasoning_transport("medium") == (
        "chat_reasoning_effort",
        "medium",
    )
    assert profile.resolve_reasoning_transport("low") == ("", "")
    assert profile.resolve_reasoning_transport("high") == ("", "")
    assert profile.resolve_reasoning_transport("max") == (
        "chat_reasoning_effort",
        "medium",
    )


def test_reasoning_transport_for_wrong_protocol_is_not_sendable():
    profile = _profile(
        api_format="responses",
        reasoning_transport={
            "status": "verified",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["high"],
        },
    )

    assert profile.reasoning_transport["api_format_compatible"] is False
    assert profile.resolve_reasoning_transport("high") == ("", "")
