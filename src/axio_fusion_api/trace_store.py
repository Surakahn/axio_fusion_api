from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .schemas import FusionResponse, sha256_text, stable_json
from .tool_contract import tool_call_safe_summary


def record_execution_trace(
    response: FusionResponse,
    *,
    tenant_key: str = "",
    path: str | Path | None = None,
) -> Path | None:
    selected = _trace_path(path)
    if not selected:
        return None
    receipt = safe_execution_trace(response, tenant_key=tenant_key)
    selected.parent.mkdir(parents=True, exist_ok=True)
    with selected.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
    return selected


def safe_execution_trace(response: FusionResponse, *, tenant_key: str = "") -> dict[str, Any]:
    route_plan = response.route_plan if isinstance(response.route_plan, Mapping) else {}
    trace = response.trace if isinstance(response.trace, Mapping) else {}
    trace_routing = trace.get("routing_decision") if isinstance(trace.get("routing_decision"), Mapping) else {}
    task_dag = route_plan.get("task_dag") if isinstance(route_plan.get("task_dag"), Mapping) else {}
    budget = route_plan.get("budget") if isinstance(route_plan.get("budget"), Mapping) else {}
    admission = route_plan.get("fusion_admission") if isinstance(route_plan.get("fusion_admission"), Mapping) else {}
    finalization_mode = str(
        budget.get("fusion_finalization_mode")
        or admission.get("fusion_finalization_mode")
        or "direct"
    )[:80]
    request_analysis = route_plan.get("request_analysis") if isinstance(route_plan.get("request_analysis"), Mapping) else {}
    stage_profile_reuse = _stage_profile_reuse_from_roles(
        route_plan.get("roles") if isinstance(route_plan.get("roles"), list) else []
    )
    circuit_filter = (
        route_plan.get("runtime_circuit_filter")
        if isinstance(route_plan.get("runtime_circuit_filter"), Mapping)
        else {}
    )
    judge = response.judge_result if isinstance(response.judge_result, Mapping) else {}
    return {
        "schema": "axio_fusion_api.execution_trace_receipt.v1",
        "response_id": response.response_id,
        "created": response.created,
        "tenant_sha256": sha256_text(tenant_key) if tenant_key else "",
        "request": response.request.prompt_free_dict(),
        "request_analysis": _safe_request_analysis(request_analysis),
        "routing_decision": {
            "public_model": response.request.public_model,
            "strategy": route_plan.get("strategy") or trace_routing.get("strategy"),
            "selected_profile_hashes": _selected_profile_hashes(route_plan),
            "selected_model_count": len(_selected_profile_hashes(route_plan)),
            "fusion_activated": bool(route_plan.get("judge_contract", {}).get("required")) if isinstance(route_plan.get("judge_contract"), Mapping) else False,
            "fusion_finalization_mode": finalization_mode,
            "local_consensus_enabled": finalization_mode == "local_consensus",
            "provider_stage_calls_reserved": finalization_mode == "provider_judge_synthesis",
        },
        "routing_policy": _safe_routing_policy_application(
            route_plan.get("routing_policy")
            if isinstance(route_plan.get("routing_policy"), Mapping)
            else {}
        ),
        "model_selection_policy": _safe_model_selection_policy(
            route_plan.get("model_selection_policy") if isinstance(route_plan.get("model_selection_policy"), Mapping) else {}
        ),
        "quality_diversity_archive": _safe_quality_diversity_archive(
            route_plan.get("quality_diversity_archive") if isinstance(route_plan.get("quality_diversity_archive"), Mapping) else {}
        ),
        "provider_routing_policy": _safe_provider_routing_policy(
            route_plan.get("provider_routing_policy") if isinstance(route_plan.get("provider_routing_policy"), Mapping) else {}
        ),
        "runtime_provider_telemetry": _safe_runtime_provider_telemetry(
            circuit_filter.get("runtime_provider_telemetry")
            if isinstance(circuit_filter.get("runtime_provider_telemetry"), Mapping)
            else {}
        ),
        "fusion_admission": _safe_fusion_admission(route_plan.get("fusion_admission") if isinstance(route_plan.get("fusion_admission"), Mapping) else {}),
        "stage_profile_reuse": _safe_stage_profile_reuse(stage_profile_reuse),
        "task_plan": _safe_task_plan(task_dag),
        "candidate_outputs": [_safe_candidate(candidate.safe_dict()) for candidate in response.candidates],
        "tool_call_summary": _safe_tool_call_summary(response.tool_calls),
        "tool_call_arbitration": _safe_tool_call_arbitration(
            trace.get("tool_call_arbitration")
            if isinstance(trace.get("tool_call_arbitration"), Mapping)
            else {}
        ),
        "judge_result": _safe_judge(judge),
        "early_exit": _safe_early_exit(trace.get("early_exit") if isinstance(trace.get("early_exit"), Mapping) else {}),
        "candidate_deduplication": _safe_candidate_deduplication(
            trace.get("candidate_deduplication") if isinstance(trace.get("candidate_deduplication"), Mapping) else {}
        ),
        "panel_repair": _safe_panel_repair(trace.get("panel_repair") if isinstance(trace.get("panel_repair"), Mapping) else {}),
        "synthesis_compression": _safe_synthesis_compression(trace.get("synthesis_compression") if isinstance(trace.get("synthesis_compression"), Mapping) else {}),
        "runtime_fusion_stage_outcome": _safe_runtime_fusion_stage_outcome(
            trace.get("runtime_fusion_stage_outcome")
            if isinstance(trace.get("runtime_fusion_stage_outcome"), Mapping)
            else {}
        ),
        "hermes_moa_execution": _safe_hermes_moa_execution(
            trace.get("hermes_moa_execution")
            if isinstance(trace.get("hermes_moa_execution"), Mapping)
            else {}
        ),
        "cache_replay": _safe_response_cache_replay(
            trace.get("cache_replay")
            if isinstance(trace.get("cache_replay"), Mapping)
            else {}
        ),
        "cache_origin_completion": _safe_response_cache_origin_completion(
            trace.get("cache_origin_completion")
            if isinstance(trace.get("cache_origin_completion"), Mapping)
            else {}
        ),
        "final_answer": {
            "answer_sha256": sha256_text(response.text),
            "answer_char_count": len(response.text),
            "raw_final_answer_persisted": False,
        },
        "cost": {
            "actual_cost_usd": _optional_float(trace.get("actual_cost_usd")),
            "provider_call_count": _optional_int(trace.get("provider_call_count")),
            "cache_hit": bool(trace.get("cache_hit")),
        },
        "latency_ms": _optional_float(trace.get("latency_ms")),
        "runtime_guards": _safe_runtime_guards(route_plan),
        "budget_lock": _safe_budget_lock(trace.get("budget_lock") if isinstance(trace.get("budget_lock"), Mapping) else {}),
        "cost_budget": _safe_cost_budget(trace.get("cost_budget") if isinstance(trace.get("cost_budget"), Mapping) else {}),
        "deadline_budget": _safe_deadline_budget(trace.get("deadline_budget") if isinstance(trace.get("deadline_budget"), Mapping) else {}),
        "prompt_budget": _safe_prompt_budget(trace.get("prompt_budget") if isinstance(trace.get("prompt_budget"), Mapping) else {}),
        "feedback_join_key": {
            "response_id": response.response_id,
            "request_fingerprint": response.request.request_fingerprint,
        },
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _stage_profile_reuse_from_roles(roles: Sequence[Any]) -> Mapping[str, Any]:
    for row in roles:
        if not isinstance(row, Mapping):
            continue
        value = row.get("stage_profile_reuse")
        if isinstance(value, Mapping):
            return value
    return {}


def _safe_stage_profile_reuse(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.stage_profile_reuse.v1",
        "expert_profile_count": _optional_int(value.get("expert_profile_count")),
        "unassigned_profile_count": _optional_int(value.get("unassigned_profile_count")),
        "eligible_unassigned_judge_profile_count": _optional_int(
            value.get("eligible_unassigned_judge_profile_count")
        ),
        "eligible_unassigned_synthesizer_profile_count": _optional_int(
            value.get("eligible_unassigned_synthesizer_profile_count")
        ),
        "rejected_unassigned_profile_count": _optional_int(
            value.get("rejected_unassigned_profile_count")
        ),
        "judge_reuses_expert_profile": value.get("judge_reuses_expert_profile") is True,
        "synthesizer_reuses_expert_profile": value.get("synthesizer_reuses_expert_profile") is True,
        "judge_and_synthesizer_share_profile": value.get("judge_and_synthesizer_share_profile") is True,
        "independent_stage_selection_enabled": value.get("independent_stage_selection_enabled") is True,
        "reuse_is_capacity_fallback": value.get("reuse_is_capacity_fallback") is True,
        "selection_policy": str(value.get("selection_policy") or "")[:120],
        "expert_latency_optimization": _safe_latency_optimization(
            value.get("expert_latency_optimization")
            if isinstance(value.get("expert_latency_optimization"), Mapping)
            else {}
        ),
        "latency_optimization": _safe_latency_optimization(
            value.get("latency_optimization")
            if isinstance(value.get("latency_optimization"), Mapping)
            else {}
        ),
        "raw_profile_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_latency_optimization(value: Mapping[str, Any]) -> dict[str, Any]:
    schema = str(value.get("schema") or "")
    allowed_schemas = {
        "axio_fusion_api.expert_latency_optimization.v1",
        "axio_fusion_api.stage_latency_optimization.v1",
    }
    return {
        "schema": schema if schema in allowed_schemas else "axio_fusion_api.latency_optimization.v1",
        "enabled": value.get("enabled") is True,
        "applied": value.get("applied") is True,
        "reason": str(value.get("reason") or "")[:120],
        "direct_profile_latency_ms": _optional_float(value.get("direct_profile_latency_ms")),
        "original_expert_phase_latency_ms": _optional_float(value.get("original_expert_phase_latency_ms")),
        "optimized_expert_phase_latency_ms": _optional_float(value.get("optimized_expert_phase_latency_ms")),
        "original_estimated_latency_ms": _optional_float(value.get("original_estimated_latency_ms")),
        "optimized_estimated_latency_ms": _optional_float(value.get("optimized_estimated_latency_ms")),
        "original_latency_multiplier_vs_direct": _optional_float(value.get("original_latency_multiplier_vs_direct")),
        "optimized_latency_multiplier_vs_direct": _optional_float(value.get("optimized_latency_multiplier_vs_direct")),
        "target_latency_multiplier": _optional_float(value.get("target_latency_multiplier")),
        "operational_target_multiplier": _optional_float(value.get("operational_target_multiplier")),
        "replaced_role_count": _optional_int(value.get("replaced_role_count")),
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def build_trace_report(paths: Sequence[str | Path]) -> dict[str, Any]:
    rows = _load_trace_rows(paths)
    costs = [_optional_float(row.get("cost", {}).get("actual_cost_usd")) for row in rows if isinstance(row.get("cost"), Mapping)]
    latencies = [_optional_float(row.get("latency_ms")) for row in rows]
    provider_calls = [_optional_int(row.get("cost", {}).get("provider_call_count")) for row in rows if isinstance(row.get("cost"), Mapping)]
    strategies: dict[str, int] = {}
    public_models: dict[str, int] = {}
    task_types: dict[str, int] = {}
    provider_routing_summary = _provider_routing_report(rows)
    routing_policy_summary = _routing_policy_report(rows)
    for row in rows:
        routing = row.get("routing_decision") if isinstance(row.get("routing_decision"), Mapping) else {}
        analysis = row.get("request_analysis") if isinstance(row.get("request_analysis"), Mapping) else {}
        strategy = str(routing.get("strategy") or "unknown")
        model = str(routing.get("public_model") or "unknown")
        task_type = str(analysis.get("task_type") or "unknown")
        strategies[strategy] = strategies.get(strategy, 0) + 1
        public_models[model] = public_models.get(model, 0) + 1
        task_types[task_type] = task_types.get(task_type, 0) + 1
    return {
        "schema": "axio_fusion_api.trace_report.v1",
        "trace_file_count": len(paths),
        "trace_count": len(rows),
        "average_cost_usd": _average(costs),
        "average_latency_ms": _average(latencies),
        "average_provider_call_count": _average(provider_calls),
        "by_strategy": dict(sorted(strategies.items())),
        "by_public_model": dict(sorted(public_models.items())),
        "by_task_type": dict(sorted(task_types.items())),
        "provider_routing_summary": provider_routing_summary,
        "routing_policy_summary": routing_policy_summary,
        "training_join_ready": bool(rows),
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def _routing_policy_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    active_count = 0
    applied_count = 0
    matched_rule_counts: list[int | None] = []
    directive_counts: list[int | None] = []
    by_version: dict[str, int] = {}
    no_match_count = 0
    inactive_count = 0
    for row in rows:
        policy = row.get("routing_policy") if isinstance(row.get("routing_policy"), Mapping) else {}
        if not policy:
            continue
        active = policy.get("active") is True
        applied = policy.get("applied") is True
        if active:
            active_count += 1
        else:
            inactive_count += 1
        if applied:
            applied_count += 1
        reasons = policy.get("reason_codes") if isinstance(policy.get("reason_codes"), list) else []
        if "routing_policy_no_matching_rule" in reasons:
            no_match_count += 1
        version = str(policy.get("bundle_digest_sha256") or policy.get("policy_id_sha256") or "")
        if _looks_like_sha256(version):
            by_version[version] = by_version.get(version, 0) + 1
        matched_rule_counts.append(_optional_int(policy.get("matched_rule_count")))
        directive_counts.append(_optional_int(policy.get("context_directive_count")))
    return {
        "policy_receipt_count": sum(
            1
            for row in rows
            if isinstance(row.get("routing_policy"), Mapping)
        ),
        "active_count": active_count,
        "applied_count": applied_count,
        "inactive_count": inactive_count,
        "no_matching_rule_count": no_match_count,
        "policy_version_count": len(by_version),
        "policy_version_usage": [
            {
                "policy_version_sha256": version,
                "trace_count": count,
            }
            for version, count in sorted(
                by_version.items(), key=lambda item: (-item[1], item[0])
            )[:24]
        ],
        "average_matched_rule_count": _average(matched_rule_counts),
        "average_context_directive_count": _average(directive_counts),
        "raw_policy_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _provider_routing_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    policy_count = 0
    fallback_enabled: list[bool | None] = []
    pool_counts: list[int | None] = []
    top_routing_scores: list[float | None] = []
    top_availability_scores: list[float | None] = []
    top_latency_scores: list[float | None] = []
    top_cost_scores: list[float | None] = []
    nonpanel_counts: list[int | None] = []
    selected_panel_counts: list[int | None] = []
    api_format_counts: list[int | None] = []
    provider_hash_counts: list[int | None] = []
    low_top_availability: list[bool | None] = []
    low_top_routing: list[bool | None] = []
    nonpanel_available: list[bool | None] = []
    for row in rows:
        policy = row.get("provider_routing_policy") if isinstance(row.get("provider_routing_policy"), Mapping) else {}
        if not policy:
            continue
        policy_count += 1
        fallback_enabled.append(policy.get("fallback_enabled") is True)
        receipts = policy.get("fallback_pool_receipts") if isinstance(policy.get("fallback_pool_receipts"), list) else []
        safe_receipts = [receipt for receipt in receipts[:24] if isinstance(receipt, Mapping)]
        safe_receipts.sort(key=lambda receipt: _optional_int(receipt.get("fallback_rank")) or 10_000)
        pool_count = _optional_int(policy.get("fallback_pool_count"))
        if pool_count is None:
            pool_count = len(safe_receipts)
        selected_count = sum(1 for receipt in safe_receipts if receipt.get("selected_in_primary_panel") is True)
        nonpanel_count = sum(1 for receipt in safe_receipts if receipt.get("selected_in_primary_panel") is not True)
        api_formats = {str(receipt.get("api_format") or "") for receipt in safe_receipts if str(receipt.get("api_format") or "")}
        provider_hashes = {
            str(receipt.get("provider_sha256") or "")
            for receipt in safe_receipts
            if _looks_like_sha256(receipt.get("provider_sha256"))
        }
        top = safe_receipts[0] if safe_receipts else {}
        top_routing = _optional_float(top.get("routing_score"))
        top_availability = _optional_float(top.get("availability_score"))
        pool_counts.append(pool_count)
        selected_panel_counts.append(selected_count)
        nonpanel_counts.append(nonpanel_count)
        api_format_counts.append(len(api_formats))
        provider_hash_counts.append(len(provider_hashes))
        top_routing_scores.append(top_routing)
        top_availability_scores.append(top_availability)
        top_latency_scores.append(_optional_float(top.get("latency_score")))
        top_cost_scores.append(_optional_float(top.get("cost_score")))
        low_top_availability.append(None if top_availability is None else top_availability < 0.65)
        low_top_routing.append(None if top_routing is None else top_routing < 0.5)
        nonpanel_available.append(nonpanel_count > 0)
    return {
        "schema": "axio_fusion_api.trace_provider_routing_summary.v1",
        "policy_count": policy_count,
        "fallback_enabled_rate": _rate(fallback_enabled),
        "average_fallback_pool_count": _average(pool_counts),
        "average_top_routing_score": _average(top_routing_scores),
        "average_top_availability_score": _average(top_availability_scores),
        "average_top_latency_score": _average(top_latency_scores),
        "average_top_cost_score": _average(top_cost_scores),
        "average_selected_panel_count": _average(selected_panel_counts),
        "average_nonpanel_count": _average(nonpanel_counts),
        "average_api_format_count": _average(api_format_counts),
        "average_provider_hash_count": _average(provider_hash_counts),
        "nonpanel_available_rate": _rate(nonpanel_available),
        "low_top_availability_rate": _rate(low_top_availability),
        "low_top_routing_rate": _rate(low_top_routing),
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _trace_path(path: str | Path | None = None) -> Path | None:
    if path:
        return Path(path)
    explicit = os.getenv("AXIO_FUSION_TRACE_LOG", "").strip()
    if explicit:
        return Path(explicit)
    artifact_dir = os.getenv("AXIO_FUSION_ARTIFACT_DIR", "").strip()
    if artifact_dir:
        return Path(artifact_dir) / "execution_traces.jsonl"
    return None


def _safe_request_analysis(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_type": str(value.get("task_type") or ""),
        "domains": [str(item) for item in value.get("domains", []) if str(item)][:12] if isinstance(value.get("domains"), list) else [],
        "complexity": _optional_float(value.get("complexity")),
        "risk": _optional_float(value.get("risk")),
        "uncertainty": _optional_float(value.get("uncertainty")),
        "privacy_level": str(value.get("privacy_level") or ""),
        "needs_current_information": bool(value.get("needs_current_information")),
        "needs_tools": bool(value.get("needs_tools")),
        "factuality_signal": bool(value.get("factuality_signal")),
        "vertical_domain_signals": [
            str(item)[:80]
            for item in value.get("vertical_domain_signals", [])
            if str(item)
        ][:12] if isinstance(value.get("vertical_domain_signals"), list) else [],
        "estimated_steps": _optional_int(value.get("estimated_steps")),
        "single_model_failure_loss": _optional_float(value.get("single_model_failure_loss")),
        "expected_output_tokens": _optional_int(value.get("expected_output_tokens")),
        "raw_prompt_persisted": False,
    }


def _selected_profile_hashes(route_plan: Mapping[str, Any]) -> list[str]:
    selected = route_plan.get("selected_models") if isinstance(route_plan.get("selected_models"), list) else []
    return [
        sha256_text(str(row.get("profile_id") or ""))
        for row in selected[:24]
        if isinstance(row, Mapping) and row.get("profile_id")
    ]


def _safe_task_plan(task_dag: Mapping[str, Any]) -> dict[str, Any]:
    nodes = task_dag.get("nodes") if isinstance(task_dag.get("nodes"), list) else []
    checkpoints = task_dag.get("checkpoints") if isinstance(task_dag.get("checkpoints"), list) else []
    return {
        "schema": task_dag.get("schema") or "axio_fusion_api.task_dag.v1",
        "fusion_finalization_mode": str(task_dag.get("fusion_finalization_mode") or "direct")[:80],
        "provider_stage_calls_reserved": bool(task_dag.get("provider_stage_calls_reserved")),
        "decomposable": bool(task_dag.get("decomposable")),
        "node_count": _optional_int(task_dag.get("node_count")),
        "edge_count": _optional_int(task_dag.get("edge_count")),
        "checkpoint_count": _optional_int(task_dag.get("checkpoint_count")),
        "subtask_count": _optional_int(task_dag.get("subtask_count")),
        "max_dependency_depth": _optional_int(task_dag.get("max_dependency_depth")),
        "node_receipts": [
            {
                "id": str(node.get("id") or ""),
                "kind": str(node.get("kind") or ""),
                "dependency_count": len(node.get("depends_on", [])) if isinstance(node.get("depends_on"), list) else 0,
                "required_capabilities": [str(item) for item in node.get("required_capabilities", []) if str(item)][:12] if isinstance(node.get("required_capabilities"), list) else [],
                "parallelizable": bool(node.get("parallelizable")),
                "verification_required": bool(node.get("verification_required")),
                "assigned_role": str(node.get("assigned_role") or ""),
            }
            for node in nodes[:64]
            if isinstance(node, Mapping)
        ],
        "checkpoint_receipts": [
            {
                "id": str(checkpoint.get("id") or ""),
                "after_node": str(checkpoint.get("after_node") or ""),
                "record_count": len(checkpoint.get("records", [])) if isinstance(checkpoint.get("records"), list) else 0,
            }
            for checkpoint in checkpoints[:24]
            if isinstance(checkpoint, Mapping)
        ],
        "raw_prompt_persisted": False,
    }


def _safe_candidate(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": str(value.get("candidate_id") or ""),
        "role": str(value.get("role") or ""),
        "profile_id_sha256": sha256_text(str(value.get("profile_id") or "")),
        "runtime_canonical_identity_sha256": str(
            value.get("runtime_canonical_identity_sha256") or ""
        ),
        "answer_sha256": str(value.get("answer_sha256") or ""),
        "answer_char_count": _optional_int(value.get("answer_char_count")),
        "confidence": _optional_float(value.get("confidence")),
        "reasoning_step_count": _optional_int(value.get("reasoning_step_count")),
        "reasoning_summary_sha256": str(value.get("reasoning_summary_sha256") or ""),
        "reasoning_summary_token_estimate": _optional_int(value.get("reasoning_summary_token_estimate")),
        "evidence_count": _optional_int(value.get("evidence_count")),
        "assumption_count": _optional_int(value.get("assumption_count")),
        "uncertainty_count": _optional_int(value.get("uncertainty_count")),
        "status": str(value.get("status") or ""),
        "latency_ms": _optional_float(value.get("latency_ms")),
        "tool_calls": _safe_tool_call_summary(value.get("tool_calls") if isinstance(value.get("tool_calls"), Mapping) else {}),
        "standardization": _safe_candidate_standardization(value.get("standardization") if isinstance(value.get("standardization"), Mapping) else {}),
        "task_execution": _safe_candidate_task_execution(value.get("task_execution") if isinstance(value.get("task_execution"), Mapping) else {}),
        "escalation_plan": _safe_targeted_escalation_plan(value.get("escalation_plan") if isinstance(value.get("escalation_plan"), Mapping) else {}),
        "tool_execution": _safe_tool_execution(value.get("tool_execution") if isinstance(value.get("tool_execution"), Mapping) else {}),
        "raw_reasoning_summary_persisted": False,
        "raw_candidate_text_persisted": False,
    }


def _safe_tool_call_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return _safe_tool_call_summary(tool_call_safe_summary(value))
    if not isinstance(value, Mapping):
        return {
            "schema": "axio_fusion_api.tool_call_summary.v1",
            "tool_call_count": 0,
            "tool_name_sha256s": [],
            "tool_call_id_sha256s": [],
            "argument_sha256s": [],
            "source_formats": [],
            "raw_tool_names_persisted": False,
            "raw_tool_arguments_persisted": False,
            "raw_tool_results_persisted": False,
        }
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.tool_call_summary.v1"),
        "tool_call_count": _optional_int(value.get("tool_call_count")) or 0,
        "tool_name_sha256s": [str(item) for item in value.get("tool_name_sha256s", []) if str(item)][:16]
        if isinstance(value.get("tool_name_sha256s"), list)
        else [],
        "tool_call_id_sha256s": [str(item) for item in value.get("tool_call_id_sha256s", []) if str(item)][:16]
        if isinstance(value.get("tool_call_id_sha256s"), list)
        else [],
        "argument_sha256s": [str(item) for item in value.get("argument_sha256s", []) if str(item)][:16]
        if isinstance(value.get("argument_sha256s"), list)
        else [],
        "source_formats": [str(item)[:40] for item in value.get("source_formats", []) if str(item)][:8]
        if isinstance(value.get("source_formats"), list)
        else [],
        "raw_tool_names_persisted": False,
        "raw_tool_arguments_persisted": False,
        "raw_tool_results_persisted": False,
    }


def _safe_tool_call_arbitration(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project native tool-plan arbitration without relaying call contents."""

    groups = value.get("tool_plan_groups") if isinstance(value.get("tool_plan_groups"), list) else []
    safe_groups = []
    for row in groups[:16]:
        if not isinstance(row, Mapping):
            continue
        safe_groups.append(
            {
                "tool_plan_sha256": _safe_sha256(row.get("tool_plan_sha256")),
                "supporting_candidate_count": max(0, _optional_int(row.get("supporting_candidate_count")) or 0),
                "supporting_profile_count": max(0, _optional_int(row.get("supporting_profile_count")) or 0),
                "supporting_provider_count": max(0, _optional_int(row.get("supporting_provider_count")) or 0),
                "supporting_profile_hashes": _safe_sha256_list(row.get("supporting_profile_hashes"), limit=12),
                "supporting_provider_hashes": _safe_sha256_list(row.get("supporting_provider_hashes"), limit=12),
                "representative_role": _safe_tool_arbitration_role(row.get("representative_role")),
                "selected": row.get("selected") is True,
                "tool_call_summary": _safe_tool_call_summary(
                    row.get("tool_call_summary") if isinstance(row.get("tool_call_summary"), Mapping) else {}
                ),
                "raw_tool_plan_persisted": False,
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
            }
        )
    return {
        "schema": "axio_fusion_api.native_tool_call_arbitration.v1",
        "enabled": value.get("enabled") is True,
        "candidate_with_native_tool_call_count": max(0, _optional_int(value.get("candidate_with_native_tool_call_count")) or 0),
        "eligible_candidate_plan_count": max(0, _optional_int(value.get("eligible_candidate_plan_count")) or 0),
        "unique_tool_plan_count": max(0, _optional_int(value.get("unique_tool_plan_count")) or 0),
        "rejected_undeclared_tool_call_count": max(0, _optional_int(value.get("rejected_undeclared_tool_call_count")) or 0),
        "rejected_ineligible_role_tool_call_count": max(
            0,
            _optional_int(value.get("rejected_ineligible_role_tool_call_count")) or 0,
        ),
        "selected": value.get("selected") is True,
        "selection_reason": _safe_tool_arbitration_reason(value.get("selection_reason")),
        "selected_tool_plan_sha256": _safe_sha256(value.get("selected_tool_plan_sha256")),
        "selected_role": _safe_tool_arbitration_role(value.get("selected_role")),
        "selected_profile_sha256": _safe_sha256(value.get("selected_profile_sha256")),
        "selected_provider_sha256": _safe_sha256(value.get("selected_provider_sha256")),
        "selected_tool_call_count": max(0, _optional_int(value.get("selected_tool_call_count")) or 0),
        "selected_tool_call_summary": _safe_tool_call_summary(
            value.get("selected_tool_call_summary")
            if isinstance(value.get("selected_tool_call_summary"), Mapping)
            else {}
        ),
        "tool_plan_groups": safe_groups,
        "raw_tool_names_persisted": False,
        "raw_tool_arguments_persisted": False,
        "raw_tool_plan_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "secrets_persisted": False,
    }


def _safe_tool_arbitration_role(value: Any) -> str:
    allowed = {
        "primary_solver",
        "independent_solver",
        "critic",
        "domain_specialist",
        "targeted_escalation",
        "fallback_solver",
    }
    text = str(value or "")
    return text if text in allowed else ""


def _safe_tool_arbitration_reason(value: Any) -> str:
    allowed = {
        "no_declared_native_tool_plan",
        "all_completed_tool_candidates_agree",
        "independent_provider_tool_plan_consensus",
        "primary_solver_tool_plan_preferred_without_independent_consensus",
        "best_available_tool_plan_without_independent_consensus",
    }
    text = str(value or "")
    return text if text in allowed else ""


def _safe_sha256(value: Any) -> str:
    return str(value or "") if _looks_like_sha256(value) else ""


def _safe_sha256_list(value: Any, *, limit: int) -> list[str]:
    rows = value if isinstance(value, list) else []
    return [digest for digest in (_safe_sha256(item) for item in rows) if digest][:limit]


def _safe_candidate_deduplication(value: Mapping[str, Any]) -> dict[str, Any]:
    groups = value.get("duplicate_groups") if isinstance(value.get("duplicate_groups"), list) else []
    stages = value.get("stages") if isinstance(value.get("stages"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.candidate_deduplication.v1",
        "enabled": bool(value.get("enabled")),
        "stage": str(value.get("stage") or ""),
        "strategy": str(value.get("strategy") or ""),
        "candidate_count_before": _optional_int(value.get("candidate_count_before")),
        "candidate_count_after": _optional_int(value.get("candidate_count_after")),
        "duplicate_candidate_count": _optional_int(value.get("duplicate_candidate_count")),
        "duplicate_group_count": _optional_int(value.get("duplicate_group_count")),
        "duplicate_rate": _optional_float(value.get("duplicate_rate")),
        "high_duplicate_rate": bool(value.get("high_duplicate_rate")),
        "duplicate_groups": [
            _safe_candidate_deduplication_group(group)
            for group in groups[:24]
            if isinstance(group, Mapping)
        ],
        "stages": [
            {
                "schema": stage.get("schema") or "axio_fusion_api.candidate_deduplication.v1",
                "stage": str(stage.get("stage") or ""),
                "candidate_count_before": _optional_int(stage.get("candidate_count_before")),
                "candidate_count_after": _optional_int(stage.get("candidate_count_after")),
                "duplicate_candidate_count": _optional_int(stage.get("duplicate_candidate_count")),
                "duplicate_group_count": _optional_int(stage.get("duplicate_group_count")),
                "duplicate_rate": _optional_float(stage.get("duplicate_rate")),
                "high_duplicate_rate": bool(stage.get("high_duplicate_rate")),
                "raw_candidate_text_persisted": False,
                "raw_profile_id_persisted": False,
            }
            for stage in stages[:8]
            if isinstance(stage, Mapping)
        ],
        "raw_candidate_text_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _safe_candidate_deduplication_group(value: Mapping[str, Any]) -> dict[str, Any]:
    duplicates = value.get("duplicate_candidate_receipts") if isinstance(value.get("duplicate_candidate_receipts"), list) else []
    return {
        "group_key_sha256": str(value.get("group_key_sha256") or ""),
        "answer_fingerprint_sha256": str(value.get("answer_fingerprint_sha256") or ""),
        "role_key": str(value.get("role_key") or ""),
        "kept_candidate_id": str(value.get("kept_candidate_id") or ""),
        "kept_profile_id_sha256": str(value.get("kept_profile_id_sha256") or ""),
        "candidate_count": _optional_int(value.get("candidate_count")),
        "duplicate_candidate_count": _optional_int(value.get("duplicate_candidate_count")),
        "duplicate_candidate_receipts": [
            {
                "candidate_id": str(row.get("candidate_id") or ""),
                "role": str(row.get("role") or ""),
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "answer_sha256": str(row.get("answer_sha256") or ""),
                "confidence": _optional_float(row.get("confidence")),
                "answer_char_count": _optional_int(row.get("answer_char_count")),
                "raw_candidate_text_persisted": False,
                "raw_profile_id_persisted": False,
            }
            for row in duplicates[:12]
            if isinstance(row, Mapping)
        ],
        "raw_candidate_text_persisted": False,
        "raw_profile_id_persisted": False,
    }


def _safe_candidate_standardization(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.candidate_standardization.v1",
            "parsed": False,
            "parse_mode": "unknown",
            "normalized_field_count": 0,
            "missing_required_fields": [],
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
        "normalized_field_count": _optional_int(value.get("normalized_field_count")),
        "answer_sha256": str(value.get("answer_sha256") or ""),
        "answer_char_count": _optional_int(value.get("answer_char_count")),
        "reasoning_step_count": _optional_int(value.get("reasoning_step_count")),
        "reasoning_summary_sha256": str(value.get("reasoning_summary_sha256") or ""),
        "evidence_count": _optional_int(value.get("evidence_count")),
        "assumption_count": _optional_int(value.get("assumption_count")),
        "uncertainty_count": _optional_int(value.get("uncertainty_count")),
        "tool_call_count": _optional_int(value.get("tool_call_count")),
        "missing_required_fields": [str(item)[:80] for item in missing[:12] if str(item)],
        "confidence_defaulted": bool(value.get("confidence_defaulted")),
        "confidence_clamped": bool(value.get("confidence_clamped")),
        "source_text_sha256": str(value.get("source_text_sha256") or ""),
        "source_char_count": _optional_int(value.get("source_char_count")),
        "raw_candidate_text_persisted": False,
        "raw_reasoning_summary_persisted": False,
        "secrets_persisted": False,
    }


def _safe_candidate_task_execution(value: Mapping[str, Any]) -> dict[str, Any]:
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
            "replica_routing": _safe_replica_routing({}),
            "raw_prompt_persisted": False,
            "raw_candidate_text_persisted": False,
            "secrets_persisted": False,
        }
    nodes = value.get("node_receipts") if isinstance(value.get("node_receipts"), list) else []
    checkpoints = value.get("checkpoint_receipts") if isinstance(value.get("checkpoint_receipts"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.candidate_task_execution.v1",
        "role": str(value.get("role") or "")[:80],
        "assigned_node_count": _optional_int(value.get("assigned_node_count")),
        "verification_node_count": _optional_int(value.get("verification_node_count")),
        "dependency_count": _optional_int(value.get("dependency_count")),
        "checkpoint_count": _optional_int(value.get("checkpoint_count")),
        "node_receipts": [
            {
                "id": str(row.get("id") or "")[:120],
                "kind": str(row.get("kind") or "")[:80],
                "assigned_role": str(row.get("assigned_role") or "")[:80],
                "dependency_count": _optional_int(row.get("dependency_count")),
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
                "record_count": _optional_int(row.get("record_count")),
            }
            for row in checkpoints[:12]
            if isinstance(row, Mapping)
        ],
        "replica_routing": _safe_replica_routing(
            value.get("replica_routing")
            if isinstance(value.get("replica_routing"), Mapping)
            else {}
        ),
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "secrets_persisted": False,
    }


def _safe_replica_routing(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.runtime_canonical_replica_routing.v1",
            "enabled": False,
            "configured_replica_count": 0,
            "runtime_eligible_replica_count": 0,
            "comparable_replica_count": 0,
            "bounded_failover_attempt_count": 0,
            "selected_profile_sha256": "",
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
    return {
        "schema": str(
            value.get("schema")
            or "axio_fusion_api.runtime_canonical_replica_routing.v1"
        )[:120],
        "enabled": bool(value.get("enabled")),
        "runtime_canonical_identity_sha256": str(
            value.get("runtime_canonical_identity_sha256") or ""
        ),
        "configured_replica_count": _optional_int(
            value.get("configured_replica_count")
        ),
        "route_eligible_replica_count": _optional_int(
            value.get("route_eligible_replica_count")
        ),
        "runtime_eligible_replica_count": _optional_int(
            value.get("runtime_eligible_replica_count")
        ),
        "comparable_replica_count": _optional_int(
            value.get("comparable_replica_count")
        ),
        "bounded_failover_attempt_count": _optional_int(
            value.get("bounded_failover_attempt_count")
        ),
        "selected_profile_sha256": str(value.get("selected_profile_sha256") or ""),
        "ordered_attempt_profile_hashes": [str(item) for item in hashes if str(item)][:24],
        "selection_policy": str(value.get("selection_policy") or "")[:120],
        "selection_reason": str(value.get("selection_reason") or "")[:120],
        "route_pool_restricted": bool(value.get("route_pool_restricted")),
        "excluded_profile_hash_count": _optional_int(
            value.get("excluded_profile_hash_count")
        ),
        "circuit_open_replica_count": _optional_int(
            value.get("circuit_open_replica_count")
        ),
        "raw_canonical_identity_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
    }


def _safe_targeted_escalation_plan(value: Mapping[str, Any]) -> dict[str, Any]:
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
            "answer_claim_independence_requirement": _safe_answer_claim_independence_requirement({}),
            "model_selection": _safe_targeted_escalation_model_selection({}),
            "raw_prompt_persisted": False,
            "raw_candidate_text_persisted": False,
            "secrets_persisted": False,
        }
    subtasks = value.get("subtasks") if isinstance(value.get("subtasks"), list) else []
    counts = value.get("blocking_gap_counts") if isinstance(value.get("blocking_gap_counts"), Mapping) else {}
    return {
        "schema": value.get("schema") or "axio_fusion_api.targeted_escalation_plan.v1",
        "enabled": bool(value.get("enabled")),
        "triggered": bool(value.get("triggered")),
        "max_rounds": _optional_int(value.get("max_rounds")),
        "subtask_count": _optional_int(value.get("subtask_count")) or len(subtasks),
        "selected_subtask_count": _optional_int(value.get("selected_subtask_count")) or len(subtasks),
        "quality_gap_triggered": bool(value.get("quality_gap_triggered")),
        "blocking_gap_counts": {
            str(key)[:80]: _optional_int(item) or 0
            for key, item in counts.items()
            if str(key)
        },
        "requires_independent_answer_claim_verification": bool(value.get("requires_independent_answer_claim_verification")),
        "requires_cross_provider_verifier": bool(value.get("requires_cross_provider_verifier")),
        "requires_new_profile_verifier": bool(value.get("requires_new_profile_verifier")),
        "answer_claim_independence_requirement": _safe_answer_claim_independence_requirement(
            value.get("answer_claim_independence_requirement") if isinstance(value.get("answer_claim_independence_requirement"), Mapping) else {}
        ),
        "model_selection": _safe_targeted_escalation_model_selection(
            value.get("model_selection") if isinstance(value.get("model_selection"), Mapping) else {}
        ),
        "subtasks": [
            {
                "id": str(row.get("id") or "")[:120],
                "kind": str(row.get("kind") or "")[:80],
                "source": str(row.get("source") or "")[:80],
                "priority": _optional_int(row.get("priority")) or 0,
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


def _safe_answer_claim_independence_requirement(value: Mapping[str, Any]) -> dict[str, Any]:
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
        "largest_answer_claim_support_fraction": _optional_float(value.get("largest_answer_claim_support_fraction")) or 0.0,
        "largest_answer_claim_unique_profile_count": _optional_int(value.get("largest_answer_claim_unique_profile_count")) or 0,
        "largest_answer_claim_unique_provider_count": _optional_int(value.get("largest_answer_claim_unique_provider_count")) or 0,
        "largest_answer_claim_unique_canonical_model_count": _optional_int(
            value.get("largest_answer_claim_unique_canonical_model_count")
        )
        or 0,
        "candidate_provider_hash_count": _optional_int(value.get("candidate_provider_hash_count")) or 0,
        "required_unique_provider_count": _optional_int(value.get("required_unique_provider_count")) or 1,
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


def _safe_targeted_escalation_model_selection(value: Mapping[str, Any]) -> dict[str, Any]:
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
        "eligible_pool_count": _optional_int(value.get("eligible_pool_count")) or 0,
        "used_profile_hash_count": _optional_int(value.get("used_profile_hash_count")) or 0,
        "reason_codes": [
            str(item)[:120]
            for item in value.get("reason_codes", [])
            if str(item)
        ][:12] if isinstance(value.get("reason_codes"), list) else [],
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
    }


def _safe_tool_execution(value: Mapping[str, Any]) -> dict[str, Any]:
    receipts = value.get("result_receipts") if isinstance(value.get("result_receipts"), list) else []
    return {
        "executed": bool(value.get("executed")),
        "requested_call_count": _optional_int(value.get("requested_call_count")) or 0,
        "executed_or_blocked_call_count": _optional_int(value.get("executed_or_blocked_call_count")) or 0,
        "success_count": _optional_int(value.get("success_count")) or 0,
        "blocked_count": _optional_int(value.get("blocked_count")) or 0,
        "failed_count": _optional_int(value.get("failed_count")) or 0,
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
            for row in receipts[:16]
            if isinstance(row, Mapping)
        ],
        "raw_tool_arguments_persisted": False,
        "raw_tool_result_persisted": False,
        "raw_tool_schema_persisted": False,
    }


def _safe_judge(value: Mapping[str, Any]) -> dict[str, Any]:
    ranked = value.get("ranked_candidates") if isinstance(value.get("ranked_candidates"), list) else []
    answer_claim_clusters = (
        value.get("answer_claim_clusters")
        if isinstance(value.get("answer_claim_clusters"), list)
        else []
    )
    largest_answer_claim_cluster = (
        answer_claim_clusters[0]
        if answer_claim_clusters and isinstance(answer_claim_clusters[0], Mapping)
        else {}
    )
    coverage = value.get("coverage_summary") if isinstance(value.get("coverage_summary"), Mapping) else {}
    calibration = value.get("confidence_calibration_summary") if isinstance(value.get("confidence_calibration_summary"), Mapping) else {}
    candidate_provider_count = _optional_int(coverage.get("candidate_provider_hash_count")) or 0
    min_provider_count = 2 if candidate_provider_count >= 2 else 1
    return {
        "schema": value.get("schema") or "axio_fusion_api.structured_judge_result.v1",
        "not_majority_vote": bool(value.get("not_majority_vote")),
        "ready_for_synthesis": bool(value.get("ready_for_synthesis")),
        "judge_provider_call": bool(value.get("judge_provider_call")),
        "judge_provider_call_attempted": bool(value.get("judge_provider_call_attempted")),
        "judge_provider_call_count": _optional_int(value.get("judge_provider_call_count")),
        "judge_profile_sha256": str(value.get("judge_profile_sha256") or ""),
        "judge_replica_routing": _safe_replica_routing(
            value.get("judge_replica_routing")
            if isinstance(value.get("judge_replica_routing"), Mapping)
            else {}
        ),
        "provider_judge_sanitized": bool(value.get("provider_judge_sanitized")),
        "consensus_count": len(value.get("consensus", [])) if isinstance(value.get("consensus"), list) else 0,
        "contradiction_count": len(value.get("contradictions", [])) if isinstance(value.get("contradictions"), list) else 0,
        "missing_coverage_count": len(value.get("missing_coverage", [])) if isinstance(value.get("missing_coverage"), list) else 0,
        "follow_up_task_count": len(value.get("follow_up_tasks", [])) if isinstance(value.get("follow_up_tasks"), list) else 0,
        "answer_claim_cluster_count": len(answer_claim_clusters),
        "largest_answer_claim_cluster_size": _optional_int(largest_answer_claim_cluster.get("candidate_count")),
        "largest_answer_claim_support_fraction": _optional_float(largest_answer_claim_cluster.get("support_fraction")),
        "largest_answer_claim_unique_profile_count": _optional_int(largest_answer_claim_cluster.get("unique_profile_count")),
        "largest_answer_claim_unique_provider_count": _optional_int(largest_answer_claim_cluster.get("unique_provider_count")),
        "largest_answer_claim_unique_canonical_model_count": _optional_int(
            largest_answer_claim_cluster.get("unique_canonical_model_count")
        ),
        "answer_claim_consensus_detected": (_optional_int(largest_answer_claim_cluster.get("candidate_count")) or 0) >= 2,
        "answer_claim_independent_consensus_detected": (
            (_optional_int(largest_answer_claim_cluster.get("candidate_count")) or 0) >= 2
            and (_optional_int(largest_answer_claim_cluster.get("unique_profile_count")) or 0) >= 2
            and (
                _optional_int(
                    largest_answer_claim_cluster.get("unique_canonical_model_count")
                )
                or 0
            ) >= 2
            and (_optional_int(largest_answer_claim_cluster.get("unique_provider_count")) or 0) >= min_provider_count
        ),
        "largest_answer_claim_fingerprint_sha256": str(largest_answer_claim_cluster.get("answer_claim_fingerprint_sha256") or ""),
        "largest_answer_claim_equivalence_type": str(largest_answer_claim_cluster.get("answer_claim_equivalence_type") or "")[:80],
        "confidence_calibration_summary": _safe_judge_confidence_calibration_summary(calibration),
        "coverage_summary": _safe_judge_coverage_summary(coverage),
        "ranked_candidate_receipts": [
            {
                "candidate_id": str(row.get("candidate_id") or ""),
                "profile_id_sha256": str(row.get("profile_id_sha256") or sha256_text(str(row.get("profile_id") or ""))),
                "score": _optional_float(row.get("score")),
                "calibrated_confidence": _optional_float(row.get("calibrated_confidence")),
                "confidence_calibration_delta": _optional_float(row.get("confidence_calibration_delta")),
                "answer_claim_support_fraction": _optional_float(row.get("answer_claim_support_fraction")),
            }
            for row in ranked[:24]
            if isinstance(row, Mapping)
        ],
        "raw_candidate_text_persisted": False,
    }


def _safe_judge_confidence_calibration_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.local_judge_confidence_calibration_summary.v1",
            "candidate_count": 0,
            "raw_candidate_text_persisted": False,
        }
    top_reasons = value.get("top_reason_counts") if isinstance(value.get("top_reason_counts"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.local_judge_confidence_calibration_summary.v1",
        "candidate_count": _optional_int(value.get("candidate_count")),
        "average_raw_confidence": _optional_float(value.get("average_raw_confidence")),
        "average_calibrated_confidence": _optional_float(value.get("average_calibrated_confidence")),
        "average_calibration_delta": _optional_float(value.get("average_calibration_delta")),
        "min_calibrated_confidence": _optional_float(value.get("min_calibrated_confidence")),
        "max_calibrated_confidence": _optional_float(value.get("max_calibrated_confidence")),
        "overconfidence_risk_count": _optional_int(value.get("overconfidence_risk_count")),
        "overconfidence_risk_rate": _optional_float(value.get("overconfidence_risk_rate")),
        "penalty_candidate_count": _optional_int(value.get("penalty_candidate_count")),
        "credit_candidate_count": _optional_int(value.get("credit_candidate_count")),
        "top_reason_counts": [
            {
                "reason": str(row.get("reason") or "")[:120],
                "count": _optional_int(row.get("count")) or 0,
            }
            for row in top_reasons[:12]
            if isinstance(row, Mapping)
        ],
        "raw_candidate_text_persisted": False,
        "raw_reasoning_summary_persisted": False,
    }


def _safe_judge_coverage_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {
            "schema": "axio_fusion_api.local_judge_coverage_summary.v1",
            "candidate_count": 0,
            "requires_source_grounding": False,
            "has_source_grounding_evidence": False,
            "requires_vertical_domain_guardrails": False,
            "raw_candidate_text_persisted": False,
        }
    return {
        "schema": value.get("schema") or "axio_fusion_api.local_judge_coverage_summary.v1",
        "candidate_count": _optional_int(value.get("candidate_count")),
        "factuality_signal": bool(value.get("factuality_signal")),
        "vertical_domain_signal_count": _optional_int(value.get("vertical_domain_signal_count")),
        "requires_source_grounding": bool(value.get("requires_source_grounding")),
        "has_source_grounding_evidence": bool(value.get("has_source_grounding_evidence")),
        "source_grounding_evidence_count": _optional_int(value.get("source_grounding_evidence_count")),
        "requires_vertical_domain_guardrails": bool(value.get("requires_vertical_domain_guardrails")),
        "candidate_profile_hash_count": _optional_int(value.get("candidate_profile_hash_count")),
        "candidate_provider_hash_count": _optional_int(value.get("candidate_provider_hash_count")),
        "candidate_canonical_model_hash_count": _optional_int(
            value.get("candidate_canonical_model_hash_count")
        ),
        "largest_answer_claim_unique_profile_count": _optional_int(value.get("largest_answer_claim_unique_profile_count")),
        "largest_answer_claim_unique_provider_count": _optional_int(value.get("largest_answer_claim_unique_provider_count")),
        "largest_answer_claim_unique_canonical_model_count": _optional_int(
            value.get("largest_answer_claim_unique_canonical_model_count")
        ),
        "answer_claim_independent_consensus_detected": bool(value.get("answer_claim_independent_consensus_detected")),
        "factuality_dag_node_count": _optional_int(value.get("factuality_dag_node_count")),
        "factuality_dag_nodes_covered_count": _optional_int(value.get("factuality_dag_nodes_covered_count")),
        "factuality_source_node_count": _optional_int(value.get("factuality_source_node_count")),
        "factuality_source_nodes_covered_count": _optional_int(value.get("factuality_source_nodes_covered_count")),
        "factuality_dag_covered_fraction": _optional_float(value.get("factuality_dag_covered_fraction")),
        "vertical_domain_guardrail_node_count": _optional_int(value.get("vertical_domain_guardrail_node_count")),
        "vertical_domain_guardrail_nodes_covered_count": _optional_int(value.get("vertical_domain_guardrail_nodes_covered_count")),
        "vertical_domain_guardrail_covered_fraction": _optional_float(value.get("vertical_domain_guardrail_covered_fraction")),
        "vertical_domain_dag_node_count": _optional_int(value.get("vertical_domain_dag_node_count")),
        "vertical_domain_dag_nodes_covered_count": _optional_int(value.get("vertical_domain_dag_nodes_covered_count")),
        "vertical_domain_dag_covered_fraction": _optional_float(value.get("vertical_domain_dag_covered_fraction")),
        "raw_candidate_text_persisted": False,
    }


def _safe_synthesis_compression(value: Mapping[str, Any]) -> dict[str, Any]:
    omitted = value.get("omitted_candidate_receipts") if isinstance(value.get("omitted_candidate_receipts"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.synthesis_candidate_compression.v1",
        "enabled": bool(value.get("enabled")),
        "max_full_candidate_count": _optional_int(value.get("max_full_candidate_count")),
        "full_candidate_count": _optional_int(value.get("full_candidate_count")),
        "omitted_candidate_count": _optional_int(value.get("omitted_candidate_count")),
        "synthesizer_replica_routing": _safe_replica_routing(
            value.get("synthesizer_replica_routing")
            if isinstance(value.get("synthesizer_replica_routing"), Mapping)
            else {}
        ),
        "omitted_candidate_receipts": [
            {
                "candidate_id": str(row.get("candidate_id") or ""),
                "answer_sha256": str(row.get("answer_sha256") or ""),
                "answer_char_count": _optional_int(row.get("answer_char_count")),
                "confidence": _optional_float(row.get("confidence")),
                "reasoning_step_count": _optional_int(row.get("reasoning_step_count")),
                "reasoning_summary_sha256": str(row.get("reasoning_summary_sha256") or ""),
                "evidence_count": _optional_int(row.get("evidence_count")),
                "uncertainty_count": _optional_int(row.get("uncertainty_count")),
                "standardization": _safe_candidate_standardization(row.get("standardization") if isinstance(row.get("standardization"), Mapping) else {}),
                "task_execution": _safe_candidate_task_execution(row.get("task_execution") if isinstance(row.get("task_execution"), Mapping) else {}),
                "escalation_plan": _safe_targeted_escalation_plan(row.get("escalation_plan") if isinstance(row.get("escalation_plan"), Mapping) else {}),
                "raw_reasoning_summary_persisted": False,
                "raw_candidate_text_persisted": False,
            }
            for row in omitted[:24]
            if isinstance(row, Mapping)
        ],
        "raw_candidate_text_persisted": False,
    }


def _safe_early_exit(value: Mapping[str, Any]) -> dict[str, Any]:
    blocking = value.get("blocking_field_counts") if isinstance(value.get("blocking_field_counts"), Mapping) else {}
    thresholds = value.get("thresholds") if isinstance(value.get("thresholds"), Mapping) else {}
    claim_consensus = value.get("answer_claim_consensus") if isinstance(value.get("answer_claim_consensus"), Mapping) else {}
    return {
        "schema": value.get("schema") or "axio_fusion_api.early_exit_decision.v1",
        "enabled": bool(value.get("enabled")),
        "triggered": bool(value.get("triggered")),
        "reason": str(value.get("reason") or ""),
        "blocked_by_hermes_acting_aggregator": bool(
            value.get("blocked_by_hermes_acting_aggregator")
        ),
        "candidate_count": _optional_int(value.get("candidate_count")),
        "min_pairwise_similarity": _optional_float(value.get("min_pairwise_similarity")),
        "best_candidate_id": str(value.get("best_candidate_id") or ""),
        "best_candidate_answer_sha256": str(value.get("best_candidate_answer_sha256") or ""),
        "best_candidate_confidence": _optional_float(value.get("best_candidate_confidence")),
        "best_candidate_calibrated_confidence": _optional_float(value.get("best_candidate_calibrated_confidence")),
        "best_ranked_score": _optional_float(value.get("best_ranked_score")),
        "thresholds": {
            "quality_target": _optional_float(thresholds.get("quality_target")),
            "min_pairwise_similarity": _optional_float(thresholds.get("min_pairwise_similarity")),
            "min_ranked_score": _optional_float(thresholds.get("min_ranked_score")),
            "min_candidate_confidence": _optional_float(thresholds.get("min_candidate_confidence")),
            "min_answer_claim_support_fraction": _optional_float(thresholds.get("min_answer_claim_support_fraction")),
            "min_answer_claim_cluster_size": _optional_int(thresholds.get("min_answer_claim_cluster_size")),
        },
        "answer_claim_consensus": {
            "schema": claim_consensus.get("schema") or "axio_fusion_api.early_exit_answer_claim_consensus.v1",
            "evaluated": bool(claim_consensus.get("evaluated")),
            "passed": bool(claim_consensus.get("passed")),
            "detected": bool(claim_consensus.get("detected")),
            "independent_detected": bool(claim_consensus.get("independent_detected")),
            "largest_cluster_size": _optional_int(claim_consensus.get("largest_cluster_size")),
            "largest_support_fraction": _optional_float(claim_consensus.get("largest_support_fraction")),
            "largest_unique_profile_count": _optional_int(claim_consensus.get("largest_unique_profile_count")),
            "largest_unique_provider_count": _optional_int(claim_consensus.get("largest_unique_provider_count")),
            "min_cluster_size": _optional_int(claim_consensus.get("min_cluster_size")),
            "min_support_fraction": _optional_float(claim_consensus.get("min_support_fraction")),
            "min_unique_profile_count": _optional_int(claim_consensus.get("min_unique_profile_count")),
            "min_unique_provider_count": _optional_int(claim_consensus.get("min_unique_provider_count")),
            "largest_answer_claim_fingerprint_sha256": str(claim_consensus.get("largest_answer_claim_fingerprint_sha256") or ""),
            "largest_answer_claim_equivalence_type": str(claim_consensus.get("largest_answer_claim_equivalence_type") or "")[:80],
            "raw_answer_claim_persisted": False,
            "raw_candidate_text_persisted": False,
        },
        "has_explicit_evidence": bool(value.get("has_explicit_evidence")),
        "blocking_field_counts": {
            "contradictions": _optional_int(blocking.get("contradictions")),
            "missing_coverage": _optional_int(blocking.get("missing_coverage")),
            "collective_blind_spots": _optional_int(blocking.get("collective_blind_spots")),
        },
        "skipped_synthesizer": bool(value.get("skipped_synthesizer")),
        "raw_candidate_text_persisted": False,
    }


def _safe_runtime_fusion_stage_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": value.get("schema") or "axio_fusion_api.runtime_fusion_stage_outcome.v1",
        "fusion_requested": bool(value.get("fusion_requested")),
        "fusion_finalization_mode": str(value.get("fusion_finalization_mode") or "direct")[:80],
        "local_consensus_enabled": bool(value.get("local_consensus_enabled")),
        "local_consensus_finalized": bool(value.get("local_consensus_finalized")),
        "provider_judge_required": bool(value.get("provider_judge_required")),
        "provider_synthesizer_required": bool(value.get("provider_synthesizer_required")),
        "initial_complete_fusion_admitted": bool(value.get("initial_complete_fusion_admitted")),
        "required_min_candidate_count": _optional_int(value.get("required_min_candidate_count")),
        "minimum_viable_candidate_count": _optional_int(value.get("minimum_viable_candidate_count")),
        "completed_candidate_count": _optional_int(value.get("completed_candidate_count")),
        "hermes_reference_output_required": bool(
            value.get("hermes_reference_output_required")
        ),
        "hermes_reference_completed_count": _optional_int(
            value.get("hermes_reference_completed_count")
        ),
        "hermes_process_contract_required": bool(
            value.get("hermes_process_contract_required")
        ),
        "hermes_process_contract_completed": bool(
            value.get("hermes_process_contract_completed")
        ),
        "candidate_quorum_met": bool(value.get("candidate_quorum_met")),
        "viable_fusion_panel": bool(value.get("viable_fusion_panel")),
        "judge_provider_call_count": _optional_int(value.get("judge_provider_call_count")),
        "judge_output_accepted": bool(value.get("judge_output_accepted")),
        "synthesis_provider_call_count": _optional_int(value.get("synthesis_provider_call_count")),
        "synthesis_output_accepted": bool(value.get("synthesis_output_accepted")),
        "early_exit_finalized": bool(value.get("early_exit_finalized")),
        "mandatory_stage_reservation_enabled": bool(value.get("mandatory_stage_reservation_enabled")),
        "mandatory_stage_reservation_released_call_count": _optional_int(
            value.get("mandatory_stage_reservation_released_call_count")
        ),
        "mandatory_stages_finalized": bool(value.get("mandatory_stages_finalized")),
        "complete_admitted_fusion_finalized": bool(value.get("complete_admitted_fusion_finalized")),
        "execution_mode": str(value.get("execution_mode") or "")[:120],
        "runtime_degraded": bool(value.get("runtime_degraded")),
        "degradation_reason": str(value.get("degradation_reason") or "")[:120],
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _safe_hermes_moa_execution(value: Mapping[str, Any]) -> dict[str, Any]:
    """Persist only process counts and completion state, never advisory text."""

    return {
        "schema": str(
            value.get("schema") or "axio_fusion_api.hermes_moa_execution.v2"
        )[:120],
        "enabled": bool(value.get("enabled")),
        "reference_role_count": _optional_int(value.get("reference_role_count")),
        "reference_attempt_count": _optional_int(value.get("reference_attempt_count")),
        "reference_completed_count": _optional_int(value.get("reference_completed_count")),
        "reference_failed_or_empty_count": _optional_int(
            value.get("reference_failed_or_empty_count")
        ),
        "partial_reference_context_used": bool(
            value.get("partial_reference_context_used")
        ),
        "feedback_reference_wave_attempt_count": _optional_int(
            value.get("feedback_reference_wave_attempt_count")
        ),
        "feedback_reference_wave_completed_count": _optional_int(
            value.get("feedback_reference_wave_completed_count")
        ),
        "feedback_reference_wave_failed_or_empty_count": _optional_int(
            value.get("feedback_reference_wave_failed_or_empty_count")
        ),
        "feedback_wave_enabled": bool(value.get("feedback_wave_enabled")),
        "feedback_reference_required": bool(
            value.get("feedback_reference_required")
        ),
        "feedback_reference_execution_present": bool(
            value.get("feedback_reference_execution_present")
        ),
        "feedback_reference_completed": bool(
            value.get("feedback_reference_completed")
        ),
        "feedback_stage_admission_status": str(
            value.get("feedback_stage_admission_status") or "not_required"
        )[:64],
        "feedback_stage_admission_blocked": bool(
            value.get("feedback_stage_admission_blocked")
        ),
        "feedback_stage_admitted": bool(value.get("feedback_stage_admitted")),
        "feedback_wave_triggered": bool(value.get("feedback_wave_triggered")),
        "process_round_count": _optional_int(value.get("process_round_count")),
        "rejudge_after_feedback_expected": bool(
            value.get("rejudge_after_feedback_expected")
        ),
        "rejudge_after_feedback_completed": bool(
            value.get("rejudge_after_feedback_completed")
        ),
        "aggregator_role": str(value.get("aggregator_role") or "")[:80],
        "judge_provider_call_count": _optional_int(
            value.get("judge_provider_call_count")
        ),
        "judge_completed_round_count": _optional_int(
            value.get("judge_completed_round_count")
        ),
        "judge_output_accepted": bool(value.get("judge_output_accepted")),
        "aggregator_provider_call_count": _optional_int(
            value.get("aggregator_provider_call_count")
        ),
        "aggregator_tool_call_count": _optional_int(
            value.get("aggregator_tool_call_count")
        ),
        "aggregator_required_to_own_final_answer": bool(
            value.get("aggregator_required_to_own_final_answer")
        ),
        "aggregator_output_accepted": bool(
            value.get("aggregator_output_accepted")
        ),
        "aggregator_owns_final_answer": bool(
            value.get("aggregator_owns_final_answer")
        ),
        "acting_aggregator": bool(value.get("acting_aggregator")),
        "process_contract_completed": bool(
            value.get("process_contract_completed")
        ),
        "reference_failures_are_nonfatal": bool(
            value.get("reference_failures_are_nonfatal")
        ),
        "recursion_blocked": bool(value.get("recursion_blocked")),
        "raw_reference_text_persisted": False,
        "raw_aggregator_text_persisted": False,
        "secrets_persisted": False,
    }


def _safe_response_cache_replay(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(
            value.get("schema") or "axio_fusion_api.response_cache_replay.v1"
        )[:120],
        "replayed": bool(value.get("replayed")),
        "origin_completion_receipt_sha256": str(
            value.get("origin_completion_receipt_sha256") or ""
        )[:64],
        "origin_completion_kind": str(
            value.get("origin_completion_kind") or ""
        )[:80],
        "origin_answer_sha256": str(value.get("origin_answer_sha256") or "")[:64],
        "exact_text_integrity_verified": bool(
            value.get("exact_text_integrity_verified")
        ),
        "origin_fusion_requested": bool(value.get("origin_fusion_requested")),
        "origin_complete_admitted_fusion_finalized": bool(
            value.get("origin_complete_admitted_fusion_finalized")
        ),
        "origin_runtime_degraded": bool(value.get("origin_runtime_degraded")),
        "origin_hermes_process_contract_required": bool(
            value.get("origin_hermes_process_contract_required")
        ),
        "origin_hermes_process_contract_completed": bool(
            value.get("origin_hermes_process_contract_completed")
        ),
        "process_executed_this_request": bool(
            value.get("process_executed_this_request")
        ),
        "provider_call_count_this_request": _optional_int(
            value.get("provider_call_count_this_request")
        ),
        "judge_provider_call_count_this_request": _optional_int(
            value.get("judge_provider_call_count_this_request")
        ),
        "synthesis_provider_call_count_this_request": _optional_int(
            value.get("synthesis_provider_call_count_this_request")
        ),
        "raw_prompt_persisted": False,
        "raw_cached_text_persisted_to_disk": False,
        "raw_origin_response_id_persisted": False,
        "secrets_persisted": False,
    }


def _safe_response_cache_origin_completion(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": str(
            value.get("schema")
            or "axio_fusion_api.response_cache_origin_completion.v1"
        )[:120],
        "cache_eligible": bool(value.get("cache_eligible")),
        "ineligible_reason_codes": [
            str(item)[:120]
            for item in (
                value.get("ineligible_reason_codes")
                if isinstance(value.get("ineligible_reason_codes"), list)
                else []
            )
            if str(item)
        ][:24],
        "completion_kind": str(value.get("completion_kind") or "")[:80],
        "origin_response_id_sha256": str(
            value.get("origin_response_id_sha256") or ""
        )[:64],
        "answer_sha256": str(value.get("answer_sha256") or "")[:64],
        "answer_char_count": _optional_int(value.get("answer_char_count")),
        "route_contract_sha256": str(
            value.get("route_contract_sha256") or ""
        )[:64],
        "provider_calls_recorded": bool(value.get("provider_calls_recorded")),
        "provider_call_count": _optional_int(value.get("provider_call_count")),
        "judge_provider_call_count": _optional_int(
            value.get("judge_provider_call_count")
        ),
        "synthesis_provider_call_count": _optional_int(
            value.get("synthesis_provider_call_count")
        ),
        "fusion_requested": bool(value.get("fusion_requested")),
        "complete_admitted_fusion_finalized": bool(
            value.get("complete_admitted_fusion_finalized")
        ),
        "runtime_degraded": bool(value.get("runtime_degraded")),
        "hermes_process_contract_required": bool(
            value.get("hermes_process_contract_required")
        ),
        "hermes_process_contract_completed": bool(
            value.get("hermes_process_contract_completed")
        ),
        "runtime_fusion_stage_outcome": _safe_runtime_fusion_stage_outcome(
            value.get("runtime_fusion_stage_outcome")
            if isinstance(value.get("runtime_fusion_stage_outcome"), Mapping)
            else {}
        ),
        "hermes_moa_execution": _safe_hermes_moa_execution(
            value.get("hermes_moa_execution")
            if isinstance(value.get("hermes_moa_execution"), Mapping)
            else {}
        ),
        "receipt_sha256": str(value.get("receipt_sha256") or "")[:64],
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "raw_profile_ids_persisted": False,
        "secrets_persisted": False,
    }


def _safe_panel_repair(value: Mapping[str, Any]) -> dict[str, Any]:
    candidates = value.get("repair_candidate_receipts") if isinstance(value.get("repair_candidate_receipts"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.panel_repair.v1",
        "enabled": bool(value.get("enabled")),
        "attempted": bool(value.get("attempted")),
        "required_min_candidate_count": _optional_int(value.get("required_min_candidate_count")),
        "completed_before": _optional_int(value.get("completed_before")),
        "repair_attempt_count": _optional_int(value.get("repair_attempt_count")),
        "completed_after": _optional_int(value.get("completed_after")),
        "success": bool(value.get("success")),
        "degraded_mode": bool(value.get("degraded_mode")),
        "blocked_reasons": [str(item)[:120] for item in value.get("blocked_reasons", [])[:24] if str(item)] if isinstance(value.get("blocked_reasons"), list) else [],
        "missing_required_roles_after": [str(item)[:80] for item in value.get("missing_required_roles_after", [])[:12] if str(item)] if isinstance(value.get("missing_required_roles_after"), list) else [],
        "attempted_profile_hashes": [str(item) for item in value.get("attempted_profile_hashes", [])[:24] if str(item)] if isinstance(value.get("attempted_profile_hashes"), list) else [],
        "attempted_provider_hashes": [str(item) for item in value.get("attempted_provider_hashes", [])[:24] if str(item)] if isinstance(value.get("attempted_provider_hashes"), list) else [],
        "repair_candidate_receipts": [
            {
                "candidate_id": str(row.get("candidate_id") or ""),
                "role": str(row.get("role") or ""),
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "provider_sha256": str(row.get("provider_sha256") or ""),
                "status": str(row.get("status") or ""),
                "error_type": str(row.get("error_type") or "")[:120],
                "answer_sha256": str(row.get("answer_sha256") or ""),
                "answer_char_count": _optional_int(row.get("answer_char_count")),
                "reasoning_step_count": _optional_int(row.get("reasoning_step_count")),
                "standardization": _safe_candidate_standardization(row.get("standardization") if isinstance(row.get("standardization"), Mapping) else {}),
                "task_execution": _safe_candidate_task_execution(row.get("task_execution") if isinstance(row.get("task_execution"), Mapping) else {}),
                "raw_profile_id_persisted": False,
                "raw_model_names_persisted": False,
                "raw_reasoning_summary_persisted": False,
                "raw_candidate_text_persisted": False,
            }
            for row in candidates[:24]
            if isinstance(row, Mapping)
        ],
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
        "raw_provider_error_persisted": False,
        "secrets_persisted": False,
    }


def _safe_runtime_guards(route_plan: Mapping[str, Any]) -> dict[str, Any]:
    guards = route_plan.get("runtime_guards") if isinstance(route_plan.get("runtime_guards"), Mapping) else {}
    return {
        "global_budget_lock": bool(guards.get("global_budget_lock")),
        "fusion_depth": _optional_int(guards.get("fusion_depth")),
        "max_fusion_depth": _optional_int(guards.get("max_fusion_depth")),
        "max_total_model_calls": _optional_int(guards.get("max_total_model_calls")),
        "caller_max_total_model_calls_explicit": bool(guards.get("caller_max_total_model_calls_explicit")),
        "initial_fusion_call_budget_checked": bool(guards.get("initial_fusion_call_budget_checked")),
        "initial_fusion_minimum_call_count": _optional_int(guards.get("initial_fusion_minimum_call_count")),
        "initial_fusion_planned_call_count": _optional_int(guards.get("initial_fusion_planned_call_count")),
        "initial_fusion_call_budget_sufficient": bool(guards.get("initial_fusion_call_budget_sufficient")),
        "initial_fusion_role_budget_constrained": bool(guards.get("initial_fusion_role_budget_constrained")),
        "initial_fusion_resource_budget_checked": bool(guards.get("initial_fusion_resource_budget_checked")),
        "initial_fusion_resource_budget_applicable": bool(guards.get("initial_fusion_resource_budget_applicable")),
        "initial_fusion_resource_budget_blocked": bool(guards.get("initial_fusion_resource_budget_blocked")),
        "initial_fusion_cost_estimate_known": bool(guards.get("initial_fusion_cost_estimate_known")),
        "initial_fusion_latency_estimate_known": bool(guards.get("initial_fusion_latency_estimate_known")),
        "mandatory_fusion_stage_call_reservation_enabled": bool(guards.get("mandatory_fusion_stage_call_reservation_enabled")),
        "mandatory_fusion_stage_reservation_roles": [
            str(role)[:80]
            for role in guards.get("mandatory_fusion_stage_reservation_roles", [])
            if str(role)
        ][:4] if isinstance(guards.get("mandatory_fusion_stage_reservation_roles"), list) else [],
        "mandatory_fusion_stage_reservation_policy": str(
            guards.get("mandatory_fusion_stage_reservation_policy") or ""
        )[:160],
        "cost_budget_enabled": bool(guards.get("cost_budget_enabled")),
        "max_cost_usd": _optional_float(guards.get("max_cost_usd")),
        "deadline_budget_enabled": bool(guards.get("deadline_budget_enabled")),
        "max_latency_ms": _optional_int(guards.get("max_latency_ms")),
        "quality_target": _optional_float(guards.get("quality_target")),
        "quality_target_applied": bool(guards.get("quality_target_applied")),
        "quality_pressure": _optional_float(guards.get("quality_pressure")),
        "fast_light_verify_requested": bool(guards.get("fast_light_verify_requested")),
        "fast_light_verify_active": bool(guards.get("fast_light_verify_active")),
        "min_judge_candidate_count": _optional_int(guards.get("min_judge_candidate_count")),
        "timeout_enforced": bool(guards.get("timeout_enforced")),
        "provider_fallback_enabled": bool(guards.get("provider_fallback_enabled")),
        "utility_based_fusion_admission_enabled": bool(guards.get("utility_based_fusion_admission_enabled")),
        "candidate_deduplication_enabled": bool(guards.get("candidate_deduplication_enabled")),
        "privacy_model_pool_filter_enabled": bool(guards.get("privacy_model_pool_filter_enabled")),
        "tool_role_isolation_enabled": bool(guards.get("tool_role_isolation_enabled")),
        "candidate_standardization_enabled": bool(guards.get("candidate_standardization_enabled")),
        "dag_role_execution_receipts_enabled": bool(guards.get("dag_role_execution_receipts_enabled")),
        "targeted_escalation_plan_enabled": bool(guards.get("targeted_escalation_plan_enabled")),
        "provider_context_window_budget_enabled": bool(guards.get("provider_context_window_budget_enabled")),
        "prompt_budget_receipts_recorded": bool(guards.get("prompt_budget_receipts_recorded")),
        "raw_budgeted_prompts_persisted": bool(guards.get("raw_budgeted_prompts_persisted")),
    }


def _safe_runtime_provider_telemetry(value: Mapping[str, Any]) -> dict[str, Any]:
    profiles = value.get("profiles") if isinstance(value.get("profiles"), list) else []
    safe_profiles = []
    for row in profiles[:128]:
        if not isinstance(row, Mapping):
            continue
        profile_hash = str(row.get("profile_id_sha256") or "")
        provider_hash = str(row.get("provider_sha256") or "")
        if not _looks_like_sha256(profile_hash) or not _looks_like_sha256(provider_hash):
            continue
        health = str(row.get("effective_health") or "unknown")
        if health not in {"unknown", "observed", "available", "degraded", "unavailable"}:
            health = "unknown"
        safe_profiles.append(
            {
                "profile_id_sha256": profile_hash,
                "provider_sha256": provider_hash,
                "observation_count": _bounded_nonnegative_int(row.get("observation_count")),
                "success_count": _bounded_nonnegative_int(row.get("success_count")),
                "failure_count": _bounded_nonnegative_int(row.get("failure_count")),
                "latency_sample_count": _bounded_nonnegative_int(row.get("latency_sample_count")),
                "observed_success_rate": _bounded_unit_float(row.get("observed_success_rate")),
                "effective_availability": _bounded_unit_float(row.get("effective_availability")),
                "effective_recent_success_rate": _bounded_unit_float(row.get("effective_recent_success_rate")),
                "effective_p50_latency_ms": _bounded_nonnegative_int(row.get("effective_p50_latency_ms")),
                "effective_p95_latency_ms": _bounded_nonnegative_int(row.get("effective_p95_latency_ms")),
                "effective_health": health,
                "calibration_applied": row.get("calibration_applied") is True,
                "latency_calibration_applied": row.get("latency_calibration_applied") is True,
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_model_name_persisted": False,
            }
        )
    safe_profiles.sort(key=lambda row: row["profile_id_sha256"])
    return {
        "schema": "axio_fusion_api.runtime_provider_telemetry_receipt.v1",
        "enabled": value.get("enabled") is True,
        "minimum_observation_count": _bounded_nonnegative_int(value.get("minimum_observation_count")),
        "latency_sample_limit_per_profile": _bounded_nonnegative_int(value.get("latency_sample_limit_per_profile")),
        "observed_profile_count": _bounded_nonnegative_int(value.get("observed_profile_count")),
        "observed_provider_hash_count": _bounded_nonnegative_int(value.get("observed_provider_hash_count")),
        "adapted_profile_count": _bounded_nonnegative_int(value.get("adapted_profile_count")),
        "profiles": safe_profiles,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def _safe_model_selection_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    panel = value.get("panel_diversity_receipt") if isinstance(value.get("panel_diversity_receipt"), Mapping) else {}
    role_coverage = value.get("role_coverage") if isinstance(value.get("role_coverage"), Mapping) else {}
    role_targets = value.get("role_targets") if isinstance(value.get("role_targets"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.model_selection_policy.v1",
        "score_first": bool(value.get("score_first")),
        "quality_target": _optional_float(value.get("quality_target")),
        "quality_target_applied": bool(value.get("quality_target_applied")),
        "quality_pressure": _optional_float(value.get("quality_pressure")),
        "provider_diversity_enabled": bool(value.get("provider_diversity_enabled")),
        "physical_profile_count_available": _optional_int(
            value.get("physical_profile_count_available")
        ),
        "canonical_model_count_available": _optional_int(
            value.get("canonical_model_count_available")
        ),
        "canonical_model_count_selected": _optional_int(
            value.get("canonical_model_count_selected")
        ),
        "canonical_duplicate_count_selected": _optional_int(
            value.get("canonical_duplicate_count_selected")
        ),
        "canonical_model_panel_deduplication_enabled": bool(
            value.get("canonical_model_panel_deduplication_enabled")
        ),
        "canonical_model_panel_deduplication_satisfied": bool(
            value.get("canonical_model_panel_deduplication_satisfied")
        ),
        "provider_count_available": _optional_int(value.get("provider_count_available")),
        "provider_count_target": _optional_int(value.get("provider_count_target")),
        "provider_count_selected": _optional_int(value.get("provider_count_selected")),
        "provider_diversity_satisfied": bool(value.get("provider_diversity_satisfied")),
        "diversity_min_relative_score": _optional_float(value.get("diversity_min_relative_score")),
        "error_correlation_aware_selection_enabled": bool(value.get("error_correlation_aware_selection_enabled")),
        "estimated_error_correlation": _optional_float(value.get("estimated_error_correlation")),
        "capability_complementarity": _optional_float(value.get("capability_complementarity")),
        "api_format_diversity": _optional_float(value.get("api_format_diversity")),
        "panel_diversity_receipt": _safe_panel_diversity_receipt(panel),
        "role_diversity_enabled": bool(value.get("role_diversity_enabled")),
        "role_target_count": len(role_targets),
        "role_coverage": _safe_role_coverage(role_coverage),
        "max_models": _optional_int(value.get("max_models")),
        "raw_prompt_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_panel_diversity_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": value.get("schema") or "axio_fusion_api.panel_diversity_receipt.v1",
        "selected_model_count": _optional_int(value.get("selected_model_count")),
        "canonical_model_count": _optional_int(value.get("canonical_model_count")),
        "canonical_duplicate_count": _optional_int(
            value.get("canonical_duplicate_count")
        ),
        "canonical_model_panel_deduplication_satisfied": bool(
            value.get("canonical_model_panel_deduplication_satisfied")
        ),
        "provider_count": _optional_int(value.get("provider_count")),
        "api_format_count": _optional_int(value.get("api_format_count")),
        "provider_diversity": _optional_float(value.get("provider_diversity")),
        "api_format_diversity": _optional_float(value.get("api_format_diversity")),
        "capability_coverage": _optional_float(value.get("capability_coverage")),
        "capability_complementarity": _optional_float(value.get("capability_complementarity")),
        "estimated_error_correlation": _optional_float(value.get("estimated_error_correlation")),
        "selection_goal": str(value.get("selection_goal") or "")[:160],
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_role_coverage(value: Mapping[str, Any]) -> dict[str, Any]:
    roles = value.get("roles") if isinstance(value.get("roles"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.role_coverage_summary.v1",
        "role_count": _optional_int(value.get("role_count")),
        "covered_role_count": _optional_int(value.get("covered_role_count")),
        "roles": [
            {
                "role": str(row.get("role") or "")[:80],
                "covered": bool(row.get("covered")),
                "best_fit_score": _optional_float(row.get("best_fit_score")),
                "best_profile_sha256": str(row.get("best_profile_sha256") or ""),
                "raw_profile_id_persisted": False,
            }
            for row in roles[:24]
            if isinstance(row, Mapping)
        ],
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_quality_diversity_archive(value: Mapping[str, Any]) -> dict[str, Any]:
    entries = value.get("entries") if isinstance(value.get("entries"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.quality_diversity_archive.v1",
        "enabled": bool(value.get("enabled")),
        "selection_kernel": str(value.get("selection_kernel") or "")[:120],
        "entry_count": _optional_int(value.get("entry_count")),
        "niche_count": _optional_int(value.get("niche_count")),
        "role_tag_count": _optional_int(value.get("role_tag_count")),
        "average_novelty_estimate": _optional_float(value.get("average_novelty_estimate")),
        "average_quality_estimate": _optional_float(value.get("average_quality_estimate")),
        "entries": [
            {
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "provider_sha256": str(row.get("provider_sha256") or ""),
                "runtime_canonical_identity_sha256": str(
                    row.get("runtime_canonical_identity_sha256") or ""
                ),
                "api_format": str(row.get("api_format") or "")[:40],
                "dominant_capability_axis": str(row.get("dominant_capability_axis") or "")[:80],
                "assigned_roles": [str(item)[:80] for item in row.get("assigned_roles", []) if str(item)][:6]
                if isinstance(row.get("assigned_roles"), list)
                else [],
                "quality_estimate": _optional_float(row.get("quality_estimate")),
                "novelty_estimate": _optional_float(row.get("novelty_estimate")),
                "niche_id_sha256": str(row.get("niche_id_sha256") or ""),
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_model_name_persisted": False,
            }
            for row in entries[:24]
            if isinstance(row, Mapping)
        ],
        "raw_prompt_persisted": False,
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_provider_routing_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    context_policy = value.get("context_transform_policy") if isinstance(value.get("context_transform_policy"), Mapping) else {}
    fallback_pool = value.get("fallback_pool") if isinstance(value.get("fallback_pool"), list) else []
    replica_groups = (
        value.get("canonical_replica_groups")
        if isinstance(value.get("canonical_replica_groups"), list)
        else []
    )
    return {
        "schema": value.get("schema") or "axio_fusion_api.provider_routing_policy.v1",
        "enabled": bool(value.get("enabled")),
        "kernel": str(value.get("kernel") or "")[:120],
        "fallback_enabled": bool(value.get("fallback_enabled")),
        "fallback_scope": str(value.get("fallback_scope") or "")[:120],
        "canonical_replica_routing_enabled": bool(
            value.get("canonical_replica_routing_enabled")
        ),
        "physical_profile_count": _optional_int(value.get("physical_profile_count")),
        "canonical_model_count": _optional_int(value.get("canonical_model_count")),
        "canonical_replica_group_count": _optional_int(
            value.get("canonical_replica_group_count")
        ),
        "same_canonical_model_failover_precedes_cross_model_fallback": bool(
            value.get("same_canonical_model_failover_precedes_cross_model_fallback")
        ),
        "fallback_pool_sorted_by": str(value.get("fallback_pool_sorted_by") or "")[:120],
        "sort_priorities": [str(item)[:80] for item in value.get("sort_priorities", []) if str(item)][:10]
        if isinstance(value.get("sort_priorities"), list)
        else [],
        "fallback_triggers": [str(item)[:100] for item in value.get("fallback_triggers", []) if str(item)][:12]
        if isinstance(value.get("fallback_triggers"), list)
        else [],
        "context_transform_policy": {
            "provider_context_window_budget_enabled": bool(context_policy.get("provider_context_window_budget_enabled")),
            "compress_lower_ranked_candidates_before_synthesis": bool(context_policy.get("compress_lower_ranked_candidates_before_synthesis")),
            "middle_out_style_truncation_allowed_only_for_internal_candidate_packets": bool(
                context_policy.get("middle_out_style_truncation_allowed_only_for_internal_candidate_packets")
            ),
        },
        "fallback_pool_count": _optional_int(value.get("fallback_pool_count")),
        "fallback_pool_receipts": [
            {
                "fallback_rank": _optional_int(row.get("fallback_rank")),
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "provider_sha256": str(row.get("provider_sha256") or ""),
                "runtime_canonical_identity_sha256": str(
                    row.get("runtime_canonical_identity_sha256") or ""
                ),
                "api_format": str(row.get("api_format") or "")[:40],
                "canonical_replica_rank": _optional_int(
                    row.get("canonical_replica_rank")
                ),
                "canonical_replica_count": _optional_int(
                    row.get("canonical_replica_count")
                ),
                "routing_score": _optional_float(row.get("routing_score")),
                "estimated_quality": _optional_float(row.get("estimated_quality")),
                "availability_score": _optional_float(row.get("availability_score")),
                "latency_score": _optional_float(row.get("latency_score")),
                "cost_score": _optional_float(row.get("cost_score")),
                "provider_diversity_score": _optional_float(row.get("provider_diversity_score")),
                "api_format_diversity_score": _optional_float(row.get("api_format_diversity_score")),
                "selected_in_primary_panel": row.get("selected_in_primary_panel") is True,
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_model_name_persisted": False,
            }
            for row in fallback_pool[:12]
            if isinstance(row, Mapping)
        ],
        "canonical_replica_group_receipts": [
            {
                "runtime_canonical_identity_sha256": str(
                    row.get("runtime_canonical_identity_sha256") or ""
                ),
                "replica_count": _optional_int(row.get("replica_count")),
                "provider_replica_count": _optional_int(
                    row.get("provider_replica_count")
                ),
                "api_format_count": _optional_int(row.get("api_format_count")),
                "profile_hashes": [
                    str(item) for item in row.get("profile_hashes", []) if str(item)
                ][:24]
                if isinstance(row.get("profile_hashes"), list)
                else [],
                "selected_panel_profile_hashes": [
                    str(item)
                    for item in row.get("selected_panel_profile_hashes", [])
                    if str(item)
                ][:12]
                if isinstance(row.get("selected_panel_profile_hashes"), list)
                else [],
                "raw_canonical_identity_persisted": False,
                "raw_profile_ids_persisted": False,
                "raw_provider_names_persisted": False,
                "raw_model_names_persisted": False,
            }
            for row in replica_groups[:24]
            if isinstance(row, Mapping)
        ],
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _safe_routing_policy_application(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project the active routing-policy decision into a durable safe trace."""

    directives = (
        value.get("context_directives")
        if isinstance(value.get("context_directives"), list)
        else []
    )
    allowed_directives = {
        "evidence_first",
        "independent_solution",
        "verify_assumptions",
        "tool_schema_strict",
        "uncertainty_calibration",
        "concise_synthesis",
    }
    safe_directives = [
        str(item)
        for item in directives
        if str(item) in allowed_directives
    ][:8]
    policy_id = _safe_sha256(value.get("policy_id_sha256"))
    bundle_digest = _safe_sha256(value.get("bundle_digest_sha256"))
    return {
        "schema": "axio_fusion_api.routing_policy_application.v1",
        "active": value.get("active") is True,
        "applied": value.get("applied") is True,
        "policy_id_sha256": policy_id,
        "bundle_digest_sha256": bundle_digest,
        "policy_version_sha256": bundle_digest or policy_id,
        "matched_rule_count": max(0, _optional_int(value.get("matched_rule_count")) or 0),
        "matched_rule_id_hashes": _safe_sha256_list(
            value.get("matched_rule_id_hashes"), limit=24
        ),
        "quality_target_floor": _bounded_unit_float(value.get("quality_target_floor")),
        "force_fusion": value.get("force_fusion") is True,
        "fast_light_verify": value.get("fast_light_verify") is True,
        "max_panel_models": _optional_int(value.get("max_panel_models")),
        "max_fusion_depth": _optional_int(value.get("max_fusion_depth")),
        "context_directive_count": len(safe_directives),
        "context_directives": safe_directives,
        "reason_codes": _safe_policy_reason_codes(value.get("reason_codes")),
        "raw_policy_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _safe_policy_reason_codes(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else []
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    safe = []
    for item in rows:
        text = str(item or "").strip().lower()
        if not text or len(text) > 120 or any(char not in allowed for char in text):
            continue
        if text not in safe:
            safe.append(text)
        if len(safe) >= 12:
            break
    return safe


def _safe_fusion_admission(value: Mapping[str, Any]) -> dict[str, Any]:
    direct = value.get("direct_candidate") if isinstance(value.get("direct_candidate"), Mapping) else {}
    fusion = value.get("fusion_candidate") if isinstance(value.get("fusion_candidate"), Mapping) else {}
    utility = value.get("utility_model") if isinstance(value.get("utility_model"), Mapping) else {}
    initial_call_plan = value.get("initial_fusion_call_plan") if isinstance(value.get("initial_fusion_call_plan"), Mapping) else {}
    initial_resource_admission = (
        value.get("initial_fusion_resource_admission")
        if isinstance(value.get("initial_fusion_resource_admission"), Mapping)
        else {}
    )
    return {
        "schema": value.get("schema") or "axio_fusion_api.fusion_admission.v1",
        "activated": bool(value.get("activated")),
        "fusion_finalization_mode": str(value.get("fusion_finalization_mode") or "direct")[:80],
        "decision_reason": str(value.get("decision_reason") or "")[:160],
        "blocked_reasons": [str(item)[:160] for item in value.get("blocked_reasons", [])[:12] if str(item)] if isinstance(value.get("blocked_reasons"), list) else [],
        "provider_plan_blocked_reasons": [
            str(item)[:160]
            for item in value.get("provider_plan_blocked_reasons", [])[:12]
            if str(item)
        ] if isinstance(value.get("provider_plan_blocked_reasons"), list) else [],
        "force_reasons": [str(item)[:160] for item in value.get("force_reasons", [])[:12] if str(item)] if isinstance(value.get("force_reasons"), list) else [],
        "threshold": _optional_float(value.get("threshold")),
        "threshold_passed": bool(value.get("threshold_passed")),
        "expected_quality_gain": _optional_float(value.get("expected_quality_gain")),
        "risk_reduction_credit": _optional_float(value.get("risk_reduction_credit")),
        "extra_cost_usd": _optional_float(value.get("extra_cost_usd")),
        "extra_latency_ms": _optional_float(value.get("extra_latency_ms")),
        "cost_penalty": _optional_float(value.get("cost_penalty")),
        "latency_penalty": _optional_float(value.get("latency_penalty")),
        "error_correlation_penalty": _optional_float(value.get("error_correlation_penalty")),
        "utility_score": _optional_float(value.get("utility_score")),
        "pricing_known": bool(value.get("pricing_known")),
        "latency_known": bool(value.get("latency_known")),
        "p95_latency_known": bool(value.get("p95_latency_known")),
        "direct_p95_estimated_latency_ms": _optional_float(
            value.get("direct_p95_estimated_latency_ms")
        ),
        "fusion_p95_estimated_latency_ms": _optional_float(
            value.get("fusion_p95_estimated_latency_ms")
        ),
        "p95_latency_multiplier_vs_single_model": _optional_float(
            value.get("p95_latency_multiplier_vs_single_model")
        ),
        "p95_latency_deadline_guard_blocked": bool(
            value.get("p95_latency_deadline_guard_blocked")
        ),
        "p95_latency_multiplier_guard_blocked": bool(
            value.get("p95_latency_multiplier_guard_blocked")
        ),
        "p95_latency_guard_blocked": bool(value.get("p95_latency_guard_blocked")),
        "latency_multiplier_guard": {
            "enabled": bool(
                value.get("latency_multiplier_guard", {}).get("enabled")
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else False
            ),
            "target_max_vs_single_model": _optional_float(
                value.get("latency_multiplier_guard", {}).get(
                    "target_max_vs_single_model"
                )
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else None
            ),
            "blocked": bool(
                value.get("latency_multiplier_guard", {}).get("blocked")
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else False
            ),
            "provider_plan_blocked": bool(
                value.get("latency_multiplier_guard", {}).get(
                    "provider_plan_blocked"
                )
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else False
            ),
            "p95_latency_known": bool(
                value.get("latency_multiplier_guard", {}).get("p95_latency_known")
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else False
            ),
            "p95_deadline_blocked": bool(
                value.get("latency_multiplier_guard", {}).get(
                    "p95_deadline_blocked"
                )
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else False
            ),
            "p95_multiplier_guard_blocked": bool(
                value.get("latency_multiplier_guard", {}).get(
                    "p95_multiplier_guard_blocked"
                )
                if isinstance(value.get("latency_multiplier_guard"), Mapping)
                else False
            ),
            "raw_profile_id_persisted": False,
        },
        "quality_target": _optional_float(value.get("quality_target")),
        "complexity": _optional_float(value.get("complexity")),
        "risk": _optional_float(value.get("risk")),
        "uncertainty": _optional_float(value.get("uncertainty")),
        "utility_model": {
            "objective": str(utility.get("objective") or "")[:160],
            "quality_weight": _optional_float(utility.get("quality_weight")),
            "cost_penalty_weight": _optional_float(utility.get("cost_penalty_weight")),
            "latency_penalty_weight": _optional_float(utility.get("latency_penalty_weight")),
            "error_correlation_penalty_weight": _optional_float(utility.get("error_correlation_penalty_weight")),
            "risk_reduction_weight": _optional_float(utility.get("risk_reduction_weight")),
            "raw_prompt_persisted": False,
        },
        "direct_candidate": {
            "profile_id_sha256": str(direct.get("profile_id_sha256") or ""),
            "provider_sha256": str(direct.get("provider_sha256") or ""),
            "expected_quality": _optional_float(direct.get("expected_quality")),
            "estimated_cost_usd": _optional_float(direct.get("estimated_cost_usd")),
            "estimated_latency_ms": _optional_float(direct.get("estimated_latency_ms")),
            "raw_profile_id_persisted": False,
        },
        "fusion_candidate": {
            "selected_model_count": _optional_int(fusion.get("selected_model_count")),
            "selected_profile_hashes": [str(item) for item in fusion.get("selected_profile_hashes", [])[:24] if str(item)] if isinstance(fusion.get("selected_profile_hashes"), list) else [],
            "selected_provider_hashes": [str(item) for item in fusion.get("selected_provider_hashes", [])[:24] if str(item)] if isinstance(fusion.get("selected_provider_hashes"), list) else [],
            "expected_quality": _optional_float(fusion.get("expected_quality")),
            "estimated_cost_usd": _optional_float(fusion.get("estimated_cost_usd")),
            "estimated_latency_ms": _optional_float(fusion.get("estimated_latency_ms")),
            "p95_estimated_latency_ms": _optional_float(
                fusion.get("p95_estimated_latency_ms")
            ),
            "provider_diversity": _optional_float(fusion.get("provider_diversity")),
            "capability_coverage": _optional_float(fusion.get("capability_coverage")),
            "capability_complementarity": _optional_float(fusion.get("capability_complementarity")),
            "estimated_error_correlation": _optional_float(fusion.get("estimated_error_correlation")),
            "judge_strength": _optional_float(fusion.get("judge_strength")),
            "raw_profile_id_persisted": False,
            "raw_model_names_persisted": False,
        },
        "initial_fusion_call_plan": {
            "schema": str(initial_call_plan.get("schema") or "axio_fusion_api.initial_fusion_call_plan.v1")[:120],
            "caller_max_total_model_calls_explicit": bool(initial_call_plan.get("caller_max_total_model_calls_explicit")),
            "max_total_model_calls": _optional_int(initial_call_plan.get("max_total_model_calls")),
            "full_expert_role_count": _optional_int(initial_call_plan.get("full_expert_role_count")),
            "mandatory_stage_call_count": _optional_int(initial_call_plan.get("mandatory_stage_call_count")),
            "configured_min_judge_candidate_count": _optional_int(initial_call_plan.get("configured_min_judge_candidate_count")),
            "minimum_expert_call_count": _optional_int(initial_call_plan.get("minimum_expert_call_count")),
            "minimum_complete_fusion_call_count": _optional_int(initial_call_plan.get("minimum_complete_fusion_call_count")),
            "full_initial_fusion_call_count": _optional_int(initial_call_plan.get("full_initial_fusion_call_count")),
            "available_expert_call_count": _optional_int(initial_call_plan.get("available_expert_call_count")),
            "planned_expert_role_count": _optional_int(initial_call_plan.get("planned_expert_role_count")),
            "planned_initial_fusion_call_count": _optional_int(initial_call_plan.get("planned_initial_fusion_call_count")),
            "has_complete_fusion_shape": bool(initial_call_plan.get("has_complete_fusion_shape")),
            "call_budget_meets_complete_floor": bool(initial_call_plan.get("call_budget_meets_complete_floor")),
            "complete_fusion_feasible": bool(initial_call_plan.get("complete_fusion_feasible")),
            "blocked_by_call_budget": bool(initial_call_plan.get("blocked_by_call_budget")),
            "role_budget_constrained": bool(initial_call_plan.get("role_budget_constrained")),
            "omitted_expert_roles": [
                str(item)[:80]
                for item in initial_call_plan.get("omitted_expert_roles", [])
                if str(item)
            ][:8] if isinstance(initial_call_plan.get("omitted_expert_roles"), list) else [],
            "judge_reserved": bool(initial_call_plan.get("judge_reserved")),
            "synthesizer_reserved": bool(initial_call_plan.get("synthesizer_reserved")),
            "raw_profile_id_persisted": False,
            "raw_model_names_persisted": False,
        },
        "initial_fusion_resource_admission": _safe_initial_fusion_resource_admission(
            initial_resource_admission
        ),
        "raw_prompt_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_initial_fusion_resource_admission(value: Mapping[str, Any]) -> dict[str, Any]:
    cost = value.get("cost") if isinstance(value.get("cost"), Mapping) else {}
    latency = value.get("latency") if isinstance(value.get("latency"), Mapping) else {}
    cost_execution = cost.get("execution") if isinstance(cost.get("execution"), Mapping) else {}
    latency_execution = latency.get("execution") if isinstance(latency.get("execution"), Mapping) else {}
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.initial_fusion_resource_admission.v1")[:120],
        "applicable": bool(value.get("applicable")),
        "complete_initial_fusion_shape": bool(value.get("complete_initial_fusion_shape")),
        "planned_initial_role_count": _optional_int(value.get("planned_initial_role_count")),
        "planned_initial_profile_count": _optional_int(value.get("planned_initial_profile_count")),
        "cost": {
            "known": bool(cost.get("known")),
            "estimated_total_cost_usd": _optional_float(cost.get("estimated_total_cost_usd")),
            "request_max_cost_usd": _optional_float(cost.get("request_max_cost_usd")),
            "within_request_budget": _optional_bool(cost.get("within_request_budget")),
            "blocked": bool(cost.get("blocked")),
            "execution": _safe_initial_fusion_cost_execution(cost_execution),
        },
        "latency": {
            "known": bool(latency.get("known")),
            "estimated_total_latency_ms": _optional_float(latency.get("estimated_total_latency_ms")),
            "request_max_latency_ms": _optional_int(latency.get("request_max_latency_ms")),
            "within_request_deadline": _optional_bool(latency.get("within_request_deadline")),
            "blocked": bool(latency.get("blocked")),
            "execution": _safe_initial_fusion_latency_execution(latency_execution),
        },
        "blocked": bool(value.get("blocked")),
        "blocked_reasons": [
            str(item)[:160]
            for item in value.get("blocked_reasons", [])
            if str(item)
        ][:8] if isinstance(value.get("blocked_reasons"), list) else [],
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_id_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_initial_fusion_cost_execution(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.initial_execution_cost_estimate.v1")[:120],
        "basis": str(value.get("basis") or "")[:160],
        "profile_count": _optional_int(value.get("profile_count")),
        "profile_hashes": [
            str(item) for item in value.get("profile_hashes", []) if str(item)
        ][:24] if isinstance(value.get("profile_hashes"), list) else [],
        "pricing_known": bool(value.get("pricing_known")),
        "estimated_input_tokens_per_expert": _optional_int(value.get("estimated_input_tokens_per_expert")),
        "role_call_count": _optional_int(value.get("role_call_count")),
        "estimated_total_cost_usd": _optional_float(value.get("estimated_total_cost_usd")),
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_initial_fusion_latency_execution(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.initial_execution_latency_estimate.v1")[:120],
        "basis": str(value.get("basis") or "")[:160],
        "expert_role_count": _optional_int(value.get("expert_role_count")),
        "expert_profile_hashes": [
            str(item) for item in value.get("expert_profile_hashes", []) if str(item)
        ][:24] if isinstance(value.get("expert_profile_hashes"), list) else [],
        "expert_parallel_slots": _optional_int(value.get("expert_parallel_slots")),
        "expert_wave_count": _optional_int(value.get("expert_wave_count")),
        "expert_phase_latency_ms": _optional_float(value.get("expert_phase_latency_ms")),
        "judge_included": bool(value.get("judge_included")),
        "judge_profile_sha256": str(value.get("judge_profile_sha256") or ""),
        "judge_latency_ms": _optional_float(value.get("judge_latency_ms")),
        "synthesizer_included": bool(value.get("synthesizer_included")),
        "synthesizer_profile_sha256": str(value.get("synthesizer_profile_sha256") or ""),
        "synthesis_latency_ms": _optional_float(value.get("synthesis_latency_ms")),
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_budget_lock(value: Mapping[str, Any]) -> dict[str, Any]:
    skipped = value.get("skipped_calls") if isinstance(value.get("skipped_calls"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.call_budget_lock.v1",
        "max_total_model_calls": _optional_int(value.get("max_total_model_calls")),
        "used_model_call_count": _optional_int(value.get("used_model_call_count")),
        "remaining_model_call_count": _optional_int(value.get("remaining_model_call_count")),
        "unreserved_remaining_model_call_count": _optional_int(value.get("unreserved_remaining_model_call_count")),
        "skipped_call_count": _optional_int(value.get("skipped_call_count")),
        "mandatory_stage_reservation_enabled": bool(value.get("mandatory_stage_reservation_enabled")),
        "planned_mandatory_stage_call_count": _optional_int(value.get("planned_mandatory_stage_call_count")),
        "reserved_mandatory_stage_call_count": _optional_int(value.get("reserved_mandatory_stage_call_count")),
        "consumed_mandatory_stage_call_count": _optional_int(value.get("consumed_mandatory_stage_call_count")),
        "released_mandatory_stage_call_count": _optional_int(value.get("released_mandatory_stage_call_count")),
        "mandatory_stage_reservation_skip_count": _optional_int(value.get("mandatory_stage_reservation_skip_count")),
        "mandatory_stage_reservations": {
            str(role)[:80]: _optional_int(count) or 0
            for role, count in value.get("mandatory_stage_reservations", {}).items()
            if str(role)
        } if isinstance(value.get("mandatory_stage_reservations"), Mapping) else {},
        "mandatory_stage_reservation_release_receipts": [
            {
                "role": str(row.get("role") or "")[:80],
                "reason": str(row.get("reason") or "")[:120],
            }
            for row in value.get("mandatory_stage_reservation_release_receipts", [])[:12]
            if isinstance(row, Mapping)
        ] if isinstance(value.get("mandatory_stage_reservation_release_receipts"), list) else [],
        "enforced": bool(value.get("enforced")),
        "skipped_call_receipts": [
            {
                "kind": str(row.get("kind") or ""),
                "role": str(row.get("role") or ""),
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "reason": str(row.get("reason") or ""),
                "raw_profile_id_persisted": False,
            }
            for row in skipped[:24]
            if isinstance(row, Mapping)
        ],
        "raw_prompt_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _safe_cost_budget(value: Mapping[str, Any]) -> dict[str, Any]:
    skipped = value.get("skipped_calls") if isinstance(value.get("skipped_calls"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.cost_budget_lock.v1",
        "max_cost_usd": _optional_float(value.get("max_cost_usd")),
        "estimated_actual_cost_usd": _optional_float(value.get("estimated_actual_cost_usd")),
        "reserved_cost_usd": _optional_float(value.get("reserved_cost_usd")),
        "remaining_cost_usd": _optional_float(value.get("remaining_cost_usd")),
        "skipped_call_count": _optional_int(value.get("skipped_call_count")),
        "unpriced_call_count": _optional_int(value.get("unpriced_call_count")),
        "over_budget_after_commit_count": _optional_int(value.get("over_budget_after_commit_count")),
        "enforced": bool(value.get("enforced")),
        "skipped_call_receipts": [
            {
                "kind": str(row.get("kind") or ""),
                "role": str(row.get("role") or ""),
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "reason": str(row.get("reason") or ""),
                "estimated_cost_usd": _optional_float(row.get("estimated_cost_usd")),
                "raw_profile_id_persisted": False,
            }
            for row in skipped[:24]
            if isinstance(row, Mapping)
        ],
        "raw_prompt_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _safe_deadline_budget(value: Mapping[str, Any]) -> dict[str, Any]:
    skipped = value.get("skipped_calls") if isinstance(value.get("skipped_calls"), list) else []
    reservations = (
        value.get("mandatory_stage_deadline_reservations_ms")
        if isinstance(value.get("mandatory_stage_deadline_reservations_ms"), Mapping)
        else {}
    )
    return {
        "schema": value.get("schema") or "axio_fusion_api.deadline_budget.v1",
        "max_latency_ms": _optional_int(value.get("max_latency_ms")),
        "elapsed_ms": _optional_float(value.get("elapsed_ms")),
        "remaining_ms": _optional_float(value.get("remaining_ms")),
        "skipped_call_count": _optional_int(value.get("skipped_call_count")),
        "mandatory_stage_deadline_reservation_enabled": value.get(
            "mandatory_stage_deadline_reservation_enabled"
        ) is True,
        "mandatory_stage_deadline_reservations_ms": {
            str(role)[:80]: max(0, _optional_int(reservation) or 0)
            for role, reservation in reservations.items()
            if str(role)
        },
        "mandatory_stage_deadline_pending_ms": max(
            0,
            _optional_int(value.get("mandatory_stage_deadline_pending_ms")) or 0,
        ),
        "mandatory_stage_deadline_consumed_ms": max(
            0,
            _optional_int(value.get("mandatory_stage_deadline_consumed_ms")) or 0,
        ),
        "mandatory_stage_deadline_released_ms": max(
            0,
            _optional_int(value.get("mandatory_stage_deadline_released_ms")) or 0,
        ),
        "mandatory_stage_deadline_reservation_skip_count": max(
            0,
            _optional_int(
                value.get("mandatory_stage_deadline_reservation_skip_count")
            )
            or 0,
        ),
        "enforced": bool(value.get("enforced")),
        "skipped_call_receipts": [
            {
                "kind": str(row.get("kind") or ""),
                "role": str(row.get("role") or ""),
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "reason": str(row.get("reason") or ""),
                "raw_profile_id_persisted": False,
            }
            for row in skipped[:24]
            if isinstance(row, Mapping)
        ],
        "raw_prompt_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _safe_prompt_budget(value: Mapping[str, Any]) -> dict[str, Any]:
    receipts = value.get("receipts") if isinstance(value.get("receipts"), list) else []
    return {
        "schema": value.get("schema") or "axio_fusion_api.prompt_budget_ledger.v1",
        "receipt_count": _optional_int(value.get("receipt_count")) or len(receipts),
        "context_budget_enforced": bool(value.get("context_budget_enforced")),
        "truncated_call_count": _optional_int(value.get("truncated_call_count")) or 0,
        "receipts": [
            {
                "schema": row.get("schema") or "axio_fusion_api.provider_prompt_budget_receipt.v1",
                "kind": str(row.get("kind") or "")[:80],
                "role": str(row.get("role") or "")[:80],
                "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
                "provider_sha256": str(row.get("provider_sha256") or ""),
                "api_format": str(row.get("api_format") or ""),
                "context_tokens_known": bool(row.get("context_tokens_known")),
                "context_tokens": _optional_int(row.get("context_tokens")),
                "reserved_output_tokens": _optional_int(row.get("reserved_output_tokens")),
                "protocol_overhead_tokens": _optional_int(row.get("protocol_overhead_tokens")),
                "max_input_tokens": _optional_int(row.get("max_input_tokens")),
                "original_input_tokens": _optional_int(row.get("original_input_tokens")),
                "final_input_tokens": _optional_int(row.get("final_input_tokens")),
                "original_prompt_tokens": _optional_int(row.get("original_prompt_tokens")),
                "final_prompt_tokens": _optional_int(row.get("final_prompt_tokens")),
                "original_system_tokens": _optional_int(row.get("original_system_tokens")),
                "final_system_tokens": _optional_int(row.get("final_system_tokens")),
                "prompt_sha256_before": str(row.get("prompt_sha256_before") or ""),
                "prompt_sha256_after": str(row.get("prompt_sha256_after") or ""),
                "system_sha256_before": str(row.get("system_sha256_before") or ""),
                "system_sha256_after": str(row.get("system_sha256_after") or ""),
                "prompt_char_count_before": _optional_int(row.get("prompt_char_count_before")),
                "prompt_char_count_after": _optional_int(row.get("prompt_char_count_after")),
                "system_char_count_before": _optional_int(row.get("system_char_count_before")),
                "system_char_count_after": _optional_int(row.get("system_char_count_after")),
                "context_budget_enforced": bool(row.get("context_budget_enforced")),
                "prompt_truncated": bool(row.get("prompt_truncated")),
                "system_truncated": bool(row.get("system_truncated")),
                "input_budget_overflow_tokens": _optional_int(row.get("input_budget_overflow_tokens")) or 0,
                "raw_prompt_persisted": False,
                "raw_candidate_text_persisted": False,
                "raw_profile_id_persisted": False,
            }
            for row in receipts[:64]
            if isinstance(row, Mapping)
        ],
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _load_trace_rows(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
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


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bounded_nonnegative_int(value: Any) -> int:
    return max(0, min(1_000_000, _optional_int(value) or 0))


def _bounded_unit_float(value: Any) -> float | None:
    parsed = _optional_float(value)
    return None if parsed is None else max(0.0, min(1.0, parsed))


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _average(values: Sequence[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return None if not clean else round(sum(clean) / len(clean), 6)


def _rate(values: Sequence[bool | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(1 for value in clean if value) / len(clean), 6)


def _looks_like_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)
