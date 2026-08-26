#!/usr/bin/env python3
"""执行 r18 screening 启动前的零 provider 请求安全核验。

该工具只读取 frozen plan/source/registry、operational admission、两个
zero-network preflight receipt 和可选 screening PID。它复用现有网络策略的
secret-free summary，但不会向 provider 或 target benchmark 发请求。输出只保存
文件内容哈希、受控状态和 reason code，不包含路径、命令行、provider 信息、凭据
或原始内容。``ready_for_operator_authorization`` 不是 live screening 授权；
仍需要 operator 明确回复授权后才能启动唯一一套 r18 live screening。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


PLAN_SCHEMA = "axio_fusion_api.non_target_screening_plan.v3"
SOURCE_SCHEMA = "axio_fusion_api.non_target_screening_source_manifest.v1"
CAMPAIGN_SCHEMA = "axio_fusion_api.non_target_screening_campaign.v3"
ADMISSION_SCHEMA = "axio_fusion_api.operational_admission.v1"
VERIFIER_SCHEMA = "axio_fusion_api.screening_preflight_verifier.v1"
EXPECTED_TRANSPORT = "proxy"
SAFE_REASONS = frozenset(
    {
        "artifact_missing",
        "artifact_invalid",
        "schema_mismatch",
        "binding_mismatch",
        "plan_not_ready",
        "plan_contract_invalid",
        "source_contract_invalid",
        "admission_not_ready",
        "preflight_not_ready",
        "credential_preflight_not_ready",
        "credential_preflight_missing",
        "unexpected_network_calls",
        "unexpected_target_calls",
        "raw_sensitive_fields_persisted",
        "pid_not_matching",
        "network_policy_invalid",
        "network_transport_mismatch",
    }
)


class PreflightInputError(ValueError):
    """表示输入不可解析或违反 preflight 契约。"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--operational-admission", required=True, type=Path)
    parser.add_argument("--preflight-state", required=True, type=Path)
    parser.add_argument("--preflight-receipt", required=True, type=Path)
    parser.add_argument("--credential-preflight-state", required=True, type=Path)
    parser.add_argument("--credential-preflight-receipt", required=True, type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument(
        "--expected-transport",
        choices=("proxy", "direct"),
        default=EXPECTED_TRANSPORT,
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PreflightInputError("artifact_missing") from exc
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightInputError("artifact_invalid") from exc
    if not isinstance(value, Mapping):
        raise PreflightInputError("artifact_invalid")
    return dict(value)


def _flag_is_false(value: Any) -> bool:
    return value is False


def _all_safe_flags_false(payload: Mapping[str, Any]) -> bool:
    keys = (
        "secrets_persisted",
        "api_keys_persisted",
        "base_urls_persisted",
        "raw_provider_outputs_persisted",
        "raw_provider_urls_persisted",
        "raw_provider_names_persisted",
        "raw_provider_model_ids_persisted",
        "raw_api_key_env_names_persisted",
        "raw_base_url_env_names_persisted",
        "raw_base_urls_persisted",
        "raw_api_keys_persisted",
        "raw_prompts_persisted",
        "raw_questions_persisted",
        "raw_labels_persisted",
        "raw_dataset_paths_persisted",
        "target_benchmark_cases_or_labels_used",
    )
    return all(_flag_is_false(payload.get(key)) for key in keys if key in payload)


def _safe_artifact_flags(payload: Mapping[str, Any]) -> bool:
    if not _all_safe_flags_false(payload):
        return False
    for key in ("anti_leakage_contract", "workload_contract"):
        nested = payload.get(key)
        if isinstance(nested, Mapping) and not _all_safe_flags_false(nested):
            return False
    return True


def _reason(value: str) -> str:
    return value if value in SAFE_REASONS else "artifact_invalid"


def _check(condition: bool, reason: str, reasons: list[str]) -> None:
    if not condition:
        reasons.append(_reason(reason))


def _at_least_int(value: Any, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _binding_checks(
    *,
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    receipt: Mapping[str, Any],
    plan_sha: str,
    source_sha: str,
    registry_sha: str,
    reasons: list[str],
) -> None:
    plan_digest = str(plan.get("plan_digest_sha256") or "")
    _check(bool(plan_digest), "binding_mismatch", reasons)
    for payload in (state, receipt):
        _check(payload.get("schema") == CAMPAIGN_SCHEMA, "schema_mismatch", reasons)
        _check(payload.get("plan_digest_sha256") == plan_digest, "binding_mismatch", reasons)
        _check(payload.get("plan_file_content_sha256") == plan_sha, "binding_mismatch", reasons)
        _check(payload.get("source_manifest_content_sha256") == source_sha, "binding_mismatch", reasons)
        _check(payload.get("registry_file_sha256") == registry_sha, "binding_mismatch", reasons)


def _validate_plan(
    plan: Mapping[str, Any], *, plan_sha: str, source_sha: str, registry_sha: str
) -> list[str]:
    reasons: list[str] = []
    _check(plan.get("schema") == PLAN_SCHEMA, "schema_mismatch", reasons)
    _check(plan.get("ready") is True, "plan_not_ready", reasons)
    _check(
        plan.get("execution_mode") == "remote_provider_api_only",
        "plan_contract_invalid",
        reasons,
    )
    _check(plan.get("max_workers") == 1, "plan_contract_invalid", reasons)
    _check(plan.get("source_family_count") == 2, "plan_contract_invalid", reasons)
    _check(
        _at_least_int(plan.get("minimum_independent_source_count"), 2),
        "plan_contract_invalid",
        reasons,
    )
    _check(
        _at_least_int(plan.get("canonical_model_group_count"), 1),
        "plan_contract_invalid",
        reasons,
    )
    _check(
        _at_least_int(plan.get("replica_profile_count"), 1),
        "plan_contract_invalid",
        reasons,
    )
    _check(
        _at_least_int(plan.get("task_count"), 1),
        "plan_contract_invalid",
        reasons,
    )
    _check(plan.get("registry_file_sha256") == registry_sha, "binding_mismatch", reasons)
    _check(plan.get("source_manifest_content_sha256") == source_sha, "binding_mismatch", reasons)
    fail_fast = plan.get("fail_fast_policy")
    _check(isinstance(fail_fast, Mapping), "plan_contract_invalid", reasons)
    if isinstance(fail_fast, Mapping):
        _check(fail_fast.get("enabled") is True, "plan_contract_invalid", reasons)
        _check(fail_fast.get("requires_max_workers") == 1, "plan_contract_invalid", reasons)
        _check(fail_fast.get("unattempted_cases_are_transport_failures") is True, "plan_contract_invalid", reasons)
    no_cheat = plan.get("no_cheat_contract")
    _check(isinstance(no_cheat, Mapping), "plan_contract_invalid", reasons)
    if isinstance(no_cheat, Mapping):
        for key in (
            "target_suite_labels_used",
            "target_suite_prompts_used",
            "target_suite_results_used",
            "retry_on_wrong_answer",
            "registry_capability_priors_used_for_strength_ranking",
        ):
            _check(no_cheat.get(key) is False, "plan_contract_invalid", reasons)
    _check(_safe_artifact_flags(plan), "raw_sensitive_fields_persisted", reasons)
    _check(isinstance(plan.get("plan_digest_sha256"), str), "binding_mismatch", reasons)
    _check(bool(plan_sha) and bool(source_sha) and bool(registry_sha), "binding_mismatch", reasons)
    return reasons


def _validate_source(source: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    _check(source.get("schema") == SOURCE_SCHEMA, "schema_mismatch", reasons)
    _check(source.get("contains_api_keys") is False, "source_contract_invalid", reasons)
    _check(source.get("contains_labels") is False, "source_contract_invalid", reasons)
    pre_registration = source.get("pre_registration")
    _check(isinstance(pre_registration, Mapping), "source_contract_invalid", reasons)
    if isinstance(pre_registration, Mapping):
        _check(pre_registration.get("declared_before_target_campaign") is True, "source_contract_invalid", reasons)
        _check(pre_registration.get("target_benchmark_results_used") is False, "source_contract_invalid", reasons)
        _check(pre_registration.get("target_suite_results_used") is False, "source_contract_invalid", reasons)
    contract = source.get("scientific_contract")
    _check(isinstance(contract, Mapping), "source_contract_invalid", reasons)
    if isinstance(contract, Mapping):
        for key in (
            "retry_on_wrong_answer",
            "retry_on_low_score",
            "retry_on_parseable_answer",
            "ranking_uses_target_suite_material",
        ):
            _check(contract.get(key) is False, "source_contract_invalid", reasons)
    _check(source.get("secrets_persisted") is False, "raw_sensitive_fields_persisted", reasons)
    return reasons


def _validate_admission(
    admission: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    admission_sha: str,
) -> list[str]:
    reasons: list[str] = []
    _check(admission.get("schema") == ADMISSION_SCHEMA, "schema_mismatch", reasons)
    _check(admission.get("status") == "ready", "admission_not_ready", reasons)
    _check(admission.get("mode") == "live", "admission_not_ready", reasons)
    _check(admission.get("target_benchmark_cases_or_labels_used") is False, "admission_not_ready", reasons)
    _check(_safe_artifact_flags(admission), "raw_sensitive_fields_persisted", reasons)
    plan_admission = plan.get("operational_admission")
    _check(isinstance(plan_admission, Mapping), "binding_mismatch", reasons)
    if isinstance(plan_admission, Mapping):
        _check(
            plan_admission.get("content_sha256") == admission_sha,
            "binding_mismatch",
            reasons,
        )
        _check(plan_admission.get("status") == "ready", "admission_not_ready", reasons)
        _check(
            admission.get("formal_baseline_eligible_count")
            == plan_admission.get("formal_baseline_eligible_count"),
            "binding_mismatch",
            reasons,
        )
    return reasons


def _validate_preflight(
    payload: Mapping[str, Any], *, plan: Mapping[str, Any], credential: bool
) -> list[str]:
    reasons: list[str] = []
    _check(payload.get("schema") == CAMPAIGN_SCHEMA, "schema_mismatch", reasons)
    _check(payload.get("status") == "preflight_ready", "preflight_not_ready", reasons)
    _check(payload.get("mode") == "preflight", "preflight_not_ready", reasons)
    _check(payload.get("network_calls_performed") is False, "unexpected_network_calls", reasons)
    _check(payload.get("target_suite_calls_performed") is False, "unexpected_target_calls", reasons)
    _check(payload.get("ready_for_ranking") is False, "preflight_not_ready", reasons)
    _check(payload.get("planned_task_count") == plan.get("task_count"), "binding_mismatch", reasons)
    _check(payload.get("selected_task_count") == plan.get("task_count"), "binding_mismatch", reasons)
    _check(_safe_artifact_flags(payload), "raw_sensitive_fields_persisted", reasons)
    if credential:
        readiness = payload.get("live_credential_readiness")
        _check(isinstance(readiness, Mapping), "credential_preflight_not_ready", reasons)
        if isinstance(readiness, Mapping):
            _check(readiness.get("ready") is True, "credential_preflight_not_ready", reasons)
            _check(
                readiness.get("credential_ready_profile_count")
                == plan.get("replica_profile_count"),
                "credential_preflight_not_ready",
                reasons,
            )
            _check(
                readiness.get("required_profile_count")
                == plan.get("replica_profile_count"),
                "credential_preflight_not_ready",
                reasons,
            )
            _check(_safe_artifact_flags(readiness), "raw_sensitive_fields_persisted", reasons)
    return reasons


def _proc_cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _option_value(tokens: Sequence[str], option: str) -> str:
    try:
        index = list(tokens).index(option)
    except ValueError:
        return ""
    return str(tokens[index + 1]) if index + 1 < len(tokens) else ""


def _path_option_matches(tokens: Sequence[str], option: str, expected: Path) -> bool:
    value = _option_value(tokens, option)
    if not value:
        return False
    try:
        return Path(value).expanduser().resolve() == expected.expanduser().resolve()
    except OSError:
        return False


def _validate_pid(pid: int | None, *, plan: Path, source: Path, registry: Path) -> dict[str, Any]:
    if pid is None:
        return {"status": "not_started", "pid_present": False, "command_sha256": ""}
    command = _proc_cmdline(pid)
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = []
    matches = (
        "baseline-screening-run" in tokens
        and "--live" in tokens
        and _path_option_matches(tokens, "--plan", plan)
        and _path_option_matches(tokens, "--source-manifest", source)
        and _path_option_matches(tokens, "--registry", registry)
    )
    return {
        "status": "matching" if matches else "blocked",
        "pid_present": bool(command),
        "command_sha256": _sha256_text(command) if command else "",
    }


def _network_summary() -> dict[str, Any]:
    try:
        from axio_fusion_api.network import provider_proxy_runtime_summary

        raw = provider_proxy_runtime_summary()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return {"valid": False, "selected_transport": "error", "listener_detected": None, "mode": ""}
    return {
        "mode": str(raw.get("mode") or ""),
        "valid": raw.get("valid") is True,
        "listener_detected": raw.get("listener_detected"),
        "selected_transport": str(raw.get("selected_transport") or ""),
        "reason_code": str(raw.get("reason_code") or ""),
        "raw_proxy_url_persisted": False,
        "secrets_persisted": False,
    }


def verify_preflight(args: argparse.Namespace) -> dict[str, Any]:
    paths = (
        args.registry,
        args.plan,
        args.source_manifest,
        args.operational_admission,
        args.preflight_state,
        args.preflight_receipt,
        args.credential_preflight_state,
        args.credential_preflight_receipt,
    )
    hashes = {str(path): _sha256_file(path) for path in paths}
    registry_sha = hashes[str(args.registry)]
    plan_sha = hashes[str(args.plan)]
    source_sha = hashes[str(args.source_manifest)]
    plan = _read_object(args.plan)
    source = _read_object(args.source_manifest)
    admission = _read_object(args.operational_admission)
    state = _read_object(args.preflight_state)
    receipt = _read_object(args.preflight_receipt)
    credential_state = _read_object(args.credential_preflight_state)
    credential_receipt = _read_object(args.credential_preflight_receipt)
    reasons: list[str] = []
    reasons.extend(
        _validate_plan(
            plan,
            plan_sha=plan_sha,
            source_sha=source_sha,
            registry_sha=registry_sha,
        )
    )
    reasons.extend(_validate_source(source))
    reasons.extend(
        _validate_admission(
            admission,
            plan,
            admission_sha=hashes[str(args.operational_admission)],
        )
    )
    _binding_checks(
        plan=plan,
        state=state,
        receipt=receipt,
        plan_sha=plan_sha,
        source_sha=source_sha,
        registry_sha=registry_sha,
        reasons=reasons,
    )
    _binding_checks(
        plan=plan,
        state=credential_state,
        receipt=credential_receipt,
        plan_sha=plan_sha,
        source_sha=source_sha,
        registry_sha=registry_sha,
        reasons=reasons,
    )
    reasons.extend(_validate_preflight(state, plan=plan, credential=False))
    reasons.extend(_validate_preflight(receipt, plan=plan, credential=False))
    reasons.extend(_validate_preflight(credential_state, plan=plan, credential=True))
    reasons.extend(_validate_preflight(credential_receipt, plan=plan, credential=True))
    pid = _validate_pid(args.pid, plan=args.plan, source=args.source_manifest, registry=args.registry)
    if pid["status"] == "blocked":
        reasons.append("pid_not_matching")
    network = _network_summary()
    if network.get("valid") is not True:
        reasons.append("network_policy_invalid")
    if network.get("selected_transport") != args.expected_transport:
        reasons.append("network_transport_mismatch")
    unique_reasons = sorted(set(reasons))
    return {
        "schema": VERIFIER_SCHEMA,
        "status": "ready_for_operator_authorization" if not unique_reasons else "blocked",
        "ready_for_operator_authorization": not unique_reasons,
        "authorization_required": True,
        "network_calls_performed": False,
        "provider_calls_performed": False,
        "target_suite_calls_performed": False,
        "frozen_inputs_mutated": False,
        "plan_file_sha256": plan_sha,
        "source_manifest_file_sha256": source_sha,
        "registry_file_sha256": registry_sha,
        "operational_admission_file_sha256": hashes[str(args.operational_admission)],
        "preflight_state_file_sha256": hashes[str(args.preflight_state)],
        "preflight_receipt_file_sha256": hashes[str(args.preflight_receipt)],
        "credential_preflight_state_file_sha256": hashes[str(args.credential_preflight_state)],
        "credential_preflight_receipt_file_sha256": hashes[str(args.credential_preflight_receipt)],
        "plan_digest_sha256": str(plan.get("plan_digest_sha256") or ""),
        "pid": pid,
        "network": network,
        "reason_codes": unique_reasons,
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> int:
    args = _parser().parse_args()
    try:
        result = verify_preflight(args)
        _atomic_write(args.output, result)
    except (PreflightInputError, TypeError, ValueError) as exc:
        result = {
            "schema": VERIFIER_SCHEMA,
            "status": "blocked",
            "ready_for_operator_authorization": False,
            "authorization_required": True,
            "network_calls_performed": False,
            "provider_calls_performed": False,
            "target_suite_calls_performed": False,
            "frozen_inputs_mutated": False,
            "reason_codes": [_reason(str(exc))],
            "raw_provider_outputs_persisted": False,
            "raw_prompts_persisted": False,
            "raw_provider_urls_persisted": False,
            "secrets_persisted": False,
        }
        _atomic_write(args.output, result)
    return 0 if result["status"] == "ready_for_operator_authorization" else 2


if __name__ == "__main__":
    raise SystemExit(main())
