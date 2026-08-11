"""benchmark v4 harness 配置与错误响应处理测试。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "scripts/run_benchmark_v4.py"


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("benchmark_v4_harness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_halueval_is_configured_as_mcq(harness) -> None:
    meta = harness.SUITES["halueval"]
    assert meta["fmt"] == "mcq"
    assert meta["qk"] == "question"
    assert meta["ok"] == "options"
    assert meta["ak"] == "answer"


def test_call_axio_returns_none_on_error_response(harness, monkeypatch) -> None:
    class FakeResponse:
        def read(self) -> bytes:
            return b'{"error": {"message": "boom"}}'

    monkeypatch.setattr(harness.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    assert harness.call_axio("axio-pro", "question") is None


def test_call_cpa_returns_none_on_error_response(harness, monkeypatch) -> None:
    class FakeResponse:
        def read(self) -> bytes:
            return b'{"error": {"message": "boom"}}'

    monkeypatch.setattr(harness.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    assert harness.call_cpa("gpt-5.6-sol", "question") is None


def test_should_rerun_supports_suite_and_model_scopes(harness) -> None:
    assert harness.should_rerun("halueval", "axio-fast", ["halueval"]) is True
    assert harness.should_rerun("halueval", "axio-fast", ["halueval:axio-fast"]) is True
    assert harness.should_rerun("halueval", "axio-pro", ["halueval:axio-fast"]) is False
    assert harness.should_rerun("halueval", "axio-fast", []) is False


def test_score_mcq_maps_digit_gold_to_letter(harness) -> None:
    assert harness.score_mcq("B", "2") == 1.0
    assert harness.score_mcq("C", "3") == 1.0
    assert harness.score_mcq("A", "2") == 0.0


def test_build_prompt_adds_translation_instruction(harness) -> None:
    case = {
        "source": "Hello.",
        "source_language": "English",
        "target_language": "Chinese (Simplified)",
    }
    meta = harness.SUITES["flores_translation_instruction"]
    prompt = harness.build_prompt(case, meta)
    assert "Translate the following English text into Chinese (Simplified)" in prompt
    assert "Hello." in prompt


def test_build_prompt_renames_digit_options(harness) -> None:
    case = {
        "question": "Which one?",
        "options": {"1": "first", "2": "second", "3": "third", "4": "fourth"},
    }
    prompt = harness.build_prompt(case, harness.SUITES["arc_challenge"])
    assert "A: first" in prompt
    assert "B: second" in prompt
    assert "1: first" not in prompt
