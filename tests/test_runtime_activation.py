from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.orchestrator import FusionEngine  # noqa: E402
from axio_fusion_api.runtime_activation import AtomicFusionRuntime  # noqa: E402
from axio_fusion_api.schemas import ModelProfile  # noqa: E402
from axio_fusion_api.server import create_http_server  # noqa: E402
from axio_fusion_api.provider_enrollment import _apply_runtime_tool_probe  # noqa: E402


def _engine(provider: str, model: str, *, health: str = "available") -> FusionEngine:
    return FusionEngine(
        [
            ModelProfile(
                provider=provider,
                model=model,
                health=health,
                base_url_env=f"{provider.upper()}_BASE_URL",
                api_key_env=f"{provider.upper()}_API_KEY",
            )
        ],
        cache_enabled=False,
    )


def test_atomic_runtime_swaps_only_complete_candidate_and_supports_generation_fenced_rollback():
    first = _engine("provider-a", "model-a")
    second = _engine("provider-b", "model-b")
    runtime = AtomicFusionRuntime(first)

    initial = runtime.safe_snapshot()
    assert initial["generation"] == 0
    assert initial["profile_count"] == 1

    blocked = runtime.swap(
        _engine("provider-b", "model-b", health="unavailable"),
        expected_generation=0,
    )
    assert blocked["status"] == "blocked"
    assert blocked["old_engine_preserved"] is True
    assert runtime.snapshot()[0] is first

    activated = runtime.swap(second, expected_generation=0, reason="channel_refresh")
    assert activated["status"] == "ready"
    assert activated["generation"] == 1
    assert activated["atomic"] is True
    assert runtime.snapshot()[0] is second
    serialized = json.dumps(activated, ensure_ascii=False)
    assert "provider-a" not in serialized
    assert "provider-b" not in serialized
    assert activated["active"]["profile_set_sha256"]

    conflict = runtime.swap(first, expected_generation=0)
    assert conflict["status"] == "blocked"
    assert runtime.snapshot()[0] is second

    rolled_back = runtime.rollback(expected_generation=1)
    assert rolled_back["status"] == "ready"
    assert rolled_back["generation"] == 2
    assert runtime.snapshot()[0] is first


def test_atomic_runtime_rejects_empty_or_disabled_candidates():
    first = _engine("provider-a", "model-a")
    runtime = AtomicFusionRuntime(first)
    empty = runtime.swap(FusionEngine([], cache_enabled=False))
    assert empty["status"] == "blocked"
    disabled = FusionEngine(
        [ModelProfile(provider="provider-b", model="model-b", enabled=False)],
        cache_enabled=False,
    )
    rejected = runtime.swap(disabled)
    assert rejected["status"] == "blocked"
    assert runtime.snapshot()[0] is first


def test_http_server_dispatches_through_atomic_runtime_handle():
    first = _engine("provider-a", "model-a")
    second = _engine("provider-b", "model-b")
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        engine=first,
        record_trace=False,
        record_runtime=False,
    )
    try:
        assert server.runtime_engine_snapshot()["generation"] == 0
        receipt = server.swap_engine(second, expected_generation=0)
        assert receipt["status"] == "ready"
        assert server.runtime_engine_snapshot()["generation"] == 1
        assert server.axio_engine is second
        rollback = server.rollback_engine(expected_generation=1)
        assert rollback["status"] == "ready"
        assert server.axio_engine is first
    finally:
        server.server_close()


def test_atomic_runtime_rollback_without_history_is_blocked():
    runtime = AtomicFusionRuntime(_engine("provider-a", "model-a"))
    result = runtime.rollback()
    assert result["status"] == "blocked"
    assert "runtime_rollback_unavailable" in result["reason_codes"]


def test_runtime_tool_capability_state_distinguishes_proven_failed_and_unprobed():
    profiles = [
        ModelProfile(provider="tool", model="proven", supports_tools=False),
        ModelProfile(provider="tool", model="failed", supports_tools=False),
        ModelProfile(provider="tool", model="unprobed", supports_tools=False),
        ModelProfile(
            provider="tool",
            model="attested",
            supports_tools=True,
            tool_capability_source="external_attestation",
        ),
    ]
    updated = _apply_runtime_tool_probe(
        profiles,
        [
            {
                "profile_id": "tool/proven",
                "status": "tool_call_supported",
            },
            {
                "profile_id": "tool/failed",
                "status": "transport_failure",
            },
            {
                "profile_id": "tool/attested",
                "status": "protocol_failure",
            },
        ],
    )
    by_model = {profile.model: profile for profile in updated}
    assert by_model["proven"].tool_capability == "proven"
    assert by_model["proven"].tool_calling_eligible is True
    assert by_model["failed"].tool_capability == "failed"
    assert by_model["failed"].tool_calling_eligible is False
    assert by_model["unprobed"].tool_capability == "unproven"
    assert by_model["unprobed"].tool_probe_status == "not_run"
    assert by_model["unprobed"].tool_calling_eligible is False
    assert by_model["attested"].tool_capability == "failed"
    assert by_model["attested"].supports_tools is True
    assert by_model["attested"].tool_calling_eligible is False


def test_runtime_refresh_atomically_replaces_only_a_ready_enrollment(monkeypatch):
    first_client = object()
    first = FusionEngine(
        [
            ModelProfile(
                provider="provider-a",
                model="model-a",
                health="available",
            )
        ],
        client=first_client,
        cache_enabled=True,
        circuit_breaker_threshold=7,
    )
    second = FusionEngine(
        [
            ModelProfile(
                provider="provider-b",
                model="model-b",
                health="available",
            )
        ],
        client=first_client,
        cache_enabled=True,
        circuit_breaker_threshold=7,
    )
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        engine=first,
        record_trace=False,
        record_runtime=False,
    )
    observed = {}

    def fake_enroll(manifest, **kwargs):
        observed["manifest"] = manifest
        observed["client"] = kwargs["client"]
        observed["engine_kwargs"] = kwargs["engine_kwargs"]
        return {
            "status": "ready",
            "engine": second,
            "receipt": {
                "schema": "axio_fusion_api.runtime_channel_enrollment.v1",
                "status": "ready",
                "discovered_profile_count": 1,
                "available_profile_count": 1,
                "profile_set_sha256": "b" * 64,
                "raw_provider_names_persisted": False,
                "raw_provider_model_ids_persisted": False,
                "raw_provider_urls_persisted": False,
                "raw_api_keys_persisted": False,
                "secrets_persisted": False,
            },
        }

    monkeypatch.setattr(
        "axio_fusion_api.provider_enrollment.enroll_runtime_channels",
        fake_enroll,
    )
    try:
        result = server.refresh_runtime_channels(
            {"providers": [{"provider": "new-channel"}]},
            expected_generation=0,
        )
        assert result["status"] == "ready"
        assert result["activation"]["generation"] == 1
        assert server.axio_engine is second
        assert observed["client"] is first_client
        assert observed["engine_kwargs"] == {
            "cache_enabled": True,
            "circuit_breaker_threshold": 7,
        }
        serialized = json.dumps(result, ensure_ascii=False)
        assert "new-channel" not in serialized
        assert "model-b" not in serialized
    finally:
        server.server_close()


def test_runtime_refresh_failure_and_generation_conflict_preserve_old_engine(monkeypatch):
    first = _engine("provider-a", "model-a")
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        engine=first,
        record_trace=False,
        record_runtime=False,
    )
    calls = {"count": 0}

    def fake_enroll(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "status": "blocked",
            "engine": None,
            "receipt": {
                "status": "blocked",
                "reason_codes": ["insufficient_live_available_profiles"],
                "provider": "must-not-leak",
                "model": "must-not-leak",
            },
        }

    monkeypatch.setattr(
        "axio_fusion_api.provider_enrollment.enroll_runtime_channels",
        fake_enroll,
    )
    try:
        conflict = server.refresh_runtime_channels(
            {"providers": []},
            expected_generation=99,
        )
        assert conflict["status"] == "blocked"
        assert "runtime_generation_conflict" in conflict["reason_codes"]
        assert calls["count"] == 0
        assert server.runtime_engine_snapshot()["generation"] == 0

        failed = server.refresh_runtime_channels(
            {"providers": []},
            expected_generation=0,
        )
        assert failed["status"] == "blocked"
        assert failed["old_engine_preserved"] is True
        assert server.runtime_engine_snapshot()["generation"] == 0
        assert server.axio_engine is first
        serialized = json.dumps(failed, ensure_ascii=False)
        assert "must-not-leak" not in serialized
    finally:
        server.server_close()
