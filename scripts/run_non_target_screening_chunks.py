#!/usr/bin/env python3
"""Resume the registered non-target baseline campaign in bounded chunks.

Credentials are read from the operator-owned credential file into the current
process environment only. The script writes safe campaign receipts and never
serializes credential values or provider outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_CREDENTIAL_FILE = Path("/home/he/VeilGuard/fusionapi能用的模型接口.txt")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--private-probe-file", required=True, type=Path)
    parser.add_argument(
        "--operational-admission-file",
        type=Path,
        default=None,
        help="Private long-request receipt bound to the screening plan.",
    )
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=DEFAULT_CREDENTIAL_FILE,
    )
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--max-tasks", type=int, default=2)
    parser.add_argument("--first-chunk", type=int, default=2)
    parser.add_argument("--max-chunks", type=int, default=49)
    return parser.parse_args()


def _load_credentials(path: Path) -> None:
    """Inject the current operator credentials without persisting their values."""

    text = path.read_text(encoding="utf-8")
    nvidia_keys = list(dict.fromkeys(re.findall(r"nvapi-[A-Za-z0-9_-]+", text)))
    token_keys = re.findall(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]+", text)
    if not nvidia_keys or not token_keys:
        raise RuntimeError("credential_file_parse_failed")
    os.environ["AXIO_NVIDIA_BASE_URL"] = "https://integrate.api.nvidia.com/v1"
    os.environ["AXIO_NVIDIA_API_KEYS"] = ",".join(nvidia_keys)
    os.environ["AXIO_TOKENAPIS_BASE_URL"] = "https://tokenapis.com/v1"
    os.environ["AXIO_TOKENAPIS_API_KEY"] = token_keys[-1]
    os.environ["AXIO_FUSION_NETWORK_MODE"] = "auto"
    os.environ["PYTHONUNBUFFERED"] = "1"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _run_chunk(args: argparse.Namespace, chunk: int) -> tuple[int, dict[str, Any]]:
    from axio_fusion_api.cli import main

    receipt = args.root / f"campaign_receipt.chunk-{chunk:02d}.safe.json"
    state = args.root / "campaign_state.private.json"
    sys.argv = [
        "axio-fusion-baseline-screening-strict",
        "--registry",
        str(args.registry),
        "baseline-screening-run",
        "--plan",
        str(args.plan),
        "--source-manifest",
        str(args.source_manifest),
        "--private-probe-file",
        str(args.private_probe_file),
        "--private-root",
        str(args.root / "private"),
        "--state-output",
        str(state),
        "--live",
        "--max-workers",
        str(max(1, args.max_workers)),
        "--max-tasks",
        str(max(1, args.max_tasks)),
    ]
    if args.operational_admission_file is not None:
        sys.argv.extend(
            [
                "--operational-admission-file",
                str(args.operational_admission_file),
            ]
        )
    sys.argv.extend(["--output", str(receipt)])
    try:
        exit_code = int(main())
    except SystemExit as exc:
        exit_code = int(exc.code or 0)
    return exit_code, _read_json(receipt)


def main() -> int:
    args = _parse_args()
    if args.first_chunk < 1 or args.max_chunks < args.first_chunk:
        raise SystemExit("invalid_chunk_range")
    args.root.mkdir(parents=True, exist_ok=True)
    _load_credentials(args.credentials_file)

    for chunk in range(args.first_chunk, args.max_chunks + 1):
        exit_code, receipt = _run_chunk(args, chunk)
        summary = {
            "chunk": chunk,
            "exit_code": exit_code,
            "status": receipt.get("status"),
            "completed_unit_count": receipt.get("completed_unit_count"),
            "failed_or_blocked_unit_count": receipt.get(
                "failed_or_blocked_unit_count"
            ),
            "planned_task_count": receipt.get("planned_task_count"),
            "ready_for_ranking": receipt.get("ready_for_ranking"),
            "reason_codes": receipt.get("reason_codes", []),
        }
        print(json.dumps(summary, ensure_ascii=True), flush=True)

        status = receipt.get("status")
        if status == "completed":
            return 0
        if status == "blocked":
            return 2
        completed = int(receipt.get("completed_unit_count") or 0)
        failed = int(receipt.get("failed_or_blocked_unit_count") or 0)
        planned = int(receipt.get("planned_task_count") or 0)
        if planned and completed + failed >= planned:
            return 0 if receipt.get("ready_for_ranking") is True else 2
        time.sleep(2)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
