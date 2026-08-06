"""Endpoint-bound probing for text-model visual input capability.

Model catalogs and provider metadata are useful priors, but neither proves
that the configured endpoint accepts an image on the configured protocol. This
module sends one small in-memory PNG through the existing strict streaming
provider adapter and promotes only the exact profile/endpoint/protocol tuple
that returns the expected visual answer.

The probe is deliberately separate from the image generation/editing lane:
vision is an input capability of a text or multimodal model, while image
generation is an output capability of an image model. Neither capability is a
benchmark score or a claim about general model quality.
"""

from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

from .latency_policy import (
    PROVIDER_MAX_RESPONSE_LATENCY_MS,
    measured_stream_latency_eligibility,
    streaming_evidence_eligibility,
)
from .providers import (
    HTTPProviderClient,
    ProviderExecutionError,
    _base_url,
    _begin_provider_request_trace,
    _dedupe_probe_profiles,
    _finish_provider_request_trace,
    _probe_row,
    _select_probe_profiles,
)
from .registry import normalize_profile
from .schemas import FusionRequest, ModelProfile, sha256_text, stable_json


VISION_PROBE_SCHEMA = "axio_fusion_api.vision_input_probe.v1"
VISION_PROBE_BINDING_SCHEMA = "axio_fusion_api.vision_input_probe_binding.v1"
VISION_PROBE_MARKER = "AXIO_VISION_COLOR_BLUE"
VISION_PROBE_PROMPT = (
    "Inspect the supplied image. It contains one solid-colored square. "
    "Return exactly AXIO_VISION_COLOR_<COLOR> in uppercase and nothing else."
)
VISION_PROBE_IMAGE_MEDIA_TYPE = "image/png"
VISION_PROBE_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKklEQVR4nGPQa7tHU8QwasGoBaMWjFowasGoBaMWjFowasGoBaMWDBULAAdMSFu4gCLwAAAAAElFTkSuQmCC"
)
VISION_PROBE_IMAGE_BYTES = base64.b64decode(VISION_PROBE_IMAGE_BASE64)
_TRANSIENT_HTTP_STATUSES = frozenset({401, 403, 408, 409, 425, 429})
_VISION_API_FORMATS = frozenset({"chat", "responses", "anthropic", "gemini"})
_VISION_TRANSPORTS = {
    "chat": "chat_image_url",
    "responses": "responses_input_image",
    "anthropic": "anthropic_image_base64",
    "gemini": "gemini_inline_data",
}


def probe_provider_vision_support(
    profiles: Sequence[ModelProfile],
    *,
    timeout: float = 90.0,
    client: HTTPProviderClient | None = None,
    live: bool = False,
    max_workers: int = 4,
    profile_hashes: Sequence[str] | None = None,
    max_models: int | None = None,
    max_models_per_provider: int | None = None,
    redact_provider_identifiers: bool = False,
) -> dict[str, Any]:
    """Probe declared visual-input candidates with a strict streaming turn."""

    candidates = [
        profile
        for profile in _dedupe_probe_profiles(profiles)
        if _vision_probe_candidate(profile)
    ]
    selected, selection_policy = _select_probe_profiles(
        candidates,
        profile_hashes=profile_hashes,
        max_models=max_models,
        max_models_per_provider=max_models_per_provider,
        required_profile_hashes=None,
    )
    bounded_timeout = max(1.0, min(90.0, float(timeout)))
    probe_client = client or HTTPProviderClient(require_streaming=True)
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
        "schema": VISION_PROBE_SCHEMA,
        "probe_kind": "vision_input",
        "mode": "live" if live else "dry_run",
        "network_calls_performed": bool(live and selected),
        "timeout_seconds": bounded_timeout,
        "max_workers": max(1, int(max_workers or 1)),
        "candidate_model_count_before_selection": len(candidates),
        "model_count": len(selected),
        "status_counts": dict(sorted(status_counts.items())),
        "passed_count": status_counts.get("passed", 0),
        "failed_count": status_counts.get("failed", 0),
        "unsupported_count": status_counts.get("unsupported", 0),
        "indeterminate_count": status_counts.get("indeterminate", 0),
        "latency_ineligible_count": status_counts.get("latency_ineligible", 0),
        "probes": rows,
        "selection_policy": selection_policy,
        "verification_contract": {
            "requires_explicit_supports_vision_prior": True,
            "requires_text_or_multimodal_model_kind": True,
            "requires_one_in_memory_image_input": True,
            "requires_protocol_local_image_wire_shape": True,
            "requires_endpoint_bound_profile_identity": True,
            "requires_live_flag_for_network_calls": True,
            "requires_strict_sse_or_ndjson_streaming": True,
            "requires_exact_visual_marker": True,
            "hard_response_timeout_seconds": 90,
            "transient_network_failures_are_indeterminate": True,
            "benchmark_prompts_or_labels_used": False,
            "raw_probe_prompt_persisted": False,
            "raw_image_bytes_persisted": False,
            "raw_provider_output_persisted": False,
        },
        "raw_probe_prompt_persisted": False,
        "raw_image_bytes_persisted": False,
        "raw_provider_response_persisted": False,
        "secrets_persisted": False,
    }
    if redact_provider_identifiers:
        return redact_vision_probe_artifact(payload)
    return payload


def _vision_probe_candidate(profile: ModelProfile) -> bool:
    api_format = _normalized_vision_api_format(profile.api_format)
    return bool(
        profile.enabled
        and profile.supports_vision is True
        and profile.model_kind in {"text", "multimodal"}
        and api_format in _VISION_API_FORMATS
    )


def _probe_one_profile(
    profile: ModelProfile,
    *,
    timeout: float,
    client: HTTPProviderClient,
) -> dict[str, Any]:
    started = time.perf_counter()
    _begin_provider_request_trace()
    request = FusionRequest(
        model="axio-fast",
        prompt=VISION_PROBE_PROMPT,
        content_parts=(
            {"type": "text", "text": VISION_PROBE_PROMPT},
            {
                "type": "image",
                "source": "base64",
                "media_type": VISION_PROBE_IMAGE_MEDIA_TYPE,
                "data": VISION_PROBE_IMAGE_BASE64,
            },
        ),
        max_output_tokens=32,
        temperature=0.0,
    )
    try:
        completion = client.complete_turn(
            profile,
            request,
            prompt=request.prompt,
            system="You are an endpoint-bound visual input capability probe.",
            timeout=timeout,
            # Responses adapters must not flatten an image request into their
            # text-only compatibility fallback during capability calibration.
            strict_wire=True,
        )
        request_receipt = _finish_provider_request_trace()
        output = str(completion.text or "")
        marker_valid = output.strip() == VISION_PROBE_MARKER
        strict_stream = _strict_vision_stream_evidence(request_receipt)
        latency_ms = _elapsed_ms(started)
        latency_eligible = _vision_latency_eligible(latency_ms=latency_ms)
        if marker_valid and strict_stream and latency_eligible:
            status = "passed"
            reason_code = "visual_marker_and_strict_stream_valid"
        elif not latency_eligible:
            status = "latency_ineligible"
            reason_code = "provider_response_latency_exceeded_90s"
        elif not strict_stream:
            status = "failed"
            reason_code = _strict_stream_reason_code(request_receipt)
        else:
            status = "failed"
            reason_code = "visual_marker_invalid"
        return _vision_probe_row(
            profile,
            status,
            latency_ms=latency_ms,
            output=output,
            reason_code=reason_code,
            marker_valid=marker_valid,
            request_receipt=request_receipt,
        )
    except ProviderExecutionError as exc:
        request_receipt = _finish_provider_request_trace()
        return _vision_probe_row(
            profile,
            _error_status(exc),
            latency_ms=_elapsed_ms(started),
            output="",
            reason_code=str(exc.error_code or "provider_error")[:120],
            error_type=type(exc).__name__,
            error_code=exc.error_code,
            http_status=exc.http_status,
            request_receipt=request_receipt,
        )
    except Exception as exc:  # noqa: BLE001 - provider boundary
        _finish_provider_request_trace()
        return _vision_probe_row(
            profile,
            "indeterminate",
            latency_ms=_elapsed_ms(started),
            output="",
            reason_code="provider_boundary_exception",
            error_type=type(exc).__name__,
            error_code=type(exc).__name__,
        )


def _vision_probe_row(
    profile: ModelProfile,
    status: str,
    *,
    latency_ms: float,
    output: str,
    reason_code: str = "",
    marker_valid: bool = False,
    error_type: str = "",
    error_code: str = "",
    http_status: int | None = None,
    request_receipt: Mapping[str, Any] | None = None,
    probe_mode: str = "live",
) -> dict[str, Any]:
    row = _probe_row(
        profile,
        status,
        latency_ms=latency_ms,
        error_type=error_type,
        error_code=error_code,
        http_status=http_status,
        output=output,
        request_receipt=request_receipt,
        probe_mode=probe_mode,
    )
    row.update(
        {
            "probe_kind": "vision_input",
            "model_kind": profile.model_kind,
            "vision_transport": _vision_transport(profile),
            "vision_probe_status_before": profile.vision_probe_status,
            "vision_capability_source_before": profile.vision_capability_source,
            "reason_code": str(reason_code or "")[:120],
            "marker_sha256": sha256_text(VISION_PROBE_MARKER),
            "marker_valid": bool(marker_valid),
            "input_image_sha256": sha256_text(VISION_PROBE_IMAGE_BASE64),
            "endpoint_binding": vision_input_probe_binding(profile),
            "raw_probe_prompt_persisted": False,
            "raw_image_bytes_persisted": False,
        }
    )
    return row


def _skipped_row(profile: ModelProfile) -> dict[str, Any]:
    return _vision_probe_row(
        profile,
        "skipped",
        latency_ms=0.0,
        output="",
        reason_code="live_flag_required",
        marker_valid=False,
        request_receipt={"strict_streaming_requested": True},
        probe_mode="dry_run",
    )


def _error_status(error: ProviderExecutionError) -> str:
    status = int(error.http_status or 0)
    code = str(error.error_code or "").casefold()
    if status >= 500 or status in _TRANSIENT_HTTP_STATUSES:
        return "indeterminate"
    if status in {400, 404, 405, 415, 422}:
        return "unsupported"
    if status >= 400:
        return "failed"
    if any(token in code for token in ("timeout", "url", "network", "transport", "rate_limit")):
        return "indeterminate"
    return "indeterminate"


def _vision_transport(profile: ModelProfile) -> str:
    return _VISION_TRANSPORTS.get(_normalized_vision_api_format(profile.api_format), "")


def _strict_vision_stream_evidence(row: Mapping[str, Any]) -> bool:
    """Require a framed stream and reject the ordinary JSON fallback path."""

    protocol = str(row.get("stream_protocol") or "").strip().casefold()
    try:
        frame_count = int(row.get("stream_frame_count") or 0)
    except (TypeError, ValueError):
        frame_count = 0
    return bool(
        row.get("stream_requested") is True
        and row.get("strict_streaming_requested") is True
        and row.get("stream_observed") is True
        and row.get("stream_fallback_used") is not True
        and protocol in {"sse", "ndjson"}
        and frame_count >= 1
    )


def _strict_stream_reason_code(row: Mapping[str, Any]) -> str:
    if row.get("stream_fallback_used") is True:
        return "ordinary_json_stream_fallback_used"
    if row.get("stream_observed") is not True:
        return "strict_stream_not_observed"
    protocol = str(row.get("stream_protocol") or "").strip().casefold()
    if protocol not in {"sse", "ndjson"}:
        return "stream_protocol_unverified"
    try:
        frame_count = int(row.get("stream_frame_count") or 0)
    except (TypeError, ValueError):
        frame_count = 0
    if frame_count < 1:
        return "stream_frame_evidence_missing"
    return "strict_stream_contract_invalid"


def _vision_latency_eligible(*, latency_ms: Any) -> bool:
    try:
        value = float(latency_ms)
    except (TypeError, ValueError):
        return False
    return 0.0 <= value <= PROVIDER_MAX_RESPONSE_LATENCY_MS


def _normalized_vision_api_format(value: Any) -> str:
    raw = str(value or "").strip().casefold().replace("_", "-")
    if raw in {"chat", "chat/completions", "chat-completions", "openai-chat"}:
        return "chat"
    if raw in {"responses", "response", "responses-api"}:
        return "responses"
    if raw in {"anthropic", "messages", "anthropic/messages", "anthropic-messages"}:
        return "anthropic"
    if raw in {"gemini", "google", "google-gemini", "gemini/generatecontent"}:
        return "gemini"
    return raw


def vision_input_probe_binding(profile: ModelProfile) -> dict[str, Any]:
    """Return a hash-only binding for one exact visual-input wire target."""

    return {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "provider_sha256": sha256_text(profile.provider),
        "model_sha256": sha256_text(profile.model),
        "base_url_sha256": sha256_text(_base_url(profile)),
        "api_format": _normalized_vision_api_format(profile.api_format),
        "transport": _vision_transport(profile),
        "input_image_media_type": VISION_PROBE_IMAGE_MEDIA_TYPE,
        "input_image_sha256": sha256_text(VISION_PROBE_IMAGE_BASE64),
        "marker_sha256": sha256_text(VISION_PROBE_MARKER),
        "prompt_sha256": sha256_text(VISION_PROBE_PROMPT),
    }


def vision_input_probe_binding_matches(
    profile: ModelProfile,
    row: Mapping[str, Any],
) -> bool:
    """Return whether a row belongs to the profile's current visual endpoint."""

    observed = row.get("endpoint_binding")
    return bool(
        isinstance(observed, Mapping)
        and dict(observed) == vision_input_probe_binding(profile)
    )


def vision_input_probe_row_passed(
    profile: ModelProfile,
    row: Mapping[str, Any],
) -> bool:
    """Validate one endpoint-bound live visual-input probe row."""

    latency = row.get("latency_ms")
    return bool(
        str(row.get("probe_kind") or "").strip().casefold() == "vision_input"
        and str(row.get("status") or "").strip().casefold() == "passed"
        and row.get("live_probe_evidence") is True
        and row.get("marker_valid") is True
        and vision_input_probe_binding_matches(profile, row)
        and _strict_vision_stream_evidence(row)
        and streaming_evidence_eligibility(row).get("eligible") is True
        and measured_stream_latency_eligibility(row).get("eligible") is True
        and _vision_latency_eligible(latency_ms=latency)
    )


def vision_input_probe_status(
    profile: ModelProfile,
    rows: Sequence[Mapping[str, Any]],
) -> str | None:
    """Aggregate exact endpoint-bound visual probe rows conservatively.

    A successful status requires every selected sample to pass. Any explicit
    protocol/content failure wins over a transient or latency-indeterminate
    result; transient and slow results remain ``indeterminate`` so production
    routing can fail closed without misclassifying them as unsupported.
    """

    exact_rows = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and str(row.get("probe_kind") or "").strip().casefold() == "vision_input"
        and row.get("live_probe_evidence") is True
        and vision_input_probe_binding_matches(profile, row)
    ]
    if not exact_rows:
        return None
    if all(vision_input_probe_row_passed(profile, row) for row in exact_rows):
        return "passed"
    statuses = {
        str(row.get("status") or "indeterminate").strip().casefold()
        for row in exact_rows
    }
    if "unsupported" in statuses:
        return "unsupported"
    if "failed" in statuses:
        return "failed"
    return "indeterminate"


def build_vision_probe_bound_registry(
    *,
    registry_path: str | Path,
    probe_path: str | Path,
) -> dict[str, Any]:
    """Promote only a complete, endpoint-bound visual-input probe cohort."""

    source = _read_json_object(registry_path, "vision_probe_registry_unreadable")
    probe = _read_json_object(probe_path, "vision_probe_artifact_unreadable")
    source_models = [
        dict(row) for row in source.get("models", []) if isinstance(row, Mapping)
    ]
    source_profiles = [normalize_profile(row) for row in source_models]
    candidates = [profile for profile in source_profiles if _vision_probe_candidate(profile)]
    probe_rows = [row for row in probe.get("probes", []) if isinstance(row, Mapping)]
    candidate_hashes = {sha256_text(profile.profile_id) for profile in candidates}
    probe_profile_hashes = {
        str(row.get("profile_id_sha256") or sha256_text(str(row.get("profile_id") or "")))
        for row in probe_rows
    }
    by_hash = {
        str(row.get("profile_id_sha256") or sha256_text(str(row.get("profile_id") or ""))): row
        for row in probe_rows
    }
    blockers: list[str] = []
    if str(probe.get("schema") or "") != VISION_PROBE_SCHEMA:
        blockers.append("vision_probe_schema_invalid")
    if str(probe.get("mode") or "") != "live" or probe.get("network_calls_performed") is not True:
        blockers.append("vision_probe_live_evidence_required")
    if not candidates:
        status = "not_applicable"
    else:
        status = "blocked"
        if candidate_hashes != probe_profile_hashes:
            blockers.append("vision_probe_profile_set_mismatch")
        for profile in candidates:
            profile_hash = sha256_text(profile.profile_id)
            row = by_hash.get(profile_hash)
            if not isinstance(row, Mapping):
                blockers.append("vision_probe_profile_row_missing")
                continue
            if str(row.get("status") or "") != "passed":
                blockers.append("vision_probe_profile_not_passed")
            if not vision_input_probe_row_passed(profile, row):
                if row.get("marker_valid") is not True:
                    blockers.append("vision_probe_marker_invalid")
                if not _strict_vision_stream_evidence(row):
                    blockers.append("vision_probe_strict_stream_invalid")
                if measured_stream_latency_eligibility(row).get("eligible") is not True:
                    blockers.append("vision_probe_latency_ineligible")
            if not vision_input_probe_binding_matches(profile, row):
                blockers.append("vision_probe_endpoint_binding_mismatch")
        if not blockers:
            status = "ready"

    receipt_core = {
        "schema": VISION_PROBE_BINDING_SCHEMA,
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
        "raw_probe_prompt_persisted": False,
        "raw_image_bytes_persisted": False,
        "secrets_persisted": False,
    }
    receipt = {
        **receipt_core,
        "blockers": sorted(set(blockers)),
        "binding_digest_sha256": sha256_text(stable_json(receipt_core)),
    }
    registry = dict(source)
    if status == "ready":
        promoted_models = []
        candidates_by_id = {profile.profile_id: profile for profile in candidates}
        for raw, profile in zip(source_models, source_profiles):
            updated = dict(raw)
            if profile.profile_id in candidates_by_id:
                updated["supports_vision"] = True
                updated["vision_probe_status"] = "passed"
                updated["vision_capability_source"] = "operational_probe"
            promoted_models.append(updated)
        registry["models"] = promoted_models
        registry["vision_probe_binding"] = receipt
        registry["vision_capability_registry_ready"] = True
    else:
        registry["vision_probe_binding"] = receipt
        registry["vision_capability_registry_ready"] = status == "not_applicable"
    registry["raw_probe_prompt_persisted"] = False
    registry["raw_image_bytes_persisted"] = False
    registry["raw_provider_response_persisted"] = False
    registry["secrets_persisted"] = False
    return {
        "schema": VISION_PROBE_BINDING_SCHEMA,
        "status": status,
        "registry": registry,
        "receipt": receipt,
        "raw_registry_persisted_in_receipt": False,
        "secrets_persisted": False,
    }


def redact_vision_probe_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a safe hash-only visual-input probe receipt."""

    probes = payload.get("probes") if isinstance(payload.get("probes"), list) else []
    redacted = {key: value for key, value in dict(payload).items() if key != "probes"}
    redacted["probes"] = [_redact_vision_probe_row(row) for row in probes if isinstance(row, Mapping)]
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
    redacted["raw_probe_prompt_persisted"] = False
    redacted["raw_image_bytes_persisted"] = False
    redacted["secrets_persisted"] = False
    return redacted


def redact_vision_probe_artifact_file(path: str | Path) -> dict[str, Any]:
    """Redact an existing visual-input probe without network access."""

    selected = Path(path)
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("vision_probe_artifact_unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("vision_probe_artifact_must_be_json_object")
    redacted = redact_vision_probe_artifact(payload)
    redacted["redaction_mode"] = "offline_existing_vision_probe_artifact"
    redacted["source_artifact_sha256"] = sha256_text(
        stable_json(_probe_redaction_digest_input(payload))
    )
    redacted["network_calls_performed_by_redaction"] = False
    redacted["raw_source_path_persisted"] = False
    return redacted


def _redact_vision_probe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    endpoint = row.get("endpoint_binding") if isinstance(row.get("endpoint_binding"), Mapping) else {}
    profile_id = str(row.get("profile_id") or "")
    provider = str(row.get("provider") or "")
    model = str(row.get("model") or "")
    return {
        "profile_id_sha256": sha256_text(profile_id) if profile_id else str(endpoint.get("profile_id_sha256") or ""),
        "provider_sha256": sha256_text(provider) if provider else str(endpoint.get("provider_sha256") or ""),
        "model_sha256": sha256_text(model) if model else str(endpoint.get("model_sha256") or ""),
        "api_format": str(row.get("api_format") or "")[:40],
        "model_kind": str(row.get("model_kind") or "")[:32],
        "probe_kind": "vision_input",
        "status": str(row.get("status") or "")[:40],
        "vision_transport": str(row.get("vision_transport") or "")[:80],
        "vision_probe_status_before": str(row.get("vision_probe_status_before") or "")[:32],
        "vision_capability_source_before": str(row.get("vision_capability_source_before") or "")[:64],
        "reason_code": str(row.get("reason_code") or "")[:120],
        "marker_sha256": str(row.get("marker_sha256") or ""),
        "marker_valid": row.get("marker_valid") is True,
        "input_image_sha256": str(row.get("input_image_sha256") or ""),
        "endpoint_binding": dict(endpoint),
        "latency_ms": row.get("latency_ms"),
        "latency_eligibility": dict(row.get("latency_eligibility") or {}) if isinstance(row.get("latency_eligibility"), Mapping) else {},
        "stream_requested": row.get("stream_requested") is True,
        "stream_observed": row.get("stream_observed") is True,
        "stream_fallback_used": row.get("stream_fallback_used") is True,
        "stream_protocol": str(row.get("stream_protocol") or "")[:32],
        "stream_frame_count": int(row.get("stream_frame_count") or 0),
        "strict_streaming_requested": row.get("strict_streaming_requested") is True,
        "provider_request_count": int(row.get("provider_request_count") or 0),
        "provider_request_success_count": int(row.get("provider_request_success_count") or 0),
        "provider_request_failure_count": int(row.get("provider_request_failure_count") or 0),
        "error_type": str(row.get("error_type") or "")[:120],
        "error_code": str(row.get("error_code") or "")[:120],
        "http_status": row.get("http_status"),
        "output_sha256": str(row.get("output_sha256") or ""),
        "live_probe_evidence": row.get("live_probe_evidence") is True,
        "raw_provider_outputs_persisted": False,
        "raw_probe_prompt_persisted": False,
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
            _redact_vision_probe_row(row)
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


def _elapsed_ms(started: float) -> float:
    return round(max(0.0, (time.perf_counter() - started) * 1000.0), 3)


__all__ = [
    "VISION_PROBE_BINDING_SCHEMA",
    "VISION_PROBE_IMAGE_BASE64",
    "VISION_PROBE_SCHEMA",
    "VISION_PROBE_MARKER",
    "VISION_PROBE_PROMPT",
    "build_vision_probe_bound_registry",
    "probe_provider_vision_support",
    "redact_vision_probe_artifact",
    "redact_vision_probe_artifact_file",
    "vision_input_probe_binding",
    "vision_input_probe_binding_matches",
    "vision_input_probe_row_passed",
    "vision_input_probe_status",
]
