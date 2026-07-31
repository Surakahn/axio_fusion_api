from __future__ import annotations

import time

import pytest

from axio_fusion_api.process_boundary import IsolatedCallError, run_isolated_call


def _return_value(value: str) -> str:
    return value


def _sleep_forever() -> None:
    time.sleep(10.0)


def test_isolated_call_returns_picklable_result() -> None:
    assert run_isolated_call(_return_value, "bounded", deadline=2.0) == "bounded"


def test_isolated_call_terminates_child_at_deadline() -> None:
    started = time.monotonic()
    with pytest.raises(IsolatedCallError) as exc_info:
        run_isolated_call(_sleep_forever, deadline=0.1)

    assert exc_info.value.timed_out is True
    assert exc_info.value.code == "isolated_call_timeout"
    assert time.monotonic() - started < 2.0
