"""Small runtime prerequisites shared by the public command entry points."""

from __future__ import annotations

import sys
from typing import TextIO


MINIMUM_PYTHON_VERSION = (3, 10)


def running_python_version() -> tuple[int, int]:
    """Return the interpreter major/minor pair without exposing environment state."""

    return int(sys.version_info[0]), int(sys.version_info[1])


def ensure_supported_python_runtime(
    *,
    version: tuple[int, int] | None = None,
    stderr: TextIO | None = None,
) -> bool:
    """Fail before provider I/O when the source tree runs on an unsupported Python."""

    detected = version or running_python_version()
    if detected >= MINIMUM_PYTHON_VERSION:
        return True
    stream = stderr or sys.stderr
    required = ".".join(str(value) for value in MINIMUM_PYTHON_VERSION)
    observed = ".".join(str(value) for value in detected)
    print(
        f"Axio Fusion requires Python {required} or newer; detected Python {observed}. "
        "Use Python 3.11 (or another supported interpreter) before running provider operations.",
        file=stream,
    )
    return False
