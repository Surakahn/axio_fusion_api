"""受限并行执行，支持硬截止时间且不等待超时任务。"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping, Sequence


def run_parallel_with_deadline(
    tasks: Sequence[tuple[int, Callable[[], Any]]],
    timeout_seconds: float,
    grace_seconds: float = 10.0,
) -> tuple[Mapping[int, Any], set[int]]:
    """并发执行任务并在硬截止时间后返回已完成结果。

    超时任务留在 daemon 线程中自然结束，不阻塞主流程。每个任务返回
    ``None`` 表示执行失败；调用方自行区分失败与超时。
    """
    completed: dict[int, Any] = {}
    lock = threading.Lock()

    def run_one(task_id: int, task: Callable[[], Any]) -> None:
        try:
            result = task()
        except Exception:
            result = None
        with lock:
            completed[task_id] = result

    threads = []
    for task_id, task in tasks:
        thread = threading.Thread(
            target=run_one,
            args=(task_id, task),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    deadline = time.monotonic() + timeout_seconds + grace_seconds
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(remaining)

    with lock:
        completed_keys = set(completed)
    pending = {task_id for task_id, _ in tasks} - completed_keys
    return {task_id: completed[task_id] for task_id in completed_keys}, pending
