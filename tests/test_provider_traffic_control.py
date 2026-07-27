from __future__ import annotations

from datetime import datetime, timezone
from email.message import Message
from email.utils import format_datetime
import io
import sys
from pathlib import Path
import urllib.error

import pytest


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api import baseline_screening
from axio_fusion_api import providers as provider_module
from axio_fusion_api.channel_config import build_runtime_profiles
from axio_fusion_api.providers import HTTPProviderClient, ProviderExecutionError
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.schemas import FusionRequest, safe_provider_error_class


@pytest.fixture(autouse=True)
def _reset_process_local_transport_state(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "off")
    with provider_module._PROVIDER_TRAFFIC_GATE_CONDITION:
        provider_module._PROVIDER_TRAFFIC_GATES.clear()
    with provider_module._PROVIDER_KEY_ROTATION_LOCK:
        provider_module._PROVIDER_KEY_ROTATION_CURSORS.clear()


class _SseResponse:
    def __init__(self, text: str = "ok") -> None:
        self._lines = iter(
            [
                ('data: {"choices":[{"delta":{"content":"' + text + '"}}]}\n').encode(),
                b"\n",
                b"data: [DONE]\n",
                b"\n",
            ]
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getheader(self, name: str):
        return "text/event-stream" if name.casefold() == "content-type" else ""

    def readline(self):
        return next(self._lines, b"")


def _install_fake_opener(monkeypatch, callback) -> None:
    class FakeOpener:
        def open(self, request, timeout=None):
            return callback(request, timeout=timeout)

    monkeypatch.setattr(
        provider_module.urllib.request,
        "build_opener",
        lambda *_handlers: FakeOpener(),
    )


def _profile(
    *,
    model: str = "fixture-model",
    traffic_control: dict | None = None,
):
    return normalize_profile(
        {
            "provider": "fixture-channel",
            "model": model,
            "api_format": "chat",
            "base_url_env": "TRAFFIC_FIXTURE_BASE_URL",
            "api_key_env": "TRAFFIC_FIXTURE_KEYS",
            "traffic_control": traffic_control or {},
        }
    )


def _request() -> FusionRequest:
    return FusionRequest(model="axio-fast", prompt="return a concise answer")


def _rate_limited_error(
    request,
    *,
    retry_after: str | None = "0",
) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        request.full_url,
        429,
        "rate limited",
        headers,
        io.BytesIO(b'{"private":"provider body"}'),
    )


def test_shared_key_pool_stops_after_first_429_and_keeps_safe_trace(monkeypatch):
    monkeypatch.setenv("TRAFFIC_FIXTURE_BASE_URL", "https://traffic.fixture/v1")
    monkeypatch.setenv("TRAFFIC_FIXTURE_KEYS", "first-fixture-key,second-fixture-key")
    calls: list[str] = []

    def callback(request, *, timeout):
        del timeout
        authorization = dict(request.header_items()).get("Authorization", "")
        calls.append(authorization)
        raise _rate_limited_error(request)

    _install_fake_opener(monkeypatch, callback)
    profile = _profile(
        traffic_control={
            "scope": "channel",
            "rate_limit_key_pool": "shared",
            "fallback_cooldown_ms": 50,
            "max_cooldown_ms": 50,
        }
    )
    request = _request()
    provider_module._begin_provider_request_trace()

    with pytest.raises(ProviderExecutionError) as exc_info:
        HTTPProviderClient().complete_turn(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=1.0,
        )
    receipt = provider_module._finish_provider_request_trace()

    assert exc_info.value.error_code == "http_error"
    assert exc_info.value.http_status == 429
    assert len(calls) == 1
    assert receipt["key_attempt_count"] == 1
    assert receipt["transport_attempt_count"] == 1
    assert receipt["rate_limit_event_count"] == 1
    assert receipt["shared_key_pool_short_circuit"] is True
    serialized = f"{receipt} {exc_info.value}"
    assert "traffic.fixture" not in serialized
    assert "first-fixture-key" not in serialized
    assert "second-fixture-key" not in serialized


def test_independent_key_pool_can_fail_over_after_a_429(monkeypatch):
    monkeypatch.setenv("TRAFFIC_FIXTURE_BASE_URL", "https://traffic.fixture/v1")
    monkeypatch.setenv("TRAFFIC_FIXTURE_KEYS", "first-fixture-key,second-fixture-key")
    calls: list[str] = []

    def callback(request, *, timeout):
        del timeout
        authorization = dict(request.header_items()).get("Authorization", "")
        calls.append(authorization)
        if len(calls) == 1:
            raise _rate_limited_error(request)
        return _SseResponse("independent-key-ok")

    _install_fake_opener(monkeypatch, callback)
    profile = _profile(
        traffic_control={
            "scope": "channel",
            "rate_limit_key_pool": "independent",
            "fallback_cooldown_ms": 50,
            "max_cooldown_ms": 50,
        }
    )
    request = _request()
    provider_module._begin_provider_request_trace()

    completion = HTTPProviderClient().complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system=request.system,
        timeout=1.0,
    )
    receipt = provider_module._finish_provider_request_trace()

    assert completion.text == "independent-key-ok"
    assert len(calls) == 2
    assert calls[0] != calls[1]
    assert receipt["key_attempt_count"] == 2
    assert receipt["transport_attempt_count"] == 2
    assert receipt["rate_limit_event_count"] == 1
    assert receipt["shared_key_pool_short_circuit"] is False


def test_channel_scope_cooldown_blocks_a_different_model_before_provider_io(monkeypatch):
    monkeypatch.setenv("TRAFFIC_FIXTURE_BASE_URL", "https://traffic.fixture/v1")
    monkeypatch.setenv("TRAFFIC_FIXTURE_KEYS", "fixture-key")
    calls: list[str] = []

    def callback(request, *, timeout):
        del timeout
        calls.append(request.full_url)
        raise _rate_limited_error(request, retry_after=None)

    _install_fake_opener(monkeypatch, callback)
    control = {
        "scope": "channel",
        "rate_limit_key_pool": "shared",
        "fallback_cooldown_ms": 100,
        "max_cooldown_ms": 100,
    }
    first = _profile(model="model-a", traffic_control=control)
    second = _profile(model="model-b", traffic_control=control)
    request = _request()

    with pytest.raises(ProviderExecutionError) as first_error:
        HTTPProviderClient().complete_turn(
            first,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=1.0,
        )
    with pytest.raises(ProviderExecutionError) as second_error:
        HTTPProviderClient().complete_turn(
            second,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=0.01,
        )

    assert first_error.value.http_status == 429
    assert second_error.value.error_code == "rate_limit_cooldown_exceeded"
    assert safe_provider_error_class(second_error.value.error_code) == "rate_limited"
    assert len(calls) == 1


def test_retry_after_accepts_standard_delta_seconds_and_http_date():
    numeric = Message()
    numeric["Retry-After"] = "42"
    assert provider_module._retry_after_seconds_from_headers(numeric, now=1_000.0) == 42.0

    date_headers = Message()
    date_headers["Retry-After"] = format_datetime(
        datetime.fromtimestamp(1_005.0, tz=timezone.utc), usegmt=True
    )
    parsed = provider_module._retry_after_seconds_from_headers(date_headers, now=1_000.0)
    assert parsed is not None
    assert 4.9 <= parsed <= 5.1


def test_runtime_channel_config_inherits_and_overrides_traffic_control():
    profiles = build_runtime_profiles(
        {
            "providers": [
                {
                    "provider": "traffic-config-fixture",
                    "api_format": "chat",
                    "base_url_env": "TRAFFIC_CONFIG_BASE_URL",
                    "api_key_env": "TRAFFIC_CONFIG_KEY",
                    "trafficControl": {
                        "scope": "channel",
                        "maxInFlight": 1,
                        "rateLimitKeyPool": "shared",
                    },
                    "models": [
                        {"model": "inherited-model"},
                        {
                            "model": "overridden-model",
                            "traffic_control": {
                                "scope": "profile",
                                "max_in_flight": 2,
                                "rate_limit_key_pool": "independent",
                            },
                        },
                    ],
                }
            ]
        },
        environment={
            "TRAFFIC_CONFIG_BASE_URL": "https://traffic-config.fixture/v1",
            "TRAFFIC_CONFIG_KEY": "fixture-key",
        },
    )
    by_model = {profile.model: profile for profile in profiles}

    assert by_model["inherited-model"].traffic_control["scope"] == "channel"
    assert by_model["inherited-model"].traffic_control["max_in_flight"] == 1
    assert by_model["overridden-model"].traffic_control["scope"] == "profile"
    assert by_model["overridden-model"].traffic_control["max_in_flight"] == 2
    assert by_model["overridden-model"].traffic_control["rate_limit_key_pool"] == "independent"


def test_transport_implementation_digest_is_bound_into_screening_adapter_digest(monkeypatch):
    monkeypatch.setattr(
        baseline_screening,
        "provider_transport_implementation_sha256",
        lambda: "a" * 64,
    )
    first = baseline_screening._screening_adapter_implementation_sha256(
        "jsonl_multiple_choice"
    )
    monkeypatch.setattr(
        baseline_screening,
        "provider_transport_implementation_sha256",
        lambda: "b" * 64,
    )
    second = baseline_screening._screening_adapter_implementation_sha256(
        "jsonl_multiple_choice"
    )

    assert len(first) == 64
    assert len(second) == 64
    assert first != second
