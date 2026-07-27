from __future__ import annotations

import sys
from pathlib import Path


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.channel_config import build_runtime_profiles
from axio_fusion_api.compat import canonicalize_payload
from axio_fusion_api import providers as provider_module
from axio_fusion_api.orchestrator import _provider_request_for_role
from axio_fusion_api.providers import HTTPProviderClient
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.schemas import FusionRequest


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
            "effort_map": {"xhigh": "high"},
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
        reasoning_effort="xhigh",
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
