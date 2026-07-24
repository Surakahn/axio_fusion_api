"""Private LiveCodeBench official-evaluator bridge.

This process reconstructs the official ``input_output`` records from a pinned
local Parquet snapshot, invokes the fixed LiveCodeBench evaluator, and writes
only hash-based per-question results. Generated code and benchmark tests stay
in memory or in the caller-owned private directory.

Generated code is untrusted. The caller must pass ``--unsafe-authorized`` and
should run this process inside a disposable isolated worker or container. The
upstream reliability guard is not a complete security sandbox.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _source_path(path: Path) -> Path:
    selected = path / "test_generation.parquet" if path.is_dir() else path
    if selected.name != "test_generation.parquet" or not selected.is_file():
        raise ValueError("livecodebench_generation_parquet_missing")
    return selected


def _load_official_samples(dataset_path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - environment gate
        raise ValueError("livecodebench_parquet_dependency_missing") from exc

    source = _source_path(dataset_path)
    required = ("question_id", "question_content", "starter_code", "function_name", "test")
    parquet_file = parquet.ParquetFile(source)
    missing = [column for column in required if column not in parquet_file.schema.names]
    if missing:
        raise ValueError("livecodebench_required_columns_missing")
    rows = parquet_file.read(columns=list(required)).to_pylist()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        question_id = str(row.get("question_id") or "").strip()
        question_content = str(row.get("question_content") or "")
        starter_code = str(row.get("starter_code") or "")
        function_name = str(row.get("function_name") or "")
        raw_tests = row.get("test")
        try:
            tests = json.loads(raw_tests) if isinstance(raw_tests, str) else raw_tests
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("livecodebench_test_payload_invalid") from exc
        if (
            not question_id
            or not question_content
            or not function_name
            or not isinstance(tests, list)
            or not tests
        ):
            raise ValueError("livecodebench_source_row_invalid")
        if any(
            not isinstance(test, Mapping)
            or "input" not in test
            or "output" not in test
            for test in tests
        ):
            raise ValueError("livecodebench_test_row_invalid")

        existing = grouped.get(question_id)
        if existing is None:
            grouped[question_id] = {
                "question_id": question_id,
                "question_content": question_content,
                "starter_code": starter_code,
                "function_name": function_name,
                "tests": list(tests),
            }
            continue
        if (
            existing["question_content"] != question_content
            or existing["starter_code"] != starter_code
            or existing["function_name"] != function_name
        ):
            raise ValueError("livecodebench_question_metadata_mismatch")
        existing["tests"].extend(tests)

    if not grouped:
        raise ValueError("livecodebench_source_empty")

    samples: list[dict[str, Any]] = []
    for question_id in sorted(grouped):
        case = grouped[question_id]
        inputs = [_json_text(test["input"]) for test in case["tests"]]
        outputs = [_json_text(test["output"]) for test in case["tests"]]
        input_output = json.dumps(
            {
                "inputs": inputs,
                "outputs": outputs,
                "fn_name": case["function_name"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        samples.append({"question_id": question_id, "input_output": input_output})
    return samples


def _load_private_generations(samples_path: Path) -> dict[str, str]:
    generations: dict[str, str] = {}
    with samples_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, Mapping):
                raise ValueError("livecodebench_private_sample_not_object")
            question_id = str(payload.get("question_id") or "").strip()
            code_list = payload.get("code_list")
            if (
                not question_id
                or not isinstance(code_list, list)
                or len(code_list) != 1
                or not isinstance(code_list[0], str)
            ):
                raise ValueError("livecodebench_private_sample_shape_invalid")
            if question_id in generations:
                raise ValueError("livecodebench_private_sample_duplicate")
            generations[question_id] = code_list[0]
    if not generations:
        raise ValueError("livecodebench_private_samples_empty")
    return generations


def _compile_passed(code: str) -> bool:
    if not code.strip():
        return False
    try:
        compile(code, "<livecodebench-private-prediction>", "exec")
    except (SyntaxError, TypeError, ValueError, MemoryError):
        return False
    return True


def _run_official_evaluator(
    *,
    harness_root: Path,
    samples: list[dict[str, Any]],
    generations: list[str],
    worker_count: int,
    timeout_seconds: float,
) -> dict[int, bool]:
    harness = str(harness_root)
    if harness not in sys.path:
        sys.path.insert(0, harness)
    from lcb_runner.evaluation.compute_code_generation_metrics import codegen_metrics

    # Discard official progress/diagnostics so no evaluator content crosses the
    # bridge's private-result boundary.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _metrics, results, _metadata = codegen_metrics(
            samples,
            [[generation] for generation in generations],
            k_list=[1],
            num_process_evaluate=max(1, int(worker_count)),
            timeout=max(1, int(math.ceil(float(timeout_seconds)))),
            debug=False,
        )
    passed_by_index: dict[int, bool] = {}
    for index in range(len(samples)):
        candidate_results = results.get(index, [])
        first_generation = candidate_results[0] if candidate_results else []
        passed_by_index[index] = (
            isinstance(first_generation, list)
            and bool(first_generation)
            and all(bool(value) and float(value) > 0.0 for value in first_generation)
        )
    return passed_by_index


def run(
    *,
    dataset_path: str | Path,
    harness_root: str | Path,
    samples_path: str | Path,
    output_path: str | Path,
    worker_count: int = 4,
    timeout_seconds: float = 3.0,
    unsafe_authorized: bool = False,
) -> int:
    if not unsafe_authorized:
        raise PermissionError("unsafe_code_execution_not_explicitly_authorized")

    all_samples = _load_official_samples(Path(dataset_path))
    generations_by_id = _load_private_generations(Path(samples_path))
    samples = [
        sample
        for sample in all_samples
        if str(sample["question_id"]) in generations_by_id
    ]
    sample_ids = [str(sample["question_id"]) for sample in samples]
    if set(sample_ids) != set(generations_by_id) or len(sample_ids) != len(generations_by_id):
        raise ValueError("livecodebench_sample_case_set_mismatch")
    generations = [generations_by_id[question_id] for question_id in sample_ids]
    passed_by_index = _run_official_evaluator(
        harness_root=Path(harness_root),
        samples=samples,
        generations=generations,
        worker_count=worker_count,
        timeout_seconds=timeout_seconds,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for index, question_id in enumerate(sample_ids):
            code = generations[index]
            prediction_hash = _sha256_text(code)
            row = {
                "question_id": question_id,
                "passed": bool(passed_by_index.get(index, False)),
                "compile_passed": _compile_passed(code),
                "prediction_sha256": prediction_hash,
                "output_sha256": prediction_hash,
            }
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
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
    parser.add_argument("--worker-count", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--unsafe-authorized", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(
            dataset_path=args.dataset,
            harness_root=args.harness_root,
            samples_path=args.samples,
            output_path=args.output,
            worker_count=args.worker_count,
            timeout_seconds=args.timeout_seconds,
            unsafe_authorized=bool(args.unsafe_authorized),
        )
    except Exception as exc:  # noqa: BLE001 - do not leak private evaluator details.
        sys.stderr.write(f"livecodebench_runner_failed:{type(exc).__name__}\n")
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through the bridge process
    raise SystemExit(main())
