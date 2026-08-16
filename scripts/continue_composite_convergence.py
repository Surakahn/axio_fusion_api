#!/usr/bin/env python3
"""安全推进一个冻结的 composite screening cohort 到下一个门禁。

监督器只承担窄范围的终态编排：观察一个已经运行的
``baseline-screening-run`` 进程，校验它仍然持有预期 frozen plan，等待 terminal
campaign state，然后按顺序执行两个允许的离线转换：transport admission 和
screening-to-ranking。它不会编辑 plan、重试 case、启动 target benchmark 流量，
也不会虚构 successor cohort。

本工具产生的 receipt 只包含 hash；CLI 私有日志保留在 operator-owned run root
下，不得直接发布。
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATUSES = frozenset({"completed", "partial", "blocked", "failed"})
DEFAULT_INTERVAL_SECONDS = 300.0
DEFAULT_MAX_TRANSPORT_FAILURE_RATE = 0.02
DEFAULT_MIN_CANONICAL_MODELS = 3
SCREENING_PROCESS_MARKER = "baseline-screening-run"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--private-probe-file", action="append", required=True)
    parser.add_argument("--operational-admission-file", type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--screening-output", required=True, type=Path)
    parser.add_argument("--transport-admission-output", required=True, type=Path)
    parser.add_argument("--ranking-output", required=True, type=Path)
    parser.add_argument("--receipt-output", required=True, type=Path)
    parser.add_argument("--lock-file", required=True, type=Path)
    parser.add_argument(
        "--command-fragment",
        default="baseline_screening_plan.composite.private.json",
        help="观察到的进程命令行必须持续包含的片段。",
    )
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument(
        "--max-transport-failure-rate",
        type=float,
        default=DEFAULT_MAX_TRANSPORT_FAILURE_RATE,
    )
    parser.add_argument(
        "--min-canonical-models",
        type=int,
        default=DEFAULT_MIN_CANONICAL_MODELS,
    )
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


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


def _emit(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True), flush=True)


def _emit_screening_progress(state_path: Path, state: Mapping[str, Any]) -> None:
    """输出低频 hash-only 进度事件，不暴露私有 case 内容。"""

    _emit(
        "screening_progress",
        status=str(state.get("status") or ""),
        completed_unit_count=state.get("completed_unit_count"),
        failed_or_blocked_unit_count=state.get("failed_or_blocked_unit_count"),
        planned_task_count=state.get("planned_task_count"),
        target_suite_calls_performed=state.get("target_suite_calls_performed"),
        state_file_sha256=_sha256_file(state_path),
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _wait_for_terminal_state(
    *, pid: int, expected_fragment: str, state_path: Path, interval_seconds: float
) -> dict[str, Any]:
    """等待但不恢复或复制进程。

    进程消失而 state 仍非 terminal 是明确阻塞。operator 必须检查私有 checkpoint
    并决定是否需要新的 successor plan；本工具不得静默恢复旧进程。
    """

    state = _read_json(state_path)
    if state.get("status") in TERMINAL_STATUSES:
        _emit_screening_progress(state_path, state)
        _emit("screening_already_terminal", status=state.get("status"))
        return state

    command = _proc_cmdline(pid)
    if not _process_matches(command, expected_fragment):
        raise RuntimeError("screening_pid_identity_check_failed")
    _emit("screening_wait_started", pid=pid, command_fragment_sha256=_sha256_text(expected_fragment))

    interval = max(1.0, float(interval_seconds))
    while True:
        state = _read_json(state_path)
        if state.get("status") in TERMINAL_STATUSES:
            _emit_screening_progress(state_path, state)
            return state
        command = _proc_cmdline(pid)
        if not command:
            raise RuntimeError("screening_process_exited_before_terminal_state")
        if not _process_matches(command, expected_fragment):
            raise RuntimeError("screening_pid_reused_or_command_changed")
        _emit_screening_progress(state_path, state)
        time.sleep(interval)


def _run_cli(arguments: Sequence[str], *, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "axio_fusion_api.cli", *arguments]
    child_env = os.environ.copy()
    source_path = str(REPO_ROOT / "src")
    existing_pythonpath = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = (
        source_path
        if not existing_pythonpath
        else source_path + os.pathsep + existing_pythonpath
    )
    try:
        with log_path.open("ab") as log:
            log.write(("\n$ " + " ".join(command) + "\n").encode("utf-8"))
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=child_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"convergence_cli_failed_{type(exc).__name__}") from exc
    return int(completed.returncode)


def _transport_arguments(args: argparse.Namespace) -> list[str]:
    return [
        "--registry",
        str(args.registry),
        "baseline-screening-transport-admission",
        "--plan",
        str(args.plan),
        "--campaign-state",
        str(args.state),
        "--max-transport-failure-rate",
        str(args.max_transport_failure_rate),
        "--min-canonical-models",
        str(args.min_canonical_models),
        "--output",
        str(args.transport_admission_output),
    ]


def _ranking_arguments(args: argparse.Namespace) -> list[str]:
    command = [
        "--registry",
        str(args.registry),
        "baseline-screening-to-ranking",
        "--plan",
        str(args.plan),
        "--campaign-state",
        str(args.state),
        "--source-manifest",
        str(args.source_manifest),
        "--private-root",
        str(args.private_root),
        "--transport-availability-file",
        str(args.transport_admission_output),
        "--output",
        str(args.ranking_output),
    ]
    for probe_file in args.private_probe_file:
        command.extend(("--private-probe-file", str(probe_file)))
    if args.operational_admission_file is not None:
        command.extend(
            ("--operational-admission-file", str(args.operational_admission_file))
        )
    return command


def _receipt(
    *,
    args: argparse.Namespace,
    state: Mapping[str, Any],
    transport_return_code: int | None,
    ranking_return_code: int | None,
    error_code: str | None = None,
) -> dict[str, Any]:
    transport = _read_json(args.transport_admission_output)
    ranking = _read_json(args.ranking_output)
    return {
        "schema": "axio_fusion_api.composite_convergence_supervisor_receipt.v1",
        "status": "ready" if ranking.get("screening_conversion_ready") is True else "blocked",
        "error_code": error_code or "",
        "screening_status": str(state.get("status") or ""),
        "screening_plan_digest_sha256": str(state.get("plan_digest_sha256") or ""),
        "screening_campaign_digest_sha256": str(state.get("campaign_digest_sha256") or ""),
        "registry_file_sha256": _sha256_file(args.registry),
        "plan_file_sha256": _sha256_file(args.plan),
        "source_manifest_file_sha256": _sha256_file(args.source_manifest),
        "probe_file_sha256": [_sha256_file(Path(path)) for path in args.private_probe_file],
        "private_root_sha256": _sha256_text(str(args.private_root)),
        "screening_output_file_sha256": _sha256_file(args.screening_output),
        "transport_admission_file_sha256": _sha256_file(args.transport_admission_output),
        "ranking_file_sha256": _sha256_file(args.ranking_output),
        "transport_return_code": transport_return_code,
        "ranking_return_code": ranking_return_code,
        "transport_status": str(transport.get("status") or ""),
        "transport_reason_codes": sorted(str(x) for x in transport.get("blockers", []) if x),
        "ranking_ready": ranking.get("screening_conversion_ready") is True,
        "ranking_reason_codes": sorted(str(x) for x in ranking.get("blockers", []) if x),
        "target_suite_calls_performed": state.get("target_suite_calls_performed"),
        "raw_provider_outputs_persisted": state.get("raw_provider_outputs_persisted"),
        "secrets_persisted": state.get("secrets_persisted"),
        "plan_mutated": False,
        "target_benchmark_started": False,
    }


def _advance_campaign(
    args: argparse.Namespace,
    *,
    state: Mapping[str, Any],
    log_path: Path,
) -> tuple[int, int | None, str | None]:
    """运行 transport admission，并仅在通过时运行 ranking conversion。"""

    if state.get("target_suite_calls_performed") is not False:
        return 2, None, "screening_target_suite_calls_present"
    transport_return_code = _run_cli(_transport_arguments(args), log_path=log_path)
    transport = _read_json(args.transport_admission_output)
    _emit(
        "transport_admission_finished",
        return_code=transport_return_code,
        status=transport.get("status"),
    )
    if transport.get("status") != "ready":
        return transport_return_code, None, "transport_admission_blocked"

    ranking_return_code = _run_cli(_ranking_arguments(args), log_path=log_path)
    ranking = _read_json(args.ranking_output)
    _emit(
        "ranking_conversion_finished",
        return_code=ranking_return_code,
        ready=ranking.get("screening_conversion_ready") is True,
    )
    if ranking.get("screening_conversion_ready") is not True:
        return transport_return_code, ranking_return_code, "screening_ranking_conversion_blocked"
    return transport_return_code, ranking_return_code, None


def main() -> int:
    args = _parser().parse_args()
    try:
        args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _emit("lock_directory_create_failed", error_code=type(exc).__name__)
        return 2
    interval = max(1.0, float(args.interval_seconds))
    try:
        lock_handle = args.lock_file.open("a+")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_handle.close()
            _emit("already_running")
            return 0
    except OSError as exc:
        _emit("lock_open_failed", error_code=type(exc).__name__)
        return 2

    transport_return_code: int | None = None
    ranking_return_code: int | None = None
    state: dict[str, Any] = {}
    error_code: str | None = None
    log_path = args.private_root / "convergence_supervisor.composite.private.log"
    try:
        state = _wait_for_terminal_state(
            pid=args.pid,
            expected_fragment=args.command_fragment,
            state_path=args.state,
            interval_seconds=interval,
        )
        transport_return_code, ranking_return_code, error_code = _advance_campaign(
            args, state=state, log_path=log_path
        )
    except RuntimeError as exc:
        error_code = str(exc)
        _emit("supervisor_blocked", error_code=error_code)
    finally:
        receipt = _receipt(
            args=args,
            state=state,
            transport_return_code=transport_return_code,
            ranking_return_code=ranking_return_code,
            error_code=error_code,
        )
        try:
            _atomic_write_json(args.receipt_output, receipt)
        except OSError as exc:
            _emit("receipt_write_failed", error_code=type(exc).__name__)
            error_code = error_code or "supervisor_receipt_write_failed"
        finally:
            lock_handle.close()

    return 0 if error_code is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
