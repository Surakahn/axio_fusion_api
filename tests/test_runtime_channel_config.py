from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api import (  # noqa: E402
    ChannelConfigError,
    FusionEngine,
    FusionRequest,
    build_runtime_profiles,
    discover_runtime_profiles,
    runtime_channel_summary,
)
from axio_fusion_api.providers import HTTPProviderClient, probe_provider_models  # noqa: E402
from axio_fusion_api.server import create_http_server, create_runtime_http_server  # noqa: E402


class _RuntimeChannelHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    model_by_key = {
        "chat-key": "chat-runtime-model",
        "responses-key": "responses-runtime-model",
        "anthropic-key": "anthropic-runtime-model",
        "gemini-key": "models/gemini-runtime-model",
    }

    def log_message(self, _format: str, *_args) -> None:
        return

    def _key(self) -> str:
        query = parse_qs(urlsplit(self.path).query)
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            return authorization[len("Bearer ") :]
        return (
            (query.get("key") or [""])[0]
            or self.headers.get("x-api-key", "")
            or self.headers.get("x-goog-api-key", "")
        )

    def _write(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        key = self._key()
        self.requests.append({"method": "GET", "path": self.path, "key": key})
        model = self.model_by_key.get(key)
        if not model or not urlsplit(self.path).path.endswith("/models"):
            self._write(401, {"error": {"code": "unauthorized"}})
            return
        if key == "chat-key":
            self._write(200, {"data": [{"id": model}]})
        elif key == "gemini-key":
            self._write(200, {"models": [{"name": model}]})
        else:
            self._write(200, {"models": [{"id": model}]})

    def do_POST(self) -> None:  # noqa: N802
        key = self._key()
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length)
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        self.requests.append(
            {
                "method": "POST",
                "path": self.path,
                "key": key,
                "payload": payload,
            }
        )
        if key not in self.model_by_key:
            self._write(401, {"error": {"code": "unauthorized"}})
            return
        if self.path.endswith("/chat/completions"):
            self._write(200, {"choices": [{"message": {"content": "AXIO_PROBE_OK"}}]})
        elif self.path.endswith("/responses"):
            self._write(200, {"output_text": "AXIO_PROBE_OK"})
        elif self.path.endswith("/messages"):
            self._write(200, {"content": [{"type": "text", "text": "AXIO_PROBE_OK"}]})
        elif self.path.endswith(":streamGenerateContent?alt=sse") or self.path.endswith(":generateContent"):
            self._write(
                200,
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "AXIO_PROBE_OK"}]}}
                    ]
                },
            )
        else:
            self._write(404, {"error": {"code": "not_found"}})


def _start_server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    _RuntimeChannelHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RuntimeChannelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _manifest(base_url: str) -> dict:
    return {
        "providers": [
            {
                "provider": "runtime-chat",
                "api_format": "chat/completions",
                "base_url": base_url,
                "api_key": "chat-key",
                "models": [{"model": "chat-runtime-model", "supports_tools": "false"}],
            },
            {
                "provider": "runtime-responses",
                "api_format": "responses",
                "base_url": base_url,
                "api_keys": ["responses-key"],
                "models": ["responses-runtime-model"],
            },
            {
                "provider": "runtime-anthropic",
                "api_format": "anthropic/messages",
                "base_url": base_url,
                "api_key": "anthropic-key",
                "models": ["anthropic-runtime-model"],
            },
            {
                "provider": "runtime-gemini",
                "api_format": "gemini/generateContent",
                "base_url": base_url,
                "api_key": "gemini-key",
                "auth_scheme": "x-goog-api-key",
                "models": ["models/gemini-runtime-model"],
            },
        ]
    }


def test_runtime_manifest_supports_direct_four_protocol_credentials_without_persistence():
    server, thread = _start_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        profiles = build_runtime_profiles(_manifest(base_url))

        assert [profile.api_format for profile in profiles] == [
            "chat",
            "responses",
            "anthropic",
            "gemini",
        ]
        assert profiles[0].supports_tools is False
        assert all(profile.runtime_base_url == base_url for profile in profiles)
        assert all(profile.runtime_api_keys for profile in profiles)
        serialized_profiles = json.dumps([profile.safe_dict() for profile in profiles])
        assert base_url not in serialized_profiles
        assert "chat-key" not in serialized_profiles
        assert "responses-key" not in serialized_profiles
        assert "anthropic-key" not in serialized_profiles
        assert "gemini-key" not in serialized_profiles
        engine = FusionEngine.from_runtime_channels(
            {
                "providers": [
                    {
                        "provider": "runtime-engine-channel",
                        "api_format": "responses",
                        "base_url": base_url,
                        "api_key": "responses-key",
                        "models": ["engine-model"],
                    }
                ]
            },
            diagnostic_only=True,
            cache_enabled=False,
        )
        assert len(engine.profiles) == 1
        assert engine.profiles[0].runtime_api_keys == ("responses-key",)
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_current_channel_template_keeps_reasoning_transport_protocol_local():
    """The operator template must not conflate Chat and Responses wire fields."""

    manifest = json.loads(
        (ROOT / "config" / "current_channels.example.json").read_text(
            encoding="utf-8"
        )
    )
    profiles = build_runtime_profiles(
        manifest,
        environment={
            "AXIO_NVIDIA_BASE_URL": "https://nvidia.fixture/v1",
            "AXIO_NVIDIA_API_KEYS": "nvidia-fixture-key",
            "AXIO_NVIDIA_MODELS": "nvidia-fixture-model",
            "AXIO_TOKENAPIS_BASE_URL": "https://responses.fixture/v1",
            "AXIO_TOKENAPIS_API_KEY": "responses-fixture-key",
            "AXIO_TOKENAPIS_MODELS": "responses-fixture-model",
        },
    )

    by_provider = {profile.provider: profile for profile in profiles}
    nvidia = by_provider["nvidia"]
    tokenapis = by_provider["tokenapis"]

    assert nvidia.api_format == "chat"
    assert nvidia.reasoning_transport == {
        "status": "candidate",
        "transport": "chat_reasoning_effort",
        "supported_efforts": ["low", "medium", "high"],
        "effort_map": {"max": "high", "xhigh": "high"},
        "api_format_compatible": True,
    }
    assert tokenapis.api_format == "responses"
    assert tokenapis.reasoning_transport == {
        "status": "candidate",
        "transport": "responses_reasoning",
        "supported_efforts": ["low", "medium", "high"],
        "effort_map": {"max": "high", "xhigh": "high"},
        "api_format_compatible": True,
    }
    assert nvidia.resolve_reasoning_transport("high") == ("", "")
    assert tokenapis.resolve_reasoning_transport("high") == ("", "")


def test_runtime_discovery_and_probe_use_direct_credentials_for_all_protocols():
    server, thread = _start_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        discovery = discover_runtime_profiles(_manifest(base_url), timeout=3)
        profiles = discovery["profiles"]

        assert discovery["status"] == "ready"
        assert discovery["discovered_profile_count"] == 4
        assert {profile.model for profile in profiles} == {
            "chat-runtime-model",
            "responses-runtime-model",
            "anthropic-runtime-model",
            "models/gemini-runtime-model",
        }

        probe = probe_provider_models(profiles, live=True, timeout=3, max_workers=4)
        assert probe["available_count"] == 4
        assert {row["api_format"] for row in probe["probes"]} == {
            "chat",
            "responses",
            "anthropic",
            "gemini",
        }
        assert {row["status"] for row in probe["probes"]} == {"available"}
        assert len([row for row in _RuntimeChannelHandler.requests if row["method"] == "GET"]) == 4
        assert len([row for row in _RuntimeChannelHandler.requests if row["method"] == "POST"]) == 4
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_runtime_discovery_exposes_partial_channel_failure_as_safe_aggregate(monkeypatch):
    import axio_fusion_api.channel_config as channel_config

    def fake_list_models(profile, *, timeout):
        del timeout
        if profile.provider == "runtime-failed":
            return {
                "status": "failed",
                "error_type": "TimeoutError",
                "model_ids": [],
            }
        return {"status": "ok", "model_ids": ["runtime-healthy-model"]}

    monkeypatch.setattr(channel_config, "_safe_list_models", fake_list_models)
    discovery = discover_runtime_profiles(
        {
            "providers": [
                {
                    "provider": "runtime-healthy",
                    "api_format": "responses",
                    "base_url": "https://healthy.example/v1",
                    "api_key": "healthy-key",
                },
                {
                    "provider": "runtime-failed",
                    "api_format": "chat/completions",
                    "base_url": "https://failed.example/v1",
                    "api_key": "failed-key",
                },
            ]
        },
        timeout=3,
    )

    assert discovery["status"] == "ready"
    assert discovery["provider_count"] == 2
    assert discovery["successful_provider_count"] == 1
    assert discovery["failed_provider_count"] == 1
    assert discovery["warning_codes"] == ["provider_discovery_partial_failure"]
    assert discovery["report_status_counts"] == {"failed": 1, "ok": 1}
    safe_projection = json.dumps(
        {
            key: value
            for key, value in discovery.items()
            if key not in {"profiles", "reports"}
        },
        ensure_ascii=False,
    )
    assert "healthy.example" not in safe_projection
    assert "healthy-key" not in safe_projection


def test_runtime_engine_discovery_requires_explicit_live_flag():
    with pytest.raises(ValueError, match="discovery requires live=True"):
        FusionEngine.from_runtime_channels(
            {
                "providers": [
                    {
                        "provider": "runtime-discovery",
                        "api_format": "responses",
                        "base_url": "https://fixture.invalid/v1",
                        "api_key": "fixture-key",
                    }
                ]
            },
            discover=True,
        )


def test_runtime_engine_can_discover_with_explicit_live_flag():
    server, thread = _start_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        engine = FusionEngine.from_runtime_channels(
            {
                "providers": [
                    {
                        "provider": "runtime-engine-discovery",
                        "api_format": "responses",
                        "base_url": base_url,
                        "api_key": "responses-key",
                    }
                ]
            },
            discover=True,
            live=True,
            diagnostic_only=True,
            discovery_timeout=3,
            cache_enabled=False,
        )
        assert [profile.model for profile in engine.profiles] == [
            "responses-runtime-model"
        ]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_runtime_engine_discovery_cannot_promote_inventory_without_diagnostic_flag():
    with pytest.raises(ValueError, match="inventory-only"):
        FusionEngine.from_runtime_channels(
            {
                "providers": [
                    {
                        "provider": "runtime-engine-production-boundary",
                        "api_format": "responses",
                        "base_url": "https://fixture.invalid/v1",
                        "api_key": "responses-key",
                    }
                ]
            },
            discover=True,
            live=True,
        )


def test_runtime_engine_static_profiles_cannot_bypass_prefusion_without_diagnostic_flag():
    with pytest.raises(ValueError, match="direct runtime profile loading is diagnostic-only"):
        FusionEngine.from_runtime_channels(
            {
                "providers": [
                    {
                        "provider": "runtime-engine-production-static-boundary",
                        "api_format": "responses",
                        "base_url": "https://fixture.invalid/v1",
                        "api_key": "responses-key",
                        "models": ["fixture-model"],
                    }
                ]
            },
        )


def test_runtime_secret_resolver_and_summary_are_hash_only():
    manifest = {
        "providers": [
            {
                "provider": "resolver-channel",
                "api_format": "responses",
                "base_url_env": "RESOLVER_BASE_URL",
                "api_key_env": "RESOLVER_API_KEY",
                "models": ["resolver-model"],
            }
        ]
    }
    profiles = build_runtime_profiles(
        manifest,
        environment={"RESOLVER_BASE_URL": "https://resolver.example/v1"},
        secret_resolver=lambda name: "resolver-secret" if name == "RESOLVER_API_KEY" else None,
    )
    summary = runtime_channel_summary(profiles)
    serialized = json.dumps(summary, ensure_ascii=False)

    assert summary["profile_count"] == 1
    assert summary["credential_ready_profile_count"] == 1
    assert summary["canonical_model_group_count"] == 1
    assert "resolver.example" not in serialized
    assert "resolver-secret" not in serialized
    assert summary["secrets_persisted"] is False


def test_runtime_manifest_rejects_invalid_protocol_and_missing_credentials():
    with pytest.raises(ChannelConfigError):
        build_runtime_profiles(
            {
                "providers": [
                    {
                        "provider": "bad-protocol",
                        "api_format": "respones",
                        "base_url": "https://fixture.example/v1",
                        "api_key": "secret",
                        "models": ["model"],
                    }
                ]
            }
        )
    with pytest.raises(ChannelConfigError):
        build_runtime_profiles(
            {
                "providers": [
                    {
                        "provider": "missing-secret",
                        "api_format": "responses",
                        "base_url": "https://fixture.example/v1",
                        "models": ["model"],
                    }
                ]
            }
        )


def test_runtime_manifest_accepts_common_direct_channel_aliases_without_persisting_secrets():
    profiles = build_runtime_profiles(
        {
            "providers": [
                {
                    "channel": "alias-channel",
                    "protocol": "responses-api",
                    "baseurl": "https://alias.fixture/v1",
                    "apikey": ["alias-key-a", "alias-key-b"],
                    "models": [{"model_id": "alias-model"}],
                }
            ]
        }
    )

    assert len(profiles) == 1
    assert profiles[0].provider == "alias-channel"
    assert profiles[0].api_format == "responses"
    assert profiles[0].model == "alias-model"
    assert profiles[0].runtime_base_url == "https://alias.fixture/v1"
    assert profiles[0].runtime_api_keys == ("alias-key-a", "alias-key-b")
    safe = json.dumps(profiles[0].safe_dict(), ensure_ascii=False)
    assert "alias.fixture" not in safe
    assert "alias-key-a" not in safe
    assert "alias-key-b" not in safe


def test_runtime_manifest_resolves_models_env_and_sequence_secret_values():
    manifest = {
        "providers": [
            {
                "provider": "runtime-env-models",
                "api_format": "responses",
                "base_url_env": "RUNTIME_MODELS_BASE_URL",
                "api_key_env": "RUNTIME_MODELS_KEYS",
                "models": [{"model": "placeholder-model"}],
                "models_env": "RUNTIME_MODELS_LIST",
            }
        ]
    }
    profiles = build_runtime_profiles(
        manifest,
        environment={
            "RUNTIME_MODELS_BASE_URL": "https://runtime-models.example/v1",
            "RUNTIME_MODELS_LIST": "model-a, model-b, model-a",
        },
        secret_resolver=lambda name: (
            ("runtime-key-a", "runtime-key-b")
            if name == "RUNTIME_MODELS_KEYS"
            else None
        ),
    )

    assert [profile.model for profile in profiles] == [
        "placeholder-model",
        "model-a",
        "model-b",
    ]
    assert all(profile.runtime_api_keys == ("runtime-key-a", "runtime-key-b") for profile in profiles)
    safe = json.dumps([profile.safe_dict() for profile in profiles], ensure_ascii=False)
    assert "runtime-models.example" not in safe
    assert "runtime-key-a" not in safe
    assert "runtime-key-b" not in safe


def test_model_scoped_endpoint_and_key_references_override_channel_literals():
    manifest = {
        "providers": [
            {
                "provider": "scoped-runtime-channel",
                "api_format": "responses",
                "base_url": "https://channel-default.example/v1",
                "api_keys": ["channel-key-a", "channel-key-b"],
                "models": [
                    {
                        "model": "scoped-model",
                        "base_url_env": "SCOPED_MODEL_BASE_URL",
                        "api_key_env": "SCOPED_MODEL_KEYS",
                    },
                    {
                        "model": "direct-model",
                        "base_url": "https://model-direct.example/v1",
                        "api_key": "model-direct-key",
                    },
                ],
            }
        ]
    }

    profiles = build_runtime_profiles(
        manifest,
        environment={"SCOPED_MODEL_BASE_URL": "https://model-scoped.example/v1"},
        secret_resolver=lambda name: (
            ("scoped-key-a", "scoped-key-b")
            if name == "SCOPED_MODEL_KEYS"
            else None
        ),
    )
    by_model = {profile.model: profile for profile in profiles}

    assert by_model["scoped-model"].runtime_base_url == "https://model-scoped.example/v1"
    assert by_model["scoped-model"].runtime_api_keys == ("scoped-key-a", "scoped-key-b")
    assert by_model["direct-model"].runtime_base_url == "https://model-direct.example/v1"
    assert by_model["direct-model"].runtime_api_keys == ("model-direct-key",)
    safe = json.dumps([profile.safe_dict() for profile in profiles], ensure_ascii=False)
    assert "channel-default.example" not in safe
    assert "model-scoped.example" not in safe
    assert "scoped-key-a" not in safe
    assert "model-direct-key" not in safe


def test_secret_resolver_key_pool_is_used_for_transport_failover():
    server, thread = _start_server()
    original_models = dict(_RuntimeChannelHandler.model_by_key)
    _RuntimeChannelHandler.model_by_key = {
        **original_models,
        "resolver-good-key": "resolver-model",
    }
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        profiles = build_runtime_profiles(
            {
                "providers": [
                    {
                        "provider": "resolver-transport",
                        "api_format": "responses",
                        "base_url_env": "RESOLVER_TRANSPORT_BASE_URL",
                        "api_key_env": "RESOLVER_TRANSPORT_KEYS",
                        "models": ["resolver-model"],
                    }
                ]
            },
            secret_resolver=lambda name: {
                "RESOLVER_TRANSPORT_BASE_URL": base_url,
                "RESOLVER_TRANSPORT_KEYS": ("resolver-bad-key", "resolver-good-key"),
            }.get(name),
        )
        assert len(profiles) == 1

        request = FusionRequest(model="axio-fast", prompt="hello")
        result = HTTPProviderClient().complete(
            profiles[0],
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=5,
        )

        assert result == "AXIO_PROBE_OK"
        posts = [
            row
            for row in _RuntimeChannelHandler.requests
            if row["method"] == "POST"
        ]
        assert [row["key"] for row in posts] == [
            "resolver-bad-key",
            "resolver-good-key",
        ]
    finally:
        _RuntimeChannelHandler.model_by_key = original_models
        server.shutdown()
        thread.join(timeout=2)


def test_secret_resolver_drives_discovery_enrollment_and_atomic_refresh():
    upstream, upstream_thread = _start_server()
    gateway = None
    try:
        base_url = f"http://127.0.0.1:{upstream.server_port}/v1"

        def resolver(name: str):
            return {
                "ENROLL_BASE_URL": base_url,
                "ENROLL_API_KEY": "responses-key",
                "REFRESH_BASE_URL": base_url,
                "REFRESH_API_KEY": "chat-key",
            }.get(name)

        gateway = create_runtime_http_server(
            {
                "providers": [
                    {
                        "provider": "resolver-enrollment",
                        "api_format": "responses",
                        "base_url_env": "ENROLL_BASE_URL",
                        "api_key_env": "ENROLL_API_KEY",
                    }
                ]
            },
            port=0,
            live=True,
            enroll=True,
            diagnostic_only=True,
            enrollment_calibrate_tools=False,
            secret_resolver=resolver,
            record_trace=False,
            record_runtime=False,
        )

        assert gateway.runtime_channel_enrollment_receipt["status"] == "ready"
        assert [profile.api_format for profile in gateway.axio_engine.profiles] == [
            "responses"
        ]
        assert gateway.axio_engine.profiles[0].runtime_api_keys == ("responses-key",)

        refresh = gateway.refresh_runtime_channels(
            {
                "providers": [
                    {
                        "provider": "resolver-refresh",
                        "api_format": "chat/completions",
                        "base_url_env": "REFRESH_BASE_URL",
                        "api_key_env": "REFRESH_API_KEY",
                    }
                ]
            },
            expected_generation=0,
            secret_resolver=resolver,
            enrollment_calibrate_tools=False,
        )

        assert refresh["status"] == "ready"
        assert refresh["activation"]["generation"] == 1
        assert [profile.api_format for profile in gateway.axio_engine.profiles] == ["chat"]
        assert gateway.axio_engine.profiles[0].runtime_api_keys == ("chat-key",)
        serialized = json.dumps(refresh, ensure_ascii=False)
        assert base_url not in serialized
        assert "responses-key" not in serialized
        assert "chat-key" not in serialized
        assert refresh["secrets_persisted"] is False
    finally:
        if gateway is not None:
            gateway.server_close()
        upstream.shutdown()
        upstream_thread.join(timeout=2)


def test_secret_resolver_exception_is_redacted_at_configuration_boundary():
    secret_fragment = "must-not-escape-secret-fragment"

    def failing_resolver(_name: str):
        raise RuntimeError(secret_fragment)

    with pytest.raises(ChannelConfigError) as exc_info:
        build_runtime_profiles(
            {
                "providers": [
                    {
                        "provider": "resolver-failure",
                        "api_format": "responses",
                        "base_url_env": "RESOLVER_FAILURE_BASE_URL",
                        "api_key_env": "RESOLVER_FAILURE_API_KEY",
                        "models": ["resolver-failure-model"],
                    }
                ]
            },
            secret_resolver=failing_resolver,
        )

    assert str(exc_info.value) == "runtime secret resolver failed"
    assert secret_fragment not in str(exc_info.value)


def test_runtime_manifest_supports_custom_model_catalog_and_static_no_discovery(monkeypatch):
    import axio_fusion_api.channel_config as channel_config

    observed: list[tuple[str, str, bool]] = []

    def fake_list_models(profile, *, timeout):
        del timeout
        observed.append((profile.provider, profile.models_endpoint, profile.discover_models))
        if profile.provider == "custom-catalog":
            return {"status": "ok", "model_ids": ["catalog-model"]}
        return {
            "status": "skipped",
            "reason_codes": ["model_discovery_disabled"],
            "model_ids": [],
        }

    monkeypatch.setattr(channel_config, "_safe_list_models", fake_list_models)
    discovery = discover_runtime_profiles(
        {
            "providers": [
                {
                    "provider": "custom-catalog",
                    "api_format": "responses",
                    "base_url": "https://catalog.example/v1",
                    "api_key": "catalog-key",
                    "models_endpoint": "/catalog/models",
                },
                {
                    "provider": "anthropic-static",
                    "api_format": "anthropic",
                    "base_url": "https://messages.example/v1",
                    "api_key": "messages-key",
                    "discover_models": False,
                    "models": ["messages-model"],
                },
            ]
        }
    )

    assert {profile.model for profile in discovery["profiles"]} == {
        "catalog-model",
        "messages-model",
    }
    assert ("custom-catalog", "/catalog/models", True) in observed
    assert ("anthropic-static", "/models", False) in observed
    assert discovery["report_status_counts"] == {"ok": 1, "skipped": 1}
    assert discovery["failed_provider_count"] == 0
    assert discovery["skipped_provider_count"] == 1
    safe = json.dumps(
        {key: value for key, value in discovery.items() if key not in {"profiles", "reports"}},
        ensure_ascii=False,
    )
    assert "catalog.example" not in safe
    assert "catalog-key" not in safe
    assert "messages-key" not in safe


def test_runtime_manifest_rejects_literal_models_env_name():
    with pytest.raises(ChannelConfigError, match="models_env"):
        build_runtime_profiles(
            {
                "providers": [
                    {
                        "provider": "invalid-model-env",
                        "api_format": "responses",
                        "base_url": "https://fixture.example/v1",
                        "api_key": "fixture-key",
                        "models_env": "model-a,model-b",
                    }
                ]
            }
        )


def test_current_channel_manifest_binds_the_three_supplied_channels_without_secrets():
    manifest_path = ROOT / "config" / "current_channels.example.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert [row["provider"] for row in manifest["providers"]] == ["nvidia", "tokenapis"]
    assert [row["api_format"] for row in manifest["providers"]] == [
        "chat/completions",
        "responses",
    ]
    assert all("base_url" not in row and "api_key" not in row for row in manifest["providers"])
    assert manifest["providers"][0]["reasoning_transport"]["transport"] == "chat_reasoning_effort"
    assert manifest["providers"][1]["reasoning_transport"]["transport"] == "responses_reasoning"
    assert all(
        row["reasoning_transport"]["effort_map"] == {"xhigh": "high", "max": "high"}
        for row in manifest["providers"]
    )
    assert all(
        row["reasoning_transport"]["status"] == "candidate"
        for row in manifest["providers"]
    )
    env_example = (ROOT / "config" / "current_channels.env.example").read_text(encoding="utf-8")
    assert "https://integrate.api.nvidia.com/v1" in env_example
    assert "https://tokenapis.com/v1" in env_example
    assert "sk-" not in env_example
    assert "nvapi-" not in env_example


def test_current_channel_reasoning_candidates_propagate_to_models_env_rows():
    manifest_path = ROOT / "config" / "current_channels.example.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = build_runtime_profiles(
        manifest,
        environment={
            "AXIO_NVIDIA_BASE_URL": "https://nvidia.fixture/v1",
            "AXIO_NVIDIA_API_KEYS": "nvidia-fixture-key",
            "AXIO_NVIDIA_MODELS": "candidate-chat-model",
            "AXIO_TOKENAPIS_BASE_URL": "https://tokenapis.fixture/v1",
            "AXIO_TOKENAPIS_API_KEY": "tokenapis-fixture-key",
            "AXIO_TOKENAPIS_MODELS": "candidate-responses-model",
        },
    )
    by_provider = {profile.provider: profile for profile in profiles}

    assert by_provider["nvidia"].reasoning_transport["status"] == "candidate"
    assert by_provider["nvidia"].reasoning_transport["transport"] == "chat_reasoning_effort"
    assert by_provider["nvidia"].reasoning_transport["effort_map"] == {
        "max": "high",
        "xhigh": "high",
    }
    assert by_provider["tokenapis"].reasoning_transport["status"] == "candidate"
    assert by_provider["tokenapis"].reasoning_transport["transport"] == "responses_reasoning"
    assert by_provider["tokenapis"].reasoning_transport["effort_map"] == {
        "max": "high",
        "xhigh": "high",
    }


def test_runtime_http_server_can_enroll_discovered_four_protocol_channels():
    server, thread = _start_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        gateway = create_runtime_http_server(
            _manifest(base_url),
            port=0,
            live=True,
            enroll=True,
            diagnostic_only=True,
            enrollment_max_workers=4,
            enrollment_calibrate_tools=True,
            enrollment_tool_probe_timeout=3,
            enrollment_tool_probe_max_models=4,
            enrollment_tool_probe_max_models_per_provider=1,
            record_trace=False,
            record_runtime=False,
        )

        assert len(gateway.axio_engine.profiles) == 4
        assert gateway.runtime_channel_enrollment_receipt["status"] == "ready"
        assert gateway.runtime_channel_enrollment_receipt["admission_mode"] == "diagnostic_stream_probe"
        assert gateway.runtime_channel_enrollment_receipt["production_admission"] is False
        assert gateway.runtime_channel_enrollment_receipt["available_logical_model_count"] == 4
        assert gateway.runtime_channel_enrollment_receipt["network_calls_performed"] is True
        serialized_receipt = json.dumps(gateway.runtime_channel_enrollment_receipt, ensure_ascii=False)
        assert base_url not in serialized_receipt
        assert "chat-key" not in serialized_receipt
        gateway.server_close()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_runtime_http_server_rejects_network_discovery_without_live():
    with pytest.raises(ValueError, match="discovery requires live=True"):
        create_runtime_http_server(
            {
                "providers": [
                    {
                        "provider": "runtime-discovery",
                        "api_format": "responses",
                        "base_url": "https://fixture.invalid/v1",
                        "api_key": "fixture-key",
                    }
                ]
            },
            live=False,
            discover=True,
        )


def test_runtime_http_server_requires_prefusion_for_production_enrollment(monkeypatch):
    observed: dict[str, object] = {}

    def fake_enroll(_manifest, **kwargs):
        observed.update(kwargs)
        return {
            "status": "blocked",
            "engine": None,
            "receipt": {
                "status": "blocked",
                "reason_codes": ["prefusion_screening_blocked"],
            },
        }

    monkeypatch.setattr(
        "axio_fusion_api.provider_enrollment.enroll_runtime_channels",
        fake_enroll,
    )
    with pytest.raises(ValueError, match="produced no serving profiles"):
        create_runtime_http_server(
            {
                "providers": [
                    {
                        "provider": "production-admission-boundary",
                        "api_format": "responses",
                        "base_url": "https://fixture.invalid/v1",
                        "api_key": "fixture-key",
                        "models": ["fixture-model"],
                    }
                ]
            },
            live=True,
            enroll=True,
            record_trace=False,
            record_runtime=False,
        )
    assert observed["require_prefusion"] is True
    assert observed["diagnostic_only"] is False


def test_runtime_refresh_forwards_multi_sample_prefusion_setting(monkeypatch):
    profile = build_runtime_profiles(
        {
            "providers": [
                {
                    "provider": "refresh-stability-fixture",
                    "api_format": "responses",
                    "base_url": "https://refresh-stability.example/v1",
                    "api_key": "fixture-key",
                    "models": ["refresh-stability-model"],
                }
            ]
        }
    )[0]
    active_engine = FusionEngine([profile], cache_enabled=False)
    candidate_engine = FusionEngine([profile], cache_enabled=False)
    gateway = create_http_server(
        port=0,
        live=True,
        engine=active_engine,
        record_trace=False,
        record_runtime=False,
    )
    observed: dict[str, object] = {}

    def fake_enroll(_manifest, **kwargs):
        observed.update(kwargs)
        return {
            "status": "ready",
            "engine": candidate_engine,
            "receipt": {"status": "ready", "reason_codes": []},
        }

    monkeypatch.setattr(
        "axio_fusion_api.provider_enrollment.enroll_runtime_channels",
        fake_enroll,
    )
    try:
        refresh = gateway.refresh_runtime_channels(
            {"providers": []},
            expected_generation=0,
            prefusion_stream_probe_samples=4,
        )
    finally:
        gateway.server_close()

    assert refresh["status"] == "ready"
    assert observed["prefusion_stream_probe_samples"] == 4


def test_runtime_http_server_cannot_bypass_required_prefusion_with_static_profiles():
    manifest = {
        "providers": [
            {
                "provider": "static-prefusion-required",
                "api_format": "responses",
                "base_url": "https://provider.invalid/v1",
                "api_key": "fixture-key",
                "models": ["fixture-model"],
            }
        ]
    }
    with pytest.raises(ValueError, match="pre-Fusion screening requires enroll=True"):
        create_runtime_http_server(
            manifest,
            live=False,
            require_prefusion=True,
        )


def test_runtime_http_server_cannot_bypass_manifest_prefusion_with_discovery():
    manifest = {
        "prefusion": {},
        "providers": [
            {
                "provider": "manifest-prefusion-required",
                "api_format": "responses",
                "base_url": "https://provider.invalid/v1",
                "api_key": "fixture-key",
                "models": ["fixture-model"],
            }
        ],
    }
    with pytest.raises(ValueError, match="pre-Fusion screening requires enroll=True"):
        create_runtime_http_server(
            manifest,
            live=True,
            discover=True,
        )


def test_runtime_http_gateway_bridges_four_upstream_and_public_protocols(monkeypatch):
    """Exercise the real gateway boundary across all four protocol families."""

    monkeypatch.delenv("AXIO_FUSION_API_KEYS", raising=False)
    upstream, upstream_thread = _start_server()
    gateway = None
    gateway_thread = None
    try:
        base_url = f"http://127.0.0.1:{upstream.server_port}/v1"
        gateway = create_runtime_http_server(
            _manifest(base_url),
            host="127.0.0.1",
            port=0,
            live=True,
            enroll=True,
            diagnostic_only=True,
            enrollment_max_workers=4,
            enrollment_calibrate_tools=True,
            record_trace=False,
            record_runtime=False,
        )
        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        public_base = f"http://127.0.0.1:{gateway.server_address[1]}"
        requests = [
            (
                "/v1/chat/completions",
                {"model": "axio-fast", "messages": [{"role": "user", "content": "hello"}]},
                lambda body: body["choices"][0]["message"]["content"],
            ),
            (
                "/v1/responses",
                {"model": "axio-fast", "input": "hello"},
                lambda body: body["output_text"],
            ),
            (
                "/v1/messages",
                {
                    "model": "axio-fast",
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "hello"}],
                },
                lambda body: body["content"][0]["text"],
            ),
            (
                "/v1beta/models/axio-fast:generateContent",
                {
                    "contents": [
                        {"role": "user", "parts": [{"text": "hello"}]},
                    ]
                },
                lambda body: body["candidates"][0]["content"]["parts"][0]["text"],
            ),
        ]
        for path, payload, extract_text in requests:
            request = Request(
                public_base + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=10) as response:
                assert response.status == 200
                body = json.loads(response.read().decode("utf-8"))
            assert extract_text(body) == "AXIO_PROBE_OK"
        assert gateway.runtime_channel_enrollment_receipt["status"] == "ready"
        assert len(gateway.axio_engine.profiles) == 4
    finally:
        if gateway is not None:
            gateway.shutdown()
            gateway.server_close()
        if gateway_thread is not None:
            gateway_thread.join(timeout=2)
        upstream.shutdown()
        upstream_thread.join(timeout=2)
