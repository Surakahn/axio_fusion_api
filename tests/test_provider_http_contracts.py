from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.cli import build_parser
from axio_fusion_api import providers as provider_module
from axio_fusion_api.providers import (
    HTTPProviderClient,
    _discovered_api_format,
    probe_exposed_provider_models,
)
from axio_fusion_api.registry import (
    build_registry_from_probe_artifacts,
    load_registry,
    normalize_profile,
)
from axio_fusion_api.schemas import FusionRequest


@pytest.fixture(autouse=True)
def _force_direct_network_for_provider_fixtures(monkeypatch):
    """Keep provider fixtures independent from the host's proxy process."""

    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "off")


def _install_fake_opener(monkeypatch, fake_urlopen):
    class FakeOpener:
        def open(self, request, timeout=None):
            return fake_urlopen(request, timeout=timeout)

    monkeypatch.setattr(
        provider_module.urllib.request,
        "build_opener",
        lambda *_handlers: FakeOpener(),
    )


class _ProviderFixtureHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    valid_keys = {
        "fixture-chat": "chat-key",
        "fixture-responses": "responses-key",
        "fixture-anthropic": "anthropic-key",
        "fixture-gemini": "gemini-key",
    }

    def log_message(self, _format: str, *_args) -> None:
        return

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_stream(self, status: int, events: list[tuple[str, dict | str]]) -> None:
        lines: list[str] = []
        for event_name, payload in events:
            if event_name:
                lines.append(f"event: {event_name}\n")
            encoded = payload if isinstance(payload, str) else json.dumps(payload)
            lines.append(f"data: {encoded}\n\n")
        body = "".join(lines).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _provider_for_request(self) -> str:
        query = parse_qs(urlsplit(self.path).query)
        key = (query.get("key") or [""])[0]
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            key = authorization[len("Bearer ") :]
        if not key:
            key = self.headers.get("x-api-key", "")
        for provider, expected in self.valid_keys.items():
            if key == expected:
                return provider
        return ""

    def do_GET(self) -> None:  # noqa: N802
        provider = self._provider_for_request()
        self.requests.append(
            {"method": "GET", "path": self.path, "provider": provider}
        )
        if not provider or not urlsplit(self.path).path.endswith("/models"):
            self._write_json(401, {"error": {"code": "unauthorized"}})
            return
        model = {
            "fixture-chat": "chat-string-model",
            "fixture-responses": "responses-string-model",
            "fixture-anthropic": "anthropic-string-model",
            "fixture-gemini": "models/gemini-string-model",
        }[provider]
        if provider == "fixture-chat":
            payload = {"data": [model]}
        elif provider == "fixture-gemini":
            payload = {"models": [{"name": model}]}
        else:
            payload = {"models": [model]}
        self._write_json(200, payload)

    def do_POST(self) -> None:  # noqa: N802
        provider = self._provider_for_request()
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length)
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        path = urlsplit(self.path).path
        self.requests.append(
            {
                "method": "POST",
                "path": self.path,
                "provider": provider,
                "payload": payload,
                "anthropic_version": self.headers.get("anthropic-version", ""),
            }
        )
        if not provider:
            self._write_json(401, {"error": {"code": "unauthorized"}})
            return
        probe_output = "AXIO_PROBE_OK" if "AXIO_PROBE_OK" in json.dumps(payload) else ""
        if path.endswith("/chat/completions"):
            self._write_stream(
                200,
                [
                    ("", {"choices": [{"delta": {"content": (probe_output or "chat-ok")}}]}),
                    ("", "[DONE]"),
                ],
            )
        elif path.endswith("/responses"):
            self._write_stream(
                200,
                [
                    (
                        "response.output_text.delta",
                        {"type": "response.output_text.delta", "delta": probe_output or "responses-ok"},
                    ),
                    ("response.completed", {"type": "response.completed"}),
                ],
            )
        elif path.endswith("/messages"):
            self._write_stream(
                200,
                [
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "delta": {"type": "text_delta", "text": probe_output or "anthropic-ok"},
                        },
                    ),
                    ("message_stop", {"type": "message_stop"}),
                ],
            )
        elif path.endswith(":streamGenerateContent") or path.endswith(":generateContent"):
            self._write_stream(
                200,
                [
                    (
                        "",
                        {
                            "candidates": [
                                {"content": {"parts": [{"text": probe_output or "gemini-ok"}]}}
                            ]
                        },
                    )
                ],
            )
        else:
            self._write_json(404, {"error": {"code": "not_found"}})


def _start_fixture_server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    _ProviderFixtureHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_provider_manifest_accepts_common_four_protocol_aliases() -> None:
    expected = {
        "chat/completion": "chat",
        "responses": "responses",
        "anthropic/messages": "anthropic",
        "gemini/generateContent": "gemini",
    }
    for raw, normalized in expected.items():
        profile = normalize_profile(
            {
                "provider": "fixture",
                "model": "fixture-model",
                "api_format": raw,
            }
        )
        assert profile.api_format == normalized


def test_provider_config_file_is_a_first_class_cli_input() -> None:
    args = build_parser().parse_args(
        [
            "--provider-config-file",
            "/private/manifest.json",
            "route-plan",
            "--model",
            "axio-fast",
            "--prompt",
            "hello",
        ]
    )
    assert args.provider_config_file == "/private/manifest.json"


@pytest.mark.parametrize(
    ("model", "owner", "expected_format"),
    (
        ("claude-3-7-sonnet", "", "anthropic"),
        ("anthropic/claude-3-7-sonnet", "", "anthropic"),
        ("claude/sonnet", "", "anthropic"),
        ("gpt-5.6-sol", "", "responses"),
        ("qwen3-max", "", "responses"),
    ),
)
def test_mixed_cpa_catalog_model_names_keep_protocol_local(
    model: str,
    owner: str,
    expected_format: str,
) -> None:
    seed = normalize_profile(
        {
            "provider": "cpa_plus",
            "model": "__discovery_seed__",
            "api_format": "responses",
        }
    )

    assert (
        _discovered_api_format(
            seed,
            model_entry={"id": model, "owned_by": owner},
        )
        == expected_format
    )


def test_explicit_catalog_protocol_metadata_overrides_model_name() -> None:
    seed = normalize_profile(
        {
            "provider": "cpa_plus",
            "model": "__discovery_seed__",
            "api_format": "responses",
        }
    )

    assert (
        _discovered_api_format(
            seed,
            model_entry={
                "id": "claude-3-7-sonnet",
                "api_format": "responses",
            },
        )
        == "responses"
    )


@pytest.mark.parametrize(
    ("fusion_deadline_bound", "timeout", "expected_code"),
    (
        (True, 0.25, "fusion_request_deadline_exhausted"),
        (False, 90.0, "provider_response_timeout_exceeded_90s"),
    ),
)
def test_stream_timeout_classification_separates_fusion_deadline_from_provider_ceiling(
    monkeypatch,
    fusion_deadline_bound,
    timeout,
    expected_code,
) -> None:
    class TimeoutResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            del exc_type, exc_value, traceback
            return False

        def readline(self):
            raise TimeoutError("fixture timeout")

    profile = normalize_profile(
        {
            "provider": "timeout-fixture",
            "model": "timeout-model",
            "api_format": "chat",
        }
    )
    monkeypatch.setattr(
        provider_module,
        "_open_provider_url",
        lambda request, timeout: TimeoutResponse(),
    )

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        provider_module._open_stream_json_request(
            urllib.request.Request("https://timeout.fixture/v1/chat/completions"),
            profile=profile,
            api_format="chat",
            timeout=timeout,
            require_streaming=True,
            fusion_deadline_bound=fusion_deadline_bound,
        )

    assert exc_info.value.error_code == expected_code
    assert expected_code in str(exc_info.value)


def test_stream_reader_refreshes_nested_socket_read_deadline(monkeypatch) -> None:
    class FakeSocket:
        def __init__(self):
            self.timeouts = []

        def settimeout(self, value):
            self.timeouts.append(float(value))

    class FakeRaw:
        def __init__(self, sock):
            self._sock = sock

    class FakeResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __init__(self):
            self.socket = FakeSocket()
            self.fp = FakeRaw(self.socket)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            del exc_type, exc_value, traceback
            return False

        def readline(self):
            raise TimeoutError("fixture timeout")

    response = FakeResponse()
    monkeypatch.setattr(
        provider_module,
        "_open_provider_url",
        lambda request, timeout: response,
    )
    profile = normalize_profile(
        {
            "provider": "nested-timeout-fixture",
            "model": "nested-timeout-model",
            "api_format": "chat",
        }
    )

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        provider_module._open_stream_json_request(
            urllib.request.Request("https://timeout.fixture/v1/chat/completions"),
            profile=profile,
            api_format="chat",
            timeout=0.2,
            require_streaming=True,
        )

    assert exc_info.value.error_code == "provider_request_timeout"
    assert response.socket.timeouts
    assert 0.0 < response.socket.timeouts[-1] <= 0.2


def test_stream_reader_watchdog_closes_a_response_that_ignores_socket_timeout(monkeypatch):
    closed = threading.Event()
    socket_closed = threading.Event()

    class WatchdogSocket:
        def close(self):
            socket_closed.set()

    class WatchdogRaw:
        def __init__(self):
            self._sock = WatchdogSocket()

        def close(self):
            self._sock.close()

    class WatchdogResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __init__(self):
            self.fp = WatchdogRaw()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            del exc_type, exc_value, traceback
            self.close()
            return False

        def close(self):
            closed.set()

        def readline(self):
            closed.wait(1.0)
            return b""

    response = WatchdogResponse()
    monkeypatch.setattr(
        provider_module,
        "_open_provider_url",
        lambda request, timeout: response,
    )
    profile = normalize_profile(
        {
            "provider": "watchdog-fixture",
            "model": "watchdog-model",
            "api_format": "chat",
        }
    )

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        provider_module._open_stream_json_request(
            urllib.request.Request("https://watchdog.fixture/v1/chat/completions"),
            profile=profile,
            api_format="chat",
            timeout=0.03,
            require_streaming=True,
        )

    assert exc_info.value.error_code == "provider_request_timeout"
    assert closed.is_set()
    assert socket_closed.is_set()


def test_stream_reader_normalizes_watchdog_value_error_as_deadline_timeout():
    deadline_at = time.monotonic() + 0.01

    class ClosedByWatchdogResponse:
        def readline(self):
            time.sleep(0.02)
            raise ValueError("I/O operation on closed file")

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        list(
            provider_module._iter_stream_events(
                ClosedByWatchdogResponse(),
                deadline_at,
                timeout_error_code="fusion_request_deadline_exhausted",
            )
        )

    assert exc_info.value.error_code == "fusion_request_deadline_exhausted"
    assert "closed file" not in str(exc_info.value)


def test_stream_reader_normalizes_context_manager_value_error_as_transport_error(monkeypatch):
    class ClosedAfterReadResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            del exc_type, exc_value, traceback
            raise ValueError("I/O operation on closed file")

        def readline(self):
            if not hasattr(self, "read_once"):
                self.read_once = True
                return b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
            return b""

    monkeypatch.setattr(
        provider_module,
        "_open_provider_url",
        lambda request, timeout: ClosedAfterReadResponse(),
    )
    profile = normalize_profile(
        {
            "provider": "context-exit-fixture",
            "model": "context-exit-model",
            "api_format": "chat",
        }
    )

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        provider_module._open_stream_json_request(
            urllib.request.Request("https://context-exit.fixture/v1/chat/completions"),
            profile=profile,
            api_format="chat",
            timeout=1.0,
            require_streaming=True,
        )

    assert exc_info.value.error_code == "provider_stream_transport_error"
    assert "closed file" not in str(exc_info.value)


def test_multi_sample_stream_probe_aggregates_independent_receipts(monkeypatch) -> None:
    profile = normalize_profile(
        {
            "provider": "stability-fixture",
            "model": "stability-model",
            "api_format": "chat",
        }
    )
    observed_samples: list[tuple[int, int]] = []

    def fake_probe_one(profile, *, timeout, client, sample_index, sample_count):
        del timeout, client
        observed_samples.append((sample_index, sample_count))
        latency = {1: 100.0, 2: 200.0, 3: 400.0}[sample_index]
        return provider_module._probe_row(
            profile,
            "available",
            latency_ms=latency,
            error_type="",
            output=f"stable-{sample_index}",
            request_receipt={
                "stream_requested": True,
                "strict_streaming_requested": True,
                "stream_observed": True,
                "stream_fallback_used": False,
                "stream_protocol": "sse",
                "stream_content_type": "text/event-stream",
                "stream_frame_count": 2,
            },
        )

    monkeypatch.setattr(provider_module, "_probe_one_model", fake_probe_one)
    report = provider_module.probe_provider_models(
        [profile],
        client=object(),
        live=True,
        require_streaming=True,
        samples_per_profile=3,
        max_workers=1,
    )
    row = report["probes"][0]

    assert observed_samples == [(1, 3), (2, 3), (3, 3)]
    assert row["status"] == "available"
    assert row["stability_sample_count"] == 3
    assert row["stability_completed_sample_count"] == 3
    assert row["stability_success_count"] == 3
    assert row["stability_failure_count"] == 0
    assert row["stability_success_rate"] == 1.0
    assert row["all_samples_eligible"] is True
    assert row["p50_latency_ms"] == 200.0
    assert row["p95_latency_ms"] == 380.0
    assert row["max_observed_latency_ms"] == 400.0
    assert row["latency_ms"] == 400.0
    assert len(row["sample_receipts"]) == 3
    assert row["sample_receipts_sha256"]
    assert report["stability_contract"]["samples_per_profile"] == 3
    assert report["stability_contract"]["requires_all_samples_success"] is True


def test_multi_sample_stream_probe_shared_deadline_skips_expired_profiles(monkeypatch) -> None:
    profiles = [
        normalize_profile(
            {
                "provider": "deadline-fixture",
                "model": f"deadline-model-{index}",
                "api_format": "chat",
            }
        )
        for index in range(2)
    ]
    calls: list[str] = []

    def unexpected_probe(*args, **kwargs):
        del args, kwargs
        calls.append("provider-request")
        raise AssertionError("an expired shared deadline must not start a request")

    monkeypatch.setattr(provider_module, "_probe_one_model", unexpected_probe)
    report = provider_module.probe_provider_models(
        profiles,
        client=object(),
        live=True,
        require_streaming=True,
        samples_per_profile=3,
        max_workers=1,
        deadline=time.monotonic() - 1.0,
    )

    assert calls == []
    assert report["budget_exhausted"] is True
    assert report["shared_deadline_bound"] is True
    assert all(row["status"] != "available" for row in report["probes"])
    assert all(
        any(
            sample.get("error_code") == "prefusion_total_budget_exhausted"
            for sample in row["sample_receipts"]
        )
        for row in report["probes"]
    )


def test_multi_sample_stream_probe_rejects_a_single_late_sample(monkeypatch) -> None:
    profile = normalize_profile(
        {
            "provider": "late-stability-fixture",
            "model": "late-stability-model",
            "api_format": "chat",
        }
    )

    def fake_probe_one(profile, *, timeout, client, sample_index, sample_count):
        del timeout, client, sample_count
        latency = 90_001.0 if sample_index == 2 else 200.0
        return provider_module._probe_row(
            profile,
            "available",
            latency_ms=latency,
            error_type="",
            output=f"late-{sample_index}",
            request_receipt={
                "stream_requested": True,
                "strict_streaming_requested": True,
                "stream_observed": True,
                "stream_fallback_used": False,
                "stream_protocol": "ndjson",
                "stream_content_type": "application/x-ndjson",
                "stream_frame_count": 1,
            },
        )

    monkeypatch.setattr(provider_module, "_probe_one_model", fake_probe_one)
    report = provider_module.probe_provider_models(
        [profile],
        client=object(),
        live=True,
        require_streaming=True,
        samples_per_profile=3,
        max_workers=1,
    )
    row = report["probes"][0]

    assert row["status"] == "latency_ineligible"
    assert row["error_code"] == "provider_response_latency_exceeded_90s"
    assert row["stability_success_count"] == 2
    assert row["stability_failure_count"] == 1
    assert row["all_samples_eligible"] is False
    assert row["max_observed_latency_ms"] == 90_001.0
    assert row["output_sha256"] == ""


def test_configured_model_name_is_the_default_canonical_identity(monkeypatch) -> None:
    configs = {
        "providers": [
            {
                "provider": "fixture-static-channel",
                "api_format": "responses",
                "base_url_env": "FIXTURE_STATIC_BASE_URL",
                "api_key_env": "FIXTURE_STATIC_KEY",
                "models": ["fixture-shared-model"],
            }
        ]
    }
    monkeypatch.setenv("AXIO_FUSION_PROVIDER_CONFIGS", json.dumps(configs))
    monkeypatch.setenv("FIXTURE_STATIC_BASE_URL", "https://fixture.invalid/v1")
    monkeypatch.setenv("FIXTURE_STATIC_KEY", "fixture-static-key")

    profiles = load_registry()

    assert len(profiles) == 1
    assert profiles[0].canonical_model_id == "fixture-shared-model"
    assert profiles[0].canonical_identity_source == "declared_canonical_model_id"


def test_private_probe_registry_preserves_canonical_identity_but_safe_registry_does_not(tmp_path):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_probe.v1",
                "probes": [
                    {
                        "provider": "fixture-private",
                        "model": "channel-alias",
                        "canonical_model_id": "vendor-family-v1",
                        "api_format": "responses",
                        "status": "available",
                        "latency_ms": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    private_registry = build_registry_from_probe_artifacts(probe_paths=[probe_path])
    safe_registry = build_registry_from_probe_artifacts(
        probe_paths=[probe_path],
        redact_provider_identifiers=True,
    )

    private_row = private_registry["models"][0]
    safe_row = safe_registry["model_receipts"][0]
    assert private_row["canonical_model_id"] == "vendor-family-v1"
    assert safe_row["raw_provider_model_id_persisted"] is False
    assert "vendor-family-v1" not in json.dumps(safe_registry)


def test_live_http_probe_handles_four_protocols_and_string_model_lists(monkeypatch) -> None:
    server, thread = _start_fixture_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        configs = {
            "providers": [
                {
                    "provider": "fixture-chat",
                    "api_format": "chat/completions",
                    "base_url_env": "FIXTURE_CHAT_BASE_URL",
                    "api_key_env": "FIXTURE_CHAT_KEY",
                },
                {
                    "provider": "fixture-responses",
                    "api_format": "responses",
                    "base_url_env": "FIXTURE_RESPONSES_BASE_URL",
                    "api_key_env": "FIXTURE_RESPONSES_KEY",
                },
                {
                    "provider": "fixture-anthropic",
                    "api_format": "anthropic/messages",
                    "base_url_env": "FIXTURE_ANTHROPIC_BASE_URL",
                    "api_key_env": "FIXTURE_ANTHROPIC_KEY",
                },
                {
                    "provider": "fixture-gemini",
                    "api_format": "gemini/generateContent",
                    "base_url_env": "FIXTURE_GEMINI_BASE_URL",
                    "api_key_env": "FIXTURE_GEMINI_KEY",
                },
            ]
        }
        monkeypatch.setenv("AXIO_FUSION_PROVIDER_CONFIGS", json.dumps(configs))
        for provider in _ProviderFixtureHandler.valid_keys:
            env_prefix = provider.upper().replace("-", "_")
            monkeypatch.setenv(f"{env_prefix}_BASE_URL", base_url)
            monkeypatch.setenv(
                f"{env_prefix}_KEY",
                _ProviderFixtureHandler.valid_keys[provider],
            )

        report = probe_exposed_provider_models(
            providers=list(_ProviderFixtureHandler.valid_keys),
            live=True,
            timeout=10,
            max_workers=4,
        )

        assert report["discovered_model_count"] == 4
        assert report["probe_report"]["available_count"] == 4
        assert report["probe_report"]["stream_requested_count"] == 4
        assert report["probe_report"]["stream_observed_count"] == 4
        assert report["probe_report"]["stream_fallback_count"] == 0
        assert all(
            row["probe_mode"] == "live"
            and row["live_probe_evidence"] is True
            and row["stream_requested"] is True
            and row["stream_observed"] is True
            and row["stream_fallback_used"] is False
            and row["stream_protocol"] in {"sse", "ndjson"}
            and row["stream_frame_count"] >= 1
            for row in report["probe_report"]["probes"]
        )
        assert {
            row["api_format"] for row in report["probe_report"]["probes"]
        } == {"chat", "responses", "anthropic", "gemini"}
        assert {
            row["provider"] for row in _ProviderFixtureHandler.requests
            if row["method"] == "GET"
        } == set(_ProviderFixtureHandler.valid_keys)
        assert {
            row["provider"] for row in _ProviderFixtureHandler.requests
            if row["method"] == "POST"
        } == set(_ProviderFixtureHandler.valid_keys)
        serialized = json.dumps(report, ensure_ascii=False)
        assert "chat-key" not in serialized
        assert "responses-key" not in serialized
        assert "anthropic-key" not in serialized
        assert "gemini-key" not in serialized
        assert base_url not in serialized
        anthropic_posts = [
            row for row in _ProviderFixtureHandler.requests
            if row["provider"] == "fixture-anthropic" and row["method"] == "POST"
        ]
        assert anthropic_posts and anthropic_posts[0]["anthropic_version"] == "2023-06-01"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_client_rotates_multiple_keys_after_transport_failure(monkeypatch) -> None:
    server, thread = _start_fixture_server()
    original_keys = dict(_ProviderFixtureHandler.valid_keys)
    _ProviderFixtureHandler.valid_keys = {"fixture-chat": "good-key"}
    try:
        monkeypatch.setenv("ROTATING_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
        monkeypatch.setenv("ROTATING_KEYS", "bad-key,good-key")
        monkeypatch.setenv("AXIO_FUSION_PROVIDER_MAX_ATTEMPTS_PER_KEY", "1")
        profile = normalize_profile(
            {
                "provider": "fixture-chat",
                "model": "rotating-model",
                "api_format": "chat",
                "base_url_env": "ROTATING_BASE_URL",
                "api_key_env": "ROTATING_KEYS",
            }
        )
        request = FusionRequest(model="axio-fast", prompt="hello")
        result = HTTPProviderClient().complete(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=5,
        )
        assert result == "chat-ok"
        posts = [
            row for row in _ProviderFixtureHandler.requests
            if row["method"] == "POST"
        ]
        assert len(posts) == 2
        assert posts[0]["provider"] == ""
        assert posts[1]["provider"] == "fixture-chat"
    finally:
        _ProviderFixtureHandler.valid_keys = original_keys
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_client_normalizes_common_text_block_variants_for_all_four_protocols(monkeypatch):
    request = FusionRequest(model="axio-fast", prompt="hello")
    profiles = {
        "chat": normalize_profile({"provider": "fixture", "model": "chat", "api_format": "chat"}),
        "responses": normalize_profile({"provider": "fixture", "model": "responses", "api_format": "responses"}),
        "anthropic": normalize_profile({"provider": "fixture", "model": "anthropic", "api_format": "anthropic"}),
        "gemini": normalize_profile({"provider": "fixture", "model": "gemini", "api_format": "gemini"}),
    }
    payloads = {
        "chat": {
            "choices": [{"message": {"content": [{"type": "text", "text": "chat block"}]}}]
        },
        "responses": {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "responses block"}]}]
        },
        "anthropic": {"content": [{"type": "text", "text": "anthropic block"}]},
        "gemini": {"candidates": [{"content": {"parts": [{"text": "gemini block"}]}}]},
    }

    def fake_post(profile, path, payload, *, timeout, **kwargs):
        del path, payload, timeout, kwargs
        return payloads[profile.api_format]

    monkeypatch.setattr(provider_module, "_post_json", fake_post)

    assert HTTPProviderClient().complete_turn(
        profiles["chat"], request, prompt=request.prompt, system=request.system
    ).text == "chat block"
    assert HTTPProviderClient().complete_turn(
        profiles["responses"], request, prompt=request.prompt, system=request.system
    ).text == "responses block"
    assert HTTPProviderClient().complete_turn(
        profiles["anthropic"], request, prompt=request.prompt, system=request.system
    ).text == "anthropic block"
    assert HTTPProviderClient().complete_turn(
        profiles["gemini"], request, prompt=request.prompt, system=request.system
    ).text == "gemini block"


def test_strict_streaming_client_rejects_ordinary_json_body(monkeypatch):
    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"json-only"}}]}'

    def fake_urlopen(request, timeout=None):
        del request, timeout
        return FakeResponse()

    _install_fake_opener(monkeypatch, fake_urlopen)
    monkeypatch.setenv("FIXTURE_STRICT_BASE_URL", "https://strict.fixture/v1")
    monkeypatch.setenv("FIXTURE_STRICT_KEY", "strict-secret")
    profile = normalize_profile(
        {
            "provider": "fixture-strict",
            "model": "strict-model",
            "api_format": "chat",
            "base_url_env": "FIXTURE_STRICT_BASE_URL",
            "api_key_env": "FIXTURE_STRICT_KEY",
        }
    )

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        HTTPProviderClient(require_streaming=True).complete_turn(
            profile,
            FusionRequest(model="axio-fast", prompt="hello"),
            prompt="hello",
            system="system",
            timeout=1.0,
        )

    assert exc_info.value.error_code == "unframed_stream_response"


def test_production_streaming_client_factory_upgrades_http_compatibility_client():
    compatibility_client = HTTPProviderClient()
    strict_client = provider_module.ensure_strict_streaming_client(compatibility_client)
    already_strict = HTTPProviderClient(require_streaming=True)

    assert compatibility_client.require_streaming is False
    assert strict_client is not compatibility_client
    assert strict_client.require_streaming is True
    assert provider_module.ensure_strict_streaming_client(already_strict) is already_strict


def test_strict_streaming_receipt_contains_framing_evidence(monkeypatch):
    class FakeResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __init__(self):
            self._lines = iter(
                [
                    b'data: {"choices":[{"delta":{"content":"ok"}}]}\n',
                    b"\n",
                    b"data: [DONE]\n",
                    b"\n",
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            return next(self._lines, b"")

    def fake_urlopen(request, timeout=None):
        del request, timeout
        return FakeResponse()

    _install_fake_opener(monkeypatch, fake_urlopen)
    monkeypatch.setenv("FIXTURE_STREAM_BASE_URL", "https://stream.fixture/v1")
    monkeypatch.setenv("FIXTURE_STREAM_KEY", "stream-secret")
    profile = normalize_profile(
        {
            "provider": "fixture-stream",
            "model": "stream-model",
            "api_format": "chat",
            "base_url_env": "FIXTURE_STREAM_BASE_URL",
            "api_key_env": "FIXTURE_STREAM_KEY",
        }
    )
    request = FusionRequest(model="axio-fast", prompt="hello")
    provider_module._begin_provider_request_trace()
    completion = HTTPProviderClient(require_streaming=True).complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system="system",
        timeout=1.0,
    )
    receipt = provider_module._finish_provider_request_trace()

    assert completion.text == "ok"
    assert receipt["stream_requested"] is True
    assert receipt["stream_observed"] is True
    assert receipt["stream_fallback_used"] is False
    assert receipt["stream_protocols"] == ["sse"]
    assert receipt["stream_frame_count"] >= 1
    assert receipt["strict_streaming_requested"] is True


@pytest.mark.parametrize(
    ("api_format", "expected_path", "result"),
    [
        (
            "chat/completions",
            "/chat/completions",
            {"choices": [{"message": {"content": "answer"}}]},
        ),
        (
            "responses",
            "/responses",
            {"output_text": "answer"},
        ),
        (
            "anthropic",
            "/messages",
            {"content": [{"type": "text", "text": "answer"}]},
        ),
        (
            "gemini",
            "/models/provider-model:streamGenerateContent?alt=sse",
            {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]},
        ),
    ],
)
def test_every_provider_adapter_uses_streaming_wire(
    monkeypatch,
    api_format,
    expected_path,
    result,
):
    calls = []

    def fake_post(profile, path, payload, **kwargs):
        calls.append((path, payload, kwargs))
        return result

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    profile = normalize_profile(
        {
            "provider": "stream-contract-fixture",
            "model": "provider-model",
            "api_format": api_format,
        }
    )
    request = FusionRequest(model="axio-fast", prompt="hello")

    completion = HTTPProviderClient(require_streaming=True).complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system="system",
        timeout=1.0,
    )

    assert completion.text == "answer"
    assert len(calls) == 1
    path, payload, kwargs = calls[0]
    assert path == expected_path
    if api_format == "gemini":
        assert "stream" not in payload
    else:
        assert payload["stream"] is True
    assert kwargs["require_streaming"] is True


def test_operational_role_probe_requires_framed_streaming_and_structured_judge():
    profile = normalize_profile(
        {
            "provider": "role-fixture",
            "model": "role-model",
            "api_format": "chat",
        }
    )
    required_keys = {
        "consensus": "bounded retry",
        "contradictions": [],
        "unique_insights": [],
        "missing_coverage": [],
        "collective_blind_spots": [],
        "ranked_candidates": [],
        "follow_up_tasks": [],
        "ready_for_synthesis": True,
    }

    class RoleClient:
        def __init__(self, *, framed: bool):
            self.framed = framed
            self.max_output_tokens: list[int | None] = []

        def complete_turn(self, _profile, request, *, system, **_kwargs):
            self.max_output_tokens.append(request.max_output_tokens)
            provider_module._record_provider_request_receipt(
                status="success",
                key_attempt_count=1,
                transport_attempt_count=1,
                retry_attempt_count=0,
                stream_requested=True,
                stream_observed=self.framed,
                stream_fallback_used=not self.framed,
                stream_protocol="sse" if self.framed else "",
                stream_frame_count=2 if self.framed else 0,
                strict_streaming_requested=True,
            )
            output = json.dumps(required_keys) if "structured judge" in system else "bounded review"
            return provider_module.ProviderCompletion(output)

    framed_client = RoleClient(framed=True)
    framed = provider_module._probe_one_model_role(
        profile,
        "judge",
        timeout=1.0,
        client=framed_client,
    )
    assert framed["status"] == "available"
    assert framed["role_output_contract_valid"] is True
    assert framed["role_streaming_contract_valid"] is True
    assert framed["stream_protocol"] == "sse"
    assert framed["stream_frame_count"] == 2
    assert framed_client.max_output_tokens == [provider_module.ROLE_PROBE_JUDGE_MAX_OUTPUT_TOKENS]

    unframed = provider_module._probe_one_model_role(
        profile,
        "judge",
        timeout=1.0,
        client=RoleClient(framed=False),
    )
    assert unframed["status"] == "incompatible"
    assert unframed["error_code"] == "role_probe_streaming_contract_invalid"


def test_operational_judge_role_probe_rejects_non_json_even_with_sse():
    profile = normalize_profile(
        {
            "provider": "role-json-fixture",
            "model": "role-json-model",
            "api_format": "chat",
        }
    )

    class InvalidJudgeClient:
        def complete_turn(self, *_args, **_kwargs):
            provider_module._record_provider_request_receipt(
                status="success",
                key_attempt_count=1,
                transport_attempt_count=1,
                retry_attempt_count=0,
                stream_requested=True,
                stream_observed=True,
                stream_fallback_used=False,
                stream_protocol="ndjson",
                stream_frame_count=1,
                strict_streaming_requested=True,
            )
            return provider_module.ProviderCompletion("not-json")

    row = provider_module._probe_one_model_role(
        profile,
        "judge",
        timeout=1.0,
        client=InvalidJudgeClient(),
    )
    assert row["status"] == "incompatible"
    assert row["error_code"] == "role_probe_output_contract_invalid"
    assert row["role_streaming_contract_valid"] is True


def _role_probe_sample_fixture(profile, role, *, latency_ms, eligible=True):
    return {
        "schema": provider_module.ROLE_PROBE_SCHEMA,
        "contract": provider_module.ROLE_PROBE_CONTRACT,
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "api_format": profile.api_format,
        "role": role,
        "status": "available" if eligible else "incompatible",
        "latency_ms": latency_ms,
        "output_sha256": provider_module.sha256_text(
            f"{profile.profile_id}:{role}:{latency_ms}"
        )
        if eligible
        else "",
        "role_output_contract_valid": eligible,
        "role_streaming_contract_valid": eligible,
        "stream_requested": eligible,
        "stream_observed": eligible,
        "stream_fallback_used": False,
        "stream_protocol": "sse" if eligible else "",
        "stream_frame_count": 2 if eligible else 0,
        "strict_streaming_requested": True,
        "error_type": "" if eligible else "RoleProbeContractError",
        "error_code": "" if eligible else "role_probe_output_contract_invalid",
    }


def test_repeated_role_probe_aggregates_quantiles_and_requires_every_sample():
    profile = normalize_profile(
        {
            "provider": "role-calibration-fixture",
            "model": "role-calibration-model",
            "api_format": "chat",
        }
    )
    samples = [
        _role_probe_sample_fixture(profile, "primary_solver", latency_ms=value)
        for value in (100, 200, 500)
    ]

    aggregate = provider_module._aggregate_role_probe_samples(
        profile,
        "primary_solver",
        samples,
        requested_sample_count=3,
    )

    assert aggregate["status"] == "available"
    assert aggregate["role_probe_sample_count"] == 3
    assert aggregate["role_probe_completed_sample_count"] == 3
    assert aggregate["role_probe_success_count"] == 3
    assert aggregate["role_probe_failure_count"] == 0
    assert aggregate["role_probe_all_samples_eligible"] is True
    assert aggregate["p50_latency_ms"] == 200.0
    assert aggregate["p95_latency_ms"] == 470.0
    assert aggregate["role_probe_sample_receipts_sha256"]
    assert "primary_solver" == aggregate["role"]

    failed = provider_module._aggregate_role_probe_samples(
        profile,
        "primary_solver",
        [
            samples[0],
            _role_probe_sample_fixture(
                profile,
                "primary_solver",
                latency_ms=250,
                eligible=False,
            ),
            samples[2],
        ],
        requested_sample_count=3,
    )
    assert failed["status"] == "stability_ineligible"
    assert failed["role_probe_all_samples_eligible"] is False
    assert failed["role_probe_success_count"] == 2


def test_role_probe_aggregation_rejects_stream_fallback_even_when_output_is_valid():
    profile = normalize_profile(
        {
            "provider": "role-stream-fixture",
            "model": "role-stream-model",
            "api_format": "chat",
        }
    )
    sample = _role_probe_sample_fixture(
        profile,
        "primary_solver",
        latency_ms=120,
    )
    sample["stream_fallback_used"] = True

    aggregate = provider_module._aggregate_role_probe_samples(
        profile,
        "primary_solver",
        [sample],
        requested_sample_count=1,
    )

    assert aggregate["status"] == "stability_ineligible"
    assert aggregate["role_probe_all_samples_eligible"] is False
    assert aggregate["role_probe_failure_count"] == 1


@pytest.mark.parametrize(
    ("role", "output"),
    [
        (
            "structured_extraction",
            '{"entity":"team-c","value":2,"confidence":0.9}',
        ),
        (
            "simple_classification",
            '{"label":"safe","confidence":0.9,"reason":"bounded"}',
        ),
        (
            "short_verification",
            '{"verdict":"pass","issues":[],"check":"deadline preserved"}',
        ),
        (
            "single_tool_argument_validation",
            '{"valid":true,"arguments":{"location":"archive","limit":3},"error":""}',
        ),
    ],
)
def test_narrow_role_probe_requires_its_fixed_json_shape(role, output):
    assert provider_module._role_probe_output_is_valid(role, output) is True
    parsed = json.loads(output)
    parsed["unexpected"] = "not allowed"
    assert provider_module._role_probe_output_is_valid(role, json.dumps(parsed)) is False


def test_role_probe_covers_high_impact_and_narrow_roles():
    assert provider_module.ROLE_PROBE_ROLES == (
        "primary_solver",
        "critic",
        "judge",
        "synthesizer",
        "structured_extraction",
        "simple_classification",
        "short_verification",
        "single_tool_argument_validation",
    )


def test_provider_adapters_omit_unspecified_temperature_but_preserve_explicit_zero(monkeypatch):
    profiles = {
        "chat": normalize_profile({"provider": "fixture", "model": "chat", "api_format": "chat"}),
        "responses": normalize_profile({"provider": "fixture", "model": "responses", "api_format": "responses"}),
        "anthropic": normalize_profile({"provider": "fixture", "model": "anthropic", "api_format": "anthropic"}),
        "gemini": normalize_profile({"provider": "fixture", "model": "gemini", "api_format": "gemini"}),
    }
    captured: dict[str, dict] = {}

    def fake_post(profile, path, payload, *, timeout, **kwargs):
        del path, timeout, kwargs
        captured[profile.api_format] = payload
        if profile.api_format == "chat":
            return {"choices": [{"message": {"content": "ok"}}]}
        if profile.api_format == "responses":
            return {"output_text": "ok"}
        if profile.api_format == "anthropic":
            return {"content": [{"type": "text", "text": "ok"}]}
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    client = HTTPProviderClient()
    unspecified = FusionRequest(model="axio-fast", prompt="hello")
    for profile in profiles.values():
        client.complete_turn(profile, unspecified, prompt=unspecified.prompt, system=unspecified.system)

    assert "temperature" not in captured["chat"]
    assert "temperature" not in captured["responses"]
    assert "temperature" not in captured["anthropic"]
    assert "temperature" not in captured["gemini"]["generationConfig"]

    explicit_zero = FusionRequest(model="axio-fast", prompt="hello", temperature=0.0)
    for profile in profiles.values():
        client.complete_turn(profile, explicit_zero, prompt=explicit_zero.prompt, system=explicit_zero.system)

    assert captured["chat"]["temperature"] == 0.0
    assert captured["responses"]["temperature"] == 0.0
    assert captured["anthropic"]["temperature"] == 0.0
    assert captured["gemini"]["generationConfig"]["temperature"] == 0.0


@pytest.mark.parametrize("parameter", ["max_tokens", "max_completion_tokens", "max_output_tokens"])
def test_chat_adapter_uses_only_the_profile_selected_output_token_parameter(
    monkeypatch,
    parameter,
):
    profile = normalize_profile(
        {
            "provider": "fixture",
            "model": "chat-model",
            "api_format": "chat",
            "max_output_tokens_parameter": parameter,
        }
    )
    captured = {}

    def fake_post(_profile, _path, payload, *, timeout, **kwargs):
        del timeout, kwargs
        captured.update(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    request = FusionRequest(model="axio-fast", prompt="hello", max_output_tokens=123)
    HTTPProviderClient().complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system=request.system,
    )

    assert captured[parameter] == 123
    assert set(captured).isdisjoint(
        {"max_tokens", "max_completion_tokens", "max_output_tokens"} - {parameter}
    )


def test_http_client_retries_bounded_semantic_empty_response(monkeypatch):
    profile = normalize_profile(
        {"provider": "fixture", "model": "empty", "api_format": "chat"}
    )
    request = FusionRequest(model="axio-fast", prompt="hello")
    calls = []

    def fake_post(profile, path, payload, *, timeout, **kwargs):
        del profile, path, payload, timeout, kwargs
        calls.append(True)
        return {"choices": [{"message": {"content": []}}]}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    monkeypatch.setenv("AXIO_FUSION_PROVIDER_EMPTY_RESPONSE_RETRIES", "1")

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        HTTPProviderClient().complete_turn(
            profile, request, prompt=request.prompt, system=request.system
        )

    assert exc_info.value.error_code == "empty_provider_response"
    assert len(calls) == 2


def test_gemini_explicit_x_goog_api_key_auth_is_respected(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self):
            self._lines = iter([b'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}\n', b"\n"])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            return next(self._lines, b"")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return FakeResponse()

    _install_fake_opener(monkeypatch, fake_urlopen)
    monkeypatch.setenv("FIXTURE_GEMINI_BASE_URL", "https://gemini.fixture/v1beta")
    monkeypatch.setenv("FIXTURE_GEMINI_API_KEY", "gemini-secret")
    profile = normalize_profile(
        {
            "provider": "fixture-gemini",
            "model": "gemini-model",
            "api_format": "gemini",
            "base_url_env": "FIXTURE_GEMINI_BASE_URL",
            "api_key_env": "FIXTURE_GEMINI_API_KEY",
            "auth_scheme": "x-goog-api-key",
        }
    )

    completion = HTTPProviderClient().complete_turn(
        profile,
        FusionRequest(model="axio-fast", prompt="hello"),
        prompt="hello",
        system="system",
        timeout=1.0,
    )

    assert completion.text == "ok"
    assert captured["headers"]["x-goog-api-key"] == "gemini-secret"
    assert "authorization" not in captured["headers"]
    assert "x-api-key" not in captured["headers"]
    assert "?key=" not in captured["url"]
    assert captured["timeout"] <= 1.0


def test_model_discovery_uses_configured_relative_catalog_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self):
            self._lines = iter([b'data: {"choices":[{"delta":{"content":"public-gateway-ok"}}]}\n', b"\n", b'data: [DONE]\n', b"\n"])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"models":[{"id":"catalog-model"}]}'

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return FakeResponse()

    _install_fake_opener(monkeypatch, fake_urlopen)
    monkeypatch.setenv("FIXTURE_CATALOG_BASE_URL", "https://catalog.fixture/v1")
    monkeypatch.setenv("FIXTURE_CATALOG_KEY", "catalog-secret")
    profile = normalize_profile(
        {
            "provider": "fixture-catalog",
            "model": "seed",
            "api_format": "anthropic",
            "base_url_env": "FIXTURE_CATALOG_BASE_URL",
            "api_key_env": "FIXTURE_CATALOG_KEY",
            "models_endpoint": "catalog/models",
        }
    )

    report = provider_module._safe_list_models(profile, timeout=1.0)

    assert report["status"] == "ok"
    assert report["model_ids"] == ["catalog-model"]
    assert report["models_endpoint"] == "/catalog/models"
    assert captured["url"] == "https://catalog.fixture/v1/catalog/models"
    assert captured["headers"]["x-api-key"] == "catalog-secret"
    assert "catalog-secret" not in json.dumps(report, ensure_ascii=False)


def test_model_discovery_can_be_disabled_for_static_model_rows(monkeypatch):
    monkeypatch.setenv("FIXTURE_STATIC_BASE_URL", "https://static.fixture/v1")
    monkeypatch.setenv("FIXTURE_STATIC_KEY", "static-secret")
    profile = normalize_profile(
        {
            "provider": "fixture-static",
            "model": "static-model",
            "api_format": "responses",
            "base_url_env": "FIXTURE_STATIC_BASE_URL",
            "api_key_env": "FIXTURE_STATIC_KEY",
            "discover_models": False,
        }
    )

    report = provider_module._safe_list_models(profile, timeout=1.0)

    assert report["status"] == "skipped"
    assert report["reason_codes"] == ["model_discovery_disabled"]
    assert report["network_calls_performed"] is False


def test_model_catalog_preserves_per_model_protocol_hints(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {"id": "gpt-5.6-terra", "owned_by": "openai"},
                        {"id": "claude-sonnet-5", "owned_by": "anthropic"},
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse()

    _install_fake_opener(monkeypatch, fake_urlopen)
    monkeypatch.setenv("FIXTURE_MULTI_FORMAT_BASE_URL", "https://multi.fixture/v1")
    monkeypatch.setenv("FIXTURE_MULTI_FORMAT_KEY", "multi-secret")
    seed = normalize_profile(
        {
            "provider": "cpa-plus",
            "model": "seed",
            "api_format": "responses",
            "base_url_env": "FIXTURE_MULTI_FORMAT_BASE_URL",
            "api_key_env": "FIXTURE_MULTI_FORMAT_KEY",
        }
    )

    report = provider_module._safe_list_models(seed, timeout=1.0)

    assert report["model_ids"] == ["gpt-5.6-terra", "claude-sonnet-5"]
    assert report["model_entries"][1]["owned_by"] == "anthropic"
    assert captured["url"] == "https://multi.fixture/v1/models"
    assert "multi-secret" not in json.dumps(report, ensure_ascii=False)

    gpt_row = provider_module._discovered_profile_row(
        seed,
        "gpt-5.6-terra",
        {},
        model_entry=report["model_entries"][0],
    )
    claude_row = provider_module._discovered_profile_row(
        seed,
        "claude-sonnet-5",
        {},
        model_entry=report["model_entries"][1],
    )

    assert gpt_row["api_format"] == "responses"
    assert claude_row["api_format"] == "anthropic"


def test_http_client_supports_explicit_no_auth_remote_gateway(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self):
            self._lines = iter(
                [
                    b'data: {"choices":[{"delta":{"content":"public-gateway-ok"}}]}\n',
                    b"\n",
                    b"data: [DONE]\n",
                    b"\n",
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            return next(self._lines, b"")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.delenv("AXIO_FUSION_HTTP_PROXY", raising=False)
    monkeypatch.delenv("AXIO_FUSION_USE_SYSTEM_PROXY", raising=False)
    monkeypatch.setenv("FIXTURE_NO_AUTH_BASE_URL", "https://public-gateway.fixture/v1")
    monkeypatch.delenv("FIXTURE_NO_AUTH_KEY", raising=False)
    profile = normalize_profile(
        {
            "provider": "fixture-public-gateway",
            "model": "public-model",
            "api_format": "chat/completions",
            "base_url_env": "FIXTURE_NO_AUTH_BASE_URL",
            "api_key_env": "FIXTURE_NO_AUTH_KEY",
            "auth_scheme": "none",
        }
    )
    _install_fake_opener(monkeypatch, fake_urlopen)
    provider_module._begin_provider_request_trace()

    completion = HTTPProviderClient().complete_turn(
        profile,
        FusionRequest(model="axio-fast", prompt="hello"),
        prompt="hello",
        system="system",
        timeout=1.0,
    )
    request_receipt = provider_module._finish_provider_request_trace()

    readiness = provider_module.profile_credential_readiness(profile)
    assert completion.text == "public-gateway-ok"
    assert captured["url"] == "https://public-gateway.fixture/v1/chat/completions"
    assert "authorization" not in captured["headers"]
    assert "x-api-key" not in captured["headers"]
    assert readiness["auth_scheme"] == "none"
    assert readiness["api_key_required"] is False
    assert readiness["api_key_count"] == 0
    assert readiness["credential_ready"] is True
    assert request_receipt["key_attempt_count"] == 0
    assert request_receipt["transport_attempt_count"] == 1
    assert request_receipt["retry_attempt_count"] == 0


def test_http_client_semantic_retry_shares_one_turn_deadline(monkeypatch):
    profile = normalize_profile(
        {"provider": "fixture", "model": "empty-deadline", "api_format": "chat"}
    )
    request = FusionRequest(model="axio-fast", prompt="hello")
    timeouts = []

    def fake_post(profile, path, payload, *, timeout, **kwargs):
        del profile, path, payload, kwargs
        timeouts.append(float(timeout))
        provider_module.time.sleep(0.006)
        return {"choices": [{"message": {"content": []}}]}

    monkeypatch.setattr(provider_module, "_post_json", fake_post)
    monkeypatch.setenv("AXIO_FUSION_PROVIDER_EMPTY_RESPONSE_RETRIES", "1")

    with pytest.raises(provider_module.ProviderExecutionError) as exc_info:
        HTTPProviderClient().complete_turn(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=0.02,
        )

    assert exc_info.value.error_code == "empty_provider_response"
    assert len(timeouts) == 2
    assert timeouts[1] < timeouts[0]


@pytest.mark.parametrize(
    "error_code",
    [
        "RemoteDisconnected",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "IncompleteRead",
    ],
)
def test_transient_peer_disconnects_are_retryable(error_code):
    assert provider_module._provider_error_retryable(
        provider_module.ProviderExecutionError("transport", error_code=error_code)
    ) is True


def test_non_transport_provider_errors_are_not_retryable():
    assert provider_module._provider_error_retryable(
        provider_module.ProviderExecutionError("invalid", error_code="invalid_json")
    ) is False


def test_responses_text_fallback_consumes_remaining_turn_deadline(monkeypatch):
    profile = normalize_profile(
        {"provider": "fixture", "model": "responses-deadline", "api_format": "responses"}
    )
    request = FusionRequest(model="axio-fast", prompt="hello")
    calls = []

    def typed_then_text(profile, path, payload, *, timeout, **kwargs):
        del profile, path, kwargs
        calls.append((payload.get("input"), float(timeout)))
        if len(calls) == 1:
            provider_module.time.sleep(0.006)
            raise provider_module.ProviderExecutionError(
                "fixture typed input rejected",
                error_code="http_error",
                http_status=400,
            )
        return {"output_text": "text fallback answer"}

    monkeypatch.setattr(provider_module, "_post_json", typed_then_text)
    completion = HTTPProviderClient().complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system=request.system,
        timeout=0.02,
    )

    assert completion.text == "text fallback answer"
    assert len(calls) == 2
    assert isinstance(calls[0][0], list)
    assert isinstance(calls[1][0], str)
    assert calls[1][1] < calls[0][1]


def test_optional_system_proxy_uses_10808_without_leaking_proxy_value(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": true}'

    class FakeOpener:
        def open(self, request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    monkeypatch.delenv("AXIO_FUSION_HTTP_PROXY", raising=False)
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "on")
    monkeypatch.setenv("AXIO_FUSION_SYSTEM_PROXY", "http://127.0.0.1:10808")
    monkeypatch.setattr(provider_module.urllib.request, "build_opener", fake_build_opener)

    readiness = provider_module.provider_proxy_readiness("http://127.0.0.1:10808")
    result = provider_module._open_json_request(
        provider_module.urllib.request.Request("https://provider.invalid/v1/health"),
        timeout=3,
    )
    serialized = json.dumps(
        {
            "runtime": provider_module.provider_proxy_runtime_summary(),
            "result": result,
        },
        ensure_ascii=False,
    )

    assert result == {"ok": True}
    assert readiness["valid"] is True
    assert provider_module.provider_proxy_runtime_summary()["mode"] == "on"
    assert captured["timeout"] == 3
    assert captured["handlers"]
    proxy_handler = captured["handlers"][0]
    assert isinstance(proxy_handler, provider_module.urllib.request.ProxyHandler)
    assert "127.0.0.1:10808" not in json.dumps(readiness, ensure_ascii=False)
    assert "127.0.0.1:10808" not in serialized
