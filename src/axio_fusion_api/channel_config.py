"""Process-local configuration for arbitrary remote Fusion channels.

The normal deployment path uses a non-secret manifest plus environment
variables.  This module adds the corresponding programmatic path for hosts
that already have a secret manager or receive a channel definition at runtime.
Literal endpoints and credentials are accepted only into in-memory
``ModelProfile`` fields and are deliberately absent from ``safe_dict`` and
all registry/artifact serializers.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

from .providers import (
    _safe_list_models,
    profile_credential_readiness,
    provider_base_url_readiness,
)
from .registry import (
    _configured_api_format,
    _default_auth_scheme,
    _normalize_auth_scheme,
    _split_config_model_rows,
    normalize_profile,
)
from .schemas import ModelProfile, sha256_text, stable_json


class ChannelConfigError(ValueError):
    """Raised when a runtime channel manifest cannot be used safely."""


SecretResolver = Callable[[str], Any]
_ENVIRONMENT_VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DISCOVERY_SEED_MODEL = "__axio_discovery_seed__"


def build_runtime_profiles(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    environment: Mapping[str, Any] | None = None,
    secret_resolver: SecretResolver | None = None,
) -> list[ModelProfile]:
    """Build serving profiles from a process-local channel manifest.

    A channel may provide ``base_url``/``api_key`` values directly, or refer to
    ``base_url_env``/``api_key_env`` names.  Common deployment spellings such as
    ``baseurl`` and ``apikey`` are accepted as aliases for direct runtime
    manifests.  The latter are resolved from the
    supplied mapping, then from ``os.environ``; ``secret_resolver`` takes
    precedence for named secrets.  Models may be strings or model objects and
    may override the channel protocol, endpoint, key pool, auth scheme, or
    capability metadata. ``models_env``/``modelsEnv`` can supply additional
    model ids without mutating the process environment.

    This helper does not perform network discovery.  A channel with no model
    rows yields no static profile and should be passed to
    :func:`discover_runtime_profiles` when its ``/models`` endpoint is the
    source of truth.
    """

    rows = _manifest_provider_rows(manifest)
    profiles: list[ModelProfile] = []
    for index, row in enumerate(rows):
        profiles.extend(
            _build_channel_profiles(
                row,
                environment=environment,
                secret_resolver=secret_resolver,
                include_discovery_seed=False,
                row_index=index,
            )
        )
    return _dedupe_profiles(profiles)


def discover_runtime_profiles(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    environment: Mapping[str, Any] | None = None,
    secret_resolver: SecretResolver | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Discover model ids from arbitrary channels without changing the process env.

    The returned ``profiles`` are live in-memory objects and can be passed
    directly to ``FusionEngine`` or the existing probe/enrollment functions.
    ``reports`` is an operator-only, private diagnostic value because it can
    contain the model ids returned by upstream ``/models``.  Callers that need
    a durable receipt should hash or redact it before writing it.
    """

    rows = _manifest_provider_rows(manifest)
    bounded_timeout = max(1.0, min(300.0, float(timeout)))
    reports: list[dict[str, Any]] = []
    discovered: list[ModelProfile] = []
    static_profiles: list[ModelProfile] = []
    for index, row in enumerate(rows):
        static_profiles.extend(
            _build_channel_profiles(
                row,
                environment=environment,
                secret_resolver=secret_resolver,
                include_discovery_seed=False,
                row_index=index,
            )
        )
        seed_profiles = _build_channel_profiles(
            row,
            environment=environment,
            secret_resolver=secret_resolver,
            include_discovery_seed=True,
            row_index=index,
        )
        seed = seed_profiles[0]
        report = _safe_list_models(seed, timeout=bounded_timeout)
        reports.append(report)
        model_ids = report.get("model_ids") if isinstance(report.get("model_ids"), list) else []
        for model_id in model_ids:
            model_name = str(model_id or "").strip()
            if not model_name:
                continue
            discovered.append(
                replace(
                    seed,
                    model=model_name,
                    canonical_model_id=model_name,
                    source="runtime_channel_discovery",
                )
            )

    profiles = _dedupe_profiles([*discovered, *static_profiles])
    report_status_counts: dict[str, int] = {}
    failed_report_count = 0
    skipped_report_count = 0
    empty_success_report_count = 0
    for report in reports:
        status = str(report.get("status") or "unknown").strip().lower()
        report_status_counts[status] = report_status_counts.get(status, 0) + 1
        if status in {"skipped", "disabled"}:
            skipped_report_count += 1
        elif status not in {"ok", "ready", "available"}:
            failed_report_count += 1
        elif not (report.get("model_ids") if isinstance(report.get("model_ids"), list) else []):
            empty_success_report_count += 1
    warning_codes: list[str] = []
    if failed_report_count:
        warning_codes.append(
            "provider_discovery_partial_failure"
            if profiles
            else "provider_discovery_all_failed"
        )
    if empty_success_report_count:
        warning_codes.append("provider_discovery_empty_inventory")
    return {
        "schema": "axio_fusion_api.runtime_channel_discovery.v1",
        "status": "ready" if profiles else "blocked",
        "profiles": profiles,
        "reports": reports,
        "provider_count": len(reports),
        "successful_provider_count": max(0, len(reports) - failed_report_count),
        "failed_provider_count": failed_report_count,
        "skipped_provider_count": skipped_report_count,
        "empty_success_provider_count": empty_success_report_count,
        "report_status_counts": dict(sorted(report_status_counts.items())),
        "warning_codes": warning_codes,
        "discovered_profile_count": len(discovered),
        "static_profile_count": len(static_profiles),
        "profile_count": len(profiles),
        "profile_set_sha256": sha256_text(
            stable_json(sorted(sha256_text(profile.profile_id) for profile in profiles))
        ),
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }


def runtime_channel_summary(profiles: Sequence[ModelProfile]) -> dict[str, Any]:
    """Return a hash-only summary suitable for an operator readiness receipt."""

    provider_hashes = sorted({sha256_text(profile.provider) for profile in profiles})
    profile_hashes = sorted(sha256_text(profile.profile_id) for profile in profiles)
    format_counts: dict[str, int] = {}
    canonical_groups: dict[str, int] = {}
    credential_ready_count = 0
    for profile in profiles:
        api_format = str(profile.api_format or "unknown")
        format_counts[api_format] = format_counts.get(api_format, 0) + 1
        identity_hash = profile.canonical_identity_sha256
        canonical_groups[identity_hash] = canonical_groups.get(identity_hash, 0) + 1
        credential_readiness = profile_credential_readiness(profile)
        if credential_readiness.get("credential_ready") is True:
            credential_ready_count += 1
    return {
        "schema": "axio_fusion_api.runtime_channel_summary.v1",
        "profile_count": len(profiles),
        "provider_count": len(provider_hashes),
        "credential_ready_profile_count": credential_ready_count,
        "profile_set_sha256": sha256_text(stable_json(profile_hashes)),
        "provider_set_sha256": sha256_text(stable_json(provider_hashes)),
        "canonical_model_group_count": len(canonical_groups),
        "canonical_replica_group_size_counts": _count_sizes(canonical_groups.values()),
        "api_format_counts": dict(sorted(format_counts.items())),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }


def _manifest_provider_rows(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if isinstance(manifest, Mapping):
        value = manifest.get("providers")
        rows = value if isinstance(value, list) else [manifest]
    elif isinstance(manifest, Sequence) and not isinstance(manifest, (str, bytes, bytearray)):
        rows = list(manifest)
    else:
        raise ChannelConfigError("runtime channel manifest must be an object or provider list")
    if not rows:
        raise ChannelConfigError("runtime channel manifest must contain at least one provider")
    invalid = [index for index, row in enumerate(rows) if not isinstance(row, Mapping)]
    if invalid:
        raise ChannelConfigError(f"runtime provider rows must be objects: indexes={invalid}")
    return [row for row in rows if isinstance(row, Mapping)]


def _build_channel_profiles(
    row: Mapping[str, Any],
    *,
    environment: Mapping[str, Any] | None,
    secret_resolver: SecretResolver | None,
    include_discovery_seed: bool,
    row_index: int,
) -> list[ModelProfile]:
    provider = _text(row, "provider", "name", "channel", "channel_name", "channelName")
    if not provider:
        raise ChannelConfigError(f"provider row {row_index} is missing provider")
    channel_format = _strict_api_format(
        _value(row, "api_format", "apiFormat", "api_mode", "protocol", "protocol_format"),
        provider=provider,
    )
    channel_models = _runtime_model_rows(
        row,
        environment=environment,
        secret_resolver=secret_resolver,
    )
    if include_discovery_seed:
        model_rows = [{"model": _DISCOVERY_SEED_MODEL}]
    else:
        model_rows = channel_models
    profiles: list[ModelProfile] = []
    for model_index, model_row in enumerate(model_rows):
        model_name = _text(model_row, "model", "model_id", "modelId", "id", "name")
        if not model_name:
            raise ChannelConfigError(
                f"provider row {row_index} model row {model_index} is missing model"
            )
        api_format = _strict_api_format(
            _value(
                model_row,
                "api_format",
                "apiFormat",
                "api_mode",
                "protocol",
                "protocol_format",
            )
            or channel_format,
            provider=provider,
            fallback=channel_format,
        )
        base_env = _environment_name(
            _value(model_row, "base_url_env", "baseUrlEnv", "baseurl_env", "baseUrlEnvName")
            or _value(row, "base_url_env", "baseUrlEnv", "baseurl_env", "baseUrlEnvName")
        )
        key_env = _environment_name(
            _value(model_row, "api_key_env", "apiKeyEnv", "apikey_env", "apiKeyEnvName")
            or _value(row, "api_key_env", "apiKeyEnv", "apikey_env", "apiKeyEnvName")
        )
        base_url = _resolve_endpoint(
            row,
            model_row,
            base_env,
            environment,
            secret_resolver=secret_resolver,
        )
        base_readiness = provider_base_url_readiness(base_url)
        if base_readiness.get("valid") is not True:
            raise ChannelConfigError(
                f"provider row {row_index} model {model_index} has invalid base_url: "
                f"{base_readiness.get('reason_code') or 'invalid'}"
            )
        auth_scheme = _normalize_auth_scheme(
            _value(model_row, "auth_scheme", "authScheme")
            or _value(row, "auth_scheme", "authScheme")
            or _default_auth_scheme(provider, api_format)
        )
        keys = _resolve_api_keys(
            row,
            model_row,
            key_env,
            environment=environment,
            secret_resolver=secret_resolver,
        )
        if auth_scheme != "none" and not keys:
            raise ChannelConfigError(
                f"provider row {row_index} model {model_index} is missing API credentials"
            )
        profile_row = {
            "provider": provider,
            "model": model_name,
            "api_format": api_format,
            "capabilities": _merged_mapping(row.get("capabilities"), model_row.get("capabilities")),
            "input_cost_per_million": _model_value(row, model_row, "input_cost_per_million"),
            "output_cost_per_million": _model_value(row, model_row, "output_cost_per_million"),
            "p50_latency_ms": _model_value(row, model_row, "p50_latency_ms"),
            "p95_latency_ms": _model_value(row, model_row, "p95_latency_ms"),
            "context_tokens": _model_value(row, model_row, "context_tokens"),
            "supports_tools": _model_value(row, model_row, "supports_tools", default=False),
            "tool_capability": _model_value(row, model_row, "tool_capability", default=""),
            "tool_capability_source": _model_value(row, model_row, "tool_capability_source", default=""),
            "tool_probe_status": _model_value(row, model_row, "tool_probe_status", default="not_run"),
            "supports_vision": _model_value(row, model_row, "supports_vision", default=False),
            "reasoning_transport": _model_value(
                row,
                model_row,
                "reasoning_transport",
                default={},
            ),
            "privacy_tags": _model_value(row, model_row, "privacy_tags", default=["external_provider"]),
            "base_url_env": base_env,
            "api_key_env": key_env,
            "auth_scheme": auth_scheme,
            "models_endpoint": _model_value(
                row,
                model_row,
                "models_endpoint",
                default="/models",
            ),
            "discover_models": _model_value(
                row,
                model_row,
                "discover_models",
                default=True,
            ),
            "canonical_model_id": _model_value(
                row,
                model_row,
                "canonical_model_id",
                default=model_name,
            ),
            "enabled": _model_value(row, model_row, "enabled", default=True),
            "health": _model_value(row, model_row, "health", default="unknown"),
            "source": "runtime_channel_config",
        }
        profile = normalize_profile(profile_row)
        profiles.append(
            replace(
                profile,
                runtime_base_url=base_url,
                runtime_api_keys=tuple(keys),
            )
        )
    return profiles


def _resolve_endpoint(
    channel: Mapping[str, Any],
    model: Mapping[str, Any],
    env_name: str,
    environment: Mapping[str, Any] | None,
    *,
    secret_resolver: SecretResolver | None,
) -> str:
    model_direct = _value(
        model,
        "base_url",
        "baseUrl",
        "baseurl",
        "baseURL",
        "endpoint",
        "endpoint_url",
    )
    if model_direct not in (None, ""):
        return str(model_direct).strip()
    # A model-scoped environment reference is an override too. It must win
    # over a channel-level literal endpoint in mixed portfolios.
    model_env = _value(
        model,
        "base_url_env",
        "baseUrlEnv",
        "baseurl_env",
        "baseUrlEnvName",
    )
    if model_env not in (None, ""):
        return _resolve_named_value(
            env_name,
            environment=environment,
            secret_resolver=secret_resolver,
        ).strip()
    channel_direct = _value(
        channel,
        "base_url",
        "baseUrl",
        "baseurl",
        "baseURL",
        "endpoint",
        "endpoint_url",
    )
    if channel_direct not in (None, ""):
        return str(channel_direct).strip()
    return _resolve_named_value(
        env_name,
        environment=environment,
        secret_resolver=secret_resolver,
    ).strip()


def _resolve_api_keys(
    channel: Mapping[str, Any],
    model: Mapping[str, Any],
    env_name: str,
    *,
    environment: Mapping[str, Any] | None,
    secret_resolver: SecretResolver | None,
) -> list[str]:
    model_direct = _value(
        model,
        "api_keys",
        "apiKeys",
        "api_key",
        "apiKey",
        "apikey",
        "keys",
    )
    if model_direct not in (None, ""):
        return _split_secret_values(model_direct)
    # A model-scoped key environment is an override too. It must win over a
    # channel-level literal key pool so requests cannot cross model scopes.
    model_env = _value(
        model,
        "api_key_env",
        "apiKeyEnv",
        "apikey_env",
        "apiKeyEnvName",
    )
    if model_env not in (None, ""):
        return _split_secret_values(
            _resolve_named_value_value(
                env_name,
                environment=environment,
                secret_resolver=secret_resolver,
            )
        )
    channel_direct = _value(
        channel,
        "api_keys",
        "apiKeys",
        "api_key",
        "apiKey",
        "apikey",
        "keys",
    )
    if channel_direct not in (None, ""):
        return _split_secret_values(channel_direct)
    return _split_secret_values(
        _resolve_named_value_value(
            env_name,
            environment=environment,
            secret_resolver=secret_resolver,
        )
    )


def _runtime_model_rows(
    channel: Mapping[str, Any],
    *,
    environment: Mapping[str, Any] | None,
    secret_resolver: SecretResolver | None,
) -> list[dict[str, Any]]:
    """Resolve static model rows with the same env contract as file manifests.

    Dynamic callers commonly keep a provider manifest in memory while the
    model list remains in a deployment environment or secret manager.  The
    process-local path must therefore not silently drop ``models_env`` when
    the file-backed registry would consume it.
    """

    rows = _split_config_model_rows(channel.get("models"))
    models_env = _environment_name(
        _value(
            channel,
            "models_env",
            "modelsEnv",
            "model_ids_env",
            "modelIdsEnv",
            "model_list_env",
            "modelListEnv",
        )
    )
    if models_env:
        rows.extend(
            _split_config_model_rows(
                _resolve_named_value_value(
                    models_env,
                    environment=environment,
                    secret_resolver=secret_resolver,
                )
            )
        )

    # Keep the first-seen order for stable route construction, while allowing
    # an environment-provided row to override a checked-in placeholder.
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for model_row in rows:
        model_name = _text(model_row, "model", "model_id", "modelId", "id", "name")
        if not model_name:
            continue
        if model_name not in deduped:
            order.append(model_name)
        deduped[model_name] = dict(model_row)
    return [deduped[model_name] for model_name in order]


def _resolve_named_value(
    env_name: str,
    *,
    environment: Mapping[str, Any] | None,
    secret_resolver: SecretResolver | None,
) -> str:
    return str(
        _resolve_named_value_value(
            env_name,
            environment=environment,
            secret_resolver=secret_resolver,
        )
        or ""
    )


def _resolve_named_value_value(
    env_name: str,
    *,
    environment: Mapping[str, Any] | None,
    secret_resolver: SecretResolver | None,
) -> Any:
    if not env_name:
        return ""
    if secret_resolver is not None:
        try:
            resolved = secret_resolver(env_name)
        except Exception:  # noqa: BLE001 - external secret-manager boundary
            raise ChannelConfigError("runtime secret resolver failed") from None
        if resolved is not None:
            return resolved
    source = environment if environment is not None else os.environ
    return source.get(env_name, "") or ""


def _strict_api_format(value: Any, *, provider: str, fallback: str | None = None) -> str:
    normalized = _configured_api_format(value, provider=provider, fallback=fallback)
    if normalized is None:
        raise ChannelConfigError(f"unsupported provider api_format for {provider}")
    return normalized


def _environment_name(value: Any) -> str:
    name = str(value or "").strip()
    if name and not _ENVIRONMENT_VARIABLE_NAME_PATTERN.fullmatch(name):
        raise ChannelConfigError(
            "base_url_env/baseurl_env, api_key_env/apikey_env, and models_env must be environment variable names"
        )
    return name


def _value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _model_value(
    channel: Mapping[str, Any],
    model: Mapping[str, Any],
    key: str,
    *,
    default: Any = None,
) -> Any:
    aliases = {
        "input_cost_per_million": ("input_cost_per_million", "inputCostPerMillion"),
        "output_cost_per_million": ("output_cost_per_million", "outputCostPerMillion"),
        "p50_latency_ms": ("p50_latency_ms", "p50LatencyMs"),
        "p95_latency_ms": ("p95_latency_ms", "p95LatencyMs"),
        "context_tokens": ("context_tokens", "contextTokens"),
        "supports_tools": ("supports_tools", "supportsTools", "tool_calling"),
        "tool_capability": ("tool_capability", "toolCapability"),
        "tool_capability_source": ("tool_capability_source", "toolCapabilitySource"),
        "tool_probe_status": ("tool_probe_status", "toolProbeStatus"),
        "supports_vision": ("supports_vision", "supportsVision", "vision"),
        "reasoning_transport": ("reasoning_transport", "reasoningTransport"),
        "privacy_tags": ("privacy_tags", "privacyTags"),
        "models_endpoint": (
            "models_endpoint",
            "modelsEndpoint",
            "model_list_endpoint",
            "modelListEndpoint",
            "models_path",
            "modelsPath",
        ),
        "discover_models": ("discover_models", "discoverModels", "discover"),
        "canonical_model_id": (
            "canonical_model_id",
            "canonicalModelId",
            "canonical_model",
            "canonicalModel",
            "canonical_identity",
            "canonicalIdentity",
        ),
        "enabled": ("enabled",),
        "health": ("health",),
    }
    keys = aliases.get(key, (key,))
    for source in (model, channel):
        for candidate in keys:
            if candidate in source and source.get(candidate) not in (None, ""):
                return source.get(candidate)
    return default


def _text(row: Mapping[str, Any], *keys: str) -> str:
    value = _value(row, *keys)
    return str(value or "").strip()


def _merged_mapping(channel: Any, model: Any) -> dict[str, Any]:
    result = dict(channel) if isinstance(channel, Mapping) else {}
    if isinstance(model, Mapping):
        result.update(dict(model))
    return result


def _split_secret_values(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = [str(item).strip() for item in value]
    else:
        values = str(value or "").replace(";", ",").replace("\n", ",").split(",")
        values = [item.strip() for item in values]
    return list(dict.fromkeys(item for item in values if item))


def _dedupe_profiles(profiles: Sequence[ModelProfile]) -> list[ModelProfile]:
    seen: dict[str, ModelProfile] = {}
    order: list[str] = []
    for profile in profiles:
        key = profile.profile_id.casefold()
        if key not in seen:
            order.append(key)
        seen[key] = profile
    return [seen[key] for key in order]


def _count_sizes(values: Sequence[int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(max(0, int(value)))
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items(), key=lambda item: int(item[0])))
