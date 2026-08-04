import json
import sys
from types import SimpleNamespace
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import continue_prefusion_convergence as supervisor


def test_proc_cmdline_rejects_unrelated_process(monkeypatch):
    monkeypatch.setattr(
        supervisor,
        "_proc_cmdline",
        lambda _pid: "python -m unrelated-worker --plan other.json",
    )
    try:
        supervisor._wait_for_exit(123, "baseline_screening_plan.r20.safe.json", 0.01)
    except RuntimeError as exc:
        assert str(exc) == "r20_pid_identity_check_failed"
    else:
        raise AssertionError("unrelated process must be rejected")


def test_wait_for_exit_accepts_expected_process_then_exit(monkeypatch):
    commands = iter(
        [
            "python baseline-screening-run --plan baseline_screening_plan.r20.safe.json",
            "",
        ]
    )
    monkeypatch.setattr(supervisor, "_proc_cmdline", lambda _pid: next(commands))
    monkeypatch.setattr(supervisor.time, "sleep", lambda _seconds: None)
    supervisor._wait_for_exit(123, "baseline_screening_plan.r20.safe.json", 0.01)


def test_conversion_ready_uses_safe_manifest_only(tmp_path):
    path = tmp_path / "ranking.safe.json"
    path.write_text(
        json.dumps({"screening_conversion_ready": True}), encoding="utf-8"
    )
    assert supervisor._conversion_ready(path) is True
    path.write_text(json.dumps({"screening_conversion_ready": False}), encoding="utf-8")
    assert supervisor._conversion_ready(path) is False


def test_existing_live_process_filters_by_command_fragment(monkeypatch):
    commands = {
        10: "python baseline-screening-run --plan baseline_screening_plan.r21.failfast.safe.json",
        11: "python baseline-screening-run --plan baseline_screening_plan.r20.safe.json",
        12: "python supervisor --r21-command-fragment baseline_screening_plan.r21.failfast.safe.json",
    }
    monkeypatch.setattr(supervisor.Path, "iterdir", lambda _self: [Path(str(x)) for x in commands])
    monkeypatch.setattr(
        supervisor,
        "_proc_cmdline",
        lambda pid: commands[int(pid)],
    )
    assert supervisor._existing_live_process("baseline_screening_plan.r21.failfast.safe.json") == [10]


def test_successor_blocked_terminal_state_is_ready_for_conversion(tmp_path):
    state = tmp_path / "r21-state.json"
    state.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")
    args = type("Args", (), {"r21_state": state})()
    assert supervisor._successor_run_finished(args, 2) is True


def test_successor_missing_state_and_nonzero_return_is_not_finished(tmp_path):
    state = tmp_path / "r21-state.json"
    args = type("Args", (), {"r21_state": state})()
    assert supervisor._successor_run_finished(args, 2) is False


def test_successor_zero_return_without_terminal_state_is_not_finished(tmp_path):
    state = tmp_path / "r21-state.json"
    state.write_text(json.dumps({"status": "running"}), encoding="utf-8")
    args = type("Args", (), {"r21_state": state})()
    assert supervisor._successor_run_finished(args, 0) is False


def test_r20_recovery_reuses_frozen_arguments_after_process_exit(monkeypatch, tmp_path):
    state_path = tmp_path / "r20-state.json"
    state_path.write_text(json.dumps({"status": "running"}), encoding="utf-8")
    args = SimpleNamespace(
        r20_state=state_path,
        r20_command_fragment="baseline_screening_plan.r20.safe.json",
        max_r20_recoveries=1,
        r20_registry=tmp_path / "registry.json",
        r20_plan=tmp_path / "r20-plan.json",
        source_manifest=tmp_path / "source.json",
        r20_private_probe_file=tmp_path / "probe.json",
        r20_private_root=tmp_path / "private",
        r20_output=tmp_path / "r20.safe.json",
        r20_ranking_output=tmp_path / "ranking.json",
    )
    commands = iter([[], []])
    monkeypatch.setattr(
        supervisor,
        "_existing_live_process",
        lambda _fragment: next(commands),
    )
    captured = {}

    def fake_run(arguments, *, log_path):
        captured["arguments"] = arguments
        state_path.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")
        return 2

    monkeypatch.setattr(supervisor, "_run_cli", fake_run)
    result = supervisor._ensure_r20_terminal(args, 0.01)
    assert result["status"] == "blocked"
    assert "baseline-screening-run" in captured["arguments"]
    assert str(args.r20_plan) in captured["arguments"]
    assert "--retry-failed" not in captured["arguments"]


def test_r20_recovery_budget_fails_closed(tmp_path):
    state_path = tmp_path / "r20-state.json"
    state_path.write_text(json.dumps({"status": "running"}), encoding="utf-8")
    args = SimpleNamespace(
        r20_state=state_path,
        max_r20_recoveries=0,
        r20_command_fragment="r20",
    )
    try:
        supervisor._ensure_r20_terminal(args, 0.01)
    except RuntimeError as exc:
        assert str(exc) == "r20_recovery_budget_exhausted"
    else:
        raise AssertionError("recovery budget must fail closed")
