from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .providers import (
    REASONING_TRANSPORT_BINDING_SCHEMA,
    reasoning_transport_probe_binding,
)
from .registry import (
    build_default_registry,
    load_registry,
    validate_prefusion_registry_handoff,
)
from .latency_policy import PROVIDER_MAX_RESPONSE_LATENCY_MS
from .schemas import (
    CAPABILITY_AXES,
    ModelProfile,
    normalize_reasoning_budget_tokens,
    normalize_reasoning_effort,
    sha256_text,
    stable_json,
)


# Operational calibration must remain importable by the serving process.  The
# optional benchmark-input path is explicitly opt-in, so it keeps only this
# static suite-to-axis mapping instead of importing the external evaluator.
_SUITE_CATEGORY_BY_ID = {
    "gpqa_diamond": "science_knowledge",
    "mmmu_text_science": "science_knowledge",
    "global_mmlu_lite": "multilingual",
    "flores_translation_instruction": "multilingual",
    "livecodebench": "code",
    "humaneval": "code",
    "math_500": "math",
    "aime_recent": "math",
    "bbh": "logic",
    "arc_challenge": "logic",
    "bfcl": "agentic_tool_calling",
    "tau_bench": "agentic_tool_calling",
    "ifeval": "daily_work",
    "mt_bench_work": "daily_work",
    "truthfulqa": "hallucination_factuality",
    "halueval": "hallucination_factuality",
    "medqa_usmle": "vertical_domain",
    "financebench": "vertical_domain",
    "legalbench": "vertical_domain",
    "bizbench": "vertical_domain",
    "policyllm_policybench": "vertical_domain",
}


def build_registry_calibration(
    *,
    registry_path: str | Path | None = None,
    probe_paths: Sequence[str | Path] = (),
    benchmark_paths: Sequence[str | Path] = (),
    feedback_paths: Sequence[str | Path] = (),
    trace_paths: Sequence[str | Path] = (),
    allow_benchmark_calibration: bool = False,
) -> dict[str, Any]:
    profiles = load_registry(registry_path)
    source_registry_payload = _load_source_registry_payload(registry_path)
    source_registry_is_prefusion = (
        source_registry_payload.get("generated_from_prefusion_screening") is True
    )
    source_prefusion_validation = (
        validate_prefusion_registry_handoff(
            source_registry_payload,
            require_ready=True,
        )
        if source_registry_is_prefusion
        else {
            "schema": "axio_fusion_api.prefusion_registry_handoff_validation.v1",
            "valid": True,
            "reason_codes": [],
            "require_ready": True,
        }
    )
    profile_map = {profile.profile_id: profile for profile in profiles}
    hash_to_profile = {sha256_text(profile.profile_id): profile.profile_id for profile in profiles}
    signals: dict[str, dict[str, Any]] = {profile.profile_id: _empty_signal(profile) for profile in profiles}
    probe_rows = _load_probe_rows(probe_paths)
    benchmark_calibration_requested = bool(benchmark_paths)
    benchmark_calibration_blocked = benchmark_calibration_requested and not allow_benchmark_calibration
    benchmark_rows = _load_benchmark_rows(benchmark_paths) if allow_benchmark_calibration else []
    feedback_rows = _load_jsonl_rows(feedback_paths)
    trace_rows = _load_jsonl_rows(trace_paths)
    _apply_probe_signals(signals, probe_rows)
    _apply_tool_probe_signals(signals, probe_rows)
    _apply_reasoning_probe_signals(signals, probe_rows)
    _apply_benchmark_signals(signals, benchmark_rows)
    _apply_feedback_signals(signals, feedback_rows, hash_to_profile)
    _apply_trace_signals(signals, trace_rows, hash_to_profile)
    patches = [
        _signal_to_patch(
            signal,
            profile=profile_map.get(str(signal.get("profile_id") or "")),
        )
        for signal in signals.values()
    ]
    patches.sort(key=lambda row: str(row["profile_id"]))
    updated_registry = _updated_registry_payload(
        profiles,
        patches,
        profile_map,
        source_payload=source_registry_payload,
        calibration_probe_file_count=len(probe_paths),
    )
    benchmark_calibration_applied = bool(benchmark_rows)
    prefusion_handoff_blocked = bool(
        source_registry_is_prefusion
        and source_prefusion_validation.get("valid") is not True
    )
    blocker_reason_codes = (
        ["prefusion_registry_source_handoff_invalid"]
        if prefusion_handoff_blocked
        else []
    )
    return {
        "schema": "axio_fusion_api.registry_calibration.v1",
        "registry_model_count": len(profiles),
        "input_artifacts": {
            "probe_file_count": len(probe_paths),
            "benchmark_file_count": len(benchmark_paths),
            "feedback_file_count": len(feedback_paths),
            "trace_file_count": len(trace_paths),
            "probe_row_count": len(probe_rows),
            "tool_probe_row_count": sum(
                1 for row in probe_rows if _is_tool_probe_row(row)
            ),
            "reasoning_probe_row_count": sum(
                1 for row in probe_rows if _is_reasoning_probe_row(row)
            ),
            "benchmark_row_count": len(benchmark_rows),
            "feedback_row_count": len(feedback_rows),
            "trace_row_count": len(trace_rows),
        },
        "patches": patches,
        "updated_registry": updated_registry,
        "source_registry_is_prefusion": source_registry_is_prefusion,
        "source_prefusion_handoff_validation": source_prefusion_validation,
        "application_contract": {
            "safe_to_write_registry": not benchmark_calibration_blocked
            and not prefusion_handoff_blocked,
            "benchmark_calibration_requested": benchmark_calibration_requested,
            "benchmark_calibration_opted_in": bool(allow_benchmark_calibration),
            "benchmark_calibration_applied": benchmark_calibration_applied,
            "benchmark_calibration_blocked": benchmark_calibration_blocked,
            "prefusion_handoff_blocked": prefusion_handoff_blocked,
            "benchmark_results_used_for_registry_calibration": benchmark_calibration_applied,
            "reasoning_transport_probe_requires_current_endpoint_binding": True,
            "cross_registry_reasoning_transport_promotion_requires_reconciliation": True,
            "final_claim_eligible_without_training_contamination_audit": not benchmark_calibration_applied
            and not prefusion_handoff_blocked,
            "blocker_reason_codes": (
                [
                    *(["benchmark_calibration_requires_explicit_opt_in"]
                      if benchmark_calibration_blocked
                      else []),
                    *blocker_reason_codes,
                ]
            ),
            "overwrites_secrets": False,
            "raw_prompt_persisted": False,
            "raw_feedback_text_persisted": False,
            "raw_provider_output_persisted": False,
            "raw_benchmark_labels_persisted": False,
        },
        "calibration_policy": {
            "benchmark_calibration_default": "blocked",
            "benchmark_calibration_requires_explicit_opt_in": True,
            "benchmark_calibration_is_exploratory_only": True,
            "benchmark_calibration_requires_separate_holdout_and_training_contamination_audit": True,
            "benchmark_calibration_must_not_be_used_for_final_claim_registry": True,
            "raw_benchmark_labels_loaded": benchmark_calibration_applied,
        },
        "secrets_persisted": False,
        "raw_prompt_persisted": False,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _empty_signal(profile: ModelProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "status_counts": {},
        "latencies_ms": [],
        "benchmark_scores": {},
        "feedback_scores": [],
        "feedback_accepts": [],
        "trace_latencies_ms": [],
        "trace_costs_usd": [],
        "trace_provider_calls": [],
        "trace_seen_count": 0,
        "tool_probe_status_counts": {},
        "tool_probe_latencies_ms": [],
        "tool_probe_total": 0,
        "tool_call_supported_count": 0,
        "reasoning_probe_rows": [],
        "current_reasoning_transport": (
            dict(profile.reasoning_transport)
            if isinstance(profile.reasoning_transport, Mapping)
            else {}
        ),
        "current_capabilities": dict(profile.capabilities),
        "current_supports_tools": bool(profile.supports_tools),
        "current_tool_capability": profile.tool_capability,
        "current_tool_capability_source": profile.tool_capability_source,
        "current_tool_probe_status": profile.tool_probe_status,
    }


def _apply_probe_signals(signals: dict[str, dict[str, Any]], rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        if _is_tool_probe_row(row) or _is_reasoning_probe_row(row):
            continue
        profile_id = str(row.get("profile_id") or "")
        if profile_id not in signals:
            continue
        status = str(row.get("status") or "unknown")
        signals[profile_id]["status_counts"][status] = signals[profile_id]["status_counts"].get(status, 0) + 1
        latency = _optional_float(row.get("latency_ms"))
        if latency is not None and latency > 0:
            signals[profile_id]["latencies_ms"].append(latency)


def _apply_tool_probe_signals(
    signals: dict[str, dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    for row in rows:
        if not _is_tool_probe_row(row):
            continue
        profile_id = str(row.get("profile_id") or "")
        if profile_id not in signals:
            continue
        status = str(row.get("status") or "unknown")
        counts = signals[profile_id]["tool_probe_status_counts"]
        counts[status] = counts.get(status, 0) + 1
        signals[profile_id]["tool_probe_total"] += 1
        if status == "tool_call_supported":
            signals[profile_id]["tool_call_supported_count"] += 1
        latency = _optional_float(row.get("latency_ms"))
        if latency is not None and latency > 0:
            signals[profile_id]["tool_probe_latencies_ms"].append(latency)


def _apply_reasoning_probe_signals(
    signals: dict[str, dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    for row in rows:
        if not _is_reasoning_probe_row(row):
            continue
        profile_id = str(row.get("profile_id") or "")
        if profile_id not in signals:
            continue
        signals[profile_id]["reasoning_probe_rows"].append(dict(row))


def _apply_benchmark_signals(signals: dict[str, dict[str, Any]], rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id.startswith("provider::"):
            continue
        profile_id = candidate_id[len("provider::") :]
        if profile_id not in signals:
            continue
        accuracy = _optional_float(row.get("accuracy"))
        if accuracy is None:
            continue
        category = _suite_category(str(row.get("suite_id") or ""))
        bucket = signals[profile_id]["benchmark_scores"].setdefault(category, [])
        bucket.append(max(0.0, min(1.0, accuracy)))


def _apply_feedback_signals(
    signals: dict[str, dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    hash_to_profile: Mapping[str, str],
) -> None:
    for row in rows:
        route = row.get("route_snapshot") if isinstance(row.get("route_snapshot"), Mapping) else {}
        profile_hashes = route.get("selected_profile_hashes") if isinstance(route.get("selected_profile_hashes"), list) else []
        score = _optional_float(row.get("score"))
        if score is None:
            score = _external_verification_score(row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {})
        accepted = row.get("accepted")
        for profile_hash in profile_hashes:
            profile_id = hash_to_profile.get(str(profile_hash))
            if not profile_id or profile_id not in signals:
                continue
            if score is not None:
                signals[profile_id]["feedback_scores"].append(max(-1.0, min(1.0, score)))
            if accepted is not None:
                signals[profile_id]["feedback_accepts"].append(bool(accepted))


def _apply_trace_signals(
    signals: dict[str, dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    hash_to_profile: Mapping[str, str],
) -> None:
    for row in rows:
        routing = row.get("routing_decision") if isinstance(row.get("routing_decision"), Mapping) else {}
        profile_hashes = routing.get("selected_profile_hashes") if isinstance(routing.get("selected_profile_hashes"), list) else []
        latency = _optional_float(row.get("latency_ms"))
        cost = _optional_float(row.get("cost", {}).get("actual_cost_usd")) if isinstance(row.get("cost"), Mapping) else None
        calls = _optional_float(row.get("cost", {}).get("provider_call_count")) if isinstance(row.get("cost"), Mapping) else None
        for profile_hash in profile_hashes:
            profile_id = hash_to_profile.get(str(profile_hash))
            if not profile_id or profile_id not in signals:
                continue
            signals[profile_id]["trace_seen_count"] += 1
            if latency is not None:
                signals[profile_id]["trace_latencies_ms"].append(latency)
            if cost is not None:
                signals[profile_id]["trace_costs_usd"].append(cost)
            if calls is not None:
                signals[profile_id]["trace_provider_calls"].append(calls)


def _signal_to_patch(
    signal: Mapping[str, Any],
    *,
    profile: ModelProfile | None,
) -> dict[str, Any]:
    status_counts = signal.get("status_counts") if isinstance(signal.get("status_counts"), Mapping) else {}
    available = int(status_counts.get("available") or 0)
    failures = int(status_counts.get("failed") or 0) + int(status_counts.get("unexpected_output") or 0)
    probe_total = available + failures
    trace_seen = int(signal.get("trace_seen_count") or 0)
    tool_probe_total = int(signal.get("tool_probe_total") or 0)
    tool_call_supported_count = int(signal.get("tool_call_supported_count") or 0)
    tool_support_rate = (
        None
        if tool_probe_total <= 0
        else round(tool_call_supported_count / tool_probe_total, 6)
    )
    feedback_scores = [float(value) for value in signal.get("feedback_scores", [])]
    feedback_accepts = [bool(value) for value in signal.get("feedback_accepts", [])]
    success_count = available + sum(1 for value in feedback_scores if value >= 0) + sum(1 for value in feedback_accepts if value)
    failure_count = failures + sum(1 for value in feedback_scores if value < 0) + sum(1 for value in feedback_accepts if not value)
    observed_total = success_count + failure_count
    availability = None if probe_total <= 0 else round(available / probe_total, 6)
    recent_success_rate = None if observed_total <= 0 else round(success_count / observed_total, 6)
    latency_values = [
        *signal.get("latencies_ms", []),
        *signal.get("trace_latencies_ms", []),
        *signal.get("tool_probe_latencies_ms", []),
    ]
    benchmark_scores = signal.get("benchmark_scores") if isinstance(signal.get("benchmark_scores"), Mapping) else {}
    capabilities_patch = _capability_patch(signal.get("current_capabilities") or {}, benchmark_scores, feedback_scores)
    health = _health_from_signals(availability, recent_success_rate, probe_total, trace_seen)
    capabilities_patch = dict(capabilities_patch)
    if tool_support_rate is not None:
        base_tool_capability = _optional_float(
            signal.get("current_capabilities", {}).get("agentic_tool_calling")
        ) or 0.0
        capabilities_patch["agentic_tool_calling"] = round(
            max(
                0.0,
                min(1.0, base_tool_capability * 0.55 + tool_support_rate * 0.45),
            ),
            6,
        )
    tool_status_counts = signal.get("tool_probe_status_counts") if isinstance(signal.get("tool_probe_status_counts"), Mapping) else {}
    if tool_probe_total <= 0:
        tool_capability_patch = None
        tool_capability_source_patch = None
        tool_probe_status_patch = None
        supports_tools_patch = None
    else:
        tool_capability_patch = (
            "proven"
            if tool_call_supported_count > 0 and tool_support_rate is not None and tool_support_rate >= 0.5
            else "failed"
        )
        tool_capability_source_patch = (
            "operational_probe"
            if not signal.get("current_supports_tools")
            else "external_attestation+operational_probe"
        )
        tool_probe_status_patch = _dominant_tool_probe_status(tool_status_counts)
        # A negative probe may not erase a separately declared external
        # attestation.  It still records failed operational evidence above.
        supports_tools_patch = (
            True
            if tool_capability_patch == "proven"
            else None
            if signal.get("current_supports_tools")
            else False
        )
    reasoning_transport_patch = _reasoning_transport_patch(
        profile,
        signal.get("current_reasoning_transport"),
        signal.get("reasoning_probe_rows"),
    )
    return {
        "profile_id": signal["profile_id"],
        "provider": signal["provider"],
        "model": signal["model"],
        "health": health,
        "availability": availability,
        "recent_success_rate": recent_success_rate,
        "observed_success_count": success_count,
        "observed_failure_count": failure_count,
        "observed_latency_ms": _median(latency_values),
        "p50_latency_ms": _median(latency_values),
        "p95_latency_ms": _percentile(latency_values, 0.95),
        "capabilities_patch": capabilities_patch,
        "supports_tools_patch": supports_tools_patch,
        "tool_capability_patch": tool_capability_patch,
        "tool_capability_source_patch": tool_capability_source_patch,
        "tool_probe_status_patch": tool_probe_status_patch,
        "tool_support_rate": tool_support_rate,
        "reasoning_transport_patch": reasoning_transport_patch,
        "signal_counts": {
            "probe_total": probe_total,
            "benchmark_category_count": len(benchmark_scores),
            "feedback_count": len(feedback_scores) + len(feedback_accepts),
            "trace_seen_count": trace_seen,
            "tool_probe_total": tool_probe_total,
            "tool_call_supported_count": tool_call_supported_count,
            "tool_probe_status_counts": dict(sorted((signal.get("tool_probe_status_counts") or {}).items())),
            "reasoning_probe_total": len(
                signal.get("reasoning_probe_rows", [])
                if isinstance(signal.get("reasoning_probe_rows"), Sequence)
                else []
            ),
        },
        "raw_prompt_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def _reasoning_transport_patch(
    profile: ModelProfile | None,
    current: Any,
    rows: Any,
) -> dict[str, Any] | None:
    """Return a status-only capability promotion from strict probe evidence."""

    config = dict(current) if isinstance(current, Mapping) else {}
    if profile is None or str(config.get("status") or "").strip().casefold() != "candidate":
        return None
    declared_efforts = _reasoning_probe_efforts(config)
    declared_budgets = _normalized_reasoning_budgets(
        config.get("supported_budget_tokens")
    )
    if not declared_efforts and not declared_budgets:
        return None
    probe_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, Sequence) else []
    exact_rows = [
        row
        for row in probe_rows
        if str(row.get("probe_kind") or "").strip().casefold() == "reasoning_transport"
        and row.get("live_probe_evidence") is True
        and str(row.get("transport") or "") == str(config.get("transport") or "")
        and _normalized_reasoning_efforts(row.get("declared_efforts")) == declared_efforts
        and _normalized_reasoning_budgets(row.get("declared_budget_tokens"))
        == declared_budgets
        and _reasoning_probe_binding_matches(profile, row)
    ]
    if not exact_rows:
        return None
    if any(
        _reasoning_probe_row_verified(row, declared_efforts, declared_budgets)
        for row in exact_rows
    ):
        patched = dict(config)
        patched["status"] = "verified"
        return patched
    if any(_reasoning_probe_row_rejected(row) for row in exact_rows):
        patched = dict(config)
        patched["status"] = "unsupported"
        return patched
    return None


def _reasoning_probe_binding_matches(
    profile: ModelProfile,
    row: Mapping[str, Any],
) -> bool:
    """Accept only a valid probe bound to the endpoint currently configured.

    Generic calibration may aggregate several operational artifacts, but it
    must not turn an old reasoning probe into a capability claim after an
    operator retargets the profile's gateway. Cross-registry promotion still
    requires the stricter full-cohort reconciliation control plane.
    """

    expected = reasoning_transport_probe_binding(profile)
    observed = (
        row.get("reasoning_transport_binding")
        if isinstance(row.get("reasoning_transport_binding"), Mapping)
        else {}
    )
    if expected.get("endpoint_binding_ready") is not True:
        return False
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


def _reasoning_probe_row_verified(
    row: Mapping[str, Any],
    declared_efforts: Sequence[str],
    declared_budgets: Sequence[int] = (),
) -> bool:
    if (
        str(row.get("status") or "").strip().casefold() != "verified"
        or row.get("strict_wire_shape_preserved") is not True
        or row.get("all_declared_efforts_strict_streaming") is not True
    ):
        return False
    control = row.get("control") if isinstance(row.get("control"), Mapping) else {}
    if not _strict_reasoning_attempt_accepted(control):
        return False
    attempts = row.get("effort_results") if isinstance(row.get("effort_results"), list) else []
    by_effort = {
        normalize_reasoning_effort(attempt.get("effort")): attempt
        for attempt in attempts
        if isinstance(attempt, Mapping)
        and normalize_reasoning_effort(attempt.get("effort"))
    }
    return all(
        _strict_reasoning_attempt_accepted(by_effort.get(effort, {}))
        for effort in declared_efforts
    ) and _budget_probe_rows_verified(row, declared_budgets)


def _budget_probe_rows_verified(
    row: Mapping[str, Any],
    declared_budgets: Sequence[int],
) -> bool:
    if not declared_budgets:
        return not _normalized_reasoning_budgets(row.get("declared_budget_tokens"))
    if row.get("all_declared_budgets_strict_streaming") is not True:
        return False
    budget_rows = row.get("budget_results") if isinstance(row.get("budget_results"), list) else []
    by_budget = {
        budget: attempt
        for attempt in budget_rows
        if isinstance(attempt, Mapping)
        for budget in _normalized_reasoning_budgets([attempt.get("budget_tokens")])
    }
    return all(
        _strict_reasoning_attempt_accepted(by_budget.get(budget, {}))
        for budget in declared_budgets
    ) or bool(
        row.get("all_declared_reasoning_controls_strict_streaming") is True
        and row.get("verified_budget_tokens")
        and set(_normalized_reasoning_budgets(row.get("verified_budget_tokens")))
        >= set(declared_budgets)
    )


def _reasoning_probe_row_rejected(row: Mapping[str, Any]) -> bool:
    if str(row.get("status") or "").strip().casefold() != "rejected":
        return False
    control = row.get("control") if isinstance(row.get("control"), Mapping) else {}
    if not _strict_reasoning_attempt_accepted(control):
        return False
    attempts: list[Any] = []
    if isinstance(row.get("effort_results"), list):
        attempts.extend(row.get("effort_results"))
    if isinstance(row.get("budget_results"), list):
        attempts.extend(row.get("budget_results"))
    return any(
        isinstance(attempt, Mapping)
        and str(attempt.get("status") or "").strip().casefold() == "rejected"
        and 400 <= _safe_count(attempt.get("http_status")) < 500
        for attempt in attempts
    )


def _strict_reasoning_attempt_accepted(row: Mapping[str, Any]) -> bool:
    latency = _optional_float(row.get("latency_ms"))
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
        and _safe_count(row.get("stream_frame_count")) >= 1
        and latency is not None
        and 0.0 <= latency <= PROVIDER_MAX_RESPONSE_LATENCY_MS
    )


def _normalized_reasoning_efforts(value: Any) -> list[str]:
    raw_values = (
        value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
        else []
    )
    values: list[str] = []
    for raw in raw_values:
        effort = normalize_reasoning_effort(raw)
        if effort and effort not in values:
            values.append(effort)
    return values


def _reasoning_probe_efforts(config: Mapping[str, Any]) -> list[str]:
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
    raw_values = value if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ) else []
    budgets: list[int] = []
    for raw in raw_values:
        budget = normalize_reasoning_budget_tokens(raw)
        if budget is not None and budget not in budgets:
            budgets.append(budget)
    return sorted(budgets)


def _dominant_tool_probe_status(counts: Mapping[str, Any]) -> str:
    """Choose a deterministic status for a profile's bounded probe cohort."""

    priority = {
        "tool_call_supported": 4,
        "tool_call_unparseable": 3,
        "text_only": 2,
        "protocol_failure": 1,
        "transport_failure": 1,
    }
    rows = [
        (str(status), _safe_count(count), priority.get(str(status), 0))
        for status, count in counts.items()
        if str(status)
    ]
    if not rows:
        return "probe_failed"
    rows.sort(key=lambda row: (row[1], row[2], row[0]), reverse=True)
    return rows[0][0]


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _capability_patch(
    current: Mapping[str, Any],
    benchmark_scores: Mapping[str, Sequence[float]],
    feedback_scores: Sequence[float],
) -> dict[str, float]:
    patch = {}
    feedback_adjustment = 0.0
    if feedback_scores:
        avg_feedback = sum(feedback_scores) / len(feedback_scores)
        feedback_adjustment = max(-0.06, min(0.06, avg_feedback * 0.04))
    for axis in CAPABILITY_AXES:
        base = _optional_float(current.get(axis)) or 0.35
        scores = [float(value) for value in benchmark_scores.get(axis, [])] if axis in benchmark_scores else []
        if scores:
            observed = sum(scores) / len(scores)
            patch[axis] = round(max(0.0, min(1.0, base * 0.70 + observed * 0.30 + feedback_adjustment)), 6)
        elif feedback_scores:
            patch[axis] = round(max(0.0, min(1.0, base + feedback_adjustment)), 6)
    return patch


def _updated_registry_payload(
    profiles: Sequence[ModelProfile],
    patches: Sequence[Mapping[str, Any]],
    profile_map: Mapping[str, ModelProfile],
    *,
    source_payload: Mapping[str, Any] | None = None,
    calibration_probe_file_count: int = 0,
) -> dict[str, Any]:
    source_payload = source_payload if isinstance(source_payload, Mapping) else {}
    prefusion_bound = source_payload.get("generated_from_prefusion_screening") is True
    patch_map = {str(patch.get("profile_id") or ""): patch for patch in patches}
    models = []
    for profile in profiles:
        row = profile.safe_dict()
        # The calibrated registry is a private serving artifact. Preserve the
        # declared identity here so replica deduplication and failover remain
        # explainable after calibration; safe artifacts keep only its hash.
        if profile.canonical_model_id:
            row["canonical_model_id"] = profile.canonical_model_id
        patch = patch_map.get(profile.profile_id, {})
        caps_patch = patch.get("capabilities_patch") if isinstance(patch.get("capabilities_patch"), Mapping) else {}
        if caps_patch:
            row["capabilities"] = {axis: float(caps_patch.get(axis, row["capabilities"].get(axis, 0.35))) for axis in CAPABILITY_AXES}
        # A pre-Fusion registry has already passed a hash-bound live stream
        # admission. Calibration may enrich routing/tool metadata, but it
        # must not rewrite the admission state from a later, smaller sample
        # and accidentally make the registry unloadable. Runtime health
        # overlays remain the place for post-admission failures.
        if not prefusion_bound:
            for key in (
                "health",
                "availability",
                "recent_success_rate",
                "observed_success_count",
                "observed_failure_count",
                "p50_latency_ms",
                "p95_latency_ms",
            ):
                if key in patch and patch[key] is not None:
                    row[key] = patch[key]
        if patch.get("supports_tools_patch") is not None:
            row["supports_tools"] = bool(patch["supports_tools_patch"])
        for patch_key, row_key in (
            ("tool_capability_patch", "tool_capability"),
            ("tool_capability_source_patch", "tool_capability_source"),
            ("tool_probe_status_patch", "tool_probe_status"),
        ):
            if patch.get(patch_key) is not None:
                row[row_key] = patch[patch_key]
        if isinstance(patch.get("reasoning_transport_patch"), Mapping):
            row["reasoning_transport"] = dict(patch["reasoning_transport_patch"])
        row["source"] = "calibrated_registry"
        row["calibration"] = {
            "profile_id_sha256": sha256_text(profile.profile_id),
            "signal_counts": patch.get("signal_counts", {}),
            "tool_support_rate": patch.get("tool_support_rate"),
            "tool_capability": patch.get("tool_capability_patch"),
            "tool_probe_status": patch.get("tool_probe_status_patch"),
            "supports_tools_updated_from_operational_probe": patch.get("supports_tools_patch") is not None,
            "reasoning_transport_status": (
                str(patch.get("reasoning_transport_patch", {}).get("status") or "")
                if isinstance(patch.get("reasoning_transport_patch"), Mapping)
                else ""
            ),
            "reasoning_transport_updated_from_operational_probe": isinstance(
                patch.get("reasoning_transport_patch"), Mapping
            ),
            "raw_prompt_persisted": False,
            "raw_provider_output_persisted": False,
        }
        models.append(row)
    if prefusion_bound:
        # Keep the complete pre-Fusion envelope, including the logical model
        # list, physical probe bindings, catalog digest, and ranking contract.
        # Rebuilding from build_default_registry() here would silently turn a
        # valid production handoff into a legacy registry.
        payload = json.loads(
            json.dumps(dict(source_payload), ensure_ascii=False, default=str)
        )
    else:
        payload = build_default_registry()
        for key in (
            "standalone_product",
            "decoupled_from_asci_fs",
            "public_models",
            "generated_from_probe",
            "source_artifacts",
            "generation_contract",
            "available_model_count",
            "live_available_model_count",
            "readiness",
        ):
            if key in source_payload:
                payload[key] = source_payload[key]
    payload["models"] = models
    payload["schema"] = "axio_fusion_api.registry.v1"
    payload["calibrated"] = True
    payload["calibration_schema"] = "axio_fusion_api.registry_calibration.v1"
    payload["model_count"] = len(models)
    payload["provider_count"] = len({str(row.get("provider") or "") for row in models})
    payload["calibration_source_artifacts"] = {
        "probe_file_count": len(source_payload.get("source_artifacts", {}).get("probe_file_path_hashes", []))
        if isinstance(source_payload.get("source_artifacts"), Mapping)
        else 0,
        "calibration_probe_file_count": max(0, int(calibration_probe_file_count)),
        "tool_probe_row_count": sum(
            int(patch.get("signal_counts", {}).get("tool_probe_total") or 0)
            for patch in patches
            if isinstance(patch.get("signal_counts"), Mapping)
        ),
        "reasoning_probe_row_count": sum(
            int(patch.get("signal_counts", {}).get("reasoning_probe_total") or 0)
            for patch in patches
            if isinstance(patch.get("signal_counts"), Mapping)
        ),
        "raw_probe_paths_persisted": False,
        "raw_provider_outputs_persisted": False,
    }
    generation_contract = payload.get("generation_contract")
    generation_contract = (
        dict(generation_contract) if isinstance(generation_contract, Mapping) else {}
    )
    generation_contract.update(
        {
            "calibration_preserves_prefusion_handoff": prefusion_bound,
            "calibration_does_not_rewrite_prefusion_stream_admission": prefusion_bound,
            "runtime_health_overlay_required_for_post_admission_failures": prefusion_bound,
        }
    )
    payload["generation_contract"] = generation_contract
    payload["secrets_persisted"] = False
    payload["raw_prompt_persisted"] = False
    return payload


def _load_source_registry_payload(path: str | Path | None) -> dict[str, Any]:
    selected = Path(path or os.getenv("AXIO_FUSION_REGISTRY_PATH", "").strip())
    if not str(selected) or not selected.exists():
        return {}
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _load_probe_rows(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for payload in _load_json_files(paths):
        payload_probe_kind = str(payload.get("probe_kind") or "").strip()
        if isinstance(payload.get("probes"), list):
            for row in payload["probes"]:
                if not isinstance(row, dict):
                    continue
                copied = dict(row)
                if payload_probe_kind and not copied.get("probe_kind"):
                    copied["probe_kind"] = payload_probe_kind
                rows.append(copied)
        probe_report = payload.get("probe_report") if isinstance(payload.get("probe_report"), Mapping) else {}
        if isinstance(probe_report.get("probes"), list):
            for row in probe_report["probes"]:
                if not isinstance(row, dict):
                    continue
                copied = dict(row)
                if payload_probe_kind and not copied.get("probe_kind"):
                    copied["probe_kind"] = payload_probe_kind
                rows.append(copied)
    return rows


def _is_tool_probe_row(row: Mapping[str, Any]) -> bool:
    return str(row.get("probe_kind") or row.get("probe_type") or "").strip().lower() == "tool_call"


def _is_reasoning_probe_row(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("probe_kind") or row.get("probe_type") or "")
        .strip()
        .lower()
        == "reasoning_transport"
    )


def _load_benchmark_rows(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for payload in _load_json_files(paths):
        if payload.get("schema") == "axio_fusion_api.multiple_choice_benchmark_run.v1":
            rows.append(dict(payload))
        elif isinstance(payload.get("runs"), list):
            rows.extend(row for row in payload["runs"] if isinstance(row, dict))
        elif isinstance(payload.get("candidates"), list):
            rows.extend(_scorecard_candidate_to_row(row) for row in payload["candidates"] if isinstance(row, Mapping))
    return rows


def _scorecard_candidate_to_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "case_count": row.get("case_count"),
        "accuracy": row.get("accuracy"),
        "latency_ms": row.get("total_latency_ms"),
    }


def _load_json_files(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        selected = Path(path)
        if not selected.exists():
            continue
        try:
            payload = json.loads(selected.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        elif isinstance(payload, list):
            rows.extend(row for row in payload if isinstance(row, dict))
    return rows


def _load_jsonl_rows(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        selected = Path(path)
        if not selected.exists():
            continue
        for line in selected.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _suite_category(suite_id: str) -> str:
    return _SUITE_CATEGORY_BY_ID.get(str(suite_id or ""), "daily_work")


def _health_from_signals(
    availability: float | None,
    recent_success_rate: float | None,
    probe_total: int,
    trace_seen: int,
) -> str:
    if availability is not None and availability <= 0.0 and probe_total > 0:
        return "unavailable"
    values = [value for value in (availability, recent_success_rate) if value is not None]
    if values and min(values) < 0.45:
        return "degraded"
    if values and min(values) >= 0.75:
        return "available"
    if trace_seen > 0:
        return "observed"
    return "unknown"


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _external_verification_score(value: Mapping[str, Any]) -> float | None:
    score = _optional_float(value.get("score"))
    if score is not None:
        if score > 1.0:
            score = score / 100.0 if score > 5.0 else score / 5.0
        return max(-1.0, min(1.0, score))
    status = str(value.get("status") or "").strip().lower()
    passed = value.get("passed")
    if isinstance(passed, bool):
        return 1.0 if passed else -1.0
    if status in {"pass", "passed", "success", "succeeded", "verified", "ok", "correct", "accepted"}:
        return 1.0
    if status in {"fail", "failed", "failure", "error", "incorrect", "rejected", "regression", "timeout"}:
        return -1.0
    return None


def _median(values: Sequence[Any]) -> int | None:
    clean = sorted(float(value) for value in values if _optional_float(value) is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return int(round(clean[mid]))
    return int(round((clean[mid - 1] + clean[mid]) / 2))


def _percentile(values: Sequence[Any], q: float) -> int | None:
    clean = sorted(float(value) for value in values if _optional_float(value) is not None)
    if not clean:
        return None
    index = min(len(clean) - 1, max(0, int(round((len(clean) - 1) * q))))
    return int(round(clean[index]))
