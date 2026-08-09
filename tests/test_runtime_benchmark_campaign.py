from __future__ import annotations

import json
import sys
from pathlib import Path


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.channel_config import build_runtime_profiles
from axio_fusion_api.evaluation import (
    run_multiple_choice_benchmark,
    run_runtime_benchmark_campaign,
)
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.provider_enrollment import enroll_runtime_channels
from axio_fusion_api.providers import ProviderCompletion
from axio_fusion_api.server import create_runtime_http_server


class _BenchmarkClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def complete(self, profile, request, *, prompt, system, timeout=None):
        self.calls.append(
            {
                "profile_id": profile.profile_id,
                "api_format": profile.api_format,
                "prompt": prompt,
                "system": system,
            }
        )
        return "AXIO_PROBE_OK" if "AXIO_PROBE_OK" in prompt else "B"

    def complete_turn(self, profile, request, *, prompt, system, timeout=None):
        self.calls.append(
            {
                "profile_id": profile.profile_id,
                "api_format": profile.api_format,
                "prompt": prompt,
                "system": system,
            }
        )
        if not request.tools:
            return ProviderCompletion(text="B")
        del request, timeout
        return ProviderCompletion(
            text="",
            tool_calls=(
                {
                    "name": "axio_probe_echo",
                    "arguments": {"value": "AXIO_TOOL_PROBE_OK"},
                },
            ),
        )


def _runtime_manifest() -> dict:
    return {
        "providers": [
            {
                "provider": "runtime-responses",
                "api_format": "responses",
                "base_url": "https://runtime.responses.example/v1",
                "api_key": "runtime-secret-key",
                "models": [
                    {
                        "model": "runtime-reasoner",
                        "canonical_model_id": "runtime-reasoner",
                        "capabilities": {
                            "science_knowledge": 0.90,
                            "logic": 0.90,
                            "structured_output": 0.90,
                            "critique": 0.85,
                            "daily_work": 0.90,
                        },
                    }
                ],
            }
        ]
    }


def test_runtime_engine_is_used_by_all_public_benchmark_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_API_KEYS", "local-benchmark-key")
    dataset_path = tmp_path / "fixture.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "question": "Which option is correct?",
                "options": ["wrong", "correct", "also wrong"],
                "answer": "B",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    client = _BenchmarkClient()
    profiles = build_runtime_profiles(_runtime_manifest())
    engine = FusionEngine(profiles, client=client, cache_enabled=False)

    runs = []
    for api_format in ("chat/completions", "responses", "anthropic", "gemini"):
        run = run_multiple_choice_benchmark(
            suite_id="arc_challenge",
            dataset_path=dataset_path,
            candidate_id="axio-fast",
            api_format=api_format,
            live=True,
            engine=engine,
            max_latency_ms=15_000,
        )
        assert run["correct_count"] == 1
        assert run["case_results"][0]["public_api_invocation"]["api_format"] == api_format
        assert run["case_results"][0]["public_api_invocation"]["transport"] == "in_process_public_endpoint"
        runs.append(run)

    serialized = json.dumps(runs, ensure_ascii=False)
    assert "runtime-secret-key" not in serialized
    assert "runtime.responses.example" not in serialized
    assert "Which option is correct?" not in serialized
    assert len(client.calls) == 4
    assert all(call["profile_id"] == "runtime-responses/runtime-reasoner" for call in client.calls)


def test_benchmark_exact_provider_model_alias_uses_native_provider_path(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_API_KEYS", "local-benchmark-key")
    dataset_path = tmp_path / "fixture.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "question": "Which option is correct?",
                "options": ["wrong", "correct", "also wrong"],
                "answer": "B",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    client = _BenchmarkClient()
    profiles = build_runtime_profiles(_runtime_manifest())
    engine = FusionEngine(profiles, client=client, cache_enabled=False)

    run = run_multiple_choice_benchmark(
        suite_id="arc_challenge",
        dataset_path=dataset_path,
        candidate_id="runtime-reasoner",
        api_format="",
        live=True,
        engine=engine,
        provider_profiles=profiles,
        max_latency_ms=15_000,
    )

    assert run["candidate_id"].startswith("provider::")
    assert run["api_format"] == "provider_native"
    assert run["case_results"][0]["status"] == "completed"
    assert run["case_results"][0]["correct"] is True
    assert len(client.calls) == 1
    serialized = json.dumps(run, ensure_ascii=False)
    assert "runtime-reasoner" not in serialized


def test_runtime_campaign_is_diagnostic_only_and_resumable(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_API_KEYS", "local-benchmark-key")
    dataset_path = tmp_path / "fixture.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "question": "Choose the correct option.",
                "options": ["wrong", "correct", "also wrong"],
                "answer": "B",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "suites": [
                    {
                        "suite_id": "arc_challenge",
                        "task_format": "multiple_choice",
                        "dataset": str(dataset_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = _BenchmarkClient()
    engine = FusionEngine(build_runtime_profiles(_runtime_manifest()), client=client, cache_enabled=False)
    output_dir = tmp_path / "runtime_campaign"

    campaign = run_runtime_benchmark_campaign(
        dataset_manifest_path=manifest_path,
        output_dir=output_dir,
        engine=engine,
        suite_ids=["arc_challenge"],
        candidate_ids=["axio-fast"],
        api_formats=["chat/completions", "responses", "anthropic", "gemini"],
        live=True,
        limit=1,
        max_latency_ms=15_000,
    )

    assert campaign["diagnostic_only"] is True
    assert campaign["final_claims_allowed"] is False
    assert campaign["completed_or_resumed_run_count"] == 4
    assert len(campaign["api_surface_parity"]["required_api_formats"]) == 4
    assert campaign["api_surface_parity"]["scoped_model_count"] == 1
    assert campaign["runtime_channel_summary"]["credential_ready_profile_count"] == 1
    assert campaign["max_latency_ms"] == 15_000
    assert len(client.calls) == 4

    resumed = run_runtime_benchmark_campaign(
        dataset_manifest_path=manifest_path,
        output_dir=output_dir,
        engine=engine,
        suite_ids=["arc_challenge"],
        candidate_ids=["axio-fast"],
        api_formats=["chat/completions", "responses", "anthropic", "gemini"],
        live=True,
        limit=1,
        resume=True,
        max_latency_ms=15_000,
    )
    assert resumed["completed_or_resumed_run_count"] == 4
    assert len(client.calls) == 4

    serialized = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))
    assert "runtime-secret-key" not in serialized
    assert "runtime.responses.example" not in serialized
    assert "Choose the correct option." not in serialized
    assert '"final_claims_allowed": true' not in serialized


def test_runtime_http_server_factory_accepts_direct_manifest_without_persisting_credentials():
    client = _BenchmarkClient()
    server = create_runtime_http_server(
        _runtime_manifest(),
        host="127.0.0.1",
        port=0,
        client=client,
        diagnostic_only=True,
        record_trace=False,
        record_runtime=False,
    )
    try:
        assert server.server_address[1] > 0
        engine = server.RequestHandlerClass if hasattr(server, "RequestHandlerClass") else None
        del engine
    finally:
        server.server_close()


def test_runtime_enrollment_filters_failed_models_and_returns_memory_only_engine():
    client = _BenchmarkClient()
    result = enroll_runtime_channels(
        _runtime_manifest(),
        client=client,
        timeout=2,
        max_workers=1,
        min_available_models=1,
        calibrate_tools=True,
        diagnostic_only=True,
    )

    assert result["status"] == "ready"
    assert result["engine"] is not None
    assert len(result["profiles"]) == 1
    assert result["profiles"][0].health == "available"
    assert result["profiles"][0].supports_tools is True
    assert result["receipt"]["raw_api_keys_persisted"] is False
    serialized = json.dumps(result["receipt"], ensure_ascii=False)
    assert "runtime-secret-key" not in serialized
    assert "runtime.responses.example" not in serialized
