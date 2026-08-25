#!/usr/bin/env python3
"""为一个 composite cohort 生成 hash-only Harness lineage receipt。

该工具只读取已经存在的控制面 artifact，不访问网络、不调用 provider、不修改
任何输入文件。它把 screening、transport、ranking、provider freeze、official
import 和 Harness execution 绑定成一个不可变的 cohort id，避免旧模板或异 cohort
结果被误接入正式 target campaign。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


SHA256_HEX_LENGTH = 64
SCREENING_PLAN_SCHEMA = "axio_fusion_api.non_target_screening_plan.v3"
SCREENING_STATE_SCHEMA = "axio_fusion_api.non_target_screening_campaign.v3"
TRANSPORT_SCHEMA = "axio_fusion_api.non_target_screening_transport_admission.v1"
RANKING_SCHEMA = "axio_fusion_api.external_provider_ranking_input.v3"
FREEZE_SCHEMA = "axio_fusion_api.provider_baseline_freeze_manifest.v1"
PIN_SCHEMA = "axio_fusion_api.benchmark_harness_pin_manifest.v1"
EXECUTION_PLAN_SCHEMA = "axio_fusion_api.official_harness_execution_plan.v1"
ACQUISITION_SCHEMA = "axio_fusion_api.benchmark_acquisition_status.v1"
IMPORT_AUDIT_SCHEMA = "axio_fusion_api.official_import_audit.v1"

REQUIRED_ARTIFACTS = (
    "registry",
    "plan",
    "state",
    "transport_admission",
    "ranking",
    "provider_baseline_freeze",
    "harness_pin",
    "execution_plan",
    "acquisition_status",
    "official_import_audit",
)
SENSITIVE_FALSE_FIELDS = (
    "raw_api_keys_persisted",
    "raw_base_urls_persisted",
    "raw_dataset_content_persisted",
    "raw_dataset_paths_persisted",
    "raw_import_paths_persisted",
    "raw_labels_persisted",
    "raw_local_paths_persisted",
    "raw_prompts_persisted",
    "raw_provider_model_ids_persisted",
    "raw_provider_names_persisted",
    "raw_provider_outputs_persisted",
    "raw_provider_urls_persisted",
    "secrets_persisted",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in REQUIRED_ARTIFACTS:
        parser.add_argument(f"--{name.replace('_', '-')}", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _looks_like_sha256(value: Any) -> bool:
    token = str(value or "").strip().lower()
    return len(token) == SHA256_HEX_LENGTH and all(
        char in "0123456789abcdef" for char in token
    )


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_reason(value: str) -> str:
    token = "".join(char if char.isalnum() or char in "_.:-" else "_" for char in value)
    return token[:128] or "artifact_invalid"


def _require_false_flags(payload: Mapping[str, Any], *, prefix: str, reasons: list[str]) -> None:
    for field in SENSITIVE_FALSE_FIELDS:
        if field in payload and payload.get(field) is not False:
            reasons.append(f"{prefix}_{field}")


def _artifact_row(path: Path, payload: Mapping[str, Any], *, ready: bool, reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "path_sha256": _sha256_text(str(path)),
        "content_sha256": _sha256_file(path),
        "schema": str(payload.get("schema") or ""),
        "ready": bool(ready and not reasons),
        "reason_codes": sorted(set(_safe_reason(str(reason)) for reason in reasons if str(reason))),
    }


def _load_required(path: Path, *, name: str, reasons: list[str]) -> dict[str, Any]:
    payload = _read_object(path)
    if not payload:
        reasons.append(f"{name}_artifact_missing_or_invalid")
    return payload


def _validate_screening(
    *,
    registry_path: Path,
    plan_path: Path,
    state_path: Path,
    registry: Mapping[str, Any],
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    reasons: list[str],
) -> None:
    registry_sha = _sha256_file(registry_path)
    plan_sha = _sha256_file(plan_path)
    state_sha = _sha256_file(state_path)
    if not registry_sha:
        reasons.append("registry_artifact_missing")
    if plan.get("schema") != SCREENING_PLAN_SCHEMA or plan.get("ready") is not True:
        reasons.append("screening_plan_not_ready")
    if state.get("schema") != SCREENING_STATE_SCHEMA or state.get("status") != "completed":
        reasons.append("screening_state_not_terminal_complete")
    if state.get("ready_for_ranking") is not True:
        reasons.append("screening_state_not_ready_for_ranking")
    if state.get("target_suite_calls_performed") is not False:
        reasons.append("screening_target_suite_calls_present")
    if str(plan.get("registry_file_sha256") or "") != registry_sha:
        reasons.append("screening_plan_registry_binding_mismatch")
    if str(state.get("registry_file_sha256") or "") != registry_sha:
        reasons.append("screening_state_registry_binding_mismatch")
    if str(state.get("plan_file_content_sha256") or "") != plan_sha:
        reasons.append("screening_state_plan_content_binding_mismatch")
    if str(state.get("plan_digest_sha256") or "") != str(plan.get("plan_digest_sha256") or ""):
        reasons.append("screening_plan_digest_mismatch")
    if not _looks_like_sha256(state.get("campaign_digest_sha256")):
        reasons.append("screening_campaign_digest_missing")
    _require_false_flags(registry, prefix="registry", reasons=reasons)
    _require_false_flags(plan, prefix="screening_plan", reasons=reasons)
    _require_false_flags(state, prefix="screening_state", reasons=reasons)
    if not plan_sha or not state_sha:
        reasons.append("screening_content_digest_missing")


def _validate_transport(
    *,
    path: Path,
    payload: Mapping[str, Any],
    registry_path: Path,
    plan_path: Path,
    state_path: Path,
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    reasons: list[str],
) -> None:
    if payload.get("schema") != TRANSPORT_SCHEMA or payload.get("status") != "ready":
        reasons.append("transport_admission_not_ready")
    expected = {
        "source_plan_file_sha256": _sha256_file(plan_path),
        "source_campaign_state_file_sha256": _sha256_file(state_path),
        "registry_file_sha256": _sha256_file(registry_path),
        "plan_digest_sha256": str(plan.get("plan_digest_sha256") or ""),
        "campaign_digest_sha256": str(state.get("campaign_digest_sha256") or ""),
    }
    for field, value in expected.items():
        if str(payload.get(field) or "") != value:
            reasons.append(f"transport_{field}_mismatch")
    if payload.get("selection_basis") != "transport_failure_rate_only":
        reasons.append("transport_selection_basis_invalid")
    if payload.get("quality_fields_used_for_selection") not in ([], None):
        reasons.append("transport_quality_selection_present")
    _require_false_flags(payload, prefix="transport", reasons=reasons)
    if not _sha256_file(path):
        reasons.append("transport_content_digest_missing")


def _validate_ranking(
    *,
    path: Path,
    payload: Mapping[str, Any],
    registry_path: Path,
    state_path: Path,
    reasons: list[str],
) -> None:
    if payload.get("schema") != RANKING_SCHEMA or payload.get("screening_conversion_ready") is not True:
        reasons.append("ranking_not_ready")
    if str(payload.get("screening_campaign_state_sha256") or "") != _sha256_file(state_path):
        reasons.append("ranking_screening_state_binding_mismatch")
    if str(payload.get("registry_file_sha256") or "") != _sha256_file(registry_path):
        reasons.append("ranking_registry_binding_mismatch")
    _require_false_flags(payload, prefix="ranking", reasons=reasons)
    if not _sha256_file(path):
        reasons.append("ranking_content_digest_missing")


def _validate_freeze(
    *,
    payload: Mapping[str, Any],
    registry_path: Path,
    transport_path: Path,
    ranking_path: Path,
    reasons: list[str],
) -> None:
    if payload.get("schema") != FREEZE_SCHEMA or payload.get("final_claim_freeze_ready") is not True:
        reasons.append("provider_baseline_freeze_not_ready")
    if payload.get("provider_baseline_selection") != "externally_ranked_top_three_pre_registered":
        reasons.append("provider_baseline_freeze_selection_invalid")
    if payload.get("selected_all_available_provider_baselines") is not False:
        reasons.append("provider_baseline_freeze_exhaustive_selection")
    if payload.get("selected_provider_baseline_count") != 3 or payload.get("required_provider_baseline_count") != 3:
        reasons.append("provider_baseline_freeze_count_invalid")
    registry = payload.get("provider_registry_receipt")
    if not isinstance(registry, Mapping) or registry.get("registry_file_sha256") != _sha256_file(registry_path):
        reasons.append("provider_baseline_freeze_registry_mismatch")
    external = payload.get("external_ranking_receipt")
    if not isinstance(external, Mapping) or external.get("ready") is not True:
        reasons.append("provider_baseline_freeze_external_ranking_not_ready")
    elif external.get("input_content_sha256") != _sha256_file(ranking_path):
        reasons.append("provider_baseline_freeze_ranking_binding_mismatch")
    transport = payload.get("transport_availability_receipt")
    if isinstance(transport, Mapping) and transport.get("required") is True:
        if transport.get("status") != "ready":
            reasons.append("provider_baseline_freeze_transport_not_ready")
        if transport.get("content_sha256") != _sha256_file(transport_path):
            reasons.append("provider_baseline_freeze_transport_binding_mismatch")
    if not _looks_like_sha256(payload.get("freeze_digest_sha256")):
        reasons.append("provider_baseline_freeze_digest_missing")
    _require_false_flags(payload, prefix="provider_baseline_freeze", reasons=reasons)


def _validate_pin(payload: Mapping[str, Any], reasons: list[str]) -> None:
    if payload.get("schema") != PIN_SCHEMA:
        reasons.append("harness_pin_schema_invalid")
    if payload.get("suite_count") != payload.get("ready_suite_count") or payload.get("blocked_suite_count") != 0:
        reasons.append("harness_pin_not_complete")
    if payload.get("all_paths_hashed_only") is not True:
        reasons.append("harness_pin_paths_not_hash_only")
    _require_false_flags(payload, prefix="harness_pin", reasons=reasons)


def _validate_execution_plan(
    *,
    payload: Mapping[str, Any],
    harness_pin_path: Path,
    acquisition_path: Path,
    provider_baseline_freeze_path: Path,
    reasons: list[str],
) -> None:
    if payload.get("schema") != EXECUTION_PLAN_SCHEMA or payload.get("status") != "ready_to_execute":
        reasons.append("execution_plan_not_ready")
    if payload.get("execution_authorized") is not True:
        reasons.append("execution_plan_not_authorized")
    if payload.get("matrix_mode") != "formal_top_three_cohort":
        reasons.append("execution_plan_formal_cohort_required")
    if payload.get("formal_top_three_cohort_complete") is not True:
        reasons.append("execution_plan_formal_cohort_incomplete")
    if payload.get("formal_cohort_binding_reason_codes") not in ([], None):
        reasons.append("execution_plan_formal_cohort_binding_blocked")
    if payload.get("all_tasks_ready_to_execute") is not True:
        reasons.append("execution_plan_tasks_not_ready")
    if payload.get("all_required_outputs_are_hash_only_import_sources") is not True:
        reasons.append("execution_plan_outputs_not_hash_only")
    if payload.get("harness_pin_manifest_path_sha256") != _sha256_text(str(harness_pin_path)):
        reasons.append("execution_plan_harness_pin_path_binding_mismatch")
    if payload.get("acquisition_status_path_sha256") != _sha256_text(str(acquisition_path)):
        reasons.append("execution_plan_acquisition_path_binding_mismatch")
    if payload.get("provider_baseline_freeze_path_sha256") != _sha256_text(
        str(provider_baseline_freeze_path)
    ):
        reasons.append("execution_plan_provider_baseline_freeze_path_binding_mismatch")
    if payload.get("provider_baseline_freeze_content_sha256") != _sha256_file(
        provider_baseline_freeze_path
    ):
        reasons.append("execution_plan_provider_baseline_freeze_content_binding_mismatch")
    if not _looks_like_sha256(payload.get("execution_plan_digest_sha256")):
        reasons.append("execution_plan_digest_missing")
    _require_false_flags(payload, prefix="execution_plan", reasons=reasons)


def _validate_acquisition(payload: Mapping[str, Any], reasons: list[str]) -> None:
    if payload.get("schema") != ACQUISITION_SCHEMA or payload.get("ready_to_assemble_manifest") is not True:
        reasons.append("benchmark_acquisition_not_ready")
    if payload.get("official_import_missing_count") != 0:
        reasons.append("benchmark_acquisition_official_imports_missing")
    if payload.get("ready_suite_count") != payload.get("required_suite_count"):
        reasons.append("benchmark_acquisition_suite_count_incomplete")
    _require_false_flags(payload, prefix="benchmark_acquisition", reasons=reasons)


def _validate_import_audit(payload: Mapping[str, Any], reasons: list[str]) -> None:
    if payload.get("schema") != IMPORT_AUDIT_SCHEMA or payload.get("ready_for_campaign_import_stage") is not True:
        reasons.append("official_import_audit_not_ready")
    if payload.get("blocked_official_suite_count") != 0:
        reasons.append("official_import_audit_blocked_suites")
    if payload.get("ready_official_suite_count") != payload.get("official_suite_count"):
        reasons.append("official_import_audit_suite_count_incomplete")
    if not _looks_like_sha256(payload.get("audit_digest_sha256")):
        reasons.append("official_import_audit_digest_missing")
    _require_false_flags(payload, prefix="official_import_audit", reasons=reasons)


def _binding_digest_input(stage_bindings: Mapping[str, Any], declarations: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.composite_harness_cohort_binding_digest.v1",
        "stage_content_sha256": {
            name: str(row.get("content_sha256") or "")
            for name, row in sorted(stage_bindings.items())
            if isinstance(row, Mapping)
        },
        "declarations": dict(declarations),
    }


def _validate_inputs(
    paths: Mapping[str, Path], payloads: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    reasons: list[str] = []
    for name, path in paths.items():
        if not _sha256_file(path):
            reasons.append(f"{name}_content_digest_missing")
    _validate_screening(
        registry_path=paths["registry"],
        plan_path=paths["plan"],
        state_path=paths["state"],
        registry=payloads["registry"],
        plan=payloads["plan"],
        state=payloads["state"],
        reasons=reasons,
    )
    _validate_transport(
        path=paths["transport_admission"],
        payload=payloads["transport_admission"],
        registry_path=paths["registry"],
        plan_path=paths["plan"],
        state_path=paths["state"],
        plan=payloads["plan"],
        state=payloads["state"],
        reasons=reasons,
    )
    _validate_ranking(
        path=paths["ranking"],
        payload=payloads["ranking"],
        registry_path=paths["registry"],
        state_path=paths["state"],
        reasons=reasons,
    )
    _validate_freeze(
        payload=payloads["provider_baseline_freeze"],
        registry_path=paths["registry"],
        transport_path=paths["transport_admission"],
        ranking_path=paths["ranking"],
        reasons=reasons,
    )
    _validate_pin(payloads["harness_pin"], reasons)
    _validate_execution_plan(
        payload=payloads["execution_plan"],
        harness_pin_path=paths["harness_pin"],
        acquisition_path=paths["acquisition_status"],
        provider_baseline_freeze_path=paths["provider_baseline_freeze"],
        reasons=reasons,
    )
    _validate_acquisition(payloads["acquisition_status"], reasons)
    _validate_import_audit(payloads["official_import_audit"], reasons)
    return reasons


def _build_stage_bindings(
    paths: Mapping[str, Path], payloads: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    return {
        name: _artifact_row(
            path,
            payloads[name],
            ready=bool(payloads[name]) and bool(_sha256_file(path)),
            reasons=(),
        )
        for name, path in paths.items()
    }


def _build_declarations(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "screening_plan_digest_sha256": str(
            payloads["plan"].get("plan_digest_sha256") or ""
        ),
        "screening_campaign_digest_sha256": str(
            payloads["state"].get("campaign_digest_sha256") or ""
        ),
        "provider_baseline_freeze_digest_sha256": str(
            payloads["provider_baseline_freeze"].get("freeze_digest_sha256") or ""
        ),
        "execution_plan_digest_sha256": str(
            payloads["execution_plan"].get("execution_plan_digest_sha256") or ""
        ),
        "official_import_audit_digest_sha256": str(
            payloads["official_import_audit"].get("audit_digest_sha256") or ""
        ),
        "target_suite_calls_performed": False,
    }


def build_binding(args: argparse.Namespace) -> dict[str, Any]:
    paths = {name: getattr(args, name) for name in REQUIRED_ARTIFACTS}
    payloads = {
        name: _load_required(path, name=name, reasons=[])
        for name, path in paths.items()
    }
    reasons = _validate_inputs(paths, payloads)

    stage_bindings = _build_stage_bindings(paths, payloads)
    declarations = _build_declarations(payloads)
    digest_input = _binding_digest_input(stage_bindings, declarations)
    binding_digest = _sha256_text(_stable_json(digest_input))
    return {
        "schema": "axio_fusion_api.composite_harness_cohort_binding.v1",
        "status": "ready" if not reasons else "blocked",
        "cohort_binding_digest_sha256": binding_digest,
        "cohort_id_sha256": binding_digest,
        "stage_bindings": stage_bindings,
        "declarations": declarations,
        "binding_digest_input": digest_input,
        "target_suite_calls_allowed": not reasons,
        "target_suite_calls_performed": False,
        "reason_codes": sorted(set(_safe_reason(reason) for reason in reasons if str(reason))),
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    args = _parser().parse_args()
    result = build_binding(args)
    try:
        _write_json(args.output, result)
    except OSError:
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
