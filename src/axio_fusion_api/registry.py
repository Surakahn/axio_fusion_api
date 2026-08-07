from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .latency_policy import (
    measured_stream_latency_eligibility,
    row_latency_eligibility,
    streaming_evidence_eligibility,
)
from .prefusion_ranking import (
    PREFUSION_BROAD_CAPABILITY_AXIS_MIN_NONZERO,
    PREFUSION_BROAD_CAPABILITY_OVERALL_THRESHOLD,
    PREFUSION_CAPABILITY_AXIS_MIN_NONZERO,
    PREFUSION_OPERATIONAL_RANKING_SCHEMA,
    PREFUSION_OPERATIONAL_RANKING_WEIGHTS,
    capability_axis_coverage,
    operational_score,
    research_quality_score,
)
from .schemas import CAPABILITY_AXES, ModelProfile, is_sha256_digest, sha256_text, stable_json


FUSION_PROVIDER_INPUT_API_FORMATS = ("chat", "responses", "anthropic", "gemini")
FUSION_PORTFOLIO_CATEGORY_AXES = {
    "science_knowledge": ("science_knowledge", "critique"),
    "multilingual": ("multilingual", "long_context"),
    "code": ("code", "logic", "structured_output"),
    "math": ("math", "logic", "critique"),
    "logic": ("logic", "critique"),
    "agentic_tool_calling": ("agentic_tool_calling", "structured_output"),
    "daily_work": ("daily_work", "structured_output"),
    "hallucination_factuality": ("critique", "science_knowledge", "structured_output"),
    "vertical_domain": ("science_knowledge", "logic", "daily_work", "long_context"),
}
FUSION_PORTFOLIO_CATEGORY_THRESHOLD = 0.65
FUSION_PORTFOLIO_STRONG_MODEL_THRESHOLD = 0.66
FUSION_PORTFOLIO_ROLE_THRESHOLD = 0.65

# ── Auxiliary model exclusions ────────────────────────────────────────────
# Models that are internal tool agents, not general-purpose LLMs suitable
# for fusion. They are excluded from the serving registry and never routed
# as fusion experts, judges, or synthesizers.
_AUXILIARY_MODEL_PATTERNS: tuple[str, ...] = (
    "codex-auto-review",
    "gpt-image-1",
    "gpt-image-2",
)
_AUXILIARY_MODEL_SUBSTRINGS: tuple[str, ...] = (
    "gpt-image-",
)


def _is_auxiliary_model(model: str) -> bool:
    model_lower = model.lower()
    for pattern in _AUXILIARY_MODEL_PATTERNS:
        if pattern in model_lower:
            return True
    for substr in _AUXILIARY_MODEL_SUBSTRINGS:
        if substr in model_lower:
            return True
    return False


# Keep this control-plane enum local to the registry validator. Importing the
# screening module here would create a cycle, and a loadable registry must be
# able to verify its own handoff without trusting the report process.
_PREFUSION_ROLE_NAMES = (
    "primary_solver",
    "independent_solver",
    "critic",
    "domain_specialist",
    "judge",
    "synthesizer",
    "structured_extraction",
    "simple_classification",
    "short_verification",
    "single_tool_argument_validation",
)
_PREFUSION_REQUIRED_ROLES = (
    "primary_solver",
    "judge",
    "synthesizer",
)
_PREFUSION_OPERATIONAL_ROLE_PROBE_ROLES = (
    "primary_solver",
    "critic",
    "judge",
    "synthesizer",
    "structured_extraction",
    "simple_classification",
    "short_verification",
    "single_tool_argument_validation",
)
# r20 was generated after the narrow-role probe expansion but before the
# primary-solver role and repeated role-level samples were added. Keep this
# exact shape readable for rollback/migration; it remains a single-sample
# operational receipt and cannot satisfy the current role-calibration contract.
_PRE_ROLE_CALIBRATION_OPERATIONAL_ROLE_PROBE_ROLES = (
    "critic",
    "judge",
    "synthesizer",
    "structured_extraction",
    "simple_classification",
    "short_verification",
    "single_tool_argument_validation",
)
_LEGACY_OPERATIONAL_ROLE_PROBE_ROLES = (
    "critic",
    "judge",
    "synthesizer",
)


_PROVIDER_CONFIG_INLINE_ENV_NAMES = (
    "AXIO_FUSION_PROVIDER_CONFIGS",
    "AXIO_FUSION_PROVIDERS_JSON",
)
_PROVIDER_CONFIG_FILE_ENV_NAME = "AXIO_FUSION_PROVIDER_CONFIG_FILE"
_PROVIDER_CONFIG_MAX_FILE_BYTES = 2 * 1024 * 1024
_ENVIRONMENT_VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUPPORTED_PROVIDER_API_FORMATS = frozenset(
    {"chat", "responses", "anthropic", "gemini"}
)
_API_FORMAT_ALIASES = {
    "chat": "chat",
    "chat/completion": "chat",
    "chat/completions": "chat",
    "chat-completions": "chat",
    "openai": "chat",
    "openai-chat": "chat",
    "responses": "responses",
    "responses-api": "responses",
    "response": "responses",
    "anthropic": "anthropic",
    "anthropic/messages": "anthropic",
    "anthropic-messages": "anthropic",
    "messages": "anthropic",
    "claude": "anthropic",
    "gemini/generatecontent": "gemini",
    "gemini/generate-content": "gemini",
    "google-gemini": "gemini",
    "google/gemini": "gemini",
    "google": "gemini",
    "gemini": "gemini",
}


def build_default_registry() -> dict[str, Any]:
    """Return a portable default registry with no secrets or raw endpoints."""

    models = [
        _profile(
            provider="nvidia",
            model="openai/gpt-oss-120b",
            api_format="chat",
            capabilities={
                "science_knowledge": 0.78,
                "multilingual": 0.72,
                "code": 0.72,
                "math": 0.70,
                "logic": 0.75,
                "agentic_tool_calling": 0.45,
                "daily_work": 0.80,
                "structured_output": 0.78,
                "critique": 0.76,
                "long_context": 0.68,
            },
            input_cost_per_million=0.036,
            output_cost_per_million=0.18,
            p50_latency_ms=1800,
            api_key_env="AXIO_NVIDIA_API_KEYS",
            base_url_env="AXIO_NVIDIA_BASE_URL",
            source="seed_prior",
        ),
        _profile(
            provider="nvidia",
            model="openai/gpt-oss-20b",
            api_format="chat",
            capabilities={
                "science_knowledge": 0.60,
                "multilingual": 0.64,
                "code": 0.62,
                "math": 0.58,
                "logic": 0.61,
                "daily_work": 0.72,
                "structured_output": 0.72,
                "critique": 0.58,
                "long_context": 0.48,
            },
            input_cost_per_million=0.02,
            output_cost_per_million=0.08,
            p50_latency_ms=900,
            api_key_env="AXIO_NVIDIA_API_KEYS",
            base_url_env="AXIO_NVIDIA_BASE_URL",
            source="seed_prior",
        ),
        _profile(
            provider="nvidia",
            model="stepfun-ai/step-3.7-flash",
            api_format="chat",
            capabilities={
                "science_knowledge": 0.62,
                "multilingual": 0.82,
                "code": 0.52,
                "math": 0.55,
                "logic": 0.58,
                "daily_work": 0.82,
                "structured_output": 0.76,
                "critique": 0.55,
                "long_context": 0.55,
            },
            input_cost_per_million=0.20,
            output_cost_per_million=1.15,
            p50_latency_ms=700,
            api_key_env="AXIO_NVIDIA_API_KEYS",
            base_url_env="AXIO_NVIDIA_BASE_URL",
            source="seed_prior",
        ),
        _profile(
            provider="nvidia",
            model="stepfun-ai/step-3.5-flash",
            api_format="chat",
            capabilities={
                "science_knowledge": 0.52,
                "multilingual": 0.74,
                "code": 0.45,
                "math": 0.46,
                "logic": 0.50,
                "daily_work": 0.76,
                "structured_output": 0.70,
                "critique": 0.45,
                "long_context": 0.42,
            },
            input_cost_per_million=0.10,
            output_cost_per_million=0.30,
            p50_latency_ms=550,
            api_key_env="AXIO_NVIDIA_API_KEYS",
            base_url_env="AXIO_NVIDIA_BASE_URL",
            source="seed_prior",
        ),
        _profile(
            provider="cpa-plus",
            model=os.getenv("AXIO_CPA_PLUS_MODEL", "gpt-5.4-mini"),
            api_format="responses",
            capabilities={
                "science_knowledge": 0.86,
                "multilingual": 0.80,
                "code": 0.80,
                "math": 0.82,
                "logic": 0.84,
                "agentic_tool_calling": 0.62,
                "daily_work": 0.88,
                "structured_output": 0.86,
                "critique": 0.84,
                "long_context": 0.82,
            },
            p50_latency_ms=2500,
            api_key_env="AXIO_CPA_PLUS_API_KEY",
            base_url_env="AXIO_CPA_PLUS_BASE_URL",
            source="seed_prior",
        ),
        _profile(
            provider="aisz",
            model=os.getenv("AXIO_AISZ_MODEL", "gpt-5.4-mini"),
            api_format="responses",
            capabilities={
                "science_knowledge": 0.84,
                "multilingual": 0.80,
                "code": 0.78,
                "math": 0.80,
                "logic": 0.82,
                "agentic_tool_calling": 0.60,
                "daily_work": 0.86,
                "structured_output": 0.84,
                "critique": 0.82,
                "long_context": 0.80,
            },
            p50_latency_ms=2500,
            api_key_env="AXIO_AISZ_API_KEY",
            base_url_env="AXIO_AISZ_BASE_URL",
            source="seed_prior",
        ),
    ]
    return {
        "schema": "axio_fusion_api.registry.v1",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "public_models": ["axio-fast", "axio-terra", "axio-pro"],
        "models": [model.safe_dict() for model in models],
        "secrets_persisted": False,
        "raw_prompt_persisted": False,
    }


def load_registry(
    path: str | Path | None = None,
    *,
    include_disabled: bool = False,
    require_prefusion: bool = False,
) -> list[ModelProfile]:
    """Load the operational registry, optionally exposing disabled profiles.

    Serving callers keep the historical default of receiving only enabled
    profiles. Provider onboarding needs to inspect a disabled candidate before
    explicit activation, so it can opt into the full private registry without
    making that candidate routable. Production serving can set
    ``require_prefusion=True`` to require the complete, hash-bound screening
    handoff rather than accepting a legacy probe registry or seed prior.
    """

    payload = _load_registry_payload(path)
    if require_prefusion:
        if payload.get("generated_from_prefusion_screening") is not True:
            raise ValueError(
                "production serving requires a registry generated by pre-Fusion screening"
            )
        contract = validate_prefusion_registry_handoff(payload, require_ready=True)
        if contract.get("valid") is not True:
            reasons = ", ".join(
                str(item)[:120]
                for item in contract.get("reason_codes", [])
                if str(item)
            )
            raise ValueError(
                "pre-Fusion registry handoff is invalid"
                + (f": {reasons}" if reasons else "")
            )
    rows = payload.get("models") if isinstance(payload.get("models"), list) else []
    profiles = [normalize_profile(row) for row in rows if isinstance(row, Mapping)]
    if not include_disabled:
        profiles = [profile for profile in profiles if profile.enabled]
    # Exclude auxiliary/tool-only models that are not general-purpose LLMs
    profiles = [p for p in profiles if not _is_auxiliary_model(p.model)]
    return _dedupe_profiles(profiles)


def load_image_registry(
    path: str | Path | None = None,
    *,
    include_disabled: bool = False,
) -> list[ModelProfile]:
    """Load a separately promoted image-capability registry.

    Text pre-Fusion registries intentionally do not carry image admission
    state. An image registry is therefore opt-in and must prove that the
    image probe binding is ready before any profile can reach ``ImageRouter``.
    Mixed text/image files are rejected instead of silently filtered.
    """

    selected = str(
        path or os.getenv("AXIO_FUSION_IMAGE_REGISTRY_PATH", "")
    ).strip()
    if not selected:
        return []
    payload = _load_registry_payload(selected)
    if payload.get("image_capability_registry_ready") is not True:
        raise ValueError("image registry is not promoted")
    binding = payload.get("image_probe_binding")
    if not isinstance(binding, Mapping) or str(binding.get("status") or "") != "ready":
        raise ValueError("image registry probe binding is not ready")
    rows = payload.get("models") if isinstance(payload.get("models"), list) else []
    profiles = [normalize_profile(row) for row in rows if isinstance(row, Mapping)]
    if not profiles:
        raise ValueError("image registry contains no profiles")
    if any(profile.text_model_eligible for profile in profiles):
        raise ValueError("image registry contains text profiles")
    if not include_disabled:
        profiles = [profile for profile in profiles if profile.enabled]
    if not profiles:
        raise ValueError("image registry contains no enabled profiles")
    if not any(
        profile.image_generation_eligible or profile.image_editing_eligible
        for profile in profiles
    ):
        raise ValueError("image registry contains no verified image operations")
    return _dedupe_profiles(profiles)


def registry_report(profiles: Sequence[ModelProfile]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.registry_report.v1",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "model_count": len(profiles),
        "provider_count": len({profile.provider for profile in profiles}),
        "models": [_private_profile_dict(profile) for profile in profiles],
        "readiness": registry_readiness(profiles),
        "secrets_persisted": False,
        "raw_prompt_persisted": False,
    }


def _private_profile_dict(profile: ModelProfile) -> dict[str, Any]:
    """Serialize a serving profile while retaining private identity binding.

    Safe artifacts intentionally omit raw canonical identities. The private
    registry already contains the provider/model aliases required for serving,
    so retaining the canonical value here lets later calibration preserve
    same-model replica grouping without weakening the safe-artifact boundary.
    """
    row = profile.safe_dict()
    if profile.canonical_model_id:
        row["canonical_model_id"] = profile.canonical_model_id
    return row


def build_provider_portfolio_audit(
    profiles: Sequence[ModelProfile],
    *,
    min_provider_baselines: int = 3,
    min_provider_count: int = 2,
    min_api_format_count: int = 2,
) -> dict[str, Any]:
    clean_profiles = [profile for profile in profiles if profile.enabled]
    census = _registry_census(clean_profiles, redact_provider_identifiers=True)
    ranked = _rank_portfolio_profiles(clean_profiles)
    category_rows = [
        _portfolio_category_row(category, axes, clean_profiles)
        for category, axes in FUSION_PORTFOLIO_CATEGORY_AXES.items()
    ]
    role_rows = _portfolio_role_rows(clean_profiles)
    independent_verification_capacity = _portfolio_independent_verification_capacity(
        clean_profiles,
        min_provider_count=min_provider_count,
    )
    baseline_candidates = [
        row
        for row in ranked
        if float(row.get("portfolio_score") or 0.0) >= FUSION_PORTFOLIO_STRONG_MODEL_THRESHOLD
    ]
    if len(baseline_candidates) < int(min_provider_baselines):
        baseline_candidates = ranked[: int(min_provider_baselines)]
    live_baseline_count = sum(1 for row in baseline_candidates[: int(min_provider_baselines)] if row.get("live_probe_evidence") is True)
    blockers = _portfolio_blockers(
        clean_profiles=clean_profiles,
        census=census,
        baseline_candidates=baseline_candidates,
        role_rows=role_rows,
        independent_verification_capacity=independent_verification_capacity,
        min_provider_baselines=min_provider_baselines,
    )
    warnings = _portfolio_warnings(
        clean_profiles=clean_profiles,
        census=census,
        category_rows=category_rows,
        independent_verification_capacity=independent_verification_capacity,
        min_provider_count=min_provider_count,
        min_api_format_count=min_api_format_count,
    )
    ready_for_serving = not blockers
    ready_for_diverse_fusion = ready_for_serving and not warnings
    ready_for_final_claim_registry_profile = (
        ready_for_serving
        and bool(independent_verification_capacity.get("final_claim_independent_verification_ready"))
        and live_baseline_count >= int(min_provider_baselines)
    )
    status = (
        "ready_for_final_claim_profile"
        if ready_for_final_claim_registry_profile and ready_for_diverse_fusion
        else "ready_for_serving_with_warnings"
        if ready_for_serving
        else "blocked"
    )
    return {
        "schema": "axio_fusion_api.provider_portfolio_audit.v1",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "provider_input_model": "configuration_driven_arbitrary_providers",
        "status": status,
        "ready_for_serving": ready_for_serving,
        "ready_for_diverse_fusion": ready_for_diverse_fusion,
        "ready_for_final_claim_registry_profile": ready_for_final_claim_registry_profile,
        "requires_live_probe_for_final_claims": True,
        "requirements": {
            "min_provider_baselines": int(min_provider_baselines),
            "min_provider_count_for_diverse_fusion": int(min_provider_count),
            "min_api_format_count_for_diverse_fusion": int(min_api_format_count),
            "role_threshold": FUSION_PORTFOLIO_ROLE_THRESHOLD,
            "category_threshold": FUSION_PORTFOLIO_CATEGORY_THRESHOLD,
            "strong_model_threshold": FUSION_PORTFOLIO_STRONG_MODEL_THRESHOLD,
            "supported_provider_input_api_formats": list(FUSION_PROVIDER_INPUT_API_FORMATS),
        },
        "inventory_summary": {
            "model_count": len(clean_profiles),
            "provider_hash_count": census["provider_count"],
            "api_format_counts": census["api_format_counts"],
            "provider_format_hash_counts": census["provider_format_counts"],
            "pricing_known_count": census["pricing_known_count"],
            "context_known_count": census["context_known_count"],
            "live_probe_evidence_model_count": sum(1 for profile in clean_profiles if _profile_has_live_evidence(profile)),
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
        },
        "provider_baseline_profile": {
            "candidate_count": len(baseline_candidates),
            "required_candidate_count": int(min_provider_baselines),
            "selected_candidate_count": min(len(baseline_candidates), int(min_provider_baselines)),
            "selected_live_probe_evidence_count": live_baseline_count,
            "selected_tiers": [
                {
                    "tier": tier,
                    **_portfolio_baseline_tier_receipt(row),
                }
                for tier, row in zip(
                    ("strongest_provider", "second_strongest_provider", "third_strongest_provider"),
                    baseline_candidates[: int(min_provider_baselines)],
                )
            ],
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
        },
        "category_coverage": category_rows,
        "role_coverage": role_rows,
        "independent_verification_capacity": independent_verification_capacity,
        "api_format_coverage": _portfolio_api_format_coverage(census, min_api_format_count=min_api_format_count),
        "blockers": blockers,
        "warnings": warnings,
        "recommendations": _portfolio_recommendations(
            blockers,
            warnings,
            category_rows,
            role_rows,
            independent_verification_capacity=independent_verification_capacity,
        ),
        "no_cheat_contract": {
            "does_not_replace_live_probe": True,
            "does_not_replace_21_suite_benchmark": True,
            "does_not_rank_final_claims_from_priors": True,
            "final_claims_require_api_request_benchmark_runs": True,
            "raw_prompts_persisted": False,
            "raw_labels_persisted": False,
            "raw_provider_outputs_persisted": False,
        },
        "anti_leakage_contract": {
            "provider_names_hashed": True,
            "provider_model_ids_hashed": True,
            "profile_ids_hashed": True,
            "raw_provider_urls_persisted": False,
            "api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def build_registry_from_probe_artifacts(
    *,
    probe_paths: Sequence[str | Path],
    include_unavailable: bool = False,
    min_available_models: int = 1,
    redact_provider_identifiers: bool = False,
) -> dict[str, Any]:
    payloads = _load_json_files(probe_paths)
    probe_rows = _probe_rows_from_payloads(payloads)
    profiles = []
    status_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    for row in probe_rows:
        status = str(row.get("status") or "unknown")
        if status == "available" and row_latency_eligibility(row).get("eligible") is False:
            status = "latency_ineligible"
        status_counts[status] = status_counts.get(status, 0) + 1
        mode = str(row.get("probe_mode") or row.get("mode") or "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        if status != "available" and not include_unavailable:
            continue
        profile = _profile_from_probe_row(row, status=status)
        profiles.append(profile)
    profiles = _dedupe_profiles(profiles)
    available_count = sum(
        1
        for row in probe_rows
        if str(row.get("status") or "") == "available"
        and row_latency_eligibility(row).get("eligible") is not False
    )
    live_available_count = sum(
        1
        for row in probe_rows
        if (
            str(row.get("status") or "") == "available"
            and row_latency_eligibility(row).get("eligible") is not False
            and _row_has_live_probe_evidence(row)
        )
    )
    blockers = []
    if available_count < int(min_available_models):
        blockers.append("insufficient_available_probe_models")
    if live_available_count < int(min_available_models):
        blockers.append("insufficient_live_available_probe_models")
    if not profiles:
        blockers.append("empty_generated_registry")
    readiness = _generated_registry_readiness(
        profiles,
        blockers=blockers,
        min_available_models=min_available_models,
        available_count=available_count,
        live_available_count=live_available_count,
        mode_counts=mode_counts,
    )
    census = _registry_census(profiles)
    if redact_provider_identifiers:
        return _redacted_registry_evidence_from_profiles(
            profiles=profiles,
            probe_paths=probe_paths,
            payload_count=len(payloads),
            probe_row_count=len(probe_rows),
            status_counts=status_counts,
            mode_counts=mode_counts,
            include_unavailable=include_unavailable,
            available_count=available_count,
            live_available_count=live_available_count,
            min_available_models=min_available_models,
            blockers=blockers,
        )
    return {
        "schema": "axio_fusion_api.registry.v1",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "generated_from_probe": True,
        "public_models": ["axio-fast", "axio-terra", "axio-pro"],
        "source_artifacts": {
            "probe_file_count": len(probe_paths),
            "probe_file_path_hashes": [sha256_text(str(path)) for path in probe_paths],
            "probe_payload_count": len(payloads),
            "probe_row_count": len(probe_rows),
            "status_counts": dict(sorted(status_counts.items())),
            "mode_counts": dict(sorted(mode_counts.items())),
            "api_format_counts": census["api_format_counts"],
            "provider_format_counts": census["provider_format_counts"],
            "include_unavailable": bool(include_unavailable),
            "raw_probe_paths_persisted": False,
            "raw_provider_outputs_persisted": False,
        },
        "model_count": len(profiles),
        "provider_count": len({profile.provider for profile in profiles}),
        "available_model_count": available_count,
        "live_available_model_count": live_available_count,
        "readiness": readiness,
        "models": [_private_profile_dict(profile) for profile in profiles],
        "generation_contract": {
            "input_must_be_prompt_free_probe_artifacts": True,
            "only_available_models_included_by_default": True,
            "provider_config_priors_inherited": True,
            "model_name_capability_priors_applied": True,
            "live_latency_receipts_preferred_over_static_latency_priors": True,
            "live_probe_evidence_required_for_final_claims": True,
            "api_keys_persisted": False,
            "base_urls_persisted": False,
            "raw_provider_outputs_persisted": False,
            "raw_provider_error_details_persisted": False,
        },
        "secrets_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_output_persisted": False,
    }


def build_probe_bound_registry(
    *,
    registry_path: str | Path,
    probe_paths: Sequence[str | Path],
    min_available_models: int = 3,
) -> dict[str, Any]:
    """Bind an operational registry to the exact live probe artifact set.

    A pre-Fusion registry contains richer role, canonical-identity, and
    routing metadata than the generic registry generated directly from probe
    rows.  This function preserves that operational projection while attaching
    the probe source counts and path hashes required by final-claim evidence.
    The binding is only ready when the two registries contain the exact same
    physical profile set and the probe-generated registry is live-ready.

    The returned object is still a private registry because its ``models``
    rows retain provider/model aliases needed by the runtime.  Safe evidence
    must be produced separately with ``provider-probe-evidence-audit``.
    """

    selected_registry_path = Path(registry_path)
    blockers: list[str] = []
    try:
        registry_payload = json.loads(
            selected_registry_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        registry_payload = {}
        blockers.append("probe_bound_registry_input_unreadable")
    if not isinstance(registry_payload, Mapping):
        registry_payload = {}
        blockers.append("probe_bound_registry_input_must_be_object")

    minimum = max(1, int(min_available_models))
    probe_registry = build_registry_from_probe_artifacts(
        probe_paths=probe_paths,
        min_available_models=minimum,
    )
    probe_readiness = (
        probe_registry.get("readiness")
        if isinstance(probe_registry.get("readiness"), Mapping)
        else {}
    )
    source_models = registry_payload.get("models")
    source_models = (
        [row for row in source_models if isinstance(row, Mapping)]
        if isinstance(source_models, list)
        else []
    )
    probe_models = probe_registry.get("models")
    probe_models = (
        [row for row in probe_models if isinstance(row, Mapping)]
        if isinstance(probe_models, list)
        else []
    )
    source_profile_hashes = _registry_profile_hash_set(source_models)
    probe_profile_hashes = _registry_profile_hash_set(probe_models)

    if str(registry_payload.get("schema") or "") != "axio_fusion_api.registry.v1":
        blockers.append("probe_bound_registry_schema_invalid")
    if (
        registry_payload.get("generated_from_prefusion_screening") is not True
        and registry_payload.get("generated_from_probe") is not True
    ):
        blockers.append("probe_bound_registry_source_not_screening_or_probe")
    if str(registry_payload.get("binding_status") or "").casefold() != "ready":
        blockers.append("probe_bound_registry_input_not_ready")
    if not source_profile_hashes:
        blockers.append("probe_bound_registry_source_profile_set_empty")
    if not probe_profile_hashes:
        blockers.append("probe_bound_registry_probe_profile_set_empty")
    if source_profile_hashes != probe_profile_hashes:
        blockers.append("probe_bound_registry_profile_set_mismatch")
    if len(source_models) != len(probe_models):
        blockers.append("probe_bound_registry_profile_count_mismatch")
    if probe_readiness.get("live_probe_proven") is not True:
        blockers.append("probe_bound_registry_live_probe_not_proven")
    if probe_readiness.get("final_claim_registry_ready") is not True:
        blockers.append("probe_bound_registry_probe_registry_not_final_claim_ready")
    if int(probe_registry.get("live_available_model_count") or 0) < minimum:
        blockers.append("probe_bound_registry_live_model_count_too_small")
    if not probe_paths:
        blockers.append("probe_bound_registry_probe_file_missing")
    if not isinstance(probe_registry.get("source_artifacts"), Mapping):
        blockers.append("probe_bound_registry_probe_source_summary_missing")

    source_artifacts = dict(probe_registry.get("source_artifacts") or {})
    binding_core = {
        "schema": "axio_fusion_api.registry_probe_binding.v1",
        "status": "ready" if not blockers else "blocked",
        "registry_input_path_sha256": sha256_text(str(selected_registry_path)),
        "probe_file_path_hashes": list(
            source_artifacts.get("probe_file_path_hashes") or []
        ),
        "probe_profile_set_sha256": sha256_text(
            stable_json(sorted(probe_profile_hashes))
        ),
        "registry_profile_set_sha256": sha256_text(
            stable_json(sorted(source_profile_hashes))
        ),
        "profile_set_matches": source_profile_hashes == probe_profile_hashes,
        "probe_model_count": len(probe_models),
        "registry_model_count": len(source_models),
        "min_available_models": minimum,
        "live_probe_proven": probe_readiness.get("live_probe_proven") is True,
        "probe_registry_final_claim_ready": probe_readiness.get(
            "final_claim_registry_ready"
        )
        is True,
        "raw_probe_paths_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    binding = {
        **binding_core,
        "blockers": sorted(set(blockers)),
    }
    binding["binding_digest_sha256"] = sha256_text(stable_json(binding_core))

    if blockers:
        blocked_registry = dict(registry_payload)
        blocked_readiness = dict(
            registry_payload.get("readiness")
            if isinstance(registry_payload.get("readiness"), Mapping)
            else {}
        )
        blocked_readiness.update(
            {
                "ready": False,
                "status": "blocked",
                "blockers": sorted(
                    set(
                        [
                            *[
                                str(item)
                                for item in blocked_readiness.get("blockers", [])
                                if str(item)
                            ],
                            *blockers,
                        ]
                    )
                ),
                "generated_from_probe": False,
                "live_probe_proven": False,
                "final_claim_registry_ready": False,
            }
        )
        blocked_registry["binding_status"] = "blocked"
        blocked_registry["readiness"] = blocked_readiness
        blocked_registry["probe_evidence_binding"] = binding
        blocked_registry["generated_from_probe"] = False
        blocked_registry["raw_provider_outputs_persisted"] = False
        blocked_registry["secrets_persisted"] = False
        return blocked_registry

    bound_registry = dict(registry_payload)
    bound_registry["generated_from_probe"] = True
    bound_registry["source_artifacts"] = source_artifacts
    bound_registry["probe_evidence_binding"] = binding
    bound_registry["generation_contract"] = {
        **dict(registry_payload.get("generation_contract") or {}),
        "probe_evidence_binding_required": True,
        "probe_artifacts_are_prompt_free": True,
        "probe_profile_set_must_match_operational_registry": True,
        "live_probe_evidence_required": True,
        "raw_probe_paths_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    bound_readiness = dict(
        registry_payload.get("readiness")
        if isinstance(registry_payload.get("readiness"), Mapping)
        else {}
    )
    bound_readiness.update(
        {
            "generated_from_probe": True,
            "live_probe_proven": True,
            "final_claim_registry_ready": True,
            "probe_profile_set_sha256": sha256_text(
                stable_json(sorted(probe_profile_hashes))
            ),
            "min_available_models": minimum,
            "raw_prompt_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        }
    )
    bound_registry["readiness"] = bound_readiness
    bound_registry["raw_provider_outputs_persisted"] = False
    bound_registry["secrets_persisted"] = False
    return bound_registry


def _registry_profile_hash_set(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    hashes: set[str] = set()
    for row in rows:
        profile_id = str(row.get("profile_id") or "").strip()
        if not profile_id:
            provider = str(row.get("provider") or "").strip()
            model = str(row.get("model") or "").strip()
            profile_id = f"{provider}/{model}" if provider or model else ""
        if profile_id:
            hashes.add(sha256_text(profile_id).lower())
    return hashes


def _profile_from_probe_row(row: Mapping[str, Any], *, status: str) -> ModelProfile:
    model_id = str(row.get("model") or row.get("id") or "").strip()
    profile_row: dict[str, Any] = {
        "provider": row.get("provider"),
        "model": model_id,
        "api_format": row.get("api_format"),
        "capabilities": row.get("capabilities") if isinstance(row.get("capabilities"), Mapping) else {},
        "input_cost_per_million": row.get("input_cost_per_million"),
        "output_cost_per_million": row.get("output_cost_per_million"),
        "p50_latency_ms": row.get("p50_latency_ms")
        if row.get("p50_latency_ms") is not None
        else row.get("latency_ms"),
        "p95_latency_ms": row.get("p95_latency_ms")
        if row.get("p95_latency_ms") is not None
        else row.get("latency_ms"),
        "context_tokens": row.get("context_tokens"),
        "recent_success_rate": row.get("stability_success_rate")
        if row.get("stability_success_rate") is not None
        else (1.0 if status == "available" else 0.0),
        "availability": row.get("stability_success_rate")
        if row.get("stability_success_rate") is not None
        else (1.0 if status == "available" else 0.0),
        "observed_success_count": row.get("stability_success_count")
        if row.get("stability_success_count") is not None
        else (1 if status == "available" else 0),
        "observed_failure_count": row.get("stability_failure_count")
        if row.get("stability_failure_count") is not None
        else (0 if status == "available" else 1),
        "supports_tools": row.get("supports_tools", False),
        "supports_vision": row.get("supports_vision", False),
        "vision_probe_status": row.get("vision_probe_status", "not_run"),
        "vision_capability_source": row.get("vision_capability_source", ""),
        "model_kind": row.get("model_kind", row.get("modelKind", "text")),
        "image_capabilities": (
            dict(row.get("image_capabilities"))
            if isinstance(row.get("image_capabilities"), Mapping)
            else {}
        ),
        "image_probe_status": row.get("image_probe_status", "not_run"),
        "reasoning_transport": (
            dict(row.get("reasoning_transport"))
            if isinstance(row.get("reasoning_transport"), Mapping)
            else {}
        ),
        "screening_reasoning_capability": (
            dict(row.get("screening_reasoning_capability"))
            if isinstance(row.get("screening_reasoning_capability"), Mapping)
            else {}
        ),
        "traffic_control": (
            dict(row.get("traffic_control"))
            if isinstance(row.get("traffic_control"), Mapping)
            else (
                dict(row.get("trafficControl"))
                if isinstance(row.get("trafficControl"), Mapping)
                else {}
            )
        ),
        "privacy_tags": row.get("privacy_tags", ["external_provider"]),
        "base_url_env": row.get("base_url_env"),
        "api_key_env": row.get("api_key_env"),
        "auth_scheme": row.get("auth_scheme"),
        "max_output_tokens_parameter": row.get(
            "max_output_tokens_parameter",
            row.get("maxOutputTokensParameter", "max_tokens"),
        ),
        "models_endpoint": row.get("models_endpoint") or row.get("modelsEndpoint") or row.get("model_list_endpoint"),
        "discover_models": row.get("discover_models", row.get("discoverModels", True)),
        "canonical_model_id": row.get("canonical_model_id")
        or row.get("canonicalModelId")
        or row.get("canonical_model")
        or row.get("canonicalModel")
        or model_id,
        "screening_prior_rank": row.get("screening_prior_rank"),
        "screening_prior_confidence": row.get("screening_prior_confidence"),
        "screening_allowed_roles": row.get("screening_allowed_roles", ()),
        "screening_disallowed_roles": row.get("screening_disallowed_roles", ()),
        "enabled": status == "available",
        "health": "available" if status == "available" else "unavailable",
        "source": "live_probe" if status == "available" else "probe_unavailable",
    }
    return normalize_profile(profile_row)


def _generated_registry_readiness(
    profiles: Sequence[ModelProfile],
    *,
    blockers: Sequence[str],
    min_available_models: int,
    available_count: int,
    live_available_count: int,
    mode_counts: Mapping[str, int],
) -> dict[str, Any]:
    base = registry_readiness(profiles)
    merged_blockers = _dedupe_strings([*base["blockers"], *blockers])
    ready = not merged_blockers
    status = "ready" if ready and not base["warnings"] else ("blocked" if merged_blockers else "usable_with_warnings")
    return {
        **base,
        "ready": ready,
        "status": status,
        "blockers": merged_blockers,
        "available_model_count": int(available_count),
        "live_available_model_count": int(live_available_count),
        "min_available_models": int(min_available_models),
        "probe_mode_counts": dict(sorted(mode_counts.items())),
        "live_probe_proven": int(live_available_count) >= int(min_available_models),
        "final_claim_registry_ready": ready and int(live_available_count) >= int(min_available_models),
        "generated_from_probe": True,
        "provider_config_priors_inherited": True,
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _registry_census(
    profiles: Sequence[ModelProfile],
    *,
    redact_provider_identifiers: bool = False,
) -> dict[str, Any]:
    api_format_counts: dict[str, int] = {}
    provider_format_counts: dict[str, int] = {}
    for profile in profiles:
        api_format = str(profile.api_format or "unknown")
        api_format_counts[api_format] = api_format_counts.get(api_format, 0) + 1
        provider_key = sha256_text(profile.provider) if redact_provider_identifiers else profile.provider
        provider_format_key = f"{provider_key}::{api_format}"
        provider_format_counts[provider_format_key] = provider_format_counts.get(provider_format_key, 0) + 1
    return {
        "model_count": len(profiles),
        "provider_count": len({profile.provider for profile in profiles}),
        "api_format_counts": dict(sorted(api_format_counts.items())),
        "provider_format_counts": dict(sorted(provider_format_counts.items())),
        "judge_candidate_count": sum(1 for profile in profiles if profile.capability("critique") >= 0.65),
        "structured_candidate_count": sum(1 for profile in profiles if profile.capability("structured_output") >= 0.65),
        "fast_candidate_count": sum(1 for profile in profiles if _is_fast_candidate(profile)),
        "tool_candidate_count": sum(
            1
            for profile in profiles
            if profile.tool_calling_eligible
        ),
        "pricing_known_count": sum(
            1
            for profile in profiles
            if profile.input_cost_per_million is not None and profile.output_cost_per_million is not None
        ),
        "context_known_count": sum(1 for profile in profiles if profile.context_tokens is not None),
    }


def _rank_portfolio_profiles(profiles: Sequence[ModelProfile]) -> list[dict[str, Any]]:
    rows = [_portfolio_model_receipt(profile) for profile in profiles]
    rows.sort(
        key=lambda row: (
            float(row.get("portfolio_score") or 0.0),
            float(row.get("mean_capability_score") or 0.0),
            -float(row.get("p50_latency_ms") or 1_000_000.0),
            str(row.get("profile_id_sha256") or ""),
        ),
        reverse=True,
    )
    return rows


def _portfolio_model_receipt(profile: ModelProfile) -> dict[str, Any]:
    capability_axes = [
        "science_knowledge",
        "multilingual",
        "code",
        "math",
        "logic",
        "agentic_tool_calling",
        "daily_work",
        "structured_output",
        "critique",
        "long_context",
    ]
    mean_capability = sum(profile.capability(axis) for axis in capability_axes) / len(capability_axes)
    role_strength = (
        profile.capability("structured_output") * 0.30
        + profile.capability("critique") * 0.30
        + profile.capability("agentic_tool_calling") * 0.15
        + profile.capability("long_context") * 0.15
        + (0.10 if profile.tool_calling_eligible else 0.0)
    )
    latency_score = _portfolio_latency_score(profile)
    reliability = _portfolio_reliability_score(profile)
    portfolio_score = mean_capability * 0.58 + role_strength * 0.20 + latency_score * 0.10 + reliability * 0.12
    return {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "provider_sha256": sha256_text(profile.provider),
        "model_sha256": sha256_text(profile.model),
        "api_format": profile.api_format,
        "portfolio_score": round(max(0.0, min(1.0, portfolio_score)), 6),
        "mean_capability_score": round(mean_capability, 6),
        "role_strength_score": round(max(0.0, min(1.0, role_strength)), 6),
        "latency_score": round(latency_score, 6),
        "reliability_score": round(reliability, 6),
        "p50_latency_ms": profile.p50_latency_ms,
        "p95_latency_ms": profile.p95_latency_ms,
        "context_tokens": profile.context_tokens,
        "pricing_known": profile.input_cost_per_million is not None and profile.output_cost_per_million is not None,
        "supports_tools": profile.supports_tools,
        "tool_capability": profile.tool_capability,
        "tool_capability_source": profile.tool_capability_source,
        "tool_probe_status": profile.tool_probe_status,
        "tool_calling_eligible": profile.tool_calling_eligible,
        "supports_vision": profile.supports_vision,
        "vision_input_eligible": profile.vision_input_eligible,
        "vision_probe_status": profile.vision_probe_status,
        "vision_capability_source": profile.vision_capability_source,
        "live_probe_evidence": _profile_has_live_evidence(profile),
        "capability_summary": {
            axis: round(profile.capability(axis), 4)
            for axis in capability_axes
        },
        "raw_provider_name_persisted": False,
        "raw_provider_model_id_persisted": False,
        "raw_profile_id_persisted": False,
    }


def _portfolio_baseline_tier_receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "profile_id_sha256": str(row.get("profile_id_sha256") or ""),
        "provider_sha256": str(row.get("provider_sha256") or ""),
        "model_sha256": str(row.get("model_sha256") or ""),
        "api_format": str(row.get("api_format") or ""),
        "portfolio_score": _optional_float(row.get("portfolio_score")),
        "mean_capability_score": _optional_float(row.get("mean_capability_score")),
        "role_strength_score": _optional_float(row.get("role_strength_score")),
        "p50_latency_ms": _optional_int(row.get("p50_latency_ms")),
        "p95_latency_ms": _optional_int(row.get("p95_latency_ms")),
        "pricing_known": row.get("pricing_known") is True,
        "live_probe_evidence": row.get("live_probe_evidence") is True,
        "raw_provider_name_persisted": False,
        "raw_provider_model_id_persisted": False,
    }


def _portfolio_category_row(
    category: str,
    axes: Sequence[str],
    profiles: Sequence[ModelProfile],
) -> dict[str, Any]:
    scored = []
    for profile in profiles:
        score = _portfolio_category_score(profile, axes, category=category)
        scored.append((profile, score))
    scored.sort(key=lambda item: (item[1], sha256_text(item[0].profile_id)), reverse=True)
    ready_candidates = [(profile, score) for profile, score in scored if score >= FUSION_PORTFOLIO_CATEGORY_THRESHOLD]
    best_score = scored[0][1] if scored else 0.0
    return {
        "category": category,
        "mapped_capability_axes": list(axes),
        "candidate_count": len(scored),
        "ready_candidate_count": len(ready_candidates),
        "best_category_score": round(best_score, 6),
        "category_ready": len(ready_candidates) >= 1,
        "top_candidate_hashes": [
            {
                "profile_id_sha256": sha256_text(profile.profile_id),
                "provider_sha256": sha256_text(profile.provider),
                "api_format": profile.api_format,
                "category_score": round(score, 6),
            }
            for profile, score in scored[:3]
        ],
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
    }


def _portfolio_category_score(profile: ModelProfile, axes: Sequence[str], *, category: str) -> float:
    if not axes:
        return 0.0
    score = sum(profile.capability(axis) for axis in axes) / len(axes)
    if category == "agentic_tool_calling" and profile.tool_calling_eligible:
        score = max(score, min(1.0, profile.capability("agentic_tool_calling") * 0.70 + 0.30))
    return max(0.0, min(1.0, score))


def _portfolio_role_rows(profiles: Sequence[ModelProfile]) -> list[dict[str, Any]]:
    role_specs = {
        "primary_solver": ("science_knowledge", "code", "math", "logic", "daily_work"),
        "judge": ("critique", "structured_output", "logic"),
        "synthesizer": ("structured_output", "critique", "long_context"),
        "critic": ("critique", "logic", "science_knowledge"),
        "tool_worker": ("agentic_tool_calling", "structured_output"),
        "fast_path": ("daily_work", "structured_output"),
    }
    rows = []
    for role, axes in role_specs.items():
        scored = []
        for profile in profiles:
            score = sum(profile.capability(axis) for axis in axes) / len(axes)
            if role == "tool_worker" and profile.tool_calling_eligible:
                score = max(score, min(1.0, profile.capability("agentic_tool_calling") * 0.70 + 0.30))
            if role == "fast_path" and _is_fast_candidate(profile):
                score = max(score, 0.70)
            scored.append((profile, max(0.0, min(1.0, score))))
        scored.sort(key=lambda item: (item[1], sha256_text(item[0].profile_id)), reverse=True)
        ready = [(profile, score) for profile, score in scored if score >= FUSION_PORTFOLIO_ROLE_THRESHOLD]
        rows.append(
            {
                "role": role,
                "mapped_capability_axes": list(axes),
                "ready_candidate_count": len(ready),
                "best_role_score": round(scored[0][1], 6) if scored else 0.0,
                "role_ready": len(ready) >= 1,
                "top_candidate_hashes": [
                    {
                        "profile_id_sha256": sha256_text(profile.profile_id),
                        "provider_sha256": sha256_text(profile.provider),
                        "api_format": profile.api_format,
                        "role_score": round(score, 6),
                    }
                    for profile, score in scored[:3]
                ],
                "raw_provider_names_persisted": False,
                "raw_provider_model_ids_persisted": False,
            }
        )
    return rows


def _portfolio_independent_verification_capacity(
    profiles: Sequence[ModelProfile],
    *,
    min_provider_count: int,
) -> dict[str, Any]:
    scored = [
        (profile, _portfolio_answer_claim_verifier_score(profile))
        for profile in profiles
    ]
    scored.sort(key=lambda item: (item[1], sha256_text(item[0].profile_id)), reverse=True)
    ready = [
        (profile, score)
        for profile, score in scored
        if score >= FUSION_PORTFOLIO_ROLE_THRESHOLD
    ]
    provider_hashes = sorted({sha256_text(profile.provider) for profile, _ in ready})
    api_formats = sorted({profile.api_format for profile, _ in ready if profile.api_format})
    live_ready_count = sum(1 for profile, _ in ready if _profile_has_live_evidence(profile))
    pricing_known_count = sum(
        1
        for profile, _ in ready
        if profile.input_cost_per_million is not None and profile.output_cost_per_million is not None
    )
    context_known_count = sum(1 for profile, _ in ready if profile.context_tokens is not None)
    required_provider_count = max(1, int(min_provider_count)) if len(profiles) > 1 else 1
    cross_provider_ready = len(provider_hashes) >= required_provider_count if len(profiles) > 1 else bool(ready)
    new_profile_ready = len(ready) >= 2 if len(profiles) > 1 else bool(ready)
    ready_for_serving = bool(ready)
    final_claim_ready = (
        ready_for_serving
        and cross_provider_ready
        and new_profile_ready
        and live_ready_count >= min(len(ready), 2)
    )
    reason_codes: list[str] = []
    if not ready:
        reason_codes.append("missing_independent_answer_claim_verifier")
    if ready_for_serving and not new_profile_ready:
        reason_codes.append("answer_claim_verifier_new_profile_capacity_below_target")
    if ready_for_serving and not cross_provider_ready:
        reason_codes.append("answer_claim_verifier_cross_provider_capacity_below_target")
    if ready_for_serving and live_ready_count < min(len(ready), 2):
        reason_codes.append("answer_claim_verifier_live_probe_evidence_below_final_claim_target")
    if ready_for_serving and pricing_known_count < len(ready):
        reason_codes.append("answer_claim_verifier_pricing_metadata_incomplete")
    if ready_for_serving and context_known_count < len(ready):
        reason_codes.append("answer_claim_verifier_context_metadata_incomplete")
    return {
        "schema": "axio_fusion_api.independent_verification_capacity.v1",
        "purpose": "preflight_for_same_source_answer_claim_consensus_repair",
        "verifier_threshold": FUSION_PORTFOLIO_ROLE_THRESHOLD,
        "candidate_count": len(scored),
        "ready_verifier_count": len(ready),
        "ready_provider_hash_count": len(provider_hashes),
        "ready_api_format_count": len(api_formats),
        "required_provider_count_for_cross_provider_verification": required_provider_count,
        "new_profile_verifier_ready": new_profile_ready,
        "cross_provider_verifier_ready": cross_provider_ready,
        "serving_independent_verification_ready": ready_for_serving,
        "final_claim_independent_verification_ready": final_claim_ready,
        "live_probe_evidence_ready_verifier_count": live_ready_count,
        "pricing_known_ready_verifier_count": pricing_known_count,
        "context_known_ready_verifier_count": context_known_count,
        "reason_codes": _dedupe_strings(reason_codes),
        "top_verifier_hashes": [
            {
                "profile_id_sha256": sha256_text(profile.profile_id),
                "provider_sha256": sha256_text(profile.provider),
                "model_sha256": sha256_text(profile.model),
                "api_format": profile.api_format,
                "verifier_score": round(score, 6),
                "critique_score": round(profile.capability("critique"), 4),
                "structured_output_score": round(profile.capability("structured_output"), 4),
                "logic_score": round(profile.capability("logic"), 4),
                "long_context_score": round(profile.capability("long_context"), 4),
                "live_probe_evidence": _profile_has_live_evidence(profile),
                "pricing_known": profile.input_cost_per_million is not None and profile.output_cost_per_million is not None,
                "context_tokens_known": profile.context_tokens is not None,
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_provider_model_id_persisted": False,
            }
            for profile, score in scored[:6]
        ],
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_profile_ids_persisted": False,
        "secrets_persisted": False,
    }


def _portfolio_answer_claim_verifier_score(profile: ModelProfile) -> float:
    evidence_axis = max(profile.capability("science_knowledge"), profile.capability("daily_work"))
    return max(
        0.0,
        min(
            1.0,
            profile.capability("critique") * 0.34
            + profile.capability("structured_output") * 0.26
            + profile.capability("logic") * 0.18
            + profile.capability("long_context") * 0.12
            + evidence_axis * 0.06
            + _portfolio_reliability_score(profile) * 0.04,
        ),
    )


def _portfolio_api_format_coverage(
    census: Mapping[str, Any],
    *,
    min_api_format_count: int,
) -> dict[str, Any]:
    counts = dict(census.get("api_format_counts") or {})
    present = sorted(api_format for api_format in FUSION_PROVIDER_INPUT_API_FORMATS if int(counts.get(api_format, 0) or 0) > 0)
    missing = sorted(api_format for api_format in FUSION_PROVIDER_INPUT_API_FORMATS if api_format not in present)
    return {
        "supported_input_api_formats": list(FUSION_PROVIDER_INPUT_API_FORMATS),
        "present_api_formats": present,
        "missing_api_formats": missing,
        "api_format_count": len(present),
        "required_api_format_count_for_diverse_fusion": int(min_api_format_count),
        "api_format_diversity_ready": len(present) >= int(min_api_format_count),
        "api_format_counts": counts,
    }


def _portfolio_blockers(
    *,
    clean_profiles: Sequence[ModelProfile],
    census: Mapping[str, Any],
    baseline_candidates: Sequence[Mapping[str, Any]],
    role_rows: Sequence[Mapping[str, Any]],
    independent_verification_capacity: Mapping[str, Any],
    min_provider_baselines: int,
) -> list[str]:
    blockers = []
    if not clean_profiles:
        blockers.append("empty_model_inventory")
    if len(baseline_candidates) < int(min_provider_baselines):
        blockers.append("fewer_than_three_provider_baseline_candidates")
    if int(census.get("judge_candidate_count") or 0) < 1:
        blockers.append("missing_judge_candidate")
    if int(census.get("structured_candidate_count") or 0) < 1:
        blockers.append("missing_structured_output_candidate")
    if int(census.get("fast_candidate_count") or 0) < 1:
        blockers.append("missing_fast_candidate")
    if any(row.get("role") in {"primary_solver", "judge", "synthesizer"} and row.get("role_ready") is not True for row in role_rows):
        blockers.append("required_fusion_role_coverage_incomplete")
    if independent_verification_capacity.get("serving_independent_verification_ready") is not True:
        blockers.append("missing_independent_answer_claim_verifier")
    return _dedupe_strings(blockers)


def _portfolio_warnings(
    *,
    clean_profiles: Sequence[ModelProfile],
    census: Mapping[str, Any],
    category_rows: Sequence[Mapping[str, Any]],
    independent_verification_capacity: Mapping[str, Any],
    min_provider_count: int,
    min_api_format_count: int,
) -> list[str]:
    warnings = []
    if int(census.get("provider_count") or 0) < int(min_provider_count) and len(clean_profiles) > 1:
        warnings.append("provider_diversity_below_target")
    if len(census.get("api_format_counts") or {}) < int(min_api_format_count) and len(clean_profiles) > 1:
        warnings.append("api_format_diversity_below_target")
    if int(census.get("tool_candidate_count") or 0) < 1:
        warnings.append("weak_or_missing_tool_candidate")
    if int(census.get("pricing_known_count") or 0) < len(clean_profiles):
        warnings.append("some_model_pricing_unknown")
    if int(census.get("context_known_count") or 0) < len(clean_profiles):
        warnings.append("some_context_windows_unknown")
    missing_categories = [row for row in category_rows if row.get("category_ready") is not True]
    if missing_categories:
        warnings.append("benchmark_category_capability_coverage_incomplete")
    reason_codes = set(independent_verification_capacity.get("reason_codes") or [])
    if "answer_claim_verifier_new_profile_capacity_below_target" in reason_codes:
        warnings.append("answer_claim_verifier_new_profile_capacity_below_target")
    if "answer_claim_verifier_cross_provider_capacity_below_target" in reason_codes:
        warnings.append("answer_claim_verifier_cross_provider_capacity_below_target")
    if "answer_claim_verifier_live_probe_evidence_below_final_claim_target" in reason_codes:
        warnings.append("answer_claim_verifier_live_probe_evidence_below_final_claim_target")
    if {
        "answer_claim_verifier_pricing_metadata_incomplete",
        "answer_claim_verifier_context_metadata_incomplete",
    } & reason_codes:
        warnings.append("answer_claim_verifier_metadata_incomplete")
    return _dedupe_strings(warnings)


def _portfolio_recommendations(
    blockers: Sequence[str],
    warnings: Sequence[str],
    category_rows: Sequence[Mapping[str, Any]],
    role_rows: Sequence[Mapping[str, Any]],
    *,
    independent_verification_capacity: Mapping[str, Any],
) -> list[dict[str, Any]]:
    recommendations = []
    reason_set = set(blockers) | set(warnings)
    if {"empty_model_inventory", "fewer_than_three_provider_baseline_candidates"} & reason_set:
        recommendations.append(
            _portfolio_recommendation(
                "add_more_usable_provider_models",
                "P0",
                ["empty_model_inventory", "fewer_than_three_provider_baseline_candidates"],
                "Add at least three live-probed usable models so strongest, second, and third single-model baselines can be frozen before evaluation.",
            )
        )
    if {"missing_judge_candidate", "missing_structured_output_candidate", "required_fusion_role_coverage_incomplete"} & reason_set:
        missing_roles = [
            str(row.get("role") or "")
            for row in role_rows
            if row.get("role_ready") is not True
        ]
        recommendations.append(
            _portfolio_recommendation(
                "add_judge_structured_synthesis_capacity",
                "P0",
                ["missing_judge_candidate", "missing_structured_output_candidate", "required_fusion_role_coverage_incomplete"],
                "Add or annotate models with strong critique, structured-output, long-context, and synthesis capabilities.",
                details={"missing_roles": sorted(role for role in missing_roles if role)},
            )
        )
    if {
        "missing_independent_answer_claim_verifier",
        "answer_claim_verifier_new_profile_capacity_below_target",
        "answer_claim_verifier_cross_provider_capacity_below_target",
        "answer_claim_verifier_live_probe_evidence_below_final_claim_target",
    } & reason_set:
        recommendations.append(
            _portfolio_recommendation(
                "add_independent_answer_claim_verifier_capacity",
                "P0",
                [
                    "missing_independent_answer_claim_verifier",
                    "answer_claim_verifier_new_profile_capacity_below_target",
                    "answer_claim_verifier_cross_provider_capacity_below_target",
                    "answer_claim_verifier_live_probe_evidence_below_final_claim_target",
                ],
                "Add or live-probe at least two strong critique/structured-output verifier profiles across independent providers so same-source answer-claim consensus can be checked before final claims.",
                details={
                    "ready_verifier_count": int(independent_verification_capacity.get("ready_verifier_count") or 0),
                    "ready_provider_hash_count": int(independent_verification_capacity.get("ready_provider_hash_count") or 0),
                    "live_probe_evidence_ready_verifier_count": int(independent_verification_capacity.get("live_probe_evidence_ready_verifier_count") or 0),
                },
            )
        )
    if "missing_fast_candidate" in reason_set:
        recommendations.append(
            _portfolio_recommendation(
                "add_low_latency_fast_path",
                "P0",
                ["missing_fast_candidate"],
                "Add at least one low-latency or explicitly fast/mini/flash model so axio-fast can route without exceeding latency gates.",
            )
        )
    if {"provider_diversity_below_target", "api_format_diversity_below_target"} & reason_set:
        recommendations.append(
            _portfolio_recommendation(
                "increase_provider_and_api_diversity",
                "P1",
                ["provider_diversity_below_target", "api_format_diversity_below_target"],
                "Add providers and model transports across chat, responses, anthropic, or gemini-compatible formats to lower correlated failure risk.",
            )
        )
    weak_categories = [
        str(row.get("category") or "")
        for row in category_rows
        if row.get("category_ready") is not True
    ]
    if weak_categories:
        recommendations.append(
            _portfolio_recommendation(
                "fill_benchmark_category_capability_gaps",
                "P1",
                ["benchmark_category_capability_coverage_incomplete"],
                "Add or annotate models specialized for weak benchmark categories before running a costly 21-suite campaign.",
                details={"weak_categories": sorted(weak_categories)},
            )
        )
    if {"some_model_pricing_unknown", "some_context_windows_unknown"} & reason_set:
        recommendations.append(
            _portfolio_recommendation(
                "complete_cost_latency_context_metadata",
                "P2",
                ["some_model_pricing_unknown", "some_context_windows_unknown"],
                "Provide pricing and context metadata so router budget locks and prompt assembly can make safe decisions.",
            )
        )
    if not recommendations:
        recommendations.append(
            _portfolio_recommendation(
                "portfolio_ready_for_live_probe_and_benchmark_replay",
                "P3",
                [],
                "Portfolio priors are sufficient; next proof still requires live probing and benchmark replay.",
            )
        )
    return recommendations


def _portfolio_recommendation(
    recommendation_id: str,
    priority: str,
    reason_codes: Sequence[str],
    action: str,
    *,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "recommendation_id": recommendation_id,
        "priority": priority,
        "triggered_by_reason_codes": [reason for reason in reason_codes if reason],
        "action": action,
        "details": dict(details or {}),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _portfolio_latency_score(profile: ModelProfile) -> float:
    latency = _optional_float(profile.p50_latency_ms, profile.p95_latency_ms)
    if latency is None or latency <= 0:
        return 0.45
    return max(0.0, min(1.0, 1.0 - min(float(latency), 8000.0) / 8000.0))


def _portfolio_reliability_score(profile: ModelProfile) -> float:
    if profile.recent_success_rate is not None:
        return max(0.0, min(1.0, float(profile.recent_success_rate)))
    if profile.availability is not None:
        return max(0.0, min(1.0, float(profile.availability)))
    total = int(profile.observed_success_count or 0) + int(profile.observed_failure_count or 0)
    if total > 0:
        return max(0.0, min(1.0, float(profile.observed_success_count or 0) / total))
    return 0.65 if str(profile.health or "").lower() == "available" else 0.50


def _profile_has_live_evidence(profile: ModelProfile) -> bool:
    source = str(profile.source or "").lower()
    health = str(profile.health or "").lower()
    return "live" in source or (health == "available" and int(profile.observed_success_count or 0) > 0)


def _is_fast_candidate(profile: ModelProfile) -> bool:
    if profile.p50_latency_ms is not None and int(profile.p50_latency_ms) <= 1800:
        return True
    model_name = profile.model.lower()
    return any(token in model_name for token in ("flash", "fast", "mini", "20b", "7b", "4b"))


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _redacted_registry_evidence_from_profiles(
    *,
    profiles: Sequence[ModelProfile],
    probe_paths: Sequence[str | Path],
    payload_count: int,
    probe_row_count: int,
    status_counts: Mapping[str, int],
    mode_counts: Mapping[str, int],
    include_unavailable: bool,
    available_count: int,
    live_available_count: int,
    min_available_models: int,
    blockers: Sequence[str],
) -> dict[str, Any]:
    profile_hashes = sorted(sha256_text(profile.profile_id) for profile in profiles)
    provider_hashes = sorted({sha256_text(profile.provider) for profile in profiles})
    census = _registry_census(profiles, redact_provider_identifiers=True)
    model_receipts = [
        {
            "profile_id_sha256": sha256_text(profile.profile_id),
            "provider_sha256": sha256_text(profile.provider),
            "model_sha256": sha256_text(profile.model),
            "api_format": profile.api_format,
            "capabilities": {axis: profile.capability(axis) for axis in CAPABILITY_AXES},
            "p50_latency_ms": profile.p50_latency_ms,
            "p95_latency_ms": profile.p95_latency_ms,
            "context_tokens": profile.context_tokens,
            "pricing_known": profile.input_cost_per_million is not None and profile.output_cost_per_million is not None,
            "supports_tools": profile.supports_tools,
            "supports_vision": profile.supports_vision,
            "recent_success_rate": profile.recent_success_rate,
            "availability": profile.availability,
            "observed_success_count": profile.observed_success_count,
            "observed_failure_count": profile.observed_failure_count,
            "health": profile.health,
            "source": profile.source,
            "auth_scheme": profile.auth_scheme,
            "models_endpoint": profile.models_endpoint,
            "discover_models": profile.discover_models,
            "base_url_env_sha256": sha256_text(profile.base_url_env) if profile.base_url_env else "",
            "api_key_env_sha256": sha256_text(profile.api_key_env) if profile.api_key_env else "",
            "raw_provider_name_persisted": False,
            "raw_provider_model_id_persisted": False,
            "raw_profile_id_persisted": False,
            "raw_base_url_env_name_persisted": False,
            "raw_api_key_env_name_persisted": False,
            "base_url_persisted": False,
            "api_key_persisted": False,
        }
        for profile in profiles
    ]
    model_receipts.sort(key=lambda row: str(row.get("profile_id_sha256") or ""))
    ready = not blockers
    return {
        "schema": "axio_fusion_api.registry_evidence.v1",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "generated_from_probe": True,
        "operational_registry": False,
        "public_models": ["axio-fast", "axio-terra", "axio-pro"],
        "source_artifacts": {
            "probe_file_count": len(probe_paths),
            "probe_file_path_hashes": [sha256_text(str(path)) for path in probe_paths],
            "probe_payload_count": int(payload_count),
            "probe_row_count": int(probe_row_count),
            "status_counts": dict(sorted(status_counts.items())),
            "mode_counts": dict(sorted(mode_counts.items())),
            "api_format_counts": census["api_format_counts"],
            "provider_format_hash_counts": census["provider_format_counts"],
            "include_unavailable": bool(include_unavailable),
            "raw_probe_paths_persisted": False,
            "raw_provider_outputs_persisted": False,
        },
        "model_count": len(profiles),
        "provider_count": len(provider_hashes),
        "available_model_count": int(available_count),
        "live_available_model_count": int(live_available_count),
        "profile_hash_count": len(profile_hashes),
        "profile_set_sha256": sha256_text(stable_json(profile_hashes)),
        "provider_hash_count": len(provider_hashes),
        "provider_set_sha256": sha256_text(stable_json(provider_hashes)),
        "readiness": {
            "ready": ready,
            "status": "ready" if ready else "blocked",
            "blockers": list(blockers),
            "warnings": registry_readiness(profiles)["warnings"],
            "api_format_counts": census["api_format_counts"],
            "provider_format_hash_counts": census["provider_format_counts"],
            "judge_candidate_count": census["judge_candidate_count"],
            "structured_candidate_count": census["structured_candidate_count"],
            "fast_candidate_count": census["fast_candidate_count"],
            "tool_candidate_count": census["tool_candidate_count"],
            "pricing_known_count": census["pricing_known_count"],
            "context_known_count": census["context_known_count"],
            "min_available_models": int(min_available_models),
            "probe_mode_counts": dict(sorted(mode_counts.items())),
            "live_available_model_count": int(live_available_count),
            "live_probe_proven": int(live_available_count) >= int(min_available_models),
            "final_claim_registry_ready": ready and int(live_available_count) >= int(min_available_models),
            "raw_prompt_persisted": False,
            "secrets_persisted": False,
        },
        "model_receipts": model_receipts,
        "provider_identifier_redaction": {
            "schema": "axio_fusion_api.provider_identifier_redaction.v1",
            "enabled": True,
            "provider_names_replaced_by_sha256": True,
            "provider_model_ids_replaced_by_sha256": True,
            "profile_ids_replaced_by_sha256": True,
            "operational_registry_required_for_live_calls": True,
            "live_probe_evidence_required_for_final_claims": True,
        },
        "generation_contract": {
            "input_must_be_prompt_free_probe_artifacts": True,
            "only_available_models_included_by_default": True,
            "live_probe_evidence_required_for_final_claims": True,
            "evidence_only_not_loadable_as_operational_registry": True,
            "api_keys_persisted": False,
            "base_urls_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_outputs_persisted": False,
            "raw_provider_error_details_persisted": False,
        },
        "secrets_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_provider_model_id_persisted": False,
        "raw_provider_output_persisted": False,
    }


def registry_readiness(profiles: Sequence[ModelProfile]) -> dict[str, Any]:
    census = _registry_census(profiles)
    blockers = []
    warnings = []
    if not profiles:
        blockers.append("empty_model_inventory")
    if not any(profile.api_key_env for profile in profiles):
        warnings.append("no_api_key_env_declared")
    if census["judge_candidate_count"] < 1:
        warnings.append("weak_or_missing_judge_candidate")
    if census["structured_candidate_count"] < 1:
        warnings.append("weak_or_missing_structured_output_candidate")
    if census["fast_candidate_count"] < 1:
        warnings.append("weak_or_missing_fast_candidate")
    if len(profiles) > 1 and census["provider_count"] < 2:
        warnings.append("single_provider_model_pool")
    return {
        "ready": not blockers,
        "status": "ready" if not blockers and not warnings else ("blocked" if blockers else "usable_with_warnings"),
        "blockers": blockers,
        "warnings": warnings,
        "model_count": census["model_count"],
        "provider_count": census["provider_count"],
        "api_format_counts": census["api_format_counts"],
        "provider_format_counts": census["provider_format_counts"],
        "judge_candidate_count": census["judge_candidate_count"],
        "structured_candidate_count": census["structured_candidate_count"],
        "fast_candidate_count": census["fast_candidate_count"],
        "tool_candidate_count": census["tool_candidate_count"],
        "pricing_known_count": census["pricing_known_count"],
        "context_known_count": census["context_known_count"],
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def normalize_profile(raw: Mapping[str, Any]) -> ModelProfile:
    provider = str(raw.get("provider") or _infer_provider(str(raw.get("model") or raw.get("id") or ""))).strip() or "openai-compatible"
    model = str(raw.get("model") or raw.get("id") or raw.get("name") or "unknown-model").strip()
    api_format = _normalize_api_format_name(raw.get("api_format") or raw.get("api_mode") or _infer_api_format(provider))
    caps = _normalize_capabilities(raw.get("capabilities") or raw.get("scores") or {}, model=model)
    screening_summary = raw.get("screening_capability_summary")
    screening_summary = screening_summary if isinstance(screening_summary, Mapping) else {}
    screening_axes = raw.get("screening_capability_axes")
    if not isinstance(screening_axes, Mapping):
        screening_axes = screening_summary.get("axes")
    screening_overall = _optional_float(
        raw.get("screening_capability_overall"),
        screening_summary.get("overall"),
    )
    return ModelProfile(
        provider=provider,
        model=model,
        api_format=api_format,
        capabilities=caps,
        input_cost_per_million=_optional_float(
            raw.get("input_cost_per_million"),
            raw.get("input_usd_per_million_tokens"),
        ),
        output_cost_per_million=_optional_float(
            raw.get("output_cost_per_million"),
            raw.get("output_usd_per_million_tokens"),
        ),
        p50_latency_ms=_optional_int(raw.get("p50_latency_ms"), raw.get("observed_latency_ms")),
        p95_latency_ms=_optional_int(raw.get("p95_latency_ms")),
        context_tokens=_optional_int(raw.get("context_tokens"), raw.get("context_window_tokens")),
        recent_success_rate=_optional_float(raw.get("recent_success_rate"), raw.get("success_rate")),
        availability=_optional_float(raw.get("availability"), raw.get("observed_availability")),
        observed_success_count=_optional_int(raw.get("observed_success_count"), raw.get("success_count")) or 0,
        observed_failure_count=_optional_int(raw.get("observed_failure_count"), raw.get("failure_count")) or 0,
        supports_tools=_coerce_bool(raw.get("supports_tools", raw.get("tool_calling", False))),
        tool_capability=str(
            raw.get("tool_capability")
            or raw.get("toolCapability")
            or ""
        ),
        tool_capability_source=str(
            raw.get("tool_capability_source")
            or raw.get("toolCapabilitySource")
            or ""
        ),
        tool_probe_status=str(
            raw.get("tool_probe_status")
            or raw.get("toolProbeStatus")
            or "not_run"
        ),
        supports_vision=_coerce_bool(raw.get("supports_vision", raw.get("vision", False))),
        vision_probe_status=str(
            raw.get("vision_probe_status")
            or raw.get("visionProbeStatus")
            or "not_run"
        ),
        vision_capability_source=str(
            raw.get("vision_capability_source")
            or raw.get("visionCapabilitySource")
            or ""
        ),
        model_kind=str(
            raw.get("model_kind")
            or raw.get("modelKind")
            or raw.get("modality")
            or raw.get("model_modality")
            or "text"
        ),
        image_capabilities=(
            dict(raw.get("image_capabilities"))
            if isinstance(raw.get("image_capabilities"), Mapping)
            else (
                dict(raw.get("imageCapabilities"))
                if isinstance(raw.get("imageCapabilities"), Mapping)
                else {}
            )
        ),
        image_probe_status=str(
            raw.get("image_probe_status")
            or raw.get("imageProbeStatus")
            or "not_run"
        ),
        privacy_tags=_normalize_privacy_tags(raw.get("privacy_tags", ["external_provider"])),
        base_url_env=str(raw.get("base_url_env") or _default_base_url_env(provider)),
        api_key_env=str(raw.get("api_key_env") or _default_api_key_env(provider)),
        auth_scheme=_normalize_auth_scheme(raw.get("auth_scheme") or raw.get("auth") or _default_auth_scheme(provider, api_format)),
        max_output_tokens_parameter=str(
            raw.get("max_output_tokens_parameter")
            or raw.get("maxOutputTokensParameter")
            or raw.get("max_tokens_parameter")
            or "max_tokens"
        ),
        models_endpoint=str(
            raw.get("models_endpoint")
            or raw.get("modelsEndpoint")
            or raw.get("model_list_endpoint")
            or raw.get("modelListEndpoint")
            or "/models"
        ).strip(),
        discover_models=_coerce_bool(
            raw.get("discover_models", raw.get("discoverModels", True)),
            default=True,
        ),
        enabled=_coerce_bool(raw.get("enabled", True), default=True),
        health=str(raw.get("health") or "unknown"),
        source=str(raw.get("source") or "registry"),
        canonical_model_id=str(
            raw.get("canonical_model_id")
            or raw.get("canonicalModelId")
            or raw.get("canonical_model")
            or raw.get("canonicalModel")
            or raw.get("canonical_identity")
            or raw.get("canonicalIdentity")
            or ""
        ).strip(),
        screening_prior_rank=_optional_int(
            raw.get("screening_prior_rank"),
            raw.get("research_prior_rank"),
        ),
        screening_prior_confidence=_optional_float(
            raw.get("screening_prior_confidence"),
            raw.get("research_confidence"),
        ),
        screening_allowed_roles=_normalize_role_names(
            raw.get("screening_allowed_roles", raw.get("allowed_roles", ()))
        ),
        screening_disallowed_roles=_normalize_role_names(
            raw.get("screening_disallowed_roles", raw.get("disallowed_roles", ()))
        ),
        screening_capability_overall=(
            max(0.0, min(1.0, screening_overall))
            if screening_overall is not None
            else None
        ),
        screening_capability_axes=_normalize_screening_capability_axes(screening_axes),
        screening_role_admission=(
            dict(raw.get("screening_role_admission"))
            if isinstance(raw.get("screening_role_admission"), Mapping)
            else {}
        ),
        screening_research_quality_score=_optional_float(
            raw.get("screening_research_quality_score"),
        ),
        screening_operational_rank=_optional_int(
            raw.get("screening_operational_rank"),
            raw.get("operational_rank"),
        ),
        screening_operational_score=_optional_float(
            raw.get("screening_operational_score"),
            raw.get("operational_score"),
        ),
        screening_operational_status=str(
            raw.get("screening_operational_status")
            or raw.get("operational_status")
            or ""
        ),
        screening_stream_reliability_score=_optional_float(
            raw.get("screening_stream_reliability_score"),
            raw.get("stream_reliability_score"),
        ),
        screening_latency_score=_optional_float(
            raw.get("screening_latency_score"),
            raw.get("latency_score"),
        ),
        reasoning_transport=(
            dict(raw.get("reasoning_transport"))
            if isinstance(raw.get("reasoning_transport"), Mapping)
            else (
                dict(raw.get("reasoningTransport"))
                if isinstance(raw.get("reasoningTransport"), Mapping)
                else {}
            )
        ),
        screening_reasoning_capability=(
            dict(raw.get("screening_reasoning_capability"))
            if isinstance(raw.get("screening_reasoning_capability"), Mapping)
            else (
                dict(raw.get("screeningReasoningCapability"))
                if isinstance(raw.get("screeningReasoningCapability"), Mapping)
                else {}
            )
        ),
        traffic_control=(
            dict(raw.get("traffic_control"))
            if isinstance(raw.get("traffic_control"), Mapping)
            else (
                dict(raw.get("trafficControl"))
                if isinstance(raw.get("trafficControl"), Mapping)
                else {}
            )
        ),
    )


def _profile(**kwargs: Any) -> ModelProfile:
    return ModelProfile(**kwargs)


def _normalize_role_names(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    normalized: list[str] = []
    for item in values:
        role = " ".join(str(item or "").strip().casefold().split())
        if role and role not in normalized:
            normalized.append(role)
    return tuple(normalized[:24])


def _load_registry_payload(path: str | Path | None) -> dict[str, Any]:
    env_path = os.getenv("AXIO_FUSION_REGISTRY_PATH", "").strip()
    selected = Path(path or env_path) if (path or env_path) else None
    if selected and selected.exists():
        with selected.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return {"models": payload}
        if isinstance(payload, dict):
            if payload.get("generated_from_prefusion_screening") is True:
                return _validate_prefusion_registry_payload(payload)
            return payload
    env_models = _models_from_env()
    if env_models:
        return {"models": env_models}
    # Once an operator supplies a provider manifest, it becomes the source of
    # truth for the process.  A provider-level endpoint without a static model
    # list is intentionally not a serving registry: it must first complete
    # /models discovery and probe-bound enrollment (or bind an explicit
    # calibrated registry).  Falling back to the built-in seed here could send
    # traffic to an unrelated, stale channel configuration.
    if _provider_configuration_is_present():
        return {
            "schema": "axio_fusion_api.registry.v1",
            "models": [],
            "registry_source": "provider_config_requires_enrollment",
            "readiness": {
                "status": "blocked",
                "blockers": ["provider_config_requires_enrollment"],
            },
        }
    return build_default_registry()


def _validate_prefusion_registry_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed when a screening-generated registry loses its bindings."""

    result = dict(payload)
    binding_status = str(result.get("binding_status") or "").strip().casefold()
    binding = result.get("prefusion_screening")
    binding = binding if isinstance(binding, Mapping) else {}
    catalog = result.get("prefusion_model_catalog")
    catalog = catalog if isinstance(catalog, Mapping) else {}
    models = result.get("models") if isinstance(result.get("models"), list) else []
    if binding_status != "ready":
        return {
            **result,
            "models": [],
            "model_count": 0,
            "available_model_count": 0,
            "live_available_model_count": 0,
            "available_logical_model_count": 0,
        }
    rows = binding.get("eligible_profile_bindings")
    rows = rows if isinstance(rows, list) else []
    valid_bindings = bool(models) and bool(rows) and len(rows) == len(models)
    model_hashes: set[str] = set()
    if valid_bindings:
        for model in models:
            if not isinstance(model, Mapping) or not str(model.get("profile_id") or ""):
                valid_bindings = False
                break
            model_hashes.add(sha256_text(str(model.get("profile_id") or "")).lower())
    binding_hashes: set[str] = set()
    if valid_bindings:
        for row in rows:
            if not isinstance(row, Mapping):
                valid_bindings = False
                break
            profile_hash = str(row.get("profile_id_sha256") or "").strip().lower()
            if not is_sha256_digest(profile_hash) or profile_hash in binding_hashes:
                valid_bindings = False
                break
            binding_hashes.add(profile_hash)
    valid_bindings = valid_bindings and model_hashes == binding_hashes
    catalog_valid = _prefusion_model_catalog_matches_binding(
        catalog=catalog,
        binding=binding,
        models=models,
    )
    for row in rows:
        if not isinstance(row, Mapping):
            valid_bindings = False
            break
        if (
            str(row.get("status") or "") != "available"
            or str(row.get("probe_mode") or "").strip().casefold() != "live"
            or row.get("live_probe_evidence") is not True
            or row.get("stream_requested") is not True
            or row.get("stream_observed") is not True
            or row.get("stream_fallback_used") is True
            or not is_sha256_digest(row.get("output_sha256"))
            or measured_stream_latency_eligibility(row).get("eligible") is not True
            or streaming_evidence_eligibility(row).get("eligible") is not True
        ):
            valid_bindings = False
            break
    if valid_bindings and not _prefusion_logical_projection_matches_models(
        binding.get("available_model_list"),
        models,
    ):
        valid_bindings = False
    if not catalog_valid:
        valid_bindings = False
    if binding_status == "ready" and not valid_bindings:
        return {
            **result,
            "models": [],
            "model_count": 0,
            "available_model_count": 0,
            "live_available_model_count": 0,
            "available_logical_model_count": 0,
            "binding_status": "blocked",
            "readiness": {
                "status": "blocked",
                "ready": False,
                "blockers": [
                    "prefusion_model_catalog_binding_invalid"
                    if not catalog_valid
                    else "prefusion_registry_probe_binding_invalid"
                ],
            },
        }
    contract = validate_prefusion_registry_handoff(result, require_ready=True)
    if not contract.get("valid"):
        return {
            **result,
            "models": [],
            "model_count": 0,
            "available_model_count": 0,
            "live_available_model_count": 0,
            "available_logical_model_count": 0,
            "binding_status": "blocked",
            "readiness": {
                "status": "blocked",
                "ready": False,
                "blockers": ["prefusion_handoff_contract_invalid"],
                "contract_reason_codes": list(contract.get("reason_codes") or []),
            },
        }
    return result


def validate_prefusion_registry_handoff(
    payload: Mapping[str, Any],
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    """Validate the physical and logical projections of a pre-Fusion registry.

    This is deliberately a hash/count/schema validator.  It does not inspect
    provider output bodies or claim that a research prior is benchmark
    evidence.  The result is safe to persist and is used at the registry load
    boundary so an edited serving list cannot bypass the original streaming
    and latency admission evidence.
    """

    issues: list[str] = []
    if not isinstance(payload, Mapping):
        return {
            "schema": "axio_fusion_api.prefusion_registry_handoff_validation.v1",
            "valid": False,
            "reason_codes": ["prefusion_registry_payload_invalid"],
            "require_ready": bool(require_ready),
        }

    if payload.get("generated_from_prefusion_screening") is not True:
        issues.append("prefusion_registry_generation_marker_missing")
    binding_status = str(payload.get("binding_status") or "").strip().casefold()
    if require_ready and binding_status != "ready":
        issues.append("prefusion_registry_binding_not_ready")

    models = payload.get("models")
    models = models if isinstance(models, list) else []
    binding = payload.get("prefusion_screening")
    binding = binding if isinstance(binding, Mapping) else {}
    rows = binding.get("eligible_profile_bindings")
    rows = rows if isinstance(rows, list) else []
    logical = binding.get("available_model_list")
    logical = logical if isinstance(logical, list) else []
    generation_contract = payload.get("generation_contract")
    generation_contract = (
        generation_contract if isinstance(generation_contract, Mapping) else {}
    )
    multi_sample_stability_required = binding.get(
        "multi_sample_stream_stability_required"
    ) is True
    if generation_contract.get("multi_sample_stream_stability_required") is True:
        multi_sample_stability_required = True
    stability_contract = binding.get("stream_stability_contract")
    stability_contract = (
        stability_contract if isinstance(stability_contract, Mapping) else {}
    )
    required_stability_samples = 1
    if multi_sample_stability_required:
        try:
            required_stability_samples = int(
                stability_contract.get("samples_per_profile")
            )
        except (TypeError, ValueError):
            required_stability_samples = 0
        if (
            str(stability_contract.get("schema") or "")
            != "axio_fusion_api.provider_probe_stability_contract.v1"
            or required_stability_samples < 2
            or required_stability_samples > 5
            or stability_contract.get("requires_all_samples_success") is not True
            or stability_contract.get(
                "requires_each_sample_latency_at_or_below_90_seconds"
            )
            is not True
            or stability_contract.get("requires_each_sample_strict_streaming")
            is not True
            or generation_contract.get("multi_sample_stream_stability_required")
            is not True
        ):
            issues.append("prefusion_registry_stream_stability_contract_invalid")

    role_probe_required = bool(
        binding.get("role_probe_required") is True
        or generation_contract.get("role_probe_contract_required") is True
    )
    if role_probe_required:
        issues.extend(
            _validate_prefusion_role_probe_binding(
                binding=binding,
                models=models,
                generation_contract=generation_contract,
            )
        )

    model_hashes: set[str] = set()
    canonical_to_model_hashes: dict[str, set[str]] = {}
    for model in models:
        if not isinstance(model, Mapping):
            issues.append("prefusion_registry_model_row_invalid")
            continue
        profile_id = str(model.get("profile_id") or "").strip()
        canonical = _normalized_prefusion_identity(
            model.get("canonical_model_id") or model.get("model")
        )
        profile_hash = sha256_text(profile_id).lower() if profile_id else ""
        if not profile_id or not canonical:
            issues.append("prefusion_registry_model_identity_missing")
            continue
        if profile_hash in model_hashes:
            issues.append("prefusion_registry_duplicate_profile")
        model_hashes.add(profile_hash)
        canonical_to_model_hashes.setdefault(canonical, set()).add(profile_hash)
        if model.get("enabled") is not True:
            issues.append("prefusion_registry_model_disabled")
        if str(model.get("health") or "").strip().casefold() != "available":
            issues.append("prefusion_registry_model_health_invalid")

    binding_hashes: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            issues.append("prefusion_registry_probe_binding_row_invalid")
            continue
        profile_hash = str(row.get("profile_id_sha256") or "").strip().lower()
        if not is_sha256_digest(profile_hash):
            issues.append("prefusion_registry_probe_profile_hash_invalid")
        elif profile_hash in binding_hashes:
            issues.append("prefusion_registry_duplicate_probe_binding")
        binding_hashes.add(profile_hash)
        if (
            str(row.get("status") or "").strip().casefold() != "available"
            or str(row.get("probe_mode") or "").strip().casefold() != "live"
            or row.get("live_probe_evidence") is not True
            or row.get("stream_requested") is not True
            or row.get("stream_observed") is not True
            or row.get("stream_fallback_used") is True
            or row.get("strict_streaming_requested") is not True
            or not is_sha256_digest(row.get("output_sha256"))
        ):
            issues.append("prefusion_registry_probe_evidence_invalid")
        if streaming_evidence_eligibility(row).get("eligible") is not True:
            issues.append("prefusion_registry_stream_evidence_invalid")
        if measured_stream_latency_eligibility(row).get("eligible") is not True:
            issues.append("prefusion_registry_stream_latency_invalid")
        latency = row.get("latency_eligibility")
        if not isinstance(latency, Mapping) or latency.get("eligible") is not True:
            issues.append("prefusion_registry_latency_receipt_invalid")
        if multi_sample_stability_required:
            try:
                sample_count = int(row.get("stability_sample_count"))
                completed_count = int(row.get("stability_completed_sample_count"))
                success_count = int(row.get("stability_success_count"))
                failure_count = int(row.get("stability_failure_count"))
                success_rate = float(row.get("stability_success_rate"))
            except (TypeError, ValueError):
                sample_count = completed_count = success_count = -1
                failure_count = -1
                success_rate = -1.0
            if (
                sample_count != required_stability_samples
                or completed_count != required_stability_samples
                or success_count != required_stability_samples
                or failure_count != 0
                or abs(success_rate - 1.0) > 1e-9
                or row.get("all_samples_eligible") is not True
                or not is_sha256_digest(row.get("sample_receipts_sha256"))
            ):
                issues.append("prefusion_registry_stream_stability_evidence_invalid")

    if model_hashes != binding_hashes:
        issues.append("prefusion_registry_model_probe_binding_mismatch")
    if not models and binding_status == "ready":
        issues.append("prefusion_registry_ready_without_models")
    if not rows and binding_status == "ready":
        issues.append("prefusion_registry_ready_without_probe_bindings")

    observed_canonical_to_hashes: dict[str, set[str]] = {}
    observed_available_ranks: list[int] = []
    observed_research_ranks: list[int] = []
    observed_operational_ranks: list[int] = []
    for row in logical:
        if not isinstance(row, Mapping):
            issues.append("prefusion_registry_logical_row_invalid")
            continue
        canonical = _normalized_prefusion_identity(row.get("canonical_model_id"))
        canonical_hash = str(row.get("canonical_identity_sha256") or "").strip().lower()
        hashes = row.get("replica_profile_id_sha256s")
        hashes = [str(value or "").strip().lower() for value in hashes] if isinstance(hashes, list) else []
        try:
            rank = int(row.get("rank"))
            available_rank = int(row.get("available_rank"))
            replica_count = int(row.get("replica_count"))
            research_rank = int(row.get("research_prior_rank"))
            operational_rank = int(row.get("operational_rank"))
        except (TypeError, ValueError):
            issues.append("prefusion_registry_logical_rank_invalid")
            continue
        if not canonical or canonical in observed_canonical_to_hashes:
            issues.append("prefusion_registry_logical_canonical_duplicate")
        if canonical_hash != sha256_text(canonical).lower():
            issues.append("prefusion_registry_logical_canonical_hash_invalid")
        if (
            not hashes
            or len(hashes) != len(set(hashes))
            or not all(is_sha256_digest(value) for value in hashes)
            or replica_count != len(hashes)
            or rank < 1
            or research_rank < 1
            or operational_rank < 1
            or available_rank < 1
            or rank != research_rank
            or available_rank != operational_rank
        ):
            issues.append("prefusion_registry_logical_replica_projection_invalid")
        observed_canonical_to_hashes[canonical] = set(hashes)
        observed_available_ranks.append(available_rank)
        observed_research_ranks.append(research_rank)
        observed_operational_ranks.append(operational_rank)
        if row.get("streaming_eligible") is not True:
            issues.append("prefusion_registry_logical_streaming_flag_invalid")
        if row.get("replicas_are_failover_not_independent_votes") is not True:
            issues.append("prefusion_registry_replica_policy_invalid")
        if row.get("research_prior_only") is not True:
            issues.append("prefusion_registry_ranking_evidence_flag_invalid")

    if logical and observed_available_ranks != list(range(1, len(logical) + 1)):
        issues.append("prefusion_registry_available_rank_not_contiguous")
    if logical and (
        len(observed_research_ranks) != len(set(observed_research_ranks))
    ):
        issues.append("prefusion_registry_research_rank_duplicate")
    if logical and observed_operational_ranks != list(range(1, len(logical) + 1)):
        issues.append("prefusion_registry_operational_rank_not_contiguous")
    if observed_canonical_to_hashes != canonical_to_model_hashes:
        issues.append("prefusion_registry_logical_physical_projection_mismatch")

    # Role coverage is part of the private registry boundary, not merely a
    # report diagnostic. Recompute it from the exact logical serving list so
    # editing the binding or catalog cannot silently promote a model into a
    # Fusion stage. This local check intentionally has no dependency on the
    # screening module, which keeps registry loading independently verifiable.
    expected_role_coverage, role_coverage_issues = _prefusion_role_coverage_projection(
        logical
    )
    issues.extend(role_coverage_issues)
    binding_role_coverage = binding.get("role_coverage")
    if not isinstance(binding_role_coverage, Mapping):
        issues.append("prefusion_registry_role_coverage_missing")
    elif stable_json(dict(binding_role_coverage)) != stable_json(expected_role_coverage):
        issues.append("prefusion_registry_role_coverage_projection_mismatch")

    catalog = payload.get("prefusion_model_catalog")
    catalog = catalog if isinstance(catalog, Mapping) else {}
    catalog_inventory = catalog.get("inventory")
    catalog_inventory = catalog_inventory if isinstance(catalog_inventory, Mapping) else {}
    catalog_ranking = catalog.get("ranking")
    catalog_ranking = catalog_ranking if isinstance(catalog_ranking, Mapping) else {}
    catalog_rows = catalog_ranking.get("ordered_models")
    catalog_rows = catalog_rows if isinstance(catalog_rows, list) else []
    catalog_available = catalog.get("available_model_list")
    catalog_available = catalog_available if isinstance(catalog_available, list) else []
    if (
        str(catalog.get("schema") or "") != "axio_fusion_api.prefusion_model_catalog.v1"
        or str(catalog.get("status") or "").strip().casefold() != "ready"
        or catalog_inventory.get("complete") is not True
        or catalog_inventory.get("ranking_complete") is not True
    ):
        issues.append("prefusion_registry_model_catalog_invalid")
    if stable_json(catalog_available) != stable_json(logical):
        issues.append("prefusion_registry_catalog_available_list_mismatch")
    catalog_role_coverage = catalog.get("role_coverage")
    if not isinstance(catalog_role_coverage, Mapping):
        issues.append("prefusion_registry_catalog_role_coverage_missing")
    elif stable_json(dict(catalog_role_coverage)) != stable_json(expected_role_coverage):
        issues.append("prefusion_registry_catalog_role_coverage_projection_mismatch")
    expected_catalog_hash = str(binding.get("model_catalog_content_sha256") or "").strip().lower()
    if not is_sha256_digest(expected_catalog_hash) or expected_catalog_hash != sha256_text(
        stable_json(dict(catalog))
    ).lower():
        issues.append("prefusion_registry_catalog_hash_invalid")
    try:
        if int(payload.get("model_count") or 0) != len(models):
            issues.append("prefusion_registry_model_count_invalid")
        if int(payload.get("available_model_count") or 0) != len(models):
            issues.append("prefusion_registry_available_count_invalid")
        if int(payload.get("live_available_model_count") or 0) != len(models):
            issues.append("prefusion_registry_live_count_invalid")
        if int(payload.get("available_logical_model_count") or 0) != len(logical):
            issues.append("prefusion_registry_logical_count_invalid")
        if int(binding.get("eligible_profile_count") or 0) != len(models):
            issues.append("prefusion_registry_binding_count_invalid")
        if int(binding.get("available_logical_model_count") or 0) != len(logical):
            issues.append("prefusion_registry_binding_logical_count_invalid")
        if int(catalog_inventory.get("available_physical_profile_count") or 0) != len(models):
            issues.append("prefusion_registry_catalog_physical_count_invalid")
        if int(catalog_inventory.get("available_logical_model_count") or 0) != len(logical):
            issues.append("prefusion_registry_catalog_logical_count_invalid")
        if int(catalog_inventory.get("logical_candidate_count") or 0) != int(
            catalog_inventory.get("ranked_logical_model_count") or 0
        ):
            issues.append("prefusion_registry_catalog_ranking_count_invalid")
    except (TypeError, ValueError):
        issues.append("prefusion_registry_count_field_invalid")

    ranking_ranks: list[int] = []
    ranking_ids: set[str] = set()
    ranking_canonicals: set[str] = set()
    ranking_available_hashes: dict[str, set[str]] = {}
    for row in catalog_rows:
        if not isinstance(row, Mapping):
            issues.append("prefusion_registry_catalog_ranking_row_invalid")
            continue
        try:
            rank = int(row.get("rank"))
        except (TypeError, ValueError):
            issues.append("prefusion_registry_catalog_ranking_rank_invalid")
            continue
        candidate_id = str(row.get("candidate_id") or "")
        canonical = _normalized_prefusion_identity(row.get("canonical_model_id"))
        ranking_ranks.append(rank)
        if not candidate_id or candidate_id in ranking_ids or not canonical:
            issues.append("prefusion_registry_catalog_ranking_identity_invalid")
        ranking_ids.add(candidate_id)
        if canonical in ranking_canonicals:
            issues.append("prefusion_registry_catalog_ranking_canonical_duplicate")
        ranking_canonicals.add(canonical)
        try:
            replica_count = int(row.get("replica_count"))
        except (TypeError, ValueError):
            replica_count = -1
        replicas = row.get("replicas")
        replicas = replicas if isinstance(replicas, list) else []
        eligible_hashes = row.get("eligible_replica_profile_id_sha256s")
        eligible_hashes = (
            [str(value or "").strip().lower() for value in eligible_hashes]
            if isinstance(eligible_hashes, list)
            else []
        )
        if (
            replica_count != len(replicas)
            or len(eligible_hashes) != len(set(eligible_hashes))
            or not all(is_sha256_digest(value) for value in eligible_hashes)
            or not set(eligible_hashes).issubset(model_hashes)
        ):
            issues.append("prefusion_registry_catalog_replica_projection_invalid")
        ranking_available_hashes[canonical] = set(eligible_hashes)
        capability_coverage = capability_axis_coverage(
            {
                "overall": row.get("capability_overall"),
                "axes": row.get("capability_axes"),
            }
        )
        if capability_coverage.get("eligible") is not True:
            issues.append("prefusion_registry_capability_axis_coverage_invalid")
        if row.get("ranking_prior_only") is not True:
            issues.append("prefusion_registry_catalog_ranking_evidence_flag_invalid")
    expected_candidate_count = int(catalog_inventory.get("logical_candidate_count") or 0)
    if (
        len(catalog_rows) != expected_candidate_count
        or sorted(ranking_ranks) != list(range(1, len(catalog_rows) + 1))
    ):
        issues.append("prefusion_registry_catalog_ranking_incomplete")
    logical_hashes_by_canonical = {
        _normalized_prefusion_identity(row.get("canonical_model_id")): set(
            str(value or "").strip().lower()
            for value in row.get("replica_profile_id_sha256s", [])
        )
        for row in logical
        if isinstance(row, Mapping)
    }
    for canonical, hashes in logical_hashes_by_canonical.items():
        if ranking_available_hashes.get(canonical) != hashes:
            issues.append("prefusion_registry_catalog_available_replica_mismatch")
    research = payload.get("research_ranking")
    research = research if isinstance(research, Mapping) else {}
    if int(research.get("candidate_count") or 0) != len(catalog_rows):
        issues.append("prefusion_registry_research_ranking_count_invalid")
    if research.get("ranking_prior_only") is not True:
        issues.append("prefusion_registry_research_prior_flag_invalid")
    research_rows = research.get("ordered_models")
    research_rows = research_rows if isinstance(research_rows, list) else []
    if len(research_rows) != len(catalog_rows):
        issues.append("prefusion_registry_research_ranking_rows_invalid")
    else:
        research_ids = {
            str(row.get("candidate_id") or "")
            for row in research_rows
            if isinstance(row, Mapping)
        }
        if research_ids != ranking_ids:
            issues.append("prefusion_registry_research_ranking_identity_mismatch")
        for row in research_rows:
            if not isinstance(row, Mapping):
                issues.append("prefusion_registry_research_ranking_row_invalid")
                continue
            capability_coverage = capability_axis_coverage(
                {
                    "overall": row.get("capability_overall"),
                    "axes": row.get("capability_axes"),
                }
            )
            if capability_coverage.get("eligible") is not True:
                issues.append("prefusion_registry_capability_axis_coverage_invalid")

    # New handoffs carry a logical-model serving order computed from the
    # research prior plus live stream evidence.  Keep the old registry format
    # readable as a legacy contract, but never treat its missing operational
    # fields as if they had been measured by this workflow.
    catalog_operational = catalog.get("operational_ranking")
    operational_contract_present = isinstance(catalog_operational, Mapping)
    operational_rows: list[Mapping[str, Any]] = []
    if operational_contract_present:
        operational_schema = str(catalog_operational.get("schema") or "")
        if operational_schema != PREFUSION_OPERATIONAL_RANKING_SCHEMA:
            issues.append("prefusion_registry_operational_ranking_schema_invalid")
        weights = catalog_operational.get("weights")
        if not isinstance(weights, Mapping) or stable_json(dict(weights)) != stable_json(
            PREFUSION_OPERATIONAL_RANKING_WEIGHTS
        ):
            issues.append("prefusion_registry_operational_ranking_weights_invalid")
        if catalog_operational.get("available_only") is not True:
            issues.append("prefusion_registry_operational_ranking_scope_invalid")
        if catalog_operational.get("control_plane_only") is not True:
            issues.append("prefusion_registry_operational_ranking_control_flag_invalid")
        raw_operational_rows = catalog_operational.get("ordered_models")
        if isinstance(raw_operational_rows, list):
            operational_rows = [
                row for row in raw_operational_rows if isinstance(row, Mapping)
            ]
        if len(operational_rows) != len(logical):
            issues.append("prefusion_registry_operational_ranking_count_invalid")

        operational_ranks: list[int] = []
        operational_ids: set[str] = set()
        operational_canonicals: set[str] = set()
        research_by_candidate = {
            str(row.get("candidate_id") or ""): row
            for row in research_rows
            if isinstance(row, Mapping)
        }
        logical_by_canonical = {
            _normalized_prefusion_identity(row.get("canonical_model_id")): row
            for row in logical
            if isinstance(row, Mapping)
        }
        for row in operational_rows:
            try:
                operational_rank = int(row.get("operational_rank"))
                available_rank = int(row.get("available_rank"))
                research_rank = int(row.get("research_prior_rank"))
                replica_count = int(row.get("replica_count"))
            except (TypeError, ValueError):
                issues.append("prefusion_registry_operational_ranking_row_invalid")
                continue
            candidate_id = str(row.get("candidate_id") or "")
            canonical = _normalized_prefusion_identity(row.get("canonical_model_id"))
            hashes = row.get("eligible_replica_profile_id_sha256s")
            hashes = (
                [str(value or "").strip().lower() for value in hashes]
                if isinstance(hashes, list)
                else []
            )
            operational_ranks.append(operational_rank)
            if not candidate_id or candidate_id in operational_ids:
                issues.append("prefusion_registry_operational_ranking_identity_invalid")
            operational_ids.add(candidate_id)
            if not canonical or canonical in operational_canonicals:
                issues.append("prefusion_registry_operational_ranking_canonical_duplicate")
            operational_canonicals.add(canonical)
            if (
                operational_rank < 1
                or available_rank != operational_rank
                or research_rank < 1
                or replica_count != len(hashes)
                or len(hashes) != len(set(hashes))
                or not all(is_sha256_digest(value) for value in hashes)
                or not set(hashes).issubset(model_hashes)
            ):
                issues.append("prefusion_registry_operational_ranking_projection_invalid")
            research_row = research_by_candidate.get(candidate_id)
            logical_row = logical_by_canonical.get(canonical)
            if not research_row or not logical_row:
                issues.append("prefusion_registry_operational_ranking_binding_invalid")
                continue
            if _normalized_prefusion_identity(
                research_row.get("canonical_model_id")
            ) != canonical:
                issues.append("prefusion_registry_operational_ranking_research_identity_mismatch")
            research_capability = {
                "overall": research_row.get("capability_overall"),
                "axes": research_row.get("capability_axes"),
            }
            expected_quality = research_quality_score(research_capability)
            observed_quality = row.get("research_quality_score")
            if not _prefusion_float_matches(observed_quality, expected_quality):
                issues.append("prefusion_registry_operational_research_quality_mismatch")
            expected_score = operational_score(
                research_quality=observed_quality,
                research_confidence=row.get(
                    "confidence", row.get("research_confidence")
                ),
                stream_reliability=row.get("stream_reliability_score"),
                latency=row.get("latency_score"),
            )
            if not _prefusion_float_matches(row.get("operational_score"), expected_score):
                issues.append("prefusion_registry_operational_score_mismatch")
            logical_hashes = {
                str(value or "").strip().lower()
                for value in logical_row.get("replica_profile_id_sha256s", [])
            }
            if set(hashes) != logical_hashes:
                issues.append("prefusion_registry_operational_replica_mismatch")
            for field in (
                "operational_rank",
                "available_rank",
                "research_prior_rank",
            ):
                if int(row.get(field) or 0) != int(logical_row.get(field) or 0):
                    issues.append("prefusion_registry_operational_logical_rank_mismatch")
            for field in (
                "research_quality_score",
                "stream_reliability_score",
                "latency_score",
                "operational_score",
            ):
                if not _prefusion_float_matches(
                    row.get(field), logical_row.get(field)
                ):
                    issues.append("prefusion_registry_operational_logical_score_mismatch")
        if operational_rows and operational_ranks != list(range(1, len(operational_rows) + 1)):
            issues.append("prefusion_registry_operational_ranking_not_contiguous")
        logical_canonicals = {
            _normalized_prefusion_identity(row.get("canonical_model_id"))
            for row in logical
            if isinstance(row, Mapping)
        }
        if operational_canonicals != logical_canonicals:
            issues.append("prefusion_registry_operational_ranking_logical_set_mismatch")
        if not operational_ids.issubset(ranking_ids):
            issues.append("prefusion_registry_operational_ranking_identity_mismatch")
    elif binding.get("operational_ranking_schema"):
        issues.append("prefusion_registry_operational_ranking_missing")

    return {
        "schema": "axio_fusion_api.prefusion_registry_handoff_validation.v1",
        "valid": not issues,
        "reason_codes": sorted(set(issues)),
        "require_ready": bool(require_ready),
        "binding_status": binding_status,
        "physical_profile_count": len(models),
        "logical_model_count": len(logical),
        "probe_binding_count": len(rows),
        "ranking_candidate_count": len(catalog_rows),
        "operational_ranking_present": operational_contract_present,
        "operational_ranking_candidate_count": len(operational_rows),
        "latency_ceiling_ms": 90_000,
        "strict_streaming_evidence_required": True,
        "ranking_prior_only": True,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def _prefusion_role_result_is_available(
    row: Mapping[str, Any],
    *,
    required_sample_count: int | None = None,
) -> bool:
    """Validate the persisted hash-safe result of one operational role probe."""

    if str(row.get("status") or "").strip().casefold() != "available":
        return False
    if row.get("role_output_contract_valid") is not True:
        return False
    if row.get("role_streaming_contract_valid") is not True:
        return False
    if row.get("stream_requested") is not True:
        return False
    if row.get("strict_streaming_requested") is not True:
        return False
    if row.get("stream_observed") is not True:
        return False
    if row.get("stream_fallback_used") is True:
        return False
    if str(row.get("stream_protocol") or "").strip().casefold() not in {
        "sse",
        "ndjson",
    }:
        return False
    if not is_sha256_digest(row.get("output_sha256")):
        return False
    try:
        frame_count = int(row.get("stream_frame_count") or 0)
        latency_ms = float(row.get("latency_ms") or 0.0)
    except (TypeError, ValueError):
        return False
    if frame_count < 1 or not 0.0 <= latency_ms <= 90_000.0:
        return False
    # Older role receipts have no repeated-sample fields. Preserve their
    # validation contract unless the current role-calibration contract is
    # explicitly requested by the caller.
    try:
        sample_count = int(row.get("role_probe_sample_count") or 0)
        completed_count = int(row.get("role_probe_completed_sample_count") or 0)
        success_count = int(row.get("role_probe_success_count") or 0)
        failure_count = int(row.get("role_probe_failure_count") or 0)
    except (TypeError, ValueError):
        return False
    if required_sample_count is not None:
        if (
            required_sample_count < 2
            or sample_count != required_sample_count
            or completed_count != required_sample_count
            or success_count != required_sample_count
            or failure_count != 0
            or row.get("role_probe_all_samples_eligible") is not True
            or not is_sha256_digest(row.get("role_probe_sample_receipts_sha256"))
        ):
            return False
        for quantile_key in ("p50_latency_ms", "p95_latency_ms"):
            if quantile_key not in row:
                return False
            try:
                quantile_value = float(row.get(quantile_key))
            except (TypeError, ValueError):
                return False
            if not 0.0 <= quantile_value <= 90_000.0:
                return False
        return True
    if sample_count > 0 and (
        completed_count != sample_count
        or success_count != sample_count
        or row.get("role_probe_all_samples_eligible") is not True
    ):
        return False
    for quantile_key in ("p50_latency_ms", "p95_latency_ms"):
        if quantile_key not in row:
            continue
        try:
            quantile_value = float(row.get(quantile_key))
        except (TypeError, ValueError):
            return False
        if not 0.0 <= quantile_value <= 90_000.0:
            return False
    return True


def _validate_prefusion_role_probe_binding(
    *,
    binding: Mapping[str, Any],
    models: Sequence[Any],
    generation_contract: Mapping[str, Any],
) -> list[str]:
    """Check role evidence, profile projections, and their content hashes."""

    issues: list[str] = []
    role_probe = binding.get("role_probe")
    role_probe = role_probe if isinstance(role_probe, Mapping) else {}
    if not role_probe:
        return ["prefusion_registry_role_probe_binding_missing"]
    if str(role_probe.get("schema") or "") != (
        "axio_fusion_api.provider_role_probe.binding.v1"
    ):
        issues.append("prefusion_registry_role_probe_schema_invalid")
    if str(role_probe.get("contract") or "") != (
        "axio_fusion_api.provider_role_probe.fixed_control_packet.v1"
    ):
        issues.append("prefusion_registry_role_probe_contract_invalid")
    requested_roles = [
        str(item)
        for item in role_probe.get("requested_roles", [])
        if str(item)
    ] if isinstance(role_probe.get("requested_roles"), list) else []
    current_role_contract = requested_roles == list(
        _PREFUSION_OPERATIONAL_ROLE_PROBE_ROLES
    )
    legacy_role_contract = requested_roles in (
        list(_PRE_ROLE_CALIBRATION_OPERATIONAL_ROLE_PROBE_ROLES),
        list(_LEGACY_OPERATIONAL_ROLE_PROBE_ROLES),
    )
    if not current_role_contract and not legacy_role_contract:
        issues.append("prefusion_registry_role_probe_roles_invalid")
    if role_probe.get("streaming_required") is not True:
        issues.append("prefusion_registry_role_probe_streaming_required_invalid")
    if int(role_probe.get("latency_ceiling_ms") or 0) != 90_000:
        issues.append("prefusion_registry_role_probe_latency_ceiling_invalid")

    required_role_sample_count: int | None = None
    if current_role_contract:
        try:
            required_role_sample_count = int(role_probe.get("samples_per_role"))
        except (TypeError, ValueError):
            required_role_sample_count = 0
        if (
            required_role_sample_count < 2
            or required_role_sample_count > 5
            or role_probe.get("requires_all_samples_success") is not True
            or role_probe.get(
                "requires_each_sample_latency_at_or_below_90_seconds"
            )
            is not True
            or role_probe.get("requires_each_sample_strict_streaming") is not True
        ):
            issues.append("prefusion_registry_role_probe_stability_contract_invalid")

    profile_receipts = role_probe.get("profile_receipts")
    profile_receipts = profile_receipts if isinstance(profile_receipts, list) else []
    if int(role_probe.get("profile_count") or 0) != len(profile_receipts):
        issues.append("prefusion_registry_role_probe_profile_count_invalid")
    expected_top_digest = str(role_probe.get("probe_receipt_sha256") or "").lower()
    if not is_sha256_digest(expected_top_digest) or expected_top_digest != sha256_text(
        stable_json(profile_receipts)
    ).lower():
        issues.append("prefusion_registry_role_probe_digest_invalid")
    expected_binding_digest = str(
        binding.get("role_probe_content_sha256") or ""
    ).lower()
    expected_generation_digest = str(
        generation_contract.get("role_probe_content_sha256") or ""
    ).lower()
    # The digest is over the canonical JSON, not over its hexadecimal text.
    actual_role_probe_digest = sha256_text(stable_json(dict(role_probe))).lower()
    if expected_binding_digest != actual_role_probe_digest:
        issues.append("prefusion_registry_role_probe_binding_digest_mismatch")
    if expected_generation_digest != actual_role_probe_digest:
        issues.append("prefusion_registry_role_probe_generation_digest_mismatch")

    model_by_hash: dict[str, Mapping[str, Any]] = {}
    for model in models:
        if not isinstance(model, Mapping):
            continue
        profile_id = str(model.get("profile_id") or "")
        if profile_id:
            model_by_hash[sha256_text(profile_id).lower()] = model
    receipt_by_hash: dict[str, Mapping[str, Any]] = {}
    for receipt in profile_receipts:
        if not isinstance(receipt, Mapping):
            issues.append("prefusion_registry_role_probe_receipt_invalid")
            continue
        profile_hash = str(receipt.get("profile_id_sha256") or "").lower()
        if not is_sha256_digest(profile_hash) or profile_hash in receipt_by_hash:
            issues.append("prefusion_registry_role_probe_profile_hash_invalid")
            continue
        receipt_by_hash[profile_hash] = receipt
        results = receipt.get("probe_results")
        results = results if isinstance(results, list) else []
        if str(receipt.get("probe_receipt_sha256") or "").lower() != sha256_text(
            stable_json(results)
        ).lower():
            issues.append("prefusion_registry_role_probe_profile_digest_invalid")
        result_roles = [
            str(row.get("role") or "")
            for row in results
            if isinstance(row, Mapping) and str(row.get("role") or "")
        ]
        if len(result_roles) != len(set(result_roles)) or not set(result_roles).issubset(
            set(requested_roles)
        ):
            issues.append("prefusion_registry_role_probe_result_roles_invalid")
        passed = sorted(
            role
            for role in result_roles
            if any(
                isinstance(row, Mapping)
                and str(row.get("role") or "") == role
                and _prefusion_role_result_is_available(
                    row,
                    required_sample_count=required_role_sample_count,
                )
                for row in results
            )
        )
        tested = sorted(set(result_roles))
        failed = sorted(set(tested).difference(passed))
        target = sorted(
            str(role)
            for role in receipt.get("target_roles", [])
            if str(role)
        ) if isinstance(receipt.get("target_roles"), list) else []
        missing = sorted(set(target).difference(tested))
        for key, expected in (
            ("tested_roles", tested),
            ("passed_roles", passed),
            ("failed_roles", failed),
            ("missing_roles", missing),
        ):
            observed = sorted(
                str(role)
                for role in receipt.get(key, [])
                if str(role)
            ) if isinstance(receipt.get(key), list) else []
            if observed != expected:
                issues.append(f"prefusion_registry_role_probe_{key}_mismatch")
        if int(receipt.get("probe_count") or 0) != len(results):
            issues.append("prefusion_registry_role_probe_count_invalid")
        if int(receipt.get("available_probe_count") or 0) != len(passed):
            issues.append("prefusion_registry_role_probe_available_count_invalid")
        if int(receipt.get("failed_probe_count") or 0) != len(failed):
            issues.append("prefusion_registry_role_probe_failed_count_invalid")
        streaming_verified = bool(
            results
            and all(
                _prefusion_role_result_is_available(
                    row,
                    required_sample_count=required_role_sample_count,
                )
                for row in results
            )
        ) if results else not target
        if receipt.get("streaming_contract_verified") is not streaming_verified:
            issues.append("prefusion_registry_role_probe_streaming_projection_invalid")

        model = model_by_hash.get(profile_hash)
        if model is None:
            issues.append("prefusion_registry_role_probe_model_binding_mismatch")
            continue
        admission = model.get("screening_role_admission")
        admission = admission if isinstance(admission, Mapping) else {}
        operational = admission.get("operational_role_probe")
        operational = operational if isinstance(operational, Mapping) else {}
        if not operational:
            issues.append("prefusion_registry_role_probe_profile_admission_missing")
            continue
        if str(operational.get("probe_receipt_sha256") or "").lower() != str(
            receipt.get("probe_receipt_sha256") or ""
        ).lower():
            issues.append("prefusion_registry_role_probe_profile_admission_digest_mismatch")
        for key in (
            "requested_roles",
            "tested_roles",
            "passed_roles",
            "failed_roles",
            "missing_roles",
        ):
            observed = sorted(
                str(role)
                for role in operational.get(key, [])
                if str(role)
            ) if isinstance(operational.get(key), list) else []
            expected = sorted(
                str(role)
                for role in (
                    requested_roles
                    if key == "requested_roles"
                    else receipt.get(key, [])
                )
                if str(role)
            )
            if observed != expected:
                issues.append(
                    f"prefusion_registry_role_probe_profile_admission_{key}_mismatch"
                )
        for key, expected in (
            ("probe_count", len(results)),
            ("available_probe_count", len(passed)),
            ("failed_probe_count", len(failed)),
        ):
            if int(operational.get(key) or 0) != expected:
                issues.append(
                    f"prefusion_registry_role_probe_profile_admission_{key}_mismatch"
                )
        if operational.get("streaming_contract_verified") is not streaming_verified:
            issues.append(
                "prefusion_registry_role_probe_profile_admission_streaming_projection_mismatch"
            )
        base_allowed = {
            str(role)
            for role in admission.get("effective_allowed_roles", [])
            if str(role)
        } if isinstance(admission.get("effective_allowed_roles"), list) else set()
        base_denied = {
            str(role)
            for role in admission.get("effective_disallowed_roles", [])
            if str(role)
        } if isinstance(admission.get("effective_disallowed_roles"), list) else set()
        failed_for_policy = set(failed).union(missing)
        expected_allowed = sorted(base_allowed.difference(failed_for_policy))
        expected_denied = sorted(
            base_denied.union(failed_for_policy).difference(expected_allowed)
        )
        actual_allowed = sorted(
            str(role)
            for role in model.get("screening_allowed_roles", [])
            if str(role)
        ) if isinstance(model.get("screening_allowed_roles"), list) else []
        actual_denied = sorted(
            str(role)
            for role in model.get("screening_disallowed_roles", [])
            if str(role)
        ) if isinstance(model.get("screening_disallowed_roles"), list) else []
        if actual_allowed != expected_allowed:
            issues.append("prefusion_registry_role_probe_allowed_roles_mismatch")
        if actual_denied != expected_denied:
            issues.append("prefusion_registry_role_probe_disallowed_roles_mismatch")

    if set(receipt_by_hash) != set(model_by_hash):
        issues.append("prefusion_registry_role_probe_profile_set_mismatch")
    if int(role_probe.get("profile_count") or 0) != len(models):
        issues.append("prefusion_registry_role_probe_model_count_mismatch")
    return issues


def _normalized_prefusion_identity(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _prefusion_float_matches(observed: Any, expected: Any) -> bool:
    """Compare persisted bounded scores without relying on binary float noise."""

    try:
        left = float(observed)
        right = float(expected)
    except (TypeError, ValueError):
        return False
    if left != left or right != right:
        return False
    return abs(left - right) <= 1e-6


def _prefusion_role_coverage_projection(
    logical_rows: Sequence[Any],
) -> tuple[dict[str, Any], list[str]]:
    """Rebuild the fixed role-capacity projection from registry data.

    The screening module computes this projection before producing the
    handoff. Repeating the small calculation here makes the persisted private
    registry self-authenticating at load time and keeps physical replicas from
    inflating logical candidate counts.
    """

    available = [row for row in logical_rows if isinstance(row, Mapping)]
    issues: list[str] = []
    role_rows: list[dict[str, Any]] = []
    valid_roles = set(_PREFUSION_ROLE_NAMES)
    for row in available:
        allowed = set(_normalize_role_names(row.get("allowed_roles", ())))
        denied = set(_normalize_role_names(row.get("disallowed_roles", ())))
        if not allowed.issubset(valid_roles) or not denied.issubset(valid_roles):
            issues.append("prefusion_registry_role_name_invalid")
        if allowed.intersection(denied):
            issues.append("prefusion_registry_role_overlap")

    for role in _PREFUSION_ROLE_NAMES:
        candidates = []
        for row in available:
            allowed = set(_normalize_role_names(row.get("allowed_roles", ())))
            denied = set(_normalize_role_names(row.get("disallowed_roles", ())))
            if role in allowed and role not in denied:
                candidates.append(row)
        identity_hashes = sorted(
            {
                str(row.get("canonical_identity_sha256") or "").strip().lower()
                for row in candidates
                if is_sha256_digest(row.get("canonical_identity_sha256"))
            }
        )
        profile_count = sum(
            max(0, _safe_nonnegative_int(row.get("replica_count")))
            for row in candidates
        )
        role_rows.append(
            {
                "role": role,
                "required": role in _PREFUSION_REQUIRED_ROLES,
                "candidate_count": len(candidates),
                "profile_count": profile_count,
                "candidate_identity_sha256s": identity_hashes,
                "ready": bool(candidates),
            }
        )

    role_rows.sort(key=lambda row: str(row.get("role") or ""))
    by_role = {str(row["role"]): row for row in role_rows}
    required_ready = all(
        bool(by_role[role]["ready"]) for role in _PREFUSION_REQUIRED_ROLES
    )
    solver_ready = bool(
        by_role["primary_solver"]["ready"]
        or by_role["independent_solver"]["ready"]
    )
    warnings = sorted(
        f"missing_{role}_candidate"
        for role in _PREFUSION_REQUIRED_ROLES
        if not by_role[role]["ready"]
    )
    coverage = {
        "schema": "axio_fusion_api.prefusion_role_coverage.v1",
        "available_logical_model_count": len(available),
        "available_physical_profile_count": sum(
            max(0, _safe_nonnegative_int(row.get("replica_count")))
            for row in available
        ),
        "roles": role_rows,
        "required_roles": list(_PREFUSION_REQUIRED_ROLES),
        "required_roles_ready": required_ready,
        "serving_ready": solver_ready,
        "fusion_role_coverage_complete": required_ready,
        "status": (
            "ready"
            if required_ready
            else "ready_with_warnings"
            if solver_ready
            else "blocked"
        ),
        "warnings": warnings,
        "role_coverage_is_capability_admission_diagnostic": True,
        "ranking_prior_only": True,
        "ranking_prior_forbidden_for_final_benchmark_claims": True,
        "raw_research_prompt_persisted": False,
        "raw_research_output_persisted": False,
        "secrets_persisted": False,
    }
    return coverage, sorted(set(issues))


def _safe_nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _prefusion_model_catalog_matches_binding(
    *,
    catalog: Mapping[str, Any],
    binding: Mapping[str, Any],
    models: Sequence[Any],
) -> bool:
    """Require the fixed pre-Fusion catalog to bind the serving projection."""

    if str(catalog.get("schema") or "") != "axio_fusion_api.prefusion_model_catalog.v1":
        return False
    if str(catalog.get("status") or "").strip().casefold() != "ready":
        return False
    inventory = catalog.get("inventory")
    if not isinstance(inventory, Mapping):
        return False
    if inventory.get("complete") is not True or inventory.get("ranking_complete") is not True:
        return False
    available = catalog.get("available_model_list")
    bound_available = binding.get("available_model_list")
    if not isinstance(available, list) or not isinstance(bound_available, list):
        return False
    if stable_json(available) != stable_json(bound_available):
        return False
    try:
        if int(inventory.get("available_logical_model_count") or 0) != len(available):
            return False
        if int(inventory.get("available_physical_profile_count") or 0) != len(models):
            return False
        if int(inventory.get("logical_candidate_count") or 0) != int(
            inventory.get("ranked_logical_model_count") or 0
        ):
            return False
    except (TypeError, ValueError):
        return False
    expected_hash = str(binding.get("model_catalog_content_sha256") or "").strip().lower()
    if not is_sha256_digest(expected_hash):
        return False
    # The registry builder stores the same compact catalog projection in the
    # top-level binding and uses its digest as the immutable handoff anchor.
    if expected_hash != sha256_text(stable_json(dict(catalog))).lower():
        return False
    return True


def _prefusion_logical_projection_matches_models(
    logical_rows: Any,
    models: Sequence[Any],
) -> bool:
    """Ensure the private logical handoff still describes every bound profile."""

    if not isinstance(logical_rows, list) or not logical_rows:
        return False
    expected: dict[str, set[str]] = {}
    for model in models:
        if not isinstance(model, Mapping):
            return False
        canonical = " ".join(
            str(model.get("canonical_model_id") or model.get("model") or "")
            .strip()
            .casefold()
            .split()
        )
        profile_id = str(model.get("profile_id") or "")
        if not canonical or not profile_id:
            return False
        expected.setdefault(canonical, set()).add(sha256_text(profile_id).lower())

    observed: dict[str, set[str]] = {}
    for row in logical_rows:
        if not isinstance(row, Mapping):
            return False
        canonical = " ".join(
            str(row.get("canonical_model_id") or "").strip().casefold().split()
        )
        hashes = row.get("replica_profile_id_sha256s")
        if not canonical or canonical in observed or not isinstance(hashes, list):
            return False
        normalized_hashes = [str(value or "").strip().lower() for value in hashes]
        try:
            replica_count = int(row.get("replica_count"))
            rank = int(row.get("rank"))
        except (TypeError, ValueError):
            return False
        if (
            not normalized_hashes
            or len(normalized_hashes) != len(set(normalized_hashes))
            or not all(is_sha256_digest(value) for value in normalized_hashes)
            or replica_count != len(normalized_hashes)
            or rank < 1
        ):
            return False
        observed[canonical] = set(normalized_hashes)
    return observed == expected


def _provider_configuration_is_present() -> bool:
    """Return whether a custom provider source was explicitly supplied.

    This deliberately checks presence rather than validity.  A malformed or
    unavailable manifest must block the custom deployment instead of silently
    activating the portable development seed.
    """

    return any(bool(row.get("present")) for row in _provider_config_source_rows())


def _load_json_files(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        selected = Path(path)
        if not selected.exists():
            continue
        try:
            payload = json.loads(selected.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def _probe_rows_from_payloads(payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for payload in payloads:
        top_mode = str(payload.get("mode") or "unknown")
        if isinstance(payload.get("probes"), list):
            for row in payload["probes"]:
                if isinstance(row, dict):
                    rows.append(_probe_row_with_mode(row, top_mode))
        probe_report = payload.get("probe_report") if isinstance(payload.get("probe_report"), Mapping) else {}
        report_mode = str(probe_report.get("mode") or top_mode or "unknown")
        if isinstance(probe_report.get("probes"), list):
            for row in probe_report["probes"]:
                if isinstance(row, dict):
                    rows.append(_probe_row_with_mode(row, report_mode))
    return rows


def _probe_row_with_mode(row: Mapping[str, Any], mode: str) -> dict[str, Any]:
    copied = dict(row)
    copied.setdefault("probe_mode", str(mode or "unknown"))
    copied.setdefault("live_probe_evidence", str(copied.get("probe_mode") or "") == "live")
    return copied


def _row_has_live_probe_evidence(row: Mapping[str, Any]) -> bool:
    if row.get("live_probe_evidence") is True:
        return True
    return str(row.get("probe_mode") or row.get("mode") or "").strip().lower() == "live"


def _models_from_env() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider, env_name, api_format, base_env, key_env in [
        ("nvidia", "AXIO_NVIDIA_MODELS", "chat", "AXIO_NVIDIA_BASE_URL", "AXIO_NVIDIA_API_KEYS"),
        ("cpa-plus", "AXIO_CPA_PLUS_MODELS", "responses", "AXIO_CPA_PLUS_BASE_URL", "AXIO_CPA_PLUS_API_KEY"),
        ("aisz", "AXIO_AISZ_MODELS", "responses", "AXIO_AISZ_BASE_URL", "AXIO_AISZ_API_KEY"),
        ("tokenapis", "AXIO_TOKENAPIS_MODELS", "responses", "AXIO_TOKENAPIS_BASE_URL", "AXIO_TOKENAPIS_API_KEY"),
        ("anthropic-compatible", "AXIO_ANTHROPIC_MODELS", "anthropic", "AXIO_ANTHROPIC_BASE_URL", "AXIO_ANTHROPIC_API_KEY"),
        ("openai-compatible", "AXIO_OPENAI_COMPAT_MODELS", "chat", "AXIO_OPENAI_COMPAT_BASE_URL", "AXIO_OPENAI_COMPAT_API_KEY"),
        ("gemini-compatible", "AXIO_GEMINI_MODELS", "gemini", "AXIO_GEMINI_BASE_URL", "AXIO_GEMINI_API_KEY"),
    ]:
        for model in _split_env_list(os.getenv(env_name, "")):
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "api_format": api_format,
                    "base_url_env": base_env,
                    "api_key_env": key_env,
                    "auth_scheme": _default_auth_scheme(provider, api_format),
                    "source": "environment",
                }
            )
    rows.extend(_custom_provider_models_from_env())
    return rows


def provider_seed_profiles_from_env(provider_names: Sequence[str] | None = None) -> list[ModelProfile]:
    selected = {
        _provider_slug(str(provider))
        for provider in provider_names or []
        if str(provider).strip()
    }
    profiles = []
    for config in _provider_configs_from_env():
        provider = str(config.get("provider") or "").strip()
        if not provider:
            continue
        if selected and _provider_slug(provider) not in selected:
            continue
        if not _provider_config_can_discover_models(config):
            continue
        profiles.append(
            normalize_profile(
                {
                    "provider": provider,
                    "model": "probe-seed",
                    "api_format": _normalize_api_format_name(config.get("api_format") or config.get("api_mode")),
                    "base_url_env": str(config.get("base_url_env") or ""),
                    "api_key_env": str(config.get("api_key_env") or ""),
                    "auth_scheme": config.get("auth_scheme"),
        "max_output_tokens_parameter": config.get(
            "max_output_tokens_parameter",
            config.get("maxOutputTokensParameter", "max_tokens"),
        ),
                    "models_endpoint": config.get("models_endpoint", "/models"),
                    "discover_models": config.get("discover_models", True),
                    "input_cost_per_million": config.get("input_cost_per_million"),
                    "output_cost_per_million": config.get("output_cost_per_million"),
                    "p50_latency_ms": config.get("p50_latency_ms"),
                    "p95_latency_ms": config.get("p95_latency_ms"),
                    "context_tokens": config.get("context_tokens"),
                    "supports_tools": config.get("supports_tools", False),
                    "supports_vision": config.get("supports_vision", False),
                    "model_kind": config.get("model_kind", config.get("modelKind", "text")),
                    "image_capabilities": config.get("image_capabilities", config.get("imageCapabilities", {})),
                    "image_probe_status": config.get("image_probe_status", config.get("imageProbeStatus", "not_run")),
                    "reasoning_transport": (
                        dict(config.get("reasoning_transport"))
                        if isinstance(config.get("reasoning_transport"), Mapping)
                        else {}
                    ),
                    "traffic_control": (
                        dict(config.get("traffic_control"))
                        if isinstance(config.get("traffic_control"), Mapping)
                        else (
                            dict(config.get("trafficControl"))
                            if isinstance(config.get("trafficControl"), Mapping)
                            else {}
                        )
                    ),
                    "privacy_tags": config.get("privacy_tags", ["external_provider"]),
                    "source": "environment_provider_config",
                }
            )
        )
    return profiles


def provider_configured_profiles_from_env(
    provider_names: Sequence[str] | None = None,
) -> list[ModelProfile]:
    """Return the explicitly configured models for arbitrary provider channels.

    This is intentionally distinct from :func:`provider_seed_profiles_from_env`.
    A provider-level seed represents one endpoint that can enumerate ``/models``;
    a configured model can instead carry its own endpoint, credential, and
    transport.  The latter must remain usable and probeable even though no
    provider-level discovery request is possible.
    """

    selected = {
        _provider_slug(str(provider))
        for provider in provider_names or []
        if str(provider).strip()
    }
    rows: list[dict[str, Any]] = []
    for config in _provider_configs_from_env():
        provider = str(config.get("provider") or "").strip()
        if not provider or (selected and _provider_slug(provider) not in selected):
            continue
        rows.extend(_custom_provider_models_from_config(config))
    return _dedupe_profiles([normalize_profile(row) for row in rows])


def provider_discovery_priors_from_env(provider_names: Sequence[str] | None = None) -> dict[str, dict[str, Any]]:
    selected = {
        _provider_slug(str(provider))
        for provider in provider_names or []
        if str(provider).strip()
    }
    priors: dict[str, dict[str, Any]] = {}
    for config in _provider_configs_from_env():
        provider = str(config.get("provider") or "").strip()
        if not provider:
            continue
        slug = _provider_slug(provider)
        if selected and slug not in selected:
            continue
        model_priors = _discovery_model_priors_for_config(config)
        priors[slug] = {
            "provider": provider,
            "api_format": _normalize_api_format_name(config.get("api_format") or config.get("api_mode")),
            "base_url_env": str(config.get("base_url_env") or "").strip(),
            "api_key_env": str(config.get("api_key_env") or "").strip(),
            "auth_scheme": config.get("auth_scheme"),
            "max_output_tokens_parameter": config.get(
                "max_output_tokens_parameter",
                config.get("maxOutputTokensParameter", "max_tokens"),
            ),
            "models_endpoint": config.get("models_endpoint", "/models"),
            "discover_models": config.get("discover_models", True),
            "capabilities": config.get("capabilities", {}),
            "input_cost_per_million": config.get("input_cost_per_million"),
            "output_cost_per_million": config.get("output_cost_per_million"),
            "p50_latency_ms": config.get("p50_latency_ms"),
            "p95_latency_ms": config.get("p95_latency_ms"),
            "context_tokens": config.get("context_tokens"),
            "supports_tools": config.get("supports_tools", False),
            "supports_vision": config.get("supports_vision", False),
            "model_kind": config.get("model_kind", config.get("modelKind", "text")),
            "image_capabilities": config.get("image_capabilities", config.get("imageCapabilities", {})),
            "image_probe_status": config.get("image_probe_status", config.get("imageProbeStatus", "not_run")),
            "reasoning_transport": (
                dict(config.get("reasoning_transport"))
                if isinstance(config.get("reasoning_transport"), Mapping)
                else {}
            ),
            "traffic_control": (
                dict(config.get("traffic_control"))
                if isinstance(config.get("traffic_control"), Mapping)
                else (
                    dict(config.get("trafficControl"))
                    if isinstance(config.get("trafficControl"), Mapping)
                    else {}
                )
            ),
            "privacy_tags": config.get("privacy_tags", ["external_provider"]),
            "model_priors": model_priors,
            "model_prior_count": len(model_priors),
            "source": "environment_provider_config",
        }
    return priors


def _custom_provider_models_from_env() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for config in _provider_configs_from_env():
        rows.extend(_custom_provider_models_from_config(config))
    return rows


def _custom_provider_models_from_config(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    provider = str(config.get("provider") or "").strip()
    if not provider:
        return []
    api_format = _normalize_api_format_name(config.get("api_format") or config.get("api_mode"))
    base_env = str(config.get("base_url_env") or "").strip()
    key_env = str(config.get("api_key_env") or "").strip()
    models_endpoint = str(
        config.get("models_endpoint")
        or config.get("modelsEndpoint")
        or config.get("model_list_endpoint")
        or config.get("modelListEndpoint")
        or "/models"
    ).strip()
    discover_models = config.get("discover_models", config.get("discoverModels", True))
    rows: list[dict[str, Any]] = []
    for model_config in _config_model_rows(config):
        model = str(model_config.get("model") or "").strip()
        if not model:
            continue
        model_api_format = _normalize_api_format_name(
            model_config.get("api_format") or model_config.get("api_mode") or api_format
        )
        model_base_env = str(model_config.get("base_url_env") or base_env).strip()
        model_key_env = str(model_config.get("api_key_env") or key_env).strip()
        canonical_model_id = _model_config_value(
            config,
            model_config,
            "canonical_model_id",
            default=model,
        ) or model
        rows.append(
            {
                "provider": provider,
                "model": model,
                "api_format": model_api_format,
                "base_url_env": model_base_env,
                "api_key_env": model_key_env,
                "auth_scheme": str(
                    model_config.get("auth_scheme")
                    or config.get("auth_scheme")
                    or _default_auth_scheme(provider, model_api_format)
                ),
                "max_output_tokens_parameter": _model_config_value(
                    config,
                    model_config,
                    "max_output_tokens_parameter",
                    default="max_tokens",
                ),
                "models_endpoint": _model_config_value(
                    config,
                    model_config,
                    "models_endpoint",
                    default=models_endpoint,
                ),
                "discover_models": _model_config_value(
                    config,
                    model_config,
                    "discover_models",
                    default=discover_models,
                ),
                "canonical_model_id": canonical_model_id,
                "capabilities": _merged_model_capabilities(config, model_config),
                "input_cost_per_million": _model_config_value(config, model_config, "input_cost_per_million"),
                "output_cost_per_million": _model_config_value(config, model_config, "output_cost_per_million"),
                "p50_latency_ms": _model_config_value(config, model_config, "p50_latency_ms"),
                "p95_latency_ms": _model_config_value(config, model_config, "p95_latency_ms"),
                "context_tokens": _model_config_value(config, model_config, "context_tokens"),
                "supports_tools": _model_config_value(config, model_config, "supports_tools", default=False),
                "supports_vision": _model_config_value(config, model_config, "supports_vision", default=False),
                "model_kind": _model_config_value(config, model_config, "model_kind", default="text"),
                "image_capabilities": _model_config_value(config, model_config, "image_capabilities", default={}),
                "image_probe_status": _model_config_value(config, model_config, "image_probe_status", default="not_run"),
                "reasoning_transport": _model_config_value(
                    config,
                    model_config,
                    "reasoning_transport",
                    default={},
                ),
                "traffic_control": _model_config_value(
                    config,
                    model_config,
                    "traffic_control",
                    default={},
                ),
                "privacy_tags": _model_config_value(config, model_config, "privacy_tags", default=["external_provider"]),
                "source": "environment_provider_config",
            }
        )
    return rows


def _provider_configs_from_env() -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    # File-backed configuration is loaded first so a deployment may keep a
    # versioned, non-secret channel manifest while an inline environment value
    # can still provide an emergency, process-local override for the same
    # provider/model profile.
    for source in _provider_config_source_rows():
        for item in source["provider_rows"]:
            if isinstance(item, Mapping):
                sanitized = _sanitize_provider_config(item)
                if sanitized:
                    configs.append(sanitized)
    return configs


def provider_configuration_source_summary() -> dict[str, Any]:
    """Return a hash-safe summary of provider configuration sources.

    A provider portfolio can be supplied inline for ephemeral environments or
    through ``AXIO_FUSION_PROVIDER_CONFIG_FILE`` for normal deployment.  The
    configuration itself is private because it contains channel and model
    aliases, so this summary intentionally exposes only source type, validity,
    and counts.  It never returns a filesystem path, environment variable name,
    provider label, model alias, URL, or credential value.
    """

    rows = _provider_config_source_rows()
    safe_rows = [
        {
            "source_kind": str(row["source_kind"]),
            "env_name_sha256": sha256_text(str(row["env_name"])),
            "present": bool(row["present"]),
            "valid_json": bool(row["valid_json"]),
            "provider_config_count": int(row["provider_config_count"]),
            "invalid_provider_config_count": int(row.get("invalid_provider_config_count") or 0),
            "reason_code": str(row["reason_code"]),
            "raw_env_name_persisted": False,
            "raw_file_path_persisted": False,
            "raw_env_value_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "secrets_persisted": False,
        }
        for row in rows
    ]
    inline_rows = [row for row in rows if row["source_kind"] == "inline_env"]
    file_rows = [row for row in rows if row["source_kind"] == "config_file"]
    return {
        "schema": "axio_fusion_api.provider_config_env_summary.v1",
        "config_env_present": any(row["present"] for row in inline_rows),
        "config_file_present": any(row["present"] for row in file_rows),
        "config_source_present": any(row["present"] for row in rows),
        "valid_config_env_count": sum(1 for row in inline_rows if row["valid_json"]),
        "valid_config_file_count": sum(1 for row in file_rows if row["valid_json"]),
        "valid_config_source_count": sum(1 for row in rows if row["valid_json"]),
        "provider_config_count": sum(int(row["provider_config_count"]) for row in rows),
        "invalid_provider_config_count": sum(
            int(row.get("invalid_provider_config_count") or 0) for row in rows
        ),
        "rows": safe_rows,
        "raw_env_names_persisted": False,
        "raw_file_paths_persisted": False,
        "raw_env_values_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _provider_config_source_rows() -> list[dict[str, Any]]:
    """Load private provider-config inputs while keeping source details local."""

    rows = [_provider_config_file_source_row()]
    rows.extend(_provider_config_inline_source_row(env_name) for env_name in _PROVIDER_CONFIG_INLINE_ENV_NAMES)
    return rows


def _provider_config_file_source_row() -> dict[str, Any]:
    configured_path = os.getenv(_PROVIDER_CONFIG_FILE_ENV_NAME, "").strip()
    result: dict[str, Any] = {
        "source_kind": "config_file",
        "env_name": _PROVIDER_CONFIG_FILE_ENV_NAME,
        "present": bool(configured_path),
        "valid_json": False,
        "provider_config_count": 0,
        "invalid_provider_config_count": 0,
        "reason_code": "config_file_not_configured",
        "provider_rows": [],
    }
    if not configured_path:
        return result
    try:
        selected = Path(configured_path).expanduser()
        if not selected.is_file():
            result["reason_code"] = "config_file_unavailable"
            return result
        if selected.stat().st_size > _PROVIDER_CONFIG_MAX_FILE_BYTES:
            result["reason_code"] = "config_file_too_large"
            return result
        raw = selected.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        result["reason_code"] = "config_file_unreadable"
        return result
    return _provider_config_source_row_from_json(
        source_kind="config_file",
        env_name=_PROVIDER_CONFIG_FILE_ENV_NAME,
        present=True,
        raw=raw,
        empty_reason="config_file_empty",
    )


def _provider_config_inline_source_row(env_name: str) -> dict[str, Any]:
    raw = os.getenv(env_name, "").strip()
    return _provider_config_source_row_from_json(
        source_kind="inline_env",
        env_name=env_name,
        present=bool(raw),
        raw=raw,
        empty_reason="config_env_not_configured",
    )


def _provider_config_source_row_from_json(
    *,
    source_kind: str,
    env_name: str,
    present: bool,
    raw: str,
    empty_reason: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_kind": source_kind,
        "env_name": env_name,
        "present": bool(present),
        "valid_json": False,
        "provider_config_count": 0,
        "invalid_provider_config_count": 0,
        "reason_code": empty_reason,
        "provider_rows": [],
    }
    if not present:
        return result
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        result["reason_code"] = "config_json_invalid"
        return result
    provider_rows = _provider_config_rows_from_payload(parsed)
    if provider_rows is None:
        result["reason_code"] = "config_root_invalid"
        return result
    sanitized_rows = [
        _sanitize_provider_config(item)
        for item in provider_rows
        if isinstance(item, Mapping)
    ]
    valid_provider_rows = [row for row in sanitized_rows if row]
    invalid_provider_count = max(0, len(provider_rows) - len(valid_provider_rows))
    result.update(
        {
            "valid_json": True,
            "provider_config_count": len(valid_provider_rows),
            "invalid_provider_config_count": invalid_provider_count,
            "reason_code": "provider_config_rows_rejected" if invalid_provider_count else "",
            "provider_rows": provider_rows,
        }
    )
    return result


def _provider_config_rows_from_payload(payload: Any) -> list[Any] | None:
    """Return every declared provider row so malformed entries are observable.

    Filtering non-mapping values here made a manifest appear valid while
    silently dropping one of its channels.  The caller deliberately keeps the
    raw rows private and counts rejected entries before creating profiles.
    """

    if isinstance(payload, Mapping):
        candidate_rows = payload.get("providers") if isinstance(payload.get("providers"), list) else [payload]
    elif isinstance(payload, list):
        candidate_rows = payload
    else:
        return None
    return list(candidate_rows)


def _sanitize_provider_config(config: Mapping[str, Any]) -> dict[str, Any]:
    provider = str(config.get("provider") or config.get("name") or "").strip()
    base_env = str(config.get("base_url_env") or config.get("baseUrlEnv") or "").strip()
    key_env = str(config.get("api_key_env") or config.get("apiKeyEnv") or "").strip()
    raw_api_format = config.get("api_format") or config.get("apiFormat") or config.get("api_mode")
    api_format = _configured_api_format(raw_api_format, provider=provider)
    if api_format is None:
        return {}
    provider_auth_scheme = _normalize_auth_scheme(
        config.get("auth_scheme")
        or config.get("authScheme")
        or _default_auth_scheme(provider, api_format)
    )
    canonical_model_id = str(
        config.get("canonical_model_id")
        or config.get("canonicalModelId")
        or config.get("canonical_model")
        or config.get("canonicalModel")
        or config.get("canonical_identity")
        or config.get("canonicalIdentity")
        or ""
    ).strip()
    model_rows = _split_config_model_rows(config.get("models"))
    models_env = str(config.get("models_env") or config.get("modelsEnv") or "").strip()
    for row in model_rows:
        raw_model_api_format = (
            row.get("api_format")
            or row.get("apiFormat")
            or row.get("api_mode")
        )
        if _configured_api_format(
            raw_model_api_format,
            provider=provider,
            fallback=api_format,
        ) is None:
            return {}
    environment_names = [base_env, key_env, models_env]
    for row in model_rows:
        environment_names.extend(
            [
                str(row.get("base_url_env") or row.get("baseUrlEnv") or "").strip(),
                str(row.get("api_key_env") or row.get("apiKeyEnv") or "").strip(),
            ]
        )
    # The schema accepts names of environment variables, never literal base
    # URLs or credentials.  Reject malformed names before any profile is
    # created so an accidental secret-bearing config cannot become a hidden
    # alternate configuration path.
    if any(name and not _is_environment_variable_name(name) for name in environment_names):
        return {}
    has_provider_credentials = bool(base_env) and (
        provider_auth_scheme == "none" or bool(key_env)
    )
    has_complete_model_credentials = bool(model_rows) and all(
        str(row.get("base_url_env") or row.get("baseUrlEnv") or base_env).strip()
        and (
            _normalize_auth_scheme(
                row.get("auth_scheme")
                or row.get("authScheme")
                or config.get("auth_scheme")
                or config.get("authScheme")
                or _default_auth_scheme(
                    provider,
                    _configured_api_format(
                        row.get("api_format")
                        or row.get("apiFormat")
                        or row.get("api_mode"),
                        provider=provider,
                        fallback=api_format,
                    )
                    or api_format,
                )
            )
            == "none"
            or str(row.get("api_key_env") or row.get("apiKeyEnv") or key_env).strip()
        )
        for row in model_rows
    )
    if not provider or not (has_provider_credentials or has_complete_model_credentials):
        return {}
    return {
        "provider": provider,
        "api_format": api_format,
        "base_url_env": base_env,
        "api_key_env": key_env,
        "auth_scheme": provider_auth_scheme,
        "models_endpoint": str(
            config.get("models_endpoint")
            or config.get("modelsEndpoint")
            or config.get("model_list_endpoint")
            or config.get("modelListEndpoint")
            or config.get("models_path")
            or config.get("modelsPath")
            or "/models"
        ).strip(),
        "discover_models": config.get("discover_models", config.get("discoverModels", True)),
        "models": config.get("models", []),
        "models_env": models_env,
        "canonical_model_id": canonical_model_id,
        "capabilities": config.get("capabilities", {}),
        "input_cost_per_million": config.get("input_cost_per_million"),
        "output_cost_per_million": config.get("output_cost_per_million"),
        "p50_latency_ms": config.get("p50_latency_ms"),
        "p95_latency_ms": config.get("p95_latency_ms"),
        "context_tokens": config.get("context_tokens"),
        "supports_tools": config.get("supports_tools", False),
        "supports_vision": config.get("supports_vision", False),
        "model_kind": config.get("model_kind", config.get("modelKind", "text")),
        "image_capabilities": (
            dict(config.get("image_capabilities"))
            if isinstance(config.get("image_capabilities"), Mapping)
            else {}
        ),
        "image_probe_status": config.get("image_probe_status", config.get("imageProbeStatus", "not_run")),
        "reasoning_transport": (
            config.get("reasoning_transport")
            if isinstance(config.get("reasoning_transport"), Mapping)
            else config.get("reasoningTransport", {})
        ),
        "traffic_control": (
            config.get("traffic_control")
            if isinstance(config.get("traffic_control"), Mapping)
            else config.get("trafficControl", {})
        ),
        "privacy_tags": config.get("privacy_tags", ["external_provider"]),
    }


def _is_environment_variable_name(value: str) -> bool:
    return bool(_ENVIRONMENT_VARIABLE_NAME_PATTERN.fullmatch(str(value or "").strip()))


def _provider_config_can_discover_models(config: Mapping[str, Any]) -> bool:
    """Return whether a provider-level `/models` request is well-defined.

    A configuration can deliberately use a different endpoint or credential
    environment variable per model.  Such a configuration is immediately
    usable by the static registry, but it has no single provider-level endpoint
    from which to enumerate unknown models.
    """

    if config.get("discover_models", True) is False:
        return False
    base_url_env = str(config.get("base_url_env") or "").strip()
    auth_scheme = _normalize_auth_scheme(
        config.get("auth_scheme")
        or _default_auth_scheme(
            str(config.get("provider") or ""),
            _normalize_api_format_name(config.get("api_format") or config.get("api_mode")),
        )
    )
    key_env = str(config.get("api_key_env") or "").strip()
    return bool(base_url_env and (auth_scheme == "none" or key_env))


def _config_model_list(config: Mapping[str, Any]) -> list[str]:
    models = [row["model"] for row in _config_model_rows(config) if row.get("model")]
    return list(dict.fromkeys(model for model in models if model))


def _config_model_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    models = _split_config_model_rows(config.get("models"))
    models_env = str(config.get("models_env") or "").strip()
    if models_env:
        models.extend({"model": model} for model in _split_env_list(os.getenv(models_env, "")))
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in models:
        model = str(row.get("model") or "").strip()
        if not model:
            continue
        if model not in deduped:
            order.append(model)
        deduped[model] = dict(row)
    return [deduped[model] for model in order]


def _split_config_model_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return [{"model": model} for model in _split_env_list(value)]
    if isinstance(value, Mapping):
        model = str(
            value.get("model")
            or value.get("model_id")
            or value.get("modelId")
            or value.get("id")
            or value.get("name")
            or ""
        ).strip()
        row = _normalize_model_config_row(value)
        if model:
            row["model"] = model
            return [row]
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rows: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                model = str(
                    item.get("model")
                    or item.get("model_id")
                    or item.get("modelId")
                    or item.get("id")
                    or item.get("name")
                    or ""
                ).strip()
                if model:
                    row = _normalize_model_config_row(item)
                    row["model"] = model
                    rows.append(row)
                continue
            model = str(item).strip()
            if model:
                rows.append({"model": model})
        return rows
    return []


def _split_config_models(value: Any) -> list[str]:
    return [row["model"] for row in _split_config_model_rows(value) if row.get("model")]


def _normalize_model_config_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    alias_pairs = {
        "apiFormat": "api_format",
        "apiMode": "api_mode",
        "baseUrlEnv": "base_url_env",
        "apiKeyEnv": "api_key_env",
        "authScheme": "auth_scheme",
        "modelsEndpoint": "models_endpoint",
        "modelListEndpoint": "model_list_endpoint",
        "modelsPath": "models_path",
        "discoverModels": "discover_models",
        "inputCostPerMillion": "input_cost_per_million",
        "outputCostPerMillion": "output_cost_per_million",
        "p50LatencyMs": "p50_latency_ms",
        "p95LatencyMs": "p95_latency_ms",
        "contextTokens": "context_tokens",
        "supportsTools": "supports_tools",
        "supportsVision": "supports_vision",
        "modelKind": "model_kind",
        "modality": "model_kind",
        "imageCapabilities": "image_capabilities",
        "imageProbeStatus": "image_probe_status",
        "privacyTags": "privacy_tags",
        "canonicalModelId": "canonical_model_id",
        "canonicalModel": "canonical_model",
        "canonicalIdentity": "canonical_identity",
        "maxOutputTokensParameter": "max_output_tokens_parameter",
        "reasoningTransport": "reasoning_transport",
        "trafficControl": "traffic_control",
    }
    for source, target in alias_pairs.items():
        if target not in result and source in result:
            result[target] = result[source]
    return result


def _discovery_model_priors_for_config(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    provider = str(config.get("provider") or "").strip()
    provider_api_format = _normalize_api_format_name(config.get("api_format") or config.get("api_mode"))
    provider_base_env = str(config.get("base_url_env") or "").strip()
    provider_key_env = str(config.get("api_key_env") or "").strip()
    rows: dict[str, dict[str, Any]] = {}
    for model_config in _config_model_rows(config):
        model = str(model_config.get("model") or "").strip()
        if not model:
            continue
        api_format = _normalize_api_format_name(model_config.get("api_format") or model_config.get("api_mode") or provider_api_format)
        rows[model] = {
            "api_format": api_format,
            "base_url_env": str(model_config.get("base_url_env") or provider_base_env).strip(),
            "api_key_env": str(model_config.get("api_key_env") or provider_key_env).strip(),
            "auth_scheme": str(
                model_config.get("auth_scheme")
                or config.get("auth_scheme")
                or _default_auth_scheme(provider, api_format)
            ),
            "max_output_tokens_parameter": _model_config_value(
                config,
                model_config,
                "max_output_tokens_parameter",
                default="max_tokens",
            ),
            "models_endpoint": _model_config_value(
                config,
                model_config,
                "models_endpoint",
                default=(
                    config.get("models_endpoint")
                    or config.get("modelsEndpoint")
                    or config.get("model_list_endpoint")
                    or config.get("modelListEndpoint")
                    or config.get("models_path")
                    or config.get("modelsPath")
                    or "/models"
                ),
            ),
            "discover_models": _model_config_value(
                config,
                model_config,
                "discover_models",
                default=config.get("discover_models", config.get("discoverModels", True)),
            ),
            "canonical_model_id": _model_config_value(
                config,
                model_config,
                "canonical_model_id",
                default="",
            ),
            "capabilities": _merged_model_capabilities(config, model_config),
            "input_cost_per_million": _model_config_value(config, model_config, "input_cost_per_million"),
            "output_cost_per_million": _model_config_value(config, model_config, "output_cost_per_million"),
            "p50_latency_ms": _model_config_value(config, model_config, "p50_latency_ms"),
            "p95_latency_ms": _model_config_value(config, model_config, "p95_latency_ms"),
            "context_tokens": _model_config_value(config, model_config, "context_tokens"),
            "supports_tools": _model_config_value(config, model_config, "supports_tools", default=False),
            "supports_vision": _model_config_value(config, model_config, "supports_vision", default=False),
            "model_kind": _model_config_value(config, model_config, "model_kind", default="text"),
            "image_capabilities": _model_config_value(config, model_config, "image_capabilities", default={}),
            "image_probe_status": _model_config_value(config, model_config, "image_probe_status", default="not_run"),
            "reasoning_transport": _model_config_value(
                config,
                model_config,
                "reasoning_transport",
                default={},
            ),
            "traffic_control": _model_config_value(
                config,
                model_config,
                "traffic_control",
                default={},
            ),
            "privacy_tags": _model_config_value(config, model_config, "privacy_tags", default=["external_provider"]),
            "source": "environment_provider_config_model_prior",
        }
    return rows


def _merged_model_capabilities(config: Mapping[str, Any], model_config: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(config.get("capabilities"), Mapping):
        merged.update(dict(config["capabilities"]))
    if isinstance(model_config.get("capabilities"), Mapping):
        merged.update(dict(model_config["capabilities"]))
    return merged


def _model_config_value(
    config: Mapping[str, Any],
    model_config: Mapping[str, Any],
    key: str,
    *,
    default: Any = None,
) -> Any:
    if key in model_config:
        return model_config.get(key)
    if key in config:
        return config.get(key)
    return default


def _normalize_api_format_name(value: Any) -> str:
    raw = str(value or "chat").strip().lower().replace("_", "-")
    normalized = _API_FORMAT_ALIASES.get(raw, raw)
    if normalized not in _SUPPORTED_PROVIDER_API_FORMATS:
        return "chat"
    return normalized


def _configured_api_format(
    value: Any,
    *,
    provider: str,
    fallback: str | None = None,
) -> str | None:
    """Resolve a manifest protocol without silently changing the wire format.

    ``normalize_profile`` keeps its legacy chat fallback for old registry rows,
    but a new provider manifest must reject a typo such as ``respones``. A
    rejected row is safer than sending credentials to the wrong endpoint.
    """

    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw:
        if fallback:
            return str(fallback)
        return _infer_api_format(provider)
    normalized = _API_FORMAT_ALIASES.get(raw)
    if normalized not in _SUPPORTED_PROVIDER_API_FORMATS:
        return None
    return normalized


def _provider_slug(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _normalize_capabilities(value: Any, *, model: str) -> dict[str, float]:
    raw = value if isinstance(value, Mapping) else {}
    caps = {axis: 0.35 for axis in CAPABILITY_AXES}
    name = model.lower()
    _apply_model_name_capability_priors(caps, name)
    for key, raw_value in raw.items():
        axis = _axis_alias(str(key))
        if axis in caps:
            number = _optional_float(raw_value)
            if number is not None:
                caps[axis] = _score01(number)
    return caps


def _normalize_screening_capability_axes(value: Any) -> dict[str, float]:
    """Normalize research-agent axes without turning them into calibration."""

    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, float] = {}
    for key, raw_value in value.items():
        axis = _axis_alias(str(key))
        if axis not in CAPABILITY_AXES:
            continue
        number = _optional_float(raw_value)
        if number is None:
            continue
        normalized[axis] = _score01(number)
    return normalized


def _apply_model_name_capability_priors(caps: dict[str, float], name: str) -> None:
    """Seed routing priors from model names until benchmark calibration overrides them."""

    if "gpt-5.6" in name:
        _raise_caps(
            caps,
            0.88,
            ("science_knowledge", "code", "math", "logic", "critique", "structured_output", "daily_work"),
        )
        _raise_caps(caps, 0.82, ("multilingual", "long_context"))
        _raise_caps(caps, 0.66, ("agentic_tool_calling",))
    elif "gpt-5.5" in name:
        _raise_caps(
            caps,
            0.84,
            ("science_knowledge", "code", "math", "logic", "critique", "structured_output", "daily_work"),
        )
        _raise_caps(caps, 0.80, ("multilingual",))
        _raise_caps(caps, 0.78, ("long_context",))
        _raise_caps(caps, 0.62, ("agentic_tool_calling",))
    elif "gpt-5.4" in name or "gpt-5" in name:
        _raise_caps(
            caps,
            0.80,
            ("science_knowledge", "code", "math", "logic", "critique", "structured_output", "daily_work"),
        )
        _raise_caps(caps, 0.78, ("multilingual",))
        _raise_caps(caps, 0.74, ("long_context",))
        _raise_caps(caps, 0.58, ("agentic_tool_calling",))
    elif any(token in name for token in ("120b", "pro", "sonnet", "opus")):
        _raise_caps(
            caps,
            0.76,
            ("science_knowledge", "code", "math", "logic", "critique", "structured_output", "daily_work"),
        )
    if any(token in name for token in ("20b", "70b", "80b")):
        _raise_caps(
            caps,
            0.62,
            ("science_knowledge", "code", "math", "logic", "structured_output", "daily_work"),
        )
    if any(token in name for token in ("flash", "mini", "4b", "7b")):
        _raise_caps(caps, 0.70, ("daily_work",))
        _raise_caps(caps, 0.66, ("multilingual",))
        _raise_caps(caps, 0.65, ("structured_output",))
    if any(token in name for token in ("codex", "code", "coder")):
        _raise_caps(caps, 0.86, ("code",))
        _raise_caps(caps, 0.82, ("critique", "structured_output"))
        _raise_caps(caps, 0.76, ("logic",))
        _raise_caps(caps, 0.72, ("agentic_tool_calling",))
        _raise_caps(caps, 0.68, ("daily_work",))
    if "review" in name or "critic" in name:
        _raise_caps(caps, 0.88, ("critique",))
        _raise_caps(caps, 0.82, ("structured_output",))
    if "terra" in name:
        _raise_caps(caps, 0.90, ("science_knowledge", "math", "logic", "daily_work"))
        _raise_caps(caps, 0.88, ("structured_output", "critique"))
        _raise_caps(caps, 0.84, ("code", "multilingual", "long_context"))
        _raise_caps(caps, 0.70, ("agentic_tool_calling",))
    if "sol" in name:
        _raise_caps(caps, 0.90, ("code", "math", "logic"))
        _raise_caps(caps, 0.86, ("science_knowledge", "critique", "structured_output"))
        _raise_caps(caps, 0.78, ("long_context",))
        _raise_caps(caps, 0.68, ("agentic_tool_calling",))
    if "luna" in name:
        _raise_caps(caps, 0.88, ("multilingual", "daily_work", "science_knowledge"))
        _raise_caps(caps, 0.86, ("structured_output", "long_context"))
        _raise_caps(caps, 0.82, ("logic", "critique"))


def _raise_caps(caps: dict[str, float], value: float, axes: Sequence[str]) -> None:
    for axis in axes:
        if axis in caps:
            caps[axis] = max(caps[axis], max(0.0, min(1.0, float(value))))


def _axis_alias(value: str) -> str:
    key = value.strip().lower()
    aliases = {
        "science": "science_knowledge",
        "scientific_synthesis": "science_knowledge",
        "reasoning": "logic",
        "coding": "code",
        "code_reasoning": "code",
        "math_reasoning": "math",
        "tool_calling": "agentic_tool_calling",
        "verification": "critique",
        "cost_efficiency": "daily_work",
    }
    return aliases.get(key, key)


def _score01(value: float) -> float:
    number = float(value)
    if number > 1.0:
        number = number / 5.0 if number <= 5.0 else number / 100.0
    return max(0.0, min(1.0, number))


def _infer_provider(model: str) -> str:
    lower = model.lower()
    if lower.startswith("claude") or lower.startswith("anthropic/"):
        return "anthropic"
    if lower.startswith("gemini") or lower.startswith("google/"):
        return "gemini"
    if "step" in lower or "nvidia" in lower or "gpt-oss" in lower:
        return "nvidia"
    return "openai-compatible"


def _infer_api_format(provider: str) -> str:
    normalized = provider.lower()
    if normalized in {"cpa-plus", "aisz", "tokenapis", "responses"}:
        return "responses"
    if normalized in {"anthropic", "anthropic-compatible"}:
        return "anthropic"
    if normalized in {"gemini", "gemini-compatible"}:
        return "gemini"
    return "chat"


def _default_base_url_env(provider: str) -> str:
    normalized = provider.lower()
    if normalized == "nvidia":
        return "AXIO_NVIDIA_BASE_URL"
    if normalized == "cpa-plus":
        return "AXIO_CPA_PLUS_BASE_URL"
    if normalized == "aisz":
        return "AXIO_AISZ_BASE_URL"
    if normalized == "tokenapis":
        return "AXIO_TOKENAPIS_BASE_URL"
    if normalized in {"anthropic", "anthropic-compatible"}:
        return "ANTHROPIC_BASE_URL"
    if normalized in {"gemini", "gemini-compatible"}:
        return "AXIO_GEMINI_BASE_URL"
    return "AXIO_OPENAI_COMPAT_BASE_URL"


def _default_api_key_env(provider: str) -> str:
    normalized = provider.lower()
    if normalized == "nvidia":
        return "AXIO_NVIDIA_API_KEYS"
    if normalized == "cpa-plus":
        return "AXIO_CPA_PLUS_API_KEY"
    if normalized == "aisz":
        return "AXIO_AISZ_API_KEY"
    if normalized == "tokenapis":
        return "AXIO_TOKENAPIS_API_KEY"
    if normalized in {"anthropic", "anthropic-compatible"}:
        return "ANTHROPIC_API_KEY"
    if normalized in {"gemini", "gemini-compatible"}:
        return "AXIO_GEMINI_API_KEY"
    return "AXIO_OPENAI_COMPAT_API_KEY"


def _default_auth_scheme(provider: str, api_format: str) -> str:
    normalized_provider = provider.lower()
    normalized_format = str(api_format or "").strip().lower()
    if normalized_format == "gemini" or normalized_provider in {"gemini", "gemini-compatible"}:
        return "query"
    if normalized_format == "anthropic" or normalized_provider in {"anthropic", "anthropic-compatible"}:
        return "x-api-key"
    return "bearer"


def _normalize_auth_scheme(value: Any) -> str:
    raw = str(value or "bearer").strip().lower().replace("_", "-")
    aliases = {
        "authorization": "bearer",
        "authorization-bearer": "bearer",
        "api-key": "x-api-key",
        "x_api_key": "x-api-key",
        "google-api-key": "x-goog-api-key",
        "x-goog-api-key": "x-goog-api-key",
        "query-key": "query",
        "url-query": "query",
        "none": "none",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in {"bearer", "x-api-key", "query", "none", "x-goog-api-key"}:
        return "bearer"
    return normalized


def _optional_float(*values: Any) -> float | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _optional_int(*values: Any) -> int | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Parse JSON and environment-style booleans without truthy-string bugs."""

    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def _normalize_privacy_tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [item.strip() for item in value.replace(";", ",").split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = [str(item).strip() for item in value]
    else:
        values = ["external_provider"]
    normalized = tuple(dict.fromkeys(item for item in values if item))
    return normalized or ("external_provider",)


def _split_env_list(value: str) -> list[str]:
    items = []
    for chunk in value.replace(";", ",").replace("\n", ",").split(","):
        text = chunk.strip()
        if text:
            items.append(text)
    return list(dict.fromkeys(items))


def _dedupe_profiles(profiles: Sequence[ModelProfile]) -> list[ModelProfile]:
    seen: dict[str, ModelProfile] = {}
    order: list[str] = []
    for profile in profiles:
        key = profile.profile_id.lower()
        if key not in seen:
            order.append(key)
        seen[key] = profile
    return [seen[key] for key in order]
