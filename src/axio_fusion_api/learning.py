from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .schemas import sha256_text


def build_learning_signal_report(
    *,
    feedback_paths: Sequence[str | Path] = (),
    scorecard_paths: Sequence[str | Path] = (),
    min_examples_for_policy_update: int = 20,
    allow_benchmark_diagnostics: bool = False,
) -> dict[str, Any]:
    feedback = _load_feedback(feedback_paths)
    benchmark_diagnostics_admitted = bool(scorecard_paths) and bool(allow_benchmark_diagnostics)
    scorecards = _load_json_files(scorecard_paths) if benchmark_diagnostics_admitted else []
    eligible = [
        row
        for row in feedback
        if isinstance(row.get("training_signal"), Mapping)
        and row["training_signal"].get("eligible_for_router_learning")
    ]
    scores = [_effective_score(row) for row in eligible]
    scores = [float(score) for score in scores if score is not None]
    accepted = [_effective_acceptance(row) for row in eligible]
    accepted = [bool(value) for value in accepted if value is not None]
    route_rows = [_route_key(row) for row in eligible]
    route_summary = _summarize_routes(eligible)
    routing_policy_summary = _summarize_routing_policies(eligible)
    verification_summary = _summarize_external_verification(eligible)
    agent_outcome_summary = _summarize_agent_outcomes(eligible)
    benchmark_summary = _summarize_scorecards(scorecards)
    benchmark_learning_contract = _benchmark_learning_contract(
        scorecard_paths=scorecard_paths,
        scorecards=scorecards,
        diagnostics_admitted=benchmark_diagnostics_admitted,
    )
    return {
        "schema": "axio_fusion_api.learning_signal_report.v1",
        "feedback_file_count": len(feedback_paths),
        "feedback_count": len(feedback),
        "eligible_feedback_count": len(eligible),
        "average_score": None if not scores else round(sum(scores) / len(scores), 6),
        "accepted_rate": None if not accepted else round(sum(1 for value in accepted if value) / len(accepted), 6),
        "route_summary": route_summary,
        "routing_policy_summary": routing_policy_summary,
        "external_verification_summary": verification_summary,
        "agent_outcome_summary": agent_outcome_summary,
        "benchmark_summary": benchmark_summary,
        "benchmark_learning_contract": benchmark_learning_contract,
        "benchmark_diagnostic_suggestions": (
            _benchmark_diagnostic_suggestions(benchmark_summary)
            if benchmark_diagnostics_admitted
            else []
        ),
        "policy_suggestions": _policy_suggestions(
            eligible_count=len(eligible),
            average_score=None if not scores else sum(scores) / len(scores),
            accepted_rate=None if not accepted else sum(1 for value in accepted if value) / len(accepted),
            route_summary=route_summary,
            verification_summary=verification_summary,
            # Benchmark evidence is intentionally excluded from operational
            # policy suggestions, even when diagnostic summaries are admitted.
            benchmark_summary={},
            min_examples=min_examples_for_policy_update,
        ),
        "training_dataset_manifest": {
            "example_count": len(route_rows),
            "features": [
                "public_model",
                "strategy",
                "task_type",
                "privacy_level",
                "routing_policy_version_sha256",
                "routing_policy_active",
                "routing_policy_applied",
                "routing_policy_matched_rule_count",
                "routing_policy_quality_target_floor",
                "routing_policy_force_fusion",
                "routing_policy_fast_light_verify",
                "routing_policy_context_directive_count",
                "complexity",
                "risk",
                "uncertainty",
                "factuality_signal",
                "vertical_domain_signal_count",
                "provider_call_count",
                "latency_ms",
                "actual_cost_usd",
                "score",
                "accepted",
                "external_verification_score",
                "external_verification_passed",
                "agent_task_success",
                "agent_tool_failure_count",
                "agent_repair_loop_count",
                "fusion_utility_score",
                "fusion_error_correlation_penalty",
                "fast_light_verify_requested",
                "fast_light_verify_active",
                "judge_answer_claim_consensus_detected",
                "judge_largest_answer_claim_equivalence_type",
                "judge_answer_claim_numeric_equivalence_detected",
                "judge_answer_claim_independent_consensus_detected",
                "judge_largest_answer_claim_unique_profile_count",
                "judge_largest_answer_claim_unique_provider_count",
                "judge_confidence_calibration_candidate_count",
                "judge_average_calibrated_confidence",
                "judge_average_confidence_calibration_delta",
                "judge_overconfidence_risk_rate",
                "judge_confidence_calibration_penalty_count",
                "early_exit_answer_claim_consensus_passed",
                "early_exit_answer_claim_support_fraction",
                "early_exit_answer_claim_equivalence_type",
                "early_exit_answer_claim_independent_detected",
                "early_exit_answer_claim_unique_profile_count",
                "early_exit_answer_claim_unique_provider_count",
                "early_exit_best_candidate_calibrated_confidence",
                "targeted_answer_claim_independence_required",
                "targeted_requires_cross_provider_verifier",
                "targeted_requires_new_profile_verifier",
                "targeted_selected_new_provider_for_claim",
                "targeted_selected_new_profile_for_claim",
                "judge_largest_answer_claim_support_fraction",
                "judge_largest_answer_claim_cluster_size",
                "panel_provider_diversity",
                "panel_capability_complementarity",
                "panel_estimated_error_correlation",
                "provider_fallback_enabled",
                "provider_fallback_pool_count",
                "provider_fallback_top_routing_score",
                "provider_fallback_top_availability_score",
                "provider_fallback_average_routing_score",
                "provider_fallback_selected_panel_count",
                "provider_fallback_nonpanel_count",
                "provider_fallback_api_format_count",
                "candidate_deduplication_duplicate_rate",
                "candidate_deduplication_duplicate_candidate_count",
                "prompt_budget_truncated_call_count",
                "synthesis_omitted_candidate_count",
                "candidate_standardization_parse_success_rate",
                "mandatory_stage_reservation_enabled",
                "mandatory_stage_reservation_skip_count",
                "mandatory_stage_reservation_consumed_call_count",
                "mandatory_stage_reservation_released_call_count",
                "fusion_initial_resource_budget_applicable",
                "fusion_initial_resource_budget_blocked",
                "fusion_initial_cost_estimate_known",
                "fusion_initial_latency_estimate_known",
                "fusion_initial_cost_within_request_budget",
                "fusion_initial_latency_within_request_deadline",
            ],
            "target": "router_policy_preference",
            "benchmark_diagnostics_admitted": benchmark_diagnostics_admitted,
            "benchmark_scores_used_for_training": False,
            "benchmark_labels_used_for_training": False,
            "router_learning_source": "operational_feedback_and_runtime_traces_only",
            "benchmark_diagnostics_only": True,
            "raw_prompt_persisted": False,
            "raw_feedback_text_persisted": False,
            "raw_provider_output_persisted": False,
            "raw_model_names_persisted": False,
        },
        "training_rows_preview": route_rows[:20],
        "supervised_finetuning_ready": len(eligible) >= max(1, int(min_examples_for_policy_update)),
        "preference_learning_ready": len(scores) >= max(1, int(min_examples_for_policy_update)),
        "reinforcement_learning_ready": False,
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def _benchmark_learning_contract(
    *,
    scorecard_paths: Sequence[str | Path],
    scorecards: Sequence[Mapping[str, Any]],
    diagnostics_admitted: bool,
) -> dict[str, Any]:
    requested = bool(scorecard_paths)
    return {
        "schema": "axio_fusion_api.benchmark_learning_contract.v1",
        "scorecard_requested": requested,
        "scorecard_file_count": len(scorecard_paths),
        "scorecard_loaded_count": len(scorecards),
        "benchmark_diagnostics_admitted": bool(diagnostics_admitted),
        "benchmark_diagnostics_only": True,
        "explicit_opt_in_required": requested,
        "benchmark_scores_used_for_router_learning": False,
        "benchmark_scores_used_for_registry_calibration": False,
        "benchmark_labels_used_for_training": False,
        "production_router_changed": False,
        "production_registry_changed": False,
        "blocked_reason_codes": (
            []
            if not requested or diagnostics_admitted
            else ["benchmark_scorecard_diagnostic_requires_explicit_opt_in"]
        ),
        "raw_scorecard_paths_persisted": False,
        "raw_benchmark_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def build_orchestrator_training_dataset(
    *,
    feedback_paths: Sequence[str | Path] = (),
    trace_paths: Sequence[str | Path] = (),
    min_pair_score_delta: float = 0.15,
    max_examples: int | None = None,
) -> dict[str, Any]:
    feedback = _load_feedback(feedback_paths)
    traces = _load_trace_rows(trace_paths)
    trace_index = _trace_join_index(traces)
    examples = []
    for row in feedback:
        if not isinstance(row.get("training_signal"), Mapping) or not row["training_signal"].get("eligible_for_router_learning"):
            continue
        trace = _matching_trace(row, trace_index)
        examples.append(_training_example(row, trace))
        if max_examples is not None and len(examples) >= max(0, int(max_examples)):
            break
    preference_pairs = _preference_pairs(examples, min_delta=float(min_pair_score_delta))
    reward_rows = [
        {
            "example_id": example["example_id"],
            "reward": example["targets"]["reward"],
            "accepted": example["targets"]["accepted"],
            "external_verification_passed": example["targets"]["external_verification_passed"],
            "raw_prompt_persisted": False,
            "raw_provider_output_persisted": False,
        }
        for example in examples
        if example["targets"]["reward"] is not None
    ]
    return {
        "schema": "axio_fusion_api.orchestrator_training_dataset.v1",
        "feedback_file_count": len(feedback_paths),
        "trace_file_count": len(trace_paths),
        "feedback_count": len(feedback),
        "trace_count": len(traces),
        "router_policy_example_count": len(examples),
        "reward_model_example_count": len(reward_rows),
        "preference_pair_count": len(preference_pairs),
        "join_summary": {
            "examples_with_trace": sum(1 for example in examples if example["source_receipts"]["trace_joined"]),
            "examples_without_trace": sum(1 for example in examples if not example["source_receipts"]["trace_joined"]),
            "join_keys": ["response_id", "request_fingerprint"],
            "raw_join_values_persisted": False,
        },
        "dataset_contract": {
            "intended_use": [
                "router_policy_supervision",
                "preference_learning",
                "reward_model_calibration",
                "shadow_policy_evaluation",
            ],
            "not_for_final_benchmark_claims": True,
            "benchmark_labels_used_for_training": False,
            "raw_prompts_persisted": False,
            "raw_feedback_text_persisted": False,
            "raw_provider_outputs_persisted": False,
            "raw_candidate_text_persisted": False,
            "raw_model_names_persisted": False,
            "secrets_persisted": False,
        },
        "feature_schema": _training_feature_schema(),
        "router_policy_examples": examples,
        "reward_model_examples": reward_rows,
        "preference_pairs": preference_pairs,
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_model_names_persisted": False,
        "secrets_persisted": False,
    }


def build_router_policy_shadow_patch(
    *,
    feedback_paths: Sequence[str | Path] = (),
    trace_paths: Sequence[str | Path] = (),
    min_examples: int = 20,
) -> dict[str, Any]:
    """Build prompt-free router policy recommendations from operational signal.

    The result is deliberately shadow-only.  It is safe evidence for policy
    review and future Orchestrator training, not an automatic production patch.
    """

    feedback = _load_feedback(feedback_paths)
    traces = _load_trace_rows(trace_paths)
    trace_index = _trace_join_index(traces)
    eligible = [
        row
        for row in feedback
        if isinstance(row.get("training_signal"), Mapping)
        and row["training_signal"].get("eligible_for_router_learning")
    ]
    observations = [_shadow_observation(row, _matching_trace(row, trace_index)) for row in eligible]
    buckets_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for observation in observations:
        key = (
            observation["routing_policy_version_sha256"],
            observation["public_model"] or "unknown",
            observation["strategy"] or "unknown",
            observation["task_type"] or "unknown",
        )
        buckets_by_key.setdefault(key, []).append(observation)
    bucket_summaries = [
        _shadow_bucket_summary(key, rows, min_examples=max(1, int(min_examples)))
        for key, rows in sorted(buckets_by_key.items(), key=lambda item: (item[0][0], item[0][1], item[0][2]))
    ]
    patch_candidates: list[dict[str, Any]] = []
    for bucket in bucket_summaries:
        patch_candidates.extend(_shadow_patch_candidates(bucket, min_examples=max(1, int(min_examples))))
    if not patch_candidates:
        patch_candidates.append(
            _shadow_patch_candidate(
                target={"public_model": "all", "strategy": "all", "task_type": "all", "bucket_id": sha256_text("all")[:16]},
                action="collect_router_feedback_before_policy_change",
                priority="high" if len(observations) < max(1, int(min_examples)) else "low",
                reason="no_negative_or_positive_bucket_signal_available",
                evidence={
                    "example_count": len(observations),
                    "min_examples": max(1, int(min_examples)),
                    "evidence_state": "insufficient" if len(observations) < max(1, int(min_examples)) else "sufficient",
                },
                suggested_policy_delta={"automatic_policy_change": False},
            )
        )
    return {
        "schema": "axio_fusion_api.router_policy_shadow_patch.v1",
        "shadow_only": True,
        "safe_to_apply_automatically": False,
        "feedback_file_count": len(feedback_paths),
        "trace_file_count": len(trace_paths),
        "feedback_count": len(feedback),
        "eligible_feedback_count": len(eligible),
        "trace_count": len(traces),
        "trace_joined_feedback_count": sum(1 for row in observations if row["trace_joined"]),
        "policy_version_bucket_count": len(
            {
                row["routing_policy_version_sha256"]
                for row in observations
                if row["routing_policy_version_sha256"]
            }
        ),
        "min_examples_per_bucket": max(1, int(min_examples)),
        "bucket_count": len(bucket_summaries),
        "patch_candidate_count": len(patch_candidates),
        "input_artifacts": {
            "feedback_path_hashes": [sha256_text(str(path)) for path in feedback_paths],
            "trace_path_hashes": [sha256_text(str(path)) for path in trace_paths],
            "raw_paths_persisted": False,
        },
        "bucket_summaries": bucket_summaries,
        "patch_candidates": patch_candidates,
        "application_contract": {
            "intended_use": [
                "shadow_policy_review",
                "router_policy_ablation_design",
                "orchestrator_training_feature_audit",
            ],
            "production_policy_changed": False,
            "requires_human_or_offline_eval_before_apply": True,
            "not_for_final_benchmark_claims": True,
            "raw_prompts_persisted": False,
            "raw_feedback_text_persisted": False,
            "raw_provider_outputs_persisted": False,
            "raw_candidate_text_persisted": False,
            "raw_model_names_persisted": False,
            "raw_agent_traces_persisted": False,
            "raw_tool_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_model_names_persisted": False,
        "raw_agent_trace_persisted": False,
        "raw_tool_outputs_persisted": False,
        "secrets_persisted": False,
    }


def build_training_contamination_audit(
    *,
    benchmark_paths: Sequence[str | Path] = (),
    training_dataset_paths: Sequence[str | Path] = (),
    learning_report_paths: Sequence[str | Path] = (),
    calibration_paths: Sequence[str | Path] = (),
    feedback_paths: Sequence[str | Path] = (),
    trace_paths: Sequence[str | Path] = (),
    allow_aggregate_benchmark_calibration: bool = False,
) -> dict[str, Any]:
    """Audit whether benchmark evidence leaked into learning/calibration inputs.

    The audit is hash-only.  It never opens benchmark datasets and never stores
    raw prompts, labels, provider outputs, or artifact paths.  It is intended as
    a final-claim guardrail: held-out benchmark runs may be evaluated and
    audited, but should not become router-learning or registry-calibration
    training signal for the same claim package.
    """

    benchmark_payloads = _load_json_files(benchmark_paths)
    training_payloads = _load_json_files(training_dataset_paths)
    learning_reports = _load_json_files(learning_report_paths)
    calibrations = _load_json_files(calibration_paths)
    feedback_rows = _load_feedback(feedback_paths)
    trace_rows = _load_trace_rows(trace_paths)
    benchmark_hashes = _benchmark_artifact_hashes(benchmark_payloads)
    learning_hashes = _learning_artifact_hashes(
        training_payloads=training_payloads,
        learning_reports=learning_reports,
        feedback_rows=feedback_rows,
        trace_rows=trace_rows,
    )
    overlap_hashes = sorted(benchmark_hashes & learning_hashes)
    findings = []
    if overlap_hashes:
        findings.append(
            {
                "kind": "benchmark_learning_hash_overlap",
                "severity": "blocker",
                "overlap_count": len(overlap_hashes),
                "overlap_hash_preview": overlap_hashes[:12],
                "raw_values_persisted": False,
            }
        )
    contract_findings = _training_contract_findings(
        training_payloads=training_payloads,
        learning_reports=learning_reports,
        calibrations=calibrations,
        allow_aggregate_benchmark_calibration=allow_aggregate_benchmark_calibration,
    )
    findings.extend(contract_findings)
    blocker_count = sum(1 for row in findings if row.get("severity") == "blocker")
    warning_count = sum(1 for row in findings if row.get("severity") == "warning")
    return {
        "schema": "axio_fusion_api.training_contamination_audit.v1",
        "final_claim_training_clean": blocker_count == 0,
        "final_claim_eligible_after_training_audit": blocker_count == 0,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "input_artifacts": {
            "benchmark_file_count": len(benchmark_paths),
            "training_dataset_file_count": len(training_dataset_paths),
            "learning_report_file_count": len(learning_report_paths),
            "calibration_file_count": len(calibration_paths),
            "feedback_file_count": len(feedback_paths),
            "trace_file_count": len(trace_paths),
            "benchmark_path_hashes": [sha256_text(str(path)) for path in benchmark_paths],
            "training_dataset_path_hashes": [sha256_text(str(path)) for path in training_dataset_paths],
            "learning_report_path_hashes": [sha256_text(str(path)) for path in learning_report_paths],
            "calibration_path_hashes": [sha256_text(str(path)) for path in calibration_paths],
            "feedback_path_hashes": [sha256_text(str(path)) for path in feedback_paths],
            "trace_path_hashes": [sha256_text(str(path)) for path in trace_paths],
            "raw_paths_persisted": False,
        },
        "hash_summary": {
            "benchmark_hash_count": len(benchmark_hashes),
            "learning_hash_count": len(learning_hashes),
            "overlap_count": len(overlap_hashes),
            "raw_hash_sources_persisted": False,
        },
        "calibration_policy": {
            "allow_aggregate_benchmark_calibration": bool(allow_aggregate_benchmark_calibration),
            "default_final_claim_policy": "benchmark-derived training or calibration signals block final public superiority claims",
            "raw_benchmark_content_persisted": False,
        },
        "findings": findings,
        "anti_leakage_contract": {
            "raw_benchmark_questions_persisted": False,
            "raw_benchmark_labels_persisted": False,
            "raw_training_prompts_persisted": False,
            "raw_provider_outputs_persisted": False,
            "raw_feedback_text_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_label_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _load_feedback(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
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


def _trace_join_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    by_response: dict[str, Mapping[str, Any]] = {}
    by_fingerprint: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        join_key = row.get("feedback_join_key") if isinstance(row.get("feedback_join_key"), Mapping) else {}
        response_id = str(join_key.get("response_id") or row.get("response_id") or "")
        fingerprint = str(join_key.get("request_fingerprint") or "")
        if response_id:
            by_response[response_id] = row
        if fingerprint:
            by_fingerprint[fingerprint] = row
    return {"response_id": by_response, "request_fingerprint": by_fingerprint}


def _matching_trace(row: Mapping[str, Any], index: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> Mapping[str, Any]:
    response_id = str(row.get("response_id") or "")
    fingerprint = str(row.get("request_fingerprint") or "")
    if response_id and response_id in index.get("response_id", {}):
        return index["response_id"][response_id]
    if fingerprint and fingerprint in index.get("request_fingerprint", {}):
        return index["request_fingerprint"][fingerprint]
    return {}


def _training_example(row: Mapping[str, Any], trace: Mapping[str, Any]) -> dict[str, Any]:
    route = row.get("route_snapshot") if isinstance(row.get("route_snapshot"), Mapping) else {}
    trace_route = trace.get("routing_decision") if isinstance(trace.get("routing_decision"), Mapping) else {}
    analysis = trace.get("request_analysis") if isinstance(trace.get("request_analysis"), Mapping) else {}
    metrics = row.get("trace_metrics") if isinstance(row.get("trace_metrics"), Mapping) else {}
    trace_cost = trace.get("cost") if isinstance(trace.get("cost"), Mapping) else {}
    verification = row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {}
    agent_outcome = row.get("agent_outcome") if isinstance(row.get("agent_outcome"), Mapping) else {}
    task_plan = trace.get("task_plan") if isinstance(trace.get("task_plan"), Mapping) else {}
    runtime = trace.get("runtime_guards") if isinstance(trace.get("runtime_guards"), Mapping) else {}
    judge = trace.get("judge_result") if isinstance(trace.get("judge_result"), Mapping) else {}
    early_exit = trace.get("early_exit") if isinstance(trace.get("early_exit"), Mapping) else {}
    fusion_admission = trace.get("fusion_admission") if isinstance(trace.get("fusion_admission"), Mapping) else {}
    model_policy = trace.get("model_selection_policy") if isinstance(trace.get("model_selection_policy"), Mapping) else {}
    panel_diversity = model_policy.get("panel_diversity_receipt") if isinstance(model_policy.get("panel_diversity_receipt"), Mapping) else {}
    candidate_deduplication = trace.get("candidate_deduplication") if isinstance(trace.get("candidate_deduplication"), Mapping) else {}
    prompt_budget = trace.get("prompt_budget") if isinstance(trace.get("prompt_budget"), Mapping) else {}
    call_budget = trace.get("budget_lock") if isinstance(trace.get("budget_lock"), Mapping) else {}
    synthesis_compression = trace.get("synthesis_compression") if isinstance(trace.get("synthesis_compression"), Mapping) else {}
    cache_replay = (
        trace.get("cache_replay")
        if isinstance(trace.get("cache_replay"), Mapping)
        else {}
    )
    cache_origin_completion = (
        trace.get("cache_origin_completion")
        if isinstance(trace.get("cache_origin_completion"), Mapping)
        else {}
    )
    replay_origin_admitted = bool(
        cache_replay.get("replayed")
        and cache_origin_completion.get("cache_eligible")
    )
    fusion_stage_outcome = (
        cache_origin_completion.get("runtime_fusion_stage_outcome")
        if replay_origin_admitted
        and isinstance(
            cache_origin_completion.get("runtime_fusion_stage_outcome"), Mapping
        )
        else trace.get("runtime_fusion_stage_outcome")
        if isinstance(trace.get("runtime_fusion_stage_outcome"), Mapping)
        else {}
    )
    hermes_execution = (
        cache_origin_completion.get("hermes_moa_execution")
        if replay_origin_admitted
        and isinstance(cache_origin_completion.get("hermes_moa_execution"), Mapping)
        else trace.get("hermes_moa_execution")
        if isinstance(trace.get("hermes_moa_execution"), Mapping)
        else {}
    )
    candidate_outputs = trace.get("candidate_outputs") if isinstance(trace.get("candidate_outputs"), list) else []
    provider_routing = trace.get("provider_routing_policy") if isinstance(trace.get("provider_routing_policy"), Mapping) else {}
    routing_policy = _routing_policy_from_route_and_trace(route, trace)
    score = _effective_score(row)
    accepted = _effective_acceptance(row)
    reward = _reward_from_signals(score, accepted, verification)
    fast_light_features = _fast_light_verify_features(runtime, trace_route)
    judge_claim_features = _judge_answer_claim_features(judge)
    judge_calibration_features = _judge_confidence_calibration_features(judge)
    early_exit_claim_features = _early_exit_answer_claim_features(early_exit)
    judge_domain_features = _judge_domain_guardrail_features(judge)
    targeted_features = _targeted_escalation_features(candidate_outputs)
    fingerprint = str(row.get("request_fingerprint") or "")
    response_id = str(row.get("response_id") or "")
    public_model = str(route.get("public_model") or trace_route.get("public_model") or "")
    strategy = str(route.get("strategy") or trace_route.get("strategy") or "")
    return {
        "example_id": sha256_text(
            json.dumps(
                {
                    "response_id": response_id,
                    "request_fingerprint": fingerprint,
                    "public_model": public_model,
                    "strategy": strategy,
                    "score": score,
                    "accepted": accepted,
                },
                sort_keys=True,
            )
        )[:32],
        "request_fingerprint_sha256": sha256_text(fingerprint),
        "response_id_sha256": sha256_text(response_id),
        "source_receipts": {
            "feedback_joined": True,
            "trace_joined": bool(trace),
            "raw_response_id_persisted": False,
            "raw_request_fingerprint_persisted": False,
        },
        "features": {
            "public_model": public_model,
            "strategy": strategy,
            "task_type": str(route.get("task_type") or analysis.get("task_type") or ""),
            "privacy_level": str(route.get("privacy_level") or analysis.get("privacy_level") or ""),
            "domains": [str(item) for item in analysis.get("domains", []) if str(item)][:12] if isinstance(analysis.get("domains"), list) else [],
            "complexity": _score01(route.get("complexity", analysis.get("complexity"))),
            "risk": _score01(route.get("risk", analysis.get("risk"))),
            "uncertainty": _score01(route.get("uncertainty", analysis.get("uncertainty"))),
            "needs_tools": bool(analysis.get("needs_tools")),
            "needs_current_information": bool(analysis.get("needs_current_information")),
            "factuality_signal": bool(analysis.get("factuality_signal")),
            "vertical_domain_signals": [
                str(item)[:80]
                for item in analysis.get("vertical_domain_signals", [])
                if str(item)
            ][:12] if isinstance(analysis.get("vertical_domain_signals"), list) else [],
            "vertical_domain_signal_count": len(analysis.get("vertical_domain_signals", []))
            if isinstance(analysis.get("vertical_domain_signals"), list)
            else 0,
            "selected_model_count": _optional_int(trace_route.get("selected_model_count")),
            "selected_profile_hashes": _string_list(route.get("selected_profile_hashes")) or _string_list(trace_route.get("selected_profile_hashes")),
            "task_node_count": _optional_int(task_plan.get("node_count")),
            "task_subtask_count": _optional_int(task_plan.get("subtask_count")),
            "task_max_dependency_depth": _optional_int(task_plan.get("max_dependency_depth")),
            "provider_call_count": _optional_int(metrics.get("provider_call_count", trace_cost.get("provider_call_count"))),
            "latency_ms": _optional_float(metrics.get("latency_ms", trace.get("latency_ms"))),
            "actual_cost_usd": _optional_float(metrics.get("actual_cost_usd", trace_cost.get("actual_cost_usd"))),
            "quality_target": _optional_float(runtime.get("quality_target")),
            "max_total_model_calls": _optional_int(runtime.get("max_total_model_calls")),
            "max_latency_ms": _optional_int(runtime.get("max_latency_ms")),
            "fusion_finalization_mode": str(
                fusion_stage_outcome.get("fusion_finalization_mode")
                or route.get("fusion_finalization_mode")
                or "direct"
            )[:80],
            "local_consensus_enabled": bool(
                fusion_stage_outcome.get("local_consensus_enabled")
            ),
            "local_consensus_finalized": bool(
                fusion_stage_outcome.get("local_consensus_finalized")
            ),
            "provider_judge_required": bool(
                fusion_stage_outcome.get("provider_judge_required")
            ),
            "provider_synthesizer_required": bool(
                fusion_stage_outcome.get("provider_synthesizer_required")
            ),
            **_routing_policy_features(routing_policy),
            **_mandatory_stage_reservation_features(call_budget),
            **_runtime_fusion_stage_outcome_features(fusion_stage_outcome),
            **_hermes_moa_execution_features(hermes_execution),
            **_response_cache_replay_features(
                cache_replay,
                cache_origin_completion,
            ),
            **fast_light_features,
            **_fusion_admission_features(fusion_admission),
            **_panel_diversity_features(panel_diversity, model_policy, fusion_admission),
            **_provider_routing_features(provider_routing),
            **_candidate_deduplication_features(candidate_deduplication),
            **_prompt_budget_features(prompt_budget),
            **_synthesis_compression_features(synthesis_compression),
            **_candidate_standardization_features(candidate_outputs, synthesis_compression),
            **judge_claim_features,
            **judge_calibration_features,
            **early_exit_claim_features,
            **judge_domain_features,
            **targeted_features,
            "judge_ready_for_synthesis": bool(judge.get("ready_for_synthesis")),
            "judge_provider_call_count": _optional_int(judge.get("judge_provider_call_count")),
            "missing_coverage_count": _optional_int(judge.get("missing_coverage_count")),
            "contradiction_count": _optional_int(judge.get("contradiction_count")),
            "early_exit_triggered": bool(early_exit.get("triggered")),
            "early_exit_reason": str(early_exit.get("reason") or ""),
            "agent_outcome_provided": bool(agent_outcome.get("provided")),
            "agent_completed_step_count": _optional_int(agent_outcome.get("completed_step_count")),
            "agent_failed_step_count": _optional_int(agent_outcome.get("failed_step_count")),
            "agent_tool_call_count": _optional_int(agent_outcome.get("tool_call_count")),
            "agent_tool_failure_count": _optional_int(agent_outcome.get("tool_failure_count")),
            "agent_repair_loop_count": _optional_int(agent_outcome.get("repair_loop_count")),
            "agent_human_intervention_required": _optional_bool(agent_outcome.get("human_intervention_required")),
            "raw_prompt_persisted": False,
            "raw_model_names_persisted": False,
            "raw_agent_trace_persisted": False,
        },
        "targets": {
            "score": score,
            "accepted": accepted,
            "external_verification_score": _optional_score(verification.get("score")),
            "external_verification_passed": _optional_bool(verification.get("passed")),
            "agent_score": _optional_score(agent_outcome.get("score")),
            "agent_task_success": _optional_bool(agent_outcome.get("task_success")),
            "reward": reward,
            "router_policy_label": strategy,
            "public_model_label": public_model,
            "raw_feedback_text_persisted": False,
            "raw_provider_output_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_model_names_persisted": False,
        "raw_agent_trace_persisted": False,
    }


def _fusion_admission_features(value: Mapping[str, Any]) -> dict[str, Any]:
    direct = value.get("direct_candidate") if isinstance(value.get("direct_candidate"), Mapping) else {}
    fusion = value.get("fusion_candidate") if isinstance(value.get("fusion_candidate"), Mapping) else {}
    utility = value.get("utility_model") if isinstance(value.get("utility_model"), Mapping) else {}
    initial_call_plan = value.get("initial_fusion_call_plan") if isinstance(value.get("initial_fusion_call_plan"), Mapping) else {}
    return {
        "fusion_activated": bool(value.get("activated")),
        "fusion_threshold_passed": bool(value.get("threshold_passed")),
        "fusion_threshold": _optional_float(value.get("threshold")),
        "fusion_utility_score": _optional_float(value.get("utility_score")),
        "fusion_expected_quality_gain": _optional_float(value.get("expected_quality_gain")),
        "fusion_risk_reduction_credit": _optional_float(value.get("risk_reduction_credit")),
        "fusion_extra_cost_usd": _optional_float(value.get("extra_cost_usd")),
        "fusion_extra_latency_ms": _optional_float(value.get("extra_latency_ms")),
        "fusion_cost_penalty": _optional_float(value.get("cost_penalty")),
        "fusion_latency_penalty": _optional_float(value.get("latency_penalty")),
        "fusion_error_correlation_penalty": _optional_float(value.get("error_correlation_penalty")),
        "fusion_direct_expected_quality": _optional_float(direct.get("expected_quality")),
        "fusion_candidate_expected_quality": _optional_float(fusion.get("expected_quality")),
        "fusion_candidate_estimated_cost_usd": _optional_float(fusion.get("estimated_cost_usd")),
        "fusion_candidate_estimated_latency_ms": _optional_float(fusion.get("estimated_latency_ms")),
        "fusion_error_correlation_penalty_weight": _optional_float(utility.get("error_correlation_penalty_weight")),
        "fusion_pricing_known": bool(value.get("pricing_known")),
        "fusion_latency_known": bool(value.get("latency_known")),
        "fusion_initial_call_budget_sufficient": _optional_bool(initial_call_plan.get("complete_fusion_feasible")),
        "fusion_initial_call_budget_blocked": _optional_bool(initial_call_plan.get("blocked_by_call_budget")),
        "fusion_initial_role_budget_constrained": _optional_bool(initial_call_plan.get("role_budget_constrained")),
        "fusion_initial_minimum_call_count": _optional_int(initial_call_plan.get("minimum_complete_fusion_call_count")),
        "fusion_initial_planned_call_count": _optional_int(initial_call_plan.get("planned_initial_fusion_call_count")),
        **_initial_fusion_resource_admission_features(
            value.get("initial_fusion_resource_admission")
            if isinstance(value.get("initial_fusion_resource_admission"), Mapping)
            else {}
        ),
    }


def _initial_fusion_resource_admission_features(value: Mapping[str, Any]) -> dict[str, Any]:
    cost = value.get("cost") if isinstance(value.get("cost"), Mapping) else {}
    latency = value.get("latency") if isinstance(value.get("latency"), Mapping) else {}
    return {
        "fusion_initial_resource_budget_applicable": _optional_bool(value.get("applicable")),
        "fusion_initial_resource_budget_blocked": _optional_bool(value.get("blocked")),
        "fusion_initial_cost_estimate_known": _optional_bool(cost.get("known")),
        "fusion_initial_latency_estimate_known": _optional_bool(latency.get("known")),
        "fusion_initial_cost_within_request_budget": _optional_bool(
            cost.get("within_request_budget")
        ),
        "fusion_initial_latency_within_request_deadline": _optional_bool(
            latency.get("within_request_deadline")
        ),
    }


def _mandatory_stage_reservation_features(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mandatory_stage_reservation_enabled": bool(value.get("mandatory_stage_reservation_enabled")),
        "mandatory_stage_reservation_skip_count": _optional_int(value.get("mandatory_stage_reservation_skip_count")),
        "mandatory_stage_reservation_planned_call_count": _optional_int(value.get("planned_mandatory_stage_call_count")),
        "mandatory_stage_reservation_reserved_call_count": _optional_int(value.get("reserved_mandatory_stage_call_count")),
        "mandatory_stage_reservation_consumed_call_count": _optional_int(value.get("consumed_mandatory_stage_call_count")),
        "mandatory_stage_reservation_released_call_count": _optional_int(value.get("released_mandatory_stage_call_count")),
        "mandatory_stage_reservation_unreserved_remaining_call_count": _optional_int(value.get("unreserved_remaining_model_call_count")),
    }


def _runtime_fusion_stage_outcome_features(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runtime_fusion_requested": bool(value.get("fusion_requested")),
        "runtime_fusion_finalization_mode": str(
            value.get("fusion_finalization_mode") or "direct"
        )[:80],
        "runtime_fusion_local_consensus_enabled": bool(
            value.get("local_consensus_enabled")
        ),
        "runtime_fusion_local_consensus_finalized": bool(
            value.get("local_consensus_finalized")
        ),
        "runtime_fusion_provider_judge_required": bool(
            value.get("provider_judge_required")
        ),
        "runtime_fusion_provider_synthesizer_required": bool(
            value.get("provider_synthesizer_required")
        ),
        "runtime_fusion_judge_provider_call_count": _optional_int(
            value.get("judge_provider_call_count")
        ),
        "runtime_fusion_judge_output_accepted": bool(
            value.get("judge_output_accepted")
        ),
        "runtime_fusion_synthesis_provider_call_count": _optional_int(
            value.get("synthesis_provider_call_count")
        ),
        "runtime_fusion_synthesis_output_accepted": bool(
            value.get("synthesis_output_accepted")
        ),
        "runtime_fusion_initial_complete_admitted": bool(
            value.get("initial_complete_fusion_admitted")
        ),
        "runtime_fusion_candidate_quorum_met": bool(value.get("candidate_quorum_met")),
        "runtime_fusion_viable_panel": bool(value.get("viable_fusion_panel")),
        "runtime_fusion_hermes_process_contract_required": bool(
            value.get("hermes_process_contract_required")
        ),
        "runtime_fusion_hermes_process_contract_completed": bool(
            value.get("hermes_process_contract_completed")
        ),
        "runtime_fusion_complete_admitted_finalized": bool(
            value.get("complete_admitted_fusion_finalized")
        ),
        "runtime_fusion_degraded": bool(value.get("runtime_degraded")),
        "runtime_fusion_execution_mode": str(value.get("execution_mode") or "")[:120],
        "runtime_fusion_degradation_reason": str(
            value.get("degradation_reason") or ""
        )[:120],
    }


def _hermes_moa_execution_features(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project only process-state signals for shadow failure analysis."""

    return {
        "hermes_execution_enabled": bool(value.get("enabled")),
        "hermes_feedback_reference_required": bool(
            value.get("feedback_reference_required")
        ),
        "hermes_feedback_reference_execution_present": bool(
            value.get("feedback_reference_execution_present")
        ),
        "hermes_feedback_reference_completed": bool(
            value.get("feedback_reference_completed")
        ),
        "hermes_feedback_stage_admission_status": str(
            value.get("feedback_stage_admission_status") or "not_required"
        )[:64],
        "hermes_feedback_stage_admission_blocked": bool(
            value.get("feedback_stage_admission_blocked")
        ),
        "hermes_feedback_stage_admitted": bool(
            value.get("feedback_stage_admitted")
        ),
        "hermes_rejudge_after_feedback_completed": bool(
            value.get("rejudge_after_feedback_completed")
        ),
        "hermes_process_contract_completed": bool(
            value.get("process_contract_completed")
        ),
    }


def _response_cache_replay_features(
    replay: Mapping[str, Any],
    origin: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "response_cache_replay": bool(replay.get("replayed")),
        "response_cache_origin_eligible": bool(origin.get("cache_eligible")),
        "response_cache_origin_completion_kind": str(
            origin.get("completion_kind") or ""
        )[:80],
        "response_cache_origin_provider_call_count": _optional_int(
            origin.get("provider_call_count")
        ),
        "response_cache_origin_fusion_requested": bool(
            origin.get("fusion_requested")
        ),
        "response_cache_origin_complete_admitted_finalized": bool(
            origin.get("complete_admitted_fusion_finalized")
        ),
        "response_cache_origin_runtime_degraded": bool(
            origin.get("runtime_degraded")
        ),
        "response_cache_origin_hermes_contract_required": bool(
            origin.get("hermes_process_contract_required")
        ),
        "response_cache_origin_hermes_contract_completed": bool(
            origin.get("hermes_process_contract_completed")
        ),
        "response_cache_process_executed_this_request": bool(
            replay.get("process_executed_this_request")
        ),
    }


def _panel_diversity_features(
    panel: Mapping[str, Any],
    model_policy: Mapping[str, Any],
    fusion_admission: Mapping[str, Any],
) -> dict[str, Any]:
    fusion_candidate = fusion_admission.get("fusion_candidate") if isinstance(fusion_admission.get("fusion_candidate"), Mapping) else {}
    return {
        "panel_selected_model_count": _optional_int(
            _first_value(panel.get("selected_model_count"), fusion_candidate.get("selected_model_count"), model_policy.get("selected_model_count"))
        ),
        "panel_provider_count": _optional_int(panel.get("provider_count")),
        "panel_api_format_count": _optional_int(panel.get("api_format_count")),
        "panel_provider_diversity": _optional_float(_first_value(panel.get("provider_diversity"), fusion_candidate.get("provider_diversity"))),
        "panel_api_format_diversity": _optional_float(_first_value(panel.get("api_format_diversity"), model_policy.get("api_format_diversity"))),
        "panel_capability_coverage": _optional_float(_first_value(panel.get("capability_coverage"), fusion_candidate.get("capability_coverage"))),
        "panel_capability_complementarity": _optional_float(
            _first_value(panel.get("capability_complementarity"), fusion_candidate.get("capability_complementarity"), model_policy.get("capability_complementarity"))
        ),
        "panel_estimated_error_correlation": _optional_float(
            _first_value(panel.get("estimated_error_correlation"), fusion_candidate.get("estimated_error_correlation"), model_policy.get("estimated_error_correlation"))
        ),
        "panel_provider_diversity_enabled": bool(model_policy.get("provider_diversity_enabled")),
        "panel_provider_count_available": _optional_int(model_policy.get("provider_count_available")),
        "panel_provider_count_target": _optional_int(model_policy.get("provider_count_target")),
        "panel_provider_count_selected": _optional_int(model_policy.get("provider_count_selected")),
        "panel_provider_diversity_satisfied": _optional_bool(model_policy.get("provider_diversity_satisfied")),
        "panel_error_correlation_aware_selection_enabled": bool(model_policy.get("error_correlation_aware_selection_enabled")),
        "panel_role_diversity_enabled": bool(model_policy.get("role_diversity_enabled")),
    }


def _provider_routing_features(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_receipts = value.get("fallback_pool_receipts")
    if not isinstance(raw_receipts, list):
        raw_receipts = value.get("fallback_pool") if isinstance(value.get("fallback_pool"), list) else []
    receipts = [row for row in raw_receipts[:24] if isinstance(row, Mapping)]
    receipts.sort(key=lambda row: _optional_int(row.get("fallback_rank")) or 10_000)
    pool_count = _optional_int(value.get("fallback_pool_count"))
    if pool_count is None:
        pool_count = len(receipts)
    selected_count = sum(1 for row in receipts if row.get("selected_in_primary_panel") is True)
    nonpanel_count = sum(1 for row in receipts if row.get("selected_in_primary_panel") is not True)
    api_formats = {str(row.get("api_format") or "") for row in receipts if str(row.get("api_format") or "")}
    provider_hashes = {
        str(row.get("provider_sha256") or "")
        for row in receipts
        if _looks_like_sha256(row.get("provider_sha256"))
    }
    profile_hashes = {
        str(row.get("profile_id_sha256") or "")
        for row in receipts
        if _looks_like_sha256(row.get("profile_id_sha256"))
    }
    routing_scores = [_optional_float(row.get("routing_score")) for row in receipts]
    availability_scores = [_optional_float(row.get("availability_score")) for row in receipts]
    latency_scores = [_optional_float(row.get("latency_score")) for row in receipts]
    cost_scores = [_optional_float(row.get("cost_score")) for row in receipts]
    quality_scores = [_optional_float(row.get("estimated_quality")) for row in receipts]
    provider_diversity_scores = [_optional_float(row.get("provider_diversity_score")) for row in receipts]
    api_format_diversity_scores = [_optional_float(row.get("api_format_diversity_score")) for row in receipts]
    top = receipts[0] if receipts else {}
    top_routing = _optional_float(top.get("routing_score"))
    top_availability = _optional_float(top.get("availability_score"))
    context_policy = value.get("context_transform_policy") if isinstance(value.get("context_transform_policy"), Mapping) else {}
    sort_priorities = [str(item) for item in value.get("sort_priorities", []) if str(item)] if isinstance(value.get("sort_priorities"), list) else []
    return {
        "provider_fallback_enabled": bool(value.get("fallback_enabled")),
        "provider_fallback_pool_count": pool_count,
        "provider_fallback_pool_sorted_by": _safe_label(value.get("fallback_pool_sorted_by"), limit=160),
        "provider_fallback_sort_uses_availability": "availability" in sort_priorities,
        "provider_fallback_trigger_count": len(value.get("fallback_triggers", [])) if isinstance(value.get("fallback_triggers"), list) else 0,
        "provider_fallback_top_routing_score": top_routing,
        "provider_fallback_top_estimated_quality": _optional_float(top.get("estimated_quality")),
        "provider_fallback_top_availability_score": top_availability,
        "provider_fallback_top_latency_score": _optional_float(top.get("latency_score")),
        "provider_fallback_top_cost_score": _optional_float(top.get("cost_score")),
        "provider_fallback_top_provider_diversity_score": _optional_float(top.get("provider_diversity_score")),
        "provider_fallback_top_api_format_diversity_score": _optional_float(top.get("api_format_diversity_score")),
        "provider_fallback_average_routing_score": _average(routing_scores),
        "provider_fallback_average_estimated_quality": _average(quality_scores),
        "provider_fallback_average_availability_score": _average(availability_scores),
        "provider_fallback_average_latency_score": _average(latency_scores),
        "provider_fallback_average_cost_score": _average(cost_scores),
        "provider_fallback_average_provider_diversity_score": _average(provider_diversity_scores),
        "provider_fallback_average_api_format_diversity_score": _average(api_format_diversity_scores),
        "provider_fallback_selected_panel_count": selected_count,
        "provider_fallback_nonpanel_count": nonpanel_count,
        "provider_fallback_api_format_count": len(api_formats),
        "provider_fallback_provider_hash_count": len(provider_hashes),
        "provider_fallback_profile_hash_count": len(profile_hashes),
        "provider_fallback_has_nonpanel_candidate": nonpanel_count > 0,
        "provider_fallback_low_top_availability": top_availability is not None and top_availability < 0.65,
        "provider_fallback_low_top_routing_score": top_routing is not None and top_routing < 0.5,
        "provider_fallback_context_compression_enabled": bool(context_policy.get("compress_lower_ranked_candidates_before_synthesis")),
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
        "raw_provider_urls_persisted": False,
    }


def _prompt_budget_features(value: Mapping[str, Any]) -> dict[str, Any]:
    receipts = value.get("receipts") if isinstance(value.get("receipts"), list) else []
    truncated_call_count = _optional_int(value.get("truncated_call_count"))
    if truncated_call_count is None:
        truncated_call_count = sum(
            1
            for row in receipts
            if isinstance(row, Mapping)
            and (bool(row.get("prompt_truncated")) or bool(row.get("system_truncated")))
        )
    overflow_total = sum(
        _optional_int(row.get("input_budget_overflow_tokens")) or 0
        for row in receipts
        if isinstance(row, Mapping)
    )
    original_input = sum(
        _optional_int(row.get("original_input_tokens")) or 0
        for row in receipts
        if isinstance(row, Mapping)
    )
    final_input = sum(
        _optional_int(row.get("final_input_tokens")) or 0
        for row in receipts
        if isinstance(row, Mapping)
    )
    return {
        "prompt_budget_receipt_count": _optional_int(value.get("receipt_count")) or len(receipts),
        "prompt_budget_context_budget_enforced": bool(value.get("context_budget_enforced")),
        "prompt_budget_truncated_call_count": truncated_call_count,
        "prompt_budget_any_truncated": truncated_call_count > 0,
        "prompt_budget_overflow_token_total": overflow_total,
        "prompt_budget_original_input_token_total": original_input,
        "prompt_budget_final_input_token_total": final_input,
        "prompt_budget_input_token_reduction": max(0, original_input - final_input),
    }


def _synthesis_compression_features(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "synthesis_compression_enabled": bool(value.get("enabled")),
        "synthesis_max_full_candidate_count": _optional_int(value.get("max_full_candidate_count")),
        "synthesis_full_candidate_count": _optional_int(value.get("full_candidate_count")),
        "synthesis_omitted_candidate_count": _optional_int(value.get("omitted_candidate_count")) or 0,
    }


def _candidate_deduplication_features(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_deduplication_enabled": bool(value.get("enabled")),
        "candidate_deduplication_before_count": _optional_int(value.get("candidate_count_before")),
        "candidate_deduplication_after_count": _optional_int(value.get("candidate_count_after")),
        "candidate_deduplication_duplicate_candidate_count": _optional_int(value.get("duplicate_candidate_count")) or 0,
        "candidate_deduplication_duplicate_group_count": _optional_int(value.get("duplicate_group_count")) or 0,
        "candidate_deduplication_duplicate_rate": _optional_float(value.get("duplicate_rate")) or 0.0,
        "candidate_deduplication_high_duplicate_rate": bool(value.get("high_duplicate_rate")),
    }


def _candidate_standardization_features(
    candidates: Sequence[Any],
    synthesis_compression: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [row for row in candidates if isinstance(row, Mapping)]
    omitted = synthesis_compression.get("omitted_candidate_receipts") if isinstance(synthesis_compression.get("omitted_candidate_receipts"), list) else []
    rows.extend(row for row in omitted if isinstance(row, Mapping))
    standardizations = [
        row.get("standardization")
        for row in rows
        if isinstance(row.get("standardization"), Mapping)
    ]
    parsed = [bool(row.get("parsed")) for row in standardizations if isinstance(row, Mapping)]
    missing_total = sum(
        len(row.get("missing_required_fields", [])) if isinstance(row.get("missing_required_fields"), list) else 0
        for row in standardizations
        if isinstance(row, Mapping)
    )
    raw_fallback_count = sum(
        1
        for row in standardizations
        if isinstance(row, Mapping) and str(row.get("parse_mode") or "") == "raw_text_fallback"
    )
    return {
        "candidate_output_count": len(rows),
        "candidate_standardization_count": len(standardizations),
        "candidate_standardization_parsed_count": sum(1 for value in parsed if value),
        "candidate_standardization_parse_success_rate": None if not parsed else round(sum(1 for value in parsed if value) / len(parsed), 6),
        "candidate_standardization_raw_fallback_count": raw_fallback_count,
        "candidate_standardization_missing_required_field_count": missing_total,
    }


def _fast_light_verify_features(runtime: Mapping[str, Any], routing: Mapping[str, Any]) -> dict[str, Any]:
    strategy = str(routing.get("strategy") or "")
    requested = _optional_bool(runtime.get("fast_light_verify_requested"))
    active = _optional_bool(runtime.get("fast_light_verify_active"))
    if requested is None:
        requested = strategy == "fast_light_verify"
    if active is None:
        active = strategy == "fast_light_verify"
    return {
        "fast_light_verify_requested": bool(requested),
        "fast_light_verify_active": bool(active),
        "fast_light_verify_strategy_detected": strategy == "fast_light_verify",
    }


def _judge_answer_claim_features(judge: Mapping[str, Any]) -> dict[str, Any]:
    consensus = _optional_bool(judge.get("answer_claim_consensus_detected"))
    cluster_size = _optional_int(judge.get("largest_answer_claim_cluster_size"))
    support_fraction = _optional_float(judge.get("largest_answer_claim_support_fraction"))
    cluster_count = _optional_int(judge.get("answer_claim_cluster_count"))
    equivalence_type = _safe_label(judge.get("largest_answer_claim_equivalence_type"), default="unknown")
    unique_profile_count = _optional_int(judge.get("largest_answer_claim_unique_profile_count"))
    unique_provider_count = _optional_int(judge.get("largest_answer_claim_unique_provider_count"))
    independent_consensus = _optional_bool(judge.get("answer_claim_independent_consensus_detected"))
    if consensus is None and cluster_size is not None:
        consensus = cluster_size >= 2
    if independent_consensus is None and cluster_size is not None and unique_profile_count is not None:
        independent_consensus = cluster_size >= 2 and unique_profile_count >= 2
    return {
        "judge_answer_claim_cluster_count": cluster_count,
        "judge_largest_answer_claim_cluster_size": cluster_size,
        "judge_largest_answer_claim_support_fraction": support_fraction,
        "judge_answer_claim_consensus_detected": consensus,
        "judge_answer_claim_independent_consensus_detected": independent_consensus,
        "judge_largest_answer_claim_unique_profile_count": unique_profile_count,
        "judge_largest_answer_claim_unique_provider_count": unique_provider_count,
        "judge_largest_answer_claim_equivalence_type": equivalence_type,
        "judge_answer_claim_numeric_equivalence_detected": equivalence_type == "numeric_value",
    }


def _judge_confidence_calibration_features(judge: Mapping[str, Any]) -> dict[str, Any]:
    summary = judge.get("confidence_calibration_summary") if isinstance(judge.get("confidence_calibration_summary"), Mapping) else {}
    return {
        "judge_confidence_calibration_candidate_count": _optional_int(summary.get("candidate_count")),
        "judge_average_raw_confidence": _optional_float(summary.get("average_raw_confidence")),
        "judge_average_calibrated_confidence": _optional_float(summary.get("average_calibrated_confidence")),
        "judge_average_confidence_calibration_delta": _optional_float(summary.get("average_calibration_delta")),
        "judge_min_calibrated_confidence": _optional_float(summary.get("min_calibrated_confidence")),
        "judge_max_calibrated_confidence": _optional_float(summary.get("max_calibrated_confidence")),
        "judge_overconfidence_risk_count": _optional_int(summary.get("overconfidence_risk_count")),
        "judge_overconfidence_risk_rate": _optional_float(summary.get("overconfidence_risk_rate")),
        "judge_confidence_calibration_penalty_count": _optional_int(summary.get("penalty_candidate_count")),
        "judge_confidence_calibration_credit_count": _optional_int(summary.get("credit_candidate_count")),
    }


def _early_exit_answer_claim_features(early_exit: Mapping[str, Any]) -> dict[str, Any]:
    claim = early_exit.get("answer_claim_consensus") if isinstance(early_exit.get("answer_claim_consensus"), Mapping) else {}
    return {
        "early_exit_best_candidate_confidence": _optional_float(early_exit.get("best_candidate_confidence")),
        "early_exit_best_candidate_calibrated_confidence": _optional_float(early_exit.get("best_candidate_calibrated_confidence")),
        "early_exit_answer_claim_consensus_evaluated": bool(claim.get("evaluated")),
        "early_exit_answer_claim_consensus_passed": bool(claim.get("passed")),
        "early_exit_answer_claim_independent_detected": bool(claim.get("independent_detected")),
        "early_exit_answer_claim_cluster_size": _optional_int(claim.get("largest_cluster_size")),
        "early_exit_answer_claim_support_fraction": _optional_float(claim.get("largest_support_fraction")),
        "early_exit_answer_claim_unique_profile_count": _optional_int(claim.get("largest_unique_profile_count")),
        "early_exit_answer_claim_unique_provider_count": _optional_int(claim.get("largest_unique_provider_count")),
        "early_exit_answer_claim_equivalence_type": _safe_label(claim.get("largest_answer_claim_equivalence_type"), default="unknown"),
    }


def _judge_domain_guardrail_features(judge: Mapping[str, Any]) -> dict[str, Any]:
    coverage = judge.get("coverage_summary") if isinstance(judge.get("coverage_summary"), Mapping) else {}
    requires_source = _optional_bool(coverage.get("requires_source_grounding"))
    has_source = _optional_bool(coverage.get("has_source_grounding_evidence"))
    source_node_count = _optional_int(coverage.get("factuality_source_node_count"))
    source_nodes_covered = _optional_int(coverage.get("factuality_source_nodes_covered_count"))
    requires_vertical = _optional_bool(coverage.get("requires_vertical_domain_guardrails"))
    guardrail_node_count = _optional_int(coverage.get("vertical_domain_guardrail_node_count"))
    guardrail_nodes_covered = _optional_int(coverage.get("vertical_domain_guardrail_nodes_covered_count"))
    source_missing = None
    if requires_source is True:
        source_missing = (has_source is not True) or ((source_node_count or 0) > 0 and (source_nodes_covered or 0) <= 0)
    vertical_missing = None
    if requires_vertical is True:
        vertical_missing = (guardrail_node_count or 0) > 0 and (guardrail_nodes_covered or 0) <= 0
    return {
        "judge_requires_source_grounding": requires_source,
        "judge_has_source_grounding_evidence": has_source,
        "judge_source_grounding_evidence_count": _optional_int(coverage.get("source_grounding_evidence_count")),
        "factuality_source_grounding_missing": source_missing,
        "factuality_dag_covered_fraction": _optional_float(coverage.get("factuality_dag_covered_fraction")),
        "judge_requires_vertical_domain_guardrails": requires_vertical,
        "vertical_domain_guardrail_missing": vertical_missing,
        "vertical_domain_guardrail_covered_fraction": _optional_float(coverage.get("vertical_domain_guardrail_covered_fraction")),
    }


def _targeted_escalation_features(candidate_outputs: Sequence[Any]) -> dict[str, Any]:
    plans = []
    for row in candidate_outputs:
        if not isinstance(row, Mapping):
            continue
        plan = row.get("escalation_plan") if isinstance(row.get("escalation_plan"), Mapping) else {}
        if plan:
            plans.append(plan)
    requirements = [
        plan.get("answer_claim_independence_requirement")
        for plan in plans
        if isinstance(plan.get("answer_claim_independence_requirement"), Mapping)
    ]
    selections = [
        plan.get("model_selection")
        for plan in plans
        if isinstance(plan.get("model_selection"), Mapping)
    ]
    return {
        "targeted_escalation_candidate_count": len(plans),
        "targeted_answer_claim_independence_required": any(bool(item.get("required")) for item in requirements if isinstance(item, Mapping)),
        "targeted_requires_cross_provider_verifier": any(bool(item.get("require_new_provider")) for item in requirements if isinstance(item, Mapping)),
        "targeted_requires_new_profile_verifier": any(bool(item.get("require_new_profile")) for item in requirements if isinstance(item, Mapping)),
        "targeted_selected_new_provider_for_claim": any(
            bool(item.get("selected_is_new_provider_for_claim"))
            for item in selections
            if isinstance(item, Mapping)
        ),
        "targeted_selected_new_profile_for_claim": any(
            bool(item.get("selected_is_new_profile_for_claim"))
            for item in selections
            if isinstance(item, Mapping)
        ),
        "targeted_independence_model_selection_present": any(bool(item.get("selected")) for item in selections if isinstance(item, Mapping)),
    }


def _preference_pairs(examples: Sequence[Mapping[str, Any]], *, min_delta: float) -> list[dict[str, Any]]:
    by_fingerprint: dict[str, list[Mapping[str, Any]]] = {}
    for example in examples:
        fingerprint_hash = str(example.get("request_fingerprint_sha256") or "")
        reward = example.get("targets", {}).get("reward") if isinstance(example.get("targets"), Mapping) else None
        if not fingerprint_hash or reward is None:
            continue
        by_fingerprint.setdefault(fingerprint_hash, []).append(example)
    pairs = []
    for fingerprint_hash, rows in by_fingerprint.items():
        ordered = sorted(rows, key=lambda item: float(item.get("targets", {}).get("reward")), reverse=True)
        if len(ordered) < 2:
            continue
        winner = ordered[0]
        loser = ordered[-1]
        delta = float(winner["targets"]["reward"]) - float(loser["targets"]["reward"])
        if delta < min_delta:
            continue
        pairs.append(
            {
                "pair_id": sha256_text(f"{winner['example_id']}:{loser['example_id']}")[:32],
                "request_fingerprint_sha256": fingerprint_hash,
                "winner_example_id": winner["example_id"],
                "loser_example_id": loser["example_id"],
                "reward_delta": round(delta, 6),
                "winner_strategy": winner.get("features", {}).get("strategy") if isinstance(winner.get("features"), Mapping) else "",
                "loser_strategy": loser.get("features", {}).get("strategy") if isinstance(loser.get("features"), Mapping) else "",
                "raw_prompt_persisted": False,
                "raw_provider_output_persisted": False,
            }
        )
    return pairs


def _reward_from_signals(score: float | None, accepted: bool | None, verification: Mapping[str, Any]) -> float | None:
    values = []
    if score is not None:
        values.append(max(-1.0, min(1.0, float(score))))
    if accepted is not None:
        values.append(1.0 if accepted else -1.0)
    verification_score = _optional_score(verification.get("score"))
    if verification_score is not None:
        values.append(max(-1.0, min(1.0, verification_score)))
    passed = _optional_bool(verification.get("passed"))
    if passed is not None and verification_score is None:
        values.append(1.0 if passed else -1.0)
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _training_feature_schema() -> dict[str, Any]:
    return {
        "feature_groups": [
            "request_analysis",
            "domain_and_factuality_signals",
            "factuality_vertical_guardrails",
            "route_policy",
            "task_dag_summary",
            "runtime_guards",
            "judge_summary",
            "judge_confidence_calibration",
            "cost_latency",
            "agent_outcome",
            "fusion_admission",
            "fast_light_verify_policy",
            "judge_answer_claim_clusters",
            "targeted_answer_claim_independence",
            "panel_diversity",
            "provider_routing_fallback",
            "prompt_budget",
            "candidate_standardization",
            "candidate_deduplication",
            "synthesis_compression",
            "mandatory_fusion_stage_reservations",
            "hermes_moa_process_contract",
            "response_cache_replay_contract",
        ],
        "target_groups": [
            "router_policy_label",
            "public_model_label",
            "reward",
            "accepted",
            "external_verification",
            "agent_outcome",
        ],
        "all_text_fields_are_labels_or_hashes": True,
        "raw_prompt_persisted": False,
        "raw_provider_output_persisted": False,
    }


def _routing_policy_from_route_and_trace(
    route: Mapping[str, Any], trace: Mapping[str, Any]
) -> Mapping[str, Any]:
    trace_policy = trace.get("routing_policy") if isinstance(trace.get("routing_policy"), Mapping) else {}
    if trace_policy:
        return trace_policy
    route_policy = route.get("routing_policy") if isinstance(route.get("routing_policy"), Mapping) else {}
    return route_policy


def _routing_policy_features(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return bounded policy-version features from an already-safe receipt."""

    policy = value if isinstance(value, Mapping) else {}
    bundle_digest = str(policy.get("bundle_digest_sha256") or "").strip().lower()
    policy_id = str(policy.get("policy_id_sha256") or "").strip().lower()
    declared_version = str(policy.get("policy_version_sha256") or "").strip().lower()
    version = next(
        (
            item
            for item in (declared_version, bundle_digest, policy_id)
            if _looks_like_sha256(item)
        ),
        "",
    )
    directives = policy.get("context_directives") if isinstance(policy.get("context_directives"), list) else []
    allowed_directives = {
        "evidence_first",
        "independent_solution",
        "verify_assumptions",
        "tool_schema_strict",
        "uncertainty_calibration",
        "concise_synthesis",
    }
    return {
        "routing_policy_version_sha256": version,
        "routing_policy_active": policy.get("active") is True,
        "routing_policy_applied": policy.get("applied") is True,
        "routing_policy_matched_rule_count": _optional_int(
            policy.get("matched_rule_count")
        )
        or 0,
        "routing_policy_quality_target_floor": _score01(
            policy.get("quality_target_floor")
        ),
        "routing_policy_force_fusion": policy.get("force_fusion") is True,
        "routing_policy_fast_light_verify": policy.get("fast_light_verify") is True,
        "routing_policy_max_panel_models": _optional_int(
            policy.get("max_panel_models")
        ),
        "routing_policy_max_fusion_depth": _optional_int(
            policy.get("max_fusion_depth")
        ),
        "routing_policy_context_directive_count": len(
            [item for item in directives if str(item) in allowed_directives]
        ),
        "raw_policy_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
    }


def _shadow_observation(row: Mapping[str, Any], trace: Mapping[str, Any]) -> dict[str, Any]:
    route = row.get("route_snapshot") if isinstance(row.get("route_snapshot"), Mapping) else {}
    trace_route = trace.get("routing_decision") if isinstance(trace.get("routing_decision"), Mapping) else {}
    analysis = trace.get("request_analysis") if isinstance(trace.get("request_analysis"), Mapping) else {}
    metrics = row.get("trace_metrics") if isinstance(row.get("trace_metrics"), Mapping) else {}
    trace_cost = trace.get("cost") if isinstance(trace.get("cost"), Mapping) else {}
    runtime = trace.get("runtime_guards") if isinstance(trace.get("runtime_guards"), Mapping) else {}
    fusion_admission = trace.get("fusion_admission") if isinstance(trace.get("fusion_admission"), Mapping) else {}
    model_policy = trace.get("model_selection_policy") if isinstance(trace.get("model_selection_policy"), Mapping) else {}
    panel_diversity = model_policy.get("panel_diversity_receipt") if isinstance(model_policy.get("panel_diversity_receipt"), Mapping) else {}
    candidate_deduplication = trace.get("candidate_deduplication") if isinstance(trace.get("candidate_deduplication"), Mapping) else {}
    prompt_budget = trace.get("prompt_budget") if isinstance(trace.get("prompt_budget"), Mapping) else {}
    synthesis_compression = trace.get("synthesis_compression") if isinstance(trace.get("synthesis_compression"), Mapping) else {}
    provider_routing = trace.get("provider_routing_policy") if isinstance(trace.get("provider_routing_policy"), Mapping) else {}
    judge = trace.get("judge_result") if isinstance(trace.get("judge_result"), Mapping) else {}
    early_exit = trace.get("early_exit") if isinstance(trace.get("early_exit"), Mapping) else {}
    candidate_outputs = trace.get("candidate_outputs") if isinstance(trace.get("candidate_outputs"), list) else []
    routing_policy = _routing_policy_from_route_and_trace(route, trace)
    prompt_features = _prompt_budget_features(prompt_budget)
    panel_features = _panel_diversity_features(panel_diversity, model_policy, fusion_admission)
    fusion_features = _fusion_admission_features(fusion_admission)
    synthesis_features = _synthesis_compression_features(synthesis_compression)
    dedupe_features = _candidate_deduplication_features(candidate_deduplication)
    provider_features = _provider_routing_features(provider_routing)
    fast_light_features = _fast_light_verify_features(runtime, trace_route)
    judge_claim_features = _judge_answer_claim_features(judge)
    judge_calibration_features = _judge_confidence_calibration_features(judge)
    early_exit_claim_features = _early_exit_answer_claim_features(early_exit)
    judge_domain_features = _judge_domain_guardrail_features(judge)
    targeted_features = _targeted_escalation_features(candidate_outputs)
    verification = row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {}
    agent_outcome = row.get("agent_outcome") if isinstance(row.get("agent_outcome"), Mapping) else {}
    score = _effective_score(row)
    accepted = _effective_acceptance(row)
    return {
        "public_model": _safe_label(_first_value(route.get("public_model"), trace_route.get("public_model")), default="unknown"),
        "strategy": _safe_label(_first_value(route.get("strategy"), trace_route.get("strategy")), default="unknown", limit=120),
        "task_type": _safe_label(_first_value(route.get("task_type"), analysis.get("task_type")), default="unknown", limit=120),
        "privacy_level": _safe_label(_first_value(route.get("privacy_level"), analysis.get("privacy_level")), default="unknown"),
        "complexity": _score01(_first_value(route.get("complexity"), analysis.get("complexity"))),
        "risk": _score01(_first_value(route.get("risk"), analysis.get("risk"))),
        "uncertainty": _score01(_first_value(route.get("uncertainty"), analysis.get("uncertainty"))),
        **_routing_policy_features(routing_policy),
        "factuality_signal": bool(analysis.get("factuality_signal")),
        "vertical_domain_signal_count": len(analysis.get("vertical_domain_signals", []))
        if isinstance(analysis.get("vertical_domain_signals"), list)
        else 0,
        "score": score,
        "accepted": accepted,
        "reward": _reward_from_signals(score, accepted, verification),
        "external_verification_passed": _optional_bool(verification.get("passed")),
        "agent_outcome_provided": bool(agent_outcome.get("provided")),
        "agent_task_success": _optional_bool(agent_outcome.get("task_success")),
        "agent_score": _optional_score(agent_outcome.get("score")),
        "agent_tool_call_count": _optional_int(agent_outcome.get("tool_call_count")),
        "agent_tool_failure_count": _optional_int(agent_outcome.get("tool_failure_count")),
        "agent_repair_loop_count": _optional_int(agent_outcome.get("repair_loop_count")),
        "agent_human_intervention_required": _optional_bool(agent_outcome.get("human_intervention_required")),
        "provider_call_count": _optional_int(_first_value(metrics.get("provider_call_count"), trace_cost.get("provider_call_count"))),
        "latency_ms": _optional_float(_first_value(metrics.get("latency_ms"), trace.get("latency_ms"))),
        "actual_cost_usd": _optional_float(_first_value(metrics.get("actual_cost_usd"), trace_cost.get("actual_cost_usd"))),
        "quality_target": _optional_float(runtime.get("quality_target")),
        "max_total_model_calls": _optional_int(runtime.get("max_total_model_calls")),
        "fast_light_verify_requested": fast_light_features["fast_light_verify_requested"],
        "fast_light_verify_active": fast_light_features["fast_light_verify_active"],
        "fusion_activated": fusion_features["fusion_activated"],
        "fusion_utility_score": fusion_features["fusion_utility_score"],
        "fusion_expected_quality_gain": fusion_features["fusion_expected_quality_gain"],
        "fusion_error_correlation_penalty": fusion_features["fusion_error_correlation_penalty"],
        "fusion_cost_penalty": fusion_features["fusion_cost_penalty"],
        "fusion_latency_penalty": fusion_features["fusion_latency_penalty"],
        "fusion_initial_resource_budget_applicable": fusion_features["fusion_initial_resource_budget_applicable"],
        "fusion_initial_resource_budget_blocked": fusion_features["fusion_initial_resource_budget_blocked"],
        "fusion_initial_cost_estimate_known": fusion_features["fusion_initial_cost_estimate_known"],
        "fusion_initial_latency_estimate_known": fusion_features["fusion_initial_latency_estimate_known"],
        "fusion_initial_cost_within_request_budget": fusion_features["fusion_initial_cost_within_request_budget"],
        "fusion_initial_latency_within_request_deadline": fusion_features["fusion_initial_latency_within_request_deadline"],
        "panel_provider_diversity": panel_features["panel_provider_diversity"],
        "panel_api_format_diversity": panel_features["panel_api_format_diversity"],
        "panel_capability_coverage": panel_features["panel_capability_coverage"],
        "panel_capability_complementarity": panel_features["panel_capability_complementarity"],
        "panel_estimated_error_correlation": panel_features["panel_estimated_error_correlation"],
        "panel_provider_diversity_satisfied": panel_features["panel_provider_diversity_satisfied"],
        "provider_fallback_enabled": provider_features["provider_fallback_enabled"],
        "provider_fallback_pool_count": provider_features["provider_fallback_pool_count"],
        "provider_fallback_top_routing_score": provider_features["provider_fallback_top_routing_score"],
        "provider_fallback_top_availability_score": provider_features["provider_fallback_top_availability_score"],
        "provider_fallback_top_latency_score": provider_features["provider_fallback_top_latency_score"],
        "provider_fallback_top_cost_score": provider_features["provider_fallback_top_cost_score"],
        "provider_fallback_average_routing_score": provider_features["provider_fallback_average_routing_score"],
        "provider_fallback_average_availability_score": provider_features["provider_fallback_average_availability_score"],
        "provider_fallback_selected_panel_count": provider_features["provider_fallback_selected_panel_count"],
        "provider_fallback_nonpanel_count": provider_features["provider_fallback_nonpanel_count"],
        "provider_fallback_api_format_count": provider_features["provider_fallback_api_format_count"],
        "provider_fallback_provider_hash_count": provider_features["provider_fallback_provider_hash_count"],
        "provider_fallback_has_nonpanel_candidate": provider_features["provider_fallback_has_nonpanel_candidate"],
        "provider_fallback_low_top_availability": provider_features["provider_fallback_low_top_availability"],
        "provider_fallback_low_top_routing_score": provider_features["provider_fallback_low_top_routing_score"],
        "provider_fallback_context_compression_enabled": provider_features["provider_fallback_context_compression_enabled"],
        "judge_answer_claim_cluster_count": judge_claim_features["judge_answer_claim_cluster_count"],
        "judge_largest_answer_claim_cluster_size": judge_claim_features["judge_largest_answer_claim_cluster_size"],
        "judge_largest_answer_claim_support_fraction": judge_claim_features["judge_largest_answer_claim_support_fraction"],
        "judge_answer_claim_consensus_detected": judge_claim_features["judge_answer_claim_consensus_detected"],
        "judge_answer_claim_independent_consensus_detected": judge_claim_features["judge_answer_claim_independent_consensus_detected"],
        "judge_largest_answer_claim_unique_profile_count": judge_claim_features["judge_largest_answer_claim_unique_profile_count"],
        "judge_largest_answer_claim_unique_provider_count": judge_claim_features["judge_largest_answer_claim_unique_provider_count"],
        "judge_largest_answer_claim_equivalence_type": judge_claim_features["judge_largest_answer_claim_equivalence_type"],
        "judge_answer_claim_numeric_equivalence_detected": judge_claim_features["judge_answer_claim_numeric_equivalence_detected"],
        "judge_confidence_calibration_candidate_count": judge_calibration_features["judge_confidence_calibration_candidate_count"],
        "judge_average_raw_confidence": judge_calibration_features["judge_average_raw_confidence"],
        "judge_average_calibrated_confidence": judge_calibration_features["judge_average_calibrated_confidence"],
        "judge_average_confidence_calibration_delta": judge_calibration_features["judge_average_confidence_calibration_delta"],
        "judge_overconfidence_risk_rate": judge_calibration_features["judge_overconfidence_risk_rate"],
        "judge_confidence_calibration_penalty_count": judge_calibration_features["judge_confidence_calibration_penalty_count"],
        "judge_confidence_calibration_credit_count": judge_calibration_features["judge_confidence_calibration_credit_count"],
        "early_exit_best_candidate_confidence": early_exit_claim_features["early_exit_best_candidate_confidence"],
        "early_exit_best_candidate_calibrated_confidence": early_exit_claim_features["early_exit_best_candidate_calibrated_confidence"],
        "early_exit_answer_claim_consensus_passed": early_exit_claim_features["early_exit_answer_claim_consensus_passed"],
        "early_exit_answer_claim_independent_detected": early_exit_claim_features["early_exit_answer_claim_independent_detected"],
        "early_exit_answer_claim_support_fraction": early_exit_claim_features["early_exit_answer_claim_support_fraction"],
        "early_exit_answer_claim_unique_profile_count": early_exit_claim_features["early_exit_answer_claim_unique_profile_count"],
        "early_exit_answer_claim_unique_provider_count": early_exit_claim_features["early_exit_answer_claim_unique_provider_count"],
        "early_exit_answer_claim_equivalence_type": early_exit_claim_features["early_exit_answer_claim_equivalence_type"],
        "judge_requires_source_grounding": judge_domain_features["judge_requires_source_grounding"],
        "judge_has_source_grounding_evidence": judge_domain_features["judge_has_source_grounding_evidence"],
        "judge_source_grounding_evidence_count": judge_domain_features["judge_source_grounding_evidence_count"],
        "factuality_source_grounding_missing": judge_domain_features["factuality_source_grounding_missing"],
        "factuality_dag_covered_fraction": judge_domain_features["factuality_dag_covered_fraction"],
        "judge_requires_vertical_domain_guardrails": judge_domain_features["judge_requires_vertical_domain_guardrails"],
        "vertical_domain_guardrail_missing": judge_domain_features["vertical_domain_guardrail_missing"],
        "vertical_domain_guardrail_covered_fraction": judge_domain_features["vertical_domain_guardrail_covered_fraction"],
        "targeted_escalation_candidate_count": targeted_features["targeted_escalation_candidate_count"],
        "targeted_answer_claim_independence_required": targeted_features["targeted_answer_claim_independence_required"],
        "targeted_requires_cross_provider_verifier": targeted_features["targeted_requires_cross_provider_verifier"],
        "targeted_requires_new_profile_verifier": targeted_features["targeted_requires_new_profile_verifier"],
        "targeted_selected_new_provider_for_claim": targeted_features["targeted_selected_new_provider_for_claim"],
        "targeted_selected_new_profile_for_claim": targeted_features["targeted_selected_new_profile_for_claim"],
        "targeted_independence_model_selection_present": targeted_features["targeted_independence_model_selection_present"],
        "missing_coverage_count": _optional_int(judge.get("missing_coverage_count")),
        "contradiction_count": _optional_int(judge.get("contradiction_count")),
        "candidate_deduplication_duplicate_rate": dedupe_features["candidate_deduplication_duplicate_rate"],
        "candidate_deduplication_duplicate_candidate_count": dedupe_features["candidate_deduplication_duplicate_candidate_count"],
        "candidate_deduplication_high_duplicate_rate": dedupe_features["candidate_deduplication_high_duplicate_rate"],
        "prompt_budget_context_budget_enforced": prompt_features["prompt_budget_context_budget_enforced"],
        "prompt_budget_truncated_call_count": prompt_features["prompt_budget_truncated_call_count"],
        "prompt_budget_any_truncated": prompt_features["prompt_budget_any_truncated"],
        "prompt_budget_overflow_token_total": prompt_features["prompt_budget_overflow_token_total"],
        "synthesis_compression_enabled": synthesis_features["synthesis_compression_enabled"],
        "synthesis_omitted_candidate_count": synthesis_features["synthesis_omitted_candidate_count"],
        "trace_joined": bool(trace),
    }


def _shadow_bucket_summary(
    key: tuple[str, str, str, str],
    rows: Sequence[Mapping[str, Any]],
    *,
    min_examples: int,
) -> dict[str, Any]:
    policy_version_sha256, public_model, strategy, task_type = key
    bucket_id = sha256_text(
        json.dumps(
            {
                "policy_version_sha256": policy_version_sha256,
                "public_model": public_model,
                "strategy": strategy,
                "task_type": task_type,
            },
            sort_keys=True,
        )
    )[:16]
    agent_rows = [row for row in rows if row.get("agent_outcome_provided")]
    agent_tool_calls = sum(_optional_int(row.get("agent_tool_call_count")) or 0 for row in agent_rows)
    agent_tool_failures = sum(_optional_int(row.get("agent_tool_failure_count")) or 0 for row in agent_rows)
    agent_repair_loops = [_optional_int(row.get("agent_repair_loop_count")) for row in agent_rows]
    accepted_values = [_optional_bool(row.get("accepted")) for row in rows]
    agent_success_values = [_optional_bool(row.get("agent_task_success")) for row in agent_rows]
    verification_values = [_optional_bool(row.get("external_verification_passed")) for row in rows]
    diversity_satisfied_values = [_optional_bool(row.get("panel_provider_diversity_satisfied")) for row in rows]
    prompt_truncated_values = [_optional_bool(row.get("prompt_budget_any_truncated")) for row in rows]
    prompt_context_budget_values = [_optional_bool(row.get("prompt_budget_context_budget_enforced")) for row in rows]
    synthesis_compression_values = [_optional_bool(row.get("synthesis_compression_enabled")) for row in rows]
    dedupe_high_values = [_optional_bool(row.get("candidate_deduplication_high_duplicate_rate")) for row in rows]
    provider_fallback_enabled_values = [_optional_bool(row.get("provider_fallback_enabled")) for row in rows]
    provider_fallback_nonpanel_values = [_optional_bool(row.get("provider_fallback_has_nonpanel_candidate")) for row in rows]
    provider_fallback_low_availability_values = [_optional_bool(row.get("provider_fallback_low_top_availability")) for row in rows]
    provider_fallback_low_routing_values = [_optional_bool(row.get("provider_fallback_low_top_routing_score")) for row in rows]
    provider_fallback_context_compression_values = [_optional_bool(row.get("provider_fallback_context_compression_enabled")) for row in rows]
    fast_light_requested_values = [_optional_bool(row.get("fast_light_verify_requested")) for row in rows]
    fast_light_active_values = [_optional_bool(row.get("fast_light_verify_active")) for row in rows]
    answer_claim_consensus_values = [_optional_bool(row.get("judge_answer_claim_consensus_detected")) for row in rows]
    answer_claim_independent_consensus_values = [_optional_bool(row.get("judge_answer_claim_independent_consensus_detected")) for row in rows]
    answer_claim_numeric_equivalence_values = [_optional_bool(row.get("judge_answer_claim_numeric_equivalence_detected")) for row in rows]
    early_exit_answer_claim_values = [_optional_bool(row.get("early_exit_answer_claim_consensus_passed")) for row in rows]
    early_exit_independent_claim_values = [_optional_bool(row.get("early_exit_answer_claim_independent_detected")) for row in rows]
    calibration_delta_values = _numeric_values(rows, "judge_average_confidence_calibration_delta")
    overconfidence_risk_values = _numeric_values(rows, "judge_overconfidence_risk_rate")
    factuality_signal_values = [_optional_bool(row.get("factuality_signal")) for row in rows]
    vertical_domain_signal_values = [
        ((_optional_int(row.get("vertical_domain_signal_count")) or 0) > 0)
        for row in rows
    ]
    source_required_values = [_optional_bool(row.get("judge_requires_source_grounding")) for row in rows]
    source_grounded_values = [_optional_bool(row.get("judge_has_source_grounding_evidence")) for row in rows]
    factuality_source_missing_values = [_optional_bool(row.get("factuality_source_grounding_missing")) for row in rows]
    vertical_required_values = [_optional_bool(row.get("judge_requires_vertical_domain_guardrails")) for row in rows]
    vertical_missing_values = [_optional_bool(row.get("vertical_domain_guardrail_missing")) for row in rows]
    targeted_independence_required_values = [_optional_bool(row.get("targeted_answer_claim_independence_required")) for row in rows]
    targeted_cross_provider_required_values = [_optional_bool(row.get("targeted_requires_cross_provider_verifier")) for row in rows]
    targeted_new_profile_required_values = [_optional_bool(row.get("targeted_requires_new_profile_verifier")) for row in rows]
    targeted_cross_provider_selected_values = [_optional_bool(row.get("targeted_selected_new_provider_for_claim")) for row in rows]
    targeted_new_profile_selected_values = [_optional_bool(row.get("targeted_selected_new_profile_for_claim")) for row in rows]
    targeted_model_selection_values = [_optional_bool(row.get("targeted_independence_model_selection_present")) for row in rows]
    initial_resource_applicable_values = [_optional_bool(row.get("fusion_initial_resource_budget_applicable")) for row in rows]
    initial_resource_blocked_values = [_optional_bool(row.get("fusion_initial_resource_budget_blocked")) for row in rows]
    initial_cost_known_values = [_optional_bool(row.get("fusion_initial_cost_estimate_known")) for row in rows]
    initial_latency_known_values = [_optional_bool(row.get("fusion_initial_latency_estimate_known")) for row in rows]
    initial_cost_within_budget_values = [_optional_bool(row.get("fusion_initial_cost_within_request_budget")) for row in rows]
    initial_latency_within_deadline_values = [_optional_bool(row.get("fusion_initial_latency_within_request_deadline")) for row in rows]
    return {
        "bucket_id": bucket_id,
        "target": {
            "source_policy_version_sha256": policy_version_sha256,
            "public_model": public_model,
            "strategy": strategy,
            "task_type": task_type,
            "bucket_id": bucket_id,
        },
        "example_count": len(rows),
        "trace_joined_count": sum(1 for row in rows if row.get("trace_joined")),
        "evidence_state": "sufficient" if len(rows) >= min_examples else "insufficient",
        "metrics": {
            "score_count": _count_present(_numeric_values(rows, "score")),
            "average_score": _average(_numeric_values(rows, "score")),
            "reward_count": _count_present(_numeric_values(rows, "reward")),
            "average_reward": _average(_numeric_values(rows, "reward")),
            "accepted_rate": _true_rate(accepted_values),
            "rejected_rate": _false_rate(accepted_values),
            "external_verification_count": _count_present(verification_values),
            "external_verification_pass_rate": _true_rate(verification_values),
            "external_verification_failure_rate": _false_rate(verification_values),
            "agent_outcome_count": len(agent_rows),
            "agent_success_rate": _true_rate(agent_success_values),
            "agent_failure_rate": _false_rate(agent_success_values),
            "agent_tool_call_count": agent_tool_calls,
            "agent_tool_failure_count": agent_tool_failures,
            "agent_tool_failure_rate": None if agent_tool_calls <= 0 else round(agent_tool_failures / agent_tool_calls, 6),
            "average_agent_tool_failures": _average(_numeric_values(agent_rows, "agent_tool_failure_count")),
            "average_agent_repair_loops": _average([value for value in agent_repair_loops if value is not None]),
            "human_intervention_rate": _true_rate([_optional_bool(row.get("agent_human_intervention_required")) for row in agent_rows]),
            "average_provider_call_count": _average(_numeric_values(rows, "provider_call_count")),
            "average_latency_ms": _average(_numeric_values(rows, "latency_ms")),
            "p95_latency_ms": _percentile(_numeric_values(rows, "latency_ms"), 0.95),
            "average_cost_usd": _average(_numeric_values(rows, "actual_cost_usd")),
            "average_complexity": _average(_numeric_values(rows, "complexity")),
            "average_risk": _average(_numeric_values(rows, "risk")),
            "average_uncertainty": _average(_numeric_values(rows, "uncertainty")),
            "average_quality_target": _average(_numeric_values(rows, "quality_target")),
            "average_max_total_model_calls": _average(_numeric_values(rows, "max_total_model_calls")),
            "fast_light_verify_requested_rate": _true_rate(fast_light_requested_values),
            "fast_light_verify_active_rate": _true_rate(fast_light_active_values),
            "average_fusion_utility_score": _average(_numeric_values(rows, "fusion_utility_score")),
            "average_fusion_expected_quality_gain": _average(_numeric_values(rows, "fusion_expected_quality_gain")),
            "average_fusion_error_correlation_penalty": _average(_numeric_values(rows, "fusion_error_correlation_penalty")),
            "average_fusion_cost_penalty": _average(_numeric_values(rows, "fusion_cost_penalty")),
            "average_fusion_latency_penalty": _average(_numeric_values(rows, "fusion_latency_penalty")),
            "initial_fusion_resource_budget_applicable_rate": _true_rate(initial_resource_applicable_values),
            "initial_fusion_resource_budget_blocked_rate": _true_rate(initial_resource_blocked_values),
            "initial_fusion_cost_estimate_known_rate": _true_rate(initial_cost_known_values),
            "initial_fusion_latency_estimate_known_rate": _true_rate(initial_latency_known_values),
            "initial_fusion_cost_within_request_budget_rate": _true_rate(initial_cost_within_budget_values),
            "initial_fusion_latency_within_request_deadline_rate": _true_rate(initial_latency_within_deadline_values),
            "average_panel_provider_diversity": _average(_numeric_values(rows, "panel_provider_diversity")),
            "average_panel_api_format_diversity": _average(_numeric_values(rows, "panel_api_format_diversity")),
            "average_panel_capability_coverage": _average(_numeric_values(rows, "panel_capability_coverage")),
            "average_panel_capability_complementarity": _average(_numeric_values(rows, "panel_capability_complementarity")),
            "average_panel_estimated_error_correlation": _average(_numeric_values(rows, "panel_estimated_error_correlation")),
            "provider_diversity_satisfied_rate": _true_rate(diversity_satisfied_values),
            "provider_fallback_enabled_rate": _true_rate(provider_fallback_enabled_values),
            "average_provider_fallback_pool_count": _average(_numeric_values(rows, "provider_fallback_pool_count")),
            "average_provider_fallback_top_routing_score": _average(_numeric_values(rows, "provider_fallback_top_routing_score")),
            "average_provider_fallback_top_availability_score": _average(_numeric_values(rows, "provider_fallback_top_availability_score")),
            "average_provider_fallback_top_latency_score": _average(_numeric_values(rows, "provider_fallback_top_latency_score")),
            "average_provider_fallback_top_cost_score": _average(_numeric_values(rows, "provider_fallback_top_cost_score")),
            "average_provider_fallback_average_routing_score": _average(_numeric_values(rows, "provider_fallback_average_routing_score")),
            "average_provider_fallback_average_availability_score": _average(_numeric_values(rows, "provider_fallback_average_availability_score")),
            "average_provider_fallback_selected_panel_count": _average(_numeric_values(rows, "provider_fallback_selected_panel_count")),
            "average_provider_fallback_nonpanel_count": _average(_numeric_values(rows, "provider_fallback_nonpanel_count")),
            "average_provider_fallback_api_format_count": _average(_numeric_values(rows, "provider_fallback_api_format_count")),
            "average_provider_fallback_provider_hash_count": _average(_numeric_values(rows, "provider_fallback_provider_hash_count")),
            "provider_fallback_nonpanel_available_rate": _true_rate(provider_fallback_nonpanel_values),
            "provider_fallback_low_top_availability_rate": _true_rate(provider_fallback_low_availability_values),
            "provider_fallback_low_top_routing_rate": _true_rate(provider_fallback_low_routing_values),
            "provider_fallback_context_compression_rate": _true_rate(provider_fallback_context_compression_values),
            "average_judge_answer_claim_cluster_count": _average(_numeric_values(rows, "judge_answer_claim_cluster_count")),
            "average_judge_largest_answer_claim_cluster_size": _average(_numeric_values(rows, "judge_largest_answer_claim_cluster_size")),
            "average_judge_largest_answer_claim_support_fraction": _average(_numeric_values(rows, "judge_largest_answer_claim_support_fraction")),
            "average_judge_largest_answer_claim_unique_profile_count": _average(_numeric_values(rows, "judge_largest_answer_claim_unique_profile_count")),
            "average_judge_largest_answer_claim_unique_provider_count": _average(_numeric_values(rows, "judge_largest_answer_claim_unique_provider_count")),
            "judge_answer_claim_consensus_rate": _true_rate(answer_claim_consensus_values),
            "judge_answer_claim_independent_consensus_rate": _true_rate(answer_claim_independent_consensus_values),
            "judge_answer_claim_numeric_equivalence_rate": _true_rate(answer_claim_numeric_equivalence_values),
            "average_judge_confidence_calibration_candidate_count": _average(_numeric_values(rows, "judge_confidence_calibration_candidate_count")),
            "average_judge_raw_confidence": _average(_numeric_values(rows, "judge_average_raw_confidence")),
            "average_judge_calibrated_confidence": _average(_numeric_values(rows, "judge_average_calibrated_confidence")),
            "average_judge_confidence_calibration_delta": _average(calibration_delta_values),
            "average_judge_overconfidence_risk_rate": _average(overconfidence_risk_values),
            "average_judge_confidence_calibration_penalty_count": _average(_numeric_values(rows, "judge_confidence_calibration_penalty_count")),
            "average_judge_confidence_calibration_credit_count": _average(_numeric_values(rows, "judge_confidence_calibration_credit_count")),
            "average_early_exit_best_candidate_confidence": _average(_numeric_values(rows, "early_exit_best_candidate_confidence")),
            "average_early_exit_best_candidate_calibrated_confidence": _average(_numeric_values(rows, "early_exit_best_candidate_calibrated_confidence")),
            "early_exit_answer_claim_consensus_rate": _true_rate(early_exit_answer_claim_values),
            "early_exit_answer_claim_independent_consensus_rate": _true_rate(early_exit_independent_claim_values),
            "average_early_exit_answer_claim_support_fraction": _average(_numeric_values(rows, "early_exit_answer_claim_support_fraction")),
            "average_early_exit_answer_claim_unique_profile_count": _average(_numeric_values(rows, "early_exit_answer_claim_unique_profile_count")),
            "average_early_exit_answer_claim_unique_provider_count": _average(_numeric_values(rows, "early_exit_answer_claim_unique_provider_count")),
            "factuality_signal_rate": _true_rate(factuality_signal_values),
            "vertical_domain_signal_rate": _true_rate(vertical_domain_signal_values),
            "source_grounding_required_rate": _true_rate(source_required_values),
            "source_grounding_evidence_rate": _true_rate(source_grounded_values),
            "factuality_source_grounding_missing_rate": _true_rate(factuality_source_missing_values),
            "average_source_grounding_evidence_count": _average(_numeric_values(rows, "judge_source_grounding_evidence_count")),
            "average_factuality_dag_covered_fraction": _average(_numeric_values(rows, "factuality_dag_covered_fraction")),
            "vertical_domain_guardrail_required_rate": _true_rate(vertical_required_values),
            "vertical_domain_guardrail_missing_rate": _true_rate(vertical_missing_values),
            "average_vertical_domain_guardrail_covered_fraction": _average(_numeric_values(rows, "vertical_domain_guardrail_covered_fraction")),
            "average_targeted_escalation_candidate_count": _average(_numeric_values(rows, "targeted_escalation_candidate_count")),
            "targeted_answer_claim_independence_requirement_rate": _true_rate(targeted_independence_required_values),
            "targeted_cross_provider_verifier_required_rate": _true_rate(targeted_cross_provider_required_values),
            "targeted_new_profile_verifier_required_rate": _true_rate(targeted_new_profile_required_values),
            "targeted_cross_provider_verifier_selected_rate": _true_rate(targeted_cross_provider_selected_values),
            "targeted_new_profile_verifier_selected_rate": _true_rate(targeted_new_profile_selected_values),
            "targeted_independence_model_selection_rate": _true_rate(targeted_model_selection_values),
            "average_missing_coverage_count": _average(_numeric_values(rows, "missing_coverage_count")),
            "average_contradiction_count": _average(_numeric_values(rows, "contradiction_count")),
            "average_candidate_deduplication_duplicate_rate": _average(_numeric_values(rows, "candidate_deduplication_duplicate_rate")),
            "average_candidate_deduplication_duplicate_candidate_count": _average(_numeric_values(rows, "candidate_deduplication_duplicate_candidate_count")),
            "candidate_deduplication_high_duplicate_rate": _true_rate(dedupe_high_values),
            "average_prompt_budget_truncated_call_count": _average(_numeric_values(rows, "prompt_budget_truncated_call_count")),
            "prompt_budget_truncation_rate": _true_rate(prompt_truncated_values),
            "prompt_context_budget_enforced_rate": _true_rate(prompt_context_budget_values),
            "average_prompt_budget_overflow_tokens": _average(_numeric_values(rows, "prompt_budget_overflow_token_total")),
            "synthesis_compression_rate": _true_rate(synthesis_compression_values),
            "average_synthesis_omitted_candidate_count": _average(_numeric_values(rows, "synthesis_omitted_candidate_count")),
        },
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_model_names_persisted": False,
        "raw_agent_trace_persisted": False,
        "raw_tool_outputs_persisted": False,
    }


def _shadow_patch_candidates(bucket: Mapping[str, Any], *, min_examples: int) -> list[dict[str, Any]]:
    metrics = bucket.get("metrics") if isinstance(bucket.get("metrics"), Mapping) else {}
    target = bucket.get("target") if isinstance(bucket.get("target"), Mapping) else {}
    public_model = str(target.get("public_model") or "")
    task_type = str(target.get("task_type") or "")
    strategy = str(target.get("strategy") or "")
    count = int(bucket.get("example_count") or 0)
    enough = count >= min_examples
    priority_suffix = "high" if enough else "medium"
    candidates: list[dict[str, Any]] = []
    if not enough:
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="keep_current_policy_collect_more_bucket_evidence",
                priority="medium",
                reason="bucket_below_min_examples",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={"automatic_policy_change": False, "min_examples_needed": min_examples},
            )
        )
    agent_failure_rate = _optional_float(metrics.get("agent_failure_rate"))
    tool_failure_rate = _optional_float(metrics.get("agent_tool_failure_rate"))
    average_repair_loops = _optional_float(metrics.get("average_agent_repair_loops"))
    if (
        int(metrics.get("agent_outcome_count") or 0) > 0
        and (
            (agent_failure_rate is not None and agent_failure_rate >= 0.3)
            or (tool_failure_rate is not None and tool_failure_rate >= 0.15)
            or (average_repair_loops is not None and average_repair_loops >= 1.0)
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="increase_agentic_verification_and_escalation",
                priority=priority_suffix,
                reason="agent_outcomes_show_tool_or_repair_failures",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "quality_target_delta": 0.08,
                    "max_total_model_calls_delta": 2,
                    "require_independent_tool_plan_check": True,
                    "targeted_escalation_enabled": True,
                    "tool_failure_escalation_enabled": True,
                },
            )
        )
    average_score = _optional_float(metrics.get("average_score"))
    accepted_rate = _optional_float(metrics.get("accepted_rate"))
    if (average_score is not None and average_score < 0.2) or (accepted_rate is not None and accepted_rate < 0.6):
        direct_like = "direct" in strategy or strategy.startswith("fast")
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="lower_fusion_activation_threshold" if direct_like else "raise_quality_target_for_task_type",
                priority=priority_suffix,
                reason="low_score_or_acceptance_rate",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta=(
                    {
                        "fusion_activation_threshold_delta": -0.08,
                        "min_judge_candidate_count_delta": 1,
                        "targeted_escalation_enabled": True,
                    }
                    if direct_like
                    else {
                        "quality_target_delta": 0.06,
                        "min_judge_candidate_count_delta": 1,
                        "targeted_escalation_enabled": True,
                    }
                ),
            )
        )
    average_reward = _optional_float(metrics.get("average_reward"))
    poor_outcome = (
        (average_reward is not None and average_reward < 0.25)
        or (average_score is not None and average_score < 0.2)
        or (accepted_rate is not None and accepted_rate < 0.6)
    )
    factuality_signal_rate = _optional_float(metrics.get("factuality_signal_rate"))
    factuality_source_missing_rate = _optional_float(metrics.get("factuality_source_grounding_missing_rate"))
    source_grounding_required_rate = _optional_float(metrics.get("source_grounding_required_rate"))
    if (
        poor_outcome
        and (
            (factuality_signal_rate is not None and factuality_signal_rate >= 0.3)
            or (source_grounding_required_rate is not None and source_grounding_required_rate >= 0.3)
        )
        and (factuality_source_missing_rate is None or factuality_source_missing_rate >= 0.3)
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="increase_factuality_source_grounding_verification",
                priority=priority_suffix,
                reason="low_reward_with_missing_factuality_source_grounding",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "require_source_grounding_for_factuality_tasks": True,
                    "targeted_escalation_enabled": True,
                    "targeted_factuality_source_grounding_check": True,
                    "prefer_critic_with_current_information_or_structured_evidence": True,
                    "must_label_unverified_claims": True,
                    "automatic_policy_change": False,
                },
            )
        )
    vertical_signal_rate = _optional_float(metrics.get("vertical_domain_signal_rate"))
    vertical_guardrail_required_rate = _optional_float(metrics.get("vertical_domain_guardrail_required_rate"))
    vertical_guardrail_missing_rate = _optional_float(metrics.get("vertical_domain_guardrail_missing_rate"))
    if (
        poor_outcome
        and (
            (vertical_signal_rate is not None and vertical_signal_rate >= 0.3)
            or (vertical_guardrail_required_rate is not None and vertical_guardrail_required_rate >= 0.3)
        )
        and (vertical_guardrail_missing_rate is None or vertical_guardrail_missing_rate >= 0.3)
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="increase_vertical_domain_guardrail_specialist_check",
                priority=priority_suffix,
                reason="low_reward_with_missing_vertical_domain_guardrails",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "require_vertical_domain_guardrail_nodes": True,
                    "prefer_domain_specialist_for_vertical_tasks": True,
                    "targeted_escalation_enabled": True,
                    "targeted_vertical_domain_guardrail_check": True,
                    "must_state_scope_assumptions_and_uncertainty": True,
                    "automatic_policy_change": False,
                },
            )
        )
    average_risk = _optional_float(metrics.get("average_risk"))
    average_uncertainty = _optional_float(metrics.get("average_uncertainty"))
    fast_light_active_rate = _optional_float(metrics.get("fast_light_verify_active_rate"))
    if (
        poor_outcome
        and public_model == "axio-fast"
        and strategy != "fast_light_verify"
        and (fast_light_active_rate is None or fast_light_active_rate < 0.5)
        and (
            (average_uncertainty is not None and average_uncertainty >= 0.45)
            or (average_risk is not None and average_risk >= 0.30)
            or task_type in {"agentic_tool_calling", "code", "logic_reasoning", "math_reasoning"}
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="enable_bounded_fast_light_verify_for_uncertain_fast_tasks",
                priority=priority_suffix,
                reason="axio_fast_low_reward_on_uncertain_or_risky_direct_route",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "fast_light_verify_enabled": True,
                    "max_models_min": 2,
                    "max_depth_delta": 0,
                    "min_judge_candidate_count_delta": 1,
                    "preserve_latency_multiplier_guard": 3.0,
                    "automatic_policy_change": False,
                },
            )
        )
    answer_claim_consensus_rate = _optional_float(metrics.get("judge_answer_claim_consensus_rate"))
    answer_claim_independent_consensus_rate = _optional_float(metrics.get("judge_answer_claim_independent_consensus_rate"))
    average_claim_support = _optional_float(metrics.get("average_judge_largest_answer_claim_support_fraction"))
    average_claim_cluster_size = _optional_float(metrics.get("average_judge_largest_answer_claim_cluster_size"))
    average_claim_unique_profile_count = _optional_float(metrics.get("average_judge_largest_answer_claim_unique_profile_count"))
    average_claim_unique_provider_count = _optional_float(metrics.get("average_judge_largest_answer_claim_unique_provider_count"))
    average_missing_coverage = _optional_float(metrics.get("average_missing_coverage_count"))
    average_contradictions = _optional_float(metrics.get("average_contradiction_count"))
    average_calibration_delta = _optional_float(metrics.get("average_judge_confidence_calibration_delta"))
    average_overconfidence_risk_rate = _optional_float(metrics.get("average_judge_overconfidence_risk_rate"))
    targeted_independence_requirement_rate = _optional_float(metrics.get("targeted_answer_claim_independence_requirement_rate"))
    targeted_cross_provider_required_rate = _optional_float(metrics.get("targeted_cross_provider_verifier_required_rate"))
    targeted_new_profile_required_rate = _optional_float(metrics.get("targeted_new_profile_verifier_required_rate"))
    targeted_cross_provider_selected_rate = _optional_float(metrics.get("targeted_cross_provider_verifier_selected_rate"))
    targeted_new_profile_selected_rate = _optional_float(metrics.get("targeted_new_profile_verifier_selected_rate"))
    if (
        poor_outcome
        and (
            (average_overconfidence_risk_rate is not None and average_overconfidence_risk_rate >= 0.30)
            or (average_calibration_delta is not None and average_calibration_delta <= -0.06)
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="tighten_local_judge_confidence_calibration",
                priority=priority_suffix,
                reason="low_reward_with_overconfidence_risk_in_judge_calibration",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "use_calibrated_confidence_for_local_ranking": True,
                    "penalize_high_confidence_without_evidence": True,
                    "cap_unsupported_factuality_confidence": True,
                    "require_source_or_guardrail_receipts_for_high_risk_tasks": True,
                    "automatic_policy_change": False,
                },
            )
        )
    if (
        poor_outcome
        and (
            (answer_claim_consensus_rate is not None and answer_claim_consensus_rate < 0.5)
            or (answer_claim_independent_consensus_rate is not None and answer_claim_independent_consensus_rate < 0.5)
            or (average_claim_support is not None and average_claim_support < 0.67)
            or (average_claim_cluster_size is not None and average_claim_cluster_size < 2.0)
            or (average_claim_unique_profile_count is not None and average_claim_unique_profile_count < 2.0)
            or (average_claim_unique_provider_count is not None and average_claim_unique_provider_count < 1.0)
            or (average_missing_coverage is not None and average_missing_coverage >= 1.0)
            or (average_contradictions is not None and average_contradictions >= 1.0)
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="increase_independent_answer_claim_verification",
                priority=priority_suffix,
                reason="low_reward_without_sufficient_answer_claim_consensus",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "require_answer_claim_cluster_check": True,
                    "require_independent_answer_claim_support": True,
                    "min_independent_claim_support_delta": 1,
                    "prefer_cross_provider_independent_solver": True,
                    "targeted_escalation_enabled": True,
                    "automatic_policy_change": False,
                },
            )
        )
    if (
        poor_outcome
        and targeted_independence_requirement_rate is not None
        and targeted_independence_requirement_rate >= 0.30
        and (
            (
                targeted_cross_provider_required_rate is not None
                and targeted_cross_provider_required_rate >= 0.30
                and (targeted_cross_provider_selected_rate is None or targeted_cross_provider_selected_rate < 0.80)
            )
            or (
                targeted_new_profile_required_rate is not None
                and targeted_new_profile_required_rate >= 0.30
                and (targeted_new_profile_selected_rate is None or targeted_new_profile_selected_rate < 0.80)
            )
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="strengthen_answer_claim_independence_escalation_routing",
                priority=priority_suffix,
                reason="same_source_answer_claim_consensus_not_repaired_by_independent_verifier",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "targeted_escalation_enabled": True,
                    "route_independent_answer_claim_checks_to_new_profile": True,
                    "prefer_cross_provider_independent_verifier_when_provider_pool_allows": True,
                    "require_answer_claim_independence_receipts": True,
                    "automatic_policy_change": False,
                },
            )
        )
    average_error_correlation = _optional_float(metrics.get("average_panel_estimated_error_correlation"))
    average_complementarity = _optional_float(metrics.get("average_panel_capability_complementarity"))
    diversity_satisfied_rate = _optional_float(metrics.get("provider_diversity_satisfied_rate"))
    if (
        poor_outcome
        and average_error_correlation is not None
        and average_error_correlation >= 0.72
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="increase_panel_provider_diversity_and_complementarity",
                priority=priority_suffix,
                reason="low_reward_with_high_estimated_error_correlation",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "provider_count_target_delta": 1 if diversity_satisfied_rate is None or diversity_satisfied_rate < 0.8 else 0,
                    "capability_complementarity_min_delta": 0.08 if average_complementarity is None or average_complementarity < 0.45 else 0.03,
                    "error_correlation_penalty_weight_delta": 0.02,
                    "require_cross_provider_independent_solver": True,
                    "prefer_api_format_diversity": True,
                    "automatic_policy_change": False,
                },
            )
        )
    average_fallback_top_availability = _optional_float(metrics.get("average_provider_fallback_top_availability_score"))
    average_fallback_top_routing = _optional_float(metrics.get("average_provider_fallback_top_routing_score"))
    average_fallback_nonpanel_count = _optional_float(metrics.get("average_provider_fallback_nonpanel_count"))
    average_fallback_api_format_count = _optional_float(metrics.get("average_provider_fallback_api_format_count"))
    fallback_low_availability_rate = _optional_float(metrics.get("provider_fallback_low_top_availability_rate"))
    fallback_low_routing_rate = _optional_float(metrics.get("provider_fallback_low_top_routing_rate"))
    if (
        poor_outcome
        and (
            (average_fallback_top_availability is not None and average_fallback_top_availability < 0.65)
            or (average_fallback_top_routing is not None and average_fallback_top_routing < 0.5)
            or (fallback_low_availability_rate is not None and fallback_low_availability_rate >= 0.3)
            or (fallback_low_routing_rate is not None and fallback_low_routing_rate >= 0.3)
            or (average_fallback_nonpanel_count is not None and average_fallback_nonpanel_count < 1.0)
            or (average_fallback_api_format_count is not None and average_fallback_api_format_count < 2.0)
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="expand_provider_fallback_pool_or_refresh_live_probe_registry",
                priority=priority_suffix,
                reason="low_reward_with_weak_provider_fallback_pool",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "refresh_live_probe_registry": True,
                    "prefer_available_cross_provider_fallback": True,
                    "min_nonpanel_fallback_candidates_delta": 1,
                    "prefer_api_format_diversity": True,
                    "probe_availability_before_expensive_campaign": True,
                    "circuit_breaker_probe_refresh_required": True,
                    "automatic_policy_change": False,
                },
            )
        )
    average_duplicate_rate = _optional_float(metrics.get("average_candidate_deduplication_duplicate_rate"))
    high_duplicate_rate = _optional_float(metrics.get("candidate_deduplication_high_duplicate_rate"))
    if (
        poor_outcome
        and (
            (average_duplicate_rate is not None and average_duplicate_rate >= 0.34)
            or (high_duplicate_rate is not None and high_duplicate_rate >= 0.3)
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="reduce_duplicate_panel_and_increase_independence",
                priority=priority_suffix,
                reason="low_reward_with_high_candidate_deduplication",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "dedupe_aware_panel_selection": True,
                    "prefer_cross_provider_independent_solver": True,
                    "prefer_api_format_diversity": True,
                    "reduce_panel_width_when_duplicate_rate_high": True,
                    "capability_complementarity_min_delta": 0.05,
                    "automatic_policy_change": False,
                },
            )
        )
    verification_failure_rate = _optional_float(metrics.get("external_verification_failure_rate"))
    if verification_failure_rate is not None and verification_failure_rate >= 0.3:
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="increase_external_verification_or_escalation",
                priority=priority_suffix,
                reason="external_verification_failure_rate_high",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "quality_target_delta": 0.05,
                    "verification_required": True,
                    "targeted_escalation_enabled": True,
                },
            )
        )
    average_provider_calls = _optional_float(metrics.get("average_provider_call_count"))
    average_latency = _optional_float(metrics.get("average_latency_ms"))
    average_prompt_truncated = _optional_float(metrics.get("average_prompt_budget_truncated_call_count"))
    prompt_truncation_rate = _optional_float(metrics.get("prompt_budget_truncation_rate"))
    average_overflow = _optional_float(metrics.get("average_prompt_budget_overflow_tokens"))
    if (
        poor_outcome
        and (
            (average_prompt_truncated is not None and average_prompt_truncated >= 1.0)
            or (prompt_truncation_rate is not None and prompt_truncation_rate >= 0.3)
            or (average_overflow is not None and average_overflow >= 256.0)
        )
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="tighten_prompt_budget_and_rank_first_compression",
                priority=priority_suffix,
                reason="low_reward_with_context_budget_truncation",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "rank_first_candidate_compression": True,
                    "preserve_user_constraints_before_candidate_summaries": True,
                    "reduce_panel_width_when_context_truncated": True,
                    "max_full_candidate_count_delta": -1,
                    "prompt_budget_overflow_replay_required": True,
                    "automatic_policy_change": False,
                },
            )
        )
    if (
        average_reward is not None
        and average_reward >= 0.65
        and accepted_rate is not None
        and accepted_rate >= 0.8
        and ((average_provider_calls is not None and average_provider_calls >= 5.0) or (average_latency is not None and average_latency >= 15000.0))
        and task_type != "agentic_tool_calling"
    ):
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="decrease_max_model_calls_or_enable_early_exit",
                priority="low" if enough else "medium",
                reason="quality_good_but_cost_or_latency_high",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={
                    "max_total_model_calls_delta": -1,
                    "early_exit_threshold_delta": -0.03,
                    "rank_first_candidate_compression": True,
                },
            )
        )
    if not candidates and enough:
        candidates.append(
            _shadow_patch_candidate(
                target=target,
                action="keep_current_policy_with_shadow_ablation",
                priority="low",
                reason="bucket_signal_stable_without_negative_trigger",
                evidence=_shadow_patch_evidence(bucket, min_examples=min_examples),
                suggested_policy_delta={"automatic_policy_change": False},
            )
        )
    return candidates


def _shadow_patch_candidate(
    *,
    target: Mapping[str, Any],
    action: str,
    priority: str,
    reason: str,
    evidence: Mapping[str, Any],
    suggested_policy_delta: Mapping[str, Any],
) -> dict[str, Any]:
    safe_target = {
        "public_model": str(target.get("public_model") or "unknown"),
        "strategy": str(target.get("strategy") or "unknown"),
        "task_type": str(target.get("task_type") or "unknown"),
        "bucket_id": str(target.get("bucket_id") or sha256_text("unknown")[:16]),
    }
    patch_id = sha256_text(json.dumps({"target": safe_target, "action": action, "reason": reason}, sort_keys=True))[:32]
    return {
        "patch_id": patch_id,
        "shadow_only": True,
        "safe_to_apply_automatically": False,
        "target": safe_target,
        "action": action,
        "priority": priority,
        "reason": reason,
        "evidence": dict(evidence),
        "suggested_policy_delta": dict(suggested_policy_delta),
        "validation_required": [
            "offline_replay_against_held_out_feedback",
            "cost_latency_regression_check",
            "benchmark_training_contamination_audit",
        ],
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_model_names_persisted": False,
        "raw_agent_trace_persisted": False,
        "raw_tool_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _shadow_patch_evidence(bucket: Mapping[str, Any], *, min_examples: int) -> dict[str, Any]:
    metrics = bucket.get("metrics") if isinstance(bucket.get("metrics"), Mapping) else {}
    return {
        "example_count": int(bucket.get("example_count") or 0),
        "min_examples": min_examples,
        "evidence_state": str(bucket.get("evidence_state") or "unknown"),
        "average_score": metrics.get("average_score"),
        "accepted_rate": metrics.get("accepted_rate"),
        "average_reward": metrics.get("average_reward"),
        "external_verification_failure_rate": metrics.get("external_verification_failure_rate"),
        "agent_outcome_count": metrics.get("agent_outcome_count"),
        "agent_failure_rate": metrics.get("agent_failure_rate"),
        "agent_tool_failure_rate": metrics.get("agent_tool_failure_rate"),
        "average_agent_repair_loops": metrics.get("average_agent_repair_loops"),
        "average_provider_call_count": metrics.get("average_provider_call_count"),
        "average_latency_ms": metrics.get("average_latency_ms"),
        "average_cost_usd": metrics.get("average_cost_usd"),
        "fast_light_verify_requested_rate": metrics.get("fast_light_verify_requested_rate"),
        "fast_light_verify_active_rate": metrics.get("fast_light_verify_active_rate"),
        "average_fusion_utility_score": metrics.get("average_fusion_utility_score"),
        "average_fusion_expected_quality_gain": metrics.get("average_fusion_expected_quality_gain"),
        "average_fusion_error_correlation_penalty": metrics.get("average_fusion_error_correlation_penalty"),
        "average_panel_provider_diversity": metrics.get("average_panel_provider_diversity"),
        "average_panel_api_format_diversity": metrics.get("average_panel_api_format_diversity"),
        "average_panel_capability_complementarity": metrics.get("average_panel_capability_complementarity"),
        "average_panel_estimated_error_correlation": metrics.get("average_panel_estimated_error_correlation"),
        "provider_diversity_satisfied_rate": metrics.get("provider_diversity_satisfied_rate"),
        "provider_fallback_enabled_rate": metrics.get("provider_fallback_enabled_rate"),
        "average_provider_fallback_pool_count": metrics.get("average_provider_fallback_pool_count"),
        "average_provider_fallback_top_routing_score": metrics.get("average_provider_fallback_top_routing_score"),
        "average_provider_fallback_top_availability_score": metrics.get("average_provider_fallback_top_availability_score"),
        "average_provider_fallback_top_latency_score": metrics.get("average_provider_fallback_top_latency_score"),
        "average_provider_fallback_top_cost_score": metrics.get("average_provider_fallback_top_cost_score"),
        "average_provider_fallback_average_routing_score": metrics.get("average_provider_fallback_average_routing_score"),
        "average_provider_fallback_average_availability_score": metrics.get("average_provider_fallback_average_availability_score"),
        "average_provider_fallback_nonpanel_count": metrics.get("average_provider_fallback_nonpanel_count"),
        "average_provider_fallback_api_format_count": metrics.get("average_provider_fallback_api_format_count"),
        "provider_fallback_nonpanel_available_rate": metrics.get("provider_fallback_nonpanel_available_rate"),
        "provider_fallback_low_top_availability_rate": metrics.get("provider_fallback_low_top_availability_rate"),
        "provider_fallback_low_top_routing_rate": metrics.get("provider_fallback_low_top_routing_rate"),
        "average_judge_answer_claim_cluster_count": metrics.get("average_judge_answer_claim_cluster_count"),
        "average_judge_largest_answer_claim_cluster_size": metrics.get("average_judge_largest_answer_claim_cluster_size"),
        "average_judge_largest_answer_claim_support_fraction": metrics.get("average_judge_largest_answer_claim_support_fraction"),
        "judge_answer_claim_consensus_rate": metrics.get("judge_answer_claim_consensus_rate"),
        "factuality_signal_rate": metrics.get("factuality_signal_rate"),
        "source_grounding_required_rate": metrics.get("source_grounding_required_rate"),
        "source_grounding_evidence_rate": metrics.get("source_grounding_evidence_rate"),
        "factuality_source_grounding_missing_rate": metrics.get("factuality_source_grounding_missing_rate"),
        "average_factuality_dag_covered_fraction": metrics.get("average_factuality_dag_covered_fraction"),
        "vertical_domain_signal_rate": metrics.get("vertical_domain_signal_rate"),
        "vertical_domain_guardrail_required_rate": metrics.get("vertical_domain_guardrail_required_rate"),
        "vertical_domain_guardrail_missing_rate": metrics.get("vertical_domain_guardrail_missing_rate"),
        "average_vertical_domain_guardrail_covered_fraction": metrics.get("average_vertical_domain_guardrail_covered_fraction"),
        "average_missing_coverage_count": metrics.get("average_missing_coverage_count"),
        "average_contradiction_count": metrics.get("average_contradiction_count"),
        "average_prompt_budget_truncated_call_count": metrics.get("average_prompt_budget_truncated_call_count"),
        "prompt_budget_truncation_rate": metrics.get("prompt_budget_truncation_rate"),
        "average_prompt_budget_overflow_tokens": metrics.get("average_prompt_budget_overflow_tokens"),
        "synthesis_compression_rate": metrics.get("synthesis_compression_rate"),
        "average_synthesis_omitted_candidate_count": metrics.get("average_synthesis_omitted_candidate_count"),
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_provider_output_persisted": False,
        "raw_agent_trace_persisted": False,
        "raw_tool_outputs_persisted": False,
    }


def _safe_label(value: Any, *, default: str = "", limit: int = 80) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return text[:limit]


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _numeric_values(rows: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    values = []
    for row in rows:
        number = _optional_float(row.get(key))
        if number is not None:
            values.append(number)
    return values


def _count_present(values: Sequence[Any]) -> int:
    return sum(1 for value in values if value is not None)


def _true_rate(values: Sequence[bool | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return round(sum(1 for value in present if value is True) / len(present), 6)


def _false_rate(values: Sequence[bool | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return round(sum(1 for value in present if value is False) / len(present), 6)


def _average(values: Sequence[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 6)


def _percentile(values: Sequence[float | int | None], q: float) -> float | None:
    present = sorted(float(value) for value in values if value is not None)
    if not present:
        return None
    if len(present) == 1:
        return round(present[0], 6)
    index = int(round((len(present) - 1) * max(0.0, min(1.0, q))))
    return round(present[index], 6)


def _benchmark_artifact_hashes(payloads: Sequence[Mapping[str, Any]]) -> set[str]:
    hashes: set[str] = set()
    for run in _benchmark_runs_from_payloads(payloads):
        _collect_case_hashes(run, hashes)
    return hashes


def _benchmark_runs_from_payloads(payloads: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    runs = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        if isinstance(payload.get("case_results"), list):
            runs.append(payload)
        if isinstance(payload.get("runs"), list):
            runs.extend(row for row in payload["runs"] if isinstance(row, Mapping))
    return runs


def _collect_case_hashes(run: Mapping[str, Any], target: set[str]) -> None:
    for key in (
        "case_id",
        "case_hash",
        "question_sha256",
        "input_sha256",
        "reference_sha256",
        "answer_sha256",
        "prediction_sha256",
        "output_sha256",
    ):
        value = run.get(key)
        if _looks_like_sha256(value):
            target.add(str(value).lower())
    rows = run.get("case_results") if isinstance(run.get("case_results"), list) else []
    for row in rows:
        if isinstance(row, Mapping):
            _collect_case_hashes(row, target)


def _learning_artifact_hashes(
    *,
    training_payloads: Sequence[Mapping[str, Any]],
    learning_reports: Sequence[Mapping[str, Any]],
    feedback_rows: Sequence[Mapping[str, Any]],
    trace_rows: Sequence[Mapping[str, Any]],
) -> set[str]:
    hashes: set[str] = set()
    for payload in training_payloads:
        _collect_sha256_values(payload, hashes)
        for example in payload.get("router_policy_examples", []) if isinstance(payload.get("router_policy_examples"), list) else []:
            if isinstance(example, Mapping):
                _collect_training_example_join_hashes(example, hashes)
    for payload in learning_reports:
        _collect_sha256_values(payload, hashes)
    for row in feedback_rows:
        _collect_sha256_values(row, hashes)
        response_id = str(row.get("response_id") or "")
        fingerprint = str(row.get("request_fingerprint") or "")
        if response_id:
            hashes.add(sha256_text(response_id))
        if fingerprint:
            hashes.add(sha256_text(fingerprint))
    for row in trace_rows:
        _collect_sha256_values(row, hashes)
        join_key = row.get("feedback_join_key") if isinstance(row.get("feedback_join_key"), Mapping) else {}
        response_id = str(join_key.get("response_id") or row.get("response_id") or "")
        fingerprint = str(join_key.get("request_fingerprint") or "")
        if response_id:
            hashes.add(sha256_text(response_id))
        if fingerprint:
            hashes.add(sha256_text(fingerprint))
    return hashes


def _collect_training_example_join_hashes(example: Mapping[str, Any], target: set[str]) -> None:
    for key in ("request_fingerprint_sha256", "response_id_sha256"):
        value = example.get(key)
        if _looks_like_sha256(value):
            target.add(str(value).lower())


def _collect_sha256_values(value: Any, target: set[str]) -> None:
    if isinstance(value, Mapping):
        for raw in value.values():
            _collect_sha256_values(raw, target)
    elif isinstance(value, list):
        for item in value:
            _collect_sha256_values(item, target)
    elif _looks_like_sha256(value):
        target.add(str(value).lower())


def _training_contract_findings(
    *,
    training_payloads: Sequence[Mapping[str, Any]],
    learning_reports: Sequence[Mapping[str, Any]],
    calibrations: Sequence[Mapping[str, Any]],
    allow_aggregate_benchmark_calibration: bool,
) -> list[dict[str, Any]]:
    findings = []
    for index, payload in enumerate(training_payloads):
        contract = payload.get("dataset_contract") if isinstance(payload.get("dataset_contract"), Mapping) else {}
        if contract.get("benchmark_labels_used_for_training") is True:
            findings.append(
                {
                    "kind": "benchmark_labels_marked_used_for_training",
                    "severity": "blocker",
                    "artifact_kind": "training_dataset",
                    "artifact_index": index,
                }
            )
        if contract.get("not_for_final_benchmark_claims") is not True:
            findings.append(
                {
                    "kind": "training_dataset_not_marked_excluded_from_final_claims",
                    "severity": "warning",
                    "artifact_kind": "training_dataset",
                    "artifact_index": index,
                }
            )
        if _contains_true_raw_persisted_flag(payload):
            findings.append(
                {
                    "kind": "raw_content_persisted_flag_detected",
                    "severity": "blocker",
                    "artifact_kind": "training_dataset",
                    "artifact_index": index,
                }
            )
    for index, payload in enumerate(learning_reports):
        manifest = payload.get("training_dataset_manifest") if isinstance(payload.get("training_dataset_manifest"), Mapping) else {}
        if manifest.get("raw_prompt_persisted") is True or manifest.get("raw_provider_output_persisted") is True:
            findings.append(
                {
                    "kind": "learning_report_raw_training_content_flag_detected",
                    "severity": "blocker",
                    "artifact_kind": "learning_report",
                    "artifact_index": index,
                }
            )
        benchmark_summary = payload.get("benchmark_summary") if isinstance(payload.get("benchmark_summary"), Mapping) else {}
        benchmark_contract = payload.get("benchmark_learning_contract") if isinstance(payload.get("benchmark_learning_contract"), Mapping) else {}
        scorecard_count = _optional_int(benchmark_summary.get("scorecard_count")) or 0
        scorecard_requested = benchmark_contract.get("scorecard_requested") is True
        if (scorecard_count > 0 or scorecard_requested) and not benchmark_contract:
            findings.append(
                {
                    "kind": "learning_report_benchmark_contract_missing",
                    "severity": "blocker",
                    "artifact_kind": "learning_report",
                    "artifact_index": index,
                }
            )
        if benchmark_contract:
            if benchmark_contract.get("benchmark_scores_used_for_router_learning") is True:
                findings.append(
                    {
                        "kind": "benchmark_scores_used_for_router_learning",
                        "severity": "blocker",
                        "artifact_kind": "learning_report",
                        "artifact_index": index,
                    }
                )
            if benchmark_contract.get("benchmark_scores_used_for_registry_calibration") is True:
                findings.append(
                    {
                        "kind": "benchmark_scores_used_for_registry_calibration",
                        "severity": "blocker",
                        "artifact_kind": "learning_report",
                        "artifact_index": index,
                    }
                )
            if benchmark_contract.get("benchmark_diagnostics_only") is not True:
                findings.append(
                    {
                        "kind": "learning_report_benchmark_diagnostics_not_marked_only",
                        "severity": "blocker",
                        "artifact_kind": "learning_report",
                        "artifact_index": index,
                    }
                )
        if _contains_true_raw_persisted_flag(payload):
            findings.append(
                {
                    "kind": "raw_content_persisted_flag_detected",
                    "severity": "blocker",
                    "artifact_kind": "learning_report",
                    "artifact_index": index,
                }
            )
    for index, payload in enumerate(calibrations):
        input_artifacts = payload.get("input_artifacts") if isinstance(payload.get("input_artifacts"), Mapping) else {}
        benchmark_count = int(input_artifacts.get("benchmark_file_count") or 0)
        if benchmark_count > 0 and not allow_aggregate_benchmark_calibration:
            findings.append(
                {
                    "kind": "benchmark_results_used_for_registry_calibration",
                    "severity": "blocker",
                    "artifact_kind": "registry_calibration",
                    "artifact_index": index,
                    "benchmark_file_count": benchmark_count,
                }
            )
        if _contains_true_raw_persisted_flag(payload):
            findings.append(
                {
                    "kind": "raw_content_persisted_flag_detected",
                    "severity": "blocker",
                    "artifact_kind": "registry_calibration",
                    "artifact_index": index,
                }
            )
    return findings


def _contains_true_raw_persisted_flag(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, raw in value.items():
            key_text = str(key)
            if key_text.startswith("raw_") and key_text.endswith("_persisted") and raw is True:
                return True
            if key_text in {"secrets_persisted", "benchmark_labels_used_for_training"} and raw is True:
                return True
            if _contains_true_raw_persisted_flag(raw):
                return True
    elif isinstance(value, list):
        return any(_contains_true_raw_persisted_flag(item) for item in value)
    return False


def _looks_like_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:24] if str(item)]


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
    return rows


def _route_key(row: Mapping[str, Any]) -> dict[str, Any]:
    route = row.get("route_snapshot") if isinstance(row.get("route_snapshot"), Mapping) else {}
    metrics = row.get("trace_metrics") if isinstance(row.get("trace_metrics"), Mapping) else {}
    verification = row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {}
    agent_outcome = row.get("agent_outcome") if isinstance(row.get("agent_outcome"), Mapping) else {}
    return {
        "public_model": str(route.get("public_model") or ""),
        "strategy": str(route.get("strategy") or ""),
        "task_type": str(route.get("task_type") or ""),
        "privacy_level": str(route.get("privacy_level") or ""),
        **_routing_policy_features(_routing_policy_from_route_and_trace(route, {})),
        "complexity": route.get("complexity"),
        "risk": route.get("risk"),
        "uncertainty": route.get("uncertainty"),
        "provider_call_count": metrics.get("provider_call_count"),
        "latency_ms": metrics.get("latency_ms"),
        "actual_cost_usd": metrics.get("actual_cost_usd"),
        "score": _effective_score(row),
        "accepted": _effective_acceptance(row),
        "external_verification_score": _optional_score(verification.get("score")),
        "external_verification_passed": _optional_bool(verification.get("passed")),
        "agent_task_success": _optional_bool(agent_outcome.get("task_success")),
        "agent_score": _optional_score(agent_outcome.get("score")),
        "agent_tool_failure_count": _optional_int(agent_outcome.get("tool_failure_count")),
        "agent_repair_loop_count": _optional_int(agent_outcome.get("repair_loop_count")),
        "request_fingerprint_sha256": sha256_text(str(row.get("request_fingerprint") or "")),
        "raw_prompt_persisted": False,
        "raw_request_fingerprint_persisted": False,
        "raw_feedback_text_persisted": False,
        "raw_agent_trace_persisted": False,
    }


def _summarize_routing_policies(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_version: dict[str, dict[str, Any]] = {}
    active_count = 0
    applied_count = 0
    unversioned_count = 0
    for row in rows:
        route = row.get("route_snapshot") if isinstance(row.get("route_snapshot"), Mapping) else {}
        policy = _routing_policy_features(_routing_policy_from_route_and_trace(route, {}))
        if policy["routing_policy_active"]:
            active_count += 1
        if policy["routing_policy_applied"]:
            applied_count += 1
        version = str(policy["routing_policy_version_sha256"] or "")
        if not version:
            unversioned_count += 1
            continue
        bucket = by_version.setdefault(
            version,
            {
                "feedback_count": 0,
                "applied_count": 0,
                "scores": [],
                "accepted": [],
            },
        )
        bucket["feedback_count"] += 1
        if policy["routing_policy_applied"]:
            bucket["applied_count"] += 1
        score = _effective_score(row)
        accepted = _effective_acceptance(row)
        if score is not None:
            bucket["scores"].append(float(score))
        if accepted is not None:
            bucket["accepted"].append(bool(accepted))
    version_rows = []
    for version, bucket in by_version.items():
        scores = bucket["scores"]
        accepted = bucket["accepted"]
        version_rows.append(
            {
                "policy_version_sha256": version,
                "feedback_count": bucket["feedback_count"],
                "applied_count": bucket["applied_count"],
                "average_score": None
                if not scores
                else round(sum(scores) / len(scores), 6),
                "accepted_rate": None
                if not accepted
                else round(
                    sum(1 for item in accepted if item) / len(accepted), 6
                ),
            }
        )
    version_rows.sort(
        key=lambda item: (-int(item["feedback_count"]), item["policy_version_sha256"])
    )
    return {
        "feedback_count": len(rows),
        "active_count": active_count,
        "applied_count": applied_count,
        "unversioned_count": unversioned_count,
        "policy_version_count": len(version_rows),
        "by_policy_version": version_rows[:24],
        "observational_only": True,
        "causal_policy_effect_established": False,
        "raw_policy_path_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _summarize_routes(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_strategy: dict[str, dict[str, Any]] = {}
    by_task_type: dict[str, int] = {}
    for row in rows:
        route = row.get("route_snapshot") if isinstance(row.get("route_snapshot"), Mapping) else {}
        strategy = str(route.get("strategy") or "unknown")
        task_type = str(route.get("task_type") or "unknown")
        by_task_type[task_type] = by_task_type.get(task_type, 0) + 1
        bucket = by_strategy.setdefault(strategy, {"count": 0, "scores": [], "accepted": []})
        bucket["count"] += 1
        score = _effective_score(row)
        accepted = _effective_acceptance(row)
        if score is not None:
            bucket["scores"].append(float(score))
        if accepted is not None:
            bucket["accepted"].append(bool(accepted))
    strategy_rows = []
    for strategy, bucket in by_strategy.items():
        scores = bucket["scores"]
        accepted = bucket["accepted"]
        strategy_rows.append(
            {
                "strategy": strategy,
                "count": bucket["count"],
                "average_score": None if not scores else round(sum(scores) / len(scores), 6),
                "accepted_rate": None if not accepted else round(sum(1 for value in accepted if value) / len(accepted), 6),
            }
        )
    strategy_rows.sort(key=lambda item: (-int(item["count"]), str(item["strategy"])))
    return {
        "by_strategy": strategy_rows,
        "by_task_type": dict(sorted(by_task_type.items())),
        "raw_prompt_persisted": False,
        "raw_feedback_text_persisted": False,
    }


def _summarize_external_verification(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = passed = failed = unknown = 0
    scores: list[float] = []
    by_status: dict[str, int] = {}
    for row in rows:
        verification = row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {}
        if not verification:
            continue
        total += 1
        status = str(verification.get("status") or "unknown")[:80] or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        score = _optional_score(verification.get("score"))
        if score is not None:
            scores.append(score)
        value = _optional_bool(verification.get("passed"))
        if value is True:
            passed += 1
        elif value is False:
            failed += 1
        else:
            unknown += 1
    return {
        "verification_count": total,
        "passed_count": passed,
        "failed_count": failed,
        "unknown_count": unknown,
        "average_verification_score": None if not scores else round(sum(scores) / len(scores), 6),
        "by_status": dict(sorted(by_status.items())),
        "raw_verification_details_persisted": False,
    }


def _summarize_agent_outcomes(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = succeeded = failed = unknown = 0
    scores: list[float] = []
    tool_calls = tool_failures = repair_loops = human_interventions = 0
    by_status: dict[str, int] = {}
    for row in rows:
        outcome = row.get("agent_outcome") if isinstance(row.get("agent_outcome"), Mapping) else {}
        if outcome.get("provided") is not True:
            continue
        total += 1
        status = str(outcome.get("final_status") or "unknown")[:80] or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        score = _optional_score(outcome.get("score"))
        if score is not None:
            scores.append(score)
        success = _optional_bool(outcome.get("task_success"))
        if success is True:
            succeeded += 1
        elif success is False:
            failed += 1
        else:
            unknown += 1
        tool_calls += _optional_int(outcome.get("tool_call_count")) or 0
        tool_failures += _optional_int(outcome.get("tool_failure_count")) or 0
        repair_loops += _optional_int(outcome.get("repair_loop_count")) or 0
        if _optional_bool(outcome.get("human_intervention_required")) is True:
            human_interventions += 1
    return {
        "agent_outcome_count": total,
        "task_success_count": succeeded,
        "task_failure_count": failed,
        "task_unknown_count": unknown,
        "average_agent_score": None if not scores else round(sum(scores) / len(scores), 6),
        "total_tool_call_count": tool_calls,
        "total_tool_failure_count": tool_failures,
        "total_repair_loop_count": repair_loops,
        "human_intervention_count": human_interventions,
        "by_status": dict(sorted(by_status.items())),
        "raw_agent_trace_persisted": False,
        "raw_task_text_persisted": False,
        "raw_tool_outputs_persisted": False,
    }


def _summarize_scorecards(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = []
    for row in rows:
        for candidate in row.get("candidates", []) if isinstance(row.get("candidates"), list) else []:
            if isinstance(candidate, Mapping):
                candidates.append(
                    {
                        "candidate_id": str(candidate.get("candidate_id") or ""),
                        "case_count": int(candidate.get("case_count") or 0),
                        "accuracy": candidate.get("accuracy"),
                    }
                )
    axio = [row for row in candidates if row["candidate_id"].startswith("axio-")]
    provider = [row for row in candidates if row["candidate_id"].startswith("provider::")]
    return {
        "scorecard_count": len(rows),
        "candidate_count": len(candidates),
        "axio_candidate_count": len(axio),
        "provider_baseline_count": len(provider),
        "best_axio_accuracy": _best_accuracy(axio),
        "best_provider_accuracy": _best_accuracy(provider),
        "claims_require_scorecard": True,
        "raw_prompt_persisted": False,
        "raw_labels_persisted": False,
    }


def _benchmark_diagnostic_suggestions(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return non-operational observations from an explicitly admitted scorecard."""

    best_axio = summary.get("best_axio_accuracy")
    best_provider = summary.get("best_provider_accuracy")
    if best_axio is None or best_provider is None:
        return []
    if float(best_axio) > float(best_provider):
        return [
            {
                "kind": "benchmark_diagnostic_axio_above_provider_observed",
                "reason": "diagnostic_scorecard_only",
                "automatic_policy_change": False,
                "not_for_router_learning": True,
            }
        ]
    return [
        {
            "kind": "benchmark_diagnostic_keep_baseline_guardrail",
            "reason": "axio_not_yet_above_observed_provider_diagnostic",
            "automatic_policy_change": False,
            "not_for_router_learning": True,
        }
    ]


def _policy_suggestions(
    *,
    eligible_count: int,
    average_score: float | None,
    accepted_rate: float | None,
    route_summary: Mapping[str, Any],
    verification_summary: Mapping[str, Any],
    benchmark_summary: Mapping[str, Any],
    min_examples: int,
) -> list[dict[str, Any]]:
    suggestions = []
    evidence = "insufficient" if eligible_count < min_examples else "sufficient"
    if eligible_count < min_examples:
        suggestions.append(
            {
                "kind": "collect_more_feedback",
                "priority": "high",
                "reason": "not_enough_feedback_for_stable_policy_update",
                "eligible_feedback_count": eligible_count,
                "min_examples": min_examples,
            }
        )
    if average_score is not None and average_score < 0.2:
        suggestions.append(
            {
                "kind": "increase_verification",
                "priority": "medium" if evidence == "insufficient" else "high",
                "reason": "low_average_feedback_score",
                "average_score": round(average_score, 6),
            }
        )
    if accepted_rate is not None and accepted_rate < 0.6:
        suggestions.append(
            {
                "kind": "raise_fusion_threshold_quality",
                "priority": "medium" if evidence == "insufficient" else "high",
                "reason": "low_user_acceptance_rate",
                "accepted_rate": round(accepted_rate, 6),
            }
        )
    failed = int(verification_summary.get("failed_count") or 0)
    passed = int(verification_summary.get("passed_count") or 0)
    if failed > 0 and failed >= passed:
        suggestions.append(
            {
                "kind": "increase_quality_target_or_escalation",
                "priority": "medium" if evidence == "insufficient" else "high",
                "reason": "external_verification_failures_not_below_passes",
                "verification_failed_count": failed,
                "verification_passed_count": passed,
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "kind": "maintain_policy_with_shadow_experiments",
                "priority": "low",
                "reason": "no_negative_signal_detected",
            }
        )
    for suggestion in suggestions:
        suggestion["raw_prompt_persisted"] = False
        suggestion["raw_feedback_text_persisted"] = False
    return suggestions


def _effective_score(row: Mapping[str, Any]) -> float | None:
    direct = _optional_score(row.get("score"))
    if direct is not None:
        return direct
    verification = row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {}
    verification_score = _optional_score(verification.get("score"))
    if verification_score is not None:
        return verification_score
    agent_outcome = row.get("agent_outcome") if isinstance(row.get("agent_outcome"), Mapping) else {}
    return _optional_score(agent_outcome.get("score"))


def _effective_acceptance(row: Mapping[str, Any]) -> bool | None:
    direct = _optional_bool(row.get("accepted"))
    if direct is not None:
        return direct
    verification = row.get("external_verification") if isinstance(row.get("external_verification"), Mapping) else {}
    verification_passed = _optional_bool(verification.get("passed"))
    if verification_passed is not None:
        return verification_passed
    agent_outcome = row.get("agent_outcome") if isinstance(row.get("agent_outcome"), Mapping) else {}
    return _optional_bool(agent_outcome.get("task_success"))


def _optional_score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0:
        number = number / 100.0 if number > 5.0 else number / 5.0
    return max(-1.0, min(1.0, number))


def _score01(value: Any) -> float | None:
    number = _optional_float(value)
    if number is None:
        return None
    return max(0.0, min(1.0, number))


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


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "pass", "passed", "success", "ok"}:
        return True
    if normalized in {"0", "false", "no", "n", "fail", "failed", "failure", "error"}:
        return False
    return None


def _best_accuracy(rows: Sequence[Mapping[str, Any]]) -> float | None:
    values = [float(row["accuracy"]) for row in rows if row.get("accuracy") is not None]
    return None if not values else round(max(values), 6)
