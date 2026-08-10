"""受限并行执行模块功能测试。"""
from __future__ import annotations

import time

from axio_fusion_api.benchmark_execution import run_parallel_with_deadline


def test_returns_completed_and_pending_after_deadline() -> None:
    def fast() -> str:
        return "ok"

    def slow() -> str:
        time.sleep(5)
        return "late"

    results, pending = run_parallel_with_deadline(
        [(1, fast), (2, slow)],
        timeout_seconds=0.1,
        grace_seconds=0.1,
    )

    assert results == {1: "ok"}
    assert pending == {2}


def test_returns_failure_as_none() -> None:
    def broken() -> str:
        raise RuntimeError("boom")

    results, pending = run_parallel_with_deadline([(1, broken)], timeout_seconds=1)

    assert results == {1: None}
    assert pending == set()
