from __future__ import annotations

import json

import pytest

from axio_fusion_api import available_model_generation as generation


def _ready_report() -> dict:
    return {
        "schema": "axio_fusion_api.pre_fusion_model_screening.v1",
        "status": "ready",
        "blockers": [],
        "research_ranking": {"candidate_count": 2},
    }


def _ready_handoff(registry: dict) -> dict:
    stability_contract = {
        "schema": "axio_fusion_api.provider_probe_stability_contract.v1",
        "samples_per_profile": 3,
        "requires_all_samples_success": True,
        "requires_each_sample_latency_at_or_below_90_seconds": True,
        "requires_each_sample_strict_streaming": True,
    }
    return {
        "schema": "axio_fusion_api.prefusion_fusion_handoff.v2",
        "status": "ready",
        "research_ranking": {
            "candidate_count": 2,
            "ordered_models": [
                {"candidate_id": "candidate_0001", "rank": 1},
                {"candidate_id": "candidate_0002", "rank": 2},
            ],
        },
        "operational_ranking": {
            "candidate_count": 1,
            "ordered_models": [
                {
                    "candidate_id": "candidate_0002",
                    "operational_rank": 1,
                    "available_rank": 1,
                    "fastest_observed_latency_ms": 1200,
                }
            ],
        },
        "available_model_list": [
            {
                "canonical_model_id": "model-fast",
                "available_rank": 1,
                "replica_count": 2,
                "replicas_are_failover_not_independent_votes": True,
            }
        ],
        "logical_model_count": 1,
        "physical_profile_count": 2,
        "stream_stability_contract": stability_contract,
        "requires_multi_sample_stream_stability": True,
        "role_coverage": {"status": "ready"},
        "fusion_registry": registry,
    }


def test_generation_publishes_only_the_validated_logical_handoff(monkeypatch):
    registry = {"schema": "axio_fusion_api.registry.v1", "binding_status": "ready"}
    observed = {}

    def fake_screening(**kwargs):
        observed.update(kwargs)
        return _ready_report()

    monkeypatch.setattr(generation, "run_prefusion_model_screening", fake_screening)
    monkeypatch.setattr(
        generation,
        "validate_prefusion_handoff",
        lambda report, require_ready: {
            "valid": True,
            "reason_codes": [],
            "physical_profile_count": 2,
            "logical_model_count": 1,
        },
    )
    monkeypatch.setattr(
        generation,
        "build_prefusion_fusion_handoff",
        lambda report, **kwargs: _ready_handoff(registry),
    )
    monkeypatch.setattr(
        generation,
        "validate_prefusion_registry_handoff",
        lambda value, require_ready: {"valid": True, "reason_codes": []},
    )

    artifact = generation.generate_available_model_set(
        live=True,
        timeout=90,
        min_available_models=1,
        stream_probe_samples=1,
    )

    assert artifact["status"] == "ready"
    assert artifact["logical_model_count"] == 1
    assert len(artifact["available_model_list"]) == 1
    assert artifact["operational_ranking"]["candidate_count"] == 1
    assert artifact["fusion_handoff"]["fusion_registry"] == registry
    assert observed["live"] is True
    assert observed["timeout"] == 90
    assert artifact["latency_gate"]["samples_per_profile"] == 3
    assert artifact["latency_gate"]["multi_sample_stability_required"] is True
    assert artifact["no_cheat_contract"]["benchmark_cases_or_labels_used"] is False


def test_invalid_registry_fails_closed_and_never_exposes_available_list(monkeypatch):
    monkeypatch.setattr(
        generation,
        "run_prefusion_model_screening",
        lambda **kwargs: _ready_report(),
    )
    monkeypatch.setattr(
        generation,
        "validate_prefusion_handoff",
        lambda report, require_ready: {"valid": True, "reason_codes": []},
    )
    monkeypatch.setattr(
        generation,
        "build_prefusion_fusion_handoff",
        lambda report, **kwargs: _ready_handoff({"binding_status": "ready"}),
    )
    monkeypatch.setattr(
        generation,
        "validate_prefusion_registry_handoff",
        lambda value, require_ready: {
            "valid": False,
            "reason_codes": ["prefusion_registry_probe_binding_invalid"],
        },
    )

    artifact = generation.generate_available_model_set(live=True)

    assert artifact["status"] == "blocked"
    assert artifact["available_model_list"] == []
    assert artifact["operational_ranking"] == {}
    assert "fusion_registry" not in artifact["fusion_handoff"]
    assert "registry:prefusion_registry_probe_binding_invalid" in artifact["blockers"]


def test_blocked_publication_does_not_replace_current_registry(tmp_path):
    registry_path = tmp_path / "active-registry.json"
    previous = {"schema": "old", "binding_status": "ready"}
    registry_path.write_text(json.dumps(previous), encoding="utf-8")

    with pytest.raises(generation.AvailableModelGenerationError) as error:
        generation.publish_available_model_set(
            {"status": "blocked"},
            registry_path=registry_path,
        )

    assert error.value.code == "available_model_generation_not_ready"
    assert json.loads(registry_path.read_text(encoding="utf-8")) == previous


def test_ready_publication_is_atomic_and_revalidates_registry(monkeypatch, tmp_path):
    registry = {"schema": "axio_fusion_api.registry.v1", "binding_status": "ready"}
    monkeypatch.setattr(
        generation,
        "validate_prefusion_registry_handoff",
        lambda value, require_ready: {"valid": True, "reason_codes": []},
    )
    artifact = {
        "status": "ready",
        "logical_model_count": 1,
        "research_ranking": {},
        "operational_ranking": {},
        "available_model_list": [],
        "fusion_handoff": {"fusion_registry": registry},
    }
    artifact["fusion_handoff"].update(
        {
            "status": "ready",
            "research_ranking": {},
            "operational_ranking": {},
            "available_model_list": artifact["available_model_list"],
        }
    )
    artifact["logical_model_count"] = 0
    registry_path = tmp_path / "runtime" / "registry.json"
    handoff_path = tmp_path / "runtime" / "available-models.json"

    receipt = generation.publish_available_model_set(
        artifact,
        registry_path=registry_path,
        handoff_path=handoff_path,
    )

    assert receipt["status"] == "ready"
    assert json.loads(registry_path.read_text(encoding="utf-8")) == registry
    assert json.loads(handoff_path.read_text(encoding="utf-8"))["status"] == "ready"
    assert not list(registry_path.parent.glob("*.tmp"))


def test_ready_publication_rejects_tampered_registry_digest(monkeypatch, tmp_path):
    registry = {"schema": "axio_fusion_api.registry.v1", "binding_status": "ready"}
    monkeypatch.setattr(
        generation,
        "validate_prefusion_registry_handoff",
        lambda value, require_ready: {"valid": True, "reason_codes": []},
    )
    handoff = {
        "status": "ready",
        "research_ranking": {},
        "operational_ranking": {},
        "available_model_list": [],
        "fusion_registry": registry,
    }
    artifact = {
        "status": "ready",
        "logical_model_count": 0,
        "research_ranking": {},
        "operational_ranking": {},
        "available_model_list": [],
        "fusion_handoff": handoff,
        "source_receipt": {
            "registry_content_sha256": "0" * 64,
        },
    }

    with pytest.raises(generation.AvailableModelGenerationError) as error:
        generation.publish_available_model_set(
            artifact,
            registry_path=tmp_path / "registry.json",
        )

    assert error.value.code == "available_model_registry_digest_mismatch"


def test_redacted_generation_cannot_be_marked_ready_with_private_registry(monkeypatch):
    registry = {"schema": "axio_fusion_api.registry.v1", "binding_status": "ready"}
    monkeypatch.setattr(
        generation,
        "run_prefusion_model_screening",
        lambda **kwargs: _ready_report(),
    )
    monkeypatch.setattr(
        generation,
        "validate_prefusion_handoff",
        lambda report, require_ready: {"valid": True, "reason_codes": []},
    )
    monkeypatch.setattr(
        generation,
        "build_prefusion_fusion_handoff",
        lambda report, **kwargs: _ready_handoff(registry),
    )
    monkeypatch.setattr(
        generation,
        "validate_prefusion_registry_handoff",
        lambda value, require_ready: {"valid": True, "reason_codes": []},
    )

    artifact = generation.generate_available_model_set(
        live=True,
        redact_provider_identifiers=True,
    )

    assert artifact["status"] == "ready"
    assert artifact["publication"]["private_registry_included"] is False
    assert "fusion_registry" not in artifact["fusion_handoff"]
