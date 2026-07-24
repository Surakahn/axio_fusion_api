import json
import sys
from pathlib import Path


STANDALONE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.evaluation import (
    _complete_provider_baseline_with_replica_failover,
    _external_provider_ranking_receipt_validation_errors,
    _external_provider_ranking_selection_receipt,
    _provider_registry_receipt,
    _provider_baseline_profiles,
    _provider_candidate_id,
    _provider_replica_profiles_for_candidate_id,
    _run_one_multiple_choice_case,
    build_external_provider_ranking_template,
)
from axio_fusion_api.registry import load_registry, normalize_profile
from axio_fusion_api.schemas import FusionRequest
from axio_fusion_api.schemas import sha256_text


def _profile(provider, model, canonical, *, api_format="chat", latency=100):
    return normalize_profile(
        {
            "provider": provider,
            "model": model,
            "canonical_model_id": canonical,
            "api_format": api_format,
            "source": "live_probe",
            "health": "available",
            "observed_success_count": 4,
            "p50_latency_ms": latency,
            "capabilities": {
                "logic": 0.8,
                "math": 0.8,
                "science_knowledge": 0.8,
                "code": 0.8,
                "structured_output": 0.8,
            },
        }
    )


def test_provider_baselines_deduplicate_canonical_models_and_keep_replicas():
    profiles = [
        _profile("provider-a", "same-model", "same-model", latency=120),
        _profile("provider-b", "same-model", "same-model", api_format="responses", latency=80),
        _profile("provider-c", "different-model", "different-model", latency=90),
    ]

    baselines = _provider_baseline_profiles(profiles)

    assert len(baselines) == 2
    assert {profile.canonical_model_id for profile in baselines} == {
        "same-model",
        "different-model",
    }
    replicas = _provider_replica_profiles_for_candidate_id(
        profiles,
        _provider_candidate_id(profiles[0]),
    )
    assert len(replicas) == 2
    assert {profile.provider for profile in replicas} == {"provider-a", "provider-b"}


def test_external_ranking_template_counts_canonical_groups_separately_from_replicas(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "provider-a",
                        "model": "same-model",
                        "canonical_model_id": "same-model",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                    {
                        "provider": "provider-b",
                        "model": "same-model",
                        "canonical_model_id": "same-model",
                        "api_format": "responses",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                    {
                        "provider": "provider-c",
                        "model": "other-model",
                        "canonical_model_id": "other-model",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                    {
                        "provider": "provider-d",
                        "model": "third-model",
                        "canonical_model_id": "third-model",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    template = build_external_provider_ranking_template(registry_path=registry_path)

    assert template["candidate_inventory_count"] == 3
    assert template["canonical_model_group_count"] == 3
    assert template["replica_profile_count"] == 4
    same_model_row = next(
        row
        for row in template["candidate_inventory"]
        if row["replica_count"] == 2
    )
    assert len(same_model_row["replica_profile_id_sha256s"]) == 2
    assert same_model_row["replica_api_formats"] == ["chat/completions", "responses"]


def test_grouped_external_ranking_receipt_validates_all_replica_attestations(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "provider-a",
                        "model": "same-model",
                        "canonical_model_id": "same-model",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                    {
                        "provider": "provider-b",
                        "model": "same-model",
                        "canonical_model_id": "same-model",
                        "api_format": "responses",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                    {
                        "provider": "provider-c",
                        "model": "other-model",
                        "canonical_model_id": "other-model",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                    {
                        "provider": "provider-d",
                        "model": "third-model",
                        "canonical_model_id": "third-model",
                        "source": "live_probe",
                        "health": "available",
                        "observed_success_count": 1,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    template = build_external_provider_ranking_template(registry_path=registry_path)
    payload = json.loads(json.dumps(template))
    payload["pre_registration"] = {
        "declared_before_campaign": True,
        "registered_on": "2026-07-19",
        "target_benchmark_results_used": False,
        "target_suite_results_used": False,
    }
    payload["ranking_method"]["candidate_pool_screening_complete"] = True
    payload["tie_break_policy"] = ["candidate_id_sha256"]

    for rank, row in enumerate(payload["candidate_inventory"], start=1):
        row["screening_rank"] = rank
        row["screening_evidence"] = [
            {
                "source_type": "independent_leaderboard",
                "source_family": "fixture-screen-alpha",
                "source_locator": f"https://fixture.invalid/screen/{rank}/alpha",
                "source_snapshot_sha256": sha256_text("fixture-screen-alpha-snapshot"),
                "retrieved_on": "2026-07-18",
                "reported_rank": rank,
                "ranking_population_count": 3,
                "supports_general_capability_ranking": True,
                "uses_target_benchmark_results": False,
            },
            {
                "source_type": "independent_evaluation_report",
                "source_family": "fixture-screen-beta",
                "source_locator": f"https://fixture.invalid/screen/{rank}/beta",
                "source_snapshot_sha256": sha256_text("fixture-screen-beta-snapshot"),
                "retrieved_on": "2026-07-18",
                "reported_rank": rank,
                "ranking_population_count": 3,
                "supports_general_capability_ranking": True,
                "uses_target_benchmark_results": False,
            },
        ]
        for binding in row["replica_identity_attestations"]:
            binding["channel_model_identity_attested"] = True
            binding["attested_on"] = "2026-07-18"
            binding["source_locator"] = "https://fixture.invalid/identity"
            binding["source_snapshot_sha256"] = sha256_text("fixture-identity-snapshot")
            binding["attestation_content_sha256"] = sha256_text(
                binding["profile_id_sha256"]
            )
        row["identity_attestation"] = row["replica_identity_attestations"][0]

    payload["rankings"] = []
    for rank, row in enumerate(payload["candidate_inventory"], start=1):
        payload["rankings"].append(
            {
                "rank": rank,
                "profile_id_sha256": row["profile_id_sha256"],
                "canonical_model_id_sha256": row["canonical_model_id_sha256"],
                "evidence": [
                    {
                        "source_type": "official_model_card",
                        "source_family": "fixture-official",
                        "source_locator": "https://fixture.invalid/official",
                        "source_snapshot_sha256": sha256_text("fixture-official-snapshot"),
                        "retrieved_on": "2026-07-18",
                        "supports_general_capability_ranking": True,
                        "uses_target_benchmark_results": False,
                    },
                    {
                        "source_type": "independent_leaderboard",
                        "source_family": "fixture-rank-alpha",
                        "source_locator": "https://fixture.invalid/rank/alpha",
                        "source_snapshot_sha256": sha256_text("fixture-rank-alpha-snapshot"),
                        "retrieved_on": "2026-07-18",
                        "reported_rank": rank,
                        "ranking_population_count": 3,
                        "supports_general_capability_ranking": True,
                        "uses_target_benchmark_results": False,
                    },
                    {
                        "source_type": "independent_evaluation_report",
                        "source_family": "fixture-rank-beta",
                        "source_locator": "https://fixture.invalid/rank/beta",
                        "source_snapshot_sha256": sha256_text("fixture-rank-beta-snapshot"),
                        "retrieved_on": "2026-07-18",
                        "reported_rank": rank,
                        "ranking_population_count": 3,
                        "supports_general_capability_ranking": True,
                        "uses_target_benchmark_results": False,
                    },
                ],
            }
        )

    ranking_path = tmp_path / "ranking.json"
    ranking_path.write_text(json.dumps(payload), encoding="utf-8")
    profiles = load_registry(registry_path)
    receipt = _external_provider_ranking_selection_receipt(
        ranking_path,
        profiles=profiles,
        registry_receipt=_provider_registry_receipt(profiles, registry_path=registry_path),
    )

    assert receipt["ready"] is True
    assert receipt["candidate_inventory_grouped_by_canonical_identity"] is True
    assert receipt["candidate_inventory_count"] == 3
    assert receipt["replica_profile_count"] == 4
    assert receipt["identity_binding_count"] == 4
    assert receipt["selected_canonical_model_identities_distinct"] is True
    safe_receipt = dict(receipt)
    safe_receipt.pop("selected_profiles_by_rank", None)
    assert _external_provider_ranking_receipt_validation_errors(safe_receipt) == []


class _ReplicaClient:
    def __init__(self, *, failures=0):
        self.failures = failures
        self.calls = []

    def complete(self, profile, request, *, prompt, system, timeout=None):
        self.calls.append(profile.profile_id)
        if len(self.calls) <= self.failures:
            raise RuntimeError("fixture provider failure")
        return "42"


def test_provider_baseline_rotation_and_same_group_failover_are_bounded():
    profiles = [
        _profile("provider-a", "same-model", "same-model", latency=120),
        _profile("provider-b", "same-model", "same-model", api_format="responses", latency=80),
    ]
    candidate_id = _provider_candidate_id(profiles[0])
    request = FusionRequest(model="axio-fast", prompt="fixture", max_output_tokens=16, temperature=0.0)

    rotating_client = _ReplicaClient()
    first = _complete_provider_baseline_with_replica_failover(
        profiles=profiles,
        candidate_id=candidate_id,
        request=request,
        prompt="fixture",
        system="fixture",
        expected_output_tokens=16,
        client=rotating_client,
        case_index=0,
    )
    second = _complete_provider_baseline_with_replica_failover(
        profiles=profiles,
        candidate_id=candidate_id,
        request=request,
        prompt="fixture",
        system="fixture",
        expected_output_tokens=16,
        client=rotating_client,
        case_index=1,
    )
    assert rotating_client.calls[:2] != rotating_client.calls[2:4]
    assert first.provider_execution["replica_count"] == 2
    assert second.provider_execution["replica_count"] == 2
    assert first.provider_execution["attempt_count"] == 1

    failing_client = _ReplicaClient(failures=1)
    recovered = _complete_provider_baseline_with_replica_failover(
        profiles=profiles,
        candidate_id=candidate_id,
        request=request,
        prompt="fixture",
        system="fixture",
        expected_output_tokens=16,
        client=failing_client,
        case_index=0,
    )
    assert len(failing_client.calls) == 2
    assert recovered.text == "42"
    assert recovered.provider_execution["attempt_count"] == 2
    assert recovered.provider_execution["failover_used"] is True

    case_result = _run_one_multiple_choice_case(
        case={
            "question": "fixture question",
            "options": ["fixture answer"],
            "option_labels": ["A"],
            "answer": "A",
        },
        index=0,
        candidate_id=candidate_id,
        api_format="chat/completions",
        profiles=profiles,
        engine=None,
        live=True,
        client=_ReplicaClient(failures=1),
        axio_gateway_url=None,
        max_latency_ms=None,
    )
    assert case_result["provider_replica_execution"]["attempt_count"] == 2
    assert case_result["provider_call_count"] == 2
