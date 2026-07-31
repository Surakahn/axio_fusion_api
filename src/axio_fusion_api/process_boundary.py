"""Killable process boundary for live control-plane network calls.

Python threads cannot guarantee recovery when a TLS wrapper remains blocked in
``poll(2)`` after its socket is closed by another thread.  Live pre-Fusion
control-plane calls therefore run in a short-lived child process.  A timeout
terminates only that child and turns the result into a normal, hash-safe
admission failure; ordinary injected test clients never need this boundary.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from typing import Any, Callable


class IsolatedCallError(RuntimeError):
    """A safe parent-side representation of a child-call failure."""

    def __init__(
        self,
        code: str,
        *,
        timed_out: bool = False,
        error_type: str = "",
        http_status: int | None = None,
    ) -> None:
        self.code = str(code or "isolated_call_failed")[:120]
        self.timed_out = bool(timed_out)
        self.error_type = str(error_type or "")[:80]
        self.http_status = http_status if isinstance(http_status, int) else None
        super().__init__(self.code)


def _isolated_worker(
    sender: Any,
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    try:
        result = target(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - child boundary
        payload = {
            "status": "error",
            "code": str(
                getattr(exc, "error_code", "")
                or getattr(exc, "code", "")
                or type(exc).__name__
            )[:120],
            "error_type": type(exc).__name__[:80],
            "http_status": (
                int(getattr(exc, "http_status"))
                if isinstance(getattr(exc, "http_status", None), int)
                else None
            ),
        }
        try:
            sender.send(payload)
        except (BrokenPipeError, EOFError, OSError):
            pass
    else:
        try:
            sender.send({"status": "ok", "result": result})
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        try:
            sender.close()
        except (OSError, EOFError):
            pass


def run_isolated_call(
    target: Callable[..., Any],
    *args: Any,
    deadline: float,
    **kwargs: Any,
) -> Any:
    """Run one picklable live operation with a hard parent-side deadline."""

    bounded_timeout = max(0.05, min(300.0, float(deadline)))
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_isolated_worker,
        args=(sender, target, tuple(args), dict(kwargs)),
    )
    process.daemon = False
    started = time.monotonic()
    try:
        process.start()
        sender.close()
        process.join(bounded_timeout)
        if process.is_alive():
            process.terminate()
            process.join(min(2.0, max(0.1, bounded_timeout / 10.0)))
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(1.0)
            raise IsolatedCallError(
                "isolated_call_timeout",
                timed_out=True,
                error_type="TimeoutError",
            )
        if not receiver.poll(0.2):
            raise IsolatedCallError(
                "isolated_child_no_result",
                error_type="ChildProcessError",
            )
        payload = receiver.recv()
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            payload = payload if isinstance(payload, dict) else {}
            raise IsolatedCallError(
                str(payload.get("code") or "isolated_child_failed"),
                error_type=str(payload.get("error_type") or "ChildProcessError"),
                http_status=payload.get("http_status"),
            )
        return payload.get("result")
    except IsolatedCallError:
        raise
    except (OSError, EOFError, ValueError, TypeError) as exc:
        raise IsolatedCallError(
            "isolated_process_start_failed",
            error_type=type(exc).__name__,
        ) from exc
    finally:
        try:
            sender.close()
        except (OSError, EOFError):
            pass
        try:
            receiver.close()
        except (OSError, EOFError):
            pass
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(1.0)
        process.close()
