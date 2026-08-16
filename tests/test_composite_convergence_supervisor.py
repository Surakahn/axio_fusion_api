import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import continue_composite_convergence as supervisor


def _args(tmp_path: Path) -> SimpleNamespace:
    registry = tmp_path / "registry.json"
    plan = tmp_path / "plan.json"
    source = tmp_path / "source.json"
    probe_one = tmp_path / "probe-one.json"
    probe_two = tmp_path / "probe-two.json"
    for path in (registry, plan, source, probe_one, probe_two):
        path.write_text("{}", encoding="utf-8")
    return SimpleNamespace(
        pid=123,
        registry=registry,
        plan=plan,
        source_manifest=source,
        private_probe_file=[str(probe_one), str(probe_two)],
        operational_admission_file=None,
        private_root=tmp_path / "private",
        state=tmp_path / "state.json",
        screening_output=tmp_path / "screening.json",
        transport_admission_output=tmp_path / "transport.json",
        ranking_output=tmp_path / "ranking.json",
        receipt_output=tmp_path / "receipt.json",
        lock_file=tmp_path / "lock",
        command_fragment="plan.json",
        interval_seconds=1.0,
        max_transport_failure_rate=0.02,
        min_canonical_models=3,
    )


def test_wait_rejects_unrelated_process(monkeypatch, tmp_path):
    args = _args(tmp_path)
    monkeypatch.setattr(supervisor, "_proc_cmdline", lambda _pid: "python unrelated")
    try:
        supervisor._wait_for_terminal_state(
            pid=args.pid,
            expected_fragment=args.command_fragment,
            state_path=args.state,
            interval_seconds=0.01,
        )
    except RuntimeError as exc:
        assert str(exc) == "screening_pid_identity_check_failed"
    else:
        raise AssertionError("unrelated process must be rejected")


def test_process_identity_requires_screening_subcommand(tmp_path):
    args = _args(tmp_path)
    assert supervisor._process_matches(
        "python --plan plan.json", args.command_fragment
    ) is False
    assert supervisor._process_matches(
        "python baseline-screening-run --plan plan.json", args.command_fragment
    ) is True


def test_terminal_state_does_not_require_live_pid(tmp_path):
    args = _args(tmp_path)
    args.state.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    assert supervisor._wait_for_terminal_state(
        pid=args.pid,
        expected_fragment=args.command_fragment,
        state_path=args.state,
        interval_seconds=0.01,
    )["status"] == "completed"


def test_ranking_arguments_bind_every_probe_and_transport_receipt(tmp_path):
    args = _args(tmp_path)
    command = supervisor._ranking_arguments(args)
    assert command.count("--private-probe-file") == 2
    assert str(args.transport_admission_output) in command
    assert "--transport-availability-file" in command


def test_ranking_arguments_bind_operational_admission_receipt(tmp_path):
    args = _args(tmp_path)
    args.operational_admission_file = tmp_path / "operational.json"
    args.operational_admission_file.write_text("{}", encoding="utf-8")
    command = supervisor._ranking_arguments(args)
    assert "--operational-admission-file" in command
    assert str(args.operational_admission_file) in command


def test_blocked_transport_skips_ranking(tmp_path, monkeypatch):
    args = _args(tmp_path)
    calls = []

    def fake_run(arguments, *, log_path):
        calls.append(list(arguments))
        args.transport_admission_output.write_text(
            json.dumps({"status": "blocked", "blockers": ["incomplete"]}),
            encoding="utf-8",
        )
        return 2

    monkeypatch.setattr(supervisor, "_run_cli", fake_run)
    result = supervisor._advance_campaign(
        args,
        state={"status": "partial", "target_suite_calls_performed": False},
        log_path=tmp_path / "log",
    )
    assert result == (2, None, "transport_admission_blocked")
    assert len(calls) == 1


def test_receipt_contains_hashes_but_not_raw_paths(tmp_path):
    args = _args(tmp_path)
    payload = supervisor._receipt(
        args=args,
        state={"status": "completed", "target_suite_calls_performed": False},
        transport_return_code=0,
        ranking_return_code=2,
        error_code="blocked",
    )
    encoded = json.dumps(payload, ensure_ascii=True)
    assert str(args.registry) not in encoded
    assert str(args.private_root) not in encoded
    assert payload["registry_file_sha256"]
    assert payload["private_root_sha256"]
