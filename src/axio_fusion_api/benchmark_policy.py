"""Versioned, secret-free policy for the formal benchmark campaign.

The policy is deliberately separate from provider credentials and benchmark
content.  It freezes the GPQA replacement disclosure, the comparison roster,
and the reasoning requirement that a formal superiority claim must satisfy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .schemas import normalize_reasoning_effort, sha256_text, stable_json


BENCHMARK_EVALUATION_POLICY_SCHEMA = "axio_fusion_api.benchmark_evaluation_policy.v1"
BENCHMARK_REASONING_LEVELS = ("low", "medium", "high", "xhigh", "max")
BENCHMARK_TARGET_REASONING_EFFORT = "max"
BENCHMARK_REPLACEMENT_DATASET_ID = "mmlu_pro_stem"


class BenchmarkPolicyError(ValueError):
    """Raised when a formal benchmark policy is malformed or unsafe."""


def default_benchmark_evaluation_policy() -> dict[str, Any]:
    """Return the immutable default policy as a fresh mapping."""

    return {
        "schema": BENCHMARK_EVALUATION_POLICY_SCHEMA,
        "gpqa": {
            "status": "skipped",
            "reason": "authorized GPQA access not available",
        },
        "replacement": {
            "benchmark_slot_id": "gpqa_diamond",
            "dataset_id": BENCHMARK_REPLACEMENT_DATASET_ID,
            "explicitly_not_gpqa": True,
        },
        "reasoning": {
            "levels": list(BENCHMARK_REASONING_LEVELS),
            "target_effort": BENCHMARK_TARGET_REASONING_EFFORT,
            "native_max_required": True,
            "fail_closed": True,
        },
        "baseline_roster": {
            "axio-pro": {
                "rank": 1,
                "model": "gpt-5.6-sol",
                "reasoning_effort": BENCHMARK_TARGET_REASONING_EFFORT,
            },
            "axio-terra": {
                "rank": 2,
                "model": "gpt-5.6-terra",
                "reasoning_effort": BENCHMARK_TARGET_REASONING_EFFORT,
            },
            "axio-fast": {
                "rank": 3,
                "model": "gpt-5.6-luna",
                "reasoning_effort": BENCHMARK_TARGET_REASONING_EFFORT,
            },
        },
    }


def default_benchmark_evaluation_policy_path() -> Path:
    """Return the repository-local, tracked policy template path."""

    return Path(__file__).resolve().parents[2] / "config" / "benchmark_evaluation_policy.example.json"


def load_benchmark_evaluation_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate a formal policy without reading credentials.

    A missing default template falls back to the same in-code contract so the
    library remains usable from an installed wheel.  An explicitly supplied
    path is fail-closed when it is missing or invalid.
    """

    selected = Path(path) if path is not None else default_benchmark_evaluation_policy_path()
    if selected.exists():
        try:
            loaded = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BenchmarkPolicyError("benchmark_policy_unreadable") from exc
    elif path is not None:
        raise BenchmarkPolicyError("benchmark_policy_not_found")
    else:
        loaded = default_benchmark_evaluation_policy()
    return validate_benchmark_evaluation_policy(loaded)


def validate_benchmark_evaluation_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the small policy surface used by the formal campaign."""

    if not isinstance(value, Mapping):
        raise BenchmarkPolicyError("benchmark_policy_not_object")
    policy = json.loads(json.dumps(dict(value), ensure_ascii=False))
    if str(policy.get("schema") or "") != BENCHMARK_EVALUATION_POLICY_SCHEMA:
        raise BenchmarkPolicyError("benchmark_policy_schema_invalid")

    gpqa = policy.get("gpqa") if isinstance(policy.get("gpqa"), Mapping) else {}
    if str(gpqa.get("status") or "") != "skipped":
        raise BenchmarkPolicyError("gpqa_must_be_explicitly_skipped")

    replacement = policy.get("replacement") if isinstance(policy.get("replacement"), Mapping) else {}
    if (
        str(replacement.get("benchmark_slot_id") or "") != "gpqa_diamond"
        or str(replacement.get("dataset_id") or "") != BENCHMARK_REPLACEMENT_DATASET_ID
        or replacement.get("explicitly_not_gpqa") is not True
    ):
        raise BenchmarkPolicyError("gpqa_replacement_disclosure_invalid")

    reasoning = policy.get("reasoning") if isinstance(policy.get("reasoning"), Mapping) else {}
    levels = tuple(str(item or "").strip().casefold() for item in reasoning.get("levels", ()))
    if levels != BENCHMARK_REASONING_LEVELS:
        raise BenchmarkPolicyError("reasoning_level_order_invalid")
    if normalize_reasoning_effort(reasoning.get("target_effort")) != BENCHMARK_TARGET_REASONING_EFFORT:
        raise BenchmarkPolicyError("benchmark_target_reasoning_effort_invalid")
    if reasoning.get("native_max_required") is not True or reasoning.get("fail_closed") is not True:
        raise BenchmarkPolicyError("native_max_fail_closed_contract_invalid")

    roster = policy.get("baseline_roster") if isinstance(policy.get("baseline_roster"), Mapping) else {}
    expected = {
        "axio-pro": (1, "gpt-5.6-sol"),
        "axio-terra": (2, "gpt-5.6-terra"),
        "axio-fast": (3, "gpt-5.6-luna"),
    }
    if set(roster) != set(expected):
        raise BenchmarkPolicyError("baseline_roster_models_invalid")
    for public_model, (rank, model_name) in expected.items():
        row = roster.get(public_model)
        if not isinstance(row, Mapping):
            raise BenchmarkPolicyError("baseline_roster_row_invalid")
        if int(row.get("rank") or 0) != rank or str(row.get("model") or "") != model_name:
            raise BenchmarkPolicyError("baseline_roster_rank_or_model_invalid")
        if normalize_reasoning_effort(row.get("reasoning_effort")) != BENCHMARK_TARGET_REASONING_EFFORT:
            raise BenchmarkPolicyError("baseline_roster_reasoning_effort_invalid")

    _reject_secret_like_keys(policy)
    return policy


def benchmark_policy_reasoning_config_sha256(
    suite_id: str,
    task_format: str,
    *,
    policy: Mapping[str, Any] | None = None,
) -> str:
    """Hash the public reasoning contract, never a request or model output."""

    selected = validate_benchmark_evaluation_policy(
        policy if isinstance(policy, Mapping) else default_benchmark_evaluation_policy()
    )
    reasoning = selected["reasoning"]
    payload = {
        "schema": "axio_fusion_api.benchmark_reasoning_config.v1",
        "suite_id": str(suite_id or ""),
        "task_format": str(task_format or ""),
        "levels": list(reasoning["levels"]),
        "target_effort": str(reasoning["target_effort"]),
        "native_max_required": reasoning.get("native_max_required") is True,
        "fail_closed": reasoning.get("fail_closed") is True,
    }
    return sha256_text(stable_json(payload))


def benchmark_policy_receipt(policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a safe policy receipt suitable for campaign artifacts."""

    selected = validate_benchmark_evaluation_policy(
        policy if isinstance(policy, Mapping) else default_benchmark_evaluation_policy()
    )
    reasoning = selected["reasoning"]
    roster = selected["baseline_roster"]
    return {
        "schema": "axio_fusion_api.benchmark_policy_receipt.v1",
        "policy_schema": selected["schema"],
        "policy_sha256": sha256_text(stable_json(selected)),
        "gpqa_status": selected["gpqa"]["status"],
        "gpqa_replacement_dataset_id": selected["replacement"]["dataset_id"],
        "gpqa_replacement_explicitly_not_gpqa": selected["replacement"]["explicitly_not_gpqa"] is True,
        "reasoning_levels": list(reasoning["levels"]),
        "target_reasoning_effort": str(reasoning["target_effort"]),
        "native_max_required": reasoning["native_max_required"] is True,
        "fail_closed": reasoning["fail_closed"] is True,
        "baseline_roster": {
            model: {
                "rank": int(row["rank"]),
                "model": str(row["model"]),
                "reasoning_effort": str(row["reasoning_effort"]),
            }
            for model, row in sorted(roster.items())
            if isinstance(row, Mapping)
        },
        "raw_api_keys_persisted": False,
        "raw_base_urls_persisted": False,
        "raw_benchmark_content_persisted": False,
        "secrets_persisted": False,
    }


def _reject_secret_like_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key or "").casefold().replace("-", "_")
            if any(token in normalized for token in ("api_key", "apikey", "secret", "credential", "base_url", "token")):
                raise BenchmarkPolicyError("benchmark_policy_must_not_contain_credentials")
            _reject_secret_like_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_like_keys(nested)
