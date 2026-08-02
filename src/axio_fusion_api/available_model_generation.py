"""Generate the model set that is allowed to enter the Fusion runtime.

This module is the small control-plane boundary between provider onboarding and
Fusion.  It deliberately delegates discovery, remote capability research,
strict streaming probes, and the hash-bound registry contract to the existing
pre-Fusion implementation.  Its job is to provide one stable result shape and
one fail-closed publication path for callers that need to hand the result to
the runtime.

The generated ranking is an operational prior, not benchmark evidence.  A
model is exposed in ``available_model_list`` only after at least one physical
replica has produced a real SSE/NDJSON stream with non-empty output and an
observed latency at or below the configured 90-second ceiling.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .latency_policy import PROVIDER_MAX_RESPONSE_LATENCY_MS
from .model_screening import (
    build_prefusion_fusion_handoff,
    run_prefusion_model_screening,
    validate_prefusion_handoff,
)
from .registry import validate_prefusion_registry_handoff
from .schemas import ModelProfile, sha256_text, stable_json


AVAILABLE_MODEL_GENERATION_SCHEMA = (
    "axio_fusion_api.available_model_generation.v1"
)


class AvailableModelGenerationError(RuntimeError):
    """Raised when a model-generation artifact cannot be published."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code or "available_model_generation_failed")[:160]
        super().__init__(message or self.code)


def generate_available_model_set(
    *,
    profiles: Sequence[ModelProfile | Mapping[str, Any]] | None = None,
    registry_path: str | Path | None = None,
    focus_manifest: Mapping[str, Any] | str | Path | None = None,
    source_manifest: Mapping[str, Any] | str | Path | None = None,
    research_agent_config: Mapping[str, Any] | str | Path | None = None,
    research_output: Mapping[str, Any] | str | Path | None = None,
    total_budget_seconds: float | None = None,
    live: bool = False,
    discovery_timeout: float = 15.0,
    timeout: float = 90.0,
    source_timeout: float = 15.0,
    max_workers: int = 4,
    max_models: int | None = None,
    min_available_models: int = 1,
    research_batch_size: int | None = None,
    research_max_workers: int | None = None,
    stream_probe_samples: int = 3,
    role_probe_samples_per_role: int = 2,
    provider_client: Any | None = None,
    research_client: Any | None = None,
    redact_provider_identifiers: bool = False,
) -> dict[str, Any]:
    """Run pre-Fusion screening and return the only runtime handoff.

    ``research_ranking`` is kept complete for auditability.  The runtime list
    and ``operational_ranking`` come from the validated handoff and therefore
    contain only latency-filtered logical models.  Physical replicas are kept
    inside the private registry for load balancing/failover; they never become
    additional model votes.
    """

    report = run_prefusion_model_screening(
        profiles=profiles,
        registry_path=registry_path,
        focus_manifest=focus_manifest,
        source_manifest=source_manifest,
        research_agent_config=research_agent_config,
        research_output=research_output,
        total_budget_seconds=total_budget_seconds,
        live=live,
        discovery_timeout=discovery_timeout,
        timeout=timeout,
        source_timeout=source_timeout,
        max_workers=max_workers,
        max_models=max_models,
        min_available_models=min_available_models,
        research_batch_size=research_batch_size,
        research_max_workers=research_max_workers,
        stream_probe_samples=stream_probe_samples,
        role_probe_samples_per_role=role_probe_samples_per_role,
        provider_client=provider_client,
        research_client=research_client,
        redact_provider_identifiers=redact_provider_identifiers,
    )

    report_validation = validate_prefusion_handoff(
        report,
        require_ready=bool(live),
    )
    handoff = build_prefusion_fusion_handoff(
        report,
        require_ready=bool(live),
        include_private_registry=True,
        redact_provider_identifiers=redact_provider_identifiers,
    )
    registry = handoff.get("fusion_registry")
    registry_validation = _validate_registry(registry, require_ready=bool(live))
    stability = _generation_stability_contract(
        report=report,
        handoff=handoff,
        registry=registry,
    )
    stability_ready = stability["multi_sample_stability_required"] is True

    ready = bool(
        report.get("status") == "ready"
        and handoff.get("status") == "ready"
        and isinstance(registry, Mapping)
        and report_validation.get("valid") is True
        and registry_validation.get("valid") is True
        and (not live or stability_ready)
    )
    if not ready:
        # A blocked result may still expose the complete research prior for
        # operator diagnosis, but it must never expose a serving list or a
        # registry that a caller could accidentally activate.
        handoff = _blocked_handoff(handoff)
        registry = None

    ranking = handoff.get("research_ranking")
    ranking = ranking if isinstance(ranking, Mapping) else {}
    operational = handoff.get("operational_ranking")
    operational = operational if isinstance(operational, Mapping) else {}
    available = handoff.get("available_model_list")
    available = available if isinstance(available, list) and ready else []
    blockers = sorted(
        {
            str(code)[:160]
            for code in report.get("blockers", [])
            if str(code)
        }
    )
    if not report_validation.get("valid"):
        blockers.extend(
            f"handoff:{str(code)[:120]}"
            for code in report_validation.get("reason_codes", [])
            if str(code)
        )
    if not registry_validation.get("valid"):
        blockers.extend(
            f"registry:{str(code)[:120]}"
            for code in registry_validation.get("reason_codes", [])
            if str(code)
        )
    if live and not stability_ready:
        blockers.append("registry:prefusion_registry_stream_stability_contract_invalid")

    artifact: dict[str, Any] = {
        "schema": AVAILABLE_MODEL_GENERATION_SCHEMA,
        "status": "ready" if ready else "blocked",
        "research_ranking": _json_copy(ranking),
        "operational_ranking": _json_copy(operational) if ready else {},
        "available_model_list": _json_copy(available),
        "logical_model_count": len(available),
        "latency_gate": {
            "max_response_seconds": PROVIDER_MAX_RESPONSE_LATENCY_MS / 1000.0,
            "max_response_latency_ms": PROVIDER_MAX_RESPONSE_LATENCY_MS,
            "requires_live_stream_probe": True,
            "requires_sse_or_ndjson": True,
            "ordinary_json_fallback_is_ineligible": True,
            "observed_latency_is_not_a_percentile": True,
            "stability_contract_schema": stability["schema"],
            "stability_contract_present": stability["contract_present"],
            "multi_sample_stability_required": stability[
                "multi_sample_stability_required"
            ],
            "samples_per_profile": stability["samples_per_profile"],
            "requires_all_samples_success": stability[
                "requires_all_samples_success"
            ],
            "requires_each_sample_latency_at_or_below_90_seconds": stability[
                "requires_each_sample_latency_at_or_below_90_seconds"
            ],
            "requires_each_sample_strict_streaming": stability[
                "requires_each_sample_strict_streaming"
            ],
        },
        "replica_policy": {
            "same_canonical_model_is_one_logical_model": True,
            "replicas_are_load_balancing_and_failover_only": True,
            "replicas_are_not_independent_votes": True,
        },
        "fusion_handoff": _json_copy(handoff),
        "validation": {
            "screening_report_valid": report_validation.get("valid") is True,
            "screening_report_reason_codes": sorted(
                str(code)[:160]
                for code in report_validation.get("reason_codes", [])
                if str(code)
            ),
            "registry_valid": registry_validation.get("valid") is True,
            "registry_reason_codes": sorted(
                str(code)[:160]
                for code in registry_validation.get("reason_codes", [])
                if str(code)
            ),
            "require_ready": bool(live),
        },
        "source_receipt": {
            "screening_report_schema": str(report.get("schema") or ""),
            "screening_status": str(report.get("status") or "blocked"),
            "screening_report_content_sha256": sha256_text(stable_json(report)),
            "handoff_content_sha256": sha256_text(stable_json(handoff)),
            "registry_content_sha256": (
                sha256_text(stable_json(registry))
                if isinstance(registry, Mapping)
                else ""
            ),
            "candidate_count": int(
                report.get("research_ranking", {}).get("candidate_count") or 0
            )
            if isinstance(report.get("research_ranking"), Mapping)
            else 0,
            "available_logical_model_count": len(available),
            "raw_provider_output_persisted": False,
            "raw_research_prompt_persisted": False,
            "raw_research_output_persisted": False,
            "secrets_persisted": False,
        },
        "blockers": sorted(set(blockers)),
        "publication": {
            "registry_must_be_published_only_when_ready": True,
            "blocked_generation_must_not_replace_active_registry": True,
            "atomic_file_publication": True,
            "private_registry_included": bool(ready and isinstance(registry, Mapping)),
        },
        "no_cheat_contract": {
            "research_ranking_is_operational_prior_only": True,
            "benchmark_cases_or_labels_used": False,
            "benchmark_results_used_to_rank_models": False,
            "final_benchmark_claims_require_external_api_evaluation": True,
            "local_model_weights_loaded": False,
            "secrets_persisted": False,
        },
    }
    # A redacted generation result must never carry a private registry.  The
    # redaction is performed by the underlying report/handoff projection; this
    # assertion protects this new wrapper if that contract changes later.
    if redact_provider_identifiers:
        artifact["fusion_handoff"].pop("fusion_registry", None)
        artifact["publication"]["private_registry_included"] = False
    return artifact


def publish_available_model_set(
    artifact: Mapping[str, Any],
    *,
    registry_path: str | Path,
    handoff_path: str | Path | None = None,
) -> dict[str, Any]:
    """Atomically publish a ready generation without replacing on failure.

    The active runtime consumes ``registry_path``.  A blocked artifact is
    diagnostic-only and is rejected before any write, so a failed refresh
    cannot turn a healthy running service into an empty registry.
    """

    if not isinstance(artifact, Mapping):
        raise AvailableModelGenerationError("available_model_artifact_invalid")
    if artifact.get("status") != "ready":
        raise AvailableModelGenerationError("available_model_generation_not_ready")
    handoff = artifact.get("fusion_handoff")
    handoff = handoff if isinstance(handoff, Mapping) else {}
    _validate_artifact_projection(artifact, handoff)
    registry = handoff.get("fusion_registry")
    if not isinstance(registry, Mapping):
        raise AvailableModelGenerationError("available_model_private_registry_missing")
    validation = validate_prefusion_registry_handoff(registry, require_ready=True)
    if validation.get("valid") is not True:
        raise AvailableModelGenerationError("available_model_registry_validation_failed")

    registry_output = _atomic_write_json(registry_path, registry)
    handoff_output: Path | None = None
    if handoff_path is not None:
        handoff_output = _atomic_write_json(handoff_path, artifact)
    return {
        "schema": "axio_fusion_api.available_model_publication.v1",
        "status": "ready",
        "registry_path": str(registry_output),
        "handoff_path": str(handoff_output) if handoff_output else "",
        "registry_content_sha256": sha256_text(stable_json(registry)),
        "logical_model_count": int(artifact.get("logical_model_count") or 0),
        "latency_ceiling_ms": PROVIDER_MAX_RESPONSE_LATENCY_MS,
        "atomic_file_publication": True,
        "secrets_persisted": False,
    }


def _validate_registry(value: Any, *, require_ready: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "valid": not require_ready,
            "reason_codes": ["available_model_private_registry_missing"],
        }
    return validate_prefusion_registry_handoff(value, require_ready=require_ready)


def _generation_stability_contract(
    *,
    report: Mapping[str, Any],
    handoff: Mapping[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Project the actual admission contract without trusting caller input."""

    registry_binding = (
        registry.get("prefusion_screening")
        if isinstance(registry, Mapping)
        else None
    )
    streaming_probe = report.get("streaming_probe")
    candidates = (
        handoff.get("stream_stability_contract"),
        registry_binding.get("stream_stability_contract")
        if isinstance(registry_binding, Mapping)
        else None,
        streaming_probe.get("stability_contract")
        if isinstance(streaming_probe, Mapping)
        else None,
    )
    raw = next((value for value in candidates if isinstance(value, Mapping)), None)
    payload = raw if isinstance(raw, Mapping) else {}
    raw_samples = payload.get("samples_per_profile")
    try:
        samples = int(raw_samples) if not isinstance(raw_samples, bool) else 0
    except (TypeError, ValueError):
        samples = 0
    if samples < 1 or samples > 5:
        samples = None
    schema = str(payload.get("schema") or "")[:120]
    requires_all = payload.get("requires_all_samples_success") is True
    requires_latency = (
        payload.get("requires_each_sample_latency_at_or_below_90_seconds") is True
    )
    requires_stream = payload.get("requires_each_sample_strict_streaming") is True
    return {
        "schema": schema,
        "contract_present": bool(payload),
        "samples_per_profile": samples,
        "requires_all_samples_success": requires_all,
        "requires_each_sample_latency_at_or_below_90_seconds": requires_latency,
        "requires_each_sample_strict_streaming": requires_stream,
        "multi_sample_stability_required": bool(
            schema == "axio_fusion_api.provider_probe_stability_contract.v1"
            and samples is not None
            and samples >= 2
            and requires_all
            and requires_latency
            and requires_stream
        ),
    }


def _validate_artifact_projection(
    artifact: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> None:
    """Ensure the published convenience projections still bind to handoff."""

    if handoff.get("status") != "ready":
        raise AvailableModelGenerationError("available_model_handoff_not_ready")
    available = artifact.get("available_model_list")
    handoff_available = handoff.get("available_model_list")
    if not isinstance(available, list) or not isinstance(handoff_available, list):
        raise AvailableModelGenerationError("available_model_projection_missing")
    if stable_json(available) != stable_json(handoff_available):
        raise AvailableModelGenerationError("available_model_projection_mismatch")
    for field in ("research_ranking", "operational_ranking"):
        if stable_json(artifact.get(field) or {}) != stable_json(handoff.get(field) or {}):
            raise AvailableModelGenerationError(
                f"available_model_{field}_projection_mismatch"
            )
    try:
        logical_count = int(artifact.get("logical_model_count"))
    except (TypeError, ValueError):
        raise AvailableModelGenerationError("available_model_logical_count_invalid")
    if logical_count != len(available):
        raise AvailableModelGenerationError("available_model_logical_count_mismatch")
    source_receipt = artifact.get("source_receipt")
    if isinstance(source_receipt, Mapping):
        expected_handoff_digest = str(
            source_receipt.get("handoff_content_sha256") or ""
        ).strip().lower()
        if expected_handoff_digest and expected_handoff_digest != sha256_text(
            stable_json(handoff)
        ).lower():
            raise AvailableModelGenerationError("available_model_handoff_digest_mismatch")
        registry = handoff.get("fusion_registry")
        expected_registry_digest = str(
            source_receipt.get("registry_content_sha256") or ""
        ).strip().lower()
        if expected_registry_digest:
            if not isinstance(registry, Mapping):
                raise AvailableModelGenerationError(
                    "available_model_registry_digest_without_registry"
                )
            if expected_registry_digest != sha256_text(
                stable_json(registry)
            ).lower():
                raise AvailableModelGenerationError(
                    "available_model_registry_digest_mismatch"
                )
        expected_available_count = source_receipt.get(
            "available_logical_model_count"
        )
        if expected_available_count is not None:
            try:
                if int(expected_available_count) != len(available):
                    raise AvailableModelGenerationError(
                        "available_model_source_count_mismatch"
                    )
            except (TypeError, ValueError):
                raise AvailableModelGenerationError(
                    "available_model_source_count_invalid"
                )


def _blocked_handoff(value: Mapping[str, Any]) -> dict[str, Any]:
    output = _json_copy(value)
    output["status"] = "blocked"
    output["available_model_list"] = []
    output["logical_model_count"] = 0
    output["physical_profile_count"] = 0
    output["private_registry_included"] = False
    output.pop("fusion_registry", None)
    return output


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(output.parent),
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(output)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return output


__all__ = [
    "AVAILABLE_MODEL_GENERATION_SCHEMA",
    "AvailableModelGenerationError",
    "generate_available_model_set",
    "publish_available_model_set",
]
