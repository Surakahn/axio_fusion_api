from __future__ import annotations

import copy
import json
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .schemas import sha256_text


@dataclass(frozen=True)
class ResponseContinuation:
    """Private, process-local state for one Responses API continuation.

    The history and tool data intentionally remain in RAM so a standard
    ``previous_response_id`` turn can be reconstructed.  They are never
    included in runtime snapshots, traces, feedback artifacts, or any other
    durable output.
    """

    response_id: str
    tenant_key: str
    history: tuple[dict[str, Any], ...]
    model: str
    instructions: str
    tools: tuple[dict[str, Any], ...]
    created_at: float
    expires_at: float
    last_accessed_at: float
    context_char_count: int


class RuntimeState:
    """In-memory gateway controls and safe feedback receipts.

    This state is deliberately local to the standalone Fusion service.  Durable
    feedback artifacts contain hashes and policy metadata, never raw prompts,
    free-form user notes, provider outputs, or API keys.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rate_windows: dict[str, list[float]] = {}
        self._budget_spend: dict[str, tuple[str, float]] = {}
        self._feedback_count = 0
        self._feedback_by_score: dict[str, int] = {}
        self._response_continuations: dict[str, ResponseContinuation] = {}

    def check_rate_limit(self, tenant_key: str, *, now: float | None = None) -> dict[str, Any]:
        limit = _env_int("AXIO_FUSION_RATE_LIMIT_PER_MINUTE")
        if not limit or limit <= 0:
            return {"allowed": True, "limit": None, "remaining": None, "retry_after_seconds": 0}
        current = float(now if now is not None else time.time())
        cutoff = current - 60.0
        with self._lock:
            bucket = [stamp for stamp in self._rate_windows.get(tenant_key, []) if stamp >= cutoff]
            allowed = len(bucket) < limit
            retry_after = 0
            if allowed:
                bucket.append(current)
            elif bucket:
                retry_after = max(1, int(60 - (current - bucket[0])))
            self._rate_windows[tenant_key] = bucket
            remaining = max(0, limit - len(bucket))
        return {
            "allowed": allowed,
            "limit": limit,
            "remaining": remaining,
            "retry_after_seconds": retry_after,
        }

    def check_budget(self, tenant_key: str, *, now: float | None = None) -> dict[str, Any]:
        daily_budget = _env_float("AXIO_FUSION_TENANT_DAILY_BUDGET_USD")
        if daily_budget is None or daily_budget <= 0:
            return {"allowed": True, "daily_budget_usd": None, "spent_usd": 0.0, "remaining_usd": None}
        day = _utc_day(now)
        with self._lock:
            stored_day, spent = self._budget_spend.get(tenant_key, (day, 0.0))
            if stored_day != day:
                stored_day, spent = day, 0.0
            self._budget_spend[tenant_key] = (stored_day, spent)
        remaining = max(0.0, daily_budget - spent)
        return {
            "allowed": spent < daily_budget,
            "daily_budget_usd": daily_budget,
            "spent_usd": round(spent, 8),
            "remaining_usd": round(remaining, 8),
        }

    def record_cost(self, tenant_key: str, cost_usd: float | None, *, now: float | None = None) -> None:
        if cost_usd is None:
            return
        try:
            amount = max(0.0, float(cost_usd))
        except (TypeError, ValueError):
            return
        if amount <= 0:
            return
        day = _utc_day(now)
        with self._lock:
            stored_day, spent = self._budget_spend.get(tenant_key, (day, 0.0))
            if stored_day != day:
                spent = 0.0
            self._budget_spend[tenant_key] = (day, spent + amount)

    def get_response_continuation(
        self,
        tenant_key: str,
        response_id: str,
        *,
        now: float | None = None,
    ) -> ResponseContinuation | None:
        """Resolve one Responses continuation without revealing its owner.

        A missing, expired, or cross-tenant identifier is deliberately the
        same ``None`` result.  The HTTP layer maps that to one uniform public
        error, which prevents response-ID enumeration across tenants.
        """

        identifier = str(response_id or "").strip()
        if not identifier:
            return None
        current = float(now if now is not None else time.time())
        with self._lock:
            self._prune_response_continuations_unlocked(current)
            stored = self._response_continuations.get(identifier)
            if stored is None or stored.tenant_key != tenant_key:
                return None
            refreshed = replace(stored, last_accessed_at=current)
            self._response_continuations[identifier] = refreshed
            return _copy_response_continuation(refreshed)

    def store_response_continuation(
        self,
        *,
        tenant_key: str,
        response_id: str,
        history: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        model: str,
        instructions: str,
        tools: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        now: float | None = None,
    ) -> bool:
        """Store a bounded continuation in RAM and return whether it fit.

        A disabled store or an oversized context does not evict unrelated
        sessions.  The caller still receives its response, but that response
        cannot be used as a future ``previous_response_id``.
        """

        identifier = str(response_id or "").strip()
        current = float(now if now is not None else time.time())
        ttl_seconds = _response_session_ttl_seconds()
        max_sessions = _response_session_max_sessions()
        max_context_chars = _response_session_max_context_chars()
        safe_history = _copy_memory_rows(history)
        safe_tools = _copy_memory_rows(tools)
        context_char_count = _response_context_char_count(
            history=safe_history,
            model=model,
            instructions=instructions,
            tools=safe_tools,
        )
        if (
            not identifier
            or not str(tenant_key or "").strip()
            or ttl_seconds <= 0
            or max_sessions <= 0
            or max_context_chars <= 0
            or context_char_count > max_context_chars
        ):
            return False
        entry = ResponseContinuation(
            response_id=identifier,
            tenant_key=str(tenant_key),
            history=safe_history,
            model=str(model or ""),
            instructions=str(instructions or ""),
            tools=safe_tools,
            created_at=current,
            expires_at=current + ttl_seconds,
            last_accessed_at=current,
            context_char_count=context_char_count,
        )
        with self._lock:
            self._prune_response_continuations_unlocked(current)
            # Replacing an existing response ID must not consume an extra
            # slot.  Make room before inserting so an identical timestamp
            # cannot evict the freshly created continuation by ID ordering.
            self._response_continuations.pop(identifier, None)
            while len(self._response_continuations) >= max_sessions:
                oldest = min(
                    self._response_continuations.values(),
                    key=lambda item: (item.last_accessed_at, item.created_at, item.response_id),
                )
                self._response_continuations.pop(oldest.response_id, None)
            self._response_continuations[identifier] = entry
            return True

    def record_feedback(self, payload: Mapping[str, Any], tenant_key: str) -> dict[str, Any]:
        score = _score(payload.get("score") or payload.get("rating"))
        accepted = _optional_bool(payload.get("accepted"))
        verification = payload.get("external_verification") if isinstance(payload.get("external_verification"), Mapping) else {}
        safe_verification = _safe_external_verification(verification)
        agent_outcome = payload.get("agent_outcome") if isinstance(payload.get("agent_outcome"), Mapping) else {}
        safe_agent_outcome = _safe_agent_outcome(agent_outcome)
        route_plan = payload.get("route_plan") if isinstance(payload.get("route_plan"), Mapping) else {}
        trace = payload.get("fusion_trace") if isinstance(payload.get("fusion_trace"), Mapping) else {}
        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
        receipt = {
            "schema": "axio_fusion_api.feedback_receipt.v1",
            "feedback_id": sha256_text(
                json.dumps(
                    {
                        "tenant": tenant_key,
                        "response_id": payload.get("response_id"),
                        "request_fingerprint": payload.get("request_fingerprint"),
                        "score": score,
                        "created": int(time.time() * 1000),
                    },
                    sort_keys=True,
                )
            )[:32],
            "tenant_sha256": sha256_text(tenant_key),
            "response_id": str(payload.get("response_id") or "")[:120],
            "request_fingerprint": str(payload.get("request_fingerprint") or "")[:128],
            "score": score,
            "accepted": accepted,
            "outcome": str(payload.get("outcome") or "")[:80],
            "tag_hashes": [sha256_text(str(tag)) for tag in tags[:12]],
            "notes_sha256": sha256_text(str(payload.get("notes") or payload.get("comment") or "")),
            "route_snapshot": _safe_route_snapshot(route_plan, payload),
            "trace_metrics": _safe_trace_metrics(trace),
            "external_verification": safe_verification,
            "agent_outcome": safe_agent_outcome,
            "training_signal": {
                "eligible_for_router_learning": bool(score is not None or accepted is not None or verification or agent_outcome),
                "external_verification_score": safe_verification.get("score"),
                "external_verification_passed": safe_verification.get("passed"),
                "agent_task_success": safe_agent_outcome.get("task_success"),
                "agent_score": safe_agent_outcome.get("score"),
                "raw_feedback_text_persisted": False,
                "raw_prompt_persisted": False,
                "raw_provider_output_persisted": False,
                "raw_agent_trace_persisted": False,
            },
            "secrets_persisted": False,
        }
        with self._lock:
            self._feedback_count += 1
            key = "none" if score is None else str(score)
            self._feedback_by_score[key] = self._feedback_by_score.get(key, 0) + 1
        _append_feedback_artifact(receipt)
        return receipt

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        rate_limit = _env_int("AXIO_FUSION_RATE_LIMIT_PER_MINUTE")
        daily_budget = _env_float("AXIO_FUSION_TENANT_DAILY_BUDGET_USD")
        with self._lock:
            self._prune_rate_windows_unlocked(current)
            self._prune_budget_spend_unlocked(_utc_day(current))
            self._prune_response_continuations_unlocked(current)
            active_rate_buckets = len(self._rate_windows)
            budget_tenants = len(self._budget_spend)
            feedback_count = self._feedback_count
            feedback_by_score = dict(self._feedback_by_score)
            rate_bucket_rows = _safe_rate_bucket_rows(self._rate_windows, limit=rate_limit)
            budget_rows = _safe_budget_rows(self._budget_spend, daily_budget=daily_budget)
            response_session_count = len(self._response_continuations)
            response_session_tenant_count = len(
                {entry.tenant_key for entry in self._response_continuations.values()}
            )
        return {
            "schema": "axio_fusion_api.runtime_snapshot.v1",
            "active_rate_limit_buckets": active_rate_buckets,
            "budget_tenant_count": budget_tenants,
            "rate_limit_buckets": rate_bucket_rows,
            "budget_tenants": budget_rows,
            "feedback_count": feedback_count,
            "feedback_by_score": feedback_by_score,
            "rate_limit_enabled": bool(rate_limit),
            "tenant_budget_enabled": daily_budget is not None,
            "feedback_artifact_enabled": bool(_feedback_path()),
            "response_continuations": {
                "active_session_count": response_session_count,
                "tenant_count": response_session_tenant_count,
                "ttl_seconds": _response_session_ttl_seconds(),
                "max_session_count": _response_session_max_sessions(),
                "max_context_chars": _response_session_max_context_chars(),
                "storage_scope": "process_memory",
                "durable": False,
                "raw_session_ids_persisted": False,
                "raw_response_context_persisted": False,
                "raw_tool_outputs_persisted": False,
            },
            "raw_prompt_persisted": False,
            "raw_feedback_text_persisted": False,
            "raw_tenant_keys_persisted": False,
            "raw_api_keys_persisted": False,
            "secrets_persisted": False,
        }

    def _prune_rate_windows_unlocked(self, current: float) -> None:
        cutoff = float(current) - 60.0
        pruned = {
            tenant_key: [stamp for stamp in stamps if stamp >= cutoff]
            for tenant_key, stamps in self._rate_windows.items()
        }
        self._rate_windows = {tenant_key: stamps for tenant_key, stamps in pruned.items() if stamps}

    def _prune_budget_spend_unlocked(self, current_day: str) -> None:
        self._budget_spend = {
            tenant_key: (day, spent)
            for tenant_key, (day, spent) in self._budget_spend.items()
            if day == current_day and float(spent or 0.0) > 0.0
        }

    def _prune_response_continuations_unlocked(self, current: float) -> None:
        active = {
            identifier: entry
            for identifier, entry in self._response_continuations.items()
            if entry.expires_at > current
        }
        max_sessions = _response_session_max_sessions()
        if max_sessions <= 0:
            self._response_continuations = {}
            return
        overflow = max(0, len(active) - max_sessions)
        if overflow:
            evicted = sorted(
                active.values(),
                key=lambda entry: (entry.last_accessed_at, entry.created_at, entry.response_id),
            )[:overflow]
            for entry in evicted:
                active.pop(entry.response_id, None)
        self._response_continuations = active


_RUNTIME_STATE = RuntimeState()


def runtime_state() -> RuntimeState:
    return _RUNTIME_STATE


def reset_runtime_state_for_tests() -> None:
    global _RUNTIME_STATE
    _RUNTIME_STATE = RuntimeState()


def tenant_key_from_headers(headers: Mapping[str, str]) -> str:
    bearer = str(headers.get("authorization") or "")
    token = bearer.split(" ", 1)[1].strip() if bearer.lower().startswith("bearer ") else ""
    x_key = str(headers.get("x-api-key") or "").strip()
    operator_key = str(headers.get("x-axio-operator-key") or "").strip()
    tenant = str(headers.get("x-axio-tenant") or "").strip()
    raw = tenant or token or x_key or operator_key or "anonymous"
    return sha256_text(raw)


def _copy_memory_rows(value: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Defensively copy JSON-shaped continuation data before retaining it."""

    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        try:
            copied = copy.deepcopy(dict(item))
        except (TypeError, ValueError):
            continue
        rows.append(copied)
    return tuple(rows)


def _copy_response_continuation(value: ResponseContinuation) -> ResponseContinuation:
    return ResponseContinuation(
        response_id=value.response_id,
        tenant_key=value.tenant_key,
        history=_copy_memory_rows(value.history),
        model=value.model,
        instructions=value.instructions,
        tools=_copy_memory_rows(value.tools),
        created_at=value.created_at,
        expires_at=value.expires_at,
        last_accessed_at=value.last_accessed_at,
        context_char_count=value.context_char_count,
    )


def _response_context_char_count(
    *,
    history: tuple[Mapping[str, Any], ...],
    model: str,
    instructions: str,
    tools: tuple[Mapping[str, Any], ...],
) -> int:
    try:
        serialized = json.dumps(
            {
                "history": list(history),
                "model": str(model or ""),
                "instructions": str(instructions or ""),
                "tools": list(tools),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        return _response_session_max_context_chars() + 1
    return len(serialized)


def _response_session_ttl_seconds() -> int:
    return _bounded_env_int(
        "AXIO_FUSION_RESPONSE_SESSION_TTL_SECONDS",
        default=1_800,
        minimum=1,
        maximum=86_400,
    )


def _response_session_max_sessions() -> int:
    return _bounded_env_int(
        "AXIO_FUSION_RESPONSE_SESSION_MAX_SESSIONS",
        default=1_000,
        minimum=0,
        maximum=100_000,
    )


def _response_session_max_context_chars() -> int:
    return _bounded_env_int(
        "AXIO_FUSION_RESPONSE_SESSION_MAX_CONTEXT_CHARS",
        default=98_304,
        minimum=0,
        maximum=4_194_304,
    )


def _bounded_env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    configured = _env_int(name)
    if configured is None:
        return int(default)
    return max(minimum, min(maximum, int(configured)))


def _safe_rate_bucket_rows(windows: Mapping[str, list[float]], *, limit: int | None) -> list[dict[str, Any]]:
    rows = []
    for tenant_key, stamps in windows.items():
        request_count = len(stamps)
        rows.append(
            {
                "tenant_sha256": sha256_text(tenant_key),
                "request_count_last_minute": request_count,
                "limit": int(limit) if limit else None,
                "remaining": max(0, int(limit) - request_count) if limit else None,
                "raw_tenant_key_persisted": False,
                "raw_api_key_persisted": False,
                "secrets_persisted": False,
            }
        )
    rows.sort(key=lambda row: (-int(row["request_count_last_minute"]), str(row["tenant_sha256"])))
    return rows[:20]


def _safe_budget_rows(spend: Mapping[str, tuple[str, float]], *, daily_budget: float | None) -> list[dict[str, Any]]:
    rows = []
    for tenant_key, (day, amount) in spend.items():
        spent = max(0.0, float(amount or 0.0))
        remaining = None if daily_budget is None or daily_budget <= 0 else max(0.0, float(daily_budget) - spent)
        rows.append(
            {
                "tenant_sha256": sha256_text(tenant_key),
                "day_sha256": sha256_text(day),
                "spent_usd": round(spent, 8),
                "daily_budget_usd": round(float(daily_budget), 8) if daily_budget is not None else None,
                "remaining_usd": round(remaining, 8) if remaining is not None else None,
                "raw_tenant_key_persisted": False,
                "raw_api_key_persisted": False,
                "secrets_persisted": False,
            }
        )
    rows.sort(key=lambda row: (-float(row["spent_usd"]), str(row["tenant_sha256"])))
    return rows[:20]


def _safe_external_verification(value: Mapping[str, Any]) -> dict[str, Any]:
    status = str(value.get("status") or "").strip()[:80]
    score = _score(value.get("score"))
    passed = _verification_passed(status)
    if score is None and passed is not None:
        score = 1.0 if passed else -1.0
    return {
        "status": status,
        "score": score,
        "passed": passed,
        "source_sha256": sha256_text(str(value.get("source") or "")),
        "details_sha256": sha256_text(str(value.get("details") or "")),
        "raw_details_persisted": False,
    }


def _safe_agent_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    if not value:
        return {
            "provided": False,
            "raw_task_text_persisted": False,
            "raw_agent_trace_persisted": False,
            "raw_tool_outputs_persisted": False,
        }
    task_success = _optional_bool(_first_present(value, "task_success", "success", "passed"))
    return {
        "provided": True,
        "source_sha256": sha256_text(str(value.get("source") or value.get("harness") or "")),
        "session_id_sha256": sha256_text(str(value.get("session_id") or value.get("conversation_id") or "")),
        "task_id_sha256": sha256_text(str(value.get("task_id") or value.get("case_id") or value.get("request_id") or "")),
        "run_id_sha256": sha256_text(str(value.get("run_id") or value.get("trace_id") or "")),
        "loop_id_sha256": sha256_text(str(value.get("loop_id") or value.get("episode_id") or "")),
        "case_hashes": _sha256_values_from_fields(
            value,
            "case_hash",
            "case_hashes",
            "benchmark_case_hash",
            "benchmark_case_hashes",
            "case_id_sha256",
            "input_sha256",
            "question_sha256",
            "reference_sha256",
        ),
        "final_status": str(value.get("final_status") or value.get("status") or "")[:80],
        "task_success": task_success,
        "score": _score(value.get("score") if value.get("score") is not None else value.get("reward")),
        "completed_step_count": _positive_int(value.get("completed_step_count") or value.get("completed_steps")),
        "failed_step_count": _positive_int(value.get("failed_step_count") or value.get("failed_steps")),
        "tool_call_count": _positive_int(value.get("tool_call_count") or value.get("tool_calls")),
        "tool_failure_count": _positive_int(value.get("tool_failure_count") or value.get("tool_failures")),
        "repair_loop_count": _positive_int(value.get("repair_loop_count") or value.get("repair_loops")),
        "human_intervention_required": _optional_bool(
            _first_present(value, "human_intervention_required", "intervention_required")
        ),
        "duration_ms": _positive_float(value.get("duration_ms") or value.get("latency_ms")),
        "cost_usd": _positive_float(value.get("cost_usd") or value.get("estimated_cost_usd")),
        "failure_reason_hashes": [
            sha256_text(str(item))
            for item in (value.get("failure_reasons") if isinstance(value.get("failure_reasons"), list) else [])
            if str(item).strip()
        ][:12],
        "raw_task_text_persisted": False,
        "raw_agent_trace_persisted": False,
        "raw_tool_outputs_persisted": False,
    }


def _first_present(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value:
            return value.get(key)
    return None


def _sha256_values_from_fields(value: Mapping[str, Any], *keys: str) -> list[str]:
    result: list[str] = []
    for key in keys:
        raw = value.get(key)
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            text = str(item or "").strip().lower()
            if _looks_like_sha256(text) and text not in result:
                result.append(text)
            if len(result) >= 24:
                return result
    return result


def _looks_like_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _verification_passed(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in {"pass", "passed", "success", "succeeded", "verified", "ok", "correct", "accepted"}:
        return True
    if normalized in {"fail", "failed", "failure", "error", "incorrect", "rejected", "regression", "timeout"}:
        return False
    return None


def _safe_route_snapshot(route_plan: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    analysis = route_plan.get("request_analysis") if isinstance(route_plan.get("request_analysis"), Mapping) else {}
    selected = route_plan.get("selected_models") if isinstance(route_plan.get("selected_models"), list) else []
    routing_policy = (
        route_plan.get("routing_policy")
        if isinstance(route_plan.get("routing_policy"), Mapping)
        else {}
    )
    return {
        "public_model": str(payload.get("public_model") or route_plan.get("public_model") or "")[:80],
        "strategy": str(payload.get("strategy") or route_plan.get("strategy") or "")[:120],
        "task_type": str(payload.get("task_type") or analysis.get("task_type") or "")[:120],
        "privacy_level": str(analysis.get("privacy_level") or "")[:80],
        "complexity": _score01(analysis.get("complexity")),
        "risk": _score01(analysis.get("risk")),
        "uncertainty": _score01(analysis.get("uncertainty")),
        "selected_profile_hashes": [
            sha256_text(str(row.get("profile_id") or ""))
            for row in selected[:16]
            if isinstance(row, Mapping)
        ],
        "routing_policy": _safe_routing_policy_snapshot(routing_policy),
        "raw_prompt_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_routing_policy_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep feedback learning attributable to a policy version, not its text.

    Policy bundles are operator artifacts.  Feedback only needs enough data to
    bucket operational outcomes and reconstruct a bounded shadow decision, so
    it retains hashes, counters, and allowlisted controls rather than a local
    path, provider selection, or prompt content.
    """

    directives = value.get("context_directives") if isinstance(value.get("context_directives"), list) else []
    reason_codes = value.get("reason_codes") if isinstance(value.get("reason_codes"), list) else []
    bundle_digest = str(value.get("bundle_digest_sha256") or "").strip().lower()
    policy_id = str(value.get("policy_id_sha256") or "").strip().lower()
    if not _looks_like_sha256(bundle_digest):
        bundle_digest = ""
    if not _looks_like_sha256(policy_id):
        policy_id = ""
    rule_hashes = []
    for item in value.get("matched_rule_id_hashes", []):
        text = str(item or "").strip().lower()
        if _looks_like_sha256(text) and text not in rule_hashes:
            rule_hashes.append(text)
        if len(rule_hashes) >= 24:
            break
    allowed_directives = {
        "evidence_first",
        "independent_solution",
        "verify_assumptions",
        "tool_schema_strict",
        "uncertainty_calibration",
        "concise_synthesis",
    }
    return {
        "schema": "axio_fusion_api.routing_policy_application.v1",
        "active": value.get("active") is True,
        "applied": value.get("applied") is True,
        "policy_id_sha256": policy_id,
        "bundle_digest_sha256": bundle_digest,
        "policy_version_sha256": bundle_digest or policy_id,
        "matched_rule_count": _positive_int(value.get("matched_rule_count")) or 0,
        "matched_rule_id_hashes": rule_hashes,
        "quality_target_floor": _score01(value.get("quality_target_floor")),
        "force_fusion": value.get("force_fusion") is True,
        "fast_light_verify": value.get("fast_light_verify") is True,
        "max_panel_models": _positive_int(value.get("max_panel_models")),
        "max_fusion_depth": _positive_int(value.get("max_fusion_depth")),
        "context_directive_count": len(
            [item for item in directives if str(item) in allowed_directives]
        ),
        "context_directives": [
            str(item)
            for item in directives
            if str(item) in allowed_directives
        ][:8],
        "reason_codes": [
            str(item)[:120]
            for item in reason_codes
            if str(item)
        ][:12],
        "raw_policy_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _safe_trace_metrics(trace: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "actual_cost_usd": _positive_float(trace.get("actual_cost_usd")),
        "latency_ms": _positive_float(trace.get("latency_ms")),
        "provider_call_count": _positive_int(trace.get("provider_call_count")),
        "cache_hit": bool(trace.get("cache_hit")),
        "raw_candidate_text_persisted": False,
        "raw_provider_output_persisted": False,
    }


def _append_feedback_artifact(receipt: Mapping[str, Any]) -> None:
    path = _feedback_path()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")


def _feedback_path() -> Path | None:
    explicit = os.getenv("AXIO_FUSION_FEEDBACK_LOG", "").strip()
    if explicit:
        return Path(explicit)
    artifact_dir = os.getenv("AXIO_FUSION_ARTIFACT_DIR", "").strip()
    if artifact_dir:
        return Path(artifact_dir) / "feedback.jsonl"
    return None


def _env_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _env_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _utc_day(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now if now is not None else time.time()))


def _score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(-1.0, min(1.0, number))


def _score01(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "accepted"}:
        return True
    if text in {"0", "false", "no", "rejected"}:
        return False
    return None
