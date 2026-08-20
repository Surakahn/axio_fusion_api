"""自适应渠道校准 - 渠道切换时检测融合质量并生成元提示词调整建议

只允许调整提示词/流程配置, 不允许修改系统代码。
"""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .schemas import sha256_text, stable_json

CALIBRATION_SCHEMA = "axio_fusion_api.adaptive_calibration.v1"
CALIBRATION_RECEIPT_SCHEMA = "axio_fusion_api.adaptive_calibration_receipt.v1"
CHANNEL_CHANGE_REASON = "channel_change_detected"
FUSION_DEGRADATION_THRESHOLD = 0.90  # 融合低于单模型90%时触发重校准

_CHANNEL_MODEL_SCALAR_FIELDS = (
    "model",
    "id",
    "name",
    "api_format",
    "protocol",
    "tool_capability",
    "tool_capability_source",
    "tool_probe_status",
    "tool_calling_eligible",
    "supports_tools",
    "supports_vision",
    "vision_input_eligible",
    "vision_probe_status",
    "vision_capability_source",
    "context_tokens",
    "p50_latency_ms",
    "p95_latency_ms",
    "input_cost_per_million",
    "output_cost_per_million",
)
_CHANNEL_ENDPOINT_FIELDS = ("base_url", "endpoint", "base_url_env", "endpoint_env")


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

    比较安全白名单渠道指纹。模型的 reasoning/tool/vision 能力、时延/成本
    元数据以及 endpoint binding 变化都会触发重校准；API key 轮换不会触发。
    """
    prev_digest = (
        _channel_fingerprint(previous_channel_manifest)
        if previous_channel_manifest
        else ""
    )
    current_digest = _channel_fingerprint(current_channel_manifest)
    return bool(prev_digest) and prev_digest != current_digest


def channel_fingerprint(manifest: Mapping[str, Any] | None) -> str:
    """返回只由安全白名单字段计算出的渠道指纹。"""

    return _channel_fingerprint(manifest if isinstance(manifest, Mapping) else {})


def _channel_fingerprint(manifest: Mapping[str, Any]) -> str:
    """生成不含密钥和原始 endpoint 的稳定渠道指纹。"""

    providers: list[dict[str, Any]] = []
    if not isinstance(manifest, Mapping):
        return sha256_text(
            stable_json(
                {"schema": "axio_fusion_api.channel_fingerprint.v2", "providers": []}
            )
        )
    provider_rows = manifest.get("providers", [])
    if not isinstance(provider_rows, list):
        provider_rows = []
    for provider in provider_rows:
        if not isinstance(provider, Mapping):
            continue
        row: dict[str, Any] = {
            "provider": str(provider.get("provider") or provider.get("name") or ""),
            "api_format": str(provider.get("api_format") or ""),
            "protocol": str(provider.get("protocol") or ""),
        }
        _add_endpoint_hashes(row, provider)
        model_rows = provider.get("models", [])
        if not isinstance(model_rows, list):
            model_rows = []
        row["models"] = sorted(
            (_safe_model_fingerprint(model, row["api_format"]) for model in model_rows),
            key=stable_json,
        )
        providers.append(row)
    providers.sort(key=stable_json)
    return sha256_text(stable_json({"schema": "axio_fusion_api.channel_fingerprint.v2", "providers": providers}))


def _safe_model_fingerprint(value: Any, provider_api_format: str) -> dict[str, Any]:
    """保留校准相关的非敏感模型元数据，不把任意配置写入指纹。"""

    if not isinstance(value, Mapping):
        return {"model": str(value or "")[:160], "api_format": provider_api_format}
    row: dict[str, Any] = {}
    for field in _CHANNEL_MODEL_SCALAR_FIELDS:
        scalar = _safe_scalar(value.get(field))
        if scalar is not None:
            row[field] = scalar
    if "api_format" not in row and provider_api_format:
        row["api_format"] = provider_api_format
    capabilities = value.get("capabilities")
    if isinstance(capabilities, Mapping):
        numeric = {
            str(key): round(float(item), 8)
            for key, item in capabilities.items()
            if isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
        }
        if numeric:
            row["capabilities"] = dict(sorted(numeric.items()))
    reasoning = value.get("reasoning_transport")
    if isinstance(reasoning, Mapping):
        effort_map = reasoning.get("effort_map", {})
        if not isinstance(effort_map, Mapping):
            effort_map = {}
        supported_efforts = reasoning.get("supported_efforts", [])
        if not isinstance(supported_efforts, (list, tuple, set, frozenset)):
            supported_efforts = []
        row["reasoning_transport"] = {
            "status": str(reasoning.get("status") or ""),
            "transport": str(reasoning.get("transport") or ""),
            "supported_efforts": sorted(
                str(item) for item in supported_efforts
                if isinstance(item, (str, int, float))
            ),
            "effort_map": {
                str(key): str(item)
                for key, item in sorted(effort_map.items(), key=lambda pair: str(pair[0]))
                if isinstance(key, (str, int, float)) and isinstance(item, (str, int, float))
            },
        }
    _add_endpoint_hashes(row, value)
    return row


def _add_endpoint_hashes(target: dict[str, Any], value: Mapping[str, Any]) -> None:
    for field in _CHANNEL_ENDPOINT_FIELDS:
        raw = value.get(field)
        if raw not in (None, ""):
            target[f"{field}_sha256"] = sha256_text(str(raw))


def _safe_scalar(value: Any) -> bool | float | int | str | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        numeric = float(value)
        return round(numeric, 8) if math.isfinite(numeric) else None
    if isinstance(value, str):
        return value[:160]
    return None


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


def build_recalibration_receipt(
    decision: Mapping[str, Any] | None,
    *,
    previous_channel_manifest: Mapping[str, Any] | None,
    current_channel_manifest: Mapping[str, Any],
    registry_profile_set_sha256: str = "",
    rollback_policy_digest_sha256: str = "",
    prompt_pack_digest_sha256: str = "",
    workflow_digest_sha256: str = "",
    contamination_audit_digest_sha256: str = "",
) -> dict[str, Any]:
    """构建不含 prompt 原文的 shadow 校准凭证。

    该凭证只允许描述候选状态，不能直接激活任何生产 prompt 或路由策略。
    缺少 registry、workflow、rollback、prompt pack 或 contamination 绑定时
    必须保持 blocked，避免把一次渠道变化误当成可发布的自我改进。
    """

    decision = decision if isinstance(decision, Mapping) else {}
    previous_digest = channel_fingerprint(previous_channel_manifest)
    current_digest = channel_fingerprint(current_channel_manifest)
    requested = decision.get("needs_recalibration") is True
    blockers: list[str] = []
    expected_previous = str(decision.get("previous_channel_digest_sha256") or "")
    expected_current = str(decision.get("current_channel_digest_sha256") or "")
    if expected_previous and expected_previous != previous_digest:
        blockers.append("adaptive_calibration_previous_channel_digest_mismatch")
    if expected_current and expected_current != current_digest:
        blockers.append("adaptive_calibration_current_channel_digest_mismatch")
    if requested:
        for value, reason in (
            (registry_profile_set_sha256, "adaptive_calibration_registry_binding_missing"),
            (rollback_policy_digest_sha256, "adaptive_calibration_rollback_target_missing"),
            (prompt_pack_digest_sha256, "adaptive_calibration_prompt_pack_binding_missing"),
            (workflow_digest_sha256, "adaptive_calibration_workflow_binding_missing"),
            (contamination_audit_digest_sha256, "adaptive_calibration_contamination_binding_missing"),
        ):
            if not _looks_like_sha256(value):
                blockers.append(reason)
        if not decision.get("evaluations"):
            blockers.append("adaptive_calibration_operational_evidence_missing")
    prompt_digest = ""
    if requested and decision.get("evaluations"):
        try:
            prompt_digest = sha256_text(
                build_recalibration_prompt(decision, current_channel_manifest)
            )
        except (AttributeError, TypeError, ValueError):
            blockers.append("adaptive_calibration_prompt_generation_failed")
    receipt = {
        "schema": CALIBRATION_RECEIPT_SCHEMA,
        "status": "not_required" if not requested else "shadow_candidate" if not blockers else "blocked",
        "decision": _safe_decision_projection(decision),
        "channel_changed": decision.get("channel_changed") is True,
        "previous_channel_fingerprint_sha256": previous_digest,
        "current_channel_fingerprint_sha256": current_digest,
        "decision_digest_sha256": sha256_text(
            stable_json(_safe_decision_projection(decision))
        ),
        "prompt_sha256": prompt_digest,
        "registry_profile_set_sha256": _validated_digest(registry_profile_set_sha256),
        "rollback_policy_digest_sha256": _validated_digest(rollback_policy_digest_sha256),
        "prompt_pack_digest_sha256": _validated_digest(prompt_pack_digest_sha256),
        "workflow_digest_sha256": _validated_digest(workflow_digest_sha256),
        "contamination_audit_digest_sha256": _validated_digest(
            contamination_audit_digest_sha256
        ),
        "ready_for_review": requested and not blockers,
        "activation_ready": False,
        "blockers": sorted(set(blockers)),
        "promotion_gate": {
            "eligible": False,
            "shadow_only": True,
            "human_approval_required": True,
            "registry_binding_required": True,
            "rollback_target_required": True,
            "prompt_pack_review_required": True,
            "workflow_review_required": True,
            "contamination_audit_required": True,
            "target_benchmark_data_allowed": False,
            "automatic_activation_allowed": False,
        },
        "raw_prompt_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    receipt["receipt_digest_sha256"] = sha256_text(
        stable_json(_recalibration_receipt_digest_input(receipt))
    )
    return receipt


def _safe_decision_projection(decision: Mapping[str, Any]) -> dict[str, Any]:
    evaluations = decision.get("evaluations")
    rows = evaluations if isinstance(evaluations, list) else []
    return {
        "schema": str(decision.get("schema") or ""),
        "channel_changed": decision.get("channel_changed") is True,
        "previous_channel_digest_sha256": _validated_digest(
            decision.get("previous_channel_digest_sha256")
        ),
        "current_channel_digest_sha256": _validated_digest(
            decision.get("current_channel_digest_sha256")
        ),
        "needs_recalibration": decision.get("needs_recalibration") is True,
        "evaluation_count": len(rows),
        "evaluation_model_hashes": sorted(
            sha256_text(str(row.get("model") or ""))
            for row in rows
            if isinstance(row, Mapping) and row.get("model")
        ),
        "evaluation_ratios": [
            _safe_number(row.get("ratio"))
            for row in rows
            if isinstance(row, Mapping) and _safe_number(row.get("ratio")) is not None
        ],
        "reason_hashes": sorted(
            sha256_text(str(reason))
            for reason in decision.get("reasons", [])
            if reason
        ),
    }


def _recalibration_receipt_digest_input(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: receipt.get(key)
        for key in (
            "schema",
            "status",
            "channel_changed",
            "previous_channel_fingerprint_sha256",
            "current_channel_fingerprint_sha256",
            "decision_digest_sha256",
            "prompt_sha256",
            "registry_profile_set_sha256",
            "rollback_policy_digest_sha256",
            "prompt_pack_digest_sha256",
            "workflow_digest_sha256",
            "contamination_audit_digest_sha256",
            "ready_for_review",
            "activation_ready",
            "blockers",
            "promotion_gate",
        )
    }


def _validated_digest(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if _looks_like_sha256(text) else ""


def _looks_like_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").strip().lower()))


def _safe_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(numeric, 6) if math.isfinite(numeric) else None


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
