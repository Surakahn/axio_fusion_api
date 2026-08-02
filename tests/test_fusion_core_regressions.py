import json

from axio_fusion_api.orchestrator import (
    _CallBudget,
    _CostBudget,
    _DeadlineBudget,
    FusionEngine,
    _extract_json_with_mode,
    _candidate_prompt_packet,
    _expert_prompt,
    _expert_system,
    _fusion_evidence_candidate_count,
    _independent_candidate_count,
    _mandatory_fusion_stage_deadline_reservations,
    _candidates_for_fusion_finalization,
    _local_judge_candidates,
    _normalize_provider_judge_result,
    _dedupe_runtime_expert_roles,
    _missing_required_candidate_roles,
    _provider_request_for_role,
    _required_min_candidate_count,
)
from axio_fusion_api.compat import canonicalize_payload, render_response
from axio_fusion_api.evaluation import _fusion_provider_env_readiness
from axio_fusion_api.registry import (
    load_registry,
    normalize_profile,
    provider_configuration_source_summary,
)
from axio_fusion_api.router import (
    _assigned_profile_for_role,
    _best_judge,
    _best_synthesizer,
    _budget_for_request,
    _budget_with_direct_profile_deadline,
    _augment_pro_role_blueprint_for_screened_specialist,
    _latency_constrained_fusion_panel,
    _latency_optimize_expert_roles,
    _latency_optimize_stage_profiles,
    _role_assignments,
    _role_blueprint,
    _stage_profile_eligibility,
    analyze_request,
    build_route_plan,
)
from axio_fusion_api.schemas import CandidateResult, FusionRequest, sha256_text
from axio_fusion_api.trace_store import safe_execution_trace
from axio_fusion_api import orchestrator as orchestrator_module


def _profile(index: int, *, critique: float = 0.8, structured: float = 0.84):
    return normalize_profile(
        {
            "provider": f"provider-{index}",
            "model": f"model-{index}",
            "api_format": ("chat", "responses", "anthropic", "gemini")[index % 4],
            "capabilities": {
                "science_knowledge": 0.9,
                "multilingual": 0.84,
                "code": 0.9,
                "math": 0.9,
                "logic": 0.9,
                "daily_work": 0.88,
                "structured_output": structured,
                "critique": critique,
                "long_context": 0.86,
            },
            "p50_latency_ms": 120,
        }
    )


def _latency_profile(name: str, latency: int, *, critique: float = 0.8, structured: float = 0.84):
    return normalize_profile(
        {
            "provider": f"latency-{name}",
            "model": name,
            "api_format": "chat",
            "p50_latency_ms": latency,
            "capabilities": {
                "daily_work": 0.86,
                "logic": 0.84,
                "structured_output": structured,
                "critique": critique,
            },
        }
    )


def _screened_profile(
    name: str,
    *,
    allowed_roles,
    disallowed_roles=(),
):
    return normalize_profile(
        {
            "provider": f"screened-{name}",
            "model": name,
            "canonical_model_id": name,
            "api_format": "chat",
            "p50_latency_ms": 120,
            "capabilities": {
                "science_knowledge": 0.9,
                "multilingual": 0.85,
                "code": 0.9,
                "math": 0.9,
                "logic": 0.9,
                "daily_work": 0.9,
                "structured_output": 0.9,
                "critique": 0.9,
                "long_context": 0.9,
            },
            "screening_allowed_roles": list(allowed_roles),
            "screening_disallowed_roles": list(disallowed_roles),
        }
    )


def test_required_runtime_quorum_does_not_count_reused_critic_as_independent_seat():
    primary = _profile(0)
    independent = _profile(1)
    route_plan = {
        "judge_contract": {"required": True},
        "budget": {"min_judge_candidate_count": 3},
    }
    roles = [
        {"role": "primary_solver", "model": primary.safe_dict()},
        {"role": "independent_solver", "model": independent.safe_dict()},
        {
            "role": "critic",
            "model": independent.safe_dict(),
            "role_profile_reuse": {
                "reused": True,
                "counts_as_independent_evidence": False,
            },
        },
    ]

    assert _required_min_candidate_count(route_plan, roles) == 2


def test_runtime_expert_panel_suppresses_duplicate_canonical_role_without_hiding_unique_critic():
    primary = _profile(0)
    independent = _profile(1)
    specialist = _profile(2)
    roles = [
        {"role": "primary_solver", "model": primary.safe_dict()},
        {"role": "independent_solver", "model": independent.safe_dict()},
        {"role": "critic", "model": independent.safe_dict()},
        {"role": "domain_specialist", "model": specialist.safe_dict()},
    ]

    admitted, receipt = _dedupe_runtime_expert_roles(roles)

    assert [row["role"] for row in admitted] == [
        "primary_solver",
        "independent_solver",
        "domain_specialist",
    ]
    assert receipt["suppressed_duplicate_role_count"] == 1
    suppressed = receipt["suppressed_roles"][0]
    assert suppressed["role"] == "critic"
    assert suppressed["retained_role"] == "independent_solver"
    assert suppressed["counts_as_independent_evidence"] is False

    route_plan = {
        "roles": roles,
        "runtime_expert_panel": receipt,
    }
    completed = [
        CandidateResult(
            "primary_solver",
            "primary_solver",
            primary.profile_id,
            primary.provider,
            primary.model,
            "primary",
            canonical_identity=primary.canonical_identity,
        ),
        CandidateResult(
            "independent_solver",
            "independent_solver",
            independent.profile_id,
            independent.provider,
            independent.model,
            "independent",
            canonical_identity=independent.canonical_identity,
        ),
        CandidateResult(
            "domain_specialist",
            "domain_specialist",
            specialist.profile_id,
            specialist.provider,
            specialist.model,
            "specialist",
            canonical_identity=specialist.canonical_identity,
        ),
    ]

    assert _missing_required_candidate_roles(route_plan, completed) == []


def test_judge_json_extractor_accepts_transport_wrappers_without_relaxing_schema():
    parsed, mode = _extract_json_with_mode(
        "Here is the structured result:\n"
        '{"ready_for_synthesis": true, "missing_coverage": []}\n'
        'END {"broken": }'
    )

    assert mode == "json_balanced_substring"
    assert parsed == {"ready_for_synthesis": True, "missing_coverage": []}


def test_panel_quorum_recovery_counts_unique_completed_canonical_branches():
    candidates = [
        CandidateResult("primary", "primary_solver", "p1", "provider-a", "model-a", "one", canonical_identity="model-a"),
        CandidateResult("critic", "critic", "p2", "provider-b", "model-b", "two", canonical_identity="model-b"),
        CandidateResult("reused-critic", "critic", "p2", "provider-b", "model-b", "three", canonical_identity="model-b"),
    ]

    assert _independent_candidate_count(candidates) == 2


def test_panel_repair_stops_at_independent_quorum_without_filling_optional_hermes_seats():
    class RepairClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            del request, prompt, system, timeout
            self.calls.append(profile.profile_id)
            return json.dumps({"answer": "bounded repair answer", "confidence": 0.8})

    profiles = [_profile(index) for index in range(4)]
    fallback_pool = [
        {
            "profile_id_sha256": sha256_text(profile.profile_id),
            "runtime_canonical_identity_sha256": profile.canonical_identity_sha256,
            "fallback_rank": index + 1,
            "routing_score": 0.8 - index * 0.01,
        }
        for index, profile in enumerate(profiles[1:])
    ]
    route_plan = {
        "hermes_moa": {
            "enabled": True,
            "reference_roles": ["primary_solver", "independent_solver", "critic"],
        },
        "provider_routing_policy": {"fallback_pool": fallback_pool},
    }
    primary = CandidateResult(
        "primary_solver",
        "primary_solver",
        profiles[0].profile_id,
        profiles[0].provider,
        profiles[0].model,
        "primary answer",
        canonical_identity=profiles[0].canonical_identity,
    )
    client = RepairClient()
    engine = FusionEngine(profiles, client=client, cache_enabled=False)
    completed = [primary]

    receipt = engine._repair_panel(
        FusionRequest(model="axio-pro", prompt="bounded repair task"),
        route_plan,
        [primary],
        completed,
        required_min_candidate_count=2,
        call_budget=_CallBudget(4),
    )

    assert receipt["success"] is True
    assert receipt["repair_attempt_count"] == 1
    assert receipt["independent_completed_after"] == 2
    assert client.calls == [profiles[1].profile_id]
    # Missing optional Hermes references must remain a receipt fact, not a
    # reason to spend the remaining fallback pool after quorum is met.
    assert receipt["missing_hermes_reference_roles_after"]


def test_panel_repair_hard_stops_after_bounded_failed_attempts():
    class FailingClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            del request, prompt, system, timeout
            self.calls.append(profile.profile_id)
            raise RuntimeError("fixture provider unavailable")

    profiles = [_profile(index) for index in range(8)]
    fallback_pool = [
        {
            "profile_id_sha256": sha256_text(profile.profile_id),
            "runtime_canonical_identity_sha256": profile.canonical_identity_sha256,
            "fallback_rank": index + 1,
            "routing_score": 0.8 - index * 0.01,
        }
        for index, profile in enumerate(profiles[1:])
    ]
    route_plan = {
        "provider_routing_policy": {"fallback_pool": fallback_pool},
        "roles": [{"role": "primary_solver"}],
    }
    primary = CandidateResult(
        "primary_solver",
        "primary_solver",
        profiles[0].profile_id,
        profiles[0].provider,
        profiles[0].model,
        "primary answer",
        canonical_identity=profiles[0].canonical_identity,
    )
    client = FailingClient()
    engine = FusionEngine(profiles, client=client, cache_enabled=False)
    completed = [primary]

    receipt = engine._repair_panel(
        FusionRequest(model="axio-pro", prompt="bounded failure task"),
        route_plan,
        [primary],
        completed,
        required_min_candidate_count=8,
        call_budget=_CallBudget(20),
    )

    assert receipt["success"] is False
    assert receipt["repair_attempt_count"] == 4
    assert len(client.calls) == 4
    assert "repair_attempt_limit_reached" in receipt["blocked_reasons"]


def test_screening_deny_only_profile_cannot_become_judge_or_synthesizer():
    denied = _screened_profile(
        "narrow",
        allowed_roles=("domain_specialist",),
        disallowed_roles=("judge", "synthesizer"),
    )

    assert _best_judge([denied]) is None
    assert _best_synthesizer([denied], {"domains": ["code"]}) is None


def test_role_assignment_fails_closed_when_primary_role_is_denied():
    denied = _screened_profile(
        "specialist-only",
        allowed_roles=("domain_specialist",),
        disallowed_roles=("primary_solver", "judge", "synthesizer"),
    )
    request = FusionRequest(model="axio-pro", prompt="Solve a code task.")
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    blueprint = _role_blueprint(request, analysis, budget)
    assert _assigned_profile_for_role(
        "primary_solver",
        [denied],
        analysis,
        blueprint,
        used_profile_ids=set(),
    ) is None
    assert _role_assignments(request, analysis, [denied], True, blueprint, budget=budget) == []


def test_missing_screened_mandatory_stages_blocks_provider_fusion():
    roles = ("primary_solver", "independent_solver")
    first = _screened_profile("primary", allowed_roles=roles, disallowed_roles=("judge", "synthesizer", "critic"))
    second = _screened_profile("independent", allowed_roles=roles, disallowed_roles=("judge", "synthesizer", "critic"))
    request = FusionRequest(
        model="axio-pro",
        prompt="Solve a complex scientific code task and verify contradictions.",
    )

    route_plan = build_route_plan(request, [first, second])
    assigned_roles = {row["role"] for row in route_plan["roles"]}

    assert assigned_roles == {"primary_solver"}
    provider_gate = route_plan["role_gate"]["provider_fusion"]
    assert {"primary_solver", "independent_solver"}.issubset(
        set(provider_gate["assigned_roles"])
    )
    assert "judge" in provider_gate["missing_roles"]
    assert "synthesizer" in provider_gate["missing_roles"]
    assert route_plan["fusion_admission"]["activated"] is False
    assert "screening_role_gate_blocked_judge" in route_plan["fusion_admission"]["blocked_reasons"]
    assert "screening_role_gate_blocked_synthesizer" in route_plan["fusion_admission"]["blocked_reasons"]


def _short_verification_profiles():
    primary = _screened_profile(
        "primary-for-short",
        allowed_roles=("primary_solver",),
    )
    short = _screened_profile(
        "short-only",
        allowed_roles=("short_verification",),
        disallowed_roles=(
            "primary_solver",
            "independent_solver",
            "critic",
            "domain_specialist",
            "judge",
            "synthesizer",
        ),
    )
    return primary, short


def test_short_verifier_opens_bounded_local_consensus_without_solver_promotion():
    primary, short = _short_verification_profiles()
    request = FusionRequest(
        model="axio-pro",
        prompt="Solve a complex scientific code task and verify the key constraint.",
    )

    route_plan = build_route_plan(request, [primary, short])
    assigned_roles = {row["role"] for row in route_plan["roles"]}

    assert assigned_roles == {"primary_solver", "short_verification"}
    assert route_plan["fusion_admission"]["activated"] is True
    assert route_plan["fusion_admission"]["fusion_finalization_mode"] == "local_consensus"
    assert "independent_solver" not in assigned_roles
    assert route_plan["role_gate"]["local_consensus"]["missing_roles"] == []
    assert {"judge", "synthesizer"}.issubset(
        set(route_plan["role_gate"]["provider_fusion"]["missing_roles"])
    )


def test_reused_critic_does_not_suppress_distinct_short_verifier():
    primary = _screened_profile(
        "primary-with-reused-critic",
        allowed_roles=("primary_solver", "critic", "short_verification"),
        disallowed_roles=(
            "independent_solver",
            "domain_specialist",
            "judge",
            "synthesizer",
        ),
    )
    short_one = _screened_profile(
        "short-one",
        allowed_roles=("short_verification",),
        disallowed_roles=(
            "primary_solver",
            "independent_solver",
            "critic",
            "domain_specialist",
            "judge",
            "synthesizer",
        ),
    )
    short_two = _screened_profile(
        "short-two",
        allowed_roles=("short_verification",),
        disallowed_roles=(
            "primary_solver",
            "independent_solver",
            "critic",
            "domain_specialist",
            "judge",
            "synthesizer",
        ),
    )

    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "quality_target": 0.9,
            "max_models": 3,
            "messages": [
                {
                    "role": "user",
                    "content": "Solve a complex scientific code task and verify contradictions.",
                }
            ],
        }
    )
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    blueprint = _role_blueprint(request, analysis, budget)
    blueprint.append(
        {
            "role": "short_verification",
            "objective": "verify one critical claim",
            "required_capabilities": ["critique", "structured_output"],
            "context_scope": "one_key_claim_only",
        }
    )
    roles = _role_assignments(
        request,
        analysis,
        [primary, short_one, short_two],
        True,
        blueprint,
        budget=budget,
    )

    assert {row["role"] for row in roles} == {
        "primary_solver",
        "critic",
        "short_verification",
    }
    critic = next(row for row in roles if row["role"] == "critic")
    assert critic["role_profile_reuse"]["counts_as_independent_evidence"] is False


def test_latency_repair_does_not_replace_narrow_evidence_with_roleless_fast_models():
    def screened(name, latency, allowed, denied=()):
        return normalize_profile(
            {
                "provider": f"latency-{name}",
                "model": name,
                "canonical_model_id": name,
                "api_format": "chat",
                "p50_latency_ms": latency,
                "capabilities": {
                    "science_knowledge": 0.8,
                    "code": 0.8,
                    "logic": 0.8,
                    "daily_work": 0.8,
                    "structured_output": 0.8,
                    "critique": 0.8,
                    "long_context": 0.8,
                },
                "screening_allowed_roles": list(allowed),
                "screening_disallowed_roles": list(denied),
            }
        )

    all_roles = (
        "primary_solver",
        "independent_solver",
        "critic",
        "domain_specialist",
        "judge",
        "synthesizer",
        "short_verification",
        "simple_classification",
        "structured_extraction",
        "single_tool_argument_validation",
    )
    profiles = [
        screened("primary", 4_000, ("primary_solver", "short_verification")),
        screened(
            "short",
            13_000,
            ("short_verification",),
            (
                "primary_solver",
                "independent_solver",
                "critic",
                "domain_specialist",
                "judge",
                "synthesizer",
            ),
        ),
        screened("fast-roleless-a", 100, (), all_roles),
        screened("fast-roleless-b", 110, (), all_roles),
    ]
    request = canonicalize_payload(
        {
            "model": "axio-terra",
            "quality_target": 0.9,
            "max_models": 3,
            "messages": [
                {
                    "role": "user",
                    "content": "Analyze a complex high-risk code workflow and verify the key constraint.",
                }
            ],
        }
    )

    route_plan = build_route_plan(request, profiles)

    assert [row["model"] for row in route_plan["selected_models"]] == [
        "primary",
        "short",
    ]
    assert route_plan["latency_constrained_panel"]["applied"] is False
    assert route_plan["latency_constrained_panel"]["reason"] == "no_distinct_candidate_panel"
    assert route_plan["fusion_admission"]["activated"] is False


def test_unused_domain_prior_does_not_suppress_short_verification_target():
    primary = _screened_profile(
        "primary-with-domain-prior",
        allowed_roles=("primary_solver", "domain_specialist"),
    )
    short = _screened_profile(
        "short-with-domain-prior",
        allowed_roles=("short_verification",),
        disallowed_roles=(
            "primary_solver",
            "independent_solver",
            "critic",
            "domain_specialist",
            "judge",
            "synthesizer",
        ),
    )
    request = FusionRequest(
        model="axio-pro",
        prompt="Solve a complex scientific code task and verify the key constraint.",
    )

    route_plan = build_route_plan(request, [primary, short])

    assert {row["role"] for row in route_plan["roles"]} == {
        "primary_solver",
        "short_verification",
    }
    assert route_plan["fusion_admission"]["activated"] is True


def test_same_primary_domain_prior_does_not_count_as_independent_evidence():
    primary = _screened_profile(
        "primary-domain-only",
        allowed_roles=("primary_solver", "domain_specialist"),
    )
    request = FusionRequest(
        model="axio-pro",
        prompt="Solve a difficult scientific code task and verify contradictions.",
    )

    route_plan = build_route_plan(request, [primary])

    assert route_plan["fusion_admission"]["activated"] is False
    assert "insufficient_independent_models" in route_plan["fusion_admission"]["blocked_reasons"]


def test_short_verifier_failure_remains_a_missing_required_role():
    primary, short = _short_verification_profiles()
    request = FusionRequest(
        model="axio-terra",
        prompt="Review a medical production code workflow and verify one critical constraint.",
    )
    route_plan = build_route_plan(request, [primary, short])
    primary_candidate = CandidateResult(
        "primary_solver",
        "primary_solver",
        primary.profile_id,
        primary.provider,
        primary.model,
        "primary answer",
        canonical_identity=primary.canonical_identity,
    )

    assert "short_verification" in _missing_required_candidate_roles(
        route_plan,
        [primary_candidate],
    )
    assert route_plan["fusion_admission"]["activated"] is True


def test_short_verifier_is_evidence_but_not_independent_solver():
    primary, short = _short_verification_profiles()
    candidates = [
        CandidateResult(
            "primary_solver",
            "primary_solver",
            primary.profile_id,
            primary.provider,
            primary.model,
            "primary answer",
            canonical_identity=primary.canonical_identity,
        ),
        CandidateResult(
            "short_verification",
            "short_verification",
            short.profile_id,
            short.provider,
            short.model,
            "pass",
            canonical_identity=short.canonical_identity,
        ),
    ]

    assert _independent_candidate_count(candidates) == 1
    assert _fusion_evidence_candidate_count(candidates) == 2


def test_short_verifier_prompt_and_candidate_packet_are_narrow_and_tool_free():
    primary, short = _short_verification_profiles()
    request = FusionRequest(
        model="axio-pro",
        prompt="Verify the one critical condition.",
        tools=(
            {
                "type": "function",
                "function": {"name": "sensitive_external_action"},
            },
        ),
    )
    route_plan = build_route_plan(request, [primary, short])
    prompt = _expert_prompt(request, "short_verification", route_plan=route_plan)
    system = _expert_system(request.system, "short_verification", route_plan=route_plan)
    provider_request = _provider_request_for_role(
        request,
        "short_verification",
        route_plan=route_plan,
    )
    candidate = CandidateResult(
        "short_verification",
        "short_verification",
        short.profile_id,
        short.provider,
        short.model,
        "pass",
        canonical_identity=short.canonical_identity,
    )
    packet = _candidate_prompt_packet(candidate, answer_char_limit=400)

    assert "Narrow verification scope" in prompt
    assert "sensitive_external_action" not in prompt
    assert "do not solve" in system.lower()
    assert provider_request.tools == ()
    assert packet["evidence_scope"] == "narrow_verification_only"
    assert packet["counts_as_full_independent_solver"] is False


def test_provider_replicas_of_one_canonical_short_verifier_count_once():
    first = _screened_profile(
        "short-provider-a",
        allowed_roles=("short_verification",),
        disallowed_roles=("primary_solver", "independent_solver"),
    )
    second = normalize_profile(
        {
            **first.safe_dict(),
            "provider": "short-provider-b",
            "model": first.model,
            "canonical_model_id": first.canonical_identity,
            "profile_id": "short-provider-b/short-provider-a",
        }
    )
    candidates = [
        CandidateResult(
            "short-a",
            "short_verification",
            first.profile_id,
            first.provider,
            first.model,
            "pass",
            canonical_identity=first.canonical_identity,
        ),
        CandidateResult(
            "short-b",
            "short_verification",
            second.profile_id,
            second.provider,
            second.model,
            "pass",
            canonical_identity=first.canonical_identity,
        ),
    ]

    assert _fusion_evidence_candidate_count(candidates) == 1


def test_screening_prior_can_open_bounded_stage_without_overwriting_runtime_capability():
    screened_stage = normalize_profile(
        {
            "provider": "screened-stage",
            "model": "stage-prior",
            "canonical_model_id": "stage-prior",
            "api_format": "chat",
            "p50_latency_ms": 1_800,
            # These remain neutral because this fixture has no runtime stage
            # calibration. The role-specific research prior is separate.
            "capabilities": {},
            "screening_allowed_roles": [
                "primary_solver",
                "independent_solver",
                "judge",
                "synthesizer",
            ],
            "screening_capability_overall": 0.77,
            "screening_capability_axes": {
                "science_knowledge": 0.70,
                "code": 0.90,
                "logic": 0.90,
                "structured_output": 0.85,
                "critique": 0.70,
                "long_context": 0.90,
                "daily_work": 0.45,
            },
        }
    )
    request = FusionRequest(
        model="axio-terra",
        prompt="Review a scientific code decision and identify contradictions.",
    )
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)

    judge_ready, judge_basis = _stage_profile_eligibility(
        screened_stage, "judge", analysis, budget
    )
    synthesizer_ready, synthesizer_basis = _stage_profile_eligibility(
        screened_stage, "synthesizer", analysis, budget
    )

    assert screened_stage.capability("critique") == 0.35
    assert screened_stage.capability("structured_output") == 0.35
    assert judge_ready is True
    assert synthesizer_ready is True
    assert judge_basis == "screening_prior_fallback"
    assert synthesizer_basis == "screening_prior_fallback"


def test_expert_latency_optimizer_never_reuses_another_expert_profile():
    primary = _latency_profile("primary", 100, critique=0.86, structured=0.86)
    independent = _latency_profile("independent", 1_000, critique=0.86, structured=0.86)
    request = FusionRequest(model="axio-pro", prompt="Review a complex workflow.")
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    roles = [
        {"role": "primary_solver", "model": primary.safe_dict()},
        {"role": "independent_solver", "model": independent.safe_dict()},
    ]

    optimized, _receipt = _latency_optimize_expert_roles(
        roles=roles,
        selected=[primary, independent],
        direct_baseline_profile=primary,
        analysis=analysis,
        budget=budget,
    )
    optimized_profile_ids = [
        row["model"]["profile_id"]
        for row in optimized
        if row.get("role") in {"primary_solver", "independent_solver"}
    ]

    assert len(optimized_profile_ids) == 2
    assert len(set(optimized_profile_ids)) == 2


def test_legacy_profiles_without_screening_contract_keep_stage_compatibility():
    """Unscreened unit profiles do not turn neutral capability defaults into denies."""

    primary = normalize_profile(
        {
            "provider": "alpha",
            "model": "primary",
            "capabilities": {"science_knowledge": 0.90, "critique": 0.80},
        }
    )
    independent = normalize_profile(
        {
            "provider": "beta",
            "model": "independent",
            "capabilities": {"science_knowledge": 0.80, "critique": 0.90},
        }
    )
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "messages": [{"role": "user", "content": "analyze a scientific claim"}],
        }
    )
    route_plan = build_route_plan(request, [primary, independent])

    assert route_plan["fusion_admission"]["activated"] is True
    assert {row["role"] for row in route_plan["roles"]} >= {
        "primary_solver",
        "independent_solver",
        "judge",
        "synthesizer",
    }



def test_deadline_budget_reserves_measured_mandatory_stages_from_optional_work(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(orchestrator_module.time, "monotonic", lambda: clock["now"])
    budget = _DeadlineBudget(
        1_000,
        mandatory_stage_reservations_ms={"judge": 400, "synthesizer": 400},
    )

    clock["now"] = 0.25
    assert budget.acquire(kind="model_role", role="primary_solver", profile_id="optional") is False
    assert budget.acquire(kind="judge", role="judge", profile_id="judge") is True
    assert 0.34 <= budget.timeout_seconds(FusionRequest(model="axio-pro", prompt="task"), role="judge") <= 0.36

    receipt = budget.safe_dict()
    assert receipt["mandatory_stage_deadline_reservation_enabled"] is True
    assert receipt["mandatory_stage_deadline_pending_ms"] == 400
    assert receipt["mandatory_stage_deadline_consumed_ms"] == 400
    assert receipt["mandatory_stage_deadline_reservation_skip_count"] == 1
    assert receipt["skipped_calls"][0]["reason"] == "mandatory_stage_deadline_reservation"


def test_dynamic_call_reservations_are_atomic_and_consumed_by_stage_role():
    budget = _CallBudget(
        6,
        mandatory_stage_reservations={"judge": 1},
    )

    # The initial Judge is admitted and executed before Hermes discovers the
    # feedback gap.  The dynamic reservation is added only after that call.
    assert budget.acquire(
        kind="judge",
        role="judge",
        profile_id="provider-a/judge",
    ) is True

    assert budget.reserve_mandatory_stage_reservations(
        {"targeted_escalation": 1, "judge": 1},
        reason="hermes_feedback_test",
    ) is True
    assert budget.acquire(
        kind="model_role",
        role="targeted_escalation",
        profile_id="provider-a/model-a",
    ) is True
    assert budget.acquire(
        kind="judge",
        role="judge",
        profile_id="provider-a/rejudge",
    ) is True

    receipt = budget.safe_dict()
    assert receipt["consumed_dynamic_mandatory_stage_call_count"] == 2
    assert receipt["consumed_mandatory_stage_call_count"] == 1
    assert receipt["reserved_mandatory_stage_call_count"] == 0


def test_dynamic_cost_reservation_survives_same_canonical_replica_failover():
    first = normalize_profile(
        {
            "provider": "provider-a",
            "model": "logical-model",
            "canonical_model_id": "logical-model-v1",
            "input_cost_per_million": 1.0,
            "output_cost_per_million": 1.0,
        }
    )
    failover = normalize_profile(
        {
            "provider": "provider-b",
            "model": "logical-model",
            "canonical_model_id": "logical-model-v1",
            "input_cost_per_million": 1.0,
            "output_cost_per_million": 1.0,
        }
    )
    budget = _CostBudget(1.0)

    assert budget.reserve_stage(
        kind="judge",
        role="judge",
        profile=first,
        prompt="judge prompt",
        system="judge system",
        expected_output_tokens=64,
        reason="hermes_feedback_test",
    ) is True
    reservation = budget.acquire(
        kind="judge",
        role="judge",
        profile=failover,
        prompt="judge prompt",
        system="judge system",
        expected_output_tokens=64,
    )
    assert reservation is not None
    assert reservation.match_mode == "canonical_identity_failover"
    assert budget.safe_dict()["dynamic_stage_reservation_count"] == 0
    assert any(
        row.get("match_mode") == "canonical_identity_failover"
        for row in budget.safe_dict()["dynamic_stage_receipts"]
    )


def test_deadline_budget_keeps_initial_and_dynamic_same_role_reservations_separate():
    budget = _DeadlineBudget(
        5_000,
        mandatory_stage_reservations_ms={"judge": 1_000},
    )
    assert budget.reserve_stage_reservations(
        {"targeted_escalation": 500, "judge": 500},
        reason="hermes_feedback_test",
    ) is True

    assert budget.acquire(kind="judge", role="judge", profile_id="judge-initial") is True
    assert budget.acquire(kind="judge", role="judge", profile_id="judge-rejudge") is True
    receipt = budget.safe_dict()
    assert receipt["mandatory_stage_deadline_consumed_ms"] == 1_000
    assert receipt["mandatory_stage_deadline_dynamic_consumed_ms"] == 500
    assert receipt["mandatory_stage_deadline_pending_ms"] == 500


def test_mandatory_stage_deadline_reservations_prefer_p95_and_have_bounded_margin():
    route_plan = {
        "judge_contract": {"required": True},
        "budget": {
            "initial_fusion_call_plan": {"complete_fusion_feasible": True},
        },
        "roles": [
            {"role": "judge", "model": {"p50_latency_ms": 500, "p95_latency_ms": 900}},
            {"role": "synthesizer", "model": {"p50_latency_ms": 300}},
        ],
    }

    reservations = _mandatory_fusion_stage_deadline_reservations(route_plan)

    assert reservations == {"judge": 1_080, "synthesizer": 480}


def _local_consensus_fixture_profiles(*, cost=None):
    def profile(provider, model, latency, daily, logic, critique, *, cost=None):
        payload = {
            "provider": provider,
            "model": model,
            "canonical_model_id": model,
            "api_format": "chat",
            "p50_latency_ms": latency,
            "capabilities": {
                "daily_work": daily,
                "logic": logic,
                "critique": critique,
                "structured_output": critique,
            },
        }
        if cost is not None:
            payload.update(
                {
                    "input_cost_per_million": cost,
                    "output_cost_per_million": cost,
                }
            )
        return normalize_profile(payload)

    return [
        profile("fast-one", "solver-a", 100, 0.99, 0.99, 0.70, cost=cost),
        profile("fast-two", "solver-b", 120, 0.95, 0.95, 0.72, cost=cost),
        profile("fast-three", "solver-c", 130, 0.94, 0.94, 0.74, cost=cost),
        profile("slow-critic", "verifier-d", 5_000, 0.75, 0.75, 0.99, cost=cost),
    ]


def test_local_consensus_route_replaces_over_3x_provider_plan_for_terra_and_pro():
    profiles = _local_consensus_fixture_profiles()
    prompt = "Analyze a high-risk production workflow and prove the routing constraints are logically consistent."

    for public_model, minimum_candidates in (("axio-terra", 2), ("axio-pro", 3)):
        route_plan = build_route_plan(
            FusionRequest(model=public_model, prompt=prompt),
            profiles,
        )
        admission = route_plan["fusion_admission"]
        local_plan = route_plan["budget"]["local_consensus_plan"]

        assert route_plan["strategy"] == f"{'terra' if public_model == 'axio-terra' else 'pro'}_local_consensus"
        assert admission["activated"] is True
        assert admission["fusion_finalization_mode"] == "local_consensus"
        assert admission["provider_plan_blocked_reasons"] == [
            "fusion_latency_exceeds_3x_single_model_guard"
        ]
        assert admission["latency_multiplier_guard"]["blocked"] is False
        assert admission["latency_multiplier_guard"]["provider_plan_blocked"] is True
        assert local_plan["feasible"] is True
        assert local_plan["minimum_candidate_count"] == minimum_candidates
        assert local_plan["latency_multiplier_vs_direct"] <= 3.0
        assert route_plan["budget"]["fusion_finalization_mode"] == "local_consensus"
        assert route_plan["runtime_guards"]["provider_stage_calls_reserved"] is False
        assert route_plan["runtime_guards"]["local_consensus_provider_stage_calls_reserved"] is False
        assert [row["role"] for row in route_plan["roles"]] == [
            "primary_solver",
            "independent_solver",
        ] + (["critic"] if public_model == "axio-pro" else [])
        assert route_plan["judge_contract"]["provider_judge_required"] is False
        assert route_plan["judge_contract"]["provider_synthesizer_required"] is False
        assert route_plan["task_dag"]["fusion_finalization_mode"] == "local_consensus"
        assert "local_consensus_finalize" in {
            node["id"] for node in route_plan["task_dag"]["nodes"]
        }
        assert "structured_judge" not in {
            node["id"] for node in route_plan["task_dag"]["nodes"]
        }
        assert "final_synthesis" not in {
            node["id"] for node in route_plan["task_dag"]["nodes"]
        }


def test_neutral_runtime_portfolio_uses_provider_diversity_and_one_parallel_backup():
    profiles = [
        normalize_profile(
            {
                "provider": provider,
                "model": f"runtime-model-{index}",
                "api_format": api_format,
                "p50_latency_ms": latency,
                "health": "available",
                "source": "runtime_channel_live_probe",
            }
        )
        for index, (provider, api_format, latency) in enumerate(
            (
                ("channel-a", "chat", 100),
                ("channel-b", "responses", 110),
                ("channel-c", "chat", 120),
                ("channel-d", "responses", 130),
            )
        )
    ]
    route_plan = build_route_plan(
        FusionRequest(
            model="axio-pro",
            prompt="Compare two difficult scientific hypotheses and identify falsifying evidence.",
        ),
        profiles,
    )

    local_plan = route_plan["budget"]["local_consensus_plan"]
    assert local_plan["capability_evidence_mode"] == "operational_only_neutral_capabilities"
    assert local_plan["provider_diversity_floor"] == 3
    assert local_plan["provider_diversity_floor_met"] is True
    assert local_plan["redundancy_enabled"] is True
    assert local_plan["redundancy_candidate_count"] == 1
    assert local_plan["panel_size"] == 4
    assert len({*local_plan["panel_provider_hashes"]}) >= 3
    assert "backup_solver" in {row["role"] for row in route_plan["roles"]}
    assert local_plan["latency_multiplier_vs_direct"] <= 3.0


def test_local_consensus_respects_channel_single_flight_and_uses_cross_provider_panel():
    def profile(provider, model, latency, traffic_control):
        return normalize_profile(
            {
                "provider": provider,
                "model": model,
                "canonical_model_id": model,
                "api_format": "chat",
                "p50_latency_ms": latency,
                "health": "available",
                "source": "runtime_channel_live_probe",
                "traffic_control": traffic_control,
                "capabilities": {
                    "science_knowledge": 0.9,
                    "logic": 0.9,
                    "structured_output": 0.9,
                    "critique": 0.9,
                },
            }
        )

    shared_nvidia = {
        "scope": "channel",
        "max_in_flight": 1,
        "rate_limit_key_pool": "shared",
    }
    profiles = [
        profile("nvidia", "nvidia-a", 100, shared_nvidia),
        profile("nvidia", "nvidia-b", 110, shared_nvidia),
        profile("tokenapis", "tokenapis-a", 130, {"scope": "profile"}),
    ]

    route_plan = build_route_plan(
        FusionRequest(
            model="axio-terra",
            prompt="Analyze a difficult scientific constraint and verify the conclusion.",
        ),
        profiles,
    )
    local_plan = route_plan["budget"]["local_consensus_plan"]

    assert local_plan["provider_serialization_detected"] is True
    assert local_plan["provider_parallelism_constraint"] is True
    assert local_plan["provider_diversity_required"] is True
    assert local_plan["provider_diversity_requirement_reason"] == "channel_single_flight_parallelism"
    assert local_plan["provider_serialization_group_count"] == 1
    assert local_plan["provider_serialization_candidate_count"] == 2
    assert local_plan["feasible"] is True
    assert len(set(local_plan["panel_provider_hashes"])) == 2


def test_local_consensus_blocks_when_only_one_channel_single_flight_pool_exists():
    traffic_control = {
        "scope": "channel",
        "max_in_flight": 1,
        "rate_limit_key_pool": "shared",
    }
    profiles = [
        normalize_profile(
            {
                "provider": "nvidia",
                "model": f"nvidia-{index}",
                "canonical_model_id": f"nvidia-{index}",
                "api_format": "chat",
                "p50_latency_ms": 100 + index * 10,
                "health": "available",
                "source": "runtime_channel_live_probe",
                "traffic_control": traffic_control,
            }
        )
        for index in range(2)
    ]

    route_plan = build_route_plan(
        FusionRequest(
            model="axio-terra",
            prompt="Analyze a difficult scientific constraint and verify the conclusion.",
        ),
        profiles,
    )
    local_plan = route_plan["budget"]["local_consensus_plan"]

    assert local_plan["provider_serialization_detected"] is True
    assert local_plan["provider_parallelism_constraint"] is True
    assert local_plan["provider_diversity_required"] is False
    assert local_plan["feasible"] is False
    assert local_plan["reason"] == "no_local_consensus_panel_meets_latency_and_quality_guard"
    assert route_plan["fusion_admission"]["activated"] is False


def test_local_consensus_runtime_uses_only_parallel_experts_and_marks_complete():
    class ExpertOnlyClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            del request, prompt, system, timeout
            self.calls.append(profile.profile_id)
            return json.dumps(
                {
                    "answer": f"candidate from {profile.model}",
                    "evidence": [{"claim": "bounded fixture", "source": "unit"}],
                    "assumptions": [],
                    "uncertainties": [],
                    "confidence": 0.9,
                }
            )

    profiles = _local_consensus_fixture_profiles()
    client = ExpertOnlyClient()
    request = FusionRequest(
        model="axio-pro",
        prompt="Analyze a high-risk production workflow and prove the routing constraints are logically consistent.",
    )
    engine = FusionEngine(profiles, client=client, cache_enabled=True)
    response = engine.complete(request, live=True)
    calls_after_origin = len(client.calls)
    cached = engine.complete(request, live=True)
    outcome = response.trace["runtime_fusion_stage_outcome"]
    safe = safe_execution_trace(response, tenant_key="local-consensus-regression")
    safe_cached = safe_execution_trace(
        cached,
        tenant_key="local-consensus-regression",
    )
    public = render_response(
        response,
        api_format="gemini",
    )

    assert len(client.calls) == 3
    assert response.trace["judge_provider_call_count"] == 0
    assert response.trace["synthesis_provider_call_count"] == 0
    assert outcome["fusion_finalization_mode"] == "local_consensus"
    assert outcome["execution_mode"] == "complete_fusion_local_consensus"
    assert outcome["local_consensus_finalized"] is True
    assert outcome["complete_admitted_fusion_finalized"] is True
    assert outcome["runtime_degraded"] is False
    assert safe["runtime_fusion_stage_outcome"]["local_consensus_finalized"] is True
    assert public["metadata"]["fusion_trace_summary"]["fusion_finalization_mode"] == "local_consensus"
    assert public["metadata"]["fusion_trace_summary"]["local_consensus_finalized"] is True
    assert calls_after_origin == 3
    assert len(client.calls) == calls_after_origin
    assert cached.text == response.text
    assert cached.trace["cache_hit"] is True
    assert cached.trace["cache_replay"]["process_executed_this_request"] is False
    assert cached.trace["cache_origin_completion"]["completion_kind"] == "complete_fusion_text"
    assert cached.trace["cache_origin_completion"]["complete_admitted_fusion_finalized"] is True
    assert safe_cached["cache_replay"]["replayed"] is True
    assert safe_cached["cache_origin_completion"]["runtime_degraded"] is False


def test_local_consensus_never_overrides_explicit_call_latency_or_cost_caps():
    profiles = _local_consensus_fixture_profiles()
    prompt = "Analyze a high-risk production workflow and prove the routing constraints are logically consistent."

    call_capped = canonicalize_payload(
        {
            "model": "axio-pro",
            "max_total_model_calls": 3,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    call_plan = build_route_plan(call_capped, profiles)
    assert call_plan["budget"]["caller_max_total_model_calls_explicit"] is True
    assert call_plan["budget"]["max_total_model_calls"] == 3
    assert call_plan["budget"]["fusion_finalization_mode"] == "direct"
    assert call_plan["fusion_admission"]["activated"] is False

    latency_capped = canonicalize_payload(
        {
            "model": "axio-terra",
            "max_latency_ms": 150,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    latency_plan = build_route_plan(latency_capped, profiles)
    assert latency_plan["budget"]["max_latency_ms"] == 150
    assert latency_plan["budget"]["fusion_finalization_mode"] == "direct"
    assert latency_plan["fusion_admission"]["activated"] is False

    cost_profiles = _local_consensus_fixture_profiles(cost=1.0)
    cost_capped = canonicalize_payload(
        {
            "model": "axio-terra",
            "max_cost_usd": 0.000001,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    cost_plan = build_route_plan(cost_capped, cost_profiles)
    assert cost_plan["budget"]["max_cost_usd"] == 0.000001
    assert cost_plan["budget"]["fusion_finalization_mode"] == "direct"
    assert cost_plan["fusion_admission"]["activated"] is False


def test_latency_optimization_replaces_slow_qualified_mandatory_stages():
    primary = _latency_profile("primary", 1_000)
    independent = _latency_profile("independent", 1_000)
    slow_judge = _latency_profile("slow-judge", 6_000, critique=0.96, structured=0.96)
    slow_synthesizer = _latency_profile("slow-synthesizer", 6_000, critique=0.90, structured=0.96)
    fast_stage = _latency_profile("fast-stage", 500, critique=0.82, structured=0.86)

    judge, synthesizer, receipt = _latency_optimize_stage_profiles(
        selected=[primary, independent, slow_judge, slow_synthesizer, fast_stage],
        primary_profile=primary,
        expert_roles=[
            {"role": "primary_solver", "model": primary.safe_dict()},
            {"role": "independent_solver", "model": independent.safe_dict()},
        ],
        judge=slow_judge,
        synthesizer=slow_synthesizer,
        analysis={"domains": ["daily_work"]},
        budget={"max_parallel_experts": 2, "max_latency_ms": 30_000},
    )

    assert receipt["applied"] is True
    assert receipt["reason"] == "faster_qualified_stage_pair_meets_latency_guard"
    assert judge.profile_id == fast_stage.profile_id
    assert synthesizer.profile_id == fast_stage.profile_id
    assert receipt["estimated_latency_multiplier_vs_direct"] <= 3.0


def test_latency_optimization_uses_the_direct_route_baseline_not_fusion_primary():
    primary = _latency_profile("primary", 2_000)
    independent = _latency_profile("independent", 2_000)
    slow_judge = _latency_profile("slow-judge", 4_000, critique=0.96, structured=0.96)
    slow_synthesizer = _latency_profile("slow-synthesizer", 4_000, critique=0.90, structured=0.96)
    fast_stage = _latency_profile("fast-stage", 500, critique=0.82, structured=0.86)
    direct_baseline = _latency_profile("direct-baseline", 1_000, critique=0.20, structured=0.20)

    judge, synthesizer, receipt = _latency_optimize_stage_profiles(
        selected=[primary, independent, slow_judge, slow_synthesizer, fast_stage, direct_baseline],
        primary_profile=primary,
        direct_baseline_profile=direct_baseline,
        expert_roles=[
            {"role": "primary_solver", "model": primary.safe_dict()},
            {"role": "independent_solver", "model": independent.safe_dict()},
        ],
        judge=slow_judge,
        synthesizer=slow_synthesizer,
        analysis={"domains": ["daily_work"]},
        budget={"max_parallel_experts": 2, "max_latency_ms": 30_000},
    )

    assert receipt["applied"] is True
    assert judge.profile_id == fast_stage.profile_id
    assert synthesizer.profile_id == fast_stage.profile_id
    assert receipt["direct_profile_latency_ms"] == 1_000.0
    assert receipt["estimated_latency_multiplier_vs_direct"] <= 3.0


def test_expert_latency_optimization_replaces_a_slow_role_within_quality_tolerance():
    primary = _latency_profile("primary", 7_000, critique=0.94, structured=0.94)
    independent = _latency_profile("independent", 1_000, critique=0.64, structured=0.64)
    critic = _latency_profile("critic", 3_000, critique=0.84, structured=0.84)
    direct = _latency_profile("direct", 3_000, critique=0.80, structured=0.80)
    roles = [
        {"role": "primary_solver", "model": primary.safe_dict()},
        {"role": "independent_solver", "model": independent.safe_dict()},
        {"role": "critic", "model": critic.safe_dict()},
    ]

    optimized, receipt = _latency_optimize_expert_roles(
        roles=roles,
        selected=[primary, independent, critic, direct],
        direct_baseline_profile=direct,
        analysis={"domains": ["daily_work"]},
        budget={"max_parallel_experts": 3, "max_latency_ms": 15_000},
    )

    optimized_primary = next(row for row in optimized if row["role"] == "primary_solver")
    assert receipt["applied"] is True
    assert receipt["replaced_role_count"] >= 1
    assert optimized_primary["model"]["p50_latency_ms"] < primary.p50_latency_ms
    assert receipt["optimized_latency_multiplier_vs_direct"] <= 2.5
    assert optimized_primary["expert_latency_optimization"]["applied"] is True


def test_latency_optimization_rejects_a_faster_pair_that_still_breaks_three_x_guard():
    primary = _latency_profile("primary", 1_000, critique=0.20, structured=0.20)
    independent = _latency_profile("independent", 1_000, critique=0.20, structured=0.20)
    slow_judge = _latency_profile("slow-judge", 6_000, critique=0.96, structured=0.96)
    slow_synthesizer = _latency_profile("slow-synthesizer", 6_000, critique=0.90, structured=0.96)
    still_too_slow = _latency_profile("still-too-slow", 2_000, critique=0.82, structured=0.86)

    judge, synthesizer, receipt = _latency_optimize_stage_profiles(
        selected=[primary, independent, slow_judge, slow_synthesizer, still_too_slow],
        primary_profile=primary,
        expert_roles=[
            {"role": "primary_solver", "model": primary.safe_dict()},
            {"role": "independent_solver", "model": independent.safe_dict()},
        ],
        judge=slow_judge,
        synthesizer=slow_synthesizer,
        analysis={"domains": ["daily_work"]},
        budget={"max_parallel_experts": 2, "max_latency_ms": 30_000},
    )

    assert receipt["applied"] is False
    assert receipt["reason"] == "no_faster_stage_pair_meets_latency_guard"
    assert judge.profile_id == slow_judge.profile_id
    assert synthesizer.profile_id == slow_synthesizer.profile_id
    assert receipt["estimated_latency_multiplier_vs_direct"] > 3.0


def test_latency_constrained_panel_search_preserves_direct_baseline_and_restores_pro_fusion():
    def profile(provider: str, model: str, latency: int, capability: float):
        return normalize_profile(
            {
                "provider": provider,
                "model": model,
                "canonical_model_id": model,
                "api_format": "chat",
                "p50_latency_ms": latency,
                "capabilities": {
                    "science_knowledge": capability,
                    "multilingual": capability,
                    "code": capability,
                    "math": capability,
                    "logic": capability,
                    "daily_work": capability,
                    "agentic_tool_calling": capability,
                    "structured_output": capability,
                    "critique": capability,
                    "long_context": capability,
                },
            }
        )

    anchor = profile("fast-channel", "anchor-model", 100, 0.95)
    slow_a = profile("slow-channel-a", "slow-model-a", 1_000, 0.99)
    slow_b = profile("slow-channel-b", "slow-model-b", 1_100, 0.99)
    slow_c = profile("slow-channel-c", "slow-model-c", 1_200, 0.99)
    fast_a = profile("fast-channel", "fast-model-a", 120, 0.86)
    fast_b = profile("fast-channel", "fast-model-b", 130, 0.86)
    fast_c = profile("fast-channel", "fast-model-c", 140, 0.86)
    all_profiles = [anchor, slow_a, slow_b, slow_c, fast_a, fast_b, fast_c]
    request = FusionRequest(
        model="axio-pro",
        prompt="Solve a complex scientific and code workflow, identify contradictions, verify claims, and define a tool plan.",
        task_type="latency_constrained_panel_test",
    )
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    role_blueprint = _role_blueprint(request, analysis, budget)
    initial_panel = [anchor, slow_a, slow_b, slow_c]
    initial_roles = _role_assignments(
        request,
        analysis,
        initial_panel,
        True,
        role_blueprint,
        budget=budget,
        latency_baseline_profile=anchor,
    )
    optimized_panel, optimized_roles, receipt = _latency_constrained_fusion_panel(
        request=request,
        analysis=analysis,
        budget=budget,
        scored=[(candidate, 0.9 if candidate in initial_panel else 0.7) for candidate in all_profiles],
        selected=initial_panel,
        role_blueprint=role_blueprint,
        direct_profile=anchor,
        initial_roles=initial_roles,
    )

    # With a 100ms direct baseline, even the fastest legal panel needs a
    # 120ms expert wave plus two serial mandatory stages.  The old fixture
    # passed only because expert latency optimization could reuse the Primary
    # profile as Independent.  Independent evidence is now identity-safe, so
    # the router correctly declines to claim a provider Fusion shape here.
    assert receipt["applied"] is False
    assert receipt["initial_latency_multiplier_vs_direct"] > 3.0
    assert receipt["optimized_latency_multiplier_vs_direct"] > 3.0
    assert receipt["reason"] == "no_panel_meets_latency_guard"
    assert optimized_panel == initial_panel
    assert len({candidate.canonical_identity for candidate in optimized_panel}) == len(optimized_panel)
    assert [row["role"] for row in optimized_roles] == [
        "primary_solver",
        "independent_solver",
        "critic",
        "judge",
        "synthesizer",
    ]


def test_latency_constrained_panel_prefers_fast_quality_equivalent_panel_before_provider_count():
    def profile(provider: str, model: str, latency: int):
        return normalize_profile(
            {
                "provider": provider,
                "model": model,
                "canonical_model_id": model,
                "api_format": "chat",
                "p50_latency_ms": latency,
                "capabilities": {
                    "science_knowledge": 0.95,
                    "multilingual": 0.92,
                    "code": 0.94,
                    "math": 0.94,
                    "logic": 0.95,
                    "daily_work": 0.94,
                    "agentic_tool_calling": 0.90,
                    "structured_output": 0.94,
                    "critique": 0.95,
                    "long_context": 0.90,
                },
            }
        )

    anchor = profile("anchor-channel", "anchor", 2_000)
    slow_a = profile("slow-channel-a", "slow-a", 2_200)
    slow_b = profile("slow-channel-b", "slow-b", 2_400)
    fast_a = profile("fast-channel", "fast-a", 700)
    fast_b = profile("fast-channel", "fast-b", 750)
    all_profiles = [anchor, slow_a, slow_b, fast_a, fast_b]
    request = FusionRequest(
        model="axio-pro",
        prompt="Solve a complex scientific and code workflow with independent verification and contradictions.",
        task_type="latency_panel_objective_test",
    )
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    role_blueprint = _role_blueprint(request, analysis, budget)
    initial_panel = [anchor, slow_a, slow_b]
    initial_roles = _role_assignments(
        request,
        analysis,
        initial_panel,
        True,
        role_blueprint,
        budget=budget,
        latency_baseline_profile=anchor,
    )

    optimized_panel, _, receipt = _latency_constrained_fusion_panel(
        request=request,
        analysis=analysis,
        budget=budget,
        scored=[(candidate, 0.9) for candidate in all_profiles],
        selected=initial_panel,
        role_blueprint=role_blueprint,
        direct_profile=anchor,
        initial_roles=initial_roles,
    )

    assert receipt["applied"] is True
    assert receipt["optimized_latency_multiplier_vs_direct"] < receipt["initial_latency_multiplier_vs_direct"]
    assert receipt["provider_diversity_relaxed_for_latency"] is True
    assert {candidate.provider for candidate in optimized_panel} == {"anchor-channel", "fast-channel"}


def test_screened_domain_specialist_completes_two_profile_pro_route_without_relabeling():
    primary = _screened_profile(
        "primary",
        allowed_roles=("primary_solver", "judge", "synthesizer"),
        disallowed_roles=("independent_solver", "critic", "domain_specialist"),
    )
    specialist = _screened_profile(
        "specialist",
        allowed_roles=("domain_specialist",),
        disallowed_roles=("primary_solver", "independent_solver", "critic", "judge", "synthesizer"),
    )

    route_plan = build_route_plan(
        FusionRequest(
            model="axio-pro",
            prompt="Solve this task and use a narrow domain review to check the result.",
        ),
        [primary, specialist],
    )

    roles = [row["role"] for row in route_plan["roles"]]
    assert roles == ["primary_solver", "domain_specialist", "judge", "synthesizer"]
    assert "independent_solver" not in roles
    assert route_plan["fusion_admission"]["activated"] is True
    assert route_plan["role_gate"]["provider_fusion"]["missing_roles"] == []
    assert route_plan["role_gate"]["provider_fusion"]["assigned_roles"] == [
        "domain_specialist",
        "judge",
        "primary_solver",
        "synthesizer",
    ]
    assert route_plan["model_selection_policy"]["canonical_duplicate_count_selected"] == 0
    assert route_plan["fusion_admission"]["latency_multiplier_vs_single_model"] <= 3.0


def test_underfilled_panel_search_adds_screened_domain_specialist_as_second_evidence():
    primary = _screened_profile(
        "underfilled-primary",
        allowed_roles=("primary_solver", "judge", "synthesizer"),
        disallowed_roles=("independent_solver", "critic", "domain_specialist"),
    )
    specialist = _screened_profile(
        "underfilled-specialist",
        allowed_roles=("domain_specialist",),
        disallowed_roles=("primary_solver", "independent_solver", "critic", "judge", "synthesizer"),
    )
    request = FusionRequest(
        model="axio-pro",
        prompt="Produce a focused answer with a separate domain-specific verification pass.",
    )
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    scored = [(primary, 0.95), (specialist, 0.70)]
    role_blueprint = _augment_pro_role_blueprint_for_screened_specialist(
        request,
        analysis,
        budget,
        scored,
        _role_blueprint(request, analysis, budget),
    )
    initial_roles = _role_assignments(
        request,
        analysis,
        [primary],
        True,
        role_blueprint,
        budget=budget,
        latency_baseline_profile=primary,
    )

    optimized_panel, optimized_roles, receipt = _latency_constrained_fusion_panel(
        request=request,
        analysis=analysis,
        budget=budget,
        scored=scored,
        selected=[primary],
        role_blueprint=role_blueprint,
        direct_profile=primary,
        initial_roles=initial_roles,
    )

    assert receipt["candidate_panel_evaluation_count"] >= 1
    assert receipt["applied"] is True
    assert len(optimized_panel) == 2
    assert len({profile.canonical_identity for profile in optimized_panel}) == 2
    assert [row["role"] for row in optimized_roles] == [
        "primary_solver",
        "domain_specialist",
        "judge",
        "synthesizer",
    ]
    assert "independent_solver" not in {row["role"] for row in optimized_roles}
    assert receipt["optimized_latency_multiplier_vs_direct"] <= 3.0


def test_stage_roles_use_unassigned_profiles_before_reusing_experts():
    profiles = [_profile(index, critique=0.72 + index * 0.03) for index in range(6)]
    request = FusionRequest(
        model="axio-pro",
        prompt=(
            "Analyze and review a complex medical legal code and mathematical policy "
            "workflow with evidence, contradictions, and tool planning."
        ),
    )

    route_plan = build_route_plan(request, profiles)
    assert route_plan["fusion_admission"]["activated"] is True
    roles = {row["role"]: row for row in route_plan["roles"]}
    expert_roles = {"primary_solver", "independent_solver", "critic", "domain_specialist"}
    expert_profile_ids = {
        roles[role]["model"]["profile_id"]
        for role in expert_roles
        if role in roles
    }

    judge = roles["judge"]
    synthesizer = roles["synthesizer"]
    assert judge["model"]["profile_id"] not in expert_profile_ids
    assert synthesizer["model"]["profile_id"] not in expert_profile_ids
    assert judge["model"]["profile_id"] != synthesizer["model"]["profile_id"]
    assert judge["stage_profile_reuse"]["judge_reuses_expert_profile"] is False
    assert judge["stage_profile_reuse"]["synthesizer_reuses_expert_profile"] is False


def test_stage_only_pool_can_supply_control_stages_without_counting_as_evidence():
    primary = _screened_profile(
        "stage-pool-primary",
        allowed_roles=("primary_solver", "independent_solver"),
        disallowed_roles=("judge", "synthesizer"),
    )
    independent = _screened_profile(
        "stage-pool-independent",
        allowed_roles=("primary_solver", "independent_solver"),
        disallowed_roles=("judge", "synthesizer"),
    )
    judge = _screened_profile(
        "stage-pool-judge",
        allowed_roles=("judge",),
        disallowed_roles=("primary_solver", "independent_solver", "synthesizer"),
    )
    synthesizer = _screened_profile(
        "stage-pool-synthesizer",
        allowed_roles=("synthesizer",),
        disallowed_roles=("primary_solver", "independent_solver", "judge"),
    )
    request = FusionRequest(
        model="axio-terra",
        prompt="Analyze a complex scientific workflow and verify contradictions.",
    )
    analysis = analyze_request(request)
    budget = _budget_for_request(request, analysis)
    blueprint = _role_blueprint(request, analysis, budget)

    roles = _role_assignments(
        request,
        analysis,
        [primary, independent],
        True,
        blueprint,
        budget=budget,
        latency_baseline_profile=primary,
        stage_profile_pool=[primary, independent, judge, synthesizer],
    )

    expert_profile_ids = {
        row["model"]["profile_id"]
        for row in roles
        if row["role"] in {"primary_solver", "independent_solver", "critic", "domain_specialist"}
    }
    judge_role = next(row for row in roles if row["role"] == "judge")
    synthesizer_role = next(row for row in roles if row["role"] == "synthesizer")
    stage_receipt = judge_role["stage_profile_reuse"]

    assert judge_role["stage_only_profile"] is True
    assert synthesizer_role["stage_only_profile"] is True
    assert judge_role["model"]["profile_id"] not in expert_profile_ids
    assert synthesizer_role["model"]["profile_id"] not in expert_profile_ids
    assert stage_receipt["stage_only_profile_pool_enabled"] is True
    assert stage_receipt["stage_only_profiles_count"] == 2
    assert stage_receipt["stage_only_profiles_count_as_independent_evidence"] is False
    assert stage_receipt["eligible_stage_only_judge_profile_count"] == 1
    assert stage_receipt["eligible_stage_only_synthesizer_profile_count"] == 1

    route_plan = build_route_plan(
        canonicalize_payload(
            {
                "model": "axio-pro",
                "max_models": 2,
                "messages": [
                    {
                        "role": "user",
                        "content": request.prompt,
                    }
                ],
            }
        ),
        [primary, independent, judge, synthesizer],
    )
    route_expert_ids = {
        row["model"]["profile_id"]
        for row in route_plan["roles"]
        if row["role"] in {"primary_solver", "independent_solver", "critic", "domain_specialist"}
    }
    route_judge = next(row for row in route_plan["roles"] if row["role"] == "judge")
    route_synthesizer = next(row for row in route_plan["roles"] if row["role"] == "synthesizer")
    assert len(route_plan["selected_models"]) == 2
    assert route_judge["stage_only_profile"] is True
    assert route_synthesizer["stage_only_profile"] is True
    assert route_judge["model"]["profile_id"] not in route_expert_ids
    assert route_synthesizer["model"]["profile_id"] not in route_expert_ids


def test_provider_judge_cannot_clear_local_hard_evidence_blocker():
    profiles = [_profile(0), _profile(1, critique=0.98, structured=0.98)]
    request = FusionRequest(
        model="axio-pro",
        prompt="Review this factual medical workflow and identify unsupported claims.",
    )
    route_plan = build_route_plan(request, profiles)
    candidates = [
        CandidateResult(
            candidate_id="primary_solver",
            role="primary_solver",
            profile_id=profiles[0].profile_id,
            provider=profiles[0].provider,
            model=profiles[0].model,
            answer="unsupported candidate answer",
            confidence=0.88,
        ),
        CandidateResult(
            candidate_id="independent_solver",
            role="independent_solver",
            profile_id=profiles[1].profile_id,
            provider=profiles[1].provider,
            model=profiles[1].model,
            answer="another unsupported candidate answer",
            confidence=0.87,
        ),
    ]
    local = _local_judge_candidates(candidates, route_plan=route_plan)
    assert "no_candidate_returned_explicit_evidence" in local["missing_coverage"]

    normalized = _normalize_provider_judge_result(
        {
            "ranked_candidates": [
                {"candidate_id": "primary_solver", "score": 0.99},
                {"candidate_id": "independent_solver", "score": 0.98},
            ],
            "consensus": [],
            "contradictions": [],
            "missing_coverage": [],
            "collective_blind_spots": [],
            "follow_up_tasks": [],
            "ready_for_synthesis": True,
        },
        candidates=candidates,
        local=local,
        profile=profiles[1],
        output=json.dumps({"ready_for_synthesis": True}),
    )

    assert normalized["ready_for_synthesis"] is False
    assert normalized["provider_ready_overridden_by_local_guard"] is True
    assert normalized["local_hard_blockers_preserved"] is True
    assert "no_candidate_returned_explicit_evidence" in normalized["missing_coverage"]


def test_generic_four_protocol_config_preserves_canonical_model_identity(monkeypatch):
    provider_configs = {
        "providers": [
            {
                "provider": "fixture-chat",
                "apiFormat": "chat/completions",
                "baseUrlEnv": "FIXTURE_CHAT_BASE_URL",
                "apiKeyEnv": "FIXTURE_CHAT_API_KEY",
                "models": [
                    {
                        "model": "fixture-chat-alias",
                        "canonicalModelId": "fixture-model-chat-v1",
                    }
                ],
            },
            {
                "provider": "fixture-responses",
                "api_format": "responses",
                "base_url_env": "FIXTURE_RESPONSES_BASE_URL",
                "api_key_env": "FIXTURE_RESPONSES_API_KEY",
                "models": [
                    {
                        "model": "fixture-responses-alias",
                        "canonical_model_id": "fixture-model-responses-v1",
                    }
                ],
            },
            {
                "provider": "fixture-anthropic",
                "api_format": "anthropic",
                "base_url_env": "FIXTURE_ANTHROPIC_BASE_URL",
                "api_key_env": "FIXTURE_ANTHROPIC_API_KEY",
                "models": [
                    {
                        "model": "fixture-anthropic-alias",
                        "canonical_model_id": "fixture-model-anthropic-v1",
                    }
                ],
            },
            {
                "provider": "fixture-gemini",
                "api_format": "gemini",
                "base_url_env": "FIXTURE_GEMINI_BASE_URL",
                "api_key_env": "FIXTURE_GEMINI_API_KEY",
                "models": [
                    {
                        "model": "fixture-gemini-alias",
                        "canonical_model_id": "fixture-model-gemini-v1",
                    }
                ],
            },
        ]
    }
    monkeypatch.delenv("AXIO_FUSION_REGISTRY_PATH", raising=False)
    monkeypatch.delenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("AXIO_FUSION_PROVIDERS_JSON", raising=False)
    monkeypatch.setenv("AXIO_FUSION_PROVIDER_CONFIGS", json.dumps(provider_configs))

    profiles = load_registry()

    assert {profile.api_format for profile in profiles} == {
        "chat",
        "responses",
        "anthropic",
        "gemini",
    }
    assert {
        profile.canonical_model_id for profile in profiles
    } == {
        "fixture-model-chat-v1",
        "fixture-model-responses-v1",
        "fixture-model-anthropic-v1",
        "fixture-model-gemini-v1",
    }
    assert all(profile.canonical_identity_sha256 for profile in profiles)


def test_file_backed_current_channel_configuration_is_private_and_protocol_agnostic(
    monkeypatch,
    tmp_path,
):
    provider_config_file = tmp_path / "fixture_provider_channels.private.json"
    provider_config_file.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "provider": "fixture-responses-channel-a",
                        "apiFormat": "responses",
                        "baseUrlEnv": "FIXTURE_RESPONSES_A_BASE_URL",
                        "apiKeyEnv": "FIXTURE_RESPONSES_A_API_KEY",
                        "models": [
                            {
                                "model": "fixture-responses-a-alias",
                                "canonicalModelId": "fixture-shared-model-v1",
                            }
                        ],
                    },
                    {
                        "provider": "fixture-chat-channel",
                        "api_format": "chat/completions",
                        "base_url_env": "FIXTURE_CHAT_BASE_URL",
                        "api_key_env": "FIXTURE_CHAT_API_KEYS",
                        "models": ["fixture-chat-alias"],
                    },
                    {
                        "provider": "fixture-responses-channel-b",
                        "api_format": "responses",
                        "base_url_env": "FIXTURE_RESPONSES_B_BASE_URL",
                        "api_key_env": "FIXTURE_RESPONSES_B_API_KEY",
                        "models": [
                            {
                                "model": "fixture-responses-b-alias",
                                "canonical_model_id": "fixture-shared-model-v1",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AXIO_FUSION_REGISTRY_PATH", raising=False)
    monkeypatch.delenv("AXIO_FUSION_PROVIDER_CONFIGS", raising=False)
    monkeypatch.delenv("AXIO_FUSION_PROVIDERS_JSON", raising=False)
    monkeypatch.setenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", str(provider_config_file))
    monkeypatch.setenv("FIXTURE_RESPONSES_A_BASE_URL", "https://fixture-responses-a.invalid/v1")
    monkeypatch.setenv("FIXTURE_RESPONSES_A_API_KEY", "fixture-responses-a-key")
    monkeypatch.setenv("FIXTURE_CHAT_BASE_URL", "https://fixture-chat.invalid/v1")
    monkeypatch.setenv("FIXTURE_CHAT_API_KEYS", "fixture-chat-key-a,fixture-chat-key-b")
    monkeypatch.setenv("FIXTURE_RESPONSES_B_BASE_URL", "https://fixture-responses-b.invalid/v1")
    monkeypatch.setenv("FIXTURE_RESPONSES_B_API_KEY", "fixture-responses-b-key")

    profiles = load_registry()
    source_summary = provider_configuration_source_summary()
    readiness = _fusion_provider_env_readiness()
    serialized_summary = json.dumps(
        {"source_summary": source_summary, "readiness": readiness},
        ensure_ascii=False,
    )

    assert len(profiles) == 3
    assert [profile.api_format for profile in profiles] == ["responses", "chat", "responses"]
    assert profiles[0].canonical_identity == profiles[2].canonical_identity
    assert source_summary["config_file_present"] is True
    assert source_summary["valid_config_file_count"] == 1
    assert source_summary["provider_config_count"] == 3
    assert readiness["custom_provider_seed_count"] == 3
    assert readiness["credentialed_provider_count"] == 3
    assert readiness["provider_config_env"]["config_file_present"] is True
    assert "fixture-responses-channel-a" not in serialized_summary
    assert "fixture-responses-a-alias" not in serialized_summary
    assert "FIXTURE_RESPONSES_A_BASE_URL" not in serialized_summary
    assert "https://fixture-responses-a.invalid" not in serialized_summary
    assert "fixture-responses-a-key" not in serialized_summary
    assert str(provider_config_file) not in serialized_summary


def test_provider_config_rejects_literal_transport_values(monkeypatch):
    provider_configs = {
        "providers": [
            {
                "provider": "fixture-invalid-config",
                "api_format": "responses",
                "base_url_env": "https://fixture.invalid/v1",
                "api_key_env": "fixture-key-value",
                "models": ["fixture-model"],
            }
        ]
    }
    monkeypatch.delenv("AXIO_FUSION_REGISTRY_PATH", raising=False)
    monkeypatch.delenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("AXIO_FUSION_PROVIDERS_JSON", raising=False)
    monkeypatch.setenv("AXIO_FUSION_PROVIDER_CONFIGS", json.dumps(provider_configs))

    assert all(profile.provider != "fixture-invalid-config" for profile in load_registry())
    summary = provider_configuration_source_summary()
    assert summary["valid_config_env_count"] == 1


def _canonical_replica_profiles():
    capabilities = {
        "daily_work": 1.0,
        "structured_output": 1.0,
        "critique": 0.9,
        "long_context": 0.9,
    }
    return [
        normalize_profile(
            {
                "provider": "fixture-replica-fast-a",
                "model": "fixture-channel-a-alias",
                "canonical_model_id": "fixture-real-model-v1",
                "api_format": "chat",
                "p50_latency_ms": 100,
                "recent_success_rate": 0.98,
                "capabilities": capabilities,
            }
        ),
        normalize_profile(
            {
                "provider": "fixture-replica-fast-b",
                "model": "fixture-channel-b-alias",
                "canonical_model_id": "FIXTURE-real-model-v1",
                "api_format": "responses",
                "p50_latency_ms": 110,
                "recent_success_rate": 0.97,
                "capabilities": capabilities,
            }
        ),
        normalize_profile(
            {
                "provider": "fixture-replica-slow",
                "model": "fixture-channel-slow-alias",
                "canonical_model_id": "fixture-real-model-v1",
                "api_format": "anthropic",
                "p50_latency_ms": 550,
                "recent_success_rate": 0.98,
                "capabilities": capabilities,
            }
        ),
        normalize_profile(
            {
                "provider": "fixture-other-model",
                "model": "fixture-other-model-alias",
                "canonical_model_id": "fixture-other-model-v1",
                "api_format": "gemini",
                "p50_latency_ms": 130,
                "recent_success_rate": 0.99,
                "capabilities": {
                    **capabilities,
                    "daily_work": 0.35,
                    "structured_output": 0.35,
                    "critique": 0.35,
                    "long_context": 0.35,
                },
            }
        ),
    ]


def test_canonical_replicas_rotate_and_do_not_count_as_independent_panel_models():
    class SuccessClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            del request, prompt, system, timeout
            self.calls.append(profile.profile_id)
            return json.dumps({"answer": "fixture answer", "confidence": 0.8})

    profiles = _canonical_replica_profiles()
    client = SuccessClient()
    engine = FusionEngine(profiles, client=client, cache_enabled=False)
    request = canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": [{"role": "user", "content": "fixture replica task"}],
        }
    )
    role = {"role": "primary_solver", "model": profiles[0].safe_dict()}

    candidates = [engine._run_role(request, role) for _ in range(4)]
    selected_replica_ids = {
        profiles[0].profile_id,
        profiles[1].profile_id,
    }

    assert client.calls == [
        profiles[0].profile_id,
        profiles[1].profile_id,
        profiles[0].profile_id,
        profiles[1].profile_id,
    ]
    assert set(client.calls) == selected_replica_ids
    assert all(candidate.canonical_identity == profiles[0].canonical_identity for candidate in candidates)
    assert len(_candidates_for_fusion_finalization(candidates)) == 1

    route_plan = build_route_plan(
        FusionRequest(model="axio-pro", prompt="review this fixture workflow"),
        profiles,
    )
    selected = route_plan["selected_models"]
    selected_canonical_hashes = {
        row["runtime_canonical_identity_sha256"] for row in selected
    }
    policy = route_plan["model_selection_policy"]

    assert len(selected) == len(selected_canonical_hashes)
    assert policy["canonical_duplicate_count_selected"] == 0
    assert policy["canonical_model_panel_deduplication_satisfied"] is True
    assert route_plan["provider_routing_policy"]["canonical_replica_group_count"] == 2


def test_fast_direct_cascade_preserves_raw_prompt_and_system_without_fusion_packet():
    class DirectClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            self.calls.append(
                {
                    "profile_id": profile.profile_id,
                    "prompt": prompt,
                    "system": system,
                    "timeout": timeout,
                    "request_prompt": request.prompt,
                }
            )
            return json.dumps({"answer": "direct answer", "confidence": 0.9})

    profile = normalize_profile(
        {
            "provider": "direct-fixture",
            "model": "direct-model",
            "api_format": "chat",
            "p50_latency_ms": 250,
            "capabilities": {"daily_work": 0.9, "structured_output": 0.9, "critique": 0.8},
        }
    )
    client = DirectClient()
    request = FusionRequest(
        model="axio-fast",
        prompt="Keep this exact user task.",
        system="Keep this exact system message.",
    )

    response = FusionEngine([profile], client=client, cache_enabled=False).complete(
        request,
        live=True,
    )

    assert response.route_plan["strategy"] == "fast_direct_cascade"
    assert response.text == "direct answer"
    assert len(client.calls) == 1
    assert client.calls[0]["prompt"] == request.prompt
    assert client.calls[0]["request_prompt"] == request.prompt
    assert client.calls[0]["system"] == request.system
    assert "Axio Fusion routing context" not in client.calls[0]["prompt"]


def test_implicit_fast_deadline_adapts_to_observed_direct_profile_latency():
    profile = normalize_profile(
        {
            "provider": "slow-gateway-fixture",
            "model": "slow-direct-model",
            "api_format": "responses",
            "p50_latency_ms": 4_000,
            "p95_latency_ms": 4_500,
        }
    )
    adapted = _budget_with_direct_profile_deadline(
        FusionRequest(model="axio-fast", prompt="task"),
        {"max_latency_ms": 2_500},
        profile,
    )

    assert adapted["max_latency_ms"] == 11_750
    assert adapted["direct_profile_deadline_adaptation"]["applied"] is True
    assert adapted["direct_profile_deadline_adaptation"]["observed_latency_ms"] == 4_500.0


def test_canonical_replica_failover_precedes_cross_model_fallback_and_stage_failover_is_bounded():
    class FailoverClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            del request, prompt, system, timeout
            self.calls.append(profile.profile_id)
            if profile.profile_id == profiles[0].profile_id:
                raise RuntimeError("fixture primary channel unavailable")
            return json.dumps({"answer": "fixture fallback answer", "confidence": 0.84})

    profiles = _canonical_replica_profiles()
    client = FailoverClient()
    request = canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": [{"role": "user", "content": "fixture failover task"}],
        }
    )
    engine = FusionEngine(profiles, client=client, cache_enabled=False)
    response = engine.complete(request, live=True)
    receipt = safe_execution_trace(response, tenant_key="fixture-canonical-replica")
    serialized_receipt = json.dumps(receipt, ensure_ascii=False)

    assert response.text == "fixture fallback answer"
    assert client.calls == [profiles[0].profile_id, profiles[1].profile_id]
    assert profiles[3].profile_id not in client.calls
    assert response.candidates[-1].canonical_identity == profiles[0].canonical_identity
    assert receipt["provider_routing_policy"][
        "same_canonical_model_failover_precedes_cross_model_fallback"
    ] is True
    assert receipt["candidate_outputs"][-1]["runtime_canonical_identity_sha256"] == sha256_text(
        profiles[0].canonical_identity
    )
    assert profiles[0].provider not in serialized_receipt
    assert profiles[1].provider not in serialized_receipt
    assert profiles[0].model not in serialized_receipt
    assert profiles[1].model not in serialized_receipt

    stage_client = FailoverClient()
    stage_engine = FusionEngine(profiles, client=stage_client, cache_enabled=False)
    stage_route_plan = build_route_plan(
        FusionRequest(model="axio-pro", prompt="fixture stage failover"),
        profiles,
    )
    stage_request = FusionRequest(model="axio-pro", prompt="fixture stage failover")
    output, selected_profile, stage_receipt, stage_attempt_count = (
        stage_engine._complete_stage_with_replica_failover(
            profiles[0],
            stage_request,
            route_plan=stage_route_plan,
            kind="judge",
            role_name="judge",
            prompt="fixture judge prompt",
            system="fixture judge system",
            call_budget=None,
            cost_budget=None,
            deadline_budget=None,
            prompt_budget=None,
        )
    )

    assert output
    assert selected_profile.profile_id == profiles[1].profile_id
    assert stage_client.calls == [profiles[0].profile_id, profiles[1].profile_id]
    assert stage_attempt_count == 2
    assert stage_receipt["stage_failure_count"] == 1
    assert stage_receipt["successful_profile_sha256"] == sha256_text(profiles[1].profile_id)


def test_role_replica_selected_but_blocked_before_provider_is_not_counted_as_attempt():
    class FirstReplicaFailureClient:
        def __init__(self):
            self.calls = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            del request, prompt, system, timeout
            self.calls.append(profile.profile_id)
            raise RuntimeError("fixture first replica transport failure")

    profiles = _canonical_replica_profiles()[:3]
    client = FirstReplicaFailureClient()
    engine = FusionEngine(profiles, client=client, cache_enabled=False)
    role = {"role": "primary_solver", "model": profiles[0].safe_dict()}

    candidate = engine._run_role(
        FusionRequest(model="axio-fast", prompt="bounded retry accounting"),
        role,
        call_budget=_CallBudget(1),
    )
    replica_receipt = candidate.safe_dict()["task_execution"]["replica_routing"]

    assert client.calls == [profiles[0].profile_id]
    assert candidate.error_type == "BudgetExhausted"
    assert replica_receipt["stage_attempt_count"] == 1
    assert replica_receipt["attempted_profile_hash_count"] == 1
    assert replica_receipt["stage_failure_count"] == 1
    assert replica_receipt["failover_used"] is False
    assert replica_receipt["successful_profile_sha256"] == ""
