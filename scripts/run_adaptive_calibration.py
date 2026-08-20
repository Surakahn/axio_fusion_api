#!/usr/bin/env python3
"""自适应渠道校准运行器

用法:
  python3 scripts/run_adaptive_calibration.py \
    --previous-manifest config/previous_channels.json \
    --current-manifest config/current_channels.json \
    --output private/adaptive_calibration_result.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from axio_fusion_api.adaptive_calibration import (
    CalibrationSnapshot,
    build_recalibration_receipt,
    build_recalibration_decision,
    channel_fingerprint,
    detect_channel_change,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Axio Fusion 自适应渠道校准")
    parser.add_argument("--previous-manifest", required=True, type=Path)
    parser.add_argument("--current-manifest", required=True, type=Path)
    parser.add_argument("--fusion-scores", type=Path, help="校准得分文件 (JSON)")
    parser.add_argument("--baseline-scores", type=Path, help="基线得分文件 (JSON)")
    parser.add_argument("--output", type=Path, default=Path("private/adaptive_calibration_result.json"))
    args = parser.parse_args()

    try:
        previous = _load_mapping(args.previous_manifest, "previous manifest")
        current = _load_mapping(args.current_manifest, "current manifest")
        fusion_scores = _load_optional_mapping(args.fusion_scores, "fusion scores")
        baseline_scores = _load_optional_mapping(args.baseline_scores, "baseline scores")
    except ValueError as exc:
        parser.error(str(exc))
    changed = detect_channel_change(previous, current)
    previous_digest = channel_fingerprint(previous)
    current_digest = channel_fingerprint(current)
    snapshots = _build_snapshots(fusion_scores)

    if snapshots:
        decision = build_recalibration_decision(
            snapshots,
            baseline_map=baseline_scores,
            channel_changed=changed,
            previous_channel_digest=previous_digest,
            current_channel_digest=current_digest,
        )
    elif changed:
        decision = _decision_without_scores(
            channel_changed=True,
            previous_digest=previous_digest,
            current_digest=current_digest,
            needs_recalibration=True,
            reason="渠道配置已变更, 需运行28题校准确认融合质量",
        )
    else:
        decision = _decision_without_scores(
            channel_changed=False,
            previous_digest=previous_digest,
            current_digest=current_digest,
            needs_recalibration=False,
            reason="渠道配置未变更且未提供校准得分, 无需重校准",
        )
    receipt = build_recalibration_receipt(
        decision,
        previous_channel_manifest=previous,
        current_channel_manifest=current,
    )

    output = {
        "decision": receipt["decision"],
        "recalibration_receipt": receipt,
        "recalibration_prompt_sha256": receipt["prompt_sha256"],
        "recalibration_prompt_persisted": False,
        "raw_scores_persisted": False,
        "secrets_persisted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"渠道变更: {changed}")
    print(f"需要重校准: {decision['needs_recalibration']}")
    print(f"校准凭证状态: {receipt['status']}")
    print(f"结果已保存: {args.output}")
    return 0


def _load_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}读取失败: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label}必须是JSON对象")
    return payload


def _load_optional_mapping(path: Path | None, label: str) -> Mapping[str, Any]:
    if path is None:
        return {}
    return _load_mapping(path, label)


def _build_snapshots(scores: Mapping[str, Any]) -> list[CalibrationSnapshot]:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    return [
        CalibrationSnapshot(model=str(model), weighted_score=float(score), timestamp=timestamp)
        for model, score in scores.items()
        if isinstance(model, str)
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(float(score))
    ]


def _decision_without_scores(
    *,
    channel_changed: bool,
    previous_digest: str,
    current_digest: str,
    needs_recalibration: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.adaptive_calibration.v1",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel_changed": channel_changed,
        "previous_channel_digest_sha256": previous_digest,
        "current_channel_digest_sha256": current_digest,
        "needs_recalibration": needs_recalibration,
        "reasons": [reason],
        "evaluations": [],
        "raw_scores_persisted": False,
        "secrets_persisted": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
