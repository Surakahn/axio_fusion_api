"""Pure scoring helpers for the pre-Fusion model handoff.

The research Agent supplies an evidence-backed capability prior.  A live
provider probe supplies serving evidence.  This module joins those two
signals into a deterministic *operational* ordering; it never consumes
benchmark cases, labels, or evaluator results.
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Mapping, Sequence

from .latency_policy import (
    measured_stream_latency_eligibility,
    streaming_evidence_eligibility,
)
from .schemas import CAPABILITY_AXES, is_sha256_digest, sha256_text


PREFUSION_OPERATIONAL_RANKING_SCHEMA = (
    "axio_fusion_api.prefusion_operational_ranking.v1"
)
PREFUSION_OPERATIONAL_RANKING_WEIGHTS = {
    "research_quality": 0.70,
    "research_confidence": 0.10,
    "stream_reliability": 0.12,
    "latency": 0.08,
}

# ``overall`` is a broad prior, while the axes are the evidence needed by the
# role router.  A positive broad score with no scored axis is not a
# comprehensive assessment.  Models that claim broad strength must cover at
# least three axes; genuinely narrow models may cover one axis and will be
# role-limited by the screening output.
PREFUSION_CAPABILITY_AXIS_MIN_NONZERO = 1
PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD = 0.70
PREFUSION_BROAD_CAPABILITY_AXIS_MIN_NONZERO = 3
PREFUSION_ROLE_NAMES = (
    "primary_solver",
    "independent_solver",
    "critic",
    "domain_specialist",
    "judge",
    "synthesizer",
    "structured_extraction",
    "simple_classification",
    "short_verification",
    "single_tool_argument_validation",
)


def clamp01(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        parsed = float(default)
    return round(max(0.0, min(1.0, parsed)), 6)


def capability_axis_coverage(
    capability_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate the minimum evidence coverage of a research capability row.

    A zero axis means that the research evidence did not support that
    capability.  This is different from an omitted field, which the strict
    schema already rejects.  The function is shared by research validation
    and registry loading so an old or edited handoff cannot regain serving
    status by bypassing the remote research step.
    """

    summary = capability_summary if isinstance(capability_summary, Mapping) else {}
    axes = summary.get("axes")
    axes = axes if isinstance(axes, Mapping) else {}
    values = [clamp01(axes.get(axis)) for axis in CAPABILITY_AXES]
    nonzero_count = sum(value > 0.0 for value in values)
    overall = clamp01(summary.get("overall"))
    required_nonzero_count = (
        PREFUSION_BROAD_CAPABILITY_AXIS_MIN_NONZERO
        if overall >= PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD
        else PREFUSION_CAPABILITY_AXIS_MIN_NONZERO
        if overall > 0.0
        else 0
    )
    if nonzero_count < required_nonzero_count:
        return {
            "eligible": False,
            "reason_code": (
                "prefusion_broad_capability_axis_coverage_insufficient"
                if overall >= PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD
                else "prefusion_capability_axis_coverage_missing"
            ),
            "overall": overall,
            "nonzero_axis_count": nonzero_count,
            "required_nonzero_axis_count": required_nonzero_count,
            "broad_overall_threshold": PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD,
            "broad_required_nonzero_axis_count": PREFUSION_BROAD_CAPABILITY_AXIS_MIN_NONZERO,
        }
    return {
        "eligible": True,
        "reason_code": "prefusion_capability_axis_coverage_verified",
        "overall": overall,
        "nonzero_axis_count": nonzero_count,
        "required_nonzero_axis_count": required_nonzero_count,
        "broad_overall_threshold": PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD,
        "broad_required_nonzero_axis_count": PREFUSION_BROAD_CAPABILITY_AXIS_MIN_NONZERO,
    }


def research_quality_score(capability_summary: Mapping[str, Any] | None) -> float:
    """Combine the Agent's overall score and complete capability axes.

    The overall score carries more weight because it is the Agent's explicit
    broad-capability judgment.  Axes provide a bounded consistency signal and
    expose malformed/overly generic rankings without pretending that the axes
    are benchmark measurements.
    """

    summary = capability_summary if isinstance(capability_summary, Mapping) else {}
    axes = summary.get("axes")
    axes = axes if isinstance(axes, Mapping) else {}
    axis_values = [clamp01(axes.get(axis)) for axis in CAPABILITY_AXES]
    overall = clamp01(summary.get("overall"))
    axis_mean = mean(axis_values) if axis_values else 0.0
    # A legacy ranking may have omitted useful axes while still carrying a
    # valid overall prior.  Keep that artifact readable; fresh ranking output
    # is required to provide non-zero axes by the model-screening validator.
    if max(axis_values, default=0.0) <= 0.0 and overall > 0.0:
        return overall
    return clamp01(overall * 0.70 + axis_mean * 0.30)


def probe_row_is_successful(row: Mapping[str, Any] | None) -> bool:
    """Return whether one physical replica has strict serving evidence."""

    if not isinstance(row, Mapping):
        return False
    return bool(
        str(row.get("status") or row.get("streaming_status") or "")
        .strip()
        .casefold()
        == "available"
        and is_sha256_digest(row.get("output_sha256"))
        and streaming_evidence_eligibility(row).get("eligible") is True
        and measured_stream_latency_eligibility(row).get("eligible") is True
    )


def probe_success_summary(
    profile_ids: Sequence[str],
    probe_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize all physical replicas, including missing/failed probes."""

    by_profile_id: dict[str, Mapping[str, Any]] = {}
    for row in probe_rows:
        if not isinstance(row, Mapping):
            continue
        profile_id = str(row.get("profile_id") or "")
        if profile_id and profile_id not in by_profile_id:
            by_profile_id[profile_id] = row
    ids = [str(value) for value in profile_ids if str(value)]
    rows = [by_profile_id.get(profile_id) for profile_id in ids]
    successes = [row for row in rows if probe_row_is_successful(row)]
    central_latencies: list[float] = []
    tail_latencies: list[float] = []
    for row in successes:
        try:
            central = float(
                row.get("p50_latency_ms", row.get("latency_ms"))
            )
        except (TypeError, ValueError):
            continue
        try:
            tail = float(row.get("p95_latency_ms", row.get("latency_ms")))
        except (TypeError, ValueError):
            tail = central
        if central >= 0:
            central_latencies.append(central)
        if tail >= 0:
            tail_latencies.append(tail)
    total = len(ids)
    success_count = len(successes)
    reliability = success_count / total if total else 0.0
    fastest_latency = min(central_latencies) if central_latencies else None
    slowest_latency = max(tail_latencies) if tail_latencies else None
    latency_score = (
        0.0
        if fastest_latency is None
        else clamp01(1.0 - fastest_latency / 90_000.0)
    )
    return {
        "replica_count": total,
        "probed_replica_count": sum(row is not None for row in rows),
        "successful_replica_count": success_count,
        "stream_reliability_score": clamp01(reliability),
        "latency_score": latency_score,
        # This is the fastest profile-level central latency from the current
        # probe run. A one-sample profile naturally contributes its observed
        # latency; a multi-sample profile contributes its measured p50.
        "fastest_observed_latency_ms": round(fastest_latency, 3)
        if fastest_latency is not None
        else None,
        "slowest_observed_latency_ms": round(slowest_latency, 3)
        if slowest_latency is not None
        else None,
        # Keep the compact internal aliases for old private artifacts and
        # callers.  New projections use the explicit observed names above.
        "fastest_latency_ms": round(fastest_latency, 3)
        if fastest_latency is not None
        else None,
        "slowest_latency_ms": round(slowest_latency, 3)
        if slowest_latency is not None
        else None,
        "all_replicas_have_success_evidence": bool(total and success_count == total),
        "successful_profile_ids": [
            str(row.get("profile_id") or "")
            for row in successes
            if str(row.get("profile_id") or "")
        ],
    }


def aggregate_profile_role_projection(
    profiles: Sequence[Any],
) -> tuple[list[str], list[str]]:
    """Union roles across physical replicas without counting replicas twice.

    A canonical model is one logical candidate, but its replicas may have
    different operational role receipts.  A role is available for the logical
    candidate when at least one currently eligible physical replica passed it;
    a role remains denied only when every replica denies it.  This preserves
    failover without letting one unhealthy replica erase a healthy one.
    """

    members = [profile for profile in profiles if profile is not None]
    if not members:
        return [], []
    allowed_sets = [
        {
            " ".join(str(role or "").strip().casefold().split())
            for role in getattr(profile, "screening_allowed_roles", ())
            if str(role or "").strip()
        }
        for profile in members
    ]
    denied_sets = [
        {
            " ".join(str(role or "").strip().casefold().split())
            for role in getattr(profile, "screening_disallowed_roles", ())
            if str(role or "").strip()
        }
        for profile in members
    ]
    allowed = set().union(*allowed_sets)
    denied = set.intersection(*denied_sets) if denied_sets else set()
    denied.difference_update(allowed)
    ordered_allowed = [role for role in PREFUSION_ROLE_NAMES if role in allowed]
    ordered_allowed.extend(
        sorted(role for role in allowed if role not in PREFUSION_ROLE_NAMES)
    )
    ordered_denied = [role for role in PREFUSION_ROLE_NAMES if role in denied]
    ordered_denied.extend(
        sorted(role for role in denied if role not in PREFUSION_ROLE_NAMES)
    )
    return ordered_allowed, ordered_denied


def operational_score(
    *,
    research_quality: Any,
    research_confidence: Any,
    stream_reliability: Any,
    latency: Any,
) -> float:
    """Compute the fixed serving-control score from its auditable components."""

    weights = PREFUSION_OPERATIONAL_RANKING_WEIGHTS
    return clamp01(
        clamp01(research_quality) * weights["research_quality"]
        + clamp01(research_confidence) * weights["research_confidence"]
        + clamp01(stream_reliability) * weights["stream_reliability"]
        + clamp01(latency) * weights["latency"]
    )


def operational_rank_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Sort available logical rows and assign contiguous operational ranks."""

    ordered = [dict(row) for row in rows if isinstance(row, Mapping)]
    ordered.sort(
        key=lambda row: (
            -clamp01(row.get("operational_score")),
            -clamp01(row.get("research_quality_score")),
            -clamp01(row.get("stream_reliability_score")),
            float(
                row.get("fastest_observed_latency_ms")
                or row.get("fastest_observed_p50_latency_ms")
                or 90_000.0
            ),
            str(row.get("canonical_identity_sha256") or ""),
        )
    )
    for rank, row in enumerate(ordered, start=1):
        row["operational_rank"] = rank
        row["available_rank"] = rank
    return ordered


def build_operational_model_rows(
    *,
    groups: Sequence[Mapping[str, Any]],
    ranking_rows: Sequence[Mapping[str, Any]],
    profiles: Sequence[Any],
    probe_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join the complete research ranking with physical probe evidence.

    A logical model is available when at least one physical replica has strict
    live stream evidence.  Failed replicas stay visible through the
    reliability component and are never counted as independent model votes.
    """

    group_by_candidate = {
        str(group.get("candidate_id") or ""): group
        for group in groups
        if isinstance(group, Mapping) and str(group.get("candidate_id") or "")
    }
    rows: list[dict[str, Any]] = []
    for ranking in ranking_rows:
        if not isinstance(ranking, Mapping):
            continue
        candidate_id = str(ranking.get("candidate_id") or "")
        group = group_by_candidate.get(candidate_id)
        if not group:
            continue
        replicas = group.get("replicas")
        replicas = replicas if isinstance(replicas, list) else []
        canonical = str(
            ranking.get("canonical_model_id")
            or group.get("canonical_model_id")
            or group.get("model")
            or ""
        )
        canonical_key = " ".join(canonical.casefold().split())
        physical_profiles = [
            profile
            for profile in profiles
            if " ".join(
                str(getattr(profile, "canonical_identity", "")).casefold().split()
            )
            == canonical_key
        ]
        profile_ids = [
            str(getattr(profile, "profile_id", ""))
            for profile in physical_profiles
            if str(getattr(profile, "profile_id", ""))
        ]
        summary = probe_success_summary(profile_ids, probe_rows)
        if not profile_ids:
            # A group without a corresponding physical profile cannot be
            # admitted.  Do not infer success from a provider/model alias.
            summary = probe_success_summary([], probe_rows)
        if int(summary.get("successful_replica_count") or 0) < 1:
            continue
        role_allowed, role_denied = aggregate_profile_role_projection(
            physical_profiles
        )
        capability = ranking.get("capability_summary")
        capability = capability if isinstance(capability, Mapping) else {}
        axes = capability.get("axes")
        axes = axes if isinstance(axes, Mapping) else {}
        research_score = research_quality_score(capability)
        confidence = clamp01(ranking.get("confidence"))
        reliability = clamp01(summary.get("stream_reliability_score"))
        latency_score = clamp01(summary.get("latency_score"))
        successful_profile_ids = {
            str(profile_id)
            for profile_id in summary.get("successful_profile_ids", [])
            if str(profile_id)
        }
        eligible_profile_hashes = {
            sha256_text(profile_id) for profile_id in successful_profile_ids
        }
        eligible_replicas = [
            dict(replica)
            for replica in replicas
            if isinstance(replica, Mapping)
            and str(replica.get("profile_id_sha256") or "").strip().lower()
            in {value.lower() for value in eligible_profile_hashes}
        ]
        available_replica_count = int(summary.get("successful_replica_count") or 0)
        physical_replica_count = int(summary.get("replica_count") or len(replicas))
        rows.append(
            {
                "rank": int(ranking.get("rank") or 0),
                "research_prior_rank": int(ranking.get("rank") or 0),
                "candidate_id": candidate_id,
                "provider": str(ranking.get("provider") or group.get("provider") or ""),
                "model": str(ranking.get("model") or group.get("model") or ""),
                "canonical_model_id": canonical,
                "api_format": str(ranking.get("api_format") or group.get("api_format") or ""),
                # Operational rows describe the currently serving subset.
                # The physical count remains available for reliability audit.
                "replica_count": available_replica_count,
                "available_replica_count": available_replica_count,
                "physical_replica_count": physical_replica_count,
                "failed_replica_count": max(
                    0, physical_replica_count - available_replica_count
                ),
                "replicas": eligible_replicas,
                "eligible_replica_profile_id_sha256s": sorted(
                    sha256_text(profile_id)
                    for profile_id in summary.get("successful_profile_ids", [])
                    if str(profile_id)
                ),
                "capability_summary": {
                    "overall": clamp01(capability.get("overall")),
                    "axes": {axis: clamp01(axes.get(axis)) for axis in CAPABILITY_AXES},
                    "strengths": list(capability.get("strengths") or [])[:8],
                    "limitations": list(capability.get("limitations") or [])[:8],
                },
                "allowed_roles": role_allowed,
                "disallowed_roles": role_denied,
                "role_admission": {
                    **(
                        dict(ranking.get("role_admission") or {})
                        if isinstance(ranking.get("role_admission"), Mapping)
                        else {}
                    ),
                    "effective_allowed_roles": role_allowed,
                    "effective_disallowed_roles": role_denied,
                    "replica_role_projection_is_union_for_allowed": True,
                    "replica_role_projection_is_intersection_for_denied": True,
                },
                "confidence": confidence,
                "research_quality_score": research_score,
                "stream_reliability_score": reliability,
                "latency_score": latency_score,
                "operational_score": operational_score(
                    research_quality=research_score,
                    research_confidence=confidence,
                    stream_reliability=reliability,
                    latency=latency_score,
                ),
                "fastest_observed_latency_ms": summary.get(
                    "fastest_observed_latency_ms",
                    summary.get("fastest_latency_ms"),
                ),
                "slowest_observed_latency_ms": summary.get(
                    "slowest_observed_latency_ms",
                    summary.get("slowest_latency_ms"),
                ),
                # Compatibility aliases for registries produced before the
                # observed-latency naming was made explicit.
                "fastest_observed_p50_latency_ms": summary.get(
                    "fastest_observed_latency_ms",
                    summary.get("fastest_latency_ms"),
                ),
                "slowest_observed_p50_latency_ms": summary.get(
                    "slowest_observed_latency_ms",
                    summary.get("slowest_latency_ms"),
                ),
                "streaming_eligible": True,
                "stream_evidence_verified": True,
                "all_replicas_have_success_evidence": summary.get(
                    "all_replicas_have_success_evidence"
                )
                is True,
                "replicas_are_failover_not_independent_votes": True,
                "research_prior_only": True,
                "operational_score_is_benchmark_evidence": False,
                "ranking_prior_forbidden_for_final_benchmark_claims": True,
            }
        )
    return operational_rank_rows(rows)


__all__ = [
    "PREFUSION_CAPABILITY_AXIS_MIN_NONZERO",
    "PREFUSION_BROAD_CAPABILITY_AXIS_MIN_NONZERO",
    "PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD",
    "PREFUSION_OPERATIONAL_RANKING_SCHEMA",
    "PREFUSION_OPERATIONAL_RANKING_WEIGHTS",
    "clamp01",
    "capability_axis_coverage",
    "operational_rank_rows",
    "build_operational_model_rows",
    "aggregate_profile_role_projection",
    "operational_score",
    "probe_row_is_successful",
    "probe_success_summary",
    "research_quality_score",
]
