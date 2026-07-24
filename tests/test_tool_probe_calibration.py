from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.calibration import build_registry_calibration
from axio_fusion_api.providers import (
    TOOL_PROBE_NAME,
    TOOL_PROBE_VALUE,
    probe_provider_tool_support,
    redact_provider_tool_probe_artifact,
)
from axio_fusion_api import providers as provider_module
from axio_fusion_api.registry import normalize_profile


class _Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _tool_response(api_format: str) -> dict:
    arguments = json.dumps({"value": TOOL_PROBE_VALUE}, separators=(",", ":"))
    if api_format == "responses":
        return {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "probe-call",
                    "name": TOOL_PROBE_NAME,
                    "arguments": arguments,
                }
            ]
        }
    if api_format == "anthropic":
        return {
            "content": [
                {
                    "type": "tool_use",
                    "id": "probe-call",
                    "name": TOOL_PROBE_NAME,
                    "input": {"value": TOOL_PROBE_VALUE},
                }
            ]
        }
    if api_format == "gemini":
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": TOOL_PROBE_NAME,
                                    "args": {"value": TOOL_PROBE_VALUE},
                                }
                            }
                        ]
                    }
                }
            ]
        }
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "probe-call",
                            "type": "function",
                            "function": {
                                "name": TOOL_PROBE_NAME,
                                "arguments": arguments,
                            },
                        }
                    ]
                }
            }
        ]
    }


def test_tool_probe_forces_declaration_and_normalizes_all_four_upstream_formats(monkeypatch):
    captured = []
    profiles = []
    for index, api_format in enumerate(("chat", "responses", "anthropic", "gemini")):
        base_env = f"TOOL_PROBE_{index}_BASE_URL"
        key_env = f"TOOL_PROBE_{index}_API_KEY"
        monkeypatch.setenv(base_env, f"https://tool-probe-{index}.example/v1")
        monkeypatch.setenv(key_env, f"tool-key-{index}")
        profiles.append(
            normalize_profile(
                {
                    "provider": f"tool-provider-{index}",
                    "model": f"tool-model-{index}",
                    "api_format": api_format,
                    "base_url_env": base_env,
                    "api_key_env": key_env,
                    "supports_tools": False,
                }
            )
        )

    def format_aware_urlopen(request, timeout=None):
        payload = json.loads((request.data or b"{}").decode("utf-8"))
        captured.append((request.full_url, payload))
        if request.full_url.endswith("/chat/completions"):
            api_format = "chat"
        elif request.full_url.endswith("/responses"):
            api_format = "responses"
        elif request.full_url.endswith("/messages"):
            api_format = "anthropic"
        else:
            api_format = "gemini"
        return _Response(_tool_response(api_format))

    class FakeOpener:
        def open(self, request, timeout=None):
            return format_aware_urlopen(request, timeout=timeout)

    monkeypatch.setattr(provider_module, "build_network_opener", lambda: FakeOpener())
    report = probe_provider_tool_support(profiles, live=True, max_workers=1, timeout=3.0)

    assert report["schema"] == "axio_fusion_api.provider_tool_probe.v1"
    assert report["tool_call_supported_count"] == 4
    assert all(row["status"] == "tool_call_supported" for row in report["probes"])
    assert all(row["argument_parseable"] is True for row in report["probes"])
    assert all(row["raw_tool_arguments_persisted"] is False for row in report["probes"])
    assert len(captured) == 4
    for _, payload in captured:
        assert payload.get("tools")
        assert payload.get("stream") is True or "stream" not in payload
    assert all("tool-key-" not in json.dumps(row) for row in report["probes"])


def test_tool_probe_distinguishes_text_only_from_invalid_native_call(monkeypatch):
    mode = ["text"]

    def fake_urlopen(request, timeout=None):
        if mode[0] == "text":
            return _Response({"choices": [{"message": {"content": "plain response"}}]})
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "bad-call",
                                    "function": {
                                        "name": TOOL_PROBE_NAME,
                                        "arguments": "not-json",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

    class FakeOpener:
        def open(self, request, timeout=None):
            return fake_urlopen(request, timeout=timeout)

    monkeypatch.setattr(provider_module, "build_network_opener", lambda: FakeOpener())
    monkeypatch.setenv("TOOL_TEXT_BASE_URL", "https://tool-text.example/v1")
    monkeypatch.setenv("TOOL_TEXT_API_KEY", "tool-text-key")
    profile = normalize_profile(
        {
            "provider": "tool-text-provider",
            "model": "tool-text-model",
            "api_format": "chat",
            "base_url_env": "TOOL_TEXT_BASE_URL",
            "api_key_env": "TOOL_TEXT_API_KEY",
        }
    )

    text_report = probe_provider_tool_support([profile], live=True, max_workers=1)
    assert text_report["probes"][0]["status"] == "text_only"
    mode[0] = "invalid"
    invalid_report = probe_provider_tool_support([profile], live=True, max_workers=1)
    assert invalid_report["probes"][0]["status"] == "tool_call_unparseable"
    assert invalid_report["probes"][0]["argument_parseable"] is False


def test_tool_probe_calibration_updates_supports_tools_without_benchmark_signal(tmp_path):
    profile = normalize_profile(
        {
            "provider": "calibration-provider",
            "model": "calibration-model",
            "canonical_model_id": "calibration-model-family-v1",
            "api_format": "chat",
            "supports_tools": False,
            "capabilities": {"agentic_tool_calling": 0.4},
        }
    )
    registry_path = tmp_path / "registry.json"
    model_row = profile.safe_dict()
    model_row["canonical_model_id"] = profile.canonical_model_id
    registry_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.registry.v1",
                "generated_from_probe": True,
                "source_artifacts": {
                    "probe_file_path_hashes": ["probe-path-hash"],
                    "status_counts": {"available": 1},
                },
                "readiness": {
                    "live_probe_proven": True,
                    "final_claim_registry_ready": True,
                },
                "generation_contract": {"live_probe_evidence_required_for_final_claims": True},
                    "models": [model_row],
            }
        ),
        encoding="utf-8",
    )
    probe_path = tmp_path / "tool-probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_tool_probe.v1",
                "probe_kind": "tool_call",
                "probes": [
                    {
                        "profile_id": profile.profile_id,
                        "provider": profile.provider,
                        "model": profile.model,
                        "status": "tool_call_supported",
                        "latency_ms": 12,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calibration = build_registry_calibration(
        registry_path=registry_path,
        probe_paths=[probe_path],
    )
    patch = calibration["patches"][0]
    updated = calibration["updated_registry"]["models"][0]
    assert calibration["input_artifacts"]["tool_probe_row_count"] == 1
    assert patch["supports_tools_patch"] is True
    assert patch["signal_counts"]["tool_call_supported_count"] == 1
    assert updated["supports_tools"] is True
    assert updated["calibration"]["supports_tools_updated_from_operational_probe"] is True
    assert updated["capabilities"]["agentic_tool_calling"] > 0.4
    assert updated["canonical_model_id"] == profile.canonical_model_id
    assert calibration["updated_registry"]["generated_from_probe"] is True
    assert calibration["updated_registry"]["source_artifacts"]["probe_file_path_hashes"] == ["probe-path-hash"]
    assert calibration["updated_registry"]["readiness"]["live_probe_proven"] is True
    assert calibration["updated_registry"]["generation_contract"]["live_probe_evidence_required_for_final_claims"] is True


def test_tool_probe_redaction_removes_provider_and_tool_details():
    payload = {
        "schema": "axio_fusion_api.provider_tool_probe.v1",
        "probe_kind": "tool_call",
        "probes": [
            {
                "profile_id": "private-provider/private-model",
                "provider": "private-provider",
                "model": "private-model",
                "status": "tool_call_supported",
                "tool_call_name_sha256s": ["hash"],
                "raw_tool_arguments": {"secret": "must-not-appear"},
            }
        ],
    }
    redacted = redact_provider_tool_probe_artifact(payload)
    serialized = json.dumps(redacted)
    assert "private-provider" not in serialized
    assert "private-model" not in serialized
    assert "must-not-appear" not in serialized
    assert redacted["probes"][0]["raw_tool_arguments_persisted"] is False
