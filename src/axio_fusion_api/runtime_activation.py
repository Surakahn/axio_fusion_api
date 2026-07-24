"""Atomic activation for process-local Fusion engines.

The provider enrollment path may take minutes and can fail halfway through a
large portfolio.  Serving must therefore keep using the last complete engine
until a new, validated engine is swapped in one critical section.  This module
stores only live engine objects in memory; activation receipts contain hashes,
counts, and bounded state labels rather than provider identifiers, prompts, or
credentials.
"""

from __future__ import annotations

from collections import Counter
import threading
from typing import Any, Mapping

from .orchestrator import FusionEngine
from .latency_policy import profile_latency_eligibility
from .registry import registry_readiness
from .schemas import sha256_text, stable_json


class RuntimeActivationError(ValueError):
    """Raised when an activation request is not a usable Fusion engine."""


class AtomicFusionRuntime:
    """Hold the active engine and replace it atomically.

    A request receives the engine object that was active at dispatch time.  A
    concurrent activation affects subsequent requests only, so an in-flight
    request cannot observe a half-updated profile list or policy bundle.
    """

    def __init__(self, engine: FusionEngine, *, history_limit: int = 2) -> None:
        _validate_engine_candidate(engine)
        self._engine = engine
        self._generation = 0
        self._history_limit = max(1, min(8, int(history_limit or 1)))
        self._history: list[FusionEngine] = []
        self._lock = threading.RLock()

    def snapshot(self) -> tuple[FusionEngine, int]:
        """Return a stable engine/generation pair for one request."""

        with self._lock:
            return self._engine, self._generation

    def safe_snapshot(self) -> dict[str, Any]:
        """Return a durable-safe projection of the active runtime."""

        with self._lock:
            return _activation_summary(
                self._engine,
                generation=self._generation,
                history_depth=len(self._history),
            )

    def swap(
        self,
        engine: FusionEngine,
        *,
        expected_generation: int | None = None,
        reason: str = "runtime_refresh",
    ) -> dict[str, Any]:
        """Atomically activate a complete candidate or leave the old one intact."""

        try:
            _validate_engine_candidate(engine)
        except RuntimeActivationError as exc:
            return _blocked_activation(
                reason_code="candidate_not_activatable",
                detail_code=str(exc),
                generation=self._generation,
            )

        with self._lock:
            if expected_generation is not None and int(expected_generation) != self._generation:
                return _blocked_activation(
                    reason_code="runtime_generation_conflict",
                    detail_code="expected_generation_does_not_match_active_generation",
                    generation=self._generation,
                )
            previous = self._engine
            previous_summary = _activation_summary(previous, generation=self._generation)
            self._history.append(previous)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]
            self._engine = engine
            self._generation += 1
            active_summary = _activation_summary(
                engine,
                generation=self._generation,
                history_depth=len(self._history),
            )
            return {
                "schema": "axio_fusion_api.runtime_activation.v1",
                "status": "ready",
                "operation": "swap",
                "generation": self._generation,
                "previous_generation": previous_summary["generation"],
                "reason_sha256": sha256_text(str(reason or "runtime_refresh")),
                "active": active_summary,
                "previous": previous_summary,
                "atomic": True,
                "old_engine_preserved_until_activation": True,
                "raw_provider_names_persisted": False,
                "raw_provider_model_ids_persisted": False,
                "raw_provider_urls_persisted": False,
                "raw_prompts_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }

    def rollback(
        self,
        *,
        expected_generation: int | None = None,
        reason: str = "runtime_rollback",
    ) -> dict[str, Any]:
        """Restore the most recent complete engine, if one is retained."""

        with self._lock:
            if expected_generation is not None and int(expected_generation) != self._generation:
                return _blocked_activation(
                    reason_code="runtime_generation_conflict",
                    detail_code="expected_generation_does_not_match_active_generation",
                    generation=self._generation,
                )
            if not self._history:
                return _blocked_activation(
                    reason_code="runtime_rollback_unavailable",
                    detail_code="no_previous_engine_retained",
                    generation=self._generation,
                )
            previous = self._engine
            candidate = self._history.pop()
            self._engine = candidate
            self._generation += 1
            # Keep the engine being rolled back from available as the next
            # rollback target, while respecting the bounded history limit.
            self._history.append(previous)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]
            active_summary = _activation_summary(
                candidate,
                generation=self._generation,
                history_depth=len(self._history),
            )
            return {
                "schema": "axio_fusion_api.runtime_activation.v1",
                "status": "ready",
                "operation": "rollback",
                "generation": self._generation,
                "previous_generation": self._generation - 1,
                "reason_sha256": sha256_text(str(reason or "runtime_rollback")),
                "active": active_summary,
                "atomic": True,
                "raw_provider_names_persisted": False,
                "raw_provider_model_ids_persisted": False,
                "raw_provider_urls_persisted": False,
                "raw_prompts_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }


def _validate_engine_candidate(engine: FusionEngine) -> None:
    if not isinstance(engine, FusionEngine):
        raise RuntimeActivationError("candidate_engine_type_invalid")
    profiles = list(engine.profiles)
    if not profiles:
        raise RuntimeActivationError("candidate_engine_has_no_profiles")
    if any(profile.enabled is not True for profile in profiles):
        raise RuntimeActivationError("candidate_engine_contains_disabled_profile")
    if any(str(profile.health or "").strip().lower() == "unavailable" for profile in profiles):
        raise RuntimeActivationError("candidate_engine_contains_unavailable_profile")
    if any(profile_latency_eligibility(profile).get("eligible") is False for profile in profiles):
        raise RuntimeActivationError("candidate_engine_contains_latency_ineligible_profile")
    readiness = registry_readiness(profiles)
    if readiness.get("ready") is not True:
        raise RuntimeActivationError("candidate_engine_registry_not_ready")


def _activation_summary(
    engine: FusionEngine,
    *,
    generation: int,
    history_depth: int = 0,
) -> dict[str, Any]:
    profiles = list(engine.profiles)
    profile_hashes = sorted(sha256_text(profile.profile_id) for profile in profiles)
    provider_hashes = sorted({sha256_text(profile.provider) for profile in profiles})
    canonical_hashes = sorted({profile.canonical_identity_sha256 for profile in profiles})
    api_formats = Counter(str(profile.api_format or "unknown") for profile in profiles)
    health = Counter(str(profile.health or "unknown") for profile in profiles)
    policy = getattr(engine, "routing_policy", {})
    policy_digest = ""
    if isinstance(policy, Mapping) and policy.get("active") is True:
        policy_digest = sha256_text(
            stable_json(
                {
                    "policy_id_sha256": str(policy.get("policy_id_sha256") or ""),
                    "bundle_digest_sha256": str(policy.get("bundle_digest_sha256") or ""),
                }
            )
        )
    return {
        "schema": "axio_fusion_api.runtime_activation_summary.v1",
        "generation": int(generation),
        "profile_count": len(profiles),
        "provider_count": len(provider_hashes),
        "canonical_model_count": len(canonical_hashes),
        "profile_set_sha256": sha256_text(stable_json(profile_hashes)),
        "provider_set_sha256": sha256_text(stable_json(provider_hashes)),
        "api_format_counts": dict(sorted(api_formats.items())),
        "health_counts": dict(sorted(health.items())),
        "routing_policy_digest_sha256": policy_digest,
        "history_depth": max(0, int(history_depth)),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _blocked_activation(*, reason_code: str, detail_code: str, generation: int) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.runtime_activation.v1",
        "status": "blocked",
        "operation": "none",
        "generation": int(generation),
        "reason_codes": [str(reason_code), str(detail_code)],
        "atomic": True,
        "old_engine_preserved": True,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


__all__ = ["AtomicFusionRuntime", "RuntimeActivationError"]
