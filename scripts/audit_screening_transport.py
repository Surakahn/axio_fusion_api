#!/usr/bin/env python3
"""对已终态的 screening unit 做零网络、hash-safe transport 根因审计。

该工具只读取 operator-owned private unit 的结构化状态和 failure telemetry
计数，不读取或输出 raw provider output、prompt、label、URL、model id 或 secret。
它不会启动 provider 请求、恢复 checkpoint、修改 frozen plan 或授权 target
benchmark。``status=ready`` 只表示审计输入自洽；transport admission 是否通过由
``transport_admission_status`` 单独表达。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


CAMPAIGN_SCHEMA = "axio_fusion_api.non_target_screening_campaign.v3"
PLAN_SCHEMA = "axio_fusion_api.non_target_screening_plan.v3"
TRANSPORT_SCHEMA = "axio_fusion_api.non_target_screening_transport_admission.v1"
UNIT_SCHEMA = "axio_fusion_api.non_target_screening_unit_private.v1"
AUDIT_SCHEMA = "axio_fusion_api.non_target_screening_transport_root_cause_audit.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UNIT_FILENAME_RE = re.compile(r"^[0-9a-f]{64}\.private\.json$")
SAFE_REASON_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class AuditInputError(ValueError):
    """表示输入缺失、绑定漂移或 private unit 结构不满足审计契约。"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--campaign-state", required=True, type=Path)
    parser.add_argument("--transport-admission", required=True, type=Path)
    parser.add_argument(
        "--unit-root",
        required=True,
        type=Path,
        help="只包含 screening unit private artifacts 的 operator-owned 目录。",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AuditInputError("transport_audit_input_unreadable") from exc
    return digest.hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _read_object(path: Path, *, error_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditInputError(error_code) from exc
    if not isinstance(value, Mapping):
        raise AuditInputError(f"{error_code}_object_required")
    return dict(value)


def _required_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuditInputError(error_code)
    return value


def _required_ratio(value: Any, *, error_code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditInputError(error_code)
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise AuditInputError(error_code)
    return parsed


def _sha256_alias(value: Any) -> str:
    token = str(value or "")
    return token if SHA256_RE.fullmatch(token) else _sha256_text(token)


def _required_identity(value: Any, *, error_code: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise AuditInputError(error_code)
    return _sha256_alias(token)


def _count_rows(rows: Mapping[str, int], *, key: str) -> list[dict[str, Any]]:
    return [{key: item, "count": rows[item]} for item in sorted(rows)]


def _telemetry_counts(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    telemetry = row.get("failure_telemetry")
    if not isinstance(telemetry, Mapping):
        raise AuditInputError("transport_audit_case_failure_telemetry_missing")
    attempt_count = _required_int(
        telemetry.get("attempt_count"),
        error_code="transport_audit_attempt_count_invalid",
    )
    failed_attempt_count = _required_int(
        telemetry.get("failed_attempt_count"),
        error_code="transport_audit_failed_attempt_count_invalid",
    )
    retry_round_count = _required_int(
        telemetry.get("retry_round_count"),
        error_code="transport_audit_retry_round_count_invalid",
    )
    retryable_failed_count = _required_int(
        telemetry.get("retryable_failed_attempt_count"),
        error_code="transport_audit_retryable_failure_count_invalid",
    )
    if failed_attempt_count > attempt_count:
        raise AuditInputError("transport_audit_failure_attempt_count_invalid")
    if retryable_failed_count > failed_attempt_count:
        raise AuditInputError("transport_audit_retryable_failure_count_exceeds_failures")
    retry_receipts = telemetry.get("retry_receipts")
    if not isinstance(retry_receipts, list) or len(retry_receipts) != retry_round_count:
        raise AuditInputError("transport_audit_retry_receipts_invalid")
    failure_class_counts: Counter[str] = Counter()
    provider_error_counts: Counter[str] = Counter()
    http_status_counts: Counter[str] = Counter()
    fail_fast_reason_counts: Counter[str] = Counter()
    for field, output_key in (
        ("transport_failure_class_counts", "transport_failure_class"),
        ("provider_error_code_counts", "provider_error_code"),
        ("http_status_counts", "http_status"),
    ):
        rows = telemetry.get(field)
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
            raise AuditInputError("transport_audit_failure_telemetry_rows_invalid")
        for item in rows:
            if not isinstance(item, Mapping):
                raise AuditInputError("transport_audit_failure_telemetry_row_invalid")
            key = str(item.get(output_key) or "")
            count = _required_int(
                item.get("count"),
                error_code="transport_audit_failure_telemetry_count_invalid",
            )
            if not key or count < 1:
                raise AuditInputError("transport_audit_failure_telemetry_value_invalid")
            if output_key == "http_status":
                if not re.fullmatch(r"[1-5][0-9]{2}", key):
                    raise AuditInputError("transport_audit_http_status_invalid")
                http_status_counts[key] += count
            elif output_key == "transport_failure_class":
                if not SAFE_REASON_RE.fullmatch(key):
                    raise AuditInputError("transport_audit_failure_class_invalid")
                failure_class_counts[key] += count
            else:
                if not SAFE_REASON_RE.fullmatch(key):
                    raise AuditInputError("transport_audit_provider_error_code_invalid")
                provider_error_counts[key] += count
        expected = sum(
            _required_int(
                item.get("count"),
                error_code="transport_audit_failure_telemetry_count_invalid",
            )
            for item in rows
            if isinstance(item, Mapping)
        )
        if output_key == "transport_failure_class" and expected != failed_attempt_count:
            raise AuditInputError("transport_audit_failure_class_count_mismatch")
        if output_key != "transport_failure_class" and expected > failed_attempt_count:
            raise AuditInputError("transport_audit_failure_telemetry_count_exceeds_failures")
    return {
        "attempt_count": attempt_count,
        "failed_attempt_count": failed_attempt_count,
        "retry_round_count": retry_round_count,
        "retryable_failed_attempt_count": retryable_failed_count,
        "failure_class_counts": failure_class_counts,
        "provider_error_counts": provider_error_counts,
        "http_status_counts": http_status_counts,
    }


def _audit_unit(path: Path) -> dict[str, Any]:
    payload = _read_object(path, error_code="transport_audit_unit_read_failed")
    if payload.get("schema") != UNIT_SCHEMA:
        raise AuditInputError("transport_audit_unit_schema_invalid")
    source_hash = _required_identity(
        payload.get("source_id"),
        error_code="transport_audit_source_identity_missing",
    )
    canonical_hash = _required_identity(
        payload.get("canonical_identity_sha256"),
        error_code="transport_audit_canonical_identity_missing",
    )
    task_hash = _required_identity(
        payload.get("task_id"),
        error_code="transport_audit_task_identity_missing",
    )
    rows = payload.get("case_results")
    if not isinstance(rows, list) or not rows:
        raise AuditInputError("transport_audit_unit_case_results_missing")
    status_counts: Counter[str] = Counter()
    failure_class_counts: Counter[str] = Counter()
    provider_error_counts: Counter[str] = Counter()
    http_status_counts: Counter[str] = Counter()
    fail_fast_reason_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    fail_fast_count = 0
    provider_attempt_count = 0
    failed_attempt_count = 0
    retry_round_count = 0
    retryable_failed_count = 0
    recovered_case_count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise AuditInputError("transport_audit_case_row_invalid")
        status = str(row.get("status") or "")
        if not SAFE_REASON_RE.fullmatch(status):
            raise AuditInputError("transport_audit_case_status_invalid")
        status_counts[status] += 1
        fail_fast = row.get("fail_fast_unattempted", False)
        if not isinstance(fail_fast, bool):
            raise AuditInputError("transport_audit_fail_fast_flag_invalid")
        if fail_fast:
            fail_fast_count += 1
        if "failure_telemetry" not in row:
            if not fail_fast or status != "transport_failed":
                raise AuditInputError("transport_audit_case_failure_telemetry_missing")
            fail_fast_reason = str(row.get("transport_failure_class") or "")
            if not SAFE_REASON_RE.fullmatch(fail_fast_reason):
                raise AuditInputError("transport_audit_fail_fast_reason_invalid")
            fail_fast_reason_counts[fail_fast_reason] += 1
            telemetry = {
                "attempt_count": 0,
                "failed_attempt_count": 0,
                "retry_round_count": 0,
                "retryable_failed_attempt_count": 0,
                "failure_class_counts": Counter(),
                "provider_error_counts": Counter(),
                "http_status_counts": Counter(),
            }
        else:
            telemetry = _telemetry_counts(row)
        attempt_count = telemetry["attempt_count"]
        failed_count = telemetry["failed_attempt_count"]
        provider_attempt_count += attempt_count
        failed_attempt_count += failed_count
        retry_round_count += telemetry["retry_round_count"]
        retryable_failed_count += telemetry["retryable_failed_attempt_count"]
        failure_class_counts.update(telemetry["failure_class_counts"])
        provider_error_counts.update(telemetry["provider_error_counts"])
        http_status_counts.update(telemetry["http_status_counts"])
        group_counts["case_count"] += 1
        group_counts[f"status:{status}"] += 1
        group_counts["provider_attempt_count"] += attempt_count
        group_counts["failed_attempt_count"] += failed_count
        group_counts["retry_round_count"] += telemetry["retry_round_count"]
        group_counts["retryable_failed_attempt_count"] += telemetry[
            "retryable_failed_attempt_count"
        ]
        if fail_fast:
            group_counts["fail_fast_unattempted_case_count"] += 1
        if status == "completed" and failed_count > 0:
            recovered_case_count += 1
    group_counts["recovered_transport_failure_case_count"] = recovered_case_count
    for key, counter in (
        ("failure_class", failure_class_counts),
        ("provider_error", provider_error_counts),
        ("http_status", http_status_counts),
        ("fail_fast_reason", fail_fast_reason_counts),
    ):
        for item, count in counter.items():
            group_counts[f"{key}:{item}"] = count
    return {
        "task_id_sha256": task_hash,
        "source_id_sha256": source_hash,
        "canonical_identity_sha256": canonical_hash,
        "case_count": len(rows),
        "completed_case_count": status_counts.get("completed", 0),
        "transport_failed_case_count": status_counts.get("transport_failed", 0),
        "fail_fast_unattempted_case_count": fail_fast_count,
        "provider_attempt_count": provider_attempt_count,
        "failed_attempt_count": failed_attempt_count,
        "retry_round_count": retry_round_count,
        "retryable_failed_attempt_count": retryable_failed_count,
        "recovered_transport_failure_case_count": recovered_case_count,
        "transport_failure_rate": round(
            status_counts.get("transport_failed", 0) / len(rows),
            12,
        ),
        "status_counts": [
            {"status": key, "count": status_counts[key]}
            for key in sorted(status_counts)
        ],
        "failure_class_counts": failure_class_counts,
        "provider_error_counts": provider_error_counts,
        "http_status_counts": http_status_counts,
        "fail_fast_reason_counts": fail_fast_reason_counts,
        "group_counts": group_counts,
        "private_unit_file_sha256": _sha256_file(path),
    }


def _validate_binding(
    *,
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    transport: Mapping[str, Any],
    plan_path: Path,
    state_path: Path,
    transport_path: Path,
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema") != PLAN_SCHEMA:
        reasons.append("transport_audit_plan_schema_invalid")
    if plan.get("ready") is not True:
        reasons.append("transport_audit_plan_not_ready")
    if state.get("schema") != CAMPAIGN_SCHEMA:
        reasons.append("transport_audit_campaign_schema_invalid")
    if state.get("status") not in {"completed", "partial", "blocked", "failed"}:
        reasons.append("transport_audit_campaign_not_terminal")
    if state.get("network_calls_performed") is not True:
        reasons.append("transport_audit_campaign_not_live")
    if state.get("target_suite_calls_performed") is not False:
        reasons.append("transport_audit_target_suite_calls_present")
    if transport.get("schema") != TRANSPORT_SCHEMA:
        reasons.append("transport_audit_transport_schema_invalid")
    if transport.get("status") not in {"ready", "blocked"}:
        reasons.append("transport_audit_transport_status_invalid")
    plan_file_hash = _sha256_file(plan_path)
    state_file_hash = _sha256_file(state_path)
    if transport.get("source_plan_file_sha256") != plan_file_hash:
        reasons.append("transport_audit_plan_file_binding_mismatch")
    if transport.get("source_campaign_state_file_sha256") != state_file_hash:
        reasons.append("transport_audit_state_file_binding_mismatch")
    plan_digest = str(plan.get("plan_digest_sha256") or "")
    if plan_digest and state.get("plan_digest_sha256") != plan_digest:
        reasons.append("transport_audit_state_plan_digest_mismatch")
    if plan_digest and transport.get("plan_digest_sha256") != plan_digest:
        reasons.append("transport_audit_transport_plan_digest_mismatch")
    campaign_status = state.get("status")
    if transport.get("campaign_status") not in {None, campaign_status}:
        reasons.append("transport_audit_campaign_status_mismatch")
    if transport.get("selection_basis") != "transport_failure_rate_only":
        reasons.append("transport_audit_selection_basis_invalid")
    if transport.get("quality_fields_used_for_selection") not in ([], None):
        reasons.append("transport_audit_quality_selection_present")
    return reasons


def _validate_admission_consistency(
    admission: Mapping[str, Any], units: Sequence[Mapping[str, Any]]
) -> list[str]:
    expected = {
        (
            str(unit["task_id_sha256"]),
            str(unit["source_id_sha256"]),
            str(unit["canonical_identity_sha256"]),
        ): unit
        for unit in units
    }
    rows = admission.get("unit_transport_evidence")
    if not isinstance(rows, list):
        return ["transport_audit_unit_transport_evidence_missing"]
    actual_rows = [row for row in rows if isinstance(row, Mapping)]
    if len(actual_rows) != len(rows):
        return ["transport_audit_unit_transport_evidence_row_invalid"]
    actual = {
        (
            str(row.get("task_id_sha256") or ""),
            str(row.get("source_id_sha256") or ""),
            str(row.get("canonical_identity_sha256") or ""),
        ): row
        for row in actual_rows
    }
    reasons: list[str] = []
    if len(actual) != len(actual_rows):
        reasons.append("transport_audit_unit_transport_evidence_duplicate")
    if set(actual) != set(expected):
        reasons.append("transport_audit_unit_identity_set_mismatch")
        return reasons
    for identity, unit in expected.items():
        row = actual[identity]
        try:
            failure_count = _required_int(
                row.get("transport_failure_count"),
                error_code="transport_audit_transport_failure_count_invalid",
            )
            fail_fast_count = _required_int(
                row.get("fail_fast_unattempted_case_count"),
                error_code="transport_audit_fail_fast_count_invalid",
            )
            observed = _required_ratio(
                row.get("transport_failure_rate"),
                error_code="transport_audit_transport_failure_rate_invalid",
            )
        except AuditInputError as exc:
            reasons.append(str(exc))
            continue
        if failure_count != unit["transport_failed_case_count"]:
            reasons.append("transport_audit_transport_failure_count_mismatch")
        if fail_fast_count != unit["fail_fast_unattempted_case_count"]:
            reasons.append("transport_audit_fail_fast_count_mismatch")
        if abs(observed - unit["transport_failure_rate"]) > 1e-9:
            reasons.append("transport_audit_transport_failure_rate_mismatch")
    return sorted(set(reasons))


def _safe_group_rows(groups: Mapping[str, Counter[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for identity in sorted(groups):
        counts = groups[identity]
        failure_classes = {
            key.removeprefix("failure_class:"): value
            for key, value in counts.items()
            if key.startswith("failure_class:")
        }
        provider_errors = {
            key.removeprefix("provider_error:"): value
            for key, value in counts.items()
            if key.startswith("provider_error:")
        }
        http_statuses = {
            key.removeprefix("http_status:"): value
            for key, value in counts.items()
            if key.startswith("http_status:")
        }
        fail_fast_reasons = {
            key.removeprefix("fail_fast_reason:"): value
            for key, value in counts.items()
            if key.startswith("fail_fast_reason:")
        }
        rows.append(
            {
                "identity_sha256": identity,
                "case_count": counts.get("case_count", 0),
                "completed_case_count": counts.get("status:completed", 0),
                "transport_failed_case_count": counts.get("status:transport_failed", 0),
                "fail_fast_unattempted_case_count": counts.get(
                    "fail_fast_unattempted_case_count", 0
                ),
                "provider_attempt_count": counts.get("provider_attempt_count", 0),
                "failed_attempt_count": counts.get("failed_attempt_count", 0),
                "retry_round_count": counts.get("retry_round_count", 0),
                "recovered_transport_failure_case_count": counts.get(
                    "recovered_transport_failure_case_count", 0
                ),
                "failure_class_counts": _count_rows(
                    failure_classes,
                    key="transport_failure_class",
                ),
                "provider_error_code_counts": _count_rows(
                    provider_errors,
                    key="provider_error_code",
                ),
                "http_status_counts": _count_rows(
                    http_statuses,
                    key="http_status",
                ),
                "fail_fast_reason_counts": _count_rows(
                    fail_fast_reasons,
                    key="transport_failure_class",
                ),
            }
        )
    return rows


def _try_read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _add_group_counts(target: Counter[str], source: Counter[str]) -> None:
    for key, value in source.items():
        target[key] += value


def _safe_unit_summary(unit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in unit.items()
        if key not in {
            "failure_class_counts",
            "provider_error_counts",
            "http_status_counts",
            "fail_fast_reason_counts",
            "group_counts",
        }
    } | {
        "failure_class_counts": _count_rows(
            unit["failure_class_counts"], key="transport_failure_class"
        ),
        "provider_error_code_counts": _count_rows(
            unit["provider_error_counts"], key="provider_error_code"
        ),
        "http_status_counts": _count_rows(
            unit["http_status_counts"], key="http_status"
        ),
        "fail_fast_reason_counts": _count_rows(
            unit["fail_fast_reason_counts"], key="transport_failure_class"
        ),
    }


def audit_transport(
    *,
    plan_path: Path,
    campaign_state_path: Path,
    transport_admission_path: Path,
    unit_root: Path,
) -> dict[str, Any]:
    """生成 hash-only transport 根因审计 receipt。"""

    plan = _read_object(plan_path, error_code="transport_audit_plan_read_failed")
    state = _read_object(campaign_state_path, error_code="transport_audit_state_read_failed")
    admission = _read_object(
        transport_admission_path,
        error_code="transport_audit_transport_read_failed",
    )
    if not unit_root.is_dir():
        raise AuditInputError("transport_audit_unit_root_missing")
    # 先按 immutable unit 文件名筛选，再打开文件；这样不会为了寻找 unit
    # 而读取 checkpoint、日志投影或其它 private artifact 的内容。
    paths = sorted(
        path
        for path in unit_root.rglob("*")
        if path.is_file() and UNIT_FILENAME_RE.fullmatch(path.name)
    )
    units: list[dict[str, Any]] = []
    global_counts: Counter[str] = Counter()
    source_counts: dict[str, Counter[str]] = {}
    canonical_counts: dict[str, Counter[str]] = {}
    global_failure_classes: Counter[str] = Counter()
    global_provider_errors: Counter[str] = Counter()
    global_http: Counter[str] = Counter()
    global_fail_fast_reasons: Counter[str] = Counter()
    identities: set[tuple[str, str, str]] = set()
    for path in paths:
        candidate = _try_read_object(path)
        if candidate is None or candidate.get("schema") != UNIT_SCHEMA:
            raise AuditInputError("transport_audit_unit_filename_schema_mismatch")
        unit = _audit_unit(path)
        identity = (
            unit["task_id_sha256"],
            unit["source_id_sha256"],
            unit["canonical_identity_sha256"],
        )
        if identity in identities:
            raise AuditInputError("transport_audit_duplicate_unit_identity")
        identities.add(identity)
        units.append(unit)
    if not units:
        raise AuditInputError("transport_audit_no_screening_units")
    reasons = _validate_binding(
        plan=plan,
        state=state,
        transport=admission,
        plan_path=plan_path,
        state_path=campaign_state_path,
        transport_path=transport_admission_path,
    )
    reasons.extend(_validate_admission_consistency(admission, units))
    expected_unit_count = _required_int(
        state.get("selected_task_count"),
        error_code="transport_audit_selected_task_count_invalid",
    )
    if expected_unit_count != len(units):
        reasons.append("transport_audit_unit_count_mismatch")
    for unit in units:
        for key in (
            "case_count",
            "completed_case_count",
            "transport_failed_case_count",
            "fail_fast_unattempted_case_count",
            "provider_attempt_count",
            "failed_attempt_count",
            "retry_round_count",
            "retryable_failed_attempt_count",
            "recovered_transport_failure_case_count",
        ):
            global_counts[key] += unit[key]
        global_failure_classes.update(unit["failure_class_counts"])
        global_provider_errors.update(unit["provider_error_counts"])
        global_http.update(unit["http_status_counts"])
        global_fail_fast_reasons.update(unit["fail_fast_reason_counts"])
        source_counts.setdefault(unit["source_id_sha256"], Counter())
        canonical_counts.setdefault(unit["canonical_identity_sha256"], Counter())
        _add_group_counts(source_counts[unit["source_id_sha256"]], unit["group_counts"])
        _add_group_counts(canonical_counts[unit["canonical_identity_sha256"]], unit["group_counts"])
    admission_rows = admission.get("unit_transport_evidence")
    completed_unit_count = sum(
        1
        for row in admission_rows or []
        if isinstance(row, Mapping) and row.get("status") == "completed"
    )
    if state.get("completed_unit_count") != completed_unit_count:
        reasons.append("transport_audit_completed_unit_count_mismatch")
    unit_file_hashes = sorted(str(unit["private_unit_file_sha256"]) for unit in units)
    payload = {
        "schema": AUDIT_SCHEMA,
        "status": "ready" if not reasons else "blocked",
        "reason_codes": sorted(set(reasons)),
        "transport_admission_status": str(admission.get("status") or ""),
        "transport_admission_blockers": [
            str(item)
            for item in admission.get("blockers", [])
            if SAFE_REASON_RE.fullmatch(str(item))
        ],
        "plan_digest_sha256": str(plan.get("plan_digest_sha256") or ""),
        "plan_file_sha256": _sha256_file(plan_path),
        "campaign_state_file_sha256": _sha256_file(campaign_state_path),
        "transport_admission_file_sha256": _sha256_file(transport_admission_path),
        "unit_file_set_sha256": _sha256_text(_stable_json(unit_file_hashes)),
        "unit_count": len(units),
        "case_count": global_counts["case_count"],
        "completed_case_count": global_counts["completed_case_count"],
        "transport_failed_case_count": global_counts["transport_failed_case_count"],
        "fail_fast_unattempted_case_count": sum(
            unit["fail_fast_unattempted_case_count"] for unit in units
        ),
        "provider_attempt_count": sum(unit["provider_attempt_count"] for unit in units),
        "failed_attempt_count": sum(unit["failed_attempt_count"] for unit in units),
        "retry_round_count": sum(unit["retry_round_count"] for unit in units),
        "retryable_failed_attempt_count": sum(
            unit["retryable_failed_attempt_count"] for unit in units
        ),
        "recovered_transport_failure_case_count": sum(
            unit["recovered_transport_failure_case_count"] for unit in units
        ),
        "failure_class_counts": _count_rows(
            global_failure_classes,
            key="transport_failure_class",
        ),
        "provider_error_code_counts": _count_rows(
            global_provider_errors,
            key="provider_error_code",
        ),
        "http_status_counts": _count_rows(
            global_http,
            key="http_status",
        ),
        "fail_fast_reason_counts": _count_rows(
            global_fail_fast_reasons,
            key="transport_failure_class",
        ),
        "units": [_safe_unit_summary(unit) for unit in units],
        "source_groups": _safe_group_rows(source_counts),
        "canonical_groups": _safe_group_rows(canonical_counts),
        "network_calls_performed": False,
        "target_suite_calls_performed": False,
        "raw_provider_outputs_persisted": False,
        "raw_prompts_persisted": False,
        "raw_labels_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise AuditInputError("transport_audit_atomic_write_failed") from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = audit_transport(
            plan_path=args.plan,
            campaign_state_path=args.campaign_state,
            transport_admission_path=args.transport_admission,
            unit_root=args.unit_root,
        )
        _write_json_atomic(args.output, payload)
    except (AuditInputError, OSError, TypeError, ValueError) as exc:
        payload = {
            "schema": AUDIT_SCHEMA,
            "status": "blocked",
            "reason_codes": [
                str(exc) if SAFE_REASON_RE.fullmatch(str(exc)) else "transport_audit_failed"
            ],
            "network_calls_performed": False,
            "target_suite_calls_performed": False,
            "raw_provider_outputs_persisted": False,
            "raw_prompts_persisted": False,
            "raw_labels_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "secrets_persisted": False,
        }
        try:
            _write_json_atomic(args.output, payload)
        except (AuditInputError, OSError) as write_error:
            sys.stderr.write(f"transport audit receipt write failed: {write_error}\n")
        json.dump(payload, sys.stdout, ensure_ascii=True, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(payload, sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if payload.get("status") == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
