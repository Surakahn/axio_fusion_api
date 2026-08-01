from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .content_contract import (
    content_parts_safe_summary,
    has_non_text_content,
    has_visual_content,
    normalize_content_parts,
    normalize_structured_output,
    structured_output_safe_summary,
)


PUBLIC_MODELS = ("axio-fast", "axio-terra", "axio-pro")
PUBLIC_MODEL_ALIASES = {
    "fast": "axio-fast",
    "terra": "axio-terra",
    "budget": "axio-terra",
    "balanced": "axio-terra",
    "high": "axio-pro",
    "pro": "axio-pro",
    "fusion": "axio-terra",
    "openrouter/fusion": "axio-terra",
    "openrouter:fusion": "axio-terra",
    "axio": "axio-terra",
    "axio-fusion": "axio-terra",
}

CAPABILITY_AXES = (
    "science_knowledge",
    "multilingual",
    "code",
    "math",
    "logic",
    "agentic_tool_calling",
    "daily_work",
    "structured_output",
    "critique",
    "long_context",
    "current_information",
)

TOOL_CAPABILITY_STATES = ("proven", "unproven", "failed")

# Image models live in the same provider registry as text models, but their
# admission contract is deliberately separate.  A profile must explicitly
# declare a supported image operation and its transport before the image
# router can use it.  This prevents a model-list name such as ``gpt-image-*``
# from accidentally entering the text Fusion pool or being treated as a
# generic chat model.
IMAGE_MODEL_KINDS = ("text", "multimodal", "image")
IMAGE_OPERATIONS = ("generation", "editing")
IMAGE_TRANSPORTS = ("images_api", "responses_image_generation")
IMAGE_CAPABILITY_STATUSES = ("unknown", "candidate", "verified", "unsupported")
_IMAGE_DEFAULT_GENERATION_PATH = "/images/generations"
_IMAGE_DEFAULT_EDIT_PATH = "/images/edits"

# Axio keeps one protocol-neutral request field and maps it only through a
# model-level, verified transport declaration.  The set is intentionally the
# union of current OpenAI Responses reasoning levels; an individual profile
# still has to declare the smaller subset its upstream actually accepts.
REASONING_EFFORT_LEVELS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
_REASONING_EFFORT_ORDER = {
    effort: index for index, effort in enumerate(REASONING_EFFORT_LEVELS)
}
SCREENING_REASONING_STATUSES = ("candidate", "unsupported", "unknown")
SCREENING_REASONING_TRANSPORTS = (
    "chat_reasoning_effort",
    "responses_reasoning",
    "responses_reasoning_effort",
)
SCREENING_REASONING_COST_MODELS = (
    "provider_documented",
    "monotonic_effort_policy",
    "unknown",
)
_REASONING_TRANSPORT_FORMATS = {
    "chat_reasoning_effort": "chat",
    "responses_reasoning": "responses",
    # Some Responses-compatible gateways retain NVIDIA NIM's top-level
    # spelling instead of the standard nested ``reasoning.effort`` object.
    # This remains profile-local and is never inferred from a provider name.
    "responses_reasoning_effort": "responses",
}
_REASONING_TRANSPORT_STATUSES = frozenset(
    {"unknown", "candidate", "verified", "unsupported"}
)

# Traffic control is deliberately a closed profile-level contract. It controls
# local scheduling only; it cannot add provider request-body fields or expose
# endpoint and credential values in a persisted artifact.
_TRAFFIC_CONTROL_SCOPES = frozenset({"profile", "channel"})
_TRAFFIC_CONTROL_KEY_POOLS = frozenset({"shared", "independent"})
_DEFAULT_TRAFFIC_CONTROL = {
    "scope": "profile",
    "max_in_flight": 0,
    "min_request_interval_ms": 0,
    "post_rate_limit_min_request_interval_ms": 1_000,
    "rate_limit_key_pool": "shared",
    "fallback_cooldown_ms": 5_000,
    "max_cooldown_ms": 60_000,
}


def normalize_reasoning_effort(value: Any) -> str:
    """Return one supported logical reasoning level or an empty value.

    Invalid caller input is deliberately omitted instead of being copied to an
    upstream request.  This keeps public compatibility permissive while
    preventing an arbitrary vendor-specific value from crossing the provider
    boundary.
    """

    normalized = str(value or "").strip().casefold().replace("_", "-")
    return normalized if normalized in _REASONING_EFFORT_ORDER else ""


def normalize_screening_reasoning_capability(
    value: Any,
    *,
    api_format: Any = "",
) -> dict[str, Any]:
    """Normalize the research Agent's model-local reasoning declaration.

    This is a research receipt, not proof that the upstream accepts the
    parameter.  Live endpoint probing is the only operation that can promote
    a ``candidate`` declaration to ``verified`` in ``reasoning_transport``.
    Keeping this shape closed prevents research output from injecting an
    arbitrary provider payload path into the serving adapter.
    """

    raw = value if isinstance(value, Mapping) else {}
    status = str(raw.get("status") or "unknown").strip().casefold()
    if status not in SCREENING_REASONING_STATUSES:
        status = "unknown"
    transport = str(raw.get("transport") or "").strip().casefold()
    if transport not in SCREENING_REASONING_TRANSPORTS:
        transport = ""
    format_name = _reasoning_transport_api_format(api_format)
    transport_format = _REASONING_TRANSPORT_FORMATS.get(transport, "")
    api_format_compatible = bool(
        transport_format and transport_format == format_name
    )
    if not api_format_compatible:
        transport = ""
    native_efforts = _reasoning_effort_values(
        raw.get("native_efforts", raw.get("nativeEfforts", ()))
    )
    native_efforts.sort(key=lambda item: _REASONING_EFFORT_ORDER[item])
    native_set = set(native_efforts)
    raw_map = raw.get("effort_map", raw.get("effortMap", {}))
    effort_map: dict[str, str] = {}
    if isinstance(raw_map, Mapping):
        for source, target in raw_map.items():
            requested = normalize_reasoning_effort(source)
            effective = normalize_reasoning_effort(target)
            if (
                requested
                and effective
                and effective in native_set
                and _REASONING_EFFORT_ORDER[effective]
                <= _REASONING_EFFORT_ORDER[requested]
            ):
                effort_map[requested] = effective
    evidence_ids = _normalized_string_list(raw.get("evidence_ids", raw.get("evidenceIds", ())))
    cost_evidence_ids = _normalized_string_list(
        raw.get("cost_evidence_ids", raw.get("costEvidenceIds", ()))
    )
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence != confidence or confidence in (float("inf"), float("-inf")):
        confidence = 0.0
    token_cost_model = str(
        raw.get("token_cost_model", raw.get("tokenCostModel", "unknown"))
        or "unknown"
    ).strip().casefold()
    latency_cost_model = str(
        raw.get("latency_cost_model", raw.get("latencyCostModel", "unknown"))
        or "unknown"
    ).strip().casefold()
    if token_cost_model not in SCREENING_REASONING_COST_MODELS:
        token_cost_model = "unknown"
    if latency_cost_model not in SCREENING_REASONING_COST_MODELS:
        latency_cost_model = "unknown"
    return {
        "status": status,
        "transport": transport,
        "api_format": format_name,
        "api_format_compatible": api_format_compatible,
        "native_efforts": native_efforts,
        "effort_map": dict(sorted(effort_map.items())),
        "evidence_ids": evidence_ids,
        "confidence": round(max(0.0, min(1.0, confidence)), 6),
        "token_cost_model": token_cost_model,
        "latency_cost_model": latency_cost_model,
        "cost_evidence_ids": cost_evidence_ids,
    }


def _normalized_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace(";", ",").split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        values = []
    normalized: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text[:160])
    return normalized[:24]


def _reasoning_transport_api_format(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("_", "-")
    if normalized in {
        "chat",
        "chat/completion",
        "chat/completions",
        "chat-completions",
        "openai",
        "openai-chat",
    }:
        return "chat"
    if normalized in {"responses", "response", "responses-api"}:
        return "responses"
    return normalized


def _reasoning_effort_values(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = value.replace(";", ",").split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    else:
        raw_values = []
    normalized: list[str] = []
    for raw in raw_values:
        effort = normalize_reasoning_effort(raw)
        if effort and effort not in normalized:
            normalized.append(effort)
    return normalized


def _normalize_reasoning_transport(
    value: Any,
    *,
    api_format: Any,
) -> dict[str, Any]:
    """Normalize a declarative, profile-local wire capability declaration.

    The configuration intentionally has no generic payload path or arbitrary
    extra-body escape hatch.  A verified declaration can select only the two
    audited transports below, and only for its matching provider protocol.
    """

    raw = value if isinstance(value, Mapping) else {}
    status = str(raw.get("status") or "unknown").strip().casefold()
    if status not in _REASONING_TRANSPORT_STATUSES:
        status = "unknown"
    transport = str(raw.get("transport") or "").strip().casefold()
    if transport not in _REASONING_TRANSPORT_FORMATS:
        transport = ""
    supported_efforts = _reasoning_effort_values(
        raw.get("supported_efforts", raw.get("supportedEfforts", ()))
    )
    supported_set = set(supported_efforts)
    raw_map = raw.get("effort_map", raw.get("effortMap", {}))
    effort_map: dict[str, str] = {}
    if isinstance(raw_map, Mapping):
        for source, target in raw_map.items():
            requested = normalize_reasoning_effort(source)
            effective = normalize_reasoning_effort(target)
            # A transport map is only a declared downgrade.  It cannot turn a
            # caller's upper bound into a more expensive reasoning request.
            if (
                requested
                and effective
                and effective in supported_set
                and _REASONING_EFFORT_ORDER[effective]
                <= _REASONING_EFFORT_ORDER[requested]
            ):
                effort_map[requested] = effective
    expected_format = _REASONING_TRANSPORT_FORMATS.get(transport, "")
    protocol_compatible = bool(
        expected_format
        and expected_format == _reasoning_transport_api_format(api_format)
    )
    normalized = {
        "status": status,
        "transport": transport,
        "supported_efforts": supported_efforts,
        "effort_map": dict(sorted(effort_map.items())),
        "api_format_compatible": protocol_compatible,
    }
    # A provider-level declaration is only a transport prior.  ``model`` is
    # the sole scope that may survive research uncertainty and reach the
    # endpoint-bound reasoning probe; keeping the marker optional preserves
    # the existing provider-level configuration shape.
    if str(raw.get("scope") or "").strip().casefold() == "model":
        normalized["scope"] = "model"
    return normalized


def _bounded_traffic_control_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_traffic_control(value: Any) -> dict[str, Any]:
    """Normalize the local provider-scheduling contract without escape hatches."""

    raw = value if isinstance(value, Mapping) else {}
    scope = str(raw.get("scope") or _DEFAULT_TRAFFIC_CONTROL["scope"]).strip().casefold()
    if scope not in _TRAFFIC_CONTROL_SCOPES:
        scope = _DEFAULT_TRAFFIC_CONTROL["scope"]
    key_pool = str(
        raw.get("rate_limit_key_pool", raw.get("rateLimitKeyPool"))
        or _DEFAULT_TRAFFIC_CONTROL["rate_limit_key_pool"]
    ).strip().casefold()
    if key_pool not in _TRAFFIC_CONTROL_KEY_POOLS:
        key_pool = _DEFAULT_TRAFFIC_CONTROL["rate_limit_key_pool"]
    max_in_flight = _bounded_traffic_control_int(
        raw.get("max_in_flight", raw.get("maxInFlight")),
        default=_DEFAULT_TRAFFIC_CONTROL["max_in_flight"],
        minimum=0,
        maximum=32,
    )
    min_interval = _bounded_traffic_control_int(
        raw.get("min_request_interval_ms", raw.get("minRequestIntervalMs")),
        default=_DEFAULT_TRAFFIC_CONTROL["min_request_interval_ms"],
        minimum=0,
        maximum=90_000,
    )
    post_rate_limit_interval = _bounded_traffic_control_int(
        raw.get(
            "post_rate_limit_min_request_interval_ms",
            raw.get("postRateLimitMinRequestIntervalMs"),
        ),
        default=_DEFAULT_TRAFFIC_CONTROL[
            "post_rate_limit_min_request_interval_ms"
        ],
        minimum=0,
        maximum=90_000,
    )
    fallback_cooldown = _bounded_traffic_control_int(
        raw.get("fallback_cooldown_ms", raw.get("fallbackCooldownMs")),
        default=_DEFAULT_TRAFFIC_CONTROL["fallback_cooldown_ms"],
        minimum=1,
        maximum=90_000,
    )
    max_cooldown = _bounded_traffic_control_int(
        raw.get("max_cooldown_ms", raw.get("maxCooldownMs")),
        default=_DEFAULT_TRAFFIC_CONTROL["max_cooldown_ms"],
        minimum=fallback_cooldown,
        maximum=90_000,
    )
    return {
        "scope": scope,
        "max_in_flight": max_in_flight,
        "min_request_interval_ms": min_interval,
        "post_rate_limit_min_request_interval_ms": post_rate_limit_interval,
        "rate_limit_key_pool": key_pool,
        "fallback_cooldown_ms": fallback_cooldown,
        "max_cooldown_ms": max_cooldown,
    }

# Provider error values cross a trust boundary.  They are useful for an
# operator to distinguish configuration, authentication, transport, and
# framing failures, but arbitrary gateway-provided strings must never enter a
# public response, safe trace, or benchmark artifact.
SAFE_PROVIDER_ERROR_CODES = frozenset(
    {
        "api_key_missing",
        "base_url_invalid",
        "base_url_missing",
        "empty_provider_response",
        "empty_provider_stream",
        "fusion_request_deadline_exhausted",
        "http_error",
        "invalid_json",
        "invalid_stream_json",
        "invalid_stream_line",
        "network_mode_invalid",
        "non_object_json",
        "non_object_stream_json",
        "OSError",
        "provider_request_failed",
        "provider_request_timeout",
        "provider_response_timeout_exceeded_90s",
        "proxy_unavailable",
        "rate_limit_cooldown_exceeded",
        "stream_framing_unverified",
        "TimeoutError",
        "tool_call_without_text",
        "unframed_stream_response",
        "URLError",
    }
)


def safe_provider_error_code(value: Any) -> str:
    """Return a closed-form provider error code suitable for safe receipts."""

    code = str(value or "").strip()
    if not code:
        return ""
    return code if code in SAFE_PROVIDER_ERROR_CODES else "unknown_provider_error"


def safe_provider_http_status(value: Any) -> int | None:
    """Accept only ordinary HTTP status values in safe diagnostics."""

    if isinstance(value, bool):
        return None
    try:
        status = int(value)
    except (TypeError, ValueError):
        return None
    return status if 100 <= status <= 599 else None


def safe_provider_error_class(
    error_code: Any,
    http_status: Any = None,
) -> str:
    """Map a provider failure to a small, non-provider-specific taxonomy."""

    code = safe_provider_error_code(error_code)
    status = safe_provider_http_status(http_status)
    if code in {"api_key_missing", "base_url_missing", "base_url_invalid"}:
        return "configuration"
    if status in {401, 403}:
        return "authentication_or_authorization"
    if status == 429:
        return "rate_limited"
    if code == "rate_limit_cooldown_exceeded":
        return "rate_limited"
    if status is not None and 400 <= status <= 499:
        return "provider_http_4xx"
    if status is not None and 500 <= status <= 599:
        return "provider_http_5xx"
    if code == "http_error":
        return "provider_http_error"
    if code in {
        "TimeoutError",
        "fusion_request_deadline_exhausted",
        "provider_request_timeout",
        "provider_response_timeout_exceeded_90s",
    }:
        return "timeout"
    if code in {"URLError", "OSError", "proxy_unavailable", "network_mode_invalid"}:
        return "transport_or_network_policy"
    if code in {
        "invalid_json",
        "invalid_stream_json",
        "invalid_stream_line",
        "non_object_json",
        "non_object_stream_json",
        "stream_framing_unverified",
        "unframed_stream_response",
    }:
        return "stream_or_response_protocol"
    if code in {"empty_provider_response", "empty_provider_stream"}:
        return "empty_provider_output"
    if code == "tool_call_without_text":
        return "tool_response_mismatch"
    if code == "provider_request_failed":
        return "provider_request_failed"
    if code == "unknown_provider_error":
        return "unknown_provider_error"
    return ""


def _normalized_tool_capability_state(value: Any, *, supports_tools: bool) -> str:
    state = str(value or "").strip().lower()
    if state not in TOOL_CAPABILITY_STATES:
        return "proven" if supports_tools else "unproven"
    return state


def _normalize_model_kind(value: Any) -> str:
    normalized = str(value or "text").strip().casefold().replace("_", "-")
    aliases = {
        "language": "text",
        "llm": "text",
        "vision-language": "multimodal",
        "vision-language-model": "multimodal",
        "image-only": "image",
        "image-model": "image",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in IMAGE_MODEL_KINDS else "text"


def _normalize_image_path(value: Any, default: str) -> str:
    raw = str(value or default).strip()
    if not raw:
        return default
    if not raw.startswith("/") or "?" in raw or "#" in raw or "://" in raw:
        return default
    if any(character.isspace() for character in raw) or ".." in raw.split("/"):
        return default
    # Image-compatible gateways should expose the familiar OpenAI paths.  A
    # relative /images/* extension is allowed, but arbitrary provider payload
    # paths are not part of the declarative contract.
    if raw.startswith("/images/"):
        return raw
    if default == "/responses" and raw == "/responses":
        return raw
    return default


def _normalize_image_capabilities(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    status = str(raw.get("status") or "unknown").strip().casefold()
    if status not in IMAGE_CAPABILITY_STATUSES:
        status = "unknown"
    transport = str(raw.get("transport") or "").strip().casefold().replace("-", "_")
    if transport not in IMAGE_TRANSPORTS:
        transport = ""
    raw_operations = raw.get("operations", raw.get("supported_operations", ()))
    if isinstance(raw_operations, str):
        raw_operations = raw_operations.replace(";", ",").split(",")
    operations: list[str] = []
    if isinstance(raw_operations, Sequence) and not isinstance(raw_operations, (bytes, bytearray)):
        for item in raw_operations:
            operation = str(item or "").strip().casefold().replace("-", "_")
            if operation == "generate":
                operation = "generation"
            if operation == "edit":
                operation = "editing"
            if operation in IMAGE_OPERATIONS and operation not in operations:
                operations.append(operation)
    # Boolean operation flags keep simple manifests readable while the
    # normalized artifact remains one fixed shape.
    if raw.get("supports_generation") is True or raw.get("generation") is True:
        if "generation" not in operations:
            operations.append("generation")
    if raw.get("supports_editing") is True or raw.get("editing") is True:
        if "editing" not in operations:
            operations.append("editing")
    if not transport or not operations:
        status = "unknown" if status == "verified" else status
    try:
        max_input_images = int(raw.get("max_input_images", raw.get("maxInputImages", 1)))
    except (TypeError, ValueError):
        max_input_images = 1
    max_input_images = max(1, min(16, max_input_images))
    streaming = bool(raw.get("streaming", raw.get("supports_streaming", False)))
    generation_default = (
        "/responses"
        if transport == "responses_image_generation"
        else _IMAGE_DEFAULT_GENERATION_PATH
    )
    return {
        "status": status,
        "transport": transport,
        "operations": [operation for operation in IMAGE_OPERATIONS if operation in operations],
        "generation_path": _normalize_image_path(
            raw.get("generation_path", raw.get("generationPath")),
            generation_default,
        ),
        "editing_path": _normalize_image_path(
            raw.get("editing_path", raw.get("editingPath")),
            _IMAGE_DEFAULT_EDIT_PATH,
        ),
        "max_input_images": max_input_images,
        "streaming": streaming,
        "raw_payload_paths_persisted": False,
    }


def canonical_public_model(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in PUBLIC_MODELS:
        return normalized
    return PUBLIC_MODEL_ALIASES.get(normalized, "axio-terra")


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def is_sha256_digest(value: Any) -> bool:
    """Return whether a value is a 64-character SHA-256 hex digest."""

    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value or "").strip()))


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def runtime_model_identity(value: str | None) -> str:
    """Normalize a model identity used only for runtime replica grouping.

    The public channel alias remains in ``ModelProfile.model`` because that is
    what a provider expects on the wire.  A configured canonical identity is
    preferred when it is available; otherwise the normalized provider model
    name gives ordinary same-name channels a conservative shared identity.
    This deliberately does not relax the separate final-benchmark requirement
    for an explicit ``canonical_model_id`` declaration.
    """

    return " ".join(str(value or "").strip().casefold().split())


def logical_model_identity(value: Any) -> str:
    """Return the canonical identity used to count one cognitive model.

    Provider/model aliases are transport identities.  A declared
    ``canonical_model_id`` is the logical identity; without one, the normalized
    model alias is the conservative fallback.  This helper accepts both a
    ``ModelProfile``-like object and a mapping so control-plane reports and
    process-local profiles use exactly the same grouping rule.
    """

    if isinstance(value, Mapping):
        canonical = value.get("canonical_model_id") or value.get("canonicalModelId")
        model = value.get("model") or value.get("id") or value.get("name")
    else:
        canonical = getattr(value, "canonical_model_id", None)
        model = getattr(value, "model", None)
    return runtime_model_identity(str(canonical or model or ""))


def logical_model_identities(values: Sequence[Any]) -> tuple[str, ...]:
    """Return deterministic unique logical model identities."""

    return tuple(sorted({identity for value in values if (identity := logical_model_identity(value))}))


def logical_model_count(values: Sequence[Any]) -> int:
    """Count logical models, never provider replicas."""

    return len(logical_model_identities(values))


def rough_token_count(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    non_ascii_count = len(text) - ascii_count
    return max(1, int(ascii_count / 4.0 + non_ascii_count / 1.6))


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    api_format: str = "chat"
    capabilities: Mapping[str, float] = field(default_factory=dict)
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    p50_latency_ms: int | None = None
    p95_latency_ms: int | None = None
    context_tokens: int | None = None
    recent_success_rate: float | None = None
    availability: float | None = None
    observed_success_count: int = 0
    observed_failure_count: int = 0
    supports_tools: bool = False
    tool_capability: str = ""
    tool_capability_source: str = ""
    tool_probe_status: str = "not_run"
    supports_vision: bool = False
    # Text and image modalities share credentials but never share a Fusion
    # candidate pool. Image eligibility is an explicit, separately probed
    # capability rather than a model-name heuristic.
    model_kind: str = "text"
    image_capabilities: Mapping[str, Any] = field(default_factory=dict)
    image_probe_status: str = "not_run"
    privacy_tags: tuple[str, ...] = ("external_provider",)
    base_url_env: str = ""
    api_key_env: str = ""
    auth_scheme: str = "bearer"
    # Model discovery is an optional control-plane capability.  A provider can
    # serve explicit model rows without exposing a compatible model-list route.
    models_endpoint: str = "/models"
    discover_models: bool = True
    enabled: bool = True
    health: str = "unknown"
    source: str = "registry"
    # This is deliberately separate from the routed channel alias in ``model``.
    # It is only required by final-claim baseline binding, never by serving.
    canonical_model_id: str = ""
    # Pre-Fusion screening metadata is an operational prior, not benchmark
    # evidence and not a replacement for declared/calibrated capabilities.
    screening_prior_rank: int | None = None
    screening_prior_confidence: float | None = None
    screening_allowed_roles: tuple[str, ...] = ()
    screening_disallowed_roles: tuple[str, ...] = ()
    # Capability axes produced by the pre-Fusion research Agent.  These are
    # deliberately kept separate from measured/calibrated ``capabilities``:
    # they are useful routing priors, but cannot become benchmark evidence or
    # silently overwrite operational calibration.
    screening_capability_overall: float | None = None
    screening_capability_axes: Mapping[str, float] = field(default_factory=dict)
    screening_role_admission: Mapping[str, Any] = field(default_factory=dict)
    # Operational ranking is computed only after the complete research prior
    # and physical streaming probe are joined.  It is a serving-control score,
    # never benchmark evidence.
    screening_research_quality_score: float | None = None
    screening_operational_rank: int | None = None
    screening_operational_score: float | None = None
    screening_operational_status: str = ""
    screening_stream_reliability_score: float | None = None
    screening_latency_score: float | None = None
    # Provider reasoning controls are a narrow, declarative capability gate.
    # They never contain arbitrary request-body paths or vendor extra fields.
    reasoning_transport: Mapping[str, Any] = field(default_factory=dict)
    # Model-specific public-source reasoning research.  This is separate from
    # ``reasoning_transport`` because research is a prior and cannot by itself
    # authorize a provider wire field.
    screening_reasoning_capability: Mapping[str, Any] = field(default_factory=dict)
    # Local scheduling controls for channels with bounded/shared rate limits.
    # This remains a closed configuration object and never changes an upstream
    # request payload.
    traffic_control: Mapping[str, Any] = field(default_factory=dict)
    # Runtime-only credential injection for programmatic deployments.  These
    # values are intentionally excluded from equality, repr, safe_dict(), and
    # every persisted registry/artifact.  Environment-backed deployments keep
    # using base_url_env/api_key_env as before.
    runtime_base_url: str = field(default="", repr=False, compare=False)
    runtime_api_keys: tuple[str, ...] = field(default_factory=tuple, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Keep legacy tool flags compatible with explicit capability state.

        Older manifests only supplied ``supports_tools``.  Treat that value as
        an external attestation until a newer operational probe supersedes it;
        an unprobed profile with no attestation remains explicitly unproven.
        """

        raw_state = str(self.tool_capability or "").strip().lower()
        state = _normalized_tool_capability_state(
            raw_state,
            supports_tools=bool(self.supports_tools),
        )
        source = str(self.tool_capability_source or "").strip() or (
            "external_attestation" if self.supports_tools else "none"
        )
        supports_tools = bool(self.supports_tools)
        if state == "proven" and source == "operational_probe":
            supports_tools = True
        if state == "proven" and not supports_tools:
            supports_tools = True
        object.__setattr__(self, "supports_tools", supports_tools)
        object.__setattr__(self, "tool_capability", state)
        object.__setattr__(self, "tool_capability_source", source)
        object.__setattr__(self, "model_kind", _normalize_model_kind(self.model_kind))
        object.__setattr__(self, "image_capabilities", _normalize_image_capabilities(self.image_capabilities))
        object.__setattr__(
            self,
            "image_probe_status",
            str(self.image_probe_status or "not_run").strip().casefold() or "not_run",
        )
        object.__setattr__(
            self,
            "tool_probe_status",
            str(self.tool_probe_status or "not_run").strip().lower() or "not_run",
        )
        endpoint = str(self.models_endpoint or "/models").strip()
        if endpoint.lower() in {"none", "disabled", "off"}:
            endpoint = ""
        object.__setattr__(self, "models_endpoint", endpoint)
        object.__setattr__(self, "discover_models", bool(self.discover_models) and bool(endpoint))
        object.__setattr__(
            self,
            "reasoning_transport",
            _normalize_reasoning_transport(
                self.reasoning_transport,
                api_format=self.api_format,
            ),
        )
        object.__setattr__(
            self,
            "screening_reasoning_capability",
            normalize_screening_reasoning_capability(
                self.screening_reasoning_capability,
                api_format=self.api_format,
            ),
        )
        object.__setattr__(
            self,
            "traffic_control",
            _normalize_traffic_control(self.traffic_control),
        )

    @property
    def profile_id(self) -> str:
        return f"{self.provider}/{self.model}"

    @property
    def canonical_identity(self) -> str:
        return runtime_model_identity(self.canonical_model_id or self.model)

    @property
    def canonical_identity_source(self) -> str:
        return "declared_canonical_model_id" if self.canonical_model_id else "normalized_model_alias"

    @property
    def canonical_identity_sha256(self) -> str:
        return sha256_text(self.canonical_identity)

    def capability(self, axis: str) -> float:
        return max(0.0, min(1.0, float(self.capabilities.get(axis, 0.0) or 0.0)))

    def screening_capability(self, axis: str) -> float:
        """Return a bounded pre-Fusion capability prior for one axis."""

        return max(
            0.0,
            min(1.0, float(self.screening_capability_axes.get(axis, 0.0) or 0.0)),
        )

    def resolve_reasoning_transport(self, requested_effort: Any) -> tuple[str, str]:
        """Resolve one verified wire transport and its effective effort.

        Unknown, candidate, unsupported, malformed, and protocol-mismatched
        declarations always fail closed.  An unsupported caller level may be
        sent only when the profile explicitly declares a non-escalating map.
        """

        requested = normalize_reasoning_effort(requested_effort)
        if not requested:
            return "", ""
        config = self.reasoning_transport
        if not isinstance(config, Mapping) or config.get("status") != "verified":
            return "", ""
        transport = str(config.get("transport") or "")
        expected_format = _REASONING_TRANSPORT_FORMATS.get(transport, "")
        if (
            not expected_format
            or expected_format != _reasoning_transport_api_format(self.api_format)
            or config.get("api_format_compatible") is not True
        ):
            return "", ""
        supported = set(_reasoning_effort_values(config.get("supported_efforts")))
        if requested in supported:
            return transport, requested
        effort_map = config.get("effort_map")
        mapped = normalize_reasoning_effort(
            effort_map.get(requested) if isinstance(effort_map, Mapping) else ""
        )
        if (
            mapped
            and mapped in supported
            and _REASONING_EFFORT_ORDER[mapped]
            <= _REASONING_EFFORT_ORDER[requested]
        ):
            return transport, mapped
        return "", ""

    def safe_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "api_format": self.api_format,
            "capabilities": {axis: self.capability(axis) for axis in CAPABILITY_AXES},
            "input_cost_per_million": self.input_cost_per_million,
            "output_cost_per_million": self.output_cost_per_million,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "context_tokens": self.context_tokens,
            "recent_success_rate": self.recent_success_rate,
            "availability": self.availability,
            "observed_success_count": self.observed_success_count,
            "observed_failure_count": self.observed_failure_count,
            "supports_tools": self.supports_tools,
            "tool_capability": self.tool_capability,
            "tool_capability_source": self.tool_capability_source,
            "tool_probe_status": self.tool_probe_status,
            "supports_vision": self.supports_vision,
            "model_kind": self.model_kind,
            "image_capabilities": dict(self.image_capabilities),
            "image_probe_status": self.image_probe_status,
            "privacy_tags": list(self.privacy_tags),
            "base_url_env": self.base_url_env,
            "api_key_env": self.api_key_env,
            "auth_scheme": self.auth_scheme,
            "models_endpoint": self.models_endpoint,
            "discover_models": self.discover_models,
            "base_url_persisted": False,
            "api_key_persisted": False,
            "enabled": self.enabled,
            "health": self.health,
            "source": self.source,
            "screening_prior_rank": self.screening_prior_rank,
            "screening_prior_confidence": self.screening_prior_confidence,
            "screening_allowed_roles": list(self.screening_allowed_roles),
            "screening_disallowed_roles": list(self.screening_disallowed_roles),
            "screening_capability_overall": (
                max(0.0, min(1.0, float(self.screening_capability_overall)))
                if self.screening_capability_overall is not None
                else None
            ),
            "screening_capability_axes": {
                axis: self.screening_capability(axis) for axis in CAPABILITY_AXES
            },
            "screening_role_admission": dict(self.screening_role_admission)
            if isinstance(self.screening_role_admission, Mapping)
            else {},
            "screening_operational_rank": self.screening_operational_rank,
            "screening_research_quality_score": (
                max(0.0, min(1.0, float(self.screening_research_quality_score)))
                if self.screening_research_quality_score is not None
                else None
            ),
            "screening_operational_score": (
                max(0.0, min(1.0, float(self.screening_operational_score)))
                if self.screening_operational_score is not None
                else None
            ),
            "screening_operational_status": str(self.screening_operational_status or ""),
            "screening_stream_reliability_score": (
                max(0.0, min(1.0, float(self.screening_stream_reliability_score)))
                if self.screening_stream_reliability_score is not None
                else None
            ),
            "screening_latency_score": (
                max(0.0, min(1.0, float(self.screening_latency_score)))
                if self.screening_latency_score is not None
                else None
            ),
            "reasoning_transport": dict(self.reasoning_transport),
            "screening_reasoning_capability": dict(
                self.screening_reasoning_capability
            ),
            "traffic_control": dict(self.traffic_control),
            "screening_prior_only": True,
            "canonical_model_identity_declared": bool(self.canonical_model_id),
            "canonical_model_id_sha256": (
                sha256_text(self.canonical_model_id)
                if self.canonical_model_id
                else ""
            ),
            "runtime_canonical_identity_sha256": self.canonical_identity_sha256,
            "runtime_canonical_identity_source": self.canonical_identity_source,
            "raw_canonical_model_id_persisted": False,
        }

    @property
    def tool_calling_eligible(self) -> bool:
        """Whether routing may spend a native-tool turn on this profile."""

        return bool(self.supports_tools and self.tool_capability == "proven")

    @property
    def text_model_eligible(self) -> bool:
        """Whether this profile may enter the text Fusion candidate pool."""

        return self.model_kind in {"text", "multimodal"}

    @property
    def image_operations(self) -> tuple[str, ...]:
        operations = self.image_capabilities.get("operations", ())
        if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes, bytearray)):
            return ()
        operation_set = {str(item) for item in operations}
        return tuple(operation for operation in IMAGE_OPERATIONS if operation in operation_set)

    @property
    def image_generation_eligible(self) -> bool:
        return bool(
            self.enabled
            and self.model_kind in {"image", "multimodal"}
            and self.image_capabilities.get("status") == "verified"
            and self.image_probe_status in {"passed", "verified", "success", "ok"}
            and self.image_capabilities.get("transport") in IMAGE_TRANSPORTS
            and "generation" in self.image_operations
        )

    @property
    def image_editing_eligible(self) -> bool:
        return bool(
            self.enabled
            and self.model_kind in {"image", "multimodal"}
            and self.image_capabilities.get("status") == "verified"
            and self.image_probe_status in {"passed", "verified", "success", "ok"}
            and self.image_capabilities.get("transport") == "images_api"
            and "editing" in self.image_operations
        )


@dataclass(frozen=True)
class FusionPolicy:
    max_cost_usd: float | None = None
    max_latency_ms: int | None = None
    quality_target: float | None = None
    max_models: int | None = None
    max_depth: int | None = None
    max_total_model_calls: int | None = None
    fusion_depth: int = 0
    max_fusion_depth: int = 2
    live: bool = False


@dataclass(frozen=True)
class FusionRequest:
    model: str
    prompt: str
    system: str = "You are Axio Fusion, a careful and evidence-aware assistant."
    # The last public user turn in a protocol-neutral content representation.
    # Rich historical turns carry the same shape under ``content_parts`` in
    # their request-local history events.
    content_parts: tuple[Mapping[str, Any], ...] = ()
    # History may include protocol-neutral assistant tool calls and tool results
    # in addition to ordinary text turns. It remains request-local and is
    # represented only by a hash in durable receipts.
    history: tuple[Mapping[str, Any], ...] = ()
    api_format: str = "chat/completions"
    task_type: str = "auto"
    requested_capabilities: tuple[str, ...] = ()
    # This is a protocol-neutral desired upper bound.  Provider adapters map
    # it only after a ModelProfile has verified the exact wire contract.
    reasoning_effort: str = ""
    # Closed public output contract. Provider adapters render this into their
    # native structured-output wrapper; arbitrary vendor fields never cross
    # the provider boundary.
    structured_output: Mapping[str, Any] = field(default_factory=dict)
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    stop: tuple[str, ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    policy: FusionPolicy = field(default_factory=FusionPolicy)

    def __post_init__(self) -> None:
        parts = normalize_content_parts(
            self.content_parts if self.content_parts else self.prompt,
            source_format="chat",
        )
        object.__setattr__(self, "content_parts", tuple(dict(item) for item in parts))
        object.__setattr__(
            self,
            "reasoning_effort",
            normalize_reasoning_effort(self.reasoning_effort),
        )
        object.__setattr__(
            self,
            "structured_output",
            normalize_structured_output(
                self.structured_output,
                api_format=self.api_format,
            ),
        )

    @property
    def public_model(self) -> str:
        return canonical_public_model(self.model)

    @property
    def has_visual_input(self) -> bool:
        if has_visual_content(self.content_parts):
            return True
        return any(
            has_visual_content(event.get("content_parts"))
            for event in self.history
            if isinstance(event, Mapping)
        )

    @property
    def has_non_text_input(self) -> bool:
        if has_non_text_content(self.content_parts):
            return True
        return any(
            has_non_text_content(event.get("content_parts"))
            for event in self.history
            if isinstance(event, Mapping)
        )

    @property
    def request_fingerprint(self) -> str:
        return sha256_text(
            stable_json(
                {
                    "model": self.public_model,
                    "prompt": self.prompt,
                    "system": self.system,
                    "history": list(self.history),
                    "content_parts": list(self.content_parts),
                    "api_format": self.api_format,
                    "task_type": self.task_type,
                    "requested_capabilities": list(self.requested_capabilities),
                    "reasoning_effort": self.reasoning_effort,
                    "structured_output": dict(self.structured_output),
                    "tools": list(self.tools),
                }
            )
        )

    def prompt_free_dict(self) -> dict[str, Any]:
        return {
            "model": self.public_model,
            "api_format": self.api_format,
            "prompt_sha256": sha256_text(self.prompt),
            "prompt_char_count": len(self.prompt),
            "system_sha256": sha256_text(self.system),
            "system_char_count": len(self.system),
            "history_count": len(self.history),
            "history_sha256": sha256_text(stable_json(list(self.history))),
            "content_parts": content_parts_safe_summary(self.content_parts),
            "task_type": self.task_type,
            "requested_capabilities": list(self.requested_capabilities),
            "reasoning_effort": self.reasoning_effort,
            "structured_output": structured_output_safe_summary(self.structured_output),
            "tool_count": len(self.tools),
            "metadata_keys": sorted(str(key) for key in self.metadata.keys()),
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stop_sequence_count": len(self.stop),
            "stop_sha256": sha256_text(stable_json(list(self.stop))),
            "request_fingerprint": self.request_fingerprint,
            "raw_prompt_persisted": False,
            "raw_source_text_persisted": False,
            "secrets_persisted": False,
        }


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    role: str
    profile_id: str
    provider: str
    model: str
    answer: str
    confidence: float = 0.5
    reasoning_summary: tuple[str, ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()
    assumptions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    status: str = "completed"
    latency_ms: float = 0.0
    error_type: str = ""
    tool_execution: Mapping[str, Any] = field(default_factory=dict)
    task_execution: Mapping[str, Any] = field(default_factory=dict)
    escalation_plan: Mapping[str, Any] = field(default_factory=dict)
    standardization: Mapping[str, Any] = field(default_factory=dict)
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    # The runtime identity is carried only in memory. Safe receipts expose its
    # digest so channel replicas cannot be mistaken for independent evidence.
    canonical_identity: str = ""

    @property
    def runtime_canonical_identity(self) -> str:
        return runtime_model_identity(self.canonical_identity or self.model)

    def safe_dict(self) -> dict[str, Any]:
        reasoning_payload = stable_json(list(self.reasoning_summary))
        return {
            "candidate_id": self.candidate_id,
            "role": self.role,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "runtime_canonical_identity_sha256": sha256_text(
                self.runtime_canonical_identity
            ),
            "answer_sha256": sha256_text(self.answer),
            "answer_char_count": len(self.answer),
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "reasoning_step_count": len(self.reasoning_summary),
            "reasoning_summary_sha256": sha256_text(reasoning_payload),
            "reasoning_summary_token_estimate": rough_token_count("\n".join(self.reasoning_summary)),
            "evidence_count": len(self.evidence),
            "assumption_count": len(self.assumptions),
            "uncertainty_count": len(self.uncertainties),
            "status": self.status,
            "latency_ms": round(float(self.latency_ms), 3),
            "error_type": self.error_type[:120],
            "tool_execution": _safe_tool_execution_summary(self.tool_execution),
            "tool_calls": _safe_tool_call_summary(self.tool_calls),
            "task_execution": _safe_candidate_task_execution_summary(self.task_execution),
            "escalation_plan": _safe_targeted_escalation_plan_summary(self.escalation_plan),
            "standardization": _safe_candidate_standardization_summary(self.standardization),
            "raw_prompt_persisted": False,
            "raw_candidate_text_persisted": False,
            "raw_reasoning_summary_persisted": False,
            "secrets_persisted": False,
        }


@dataclass(frozen=True)
class FusionResponse:
    text: str
    request: FusionRequest
    route_plan: Mapping[str, Any]
    candidates: tuple[CandidateResult, ...] = ()
    judge_result: Mapping[str, Any] = field(default_factory=dict)
    trace: Mapping[str, Any] = field(default_factory=dict)
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    provider_calls_recorded: bool = False
    response_id: str = field(default_factory=lambda: f"fusion-{uuid.uuid4().hex}")
    created: int = field(default_factory=lambda: int(time.time()))

    def usage(self) -> dict[str, int]:
        prompt_text = "\n".join(
            [
                self.request.system,
                *[str(item.get("content") or "") for item in self.request.history],
                self.request.prompt,
            ]
        )
        prompt_tokens = rough_token_count(prompt_text)
        completion_tokens = rough_token_count(self.text)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }


def _safe_tool_call_summary(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [call for call in calls if isinstance(call, Mapping)]
    return {
        "schema": "axio_fusion_api.tool_call_summary.v1",
        "tool_call_count": len(rows),
        "tool_name_sha256s": [sha256_text(str(call.get("name") or "")) for call in rows[:16]],
        "tool_call_id_sha256s": [sha256_text(str(call.get("id") or "")) for call in rows[:16]],
        "argument_sha256s": [
            sha256_text(stable_json(call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {}))
            for call in rows[:16]
        ],
        "source_formats": sorted({str(call.get("source_format") or "") for call in rows if str(call.get("source_format") or "")}),
        "raw_tool_names_persisted": False,
        "raw_tool_arguments_persisted": False,
        "raw_tool_results_persisted": False,
    }


def _safe_tool_execution_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "executed": False,
            "requested_call_count": 0,
            "success_count": 0,
            "blocked_count": 0,
            "failed_count": 0,
            "raw_tool_arguments_persisted": False,
            "raw_tool_result_persisted": False,
            "raw_tool_schema_persisted": False,
        }
    results = value.get("results") if isinstance(value.get("results"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.tool_execution_batch.v1",
        "executed": True,
        "requested_call_count": int(value.get("requested_call_count") or 0),
        "executed_or_blocked_call_count": int(value.get("executed_or_blocked_call_count") or 0),
        "success_count": int(value.get("success_count") or 0),
        "blocked_count": int(value.get("blocked_count") or 0),
        "failed_count": int(value.get("failed_count") or 0),
        "result_receipts": [
            {
                "call_index": row.get("call_index"),
                "tool_hash": str(row.get("tool_hash") or ""),
                "tool_name_sha256": str(row.get("tool_name_sha256") or ""),
                "tool_category": str(row.get("tool_category") or ""),
                "status": str(row.get("status") or ""),
                "result_sha256": str(row.get("result_sha256") or ""),
                "error_code": str(row.get("error_code") or "")[:120],
                "raw_tool_arguments_persisted": False,
                "raw_tool_result_persisted": False,
                "raw_tool_schema_persisted": False,
            }
            for row in results[:16]
            if isinstance(row, Mapping)
        ],
        "raw_tool_arguments_persisted": False,
        "raw_tool_result_persisted": False,
        "raw_tool_schema_persisted": False,
    }


def _safe_candidate_standardization_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.candidate_standardization.v1",
            "parsed": False,
            "parse_mode": "unknown",
            "answer_field": "",
            "reasoning_field": "",
            "normalized_field_count": 0,
            "missing_required_fields": [],
            "confidence_defaulted": True,
            "confidence_clamped": False,
            "source_text_sha256": "",
            "source_char_count": 0,
            "raw_candidate_text_persisted": False,
            "raw_reasoning_summary_persisted": False,
            "secrets_persisted": False,
        }
    missing = value.get("missing_required_fields") if isinstance(value.get("missing_required_fields"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.candidate_standardization.v1",
        "parsed": bool(value.get("parsed")),
        "parse_mode": str(value.get("parse_mode") or "unknown")[:80],
        "answer_field": str(value.get("answer_field") or "")[:80],
        "reasoning_field": str(value.get("reasoning_field") or "")[:80],
        "evidence_field": str(value.get("evidence_field") or "")[:80],
        "assumptions_field": str(value.get("assumptions_field") or "")[:80],
        "uncertainties_field": str(value.get("uncertainties_field") or "")[:80],
        "confidence_field": str(value.get("confidence_field") or "")[:80],
        "normalized_field_count": _safe_int(value.get("normalized_field_count"), default=0),
        "answer_char_count": _safe_int(value.get("answer_char_count"), default=0),
        "answer_sha256": str(value.get("answer_sha256") or ""),
        "reasoning_step_count": _safe_int(value.get("reasoning_step_count"), default=0),
        "reasoning_summary_sha256": str(value.get("reasoning_summary_sha256") or ""),
        "evidence_count": _safe_int(value.get("evidence_count"), default=0),
        "assumption_count": _safe_int(value.get("assumption_count"), default=0),
        "uncertainty_count": _safe_int(value.get("uncertainty_count"), default=0),
        "tool_call_count": _safe_int(value.get("tool_call_count"), default=0),
        "missing_required_fields": [str(item)[:80] for item in missing[:12] if str(item)],
        "confidence_defaulted": bool(value.get("confidence_defaulted")),
        "confidence_clamped": bool(value.get("confidence_clamped")),
        "source_text_sha256": str(value.get("source_text_sha256") or ""),
        "source_char_count": _safe_int(value.get("source_char_count"), default=0),
        "raw_candidate_text_persisted": False,
        "raw_reasoning_summary_persisted": False,
        "secrets_persisted": False,
    }


def _safe_candidate_task_execution_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.candidate_task_execution.v1",
            "role": "",
            "assigned_node_count": 0,
            "verification_node_count": 0,
            "dependency_count": 0,
            "checkpoint_count": 0,
            "node_receipts": [],
            "checkpoint_receipts": [],
            "replica_routing": _safe_replica_routing_summary({}),
            "provider_error_code": "",
            "provider_http_status": None,
            "provider_error_class": "",
            "hermes_cognitive_budget": {},
            "hermes_reference_fanout_cadence": "",
            "raw_prompt_persisted": False,
            "raw_candidate_text_persisted": False,
            "secrets_persisted": False,
        }
    nodes = value.get("node_receipts") if isinstance(value.get("node_receipts"), list) else []
    checkpoints = value.get("checkpoint_receipts") if isinstance(value.get("checkpoint_receipts"), list) else []
    provider_error_code = safe_provider_error_code(value.get("provider_error_code"))
    provider_http_status = safe_provider_http_status(value.get("provider_http_status"))
    return {
        "schema": value.get("schema") or "axio_fusion_api.candidate_task_execution.v1",
        "role": str(value.get("role") or "")[:80],
        "assigned_node_count": _safe_int(value.get("assigned_node_count"), default=0),
        "verification_node_count": _safe_int(value.get("verification_node_count"), default=0),
        "dependency_count": _safe_int(value.get("dependency_count"), default=0),
        "checkpoint_count": _safe_int(value.get("checkpoint_count"), default=0),
        "node_receipts": [
            {
                "id": str(row.get("id") or "")[:120],
                "kind": str(row.get("kind") or "")[:80],
                "assigned_role": str(row.get("assigned_role") or "")[:80],
                "dependency_count": _safe_int(row.get("dependency_count"), default=0),
                "required_capabilities": [
                    str(item)[:80]
                    for item in row.get("required_capabilities", [])
                    if str(item)
                ][:8] if isinstance(row.get("required_capabilities"), list) else [],
                "parallelizable": bool(row.get("parallelizable")),
                "verification_required": bool(row.get("verification_required")),
            }
            for row in nodes[:24]
            if isinstance(row, Mapping)
        ],
        "checkpoint_receipts": [
            {
                "id": str(row.get("id") or "")[:120],
                "after_node": str(row.get("after_node") or "")[:120],
                "record_count": _safe_int(row.get("record_count"), default=0),
            }
            for row in checkpoints[:12]
            if isinstance(row, Mapping)
        ],
        "replica_routing": _safe_replica_routing_summary(
            value.get("replica_routing")
            if isinstance(value.get("replica_routing"), Mapping)
            else {}
        ),
        "provider_error_code": provider_error_code,
        "provider_http_status": provider_http_status,
        "provider_error_class": safe_provider_error_class(
            provider_error_code,
            provider_http_status,
        ),
        "hermes_cognitive_budget": _safe_hermes_cognitive_budget(
            value.get("hermes_cognitive_budget")
            if isinstance(value.get("hermes_cognitive_budget"), Mapping)
            else {}
        ),
        "hermes_reference_fanout_cadence": str(
            value.get("hermes_reference_fanout_cadence") or ""
        )[:80],
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "secrets_persisted": False,
    }


def _safe_hermes_cognitive_budget(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {}
    return {
        "reasoning_effort": str(value.get("reasoning_effort") or "")[:24],
        "budget_class": str(value.get("budget_class") or "")[:48],
        "control_mode": str(value.get("control_mode") or "")[:80],
        "wire_reasoning_parameter_forwarding": str(
            value.get("wire_reasoning_parameter_forwarding") or ""
        )[:80],
        "hidden_chain_of_thought_requested": False,
        "public_reasoning_summary_only": True,
    }


def _safe_replica_routing_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.runtime_canonical_replica_routing.v1",
            "enabled": False,
            "configured_replica_count": 0,
            "runtime_eligible_replica_count": 0,
            "comparable_replica_count": 0,
            "bounded_failover_attempt_count": 0,
            "selected_profile_sha256": "",
            "attempted_profile_hash_count": 0,
            "stage_attempt_count": 0,
            "stage_failure_count": 0,
            "failover_used": False,
            "successful_profile_sha256": "",
            "terminal_reason": "",
            "initial_attempt_reason": "",
            "stage_error_code_counts": {},
            "stage_error_class_counts": {},
            "stage_http_status_counts": {},
            "last_stage_error_code": "",
            "last_stage_error_class": "",
            "last_stage_http_status": None,
            "raw_canonical_identity_persisted": False,
            "raw_profile_id_persisted": False,
            "raw_provider_name_persisted": False,
            "raw_model_name_persisted": False,
        }
    hashes = (
        value.get("ordered_attempt_profile_hashes")
        if isinstance(value.get("ordered_attempt_profile_hashes"), list)
        else []
    )
    attempts = value.get("stage_attempt_receipts") if isinstance(value.get("stage_attempt_receipts"), list) else []
    error_code_counts: dict[str, int] = {}
    error_class_counts: dict[str, int] = {}
    http_status_counts: dict[str, int] = {}
    last_error_code = ""
    last_error_class = ""
    last_http_status: int | None = None
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            continue
        error_code = safe_provider_error_code(attempt.get("error_code"))
        http_status = safe_provider_http_status(attempt.get("http_status"))
        if error_code:
            error_code_counts[error_code] = error_code_counts.get(error_code, 0) + 1
            last_error_code = error_code
        error_class = safe_provider_error_class(error_code, http_status)
        if error_class:
            error_class_counts[error_class] = error_class_counts.get(error_class, 0) + 1
            last_error_class = error_class
        if http_status is not None:
            key = str(http_status)
            http_status_counts[key] = http_status_counts.get(key, 0) + 1
            last_http_status = http_status
    provider_error_code = safe_provider_error_code(value.get("provider_error_code"))
    provider_http_status = safe_provider_http_status(value.get("provider_http_status"))
    return {
        "schema": str(
            value.get("schema")
            or "axio_fusion_api.runtime_canonical_replica_routing.v1"
        )[:120],
        "enabled": bool(value.get("enabled")),
        "runtime_canonical_identity_sha256": str(
            value.get("runtime_canonical_identity_sha256") or ""
        ),
        "configured_replica_count": _safe_int(
            value.get("configured_replica_count"), default=0
        ),
        "route_eligible_replica_count": _safe_int(
            value.get("route_eligible_replica_count"), default=0
        ),
        "runtime_eligible_replica_count": _safe_int(
            value.get("runtime_eligible_replica_count"), default=0
        ),
        "comparable_replica_count": _safe_int(
            value.get("comparable_replica_count"), default=0
        ),
        "bounded_failover_attempt_count": _safe_int(
            value.get("bounded_failover_attempt_count"), default=0
        ),
        "selected_profile_sha256": str(value.get("selected_profile_sha256") or ""),
        "ordered_attempt_profile_hashes": [str(item) for item in hashes if str(item)][:24],
        "attempted_profile_hash_count": len(
            value.get("attempted_profile_hashes", [])
        ) if isinstance(value.get("attempted_profile_hashes"), list) else 0,
        "stage_attempt_count": _safe_int(value.get("stage_attempt_count"), default=0),
        "stage_failure_count": _safe_int(value.get("stage_failure_count"), default=0),
        "failover_used": bool(value.get("failover_used")),
        "successful_profile_sha256": str(
            value.get("successful_profile_sha256") or ""
        ),
        "terminal_reason": str(value.get("terminal_reason") or "")[:120],
        "initial_attempt_reason": str(
            value.get("initial_attempt_reason") or ""
        )[:120],
        "provider_error_code": provider_error_code,
        "provider_http_status": provider_http_status,
        "stage_error_code_counts": dict(sorted(error_code_counts.items())),
        "stage_error_class_counts": dict(sorted(error_class_counts.items())),
        "stage_http_status_counts": dict(sorted(http_status_counts.items())),
        "last_stage_error_code": last_error_code,
        "last_stage_error_class": last_error_class,
        "last_stage_http_status": last_http_status,
        "selection_policy": str(value.get("selection_policy") or "")[:120],
        "selection_reason": str(value.get("selection_reason") or "")[:120],
        "route_pool_restricted": bool(value.get("route_pool_restricted")),
        "excluded_profile_hash_count": _safe_int(
            value.get("excluded_profile_hash_count"), default=0
        ),
        "circuit_open_replica_count": _safe_int(
            value.get("circuit_open_replica_count"), default=0
        ),
        "raw_canonical_identity_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
    }


def _safe_targeted_escalation_plan_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.targeted_escalation_plan.v1",
            "enabled": False,
            "triggered": False,
            "subtask_count": 0,
            "selected_subtask_count": 0,
            "subtasks": [],
            "quality_gap_triggered": False,
            "requires_independent_answer_claim_verification": False,
            "requires_cross_provider_verifier": False,
            "requires_new_profile_verifier": False,
            "answer_claim_independence_requirement": _safe_answer_claim_independence_requirement_summary({}),
            "model_selection": _safe_targeted_escalation_model_selection_summary({}),
            "raw_prompt_persisted": False,
            "raw_candidate_text_persisted": False,
            "secrets_persisted": False,
        }
    subtasks = value.get("subtasks") if isinstance(value.get("subtasks"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.targeted_escalation_plan.v1",
        "enabled": bool(value.get("enabled")),
        "triggered": bool(value.get("triggered")),
        "max_rounds": _safe_int(value.get("max_rounds"), default=0),
        "subtask_count": _safe_int(value.get("subtask_count"), default=len(subtasks)),
        "selected_subtask_count": _safe_int(value.get("selected_subtask_count"), default=len(subtasks)),
        "quality_gap_triggered": bool(value.get("quality_gap_triggered")),
        "blocking_gap_counts": _safe_counts(value.get("blocking_gap_counts") if isinstance(value.get("blocking_gap_counts"), Mapping) else {}),
        "requires_independent_answer_claim_verification": bool(value.get("requires_independent_answer_claim_verification")),
        "requires_cross_provider_verifier": bool(value.get("requires_cross_provider_verifier")),
        "requires_new_profile_verifier": bool(value.get("requires_new_profile_verifier")),
        "answer_claim_independence_requirement": _safe_answer_claim_independence_requirement_summary(
            value.get("answer_claim_independence_requirement") if isinstance(value.get("answer_claim_independence_requirement"), Mapping) else {}
        ),
        "model_selection": _safe_targeted_escalation_model_selection_summary(
            value.get("model_selection") if isinstance(value.get("model_selection"), Mapping) else {}
        ),
        "subtasks": [
            {
                "id": str(row.get("id") or "")[:120],
                "kind": str(row.get("kind") or "")[:80],
                "source": str(row.get("source") or "")[:80],
                "priority": _safe_int(row.get("priority"), default=0),
                "focus_sha256": str(row.get("focus_sha256") or ""),
                "focus_label": str(row.get("focus_label") or "")[:160],
                "focused_dag_node_ids": [
                    str(item)[:120]
                    for item in row.get("focused_dag_node_ids", [])
                    if str(item)
                ][:12] if isinstance(row.get("focused_dag_node_ids"), list) else [],
                "raw_focus_persisted": False,
            }
            for row in subtasks[:12]
            if isinstance(row, Mapping)
        ],
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "secrets_persisted": False,
    }


def _safe_answer_claim_independence_requirement_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.answer_claim_independence_requirement.v1",
            "required": False,
            "require_new_profile": False,
            "require_new_canonical_model": False,
            "require_new_provider": False,
            "reason_codes": [],
            "raw_answer_claim_persisted": False,
            "raw_profile_id_persisted": False,
            "raw_provider_name_persisted": False,
            "raw_candidate_text_persisted": False,
        }
    return {
        "schema": value.get("schema") or "axio_fusion_api.answer_claim_independence_requirement.v1",
        "required": bool(value.get("required")),
        "require_new_profile": bool(value.get("require_new_profile")),
        "require_new_canonical_model": bool(value.get("require_new_canonical_model")),
        "require_new_provider": bool(value.get("require_new_provider")),
        "largest_answer_claim_fingerprint_sha256": str(value.get("largest_answer_claim_fingerprint_sha256") or ""),
        "largest_answer_claim_equivalence_type": str(value.get("largest_answer_claim_equivalence_type") or "")[:80],
        "largest_answer_claim_support_fraction": _safe_float(value.get("largest_answer_claim_support_fraction"), default=0.0),
        "largest_answer_claim_unique_profile_count": _safe_int(value.get("largest_answer_claim_unique_profile_count"), default=0),
        "largest_answer_claim_unique_provider_count": _safe_int(value.get("largest_answer_claim_unique_provider_count"), default=0),
        "largest_answer_claim_unique_canonical_model_count": _safe_int(
            value.get("largest_answer_claim_unique_canonical_model_count"),
            default=0,
        ),
        "candidate_provider_hash_count": _safe_int(value.get("candidate_provider_hash_count"), default=0),
        "required_unique_provider_count": _safe_int(value.get("required_unique_provider_count"), default=1),
        "supporting_profile_hashes": [
            str(item)
            for item in value.get("supporting_profile_hashes", [])
            if str(item)
        ][:12] if isinstance(value.get("supporting_profile_hashes"), list) else [],
        "supporting_provider_hashes": [
            str(item)
            for item in value.get("supporting_provider_hashes", [])
            if str(item)
        ][:12] if isinstance(value.get("supporting_provider_hashes"), list) else [],
        "supporting_canonical_identity_hashes": [
            str(item)
            for item in value.get("supporting_canonical_identity_hashes", [])
            if str(item)
        ][:12]
        if isinstance(value.get("supporting_canonical_identity_hashes"), list)
        else [],
        "reason_codes": [
            str(item)[:120]
            for item in value.get("reason_codes", [])
            if str(item)
        ][:12] if isinstance(value.get("reason_codes"), list) else [],
        "raw_answer_claim_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_candidate_text_persisted": False,
    }


def _safe_targeted_escalation_model_selection_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.targeted_escalation_model_selection.v1",
            "selected": False,
            "raw_profile_id_persisted": False,
            "raw_provider_name_persisted": False,
            "raw_model_name_persisted": False,
        }
    return {
        "schema": value.get("schema") or "axio_fusion_api.targeted_escalation_model_selection.v1",
        "selected": bool(value.get("selected")),
        "selected_profile_sha256": str(value.get("selected_profile_sha256") or ""),
        "selected_provider_sha256": str(value.get("selected_provider_sha256") or ""),
        "selected_runtime_canonical_identity_sha256": str(
            value.get("selected_runtime_canonical_identity_sha256") or ""
        ),
        "selected_is_new_profile_for_claim": bool(value.get("selected_is_new_profile_for_claim")),
        "selected_is_new_provider_for_claim": bool(value.get("selected_is_new_provider_for_claim")),
        "selected_is_new_canonical_model_for_claim": bool(
            value.get("selected_is_new_canonical_model_for_claim")
        ),
        "requires_new_profile_verifier": bool(value.get("requires_new_profile_verifier")),
        "requires_new_canonical_model_verifier": bool(
            value.get("requires_new_canonical_model_verifier")
        ),
        "requires_cross_provider_verifier": bool(value.get("requires_cross_provider_verifier")),
        "eligible_pool_count": _safe_int(value.get("eligible_pool_count"), default=0),
        "used_profile_hash_count": _safe_int(value.get("used_profile_hash_count"), default=0),
        "reason_codes": [
            str(item)[:120]
            for item in value.get("reason_codes", [])
            if str(item)
        ][:12] if isinstance(value.get("reason_codes"), list) else [],
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
    }


def _safe_counts(value: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(key)[:80]: _safe_int(item, default=0)
        for key, item in value.items()
        if str(key)
    }


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
