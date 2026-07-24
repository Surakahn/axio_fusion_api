from __future__ import annotations

import json
import sys
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.evaluation import (
    _benchmark_prompt_case_projection,
    _benchmark_prompt_contract,
    _benchmark_prompt_contract_is_clean,
    _final_run_anti_leakage_receipt,
    _generic_case_prompt,
    _multiple_choice_prompt,
    validate_benchmark_dataset,
)


def _prompt_for(case: dict, task_format: str) -> tuple[dict, str, dict]:
    projection = _benchmark_prompt_case_projection(case, task_format)
    prompt = (
        _multiple_choice_prompt(projection)
        if task_format == "multiple_choice"
        else _generic_case_prompt(projection, task_format)
    )
    contract = _benchmark_prompt_contract(
        case,
        projection,
        prompt=prompt,
        task_format=task_format,
    )
    return projection, prompt, contract


def test_prompt_projection_excludes_scoring_fields_for_every_builtin_format():
    cases = {
        "multiple_choice": {
            "question": "Which option is public?",
            "options": ["one", "two"],
            "answer": "B",
            "label": "SECRET_MCQ_LABEL",
        },
        "translation_chrf": {
            "source": "A public source sentence.",
            "source_language": "en",
            "target_language": "fr",
            "reference": "SECRET_TRANSLATION_REFERENCE",
            "pass_threshold": 0.5,
        },
        "python_code": {
            "prompt": "Implement the public function.",
            "entry_point": "solve",
            "tests": "SECRET_HIDDEN_TESTS",
            "answer": "SECRET_CODE_ANSWER",
        },
        "tool_call_ast": {
            "prompt": "Use the public search tool.",
            "tools": [{"name": "search", "parameters": {"query": "string"}}],
            "expected_tool_call": {"name": "search", "arguments": {"query": "SECRET_TOOL_ARGUMENT"}},
        },
        "instruction_checks": {
            "prompt": "Follow the public instruction.",
            "checks": {"contains": ["SECRET_INSTRUCTION_LABEL"]},
        },
        "exact_match": {
            "prompt": "Compute the public result.",
            "answer": "SECRET_EXACT_ANSWER",
            "reference": "SECRET_EXACT_REFERENCE",
        },
    }

    for task_format, case in cases.items():
        projection, prompt, contract = _prompt_for(case, task_format)
        assert _benchmark_prompt_contract_is_clean(contract), task_format
        assert not set(case).intersection(contract["scoring_field_names_in_prompt_builder_input"])
        assert contract["scoring_fields_structurally_excluded_from_prompt"] is True
        assert all(secret not in prompt for secret in _secret_values(case))
        assert "prompt" not in contract["scoring_field_names_in_prompt_builder_input"]
        assert set(projection).isdisjoint({"answer", "reference", "tests", "checks", "expected_tool_call"})


def test_multiple_choice_projection_normalizes_public_choices_without_answer():
    case = {
        "question": "Choose one.",
        "choices": {"A": "first", "B": "second"},
        "answer": "B",
    }
    projection, prompt, contract = _prompt_for(case, "multiple_choice")

    assert projection["option_labels"] == ["A", "B"]
    assert projection["options"] == ["first", "second"]
    assert "first" in prompt and "second" in prompt
    assert "B" not in prompt.split("Answer with", 1)[-1]
    assert _benchmark_prompt_contract_is_clean(contract)


def test_dataset_validation_reports_prompt_contract_and_keeps_values_out_of_receipt(tmp_path):
    secret = "SECRET_EXACT_VALIDATION_VALUE"
    dataset = tmp_path / "math.jsonl"
    dataset.write_text(
        json.dumps({"prompt": "Return the public result.", "answer": secret}) + "\n",
        encoding="utf-8",
    )

    report = validate_benchmark_dataset(
        suite_id="math_500",
        dataset_path=dataset,
        task_format="exact_match",
    )

    serialized = json.dumps(report, ensure_ascii=False)
    assert report["prompt_contract_violation_count"] == 0
    assert report["ready_for_scoring"] is True
    assert secret not in serialized
    assert str(dataset) not in serialized


def test_final_claim_anti_leakage_gate_requires_prompt_contract_for_local_runs():
    case = {"prompt": "public task", "answer": "SECRET_FINAL_ANSWER"}
    _, _, clean_contract = _prompt_for(case, "exact_match")
    base = {
        "suite_id": "math_500",
        "candidate_id": "axio-pro",
        "anti_leakage_contract": {
            "prompt_contract_required_for_final_claim": True,
            "prompt_contract_schema": clean_contract["schema"],
            "raw_inputs_persisted": False,
            "raw_references_persisted": False,
            "raw_labels_persisted": False,
            "raw_provider_outputs_persisted": False,
            "benchmark_labels_used_for_training": False,
        },
        "case_results": [
            {
                "prompt_contract": clean_contract,
                "raw_input_persisted": False,
                "raw_reference_persisted": False,
                "raw_label_persisted": False,
                "raw_model_output_persisted": False,
                "secrets_persisted": False,
            }
        ],
    }

    clean = _final_run_anti_leakage_receipt(base)
    assert clean["clean"] is True
    assert clean["prompt_contract_required_for_final_claim"] is True
    assert clean["prompt_contract_issue_count"] == 0

    bad = dict(base)
    bad["case_results"] = [dict(base["case_results"][0], prompt_contract=None)]
    failed = _final_run_anti_leakage_receipt(bad)
    assert failed["clean"] is False
    assert failed["prompt_contract_issue_count"] == 1
    assert "prompt_contract_missing_or_failed" in failed["reason_codes"]


def _secret_values(case: dict) -> list[str]:
    values: list[str] = []
    for key in ("answer", "label", "target", "reference", "tests", "expected_tool_call", "checks"):
        value = case.get(key)
        if isinstance(value, str):
            if "SECRET" in value:
                values.append(value)
        elif value is not None:
            serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
            if "SECRET" in serialized:
                values.append(serialized)
    return values
