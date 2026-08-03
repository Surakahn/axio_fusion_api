from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Mapping, Sequence

from .content_contract import content_parts_supported_by_format
from .hermes_moa import build_process_plan, safe_plan
from .latency_policy import PROVIDER_MAX_RESPONSE_LATENCY_MS, profile_latency_eligibility
from .policy_control import resolve_routing_policy
from .schemas import CAPABILITY_AXES, FusionRequest, ModelProfile, sha256_text, stable_json


FUSION_LATENCY_MULTIPLIER_GUARD = 3.0
FUSION_OPERATIONAL_LATENCY_TARGET = 2.5
LOCAL_CONSENSUS_OVERHEAD_MS = 75
# A single parallel redundancy seat is useful when a newly enrolled provider
# has no domain-quality evidence yet.  It does not add a serial stage, but it
# gives the local quorum one bounded failure cushion.
LOCAL_CONSENSUS_MAX_PANEL_SIZE = 4
EXPERT_QUALITY_REPLACEMENT_TOLERANCE = 0.12
ROUTE_COST_EXPERT_OUTPUT_TOKENS = 1024
# Keep this equal to the largest Hermes Judge wire cap. A lower estimate would
# admit a route whose real mandatory control packet can exceed its cost/time
# reservation; the Terra cap remains lower but is safely covered by this bound.
ROUTE_COST_JUDGE_OUTPUT_TOKENS = 1_024
ROUTE_COST_SYNTHESIZER_OUTPUT_TOKENS = 1024
FAST_DIRECT_BASE_SCORE_WEIGHT = 0.35
FAST_DIRECT_LATENCY_WEIGHT = 0.50
FAST_DIRECT_RELIABILITY_WEIGHT = 0.15
FAST_DIRECT_CASCADE_SAFETY_MARGIN_MS = 150
FAST_DIRECT_DEFAULT_DEADLINE_MS = 2500
FAST_DIRECT_DEADLINE_MULTIPLIER = 2.5
FAST_DIRECT_DEADLINE_MARGIN_MS = 500
FAST_DIRECT_MAX_DEADLINE_MS = 60_000
# A pre-Fusion role prior is allowed to open a bounded stage call when the
# operational capability vector is still the explicit neutral/unknown value.
# It never overwrites that vector or becomes benchmark evidence.  The margin
# above the ordinary stage floor keeps a weak/narrow prior out of Judge and
# Synthesizer admission.
SCREENING_STAGE_CAPABILITY_FLOOR = 0.55
SCREENING_SYNTHESIZER_DOMAIN_FLOOR = 0.45
ROUTING_POLICY_MAX_RULE_RECEIPTS = 24

# These roles are evidence-producing calls in the initial Fusion wave.  A
# short verifier is deliberately separate from full solver roles: it can add
# one bounded check, but it must never be promoted into a complete solver or a
# control-stage model.
_FULL_EVIDENCE_ROLE_NAMES = (
    "primary_solver",
    "independent_solver",
    "critic",
    "domain_specialist",
)
_NARROW_EVIDENCE_ROLE_NAMES = ("short_verification",)
_FUSION_EXPERT_ROLE_NAMES = (*_FULL_EVIDENCE_ROLE_NAMES, *_NARROW_EVIDENCE_ROLE_NAMES)


def analyze_request(request: FusionRequest) -> dict[str, Any]:
    text = " ".join([request.task_type, request.prompt, *request.requested_capabilities]).lower()
    fusion_plugin_requested = _fusion_plugin_requested(request)
    non_fusion_tools_declared = _non_fusion_tools_declared(request)
    quality_target = _quality_target(request)
    quality_pressure = _quality_pressure(quality_target)
    domains = []
    vertical_domain_signals: list[str] = []
    factuality_signal = any(
        token in text
        for token in (
            "hallucination",
            "hallucinated",
            "factual",
            "fact-check",
            "fact check",
            "truthful",
            "truthfulness",
            "grounded",
            "citation",
            "source",
            "evidence",
            "幻觉",
            "事实",
            "核查",
            "查证",
            "引用",
            "证据",
        )
    )
    if any(token in text for token in ("paper", "science", "biology", "physics", "chemistry", "research", "论文", "科研")):
        domains.append("science_knowledge")
    if any(token in text for token in ("python", "code", "bug", "repo", "program", "代码", "编程")):
        domains.append("code")
    if any(token in text for token in ("math", "proof", "equation", "calculate", "数学", "证明")):
        domains.append("math")
    if any(token in text for token in ("logic", "reason", "constraint", "推理", "逻辑")):
        domains.append("logic")
    if any(token in text for token in ("medical", "clinical", "medicine", "healthcare", "medqa", "usmle", "医疗", "医学", "临床")):
        domains.extend(["science_knowledge", "logic"])
        vertical_domain_signals.append("medical")
    if any(token in text for token in ("finance", "financial", "accounting", "valuation", "earnings", "risk model", "金融", "财务", "估值")):
        domains.extend(["math", "logic", "daily_work"])
        vertical_domain_signals.append("finance")
    if any(token in text for token in ("legal", "law", "contract", "statute", "regulation", "compliance", "法律", "法规", "合规", "合同")):
        domains.extend(["logic", "critique", "daily_work"])
        vertical_domain_signals.append("legal")
    if any(token in text for token in ("policy", "public policy", "policybench", "government", "governance", "政策", "治理", "监管")):
        domains.extend(["logic", "critique", "daily_work"])
        vertical_domain_signals.append("policy")
    if any(token in text for token in ("consulting", "strategy", "business case", "bizbench", "咨询", "战略", "商业")):
        domains.extend(["daily_work", "logic", "structured_output"])
        vertical_domain_signals.append("consulting")
    if factuality_signal:
        domains.extend(["critique", "logic"])
    if non_fusion_tools_declared or any(token in text for token in ("tool", "function", "agent", "workflow", "工具", "智能体")):
        domains.append("agentic_tool_calling")
    if any(ord(ch) > 127 for ch in request.prompt):
        domains.append("multilingual")
    if not domains:
        domains.append("daily_work")
    complexity = 0.18
    complexity += min(0.24, len(request.prompt) / 6000.0)
    complexity += 0.10 * max(0, len(domains) - 1)
    complexity += 0.10 if request.history else 0.0
    complexity += 0.08 if request.has_visual_input else 0.0
    complexity += 0.16 if non_fusion_tools_declared else 0.0
    complexity += 0.10 if fusion_plugin_requested else 0.0
    complexity += 0.08 * quality_pressure
    complexity += 0.18 if request.public_model == "axio-pro" else 0.06 if request.public_model == "axio-terra" else 0.0
    if any(token in text for token in ("analyze", "design", "prove", "debug", "review", "benchmark", "架构", "审查", "证明", "调研")):
        complexity += 0.16
    risk = 0.15
    if any(token in text for token in ("medical", "legal", "finance", "security", "production", "法律", "金融", "医疗", "安全", "生产")):
        risk += 0.35
    elif vertical_domain_signals:
        risk += 0.24
    if factuality_signal:
        risk += 0.10
    if "code" in domains or "agentic_tool_calling" in domains:
        risk += 0.16
    uncertainty = 0.20 + complexity * 0.45
    if fusion_plugin_requested:
        uncertainty += 0.08
    uncertainty += 0.06 * quality_pressure
    if factuality_signal:
        uncertainty += 0.12
    needs_current = any(token in text for token in ("latest", "current", "today", "now", "news", "最新", "今天", "当前"))
    if needs_current:
        uncertainty += 0.14
        domains.append("current_information")
    privacy_level = _privacy_level(request)
    return {
        "schema": "axio_fusion_api.request_analysis.v1",
        "task_type": request.task_type if request.task_type != "auto" else _task_type_from_domains(domains),
        "domains": list(dict.fromkeys(domains)),
        "complexity": round(max(0.0, min(1.0, complexity)), 4),
        "risk": round(max(0.0, min(1.0, risk)), 4),
        "uncertainty": round(max(0.0, min(1.0, uncertainty)), 4),
        "needs_current_information": needs_current,
        "needs_tools": bool(non_fusion_tools_declared),
        "has_visual_input": request.has_visual_input,
        "structured_output_requested": bool(request.structured_output),
        "factuality_signal": factuality_signal,
        "vertical_domain_signals": list(dict.fromkeys(vertical_domain_signals)),
        "fusion_plugin_requested": fusion_plugin_requested,
        "quality_target": quality_target,
        "quality_pressure": round(quality_pressure, 4),
        "decomposable": complexity >= 0.58 or len(domains) >= 3,
        "estimated_steps": 1 if complexity < 0.42 else 3 if complexity < 0.72 else 5,
        "privacy_level": privacy_level,
        "single_model_failure_loss": round(max(0.05, min(1.0, risk * 0.55 + complexity * 0.35)), 4),
        "expected_output_tokens": request.max_output_tokens or _expected_output_tokens(complexity),
        "raw_prompt_persisted": False,
    }


def build_route_plan(
    request: FusionRequest,
    profiles: Sequence[ModelProfile],
    *,
    routing_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = analyze_request(request)
    policy_application = resolve_routing_policy(
        routing_policy,
        public_model=request.public_model,
        task_type=str(analysis.get("task_type") or "unknown"),
        risk=float(analysis.get("risk") or 0.0),
    )
    analysis = _apply_routing_policy_to_analysis(analysis, policy_application)
    budget = _budget_for_request(
        request,
        analysis,
        routing_policy=policy_application,
    )
    role_blueprint = _role_blueprint(request, analysis, budget)
    eligible_profiles, privacy_policy = _apply_privacy_filter(request, profiles, analysis)
    scored = _rank_profiles(eligible_profiles, analysis)
    role_blueprint = _augment_pro_role_blueprint_for_screened_specialist(
        request,
        analysis,
        budget,
        scored,
        role_blueprint,
    )
    selected = _select_panel(request, analysis, budget, scored, role_blueprint=role_blueprint)
    # Expert seats come from the selected logical panel. Mandatory control
    # stages may use any other profile that already passed the pre-Fusion
    # screening handoff. Keeping this pool separate prevents a fast Judge or
    # Synthesizer from being counted as an independent evidence branch.
    stage_profile_pool = [
        profile
        for profile, _score in scored
        if _screening_role_contract_present(profile)
    ]
    # The latency contract is relative to the direct route the same request
    # would actually take, not necessarily to the Fusion primary role.  Build
    # that direct assignment first so mandatory-stage optimization and final
    # admission share the same single-model baseline.
    direct_roles = _role_assignments(
        request,
        analysis,
        selected,
        False,
        role_blueprint,
        budget=budget,
    )
    direct_latency_profile = _profile_for_assigned_role(
        direct_roles,
        selected,
        "primary_solver",
    )
    budget = _budget_with_direct_profile_deadline(
        request,
        budget,
        direct_latency_profile,
    )
    # Build both execution shapes before admission.  The latency gate must
    # price the same roles the runtime will actually schedule, rather than an
    # arbitrary prefix of the selected panel.  A caller-supplied call ceiling
    # is also part of admission: Fusion must reserve its initial expert,
    # Judge, and Synthesizer calls before it is allowed to claim the Fusion
    # path.  Extra expert roles may be trimmed, but a partial plan that is
    # guaranteed to skip its Judge or Synthesizer is never admitted.
    full_fusion_roles = _role_assignments(
        request,
        analysis,
        selected,
        True,
        role_blueprint,
        budget=budget,
        latency_baseline_profile=direct_latency_profile,
        stage_profile_pool=stage_profile_pool,
    )
    selected, full_fusion_roles, latency_constrained_panel = (
        _latency_constrained_fusion_panel(
            request=request,
            analysis=analysis,
            budget=budget,
            scored=scored,
            selected=selected,
            role_blueprint=role_blueprint,
            direct_profile=direct_latency_profile,
            initial_roles=full_fusion_roles,
            stage_profile_pool=stage_profile_pool,
        )
    )
    initial_fusion_call_plan = _initial_fusion_call_plan(budget, full_fusion_roles)
    budget = _budget_with_initial_fusion_call_plan(budget, initial_fusion_call_plan)
    planned_fusion_roles = (
        initial_fusion_call_plan["execution_roles"]
        if bool(initial_fusion_call_plan.get("complete_fusion_feasible"))
        else full_fusion_roles
    )
    initial_fusion_resource_admission = _initial_fusion_resource_admission(
        request,
        analysis,
        budget,
        selected,
        planned_fusion_roles=(
            initial_fusion_call_plan["execution_roles"]
            if bool(initial_fusion_call_plan.get("complete_fusion_feasible"))
            else []
        ),
        initial_fusion_call_plan=initial_fusion_call_plan,
        profile_pool=stage_profile_pool,
    )
    budget = _budget_with_initial_fusion_resource_admission(
        budget,
        initial_fusion_resource_admission,
    )
    local_consensus_panel, local_consensus_roles, local_consensus_plan = _local_consensus_plan(
        request=request,
        analysis=analysis,
        budget=budget,
        scored=scored,
        selected=selected,
        role_blueprint=role_blueprint,
        direct_profile=direct_latency_profile,
    )
    direct_role_gate = _role_gate_receipt(
        required_roles=["primary_solver"],
        roles=direct_roles,
        selected=selected,
        gate_name="direct",
    )
    provider_role_gate = _role_gate_receipt(
        required_roles=_provider_fusion_required_roles(
            request,
            analysis,
            budget,
            selected,
            role_blueprint,
            assigned_roles=planned_fusion_roles,
        ),
        roles=planned_fusion_roles,
        selected=selected,
        candidate_profiles=stage_profile_pool,
        gate_name="provider_fusion",
    )
    local_role_gate = _role_gate_receipt(
        required_roles=_local_consensus_required_roles(
            request,
            selected,
            role_blueprint,
            assigned_roles=local_consensus_roles,
        ),
        roles=local_consensus_roles,
        selected=local_consensus_panel or selected,
        gate_name="local_consensus",
    )
    role_gate = {
        "schema": "axio_fusion_api.route_role_gate.v1",
        "direct": direct_role_gate,
        "provider_fusion": provider_role_gate,
        "local_consensus": local_role_gate,
        "explicit_deny_is_hard_block": True,
        "streaming_admission_is_separate_from_role_admission": True,
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
    }
    fusion_admission = _fusion_admission(
        request,
        analysis,
        budget,
        scored,
        selected,
        planned_fusion_roles=planned_fusion_roles,
        direct_roles=direct_roles,
        initial_fusion_call_plan=initial_fusion_call_plan,
        initial_fusion_resource_admission=initial_fusion_resource_admission,
        local_consensus_plan=local_consensus_plan,
        direct_profile=direct_latency_profile,
        routing_policy=policy_application,
        role_gate=role_gate,
        stage_profile_pool=stage_profile_pool,
    )
    activated = bool(fusion_admission.get("activated"))
    finalization_mode = str(
        fusion_admission.get("fusion_finalization_mode") or "direct"
    )
    if activated and finalization_mode == "local_consensus":
        selected = list(local_consensus_panel)
        roles = list(local_consensus_roles)
    else:
        roles = planned_fusion_roles if activated else direct_roles
    budget = _budget_with_fusion_finalization_mode(
        budget,
        finalization_mode=finalization_mode,
        local_consensus_plan=local_consensus_plan,
    )
    search_policy = _deliberative_search_policy(request, analysis, budget, selected, activated, roles)
    quality_diversity_archive = _quality_diversity_archive(analysis, selected, roles)
    provider_routing_policy = _provider_routing_policy(request, analysis, budget, scored, selected)
    tool_policy = _tool_policy(request, roles)
    plugin_policy = _plugin_policy(request, tool_policy, activated)
    provider_stage_reservation_enabled = bool(
        activated
        and finalization_mode == "provider_judge_synthesis"
        and budget["initial_fusion_call_budget_sufficient"]
        and budget["initial_fusion_call_plan"].get("judge_reserved")
        and budget["initial_fusion_call_plan"].get("synthesizer_reserved")
    )
    hermes_moa_plan = safe_plan(
        build_process_plan(
            public_model=request.public_model,
            request_max_output_tokens=request.max_output_tokens,
            tools_declared=bool(request.tools),
            budget=budget,
            roles=roles,
            finalization_mode=finalization_mode,
        )
    )
    return {
        "schema": "axio_fusion_api.route_plan.v1",
        "public_model": request.public_model,
        "request": request.prompt_free_dict(),
        "request_analysis": analysis,
        "strategy": _strategy_id(
            request.public_model,
            activated,
            finalization_mode=finalization_mode,
        ),
        "budget": budget,
        "routing_policy": _safe_routing_policy_application(policy_application),
        "privacy_policy": privacy_policy,
        "fusion_admission": fusion_admission,
        "role_gate": role_gate,
        "latency_constrained_panel": latency_constrained_panel,
        "tool_policy": tool_policy,
        "plugin_policy": plugin_policy,
        "selected_models": [profile.safe_dict() for profile in selected],
        "model_selection_policy": _model_selection_policy(request, analysis, budget, scored, selected, role_blueprint),
        "quality_diversity_archive": quality_diversity_archive,
        "provider_routing_policy": provider_routing_policy,
        "deliberative_search_policy": search_policy,
        "ranked_candidates": [
            {"profile_id": profile.profile_id, "score": round(score, 4)}
            for profile, score in scored[:12]
        ],
        "roles": roles,
        "hermes_moa": hermes_moa_plan,
        "orchestration_scaffold": _orchestration_scaffold(
            request=request,
            analysis=analysis,
            budget=budget,
            activated=activated,
            roles=roles,
            role_blueprint=role_blueprint,
            search_policy=search_policy,
            finalization_mode=finalization_mode,
        ),
        "task_dag": _task_dag(activated, analysis, roles, finalization_mode=finalization_mode),
        "judge_contract": _judge_contract(activated, finalization_mode=finalization_mode),
        "targeted_escalation": {
            "enabled": activated and budget["max_depth"] > 0,
            "scope": "contested_or_missing_subtasks_only",
            "max_rounds": budget["max_depth"],
            "candidate_pool": _targeted_escalation_pool(analysis, scored, selected),
            "candidate_pool_source": "privacy_filtered_ranked_registry",
            "forbidden": ["rerun_full_panel_unbounded", "recursive_fusion_without_depth_guard"],
            "raw_prompt_persisted": False,
            "secrets_persisted": False,
        },
        "runtime_guards": {
            "global_budget_lock": True,
            "fusion_depth": request.policy.fusion_depth,
            "max_fusion_depth": request.policy.max_fusion_depth,
            "max_total_model_calls": budget["max_total_model_calls"],
            "caller_max_total_model_calls_explicit": budget["caller_max_total_model_calls_explicit"],
            "initial_fusion_call_budget_checked": True,
            "initial_fusion_minimum_call_count": budget["initial_fusion_minimum_call_count"],
            "initial_fusion_planned_call_count": budget["initial_fusion_planned_call_count"],
            "initial_fusion_call_budget_sufficient": budget["initial_fusion_call_budget_sufficient"],
            "initial_fusion_role_budget_constrained": budget["initial_fusion_role_budget_constrained"],
            "initial_fusion_resource_budget_checked": True,
            "initial_fusion_resource_budget_applicable": bool(
                budget["initial_fusion_resource_admission"].get("applicable")
            ),
            "initial_fusion_resource_budget_blocked": bool(
                budget["initial_fusion_resource_admission"].get("blocked")
            ),
            "initial_fusion_cost_estimate_known": bool(
                budget["initial_fusion_resource_admission"].get("cost", {}).get("known")
            ),
            "initial_fusion_latency_estimate_known": bool(
                budget["initial_fusion_resource_admission"].get("latency", {}).get("known")
            ),
            "mandatory_fusion_stage_call_reservation_enabled": provider_stage_reservation_enabled,
            "mandatory_fusion_stage_reservation_roles": ["judge", "synthesizer"]
            if provider_stage_reservation_enabled
            else [],
            "mandatory_fusion_stage_reservation_policy": "preserve_initial_judge_and_synthesizer_calls_from_optional_runtime_work",
            "cost_budget_enabled": True,
            "max_cost_usd": budget["max_cost_usd"],
            "deadline_budget_enabled": True,
            "max_latency_ms": budget["max_latency_ms"],
            "quality_target": budget["quality_target"],
            "quality_target_applied": budget["quality_target_applied"],
            "quality_pressure": budget["quality_pressure"],
            "routing_policy_active": policy_application.get("active") is True,
            "routing_policy_applied": policy_application.get("applied") is True,
            "routing_policy_context_directive_count": len(
                policy_application.get("context_directives", [])
                if isinstance(policy_application.get("context_directives"), list)
                else []
            ),
            "fast_light_verify_requested": bool(budget.get("fast_light_verify_requested")),
            "fast_light_verify_active": request.public_model == "axio-fast" and activated and bool(budget.get("fast_light_verify_requested")),
            "min_judge_candidate_count": budget["min_judge_candidate_count"],
            "timeout_enforced": True,
            "provider_fallback_enabled": True,
            "utility_based_fusion_admission_enabled": True,
            "fusion_finalization_mode": finalization_mode,
            "local_consensus_enabled": finalization_mode == "local_consensus",
            "provider_stage_calls_reserved": provider_stage_reservation_enabled,
            "provider_stage_call_roles": ["judge", "synthesizer"]
            if provider_stage_reservation_enabled
            else [],
            "local_consensus_provider_stage_calls_reserved": False,
            "candidate_deduplication_enabled": True,
            "privacy_model_pool_filter_enabled": True,
            "tool_role_isolation_enabled": True,
            "candidate_standardization_enabled": True,
            "dag_role_execution_receipts_enabled": True,
            "targeted_escalation_plan_enabled": True,
            "deliberative_search_policy_enabled": bool(search_policy.get("enabled")),
            "latency_multiplier_guard": search_policy.get("latency_multiplier_guard"),
            "latency_constrained_panel_optimization_enabled": True,
            "latency_constrained_panel_optimization_applied": bool(
                latency_constrained_panel.get("applied")
            ),
            "provider_context_window_budget_enabled": True,
            "prompt_budget_receipts_recorded": True,
            "raw_budgeted_prompts_persisted": False,
            "hermes_moa_enabled": bool(hermes_moa_plan.get("enabled")),
            "hermes_moa_reference_role_count": _safe_nonnegative_int(
                hermes_moa_plan.get("reference_role_count")
            ),
            "hermes_moa_reference_wave_parallel": bool(
                hermes_moa_plan.get("enabled")
                and hermes_moa_plan.get("stage_order", [])[0:1]
                == ["parallel_reference_advisory_wave"]
            ),
            "hermes_moa_reference_fanout_cadence": str(
                hermes_moa_plan.get("cache_policy", {}).get(
                    "reference_fanout_cadence"
                )
                if isinstance(hermes_moa_plan.get("cache_policy"), Mapping)
                else ""
            )[:80],
            "hermes_moa_slot_cognitive_budget_enabled": bool(
                isinstance(hermes_moa_plan.get("stage_cognitive_budget"), Mapping)
                and hermes_moa_plan["stage_cognitive_budget"].get("slots")
            ),
            "hermes_moa_structured_judge_max_tokens": _safe_nonnegative_int(
                hermes_moa_plan.get("stage_output_budget", {}).get(
                    "judge_max_tokens"
                )
                if isinstance(hermes_moa_plan.get("stage_output_budget"), Mapping)
                else 0
            ),
            "hermes_moa_aggregator_owns_final_answer": bool(
                hermes_moa_plan.get("aggregator_owns_final_answer")
            ),
            "hermes_moa_aggregator_tools_admitted": bool(
                hermes_moa_plan.get("aggregator_tools_admitted")
            ),
            "hermes_moa_feedback_wave_enabled": bool(
                hermes_moa_plan.get("process_round_policy", {}).get(
                    "feedback_reference_wave_enabled"
                )
                if isinstance(hermes_moa_plan.get("process_round_policy"), Mapping)
                else False
            ),
            "hermes_moa_feedback_max_rounds": _safe_nonnegative_int(
                hermes_moa_plan.get("process_round_policy", {}).get("max_feedback_rounds")
                if isinstance(hermes_moa_plan.get("process_round_policy"), Mapping)
                else 0
            ),
            "hermes_moa_recursion_guard_enabled": bool(
                isinstance(hermes_moa_plan.get("recursion_guard"), Mapping)
                and hermes_moa_plan["recursion_guard"].get("enabled") is True
            ),
        },
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _apply_routing_policy_to_analysis(
    analysis: Mapping[str, Any],
    routing_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply only resolved, bounded controls before budget admission."""

    updated = dict(analysis)
    if routing_policy.get("applied") is not True:
        updated["routing_policy_quality_target_floor_applied"] = False
        updated["routing_policy_fast_light_verify"] = False
        return updated
    floor = _policy_optional_float(routing_policy.get("quality_target_floor"))
    current_target = float(updated.get("quality_target") or 0.0)
    effective_target = max(current_target, floor or 0.0)
    updated["quality_target"] = round(min(1.0, effective_target), 4)
    updated["quality_pressure"] = round(
        _quality_pressure(float(updated["quality_target"])),
        4,
    )
    updated["routing_policy_quality_target_floor_applied"] = (
        floor is not None and effective_target > current_target
    )
    updated["routing_policy_fast_light_verify"] = (
        routing_policy.get("fast_light_verify") is True
    )
    updated["routing_policy_context_directive_count"] = len(
        routing_policy.get("context_directives", [])
        if isinstance(routing_policy.get("context_directives"), list)
        else []
    )
    return updated


def _safe_routing_policy_application(
    routing_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    routing_policy = routing_policy if isinstance(routing_policy, Mapping) else {}
    directives = routing_policy.get("context_directives")
    return {
        "schema": "axio_fusion_api.routing_policy_application.v1",
        "active": routing_policy.get("active") is True,
        "applied": routing_policy.get("applied") is True,
        "policy_id_sha256": str(routing_policy.get("policy_id_sha256") or ""),
        "bundle_digest_sha256": str(
            routing_policy.get("bundle_digest_sha256") or ""
        ),
        "matched_rule_count": max(0, _policy_optional_int(routing_policy.get("matched_rule_count")) or 0),
        "matched_rule_id_hashes": [
            str(item)
            for item in routing_policy.get("matched_rule_id_hashes", [])
            if isinstance(item, str)
        ][:ROUTING_POLICY_MAX_RULE_RECEIPTS],
        "quality_target_floor": _policy_optional_float(
            routing_policy.get("quality_target_floor")
        ),
        "force_fusion": routing_policy.get("force_fusion") is True,
        "fast_light_verify": routing_policy.get("fast_light_verify") is True,
        "max_panel_models": _policy_optional_int(
            routing_policy.get("max_panel_models")
        ),
        "max_fusion_depth": _policy_optional_int(
            routing_policy.get("max_fusion_depth")
        ),
        "context_directives": [
            str(item)
            for item in directives
            if str(item)
            in {
                "evidence_first",
                "independent_solution",
                "verify_assumptions",
                "tool_schema_strict",
                "uncertainty_calibration",
                "concise_synthesis",
            }
        ][:8]
        if isinstance(directives, list)
        else [],
        "reason_codes": [
            str(item)[:120]
            for item in routing_policy.get("reason_codes", [])
            if isinstance(item, str)
        ][:12],
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _policy_optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(1.0, parsed)), 4)


def _policy_optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _budget_for_request(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    *,
    routing_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    model = request.public_model
    complexity = float(analysis.get("complexity") or 0.0)
    quality_target = float(analysis.get("quality_target") or _quality_target(request))
    quality_pressure = _quality_pressure(quality_target)
    routing_policy = routing_policy if isinstance(routing_policy, Mapping) else {}
    plugin_summary = _fusion_plugin_directive_summary(request)
    fast_light_verify = _fast_light_verify_requested(request, analysis)
    if model == "axio-fast":
        max_models = 2 if fast_light_verify else 1
        max_depth = 0
        max_cost = 0.0015 if fast_light_verify else 0.001
        max_latency = 3500 if fast_light_verify else 2500
    elif model == "axio-pro":
        max_models = 6 if complexity >= 0.72 else 4
        max_depth, max_cost, max_latency = 2, 0.02, 25000
    else:
        max_models = 3 if complexity >= 0.42 else 2
        # Terra's initial Fusion plan may already consume nearly 3x a fast
        # direct call. Keep the 3x admission guard as the capability/latency
        # contract, but leave a bounded network-tail allowance so an admitted
        # plan is not cancelled at the exact p50 estimate before Judge or
        # Synthesis can run.
        max_depth, max_cost, max_latency = 1, 0.005, 15000
    if quality_pressure > 0.0 and model != "axio-fast":
        if quality_target >= 0.90:
            max_models = max(max_models, 4 if model == "axio-terra" else 5)
            max_depth = max(max_depth, 2)
        elif quality_target >= 0.82:
            max_models = max(max_models, 3)
            max_depth = max(max_depth, 1)
    if plugin_summary["fusion_plugin_requested"] and plugin_summary["analysis_model_count"] > 0:
        requested_panel = plugin_summary["analysis_model_count"] + (1 if plugin_summary["synthesis_model_configured"] else 0)
        max_models = max(max_models, min(8, max(2, requested_panel)))
    policy_panel_cap = _policy_optional_int(routing_policy.get("max_panel_models"))
    policy_depth_cap = _policy_optional_int(routing_policy.get("max_fusion_depth"))
    if policy_panel_cap is not None:
        max_models = min(max_models, policy_panel_cap)
    if policy_depth_cap is not None:
        max_depth = min(max_depth, policy_depth_cap)
    if request.policy.max_models:
        max_models = min(max_models, request.policy.max_models)
    if request.policy.max_depth is not None:
        max_depth = min(max_depth, request.policy.max_depth)
    if request.policy.max_cost_usd is not None:
        max_cost = min(max_cost, request.policy.max_cost_usd)
    if request.policy.max_latency_ms is not None:
        # A caller deadline is an upper bound for this request, while the
        # tier's implicit default is only an operating target. Do not let a
        # smaller internal default silently override an explicit but still
        # bounded caller deadline. Fast has a separate direct-cascade product
        # ceiling; Fusion tiers use the shared provider eligibility ceiling.
        deadline_ceiling_ms = (
            FAST_DIRECT_MAX_DEADLINE_MS
            if model == "axio-fast"
            else PROVIDER_MAX_RESPONSE_LATENCY_MS
        )
        max_latency = min(
            deadline_ceiling_ms,
            max(1, int(request.policy.max_latency_ms)),
        )
    # Judge and synthesis are part of every admitted Fusion route, including
    # the bounded fast light-verify path.  Fallback and escalation allowances
    # remain separate so the initial plan has an explicit call budget floor.
    fusion_stage_call_allowance = 2 if (model != "axio-fast" or fast_light_verify) else 0
    fallback_call_allowance = 1 if model == "axio-fast" else min(2, max(1, int(max_depth)))
    caller_max_total_model_calls_explicit = request.policy.max_total_model_calls is not None
    max_calls = request.policy.max_total_model_calls if caller_max_total_model_calls_explicit else (
        max_models + fusion_stage_call_allowance + max_depth + fallback_call_allowance
    )
    min_judge_candidate_count = 2 if (model != "axio-fast" or fast_light_verify) else 1
    if model != "axio-fast" and quality_target >= 0.90:
        min_judge_candidate_count = 3
    elif model != "axio-fast" and quality_target >= 0.82:
        min_judge_candidate_count = 2
    # The initial Fusion schedule has at most four expert roles
    # (primary/independent/critic/domain specialist).  Run that bounded set
    # concurrently whenever the tier admits Fusion: otherwise three equal-
    # latency experts plus a Judge and Synthesizer are structurally unable to
    # meet the 3x latency contract even though the executor can safely fan out
    # the independent work.  This is a concurrency cap, not an unbounded
    # recursion or provider-wide parallelism setting.
    max_parallel_experts = max(1, min(4, int(max_models)))
    # A caller may deliberately grant the direct Fast cascade two calls.  That
    # capacity is a real failure-recovery allowance, not an unbounded route
    # expansion, so retain it in the safe route receipt even when the caller
    # supplied the overall ceiling explicitly.
    if model == "axio-fast" and not fast_light_verify:
        effective_fallback_call_allowance = max(0, int(max_calls) - 1)
    else:
        effective_fallback_call_allowance = 0 if caller_max_total_model_calls_explicit else fallback_call_allowance
    return {
        "mode": model,
        "quality_target": quality_target,
        "quality_target_applied": quality_pressure > 0.0,
        "quality_pressure": round(quality_pressure, 4),
        "fast_light_verify_requested": fast_light_verify,
        "max_models": max(1, int(max_models)),
        "max_parallel_experts": max_parallel_experts,
        "max_depth": max(0, int(max_depth)),
        "max_total_model_calls": max(1, int(max_calls)),
        "caller_max_total_model_calls_explicit": caller_max_total_model_calls_explicit,
        "initial_fusion_stage_call_allowance": fusion_stage_call_allowance,
        "fallback_call_allowance": effective_fallback_call_allowance,
        "max_cost_usd": float(max_cost),
        "max_latency_ms": int(max_latency),
        "min_judge_candidate_count": min_judge_candidate_count,
        "rank_first_candidate_compression": True,
        "max_synthesis_candidates": min(2, max(1, int(max_models))),
        "early_exit_enabled": True,
        "fusion_plugin_requested_analysis_model_count": plugin_summary["analysis_model_count"],
        "fusion_plugin_panel_size_applied": min(max_models, max(0, plugin_summary["analysis_model_count"] + (1 if plugin_summary["synthesis_model_configured"] else 0))),
        "routing_policy_panel_cap": policy_panel_cap,
        "routing_policy_depth_cap": policy_depth_cap,
    }


def _budget_with_direct_profile_deadline(
    request: FusionRequest,
    budget: Mapping[str, Any],
    direct_profile: ModelProfile | None,
) -> dict[str, Any]:
    """Adapt an implicit tier deadline to the calibrated direct profile.

    A fixed tier ceiling is useful as a default, but it is not a valid
    universal provider SLA. A live probe can legitimately show a slower remote
    gateway, and the runtime must not cancel an admitted Fusion panel at the
    exact implicit default while the direct provider is still within its
    calibrated tail. Fast uses its tighter operating target; Terra and Pro use
    the measured direct p95 as the reference for the hard 3x upper bound.

    This is a timeout/admission allowance, not a promise that Fusion may spend
    that whole window.  The hard three-times latency comparison remains a
    separate measured execution gate.
    """

    updated = dict(budget)
    receipt = {
        "schema": "axio_fusion_api.direct_profile_deadline_adaptation.v1",
        "enabled": request.public_model == "axio-fast",
        "applied": False,
        "reason": "not_fast_route",
        "explicit_caller_deadline_preserved": request.policy.max_latency_ms is not None,
        "direct_profile_latency_known": False,
        "observed_latency_ms": None,
        "configured_deadline_ms": int(budget.get("max_latency_ms") or FAST_DIRECT_DEFAULT_DEADLINE_MS),
        "adapted_deadline_ms": int(budget.get("max_latency_ms") or FAST_DIRECT_DEFAULT_DEADLINE_MS),
        "raw_profile_id_persisted": False,
        "raw_model_name_persisted": False,
    }
    adaptive_models = {"axio-fast", "axio-terra", "axio-pro"}
    receipt["enabled"] = request.public_model in adaptive_models
    if request.public_model not in adaptive_models:
        updated["direct_profile_deadline_adaptation"] = receipt
        return updated
    if request.policy.max_latency_ms is not None:
        receipt["reason"] = "explicit_caller_deadline"
        updated["direct_profile_deadline_adaptation"] = receipt
        return updated
    if direct_profile is None:
        receipt["reason"] = "direct_profile_missing"
        updated["direct_profile_deadline_adaptation"] = receipt
        return updated
    observed = direct_profile.p95_latency_ms or direct_profile.p50_latency_ms
    observed_quantile = "p95" if direct_profile.p95_latency_ms is not None else "p50"
    if observed is None or float(observed) <= 0.0:
        receipt["reason"] = "direct_profile_latency_unknown"
        updated["direct_profile_deadline_adaptation"] = receipt
        return updated
    configured = max(
        FAST_DIRECT_DEFAULT_DEADLINE_MS,
        int(budget.get("max_latency_ms") or FAST_DIRECT_DEFAULT_DEADLINE_MS),
    )
    if request.public_model == "axio-fast":
        target_multiplier = FAST_DIRECT_DEADLINE_MULTIPLIER
        margin_ms = FAST_DIRECT_DEADLINE_MARGIN_MS
        reason = "calibrated_direct_profile_latency"
    else:
        target_multiplier = FUSION_LATENCY_MULTIPLIER_GUARD
        margin_ms = 0
        reason = "calibrated_direct_profile_p95_three_x_bound"
    adapted = min(
        FAST_DIRECT_MAX_DEADLINE_MS,
        max(
            configured,
            int(math.ceil(float(observed) * target_multiplier + margin_ms)),
        ),
    )
    receipt.update(
        {
            "applied": adapted != configured,
            "reason": reason,
            "direct_profile_latency_known": True,
            "observed_latency_ms": round(float(observed), 3),
            "observed_latency_quantile": observed_quantile,
            "target_latency_multiplier": target_multiplier,
            "deadline_margin_ms": margin_ms,
            "configured_deadline_ms": configured,
            "adapted_deadline_ms": adapted,
        }
    )
    updated["max_latency_ms"] = adapted
    updated["direct_profile_deadline_adaptation"] = receipt
    return updated


def _initial_fusion_call_plan(
    budget: Mapping[str, Any],
    full_roles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reserve a complete initial Fusion schedule under the call ceiling.

    A complete initial Fusion pass needs two independent expert candidates plus
    a Judge and Synthesizer.  When the ceiling can accommodate that floor but
    not every optional expert role, keep the primary and independent branches
    and trim later expert roles.  When it cannot accommodate the floor, the
    router must decline Fusion before runtime rather than silently exhausting
    the budget before its mandatory stages.
    """

    expert_role_names = set(_FUSION_EXPERT_ROLE_NAMES)
    expert_roles = [
        row
        for row in full_roles
        if isinstance(row, Mapping) and str(row.get("role") or "") in expert_role_names
    ]
    judge_role = next(
        (
            row
            for row in full_roles
            if isinstance(row, Mapping) and str(row.get("role") or "") == "judge"
        ),
        None,
    )
    synthesizer_role = next(
        (
            row
            for row in full_roles
            if isinstance(row, Mapping) and str(row.get("role") or "") == "synthesizer"
        ),
        None,
    )
    try:
        max_total_calls = max(1, int(budget.get("max_total_model_calls") or 1))
    except (TypeError, ValueError):
        max_total_calls = 1
    caller_cap_explicit = bool(budget.get("caller_max_total_model_calls_explicit"))
    mandatory_roles = [role for role in (judge_role, synthesizer_role) if role is not None]
    mandatory_stage_call_count = len(mandatory_roles)
    configured_min_candidates = max(
        1,
        int(budget.get("min_judge_candidate_count") or 2),
    )
    # Keep this aligned with ``_required_min_candidate_count`` at runtime.
    # High-quality requests may require three independently completed expert
    # candidates, while a smaller available expert shape can only require the
    # candidates it actually contains.
    minimum_expert_call_count = (
        max(2, min(configured_min_candidates, len(expert_roles)))
        if len(expert_roles) >= 2
        else len(expert_roles)
    )
    minimum_complete_fusion_call_count = minimum_expert_call_count + mandatory_stage_call_count
    has_complete_fusion_shape = (
        len(expert_roles) >= minimum_expert_call_count
        and judge_role is not None
        and synthesizer_role is not None
    )
    available_expert_call_count = max(0, max_total_calls - mandatory_stage_call_count)
    call_budget_meets_complete_floor = max_total_calls >= minimum_complete_fusion_call_count
    complete_fusion_feasible = bool(
        has_complete_fusion_shape and call_budget_meets_complete_floor
    )
    planned_expert_roles = (
        expert_roles[:available_expert_call_count]
        if complete_fusion_feasible
        else []
    )
    execution_roles = [*planned_expert_roles, *mandatory_roles] if complete_fusion_feasible else []
    full_initial_fusion_call_count = len(expert_roles) + mandatory_stage_call_count
    planned_initial_fusion_call_count = len(execution_roles)
    role_budget_constrained = bool(
        complete_fusion_feasible
        and planned_initial_fusion_call_count < full_initial_fusion_call_count
    )
    omitted_expert_roles = (
        expert_roles[len(planned_expert_roles) :]
        if complete_fusion_feasible
        else expert_roles
    )
    blocked_by_call_budget = bool(
        has_complete_fusion_shape and not call_budget_meets_complete_floor
    )
    return {
        "execution_roles": execution_roles,
        "caller_max_total_model_calls_explicit": caller_cap_explicit,
        "max_total_model_calls": max_total_calls,
        "full_expert_role_count": len(expert_roles),
        "mandatory_stage_call_count": mandatory_stage_call_count,
        "configured_min_judge_candidate_count": configured_min_candidates,
        "minimum_expert_call_count": minimum_expert_call_count,
        "minimum_complete_fusion_call_count": minimum_complete_fusion_call_count,
        "full_initial_fusion_call_count": full_initial_fusion_call_count,
        "available_expert_call_count": available_expert_call_count,
        "planned_expert_role_count": len(planned_expert_roles),
        "planned_initial_fusion_call_count": planned_initial_fusion_call_count,
        "has_complete_fusion_shape": has_complete_fusion_shape,
        "call_budget_meets_complete_floor": call_budget_meets_complete_floor,
        "complete_fusion_feasible": complete_fusion_feasible,
        "blocked_by_call_budget": blocked_by_call_budget,
        "role_budget_constrained": role_budget_constrained,
        "omitted_expert_roles": [
            str(role.get("role") or "")
            for role in omitted_expert_roles
            if str(role.get("role") or "")
        ],
        "judge_reserved": judge_role is not None,
        "synthesizer_reserved": synthesizer_role is not None,
    }


def _safe_initial_fusion_call_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.initial_fusion_call_plan.v1",
        "caller_max_total_model_calls_explicit": bool(value.get("caller_max_total_model_calls_explicit")),
        "max_total_model_calls": max(1, int(value.get("max_total_model_calls") or 1)),
        "full_expert_role_count": max(0, int(value.get("full_expert_role_count") or 0)),
        "mandatory_stage_call_count": max(0, int(value.get("mandatory_stage_call_count") or 0)),
        "configured_min_judge_candidate_count": max(0, int(value.get("configured_min_judge_candidate_count") or 0)),
        "minimum_expert_call_count": max(0, int(value.get("minimum_expert_call_count") or 0)),
        "minimum_complete_fusion_call_count": max(0, int(value.get("minimum_complete_fusion_call_count") or 0)),
        "full_initial_fusion_call_count": max(0, int(value.get("full_initial_fusion_call_count") or 0)),
        "available_expert_call_count": max(0, int(value.get("available_expert_call_count") or 0)),
        "planned_expert_role_count": max(0, int(value.get("planned_expert_role_count") or 0)),
        "planned_initial_fusion_call_count": max(0, int(value.get("planned_initial_fusion_call_count") or 0)),
        "has_complete_fusion_shape": bool(value.get("has_complete_fusion_shape")),
        "call_budget_meets_complete_floor": bool(value.get("call_budget_meets_complete_floor")),
        "complete_fusion_feasible": bool(value.get("complete_fusion_feasible")),
        "blocked_by_call_budget": bool(value.get("blocked_by_call_budget")),
        "role_budget_constrained": bool(value.get("role_budget_constrained")),
        "omitted_expert_roles": [
            str(role)[:80]
            for role in value.get("omitted_expert_roles", [])
            if str(role)
        ][:8] if isinstance(value.get("omitted_expert_roles"), list) else [],
        "judge_reserved": bool(value.get("judge_reserved")),
        "synthesizer_reserved": bool(value.get("synthesizer_reserved")),
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _budget_with_initial_fusion_call_plan(
    budget: Mapping[str, Any],
    initial_fusion_call_plan: Mapping[str, Any],
) -> dict[str, Any]:
    safe_plan = _safe_initial_fusion_call_plan(initial_fusion_call_plan)
    return {
        **dict(budget),
        "initial_fusion_call_plan": safe_plan,
        "initial_fusion_minimum_call_count": safe_plan["minimum_complete_fusion_call_count"],
        "initial_fusion_planned_call_count": safe_plan["planned_initial_fusion_call_count"],
        "initial_fusion_call_budget_sufficient": safe_plan["complete_fusion_feasible"],
        "initial_fusion_role_budget_constrained": safe_plan["role_budget_constrained"],
    }


def _initial_fusion_resource_admission(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    selected: Sequence[ModelProfile],
    *,
    planned_fusion_roles: Sequence[Mapping[str, Any]],
    initial_fusion_call_plan: Mapping[str, Any],
    profile_pool: Sequence[ModelProfile] | None = None,
) -> dict[str, Any]:
    """Check the complete initial panel against request-local hard limits.

    The executor retains cost and deadline locks because real provider usage and
    latency are uncertain.  This admission check addresses the separate case
    where the assigned initial expert, Judge, and Synthesizer schedule is
    already known to exceed the caller's limit before any provider call.  It
    intentionally does not reject missing price or p50 telemetry: unknown
    estimates remain visible in the receipt and are handled by runtime locks.
    """

    complete_shape = bool(initial_fusion_call_plan.get("complete_fusion_feasible"))
    execution_profiles = _planned_execution_profiles(
        planned_fusion_roles,
        selected,
        profile_pool=profile_pool,
    )
    estimated_cost, cost_execution = _estimated_fusion_execution_cost_usd(
        selected,
        planned_fusion_roles,
        analysis,
        max_output_tokens=request.max_output_tokens,
        profile_pool=profile_pool,
    )
    estimated_latency, latency_known, latency_execution = _estimated_fusion_execution_latency_ms(
        selected,
        planned_fusion_roles,
        max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
        profile_pool=profile_pool,
    )
    cost_known = estimated_cost is not None
    applicable = bool(complete_shape and execution_profiles)
    max_cost_usd = max(0.0, float(budget.get("max_cost_usd") or 0.0))
    max_latency_ms = max(1, int(budget.get("max_latency_ms") or 1))
    cost_exceeds = bool(applicable and cost_known and float(estimated_cost) > max_cost_usd)
    latency_exceeds = bool(
        applicable and latency_known and float(estimated_latency) > float(max_latency_ms)
    )
    blocked_reasons: list[str] = []
    if cost_exceeds:
        blocked_reasons.append("initial_fusion_cost_exceeds_request_budget")
    if latency_exceeds:
        blocked_reasons.append("initial_fusion_latency_exceeds_request_deadline")
    return {
        "schema": "axio_fusion_api.initial_fusion_resource_admission.v1",
        "applicable": applicable,
        "complete_initial_fusion_shape": complete_shape,
        "planned_initial_role_count": len(planned_fusion_roles),
        "planned_initial_profile_count": len(execution_profiles),
        "cost": {
            "known": cost_known,
            "estimated_total_cost_usd": round(float(estimated_cost), 8) if cost_known else None,
            "request_max_cost_usd": round(max_cost_usd, 8),
            "within_request_budget": None if not cost_known else not cost_exceeds,
            "blocked": cost_exceeds,
            "execution": cost_execution,
        },
        "latency": {
            "known": bool(latency_known),
            "estimated_total_latency_ms": round(float(estimated_latency), 3)
            if latency_known
            else None,
            "request_max_latency_ms": max_latency_ms,
            "within_request_deadline": None if not latency_known else not latency_exceeds,
            "blocked": latency_exceeds,
            "execution": latency_execution,
        },
        "blocked": bool(blocked_reasons),
        "blocked_reasons": blocked_reasons,
        "policy": (
            "route_declines_complete_initial_fusion_when_known_assigned_initial_cost_or_p50_latency_"
            "exceeds_request_hard_budget; unknown_estimates_do_not_block_and_runtime_locks_remain_enforced"
        ),
        "optional_repair_or_escalation_included": False,
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
        "schema": "axio_fusion_api.initial_fusion_resource_admission.v1",
        "applicable": bool(value.get("applicable")),
        "complete_initial_fusion_shape": bool(value.get("complete_initial_fusion_shape")),
        "planned_initial_role_count": max(0, int(value.get("planned_initial_role_count") or 0)),
        "planned_initial_profile_count": max(0, int(value.get("planned_initial_profile_count") or 0)),
        "cost": {
            "known": bool(cost.get("known")),
            "estimated_total_cost_usd": _safe_nonnegative_float(cost.get("estimated_total_cost_usd")),
            "request_max_cost_usd": _safe_nonnegative_float(cost.get("request_max_cost_usd")),
            "within_request_budget": _safe_optional_bool(cost.get("within_request_budget")),
            "blocked": bool(cost.get("blocked")),
            "execution": _safe_fusion_cost_execution_receipt(cost_execution),
        },
        "latency": {
            "known": bool(latency.get("known")),
            "estimated_total_latency_ms": _safe_nonnegative_float(latency.get("estimated_total_latency_ms")),
            "request_max_latency_ms": _safe_nonnegative_int(latency.get("request_max_latency_ms")),
            "within_request_deadline": _safe_optional_bool(latency.get("within_request_deadline")),
            "blocked": bool(latency.get("blocked")),
            "execution": _safe_fusion_latency_execution_receipt(latency_execution),
        },
        "blocked": bool(value.get("blocked")),
        "blocked_reasons": [
            str(reason)[:160]
            for reason in value.get("blocked_reasons", [])
            if str(reason)
        ][:8] if isinstance(value.get("blocked_reasons"), list) else [],
        "policy": str(value.get("policy") or "")[:240],
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_fusion_cost_execution_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.initial_execution_cost_estimate.v1")[:120],
        "basis": str(value.get("basis") or "")[:160],
        "profile_count": _safe_nonnegative_int(value.get("profile_count")),
        "profile_hashes": [
            str(item)
            for item in value.get("profile_hashes", [])
            if str(item)
        ][:24] if isinstance(value.get("profile_hashes"), list) else [],
        "pricing_known": bool(value.get("pricing_known")),
        "estimated_input_tokens_per_expert": _safe_nonnegative_int(
            value.get("estimated_input_tokens_per_expert")
        ),
        "role_call_count": _safe_nonnegative_int(value.get("role_call_count")),
        "estimated_total_cost_usd": _safe_nonnegative_float(value.get("estimated_total_cost_usd")),
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_fusion_latency_execution_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.initial_execution_latency_estimate.v1")[:120],
        "basis": str(value.get("basis") or "")[:160],
        "latency_quantile": str(value.get("latency_quantile") or "p50")[:8],
        "expert_role_count": _safe_nonnegative_int(value.get("expert_role_count")),
        "expert_profile_hashes": [
            str(item)
            for item in value.get("expert_profile_hashes", [])
            if str(item)
        ][:24] if isinstance(value.get("expert_profile_hashes"), list) else [],
        "expert_parallel_slots": _safe_nonnegative_int(value.get("expert_parallel_slots")),
        "expert_wave_count": _safe_nonnegative_int(value.get("expert_wave_count")),
        "expert_phase_latency_ms": _safe_nonnegative_float(value.get("expert_phase_latency_ms")),
        "provider_serialization_adjustment_applied": bool(
            value.get("provider_serialization_adjustment_applied")
        ),
        "judge_included": bool(value.get("judge_included")),
        "judge_profile_sha256": str(value.get("judge_profile_sha256") or ""),
        "judge_latency_ms": _safe_nonnegative_float(value.get("judge_latency_ms")),
        "synthesizer_included": bool(value.get("synthesizer_included")),
        "synthesizer_profile_sha256": str(value.get("synthesizer_profile_sha256") or ""),
        "synthesis_latency_ms": _safe_nonnegative_float(value.get("synthesis_latency_ms")),
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _safe_nonnegative_float(value: Any) -> float | None:
    try:
        return max(0.0, float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _safe_nonnegative_int(value: Any) -> int | None:
    try:
        return max(0, int(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _safe_optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _budget_with_initial_fusion_resource_admission(
    budget: Mapping[str, Any],
    initial_fusion_resource_admission: Mapping[str, Any],
) -> dict[str, Any]:
    safe_admission = _safe_initial_fusion_resource_admission(
        initial_fusion_resource_admission
    )
    return {
        **dict(budget),
        "initial_fusion_resource_admission": safe_admission,
        "initial_fusion_resource_budget_checked": True,
        "initial_fusion_resource_budget_applicable": safe_admission["applicable"],
        "initial_fusion_resource_budget_blocked": safe_admission["blocked"],
    }


def _budget_with_fusion_finalization_mode(
    budget: Mapping[str, Any],
    *,
    finalization_mode: str,
    local_consensus_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the admitted finalization contract to the runtime budget.

    The provider-stage call plan remains preserved as an audit record.  A local
    consensus route is a different, explicitly priced execution shape: it
    spends calls only on independent experts and performs the final selection
    in-process.  Keeping the distinction in the budget prevents the executor
    from reserving or silently spending Judge/Synthesizer calls that the route
    never admitted.
    """

    mode = str(finalization_mode or "direct")
    local = mode == "local_consensus"
    minimum_candidates = max(
        1,
        _safe_nonnegative_int(local_consensus_plan.get("minimum_candidate_count")) or 2,
    )
    updated = {
        **dict(budget),
        "fusion_finalization_mode": mode,
        "local_consensus_enabled": local,
        "local_consensus_candidate_available": bool(
            local_consensus_plan.get("feasible")
        ),
        "local_consensus_min_candidate_count": minimum_candidates if local else 0,
        "local_consensus_provider_stage_calls_reserved": False,
        "local_consensus_plan": _safe_local_consensus_plan(local_consensus_plan),
    }
    if local:
        updated["min_judge_candidate_count"] = max(
            _safe_nonnegative_int(updated.get("min_judge_candidate_count")) or 2,
            minimum_candidates,
        )
    return updated


def _provider_serialization_signature(
    profile: ModelProfile,
) -> tuple[str, str, str, str, str] | None:
    """Identify a channel-level single-flight transport group.

    ``max_in_flight`` is meaningful across profiles only when the traffic
    contract is channel-scoped and the key pool is shared.  A profile-scoped
    limit must not suppress otherwise independent model calls.  The returned
    tuple contains configuration identifiers only; it is used in-memory and
    never enters a receipt.
    """

    raw = profile.traffic_control if isinstance(profile.traffic_control, Mapping) else {}
    scope = str(raw.get("scope") or "profile").strip().casefold()
    key_pool = str(raw.get("rate_limit_key_pool") or "shared").strip().casefold()
    try:
        max_in_flight = int(raw.get("max_in_flight") or 0)
    except (TypeError, ValueError):
        max_in_flight = 0
    if scope != "channel" or key_pool != "shared" or max_in_flight != 1:
        return None
    return (
        str(profile.provider),
        str(profile.base_url_env or profile.runtime_base_url),
        str(profile.api_key_env),
        str(profile.api_format),
        str(profile.auth_scheme),
    )


def _serializing_provider_groups(
    profiles: Sequence[ModelProfile],
) -> dict[tuple[str, str, str, str, str], tuple[ModelProfile, ...]]:
    groups: dict[tuple[str, str, str, str, str], list[ModelProfile]] = {}
    for profile in profiles:
        signature = _provider_serialization_signature(profile)
        if signature is not None:
            groups.setdefault(signature, []).append(profile)
    return {
        signature: tuple(rows)
        for signature, rows in groups.items()
        if len(rows) >= 2
    }


def _panel_contains_serialized_provider_pair(
    profiles: Sequence[ModelProfile],
) -> bool:
    groups = _serializing_provider_groups(profiles)
    return any(len(rows) >= 2 for rows in groups.values())


def _local_consensus_plan(
    *,
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    selected: Sequence[ModelProfile],
    role_blueprint: Sequence[Mapping[str, Any]],
    direct_profile: ModelProfile | None,
) -> tuple[list[ModelProfile], list[dict[str, Any]], dict[str, Any]]:
    """Find a latency-feasible multi-model panel with local finalization.

    This path is deliberately narrower than provider Judge/Synthesizer
    Fusion.  It exists for a real operational case: two or three independent
    providers can answer in one parallel wave, while serial remote stages
    would violate the hard latency contract.  The local judge already used by
    the ordinary runtime ranks evidence, coverage, calibration, and risk; no
    benchmark labels or hidden model output is involved in admission.
    """

    default: dict[str, Any] = {
        "schema": "axio_fusion_api.local_consensus_plan.v1",
        "enabled": request.public_model in {"axio-terra", "axio-pro"},
        "feasible": False,
        "finalization_mode": "provider_judge_synthesis",
        "reason": "not_applicable_for_public_tier",
        "minimum_candidate_count": 0,
        "panel_size": 0,
        "panel_profile_hashes": [],
        "panel_provider_hashes": [],
        "expert_role_count": 0,
        "expert_phase_latency_ms": None,
        "local_overhead_ms": LOCAL_CONSENSUS_OVERHEAD_MS,
        "estimated_latency_ms": None,
        "latency_multiplier_vs_direct": None,
        "latency_guard_blocked": False,
        "request_deadline_blocked": False,
        "p95_latency_known": False,
        "expert_p95_phase_latency_ms": None,
        "estimated_p95_latency_ms": None,
        "p95_latency_multiplier_vs_direct": None,
        "p95_latency_guard_blocked": False,
        "p95_request_deadline_blocked": False,
        "cost_known": False,
        "estimated_cost_usd": None,
        "cost_budget_blocked": False,
        "expected_quality": None,
        "direct_expected_quality": None,
        "expected_quality_delta": None,
        "candidate_pool_count": 0,
        "candidate_panel_evaluation_count": 0,
        "provider_diversity_floor": 0,
        "provider_diversity_floor_met": False,
        "provider_serialization_detected": False,
        "provider_parallelism_constraint": False,
        "provider_diversity_required": False,
        "provider_serialization_group_count": 0,
        "provider_serialization_candidate_count": 0,
        "provider_diversity_requirement_reason": "",
        "capability_evidence_mode": "unknown",
        "redundancy_enabled": False,
        "redundancy_candidate_count": 0,
        "planned_execution": {
            "schema": "axio_fusion_api.local_consensus_execution.v1",
            "basis": "parallel_expert_calls_only_plus_in_process_consensus",
            "expert_role_count": 0,
            "expert_profile_hashes": [],
            "expert_parallel_slots": 0,
            "expert_wave_count": 0,
            "expert_phase_latency_ms": None,
            "latency_quantile": "p50",
            "local_consensus_overhead_ms": LOCAL_CONSENSUS_OVERHEAD_MS,
            "total_latency_ms": None,
            "provider_judge_included": False,
            "provider_synthesizer_included": False,
            "raw_profile_id_persisted": False,
            "secrets_persisted": False,
        },
        "planned_p95_execution": {
            "schema": "axio_fusion_api.local_consensus_execution.v1",
            "basis": "parallel_expert_calls_only_plus_in_process_consensus",
            "latency_quantile": "p95",
            "expert_role_count": 0,
            "expert_profile_hashes": [],
            "expert_parallel_slots": 0,
            "expert_wave_count": 0,
            "expert_phase_latency_ms": None,
            "local_consensus_overhead_ms": LOCAL_CONSENSUS_OVERHEAD_MS,
            "total_latency_ms": None,
            "provider_judge_included": False,
            "provider_synthesizer_included": False,
            "raw_profile_id_persisted": False,
            "secrets_persisted": False,
        },
        "planned_cost": {
            "schema": "axio_fusion_api.local_consensus_cost_estimate.v1",
            "basis": "parallel_expert_calls_only_plus_in_process_consensus",
            "profile_count": 0,
            "profile_hashes": [],
            "pricing_known": False,
            "role_call_count": 0,
            "estimated_total_cost_usd": None,
            "raw_profile_id_persisted": False,
            "secrets_persisted": False,
        },
        "raw_profile_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }
    if request.public_model not in {"axio-terra", "axio-pro"}:
        return [], [], default
    direct_latency_value = (
        _role_latency_ms(direct_profile, "primary_solver", "p50_latency_ms")
        if direct_profile is not None
        else None
    )
    if direct_profile is None or direct_latency_value is None:
        default["reason"] = "direct_latency_telemetry_unknown"
        return [], [], default

    has_critic_target = any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "critic"
        for row in role_blueprint
    )
    has_short_verification_target = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") == "short_verification"
        for row in role_blueprint
    )
    has_domain_target = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") == "domain_specialist"
        for row in role_blueprint
    )
    has_full_second_role = _distinct_full_second_role_available(
        scored,
        role_blueprint,
    )
    # Pro's original local-consensus contract requires a third verification
    # seat whenever the task blueprint calls for a Critic.  A narrow verifier
    # is the only deliberate two-seat exception: it is explicitly screened as
    # the second evidence branch and cannot be treated as a full Critic.
    minimum_count = (
        3
        if request.public_model == "axio-pro"
        and has_critic_target
        and (has_full_second_role or not has_short_verification_target)
        else 2
    )
    default["minimum_candidate_count"] = minimum_count
    try:
        max_total_calls = max(1, int(budget.get("max_total_model_calls") or 1))
    except (TypeError, ValueError):
        max_total_calls = 1
    if max_total_calls < minimum_count:
        default["reason"] = "max_total_model_calls_below_local_consensus_floor"
        return [], [], default
    if bool(budget.get("caller_max_total_model_calls_explicit")):
        # An explicit caller ceiling limits total provider calls, but it does
        # not require the slower provider Judge/Synthesizer shape.  Permit the
        # local shape only when the caller granted at least the complete
        # provider Fusion floor; a smaller ceiling remains a hard refusal.
        provider_stage_floor = minimum_count + 2
        default["explicit_call_budget_floor"] = provider_stage_floor
        if max_total_calls < provider_stage_floor:
            default["reason"] = "explicit_call_budget_below_local_fallback_floor"
            return [], [], default
        default["reason"] = "explicit_call_budget_allows_latency_safe_local_consensus"

    try:
        max_latency_ms = max(1, int(budget.get("max_latency_ms") or 1))
    except (TypeError, ValueError):
        max_latency_ms = 1
    direct_latency = max(1.0, float(direct_latency_value))
    candidate_pool_by_identity: dict[str, ModelProfile] = {}
    # Score-first candidates preserve capability quality; fastest candidates
    # make the bounded search useful when the score-first panel contains a
    # slow mandatory-stage model.
    ranked_candidates = [profile for profile, _ in scored[:24]]
    fastest_candidates = sorted(
        [profile for profile, _ in scored],
        key=lambda profile: (
            float(profile.p50_latency_ms)
            if profile.p50_latency_ms is not None
            else float("inf"),
            profile.profile_id,
        ),
    )[:24]
    for profile in [*selected, direct_profile, *ranked_candidates, *fastest_candidates]:
        if not profile.enabled or str(profile.health or "unknown") == "unavailable":
            continue
        if not any(
            _screening_role_allowed(profile, role)
            for role in _FUSION_EXPERT_ROLE_NAMES
        ):
            continue
        if profile.p50_latency_ms is None or float(profile.p50_latency_ms) <= 0:
            continue
        if float(profile.p50_latency_ms) > max_latency_ms:
            continue
        candidate_pool_by_identity.setdefault(profile.canonical_identity, profile)
    candidate_pool = list(candidate_pool_by_identity.values())
    default["candidate_pool_count"] = len(candidate_pool)
    if len(candidate_pool) < minimum_count:
        default["reason"] = "insufficient_latency_eligible_independent_models"
        return [], [], default

    relevant_axes = list(
        dict.fromkeys(
            [
                *_analysis_capability_axes(analysis),
                "structured_output",
                "critique",
            ]
        )
    )
    capability_evidence_available = any(
        _profile_has_relevant_capability_evidence(profile, relevant_axes)
        for profile in candidate_pool
    )
    capability_evidence_mode = (
        "declared_or_calibrated"
        if capability_evidence_available
        else "operational_only_neutral_capabilities"
    )
    default["capability_evidence_mode"] = capability_evidence_mode
    available_provider_count = len({profile.provider for profile in candidate_pool})
    provider_diversity_floor = min(minimum_count, available_provider_count)
    default["provider_diversity_floor"] = provider_diversity_floor
    serializing_groups = _serializing_provider_groups(candidate_pool)
    serializing_candidate_count = sum(len(rows) for rows in serializing_groups.values())
    provider_parallelism_constraint = bool(serializing_groups and minimum_count >= 2)
    default.update(
        {
            "provider_serialization_detected": bool(serializing_groups),
            "provider_parallelism_constraint": provider_parallelism_constraint,
            "provider_serialization_group_count": len(serializing_groups),
            "provider_serialization_candidate_count": serializing_candidate_count,
        }
    )
    # A local-consensus panel is only useful when its evidence and failure
    # domains are meaningfully independent.  Capability scores can rank
    # models, but they cannot prove that two models on the same gateway have
    # independent queueing, rate limits, or outage behavior.  When at least
    # two providers are available, prefer a cross-provider panel even when
    # capability evidence exists; a single-provider panel remains valid only
    # when the portfolio offers no provider-diverse alternative.
    require_provider_diversity = bool(provider_diversity_floor > 1)
    default["provider_diversity_required"] = require_provider_diversity
    default["provider_diversity_requirement_reason"] = (
        "channel_single_flight_parallelism"
        if provider_parallelism_constraint and provider_diversity_floor > 1
        else (
            "cross_provider_independence"
            if capability_evidence_available and provider_diversity_floor > 1
            else (
                "neutral_capability_evidence"
                if provider_diversity_floor > 1
                else ""
            )
        )
    )
    desired_panel_size = minimum_count
    if (
        not capability_evidence_available
        and max(1, int(budget.get("max_models") or minimum_count)) > minimum_count
        and minimum_count < LOCAL_CONSENSUS_MAX_PANEL_SIZE
    ):
        desired_panel_size = minimum_count + 1
        default["redundancy_enabled"] = True
        default["redundancy_candidate_count"] = 1

    direct_quality = _expected_profile_quality(direct_profile, analysis)
    default["direct_expected_quality"] = round(direct_quality, 4)
    evaluations: list[
        tuple[
            tuple[ModelProfile, ...],
            list[dict[str, Any]],
            float,
            float,
            float | None,
            float | None,
            float | None,
        ]
    ] = []
    max_parallel = max(1, int(budget.get("max_parallel_experts") or minimum_count))
    for panel_size in range(minimum_count, desired_panel_size + 1):
        for panel_tuple in combinations(candidate_pool, panel_size):
            panel = tuple(panel_tuple)
            if len({profile.canonical_identity for profile in panel}) != len(panel):
                continue
            # The runtime traffic gate serializes profiles in the same
            # channel-scoped shared pool.  A phase-length calculation that
            # ignores this would overstate Fusion parallelism and could breach
            # the 3x latency contract.
            if _panel_contains_serialized_provider_pair(panel):
                continue
            provider_count = len({profile.provider for profile in panel})
            if require_provider_diversity and provider_count < provider_diversity_floor:
                continue
            roles = _role_assignments(
                request,
                analysis,
                panel,
                True,
                role_blueprint,
                budget=budget,
                latency_baseline_profile=direct_profile,
                allow_critic_as_second_evidence=True,
            )
            if len(panel) > minimum_count:
                assigned_expert_profile_ids = {
                    str(
                        (
                            row.get("model")
                            if isinstance(row.get("model"), Mapping)
                            else {}
                        ).get("profile_id")
                        or ""
                    )
                    for row in roles
                    if isinstance(row, Mapping)
                    and str(row.get("role") or "")
                    in set(_FUSION_EXPERT_ROLE_NAMES)
                }
                backup_profile = next(
                    (
                        profile
                        for profile in panel
                        if profile.profile_id not in assigned_expert_profile_ids
                        and _screening_role_allowed(profile, "independent_solver")
                    ),
                    None,
                )
                if backup_profile is not None:
                    roles.append(
                        _role_assignment(
                            "backup_solver",
                            "bounded_redundant_independent_candidate",
                            backup_profile,
                            role_blueprint,
                            analysis,
                        )
                    )
            expert_roles = [
                row
                for row in roles
                if isinstance(row, Mapping)
                and str(row.get("role") or "")
                in {
                    *_FUSION_EXPERT_ROLE_NAMES,
                    "backup_solver",
                }
            ]
            if len(expert_roles) < minimum_count:
                continue
            expert_profiles = [
                next(
                    (
                        profile
                        for profile in panel
                        if profile.profile_id
                        == str(
                            (row.get("model") if isinstance(row.get("model"), Mapping) else {}).get(
                                "profile_id"
                            )
                            or ""
                        )
                    ),
                    None,
                )
                for row in expert_roles
            ]
            expert_profiles = [profile for profile in expert_profiles if profile is not None]
            if len(expert_profiles) < minimum_count:
                continue
            expert_role_profiles = _assigned_role_profile_pairs(
                expert_roles,
                panel,
                role_names={*_FUSION_EXPERT_ROLE_NAMES, "backup_solver"},
            )
            if len(expert_role_profiles) < minimum_count:
                continue
            expert_p50_latencies = [
                _role_latency_ms(profile, role, "p50_latency_ms")
                for role, profile in expert_role_profiles
            ]
            if any(
                latency is None or latency > max_latency_ms
                for latency in expert_p50_latencies
            ):
                continue
            phase_latency = _parallel_expert_phase_latency_ms(
                [float(latency) for latency in expert_p50_latencies],
                max_parallel=max_parallel,
                profiles=[profile for _, profile in expert_role_profiles],
            )
            estimated_latency = phase_latency + LOCAL_CONSENSUS_OVERHEAD_MS
            multiplier = estimated_latency / direct_latency
            cost, cost_receipt = _estimated_local_consensus_cost_usd(
                expert_profiles,
                analysis,
                max_output_tokens=request.max_output_tokens,
            )
            if estimated_latency > max_latency_ms:
                continue
            if multiplier > FUSION_LATENCY_MULTIPLIER_GUARD:
                continue
            if cost is not None and cost > max(0.0, float(budget.get("max_cost_usd") or 0.0)):
                continue
            panel_p95_latency: float | None = None
            panel_p95_multiplier: float | None = None
            direct_p95_latency = _role_latency_ms(
                direct_profile,
                "primary_solver",
                "p95_latency_ms",
            )
            expert_p95_latencies = [
                _role_latency_ms(profile, role, "p95_latency_ms")
                for role, profile in expert_role_profiles
            ]
            p95_known = bool(
                direct_p95_latency is not None
                and all(latency is not None for latency in expert_p95_latencies)
            )
            if p95_known:
                panel_p95_phase = _parallel_expert_phase_latency_ms(
                    [float(latency) for latency in expert_p95_latencies],
                    max_parallel=max_parallel,
                    profiles=[profile for _, profile in expert_role_profiles],
                )
                panel_p95_latency = panel_p95_phase + LOCAL_CONSENSUS_OVERHEAD_MS
                panel_p95_multiplier = panel_p95_latency / max(
                    1.0,
                    float(direct_p95_latency),
                )
                if panel_p95_latency > max_latency_ms:
                    continue
                if panel_p95_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD:
                    continue
            quality = _local_consensus_expected_quality(expert_profiles, analysis)
            # A local consensus panel may trade a small amount of peak capability
            # for independent error coverage, but never a large quality regression.
            if quality < direct_quality - EXPERT_QUALITY_REPLACEMENT_TOLERANCE:
                continue
            evaluations.append(
                (
                    panel,
                    expert_roles,
                    quality,
                    multiplier,
                    cost,
                    panel_p95_latency,
                    panel_p95_multiplier,
                )
            )

    default["candidate_panel_evaluation_count"] = len(evaluations)
    if not evaluations:
        default["reason"] = "no_local_consensus_panel_meets_latency_and_quality_guard"
        return [], [], default
    chosen = max(
        evaluations,
        key=lambda row: (
            len({profile.provider for profile in row[0]})
            if require_provider_diversity
            else 0,
            len({profile.api_format for profile in row[0]})
            if require_provider_diversity
            else 0,
            round(float(row[2]), 8),
            -round(float(row[3]), 8),
            -round(float(row[4] or 0.0), 8),
            len({profile.provider for profile in row[0]}),
            tuple(profile.profile_id for profile in row[0]),
        ),
    )
    (
        panel,
        expert_roles,
        quality,
        multiplier,
        cost,
        panel_p95_latency,
        panel_p95_multiplier,
    ) = chosen
    chosen_expert_role_profiles = _assigned_role_profile_pairs(
        expert_roles,
        panel,
        role_names={*_FUSION_EXPERT_ROLE_NAMES, "backup_solver"},
    )
    phase_latency = _parallel_expert_phase_latency_ms(
        [
            float(_role_latency_ms(profile, role, "p50_latency_ms") or 0.0)
            for role, profile in chosen_expert_role_profiles
        ],
        max_parallel=max_parallel,
        profiles=[profile for _, profile in chosen_expert_role_profiles],
    )
    _chosen_cost, chosen_cost_receipt = _estimated_local_consensus_cost_usd(
        [profile for _, profile in chosen_expert_role_profiles],
        analysis,
        max_output_tokens=request.max_output_tokens,
    )
    planned_execution = _fusion_latency_execution_receipt(
        [profile for _, profile in chosen_expert_role_profiles],
        None,
        None,
        max_parallel=max_parallel,
        expert_phase_latency_ms=phase_latency,
    )
    planned_execution.update(
        {
            "schema": "axio_fusion_api.local_consensus_execution.v1",
            "basis": "parallel_expert_calls_only_plus_in_process_consensus",
            "local_consensus_overhead_ms": LOCAL_CONSENSUS_OVERHEAD_MS,
            "total_latency_ms": round(
                float(phase_latency + LOCAL_CONSENSUS_OVERHEAD_MS),
                3,
            ),
            "provider_judge_included": False,
            "provider_synthesizer_included": False,
        }
    )
    planned_p95_execution = _fusion_latency_execution_receipt(
        [profile for _, profile in chosen_expert_role_profiles],
        None,
        None,
        max_parallel=max_parallel,
        latency_quantile="p95",
        expert_phase_latency_ms=(
            max(0.0, float(panel_p95_latency) - LOCAL_CONSENSUS_OVERHEAD_MS)
            if panel_p95_latency is not None
            else 0.0
        ),
    )
    planned_p95_execution.update(
        {
            "schema": "axio_fusion_api.local_consensus_execution.v1",
            "basis": "parallel_expert_calls_only_plus_in_process_consensus",
            "local_consensus_overhead_ms": LOCAL_CONSENSUS_OVERHEAD_MS,
            "total_latency_ms": (
                round(float(panel_p95_latency), 3)
                if panel_p95_latency is not None
                else None
            ),
            "provider_judge_included": False,
            "provider_synthesizer_included": False,
        }
    )
    planned_cost = dict(chosen_cost_receipt)
    planned_cost.update(
        {
            "basis": "parallel_expert_calls_only_plus_in_process_consensus",
            "raw_profile_id_persisted": False,
            "secrets_persisted": False,
        }
    )
    default.update(
        {
            "feasible": True,
            "finalization_mode": "local_consensus",
            "reason": "parallel_expert_panel_with_local_consensus_within_3x_guard",
            "panel_size": len(panel),
            "panel_profile_hashes": [sha256_text(profile.profile_id) for profile in panel[:24]],
            "panel_provider_hashes": list(
                dict.fromkeys(sha256_text(profile.provider) for profile in panel[:24])
            ),
            "expert_role_count": len(expert_roles),
            "expert_phase_latency_ms": round(float(phase_latency), 3),
            "estimated_latency_ms": round(float(phase_latency + LOCAL_CONSENSUS_OVERHEAD_MS), 3),
            "latency_multiplier_vs_direct": round(float(multiplier), 4),
            "p95_latency_known": panel_p95_latency is not None,
            "expert_p95_phase_latency_ms": (
                round(
                    max(0.0, float(panel_p95_latency) - LOCAL_CONSENSUS_OVERHEAD_MS),
                    3,
                )
                if panel_p95_latency is not None
                else None
            ),
            "estimated_p95_latency_ms": (
                round(float(panel_p95_latency), 3)
                if panel_p95_latency is not None
                else None
            ),
            "p95_latency_multiplier_vs_direct": (
                round(float(panel_p95_multiplier), 4)
                if panel_p95_multiplier is not None
                else None
            ),
            "p95_latency_guard_blocked": False,
            "p95_request_deadline_blocked": False,
            "expected_quality": round(float(quality), 4),
            "expected_quality_delta": round(float(quality - direct_quality), 4),
            "cost_known": cost is not None,
            "estimated_cost_usd": round(float(cost), 8) if cost is not None else None,
            "provider_diversity_floor": provider_diversity_floor,
            "provider_diversity_floor_met": len({profile.provider for profile in panel})
            >= provider_diversity_floor,
            "provider_serialization_detected": bool(serializing_groups),
            "provider_parallelism_constraint": provider_parallelism_constraint,
            "provider_diversity_required": require_provider_diversity,
            "provider_serialization_group_count": len(serializing_groups),
            "provider_serialization_candidate_count": serializing_candidate_count,
            "provider_diversity_requirement_reason": str(
                default.get("provider_diversity_requirement_reason") or ""
            ),
            "capability_evidence_mode": capability_evidence_mode,
            "redundancy_enabled": bool(desired_panel_size > minimum_count),
            "redundancy_candidate_count": max(0, len(panel) - minimum_count),
            "planned_execution": planned_execution,
            "planned_p95_execution": planned_p95_execution,
            "planned_cost": planned_cost,
            "provider_stage_calls_reserved": False,
        }
    )
    return list(panel), [dict(role) for role in expert_roles], default


def _estimated_local_consensus_cost_usd(
    profiles: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
    *,
    max_output_tokens: int | None,
) -> tuple[float | None, dict[str, Any]]:
    pricing_known = all(
        profile.input_cost_per_million is not None
        and profile.output_cost_per_million is not None
        for profile in profiles
    )
    receipt = {
        "schema": "axio_fusion_api.local_consensus_cost_estimate.v1",
        "basis": "parallel_expert_calls_only_plus_in_process_consensus",
        "profile_count": len(profiles),
        "profile_hashes": [sha256_text(profile.profile_id) for profile in profiles[:24]],
        "pricing_known": pricing_known,
        "estimated_input_tokens_per_expert": _estimated_input_tokens_for_route(analysis),
        "estimated_output_tokens_per_expert": _estimated_role_output_tokens(
            max_output_tokens=max_output_tokens,
            kind="model_role",
        ),
        "role_call_count": len(profiles),
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }
    if not pricing_known:
        receipt["estimated_total_cost_usd"] = None
        return None, receipt
    input_tokens = _estimated_input_tokens_for_route(analysis)
    output_tokens = _estimated_role_output_tokens(
        max_output_tokens=max_output_tokens,
        kind="model_role",
    )
    total = sum(
        _profile_call_cost_usd(
            profile,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        for profile in profiles
    )
    receipt["estimated_total_cost_usd"] = round(float(total), 8)
    return total, receipt


def _local_consensus_expected_quality(
    profiles: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
) -> float:
    if not profiles:
        return 0.0
    individual = sorted(
        (_expected_profile_quality(profile, analysis) for profile in profiles),
        reverse=True,
    )
    coverage = _capability_coverage_score(profiles, analysis)
    complementarity = _capability_complementarity_score(profiles, analysis)
    provider_diversity = _provider_diversity_score(profiles)
    correlation = _estimated_error_correlation(profiles, analysis)
    independent_credit = min(0.10, max(0, len(profiles) - 1) * 0.045)
    quality = (
        individual[0] * 0.68
        + (sum(individual[1:]) / max(1, len(individual) - 1) if len(individual) > 1 else individual[0]) * 0.12
        + coverage * 0.08
        + complementarity * 0.06
        + provider_diversity * 0.03
        + max(0.0, 1.0 - correlation) * 0.03
        + independent_credit
    )
    return max(0.0, min(1.0, quality))


def _safe_local_consensus_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    execution = value.get("planned_execution") if isinstance(value.get("planned_execution"), Mapping) else {}
    p95_execution = (
        value.get("planned_p95_execution")
        if isinstance(value.get("planned_p95_execution"), Mapping)
        else {}
    )
    cost = value.get("planned_cost") if isinstance(value.get("planned_cost"), Mapping) else {}
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.local_consensus_plan.v1")[:120],
        "enabled": bool(value.get("enabled")),
        "feasible": bool(value.get("feasible")),
        "finalization_mode": str(value.get("finalization_mode") or "provider_judge_synthesis")[:80],
        "reason": str(value.get("reason") or "")[:160],
        "minimum_candidate_count": _safe_nonnegative_int(value.get("minimum_candidate_count")),
        "panel_size": _safe_nonnegative_int(value.get("panel_size")),
        "panel_profile_hashes": [
            str(item) for item in value.get("panel_profile_hashes", [])[:24] if str(item)
        ] if isinstance(value.get("panel_profile_hashes"), list) else [],
        "panel_provider_hashes": [
            str(item) for item in value.get("panel_provider_hashes", [])[:24] if str(item)
        ] if isinstance(value.get("panel_provider_hashes"), list) else [],
        "expert_role_count": _safe_nonnegative_int(value.get("expert_role_count")),
        "expert_phase_latency_ms": _safe_nonnegative_float(value.get("expert_phase_latency_ms")),
        "local_overhead_ms": _safe_nonnegative_int(value.get("local_overhead_ms")),
        "estimated_latency_ms": _safe_nonnegative_float(value.get("estimated_latency_ms")),
        "latency_multiplier_vs_direct": _safe_nonnegative_float(value.get("latency_multiplier_vs_direct")),
        "latency_guard_blocked": bool(value.get("latency_guard_blocked")),
        "request_deadline_blocked": bool(value.get("request_deadline_blocked")),
        "p95_latency_known": bool(value.get("p95_latency_known")),
        "expert_p95_phase_latency_ms": _safe_nonnegative_float(
            value.get("expert_p95_phase_latency_ms")
        ),
        "estimated_p95_latency_ms": _safe_nonnegative_float(
            value.get("estimated_p95_latency_ms")
        ),
        "p95_latency_multiplier_vs_direct": _safe_nonnegative_float(
            value.get("p95_latency_multiplier_vs_direct")
        ),
        "p95_latency_guard_blocked": bool(value.get("p95_latency_guard_blocked")),
        "p95_request_deadline_blocked": bool(
            value.get("p95_request_deadline_blocked")
        ),
        "cost_known": bool(value.get("cost_known")),
        "estimated_cost_usd": _safe_nonnegative_float(value.get("estimated_cost_usd")),
        "cost_budget_blocked": bool(value.get("cost_budget_blocked")),
        "expected_quality": _safe_nonnegative_float(value.get("expected_quality")),
        "direct_expected_quality": _safe_nonnegative_float(value.get("direct_expected_quality")),
        "expected_quality_delta": value.get("expected_quality_delta"),
        "candidate_pool_count": _safe_nonnegative_int(value.get("candidate_pool_count")),
        "candidate_panel_evaluation_count": _safe_nonnegative_int(
            value.get("candidate_panel_evaluation_count")
        ),
        "provider_diversity_floor": _safe_nonnegative_int(
            value.get("provider_diversity_floor")
        ),
        "provider_diversity_floor_met": bool(value.get("provider_diversity_floor_met")),
        "provider_serialization_detected": bool(value.get("provider_serialization_detected")),
        "provider_parallelism_constraint": bool(value.get("provider_parallelism_constraint")),
        "provider_diversity_required": bool(value.get("provider_diversity_required")),
        "provider_serialization_group_count": _safe_nonnegative_int(
            value.get("provider_serialization_group_count")
        ),
        "provider_serialization_candidate_count": _safe_nonnegative_int(
            value.get("provider_serialization_candidate_count")
        ),
        "provider_diversity_requirement_reason": str(
            value.get("provider_diversity_requirement_reason") or ""
        )[:80],
        "capability_evidence_mode": str(
            value.get("capability_evidence_mode") or "unknown"
        )[:80],
        "redundancy_enabled": bool(value.get("redundancy_enabled")),
        "redundancy_candidate_count": _safe_nonnegative_int(
            value.get("redundancy_candidate_count")
        ),
        "planned_execution": _safe_local_consensus_execution(
            execution,
            latency_quantile="p50",
        ),
        "planned_p95_execution": _safe_local_consensus_execution(
            p95_execution,
            latency_quantile="p95",
        ),
        "planned_cost": {
            "schema": str(
                cost.get("schema")
                or "axio_fusion_api.local_consensus_cost_estimate.v1"
            )[:120],
            "basis": str(cost.get("basis") or "")[:160],
            "profile_count": _safe_nonnegative_int(cost.get("profile_count")),
            "profile_hashes": [
                str(item) for item in cost.get("profile_hashes", []) if str(item)
            ][:24]
            if isinstance(cost.get("profile_hashes"), list)
            else [],
            "pricing_known": bool(cost.get("pricing_known")),
            "role_call_count": _safe_nonnegative_int(cost.get("role_call_count")),
            "estimated_total_cost_usd": _safe_nonnegative_float(
                cost.get("estimated_total_cost_usd")
            ),
            "raw_profile_id_persisted": False,
            "secrets_persisted": False,
        },
        "provider_stage_calls_reserved": False,
        "raw_profile_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _safe_local_consensus_execution(
    value: Mapping[str, Any],
    *,
    latency_quantile: str,
) -> dict[str, Any]:
    return {
        "schema": str(
            value.get("schema") or "axio_fusion_api.local_consensus_execution.v1"
        )[:120],
        "basis": str(value.get("basis") or "")[:160],
        "latency_quantile": str(latency_quantile or value.get("latency_quantile") or "p50")[:8],
        "expert_role_count": _safe_nonnegative_int(value.get("expert_role_count")),
        "expert_profile_hashes": [
            str(item) for item in value.get("expert_profile_hashes", []) if str(item)
        ][:24] if isinstance(value.get("expert_profile_hashes"), list) else [],
        "expert_parallel_slots": _safe_nonnegative_int(value.get("expert_parallel_slots")),
        "expert_wave_count": _safe_nonnegative_int(value.get("expert_wave_count")),
        "expert_phase_latency_ms": _safe_nonnegative_float(
            value.get("expert_phase_latency_ms")
        ),
        "local_consensus_overhead_ms": _safe_nonnegative_float(
            value.get("local_consensus_overhead_ms")
        ),
        "total_latency_ms": _safe_nonnegative_float(value.get("total_latency_ms")),
        "provider_judge_included": bool(value.get("provider_judge_included")),
        "provider_synthesizer_included": bool(
            value.get("provider_synthesizer_included")
        ),
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }

def _rank_profiles(profiles: Sequence[ModelProfile], analysis: Mapping[str, Any]) -> list[tuple[ModelProfile, float]]:
    domains = list(analysis.get("domains") or ["daily_work"])
    scored = []
    prior_ranks = [
        int(
            profile.screening_operational_rank
            or profile.screening_prior_rank
        )
        for profile in profiles
        if (
            (
                profile.screening_operational_rank is not None
                or profile.screening_prior_rank is not None
            )
            and int(
                profile.screening_operational_rank
                or profile.screening_prior_rank
                or 0
            )
            > 0
        )
    ]
    max_prior_rank = max(prior_ranks, default=0)
    for profile in profiles:
        capability = sum(profile.capability(axis) for axis in domains) / max(1, len(domains))
        critique = profile.capability("critique")
        structured = profile.capability("structured_output")
        cost = _cost_efficiency(profile)
        latency = _latency_score(profile)
        reliability = _reliability_score(profile)
        score = capability * 0.42 + critique * 0.14 + structured * 0.12 + cost * 0.10 + latency * 0.08 + reliability * 0.14
        # Screening is a bounded operational prior. It can break close
        # capability ties, but cannot override measured capability, latency,
        # or reliability evidence.
        score += _screening_prior_score(profile, max_prior_rank) * 0.04
        scored.append((profile, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def _fast_profile_within_deadline(profile: ModelProfile, max_latency_ms: int) -> bool:
    """Treat an observed p50 above the Fast deadline as infeasible when possible.

    Missing latency telemetry is deliberately not rejected.  A newly configured
    provider must remain usable while probe/calibration evidence is collected;
    known-slow profiles, however, should not displace a known-fast alternative
    on the direct Fast path.
    """

    latency = profile.p50_latency_ms
    return latency is None or int(latency) <= max(1, int(max_latency_ms))


def _screening_prior_score(profile: ModelProfile, max_rank: int) -> float:
    rank = profile.screening_operational_rank or profile.screening_prior_rank
    if rank is None or int(rank) <= 0 or max_rank <= 0:
        return 0.0
    if max_rank == 1:
        return 1.0
    return max(0.0, min(1.0, 1.0 - (int(rank) - 1) / float(max_rank - 1)))


def _screening_role_allowed(profile: ModelProfile, role: str) -> bool:
    """Apply screening role constraints and completed role-probe failures.

    Legacy registries have empty role metadata and remain compatible. A
    screened profile with an allow-list is intentionally fail-closed for
    roles outside that list, while an explicit deny-list always wins.
    A completed operational role probe is a stronger serving signal than a
    research-time capability promotion: a role that the strict streaming
    probe failed must not be admitted merely because the research Agent
    inferred that the model might perform it well.
    """

    role_name = " ".join(str(role or "").strip().casefold().split())
    if not role_name:
        return True
    denied = {str(item).strip().casefold() for item in profile.screening_disallowed_roles}
    if role_name in denied:
        return False
    allowed = {str(item).strip().casefold() for item in profile.screening_allowed_roles}
    if allowed and role_name not in allowed:
        return False

    admission = profile.screening_role_admission
    admission = admission if isinstance(admission, Mapping) else {}
    operational = admission.get("operational_role_probe")
    operational = operational if isinstance(operational, Mapping) else {}
    if operational:
        failed_roles = {
            " ".join(str(item or "").strip().casefold().split())
            for item in operational.get("failed_roles", [])
            if str(item)
        }
        if role_name in failed_roles:
            return False
        tested_roles = {
            " ".join(str(item or "").strip().casefold().split())
            for item in operational.get("tested_roles", [])
            if str(item)
        }
        passed_roles = {
            " ".join(str(item or "").strip().casefold().split())
            for item in operational.get("passed_roles", [])
            if str(item)
        }
        if role_name in tested_roles and role_name not in passed_roles:
            return False
    return True


def _screening_role_contract_present(profile: ModelProfile) -> bool:
    """Return whether the profile carries an explicit pre-Fusion role contract.

    A profile created directly by an older caller has no screening role data;
    its capability vector may therefore contain neutral defaults rather than
    an assertion that structured output is weak.  Generated pre-Fusion
    registries always carry an allow/deny decision, so their capability floors
    remain enforced below.
    """

    return bool(profile.screening_allowed_roles or profile.screening_disallowed_roles)


def _distinct_full_second_role_available(
    scored: Sequence[tuple[ModelProfile, float]],
    role_blueprint: Sequence[Mapping[str, Any]],
) -> bool:
    """Check for a separately assignable full evidence branch.

    A screening prior on the same canonical model as the direct primary is
    not independent evidence.  Domain-specialist capacity is considered only
    when the current request actually has a domain-specialist target; an
    unused role prior must not suppress the narrower short-verification path.
    """

    has_domain_target = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") == "domain_specialist"
        for row in role_blueprint
    )
    primary_profiles = [
        profile
        for profile, _score in scored
        if _screening_role_allowed(profile, "primary_solver")
    ]
    if not primary_profiles:
        return False
    second_profiles = [
        profile
        for profile, _score in scored
        if _screening_role_allowed(profile, "independent_solver")
        or (has_domain_target and _screening_role_allowed(profile, "domain_specialist"))
    ]
    return any(
        primary.canonical_identity != second.canonical_identity
        for primary in primary_profiles
        for second in second_profiles
    )


def _legacy_neutral_capability(profile: ModelProfile, axis: str) -> bool:
    """Treat only the normalized neutral value as unknown legacy evidence."""

    return (
        not _screening_role_contract_present(profile)
        and abs(profile.capability(axis) - 0.35) <= 1e-6
    )


def _fast_direct_candidate_order(
    scored: Sequence[tuple[ModelProfile, float]],
    budget: Mapping[str, Any],
) -> list[tuple[ModelProfile, float]]:
    """Order the bounded Fast cascade by deadline feasibility and speed utility."""

    if not scored:
        return []
    # A streaming-admitted profile is not automatically a valid direct solver.
    # The pre-Fusion role contract is a hard control-plane boundary; a Fast
    # cascade must not bypass an explicit primary-solver deny just because the
    # profile is cheap or quick.
    primary_allowed = [
        row for row in scored if _screening_role_allowed(row[0], "primary_solver")
    ]
    if not primary_allowed:
        return []
    scored = primary_allowed
    max_latency_ms = max(1, int(budget.get("max_latency_ms") or 2500))
    feasible = [
        row
        for row in scored
        if _fast_profile_within_deadline(row[0], max_latency_ms)
    ]
    candidates = feasible or list(scored)
    fallback_allowance = max(0, int(budget.get("fallback_call_allowance") or 0))
    if fallback_allowance > 0:
        # A direct Fast route executes its fallback serially.  Prefer a primary
        # for which the quickest distinct, observed-latency fallback still fits
        # inside the deadline with a small transport/scheduling cushion.  This
        # prevents a barely-feasible primary from making its own recovery path
        # unreachable under ordinary network variance.
        pair_feasible = []
        for profile, score in candidates:
            if profile.p50_latency_ms is None:
                continue
            alternate_latencies = [
                int(other.p50_latency_ms)
                for other, _ in candidates
                if other.profile_id != profile.profile_id
                and other.p50_latency_ms is not None
                and int(other.p50_latency_ms) > 0
            ]
            if not alternate_latencies:
                continue
            projected_cascade_ms = (
                int(profile.p50_latency_ms)
                + min(alternate_latencies)
                + FAST_DIRECT_CASCADE_SAFETY_MARGIN_MS
            )
            if projected_cascade_ms <= max_latency_ms:
                pair_feasible.append((profile, score))
        if pair_feasible:
            candidates = pair_feasible

    def sort_key(row: tuple[ModelProfile, float]) -> tuple[float, int, float, str]:
        profile, base_score = row
        observed_latency = profile.p50_latency_ms
        latency_sort_value = int(observed_latency) if observed_latency is not None else max_latency_ms + 1
        speed_utility = (
            float(base_score) * FAST_DIRECT_BASE_SCORE_WEIGHT
            + _latency_score(profile) * FAST_DIRECT_LATENCY_WEIGHT
            + _reliability_score(profile) * FAST_DIRECT_RELIABILITY_WEIGHT
        )
        return (
            -round(speed_utility, 8),
            latency_sort_value,
            -round(float(base_score), 8),
            profile.profile_id,
        )

    return sorted(candidates, key=sort_key)


def _select_panel(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    *,
    role_blueprint: Sequence[Mapping[str, Any]],
) -> list[ModelProfile]:
    if not scored:
        return []
    max_models = int(budget.get("max_models") or 1)
    fast_light_verify = _fast_light_verify_enabled(request, analysis, budget)
    if request.public_model == "axio-fast" and not fast_light_verify:
        fast_candidates = _fast_direct_candidate_order(scored, budget)
        return [fast_candidates[0][0]] if fast_candidates else []
    selected: list[ModelProfile] = []
    seen_profiles: set[str] = set()
    # A channel replica improves availability, not cognitive diversity.  The
    # panel keeps one representative per real runtime model identity; the
    # remaining physical profiles stay in the provider replica pool.
    seen_canonical_identities: set[str] = set()
    seen_providers: set[str] = set()
    best_score = float(scored[0][1])
    provider_count = len({profile.provider for profile, _ in scored})
    target_provider_count = 1
    if max_models > 1 and provider_count > 1:
        quality_target = float(budget.get("quality_target") or 0.0)
        max_provider_target = 3 if request.public_model == "axio-pro" or quality_target >= 0.90 else 2
        target_provider_count = min(provider_count, max_models, max_provider_target)

    def add(profile: ModelProfile) -> bool:
        if (
            profile.profile_id in seen_profiles
            or profile.canonical_identity in seen_canonical_identities
            or len(selected) >= max_models
        ):
            return False
        selected.append(profile)
        seen_profiles.add(profile.profile_id)
        seen_canonical_identities.add(profile.canonical_identity)
        seen_providers.add(profile.provider)
        return True

    panel_roles = [
        str(row.get("role") or "")
        for row in role_blueprint
        if isinstance(row, Mapping) and str(row.get("role") or "")
    ]
    panel_roles = list(
        dict.fromkeys(
            [
                *panel_roles,
                *( ["judge", "synthesizer"] if request.public_model != "axio-fast" else [] ),
            ]
        )
    )

    def panel_role_allowed(profile: ModelProfile) -> bool:
        # Empty metadata remains legacy-compatible because
        # ``_screening_role_allowed`` treats it as an unrestricted profile.
        return any(
            _screening_role_allowed(profile, role) for role in panel_roles
        )

    role_targets = [
        row
        for row in role_blueprint
        if str(row.get("role")) in {
            "primary_solver",
            "independent_solver",
            "critic",
            "domain_specialist",
        }
    ]
    full_second_role_available = _distinct_full_second_role_available(
        scored,
        role_blueprint,
    )
    if not full_second_role_available:
        role_targets.extend(
            row
            for row in role_blueprint
            if isinstance(row, Mapping)
            and str(row.get("role") or "") == "short_verification"
        )
    if not role_targets:
        role_targets = [{"role": "primary_solver"}]
    for target in role_targets:
        if len(selected) >= max_models:
            break
        profile = _best_panel_profile_for_role(
            target,
            scored,
            selected=selected,
            analysis=analysis,
            prefer_new_provider=str(target.get("role"))
            in {"independent_solver", "critic", "domain_specialist", "short_verification"},
        )
        if profile is not None:
            add(profile)
    if not selected:
        for profile, _ in scored:
            if not panel_role_allowed(profile):
                continue
            add(profile)
            break
    diverse_min_score = best_score * 0.55
    for profile, score in scored:
        if len(selected) >= max_models or len(seen_providers) >= target_provider_count:
            break
        if (
            profile.provider in seen_providers
            or float(score) < diverse_min_score
            or not panel_role_allowed(profile)
        ):
            continue
        add(profile)
    for profile, _ in scored:
        if len(selected) >= max_models:
            return selected
        if not panel_role_allowed(profile):
            continue
        add(profile)
    return selected


def _latency_constrained_fusion_panel(
    *,
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    selected: Sequence[ModelProfile],
    role_blueprint: Sequence[Mapping[str, Any]],
    direct_profile: ModelProfile | None,
    initial_roles: Sequence[Mapping[str, Any]],
    stage_profile_pool: Sequence[ModelProfile] | None = None,
) -> tuple[list[ModelProfile], list[dict[str, Any]], dict[str, Any]]:
    """Search a bounded latency-feasible panel before hard Fusion admission.

    The ordinary panel is score-first and may contain a slow but capable
    profile.  Replacing roles only inside that panel cannot discover a faster
    qualified stage model.  This bounded search keeps the direct profile fixed
    as the comparison baseline, evaluates candidate panels using the exact
    initial role scheduler, and only promotes a panel when it remains within
    the hard 3x latency contract.  It is an engineering admission control, not
    a benchmark-tuned quality rule.
    """

    effective_stage_profile_pool = _merge_stage_profile_pool(selected, stage_profile_pool)
    direct_latency = direct_profile.p50_latency_ms if direct_profile is not None else None
    initial_latency, initial_known, initial_execution = _estimated_fusion_execution_latency_ms(
        selected,
        initial_roles,
        max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
        profile_pool=effective_stage_profile_pool,
    )
    direct_p95_latency = (
        _role_latency_ms(direct_profile, "primary_solver", "p95_latency_ms")
        if direct_profile is not None
        else None
    )
    initial_p95_latency, initial_p95_known, initial_p95_execution = (
        _estimated_fusion_execution_latency_p95_ms(
            selected,
            initial_roles,
            max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
            profile_pool=effective_stage_profile_pool,
        )
    )
    initial_quality = _fusion_utility_estimate(
        request,
        analysis,
        budget,
        selected,
        direct_profile,
        planned_fusion_roles=initial_roles,
        stage_profile_pool=effective_stage_profile_pool,
    )
    initial_multiplier = (
        initial_latency / max(1.0, float(direct_latency))
        if initial_known and direct_latency is not None
        else None
    )
    initial_p95_multiplier = (
        initial_p95_latency / max(1.0, float(direct_p95_latency))
        if initial_p95_known and direct_p95_latency is not None
        else None
    )
    try:
        max_latency_ms = max(1, int(budget.get("max_latency_ms") or 1))
    except (TypeError, ValueError):
        max_latency_ms = 1
    initial_p95_guard_blocked = bool(
        initial_p95_known
        and (
            initial_p95_latency > max_latency_ms
            or (
                initial_p95_multiplier is not None
                and initial_p95_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
            )
        )
    )
    receipt: dict[str, Any] = {
        "schema": "axio_fusion_api.latency_constrained_panel.v1",
        "enabled": request.public_model != "axio-fast",
        "applied": False,
        "reason": "not_applicable_for_fast_direct_path"
        if request.public_model == "axio-fast"
        else "panel_within_operational_latency_target",
        "hard_latency_multiplier_target": FUSION_LATENCY_MULTIPLIER_GUARD,
        "operational_latency_multiplier_target": FUSION_OPERATIONAL_LATENCY_TARGET,
        "direct_profile_latency_ms": round(float(direct_latency), 3)
        if direct_latency is not None
        else None,
        "direct_profile_p95_latency_ms": round(float(direct_p95_latency), 3)
        if direct_p95_latency is not None
        else None,
        "initial_latency_known": bool(initial_known and direct_latency is not None),
        "initial_estimated_latency_ms": round(float(initial_latency), 3)
        if initial_known
        else None,
        "initial_latency_multiplier_vs_direct": round(float(initial_multiplier), 4)
        if initial_multiplier is not None
        else None,
        "initial_p95_latency_known": bool(initial_p95_known and direct_p95_latency is not None),
        "initial_estimated_p95_latency_ms": round(float(initial_p95_latency), 3)
        if initial_p95_known
        else None,
        "initial_p95_latency_multiplier_vs_direct": round(float(initial_p95_multiplier), 4)
        if initial_p95_multiplier is not None
        else None,
        "initial_p95_latency_guard_blocked": initial_p95_guard_blocked,
        "optimized_estimated_latency_ms": round(float(initial_latency), 3)
        if initial_known
        else None,
        "optimized_latency_multiplier_vs_direct": round(float(initial_multiplier), 4)
        if initial_multiplier is not None
        else None,
        "optimized_estimated_p95_latency_ms": round(float(initial_p95_latency), 3)
        if initial_p95_known
        else None,
        "optimized_p95_latency_multiplier_vs_direct": round(float(initial_p95_multiplier), 4)
        if initial_p95_multiplier is not None
        else None,
        "optimized_p95_latency_guard_blocked": initial_p95_guard_blocked,
        "p95_latency_optimization_triggered": False,
        "initial_panel_size": len(selected),
        "optimized_panel_size": len(selected),
        "initial_panel_provider_count": len({profile.provider for profile in selected}),
        "optimized_panel_provider_count": len({profile.provider for profile in selected}),
        "candidate_pool_count": 0,
        "candidate_panel_evaluation_count": 0,
        "quality_floor_mode": "not_evaluated",
        "initial_fusion_expected_quality": initial_quality.get("fusion_expected_quality"),
        "optimized_fusion_expected_quality": initial_quality.get("fusion_expected_quality"),
        "initial_panel_profile_hashes": [sha256_text(profile.profile_id) for profile in selected[:24]],
        "optimized_panel_profile_hashes": [sha256_text(profile.profile_id) for profile in selected[:24]],
        "replacement_count": 0,
        "provider_diversity_relaxed_for_latency": False,
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
    }
    try:
        max_models = max(1, int(budget.get("max_models") or len(selected) or 1))
    except (TypeError, ValueError):
        max_models = max(1, len(selected) or 1)

    selected_canonical_identities = {
        profile.canonical_identity for profile in selected
    }
    candidate_roles = {
        str(row.get("role") or "")
        for row in role_blueprint
        if isinstance(row, Mapping)
        and str(row.get("role") or "")
        in {"independent_solver", "critic", "domain_specialist", "short_verification"}
    }
    distinct_role_candidate_exists = bool(
        max_models > len(selected)
        and any(
            profile.enabled
            and str(profile.health or "unknown") != "unavailable"
            and profile.canonical_identity not in selected_canonical_identities
            and any(_screening_role_allowed(profile, role) for role in candidate_roles)
            for profile, _ in scored
        )
    )
    underfilled_panel_search = len(selected) < 2 and distinct_role_candidate_exists
    if (
        request.public_model == "axio-fast"
        or direct_profile is None
        or direct_latency is None
        or not initial_known
        or initial_multiplier is None
        or max_models < 2
        or (
            len(selected) >= 2
            and initial_multiplier <= FUSION_LATENCY_MULTIPLIER_GUARD
            and not initial_p95_guard_blocked
        )
        or (len(selected) < 2 and not underfilled_panel_search)
    ):
        if request.public_model != "axio-fast" and not initial_known:
            receipt["reason"] = "unknown_latency_telemetry"
        elif (
            request.public_model != "axio-fast"
            and initial_multiplier is not None
            and initial_multiplier <= FUSION_LATENCY_MULTIPLIER_GUARD
        ):
            receipt["reason"] = "panel_within_hard_latency_guard"
        elif (
            request.public_model != "axio-fast"
            and len(selected) < 2
            and not underfilled_panel_search
        ):
            receipt["reason"] = "no_distinct_role_qualified_candidate"
        return list(selected), [dict(role) for role in initial_roles], receipt

    anchor = direct_profile
    max_models = max(2, max_models)
    # A four-profile panel is retained when the score-first plan already fits
    # the operational target.  Once the hard latency guard is violated, the
    # bounded repair searches only two- and three-profile panels: this is the
    # smallest complete shape that can keep independent experts, Judge, and
    # Synthesizer while preventing route planning itself from becoming a new
    # latency source.
    max_panel_size = min(max_models, 3)
    candidate_limit = min(
        len(scored),
        max(24, min(40, max_models * 10)),
    )
    top_profiles = [profile for profile, _ in scored[:candidate_limit]]
    fastest_profiles = [
        profile
        for profile, _ in sorted(
            scored,
            key=lambda row: (
                float(row[0].p50_latency_ms)
                if row[0].p50_latency_ms is not None
                else float("inf"),
                -float(row[1]),
                row[0].profile_id,
            ),
        )[:candidate_limit]
    ]
    stage_profiles = [
        profile
        for profile, _ in scored
        if (
            profile.p50_latency_ms is not None
            and (
                _stage_profile_eligibility(profile, "judge", analysis, budget)[0]
                or _stage_profile_eligibility(profile, "synthesizer", analysis, budget)[0]
            )
        )
    ]
    pool_by_id: dict[str, ModelProfile] = {}
    for profile in [*top_profiles, *fastest_profiles, *stage_profiles, *selected]:
        pool_by_id.setdefault(profile.profile_id, profile)
    pool_by_id.setdefault(anchor.profile_id, anchor)
    candidate_pool = list(pool_by_id.values())
    receipt["candidate_pool_count"] = len(candidate_pool)

    def evaluate_panel(
        panel: Sequence[ModelProfile],
    ) -> tuple[float, bool, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        roles = _role_assignments(
            request,
            analysis,
            panel,
            True,
            role_blueprint,
            budget=budget,
            latency_baseline_profile=anchor,
            stage_profile_pool=effective_stage_profile_pool,
        )
        latency, known, _execution = _estimated_fusion_execution_latency_ms(
            panel,
            roles,
            max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
            profile_pool=effective_stage_profile_pool,
        )
        multiplier = (
            latency / max(1.0, float(direct_latency))
            if known
            else float("inf")
        )
        quality = _fusion_utility_estimate(
            request,
            analysis,
            budget,
            panel,
            anchor,
            planned_fusion_roles=roles,
            stage_profile_pool=effective_stage_profile_pool,
        )
        p95_latency, p95_known, _p95_execution = _estimated_fusion_execution_latency_p95_ms(
            panel,
            roles,
            max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
            profile_pool=effective_stage_profile_pool,
        )
        p95_multiplier = (
            p95_latency / max(1.0, float(direct_p95_latency))
            if p95_known and direct_p95_latency is not None
            else None
        )
        p95_guard_blocked = bool(
            p95_known
            and (
                p95_latency > max_latency_ms
                or (
                    p95_multiplier is not None
                    and p95_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
                )
            )
        )
        return multiplier, known, roles, quality, {
            "latency_ms": latency,
            "provider_count": len({profile.provider for profile in panel}),
            "p50_deadline_blocked": bool(known and latency > max_latency_ms),
            "p95_latency_ms": p95_latency if p95_known else None,
            "p95_known": bool(p95_known and direct_p95_latency is not None),
            "p95_multiplier": p95_multiplier,
            "p95_guard_blocked": p95_guard_blocked,
        }

    evaluations: list[tuple[tuple[ModelProfile, ...], float, list[dict[str, Any]], dict[str, Any], dict[str, Any]]] = []
    other_profiles = [
        profile
        for profile in candidate_pool
        if profile.profile_id != anchor.profile_id
    ]
    minimum_panel_size = 2
    distinct_verification_candidate = any(
        profile.canonical_identity != anchor.canonical_identity
        and (
            _screening_role_allowed(profile, "independent_solver")
            or _screening_role_allowed(profile, "critic")
            or _screening_role_allowed(profile, "domain_specialist")
            or _screening_role_allowed(profile, "short_verification")
        )
        for profile in other_profiles
    )
    distinct_critic_candidate = any(
        profile.canonical_identity != anchor.canonical_identity
        and _screening_role_allowed(profile, "critic")
        for profile in other_profiles
    )
    if request.public_model == "axio-pro" and distinct_critic_candidate and any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "critic"
        for row in role_blueprint
    ):
        # Pro's independent-verification contract is Primary + Independent +
        # Critic.  Domain-specialist work may be trimmed under the hard
        # latency guard, but the critic cannot disappear merely because no
        # qualified replacement was discovered.
        minimum_panel_size = 3
    for panel_size in range(minimum_panel_size, max_panel_size + 1):
        for combination in combinations(other_profiles, panel_size - 1):
            panel = (anchor, *combination)
            if len({profile.canonical_identity for profile in panel}) != len(panel):
                continue
            multiplier, known, roles, quality, meta = evaluate_panel(panel)
            assigned_evidence_roles = {
                str(row.get("role") or "")
                for row in roles
                if isinstance(row, Mapping)
                and str(row.get("role") or "")
                in {"independent_solver", "critic", "domain_specialist", "short_verification"}
            }
            if not assigned_evidence_roles or not _panel_has_distinct_evidence_shape(
                request,
                roles,
            ):
                continue
            if request.public_model != "axio-fast" and not {
                "judge",
                "synthesizer",
            }.issubset(
                {
                    str(row.get("role") or "")
                    for row in roles
                    if isinstance(row, Mapping)
                }
            ):
                continue
            evaluations.append((panel, multiplier, roles, quality, meta))
    receipt["candidate_panel_evaluation_count"] = len(evaluations)
    if not evaluations:
        receipt["reason"] = "no_distinct_candidate_panel"
        return list(selected), [dict(role) for role in initial_roles], receipt

    direct_quality = float(initial_quality.get("direct_expected_quality") or 0.0)
    initial_fusion_quality = float(initial_quality.get("fusion_expected_quality") or 0.0)
    quality_floors = (
        (max(direct_quality, initial_fusion_quality - EXPERT_QUALITY_REPLACEMENT_TOLERANCE), "bounded_quality_tolerance"),
        (direct_quality, "direct_quality_floor_fallback"),
    )
    chosen = None
    for quality_floor, floor_mode in quality_floors:
        feasible = [
            row
            for row in evaluations
            if row[1] <= FUSION_LATENCY_MULTIPLIER_GUARD
            and not row[4].get("p50_deadline_blocked")
            and not row[4].get("p95_guard_blocked")
            and float(row[3].get("fusion_expected_quality") or 0.0) >= quality_floor
        ]
        if feasible:
            chosen = max(
                feasible,
                key=lambda row: (
                    float(row[3].get("fusion_expected_quality") or 0.0),
                    -float(row[1]),
                    int(row[4].get("provider_count") or 0),
                    len(row[0]),
                ),
            )
            receipt["quality_floor_mode"] = floor_mode
            break
    if chosen is None:
        receipt["reason"] = "no_panel_meets_latency_guard"
        return list(selected), [dict(role) for role in initial_roles], receipt

    panel, multiplier, roles, quality, meta = chosen
    initial_ids = {profile.profile_id for profile in selected}
    optimized_ids = {profile.profile_id for profile in panel}
    provider_target = min(
        len({profile.provider for profile, _ in scored}),
        max_models,
        3 if request.public_model == "axio-pro" else 2,
    )
    receipt.update(
        {
            "applied": True,
            "reason": "bounded_candidate_panel_meets_latency_guard",
            "optimized_estimated_latency_ms": round(float(meta["latency_ms"]), 3),
            "optimized_latency_multiplier_vs_direct": round(float(multiplier), 4),
            "optimized_estimated_p95_latency_ms": (
                round(float(meta["p95_latency_ms"]), 3)
                if meta.get("p95_latency_ms") is not None
                else None
            ),
            "optimized_p95_latency_multiplier_vs_direct": (
                round(float(meta["p95_multiplier"]), 4)
                if meta.get("p95_multiplier") is not None
                else None
            ),
            "optimized_p95_latency_guard_blocked": bool(meta.get("p95_guard_blocked")),
            "p95_latency_optimization_triggered": initial_p95_guard_blocked,
            "optimized_panel_size": len(panel),
            "optimized_panel_provider_count": int(meta["provider_count"]),
            "optimized_fusion_expected_quality": quality.get("fusion_expected_quality"),
            "optimized_panel_profile_hashes": [sha256_text(profile.profile_id) for profile in panel[:24]],
            "replacement_count": len(initial_ids.symmetric_difference(optimized_ids)) // 2,
            "provider_diversity_relaxed_for_latency": int(meta["provider_count"]) < provider_target,
        }
    )
    return list(panel), roles, receipt


def _model_selection_policy(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    selected: Sequence[ModelProfile],
    role_blueprint: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    provider_count = len({profile.provider for profile, _ in scored})
    selected_provider_count = len({profile.provider for profile in selected})
    canonical_identities_available = {
        profile.canonical_identity for profile, _ in scored
    }
    selected_canonical_identities = {
        profile.canonical_identity for profile in selected
    }
    max_models = int(budget.get("max_models") or 1)
    diversity_metrics = _panel_diversity_metrics(selected, analysis)
    target_provider_count = 1
    fast_light_verify = _fast_light_verify_enabled(request, analysis, budget)
    diversity_enabled = request.public_model != "axio-fast" or fast_light_verify
    if diversity_enabled and max_models > 1 and provider_count > 1:
        quality_target = float(budget.get("quality_target") or 0.0)
        max_provider_target = 3 if request.public_model == "axio-pro" or quality_target >= 0.90 else 2
        target_provider_count = min(provider_count, max_models, max_provider_target)
    fast_direct_cascade = request.public_model == "axio-fast" and not fast_light_verify
    fast_deadline_ms = max(1, int(budget.get("max_latency_ms") or 2500))
    fast_feasible_profiles = [
        profile
        for profile, _ in scored
        if _fast_profile_within_deadline(profile, fast_deadline_ms)
    ]
    return {
        "schema": "axio_fusion_api.model_selection_policy.v1",
        "score_first": True,
        "quality_target": float(budget.get("quality_target") or 0.0),
        "quality_target_applied": bool(budget.get("quality_target_applied")),
        "quality_pressure": float(budget.get("quality_pressure") or 0.0),
        "provider_diversity_enabled": diversity_enabled,
        "physical_profile_count_available": len(scored),
        "canonical_model_count_available": len(canonical_identities_available),
        "canonical_model_count_selected": len(selected_canonical_identities),
        "canonical_duplicate_count_selected": max(
            0, len(selected) - len(selected_canonical_identities)
        ),
        "canonical_model_panel_deduplication_enabled": True,
        "canonical_model_panel_deduplication_satisfied": len(selected)
        == len(selected_canonical_identities),
        "provider_count_available": provider_count,
        "provider_count_target": target_provider_count,
        "provider_count_selected": selected_provider_count,
        "provider_diversity_satisfied": selected_provider_count >= target_provider_count,
        "diversity_min_relative_score": 0.55,
        "error_correlation_aware_selection_enabled": True,
        "estimated_error_correlation": diversity_metrics["estimated_error_correlation"],
        "capability_complementarity": diversity_metrics["capability_complementarity"],
        "api_format_diversity": diversity_metrics["api_format_diversity"],
        "panel_diversity_receipt": diversity_metrics,
        "role_diversity_enabled": diversity_enabled,
        "role_targets": _safe_role_targets_for_policy(role_blueprint),
        "role_coverage": _role_coverage_summary(role_blueprint, selected, analysis),
        "max_models": max_models,
        "fast_direct_deadline_feasibility_enabled": fast_direct_cascade,
        "fast_direct_deadline_ms": fast_deadline_ms if fast_direct_cascade else None,
        "fast_direct_latency_feasible_candidate_count": len(fast_feasible_profiles)
        if fast_direct_cascade
        else 0,
        "fast_direct_selected_within_deadline": bool(selected)
        and _fast_profile_within_deadline(selected[0], fast_deadline_ms)
        if fast_direct_cascade
        else None,
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _role_blueprint(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> list[dict[str, Any]]:
    domains = _analysis_capability_axes(analysis)
    high_quality = _quality_target(request) >= 0.90
    risk = float(analysis.get("risk") or 0.0)
    uncertainty = float(analysis.get("uncertainty") or 0.0)
    decomposable = bool(analysis.get("decomposable"))
    targets: list[dict[str, Any]] = [
        _role_target(
            role="primary_solver",
            objective="solve_the_main_task_with_full_constraint_coverage",
            required_capabilities=[*domains, "structured_output"],
            scoring_weights={
                "domain": 0.50,
                "structured_output": 0.16,
                "critique": 0.10,
                "reliability": 0.14,
                "latency": 0.05,
                "cost": 0.05,
            },
            context_scope="original_task_plus_role_scoped_dag",
            stop_condition="candidate_answer_with_evidence_or_explicit_uncertainty",
        )
    ]
    if request.public_model != "axio-fast" or _fast_light_verify_enabled(request, analysis, budget):
        targets.append(
            _role_target(
                role="independent_solver",
                objective="produce_an_independent_candidate_from_a_different_angle",
                required_capabilities=[*domains, "structured_output"],
                scoring_weights={
                    "domain": 0.40,
                    "structured_output": 0.14,
                    "critique": 0.08,
                    "reliability": 0.12,
                    "latency": 0.12,
                    "cost": 0.10,
                    "provider_diversity": 0.04,
                },
                context_scope="original_task_plus_alternate_assumptions_and_dag",
                stop_condition="independent_candidate_or_clear_blocker",
            )
        )
    if (
        request.public_model == "axio-pro"
        or high_quality
        or risk >= 0.45
        or uncertainty >= 0.58
    ):
        targets.append(
            _role_target(
                role="critic",
                objective="find_errors_omissions_counterexamples_and_risk",
                required_capabilities=[*domains, "critique", "structured_output"],
                scoring_weights={
                    "domain": 0.14,
                    "structured_output": 0.27,
                    "critique": 0.44,
                    "reliability": 0.12,
                    "latency": 0.03,
                    "cost": 0.03,
                    "provider_diversity": 0.02,
                },
                context_scope="original_task_plus_verification_nodes_and_candidate_rubric",
                stop_condition="specific_gaps_counterexamples_or_confidence_in_no_issue",
            )
        )
    needs_specialist = (
        decomposable
        and int(budget.get("max_models") or 1) >= 4
        and (
            len(domains) >= 2
            or risk >= 0.45
            or bool(analysis.get("factuality_signal"))
            or bool(analysis.get("vertical_domain_signals"))
            or bool(analysis.get("needs_tools"))
        )
    )
    if needs_specialist:
        targets.append(
            _role_target(
                role="domain_specialist",
                objective="cover_the_strongest_domain_specific_subtask_or_tool_plan",
                required_capabilities=_domain_specialist_axes(analysis),
                scoring_weights={
                    "domain": 0.56,
                    "structured_output": 0.12,
                    "critique": 0.08,
                    "reliability": 0.10,
                    "latency": 0.05,
                    "cost": 0.05,
                    "provider_diversity": 0.04,
                },
                context_scope="domain_subtask_nodes_only",
                stop_condition="specialist_findings_with_evidence_and_unresolved_questions",
            )
        )
    if request.public_model != "axio-fast":
        targets.extend(
            [
                _role_target(
                    role="judge",
                    objective="compare_candidates_extract_consensus_contradictions_gaps_unique_insights_and_rank",
                    required_capabilities=["critique", "structured_output", *domains],
                    scoring_weights={
                        "domain": 0.20,
                        "structured_output": 0.34,
                        "critique": 0.32,
                        "reliability": 0.10,
                        "latency": 0.02,
                        "cost": 0.02,
                    },
                    context_scope="candidate_packets_local_rubric_and_role_scoped_dag",
                    stop_condition="valid_structured_judge_record",
                ),
                _role_target(
                    role="synthesizer",
                    objective="write_one_final_answer_from_judge_record_and_top_ranked_candidates",
                    required_capabilities=["structured_output", "long_context", *domains],
                    scoring_weights={
                        "domain": 0.28,
                        "structured_output": 0.36,
                        "critique": 0.14,
                        "reliability": 0.12,
                        "latency": 0.04,
                        "cost": 0.04,
                        "context": 0.02,
                    },
                    context_scope="judge_record_top_candidates_and_hash_receipts_for_compressed_candidates",
                    stop_condition="single_user_facing_answer_with_dispute_labels",
                ),
            ]
        )
    return targets


def _augment_pro_role_blueprint_for_screened_specialist(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    role_blueprint: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Expose an explicit screened narrow seat before panel selection.

    A conservative lexical decomposition detector may produce only one
    primary-capable profile even though the pre-Fusion handoff contains a
    different model explicitly screened for a narrow specialist role.  Only
    an explicit screening contract can trigger this augmentation; legacy
    neutral profiles therefore retain their historical panel behavior.
    """

    blueprint = [dict(row) for row in role_blueprint]
    if request.public_model not in {"axio-terra", "axio-pro"}:
        return blueprint
    if int(budget.get("max_models") or 1) < 2:
        return blueprint
    has_domain_target = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") == "domain_specialist"
        for row in blueprint
    )
    has_screened_domain_specialist = any(
        _screening_role_contract_present(profile)
        and _screening_role_allowed(profile, "domain_specialist")
        and not _screening_role_allowed(profile, "primary_solver")
        for profile, _ in scored
    )
    if request.public_model == "axio-pro" and not has_domain_target and has_screened_domain_specialist:
        blueprint.append(
            _role_target(
                role="domain_specialist",
                objective="cover_the_strongest_domain_specific_subtask_or_tool_plan",
                required_capabilities=_domain_specialist_axes(analysis),
                scoring_weights={
                    "domain": 0.56,
                    "structured_output": 0.12,
                    "critique": 0.08,
                    "reliability": 0.10,
                    "latency": 0.05,
                    "cost": 0.05,
                    "provider_diversity": 0.04,
                },
                context_scope="domain_subtask_nodes_only",
                stop_condition="specialist_findings_with_evidence_and_unresolved_questions",
            )
        )

    has_qualified_full_second_role = _distinct_full_second_role_available(
        scored,
        blueprint,
    )
    has_short_target = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") == "short_verification"
        for row in blueprint
    )
    has_screened_short_verifier = any(
        _screening_role_contract_present(profile)
        and _screening_role_allowed(profile, "short_verification")
        and not any(
            _screening_role_allowed(profile, role)
            for role in (
                "primary_solver",
                "independent_solver",
                "critic",
                "domain_specialist",
                "judge",
                "synthesizer",
            )
        )
        for profile, _ in scored
    )
    if not has_qualified_full_second_role and has_screened_short_verifier and not has_short_target:
        blueprint.append(
            _role_target(
                role="short_verification",
                objective="verify_one_critical_claim_constraint_or_risk_without_solving_the_full_task",
                required_capabilities=["critique", "structured_output"],
                scoring_weights={
                    "critique": 0.46,
                    "structured_output": 0.28,
                    "reliability": 0.14,
                    "latency": 0.07,
                    "cost": 0.05,
                    "provider_diversity": 0.04,
                },
                context_scope="one_key_claim_or_constraint_only",
                stop_condition="short_structured_verdict_with_issues_and_check",
            )
        )
    return blueprint


def _role_target(
    *,
    role: str,
    objective: str,
    required_capabilities: Sequence[str],
    scoring_weights: Mapping[str, float],
    context_scope: str,
    stop_condition: str,
) -> dict[str, Any]:
    axes = [axis for axis in required_capabilities if axis in CAPABILITY_AXES or axis == "safety"]
    return {
        "role": role,
        "objective": objective,
        "required_capabilities": list(dict.fromkeys(axes)),
        "scoring_weights": {
            str(key): round(float(value), 4)
            for key, value in scoring_weights.items()
        },
        "context_scope": context_scope,
        "stop_condition": stop_condition,
        "raw_prompt_persisted": False,
        "raw_model_names_persisted": False,
    }


def _best_panel_profile_for_role(
    target: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    *,
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
    prefer_new_provider: bool,
) -> ModelProfile | None:
    selected_ids = {profile.profile_id for profile in selected}
    selected_canonical_identities = {
        profile.canonical_identity for profile in selected
    }
    selected_providers = {profile.provider for profile in selected}
    candidates = []
    for profile, base_score in scored:
        if (
            profile.profile_id in selected_ids
            or profile.canonical_identity in selected_canonical_identities
        ):
            continue
        if not _screening_role_allowed(profile, str(target.get("role") or "")):
            continue
        role_score = _role_fit_score(
            profile,
            target,
            analysis,
            base_score=float(base_score),
            selected_providers=selected_providers,
            prefer_new_provider=prefer_new_provider,
        )
        role_score += _incremental_panel_complementarity(profile, selected, analysis)
        candidates.append((profile, role_score))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return candidates[0][0]


def _assigned_profile_for_role(
    role: str,
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
    role_blueprint: Sequence[Mapping[str, Any]],
    *,
    used_profile_ids: set[str],
) -> ModelProfile | None:
    target = _role_blueprint_target(role_blueprint, role)
    unused = [profile for profile in selected if profile.profile_id not in used_profile_ids]
    unused_allowed = [
        profile for profile in unused if _screening_role_allowed(profile, role)
    ]
    if unused_allowed:
        pool = unused_allowed
    else:
        # Independent expert seats must remain genuinely independent.  If the
        # only role-qualified profile has already been assigned, omitting the
        # seat is safer than presenting the same model as a second vote.
        if role != "primary_solver":
            return None
        pool = [
            profile
            for profile in selected
            if _screening_role_allowed(profile, role)
        ]
    if not pool:
        return None
    ranked = sorted(
        pool,
        key=lambda profile: _role_fit_score(
            profile,
            target,
            analysis,
            base_score=0.0,
            selected_providers=set(),
            prefer_new_provider=False,
        ),
        reverse=True,
    )
    return ranked[0]


def _role_runtime_identity(role: Mapping[str, Any]) -> str:
    model = role.get("model") if isinstance(role.get("model"), Mapping) else {}
    return str(
        model.get("runtime_canonical_identity_sha256")
        or model.get("canonical_model_id_sha256")
        or model.get("profile_id")
        or ""
    ).strip()


def _has_distinct_full_evidence_role(roles: Sequence[Mapping[str, Any]]) -> bool:
    """Return whether a full-evidence role is a distinct canonical branch."""

    primary_identity = next(
        (
            _role_runtime_identity(row)
            for row in roles
            if isinstance(row, Mapping)
            and str(row.get("role") or "") == "primary_solver"
        ),
        "",
    )
    if not primary_identity:
        return False
    return any(
        str(row.get("role") or "")
        in {"independent_solver", "critic", "domain_specialist"}
        and _role_runtime_identity(row)
        and _role_runtime_identity(row) != primary_identity
        for row in roles
        if isinstance(row, Mapping)
    )


def _panel_has_distinct_evidence_shape(
    request: FusionRequest,
    roles: Sequence[Mapping[str, Any]],
) -> bool:
    """Keep latency repair from replacing evidence with role-less models."""

    if request.public_model == "axio-fast":
        return True
    primary_identity = next(
        (
            _role_runtime_identity(row)
            for row in roles
            if isinstance(row, Mapping)
            and str(row.get("role") or "") == "primary_solver"
        ),
        "",
    )
    if not primary_identity:
        return False
    return any(
        str(row.get("role") or "")
        in {
            "independent_solver",
            "critic",
            "domain_specialist",
            "short_verification",
        }
        and _role_runtime_identity(row)
        and _role_runtime_identity(row) != primary_identity
        for row in roles
        if isinstance(row, Mapping)
    )


def _role_assignment(
    role: str,
    assignment: str,
    profile: ModelProfile,
    role_blueprint: Sequence[Mapping[str, Any]],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    target = _role_blueprint_target(role_blueprint, role)
    assignment = {
        "role": role,
        "assignment": assignment,
        "model": profile.safe_dict(),
        "role_intent": {
            "schema": "axio_fusion_api.role_intent.v1",
            "objective": str(target.get("objective") or assignment),
            "required_capabilities": list(target.get("required_capabilities") or _analysis_capability_axes(analysis)),
            "context_scope": str(target.get("context_scope") or "role_scoped_context"),
            "stop_condition": str(target.get("stop_condition") or "bounded_role_output"),
            "selection_score": round(
                _role_fit_score(
                    profile,
                    target,
                    analysis,
                    base_score=0.0,
                    selected_providers=set(),
                    prefer_new_provider=False,
                ),
                4,
            ),
            "raw_prompt_persisted": False,
            "raw_model_names_persisted": False,
        },
    }
    if role == "short_verification":
        assignment.update(
            {
                "evidence_scope": "narrow_verification_only",
                "counts_as_full_independent_solver": False,
                "native_tools_allowed": False,
                "full_task_solution_allowed": False,
            }
        )
    return assignment


def _role_fit_score(
    profile: ModelProfile,
    target: Mapping[str, Any],
    analysis: Mapping[str, Any],
    *,
    base_score: float,
    selected_providers: set[str],
    prefer_new_provider: bool,
) -> float:
    weights = target.get("scoring_weights") if isinstance(target.get("scoring_weights"), Mapping) else {}
    axes = [
        str(axis)
        for axis in target.get("required_capabilities", [])
        if str(axis) in CAPABILITY_AXES
    ] or _analysis_capability_axes(analysis)
    domain_axes = [
        axis
        for axis in axes
        if axis not in {"structured_output", "critique", "long_context"}
    ] or _analysis_capability_axes(analysis)
    domain = _routing_domain_average(profile, domain_axes)
    score = float(base_score) * 0.06
    score += domain * _weight(weights, "domain", 0.40)
    score += _routing_capability(profile, "structured_output") * _weight(weights, "structured_output", 0.14)
    score += _routing_capability(profile, "critique") * _weight(weights, "critique", 0.12)
    score += _reliability_score(profile) * _weight(weights, "reliability", 0.12)
    score += _latency_score(profile) * _weight(weights, "latency", 0.06)
    score += _cost_efficiency(profile) * _weight(weights, "cost", 0.06)
    score += _routing_capability(profile, "long_context") * _weight(weights, "context", 0.0)
    if prefer_new_provider and profile.provider not in selected_providers:
        score += _weight(weights, "provider_diversity", 0.03)
    if bool(analysis.get("needs_tools")) and profile.tool_calling_eligible:
        score += 0.03
    return score


def _routing_capability(profile: ModelProfile, axis: str) -> float:
    """Use a screened prior only for role routing while preserving calibration.

    A profile carrying an explicit pre-Fusion contract with a neutral runtime
    value has unknown operational evidence for that axis.  The research prior
    can still help choose the role it was screened for; it is never copied to
    ``profile.capabilities`` and never used as an evaluation score.
    """

    operational = profile.capability(axis)
    if (
        _screening_role_contract_present(profile)
        and abs(operational - 0.35) <= 1e-6
        and profile.screening_capability(axis) > 0.0
    ):
        return profile.screening_capability(axis)
    return operational


def _routing_domain_average(profile: ModelProfile, axes: Sequence[str]) -> float:
    valid_axes = [axis for axis in axes if axis in CAPABILITY_AXES]
    valid_axes = valid_axes or ["daily_work"]
    return sum(_routing_capability(profile, axis) for axis in valid_axes) / max(1, len(valid_axes))


def _weight(weights: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(weights.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _role_blueprint_target(role_blueprint: Sequence[Mapping[str, Any]], role: str) -> Mapping[str, Any]:
    for row in role_blueprint:
        if isinstance(row, Mapping) and str(row.get("role")) == role:
            return row
    return {"role": role, "required_capabilities": []}


def _analysis_capability_axes(analysis: Mapping[str, Any]) -> list[str]:
    axes = [
        str(domain)
        for domain in analysis.get("domains", []) or ["daily_work"]
        if str(domain) in CAPABILITY_AXES
    ]
    return list(dict.fromkeys(axes or ["daily_work"]))


def _domain_specialist_axes(analysis: Mapping[str, Any]) -> list[str]:
    axes = _analysis_capability_axes(analysis)
    vertical_signals = {
        str(item)
        for item in analysis.get("vertical_domain_signals", [])
        if str(item)
    } if isinstance(analysis.get("vertical_domain_signals"), list) else set()
    if bool(analysis.get("factuality_signal")):
        return ["critique", "structured_output", "logic"]
    if "medical" in vertical_signals:
        return ["science_knowledge", "logic", "critique"]
    if "finance" in vertical_signals:
        return ["math", "logic", "critique"]
    if "legal" in vertical_signals or "policy" in vertical_signals:
        return ["logic", "critique", "daily_work"]
    if "consulting" in vertical_signals:
        return ["daily_work", "structured_output", "logic"]
    if "agentic_tool_calling" in axes:
        return ["agentic_tool_calling", "structured_output", "critique"]
    if "code" in axes:
        return ["code", "logic", "critique"]
    if "math" in axes:
        return ["math", "logic", "critique"]
    if "science_knowledge" in axes:
        return ["science_knowledge", "logic", "critique"]
    if "multilingual" in axes:
        return ["multilingual", "daily_work", "structured_output"]
    return axes


def _domain_average(profile: ModelProfile, axes: Sequence[str]) -> float:
    selected = [axis for axis in axes if axis in CAPABILITY_AXES]
    if not selected:
        selected = ["daily_work"]
    return sum(profile.capability(axis) for axis in selected) / max(1, len(selected))


def _profile_has_relevant_capability_evidence(
    profile: ModelProfile,
    axes: Sequence[str],
) -> bool:
    """Distinguish declared/calibrated capability from neutral defaults.

    A newly discovered model is normalized with a neutral 0.35 vector. That
    value is a conservative serving prior, not evidence that the model is
    strong in a domain. Declarations and later calibration move an axis away
    from the neutral value. This distinction lets an uncalibrated portfolio
    use transport diversity without pretending to know model intelligence.
    """

    for axis in axes:
        if axis not in CAPABILITY_AXES:
            continue
        if abs(profile.capability(axis) - 0.35) > 1e-6:
            return True
    return False


def _safe_role_targets_for_policy(role_blueprint: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": str(row.get("role") or ""),
            "required_capabilities": [
                str(axis)
                for axis in row.get("required_capabilities", [])
                if str(axis)
            ][:8],
            "context_scope": str(row.get("context_scope") or "")[:120],
            "raw_model_names_persisted": False,
        }
        for row in role_blueprint
        if isinstance(row, Mapping)
    ][:12]


def _role_coverage_summary(
    role_blueprint: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    role_rows = []
    for row in role_blueprint:
        if not isinstance(row, Mapping):
            continue
        role = str(row.get("role") or "")
        if role in {"judge", "synthesizer"}:
            continue
        best = _best_panel_profile_for_role(
            row,
            [(profile, 0.0) for profile in selected],
            selected=[],
            analysis=analysis,
            prefer_new_provider=False,
        )
        role_rows.append(
            {
                "role": role,
                "covered": best is not None,
                "best_fit_score": round(
                    _role_fit_score(
                        best,
                        row,
                        analysis,
                        base_score=0.0,
                        selected_providers=set(),
                        prefer_new_provider=False,
                    ),
                    4,
                ) if best is not None else 0.0,
                "best_profile_sha256": sha256_text(best.profile_id) if best is not None else "",
                "raw_profile_id_persisted": False,
            }
        )
    return {
        "schema": "axio_fusion_api.role_coverage_summary.v1",
        "role_count": len(role_rows),
        "covered_role_count": sum(1 for row in role_rows if row["covered"]),
        "roles": role_rows,
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _role_gate_receipt(
    *,
    required_roles: Sequence[str],
    roles: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile],
    gate_name: str,
    candidate_profiles: Sequence[ModelProfile] | None = None,
) -> dict[str, Any]:
    """Bind screened role capacity to the exact route shape.

    The prefusion registry can contain a live, stream-tested model that is
    intentionally limited to a narrow role.  This receipt makes that
    distinction explicit before admission and keeps missing mandatory seats
    observable without persisting provider or model identifiers.
    """

    normalized_required = list(
        dict.fromkeys(
            str(role).strip().casefold()
            for role in required_roles
            if str(role).strip()
        )
    )
    assigned_roles = {
        str(row.get("role") or "").strip().casefold()
        for row in roles
        if isinstance(row, Mapping) and str(row.get("role") or "").strip()
    }
    candidate_pool = list(candidate_profiles) if candidate_profiles is not None else list(selected)
    candidate_counts = {
        role: sum(_screening_role_allowed(profile, role) for profile in candidate_pool)
        for role in normalized_required
    }
    missing_roles = [role for role in normalized_required if role not in assigned_roles]
    return {
        "schema": "axio_fusion_api.role_gate_receipt.v1",
        "gate_name": str(gate_name or "route")[:64],
        "required_roles": normalized_required,
        "assigned_roles": sorted(assigned_roles),
        "missing_roles": missing_roles,
        "candidate_count_by_role": candidate_counts,
        "passed": not missing_roles,
        "explicit_deny_is_hard_block": True,
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _provider_fusion_required_roles(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    selected: Sequence[ModelProfile],
    role_blueprint: Sequence[Mapping[str, Any]],
    *,
    assigned_roles: Sequence[Mapping[str, Any]] = (),
) -> list[str]:
    """Return mandatory seats for a provider Judge/Synthesizer route."""

    required = ["primary_solver"]
    verification_enabled = request.public_model != "axio-fast" or _fast_light_verify_enabled(
        request, analysis, budget
    )
    if verification_enabled and len(selected) >= 2:
        assigned_role_names = {
            str(row.get("role") or "")
            for row in assigned_roles
            if isinstance(row, Mapping)
        }
        if "independent_solver" in assigned_role_names:
            required.append("independent_solver")
        elif "domain_specialist" in assigned_role_names:
            # A screened specialist is a real second evidence source for its
            # narrow subtask.  It is not relabeled as an independent solver;
            # the receipt preserves the role actually admitted by research.
            required.append("domain_specialist")
        elif "short_verification" in assigned_role_names:
            # A narrow verifier is the last-resort second evidence seat.  It
            # remains explicitly narrow in the gate; it is never renamed to a
            # solver role or allowed to clear a missing solver contract.
            required.append("short_verification")
        else:
            # Keep the blocker explicit when the panel has no second role.
            required.append("independent_solver")
    if verification_enabled and len(selected) >= 3 and any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "critic"
        for row in role_blueprint
    ) and any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "critic"
        for row in assigned_roles
    ):
        required.append("critic")
    # ``domain_specialist`` is an optional coverage seat.  The initial call
    # planner may trim it under an explicit model-call ceiling, so it must not
    # be treated as a mandatory provider-fusion blocker.
    if request.public_model != "axio-fast":
        required.extend(["judge", "synthesizer"])
    return list(dict.fromkeys(required))


def _local_consensus_required_roles(
    request: FusionRequest,
    selected: Sequence[ModelProfile],
    role_blueprint: Sequence[Mapping[str, Any]],
    *,
    assigned_roles: Sequence[Mapping[str, Any]] = (),
) -> list[str]:
    assigned_role_names = {
        str(row.get("role") or "")
        for row in assigned_roles
        if isinstance(row, Mapping)
    }
    required = ["primary_solver"]
    if "independent_solver" in assigned_role_names:
        required.append("independent_solver")
    elif "domain_specialist" in assigned_role_names:
        required.append("domain_specialist")
    elif "short_verification" in assigned_role_names:
        required.append("short_verification")
    elif "critic" in assigned_role_names:
        # A screened Critic is a full-evidence role, but it is not relabeled as
        # an independent solver. This is the bounded cross-provider fallback
        # when the pre-Fusion role contract has no independent_solver seat.
        required.append("critic")
    else:
        required.append("independent_solver")
    if request.public_model == "axio-pro" and len(selected) >= 3 and any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "critic"
        for row in role_blueprint
    ) and "critic" in assigned_role_names:
        required.append("critic")
    return required


def _fusion_admission(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    selected: Sequence[ModelProfile],
    *,
    planned_fusion_roles: Sequence[Mapping[str, Any]],
    direct_roles: Sequence[Mapping[str, Any]],
    initial_fusion_call_plan: Mapping[str, Any],
    initial_fusion_resource_admission: Mapping[str, Any],
    local_consensus_plan: Mapping[str, Any] | None = None,
    direct_profile: ModelProfile | None = None,
    routing_policy: Mapping[str, Any] | None = None,
    role_gate: Mapping[str, Any] | None = None,
    stage_profile_pool: Sequence[ModelProfile] | None = None,
) -> dict[str, Any]:
    direct_profile = direct_profile or _profile_for_assigned_role(
        direct_roles,
        selected,
        "primary_solver",
    ) or (scored[0][0] if scored else None)
    local_consensus_plan = (
        local_consensus_plan
        if isinstance(local_consensus_plan, Mapping)
        else {}
    )
    role_gate = role_gate if isinstance(role_gate, Mapping) else {}
    direct_role_gate = (
        role_gate.get("direct")
        if isinstance(role_gate.get("direct"), Mapping)
        else {}
    )
    provider_role_gate = (
        role_gate.get("provider_fusion")
        if isinstance(role_gate.get("provider_fusion"), Mapping)
        else {}
    )
    local_role_gate = (
        role_gate.get("local_consensus")
        if isinstance(role_gate.get("local_consensus"), Mapping)
        else {}
    )
    threshold = _fusion_admission_threshold(request, analysis, budget)
    estimate = _fusion_utility_estimate(
        request,
        analysis,
        budget,
        selected,
        direct_profile,
        planned_fusion_roles=planned_fusion_roles,
        stage_profile_pool=stage_profile_pool,
    )
    blocked_reasons: list[str] = []
    force_reasons: list[str] = []
    fast_light_verify = _fast_light_verify_enabled(request, analysis, budget)
    if request.policy.fusion_depth >= request.policy.max_fusion_depth:
        blocked_reasons.append("max_fusion_depth_reached")
    if request.public_model == "axio-fast" and not fast_light_verify:
        blocked_reasons.append("fast_tier_prefers_direct_cascade")
    for role in direct_role_gate.get("missing_roles", []):
        blocked_reasons.append(f"screening_role_gate_blocked_{str(role)[:64]}")
    provider_role_blockers = [
        f"screening_role_gate_blocked_{str(role)[:64]}"
        for role in provider_role_gate.get("missing_roles", [])
        if str(role)
    ]
    local_role_blockers = [
        f"screening_role_gate_blocked_{str(role)[:64]}"
        for role in local_role_gate.get("missing_roles", [])
        if str(role)
    ]
    blocked_reasons.extend(provider_role_blockers)
    # An infeasible local-consensus search has no execution contract to gate;
    # its empty role list must not block an otherwise valid direct/provider
    # route.  Once the local shape is feasible, however, its role gate is hard.
    if local_consensus_plan.get("feasible") is True:
        blocked_reasons.extend(local_role_blockers)
    local_consensus_candidate_count = _safe_nonnegative_int(
        local_consensus_plan.get("panel_size")
    )
    if len(selected) < 2 and not (
        local_consensus_plan.get("feasible") is True
        and local_consensus_candidate_count >= 2
    ):
        blocked_reasons.append("insufficient_independent_models")
    if bool(initial_fusion_call_plan.get("blocked_by_call_budget")) or (
        initial_fusion_call_plan.get("call_budget_meets_complete_floor") is False
        and (request.public_model != "axio-fast" or fast_light_verify)
    ):
        blocked_reasons.append("max_total_model_calls_below_complete_fusion_floor")
    for reason in initial_fusion_resource_admission.get("blocked_reasons", []):
        normalized = str(reason or "")
        if normalized in {
            "initial_fusion_cost_exceeds_request_budget",
            "initial_fusion_latency_exceeds_request_deadline",
        }:
            blocked_reasons.append(normalized)
    if estimate["latency_multiplier_guard_blocked"]:
        blocked_reasons.append("fusion_latency_exceeds_3x_single_model_guard")
    if estimate["p95_latency_deadline_guard_blocked"]:
        blocked_reasons.append("fusion_p95_latency_exceeds_request_deadline")
    if estimate["p95_latency_multiplier_guard_blocked"]:
        blocked_reasons.append("fusion_p95_latency_exceeds_3x_single_model_guard")
    if bool(analysis.get("fusion_plugin_requested")):
        force_reasons.append("fusion_plugin_requested")
    if isinstance(routing_policy, Mapping) and routing_policy.get("force_fusion") is True:
        force_reasons.append("active_routing_policy_requires_fusion")
    if float(analysis.get("quality_target") or 0.0) >= 0.82:
        force_reasons.append("quality_target_requires_fusion")
    if request.public_model == "axio-pro" and len(selected) >= 2:
        force_reasons.append("pro_tier_independent_verification_policy")
    if request.public_model == "axio-fast" and fast_light_verify and len(selected) >= 2:
        force_reasons.append("fast_light_verify_policy")
    if float(analysis.get("risk") or 0.0) >= 0.55 and len(selected) >= 2:
        force_reasons.append("high_risk_requires_independent_verification")
    if _non_fusion_tools_declared(request) and len(selected) >= 2 and (request.public_model != "axio-fast" or fast_light_verify):
        force_reasons.append("tool_task_requires_independent_plan_check")
    utility_score = float(estimate["utility_score"])
    threshold_passed = utility_score >= threshold
    if _terra_direct_cascade_preferred(request, analysis, threshold_passed):
        blocked_reasons.append("low_risk_direct_cascade_preferred")
    local_trigger_reasons = {
        "fusion_latency_exceeds_3x_single_model_guard",
        "fusion_p95_latency_exceeds_request_deadline",
        "fusion_p95_latency_exceeds_3x_single_model_guard",
        "initial_fusion_cost_exceeds_request_budget",
        "initial_fusion_latency_exceeds_request_deadline",
        "max_total_model_calls_below_complete_fusion_floor",
        *provider_role_blockers,
    }
    local_provider_blocked_reasons = [
        str(reason)
        for reason in blocked_reasons
        if str(reason) in local_trigger_reasons
    ]
    local_disallowed_reasons = [
        str(reason)
        for reason in blocked_reasons
        if str(reason) not in local_trigger_reasons
    ]
    local_can_replace_provider_plan = bool(
        local_consensus_plan.get("feasible")
        and local_provider_blocked_reasons
        and not local_disallowed_reasons
        and (
            not bool(budget.get("caller_max_total_model_calls_explicit"))
            or int(budget.get("max_total_model_calls") or 0)
            >= max(
                _safe_nonnegative_int(local_consensus_plan.get("panel_size")) + 2,
                _safe_nonnegative_int(
                    initial_fusion_call_plan.get("minimum_complete_fusion_call_count")
                ),
            )
        )
        and request.public_model in {"axio-terra", "axio-pro"}
    )
    finalization_mode = "local_consensus" if local_can_replace_provider_plan else (
        "provider_judge_synthesis" if request.public_model != "axio-fast" else "direct"
    )
    effective_blocked_reasons = (
        [] if local_can_replace_provider_plan else list(blocked_reasons)
    )
    local_consensus_activation = bool(
        local_can_replace_provider_plan
        and request.public_model in {"axio-terra", "axio-pro"}
    )
    activated = bool(
        local_consensus_activation
        or (
            not effective_blocked_reasons
            and (bool(force_reasons) or threshold_passed)
        )
    )
    if effective_blocked_reasons:
        decision_reason = effective_blocked_reasons[0]
    elif local_can_replace_provider_plan and activated:
        decision_reason = "local_consensus_within_3x_latency_guard"
    elif force_reasons:
        decision_reason = force_reasons[0]
    elif threshold_passed:
        decision_reason = "expected_quality_gain_exceeds_cost_latency_penalty"
    else:
        decision_reason = "expected_gain_below_cost_latency_threshold"
    return {
        "schema": "axio_fusion_api.fusion_admission.v1",
        "activated": activated,
        "fusion_finalization_mode": finalization_mode if activated else "direct",
        "decision_reason": decision_reason,
        "blocked_reasons": effective_blocked_reasons,
        "provider_plan_blocked_reasons": local_provider_blocked_reasons,
        "local_consensus_provider_plan_replaced": bool(
            local_can_replace_provider_plan and activated
        ),
        "force_reasons": force_reasons,
        "threshold": round(threshold, 4),
        "threshold_passed": threshold_passed,
        "utility_model": {
            "objective": "expected_quality_gain_minus_cost_latency_and_error_correlation_plus_risk_reduction",
            "quality_weight": 1.0,
            "cost_penalty_weight": estimate["cost_penalty_weight"],
            "latency_penalty_weight": estimate["latency_penalty_weight"],
            "error_correlation_penalty_weight": estimate["error_correlation_penalty_weight"],
            "risk_reduction_weight": estimate["risk_reduction_weight"],
            "raw_prompt_persisted": False,
        },
        "direct_candidate": {
            "profile_id_sha256": sha256_text(direct_profile.profile_id) if direct_profile else "",
            "provider_sha256": sha256_text(direct_profile.provider) if direct_profile else "",
            "expected_quality": estimate["direct_expected_quality"],
            "estimated_cost_usd": estimate["direct_estimated_cost_usd"],
            "estimated_latency_ms": estimate["direct_estimated_latency_ms"],
            "p95_estimated_latency_ms": estimate["direct_p95_estimated_latency_ms"],
            "raw_profile_id_persisted": False,
        },
        "fusion_candidate": {
            "finalization_mode": finalization_mode if activated else "direct",
            "selected_model_count": (
                _safe_nonnegative_int(local_consensus_plan.get("panel_size"))
                if local_can_replace_provider_plan
                else len(selected)
            ),
            "selected_profile_hashes": (
                list(local_consensus_plan.get("panel_profile_hashes", []))
                if local_can_replace_provider_plan
                else [sha256_text(profile.profile_id) for profile in selected[:24]]
            ),
            "selected_provider_hashes": (
                list(local_consensus_plan.get("panel_provider_hashes", []))
                if local_can_replace_provider_plan
                else list(dict.fromkeys(sha256_text(profile.provider) for profile in selected[:24]))
            ),
            "expected_quality": (
                local_consensus_plan.get("expected_quality")
                if local_can_replace_provider_plan
                else estimate["fusion_expected_quality"]
            ),
            "estimated_cost_usd": (
                local_consensus_plan.get("estimated_cost_usd")
                if local_can_replace_provider_plan
                else estimate["fusion_estimated_cost_usd"]
            ),
            "estimated_latency_ms": (
                local_consensus_plan.get("estimated_latency_ms")
                if local_can_replace_provider_plan
                else estimate["fusion_estimated_latency_ms"]
            ),
            "p95_estimated_latency_ms": (
                None
                if local_can_replace_provider_plan
                else estimate["fusion_p95_estimated_latency_ms"]
            ),
            "provider_diversity": estimate["provider_diversity"],
            "capability_coverage": estimate["capability_coverage"],
            "capability_complementarity": estimate["capability_complementarity"],
            "estimated_error_correlation": estimate["estimated_error_correlation"],
            "judge_strength": estimate["judge_strength"],
            "planned_initial_execution": (
                local_consensus_plan.get("planned_execution")
                if local_can_replace_provider_plan
                else estimate["fusion_latency_execution"]
            ),
            "planned_initial_p95_execution": (
                None
                if local_can_replace_provider_plan
                else estimate["fusion_p95_latency_execution"]
            ),
            "planned_initial_cost": (
                local_consensus_plan.get("planned_cost")
                if local_can_replace_provider_plan
                else estimate["fusion_cost_execution"]
            ),
            "initial_execution_profile_count": (
                _safe_nonnegative_int(local_consensus_plan.get("panel_size"))
                if local_can_replace_provider_plan
                else estimate["initial_execution_profile_count"]
            ),
            "raw_profile_id_persisted": False,
            "raw_model_names_persisted": False,
        },
        "initial_fusion_call_plan": _safe_initial_fusion_call_plan(initial_fusion_call_plan),
        "initial_fusion_resource_admission": _safe_initial_fusion_resource_admission(
            initial_fusion_resource_admission
        ),
        "role_gate": role_gate,
        "local_consensus_plan": _safe_local_consensus_plan(local_consensus_plan),
        "expected_quality_gain": (
            local_consensus_plan.get("expected_quality_delta")
            if local_can_replace_provider_plan
            else estimate["expected_quality_gain"]
        ),
        "risk_reduction_credit": estimate["risk_reduction_credit"],
        "extra_cost_usd": (
            round(
                max(
                    0.0,
                    float(local_consensus_plan.get("estimated_cost_usd") or 0.0)
                    - float(estimate.get("direct_estimated_cost_usd") or 0.0),
                ),
                8,
            )
            if local_can_replace_provider_plan and local_consensus_plan.get("cost_known")
            else estimate["extra_cost_usd"]
        ),
        "extra_latency_ms": (
            round(
                max(
                    0.0,
                    float(local_consensus_plan.get("estimated_latency_ms") or 0.0)
                    - float(estimate.get("direct_estimated_latency_ms") or 0.0),
                ),
                3,
            )
            if local_can_replace_provider_plan
            else estimate["extra_latency_ms"]
        ),
        "cost_penalty": estimate["cost_penalty"],
        "latency_penalty": estimate["latency_penalty"],
        "latency_multiplier_vs_single_model": (
            local_consensus_plan.get("latency_multiplier_vs_direct")
            if local_can_replace_provider_plan
            else estimate["latency_multiplier_vs_single_model"]
        ),
        "p95_latency_known": estimate["p95_latency_known"],
        "direct_p95_estimated_latency_ms": estimate[
            "direct_p95_estimated_latency_ms"
        ],
        "fusion_p95_estimated_latency_ms": estimate[
            "fusion_p95_estimated_latency_ms"
        ],
        "p95_latency_multiplier_vs_single_model": estimate[
            "p95_latency_multiplier_vs_single_model"
        ],
        "p95_latency_deadline_guard_blocked": estimate[
            "p95_latency_deadline_guard_blocked"
        ],
        "p95_latency_multiplier_guard_blocked": estimate[
            "p95_latency_multiplier_guard_blocked"
        ],
        "p95_latency_guard_blocked": estimate["p95_latency_guard_blocked"],
        "latency_multiplier_guard": {
            "enabled": True,
            "target_max_vs_single_model": FUSION_LATENCY_MULTIPLIER_GUARD,
            "blocked": False if local_can_replace_provider_plan else bool(
                estimate["latency_multiplier_guard_blocked"]
                or estimate["p95_latency_guard_blocked"]
            ),
            "latency_known": True if local_can_replace_provider_plan else estimate["latency_known"],
            "provider_plan_blocked": bool(
                estimate["latency_multiplier_guard_blocked"]
                or estimate["p95_latency_guard_blocked"]
            ),
            "p50_multiplier_vs_single_model": estimate[
                "latency_multiplier_vs_single_model"
            ],
            "p95_latency_known": estimate["p95_latency_known"],
            "p95_latency_ms": estimate["fusion_p95_estimated_latency_ms"],
            "direct_p95_latency_ms": estimate[
                "direct_p95_estimated_latency_ms"
            ],
            "p95_multiplier_vs_single_model": estimate[
                "p95_latency_multiplier_vs_single_model"
            ],
            "p95_deadline_blocked": estimate[
                "p95_latency_deadline_guard_blocked"
            ],
            "p95_multiplier_guard_blocked": estimate[
                "p95_latency_multiplier_guard_blocked"
            ],
            "p95_provider_plan_blocked": estimate["p95_latency_guard_blocked"],
            "policy": "admitted execution shape must keep known p50 and p95 latency within the request deadline and 3x direct single-model guard",
        },
        "error_correlation_penalty": estimate["error_correlation_penalty"],
        "utility_score": estimate["utility_score"],
        "pricing_known": (
            local_consensus_plan.get("cost_known")
            if local_can_replace_provider_plan
            else estimate["pricing_known"]
        ),
        "latency_known": True if local_can_replace_provider_plan else estimate["latency_known"],
        "quality_target": float(analysis.get("quality_target") or 0.0),
        "complexity": float(analysis.get("complexity") or 0.0),
        "risk": float(analysis.get("risk") or 0.0),
        "uncertainty": float(analysis.get("uncertainty") or 0.0),
        "raw_prompt_persisted": False,
        "raw_profile_id_persisted": False,
        "secrets_persisted": False,
    }


def _terra_direct_cascade_preferred(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    utility_threshold_passed: bool,
) -> bool:
    """Keep ordinary short Terra requests on the one-provider cascade path.

    Portfolio diversity can produce a small modeled gain even when the task
    itself has no verification need.  For that narrow case, a direct answer
    plus one failure fallback is both the more honest latency policy and the
    intended ``axio-terra`` operating mode.  Explicit quality, safety,
    factuality, tool, and decomposition signals retain fusion eligibility.
    """

    return bool(
        utility_threshold_passed
        and request.public_model == "axio-terra"
        and float(analysis.get("quality_target") or 0.0) < 0.82
        and float(analysis.get("complexity") or 0.0) < 0.42
        and float(analysis.get("risk") or 0.0) < 0.35
        and float(analysis.get("uncertainty") or 0.0) < 0.48
        and not bool(analysis.get("fusion_plugin_requested"))
        and not bool(analysis.get("needs_tools"))
        and not bool(analysis.get("factuality_signal"))
        and not bool(analysis.get("needs_current_information"))
        and not bool(analysis.get("vertical_domain_signals"))
        and not bool(analysis.get("decomposable"))
    )


def _fusion_utility_estimate(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    selected: Sequence[ModelProfile],
    direct_profile: ModelProfile | None,
    *,
    planned_fusion_roles: Sequence[Mapping[str, Any]],
    stage_profile_pool: Sequence[ModelProfile] | None = None,
) -> dict[str, Any]:
    direct_quality = _expected_profile_quality(direct_profile, analysis) if direct_profile is not None else 0.0
    execution_profiles = _planned_execution_profiles(
        planned_fusion_roles,
        selected,
        profile_pool=stage_profile_pool,
    )
    provider_diversity = _provider_diversity_score(execution_profiles)
    capability_coverage = _capability_coverage_score(execution_profiles, analysis)
    complementarity = _capability_complementarity_score(execution_profiles, analysis)
    error_correlation = _estimated_error_correlation(execution_profiles, analysis)
    judge_strength = _judge_strength(execution_profiles)
    role_count_bonus = min(0.06, max(0, len(execution_profiles) - 1) * 0.018)
    fusion_quality = min(
        1.0,
        direct_quality
        + provider_diversity * 0.030
        + capability_coverage * 0.045
        + complementarity * 0.055
        + judge_strength * 0.045
        + role_count_bonus
        + (0.035 if bool(analysis.get("decomposable")) and len(execution_profiles) >= 3 else 0.0)
        + float(analysis.get("quality_pressure") or 0.0) * 0.035,
    )
    raw_gain = max(0.0, fusion_quality - direct_quality)
    demand = _fusion_demand_score(request, analysis)
    expected_gain = raw_gain * (0.45 + 0.75 * demand)
    risk_credit = (
        float(analysis.get("risk") or 0.0)
        * float(analysis.get("uncertainty") or 0.0)
        * (0.035 + 0.035 * min(1.0, max(0.0, float(analysis.get("quality_pressure") or 0.0))))
    )
    direct_cost = _estimated_route_cost_usd(
        [direct_profile] if direct_profile is not None else [],
        analysis,
        max_output_tokens=request.max_output_tokens,
    )
    fusion_cost, fusion_cost_execution = _estimated_fusion_execution_cost_usd(
        selected,
        planned_fusion_roles,
        analysis,
        max_output_tokens=request.max_output_tokens,
        profile_pool=stage_profile_pool,
    )
    pricing_known = direct_cost is not None and fusion_cost is not None
    extra_cost = None if not pricing_known else max(0.0, float(fusion_cost) - float(direct_cost))
    direct_latency_value = (
        _role_latency_ms(direct_profile, "primary_solver", "p50_latency_ms")
        if direct_profile is not None
        else None
    )
    direct_latency = float(direct_latency_value or 0.0)
    direct_latency_known = direct_latency_value is not None and direct_latency > 0.0
    fusion_latency, fusion_latency_known, fusion_latency_execution = _estimated_fusion_execution_latency_ms(
        selected,
        planned_fusion_roles,
        max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
        profile_pool=stage_profile_pool,
    )
    extra_latency = max(0.0, fusion_latency - direct_latency)
    latency_multiplier = (
        fusion_latency / max(1.0, direct_latency)
        if direct_latency > 0.0
        else float("inf") if fusion_latency > 0.0 else 1.0
    )
    latency_known = direct_latency_known and fusion_latency_known
    latency_multiplier_guard_blocked = bool(
        latency_known and latency_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
    )
    direct_p95_value = (
        _role_latency_ms(direct_profile, "primary_solver", "p95_latency_ms")
        if direct_profile is not None
        else None
    )
    direct_p95_latency = float(direct_p95_value or 0.0)
    direct_p95_latency_known = bool(direct_p95_latency > 0.0)
    fusion_p95_latency, fusion_p95_latency_known, fusion_p95_latency_execution = (
        _estimated_fusion_execution_latency_p95_ms(
            selected,
            planned_fusion_roles,
            max_parallel=max(1, int(budget.get("max_parallel_experts") or 1)),
            profile_pool=stage_profile_pool,
        )
    )
    p95_latency_known = bool(
        direct_p95_latency_known and fusion_p95_latency_known
    )
    p95_latency_multiplier = (
        fusion_p95_latency / max(1.0, direct_p95_latency)
        if p95_latency_known and direct_p95_latency > 0.0
        else None
    )
    max_latency = max(1.0, float(budget.get("max_latency_ms") or 10_000))
    p95_latency_deadline_guard_blocked = bool(
        p95_latency_known and fusion_p95_latency > max_latency
    )
    p95_latency_multiplier_guard_blocked = bool(
        p95_latency_multiplier is not None
        and p95_latency_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
    )
    p95_latency_guard_blocked = bool(
        p95_latency_deadline_guard_blocked
        or p95_latency_multiplier_guard_blocked
    )
    cost_weight = 0.055 if request.public_model == "axio-terra" else 0.035
    latency_weight = 0.050 if request.public_model == "axio-terra" else 0.035
    risk_weight = 1.0
    max_cost = max(0.000001, float(budget.get("max_cost_usd") or 0.001))
    if pricing_known:
        cost_penalty = min(0.18, (float(extra_cost or 0.0) / max_cost) * cost_weight)
    else:
        cost_penalty = min(0.10, max(0, len(execution_profiles) - 1) * cost_weight * 0.35)
    latency_penalty = min(0.14, (extra_latency / max_latency) * latency_weight)
    correlation_penalty = max(0.0, error_correlation - 0.72) * 0.055
    utility = expected_gain + risk_credit * risk_weight - cost_penalty - latency_penalty - correlation_penalty
    return {
        "direct_expected_quality": round(direct_quality, 4),
        "fusion_expected_quality": round(fusion_quality, 4),
        "expected_quality_gain": round(expected_gain, 4),
        "risk_reduction_credit": round(risk_credit, 4),
        "direct_estimated_cost_usd": round(direct_cost, 8) if direct_cost is not None else None,
        "fusion_estimated_cost_usd": round(fusion_cost, 8) if fusion_cost is not None else None,
        "fusion_cost_execution": fusion_cost_execution,
        "extra_cost_usd": round(extra_cost, 8) if extra_cost is not None else None,
        "direct_estimated_latency_ms": round(direct_latency, 3),
        "fusion_estimated_latency_ms": round(fusion_latency, 3),
        "fusion_latency_execution": fusion_latency_execution,
        "fusion_p95_latency_execution": fusion_p95_latency_execution,
        "initial_execution_profile_count": len(execution_profiles),
        "extra_latency_ms": round(extra_latency, 3),
        "provider_diversity": round(provider_diversity, 4),
        "capability_coverage": round(capability_coverage, 4),
        "capability_complementarity": round(complementarity, 4),
        "estimated_error_correlation": round(error_correlation, 4),
        "error_correlation_penalty": round(correlation_penalty, 4),
        "judge_strength": round(judge_strength, 4),
        "cost_penalty": round(cost_penalty, 4),
        "latency_penalty": round(latency_penalty, 4),
        "utility_score": round(utility, 4),
        "pricing_known": pricing_known,
        "latency_known": latency_known,
        "latency_multiplier_vs_single_model": round(latency_multiplier, 4)
        if math.isfinite(latency_multiplier)
        else None,
        "latency_multiplier_guard_blocked": latency_multiplier_guard_blocked,
        "direct_p95_estimated_latency_ms": round(direct_p95_latency, 3)
        if direct_p95_latency_known
        else None,
        "fusion_p95_estimated_latency_ms": round(fusion_p95_latency, 3)
        if fusion_p95_latency_known
        else None,
        "p95_latency_known": p95_latency_known,
        "p95_latency_multiplier_vs_single_model": round(p95_latency_multiplier, 4)
        if p95_latency_multiplier is not None
        else None,
        "p95_latency_deadline_guard_blocked": p95_latency_deadline_guard_blocked,
        "p95_latency_multiplier_guard_blocked": p95_latency_multiplier_guard_blocked,
        "p95_latency_guard_blocked": p95_latency_guard_blocked,
        "cost_penalty_weight": cost_weight,
        "latency_penalty_weight": latency_weight,
        "error_correlation_penalty_weight": 0.055,
        "risk_reduction_weight": risk_weight,
    }


def _fusion_admission_threshold(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> float:
    if request.public_model == "axio-pro":
        base = 0.025
    elif request.public_model == "axio-terra":
        base = 0.065
    else:
        base = 0.20
    base -= min(0.025, float(analysis.get("quality_pressure") or 0.0) * 0.025)
    base -= 0.015 if float(analysis.get("risk") or 0.0) >= 0.45 else 0.0
    base += 0.010 if float(budget.get("max_latency_ms") or 0.0) <= 3000 else 0.0
    return max(0.005, round(base, 4))


def _fusion_demand_score(request: FusionRequest, analysis: Mapping[str, Any]) -> float:
    demand = (
        float(analysis.get("complexity") or 0.0) * 0.42
        + float(analysis.get("risk") or 0.0) * 0.22
        + float(analysis.get("uncertainty") or 0.0) * 0.22
        + float(analysis.get("quality_pressure") or 0.0) * 0.24
    )
    if request.public_model == "axio-pro":
        demand += 0.16
    elif request.public_model == "axio-fast" and _fast_light_verify_requested(request, analysis):
        demand += 0.08
    if bool(analysis.get("fusion_plugin_requested")):
        demand += 0.18
    if bool(analysis.get("decomposable")):
        demand += 0.08
    return max(0.0, min(1.0, demand))


def _fast_light_verify_requested(request: FusionRequest, analysis: Mapping[str, Any]) -> bool:
    if request.public_model != "axio-fast":
        return False
    quality_target = float(analysis.get("quality_target") or _quality_target(request))
    complexity = float(analysis.get("complexity") or 0.0)
    risk = float(analysis.get("risk") or 0.0)
    uncertainty = float(analysis.get("uncertainty") or 0.0)
    return bool(
        quality_target >= 0.82
        or bool(analysis.get("routing_policy_fast_light_verify"))
        or risk >= 0.55
        or (uncertainty >= 0.58 and complexity >= 0.46)
        or _non_fusion_tools_declared(request)
    )


def _fast_light_verify_enabled(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> bool:
    return bool(
        _fast_light_verify_requested(request, analysis)
        and int(budget.get("max_models") or 1) >= 2
    )


def _expected_profile_quality(profile: ModelProfile | None, analysis: Mapping[str, Any]) -> float:
    if profile is None:
        return 0.0
    domains = _analysis_capability_axes(analysis)
    domain = _domain_average(profile, domains)
    score = (
        domain * 0.52
        + profile.capability("structured_output") * 0.14
        + profile.capability("critique") * 0.08
        + profile.capability("long_context") * 0.04
        + _reliability_score(profile) * 0.16
        + _latency_score(profile) * 0.03
        + _cost_efficiency(profile) * 0.03
    )
    if bool(analysis.get("needs_tools")) and profile.tool_calling_eligible:
        score += 0.03
    return max(0.0, min(1.0, score))


def _provider_diversity_score(selected: Sequence[ModelProfile]) -> float:
    if len(selected) <= 1:
        return 0.0
    return len({profile.provider for profile in selected}) / max(1, len(selected))


def _api_format_diversity_score(selected: Sequence[ModelProfile]) -> float:
    if len(selected) <= 1:
        return 0.0
    return len({profile.api_format for profile in selected}) / max(1, len(selected))


def _capability_coverage_score(selected: Sequence[ModelProfile], analysis: Mapping[str, Any]) -> float:
    if not selected:
        return 0.0
    axes = list(dict.fromkeys([*_analysis_capability_axes(analysis), "structured_output", "critique"]))
    per_axis = []
    for axis in axes:
        per_axis.append(max(profile.capability(axis) for profile in selected))
    return sum(per_axis) / max(1, len(per_axis))


def _capability_complementarity_score(selected: Sequence[ModelProfile], analysis: Mapping[str, Any]) -> float:
    if len(selected) <= 1:
        return 0.0
    axes = list(dict.fromkeys([*_analysis_capability_axes(analysis), "structured_output", "critique", "long_context"]))
    gains = []
    for axis in axes:
        values = sorted((profile.capability(axis) for profile in selected), reverse=True)
        if not values:
            continue
        best = values[0]
        average = sum(values) / len(values)
        second = values[1] if len(values) > 1 else average
        unique_strength = max(0.0, best - average)
        backup_strength = min(best, second)
        gains.append(min(1.0, unique_strength * 1.4 + backup_strength * 0.35))
    role_spread = _role_strength_spread(selected, analysis)
    return max(0.0, min(1.0, (sum(gains) / max(1, len(gains))) * 0.70 + role_spread * 0.30))


def _role_strength_spread(selected: Sequence[ModelProfile], analysis: Mapping[str, Any]) -> float:
    if not selected:
        return 0.0
    domains = _analysis_capability_axes(analysis)
    role_scores = {
        "domain": max(_domain_average(profile, domains) for profile in selected),
        "critique": max(profile.capability("critique") for profile in selected),
        "structured": max(profile.capability("structured_output") for profile in selected),
        "long_context": max(profile.capability("long_context") for profile in selected),
        "tool": max(
            max(profile.capability("agentic_tool_calling"), 0.78 if profile.tool_calling_eligible else 0.0)
            for profile in selected
        ),
    }
    covered = sum(1 for value in role_scores.values() if value >= 0.65)
    return covered / max(1, len(role_scores))


def _estimated_error_correlation(selected: Sequence[ModelProfile], analysis: Mapping[str, Any]) -> float:
    if len(selected) <= 1:
        return 1.0 if selected else 0.0
    pair_scores = []
    for left_index, left in enumerate(selected):
        for right in selected[left_index + 1:]:
            pair_scores.append(_pair_error_correlation(left, right, analysis))
    return max(0.0, min(1.0, sum(pair_scores) / max(1, len(pair_scores))))


def _pair_error_correlation(left: ModelProfile, right: ModelProfile, analysis: Mapping[str, Any]) -> float:
    # Two channels for the same underlying model are availability replicas.
    # They must never be priced as independent error evidence.
    if left.canonical_identity == right.canonical_identity:
        return 1.0
    capability_similarity = _capability_similarity(left, right, analysis)
    score = 0.16 + capability_similarity * 0.38
    if left.provider == right.provider:
        score += 0.26
    if left.api_format == right.api_format:
        score += 0.06
    if bool(set(left.privacy_tags).intersection(set(right.privacy_tags))):
        score += 0.02
    latency_gap = abs(float(left.p50_latency_ms or 1500) - float(right.p50_latency_ms or 1500))
    if latency_gap <= 250:
        score += 0.02
    if _domain_leader_axis(left, analysis) != _domain_leader_axis(right, analysis):
        score -= 0.08
    return max(0.0, min(1.0, score))


def _capability_similarity(left: ModelProfile, right: ModelProfile, analysis: Mapping[str, Any]) -> float:
    axes = list(dict.fromkeys([*_analysis_capability_axes(analysis), "structured_output", "critique", "long_context", "agentic_tool_calling"]))
    deltas = [abs(left.capability(axis) - right.capability(axis)) for axis in axes]
    return max(0.0, min(1.0, 1.0 - sum(deltas) / max(1, len(deltas))))


def _domain_leader_axis(profile: ModelProfile, analysis: Mapping[str, Any]) -> str:
    axes = list(dict.fromkeys([*_analysis_capability_axes(analysis), "structured_output", "critique", "agentic_tool_calling"]))
    return max(axes, key=lambda axis: profile.capability(axis)) if axes else "daily_work"


def _incremental_panel_complementarity(
    profile: ModelProfile,
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
) -> float:
    if not selected:
        return 0.0
    before = _panel_diversity_metrics(selected, analysis)
    after = _panel_diversity_metrics([*selected, profile], analysis)
    complementarity_gain = after["capability_complementarity"] - before["capability_complementarity"]
    correlation_drop = before["estimated_error_correlation"] - after["estimated_error_correlation"]
    api_gain = after["api_format_diversity"] - before["api_format_diversity"]
    return complementarity_gain * 0.08 + correlation_drop * 0.05 + max(0.0, api_gain) * 0.015


def _panel_diversity_metrics(
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    providers = [profile.provider for profile in selected]
    api_formats = [profile.api_format for profile in selected]
    canonical_identities = [profile.canonical_identity for profile in selected]
    return {
        "schema": "axio_fusion_api.panel_diversity_receipt.v1",
        "selected_model_count": len(selected),
        "canonical_model_count": len(set(canonical_identities)),
        "canonical_duplicate_count": max(0, len(selected) - len(set(canonical_identities))),
        "canonical_model_panel_deduplication_satisfied": len(selected)
        == len(set(canonical_identities)),
        "provider_count": len(set(providers)),
        "api_format_count": len(set(api_formats)),
        "provider_diversity": round(_provider_diversity_score(selected), 4),
        "api_format_diversity": round(_api_format_diversity_score(selected), 4),
        "capability_coverage": round(_capability_coverage_score(selected, analysis), 4),
        "capability_complementarity": round(_capability_complementarity_score(selected, analysis), 4),
        "estimated_error_correlation": round(_estimated_error_correlation(selected, analysis), 4),
        "selection_goal": "maximize_capability_coverage_while_lowering_correlated_errors",
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _judge_strength(selected: Sequence[ModelProfile]) -> float:
    if not selected:
        return 0.0
    return max((profile.capability("critique") + profile.capability("structured_output")) / 2.0 for profile in selected)


def _estimated_route_cost_usd(
    profiles: Sequence[ModelProfile | None],
    analysis: Mapping[str, Any],
    *,
    include_judge_and_synth: bool = False,
    max_output_tokens: int | None = None,
) -> float | None:
    clean = [profile for profile in profiles if profile is not None]
    if not clean:
        return None
    if any(profile.input_cost_per_million is None or profile.output_cost_per_million is None for profile in clean):
        return None
    input_tokens = _estimated_input_tokens_for_route(analysis)
    output_tokens = _estimated_role_output_tokens(
        max_output_tokens=max_output_tokens,
        kind="model_role",
    )
    total = 0.0
    for profile in clean:
        total += _profile_call_cost_usd(profile, input_tokens=input_tokens, output_tokens=output_tokens)
    if include_judge_and_synth and clean:
        judge = _best_judge(clean)
        synth = _best_synthesizer(clean, analysis)
        if judge is not None:
            total += _profile_call_cost_usd(
                judge,
                input_tokens=max(input_tokens, output_tokens * min(3, len(clean))),
                output_tokens=_estimated_role_output_tokens(
                    max_output_tokens=max_output_tokens,
                    kind="judge",
                ),
            )
        if synth is not None:
            total += _profile_call_cost_usd(
                synth,
                input_tokens=max(input_tokens, output_tokens * min(2, len(clean))),
                output_tokens=_estimated_role_output_tokens(
                    max_output_tokens=max_output_tokens,
                    kind="synthesizer",
                ),
            )
    return total


def _planned_execution_profiles(
    roles: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile | None],
    *,
    profile_pool: Sequence[ModelProfile] | None = None,
) -> list[ModelProfile]:
    clean = [profile for profile in selected if profile is not None]
    selected_by_id = {profile.profile_id: profile for profile in clean}
    for profile in profile_pool or ():
        if profile is not None:
            selected_by_id.setdefault(profile.profile_id, profile)
    profiles: list[ModelProfile] = []
    for role in roles:
        if not isinstance(role, Mapping):
            continue
        model = role.get("model") if isinstance(role.get("model"), Mapping) else {}
        profile = selected_by_id.get(str(model.get("profile_id") or ""))
        if profile is not None:
            profiles.append(profile)
    return profiles


def _estimated_fusion_execution_cost_usd(
    selected: Sequence[ModelProfile | None],
    planned_roles: Sequence[Mapping[str, Any]],
    analysis: Mapping[str, Any],
    *,
    max_output_tokens: int | None = None,
    profile_pool: Sequence[ModelProfile] | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """Estimate the initial assigned role schedule with role-specific budgets."""

    execution_profiles = _planned_execution_profiles(
        planned_roles,
        selected,
        profile_pool=profile_pool,
    )
    if not execution_profiles:
        return None, _fusion_cost_execution_receipt([], analysis, pricing_known=False)
    pricing_known = all(
        profile.input_cost_per_million is not None and profile.output_cost_per_million is not None
        for profile in execution_profiles
    )
    receipt = _fusion_cost_execution_receipt(execution_profiles, analysis, pricing_known=pricing_known)
    if not pricing_known:
        return None, receipt
    input_tokens = _estimated_input_tokens_for_route(analysis)
    expert_roles = set(_FUSION_EXPERT_ROLE_NAMES)
    total = 0.0
    role_costs: list[float] = []
    for role in planned_roles:
        if not isinstance(role, Mapping):
            continue
        model = role.get("model") if isinstance(role.get("model"), Mapping) else {}
        profile_id = str(model.get("profile_id") or "")
        profile = next((item for item in execution_profiles if item.profile_id == profile_id), None)
        if profile is None:
            continue
        role_name = str(role.get("role") or "")
        if role_name in expert_roles:
            role_input_tokens = input_tokens
            role_output_tokens = _estimated_role_output_tokens(
                max_output_tokens=max_output_tokens,
                kind="model_role",
            )
        elif role_name == "judge":
            role_input_tokens = max(
                input_tokens,
                _estimated_role_output_tokens(
                    max_output_tokens=max_output_tokens,
                    kind="model_role",
                )
                * min(3, len(_planned_expert_profiles(planned_roles, execution_profiles))),
            )
            role_output_tokens = _estimated_role_output_tokens(
                max_output_tokens=max_output_tokens,
                kind="judge",
            )
        elif role_name == "synthesizer":
            role_input_tokens = max(
                input_tokens,
                _estimated_role_output_tokens(
                    max_output_tokens=max_output_tokens,
                    kind="model_role",
                )
                * min(2, len(_planned_expert_profiles(planned_roles, execution_profiles))),
            )
            role_output_tokens = _estimated_role_output_tokens(
                max_output_tokens=max_output_tokens,
                kind="synthesizer",
            )
        else:
            continue
        cost = _profile_call_cost_usd(profile, input_tokens=role_input_tokens, output_tokens=role_output_tokens)
        total += cost
        role_costs.append(cost)
    receipt["role_call_count"] = len(role_costs)
    receipt["estimated_total_cost_usd"] = round(total, 8)
    return total, receipt


def _fusion_cost_execution_receipt(
    profiles: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
    *,
    pricing_known: bool,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.initial_execution_cost_estimate.v1",
        "basis": "assigned_runtime_roles_before_data_dependent_repair_or_escalation",
        "profile_count": len(profiles),
        "profile_hashes": [sha256_text(profile.profile_id) for profile in profiles],
        "pricing_known": bool(pricing_known),
        "estimated_input_tokens_per_expert": _estimated_input_tokens_for_route(analysis),
        "role_call_count": 0,
        "estimated_total_cost_usd": None,
        "optional_repair_or_escalation_included": False,
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _profile_call_cost_usd(profile: ModelProfile, *, input_tokens: int, output_tokens: int) -> float:
    input_cost = float(profile.input_cost_per_million or 0.0)
    output_cost = float(profile.output_cost_per_million or 0.0)
    return (max(0, input_tokens) * input_cost + max(0, output_tokens) * output_cost) / 1_000_000


def _estimated_input_tokens_for_route(analysis: Mapping[str, Any]) -> int:
    steps = max(1, int(analysis.get("estimated_steps") or 1))
    complexity = max(0.0, min(1.0, float(analysis.get("complexity") or 0.0)))
    return int(256 + steps * 128 + complexity * 900)


def _estimated_role_output_tokens(*, max_output_tokens: int | None, kind: str) -> int:
    """Mirror the runtime's initial output reservation policy for admission."""

    if max_output_tokens is not None:
        try:
            return max(1, min(8192, int(max_output_tokens)))
        except (TypeError, ValueError):
            pass
    if kind == "judge":
        return ROUTE_COST_JUDGE_OUTPUT_TOKENS
    if kind == "synthesizer":
        return ROUTE_COST_SYNTHESIZER_OUTPUT_TOKENS
    return ROUTE_COST_EXPERT_OUTPUT_TOKENS


def _estimated_route_latency_ms(
    profiles: Sequence[ModelProfile | None],
    *,
    include_judge_and_synth: bool = False,
    max_parallel: int = 1,
) -> tuple[float, bool]:
    clean = [profile for profile in profiles if profile is not None]
    if not clean:
        return 0.0, False
    known = all(profile.p50_latency_ms is not None for profile in clean)
    latencies = [float(profile.p50_latency_ms or 1500) for profile in clean]
    if include_judge_and_synth and clean:
        parallel = max(1, int(max_parallel or 1))
        expert_latency = _parallel_expert_phase_latency_ms(
            latencies,
            max_parallel=parallel,
            profiles=clean,
        )
        judge = _best_judge(clean)
        synth = _best_synthesizer(clean, {"domains": ["daily_work"]})
        if judge is None or synth is None:
            return expert_latency, False
        if judge.p50_latency_ms is None or synth.p50_latency_ms is None:
            return expert_latency, False
        judge_latency = float(judge.p50_latency_ms or 1500)
        synth_latency = float(synth.p50_latency_ms or 1500)
        return expert_latency + judge_latency + synth_latency, known
    return latencies[0], known


def _profile_for_assigned_role(
    roles: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile],
    role_name: str,
    *,
    profile_pool: Sequence[ModelProfile] | None = None,
) -> ModelProfile | None:
    selected_by_id = {profile.profile_id: profile for profile in selected}
    for profile in profile_pool or ():
        selected_by_id.setdefault(profile.profile_id, profile)
    for role in roles:
        if not isinstance(role, Mapping) or str(role.get("role") or "") != role_name:
            continue
        model = role.get("model") if isinstance(role.get("model"), Mapping) else {}
        profile_id = str(model.get("profile_id") or "")
        if profile_id in selected_by_id:
            return selected_by_id[profile_id]
    return None


def _assigned_role_profile_pairs(
    roles: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile],
    *,
    role_names: set[str] | frozenset[str],
    profile_pool: Sequence[ModelProfile] | None = None,
) -> list[tuple[str, ModelProfile]]:
    """Resolve the concrete profile and role for each assigned call."""

    selected_by_id = {profile.profile_id: profile for profile in selected}
    for profile in profile_pool or ():
        selected_by_id.setdefault(profile.profile_id, profile)
    normalized_names = {
        " ".join(str(name or "").strip().casefold().split())
        for name in role_names
    }
    pairs: list[tuple[str, ModelProfile]] = []
    for row in roles:
        if not isinstance(row, Mapping):
            continue
        role = " ".join(str(row.get("role") or "").strip().casefold().split())
        if role not in normalized_names:
            continue
        model = row.get("model") if isinstance(row.get("model"), Mapping) else {}
        profile = selected_by_id.get(str(model.get("profile_id") or ""))
        if profile is not None:
            pairs.append((role, profile))
    return pairs


def _role_latency_ms(
    profile: ModelProfile,
    role: str,
    latency_attribute: str,
) -> float | None:
    """Return calibrated role latency, falling back to the profile latency."""

    fallback = getattr(profile, latency_attribute, None)
    admission = profile.screening_role_admission
    admission = admission if isinstance(admission, Mapping) else {}
    operational = admission.get("operational_role_probe")
    operational = operational if isinstance(operational, Mapping) else {}
    role_latency = operational.get("role_latency")
    role_latency = role_latency if isinstance(role_latency, Mapping) else {}
    normalized_role = " ".join(str(role or "").strip().casefold().split())
    row = role_latency.get(normalized_role)
    row = row if isinstance(row, Mapping) else {}
    if row.get("all_samples_eligible") is True:
        value = row.get(latency_attribute)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and math.isfinite(parsed) and parsed > 0.0:
            return parsed
    try:
        parsed_fallback = float(fallback)
    except (TypeError, ValueError):
        return None
    return parsed_fallback if math.isfinite(parsed_fallback) and parsed_fallback > 0.0 else None


def _merge_profile_pool(
    selected: Sequence[ModelProfile | None],
    profile_pool: Sequence[ModelProfile] | None,
) -> list[ModelProfile]:
    """Resolve selected experts plus non-evidence stage-only profiles by id."""

    merged: list[ModelProfile] = []
    seen: set[str] = set()
    for profile in [*selected, *(profile_pool or ())]:
        if profile is None or profile.profile_id in seen:
            continue
        seen.add(profile.profile_id)
        merged.append(profile)
    return merged


def _merge_stage_profile_pool(
    selected: Sequence[ModelProfile | None],
    profile_pool: Sequence[ModelProfile] | None,
) -> list[ModelProfile]:
    """Add only explicit pre-Fusion-screened profiles to the stage pool.

    Legacy callers may provide neutral profiles without a screening contract.
    Those profiles remain valid selected experts, but they must not silently
    become a new mandatory control-stage candidate merely because they happen
    to be faster.
    """

    screened_pool = [
        profile
        for profile in profile_pool or ()
        if _screening_role_contract_present(profile)
    ]
    return _merge_profile_pool(selected, screened_pool)


def _planned_expert_profiles(
    roles: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile],
) -> list[ModelProfile]:
    selected_by_id = {profile.profile_id: profile for profile in selected}
    expert_roles = set(_FUSION_EXPERT_ROLE_NAMES)
    profiles: list[ModelProfile] = []
    for role in roles:
        if not isinstance(role, Mapping) or str(role.get("role") or "") not in expert_roles:
            continue
        model = role.get("model") if isinstance(role.get("model"), Mapping) else {}
        profile = selected_by_id.get(str(model.get("profile_id") or ""))
        if profile is not None:
            profiles.append(profile)
    return profiles


def _estimated_fusion_execution_latency_ms(
    selected: Sequence[ModelProfile | None],
    planned_roles: Sequence[Mapping[str, Any]],
    *,
    max_parallel: int,
    profile_pool: Sequence[ModelProfile] | None = None,
) -> tuple[float, bool, dict[str, Any]]:
    return _estimated_fusion_execution_latency_quantile_ms(
        selected,
        planned_roles,
        max_parallel=max_parallel,
        profile_pool=profile_pool,
        latency_attribute="p50_latency_ms",
        latency_quantile="p50",
    )


def _estimated_fusion_execution_latency_p95_ms(
    selected: Sequence[ModelProfile | None],
    planned_roles: Sequence[Mapping[str, Any]],
    *,
    max_parallel: int,
    profile_pool: Sequence[ModelProfile] | None = None,
) -> tuple[float, bool, dict[str, Any]]:
    """Estimate the same initial schedule from measured p95 role telemetry.

    A missing p95 remains unknown.  Callers may display the estimate, but
    must not turn the fallback arithmetic into a hard p95 admission failure.
    """

    return _estimated_fusion_execution_latency_quantile_ms(
        selected,
        planned_roles,
        max_parallel=max_parallel,
        profile_pool=profile_pool,
        latency_attribute="p95_latency_ms",
        latency_quantile="p95",
    )


def _estimated_fusion_execution_latency_quantile_ms(
    selected: Sequence[ModelProfile | None],
    planned_roles: Sequence[Mapping[str, Any]],
    *,
    max_parallel: int,
    profile_pool: Sequence[ModelProfile] | None,
    latency_attribute: str,
    latency_quantile: str,
) -> tuple[float, bool, dict[str, Any]]:
    """Estimate the assigned expert/control-stage sequence at one quantile.

    The role assignment and provider-capacity semantics are shared by p50 and
    p95.  Only the measured profile field changes, which keeps the two guards
    from drifting apart as the orchestration graph evolves.
    """

    clean = [profile for profile in selected if profile is not None]
    if not clean:
        return 0.0, False, _fusion_latency_execution_receipt(
            [],
            None,
            None,
            max_parallel=max_parallel,
            latency_quantile=latency_quantile,
        )
    expert_role_profiles = _assigned_role_profile_pairs(
        planned_roles,
        clean,
        role_names={*_FUSION_EXPERT_ROLE_NAMES, "backup_solver"},
    )
    expert_profiles = [profile for _, profile in expert_role_profiles]
    judge_profile = _profile_for_assigned_role(
        planned_roles,
        clean,
        "judge",
        profile_pool=profile_pool,
    )
    synthesizer_profile = _profile_for_assigned_role(
        planned_roles,
        clean,
        "synthesizer",
        profile_pool=profile_pool,
    )
    latency_profiles = [*expert_profiles]
    if judge_profile is not None:
        latency_profiles.append(judge_profile)
    if synthesizer_profile is not None:
        latency_profiles.append(synthesizer_profile)
    expert_latency_values = [
        _role_latency_ms(profile, role, latency_attribute)
        for role, profile in expert_role_profiles
    ]
    judge_latency_value = (
        _role_latency_ms(judge_profile, "judge", latency_attribute)
        if judge_profile is not None
        else None
    )
    synthesizer_latency_value = (
        _role_latency_ms(synthesizer_profile, "synthesizer", latency_attribute)
        if synthesizer_profile is not None
        else None
    )
    measured_values = [
        *expert_latency_values,
        *([judge_latency_value] if judge_profile is not None else []),
        *([synthesizer_latency_value] if synthesizer_profile is not None else []),
    ]
    known = bool(latency_profiles) and all(
        value is not None and value > 0.0 for value in measured_values
    )

    def latency(value: float | None) -> float:
        return float(value) if value is not None and value > 0.0 else 1500.0

    expert_latencies = [latency(value) for value in expert_latency_values]
    provider_serialization_adjusted = _panel_contains_serialized_provider_pair(expert_profiles)
    expert_phase = _parallel_expert_phase_latency_ms(
        expert_latencies,
        max_parallel=max_parallel,
        profiles=expert_profiles,
    )
    judge_latency = latency(judge_latency_value) if judge_profile is not None else 0.0
    synthesis_latency = (
        latency(synthesizer_latency_value) if synthesizer_profile is not None else 0.0
    )
    total = expert_phase + judge_latency + synthesis_latency
    receipt = _fusion_latency_execution_receipt(
        expert_profiles,
        judge_profile,
        synthesizer_profile,
        max_parallel=max_parallel,
        latency_quantile=latency_quantile,
        expert_phase_latency_ms=expert_phase,
        judge_latency_ms=judge_latency,
        synthesis_latency_ms=synthesis_latency,
        provider_serialization_adjustment_applied=provider_serialization_adjusted,
    )
    return total, known, receipt


def _fusion_latency_execution_receipt(
    expert_profiles: Sequence[ModelProfile],
    judge_profile: ModelProfile | None,
    synthesizer_profile: ModelProfile | None,
    *,
    max_parallel: int,
    expert_phase_latency_ms: float = 0.0,
    judge_latency_ms: float = 0.0,
    synthesis_latency_ms: float = 0.0,
    provider_serialization_adjustment_applied: bool = False,
    latency_quantile: str = "p50",
) -> dict[str, Any]:
    slots = max(1, int(max_parallel or 1))
    return {
        "schema": "axio_fusion_api.initial_execution_latency_estimate.v1",
        "basis": "assigned_runtime_roles_before_data_dependent_repair_or_escalation",
        "latency_quantile": str(latency_quantile or "p50")[:8],
        "expert_role_count": len(expert_profiles),
        "expert_profile_hashes": [sha256_text(profile.profile_id) for profile in expert_profiles],
        "expert_parallel_slots": slots,
        "expert_wave_count": int(math.ceil(len(expert_profiles) / slots)) if expert_profiles else 0,
        "expert_phase_latency_ms": round(float(expert_phase_latency_ms), 3),
        "provider_serialization_adjustment_applied": bool(
            provider_serialization_adjustment_applied
        ),
        "judge_included": judge_profile is not None,
        "judge_profile_sha256": sha256_text(judge_profile.profile_id) if judge_profile is not None else "",
        "judge_latency_ms": round(float(judge_latency_ms), 3),
        "synthesizer_included": synthesizer_profile is not None,
        "synthesizer_profile_sha256": sha256_text(synthesizer_profile.profile_id) if synthesizer_profile is not None else "",
        "synthesis_latency_ms": round(float(synthesis_latency_ms), 3),
        "optional_repair_or_escalation_included": False,
        "raw_profile_id_persisted": False,
        "raw_model_names_persisted": False,
    }


def _parallel_expert_phase_latency_ms(
    latencies: Sequence[float],
    *,
    max_parallel: int,
    profiles: Sequence[ModelProfile] | None = None,
) -> float:
    """Conservatively estimate every queued expert wave in the runtime pool."""

    if profiles is not None and len(profiles) == len(latencies):
        # A channel-scoped shared single-flight pool serializes calls even if
        # the executor has free worker slots.  Use a conservative upper bound
        # for provider-stage admission so the 3x guard cannot be cleared by a
        # purely local thread-count calculation.
        if _panel_contains_serialized_provider_pair(profiles):
            return sum(max(0.0, float(value)) for value in latencies)
    slots = max(1, int(max_parallel or 1))
    total = 0.0
    for start in range(0, len(latencies), slots):
        wave = latencies[start : start + slots]
        if wave:
            total += max(float(value) for value in wave)
    return total


def _role_assignments(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    selected: Sequence[ModelProfile],
    activated: bool,
    role_blueprint: Sequence[Mapping[str, Any]],
    *,
    budget: Mapping[str, Any] | None = None,
    latency_baseline_profile: ModelProfile | None = None,
    stage_profile_pool: Sequence[ModelProfile] | None = None,
    allow_critic_as_second_evidence: bool = False,
) -> list[dict[str, Any]]:
    if not selected:
        return []
    has_critic_target = any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "critic"
        for row in role_blueprint
    )
    has_distinct_independent_candidate = any(
        _screening_role_allowed(profile, "independent_solver")
        for profile in selected
    )
    needs_critic = activated and (
        (has_critic_target and len(selected) >= 3)
        or (
            allow_critic_as_second_evidence
            and len(selected) >= 2
            and not has_distinct_independent_candidate
        )
    )
    critic: ModelProfile | None = None
    critic_reused = False
    reserved: set[str] = set()
    if needs_critic:
        # Prefer a genuinely separate specialist when doing so still leaves
        # both Primary and Independent seats feasible.  The old greedy
        # reservation could consume the only independent-capable profile;
        # this bounded look-ahead keeps role diversity without making the
        # narrow-panel fallback pretend that a specialist is independent.
        critic_candidates = sorted(
            [
                profile
                for profile in selected
                if _screening_role_allowed(profile, "critic")
            ],
            key=lambda profile: _role_fit_score(
                profile,
                _role_blueprint_target(role_blueprint, "critic"),
                analysis,
                base_score=0.0,
                selected_providers=set(),
                prefer_new_provider=False,
            ),
            reverse=True,
        )
        for candidate in critic_candidates:
            primary_without_critic = _assigned_profile_for_role(
                "primary_solver",
                selected,
                analysis,
                role_blueprint,
                used_profile_ids={candidate.profile_id},
            )
            if primary_without_critic is None:
                continue
            independent_without_critic = _assigned_profile_for_role(
                "independent_solver",
                selected,
                analysis,
                role_blueprint,
                used_profile_ids={candidate.profile_id, primary_without_critic.profile_id},
            )
            if independent_without_critic is not None:
                critic = candidate
                reserved = {candidate.profile_id}
                break
    primary = _assigned_profile_for_role(
        "primary_solver",
        selected,
        analysis,
        role_blueprint,
        used_profile_ids=reserved,
    )
    if primary is None:
        return []
    used = {primary.profile_id, *reserved}
    roles = [
        _role_assignment(
            "primary_solver",
            "answer_candidate",
            primary,
            role_blueprint,
            analysis,
        )
    ]
    if activated and len(selected) >= 2:
        independent = _assigned_profile_for_role(
            "independent_solver",
            selected,
            analysis,
            role_blueprint,
            used_profile_ids=used,
        )
        if independent is not None:
            used.add(independent.profile_id)
            roles.append(
                _role_assignment(
                    "independent_solver",
                    "independent_candidate",
                    independent,
                    role_blueprint,
                    analysis,
                )
            )
    if needs_critic and critic is None:
        critic = _assigned_profile_for_role(
            "critic",
            selected,
            analysis,
            role_blueprint,
            used_profile_ids=used,
        )
        if critic is None and used:
            # Preserve the two genuinely independent evidence seats first.
            # A Critic is a verification instruction, not an additional
            # independent vote, so it may reuse the independent profile when
            # the selected panel has no third critic-capable model.
            critic = _assigned_profile_for_role(
                "critic",
                selected,
                analysis,
                role_blueprint,
                used_profile_ids={primary.profile_id},
            )
            if critic is None:
                critic = _assigned_profile_for_role(
                    "critic",
                    selected,
                    analysis,
                    role_blueprint,
                    used_profile_ids=set(),
                )
            critic_reused = critic is not None and critic.profile_id in used
        if critic is not None:
            if critic.profile_id not in used:
                used.add(critic.profile_id)
    if critic is not None:
        critic_role = _role_assignment(
            "critic",
            "find_errors_omissions_counterexamples",
            critic,
            role_blueprint,
            analysis,
        )
        if critic_reused:
            critic_role["role_profile_reuse"] = {
                "schema": "axio_fusion_api.role_profile_reuse.v1",
                "reused": True,
                "reason": "no_unused_critic_capable_profile_after_independent_seats",
                "profile_sha256": sha256_text(critic.profile_id),
                "counts_as_independent_evidence": False,
                "raw_profile_id_persisted": False,
                "raw_model_names_persisted": False,
            }
        roles.append(critic_role)
    has_domain_specialist_target = any(
        isinstance(row, Mapping) and str(row.get("role") or "") == "domain_specialist"
        for row in role_blueprint
    )
    screened_domain_capacity = any(
        _screening_role_contract_present(profile)
        and _screening_role_allowed(profile, "domain_specialist")
        for profile in selected
    )
    has_independent_evidence_role = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") in {"independent_solver", "critic"}
        for row in roles
    )
    small_screened_domain_panel = (
        len(selected) >= 2
        and screened_domain_capacity
        and not has_independent_evidence_role
    )
    if activated and has_domain_specialist_target and (
        len(selected) >= 4 or small_screened_domain_panel
    ):
        domain_specialist = _assigned_profile_for_role(
            "domain_specialist",
            selected,
            analysis,
            role_blueprint,
            used_profile_ids=used,
        )
        if domain_specialist is not None:
            used.add(domain_specialist.profile_id)
            roles.append(
                _role_assignment(
                    "domain_specialist",
                    "cover_strongest_domain_specific_subtask",
                    domain_specialist,
                    role_blueprint,
                    analysis,
                )
            )
    # A reused Critic is a second instruction on the primary model, not a
    # second evidence branch. Keep the narrow verifier available until a
    # genuinely distinct canonical model has been assigned to a full-evidence
    # role.
    has_full_second_evidence_role = _has_distinct_full_evidence_role(roles)
    has_short_verification_target = any(
        isinstance(row, Mapping)
        and str(row.get("role") or "") == "short_verification"
        for row in role_blueprint
    )
    screened_short_capacity = any(
        _screening_role_contract_present(profile)
        and _screening_role_allowed(profile, "short_verification")
        for profile in selected
    )
    if (
        activated
        and len(selected) >= 2
        and has_short_verification_target
        and screened_short_capacity
        and not has_full_second_evidence_role
    ):
        short_verifier = _assigned_profile_for_role(
            "short_verification",
            selected,
            analysis,
            role_blueprint,
            used_profile_ids=used,
        )
        if short_verifier is not None:
            used.add(short_verifier.profile_id)
            roles.append(
                _role_assignment(
                    "short_verification",
                    "verify_one_critical_claim_constraint_or_risk",
                    short_verifier,
                    role_blueprint,
                    analysis,
                )
            )
    if activated:
        # Expert branches are deliberately assigned first. Judge and
        # Synthesizer may then draw from the pre-Fusion stage pool, including
        # profiles outside the evidence panel, only when their role contract
        # and resource gates pass. Stage profiles never become evidence seats.
        stage_budget = budget if isinstance(budget, Mapping) else {}
        roles, expert_latency_optimization = _latency_optimize_expert_roles(
            roles=roles,
            selected=selected,
            direct_baseline_profile=latency_baseline_profile,
            analysis=analysis,
            budget=stage_budget,
        )
        selected_by_id = {profile.profile_id: profile for profile in selected}
        primary = next(
            (
                selected_by_id.get(
                    str((row.get("model") if isinstance(row.get("model"), Mapping) else {}).get("profile_id") or "")
                )
                for row in roles
                if isinstance(row, Mapping) and str(row.get("role") or "") == "primary_solver"
            ),
            primary,
        )
        used = {
            str(
                (row.get("model") if isinstance(row.get("model"), Mapping) else {}).get("profile_id") or ""
            )
            for row in roles
            if isinstance(row, Mapping)
            and str(row.get("role") or "") in {*_FULL_EVIDENCE_ROLE_NAMES, "short_verification"}
        }
        unassigned_stage_profiles = [
            profile
            for profile in selected
            if profile.profile_id not in used
        ]
        effective_stage_profile_pool = _merge_stage_profile_pool(selected, stage_profile_pool)
        selected_profile_ids = {item.profile_id for item in selected}
        stage_only_profiles = [
            profile
            for profile in effective_stage_profile_pool
            if profile.profile_id not in selected_profile_ids
        ]
        eligible_judge_profiles = [
            profile
            for profile in unassigned_stage_profiles
            if _stage_profile_eligibility(profile, "judge", analysis, stage_budget)[0]
        ]
        eligible_stage_judge_profiles = [
            profile
            for profile in stage_only_profiles
            if _stage_profile_eligibility(profile, "judge", analysis, stage_budget)[0]
        ]
        eligible_judge_all_profiles = [
            profile
            for profile in selected
            if _stage_profile_eligibility(profile, "judge", analysis, stage_budget)[0]
        ]
        role_capable_judge_profiles = [
            profile
            for profile in effective_stage_profile_pool
            if _screening_role_allowed(profile, "judge")
            and profile_latency_eligibility(profile).get("eligible") is not False
            and min(profile.capability("critique"), profile.capability("structured_output")) >= 0.50
        ]
        eligible_judge_operational_unassigned_profiles = [
            profile
            for profile in eligible_judge_profiles
            if _stage_profile_has_operational_evidence(
                profile,
                "judge",
                analysis,
                stage_budget,
            )
        ]
        eligible_judge_operational_stage_profiles = [
            profile
            for profile in eligible_stage_judge_profiles
            if _stage_profile_has_operational_evidence(
                profile,
                "judge",
                analysis,
                stage_budget,
            )
        ]
        eligible_judge_operational_reuse_profiles = [
            profile
            for profile in eligible_judge_all_profiles
            if _stage_profile_has_operational_evidence(
                profile,
                "judge",
                analysis,
                stage_budget,
            )
        ]
        # Keep a role-capable stage visible to the resource admission receipt
        # even when its known p50/cost exceeds the caller's hard budget.  The
        # admission layer then records the concrete blocker and prevents
        # activation; this is different from bypassing an explicit role deny.
        judge = _best_judge(
            eligible_judge_operational_unassigned_profiles
            or eligible_judge_operational_stage_profiles
            or eligible_judge_operational_reuse_profiles
            or eligible_judge_profiles
            or eligible_stage_judge_profiles
            or eligible_judge_all_profiles
            or role_capable_judge_profiles
        )
        remaining_unassigned_profiles = [
            profile
            for profile in unassigned_stage_profiles
            if judge is None or profile.profile_id != judge.profile_id
        ]
        eligible_synthesizer_profiles = [
            profile
            for profile in remaining_unassigned_profiles
            if _stage_profile_eligibility(profile, "synthesizer", analysis, stage_budget)[0]
        ]
        eligible_stage_synthesizer_profiles = [
            profile
            for profile in stage_only_profiles
            if _stage_profile_eligibility(profile, "synthesizer", analysis, stage_budget)[0]
        ]
        eligible_synthesizer_all_profiles = [
            profile
            for profile in selected
            if _stage_profile_eligibility(profile, "synthesizer", analysis, stage_budget)[0]
        ]
        role_capable_synthesizer_profiles = [
            profile
            for profile in effective_stage_profile_pool
            if _screening_role_allowed(profile, "synthesizer")
            and profile_latency_eligibility(profile).get("eligible") is not False
            and profile.capability("structured_output") >= 0.50
            and _domain_average(profile, _analysis_capability_axes(analysis)) >= 0.35
        ]
        eligible_synthesizer_operational_unassigned_profiles = [
            profile
            for profile in eligible_synthesizer_profiles
            if _stage_profile_has_operational_evidence(
                profile,
                "synthesizer",
                analysis,
                stage_budget,
            )
        ]
        eligible_synthesizer_operational_stage_profiles = [
            profile
            for profile in eligible_stage_synthesizer_profiles
            if _stage_profile_has_operational_evidence(
                profile,
                "synthesizer",
                analysis,
                stage_budget,
            )
        ]
        eligible_synthesizer_operational_reuse_profiles = [
            profile
            for profile in eligible_synthesizer_all_profiles
            if _stage_profile_has_operational_evidence(
                profile,
                "synthesizer",
                analysis,
                stage_budget,
            )
        ]
        synthesizer = _best_synthesizer(
            eligible_synthesizer_operational_unassigned_profiles
            or eligible_synthesizer_operational_stage_profiles
            or eligible_synthesizer_operational_reuse_profiles
            or eligible_synthesizer_profiles
            or eligible_stage_synthesizer_profiles
            or eligible_synthesizer_all_profiles
            or role_capable_synthesizer_profiles,
            analysis,
        )
        if judge is not None and synthesizer is not None:
            judge, synthesizer, latency_optimization = _latency_optimize_stage_profiles(
                selected=selected,
                primary_profile=primary,
                direct_baseline_profile=latency_baseline_profile,
                expert_roles=roles,
                judge=judge,
                synthesizer=synthesizer,
                analysis=analysis,
                budget=stage_budget,
                stage_profile_pool=effective_stage_profile_pool,
            )
        else:
            latency_optimization = {
                "schema": "axio_fusion_api.stage_latency_optimization.v1",
                "enabled": False,
                "applied": False,
                "reason": "screening_role_gate_blocked_mandatory_stage",
                "direct_profile_latency_ms": (
                    round(float(latency_baseline_profile.p50_latency_ms), 3)
                    if latency_baseline_profile is not None
                    and latency_baseline_profile.p50_latency_ms is not None
                    else None
                ),
                "original_judge_profile_sha256": sha256_text(judge.profile_id)
                if judge is not None
                else "",
                "original_synthesizer_profile_sha256": sha256_text(synthesizer.profile_id)
                if synthesizer is not None
                else "",
                "selected_judge_profile_sha256": sha256_text(judge.profile_id)
                if judge is not None
                else "",
                "selected_synthesizer_profile_sha256": sha256_text(synthesizer.profile_id)
                if synthesizer is not None
                else "",
                "raw_profile_ids_persisted": False,
                "raw_model_names_persisted": False,
            }
        rejected_unassigned_profile_count = max(
            0,
            len(unassigned_stage_profiles)
            - len(eligible_judge_profiles)
            - len(eligible_synthesizer_profiles),
        )
        stage_reuse = {
            "schema": "axio_fusion_api.stage_profile_reuse.v1",
            "expert_profile_count": len(used),
            "unassigned_profile_count": len(unassigned_stage_profiles),
            "eligible_unassigned_judge_profile_count": len(eligible_judge_profiles),
            "eligible_unassigned_synthesizer_profile_count": len(eligible_synthesizer_profiles),
            "stage_profile_pool_count": len(effective_stage_profile_pool),
            "stage_only_profile_count": len(stage_only_profiles),
            "stage_only_profiles_count": len(stage_only_profiles),
            "eligible_stage_only_judge_profile_count": sum(
                profile.profile_id in {item.profile_id for item in stage_only_profiles}
                for profile in eligible_stage_judge_profiles
            ),
            "eligible_stage_only_synthesizer_profile_count": sum(
                profile.profile_id in {item.profile_id for item in stage_only_profiles}
                for profile in eligible_stage_synthesizer_profiles
            ),
            "rejected_unassigned_profile_count": rejected_unassigned_profile_count,
            "judge_reuses_expert_profile": judge is not None and judge.profile_id in used,
            "synthesizer_reuses_expert_profile": synthesizer is not None and synthesizer.profile_id in used,
            "judge_and_synthesizer_share_profile": (
                judge is not None
                and synthesizer is not None
                and judge.profile_id == synthesizer.profile_id
            ),
            "independent_stage_selection_enabled": True,
            "stage_only_profile_pool_enabled": bool(stage_profile_pool is not None),
            "stage_only_profiles_count_as_independent_evidence": False,
            "reuse_is_capacity_fallback": True,
            "selection_policy": "independence_first_after_role_and_resource_gate",
            "expert_latency_optimization": expert_latency_optimization,
            "latency_optimization": latency_optimization,
            "raw_profile_id_persisted": False,
            "raw_model_names_persisted": False,
        }
        if judge is not None:
            roles.append(
                {
                    **_role_assignment(
                        "judge",
                        "compare_candidates_rank_and_identify_gaps",
                        judge,
                        role_blueprint,
                        analysis,
                    ),
                    "stage_only_profile": judge.profile_id not in selected_profile_ids,
                    "stage_profile_reuse": stage_reuse,
                }
            )
        if synthesizer is not None:
            roles.append(
                {
                    **_role_assignment(
                        "synthesizer",
                        "write_final_answer_from_judge_record",
                        synthesizer,
                        role_blueprint,
                        analysis,
                    ),
                    "stage_only_profile": synthesizer.profile_id not in selected_profile_ids,
                    "stage_profile_reuse": stage_reuse,
                }
            )
    return roles


def _latency_optimize_expert_roles(
    *,
    roles: Sequence[Mapping[str, Any]],
    selected: Sequence[ModelProfile],
    direct_baseline_profile: ModelProfile | None,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reduce a slow expert outlier before mandatory stages are scheduled.

    The final contract remains 3x versus the direct route.  This pass uses a
    stricter 2.5x operating target as headroom for provider variance, but only
    replaces a role when the faster profile remains within a bounded quality
    tolerance and satisfies that role's capability floor.
    """

    expert_role_names = set(_FULL_EVIDENCE_ROLE_NAMES)
    selected_by_id = {profile.profile_id: profile for profile in selected}
    expert_rows = [
        row
        for row in roles
        if isinstance(row, Mapping) and str(row.get("role") or "") in expert_role_names
    ]
    direct_latency = direct_baseline_profile.p50_latency_ms if direct_baseline_profile is not None else None
    current_profiles = [
        selected_by_id.get(
            str((row.get("model") if isinstance(row.get("model"), Mapping) else {}).get("profile_id") or "")
        )
        for row in expert_rows
    ]
    known = (
        direct_latency is not None
        and bool(current_profiles)
        and all(profile is not None and profile.p50_latency_ms is not None for profile in current_profiles)
    )
    receipt: dict[str, Any] = {
        "schema": "axio_fusion_api.expert_latency_optimization.v1",
        "enabled": True,
        "applied": False,
        "reason": "unknown_latency_telemetry" if not known else "expert_plan_within_operational_latency_target",
        "direct_profile_latency_ms": round(float(direct_latency), 3) if direct_latency is not None else None,
        "original_expert_phase_latency_ms": None,
        "optimized_expert_phase_latency_ms": None,
        "original_estimated_latency_ms": None,
        "optimized_estimated_latency_ms": None,
        "original_latency_multiplier_vs_direct": None,
        "optimized_latency_multiplier_vs_direct": None,
        "operational_target_multiplier": FUSION_OPERATIONAL_LATENCY_TARGET,
        "replaced_role_count": 0,
        "replacements": [],
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
    }
    mutable_roles = [dict(row) for row in roles]
    if not known:
        return mutable_roles, receipt

    max_parallel = max(1, int(budget.get("max_parallel_experts") or 1))
    original_phase = _parallel_expert_phase_latency_ms(
        [float(profile.p50_latency_ms) for profile in current_profiles if profile is not None],
        max_parallel=max_parallel,
    )
    stage_candidates = [
        profile
        for profile in selected
        if profile.p50_latency_ms is not None
        and (
            _stage_profile_eligibility(profile, "judge", analysis, budget)[0]
            or _stage_profile_eligibility(profile, "synthesizer", analysis, budget)[0]
        )
    ]
    stage_floor = (
        min(float(profile.p50_latency_ms) for profile in stage_candidates) * 2
        if stage_candidates
        else 0.0
    )
    direct = max(1.0, float(direct_latency))
    original_total = original_phase + stage_floor
    original_multiplier = original_total / direct
    receipt["original_expert_phase_latency_ms"] = round(original_phase, 3)
    receipt["optimized_expert_phase_latency_ms"] = round(original_phase, 3)
    receipt["original_estimated_latency_ms"] = round(original_total, 3)
    receipt["optimized_estimated_latency_ms"] = round(original_total, 3)
    receipt["original_latency_multiplier_vs_direct"] = round(original_multiplier, 4)
    receipt["optimized_latency_multiplier_vs_direct"] = round(original_multiplier, 4)
    if original_multiplier <= FUSION_OPERATIONAL_LATENCY_TARGET:
        return mutable_roles, receipt

    replaced_roles: set[str] = set()
    while True:
        profile_by_role = {
            str(row.get("role") or ""): selected_by_id.get(
                str((row.get("model") if isinstance(row.get("model"), Mapping) else {}).get("profile_id") or "")
            )
            for row in mutable_roles
            if isinstance(row, Mapping) and str(row.get("role") or "") in expert_role_names
        }
        expert_profiles = [profile for profile in profile_by_role.values() if profile is not None]
        phase = _parallel_expert_phase_latency_ms(
            [float(profile.p50_latency_ms) for profile in expert_profiles if profile.p50_latency_ms is not None],
            max_parallel=max_parallel,
        )
        total = phase + stage_floor
        if total / direct <= FUSION_OPERATIONAL_LATENCY_TARGET:
            break
        slowest = sorted(
            (
                (role, profile)
                for role, profile in profile_by_role.items()
                if profile is not None and profile.p50_latency_ms is not None and role not in replaced_roles
            ),
            key=lambda item: (float(item[1].p50_latency_ms or 1500), item[0]),
            reverse=True,
        )
        if not slowest:
            break
        role, current = slowest[0]
        other_expert_profiles = [
            profile
            for role_name, profile in profile_by_role.items()
            if role_name != role and profile is not None
        ]
        other_expert_ids = {profile.profile_id for profile in other_expert_profiles}
        other_expert_canonical_ids = {
            profile.canonical_identity for profile in other_expert_profiles
        }
        current_quality = _expected_profile_quality(current, analysis)
        candidates = [
            profile
            for profile in selected
            if profile.p50_latency_ms is not None
            and float(profile.p50_latency_ms) < float(current.p50_latency_ms)
            and profile.profile_id not in other_expert_ids
            and profile.canonical_identity not in other_expert_canonical_ids
            and _expert_profile_eligibility(profile, role, analysis)
            and _expected_profile_quality(profile, analysis) >= current_quality - EXPERT_QUALITY_REPLACEMENT_TOLERANCE
            and len(
                {
                    candidate.provider
                    for role_name, candidate in profile_by_role.items()
                    if role_name != role
                }
                | {profile.provider}
            ) >= len({candidate.provider for candidate in expert_profiles})
        ]
        if not candidates:
            replaced_roles.add(role)
            continue
        replacement = sorted(
            candidates,
            key=lambda profile: (
                float(profile.p50_latency_ms or 1500),
                -_expected_profile_quality(profile, analysis),
                profile.profile_id,
            ),
        )[0]
        for index, row in enumerate(mutable_roles):
            if str(row.get("role") or "") != role:
                continue
            mutable_roles[index] = {
                **row,
                "model": replacement.safe_dict(),
            }
            break
        replaced_roles.add(role)
        receipt["replacements"].append(
            {
                "role": role,
                "from_profile_sha256": sha256_text(current.profile_id),
                "to_profile_sha256": sha256_text(replacement.profile_id),
                "latency_reduction_ms": round(float(current.p50_latency_ms) - float(replacement.p50_latency_ms), 3),
                "quality_delta": round(_expected_profile_quality(replacement, analysis) - current_quality, 4),
                "raw_profile_ids_persisted": False,
            }
        )

    optimized_profiles = [
        selected_by_id.get(
            str((row.get("model") if isinstance(row.get("model"), Mapping) else {}).get("profile_id") or "")
        )
        for row in mutable_roles
        if isinstance(row, Mapping) and str(row.get("role") or "") in expert_role_names
    ]
    optimized_profiles = [profile for profile in optimized_profiles if profile is not None]
    optimized_phase = _parallel_expert_phase_latency_ms(
        [float(profile.p50_latency_ms) for profile in optimized_profiles if profile.p50_latency_ms is not None],
        max_parallel=max_parallel,
    )
    optimized_total = optimized_phase + stage_floor
    optimized_multiplier = optimized_total / direct
    receipt["optimized_expert_phase_latency_ms"] = round(optimized_phase, 3)
    receipt["optimized_estimated_latency_ms"] = round(optimized_total, 3)
    receipt["optimized_latency_multiplier_vs_direct"] = round(optimized_multiplier, 4)
    receipt["replaced_role_count"] = len(receipt["replacements"])
    if receipt["replacements"]:
        receipt["applied"] = True
        receipt["reason"] = (
            "faster_qualified_expert_assignments_meet_operational_latency_target"
            if optimized_multiplier <= FUSION_OPERATIONAL_LATENCY_TARGET
            else "faster_expert_assignments_exhausted_before_operational_target"
        )
        for index, row in enumerate(mutable_roles):
            if str(row.get("role") or "") in expert_role_names:
                mutable_roles[index] = {
                    **row,
                    "expert_latency_optimization": {
                        "schema": receipt["schema"],
                        "applied": True,
                        "reason": receipt["reason"],
                        "raw_profile_ids_persisted": False,
                        "raw_model_names_persisted": False,
                    },
                }
    elif optimized_multiplier > FUSION_OPERATIONAL_LATENCY_TARGET:
        receipt["reason"] = "no_faster_qualified_expert_assignment"
    return mutable_roles, receipt


def _expert_profile_eligibility(
    profile: ModelProfile,
    role: str,
    analysis: Mapping[str, Any],
) -> bool:
    if not profile.enabled or profile.p50_latency_ms is None:
        return False
    if profile_latency_eligibility(profile).get("eligible") is False:
        return False
    if not _screening_role_allowed(profile, role):
        return False
    if role == "critic":
        return min(profile.capability("critique"), profile.capability("structured_output")) >= 0.60
    axes = _analysis_capability_axes(analysis)
    return (
        profile.capability("structured_output") >= 0.55
        and _domain_average(profile, axes) >= 0.55
    )


def _latency_optimize_stage_profiles(
    *,
    selected: Sequence[ModelProfile],
    primary_profile: ModelProfile,
    direct_baseline_profile: ModelProfile | None = None,
    expert_roles: Sequence[Mapping[str, Any]],
    judge: ModelProfile,
    synthesizer: ModelProfile,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    stage_profile_pool: Sequence[ModelProfile] | None = None,
) -> tuple[ModelProfile, ModelProfile, dict[str, Any]]:
    """Use faster qualified stage profiles for both p50 and p95 guard repairs."""

    direct_profile = direct_baseline_profile or primary_profile
    direct_latency = direct_profile.p50_latency_ms
    expert_profiles = _planned_expert_profiles(expert_roles, selected)
    expert_role_profiles = _assigned_role_profile_pairs(
        expert_roles,
        selected,
        role_names=set(_FUSION_EXPERT_ROLE_NAMES),
    )
    current_stage_latencies = [judge.p50_latency_ms, synthesizer.p50_latency_ms]
    known = (
        direct_latency is not None
        and all(profile.p50_latency_ms is not None for profile in expert_profiles)
        and all(value is not None for value in current_stage_latencies)
    )
    direct_p95_latency = _role_latency_ms(
        direct_profile,
        "primary_solver",
        "p95_latency_ms",
    )
    current_p95_expert_latencies = [
        _role_latency_ms(profile, role, "p95_latency_ms")
        for role, profile in expert_role_profiles
    ]
    current_p95_stage_latencies = [
        _role_latency_ms(judge, "judge", "p95_latency_ms"),
        _role_latency_ms(synthesizer, "synthesizer", "p95_latency_ms"),
    ]
    p95_known = bool(
        direct_p95_latency is not None
        and all(value is not None for value in current_p95_expert_latencies)
        and all(value is not None for value in current_p95_stage_latencies)
    )
    base_receipt = {
        "schema": "axio_fusion_api.stage_latency_optimization.v1",
        "enabled": True,
        "applied": False,
        "reason": "unknown_latency_telemetry" if not known else "current_plan_within_operational_latency_target",
        "direct_profile_latency_ms": round(float(direct_latency), 3) if direct_latency is not None else None,
        "direct_profile_p95_latency_ms": round(float(direct_p95_latency), 3) if direct_p95_latency is not None else None,
        "expert_phase_latency_ms": None,
        "p95_latency_known": p95_known,
        "original_p95_expert_phase_latency_ms": None,
        "original_p95_latency_ms": None,
        "optimized_p95_latency_ms": None,
        "original_p95_latency_multiplier_vs_direct": None,
        "optimized_p95_latency_multiplier_vs_direct": None,
        "p95_guard_triggered": False,
        "original_judge_profile_sha256": sha256_text(judge.profile_id),
        "original_synthesizer_profile_sha256": sha256_text(synthesizer.profile_id),
        "selected_judge_profile_sha256": sha256_text(judge.profile_id),
        "selected_synthesizer_profile_sha256": sha256_text(synthesizer.profile_id),
        "estimated_initial_latency_ms": None,
        "estimated_latency_multiplier_vs_direct": None,
        "target_latency_multiplier": FUSION_LATENCY_MULTIPLIER_GUARD,
        "operational_target_multiplier": FUSION_OPERATIONAL_LATENCY_TARGET,
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
    }
    if not known:
        return judge, synthesizer, base_receipt
    try:
        max_parallel = max(1, int(budget.get("max_parallel_experts") or 1))
    except (TypeError, ValueError):
        max_parallel = 1
    try:
        max_latency_ms = max(1, int(budget.get("max_latency_ms") or 1))
    except (TypeError, ValueError):
        max_latency_ms = 1
    expert_phase = _parallel_expert_phase_latency_ms(
        [float(profile.p50_latency_ms) for profile in expert_profiles],
        max_parallel=max_parallel,
        profiles=expert_profiles,
    )
    current_total = expert_phase + sum(float(value) for value in current_stage_latencies)
    direct = max(1.0, float(direct_latency))
    current_multiplier = current_total / direct
    current_p95_expert_phase = (
        _parallel_expert_phase_latency_ms(
            [float(value) for value in current_p95_expert_latencies],
            max_parallel=max_parallel,
            profiles=[profile for _, profile in expert_role_profiles],
        )
        if p95_known
        else None
    )
    current_p95_total = (
        float(current_p95_expert_phase) + sum(float(value) for value in current_p95_stage_latencies)
        if p95_known and current_p95_expert_phase is not None
        else None
    )
    current_p95_multiplier = (
        current_p95_total / max(1.0, float(direct_p95_latency))
        if current_p95_total is not None and direct_p95_latency is not None
        else None
    )
    p50_guard_triggered = current_multiplier > FUSION_OPERATIONAL_LATENCY_TARGET
    p95_guard_triggered = bool(
        p95_known
        and current_p95_total is not None
        and (
            current_p95_total > max_latency_ms
            or (
                current_p95_multiplier is not None
                and current_p95_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
            )
        )
    )
    base_receipt.update(
        {
            "expert_phase_latency_ms": round(expert_phase, 3),
            "estimated_initial_latency_ms": round(current_total, 3),
            "estimated_latency_multiplier_vs_direct": round(current_multiplier, 4),
            "original_p95_expert_phase_latency_ms": round(float(current_p95_expert_phase), 3)
            if current_p95_expert_phase is not None
            else None,
            "original_p95_latency_ms": round(float(current_p95_total), 3)
            if current_p95_total is not None
            else None,
            "optimized_p95_latency_ms": round(float(current_p95_total), 3)
            if current_p95_total is not None
            else None,
            "original_p95_latency_multiplier_vs_direct": round(float(current_p95_multiplier), 4)
            if current_p95_multiplier is not None
            else None,
            "optimized_p95_latency_multiplier_vs_direct": round(float(current_p95_multiplier), 4)
            if current_p95_multiplier is not None
            else None,
            "p95_guard_triggered": p95_guard_triggered,
        }
    )
    if not p50_guard_triggered and not p95_guard_triggered:
        return judge, synthesizer, base_receipt

    stage_candidates = _merge_stage_profile_pool(selected, stage_profile_pool)
    eligible_judges = [
        profile
        for profile in stage_candidates
        if profile.p50_latency_ms is not None
        and _stage_profile_eligibility(profile, "judge", analysis, budget)[0]
    ]
    eligible_synthesizers = [
        profile
        for profile in stage_candidates
        if profile.p50_latency_ms is not None
        and _stage_profile_eligibility(profile, "synthesizer", analysis, budget)[0]
    ]
    operational_judges = [
        profile
        for profile in eligible_judges
        if _stage_profile_has_operational_evidence(profile, "judge", analysis, budget)
    ]
    operational_synthesizers = [
        profile
        for profile in eligible_synthesizers
        if _stage_profile_has_operational_evidence(
            profile,
            "synthesizer",
            analysis,
            budget,
        )
    ]
    # A screening-only profile remains a valid last-resort stage candidate,
    # but a faster such prior must not replace a slower profile with measured
    # role capability merely to optimize the p50 estimate.
    eligible_judges = operational_judges or eligible_judges
    eligible_synthesizers = operational_synthesizers or eligible_synthesizers
    if not eligible_judges or not eligible_synthesizers:
        base_receipt["reason"] = "no_qualified_stage_profile_pair"
        return judge, synthesizer, base_receipt

    stage_pairs: list[tuple[ModelProfile, ModelProfile, float, float | None]] = []
    for candidate_judge in eligible_judges:
        for candidate_synthesizer in eligible_synthesizers:
            optimized_total = (
                expert_phase
                + float(candidate_judge.p50_latency_ms)
                + float(candidate_synthesizer.p50_latency_ms)
            )
            optimized_multiplier = optimized_total / direct
            if (
                optimized_total >= current_total
                or optimized_total > max_latency_ms
                or optimized_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
            ):
                continue
            optimized_p95_total: float | None = None
            if p95_known:
                candidate_p95_judge = _role_latency_ms(
                    candidate_judge,
                    "judge",
                    "p95_latency_ms",
                )
                candidate_p95_synthesizer = _role_latency_ms(
                    candidate_synthesizer,
                    "synthesizer",
                    "p95_latency_ms",
                )
                if (
                    candidate_p95_judge is None
                    or candidate_p95_synthesizer is None
                    or current_p95_expert_phase is None
                ):
                    continue
                optimized_p95_total = (
                    float(current_p95_expert_phase)
                    + float(candidate_p95_judge)
                    + float(candidate_p95_synthesizer)
                )
                optimized_p95_multiplier = optimized_p95_total / max(
                    1.0,
                    float(direct_p95_latency or 0.0),
                )
                if (
                    optimized_p95_total > max_latency_ms
                    or optimized_p95_multiplier > FUSION_LATENCY_MULTIPLIER_GUARD
                    or (
                        p95_guard_triggered
                        and current_p95_total is not None
                        and optimized_p95_total >= current_p95_total
                    )
                ):
                    continue
            stage_pairs.append(
                (
                    candidate_judge,
                    candidate_synthesizer,
                    optimized_total,
                    optimized_p95_total,
                )
            )
    if not stage_pairs:
        base_receipt["reason"] = "no_faster_stage_pair_meets_latency_guard"
        return judge, synthesizer, base_receipt
    faster_judge, faster_synthesizer, optimized_total, optimized_p95_total = min(
        stage_pairs,
        key=lambda row: (
            float(row[3]) if p95_guard_triggered and row[3] is not None else float(row[2]),
            float(row[2]),
            -row[0].capability("critique") - row[0].capability("structured_output"),
            -row[1].capability("structured_output") - row[1].capability("long_context"),
            row[0].profile_id,
            row[1].profile_id,
        ),
    )
    optimized_multiplier = optimized_total / direct
    optimized_p95_multiplier = (
        optimized_p95_total / max(1.0, float(direct_p95_latency))
        if optimized_p95_total is not None and direct_p95_latency is not None
        else None
    )
    base_receipt.update(
        {
            "applied": True,
            "reason": "faster_qualified_stage_pair_meets_latency_guard",
            "selected_judge_profile_sha256": sha256_text(faster_judge.profile_id),
            "selected_synthesizer_profile_sha256": sha256_text(faster_synthesizer.profile_id),
            "estimated_initial_latency_ms": round(optimized_total, 3),
            "estimated_latency_multiplier_vs_direct": round(optimized_multiplier, 4),
            "optimized_p95_latency_ms": round(float(optimized_p95_total), 3)
            if optimized_p95_total is not None
            else None,
            "optimized_p95_latency_multiplier_vs_direct": round(float(optimized_p95_multiplier), 4)
            if optimized_p95_multiplier is not None
            else None,
            "optimization_basis": "p95" if p95_guard_triggered else "p50",
        }
    )
    return faster_judge, faster_synthesizer, base_receipt


def _stage_profile_eligibility(
    profile: ModelProfile,
    role: str,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> tuple[bool, str]:
    """Gate an unassigned panel member before promoting it to a mandatory stage."""

    if not profile.enabled:
        return False, "profile_disabled"
    if profile_latency_eligibility(profile).get("eligible") is False:
        return False, "provider_response_latency_exceeded_90s"
    if not _screening_role_allowed(profile, role):
        return False, "screening_role_guard_blocked"
    try:
        max_latency_ms = max(1, int(budget.get("max_latency_ms") or 0))
    except (TypeError, ValueError):
        max_latency_ms = 0
    if profile.p50_latency_ms is not None and max_latency_ms and int(profile.p50_latency_ms) > max_latency_ms:
        return False, "p50_latency_exceeds_stage_budget"
    if role == "judge":
        critique_ready, critique_basis = _stage_axis_eligibility(
            profile,
            "critique",
            operational_floor=0.50,
            screening_floor=SCREENING_STAGE_CAPABILITY_FLOOR,
        )
        structured_ready, structured_basis = _stage_axis_eligibility(
            profile,
            "structured_output",
            operational_floor=0.50,
            screening_floor=SCREENING_STAGE_CAPABILITY_FLOOR,
        )
        if not critique_ready or not structured_ready:
            return False, "judge_capability_floor_not_met"
        output_kind = "judge"
        capability_basis = (
            "screening_prior_fallback"
            if "screening_prior_fallback" in {critique_basis, structured_basis}
            else "operational_capability"
        )
    else:
        structured_ready, structured_basis = _stage_axis_eligibility(
            profile,
            "structured_output",
            operational_floor=0.50,
            screening_floor=SCREENING_STAGE_CAPABILITY_FLOOR,
        )
        if not structured_ready:
            return False, "synthesizer_structured_output_floor_not_met"
        domain_ready, domain_basis = _stage_domain_eligibility(
            profile,
            _analysis_capability_axes(analysis),
            operational_floor=0.35,
            screening_floor=SCREENING_SYNTHESIZER_DOMAIN_FLOOR,
        )
        if not domain_ready:
            return False, "synthesizer_domain_capability_floor_not_met"
        output_kind = "synthesizer"
        capability_basis = (
            "screening_prior_fallback"
            if "screening_prior_fallback" in {structured_basis, domain_basis}
            else "operational_capability"
        )
    try:
        max_cost_usd = max(0.0, float(budget.get("max_cost_usd") or 0.0))
    except (TypeError, ValueError):
        max_cost_usd = 0.0
    if (
        max_cost_usd > 0.0
        and profile.input_cost_per_million is not None
        and profile.output_cost_per_million is not None
    ):
        estimated_cost = _profile_call_cost_usd(
            profile,
            input_tokens=_estimated_input_tokens_for_route(analysis),
            output_tokens=_estimated_role_output_tokens(
                max_output_tokens=None,
                kind=output_kind,
            ),
        )
        if estimated_cost > max_cost_usd:
            return False, "stage_call_cost_exceeds_request_budget"
    return True, capability_basis


def _stage_profile_has_operational_evidence(
    profile: ModelProfile,
    role: str,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> bool:
    """Return whether a stage admit is backed by runtime capability evidence."""

    eligible, basis = _stage_profile_eligibility(profile, role, analysis, budget)
    return bool(eligible and basis == "operational_capability")


def _stage_axis_eligibility(
    profile: ModelProfile,
    axis: str,
    *,
    operational_floor: float,
    screening_floor: float,
) -> tuple[bool, str]:
    """Check a stage axis without turning a research prior into calibration."""

    value = profile.capability(axis)
    if value >= float(operational_floor):
        return True, "operational_capability"
    # A screened profile's neutral runtime value means unknown, not weak.  A
    # role-specific research prior may therefore admit one bounded stage call,
    # provided it is explicit and materially above the stage floor.  Known low
    # operational values and profiles with no screening contract remain hard
    # failures (legacy neutral compatibility is handled separately).
    if _legacy_neutral_capability(profile, axis):
        return True, "legacy_neutral_capability"
    if (
        _screening_role_contract_present(profile)
        and abs(value - 0.35) <= 1e-6
        and profile.screening_capability(axis) >= float(screening_floor)
    ):
        return True, "screening_prior_fallback"
    return False, "capability_floor_not_met"


def _stage_domain_eligibility(
    profile: ModelProfile,
    axes: Sequence[str],
    *,
    operational_floor: float,
    screening_floor: float,
) -> tuple[bool, str]:
    """Check the synthesizer's domain coverage with an auditable basis."""

    valid_axes = [axis for axis in axes if axis in CAPABILITY_AXES]
    valid_axes = valid_axes or ["daily_work"]
    operational_average = _domain_average(profile, valid_axes)
    if operational_average >= float(operational_floor):
        return True, "operational_capability"
    if not _screening_role_contract_present(profile):
        if all(_legacy_neutral_capability(profile, axis) for axis in valid_axes):
            return True, "legacy_neutral_capability"
        return False, "domain_capability_floor_not_met"
    # Do not let a known low runtime axis be washed out by a screening prior.
    # The prior fallback is only for a wholly uncalibrated domain vector.
    if not all(abs(profile.capability(axis) - 0.35) <= 1e-6 for axis in valid_axes):
        return False, "domain_capability_floor_not_met"
    screening_average = sum(
        profile.screening_capability(axis) for axis in valid_axes
    ) / max(1, len(valid_axes))
    if screening_average >= float(screening_floor):
        return True, "screening_prior_fallback"
    return False, "domain_capability_floor_not_met"


def _best_judge(
    selected: Sequence[ModelProfile],
    *,
    excluded_profile_ids: Sequence[str] = (),
) -> ModelProfile | None:
    """Choose a judge while preserving a separate profile when the panel allows it."""

    excluded = {str(profile_id) for profile_id in excluded_profile_ids if str(profile_id)}
    candidates = [profile for profile in selected if profile.profile_id not in excluded]
    role_allowed = [
        profile for profile in candidates
        if _screening_role_allowed(profile, "judge")
    ]
    if not role_allowed:
        # Reuse is a capacity fallback only after the hard role gate has been
        # applied.  An explicit deny is never a candidate for Judge.
        role_allowed = [
            profile for profile in selected
            if _screening_role_allowed(profile, "judge")
        ]
    if not role_allowed:
        return None
    pool = role_allowed
    return sorted(
        pool,
        key=lambda p: (
            p.capability("critique") + p.capability("structured_output"),
            _reliability_score(p),
            _latency_score(p),
            p.profile_id,
        ),
        reverse=True,
    )[0]


def _best_synthesizer(
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
    *,
    excluded_profile_ids: Sequence[str] = (),
) -> ModelProfile | None:
    """Choose a synthesizer from the remaining panel profiles when possible."""

    domains = _analysis_capability_axes(analysis)
    excluded = {str(profile_id) for profile_id in excluded_profile_ids if str(profile_id)}
    candidates = [profile for profile in selected if profile.profile_id not in excluded]
    role_allowed = [
        profile for profile in candidates
        if _screening_role_allowed(profile, "synthesizer")
    ]
    if not role_allowed:
        role_allowed = [
            profile for profile in selected
            if _screening_role_allowed(profile, "synthesizer")
        ]
    if not role_allowed:
        return None
    pool = role_allowed
    return sorted(
        pool,
        key=lambda profile: (
            profile.capability("structured_output") * 0.36
            + profile.capability("critique") * 0.18
            + profile.capability("long_context") * 0.12
            + _domain_average(profile, domains) * 0.24
            + _reliability_score(profile) * 0.10,
            profile.profile_id,
        ),
        reverse=True,
    )[0]


def _orchestration_scaffold(
    *,
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    activated: bool,
    roles: Sequence[Mapping[str, Any]],
    role_blueprint: Sequence[Mapping[str, Any]],
    search_policy: Mapping[str, Any] | None = None,
    finalization_mode: str = "direct",
) -> dict[str, Any]:
    domains = _analysis_capability_axes(analysis)
    search = search_policy if isinstance(search_policy, Mapping) else {}
    mode = str(finalization_mode or "direct")
    local_consensus = mode == "local_consensus"
    return {
        "schema": "axio_fusion_api.orchestration_scaffold.v1",
        "execution_kernel": (
            "adaptive_parallel_panel_local_consensus"
            if local_consensus
            else "adaptive_panel_judge_synthesizer"
        ),
        "fusion_activated": bool(activated),
        "fusion_finalization_mode": mode,
        "provider_stage_calls_reserved": bool(
            activated and mode == "provider_judge_synthesis"
        ),
        "local_consensus_enabled": local_consensus,
        "query_adaptive_routing": True,
        "cost_guarded": True,
        "role_blueprint": _safe_role_targets_for_policy(role_blueprint),
        "deliberative_search_policy": _safe_search_policy_for_scaffold(search),
        "stage_order": _stage_order(
            activated,
            analysis,
            finalization_mode=mode,
        ),
        "context_assembly": {
            "schema": "axio_fusion_api.context_assembly_policy.v1",
            "raw_prompt_sent_to_selected_runtime_providers": True,
            "raw_prompt_persisted": False,
            "expert_context": [
                "system_instruction",
                "original_user_task",
                "safe_routing_context",
                "deliberative_search_contract",
                "role_intent",
                "role_scoped_dag_nodes",
                "safe_tool_contract_when_declared",
                "candidate_task_execution_receipt",
            ],
            "judge_context": [
                "original_user_task",
                "safe_routing_context",
                "deliberative_search_contract",
                "candidate_packets",
                "local_rubric_precheck",
                "role_scoped_dag_nodes",
                "candidate_task_execution_receipts",
            ],
            "synthesizer_context": [
                "original_user_task",
                "safe_routing_context",
                "deliberative_search_contract",
                "judge_record",
                "top_ranked_candidate_text",
                "hash_receipts_for_compressed_candidates",
            ],
            "local_consensus_context": [
                "original_user_task",
                "safe_routing_context",
                "candidate_packets",
                "local_rubric_precheck",
                "coverage_and_calibration_receipts",
                "risk_and_disagreement_receipts",
                "top_ranked_candidate_text",
            ],
            "targeted_escalation_context": [
                "original_user_task",
                "safe_routing_context",
                "deliberative_search_contract",
                "missing_coverage_hashes",
                "contradiction_hashes",
                "quality_gap_receipt",
                "focused_dag_node_ids",
            ],
            "raw_candidate_text_persisted": False,
            "secrets_persisted": False,
        },
        "adaptive_stop_policy": {
            "early_exit_when": [
                "judge_ready",
                "candidate_agreement_above_threshold",
                "explicit_evidence_present",
                "top_ranked_score_above_threshold",
            ],
            "escalate_when": [
                "judge_not_ready",
                "missing_coverage_present",
                "contradiction_present",
                "quality_target_gap_present",
                "risk_or_uncertainty_requires_verification",
                "factuality_source_grounding_missing",
                "vertical_domain_guardrail_missing",
            ],
            "max_depth": int(budget.get("max_depth") or 0),
            "max_total_model_calls": int(budget.get("max_total_model_calls") or 1),
            "initial_fusion_call_plan": _safe_initial_fusion_call_plan(
                budget.get("initial_fusion_call_plan")
                if isinstance(budget.get("initial_fusion_call_plan"), Mapping)
                else {}
            ),
            "recursive_fusion_blocked": request.policy.fusion_depth >= request.policy.max_fusion_depth,
            "provider_judge_required": bool(
                activated and mode == "provider_judge_synthesis"
            ),
            "provider_synthesizer_required": bool(
                activated and mode == "provider_judge_synthesis"
            ),
            "local_consensus_required": bool(activated and local_consensus),
        },
        "domain_scaffold": {
            "domains": domains,
            "factuality_signal": bool(analysis.get("factuality_signal")),
            "vertical_domain_signals": [
                str(item)
                for item in analysis.get("vertical_domain_signals", [])
                if str(item)
            ][:12] if isinstance(analysis.get("vertical_domain_signals"), list) else [],
            "decomposable": bool(analysis.get("decomposable")),
            "estimated_steps": int(analysis.get("estimated_steps") or 1),
            "requires_tool_plan_check": "agentic_tool_calling" in domains,
            "requires_fact_currency_check": bool(analysis.get("needs_current_information")),
            "requires_source_grounding": bool(
                analysis.get("factuality_signal") or analysis.get("needs_current_information")
            ),
            "requires_vertical_domain_guardrails": bool(analysis.get("vertical_domain_signals")),
            "requires_independent_verification": bool(
                activated
                and (
                    request.public_model == "axio-pro"
                    or float(analysis.get("risk") or 0.0) >= 0.45
                    or float(analysis.get("quality_target") or 0.0) >= 0.82
                )
            ),
        },
        "assigned_role_count": len(roles),
        "raw_prompt_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _deliberative_search_policy(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    selected: Sequence[ModelProfile],
    activated: bool,
    roles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    domains = _analysis_capability_axes(analysis)
    quality_target = float(budget.get("quality_target") or 0.0)
    max_depth = max(0, int(budget.get("max_depth") or 0))
    max_parallel = max(1, int(budget.get("max_parallel_experts") or 1))
    selected_count = len(selected)
    exploration_width = 1 if not activated else min(selected_count, max_parallel)
    verification_width = 0
    if activated:
        verification_width = 1
        if request.public_model == "axio-pro" or quality_target >= 0.90:
            verification_width = min(2, max(1, selected_count - exploration_width))
    role_branches = [_search_branch_for_role(role, domains) for role in roles if isinstance(role, Mapping)]
    role_branches = [row for row in role_branches if row]
    if not role_branches:
        role_branches = [_search_branch_for_role({"role": "primary_solver"}, domains)]
    return {
        "schema": "axio_fusion_api.deliberative_search_policy.v1",
        "enabled": bool(activated),
        "kernel": "bounded_deliberative_branch_and_verify",
        "inspired_by": [
            "multi_agent_debate",
            "tree_search_style_explore_select_refine",
            "provider_routing_fallback",
        ],
        "not_a_training_or_benchmark_tuning_loop": True,
        "exploration_width": max(1, exploration_width),
        "verification_width": max(0, verification_width),
        "max_refinement_rounds": max_depth,
        "candidate_similarity_gate": _search_similarity_gate(quality_target),
        "selection_objective": [
            "correctness",
            "evidence_quality",
            "constraint_coverage",
            "independent_error_modes",
            "low_unresolved_uncertainty",
            "latency_budget_fit",
        ],
        "branch_policies": role_branches[:12],
        "escalation_triggers": [
            "missing_coverage",
            "candidate_contradiction",
            "quality_target_gap",
            "collective_blind_spot",
            "tool_task_without_tool_receipt",
            "high_duplicate_rate",
            *_domain_escalation_triggers(analysis),
        ],
        "latency_multiplier_guard": {
            "enabled": True,
            "target_max_vs_single_model": FUSION_LATENCY_MULTIPLIER_GUARD,
            "policy": "prefer_parallel_experts_and_targeted_escalation_over_unbounded_serial_refinement",
        },
        "anti_cheating_contract": {
            "no_benchmark_labels_in_prompt": True,
            "no_training_on_eval_cases": True,
            "case_hash_binding_required_for_claims": True,
        },
        "raw_prompt_persisted": False,
        "raw_model_names_persisted": False,
        "raw_profile_ids_persisted": False,
        "secrets_persisted": False,
    }


def _domain_escalation_triggers(analysis: Mapping[str, Any]) -> list[str]:
    triggers: list[str] = []
    if bool(analysis.get("factuality_signal")):
        triggers.extend(
            [
                "factuality_source_grounding_missing",
                "hallucination_risk_unresolved",
                "evidence_consistency_gap",
            ]
        )
    if isinstance(analysis.get("vertical_domain_signals"), list) and analysis.get("vertical_domain_signals"):
        triggers.extend(
            [
                "vertical_domain_guardrail_missing",
                "vertical_domain_scope_uncertainty_unresolved",
            ]
        )
    return list(dict.fromkeys(triggers))


def _search_branch_for_role(role: Mapping[str, Any], domains: Sequence[str]) -> dict[str, Any]:
    role_name = str(role.get("role") or "")
    branch = {
        "primary_solver": {
            "branch_type": "exploit_best_known_solution_path",
            "instruction": "produce_complete_candidate_with_constraints_and_evidence",
        },
        "independent_solver": {
            "branch_type": "explore_independent_hypothesis",
            "instruction": "avoid_copying_primary_path_and_surface_alternate_assumptions",
        },
        "critic": {
            "branch_type": "adversarial_verification",
            "instruction": "search_for_counterexamples_omissions_and_safety_or_logic_failures",
        },
        "domain_specialist": {
            "branch_type": "domain_decomposition_probe",
            "instruction": "focus_on_highest_risk_domain_subtask_and_evidence_gaps",
        },
        "judge": {
            "branch_type": "select_and_bound",
            "instruction": "rank_by_rubric_not_majority_vote_and_emit_targeted_followups",
        },
        "synthesizer": {
            "branch_type": "compose_verified_answer",
            "instruction": "integrate_verified_consensus_and_label_unresolved_disputes",
        },
    }.get(role_name)
    if not branch:
        return {}
    return {
        "role": role_name,
        "branch_type": branch["branch_type"],
        "instruction": branch["instruction"],
        "domain_axes": list(domains[:8]),
        "raw_prompt_persisted": False,
        "raw_model_names_persisted": False,
    }


def _search_similarity_gate(quality_target: float) -> dict[str, Any]:
    if quality_target >= 0.90:
        low, high = 0.42, 0.94
    elif quality_target >= 0.82:
        low, high = 0.36, 0.92
    else:
        low, high = 0.30, 0.90
    return {
        "min_useful_divergence": low,
        "max_duplicate_similarity": high,
        "policy": "keep_diverse_reasoning_paths_but_trigger_verification_when_answers_conflict",
    }


def _safe_search_policy_for_scaffold(search_policy: Mapping[str, Any]) -> dict[str, Any]:
    branches = search_policy.get("branch_policies") if isinstance(search_policy.get("branch_policies"), list) else []
    return {
        "schema": str(search_policy.get("schema") or "axio_fusion_api.deliberative_search_policy.v1"),
        "enabled": bool(search_policy.get("enabled")),
        "kernel": str(search_policy.get("kernel") or "")[:120],
        "exploration_width": int(search_policy.get("exploration_width") or 0),
        "verification_width": int(search_policy.get("verification_width") or 0),
        "max_refinement_rounds": int(search_policy.get("max_refinement_rounds") or 0),
        "branch_count": len(branches),
        "branch_policies": [
            {
                "role": str(row.get("role") or "")[:80],
                "branch_type": str(row.get("branch_type") or "")[:120],
                "instruction": str(row.get("instruction") or "")[:160],
                "raw_model_names_persisted": False,
            }
            for row in branches[:12]
            if isinstance(row, Mapping)
        ],
        "latency_multiplier_guard": search_policy.get("latency_multiplier_guard") if isinstance(search_policy.get("latency_multiplier_guard"), Mapping) else {},
        "raw_prompt_persisted": False,
        "raw_model_names_persisted": False,
    }


def _stage_order(
    activated: bool,
    analysis: Mapping[str, Any],
    *,
    finalization_mode: str = "direct",
) -> list[str]:
    stages = ["request_analysis", "privacy_filter", "budget_lock", "primary_candidate"]
    if activated:
        if bool(analysis.get("decomposable")):
            stages.append("task_decomposition")
        stages.extend(["parallel_expert_candidates", "candidate_standardization"])
        if str(finalization_mode or "direct") == "local_consensus":
            stages.append("local_consensus_finalize")
        else:
            stages.extend(
                [
                    "structured_judge",
                    "targeted_escalation_gate",
                    "rank_first_candidate_compression",
                    "final_synthesis",
                ]
            )
    else:
        stages.append("direct_finalize")
    return stages


def _targeted_escalation_pool(
    analysis: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    selected: Sequence[ModelProfile],
) -> list[dict[str, Any]]:
    selected_ids = {profile.profile_id for profile in selected}
    ranked = sorted(
        (
            (
                profile,
                _targeted_escalation_score(profile, analysis, base_score=float(base_score)),
            )
            for profile, base_score in scored
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [
        {
            "model": profile.safe_dict(),
            "escalation_score": round(float(score), 4),
            "already_in_panel": profile.profile_id in selected_ids,
            "selection_goal": "resolve_contested_or_missing_subtask",
            "raw_prompt_persisted": False,
            "secrets_persisted": False,
        }
        for profile, score in ranked[:12]
    ]


def _targeted_escalation_score(
    profile: ModelProfile,
    analysis: Mapping[str, Any],
    *,
    base_score: float,
) -> float:
    domains = [
        str(domain)
        for domain in analysis.get("domains", []) or ["daily_work"]
        if str(domain) in CAPABILITY_AXES
    ] or ["daily_work"]
    domain_score = sum(profile.capability(axis) for axis in domains) / max(1, len(domains))
    verification_score = (profile.capability("critique") + profile.capability("structured_output")) / 2.0
    specialist_bonus = 0.0
    if "code" in domains:
        specialist_bonus += profile.capability("code") * 0.05
    if "math" in domains or "logic" in domains:
        specialist_bonus += max(profile.capability("math"), profile.capability("logic")) * 0.05
    if "agentic_tool_calling" in domains:
        specialist_bonus += profile.capability("agentic_tool_calling") * 0.05
    if bool(analysis.get("needs_current_information")):
        specialist_bonus += profile.capability("current_information") * 0.04
    reliability = _reliability_score(profile)
    return domain_score * 0.46 + verification_score * 0.24 + reliability * 0.16 + float(base_score) * 0.10 + specialist_bonus


def _strategy_id(
    public_model: str,
    activated: bool,
    *,
    finalization_mode: str = "direct",
) -> str:
    if activated and str(finalization_mode or "") == "local_consensus":
        return "pro_local_consensus" if public_model == "axio-pro" else "terra_local_consensus"
    if public_model == "axio-fast":
        return "fast_light_verify" if activated else "fast_direct_cascade"
    if public_model == "axio-pro":
        return "pro_panel_judge_escalation" if activated else "pro_direct_with_verifier_gap"
    return "terra_cost_guarded_fusion" if activated else "terra_direct"


def _task_dag(
    activated: bool,
    analysis: Mapping[str, Any],
    roles: Sequence[Mapping[str, Any]],
    *,
    finalization_mode: str = "direct",
) -> dict[str, Any]:
    nodes = [
        _dag_node("request_analysis", "control", [], ["routing"], False, 0.0, False),
        _dag_node("safety_privacy_gate", "control", ["request_analysis"], ["privacy", "safety"], False, 0.0, True),
        _dag_node("budget_lock", "control", ["safety_privacy_gate"], ["cost_control"], False, 0.0, True),
        _dag_node("primary_candidate", "model_call", ["budget_lock"], _primary_capabilities(analysis), False, 0.0, False, "primary_solver"),
    ]
    checkpoints = [
        {
            "id": "checkpoint_after_request_analysis",
            "after_node": "budget_lock",
            "records": ["request_features", "privacy_policy", "budget"],
            "raw_prompt_persisted": False,
        }
    ]
    subtask_nodes = _domain_subtask_nodes(analysis) if activated or bool(analysis.get("decomposable")) else []
    if activated:
        if subtask_nodes:
            nodes.append(_dag_node("task_decomposition", "planning", ["budget_lock"], ["planning"], False, 0.0, True, "primary_solver"))
            for node in subtask_nodes:
                nodes.append(node)
            candidate_dependencies = ["primary_candidate", *[str(node["id"]) for node in subtask_nodes if node.get("kind") in {"model_call", "tool_or_model_call"}]]
        else:
            candidate_dependencies = ["primary_candidate"]
        nodes.append(_dag_node("parallel_expert_candidates", "parallel_model_calls", ["budget_lock"], _primary_capabilities(analysis), True, 0.0, False, "independent_solver"))
        nodes.append(_dag_node("candidate_standardization", "normalization", candidate_dependencies + ["parallel_expert_candidates"], ["structured_output"], False, 0.0, True))
        if str(finalization_mode or "direct") == "local_consensus":
            nodes.append(
                _dag_node(
                    "local_consensus_finalize",
                    "local_consensus",
                    ["candidate_standardization"],
                    ["critique", "structured_output"],
                    False,
                    0.0,
                    True,
                )
            )
        else:
            nodes.append(_dag_node("structured_judge", "judge", ["candidate_standardization"], ["critique", "structured_output"], False, 0.0, True, "judge"))
            nodes.append(_dag_node("targeted_escalation_gate", "control", ["structured_judge"], ["critique"], False, 0.0, True))
            nodes.append(_dag_node("final_synthesis", "synthesis", ["structured_judge", "targeted_escalation_gate"], ["structured_output"], False, 0.0, True, "synthesizer"))
        checkpoints.extend(
            [
                {
                    "id": "checkpoint_after_candidate_standardization",
                    "after_node": "candidate_standardization",
                    "records": ["candidate_receipts", "dedupe_hashes", "coverage_counts"],
                    "raw_candidate_text_persisted": False,
                },
                {
                    "id": (
                        "checkpoint_after_local_consensus"
                        if str(finalization_mode or "direct") == "local_consensus"
                        else "checkpoint_after_structured_judge"
                    ),
                    "after_node": (
                        "local_consensus_finalize"
                        if str(finalization_mode or "direct") == "local_consensus"
                        else "structured_judge"
                    ),
                    "records": (
                        ["local_scores", "coverage", "calibration", "disagreements"]
                        if str(finalization_mode or "direct") == "local_consensus"
                        else ["judge_scores", "missing_coverage", "contradictions", "follow_up_tasks"]
                    ),
                    "raw_candidate_text_persisted": False,
                },
            ]
        )
    else:
        nodes.append(_dag_node("finalize_direct", "control", ["primary_candidate"], ["structured_output"], False, 0.0, False))
    checkpoints.append(
        {
            "id": "checkpoint_final",
            "after_node": (
                "local_consensus_finalize"
                if activated and str(finalization_mode or "direct") == "local_consensus"
                else "final_synthesis"
                if activated
                else "finalize_direct"
            ),
            "records": ["final_answer_hash", "cost", "latency_ms", "provider_call_count"],
            "raw_final_answer_persisted": False,
        }
    )
    edges = [(dependency, str(node["id"])) for node in nodes for dependency in node.get("depends_on", [])]
    return {
        "schema": "axio_fusion_api.task_dag.v1",
        "fusion_finalization_mode": str(finalization_mode or "direct"),
        "provider_stage_calls_reserved": bool(
            activated and str(finalization_mode or "direct") == "provider_judge_synthesis"
        ),
        "decomposable": bool(analysis.get("decomposable")),
        "nodes": nodes,
        "edges": [{"from": left, "to": right} for left, right in edges],
        "checkpoints": checkpoints,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "checkpoint_count": len(checkpoints),
        "role_count": len(roles),
        "subtask_count": len(subtask_nodes),
        "max_dependency_depth": _max_dependency_depth(nodes),
        "raw_prompt_persisted": False,
    }


def _judge_contract(
    activated: bool,
    *,
    finalization_mode: str = "direct",
) -> dict[str, Any]:
    mode = str(finalization_mode or "direct")
    local_consensus = mode == "local_consensus"
    return {
        "required": activated,
        "finalization_mode": mode,
        "provider_judge_required": bool(activated and not local_consensus),
        "provider_synthesizer_required": bool(activated and not local_consensus),
        "local_consensus_required": bool(activated and local_consensus),
        "provider_stage_calls_reserved": bool(activated and not local_consensus),
        "not_majority_vote": True,
        "rubric": [
            "answers_original_request",
            "constraint_satisfaction",
            "reasoning_consistency",
            "evidence_quality",
            "coverage",
            "contradictions",
            "actionability",
            "safety",
        ],
        "structured_output_schema": {
            "consensus": [],
            "contradictions": [],
            "unique_insights": [],
            "missing_coverage": [],
            "ranked_candidates": [],
            "follow_up_tasks": [],
            "ready_for_synthesis": False,
        },
        "evidence_without_source_is_unverified": True,
    }


def _cost_efficiency(profile: ModelProfile) -> float:
    if profile.input_cost_per_million is None or profile.output_cost_per_million is None:
        return 0.55
    blended = profile.input_cost_per_million * 0.65 + profile.output_cost_per_million * 0.35
    return 1.0 / (1.0 + math.sqrt(max(0.0, blended)))


def _latency_score(profile: ModelProfile) -> float:
    if not profile.p50_latency_ms:
        return 0.55
    return 1.0 / (1.0 + max(0, profile.p50_latency_ms - 300) / 3000.0)


def _reliability_score(profile: ModelProfile) -> float:
    values = []
    if profile.recent_success_rate is not None:
        values.append(max(0.0, min(1.0, float(profile.recent_success_rate))))
    if profile.availability is not None:
        values.append(max(0.0, min(1.0, float(profile.availability))))
    if not values:
        if profile.health == "available":
            return 0.82
        if profile.health in {"failed", "unavailable"}:
            return 0.20
        return 0.55
    return sum(values) / len(values)


def _task_type_from_domains(domains: Sequence[str]) -> str:
    if "code" in domains:
        return "code_generation_or_review"
    if "science_knowledge" in domains:
        return "science_research"
    if "agentic_tool_calling" in domains:
        return "agentic_tool_calling"
    if "math" in domains:
        return "math_reasoning"
    if "logic" in domains:
        return "logic_reasoning"
    return "general_work"


def _privacy_level(request: FusionRequest) -> str:
    raw = str(
        request.metadata.get("privacy_level")
        or request.metadata.get("data_classification")
        or request.metadata.get("data_sensitivity")
        or "public"
    ).strip().lower()
    aliases = {
        "caller_controlled": "public",
        "external": "public",
        "open": "public",
        "internal_data": "internal",
        "private": "internal",
        "restricted": "confidential",
        "secret": "confidential",
        "classified": "confidential",
        "机密": "confidential",
        "内部": "internal",
        "公开": "public",
    }
    return aliases.get(raw, raw if raw in {"public", "internal", "confidential"} else "public")


def _expected_output_tokens(complexity: float) -> int:
    if complexity >= 0.72:
        return 1600
    if complexity >= 0.42:
        return 900
    return 350


def _quality_target(request: FusionRequest) -> float:
    value = request.policy.quality_target
    if value is None:
        return 0.0
    try:
        target = float(value)
    except (TypeError, ValueError):
        return 0.0
    if target > 1.0:
        target = target / 100.0 if target > 5.0 else target / 5.0
    return round(max(0.0, min(1.0, target)), 4)


def _quality_pressure(quality_target: float) -> float:
    if quality_target <= 0.72:
        return 0.0
    return max(0.0, min(1.0, (quality_target - 0.72) / 0.23))


def _apply_privacy_filter(
    request: FusionRequest,
    profiles: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
) -> tuple[list[ModelProfile], dict[str, Any]]:
    level = str(analysis.get("privacy_level") or "public")
    allowed_tags = _allowed_privacy_tags(level)
    eligible = []
    blocked_counts: dict[str, int] = {}
    for profile in profiles:
        # Registry enablement is an admission control, not merely a hint for
        # optional expert replacements.  In particular, newly configured
        # providers stay disabled until the explicit onboarding activation
        # creates a new private registry, so they must never become a direct
        # fallback or an Axio Terra/Pro panel member here.
        if profile.enabled is not True:
            blocked_counts["profile_disabled"] = (
                blocked_counts.get("profile_disabled", 0) + 1
            )
            continue
        if profile_latency_eligibility(profile).get("eligible") is False:
            blocked_counts["provider_response_latency_exceeded_90s"] = (
                blocked_counts.get("provider_response_latency_exceeded_90s", 0) + 1
            )
            continue
        if request.has_non_text_input:
            if request.has_visual_input and profile.supports_vision is not True:
                blocked_counts["vision_capability_required"] = (
                    blocked_counts.get("vision_capability_required", 0) + 1
                )
                continue
            if not content_parts_supported_by_format(
                _request_content_parts(request),
                target_format=profile.api_format,
            ):
                blocked_counts["content_not_representable_by_provider_protocol"] = (
                    blocked_counts.get("content_not_representable_by_provider_protocol", 0) + 1
                )
                continue
        if request.structured_output and profile.capability("structured_output") < 0.50:
            blocked_counts["structured_output_capability_floor"] = (
                blocked_counts.get("structured_output_capability_floor", 0) + 1
            )
            continue
        tags = {str(tag).strip().lower() for tag in profile.privacy_tags}
        if level == "public" or tags.intersection(allowed_tags):
            eligible.append(profile)
            continue
        reason = f"missing_allowed_privacy_tag_for_{level}"
        blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
    return eligible, {
        "schema": "axio_fusion_api.privacy_policy.v1",
        "requested_privacy_level": level,
        "allowed_privacy_tags": sorted(allowed_tags),
        "model_pool_input_count": len(profiles),
        "model_pool_eligible_count": len(eligible),
        "model_pool_blocked_count": max(0, len(profiles) - len(eligible)),
        "blocked_counts": blocked_counts,
        "model_pool_restricted": level != "public",
        "fallback_when_empty": "return_no_eligible_model_error",
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _request_content_parts(request: FusionRequest) -> list[Mapping[str, Any]]:
    parts: list[Mapping[str, Any]] = [
        dict(item)
        for item in request.content_parts
        if isinstance(item, Mapping)
    ]
    for event in request.history:
        if not isinstance(event, Mapping):
            continue
        event_parts = event.get("content_parts")
        if isinstance(event_parts, Sequence) and not isinstance(event_parts, (str, bytes)):
            parts.extend(
                dict(item)
                for item in event_parts
                if isinstance(item, Mapping)
            )
    return parts


def _allowed_privacy_tags(level: str) -> set[str]:
    if level == "confidential":
        return {"local", "on_prem", "private_deployment", "confidential_approved"}
    if level == "internal":
        return {
            "local",
            "on_prem",
            "private_deployment",
            "contracted_provider",
            "data_agreement",
            "internal_approved",
            "confidential_approved",
        }
    return {"external_provider", "contracted_provider", "data_agreement", "local", "private_deployment"}


def _tool_policy(request: FusionRequest, roles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tool_receipts = [_tool_receipt(index, tool) for index, tool in enumerate(request.tools)]
    role_permissions = []
    for role in roles:
        role_name = str(role.get("role") or "")
        allowed = [
            receipt["tool_hash"]
            for receipt in tool_receipts
            if _role_can_use_tool(role_name, str(receipt["category"]), bool(receipt["approval_required"]))
        ]
        role_permissions.append(
            {
                "role": role_name,
                "allowed_tool_hashes": allowed,
                "denied_tool_hashes": [
                    receipt["tool_hash"]
                    for receipt in tool_receipts
                    if receipt["tool_hash"] not in allowed
                ],
                "judge_read_only": role_name == "judge",
                "raw_tool_schema_persisted": False,
            }
        )
    return {
        "schema": "axio_fusion_api.tool_policy.v1",
        "tool_count": len(tool_receipts),
        "tool_receipts": tool_receipts,
        "role_permissions": role_permissions,
        "destructive_tools_require_external_approval": True,
        "default_deny": True,
        "raw_tool_schema_persisted": False,
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _tool_receipt(index: int, tool: Mapping[str, Any]) -> dict[str, Any]:
    tool_type = str(tool.get("type") or "").strip().lower()
    function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
    name = str(tool.get("name") or function.get("name") or tool_type or f"tool_{index}")
    category = _tool_category(name, tool_type)
    approval_required = category in {"destructive_execution", "write_action", "deployment_action"}
    fusion_directive = _fusion_plugin_directive(tool) if category == "fusion_plugin" else {}
    source = "plugin" if str(tool.get("_axio_source") or "").strip().lower() == "plugin" else "tool"
    return {
        "tool_index": index,
        "source": source,
        "tool_hash": sha256_text(f"{index}:{tool_type}:{name}"),
        "tool_type": "fusion_plugin" if category == "fusion_plugin" else (tool_type or "unknown"),
        "name_sha256": sha256_text(name),
        "category": category,
        "approval_required": approval_required,
        "fusion_plugin": fusion_directive if fusion_directive else None,
        "raw_tool_schema_persisted": False,
    }


def _tool_category(name: str, tool_type: str) -> str:
    text = f"{name} {tool_type}".lower()
    if (
        tool_type == "fusion"
        or tool_type in {"openrouter:fusion", "openrouter/fusion", "axio_fusion", "axio-fusion"}
        or name.strip().lower() in {"fusion", "openrouter:fusion", "axio_fusion", "axio-fusion"}
        or "openrouter:fusion" in text
        or "openrouter/fusion" in text
    ):
        return "fusion_plugin"
    if any(token in text for token in ("delete", "write", "patch", "deploy", "exec", "shell", "command", "mutation")):
        return "destructive_execution" if any(token in text for token in ("exec", "shell", "command")) else "write_action"
    if any(token in text for token in ("search", "web", "browser", "http", "fetch")):
        return "network_search"
    if any(token in text for token in ("repo", "code", "file", "read")):
        return "repo_read"
    if "function" in text or tool_type:
        return "function_call"
    return "unknown"


def _role_can_use_tool(role: str, category: str, approval_required: bool) -> bool:
    if category == "fusion_plugin":
        return False
    if approval_required:
        return False
    if role in {"judge", "synthesizer"}:
        return False
    if role == "critic":
        return category in {"repo_read", "function_call"}
    if role in {"primary_solver", "independent_solver", "fallback_solver", "targeted_escalation"}:
        return category in {"network_search", "repo_read", "function_call"}
    return False


def _fusion_plugin_requested(request: FusionRequest) -> bool:
    if bool(request.metadata.get("openrouter_fusion_model_alias")):
        return True
    for tool in request.tools:
        if not isinstance(tool, Mapping):
            continue
        if not _fusion_tool_enabled(tool):
            continue
        tool_type = str(tool.get("type") or "").strip().lower()
        function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
        name = str(tool.get("name") or function.get("name") or tool_type).strip().lower()
        if _tool_category(name, tool_type) == "fusion_plugin":
            return True
    return False


def _non_fusion_tools_declared(request: FusionRequest) -> bool:
    for tool in request.tools:
        if not isinstance(tool, Mapping):
            continue
        tool_type = str(tool.get("type") or "").strip().lower()
        function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
        name = str(tool.get("name") or function.get("name") or tool_type).strip().lower()
        if _tool_category(name, tool_type) == "fusion_plugin":
            continue
        return True
    return False


def _plugin_policy(
    request: FusionRequest,
    tool_policy: Mapping[str, Any],
    activated: bool,
) -> dict[str, Any]:
    tool_receipts = tool_policy.get("tool_receipts") if isinstance(tool_policy.get("tool_receipts"), list) else []
    plugin_receipts = []
    if bool(request.metadata.get("openrouter_fusion_model_alias")):
        plugin_receipts.append(
            {
                "source": "model_alias",
                "tool_index": None,
                "tool_hash": sha256_text("model_alias:openrouter_fusion"),
                "name_sha256": sha256_text("openrouter/fusion"),
                "category": "fusion_plugin",
                "activation_scope": "orchestrator_route_decision",
                "openrouter_compatible": True,
                "enabled": True,
                "raw_tool_schema_persisted": False,
            }
        )
    for receipt in tool_receipts:
        if not isinstance(receipt, Mapping) or receipt.get("category") != "fusion_plugin":
            continue
        directive = receipt.get("fusion_plugin") if isinstance(receipt.get("fusion_plugin"), Mapping) else {}
        if directive.get("enabled") is False:
            continue
        plugin_receipts.append(
            {
                "source": str(receipt.get("source") or "tool"),
                "tool_index": receipt.get("tool_index"),
                "tool_hash": receipt.get("tool_hash"),
                "name_sha256": receipt.get("name_sha256"),
                "category": receipt.get("category"),
                "activation_scope": "orchestrator_route_decision",
                "openrouter_compatible": bool(directive.get("openrouter_compatible")),
                "enabled": bool(directive.get("enabled", True)),
                "config_hash": directive.get("config_hash"),
                "analysis_model_count": directive.get("analysis_model_count"),
                "analysis_model_hashes": directive.get("analysis_model_hashes"),
                "synthesis_model_configured": bool(directive.get("synthesis_model_configured")),
                "synthesis_model_sha256": directive.get("synthesis_model_sha256"),
                "preset_id": directive.get("preset_id"),
                "raw_tool_schema_persisted": False,
            }
        )
    return {
        "schema": "axio_fusion_api.plugin_policy.v1",
        "fusion_plugin_requested": bool(plugin_receipts),
        "fusion_plugin_count": len(plugin_receipts),
        "activation_effect": "force_fusion_when_policy_and_model_pool_allow" if plugin_receipts else "none",
        "fusion_activated": bool(activated),
        "public_model_after_canonicalization": request.public_model,
        "plugin_receipts": plugin_receipts,
        "plugin_executes_as_external_tool": False,
        "raw_tool_schema_persisted": False,
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _fusion_plugin_directive_summary(request: FusionRequest) -> dict[str, Any]:
    analysis_hashes: list[str] = []
    synthesis_model_configured = False
    requested = bool(request.metadata.get("openrouter_fusion_model_alias"))
    for tool in request.tools:
        if not isinstance(tool, Mapping):
            continue
        tool_type = str(tool.get("type") or "").strip().lower()
        function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
        name = str(tool.get("name") or function.get("name") or tool_type).strip().lower()
        if _tool_category(name, tool_type) != "fusion_plugin" or not _fusion_tool_enabled(tool):
            continue
        requested = True
        directive = _fusion_plugin_directive(tool)
        analysis_hashes.extend(str(item) for item in directive.get("analysis_model_hashes", []) if str(item))
        synthesis_model_configured = synthesis_model_configured or bool(directive.get("synthesis_model_configured"))
    return {
        "fusion_plugin_requested": requested,
        "analysis_model_count": len(analysis_hashes),
        "synthesis_model_configured": synthesis_model_configured,
        "analysis_model_hashes": analysis_hashes[:12],
    }


def _fusion_plugin_directive(tool: Mapping[str, Any]) -> dict[str, Any]:
    config = _fusion_plugin_config(tool)
    analysis_models = _string_list(config.get("analysis_models") or config.get("analysisModels"))
    synthesis_model = str(config.get("model") or config.get("synthesis_model") or config.get("synthesisModel") or "").strip()
    preset = str(config.get("preset") or "").strip().lower()
    preset_id = preset if preset in {"auto", "fast", "balanced", "quality", "high", "cost"} else ("custom" if preset else "")
    enabled = _fusion_tool_enabled(tool)
    directive_for_hash = {
        "analysis_model_hashes": [sha256_text(model) for model in analysis_models],
        "synthesis_model_sha256": sha256_text(synthesis_model) if synthesis_model else "",
        "preset_id": preset_id,
        "enabled": enabled,
    }
    tool_type = str(tool.get("type") or "").strip().lower()
    return {
        "schema": "axio_fusion_api.fusion_plugin_directive.v1",
        "enabled": enabled,
        "openrouter_compatible": tool_type in {"openrouter:fusion", "openrouter/fusion"} or _contains_openrouter_fusion(tool),
        "config_hash": sha256_text(stable_json(directive_for_hash)),
        "analysis_model_count": len(analysis_models),
        "analysis_model_hashes": directive_for_hash["analysis_model_hashes"][:12],
        "synthesis_model_configured": bool(synthesis_model),
        "synthesis_model_sha256": directive_for_hash["synthesis_model_sha256"],
        "preset_id": preset_id,
        "raw_model_names_persisted": False,
        "raw_tool_schema_persisted": False,
    }


def _fusion_plugin_config(tool: Mapping[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for key in ("parameters", "config", "fusion"):
        value = tool.get(key)
        if isinstance(value, Mapping):
            config.update(dict(value))
    for key in ("analysis_models", "analysisModels", "model", "synthesis_model", "synthesisModel", "preset", "enabled"):
        if key in tool:
            config[key] = tool[key]
    return config


def _fusion_tool_enabled(tool: Mapping[str, Any]) -> bool:
    config = _fusion_plugin_config(tool)
    value = config.get("enabled")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _contains_openrouter_fusion(tool: Mapping[str, Any]) -> bool:
    function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
    text = " ".join(
        [
            str(tool.get("type") or ""),
            str(tool.get("name") or ""),
            str(function.get("name") or ""),
        ]
    ).lower()
    return "openrouter:fusion" in text or "openrouter/fusion" in text


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _quality_diversity_archive(
    analysis: Mapping[str, Any],
    selected: Sequence[ModelProfile],
    roles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    role_by_profile: dict[str, list[str]] = {}
    for role in roles:
        if not isinstance(role, Mapping):
            continue
        model = role.get("model") if isinstance(role.get("model"), Mapping) else {}
        profile_id = str(model.get("profile_id") or "")
        role_name = str(role.get("role") or "")
        if profile_id and role_name:
            role_by_profile.setdefault(profile_id, []).append(role_name)
    entries = []
    for profile in selected:
        novelty = _profile_archive_novelty(profile, selected, analysis)
        roles_for_profile = role_by_profile.get(profile.profile_id, [])
        entries.append(
            {
                "profile_id_sha256": sha256_text(profile.profile_id),
                "provider_sha256": sha256_text(profile.provider),
                "runtime_canonical_identity_sha256": profile.canonical_identity_sha256,
                "api_format": profile.api_format,
                "dominant_capability_axis": _domain_leader_axis(profile, analysis),
                "assigned_roles": roles_for_profile[:6],
                "quality_estimate": round(_expected_profile_quality(profile, analysis), 4),
                "novelty_estimate": round(novelty, 4),
                "niche_id_sha256": sha256_text(
                    stable_json(
                        {
                            "axis": _domain_leader_axis(profile, analysis),
                            "api_format": profile.api_format,
                            "roles": sorted(roles_for_profile),
                        }
                    )
                ),
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_model_name_persisted": False,
            }
        )
    niche_ids = {row["niche_id_sha256"] for row in entries}
    role_tags = sorted({role for row in entries for role in row.get("assigned_roles", [])})
    return {
        "schema": "axio_fusion_api.quality_diversity_archive.v1",
        "enabled": len(selected) >= 2,
        "selection_kernel": "quality_diversity_niche_archive",
        "inspired_by": ["quality_diversity_search", "agent_skill_niches", "provider_capability_diversification"],
        "objective": [
            "preserve_high_quality_primary_candidate",
            "cover_distinct_capability_niches",
            "reduce_correlated_error_modes",
            "assign_critic_and_specialist_roles_to_nonidentical_strengths",
        ],
        "entry_count": len(entries),
        "canonical_model_count": len(
            {profile.canonical_identity for profile in selected}
        ),
        "canonical_duplicate_count": max(
            0,
            len(selected) - len({profile.canonical_identity for profile in selected}),
        ),
        "niche_count": len(niche_ids),
        "role_tag_count": len(role_tags),
        "role_tags": role_tags[:12],
        "average_novelty_estimate": round(sum(row["novelty_estimate"] for row in entries) / max(1, len(entries)), 4),
        "average_quality_estimate": round(sum(row["quality_estimate"] for row in entries) / max(1, len(entries)), 4),
        "entries": entries[:12],
        "prompt_contract": {
            "experts_should_not_copy_each_other": True,
            "critic_searches_failure_modes_not_majority_vote": True,
            "synthesizer_preserves_verified_minority_insights": True,
            "raw_candidate_text_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def _profile_archive_novelty(
    profile: ModelProfile,
    selected: Sequence[ModelProfile],
    analysis: Mapping[str, Any],
) -> float:
    others = [item for item in selected if item.profile_id != profile.profile_id]
    if not others:
        return 0.0
    correlations = [_pair_error_correlation(profile, other, analysis) for other in others]
    return max(0.0, min(1.0, 1.0 - sum(correlations) / max(1, len(correlations))))


def _provider_routing_policy(
    request: FusionRequest,
    analysis: Mapping[str, Any],
    budget: Mapping[str, Any],
    scored: Sequence[tuple[ModelProfile, float]],
    selected: Sequence[ModelProfile],
) -> dict[str, Any]:
    selected_ids = {profile.profile_id for profile in selected}
    selected_providers = {profile.provider for profile in selected}
    selected_api_formats = {profile.api_format for profile in selected}
    fast_direct_cascade = bool(
        request.public_model == "axio-fast"
        and not _fast_light_verify_enabled(request, analysis, budget)
    )
    fast_deadline_ms = max(1, int(budget.get("max_latency_ms") or 2500))
    fallback_scored = [
        (
            profile,
            _provider_fallback_routing_score(
                profile,
                analysis,
                base_score=float(score),
                selected_providers=selected_providers,
                selected_api_formats=selected_api_formats,
            ),
            float(score),
        )
        for profile, score in scored
    ]
    if fast_direct_cascade:
        # The Fast cascade is serial.  Its fallback must be a profile that can
        # plausibly start and finish inside the same deadline, rather than the
        # highest-quality slow profile left after the primary attempt.
        fallback_scored.sort(
            key=lambda row: (
                0 if _fast_profile_within_deadline(row[0], fast_deadline_ms) else 1,
                int(row[0].p50_latency_ms)
                if row[0].p50_latency_ms is not None
                else fast_deadline_ms + 1,
                -round(float(row[1]), 8),
                row[0].profile_id,
            )
        )
    else:
        fallback_scored.sort(key=lambda row: row[1], reverse=True)
    fallback_pool = []
    canonical_replica_rows: dict[str, list[dict[str, Any]]] = {}
    for rank, (profile, routing_score, base_score) in enumerate(fallback_scored[:24], start=1):
        pricing_known = profile.input_cost_per_million is not None and profile.output_cost_per_million is not None
        canonical_identity_sha256 = profile.canonical_identity_sha256
        row = {
            "fallback_rank": rank,
            "profile_id_sha256": sha256_text(profile.profile_id),
            "provider_sha256": sha256_text(profile.provider),
            "runtime_canonical_identity_sha256": canonical_identity_sha256,
            "api_format": profile.api_format,
            "base_route_score": round(float(base_score), 4),
            "routing_score": round(float(routing_score), 4),
            "estimated_quality": round(_expected_profile_quality(profile, analysis), 4),
            "availability_score": round(_reliability_score(profile), 4),
            "latency_score": round(_latency_score(profile), 4),
            "cost_score": round(_cost_efficiency(profile), 4),
            "provider_diversity_score": 1.0 if profile.provider not in selected_providers else 0.0,
            "api_format_diversity_score": 1.0 if profile.api_format not in selected_api_formats else 0.0,
            "estimated_latency_ms": profile.p50_latency_ms,
            "pricing_known": pricing_known,
            "selected_in_primary_panel": profile.profile_id in selected_ids,
            "raw_profile_id_persisted": False,
            "raw_provider_name_persisted": False,
            "raw_model_name_persisted": False,
        }
        canonical_replica_rows.setdefault(canonical_identity_sha256, []).append(row)
        fallback_pool.append(row)
    canonical_replica_groups = []
    for canonical_identity_sha256, rows in canonical_replica_rows.items():
        provider_hashes = [str(row.get("provider_sha256") or "") for row in rows]
        profile_hashes = [str(row.get("profile_id_sha256") or "") for row in rows]
        api_formats = [str(row.get("api_format") or "") for row in rows]
        selected_profile_hashes = [
            str(row.get("profile_id_sha256") or "")
            for row in rows
            if row.get("selected_in_primary_panel") is True
        ]
        for replica_rank, row in enumerate(rows, start=1):
            row["canonical_replica_rank"] = replica_rank
            row["canonical_replica_count"] = len(rows)
        canonical_replica_groups.append(
            {
                "schema": "axio_fusion_api.canonical_replica_pool.v1",
                "runtime_canonical_identity_sha256": canonical_identity_sha256,
                "replica_count": len(rows),
                "provider_replica_count": len(set(provider_hashes)),
                "api_format_count": len(set(api_formats)),
                "profile_hashes": profile_hashes[:24],
                "provider_hashes": list(dict.fromkeys(provider_hashes))[:24],
                "selected_panel_profile_hashes": selected_profile_hashes[:12],
                "fallback_rank_order": [
                    _safe_nonnegative_int(row.get("fallback_rank")) or 0
                    for row in rows[:24]
                ],
                "raw_canonical_identity_persisted": False,
                "raw_profile_ids_persisted": False,
                "raw_provider_names_persisted": False,
                "raw_model_names_persisted": False,
            }
        )
    canonical_replica_groups.sort(
        key=lambda row: (
            -int(row.get("replica_count") or 0),
            str(row.get("runtime_canonical_identity_sha256") or ""),
        )
    )
    return {
        "schema": "axio_fusion_api.provider_routing_policy.v1",
        "enabled": True,
        "kernel": "openrouter_style_provider_routing_with_local_budget_and_privacy_gates",
        "fallback_enabled": True,
        "fallback_scope": "same_request_only_without_recursive_fusion",
        "canonical_replica_routing_enabled": True,
        "physical_profile_count": len(fallback_pool),
        "canonical_model_count": len(canonical_replica_groups),
        "canonical_replica_group_count": len(canonical_replica_groups),
        "canonical_replica_groups": canonical_replica_groups[:24],
        "same_canonical_model_failover_precedes_cross_model_fallback": True,
        "fallback_pool_sorted_by": (
            "fast_deadline_feasibility_then_observed_latency_then_availability_and_role_fit"
            if fast_direct_cascade
            else "availability_then_role_fit_then_latency_cost_and_diversity"
        ),
        "sort_priorities": (
            [
                "fast_deadline_feasibility",
                "observed_latency",
                "availability",
                "role_fit_quality",
                "provider_diversity",
                "api_format_diversity",
                "cost",
            ]
            if fast_direct_cascade
            else [
                "availability",
                "privacy_eligibility",
                "role_fit_quality",
                "provider_diversity",
                "api_format_diversity",
                "latency",
                "cost",
            ]
        ),
        "fast_direct_deadline_feasibility_enabled": fast_direct_cascade,
        "fast_direct_deadline_ms": fast_deadline_ms if fast_direct_cascade else None,
        "fallback_triggers": [
            "provider_timeout",
            "provider_http_retry_exhausted",
            "empty_or_unparseable_candidate",
            "runtime_circuit_open",
            "missing_required_role_output",
            "same_canonical_model_replica_failover",
        ],
        "context_transform_policy": {
            "provider_context_window_budget_enabled": True,
            "compress_lower_ranked_candidates_before_synthesis": bool(budget.get("rank_first_candidate_compression")),
            "middle_out_style_truncation_allowed_only_for_internal_candidate_packets": True,
            "raw_prompt_persisted": False,
        },
        "health_signal_sources": [
            "live_probe_generated_registry",
            "runtime_circuit_breaker",
            "safe_feedback_and_trace_calibration",
        ],
        "fallback_pool_count": len(fallback_pool),
        "fallback_pool": fallback_pool,
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _provider_fallback_routing_score(
    profile: ModelProfile,
    analysis: Mapping[str, Any],
    *,
    base_score: float,
    selected_providers: set[str],
    selected_api_formats: set[str],
) -> float:
    quality = _expected_profile_quality(profile, analysis)
    availability = _reliability_score(profile)
    latency = _latency_score(profile)
    cost = _cost_efficiency(profile)
    provider_diversity = 1.0 if profile.provider not in selected_providers else 0.0
    api_diversity = 1.0 if profile.api_format not in selected_api_formats else 0.0
    return (
        availability * 0.30
        + quality * 0.30
        + float(base_score) * 0.14
        + latency * 0.10
        + cost * 0.06
        + provider_diversity * 0.07
        + api_diversity * 0.03
    )


def _dag_node(
    node_id: str,
    kind: str,
    depends_on: Sequence[str],
    required_capabilities: Sequence[str],
    parallelizable: bool,
    max_cost_usd: float,
    verification_required: bool,
    assigned_role: str = "",
) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": kind,
        "depends_on": list(depends_on),
        "required_capabilities": list(dict.fromkeys(required_capabilities)),
        "parallelizable": bool(parallelizable),
        "max_cost_usd": round(float(max_cost_usd), 6),
        "verification_required": bool(verification_required),
        "assigned_role": assigned_role,
        "raw_prompt_persisted": False,
    }


def _primary_capabilities(analysis: Mapping[str, Any]) -> list[str]:
    domains = [str(domain) for domain in analysis.get("domains", [])]
    if not domains:
        domains = ["daily_work"]
    return [domain for domain in domains if domain in CAPABILITY_AXES] or ["daily_work"]


def _domain_subtask_nodes(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    domains = set(str(domain) for domain in analysis.get("domains", []) or [])
    nodes: list[dict[str, Any]] = []
    nodes.extend(_factuality_subtask_nodes(analysis))
    nodes.extend(_vertical_domain_subtask_nodes(analysis))
    if "code" in domains:
        nodes.extend(
            [
                _dag_node("understand_system_boundaries", "model_call", ["task_decomposition"], ["code", "logic"], False, 0.001, True, "primary_solver"),
                _dag_node("inspect_trust_boundaries", "model_call", ["understand_system_boundaries"], ["code", "critique"], True, 0.001, True, "critic"),
                _dag_node("check_authorization_paths", "model_call", ["understand_system_boundaries"], ["code", "critique"], True, 0.001, True, "critic"),
                _dag_node("check_injection_and_data_leakage", "model_call", ["understand_system_boundaries"], ["code", "critique"], True, 0.001, True, "critic"),
                _dag_node("domain_specialist_code_risk_review", "model_call", ["understand_system_boundaries"], ["code", "logic", "critique"], True, 0.0015, True, "domain_specialist"),
                _dag_node("validate_attack_or_failure_paths", "model_call", ["inspect_trust_boundaries", "check_authorization_paths", "check_injection_and_data_leakage"], ["code", "logic", "critique"], False, 0.002, True, "judge"),
            ]
        )
    if "science_knowledge" in domains:
        nodes.extend(
            [
                _dag_node("extract_scientific_claims", "model_call", ["task_decomposition"], ["science_knowledge", "structured_output"], False, 0.001, True, "primary_solver"),
                _dag_node("map_evidence_and_assumptions", "model_call", ["extract_scientific_claims"], ["science_knowledge", "critique"], True, 0.0015, True, "independent_solver"),
                _dag_node("compare_hypotheses", "model_call", ["extract_scientific_claims"], ["science_knowledge", "logic"], True, 0.0015, True, "independent_solver"),
                _dag_node("domain_specialist_scientific_evidence_review", "model_call", ["extract_scientific_claims"], ["science_knowledge", "logic", "critique"], True, 0.0015, True, "domain_specialist"),
                _dag_node("identify_evidence_gaps", "model_call", ["map_evidence_and_assumptions", "compare_hypotheses"], ["science_knowledge", "critique"], False, 0.001, True, "critic"),
            ]
        )
    if "math" in domains:
        nodes.extend(
            [
                _dag_node("formalize_problem", "model_call", ["task_decomposition"], ["math", "logic"], False, 0.001, True, "primary_solver"),
                _dag_node("solve_independently", "model_call", ["formalize_problem"], ["math"], True, 0.001, True, "independent_solver"),
                _dag_node("domain_specialist_solution_probe", "model_call", ["formalize_problem"], ["math", "logic"], True, 0.001, True, "domain_specialist"),
                _dag_node("verify_solution_constraints", "model_call", ["formalize_problem", "solve_independently"], ["math", "critique"], False, 0.001, True, "critic"),
            ]
        )
    if "logic" in domains and "math" not in domains:
        nodes.extend(
            [
                _dag_node("extract_constraints", "model_call", ["task_decomposition"], ["logic", "structured_output"], False, 0.001, True, "primary_solver"),
                _dag_node("search_counterexamples", "model_call", ["extract_constraints"], ["logic", "critique"], True, 0.001, True, "critic"),
                _dag_node("domain_specialist_constraint_probe", "model_call", ["extract_constraints"], ["logic", "structured_output"], True, 0.001, True, "domain_specialist"),
                _dag_node("rank_consistent_solutions", "model_call", ["extract_constraints", "search_counterexamples"], ["logic", "critique"], False, 0.001, True, "judge"),
            ]
        )
    if "agentic_tool_calling" in domains:
        nodes.extend(
            [
                _dag_node("tool_use_plan", "planning", ["task_decomposition"], ["agentic_tool_calling"], False, 0.0, True, "primary_solver"),
                _dag_node("tool_permission_check", "control", ["tool_use_plan"], ["safety"], False, 0.0, True),
                _dag_node("dry_run_tool_sequence", "tool_or_model_call", ["tool_permission_check"], ["agentic_tool_calling", "structured_output"], False, 0.001, True, "independent_solver"),
                _dag_node("domain_specialist_tool_workflow_probe", "tool_or_model_call", ["tool_permission_check"], ["agentic_tool_calling", "critique"], True, 0.001, True, "domain_specialist"),
            ]
        )
    if "current_information" in domains:
        nodes.extend(
            [
                _dag_node("current_information_need_check", "control", ["task_decomposition"], ["current_information"], False, 0.0, True),
                _dag_node("source_reliability_assessment", "model_call", ["current_information_need_check"], ["current_information", "critique"], False, 0.001, True, "critic"),
            ]
        )
    if not nodes and bool(analysis.get("decomposable")):
        nodes.extend(
            [
                _dag_node("clarify_deliverable", "model_call", ["task_decomposition"], ["daily_work", "structured_output"], False, 0.0005, False, "primary_solver"),
                _dag_node("independent_workflow_check", "model_call", ["clarify_deliverable"], ["daily_work", "critique"], True, 0.0005, True, "independent_solver"),
            ]
        )
    return _dedupe_dag_nodes(nodes)


def _factuality_subtask_nodes(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not bool(analysis.get("factuality_signal")):
        return []
    return [
        _dag_node(
            "extract_factual_claims",
            "model_call",
            ["task_decomposition"],
            ["structured_output", "critique"],
            False,
            0.001,
            True,
            "primary_solver",
        ),
        _dag_node(
            "source_grounding_check",
            "model_call",
            ["extract_factual_claims"],
            ["critique", "structured_output", "current_information"],
            True,
            0.0015,
            True,
            "critic",
        ),
        _dag_node(
            "hallucination_risk_review",
            "model_call",
            ["extract_factual_claims"],
            ["critique", "logic"],
            True,
            0.0015,
            True,
            "critic",
        ),
        _dag_node(
            "evidence_consistency_decision",
            "model_call",
            ["source_grounding_check", "hallucination_risk_review"],
            ["critique", "logic", "structured_output"],
            False,
            0.0015,
            True,
            "judge",
        ),
    ]


def _vertical_domain_subtask_nodes(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    signals = [
        str(item)
        for item in analysis.get("vertical_domain_signals", [])
        if str(item)
    ] if isinstance(analysis.get("vertical_domain_signals"), list) else []
    if not signals:
        return []
    nodes: list[dict[str, Any]] = []
    synthesis_deps: list[str] = []
    signal_set = set(signals)
    if "medical" in signal_set:
        nodes.extend(
            [
                _dag_node(
                    "medical_evidence_and_safety_guardrail",
                    "model_call",
                    ["task_decomposition"],
                    ["science_knowledge", "critique", "logic"],
                    True,
                    0.0015,
                    True,
                    "domain_specialist",
                ),
                _dag_node(
                    "clinical_uncertainty_and_scope_check",
                    "model_call",
                    ["medical_evidence_and_safety_guardrail"],
                    ["science_knowledge", "critique"],
                    True,
                    0.001,
                    True,
                    "critic",
                ),
            ]
        )
        synthesis_deps.append("clinical_uncertainty_and_scope_check")
    if "finance" in signal_set:
        nodes.extend(
            [
                _dag_node(
                    "finance_assumption_and_arithmetic_check",
                    "model_call",
                    ["task_decomposition"],
                    ["math", "logic", "critique"],
                    True,
                    0.0015,
                    True,
                    "domain_specialist",
                ),
                _dag_node(
                    "financial_risk_sensitivity_check",
                    "model_call",
                    ["finance_assumption_and_arithmetic_check"],
                    ["math", "critique", "daily_work"],
                    True,
                    0.001,
                    True,
                    "critic",
                ),
            ]
        )
        synthesis_deps.append("financial_risk_sensitivity_check")
    if "legal" in signal_set:
        nodes.append(
            _dag_node(
                "legal_authority_and_jurisdiction_check",
                "model_call",
                ["task_decomposition"],
                ["logic", "critique", "daily_work"],
                True,
                0.0015,
                True,
                "domain_specialist",
            )
        )
        synthesis_deps.append("legal_authority_and_jurisdiction_check")
    if "policy" in signal_set:
        nodes.append(
            _dag_node(
                "policy_stakeholder_and_regulatory_check",
                "model_call",
                ["task_decomposition"],
                ["logic", "critique", "daily_work"],
                True,
                0.0015,
                True,
                "domain_specialist",
            )
        )
        synthesis_deps.append("policy_stakeholder_and_regulatory_check")
    if "consulting" in signal_set:
        nodes.append(
            _dag_node(
                "consulting_actionability_tradeoff_check",
                "model_call",
                ["task_decomposition"],
                ["daily_work", "structured_output", "logic"],
                True,
                0.001,
                True,
                "domain_specialist",
            )
        )
        synthesis_deps.append("consulting_actionability_tradeoff_check")
    if len(synthesis_deps) >= 2:
        nodes.append(
            _dag_node(
                "vertical_domain_risk_synthesis",
                "model_call",
                synthesis_deps,
                ["critique", "logic", "structured_output"],
                False,
                0.0015,
                True,
                "judge",
            )
        )
    return nodes


def _dedupe_dag_nodes(nodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        result.append(dict(node))
    return result


def _max_dependency_depth(nodes: Sequence[Mapping[str, Any]]) -> int:
    by_id = {str(node.get("id") or ""): node for node in nodes}

    def depth(node_id: str, visiting: set[str] | None = None) -> int:
        visiting = set(visiting or set())
        if node_id in visiting:
            return 0
        visiting.add(node_id)
        node = by_id.get(node_id)
        if not node:
            return 0
        deps = [str(dep) for dep in node.get("depends_on", [])]
        if not deps:
            return 1
        return 1 + max(depth(dep, visiting) for dep in deps)

    return max((depth(node_id) for node_id in by_id), default=0)
