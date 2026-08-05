"""Provider-channel enrollment for the standalone Fusion service.

This module is operational glue rather than routing logic. It turns a
non-secret channel manifest plus process-local credentials into a probe-bound
serving registry. Endpoint and API key values remain in the environment (or an
external secret manager) and never enter the returned receipt.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from .calibration import build_registry_calibration
from .channel_config import discover_runtime_profiles, runtime_channel_summary
from .latency_policy import (
    PROVIDER_MAX_RESPONSE_LATENCY_MS,
    PROVIDER_MAX_RESPONSE_SECONDS,
    measured_stream_latency_eligibility,
    row_latency_eligibility,
    streaming_evidence_eligibility,
)
from .model_screening import (
    apply_prefusion_handoff_metadata,
    build_prefusion_fusion_handoff,
    run_prefusion_model_screening,
)
from .orchestrator import FusionEngine
from .providers import (
    HTTPProviderClient,
    REASONING_TRANSPORT_BINDING_SCHEMA,
    ensure_strict_streaming_client,
    probe_exposed_provider_models,
    probe_provider_models,
    probe_provider_reasoning_support,
    probe_provider_tool_support,
    reasoning_transport_probe_binding,
)
from .vision_probe import probe_provider_vision_support, vision_input_probe_status
from .registry import (
    build_registry_from_probe_artifacts,
    load_registry,
    provider_configuration_source_summary,
    registry_readiness,
)
from .schemas import (
    ModelProfile,
    is_sha256_digest,
    normalize_reasoning_budget_tokens,
    normalize_reasoning_effort,
    sha256_text,
    stable_json,
)
from .schemas import logical_model_count


_ENROLLMENT_SCHEMA = "axio_fusion_api.provider_enrollment.v1"


def enroll_runtime_channels(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    environment: Mapping[str, Any] | None = None,
    secret_resolver: Any | None = None,
    timeout: float = 60.0,
    max_workers: int = 8,
    max_models: int | None = None,
    max_models_per_provider: int | None = None,
    min_available_models: int = 1,
    calibrate_tools: bool = True,
    tool_probe_timeout: float | None = None,
    tool_probe_max_models: int | None = None,
    tool_probe_max_models_per_provider: int | None = None,
    calibrate_reasoning: bool = True,
    reasoning_probe_timeout: float | None = None,
    reasoning_probe_max_models: int | None = None,
    reasoning_probe_max_models_per_provider: int | None = None,
    calibrate_vision: bool = True,
    vision_probe_timeout: float | None = None,
    vision_probe_max_models: int | None = None,
    vision_probe_max_models_per_provider: int | None = None,
    live: bool = True,
    client: HTTPProviderClient | None = None,
    engine_kwargs: Mapping[str, Any] | None = None,
    require_prefusion: bool = False,
    diagnostic_only: bool = False,
    focus_manifest: Mapping[str, Any] | str | Path | None = None,
    source_manifest: Mapping[str, Any] | str | Path | None = None,
    research_agent_config: Mapping[str, Any] | str | Path | None = None,
    research_output: Mapping[str, Any] | str | Path | None = None,
    prefusion_max_models: int | None = None,
    prefusion_research_batch_size: int | None = None,
    prefusion_research_max_workers: int | None = None,
    prefusion_stream_probe_samples: int | None = None,
    prefusion_role_probe_samples_per_role: int | None = None,
    prefusion_total_budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Discover and enroll arbitrary direct-credential channels in memory.

    Unlike :func:`enroll_provider_channels`, this path never writes a private
    registry or probe payload. It is intended for a process that receives
    literal credentials from a secret manager, performs bounded discovery and
    probes, and immediately serves the resulting in-memory engine. The return
    value contains a safe receipt plus live ``profiles``/``engine`` objects for
    the caller; only the receipt is suitable for serialization.

    Unless ``diagnostic_only=True`` is explicit, this function treats runtime
    enrollment as a production admission boundary. Discovery is only an
    inventory step, and the profiles must pass the remote research ranking and
    the real streaming probe in :func:`run_prefusion_model_screening` before
    they can reach the engine. The diagnostic escape hatch is reserved for
    fixtures and operational inspection that intentionally do not provide the
    pre-Fusion configuration.
    """

    started = time.monotonic()
    bounded_timeout = max(1.0, min(300.0, float(timeout)))
    bounded_workers = max(1, min(32, int(max_workers or 1)))
    bounded_tool_timeout = max(
        1.0,
        min(
            300.0,
            float(tool_probe_timeout)
            if tool_probe_timeout is not None
            else min(bounded_timeout, 20.0),
        ),
    )
    bounded_reasoning_timeout = max(
        1.0,
        min(
            PROVIDER_MAX_RESPONSE_SECONDS,
            float(reasoning_probe_timeout)
            if reasoning_probe_timeout is not None
            else min(bounded_timeout, 20.0),
        ),
    )
    bounded_vision_timeout = max(
        1.0,
        min(
            PROVIDER_MAX_RESPONSE_SECONDS,
            float(vision_probe_timeout)
            if vision_probe_timeout is not None
            else min(bounded_timeout, 20.0),
        ),
    )
    prefusion_config, prefusion_declared = _prefusion_config_from_manifest(manifest)
    focus_manifest = focus_manifest if focus_manifest is not None else _prefusion_value(
        prefusion_config, "focus_manifest", "focus", "focus_path"
    )
    source_manifest = source_manifest if source_manifest is not None else _prefusion_value(
        prefusion_config, "source_manifest", "sources", "source_path"
    )
    research_agent_config = (
        research_agent_config
        if research_agent_config is not None
        else _prefusion_value(
            prefusion_config,
            "research_agent_config",
            "research_agent",
            "research_agent_path",
        )
    )
    research_output = research_output if research_output is not None else _prefusion_value(
        prefusion_config, "research_output", "research_output_path"
    )
    configured_prefusion_max_models = _optional_positive_int(
        prefusion_max_models
        if prefusion_max_models is not None
        else _prefusion_value(prefusion_config, "max_models", "candidate_limit")
    )
    configured_research_batch_size = _optional_positive_int(
        prefusion_research_batch_size
        if prefusion_research_batch_size is not None
        else _prefusion_value(
            prefusion_config,
            "candidate_batch_size",
            "research_batch_size",
            "batch_size",
        )
    )
    configured_research_max_workers = _optional_positive_int(
        prefusion_research_max_workers
        if prefusion_research_max_workers is not None
        else _prefusion_value(
            prefusion_config,
            "research_max_workers",
            "batch_max_workers",
        )
    )
    configured_stream_probe_samples = _optional_positive_int(
        prefusion_stream_probe_samples
        if prefusion_stream_probe_samples is not None
        else _prefusion_value(
            prefusion_config,
            "stream_probe_samples",
            "stability_probe_samples",
            "probe_samples",
        )
    ) or 3
    configured_role_probe_samples = _optional_positive_int(
        prefusion_role_probe_samples_per_role
        if prefusion_role_probe_samples_per_role is not None
        else _prefusion_value(
            prefusion_config,
            "role_probe_samples_per_role",
            "role_probe_samples",
        )
    ) or 2
    configured_total_budget_seconds = (
        prefusion_total_budget_seconds
        if prefusion_total_budget_seconds is not None
        else _prefusion_value(
            prefusion_config,
            "total_budget_seconds",
            "budget_seconds",
            "wall_clock_budget_seconds",
        )
    )
    prefusion_min_available_models = _optional_positive_int(
        _prefusion_value(prefusion_config, "min_available_models")
    ) or max(1, int(min_available_models))
    prefusion_required = bool(
        require_prefusion
        or prefusion_declared
        or not diagnostic_only
    )
    # The diagnostic escape hatch deliberately retains the legacy compatibility
    # client. Every production enrollment path receives a strict client so the
    # text probe, tool calibration, and the activated Fusion engine share the
    # same framed-stream transport contract.
    active_client = (
        ensure_strict_streaming_client(client)
        if prefusion_required
        else (client or HTTPProviderClient())
    )
    admission_mode = (
        "prefusion_production"
        if prefusion_required
        else "diagnostic_stream_probe"
    )
    if not live:
        return {
            "status": "blocked",
            "profiles": (),
            "engine": None,
            "receipt": {
                "schema": "axio_fusion_api.runtime_channel_enrollment.v1",
                "status": "blocked",
                "admission_mode": admission_mode,
                "production_admission": admission_mode == "prefusion_production",
                "diagnostic_only": bool(diagnostic_only),
                "reason_codes": ["live_flag_required_for_runtime_enrollment"],
                "network_calls_performed": False,
                "secrets_persisted": False,
            },
        }

    discovery = discover_runtime_profiles(
        manifest,
        environment=environment,
        secret_resolver=secret_resolver,
        timeout=min(bounded_timeout, 30.0),
    )
    discovered_profiles = list(discovery.get("profiles") or [])
    discovery_warning_codes = [
        str(item)[:120]
        for item in discovery.get("warning_codes", [])
        if str(item)
    ] if isinstance(discovery.get("warning_codes"), list) else []
    prefusion_report: dict[str, Any] = {}
    prefusion_summary = _empty_prefusion_summary(required=prefusion_required)
    reasoning_probe: dict[str, Any] = {}
    reasoning_probe_source = "not_run"
    if prefusion_required:
        prefusion_report = run_prefusion_model_screening(
            profiles=discovered_profiles,
            focus_manifest=focus_manifest,
            source_manifest=source_manifest,
            research_agent_config=research_agent_config,
            research_output=research_output,
            live=True,
            timeout=bounded_timeout,
            source_timeout=min(bounded_timeout, 30.0),
            max_workers=bounded_workers,
            max_models=configured_prefusion_max_models,
            min_available_models=prefusion_min_available_models,
            research_batch_size=configured_research_batch_size,
            research_max_workers=configured_research_max_workers,
            stream_probe_samples=configured_stream_probe_samples,
            role_probe_samples_per_role=configured_role_probe_samples,
            total_budget_seconds=configured_total_budget_seconds,
            provider_client=active_client,
            research_client=active_client,
        )
        handoff_boundary = build_prefusion_fusion_handoff(
            prefusion_report,
            require_ready=True,
        )
        handoff_validation = handoff_boundary.get("validation", {})
        if handoff_boundary.get("status") != "ready":
            prefusion_report = {
                **prefusion_report,
                "status": "blocked",
                "blockers": sorted(
                    set(
                        [
                            *list(prefusion_report.get("blockers") or []),
                            "prefusion_handoff_contract_invalid",
                        ]
                    )
                ),
                "handoff_validation": handoff_validation,
            }
        prefusion_profiles = _profiles_bound_to_prefusion_report(
            discovered_profiles,
            prefusion_report,
        )
        # The report is a private control-plane handoff, while dynamic
        # enrollment must keep its runtime credentials on the discovered
        # profiles.  Apply only the non-secret ranking projections so Fusion
        # sees the same role/rank/latency policy as a file-backed registry.
        prefusion_profiles = apply_prefusion_handoff_metadata(
            prefusion_profiles,
            prefusion_report,
        )
        probe = _prefusion_probe_payload(prefusion_report)
        reasoning_probe = _prefusion_reasoning_probe_payload(prefusion_report)
        reasoning_probe_source = "prefusion_screening"
        probe_rows = [row for row in probe.get("probes", []) if isinstance(row, Mapping)]
        calibrated_profiles = [
            replace(profile, health="available", source="prefusion_stream_probe")
            for profile in prefusion_profiles
        ]
        prefusion_summary = _prefusion_receipt_summary(prefusion_report)
    else:
        probe = probe_provider_models(
            discovered_profiles,
            timeout=bounded_timeout,
            client=active_client,
            live=True,
            max_workers=bounded_workers,
            max_models=max_models,
            max_models_per_provider=max_models_per_provider,
        )
        probe_rows = [row for row in probe.get("probes", []) if isinstance(row, Mapping)]
        calibrated_profiles = _apply_runtime_text_probe(discovered_profiles, probe_rows)
    tool_probe: dict[str, Any] = {}
    if calibrate_tools:
        available_profiles = [
            profile for profile in calibrated_profiles if profile.health == "available"
        ]
        tool_probe = probe_provider_tool_support(
            available_profiles,
            timeout=bounded_tool_timeout,
            client=active_client,
            live=True,
            max_workers=bounded_workers,
            max_models=tool_probe_max_models,
            max_models_per_provider=tool_probe_max_models_per_provider,
        )
        calibrated_profiles = _apply_runtime_tool_probe(
            calibrated_profiles,
            [row for row in tool_probe.get("probes", []) if isinstance(row, Mapping)],
        )
    if calibrate_reasoning and not prefusion_required:
        available_profiles = [
            profile for profile in calibrated_profiles if profile.health == "available"
        ]
        reasoning_probe = probe_provider_reasoning_support(
            available_profiles,
            timeout=bounded_reasoning_timeout,
            client=active_client,
            live=True,
            max_workers=bounded_workers,
            max_models=reasoning_probe_max_models,
            max_models_per_provider=reasoning_probe_max_models_per_provider,
        )
        calibrated_profiles = _apply_runtime_reasoning_probe(
            calibrated_profiles,
            [
                row
                for row in reasoning_probe.get("probes", [])
                if isinstance(row, Mapping)
            ],
        )
        reasoning_probe_source = "runtime_diagnostic"
    vision_probe: dict[str, Any] = {}
    if calibrate_vision:
        available_profiles = [
            profile for profile in calibrated_profiles if profile.health == "available"
        ]
        vision_probe = probe_provider_vision_support(
            available_profiles,
            timeout=bounded_vision_timeout,
            client=active_client,
            live=True,
            max_workers=bounded_workers,
            max_models=vision_probe_max_models,
            max_models_per_provider=vision_probe_max_models_per_provider,
        )
        calibrated_profiles = _apply_runtime_vision_probe(
            calibrated_profiles,
            [
                row
                for row in vision_probe.get("probes", [])
                if isinstance(row, Mapping)
            ],
        )
    serving_profiles = [
        profile for profile in calibrated_profiles if profile.health == "available"
    ]
    serving_logical_model_count = logical_model_count(serving_profiles)
    screening_ready = not prefusion_required or (
        str(prefusion_report.get("status") or "").strip().casefold() == "ready"
        and prefusion_summary.get("status") == "ready"
        and serving_logical_model_count >= prefusion_min_available_models
    )
    if prefusion_required and not screening_ready:
        serving_profiles = []
    ready = screening_ready and serving_logical_model_count >= max(1, int(min_available_models))
    engine = (
        FusionEngine(
            serving_profiles,
            client=active_client,
            **dict(engine_kwargs or {}),
        )
        if serving_profiles
        else None
    )
    receipt = {
        "schema": "axio_fusion_api.runtime_channel_enrollment.v1",
        "status": "ready" if ready else "blocked",
        "admission_mode": admission_mode,
        "production_admission": admission_mode == "prefusion_production",
        "diagnostic_only": bool(diagnostic_only),
        "network_calls_performed": True,
        "discovery_status": str(discovery.get("status") or "unknown")[:40],
        "discovery_provider_count": max(0, int(discovery.get("provider_count") or 0)),
        "discovery_successful_provider_count": max(
            0, int(discovery.get("successful_provider_count") or 0)
        ),
        "discovery_failed_provider_count": max(
            0, int(discovery.get("failed_provider_count") or 0)
        ),
        "discovery_skipped_provider_count": max(
            0, int(discovery.get("skipped_provider_count") or 0)
        ),
        "discovery_empty_success_provider_count": max(
            0, int(discovery.get("empty_success_provider_count") or 0)
        ),
        "discovery_report_status_counts": {
            str(key)[:40]: max(0, int(value or 0))
            for key, value in (
                discovery.get("report_status_counts", {}).items()
                if isinstance(discovery.get("report_status_counts"), Mapping)
                else []
            )
        },
        "discovery_warning_codes": sorted(set(discovery_warning_codes)),
        "discovered_profile_count": len(discovered_profiles),
        "probed_profile_count": len(probe_rows),
        "available_profile_count": len(serving_profiles),
        "available_logical_model_count": serving_logical_model_count,
        "unavailable_profile_count": max(0, len(calibrated_profiles) - len(serving_profiles)),
        "minimum_available_models": max(1, int(min_available_models)),
        "prefusion": prefusion_summary,
        "text_probe_available_count": sum(1 for row in probe_rows if row.get("status") == "available"),
        "text_probe_failure_count": sum(1 for row in probe_rows if row.get("status") != "available"),
        "tool_probe_enabled": bool(calibrate_tools),
        "tool_probe_timeout_seconds": bounded_tool_timeout if calibrate_tools else None,
        "tool_probe_max_models": (
            max(0, int(tool_probe_max_models))
            if tool_probe_max_models is not None
            else None
        ),
        "tool_probe_max_models_per_provider": (
            max(0, int(tool_probe_max_models_per_provider))
            if tool_probe_max_models_per_provider is not None
            else None
        ),
        "tool_probe_selected_model_count": int(tool_probe.get("model_count") or 0),
        "tool_probe_supported_count": int(tool_probe.get("tool_call_supported_count") or 0),
        "tool_probe_text_only_count": int(tool_probe.get("text_only_count") or 0),
        "tool_probe_failure_count": sum(
            1
            for row in tool_probe.get("probes", [])
            if isinstance(row, Mapping)
            and str(row.get("status") or "") not in {"tool_call_supported", "text_only"}
        ),
        "reasoning_probe_enabled": bool(calibrate_reasoning),
        "reasoning_probe_source": reasoning_probe_source,
        "reasoning_probe_reused_from_prefusion": reasoning_probe_source == "prefusion_screening",
        "reasoning_probe_timeout_seconds": (
            bounded_reasoning_timeout if calibrate_reasoning else None
        ),
        "reasoning_probe_max_models": (
            max(0, int(reasoning_probe_max_models))
            if reasoning_probe_max_models is not None
            else None
        ),
        "reasoning_probe_max_models_per_provider": (
            max(0, int(reasoning_probe_max_models_per_provider))
            if reasoning_probe_max_models_per_provider is not None
            else None
        ),
        "reasoning_probe_selected_model_count": int(reasoning_probe.get("model_count") or 0),
        "reasoning_probe_verified_count": int(reasoning_probe.get("verified_count") or 0),
        "reasoning_probe_rejected_count": int(reasoning_probe.get("rejected_count") or 0),
        "reasoning_probe_indeterminate_count": int(reasoning_probe.get("indeterminate_count") or 0),
        "vision_probe_enabled": bool(calibrate_vision),
        "vision_probe_timeout_seconds": bounded_vision_timeout if calibrate_vision else None,
        "vision_probe_max_models": (
            max(0, int(vision_probe_max_models))
            if vision_probe_max_models is not None
            else None
        ),
        "vision_probe_max_models_per_provider": (
            max(0, int(vision_probe_max_models_per_provider))
            if vision_probe_max_models_per_provider is not None
            else None
        ),
        "vision_probe_selected_model_count": int(vision_probe.get("model_count") or 0),
        "vision_probe_passed_count": int(vision_probe.get("passed_count") or 0),
        "vision_probe_failed_count": int(vision_probe.get("failed_count") or 0),
        "vision_probe_unsupported_count": int(vision_probe.get("unsupported_count") or 0),
        "vision_probe_indeterminate_count": int(vision_probe.get("indeterminate_count") or 0),
        "vision_probe_latency_ineligible_count": int(
            vision_probe.get("latency_ineligible_count") or 0
        ),
        "runtime_channel_summary": runtime_channel_summary(serving_profiles),
        "profile_set_sha256": sha256_text(
            stable_json(sorted(sha256_text(profile.profile_id) for profile in serving_profiles))
        ),
        "reason_codes": (
            []
            if ready
            else sorted(
                set(
                    [
                        *(
                            str(item)[:120]
                            for item in prefusion_report.get("blockers", [])
                            if str(item)
                        ),
                        "prefusion_screening_blocked"
                        if prefusion_required and not screening_ready
                        else "insufficient_live_available_profiles",
                    ]
                )
            )
        ),
        "warning_codes": sorted(set(discovery_warning_codes)),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_provider_outputs_persisted": False,
        "raw_probe_prompts_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }
    return {
        "status": receipt["status"],
        "profiles": tuple(serving_profiles),
        "engine": engine,
        "receipt": receipt,
    }


def _prefusion_config_from_manifest(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Read the non-secret pre-Fusion block without touching provider rows."""

    if not isinstance(manifest, Mapping):
        return {}, False
    for key in ("prefusion", "pre_fusion", "preFusion"):
        if key not in manifest:
            continue
        value = manifest.get(key)
        if value is None:
            return {}, True
        if not isinstance(value, Mapping):
            raise ValueError("runtime manifest prefusion block must be an object")
        return {str(name): item for name, item in value.items()}, True
    return {}, False


def _prefusion_value(config: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in config and config.get(key) not in (None, ""):
            return config.get(key)
    return None


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _empty_prefusion_summary(*, required: bool) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.runtime_prefusion_receipt.v1",
        "required": bool(required),
        "status": "not_requested" if not required else "not_run",
        "candidate_logical_model_count": 0,
        "ranked_logical_model_count": 0,
        "available_logical_model_count": 0,
        "eligible_physical_profile_count": 0,
        "available_model_list_sha256": "",
        "registry_content_sha256": "",
        "research_status": "not_run",
        "research_output_sha256": "",
        "stream_request_count": 0,
        "stream_observed_count": 0,
        "stream_fallback_count": 0,
        "latency_ceiling_ms": 90_000,
        "ranking_prior_only": True,
        "live_stream_gate_required": True,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _prefusion_probe_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = report.get("streaming_probe") if isinstance(report, Mapping) else {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _prefusion_reasoning_probe_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the reasoning receipt already produced by pre-Fusion screening."""

    payload = report.get("reasoning_probe") if isinstance(report, Mapping) else {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _profiles_bound_to_prefusion_report(
    profiles: Sequence[ModelProfile],
    report: Mapping[str, Any],
) -> list[ModelProfile]:
    """Resolve exact physical profiles and bind fresh streaming evidence.

    The returned objects remain the process-local profiles produced by channel
    discovery, so their runtime endpoint and credential fields are preserved
    only in memory.  Probe measurements and health are copied from the
    hash-bound screening report; provider/model aliases are never used as a
    substitute for the physical profile hash.
    """

    if str(report.get("status") or "").strip().casefold() != "ready":
        return []
    registry = report.get("fusion_registry")
    if not isinstance(registry, Mapping) or registry.get("binding_status") != "ready":
        return []
    handoff = report.get("fusion_handoff")
    if not isinstance(handoff, Mapping) or handoff.get("status") != "ready":
        return []
    binding = registry.get("prefusion_screening")
    bindings = binding.get("eligible_profile_bindings") if isinstance(binding, Mapping) else None
    models = registry.get("models")
    if not isinstance(bindings, list) or not isinstance(models, list) or not bindings:
        return []

    binding_hashes: set[str] = set()
    for row in bindings:
        if not isinstance(row, Mapping):
            return []
        profile_hash = str(row.get("profile_id_sha256") or "").strip().lower()
        if (
            not is_sha256_digest(profile_hash)
            or profile_hash in binding_hashes
            or str(row.get("status") or "") != "available"
            or str(row.get("probe_mode") or "").strip().casefold() != "live"
            or row.get("live_probe_evidence") is not True
            or row.get("stream_requested") is not True
            or row.get("stream_observed") is not True
            or row.get("stream_fallback_used") is True
            or not is_sha256_digest(row.get("output_sha256"))
            or streaming_evidence_eligibility(row).get("eligible") is not True
            or measured_stream_latency_eligibility(row).get("eligible") is not True
        ):
            return []
        latency = row.get("latency_eligibility")
        if not isinstance(latency, Mapping) or latency.get("eligible") is not True:
            return []
        binding_hashes.add(profile_hash)

    registry_hashes: set[str] = set()
    for row in models:
        if not isinstance(row, Mapping):
            return []
        profile_id = str(row.get("profile_id") or "").strip()
        if not profile_id:
            return []
        registry_hashes.add(sha256_text(profile_id).lower())
    if registry_hashes != binding_hashes:
        return []

    probe_rows = report.get("streaming_probe")
    probe_rows = probe_rows.get("probes") if isinstance(probe_rows, Mapping) else None
    probe_by_profile_id = {
        str(row.get("profile_id") or ""): row
        for row in (probe_rows if isinstance(probe_rows, list) else [])
        if isinstance(row, Mapping) and str(row.get("profile_id") or "")
    }
    selected: list[ModelProfile] = []
    seen: set[str] = set()
    for profile in profiles:
        profile_hash = sha256_text(profile.profile_id).lower()
        if profile_hash not in binding_hashes or profile_hash in seen:
            continue
        probe = probe_by_profile_id.get(profile.profile_id)
        if not isinstance(probe, Mapping):
            return []
        try:
            observed_latency_ms = int(round(float(probe.get("latency_ms"))))
        except (TypeError, ValueError):
            return []
        if observed_latency_ms < 0:
            return []
        selected.append(
            replace(
                profile,
                p50_latency_ms=observed_latency_ms,
                p95_latency_ms=observed_latency_ms,
                recent_success_rate=1.0,
                availability=1.0,
                observed_success_count=max(1, profile.observed_success_count) + 1,
                health="available",
                enabled=True,
                source="prefusion_stream_probe",
            )
        )
        seen.add(profile_hash)
    return selected if len(seen) == len(binding_hashes) else []


def _prefusion_receipt_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project screening into a safe runtime receipt without model aliases."""

    summary = _empty_prefusion_summary(required=True)
    ranking = report.get("research_ranking") if isinstance(report, Mapping) else {}
    ranking = ranking if isinstance(ranking, Mapping) else {}
    research_receipt = ranking.get("research_receipt")
    research_receipt = research_receipt if isinstance(research_receipt, Mapping) else {}
    probe = _prefusion_probe_payload(report)
    registry = report.get("fusion_registry") if isinstance(report, Mapping) else {}
    registry = registry if isinstance(registry, Mapping) else {}
    binding = registry.get("prefusion_screening")
    binding = binding if isinstance(binding, Mapping) else {}
    available = report.get("available_model_list")
    if not isinstance(available, list):
        available = binding.get("available_model_list")
    if not isinstance(available, list):
        available = []
    handoff = report.get("fusion_handoff")
    handoff = handoff if isinstance(handoff, Mapping) else {}
    summary.update(
        {
            "status": (
                "ready"
                if str(report.get("status") or "").strip().casefold() == "ready"
                and str(handoff.get("status") or "").strip().casefold() == "ready"
                else "blocked"
            ),
            "candidate_logical_model_count": max(
                0,
                int((report.get("candidate_inventory") or {}).get("logical_model_count") or 0),
            ),
            "ranked_logical_model_count": max(0, int(ranking.get("candidate_count") or 0)),
            "available_logical_model_count": len(available),
            "eligible_physical_profile_count": max(0, int(binding.get("eligible_profile_count") or 0)),
            "available_model_list_sha256": sha256_text(stable_json(available)) if available else "",
            "registry_content_sha256": sha256_text(stable_json(registry)) if registry else "",
            "research_status": str(research_receipt.get("status") or ranking.get("status") or "unknown")[:40],
            "research_output_sha256": str(research_receipt.get("output_sha256") or "")
            if is_sha256_digest(research_receipt.get("output_sha256"))
            else "",
            "stream_request_count": max(0, int(probe.get("stream_requested_count") or 0)),
            "stream_observed_count": max(0, int(probe.get("stream_observed_count") or 0)),
            "stream_fallback_count": max(0, int(probe.get("stream_fallback_count") or 0)),
        }
    )
    return summary


def _apply_runtime_text_probe(
    profiles: Sequence[ModelProfile],
    rows: Sequence[Mapping[str, Any]],
) -> list[ModelProfile]:
    rows_by_profile = {
        str(row.get("profile_id") or ""): row
        for row in rows
        if str(row.get("profile_id") or "")
    }
    calibrated: list[ModelProfile] = []
    for profile in profiles:
        row = rows_by_profile.get(profile.profile_id)
        if row is None:
            calibrated.append(replace(profile, health="unavailable", source="runtime_channel_probe_missing"))
            continue
        status = str(row.get("status") or "failed")
        latency = _safe_probe_latency(row.get("latency_ms"))
        success = status == "available" and row_latency_eligibility(row).get("eligible") is not False
        calibrated.append(
            replace(
                profile,
                health="available" if success else "unavailable",
                p50_latency_ms=latency or profile.p50_latency_ms,
                p95_latency_ms=latency or profile.p95_latency_ms,
                recent_success_rate=1.0 if success else 0.0,
                observed_success_count=1 if success else 0,
                observed_failure_count=0 if success else 1,
                source=(
                    "runtime_channel_live_probe"
                    if success
                    else "runtime_channel_probe_latency_ineligible"
                    if status == "available"
                    else "runtime_channel_live_probe"
                ),
            )
        )
    return calibrated


def _apply_runtime_tool_probe(
    profiles: Sequence[ModelProfile],
    rows: Sequence[Mapping[str, Any]],
) -> list[ModelProfile]:
    """Apply only evidence for profiles actually selected by this probe.

    A bounded probe samples only part of a large portfolio.  Consequently an
    absent row means ``not_run``, not failure.  A failed row records negative
    operational evidence, while an explicit external attestation is retained
    in ``supports_tools`` so a transient probe failure cannot silently erase a
    declared capability.  Routing can use ``tool_capability`` to avoid treating
    an unproven or failed profile as a tool specialist.
    """

    rows_by_profile = {
        str(row.get("profile_id") or ""): row
        for row in rows
        if str(row.get("profile_id") or "")
    }
    updated: list[ModelProfile] = []
    for profile in profiles:
        row = rows_by_profile.get(profile.profile_id)
        if row is None:
            updated.append(profile)
            continue
        status = str(row.get("status") or "probe_failed").strip().lower()
        if status == "tool_call_supported":
            capabilities = dict(profile.capabilities)
            # This is the only capability axis that this operational probe
            # can establish. Do not infer domain, reasoning, or model-quality
            # scores from a successful native tool turn.
            if profile.capability("agentic_tool_calling") <= 0.35:
                capabilities["agentic_tool_calling"] = 0.78
            updated.append(
                replace(
                    profile,
                    capabilities=capabilities,
                    supports_tools=True,
                    tool_capability="proven",
                    tool_capability_source="operational_probe",
                    tool_probe_status=status,
                )
            )
            continue
        external_attestation = bool(profile.supports_tools) and profile.tool_capability_source in {
            "external_attestation",
            "external_attestation+operational_probe",
        }
        updated.append(
            replace(
                profile,
                # Keep an explicit attestation usable, but make the latest
                # contradictory operational evidence visible to the router.
                supports_tools=bool(profile.supports_tools and external_attestation),
                tool_capability="failed",
                tool_capability_source=(
                    "external_attestation+operational_probe"
                    if external_attestation
                    else "operational_probe"
                ),
                tool_probe_status=status,
            )
        )
    return updated


def _apply_runtime_vision_probe(
    profiles: Sequence[ModelProfile],
    rows: Sequence[Mapping[str, Any]],
) -> list[ModelProfile]:
    """Apply endpoint-bound visual evidence without touching quality scores."""

    updated: list[ModelProfile] = []
    for profile in profiles:
        status = vision_input_probe_status(profile, rows)
        if status is None:
            updated.append(profile)
            continue
        updated.append(
            replace(
                profile,
                supports_vision=True,
                vision_probe_status=status,
                vision_capability_source="operational_probe",
            )
        )
    return updated


def _apply_runtime_reasoning_probe(
    profiles: Sequence[ModelProfile],
    rows: Sequence[Mapping[str, Any]],
) -> list[ModelProfile]:
    """Promote only exact candidate profiles with complete strict evidence.

    Reasoning transport is a provider-wire capability, not a model-quality
    score. A missing row means that a bounded probe did not select the model;
    timeouts and other indeterminate rows preserve the original candidate.
    Only a control plus every declared level can promote to ``verified``.
    """

    rows_by_profile = {
        str(row.get("profile_id") or ""): row
        for row in rows
        if str(row.get("profile_id") or "")
    }
    updated: list[ModelProfile] = []
    for profile in profiles:
        row = rows_by_profile.get(profile.profile_id)
        if row is None:
            updated.append(profile)
            continue
        config = (
            dict(profile.reasoning_transport)
            if isinstance(profile.reasoning_transport, Mapping)
            else {}
        )
        if str(config.get("status") or "").strip().casefold() != "candidate":
            updated.append(profile)
            continue
        if _reasoning_probe_row_verifies_profile(profile, row):
            next_config = dict(config)
            next_config["status"] = "verified"
            updated.append(replace(profile, reasoning_transport=next_config))
            continue
        if _reasoning_probe_row_rejects_profile(profile, row):
            next_config = dict(config)
            next_config["status"] = "unsupported"
            updated.append(replace(profile, reasoning_transport=next_config))
            continue
        updated.append(profile)
    return updated


def _reasoning_probe_row_verifies_profile(
    profile: ModelProfile,
    row: Mapping[str, Any],
) -> bool:
    config = (
        dict(profile.reasoning_transport)
        if isinstance(profile.reasoning_transport, Mapping)
        else {}
    )
    if (
        str(row.get("probe_kind") or "").strip().casefold() != "reasoning_transport"
        or str(row.get("status") or "").strip().casefold() != "verified"
        or row.get("live_probe_evidence") is not True
        or row.get("strict_wire_shape_preserved") is not True
        or str(row.get("transport") or "") != str(config.get("transport") or "")
        or not _reasoning_probe_binding_matches_profile(profile, row)
    ):
        return False
    declared_efforts = _reasoning_probe_efforts(config)
    row_efforts = _normalized_reasoning_efforts(row.get("declared_efforts"))
    if declared_efforts and row_efforts != declared_efforts:
        return False
    if not declared_efforts and row_efforts:
        return False
    control = row.get("control") if isinstance(row.get("control"), Mapping) else {}
    if not _strict_reasoning_probe_attempt_accepted(control):
        return False
    attempt_rows = (
        row.get("effort_results")
        if isinstance(row.get("effort_results"), list)
        else []
    )
    by_effort = {
        normalize_reasoning_effort(attempt.get("effort")): attempt
        for attempt in attempt_rows
        if isinstance(attempt, Mapping)
        and normalize_reasoning_effort(attempt.get("effort"))
    }
    efforts_valid = bool(
        row.get("all_declared_efforts_strict_streaming") is True
        and all(
            _strict_reasoning_probe_attempt_accepted(by_effort.get(effort, {}))
            for effort in declared_efforts
        )
    )
    transport = str(config.get("transport") or "")
    if transport not in {"anthropic_thinking", "gemini_thinking_config"}:
        return bool(declared_efforts and efforts_valid)
    declared_budgets = _normalized_reasoning_budgets(config.get("supported_budget_tokens"))
    row_budgets = _normalized_reasoning_budgets(row.get("declared_budget_tokens"))
    if not declared_budgets or row_budgets != declared_budgets:
        return False
    budget_rows = (
        row.get("budget_results")
        if isinstance(row.get("budget_results"), list)
        else []
    )
    by_budget: dict[int, Mapping[str, Any]] = {}
    for attempt in budget_rows:
        if not isinstance(attempt, Mapping):
            continue
        for budget in _normalized_reasoning_budgets([attempt.get("budget_tokens")]):
            by_budget[budget] = attempt
    budget_map = config.get("budget_tokens_by_effort")
    for budget in declared_budgets:
        mapped_efforts = [
            effort
            for effort, raw_budget in budget_map.items()
            if normalize_reasoning_budget_tokens(raw_budget) == budget
        ] if isinstance(budget_map, Mapping) else []
        if mapped_efforts:
            if not any(
                _strict_reasoning_probe_attempt_accepted(by_effort.get(effort, {}))
                for effort in mapped_efforts
            ):
                return False
        elif not _strict_reasoning_probe_attempt_accepted(by_budget.get(budget, {})):
            return False
    return bool(
        row.get("all_declared_budgets_strict_streaming") is True
        and row.get("all_declared_reasoning_controls_strict_streaming") is True
    )


def _reasoning_probe_row_rejects_profile(
    profile: ModelProfile,
    row: Mapping[str, Any],
) -> bool:
    config = (
        dict(profile.reasoning_transport)
        if isinstance(profile.reasoning_transport, Mapping)
        else {}
    )
    if (
        str(row.get("probe_kind") or "").strip().casefold() != "reasoning_transport"
        or str(row.get("status") or "").strip().casefold() != "rejected"
        or row.get("live_probe_evidence") is not True
        or str(row.get("transport") or "") != str(config.get("transport") or "")
        or not _reasoning_probe_binding_matches_profile(profile, row)
    ):
        return False
    control = row.get("control") if isinstance(row.get("control"), Mapping) else {}
    if not _strict_reasoning_probe_attempt_accepted(control):
        return False
    attempts = []
    if isinstance(row.get("effort_results"), list):
        attempts.extend(row.get("effort_results"))
    if isinstance(row.get("budget_results"), list):
        attempts.extend(row.get("budget_results"))
    return any(
        isinstance(attempt, Mapping)
        and str(attempt.get("status") or "").strip().casefold() == "rejected"
        and 400 <= _safe_status_code(attempt.get("http_status")) < 500
        for attempt in attempts
    )


def _reasoning_probe_binding_matches_profile(
    profile: ModelProfile,
    row: Mapping[str, Any],
) -> bool:
    """Require the fresh in-memory probe to match the current endpoint."""

    expected = reasoning_transport_probe_binding(profile)
    observed = (
        row.get("reasoning_transport_binding")
        if isinstance(row.get("reasoning_transport_binding"), Mapping)
        else {}
    )
    if str(observed.get("schema") or "") != REASONING_TRANSPORT_BINDING_SCHEMA:
        return False
    observed_digest = sha256_text(
        stable_json(
            {
                key: value
                for key, value in observed.items()
                if key != "binding_sha256"
            }
        )
    )
    return bool(
        observed.get("binding_sha256")
        and observed_digest == str(observed.get("binding_sha256") or "")
        and str(observed.get("binding_sha256") or "")
        == str(expected.get("binding_sha256") or "")
    )


def _strict_reasoning_probe_attempt_accepted(attempt: Mapping[str, Any]) -> bool:
    if str(attempt.get("status") or "").strip().casefold() != "accepted":
        return False
    if attempt.get("marker_observed") is not True:
        return False
    if attempt.get("strict_streaming_contract_valid") is not True:
        return False
    if attempt.get("stream_requested") is not True:
        return False
    if attempt.get("strict_streaming_requested") is not True:
        return False
    if attempt.get("stream_observed") is not True:
        return False
    if attempt.get("stream_fallback_used") is True:
        return False
    if str(attempt.get("stream_protocol") or "").strip().casefold() not in {"sse", "ndjson"}:
        return False
    if _safe_nonnegative_int(attempt.get("stream_frame_count")) < 1:
        return False
    latency = _safe_nonnegative_float(attempt.get("latency_ms"))
    return latency is not None and latency <= PROVIDER_MAX_RESPONSE_LATENCY_MS


def _normalized_reasoning_efforts(value: Any) -> list[str]:
    raw_values = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    efforts: list[str] = []
    for raw in raw_values:
        effort = normalize_reasoning_effort(raw)
        if effort and effort not in efforts:
            efforts.append(effort)
    return efforts


def _reasoning_probe_efforts(config: Mapping[str, Any]) -> list[str]:
    """Include logical effort aliases backed by exact native budgets."""

    efforts = _normalized_reasoning_efforts(config.get("supported_efforts"))
    transport = str(config.get("transport") or "").strip().casefold()
    if transport in {"anthropic_thinking", "gemini_thinking_config"}:
        budget_map = config.get("budget_tokens_by_effort")
        if isinstance(budget_map, Mapping):
            for raw_effort in budget_map:
                effort = normalize_reasoning_effort(raw_effort)
                if effort and effort not in efforts:
                    efforts.append(effort)
    return efforts


def _normalized_reasoning_budgets(value: Any) -> list[int]:
    raw_values = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    budgets: list[int] = []
    for raw in raw_values:
        budget = normalize_reasoning_budget_tokens(raw)
        if budget is not None and budget not in budgets:
            budgets.append(budget)
    return sorted(budgets)


def _safe_status_code(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_nonnegative_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed < 0.0:
        return None
    return parsed


def _safe_probe_latency(value: Any) -> int | None:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(1, parsed) if parsed > 0 else None


def enroll_provider_channels(
    *,
    config_path: str | Path | None = None,
    output_dir: str | Path,
    providers: Sequence[str] = (),
    live: bool = False,
    timeout: float = 60.0,
    max_workers: int = 4,
    max_models: int | None = None,
    max_models_per_provider: int | None = None,
    min_available_models: int = 1,
    include_unavailable: bool = False,
    calibrate_tools: bool = True,
    tool_probe_timeout: float | None = None,
    tool_probe_max_models: int | None = None,
    tool_probe_max_models_per_provider: int | None = None,
    calibrate_reasoning: bool = True,
    reasoning_probe_timeout: float | None = None,
    reasoning_probe_max_models: int | None = None,
    reasoning_probe_max_models_per_provider: int | None = None,
    calibrate_vision: bool = True,
    vision_probe_timeout: float | None = None,
    vision_probe_max_models: int | None = None,
    vision_probe_max_models_per_provider: int | None = None,
    redact_provider_identifiers: bool = False,
) -> dict[str, Any]:
    """Discover, probe, and operationally calibrate configured channels.

    The config file contains only provider labels, protocol names, model
    aliases, and environment-variable references. The selected config path is
    installed for this operation and restored before returning, which keeps
    this helper safe to compose in tests and operator processes.

    Private intermediate artifacts retain the aliases required to load a live
    registry and must stay in an operator-only directory. The returned receipt
    contains only hashes, counts, readiness flags, and bounded reason codes.
    """

    started = time.monotonic()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    previous_config_path = os.environ.get("AXIO_FUSION_PROVIDER_CONFIG_FILE")
    if config_path is not None:
        os.environ["AXIO_FUSION_PROVIDER_CONFIG_FILE"] = str(Path(config_path))

    probe_path = output_root / "provider_probe.private.json"
    redacted_probe_path = output_root / "provider_probe.safe.json"
    registry_path = output_root / "runtime_registry.candidate.private.json"
    redacted_registry_path = output_root / "runtime_registry.safe.json"
    tool_probe_path = output_root / "provider_tool_probe.private.json"
    redacted_tool_probe_path = output_root / "provider_tool_probe.safe.json"
    reasoning_probe_path = output_root / "provider_reasoning_probe.private.json"
    redacted_reasoning_probe_path = output_root / "provider_reasoning_probe.safe.json"
    vision_probe_path = output_root / "vision_probe.private.json"
    redacted_vision_probe_path = output_root / "vision_probe.safe.json"
    calibration_path = output_root / "registry_calibration.private.json"
    calibrated_registry_path = output_root / "runtime_registry.calibrated.private.json"
    receipt_path = output_root / "enrollment_receipt.safe.json"

    reason_codes: list[str] = []
    warning_codes: list[str] = []
    stage_receipts: dict[str, Any] = {}
    source_summary = provider_configuration_source_summary()
    try:
        if config_path is not None and source_summary.get("config_file_present") is not True:
            reason_codes.append("provider_config_file_not_loaded")
        if not live:
            reason_codes.append("live_flag_required_for_channel_enrollment")

        if not reason_codes:
            bounded_timeout = max(1.0, min(300.0, float(timeout)))
            bounded_workers = max(1, min(32, int(max_workers or 1)))
            probe_payload = probe_exposed_provider_models(
                providers=list(providers),
                timeout=bounded_timeout,
                live=True,
                max_models=max_models,
                max_models_per_provider=max_models_per_provider,
                max_workers=bounded_workers,
                redact_provider_identifiers=False,
            )
            _write_json(probe_path, probe_payload)
            nested_probe = probe_payload.get("probe_report") if isinstance(probe_payload.get("probe_report"), Mapping) else {}
            stage_receipts["discovery_and_text_probe"] = _stage_receipt(
                status="ready" if nested_probe.get("available_count") is not None else "failed",
                path=probe_path,
                payload=probe_payload,
                count_fields=("discovered_model_count", "candidate_model_count"),
                extra_counts={"available_count": nested_probe.get("available_count")},
            )
            if int(probe_payload.get("candidate_model_count") or 0) < int(min_available_models):
                reason_codes.append("insufficient_probe_candidates")
            if int(nested_probe.get("available_count") or 0) < int(min_available_models):
                reason_codes.append("insufficient_live_available_probe_models")
            if redact_provider_identifiers:
                _write_json(redacted_probe_path, _redacted_probe_copy(probe_payload))
        else:
            stage_receipts["discovery_and_text_probe"] = {
                "status": "blocked",
                "reason_codes": ["live_flag_required_for_channel_enrollment"],
            }

        if not reason_codes:
            registry_payload = build_registry_from_probe_artifacts(
                probe_paths=[probe_path],
                include_unavailable=include_unavailable,
                min_available_models=max(1, int(min_available_models)),
                redact_provider_identifiers=False,
            )
            _write_json(registry_path, registry_payload)
            registry_status = registry_payload.get("readiness", {})
            stage_receipts["runtime_registry"] = _stage_receipt(
                status="ready" if registry_status.get("ready") is True else "failed",
                path=registry_path,
                payload=registry_payload,
                count_fields=("model_count", "provider_count", "available_model_count", "live_available_model_count"),
            )
            if registry_status.get("ready") is not True:
                reason_codes.extend(
                    str(item)
                    for item in registry_status.get("blockers", [])
                    if str(item)
                )
            if redact_provider_identifiers:
                redacted_registry_payload = build_registry_from_probe_artifacts(
                    probe_paths=[probe_path],
                    include_unavailable=include_unavailable,
                    min_available_models=max(1, int(min_available_models)),
                    redact_provider_identifiers=True,
                )
                _write_json(redacted_registry_path, redacted_registry_payload)
        else:
            stage_receipts["runtime_registry"] = {"status": "blocked", "reason_codes": list(reason_codes)}

        if not reason_codes and calibrate_tools:
            profiles = load_registry(registry_path)
            bounded_tool_timeout = max(
                1.0,
                min(
                    300.0,
                    float(tool_probe_timeout)
                    if tool_probe_timeout is not None
                    else min(max(1.0, min(300.0, float(timeout))), 20.0),
                ),
            )
            tool_probe_payload = probe_provider_tool_support(
                profiles,
                timeout=bounded_tool_timeout,
                live=True,
                max_workers=max(1, min(32, int(max_workers or 1))),
                max_models=tool_probe_max_models,
                max_models_per_provider=tool_probe_max_models_per_provider,
                redact_provider_identifiers=False,
            )
            _write_json(tool_probe_path, tool_probe_payload)
            supported_count = int(tool_probe_payload.get("tool_call_supported_count") or 0)
            stage_receipts["native_tool_probe"] = _stage_receipt(
                status="ready" if tool_probe_payload.get("network_calls_performed") is True else "failed",
                path=tool_probe_path,
                payload=tool_probe_payload,
                count_fields=("model_count", "tool_call_supported_count", "text_only_count", "protocol_failure_count", "transport_failure_count"),
                extra_counts={
                    "timeout_seconds": bounded_tool_timeout,
                    "selected_model_count": tool_probe_payload.get("model_count"),
                },
            )
            if supported_count < 1:
                warning_codes.append("no_native_tool_capable_profile_probed")
            if redact_provider_identifiers:
                _write_json(redacted_tool_probe_path, _redacted_tool_probe_copy(tool_probe_payload))
        elif not calibrate_tools:
            stage_receipts["native_tool_probe"] = {"status": "skipped", "reason_codes": ["tool_calibration_disabled"]}
        else:
            stage_receipts["native_tool_probe"] = {"status": "blocked", "reason_codes": list(reason_codes)}

        reasoning_probe_payload: dict[str, Any] = {}
        if not reason_codes and calibrate_reasoning:
            profiles = load_registry(registry_path)
            bounded_reasoning_timeout = max(
                1.0,
                min(
                    PROVIDER_MAX_RESPONSE_SECONDS,
                    float(reasoning_probe_timeout)
                    if reasoning_probe_timeout is not None
                    else min(
                        max(1.0, min(PROVIDER_MAX_RESPONSE_SECONDS, float(timeout))),
                        20.0,
                    ),
                ),
            )
            reasoning_probe_payload = probe_provider_reasoning_support(
                profiles,
                timeout=bounded_reasoning_timeout,
                live=True,
                max_workers=max(1, min(32, int(max_workers or 1))),
                max_models=reasoning_probe_max_models,
                max_models_per_provider=reasoning_probe_max_models_per_provider,
                redact_provider_identifiers=False,
            )
            _write_json(reasoning_probe_path, reasoning_probe_payload)
            stage_receipts["reasoning_transport_probe"] = _stage_receipt(
                status=(
                    "ready"
                    if reasoning_probe_payload.get("network_calls_performed") is True
                    or int(reasoning_probe_payload.get("model_count") or 0) == 0
                    else "failed"
                ),
                path=reasoning_probe_path,
                payload=reasoning_probe_payload,
                count_fields=(
                    "model_count",
                    "verified_count",
                    "rejected_count",
                    "indeterminate_count",
                ),
                extra_counts={"timeout_seconds": bounded_reasoning_timeout},
            )
            if (
                int(reasoning_probe_payload.get("candidate_model_count_before_selection") or 0) > 0
                and int(reasoning_probe_payload.get("verified_count") or 0) < 1
            ):
                warning_codes.append("no_reasoning_transport_candidate_verified")
            if redact_provider_identifiers:
                _write_json(
                    redacted_reasoning_probe_path,
                    _redacted_reasoning_probe_copy(reasoning_probe_payload),
                )
        elif not calibrate_reasoning:
            stage_receipts["reasoning_transport_probe"] = {
                "status": "skipped",
                "reason_codes": ["reasoning_calibration_disabled"],
            }
        else:
            stage_receipts["reasoning_transport_probe"] = {
                "status": "blocked",
                "reason_codes": list(reason_codes),
            }

        vision_probe_payload: dict[str, Any] = {}
        if not reason_codes and calibrate_vision:
            profiles = load_registry(registry_path)
            bounded_vision_timeout = max(
                1.0,
                min(
                    PROVIDER_MAX_RESPONSE_SECONDS,
                    float(vision_probe_timeout)
                    if vision_probe_timeout is not None
                    else min(
                        max(1.0, min(PROVIDER_MAX_RESPONSE_SECONDS, float(timeout))),
                        20.0,
                    ),
                ),
            )
            vision_probe_payload = probe_provider_vision_support(
                profiles,
                timeout=bounded_vision_timeout,
                live=True,
                max_workers=max(1, min(32, int(max_workers or 1))),
                max_models=vision_probe_max_models,
                max_models_per_provider=vision_probe_max_models_per_provider,
                redact_provider_identifiers=False,
            )
            _write_json(vision_probe_path, vision_probe_payload)
            stage_receipts["vision_input_probe"] = _stage_receipt(
                status=(
                    "ready"
                    if vision_probe_payload.get("network_calls_performed") is True
                    or int(vision_probe_payload.get("model_count") or 0) == 0
                    else "failed"
                ),
                path=vision_probe_path,
                payload=vision_probe_payload,
                count_fields=(
                    "model_count",
                    "passed_count",
                    "failed_count",
                    "unsupported_count",
                    "indeterminate_count",
                    "latency_ineligible_count",
                ),
                extra_counts={"timeout_seconds": bounded_vision_timeout},
            )
            if redact_provider_identifiers:
                _write_json(
                    redacted_vision_probe_path,
                    _redacted_vision_probe_copy(vision_probe_payload),
                )
        elif not calibrate_vision:
            stage_receipts["vision_input_probe"] = {
                "status": "skipped",
                "reason_codes": ["vision_calibration_disabled"],
            }
        else:
            stage_receipts["vision_input_probe"] = {
                "status": "blocked",
                "reason_codes": list(reason_codes),
            }

        calibration_enabled = bool(calibrate_tools or calibrate_reasoning or calibrate_vision)
        if not reason_codes and calibration_enabled:
            calibration_probe_paths: list[Path] = [probe_path]
            if calibrate_tools:
                calibration_probe_paths.append(tool_probe_path)
            if calibrate_reasoning:
                calibration_probe_paths.append(reasoning_probe_path)
            if calibrate_vision:
                calibration_probe_paths.append(vision_probe_path)
            calibration_payload = build_registry_calibration(
                registry_path=registry_path,
                probe_paths=calibration_probe_paths,
            )
            _write_json(calibration_path, calibration_payload)
            calibration_contract = calibration_payload.get("application_contract", {})
            stage_receipts["operational_calibration"] = _stage_receipt(
                status="ready" if calibration_contract.get("safe_to_write_registry") is True else "failed",
                path=calibration_path,
                payload=calibration_payload,
                count_fields=("registry_model_count",),
            )
            if calibration_contract.get("safe_to_write_registry") is not True:
                reason_codes.extend(
                    str(item)
                    for item in calibration_contract.get("blocker_reason_codes", [])
                    if str(item)
                )
            else:
                _write_json(calibrated_registry_path, calibration_payload["updated_registry"])
        elif not calibration_enabled:
            stage_receipts["operational_calibration"] = {
                "status": "skipped",
                "reason_codes": ["operational_calibration_disabled"],
            }
        else:
            stage_receipts["operational_calibration"] = {"status": "blocked", "reason_codes": list(reason_codes)}

        candidate_registry = calibrated_registry_path if calibrated_registry_path.is_file() else registry_path
        final_profiles = load_registry(candidate_registry) if not reason_codes and candidate_registry.is_file() else []
        final_readiness = registry_readiness(final_profiles)
        status = "ready" if not reason_codes and final_readiness.get("ready") is True else "blocked"
        result = {
            "schema": _ENROLLMENT_SCHEMA,
            "status": status,
            "live": bool(live),
            "config_source": {
                "config_file_supplied": config_path is not None,
                "config_source_summary": _safe_source_summary(source_summary),
                "config_path_sha256": sha256_text(str(Path(config_path))) if config_path is not None else "",
            },
            "stages": stage_receipts,
            "artifacts": {
                "probe_private_path_sha256": _path_receipt(probe_path),
                "probe_safe_path_sha256": _path_receipt(redacted_probe_path),
                "registry_candidate_path_sha256": _path_receipt(registry_path),
                "registry_safe_path_sha256": _path_receipt(redacted_registry_path),
                "tool_probe_private_path_sha256": _path_receipt(tool_probe_path),
                "tool_probe_safe_path_sha256": _path_receipt(redacted_tool_probe_path),
                "reasoning_probe_private_path_sha256": _path_receipt(reasoning_probe_path),
                "reasoning_probe_safe_path_sha256": _path_receipt(redacted_reasoning_probe_path),
                "vision_probe_private_path_sha256": _path_receipt(vision_probe_path),
                "vision_probe_safe_path_sha256": _path_receipt(redacted_vision_probe_path),
                "calibration_path_sha256": _path_receipt(calibration_path),
                "calibrated_registry_path_sha256": _path_receipt(calibrated_registry_path),
                "serving_registry_path_sha256": _path_receipt(candidate_registry) if status == "ready" else "",
            },
            "serving_registry": {
                "model_count": len(final_profiles),
                "provider_count": len({profile.provider for profile in final_profiles}),
                "api_format_counts": _api_format_counts(final_profiles),
                "readiness": _safe_registry_readiness(final_readiness),
                "path_is_calibrated": candidate_registry == calibrated_registry_path and status == "ready",
            },
            "reason_codes": sorted(set(reason_codes)),
            "warning_codes": sorted(set(warning_codes)),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "anti_leakage_contract": {
                "raw_provider_names_persisted_in_receipt": False,
                "raw_provider_model_ids_persisted_in_receipt": False,
                "raw_provider_urls_persisted": False,
                "raw_api_keys_persisted": False,
                "raw_prompts_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
                "private_intermediate_artifacts_are_operator_only": True,
            },
        }
        _write_json(receipt_path, result)
        return result
    finally:
        if previous_config_path is None:
            os.environ.pop("AXIO_FUSION_PROVIDER_CONFIG_FILE", None)
        else:
            os.environ["AXIO_FUSION_PROVIDER_CONFIG_FILE"] = previous_config_path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _path_receipt(path: Path) -> str:
    return sha256_text(str(path)) if path.is_file() else ""


def _stage_receipt(
    *,
    status: str,
    path: Path,
    payload: Mapping[str, Any],
    count_fields: Sequence[str],
    extra_counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    counts = {
        field: _safe_nonnegative_int(payload.get(field))
        for field in count_fields
        if payload.get(field) is not None
    }
    counts.update(
        {
            str(field): _safe_nonnegative_int(value)
            for field, value in (extra_counts or {}).items()
            if value is not None
        }
    )
    return {
        "status": str(status),
        "artifact_path_sha256": _path_receipt(path),
        "artifact_content_sha256": sha256_text(stable_json(payload)),
        "counts": counts,
    }


def _safe_source_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "config_source_present": value.get("config_source_present") is True,
        "config_file_present": value.get("config_file_present") is True,
        "config_env_present": value.get("config_env_present") is True,
        "valid_config_source_count": _safe_nonnegative_int(value.get("valid_config_source_count")),
        "provider_config_count": _safe_nonnegative_int(value.get("provider_config_count")),
        "invalid_provider_config_count": _safe_nonnegative_int(value.get("invalid_provider_config_count")),
    }


def _safe_registry_readiness(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ready": value.get("ready") is True,
        "status": str(value.get("status") or ""),
        "blockers": [str(item) for item in value.get("blockers", []) if str(item)],
        "warnings": [str(item) for item in value.get("warnings", []) if str(item)],
    }


def _api_format_counts(profiles: Sequence[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for profile in profiles:
        api_format = str(getattr(profile, "api_format", "") or "unknown")
        counts[api_format] = counts.get(api_format, 0) + 1
    return dict(sorted(counts.items()))


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _redacted_probe_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    from .providers import redact_provider_probe_artifact

    return redact_provider_probe_artifact(payload)


def _redacted_tool_probe_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    from .providers import redact_provider_tool_probe_artifact

    return redact_provider_tool_probe_artifact(payload)


def _redacted_reasoning_probe_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    from .providers import redact_provider_reasoning_probe_artifact

    return redact_provider_reasoning_probe_artifact(payload)


def _redacted_vision_probe_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    from .vision_probe import redact_vision_probe_artifact

    return redact_vision_probe_artifact(payload)
