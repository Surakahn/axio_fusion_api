#!/usr/bin/env python3
"""持续运行 composite cohort 的离线 lineage 与收敛审计 watcher。

watcher 只读取控制面 artifact：每个周期先重建同一 cohort 的 hash-only binding，
再运行收敛审计。它不调用 provider、不修改 frozen plan、不恢复 screening，也不
启动 target Harness。screening 仍在运行时会校验 PID 身份；screening 进入终态后，
默认输出一次最终快照并退出，后续 successor 或 target campaign 仍由明确的下一步
操作负责。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import audit_composite_convergence as convergence_audit
import build_composite_harness_binding as cohort_binding


TERMINAL_SCREENING_STATUSES = frozenset({"completed", "partial", "blocked", "failed"})
SCREENING_PROCESS_MARKER = "baseline-screening-run"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening-pid", required=True, type=int)
    parser.add_argument("--screening-command-fragment", required=True)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--transport-admission", required=True, type=Path)
    parser.add_argument("--ranking", required=True, type=Path)
    parser.add_argument("--provider-baseline-freeze", required=True, type=Path)
    parser.add_argument("--harness-pin", required=True, type=Path)
    parser.add_argument("--execution-plan", required=True, type=Path)
    parser.add_argument("--acquisition-status", required=True, type=Path)
    parser.add_argument("--official-import-audit", required=True, type=Path)
    parser.add_argument("--cohort-binding", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    parser.add_argument("--target-campaign", type=Path)
    parser.add_argument("--final-audit", type=Path)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    return parser


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _proc_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _process_matches(command: str, expected_fragment: str) -> bool:
    return bool(
        command
        and SCREENING_PROCESS_MARKER in command
        and expected_fragment in command
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _binding_args(args: argparse.Namespace) -> argparse.Namespace:
    return SimpleNamespace(
        registry=args.registry,
        plan=args.plan,
        state=args.state,
        transport_admission=args.transport_admission,
        ranking=args.ranking,
        provider_baseline_freeze=args.provider_baseline_freeze,
        harness_pin=args.harness_pin,
        execution_plan=args.execution_plan,
        acquisition_status=args.acquisition_status,
        official_import_audit=args.official_import_audit,
        output=args.cohort_binding,
    )


def _audit_args(args: argparse.Namespace) -> argparse.Namespace:
    return SimpleNamespace(
        registry=args.registry,
        plan=args.plan,
        state=args.state,
        transport_admission=args.transport_admission,
        ranking=args.ranking,
        provider_baseline_freeze=args.provider_baseline_freeze,
        harness_pin=args.harness_pin,
        execution_plan=args.execution_plan,
        acquisition_status=args.acquisition_status,
        official_import_audit=args.official_import_audit,
        cohort_binding=args.cohort_binding,
        target_campaign=args.target_campaign,
        final_audit=args.final_audit,
        output=args.audit_output,
    )


def _emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=True, sort_keys=True), flush=True)


def _run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    binding_payload = cohort_binding.build_binding(_binding_args(args))
    _atomic_write_json(args.cohort_binding, binding_payload)
    audit_payload = convergence_audit.audit_cohort(_audit_args(args))
    _atomic_write_json(args.audit_output, audit_payload)
    _emit(
        "convergence_snapshot",
        status=audit_payload.get("status"),
        next_gate=audit_payload.get("next_gate"),
        target_suite_calls_allowed=audit_payload.get("target_suite_calls_allowed"),
        final_claim_allowed=audit_payload.get("final_claim_allowed"),
        reason_codes=audit_payload.get("reason_codes", []),
        binding_status=binding_payload.get("status"),
        target_suite_calls_performed=binding_payload.get("target_suite_calls_performed"),
    )
    return audit_payload


def _require_screening_identity(args: argparse.Namespace) -> None:
    command = _proc_cmdline(args.screening_pid)
    if not _process_matches(command, args.screening_command_fragment):
        raise RuntimeError("screening_pid_identity_check_failed")


def main() -> int:
    args = _parser().parse_args()
    interval = max(1.0, float(args.interval_seconds))
    while True:
        state = _read_object(args.state)
        screening_status = str(state.get("status") or "")
        if screening_status not in TERMINAL_SCREENING_STATUSES:
            try:
                _require_screening_identity(args)
            except RuntimeError as exc:
                _emit("watcher_blocked", error_code=str(exc))
                return 2
        try:
            audit_payload = _run_cycle(args)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            _emit("watcher_cycle_failed", error_code=type(exc).__name__)
            return 2
        if args.once:
            return 0
        state = _read_object(args.state)
        screening_status = str(state.get("status") or "")
        if screening_status in TERMINAL_SCREENING_STATUSES:
            _emit("screening_terminal", status=screening_status)
            return 0
        if audit_payload.get("status") in {"ready_for_target_campaign", "ready"}:
            _emit("watcher_stop", status=audit_payload.get("status"))
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
