"""Standalone Axio Fusion API package.

This package intentionally does not import ASciFS/``axio`` modules.  It can be
installed and served as an independent product, while ASciFS may consume it via
HTTP-compatible model APIs.
"""

from .compat import canonicalize_payload, render_response
from .channel_config import (
    ChannelConfigError,
    build_runtime_profiles,
    discover_runtime_profiles,
    runtime_channel_summary,
)
from .orchestrator import FusionEngine
from .provider_enrollment import enroll_provider_channels, enroll_runtime_channels
from .model_screening import (
    ModelScreeningError,
    apply_prefusion_handoff_metadata,
    build_prefusion_fusion_handoff,
    build_fusion_registry_from_screening,
    run_prefusion_model_screening,
    validate_prefusion_handoff,
)
from .available_model_generation import (
    AVAILABLE_MODEL_GENERATION_SCHEMA,
    AvailableModelGenerationError,
    generate_available_model_set,
    publish_available_model_set,
)
from .registry import (
    build_default_registry,
    load_registry,
    validate_prefusion_registry_handoff,
)
from .router import build_route_plan
from .server import create_runtime_http_server
from .runtime_activation import AtomicFusionRuntime, RuntimeActivationError
from .schemas import (
    PUBLIC_MODELS,
    CandidateResult,
    FusionRequest,
    FusionResponse,
    ModelProfile,
)

__all__ = [
    "PUBLIC_MODELS",
    "ChannelConfigError",
    "CandidateResult",
    "FusionEngine",
    "FusionRequest",
    "FusionResponse",
    "ModelProfile",
    "build_default_registry",
    "build_runtime_profiles",
    "create_runtime_http_server",
    "build_route_plan",
    "canonicalize_payload",
    "load_registry",
    "enroll_provider_channels",
    "enroll_runtime_channels",
    "ModelScreeningError",
    "apply_prefusion_handoff_metadata",
    "build_prefusion_fusion_handoff",
    "run_prefusion_model_screening",
    "build_fusion_registry_from_screening",
    "validate_prefusion_handoff",
    "validate_prefusion_registry_handoff",
    "AVAILABLE_MODEL_GENERATION_SCHEMA",
    "AvailableModelGenerationError",
    "generate_available_model_set",
    "publish_available_model_set",
    "discover_runtime_profiles",
    "render_response",
    "runtime_channel_summary",
    "AtomicFusionRuntime",
    "RuntimeActivationError",
]
