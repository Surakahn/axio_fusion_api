import json
from pathlib import Path
from types import SimpleNamespace


import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import watch_composite_convergence as watcher


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _args(tmp_path: Path) -> SimpleNamespace:
    paths = {}
    for name in (
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
    ):
        paths[name] = tmp_path / f"{name}.json"
        _write(paths[name], {})
    paths["cohort_binding"] = tmp_path / "cohort-binding.json"
    paths["audit_output"] = tmp_path / "audit.json"
    return SimpleNamespace(
        screening_pid=999999,
        screening_command_fragment="frozen-plan.json",
        target_campaign=None,
        final_audit=None,
        **paths,
    )


def test_cycle_rebuilds_binding_and_audit_atomically(tmp_path: Path) -> None:
    args = _args(tmp_path)
    _write(args.state, {"status": "running"})
    result = watcher._run_cycle(args)
    assert result["status"] == "running"
    assert json.loads(args.cohort_binding.read_text(encoding="utf-8"))["status"] == "blocked"
    encoded = args.cohort_binding.read_text(encoding="utf-8") + args.audit_output.read_text(encoding="utf-8")
    assert str(tmp_path) not in encoded


def test_process_identity_requires_screening_runner_and_plan() -> None:
    assert watcher._process_matches("python unrelated", "plan.json") is False
    assert watcher._process_matches(
        "python baseline-screening-run --plan plan.json", "plan.json"
    ) is True


def test_terminal_state_does_not_require_live_screening_pid(tmp_path: Path, monkeypatch) -> None:
    args = _args(tmp_path)
    _write(args.state, {"status": "completed"})
    monkeypatch.setattr(watcher, "_proc_cmdline", lambda _pid: "")
    watcher._run_cycle(args)
    assert json.loads(args.audit_output.read_text(encoding="utf-8"))["status"] == "blocked"
