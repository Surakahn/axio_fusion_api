from __future__ import annotations

import json

import pytest

import axio_fusion_api.official_campaign as official_campaign_module
from axio_fusion_api.evaluation import _provider_baseline_freeze_digest_input
from axio_fusion_api.official_harness import (
    validate_provider_baseline_freeze_for_official_campaign,
)
from axio_fusion_api.official_campaign import run_official_harness_campaign
from axio_fusion_api.registry import build_default_registry
from axio_fusion_api.schemas import sha256_text, stable_json


def _claim_only_freeze(*, registry_file_sha256: str) -> dict:
    candidate_hashes = [sha256_text(f"provider::{rank}") for rank in (1, 2, 3)]
    manifest = {
        "schema": "axio_fusion_api.provider_baseline_freeze_manifest.v1",
        "final_claim_freeze_ready": True,
        "provider_baseline_selection": "externally_ranked_top_three_pre_registered",
        "selected_all_available_provider_baselines": False,
        "selected_provider_baseline_count": 3,
        "required_provider_baseline_count": 3,
        "selected_provider_candidate_id_hashes": candidate_hashes,
        "selected_provider_candidate_id_set_sha256": sha256_text(
            stable_json(sorted(candidate_hashes))
        ),
        "frozen_candidate_rows": [
            {"pre_campaign_external_rank": rank, "candidate_id_hash": candidate_hashes[rank - 1]}
            for rank in (1, 2, 3)
        ],
        "tier_target_policy": [
            {"axio_model": "axio-pro", "target_provider_rank": 1},
            {"axio_model": "axio-terra", "target_provider_rank": 2},
            {"axio_model": "axio-fast", "target_provider_rank": 3},
        ],
        "external_ranking_receipt": {
            "schema": "axio_fusion_api.external_provider_ranking_receipt.v3",
            "ready": True,
            "pre_registered_before_campaign": True,
            "identity_binding_ready": True,
            "target_benchmark_material_detected": False,
        },
        "provider_registry_receipt": {
            "registry_file_sha256": registry_file_sha256,
        },
    }
    manifest["freeze_digest_sha256"] = sha256_text(
        stable_json(_provider_baseline_freeze_digest_input(manifest))
    )
    return manifest


def _campaign_inputs(tmp_path, *, candidate_type: str) -> dict:
    candidate_id = "axio-pro" if candidate_type == "axio" else "provider::fixture"
    task = {
        "execution_task_id": "official_harness_task_0001",
        "suite_id": "ifeval",
        "task_format": "instruction_checks",
        "candidate_id_hash": sha256_text(candidate_id),
        "run_unit_id_hash": sha256_text(f"{candidate_id}@chat_completions"),
        "candidate_type": candidate_type,
        "api_format": "chat/completions",
        "provider_profile_hash": sha256_text("provider-profile")
        if candidate_type == "provider"
        else "",
        "ready_to_execute": True,
    }
    plan_path = tmp_path / "execution_plan.safe.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.official_harness_execution_plan.v1",
                "execution_plan_digest_sha256": sha256_text("plan"),
                "all_tasks_ready_to_execute": True,
                "tasks": [task],
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "suite_config.private.json"
    config_path.write_text(
        json.dumps(
            {
                "suites": [
                    {
                        "suite_id": "ifeval",
                        "dataset_path": str(tmp_path / "dataset.private.jsonl"),
                        "harness_root": str(tmp_path / "harness.private"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.private.json"
    registry_path.write_text(json.dumps(build_default_registry()), encoding="utf-8")
    freeze_path = tmp_path / "provider_freeze.blocked.safe.json"
    freeze_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_baseline_freeze_manifest.v1",
                "final_claim_freeze_ready": False,
                "selected_provider_profile_hashes": [],
            }
        ),
        encoding="utf-8",
    )
    pin_path = tmp_path / "harness_pin.safe.json"
    pin_path.write_text(json.dumps({"suites": []}), encoding="utf-8")
    return {
        "execution_plan_path": plan_path,
        "suite_config_path": config_path,
        "registry_path": registry_path,
        "provider_baseline_freeze_manifest_path": freeze_path,
        "harness_pin_manifest_path": pin_path,
        "private_root": tmp_path / "private_runs",
        "safe_import_root": tmp_path / "safe_imports",
    }


def test_axio_only_offline_preflight_does_not_require_provider_rank_freeze(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls = []

    def fake_preflight(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ready",
            "case_set_digest_sha256": sha256_text("ifeval-cases"),
            "case_count": 2,
            "reason_codes": [],
            "model_calls_performed": False,
            "official_harness_execution_performed": False,
        }

    monkeypatch.setattr(
        official_campaign_module,
        "build_official_harness_bridge_preflight",
        fake_preflight,
    )
    result = run_official_harness_campaign(
        **_campaign_inputs(tmp_path, candidate_type="axio"),
        live=False,
    )

    assert result["status"] == "preflight_ready"
    assert result["preflight_ready_task_count"] == 1
    assert result["model_call_task_count"] == 0
    assert len(calls) == 1
    controls = result["execution_controls"]
    assert controls["provider_baseline_freeze_required"] is False
    assert controls["provider_baseline_freeze_ready"] is False
    assert controls["unfrozen_axio_preflight_only"] is True


@pytest.mark.parametrize(
    ("candidate_type", "live"),
    (("axio", True), ("provider", False)),
)
def test_live_or_provider_campaign_still_requires_provider_rank_freeze(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    candidate_type: str,
    live: bool,
) -> None:
    def unexpected_preflight(**kwargs):
        del kwargs
        raise AssertionError("preflight must not run before the provider freeze")

    monkeypatch.setattr(
        official_campaign_module,
        "build_official_harness_bridge_preflight",
        unexpected_preflight,
    )
    result = run_official_harness_campaign(
        **_campaign_inputs(tmp_path, candidate_type=candidate_type),
        live=live,
    )

    assert result["status"] == "blocked"
    assert "official_campaign_provider_freeze_not_ready" in result["reason_codes"]
    controls = result["execution_controls"]
    assert controls["provider_baseline_freeze_required"] is True
    assert controls["provider_baseline_freeze_ready"] is False
    assert controls["unfrozen_axio_preflight_only"] is False


def test_official_campaign_freeze_validation_rejects_claim_only_and_exhaustive_matrix() -> None:
    registry_sha = sha256_text("registry")
    claimed = _claim_only_freeze(registry_file_sha256=registry_sha)
    claim_only = validate_provider_baseline_freeze_for_official_campaign(
        claimed,
        registry_file_sha256=registry_sha,
    )
    assert claim_only["ready"] is False
    assert claim_only["external_ranking_mapping_valid"] is False
    assert claim_only["external_ranking_validation_error_count"] > 0
    assert (
        "provider_baseline_freeze_external_ranking_mapping_invalid"
        in claim_only["reason_codes"]
    )

    exhaustive = {
        **claimed,
        "provider_baseline_selection": "all_available_provider_models",
        "selected_all_available_provider_baselines": True,
        "selected_provider_baseline_count": 4,
        "selected_provider_candidate_id_hashes": [
            *claimed["selected_provider_candidate_id_hashes"],
            sha256_text("provider::4"),
        ],
    }
    exhaustive["selected_provider_candidate_id_set_sha256"] = sha256_text(
        stable_json(sorted(exhaustive["selected_provider_candidate_id_hashes"]))
    )
    exhaustive["freeze_digest_sha256"] = sha256_text(
        stable_json(_provider_baseline_freeze_digest_input(exhaustive))
    )
    rejected = validate_provider_baseline_freeze_for_official_campaign(
        exhaustive,
        registry_file_sha256=registry_sha,
    )

    assert rejected["ready"] is False
    assert "provider_baseline_freeze_digest_invalid" not in rejected["reason_codes"]
    assert (
        "provider_baseline_freeze_not_externally_ranked_top_three"
        in rejected["reason_codes"]
    )
    assert (
        "provider_baseline_freeze_exhaustive_diagnostic_not_allowed"
        in rejected["reason_codes"]
    )
    assert "provider_baseline_freeze_selected_count_mismatch" in rejected["reason_codes"]
    assert "provider_baseline_freeze_candidate_set_mismatch" in rejected["reason_codes"]
