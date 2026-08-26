"""BizBench 任务感知物化与审计评分契约测试。"""
from __future__ import annotations

import json
from pathlib import Path

import axio_fusion_api.evaluation as evaluation


def _case(**overrides):
    row = {
        "prompt": "Question: compute the value",
        "question": "compute the value",
        "answer": "100",
        "category": "SEC-NUM",
        "bizbench_task": "SEC-NUM",
        "bizbench_evaluator": evaluation.BIZBENCH_EVALUATOR_ID,
        "bizbench_output_mode": "numeric",
    }
    row.update(overrides)
    return row


def test_bizbench_materializer_preserves_task_contract(monkeypatch, tmp_path: Path):
    raw_root = tmp_path / "raw"
    (raw_root / "bizbench" / "data").mkdir(parents=True)
    parquet_path = raw_root / "bizbench" / "data" / "test-00000.parquet"
    parquet_path.write_bytes(b"fixture")
    monkeypatch.setattr(
        evaluation,
        "_read_parquet_rows",
        lambda _path: [
            {
                "question": "Which answer?",
                "answer": "1",
                "task": "FinKnow",
                "context": None,
                "context_type": None,
                "options": ["first", "second", "third"],
                "program": None,
            },
            {
                "question": "What is the value?",
                "answer": "100",
                "task": "SEC-NUM",
                "context": "A filing excerpt",
                "context_type": "string",
                "options": None,
                "program": None,
            },
        ],
    )

    rows = evaluation._materialize_bizbench(raw_root)

    assert [row["bizbench_output_mode"] for row in rows] == ["choice", "numeric_or_span"]
    assert "A. first" in rows[0]["prompt"]
    assert "Return only the single best option letter." in rows[0]["prompt"]
    assert "Context:\nA filing excerpt" in rows[1]["prompt"]
    assert rows[0]["bizbench_evaluator"] == evaluation.BIZBENCH_EVALUATOR_ID
    assert "answer" not in evaluation._benchmark_prompt_case_projection(rows[0], "exact_match")


def test_bizbench_materializer_drops_parquet_nan_context(monkeypatch, tmp_path: Path):
    raw_root = tmp_path / "raw"
    (raw_root / "bizbench" / "data").mkdir(parents=True)
    parquet_path = raw_root / "bizbench" / "data" / "test-00000.parquet"
    parquet_path.write_bytes(b"fixture")
    monkeypatch.setattr(
        evaluation,
        "_read_parquet_rows",
        lambda _path: [
            {
                "question": "Compute the answer",
                "answer": "7",
                "task": "FinCode",
                "context": float("nan"),
                "context_type": float("nan"),
                "options": None,
                "program": "answer = 7",
            }
        ],
    )
    row = evaluation._materialize_bizbench(raw_root)[0]
    assert row["context"] == ""
    assert row["context_type"] == ""
    assert "nan" not in row["prompt"].lower()


def test_bizbench_sec_num_supports_numeric_and_open_vocabulary_spans():
    numeric = _case(
        answer="85",
        bizbench_task="SEC-NUM",
        bizbench_output_mode="numeric_or_span",
    )
    assert evaluation._score_bizbench_output(output="85", case=numeric, timeout=1)["correct"] is True
    assert evaluation._score_bizbench_output(output="86", case=numeric, timeout=1)["correct"] is False

    span = _case(
        answer="10-year",
        bizbench_task="SEC-NUM",
        bizbench_output_mode="numeric_or_span",
    )
    assert evaluation._score_bizbench_output(output="10-year", case=span, timeout=1)["correct"] is True
    assert evaluation._score_bizbench_output(output="10", case=span, timeout=1)["correct"] is False


def test_bizbench_choice_and_numeric_scoring_are_deterministic():
    choice = _case(
        answer="1",
        category="FinKnow",
        bizbench_task="FinKnow",
        bizbench_output_mode="choice",
        options=["first", "second"],
        option_labels=["A", "B"],
    )
    assert evaluation._score_bizbench_output(output="Final answer: B", case=choice, timeout=1)["correct"] is True
    assert evaluation._score_bizbench_output(output="A", case=choice, timeout=1)["correct"] is False

    numeric = _case(answer="100")
    assert evaluation._score_bizbench_output(output="101", case=numeric, timeout=1)["correct"] is True
    assert evaluation._score_bizbench_output(output="102", case=numeric, timeout=1)["correct"] is False


def test_bizbench_program_numeric_executes_structured_context(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_ALLOW_BENCHMARK_CODE_EXEC", "1")
    case = _case(
        answer="105",
        category="CodeTAT-QA",
        bizbench_task="CodeTAT-QA",
        bizbench_output_mode="program_numeric",
        context_type="json",
        context=json.dumps({"Revenue": {"2017": 55, "2018": 50}}),
    )
    output = '```python\nanswer = df["Revenue"]["2017"] + df["Revenue"]["2018"]\n```'
    scored = evaluation._score_bizbench_output(output=output, case=case, timeout=2)
    assert scored["correct"] is True
    assert scored["metric"] == "numeric_reasoning_accuracy"


def test_bizbench_program_rejects_imports_and_dangerous_calls(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_ALLOW_BENCHMARK_CODE_EXEC", "1")
    case = _case(
        bizbench_task="FinCode",
        bizbench_output_mode="program_numeric",
    )
    scored = evaluation._score_bizbench_output(
        output="```python\nimport os\nanswer = 100\n```",
        case=case,
        timeout=2,
    )
    assert scored["correct"] is False
    assert scored["error_type"] == "bizbench_code_import_forbidden"

    reflected = evaluation._score_bizbench_output(
        output="answer = globals()['__builtins__']['open']('/etc/passwd').read()",
        case=case,
        timeout=2,
    )
    assert reflected["correct"] is False
    assert reflected["error_type"] == "bizbench_code_dangerous_call"


def test_bizbench_program_runtime_uses_restricted_builtins(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_ALLOW_BENCHMARK_CODE_EXEC", "1")
    case = _case(
        bizbench_task="FinCode",
        bizbench_output_mode="program_numeric",
    )
    output = "answer = open('/etc/passwd').read()"
    scored = evaluation._score_bizbench_output(output=output, case=case, timeout=2)
    assert scored["correct"] is False
    assert scored["error_type"] == "bizbench_code_dangerous_call"


def test_bizbench_formula_executes_candidate_against_gold(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_ALLOW_BENCHMARK_CODE_EXEC", "1")
    stub = """def simple_interest(principal: float, rate: float, time: float) -> float:
    \"\"\"Return simple interest.\"\"\"
"""
    case = _case(
        prompt=stub,
        question=stub,
        bizbench_stub=stub,
        answer="    return principal * (1 + rate * time)\n",
        category="FormulaEval",
        bizbench_task="FormulaEval",
        bizbench_output_mode="formula_code",
    )
    scored = evaluation._score_bizbench_output(
        output="return principal * (1 + rate * time)",
        case=case,
        timeout=2,
    )
    assert scored["correct"] is True
    assert scored["metric"] == "formula_unit_test_accuracy"
