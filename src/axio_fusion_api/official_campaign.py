from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from .official_harness import (
    build_official_harness_bridge_preflight,
    evaluate_official_harness_samples,
    generate_official_harness_samples,
    import_official_harness_evaluation,
    validate_provider_baseline_freeze_for_official_campaign,
)
from .providers import HTTPProviderClient, ensure_strict_streaming_client
from .registry import load_registry
from .schemas import ModelProfile, PUBLIC_MODELS, sha256_text, stable_json


_EXECUTION_PLAN_SCHEMA = "axio_fusion_api.official_harness_execution_plan.v1"
_CAMPAIGN_SCHEMA = "axio_fusion_api.official_harness_campaign.v1"
_PROVIDER_CANDIDATE_PREFIX = "provider::"


def run_official_harness_campaign(
    *,
    execution_plan_path: str | Path,
    suite_config_path: str | Path,
    registry_path: str | Path | None,
    provider_baseline_freeze_manifest_path: str | Path,
    harness_pin_manifest_path: str | Path,
    private_root: str | Path,
    safe_import_root: str | Path,
    state_path: str | Path | None = None,
    suite_ids: Sequence[str] = (),
    execution_task_ids: Sequence[str] = (),
    candidate_hashes: Sequence[str] = (),
    max_tasks: int | None = None,
    limit: int | None = None,
    live: bool = False,
    retry_failed: bool = False,
    overwrite: bool = False,
    allow_unsafe_code_execution: bool = False,
    client: HTTPProviderClient | None = None,
) -> dict[str, Any]:
    """Run or preflight a resumable hash-bound official-harness matrix.

    The suite config is private operator input and may contain local paths and
    simulator settings. Returned and persisted campaign state contains only
    hashes, counts, public suite identifiers, and bounded reason codes.
    """

    started = time.monotonic()
    plan_path = Path(execution_plan_path)
    config_path = Path(suite_config_path)
    registry_file = Path(registry_path) if registry_path else Path("__axio_missing_registry__")
    freeze_path = Path(provider_baseline_freeze_manifest_path)
    pin_path = Path(harness_pin_manifest_path)
    private_dir = Path(private_root)
    import_dir = Path(safe_import_root)
    selected_state_path = Path(state_path) if state_path else None
    load_reasons: list[str] = []
    plan = _load_json_object(plan_path, "official_campaign_execution_plan", load_reasons)
    suite_config = _load_json_object(config_path, "official_campaign_suite_config", load_reasons)
    freeze_load_reasons: list[str] = []
    freeze = _load_json_object(
        freeze_path,
        "official_campaign_provider_freeze",
        freeze_load_reasons,
    )
    profiles = _load_campaign_registry(registry_file, load_reasons)
    plan_digest = str(plan.get("execution_plan_digest_sha256") or "")
    if str(plan.get("schema") or "") != _EXECUTION_PLAN_SCHEMA:
        load_reasons.append("official_campaign_execution_plan_schema_invalid")
    if plan.get("all_tasks_ready_to_execute") is not True:
        load_reasons.append("official_campaign_execution_plan_not_ready")
    if not plan_digest or len(plan_digest) != 64:
        load_reasons.append("official_campaign_execution_plan_digest_invalid")
    if not isinstance(suite_config.get("suites"), (list, Mapping)):
        load_reasons.append("official_campaign_suite_config_suites_missing")
    if registry_path is None or not str(registry_path).strip():
        load_reasons.append("official_campaign_registry_path_missing")
    elif not registry_file.is_file():
        load_reasons.append("official_campaign_registry_file_missing")
    if not pin_path.is_file():
        load_reasons.append("official_campaign_harness_pin_manifest_missing")

    existing_state = _load_existing_state(selected_state_path)
    if existing_state and str(existing_state.get("execution_plan_digest_sha256") or "") != plan_digest:
        load_reasons.append("official_campaign_resume_execution_plan_mismatch")

    task_rows = [row for row in plan.get("tasks", []) if isinstance(row, Mapping)]
    selected_tasks = _select_campaign_tasks(
        task_rows,
        suite_ids=suite_ids,
        execution_task_ids=execution_task_ids,
        candidate_hashes=candidate_hashes,
        max_tasks=max_tasks,
    )
    if not selected_tasks:
        load_reasons.append("official_campaign_no_tasks_selected")
    provider_task_selected = any(
        str(task.get("candidate_type") or "") == "provider"
        for task in selected_tasks
    )
    provider_freeze_required = bool(live or provider_task_selected)
    provider_freeze_validation = (
        validate_provider_baseline_freeze_for_official_campaign(
            freeze,
            registry_file_sha256=_file_content_sha256(registry_file),
        )
    )
    provider_freeze_ready = provider_freeze_validation.get("ready") is True
    if provider_freeze_required:
        load_reasons.extend(freeze_load_reasons)
        if not provider_freeze_ready:
            load_reasons.append("official_campaign_provider_freeze_not_ready")
            load_reasons.extend(
                f"official_campaign_{reason}"
                for reason in provider_freeze_validation.get("reason_codes", [])
                if str(reason)
            )

    base_state = _campaign_base_state(
        plan_path=plan_path,
        config_path=config_path,
        registry_path=registry_file,
        freeze_path=freeze_path,
        pin_path=pin_path,
        private_root=private_dir,
        safe_import_root=import_dir,
        execution_plan_digest=plan_digest,
        source_task_count=len(task_rows),
        selected_task_count=len(selected_tasks),
        live=live,
        retry_failed=retry_failed,
        overwrite=overwrite,
        allow_unsafe_code_execution=allow_unsafe_code_execution,
        provider_baseline_freeze_required=provider_freeze_required,
        provider_baseline_freeze_ready=provider_freeze_ready,
        provider_baseline_freeze_validation=provider_freeze_validation,
    )
    if load_reasons:
        blocked = _finalize_campaign_state(
            base_state,
            task_receipts=[],
            status="blocked",
            reason_codes=load_reasons,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
        _persist_campaign_state(selected_state_path, blocked)
        return blocked

    _ensure_private_root(private_dir)
    import_dir.mkdir(parents=True, exist_ok=True)
    previous_by_id = {
        str(row.get("execution_task_id") or ""): row
        for row in existing_state.get("task_receipts", [])
        if isinstance(row, Mapping) and str(row.get("execution_task_id") or "")
    } if isinstance(existing_state, Mapping) else {}
    frozen_hashes = {
        str(value).strip().lower()
        for value in freeze.get("selected_provider_profile_hashes", [])
        if _looks_like_sha256(value)
    }
    task_receipts: list[dict[str, Any]] = []
    active_client = ensure_strict_streaming_client(client)

    for task in selected_tasks:
        task_id = str(task.get("execution_task_id") or "")
        previous = previous_by_id.get(task_id, {})
        if (
            previous
            and str(previous.get("status") or "") in {"failed", "blocked"}
            and not retry_failed
            and not overwrite
        ):
            task_receipts.append(_previous_failure_skip_receipt(task, previous))
            _persist_campaign_progress(selected_state_path, base_state, task_receipts, started)
            continue
        receipt = _run_campaign_task(
            task=task,
            suite_config=suite_config,
            profiles=profiles,
            frozen_hashes=frozen_hashes,
            registry_path=registry_file,
            freeze_path=freeze_path,
            pin_path=pin_path,
            private_root=private_dir,
            safe_import_root=import_dir,
            live=live,
            overwrite=overwrite,
            allow_unsafe_code_execution=allow_unsafe_code_execution,
            limit_override=limit,
            client=active_client,
        )
        task_receipts.append(receipt)
        _persist_campaign_progress(selected_state_path, base_state, task_receipts, started)

    final_status, final_reasons = _campaign_completion_status(task_receipts, live=live)
    result = _finalize_campaign_state(
        base_state,
        task_receipts=task_receipts,
        status=final_status,
        reason_codes=final_reasons,
        elapsed_ms=(time.monotonic() - started) * 1000,
    )
    _persist_campaign_state(selected_state_path, result)
    return result


def _run_campaign_task(
    *,
    task: Mapping[str, Any],
    suite_config: Mapping[str, Any],
    profiles: Sequence[ModelProfile],
    frozen_hashes: set[str],
    registry_path: Path,
    freeze_path: Path,
    pin_path: Path,
    private_root: Path,
    safe_import_root: Path,
    live: bool,
    overwrite: bool,
    allow_unsafe_code_execution: bool,
    limit_override: int | None,
    client: HTTPProviderClient,
) -> dict[str, Any]:
    started = time.monotonic()
    base = _campaign_task_base_receipt(task)
    reasons: list[str] = []
    candidate = _resolve_campaign_candidate(task, profiles)
    reasons.extend(candidate["reason_codes"])
    config = _resolved_suite_config(suite_config, str(task.get("suite_id") or ""))
    reasons.extend(config["reason_codes"])
    if task.get("ready_to_execute") is not True:
        reasons.append("official_campaign_task_not_ready_in_execution_plan")
    if reasons:
        return _campaign_task_terminal_receipt(
            base,
            status="blocked",
            reason_codes=reasons,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )

    suite_id = str(task.get("suite_id") or "")
    run_token = f"{str(task.get('execution_task_id') or 'task')}_{str(task.get('run_unit_id_hash') or '')[:12]}"
    private_run_dir = private_root / suite_id / run_token
    safe_output_path = safe_import_root / suite_id / f"{run_token}.safe.json"
    safe_output_path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and _valid_existing_import(safe_output_path, task):
        existing = json.loads(safe_output_path.read_text(encoding="utf-8"))
        return {
            **base,
            "status": "imported",
            "resume_action": "existing_import_reused",
            "safe_import_path_sha256": sha256_text(str(safe_output_path)),
            "safe_import_content_sha256": sha256_text(stable_json(existing)),
            "preflight_status": "reused",
            "generation_status": "reused",
            "evaluation_status": "reused",
            "import_status": "imported",
            "model_calls_performed": False,
            "official_harness_execution_performed": False,
            "reason_codes": [],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }

    task_limit = limit_override if limit_override is not None else _optional_int(config.get("limit"))
    auxiliary = _campaign_auxiliary_candidates(
        suite_id=suite_id,
        target=candidate,
        config=config,
        profiles=profiles,
        frozen_hashes=frozen_hashes,
    )
    reasons.extend(auxiliary["reason_codes"])
    common = {
        "suite_id": suite_id,
        "dataset_path": str(config["dataset_path"]),
        "harness_root": str(config["harness_root"]),
        "private_run_dir": private_run_dir,
        "candidate_id": candidate["candidate_id"],
        "api_format": str(task.get("api_format") or "chat/completions"),
        "registry_path": registry_path,
        "provider_baseline_freeze_manifest_path": freeze_path,
        "harness_pin_manifest_path": pin_path,
        "limit": task_limit,
        "max_output_tokens": _optional_int(config.get("max_output_tokens")),
        "axio_gateway_url": config.get("axio_gateway_url"),
        "tau_user_model": config.get("tau_user_model"),
        "tau_user_provider": config.get("tau_user_provider"),
        "tau_user_strategy": str(config.get("tau_user_strategy") or "llm"),
        "tau_environments": _string_list(config.get("tau_environments")),
        "tau_max_steps": _optional_int(config.get("tau_max_steps")) or 30,
        "tau_python_executable": config.get("tau_python_executable"),
        "mt_comparison_candidate_id": auxiliary.get("comparison_candidate_id"),
        "mt_judge_candidate_id": auxiliary.get("judge_candidate_id"),
        "mt_judge_registry_path": registry_path,
        "mt_judge_max_output_tokens": _optional_int(config.get("mt_judge_max_output_tokens")) or 2048,
    }
    if reasons:
        return _campaign_task_terminal_receipt(
            base,
            status="blocked",
            reason_codes=reasons,
            elapsed_ms=(time.monotonic() - started) * 1000,
            auxiliary=auxiliary,
        )

    preflight = build_official_harness_bridge_preflight(**common)
    if preflight.get("status") != "ready":
        return _campaign_task_stage_receipt(
            base,
            status="blocked",
            preflight=preflight,
            generation=None,
            evaluation=None,
            imported=None,
            auxiliary=auxiliary,
            safe_output_path=safe_output_path,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
    if not live:
        return _campaign_task_stage_receipt(
            base,
            status="preflight_ready",
            preflight=preflight,
            generation=None,
            evaluation=None,
            imported=None,
            auxiliary=auxiliary,
            safe_output_path=safe_output_path,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )

    generation = _existing_stage_receipt(
        private_run_dir / "generation_receipt.safe.json",
        expected_status="generated",
        task=task,
        case_set_digest=str(preflight.get("case_set_digest_sha256") or ""),
    ) if not overwrite else None
    if generation is None:
        generation = generate_official_harness_samples(
            **common,
            live=True,
            client=client,
        )
    if generation.get("status") != "generated":
        return _campaign_task_stage_receipt(
            base,
            status="failed" if generation.get("status") == "partial" else "blocked",
            preflight=preflight,
            generation=generation,
            evaluation=None,
            imported=None,
            auxiliary=auxiliary,
            safe_output_path=safe_output_path,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )

    evaluation = _existing_stage_receipt(
        private_run_dir / "official_evaluation_receipt.safe.json",
        expected_status="evaluated",
        task=task,
        case_set_digest=str(preflight.get("case_set_digest_sha256") or ""),
    ) if not overwrite else None
    if evaluation is None:
        evaluation = evaluate_official_harness_samples(
            **common,
            allow_unsafe_code_execution=allow_unsafe_code_execution,
            python_executable=config.get("python_executable"),
            worker_count=_optional_int(config.get("worker_count")) or 4,
            timeout_seconds=_optional_float(config.get("timeout_seconds")) or 3.0,
            live=True,
            client=client,
        )
    if evaluation.get("status") != "evaluated":
        return _campaign_task_stage_receipt(
            base,
            status="failed" if evaluation.get("status") == "partial" else "blocked",
            preflight=preflight,
            generation=generation,
            evaluation=evaluation,
            imported=None,
            auxiliary=auxiliary,
            safe_output_path=safe_output_path,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )

    imported = import_official_harness_evaluation(private_run_dir=private_run_dir, mt_side="target")
    if imported.get("status") == "blocked" or imported.get("mode") != "official_harness_import":
        return _campaign_task_stage_receipt(
            base,
            status="blocked",
            preflight=preflight,
            generation=generation,
            evaluation=evaluation,
            imported=imported,
            auxiliary=auxiliary,
            safe_output_path=safe_output_path,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
    _atomic_write_json(safe_output_path, imported)
    return _campaign_task_stage_receipt(
        base,
        status="imported",
        preflight=preflight,
        generation=generation,
        evaluation=evaluation,
        imported=imported,
        auxiliary=auxiliary,
        safe_output_path=safe_output_path,
        elapsed_ms=(time.monotonic() - started) * 1000,
    )


def _resolve_campaign_candidate(
    task: Mapping[str, Any],
    profiles: Sequence[ModelProfile],
) -> dict[str, Any]:
    candidate_hash = str(task.get("candidate_id_hash") or "").strip().lower()
    candidate_type = str(task.get("candidate_type") or "")
    if candidate_type == "axio":
        matches = [model for model in PUBLIC_MODELS if sha256_text(model) == candidate_hash]
        return {
            "candidate_id": matches[0] if len(matches) == 1 else "",
            "candidate_type": candidate_type,
            "profile": None,
            "profile_hash": "",
            "reason_codes": [] if len(matches) == 1 else ["official_campaign_axio_candidate_hash_unresolved"],
        }
    if candidate_type == "provider":
        profile_hash = str(task.get("provider_profile_hash") or "").strip().lower()
        matches = [profile for profile in profiles if sha256_text(profile.profile_id) == profile_hash]
        candidate_id = f"{_PROVIDER_CANDIDATE_PREFIX}{profile_hash}" if len(matches) == 1 else ""
        reasons = []
        if len(matches) != 1:
            reasons.append("official_campaign_provider_profile_hash_unresolved")
        elif sha256_text(candidate_id) != candidate_hash:
            reasons.append("official_campaign_provider_candidate_hash_mismatch")
        return {
            "candidate_id": candidate_id,
            "candidate_type": candidate_type,
            "profile": matches[0] if len(matches) == 1 else None,
            "profile_hash": profile_hash,
            "reason_codes": reasons,
        }
    return {
        "candidate_id": "",
        "candidate_type": candidate_type,
        "profile": None,
        "profile_hash": "",
        "reason_codes": ["official_campaign_candidate_type_not_supported"],
    }


def _campaign_auxiliary_candidates(
    *,
    suite_id: str,
    target: Mapping[str, Any],
    config: Mapping[str, Any],
    profiles: Sequence[ModelProfile],
    frozen_hashes: set[str],
) -> dict[str, Any]:
    if suite_id != "mt_bench_work":
        return {
            "applicable": False,
            "reason_codes": [],
            "raw_provider_identifiers_persisted": False,
            "secrets_persisted": False,
        }
    explicit_comparison = str(config.get("mt_comparison_candidate_id") or "").strip()
    explicit_judge = str(config.get("mt_judge_candidate_id") or "").strip()
    if explicit_comparison and explicit_judge:
        return {
            "applicable": True,
            "selection_policy": "explicit_private_config",
            "comparison_candidate_id": explicit_comparison,
            "judge_candidate_id": explicit_judge,
            "comparison_candidate_id_sha256": sha256_text(explicit_comparison),
            "judge_candidate_id_sha256": sha256_text(explicit_judge),
            "reason_codes": [],
            "raw_provider_identifiers_persisted": False,
            "secrets_persisted": False,
        }

    profile_by_hash = {sha256_text(profile.profile_id): profile for profile in profiles}
    ranked_hashes = _ranked_profile_hashes(profiles)
    comparison_pool = _configured_hash_pool(config.get("mt_comparison_profile_hashes"), ranked_hashes)
    judge_pool = _configured_hash_pool(config.get("mt_judge_profile_hashes"), ranked_hashes)
    target_hash = str(target.get("profile_hash") or "")
    target_profile = target.get("profile") if isinstance(target.get("profile"), ModelProfile) else None
    comparison_candidates = [
        profile_hash
        for profile_hash in comparison_pool
        if profile_hash in frozen_hashes and profile_hash in profile_by_hash and profile_hash != target_hash
    ]
    if target_profile is not None:
        comparison_candidates.sort(
            key=lambda profile_hash: (
                profile_by_hash[profile_hash].provider != target_profile.provider,
                comparison_pool.index(profile_hash),
            )
        )
    for comparison_hash in comparison_candidates:
        comparison_profile = profile_by_hash[comparison_hash]
        for judge_hash in judge_pool:
            judge_profile = profile_by_hash.get(judge_hash)
            if judge_profile is None or judge_hash in {target_hash, comparison_hash}:
                continue
            if judge_profile.provider == comparison_profile.provider:
                continue
            if target_profile is not None and judge_profile.provider == target_profile.provider:
                continue
            comparison_id = f"{_PROVIDER_CANDIDATE_PREFIX}{comparison_hash}"
            judge_id = f"{_PROVIDER_CANDIDATE_PREFIX}{judge_hash}"
            return {
                "applicable": True,
                "selection_policy": "deterministic_cross_provider_profile_pool",
                "comparison_candidate_id": comparison_id,
                "judge_candidate_id": judge_id,
                "comparison_profile_hash": comparison_hash,
                "judge_profile_hash": judge_hash,
                "comparison_candidate_id_sha256": sha256_text(comparison_id),
                "judge_candidate_id_sha256": sha256_text(judge_id),
                "reason_codes": [],
                "raw_provider_identifiers_persisted": False,
                "secrets_persisted": False,
            }
    return {
        "applicable": True,
        "selection_policy": "deterministic_cross_provider_profile_pool",
        "comparison_candidate_id": "",
        "judge_candidate_id": "",
        "comparison_candidate_id_sha256": "",
        "judge_candidate_id_sha256": "",
        "reason_codes": ["official_campaign_mt_bench_independent_auxiliary_candidates_unavailable"],
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _ranked_profile_hashes(profiles: Sequence[ModelProfile]) -> list[str]:
    ranked = sorted(
        profiles,
        key=lambda profile: (
            -(
                3.0 * profile.capability("critique")
                + 2.0 * profile.capability("logic")
                + profile.capability("science_knowledge")
                + profile.capability("math")
                + profile.capability("structured_output")
            ),
            -(float(profile.availability) if profile.availability is not None else 0.0),
            sha256_text(profile.profile_id),
        ),
    )
    return [sha256_text(profile.profile_id) for profile in ranked]


def _configured_hash_pool(value: Any, fallback: Sequence[str]) -> list[str]:
    configured = [item for item in _string_list(value) if _looks_like_sha256(item)]
    return list(dict.fromkeys(configured)) if configured else list(fallback)


def _resolved_suite_config(config: Mapping[str, Any], suite_id: str) -> dict[str, Any]:
    defaults = dict(config.get("defaults") or {}) if isinstance(config.get("defaults"), Mapping) else {}
    suites = config.get("suites")
    selected: Mapping[str, Any] = {}
    if isinstance(suites, Mapping):
        row = suites.get(suite_id)
        selected = row if isinstance(row, Mapping) else {}
    elif isinstance(suites, list):
        selected = next(
            (
                row
                for row in suites
                if isinstance(row, Mapping) and str(row.get("suite_id") or "") == suite_id
            ),
            {},
        )
    merged = {**defaults, **dict(selected)}
    reasons = []
    if not str(merged.get("dataset_path") or "").strip():
        reasons.append("official_campaign_suite_dataset_path_missing")
    if not str(merged.get("harness_root") or "").strip():
        reasons.append("official_campaign_suite_harness_root_missing")
    return {**merged, "reason_codes": reasons}


def _existing_stage_receipt(
    path: Path,
    *,
    expected_status: str,
    task: Mapping[str, Any],
    case_set_digest: str,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if str(payload.get("status") or "") != expected_status:
        return None
    if str(payload.get("suite_id") or "") != str(task.get("suite_id") or ""):
        return None
    if sha256_text(str(payload.get("candidate_id") or "")) != str(task.get("candidate_id_hash") or ""):
        return None
    if str(payload.get("case_set_digest_sha256") or "") != case_set_digest:
        return None
    return dict(payload)


def _valid_existing_import(path: Path, task: Mapping[str, Any]) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(payload, Mapping)
        and payload.get("mode") == "official_harness_import"
        and payload.get("status") != "blocked"
        and str(payload.get("suite_id") or "") == str(task.get("suite_id") or "")
        and sha256_text(str(payload.get("candidate_id") or "")) == str(task.get("candidate_id_hash") or "")
        and isinstance(payload.get("case_results"), list)
        and bool(payload.get("case_results"))
    )


def _campaign_task_stage_receipt(
    base: Mapping[str, Any],
    *,
    status: str,
    preflight: Mapping[str, Any] | None,
    generation: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any] | None,
    imported: Mapping[str, Any] | None,
    auxiliary: Mapping[str, Any],
    safe_output_path: Path,
    elapsed_ms: float,
) -> dict[str, Any]:
    stage_rows = [row for row in (preflight, generation, evaluation, imported) if isinstance(row, Mapping)]
    reason_codes = sorted(
        {
            str(reason)
            for row in stage_rows
            for reason in row.get("reason_codes", [])
            if str(reason)
        }
    )
    imported_ready = isinstance(imported, Mapping) and imported.get("mode") == "official_harness_import" and imported.get("status") != "blocked"
    return {
        **dict(base),
        "status": status,
        "resume_action": "executed_or_resumed_stage_chain",
        "preflight_status": str(preflight.get("status") or "") if isinstance(preflight, Mapping) else "not_run",
        "generation_status": str(generation.get("status") or "") if isinstance(generation, Mapping) else "not_run",
        "evaluation_status": str(evaluation.get("status") or "") if isinstance(evaluation, Mapping) else "not_run",
        "import_status": "imported" if imported_ready else str(imported.get("status") or "not_run") if isinstance(imported, Mapping) else "not_run",
        "case_count": _first_int(evaluation, generation, preflight, field="case_count"),
        "completed_case_count": _first_int(evaluation, generation, field="completed_case_count"),
        "model_calls_performed": any(row.get("model_calls_performed") is True for row in stage_rows),
        "official_harness_execution_performed": any(
            row.get("official_harness_execution_performed") is True for row in stage_rows
        ),
        "safe_import_path_sha256": sha256_text(str(safe_output_path)),
        "safe_import_content_sha256": (
            sha256_text(stable_json(imported)) if imported_ready else ""
        ),
        "mt_bench_auxiliary_selection": _safe_auxiliary_receipt(auxiliary),
        "reason_codes": reason_codes,
        "elapsed_ms": round(float(elapsed_ms), 3),
        "raw_private_run_path_persisted": False,
        "raw_safe_import_path_persisted": False,
        "raw_candidate_id_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _campaign_task_base_receipt(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.official_harness_campaign_task.v1",
        "execution_task_id": str(task.get("execution_task_id") or ""),
        "suite_id": str(task.get("suite_id") or ""),
        "task_format": str(task.get("task_format") or ""),
        "candidate_id_hash": str(task.get("candidate_id_hash") or ""),
        "run_unit_id_hash": str(task.get("run_unit_id_hash") or ""),
        "candidate_type": str(task.get("candidate_type") or ""),
        "api_format": str(task.get("api_format") or ""),
        "provider_profile_hash": str(task.get("provider_profile_hash") or ""),
        "raw_candidate_id_persisted": False,
        "raw_provider_model_id_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _campaign_task_terminal_receipt(
    base: Mapping[str, Any],
    *,
    status: str,
    reason_codes: Sequence[str],
    elapsed_ms: float,
    auxiliary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **dict(base),
        "status": status,
        "resume_action": "none",
        "preflight_status": "not_run",
        "generation_status": "not_run",
        "evaluation_status": "not_run",
        "import_status": "not_run",
        "case_count": 0,
        "completed_case_count": 0,
        "model_calls_performed": False,
        "official_harness_execution_performed": False,
        "safe_import_path_sha256": "",
        "safe_import_content_sha256": "",
        "mt_bench_auxiliary_selection": _safe_auxiliary_receipt(auxiliary or {}),
        "reason_codes": sorted(set(str(reason) for reason in reason_codes if str(reason))),
        "elapsed_ms": round(float(elapsed_ms), 3),
        "raw_private_run_path_persisted": False,
        "raw_safe_import_path_persisted": False,
    }


def _safe_auxiliary_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("applicable") is not True:
        return {"applicable": False, "secrets_persisted": False}
    return {
        "applicable": True,
        "selection_policy": str(value.get("selection_policy") or ""),
        "comparison_candidate_id_sha256": str(value.get("comparison_candidate_id_sha256") or ""),
        "judge_candidate_id_sha256": str(value.get("judge_candidate_id_sha256") or ""),
        "comparison_profile_hash": str(value.get("comparison_profile_hash") or ""),
        "judge_profile_hash": str(value.get("judge_profile_hash") or ""),
        "reason_codes": sorted(str(reason) for reason in value.get("reason_codes", []) if str(reason)),
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _previous_failure_skip_receipt(task: Mapping[str, Any], previous: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_campaign_task_base_receipt(task),
        "status": str(previous.get("status") or "blocked"),
        "resume_action": "previous_failure_retained_retry_not_enabled",
        "preflight_status": str(previous.get("preflight_status") or "not_run"),
        "generation_status": str(previous.get("generation_status") or "not_run"),
        "evaluation_status": str(previous.get("evaluation_status") or "not_run"),
        "import_status": str(previous.get("import_status") or "not_run"),
        "case_count": _optional_int(previous.get("case_count")) or 0,
        "completed_case_count": _optional_int(previous.get("completed_case_count")) or 0,
        "model_calls_performed": False,
        "official_harness_execution_performed": False,
        "safe_import_path_sha256": str(previous.get("safe_import_path_sha256") or ""),
        "safe_import_content_sha256": str(previous.get("safe_import_content_sha256") or ""),
        "mt_bench_auxiliary_selection": dict(previous.get("mt_bench_auxiliary_selection") or {}),
        "reason_codes": sorted(str(reason) for reason in previous.get("reason_codes", []) if str(reason)),
        "elapsed_ms": 0.0,
        "raw_private_run_path_persisted": False,
        "raw_safe_import_path_persisted": False,
    }


def _campaign_base_state(
    *,
    plan_path: Path,
    config_path: Path,
    registry_path: Path,
    freeze_path: Path,
    pin_path: Path,
    private_root: Path,
    safe_import_root: Path,
    execution_plan_digest: str,
    source_task_count: int,
    selected_task_count: int,
    live: bool,
    retry_failed: bool,
    overwrite: bool,
    allow_unsafe_code_execution: bool,
    provider_baseline_freeze_required: bool,
    provider_baseline_freeze_ready: bool,
    provider_baseline_freeze_validation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": _CAMPAIGN_SCHEMA,
        "mode": "live" if live else "preflight_only",
        "execution_plan_digest_sha256": execution_plan_digest,
        "execution_plan_content_sha256": _file_content_sha256(plan_path),
        "suite_config_content_sha256": _file_content_sha256(config_path),
        "registry_content_sha256": _file_content_sha256(registry_path),
        "provider_baseline_freeze_content_sha256": _file_content_sha256(freeze_path),
        "harness_pin_manifest_content_sha256": _file_content_sha256(pin_path),
        "execution_plan_path_sha256": sha256_text(str(plan_path)),
        "suite_config_path_sha256": sha256_text(str(config_path)),
        "registry_path_sha256": sha256_text(str(registry_path)),
        "provider_baseline_freeze_path_sha256": sha256_text(str(freeze_path)),
        "harness_pin_manifest_path_sha256": sha256_text(str(pin_path)),
        "private_root_path_sha256": sha256_text(str(private_root)),
        "safe_import_root_path_sha256": sha256_text(str(safe_import_root)),
        "source_task_count": int(source_task_count),
        "selected_task_count": int(selected_task_count),
        "execution_controls": {
            "live_requires_explicit_flag": True,
            "provider_baseline_freeze_required": bool(
                provider_baseline_freeze_required
            ),
            "provider_baseline_freeze_ready": bool(
                provider_baseline_freeze_ready
            ),
            "provider_baseline_freeze_validation": dict(
                provider_baseline_freeze_validation
            ),
            "unfrozen_axio_preflight_only": bool(
                not live
                and not provider_baseline_freeze_required
                and not provider_baseline_freeze_ready
            ),
            "retry_failed": bool(retry_failed),
            "overwrite": bool(overwrite),
            "unsafe_code_execution_explicitly_authorized": bool(allow_unsafe_code_execution),
            "state_persisted_after_each_task": True,
            "existing_valid_imports_reused": not overwrite,
        },
        "raw_execution_plan_path_persisted": False,
        "raw_suite_config_path_persisted": False,
        "raw_registry_path_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "raw_private_paths_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _finalize_campaign_state(
    base: Mapping[str, Any],
    *,
    task_receipts: Sequence[Mapping[str, Any]],
    status: str,
    reason_codes: Sequence[str],
    elapsed_ms: float,
) -> dict[str, Any]:
    receipts = [dict(row) for row in task_receipts]
    counts: dict[str, int] = {}
    for row in receipts:
        row_status = str(row.get("status") or "unknown")
        counts[row_status] = counts.get(row_status, 0) + 1
    return {
        **dict(base),
        "status": status,
        "processed_task_count": len(receipts),
        "status_counts": dict(sorted(counts.items())),
        "imported_task_count": counts.get("imported", 0),
        "preflight_ready_task_count": counts.get("preflight_ready", 0),
        "blocked_task_count": counts.get("blocked", 0),
        "failed_task_count": counts.get("failed", 0),
        "model_call_task_count": sum(1 for row in receipts if row.get("model_calls_performed") is True),
        "official_harness_execution_task_count": sum(
            1 for row in receipts if row.get("official_harness_execution_performed") is True
        ),
        "reason_codes": sorted(set(str(reason) for reason in reason_codes if str(reason))),
        "task_receipts": receipts,
        "elapsed_ms": round(float(elapsed_ms), 3),
        "campaign_state_digest_sha256": sha256_text(
            stable_json(
                {
                    "schema": _CAMPAIGN_SCHEMA,
                    "execution_plan_digest_sha256": base.get("execution_plan_digest_sha256"),
                    "mode": base.get("mode"),
                    "status": status,
                    "task_receipts": receipts,
                    "reason_codes": sorted(set(str(reason) for reason in reason_codes if str(reason))),
                }
            )
        ),
    }


def _persist_campaign_progress(
    state_path: Path | None,
    base: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    started: float,
) -> None:
    status, reasons = _campaign_completion_status(receipts, live=base.get("mode") == "live", in_progress=True)
    payload = _finalize_campaign_state(
        base,
        task_receipts=receipts,
        status=status,
        reason_codes=reasons,
        elapsed_ms=(time.monotonic() - started) * 1000,
    )
    _persist_campaign_state(state_path, payload)


def _campaign_completion_status(
    receipts: Sequence[Mapping[str, Any]],
    *,
    live: bool,
    in_progress: bool = False,
) -> tuple[str, list[str]]:
    if in_progress:
        return "running", []
    statuses = [str(row.get("status") or "") for row in receipts]
    if live and statuses and all(status == "imported" for status in statuses):
        return "live_complete", []
    if not live and statuses and all(status == "preflight_ready" for status in statuses):
        return "preflight_ready", []
    reasons = sorted(
        {
            str(reason)
            for row in receipts
            for reason in row.get("reason_codes", [])
            if str(reason)
        }
    )
    if statuses and all(status == "blocked" for status in statuses):
        return "blocked", reasons or ["official_campaign_all_selected_tasks_blocked"]
    return "partial", reasons or ["official_campaign_selected_tasks_incomplete"]


def _select_campaign_tasks(
    tasks: Sequence[Mapping[str, Any]],
    *,
    suite_ids: Sequence[str],
    execution_task_ids: Sequence[str],
    candidate_hashes: Sequence[str],
    max_tasks: int | None,
) -> list[Mapping[str, Any]]:
    suites = {str(value).strip().lower() for value in suite_ids if str(value).strip()}
    task_ids = {str(value).strip() for value in execution_task_ids if str(value).strip()}
    hashes = {str(value).strip().lower() for value in candidate_hashes if _looks_like_sha256(value)}
    selected = [
        task
        for task in tasks
        if (not suites or str(task.get("suite_id") or "").lower() in suites)
        and (not task_ids or str(task.get("execution_task_id") or "") in task_ids)
        and (not hashes or str(task.get("candidate_id_hash") or "").lower() in hashes)
    ]
    if max_tasks is not None:
        return selected[: max(0, int(max_tasks))]
    return selected


def _load_campaign_registry(path: Path, reasons: list[str]) -> list[ModelProfile]:
    try:
        return load_registry(path)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        reasons.append("official_campaign_registry_unreadable")
        return []


def _load_json_object(path: Path, prefix: str, reasons: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        reasons.append(f"{prefix}_unreadable")
        return {}
    if not isinstance(payload, Mapping):
        reasons.append(f"{prefix}_not_object")
        return {}
    return dict(payload)


def _load_existing_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) and payload.get("schema") == _CAMPAIGN_SCHEMA else {}


def _persist_campaign_state(path: Path | None, payload: Mapping[str, Any]) -> None:
    if path is not None:
        _atomic_write_json(path, payload)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _ensure_private_root(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _file_content_sha256(path: Path) -> str:
    try:
        return sha256_text(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _first_int(*rows: Mapping[str, Any] | None, field: str) -> int:
    for row in rows:
        if isinstance(row, Mapping):
            value = _optional_int(row.get(field))
            if value is not None:
                return value
    return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _looks_like_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)
