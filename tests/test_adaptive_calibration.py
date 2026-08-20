"""自适应渠道校准模块测试。"""
from __future__ import annotations

from axio_fusion_api.adaptive_calibration import (
    CalibrationSnapshot,
    build_recalibration_decision,
    build_recalibration_prompt,
    build_recalibration_receipt,
    channel_fingerprint,
    detect_channel_change,
    evaluate_fusion_vs_baseline,
)


def test_detect_channel_change_returns_true_on_provider_change():
    previous = {
        "providers": [
            {"provider": "nvidia", "api_format": "chat", "models": [{"model": "m1"}]},
        ]
    }
    current = {
        "providers": [
            {"provider": "nvidia", "api_format": "chat", "models": [{"model": "m2"}]},
        ]
    }
    assert detect_channel_change(previous, current) is True


def test_detect_channel_change_returns_false_on_identical_channel():
    manifest = {
        "providers": [
            {"provider": "nvidia", "api_format": "chat", "models": [{"model": "m1"}]},
        ]
    }
    assert detect_channel_change(manifest, manifest) is False


def test_detect_channel_change_tracks_capability_transport_and_endpoint_binding():
    previous = {
        "providers": [
            {
                "provider": "nvidia",
                "api_format": "chat",
                "base_url": "https://provider-a.example/v1",
                "models": [
                    {
                        "model": "m1",
                        "capabilities": {"logic": 0.8},
                        "reasoning_transport": {
                            "status": "verified",
                            "transport": "chat_reasoning_effort",
                            "supported_efforts": ["low", "high"],
                        },
                        "tool_calling_eligible": False,
                    }
                ],
            }
        ]
    }
    current = {
        "providers": [
            {
                "provider": "nvidia",
                "api_format": "chat",
                "base_url": "https://provider-b.example/v1",
                "models": [
                    {
                        "model": "m1",
                        "capabilities": {"logic": 0.9},
                        "reasoning_transport": {
                            "status": "verified",
                            "transport": "chat_reasoning_effort",
                            "supported_efforts": ["low", "medium", "high"],
                        },
                        "tool_calling_eligible": True,
                    }
                ],
            }
        ]
    }
    assert detect_channel_change(previous, current) is True


def test_detect_channel_change_ignores_credential_rotation():
    previous = {
        "providers": [
            {
                "provider": "cpa",
                "api_format": "responses",
                "api_key_env": "CPA_KEY_OLD",
                "models": [{"model": "m1"}],
            }
        ]
    }
    current = {
        "providers": [
            {
                "provider": "cpa",
                "api_format": "responses",
                "api_key_env": "CPA_KEY_ROTATED",
                "models": [{"model": "m1"}],
            }
        ]
    }
    assert detect_channel_change(previous, current) is False


def test_evaluate_fusion_vs_baseline_above_threshold():
    result = evaluate_fusion_vs_baseline(0.95, 1.0, "axio-pro")
    assert result["ratio"] == 0.95
    assert result["needs_recalibration"] is False


def test_evaluate_fusion_vs_baseline_below_threshold():
    result = evaluate_fusion_vs_baseline(0.85, 1.0, "axio-pro")
    assert result["ratio"] == 0.85
    assert result["needs_recalibration"] is True


def test_build_recalibration_decision_triggers_on_degradation():
    snapshots = [
        CalibrationSnapshot("axio-pro", 0.80, "2026-08-10"),
        CalibrationSnapshot("axio-terra", 0.95, "2026-08-10"),
    ]
    decision = build_recalibration_decision(
        snapshots,
        baseline_map={"axio-pro": 1.0, "axio-terra": 1.0},
        channel_changed=True,
        previous_channel_digest="abc",
        current_channel_digest="def",
    )
    assert decision["needs_recalibration"] is True
    assert any("axio-pro" in reason for reason in decision["reasons"])


def test_build_recalibration_decision_does_not_trigger_when_healthy():
    snapshots = [
        CalibrationSnapshot("axio-pro", 0.95, "2026-08-10"),
    ]
    decision = build_recalibration_decision(
        snapshots,
        baseline_map={"axio-pro": 1.0},
        channel_changed=True,
        previous_channel_digest="abc",
        current_channel_digest="def",
    )
    assert decision["needs_recalibration"] is False
    assert any("未退化" in reason for reason in decision["reasons"])


def test_build_recalibration_prompt_contains_safe_channel_only():
    decision = {
        "needs_recalibration": True,
        "reasons": ["axio-pro 退化"],
        "evaluations": [],
    }
    channel = {
        "providers": [
            {
                "provider": "cpa",
                "api_format": "responses",
                "models": [{"model": "secret-model"}],
            }
        ]
    }
    prompt = build_recalibration_prompt(decision, channel)
    assert "secret-model" not in prompt
    assert "渠道摘要" in prompt
    assert "校准决策" in prompt


def test_build_recalibration_receipt_is_shadow_candidate_with_complete_bindings():
    previous = {
        "providers": [
            {"provider": "nvidia", "api_format": "chat", "models": [{"model": "m1"}]},
        ]
    }
    current = {
        "providers": [
            {"provider": "cpa", "api_format": "responses", "models": [{"model": "m2"}]},
        ]
    }
    decision = build_recalibration_decision(
        [CalibrationSnapshot("axio-pro", 0.80, "2026-08-10")],
        baseline_map={"axio-pro": 1.0},
        channel_changed=True,
        previous_channel_digest=channel_fingerprint(previous),
        current_channel_digest=channel_fingerprint(current),
    )
    receipt = build_recalibration_receipt(
        decision,
        previous_channel_manifest=previous,
        current_channel_manifest=current,
        registry_profile_set_sha256="a" * 64,
        rollback_policy_digest_sha256="b" * 64,
        prompt_pack_digest_sha256="c" * 64,
        workflow_digest_sha256="d" * 64,
        contamination_audit_digest_sha256="e" * 64,
    )

    assert receipt["status"] == "shadow_candidate"
    assert receipt["ready_for_review"] is True
    assert receipt["activation_ready"] is False
    assert len(receipt["prompt_sha256"]) == 64
    assert receipt["blockers"] == []
    assert receipt["promotion_gate"]["shadow_only"] is True
    assert receipt["promotion_gate"]["human_approval_required"] is True
    assert receipt["promotion_gate"]["automatic_activation_allowed"] is False
    assert receipt["raw_prompt_persisted"] is False
    assert receipt["raw_provider_names_persisted"] is False
    assert receipt["raw_provider_model_ids_persisted"] is False


def test_build_recalibration_receipt_blocks_digest_mismatch():
    manifest = {
        "providers": [
            {"provider": "cpa", "api_format": "responses", "models": [{"model": "m1"}]},
        ]
    }
    decision = {
        "schema": "axio_fusion_api.adaptive_calibration.v1",
        "channel_changed": True,
        "previous_channel_digest_sha256": "f" * 64,
        "current_channel_digest_sha256": channel_fingerprint(manifest),
        "needs_recalibration": True,
        "evaluations": [{"model": "axio-pro", "ratio": 0.8}],
        "reasons": ["退化"],
    }
    receipt = build_recalibration_receipt(
        decision,
        previous_channel_manifest=manifest,
        current_channel_manifest=manifest,
    )

    assert receipt["status"] == "blocked"
    assert "adaptive_calibration_previous_channel_digest_mismatch" in receipt["blockers"]
    assert receipt["activation_ready"] is False
