#!/usr/bin/env python3
"""对一个 composite cohort 执行纯离线的 hash-only 收敛审计。

该审计器只读取已经生成的 safe/private 控制面 artifact，不发起网络请求，不
修改 frozen plan，不恢复 screening，也不启动 target benchmark。它把每一层
证据转换成明确的 ``ready``、``running``、``blocked`` 或 ``pending`` 状态，
使长时间 live screening 结束后可以直接判断下一道门，而无需读取答案、标签或
provider 输出。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


TERMINAL_SCREENING = frozenset({"completed", "partial", "blocked", "failed"})
SAFE_REASON_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--transport-admission", type=Path)
    parser.add_argument("--ranking", type=Path)
    parser.add_argument("--provider-baseline-freeze", type=Path)
    parser.add_argument("--harness-pin", type=Path)
    parser.add_argument("--execution-plan", type=Path)
    parser.add_argument("--acquisition-status", type=Path)
    parser.add_argument("--official-import-audit", type=Path)
    parser.add_argument("--cohort-binding", type=Path)
    parser.add_argument("--target-campaign", type=Path)
    parser.add_argument("--final-audit", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _read_object(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _safe_reasons(value: Mapping[str, Any]) -> list[str]:
    reasons: set[str] = set()

    def add(raw: Any) -> None:
        token = str(raw)
        if SAFE_REASON_RE.fullmatch(token):
            reasons.add(token)

    for key in ("reason_codes", "blockers", "blocking_reasons"):
        rows = value.get(key)
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            for item in rows:
                add(item)
    counts = value.get("blocking_reason_counts")
    if isinstance(counts, Mapping):
        for key in counts:
            add(key)
    return sorted(reasons)


def _artifact_stage(
    name: str,
    path: Path | None,
    *,
    ready: bool,
    status: str | None = None,
    reasons: Sequence[str] = (),
) -> dict[str, Any]:
    payload = _read_object(path)
    if path is None or not path.is_file():
        stage_status = "pending"
        stage_reasons = ["artifact_missing"]
    elif payload is None:
        stage_status = "blocked"
        stage_reasons = ["artifact_invalid"]
    elif ready:
        stage_status = "ready"
        stage_reasons = []
    else:
        stage_status = status or "blocked"
        stage_reasons = sorted(
            str(item) for item in reasons if SAFE_REASON_RE.fullmatch(str(item))
        )
        if not stage_reasons:
            stage_reasons = _safe_reasons(payload) or [f"{name}_not_ready"]
    return {
        "stage": name,
        "status": stage_status,
        "reason_codes": stage_reasons,
        "artifact_sha256": _sha256_file(path) if path else "",
        "schema": str(payload.get("schema") or "") if payload else "",
    }


def _screening_stage(
    *, state_path: Path, plan_path: Path, registry_path: Path
) -> dict[str, Any]:
    state = _read_object(state_path)
    plan = _read_object(plan_path)
    reasons: list[str] = []
    if state is None:
        return _artifact_stage("screening", state_path, ready=False, reasons=("screening_state_missing",))
    if plan is None:
        reasons.append("screening_plan_missing")
    elif plan.get("ready") is not True:
        reasons.append("screening_plan_not_ready")
    plan_digest = str(plan.get("plan_digest_sha256") or "") if plan else ""
    state_plan_digest = str(state.get("plan_digest_sha256") or "")
    if plan_digest and state_plan_digest and plan_digest != state_plan_digest:
        reasons.append("screening_plan_digest_mismatch")
    registry_hash = _sha256_file(registry_path)
    state_registry_hash = str(state.get("registry_file_sha256") or "")
    if state_registry_hash and registry_hash and state_registry_hash != registry_hash:
        reasons.append("screening_registry_digest_mismatch")
    state_status = str(state.get("status") or "")
    if state_status not in TERMINAL_SCREENING:
        status = "running" if state_status == "running" else "pending"
        reasons.append("screening_not_terminal")
        return _artifact_stage("screening", state_path, ready=False, status=status, reasons=reasons)
    if state.get("ready_for_ranking") is not True:
        reasons.append("screening_not_ready_for_ranking")
    return _artifact_stage("screening", state_path, ready=not reasons, reasons=reasons)


def _boolean_stage(name: str, path: Path | None, fields: Sequence[str]) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and any(value.get(field) is True for field in fields)
    return _artifact_stage(name, path, ready=ready, reasons=_safe_reasons(value or {}))


def _transport_stage(path: Path | None) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and str(value.get("status") or "") == "ready"
    return _artifact_stage("transport_admission", path, ready=ready)


def _ranking_stage(path: Path | None) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and value.get("screening_conversion_ready") is True
    return _artifact_stage("ranking", path, ready=ready)


def _provider_freeze_stage(path: Path | None, registry_path: Path) -> dict[str, Any]:
    value = _read_object(path)
    reasons: list[str] = []
    if value:
        if value.get("schema") != "axio_fusion_api.provider_baseline_freeze_manifest.v1":
            reasons.append("provider_baseline_freeze_schema_invalid")
        if value.get("final_claim_freeze_ready") is not True:
            reasons.append("provider_baseline_freeze_not_ready")
        if value.get("provider_baseline_selection") != "externally_ranked_top_three_pre_registered":
            reasons.append("provider_baseline_freeze_selection_invalid")
        if value.get("selected_all_available_provider_baselines") is not False:
            reasons.append("provider_baseline_freeze_exhaustive_selection")
        if value.get("selected_provider_baseline_count") != 3:
            reasons.append("provider_baseline_freeze_selected_count_invalid")
        if value.get("required_provider_baseline_count") != 3:
            reasons.append("provider_baseline_freeze_required_count_invalid")
        external = value.get("external_ranking_receipt")
        if not isinstance(external, Mapping) or external.get("ready") is not True:
            reasons.append("provider_baseline_freeze_external_ranking_not_ready")
        elif external.get("pre_registered_before_campaign") is not True:
            reasons.append("provider_baseline_freeze_external_ranking_not_preregistered")
        registry = value.get("provider_registry_receipt")
        if not isinstance(registry, Mapping) or registry.get("registry_file_sha256") != _sha256_file(registry_path):
            reasons.append("provider_baseline_freeze_registry_mismatch")
        for key in ("raw_provider_outputs_persisted", "raw_provider_urls_persisted", "secrets_persisted"):
            if value.get(key) is not False:
                reasons.append(f"provider_baseline_freeze_{key}")
    return _artifact_stage("provider_baseline_freeze", path, ready=not reasons and bool(value), reasons=reasons)


def _harness_pin_stage(path: Path | None) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and (
        value.get("suite_count", 0) == value.get("ready_suite_count", -1)
        and value.get("blocked_suite_count", 1) == 0
        and value.get("raw_local_paths_persisted") is False
        and value.get("all_paths_hashed_only") is True
        and value.get("raw_dataset_content_persisted") is False
        and value.get("raw_prompts_persisted") is False
        and value.get("raw_labels_persisted") is False
        and value.get("raw_provider_outputs_persisted") is False
        and value.get("secrets_persisted") is False
    )
    return _artifact_stage("harness_pin", path, ready=ready)


def _execution_plan_stage(path: Path | None) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and (
        value.get("status") == "ready_to_execute"
        and value.get("all_tasks_ready_to_execute") is True
        and value.get("all_required_outputs_are_hash_only_import_sources") is True
        and value.get("secrets_persisted") is False
    )
    return _artifact_stage("execution_plan", path, ready=ready)


def _acquisition_stage(path: Path | None) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and (
        value.get("ready_to_assemble_manifest") is True
        and value.get("official_import_missing_count") == 0
        and value.get("ready_suite_count") == value.get("required_suite_count")
        and value.get("secrets_persisted") is False
        and value.get("raw_provider_outputs_persisted") is False
    )
    return _artifact_stage("benchmark_acquisition", path, ready=ready)


def _official_import_stage(path: Path | None) -> dict[str, Any]:
    value = _read_object(path)
    ready = bool(value) and (
        value.get("ready_for_campaign_import_stage") is True
        and value.get("blocked_official_suite_count") == 0
        and value.get("ready_official_suite_count") == value.get("official_suite_count")
        and value.get("secrets_persisted") is False
        and value.get("raw_provider_outputs_persisted") is False
    )
    return _artifact_stage("official_import", path, ready=ready)


def _cohort_binding_stage(
    path: Path | None,
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """验证所有前置证据是否绑定到同一个 immutable cohort。"""

    payload = _read_object(path)
    reasons: list[str] = []
    if payload is None:
        return _artifact_stage("cohort_binding", path, ready=False, reasons=("artifact_missing",))
    if payload.get("schema") != "axio_fusion_api.composite_harness_cohort_binding.v1":
        reasons.append("cohort_binding_schema_invalid")
    if payload.get("status") != "ready":
        reasons.append("cohort_binding_not_ready")
    declared_digest = str(payload.get("cohort_binding_digest_sha256") or "")
    if payload.get("cohort_id_sha256") != declared_digest:
        reasons.append("cohort_binding_cohort_id_mismatch")
    if payload.get("target_suite_calls_allowed") is not True:
        reasons.append("cohort_binding_target_calls_not_allowed")
    if payload.get("target_suite_calls_performed") is not False:
        reasons.append("cohort_binding_target_suite_calls_present")
    bindings = payload.get("stage_bindings")
    if not isinstance(bindings, Mapping):
        reasons.append("cohort_binding_stage_bindings_missing")
        bindings = {}
    required = {
        "registry": args.registry,
        "plan": args.plan,
        "state": args.state,
        "transport_admission": args.transport_admission,
        "ranking": args.ranking,
        "provider_baseline_freeze": args.provider_baseline_freeze,
        "harness_pin": args.harness_pin,
        "execution_plan": args.execution_plan,
        "acquisition_status": args.acquisition_status,
        "official_import_audit": args.official_import_audit,
    }
    for name, artifact_path in required.items():
        row = bindings.get(name)
        if artifact_path is None or not isinstance(row, Mapping):
            reasons.append(f"cohort_binding_{name}_missing")
            continue
        if str(row.get("content_sha256") or "") != _sha256_file(artifact_path):
            reasons.append(f"cohort_binding_{name}_content_mismatch")
        if str(row.get("path_sha256") or "") != _sha256_text(str(artifact_path)):
            reasons.append(f"cohort_binding_{name}_path_mismatch")
    declarations = payload.get("declarations")
    if not isinstance(declarations, Mapping):
        reasons.append("cohort_binding_declarations_missing")
        declarations = {}
    state = _read_object(args.state)
    plan = _read_object(args.plan)
    freeze = _read_object(args.provider_baseline_freeze)
    execution = _read_object(args.execution_plan)
    import_audit = _read_object(args.official_import_audit)
    expected_declarations = {
        "screening_plan_digest_sha256": str(plan.get("plan_digest_sha256") or ""),
        "screening_campaign_digest_sha256": str(state.get("campaign_digest_sha256") or ""),
        "provider_baseline_freeze_digest_sha256": str(freeze.get("freeze_digest_sha256") or ""),
        "execution_plan_digest_sha256": str(execution.get("execution_plan_digest_sha256") or ""),
        "official_import_audit_digest_sha256": str(import_audit.get("audit_digest_sha256") or ""),
        "target_suite_calls_performed": False,
    }
    for name, expected in expected_declarations.items():
        if declarations.get(name) != expected:
            reasons.append(f"cohort_binding_{name}_mismatch")
    digest_input = payload.get("binding_digest_input")
    if not isinstance(digest_input, Mapping) or not _sha256_text(_stable_json(digest_input)) == declared_digest:
        reasons.append("cohort_binding_digest_invalid")
    for field in (
        "raw_provider_outputs_persisted",
        "raw_prompts_persisted",
        "raw_labels_persisted",
        "raw_provider_urls_persisted",
        "secrets_persisted",
    ):
        if payload.get(field) is not False:
            reasons.append(f"cohort_binding_{field}")
    return _artifact_stage("cohort_binding", path, ready=not reasons, reasons=reasons)


def _stage_statuses(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        _screening_stage(state_path=args.state, plan_path=args.plan, registry_path=args.registry),
        _transport_stage(args.transport_admission),
        _ranking_stage(args.ranking),
        _provider_freeze_stage(args.provider_baseline_freeze, args.registry),
        _harness_pin_stage(args.harness_pin),
        _execution_plan_stage(args.execution_plan),
        _acquisition_stage(args.acquisition_status),
        _official_import_stage(args.official_import_audit),
        _cohort_binding_stage(args.cohort_binding, args=args),
        _boolean_stage("target_campaign", args.target_campaign, ("final_claims_allowed", "status_complete")),
        _boolean_stage("final_audit", args.final_audit, ("final_claims_allowed", "completion_ready", "ready")),
    ]


def audit_cohort(args: argparse.Namespace) -> dict[str, Any]:
    stages = _stage_statuses(args)
    first_pending = next((stage for stage in stages if stage["status"] != "ready"), None)
    pre_target_ready = all(stage["status"] == "ready" for stage in stages[:9])
    any_running = any(stage["status"] == "running" for stage in stages)
    state = _read_object(args.state) or {}
    target_calls_present = state.get("target_suite_calls_performed") is not False
    reason_codes = {reason for stage in stages for reason in stage["reason_codes"]}
    if target_calls_present:
        reason_codes.add("screening_target_suite_calls_present")
    all_ready = first_pending is None and not target_calls_present
    target_calls_allowed = pre_target_ready and not target_calls_present
    if all_ready:
        overall_status = "ready"
    elif target_calls_allowed:
        overall_status = "ready_for_target_campaign"
    else:
        overall_status = "running" if any_running else "blocked"
    return {
        "schema": "axio_fusion_api.composite_convergence_audit.v1",
        "status": overall_status,
        "next_gate": first_pending["stage"] if first_pending else "complete",
        "reason_codes": sorted(reason_codes),
        "stage_statuses": stages,
        "input_bindings": {
            "registry_file_sha256": _sha256_file(args.registry),
            "plan_file_sha256": _sha256_file(args.plan),
            "state_file_sha256": _sha256_file(args.state),
            "screening_plan_digest_sha256": str(state.get("plan_digest_sha256") or ""),
            "screening_campaign_digest_sha256": str(state.get("campaign_digest_sha256") or ""),
        },
        "target_suite_calls_allowed": target_calls_allowed,
        "final_claim_allowed": all_ready,
        "plan_mutated": False,
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    args = _parser().parse_args()
    result = audit_cohort(args)
    try:
        _write_json(args.output, result)
    except OSError:
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
