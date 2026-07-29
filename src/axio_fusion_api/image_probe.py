"""Endpoint-bound image capability probing and registry promotion.

Image support is an operational capability, not a model-name inference. This
module sends a fixed, non-benchmark generation/edit control request only when
an operator explicitly selects live mode. The artifact records hashes,
statuses, timing, and stream framing; raw image bytes and provider responses
never leave process memory.
"""

from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

from .compat import normalize_api_format
from .image_api import ImagePart, ImageProviderClient, ImageProviderResult
from .providers import (
    ProviderExecutionError,
    _base_url,
    _dedupe_probe_profiles,
    _select_probe_profiles,
)
from .registry import normalize_profile
from .schemas import ModelProfile, sha256_text, stable_json


IMAGE_PROBE_SCHEMA = "axio_fusion_api.image_probe.v1"
IMAGE_PROBE_BINDING_SCHEMA = "axio_fusion_api.image_probe_registry_binding.v1"
IMAGE_PROBE_PROMPT = (
    "Capability control only: generate one simple solid blue square on a white "
    "background. Do not add text, logos, or extra objects."
)
IMAGE_EDIT_PROBE_PROMPT = (
    "Capability control only: change the background of this tiny source image "
    "to solid blue. Do not add text, logos, or extra objects."
)
_IMAGE_PROBE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_TRANSIENT_HTTP_STATUSES = frozenset({401, 403, 408, 409, 425, 429})


def probe_image_capabilities(
    profiles: Sequence[ModelProfile],
    *,
    timeout: float = 90.0,
    client: ImageProviderClient | None = None,
    live: bool = False,
    max_workers: int = 4,
    profile_hashes: Sequence[str] | None = None,
    max_models: int | None = None,
    max_models_per_provider: int | None = None,
    redact_provider_identifiers: bool = False,
) -> dict[str, Any]:
    """Probe declared image operations without inferring unsupported ones."""

    candidates = [
        profile
        for profile in _dedupe_probe_profiles(profiles)
        if _image_probe_candidate(profile)
    ]
    selected, selection_policy = _select_probe_profiles(
        candidates,
        profile_hashes=profile_hashes,
        max_models=max_models,
        max_models_per_provider=max_models_per_provider,
    )
    bounded_timeout = max(1.0, min(90.0, float(timeout)))
    probe_client = client or ImageProviderClient()
    if not live:
        rows = [_skipped_row(profile) for profile in selected]
    else:
        rows = []
        workers = max(1, min(32, int(max_workers or 1), len(selected) or 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _probe_one_profile,
                    profile,
                    timeout=bounded_timeout,
                    client=probe_client,
                ): profile
                for profile in selected
            }
            for future in as_completed(futures):
                rows.append(future.result())
        rows.sort(key=lambda row: str(row.get("profile_id") or ""))

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    payload: dict[str, Any] = {
        "schema": IMAGE_PROBE_SCHEMA,
        "probe_kind": "image_capability",
        "mode": "live" if live else "dry_run",
        "network_calls_performed": bool(live and selected),
        "timeout_seconds": bounded_timeout,
        "max_workers": max(1, int(max_workers or 1)),
        "candidate_model_count_before_selection": len(candidates),
        "model_count": len(selected),
        "status_counts": dict(sorted(status_counts.items())),
        "passed_count": status_counts.get("passed", 0),
        "failed_count": status_counts.get("failed", 0),
        "indeterminate_count": status_counts.get("indeterminate", 0),
        "probes": rows,
        "selection_policy": selection_policy,
        "verification_contract": {
            "requires_explicit_image_model_kind": True,
            "requires_declared_image_transport_and_operations": True,
            "requires_endpoint_bound_profile_identity": True,
            "requires_live_flag_for_network_calls": True,
            "requires_generation_and_edit_operations_separately": True,
            "requires_strict_streaming_when_declared": True,
            "hard_response_timeout_seconds": 90,
            "transient_network_failures_are_indeterminate": True,
            "promotion_requires_all_declared_operations_passed": True,
            "benchmark_prompts_are_never_used": True,
        },
        "raw_probe_prompt_persisted": False,
        "raw_image_bytes_persisted": False,
        "raw_provider_response_persisted": False,
        "secrets_persisted": False,
    }
    if redact_provider_identifiers:
        return redact_image_probe_artifact(payload)
    return payload


def redact_image_probe_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a hash-only image probe receipt."""

    probes = payload.get("probes") if isinstance(payload.get("probes"), list) else []
    redacted = {
        key: value
        for key, value in dict(payload).items()
        if key not in {"probes"}
    }
    redacted["probes"] = [
        _redact_probe_row(row)
        for row in probes
        if isinstance(row, Mapping)
    ]
    redacted["provider_identifier_redaction"] = {
        "provider_names_hashed": True,
        "model_names_hashed": True,
        "profile_ids_hashed": True,
        "endpoint_values_hashed": True,
        "raw_provider_outputs_persisted": False,
        "raw_image_bytes_persisted": False,
        "secrets_persisted": False,
    }
    redacted["raw_provider_names_persisted"] = False
    redacted["raw_provider_model_ids_persisted"] = False
    redacted["raw_provider_outputs_persisted"] = False
    redacted["raw_image_bytes_persisted"] = False
    redacted["secrets_persisted"] = False
    return redacted


def redact_image_probe_artifact_file(path: str | Path) -> dict[str, Any]:
    """Redact an existing image probe without contacting a provider."""

    selected = Path(path)
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("image_probe_artifact_unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("image_probe_artifact_must_be_json_object")
    redacted = redact_image_probe_artifact(payload)
    redacted["redaction_mode"] = "offline_existing_image_probe_artifact"
    redacted["source_artifact_sha256"] = sha256_text(
        stable_json(_probe_redaction_digest_input(payload))
    )
    redacted["network_calls_performed_by_redaction"] = False
    redacted["raw_source_path_persisted"] = False
    return redacted


def build_image_probe_bound_registry(
    *,
    registry_path: str | Path,
    probe_path: str | Path,
) -> dict[str, Any]:
    """Promote only a complete, endpoint-bound image probe cohort.

    The returned ``registry`` is private and keeps the source registry's
    serving aliases. The ``receipt`` is safe to publish. A blocked bind never
    promotes any profile, which makes a transient or partial probe harmless.
    """

    source = _read_json_object(registry_path, "image_probe_registry_unreadable")
    probe = _read_json_object(probe_path, "image_probe_artifact_unreadable")
    source_models = [
        dict(row)
        for row in source.get("models", [])
        if isinstance(row, Mapping)
    ]
    source_profiles = [normalize_profile(row) for row in source_models]
    candidates = [profile for profile in source_profiles if _image_probe_candidate(profile)]
    probe_rows = [row for row in probe.get("probes", []) if isinstance(row, Mapping)]
    candidate_hashes = {sha256_text(profile.profile_id) for profile in candidates}
    # Private artifacts carry the raw profile id; safe artifacts carry its
    # hash. Binding accepts both shapes but never reconstructs an identifier.
    probe_profile_hashes = {
        str(row.get("profile_id_sha256") or sha256_text(str(row.get("profile_id") or "")))
        for row in probe_rows
    }
    by_hash = {
        str(row.get("profile_id_sha256") or sha256_text(str(row.get("profile_id") or ""))): row
        for row in probe_rows
    }
    blockers: list[str] = []
    if str(probe.get("schema") or "") != IMAGE_PROBE_SCHEMA:
        blockers.append("image_probe_schema_invalid")
    if str(probe.get("mode") or "") != "live" or probe.get("network_calls_performed") is not True:
        blockers.append("image_probe_live_evidence_required")
    if not candidates:
        status = "not_applicable"
    else:
        status = "blocked"
        if candidate_hashes != probe_profile_hashes:
            blockers.append("image_probe_profile_set_mismatch")
        for profile in candidates:
            profile_hash = sha256_text(profile.profile_id)
            row = by_hash.get(profile_hash)
            if not isinstance(row, Mapping):
                blockers.append("image_probe_profile_row_missing")
                continue
            if str(row.get("status") or "") != "passed":
                blockers.append("image_probe_profile_not_passed")
            if row.get("all_declared_operations_passed") is not True:
                blockers.append("image_probe_operation_not_passed")
            expected_binding = _endpoint_binding(profile)
            actual_binding = row.get("endpoint_binding") if isinstance(row.get("endpoint_binding"), Mapping) else {}
            if dict(actual_binding) != expected_binding:
                blockers.append("image_probe_endpoint_binding_mismatch")
        if not blockers:
            status = "ready"

    receipt_core = {
        "schema": IMAGE_PROBE_BINDING_SCHEMA,
        "status": status,
        "registry_path_sha256": sha256_text(str(registry_path)),
        "probe_artifact_sha256": sha256_text(stable_json(probe)),
        "candidate_profile_count": len(candidates),
        "probe_profile_count": len(probe_rows),
        "candidate_profile_set_sha256": sha256_text(stable_json(sorted(candidate_hashes))),
        "probe_profile_set_sha256": sha256_text(stable_json(sorted(probe_profile_hashes))),
        "profile_set_matches": candidate_hashes == probe_profile_hashes,
        "promoted_profile_count": len(candidates) if status == "ready" else 0,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_probe_paths_persisted": False,
        "raw_image_bytes_persisted": False,
        "secrets_persisted": False,
    }
    receipt = {
        **receipt_core,
        "blockers": sorted(set(blockers)),
        "binding_digest_sha256": sha256_text(stable_json(receipt_core)),
    }
    if status == "ready":
        promoted_models = []
        for raw, profile in zip(source_models, source_profiles):
            updated = dict(raw)
            if profile in candidates:
                capabilities = dict(profile.image_capabilities)
                capabilities["status"] = "verified"
                updated["image_capabilities"] = capabilities
                updated["image_probe_status"] = "passed"
            promoted_models.append(updated)
        registry = dict(source)
        registry["models"] = promoted_models
        registry["image_probe_binding"] = receipt
        registry["image_capability_registry_ready"] = True
        registry["raw_image_bytes_persisted"] = False
        registry["raw_provider_response_persisted"] = False
        registry["secrets_persisted"] = False
    else:
        registry = dict(source)
        registry["image_probe_binding"] = receipt
        registry["image_capability_registry_ready"] = status == "not_applicable"
    return {
        "schema": IMAGE_PROBE_BINDING_SCHEMA,
        "status": status,
        "registry": registry,
        "receipt": receipt,
        "raw_registry_persisted_in_receipt": False,
        "secrets_persisted": False,
    }


def _image_probe_candidate(profile: ModelProfile) -> bool:
    return bool(
        profile.enabled
        and profile.model_kind in {"image", "multimodal"}
        and profile.image_operations
        and profile.image_capabilities.get("transport")
    )


def _endpoint_binding(profile: ModelProfile) -> dict[str, Any]:
    capabilities = profile.image_capabilities
    return {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "provider_sha256": sha256_text(profile.provider),
        "model_sha256": sha256_text(profile.model),
        "base_url_sha256": sha256_text(_base_url(profile)),
        "api_format": normalize_api_format(profile.api_format),
        "transport": str(capabilities.get("transport") or ""),
        "generation_path": str(capabilities.get("generation_path") or ""),
        "editing_path": str(capabilities.get("editing_path") or ""),
    }


def _probe_one_profile(
    profile: ModelProfile,
    *,
    timeout: float,
    client: ImageProviderClient,
) -> dict[str, Any]:
    started = time.perf_counter()
    declared_operations = list(profile.image_operations)
    unsupported_operations = {
        operation
        for operation in declared_operations
        if str(profile.image_capabilities.get("transport") or "")
        == "responses_image_generation"
        and operation == "editing"
    }
    operations = [operation for operation in declared_operations if operation not in unsupported_operations]
    operation_rows: list[dict[str, Any]] = []
    for operation in declared_operations:
        if operation in unsupported_operations:
            operation_rows.append(
                {
                    "operation": operation,
                    "status": "failed",
                    "reason_code": "operation_not_supported_by_declared_transport",
                    "http_status": None,
                    "latency_ms": 0.0,
                    "stream_requested": False,
                    "stream_observed": False,
                    "stream_protocol": "",
                    "stream_frame_count": 0,
                }
            )
    for operation in operations:
        operation_started = time.perf_counter()
        stream_requested = profile.image_capabilities.get("streaming") is True
        try:
            if operation == "generation":
                result = client.generate(
                    profile,
                    {"model": "axio-terra", "prompt": IMAGE_PROBE_PROMPT, "stream": stream_requested},
                    timeout=timeout,
                )
            else:
                result = client.edit(
                    profile,
                    {
                        "model": "axio-terra",
                        "prompt": IMAGE_EDIT_PROBE_PROMPT,
                        "stream": stream_requested,
                    },
                    [ImagePart("image", "axio-image-probe.png", "image/png", _IMAGE_PROBE_PNG)],
                    timeout=timeout,
                )
            operation_rows.append(
                _successful_operation_row(
                    operation,
                    result,
                    stream_requested=stream_requested,
                    latency_ms=_elapsed_ms(operation_started),
                )
            )
        except ProviderExecutionError as exc:
            operation_rows.append(
                {
                    "operation": operation,
                    "status": _error_status(exc),
                    "reason_code": _error_reason_code(exc),
                    "http_status": int(exc.http_status) if exc.http_status is not None else None,
                    "latency_ms": _elapsed_ms(operation_started),
                    "stream_requested": stream_requested,
                    "stream_observed": False,
                    "stream_protocol": "",
                    "stream_frame_count": 0,
                }
            )
        except Exception:
            operation_rows.append(
                {
                    "operation": operation,
                    "status": "indeterminate",
                    "reason_code": "unexpected_probe_error",
                    "http_status": None,
                    "latency_ms": _elapsed_ms(operation_started),
                    "stream_requested": stream_requested,
                    "stream_observed": False,
                    "stream_protocol": "",
                    "stream_frame_count": 0,
                }
            )
    statuses = {str(row.get("status") or "") for row in operation_rows}
    if "failed" in statuses:
        status = "failed"
    elif "indeterminate" in statuses:
        status = "indeterminate"
    else:
        status = "passed"
    return {
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "api_format": profile.api_format,
        "model_kind": profile.model_kind,
        "transport": str(profile.image_capabilities.get("transport") or ""),
        "operations": declared_operations,
        "image_probe_status_before": profile.image_probe_status,
        "image_capability_status_before": str(profile.image_capabilities.get("status") or ""),
        "endpoint_binding": _endpoint_binding(profile),
        "prompt_sha256": sha256_text(IMAGE_PROBE_PROMPT),
        "edit_prompt_sha256": sha256_text(IMAGE_EDIT_PROBE_PROMPT),
        "status": status,
        "all_declared_operations_passed": bool(operation_rows)
        and all(row.get("status") == "passed" for row in operation_rows),
        "operation_results": operation_rows,
        "latency_ms": _elapsed_ms(started),
        "live_probe_evidence": True,
        "raw_probe_prompt_persisted": False,
        "raw_image_bytes_persisted": False,
        "raw_provider_response_persisted": False,
        "secrets_persisted": False,
    }


def _successful_operation_row(
    operation: str,
    result: ImageProviderResult,
    *,
    stream_requested: bool,
    latency_ms: float,
) -> dict[str, Any]:
    stream_observed = bool(result.stream_events)
    status = "passed"
    reason_code = ""
    if not result.data:
        status = "failed"
        reason_code = "empty_image_result"
    elif stream_requested and not stream_observed:
        status = "failed"
        reason_code = "declared_stream_not_observed"
    return {
        "operation": operation,
        "status": status,
        "reason_code": reason_code,
        "latency_ms": latency_ms,
        "result_count": len(result.data),
        "result_digest_sha256": sha256_text(
            stable_json(
                [
                    {
                        "has_b64_json": isinstance(item.get("b64_json"), str),
                        "has_url": isinstance(item.get("url"), str),
                        "has_revised_prompt": isinstance(item.get("revised_prompt"), str),
                    }
                    for item in result.data
                    if isinstance(item, Mapping)
                ]
            )
        ),
        "stream_requested": stream_requested,
        "stream_observed": stream_observed,
        "stream_protocol": result.stream_protocol,
        "stream_frame_count": len(result.stream_events),
    }


def _skipped_row(profile: ModelProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "api_format": profile.api_format,
        "model_kind": profile.model_kind,
        "transport": str(profile.image_capabilities.get("transport") or ""),
        "operations": list(profile.image_operations),
        "endpoint_binding": _endpoint_binding(profile),
        "status": "skipped",
        "reason_code": "live_flag_required",
        "all_declared_operations_passed": False,
        "live_probe_evidence": False,
        "raw_probe_prompt_persisted": False,
        "raw_image_bytes_persisted": False,
        "raw_provider_response_persisted": False,
        "secrets_persisted": False,
    }


def _error_status(error: ProviderExecutionError) -> str:
    status = int(error.http_status or 0)
    code = str(error.error_code or "").casefold()
    if status >= 500 or status in _TRANSIENT_HTTP_STATUSES:
        return "indeterminate"
    if status >= 400:
        return "failed"
    if any(token in code for token in ("timeout", "url", "network", "transport", "rate_limit")):
        return "indeterminate"
    return "indeterminate"


def _error_reason_code(error: ProviderExecutionError) -> str:
    code = str(error.error_code or "provider_error").strip().lower()
    return code[:80] or "provider_error"


def _elapsed_ms(started: float) -> float:
    return round(max(0.0, (time.perf_counter() - started) * 1000.0), 3)


def _redact_probe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    operations = row.get("operation_results") if isinstance(row.get("operation_results"), list) else []
    endpoint = row.get("endpoint_binding") if isinstance(row.get("endpoint_binding"), Mapping) else {}
    return {
        "profile_id_sha256": sha256_text(str(row.get("profile_id") or ""))
        if row.get("profile_id")
        else str(endpoint.get("profile_id_sha256") or ""),
        "provider_sha256": sha256_text(str(row.get("provider") or ""))
        if row.get("provider")
        else str(endpoint.get("provider_sha256") or ""),
        "model_sha256": sha256_text(str(row.get("model") or ""))
        if row.get("model")
        else str(endpoint.get("model_sha256") or ""),
        "api_format": str(row.get("api_format") or "")[:40],
        "model_kind": str(row.get("model_kind") or "")[:32],
        "transport": str(row.get("transport") or "")[:64],
        "operations": [str(item) for item in row.get("operations", []) if str(item)],
        "endpoint_binding": dict(endpoint),
        "status": str(row.get("status") or "")[:40],
        "all_declared_operations_passed": row.get("all_declared_operations_passed") is True,
        "operation_results": [
            {
                key: value
                for key, value in dict(operation).items()
                if key not in {"result_digest_sha256"} or isinstance(value, str)
            }
            for operation in operations
            if isinstance(operation, Mapping)
        ],
        "latency_ms": row.get("latency_ms"),
        "live_probe_evidence": row.get("live_probe_evidence") is True,
        "prompt_sha256": str(row.get("prompt_sha256") or ""),
        "edit_prompt_sha256": str(row.get("edit_prompt_sha256") or ""),
        "raw_provider_outputs_persisted": False,
        "raw_image_bytes_persisted": False,
        "secrets_persisted": False,
    }


def _probe_redaction_digest_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(payload.get("schema") or ""),
        "probe_kind": str(payload.get("probe_kind") or ""),
        "mode": str(payload.get("mode") or ""),
        "network_calls_performed": payload.get("network_calls_performed") is True,
        "probes": [
            _redact_probe_row(row)
            for row in payload.get("probes", [])
            if isinstance(row, Mapping)
        ],
    }


def _read_json_object(path: str | Path, error_code: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(error_code) from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{error_code}_must_be_object")
    return dict(payload)


__all__ = [
    "IMAGE_PROBE_BINDING_SCHEMA",
    "IMAGE_PROBE_PROMPT",
    "IMAGE_PROBE_SCHEMA",
    "build_image_probe_bound_registry",
    "probe_image_capabilities",
    "redact_image_probe_artifact",
    "redact_image_probe_artifact_file",
]
