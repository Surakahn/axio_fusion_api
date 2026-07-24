"""Shared provider latency eligibility policy.

This module is intentionally dependency-light so the provider client, registry,
runtime enrollment, and router can apply the same hard response-time rule
without importing one another.  A model-quality prior can never make a slow
profile eligible.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


PROVIDER_MAX_RESPONSE_SECONDS = 90.0
PROVIDER_MAX_RESPONSE_LATENCY_MS = int(PROVIDER_MAX_RESPONSE_SECONDS * 1000)


def latency_eligibility(
    *,
    observed_latency_ms: Any = None,
    p50_latency_ms: Any = None,
    p95_latency_ms: Any = None,
) -> dict[str, Any]:
    """Return a hash-safe decision for the hard 90-second response ceiling.

    ``observed_latency_ms`` is the authoritative value for a fresh streaming
    probe.  Registry p50/p95 values are conservative gates when present; a
    single known percentile above the ceiling keeps the profile out of the
    serving pool until fresh evidence replaces it.
    """

    values: list[tuple[str, float]] = []
    for label, raw in (
        ("observed", observed_latency_ms),
        ("p50", p50_latency_ms),
        ("p95", p95_latency_ms),
    ):
        try:
            value = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            value = None
        if value is not None and value >= 0:
            values.append((label, value))

    exceeded = [(label, value) for label, value in values if value > PROVIDER_MAX_RESPONSE_LATENCY_MS]
    if exceeded:
        return {
            "eligible": False,
            "reason_code": "provider_response_latency_exceeded_90s",
            "max_response_seconds": PROVIDER_MAX_RESPONSE_SECONDS,
            "observed_latency_ms": _safe_number(observed_latency_ms),
            "p50_latency_ms": _safe_number(p50_latency_ms),
            "p95_latency_ms": _safe_number(p95_latency_ms),
            "exceeded_measurements": [label for label, _ in exceeded],
        }
    return {
        "eligible": True,
        "reason_code": "within_provider_response_latency_limit",
        "max_response_seconds": PROVIDER_MAX_RESPONSE_SECONDS,
        "observed_latency_ms": _safe_number(observed_latency_ms),
        "p50_latency_ms": _safe_number(p50_latency_ms),
        "p95_latency_ms": _safe_number(p95_latency_ms),
        "exceeded_measurements": [],
    }


def profile_latency_eligibility(profile: Any) -> dict[str, Any]:
    """Evaluate a ModelProfile-like object without importing schemas."""

    return latency_eligibility(
        p50_latency_ms=getattr(profile, "p50_latency_ms", None),
        p95_latency_ms=getattr(profile, "p95_latency_ms", None),
    )


def row_latency_eligibility(row: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a probe/registry row using its observed and percentile fields."""

    return latency_eligibility(
        observed_latency_ms=row.get("latency_ms", row.get("observed_latency_ms")),
        p50_latency_ms=row.get("p50_latency_ms"),
        p95_latency_ms=row.get("p95_latency_ms"),
    )


def measured_stream_latency_eligibility(row: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the hard gate to a row that claims to be a live stream probe.

    ``row_latency_eligibility`` is intentionally permissive for static
    registry priors: an absent latency value is not itself a slow value. A
    serving admission, however, must have an actual observed measurement.
    This stricter helper is used only at the pre-Fusion live-probe boundary.
    """

    raw_observed = row.get("latency_ms", row.get("observed_latency_ms"))
    try:
        observed = float(raw_observed) if raw_observed not in (None, "") else None
    except (TypeError, ValueError):
        observed = None
    if observed is None or not math.isfinite(observed) or observed < 0:
        return {
            "eligible": False,
            "reason_code": "provider_stream_latency_measurement_missing_or_invalid",
            "measurement_present": False,
            "max_response_seconds": PROVIDER_MAX_RESPONSE_SECONDS,
            "observed_latency_ms": None,
            "exceeded_measurements": [],
        }
    result = latency_eligibility(
        observed_latency_ms=observed,
        p50_latency_ms=row.get("p50_latency_ms"),
        p95_latency_ms=row.get("p95_latency_ms"),
    )
    result["measurement_present"] = True
    return result


def streaming_evidence_eligibility(row: Mapping[str, Any]) -> dict[str, Any]:
    """Require an actual framed stream before a row can enter serving.

    ``stream=true`` is only a request hint.  A provider is admitted only when
    the response was consumed as SSE or NDJSON, produced at least one parsed
    frame, and did not use the ordinary-JSON compatibility path.
    """

    if row.get("stream_requested") is not True:
        return {"eligible": False, "reason_code": "stream_request_evidence_missing"}
    if row.get("strict_streaming_requested") is not True:
        return {
            "eligible": False,
            "reason_code": "strict_stream_request_evidence_missing",
        }
    if row.get("stream_observed") is not True:
        return {"eligible": False, "reason_code": "stream_observation_missing"}
    if row.get("stream_fallback_used") is True:
        return {"eligible": False, "reason_code": "ordinary_json_stream_fallback_used"}
    protocol = str(row.get("stream_protocol") or "").strip().casefold()
    if protocol not in {"sse", "ndjson"}:
        return {"eligible": False, "reason_code": "stream_protocol_unverified"}
    try:
        frame_count = int(row.get("stream_frame_count"))
    except (TypeError, ValueError):
        frame_count = 0
    if frame_count < 1:
        return {"eligible": False, "reason_code": "stream_frame_evidence_missing"}
    return {
        "eligible": True,
        "reason_code": "framed_stream_evidence_verified",
        "stream_protocol": protocol,
        "stream_frame_count": frame_count,
        "strict_streaming_requested": True,
    }


def _safe_number(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else round(parsed, 3)
