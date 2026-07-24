from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from .registry import load_registry
from .schemas import CAPABILITY_AXES, ModelProfile, sha256_text, stable_json


PROVIDER_ONBOARDING_CANDIDATE_SCHEMA = "axio_fusion_api.provider_onboarding_candidate.v1"
PROVIDER_ONBOARDING_REVIEW_SCHEMA = "axio_fusion_api.provider_onboarding_review.v1"
PROVIDER_ONBOARDING_ACTIVATION_SCHEMA = "axio_fusion_api.provider_onboarding_activation.v1"
PROVIDER_ONBOARDING_APPLY_RECEIPT_SCHEMA = "axio_fusion_api.provider_onboarding_apply_receipt.v1"
PROVIDER_ONBOARDING_LIFECYCLE = (
    "configured",
    "protocol_validated",
    "live_probed",
    "capability_calibrated",
    "shadow_candidate",
    "approved",
    "active",
    "retired",
)
SUPPORTED_PROVIDER_API_FORMATS = frozenset({"chat", "responses", "anthropic", "gemini"})


def build_provider_onboarding_candidate(
    *,
    profiles: Sequence[ModelProfile],
    candidate_profile_hashes: Sequence[str],
    probe_paths: Sequence[str | Path] = (),
    calibration_paths: Sequence[str | Path] = (),
    created_on: str | None = None,
) -> dict[str, Any]:
    """Build a private-registry-bound, shadow-only provider onboarding plan.

    Newly configured profiles remain disabled in the serving registry.  This
    artifact may consume private probe/calibration files, but it emits only
    profile/provider/model hashes and aggregate capability information.
    """

    profile_map = {sha256_text(profile.profile_id): profile for profile in profiles}
    selected_hashes = _normalized_profile_hashes(candidate_profile_hashes)
    selected_profiles = [profile_map[item] for item in selected_hashes if item in profile_map]
    unknown_hashes = [item for item in selected_hashes if item not in profile_map]
    created_on = str(created_on or date.today().isoformat())
    blockers = []
    if not _valid_iso_date(created_on):
        blockers.append("provider_onboarding_candidate_created_on_invalid")
        created_on = ""
    if not selected_hashes:
        blockers.append("provider_onboarding_candidate_profiles_missing")
    if unknown_hashes:
        blockers.append("provider_onboarding_candidate_profiles_not_in_registry")
    configured_rows = [_configured_profile_receipt(profile) for profile in selected_profiles]
    configured_ready = bool(selected_profiles) and all(
        row["configured"] for row in configured_rows
    )
    if not configured_ready:
        blockers.append("provider_onboarding_configured_stage_incomplete")

    probe_payloads = _load_json_objects(probe_paths)
    probe_index = _probe_evidence_index(probe_payloads)
    protocol_rows = [
        _protocol_probe_receipt(profile, probe_index.get(sha256_text(profile.profile_id), []))
        for profile in selected_profiles
    ]
    protocol_validated = bool(selected_profiles) and all(
        row["protocol_validated"] for row in protocol_rows
    )
    live_probed = bool(selected_profiles) and all(
        row["live_probed"] for row in protocol_rows
    )
    if not protocol_validated:
        blockers.append("provider_onboarding_protocol_validation_incomplete")
    if not live_probed:
        blockers.append("provider_onboarding_live_probe_incomplete")

    calibration_payloads = _load_json_objects(calibration_paths)
    calibration_index = _calibration_evidence_index(calibration_payloads)
    calibration_rows = [
        _calibration_receipt(
            profile,
            calibration_index.get(sha256_text(profile.profile_id), []),
        )
        for profile in selected_profiles
    ]
    capability_calibrated = bool(selected_profiles) and all(
        row["capability_calibrated"] for row in calibration_rows
    )
    if not capability_calibrated:
        blockers.append("provider_onboarding_capability_calibration_incomplete")

    complementarity = _complementarity_receipt(
        selected_profiles,
        profiles,
    )
    complementarity_assessed = complementarity["assessed"] is True
    if not complementarity_assessed:
        blockers.append("provider_onboarding_complementarity_assessment_incomplete")

    shadow_candidate_ready = (
        configured_ready
        and protocol_validated
        and live_probed
        and capability_calibrated
        and complementarity_assessed
        and all(profile.enabled is False for profile in selected_profiles)
    )
    if not shadow_candidate_ready:
        blockers.append("provider_onboarding_shadow_candidate_not_ready")
    candidate = {
        "schema": PROVIDER_ONBOARDING_CANDIDATE_SCHEMA,
        "status": "shadow_candidate" if shadow_candidate_ready else "blocked",
        "created_on": created_on,
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "candidate_profile_count": len(selected_profiles),
        "candidate_profile_hashes": selected_hashes,
        "candidate_profiles": configured_rows,
        "lifecycle": {
            "allowed_states": list(PROVIDER_ONBOARDING_LIFECYCLE),
            "current_state": "shadow_candidate" if shadow_candidate_ready else _next_lifecycle_state(
                configured_ready=configured_ready,
                protocol_validated=protocol_validated,
                live_probed=live_probed,
                capability_calibrated=capability_calibrated,
                complementarity_assessed=complementarity_assessed,
            ),
            "stages": [
                {
                    "state": "configured",
                    "ready": configured_ready,
                    "profile_count": len(configured_rows),
                },
                {
                    "state": "protocol_validated",
                    "ready": protocol_validated,
                    "profile_count": len(protocol_rows),
                },
                {
                    "state": "live_probed",
                    "ready": live_probed,
                    "profile_count": len(protocol_rows),
                },
                {
                    "state": "capability_calibrated",
                    "ready": capability_calibrated,
                    "profile_count": len(calibration_rows),
                },
                {
                    "state": "shadow_candidate",
                    "ready": shadow_candidate_ready,
                    "profile_count": len(selected_profiles),
                },
            ],
        },
        "probe_evidence": {
            "probe_file_count": len(probe_paths),
            "probe_path_hashes": [sha256_text(str(path)) for path in probe_paths],
            "probe_payload_count": len(probe_payloads),
            "profile_receipts": protocol_rows,
            "raw_probe_paths_persisted": False,
            "raw_provider_outputs_persisted": False,
        },
        "calibration_evidence": {
            "calibration_file_count": len(calibration_paths),
            "calibration_path_hashes": [
                sha256_text(str(path)) for path in calibration_paths
            ],
            "calibration_payload_count": len(calibration_payloads),
            "profile_receipts": calibration_rows,
            "raw_calibration_paths_persisted": False,
            "raw_provider_outputs_persisted": False,
        },
        "complementarity": complementarity,
        "shadow_routing_contract": {
            "candidate_profiles_must_remain_disabled": True,
            "candidate_profiles_currently_enabled": sum(
                1 for profile in selected_profiles if profile.enabled
            ),
            "serving_direct_route_eligible": False,
            "terra_panel_eligible": False,
            "pro_panel_eligible": False,
            "live_probe_allowed": True,
            "shadow_or_offline_evaluation_required_before_approval": True,
            "automatic_panel_promotion": False,
        },
        "ready_for_review": shadow_candidate_ready,
        "blockers": sorted(set(blockers)),
        "application_contract": {
            "remote_api_only": True,
            "local_model_weights_loaded": False,
            "provider_calls_performed_by_assessment": False,
            "registry_mutated_by_assessment": False,
            "new_provider_auto_enabled": False,
            "new_provider_auto_enters_fusion_panel": False,
            "human_approval_required": True,
            "separate_registry_activation_required": True,
            "not_for_final_benchmark_claims": True,
            "raw_prompts_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }
    candidate["candidate_digest_sha256"] = sha256_text(
        stable_json(_candidate_digest_input(candidate))
    )
    return candidate


def review_provider_onboarding_candidate(
    candidate: Mapping[str, Any] | None,
    *,
    profiles: Sequence[ModelProfile],
    approved: bool,
    reviewer_id: str = "",
    reviewed_on: str | None = None,
) -> dict[str, Any]:
    """Create a hash-only human approval record for a shadow candidate."""

    candidate = candidate if isinstance(candidate, Mapping) else {}
    reviewed_on = str(reviewed_on or date.today().isoformat())
    blockers = _candidate_validation_errors(candidate, profiles=profiles)
    if approved is not True:
        blockers.append("provider_onboarding_human_approval_missing")
    if not _valid_iso_date(reviewed_on):
        blockers.append("provider_onboarding_reviewed_on_invalid")
        reviewed_on = ""
    review = {
        "schema": PROVIDER_ONBOARDING_REVIEW_SCHEMA,
        "candidate_digest_sha256": str(candidate.get("candidate_digest_sha256") or ""),
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "reviewed_on": reviewed_on,
        "approved": approved is True,
        "reviewer_id_sha256": sha256_text(str(reviewer_id or ""))
        if str(reviewer_id or "")
        else "",
        "candidate_profile_hashes": _normalized_profile_hashes(
            candidate.get("candidate_profile_hashes")
            if isinstance(candidate.get("candidate_profile_hashes"), list)
            else []
        ),
        "ready_for_activation": not blockers,
        "blockers": sorted(set(blockers)),
        "application_contract": {
            "human_approval_required": True,
            "automatic_registry_mutation": False,
            "automatic_panel_promotion": False,
            "raw_reviewer_id_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "secrets_persisted": False,
        },
        "raw_reviewer_id_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }
    review["review_digest_sha256"] = sha256_text(stable_json(_review_digest_input(review)))
    return review


def activate_provider_onboarding_candidate(
    candidate: Mapping[str, Any] | None,
    review: Mapping[str, Any] | None,
    *,
    profiles: Sequence[ModelProfile],
    activated_on: str | None = None,
) -> dict[str, Any]:
    """Authorize a registry activation without changing the registry itself."""

    candidate = candidate if isinstance(candidate, Mapping) else {}
    review = review if isinstance(review, Mapping) else {}
    activated_on = str(activated_on or date.today().isoformat())
    blockers = _candidate_validation_errors(candidate, profiles=profiles)
    blockers.extend(_review_validation_errors(review, candidate=candidate, profiles=profiles))
    if not _valid_iso_date(activated_on):
        blockers.append("provider_onboarding_activated_on_invalid")
        activated_on = ""
    activation = {
        "schema": PROVIDER_ONBOARDING_ACTIVATION_SCHEMA,
        "status": "approved_pending_registry_activation" if not blockers else "blocked",
        "activated_on": activated_on,
        "candidate_digest_sha256": str(candidate.get("candidate_digest_sha256") or ""),
        "review_digest_sha256": str(review.get("review_digest_sha256") or ""),
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "candidate_profile_hashes": _normalized_profile_hashes(
            candidate.get("candidate_profile_hashes")
            if isinstance(candidate.get("candidate_profile_hashes"), list)
            else []
        ),
        "activation_ready": not blockers,
        "blockers": sorted(set(blockers)),
        "activation_contract": {
            "requires_explicit_private_registry_output_path": True,
            "in_place_registry_overwrite_allowed": False,
            "candidate_profiles_enabled_by_this_artifact": False,
            "candidate_profiles_panel_eligible_before_apply": False,
            "candidate_profiles_become_eligible_only_after_apply": True,
            "provider_calls_performed": False,
            "local_model_weights_loaded": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "secrets_persisted": False,
        },
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }
    activation["activation_digest_sha256"] = sha256_text(
        stable_json(_activation_digest_input(activation))
    )
    return activation


def apply_provider_onboarding_activation(
    candidate: Mapping[str, Any] | None,
    review: Mapping[str, Any] | None,
    *,
    registry_path: str | Path,
    output_registry_path: str | Path,
) -> dict[str, Any]:
    """Write a new private registry with approved candidate profiles enabled.

    The source registry is never changed in place.  The return value is a safe
    receipt; the explicitly requested output registry remains an operator-only
    configuration file and therefore preserves its private provider settings.
    """

    candidate = candidate if isinstance(candidate, Mapping) else {}
    review = review if isinstance(review, Mapping) else {}
    source = Path(registry_path)
    target = Path(output_registry_path)
    blockers = []
    if not source.exists() or not source.is_file():
        blockers.append("provider_onboarding_source_registry_not_found")
    if not str(output_registry_path or "").strip():
        blockers.append("provider_onboarding_output_registry_path_missing")
    if source.exists() and target and _same_path(source, target):
        blockers.append("provider_onboarding_in_place_registry_activation_forbidden")
    profiles = load_registry(source, include_disabled=True) if not blockers else []
    blockers.extend(_candidate_validation_errors(candidate, profiles=profiles))
    blockers.extend(_review_validation_errors(review, candidate=candidate, profiles=profiles))
    activation = activate_provider_onboarding_candidate(
        candidate,
        review,
        profiles=profiles,
    )
    if activation.get("activation_ready") is not True:
        blockers.extend(
            str(item) for item in activation.get("blockers", []) if str(item)
        )
    selected_hashes = _normalized_profile_hashes(
        candidate.get("candidate_profile_hashes")
        if isinstance(candidate.get("candidate_profile_hashes"), list)
        else []
    )
    raw_registry: dict[str, Any] = {}
    if not blockers:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blockers.append("provider_onboarding_source_registry_invalid_json")
        else:
            if not isinstance(payload, Mapping) or not isinstance(payload.get("models"), list):
                blockers.append("provider_onboarding_source_registry_models_missing")
            else:
                raw_registry = dict(payload)
    before_digest = _registry_enablement_digest(raw_registry)
    changed_hashes: list[str] = []
    if not blockers:
        models = raw_registry.get("models") if isinstance(raw_registry.get("models"), list) else []
        updated_models = []
        for row in models:
            if not isinstance(row, Mapping):
                continue
            updated = dict(row)
            profile_hash = sha256_text(
                f"{str(updated.get('provider') or '')}/{str(updated.get('model') or '')}"
            )
            if profile_hash in selected_hashes:
                if updated.get("enabled") is True:
                    blockers.append("provider_onboarding_candidate_already_enabled")
                updated["enabled"] = True
                updated["onboarding_state"] = "active"
                changed_hashes.append(profile_hash)
            updated_models.append(updated)
        if sorted(set(changed_hashes)) != selected_hashes:
            blockers.append("provider_onboarding_candidate_registry_rows_missing")
        raw_registry["models"] = updated_models
    if not blockers:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(raw_registry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    after_digest = _registry_enablement_digest(raw_registry) if not blockers else ""
    return {
        "schema": PROVIDER_ONBOARDING_APPLY_RECEIPT_SCHEMA,
        "status": "active" if not blockers else "blocked",
        "candidate_digest_sha256": str(candidate.get("candidate_digest_sha256") or "")
        if _looks_like_sha256(candidate.get("candidate_digest_sha256"))
        else "",
        "review_digest_sha256": str(review.get("review_digest_sha256") or "")
        if _looks_like_sha256(review.get("review_digest_sha256"))
        else "",
        "activation_digest_sha256": str(activation.get("activation_digest_sha256") or "")
        if _looks_like_sha256(activation.get("activation_digest_sha256"))
        else "",
        "candidate_profile_hashes": selected_hashes,
        "enabled_profile_count": len(changed_hashes) if not blockers else 0,
        "registry_before_enablement_digest_sha256": before_digest,
        "registry_after_enablement_digest_sha256": after_digest,
        "registry_output_written": not blockers,
        "registry_output_path_sha256": sha256_text(str(target)) if str(target) else "",
        "blockers": sorted(set(blockers)),
        "application_contract": {
            "source_registry_mutated_in_place": False,
            "output_registry_is_private_operator_configuration": True,
            "provider_calls_performed": False,
            "local_model_weights_loaded": False,
            "candidate_profiles_panel_eligible_after_apply": not blockers,
            "raw_registry_paths_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "secrets_persisted": False,
        },
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return selected


def _configured_profile_receipt(profile: ModelProfile) -> dict[str, Any]:
    api_format = str(profile.api_format or "").strip().lower()
    config_ready = (
        profile.enabled is False
        and api_format in SUPPORTED_PROVIDER_API_FORMATS
        and bool(str(profile.base_url_env or "").strip())
        and bool(str(profile.api_key_env or "").strip())
    )
    return {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "provider_sha256": sha256_text(profile.provider),
        "model_sha256": sha256_text(profile.model),
        "api_format": api_format,
        "configured": config_ready,
        "enabled": profile.enabled is True,
        "base_url_reference_configured": bool(str(profile.base_url_env or "").strip()),
        "credential_reference_configured": bool(str(profile.api_key_env or "").strip()),
        "supports_tools": profile.supports_tools is True,
        "supports_vision": profile.supports_vision is True,
        "capability_summary": {
            axis: round(profile.capability(axis), 4) for axis in CAPABILITY_AXES
        },
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_id_persisted": False,
        "raw_base_url_reference_persisted": False,
        "raw_credential_reference_persisted": False,
    }


def _probe_evidence_index(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for payload in payloads:
        mode = _probe_mode(payload)
        network_called = _probe_network_called(payload)
        for row in _probe_rows(payload):
            profile_hash = _profile_hash_from_evidence(row)
            if not profile_hash:
                continue
            indexed.setdefault(profile_hash, []).append(
                {
                    "mode": mode,
                    "network_called": network_called,
                    "api_format": str(row.get("api_format") or "").strip().lower(),
                    "status": str(row.get("status") or "").strip().lower(),
                    "transport_attempt_count": _safe_int(
                        row.get("transport_attempt_count")
                    ),
                    "provider_request_count": _safe_int(
                        row.get("provider_request_count")
                    ),
                    "latency_ms": _safe_nonnegative_float(row.get("latency_ms")),
                }
            )
    return indexed


def _protocol_probe_receipt(
    profile: ModelProfile, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    api_format = str(profile.api_format or "").strip().lower()
    matching = [
        row
        for row in rows
        if str(row.get("api_format") or "") == api_format
        and row.get("mode") == "live"
        and row.get("network_called") is True
    ]
    transport_rows = [
        row
        for row in matching
        if _safe_int(row.get("transport_attempt_count")) > 0
        or _safe_int(row.get("provider_request_count")) > 0
        or str(row.get("status") or "") == "available"
    ]
    available_rows = [
        row for row in matching if str(row.get("status") or "") == "available"
    ]
    latencies = [
        _safe_nonnegative_float(row.get("latency_ms")) for row in available_rows
    ]
    return {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "api_format": api_format,
        "live_probe_row_count": len(matching),
        "live_transport_attempt_row_count": len(transport_rows),
        "live_available_row_count": len(available_rows),
        "protocol_validated": bool(transport_rows),
        "live_probed": bool(available_rows),
        "observed_latency_ms": _average(latencies),
        "raw_provider_output_persisted": False,
        "raw_provider_error_persisted": False,
    }


def _calibration_evidence_index(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for payload in payloads:
        patches = payload.get("patches") if isinstance(payload.get("patches"), list) else []
        for patch in patches:
            if not isinstance(patch, Mapping):
                continue
            profile_hash = _profile_hash_from_evidence(patch)
            if not profile_hash:
                continue
            counts = patch.get("signal_counts") if isinstance(patch.get("signal_counts"), Mapping) else {}
            capability_patch = (
                patch.get("capabilities_patch")
                if isinstance(patch.get("capabilities_patch"), Mapping)
                else {}
            )
            indexed.setdefault(profile_hash, []).append(
                {
                    "probe_total": _safe_int(counts.get("probe_total")),
                    "trace_seen_count": _safe_int(counts.get("trace_seen_count")),
                    "feedback_count": _safe_int(counts.get("feedback_count")),
                    "capability_axis_count": len(
                        [axis for axis in CAPABILITY_AXES if axis in capability_patch]
                    ),
                    "health": _safe_label(patch.get("health"), default="unknown"),
                }
            )
    return indexed


def _calibration_receipt(
    profile: ModelProfile, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    probe_total = sum(_safe_int(row.get("probe_total")) for row in rows)
    capability_axis_count = max(
        [_safe_int(row.get("capability_axis_count")) for row in rows] or [0]
    )
    return {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "calibration_row_count": len(rows),
        "probe_signal_count": probe_total,
        "capability_axis_count": capability_axis_count,
        "capability_calibrated": bool(rows) and probe_total > 0,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
    }


def _complementarity_receipt(
    candidates: Sequence[ModelProfile], profiles: Sequence[ModelProfile]
) -> dict[str, Any]:
    candidate_hashes = {sha256_text(profile.profile_id) for profile in candidates}
    active = [
        profile
        for profile in profiles
        if profile.enabled is True and sha256_text(profile.profile_id) not in candidate_hashes
    ]
    rows = []
    for candidate in candidates:
        similarities = [_capability_similarity(candidate, profile) for profile in active]
        best_similarity = max(similarities) if similarities else None
        rows.append(
            {
                "profile_id_sha256": sha256_text(candidate.profile_id),
                "active_pool_profile_count": len(active),
                "best_capability_similarity": best_similarity,
                "capability_complementarity_estimate": None
                if best_similarity is None
                else round(1.0 - best_similarity, 6),
                "novel_capability_axis_count": _novel_axis_count(candidate, active),
                "api_format_diversity_candidate": bool(
                    active
                    and candidate.api_format
                    not in {profile.api_format for profile in active}
                ),
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_model_id_persisted": False,
            }
        )
    return {
        "method": "capability_vector_similarity_and_api_format_diversity.v1",
        "assessed": bool(candidates),
        "active_pool_profile_count": len(active),
        "candidate_receipts": rows,
        "heuristic_only": True,
        "not_a_model_quality_rank": True,
        "not_a_benchmark_substitute": True,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
    }


def _capability_similarity(left: ModelProfile, right: ModelProfile) -> float:
    if not CAPABILITY_AXES:
        return 0.0
    distance = sum(
        abs(left.capability(axis) - right.capability(axis)) for axis in CAPABILITY_AXES
    ) / len(CAPABILITY_AXES)
    return round(max(0.0, min(1.0, 1.0 - distance)), 6)


def _novel_axis_count(candidate: ModelProfile, active: Sequence[ModelProfile]) -> int:
    if not active:
        return 0
    count = 0
    for axis in CAPABILITY_AXES:
        baseline = max(profile.capability(axis) for profile in active)
        if candidate.capability(axis) >= baseline + 0.05:
            count += 1
    return count


def _candidate_validation_errors(
    candidate: Mapping[str, Any], *, profiles: Sequence[ModelProfile]
) -> list[str]:
    errors = []
    if str(candidate.get("schema") or "") != PROVIDER_ONBOARDING_CANDIDATE_SCHEMA:
        errors.append("provider_onboarding_candidate_schema_unrecognized")
    digest = str(candidate.get("candidate_digest_sha256") or "")
    if not _looks_like_sha256(digest) or digest != sha256_text(
        stable_json(_candidate_digest_input(candidate))
    ):
        errors.append("provider_onboarding_candidate_digest_mismatch")
    if candidate.get("status") != "shadow_candidate" or candidate.get("ready_for_review") is not True:
        errors.append("provider_onboarding_candidate_not_shadow_ready")
    if str(candidate.get("registry_profile_set_sha256") or "") != _profile_set_sha256(profiles):
        errors.append("provider_onboarding_candidate_registry_binding_mismatch")
    selected = _normalized_profile_hashes(
        candidate.get("candidate_profile_hashes")
        if isinstance(candidate.get("candidate_profile_hashes"), list)
        else []
    )
    profile_map = {sha256_text(profile.profile_id): profile for profile in profiles}
    if not selected or any(item not in profile_map for item in selected):
        errors.append("provider_onboarding_candidate_profiles_invalid")
    if any(profile_map[item].enabled is True for item in selected if item in profile_map):
        errors.append("provider_onboarding_candidate_profiles_enabled_before_apply")
    lifecycle = candidate.get("lifecycle") if isinstance(candidate.get("lifecycle"), Mapping) else {}
    stages = lifecycle.get("stages") if isinstance(lifecycle.get("stages"), list) else []
    readiness = {
        str(row.get("state") or ""): row.get("ready") is True
        for row in stages
        if isinstance(row, Mapping)
    }
    for state in (
        "configured",
        "protocol_validated",
        "live_probed",
        "capability_calibrated",
        "shadow_candidate",
    ):
        if readiness.get(state) is not True:
            errors.append(f"provider_onboarding_candidate_{state}_stage_invalid")
    if _contains_forbidden_raw_fields(candidate):
        errors.append("provider_onboarding_candidate_contains_raw_private_fields")
    return sorted(set(errors))


def _review_validation_errors(
    review: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    profiles: Sequence[ModelProfile],
) -> list[str]:
    errors = []
    if str(review.get("schema") or "") != PROVIDER_ONBOARDING_REVIEW_SCHEMA:
        errors.append("provider_onboarding_review_schema_unrecognized")
    digest = str(review.get("review_digest_sha256") or "")
    if not _looks_like_sha256(digest) or digest != sha256_text(
        stable_json(_review_digest_input(review))
    ):
        errors.append("provider_onboarding_review_digest_mismatch")
    if review.get("approved") is not True or review.get("ready_for_activation") is not True:
        errors.append("provider_onboarding_review_not_approved")
    if str(review.get("candidate_digest_sha256") or "") != str(
        candidate.get("candidate_digest_sha256") or ""
    ):
        errors.append("provider_onboarding_review_candidate_binding_mismatch")
    if str(review.get("registry_profile_set_sha256") or "") != _profile_set_sha256(profiles):
        errors.append("provider_onboarding_review_registry_binding_mismatch")
    review_hashes = _normalized_profile_hashes(
        review.get("candidate_profile_hashes")
        if isinstance(review.get("candidate_profile_hashes"), list)
        else []
    )
    candidate_hashes = _normalized_profile_hashes(
        candidate.get("candidate_profile_hashes")
        if isinstance(candidate.get("candidate_profile_hashes"), list)
        else []
    )
    if review_hashes != candidate_hashes:
        errors.append("provider_onboarding_review_profile_binding_mismatch")
    if _contains_forbidden_raw_fields(review):
        errors.append("provider_onboarding_review_contains_raw_private_fields")
    return sorted(set(errors))


def _candidate_digest_input(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(candidate.get("schema") or ""),
        "status": str(candidate.get("status") or ""),
        "created_on": str(candidate.get("created_on") or ""),
        "registry_profile_set_sha256": str(
            candidate.get("registry_profile_set_sha256") or ""
        ),
        "candidate_profile_hashes": _normalized_profile_hashes(
            candidate.get("candidate_profile_hashes")
            if isinstance(candidate.get("candidate_profile_hashes"), list)
            else []
        ),
        "candidate_profiles": _safe_candidate_profiles(candidate.get("candidate_profiles")),
        "lifecycle": _safe_lifecycle(candidate.get("lifecycle")),
        "probe_evidence": _safe_probe_evidence(candidate.get("probe_evidence")),
        "calibration_evidence": _safe_calibration_evidence(
            candidate.get("calibration_evidence")
        ),
        "complementarity": _safe_complementarity(candidate.get("complementarity")),
        "shadow_routing_contract": _safe_shadow_routing_contract(
            candidate.get("shadow_routing_contract")
        ),
        "ready_for_review": candidate.get("ready_for_review") is True,
        "blockers": sorted(str(item) for item in candidate.get("blockers", []) if item),
        "application_contract": _safe_application_contract(
            candidate.get("application_contract")
        ),
    }


def _review_digest_input(review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(review.get("schema") or ""),
        "candidate_digest_sha256": str(review.get("candidate_digest_sha256") or ""),
        "registry_profile_set_sha256": str(
            review.get("registry_profile_set_sha256") or ""
        ),
        "reviewed_on": str(review.get("reviewed_on") or ""),
        "approved": review.get("approved") is True,
        "reviewer_id_sha256": str(review.get("reviewer_id_sha256") or ""),
        "candidate_profile_hashes": _normalized_profile_hashes(
            review.get("candidate_profile_hashes")
            if isinstance(review.get("candidate_profile_hashes"), list)
            else []
        ),
        "ready_for_activation": review.get("ready_for_activation") is True,
        "blockers": sorted(str(item) for item in review.get("blockers", []) if item),
        "application_contract": _safe_application_contract(
            review.get("application_contract")
        ),
    }


def _activation_digest_input(activation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(activation.get("schema") or ""),
        "status": str(activation.get("status") or ""),
        "activated_on": str(activation.get("activated_on") or ""),
        "candidate_digest_sha256": str(
            activation.get("candidate_digest_sha256") or ""
        ),
        "review_digest_sha256": str(activation.get("review_digest_sha256") or ""),
        "registry_profile_set_sha256": str(
            activation.get("registry_profile_set_sha256") or ""
        ),
        "candidate_profile_hashes": _normalized_profile_hashes(
            activation.get("candidate_profile_hashes")
            if isinstance(activation.get("candidate_profile_hashes"), list)
            else []
        ),
        "activation_ready": activation.get("activation_ready") is True,
        "blockers": sorted(str(item) for item in activation.get("blockers", []) if item),
        "activation_contract": _safe_application_contract(
            activation.get("activation_contract")
        ),
    }


def _safe_candidate_profiles(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    safe = []
    for row in rows[:64]:
        if not isinstance(row, Mapping):
            continue
        profile_hash = str(row.get("profile_id_sha256") or "")
        provider_hash = str(row.get("provider_sha256") or "")
        model_hash = str(row.get("model_sha256") or "")
        if not (
            _looks_like_sha256(profile_hash)
            and _looks_like_sha256(provider_hash)
            and _looks_like_sha256(model_hash)
        ):
            continue
        capabilities = (
            row.get("capability_summary")
            if isinstance(row.get("capability_summary"), Mapping)
            else {}
        )
        safe.append(
            {
                "profile_id_sha256": profile_hash,
                "provider_sha256": provider_hash,
                "model_sha256": model_hash,
                "api_format": str(row.get("api_format") or ""),
                "configured": row.get("configured") is True,
                "enabled": row.get("enabled") is True,
                "base_url_reference_configured": row.get(
                    "base_url_reference_configured"
                )
                is True,
                "credential_reference_configured": row.get(
                    "credential_reference_configured"
                )
                is True,
                "supports_tools": row.get("supports_tools") is True,
                "supports_vision": row.get("supports_vision") is True,
                "capability_summary": {
                    axis: _safe_unit_float(capabilities.get(axis)) or 0.0
                    for axis in CAPABILITY_AXES
                },
            }
        )
    return safe


def _safe_lifecycle(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    stages = value.get("stages") if isinstance(value.get("stages"), list) else []
    return {
        "allowed_states": [
            str(item)
            for item in value.get("allowed_states", [])
            if str(item) in PROVIDER_ONBOARDING_LIFECYCLE
        ][:8]
        if isinstance(value.get("allowed_states"), list)
        else [],
        "current_state": str(value.get("current_state") or ""),
        "stages": [
            {
                "state": str(row.get("state") or ""),
                "ready": row.get("ready") is True,
                "profile_count": _safe_int(row.get("profile_count")),
            }
            for row in stages[:8]
            if isinstance(row, Mapping)
            and str(row.get("state") or "") in PROVIDER_ONBOARDING_LIFECYCLE
        ],
    }


def _safe_probe_evidence(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    rows = value.get("profile_receipts") if isinstance(value.get("profile_receipts"), list) else []
    return {
        "probe_file_count": _safe_int(value.get("probe_file_count")),
        "probe_path_hashes": _normalized_hashes(value.get("probe_path_hashes"), limit=64),
        "probe_payload_count": _safe_int(value.get("probe_payload_count")),
        "profile_receipts": [
            {
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "api_format": str(row.get("api_format") or ""),
                "live_probe_row_count": _safe_int(row.get("live_probe_row_count")),
                "live_transport_attempt_row_count": _safe_int(
                    row.get("live_transport_attempt_row_count")
                ),
                "live_available_row_count": _safe_int(
                    row.get("live_available_row_count")
                ),
                "protocol_validated": row.get("protocol_validated") is True,
                "live_probed": row.get("live_probed") is True,
                "observed_latency_ms": _safe_nonnegative_float(
                    row.get("observed_latency_ms")
                ),
            }
            for row in rows[:64]
            if isinstance(row, Mapping)
            and _looks_like_sha256(row.get("profile_id_sha256"))
        ],
    }


def _safe_calibration_evidence(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    rows = value.get("profile_receipts") if isinstance(value.get("profile_receipts"), list) else []
    return {
        "calibration_file_count": _safe_int(value.get("calibration_file_count")),
        "calibration_path_hashes": _normalized_hashes(
            value.get("calibration_path_hashes"), limit=64
        ),
        "calibration_payload_count": _safe_int(value.get("calibration_payload_count")),
        "profile_receipts": [
            {
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "calibration_row_count": _safe_int(row.get("calibration_row_count")),
                "probe_signal_count": _safe_int(row.get("probe_signal_count")),
                "capability_axis_count": _safe_int(row.get("capability_axis_count")),
                "capability_calibrated": row.get("capability_calibrated") is True,
            }
            for row in rows[:64]
            if isinstance(row, Mapping)
            and _looks_like_sha256(row.get("profile_id_sha256"))
        ],
    }


def _safe_complementarity(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    rows = value.get("candidate_receipts") if isinstance(value.get("candidate_receipts"), list) else []
    return {
        "method": str(value.get("method") or ""),
        "assessed": value.get("assessed") is True,
        "active_pool_profile_count": _safe_int(value.get("active_pool_profile_count")),
        "candidate_receipts": [
            {
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "active_pool_profile_count": _safe_int(
                    row.get("active_pool_profile_count")
                ),
                "best_capability_similarity": _safe_unit_float(
                    row.get("best_capability_similarity")
                ),
                "capability_complementarity_estimate": _safe_unit_float(
                    row.get("capability_complementarity_estimate")
                ),
                "novel_capability_axis_count": _safe_int(
                    row.get("novel_capability_axis_count")
                ),
                "api_format_diversity_candidate": row.get(
                    "api_format_diversity_candidate"
                )
                is True,
            }
            for row in rows[:64]
            if isinstance(row, Mapping)
            and _looks_like_sha256(row.get("profile_id_sha256"))
        ],
        "heuristic_only": value.get("heuristic_only") is True,
        "not_a_model_quality_rank": value.get("not_a_model_quality_rank") is True,
        "not_a_benchmark_substitute": value.get("not_a_benchmark_substitute") is True,
    }


def _safe_shadow_routing_contract(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    return {
        "candidate_profiles_must_remain_disabled": value.get(
            "candidate_profiles_must_remain_disabled"
        )
        is True,
        "candidate_profiles_currently_enabled": _safe_int(
            value.get("candidate_profiles_currently_enabled")
        ),
        "serving_direct_route_eligible": value.get("serving_direct_route_eligible")
        is True,
        "terra_panel_eligible": value.get("terra_panel_eligible") is True,
        "pro_panel_eligible": value.get("pro_panel_eligible") is True,
        "live_probe_allowed": value.get("live_probe_allowed") is True,
        "shadow_or_offline_evaluation_required_before_approval": value.get(
            "shadow_or_offline_evaluation_required_before_approval"
        )
        is True,
        "automatic_panel_promotion": value.get("automatic_panel_promotion") is True,
    }


def _safe_application_contract(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    return {
        str(key): bool(raw)
        for key, raw in value.items()
        if str(key)
        in {
            "remote_api_only",
            "local_model_weights_loaded",
            "provider_calls_performed_by_assessment",
            "registry_mutated_by_assessment",
            "new_provider_auto_enabled",
            "new_provider_auto_enters_fusion_panel",
            "human_approval_required",
            "separate_registry_activation_required",
            "not_for_final_benchmark_claims",
            "automatic_registry_mutation",
            "automatic_panel_promotion",
            "requires_explicit_private_registry_output_path",
            "in_place_registry_overwrite_allowed",
            "candidate_profiles_enabled_by_this_artifact",
            "candidate_profiles_panel_eligible_before_apply",
            "candidate_profiles_become_eligible_only_after_apply",
            "provider_calls_performed",
            "source_registry_mutated_in_place",
            "output_registry_is_private_operator_configuration",
            "local_model_weights_loaded",
            "candidate_profiles_panel_eligible_after_apply",
        }
    }


def _next_lifecycle_state(
    *,
    configured_ready: bool,
    protocol_validated: bool,
    live_probed: bool,
    capability_calibrated: bool,
    complementarity_assessed: bool,
) -> str:
    for state, ready in (
        ("configured", configured_ready),
        ("protocol_validated", protocol_validated),
        ("live_probed", live_probed),
        ("capability_calibrated", capability_calibrated),
        ("shadow_candidate", complementarity_assessed),
    ):
        if not ready:
            return state
    return "shadow_candidate"


def _probe_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = []
    direct = payload.get("probes") if isinstance(payload.get("probes"), list) else []
    rows.extend(row for row in direct if isinstance(row, Mapping))
    report = payload.get("probe_report") if isinstance(payload.get("probe_report"), Mapping) else {}
    nested = report.get("probes") if isinstance(report.get("probes"), list) else []
    rows.extend(row for row in nested if isinstance(row, Mapping))
    return rows


def _probe_mode(payload: Mapping[str, Any]) -> str:
    report = payload.get("probe_report") if isinstance(payload.get("probe_report"), Mapping) else {}
    return str(payload.get("mode") or report.get("mode") or "").strip().lower()


def _probe_network_called(payload: Mapping[str, Any]) -> bool:
    report = payload.get("probe_report") if isinstance(payload.get("probe_report"), Mapping) else {}
    return (
        payload.get("network_calls_performed") is True
        or report.get("network_calls_performed") is True
    )


def _profile_hash_from_evidence(row: Mapping[str, Any]) -> str:
    hashed = str(row.get("profile_id_sha256") or "").strip().lower()
    if _looks_like_sha256(hashed):
        return hashed
    profile_id = str(row.get("profile_id") or "")
    return sha256_text(profile_id) if profile_id else ""


def _registry_enablement_digest(payload: Mapping[str, Any]) -> str:
    models = payload.get("models") if isinstance(payload.get("models"), list) else []
    rows = []
    for row in models:
        if not isinstance(row, Mapping):
            continue
        profile_id = f"{str(row.get('provider') or '')}/{str(row.get('model') or '')}"
        rows.append(
            {
                "profile_id_sha256": sha256_text(profile_id),
                "enabled": row.get("enabled") is not False,
            }
        )
    return sha256_text(stable_json(sorted(rows, key=lambda item: item["profile_id_sha256"])))


def _profile_set_sha256(profiles: Sequence[ModelProfile]) -> str:
    return sha256_text(
        stable_json(sorted(sha256_text(profile.profile_id) for profile in profiles))
    )


def _normalized_profile_hashes(value: Sequence[Any]) -> list[str]:
    return _normalized_hashes(value, limit=128)


def _normalized_hashes(value: Any, *, limit: int) -> list[str]:
    rows = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []
    safe = []
    for item in rows:
        text = str(item or "").strip().lower()
        if _looks_like_sha256(text) and text not in safe:
            safe.append(text)
        if len(safe) >= limit:
            break
    return sorted(safe)


def _contains_forbidden_raw_fields(value: Any) -> bool:
    forbidden = {
        "provider",
        "provider_name",
        "model",
        "model_id",
        "canonical_model_id",
        "base_url",
        "base_url_env",
        "api_key",
        "api_key_env",
        "prompt",
        "system_prompt",
        "source_locator",
        "reviewer_id",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key or "").strip().lower()
            if normalized in forbidden or normalized.endswith("_url"):
                return True
            if _contains_forbidden_raw_fields(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_raw_fields(item) for item in value)
    return False


def _load_json_objects(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        selected = Path(path)
        if not selected.exists() or not selected.is_file():
            continue
        try:
            payload = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def _safe_label(value: Any, *, default: str = "") -> str:
    text = "".join(
        char if char.isascii() and (char.islower() or char.isdigit() or char == "_") else "_"
        for char in str(value or "").strip().lower()
    ).strip("_")
    return text[:80] or default


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_nonnegative_float(value: Any) -> float | None:
    try:
        return round(max(0.0, float(value)), 6)
    except (TypeError, ValueError):
        return None


def _safe_unit_float(value: Any) -> float | None:
    parsed = _safe_nonnegative_float(value)
    return None if parsed is None else round(min(1.0, parsed), 6)


def _average(values: Sequence[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else round(sum(clean) / len(clean), 6)


def _looks_like_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _valid_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return False
    return True
