from __future__ import annotations

import ast
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

from .compat import canonicalize_payload, normalize_api_format
from .evaluation import (
    EXTERNAL_PROVIDER_RANKING_RECEIPT_SCHEMA,
    EXTERNAL_PROVIDER_RANKING_REQUIRED_RANKS,
    EXTERNAL_PROVIDER_RANKING_SELECTION_MODE,
    _complete_public_axio_benchmark_candidate,
    _estimate_benchmark_provider_call_cost,
    _external_provider_rank_mapping_validation_errors,
    _provider_baseline_freeze_digest_input,
    import_official_benchmark_run,
)
from .orchestrator import FusionEngine
from .providers import HTTPProviderClient, ensure_strict_streaming_client
from .registry import load_registry
from .schemas import FusionRequest, ModelProfile, PUBLIC_MODELS, sha256_text, stable_json


OFFICIAL_HARNESS_BRIDGE_SUPPORTED_SUITES = frozenset(
    {"livecodebench", "humaneval", "ifeval", "bfcl", "tau_bench", "mt_bench_work"}
)
_CODE_EXECUTION_SUITES = frozenset({"livecodebench", "humaneval"})
_HARNESS_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "livecodebench": (
        "lcb_runner/evaluation/compute_code_generation_metrics.py",
        "lcb_runner/evaluation/pass_k_utils.py",
        "lcb_runner/evaluation/testing_util.py",
    ),
    "humaneval": (
        "human_eval/evaluation.py",
        "human_eval/execution.py",
    ),
    "ifeval": (
        "instruction_following_eval/evaluation_main.py",
        "instruction_following_eval/evaluation_lib.py",
        "instruction_following_eval/instructions_registry.py",
    ),
    "bfcl": (
        "berkeley-function-call-leaderboard/bfcl_eval/eval_checker/ast_eval/ast_checker.py",
        "berkeley-function-call-leaderboard/bfcl_eval/constants/category_mapping.py",
        "berkeley-function-call-leaderboard/bfcl_eval/constants/type_mappings.py",
    ),
    "tau_bench": (
        "tau_bench/envs/__init__.py",
        "tau_bench/envs/base.py",
        "tau_bench/envs/user.py",
        "tau_bench/envs/retail/env.py",
        "tau_bench/envs/retail/tasks_test.py",
        "tau_bench/envs/airline/env.py",
        "tau_bench/envs/airline/tasks_test.py",
    ),
    "mt_bench_work": (
        "fastchat/llm_judge/common.py",
        "fastchat/llm_judge/gen_judgment.py",
        "fastchat/llm_judge/data/judge_prompts.jsonl",
        "fastchat/llm_judge/data/mt_bench/question.jsonl",
        "fastchat/llm_judge/data/mt_bench/reference_answer/gpt-4.jsonl",
    ),
}
_PIN_REQUIRED_FIELDS = (
    "harness_name_sha256",
    "harness_version_sha256",
    "dataset_snapshot_sha256",
    "evaluator_config_sha256",
    "prompt_protocol_sha256",
    "decoding_config_sha256",
)
_PROVIDER_CANDIDATE_PREFIX = "provider::"
_GENERATION_BINDING_FILENAME = "generation_binding.safe.json"
_EVALUATION_RECEIPT_FILENAME = "official_evaluation_receipt.safe.json"
_SCORED_ROWS_FILENAME = "official_scored_rows.safe.jsonl"
_EVALUATION_RECEIPT_SCHEMA = "axio_fusion_api.official_harness_evaluation.v1"
_IMPORT_BRIDGE_SCHEMA = "axio_fusion_api.official_harness_import_bridge.v1"
_BRIDGE_API_FORMATS = frozenset({"chat/completions", "responses", "anthropic", "gemini"})
_GENERATION_PRIVATE_FILENAMES = (
    "samples.private.jsonl",
    "generation.safe.jsonl",
    "generation_receipt.safe.json",
)
_LIVECODEBENCH_RESULT_FILENAME = "livecodebench_results.private.jsonl"
_BFCL_RESULT_FILENAME = "bfcl_results.private.jsonl"
_TAU_BENCH_RESULT_FILENAME = "tau_bench_results.private.jsonl"
_TAU_BENCH_INTERACTIONS_FILENAME = "tau_bench_interactions.private.jsonl"
_TAU_BENCH_PRIVATE_FILENAMES = (
    _TAU_BENCH_RESULT_FILENAME,
    _TAU_BENCH_INTERACTIONS_FILENAME,
)
_MT_BENCH_COMPARISON_SAMPLES_FILENAME = "mt_bench_comparison.private.jsonl"
_MT_BENCH_COMPARISON_METADATA_FILENAME = "mt_bench_comparison.safe.jsonl"
_MT_BENCH_COMPARISON_GENERATION_BINDING_FILENAME = "mt_bench_comparison_generation_binding.safe.json"
_MT_BENCH_PAIR_BINDING_FILENAME = "mt_bench_pair_binding.safe.json"
_MT_BENCH_JUDGMENTS_FILENAME = "mt_bench_judgments.private.jsonl"
_MT_BENCH_JUDGMENT_RECEIPTS_FILENAME = "mt_bench_judgment_receipts.safe.jsonl"
_MT_BENCH_COMPARISON_SCORED_ROWS_FILENAME = "mt_bench_comparison_scored_rows.safe.jsonl"
_MT_BENCH_COMPARISON_EVALUATION_RECEIPT_FILENAME = "mt_bench_comparison_evaluation_receipt.safe.json"
_MT_BENCH_PRIVATE_FILENAMES = (
    _MT_BENCH_COMPARISON_SAMPLES_FILENAME,
    _MT_BENCH_COMPARISON_METADATA_FILENAME,
    _MT_BENCH_COMPARISON_GENERATION_BINDING_FILENAME,
    _MT_BENCH_PAIR_BINDING_FILENAME,
    _MT_BENCH_JUDGMENTS_FILENAME,
    _MT_BENCH_JUDGMENT_RECEIPTS_FILENAME,
    _MT_BENCH_COMPARISON_SCORED_ROWS_FILENAME,
    _MT_BENCH_COMPARISON_EVALUATION_RECEIPT_FILENAME,
)
_BFCL_V3_MARKER = 'VERSION_PREFIX = "BFCL_v3"'
_BFCL_V3_AST_CATEGORY_FILENAMES = (
    ("simple", "BFCL_v3_simple.json"),
    ("multiple", "BFCL_v3_multiple.json"),
    ("parallel", "BFCL_v3_parallel.json"),
    ("parallel_multiple", "BFCL_v3_parallel_multiple.json"),
    ("live_simple", "BFCL_v3_live_simple.json"),
    ("live_multiple", "BFCL_v3_live_multiple.json"),
)
_TAU_BENCH_ENVIRONMENTS = ("retail", "airline")
_TAU_BENCH_TASK_SOURCES = (
    ("retail", "tau_bench/envs/retail/tasks_test.py", "TASKS_TEST"),
    ("airline", "tau_bench/envs/airline/tasks_test.py", "TASKS"),
)
_TAU_BENCH_USER_STRATEGIES = frozenset({"llm", "react", "verify", "reflection"})
_MT_BENCH_REFERENCE_CATEGORIES = frozenset({"math", "reasoning", "coding", "arena-hard-200"})
_MT_BENCH_SYSTEM_PROMPT = "You are a helpful assistant."
_MT_BENCH_JUDGE_MAX_OUTPUT_TOKENS = 2048


def build_official_harness_bridge_preflight(
    *,
    suite_id: str,
    dataset_path: str | Path,
    harness_root: str | Path,
    private_run_dir: str | Path,
    candidate_id: str,
    api_format: str = "chat/completions",
    registry_path: str | Path | None = None,
    provider_baseline_freeze_manifest_path: str | Path | None = None,
    harness_pin_manifest_path: str | Path | None = None,
    limit: int | None = None,
    max_output_tokens: int | None = None,
    axio_gateway_url: str | None = None,
    tau_user_model: str | None = None,
    tau_user_provider: str | None = None,
    tau_user_strategy: str = "llm",
    tau_environments: Sequence[str] = (),
    tau_max_steps: int = 30,
    tau_python_executable: str | None = None,
    mt_comparison_candidate_id: str | None = None,
    mt_judge_candidate_id: str | None = None,
    mt_judge_registry_path: str | Path | None = None,
    mt_judge_max_output_tokens: int = _MT_BENCH_JUDGE_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Validate an official-harness run without calling any model or evaluator.

    The returned receipt is intentionally safe to publish: it contains hashes,
    counts, protocol labels, and reason codes only. Raw benchmark prompts,
    hidden tests, labels, model responses, local paths, and credentials stay in
    the explicitly supplied private run directory or in the source files.
    """

    normalized_suite = str(suite_id or "").strip().lower()
    dataset = Path(dataset_path)
    harness = Path(harness_root)
    private_dir = Path(private_run_dir)
    reasons: list[str] = []
    if normalized_suite not in OFFICIAL_HARNESS_BRIDGE_SUPPORTED_SUITES:
        reasons.append("official_harness_bridge_suite_not_supported")
    candidate = _bridge_candidate_binding(
        candidate_id=candidate_id,
        api_format=api_format,
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
    )
    reasons.extend(candidate["reason_codes"])
    requirements = _HARNESS_REQUIREMENTS.get(normalized_suite, ())
    missing_harness_files = [relative for relative in requirements if not (harness / relative).is_file()]
    if not harness.is_dir():
        reasons.append("official_harness_root_not_found")
    elif missing_harness_files:
        reasons.append("official_harness_required_files_missing")
    if normalized_suite == "bfcl":
        reasons.extend(_bfcl_v3_harness_reasons(harness))
    if normalized_suite == "tau_bench":
        tau_user_simulator = _tau_user_simulator_binding(
            model=tau_user_model,
            provider=tau_user_provider,
            strategy=tau_user_strategy,
        )
        tau_execution = _tau_execution_binding(
            environments=tau_environments,
            max_steps=tau_max_steps,
            max_output_tokens=max_output_tokens,
            python_executable=tau_python_executable,
            gateway_configured=bool(str(axio_gateway_url or "").strip()),
        )
        reasons.extend(
            _tau_bench_preflight_reasons(
                candidate=candidate,
                user_simulator=tau_user_simulator,
                execution=tau_execution,
            )
        )
    else:
        tau_user_simulator = _not_applicable_tau_binding()
        tau_execution = _not_applicable_tau_binding()
    if normalized_suite == "mt_bench_work":
        mt_comparison = _mt_bench_comparison_binding(
            candidate_id=mt_comparison_candidate_id,
            registry_path=registry_path,
            provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
        )
        mt_judge = _mt_bench_judge_binding(
            candidate_id=mt_judge_candidate_id,
            registry_path=mt_judge_registry_path or registry_path,
        )
        mt_execution = _mt_bench_execution_binding(
            candidate=candidate,
            comparison=mt_comparison,
            judge=mt_judge,
            axio_gateway_url=axio_gateway_url,
            judge_max_output_tokens=mt_judge_max_output_tokens,
        )
        reasons.extend(mt_comparison["reason_codes"])
        reasons.extend(mt_judge["reason_codes"])
        reasons.extend(_mt_bench_preflight_reasons(execution=mt_execution))
    else:
        mt_comparison = _not_applicable_mt_binding()
        mt_judge = _not_applicable_mt_binding()
        mt_execution = _not_applicable_mt_binding()
    inventory = _official_source_inventory(
        dataset,
        suite_id=normalized_suite,
        limit=limit,
        tau_environments=tuple(str(item) for item in tau_execution.get("environments", ()) if str(item)),
    )
    reasons.extend(inventory["reason_codes"])
    pin = _harness_pin_binding(harness_pin_manifest_path, suite_id=normalized_suite)
    reasons.extend(pin["reason_codes"])
    target_tokens = _target_max_output_tokens(normalized_suite, max_output_tokens)
    generation_protocol = (
        _tau_generation_protocol_receipt(
            candidate=candidate,
            pin=pin,
            user_simulator=tau_user_simulator,
            execution=tau_execution,
            max_output_tokens=target_tokens,
        )
        if normalized_suite == "tau_bench"
        else _mt_bench_generation_protocol_receipt(
            candidate=candidate,
            comparison=mt_comparison,
            execution=mt_execution,
            pin=pin,
            max_output_tokens=target_tokens,
        )
        if normalized_suite == "mt_bench_work"
        else _generation_protocol_receipt(
            suite_id=normalized_suite,
            candidate=candidate,
            pin=pin,
            max_output_tokens=target_tokens,
        )
    )
    mt_comparison_generation_protocol = (
        _mt_bench_comparison_generation_protocol_receipt(
            candidate=mt_comparison,
            target=candidate,
            execution=mt_execution,
            pin=pin,
            max_output_tokens=target_tokens,
        )
        if normalized_suite == "mt_bench_work"
        else _not_applicable_mt_binding()
    )
    return {
        "schema": "axio_fusion_api.official_harness_bridge_preflight.v1",
        "status": "ready" if not reasons else "blocked",
        "suite_id": normalized_suite,
        "task_format": _official_task_format(normalized_suite),
        "candidate_id": candidate["candidate_id"],
        "candidate_kind": candidate["candidate_kind"],
        "api_format": candidate["api_format"],
        "candidate_binding": _safe_candidate_binding(candidate),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(candidate),
        "generation_protocol": generation_protocol,
        "mt_bench_comparison_generation_protocol": mt_comparison_generation_protocol,
        "max_output_tokens": target_tokens,
        "case_count": inventory["case_count"],
        "case_set_digest_sha256": inventory["case_set_digest_sha256"],
        "source_parser": inventory["source_parser"],
        "source_row_count": inventory["source_row_count"],
        "invalid_source_row_count": inventory["invalid_source_row_count"],
        "limit": None if limit is None else int(limit),
        "dataset_path_sha256": sha256_text(str(dataset)),
        "harness_root_sha256": sha256_text(str(harness)),
        "private_run_dir_sha256": sha256_text(str(private_dir)),
        "registry_path_sha256": sha256_text(str(registry_path)) if registry_path else "",
        "provider_baseline_freeze_manifest_path_sha256": (
            sha256_text(str(provider_baseline_freeze_manifest_path))
            if provider_baseline_freeze_manifest_path
            else ""
        ),
        "required_harness_file_count": len(requirements),
        "available_harness_file_count": len(requirements) - len(missing_harness_files),
        "missing_harness_file_count": len(missing_harness_files),
        "harness_pin_binding": pin,
        "tau_user_simulator": tau_user_simulator if normalized_suite == "tau_bench" else _not_applicable_tau_binding(),
        "tau_execution": tau_execution if normalized_suite == "tau_bench" else _not_applicable_tau_binding(),
        "mt_bench_comparison": _safe_mt_bench_candidate_binding(mt_comparison),
        "mt_bench_judge": _safe_mt_bench_candidate_binding(mt_judge),
        "mt_bench_execution": mt_execution if normalized_suite == "mt_bench_work" else _not_applicable_mt_binding(),
        "model_calls_performed": False,
        "official_harness_execution_performed": False,
        "raw_dataset_path_persisted": False,
        "raw_harness_path_persisted": False,
        "raw_private_run_path_persisted": False,
        "raw_case_hashes_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
        "reason_codes": sorted(set(reasons)),
    }


def generate_official_harness_samples(
    *,
    suite_id: str,
    dataset_path: str | Path,
    harness_root: str | Path,
    private_run_dir: str | Path,
    candidate_id: str,
    api_format: str = "chat/completions",
    registry_path: str | Path | None = None,
    provider_baseline_freeze_manifest_path: str | Path | None = None,
    harness_pin_manifest_path: str | Path | None = None,
    live: bool = False,
    client: HTTPProviderClient | None = None,
    engine: FusionEngine | None = None,
    axio_gateway_url: str | None = None,
    limit: int | None = None,
    max_output_tokens: int | None = None,
    tau_user_model: str | None = None,
    tau_user_provider: str | None = None,
    tau_user_strategy: str = "llm",
    tau_environments: Sequence[str] = (),
    tau_max_steps: int = 30,
    tau_python_executable: str | None = None,
    mt_comparison_candidate_id: str | None = None,
    mt_judge_candidate_id: str | None = None,
    mt_judge_registry_path: str | Path | None = None,
    mt_judge_max_output_tokens: int = _MT_BENCH_JUDGE_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Generate private official-harness samples through Axio's public API.

    `live=False` is deliberately a preflight-only mode. It never writes sample
    content or calls a provider. A live run writes raw prompt/output material
    only beneath `private_run_dir`; the returned and persisted receipts stay
    hash-only and are suitable for later import/audit.
    """

    preflight = build_official_harness_bridge_preflight(
        suite_id=suite_id,
        dataset_path=dataset_path,
        harness_root=harness_root,
        private_run_dir=private_run_dir,
        candidate_id=candidate_id,
        api_format=api_format,
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
        harness_pin_manifest_path=harness_pin_manifest_path,
        limit=limit,
        max_output_tokens=max_output_tokens,
        axio_gateway_url=axio_gateway_url,
        tau_user_model=tau_user_model,
        tau_user_provider=tau_user_provider,
        tau_user_strategy=tau_user_strategy,
        tau_environments=tau_environments,
        tau_max_steps=tau_max_steps,
        tau_python_executable=tau_python_executable,
        mt_comparison_candidate_id=mt_comparison_candidate_id,
        mt_judge_candidate_id=mt_judge_candidate_id,
        mt_judge_registry_path=mt_judge_registry_path,
        mt_judge_max_output_tokens=mt_judge_max_output_tokens,
    )
    if preflight["status"] != "ready":
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=preflight["reason_codes"],
        )
    if not live:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=["live_generation_required"],
        )

    normalized_suite = str(suite_id).strip().lower()
    normalized_format = str(preflight["api_format"] or normalize_api_format(api_format))
    candidate = _candidate_from_preflight(preflight, registry_path=registry_path)
    if candidate["reason_codes"]:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=candidate["reason_codes"],
        )
    if normalized_suite == "tau_bench":
        return _generate_tau_bench_samples(
            preflight=preflight,
            dataset_path=Path(dataset_path),
            harness_root=Path(harness_root),
            private_run_dir=Path(private_run_dir),
            candidate=candidate,
            registry_path=registry_path,
            axio_gateway_url=axio_gateway_url,
            limit=limit,
            max_output_tokens=max_output_tokens,
            tau_user_model=tau_user_model,
            tau_user_provider=tau_user_provider,
            tau_user_strategy=tau_user_strategy,
            tau_environments=tau_environments,
            tau_max_steps=tau_max_steps,
            tau_python_executable=tau_python_executable,
        )
    if normalized_suite == "mt_bench_work":
        return _generate_mt_bench_samples(
            preflight=preflight,
            dataset_path=Path(dataset_path),
            harness_root=Path(harness_root),
            private_run_dir=Path(private_run_dir),
            candidate=candidate,
            registry_path=registry_path,
            provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
            axio_gateway_url=axio_gateway_url,
            limit=limit,
            engine=engine,
            client=client,
            mt_comparison_candidate_id=mt_comparison_candidate_id,
            mt_judge_candidate_id=mt_judge_candidate_id,
            mt_judge_registry_path=mt_judge_registry_path,
            mt_judge_max_output_tokens=mt_judge_max_output_tokens,
        )
    cases = _load_private_source_cases(Path(dataset_path), suite_id=normalized_suite, limit=limit)
    private_root = _ensure_private_run_dir(private_run_dir)
    private_root_reasons = _private_generation_root_reasons(private_root)
    if private_root_reasons:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=private_root_reasons,
        )
    samples_path = private_root / "samples.private.jsonl"
    metadata_path = private_root / "generation.safe.jsonl"
    receipt_path = private_root / "generation_receipt.safe.json"
    binding_path = private_root / _GENERATION_BINDING_FILENAME
    active_engine = engine or FusionEngine(load_registry(registry_path), client=client)
    sample_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    target_tokens = int(preflight["max_output_tokens"])

    for index, case in enumerate(cases):
        started = time.monotonic()
        output = ""
        status = "completed"
        error_type = ""
        cost: Mapping[str, Any] = {}
        invocation: Mapping[str, Any] = _not_invoked_public_api_receipt(normalized_format)
        try:
            completion = _complete_official_harness_candidate(
                candidate=candidate,
                engine=active_engine,
                client=client,
                prompt=str(case["prompt"]),
                system=_official_generation_system_prompt(normalized_suite),
                task_type=_official_generation_task_type(normalized_suite),
                max_output_tokens=target_tokens,
                axio_gateway_url=axio_gateway_url,
                tools=tuple(case.get("tools") or ()),
                messages=tuple(case.get("messages") or ()),
            )
            output = _official_sample_output(
                normalized_suite,
                completion.text,
                tool_calls=completion.tool_calls,
            )
            cost = completion.cost
            invocation = completion.api_invocation
        except Exception as exc:  # noqa: BLE001 - provider boundary must stay redacted.
            status = "failed"
            error_type = type(exc).__name__
        sample_rows.append(
            _private_sample_row(
                normalized_suite,
                case,
                output,
                tool_calls=completion.tool_calls if status == "completed" else (),
                raw_output_text=completion.text if status == "completed" else "",
            )
        )
        metadata_rows.append(
            {
                "case_index": index,
                "case_id": case["case_id"],
                "status": status,
                "error_type": error_type[:120],
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "output_sha256": sha256_text(output),
                **_safe_cost_fields(cost),
                "public_api_invocation": dict(invocation),
                "raw_prompt_persisted": False,
                "raw_model_output_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }
        )
    _write_private_jsonl(samples_path, sample_rows)
    _write_private_jsonl(metadata_path, metadata_rows)
    succeeded = [row for row in metadata_rows if row["status"] == "completed"]
    generation_binding = _generation_binding_receipt(
        preflight=preflight,
        candidate=candidate,
        case_set_digest_sha256=str(preflight["case_set_digest_sha256"]),
        metadata_rows=metadata_rows,
        max_output_tokens=target_tokens,
    )
    _write_private_json(binding_path, generation_binding)
    receipt = {
        "schema": "axio_fusion_api.official_harness_generation.v1",
        "status": "generated" if len(succeeded) == len(metadata_rows) else "partial",
        "suite_id": normalized_suite,
        "task_format": _official_task_format(normalized_suite),
        "candidate_id": candidate["candidate_id"],
        "candidate_kind": candidate["candidate_kind"],
        "api_format": normalized_format,
        "candidate_binding": _safe_candidate_binding(candidate),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(candidate),
        "generation_protocol": dict(preflight["generation_protocol"]),
        "max_output_tokens": target_tokens,
        "case_count": len(metadata_rows),
        "completed_case_count": len(succeeded),
        "failed_case_count": len(metadata_rows) - len(succeeded),
        "case_set_digest_sha256": preflight["case_set_digest_sha256"],
        "private_samples_path_sha256": sha256_text(str(samples_path)),
        "generation_metadata_path_sha256": sha256_text(str(metadata_path)),
        "generation_receipt_path_sha256": sha256_text(str(receipt_path)),
        "generation_binding_path_sha256": sha256_text(str(binding_path)),
        "generation_binding_digest_sha256": str(generation_binding["generation_binding_digest_sha256"]),
        "generation_metadata_digest_sha256": sha256_text(stable_json(metadata_rows)),
        "gateway_configured": bool(axio_gateway_url),
        "gateway_url_sha256": sha256_text(str(axio_gateway_url)) if axio_gateway_url else "",
        "model_calls_performed": True,
        "official_harness_execution_performed": False,
        "preflight": _safe_preflight_reference(preflight),
        "private_sample_store_used": True,
        "raw_private_samples_location_disclosed": False,
        "raw_prompts_persisted_in_receipt": False,
        "raw_model_outputs_persisted_in_receipt": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    _write_private_json(receipt_path, receipt)
    return receipt


def evaluate_official_harness_samples(
    *,
    suite_id: str,
    dataset_path: str | Path,
    harness_root: str | Path,
    private_run_dir: str | Path,
    candidate_id: str,
    api_format: str = "chat/completions",
    registry_path: str | Path | None = None,
    provider_baseline_freeze_manifest_path: str | Path | None = None,
    harness_pin_manifest_path: str | Path | None = None,
    allow_unsafe_code_execution: bool = False,
    python_executable: str | None = None,
    worker_count: int = 4,
    timeout_seconds: float = 3.0,
    limit: int | None = None,
    max_output_tokens: int | None = None,
    axio_gateway_url: str | None = None,
    live: bool = False,
    client: HTTPProviderClient | None = None,
    tau_user_model: str | None = None,
    tau_user_provider: str | None = None,
    tau_user_strategy: str = "llm",
    tau_environments: Sequence[str] = (),
    tau_max_steps: int = 30,
    tau_python_executable: str | None = None,
    mt_comparison_candidate_id: str | None = None,
    mt_judge_candidate_id: str | None = None,
    mt_judge_registry_path: str | Path | None = None,
    mt_judge_max_output_tokens: int = _MT_BENCH_JUDGE_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Run an official evaluator against previously generated private samples.

    LiveCodeBench and HumanEval evaluate untrusted generated code. They are
    blocked unless the caller explicitly sets
    `allow_unsafe_code_execution=True`; production usage should run those
    evaluators in an isolated worker/container. IFEval is deterministic checking
    and does not require that extra code-execution flag.
    """

    preflight = build_official_harness_bridge_preflight(
        suite_id=suite_id,
        dataset_path=dataset_path,
        harness_root=harness_root,
        private_run_dir=private_run_dir,
        candidate_id=candidate_id,
        api_format=api_format,
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
        harness_pin_manifest_path=harness_pin_manifest_path,
        limit=limit,
        max_output_tokens=max_output_tokens,
        axio_gateway_url=axio_gateway_url,
        tau_user_model=tau_user_model,
        tau_user_provider=tau_user_provider,
        tau_user_strategy=tau_user_strategy,
        tau_environments=tau_environments,
        tau_max_steps=tau_max_steps,
        tau_python_executable=tau_python_executable,
        mt_comparison_candidate_id=mt_comparison_candidate_id,
        mt_judge_candidate_id=mt_judge_candidate_id,
        mt_judge_registry_path=mt_judge_registry_path,
        mt_judge_max_output_tokens=mt_judge_max_output_tokens,
    )
    if preflight["status"] != "ready":
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=preflight["reason_codes"],
        )
    normalized_suite = str(suite_id).strip().lower()
    candidate = _candidate_from_preflight(preflight, registry_path=registry_path)
    if candidate["reason_codes"]:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=candidate["reason_codes"],
        )
    if normalized_suite == "tau_bench":
        return _evaluate_tau_bench_samples(
            preflight=preflight,
            dataset_path=Path(dataset_path),
            harness_root=Path(harness_root),
            private_run_dir=Path(private_run_dir),
            candidate=candidate,
            limit=limit,
        )
    if normalized_suite == "mt_bench_work":
        return _evaluate_mt_bench_samples(
            preflight=preflight,
            dataset_path=Path(dataset_path),
            harness_root=Path(harness_root),
            private_run_dir=Path(private_run_dir),
            candidate=candidate,
            registry_path=registry_path,
            provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
            axio_gateway_url=axio_gateway_url,
            limit=limit,
            live=live,
            client=client,
            mt_comparison_candidate_id=mt_comparison_candidate_id,
            mt_judge_candidate_id=mt_judge_candidate_id,
            mt_judge_registry_path=mt_judge_registry_path,
            mt_judge_max_output_tokens=mt_judge_max_output_tokens,
        )
    if normalized_suite in _CODE_EXECUTION_SUITES and not allow_unsafe_code_execution:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=["unsafe_code_execution_not_explicitly_authorized"],
        )
    private_root = Path(private_run_dir)
    samples_path = private_root / "samples.private.jsonl"
    metadata_path = private_root / "generation.safe.jsonl"
    binding_path = private_root / _GENERATION_BINDING_FILENAME
    if not samples_path.is_file() or not metadata_path.is_file():
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=["private_generated_samples_missing"],
        )
    generation_binding = _load_generation_binding(
        binding_path,
        preflight=preflight,
        candidate=candidate,
        metadata_path=metadata_path,
    )
    if generation_binding["ready"] is not True:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=generation_binding["reason_codes"],
        )
    evaluator_output = private_root / "official_evaluator.private"
    evaluator_output.mkdir(parents=True, exist_ok=True)
    _try_private_permissions(evaluator_output)
    command = _official_evaluator_command(
        suite_id=normalized_suite,
        dataset_path=Path(dataset_path),
        harness_root=Path(harness_root),
        samples_path=samples_path,
        evaluator_output=evaluator_output,
        python_executable=python_executable or sys.executable,
        worker_count=worker_count,
        timeout_seconds=timeout_seconds,
        limit=limit,
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(harness_root),
            env=_official_evaluator_environment(harness_root),
            capture_output=True,
            text=True,
            timeout=_evaluator_process_timeout(normalized_suite, timeout_seconds, preflight["case_count"]),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _bridge_failed_evaluation_receipt(
            preflight=preflight,
            error_type=type(exc).__name__,
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
        )
    if completed.returncode != 0:
        return _bridge_failed_evaluation_receipt(
            preflight=preflight,
            error_type="OfficialHarnessProcessFailed",
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
            stdout=str(completed.stdout or ""),
            stderr=str(completed.stderr or ""),
            return_code=completed.returncode,
        )
    result_path = _official_evaluator_result_path(
        suite_id=normalized_suite,
        samples_path=samples_path,
        evaluator_output=evaluator_output,
    )
    if not result_path.is_file():
        return _bridge_failed_evaluation_receipt(
            preflight=preflight,
            error_type="OfficialHarnessResultMissing",
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
            stdout=str(completed.stdout or ""),
            stderr=str(completed.stderr or ""),
            return_code=completed.returncode,
        )
    generation = _safe_generation_metadata(metadata_path)
    try:
        scored_rows, normalization = _normalize_official_harness_results(
            suite_id=normalized_suite,
            dataset_path=Path(dataset_path),
            result_path=result_path,
            generation=generation,
            limit=limit,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _bridge_failed_evaluation_receipt(
            preflight=preflight,
            error_type=type(exc).__name__,
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
            stdout=str(completed.stdout or ""),
            stderr=str(completed.stderr or ""),
            return_code=completed.returncode,
        )
    result_case_alignment = _official_result_case_alignment(preflight, scored_rows)
    scored_path = private_root / _SCORED_ROWS_FILENAME
    receipt_path = private_root / _EVALUATION_RECEIPT_FILENAME
    _write_private_jsonl(scored_path, scored_rows)
    completed_rows = [row for row in scored_rows if row.get("status") == "completed"]
    passed_rows = [row for row in scored_rows if row.get("passed") is True]
    instruction_scores = [
        float(row["instruction_level_score"])
        for row in scored_rows
        if isinstance(row.get("instruction_level_score"), (int, float))
    ]
    compile_scores = [
        1.0 if row.get("compile_passed") is True else 0.0
        for row in scored_rows
        if normalized_suite == "livecodebench" and isinstance(row.get("compile_passed"), bool)
    ]
    receipt = {
        "schema": _EVALUATION_RECEIPT_SCHEMA,
        "status": (
            "evaluated"
            if len(completed_rows) == len(scored_rows) and result_case_alignment["ready"] is True
            else "partial"
        ),
        "suite_id": normalized_suite,
        "task_format": _official_task_format(normalized_suite),
        "candidate_id": candidate["candidate_id"],
        "candidate_kind": candidate["candidate_kind"],
        "api_format": str(preflight["api_format"]),
        "candidate_binding": _safe_candidate_binding(candidate),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(candidate),
        "generation_protocol": dict(preflight["generation_protocol"]),
        "generation_binding_digest_sha256": str(generation_binding["generation_binding_digest_sha256"]),
        "case_count": len(scored_rows),
        "completed_case_count": len(completed_rows),
        "passed_case_count": len(passed_rows),
        "primary_score": round(len(passed_rows) / len(scored_rows), 6) if scored_rows else None,
        "primary_metric": _official_primary_metric(normalized_suite),
        "instruction_level_accuracy": (
            round(sum(instruction_scores) / len(instruction_scores), 6) if instruction_scores else None
        ),
        "compile_rate": (
            round(sum(compile_scores) / len(compile_scores), 6) if compile_scores else None
        ),
        "case_set_digest_sha256": preflight["case_set_digest_sha256"],
        "safe_scored_rows_path_sha256": sha256_text(str(scored_path)),
        "safe_scored_rows_digest_sha256": sha256_text(stable_json(scored_rows)),
        "official_harness_result_path_sha256": sha256_text(str(result_path)),
        "evaluator_stdout_sha256": sha256_text(str(completed.stdout or "")),
        "evaluator_stderr_sha256": sha256_text(str(completed.stderr or "")),
        "evaluator_return_code": int(completed.returncode),
        "evaluator_latency_ms": round((time.monotonic() - started) * 1000, 3),
        "evaluator_command_protocol_sha256": _official_evaluator_command_protocol_digest(normalized_suite, command),
        "normalization": normalization,
        "result_case_alignment": result_case_alignment,
        "official_import_binding": _official_import_binding(
            preflight=preflight,
            candidate=candidate,
            scored_path=scored_path,
            result_case_alignment=result_case_alignment,
        ),
        "reason_codes": list(result_case_alignment["reason_codes"]),
        "official_harness_execution_performed": True,
        "model_calls_performed": False,
        "preflight": _safe_preflight_reference(preflight),
        "private_sample_store_used": True,
        "raw_private_samples_location_disclosed": False,
        "raw_prompts_persisted_in_receipt": False,
        "raw_model_outputs_persisted_in_receipt": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    receipt["evaluation_receipt_digest_sha256"] = _evaluation_receipt_digest(receipt)
    _write_private_json(receipt_path, receipt)
    return receipt


def import_official_harness_evaluation(
    *,
    private_run_dir: str | Path,
    mt_side: str = "target",
) -> dict[str, Any]:
    """Convert one completed LiveCodeBench/HumanEval/IFEval receipt into a safe run.

    The function deliberately derives every input from one private run directory.
    Operators therefore cannot accidentally retype or swap the candidate alias,
    scored-row source, harness identity, prompt protocol, or decoding protocol
    when promoting an official-harness result into the benchmark import chain.
    No provider or evaluator is invoked here.
    """

    private_root = Path(private_run_dir)
    selected_mt_side = str(mt_side or "target").strip().lower()
    if selected_mt_side not in {"target", "comparison"}:
        return _official_harness_import_bridge_blocked_receipt(
            private_root=private_root,
            receipt_path=private_root / _EVALUATION_RECEIPT_FILENAME,
            scored_path=private_root / _SCORED_ROWS_FILENAME,
            validation={},
            reason_codes=["official_harness_mt_bench_import_side_invalid"],
        )
    if selected_mt_side == "comparison":
        receipt_path = private_root / _MT_BENCH_COMPARISON_EVALUATION_RECEIPT_FILENAME
        scored_path = private_root / _MT_BENCH_COMPARISON_SCORED_ROWS_FILENAME
        metadata_path = private_root / _MT_BENCH_COMPARISON_METADATA_FILENAME
        generation_binding_path = private_root / _MT_BENCH_COMPARISON_GENERATION_BINDING_FILENAME
    else:
        receipt_path = private_root / _EVALUATION_RECEIPT_FILENAME
        scored_path = private_root / _SCORED_ROWS_FILENAME
        metadata_path = private_root / "generation.safe.jsonl"
        generation_binding_path = private_root / _GENERATION_BINDING_FILENAME
    validation = _validate_official_harness_import_bridge(
        private_root=private_root,
        receipt_path=receipt_path,
        scored_path=scored_path,
        metadata_path=metadata_path,
        generation_binding_path=generation_binding_path,
        mt_side=selected_mt_side,
    )
    if validation["ready"] is not True:
        return _official_harness_import_bridge_blocked_receipt(
            private_root=private_root,
            receipt_path=receipt_path,
            scored_path=scored_path,
            validation=validation,
        )

    receipt = validation["receipt"]
    import_binding = validation["official_import_binding"]
    try:
        run = import_official_benchmark_run(
            suite_id=str(receipt["suite_id"]),
            candidate_id=str(receipt["candidate_id"]),
            source_path=scored_path,
            task_format=str(receipt["task_format"]),
            api_format=str(receipt["api_format"]),
            harness_name=str(import_binding["harness_name_sha256"]),
            harness_version=str(import_binding["harness_version_sha256"]),
            dataset_snapshot=str(import_binding["dataset_snapshot_sha256"]),
            evaluator_config=str(import_binding["evaluator_config_sha256"]),
            position_balanced=bool(import_binding["position_balanced"]),
            prompt_protocol=str(import_binding["prompt_protocol_sha256"]),
            decoding_config=str(import_binding["decoding_config_sha256"]),
        )
    except Exception as exc:  # noqa: BLE001 - never persist provider or benchmark content from an exception.
        return _official_harness_import_bridge_blocked_receipt(
            private_root=private_root,
            receipt_path=receipt_path,
            scored_path=scored_path,
            validation=validation,
            reason_codes=["official_harness_import_bridge_import_failed"],
            error_type=type(exc).__name__,
        )

    bridge = _safe_official_harness_import_bridge_receipt(
        private_root=private_root,
        receipt_path=receipt_path,
        scored_path=scored_path,
        receipt=receipt,
        import_binding=import_binding,
        validation=validation,
        mt_side=selected_mt_side,
    )
    run_reasons = _official_harness_imported_run_reasons(
        run,
        receipt=receipt,
        import_binding=import_binding,
        validation=validation,
    )
    if run_reasons:
        return _official_harness_import_bridge_blocked_receipt(
            private_root=private_root,
            receipt_path=receipt_path,
            scored_path=scored_path,
            validation=validation,
            reason_codes=run_reasons,
        )
    run["mode"] = "official_harness_import"
    run["official_harness_bridge"] = bridge
    import_receipt = run.get("import_receipt") if isinstance(run.get("import_receipt"), Mapping) else {}
    run["import_receipt"] = {
        **dict(import_receipt),
        "source_kind": "official_harness_scored_rows",
        "official_harness_import_bridge": bridge,
        "raw_source_path_persisted": False,
        "raw_source_content_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    return run


def _validate_official_harness_import_bridge(
    *,
    private_root: Path,
    receipt_path: Path,
    scored_path: Path,
    metadata_path: Path,
    generation_binding_path: Path,
    mt_side: str = "target",
) -> dict[str, Any]:
    reasons: list[str] = []
    receipt = _load_private_json_object(
        receipt_path,
        missing_reason="official_harness_import_bridge_evaluation_receipt_missing",
        unreadable_reason="official_harness_import_bridge_evaluation_receipt_unreadable",
        reasons=reasons,
    )
    if not receipt:
        return _official_harness_import_bridge_validation(
            private_root=private_root,
            receipt_path=receipt_path,
            scored_path=scored_path,
            receipt={},
            import_binding={},
            reasons=reasons,
        )

    _validate_evaluation_receipt(receipt, receipt_path=receipt_path, scored_path=scored_path, reasons=reasons)
    import_binding = (
        dict(receipt["official_import_binding"])
        if isinstance(receipt.get("official_import_binding"), Mapping)
        else {}
    )
    _validate_official_import_binding(
        receipt,
        import_binding,
        scored_path=scored_path,
        reasons=reasons,
    )
    scored_rows = _load_private_jsonl_rows(
        scored_path,
        missing_reason="official_harness_import_bridge_scored_rows_missing",
        unreadable_reason="official_harness_import_bridge_scored_rows_unreadable",
        reasons=reasons,
    )
    _validate_scored_rows(
        receipt,
        scored_rows,
        reasons=reasons,
    )
    generation_binding = _load_private_json_object(
        generation_binding_path,
        missing_reason="official_harness_import_bridge_generation_binding_missing",
        unreadable_reason="official_harness_import_bridge_generation_binding_unreadable",
        reasons=reasons,
    )
    metadata_rows = _load_private_jsonl_rows(
        metadata_path,
        missing_reason="official_harness_import_bridge_generation_metadata_missing",
        unreadable_reason="official_harness_import_bridge_generation_metadata_unreadable",
        reasons=reasons,
    )
    _validate_generation_binding_for_import(
        receipt,
        generation_binding,
        metadata_rows,
        scored_rows,
        reasons=reasons,
    )
    if str(receipt.get("suite_id") or "") == "mt_bench_work":
        _validate_mt_bench_import_artifacts(
            private_root=private_root,
            receipt=receipt,
            scored_rows=scored_rows,
            metadata_rows=metadata_rows,
            generation_binding=generation_binding,
            mt_side=mt_side,
            reasons=reasons,
        )
    validation = _official_harness_import_bridge_validation(
        private_root=private_root,
        receipt_path=receipt_path,
        scored_path=scored_path,
        receipt=receipt,
        import_binding=import_binding,
        reasons=reasons,
    )
    return {
        **validation,
        "receipt": receipt,
        "official_import_binding": import_binding,
    }


def _load_private_json_object(
    path: Path,
    *,
    missing_reason: str,
    unreadable_reason: str,
    reasons: list[str],
) -> dict[str, Any]:
    if not path.is_file():
        reasons.append(missing_reason)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reasons.append(unreadable_reason)
        return {}
    if not isinstance(payload, Mapping):
        reasons.append(unreadable_reason)
        return {}
    return dict(payload)


def _load_private_jsonl_rows(
    path: Path,
    *,
    missing_reason: str,
    unreadable_reason: str,
    reasons: list[str],
) -> list[dict[str, Any]]:
    if not path.is_file():
        reasons.append(missing_reason)
        return []
    try:
        return list(_iter_private_jsonl(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        reasons.append(unreadable_reason)
        return []


def _validate_evaluation_receipt(
    receipt: Mapping[str, Any],
    *,
    receipt_path: Path,
    scored_path: Path,
    reasons: list[str],
) -> None:
    if str(receipt.get("schema") or "") != _EVALUATION_RECEIPT_SCHEMA:
        reasons.append("official_harness_import_bridge_evaluation_receipt_schema_invalid")
    declared_digest = str(receipt.get("evaluation_receipt_digest_sha256") or "")
    if not _looks_like_sha256(declared_digest) or declared_digest != _evaluation_receipt_digest(receipt):
        reasons.append("official_harness_import_bridge_evaluation_receipt_digest_invalid")
    if str(receipt.get("status") or "") != "evaluated":
        reasons.append("official_harness_import_bridge_evaluation_not_complete")
    if receipt.get("official_harness_execution_performed") is not True:
        reasons.append("official_harness_import_bridge_official_execution_missing")
    return_code = receipt.get("evaluator_return_code")
    if isinstance(return_code, bool) or not isinstance(return_code, int) or return_code != 0:
        reasons.append("official_harness_import_bridge_evaluator_return_code_invalid")
    if _contains_true_flag(receipt):
        reasons.append("official_harness_import_bridge_evaluation_receipt_raw_content_flagged")

    suite_id = str(receipt.get("suite_id") or "")
    task_format = str(receipt.get("task_format") or "")
    if suite_id not in OFFICIAL_HARNESS_BRIDGE_SUPPORTED_SUITES:
        reasons.append("official_harness_import_bridge_suite_not_supported")
    elif task_format != _official_task_format(suite_id):
        reasons.append("official_harness_import_bridge_task_format_mismatch")
    elif str(receipt.get("primary_metric") or "") != _official_primary_metric(suite_id):
        reasons.append("official_harness_import_bridge_primary_metric_mismatch")

    candidate_id = str(receipt.get("candidate_id") or "")
    candidate_kind = str(receipt.get("candidate_kind") or "")
    expected_kind = _bridge_candidate_kind(candidate_id)
    if not expected_kind:
        reasons.append("official_harness_import_bridge_candidate_not_safe")
    elif candidate_kind != expected_kind:
        reasons.append("official_harness_import_bridge_candidate_kind_mismatch")
    api_format = str(receipt.get("api_format") or "")
    if api_format not in _BRIDGE_API_FORMATS:
        reasons.append("official_harness_import_bridge_api_format_invalid")
    binding = receipt.get("candidate_binding") if isinstance(receipt.get("candidate_binding"), Mapping) else {}
    if str(binding.get("candidate_id_sha256") or "") != sha256_text(candidate_id):
        reasons.append("official_harness_import_bridge_candidate_binding_mismatch")
    if str(binding.get("candidate_kind") or "") != candidate_kind:
        reasons.append("official_harness_import_bridge_candidate_binding_kind_mismatch")
    if str(binding.get("api_format") or "") != api_format:
        reasons.append("official_harness_import_bridge_candidate_binding_api_format_mismatch")

    case_count = _safe_int(receipt.get("case_count"))
    if case_count <= 0:
        reasons.append("official_harness_import_bridge_case_set_empty")
    if _safe_int(receipt.get("completed_case_count")) != case_count:
        reasons.append("official_harness_import_bridge_generation_incomplete")
    if _safe_int(receipt.get("passed_case_count")) > case_count:
        reasons.append("official_harness_import_bridge_passed_case_count_invalid")
    if not _looks_like_sha256(receipt.get("case_set_digest_sha256")):
        reasons.append("official_harness_import_bridge_case_set_digest_invalid")
    if str(receipt.get("safe_scored_rows_path_sha256") or "") != sha256_text(str(scored_path)):
        reasons.append("official_harness_import_bridge_scored_rows_path_mismatch")
    if str(receipt.get("safe_scored_rows_path_sha256") or "") == sha256_text(str(receipt_path)):
        reasons.append("official_harness_import_bridge_scored_rows_path_invalid")

    alignment = receipt.get("result_case_alignment") if isinstance(receipt.get("result_case_alignment"), Mapping) else {}
    if alignment.get("ready") is not True:
        reasons.append("official_harness_import_bridge_result_case_alignment_not_ready")
    if _safe_int(alignment.get("expected_case_count")) != case_count or _safe_int(alignment.get("observed_case_count")) != case_count:
        reasons.append("official_harness_import_bridge_result_case_count_mismatch")
    if str(alignment.get("expected_case_set_digest_sha256") or "") != str(receipt.get("case_set_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_result_expected_case_set_mismatch")
    if str(alignment.get("observed_case_set_digest_sha256") or "") != str(receipt.get("case_set_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_result_observed_case_set_mismatch")

    normalization = receipt.get("normalization") if isinstance(receipt.get("normalization"), Mapping) else {}
    if str(normalization.get("schema") or "") != "axio_fusion_api.official_harness_normalization.v1":
        reasons.append("official_harness_import_bridge_normalization_schema_invalid")
    if _safe_int(normalization.get("input_result_row_count")) != case_count:
        reasons.append("official_harness_import_bridge_normalization_case_count_mismatch")
    if _safe_int(normalization.get("completed_row_count")) != case_count:
        reasons.append("official_harness_import_bridge_normalization_incomplete")
    if str(normalization.get("case_set_digest_sha256") or "") != str(receipt.get("case_set_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_normalization_case_set_mismatch")
    if suite_id == "tau_bench":
        _validate_tau_bench_normalization(receipt, normalization, reasons=reasons)
    if suite_id == "mt_bench_work":
        if receipt.get("position_balanced") is not True:
            reasons.append("official_harness_import_bridge_mt_bench_position_balance_missing")
        if str(receipt.get("mt_bench_side") or "") not in {"target", "comparison"}:
            reasons.append("official_harness_import_bridge_mt_bench_side_invalid")
        if _safe_int(receipt.get("judge_call_count")) != case_count * 2:
            reasons.append("official_harness_import_bridge_mt_bench_judge_call_count_mismatch")
        if not _looks_like_sha256(receipt.get("judge_output_digest_sha256")):
            reasons.append("official_harness_import_bridge_mt_bench_judge_receipt_digest_invalid")
        if not _looks_like_sha256(receipt.get("mt_bench_pair_binding_digest_sha256")):
            reasons.append("official_harness_import_bridge_mt_bench_pair_binding_digest_invalid")
        if not _looks_like_sha256(receipt.get("counterpart_candidate_id_sha256")):
            reasons.append("official_harness_import_bridge_mt_bench_counterpart_binding_invalid")

    protocol = receipt.get("generation_protocol") if isinstance(receipt.get("generation_protocol"), Mapping) else {}
    _validate_generation_protocol(receipt, protocol, reasons=reasons)
    if candidate_kind == "provider_native":
        provider_freeze = (
            receipt.get("provider_baseline_freeze_binding")
            if isinstance(receipt.get("provider_baseline_freeze_binding"), Mapping)
            else {}
        )
        if provider_freeze.get("required") is not True or provider_freeze.get("ready") is not True:
            reasons.append("official_harness_import_bridge_provider_freeze_not_ready")
        if provider_freeze.get("candidate_frozen") is not True:
            reasons.append("official_harness_import_bridge_provider_candidate_not_frozen")
        if str(provider_freeze.get("candidate_id_sha256") or "") != sha256_text(candidate_id):
            reasons.append("official_harness_import_bridge_provider_freeze_candidate_mismatch")
        if not _looks_like_sha256(provider_freeze.get("manifest_digest_sha256")):
            reasons.append("official_harness_import_bridge_provider_freeze_digest_invalid")
        if not _looks_like_sha256(binding.get("profile_id_sha256")):
            reasons.append("official_harness_import_bridge_provider_profile_binding_invalid")


def _validate_generation_protocol(
    receipt: Mapping[str, Any],
    protocol: Mapping[str, Any],
    *,
    reasons: list[str],
) -> None:
    suite_id = str(receipt.get("suite_id") or "")
    expected_schema = (
        "axio_fusion_api.tau_bench_generation_protocol.v1"
        if suite_id == "tau_bench"
        else "axio_fusion_api.mt_bench_generation_protocol.v1"
        if suite_id == "mt_bench_work"
        else "axio_fusion_api.official_harness_generation_protocol.v1"
    )
    if str(protocol.get("schema") or "") != expected_schema:
        reasons.append("official_harness_import_bridge_generation_protocol_schema_invalid")
    declared_digest = str(protocol.get("generation_protocol_digest_sha256") or "")
    if not _looks_like_sha256(declared_digest) or declared_digest != _generation_protocol_digest(protocol):
        reasons.append("official_harness_import_bridge_generation_protocol_digest_invalid")
    if str(protocol.get("suite_id") or "") != suite_id:
        reasons.append("official_harness_import_bridge_generation_protocol_suite_mismatch")
    if str(protocol.get("candidate_kind") or "") != str(receipt.get("candidate_kind") or ""):
        reasons.append("official_harness_import_bridge_generation_protocol_candidate_kind_mismatch")
    if str(protocol.get("candidate_id_sha256") or "") != sha256_text(str(receipt.get("candidate_id") or "")):
        reasons.append("official_harness_import_bridge_generation_protocol_candidate_mismatch")
    if str(protocol.get("api_format") or "") != str(receipt.get("api_format") or ""):
        reasons.append("official_harness_import_bridge_generation_protocol_api_format_mismatch")
    expected_task_type = _official_generation_task_type(suite_id)
    if str(protocol.get("task_type") or "") != expected_task_type:
        reasons.append("official_harness_import_bridge_generation_protocol_task_type_mismatch")
    if protocol.get("temperature") != 0.0 or protocol.get("top_p") is not None:
        reasons.append("official_harness_import_bridge_generation_protocol_not_deterministic")
    if _safe_int(protocol.get("stop_sequence_count")) != 0:
        reasons.append("official_harness_import_bridge_generation_protocol_stop_sequences_invalid")
    if suite_id == "tau_bench":
        if not _looks_like_sha256(protocol.get("user_simulator_configuration_sha256")):
            reasons.append("official_harness_import_bridge_tau_user_simulator_binding_invalid")
        if str(protocol.get("user_simulator_strategy") or "") not in _TAU_BENCH_USER_STRATEGIES:
            reasons.append("official_harness_import_bridge_tau_user_strategy_invalid")
        if not _looks_like_sha256(protocol.get("environment_selection_sha256")):
            reasons.append("official_harness_import_bridge_tau_environment_binding_invalid")
        if _safe_int(protocol.get("max_steps")) <= 0:
            reasons.append("official_harness_import_bridge_tau_max_steps_invalid")
    elif suite_id == "mt_bench_work":
        if protocol.get("two_turn_dialogue") is not True or protocol.get("turn_order_fixed") is not True:
            reasons.append("official_harness_import_bridge_mt_bench_two_turn_protocol_invalid")
        if str(protocol.get("answer_system_prompt_sha256") or "") != sha256_text(_MT_BENCH_SYSTEM_PROMPT):
            reasons.append("official_harness_import_bridge_mt_bench_system_prompt_binding_invalid")
        if not _looks_like_sha256(protocol.get("comparison_candidate_id_sha256")):
            reasons.append("official_harness_import_bridge_mt_bench_comparison_candidate_binding_invalid")
        if str(protocol.get("comparison_candidate_kind") or "") not in {"public_axio", "provider_native"}:
            reasons.append("official_harness_import_bridge_mt_bench_comparison_kind_invalid")
        if not _looks_like_sha256(protocol.get("execution_configuration_sha256")):
            reasons.append("official_harness_import_bridge_mt_bench_execution_binding_invalid")
    elif not _looks_like_sha256(protocol.get("system_prompt_sha256")):
        reasons.append("official_harness_import_bridge_generation_protocol_system_prompt_hash_invalid")
    if _safe_int(protocol.get("max_output_tokens")) <= 0:
        reasons.append("official_harness_import_bridge_generation_protocol_output_budget_invalid")
    for field in ("prompt_protocol_sha256", "decoding_config_sha256", "harness_pin_digest_sha256"):
        if not _looks_like_sha256(protocol.get(field)):
            reasons.append(f"official_harness_import_bridge_generation_protocol_{field}_invalid")
    if _contains_true_flag(protocol):
        reasons.append("official_harness_import_bridge_generation_protocol_raw_content_flagged")


def _validate_official_import_binding(
    receipt: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    scored_path: Path,
    reasons: list[str],
) -> None:
    if str(binding.get("schema") or "") != "axio_fusion_api.official_harness_import_binding.v1":
        reasons.append("official_harness_import_bridge_binding_schema_invalid")
    if str(binding.get("candidate_id_sha256") or "") != sha256_text(str(receipt.get("candidate_id") or "")):
        reasons.append("official_harness_import_bridge_binding_candidate_mismatch")
    if str(binding.get("candidate_kind") or "") != str(receipt.get("candidate_kind") or ""):
        reasons.append("official_harness_import_bridge_binding_candidate_kind_mismatch")
    if str(binding.get("api_format") or "") != str(receipt.get("api_format") or ""):
        reasons.append("official_harness_import_bridge_binding_api_format_mismatch")
    if str(binding.get("source_path_sha256") or "") != sha256_text(str(scored_path)):
        reasons.append("official_harness_import_bridge_binding_scored_rows_path_mismatch")
    if binding.get("case_set_matches_preflight") is not True:
        reasons.append("official_harness_import_bridge_binding_case_set_not_preflight_matched")
    if str(binding.get("case_set_digest_sha256") or "") != str(receipt.get("case_set_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_binding_case_set_mismatch")
    for field in _PIN_REQUIRED_FIELDS:
        if not _looks_like_sha256(binding.get(field)):
            reasons.append(f"official_harness_import_bridge_binding_{field}_invalid")
    protocol = receipt.get("generation_protocol") if isinstance(receipt.get("generation_protocol"), Mapping) else {}
    for field in ("prompt_protocol_sha256", "decoding_config_sha256"):
        if str(binding.get(field) or "") != str(protocol.get(field) or ""):
            reasons.append(f"official_harness_import_bridge_binding_{field}_mismatch")
    preflight = receipt.get("preflight") if isinstance(receipt.get("preflight"), Mapping) else {}
    pin = preflight.get("harness_pin_binding") if isinstance(preflight.get("harness_pin_binding"), Mapping) else {}
    for field in ("harness_name_sha256", "harness_version_sha256", "dataset_snapshot_sha256", "evaluator_config_sha256"):
        if str(binding.get(field) or "") != str(pin.get(field) or ""):
            reasons.append(f"official_harness_import_bridge_binding_{field}_pin_mismatch")
    if str(receipt.get("suite_id") or "") == "mt_bench_work" and binding.get("position_balanced") is not True:
        reasons.append("official_harness_import_bridge_mt_bench_position_balancing_missing")
    if _contains_true_flag(binding):
        reasons.append("official_harness_import_bridge_binding_raw_content_flagged")


def _validate_scored_rows(
    receipt: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    reasons: list[str],
) -> None:
    expected_count = _safe_int(receipt.get("case_count"))
    expected_digest = str(receipt.get("case_set_digest_sha256") or "")
    expected_metric = str(receipt.get("primary_metric") or "")
    if len(rows) != expected_count:
        reasons.append("official_harness_import_bridge_scored_rows_case_count_mismatch")
    if str(receipt.get("safe_scored_rows_digest_sha256") or "") != sha256_text(stable_json(list(rows))):
        reasons.append("official_harness_import_bridge_scored_rows_digest_mismatch")
    suite_id = str(receipt.get("suite_id") or "")
    case_ids: list[str] = []
    for row in rows:
        unexpected = set(row) - _SAFE_SCORED_ROW_FIELDS
        if unexpected:
            reasons.append("official_harness_import_bridge_scored_rows_unsafe_fields")
        if _contains_true_flag(row):
            reasons.append("official_harness_import_bridge_scored_rows_raw_content_flagged")
        case_id = str(row.get("case_id") or "")
        case_ids.append(case_id)
        if not _looks_like_sha256(case_id):
            reasons.append("official_harness_import_bridge_scored_rows_case_id_invalid")
        if str(row.get("status") or "") != "completed":
            reasons.append("official_harness_import_bridge_scored_rows_not_completed")
        if not isinstance(row.get("passed"), bool) or not isinstance(row.get("correct"), bool):
            reasons.append("official_harness_import_bridge_scored_rows_score_state_invalid")
        if row.get("passed") is not row.get("correct"):
            reasons.append("official_harness_import_bridge_scored_rows_pass_correct_mismatch")
        allowed_scores = {0.0, 0.5, 1.0} if suite_id == "mt_bench_work" else {0.0, 1.0}
        if _safe_float(row.get("score")) not in allowed_scores:
            reasons.append("official_harness_import_bridge_scored_rows_score_invalid")
        elif bool(row.get("passed")) != (_safe_float(row.get("score")) == 1.0):
            reasons.append("official_harness_import_bridge_scored_rows_score_pass_mismatch")
        if str(row.get("metric") or "") != expected_metric:
            reasons.append("official_harness_import_bridge_scored_rows_metric_mismatch")
        if not _looks_like_sha256(row.get("prediction_sha256")) or not _looks_like_sha256(row.get("output_sha256")):
            reasons.append("official_harness_import_bridge_scored_rows_output_hash_invalid")
        if str(row.get("error_type") or ""):
            reasons.append("official_harness_import_bridge_scored_rows_error_present")
        if suite_id == "ifeval":
            instruction_score = row.get("instruction_level_score")
            if not isinstance(instruction_score, (int, float)) or not 0.0 <= float(instruction_score) <= 1.0:
                reasons.append("official_harness_import_bridge_scored_rows_instruction_score_invalid")
            if _safe_int(row.get("instruction_count")) <= 0:
                reasons.append("official_harness_import_bridge_scored_rows_instruction_count_invalid")
        if suite_id == "livecodebench":
            if not isinstance(row.get("compile_passed"), bool):
                reasons.append("official_harness_import_bridge_scored_rows_compile_state_invalid")
            if str(row.get("prediction_sha256") or "") != str(row.get("output_sha256") or ""):
                reasons.append("official_harness_import_bridge_scored_rows_prediction_output_hash_mismatch")
        if suite_id == "tau_bench":
            _validate_tau_bench_scored_row(row, reasons=reasons)
        if suite_id == "mt_bench_work":
            _validate_mt_bench_scored_row(row, reasons=reasons)
    if len(set(case_ids)) != len(case_ids):
        reasons.append("official_harness_import_bridge_scored_rows_case_ids_not_unique")
    if _case_set_digest(str(receipt.get("suite_id") or ""), case_ids) != expected_digest:
        reasons.append("official_harness_import_bridge_scored_rows_case_set_mismatch")
    completed_count = sum(1 for row in rows if str(row.get("status") or "") == "completed")
    passed_count = sum(1 for row in rows if row.get("passed") is True)
    if completed_count != _safe_int(receipt.get("completed_case_count")):
        reasons.append("official_harness_import_bridge_scored_rows_completed_count_mismatch")
    if passed_count != _safe_int(receipt.get("passed_case_count")):
        reasons.append("official_harness_import_bridge_scored_rows_passed_count_mismatch")
    observed_primary_score = (
        round(sum(_safe_float(row.get("score")) for row in rows) / len(rows), 6)
        if suite_id == "mt_bench_work" and rows
        else round(passed_count / len(rows), 6)
        if rows
        else None
    )
    if receipt.get("primary_score") != observed_primary_score:
        reasons.append("official_harness_import_bridge_scored_rows_primary_score_mismatch")
    if suite_id == "ifeval":
        instruction_scores = [
            float(row["instruction_level_score"])
            for row in rows
            if isinstance(row.get("instruction_level_score"), (int, float))
        ]
        observed_instruction_score = (
            round(sum(instruction_scores) / len(instruction_scores), 6)
            if instruction_scores
            else None
        )
        if receipt.get("instruction_level_accuracy") != observed_instruction_score:
            reasons.append("official_harness_import_bridge_scored_rows_instruction_score_summary_mismatch")
    if suite_id == "livecodebench":
        compile_scores = [
            1.0 if row.get("compile_passed") is True else 0.0
            for row in rows
            if isinstance(row.get("compile_passed"), bool)
        ]
        observed_compile_rate = (
            round(sum(compile_scores) / len(compile_scores), 6)
            if compile_scores
            else None
        )
        if receipt.get("compile_rate") != observed_compile_rate:
            reasons.append("official_harness_import_bridge_scored_rows_compile_rate_summary_mismatch")
    if suite_id == "tau_bench":
        tool_action_count = sum(_safe_int(row.get("tool_action_count")) for row in rows)
        tool_error_count = sum(_safe_int(row.get("tool_error_count")) for row in rows)
        observed_tool_error_rate = round(tool_error_count / tool_action_count, 6) if tool_action_count else 0.0
        if _safe_int(receipt.get("tool_action_count")) != tool_action_count:
            reasons.append("official_harness_import_bridge_tau_tool_action_count_mismatch")
        if _safe_int(receipt.get("tool_error_count")) != tool_error_count:
            reasons.append("official_harness_import_bridge_tau_tool_error_count_mismatch")
        if not _safe_ratio_matches(receipt.get("tool_error_rate"), observed_tool_error_rate):
            reasons.append("official_harness_import_bridge_tau_tool_error_rate_mismatch")
        normalization = receipt.get("normalization") if isinstance(receipt.get("normalization"), Mapping) else {}
        if _safe_int(normalization.get("tool_action_count")) != tool_action_count:
            reasons.append("official_harness_import_bridge_tau_normalization_tool_action_count_mismatch")
        if _safe_int(normalization.get("tool_error_count")) != tool_error_count:
            reasons.append("official_harness_import_bridge_tau_normalization_tool_error_count_mismatch")
        if not _safe_ratio_matches(normalization.get("tool_error_rate"), observed_tool_error_rate):
            reasons.append("official_harness_import_bridge_tau_normalization_tool_error_rate_mismatch")


def _validate_tau_bench_scored_row(row: Mapping[str, Any], *, reasons: list[str]) -> None:
    for field in ("tool_action_count", "tool_error_count", "candidate_call_count"):
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"official_harness_import_bridge_tau_{field}_invalid")
    action_count = row.get("tool_action_count")
    error_count = row.get("tool_error_count")
    candidate_call_count = row.get("candidate_call_count")
    if (
        isinstance(action_count, int)
        and isinstance(error_count, int)
        and not isinstance(action_count, bool)
        and not isinstance(error_count, bool)
        and error_count > action_count
    ):
        reasons.append("official_harness_import_bridge_tau_tool_error_count_exceeds_actions")
    if (
        isinstance(candidate_call_count, int)
        and not isinstance(candidate_call_count, bool)
        and candidate_call_count <= 0
    ):
        reasons.append("official_harness_import_bridge_tau_candidate_call_count_invalid")


def _validate_mt_bench_scored_row(row: Mapping[str, Any], *, reasons: list[str]) -> None:
    if row.get("position_balanced") is not True:
        reasons.append("official_harness_import_bridge_mt_bench_position_balance_invalid")
    if not isinstance(row.get("judge_disagreement"), bool):
        reasons.append("official_harness_import_bridge_mt_bench_judge_disagreement_invalid")
    judge_call_count = row.get("judge_call_count")
    if isinstance(judge_call_count, bool) or not isinstance(judge_call_count, int) or judge_call_count != 2:
        reasons.append("official_harness_import_bridge_mt_bench_judge_call_count_invalid")
    if not _looks_like_sha256(row.get("judge_output_sha256")):
        reasons.append("official_harness_import_bridge_mt_bench_judge_output_hash_invalid")


def _validate_tau_bench_normalization(
    receipt: Mapping[str, Any],
    normalization: Mapping[str, Any],
    *,
    reasons: list[str],
) -> None:
    for field in ("tool_action_count", "tool_error_count"):
        value = normalization.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"official_harness_import_bridge_tau_normalization_{field}_invalid")
    if not _safe_ratio(normalization.get("tool_error_rate")):
        reasons.append("official_harness_import_bridge_tau_normalization_tool_error_rate_invalid")
    if not _safe_ratio(receipt.get("tool_error_rate")):
        reasons.append("official_harness_import_bridge_tau_tool_error_rate_invalid")


def _safe_ratio(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= float(value) <= 1.0


def _safe_ratio_matches(value: Any, expected: float) -> bool:
    return _safe_ratio(value) and round(float(value), 6) == round(float(expected), 6)


def _validate_generation_binding_for_import(
    receipt: Mapping[str, Any],
    binding: Mapping[str, Any],
    metadata_rows: Sequence[Mapping[str, Any]],
    scored_rows: Sequence[Mapping[str, Any]],
    *,
    reasons: list[str],
) -> None:
    if str(binding.get("schema") or "") != "axio_fusion_api.official_harness_generation_binding.v1":
        reasons.append("official_harness_import_bridge_generation_binding_schema_invalid")
    declared_digest = str(binding.get("generation_binding_digest_sha256") or "")
    if not _looks_like_sha256(declared_digest) or declared_digest != _generation_binding_digest(binding):
        reasons.append("official_harness_import_bridge_generation_binding_digest_invalid")
    if declared_digest != str(receipt.get("generation_binding_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_generation_binding_receipt_mismatch")
    for field, expected in (
        ("suite_id", str(receipt.get("suite_id") or "")),
        ("task_format", str(receipt.get("task_format") or "")),
        ("candidate_kind", str(receipt.get("candidate_kind") or "")),
        ("api_format", str(receipt.get("api_format") or "")),
        ("case_set_digest_sha256", str(receipt.get("case_set_digest_sha256") or "")),
    ):
        if str(binding.get(field) or "") != expected:
            reasons.append(f"official_harness_import_bridge_generation_binding_{field}_mismatch")
    if str(binding.get("candidate_id_sha256") or "") != sha256_text(str(receipt.get("candidate_id") or "")):
        reasons.append("official_harness_import_bridge_generation_binding_candidate_mismatch")
    candidate_binding = receipt.get("candidate_binding") if isinstance(receipt.get("candidate_binding"), Mapping) else {}
    if str(binding.get("profile_id_sha256") or "") != str(candidate_binding.get("profile_id_sha256") or ""):
        reasons.append("official_harness_import_bridge_generation_binding_profile_mismatch")
    protocol = receipt.get("generation_protocol") if isinstance(receipt.get("generation_protocol"), Mapping) else {}
    if str(binding.get("generation_protocol_digest_sha256") or "") != str(protocol.get("generation_protocol_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_generation_binding_protocol_mismatch")
    if _safe_int(binding.get("max_output_tokens")) != _safe_int(protocol.get("max_output_tokens")):
        reasons.append("official_harness_import_bridge_generation_binding_output_budget_mismatch")
    if _safe_int(binding.get("case_count")) != _safe_int(receipt.get("case_count")):
        reasons.append("official_harness_import_bridge_generation_binding_case_count_mismatch")
    if str(binding.get("metadata_digest_sha256") or "") != sha256_text(stable_json(list(metadata_rows))):
        reasons.append("official_harness_import_bridge_generation_metadata_digest_mismatch")
    if len(metadata_rows) != _safe_int(receipt.get("case_count")):
        reasons.append("official_harness_import_bridge_generation_metadata_case_count_mismatch")
    metadata_case_ids: list[str] = []
    metadata_output_hashes: dict[str, str] = {}
    for row in metadata_rows:
        unexpected = set(row) - _SAFE_GENERATION_METADATA_FIELDS
        if unexpected:
            reasons.append("official_harness_import_bridge_generation_metadata_unsafe_fields")
        if _contains_true_flag(row):
            reasons.append("official_harness_import_bridge_generation_metadata_raw_content_flagged")
        case_id = str(row.get("case_id") or "")
        metadata_case_ids.append(case_id)
        if not _looks_like_sha256(case_id) or str(row.get("status") or "") != "completed":
            reasons.append("official_harness_import_bridge_generation_metadata_row_invalid")
        if not _looks_like_sha256(row.get("output_sha256")) or str(row.get("error_type") or ""):
            reasons.append("official_harness_import_bridge_generation_metadata_output_invalid")
        metadata_output_hashes[case_id] = str(row.get("output_sha256") or "")
    scored_case_ids = [str(row.get("case_id") or "") for row in scored_rows]
    if len(metadata_case_ids) != len(scored_case_ids) or set(metadata_case_ids) != set(scored_case_ids):
        reasons.append("official_harness_import_bridge_generation_metadata_case_set_mismatch")
    for row in scored_rows:
        case_id = str(row.get("case_id") or "")
        if metadata_output_hashes.get(case_id) != str(row.get("output_sha256") or ""):
            reasons.append("official_harness_import_bridge_generation_metadata_output_hash_mismatch")
    if _contains_true_flag(binding):
        reasons.append("official_harness_import_bridge_generation_binding_raw_content_flagged")


def _validate_mt_bench_import_artifacts(
    *,
    private_root: Path,
    receipt: Mapping[str, Any],
    scored_rows: Sequence[Mapping[str, Any]],
    metadata_rows: Sequence[Mapping[str, Any]],
    generation_binding: Mapping[str, Any],
    mt_side: str,
    reasons: list[str],
) -> None:
    """Validate both sides of a position-balanced MT-Bench match before import."""

    selected_side = str(mt_side or "").strip().lower()
    receipt_side = str(receipt.get("mt_bench_side") or "").strip().lower()
    if selected_side not in {"target", "comparison"} or receipt_side != selected_side:
        reasons.append("official_harness_import_bridge_mt_bench_import_side_mismatch")
        return
    target_receipt_path = private_root / _EVALUATION_RECEIPT_FILENAME
    comparison_receipt_path = private_root / _MT_BENCH_COMPARISON_EVALUATION_RECEIPT_FILENAME
    target_scored_path = private_root / _SCORED_ROWS_FILENAME
    comparison_scored_path = private_root / _MT_BENCH_COMPARISON_SCORED_ROWS_FILENAME
    target_metadata_path = private_root / "generation.safe.jsonl"
    comparison_metadata_path = private_root / _MT_BENCH_COMPARISON_METADATA_FILENAME
    target_binding_path = private_root / _GENERATION_BINDING_FILENAME
    comparison_binding_path = private_root / _MT_BENCH_COMPARISON_GENERATION_BINDING_FILENAME
    pair_binding_path = private_root / _MT_BENCH_PAIR_BINDING_FILENAME
    judgment_receipts_path = private_root / _MT_BENCH_JUDGMENT_RECEIPTS_FILENAME

    target_receipt = _load_private_json_object(
        target_receipt_path,
        missing_reason="official_harness_import_bridge_mt_bench_target_receipt_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_target_receipt_unreadable",
        reasons=reasons,
    )
    comparison_receipt = _load_private_json_object(
        comparison_receipt_path,
        missing_reason="official_harness_import_bridge_mt_bench_comparison_receipt_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_comparison_receipt_unreadable",
        reasons=reasons,
    )
    target_rows = _load_private_jsonl_rows(
        target_scored_path,
        missing_reason="official_harness_import_bridge_mt_bench_target_scored_rows_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_target_scored_rows_unreadable",
        reasons=reasons,
    )
    comparison_rows = _load_private_jsonl_rows(
        comparison_scored_path,
        missing_reason="official_harness_import_bridge_mt_bench_comparison_scored_rows_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_comparison_scored_rows_unreadable",
        reasons=reasons,
    )
    target_metadata = _load_private_jsonl_rows(
        target_metadata_path,
        missing_reason="official_harness_import_bridge_mt_bench_target_metadata_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_target_metadata_unreadable",
        reasons=reasons,
    )
    comparison_metadata = _load_private_jsonl_rows(
        comparison_metadata_path,
        missing_reason="official_harness_import_bridge_mt_bench_comparison_metadata_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_comparison_metadata_unreadable",
        reasons=reasons,
    )
    target_binding = _load_private_json_object(
        target_binding_path,
        missing_reason="official_harness_import_bridge_mt_bench_target_generation_binding_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_target_generation_binding_unreadable",
        reasons=reasons,
    )
    comparison_binding = _load_private_json_object(
        comparison_binding_path,
        missing_reason="official_harness_import_bridge_mt_bench_comparison_generation_binding_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_comparison_generation_binding_unreadable",
        reasons=reasons,
    )
    pair_binding = _load_private_json_object(
        pair_binding_path,
        missing_reason="official_harness_import_bridge_mt_bench_pair_binding_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_pair_binding_unreadable",
        reasons=reasons,
    )
    judgment_rows = _load_private_jsonl_rows(
        judgment_receipts_path,
        missing_reason="official_harness_import_bridge_mt_bench_judgment_receipts_missing",
        unreadable_reason="official_harness_import_bridge_mt_bench_judgment_receipts_unreadable",
        reasons=reasons,
    )
    if not target_receipt or not comparison_receipt:
        return

    for side_name, side_receipt, side_path, side_rows, side_metadata, side_binding in (
        ("target", target_receipt, target_scored_path, target_rows, target_metadata, target_binding),
        (
            "comparison",
            comparison_receipt,
            comparison_scored_path,
            comparison_rows,
            comparison_metadata,
            comparison_binding,
        ),
    ):
        _validate_evaluation_receipt(
            side_receipt,
            receipt_path=(target_receipt_path if side_name == "target" else comparison_receipt_path),
            scored_path=side_path,
            reasons=reasons,
        )
        import_binding = (
            side_receipt.get("official_import_binding")
            if isinstance(side_receipt.get("official_import_binding"), Mapping)
            else {}
        )
        _validate_official_import_binding(
            side_receipt,
            import_binding,
            scored_path=side_path,
            reasons=reasons,
        )
        _validate_scored_rows(side_receipt, side_rows, reasons=reasons)
        _validate_generation_binding_for_import(
            side_receipt,
            side_binding,
            side_metadata,
            side_rows,
            reasons=reasons,
        )
        if str(side_receipt.get("mt_bench_side") or "") != side_name:
            reasons.append("official_harness_import_bridge_mt_bench_side_receipt_mismatch")

    if str(receipt.get("candidate_id") or "") != str(
        (target_receipt if selected_side == "target" else comparison_receipt).get("candidate_id") or ""
    ):
        reasons.append("official_harness_import_bridge_mt_bench_selected_receipt_candidate_mismatch")
    selected_rows = target_rows if selected_side == "target" else comparison_rows
    if stable_json(list(scored_rows)) != stable_json(selected_rows):
        reasons.append("official_harness_import_bridge_mt_bench_selected_scored_rows_mismatch")
    if stable_json(list(metadata_rows)) != stable_json(
        target_metadata if selected_side == "target" else comparison_metadata
    ):
        reasons.append("official_harness_import_bridge_mt_bench_selected_metadata_mismatch")
    if stable_json(dict(generation_binding)) != stable_json(
        target_binding if selected_side == "target" else comparison_binding
    ):
        reasons.append("official_harness_import_bridge_mt_bench_selected_generation_binding_mismatch")

    _validate_mt_bench_pair_binding_for_import(
        pair_binding,
        target_receipt=target_receipt,
        comparison_receipt=comparison_receipt,
        target_metadata=target_metadata,
        comparison_metadata=comparison_metadata,
        target_binding=target_binding,
        comparison_binding=comparison_binding,
        reasons=reasons,
    )
    _validate_mt_bench_judgment_receipts(
        judgment_rows,
        target_rows=target_rows,
        comparison_rows=comparison_rows,
        target_receipt=target_receipt,
        comparison_receipt=comparison_receipt,
        reasons=reasons,
    )


def _validate_mt_bench_pair_binding_for_import(
    binding: Mapping[str, Any],
    *,
    target_receipt: Mapping[str, Any],
    comparison_receipt: Mapping[str, Any],
    target_metadata: Sequence[Mapping[str, Any]],
    comparison_metadata: Sequence[Mapping[str, Any]],
    target_binding: Mapping[str, Any],
    comparison_binding: Mapping[str, Any],
    reasons: list[str],
) -> None:
    if str(binding.get("schema") or "") != "axio_fusion_api.mt_bench_pair_binding.v1":
        reasons.append("official_harness_import_bridge_mt_bench_pair_binding_schema_invalid")
    declared_digest = str(binding.get("pair_binding_digest_sha256") or "")
    body = dict(binding)
    body.pop("pair_binding_digest_sha256", None)
    if not _looks_like_sha256(declared_digest) or declared_digest != sha256_text(stable_json(body)):
        reasons.append("official_harness_import_bridge_mt_bench_pair_binding_digest_invalid")
    if str(target_receipt.get("mt_bench_pair_binding_digest_sha256") or "") != declared_digest:
        reasons.append("official_harness_import_bridge_mt_bench_target_pair_binding_mismatch")
    if str(comparison_receipt.get("mt_bench_pair_binding_digest_sha256") or "") != declared_digest:
        reasons.append("official_harness_import_bridge_mt_bench_comparison_pair_binding_mismatch")
    expected_values = {
        "suite_id": "mt_bench_work",
        "case_count": _safe_int(target_receipt.get("case_count")),
        "case_set_digest_sha256": str(target_receipt.get("case_set_digest_sha256") or ""),
        "target_candidate_id_sha256": sha256_text(str(target_receipt.get("candidate_id") or "")),
        "comparison_candidate_id_sha256": sha256_text(str(comparison_receipt.get("candidate_id") or "")),
        "target_generation_metadata_digest_sha256": sha256_text(stable_json(list(target_metadata))),
        "comparison_generation_metadata_digest_sha256": sha256_text(stable_json(list(comparison_metadata))),
        "target_generation_binding_digest_sha256": str(
            target_binding.get("generation_binding_digest_sha256") or ""
        ),
        "comparison_generation_binding_digest_sha256": str(
            comparison_binding.get("generation_binding_digest_sha256") or ""
        ),
        "target_generation_protocol_digest_sha256": str(
            (target_receipt.get("generation_protocol") or {}).get("generation_protocol_digest_sha256")
            if isinstance(target_receipt.get("generation_protocol"), Mapping)
            else ""
        ),
        "comparison_generation_protocol_digest_sha256": str(
            (comparison_receipt.get("generation_protocol") or {}).get(
                "generation_protocol_digest_sha256"
            )
            if isinstance(comparison_receipt.get("generation_protocol"), Mapping)
            else ""
        ),
    }
    for field, expected in expected_values.items():
        if binding.get(field) != expected:
            reasons.append(f"official_harness_import_bridge_mt_bench_pair_binding_{field}_mismatch")
    if _safe_int(comparison_receipt.get("case_count")) != _safe_int(target_receipt.get("case_count")):
        reasons.append("official_harness_import_bridge_mt_bench_pair_case_count_mismatch")
    if str(comparison_receipt.get("case_set_digest_sha256") or "") != str(
        target_receipt.get("case_set_digest_sha256") or ""
    ):
        reasons.append("official_harness_import_bridge_mt_bench_pair_case_set_mismatch")
    if binding.get("two_turn_dialogue") is not True:
        reasons.append("official_harness_import_bridge_mt_bench_pair_two_turn_invalid")
    if binding.get("position_balanced") is not True or _safe_int(binding.get("judge_calls_per_case")) != 2:
        reasons.append("official_harness_import_bridge_mt_bench_pair_position_balance_invalid")
    if binding.get("judge_cross_provider_from_target") is not True:
        reasons.append("official_harness_import_bridge_mt_bench_pair_judge_target_independence_invalid")
    if binding.get("judge_cross_provider_from_comparison") is not True:
        reasons.append("official_harness_import_bridge_mt_bench_pair_judge_comparison_independence_invalid")
    if _contains_true_flag(binding):
        reasons.append("official_harness_import_bridge_mt_bench_pair_raw_content_flagged")


def _validate_mt_bench_judgment_receipts(
    rows: Sequence[Mapping[str, Any]],
    *,
    target_rows: Sequence[Mapping[str, Any]],
    comparison_rows: Sequence[Mapping[str, Any]],
    target_receipt: Mapping[str, Any],
    comparison_receipt: Mapping[str, Any],
    reasons: list[str],
) -> None:
    expected_count = _safe_int(target_receipt.get("case_count"))
    if len(rows) != expected_count:
        reasons.append("official_harness_import_bridge_mt_bench_judgment_case_count_mismatch")
    expected_digest = sha256_text(stable_json(list(rows)))
    for side_receipt in (target_receipt, comparison_receipt):
        if str(side_receipt.get("judge_output_digest_sha256") or "") != expected_digest:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_digest_mismatch")
        if _safe_int(side_receipt.get("judge_call_count")) != expected_count * 2:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_call_count_mismatch")
    judgment_by_case: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        unexpected = set(row) - _SAFE_MT_BENCH_JUDGMENT_RECEIPT_FIELDS
        if unexpected:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_receipt_unsafe_fields")
        if _contains_true_flag(row):
            reasons.append("official_harness_import_bridge_mt_bench_judgment_receipt_raw_content_flagged")
        case_id = str(row.get("case_id") or "")
        if not _looks_like_sha256(case_id) or case_id in judgment_by_case:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_case_id_invalid")
        judgment_by_case[case_id] = row
        if str(row.get("status") or "") != "completed" or str(row.get("error_type") or ""):
            reasons.append("official_harness_import_bridge_mt_bench_judgment_not_completed")
        if row.get("position_balanced") is not True or _safe_int(row.get("judge_call_count")) != 2:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_position_balance_invalid")
        if not isinstance(row.get("judge_disagreement"), bool):
            reasons.append("official_harness_import_bridge_mt_bench_judgment_disagreement_invalid")
        if not _looks_like_sha256(row.get("judge_output_sha256")) or not _looks_like_sha256(
            row.get("judge_prompt_sha256")
        ):
            reasons.append("official_harness_import_bridge_mt_bench_judgment_hash_invalid")
        if str(row.get("first_position_outcome") or "") not in {"target", "comparison", "tie"}:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_first_outcome_invalid")
        if str(row.get("second_position_outcome") or "") not in {"target", "comparison", "tie"}:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_second_outcome_invalid")
        if str(row.get("final_outcome") or "") not in {"target", "comparison", "tie"}:
            reasons.append("official_harness_import_bridge_mt_bench_judgment_final_outcome_invalid")
    target_by_case = {str(row.get("case_id") or ""): row for row in target_rows}
    comparison_by_case = {str(row.get("case_id") or ""): row for row in comparison_rows}
    if set(target_by_case) != set(judgment_by_case) or set(comparison_by_case) != set(judgment_by_case):
        reasons.append("official_harness_import_bridge_mt_bench_judgment_case_set_mismatch")
    for case_id, judgment in judgment_by_case.items():
        target_row = target_by_case.get(case_id, {})
        comparison_row = comparison_by_case.get(case_id, {})
        if _safe_float(target_row.get("score")) + _safe_float(comparison_row.get("score")) != 1.0:
            reasons.append("official_harness_import_bridge_mt_bench_pair_score_not_complementary")
        for side_name, row in (("target", target_row), ("comparison", comparison_row)):
            expected_score = (
                1.0
                if judgment.get("final_outcome") == side_name
                else 0.5
                if judgment.get("final_outcome") == "tie"
                else 0.0
            )
            if _safe_float(row.get("score")) != expected_score:
                reasons.append("official_harness_import_bridge_mt_bench_judgment_score_mismatch")
            if str(row.get("judge_output_sha256") or "") != str(judgment.get("judge_output_sha256") or ""):
                reasons.append("official_harness_import_bridge_mt_bench_judgment_output_hash_mismatch")


def _official_harness_import_bridge_validation(
    *,
    private_root: Path,
    receipt_path: Path,
    scored_path: Path,
    receipt: Mapping[str, Any],
    import_binding: Mapping[str, Any],
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "ready": not reasons,
        "reason_codes": sorted(set(str(reason) for reason in reasons if reason)),
        "private_run_dir_sha256": sha256_text(str(private_root)),
        "evaluation_receipt_path_sha256": sha256_text(str(receipt_path)),
        "safe_scored_rows_path_sha256": sha256_text(str(scored_path)),
        "evaluation_receipt_digest_sha256": str(receipt.get("evaluation_receipt_digest_sha256") or ""),
        "safe_scored_rows_digest_sha256": str(receipt.get("safe_scored_rows_digest_sha256") or ""),
        "generation_binding_digest_sha256": str(receipt.get("generation_binding_digest_sha256") or ""),
        "candidate_id_sha256": sha256_text(str(receipt.get("candidate_id") or "")) if receipt.get("candidate_id") else "",
        "candidate_kind": str(receipt.get("candidate_kind") or ""),
        "api_format": str(receipt.get("api_format") or ""),
        "case_count": _safe_int(receipt.get("case_count")),
        "case_set_digest_sha256": str(receipt.get("case_set_digest_sha256") or ""),
        "official_import_binding_digest_sha256": sha256_text(stable_json(dict(import_binding))) if import_binding else "",
        "raw_private_run_path_persisted": False,
        "raw_evaluation_receipt_path_persisted": False,
        "raw_scored_rows_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _safe_official_harness_import_bridge_receipt(
    *,
    private_root: Path,
    receipt_path: Path,
    scored_path: Path,
    receipt: Mapping[str, Any],
    import_binding: Mapping[str, Any],
    validation: Mapping[str, Any],
    mt_side: str = "target",
) -> dict[str, Any]:
    freeze = receipt.get("provider_baseline_freeze_binding") if isinstance(receipt.get("provider_baseline_freeze_binding"), Mapping) else {}
    return {
        "schema": _IMPORT_BRIDGE_SCHEMA,
        "status": "imported",
        "automatic_binding_transfer": True,
        "manual_candidate_or_harness_fields_accepted": False,
        "private_run_dir_sha256": sha256_text(str(private_root)),
        "evaluation_receipt_path_sha256": sha256_text(str(receipt_path)),
        "evaluation_receipt_digest_sha256": str(validation.get("evaluation_receipt_digest_sha256") or ""),
        "safe_scored_rows_path_sha256": sha256_text(str(scored_path)),
        "safe_scored_rows_digest_sha256": str(validation.get("safe_scored_rows_digest_sha256") or ""),
        "generation_binding_digest_sha256": str(validation.get("generation_binding_digest_sha256") or ""),
        "candidate_id_sha256": str(validation.get("candidate_id_sha256") or ""),
        "candidate_kind": str(validation.get("candidate_kind") or ""),
        "api_format": str(validation.get("api_format") or ""),
        "case_count": _safe_int(validation.get("case_count")),
        "case_set_digest_sha256": str(validation.get("case_set_digest_sha256") or ""),
        "harness_name_sha256": str(import_binding.get("harness_name_sha256") or ""),
        "harness_version_sha256": str(import_binding.get("harness_version_sha256") or ""),
        "dataset_snapshot_sha256": str(import_binding.get("dataset_snapshot_sha256") or ""),
        "evaluator_config_sha256": str(import_binding.get("evaluator_config_sha256") or ""),
        "prompt_protocol_sha256": str(import_binding.get("prompt_protocol_sha256") or ""),
        "decoding_config_sha256": str(import_binding.get("decoding_config_sha256") or ""),
        "position_balanced": import_binding.get("position_balanced") is True,
        "mt_bench_import_side": str(mt_side) if str(receipt.get("suite_id") or "") == "mt_bench_work" else "",
        "provider_baseline_freeze_manifest_digest_sha256": str(freeze.get("manifest_digest_sha256") or ""),
        "provider_baseline_candidate_frozen": freeze.get("candidate_frozen") if freeze.get("required") is True else None,
        "raw_private_run_path_persisted": False,
        "raw_evaluation_receipt_path_persisted": False,
        "raw_scored_rows_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _official_harness_imported_run_reasons(
    run: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any],
    import_binding: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    candidate_id = str(receipt.get("candidate_id") or "")
    if str(run.get("suite_id") or "") != str(receipt.get("suite_id") or ""):
        reasons.append("official_harness_import_bridge_imported_suite_mismatch")
    if str(run.get("candidate_id") or "") != candidate_id:
        reasons.append("official_harness_import_bridge_imported_candidate_mismatch")
    if str(run.get("task_format") or "") != str(receipt.get("task_format") or ""):
        reasons.append("official_harness_import_bridge_imported_task_format_mismatch")
    expected_api_format = str(receipt.get("api_format") or "")
    if str(receipt.get("candidate_kind") or "") == "provider_native":
        if str(run.get("api_format") or "") != "provider_native":
            reasons.append("official_harness_import_bridge_imported_provider_api_format_mismatch")
    elif str(run.get("api_format") or "") != expected_api_format:
        reasons.append("official_harness_import_bridge_imported_api_format_mismatch")
    if _safe_int(run.get("case_count")) != _safe_int(validation.get("case_count")):
        reasons.append("official_harness_import_bridge_imported_case_count_mismatch")
    run_case_ids = [str(row.get("case_id") or "") for row in run.get("case_results", []) if isinstance(row, Mapping)]
    if _case_set_digest(str(receipt.get("suite_id") or ""), run_case_ids) != str(validation.get("case_set_digest_sha256") or ""):
        reasons.append("official_harness_import_bridge_imported_case_set_mismatch")
    for field in ("prompt_protocol_sha256", "decoding_config_sha256"):
        if str(run.get(field) or "") != str(import_binding.get(field) or ""):
            reasons.append(f"official_harness_import_bridge_imported_{field}_mismatch")
    harness = run.get("harness_receipt") if isinstance(run.get("harness_receipt"), Mapping) else {}
    for source_field, run_field in (
        ("harness_name_sha256", "harness_name_sha256"),
        ("harness_version_sha256", "harness_version_sha256"),
        ("dataset_snapshot_sha256", "dataset_snapshot_sha256"),
        ("evaluator_config_sha256", "evaluator_config_sha256"),
        ("prompt_protocol_sha256", "prompt_protocol_sha256"),
        ("decoding_config_sha256", "decoding_config_sha256"),
    ):
        if str(harness.get(run_field) or "") != str(import_binding.get(source_field) or ""):
            reasons.append(f"official_harness_import_bridge_imported_{run_field}_mismatch")
    if harness.get("official_or_audited_harness") is not True or harness.get("final_claim_eligible") is not True:
        reasons.append("official_harness_import_bridge_imported_harness_not_final_claim_eligible")
    if _contains_true_flag(run):
        reasons.append("official_harness_import_bridge_imported_run_raw_content_flagged")
    return sorted(set(reasons))


def _official_harness_import_bridge_blocked_receipt(
    *,
    private_root: Path,
    receipt_path: Path,
    scored_path: Path,
    validation: Mapping[str, Any],
    reason_codes: Sequence[str] = (),
    error_type: str = "",
) -> dict[str, Any]:
    all_reasons = [*validation.get("reason_codes", []), *reason_codes]
    return {
        "schema": _IMPORT_BRIDGE_SCHEMA,
        "status": "blocked",
        "private_run_dir_sha256": sha256_text(str(private_root)),
        "evaluation_receipt_path_sha256": sha256_text(str(receipt_path)),
        "safe_scored_rows_path_sha256": sha256_text(str(scored_path)),
        "candidate_id_sha256": str(validation.get("candidate_id_sha256") or ""),
        "candidate_kind": str(validation.get("candidate_kind") or ""),
        "api_format": str(validation.get("api_format") or ""),
        "case_count": _safe_int(validation.get("case_count")),
        "case_set_digest_sha256": str(validation.get("case_set_digest_sha256") or ""),
        "error_type": str(error_type or "")[:120],
        "reason_codes": sorted(set(str(reason) for reason in all_reasons if reason)),
        "model_calls_performed": False,
        "official_harness_execution_performed": False,
        "raw_private_run_path_persisted": False,
        "raw_evaluation_receipt_path_persisted": False,
        "raw_scored_rows_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _bridge_candidate_kind(candidate_id: str) -> str:
    if candidate_id in PUBLIC_MODELS:
        return "public_axio"
    if candidate_id.startswith(_PROVIDER_CANDIDATE_PREFIX) and _looks_like_sha256(
        candidate_id[len(_PROVIDER_CANDIDATE_PREFIX) :]
    ):
        return "provider_native"
    return ""


def _evaluation_receipt_digest(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("evaluation_receipt_digest_sha256", None)
    return sha256_text(stable_json(payload))


def _generation_protocol_digest(protocol: Mapping[str, Any]) -> str:
    payload = dict(protocol)
    payload.pop("generation_protocol_digest_sha256", None)
    return sha256_text(stable_json(payload))


def _generation_binding_digest(binding: Mapping[str, Any]) -> str:
    payload = dict(binding)
    payload.pop("generation_binding_digest_sha256", None)
    return sha256_text(stable_json(payload))


_SAFE_SCORED_ROW_FIELDS = frozenset(
    {
        "case_index",
        "case_id",
        "status",
        "passed",
        "correct",
        "score",
        "metric",
        "latency_ms",
        "prediction_sha256",
        "output_sha256",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "pricing_known",
        "provider_call_count",
        "error_type",
        "instruction_level_score",
        "instruction_count",
        "compile_passed",
        "tool_action_count",
        "tool_error_count",
        "candidate_call_count",
        "position_balanced",
        "judge_disagreement",
        "judge_call_count",
        "judge_output_sha256",
        "public_api_invocation",
        "raw_input_persisted",
        "raw_reference_persisted",
        "raw_label_persisted",
        "raw_model_output_persisted",
        "raw_provider_outputs_persisted",
        "secrets_persisted",
    }
)
_SAFE_GENERATION_METADATA_FIELDS = frozenset(
    {
        "case_index",
        "case_id",
        "status",
        "error_type",
        "latency_ms",
        "output_sha256",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "pricing_known",
        "provider_call_count",
        "public_api_invocation",
        "raw_prompt_persisted",
        "raw_model_output_persisted",
        "raw_provider_outputs_persisted",
        "secrets_persisted",
    }
)
_SAFE_MT_BENCH_JUDGMENT_RECEIPT_FIELDS = frozenset(
    {
        "case_index",
        "case_id",
        "status",
        "error_type",
        "judge_template_sha256",
        "reference_answer_used",
        "position_balanced",
        "judge_call_count",
        "first_position_outcome",
        "second_position_outcome",
        "final_outcome",
        "judge_disagreement",
        "judge_prompt_sha256",
        "judge_output_sha256",
        "judge_latency_ms",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "pricing_known",
        "provider_call_count",
        "raw_prompt_persisted",
        "raw_reference_persisted",
        "raw_judge_output_persisted",
        "raw_provider_outputs_persisted",
        "secrets_persisted",
    }
)


def _official_source_inventory(
    path: Path,
    *,
    suite_id: str,
    limit: int | None,
    tau_environments: Sequence[str] = (),
) -> dict[str, Any]:
    reasons: list[str] = []
    parser = _source_parser_name(suite_id)
    if not parser:
        reasons.append("official_harness_bridge_source_parser_not_supported")
        return {
            "source_parser": "",
            "case_count": 0,
            "source_row_count": 0,
            "invalid_source_row_count": 0,
            "case_set_digest_sha256": "",
            "reason_codes": reasons,
        }
    if not path.is_file() and not (suite_id in {"bfcl", "tau_bench"} and path.is_dir()):
        if suite_id == "livecodebench" and path.is_dir():
            path = path / "test_generation.parquet"
        if path.is_file():
            return _official_source_inventory(
                path,
                suite_id=suite_id,
                limit=limit,
                tau_environments=tau_environments,
            )
        reasons.append("official_harness_dataset_not_found")
        return {
            "source_parser": parser,
            "case_count": 0,
            "source_row_count": 0,
            "invalid_source_row_count": 0,
            "case_set_digest_sha256": "",
            "reason_codes": reasons,
        }
    if suite_id == "tau_bench":
        try:
            cases, source_row_count, invalid_row_count = _load_tau_bench_source_cases(
                path,
                limit=limit,
                environments=tau_environments,
            )
        except _TauBenchSourceError as exc:
            reasons.append(exc.reason_code)
            return {
                "source_parser": parser,
                "case_count": 0,
                "source_row_count": 0,
                "invalid_source_row_count": 0,
                "case_set_digest_sha256": "",
                "reason_codes": sorted(set(reasons)),
            }
        if invalid_row_count:
            reasons.append("official_harness_tau_bench_invalid_rows")
        case_ids = [str(case["case_id"]) for case in cases]
        if not case_ids:
            reasons.append("official_harness_case_set_empty")
        return {
            "source_parser": parser,
            "case_count": len(case_ids),
            "source_row_count": source_row_count,
            "invalid_source_row_count": invalid_row_count,
            "case_set_digest_sha256": _case_set_digest(suite_id, case_ids),
            "reason_codes": sorted(set(reasons)),
        }
    if suite_id == "mt_bench_work":
        try:
            cases, source_row_count, invalid_row_count = _load_mt_bench_source_cases(path, limit=limit)
        except _MTBenchSourceError as exc:
            reasons.append(exc.reason_code)
            return {
                "source_parser": parser,
                "case_count": 0,
                "source_row_count": 0,
                "invalid_source_row_count": 0,
                "case_set_digest_sha256": "",
                "reason_codes": sorted(set(reasons)),
            }
        if invalid_row_count:
            reasons.append("official_harness_mt_bench_invalid_rows")
        case_ids = [str(case["case_id"]) for case in cases]
        if not case_ids:
            reasons.append("official_harness_case_set_empty")
        return {
            "source_parser": parser,
            "case_count": len(case_ids),
            "source_row_count": source_row_count,
            "invalid_source_row_count": invalid_row_count,
            "case_set_digest_sha256": _case_set_digest(suite_id, case_ids),
            "reason_codes": sorted(set(reasons)),
        }
    if suite_id == "bfcl":
        try:
            cases, source_row_count, invalid_row_count = _load_bfcl_source_cases(path, limit=limit)
        except _BFCLSourceError as exc:
            reasons.append(exc.reason_code)
            return {
                "source_parser": parser,
                "case_count": 0,
                "source_row_count": 0,
                "invalid_source_row_count": 0,
                "case_set_digest_sha256": "",
                "reason_codes": sorted(set(reasons)),
            }
        if invalid_row_count:
            reasons.append("official_harness_bfcl_invalid_rows")
        case_ids = [str(case["case_id"]) for case in cases]
        if not case_ids:
            reasons.append("official_harness_case_set_empty")
        return {
            "source_parser": parser,
            "case_count": len(case_ids),
            "source_row_count": source_row_count,
            "invalid_source_row_count": invalid_row_count,
            "case_set_digest_sha256": _case_set_digest(suite_id, case_ids),
            "reason_codes": sorted(set(reasons)),
        }

    if suite_id == "livecodebench":
        try:
            cases, source_row_count, invalid_row_count = _load_livecodebench_source_cases(path, limit=limit)
        except _LiveCodeBenchSourceError as exc:
            reasons.append(exc.reason_code)
            return {
                "source_parser": parser,
                "case_count": 0,
                "source_row_count": 0,
                "invalid_source_row_count": 0,
                "case_set_digest_sha256": "",
                "reason_codes": sorted(set(reasons)),
            }
        if invalid_row_count:
            reasons.append("official_harness_livecodebench_invalid_rows")
        case_ids = [str(case["case_id"]) for case in cases]
        if not case_ids:
            reasons.append("official_harness_case_set_empty")
        return {
            "source_parser": parser,
            "case_count": len(case_ids),
            "source_row_count": source_row_count,
            "invalid_source_row_count": invalid_row_count,
            "case_set_digest_sha256": _case_set_digest(suite_id, case_ids),
            "reason_codes": sorted(set(reasons)),
        }

    case_ids: list[str] = []
    source_rows = 0
    invalid_rows = 0
    try:
        for row in _iter_private_jsonl(path):
            source_rows += 1
            identifier = _source_case_identifier(row, suite_id=suite_id)
            if identifier in (None, ""):
                invalid_rows += 1
                continue
            case_ids.append(_official_case_id(suite_id, identifier))
            if limit is not None and len(case_ids) >= int(limit):
                break
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reasons.append("official_harness_dataset_unreadable")
    if invalid_rows:
        reasons.append("official_harness_dataset_invalid_rows")
    unique_ids = sorted(set(case_ids))
    if len(unique_ids) != len(case_ids):
        reasons.append("official_harness_case_identifiers_not_unique")
    if not unique_ids:
        reasons.append("official_harness_case_set_empty")
    return {
        "source_parser": parser,
        "case_count": len(unique_ids),
        "source_row_count": source_rows,
        "invalid_source_row_count": invalid_rows,
        "case_set_digest_sha256": _case_set_digest(suite_id, unique_ids),
        "reason_codes": reasons,
    }


def _load_private_source_cases(path: Path, *, suite_id: str, limit: int | None) -> list[dict[str, Any]]:
    if suite_id == "tau_bench":
        cases, _, invalid_row_count = _load_tau_bench_source_cases(
            path,
            limit=limit,
            environments=_TAU_BENCH_ENVIRONMENTS,
        )
        if invalid_row_count:
            raise ValueError("official_harness_tau_bench_invalid_rows")
        return cases
    if suite_id == "mt_bench_work":
        cases, _, invalid_row_count = _load_mt_bench_source_cases(path, limit=limit)
        if invalid_row_count:
            raise ValueError("official_harness_mt_bench_invalid_rows")
        return cases
    if suite_id == "bfcl":
        cases, _, invalid_row_count = _load_bfcl_source_cases(path, limit=limit)
        if invalid_row_count:
            raise ValueError("official_harness_bfcl_invalid_rows")
        return cases
    if suite_id == "livecodebench":
        cases, _, invalid_row_count = _load_livecodebench_source_cases(path, limit=limit)
        if invalid_row_count:
            raise ValueError("official_harness_livecodebench_invalid_rows")
        return cases
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _iter_private_jsonl(path):
        identifier = _source_case_identifier(row, suite_id=suite_id)
        prompt = str(row.get("prompt") or "")
        if identifier in (None, "") or not prompt:
            raise ValueError("official_source_case_missing_identifier_or_prompt")
        case_id = _official_case_id(suite_id, identifier)
        if case_id in seen:
            raise ValueError("official_source_case_identifier_duplicate")
        seen.add(case_id)
        cases.append(
            {
                "case_id": case_id,
                "source_identifier": str(identifier),
                "prompt": prompt,
            }
        )
        if limit is not None and len(cases) >= int(limit):
            break
    if not cases:
        raise ValueError("official_source_case_set_empty")
    return cases


def _iter_private_jsonl(path: Path):
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, Mapping):
                raise ValueError("official_source_row_not_object")
            yield dict(payload)


def _source_case_identifier(row: Mapping[str, Any], *, suite_id: str) -> Any:
    if suite_id == "livecodebench":
        return row.get("question_id")
    if suite_id == "humaneval":
        return row.get("task_id")
    if suite_id == "ifeval":
        return row.get("key")
    if suite_id == "mt_bench_work":
        return row.get("question_id")
    return None


def _source_parser_name(suite_id: str) -> str:
    return {
        "livecodebench": "livecodebench_parquet_question_id_v1",
        "humaneval": "humaneval_task_id_v1",
        "ifeval": "ifeval_key_v1",
        "bfcl": "bfcl_v3_native_tool_call_ast_v1",
        "tau_bench": "tau_bench_static_task_index_v1",
        "mt_bench_work": "mt_bench_question_id_two_turn_v1",
    }.get(suite_id, "")


class _LiveCodeBenchSourceError(ValueError):
    """Private source parsing failure that becomes a safe preflight reason."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _BFCLSourceError(ValueError):
    """Private BFCL source parsing failure that becomes a safe preflight reason."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _TauBenchSourceError(ValueError):
    """Private tau-bench source parsing failure with a safe reason code."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _MTBenchSourceError(ValueError):
    """Private MT-Bench source parsing failure with a safe reason code."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _load_mt_bench_source_cases(
    path: Path,
    *,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int, int]:
    if not path.is_file():
        raise _MTBenchSourceError("official_harness_mt_bench_question_file_required")
    if limit is not None and int(limit) <= 0:
        return [], 0, 0
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_row_count = 0
    invalid_rows = 0
    try:
        rows = _iter_private_jsonl(path)
        for row in rows:
            source_row_count += 1
            identifier = str(row.get("question_id") or "").strip()
            category = str(row.get("category") or "").strip().lower()
            turns = row.get("turns")
            valid_turns = (
                isinstance(turns, list)
                and len(turns) == 2
                and all(isinstance(turn, str) and turn.strip() for turn in turns)
            )
            case_id = _official_case_id("mt_bench_work", identifier)
            if not identifier or not category or not valid_turns or case_id in seen:
                invalid_rows += 1
                continue
            seen.add(case_id)
            cases.append(
                {
                    "case_id": case_id,
                    "source_identifier": identifier,
                    "category": category,
                    "turns": [str(turn) for turn in turns],
                }
            )
            if limit is not None and len(cases) >= int(limit):
                break
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _MTBenchSourceError("official_harness_mt_bench_question_file_unreadable") from exc
    if invalid_rows and not cases:
        raise _MTBenchSourceError("official_harness_mt_bench_source_rows_invalid")
    return cases, source_row_count, invalid_rows


def _load_tau_bench_source_cases(
    path: Path,
    *,
    limit: int | None,
    environments: Sequence[str],
) -> tuple[list[dict[str, Any]], int, int]:
    if not path.is_dir():
        raise _TauBenchSourceError("official_harness_tau_bench_dataset_directory_required")
    requested = _normalize_tau_environments(environments)
    source_by_environment = {
        environment: (relative_path, target_name)
        for environment, relative_path, target_name in _TAU_BENCH_TASK_SOURCES
    }
    cases: list[dict[str, Any]] = []
    source_row_count = 0
    invalid_rows = 0
    if limit is not None and int(limit) <= 0:
        return cases, source_row_count, invalid_rows
    for environment in requested:
        relative_path, target_name = source_by_environment[environment]
        source = path / relative_path
        if not source.is_file():
            raise _TauBenchSourceError("official_harness_tau_bench_task_files_missing")
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=source.name)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise _TauBenchSourceError("official_harness_tau_bench_task_ast_unreadable") from exc
        task_list = _tau_bench_static_task_list(tree, target_name=target_name)
        if task_list is None:
            raise _TauBenchSourceError("official_harness_tau_bench_static_task_list_missing")
        for task_index, node in enumerate(task_list.elts):
            source_row_count += 1
            if not isinstance(node, ast.Call):
                invalid_rows += 1
                continue
            source_identifier = f"{environment}:{task_index}"
            cases.append(
                {
                    "case_id": _official_case_id("tau_bench", source_identifier),
                    "source_identifier": source_identifier,
                    "environment": environment,
                    "task_index": task_index,
                }
            )
            if limit is not None and len(cases) >= max(0, int(limit)):
                return cases, source_row_count, invalid_rows
    return cases, source_row_count, invalid_rows


def _tau_bench_static_task_list(tree: ast.Module, *, target_name: str) -> ast.List | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == target_name for target in targets):
            return value if isinstance(value, ast.List) else None
    return None


def _load_bfcl_source_cases(
    path: Path,
    *,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int, int]:
    if not path.is_dir():
        raise _BFCLSourceError("official_harness_bfcl_dataset_directory_required")
    if limit is not None and int(limit) <= 0:
        return [], 0, 0
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_row_count = 0
    invalid_rows = 0
    for category, filename in _BFCL_V3_AST_CATEGORY_FILENAMES:
        source = path / filename
        if not source.is_file():
            raise _BFCLSourceError("official_harness_bfcl_category_files_missing")
        try:
            rows = _iter_private_jsonl(source)
            for row in rows:
                source_row_count += 1
                identifier = str(row.get("id") or "").strip()
                question_turns = row.get("question")
                functions = row.get("function")
                messages = question_turns[0] if isinstance(question_turns, list) and len(question_turns) == 1 else None
                valid_messages = (
                    isinstance(messages, list)
                    and bool(messages)
                    and all(
                        isinstance(message, Mapping)
                        and str(message.get("role") or "").strip().lower() in {"system", "user", "assistant"}
                        and bool(str(message.get("content") or ""))
                        for message in messages
                    )
                )
                valid_functions = (
                    isinstance(functions, list)
                    and bool(functions)
                    and all(
                        isinstance(function, Mapping)
                        and bool(str(function.get("name") or "").strip())
                        and isinstance(function.get("parameters"), Mapping)
                        for function in functions
                    )
                )
                source_identifier = {"category": source.stem, "id": identifier}
                case_id = _official_case_id("bfcl", source_identifier)
                if not identifier or not valid_messages or not valid_functions:
                    invalid_rows += 1
                    continue
                if case_id in seen:
                    raise _BFCLSourceError("official_harness_bfcl_case_identifier_duplicate")
                seen.add(case_id)
                current_prompt = next(
                    (
                        str(message.get("content") or "")
                        for message in reversed(messages)
                        if str(message.get("role") or "").strip().lower() == "user"
                    ),
                    "",
                )
                if not current_prompt:
                    invalid_rows += 1
                    continue
                cases.append(
                    {
                        "case_id": case_id,
                        "source_identifier": identifier,
                        "source_file_stem": source.stem,
                        "category": category,
                        "prompt": current_prompt,
                        "messages": [dict(message) for message in messages],
                        "tools": [
                            {"type": "function", "function": dict(function)}
                            for function in functions
                        ],
                    }
                )
                if limit is not None and len(cases) >= int(limit):
                    return cases, source_row_count, invalid_rows
        except _BFCLSourceError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise _BFCLSourceError("official_harness_bfcl_dataset_unreadable") from exc
    if invalid_rows and not cases:
        raise _BFCLSourceError("official_harness_bfcl_source_rows_invalid")
    return cases, source_row_count, invalid_rows


def _bfcl_v3_harness_reasons(harness_root: Path) -> list[str]:
    marker = (
        harness_root
        / "berkeley-function-call-leaderboard"
        / "bfcl_eval"
        / "constants"
        / "category_mapping.py"
    )
    try:
        return [] if _BFCL_V3_MARKER in marker.read_text(encoding="utf-8") else ["official_harness_bfcl_v3_harness_required"]
    except (OSError, UnicodeDecodeError):
        return ["official_harness_bfcl_v3_harness_required"]


def _load_livecodebench_source_cases(
    path: Path,
    *,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int, int]:
    source = path / "test_generation.parquet" if path.is_dir() else path
    if source.name != "test_generation.parquet" or not source.is_file():
        raise _LiveCodeBenchSourceError("official_harness_livecodebench_generation_parquet_missing")
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise _LiveCodeBenchSourceError("official_harness_livecodebench_parquet_dependency_missing") from exc
    required_columns = ("question_id", "question_content", "starter_code", "function_name", "test")
    try:
        parquet_file = parquet.ParquetFile(source)
        missing_columns = [column for column in required_columns if column not in parquet_file.schema.names]
        if missing_columns:
            raise _LiveCodeBenchSourceError("official_harness_livecodebench_required_columns_missing")
        rows = parquet_file.read(columns=list(required_columns)).to_pylist()
    except _LiveCodeBenchSourceError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise _LiveCodeBenchSourceError("official_harness_livecodebench_parquet_unreadable") from exc

    grouped: dict[str, dict[str, Any]] = {}
    invalid_rows = 0
    for row in rows:
        identifier = str(row.get("question_id") or "").strip()
        question = str(row.get("question_content") or "")
        starter_code = str(row.get("starter_code") or "")
        function_name = str(row.get("function_name") or "")
        raw_test = row.get("test")
        try:
            test_rows = json.loads(raw_test) if isinstance(raw_test, str) else raw_test
        except (TypeError, ValueError, json.JSONDecodeError):
            test_rows = None
        valid_tests = (
            isinstance(test_rows, list)
            and bool(test_rows)
            and all(
                isinstance(test, Mapping)
                and "input" in test
                and "output" in test
                for test in test_rows
            )
        )
        if not identifier or not question or not function_name or not valid_tests:
            invalid_rows += 1
            continue
        existing = grouped.get(identifier)
        if existing is None:
            grouped[identifier] = {
                "source_identifier": identifier,
                "case_id": _official_case_id("livecodebench", identifier),
                "prompt": _livecodebench_prompt(question, starter_code),
                "question_content": question,
                "starter_code": starter_code,
                "function_name": function_name,
                "test_count": len(test_rows),
            }
            continue
        if (
            existing["question_content"] != question
            or existing["starter_code"] != starter_code
            or existing["function_name"] != function_name
        ):
            raise _LiveCodeBenchSourceError("official_harness_livecodebench_question_metadata_mismatch")
        existing["test_count"] += len(test_rows)

    if invalid_rows and not grouped:
        raise _LiveCodeBenchSourceError("official_harness_livecodebench_source_rows_invalid")
    ordered = [grouped[key] for key in sorted(grouped)]
    if limit is not None:
        ordered = ordered[: max(0, int(limit))]
    return ordered, len(rows), invalid_rows


def _livecodebench_prompt(question_content: str, starter_code: str) -> str:
    prompt = f"### Question:\n{question_content}\n\n"
    if starter_code:
        prompt += "### Format: You will use the following starter code to write the solution to the problem and enclose your code within delimiters.\n"
        prompt += f"```python\n{starter_code}\n```\n\n"
    else:
        prompt += "### Format: Read the inputs from stdin solve the problem and write the answer to stdout (do not directly test on the sample inputs). Enclose your code within delimiters as follows. Ensure that when the python program runs, it reads the inputs, runs the algorithm and writes output to STDOUT.\n"
        prompt += "```python\n# YOUR CODE HERE\n```\n\n"
    return prompt + "### Answer: (use the provided format with backticks)\n\n"


def _official_case_id(suite_id: str, identifier: Any) -> str:
    return sha256_text(
        json.dumps(
            {"suite_id": suite_id, "id": str(identifier)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _case_set_digest(suite_id: str, case_ids: Sequence[str]) -> str:
    return sha256_text(stable_json({"suite_id": suite_id, "case_hashes": sorted(set(case_ids))})) if case_ids else ""


def _harness_pin_binding(path: str | Path | None, *, suite_id: str) -> dict[str, Any]:
    if not path:
        return {
            "provided": False,
            "ready": False,
            "manifest_path_sha256": "",
            "reason_codes": ["official_harness_pin_manifest_required"],
            "raw_manifest_path_persisted": False,
        }
    selected = Path(path)
    if not selected.is_file():
        return {
            "provided": True,
            "ready": False,
            "manifest_path_sha256": sha256_text(str(selected)),
            "reason_codes": ["official_harness_pin_manifest_not_found"],
            "raw_manifest_path_persisted": False,
        }
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "provided": True,
            "ready": False,
            "manifest_path_sha256": sha256_text(str(selected)),
            "reason_codes": ["official_harness_pin_manifest_unreadable"],
            "raw_manifest_path_persisted": False,
        }
    rows = payload.get("suites") if isinstance(payload, Mapping) and isinstance(payload.get("suites"), list) else []
    row = next((item for item in rows if isinstance(item, Mapping) and str(item.get("suite_id") or "") == suite_id), {})
    reasons: list[str] = []
    if not row:
        reasons.append("official_harness_pin_suite_missing")
    elif row.get("ready") is not True:
        reasons.append("official_harness_pin_suite_not_ready")
    for field in _PIN_REQUIRED_FIELDS:
        value = str(row.get(field) or "") if isinstance(row, Mapping) else ""
        if not _looks_like_sha256(value):
            reasons.append(f"official_harness_pin_missing_{field}")
    return {
        "provided": True,
        "ready": not reasons,
        "manifest_path_sha256": sha256_text(str(selected)),
        "suite_pin_digest_sha256": sha256_text(
            stable_json({field: str(row.get(field) or "") for field in _PIN_REQUIRED_FIELDS})
        )
        if row
        else "",
        **({field: str(row.get(field) or "") for field in _PIN_REQUIRED_FIELDS} if row else {}),
        "reason_codes": sorted(set(reasons)),
        "raw_manifest_path_persisted": False,
        "raw_harness_identifiers_persisted": False,
    }


def _bridge_candidate_binding(
    *,
    candidate_id: str,
    api_format: str,
    registry_path: str | Path | None,
    provider_baseline_freeze_manifest_path: str | Path | None,
) -> dict[str, Any]:
    requested = str(candidate_id or "").strip()
    if requested in PUBLIC_MODELS:
        return {
            "candidate_id": requested,
            "candidate_kind": "public_axio",
            "api_format": normalize_api_format(api_format),
            "profile": None,
            "profile_id_sha256": "",
            "provider_candidate_id_sha256": "",
            "registry_binding": _not_required_registry_binding(),
            "provider_baseline_freeze_binding": _not_required_provider_baseline_freeze_binding(),
            "reason_codes": [],
        }

    if not requested.startswith(_PROVIDER_CANDIDATE_PREFIX):
        return _unsupported_bridge_candidate(reason="official_harness_bridge_candidate_not_supported")

    suffix = requested[len(_PROVIDER_CANDIDATE_PREFIX) :].strip().lower()
    if not _looks_like_sha256(suffix):
        return _unsupported_bridge_candidate(reason="official_harness_bridge_provider_candidate_hash_required")
    registry = _private_registry_candidate_binding(registry_path, candidate_suffix=suffix)
    freeze = _provider_baseline_freeze_candidate_binding(
        provider_baseline_freeze_manifest_path,
        candidate_id=f"{_PROVIDER_CANDIDATE_PREFIX}{suffix}",
        registry_file_sha256=str(registry.get("registry_file_sha256") or ""),
    )
    reasons = [*registry["reason_codes"], *freeze["reason_codes"]]
    registry_file_sha256 = str(registry.get("registry_file_sha256") or "")
    frozen_registry_file_sha256 = str(freeze.get("registry_file_sha256") or "")
    if not frozen_registry_file_sha256:
        reasons.append("official_harness_bridge_provider_baseline_freeze_registry_missing")
    elif registry_file_sha256 != frozen_registry_file_sha256:
        reasons.append("official_harness_bridge_provider_registry_freeze_mismatch")
    profile = registry.get("profile")
    return {
        "candidate_id": f"{_PROVIDER_CANDIDATE_PREFIX}{suffix}",
        "candidate_kind": "provider_native",
        "api_format": normalize_api_format(str(getattr(profile, "api_format", "") or "")),
        "profile": profile,
        "profile_id_sha256": str(registry.get("profile_id_sha256") or ""),
        "provider_candidate_id_sha256": sha256_text(f"{_PROVIDER_CANDIDATE_PREFIX}{suffix}"),
        "registry_binding": registry,
        "provider_baseline_freeze_binding": freeze,
        "reason_codes": sorted(set(str(reason) for reason in reasons if reason)),
    }


def _unsupported_bridge_candidate(*, reason: str) -> dict[str, Any]:
    return {
        "candidate_id": "",
        "candidate_kind": "unsupported",
        "api_format": "",
        "profile": None,
        "profile_id_sha256": "",
        "provider_candidate_id_sha256": "",
        "registry_binding": _not_required_registry_binding(),
        "provider_baseline_freeze_binding": _not_required_provider_baseline_freeze_binding(),
        "reason_codes": [reason],
    }


def _private_registry_candidate_binding(
    registry_path: str | Path | None,
    *,
    candidate_suffix: str,
) -> dict[str, Any]:
    if not registry_path:
        return {
            "required": True,
            "provided": False,
            "ready": False,
            "registry_path_sha256": "",
            "registry_file_sha256": "",
            "profile_id_sha256": "",
            "reason_codes": ["official_harness_bridge_provider_registry_required"],
            "raw_registry_path_persisted": False,
            "raw_provider_identifiers_persisted": False,
        }
    selected = Path(registry_path)
    if not selected.is_file():
        return {
            "required": True,
            "provided": True,
            "ready": False,
            "registry_path_sha256": sha256_text(str(selected)),
            "registry_file_sha256": "",
            "profile_id_sha256": "",
            "reason_codes": ["official_harness_bridge_provider_registry_not_found"],
            "raw_registry_path_persisted": False,
            "raw_provider_identifiers_persisted": False,
        }
    try:
        profiles = load_registry(selected)
        registry_file_sha256 = sha256_text(selected.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "required": True,
            "provided": True,
            "ready": False,
            "registry_path_sha256": sha256_text(str(selected)),
            "registry_file_sha256": "",
            "profile_id_sha256": "",
            "reason_codes": ["official_harness_bridge_provider_registry_unreadable"],
            "raw_registry_path_persisted": False,
            "raw_provider_identifiers_persisted": False,
        }
    matches = [profile for profile in profiles if sha256_text(profile.profile_id) == candidate_suffix]
    reasons: list[str] = []
    if not matches:
        reasons.append("official_harness_bridge_provider_candidate_not_in_registry")
    elif len(matches) > 1:
        reasons.append("official_harness_bridge_provider_candidate_ambiguous")
    profile = matches[0] if len(matches) == 1 else None
    return {
        "required": True,
        "provided": True,
        "ready": not reasons,
        "registry_path_sha256": sha256_text(str(selected)),
        "registry_file_sha256": registry_file_sha256,
        "profile": profile,
        "profile_id_sha256": sha256_text(profile.profile_id) if profile is not None else "",
        "api_format": normalize_api_format(str(profile.api_format)) if profile is not None else "",
        "reason_codes": reasons,
        "raw_registry_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
    }


def _provider_baseline_freeze_candidate_binding(
    path: str | Path | None,
    *,
    candidate_id: str,
    registry_file_sha256: str = "",
) -> dict[str, Any]:
    if not path:
        return {
            "required": True,
            "provided": False,
            "ready": False,
            "manifest_path_sha256": "",
            "manifest_digest_sha256": "",
            "candidate_id_sha256": sha256_text(candidate_id),
            "reason_codes": ["official_harness_bridge_provider_baseline_freeze_required"],
            "raw_manifest_path_persisted": False,
        }
    selected = Path(path)
    if not selected.is_file():
        return {
            "required": True,
            "provided": True,
            "ready": False,
            "manifest_path_sha256": sha256_text(str(selected)),
            "manifest_digest_sha256": "",
            "candidate_id_sha256": sha256_text(candidate_id),
            "reason_codes": ["official_harness_bridge_provider_baseline_freeze_not_found"],
            "raw_manifest_path_persisted": False,
        }
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "required": True,
            "provided": True,
            "ready": False,
            "manifest_path_sha256": sha256_text(str(selected)),
            "manifest_digest_sha256": "",
            "candidate_id_sha256": sha256_text(candidate_id),
            "reason_codes": ["official_harness_bridge_provider_baseline_freeze_unreadable"],
            "raw_manifest_path_persisted": False,
        }
    if not isinstance(payload, Mapping):
        return {
            "required": True,
            "provided": True,
            "ready": False,
            "manifest_path_sha256": sha256_text(str(selected)),
            "manifest_digest_sha256": "",
            "candidate_id_sha256": sha256_text(candidate_id),
            "reason_codes": ["official_harness_bridge_provider_baseline_freeze_invalid"],
            "raw_manifest_path_persisted": False,
        }
    declared_digest = str(payload.get("freeze_digest_sha256") or "")
    computed_digest = sha256_text(stable_json(_provider_baseline_freeze_digest_input(payload)))
    candidate_hash = sha256_text(candidate_id)
    selected_hashes = [
        str(value)
        for value in payload.get("selected_provider_candidate_id_hashes", [])
        if _looks_like_sha256(value)
    ] if isinstance(payload.get("selected_provider_candidate_id_hashes"), list) else []
    reasons: list[str] = []
    claim_validation = validate_provider_baseline_freeze_for_official_campaign(
        payload,
        registry_file_sha256=registry_file_sha256,
    )
    reasons.extend(
        f"official_harness_bridge_{reason}"
        for reason in claim_validation.get("reason_codes", [])
        if str(reason)
    )
    if candidate_hash not in selected_hashes:
        reasons.append("official_harness_bridge_provider_candidate_not_frozen")
    return {
        "required": True,
        "provided": True,
        "ready": not reasons,
        "manifest_path_sha256": sha256_text(str(selected)),
        "manifest_digest_sha256": declared_digest if _looks_like_sha256(declared_digest) else "",
        "candidate_id_sha256": candidate_hash,
        "selected_candidate_hash_count": len(selected_hashes),
        "candidate_frozen": candidate_hash in selected_hashes,
        "claim_contract_ready": claim_validation.get("ready") is True,
        "registry_file_sha256": str(
            (payload.get("provider_registry_receipt") or {}).get("registry_file_sha256")
            if isinstance(payload.get("provider_registry_receipt"), Mapping)
            else ""
        ),
        "reason_codes": sorted(set(reasons)),
        "raw_manifest_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
    }


def validate_provider_baseline_freeze_for_official_campaign(
    payload: Mapping[str, Any] | None,
    *,
    registry_file_sha256: str = "",
) -> dict[str, Any]:
    """Validate the final-claim semantics needed before target-suite work.

    A historical exhaustive provider freeze may have a valid digest and a
    legacy ``final_claim_freeze_ready`` flag.  It is not the pre-registered
    canonical rank-1/2/3 contract required by the current campaign.  This
    validator is intentionally independent of target-suite data and is safe to
    run for both offline preflight and live admission.
    """

    manifest = payload if isinstance(payload, Mapping) else {}
    declared_digest = str(manifest.get("freeze_digest_sha256") or "")
    computed_digest = sha256_text(
        stable_json(_provider_baseline_freeze_digest_input(manifest))
    )
    required_count = len(EXTERNAL_PROVIDER_RANKING_REQUIRED_RANKS)
    selected_candidate_hashes = [
        str(value).strip().lower()
        for value in manifest.get("selected_provider_candidate_id_hashes", [])
        if _looks_like_sha256(value)
    ] if isinstance(manifest.get("selected_provider_candidate_id_hashes"), list) else []
    frozen_rows = (
        manifest.get("frozen_candidate_rows")
        if isinstance(manifest.get("frozen_candidate_rows"), list)
        else []
    )
    observed_ranks = sorted(
        rank
        for rank in (
            _optional_positive_int(row.get("pre_campaign_external_rank"))
            for row in frozen_rows
            if isinstance(row, Mapping)
        )
        if rank is not None
    )
    tier_rows = (
        manifest.get("tier_target_policy")
        if isinstance(manifest.get("tier_target_policy"), list)
        else []
    )
    observed_tiers = {
        str(row.get("axio_model") or ""): _optional_positive_int(
            row.get("target_provider_rank")
        )
        for row in tier_rows
        if isinstance(row, Mapping)
    }
    expected_tiers = {
        "axio-pro": 1,
        "axio-terra": 2,
        "axio-fast": 3,
    }
    external = (
        manifest.get("external_ranking_receipt")
        if isinstance(manifest.get("external_ranking_receipt"), Mapping)
        else {}
    )
    registry_receipt = (
        manifest.get("provider_registry_receipt")
        if isinstance(manifest.get("provider_registry_receipt"), Mapping)
        else {}
    )
    expected_registry_sha = str(registry_file_sha256 or "")
    mapping_validation_errors = _external_provider_rank_mapping_validation_errors(
        manifest,
        expected_registry_file_sha256=expected_registry_sha,
    )
    declared_candidate_set_digest = str(
        manifest.get("selected_provider_candidate_id_set_sha256") or ""
    )
    computed_candidate_set_digest = sha256_text(
        stable_json(sorted(set(selected_candidate_hashes)))
    )
    reasons: list[str] = []
    if str(manifest.get("schema") or "") != "axio_fusion_api.provider_baseline_freeze_manifest.v1":
        reasons.append("provider_baseline_freeze_schema_invalid")
    if not _looks_like_sha256(declared_digest) or declared_digest != computed_digest:
        reasons.append("provider_baseline_freeze_digest_invalid")
    if manifest.get("final_claim_freeze_ready") is not True:
        reasons.append("provider_baseline_freeze_not_ready")
    if str(manifest.get("provider_baseline_selection") or "") != EXTERNAL_PROVIDER_RANKING_SELECTION_MODE:
        reasons.append("provider_baseline_freeze_not_externally_ranked_top_three")
    if manifest.get("selected_all_available_provider_baselines") is not False:
        reasons.append("provider_baseline_freeze_exhaustive_diagnostic_not_allowed")
    if _optional_positive_int(manifest.get("selected_provider_baseline_count")) != required_count:
        reasons.append("provider_baseline_freeze_selected_count_mismatch")
    if _optional_positive_int(manifest.get("required_provider_baseline_count")) != required_count:
        reasons.append("provider_baseline_freeze_required_count_mismatch")
    if len(selected_candidate_hashes) != required_count or len(set(selected_candidate_hashes)) != required_count:
        reasons.append("provider_baseline_freeze_candidate_set_mismatch")
    if (
        not _looks_like_sha256(declared_candidate_set_digest)
        or declared_candidate_set_digest != computed_candidate_set_digest
    ):
        reasons.append("provider_baseline_freeze_candidate_set_digest_invalid")
    if observed_ranks != list(EXTERNAL_PROVIDER_RANKING_REQUIRED_RANKS):
        reasons.append("provider_baseline_freeze_rank_rows_incomplete")
    if observed_tiers != expected_tiers:
        reasons.append("provider_baseline_freeze_tier_mapping_invalid")
    if str(external.get("schema") or "") != EXTERNAL_PROVIDER_RANKING_RECEIPT_SCHEMA:
        reasons.append("provider_baseline_freeze_external_ranking_receipt_missing")
    if external.get("ready") is not True:
        reasons.append("provider_baseline_freeze_external_ranking_not_ready")
    if external.get("pre_registered_before_campaign") is not True:
        reasons.append("provider_baseline_freeze_external_ranking_not_pre_registered")
    if external.get("identity_binding_ready") is not True:
        reasons.append("provider_baseline_freeze_external_ranking_identity_not_ready")
    if external.get("target_benchmark_material_detected") is True:
        reasons.append("provider_baseline_freeze_target_material_detected")
    if mapping_validation_errors:
        reasons.append("provider_baseline_freeze_external_ranking_mapping_invalid")
    frozen_registry_sha = str(registry_receipt.get("registry_file_sha256") or "")
    if expected_registry_sha and frozen_registry_sha != expected_registry_sha:
        reasons.append("provider_baseline_freeze_registry_mismatch")
    return {
        "schema": "axio_fusion_api.official_campaign_provider_freeze_validation.v1",
        "ready": not reasons,
        "selection_mode": str(manifest.get("provider_baseline_selection") or ""),
        "selected_provider_baseline_count": _optional_positive_int(
            manifest.get("selected_provider_baseline_count")
        ) or 0,
        "required_provider_baseline_count": required_count,
        "selected_candidate_hash_count": len(selected_candidate_hashes),
        "candidate_set_digest_valid": bool(
            _looks_like_sha256(declared_candidate_set_digest)
            and declared_candidate_set_digest == computed_candidate_set_digest
        ),
        "rank_row_count": len(observed_ranks),
        "tier_mapping_valid": observed_tiers == expected_tiers,
        "external_ranking_mapping_valid": not mapping_validation_errors,
        "external_ranking_validation_error_count": len(mapping_validation_errors),
        "external_ranking_validation_error_set_sha256": sha256_text(
            stable_json(mapping_validation_errors)
        ),
        "registry_binding_checked": bool(expected_registry_sha),
        "registry_binding_matches": bool(expected_registry_sha)
        and frozen_registry_sha == expected_registry_sha,
        "reason_codes": sorted(set(reasons)),
        "raw_provider_identifiers_persisted": False,
        "raw_local_paths_persisted": False,
        "secrets_persisted": False,
    }


def _not_required_registry_binding() -> dict[str, Any]:
    return {
        "required": False,
        "provided": False,
        "ready": True,
        "registry_path_sha256": "",
        "registry_file_sha256": "",
        "profile_id_sha256": "",
        "reason_codes": [],
        "raw_registry_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
    }


def _not_required_provider_baseline_freeze_binding() -> dict[str, Any]:
    return {
        "required": False,
        "provided": False,
        "ready": True,
        "manifest_path_sha256": "",
        "manifest_digest_sha256": "",
        "candidate_id_sha256": "",
        "reason_codes": [],
        "raw_manifest_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
    }


def _safe_candidate_binding(candidate: Mapping[str, Any]) -> dict[str, Any]:
    registry = candidate.get("registry_binding") if isinstance(candidate.get("registry_binding"), Mapping) else {}
    return {
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")) if candidate.get("candidate_id") else "",
        "profile_id_sha256": str(candidate.get("profile_id_sha256") or ""),
        "api_format": str(candidate.get("api_format") or ""),
        "registry_required": registry.get("required") is True,
        "registry_ready": registry.get("ready") is True,
        "registry_file_sha256": str(registry.get("registry_file_sha256") or ""),
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _safe_provider_baseline_freeze_binding(candidate: Mapping[str, Any]) -> dict[str, Any]:
    binding = (
        candidate.get("provider_baseline_freeze_binding")
        if isinstance(candidate.get("provider_baseline_freeze_binding"), Mapping)
        else {}
    )
    return {
        "required": binding.get("required") is True,
        "ready": binding.get("ready") is True,
        "manifest_digest_sha256": str(binding.get("manifest_digest_sha256") or ""),
        "candidate_id_sha256": str(binding.get("candidate_id_sha256") or ""),
        "candidate_frozen": binding.get("candidate_frozen") is True if binding.get("required") is True else None,
        "registry_file_sha256": str(binding.get("registry_file_sha256") or ""),
        "reason_codes": sorted(str(reason) for reason in binding.get("reason_codes", []) if reason),
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _candidate_from_preflight(
    preflight: Mapping[str, Any],
    *,
    registry_path: str | Path | None,
) -> dict[str, Any]:
    binding = preflight.get("candidate_binding") if isinstance(preflight.get("candidate_binding"), Mapping) else {}
    candidate_kind = str(preflight.get("candidate_kind") or "")
    candidate_id = str(preflight.get("candidate_id") or "")
    profile: ModelProfile | None = None
    reasons: list[str] = []
    if candidate_kind == "provider_native":
        suffix = candidate_id[len(_PROVIDER_CANDIDATE_PREFIX) :] if candidate_id.startswith(_PROVIDER_CANDIDATE_PREFIX) else ""
        registry = _private_registry_candidate_binding(registry_path, candidate_suffix=suffix)
        reasons.extend(str(reason) for reason in registry.get("reason_codes", []) if reason)
        profile = registry.get("profile") if isinstance(registry.get("profile"), ModelProfile) else None
        if str(registry.get("registry_file_sha256") or "") != str(binding.get("registry_file_sha256") or ""):
            reasons.append("official_harness_bridge_provider_registry_changed_after_preflight")
        if str(registry.get("profile_id_sha256") or "") != str(binding.get("profile_id_sha256") or ""):
            reasons.append("official_harness_bridge_provider_profile_changed_after_preflight")
    return {
        "candidate_id": candidate_id,
        "candidate_kind": candidate_kind,
        "api_format": str(preflight.get("api_format") or ""),
        "profile": profile,
        "profile_id_sha256": str(binding.get("profile_id_sha256") or ""),
        "registry_binding": (
            registry if candidate_kind == "provider_native" else _not_required_registry_binding()
        ),
        "provider_baseline_freeze_binding": dict(preflight.get("provider_baseline_freeze_binding") or {}),
        "reason_codes": sorted(set(reasons)),
    }


def _target_max_output_tokens(suite_id: str, value: int | None) -> int:
    if value is None:
        return _default_max_output_tokens(suite_id)
    return max(1, min(int(value), 16384))


def _not_applicable_mt_binding() -> dict[str, Any]:
    return {
        "applicable": False,
        "configured": False,
        "raw_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _mt_bench_comparison_binding(
    *,
    candidate_id: str | None,
    registry_path: str | Path | None,
    provider_baseline_freeze_manifest_path: str | Path | None,
) -> dict[str, Any]:
    binding = _bridge_candidate_binding(
        candidate_id=str(candidate_id or ""),
        api_format="chat/completions",
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
    )
    reasons = list(binding.get("reason_codes") or [])
    if binding.get("candidate_kind") != "provider_native":
        reasons.append("official_harness_mt_bench_comparison_provider_candidate_required")
    return {**binding, "reason_codes": sorted(set(str(reason) for reason in reasons if reason))}


def _mt_bench_judge_binding(
    *,
    candidate_id: str | None,
    registry_path: str | Path | None,
) -> dict[str, Any]:
    requested = str(candidate_id or "").strip()
    if not requested.startswith(_PROVIDER_CANDIDATE_PREFIX):
        return _unsupported_bridge_candidate(
            reason="official_harness_mt_bench_judge_provider_candidate_required"
        )
    suffix = requested[len(_PROVIDER_CANDIDATE_PREFIX) :].strip().lower()
    if not _looks_like_sha256(suffix):
        return _unsupported_bridge_candidate(
            reason="official_harness_mt_bench_judge_candidate_hash_required"
        )
    registry = _private_registry_candidate_binding(registry_path, candidate_suffix=suffix)
    profile = registry.get("profile") if isinstance(registry.get("profile"), ModelProfile) else None
    return {
        "candidate_id": f"{_PROVIDER_CANDIDATE_PREFIX}{suffix}",
        "candidate_kind": "provider_native",
        "api_format": normalize_api_format(str(getattr(profile, "api_format", "") or "")),
        "profile": profile,
        "profile_id_sha256": str(registry.get("profile_id_sha256") or ""),
        "provider_candidate_id_sha256": sha256_text(f"{_PROVIDER_CANDIDATE_PREFIX}{suffix}"),
        "registry_binding": registry,
        "provider_baseline_freeze_binding": _not_required_provider_baseline_freeze_binding(),
        "reason_codes": sorted(
            set(str(reason) for reason in registry.get("reason_codes", []) if reason)
        ),
    }


def _safe_mt_bench_candidate_binding(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("applicable") is False:
        return _not_applicable_mt_binding()
    registry = candidate.get("registry_binding") if isinstance(candidate.get("registry_binding"), Mapping) else {}
    freeze = (
        candidate.get("provider_baseline_freeze_binding")
        if isinstance(candidate.get("provider_baseline_freeze_binding"), Mapping)
        else {}
    )
    candidate_id = str(candidate.get("candidate_id") or "")
    return {
        "applicable": True,
        "configured": not bool(candidate.get("reason_codes")),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(candidate_id) if candidate_id else "",
        "profile_id_sha256": str(candidate.get("profile_id_sha256") or ""),
        "api_format": str(candidate.get("api_format") or ""),
        "registry_required": registry.get("required") is True,
        "registry_ready": registry.get("ready") is True,
        "registry_file_sha256": str(registry.get("registry_file_sha256") or ""),
        "provider_baseline_frozen": (
            freeze.get("candidate_frozen") is True if freeze.get("required") is True else None
        ),
        "provider_baseline_freeze_digest_sha256": str(freeze.get("manifest_digest_sha256") or ""),
        "reason_codes": sorted(str(reason) for reason in candidate.get("reason_codes", []) if reason),
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _mt_bench_execution_binding(
    *,
    candidate: Mapping[str, Any],
    comparison: Mapping[str, Any],
    judge: Mapping[str, Any],
    axio_gateway_url: str | None,
    judge_max_output_tokens: int,
) -> dict[str, Any]:
    try:
        judge_tokens = max(1, min(int(judge_max_output_tokens), 16384))
    except (TypeError, ValueError):
        judge_tokens = 0
    target_id = str(candidate.get("candidate_id") or "")
    comparison_id = str(comparison.get("candidate_id") or "")
    judge_id = str(judge.get("candidate_id") or "")
    target_profile = candidate.get("profile") if isinstance(candidate.get("profile"), ModelProfile) else None
    comparison_profile = comparison.get("profile") if isinstance(comparison.get("profile"), ModelProfile) else None
    judge_profile = judge.get("profile") if isinstance(judge.get("profile"), ModelProfile) else None
    target_comparison_distinct = bool(target_id and comparison_id and target_id != comparison_id)
    judge_distinct_from_candidate = bool(judge_id and judge_id != target_id)
    judge_distinct_from_comparison = bool(judge_id and judge_id != comparison_id)
    judge_cross_provider_from_target = (
        True
        if target_profile is None
        else bool(judge_profile is not None and judge_profile.provider != target_profile.provider)
    )
    judge_cross_provider_from_comparison = bool(
        judge_profile is not None
        and comparison_profile is not None
        and judge_profile.provider != comparison_profile.provider
    )
    payload = {
        "two_turn_dialogue": True,
        "position_balanced": True,
        "judge_calls_per_case": 2,
        "judge_max_output_tokens": judge_tokens,
        "target_candidate_id_sha256": sha256_text(target_id) if target_id else "",
        "comparison_candidate_id_sha256": sha256_text(comparison_id) if comparison_id else "",
        "judge_candidate_id_sha256": sha256_text(judge_id) if judge_id else "",
        "target_comparison_distinct": target_comparison_distinct,
        "judge_distinct_from_candidate": judge_distinct_from_candidate,
        "judge_distinct_from_comparison": judge_distinct_from_comparison,
        "judge_cross_provider_from_target": judge_cross_provider_from_target,
        "judge_cross_provider_from_comparison": judge_cross_provider_from_comparison,
        "public_axio_gateway_configured": bool(str(axio_gateway_url or "").strip()),
        "answer_system_prompt_sha256": sha256_text(_MT_BENCH_SYSTEM_PROMPT),
        "reference_category_set_sha256": sha256_text(stable_json(sorted(_MT_BENCH_REFERENCE_CATEGORIES))),
    }
    configured = bool(
        comparison.get("candidate_kind") == "provider_native"
        and judge.get("candidate_kind") == "provider_native"
        and comparison_profile is not None
        and judge_profile is not None
        and target_comparison_distinct
        and judge_distinct_from_candidate
        and judge_distinct_from_comparison
        and judge_cross_provider_from_target
        and judge_cross_provider_from_comparison
        and judge_tokens > 0
    )
    return {
        "schema": "axio_fusion_api.mt_bench_execution.v1",
        "applicable": True,
        "configured": configured,
        **payload,
        "configuration_sha256": sha256_text(stable_json(payload)),
        "raw_gateway_url_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "secrets_persisted": False,
    }


def _mt_bench_preflight_reasons(*, execution: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if execution.get("configured") is not True:
        reasons.append("official_harness_mt_bench_execution_not_configured")
    if execution.get("two_turn_dialogue") is not True:
        reasons.append("official_harness_mt_bench_two_turn_protocol_required")
    if execution.get("position_balanced") is not True or _safe_int(execution.get("judge_calls_per_case")) != 2:
        reasons.append("official_harness_mt_bench_position_balancing_required")
    if execution.get("target_comparison_distinct") is not True:
        reasons.append("official_harness_mt_bench_comparison_not_independent")
    if execution.get("judge_distinct_from_candidate") is not True:
        reasons.append("official_harness_mt_bench_judge_matches_target")
    if execution.get("judge_distinct_from_comparison") is not True:
        reasons.append("official_harness_mt_bench_judge_matches_comparison")
    if execution.get("judge_cross_provider_from_target") is not True:
        reasons.append("official_harness_mt_bench_judge_not_cross_provider_from_target")
    if execution.get("judge_cross_provider_from_comparison") is not True:
        reasons.append("official_harness_mt_bench_judge_not_cross_provider_from_comparison")
    if execution.get("public_axio_gateway_configured") is not True and execution.get("target_candidate_id_sha256"):
        # The public-Axio condition is checked in the caller's candidate binding
        # below. This placeholder keeps the persisted execution contract free of
        # a raw public model name.
        pass
    return reasons


def _mt_bench_runtime_bindings(
    *,
    preflight: Mapping[str, Any],
    candidate_id: str,
    api_format: str,
    registry_path: str | Path | None,
    provider_baseline_freeze_manifest_path: str | Path | None,
    mt_comparison_candidate_id: str | None,
    mt_judge_candidate_id: str | None,
    mt_judge_registry_path: str | Path | None,
    axio_gateway_url: str | None,
    mt_judge_max_output_tokens: int,
) -> dict[str, Any]:
    """Re-resolve all private identities before a paired MT-Bench action.

    Preflight returns only opaque bindings. Generation and judging must rebuild
    those bindings from the private registry/freeze inputs so a changed profile,
    frozen baseline, or judge cannot silently replace one side of the match.
    """

    target = _bridge_candidate_binding(
        candidate_id=candidate_id,
        api_format=api_format,
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
    )
    comparison = _mt_bench_comparison_binding(
        candidate_id=mt_comparison_candidate_id,
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
    )
    judge = _mt_bench_judge_binding(
        candidate_id=mt_judge_candidate_id,
        registry_path=mt_judge_registry_path or registry_path,
    )
    execution = _mt_bench_execution_binding(
        candidate=target,
        comparison=comparison,
        judge=judge,
        axio_gateway_url=axio_gateway_url,
        judge_max_output_tokens=mt_judge_max_output_tokens,
    )
    reasons = [
        *target.get("reason_codes", []),
        *comparison.get("reason_codes", []),
        *judge.get("reason_codes", []),
        *_mt_bench_preflight_reasons(execution=execution),
    ]
    expected_target = (
        preflight.get("candidate_binding")
        if isinstance(preflight.get("candidate_binding"), Mapping)
        else {}
    )
    expected_comparison = (
        preflight.get("mt_bench_comparison")
        if isinstance(preflight.get("mt_bench_comparison"), Mapping)
        else {}
    )
    expected_judge = (
        preflight.get("mt_bench_judge")
        if isinstance(preflight.get("mt_bench_judge"), Mapping)
        else {}
    )
    expected_execution = (
        preflight.get("mt_bench_execution")
        if isinstance(preflight.get("mt_bench_execution"), Mapping)
        else {}
    )
    if stable_json(_safe_candidate_binding(target)) != stable_json(dict(expected_target)):
        reasons.append("official_harness_mt_bench_target_binding_changed_after_preflight")
    if stable_json(_safe_mt_bench_candidate_binding(comparison)) != stable_json(dict(expected_comparison)):
        reasons.append("official_harness_mt_bench_comparison_binding_changed_after_preflight")
    if stable_json(_safe_mt_bench_candidate_binding(judge)) != stable_json(dict(expected_judge)):
        reasons.append("official_harness_mt_bench_judge_binding_changed_after_preflight")
    if str(execution.get("configuration_sha256") or "") != str(expected_execution.get("configuration_sha256") or ""):
        reasons.append("official_harness_mt_bench_execution_binding_changed_after_preflight")
    return {
        "ready": not reasons,
        "target": target,
        "comparison": comparison,
        "judge": judge,
        "execution": execution,
        "reason_codes": sorted(set(str(reason) for reason in reasons if reason)),
    }


def _mt_bench_generation_protocol_receipt(
    *,
    candidate: Mapping[str, Any],
    comparison: Mapping[str, Any],
    execution: Mapping[str, Any],
    pin: Mapping[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    payload = {
        "schema": "axio_fusion_api.mt_bench_generation_protocol.v1",
        "suite_id": "mt_bench_work",
        "task_type": "daily_work",
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")),
        "api_format": str(candidate.get("api_format") or ""),
        "comparison_candidate_id_sha256": sha256_text(str(comparison.get("candidate_id") or "")),
        "comparison_candidate_kind": str(comparison.get("candidate_kind") or ""),
        "comparison_profile_id_sha256": str(comparison.get("profile_id_sha256") or ""),
        "two_turn_dialogue": True,
        "turn_order_fixed": True,
        "answer_system_prompt_sha256": sha256_text(_MT_BENCH_SYSTEM_PROMPT),
        "execution_configuration_sha256": str(execution.get("configuration_sha256") or ""),
        "temperature": 0.0,
        "top_p": None,
        "stop_sequence_count": 0,
        "max_output_tokens": int(max_output_tokens),
        "prompt_protocol_sha256": str(pin.get("prompt_protocol_sha256") or ""),
        "decoding_config_sha256": str(pin.get("decoding_config_sha256") or ""),
        "harness_pin_digest_sha256": str(pin.get("suite_pin_digest_sha256") or ""),
        "raw_prompt_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    payload["generation_protocol_digest_sha256"] = sha256_text(stable_json(payload))
    return payload


def _mt_bench_comparison_generation_protocol_receipt(
    *,
    candidate: Mapping[str, Any],
    target: Mapping[str, Any],
    execution: Mapping[str, Any],
    pin: Mapping[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    """Build the frozen native-baseline protocol for the other MT-Bench side."""

    payload = {
        "schema": "axio_fusion_api.mt_bench_generation_protocol.v1",
        "suite_id": "mt_bench_work",
        "task_type": "daily_work",
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")),
        "api_format": str(candidate.get("api_format") or ""),
        "comparison_candidate_id_sha256": sha256_text(str(target.get("candidate_id") or "")),
        "comparison_candidate_kind": str(target.get("candidate_kind") or ""),
        "comparison_profile_id_sha256": str(target.get("profile_id_sha256") or ""),
        "two_turn_dialogue": True,
        "turn_order_fixed": True,
        "answer_system_prompt_sha256": sha256_text(_MT_BENCH_SYSTEM_PROMPT),
        "execution_configuration_sha256": str(execution.get("configuration_sha256") or ""),
        "temperature": 0.0,
        "top_p": None,
        "stop_sequence_count": 0,
        "max_output_tokens": int(max_output_tokens),
        "prompt_protocol_sha256": str(pin.get("prompt_protocol_sha256") or ""),
        "decoding_config_sha256": str(pin.get("decoding_config_sha256") or ""),
        "harness_pin_digest_sha256": str(pin.get("suite_pin_digest_sha256") or ""),
        "raw_prompt_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    payload["generation_protocol_digest_sha256"] = sha256_text(stable_json(payload))
    return payload


def _not_applicable_tau_binding() -> dict[str, Any]:
    return {
        "applicable": False,
        "configured": False,
        "raw_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _normalize_tau_environments(value: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(str(item).strip().lower() for item in value if str(item).strip())
    if not selected:
        return _TAU_BENCH_ENVIRONMENTS
    return tuple(environment for environment in _TAU_BENCH_ENVIRONMENTS if environment in selected)


def _tau_user_simulator_binding(
    *,
    model: str | None,
    provider: str | None,
    strategy: str,
) -> dict[str, Any]:
    model_text = str(model or "").strip()
    provider_text = str(provider or "").strip()
    strategy_text = str(strategy or "").strip().lower()
    configured = bool(model_text and provider_text and strategy_text in _TAU_BENCH_USER_STRATEGIES)
    payload = {
        "model_sha256": sha256_text(model_text) if model_text else "",
        "provider_sha256": sha256_text(provider_text) if provider_text else "",
        "strategy": strategy_text,
    }
    return {
        "schema": "axio_fusion_api.tau_bench_user_simulator.v1",
        "applicable": True,
        "configured": configured,
        "strategy": strategy_text,
        "model_sha256": payload["model_sha256"],
        "provider_sha256": payload["provider_sha256"],
        "configuration_sha256": sha256_text(stable_json(payload)) if configured else "",
        "raw_user_model_persisted": False,
        "raw_user_provider_persisted": False,
        "secrets_persisted": False,
    }


def _tau_execution_binding(
    *,
    environments: Sequence[str],
    max_steps: int,
    max_output_tokens: int | None,
    python_executable: str | None,
    gateway_configured: bool,
) -> dict[str, Any]:
    requested = tuple(str(item).strip().lower() for item in environments if str(item).strip())
    normalized = _normalize_tau_environments(environments)
    try:
        steps = int(max_steps)
    except (TypeError, ValueError):
        steps = 0
    executable = str(python_executable or sys.executable or "").strip()
    python_major, python_minor, python_ready = _tau_python_runtime_version(executable)
    payload = {
        "environments": list(normalized),
        "max_steps": steps,
        "requested_max_output_tokens": max_output_tokens,
        "python_executable_sha256": sha256_text(executable) if executable else "",
        "python_major": python_major,
        "python_minor": python_minor,
        "python_runtime_ready": python_ready,
        "gateway_configured": bool(gateway_configured),
    }
    return {
        "schema": "axio_fusion_api.tau_bench_execution.v1",
        "applicable": True,
        "configured": bool(normalized and steps > 0 and executable and python_ready),
        "environments": list(normalized),
        "environment_count": len(normalized),
        "requested_environment_count": len(requested),
        "requested_environments_valid": (
            not requested
            or (
                len(requested) == len(set(requested))
                and len(normalized) == len(requested)
            )
        ),
        "environment_selection_sha256": sha256_text(stable_json(list(normalized))),
        "max_steps": steps,
        "requested_max_output_tokens": max_output_tokens,
        "python_executable_sha256": payload["python_executable_sha256"],
        "python_major": python_major,
        "python_minor": python_minor,
        "python_runtime_ready": python_ready,
        "gateway_configured": bool(gateway_configured),
        "configuration_sha256": sha256_text(stable_json(payload)),
        "raw_python_executable_persisted": False,
        "raw_gateway_url_persisted": False,
        "secrets_persisted": False,
    }


def _tau_python_runtime_version(executable: str) -> tuple[int, int, bool]:
    if not executable:
        return 0, 0, False
    try:
        completed = subprocess.run(
            [executable, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if completed.returncode != 0:
            return 0, 0, False
        raw = str(completed.stdout or "").strip().split(".")
        major, minor = int(raw[0]), int(raw[1])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0, 0, False
    return major, minor, (major, minor) >= (3, 9)


def _tau_bench_preflight_reasons(
    *,
    candidate: Mapping[str, Any],
    user_simulator: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if user_simulator.get("configured") is not True:
        reasons.append("official_harness_tau_bench_user_simulator_not_configured")
    if str(user_simulator.get("strategy") or "") not in _TAU_BENCH_USER_STRATEGIES:
        reasons.append("official_harness_tau_bench_user_strategy_invalid")
    if execution.get("configured") is not True:
        reasons.append("official_harness_tau_bench_execution_not_configured")
    if execution.get("python_runtime_ready") is not True:
        reasons.append("official_harness_tau_bench_python_3_9_required")
    if execution.get("requested_environments_valid") is not True:
        reasons.append("official_harness_tau_bench_environment_selection_invalid")
    if candidate.get("candidate_kind") == "public_axio" and execution.get("gateway_configured") is not True:
        reasons.append("official_harness_tau_bench_public_gateway_required")
    profile = candidate.get("profile")
    if isinstance(profile, ModelProfile):
        same_model = sha256_text(str(profile.model)) == str(user_simulator.get("model_sha256") or "")
        same_provider = sha256_text(str(profile.provider)) == str(user_simulator.get("provider_sha256") or "")
        if same_model and same_provider:
            reasons.append("official_harness_tau_bench_user_simulator_not_independent")
    return reasons


def _tau_generation_protocol_receipt(
    *,
    candidate: Mapping[str, Any],
    pin: Mapping[str, Any],
    user_simulator: Mapping[str, Any],
    execution: Mapping[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    payload = {
        "schema": "axio_fusion_api.tau_bench_generation_protocol.v1",
        "suite_id": "tau_bench",
        "task_type": "agentic_tool_calling",
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")),
        "api_format": str(candidate.get("api_format") or ""),
        "user_simulator_configuration_sha256": str(user_simulator.get("configuration_sha256") or ""),
        "user_simulator_strategy": str(user_simulator.get("strategy") or ""),
        "environment_selection_sha256": str(execution.get("environment_selection_sha256") or ""),
        "max_steps": _safe_int(execution.get("max_steps")),
        "temperature": 0.0,
        "top_p": None,
        "stop_sequence_count": 0,
        "max_output_tokens": int(max_output_tokens),
        "prompt_protocol_sha256": str(pin.get("prompt_protocol_sha256") or ""),
        "decoding_config_sha256": str(pin.get("decoding_config_sha256") or ""),
        "harness_pin_digest_sha256": str(pin.get("suite_pin_digest_sha256") or ""),
        "raw_prompt_persisted": False,
        "raw_user_simulator_content_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    payload["generation_protocol_digest_sha256"] = sha256_text(stable_json(payload))
    return payload


def _generate_tau_bench_samples(
    *,
    preflight: Mapping[str, Any],
    dataset_path: Path,
    harness_root: Path,
    private_run_dir: Path,
    candidate: Mapping[str, Any],
    registry_path: str | Path | None,
    axio_gateway_url: str | None,
    limit: int | None,
    max_output_tokens: int | None,
    tau_user_model: str | None,
    tau_user_provider: str | None,
    tau_user_strategy: str,
    tau_environments: Sequence[str],
    tau_max_steps: int,
    tau_python_executable: str | None,
) -> dict[str, Any]:
    """Execute tau-bench's official environment in a private worker process."""

    del max_output_tokens, tau_environments
    private_root = _ensure_private_run_dir(private_run_dir)
    private_root_reasons = _private_generation_root_reasons(private_root)
    if private_root_reasons:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=private_root_reasons,
        )
    execution = preflight.get("tau_execution") if isinstance(preflight.get("tau_execution"), Mapping) else {}
    environments = tuple(str(item) for item in execution.get("environments", []) if str(item))
    try:
        cases, _, invalid_rows = _load_tau_bench_source_cases(
            dataset_path,
            limit=limit,
            environments=environments,
        )
    except _TauBenchSourceError as exc:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=[exc.reason_code],
        )
    if invalid_rows or not cases:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=["official_harness_tau_bench_source_rows_invalid" if invalid_rows else "official_harness_case_set_empty"],
        )

    samples_path = private_root / "samples.private.jsonl"
    metadata_path = private_root / "generation.safe.jsonl"
    receipt_path = private_root / "generation_receipt.safe.json"
    binding_path = private_root / _GENERATION_BINDING_FILENAME
    results_path = private_root / _TAU_BENCH_RESULT_FILENAME
    interactions_path = private_root / _TAU_BENCH_INTERACTIONS_FILENAME
    executable = str(tau_python_executable or sys.executable)
    command = _tau_bench_runner_command(
        python_executable=executable,
        harness_root=harness_root,
        results_path=results_path,
        interactions_path=interactions_path,
        candidate=candidate,
        registry_path=registry_path,
        api_format=str(preflight.get("api_format") or ""),
        axio_gateway_url=axio_gateway_url,
        user_model=tau_user_model,
        user_provider=tau_user_provider,
        user_strategy=tau_user_strategy,
        environments=environments,
        limit=limit,
        max_steps=_safe_int(execution.get("max_steps") or tau_max_steps),
        max_output_tokens=_safe_int(preflight.get("max_output_tokens")),
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(harness_root),
            env=_tau_bench_worker_environment(harness_root),
            capture_output=True,
            text=True,
            timeout=_tau_bench_process_timeout(
                case_count=len(cases),
                max_steps=_safe_int(execution.get("max_steps") or tau_max_steps),
            ),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _tau_bench_failed_generation_receipt(
            preflight=preflight,
            error_type=type(exc).__name__,
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
        )
    if completed.returncode != 0 or not results_path.is_file() or not interactions_path.is_file():
        return _tau_bench_failed_generation_receipt(
            preflight=preflight,
            error_type="TauBenchWorkerFailed" if completed.returncode else "TauBenchWorkerResultMissing",
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
            stdout=str(completed.stdout or ""),
            stderr=str(completed.stderr or ""),
            return_code=completed.returncode,
        )

    try:
        metadata_rows, sample_rows = _tau_bench_generation_rows(
            source_cases=cases,
            result_path=results_path,
            candidate=candidate,
            api_format=str(preflight.get("api_format") or ""),
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return _tau_bench_failed_generation_receipt(
            preflight=preflight,
            error_type=type(exc).__name__,
            latency_ms=(time.monotonic() - started) * 1000,
            command=command,
            stdout=str(completed.stdout or ""),
            stderr=str(completed.stderr or ""),
            return_code=completed.returncode,
        )

    _write_private_jsonl(samples_path, sample_rows)
    _write_private_jsonl(metadata_path, metadata_rows)
    generation_binding = _generation_binding_receipt(
        preflight=preflight,
        candidate=candidate,
        case_set_digest_sha256=str(preflight.get("case_set_digest_sha256") or ""),
        metadata_rows=metadata_rows,
        max_output_tokens=_safe_int(preflight.get("max_output_tokens")),
    )
    _write_private_json(binding_path, generation_binding)
    succeeded = [row for row in metadata_rows if row.get("status") == "completed"]
    receipt = {
        "schema": "axio_fusion_api.official_harness_generation.v1",
        "status": "generated" if len(succeeded) == len(metadata_rows) else "partial",
        "suite_id": "tau_bench",
        "task_format": "tool_call_ast",
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "candidate_binding": _safe_candidate_binding(candidate),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(candidate),
        "generation_protocol": dict(preflight.get("generation_protocol") or {}),
        "max_output_tokens": _safe_int(preflight.get("max_output_tokens")),
        "case_count": len(metadata_rows),
        "completed_case_count": len(succeeded),
        "failed_case_count": len(metadata_rows) - len(succeeded),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "private_samples_path_sha256": sha256_text(str(samples_path)),
        "generation_metadata_path_sha256": sha256_text(str(metadata_path)),
        "generation_receipt_path_sha256": sha256_text(str(receipt_path)),
        "generation_binding_path_sha256": sha256_text(str(binding_path)),
        "tau_private_results_path_sha256": sha256_text(str(results_path)),
        "tau_private_interactions_path_sha256": sha256_text(str(interactions_path)),
        "generation_binding_digest_sha256": str(generation_binding.get("generation_binding_digest_sha256") or ""),
        "generation_metadata_digest_sha256": sha256_text(stable_json(metadata_rows)),
        "gateway_configured": bool(str(axio_gateway_url or "")),
        "gateway_url_sha256": sha256_text(str(axio_gateway_url)) if axio_gateway_url else "",
        "model_calls_performed": True,
        "official_harness_execution_performed": True,
        "tau_user_simulator_configuration_sha256": str(
            (preflight.get("tau_user_simulator") or {}).get("configuration_sha256")
            if isinstance(preflight.get("tau_user_simulator"), Mapping)
            else ""
        ),
        "preflight": _safe_preflight_reference(preflight),
        "private_sample_store_used": True,
        "raw_private_samples_location_disclosed": False,
        "raw_prompts_persisted_in_receipt": False,
        "raw_model_outputs_persisted_in_receipt": False,
        "raw_user_simulator_content_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    _write_private_json(receipt_path, receipt)
    return receipt


def _generate_mt_bench_samples(
    *,
    preflight: Mapping[str, Any],
    dataset_path: Path,
    harness_root: Path,
    private_run_dir: Path,
    candidate: Mapping[str, Any],
    registry_path: str | Path | None,
    provider_baseline_freeze_manifest_path: str | Path | None,
    axio_gateway_url: str | None,
    limit: int | None,
    engine: FusionEngine | None,
    client: HTTPProviderClient | None,
    mt_comparison_candidate_id: str | None,
    mt_judge_candidate_id: str | None,
    mt_judge_registry_path: str | Path | None,
    mt_judge_max_output_tokens: int,
) -> dict[str, Any]:
    """Generate both fixed two-turn MT-Bench answer sets in one private run."""

    del harness_root, candidate
    bindings = _mt_bench_runtime_bindings(
        preflight=preflight,
        candidate_id=str(preflight.get("candidate_id") or ""),
        api_format=str(preflight.get("api_format") or ""),
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
        mt_comparison_candidate_id=mt_comparison_candidate_id,
        mt_judge_candidate_id=mt_judge_candidate_id,
        mt_judge_registry_path=mt_judge_registry_path,
        axio_gateway_url=axio_gateway_url,
        mt_judge_max_output_tokens=mt_judge_max_output_tokens,
    )
    if bindings["ready"] is not True:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=bindings["reason_codes"],
        )
    try:
        cases, _, invalid_rows = _load_mt_bench_source_cases(dataset_path, limit=limit)
    except _MTBenchSourceError as exc:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=[exc.reason_code],
        )
    if invalid_rows or not cases:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=[
                "official_harness_mt_bench_source_rows_invalid"
                if invalid_rows
                else "official_harness_case_set_empty"
            ],
        )
    if _case_set_digest("mt_bench_work", [str(case["case_id"]) for case in cases]) != str(
        preflight.get("case_set_digest_sha256") or ""
    ):
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=["official_harness_mt_bench_case_set_changed_after_preflight"],
        )

    private_root = _ensure_private_run_dir(private_run_dir)
    private_root_reasons = _private_generation_root_reasons(private_root)
    if private_root_reasons:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_generation.v1",
            preflight=preflight,
            reason_codes=private_root_reasons,
        )

    target = bindings["target"]
    comparison = bindings["comparison"]
    active_engine = engine or FusionEngine(load_registry(registry_path), client=client)
    target_samples, target_metadata = _mt_bench_generate_dialogues(
        cases=cases,
        candidate=target,
        engine=active_engine,
        client=client,
        max_output_tokens=_safe_int(preflight.get("max_output_tokens")),
        axio_gateway_url=axio_gateway_url,
    )
    comparison_samples, comparison_metadata = _mt_bench_generate_dialogues(
        cases=cases,
        candidate=comparison,
        engine=active_engine,
        client=client,
        max_output_tokens=_safe_int(preflight.get("max_output_tokens")),
        axio_gateway_url=None,
    )

    samples_path = private_root / "samples.private.jsonl"
    metadata_path = private_root / "generation.safe.jsonl"
    receipt_path = private_root / "generation_receipt.safe.json"
    binding_path = private_root / _GENERATION_BINDING_FILENAME
    comparison_samples_path = private_root / _MT_BENCH_COMPARISON_SAMPLES_FILENAME
    comparison_metadata_path = private_root / _MT_BENCH_COMPARISON_METADATA_FILENAME
    comparison_binding_path = private_root / _MT_BENCH_COMPARISON_GENERATION_BINDING_FILENAME
    pair_binding_path = private_root / _MT_BENCH_PAIR_BINDING_FILENAME
    _write_private_jsonl(samples_path, target_samples)
    _write_private_jsonl(metadata_path, target_metadata)
    _write_private_jsonl(comparison_samples_path, comparison_samples)
    _write_private_jsonl(comparison_metadata_path, comparison_metadata)

    target_protocol = (
        preflight.get("generation_protocol")
        if isinstance(preflight.get("generation_protocol"), Mapping)
        else {}
    )
    comparison_protocol = (
        preflight.get("mt_bench_comparison_generation_protocol")
        if isinstance(preflight.get("mt_bench_comparison_generation_protocol"), Mapping)
        else {}
    )
    target_binding = _generation_binding_receipt(
        preflight=preflight,
        candidate=target,
        case_set_digest_sha256=str(preflight.get("case_set_digest_sha256") or ""),
        metadata_rows=target_metadata,
        max_output_tokens=_safe_int(preflight.get("max_output_tokens")),
        generation_protocol=target_protocol,
    )
    comparison_binding = _generation_binding_receipt(
        preflight=preflight,
        candidate=comparison,
        case_set_digest_sha256=str(preflight.get("case_set_digest_sha256") or ""),
        metadata_rows=comparison_metadata,
        max_output_tokens=_safe_int(preflight.get("max_output_tokens")),
        generation_protocol=comparison_protocol,
    )
    pair_binding = _mt_bench_pair_binding_receipt(
        preflight=preflight,
        target=target,
        comparison=comparison,
        judge=bindings["judge"],
        target_metadata=target_metadata,
        comparison_metadata=comparison_metadata,
        target_generation_binding=target_binding,
        comparison_generation_binding=comparison_binding,
    )
    _write_private_json(binding_path, target_binding)
    _write_private_json(comparison_binding_path, comparison_binding)
    _write_private_json(pair_binding_path, pair_binding)

    target_completed = sum(1 for row in target_metadata if row.get("status") == "completed")
    comparison_completed = sum(1 for row in comparison_metadata if row.get("status") == "completed")
    all_completed = target_completed == len(cases) and comparison_completed == len(cases)
    receipt = {
        "schema": "axio_fusion_api.official_harness_generation.v1",
        "status": "generated" if all_completed else "partial",
        "suite_id": "mt_bench_work",
        "task_format": "external_pairwise_judge",
        "candidate_id": str(target.get("candidate_id") or ""),
        "candidate_kind": str(target.get("candidate_kind") or ""),
        "api_format": str(target.get("api_format") or ""),
        "candidate_binding": _safe_candidate_binding(target),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(target),
        "generation_protocol": dict(target_protocol),
        "mt_bench_comparison_generation_protocol": dict(comparison_protocol),
        "mt_bench_comparison": _safe_mt_bench_candidate_binding(comparison),
        "mt_bench_judge": _safe_mt_bench_candidate_binding(bindings["judge"]),
        "mt_bench_execution": dict(bindings["execution"]),
        "max_output_tokens": _safe_int(preflight.get("max_output_tokens")),
        "case_count": len(cases),
        "completed_case_count": target_completed,
        "failed_case_count": len(cases) - target_completed,
        "comparison_completed_case_count": comparison_completed,
        "comparison_failed_case_count": len(cases) - comparison_completed,
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "private_samples_path_sha256": sha256_text(str(samples_path)),
        "generation_metadata_path_sha256": sha256_text(str(metadata_path)),
        "generation_receipt_path_sha256": sha256_text(str(receipt_path)),
        "generation_binding_path_sha256": sha256_text(str(binding_path)),
        "generation_binding_digest_sha256": str(target_binding.get("generation_binding_digest_sha256") or ""),
        "generation_metadata_digest_sha256": sha256_text(stable_json(target_metadata)),
        "mt_bench_comparison_samples_path_sha256": sha256_text(str(comparison_samples_path)),
        "mt_bench_comparison_metadata_path_sha256": sha256_text(str(comparison_metadata_path)),
        "mt_bench_comparison_generation_binding_path_sha256": sha256_text(str(comparison_binding_path)),
        "mt_bench_comparison_generation_binding_digest_sha256": str(
            comparison_binding.get("generation_binding_digest_sha256") or ""
        ),
        "mt_bench_comparison_metadata_digest_sha256": sha256_text(stable_json(comparison_metadata)),
        "mt_bench_pair_binding_path_sha256": sha256_text(str(pair_binding_path)),
        "mt_bench_pair_binding_digest_sha256": str(pair_binding.get("pair_binding_digest_sha256") or ""),
        "gateway_configured": bool(str(axio_gateway_url or "").strip()),
        "gateway_url_sha256": sha256_text(str(axio_gateway_url)) if axio_gateway_url else "",
        "model_calls_performed": True,
        "official_harness_execution_performed": False,
        "preflight": _safe_preflight_reference(preflight),
        "private_sample_store_used": True,
        "raw_private_samples_location_disclosed": False,
        "raw_prompts_persisted_in_receipt": False,
        "raw_model_outputs_persisted_in_receipt": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    _write_private_json(receipt_path, receipt)
    return receipt


def _mt_bench_generate_dialogues(
    *,
    cases: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    engine: FusionEngine,
    client: HTTPProviderClient | None,
    max_output_tokens: int,
    axio_gateway_url: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    samples: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        started = time.monotonic()
        turns = [str(turn) for turn in case.get("turns", [])]
        outputs: list[str] = []
        completions: list[Any] = []
        status = "completed"
        error_type = ""
        for turn_index, turn in enumerate(turns):
            messages: list[dict[str, str]] = [
                {"role": "system", "content": _MT_BENCH_SYSTEM_PROMPT},
                {"role": "user", "content": turns[0]},
            ]
            if turn_index == 1:
                messages.extend(
                    [
                        {"role": "assistant", "content": outputs[0]},
                        {"role": "user", "content": turn},
                    ]
                )
            try:
                completion = _complete_official_harness_candidate(
                    candidate=candidate,
                    engine=engine,
                    client=client,
                    prompt=turn,
                    system=_MT_BENCH_SYSTEM_PROMPT,
                    task_type="daily_work",
                    max_output_tokens=max_output_tokens,
                    axio_gateway_url=axio_gateway_url,
                    messages=tuple(messages),
                )
            except Exception as exc:  # noqa: BLE001 - provider details must not escape the private run.
                status = "failed"
                error_type = type(exc).__name__
                break
            outputs.append(str(completion.text or ""))
            completions.append(completion)
        while len(outputs) < 2:
            outputs.append("")
        cost = _mt_bench_combined_cost(completions)
        invocation = _mt_bench_generation_invocation(completions, candidate=candidate)
        samples.append(
            {
                "question_id": str(case.get("source_identifier") or ""),
                "choices": [{"index": 0, "turns": outputs[:2]}],
            }
        )
        metadata_rows.append(
            {
                "case_index": index,
                "case_id": str(case.get("case_id") or ""),
                "status": status,
                "error_type": error_type[:120],
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "output_sha256": sha256_text(stable_json(outputs[:2])),
                **_safe_cost_fields(cost),
                "public_api_invocation": invocation,
                "raw_prompt_persisted": False,
                "raw_model_output_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }
        )
    return samples, metadata_rows


def _mt_bench_combined_cost(completions: Sequence[Any]) -> dict[str, Any]:
    receipts = [
        completion.cost
        for completion in completions
        if isinstance(getattr(completion, "cost", None), Mapping)
    ]
    if not receipts:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "pricing_known": False,
            "provider_call_count": 0,
        }
    return {
        "input_tokens": sum(_safe_int(receipt.get("input_tokens")) for receipt in receipts),
        "output_tokens": sum(_safe_int(receipt.get("output_tokens")) for receipt in receipts),
        "estimated_cost_usd": round(
            sum(max(0.0, _safe_float(receipt.get("estimated_cost_usd"))) for receipt in receipts),
            8,
        ),
        "pricing_known": all(receipt.get("pricing_known") is True for receipt in receipts),
        "provider_call_count": sum(_safe_int(receipt.get("provider_call_count")) for receipt in receipts),
    }


def _mt_bench_generation_invocation(
    completions: Sequence[Any],
    *,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    invocations = [
        dict(completion.api_invocation)
        for completion in completions
        if isinstance(getattr(completion, "api_invocation", None), Mapping)
    ]
    public_axio = candidate.get("candidate_kind") == "public_axio"
    http_gateway_turn_count = sum(
        1
        for item in invocations
        if item.get("transport") == "http_gateway"
        and item.get("network_calls_performed") is True
    )
    matching_format_turn_count = sum(
        1
        for item in invocations
        if str(item.get("api_format") or "") == str(candidate.get("api_format") or "")
    )
    return {
        "schema": "axio_fusion_api.mt_bench_generation_invocation.v1",
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "api_format": str(candidate.get("api_format") or ""),
        "public_api_surface_used": bool(invocations) and all(
            item.get("public_api_surface_used") is True for item in invocations
        ),
        "dialogue_turn_count": len(invocations),
        "transport": "http_gateway" if public_axio and http_gateway_turn_count == len(invocations) and invocations else "",
        "network_calls_performed": public_axio and bool(invocations) and http_gateway_turn_count == len(invocations),
        "http_gateway_call_count": http_gateway_turn_count,
        "network_call_count": http_gateway_turn_count,
        "matching_api_format_turn_count": matching_format_turn_count,
        "all_turns_match_candidate_api_format": bool(invocations) and matching_format_turn_count == len(invocations),
        "turn_invocation_digest_sha256": sha256_text(stable_json(invocations)),
        "raw_provider_identifiers_persisted": False,
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _mt_bench_pair_binding_receipt(
    *,
    preflight: Mapping[str, Any],
    target: Mapping[str, Any],
    comparison: Mapping[str, Any],
    judge: Mapping[str, Any],
    target_metadata: Sequence[Mapping[str, Any]],
    comparison_metadata: Sequence[Mapping[str, Any]],
    target_generation_binding: Mapping[str, Any],
    comparison_generation_binding: Mapping[str, Any],
) -> dict[str, Any]:
    execution = preflight.get("mt_bench_execution") if isinstance(preflight.get("mt_bench_execution"), Mapping) else {}
    payload = {
        "schema": "axio_fusion_api.mt_bench_pair_binding.v1",
        "suite_id": "mt_bench_work",
        "case_count": len(target_metadata),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "target_candidate_id_sha256": sha256_text(str(target.get("candidate_id") or "")),
        "target_candidate_kind": str(target.get("candidate_kind") or ""),
        "target_profile_id_sha256": str(target.get("profile_id_sha256") or ""),
        "target_api_format": str(target.get("api_format") or ""),
        "comparison_candidate_id_sha256": sha256_text(str(comparison.get("candidate_id") or "")),
        "comparison_candidate_kind": str(comparison.get("candidate_kind") or ""),
        "comparison_profile_id_sha256": str(comparison.get("profile_id_sha256") or ""),
        "comparison_api_format": str(comparison.get("api_format") or ""),
        "judge_candidate_id_sha256": sha256_text(str(judge.get("candidate_id") or "")),
        "judge_profile_id_sha256": str(judge.get("profile_id_sha256") or ""),
        "judge_api_format": str(judge.get("api_format") or ""),
        "target_generation_metadata_digest_sha256": sha256_text(stable_json(list(target_metadata))),
        "comparison_generation_metadata_digest_sha256": sha256_text(stable_json(list(comparison_metadata))),
        "target_generation_binding_digest_sha256": str(
            target_generation_binding.get("generation_binding_digest_sha256") or ""
        ),
        "comparison_generation_binding_digest_sha256": str(
            comparison_generation_binding.get("generation_binding_digest_sha256") or ""
        ),
        "target_generation_protocol_digest_sha256": str(
            (preflight.get("generation_protocol") or {}).get("generation_protocol_digest_sha256")
            if isinstance(preflight.get("generation_protocol"), Mapping)
            else ""
        ),
        "comparison_generation_protocol_digest_sha256": str(
            (preflight.get("mt_bench_comparison_generation_protocol") or {}).get(
                "generation_protocol_digest_sha256"
            )
            if isinstance(preflight.get("mt_bench_comparison_generation_protocol"), Mapping)
            else ""
        ),
        "execution_configuration_sha256": str(execution.get("configuration_sha256") or ""),
        "two_turn_dialogue": execution.get("two_turn_dialogue") is True,
        "position_balanced": execution.get("position_balanced") is True,
        "judge_calls_per_case": _safe_int(execution.get("judge_calls_per_case")),
        "judge_cross_provider_from_target": execution.get("judge_cross_provider_from_target") is True,
        "judge_cross_provider_from_comparison": execution.get("judge_cross_provider_from_comparison") is True,
        "raw_candidate_ids_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    payload["pair_binding_digest_sha256"] = sha256_text(stable_json(payload))
    return payload


def _evaluate_mt_bench_samples(
    *,
    preflight: Mapping[str, Any],
    dataset_path: Path,
    harness_root: Path,
    private_run_dir: Path,
    candidate: Mapping[str, Any],
    registry_path: str | Path | None,
    provider_baseline_freeze_manifest_path: str | Path | None,
    axio_gateway_url: str | None,
    limit: int | None,
    live: bool,
    client: HTTPProviderClient | None,
    mt_comparison_candidate_id: str | None,
    mt_judge_candidate_id: str | None,
    mt_judge_registry_path: str | Path | None,
    mt_judge_max_output_tokens: int,
) -> dict[str, Any]:
    """Judge a generated MT-Bench pair with FastChat's fixed paired protocol."""

    del candidate
    if not live:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=["mt_bench_live_judge_required"],
        )
    bindings = _mt_bench_runtime_bindings(
        preflight=preflight,
        candidate_id=str(preflight.get("candidate_id") or ""),
        api_format=str(preflight.get("api_format") or ""),
        registry_path=registry_path,
        provider_baseline_freeze_manifest_path=provider_baseline_freeze_manifest_path,
        mt_comparison_candidate_id=mt_comparison_candidate_id,
        mt_judge_candidate_id=mt_judge_candidate_id,
        mt_judge_registry_path=mt_judge_registry_path,
        axio_gateway_url=axio_gateway_url,
        mt_judge_max_output_tokens=mt_judge_max_output_tokens,
    )
    if bindings["ready"] is not True:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=bindings["reason_codes"],
        )
    try:
        cases, _, invalid_rows = _load_mt_bench_source_cases(dataset_path, limit=limit)
        if invalid_rows or not cases:
            raise _MTBenchSourceError(
                "official_harness_mt_bench_source_rows_invalid"
                if invalid_rows
                else "official_harness_case_set_empty"
            )
        if _case_set_digest("mt_bench_work", [str(case["case_id"]) for case in cases]) != str(
            preflight.get("case_set_digest_sha256") or ""
        ):
            raise _MTBenchSourceError("official_harness_mt_bench_case_set_changed_after_preflight")
    except _MTBenchSourceError as exc:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=[exc.reason_code],
        )

    target = bindings["target"]
    comparison = bindings["comparison"]
    judge = bindings["judge"]
    target_samples_path = private_run_dir / "samples.private.jsonl"
    target_metadata_path = private_run_dir / "generation.safe.jsonl"
    target_generation_binding_path = private_run_dir / _GENERATION_BINDING_FILENAME
    comparison_samples_path = private_run_dir / _MT_BENCH_COMPARISON_SAMPLES_FILENAME
    comparison_metadata_path = private_run_dir / _MT_BENCH_COMPARISON_METADATA_FILENAME
    comparison_generation_binding_path = private_run_dir / _MT_BENCH_COMPARISON_GENERATION_BINDING_FILENAME
    pair_binding_path = private_run_dir / _MT_BENCH_PAIR_BINDING_FILENAME
    required_paths = (
        target_samples_path,
        target_metadata_path,
        target_generation_binding_path,
        comparison_samples_path,
        comparison_metadata_path,
        comparison_generation_binding_path,
        pair_binding_path,
    )
    if not all(path.is_file() for path in required_paths):
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=["private_generated_samples_missing"],
        )
    target_generation = _load_generation_binding(
        target_generation_binding_path,
        preflight=preflight,
        candidate=target,
        metadata_path=target_metadata_path,
    )
    comparison_preflight = _mt_bench_comparison_preflight(preflight, comparison)
    comparison_generation = _load_generation_binding(
        comparison_generation_binding_path,
        preflight=comparison_preflight,
        candidate=comparison,
        metadata_path=comparison_metadata_path,
    )
    artifact_reasons = [
        *target_generation.get("reason_codes", []),
        *comparison_generation.get("reason_codes", []),
    ]
    try:
        target_metadata = list(_iter_private_jsonl(target_metadata_path))
        comparison_metadata = list(_iter_private_jsonl(comparison_metadata_path))
        pair_binding_result = _load_mt_bench_pair_binding(
            pair_binding_path,
            preflight=preflight,
            target=target,
            comparison=comparison,
            judge=judge,
            target_metadata=target_metadata,
            comparison_metadata=comparison_metadata,
            target_generation_binding_digest=str(
                target_generation.get("generation_binding_digest_sha256") or ""
            ),
            comparison_generation_binding_digest=str(
                comparison_generation.get("generation_binding_digest_sha256") or ""
            ),
        )
        artifact_reasons.extend(pair_binding_result.get("reason_codes", []))
        target_answers = _load_mt_bench_private_answers(target_samples_path, cases=cases)
        comparison_answers = _load_mt_bench_private_answers(comparison_samples_path, cases=cases)
        judge_templates = _load_mt_bench_judge_templates(
            harness_root / "fastchat/llm_judge/data/judge_prompts.jsonl"
        )
        reference_answers = _load_mt_bench_reference_answers(
            harness_root / "fastchat/llm_judge/data/mt_bench/reference_answer/gpt-4.jsonl",
            cases=cases,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _mt_bench_failed_evaluation_receipt(
            preflight=preflight,
            error_type=type(exc).__name__,
        )
    if artifact_reasons:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=artifact_reasons,
        )
    pair_binding = (
        dict(pair_binding_result.get("payload") or {})
        if isinstance(pair_binding_result.get("payload"), Mapping)
        else {}
    )

    judge_client = ensure_strict_streaming_client(client)
    judge_engine = FusionEngine((), client=judge_client)
    judgment_rows: list[dict[str, Any]] = []
    judgment_receipts: list[dict[str, Any]] = []
    target_metadata_by_case = _mt_bench_metadata_by_case(target_metadata)
    comparison_metadata_by_case = _mt_bench_metadata_by_case(comparison_metadata)
    for index, case in enumerate(cases):
        private_row, safe_row = _mt_bench_judge_case(
            index=index,
            case=case,
            target_turns=target_answers[str(case["case_id"])],
            comparison_turns=comparison_answers[str(case["case_id"])],
            reference_turns=reference_answers.get(str(case["case_id"])),
            judge_templates=judge_templates,
            judge=judge,
            engine=judge_engine,
            client=judge_client,
            max_output_tokens=_safe_int(bindings["execution"].get("judge_max_output_tokens")),
        )
        judgment_rows.append(private_row)
        judgment_receipts.append(safe_row)

    judgments_path = private_run_dir / _MT_BENCH_JUDGMENTS_FILENAME
    judgment_receipts_path = private_run_dir / _MT_BENCH_JUDGMENT_RECEIPTS_FILENAME
    _write_private_jsonl(judgments_path, judgment_rows)
    _write_private_jsonl(judgment_receipts_path, judgment_receipts)
    target_scored_rows, comparison_scored_rows = _mt_bench_scored_rows(
        cases=cases,
        judgments=judgment_receipts,
        target_metadata=target_metadata_by_case,
        comparison_metadata=comparison_metadata_by_case,
    )
    target_scored_path = private_run_dir / _SCORED_ROWS_FILENAME
    comparison_scored_path = private_run_dir / _MT_BENCH_COMPARISON_SCORED_ROWS_FILENAME
    _write_private_jsonl(target_scored_path, target_scored_rows)
    _write_private_jsonl(comparison_scored_path, comparison_scored_rows)

    target_receipt = _mt_bench_evaluation_receipt(
        preflight=preflight,
        candidate=target,
        counterpart=comparison,
        side="target",
        generation_protocol=preflight.get("generation_protocol") if isinstance(preflight.get("generation_protocol"), Mapping) else {},
        generation_binding_digest_sha256=str(target_generation.get("generation_binding_digest_sha256") or ""),
        scored_rows=target_scored_rows,
        scored_path=target_scored_path,
        judge_receipts=judgment_receipts,
        judgments_path=judgments_path,
        judgment_receipts_path=judgment_receipts_path,
        pair_binding=pair_binding,
        pair_binding_path=pair_binding_path,
        counterpart_scored_path=comparison_scored_path,
        execution=bindings["execution"],
    )
    comparison_receipt = _mt_bench_evaluation_receipt(
        preflight=comparison_preflight,
        candidate=comparison,
        counterpart=target,
        side="comparison",
        generation_protocol=(
            preflight.get("mt_bench_comparison_generation_protocol")
            if isinstance(preflight.get("mt_bench_comparison_generation_protocol"), Mapping)
            else {}
        ),
        generation_binding_digest_sha256=str(comparison_generation.get("generation_binding_digest_sha256") or ""),
        scored_rows=comparison_scored_rows,
        scored_path=comparison_scored_path,
        judge_receipts=judgment_receipts,
        judgments_path=judgments_path,
        judgment_receipts_path=judgment_receipts_path,
        pair_binding=pair_binding,
        pair_binding_path=pair_binding_path,
        counterpart_scored_path=target_scored_path,
        execution=bindings["execution"],
    )
    _write_private_json(private_run_dir / _EVALUATION_RECEIPT_FILENAME, target_receipt)
    _write_private_json(
        private_run_dir / _MT_BENCH_COMPARISON_EVALUATION_RECEIPT_FILENAME,
        comparison_receipt,
    )
    return target_receipt


def _mt_bench_comparison_preflight(
    preflight: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(preflight)
    payload["candidate_id"] = str(comparison.get("candidate_id") or "")
    payload["candidate_kind"] = str(comparison.get("candidate_kind") or "")
    payload["api_format"] = str(comparison.get("api_format") or "")
    payload["candidate_binding"] = _safe_candidate_binding(comparison)
    payload["provider_baseline_freeze_binding"] = _safe_provider_baseline_freeze_binding(comparison)
    protocol = preflight.get("mt_bench_comparison_generation_protocol")
    payload["generation_protocol"] = dict(protocol) if isinstance(protocol, Mapping) else {}
    return payload


def _load_mt_bench_pair_binding(
    path: Path,
    *,
    preflight: Mapping[str, Any],
    target: Mapping[str, Any],
    comparison: Mapping[str, Any],
    judge: Mapping[str, Any],
    target_metadata: Sequence[Mapping[str, Any]],
    comparison_metadata: Sequence[Mapping[str, Any]],
    target_generation_binding_digest: str,
    comparison_generation_binding_digest: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    payload = _load_private_json_object(
        path,
        missing_reason="official_harness_mt_bench_pair_binding_missing",
        unreadable_reason="official_harness_mt_bench_pair_binding_unreadable",
        reasons=reasons,
    )
    if not payload:
        return {"ready": False, "reason_codes": sorted(set(reasons)), "payload": {}}
    declared = str(payload.get("pair_binding_digest_sha256") or "")
    body = dict(payload)
    body.pop("pair_binding_digest_sha256", None)
    if str(payload.get("schema") or "") != "axio_fusion_api.mt_bench_pair_binding.v1":
        reasons.append("official_harness_mt_bench_pair_binding_schema_invalid")
    if not _looks_like_sha256(declared) or declared != sha256_text(stable_json(body)):
        reasons.append("official_harness_mt_bench_pair_binding_digest_invalid")
    expected = {
        "suite_id": "mt_bench_work",
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "target_candidate_id_sha256": sha256_text(str(target.get("candidate_id") or "")),
        "comparison_candidate_id_sha256": sha256_text(str(comparison.get("candidate_id") or "")),
        "judge_candidate_id_sha256": sha256_text(str(judge.get("candidate_id") or "")),
        "target_generation_metadata_digest_sha256": sha256_text(stable_json(list(target_metadata))),
        "comparison_generation_metadata_digest_sha256": sha256_text(stable_json(list(comparison_metadata))),
        "target_generation_binding_digest_sha256": str(target_generation_binding_digest or ""),
        "comparison_generation_binding_digest_sha256": str(comparison_generation_binding_digest or ""),
        "target_generation_protocol_digest_sha256": str(
            (preflight.get("generation_protocol") or {}).get("generation_protocol_digest_sha256")
            if isinstance(preflight.get("generation_protocol"), Mapping)
            else ""
        ),
        "comparison_generation_protocol_digest_sha256": str(
            (preflight.get("mt_bench_comparison_generation_protocol") or {}).get(
                "generation_protocol_digest_sha256"
            )
            if isinstance(preflight.get("mt_bench_comparison_generation_protocol"), Mapping)
            else ""
        ),
        "execution_configuration_sha256": str(
            (preflight.get("mt_bench_execution") or {}).get("configuration_sha256")
            if isinstance(preflight.get("mt_bench_execution"), Mapping)
            else ""
        ),
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            reasons.append(f"official_harness_mt_bench_pair_binding_{field}_mismatch")
    for field, expected_value in (
        ("target_profile_id_sha256", str(target.get("profile_id_sha256") or "")),
        ("comparison_profile_id_sha256", str(comparison.get("profile_id_sha256") or "")),
        ("judge_profile_id_sha256", str(judge.get("profile_id_sha256") or "")),
        ("target_api_format", str(target.get("api_format") or "")),
        ("comparison_api_format", str(comparison.get("api_format") or "")),
        ("judge_api_format", str(judge.get("api_format") or "")),
    ):
        if str(payload.get(field) or "") != expected_value:
            reasons.append(f"official_harness_mt_bench_pair_binding_{field}_mismatch")
    if payload.get("two_turn_dialogue") is not True:
        reasons.append("official_harness_mt_bench_pair_binding_two_turn_required")
    if payload.get("position_balanced") is not True or _safe_int(payload.get("judge_calls_per_case")) != 2:
        reasons.append("official_harness_mt_bench_pair_binding_position_balancing_invalid")
    if payload.get("judge_cross_provider_from_target") is not True:
        reasons.append("official_harness_mt_bench_pair_binding_judge_target_independence_invalid")
    if payload.get("judge_cross_provider_from_comparison") is not True:
        reasons.append("official_harness_mt_bench_pair_binding_judge_comparison_independence_invalid")
    if _contains_true_flag(payload):
        reasons.append("official_harness_mt_bench_pair_binding_raw_content_flagged")
    return {
        "ready": not reasons,
        "reason_codes": sorted(set(reasons)),
        "payload": payload,
    }


def _load_mt_bench_private_answers(
    path: Path,
    *,
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    case_by_identifier = {
        str(case.get("source_identifier") or ""): str(case.get("case_id") or "")
        for case in cases
    }
    answers: dict[str, list[str]] = {}
    for row in _iter_private_jsonl(path):
        identifier = str(row.get("question_id") or "")
        case_id = case_by_identifier.get(identifier)
        choices = row.get("choices")
        if not case_id or not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("mt_bench_private_answers_invalid")
        choice = choices[0]
        turns = choice.get("turns") if isinstance(choice, Mapping) else None
        if (
            case_id in answers
            or not isinstance(turns, list)
            or len(turns) != 2
            or not all(isinstance(turn, str) for turn in turns)
        ):
            raise ValueError("mt_bench_private_answers_invalid")
        answers[case_id] = [str(turn) for turn in turns]
    if set(answers) != {str(case.get("case_id") or "") for case in cases}:
        raise ValueError("mt_bench_private_answers_case_set_mismatch")
    return answers


def _load_mt_bench_judge_templates(path: Path) -> dict[str, dict[str, Any]]:
    required = {"pair-v2-multi-turn", "pair-math-v1-multi-turn"}
    templates: dict[str, dict[str, Any]] = {}
    for row in _iter_private_jsonl(path):
        name = str(row.get("name") or "")
        if name in required:
            templates[name] = row
    for name in required:
        template = templates.get(name)
        if (
            not isinstance(template, Mapping)
            or str(template.get("type") or "") != "pairwise"
            or not isinstance(template.get("system_prompt"), str)
            or not isinstance(template.get("prompt_template"), str)
            or str(template.get("output_format") or "") != "[[A]]"
        ):
            raise ValueError("mt_bench_judge_template_invalid")
    return templates


def _load_mt_bench_reference_answers(
    path: Path,
    *,
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    required_ids = {
        str(case.get("source_identifier") or ""): str(case.get("case_id") or "")
        for case in cases
        if str(case.get("category") or "") in _MT_BENCH_REFERENCE_CATEGORIES
    }
    if not required_ids:
        return {}
    references: dict[str, list[str]] = {}
    for row in _iter_private_jsonl(path):
        identifier = str(row.get("question_id") or "")
        case_id = required_ids.get(identifier)
        if not case_id:
            continue
        choices = row.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("mt_bench_reference_answers_invalid")
        choice = choices[0]
        turns = choice.get("turns") if isinstance(choice, Mapping) else None
        if (
            case_id in references
            or not isinstance(turns, list)
            or len(turns) != 2
            or not all(isinstance(turn, str) and turn.strip() for turn in turns)
        ):
            raise ValueError("mt_bench_reference_answers_invalid")
        references[case_id] = [str(turn) for turn in turns]
    if set(references) != set(required_ids.values()):
        raise ValueError("mt_bench_reference_answers_case_set_mismatch")
    return references


def _mt_bench_metadata_by_case(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "")
        if not _looks_like_sha256(case_id) or case_id in metadata:
            raise ValueError("mt_bench_generation_metadata_invalid")
        metadata[case_id] = dict(row)
    return metadata


def _mt_bench_judge_case(
    *,
    index: int,
    case: Mapping[str, Any],
    target_turns: Sequence[str],
    comparison_turns: Sequence[str],
    reference_turns: Sequence[str] | None,
    judge_templates: Mapping[str, Mapping[str, Any]],
    judge: Mapping[str, Any],
    engine: FusionEngine,
    client: HTTPProviderClient,
    max_output_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    category = str(case.get("category") or "")
    reference_required = category in _MT_BENCH_REFERENCE_CATEGORIES
    template_name = "pair-math-v1-multi-turn" if reference_required else "pair-v2-multi-turn"
    template = judge_templates[template_name]
    system_prompt = str(template.get("system_prompt") or "")
    first_prompt = _mt_bench_render_judge_prompt(
        template=template,
        case=case,
        answer_a=target_turns,
        answer_b=comparison_turns,
        reference_turns=reference_turns if reference_required else None,
    )
    second_prompt = _mt_bench_render_judge_prompt(
        template=template,
        case=case,
        answer_a=comparison_turns,
        answer_b=target_turns,
        reference_turns=reference_turns if reference_required else None,
    )
    prompts = [first_prompt, second_prompt]
    outputs: list[str] = []
    completions: list[Any] = []
    outcomes: list[str] = []
    error_type = ""
    for call_index, prompt in enumerate(prompts):
        try:
            completion = _complete_official_harness_candidate(
                candidate=judge,
                engine=engine,
                client=client,
                prompt=prompt,
                system=system_prompt,
                task_type="daily_work",
                max_output_tokens=max(1, int(max_output_tokens)),
                axio_gateway_url=None,
            )
        except Exception as exc:  # noqa: BLE001 - keep provider failure details out of receipts.
            error_type = type(exc).__name__
            break
        output = str(completion.text or "")
        outputs.append(output)
        completions.append(completion)
        outcome = _mt_bench_official_verdict(
            output,
            target_is_a=call_index == 0,
        )
        outcomes.append(outcome)
        if outcome == "error":
            error_type = "JudgeVerdictParseError"
    while len(outputs) < 2:
        outputs.append("")
    while len(outcomes) < 2:
        outcomes.append("error")
    completed = not error_type and all(outcome in {"target", "comparison", "tie"} for outcome in outcomes)
    disagreement = completed and outcomes[0] != outcomes[1]
    final_outcome = "tie" if disagreement else outcomes[0] if completed else "error"
    cost = _mt_bench_combined_cost(completions)
    prompt_digest = sha256_text(stable_json(prompts))
    output_digest = sha256_text(stable_json(outputs))
    private_row = {
        "question_id": str(case.get("source_identifier") or ""),
        "g1_user_prompt": first_prompt,
        "g1_judgment": outputs[0],
        "g2_user_prompt": second_prompt,
        "g2_judgment": outputs[1],
        "g1_winner": outcomes[0],
        "g2_winner": outcomes[1],
        "final_winner": final_outcome,
    }
    safe_row = {
        "case_index": index,
        "case_id": str(case.get("case_id") or ""),
        "status": "completed" if completed else "failed",
        "error_type": error_type[:120],
        "judge_template_sha256": sha256_text(template_name),
        "reference_answer_used": reference_required,
        "position_balanced": True,
        "judge_call_count": len(completions),
        "first_position_outcome": outcomes[0],
        "second_position_outcome": outcomes[1],
        "final_outcome": final_outcome,
        "judge_disagreement": disagreement,
        "judge_prompt_sha256": prompt_digest,
        "judge_output_sha256": output_digest,
        "judge_latency_ms": round((time.monotonic() - started) * 1000, 3),
        **_safe_cost_fields(cost),
        "raw_prompt_persisted": False,
        "raw_reference_persisted": False,
        "raw_judge_output_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    return private_row, safe_row


def _mt_bench_render_judge_prompt(
    *,
    template: Mapping[str, Any],
    case: Mapping[str, Any],
    answer_a: Sequence[str],
    answer_b: Sequence[str],
    reference_turns: Sequence[str] | None,
) -> str:
    if len(answer_a) != 2 or len(answer_b) != 2:
        raise ValueError("mt_bench_answer_turn_count_invalid")
    turns = case.get("turns")
    if not isinstance(turns, list) or len(turns) != 2:
        raise ValueError("mt_bench_question_turn_count_invalid")
    values: dict[str, Any] = {
        "question_1": str(turns[0]),
        "question_2": str(turns[1]),
        "answer_a_1": str(answer_a[0]),
        "answer_a_2": str(answer_a[1]),
        "answer_b_1": str(answer_b[0]),
        "answer_b_2": str(answer_b[1]),
    }
    if reference_turns is not None:
        if len(reference_turns) != 2:
            raise ValueError("mt_bench_reference_turn_count_invalid")
        values["ref_answer_1"] = str(reference_turns[0])
        values["ref_answer_2"] = str(reference_turns[1])
    return str(template.get("prompt_template") or "").format(**values)


def _mt_bench_official_verdict(judgment: str, *, target_is_a: bool) -> str:
    """Mirror FastChat's pairwise marker precedence before mapping positions."""

    text = str(judgment or "")
    if "[[A]]" in text:
        return "target" if target_is_a else "comparison"
    if "[[B]]" in text:
        return "comparison" if target_is_a else "target"
    if "[[C]]" in text:
        return "tie"
    return "error"


def _mt_bench_scored_rows(
    *,
    cases: Sequence[Mapping[str, Any]],
    judgments: Sequence[Mapping[str, Any]],
    target_metadata: Mapping[str, Mapping[str, Any]],
    comparison_metadata: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    judgments_by_case = {
        str(row.get("case_id") or ""): row
        for row in judgments
        if isinstance(row, Mapping)
    }
    target_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        case_id = str(case.get("case_id") or "")
        judgment = judgments_by_case.get(case_id, {})
        target_row = _mt_bench_scored_row(
            index=index,
            case_id=case_id,
            side="target",
            metadata=target_metadata.get(case_id, {}),
            judgment=judgment,
        )
        comparison_row = _mt_bench_scored_row(
            index=index,
            case_id=case_id,
            side="comparison",
            metadata=comparison_metadata.get(case_id, {}),
            judgment=judgment,
        )
        target_rows.append(target_row)
        comparison_rows.append(comparison_row)
    return target_rows, comparison_rows


def _mt_bench_scored_row(
    *,
    index: int,
    case_id: str,
    side: str,
    metadata: Mapping[str, Any],
    judgment: Mapping[str, Any],
) -> dict[str, Any]:
    status = "completed"
    error_type = ""
    outcome = str(judgment.get("final_outcome") or "error")
    if str(metadata.get("status") or "") != "completed":
        status = "generation_failed"
        error_type = str(metadata.get("error_type") or "GenerationFailed")[:120]
    elif str(judgment.get("status") or "") != "completed":
        status = "judge_failed"
        error_type = str(judgment.get("error_type") or "JudgeFailed")[:120]
    if status == "completed":
        if outcome == side:
            score = 1.0
        elif outcome in {"target", "comparison", "tie"}:
            score = 0.5 if outcome == "tie" else 0.0
        else:
            status = "judge_failed"
            error_type = "JudgeVerdictParseError"
            score = 0.0
    else:
        score = 0.0
    return {
        "case_index": index,
        "case_id": case_id,
        "status": status,
        "passed": status == "completed" and score == 1.0,
        "correct": status == "completed" and score == 1.0,
        "score": score,
        "metric": "win_rate",
        "latency_ms": round(max(0.0, _safe_float(metadata.get("latency_ms"))), 3),
        "prediction_sha256": str(metadata.get("output_sha256") or ""),
        "output_sha256": str(metadata.get("output_sha256") or ""),
        **_safe_cost_fields(metadata),
        "error_type": error_type,
        "position_balanced": True,
        "judge_disagreement": judgment.get("judge_disagreement") is True,
        "judge_call_count": _safe_int(judgment.get("judge_call_count")),
        "judge_output_sha256": str(judgment.get("judge_output_sha256") or ""),
        "raw_input_persisted": False,
        "raw_reference_persisted": False,
        "raw_label_persisted": False,
        "raw_model_output_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _mt_bench_evaluation_receipt(
    *,
    preflight: Mapping[str, Any],
    candidate: Mapping[str, Any],
    counterpart: Mapping[str, Any],
    side: str,
    generation_protocol: Mapping[str, Any],
    generation_binding_digest_sha256: str,
    scored_rows: Sequence[Mapping[str, Any]],
    scored_path: Path,
    judge_receipts: Sequence[Mapping[str, Any]],
    judgments_path: Path,
    judgment_receipts_path: Path,
    pair_binding: Mapping[str, Any],
    pair_binding_path: Path,
    counterpart_scored_path: Path,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    completed_rows = [row for row in scored_rows if row.get("status") == "completed"]
    passed_rows = [row for row in scored_rows if row.get("passed") is True]
    result_case_alignment = _official_result_case_alignment(preflight, scored_rows)
    normalization = {
        "schema": "axio_fusion_api.official_harness_normalization.v1",
        "input_result_row_count": len(scored_rows),
        "completed_row_count": len(completed_rows),
        "case_set_digest_sha256": _case_set_digest(
            "mt_bench_work", [str(row.get("case_id") or "") for row in scored_rows]
        ),
        "position_balanced": True,
        "judge_call_count": sum(_safe_int(row.get("judge_call_count")) for row in scored_rows),
        "judge_disagreement_count": sum(
            1 for row in scored_rows if row.get("judge_disagreement") is True
        ),
        "raw_result_content_persisted": False,
        "raw_prompts_persisted": False,
        "raw_model_outputs_persisted": False,
        "secrets_persisted": False,
    }
    scores = [float(row.get("score") or 0.0) for row in scored_rows]
    judge_latency_ms = round(
        sum(max(0.0, _safe_float(row.get("judge_latency_ms"))) for row in judge_receipts),
        3,
    )
    judge_cost = {
        "input_tokens": sum(_safe_int(row.get("input_tokens")) for row in judge_receipts),
        "output_tokens": sum(_safe_int(row.get("output_tokens")) for row in judge_receipts),
        "estimated_cost_usd": round(
            sum(max(0.0, _safe_float(row.get("estimated_cost_usd"))) for row in judge_receipts),
            8,
        ),
        "pricing_known": bool(judge_receipts)
        and all(row.get("pricing_known") is True for row in judge_receipts),
        "provider_call_count": sum(_safe_int(row.get("provider_call_count")) for row in judge_receipts),
    }
    all_judgments_completed = all(row.get("status") == "completed" for row in judge_receipts)
    status = (
        "evaluated"
        if len(completed_rows) == len(scored_rows)
        and all_judgments_completed
        and result_case_alignment.get("ready") is True
        else "partial"
    )
    receipt = {
        "schema": _EVALUATION_RECEIPT_SCHEMA,
        "status": status,
        "suite_id": "mt_bench_work",
        "task_format": "external_pairwise_judge",
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "api_format": str(candidate.get("api_format") or ""),
        "candidate_binding": _safe_candidate_binding(candidate),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(candidate),
        "generation_protocol": dict(generation_protocol),
        "generation_binding_digest_sha256": str(generation_binding_digest_sha256 or ""),
        "case_count": len(scored_rows),
        "completed_case_count": len(completed_rows),
        "passed_case_count": len(passed_rows),
        "primary_score": round(sum(scores) / len(scores), 6) if scores else None,
        "primary_metric": "win_rate",
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "safe_scored_rows_path_sha256": sha256_text(str(scored_path)),
        "safe_scored_rows_digest_sha256": sha256_text(stable_json(list(scored_rows))),
        "evaluator_stdout_sha256": sha256_text(""),
        "evaluator_stderr_sha256": sha256_text(""),
        "evaluator_return_code": 0,
        "evaluator_latency_ms": judge_latency_ms,
        "evaluator_command_protocol_sha256": _mt_bench_judge_command_protocol_digest(),
        "judge_latency_ms": judge_latency_ms,
        "judge_call_count": sum(_safe_int(row.get("judge_call_count")) for row in judge_receipts),
        "judge_disagreement_count": sum(
            1 for row in judge_receipts if row.get("judge_disagreement") is True
        ),
        "judge_output_digest_sha256": sha256_text(stable_json(list(judge_receipts))),
        "judge_receipts_path_sha256": sha256_text(str(judgment_receipts_path)),
        "private_judgments_path_sha256": sha256_text(str(judgments_path)),
        "mt_bench_pair_binding_path_sha256": sha256_text(str(pair_binding_path)),
        "mt_bench_pair_binding_digest_sha256": str(pair_binding.get("pair_binding_digest_sha256") or ""),
        "counterpart_scored_rows_path_sha256": sha256_text(str(counterpart_scored_path)),
        "counterpart_candidate_id_sha256": sha256_text(str(counterpart.get("candidate_id") or "")),
        "counterpart_candidate_kind": str(counterpart.get("candidate_kind") or ""),
        "counterpart_profile_id_sha256": str(counterpart.get("profile_id_sha256") or ""),
        "mt_bench_side": str(side),
        "position_balanced": True,
        "mt_bench_execution_configuration_sha256": str(execution.get("configuration_sha256") or ""),
        "judge_cost": _safe_cost_fields(judge_cost),
        "normalization": normalization,
        "result_case_alignment": result_case_alignment,
        "official_import_binding": _official_import_binding(
            preflight=preflight,
            candidate=candidate,
            scored_path=scored_path,
            result_case_alignment=result_case_alignment,
        ),
        "reason_codes": list(result_case_alignment.get("reason_codes") or []),
        "official_harness_execution_performed": True,
        "model_calls_performed": True,
        "preflight": _safe_preflight_reference(preflight),
        "private_sample_store_used": True,
        "raw_private_samples_location_disclosed": False,
        "raw_prompts_persisted_in_receipt": False,
        "raw_model_outputs_persisted_in_receipt": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    receipt["evaluation_receipt_digest_sha256"] = _evaluation_receipt_digest(receipt)
    return receipt


def _mt_bench_judge_command_protocol_digest() -> str:
    return sha256_text(
        stable_json(
            {
                "suite_id": "mt_bench_work",
                "command_kind": "fastchat_pairwise_multi_turn_position_balanced",
                "judge_calls_per_case": 2,
                "reference_categories": sorted(_MT_BENCH_REFERENCE_CATEGORIES),
            }
        )
    )


def _mt_bench_failed_evaluation_receipt(
    *,
    preflight: Mapping[str, Any],
    error_type: str,
) -> dict[str, Any]:
    return {
        "schema": _EVALUATION_RECEIPT_SCHEMA,
        "status": "failed",
        "suite_id": "mt_bench_work",
        "candidate_id": str(preflight.get("candidate_id") or ""),
        "candidate_kind": str(preflight.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "error_type": str(error_type)[:120],
        "evaluator_latency_ms": 0.0,
        "evaluator_return_code": 0,
        "evaluator_stdout_sha256": sha256_text(""),
        "evaluator_stderr_sha256": sha256_text(""),
        "evaluator_command_protocol_sha256": _mt_bench_judge_command_protocol_digest(),
        "model_calls_performed": False,
        "official_harness_execution_performed": True,
        "preflight": _safe_preflight_reference(preflight),
        "raw_error_message_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _evaluate_tau_bench_samples(
    *,
    preflight: Mapping[str, Any],
    dataset_path: Path,
    harness_root: Path,
    private_run_dir: Path,
    candidate: Mapping[str, Any],
    limit: int | None,
) -> dict[str, Any]:
    del harness_root
    samples_path = private_run_dir / "samples.private.jsonl"
    metadata_path = private_run_dir / "generation.safe.jsonl"
    binding_path = private_run_dir / _GENERATION_BINDING_FILENAME
    results_path = private_run_dir / _TAU_BENCH_RESULT_FILENAME
    if not samples_path.is_file() or not metadata_path.is_file() or not results_path.is_file():
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=["private_generated_samples_missing"],
        )
    generation_binding = _load_generation_binding(
        binding_path,
        preflight=preflight,
        candidate=candidate,
        metadata_path=metadata_path,
    )
    if generation_binding.get("ready") is not True:
        return _bridge_blocked_receipt(
            schema="axio_fusion_api.official_harness_evaluation.v1",
            preflight=preflight,
            reason_codes=generation_binding.get("reason_codes") or [],
        )
    execution = preflight.get("tau_execution") if isinstance(preflight.get("tau_execution"), Mapping) else {}
    try:
        source_cases, _, invalid_rows = _load_tau_bench_source_cases(
            dataset_path,
            limit=limit,
            environments=tuple(str(item) for item in execution.get("environments", []) if str(item)),
        )
        if invalid_rows:
            raise ValueError("tau_bench_source_rows_invalid")
        generation = _safe_generation_metadata(metadata_path)
        scored_rows, normalization = _normalize_tau_bench_results(
            source_cases=source_cases,
            result_path=results_path,
            generation=generation,
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return _tau_bench_failed_evaluation_receipt(
            preflight=preflight,
            error_type=type(exc).__name__,
        )
    result_case_alignment = _official_result_case_alignment(preflight, scored_rows)
    scored_path = private_run_dir / _SCORED_ROWS_FILENAME
    receipt_path = private_run_dir / _EVALUATION_RECEIPT_FILENAME
    _write_private_jsonl(scored_path, scored_rows)
    completed_rows = [row for row in scored_rows if row.get("status") == "completed"]
    passed_rows = [row for row in scored_rows if row.get("passed") is True]
    tool_action_count = sum(_safe_int(row.get("tool_action_count")) for row in scored_rows)
    tool_error_count = sum(_safe_int(row.get("tool_error_count")) for row in scored_rows)
    tool_error_rate = round(tool_error_count / tool_action_count, 6) if tool_action_count else 0.0
    receipt = {
        "schema": _EVALUATION_RECEIPT_SCHEMA,
        "status": "evaluated" if len(completed_rows) == len(scored_rows) and result_case_alignment["ready"] is True else "partial",
        "suite_id": "tau_bench",
        "task_format": "tool_call_ast",
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "candidate_binding": _safe_candidate_binding(candidate),
        "provider_baseline_freeze_binding": _safe_provider_baseline_freeze_binding(candidate),
        "generation_protocol": dict(preflight.get("generation_protocol") or {}),
        "generation_binding_digest_sha256": str(generation_binding.get("generation_binding_digest_sha256") or ""),
        "case_count": len(scored_rows),
        "completed_case_count": len(completed_rows),
        "passed_case_count": len(passed_rows),
        "primary_score": round(len(passed_rows) / len(scored_rows), 6) if scored_rows else None,
        "primary_metric": "task_success_rate",
        "tool_error_rate": tool_error_rate,
        "tool_error_count": tool_error_count,
        "tool_action_count": tool_action_count,
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "safe_scored_rows_path_sha256": sha256_text(str(scored_path)),
        "safe_scored_rows_digest_sha256": sha256_text(stable_json(scored_rows)),
        "official_harness_result_path_sha256": sha256_text(str(results_path)),
        "evaluator_stdout_sha256": sha256_text(""),
        "evaluator_stderr_sha256": sha256_text(""),
        "evaluator_return_code": 0,
        "evaluator_latency_ms": 0.0,
        "evaluator_command_protocol_sha256": _tau_bench_command_protocol_digest(),
        "normalization": normalization,
        "result_case_alignment": result_case_alignment,
        "official_import_binding": _official_import_binding(
            preflight=preflight,
            candidate=candidate,
            scored_path=scored_path,
            result_case_alignment=result_case_alignment,
        ),
        "reason_codes": list(result_case_alignment.get("reason_codes") or []),
        "official_harness_execution_performed": True,
        "model_calls_performed": False,
        "preflight": _safe_preflight_reference(preflight),
        "private_sample_store_used": True,
        "raw_private_samples_location_disclosed": False,
        "raw_prompts_persisted_in_receipt": False,
        "raw_model_outputs_persisted_in_receipt": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    receipt["evaluation_receipt_digest_sha256"] = _evaluation_receipt_digest(receipt)
    _write_private_json(receipt_path, receipt)
    return receipt


def _tau_bench_runner_command(
    *,
    python_executable: str,
    harness_root: Path,
    results_path: Path,
    interactions_path: Path,
    candidate: Mapping[str, Any],
    registry_path: str | Path | None,
    api_format: str,
    axio_gateway_url: str | None,
    user_model: str | None,
    user_provider: str | None,
    user_strategy: str,
    environments: Sequence[str],
    limit: int | None,
    max_steps: int,
    max_output_tokens: int,
) -> list[str]:
    runner = Path(__file__).with_name("tau_bench_bridge_runner.py")
    command = [
        python_executable,
        str(runner),
        "--harness-root",
        str(harness_root),
        "--output",
        str(results_path),
        "--interactions-output",
        str(interactions_path),
        "--candidate-kind",
        str(candidate.get("candidate_kind") or ""),
        "--candidate-id",
        str(candidate.get("candidate_id") or ""),
        "--api-format",
        api_format,
        "--user-model",
        str(user_model or ""),
        "--user-provider",
        str(user_provider or ""),
        "--user-strategy",
        str(user_strategy or "llm"),
        "--max-steps",
        str(max(1, int(max_steps))),
        "--max-output-tokens",
        str(max(1, int(max_output_tokens))),
    ]
    for environment in environments:
        command.extend(["--environment", str(environment)])
    if limit is not None:
        command.extend(["--limit", str(max(0, int(limit)))])
    if candidate.get("candidate_kind") == "public_axio":
        command.extend(["--gateway-url", str(axio_gateway_url or "")])
    else:
        command.extend(["--registry", str(registry_path or "")])
    return command


def _tau_bench_worker_environment(harness_root: Path) -> dict[str, str]:
    environment = _official_evaluator_environment(harness_root)
    source_root = str(Path(__file__).resolve().parent.parent)
    current = str(environment.get("PYTHONPATH") or "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_root, str(harness_root), current) if part
    )
    return environment


def _tau_bench_process_timeout(*, case_count: int, max_steps: int) -> float:
    # Each visible candidate turn and each official user-simulator turn can
    # reach its own provider timeout. The broad bound avoids killing a valid
    # long interaction while still making stalled workers observable.
    return max(300.0, float(max(1, case_count) * max(1, max_steps) * 120))


def _tau_bench_command_protocol_digest() -> str:
    return sha256_text(
        stable_json(
            {
                "suite_id": "tau_bench",
                "command_kind": "tau_bench_pinned_native_environment_interaction",
                "candidate_transport": "public_axio_or_frozen_provider_native",
                "hidden_task_goals_sent_to_candidate": False,
            }
        )
    )


def _tau_bench_generation_rows(
    *,
    source_cases: Sequence[Mapping[str, Any]],
    result_path: Path,
    candidate: Mapping[str, Any],
    api_format: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_by_identifier = {
        str(case.get("source_identifier") or ""): dict(case)
        for case in source_cases
    }
    metadata_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, result in enumerate(_iter_private_jsonl(result_path)):
        identifier = str(result.get("source_identifier") or "")
        case = source_by_identifier.get(identifier)
        if case is None or identifier in seen:
            raise ValueError("tau_bench_result_case_not_in_source")
        seen.add(identifier)
        output_hash = str(result.get("output_sha256") or "").strip().lower()
        prediction_hash = str(result.get("prediction_sha256") or "").strip().lower()
        trajectory_hash = str(result.get("trajectory_sha256") or "").strip().lower()
        if not all(_looks_like_sha256(value) for value in (output_hash, prediction_hash, trajectory_hash)):
            raise ValueError("tau_bench_result_output_hash_invalid")
        if output_hash != prediction_hash or output_hash != trajectory_hash:
            raise ValueError("tau_bench_result_output_hash_mismatch")
        status = str(result.get("status") or "").strip().lower()
        if status not in {"completed", "failed"}:
            raise ValueError("tau_bench_result_status_invalid")
        transport = result.get("public_api_transport") if isinstance(result.get("public_api_transport"), Mapping) else {}
        public_axio = candidate.get("candidate_kind") == "public_axio"
        candidate_call_count = _safe_int(result.get("candidate_call_count"))
        http_gateway_call_count = _safe_int(transport.get("http_gateway_call_count"))
        network_call_count = _safe_int(transport.get("network_call_count"))
        invocation = {
            "schema": "axio_fusion_api.benchmark_public_api_invocation.v1",
            "public_api_surface_used": public_axio and transport.get("public_api_surface_used") is True,
            "candidate_kind": str(candidate.get("candidate_kind") or ""),
            "api_format": str(api_format or ""),
            "status": "tau_bench_interaction_completed" if status == "completed" else "tau_bench_interaction_failed",
            "agent_turn_count": candidate_call_count,
            "tool_call_count": _safe_int(result.get("tool_action_count")),
            "tool_error_count": _safe_int(result.get("tool_error_count")),
            "transport": "http_gateway" if public_axio and transport.get("transport") == "http_gateway" and http_gateway_call_count == candidate_call_count and candidate_call_count else "",
            "network_calls_performed": public_axio and transport.get("network_calls_performed") is True and network_call_count == candidate_call_count and candidate_call_count > 0,
            "http_gateway_call_count": http_gateway_call_count,
            "network_call_count": network_call_count,
            "all_agent_turns_use_http_gateway": public_axio and candidate_call_count > 0 and http_gateway_call_count == candidate_call_count,
            "all_agent_turns_record_network_calls": public_axio and candidate_call_count > 0 and network_call_count == candidate_call_count,
            "api_format_matches_candidate": transport.get("api_format_matches_candidate") is True,
            "unsafe_transport_receipt_count": _safe_int(transport.get("unsafe_transport_receipt_count")),
            "raw_gateway_url_persisted": False,
            "raw_tool_names_persisted": False,
            "raw_tool_arguments_persisted": False,
            "raw_message_content_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        }
        metadata_rows.append(
            {
                "case_index": index,
                "case_id": str(case["case_id"]),
                "status": status,
                "error_type": str(result.get("error_type") or "")[:120],
                "latency_ms": round(max(0.0, _safe_float(result.get("latency_ms"))), 3),
                "output_sha256": output_hash,
                **_safe_cost_fields(result),
                "public_api_invocation": invocation,
                "raw_prompt_persisted": False,
                "raw_model_output_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }
        )
        sample_rows.append(
            {
                "source_identifier": identifier,
                "trajectory_sha256": trajectory_hash,
                "output_sha256": output_hash,
            }
        )
    if len(seen) != len(source_by_identifier):
        raise ValueError("tau_bench_result_case_set_incomplete")
    return metadata_rows, sample_rows


def _normalize_tau_bench_results(
    *,
    source_cases: Sequence[Mapping[str, Any]],
    result_path: Path,
    generation: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_by_identifier = {
        str(case.get("source_identifier") or ""): dict(case)
        for case in source_cases
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, result in enumerate(_iter_private_jsonl(result_path)):
        identifier = str(result.get("source_identifier") or "")
        case = source_by_identifier.get(identifier)
        if case is None or identifier in seen:
            raise ValueError("tau_bench_result_case_not_in_source")
        seen.add(identifier)
        case_id = str(case["case_id"])
        metadata = generation.get(case_id, {})
        output_hash = str(result.get("output_sha256") or "").strip().lower()
        prediction_hash = str(result.get("prediction_sha256") or "").strip().lower()
        trajectory_hash = str(result.get("trajectory_sha256") or "").strip().lower()
        if not all(_looks_like_sha256(value) for value in (output_hash, prediction_hash, trajectory_hash)):
            raise ValueError("tau_bench_result_output_hash_invalid")
        if output_hash != prediction_hash or output_hash != trajectory_hash:
            raise ValueError("tau_bench_result_output_hash_mismatch")
        if str(metadata.get("output_sha256") or "").strip().lower() != output_hash:
            raise ValueError("tau_bench_result_generation_output_hash_mismatch")
        passed = result.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("tau_bench_result_score_state_invalid")
        row = _safe_scored_row(
            case_id=case_id,
            index=index,
            passed=passed,
            metric="task_success_rate",
            metadata=metadata,
            prediction_text="",
            prediction_sha256=prediction_hash,
            output_sha256=output_hash,
        )
        row["tool_action_count"] = _safe_int(result.get("tool_action_count"))
        row["tool_error_count"] = _safe_int(result.get("tool_error_count"))
        row["candidate_call_count"] = _safe_int(result.get("candidate_call_count"))
        rows.append(row)
    if len(seen) != len(source_by_identifier):
        raise ValueError("tau_bench_result_case_set_incomplete")
    tool_action_count = sum(_safe_int(row.get("tool_action_count")) for row in rows)
    tool_error_count = sum(_safe_int(row.get("tool_error_count")) for row in rows)
    return rows, {
        "schema": "axio_fusion_api.official_harness_normalization.v1",
        "input_result_row_count": len(rows),
        "completed_row_count": sum(1 for row in rows if row.get("status") == "completed"),
        "case_set_digest_sha256": _case_set_digest("tau_bench", [str(row["case_id"]) for row in rows]),
        "tool_action_count": tool_action_count,
        "tool_error_count": tool_error_count,
        "tool_error_rate": round(tool_error_count / tool_action_count, 6) if tool_action_count else 0.0,
        "raw_result_content_persisted": False,
        "raw_prompts_persisted": False,
        "raw_model_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _tau_bench_failed_generation_receipt(
    *,
    preflight: Mapping[str, Any],
    error_type: str,
    latency_ms: float,
    command: Sequence[str],
    stdout: str = "",
    stderr: str = "",
    return_code: int | None = None,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.official_harness_generation.v1",
        "status": "failed",
        "suite_id": "tau_bench",
        "candidate_id": str(preflight.get("candidate_id") or ""),
        "candidate_kind": str(preflight.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "error_type": str(error_type)[:120],
        "worker_latency_ms": round(max(0.0, float(latency_ms)), 3),
        "worker_return_code": return_code,
        "worker_stdout_sha256": sha256_text(stdout),
        "worker_stderr_sha256": sha256_text(stderr),
        "worker_command_protocol_sha256": _tau_bench_command_protocol_digest(),
        "model_calls_performed": False,
        "official_harness_execution_performed": True,
        "preflight": _safe_preflight_reference(preflight),
        "raw_error_message_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _tau_bench_failed_evaluation_receipt(
    *,
    preflight: Mapping[str, Any],
    error_type: str,
) -> dict[str, Any]:
    return {
        "schema": _EVALUATION_RECEIPT_SCHEMA,
        "status": "failed",
        "suite_id": "tau_bench",
        "candidate_id": str(preflight.get("candidate_id") or ""),
        "candidate_kind": str(preflight.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "error_type": str(error_type)[:120],
        "evaluator_latency_ms": 0.0,
        "evaluator_return_code": 0,
        "evaluator_stdout_sha256": sha256_text(""),
        "evaluator_stderr_sha256": sha256_text(""),
        "evaluator_command_protocol_sha256": _tau_bench_command_protocol_digest(),
        "model_calls_performed": False,
        "official_harness_execution_performed": True,
        "preflight": _safe_preflight_reference(preflight),
        "raw_error_message_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _generation_protocol_receipt(
    *,
    suite_id: str,
    candidate: Mapping[str, Any],
    pin: Mapping[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    task_type = _official_generation_task_type(suite_id)
    payload = {
        "schema": "axio_fusion_api.official_harness_generation_protocol.v1",
        "suite_id": suite_id,
        "task_type": task_type,
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")),
        "api_format": str(candidate.get("api_format") or ""),
        "system_prompt_sha256": sha256_text(_official_generation_system_prompt(suite_id)),
        "temperature": 0.0,
        "top_p": None,
        "stop_sequence_count": 0,
        "max_output_tokens": int(max_output_tokens),
        "prompt_protocol_sha256": str(pin.get("prompt_protocol_sha256") or ""),
        "decoding_config_sha256": str(pin.get("decoding_config_sha256") or ""),
        "harness_pin_digest_sha256": str(pin.get("suite_pin_digest_sha256") or ""),
        "raw_prompt_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    payload["generation_protocol_digest_sha256"] = sha256_text(stable_json(payload))
    return payload


def _complete_official_harness_candidate(
    *,
    candidate: Mapping[str, Any],
    engine: FusionEngine,
    client: HTTPProviderClient | None,
    prompt: str,
    system: str,
    task_type: str,
    max_output_tokens: int,
    axio_gateway_url: str | None,
    tools: Sequence[Mapping[str, Any]] = (),
    messages: Sequence[Mapping[str, Any]] = (),
) -> Any:
    if candidate.get("candidate_kind") == "public_axio":
        return _complete_public_axio_benchmark_candidate(
            engine=engine,
            candidate_id=str(candidate["candidate_id"]),
            api_format=str(candidate["api_format"]),
            prompt=prompt,
            system=system,
            task_type=task_type,
            max_output_tokens=max_output_tokens,
            axio_gateway_url=axio_gateway_url,
            tools=tools,
            messages=messages,
        )
    profile = candidate.get("profile")
    if not isinstance(profile, ModelProfile):
        raise ValueError("official_harness_bridge_provider_profile_missing")
    request = _official_provider_request(
        prompt=prompt,
        system=system,
        task_type=task_type,
        max_output_tokens=max_output_tokens,
        tools=tools,
        messages=messages,
    )
    from .evaluation import BenchmarkCompletion

    active_client = ensure_strict_streaming_client(client)
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    if tools:
        turn = active_client.complete_turn(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=90.0,
        )
        output = turn.text
        tool_calls = turn.tool_calls
    else:
        output = active_client.complete(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=90.0,
        )
    return BenchmarkCompletion(
        text=output,
        tool_calls=tool_calls,
        cost=_estimate_benchmark_provider_call_cost(
            profile,
            prompt=request.prompt,
            system=request.system,
            output_text=output,
            expected_output_tokens=max_output_tokens,
        ),
        api_invocation=_provider_native_invocation_receipt(
            profile,
            tool_declaration_count=len(tools),
            tool_call_count=len(tool_calls),
        ),
    )


def _official_provider_request(
    *,
    prompt: str,
    system: str,
    task_type: str,
    max_output_tokens: int,
    tools: Sequence[Mapping[str, Any]],
    messages: Sequence[Mapping[str, Any]],
) -> Any:
    rows: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = message.get("content")
        if role in {"system", "user", "assistant"} and isinstance(content, str) and content:
            rows.append({"role": role, "content": content})
    if not rows:
        if system:
            rows.append({"role": "system", "content": system})
        rows.append({"role": "user", "content": prompt})
    elif system and not any(str(row.get("role") or "") == "system" for row in rows):
        rows.insert(0, {"role": "system", "content": system})
    return canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": rows,
            "task_type": task_type,
            "temperature": 0,
            "max_tokens": int(max_output_tokens),
            "tools": [dict(tool) for tool in tools if isinstance(tool, Mapping)],
        },
        api_format="chat/completions",
    )


def _provider_native_invocation_receipt(
    profile: ModelProfile,
    *,
    tool_declaration_count: int = 0,
    tool_call_count: int = 0,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.benchmark_public_api_invocation.v1",
        "public_api_surface_used": False,
        "candidate_kind": "provider_native",
        "api_format": str(profile.api_format),
        "provider_profile_sha256": sha256_text(profile.profile_id),
        "status": "provider_native_invoked",
        "tool_declaration_count": max(0, int(tool_declaration_count)),
        "tool_call_count": max(0, int(tool_call_count)),
        "raw_tool_names_persisted": False,
        "raw_tool_arguments_persisted": False,
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _private_generation_root_reasons(root: Path) -> list[str]:
    existing = [
        filename
        for filename in (
            *_GENERATION_PRIVATE_FILENAMES,
            *_TAU_BENCH_PRIVATE_FILENAMES,
            *_MT_BENCH_PRIVATE_FILENAMES,
            _GENERATION_BINDING_FILENAME,
        )
        if (root / filename).exists()
    ]
    return ["official_harness_private_run_dir_not_empty"] if existing else []


def _generation_binding_receipt(
    *,
    preflight: Mapping[str, Any],
    candidate: Mapping[str, Any],
    case_set_digest_sha256: str,
    metadata_rows: Sequence[Mapping[str, Any]],
    max_output_tokens: int,
    generation_protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    protocol = (
        generation_protocol
        if isinstance(generation_protocol, Mapping)
        else preflight.get("generation_protocol")
        if isinstance(preflight.get("generation_protocol"), Mapping)
        else {}
    )
    payload = {
        "schema": "axio_fusion_api.official_harness_generation_binding.v1",
        "suite_id": str(preflight.get("suite_id") or ""),
        "task_format": str(preflight.get("task_format") or ""),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")),
        "api_format": str(candidate.get("api_format") or ""),
        "profile_id_sha256": str(candidate.get("profile_id_sha256") or ""),
        "case_set_digest_sha256": case_set_digest_sha256,
        "case_count": len(metadata_rows),
        "metadata_digest_sha256": sha256_text(stable_json(list(metadata_rows))),
        "generation_protocol_digest_sha256": str(protocol.get("generation_protocol_digest_sha256") or ""),
        "max_output_tokens": int(max_output_tokens),
        "raw_candidate_id_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    payload["generation_binding_digest_sha256"] = sha256_text(stable_json(payload))
    return payload


def _load_generation_binding(
    path: Path,
    *,
    preflight: Mapping[str, Any],
    candidate: Mapping[str, Any],
    metadata_path: Path,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not path.is_file():
        reasons.append("official_harness_generation_binding_missing")
        return {"ready": False, "reason_codes": reasons, "generation_binding_digest_sha256": ""}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ready": False,
            "reason_codes": ["official_harness_generation_binding_unreadable"],
            "generation_binding_digest_sha256": "",
        }
    if not isinstance(payload, Mapping):
        return {
            "ready": False,
            "reason_codes": ["official_harness_generation_binding_invalid"],
            "generation_binding_digest_sha256": "",
        }
    body = dict(payload)
    declared = str(body.pop("generation_binding_digest_sha256", "") or "")
    computed = sha256_text(stable_json(body))
    if str(payload.get("schema") or "") != "axio_fusion_api.official_harness_generation_binding.v1":
        reasons.append("official_harness_generation_binding_schema_invalid")
    if not _looks_like_sha256(declared) or declared != computed:
        reasons.append("official_harness_generation_binding_digest_invalid")
    expected_candidate_hash = sha256_text(str(candidate.get("candidate_id") or ""))
    if str(payload.get("candidate_id_sha256") or "") != expected_candidate_hash:
        reasons.append("official_harness_generation_binding_candidate_mismatch")
    if str(payload.get("candidate_kind") or "") != str(candidate.get("candidate_kind") or ""):
        reasons.append("official_harness_generation_binding_candidate_kind_mismatch")
    if str(payload.get("api_format") or "") != str(candidate.get("api_format") or ""):
        reasons.append("official_harness_generation_binding_api_format_mismatch")
    if str(payload.get("profile_id_sha256") or "") != str(candidate.get("profile_id_sha256") or ""):
        reasons.append("official_harness_generation_binding_profile_mismatch")
    if str(payload.get("suite_id") or "") != str(preflight.get("suite_id") or ""):
        reasons.append("official_harness_generation_binding_suite_mismatch")
    if str(payload.get("case_set_digest_sha256") or "") != str(preflight.get("case_set_digest_sha256") or ""):
        reasons.append("official_harness_generation_binding_case_set_mismatch")
    protocol = preflight.get("generation_protocol") if isinstance(preflight.get("generation_protocol"), Mapping) else {}
    if str(payload.get("generation_protocol_digest_sha256") or "") != str(protocol.get("generation_protocol_digest_sha256") or ""):
        reasons.append("official_harness_generation_binding_protocol_mismatch")
    if int(payload.get("max_output_tokens") or 0) != int(preflight.get("max_output_tokens") or 0):
        reasons.append("official_harness_generation_binding_max_output_tokens_mismatch")
    try:
        metadata = list(_iter_private_jsonl(metadata_path))
        metadata_digest = sha256_text(stable_json(metadata))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        metadata_digest = ""
        reasons.append("official_harness_generation_binding_metadata_unreadable")
    if str(payload.get("metadata_digest_sha256") or "") != metadata_digest:
        reasons.append("official_harness_generation_binding_metadata_mismatch")
    if _safe_int(payload.get("case_count")) != _safe_int(preflight.get("case_count")):
        reasons.append("official_harness_generation_binding_case_count_mismatch")
    if _contains_true_flag(payload):
        reasons.append("official_harness_generation_binding_raw_content_flagged")
    return {
        "ready": not reasons,
        "reason_codes": sorted(set(reasons)),
        "generation_binding_digest_sha256": declared if _looks_like_sha256(declared) else "",
    }


def _contains_true_flag(payload: Mapping[str, Any]) -> bool:
    for key, value in payload.items():
        if isinstance(value, Mapping) and _contains_true_flag(value):
            return True
        if isinstance(value, list) and any(isinstance(item, Mapping) and _contains_true_flag(item) for item in value):
            return True
        if value is True and ("raw_" in str(key) or "secrets_persisted" == str(key)):
            return True
    return False


def _private_sample_row(
    suite_id: str,
    case: Mapping[str, Any],
    output: str,
    *,
    tool_calls: Sequence[Mapping[str, Any]] = (),
    raw_output_text: str = "",
) -> dict[str, Any]:
    if suite_id == "bfcl":
        return {
            "category": str(case["category"]),
            "id": str(case["source_identifier"]),
            "text": str(raw_output_text),
            "tool_calls": _bfcl_private_tool_call_rows(tool_calls),
        }
    if suite_id == "livecodebench":
        return {
            "question_id": str(case["source_identifier"]),
            "code_list": [output],
        }
    if suite_id == "humaneval":
        return {"task_id": str(case["source_identifier"]), "completion": output}
    return {"prompt": str(case["prompt"]), "response": output}


def _official_generation_system_prompt(suite_id: str) -> str:
    if suite_id == "bfcl":
        # A whitespace system field prevents the public gateway's default
        # assistant preamble from changing BFCL's native-tool-call protocol.
        return " "
    if suite_id == "livecodebench":
        return (
            "You are an expert Python programmer. You will be given a question "
            "(problem specification) and will generate a correct Python program "
            "that matches the specification and passes all tests."
        )
    if suite_id == "humaneval":
        return (
            "Complete the supplied Python function. Return only the continuation "
            "that follows the prompt, without Markdown fences, explanations, tests, "
            "or a repeated function signature."
        )
    return "Follow the user's instructions exactly. Return only the requested answer without commentary about the evaluation."


def _official_sample_output(
    suite_id: str,
    output: str,
    *,
    tool_calls: Sequence[Mapping[str, Any]] = (),
) -> str:
    raw = str(output or "")
    if suite_id == "bfcl":
        return stable_json(
            {
                "text": raw,
                "tool_calls": _bfcl_private_tool_call_rows(tool_calls),
            }
        )
    if suite_id == "livecodebench":
        lines = raw.split("\n")
        indices = [index for index, line in enumerate(lines) if "```" in line]
        if len(indices) < 2:
            return ""
        return "\n".join(lines[indices[-2] + 1 : indices[-1]])
    text = raw.strip()
    if suite_id != "humaneval" or "```" not in text:
        return text
    fenced = text.split("```")
    if len(fenced) < 3:
        return text
    code = fenced[1].strip()
    if code.lower().startswith("python"):
        code = code[6:].lstrip("\r\n")
    return code


def _default_max_output_tokens(suite_id: str) -> int:
    if suite_id == "livecodebench":
        return 2048
    return 1024 if suite_id == "humaneval" else 512


def _official_generation_task_type(suite_id: str) -> str:
    if suite_id in _CODE_EXECUTION_SUITES:
        return "code"
    if suite_id in {"bfcl", "tau_bench"}:
        return "agentic_tool_calling"
    return "daily_work"


def _bfcl_private_tool_call_rows(
    calls: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        name = str(call.get("name") or "").strip()
        arguments = call.get("arguments")
        if not name or not isinstance(arguments, Mapping):
            continue
        rows.append(
            {
                "id": str(call.get("id") or ""),
                "type": str(call.get("type") or "function"),
                "name": name,
                "arguments": dict(arguments),
            }
        )
    return rows


def _safe_cost_fields(cost: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "input_tokens": _safe_int(cost.get("input_tokens")),
        "output_tokens": _safe_int(cost.get("output_tokens")),
        "estimated_cost_usd": round(max(0.0, _safe_float(cost.get("estimated_cost_usd"))), 8),
        "pricing_known": cost.get("pricing_known") is True,
        "provider_call_count": _safe_int(cost.get("provider_call_count")),
    }


def _not_invoked_public_api_receipt(api_format: str) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.benchmark_public_api_invocation.v1",
        "public_api_surface_used": False,
        "api_format": api_format,
        "status": "not_invoked",
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _ensure_private_run_dir(path: str | Path) -> Path:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    _try_private_permissions(root)
    return root


def _try_private_permissions(path: Path) -> None:
    try:
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    except OSError:
        pass


def _write_private_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    _try_private_permissions(path)


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _try_private_permissions(path)


def _bridge_blocked_receipt(
    *,
    schema: str,
    preflight: Mapping[str, Any],
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": schema,
        "status": "blocked",
        "suite_id": str(preflight.get("suite_id") or ""),
        "candidate_id": str(preflight.get("candidate_id") or ""),
        "candidate_kind": str(preflight.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "reason_codes": sorted(set(str(reason) for reason in reason_codes if reason)),
        "model_calls_performed": False,
        "official_harness_execution_performed": False,
        "preflight": _safe_preflight_reference(preflight),
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _safe_preflight_reference(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(preflight.get("schema") or ""),
        "status": str(preflight.get("status") or ""),
        "suite_id": str(preflight.get("suite_id") or ""),
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "harness_root_sha256": str(preflight.get("harness_root_sha256") or ""),
        "dataset_path_sha256": str(preflight.get("dataset_path_sha256") or ""),
        "harness_pin_binding": dict(preflight.get("harness_pin_binding") or {}),
        "candidate_binding": dict(preflight.get("candidate_binding") or {}),
        "provider_baseline_freeze_binding": dict(preflight.get("provider_baseline_freeze_binding") or {}),
        "generation_protocol": dict(preflight.get("generation_protocol") or {}),
        "mt_bench_comparison_generation_protocol": dict(
            preflight.get("mt_bench_comparison_generation_protocol") or {}
        ),
        "mt_bench_comparison": dict(preflight.get("mt_bench_comparison") or {}),
        "mt_bench_judge": dict(preflight.get("mt_bench_judge") or {}),
        "mt_bench_execution": dict(preflight.get("mt_bench_execution") or {}),
        "raw_paths_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _official_evaluator_command(
    *,
    suite_id: str,
    dataset_path: Path,
    harness_root: Path,
    samples_path: Path,
    evaluator_output: Path,
    python_executable: str,
    worker_count: int,
    timeout_seconds: float,
    limit: int | None,
) -> list[str]:
    if suite_id == "livecodebench":
        runner = Path(__file__).with_name("livecodebench_bridge_runner.py")
        command = [
            python_executable,
            str(runner),
            "--dataset",
            str(dataset_path),
            "--harness-root",
            str(harness_root),
            "--samples",
            str(samples_path),
            "--output",
            str(evaluator_output / _LIVECODEBENCH_RESULT_FILENAME),
            "--worker-count",
            str(max(1, int(worker_count))),
            "--timeout-seconds",
            str(max(0.1, float(timeout_seconds))),
            "--unsafe-authorized",
        ]
        return command
    if suite_id == "bfcl":
        runner = Path(__file__).with_name("bfcl_bridge_runner.py")
        command = [
            python_executable,
            str(runner),
            "--dataset",
            str(dataset_path),
            "--harness-root",
            str(harness_root),
            "--samples",
            str(samples_path),
            "--output",
            str(evaluator_output / _BFCL_RESULT_FILENAME),
        ]
        if limit is not None:
            command.extend(["--limit", str(max(0, int(limit)))])
        return command
    if suite_id == "humaneval":
        runner = (
            "from human_eval.evaluation import evaluate_functional_correctness; "
            "import json, sys; "
            "print(json.dumps(evaluate_functional_correctness("
            "sys.argv[1], k=[1], n_workers=int(sys.argv[2]), "
            "timeout=float(sys.argv[3]), problem_file=sys.argv[4]), sort_keys=True))"
        )
        return [
            python_executable,
            "-c",
            runner,
            str(samples_path),
            str(max(1, int(worker_count))),
            str(max(0.1, float(timeout_seconds))),
            str(dataset_path),
        ]
    return [
        python_executable,
        str(harness_root / "instruction_following_eval" / "evaluation_main.py"),
        "--input_data",
        str(dataset_path),
        "--input_response_data",
        str(samples_path),
        "--output_dir",
        str(evaluator_output),
    ]


def _official_evaluator_environment(harness_root: str | Path) -> dict[str, str]:
    environment = dict(os.environ)
    current = str(environment.get("PYTHONPATH") or "")
    environment["PYTHONPATH"] = str(harness_root) if not current else f"{harness_root}{os.pathsep}{current}"
    return environment


def _evaluator_process_timeout(suite_id: str, timeout_seconds: float, case_count: Any) -> float:
    count = max(1, _safe_int(case_count))
    if suite_id in _CODE_EXECUTION_SUITES:
        return max(60.0, count * max(0.1, float(timeout_seconds)) * 2.0 + 60.0)
    return max(60.0, count * 0.5 + 60.0)


def _official_evaluator_result_path(*, suite_id: str, samples_path: Path, evaluator_output: Path) -> Path:
    if suite_id == "livecodebench":
        return evaluator_output / _LIVECODEBENCH_RESULT_FILENAME
    if suite_id == "bfcl":
        return evaluator_output / _BFCL_RESULT_FILENAME
    if suite_id == "humaneval":
        return Path(str(samples_path) + "_results.jsonl")
    return evaluator_output / "eval_results_strict.jsonl"


def _official_evaluator_command_protocol_digest(suite_id: str, command: Sequence[str]) -> str:
    # Paths and generated code are intentionally excluded from the persistent digest.
    return sha256_text(
        stable_json(
            {
                "suite_id": suite_id,
                "command_kind": (
                    "livecodebench_codegen_metrics"
                    if suite_id == "livecodebench"
                    else "bfcl_v3_native_tool_call_ast"
                    if suite_id == "bfcl"
                    else "human_eval_evaluate_functional_correctness"
                    if suite_id == "humaneval"
                    else "ifeval_evaluation_main"
                ),
                "argument_count": len(command),
            }
        )
    )


def _bridge_failed_evaluation_receipt(
    *,
    preflight: Mapping[str, Any],
    error_type: str,
    latency_ms: float,
    command: Sequence[str],
    stdout: str = "",
    stderr: str = "",
    return_code: int | None = None,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.official_harness_evaluation.v1",
        "status": "failed",
        "suite_id": str(preflight.get("suite_id") or ""),
        "candidate_id": str(preflight.get("candidate_id") or ""),
        "candidate_kind": str(preflight.get("candidate_kind") or ""),
        "api_format": str(preflight.get("api_format") or ""),
        "case_count": _safe_int(preflight.get("case_count")),
        "case_set_digest_sha256": str(preflight.get("case_set_digest_sha256") or ""),
        "error_type": str(error_type)[:120],
        "evaluator_latency_ms": round(max(0.0, float(latency_ms)), 3),
        "evaluator_return_code": return_code,
        "evaluator_stdout_sha256": sha256_text(stdout),
        "evaluator_stderr_sha256": sha256_text(stderr),
        "evaluator_command_protocol_sha256": _official_evaluator_command_protocol_digest(
            str(preflight.get("suite_id") or ""), command
        ),
        "model_calls_performed": False,
        "official_harness_execution_performed": True,
        "preflight": _safe_preflight_reference(preflight),
        "raw_provider_identifiers_persisted": False,
        "raw_error_message_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _safe_generation_metadata(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _iter_private_jsonl(path):
        case_id = str(row.get("case_id") or "")
        if not _looks_like_sha256(case_id):
            raise ValueError("generation_metadata_case_id_invalid")
        rows[case_id] = {
            "status": str(row.get("status") or ""),
            "error_type": str(row.get("error_type") or "")[:120],
            "latency_ms": round(max(0.0, _safe_float(row.get("latency_ms"))), 3),
            "output_sha256": str(row.get("output_sha256") or ""),
            **_safe_cost_fields(row),
            "public_api_invocation": _safe_public_api_invocation(row.get("public_api_invocation")),
        }
    return rows


def _normalize_official_harness_results(
    *,
    suite_id: str,
    dataset_path: Path,
    result_path: Path,
    generation: Mapping[str, Mapping[str, Any]],
    limit: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if suite_id == "livecodebench":
        rows = _normalize_livecodebench_results(
            dataset_path,
            result_path,
            generation,
            limit=limit,
        )
    elif suite_id == "bfcl":
        rows = _normalize_bfcl_results(
            dataset_path,
            result_path,
            generation,
            limit=limit,
        )
    elif suite_id == "humaneval":
        rows = _normalize_humaneval_results(result_path, generation)
    else:
        rows = _normalize_ifeval_results(dataset_path, result_path, generation, limit=limit)
    completed = [row for row in rows if row.get("status") == "completed"]
    return rows, {
        "schema": "axio_fusion_api.official_harness_normalization.v1",
        "input_result_row_count": len(rows),
        "completed_row_count": len(completed),
        "case_set_digest_sha256": _case_set_digest(suite_id, [str(row["case_id"]) for row in rows]),
        "raw_result_content_persisted": False,
        "raw_prompts_persisted": False,
        "raw_model_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _official_result_case_alignment(
    preflight: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_count = _safe_int(preflight.get("case_count"))
    expected_digest = str(preflight.get("case_set_digest_sha256") or "")
    observed_ids = [str(row.get("case_id") or "") for row in rows]
    observed_digest = _case_set_digest(str(preflight.get("suite_id") or ""), observed_ids)
    reasons: list[str] = []
    if len(rows) != expected_count:
        reasons.append("official_harness_result_case_count_mismatch")
    if len(set(observed_ids)) != len(observed_ids):
        reasons.append("official_harness_result_case_identifiers_not_unique")
    if expected_digest != observed_digest:
        reasons.append("official_harness_result_case_set_mismatch")
    return {
        "schema": "axio_fusion_api.official_harness_result_case_alignment.v1",
        "ready": not reasons,
        "expected_case_count": expected_count,
        "observed_case_count": len(rows),
        "expected_case_set_digest_sha256": expected_digest,
        "observed_case_set_digest_sha256": observed_digest,
        "reason_codes": sorted(set(reasons)),
        "raw_case_hashes_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _official_import_binding(
    *,
    preflight: Mapping[str, Any],
    candidate: Mapping[str, Any],
    scored_path: Path,
    result_case_alignment: Mapping[str, Any],
) -> dict[str, Any]:
    pin = preflight.get("harness_pin_binding") if isinstance(preflight.get("harness_pin_binding"), Mapping) else {}
    protocol = preflight.get("generation_protocol") if isinstance(preflight.get("generation_protocol"), Mapping) else {}
    return {
        "schema": "axio_fusion_api.official_harness_import_binding.v1",
        "candidate_id_sha256": sha256_text(str(candidate.get("candidate_id") or "")),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "api_format": str(candidate.get("api_format") or ""),
        "source_path_sha256": sha256_text(str(scored_path)),
        "case_set_digest_sha256": str(result_case_alignment.get("observed_case_set_digest_sha256") or ""),
        "case_set_matches_preflight": result_case_alignment.get("ready") is True,
        "harness_name_sha256": str(pin.get("harness_name_sha256") or ""),
        "harness_version_sha256": str(pin.get("harness_version_sha256") or ""),
        "dataset_snapshot_sha256": str(pin.get("dataset_snapshot_sha256") or ""),
        "evaluator_config_sha256": str(pin.get("evaluator_config_sha256") or ""),
        "prompt_protocol_sha256": str(protocol.get("prompt_protocol_sha256") or ""),
        "decoding_config_sha256": str(protocol.get("decoding_config_sha256") or ""),
        "position_balanced": str(preflight.get("suite_id") or "") == "mt_bench_work",
        "raw_source_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _normalize_humaneval_results(
    result_path: Path,
    generation: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, result in enumerate(_iter_private_jsonl(result_path)):
        task_id = result.get("task_id")
        if task_id in (None, ""):
            raise ValueError("humaneval_result_task_id_missing")
        case_id = _official_case_id("humaneval", task_id)
        if case_id in seen:
            raise ValueError("humaneval_result_case_duplicate")
        seen.add(case_id)
        metadata = generation.get(case_id, {})
        passed = bool(result.get("passed"))
        rows.append(
            _safe_scored_row(
                case_id=case_id,
                index=index,
                passed=passed,
                metric="pass_at_1",
                metadata=metadata,
                prediction_text=str(result.get("completion") or ""),
            )
        )
    return rows


def _normalize_livecodebench_results(
    dataset_path: Path,
    result_path: Path,
    generation: Mapping[str, Mapping[str, Any]],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    cases, _, invalid_row_count = _load_livecodebench_source_cases(
        dataset_path,
        limit=limit,
    )
    if invalid_row_count:
        raise ValueError("livecodebench_source_rows_invalid")
    source_to_case_id = {
        str(case["source_identifier"]): str(case["case_id"])
        for case in cases
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, result in enumerate(_iter_private_jsonl(result_path)):
        identifier = str(result.get("question_id") or "").strip()
        if identifier not in source_to_case_id:
            raise ValueError("livecodebench_result_question_id_not_in_source")
        case_id = source_to_case_id[identifier]
        if case_id in seen:
            raise ValueError("livecodebench_result_case_duplicate")
        seen.add(case_id)

        prediction_hash = str(result.get("prediction_sha256") or "").strip().lower()
        output_hash = str(result.get("output_sha256") or "").strip().lower()
        if not _looks_like_sha256(prediction_hash) or not _looks_like_sha256(output_hash):
            raise ValueError("livecodebench_result_output_hash_invalid")
        if prediction_hash != output_hash:
            raise ValueError("livecodebench_result_prediction_output_hash_mismatch")

        metadata = generation.get(case_id, {})
        expected_hash = str(metadata.get("output_sha256") or "").strip().lower()
        if expected_hash != prediction_hash:
            raise ValueError("livecodebench_result_output_hash_mismatch")
        passed = result.get("passed")
        compile_passed = result.get("compile_passed")
        if not isinstance(passed, bool) or not isinstance(compile_passed, bool):
            raise ValueError("livecodebench_result_score_state_invalid")
        rows.append(
            _safe_scored_row(
                case_id=case_id,
                index=index,
                passed=passed,
                metric="pass_at_1",
                metadata=metadata,
                prediction_text="",
                prediction_sha256=prediction_hash,
                output_sha256=output_hash,
                compile_passed=compile_passed,
            )
        )
    return rows


def _normalize_bfcl_results(
    dataset_path: Path,
    result_path: Path,
    generation: Mapping[str, Mapping[str, Any]],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    cases, _, invalid_row_count = _load_bfcl_source_cases(dataset_path, limit=limit)
    if invalid_row_count:
        raise ValueError("bfcl_source_rows_invalid")
    source_to_case_id = {
        (str(case["category"]), str(case["source_identifier"])): str(case["case_id"])
        for case in cases
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, result in enumerate(_iter_private_jsonl(result_path)):
        category = str(result.get("category") or "").strip()
        identifier = str(result.get("id") or "").strip()
        key = (category, identifier)
        if key not in source_to_case_id:
            raise ValueError("bfcl_result_case_not_in_source")
        case_id = source_to_case_id[key]
        if case_id in seen:
            raise ValueError("bfcl_result_case_duplicate")
        seen.add(case_id)
        prediction_hash = str(result.get("prediction_sha256") or "").strip().lower()
        output_hash = str(result.get("output_sha256") or "").strip().lower()
        if not _looks_like_sha256(prediction_hash) or not _looks_like_sha256(output_hash):
            raise ValueError("bfcl_result_output_hash_invalid")
        if prediction_hash != output_hash:
            raise ValueError("bfcl_result_prediction_output_hash_mismatch")
        metadata = generation.get(case_id, {})
        expected_hash = str(metadata.get("output_sha256") or "").strip().lower()
        if expected_hash != prediction_hash:
            raise ValueError("bfcl_result_output_hash_mismatch")
        passed = result.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("bfcl_result_score_state_invalid")
        rows.append(
            _safe_scored_row(
                case_id=case_id,
                index=index,
                passed=passed,
                metric="ast_match",
                metadata=metadata,
                prediction_text="",
                prediction_sha256=prediction_hash,
                output_sha256=output_hash,
            )
        )
    return rows


def _normalize_ifeval_results(
    dataset_path: Path,
    result_path: Path,
    generation: Mapping[str, Mapping[str, Any]],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    prompt_to_identifier: dict[str, Any] = {}
    for source in _iter_private_jsonl(dataset_path):
        prompt = str(source.get("prompt") or "")
        identifier = source.get("key")
        if not prompt or identifier in (None, "") or prompt in prompt_to_identifier:
            raise ValueError("ifeval_source_prompt_mapping_invalid")
        prompt_to_identifier[prompt] = identifier
        if limit is not None and len(prompt_to_identifier) >= int(limit):
            break
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, result in enumerate(_iter_private_jsonl(result_path)):
        prompt = str(result.get("prompt") or "")
        if prompt not in prompt_to_identifier:
            raise ValueError("ifeval_result_prompt_not_in_source")
        case_id = _official_case_id("ifeval", prompt_to_identifier[prompt])
        if case_id in seen:
            raise ValueError("ifeval_result_case_duplicate")
        seen.add(case_id)
        checks = result.get("follow_instruction_list")
        if not isinstance(checks, list) or not checks:
            raise ValueError("ifeval_result_instruction_checks_missing")
        instruction_score = sum(1 for item in checks if item is True) / len(checks)
        metadata = generation.get(case_id, {})
        row = _safe_scored_row(
            case_id=case_id,
            index=index,
            passed=bool(result.get("follow_all_instructions")),
            metric="prompt_level_strict_accuracy",
            metadata=metadata,
            prediction_text=str(result.get("response") or ""),
        )
        row["instruction_level_score"] = round(instruction_score, 6)
        row["instruction_count"] = len(checks)
        rows.append(row)
    return rows


def _safe_scored_row(
    *,
    case_id: str,
    index: int,
    passed: bool,
    metric: str,
    metadata: Mapping[str, Any],
    prediction_text: str,
    prediction_sha256: str | None = None,
    output_sha256: str | None = None,
    compile_passed: bool | None = None,
) -> dict[str, Any]:
    row = {
        "case_index": int(index),
        "case_id": case_id,
        "status": "completed" if metadata.get("status") == "completed" else "generation_failed",
        "passed": bool(passed),
        "correct": bool(passed),
        "score": 1.0 if passed else 0.0,
        "metric": metric,
        "latency_ms": round(max(0.0, _safe_float(metadata.get("latency_ms"))), 3),
        "prediction_sha256": str(prediction_sha256 or sha256_text(prediction_text)),
        "output_sha256": str(output_sha256 or sha256_text(prediction_text)),
        **_safe_cost_fields(metadata),
        "error_type": str(metadata.get("error_type") or "")[:120],
        "public_api_invocation": _safe_public_api_invocation(metadata.get("public_api_invocation")),
        "raw_input_persisted": False,
        "raw_reference_persisted": False,
        "raw_label_persisted": False,
        "raw_model_output_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    if compile_passed is not None:
        row["compile_passed"] = bool(compile_passed)
    return row


def _safe_public_api_invocation(value: Any) -> dict[str, Any]:
    """Project a transport receipt without copying URL, prompt, or output data."""

    source = value if isinstance(value, Mapping) else {}
    safe = {
        "schema": str(source.get("schema") or ""),
        "public_api_surface_used": source.get("public_api_surface_used") is True,
        "candidate_kind": str(source.get("candidate_kind") or ""),
        "api_format": str(source.get("api_format") or ""),
        "transport": str(source.get("transport") or ""),
        "network_calls_performed": source.get("network_calls_performed") is True,
        "status_code": _safe_int(source.get("status_code")),
        "response_shape_valid": source.get("response_shape_valid") is True,
        "response_model_matches_request": source.get("response_model_matches_request") is True,
        "dialogue_turn_count": _safe_int(source.get("dialogue_turn_count")),
        "agent_turn_count": _safe_int(source.get("agent_turn_count")),
        "http_gateway_call_count": _safe_int(source.get("http_gateway_call_count")),
        "network_call_count": _safe_int(source.get("network_call_count")),
        "raw_gateway_url_persisted": False,
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    if source.get("gateway_url_sha256"):
        safe["gateway_url_sha256"] = str(source.get("gateway_url_sha256") or "")
    return safe


def _official_task_format(suite_id: str) -> str:
    if suite_id in _CODE_EXECUTION_SUITES:
        return "python_code"
    if suite_id in {"bfcl", "tau_bench"}:
        return "tool_call_ast"
    if suite_id == "mt_bench_work":
        return "external_pairwise_judge"
    return "instruction_checks"


def _official_primary_metric(suite_id: str) -> str:
    if suite_id in _CODE_EXECUTION_SUITES:
        return "pass_at_1"
    if suite_id == "bfcl":
        return "ast_match"
    if suite_id == "tau_bench":
        return "task_success_rate"
    if suite_id == "mt_bench_work":
        return "win_rate"
    return "prompt_level_strict_accuracy"


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _looks_like_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)
