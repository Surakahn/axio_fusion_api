#!/usr/bin/env python3
"""为 composite cohort 准备可审计的 Harness 控制面。

本脚本只执行本地、离线的 checklist/template/status/audit 生成。它不会访问
provider，不会修改 screening plan，不会恢复 live screening，也不会授权 target
benchmark。所有输出均使用原子替换，并把 cohort 输入和 stage 结果保存为 hash-only
receipt，便于 screening 终态后继续推进同一条 lineage。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCRIPT_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_ROOT.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from axio_fusion_api.evaluation import (  # noqa: E402
    build_benchmark_acquisition_checklist,
    build_benchmark_acquisition_status,
    build_benchmark_harness_pin_manifest,
    build_official_harness_execution_plan,
    build_official_import_audit,
    build_official_import_batch_template,
)
import audit_composite_convergence as convergence_audit  # noqa: E402
import build_composite_harness_binding as cohort_binding  # noqa: E402


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PIN_SCHEMA = "axio_fusion_api.benchmark_harness_pin_manifest.v1"
CHECKLIST_SCHEMA = "axio_fusion_api.benchmark_acquisition_checklist.v1"
IMPORT_TEMPLATE_SCHEMA = "axio_fusion_api.official_import_batch_template.v1"
ACQUISITION_SCHEMA = "axio_fusion_api.benchmark_acquisition_status.v1"
EXECUTION_SCHEMA = "axio_fusion_api.official_harness_execution_plan.v1"
IMPORT_AUDIT_SCHEMA = "axio_fusion_api.official_import_audit.v1"
SENSITIVE_FIELDS = (
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
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--transport-admission", required=True, type=Path)
    parser.add_argument("--ranking", required=True, type=Path)
    parser.add_argument("--provider-baseline-freeze", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--harness-root", type=Path)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--bfcl-harness-root", type=Path)
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/benchmarks"))
    parser.add_argument("--safe-import-dir", type=Path, default=Path("outputallresult/fusion_api_product/imports"))
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--case-hash-manifest", type=Path)
    parser.add_argument("--min-cases-per-suite", type=int, default=100)
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


def _safe_reason(value: Any) -> str:
    token = "".join(char if char.isalnum() or char in "_.:-" else "_" for char in str(value))
    return token[:128] or "artifact_invalid"


def _read_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _sensitive_values_are_safe(payload: Mapping[str, Any]) -> bool:
    return all(payload.get(field) is not True for field in SENSITIVE_FIELDS)


def _blocked_artifact(schema: str, *reasons: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": schema,
        "status": "blocked",
        "reason_codes": sorted({_safe_reason(reason) for reason in reasons}),
    }
    payload.update({field: False for field in SENSITIVE_FIELDS})
    return payload


def _optional_path(path: Path | None) -> Path | None:
    return path if path is not None and path.is_file() else None


def _freeze_path(path: Path) -> Path | None:
    return _optional_path(path)


def _call_stage(
    schema: str,
    builder: Callable[[], Mapping[str, Any]],
    *,
    missing_reason: str,
) -> dict[str, Any]:
    try:
        payload = dict(builder())
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return _blocked_artifact(schema, missing_reason)
    if not payload:
        return _blocked_artifact(schema, missing_reason)
    return payload


def _stage_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "harness_pin": output_dir / "harness_pin_manifest.composite.successor.safe.json",
        "acquisition_checklist": output_dir / "benchmark_acquisition_checklist.composite.successor.safe.json",
        "import_template": output_dir / "benchmark_import_batch_template.composite.successor.safe.json",
        "acquisition_status": output_dir / "benchmark_acquisition_status.composite.successor.safe.json",
        "execution_plan": output_dir / "official_harness_execution_plan.composite.successor.safe.json",
        "official_import_audit": output_dir / "official_import_audit.composite.successor.safe.json",
        "cohort_binding": output_dir / "composite_harness_cohort_binding.successor.safe.json",
        "convergence_audit": output_dir / "composite_convergence_audit.safe.json",
        "receipt": output_dir / "composite_harness_scaffold.safe.json",
    }


def _write_stage(path: Path, payload: Mapping[str, Any]) -> None:
    _write_json_atomic(path, payload)


def _stage_snapshot(name: str, path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    reasons = [
        _safe_reason(reason)
        for reason in payload.get("reason_codes", [])
        if str(reason)
    ]
    sensitive_ok = _sensitive_values_are_safe(payload)
    schema_ok = bool(payload.get("schema"))
    ready = schema_ok and sensitive_ok and not reasons
    if name == "harness_pin":
        ready = ready and (
            payload.get("suite_count") == payload.get("ready_suite_count")
            and payload.get("blocked_suite_count") == 0
            and payload.get("all_paths_hashed_only") is True
        )
    elif name == "acquisition_status":
        ready = ready and (
            payload.get("ready_to_assemble_manifest") is True
            and payload.get("official_import_missing_count") == 0
        )
    elif name == "execution_plan":
        ready = ready and (
            payload.get("status") == "ready_to_execute"
            and payload.get("all_tasks_ready_to_execute") is True
        )
    elif name == "official_import_audit":
        ready = ready and (
            payload.get("ready_for_campaign_import_stage") is True
            and payload.get("blocked_official_suite_count") == 0
        )
    status = "ready" if ready else "blocked"
    if name == "acquisition_checklist" and status == "ready":
        status = "template_ready"
    if name == "import_template" and status == "ready":
        status = "operator_action_required"
        reasons.append("official_import_template_requires_operator_fill")
    return {
        "stage": name,
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "artifact_sha256": _sha256_file(path),
        "path_sha256": _sha256_text(str(path)),
        "schema": str(payload.get("schema") or ""),
    }


def _lineage_args(args: argparse.Namespace, paths: Mapping[str, Path]) -> argparse.Namespace:
    return argparse.Namespace(
        registry=args.registry,
        plan=args.plan,
        state=args.state,
        transport_admission=args.transport_admission,
        ranking=args.ranking,
        provider_baseline_freeze=args.provider_baseline_freeze,
        harness_pin=paths["harness_pin"],
        execution_plan=paths["execution_plan"],
        acquisition_status=paths["acquisition_status"],
        official_import_audit=paths["official_import_audit"],
        output=paths["cohort_binding"],
    )


def _audit_args(args: argparse.Namespace, paths: Mapping[str, Path]) -> argparse.Namespace:
    return argparse.Namespace(
        registry=args.registry,
        plan=args.plan,
        state=args.state,
        transport_admission=args.transport_admission,
        ranking=args.ranking,
        provider_baseline_freeze=args.provider_baseline_freeze,
        harness_pin=paths["harness_pin"],
        execution_plan=paths["execution_plan"],
        acquisition_status=paths["acquisition_status"],
        official_import_audit=paths["official_import_audit"],
        cohort_binding=paths["cohort_binding"],
        target_campaign=None,
        final_audit=None,
        output=paths["convergence_audit"],
    )


def _build_stage_payloads(args: argparse.Namespace, paths: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    freeze = _freeze_path(args.provider_baseline_freeze)
    pin = _call_stage(
        PIN_SCHEMA,
        lambda: build_benchmark_harness_pin_manifest(
            harness_root=args.harness_root,
            raw_root=args.raw_root,
            bfcl_harness_root=args.bfcl_harness_root,
        )
        if args.harness_root is not None and args.raw_root is not None
        else _blocked_artifact(PIN_SCHEMA, "harness_root_and_raw_root_required"),
        missing_reason="harness_pin_generation_failed",
    )
    _write_stage(paths["harness_pin"], pin)

    checklist = _call_stage(
        CHECKLIST_SCHEMA,
        lambda: build_benchmark_acquisition_checklist(
            registry_path=args.registry,
            dataset_manifest_path=_optional_path(args.dataset_manifest),
            base_dir=str(args.dataset_dir),
            import_dir=str(args.safe_import_dir),
            include_provider_baselines=True,
            max_provider_baselines=3,
            provider_baseline_freeze_path=freeze,
            min_cases_per_suite=args.min_cases_per_suite,
        ),
        missing_reason="benchmark_acquisition_checklist_generation_failed",
    )
    _write_stage(paths["acquisition_checklist"], checklist)

    import_template = _call_stage(
        IMPORT_TEMPLATE_SCHEMA,
        lambda: build_official_import_batch_template(
            acquisition_checklist_path=paths["acquisition_checklist"],
            harness_pin_manifest_path=paths["harness_pin"],
        ),
        missing_reason="official_import_template_generation_failed",
    )
    _write_stage(paths["import_template"], import_template)

    acquisition_status = _call_stage(
        ACQUISITION_SCHEMA,
        lambda: build_benchmark_acquisition_status(
            registry_path=args.registry,
            dataset_dir=args.dataset_dir,
            dataset_manifest_path=_optional_path(args.dataset_manifest),
            import_dirs=(args.safe_import_dir,),
            include_provider_baselines=True,
            max_provider_baselines=3,
            provider_baseline_freeze_path=freeze,
            min_cases_per_suite=args.min_cases_per_suite,
        ),
        missing_reason="benchmark_acquisition_status_generation_failed",
    )
    _write_stage(paths["acquisition_status"], acquisition_status)

    execution_plan = _call_stage(
        EXECUTION_SCHEMA,
        lambda: build_official_harness_execution_plan(
            import_batch_template_path=paths["import_template"],
            acquisition_status_path=paths["acquisition_status"],
            harness_pin_manifest_path=paths["harness_pin"],
        ),
        missing_reason="official_harness_execution_plan_generation_failed",
    )
    _write_stage(paths["execution_plan"], execution_plan)

    import_audit = _call_stage(
        IMPORT_AUDIT_SCHEMA,
        lambda: build_official_import_audit(
            dataset_manifest_path=_optional_path(args.dataset_manifest),
            source_manifest_path=_optional_path(args.source_manifest),
            case_hash_manifest_path=_optional_path(args.case_hash_manifest),
            harness_pin_manifest_path=paths["harness_pin"],
            import_dirs=(args.safe_import_dir,),
            registry_path=args.registry,
            include_provider_baselines=True,
            max_provider_baselines=3,
            provider_baseline_freeze_path=freeze,
            min_cases_per_suite=args.min_cases_per_suite,
        ),
        missing_reason="official_import_audit_generation_failed",
    )
    _write_stage(paths["official_import_audit"], import_audit)
    return {
        "harness_pin": pin,
        "acquisition_checklist": checklist,
        "import_template": import_template,
        "acquisition_status": acquisition_status,
        "execution_plan": execution_plan,
        "official_import_audit": import_audit,
    }


def _build_receipt(
    args: argparse.Namespace,
    paths: Mapping[str, Path],
    stages: Mapping[str, Mapping[str, Any]],
    binding: Mapping[str, Any],
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    snapshots = [
        _stage_snapshot(name, paths[name], stages[name])
        for name in (
            "harness_pin",
            "acquisition_checklist",
            "import_template",
            "acquisition_status",
            "execution_plan",
            "official_import_audit",
        )
    ]
    snapshots.extend(
        {
            "stage": name,
            "status": str(payload.get("status") or "blocked"),
            "reason_codes": [
                _safe_reason(reason)
                for reason in payload.get("reason_codes", [])
                if str(reason)
            ],
            "artifact_sha256": _sha256_file(paths[name]),
            "path_sha256": _sha256_text(str(paths[name])),
            "schema": str(payload.get("schema") or ""),
        }
        for name, payload in (
            ("cohort_binding", binding),
            ("convergence_audit", audit),
        )
    )
    state = _read_object(args.state)
    plan = _read_object(args.plan)
    status = str(audit.get("status") or "blocked")
    return {
        "schema": "axio_fusion_api.composite_harness_scaffold.v1",
        "status": status,
        "next_gate": str(audit.get("next_gate") or "screening"),
        "reason_codes": sorted(
            {
                _safe_reason(reason)
                for reason in audit.get("reason_codes", [])
                if str(reason)
            }
        ),
        "screening_plan_digest_sha256": str(plan.get("plan_digest_sha256") or ""),
        "screening_campaign_digest_sha256": str(state.get("campaign_digest_sha256") or ""),
        "cohort_input_bindings": {
            "registry_file_sha256": _sha256_file(args.registry),
            "plan_file_sha256": _sha256_file(args.plan),
            "state_file_sha256": _sha256_file(args.state),
            "transport_admission_file_sha256": _sha256_file(args.transport_admission),
            "ranking_file_sha256": _sha256_file(args.ranking),
            "provider_baseline_freeze_file_sha256": _sha256_file(args.provider_baseline_freeze),
        },
        "stage_statuses": snapshots,
        "cohort_binding_digest_sha256": str(binding.get("cohort_binding_digest_sha256") or ""),
        "convergence_audit_status": status,
        "target_suite_calls_allowed": False,
        "target_suite_calls_performed": False,
        "provider_calls_performed": False,
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def run_scaffold(args: argparse.Namespace) -> dict[str, Any]:
    paths = _stage_paths(args.output_dir)
    stages = _build_stage_payloads(args, paths)
    binding = cohort_binding.build_binding(_lineage_args(args, paths))
    _write_stage(paths["cohort_binding"], binding)
    audit = convergence_audit.audit_cohort(_audit_args(args, paths))
    _write_stage(paths["convergence_audit"], audit)
    receipt = _build_receipt(args, paths, stages, binding, audit)
    _write_stage(paths["receipt"], receipt)
    return receipt


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = run_scaffold(args)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return 2
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] in {"ready_for_target_campaign", "ready"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
