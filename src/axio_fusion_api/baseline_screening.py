from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import ast
import inspect
import json
import math
import random
import re
import sys
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from .evaluation import (
    EXTERNAL_PROVIDER_RANKING_AGGREGATION,
    EXTERNAL_PROVIDER_RANKING_INPUT_SCHEMA,
    EXTERNAL_PROVIDER_RANKING_MIN_INDEPENDENT_SOURCES,
    EXTERNAL_PROVIDER_RANKING_REQUIRED_RANKS,
    _external_ranking_contains_target_benchmark_material,
    _provider_baseline_group_summaries,
    build_external_provider_ranking_template,
)
from .latency_policy import PROVIDER_MAX_RESPONSE_SECONDS
from .operational_admission import validate_operational_admission_handoff
from .providers import (
    HTTPProviderClient,
    ensure_strict_streaming_client,
    profile_credential_readiness,
)
from .registry import load_registry
from .schemas import FusionRequest, ModelProfile, sha256_text, stable_json


SCREENING_SOURCE_MANIFEST_SCHEMA = (
    "axio_fusion_api.non_target_screening_source_manifest.v1"
)
SCREENING_PLAN_SCHEMA = "axio_fusion_api.non_target_screening_plan.v2"
SCREENING_CAMPAIGN_SCHEMA = "axio_fusion_api.non_target_screening_campaign.v2"
SCREENING_UNIT_PRIVATE_SCHEMA = (
    "axio_fusion_api.non_target_screening_unit_private.v1"
)
SCREENING_UNIT_SAFE_SCHEMA = "axio_fusion_api.non_target_screening_unit_safe.v1"
SCREENING_IDENTITY_ATTESTATION_SCHEMA = (
    "axio_fusion_api.provider_identity_attestation_receipt.v1"
)

SUPPORTED_SCREENING_ADAPTERS = frozenset(
    {"jsonl_multiple_choice", "mmlu_pro", "livebench_official"}
)
DEFAULT_MIN_CASES_PER_SOURCE = 100
DEFAULT_MAX_TRANSPORT_FAILURE_RATE = 0.02
DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
DEFAULT_TIE_BREAK_POLICY = (
    "source_mean_score_descending",
    "source_confidence_lower_bound_descending",
    "candidate_id_sha256_ascending",
    "mean_common_source_normalized_rank_percentile_then_candidate_id_sha256",
)
_MMLU_ANSWER_PATTERNS = (
    re.compile(r"answer is \(?([A-J])\)?"),
    re.compile(r"[aA]nswer:\s*([A-J])"),
    re.compile(r"\b([A-J])\b"),
)
_LIVEBENCH_SUPPORTED_TASKS = frozenset(
    {
        "zebra_puzzle",
        "spatial",
        "web_of_lies_v2",
        "cta",
        "tablereformat",
        "tablejoin",
        "connections",
        "typos",
        "plot_unscrambling",
    }
)

# The scorer-silencing call changes process hygiene, not prompt selection,
# decoding, parsing, or score semantics. Keep already frozen plans resumable
# across this narrowly scoped operational hardening change.
_NON_SEMANTIC_SCREENING_SOURCE_REWRITES = (
    (
        "score = _score_screening_output_silently(source, case, output)",
        "score = _score_screening_output(source, case, output)",
    ),
)


@dataclass(frozen=True)
class ScreeningCase:
    case_id: str
    prompt: str
    reference: Any
    stratum: str
    metadata: Mapping[str, Any]


def build_non_target_screening_plan(
    *,
    registry_path: str | Path,
    source_manifest_path: str | Path,
    private_probe_files: Sequence[str | Path] = (),
    min_cases_per_source: int = DEFAULT_MIN_CASES_PER_SOURCE,
    operational_admission_path: str | Path | None = None,
) -> dict[str, Any]:
    """Pre-register a complete-pool, non-target provider screening matrix.

    The returned plan is safe to persist. Dataset paths, questions, labels,
    provider/model aliases, source locators, and probe contents are replaced by
    hashes. The source manifest and probe files remain private operator inputs.
    """

    registry_file = Path(registry_path)
    source_file = Path(source_manifest_path)
    blockers: list[str] = []
    profiles = _load_registry_for_screening(registry_file, blockers)
    profiles, operational_admission = _apply_operational_admission_filter(
        profiles,
        operational_admission_path=operational_admission_path,
        blockers=blockers,
    )
    source_manifest, source_manifest_sha256 = _load_private_json(
        source_file,
        reason_prefix="screening_source_manifest",
        blockers=blockers,
    )
    registry_sha256 = _file_sha256(registry_file)
    if not registry_sha256:
        blockers.append("screening_registry_content_digest_missing")
    if source_manifest.get("schema") != SCREENING_SOURCE_MANIFEST_SCHEMA:
        blockers.append("screening_source_manifest_schema_invalid")

    pre_registration = (
        source_manifest.get("pre_registration")
        if isinstance(source_manifest.get("pre_registration"), Mapping)
        else {}
    )
    registered_on = str(pre_registration.get("registered_on") or "")
    selection_seed = str(pre_registration.get("selection_seed") or "")
    if pre_registration.get("declared_before_target_campaign") is not True:
        blockers.append("screening_not_declared_before_target_campaign")
    if not _valid_iso_date(registered_on):
        blockers.append("screening_registration_date_invalid")
    if not selection_seed:
        blockers.append("screening_selection_seed_missing")
    if pre_registration.get("target_benchmark_results_used") is not False:
        blockers.append("screening_target_benchmark_results_used")
    if pre_registration.get("target_suite_results_used") is not False:
        blockers.append("screening_target_suite_results_used")
    if _external_ranking_contains_target_benchmark_material(source_manifest):
        blockers.append("screening_source_manifest_contains_target_material")

    groups = _canonical_live_groups(profiles)
    if len(groups) < len(EXTERNAL_PROVIDER_RANKING_REQUIRED_RANKS):
        blockers.append("screening_fewer_than_three_live_canonical_models")
    if any(not row["canonical_model_identity_declared"] for row in groups):
        blockers.append("screening_canonical_model_identity_missing")

    identity = build_provider_identity_attestation_receipt(
        profiles=profiles,
        private_probe_files=private_probe_files,
        attested_on=registered_on,
    )
    if identity.get("ready") is not True:
        blockers.extend(str(reason) for reason in identity.get("blockers", []))

    raw_sources = (
        source_manifest.get("sources")
        if isinstance(source_manifest.get("sources"), list)
        else []
    )
    if len(raw_sources) < EXTERNAL_PROVIDER_RANKING_MIN_INDEPENDENT_SOURCES:
        blockers.append("screening_independent_source_count_below_minimum")
    source_receipts: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    source_families: set[str] = set()
    minimum = max(1, int(min_cases_per_source))
    for source in raw_sources:
        receipt, source_blockers = _screening_source_receipt(
            source,
            selection_seed=selection_seed,
            min_cases_per_source=minimum,
        )
        source_receipts.append(receipt)
        blockers.extend(source_blockers)
        source_id = str(source.get("source_id") or "") if isinstance(source, Mapping) else ""
        source_family_sha256 = str(receipt.get("source_family_sha256") or "")
        if source_id in source_ids:
            blockers.append("screening_source_id_duplicate")
        source_ids.add(source_id)
        if source_family_sha256 in source_families:
            blockers.append("screening_source_family_duplicate")
        source_families.add(source_family_sha256)

    candidate_rows = [_safe_group_row(group) for group in groups]
    task_by_binding: dict[tuple[str, str], dict[str, Any]] = {}
    for source in source_receipts:
        for candidate in candidate_rows:
            task_core = {
                "source_id_sha256": str(source.get("source_id_sha256") or ""),
                "source_snapshot_sha256": str(
                    source.get("source_snapshot_sha256") or ""
                ),
                "case_set_digest_sha256": str(
                    source.get("case_set_digest_sha256") or ""
                ),
                "prompt_set_digest_sha256": str(
                    source.get("prompt_set_digest_sha256") or ""
                ),
                "reference_set_digest_sha256": str(
                    source.get("reference_set_digest_sha256") or ""
                ),
                "case_contract_set_digest_sha256": str(
                    source.get("case_contract_set_digest_sha256") or ""
                ),
                "adapter_implementation_sha256": str(
                    source.get("adapter_implementation_sha256") or ""
                ),
                "canonical_identity_sha256": str(
                    candidate.get("canonical_identity_sha256") or ""
                ),
                "candidate_id_sha256": str(
                    candidate.get("candidate_id_sha256") or ""
                ),
                "representative_profile_id_sha256": str(
                    candidate.get("representative_profile_id_sha256") or ""
                ),
                "replica_profile_id_sha256s": list(
                    candidate.get("replica_profile_id_sha256s") or []
                ),
            }
            task_by_binding[
                (
                    str(source.get("source_id_sha256") or ""),
                    str(candidate.get("canonical_identity_sha256") or ""),
                )
            ] = {
                "task_id": sha256_text(stable_json(task_core)),
                **task_core,
                "ready": bool(source.get("ready")),
            }

    task_rows, execution_schedule = _balanced_screening_task_schedule(
        task_by_binding=task_by_binding,
        source_receipts=source_receipts,
        candidate_rows=candidate_rows,
        selection_seed=selection_seed,
    )

    plan: dict[str, Any] = {
        "schema": SCREENING_PLAN_SCHEMA,
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "execution_mode": "remote_provider_api_only",
        "registry_file_sha256": registry_sha256,
        "source_manifest_content_sha256": source_manifest_sha256,
        "operational_admission": operational_admission,
        "pre_registered_before_target_campaign": (
            pre_registration.get("declared_before_target_campaign") is True
        ),
        "registered_on": registered_on,
        "selection_seed_sha256": sha256_text(selection_seed),
        "minimum_independent_source_count": (
            EXTERNAL_PROVIDER_RANKING_MIN_INDEPENDENT_SOURCES
        ),
        "minimum_cases_per_source": minimum,
        "source_count": len(source_receipts),
        "source_family_count": len(source_families),
        "sources": source_receipts,
        "canonical_model_group_count": len(candidate_rows),
        "replica_profile_count": sum(
            int(row.get("replica_count") or 0) for row in candidate_rows
        ),
        "candidate_group_set_sha256": sha256_text(
            stable_json(
                sorted(
                    str(row.get("canonical_identity_sha256") or "")
                    for row in candidate_rows
                )
            )
        ),
        "candidate_groups": candidate_rows,
        "identity_attestation_receipt": _safe_identity_attestation_receipt(
            identity
        ),
        "task_count": len(task_rows),
        "estimated_provider_call_count": sum(
            int(source.get("selected_case_count") or 0)
            for source in source_receipts
        )
        * len(candidate_rows),
        "tasks": task_rows,
        "execution_schedule": execution_schedule,
        "ranking_policy": {
            "source_rank_metric": "mean_case_score_with_transport_failures_scored_zero",
            "tie_break_policy": list(DEFAULT_TIE_BREAK_POLICY),
            "cross_source_aggregation": EXTERNAL_PROVIDER_RANKING_AGGREGATION,
            "same_case_set_for_every_candidate": True,
            "same_prompt_protocol_for_every_candidate": True,
            "same_decoding_config_for_every_candidate": True,
            "canonical_model_replicas_count_as_one_candidate": True,
            "replicas_are_failover_not_independent_votes": True,
            "task_order_fixed_before_provider_calls": True,
            "source_and_candidate_order_temporally_counterbalanced": True,
        },
        "no_cheat_contract": {
            "target_suite_prompts_used": False,
            "target_suite_labels_used": False,
            "target_suite_results_used": False,
            "provider_model_names_used_for_strength_ranking": False,
            "registry_capability_priors_used_for_strength_ranking": False,
            "retry_on_wrong_answer": False,
            "benchmark_outputs_used_for_router_training": False,
            "benchmark_outputs_used_for_prompt_tuning": False,
            "ranking_frozen_before_target_campaign": True,
        },
        "anti_leakage_contract": _safe_artifact_contract(),
        "ready": False,
        "blockers": [],
        "raw_dataset_paths_persisted": False,
        "raw_questions_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    blockers.extend(_screening_execution_schedule_errors(plan))
    blockers.extend(_screening_safe_artifact_leakage_errors(plan))
    plan["blockers"] = sorted(set(blockers))
    plan["ready"] = not blockers
    plan["plan_digest_sha256"] = sha256_text(
        stable_json(_screening_plan_digest_input(plan))
    )
    return plan


def _balanced_screening_task_schedule(
    *,
    task_by_binding: Mapping[tuple[str, str], Mapping[str, Any]],
    source_receipts: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    selection_seed: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a frozen, source-interleaved, candidate-counterbalanced order.

    For each adjacent pair of independent sources, the second source observes
    candidates in the reverse order of the first.  Tasks are then emitted one
    source at a time within each round.  With the usual two-source screening
    design, every candidate's two temporal positions sum to the same value,
    reducing confounding from long-running provider drift without changing a
    prompt, label, retry rule, or score.
    """

    source_hashes = sorted(
        {
            str(row.get("source_id_sha256") or "")
            for row in source_receipts
            if str(row.get("source_id_sha256") or "")
        },
        key=lambda value: sha256_text(
            f"{selection_seed}:screening-schedule:source:{value}"
        ),
    )
    candidate_hashes = sorted(
        {
            str(row.get("canonical_identity_sha256") or "")
            for row in candidate_rows
            if str(row.get("canonical_identity_sha256") or "")
        },
        key=lambda value: sha256_text(
            f"{selection_seed}:screening-schedule:candidate:{value}"
        ),
    )
    candidate_count = len(candidate_hashes)
    per_source: dict[str, list[str]] = {}
    for source_index, source_hash in enumerate(source_hashes):
        pair_index = source_index // 2
        if candidate_count:
            offset = pair_index % candidate_count
            forward = [
                *candidate_hashes[offset:],
                *candidate_hashes[:offset],
            ]
        else:
            forward = []
        per_source[source_hash] = (
            forward if source_index % 2 == 0 else list(reversed(forward))
        )

    task_rows: list[dict[str, Any]] = []
    for round_index in range(candidate_count):
        for source_hash in source_hashes:
            canonical_hash = per_source[source_hash][round_index]
            task = task_by_binding.get((source_hash, canonical_hash))
            if not isinstance(task, Mapping):
                continue
            task_rows.append(
                {
                    **dict(task),
                    "execution_index": len(task_rows),
                }
            )

    schedule_core: dict[str, Any] = {
        "strategy": "seeded_paired_reverse_source_interleave_v1",
        "selection_seed_sha256": sha256_text(selection_seed),
        "source_count": len(source_hashes),
        "candidate_count": candidate_count,
        "round_count": candidate_count,
        "task_count": len(task_rows),
        "task_id_sequence_sha256": sha256_text(
            stable_json(
                [str(row.get("task_id") or "") for row in task_rows]
            )
        ),
        "source_order_sha256": sha256_text(stable_json(source_hashes)),
        "candidate_seed_order_sha256": sha256_text(
            stable_json(candidate_hashes)
        ),
        "source_interleaving": "one_task_per_source_per_round",
        "candidate_counterbalance": "paired_sources_use_reverse_order",
        "task_order_frozen_before_provider_calls": True,
    }
    return task_rows, {
        **schedule_core,
        "schedule_digest_sha256": sha256_text(stable_json(schedule_core)),
    }


def _screening_execution_schedule_errors(
    plan: Mapping[str, Any],
) -> list[str]:
    schedule = (
        plan.get("execution_schedule")
        if isinstance(plan.get("execution_schedule"), Mapping)
        else {}
    )
    tasks = (
        [row for row in plan.get("tasks", []) if isinstance(row, Mapping)]
        if isinstance(plan.get("tasks"), list)
        else []
    )
    errors: list[str] = []
    if schedule.get("strategy") != "seeded_paired_reverse_source_interleave_v1":
        errors.append("screening_execution_schedule_strategy_invalid")
    expected_count = int(plan.get("task_count") or 0)
    if len(tasks) != expected_count or int(schedule.get("task_count") or -1) != len(tasks):
        errors.append("screening_execution_schedule_task_count_mismatch")
    task_ids = [str(row.get("task_id") or "") for row in tasks]
    if not all(task_ids) or len(set(task_ids)) != len(task_ids):
        errors.append("screening_execution_schedule_task_id_invalid")
    if [row.get("execution_index") for row in tasks] != list(range(len(tasks))):
        errors.append("screening_execution_schedule_index_mismatch")
    if str(schedule.get("task_id_sequence_sha256") or "") != sha256_text(
        stable_json(task_ids)
    ):
        errors.append("screening_execution_schedule_sequence_mismatch")
    if str(schedule.get("selection_seed_sha256") or "") != str(
        plan.get("selection_seed_sha256") or ""
    ):
        errors.append("screening_execution_schedule_seed_mismatch")
    declared_digest = str(schedule.get("schedule_digest_sha256") or "")
    schedule_core = {
        key: value
        for key, value in schedule.items()
        if key != "schedule_digest_sha256"
    }
    if not _looks_like_sha256(declared_digest) or declared_digest != sha256_text(
        stable_json(schedule_core)
    ):
        errors.append("screening_execution_schedule_digest_mismatch")
    return sorted(set(errors))


def build_provider_identity_attestation_receipt(
    *,
    profiles: Sequence[ModelProfile],
    private_probe_files: Sequence[str | Path],
    attested_on: str,
) -> dict[str, Any]:
    """Bind exact provider catalog aliases to declared canonical identities.

    Automatic attestation is deliberately conservative: the channel catalog
    must list the exact model alias and the declared canonical id must equal
    that alias. Renamed or cross-family aliases require an operator-supplied
    attestation instead of fuzzy matching.
    """

    blockers: list[str] = []
    if not _valid_iso_date(attested_on):
        blockers.append("screening_identity_attestation_date_invalid")
    probe_payloads: list[tuple[str, Mapping[str, Any]]] = []
    for value in private_probe_files:
        path = Path(value)
        payload, digest = _load_private_json(
            path,
            reason_prefix="screening_identity_probe",
            blockers=blockers,
        )
        if payload:
            probe_payloads.append((digest, payload))
    if not probe_payloads:
        blockers.append("screening_identity_probe_evidence_missing")

    catalog_rows: list[dict[str, Any]] = []
    for artifact_sha256, payload in probe_payloads:
        reports = (
            payload.get("provider_reports")
            if isinstance(payload.get("provider_reports"), list)
            else []
        )
        for report in reports:
            if not isinstance(report, Mapping):
                continue
            provider = str(report.get("provider") or "")
            model_ids = sorted(
                {
                    str(item)
                    for item in report.get("model_ids", [])
                    if str(item)
                }
            ) if isinstance(report.get("model_ids"), list) else []
            if not provider or not model_ids or str(report.get("status") or "") != "ok":
                continue
            snapshot_input = {
                "artifact_sha256": artifact_sha256,
                "base_url_sha256": str(report.get("base_url_sha256") or ""),
                "provider_sha256": sha256_text(provider),
                "model_ids": model_ids,
                "reported_model_count": int(report.get("model_count") or 0),
            }
            catalog_rows.append(
                {
                    "provider": provider,
                    "model_ids": set(model_ids),
                    "provider_sha256": sha256_text(provider),
                    "base_url_sha256": str(report.get("base_url_sha256") or ""),
                    "source_snapshot_sha256": sha256_text(
                        stable_json(snapshot_input)
                    ),
                }
            )

    bindings: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        if not _profile_has_live_probe_evidence(profile):
            continue
        profile_hash = sha256_text(profile.profile_id)
        canonical = str(profile.canonical_model_id or "")
        if not canonical:
            blockers.append("screening_identity_canonical_model_id_missing")
            continue
        if canonical != profile.model:
            blockers.append("screening_identity_alias_requires_manual_attestation")
            continue
        matches = [
            row
            for row in catalog_rows
            if row["provider"] == profile.provider
            and profile.model in row["model_ids"]
        ]
        if not matches:
            blockers.append("screening_identity_exact_catalog_match_missing")
            continue
        match = sorted(
            matches,
            key=lambda row: (
                str(row["source_snapshot_sha256"]),
                str(row["base_url_sha256"]),
            ),
        )[0]
        source_locator = (
            "urn:axio:provider-model-catalog:"
            f"{match['provider_sha256']}:{match['base_url_sha256']}"
        )
        content = {
            "profile_id_sha256": profile_hash,
            "provider_alias_sha256": sha256_text(profile.provider),
            "model_alias_sha256": sha256_text(profile.model),
            "canonical_model_id_sha256": sha256_text(canonical),
            "base_url_sha256": match["base_url_sha256"],
            "source_snapshot_sha256": match["source_snapshot_sha256"],
        }
        bindings[profile_hash] = {
            "attestation_kind": "channel_model_identity_mapping",
            "channel_model_identity_attested": True,
            "profile_id_sha256": profile_hash,
            "provider_alias_sha256": sha256_text(profile.provider),
            "model_alias_sha256": sha256_text(profile.model),
            "canonical_model_id_sha256": sha256_text(canonical),
            "base_url_sha256": str(match["base_url_sha256"]),
            "attested_on": attested_on,
            "source_locator": source_locator,
            "source_snapshot_sha256": str(match["source_snapshot_sha256"]),
            "attestation_content_sha256": sha256_text(stable_json(content)),
        }

    expected_profile_hashes = sorted(
        sha256_text(profile.profile_id)
        for profile in profiles
        if _profile_has_live_probe_evidence(profile)
    )
    binding_hashes = sorted(bindings)
    if binding_hashes != expected_profile_hashes:
        blockers.append("screening_identity_attestation_profile_set_incomplete")
    return {
        "schema": SCREENING_IDENTITY_ATTESTATION_SCHEMA,
        "attested_on": attested_on,
        "probe_artifact_count": len(probe_payloads),
        "probe_artifact_set_sha256": sha256_text(
            stable_json(sorted(digest for digest, _ in probe_payloads))
        ),
        "expected_profile_count": len(expected_profile_hashes),
        "attested_profile_count": len(bindings),
        "profile_set_sha256": sha256_text(stable_json(binding_hashes)),
        "attestation_set_sha256": sha256_text(
            stable_json(
                sorted(
                    sha256_text(stable_json(binding))
                    for binding in bindings.values()
                )
            )
        ),
        "bindings": [bindings[key] for key in sorted(bindings)],
        "exact_channel_alias_match_required": True,
        "fuzzy_identity_mapping_used": False,
        "ready": not blockers,
        "blockers": sorted(set(blockers)),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _safe_identity_attestation_receipt(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Project private catalog bindings into a hash-only plan receipt."""

    bindings = (
        receipt.get("bindings")
        if isinstance(receipt.get("bindings"), list)
        else []
    )
    return {
        "schema": str(receipt.get("schema") or ""),
        "attested_on": str(receipt.get("attested_on") or ""),
        "probe_artifact_count": int(receipt.get("probe_artifact_count") or 0),
        "probe_artifact_set_sha256": str(
            receipt.get("probe_artifact_set_sha256") or ""
        ),
        "expected_profile_count": int(
            receipt.get("expected_profile_count") or 0
        ),
        "attested_profile_count": int(
            receipt.get("attested_profile_count") or 0
        ),
        "profile_set_sha256": str(receipt.get("profile_set_sha256") or ""),
        "attestation_set_sha256": str(
            receipt.get("attestation_set_sha256") or ""
        ),
        "bindings": [
            {
                "attestation_kind": str(
                    binding.get("attestation_kind") or ""
                ),
                "channel_model_identity_attested": (
                    binding.get("channel_model_identity_attested") is True
                ),
                "profile_id_sha256": str(
                    binding.get("profile_id_sha256") or ""
                ),
                "provider_alias_sha256": str(
                    binding.get("provider_alias_sha256") or ""
                ),
                "model_alias_sha256": str(
                    binding.get("model_alias_sha256") or ""
                ),
                "canonical_model_id_sha256": str(
                    binding.get("canonical_model_id_sha256") or ""
                ),
                "base_url_sha256": str(
                    binding.get("base_url_sha256") or ""
                ),
                "attested_on": str(binding.get("attested_on") or ""),
                "source_locator_sha256": sha256_text(
                    str(binding.get("source_locator") or "")
                ),
                "source_snapshot_sha256": str(
                    binding.get("source_snapshot_sha256") or ""
                ),
                "attestation_content_sha256": str(
                    binding.get("attestation_content_sha256") or ""
                ),
                "raw_source_locator_persisted": False,
            }
            for binding in bindings
            if isinstance(binding, Mapping)
        ],
        "exact_channel_alias_match_required": (
            receipt.get("exact_channel_alias_match_required") is True
        ),
        "fuzzy_identity_mapping_used": (
            receipt.get("fuzzy_identity_mapping_used") is True
        ),
        "ready": receipt.get("ready") is True,
        "blockers": sorted(
            str(reason) for reason in receipt.get("blockers", []) if str(reason)
        ),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _load_registry_for_screening(
    registry_file: Path,
    blockers: list[str],
) -> list[ModelProfile]:
    if not registry_file.is_file():
        blockers.append("screening_registry_file_missing")
        return []
    try:
        return list(load_registry(registry_file))
    except Exception:  # noqa: BLE001 - safe plan must not expose private data
        blockers.append("screening_registry_load_failed")
        return []


def _load_private_json(
    path: Path,
    *,
    reason_prefix: str,
    blockers: list[str],
) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        blockers.append(f"{reason_prefix}_file_missing")
        return {}, ""
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        blockers.append(f"{reason_prefix}_invalid_json")
        return {}, ""
    if not isinstance(value, Mapping):
        blockers.append(f"{reason_prefix}_not_object")
        return {}, sha256_text(raw)
    return dict(value), sha256_text(raw)


def _apply_operational_admission_filter(
    profiles: Sequence[ModelProfile],
    *,
    operational_admission_path: str | Path | None,
    blockers: list[str],
) -> tuple[list[ModelProfile], dict[str, Any]]:
    """Bind baseline candidates to the independent long-request gate."""

    if operational_admission_path is None or not str(operational_admission_path).strip():
        return list(profiles), {
            "required": False,
            "status": "not_required",
            "content_sha256": "",
            "eligible_profile_id_sha256s": [],
            "candidate_profile_count": len(profiles),
            "formal_baseline_eligible_count": None,
            "reason_codes": [],
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "secrets_persisted": False,
        }
    validation = validate_operational_admission_handoff(
        operational_admission_path,
        profiles,
        require_formal=True,
    )
    reason_codes = [str(reason) for reason in validation.get("reason_codes", []) if str(reason)]
    blockers.extend(reason_codes)
    eligible_ids = {
        str(value)
        for value in validation.get("eligible_profile_ids", [])
        if str(value)
    }
    filtered = [profile for profile in profiles if profile.profile_id in eligible_ids]
    if validation.get("valid") is not True:
        filtered = []
    if not filtered:
        blockers.append("screening_operational_admission_left_no_baseline_profiles")
    return filtered, {
        "required": True,
        "status": "ready" if validation.get("valid") is True else "blocked",
        "content_sha256": str(validation.get("content_sha256") or ""),
        "eligible_profile_id_sha256s": sorted(
            str(value)
            for value in validation.get("eligible_profile_id_sha256s", [])
            if str(value)
        ),
        "candidate_profile_count": len(profiles),
        "filtered_profile_count": len(filtered),
        "formal_baseline_eligible_count": int(
            validation.get("formal_baseline_eligible_count") or 0
        ),
        "reason_codes": sorted(set(reason_codes)),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _canonical_live_groups(profiles: Sequence[ModelProfile]) -> list[dict[str, Any]]:
    """Project the evaluation subsystem's canonical replica groups.

    Baseline aliases are historical representative-profile hashes.  Reusing
    the exact evaluation helper here is therefore an integrity requirement:
    choosing a different representative would make a scientifically valid
    screening campaign impossible to bind to the later freeze.
    """

    rows: list[dict[str, Any]] = []
    for group in _provider_baseline_group_summaries(profiles, live_only=True):
        canonical_hash = str(group["canonical_identity_sha256"])
        replicas = tuple(group["replicas"])
        representative = group["representative"]
        profile_hashes = list(group["replica_profile_id_sha256s"])
        representative_hash = sha256_text(representative.profile_id)
        rows.append(
            {
                "canonical_identity_sha256": canonical_hash,
                "canonical_model_id_sha256": (
                    sha256_text(representative.canonical_model_id)
                    if representative.canonical_model_id
                    else ""
                ),
                "canonical_model_identity_declared": all(
                    bool(item.canonical_model_id) for item in replicas
                ),
                "representative": representative,
                "representative_profile_id_sha256": representative_hash,
                "candidate_id_sha256": sha256_text(
                    f"provider::{representative_hash}"
                ),
                "replicas": replicas,
                "replica_profile_id_sha256s": profile_hashes,
                "replica_profile_set_sha256": str(
                    group["replica_profile_set_sha256"]
                ),
                "replica_count": len(replicas),
            }
        )
    return sorted(rows, key=lambda row: str(row["canonical_identity_sha256"]))


def _safe_group_row(group: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_identity_sha256": str(
            group.get("canonical_identity_sha256") or ""
        ),
        "canonical_model_id_sha256": str(
            group.get("canonical_model_id_sha256") or ""
        ),
        "canonical_model_identity_declared": (
            group.get("canonical_model_identity_declared") is True
        ),
        "representative_profile_id_sha256": str(
            group.get("representative_profile_id_sha256") or ""
        ),
        "candidate_id_sha256": str(group.get("candidate_id_sha256") or ""),
        "replica_count": int(group.get("replica_count") or 0),
        "replica_profile_id_sha256s": list(
            group.get("replica_profile_id_sha256s") or []
        ),
        "replica_profile_set_sha256": str(
            group.get("replica_profile_set_sha256") or ""
        ),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
    }


def _screening_adapter_runtime_preflight(
    source: Mapping[str, Any],
) -> list[str]:
    """Validate optional official scorer imports before any provider call.

    A source plan is a frozen execution contract.  Discovering a missing
    scorer dependency only after hundreds of remote answers have been
    collected would waste provider budget and leave an ambiguous campaign
    checkpoint.  The preflight intentionally returns stable reason codes and
    keeps the dependency exception text out of persisted artifacts.
    """

    adapter = str(source.get("adapter") or "")
    if adapter != "livebench_official":
        return []
    try:
        _livebench_scorers(str(source.get("harness_root") or ""))
    except ImportError:
        return ["screening_source_runtime_dependency_missing"]
    except Exception:  # noqa: BLE001 - private harness details stay local
        return ["screening_source_runtime_preflight_failed"]
    return []


def _screening_source_receipt(
    source: Any,
    *,
    selection_seed: str,
    min_cases_per_source: int,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not isinstance(source, Mapping):
        return _empty_source_receipt(), ["screening_source_row_invalid"]
    source_id = str(source.get("source_id") or "").strip()
    source_family = str(source.get("source_family") or "").strip()
    adapter = str(source.get("adapter") or "").strip()
    source_type = str(source.get("source_type") or "")
    retrieved_on = str(source.get("retrieved_on") or "")
    if not source_id:
        blockers.append("screening_source_id_missing")
    if not source_family:
        blockers.append("screening_source_family_missing")
    if adapter not in SUPPORTED_SCREENING_ADAPTERS:
        blockers.append("screening_source_adapter_unsupported")
    if source_type != "independent_evaluation_report":
        blockers.append("screening_source_type_not_independent_evaluation")
    if not _valid_iso_date(retrieved_on):
        blockers.append("screening_source_retrieval_date_invalid")
    if source.get("supports_general_capability_ranking") is not True:
        blockers.append("screening_source_scope_inadequate")
    if source.get("uses_target_benchmark_results") is not False:
        blockers.append("screening_source_uses_target_results")

    cases: list[ScreeningCase] = []
    try:
        cases = _load_source_cases(source)
    except Exception:  # noqa: BLE001 - paths and dataset rows remain private
        blockers.append("screening_source_load_failed")
    runtime_preflight_blockers = _screening_adapter_runtime_preflight(source)
    blockers.extend(runtime_preflight_blockers)
    selected_cases = _select_screening_cases(
        cases,
        source.get("selection"),
        selection_seed=selection_seed,
        source_id=source_id,
    )
    required_cases = max(
        min_cases_per_source,
        _optional_int(source.get("minimum_case_count")) or 0,
    )
    if len(selected_cases) < required_cases:
        blockers.append("screening_source_selected_case_count_below_minimum")

    file_receipts, file_blockers = _source_file_receipts(source)
    blockers.extend(file_blockers)
    case_hashes = sorted(sha256_text(case.case_id) for case in selected_cases)
    case_contract = _screening_case_contract_receipt(selected_cases)
    adapter_implementation_sha256 = _screening_adapter_implementation_sha256(
        adapter
    )
    decoding_receipt = _safe_decoding_receipt(source.get("decoding"))
    if not _looks_like_sha256(adapter_implementation_sha256):
        blockers.append("screening_source_adapter_implementation_digest_missing")
    snapshot_input = {
        "source_id": source_id,
        "source_family": source_family,
        "adapter": adapter,
        "file_receipts": file_receipts,
        "selection": _safe_selection_policy(source.get("selection")),
        "prompt_protocol": _safe_protocol_receipt(source.get("prompt_protocol")),
        "decoding": decoding_receipt,
        "adapter_configuration": _safe_adapter_configuration_receipt(source),
        "runtime_preflight_blockers": sorted(set(runtime_preflight_blockers)),
        "selected_case_hashes": case_hashes,
        **case_contract,
        "adapter_implementation_sha256": adapter_implementation_sha256,
    }
    source_snapshot_sha256 = sha256_text(stable_json(snapshot_input))
    declared_snapshot = str(source.get("source_snapshot_sha256") or "")
    if declared_snapshot and declared_snapshot != source_snapshot_sha256:
        blockers.append("screening_source_declared_snapshot_mismatch")
    return (
        {
            "source_id_sha256": sha256_text(source_id),
            "source_family_sha256": sha256_text(source_family),
            "source_type": source_type,
            "adapter": adapter,
            "retrieved_on": retrieved_on,
            "supports_general_capability_ranking": (
                source.get("supports_general_capability_ranking") is True
            ),
            "uses_target_benchmark_results": False,
            "source_locator_sha256": sha256_text(
                str(source.get("source_locator") or "")
            ),
            "source_snapshot_sha256": source_snapshot_sha256,
            "source_file_count": len(file_receipts),
            "source_file_set_sha256": sha256_text(
                stable_json(file_receipts)
            ),
            "available_case_count": len(cases),
            "selected_case_count": len(selected_cases),
            "required_case_count": required_cases,
            "case_set_digest_sha256": sha256_text(stable_json(case_hashes)),
            **case_contract,
            "adapter_implementation_sha256": adapter_implementation_sha256,
            "case_id_hashes": case_hashes,
            "stratum_count": len({case.stratum for case in selected_cases}),
            "selection_policy": _safe_selection_policy(source.get("selection")),
            "prompt_protocol_sha256": sha256_text(
                stable_json(_safe_protocol_receipt(source.get("prompt_protocol")))
            ),
            "decoding_config_sha256": sha256_text(
                stable_json(_safe_decoding_receipt(source.get("decoding")))
            ),
            "adapter_configuration_sha256": sha256_text(
                stable_json(_safe_adapter_configuration_receipt(source))
            ),
            "runtime_preflight_ready": not runtime_preflight_blockers,
            "runtime_preflight_blockers": sorted(
                set(runtime_preflight_blockers)
            ),
            "configured_timeout_seconds": decoding_receipt[
                "configured_timeout_seconds"
            ],
            "effective_timeout_seconds": decoding_receipt["timeout_seconds"],
            "timeout_cap_seconds": decoding_receipt["timeout_cap_seconds"],
            "timeout_cap_applied": decoding_receipt["timeout_cap_applied"],
            "max_transport_failure_rate": _bounded_failure_rate(
                source.get("max_transport_failure_rate")
            ),
            "ready": not blockers,
            "blockers": sorted(set(blockers)),
            "raw_dataset_paths_persisted": False,
            "raw_questions_persisted": False,
            "raw_labels_persisted": False,
            "raw_source_locator_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        sorted(set(blockers)),
    )


def _empty_source_receipt() -> dict[str, Any]:
    return {
        "source_id_sha256": sha256_text(""),
        "source_family_sha256": sha256_text(""),
        "selected_case_count": 0,
        "ready": False,
        "raw_dataset_paths_persisted": False,
        "raw_questions_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _source_file_receipts(
    source: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    paths: list[tuple[str, str]] = []
    for key in ("dataset_path", "validation_path", "harness_path"):
        value = str(source.get(key) or "")
        if value:
            paths.append((key, value))
    for value in source.get("dataset_paths", []) if isinstance(source.get("dataset_paths"), list) else []:
        if str(value):
            paths.append(("dataset_paths", str(value)))
    harness_root = str(source.get("harness_root") or "")
    if harness_root:
        archive = str(source.get("harness_archive_path") or "")
        if archive:
            paths.append(("harness_archive_path", archive))
        elif Path(harness_root).is_dir():
            paths.append(("harness_root_marker", str(Path(harness_root) / "README.md")))
    receipts: list[dict[str, Any]] = []
    for kind, raw_path in paths:
        path = Path(raw_path)
        digest = _file_sha256(path)
        if not digest:
            blockers.append("screening_source_required_file_missing")
        receipts.append(
            {
                "kind": kind,
                "path_sha256": sha256_text(str(path)),
                "content_sha256": digest,
                "size_bytes": path.stat().st_size if path.is_file() else 0,
            }
        )
    if not receipts:
        blockers.append("screening_source_files_missing")
    return sorted(receipts, key=lambda row: (row["kind"], row["path_sha256"])), blockers


def _load_source_cases(source: Mapping[str, Any]) -> list[ScreeningCase]:
    adapter = str(source.get("adapter") or "")
    if adapter == "jsonl_multiple_choice":
        return _load_jsonl_multiple_choice_cases(Path(str(source.get("dataset_path") or "")))
    if adapter == "mmlu_pro":
        return _load_mmlu_pro_cases(source)
    if adapter == "livebench_official":
        return _load_livebench_cases(source)
    raise ValueError("unsupported screening source adapter")


def _load_jsonl_multiple_choice_cases(path: Path) -> list[ScreeningCase]:
    rows = _read_jsonl(path)
    cases: list[ScreeningCase] = []
    for index, row in enumerate(rows):
        options = [str(item) for item in row.get("options", [])]
        labels = [chr(ord("A") + offset) for offset in range(len(options))]
        question = str(row.get("question") or row.get("prompt") or "")
        if not question or not options:
            continue
        case_id = str(row.get("id") or row.get("case_id") or index)
        prompt = _multiple_choice_prompt(question, options, labels)
        cases.append(
            ScreeningCase(
                case_id=case_id,
                prompt=prompt,
                reference=str(row.get("answer") or "").strip().upper(),
                stratum=str(row.get("category") or "default"),
                metadata={"adapter": "jsonl_multiple_choice"},
            )
        )
    return cases


def _load_mmlu_pro_cases(source: Mapping[str, Any]) -> list[ScreeningCase]:
    test_rows = _read_parquet(Path(str(source.get("dataset_path") or "")))
    validation_rows = _read_parquet(Path(str(source.get("validation_path") or "")))
    examples_by_category: dict[str, list[Mapping[str, Any]]] = {}
    for row in validation_rows:
        category = str(row.get("category") or "")
        examples_by_category.setdefault(category, []).append(row)
    shots = max(
        0,
        min(
            5,
            _optional_int(
                (source.get("prompt_protocol") or {}).get("shots")
                if isinstance(source.get("prompt_protocol"), Mapping)
                else None
            )
            or 5,
        ),
    )
    cases: list[ScreeningCase] = []
    for index, row in enumerate(test_rows):
        question = str(row.get("question") or "")
        options = [str(item) for item in row.get("options", []) if str(item) != "N/A"]
        category = str(row.get("category") or "other")
        if not question or not options:
            continue
        prefix = (
            "The following are multiple choice questions (with answers) about "
            f"{category}. Think step by step and then output the answer in the "
            'format of "The answer is (X)" at the end.\n\n'
        )
        demonstrations = "".join(
            _format_mmlu_example(example, include_answer=True)
            for example in examples_by_category.get(category, [])[:shots]
        )
        prompt = prefix + demonstrations + _format_mmlu_example(row, include_answer=False)
        cases.append(
            ScreeningCase(
                case_id=f"mmlu-pro:{row.get('question_id', index)}",
                prompt=prompt,
                reference=str(row.get("answer") or "").strip().upper(),
                stratum=category,
                metadata={"adapter": "mmlu_pro", "category": category},
            )
        )
    return cases


def _format_mmlu_example(row: Mapping[str, Any], *, include_answer: bool) -> str:
    options = [str(item) for item in row.get("options", []) if str(item) != "N/A"]
    option_lines = [
        f"{chr(ord('A') + index)}. {option}"
        for index, option in enumerate(options)
    ]
    lines = [
        f"Question: {str(row.get('question') or '')}",
        "Options: " + (option_lines[0] if option_lines else ""),
        *option_lines[1:],
    ]
    if include_answer:
        cot = str(row.get("cot_content") or "Let's think step by step.")
        if cot.startswith("A: "):
            cot = cot[3:]
        lines.append(f"Answer: {cot}")
        lines.append("")
    else:
        lines.append("Answer: Let's think step by step.")
        lines.append("")
    return "\n".join(lines) + "\n"


def _load_livebench_cases(source: Mapping[str, Any]) -> list[ScreeningCase]:
    included_tasks = {
        str(item)
        for item in source.get("included_tasks", [])
        if str(item)
    } if isinstance(source.get("included_tasks"), list) else set(_LIVEBENCH_SUPPORTED_TASKS)
    if not included_tasks or not included_tasks.issubset(_LIVEBENCH_SUPPORTED_TASKS):
        raise ValueError("unsupported LiveBench task selected")
    rows: list[Mapping[str, Any]] = []
    for value in source.get("dataset_paths", []) if isinstance(source.get("dataset_paths"), list) else []:
        rows.extend(_read_parquet(Path(str(value))))
    selected_release = str(source.get("livebench_release_option") or "")
    if not _valid_iso_date(selected_release):
        raise ValueError("LiveBench release option is required")
    cases: list[ScreeningCase] = []
    for row in rows:
        task = str(row.get("task") or "")
        if task not in included_tasks:
            continue
        release_date = _date_text(row.get("livebench_release_date"))
        removal_date = _date_text(row.get("livebench_removal_date"))
        if not release_date or release_date > selected_release:
            continue
        if removal_date and removal_date <= selected_release:
            continue
        turns = row.get("turns")
        if isinstance(turns, str):
            try:
                turns = ast.literal_eval(turns)
            except (SyntaxError, ValueError):
                turns = [turns]
        prompt = str(turns[0] if isinstance(turns, list) and turns else "")
        case_id = str(row.get("question_id") or "")
        if not prompt or not case_id:
            continue
        cases.append(
            ScreeningCase(
                case_id=f"livebench:{case_id}",
                prompt=prompt,
                reference=row.get("ground_truth"),
                stratum=task,
                metadata={
                    "adapter": "livebench_official",
                    "task": task,
                    "subtask": str(row.get("subtask") or ""),
                    "livebench_release_date": release_date,
                    "livebench_release_option": selected_release,
                    "question_text": prompt,
                },
            )
        )
    return cases


def _select_screening_cases(
    cases: Sequence[ScreeningCase],
    selection: Any,
    *,
    selection_seed: str,
    source_id: str,
) -> list[ScreeningCase]:
    policy = selection if isinstance(selection, Mapping) else {}
    max_per_stratum = _optional_int(policy.get("max_per_stratum"))
    max_cases = _optional_int(policy.get("max_cases"))
    grouped: dict[str, list[ScreeningCase]] = {}
    for case in cases:
        grouped.setdefault(case.stratum or "default", []).append(case)
    selected: list[ScreeningCase] = []
    for stratum in sorted(grouped):
        rows = sorted(
            grouped[stratum],
            key=lambda case: sha256_text(
                f"{selection_seed}:{source_id}:{stratum}:{case.case_id}"
            ),
        )
        if max_per_stratum is not None:
            rows = rows[: max(0, max_per_stratum)]
        selected.extend(rows)
    selected.sort(
        key=lambda case: sha256_text(
            f"{selection_seed}:{source_id}:all:{case.case_id}"
        )
    )
    if max_cases is not None:
        selected = selected[: max(0, max_cases)]
    return selected


def _safe_selection_policy(value: Any) -> dict[str, Any]:
    policy = value if isinstance(value, Mapping) else {}
    return {
        "strategy": str(policy.get("strategy") or "stratified_sha256_order"),
        "max_per_stratum": _optional_int(policy.get("max_per_stratum")),
        "max_cases": _optional_int(policy.get("max_cases")),
        "selection_is_label_blind": True,
        "selection_is_model_output_blind": True,
    }


def _safe_protocol_receipt(value: Any) -> dict[str, Any]:
    protocol = value if isinstance(value, Mapping) else {}
    system_prompt_declared = "system_prompt" in protocol
    system_prompt = str(protocol.get("system_prompt") or "")
    return {
        "shots": max(0, _optional_int(protocol.get("shots")) or 0),
        "answer_extraction": str(protocol.get("answer_extraction") or "source_adapter"),
        "official_prompt_family": str(protocol.get("official_prompt_family") or ""),
        "system_prompt_declared": system_prompt_declared,
        "system_prompt_sha256": (
            sha256_text(system_prompt) if system_prompt_declared else ""
        ),
        "retry_on_wrong_answer": False,
        "raw_prompt_persisted": False,
    }


def _safe_decoding_receipt(value: Any) -> dict[str, Any]:
    decoding = value if isinstance(value, Mapping) else {}
    configured_timeout = max(
        1.0,
        _optional_float(decoding.get("timeout_seconds")) or 120.0,
    )
    effective_timeout = min(
        PROVIDER_MAX_RESPONSE_SECONDS,
        configured_timeout,
    )
    return {
        "temperature": _optional_float(decoding.get("temperature")),
        "top_p": _optional_float(decoding.get("top_p")),
        "max_output_tokens": max(
            1,
            _optional_int(decoding.get("max_output_tokens")) or 1024,
        ),
        # Baseline screening is also a serving-eligibility input. A source
        # manifest cannot extend the provider response budget beyond the
        # shared 90-second policy, otherwise a slow model could enter the
        # external ranking cohort while the Fusion registry rejects it.
        "configured_timeout_seconds": round(configured_timeout, 3),
        "timeout_seconds": round(effective_timeout, 3),
        "timeout_cap_seconds": PROVIDER_MAX_RESPONSE_SECONDS,
        "timeout_cap_applied": configured_timeout > PROVIDER_MAX_RESPONSE_SECONDS,
        "max_exception_attempt_rounds": max(
            1,
            min(
                3,
                _optional_int(decoding.get("max_exception_attempt_rounds")) or 1,
            ),
        ),
        "retry_on_wrong_answer": False,
    }


def _safe_adapter_configuration_receipt(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    tasks = sorted(
        str(item)
        for item in source.get("included_tasks", [])
        if str(item)
    ) if isinstance(source.get("included_tasks"), list) else []
    return {
        "adapter": str(source.get("adapter") or ""),
        "livebench_release_option": str(
            source.get("livebench_release_option") or ""
        ),
        "included_task_count": len(tasks),
        "included_task_set_sha256": sha256_text(stable_json(tasks)),
        "raw_task_names_persisted": False,
    }


def _screening_case_contract_receipt(
    cases: Sequence[ScreeningCase],
) -> dict[str, str]:
    prompt_rows = sorted(
        (
            {
                "case_id_sha256": sha256_text(case.case_id),
                "prompt_sha256": sha256_text(case.prompt),
            }
            for case in cases
        ),
        key=lambda row: row["case_id_sha256"],
    )
    reference_rows = sorted(
        (
            {
                "case_id_sha256": sha256_text(case.case_id),
                "reference_sha256": sha256_text(stable_json(case.reference)),
            }
            for case in cases
        ),
        key=lambda row: row["case_id_sha256"],
    )
    contract_rows = sorted(
        (
            {
                "case_id_sha256": sha256_text(case.case_id),
                "prompt_sha256": sha256_text(case.prompt),
                "reference_sha256": sha256_text(stable_json(case.reference)),
                "stratum_sha256": sha256_text(case.stratum),
            }
            for case in cases
        ),
        key=lambda row: row["case_id_sha256"],
    )
    return {
        "prompt_set_digest_sha256": sha256_text(stable_json(prompt_rows)),
        "reference_set_digest_sha256": sha256_text(
            stable_json(reference_rows)
        ),
        "case_contract_set_digest_sha256": sha256_text(
            stable_json(contract_rows)
        ),
    }


def _screening_adapter_implementation_sha256(adapter: str) -> str:
    common = [
        _select_screening_cases,
        _run_screening_case,
        _score_screening_output,
    ]
    selected = {
        "jsonl_multiple_choice": [
            _load_jsonl_multiple_choice_cases,
            _multiple_choice_prompt,
            _extract_single_choice,
        ],
        "mmlu_pro": [
            _load_mmlu_pro_cases,
            _format_mmlu_example,
            _extract_mmlu_choice,
        ],
        "livebench_official": [
            _load_livebench_cases,
            _score_livebench_output,
            _livebench_scorers,
        ],
    }.get(str(adapter or ""), [])
    if not selected:
        return ""
    try:
        source_rows = [
            inspect.getsource(callable_value)
            for callable_value in [*common, *selected]
        ]
    except (OSError, TypeError):
        return ""
    for old_source, new_source in _NON_SEMANTIC_SCREENING_SOURCE_REWRITES:
        source_rows = [
            source_row.replace(old_source, new_source)
            for source_row in source_rows
        ]
    contract = {
        "adapter": str(adapter),
        "source_rows": source_rows,
        "mmlu_answer_patterns": [
            pattern.pattern for pattern in _MMLU_ANSWER_PATTERNS
        ],
        "livebench_supported_tasks": sorted(_LIVEBENCH_SUPPORTED_TASKS),
    }
    return sha256_text(stable_json(contract))


def _screening_plan_digest_input(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"plan_digest_sha256", "ready", "blockers"}
    }


def _profile_has_live_probe_evidence(profile: ModelProfile) -> bool:
    return "live" in str(profile.source or "").lower() or (
        str(profile.health or "").lower() == "available"
        and int(profile.observed_success_count or 0) > 0
    )


def _safe_artifact_contract() -> dict[str, bool]:
    return {
        "raw_dataset_paths_persisted": False,
        "raw_questions_persisted": False,
        "raw_options_persisted": False,
        "raw_labels_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _screening_safe_artifact_leakage_errors(value: Any) -> list[str]:
    """Fail closed when a nominally safe screening artifact contains raw data."""

    errors: list[str] = []
    forbidden_raw_keys = {
        "api_key",
        "base_url",
        "dataset_path",
        "dataset_paths",
        "harness_path",
        "harness_root",
        "model",
        "model_id",
        "model_ids",
        "output",
        "outputs",
        "private_root",
        "prompt",
        "provider",
        "question",
        "reference",
        "source_id",
        "source_locator",
    }

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for raw_key, child in item.items():
                key = str(raw_key or "").strip().lower()
                if key.endswith("_persisted") and child is True:
                    errors.append("screening_safe_artifact_true_persistence_flag")
                if key in forbidden_raw_keys and child not in (None, "", [], {}):
                    errors.append("screening_safe_artifact_raw_field_present")
                walk(child)
            return
        if isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for child in item:
                walk(child)
            return
        if not isinstance(item, str):
            return
        text = item.strip()
        lowered = text.lower()
        if re.search(r"(?:https?|file)://", lowered):
            errors.append("screening_safe_artifact_raw_url_present")
        if text.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text):
            errors.append("screening_safe_artifact_raw_path_present")
        if re.search(r"\b(?:sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,})\b", text):
            errors.append("screening_safe_artifact_api_key_like_value_present")

    walk(value)
    return sorted(set(errors))


def _multiple_choice_prompt(
    question: str,
    options: Sequence[str],
    labels: Sequence[str],
) -> str:
    lines = [question, ""]
    lines.extend(f"{label}. {option}" for label, option in zip(labels, options))
    lines.extend(["", "Answer with only the single best option letter."])
    return "\n".join(lines)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as parquet  # type: ignore[import-not-found]

    return [dict(row) for row in parquet.read_table(path).to_pylist()]


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_iso_date(value: Any) -> bool:
    from datetime import date

    try:
        date.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return False
    return True


def _date_text(value: Any) -> str:
    if hasattr(value, "strftime"):
        try:
            return str(value.strftime("%Y-%m-%d"))
        except Exception:  # noqa: BLE001
            pass
    return str(value or "")[:10]


def _screening_live_credential_receipt(
    *,
    profiles: Sequence[ModelProfile],
    required_profile_hashes: Sequence[str],
    identity_attestation: Mapping[str, Any],
    injected_client: bool,
) -> dict[str, Any]:
    """Project transport readiness without persisting env names or values."""

    required = sorted({str(value) for value in required_profile_hashes if str(value)})
    by_hash = {sha256_text(profile.profile_id): profile for profile in profiles}
    ready_hashes: list[str] = []
    invalid_base_url_count = 0
    missing_base_url_count = 0
    missing_api_key_count = 0
    endpoint_binding_missing_count = 0
    endpoint_binding_mismatch_count = 0
    api_format_counts: dict[str, int] = {}
    reason_codes: list[str] = []
    identity_by_profile = {
        str(row.get("profile_id_sha256") or ""): row
        for row in identity_attestation.get("bindings", [])
        if isinstance(row, Mapping) and str(row.get("profile_id_sha256") or "")
    } if isinstance(identity_attestation.get("bindings"), list) else {}
    if injected_client:
        # Test or embedding clients own their transport configuration. The
        # campaign still binds that fact, while production CLI execution uses
        # HTTPProviderClient and must pass the environment-backed checks below.
        ready_hashes = list(required)
        mode = "injected_client_transport_owned"
    else:
        mode = "environment_backed_http_provider_client"
        for profile_hash in required:
            profile = by_hash.get(profile_hash)
            if profile is None:
                reason_codes.append("screening_live_credential_profile_unresolved")
                continue
            readiness = profile_credential_readiness(profile)
            if readiness.get("credential_ready") is True:
                binding = identity_by_profile.get(profile_hash)
                attested_endpoint_hash = str(
                    binding.get("base_url_sha256") or ""
                ) if isinstance(binding, Mapping) else ""
                current_endpoint_hash = str(readiness.get("base_url_sha256") or "")
                if not attested_endpoint_hash:
                    endpoint_binding_missing_count += 1
                    continue
                if attested_endpoint_hash != current_endpoint_hash:
                    endpoint_binding_mismatch_count += 1
                    continue
                ready_hashes.append(profile_hash)
                api_format = str(profile.api_format or "")
                api_format_counts[api_format] = api_format_counts.get(api_format, 0) + 1
                continue
            if readiness.get("base_url_configured") is not True:
                missing_base_url_count += 1
            elif readiness.get("base_url_valid") is not True:
                invalid_base_url_count += 1
            if (
                readiness.get("api_key_required") is True
                and int(readiness.get("api_key_count") or 0) < 1
            ):
                missing_api_key_count += 1
    missing_hashes = sorted(set(required) - set(ready_hashes))
    if missing_hashes:
        reason_codes.append("screening_live_credentials_incomplete")
    if missing_base_url_count:
        reason_codes.append("screening_live_base_url_missing")
    if invalid_base_url_count:
        reason_codes.append("screening_live_base_url_invalid")
    if missing_api_key_count:
        reason_codes.append("screening_live_api_key_missing")
    if endpoint_binding_missing_count:
        reason_codes.append("screening_live_endpoint_attestation_missing")
    if endpoint_binding_mismatch_count:
        reason_codes.append("screening_live_endpoint_attestation_mismatch")
    core = {
        "schema": "axio_fusion_api.non_target_screening_live_credential_readiness.v1",
        "mode": mode,
        "required_profile_count": len(required),
        "credential_ready_profile_count": len(ready_hashes),
        "missing_profile_count": len(missing_hashes),
        "required_profile_set_sha256": sha256_text(stable_json(required)),
        "credential_ready_profile_set_sha256": sha256_text(
            stable_json(sorted(ready_hashes))
        ),
        "missing_profile_set_sha256": sha256_text(stable_json(missing_hashes)),
        "credential_ready_api_format_counts": dict(sorted(api_format_counts.items())),
        "missing_base_url_count": missing_base_url_count,
        "invalid_base_url_count": invalid_base_url_count,
        "missing_api_key_count": missing_api_key_count,
        "endpoint_binding_missing_count": endpoint_binding_missing_count,
        "endpoint_binding_mismatch_count": endpoint_binding_mismatch_count,
        "endpoint_identity_binding_required": not injected_client,
        "injected_client": bool(injected_client),
        "ready": not reason_codes,
        "reason_codes": sorted(set(reason_codes)),
        "raw_base_urls_persisted": False,
        "raw_base_url_env_names_persisted": False,
        "raw_api_key_env_names_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }
    return {
        **core,
        "readiness_digest_sha256": sha256_text(stable_json(core)),
    }


def _bounded_failure_rate(value: Any) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        return DEFAULT_MAX_TRANSPORT_FAILURE_RATE
    return max(0.0, min(1.0, parsed))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_non_target_screening_campaign(
    *,
    plan_path: str | Path,
    registry_path: str | Path,
    source_manifest_path: str | Path,
    private_probe_files: Sequence[str | Path],
    private_root: str | Path,
    state_path: str | Path | None = None,
    live: bool = False,
    max_workers: int = 4,
    max_tasks: int | None = None,
    retry_failed: bool = False,
    overwrite: bool = False,
    operational_admission_path: str | Path | None = None,
    client: HTTPProviderClient | None = None,
) -> dict[str, Any]:
    """Execute or resume a pre-registered complete-pool screening campaign."""

    started = time.monotonic()
    plan_file = Path(plan_path)
    registry_file = Path(registry_path)
    source_file = Path(source_manifest_path)
    output_root = Path(private_root)
    selected_state_path = Path(state_path) if state_path else None
    blockers: list[str] = []
    if overwrite:
        blockers.append("screening_overwrite_forbidden")
    plan, plan_file_sha256 = _load_private_json(
        plan_file,
        reason_prefix="screening_plan",
        blockers=blockers,
    )
    if plan.get("schema") != SCREENING_PLAN_SCHEMA:
        blockers.append("screening_plan_schema_invalid")
    if plan.get("ready") is not True:
        blockers.append("screening_plan_not_ready")
    blockers.extend(_screening_execution_schedule_errors(plan))
    current_plan = build_non_target_screening_plan(
        registry_path=registry_file,
        source_manifest_path=source_file,
        private_probe_files=private_probe_files,
        min_cases_per_source=int(
            plan.get("minimum_cases_per_source") or DEFAULT_MIN_CASES_PER_SOURCE
        ),
        operational_admission_path=operational_admission_path,
    )
    plan_digest = str(plan.get("plan_digest_sha256") or "")
    if not _looks_like_sha256(plan_digest):
        blockers.append("screening_plan_digest_invalid")
    if current_plan.get("plan_digest_sha256") != plan_digest:
        blockers.append("screening_plan_current_inputs_mismatch")
    if current_plan.get("ready") is not True:
        blockers.extend(
            f"current_{reason}" for reason in current_plan.get("blockers", [])
        )

    source_manifest, source_manifest_sha256 = _load_private_json(
        source_file,
        reason_prefix="screening_source_manifest",
        blockers=blockers,
    )
    profiles = _load_registry_for_screening(registry_file, blockers)
    profiles, operational_admission = _apply_operational_admission_filter(
        profiles,
        operational_admission_path=operational_admission_path,
        blockers=blockers,
    )
    profile_by_hash = {sha256_text(item.profile_id): item for item in profiles}
    groups = {
        str(row["canonical_identity_sha256"]): row
        for row in _canonical_live_groups(profiles)
    }
    raw_sources = {
        str(row.get("source_id") or ""): row
        for row in source_manifest.get("sources", [])
        if isinstance(row, Mapping) and str(row.get("source_id") or "")
    } if isinstance(source_manifest.get("sources"), list) else {}
    source_receipts = {
        str(row.get("source_id_sha256") or ""): row
        for row in plan.get("sources", [])
        if isinstance(row, Mapping) and str(row.get("source_id_sha256") or "")
    } if isinstance(plan.get("sources"), list) else {}
    selection_seed = str(
        (source_manifest.get("pre_registration") or {}).get("selection_seed")
        if isinstance(source_manifest.get("pre_registration"), Mapping)
        else ""
    )

    selected_cases: dict[str, list[ScreeningCase]] = {}
    for source_id, source in raw_sources.items():
        try:
            cases = _select_screening_cases(
                _load_source_cases(source),
                source.get("selection"),
                selection_seed=selection_seed,
                source_id=source_id,
            )
        except Exception:  # noqa: BLE001
            blockers.append("screening_campaign_source_load_failed")
            continue
        source_hash = sha256_text(source_id)
        receipt = source_receipts.get(source_hash, {})
        case_hashes = sorted(sha256_text(case.case_id) for case in cases)
        if sha256_text(stable_json(case_hashes)) != str(
            receipt.get("case_set_digest_sha256") or ""
        ):
            blockers.append("screening_campaign_case_set_digest_mismatch")
        case_contract = _screening_case_contract_receipt(cases)
        for field in (
            "prompt_set_digest_sha256",
            "reference_set_digest_sha256",
            "case_contract_set_digest_sha256",
        ):
            if str(receipt.get(field) or "") != str(
                case_contract.get(field) or ""
            ):
                blockers.append("screening_campaign_case_contract_mismatch")
        if str(receipt.get("adapter_implementation_sha256") or "") != str(
            _screening_adapter_implementation_sha256(
                str(source.get("adapter") or "")
            )
        ):
            blockers.append("screening_campaign_adapter_implementation_mismatch")
        selected_cases[source_hash] = cases

    task_rows = [
        dict(row)
        for row in plan.get("tasks", [])
        if isinstance(row, Mapping)
    ] if isinstance(plan.get("tasks"), list) else []
    required_profile_hashes = sorted(
        {
            str(value)
            for task in task_rows
            for value in task.get("replica_profile_id_sha256s", [])
            if str(value)
        }
    )
    credential_receipt = _screening_live_credential_receipt(
        profiles=profiles,
        required_profile_hashes=required_profile_hashes,
        identity_attestation=(
            plan.get("identity_attestation_receipt")
            if isinstance(plan.get("identity_attestation_receipt"), Mapping)
            else {}
        ),
        injected_client=client is not None,
    )
    if live and client is None and credential_receipt.get("ready") is not True:
        blockers.extend(
            str(reason)
            for reason in credential_receipt.get("reason_codes", [])
            if str(reason)
        )
    base_state = {
        "schema": SCREENING_CAMPAIGN_SCHEMA,
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "mode": "live" if live else "preflight",
        "plan_file_content_sha256": plan_file_sha256,
        "plan_digest_sha256": plan_digest,
        "execution_schedule_digest_sha256": str(
            (plan.get("execution_schedule") or {}).get(
                "schedule_digest_sha256"
            )
            if isinstance(plan.get("execution_schedule"), Mapping)
            else ""
        ),
        "execution_task_sequence_sha256": str(
            (plan.get("execution_schedule") or {}).get(
                "task_id_sequence_sha256"
            )
            if isinstance(plan.get("execution_schedule"), Mapping)
            else ""
        ),
        "live_credential_readiness": credential_receipt,
        "live_credential_readiness_digest_sha256": str(
            credential_receipt.get("readiness_digest_sha256") or ""
        ),
        "registry_file_sha256": _file_sha256(registry_file),
        "source_manifest_content_sha256": source_manifest_sha256,
        "operational_admission": operational_admission,
        "private_root_sha256": sha256_text(str(output_root)),
        "planned_task_count": int(plan.get("task_count") or 0),
        "selected_task_count": len(task_rows),
        "max_new_tasks": (
            max(0, int(max_tasks)) if max_tasks is not None else None
        ),
        "max_workers": max(1, int(max_workers)),
        "network_calls_performed": False,
        "target_suite_calls_performed": False,
        "benchmark_outputs_used_for_training": False,
        "benchmark_outputs_used_for_prompt_tuning": False,
        "anti_leakage_contract": _safe_artifact_contract(),
        "raw_private_root_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    if blockers:
        # A live preflight failure must never erase a usable checkpoint.  In
        # particular, credentials are intentionally process-local, so a
        # restarted operator process may briefly fail this gate before the
        # same secret resolver is injected again.  Keep the prior state file
        # byte-for-byte intact; the next live invocation can authenticate and
        # resume it.  A first preflight with no checkpoint still gets a normal
        # blocked receipt for operator visibility.
        prior_state = (
            _load_existing_campaign_state(selected_state_path)
            if live
            else {}
        )
        preserve_prior_checkpoint = bool(
            live
            and selected_state_path is not None
            and selected_state_path.is_file()
            and prior_state
        )
        return _finalize_campaign_state(
            base_state,
            units=[],
            status="blocked",
            blockers=blockers,
            elapsed_ms=(time.monotonic() - started) * 1000,
            state_path=None if preserve_prior_checkpoint else selected_state_path,
        )
    if not live:
        return _finalize_campaign_state(
            base_state,
            units=[],
            status="preflight_ready",
            blockers=[],
            elapsed_ms=(time.monotonic() - started) * 1000,
            state_path=selected_state_path,
        )

    output_root.mkdir(parents=True, exist_ok=True)
    existing_state = _load_existing_campaign_state(selected_state_path)
    existing_state = _recover_private_checkpoint_state(
        existing_state,
        base_state=base_state,
        task_rows=task_rows,
        raw_sources=raw_sources,
        selected_cases=selected_cases,
        source_receipts=source_receipts,
        private_root=output_root,
    )
    if (
        selected_state_path is not None
        and selected_state_path.is_file()
        and not existing_state
    ):
        return _finalize_campaign_state(
            base_state,
            units=[],
            status="blocked",
            blockers=["screening_resume_state_invalid"],
            elapsed_ms=(time.monotonic() - started) * 1000,
            state_path=None,
        )
    resume_errors = _screening_resume_state_errors(
        existing_state,
        base_state=base_state,
    )
    if existing_state and not resume_errors:
        task_by_id = {
            str(row.get("task_id") or ""): row
            for row in task_rows
            if str(row.get("task_id") or "")
        }
        observed_ids: list[str] = []
        for previous_unit in existing_state.get("units", []):
            if not isinstance(previous_unit, Mapping):
                resume_errors.append("screening_resume_unit_invalid")
                continue
            task_id = str(previous_unit.get("task_id") or "")
            observed_ids.append(task_id)
            task = task_by_id.get(task_id)
            if not isinstance(task, Mapping):
                resume_errors.append("screening_resume_task_binding_unresolved")
                continue
            source_hash = str(task.get("source_id_sha256") or "")
            source = next(
                (
                    row
                    for private_id, row in raw_sources.items()
                    if sha256_text(private_id) == source_hash
                ),
                None,
            )
            cases = selected_cases.get(source_hash, [])
            if not isinstance(source, Mapping) or not cases:
                resume_errors.append("screening_resume_source_binding_unresolved")
                continue
            resume_errors.extend(
                _verify_screening_unit_private_artifact(
                    task=task,
                    unit=previous_unit,
                    source=source,
                    cases=cases,
                    private_root=output_root,
                )
            )
        if len(observed_ids) != len(set(observed_ids)):
            resume_errors.append("screening_resume_unit_id_duplicate")
    if resume_errors:
        return _finalize_campaign_state(
            base_state,
            units=[],
            status="blocked",
            blockers=sorted(set(resume_errors)),
            elapsed_ms=(time.monotonic() - started) * 1000,
            # Never destroy a checkpoint that failed authentication.  The
            # caller can repair credentials or investigate the binding and
            # retry against the original bytes.
            state_path=None
            if live and selected_state_path is not None and existing_state
            else selected_state_path,
        )
    existing_units = {
        str(row.get("task_id") or ""): dict(row)
        for row in existing_state.get("units", [])
        if isinstance(row, Mapping) and str(row.get("task_id") or "")
    } if isinstance(existing_state, Mapping) else {}
    # Baseline calls are production-admission evidence: requesting
    # ``stream=true`` is insufficient unless the transport also observes
    # framed streaming data from the provider.
    active_client = ensure_strict_streaming_client(client)
    units: list[dict[str, Any]] = []
    new_task_count = 0
    for task in task_rows:
        task_id = str(task.get("task_id") or "")
        previous = existing_units.get(task_id)
        if (
            previous
            and previous.get("status") == "completed"
            and not overwrite
        ):
            units.append(previous)
            _persist_campaign_progress(selected_state_path, base_state, units, started)
            continue
        if (
            previous
            and previous.get("status") in {"failed", "blocked"}
            and not retry_failed
            and not overwrite
        ):
            units.append(previous)
            _persist_campaign_progress(selected_state_path, base_state, units, started)
            continue
        if max_tasks is not None and new_task_count >= max(0, int(max_tasks)):
            continue
        source_hash = str(task.get("source_id_sha256") or "")
        canonical_hash = str(task.get("canonical_identity_sha256") or "")
        source = next(
            (
                row
                for private_id, row in raw_sources.items()
                if sha256_text(private_id) == source_hash
            ),
            None,
        )
        source_receipt = source_receipts.get(source_hash)
        group = groups.get(canonical_hash)
        if not isinstance(source, Mapping) or not isinstance(source_receipt, Mapping) or not isinstance(group, Mapping):
            unit = _blocked_unit(task, "screening_task_binding_unresolved")
        else:
            replica_hashes = [
                str(value)
                for value in task.get("replica_profile_id_sha256s", [])
                if str(value)
            ]
            replicas = [
                profile_by_hash[value]
                for value in replica_hashes
                if value in profile_by_hash
            ]
            if len(replicas) != len(replica_hashes):
                unit = _blocked_unit(task, "screening_task_replica_set_unresolved")
            else:
                unit = _run_screening_unit(
                    task=task,
                    private_source_id=str(source.get("source_id") or ""),
                    source=source,
                    source_receipt=source_receipt,
                    cases=selected_cases.get(source_hash, []),
                    replicas=replicas,
                    private_root=output_root,
                    client=active_client,
                    max_workers=max_workers,
                    previous_unit=previous,
                )
        units.append(unit)
        new_task_count += 1
        _persist_campaign_progress(selected_state_path, base_state, units, started)

    all_planned_selected = len(task_rows) == int(plan.get("task_count") or 0)
    completed = sum(1 for row in units if row.get("status") == "completed")
    unit_blockers = sorted(
        {
            str(reason)
            for row in units
            for reason in row.get("reason_codes", [])
            if str(reason)
        }
    )
    if completed == len(task_rows) and all_planned_selected:
        status = "completed"
        final_blockers: list[str] = []
    elif any(row.get("status") in {"failed", "blocked"} for row in units):
        status = "partial"
        final_blockers = unit_blockers or ["screening_campaign_units_incomplete"]
    else:
        status = "partial"
        final_blockers = ["screening_campaign_task_chunk_incomplete"]
    return _finalize_campaign_state(
        base_state,
        units=units,
        status=status,
        blockers=final_blockers,
        elapsed_ms=(time.monotonic() - started) * 1000,
        state_path=selected_state_path,
    )


def build_external_ranking_manifest_from_screening(
    *,
    plan_path: str | Path,
    campaign_state_path: str | Path,
    registry_path: str | Path,
    source_manifest_path: str | Path,
    private_probe_files: Sequence[str | Path],
    private_root: str | Path,
    operational_admission_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convert a complete screening campaign into the strict ranking v3 input."""

    blockers: list[str] = []
    plan, _ = _load_private_json(
        Path(plan_path),
        reason_prefix="screening_ranking_plan",
        blockers=blockers,
    )
    state, state_sha256 = _load_private_json(
        Path(campaign_state_path),
        reason_prefix="screening_ranking_state",
        blockers=blockers,
    )
    source_manifest, source_manifest_sha256 = _load_private_json(
        Path(source_manifest_path),
        reason_prefix="screening_ranking_source_manifest",
        blockers=blockers,
    )
    profiles = _load_registry_for_screening(Path(registry_path), blockers)
    profiles, operational_admission = _apply_operational_admission_filter(
        profiles,
        operational_admission_path=operational_admission_path,
        blockers=blockers,
    )
    template = build_external_provider_ranking_template(
        registry_path=registry_path,
        profiles=profiles,
    )
    if plan.get("schema") != SCREENING_PLAN_SCHEMA or plan.get("ready") is not True:
        blockers.append("screening_ranking_plan_not_ready")
    blockers.extend(_screening_execution_schedule_errors(plan))
    if state.get("schema") != SCREENING_CAMPAIGN_SCHEMA:
        blockers.append("screening_ranking_campaign_schema_invalid")
    if state.get("status") != "completed" or state.get("ready_for_ranking") is not True:
        blockers.append("screening_ranking_campaign_not_complete")
    if str(state.get("plan_digest_sha256") or "") != str(
        plan.get("plan_digest_sha256") or ""
    ):
        blockers.append("screening_ranking_plan_binding_mismatch")
    schedule = (
        plan.get("execution_schedule")
        if isinstance(plan.get("execution_schedule"), Mapping)
        else {}
    )
    if str(state.get("execution_schedule_digest_sha256") or "") != str(
        schedule.get("schedule_digest_sha256") or ""
    ):
        blockers.append("screening_ranking_schedule_binding_mismatch")
    if str(state.get("execution_task_sequence_sha256") or "") != str(
        schedule.get("task_id_sequence_sha256") or ""
    ):
        blockers.append("screening_ranking_task_sequence_binding_mismatch")
    if str(state.get("registry_file_sha256") or "") != _file_sha256(
        Path(registry_path)
    ):
        blockers.append("screening_ranking_registry_binding_mismatch")
    if str(state.get("source_manifest_content_sha256") or "") != source_manifest_sha256:
        blockers.append("screening_ranking_source_binding_mismatch")
    if stable_json(state.get("operational_admission")) != stable_json(
        plan.get("operational_admission")
    ):
        blockers.append("screening_ranking_operational_admission_binding_mismatch")
    declared_plan_digest = str(plan.get("plan_digest_sha256") or "")
    computed_plan_digest = sha256_text(
        stable_json(_screening_plan_digest_input(plan))
    )
    if declared_plan_digest != computed_plan_digest:
        blockers.append("screening_ranking_plan_digest_mismatch")
    current_plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=source_manifest_path,
        private_probe_files=private_probe_files,
        min_cases_per_source=int(
            plan.get("minimum_cases_per_source") or DEFAULT_MIN_CASES_PER_SOURCE
        ),
        operational_admission_path=operational_admission_path,
    )
    if current_plan.get("ready") is not True:
        blockers.extend(
            f"screening_ranking_current_{reason}"
            for reason in current_plan.get("blockers", [])
        )
    if current_plan.get("plan_digest_sha256") != declared_plan_digest:
        blockers.append("screening_ranking_current_inputs_mismatch")
    declared_campaign_digest = str(state.get("campaign_digest_sha256") or "")
    computed_campaign_digest = sha256_text(
        stable_json(
            {
                key: value
                for key, value in state.items()
                if key not in {"campaign_digest_sha256", "elapsed_ms"}
            }
        )
    )
    if declared_campaign_digest != computed_campaign_digest:
        blockers.append("screening_ranking_campaign_digest_mismatch")
    blockers.extend(
        _verify_completed_screening_campaign(
            plan=plan,
            state=state,
            source_manifest=source_manifest,
            private_root=Path(private_root),
        )
    )

    pre_registration = (
        source_manifest.get("pre_registration")
        if isinstance(source_manifest.get("pre_registration"), Mapping)
        else {}
    )
    registered_on = str(pre_registration.get("registered_on") or "")
    identity = build_provider_identity_attestation_receipt(
        profiles=profiles,
        private_probe_files=private_probe_files,
        attested_on=registered_on,
    )
    if identity.get("ready") is not True:
        blockers.extend(str(reason) for reason in identity.get("blockers", []))
    identity_by_profile = {
        str(row.get("profile_id_sha256") or ""): dict(row)
        for row in identity.get("bindings", [])
        if isinstance(row, Mapping) and str(row.get("profile_id_sha256") or "")
    }

    source_rows = [
        dict(row)
        for row in source_manifest.get("sources", [])
        if isinstance(row, Mapping)
    ] if isinstance(source_manifest.get("sources"), list) else []
    source_receipt_by_id = {
        str(row.get("source_id_sha256") or ""): row
        for row in plan.get("sources", [])
        if isinstance(row, Mapping)
    } if isinstance(plan.get("sources"), list) else {}
    units = [
        dict(row)
        for row in state.get("units", [])
        if isinstance(row, Mapping)
    ] if isinstance(state.get("units"), list) else []
    units_by_source: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        units_by_source.setdefault(
            str(unit.get("source_id_sha256") or ""), []
        ).append(unit)

    candidate_count = int(plan.get("canonical_model_group_count") or 0)
    source_rank_by_candidate: dict[str, list[dict[str, Any]]] = {}
    source_evidence_by_id: dict[str, dict[str, Any]] = {}
    official_evidence: list[dict[str, Any]] = []
    for source in source_rows:
        source_id = str(source.get("source_id") or "")
        source_hash = sha256_text(source_id)
        source_receipt = source_receipt_by_id.get(source_hash, {})
        source_units = units_by_source.get(source_hash, [])
        if len(source_units) != candidate_count:
            blockers.append("screening_ranking_source_candidate_count_incomplete")
            continue
        if any(unit.get("status") != "completed" for unit in source_units):
            blockers.append("screening_ranking_source_has_incomplete_unit")
            continue
        ordered = sorted(
            source_units,
            key=lambda unit: (
                -float(unit.get("mean_score") or 0.0),
                -float(unit.get("confidence_interval_95_lower") or 0.0),
                str(unit.get("candidate_id_sha256") or ""),
            ),
        )
        evidence_base = {
            "source_type": "independent_evaluation_report",
            "source_family": str(source.get("source_family") or ""),
            "source_locator": str(source.get("source_locator") or ""),
            "source_snapshot_sha256": str(
                source_receipt.get("source_snapshot_sha256") or ""
            ),
            "retrieved_on": str(source.get("retrieved_on") or registered_on),
            "ranking_population_count": candidate_count,
            "supports_general_capability_ranking": True,
            "uses_target_benchmark_results": False,
        }
        if not evidence_base["source_family"] or not evidence_base["source_locator"]:
            blockers.append("screening_ranking_source_evidence_incomplete")
        source_evidence_by_id[source_hash] = evidence_base
        for rank, unit in enumerate(ordered, start=1):
            candidate_hash = str(unit.get("candidate_id_sha256") or "")
            source_rank_by_candidate.setdefault(candidate_hash, []).append(
                {**evidence_base, "reported_rank": rank}
            )
        official = source.get("official_evidence")
        if not isinstance(official, Mapping):
            blockers.append("screening_ranking_official_evidence_missing")
        else:
            official_row = {
                "source_type": str(official.get("source_type") or "official_release"),
                "source_family": str(official.get("source_family") or ""),
                "source_locator": str(official.get("source_locator") or ""),
                "source_snapshot_sha256": str(
                    official.get("source_snapshot_sha256")
                    or source_receipt.get("source_snapshot_sha256")
                    or ""
                ),
                "retrieved_on": str(official.get("retrieved_on") or registered_on),
                "supports_general_capability_ranking": (
                    official.get("supports_general_capability_ranking") is True
                ),
                "uses_target_benchmark_results": False,
                "evidence_role": str(
                    official.get("evidence_role")
                    or "benchmark_method_and_release_provenance_only"
                ),
                "does_not_attest_model_identity": (
                    official.get("does_not_attest_model_identity") is True
                ),
            }
            if (
                not official_row["source_family"]
                or not official_row["source_locator"]
                or not _looks_like_sha256(official_row["source_snapshot_sha256"])
                or official_row["supports_general_capability_ranking"] is not True
                or official_row["evidence_role"]
                != "benchmark_method_and_release_provenance_only"
                or official_row["does_not_attest_model_identity"] is not True
            ):
                blockers.append("screening_ranking_official_evidence_invalid")
            official_evidence.append(official_row)

    candidate_inventory = [
        dict(row)
        for row in template.get("candidate_inventory", [])
        if isinstance(row, Mapping)
    ]
    if len(candidate_inventory) != candidate_count:
        blockers.append("screening_ranking_template_candidate_count_mismatch")
    overall_rows: list[dict[str, Any]] = []
    for row in candidate_inventory:
        candidate_hash = str(row.get("candidate_id_sha256") or "")
        evidence_rows = source_rank_by_candidate.get(candidate_hash, [])
        if len(evidence_rows) != len(source_rows):
            blockers.append("screening_ranking_candidate_source_coverage_incomplete")
            continue
        normalized = [
            (int(evidence["reported_rank"]) - 1) / max(1, candidate_count - 1)
            for evidence in evidence_rows
        ]
        overall_rows.append(
            {
                "candidate_hash": candidate_hash,
                "mean_normalized_rank_percentile": sum(normalized) / len(normalized),
                "row": row,
                "evidence": evidence_rows,
            }
        )
    overall_rows.sort(
        key=lambda item: (
            float(item["mean_normalized_rank_percentile"]),
            str(item["candidate_hash"]),
        )
    )
    overall_rank_by_candidate = {
        str(item["candidate_hash"]): rank
        for rank, item in enumerate(overall_rows, start=1)
    }

    for row in candidate_inventory:
        candidate_hash = str(row.get("candidate_id_sha256") or "")
        profile_hashes = [
            str(value)
            for value in row.get("replica_profile_id_sha256s", [])
            if str(value)
        ]
        bindings = [identity_by_profile.get(value) for value in profile_hashes]
        if any(not isinstance(binding, Mapping) for binding in bindings):
            blockers.append("screening_ranking_replica_identity_binding_missing")
        else:
            row["replica_identity_attestations"] = [dict(binding) for binding in bindings]
            representative_hash = str(row.get("profile_id_sha256") or "")
            row["identity_attestation"] = dict(
                identity_by_profile.get(representative_hash, {})
            )
        row["screening_rank"] = overall_rank_by_candidate.get(candidate_hash)
        row["screening_evidence"] = source_rank_by_candidate.get(candidate_hash, [])

    if blockers:
        template.update(
            {
                "template_only": True,
                "operator_action_required": True,
                "ranking_assignment_present": False,
                "screening_campaign_state_sha256": state_sha256,
                "screening_conversion_ready": False,
                "blockers": sorted(set([*template.get("blockers", []), *blockers])),
            }
        )
        return template

    rankings: list[dict[str, Any]] = []
    for rank in EXTERNAL_PROVIDER_RANKING_REQUIRED_RANKS:
        selected = overall_rows[rank - 1]
        row = selected["row"]
        evidence = _dedupe_evidence(
            [*selected["evidence"], *official_evidence]
        )
        rankings.append(
            {
                "rank": rank,
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "canonical_model_id_sha256": str(
                    row.get("canonical_model_id_sha256") or ""
                ),
                "evidence": evidence,
            }
        )
    template.update(
        {
            "template_only": False,
            "operator_action_required": False,
            "ranking_assignment_present": True,
            "ranking_method": {
                "aggregation": EXTERNAL_PROVIDER_RANKING_AGGREGATION,
                "minimum_independent_sources_per_candidate": (
                    EXTERNAL_PROVIDER_RANKING_MIN_INDEPENDENT_SOURCES
                ),
                "minimum_common_independent_source_families": (
                    EXTERNAL_PROVIDER_RANKING_MIN_INDEPENDENT_SOURCES
                ),
                "candidate_pool_screening_complete": True,
                "selected_rows_must_equal_derived_pool_top_three": True,
            },
            "pre_registration": {
                "declared_before_campaign": True,
                "registered_on": registered_on,
                "target_benchmark_results_used": False,
                "target_suite_results_used": False,
            },
            "tie_break_policy": list(DEFAULT_TIE_BREAK_POLICY),
            "candidate_inventory": candidate_inventory,
            "rankings": rankings,
            "screening_campaign_state_sha256": state_sha256,
            "screening_conversion_ready": True,
            "blockers": [],
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        }
    )
    return template


def _run_screening_unit(
    *,
    task: Mapping[str, Any],
    private_source_id: str,
    source: Mapping[str, Any],
    source_receipt: Mapping[str, Any],
    cases: Sequence[ScreeningCase],
    replicas: Sequence[ModelProfile],
    private_root: Path,
    client: HTTPProviderClient,
    max_workers: int,
    previous_unit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    decoding = _safe_decoding_receipt(source.get("decoding"))
    protocol = (
        source.get("prompt_protocol")
        if isinstance(source.get("prompt_protocol"), Mapping)
        else {}
    )
    system_prompt = (
        str(protocol.get("system_prompt") or "")
        if "system_prompt" in protocol
        else (
            "You are being evaluated under a fixed, non-target capability "
            "protocol. Follow the user instruction exactly."
        )
    )
    unit_path = _screening_unit_path(private_root, task)
    preserved_results, resume_error = _private_resume_case_results(
        unit_path=unit_path,
        previous_unit=previous_unit,
        task=task,
        source=source,
        cases=cases,
    )
    if resume_error:
        return _blocked_unit(task, resume_error)

    pending_cases = [
        case for case in cases if case.case_id not in preserved_results
    ]
    workers = max(1, min(int(max_workers), len(pending_cases) or 1))
    case_results: list[dict[str, Any]] = list(preserved_results.values())
    # Keep an independent private checkpoint while a unit is in flight.  The
    # public/safe unit is written only after the complete frozen case set has
    # been answered, but an interrupted process must not discard answers that
    # were already returned by remote providers.  The checkpoint is never
    # referenced by a safe artifact and is validated against the task/source
    # binding again on resume.
    _persist_screening_private_checkpoint(
        _screening_checkpoint_path(private_root, task),
        task=task,
        private_source_id=private_source_id,
        case_results=case_results,
        expected_case_count=len(cases),
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_screening_case,
                case=case,
                source=source,
                replicas=replicas,
                client=client,
                decoding=decoding,
                system_prompt=system_prompt,
            ): case.case_id
            for case in pending_cases
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:  # noqa: BLE001
                result = {
                    "case_id": futures[future],
                    "status": "internal_error",
                    "score": None,
                    "output": "",
                    "output_sha256": sha256_text(""),
                    "latency_ms": 0.0,
                    "attempts": [],
                    "selected_replica_profile_id_sha256": "",
                    "error_type": "InternalScreeningError",
                }
            case_results.append(result)
            _persist_screening_private_checkpoint(
                _screening_checkpoint_path(private_root, task),
                task=task,
                private_source_id=private_source_id,
                case_results=case_results,
                expected_case_count=len(cases),
            )
    case_results.sort(key=lambda row: sha256_text(str(row.get("case_id") or "")))
    scoring_errors = sum(
        1
        for row in case_results
        if row.get("status") in {"scorer_error", "internal_error"}
        or (row.get("status") == "completed" and row.get("score") is None)
    )
    transport_failures = sum(
        1 for row in case_results if row.get("status") == "transport_failed"
    )
    scores = [
        float(row["score"])
        for row in case_results
        if row.get("status") == "completed" and row.get("score") is not None
    ]
    expected_count = len(cases)
    transport_failure_rate = (
        transport_failures / expected_count if expected_count else 1.0
    )
    max_failure_rate = _bounded_failure_rate(
        source_receipt.get("max_transport_failure_rate")
    )
    reason_codes: list[str] = []
    if expected_count != int(source_receipt.get("selected_case_count") or 0):
        reason_codes.append("screening_unit_case_count_mismatch")
    if scoring_errors:
        reason_codes.append("screening_unit_scorer_error")
    if transport_failure_rate > max_failure_rate:
        reason_codes.append("screening_unit_transport_failure_rate_exceeded")
    if not scores:
        reason_codes.append("screening_unit_no_scores")
    mean_score = sum(scores) / len(scores) if scores else 0.0
    lower, upper, confidence_method = _mean_confidence_interval(scores)
    latencies = [
        float(row.get("latency_ms") or 0.0)
        for row in case_results
        if float(row.get("latency_ms") or 0.0) > 0
    ]
    private_payload = {
        "schema": SCREENING_UNIT_PRIVATE_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "source_id": private_source_id,
        "canonical_identity_sha256": str(
            task.get("canonical_identity_sha256") or ""
        ),
        "candidate_id_sha256": str(task.get("candidate_id_sha256") or ""),
        "case_results": case_results,
        "raw_provider_outputs_persisted": True,
        "private_artifact": True,
        "secrets_persisted": False,
    }
    _atomic_write_json(unit_path, private_payload)
    checkpoint_path = _screening_checkpoint_path(private_root, task)
    try:
        checkpoint_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # The final unit remains valid even if cleanup is delayed.  A later
        # resume will validate and ignore a stale checkpoint whose case set is
        # already complete.
        pass
    private_sha256 = _file_sha256(unit_path)
    safe_cases = [
        {
            "case_id_sha256": sha256_text(str(row.get("case_id") or "")),
            "status": str(row.get("status") or ""),
            "score": (
                round(float(row["score"]), 12)
                if row.get("score") is not None
                else None
            ),
            "latency_ms": round(float(row.get("latency_ms") or 0.0), 3),
            "attempt_count": len(row.get("attempts", [])),
            "selected_replica_profile_id_sha256": str(
                row.get("selected_replica_profile_id_sha256") or ""
            ),
            "output_sha256": str(row.get("output_sha256") or ""),
            "raw_prompt_persisted": False,
            "raw_label_persisted": False,
            "raw_provider_output_persisted": False,
        }
        for row in case_results
    ]
    return {
        "schema": SCREENING_UNIT_SAFE_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "source_id_sha256": str(task.get("source_id_sha256") or ""),
        "source_snapshot_sha256": str(
            task.get("source_snapshot_sha256") or ""
        ),
        "case_set_digest_sha256": str(task.get("case_set_digest_sha256") or ""),
        "canonical_identity_sha256": str(
            task.get("canonical_identity_sha256") or ""
        ),
        "candidate_id_sha256": str(task.get("candidate_id_sha256") or ""),
        "representative_profile_id_sha256": str(
            task.get("representative_profile_id_sha256") or ""
        ),
        "replica_profile_id_sha256s": list(
            task.get("replica_profile_id_sha256s") or []
        ),
        "expected_case_count": expected_count,
        "scored_case_count": len(scores),
        "transport_failure_count": transport_failures,
        "transport_failure_rate": round(transport_failure_rate, 12),
        "max_transport_failure_rate": max_failure_rate,
        "scorer_error_count": scoring_errors,
        "mean_score": round(mean_score, 12),
        "confidence_interval_95_lower": round(lower, 12),
        "confidence_interval_95_upper": round(upper, 12),
        "confidence_interval_95_method": confidence_method,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "case_results": safe_cases,
        "private_unit_content_sha256": private_sha256,
        "status": "completed" if not reason_codes else "failed",
        "reason_codes": sorted(set(reason_codes)),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "raw_private_unit_path_persisted": False,
        "raw_source_id_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _run_screening_case(
    *,
    case: ScreeningCase,
    source: Mapping[str, Any],
    replicas: Sequence[ModelProfile],
    client: HTTPProviderClient,
    decoding: Mapping[str, Any],
    system_prompt: str,
) -> dict[str, Any]:
    started = time.monotonic()
    effective_timeout_seconds = _safe_decoding_receipt(decoding)["timeout_seconds"]
    ordered = _rotated_replicas(replicas, case.case_id)
    rounds = max(1, int(decoding.get("max_exception_attempt_rounds") or 1))
    attempts: list[dict[str, Any]] = []
    output = ""
    selected_hash = ""
    error_type = ""
    for round_index in range(rounds):
        for profile in ordered:
            profile_hash = sha256_text(profile.profile_id)
            attempt_started = time.monotonic()
            request = FusionRequest(
                model="axio-fast",
                prompt=case.prompt,
                system=system_prompt,
                api_format=profile.api_format,
                task_type="non_target_provider_baseline_screening",
                temperature=_optional_float(decoding.get("temperature")),
                top_p=_optional_float(decoding.get("top_p")),
                max_output_tokens=int(decoding.get("max_output_tokens") or 1024),
                metadata={
                    "_axio_non_target_screening": True,
                    "_axio_target_suite_material_used": False,
                },
            )
            try:
                output = str(
                    client.complete(
                        profile,
                        request,
                        prompt=case.prompt,
                        system=system_prompt,
                        timeout=effective_timeout_seconds,
                    )
                    or ""
                )
                if not output.strip():
                    raise RuntimeError("empty screening output")
                selected_hash = profile_hash
                attempts.append(
                    {
                        "profile_id_sha256": profile_hash,
                        "round": round_index + 1,
                        "status": "completed",
                        "latency_ms": round(
                            (time.monotonic() - attempt_started) * 1000,
                            3,
                        ),
                    }
                )
                break
            except Exception as exc:  # noqa: BLE001 - private error type only
                error_type = type(exc).__name__[:120]
                attempts.append(
                    {
                        "profile_id_sha256": profile_hash,
                        "round": round_index + 1,
                        "status": "failed",
                        "error_type": error_type,
                        "latency_ms": round(
                            (time.monotonic() - attempt_started) * 1000,
                            3,
                        ),
                    }
                )
        if output.strip():
            break
    latency_ms = (time.monotonic() - started) * 1000
    if not output.strip():
        return {
            "case_id": case.case_id,
            "status": "transport_failed",
            # A transport failure is missing data, not an incorrect answer.
            # The unit-level failure-rate gate still decides whether the
            # candidate is admissible for ranking.
            "score": None,
            "output": "",
            "output_sha256": sha256_text(""),
            "latency_ms": round(latency_ms, 3),
            "attempts": attempts,
            "selected_replica_profile_id_sha256": "",
            "error_type": error_type or "ProviderExecutionFailed",
        }
    try:
        score = _score_screening_output_silently(source, case, output)
    except Exception as exc:  # noqa: BLE001 - scorer failure is not model failure
        return {
            "case_id": case.case_id,
            "status": "scorer_error",
            "score": None,
            "output": output,
            "output_sha256": sha256_text(output),
            "latency_ms": round(latency_ms, 3),
            "attempts": attempts,
            "selected_replica_profile_id_sha256": selected_hash,
            "error_type": type(exc).__name__[:120],
        }
    return {
        "case_id": case.case_id,
        "status": "completed",
        "score": max(0.0, min(1.0, float(score))),
        "output": output,
        "output_sha256": sha256_text(output),
        "latency_ms": round(latency_ms, 3),
        "attempts": attempts,
        "selected_replica_profile_id_sha256": selected_hash,
        "error_type": "",
    }


_SCREENING_SCORER_LOCK = threading.Lock()


def _verify_completed_screening_campaign(
    *,
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    private_root: Path,
) -> list[str]:
    """Recompute every completed unit from its private raw-output artifact."""

    errors: list[str] = []
    if not private_root.is_dir():
        return ["screening_ranking_private_root_missing"]
    raw_sources = {
        sha256_text(str(source.get("source_id") or "")): source
        for source in source_manifest.get("sources", [])
        if isinstance(source, Mapping) and str(source.get("source_id") or "")
    } if isinstance(source_manifest.get("sources"), list) else {}
    selection_seed = str(
        (source_manifest.get("pre_registration") or {}).get("selection_seed")
        if isinstance(source_manifest.get("pre_registration"), Mapping)
        else ""
    )
    expected_cases_by_source: dict[str, list[ScreeningCase]] = {}
    for source_hash, source in raw_sources.items():
        try:
            expected_cases_by_source[source_hash] = _select_screening_cases(
                _load_source_cases(source),
                source.get("selection"),
                selection_seed=selection_seed,
                source_id=str(source.get("source_id") or ""),
            )
        except Exception:  # noqa: BLE001 - never expose private scorer details
            errors.append("screening_ranking_private_source_load_failed")

    task_by_id = {
        str(task.get("task_id") or ""): task
        for task in plan.get("tasks", [])
        if isinstance(task, Mapping) and str(task.get("task_id") or "")
    } if isinstance(plan.get("tasks"), list) else {}
    state_units = [
        unit
        for unit in state.get("units", [])
        if isinstance(unit, Mapping)
    ] if isinstance(state.get("units"), list) else []
    unit_by_id = {
        str(unit.get("task_id") or ""): unit
        for unit in state_units
        if str(unit.get("task_id") or "")
    }
    if len(unit_by_id) != len(state_units):
        errors.append("screening_ranking_campaign_unit_id_duplicate")
    if set(unit_by_id) != set(task_by_id):
        errors.append("screening_ranking_campaign_task_set_mismatch")

    for task_id, task in task_by_id.items():
        unit = unit_by_id.get(task_id)
        if not isinstance(unit, Mapping) or unit.get("status") != "completed":
            errors.append("screening_ranking_campaign_unit_not_completed")
            continue
        source_hash = str(task.get("source_id_sha256") or "")
        source = raw_sources.get(source_hash)
        cases = expected_cases_by_source.get(source_hash, [])
        if not isinstance(source, Mapping) or not cases:
            errors.append("screening_ranking_campaign_unit_source_unresolved")
            continue
        errors.extend(
            _verify_screening_unit_private_artifact(
                task=task,
                unit=unit,
                source=source,
                cases=cases,
                private_root=private_root,
            )
        )
    return sorted(set(errors))


def _verify_screening_unit_private_artifact(
    *,
    task: Mapping[str, Any],
    unit: Mapping[str, Any],
    source: Mapping[str, Any],
    cases: Sequence[ScreeningCase],
    private_root: Path,
) -> list[str]:
    errors: list[str] = []
    unit_path = _screening_unit_path(private_root, task)
    expected_content_sha256 = str(
        unit.get("private_unit_content_sha256") or ""
    )
    if not unit_path.is_file():
        return ["screening_ranking_private_unit_missing"]
    if not expected_content_sha256 or _file_sha256(unit_path) != expected_content_sha256:
        return ["screening_ranking_private_unit_digest_mismatch"]
    try:
        payload = json.loads(unit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["screening_ranking_private_unit_invalid"]
    if not isinstance(payload, Mapping):
        return ["screening_ranking_private_unit_invalid"]
    if payload.get("schema") != SCREENING_UNIT_PRIVATE_SCHEMA:
        errors.append("screening_ranking_private_unit_schema_invalid")
    for key in (
        "task_id",
        "canonical_identity_sha256",
        "candidate_id_sha256",
    ):
        if str(payload.get(key) or "") != str(task.get(key) or ""):
            errors.append("screening_ranking_private_unit_binding_mismatch")
    if str(payload.get("source_id") or "") != str(source.get("source_id") or ""):
        errors.append("screening_ranking_private_unit_source_mismatch")

    raw_results = (
        payload.get("case_results")
        if isinstance(payload.get("case_results"), list)
        else []
    )
    result_by_case = {
        str(row.get("case_id") or ""): row
        for row in raw_results
        if isinstance(row, Mapping) and str(row.get("case_id") or "")
    }
    if len(result_by_case) != len(raw_results):
        errors.append("screening_ranking_private_case_id_duplicate")
    expected_by_case = {case.case_id: case for case in cases}
    if set(result_by_case) != set(expected_by_case):
        errors.append("screening_ranking_private_case_set_mismatch")

    scores: list[float] = []
    latencies: list[float] = []
    transport_failures = 0
    scorer_errors = 0
    safe_case_by_hash = {
        str(row.get("case_id_sha256") or ""): row
        for row in unit.get("case_results", [])
        if isinstance(row, Mapping) and str(row.get("case_id_sha256") or "")
    } if isinstance(unit.get("case_results"), list) else {}
    # `_run_screening_unit` persists case results in this order before its
    # bootstrap confidence interval is computed. Keep verification aligned so
    # a resumed partial-credit source has the identical deterministic seed.
    for case_id in sorted(expected_by_case, key=sha256_text):
        case = expected_by_case[case_id]
        row = result_by_case.get(case_id)
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or "")
        output = str(row.get("output") or "")
        if str(row.get("output_sha256") or "") != sha256_text(output):
            errors.append("screening_ranking_private_output_digest_mismatch")
        declared_score = _optional_float(row.get("score"))
        if status == "completed":
            try:
                recomputed = _score_screening_output_silently(
                    source,
                    case,
                    output,
                )
            except Exception:  # noqa: BLE001
                errors.append("screening_ranking_private_rescore_failed")
                continue
            recomputed = max(0.0, min(1.0, float(recomputed)))
            if declared_score is None or not math.isclose(
                declared_score,
                recomputed,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                errors.append("screening_ranking_private_score_mismatch")
            scores.append(recomputed)
        elif status == "transport_failed":
            transport_failures += 1
            # Missing transport observations must not enter the accuracy
            # denominator. The pre-registered failure-rate gate remains the
            # authoritative admission rule for the unit.
        else:
            scorer_errors += 1
        latency = max(0.0, _optional_float(row.get("latency_ms")) or 0.0)
        if latency > 0:
            latencies.append(latency)
        safe_row = safe_case_by_hash.get(sha256_text(case_id))
        if not isinstance(safe_row, Mapping):
            errors.append("screening_ranking_safe_case_binding_missing")
            continue
        if str(safe_row.get("output_sha256") or "") != sha256_text(output):
            errors.append("screening_ranking_safe_output_digest_mismatch")
        safe_score = _optional_float(safe_row.get("score"))
        if (safe_score is None) != (declared_score is None) or (
            safe_score is not None
            and declared_score is not None
            and not math.isclose(
                safe_score,
                declared_score,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            errors.append("screening_ranking_safe_case_score_mismatch")

    expected_count = len(cases)
    mean_score = sum(scores) / len(scores) if scores else 0.0
    lower, upper, method = _mean_confidence_interval(scores)
    expected_failure_rate = (
        transport_failures / expected_count if expected_count else 1.0
    )
    aggregate_checks = (
        ("expected_case_count", expected_count, 0.0),
        ("scored_case_count", len(scores), 0.0),
        ("transport_failure_count", transport_failures, 0.0),
        ("transport_failure_rate", expected_failure_rate, 1e-12),
        ("scorer_error_count", scorer_errors, 0.0),
        ("mean_score", mean_score, 1e-12),
        ("confidence_interval_95_lower", lower, 1e-12),
        ("confidence_interval_95_upper", upper, 1e-12),
        ("p50_latency_ms", _percentile(latencies, 0.50), 1e-3),
        ("p95_latency_ms", _percentile(latencies, 0.95), 1e-3),
    )
    for key, expected, tolerance in aggregate_checks:
        observed = unit.get(key)
        if expected is None:
            if observed is not None:
                errors.append("screening_ranking_safe_unit_aggregate_mismatch")
            continue
        observed_number = _optional_float(observed)
        if observed_number is None or not math.isclose(
            observed_number,
            float(expected),
            rel_tol=0.0,
            abs_tol=tolerance,
        ):
            errors.append("screening_ranking_safe_unit_aggregate_mismatch")
    if str(unit.get("confidence_interval_95_method") or "") != method:
        errors.append("screening_ranking_safe_unit_confidence_method_mismatch")
    return sorted(set(errors))


def _score_screening_output_silently(
    source: Mapping[str, Any],
    case: ScreeningCase,
    output: str,
) -> float:
    """Suppress noisy third-party scorer diagnostics during verification."""

    with _SCREENING_SCORER_LOCK:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return _score_screening_output(source, case, output)


def _score_screening_output(
    source: Mapping[str, Any],
    case: ScreeningCase,
    output: str,
) -> float:
    adapter = str(source.get("adapter") or "")
    if adapter == "jsonl_multiple_choice":
        predicted = _extract_single_choice(output)
        return float(bool(predicted and predicted == str(case.reference).upper()))
    if adapter == "mmlu_pro":
        predicted = _extract_mmlu_choice(output)
        return float(bool(predicted and predicted == str(case.reference).upper()))
    if adapter == "livebench_official":
        return _score_livebench_output(source, case, output)
    raise ValueError("unsupported screening scorer")


def _extract_single_choice(value: str) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"(?:ANSWER\s*[:=]\s*)?\(?([A-J])\)?\s*$", text)
    if match:
        return match.group(1)
    matches = re.findall(r"\b([A-J])\b", text)
    return matches[-1] if matches else ""


def _extract_mmlu_choice(value: str) -> str:
    text = str(value or "")
    for pattern in _MMLU_ANSWER_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            return str(matches[-1]).upper()
    return ""


def _score_livebench_output(
    source: Mapping[str, Any],
    case: ScreeningCase,
    output: str,
) -> float:
    root = str(source.get("harness_root") or "")
    scorers = _livebench_scorers(root)
    task = str(case.metadata.get("task") or "")
    reference = case.reference
    release = str(case.metadata.get("livebench_release_date") or "")
    question = str(case.metadata.get("question_text") or case.prompt)
    if task == "zebra_puzzle":
        return float(scorers["zebra_factory"](release)(reference, output, False))
    if task == "spatial":
        return float(scorers["spatial"](reference, output, False))
    if task == "web_of_lies_v2":
        return float(scorers["web_of_lies"](reference, output, False))
    if task == "cta":
        return float(scorers["cta"](reference, output, False))
    if task == "tablereformat":
        version = "v2" if release >= "2025-04-25" else "v1"
        return float(scorers["table"](question, reference, output, version, False))
    if task == "tablejoin":
        return float(scorers["tablejoin"](question, reference, output, False))
    if task == "connections":
        return float(scorers["connections_factory"](release)(reference, output, False))
    if task == "typos":
        return float(scorers["typos"](reference, output, False))
    if task == "plot_unscrambling":
        return float(scorers["plot"](reference, output, False))
    raise ValueError("unsupported pinned LiveBench screening task")


_LIVEBENCH_SCORER_CACHE: dict[str, dict[str, Callable[..., Any]]] = {}


def _livebench_scorers(root: str) -> dict[str, Callable[..., Any]]:
    selected = str(Path(root).resolve())
    if selected in _LIVEBENCH_SCORER_CACHE:
        return _LIVEBENCH_SCORER_CACHE[selected]
    if not Path(selected, "livebench").is_dir():
        raise ValueError("LiveBench harness root invalid")
    if selected not in sys.path:
        sys.path.insert(0, selected)
    from livebench.process_results.data_analysis.cta.utils import (  # type: ignore[import-not-found]
        cta_process_results,
    )
    from livebench.process_results.data_analysis.tablejoin.utils import (  # type: ignore[import-not-found]
        joinmap_process_results,
    )
    from livebench.process_results.data_analysis.tablereformat.utils import (  # type: ignore[import-not-found]
        table_process_results,
    )
    from livebench.process_results.reasoning.spatial.utils import (  # type: ignore[import-not-found]
        spatial_process_results,
    )
    from livebench.process_results.reasoning.web_of_lies_v2.utils import (  # type: ignore[import-not-found]
        web_of_lies_process_results,
    )
    from livebench.process_results.reasoning.zebra_puzzle.utils import (  # type: ignore[import-not-found]
        get_zebra_puzzle_evaluator,
    )
    from livebench.process_results.writing.connections.utils import (  # type: ignore[import-not-found]
        get_connections_puzzle_evaluator,
    )
    from livebench.process_results.writing.plot_unscrambling.utils import (  # type: ignore[import-not-found]
        plot_unscrambling_process_results,
    )
    from livebench.process_results.writing.typos.utils import (  # type: ignore[import-not-found]
        typos_process_results,
    )

    scorers: dict[str, Callable[..., Any]] = {
        "cta": cta_process_results,
        "tablejoin": joinmap_process_results,
        "table": table_process_results,
        "spatial": spatial_process_results,
        "web_of_lies": web_of_lies_process_results,
        "zebra_factory": get_zebra_puzzle_evaluator,
        "connections_factory": get_connections_puzzle_evaluator,
        "plot": plot_unscrambling_process_results,
        "typos": typos_process_results,
    }
    _LIVEBENCH_SCORER_CACHE[selected] = scorers
    return scorers


def _rotated_replicas(
    replicas: Sequence[ModelProfile],
    case_id: str,
) -> list[ModelProfile]:
    ordered = sorted(replicas, key=lambda item: sha256_text(item.profile_id))
    if not ordered:
        return []
    offset = int(sha256_text(case_id)[:12], 16) % len(ordered)
    return [*ordered[offset:], *ordered[:offset]]


def _private_resume_case_results(
    *,
    unit_path: Path,
    previous_unit: Mapping[str, Any] | None,
    task: Mapping[str, Any],
    source: Mapping[str, Any],
    cases: Sequence[ScreeningCase],
) -> tuple[dict[str, dict[str, Any]], str]:
    """Reuse answered cases while retrying transport/scorer failures only.

    A completed-but-wrong answer is still an answered case and must never be
    sampled again.  This prevents a resumed campaign from gradually selecting
    lucky outputs.  Private raw results are content-bound to the prior safe
    unit before any row is reused.
    """

    previous_is_resumable = (
        isinstance(previous_unit, Mapping)
        and bool(previous_unit)
        and previous_unit.get("status") in {"failed", "blocked"}
    )
    checkpoint_path = _screening_checkpoint_path(unit_path.parent.parent, task)
    # A task may have no safe state row yet when the process is interrupted
    # during its first execution.  In that case a task-bound private
    # checkpoint is still safe to resume.  A completed safe unit must never be
    # replayed merely because its final artifact happens to exist.
    if not previous_is_resumable and not checkpoint_path.is_file():
        return {}, ""
    selected_path = checkpoint_path if checkpoint_path.is_file() else unit_path
    if not selected_path.is_file():
        return {}, "screening_resume_private_unit_missing"
    expected_sha256 = str(
        previous_unit.get("private_unit_content_sha256") or ""
    ) if isinstance(previous_unit, Mapping) else ""
    # The checkpoint is intentionally mutable as case results arrive, so it is
    # authenticated by its task/source binding below rather than by the stale
    # digest of the previous completed/failed safe unit.
    if selected_path == unit_path and (
        not expected_sha256 or _file_sha256(unit_path) != expected_sha256
    ):
        return {}, "screening_resume_private_unit_digest_mismatch"
    try:
        payload = json.loads(selected_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, "screening_resume_private_unit_invalid"
    if not isinstance(payload, Mapping):
        return {}, "screening_resume_private_unit_invalid"
    if payload.get("schema") != SCREENING_UNIT_PRIVATE_SCHEMA:
        return {}, "screening_resume_private_unit_schema_invalid"
    if str(payload.get("task_id") or "") != str(task.get("task_id") or ""):
        return {}, "screening_resume_private_unit_task_mismatch"
    if str(payload.get("source_id") or "") != str(source.get("source_id") or ""):
        return {}, "screening_resume_private_unit_source_mismatch"
    expected_candidate = str(task.get("candidate_id_sha256") or "")
    observed_candidate = str(payload.get("candidate_id_sha256") or "")
    if expected_candidate and observed_candidate != expected_candidate:
        return {}, "screening_resume_private_unit_candidate_mismatch"
    expected_case_ids = {case.case_id for case in cases}
    raw_results = (
        payload.get("case_results")
        if isinstance(payload.get("case_results"), list)
        else []
    )
    observed_case_ids = [
        str(row.get("case_id") or "")
        for row in raw_results
        if isinstance(row, Mapping)
    ]
    if len(observed_case_ids) != len(set(observed_case_ids)) or not set(
        observed_case_ids
    ).issubset(expected_case_ids):
        return {}, "screening_resume_private_unit_case_set_mismatch"
    preserved: dict[str, dict[str, Any]] = {}
    for raw_row in raw_results:
        if not isinstance(raw_row, Mapping):
            continue
        case_id = str(raw_row.get("case_id") or "")
        if not case_id or not str(raw_row.get("output") or "").strip():
            continue
        status = str(raw_row.get("status") or "")
        if status == "completed" and raw_row.get("score") is not None:
            preserved[case_id] = dict(raw_row)
            continue
        # A scorer can fail after the provider has already returned a valid
        # answer (for example, when an optional official scorer dependency was
        # absent).  Re-score that immutable private answer during resume rather
        # than issuing a second provider request.  Transport failures remain
        # pending and are retried by the normal replica policy below.
        if status != "scorer_error":
            continue
        case = next((item for item in cases if item.case_id == case_id), None)
        if case is None:
            continue
        try:
            score = _score_screening_output_silently(
                source,
                case,
                str(raw_row.get("output") or ""),
            )
        except Exception:  # noqa: BLE001 - leave it pending if the scorer is still unavailable
            continue
        repaired = dict(raw_row)
        repaired.update(
            {
                "status": "completed",
                "score": max(0.0, min(1.0, float(score))),
                "output_sha256": sha256_text(str(raw_row.get("output") or "")),
                "error_type": "",
            }
        )
        preserved[case_id] = repaired
    return preserved, ""


def _recover_private_checkpoint_state(
    state: Mapping[str, Any],
    *,
    base_state: Mapping[str, Any],
    task_rows: Sequence[Mapping[str, Any]],
    raw_sources: Mapping[str, Mapping[str, Any]],
    selected_cases: Mapping[str, Sequence[ScreeningCase]],
    source_receipts: Mapping[str, Mapping[str, Any]],
    private_root: Path,
) -> dict[str, Any]:
    """Rebuild safe unit indexes when a prior checkpoint was interrupted.

    Raw unit files are intentionally private, but they are still bound to the
    frozen task and source contract.  A process-local credential preflight can
    fail after a long campaign and an older runner may have written an empty
    blocked checkpoint.  Retryable failed or blocked units are also rebuilt
    here because scorer implementation repairs can legitimately change their
    safe aggregate without changing an already returned provider answer.

    Completed units are deliberately excluded from this repair path.  Their
    persisted aggregate and private digest remain a strict fail-closed
    contract.  No provider call is made here and no raw content is copied into
    the returned state.
    """

    if not isinstance(state, Mapping):
        return dict(state)
    existing_units = {
        str(row.get("task_id") or ""): dict(row)
        for row in state.get("units", [])
        if isinstance(row, Mapping) and str(row.get("task_id") or "")
    } if isinstance(state.get("units"), list) else {}
    source_by_hash = {
        sha256_text(str(source_id)): dict(source)
        for source_id, source in raw_sources.items()
        if isinstance(source, Mapping) and str(source_id)
    }
    recovered_task_ids: list[str] = []
    for task in task_rows:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        previous_unit = existing_units.get(task_id)
        if (
            previous_unit is not None
            and previous_unit.get("status") not in {"failed", "blocked"}
        ):
            # A completed result must authenticate against the exact safe
            # aggregate saved at completion time.  It is never silently
            # re-derived from mutable private state during resume.
            continue
        source_hash = str(task.get("source_id_sha256") or "")
        source = raw_sources.get(source_hash) or source_by_hash.get(source_hash)
        cases = selected_cases.get(source_hash, ())
        source_receipt = source_receipts.get(source_hash)
        if (
            not isinstance(source, Mapping)
            or not cases
            or not isinstance(source_receipt, Mapping)
        ):
            continue
        unit_path = _screening_unit_path(private_root, task)
        expected_private_sha256 = str(
            previous_unit.get("private_unit_content_sha256") or ""
        ) if isinstance(previous_unit, Mapping) else ""
        if expected_private_sha256 and (
            _file_sha256(unit_path) != expected_private_sha256
        ):
            # The normal resume verifier will report the mismatch and stop
            # rather than allowing a changed failed/blocked artifact to be
            # converted into fresh trusted state.
            continue
        unit = _rebuild_safe_unit_from_private_artifact(
            task=task,
            source=source,
            source_receipt=source_receipt,
            cases=cases,
            private_root=private_root,
        )
        if unit is None:
            continue
        if (
            isinstance(previous_unit, Mapping)
            and not _retryable_unit_output_bindings_match(previous_unit, unit)
        ):
            # A stale confidence interval is repairable; a changed answer is
            # not.  Leave the prior row untouched so strict resume validation
            # can fail closed with its original evidence.
            continue
        existing_units[task_id] = unit
        recovered_task_ids.append(task_id)
    if not recovered_task_ids:
        return dict(state)

    # Refresh process-local readiness and current execution bindings from the
    # invocation that is actually about to resume.  Older interrupted runs
    # may have persisted a blocked, credential-less base state; retaining its
    # digest would make an otherwise valid private checkpoint fail the normal
    # resume authentication gate.
    result = {**dict(state), **dict(base_state)}
    merged_units = list(existing_units.values())
    result["units"] = sorted(
        merged_units,
        key=lambda row: str(row.get("task_id") or ""),
    )
    result["status"] = "partial"
    result["completed_unit_count"] = sum(
        1 for row in merged_units if row.get("status") == "completed"
    )
    result["failed_or_blocked_unit_count"] = sum(
        1 for row in merged_units if row.get("status") in {"failed", "blocked"}
    )
    result["ready_for_ranking"] = False
    result["reason_codes"] = ["screening_private_checkpoint_recovered"]
    # The resumed state must authenticate the complete merged set on the next
    # invocation. Hashing only the newly recovered rows would make a prior
    # failed or blocked row look like checkpoint tampering on resume.
    result["unit_set_digest_sha256"] = _screening_unit_set_digest(merged_units)
    result["campaign_digest_sha256"] = sha256_text(
        stable_json(
            {
                key: value
                for key, value in result.items()
                if key not in {"campaign_digest_sha256", "elapsed_ms"}
            }
        )
    )
    return result


def _retryable_unit_output_bindings_match(
    previous_unit: Mapping[str, Any],
    rebuilt_unit: Mapping[str, Any],
) -> bool:
    """Keep retryable recovery bound to previously recorded answer hashes.

    Failed and blocked units may be rebuilt after a scorer repair, so their
    aggregate fields cannot be treated as immutable.  Their task identity and
    answer hashes still are.  An older interrupted checkpoint may not contain
    safe case rows at all; in that narrow case the fully validated private
    artifact is the only available recovery evidence.
    """

    for key in (
        "task_id",
        "source_id_sha256",
        "canonical_identity_sha256",
        "candidate_id_sha256",
    ):
        previous_value = str(previous_unit.get(key) or "")
        if previous_value and previous_value != str(rebuilt_unit.get(key) or ""):
            return False

    previous_cases = previous_unit.get("case_results")
    if not isinstance(previous_cases, list) or not previous_cases:
        return True
    rebuilt_cases = rebuilt_unit.get("case_results")
    if not isinstance(rebuilt_cases, list):
        return False

    def by_case_hash(rows: Sequence[Any]) -> dict[str, Mapping[str, Any]] | None:
        result: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                return None
            case_hash = str(row.get("case_id_sha256") or "")
            output_hash = str(row.get("output_sha256") or "")
            if not case_hash or not output_hash or case_hash in result:
                return None
            result[case_hash] = row
        return result

    previous_by_case = by_case_hash(previous_cases)
    rebuilt_by_case = by_case_hash(rebuilt_cases)
    if previous_by_case is None or rebuilt_by_case is None:
        return False
    if set(previous_by_case) != set(rebuilt_by_case):
        return False
    return all(
        str(previous_row.get("output_sha256") or "")
        == str(rebuilt_by_case[case_hash].get("output_sha256") or "")
        for case_hash, previous_row in previous_by_case.items()
    )


def _rebuild_safe_unit_from_private_artifact(
    *,
    task: Mapping[str, Any],
    source: Mapping[str, Any],
    source_receipt: Mapping[str, Any],
    cases: Sequence[ScreeningCase],
    private_root: Path,
) -> dict[str, Any] | None:
    """Validate and aggregate one existing private unit without new calls."""

    unit_path = _screening_unit_path(private_root, task)
    try:
        payload = json.loads(unit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("schema") != SCREENING_UNIT_PRIVATE_SCHEMA:
        return None
    if any(
        str(payload.get(key) or "") != str(task.get(key) or "")
        for key in ("task_id", "canonical_identity_sha256", "candidate_id_sha256")
    ):
        return None
    if str(payload.get("source_id") or "") != str(source.get("source_id") or ""):
        return None
    raw_rows = payload.get("case_results")
    if not isinstance(raw_rows, list):
        return None
    by_case: dict[str, dict[str, Any]] = {}
    mutable_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            return None
        case_id = str(row.get("case_id") or "")
        if not case_id or case_id in by_case:
            return None
        mutable = dict(row)
        by_case[case_id] = mutable
        mutable_rows.append(mutable)
    expected = {case.case_id: case for case in cases}
    if set(by_case) != set(expected):
        return None

    safe_cases: list[dict[str, Any]] = []
    scores: list[float] = []
    latencies: list[float] = []
    transport_failures = 0
    scorer_errors = 0
    private_payload_changed = False
    # Match the stable order used by `_run_screening_unit` when it finalized
    # the original safe aggregate. Partial-credit bootstrap intervals are
    # deterministic only when their input ordering is identical on recovery.
    for case_id in sorted(expected, key=sha256_text):
        case = expected[case_id]
        row = by_case[case_id]
        output = str(row.get("output") or "")
        if str(row.get("output_sha256") or "") != sha256_text(output):
            return None
        status = str(row.get("status") or "")
        score: float | None
        if status == "transport_failed":
            # A transport failure is missing data, not an incorrect answer.
            # Keep it out of both the accuracy denominator and the safe score
            # projection so recovery has the same semantics as first-pass
            # execution and final campaign verification.
            score = None
            transport_failures += 1
        elif output.strip():
            try:
                score = max(
                    0.0,
                    min(
                        1.0,
                        float(
                            _score_screening_output_silently(
                                source,
                                case,
                                output,
                            )
                        ),
                    ),
                )
            except Exception:  # noqa: BLE001 - preserve scorer failure for retry
                score = None
                scorer_errors += 1
            else:
                if status == "scorer_error":
                    row.update(
                        {
                            "status": "completed",
                            "score": score,
                            "error_type": "",
                        }
                    )
                    private_payload_changed = True
        else:
            score = None
            scorer_errors += 1
        latency = max(0.0, _optional_float(row.get("latency_ms")) or 0.0)
        if latency > 0:
            latencies.append(latency)
        if score is not None:
            scores.append(score)
        safe_cases.append(
            {
                "case_id_sha256": sha256_text(case_id),
                "status": status,
                "score": round(score, 12) if score is not None else None,
                "latency_ms": round(latency, 3),
                "attempt_count": len(row.get("attempts", []))
                if isinstance(row.get("attempts"), list)
                else 0,
                "selected_replica_profile_id_sha256": str(
                    row.get("selected_replica_profile_id_sha256") or ""
                ),
                "output_sha256": sha256_text(output),
                "raw_prompt_persisted": False,
                "raw_label_persisted": False,
                "raw_provider_output_persisted": False,
            }
        )

    expected_count = len(cases)
    failure_rate = transport_failures / expected_count if expected_count else 1.0
    max_failure_rate = _bounded_failure_rate(
        source_receipt.get("max_transport_failure_rate")
    )
    reasons: list[str] = []
    if scorer_errors:
        reasons.append("screening_unit_scorer_error")
    if failure_rate > max_failure_rate:
        reasons.append("screening_unit_transport_failure_rate_exceeded")
    if not scores:
        reasons.append("screening_unit_no_scores")
    lower, upper, confidence_method = _mean_confidence_interval(scores)
    if private_payload_changed:
        repaired_payload = dict(payload)
        repaired_payload["case_results"] = mutable_rows
        _atomic_write_json(unit_path, repaired_payload)

    return {
        "schema": SCREENING_UNIT_SAFE_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "source_id_sha256": str(task.get("source_id_sha256") or ""),
        "source_snapshot_sha256": str(task.get("source_snapshot_sha256") or ""),
        "case_set_digest_sha256": str(task.get("case_set_digest_sha256") or ""),
        "canonical_identity_sha256": str(task.get("canonical_identity_sha256") or ""),
        "candidate_id_sha256": str(task.get("candidate_id_sha256") or ""),
        "representative_profile_id_sha256": str(
            task.get("representative_profile_id_sha256") or ""
        ),
        "replica_profile_id_sha256s": list(task.get("replica_profile_id_sha256s") or []),
        "expected_case_count": expected_count,
        "scored_case_count": len(scores),
        "transport_failure_count": transport_failures,
        "transport_failure_rate": round(failure_rate, 12),
        "max_transport_failure_rate": max_failure_rate,
        "scorer_error_count": scorer_errors,
        "mean_score": round(sum(scores) / len(scores), 12) if scores else 0.0,
        "confidence_interval_95_lower": round(lower, 12),
        "confidence_interval_95_upper": round(upper, 12),
        "confidence_interval_95_method": confidence_method,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "case_results": safe_cases,
        "private_unit_content_sha256": _file_sha256(unit_path),
        "status": "completed" if not reasons else "failed",
        "reason_codes": sorted(set(reasons)),
        "elapsed_ms": 0.0,
        "raw_private_unit_path_persisted": False,
        "raw_source_id_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _screening_unit_set_digest(units: Sequence[Mapping[str, Any]]) -> str:
    return sha256_text(
        stable_json(
            sorted(
                (
                    {
                        "task_id": str(row.get("task_id") or ""),
                        "status": str(row.get("status") or ""),
                        "mean_score": row.get("mean_score"),
                        "private_unit_content_sha256": str(
                            row.get("private_unit_content_sha256") or ""
                        ),
                    }
                    for row in units
                ),
                key=lambda row: str(row["task_id"]),
            )
        )
    )


def _screening_unit_path(
    private_root: Path,
    task: Mapping[str, Any],
) -> Path:
    source_slug = str(task.get("source_id_sha256") or "source")[:16]
    task_id = str(task.get("task_id") or "task")
    return private_root / source_slug / f"{task_id}.private.json"


def _screening_checkpoint_path(
    private_root: Path,
    task: Mapping[str, Any],
) -> Path:
    """Return the private, non-safe path used for an in-flight unit."""

    source_slug = str(task.get("source_id_sha256") or "source")[:16]
    task_id = str(task.get("task_id") or "task")
    return private_root / source_slug / f"{task_id}.checkpoint.private.json"


def _persist_screening_private_checkpoint(
    path: Path,
    *,
    task: Mapping[str, Any],
    private_source_id: str,
    case_results: Sequence[Mapping[str, Any]],
    expected_case_count: int,
) -> None:
    """Atomically persist an in-flight provider-answer checkpoint.

    This file deliberately contains raw remote outputs and therefore stays in
    the operator-owned private root.  It has no safe-artifact digest and is
    never sufficient for ranking; it only reduces recovery loss after a
    process or network interruption.
    """

    payload = {
        "schema": SCREENING_UNIT_PRIVATE_SCHEMA,
        "checkpoint_status": "partial",
        "task_id": str(task.get("task_id") or ""),
        "source_id": private_source_id,
        "canonical_identity_sha256": str(
            task.get("canonical_identity_sha256") or ""
        ),
        "candidate_id_sha256": str(task.get("candidate_id_sha256") or ""),
        "expected_case_count": max(0, int(expected_case_count)),
        "case_results": [dict(row) for row in case_results],
        "raw_provider_outputs_persisted": True,
        "private_artifact": True,
        "secrets_persisted": False,
    }
    _atomic_write_json(path, payload)


def _blocked_unit(task: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "schema": SCREENING_UNIT_SAFE_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "source_id_sha256": str(task.get("source_id_sha256") or ""),
        "canonical_identity_sha256": str(
            task.get("canonical_identity_sha256") or ""
        ),
        "candidate_id_sha256": str(task.get("candidate_id_sha256") or ""),
        "status": "blocked",
        "reason_codes": [reason],
        "case_results": [],
        "raw_source_id_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _mean_confidence_interval(
    values: Sequence[float],
) -> tuple[float, float, str]:
    if not values:
        return 0.0, 0.0, "not_available"
    mean = sum(values) / len(values)
    if all(float(value) in {0.0, 1.0} for value in values):
        # Wilson is well behaved for binary accuracy even near zero or one.
        z = 1.959963984540054
        count = len(values)
        denominator = 1.0 + (z * z / count)
        center = (mean + z * z / (2.0 * count)) / denominator
        margin = (
            z
            * math.sqrt(
                mean * (1.0 - mean) / count
                + z * z / (4.0 * count * count)
            )
            / denominator
        )
        return (
            max(0.0, center - margin),
            min(1.0, center + margin),
            "wilson_score_binary_95",
        )
    if len(values) < 2:
        return max(0.0, mean), min(1.0, mean), "single_observation"

    # LiveBench scorers can award partial credit.  A deterministic percentile
    # bootstrap avoids assuming normally distributed bounded task scores.
    seed = int(sha256_text(stable_json(list(values)))[:16], 16)
    generator = random.Random(seed)
    count = len(values)
    resampled_means = sorted(
        sum(values[generator.randrange(count)] for _ in range(count)) / count
        for _ in range(DEFAULT_BOOTSTRAP_RESAMPLES)
    )
    lower = _percentile(resampled_means, 0.025)
    upper = _percentile(resampled_means, 0.975)
    return (
        max(0.0, float(lower if lower is not None else mean)),
        min(1.0, float(upper if upper is not None else mean)),
        f"deterministic_percentile_bootstrap_{DEFAULT_BOOTSTRAP_RESAMPLES}_95",
    )


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _finalize_campaign_state(
    base: Mapping[str, Any],
    *,
    units: Sequence[Mapping[str, Any]],
    status: str,
    blockers: Sequence[str],
    elapsed_ms: float,
    state_path: Path | None,
) -> dict[str, Any]:
    rows = sorted(
        (dict(row) for row in units),
        key=lambda row: str(row.get("task_id") or ""),
    )
    completed = sum(1 for row in rows if row.get("status") == "completed")
    result = {
        **dict(base),
        "status": status,
        "network_calls_performed": bool(base.get("mode") == "live" and rows),
        "completed_unit_count": completed,
        "failed_or_blocked_unit_count": sum(
            1 for row in rows if row.get("status") in {"failed", "blocked"}
        ),
        "units": rows,
        "unit_set_digest_sha256": sha256_text(
            stable_json(
                sorted(
                    (
                        {
                            "task_id": str(row.get("task_id") or ""),
                            "status": str(row.get("status") or ""),
                            "mean_score": row.get("mean_score"),
                            "private_unit_content_sha256": str(
                                row.get("private_unit_content_sha256") or ""
                            ),
                        }
                        for row in rows
                    ),
                    key=lambda row: str(row["task_id"]),
                )
            )
        ),
        "ready_for_ranking": (
            status == "completed"
            and completed == int(base.get("planned_task_count") or 0)
            and not blockers
        ),
        "reason_codes": sorted(set(str(reason) for reason in blockers if str(reason))),
        "elapsed_ms": round(elapsed_ms, 3),
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    safe_errors = _screening_safe_artifact_leakage_errors(result)
    if safe_errors:
        result["status"] = "blocked"
        result["ready_for_ranking"] = False
        result["reason_codes"] = sorted(
            set([*result["reason_codes"], *safe_errors])
        )
    result["campaign_digest_sha256"] = sha256_text(
        stable_json(
            {
                key: value
                for key, value in result.items()
                if key not in {"campaign_digest_sha256", "elapsed_ms"}
            }
        )
    )
    if state_path is not None:
        _atomic_write_json(state_path, result)
    return result


def _persist_campaign_progress(
    state_path: Path | None,
    base: Mapping[str, Any],
    units: Sequence[Mapping[str, Any]],
    started: float,
) -> None:
    if state_path is None:
        return
    _finalize_campaign_state(
        base,
        units=units,
        status="running",
        blockers=[],
        elapsed_ms=(time.monotonic() - started) * 1000,
        state_path=state_path,
    )


def _load_existing_campaign_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _screening_resume_state_errors(
    state: Mapping[str, Any],
    *,
    base_state: Mapping[str, Any],
) -> list[str]:
    """Authenticate a safe checkpoint before any completed unit is trusted."""

    if not state:
        return []
    errors: list[str] = []
    if state.get("schema") != SCREENING_CAMPAIGN_SCHEMA:
        errors.append("screening_resume_state_schema_invalid")
    for key in (
        "mode",
        "plan_file_content_sha256",
        "plan_digest_sha256",
        "registry_file_sha256",
        "source_manifest_content_sha256",
        "execution_schedule_digest_sha256",
        "execution_task_sequence_sha256",
        "live_credential_readiness_digest_sha256",
        "private_root_sha256",
        "planned_task_count",
    ):
        if state.get(key) != base_state.get(key):
            errors.append(f"screening_resume_{key}_mismatch")

    declared_digest = str(state.get("campaign_digest_sha256") or "")
    computed_digest = sha256_text(
        stable_json(
            {
                key: value
                for key, value in state.items()
                if key not in {"campaign_digest_sha256", "elapsed_ms"}
            }
        )
    )
    if not _looks_like_sha256(declared_digest) or declared_digest != computed_digest:
        errors.append("screening_resume_campaign_digest_mismatch")

    units = (
        [row for row in state.get("units", []) if isinstance(row, Mapping)]
        if isinstance(state.get("units"), list)
        else []
    )
    expected_unit_set_digest = sha256_text(
        stable_json(
            sorted(
                (
                    {
                        "task_id": str(row.get("task_id") or ""),
                        "status": str(row.get("status") or ""),
                        "mean_score": row.get("mean_score"),
                        "private_unit_content_sha256": str(
                            row.get("private_unit_content_sha256") or ""
                        ),
                    }
                    for row in units
                ),
                key=lambda row: str(row["task_id"]),
            )
        )
    )
    if str(state.get("unit_set_digest_sha256") or "") != expected_unit_set_digest:
        errors.append("screening_resume_unit_set_digest_mismatch")
    errors.extend(_screening_safe_artifact_leakage_errors(state))
    return sorted(set(errors))


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _dedupe_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = dict(row)
        selected.setdefault(sha256_text(stable_json(value)), value)
    return [selected[key] for key in sorted(selected)]


def _looks_like_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").lower()))
