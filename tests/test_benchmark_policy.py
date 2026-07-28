from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api.benchmark_policy import (  # noqa: E402
    BenchmarkPolicyError,
    benchmark_policy_receipt,
    load_benchmark_evaluation_policy,
    validate_benchmark_evaluation_policy,
)
from axio_fusion_api.evaluation import (  # noqa: E402
    _benchmark_public_api_payload,
    _claim_reasoning_gate,
    _provider_benchmark_reasoning_receipt,
)
from axio_fusion_api.registry import normalize_profile  # noqa: E402


def test_formal_policy_freezes_replacement_roster_and_max_contract():
    policy = load_benchmark_evaluation_policy()
    receipt = benchmark_policy_receipt(policy)

    assert policy["gpqa"]["status"] == "skipped"
    assert policy["replacement"] == {
        "benchmark_slot_id": "gpqa_diamond",
        "dataset_id": "mmlu_pro_stem",
        "explicitly_not_gpqa": True,
    }
    assert receipt["target_reasoning_effort"] == "max"
    assert receipt["native_max_required"] is True
    assert receipt["baseline_roster"]["axio-fast"]["model"] == "gpt-5.6-luna"


def test_policy_rejects_credentials_and_wrong_reasoning_order():
    policy = load_benchmark_evaluation_policy()

    with_secret = copy.deepcopy(policy)
    with_secret["provider_api_key"] = "must-not-be-accepted"
    with pytest.raises(BenchmarkPolicyError, match="credentials"):
        validate_benchmark_evaluation_policy(with_secret)

    wrong_order = copy.deepcopy(policy)
    wrong_order["reasoning"]["levels"] = ["low", "medium", "high", "max", "xhigh"]
    with pytest.raises(BenchmarkPolicyError, match="reasoning_level_order"):
        validate_benchmark_evaluation_policy(wrong_order)


def test_public_benchmark_surfaces_carry_one_logical_max_request():
    for api_format in ("chat/completions", "responses", "anthropic", "gemini"):
        _, payload = _benchmark_public_api_payload(
            model="axio-pro",
            api_format=api_format,
            prompt="fixture prompt",
            system="fixture system",
            task_type="logic_reasoning",
            max_output_tokens=32,
        )
        if api_format == "responses":
            assert payload["reasoning"] == {"effort": "max"}
        else:
            assert payload["reasoning_effort"] == "max"


def test_provider_reasoning_receipt_does_not_promote_max_to_native_when_mapped_to_high():
    profile = normalize_profile(
        {
            "provider": "fixture-provider",
            "model": "fixture-model",
            "api_format": "chat/completions",
            "reasoning_transport": {
                "status": "verified",
                "transport": "chat_reasoning_effort",
                "supported_efforts": ["low", "medium", "high"],
                "effort_map": {"max": "high"},
            },
        }
    )
    receipt = _provider_benchmark_reasoning_receipt(profile)

    assert receipt["requested_reasoning_effort"] == "max"
    assert receipt["effective_reasoning_effort"] == "high"
    assert receipt["native_reasoning_effort_verified"] is False
    assert receipt["status"] == "verified_transport_downgrade"


def test_claim_reasoning_gate_fails_closed_for_unverified_native_max():
    run = {
        "suite_id": "arc_challenge",
        "task_format": "multiple_choice",
        "reasoning_receipt": {
            "requested_reasoning_effort": "max",
            "effective_reasoning_effort": "high",
            "reasoning_transport": "chat_reasoning_effort",
            "native_reasoning_effort_verified": False,
            "status": "native_unverified",
        },
    }
    gate = _claim_reasoning_gate(
        run,
        required_reasoning_effort="max",
        native_max_required=True,
        suite_id="arc_challenge",
        task_format="multiple_choice",
    )

    assert gate["passed"] is False
    assert "provider_baseline_native_max_unverified" in gate["reason_codes"]
    assert "provider_baseline_effective_reasoning_effort_mismatch" in gate["reason_codes"]
