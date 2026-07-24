"""Private BFCL V3 native-tool-call evaluator bridge.

This runner receives private model outputs from the Fusion benchmark bridge,
loads the pinned BFCL V3 source and possible-answer files only after generation,
and invokes the upstream AST checker.  Its result file contains no benchmark
text, labels, tool names, arguments, or evaluator diagnostics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import types
from typing import Any, Callable, Mapping


_BFCL_V3_MARKER = 'VERSION_PREFIX = "BFCL_v3"'
_BFCL_V3_AST_CATEGORIES = (
    "simple",
    "multiple",
    "parallel",
    "parallel_multiple",
    "live_simple",
    "live_multiple",
)
_NEUTRAL_NATIVE_TOOL_MODEL = "axio_native_tool_contract"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _harness_source_root(harness_root: Path) -> Path:
    source_root = harness_root / "berkeley-function-call-leaderboard"
    marker = source_root / "bfcl_eval" / "constants" / "category_mapping.py"
    try:
        compatible = _BFCL_V3_MARKER in marker.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        compatible = False
    if not compatible:
        raise ValueError("bfcl_v3_dataset_harness_version_mismatch")
    return source_root


def _iter_jsonl(path: Path):
    try:
        handle = path.open("r", encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("bfcl_private_source_unreadable") from exc
    with handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("bfcl_private_source_json_invalid") from exc
            if not isinstance(value, Mapping):
                raise ValueError("bfcl_private_source_row_invalid")
            yield dict(value)


def _load_source_cases(dataset_path: Path, *, limit: int | None) -> list[dict[str, Any]]:
    if not dataset_path.is_dir():
        raise ValueError("bfcl_v3_dataset_directory_required")
    cases: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for category in _BFCL_V3_AST_CATEGORIES:
        source_path = dataset_path / f"BFCL_v3_{category}.json"
        answer_path = dataset_path / "possible_answer" / f"BFCL_v3_{category}.json"
        answers = {
            str(row.get("id") or ""): row
            for row in _iter_jsonl(answer_path)
            if str(row.get("id") or "")
        }
        if not answers:
            raise ValueError("bfcl_possible_answer_rows_missing")
        for source in _iter_jsonl(source_path):
            identifier = str(source.get("id") or "")
            functions = source.get("function")
            answer = answers.get(identifier)
            if (
                not identifier
                or not isinstance(functions, list)
                or not all(isinstance(item, Mapping) for item in functions)
                or not isinstance(answer, Mapping)
                or not isinstance(answer.get("ground_truth"), list)
            ):
                raise ValueError("bfcl_source_or_answer_row_invalid")
            key = (category, identifier)
            if key in seen:
                raise ValueError("bfcl_source_case_duplicate")
            seen.add(key)
            cases.append(
                {
                    "category": category,
                    "id": identifier,
                    "functions": [dict(item) for item in functions],
                    "ground_truth": list(answer["ground_truth"]),
                }
            )
            if limit is not None and len(cases) >= max(0, int(limit)):
                return cases
    if not cases:
        raise ValueError("bfcl_source_cases_empty")
    return cases


def _canonical_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("bfcl_private_sample_tool_calls_invalid")
    calls: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("bfcl_private_sample_tool_call_invalid")
        name = str(item.get("name") or "").strip()
        arguments = item.get("arguments")
        if not name or not isinstance(arguments, Mapping):
            raise ValueError("bfcl_private_sample_tool_call_invalid")
        calls.append(
            {
                "id": str(item.get("id") or ""),
                "type": str(item.get("type") or "function"),
                "name": name,
                "arguments": dict(arguments),
            }
        )
    return calls


def _load_private_predictions(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    predictions: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _iter_jsonl(path):
        category = str(row.get("category") or "")
        identifier = str(row.get("id") or "")
        text = row.get("text")
        if category not in _BFCL_V3_AST_CATEGORIES or not identifier or not isinstance(text, str):
            raise ValueError("bfcl_private_sample_shape_invalid")
        key = (category, identifier)
        if key in predictions:
            raise ValueError("bfcl_private_sample_duplicate")
        predictions[key] = {
            "text": text,
            "tool_calls": _canonical_tool_calls(row.get("tool_calls")),
        }
    if not predictions:
        raise ValueError("bfcl_private_samples_empty")
    return predictions


def _load_official_ast_checker(harness_root: Path) -> Callable[..., Mapping[str, Any]]:
    source_root = _harness_source_root(harness_root)
    source_text = str(source_root)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)

    # The upstream AST checker imports the full model-handler registry only to
    # decide whether a model-specific adapter substitutes dots in tool names.
    # Axio normalizes native tool calls back to the source schema names, so the
    # checker receives a neutral no-substitution profile without loading any
    # provider SDK or invoking a model handler.
    class _NeutralModelConfigs(dict[str, Any]):
        def __missing__(self, key: str) -> Any:
            value = types.SimpleNamespace(underscore_to_dot=False)
            self[key] = value
            return value

    module_name = "bfcl_eval.constants.model_config"
    stub = types.ModuleType(module_name)
    stub.MODEL_CONFIG_MAPPING = _NeutralModelConfigs()
    sys.modules[module_name] = stub
    try:
        from bfcl_eval.eval_checker.ast_eval.ast_checker import ast_checker
    except (ImportError, OSError, SyntaxError) as exc:
        raise ValueError("bfcl_v3_official_ast_checker_unavailable") from exc
    return ast_checker


def _prediction_for_ast(tool_calls: list[dict[str, Any]]) -> list[dict[str, dict[str, Any]]]:
    return [{str(call["name"]): dict(call["arguments"])} for call in tool_calls]


def _prediction_hash(prediction: Mapping[str, Any]) -> str:
    return _sha256_text(_stable_json(prediction))


def run(
    *,
    dataset_path: str | Path,
    harness_root: str | Path,
    samples_path: str | Path,
    output_path: str | Path,
    limit: int | None = None,
) -> int:
    _harness_source_root(Path(harness_root))
    cases = _load_source_cases(Path(dataset_path), limit=limit)
    predictions = _load_private_predictions(Path(samples_path))
    expected_keys = {(str(case["category"]), str(case["id"])) for case in cases}
    if set(predictions) != expected_keys:
        raise ValueError("bfcl_private_sample_case_set_mismatch")
    ast_checker = _load_official_ast_checker(Path(harness_root))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for case in cases:
            key = (str(case["category"]), str(case["id"]))
            prediction = predictions[key]
            try:
                result = ast_checker(
                    case["functions"],
                    _prediction_for_ast(prediction["tool_calls"]),
                    case["ground_truth"],
                    "Python",
                    str(case["category"]),
                    _NEUTRAL_NATIVE_TOOL_MODEL,
                )
                passed = bool(isinstance(result, Mapping) and result.get("valid") is True)
            except Exception:  # noqa: BLE001 - evaluator diagnostics stay private.
                passed = False
            prediction_payload = {
                "text": str(prediction["text"]),
                "tool_calls": list(prediction["tool_calls"]),
            }
            prediction_hash = _prediction_hash(prediction_payload)
            handle.write(
                json.dumps(
                    {
                        "category": key[0],
                        "id": key[1],
                        "passed": passed,
                        "prediction_sha256": prediction_hash,
                        "output_sha256": prediction_hash,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            handle.write("\n")
    try:
        output.chmod(0o600)
    except OSError:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--harness-root", required=True)
    parser.add_argument("--samples", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        return run(
            dataset_path=args.dataset,
            harness_root=args.harness_root,
            samples_path=args.samples,
            output_path=args.output,
            limit=args.limit,
        )
    except Exception as exc:  # noqa: BLE001 - never leak source or evaluator content.
        sys.stderr.write(f"bfcl_runner_failed:{type(exc).__name__}\n")
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through the bridge process
    raise SystemExit(main())
