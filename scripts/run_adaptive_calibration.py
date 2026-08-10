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
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from axio_fusion_api.adaptive_calibration import (
    CalibrationSnapshot,
    build_recalibration_decision,
    build_recalibration_prompt,
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

    previous = json.loads(args.previous_manifest.read_text(encoding="utf-8"))
    current = json.loads(args.current_manifest.read_text(encoding="utf-8"))
    changed = detect_channel_change(previous, current)

    fusion_scores = {}
    if args.fusion_scores and args.fusion_scores.exists():
        fusion_scores = json.loads(args.fusion_scores.read_text(encoding="utf-8"))
    baseline_scores = {}
    if args.baseline_scores and args.baseline_scores.exists():
        baseline_scores = json.loads(args.baseline_scores.read_text(encoding="utf-8"))

    snapshots = []
    for model, score in fusion_scores.items():
        if isinstance(score, (int, float)):
            snapshots.append(
                CalibrationSnapshot(
                    model=model,
                    weighted_score=float(score),
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

    if snapshots:
        decision = build_recalibration_decision(
            snapshots,
            baseline_map=baseline_scores,
            channel_changed=changed,
            previous_channel_digest="",
            current_channel_digest="",
        )
    elif changed:
        decision = {
            "schema": "axio_fusion_api.adaptive_calibration.v1",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel_changed": True,
            "previous_channel_digest_sha256": "",
            "current_channel_digest_sha256": "",
            "needs_recalibration": True,
            "reasons": ["渠道配置已变更, 需运行28题校准确认融合质量"],
            "evaluations": [],
            "raw_scores_persisted": False,
            "secrets_persisted": False,
        }
    else:
        decision = {
            "schema": "axio_fusion_api.adaptive_calibration.v1",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel_changed": False,
            "previous_channel_digest_sha256": "",
            "current_channel_digest_sha256": "",
            "needs_recalibration": False,
            "reasons": ["渠道配置未变更且未提供校准得分, 无需重校准"],
            "evaluations": [],
            "raw_scores_persisted": False,
            "secrets_persisted": False,
        }

    if decision["needs_recalibration"] and snapshots:
        prompt = build_recalibration_prompt(decision, current)
    elif decision["needs_recalibration"]:
        prompt = "当前缺少校准得分, 请先运行28题校准后再生成元提示词。"
    else:
        prompt = "无需重校准。"

    output = {
        "decision": decision,
        "recalibration_prompt": prompt,
        "raw_scores_persisted": False,
        "secrets_persisted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"渠道变更: {changed}")
    print(f"需要重校准: {decision['needs_recalibration']}")
    print(f"结果已保存: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
