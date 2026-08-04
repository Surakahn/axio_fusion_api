#!/usr/bin/env python3
"""Continue the registered pre-Fusion screening path after a live cohort exits.

This operator utility is intentionally narrower than the screening runner. It
does not alter a frozen plan, retry a completed case, tune prompts, or launch
benchmark traffic. It waits for one known screening process, performs the
single permitted ranking conversion, and starts the already pre-registered
successor cohort only when the conversion is not ready.

Credential values are read into the child process environment only. Runtime
receipts and logs belong under ``private/`` and are therefore not source
artifacts.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIAL_FILE = Path("/home/he/VeilGuard/fusionapi能用的模型接口.txt")
DEFAULT_INTERVAL_SECONDS = 300.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r20-pid", required=True, type=int)
    parser.add_argument("--r20-state", required=True, type=Path)
    parser.add_argument("--r20-plan", required=True, type=Path)
    parser.add_argument("--r20-registry", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--r20-private-root", required=True, type=Path)
    parser.add_argument("--r20-private-probe-file", required=True, type=Path)
    parser.add_argument("--r20-ranking-output", required=True, type=Path)
    parser.add_argument("--r21-plan", required=True, type=Path)
    parser.add_argument("--r21-private-root", required=True, type=Path)
    parser.add_argument("--r21-state", required=True, type=Path)
    parser.add_argument("--r21-output", required=True, type=Path)
    parser.add_argument("--r21-ranking-output", required=True, type=Path)
    parser.add_argument("--lock-file", required=True, type=Path)
    parser.add_argument(
        "--credentials-file", type=Path, default=DEFAULT_CREDENTIAL_FILE
    )
    parser.add_argument(
        "--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS
    )
    parser.add_argument(
        "--r20-command-fragment",
        default="baseline_screening_plan.r20.safe.json",
        help="Required fragment used to reject PID reuse or an unrelated process.",
    )
    parser.add_argument(
        "--r21-command-fragment",
        default="baseline_screening_plan.r21.failfast.safe.json",
    )
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _proc_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _load_credentials(path: Path) -> None:
    """Reuse the existing private credential loader without printing values."""

    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from run_non_target_screening_chunks import _load_credentials

    _load_credentials(path)
    os.environ.setdefault("AXIO_FUSION_NETWORK_MODE", "auto")
    os.environ.setdefault("AXIO_FUSION_SYSTEM_PROXY", "http://127.0.0.1:10808")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")


def _emit(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True), flush=True)


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
    return int(completed.returncode)


def _conversion_arguments(
    *,
    registry: Path,
    plan: Path,
    state: Path,
    source_manifest: Path,
    private_root: Path,
    private_probe_file: Path,
    output: Path,
) -> list[str]:
    return [
        "--registry",
        str(registry),
        "baseline-screening-to-ranking",
        "--plan",
        str(plan),
        "--campaign-state",
        str(state),
        "--source-manifest",
        str(source_manifest),
        "--private-root",
        str(private_root),
        "--private-probe-file",
        str(private_probe_file),
        "--output",
        str(output),
    ]


def _screening_arguments(
    *,
    registry: Path,
    plan: Path,
    source_manifest: Path,
    private_probe_file: Path,
    private_root: Path,
    state: Path,
    output: Path,
) -> list[str]:
    return [
        "--registry",
        str(registry),
        "baseline-screening-run",
        "--plan",
        str(plan),
        "--source-manifest",
        str(source_manifest),
        "--private-probe-file",
        str(private_probe_file),
        "--private-root",
        str(private_root),
        "--state-output",
        str(state),
        "--live",
        "--output",
        str(output),
    ]


def _wait_for_exit(pid: int, expected_fragment: str, interval: float) -> None:
    first_command = _proc_cmdline(pid)
    if not first_command or expected_fragment not in first_command:
        raise RuntimeError("r20_pid_identity_check_failed")
    _emit("r20_wait_started", pid=pid, command_fragment=expected_fragment)
    while True:
        current_command = _proc_cmdline(pid)
        if not current_command:
            _emit("r20_process_exited", pid=pid)
            return
        if expected_fragment not in current_command:
            raise RuntimeError("r20_pid_reused_or_command_changed")
        time.sleep(interval)


def _wait_for_terminal_state(path: Path, interval: float) -> dict[str, Any]:
    while True:
        state = _read_json(path)
        if state.get("status") not in {None, "running", "partial"}:
            return state
        time.sleep(interval)


def _conversion_ready(path: Path) -> bool:
    return _read_json(path).get("screening_conversion_ready") is True


def _existing_live_process(fragment: str) -> list[int]:
    matches: list[int] = []
    proc_root = Path("/proc")
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        command = _proc_cmdline(pid)
        if "baseline-screening-run" in command and fragment in command:
            matches.append(pid)
    return sorted(matches)


def _run_successor(args: argparse.Namespace) -> int:
    existing = [pid for pid in _existing_live_process(args.r21_command_fragment)]
    if existing:
        _emit("r21_already_running", pids=existing)
        return 0
    args.r21_private_root.mkdir(parents=True, exist_ok=True)
    log_path = args.r21_private_root / "convergence_supervisor.private.log"
    command = _screening_arguments(
        registry=args.r20_registry,
        plan=args.r21_plan,
        source_manifest=args.source_manifest,
        private_probe_file=args.r20_private_probe_file,
        private_root=args.r21_private_root,
        state=args.r21_state,
        output=args.r21_output,
    )
    _emit("r21_starting", plan=str(args.r21_plan))
    return _run_cli(command, log_path=log_path)


def _successor_run_finished(args: argparse.Namespace, _return_code: int) -> bool:
    """Treat a terminal campaign receipt as a launched successor.

    The CLI intentionally returns a non-zero code for a valid blocked
    screening campaign. That is a quality-gate result, not a process-launch
    failure, and the next step is still the single ranking conversion.
    """

    state = _read_json(args.r21_state)
    terminal = state.get("status") in {"completed", "blocked", "failed"}
    return terminal


def main() -> int:
    args = _parser().parse_args()
    interval = max(1.0, float(args.interval_seconds))
    args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_file.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _emit("already_running")
            return 0

        _load_credentials(args.credentials_file)
        _wait_for_exit(args.r20_pid, args.r20_command_fragment, interval)
        r20_state = _wait_for_terminal_state(args.r20_state, interval)
        _emit("r20_terminal_state", status=r20_state.get("status"))

        r20_log = args.r20_ranking_output.parent / "convergence_supervisor.private.log"
        r20_rc = _run_cli(
            _conversion_arguments(
                registry=args.r20_registry,
                plan=args.r20_plan,
                state=args.r20_state,
                source_manifest=args.source_manifest,
                private_root=args.r20_private_root,
                private_probe_file=args.r20_private_probe_file,
                output=args.r20_ranking_output,
            ),
            log_path=r20_log,
        )
        r20_ready = _conversion_ready(args.r20_ranking_output)
        _emit("r20_ranking_conversion", return_code=r20_rc, ready=r20_ready)
        if r20_ready:
            _emit("baseline_freeze_gate_open", ranking=str(args.r20_ranking_output))
            return 0

        successor_rc = _run_successor(args)
        if not _successor_run_finished(args, successor_rc):
            _emit("r21_start_failed")
            return 2

        while True:
            r21_state = _read_json(args.r21_state)
            if r21_state.get("status") in {"completed", "blocked", "failed"}:
                break
            time.sleep(interval)
        _emit("r21_terminal_state", status=r21_state.get("status"))

        r21_log = args.r21_ranking_output.parent / "convergence_supervisor.private.log"
        r21_rc = _run_cli(
            _conversion_arguments(
                registry=args.r20_registry,
                plan=args.r21_plan,
                state=args.r21_state,
                source_manifest=args.source_manifest,
                private_root=args.r21_private_root,
                private_probe_file=args.r20_private_probe_file,
                output=args.r21_ranking_output,
            ),
            log_path=r21_log,
        )
        r21_ready = _conversion_ready(args.r21_ranking_output)
        _emit("r21_ranking_conversion", return_code=r21_rc, ready=r21_ready)
        return 0 if r21_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
