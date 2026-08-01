"""Endpoint-bound promotion of remote reasoning-transport capabilities.

Reasoning controls are operational wire capabilities. They are not a quality
ranking signal and must not be copied between similarly named provider
channels. This module applies a completed strict reasoning probe to a new
private registry only when the provider/model, protocol, endpoint hash, and
declared transport contract are all bound to the same cohort.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .latency_policy import PROVIDER_MAX_RESPONSE_LATENCY_MS
from .providers import (
    REASONING_PROBE_SCHEMA,
    REASONING_TRANSPORT_BINDING_SCHEMA,
    reasoning_transport_probe_binding,
)
from .registry import normalize_profile, validate_prefusion_registry_handoff
from .schemas import (
    ModelProfile,
    normalize_reasoning_budget_tokens,
    normalize_reasoning_effort,
    sha256_text,
    stable_json,
)


REASONING_TRANSPORT_RECONCILIATION_SCHEMA = (
    "axio_fusion_api.reasoning_transport_reconciliation.v1"
)


def build_reasoning_transport_reconciliation(
    *,
    source_registry_path: str | Path,
    calibration_registry_path: str | Path,
    reasoning_probe_path: str | Path,
) -> dict[str, Any]:
    """Build an endpoint-bound, private registry update without writing it.

    The source registry supplies the serving/ranking envelope. The calibration
    registry supplies only the already-derived reasoning status, while the
    probe independently proves that status. All three private artifacts must
    describe the same complete profile cohort. The returned receipt is safe to
    persist; ``updated_registry`` remains private operator configuration.
    """

    source_path = Path(source_registry_path)
    calibration_path = Path(calibration_registry_path)
    probe_path = Path(reasoning_probe_path)
    blockers: list[str] = []

    source_payload = _load_json_object(source_path, "reasoning_reconciliation_source")
    calibration_payload = _load_json_object(
        calibration_path,
        "reasoning_reconciliation_calibration",
    )
    probe_payload = _load_json_object(probe_path, "reasoning_reconciliation_probe")
    for payload in (source_payload, calibration_payload, probe_payload):
        blockers.extend(payload.get("_load_errors", []))

    source_registry = _payload_without_load_errors(source_payload)
    calibration_registry = _payload_without_load_errors(calibration_payload)
    probe = _payload_without_load_errors(probe_payload)
    source_profiles, _, source_errors = _registry_profile_index(source_registry)
    calibration_profiles, _, calibration_errors = _registry_profile_index(calibration_registry)
    blockers.extend(source_errors)
    blockers.extend(calibration_errors)

    if str(source_registry.get("schema") or "") != "axio_fusion_api.registry.v1":
        blockers.append("reasoning_reconciliation_source_registry_schema_invalid")
    if str(calibration_registry.get("schema") or "") != "axio_fusion_api.registry.v1":
        blockers.append("reasoning_reconciliation_calibration_registry_schema_invalid")
    if str(probe.get("schema") or "") != REASONING_PROBE_SCHEMA:
        blockers.append("reasoning_reconciliation_probe_schema_invalid")
    if str(probe.get("probe_kind") or "").strip().casefold() != "reasoning_transport":
        blockers.append("reasoning_reconciliation_probe_kind_invalid")
    if str(probe.get("mode") or "").strip().casefold() != "live":
        blockers.append("reasoning_reconciliation_probe_not_live")
    if probe.get("network_calls_performed") is not True:
        blockers.append("reasoning_reconciliation_probe_network_evidence_missing")
    timeout_seconds = _positive_float(probe.get("timeout_seconds"))
    if timeout_seconds is None or timeout_seconds > PROVIDER_MAX_RESPONSE_LATENCY_MS / 1000:
        blockers.append("reasoning_reconciliation_probe_timeout_invalid")

    source_ids = set(source_profiles)
    calibration_ids = set(calibration_profiles)
    if not source_ids:
        blockers.append("reasoning_reconciliation_source_profile_set_empty")
    if not calibration_ids:
        blockers.append("reasoning_reconciliation_calibration_profile_set_empty")
    if source_ids != calibration_ids:
        blockers.append("reasoning_reconciliation_registry_profile_set_mismatch")

    source_is_prefusion = source_registry.get("generated_from_prefusion_screening") is True
    source_prefusion_validation = (
        validate_prefusion_registry_handoff(source_registry, require_ready=True)
        if source_is_prefusion
        else _not_required_prefusion_validation()
    )
    if source_prefusion_validation.get("valid") is not True:
        blockers.append("reasoning_reconciliation_source_prefusion_handoff_invalid")

    candidate_ids: set[str] = set()
    for profile_id in sorted(source_ids.intersection(calibration_ids)):
        source_profile = source_profiles[profile_id]
        calibration_profile = calibration_profiles[profile_id]
        if _profile_identity_binding(source_profile) != _profile_identity_binding(
            calibration_profile
        ):
            blockers.append("reasoning_reconciliation_profile_identity_mismatch")
        source_contract = _transport_contract(source_profile)
        calibration_contract = _transport_contract(calibration_profile)
        if source_contract["status"] == "candidate":
            candidate_ids.add(profile_id)
            if not _valid_candidate_contract(source_contract):
                blockers.append("reasoning_reconciliation_source_candidate_contract_invalid")
            if _transport_contract_without_status(source_contract) != _transport_contract_without_status(
                calibration_contract
            ):
                blockers.append("reasoning_reconciliation_transport_contract_mismatch")
        elif source_contract != calibration_contract:
            blockers.append("reasoning_reconciliation_non_candidate_transport_changed")

    if not candidate_ids:
        blockers.append("reasoning_reconciliation_candidate_profiles_missing")

    probe_rows, probe_errors = _reasoning_probe_index(probe)
    blockers.extend(probe_errors)
    if set(probe_rows) != candidate_ids:
        blockers.append("reasoning_reconciliation_probe_candidate_set_mismatch")
    _validate_probe_selection(probe, candidate_count=len(candidate_ids), blockers=blockers)

    outcomes: dict[str, str] = {}
    for profile_id in sorted(candidate_ids):
        source_profile = source_profiles.get(profile_id)
        calibration_profile = calibration_profiles.get(profile_id)
        row = probe_rows.get(profile_id)
        if source_profile is None or calibration_profile is None or row is None:
            continue
        outcome, row_errors = _validate_probe_row(
            row,
            profile=source_profile,
            transport_contract=_transport_contract(source_profile),
        )
        blockers.extend(row_errors)
        if not outcome:
            continue
        if _transport_contract(calibration_profile)["status"] != outcome:
            blockers.append("reasoning_reconciliation_calibration_status_mismatch")
            continue
        outcomes[profile_id] = outcome

    if len(outcomes) != len(candidate_ids):
        blockers.append("reasoning_reconciliation_candidate_outcomes_incomplete")

    status_counts = {
        status: sum(1 for value in outcomes.values() if value == status)
        for status in ("verified", "unsupported", "candidate")
    }
    updated_registry: dict[str, Any] = {}
    output_prefusion_validation = _not_required_prefusion_validation()
    if not blockers:
        updated_registry = _updated_registry_payload(
            source_registry,
            source_profiles=source_profiles,
            outcomes=outcomes,
            source_registry_content_sha256=_content_sha256(source_registry),
            calibration_registry_content_sha256=_content_sha256(calibration_registry),
            reasoning_probe_content_sha256=_content_sha256(probe),
        )
        output_prefusion_validation = (
            validate_prefusion_registry_handoff(updated_registry, require_ready=True)
            if source_is_prefusion
            else _not_required_prefusion_validation()
        )
        if output_prefusion_validation.get("valid") is not True:
            blockers.append("reasoning_reconciliation_output_prefusion_handoff_invalid")
            updated_registry = {}

    ready = not blockers and bool(updated_registry)
    receipt = {
        "schema": REASONING_TRANSPORT_RECONCILIATION_SCHEMA,
        "status": "ready" if ready else "blocked",
        "source_registry_path_sha256": sha256_text(str(source_path)),
        "calibration_registry_path_sha256": sha256_text(str(calibration_path)),
        "reasoning_probe_path_sha256": sha256_text(str(probe_path)),
        "source_registry_content_sha256": _content_sha256(source_registry),
        "calibration_registry_content_sha256": _content_sha256(calibration_registry),
        "reasoning_probe_content_sha256": _content_sha256(probe),
        "source_registry_prefusion_bound": source_is_prefusion,
        "source_prefusion_validation": _safe_prefusion_validation(
            source_prefusion_validation
        ),
        "output_prefusion_validation": _safe_prefusion_validation(
            output_prefusion_validation
        ),
        "source_profile_count": len(source_profiles),
        "calibration_profile_count": len(calibration_profiles),
        "source_profile_set_sha256": _profile_set_sha256(source_profiles),
        "calibration_profile_set_sha256": _profile_set_sha256(calibration_profiles),
        "candidate_profile_count": len(candidate_ids),
        "candidate_profile_set_sha256": _profile_set_sha256(
            {profile_id: source_profiles[profile_id] for profile_id in candidate_ids if profile_id in source_profiles}
        ),
        "probe_profile_count": len(probe_rows),
        "endpoint_bound_probe_evidence_required": True,
        "endpoint_bound_profile_count": len(outcomes),
        "updated_profile_count": sum(
            1
            for profile_id, outcome in outcomes.items()
            if _transport_contract(source_profiles[profile_id])["status"] != outcome
        ),
        "outcome_status_counts": status_counts,
        "output_registry_content_sha256": _content_sha256(updated_registry)
        if ready
        else "",
        "registry_output_written": False,
        "registry_output_path_sha256": "",
        "blockers": sorted(set(str(item) for item in blockers if str(item))),
        "application_contract": {
            "source_registry_mutated_in_place": False,
            "output_registry_must_be_private_operator_configuration": True,
            "requires_exact_source_calibration_profile_set": True,
            "requires_complete_unbounded_candidate_probe_set": True,
            "requires_endpoint_bound_profile_transport_identity": True,
            "only_reasoning_transport_statuses_may_change": True,
            "does_not_change_model_ranking": True,
            "does_not_change_capability_scores": True,
            "does_not_change_benchmark_baseline_or_results": True,
            "provider_calls_performed_by_reconciliation": False,
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
    receipt["reconciliation_digest_sha256"] = sha256_text(
        stable_json(_receipt_digest_input(receipt))
    )
    return {"receipt": receipt, "updated_registry": updated_registry}


def apply_reasoning_transport_reconciliation(
    reconciliation: Mapping[str, Any],
    *,
    source_registry_path: str | Path,
    output_registry_path: str | Path,
) -> dict[str, Any]:
    """Atomically write a ready reconciliation to a distinct private path."""

    receipt = (
        dict(reconciliation.get("receipt"))
        if isinstance(reconciliation.get("receipt"), Mapping)
        else {}
    )
    updated_registry = (
        dict(reconciliation.get("updated_registry"))
        if isinstance(reconciliation.get("updated_registry"), Mapping)
        else {}
    )
    source = Path(source_registry_path)
    target = Path(output_registry_path)
    blockers = [str(item) for item in receipt.get("blockers", []) if str(item)]
    if receipt.get("status") != "ready" or not updated_registry:
        blockers.append("reasoning_reconciliation_not_ready_to_write")
    if not str(output_registry_path or "").strip():
        blockers.append("reasoning_reconciliation_output_registry_path_missing")
    if _same_path(source, target):
        blockers.append("reasoning_reconciliation_in_place_overwrite_forbidden")
    if blockers:
        return {
            **receipt,
            "status": "blocked",
            "registry_output_written": False,
            "registry_output_path_sha256": sha256_text(str(target)) if str(target) else "",
            "blockers": sorted(set(blockers)),
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(updated_registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        **receipt,
        "registry_output_written": True,
        "registry_output_path_sha256": sha256_text(str(target)),
    }


def _load_json_object(path: Path, prefix: str) -> dict[str, Any]:
    if not path.is_file():
        return {"_load_errors": [f"{prefix}_not_found"]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_load_errors": [f"{prefix}_invalid_json"]}
    if not isinstance(payload, Mapping):
        return {"_load_errors": [f"{prefix}_not_json_object"]}
    return dict(payload)


def _payload_without_load_errors(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "_load_errors"}


def _registry_profile_index(
    payload: Mapping[str, Any],
) -> tuple[dict[str, ModelProfile], dict[str, Mapping[str, Any]], list[str]]:
    rows = payload.get("models") if isinstance(payload.get("models"), list) else []
    profiles: dict[str, ModelProfile] = {}
    raw_rows: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    if not rows:
        errors.append("reasoning_reconciliation_registry_models_missing")
    for raw in rows:
        if not isinstance(raw, Mapping):
            errors.append("reasoning_reconciliation_registry_model_row_invalid")
            continue
        try:
            profile = normalize_profile(raw)
        except (TypeError, ValueError):
            errors.append("reasoning_reconciliation_registry_model_normalization_failed")
            continue
        profile_id = profile.profile_id
        declared_profile_id = str(raw.get("profile_id") or "").strip()
        if declared_profile_id and declared_profile_id != profile_id:
            errors.append("reasoning_reconciliation_registry_profile_identity_invalid")
        if not profile_id or profile_id in profiles:
            errors.append("reasoning_reconciliation_registry_profile_duplicate")
            continue
        profiles[profile_id] = profile
        raw_rows[profile_id] = raw
    return profiles, raw_rows, errors


def _reasoning_probe_index(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    rows = payload.get("probes") if isinstance(payload.get("probes"), list) else []
    indexed: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    if not rows:
        errors.append("reasoning_reconciliation_probe_rows_missing")
    for row in rows:
        if not isinstance(row, Mapping):
            errors.append("reasoning_reconciliation_probe_row_invalid")
            continue
        profile_id = str(row.get("profile_id") or "").strip()
        if not profile_id or profile_id in indexed:
            errors.append("reasoning_reconciliation_probe_profile_identity_invalid")
            continue
        indexed[profile_id] = row
    return indexed, errors


def _validate_probe_selection(
    probe: Mapping[str, Any],
    *,
    candidate_count: int,
    blockers: list[str],
) -> None:
    for field in ("candidate_model_count_before_selection", "model_count"):
        if _nonnegative_int(probe.get(field)) != candidate_count:
            blockers.append("reasoning_reconciliation_probe_selection_incomplete")
            break
    selection = probe.get("selection_policy")
    selection = selection if isinstance(selection, Mapping) else {}
    if (
        selection.get("profile_hash_filter_enabled") is not False
        or selection.get("max_models") is not None
        or selection.get("max_models_per_provider") is not None
        or _nonnegative_int(selection.get("selected_model_count")) != candidate_count
    ):
        blockers.append("reasoning_reconciliation_probe_selection_not_full_cohort")


def _validate_probe_row(
    row: Mapping[str, Any],
    *,
    profile: ModelProfile,
    transport_contract: Mapping[str, Any],
) -> tuple[str, list[str]]:
    errors: list[str] = []
    expected_binding = reasoning_transport_probe_binding(profile)
    observed_binding = (
        row.get("reasoning_transport_binding")
        if isinstance(row.get("reasoning_transport_binding"), Mapping)
        else {}
    )
    if expected_binding.get("endpoint_binding_ready") is not True:
        errors.append("reasoning_reconciliation_current_endpoint_unresolved")
    if str(observed_binding.get("schema") or "") != REASONING_TRANSPORT_BINDING_SCHEMA:
        errors.append("reasoning_reconciliation_probe_endpoint_binding_missing")
    elif _binding_digest(observed_binding) != str(observed_binding.get("binding_sha256") or ""):
        errors.append("reasoning_reconciliation_probe_endpoint_binding_digest_invalid")
    elif str(observed_binding.get("binding_sha256") or "") != str(
        expected_binding.get("binding_sha256") or ""
    ):
        errors.append("reasoning_reconciliation_probe_endpoint_binding_mismatch")
    if str(row.get("profile_id") or "") != profile.profile_id:
        errors.append("reasoning_reconciliation_probe_profile_mismatch")
    if str(row.get("provider") or "") != profile.provider or str(row.get("model") or "") != profile.model:
        errors.append("reasoning_reconciliation_probe_provider_model_mismatch")
    if str(row.get("api_format") or "") != str(expected_binding.get("api_format") or ""):
        errors.append("reasoning_reconciliation_probe_api_format_mismatch")
    if str(row.get("probe_kind") or "").strip().casefold() != "reasoning_transport":
        errors.append("reasoning_reconciliation_probe_row_kind_invalid")
    if str(row.get("probe_mode") or "").strip().casefold() != "live" or row.get("live_probe_evidence") is not True:
        errors.append("reasoning_reconciliation_probe_row_not_live")
    if row.get("strict_wire_shape_preserved") is not True:
        errors.append("reasoning_reconciliation_probe_wire_shape_invalid")
    if str(row.get("transport") or "") != str(transport_contract.get("transport") or ""):
        errors.append("reasoning_reconciliation_probe_transport_mismatch")
    if _normalized_efforts(row.get("declared_efforts")) != list(
        transport_contract.get("supported_efforts") or []
    ):
        errors.append("reasoning_reconciliation_probe_effort_set_mismatch")
    if _normalized_budgets(row.get("declared_budget_tokens")) != list(
        transport_contract.get("supported_budget_tokens") or []
    ):
        errors.append("reasoning_reconciliation_probe_budget_set_mismatch")
    if errors:
        return "", errors

    status = str(row.get("status") or "").strip().casefold()
    if status == "verified":
        if _verified_probe_row(
            row,
            transport_contract.get("supported_efforts") or [],
            transport_contract.get("supported_budget_tokens") or [],
        ):
            return "verified", errors
        return "", ["reasoning_reconciliation_verified_probe_evidence_invalid"]
    if status == "rejected":
        if _rejected_probe_row(row):
            return "unsupported", errors
        return "", ["reasoning_reconciliation_rejected_probe_evidence_invalid"]
    if status == "indeterminate":
        return "candidate", errors
    return "", ["reasoning_reconciliation_probe_status_invalid"]


def _verified_probe_row(
    row: Mapping[str, Any],
    efforts: Sequence[str],
    budgets: Sequence[int] = (),
) -> bool:
    if row.get("all_declared_efforts_strict_streaming") is not True:
        return False
    control = row.get("control") if isinstance(row.get("control"), Mapping) else {}
    if not _strict_attempt_accepted(control):
        return False
    by_effort = {
        normalize_reasoning_effort(item.get("effort")): item
        for item in row.get("effort_results", [])
        if isinstance(item, Mapping) and normalize_reasoning_effort(item.get("effort"))
    } if isinstance(row.get("effort_results"), list) else {}
    if not all(_strict_attempt_accepted(by_effort.get(effort, {})) for effort in efforts):
        return False
    if not budgets:
        return not _normalized_budgets(row.get("declared_budget_tokens"))
    if row.get("all_declared_budgets_strict_streaming") is not True:
        return False
    budget_rows = row.get("budget_results") if isinstance(row.get("budget_results"), list) else []
    by_budget = {
        budget: attempt
        for attempt in budget_rows
        if isinstance(attempt, Mapping)
        for budget in _normalized_budgets([attempt.get("budget_tokens")])
    }
    verified_budgets = set(_normalized_budgets(row.get("verified_budget_tokens")))
    return all(
        _strict_attempt_accepted(by_budget.get(budget, {}))
        or budget in verified_budgets
        for budget in budgets
    ) and row.get("all_declared_reasoning_controls_strict_streaming") is True


def _rejected_probe_row(row: Mapping[str, Any]) -> bool:
    control = row.get("control") if isinstance(row.get("control"), Mapping) else {}
    if not _strict_attempt_accepted(control):
        return False
    attempts: list[Any] = []
    if isinstance(row.get("effort_results"), list):
        attempts.extend(row.get("effort_results"))
    if isinstance(row.get("budget_results"), list):
        attempts.extend(row.get("budget_results"))
    return any(
        isinstance(item, Mapping)
        and str(item.get("status") or "").strip().casefold() == "rejected"
        and 400 <= _nonnegative_int(item.get("http_status")) < 500
        and _nonnegative_int(item.get("http_status")) not in {401, 403, 408, 429}
        for item in attempts
    )


def _strict_attempt_accepted(row: Mapping[str, Any]) -> bool:
    latency_ms = _positive_float(row.get("latency_ms"))
    return bool(
        str(row.get("status") or "").strip().casefold() == "accepted"
        and row.get("marker_observed") is True
        and row.get("strict_streaming_contract_valid") is True
        and row.get("stream_requested") is True
        and row.get("strict_streaming_requested") is True
        and row.get("stream_observed") is True
        and row.get("stream_fallback_used") is not True
        and str(row.get("stream_protocol") or "").strip().casefold()
        in {"sse", "ndjson"}
        and _nonnegative_int(row.get("stream_frame_count")) >= 1
        and latency_ms is not None
        and latency_ms <= PROVIDER_MAX_RESPONSE_LATENCY_MS
    )


def _updated_registry_payload(
    source_registry: Mapping[str, Any],
    *,
    source_profiles: Mapping[str, ModelProfile],
    outcomes: Mapping[str, str],
    source_registry_content_sha256: str,
    calibration_registry_content_sha256: str,
    reasoning_probe_content_sha256: str,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(dict(source_registry), ensure_ascii=False))
    models = payload.get("models") if isinstance(payload.get("models"), list) else []
    updated_models: list[dict[str, Any]] = []
    for raw in models:
        if not isinstance(raw, Mapping):
            continue
        updated = dict(raw)
        profile = normalize_profile(updated)
        status = outcomes.get(profile.profile_id)
        if status:
            transport = dict(source_profiles[profile.profile_id].reasoning_transport)
            transport["status"] = status
            if "reasoningTransport" in updated and "reasoning_transport" not in updated:
                updated["reasoningTransport"] = transport
            else:
                updated["reasoning_transport"] = transport
        updated_models.append(updated)
    payload["models"] = updated_models
    payload["calibrated"] = True
    payload["reasoning_transport_reconciliation"] = {
        "schema": REASONING_TRANSPORT_RECONCILIATION_SCHEMA,
        "status": "ready",
        "source_registry_content_sha256": source_registry_content_sha256,
        "calibration_registry_content_sha256": calibration_registry_content_sha256,
        "reasoning_probe_content_sha256": reasoning_probe_content_sha256,
        "source_profile_set_sha256": _profile_set_sha256(source_profiles),
        "candidate_profile_count": len(outcomes),
        "outcome_status_counts": {
            status: sum(1 for value in outcomes.values() if value == status)
            for status in ("verified", "unsupported", "candidate")
        },
        "endpoint_bound_profile_transport_identity": True,
        "only_reasoning_transport_statuses_changed": True,
        "model_ranking_changed": False,
        "benchmark_results_used": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }
    generation_contract = payload.get("generation_contract")
    generation_contract = dict(generation_contract) if isinstance(generation_contract, Mapping) else {}
    generation_contract.update(
        {
            "reasoning_transport_reconciliation_endpoint_bound": True,
            "reasoning_transport_reconciliation_does_not_change_ranking": True,
            "reasoning_transport_reconciliation_uses_benchmark_results": False,
        }
    )
    payload["generation_contract"] = generation_contract
    payload["raw_provider_urls_persisted"] = False
    payload["secrets_persisted"] = False
    return payload


def _profile_identity_binding(profile: ModelProfile) -> dict[str, Any]:
    binding = reasoning_transport_probe_binding(profile)
    return {
        "profile_id_sha256": binding["profile_id_sha256"],
        "canonical_identity_sha256": binding["canonical_identity_sha256"],
        "api_format": binding["api_format"],
        "auth_scheme": binding["auth_scheme"],
        "base_url_sha256": binding["base_url_sha256"],
        "endpoint_binding_ready": binding["endpoint_binding_ready"],
    }


def _transport_contract(profile: ModelProfile) -> dict[str, Any]:
    config = dict(profile.reasoning_transport) if isinstance(profile.reasoning_transport, Mapping) else {}
    return {
        "status": str(config.get("status") or "").strip().casefold(),
        "transport": str(config.get("transport") or "").strip().casefold(),
        "supported_efforts": _probe_efforts(config),
        "effort_map": _normalized_effort_map(config.get("effort_map")),
        "supported_budget_tokens": _normalized_budgets(
            config.get("supported_budget_tokens")
        ),
        "budget_tokens_by_effort": _normalized_budget_map(
            config.get("budget_tokens_by_effort")
        ),
        "api_format_compatible": config.get("api_format_compatible") is True,
    }


def _transport_contract_without_status(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "status"}


def _valid_candidate_contract(value: Mapping[str, Any]) -> bool:
    transport = str(value.get("transport") or "").strip().casefold()
    budget_transport = transport in {
        "anthropic_thinking",
        "gemini_thinking_config",
    }
    has_controls = bool(
        value.get("supported_budget_tokens")
        if budget_transport
        else value.get("supported_efforts")
    )
    return bool(
        value.get("status") == "candidate"
        and value.get("transport")
        and has_controls
        and (budget_transport or not value.get("supported_budget_tokens"))
        and value.get("api_format_compatible") is True
    )


def _normalized_efforts(value: Any) -> list[str]:
    values = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    normalized: list[str] = []
    for item in values:
        effort = normalize_reasoning_effort(item)
        if effort and effort not in normalized:
            normalized.append(effort)
    return normalized


def _normalized_effort_map(value: Any) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not isinstance(value, Mapping):
        return normalized
    for source, target in value.items():
        requested = normalize_reasoning_effort(source)
        effective = normalize_reasoning_effort(target)
        if requested and effective:
            normalized[requested] = effective
    return dict(sorted(normalized.items()))


def _probe_efforts(config: Mapping[str, Any]) -> list[str]:
    efforts = _normalized_efforts(config.get("supported_efforts"))
    transport = str(config.get("transport") or "").strip().casefold()
    if transport in {"anthropic_thinking", "gemini_thinking_config"}:
        budget_map = config.get("budget_tokens_by_effort")
        if isinstance(budget_map, Mapping):
            for raw_effort in budget_map:
                effort = normalize_reasoning_effort(raw_effort)
                if effort and effort not in efforts:
                    efforts.append(effort)
    return efforts


def _normalized_budgets(value: Any) -> list[int]:
    values = value if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ) else []
    budgets: list[int] = []
    for raw in values:
        budget = normalize_reasoning_budget_tokens(raw)
        if budget is not None and budget not in budgets:
            budgets.append(budget)
    return sorted(budgets)


def _normalized_budget_map(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, int] = {}
    for raw_effort, raw_budget in value.items():
        effort = normalize_reasoning_effort(raw_effort)
        budget = normalize_reasoning_budget_tokens(raw_budget)
        if effort and budget is not None:
            normalized[effort] = budget
    return dict(sorted(normalized.items()))


def _binding_digest(value: Mapping[str, Any]) -> str:
    return sha256_text(
        stable_json({key: item for key, item in value.items() if key != "binding_sha256"})
    )


def _profile_set_sha256(profiles: Mapping[str, ModelProfile]) -> str:
    return sha256_text(stable_json(sorted(sha256_text(profile_id) for profile_id in profiles)))


def _content_sha256(payload: Mapping[str, Any]) -> str:
    return sha256_text(stable_json(dict(payload))) if payload else ""


def _safe_prefusion_validation(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "required": value.get("required") is True,
        "valid": value.get("valid") is True,
        "reason_code_count": len(value.get("reason_codes") or []),
        "reason_codes": [
            str(item)[:120] for item in value.get("reason_codes", []) if str(item)
        ],
    }


def _not_required_prefusion_validation() -> dict[str, Any]:
    return {"required": False, "valid": True, "reason_codes": []}


def _receipt_digest_input(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in receipt.items()
        if key
        not in {
            "registry_output_written",
            "registry_output_path_sha256",
            "reconciliation_digest_sha256",
        }
    }


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
