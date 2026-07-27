from __future__ import annotations

import io
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api import cli, service_cli
from axio_fusion_api.runtime_requirements import ensure_supported_python_runtime


def test_runtime_requirement_reports_unsupported_python_without_side_effects():
    stderr = io.StringIO()

    assert ensure_supported_python_runtime(version=(3, 8), stderr=stderr) is False

    message = stderr.getvalue()
    assert "Python 3.10 or newer" in message
    assert "Python 3.8" in message


def test_runtime_requirement_accepts_declared_minimum_version():
    assert ensure_supported_python_runtime(version=(3, 10), stderr=io.StringIO()) is True
    assert ensure_supported_python_runtime(version=(3, 11), stderr=io.StringIO()) is True


def test_standalone_and_production_cli_reject_before_parser(monkeypatch):
    for module in (cli, service_cli):
        called = []
        monkeypatch.setattr(module, "ensure_supported_python_runtime", lambda: False)
        monkeypatch.setattr(module, "build_parser", lambda: called.append(True))

        assert module.main(["--help"]) == 2
        assert called == []
