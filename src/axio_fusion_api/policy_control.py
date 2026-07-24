from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from .schemas import ModelProfile, PUBLIC_MODELS, sha256_text, stable_json


ROUTING_POLICY_CANDIDATE_SCHEMA = "axio_fusion_api.routing_policy_candidate.v1"
ROUTING_POLICY_REVIEW_SCHEMA = "axio_fusion_api.routing_policy_review.v1"
ROUTING_POLICY_BUNDLE_SCHEMA = "axio_fusion_api.routing_policy_bundle.v1"
ROUTING_POLICY_SHADOW_REPLAY_SCHEMA = "axio_fusion_api.routing_policy_shadow_replay.v1"
ROUTING_POLICY_MAX_RULES = 24
ROUTING_POLICY_ALLOWED_CONTEXT_DIRECTIVES = frozenset(
    {
        "evidence_first",
        "independent_solution",
        "verify_assumptions",
        "tool_schema_strict",
        "uncertainty_calibration",
        "concise_synthesis",
    }
)


def build_routing_policy_candidate(
    shadow_patch: Mapping[str, Any] | None,
    *,
    profiles: Sequence[ModelProfile],
    min_examples: int = 20,
    created_on: str | None = None,
) -> dict[str, Any]:
    """Compile a shadow-only learning artifact into a reviewable policy draft.

    The compiler intentionally accepts only bounded routing controls and static
    context-playbook labels. It cannot emit raw provider selection, arbitrary
    prompt text, budget overrides, or an active production policy.
    """

    shadow_patch = shadow_patch if isinstance(shadow_patch, Mapping) else {}
    min_examples = max(1, int(min_examples))
    blockers = _shadow_patch_validation_errors(shadow_patch)
    registry_profile_set_sha256 = _profile_set_sha256(profiles)
    source_digest = sha256_text(stable_json(_shadow_patch_digest_input(shadow_patch)))
    rules: list[dict[str, Any]] = []
    patch_rows = (
        shadow_patch.get("patch_candidates")
        if isinstance(shadow_patch.get("patch_candidates"), list)
        else []
    )
    for patch in patch_rows:
        rule = _policy_rule_from_shadow_patch(
            patch,
            min_examples=min_examples,
        )
        if rule is not None:
            rules.append(rule)
    rules = _dedupe_rules(rules)[:ROUTING_POLICY_MAX_RULES]
    if not rules:
        blockers.append("routing_policy_candidate_has_no_eligible_rules")
    created_on = str(created_on or date.today().isoformat())
    if not _valid_iso_date(created_on):
        blockers.append("routing_policy_candidate_created_on_invalid")
        created_on = ""
    candidate = {
        "schema": ROUTING_POLICY_CANDIDATE_SCHEMA,
        "status": "draft",
        "created_on": created_on,
        "registry_profile_set_sha256": registry_profile_set_sha256,
        "source_shadow_patch_digest_sha256": source_digest,
        "source_shadow_patch_schema": str(shadow_patch.get("schema") or ""),
        "source_shadow_patch_shadow_only": shadow_patch.get("shadow_only") is True,
        "minimum_examples_per_rule": min_examples,
        "rule_count": len(rules),
        "rules": rules,
        "ready_for_review": not blockers,
        "blockers": sorted(set(blockers)),
        "application_contract": {
            "shadow_only_source_required": True,
            "human_approval_required": True,
            "contamination_audit_required": True,
            "registry_binding_required": True,
            "automatic_activation_allowed": False,
            "target_benchmark_results_used": False,
            "target_benchmark_labels_used": False,
            "allows_raw_provider_selection": False,
            "allows_arbitrary_prompt_text": False,
            "allows_hard_budget_guard_override": False,
        },
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    candidate["candidate_digest_sha256"] = sha256_text(
        stable_json(_candidate_digest_input(candidate))
    )
    return candidate


def review_routing_policy_candidate(
    candidate: Mapping[str, Any] | None,
    *,
    profiles: Sequence[ModelProfile],
    contamination_audit: Mapping[str, Any] | None,
    approved: bool,
    reviewer_id: str = "",
    reviewed_on: str | None = None,
) -> dict[str, Any]:
    """Produce an immutable approval record without exposing reviewer text."""

    candidate = candidate if isinstance(candidate, Mapping) else {}
    contamination_audit = (
        contamination_audit if isinstance(contamination_audit, Mapping) else {}
    )
    reviewed_on = str(reviewed_on or date.today().isoformat())
    errors = _candidate_validation_errors(candidate, profiles=profiles)
    contamination = _contamination_receipt(contamination_audit)
    if not contamination["clean"]:
        errors.append("routing_policy_contamination_audit_not_clean")
    if not _valid_iso_date(reviewed_on):
        errors.append("routing_policy_reviewed_on_invalid")
        reviewed_on = ""
    if approved is not True:
        errors.append("routing_policy_human_approval_missing")
    review = {
        "schema": ROUTING_POLICY_REVIEW_SCHEMA,
        "candidate_digest_sha256": str(candidate.get("candidate_digest_sha256") or ""),
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "reviewed_on": reviewed_on,
        "approved": approved is True,
        "reviewer_id_sha256": sha256_text(str(reviewer_id or ""))
        if str(reviewer_id or "")
        else "",
        "contamination_audit": contamination,
        "ready_for_activation": not errors,
        "blockers": sorted(set(errors)),
        "raw_reviewer_id_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }
    review["review_digest_sha256"] = sha256_text(stable_json(_review_digest_input(review)))
    return review


def activate_routing_policy(
    candidate: Mapping[str, Any] | None,
    review: Mapping[str, Any] | None,
    *,
    profiles: Sequence[ModelProfile],
    rollback_policy_digest_sha256: str = "",
    activated_on: str | None = None,
) -> dict[str, Any]:
    """Create a registry-bound active policy bundle after a successful review."""

    candidate = candidate if isinstance(candidate, Mapping) else {}
    review = review if isinstance(review, Mapping) else {}
    activated_on = str(activated_on or date.today().isoformat())
    errors = _candidate_validation_errors(candidate, profiles=profiles)
    errors.extend(_review_validation_errors(review, candidate=candidate, profiles=profiles))
    if not _valid_iso_date(activated_on):
        errors.append("routing_policy_activated_on_invalid")
        activated_on = ""
    rollback_policy_digest_sha256 = str(rollback_policy_digest_sha256 or "")
    if rollback_policy_digest_sha256 and not _looks_like_sha256(
        rollback_policy_digest_sha256
    ):
        errors.append("routing_policy_rollback_digest_invalid")
        rollback_policy_digest_sha256 = ""
    bundle = {
        "schema": ROUTING_POLICY_BUNDLE_SCHEMA,
        "status": "active" if not errors else "blocked",
        "activated_on": activated_on,
        "policy_id_sha256": str(candidate.get("candidate_digest_sha256") or ""),
        "policy_candidate_digest_sha256": str(
            candidate.get("candidate_digest_sha256") or ""
        ),
        "policy_review_digest_sha256": str(review.get("review_digest_sha256") or ""),
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "source_shadow_patch_digest_sha256": str(
            candidate.get("source_shadow_patch_digest_sha256") or ""
        ),
        "rollback_policy_digest_sha256": rollback_policy_digest_sha256,
        "rule_count": _safe_int(candidate.get("rule_count")),
        "rules": _safe_rules(candidate.get("rules")),
        "activation_ready": not errors,
        "blockers": sorted(set(errors)),
        "application_contract": {
            "active_rules_require_registry_profile_set_match": True,
            "caller_budget_and_privacy_limits_remain_hard": True,
            "fusion_latency_guard_remains_hard": True,
            "target_benchmark_results_used": False,
            "target_benchmark_labels_used": False,
            "automatic_rule_promotion": False,
            "rollback_supported": True,
        },
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    bundle["bundle_digest_sha256"] = sha256_text(stable_json(_bundle_digest_input(bundle)))
    return bundle


def load_active_routing_policy(
    profiles: Sequence[ModelProfile],
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Load an operator policy bundle or return a safe disabled projection."""

    configured_path = str(
        path if path is not None else os.getenv("AXIO_FUSION_ROUTING_POLICY_PATH", "")
    ).strip()
    if not configured_path:
        return _disabled_policy("routing_policy_not_configured")
    selected = Path(configured_path)
    if not selected.exists() or not selected.is_file():
        return _disabled_policy("routing_policy_not_found", path=selected)
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _disabled_policy("routing_policy_invalid_json", path=selected)
    if not isinstance(payload, Mapping):
        return _disabled_policy("routing_policy_not_object", path=selected)
    errors = _bundle_validation_errors(payload, profiles=profiles)
    if errors:
        return _disabled_policy(
            *errors,
            path=selected,
            bundle_digest_sha256=str(payload.get("bundle_digest_sha256") or ""),
        )
    return {
        "schema": ROUTING_POLICY_BUNDLE_SCHEMA,
        "active": True,
        "policy_id_sha256": str(payload.get("policy_id_sha256") or ""),
        "bundle_digest_sha256": str(payload.get("bundle_digest_sha256") or ""),
        "registry_profile_set_sha256": str(
            payload.get("registry_profile_set_sha256") or ""
        ),
        "rules": _safe_rules(payload.get("rules")),
        "rule_count": _safe_int(payload.get("rule_count")),
        "load_path_sha256": sha256_text(str(selected)),
        "reason_codes": [],
        "raw_local_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def resolve_routing_policy(
    policy: Mapping[str, Any] | None,
    *,
    public_model: str,
    task_type: str,
    risk: float,
) -> dict[str, Any]:
    """Resolve matching active rules into a safe, bounded route application."""

    policy = policy if isinstance(policy, Mapping) else {}
    if policy.get("active") is not True:
        return _empty_policy_application(policy, "routing_policy_inactive")
    public_model = str(public_model or "").strip().lower()
    task_type = _safe_label(task_type, default="unknown")
    risk = max(0.0, min(1.0, _safe_float(risk)))
    matched_rule_ids: list[str] = []
    quality_target_floor: float | None = None
    force_fusion = False
    fast_light_verify = False
    max_panel_models: int | None = None
    max_fusion_depth: int | None = None
    directives: list[str] = []
    for rule in _safe_rules(policy.get("rules")):
        match = rule.get("match") if isinstance(rule.get("match"), Mapping) else {}
        if not _rule_matches(
            match,
            public_model=public_model,
            task_type=task_type,
            risk=risk,
        ):
            continue
        matched_rule_ids.append(str(rule.get("rule_id_sha256") or ""))
        controls = rule.get("controls") if isinstance(rule.get("controls"), Mapping) else {}
        floor = _safe_optional_float(controls.get("quality_target_floor"))
        if floor is not None:
            quality_target_floor = max(quality_target_floor or 0.0, floor)
        force_fusion = force_fusion or controls.get("force_fusion") is True
        fast_light_verify = fast_light_verify or controls.get("fast_light_verify") is True
        panel_cap = _safe_optional_int(controls.get("max_panel_models"))
        if panel_cap is not None:
            max_panel_models = (
                panel_cap
                if max_panel_models is None
                else min(max_panel_models, panel_cap)
            )
        depth_cap = _safe_optional_int(controls.get("max_fusion_depth"))
        if depth_cap is not None:
            max_fusion_depth = (
                depth_cap
                if max_fusion_depth is None
                else min(max_fusion_depth, depth_cap)
            )
        directives.extend(
            directive
            for directive in controls.get("context_directives", [])
            if directive in ROUTING_POLICY_ALLOWED_CONTEXT_DIRECTIVES
        )
    if not matched_rule_ids:
        return _empty_policy_application(policy, "routing_policy_no_matching_rule")
    return {
        "schema": "axio_fusion_api.routing_policy_application.v1",
        "active": True,
        "applied": True,
        "policy_id_sha256": str(policy.get("policy_id_sha256") or ""),
        "bundle_digest_sha256": str(policy.get("bundle_digest_sha256") or ""),
        "matched_rule_count": len(matched_rule_ids),
        "matched_rule_id_hashes": sorted(set(matched_rule_ids)),
        "quality_target_floor": quality_target_floor,
        "force_fusion": force_fusion,
        "fast_light_verify": fast_light_verify,
        "max_panel_models": max_panel_models,
        "max_fusion_depth": max_fusion_depth,
        "context_directives": list(dict.fromkeys(directives)),
        "reason_codes": [],
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def build_routing_policy_shadow_replay(
    candidate: Mapping[str, Any] | None,
    *,
    trace_paths: Sequence[str | Path] = (),
    feedback_paths: Sequence[str | Path] = (),
    max_cases: int = 500,
) -> dict[str, Any]:
    """Replay bounded candidate-policy decisions over prompt-free traces.

    This is deliberately a decision replay, not a counterfactual model-quality
    evaluation.  It can establish which historical route classes a candidate
    would affect and whether those classes already encountered hard budget
    guards.  It cannot infer a new answer, latency, cost, or quality score
    without a separately executed paired shadow experiment.
    """

    candidate = candidate if isinstance(candidate, Mapping) else {}
    max_cases = max(1, min(5_000, int(max_cases)))
    blockers = _replay_candidate_validation_errors(candidate)
    candidate_digest = str(candidate.get("candidate_digest_sha256") or "")
    safe_rules = _safe_rules(candidate.get("rules"))
    candidate_policy = {
        "active": not blockers,
        "policy_id_sha256": candidate_digest if _looks_like_sha256(candidate_digest) else "",
        "bundle_digest_sha256": candidate_digest if _looks_like_sha256(candidate_digest) else "",
        "rules": safe_rules,
    }
    trace_rows = _load_jsonl_objects(trace_paths)
    feedback_rows = _load_jsonl_objects(feedback_paths)
    feedback_index = _replay_feedback_index(feedback_rows)
    receipts: list[dict[str, Any]] = []
    summary = _empty_replay_summary()
    for trace in trace_rows[:max_cases]:
        receipt = _replay_trace_decision(
            trace,
            candidate_policy=candidate_policy,
            feedback_index=feedback_index,
        )
        if receipt is None:
            summary["skipped_trace_count"] += 1
            continue
        receipts.append(receipt)
        _accumulate_replay_summary(summary, receipt)
    if not trace_rows:
        blockers.append("routing_policy_shadow_replay_no_trace_rows")
    if len(trace_rows) > max_cases:
        blockers.append("routing_policy_shadow_replay_case_limit_reached")
    if not candidate_digest or not _looks_like_sha256(candidate_digest):
        blockers.append("routing_policy_shadow_replay_candidate_digest_invalid")
    blockers = sorted(set(blockers))
    quality = _replay_quality_evidence(receipts)
    decision_ready = bool(receipts) and not any(
        blocker
        for blocker in blockers
        if blocker
        not in {"routing_policy_shadow_replay_case_limit_reached"}
    )
    replay_digest = sha256_text(
        stable_json(
            {
                "candidate_digest_sha256": candidate_digest
                if _looks_like_sha256(candidate_digest)
                else "",
                "trace_receipt_hashes": [
                    str(row.get("case_receipt_sha256") or "")
                    for row in receipts
                ],
                "feedback_observation_count": quality["historical_feedback_count"],
                "max_cases": max_cases,
            }
        )
    )
    return {
        "schema": ROUTING_POLICY_SHADOW_REPLAY_SCHEMA,
        "status": "decision_replay_ready" if decision_ready else "blocked",
        "candidate_policy_version_sha256": candidate_digest
        if _looks_like_sha256(candidate_digest)
        else "",
        "candidate_rule_count": len(safe_rules),
        "candidate_ready_for_review": candidate.get("ready_for_review") is True,
        "replay_digest_sha256": replay_digest,
        "input_artifacts": {
            "trace_file_count": len(trace_paths),
            "feedback_file_count": len(feedback_paths),
            "trace_path_hashes": [sha256_text(str(path)) for path in trace_paths],
            "feedback_path_hashes": [sha256_text(str(path)) for path in feedback_paths],
            "trace_row_count": len(trace_rows),
            "feedback_row_count": len(feedback_rows),
            "max_case_count": max_cases,
            "raw_artifact_paths_persisted": False,
        },
        "decision_summary": summary,
        "quality_evidence": quality,
        "case_receipt_count": len(receipts),
        "case_receipts": receipts,
        "promotion_gate": {
            "eligible": False,
            "requires_human_review": True,
            "requires_clean_contamination_audit": True,
            "requires_registry_binding": True,
            "requires_paired_candidate_execution": True,
            "requires_independent_quality_or_verification_evidence": True,
            "decision_replay_alone_is_sufficient": False,
            "reason_codes": [
                "routing_policy_shadow_replay_is_not_counterfactual_quality_evidence",
                "routing_policy_shadow_replay_does_not_execute_candidate_model_calls",
            ],
        },
        "blockers": blockers,
        "application_contract": {
            "shadow_only": True,
            "candidate_policy_executed": False,
            "provider_calls_performed": False,
            "historical_quality_not_attributed_to_candidate": True,
            "historical_latency_not_attributed_to_candidate": True,
            "historical_cost_not_attributed_to_candidate": True,
            "not_for_final_benchmark_claims": True,
            "no_automatic_policy_activation": True,
            "raw_prompts_persisted": False,
            "raw_feedback_text_persisted": False,
            "raw_provider_outputs_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _replay_candidate_validation_errors(candidate: Mapping[str, Any]) -> list[str]:
    errors = []
    if str(candidate.get("schema") or "") != ROUTING_POLICY_CANDIDATE_SCHEMA:
        errors.append("routing_policy_shadow_replay_candidate_schema_unrecognized")
    digest = str(candidate.get("candidate_digest_sha256") or "")
    if not _looks_like_sha256(digest) or digest != sha256_text(
        stable_json(_candidate_digest_input(candidate))
    ):
        errors.append("routing_policy_shadow_replay_candidate_digest_mismatch")
    if candidate.get("status") != "draft" or candidate.get("ready_for_review") is not True:
        errors.append("routing_policy_shadow_replay_candidate_not_review_ready")
    rules = _safe_rules(candidate.get("rules"))
    if not rules or len(rules) != _safe_int(candidate.get("rule_count")):
        errors.append("routing_policy_shadow_replay_candidate_rules_invalid")
    if _contains_forbidden_raw_fields(candidate):
        errors.append("routing_policy_shadow_replay_candidate_contains_raw_private_fields")
    return sorted(set(errors))


def _load_jsonl_objects(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        selected = Path(path)
        if not selected.exists() or not selected.is_file():
            continue
        try:
            lines = selected.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, Mapping):
                rows.append(dict(payload))
    return rows


def _replay_feedback_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        response_id = str(row.get("response_id") or "")
        fingerprint = str(row.get("request_fingerprint") or "")
        for key in (response_id, fingerprint):
            if key:
                index[key] = row
    return index


def _replay_trace_decision(
    trace: Mapping[str, Any],
    *,
    candidate_policy: Mapping[str, Any],
    feedback_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    routing = (
        trace.get("routing_decision")
        if isinstance(trace.get("routing_decision"), Mapping)
        else {}
    )
    analysis = (
        trace.get("request_analysis")
        if isinstance(trace.get("request_analysis"), Mapping)
        else {}
    )
    public_model = str(routing.get("public_model") or "").strip().lower()
    if public_model not in PUBLIC_MODELS:
        return None
    task_type = _safe_label(analysis.get("task_type"), default="unknown")
    risk = max(0.0, min(1.0, _safe_float(analysis.get("risk"))))
    historical = _safe_replay_policy_application(
        trace.get("routing_policy")
        if isinstance(trace.get("routing_policy"), Mapping)
        else {}
    )
    candidate = _safe_replay_policy_application(
        resolve_routing_policy(
            candidate_policy,
            public_model=public_model,
            task_type=task_type,
            risk=risk,
        )
    )
    join_key = trace.get("feedback_join_key") if isinstance(trace.get("feedback_join_key"), Mapping) else {}
    response_id = str(join_key.get("response_id") or trace.get("response_id") or "")
    fingerprint = str(join_key.get("request_fingerprint") or "")
    feedback = feedback_index.get(response_id) or feedback_index.get(fingerprint) or {}
    fusion = trace.get("fusion_admission") if isinstance(trace.get("fusion_admission"), Mapping) else {}
    guards = trace.get("runtime_guards") if isinstance(trace.get("runtime_guards"), Mapping) else {}
    cost = trace.get("cost") if isinstance(trace.get("cost"), Mapping) else {}
    case_receipt = {
        "public_model": public_model,
        "task_type": task_type,
        "risk": round(risk, 6),
        "historical_policy": historical,
        "candidate_policy": candidate,
        "decision_delta": _replay_decision_delta(historical, candidate),
        "historical_execution": {
            "fusion_activated": fusion.get("activated") is True,
            "initial_resource_budget_blocked": guards.get(
                "initial_fusion_resource_budget_blocked"
            )
            is True,
            "max_total_model_calls": _safe_optional_int(
                guards.get("max_total_model_calls")
            ),
            "max_latency_ms": _safe_optional_int(guards.get("max_latency_ms")),
            "actual_provider_call_count": _safe_optional_int(
                cost.get("provider_call_count")
            ),
            "actual_latency_ms": _safe_nonnegative_float(trace.get("latency_ms")),
            "actual_cost_usd": _safe_nonnegative_float(
                cost.get("actual_cost_usd")
            ),
            "counterfactual_execution_recomputed": False,
        },
        "historical_feedback": _safe_replay_feedback(feedback),
        "candidate_quality_observed": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }
    case_receipt["case_receipt_sha256"] = sha256_text(
        stable_json(
            {
                "response_id_sha256": sha256_text(response_id),
                "request_fingerprint_sha256": sha256_text(fingerprint),
                "candidate_policy_version_sha256": candidate["policy_version_sha256"],
                "historical_policy_version_sha256": historical["policy_version_sha256"],
                "decision_delta": case_receipt["decision_delta"],
            }
        )
    )
    return case_receipt


def _safe_replay_policy_application(value: Mapping[str, Any]) -> dict[str, Any]:
    policy_id = str(value.get("policy_id_sha256") or "").strip().lower()
    bundle_digest = str(value.get("bundle_digest_sha256") or "").strip().lower()
    if not _looks_like_sha256(policy_id):
        policy_id = ""
    if not _looks_like_sha256(bundle_digest):
        bundle_digest = ""
    directives = value.get("context_directives") if isinstance(value.get("context_directives"), list) else []
    safe_directives = [
        str(item)
        for item in directives
        if str(item) in ROUTING_POLICY_ALLOWED_CONTEXT_DIRECTIVES
    ][:8]
    return {
        "active": value.get("active") is True,
        "applied": value.get("applied") is True,
        "policy_version_sha256": bundle_digest or policy_id,
        "matched_rule_count": max(0, _safe_optional_int(value.get("matched_rule_count")) or 0),
        "matched_rule_id_hashes": [
            str(item).strip().lower()
            for item in value.get("matched_rule_id_hashes", [])
            if _looks_like_sha256(str(item).strip().lower())
        ][:ROUTING_POLICY_MAX_RULES]
        if isinstance(value.get("matched_rule_id_hashes"), list)
        else [],
        "quality_target_floor": _safe_optional_float(
            value.get("quality_target_floor")
        ),
        "force_fusion": value.get("force_fusion") is True,
        "fast_light_verify": value.get("fast_light_verify") is True,
        "max_panel_models": _safe_optional_int(value.get("max_panel_models")),
        "max_fusion_depth": _safe_optional_int(value.get("max_fusion_depth")),
        "context_directive_count": len(safe_directives),
        "raw_policy_path_persisted": False,
    }


def _replay_decision_delta(
    historical: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    historical_floor = _safe_optional_float(historical.get("quality_target_floor"))
    candidate_floor = _safe_optional_float(candidate.get("quality_target_floor"))
    return {
        "candidate_rule_match_changed": (
            historical.get("matched_rule_id_hashes")
            != candidate.get("matched_rule_id_hashes")
        ),
        "policy_application_changed": historical.get("applied") is not candidate.get("applied"),
        "quality_target_floor_delta": _replay_optional_delta(
            historical_floor, candidate_floor
        ),
        "force_fusion_newly_requested": (
            candidate.get("force_fusion") is True
            and historical.get("force_fusion") is not True
        ),
        "fast_light_verify_newly_requested": (
            candidate.get("fast_light_verify") is True
            and historical.get("fast_light_verify") is not True
        ),
        "max_panel_models_delta": _replay_optional_int_delta(
            historical.get("max_panel_models"), candidate.get("max_panel_models")
        ),
        "max_fusion_depth_delta": _replay_optional_int_delta(
            historical.get("max_fusion_depth"), candidate.get("max_fusion_depth")
        ),
        "context_directive_count_delta": (
            (_safe_optional_int(candidate.get("context_directive_count")) or 0)
            - (_safe_optional_int(historical.get("context_directive_count")) or 0)
        ),
        "counterfactual_route_plan_recomputed": False,
        "counterfactual_model_output_generated": False,
    }


def _replay_optional_delta(
    historical: float | None, candidate: float | None
) -> float | None:
    if historical is None or candidate is None:
        return None
    return round(candidate - historical, 6)


def _replay_optional_int_delta(historical: Any, candidate: Any) -> int | None:
    left = _safe_optional_int(historical)
    right = _safe_optional_int(candidate)
    if left is None or right is None:
        return None
    return right - left


def _safe_replay_feedback(value: Mapping[str, Any]) -> dict[str, Any]:
    verification = (
        value.get("external_verification")
        if isinstance(value.get("external_verification"), Mapping)
        else {}
    )
    return {
        "joined": bool(value),
        "score": _safe_feedback_score(value.get("score")),
        "accepted": value.get("accepted") if isinstance(value.get("accepted"), bool) else None,
        "external_verification_score": _safe_feedback_score(verification.get("score")),
        "external_verification_passed": verification.get("passed")
        if isinstance(verification.get("passed"), bool)
        else None,
        "raw_feedback_text_persisted": False,
    }


def _safe_feedback_score(value: Any) -> float | None:
    parsed = _safe_optional_float(value)
    if parsed is None:
        return None
    return round(max(-1.0, min(1.0, parsed)), 6)


def _empty_replay_summary() -> dict[str, Any]:
    return {
        "replayed_case_count": 0,
        "skipped_trace_count": 0,
        "historical_policy_active_count": 0,
        "historical_policy_applied_count": 0,
        "candidate_policy_applied_count": 0,
        "policy_application_changed_count": 0,
        "candidate_force_fusion_newly_requested_count": 0,
        "candidate_fast_light_verify_newly_requested_count": 0,
        "historical_fusion_activated_count": 0,
        "historical_resource_budget_blocked_count": 0,
        "candidate_changed_under_existing_call_cap_count": 0,
        "candidate_changed_under_existing_latency_cap_count": 0,
        "candidate_changed_under_existing_cost_observation_count": 0,
    }


def _accumulate_replay_summary(summary: dict[str, Any], receipt: Mapping[str, Any]) -> None:
    historical = receipt.get("historical_policy") if isinstance(receipt.get("historical_policy"), Mapping) else {}
    candidate = receipt.get("candidate_policy") if isinstance(receipt.get("candidate_policy"), Mapping) else {}
    delta = receipt.get("decision_delta") if isinstance(receipt.get("decision_delta"), Mapping) else {}
    execution = receipt.get("historical_execution") if isinstance(receipt.get("historical_execution"), Mapping) else {}
    summary["replayed_case_count"] += 1
    if historical.get("active") is True:
        summary["historical_policy_active_count"] += 1
    if historical.get("applied") is True:
        summary["historical_policy_applied_count"] += 1
    if candidate.get("applied") is True:
        summary["candidate_policy_applied_count"] += 1
    if delta.get("policy_application_changed") is True or delta.get("candidate_rule_match_changed") is True:
        summary["policy_application_changed_count"] += 1
    if delta.get("force_fusion_newly_requested") is True:
        summary["candidate_force_fusion_newly_requested_count"] += 1
    if delta.get("fast_light_verify_newly_requested") is True:
        summary["candidate_fast_light_verify_newly_requested_count"] += 1
    if execution.get("fusion_activated") is True:
        summary["historical_fusion_activated_count"] += 1
    if execution.get("initial_resource_budget_blocked") is True:
        summary["historical_resource_budget_blocked_count"] += 1
    changed = delta.get("policy_application_changed") is True or delta.get("candidate_rule_match_changed") is True
    if changed and _safe_optional_int(execution.get("max_total_model_calls")) is not None:
        summary["candidate_changed_under_existing_call_cap_count"] += 1
    if changed and _safe_optional_int(execution.get("max_latency_ms")) is not None:
        summary["candidate_changed_under_existing_latency_cap_count"] += 1
    if changed and _safe_nonnegative_float(execution.get("actual_cost_usd")) is not None:
        summary["candidate_changed_under_existing_cost_observation_count"] += 1


def _replay_quality_evidence(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scores = []
    accepted = []
    verification_scores = []
    verification_passed = []
    joined = 0
    for receipt in receipts:
        feedback = receipt.get("historical_feedback") if isinstance(receipt.get("historical_feedback"), Mapping) else {}
        if feedback.get("joined") is not True:
            continue
        joined += 1
        score = _safe_feedback_score(feedback.get("score"))
        if score is not None:
            scores.append(score)
        if isinstance(feedback.get("accepted"), bool):
            accepted.append(bool(feedback.get("accepted")))
        verification_score = _safe_feedback_score(feedback.get("external_verification_score"))
        if verification_score is not None:
            verification_scores.append(verification_score)
        if isinstance(feedback.get("external_verification_passed"), bool):
            verification_passed.append(bool(feedback.get("external_verification_passed")))
    return {
        "historical_feedback_count": joined,
        "historical_average_score": None
        if not scores
        else round(sum(scores) / len(scores), 6),
        "historical_accepted_rate": None
        if not accepted
        else round(sum(1 for value in accepted if value) / len(accepted), 6),
        "historical_average_external_verification_score": None
        if not verification_scores
        else round(sum(verification_scores) / len(verification_scores), 6),
        "historical_external_verification_pass_rate": None
        if not verification_passed
        else round(
            sum(1 for value in verification_passed if value)
            / len(verification_passed),
            6,
        ),
        "candidate_counterfactual_output_count": 0,
        "paired_case_count": 0,
        "quality_comparison_available": False,
        "historical_observations_are_candidate_quality_evidence": False,
        "reason_codes": [
            "candidate_policy_not_executed_in_decision_replay",
            "paired_candidate_outputs_and_independent_verification_required",
        ],
        "raw_feedback_text_persisted": False,
        "raw_provider_outputs_persisted": False,
    }


def _safe_nonnegative_float(value: Any) -> float | None:
    parsed = _safe_optional_float(value)
    if parsed is None:
        return None
    return round(max(0.0, parsed), 6)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return selected


def _policy_rule_from_shadow_patch(
    patch: Any,
    *,
    min_examples: int,
) -> dict[str, Any] | None:
    if not isinstance(patch, Mapping):
        return None
    target = patch.get("target") if isinstance(patch.get("target"), Mapping) else {}
    evidence = patch.get("evidence") if isinstance(patch.get("evidence"), Mapping) else {}
    if _safe_int(evidence.get("example_count")) < min_examples:
        return None
    public_model = str(target.get("public_model") or "all").strip().lower()
    if public_model not in {*PUBLIC_MODELS, "all"}:
        return None
    task_type = _safe_label(target.get("task_type"), default="all")
    controls = _controls_from_shadow_patch(patch)
    if not controls:
        return None
    match = {
        "public_model": public_model,
        "task_type": task_type,
        "min_risk": 0.0,
    }
    rule_id = sha256_text(
        stable_json(
            {
                "target": match,
                "controls": controls,
                "patch_id": str(patch.get("patch_id") or ""),
            }
        )
    )
    return {
        "rule_id_sha256": rule_id,
        "match": match,
        "controls": controls,
        "evidence": {
            "example_count": _safe_int(evidence.get("example_count")),
            "accepted_rate": _safe_optional_float(evidence.get("accepted_rate")),
            "average_score": _safe_optional_float(evidence.get("average_score")),
            "trace_joined_count": _safe_int(evidence.get("trace_joined_count")),
        },
        "source_patch_id_sha256": sha256_text(str(patch.get("patch_id") or "")),
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
    }


def _controls_from_shadow_patch(patch: Mapping[str, Any]) -> dict[str, Any]:
    delta = (
        patch.get("suggested_policy_delta")
        if isinstance(patch.get("suggested_policy_delta"), Mapping)
        else {}
    )
    action = _safe_label(patch.get("action"), default="")
    controls: dict[str, Any] = {}
    quality_delta = _safe_optional_float(delta.get("quality_target_delta"))
    if quality_delta is not None and 0.0 < quality_delta <= 0.16:
        controls["quality_target_floor"] = round(min(0.96, 0.72 + quality_delta), 4)
    if delta.get("targeted_escalation_enabled") is True or "agent" in action:
        controls["force_fusion"] = True
        controls["max_fusion_depth"] = 2
    if delta.get("fast_light_verify") is True or "fast" in action:
        controls["fast_light_verify"] = True
    if _safe_optional_int(delta.get("max_models_cap")) is not None:
        controls["max_panel_models"] = _safe_optional_int(delta.get("max_models_cap"))
    directives: list[str] = []
    if any(token in action for token in ("factual", "source", "grounding")):
        directives.extend(["evidence_first", "uncertainty_calibration"])
    if any(token in action for token in ("agent", "tool")):
        directives.extend(
            ["independent_solution", "tool_schema_strict", "verify_assumptions"]
        )
    if any(token in action for token in ("claim", "critic", "verification")):
        directives.extend(["independent_solution", "verify_assumptions"])
    if delta.get("rank_first_candidate_compression") is True:
        directives.append("concise_synthesis")
    directives = [
        directive
        for directive in dict.fromkeys(directives)
        if directive in ROUTING_POLICY_ALLOWED_CONTEXT_DIRECTIVES
    ]
    if directives:
        controls["context_directives"] = directives
    return _safe_controls(controls)


def _safe_rules(value: Any) -> list[dict[str, Any]]:
    rules = value if isinstance(value, list) else []
    safe = []
    for rule in rules[:ROUTING_POLICY_MAX_RULES]:
        if not isinstance(rule, Mapping):
            continue
        match = rule.get("match") if isinstance(rule.get("match"), Mapping) else {}
        controls = _safe_controls(rule.get("controls"))
        rule_id = str(rule.get("rule_id_sha256") or "")
        if not _looks_like_sha256(rule_id) or not _valid_match(match) or not controls:
            continue
        safe.append(
            {
                "rule_id_sha256": rule_id,
                "match": {
                    "public_model": str(match.get("public_model") or "all"),
                    "task_type": _safe_label(match.get("task_type"), default="all"),
                    "min_risk": round(max(0.0, min(1.0, _safe_float(match.get("min_risk")))), 4),
                },
                "controls": controls,
                "evidence": _safe_rule_evidence(rule.get("evidence")),
                "source_patch_id_sha256": str(
                    rule.get("source_patch_id_sha256") or ""
                ),
                "raw_prompt_persisted": False,
                "raw_provider_names_persisted": False,
                "raw_provider_model_ids_persisted": False,
            }
        )
    return safe


def _safe_controls(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    controls: dict[str, Any] = {}
    floor = _safe_optional_float(value.get("quality_target_floor"))
    if floor is not None and 0.72 <= floor <= 0.96:
        controls["quality_target_floor"] = round(floor, 4)
    if value.get("force_fusion") is True:
        controls["force_fusion"] = True
    if value.get("fast_light_verify") is True:
        controls["fast_light_verify"] = True
    panel_cap = _safe_optional_int(value.get("max_panel_models"))
    if panel_cap is not None and 1 <= panel_cap <= 6:
        controls["max_panel_models"] = panel_cap
    depth_cap = _safe_optional_int(value.get("max_fusion_depth"))
    if depth_cap is not None and 0 <= depth_cap <= 2:
        controls["max_fusion_depth"] = depth_cap
    directives = value.get("context_directives") if isinstance(value.get("context_directives"), list) else []
    directives = [
        str(item)
        for item in directives
        if str(item) in ROUTING_POLICY_ALLOWED_CONTEXT_DIRECTIVES
    ]
    if directives:
        controls["context_directives"] = list(dict.fromkeys(directives))
    return controls


def _safe_rule_evidence(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    return {
        "example_count": _safe_int(value.get("example_count")),
        "accepted_rate": _safe_optional_float(value.get("accepted_rate")),
        "average_score": _safe_optional_float(value.get("average_score")),
        "trace_joined_count": _safe_int(value.get("trace_joined_count")),
    }


def _shadow_patch_validation_errors(shadow_patch: Mapping[str, Any]) -> list[str]:
    errors = []
    if str(shadow_patch.get("schema") or "") != "axio_fusion_api.router_policy_shadow_patch.v1":
        errors.append("routing_policy_shadow_patch_schema_unrecognized")
    if shadow_patch.get("shadow_only") is not True:
        errors.append("routing_policy_shadow_patch_not_shadow_only")
    if shadow_patch.get("safe_to_apply_automatically") is not False:
        errors.append("routing_policy_shadow_patch_automatic_apply_flag_invalid")
    contract = (
        shadow_patch.get("application_contract")
        if isinstance(shadow_patch.get("application_contract"), Mapping)
        else {}
    )
    if contract.get("production_policy_changed") is not False:
        errors.append("routing_policy_shadow_patch_production_change_detected")
    if contract.get("not_for_final_benchmark_claims") is not True:
        errors.append("routing_policy_shadow_patch_benchmark_contract_missing")
    if _contains_forbidden_raw_fields(shadow_patch):
        errors.append("routing_policy_shadow_patch_contains_raw_private_fields")
    return errors


def _candidate_validation_errors(
    candidate: Mapping[str, Any],
    *,
    profiles: Sequence[ModelProfile],
) -> list[str]:
    errors = []
    if str(candidate.get("schema") or "") != ROUTING_POLICY_CANDIDATE_SCHEMA:
        errors.append("routing_policy_candidate_schema_unrecognized")
    digest = str(candidate.get("candidate_digest_sha256") or "")
    if not _looks_like_sha256(digest) or digest != sha256_text(
        stable_json(_candidate_digest_input(candidate))
    ):
        errors.append("routing_policy_candidate_digest_mismatch")
    if candidate.get("status") != "draft":
        errors.append("routing_policy_candidate_status_invalid")
    if candidate.get("ready_for_review") is not True:
        errors.append("routing_policy_candidate_not_ready_for_review")
    if str(candidate.get("registry_profile_set_sha256") or "") != _profile_set_sha256(profiles):
        errors.append("routing_policy_candidate_registry_binding_mismatch")
    rules = _safe_rules(candidate.get("rules"))
    if len(rules) != _safe_int(candidate.get("rule_count")) or not rules:
        errors.append("routing_policy_candidate_rules_invalid")
    if _contains_forbidden_raw_fields(candidate):
        errors.append("routing_policy_candidate_contains_raw_private_fields")
    return sorted(set(errors))


def _review_validation_errors(
    review: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    profiles: Sequence[ModelProfile],
) -> list[str]:
    errors = []
    if str(review.get("schema") or "") != ROUTING_POLICY_REVIEW_SCHEMA:
        errors.append("routing_policy_review_schema_unrecognized")
    digest = str(review.get("review_digest_sha256") or "")
    if not _looks_like_sha256(digest) or digest != sha256_text(
        stable_json(_review_digest_input(review))
    ):
        errors.append("routing_policy_review_digest_mismatch")
    if review.get("approved") is not True or review.get("ready_for_activation") is not True:
        errors.append("routing_policy_review_not_approved")
    if str(review.get("candidate_digest_sha256") or "") != str(
        candidate.get("candidate_digest_sha256") or ""
    ):
        errors.append("routing_policy_review_candidate_binding_mismatch")
    if str(review.get("registry_profile_set_sha256") or "") != _profile_set_sha256(profiles):
        errors.append("routing_policy_review_registry_binding_mismatch")
    contamination = review.get("contamination_audit")
    if not isinstance(contamination, Mapping) or contamination.get("clean") is not True:
        errors.append("routing_policy_review_contamination_binding_invalid")
    if _contains_forbidden_raw_fields(review):
        errors.append("routing_policy_review_contains_raw_private_fields")
    return sorted(set(errors))


def _bundle_validation_errors(
    bundle: Mapping[str, Any],
    *,
    profiles: Sequence[ModelProfile],
) -> list[str]:
    errors = []
    if str(bundle.get("schema") or "") != ROUTING_POLICY_BUNDLE_SCHEMA:
        errors.append("routing_policy_bundle_schema_unrecognized")
    if bundle.get("status") != "active" or bundle.get("activation_ready") is not True:
        errors.append("routing_policy_bundle_not_active")
    digest = str(bundle.get("bundle_digest_sha256") or "")
    if not _looks_like_sha256(digest) or digest != sha256_text(
        stable_json(_bundle_digest_input(bundle))
    ):
        errors.append("routing_policy_bundle_digest_mismatch")
    if str(bundle.get("registry_profile_set_sha256") or "") != _profile_set_sha256(profiles):
        errors.append("routing_policy_bundle_registry_binding_mismatch")
    rules = _safe_rules(bundle.get("rules"))
    if not rules or len(rules) != _safe_int(bundle.get("rule_count")):
        errors.append("routing_policy_bundle_rules_invalid")
    if _contains_forbidden_raw_fields(bundle):
        errors.append("routing_policy_bundle_contains_raw_private_fields")
    return sorted(set(errors))


def _contamination_receipt(audit: Mapping[str, Any]) -> dict[str, Any]:
    blocker_count = _safe_int(audit.get("blocker_count"))
    learning_clean = audit.get("final_claim_training_clean") is True
    clean = bool(audit) and blocker_count == 0 and learning_clean
    return {
        "schema": str(audit.get("schema") or ""),
        "content_sha256": sha256_text(stable_json(_contamination_digest_input(audit)))
        if audit
        else "",
        "blocker_count": blocker_count,
        "final_claim_training_clean": learning_clean,
        "clean": clean,
        "raw_artifact_paths_persisted": False,
        "raw_benchmark_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
    }


def _contamination_digest_input(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(audit.get("schema") or ""),
        "blocker_count": _safe_int(audit.get("blocker_count")),
        "warning_count": _safe_int(audit.get("warning_count")),
        "final_claim_training_clean": audit.get("final_claim_training_clean") is True,
        "benchmark_labels_used_for_training": audit.get(
            "benchmark_labels_used_for_training"
        ) is True,
        "benchmark_scores_used_for_router_learning": audit.get(
            "benchmark_scores_used_for_router_learning"
        ) is True,
    }


def _disabled_policy(*reasons: str, path: Path | None = None, bundle_digest_sha256: str = "") -> dict[str, Any]:
    return {
        "schema": ROUTING_POLICY_BUNDLE_SCHEMA,
        "active": False,
        "policy_id_sha256": "",
        "bundle_digest_sha256": bundle_digest_sha256
        if _looks_like_sha256(bundle_digest_sha256)
        else "",
        "registry_profile_set_sha256": "",
        "rules": [],
        "rule_count": 0,
        "load_path_sha256": sha256_text(str(path)) if path is not None else "",
        "reason_codes": sorted(set(str(reason) for reason in reasons if reason)),
        "raw_local_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _empty_policy_application(policy: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.routing_policy_application.v1",
        "active": policy.get("active") is True,
        "applied": False,
        "policy_id_sha256": str(policy.get("policy_id_sha256") or ""),
        "bundle_digest_sha256": str(policy.get("bundle_digest_sha256") or ""),
        "matched_rule_count": 0,
        "matched_rule_id_hashes": [],
        "quality_target_floor": None,
        "force_fusion": False,
        "fast_light_verify": False,
        "max_panel_models": None,
        "max_fusion_depth": None,
        "context_directives": [],
        "reason_codes": [reason],
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _rule_matches(
    match: Mapping[str, Any],
    *,
    public_model: str,
    task_type: str,
    risk: float,
) -> bool:
    model = str(match.get("public_model") or "all")
    task = _safe_label(match.get("task_type"), default="all")
    minimum_risk = max(0.0, min(1.0, _safe_float(match.get("min_risk"))))
    return (
        model in {"all", public_model}
        and task in {"all", task_type}
        and risk >= minimum_risk
    )


def _valid_match(match: Mapping[str, Any]) -> bool:
    model = str(match.get("public_model") or "all")
    return (
        model in {*PUBLIC_MODELS, "all"}
        and bool(_safe_label(match.get("task_type"), default="all"))
        and 0.0 <= _safe_float(match.get("min_risk")) <= 1.0
    )


def _profile_set_sha256(profiles: Sequence[ModelProfile]) -> str:
    return sha256_text(
        stable_json(sorted({sha256_text(profile.profile_id) for profile in profiles}))
    )


def _candidate_digest_input(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ROUTING_POLICY_CANDIDATE_SCHEMA,
        "status": str(candidate.get("status") or ""),
        "created_on": str(candidate.get("created_on") or ""),
        "registry_profile_set_sha256": str(
            candidate.get("registry_profile_set_sha256") or ""
        ),
        "source_shadow_patch_digest_sha256": str(
            candidate.get("source_shadow_patch_digest_sha256") or ""
        ),
        "source_shadow_patch_schema": str(
            candidate.get("source_shadow_patch_schema") or ""
        ),
        "source_shadow_patch_shadow_only": candidate.get(
            "source_shadow_patch_shadow_only"
        )
        is True,
        "minimum_examples_per_rule": _safe_int(
            candidate.get("minimum_examples_per_rule")
        ),
        "rule_count": _safe_int(candidate.get("rule_count")),
        "rules": _safe_rules(candidate.get("rules")),
        "ready_for_review": candidate.get("ready_for_review") is True,
        "blockers": sorted(str(item) for item in candidate.get("blockers", []) if item),
        "application_contract": {
            key: value
            for key, value in (
                candidate.get("application_contract", {}).items()
                if isinstance(candidate.get("application_contract"), Mapping)
                else []
            )
        },
    }


def _review_digest_input(review: Mapping[str, Any]) -> dict[str, Any]:
    contamination = (
        review.get("contamination_audit")
        if isinstance(review.get("contamination_audit"), Mapping)
        else {}
    )
    return {
        "schema": ROUTING_POLICY_REVIEW_SCHEMA,
        "candidate_digest_sha256": str(review.get("candidate_digest_sha256") or ""),
        "registry_profile_set_sha256": str(
            review.get("registry_profile_set_sha256") or ""
        ),
        "reviewed_on": str(review.get("reviewed_on") or ""),
        "approved": review.get("approved") is True,
        "reviewer_id_sha256": str(review.get("reviewer_id_sha256") or ""),
        "contamination_audit": dict(contamination),
        "ready_for_activation": review.get("ready_for_activation") is True,
        "blockers": sorted(str(item) for item in review.get("blockers", []) if item),
    }


def _bundle_digest_input(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ROUTING_POLICY_BUNDLE_SCHEMA,
        "status": str(bundle.get("status") or ""),
        "activated_on": str(bundle.get("activated_on") or ""),
        "policy_id_sha256": str(bundle.get("policy_id_sha256") or ""),
        "policy_candidate_digest_sha256": str(
            bundle.get("policy_candidate_digest_sha256") or ""
        ),
        "policy_review_digest_sha256": str(
            bundle.get("policy_review_digest_sha256") or ""
        ),
        "registry_profile_set_sha256": str(
            bundle.get("registry_profile_set_sha256") or ""
        ),
        "source_shadow_patch_digest_sha256": str(
            bundle.get("source_shadow_patch_digest_sha256") or ""
        ),
        "rollback_policy_digest_sha256": str(
            bundle.get("rollback_policy_digest_sha256") or ""
        ),
        "rule_count": _safe_int(bundle.get("rule_count")),
        "rules": _safe_rules(bundle.get("rules")),
        "activation_ready": bundle.get("activation_ready") is True,
        "blockers": sorted(str(item) for item in bundle.get("blockers", []) if item),
        "application_contract": {
            key: value
            for key, value in (
                bundle.get("application_contract", {}).items()
                if isinstance(bundle.get("application_contract"), Mapping)
                else []
            )
        },
    }


def _shadow_patch_digest_input(shadow_patch: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(shadow_patch.get("schema") or ""),
        "shadow_only": shadow_patch.get("shadow_only") is True,
        "safe_to_apply_automatically": shadow_patch.get(
            "safe_to_apply_automatically"
        )
        is True,
        "eligible_feedback_count": _safe_int(
            shadow_patch.get("eligible_feedback_count")
        ),
        "min_examples_per_bucket": _safe_int(
            shadow_patch.get("min_examples_per_bucket")
        ),
        "patch_candidate_count": _safe_int(
            shadow_patch.get("patch_candidate_count")
        ),
        "patch_candidates": [
            {
                "patch_id": str(row.get("patch_id") or ""),
                "target": dict(row.get("target") or {})
                if isinstance(row.get("target"), Mapping)
                else {},
                "action": _safe_label(row.get("action")),
                "evidence": dict(row.get("evidence") or {})
                if isinstance(row.get("evidence"), Mapping)
                else {},
                "suggested_policy_delta": dict(
                    row.get("suggested_policy_delta") or {}
                )
                if isinstance(row.get("suggested_policy_delta"), Mapping)
                else {},
            }
            for row in shadow_patch.get("patch_candidates", [])
            if isinstance(row, Mapping)
        ],
    }


def _dedupe_rules(rules: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for rule in rules:
        rule_id = str(rule.get("rule_id_sha256") or "")
        if not rule_id or rule_id in seen:
            continue
        seen.add(rule_id)
        deduped.append(dict(rule))
    return deduped


def _contains_forbidden_raw_fields(value: Any) -> bool:
    forbidden = {
        "provider",
        "provider_name",
        "model",
        "model_id",
        "canonical_model_id",
        "base_url",
        "api_key",
        "prompt",
        "system_prompt",
        "source_locator",
        "reviewer_id",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key or "").strip().lower()
            if normalized in forbidden or normalized.endswith("_url"):
                return True
            if _contains_forbidden_raw_fields(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_raw_fields(item) for item in value)
    return False


def _safe_label(value: Any, *, default: str = "") -> str:
    text = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return (text[:80] or default)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_optional_float(value: Any) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").strip().lower()))


def _valid_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return False
    return True
