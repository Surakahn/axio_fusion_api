"""自适应渠道校准 - 渠道切换时检测融合质量并生成元提示词调整建议

只允许调整提示词/流程配置, 不允许修改系统代码。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .schemas import sha256_text

CALIBRATION_SCHEMA = "axio_fusion_api.adaptive_calibration.v1"
CHANNEL_CHANGE_REASON = "channel_change_detected"
FUSION_DEGRADATION_THRESHOLD = 0.90  # 融合低于单模型90%时触发重校准


@dataclass(frozen=True)
class CalibrationSnapshot:
    """一次校准的模型得分快照。"""

    model: str
    weighted_score: float
    timestamp: str


def detect_channel_change(
    previous_channel_manifest: Mapping[str, Any] | None,
    current_channel_manifest: Mapping[str, Any],
) -> bool:
    """检测渠道配置是否发生变化。

    比较渠道指纹(provider列表+模型列表+协议), 忽略API key等敏感值。
    """
    prev_digest = (
        _channel_fingerprint(previous_channel_manifest)
        if previous_channel_manifest
        else ""
    )
    current_digest = _channel_fingerprint(current_channel_manifest)
    return bool(prev_digest) and prev_digest != current_digest


def _channel_fingerprint(manifest: Mapping[str, Any]) -> str:
    """渠道指纹: provider + model + api_format 的有序哈希。"""
    providers = []
    for provider in manifest.get("providers", []):
        if not isinstance(provider, Mapping):
            continue
        provider_name = str(provider.get("provider") or provider.get("name") or "")
        models = [str(m.get("model") or "") for m in provider.get("models", []) if isinstance(m, Mapping)]
        api_format = str(provider.get("api_format") or "")
        providers.append(
            {"provider": provider_name, "models": sorted(models), "api_format": api_format}
        )
    return sha256_text(json.dumps(providers, sort_keys=True))


def evaluate_fusion_vs_baseline(
    fusion_score: float,
    baseline_score: float,
    model_name: str,
) -> dict[str, Any]:
    """计算融合模型相对单模型基线的能力保持率。"""
    ratio = fusion_score / max(baseline_score, 0.0001)
    needs_recalibration = ratio < FUSION_DEGRADATION_THRESHOLD
    return {
        "model": model_name,
        "fusion_score": round(fusion_score, 4),
        "baseline_score": round(baseline_score, 4),
        "ratio": round(ratio, 4),
        "needs_recalibration": needs_recalibration,
        "threshold": FUSION_DEGRADATION_THRESHOLD,
    }


def build_recalibration_decision(
    snapshots: Sequence[CalibrationSnapshot],
    *,
    baseline_map: Mapping[str, float],
    channel_changed: bool,
    previous_channel_digest: str,
    current_channel_digest: str,
) -> dict[str, Any]:
    """汇总校准结果, 决定是否需要重校准。

    仅在以下情况触发重校准:
    1. 渠道发生变化且融合质量低于单模型90%
    2. 日常运行中融合质量低于单模型90%
    """
    evaluations = []
    needs_recalibration = False
    reasons = []

    for snap in snapshots:
        baseline = baseline_map.get(snap.model)
        if baseline is None:
            continue
        evaluation = evaluate_fusion_vs_baseline(
            snap.weighted_score, baseline, snap.model
        )
        evaluations.append(evaluation)
        if evaluation["needs_recalibration"]:
            needs_recalibration = True
            reasons.append(
                f"{snap.model} 融合能力为单模型的 {evaluation['ratio']:.1%}"
            )

    if channel_changed and not needs_recalibration:
        reasons.append("渠道已变更但融合能力未退化, 无需调整")

    return {
        "schema": CALIBRATION_SCHEMA,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel_changed": channel_changed,
        "previous_channel_digest_sha256": previous_channel_digest,
        "current_channel_digest_sha256": current_channel_digest,
        "needs_recalibration": needs_recalibration,
        "reasons": reasons,
        "evaluations": evaluations,
        "raw_scores_persisted": False,
        "secrets_persisted": False,
    }


META_PROMPT = """你是 Axio Fusion 的渠道适配架构师。系统当前检测到融合质量相对单模型基线退化，需要调整融合提示词或 Harness 组合流程。

## 可调整范围
- 各角色的提示词（primary_solver / independent_solver / critic / judge / synthesizer）
- Harness 组件的构造和组合顺序
- 角色之间的信息传递格式
- 融合流程节点（如是否启用 critic、judge 的置信度阈值）

## 不可调整范围
- 系统运行代码（router.py、orchestrator.py、providers.py 等）
- 安全边界（API key 隔离、提示词注入防护、超时预算）
- 对外 API 格式

## 输入
- 当前渠道配置摘要（渠道变更内容、当前可用模型）
- 校准结果（每个融合模型 vs 对应单模型基线的得分）
- 退化最严重的任务类别和典型失败模式

## 输出要求
返回一个 JSON 配置块，包含：
1. `analysis`: 对退化根因的分析（1-3 句）
2. `prompt_adjustments`: 每个需要调整的角色提示词修改建议
3. `flow_adjustments`: 需要调整的流程节点和组合方式
4. `expected_impact`: 预期对哪些任务类别有提升

注意：不要为了调整而调整。如果融合质量仍然高于单模型 90%，不要触发重校准。所有修改必须可回滚，且保持安全边界不变。
"""


def build_recalibration_prompt(
    decision: Mapping[str, Any],
    channel_manifest: Mapping[str, Any],
    failure_examples: Sequence[Mapping[str, Any]] = (),
) -> str:
    """生成元提示词，交给最佳模型进行渠道适配调整。"""
    safe_channel = {
        "providers": [
            {
                "provider": p.get("provider") or p.get("name"),
                "api_format": p.get("api_format"),
                "model_count": len(
                    p.get("models", [])
                    if isinstance(p.get("models"), list)
                    else []
                ),
            }
            for p in channel_manifest.get("providers", [])
            if isinstance(p, Mapping)
        ]
    }
    failure_summary = [
        {
            "suite": item.get("suite"),
            "model": item.get("model"),
            "correct": item.get("correct"),
            "total": item.get("total"),
        }
        for item in failure_examples
        if isinstance(item, Mapping)
    ]
    return "\n\n".join(
        [
            META_PROMPT,
            f"## 校准决策\n{json.dumps(decision, ensure_ascii=False, indent=2)}",
            f"## 渠道摘要\n{json.dumps(safe_channel, ensure_ascii=False, indent=2)}",
            (
                f"## 典型失败案例\n{json.dumps(failure_summary, ensure_ascii=False, indent=2)}"
                if failure_summary
                else "## 典型失败案例\n暂无详细案例，请基于校准得分分析。"
            ),
        ]
    )
