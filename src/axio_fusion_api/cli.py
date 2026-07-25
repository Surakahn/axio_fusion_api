from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .benchmark_acquisition import (
    BenchmarkAcquisitionError,
    GPQA_DEFAULT_DESTINATION,
    GPQA_DEFAULT_DOWNLOAD_MANIFEST,
    acquire_gpqa_diamond,
)
from .baseline_screening import (
    build_external_ranking_manifest_from_screening,
    build_non_target_screening_plan,
    run_non_target_screening_campaign,
)
from .calibration import build_registry_calibration, write_json as write_calibration_json
from .compat import canonicalize_payload, render_response
from .execution_boundary import build_remote_api_execution_audit
from .evaluation import (
    assemble_benchmark_dataset_manifest,
    audit_benchmark_campaign_readiness,
    build_benchmark_acquisition_checklist,
    build_benchmark_acquisition_status,
    benchmark_manifest,
    build_benchmark_case_hash_manifest,
    build_benchmark_dataset_manifest_template,
    build_benchmark_evidence_pack,
    build_external_provider_ranking_template,
    build_benchmark_fusion_failure_analysis,
    build_benchmark_claim_audit,
    build_benchmark_final_audit,
    build_benchmark_harness_pin_manifest,
    build_benchmark_methodology_manifest,
    build_benchmark_materialization_status,
    build_benchmark_campaign_progress_plan,
    build_provider_baseline_freeze_manifest,
    build_provider_probe_evidence_audit,
    build_benchmark_run_matrix,
    build_benchmark_scorecard,
    build_benchmark_api_surface_parity_report,
    build_benchmark_source_manifest_template,
    build_fusion_code_test_receipt,
    build_fusion_completion_audit,
    build_fusion_live_readiness,
    build_fusion_live_runbook,
    build_fusion_system_development_readiness,
    _fusion_provider_env_readiness,
    build_official_harness_execution_plan,
    build_official_import_audit,
    bind_benchmark_source_manifest_case_hashes,
    build_official_import_batch_template,
    import_official_benchmark_run_batch,
    import_official_benchmark_run,
    materialize_benchmark_datasets,
    prepare_benchmark_source_manifest,
    run_benchmark_campaign,
    run_benchmark_dataset,
    run_multiple_choice_benchmark,
    validate_benchmark_source_manifest,
    validate_benchmark_dataset,
    write_json,
)
from .learning import (
    build_learning_signal_report,
    build_orchestrator_training_dataset,
    build_router_policy_shadow_patch,
    build_training_contamination_audit,
    write_json as write_learning_json,
)
from .available_model_generation import (
    AvailableModelGenerationError,
    generate_available_model_set,
    publish_available_model_set,
)
from .model_screening import (
    ModelScreeningError,
    run_prefusion_model_screening,
)
from .official_harness import (
    build_official_harness_bridge_preflight,
    evaluate_official_harness_samples,
    generate_official_harness_samples,
    import_official_harness_evaluation,
)
from .official_campaign import run_official_harness_campaign
from .operational_admission import run_operational_admission
from .orchestrator import FusionEngine
from .policy_control import (
    activate_routing_policy,
    build_routing_policy_candidate,
    build_routing_policy_shadow_replay,
    load_active_routing_policy,
    review_routing_policy_candidate,
)
from .provider_onboarding import (
    activate_provider_onboarding_candidate,
    apply_provider_onboarding_activation,
    build_provider_onboarding_candidate,
    review_provider_onboarding_candidate,
)
from .provider_enrollment import enroll_provider_channels
from .providers import (
    build_provider_input_adapter_self_test,
    discover_provider_inventory,
    probe_exposed_provider_models,
    probe_provider_models,
    probe_provider_tool_support,
    redact_provider_probe_artifact_file,
    redact_provider_tool_probe_artifact_file,
)
from .registry import (
    build_provider_portfolio_audit,
    build_registry_from_probe_artifacts,
    load_registry,
    provider_configured_profiles_from_env,
    provider_configuration_source_summary,
    registry_report,
)
from .server import (
    build_api_surface_live_smoke,
    build_api_surface_protocol_self_test,
    build_api_surface_stream_live_smoke,
    build_fast_path_live_diagnostic,
    build_fusion_deliberation_live_smoke,
    create_runtime_http_server,
    serve,
)
from .schemas import sha256_text
from .trace_store import build_trace_report, write_json as write_trace_json
from .tools import execute_tool_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axio-fusion-api-standalone")
    parser.add_argument("--registry", default=None)
    parser.add_argument(
        "--provider-config-file",
        default=None,
        help=(
            "Non-secret provider manifest. Put this option before the command; "
            "base URLs and API keys are resolved from its environment-variable names."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8789)
    serve_cmd.add_argument("--live", action="store_true")
    serve_cmd.add_argument(
        "--discover",
        action="store_true",
        help="Discover model ids from the configured provider manifest before serving.",
    )
    serve_cmd.add_argument(
        "--enroll",
        action="store_true",
        help="Discover, text-probe, and optionally tool-probe provider models before serving.",
    )
    serve_cmd.add_argument(
        "--diagnostic-only",
        action="store_true",
        help=(
            "Allow inventory/ordinary probe compatibility paths without pre-Fusion "
            "admission; never use for production serving."
        ),
    )
    serve_cmd.add_argument("--discovery-timeout", type=float, default=15.0)
    serve_cmd.add_argument("--enrollment-max-workers", type=int, default=8)
    serve_cmd.add_argument("--enrollment-max-models", type=int, default=None)
    serve_cmd.add_argument("--enrollment-max-models-per-provider", type=int, default=None)
    serve_cmd.add_argument(
        "--enrollment-tool-probe-timeout",
        type=float,
        default=None,
        help="Bound native-tool calibration separately from text health enrollment.",
    )
    serve_cmd.add_argument("--enrollment-tool-probe-max-models", type=int, default=None)
    serve_cmd.add_argument(
        "--enrollment-tool-probe-max-models-per-provider",
        type=int,
        default=None,
    )
    serve_cmd.add_argument("--enrollment-min-available-models", type=int, default=1)
    serve_cmd.add_argument("--no-tool-calibration", action="store_true")
    serve_cmd.add_argument(
        "--prefusion-focus-manifest",
        default=None,
        help="Non-secret focus manifest used by the pre-Fusion research ranking agent.",
    )
    serve_cmd.add_argument(
        "--prefusion-source-manifest",
        default=None,
        help="Public-source manifest used to build the pre-Fusion operational prior.",
    )
    serve_cmd.add_argument(
        "--prefusion-research-agent-config",
        default=None,
        help="Non-secret remote research-agent profile configuration.",
    )
    serve_cmd.add_argument(
        "--prefusion-research-output",
        default=None,
        help="Previously captured strict research JSON for a controlled run.",
    )
    serve_cmd.add_argument("--prefusion-max-models", type=int, default=None)
    serve_cmd.add_argument(
        "--prefusion-research-batch-size",
        type=int,
        default=None,
        help="Logical candidates per remote research-agent request.",
    )
    serve_cmd.add_argument(
        "--prefusion-research-max-workers",
        type=int,
        default=None,
        help="Bounded concurrent research-agent batch requests.",
    )
    serve_cmd.add_argument(
        "--prefusion-stream-probe-samples",
        type=int,
        default=None,
        help="Strict streaming health samples per physical profile; production requires at least two.",
    )
    serve_cmd.add_argument(
        "--enrollment-receipt-output",
        default=None,
        help="Optional safe JSON path for the in-memory enrollment receipt.",
    )
    serve_cmd.set_defaults(func=cmd_serve)

    complete = sub.add_parser("complete")
    complete.add_argument("--api-format", default="chat/completions")
    complete.add_argument("--model", default="axio-terra")
    complete.add_argument("--prompt", default=None)
    complete.add_argument("--request-json", default=None)
    complete.add_argument("--request-file", default=None)
    complete.add_argument("--task-type", default="auto")
    complete.add_argument("--live", action="store_true")
    complete.set_defaults(func=cmd_complete)

    route = sub.add_parser("route-plan")
    route.add_argument("--api-format", default="chat/completions")
    route.add_argument("--model", default="axio-terra")
    route.add_argument("--prompt", default=None)
    route.add_argument("--request-json", default=None)
    route.add_argument("--request-file", default=None)
    route.add_argument("--task-type", default="auto")
    route.set_defaults(func=cmd_route_plan)

    surface_protocol = sub.add_parser("api-surface-protocol-self-test")
    surface_protocol.add_argument("--model", action="append", default=[])
    surface_protocol.add_argument("--prompt", default=None)
    surface_protocol.add_argument("--task-type", default="api_surface_protocol_self_test")
    surface_protocol.add_argument("--output", default=None)
    surface_protocol.set_defaults(func=cmd_api_surface_protocol_self_test)

    surface_live_smoke = sub.add_parser("api-surface-live-smoke")
    surface_live_smoke.add_argument("--model", action="append", default=[])
    surface_live_smoke.add_argument("--prompt", default=None)
    surface_live_smoke.add_argument("--task-type", default="api_surface_live_smoke")
    surface_live_smoke.add_argument("--max-latency-ms", type=int, default=12000)
    surface_live_smoke.add_argument("--max-output-tokens", type=int, default=48)
    surface_live_smoke.add_argument("--live", action="store_true")
    surface_live_smoke.add_argument("--output", default=None)
    surface_live_smoke.set_defaults(func=cmd_api_surface_live_smoke)

    surface_stream_live_smoke = sub.add_parser("api-surface-stream-live-smoke")
    surface_stream_live_smoke.add_argument("--model", action="append", default=[])
    surface_stream_live_smoke.add_argument("--prompt", default=None)
    surface_stream_live_smoke.add_argument(
        "--task-type",
        default="api_surface_stream_live_smoke",
    )
    surface_stream_live_smoke.add_argument("--max-latency-ms", type=int, default=12000)
    surface_stream_live_smoke.add_argument("--max-output-tokens", type=int, default=48)
    surface_stream_live_smoke.add_argument("--live", action="store_true")
    surface_stream_live_smoke.add_argument("--output", default=None)
    surface_stream_live_smoke.set_defaults(func=cmd_api_surface_stream_live_smoke)

    fast_path_diagnostic = sub.add_parser(
        "fast-path-live-diagnostic",
        help="Run one strict-streaming axio-fast request with a bounded safe receipt.",
    )
    fast_path_diagnostic.add_argument(
        "--api-format",
        default="chat/completions",
        choices=["chat/completions", "responses", "anthropic", "gemini"],
    )
    fast_path_diagnostic.add_argument("--prompt", default=None)
    fast_path_diagnostic.add_argument("--task-type", default="fast_path_live_diagnostic")
    fast_path_diagnostic.add_argument("--max-latency-ms", type=int, default=12000)
    fast_path_diagnostic.add_argument("--max-output-tokens", type=int, default=48)
    fast_path_diagnostic.add_argument("--live", action="store_true")
    fast_path_diagnostic.add_argument("--output", default=None)
    fast_path_diagnostic.set_defaults(func=cmd_fast_path_live_diagnostic)

    deliberation_live_smoke = sub.add_parser("fusion-deliberation-live-smoke")
    deliberation_live_smoke.add_argument("--model", action="append", default=[])
    deliberation_live_smoke.add_argument("--prompt", default=None)
    deliberation_live_smoke.add_argument("--task-type", default="fusion_deliberation_live_smoke")
    deliberation_live_smoke.add_argument("--max-latency-ms", type=int, default=30000)
    deliberation_live_smoke.add_argument("--max-output-tokens", type=int, default=128)
    deliberation_live_smoke.add_argument("--max-total-model-calls", type=int, default=6)
    deliberation_live_smoke.add_argument("--max-cost-usd", type=float, default=0.02)
    deliberation_live_smoke.add_argument("--live", action="store_true")
    deliberation_live_smoke.add_argument("--output", default=None)
    deliberation_live_smoke.set_defaults(func=cmd_fusion_deliberation_live_smoke)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--live", action="store_true")
    inventory.add_argument("--timeout", type=float, default=10.0)
    inventory.set_defaults(func=cmd_inventory)

    provider_config_summary = sub.add_parser(
        "provider-config-summary",
        help="Validate provider manifest sources without network calls or secret values.",
    )
    provider_config_summary.add_argument(
        "--output",
        default=None,
        help="Optional safe JSON output path for the operator summary.",
    )
    provider_config_summary.set_defaults(func=cmd_provider_config_summary)

    probe = sub.add_parser("probe")
    probe.add_argument("--timeout", type=float, default=60.0)
    probe.add_argument("--live", action="store_true")
    probe.add_argument("--discover-live-models", action="store_true")
    probe.add_argument("--provider", action="append", default=None)
    probe.add_argument(
        "--profile-hash",
        action="append",
        default=None,
        help="Probe only exact SHA-256 profile identifiers; raw provider/model names are not required.",
    )
    probe.add_argument("--max-models", type=int, default=None)
    probe.add_argument("--max-models-per-provider", type=int, default=None)
    probe.add_argument("--max-workers", type=int, default=4)
    probe.add_argument("--redact-provider-identifiers", action="store_true")
    probe.add_argument("--output", default=None)
    probe.set_defaults(func=cmd_probe)

    tool_probe = sub.add_parser("tool-probe")
    tool_probe.add_argument("--timeout", type=float, default=60.0)
    tool_probe.add_argument("--live", action="store_true")
    tool_probe.add_argument(
        "--profile-hash",
        action="append",
        default=None,
        help="Probe only exact SHA-256 profile identifiers; raw provider/model names are not required.",
    )
    tool_probe.add_argument("--max-models", type=int, default=None)
    tool_probe.add_argument("--max-models-per-provider", type=int, default=None)
    tool_probe.add_argument("--max-workers", type=int, default=4)
    tool_probe.add_argument("--redact-provider-identifiers", action="store_true")
    tool_probe.add_argument("--output", default=None)
    tool_probe.set_defaults(func=cmd_tool_probe)

    operational_admission = sub.add_parser(
        "operational-admission",
        help=(
            "Run fixed non-target long-request workloads and separate production "
            "admission from formal baseline eligibility."
        ),
    )
    operational_admission.add_argument(
        "--registry", dest="registry", default=argparse.SUPPRESS
    )
    operational_admission.add_argument("--timeout", type=float, default=90.0)
    operational_admission.add_argument("--live", action="store_true")
    operational_admission.add_argument(
        "--profile-hash",
        action="append",
        default=None,
        help="Run only exact SHA-256 profile identifiers.",
    )
    operational_admission.add_argument("--max-models", type=int, default=None)
    operational_admission.add_argument("--max-models-per-provider", type=int, default=None)
    operational_admission.add_argument("--max-workers", type=int, default=4)
    operational_admission.add_argument("--failure-rate-threshold", type=float, default=0.25)
    operational_admission.add_argument("--min-successful-workloads", type=int, default=3)
    operational_admission.add_argument("--repetitions", type=int, default=1)
    operational_admission.add_argument("--redact-provider-identifiers", action="store_true")
    operational_admission.add_argument("--output", default=None)
    operational_admission.set_defaults(func=cmd_operational_admission)

    enrollment = sub.add_parser(
        "enroll-providers",
        help="Discover, probe, and operationally calibrate configured remote provider channels.",
    )
    enrollment.add_argument(
        "--config-file",
        default=None,
        help="Non-secret channel manifest; endpoints and keys are supplied through its env-var references.",
    )
    enrollment.add_argument("--provider", action="append", default=[])
    enrollment.add_argument("--timeout", type=float, default=60.0)
    enrollment.add_argument("--max-models", type=int, default=None)
    enrollment.add_argument("--max-models-per-provider", type=int, default=None)
    enrollment.add_argument("--tool-probe-timeout", type=float, default=None)
    enrollment.add_argument("--tool-probe-max-models", type=int, default=None)
    enrollment.add_argument("--tool-probe-max-models-per-provider", type=int, default=None)
    enrollment.add_argument("--max-workers", type=int, default=4)
    enrollment.add_argument("--min-available-models", type=int, default=1)
    enrollment.add_argument("--include-unavailable", action="store_true")
    enrollment.add_argument("--no-tool-calibration", action="store_true")
    enrollment.add_argument("--redact-provider-identifiers", action="store_true")
    enrollment.add_argument("--live", action="store_true")
    enrollment.add_argument("--output-dir", required=True)
    enrollment.set_defaults(func=cmd_enroll_providers)

    pre_fusion = sub.add_parser(
        "pre-fusion-screen",
        help=(
            "Research-rank configured logical models, live-probe streaming latency, "
            "and generate the serving registry consumed by Fusion."
        ),
    )
    # ``--registry`` is also a global option. Suppress the subparser default so
    # either ``--registry path pre-fusion-screen`` or the more natural
    # ``pre-fusion-screen --registry path`` keeps the supplied value.
    pre_fusion.add_argument("--registry", dest="registry", default=argparse.SUPPRESS)
    pre_fusion.add_argument("--focus-manifest", default=None)
    pre_fusion.add_argument("--source-manifest", default=None)
    pre_fusion.add_argument("--research-agent-config", default=None)
    pre_fusion.add_argument(
        "--research-output",
        default=None,
        help="Optional previously captured strict research JSON for offline validation only.",
    )
    pre_fusion.add_argument("--live", action="store_true")
    pre_fusion.add_argument(
        "--discovery-timeout",
        type=float,
        default=15.0,
        help="Per-channel /models discovery timeout in seconds.",
    )
    pre_fusion.add_argument("--timeout", type=float, default=90.0)
    pre_fusion.add_argument("--source-timeout", type=float, default=15.0)
    pre_fusion.add_argument("--max-workers", type=int, default=4)
    pre_fusion.add_argument("--max-models", type=int, default=None)
    pre_fusion.add_argument(
        "--stream-probe-samples",
        type=int,
        default=3,
        help="Independent strict stream samples required per physical profile.",
    )
    pre_fusion.add_argument(
        "--research-batch-size",
        type=int,
        default=None,
        help="Logical candidates per remote research-agent request.",
    )
    pre_fusion.add_argument(
        "--research-max-workers",
        type=int,
        default=None,
        help="Bounded concurrent research-agent batch requests.",
    )
    pre_fusion.add_argument("--min-available-models", type=int, default=3)
    pre_fusion.add_argument("--output", default=None)
    pre_fusion.add_argument(
        "--registry-output",
        default=None,
        help="Private loadable registry path; it is written only from eligible live profiles.",
    )
    pre_fusion.add_argument("--redact-provider-identifiers", action="store_true")
    pre_fusion.set_defaults(func=cmd_pre_fusion_screen)

    available_models = sub.add_parser(
        "generate-available-models",
        help=(
            "Generate the complete capability ranking and the strict-streaming, "
            "90-second latency-filtered model set consumed by Fusion."
        ),
    )
    available_models.add_argument(
        "--registry", dest="registry", default=argparse.SUPPRESS
    )
    available_models.add_argument("--focus-manifest", default=None)
    available_models.add_argument("--source-manifest", default=None)
    available_models.add_argument("--research-agent-config", default=None)
    available_models.add_argument("--research-output", default=None)
    available_models.add_argument("--live", action="store_true")
    available_models.add_argument("--discovery-timeout", type=float, default=15.0)
    available_models.add_argument("--timeout", type=float, default=90.0)
    available_models.add_argument("--source-timeout", type=float, default=15.0)
    available_models.add_argument("--max-workers", type=int, default=4)
    available_models.add_argument("--max-models", type=int, default=None)
    available_models.add_argument("--stream-probe-samples", type=int, default=3)
    available_models.add_argument("--research-batch-size", type=int, default=None)
    available_models.add_argument("--research-max-workers", type=int, default=None)
    available_models.add_argument("--min-available-models", type=int, default=3)
    available_models.add_argument(
        "--output",
        default=None,
        help="Private control-plane artifact containing rankings, handoff, and validation receipts.",
    )
    available_models.add_argument(
        "--registry-output",
        default=None,
        help="Private registry path to publish only after the complete handoff validates.",
    )
    available_models.add_argument(
        "--handoff-output",
        default=None,
        help=(
            "Optional private generation handoff path written together with the "
            "published registry."
        ),
    )
    available_models.add_argument("--redact-provider-identifiers", action="store_true")
    available_models.set_defaults(func=cmd_generate_available_models)

    redact_tool_probe = sub.add_parser("redact-tool-probe")
    redact_tool_probe.add_argument("--probe-file", required=True)
    redact_tool_probe.add_argument("--output", required=True)
    redact_tool_probe.set_defaults(func=cmd_redact_tool_probe)

    redact_probe = sub.add_parser("redact-provider-probe")
    redact_probe.add_argument("--probe-file", required=True)
    redact_probe.add_argument("--output", required=True)
    redact_probe.set_defaults(func=cmd_redact_provider_probe)

    registry_from_probe = sub.add_parser("registry-from-probe")
    registry_from_probe.add_argument("--probe-file", action="append", required=True)
    registry_from_probe.add_argument("--include-unavailable", action="store_true")
    registry_from_probe.add_argument("--min-available-models", type=int, default=1)
    registry_from_probe.add_argument("--redact-provider-identifiers", action="store_true")
    registry_from_probe.add_argument("--output", required=True)
    registry_from_probe.set_defaults(func=cmd_registry_from_probe)

    portfolio = sub.add_parser("provider-portfolio-audit")
    portfolio.add_argument("--min-provider-baselines", type=int, default=3)
    portfolio.add_argument("--min-provider-count", type=int, default=2)
    portfolio.add_argument("--min-api-format-count", type=int, default=2)
    portfolio.add_argument("--output", default=None)
    portfolio.set_defaults(func=cmd_provider_portfolio_audit)

    provider_adapter = sub.add_parser("provider-input-adapter-self-test")
    provider_adapter.add_argument("--prompt", default=None)
    provider_adapter.add_argument("--system", default=None)
    provider_adapter.add_argument("--output", default=None)
    provider_adapter.set_defaults(func=cmd_provider_input_adapter_self_test)

    execution_boundary = sub.add_parser("remote-api-execution-audit")
    execution_boundary.add_argument("--output", default=None)
    execution_boundary.set_defaults(func=cmd_remote_api_execution_audit)

    external_ranking_template = sub.add_parser("benchmark-external-ranking-template")
    external_ranking_template.add_argument(
        "--output",
        required=True,
        help="Private operator template. It lists only live-probed profile hashes and never ranks providers automatically.",
    )
    external_ranking_template.set_defaults(func=cmd_benchmark_external_ranking_template)

    screening_plan = sub.add_parser("baseline-screening-plan")
    screening_plan.add_argument("--source-manifest", required=True)
    screening_plan.add_argument(
        "--private-probe-file",
        action="append",
        required=True,
    )
    screening_plan.add_argument("--min-cases-per-source", type=int, default=100)
    screening_plan.add_argument("--output", required=True)
    screening_plan.set_defaults(func=cmd_baseline_screening_plan)

    screening_run = sub.add_parser("baseline-screening-run")
    screening_run.add_argument("--plan", required=True)
    screening_run.add_argument("--source-manifest", required=True)
    screening_run.add_argument(
        "--private-probe-file",
        action="append",
        required=True,
    )
    screening_run.add_argument("--private-root", required=True)
    screening_run.add_argument("--state-output", required=True)
    screening_run.add_argument("--live", action="store_true")
    screening_run.add_argument("--max-workers", type=int, default=4)
    screening_run.add_argument("--max-tasks", type=int, default=None)
    screening_run.add_argument("--retry-failed", action="store_true")
    screening_run.add_argument("--output", default=None)
    screening_run.set_defaults(func=cmd_baseline_screening_run)

    screening_ranking = sub.add_parser("baseline-screening-to-ranking")
    screening_ranking.add_argument("--plan", required=True)
    screening_ranking.add_argument("--campaign-state", required=True)
    screening_ranking.add_argument("--source-manifest", required=True)
    screening_ranking.add_argument("--private-root", required=True)
    screening_ranking.add_argument(
        "--private-probe-file",
        action="append",
        required=True,
    )
    screening_ranking.add_argument("--output", required=True)
    screening_ranking.set_defaults(func=cmd_baseline_screening_to_ranking)

    baseline_freeze = sub.add_parser("benchmark-provider-baseline-freeze")
    baseline_freeze.add_argument("--max-provider-baselines", type=int, default=3)
    baseline_freeze.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; it cannot support a final superiority claim without external top-three pre-registration.",
    )
    baseline_freeze.add_argument("--no-provider-baselines", action="store_true")
    baseline_freeze.add_argument("--min-provider-baselines", type=int, default=3)
    baseline_freeze.add_argument("--provider-probe-evidence-audit", default=None)
    baseline_freeze.add_argument(
        "--external-ranking-manifest",
        default=None,
        help="Private pre-registration input with hash aliases and external-source evidence; it is never copied to safe output.",
    )
    baseline_freeze.add_argument("--output", default=None)
    baseline_freeze.set_defaults(func=cmd_benchmark_provider_baseline_freeze)

    probe_evidence = sub.add_parser("provider-probe-evidence-audit")
    probe_evidence.add_argument("--private-probe-file", action="append", required=True)
    probe_evidence.add_argument("--private-registry-file", required=True)
    probe_evidence.add_argument("--redacted-probe-file", required=True)
    probe_evidence.add_argument("--redacted-registry-evidence-file", required=True)
    probe_evidence.add_argument("--min-available-models", type=int, default=3)
    probe_evidence.add_argument("--output", default=None)
    probe_evidence.set_defaults(func=cmd_provider_probe_evidence_audit)

    benchmarks = sub.add_parser("benchmarks")
    benchmarks.set_defaults(func=cmd_benchmarks)

    methodology = sub.add_parser("benchmark-methodology")
    methodology.add_argument("--output", default=None)
    methodology.set_defaults(func=cmd_benchmark_methodology)

    template = sub.add_parser("benchmark-dataset-template")
    template.add_argument("--base-dir", default="data/benchmarks")
    template.add_argument("--min-cases-per-suite", type=int, default=100)
    template.add_argument("--output", default=None)
    template.set_defaults(func=cmd_benchmark_dataset_template)

    source_template = sub.add_parser("benchmark-source-manifest-template")
    source_template.add_argument("--base-dir", default="data/benchmarks")
    source_template.add_argument("--import-dir", default="outputallresult/fusion_api_product/imports")
    source_template.add_argument("--min-cases-per-suite", type=int, default=100)
    source_template.add_argument("--output", default=None)
    source_template.set_defaults(func=cmd_benchmark_source_manifest_template)

    source_prepare = sub.add_parser("benchmark-source-manifest-prepare")
    source_prepare.add_argument("--template", required=True)
    source_prepare.add_argument("--case-hash-manifest", default=None)
    source_prepare.add_argument("--harness-pin-manifest", default=None)
    source_prepare.add_argument("--min-cases-per-suite", type=int, default=100)
    source_prepare.add_argument("--output", required=True)
    source_prepare.set_defaults(func=cmd_benchmark_source_manifest_prepare)

    source_validate = sub.add_parser("benchmark-source-manifest-validate")
    source_validate.add_argument("--source-manifest", required=True)
    source_validate.add_argument("--min-cases-per-suite", type=int, default=100)
    source_validate.add_argument("--output", default=None)
    source_validate.set_defaults(func=cmd_benchmark_source_manifest_validate)

    assemble = sub.add_parser("benchmark-assemble-manifest")
    assemble.add_argument("--template", default=None)
    assemble.add_argument("--dataset-dir", default=None)
    assemble.add_argument("--import-dir", action="append", default=[])
    assemble.add_argument("--min-cases-per-suite", type=int, default=100)
    assemble.add_argument("--output", required=True)
    assemble.set_defaults(func=cmd_benchmark_assemble_manifest)

    case_hash_manifest = sub.add_parser("benchmark-case-hash-manifest")
    case_hash_manifest.add_argument("--dataset-manifest", required=True)
    case_hash_manifest.add_argument("--candidate-id", action="append", default=[])
    case_hash_manifest.add_argument(
        "--official-case-source",
        action="append",
        default=[],
        metavar="SUITE_ID=PRIVATE_SOURCE_PATH",
        help="Bind an official source's stable case identifiers before model generation; paths remain hash-only in output.",
    )
    case_hash_manifest.add_argument("--min-cases-per-suite", type=int, default=100)
    case_hash_manifest.add_argument("--output", default=None)
    case_hash_manifest.set_defaults(func=cmd_benchmark_case_hash_manifest)

    bind_source_manifest = sub.add_parser("benchmark-source-manifest-bind-case-hashes")
    bind_source_manifest.add_argument("--source-manifest", required=True)
    bind_source_manifest.add_argument("--case-hash-manifest", required=True)
    bind_source_manifest.add_argument("--min-cases-per-suite", type=int, default=100)
    bind_source_manifest.add_argument("--output", default=None)
    bind_source_manifest.set_defaults(func=cmd_benchmark_source_manifest_bind_case_hashes)

    materialization_status = sub.add_parser("benchmark-materialization-status")
    materialization_status.add_argument("--raw-root", default="/mnt/storage/axio_fusion_benchmarks/raw")
    materialization_status.add_argument("--output-dir", default="/mnt/storage/axio_fusion_benchmarks/standardized")
    materialization_status.add_argument(
        "--download-manifest",
        default=GPQA_DEFAULT_DOWNLOAD_MANIFEST,
    )
    materialization_status.add_argument("--suite-id", action="append", default=[])
    materialization_status.add_argument("--min-cases-per-suite", type=int, default=100)
    materialization_status.add_argument("--output", default=None)
    materialization_status.set_defaults(func=cmd_benchmark_materialization_status)

    materialize = sub.add_parser("benchmark-materialize-datasets")
    materialize.add_argument("--raw-root", default="/mnt/storage/axio_fusion_benchmarks/raw")
    materialize.add_argument("--output-dir", default="/mnt/storage/axio_fusion_benchmarks/standardized")
    materialize.add_argument(
        "--download-manifest",
        default=GPQA_DEFAULT_DOWNLOAD_MANIFEST,
    )
    materialize.add_argument("--suite-id", action="append", default=[])
    materialize.add_argument("--limit-per-suite", type=int, default=None)
    materialize.add_argument("--min-cases-per-suite", type=int, default=100)
    materialize.add_argument("--overwrite", action="store_true")
    materialize.add_argument("--output", default=None)
    materialize.set_defaults(func=cmd_benchmark_materialize_datasets)

    gpqa_acquire = sub.add_parser("benchmark-acquire-gpqa-diamond")
    gpqa_acquire.add_argument(
        "--accept-no-example-leakage-terms",
        action="store_true",
        help=(
            "Confirm that the operator accepted the upstream gated terms and "
            "will not publicly disclose benchmark examples."
        ),
    )
    gpqa_acquire.add_argument("--destination", default=GPQA_DEFAULT_DESTINATION)
    gpqa_acquire.add_argument(
        "--download-manifest",
        default=GPQA_DEFAULT_DOWNLOAD_MANIFEST,
    )
    gpqa_acquire.add_argument("--timeout-seconds", type=float, default=90.0)
    gpqa_acquire.add_argument("--output", default=None)
    gpqa_acquire.set_defaults(func=cmd_benchmark_acquire_gpqa_diamond)

    matrix = sub.add_parser("benchmark-matrix")
    matrix.add_argument("--suite-id", action="append", default=None)
    matrix.add_argument("--candidate-id", action="append", default=[])
    matrix.add_argument("--max-provider-baselines", type=int, default=3)
    matrix.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    matrix.add_argument("--no-provider-baselines", action="store_true")
    matrix.add_argument("--provider-baseline-freeze", default=None)
    matrix.add_argument("--output", default=None)
    matrix.set_defaults(func=cmd_benchmark_matrix)

    acquisition = sub.add_parser("benchmark-acquisition-checklist")
    acquisition.add_argument("--dataset-manifest", default=None)
    acquisition.add_argument("--base-dir", default="data/benchmarks")
    acquisition.add_argument("--import-dir", default="outputallresult/fusion_api_product/imports")
    acquisition.add_argument("--candidate-id", action="append", default=[])
    acquisition.add_argument("--max-provider-baselines", type=int, default=3)
    acquisition.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    acquisition.add_argument("--no-provider-baselines", action="store_true")
    acquisition.add_argument("--provider-baseline-freeze", default=None)
    acquisition.add_argument("--min-cases-per-suite", type=int, default=100)
    acquisition.add_argument("--output", default=None)
    acquisition.set_defaults(func=cmd_benchmark_acquisition_checklist)

    acquisition_status = sub.add_parser("benchmark-acquisition-status")
    acquisition_status.add_argument("--dataset-dir", default="data/benchmarks")
    acquisition_status.add_argument("--import-dir", action="append", default=[])
    acquisition_status.add_argument("--candidate-id", action="append", default=[])
    acquisition_status.add_argument("--max-provider-baselines", type=int, default=3)
    acquisition_status.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    acquisition_status.add_argument("--no-provider-baselines", action="store_true")
    acquisition_status.add_argument("--provider-baseline-freeze", default=None)
    acquisition_status.add_argument("--min-cases-per-suite", type=int, default=100)
    acquisition_status.add_argument("--output", default=None)
    acquisition_status.set_defaults(func=cmd_benchmark_acquisition_status)

    run = sub.add_parser("benchmark-run")
    run.add_argument("--suite-id", required=True)
    run.add_argument("--dataset", required=True)
    run.add_argument("--candidate-id", default="axio-pro")
    run.add_argument("--task-format", default="auto")
    run.add_argument("--api-format", default="")
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--live", action="store_true")
    run.add_argument("--axio-gateway-url", default=None)
    run.add_argument("--code-timeout-seconds", type=float, default=5.0)
    run.add_argument("--output", default=None)
    run.set_defaults(func=cmd_benchmark_run)

    validate = sub.add_parser("benchmark-validate-dataset")
    validate.add_argument("--suite-id", required=True)
    validate.add_argument("--dataset", required=True)
    validate.add_argument("--task-format", default="auto")
    validate.add_argument("--max-rows", type=int, default=None)
    validate.add_argument("--output", default=None)
    validate.set_defaults(func=cmd_benchmark_validate_dataset)

    import_run = sub.add_parser("benchmark-import-official-run")
    import_run.add_argument("--suite-id", required=True)
    import_run.add_argument("--candidate-id", required=True)
    import_run.add_argument("--source", required=True)
    import_run.add_argument("--task-format", default="auto")
    import_run.add_argument("--api-format", default="")
    import_run.add_argument("--harness-name", required=True)
    import_run.add_argument("--harness-version", required=True)
    import_run.add_argument("--dataset-snapshot", required=True)
    import_run.add_argument("--evaluator-config", required=True)
    import_run.add_argument("--prompt-protocol", default="")
    import_run.add_argument("--decoding-config", default="")
    import_run.add_argument("--position-balanced", action="store_true")
    import_run.add_argument("--output", required=True)
    import_run.set_defaults(func=cmd_benchmark_import_official_run)

    import_batch = sub.add_parser("benchmark-import-official-batch")
    import_batch.add_argument("--batch-file", required=True)
    import_batch.add_argument("--output-dir", required=True)
    import_batch.add_argument("--harness-name", default="")
    import_batch.add_argument("--harness-version", default="")
    import_batch.add_argument("--dataset-snapshot", default="")
    import_batch.add_argument("--evaluator-config", default="")
    import_batch.add_argument("--prompt-protocol", default="")
    import_batch.add_argument("--decoding-config", default="")
    import_batch.add_argument("--output", default=None)
    import_batch.set_defaults(func=cmd_benchmark_import_official_batch)

    import_batch_template = sub.add_parser("benchmark-import-batch-template")
    import_batch_template.add_argument("--acquisition-checklist", required=True)
    import_batch_template.add_argument("--source-root-placeholder", default="<OFFICIAL_HARNESS_OUTPUT_DIR>")
    import_batch_template.add_argument("--safe-import-dir-placeholder", default="<SAFE_OFFICIAL_IMPORT_DIR>")
    import_batch_template.add_argument("--harness-pin-manifest", default=None)
    import_batch_template.add_argument("--output", required=True)
    import_batch_template.set_defaults(func=cmd_benchmark_import_batch_template)

    harness_execution_plan = sub.add_parser("benchmark-official-harness-execution-plan")
    harness_execution_plan.add_argument("--import-batch-template", required=True)
    harness_execution_plan.add_argument("--acquisition-status", default=None)
    harness_execution_plan.add_argument("--harness-pin-manifest", default=None)
    harness_execution_plan.add_argument("--output", required=True)
    harness_execution_plan.set_defaults(func=cmd_benchmark_official_harness_execution_plan)

    harness_preflight = sub.add_parser("benchmark-official-harness-preflight")
    harness_preflight.add_argument(
        "--suite-id",
        required=True,
        choices=("livecodebench", "humaneval", "ifeval", "bfcl", "tau_bench", "mt_bench_work"),
    )
    harness_preflight.add_argument("--dataset", required=True)
    harness_preflight.add_argument("--harness-root", required=True)
    harness_preflight.add_argument("--private-run-dir", required=True)
    harness_preflight.add_argument("--candidate-id", default="axio-pro")
    harness_preflight.add_argument("--api-format", default="chat/completions")
    harness_preflight.add_argument("--provider-baseline-freeze-manifest", default=None)
    harness_preflight.add_argument("--harness-pin-manifest", required=True)
    harness_preflight.add_argument("--axio-gateway-url", default=None)
    harness_preflight.add_argument("--limit", type=int, default=None)
    harness_preflight.add_argument("--max-output-tokens", type=int, default=None)
    harness_preflight.add_argument("--tau-user-model", default=None)
    harness_preflight.add_argument("--tau-user-provider", default=None)
    harness_preflight.add_argument("--tau-user-strategy", default="llm")
    harness_preflight.add_argument("--tau-environment", action="append", default=[])
    harness_preflight.add_argument("--tau-max-steps", type=int, default=30)
    harness_preflight.add_argument("--tau-python-executable", default=None)
    harness_preflight.add_argument("--mt-comparison-candidate-id", default=None)
    harness_preflight.add_argument("--mt-judge-candidate-id", default=None)
    harness_preflight.add_argument("--mt-judge-registry", default=None)
    harness_preflight.add_argument("--mt-judge-max-output-tokens", type=int, default=2048)
    harness_preflight.add_argument("--output", required=True)
    harness_preflight.set_defaults(func=cmd_benchmark_official_harness_preflight)

    harness_generate = sub.add_parser("benchmark-official-harness-generate")
    harness_generate.add_argument(
        "--suite-id",
        required=True,
        choices=("livecodebench", "humaneval", "ifeval", "bfcl", "tau_bench", "mt_bench_work"),
    )
    harness_generate.add_argument("--dataset", required=True)
    harness_generate.add_argument("--harness-root", required=True)
    harness_generate.add_argument("--private-run-dir", required=True)
    harness_generate.add_argument("--candidate-id", default="axio-pro")
    harness_generate.add_argument("--api-format", default="chat/completions")
    harness_generate.add_argument("--provider-baseline-freeze-manifest", default=None)
    harness_generate.add_argument("--harness-pin-manifest", required=True)
    harness_generate.add_argument("--axio-gateway-url", default=None)
    harness_generate.add_argument("--limit", type=int, default=None)
    harness_generate.add_argument("--max-output-tokens", type=int, default=None)
    harness_generate.add_argument("--tau-user-model", default=None)
    harness_generate.add_argument("--tau-user-provider", default=None)
    harness_generate.add_argument("--tau-user-strategy", default="llm")
    harness_generate.add_argument("--tau-environment", action="append", default=[])
    harness_generate.add_argument("--tau-max-steps", type=int, default=30)
    harness_generate.add_argument("--tau-python-executable", default=None)
    harness_generate.add_argument("--mt-comparison-candidate-id", default=None)
    harness_generate.add_argument("--mt-judge-candidate-id", default=None)
    harness_generate.add_argument("--mt-judge-registry", default=None)
    harness_generate.add_argument("--mt-judge-max-output-tokens", type=int, default=2048)
    harness_generate.add_argument("--live", action="store_true")
    harness_generate.add_argument("--output", required=True)
    harness_generate.set_defaults(func=cmd_benchmark_official_harness_generate)

    harness_evaluate = sub.add_parser("benchmark-official-harness-evaluate")
    harness_evaluate.add_argument(
        "--suite-id",
        required=True,
        choices=("livecodebench", "humaneval", "ifeval", "bfcl", "tau_bench", "mt_bench_work"),
    )
    harness_evaluate.add_argument("--dataset", required=True)
    harness_evaluate.add_argument("--harness-root", required=True)
    harness_evaluate.add_argument("--private-run-dir", required=True)
    harness_evaluate.add_argument("--candidate-id", default="axio-pro")
    harness_evaluate.add_argument("--api-format", default="chat/completions")
    harness_evaluate.add_argument("--provider-baseline-freeze-manifest", default=None)
    harness_evaluate.add_argument("--harness-pin-manifest", required=True)
    harness_evaluate.add_argument("--axio-gateway-url", default=None)
    harness_evaluate.add_argument("--allow-unsafe-code-execution", action="store_true")
    harness_evaluate.add_argument("--python-executable", default=None)
    harness_evaluate.add_argument("--worker-count", type=int, default=4)
    harness_evaluate.add_argument("--timeout-seconds", type=float, default=3.0)
    harness_evaluate.add_argument("--limit", type=int, default=None)
    harness_evaluate.add_argument("--max-output-tokens", type=int, default=None)
    harness_evaluate.add_argument("--tau-user-model", default=None)
    harness_evaluate.add_argument("--tau-user-provider", default=None)
    harness_evaluate.add_argument("--tau-user-strategy", default="llm")
    harness_evaluate.add_argument("--tau-environment", action="append", default=[])
    harness_evaluate.add_argument("--tau-max-steps", type=int, default=30)
    harness_evaluate.add_argument("--tau-python-executable", default=None)
    harness_evaluate.add_argument("--mt-comparison-candidate-id", default=None)
    harness_evaluate.add_argument("--mt-judge-candidate-id", default=None)
    harness_evaluate.add_argument("--mt-judge-registry", default=None)
    harness_evaluate.add_argument("--mt-judge-max-output-tokens", type=int, default=2048)
    harness_evaluate.add_argument("--live", action="store_true")
    harness_evaluate.add_argument("--output", required=True)
    harness_evaluate.set_defaults(func=cmd_benchmark_official_harness_evaluate)

    harness_import = sub.add_parser("benchmark-official-harness-import")
    harness_import.add_argument("--private-run-dir", required=True)
    harness_import.add_argument("--mt-side", choices=("target", "comparison"), default="target")
    harness_import.add_argument("--output", required=True)
    harness_import.set_defaults(func=cmd_benchmark_official_harness_import)

    harness_campaign = sub.add_parser("benchmark-official-harness-campaign")
    harness_campaign.add_argument("--execution-plan", required=True)
    harness_campaign.add_argument(
        "--suite-config",
        required=True,
        help="Private JSON with per-suite dataset/harness paths and optional simulator settings.",
    )
    harness_campaign.add_argument("--provider-baseline-freeze-manifest", required=True)
    harness_campaign.add_argument("--harness-pin-manifest", required=True)
    harness_campaign.add_argument("--private-root", required=True)
    harness_campaign.add_argument("--safe-import-root", required=True)
    harness_campaign.add_argument("--suite-id", action="append", default=[])
    harness_campaign.add_argument("--execution-task-id", action="append", default=[])
    harness_campaign.add_argument("--candidate-hash", action="append", default=[])
    harness_campaign.add_argument("--max-tasks", type=int, default=None)
    harness_campaign.add_argument("--limit", type=int, default=None)
    harness_campaign.add_argument("--live", action="store_true")
    harness_campaign.add_argument("--retry-failed", action="store_true")
    harness_campaign.add_argument("--overwrite", action="store_true")
    harness_campaign.add_argument("--allow-unsafe-code-execution", action="store_true")
    harness_campaign.add_argument("--output", required=True)
    harness_campaign.set_defaults(func=cmd_benchmark_official_harness_campaign)

    official_import_audit = sub.add_parser("benchmark-official-import-audit")
    official_import_audit.add_argument("--dataset-manifest", default=None)
    official_import_audit.add_argument("--source-manifest", default=None)
    official_import_audit.add_argument("--case-hash-manifest", default=None)
    official_import_audit.add_argument("--harness-pin-manifest", default=None)
    official_import_audit.add_argument("--import-dir", action="append", default=[])
    official_import_audit.add_argument("--run-file", action="append", default=[])
    official_import_audit.add_argument("--candidate-id", action="append", default=[])
    official_import_audit.add_argument("--max-provider-baselines", type=int, default=3)
    official_import_audit.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    official_import_audit.add_argument("--no-provider-baselines", action="store_true")
    official_import_audit.add_argument("--provider-baseline-freeze", default=None)
    official_import_audit.add_argument("--min-cases-per-suite", type=int, default=100)
    official_import_audit.add_argument("--output", required=True)
    official_import_audit.set_defaults(func=cmd_benchmark_official_import_audit)

    harness_pins = sub.add_parser("benchmark-harness-pin-manifest")
    harness_pins.add_argument("--harness-root", required=True)
    harness_pins.add_argument("--raw-root", required=True)
    harness_pins.add_argument("--bfcl-harness-root", default=None)
    harness_pins.add_argument("--output", required=True)
    harness_pins.set_defaults(func=cmd_benchmark_harness_pin_manifest)

    scorecard = sub.add_parser("benchmark-scorecard")
    scorecard.add_argument("--run-file", action="append", required=True)
    scorecard.add_argument("--provider-baseline-freeze", default=None)
    scorecard.add_argument("--require-http-gateway", action="store_true")
    scorecard.add_argument("--output", default=None)
    scorecard.set_defaults(func=cmd_benchmark_scorecard)

    surface_parity = sub.add_parser("benchmark-api-surface-parity")
    surface_parity.add_argument("--run-file", action="append", required=True)
    surface_parity.add_argument("--score-tolerance", type=float, default=0.02)
    surface_parity.add_argument("--require-http-gateway", action="store_true")
    surface_parity.add_argument("--output", default=None)
    surface_parity.set_defaults(func=cmd_benchmark_api_surface_parity)

    audit = sub.add_parser("benchmark-claim-audit")
    audit.add_argument("--run-file", action="append", required=True)
    audit.add_argument("--min-cases-per-suite", type=int, default=100)
    audit.add_argument("--alpha", type=float, default=0.05)
    audit.add_argument("--provider-baseline-freeze", default=None)
    audit.add_argument("--require-http-gateway", action="store_true")
    audit.add_argument("--output", default=None)
    audit.set_defaults(func=cmd_benchmark_claim_audit)

    failure = sub.add_parser("benchmark-fusion-failure-analysis")
    failure.add_argument("--scorecard-file", default=None)
    failure.add_argument("--claim-audit-file", default=None)
    failure.add_argument("--readiness-file", default=None)
    failure.add_argument("--trace-report-file", default=None)
    failure.add_argument("--output", default=None)
    failure.set_defaults(func=cmd_benchmark_fusion_failure_analysis)

    campaign = sub.add_parser("benchmark-campaign")
    campaign.add_argument("--dataset-manifest", required=True)
    campaign.add_argument("--output-dir", required=True)
    campaign.add_argument("--candidate-id", action="append", default=[])
    campaign.add_argument("--max-provider-baselines", type=int, default=3)
    campaign.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    campaign.add_argument("--no-provider-baselines", action="store_true")
    campaign.add_argument("--provider-probe-evidence-audit", default=None)
    campaign.add_argument("--provider-baseline-freeze", default=None)
    campaign.add_argument("--source-manifest", default=None)
    campaign.add_argument("--case-hash-manifest", default=None)
    campaign.add_argument("--official-import-audit", default=None)
    campaign.add_argument("--api-surface-protocol", default=None)
    campaign.add_argument("--provider-input-adapter", default=None)
    campaign.add_argument("--system-development-readiness", default=None)
    campaign.add_argument("--limit", type=int, default=None)
    campaign.add_argument("--live", action="store_true")
    campaign.add_argument("--axio-gateway-url", default=None)
    campaign.add_argument("--strict-live-preflight", action="store_true")
    campaign.add_argument("--no-resume", action="store_true")
    campaign.add_argument("--code-timeout-seconds", type=float, default=5.0)
    campaign.add_argument("--min-cases-per-suite", type=int, default=100)
    campaign.add_argument("--alpha", type=float, default=0.05)
    campaign.set_defaults(func=cmd_benchmark_campaign)

    campaign_progress = sub.add_parser("benchmark-campaign-progress-plan")
    campaign_progress.add_argument("--dataset-manifest", required=True)
    campaign_progress.add_argument("--output-dir", required=True)
    campaign_progress.add_argument("--candidate-id", action="append", default=[])
    campaign_progress.add_argument("--max-provider-baselines", type=int, default=3)
    campaign_progress.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    campaign_progress.add_argument("--no-provider-baselines", action="store_true")
    campaign_progress.add_argument("--provider-baseline-freeze", default=None)
    campaign_progress.add_argument("--min-cases-per-suite", type=int, default=100)
    campaign_progress.add_argument("--output", default=None)
    campaign_progress.set_defaults(func=cmd_benchmark_campaign_progress_plan)

    ready = sub.add_parser("benchmark-readiness")
    ready.add_argument("--dataset-manifest", required=True)
    ready.add_argument("--candidate-id", action="append", default=[])
    ready.add_argument("--max-provider-baselines", type=int, default=3)
    ready.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    ready.add_argument("--no-provider-baselines", action="store_true")
    ready.add_argument("--provider-baseline-freeze", default=None)
    ready.add_argument("--min-cases-per-suite", type=int, default=100)
    ready.add_argument("--output", default=None)
    ready.set_defaults(func=cmd_benchmark_readiness)

    live_ready = sub.add_parser("fusion-live-readiness")
    live_ready.add_argument(
        "--benchmark-manifest-dir",
        default="/mnt/storage/axio_fusion_benchmarks/manifests",
    )
    live_ready.add_argument("--materialization-status", default=None)
    live_ready.add_argument("--case-hash-manifest", default=None)
    live_ready.add_argument("--harness-pin-manifest", default=None)
    live_ready.add_argument("--source-manifest-validation", default=None)
    live_ready.add_argument("--import-batch-template", default=None)
    live_ready.add_argument("--official-harness-execution-plan", default=None)
    live_ready.add_argument("--official-import-audit", default=None)
    live_ready.add_argument("--acquisition-status", default=None)
    live_ready.add_argument("--provider-baseline-freeze", default=None)
    live_ready.add_argument("--provider-probe-evidence-audit", default=None)
    live_ready.add_argument("--output", default=None)
    live_ready.set_defaults(func=cmd_fusion_live_readiness)

    live_runbook = sub.add_parser("fusion-live-runbook")
    live_runbook.add_argument("--benchmark-manifest-dir", default="/mnt/storage/axio_fusion_benchmarks/manifests")
    live_runbook.add_argument("--min-cases-per-suite", type=int, default=100)
    live_runbook.add_argument("--alpha", type=float, default=0.05)
    live_runbook.add_argument("--max-provider-baselines", type=int, default=3)
    live_runbook.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; the generated final runbook always requires external top-three pre-registration.",
    )
    live_runbook.add_argument("--no-provider-baselines", action="store_true")
    live_runbook.add_argument("--output", default=None)
    live_runbook.set_defaults(func=cmd_fusion_live_runbook)

    code_test = sub.add_parser("fusion-code-test-receipt")
    code_test.add_argument("--test-name", default="standalone_fusion_pytest")
    code_test.add_argument(
        "--command-template",
        default="PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q tests",
    )
    code_test.add_argument("--exit-code", type=int, required=True)
    code_test.add_argument("--passed-count", type=int, required=True)
    code_test.add_argument("--failed-count", type=int, default=0)
    code_test.add_argument("--skipped-count", type=int, default=0)
    code_test.add_argument("--deselected-count", type=int, default=0)
    code_test.add_argument("--duration-seconds", type=float, default=None)
    code_test.add_argument("--output", default=None)
    code_test.set_defaults(func=cmd_fusion_code_test_receipt)

    system_ready = sub.add_parser("fusion-system-readiness")
    system_ready.add_argument("--code-test-receipt", default=None)
    system_ready.add_argument("--api-surface-protocol", default=None)
    system_ready.add_argument("--provider-input-adapter", default=None)
    system_ready.add_argument("--live-runbook", default=None)
    system_ready.add_argument("--min-cases-per-suite", type=int, default=100)
    system_ready.add_argument("--alpha", type=float, default=0.05)
    system_ready.add_argument("--output", default=None)
    system_ready.set_defaults(func=cmd_fusion_system_development_readiness)

    final_audit = sub.add_parser("benchmark-final-audit")
    final_audit.add_argument("--campaign-dir", default=None)
    final_audit.add_argument("--campaign-file", default=None)
    final_audit.add_argument("--source-manifest", default=None)
    final_audit.add_argument("--case-hash-manifest", default=None)
    final_audit.add_argument("--runs-file", default=None)
    final_audit.add_argument("--scorecard-file", default=None)
    final_audit.add_argument("--claim-audit-file", default=None)
    final_audit.add_argument("--methodology-file", default=None)
    final_audit.add_argument("--provider-probe-evidence-audit", default=None)
    final_audit.add_argument("--provider-baseline-freeze", default=None)
    final_audit.add_argument("--official-import-audit", default=None)
    final_audit.add_argument("--api-surface-parity", default=None)
    final_audit.add_argument("--training-contamination-audit-file", default=None)
    final_audit.add_argument("--min-cases-per-suite", type=int, default=100)
    final_audit.add_argument("--alpha", type=float, default=0.05)
    final_audit.add_argument("--output", default=None)
    final_audit.set_defaults(func=cmd_benchmark_final_audit)

    evidence = sub.add_parser("benchmark-evidence-pack")
    evidence.add_argument("--source-manifest", default=None)
    evidence.add_argument("--case-hash-manifest", default=None)
    evidence.add_argument("--provider-probe-evidence-audit", default=None)
    evidence.add_argument("--provider-baseline-freeze", default=None)
    evidence.add_argument("--official-import-audit", default=None)
    evidence.add_argument("--api-surface-parity", default=None)
    evidence.add_argument("--dataset-manifest", default=None)
    evidence.add_argument("--campaign-dir", default=None)
    evidence.add_argument("--candidate-id", action="append", default=[])
    evidence.add_argument("--max-provider-baselines", type=int, default=3)
    evidence.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    evidence.add_argument("--no-provider-baselines", action="store_true")
    evidence.add_argument("--min-cases-per-suite", type=int, default=100)
    evidence.add_argument("--alpha", type=float, default=0.05)
    evidence.add_argument("--output", default=None)
    evidence.set_defaults(func=cmd_benchmark_evidence_pack)

    completion = sub.add_parser("fusion-completion-audit")
    completion.add_argument("--evidence-pack", default=None)
    completion.add_argument("--final-audit", default=None)
    completion.add_argument("--api-surface-protocol", default=None)
    completion.add_argument("--provider-input-adapter", default=None)
    completion.add_argument("--system-development-readiness", default=None)
    completion.add_argument("--live-runbook", default=None)
    completion.add_argument("--failure-analysis", default=None)
    completion.add_argument("--source-manifest", default=None)
    completion.add_argument("--case-hash-manifest", default=None)
    completion.add_argument("--provider-probe-evidence-audit", default=None)
    completion.add_argument("--provider-baseline-freeze", default=None)
    completion.add_argument("--official-import-audit", default=None)
    completion.add_argument("--api-surface-parity", default=None)
    completion.add_argument("--dataset-manifest", default=None)
    completion.add_argument("--campaign-dir", default=None)
    completion.add_argument("--candidate-id", action="append", default=[])
    completion.add_argument("--max-provider-baselines", type=int, default=3)
    completion.add_argument(
        "--all-provider-baselines",
        action="store_true",
        help="Diagnostic only; final claims require --provider-baseline-freeze from external top-three pre-registration.",
    )
    completion.add_argument("--no-provider-baselines", action="store_true")
    completion.add_argument("--min-cases-per-suite", type=int, default=100)
    completion.add_argument("--alpha", type=float, default=0.05)
    completion.add_argument("--output", default=None)
    completion.set_defaults(func=cmd_fusion_completion_audit)

    learning = sub.add_parser("learning-report")
    learning.add_argument("--feedback-file", action="append", default=[])
    learning.add_argument("--scorecard-file", action="append", default=[])
    learning.add_argument(
        "--allow-benchmark-diagnostics",
        action="store_true",
        help="Explicitly admit benchmark scorecards as diagnostic-only input; never enables router learning or registry updates.",
    )
    learning.add_argument("--min-examples", type=int, default=20)
    learning.add_argument("--output", default=None)
    learning.set_defaults(func=cmd_learning_report)

    training = sub.add_parser("orchestrator-training-dataset")
    training.add_argument("--feedback-file", action="append", default=[])
    training.add_argument("--trace-file", action="append", default=[])
    training.add_argument("--min-pair-score-delta", type=float, default=0.15)
    training.add_argument("--max-examples", type=int, default=None)
    training.add_argument("--output", default=None)
    training.set_defaults(func=cmd_orchestrator_training_dataset)

    shadow = sub.add_parser("router-policy-shadow-patch")
    shadow.add_argument("--feedback-file", action="append", default=[])
    shadow.add_argument("--trace-file", action="append", default=[])
    shadow.add_argument("--min-examples", type=int, default=20)
    shadow.add_argument("--output", default=None)
    shadow.set_defaults(func=cmd_router_policy_shadow_patch)

    policy_candidate = sub.add_parser("routing-policy-candidate")
    policy_candidate.add_argument("--shadow-patch", required=True)
    policy_candidate.add_argument("--min-examples", type=int, default=20)
    policy_candidate.add_argument("--created-on", default=None)
    policy_candidate.add_argument("--output", default=None)
    policy_candidate.set_defaults(func=cmd_routing_policy_candidate)

    policy_replay = sub.add_parser("routing-policy-shadow-replay")
    policy_replay.add_argument("--candidate", required=True)
    policy_replay.add_argument("--trace-file", action="append", default=[])
    policy_replay.add_argument("--feedback-file", action="append", default=[])
    policy_replay.add_argument("--max-cases", type=int, default=500)
    policy_replay.add_argument("--output", default=None)
    policy_replay.set_defaults(func=cmd_routing_policy_shadow_replay)

    policy_review = sub.add_parser("routing-policy-review")
    policy_review.add_argument("--candidate", required=True)
    policy_review.add_argument("--contamination-audit", required=True)
    policy_review.add_argument(
        "--approve",
        action="store_true",
        help="Explicit human approval; without it the review remains blocked.",
    )
    policy_review.add_argument("--reviewer-id", default="")
    policy_review.add_argument("--reviewed-on", default=None)
    policy_review.add_argument("--output", default=None)
    policy_review.set_defaults(func=cmd_routing_policy_review)

    policy_activate = sub.add_parser("routing-policy-activate")
    policy_activate.add_argument("--candidate", required=True)
    policy_activate.add_argument("--review", required=True)
    policy_activate.add_argument("--rollback-policy-digest", default="")
    policy_activate.add_argument("--activated-on", default=None)
    policy_activate.add_argument("--output", default=None)
    policy_activate.set_defaults(func=cmd_routing_policy_activate)

    policy_status = sub.add_parser("routing-policy-status")
    policy_status.add_argument("--policy", default=None)
    policy_status.add_argument("--output", default=None)
    policy_status.set_defaults(func=cmd_routing_policy_status)

    onboarding_candidate = sub.add_parser("provider-onboarding-candidate")
    onboarding_candidate.add_argument(
        "--candidate-profile-hash", action="append", required=True, default=[]
    )
    onboarding_candidate.add_argument("--probe-file", action="append", default=[])
    onboarding_candidate.add_argument("--calibration-file", action="append", default=[])
    onboarding_candidate.add_argument("--created-on", default=None)
    onboarding_candidate.add_argument("--output", default=None)
    onboarding_candidate.set_defaults(func=cmd_provider_onboarding_candidate)

    onboarding_review = sub.add_parser("provider-onboarding-review")
    onboarding_review.add_argument("--candidate", required=True)
    onboarding_review.add_argument("--approve", action="store_true")
    onboarding_review.add_argument("--reviewer-id", default="")
    onboarding_review.add_argument("--reviewed-on", default=None)
    onboarding_review.add_argument("--output", default=None)
    onboarding_review.set_defaults(func=cmd_provider_onboarding_review)

    onboarding_activate = sub.add_parser("provider-onboarding-activate")
    onboarding_activate.add_argument("--candidate", required=True)
    onboarding_activate.add_argument("--review", required=True)
    onboarding_activate.add_argument("--activated-on", default=None)
    onboarding_activate.add_argument("--output", default=None)
    onboarding_activate.set_defaults(func=cmd_provider_onboarding_activate)

    onboarding_apply = sub.add_parser("provider-onboarding-apply")
    onboarding_apply.add_argument("--candidate", required=True)
    onboarding_apply.add_argument("--review", required=True)
    onboarding_apply.add_argument("--source-registry", required=True)
    onboarding_apply.add_argument("--output-registry", required=True)
    onboarding_apply.add_argument("--output", default=None)
    onboarding_apply.set_defaults(func=cmd_provider_onboarding_apply)

    contamination = sub.add_parser("training-contamination-audit")
    contamination.add_argument("--benchmark-file", action="append", default=[])
    contamination.add_argument("--training-dataset-file", action="append", default=[])
    contamination.add_argument("--learning-report-file", action="append", default=[])
    contamination.add_argument("--calibration-file", action="append", default=[])
    contamination.add_argument("--feedback-file", action="append", default=[])
    contamination.add_argument("--trace-file", action="append", default=[])
    contamination.add_argument("--allow-aggregate-benchmark-calibration", action="store_true")
    contamination.add_argument("--output", default=None)
    contamination.set_defaults(func=cmd_training_contamination_audit)

    traces = sub.add_parser("trace-report")
    traces.add_argument("--trace-file", action="append", default=[])
    traces.add_argument("--output", default=None)
    traces.set_defaults(func=cmd_trace_report)

    calibrate = sub.add_parser("calibrate-registry")
    calibrate.add_argument("--probe-file", action="append", default=[])
    calibrate.add_argument("--benchmark-file", action="append", default=[])
    calibrate.add_argument("--feedback-file", action="append", default=[])
    calibrate.add_argument("--trace-file", action="append", default=[])
    calibrate.add_argument(
        "--allow-benchmark-calibration",
        action="store_true",
        help="Exploratory only; benchmark-derived registry updates require a separate holdout and contamination audit.",
    )
    calibrate.add_argument("--output", default=None)
    calibrate.add_argument("--updated-registry-output", default=None)
    calibrate.set_defaults(func=cmd_calibrate_registry)

    tool = sub.add_parser("tool-execute")
    tool.add_argument("--role", default="primary_solver")
    tool.add_argument("--call-json", action="append", default=[])
    tool.add_argument("--call-file", default=None)
    tool.add_argument("--tool-policy-file", default=None)
    tool.add_argument("--max-tool-calls", type=int, default=None)
    tool.add_argument("--output", default=None)
    tool.set_defaults(func=cmd_tool_execute)

    return parser


def cmd_serve(args: argparse.Namespace) -> int:
    dynamic_manifest_mode = bool(args.discover or args.enroll)
    if dynamic_manifest_mode and not args.provider_config_file:
        configured_path = os.getenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", "").strip()
        if not configured_path:
            raise SystemExit(
                "--discover/--enroll requires --provider-config-file or "
                "AXIO_FUSION_PROVIDER_CONFIG_FILE"
            )
    if args.enroll and not args.live:
        raise SystemExit("--enroll requires --live so provider probes cannot run accidentally in dry mode")
    if args.discover and not args.live:
        raise SystemExit("--discover requires --live because model discovery performs network requests")
    if args.discover and not args.enroll and not args.diagnostic_only:
        raise SystemExit(
            "--discover is inventory-only; use --enroll for production pre-Fusion admission "
            "or add --diagnostic-only for diagnostics"
        )
    if args.registry and dynamic_manifest_mode:
        raise SystemExit("--registry cannot be combined with --discover/--enroll")
    if args.registry and not dynamic_manifest_mode:
        os.environ["AXIO_FUSION_REGISTRY_PATH"] = str(args.registry)
    print(f"Serving standalone Axio Fusion API on http://{args.host}:{args.port}", file=sys.stderr)
    if not dynamic_manifest_mode:
        try:
            serve(host=args.host, port=args.port, live=args.live)
        except KeyboardInterrupt:
            return 0
        return 0

    manifest_path = args.provider_config_file or os.getenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", "").strip()
    manifest = _load_json_object(manifest_path)
    server = create_runtime_http_server(
        manifest,
        host=args.host,
        port=args.port,
        live=bool(args.live),
        discover=bool(args.discover and not args.enroll),
        enroll=bool(args.enroll),
        diagnostic_only=bool(args.diagnostic_only),
        discovery_timeout=args.discovery_timeout,
        enrollment_max_workers=args.enrollment_max_workers,
        enrollment_max_models=args.enrollment_max_models,
        enrollment_max_models_per_provider=args.enrollment_max_models_per_provider,
        enrollment_tool_probe_timeout=args.enrollment_tool_probe_timeout,
        enrollment_tool_probe_max_models=args.enrollment_tool_probe_max_models,
        enrollment_tool_probe_max_models_per_provider=args.enrollment_tool_probe_max_models_per_provider,
        enrollment_min_available_models=args.enrollment_min_available_models,
        enrollment_calibrate_tools=not bool(args.no_tool_calibration),
        require_prefusion=bool(args.enroll and not args.diagnostic_only),
        focus_manifest=args.prefusion_focus_manifest,
        source_manifest=args.prefusion_source_manifest,
        research_agent_config=args.prefusion_research_agent_config,
        research_output=args.prefusion_research_output,
        prefusion_max_models=args.prefusion_max_models,
        prefusion_research_batch_size=args.prefusion_research_batch_size,
        prefusion_research_max_workers=args.prefusion_research_max_workers,
        prefusion_stream_probe_samples=args.prefusion_stream_probe_samples,
    )
    receipt = getattr(server, "runtime_channel_enrollment_receipt", {})
    if args.enrollment_receipt_output and isinstance(receipt, dict):
        write_json(args.enrollment_receipt_output, receipt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    engine = FusionEngine(
        load_registry(args.registry, require_prefusion=bool(args.live))
    )
    request = canonicalize_payload(_request_payload_from_args(args), api_format=args.api_format)
    response = engine.complete(request, live=args.live)
    print(json.dumps(render_response(response, api_format=args.api_format), ensure_ascii=False, indent=2))
    return 0


def cmd_route_plan(args: argparse.Namespace) -> int:
    engine = FusionEngine(load_registry(args.registry))
    request = canonicalize_payload(_request_payload_from_args(args), api_format=args.api_format)
    print(json.dumps(engine.complete(request, live=False).route_plan, ensure_ascii=False, indent=2))
    return 0


def cmd_api_surface_protocol_self_test(args: argparse.Namespace) -> int:
    payload = build_api_surface_protocol_self_test(
        registry_path=args.registry,
        models=args.model,
        prompt=args.prompt,
        task_type=args.task_type,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_api_surface_live_smoke(args: argparse.Namespace) -> int:
    payload = build_api_surface_live_smoke(
        registry_path=args.registry,
        models=args.model,
        prompt=args.prompt,
        task_type=args.task_type,
        max_latency_ms=args.max_latency_ms,
        max_output_tokens=args.max_output_tokens,
        live=bool(args.live),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_api_surface_stream_live_smoke(args: argparse.Namespace) -> int:
    payload = build_api_surface_stream_live_smoke(
        registry_path=args.registry,
        models=args.model,
        prompt=args.prompt,
        task_type=args.task_type,
        max_latency_ms=args.max_latency_ms,
        max_output_tokens=args.max_output_tokens,
        live=bool(args.live),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fast_path_live_diagnostic(args: argparse.Namespace) -> int:
    payload = build_fast_path_live_diagnostic(
        registry_path=args.registry,
        api_format=args.api_format,
        prompt=args.prompt,
        task_type=args.task_type,
        max_latency_ms=args.max_latency_ms,
        max_output_tokens=args.max_output_tokens,
        live=bool(args.live),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fusion_deliberation_live_smoke(args: argparse.Namespace) -> int:
    payload = build_fusion_deliberation_live_smoke(
        registry_path=args.registry,
        models=args.model,
        prompt=args.prompt,
        task_type=args.task_type,
        max_latency_ms=args.max_latency_ms,
        max_output_tokens=args.max_output_tokens,
        max_total_model_calls=args.max_total_model_calls,
        max_cost_usd=args.max_cost_usd,
        live=bool(args.live),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    print(json.dumps(discover_provider_inventory(live=args.live, timeout=args.timeout), ensure_ascii=False, indent=2))
    return 0


def cmd_provider_config_summary(args: argparse.Namespace) -> int:
    configured_profiles = provider_configured_profiles_from_env()
    profiles = load_registry(args.registry)
    configuration_sources = provider_configuration_source_summary()
    provider_readiness = _fusion_provider_env_readiness(registry_path=args.registry)
    api_format_counts: dict[str, int] = {}
    provider_hashes = set()
    for profile in profiles:
        api_format = str(profile.api_format or "unknown")
        api_format_counts[api_format] = api_format_counts.get(api_format, 0) + 1
        provider_hashes.add(sha256_text(profile.provider))
    explicit_registry_argument = bool(str(args.registry or "").strip())
    explicit_registry_available = False
    if explicit_registry_argument:
        try:
            explicit_registry_available = Path(str(args.registry)).is_file()
        except OSError:
            explicit_registry_available = False
    environment_registry_configured = bool(
        os.getenv("AXIO_FUSION_REGISTRY_PATH", "").strip()
    )
    environment_registry_available = False
    if environment_registry_configured and not explicit_registry_argument:
        try:
            environment_registry_available = Path(
                os.getenv("AXIO_FUSION_REGISTRY_PATH", "")
            ).is_file()
        except OSError:
            environment_registry_available = False
    if explicit_registry_argument:
        runtime_registry_source = (
            "explicit_registry"
            if explicit_registry_available
            else "explicit_registry_unavailable"
        )
    elif environment_registry_configured:
        runtime_registry_source = (
            "environment_registry"
            if environment_registry_available
            else "environment_registry_unavailable"
        )
    elif any(str(profile.source or "") == "environment" for profile in profiles):
        runtime_registry_source = "environment_model_list"
    elif configured_profiles:
        runtime_registry_source = "provider_config_static_models"
    elif configuration_sources.get("config_source_present"):
        runtime_registry_source = "provider_config_requires_enrollment_or_explicit_registry"
    else:
        runtime_registry_source = "default_fallback_until_enrollment_or_registry_binding"
    payload = {
        "schema": "axio_fusion_api.provider_config_operator_summary.v1",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "network_calls_performed": False,
        "supported_provider_input_api_formats": ["chat", "responses", "anthropic", "gemini"],
        "configuration_sources": configuration_sources,
        "configured_static_profile_count": len(configured_profiles),
        "configured_static_profile_set_sha256": sha256_text(
            json.dumps(sorted(profile.profile_id for profile in configured_profiles), separators=(",", ":"))
        ),
        "runtime_registry_profile_count": len(profiles),
        "runtime_registry_provider_hash_count": len(provider_hashes),
        "runtime_registry_api_format_counts": dict(sorted(api_format_counts.items())),
        "runtime_registry_source": runtime_registry_source,
        "runtime_registry_explicit_argument": explicit_registry_argument,
        "runtime_registry_artifact_available": (
            explicit_registry_available
            if explicit_registry_argument
            else environment_registry_available
            if environment_registry_configured
            else None
        ),
        "runtime_registry_requires_enrollment": runtime_registry_source
        in {
            "provider_config_requires_enrollment_or_explicit_registry",
            "explicit_registry_unavailable",
            "environment_registry_unavailable",
        },
        "credential_ready": provider_readiness.get("credential_ready") is True,
        "credentialed_provider_count": int(provider_readiness.get("credentialed_provider_count") or 0),
        "credentialed_provider_profile_count": int(
            provider_readiness.get("credentialed_provider_profile_count") or 0
        ),
        "credentialed_configuration_channel_count": int(
            provider_readiness.get("credentialed_configuration_channel_count") or 0
        ),
        "config_credentialed_provider_profile_count": int(
            provider_readiness.get("config_credentialed_provider_profile_count") or 0
        ),
        "registry_credentialed_provider_profile_count": int(
            provider_readiness.get("registry_credentialed_provider_profile_count") or 0
        ),
        "credentialed_profile_count_accounting": dict(
            provider_readiness.get("credentialed_profile_count_accounting") or {}
        ),
        "credentialed_api_format_counts": dict(
            provider_readiness.get("credentialed_api_format_counts") or {}
        ),
        "live_probe_ready": bool(provider_readiness.get("credentialed_provider_count")),
        "live_probe_reason_codes": (
            []
            if provider_readiness.get("credentialed_provider_count")
            else ["provider_credentials_missing"]
        ),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_key_env_names_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }
    _emit_json(payload, output=args.output)
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    profiles = load_registry(args.registry)
    live = bool(args.live or os.getenv("AXIO_FUSION_PROBE_LIVE") == "1")
    if args.discover_live_models:
        _emit_json(
            probe_exposed_provider_models(
                providers=args.provider,
                timeout=args.timeout,
                live=live,
                max_models=args.max_models,
                max_models_per_provider=args.max_models_per_provider,
                profile_hashes=args.profile_hash,
                max_workers=args.max_workers,
                redact_provider_identifiers=bool(args.redact_provider_identifiers),
            ),
            output=args.output,
        )
    else:
        _emit_json(
            probe_provider_models(
                profiles,
                timeout=args.timeout,
                live=live,
                max_workers=args.max_workers,
                profile_hashes=args.profile_hash,
                max_models=args.max_models,
                max_models_per_provider=args.max_models_per_provider,
                redact_provider_identifiers=bool(args.redact_provider_identifiers),
            ),
            output=args.output,
        )
    return 0


def cmd_tool_probe(args: argparse.Namespace) -> int:
    profiles = load_registry(args.registry)
    live = bool(args.live or os.getenv("AXIO_FUSION_PROBE_LIVE") == "1")
    _emit_json(
        probe_provider_tool_support(
            profiles,
            timeout=args.timeout,
            live=live,
            max_workers=args.max_workers,
            profile_hashes=args.profile_hash,
            max_models=args.max_models,
            max_models_per_provider=args.max_models_per_provider,
            redact_provider_identifiers=bool(args.redact_provider_identifiers),
        ),
        output=args.output,
    )
    return 0


def cmd_operational_admission(args: argparse.Namespace) -> int:
    profiles = load_registry(args.registry)
    live = bool(args.live or os.getenv("AXIO_FUSION_PROBE_LIVE") == "1")
    payload = run_operational_admission(
        profiles,
        timeout=args.timeout,
        live=live,
        max_workers=args.max_workers,
        profile_hashes=args.profile_hash,
        max_models=args.max_models,
        max_models_per_provider=args.max_models_per_provider,
        failure_rate_threshold=args.failure_rate_threshold,
        min_successful_workloads=args.min_successful_workloads,
        repetitions=args.repetitions,
        redact_provider_identifiers=bool(args.redact_provider_identifiers),
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("status") == "ready" else 2


def cmd_enroll_providers(args: argparse.Namespace) -> int:
    # ``--provider-config-file`` is a global option so it can be shared by all
    # control-plane commands. Preserve it as the explicit source here instead
    # of relying only on the temporary environment bridge in ``main``.
    config_path = args.config_file or getattr(args, "provider_config_file", None)
    payload = enroll_provider_channels(
        config_path=config_path,
        output_dir=args.output_dir,
        providers=args.provider,
        live=bool(args.live or os.getenv("AXIO_FUSION_PROBE_LIVE") == "1"),
        timeout=args.timeout,
        max_workers=args.max_workers,
        max_models=args.max_models,
        max_models_per_provider=args.max_models_per_provider,
        min_available_models=args.min_available_models,
        include_unavailable=bool(args.include_unavailable),
        calibrate_tools=not bool(args.no_tool_calibration),
        tool_probe_timeout=args.tool_probe_timeout,
        tool_probe_max_models=args.tool_probe_max_models,
        tool_probe_max_models_per_provider=args.tool_probe_max_models_per_provider,
        redact_provider_identifiers=bool(args.redact_provider_identifiers),
    )
    _emit_json(payload)
    return 0 if payload.get("status") == "ready" else 2


def cmd_pre_fusion_screen(args: argparse.Namespace) -> int:
    """Run the pre-Fusion control-plane workflow and bind its registry."""

    configured_provider_manifest = (
        getattr(args, "provider_config_file", None)
        or os.getenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", "").strip()
    )
    if args.registry and configured_provider_manifest:
        raise SystemExit(
            "pre-fusion-screen cannot combine --registry with a provider "
            "manifest; complete /models discovery would be bypassed"
        )

    try:
        payload = run_prefusion_model_screening(
            registry_path=args.registry,
            focus_manifest=args.focus_manifest,
            source_manifest=args.source_manifest,
            research_agent_config=args.research_agent_config,
            research_output=args.research_output,
            live=bool(args.live),
            discovery_timeout=args.discovery_timeout,
            timeout=args.timeout,
            source_timeout=args.source_timeout,
            max_workers=args.max_workers,
            max_models=args.max_models,
            min_available_models=args.min_available_models,
            research_batch_size=args.research_batch_size,
            research_max_workers=args.research_max_workers,
            stream_probe_samples=args.stream_probe_samples,
            redact_provider_identifiers=bool(args.redact_provider_identifiers),
        )
    except ModelScreeningError as exc:
        payload = {
            "schema": "axio_fusion_api.pre_fusion_model_screening.v1",
            "status": "blocked",
            "blockers": [exc.code],
            "secrets_persisted": False,
            "raw_source_content_persisted": False,
            "raw_research_prompt_persisted": False,
            "raw_research_output_persisted": False,
            "raw_provider_output_persisted": False,
        }
        _emit_json(payload, output=args.output)
        return 2

    if args.registry_output and payload.get("status") == "ready":
        if args.redact_provider_identifiers:
            raise SystemExit(
                "--registry-output cannot be combined with --redact-provider-identifiers; "
                "a serving registry requires private model aliases."
            )
        _write_json_atomic(args.registry_output, payload.get("fusion_registry") or {})
        handoff = payload.get("fusion_handoff")
        if isinstance(handoff, dict):
            handoff["registry_artifact_published"] = True
    elif args.registry_output:
        # A failed screening run must never replace a previously active
        # registry with an empty/blocked intermediate artifact.
        handoff = payload.get("fusion_handoff")
        if isinstance(handoff, dict):
            handoff["registry_artifact_published"] = False
    _emit_json(payload, output=args.output)
    return 0 if payload.get("status") == "ready" else 2


def cmd_generate_available_models(args: argparse.Namespace) -> int:
    """Publish the explicit model-generation handoff used by Fusion."""

    configured_provider_manifest = (
        getattr(args, "provider_config_file", None)
        or os.getenv("AXIO_FUSION_PROVIDER_CONFIG_FILE", "").strip()
    )
    if args.registry and configured_provider_manifest:
        raise SystemExit(
            "generate-available-models cannot combine --registry with a provider "
            "manifest; complete /models discovery would be bypassed"
        )
    if args.registry_output and args.redact_provider_identifiers:
        raise SystemExit(
            "--registry-output cannot be combined with --redact-provider-identifiers"
        )
    if args.handoff_output and not args.registry_output:
        raise SystemExit("--handoff-output requires --registry-output")
    try:
        payload = generate_available_model_set(
            registry_path=args.registry,
            focus_manifest=args.focus_manifest,
            source_manifest=args.source_manifest,
            research_agent_config=args.research_agent_config,
            research_output=args.research_output,
            live=bool(args.live),
            discovery_timeout=args.discovery_timeout,
            timeout=args.timeout,
            source_timeout=args.source_timeout,
            max_workers=args.max_workers,
            max_models=args.max_models,
            min_available_models=args.min_available_models,
            research_batch_size=args.research_batch_size,
            research_max_workers=args.research_max_workers,
            stream_probe_samples=args.stream_probe_samples,
            redact_provider_identifiers=bool(args.redact_provider_identifiers),
        )
    except (ModelScreeningError, AvailableModelGenerationError) as exc:
        payload = {
            "schema": "axio_fusion_api.available_model_generation.v1",
            "status": "blocked",
            "available_model_list": [],
            "logical_model_count": 0,
            "blockers": [
                str(getattr(exc, "code", "available_model_generation_failed"))
            ],
            "publication": {
                "registry_must_be_published_only_when_ready": True,
                "blocked_generation_must_not_replace_active_registry": True,
            },
            "secrets_persisted": False,
        }
    if payload.get("status") == "ready" and args.registry_output:
        publication = publish_available_model_set(
            payload,
            registry_path=args.registry_output,
            handoff_path=args.handoff_output,
        )
        payload = {
            **payload,
            "publication": {
                **dict(payload.get("publication") or {}),
                "published": publication,
            },
        }
    _emit_json(payload, output=args.output)
    return 0 if payload.get("status") == "ready" else 2


def cmd_redact_provider_probe(args: argparse.Namespace) -> int:
    _emit_json(
        redact_provider_probe_artifact_file(args.probe_file),
        output=args.output,
    )
    return 0


def cmd_redact_tool_probe(args: argparse.Namespace) -> int:
    _emit_json(
        redact_provider_tool_probe_artifact_file(args.probe_file),
        output=args.output,
    )
    return 0


def cmd_registry_from_probe(args: argparse.Namespace) -> int:
    payload = build_registry_from_probe_artifacts(
        probe_paths=args.probe_file,
        include_unavailable=bool(args.include_unavailable),
        min_available_models=args.min_available_models,
        redact_provider_identifiers=bool(args.redact_provider_identifiers),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_provider_portfolio_audit(args: argparse.Namespace) -> int:
    payload = build_provider_portfolio_audit(
        load_registry(args.registry),
        min_provider_baselines=args.min_provider_baselines,
        min_provider_count=args.min_provider_count,
        min_api_format_count=args.min_api_format_count,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_provider_input_adapter_self_test(args: argparse.Namespace) -> int:
    payload = build_provider_input_adapter_self_test(
        load_registry(args.registry),
        prompt=args.prompt,
        system=args.system,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_remote_api_execution_audit(args: argparse.Namespace) -> int:
    payload = build_remote_api_execution_audit()
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready") is True else 2


def cmd_benchmark_provider_baseline_freeze(args: argparse.Namespace) -> int:
    payload = build_provider_baseline_freeze_manifest(
        registry_path=args.registry,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        min_provider_baselines=args.min_provider_baselines,
        provider_probe_evidence_audit_path=args.provider_probe_evidence_audit,
        external_ranking_manifest_path=args.external_ranking_manifest,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_external_ranking_template(args: argparse.Namespace) -> int:
    payload = build_external_provider_ranking_template(registry_path=args.registry)
    _emit_json(payload, output=args.output)
    return 0


def _baseline_screening_registry(args: argparse.Namespace) -> str:
    registry = str(getattr(args, "registry", None) or "").strip()
    if not registry:
        raise SystemExit(
            "baseline screening requires global --registry before the command"
        )
    return registry


def cmd_baseline_screening_plan(args: argparse.Namespace) -> int:
    payload = build_non_target_screening_plan(
        registry_path=_baseline_screening_registry(args),
        source_manifest_path=args.source_manifest,
        private_probe_files=args.private_probe_file,
        min_cases_per_source=args.min_cases_per_source,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready") is True else 2


def cmd_baseline_screening_run(args: argparse.Namespace) -> int:
    payload = run_non_target_screening_campaign(
        plan_path=args.plan,
        registry_path=_baseline_screening_registry(args),
        source_manifest_path=args.source_manifest,
        private_probe_files=args.private_probe_file,
        private_root=args.private_root,
        state_path=args.state_output,
        live=bool(args.live),
        max_workers=args.max_workers,
        max_tasks=args.max_tasks,
        retry_failed=bool(args.retry_failed),
        overwrite=False,
    )
    _emit_json(payload, output=args.output)
    if payload.get("status") in {"completed", "preflight_ready"}:
        return 0
    if (
        payload.get("status") == "partial"
        and payload.get("reason_codes") == [
            "screening_campaign_task_chunk_incomplete"
        ]
    ):
        return 0
    return 2


def cmd_baseline_screening_to_ranking(args: argparse.Namespace) -> int:
    payload = build_external_ranking_manifest_from_screening(
        plan_path=args.plan,
        campaign_state_path=args.campaign_state,
        registry_path=_baseline_screening_registry(args),
        source_manifest_path=args.source_manifest,
        private_probe_files=args.private_probe_file,
        private_root=args.private_root,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("screening_conversion_ready") is True else 2


def cmd_provider_probe_evidence_audit(args: argparse.Namespace) -> int:
    payload = build_provider_probe_evidence_audit(
        private_probe_files=args.private_probe_file,
        private_registry_file=args.private_registry_file,
        redacted_probe_file=args.redacted_probe_file,
        redacted_registry_evidence_file=args.redacted_registry_evidence_file,
        min_available_models=args.min_available_models,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmarks(args: argparse.Namespace) -> int:
    _emit_json(benchmark_manifest())
    return 0


def cmd_benchmark_methodology(args: argparse.Namespace) -> int:
    _emit_json(build_benchmark_methodology_manifest(), output=args.output)
    return 0


def cmd_benchmark_dataset_template(args: argparse.Namespace) -> int:
    payload = build_benchmark_dataset_manifest_template(
        base_dir=args.base_dir,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_source_manifest_template(args: argparse.Namespace) -> int:
    payload = build_benchmark_source_manifest_template(
        base_dir=args.base_dir,
        import_dir=args.import_dir,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_source_manifest_prepare(args: argparse.Namespace) -> int:
    payload = prepare_benchmark_source_manifest(
        template_path=args.template,
        case_hash_manifest_path=args.case_hash_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_source_manifest_validate(args: argparse.Namespace) -> int:
    payload = validate_benchmark_source_manifest(
        source_manifest_path=args.source_manifest,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_assemble_manifest(args: argparse.Namespace) -> int:
    payload = assemble_benchmark_dataset_manifest(
        template_path=args.template,
        dataset_dir=args.dataset_dir,
        import_dirs=args.import_dir,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_case_hash_manifest(args: argparse.Namespace) -> int:
    payload = build_benchmark_case_hash_manifest(
        dataset_manifest_path=args.dataset_manifest,
        candidate_ids=args.candidate_id,
        official_case_sources=_official_case_source_assignments(args.official_case_source),
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_source_manifest_bind_case_hashes(args: argparse.Namespace) -> int:
    payload = bind_benchmark_source_manifest_case_hashes(
        source_manifest_path=args.source_manifest,
        case_hash_manifest_path=args.case_hash_manifest,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_materialization_status(args: argparse.Namespace) -> int:
    payload = build_benchmark_materialization_status(
        raw_root=args.raw_root,
        output_dir=args.output_dir,
        download_manifest_path=args.download_manifest,
        suite_ids=args.suite_id,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_materialize_datasets(args: argparse.Namespace) -> int:
    payload = materialize_benchmark_datasets(
        raw_root=args.raw_root,
        output_dir=args.output_dir,
        download_manifest_path=args.download_manifest,
        suite_ids=args.suite_id,
        limit_per_suite=args.limit_per_suite,
        min_cases_per_suite=args.min_cases_per_suite,
        overwrite=bool(args.overwrite),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_acquire_gpqa_diamond(args: argparse.Namespace) -> int:
    try:
        payload = acquire_gpqa_diamond(
            accept_no_example_leakage_terms=bool(args.accept_no_example_leakage_terms),
            destination=args.destination,
            download_manifest_path=args.download_manifest,
            timeout_seconds=args.timeout_seconds,
        )
        exit_code = 0
    except BenchmarkAcquisitionError as exc:
        payload = exc.safe_receipt()
        exit_code = 2
    _emit_json(payload, output=args.output)
    return exit_code


def cmd_benchmark_matrix(args: argparse.Namespace) -> int:
    payload = build_benchmark_run_matrix(
        registry_path=args.registry,
        suite_ids=args.suite_id,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_acquisition_checklist(args: argparse.Namespace) -> int:
    payload = build_benchmark_acquisition_checklist(
        registry_path=args.registry,
        dataset_manifest_path=args.dataset_manifest,
        candidate_ids=args.candidate_id,
        base_dir=args.base_dir,
        import_dir=args.import_dir,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_acquisition_status(args: argparse.Namespace) -> int:
    payload = build_benchmark_acquisition_status(
        registry_path=args.registry,
        dataset_dir=args.dataset_dir,
        import_dirs=args.import_dir,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_run(args: argparse.Namespace) -> int:
    payload = run_benchmark_dataset(
        suite_id=args.suite_id,
        dataset_path=args.dataset,
        candidate_id=args.candidate_id,
        task_format=args.task_format,
        api_format=args.api_format,
        registry_path=args.registry,
        limit=args.limit,
        live=args.live,
        code_timeout_seconds=args.code_timeout_seconds,
        axio_gateway_url=args.axio_gateway_url,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_validate_dataset(args: argparse.Namespace) -> int:
    payload = validate_benchmark_dataset(
        suite_id=args.suite_id,
        dataset_path=args.dataset,
        task_format=args.task_format,
        max_rows=args.max_rows,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_import_official_run(args: argparse.Namespace) -> int:
    payload = import_official_benchmark_run(
        suite_id=args.suite_id,
        candidate_id=args.candidate_id,
        source_path=args.source,
        task_format=args.task_format,
        api_format=args.api_format,
        harness_name=args.harness_name,
        harness_version=args.harness_version,
        dataset_snapshot=args.dataset_snapshot,
        evaluator_config=args.evaluator_config,
        position_balanced=bool(args.position_balanced),
        prompt_protocol=args.prompt_protocol,
        decoding_config=args.decoding_config,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_import_official_batch(args: argparse.Namespace) -> int:
    payload = import_official_benchmark_run_batch(
        batch_path=args.batch_file,
        output_dir=args.output_dir,
        default_harness_name=args.harness_name,
        default_harness_version=args.harness_version,
        default_dataset_snapshot=args.dataset_snapshot,
        default_evaluator_config=args.evaluator_config,
        default_prompt_protocol=args.prompt_protocol,
        default_decoding_config=args.decoding_config,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_import_batch_template(args: argparse.Namespace) -> int:
    payload = build_official_import_batch_template(
        acquisition_checklist_path=args.acquisition_checklist,
        source_root_placeholder=args.source_root_placeholder,
        safe_import_dir_placeholder=args.safe_import_dir_placeholder,
        harness_pin_manifest_path=args.harness_pin_manifest,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_official_harness_execution_plan(args: argparse.Namespace) -> int:
    payload = build_official_harness_execution_plan(
        import_batch_template_path=args.import_batch_template,
        acquisition_status_path=args.acquisition_status,
        harness_pin_manifest_path=args.harness_pin_manifest,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_official_harness_preflight(args: argparse.Namespace) -> int:
    payload = build_official_harness_bridge_preflight(
        suite_id=args.suite_id,
        dataset_path=args.dataset,
        harness_root=args.harness_root,
        private_run_dir=args.private_run_dir,
        candidate_id=args.candidate_id,
        api_format=args.api_format,
        registry_path=args.registry,
        provider_baseline_freeze_manifest_path=args.provider_baseline_freeze_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        limit=args.limit,
        max_output_tokens=args.max_output_tokens,
        axio_gateway_url=args.axio_gateway_url,
        tau_user_model=args.tau_user_model,
        tau_user_provider=args.tau_user_provider,
        tau_user_strategy=args.tau_user_strategy,
        tau_environments=args.tau_environment,
        tau_max_steps=args.tau_max_steps,
        tau_python_executable=args.tau_python_executable,
        mt_comparison_candidate_id=args.mt_comparison_candidate_id,
        mt_judge_candidate_id=args.mt_judge_candidate_id,
        mt_judge_registry_path=args.mt_judge_registry,
        mt_judge_max_output_tokens=args.mt_judge_max_output_tokens,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_official_harness_generate(args: argparse.Namespace) -> int:
    payload = generate_official_harness_samples(
        suite_id=args.suite_id,
        dataset_path=args.dataset,
        harness_root=args.harness_root,
        private_run_dir=args.private_run_dir,
        candidate_id=args.candidate_id,
        api_format=args.api_format,
        registry_path=args.registry,
        provider_baseline_freeze_manifest_path=args.provider_baseline_freeze_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        live=bool(args.live),
        axio_gateway_url=args.axio_gateway_url,
        limit=args.limit,
        max_output_tokens=args.max_output_tokens,
        tau_user_model=args.tau_user_model,
        tau_user_provider=args.tau_user_provider,
        tau_user_strategy=args.tau_user_strategy,
        tau_environments=args.tau_environment,
        tau_max_steps=args.tau_max_steps,
        tau_python_executable=args.tau_python_executable,
        mt_comparison_candidate_id=args.mt_comparison_candidate_id,
        mt_judge_candidate_id=args.mt_judge_candidate_id,
        mt_judge_registry_path=args.mt_judge_registry,
        mt_judge_max_output_tokens=args.mt_judge_max_output_tokens,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_official_harness_evaluate(args: argparse.Namespace) -> int:
    payload = evaluate_official_harness_samples(
        suite_id=args.suite_id,
        dataset_path=args.dataset,
        harness_root=args.harness_root,
        private_run_dir=args.private_run_dir,
        candidate_id=args.candidate_id,
        api_format=args.api_format,
        registry_path=args.registry,
        provider_baseline_freeze_manifest_path=args.provider_baseline_freeze_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        allow_unsafe_code_execution=bool(args.allow_unsafe_code_execution),
        python_executable=args.python_executable,
        worker_count=args.worker_count,
        timeout_seconds=args.timeout_seconds,
        limit=args.limit,
        max_output_tokens=args.max_output_tokens,
        axio_gateway_url=args.axio_gateway_url,
        tau_user_model=args.tau_user_model,
        tau_user_provider=args.tau_user_provider,
        tau_user_strategy=args.tau_user_strategy,
        tau_environments=args.tau_environment,
        tau_max_steps=args.tau_max_steps,
        tau_python_executable=args.tau_python_executable,
        live=bool(args.live),
        mt_comparison_candidate_id=args.mt_comparison_candidate_id,
        mt_judge_candidate_id=args.mt_judge_candidate_id,
        mt_judge_registry_path=args.mt_judge_registry,
        mt_judge_max_output_tokens=args.mt_judge_max_output_tokens,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_official_harness_import(args: argparse.Namespace) -> int:
    payload = import_official_harness_evaluation(
        private_run_dir=args.private_run_dir,
        mt_side=args.mt_side,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_official_harness_campaign(args: argparse.Namespace) -> int:
    run_official_harness_campaign(
        execution_plan_path=args.execution_plan,
        suite_config_path=args.suite_config,
        registry_path=args.registry,
        provider_baseline_freeze_manifest_path=args.provider_baseline_freeze_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        private_root=args.private_root,
        safe_import_root=args.safe_import_root,
        state_path=args.output,
        suite_ids=args.suite_id,
        execution_task_ids=args.execution_task_id,
        candidate_hashes=args.candidate_hash,
        max_tasks=args.max_tasks,
        limit=args.limit,
        live=bool(args.live),
        retry_failed=bool(args.retry_failed),
        overwrite=bool(args.overwrite),
        allow_unsafe_code_execution=bool(args.allow_unsafe_code_execution),
    )
    return 0


def cmd_benchmark_official_import_audit(args: argparse.Namespace) -> int:
    include_provider_baselines = not args.no_provider_baselines
    max_provider_baselines = None if args.all_provider_baselines else args.max_provider_baselines
    payload = build_official_import_audit(
        dataset_manifest_path=args.dataset_manifest,
        source_manifest_path=args.source_manifest,
        case_hash_manifest_path=args.case_hash_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        import_dirs=args.import_dir,
        run_paths=args.run_file,
        registry_path=args.registry,
        candidate_ids=args.candidate_id,
        include_provider_baselines=include_provider_baselines,
        max_provider_baselines=max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_harness_pin_manifest(args: argparse.Namespace) -> int:
    payload = build_benchmark_harness_pin_manifest(
        harness_root=args.harness_root,
        raw_root=args.raw_root,
        bfcl_harness_root=args.bfcl_harness_root,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_scorecard(args: argparse.Namespace) -> int:
    payload = build_benchmark_scorecard(
        _load_run_files(args.run_file),
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        require_http_gateway=bool(args.require_http_gateway),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_api_surface_parity(args: argparse.Namespace) -> int:
    payload = build_benchmark_api_surface_parity_report(
        _load_run_files(args.run_file),
        score_tolerance=args.score_tolerance,
        require_http_gateway=bool(args.require_http_gateway),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_claim_audit(args: argparse.Namespace) -> int:
    payload = build_benchmark_claim_audit(
        _load_run_files(args.run_file),
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        require_http_gateway=bool(args.require_http_gateway),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_fusion_failure_analysis(args: argparse.Namespace) -> int:
    payload = build_benchmark_fusion_failure_analysis(
        scorecard=_load_json_object(args.scorecard_file),
        claim_audit=_load_json_object(args.claim_audit_file),
        readiness=_load_json_object(args.readiness_file),
        trace_report=_load_json_object(args.trace_report_file),
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_campaign(args: argparse.Namespace) -> int:
    payload = run_benchmark_campaign(
        dataset_manifest_path=args.dataset_manifest,
        output_dir=args.output_dir,
        registry_path=args.registry,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        provider_probe_evidence_audit_path=args.provider_probe_evidence_audit,
        source_manifest_path=args.source_manifest,
        case_hash_manifest_path=args.case_hash_manifest,
        official_import_audit_path=args.official_import_audit,
        api_surface_protocol_path=args.api_surface_protocol,
        provider_input_adapter_path=args.provider_input_adapter,
        system_development_readiness_path=args.system_development_readiness,
        limit=args.limit,
        live=args.live,
        resume=not bool(args.no_resume),
        code_timeout_seconds=args.code_timeout_seconds,
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
        strict_live_preflight=args.strict_live_preflight,
        axio_gateway_url=args.axio_gateway_url,
    )
    _emit_json(payload)
    return 0


def cmd_benchmark_campaign_progress_plan(args: argparse.Namespace) -> int:
    payload = build_benchmark_campaign_progress_plan(
        dataset_manifest_path=args.dataset_manifest,
        output_dir=args.output_dir,
        registry_path=args.registry,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_readiness(args: argparse.Namespace) -> int:
    payload = audit_benchmark_campaign_readiness(
        dataset_manifest_path=args.dataset_manifest,
        registry_path=args.registry,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        min_cases_per_suite=args.min_cases_per_suite,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fusion_live_readiness(args: argparse.Namespace) -> int:
    payload = build_fusion_live_readiness(
        registry_path=args.registry,
        benchmark_manifest_dir=args.benchmark_manifest_dir,
        materialization_status_path=args.materialization_status,
        case_hash_manifest_path=args.case_hash_manifest,
        harness_pin_manifest_path=args.harness_pin_manifest,
        source_manifest_validation_path=args.source_manifest_validation,
        import_batch_template_path=args.import_batch_template,
        official_harness_execution_plan_path=args.official_harness_execution_plan,
        official_import_audit_path=args.official_import_audit,
        acquisition_status_path=args.acquisition_status,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        provider_probe_evidence_audit_path=args.provider_probe_evidence_audit,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fusion_live_runbook(args: argparse.Namespace) -> int:
    payload = build_fusion_live_runbook(
        registry_path=args.registry,
        benchmark_manifest_dir=args.benchmark_manifest_dir,
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_final_audit(args: argparse.Namespace) -> int:
    payload = build_benchmark_final_audit(
        campaign_dir=args.campaign_dir,
        campaign_file=args.campaign_file,
        source_manifest_path=args.source_manifest,
        case_hash_manifest_path=args.case_hash_manifest,
        runs_file=args.runs_file,
        scorecard_file=args.scorecard_file,
        claim_audit_file=args.claim_audit_file,
        methodology_file=args.methodology_file,
        provider_probe_evidence_audit_file=args.provider_probe_evidence_audit,
        provider_baseline_freeze_file=args.provider_baseline_freeze,
        official_import_audit_file=args.official_import_audit,
        api_surface_parity_file=args.api_surface_parity,
        training_contamination_audit_file=args.training_contamination_audit_file,
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_benchmark_evidence_pack(args: argparse.Namespace) -> int:
    payload = build_benchmark_evidence_pack(
        registry_path=args.registry,
        source_manifest_path=args.source_manifest,
        case_hash_manifest_path=args.case_hash_manifest,
        provider_probe_evidence_audit_path=args.provider_probe_evidence_audit,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        official_import_audit_path=args.official_import_audit,
        api_surface_parity_path=args.api_surface_parity,
        dataset_manifest_path=args.dataset_manifest,
        campaign_dir=args.campaign_dir,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fusion_completion_audit(args: argparse.Namespace) -> int:
    payload = build_fusion_completion_audit(
        registry_path=args.registry,
        evidence_pack_path=args.evidence_pack,
        final_audit_path=args.final_audit,
        api_surface_protocol_path=args.api_surface_protocol,
        provider_input_adapter_path=args.provider_input_adapter,
        system_development_readiness_path=args.system_development_readiness,
        live_runbook_path=args.live_runbook,
        failure_analysis_path=args.failure_analysis,
        source_manifest_path=args.source_manifest,
        case_hash_manifest_path=args.case_hash_manifest,
        provider_probe_evidence_audit_path=args.provider_probe_evidence_audit,
        provider_baseline_freeze_path=args.provider_baseline_freeze,
        official_import_audit_path=args.official_import_audit,
        api_surface_parity_path=args.api_surface_parity,
        dataset_manifest_path=args.dataset_manifest,
        campaign_dir=args.campaign_dir,
        candidate_ids=args.candidate_id,
        include_provider_baselines=not bool(args.no_provider_baselines),
        max_provider_baselines=None if args.all_provider_baselines else args.max_provider_baselines,
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fusion_code_test_receipt(args: argparse.Namespace) -> int:
    payload = build_fusion_code_test_receipt(
        test_name=args.test_name,
        command_template=args.command_template,
        exit_code=args.exit_code,
        passed_count=args.passed_count,
        failed_count=args.failed_count,
        skipped_count=args.skipped_count,
        deselected_count=args.deselected_count,
        duration_seconds=args.duration_seconds,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_fusion_system_development_readiness(args: argparse.Namespace) -> int:
    payload = build_fusion_system_development_readiness(
        registry_path=args.registry,
        code_test_receipt_path=args.code_test_receipt,
        api_surface_protocol_path=args.api_surface_protocol,
        provider_input_adapter_path=args.provider_input_adapter,
        live_runbook_path=args.live_runbook,
        min_cases_per_suite=args.min_cases_per_suite,
        alpha=args.alpha,
    )
    _emit_json(payload, output=args.output)
    return 0


def cmd_learning_report(args: argparse.Namespace) -> int:
    payload = build_learning_signal_report(
        feedback_paths=args.feedback_file,
        scorecard_paths=args.scorecard_file,
        min_examples_for_policy_update=args.min_examples,
        allow_benchmark_diagnostics=bool(args.allow_benchmark_diagnostics),
    )
    blocked_benchmark_diagnostics = bool(args.scorecard_file) and not bool(args.allow_benchmark_diagnostics)
    if args.output:
        write_learning_json(args.output, payload)
        return 2 if blocked_benchmark_diagnostics else 0
    _emit_json(payload)
    return 2 if blocked_benchmark_diagnostics else 0


def cmd_orchestrator_training_dataset(args: argparse.Namespace) -> int:
    payload = build_orchestrator_training_dataset(
        feedback_paths=args.feedback_file,
        trace_paths=args.trace_file,
        min_pair_score_delta=args.min_pair_score_delta,
        max_examples=args.max_examples,
    )
    if args.output:
        write_learning_json(args.output, payload)
        return 0
    _emit_json(payload)
    return 0


def cmd_router_policy_shadow_patch(args: argparse.Namespace) -> int:
    payload = build_router_policy_shadow_patch(
        feedback_paths=args.feedback_file,
        trace_paths=args.trace_file,
        min_examples=args.min_examples,
    )
    if args.output:
        write_learning_json(args.output, payload)
        return 0
    _emit_json(payload)
    return 0


def cmd_routing_policy_candidate(args: argparse.Namespace) -> int:
    payload = build_routing_policy_candidate(
        _load_json_object(args.shadow_patch),
        profiles=load_registry(args.registry),
        min_examples=args.min_examples,
        created_on=args.created_on,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready_for_review") is True else 2


def cmd_routing_policy_shadow_replay(args: argparse.Namespace) -> int:
    payload = build_routing_policy_shadow_replay(
        _safe_load_json_object(args.candidate),
        trace_paths=args.trace_file,
        feedback_paths=args.feedback_file,
        max_cases=args.max_cases,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("status") == "decision_replay_ready" else 2


def cmd_routing_policy_review(args: argparse.Namespace) -> int:
    payload = review_routing_policy_candidate(
        _load_json_object(args.candidate),
        profiles=load_registry(args.registry),
        contamination_audit=_load_json_object(args.contamination_audit),
        approved=bool(args.approve),
        reviewer_id=args.reviewer_id,
        reviewed_on=args.reviewed_on,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready_for_activation") is True else 2


def cmd_routing_policy_activate(args: argparse.Namespace) -> int:
    payload = activate_routing_policy(
        _load_json_object(args.candidate),
        _load_json_object(args.review),
        profiles=load_registry(args.registry),
        rollback_policy_digest_sha256=args.rollback_policy_digest,
        activated_on=args.activated_on,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("activation_ready") is True else 2


def cmd_routing_policy_status(args: argparse.Namespace) -> int:
    payload = load_active_routing_policy(
        load_registry(args.registry),
        path=args.policy,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("active") is True else 2


def cmd_provider_onboarding_candidate(args: argparse.Namespace) -> int:
    payload = build_provider_onboarding_candidate(
        profiles=load_registry(args.registry, include_disabled=True),
        candidate_profile_hashes=args.candidate_profile_hash,
        probe_paths=args.probe_file,
        calibration_paths=args.calibration_file,
        created_on=args.created_on,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready_for_review") is True else 2


def cmd_provider_onboarding_review(args: argparse.Namespace) -> int:
    payload = review_provider_onboarding_candidate(
        _safe_load_json_object(args.candidate),
        profiles=load_registry(args.registry, include_disabled=True),
        approved=bool(args.approve),
        reviewer_id=args.reviewer_id,
        reviewed_on=args.reviewed_on,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready_for_activation") is True else 2


def cmd_provider_onboarding_activate(args: argparse.Namespace) -> int:
    payload = activate_provider_onboarding_candidate(
        _safe_load_json_object(args.candidate),
        _safe_load_json_object(args.review),
        profiles=load_registry(args.registry, include_disabled=True),
        activated_on=args.activated_on,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("activation_ready") is True else 2


def cmd_provider_onboarding_apply(args: argparse.Namespace) -> int:
    payload = apply_provider_onboarding_activation(
        _safe_load_json_object(args.candidate),
        _safe_load_json_object(args.review),
        registry_path=args.source_registry,
        output_registry_path=args.output_registry,
    )
    _emit_json(payload, output=args.output)
    return 0 if payload.get("status") == "active" else 2


def cmd_training_contamination_audit(args: argparse.Namespace) -> int:
    payload = build_training_contamination_audit(
        benchmark_paths=args.benchmark_file,
        training_dataset_paths=args.training_dataset_file,
        learning_report_paths=args.learning_report_file,
        calibration_paths=args.calibration_file,
        feedback_paths=args.feedback_file,
        trace_paths=args.trace_file,
        allow_aggregate_benchmark_calibration=bool(args.allow_aggregate_benchmark_calibration),
    )
    if args.output:
        write_learning_json(args.output, payload)
        return 0
    _emit_json(payload)
    return 0


def cmd_trace_report(args: argparse.Namespace) -> int:
    payload = build_trace_report(args.trace_file)
    if args.output:
        write_trace_json(args.output, payload)
        return 0
    _emit_json(payload)
    return 0


def cmd_calibrate_registry(args: argparse.Namespace) -> int:
    payload = build_registry_calibration(
        registry_path=args.registry,
        probe_paths=args.probe_file,
        benchmark_paths=args.benchmark_file,
        feedback_paths=args.feedback_file,
        trace_paths=args.trace_file,
        allow_benchmark_calibration=bool(args.allow_benchmark_calibration),
    )
    contract = payload.get("application_contract") if isinstance(payload.get("application_contract"), dict) else {}
    if contract.get("safe_to_write_registry") is not True:
        if args.output:
            write_calibration_json(args.output, payload)
        else:
            _emit_json(payload)
        return 2
    if args.updated_registry_output:
        write_calibration_json(args.updated_registry_output, payload["updated_registry"])
    if args.output:
        write_calibration_json(args.output, payload)
        return 0
    _emit_json(payload)
    return 0


def cmd_tool_execute(args: argparse.Namespace) -> int:
    calls = []
    tool_policy = None
    if args.call_file:
        payload = json.loads(Path(args.call_file).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            calls.extend(row for row in payload if isinstance(row, dict))
        elif isinstance(payload, dict) and isinstance(payload.get("calls"), list):
            calls.extend(row for row in payload["calls"] if isinstance(row, dict))
        elif isinstance(payload, dict):
            calls.append(payload)
    if args.tool_policy_file:
        policy_payload = json.loads(Path(args.tool_policy_file).read_text(encoding="utf-8"))
        if isinstance(policy_payload, dict) and isinstance(policy_payload.get("tool_policy"), dict):
            tool_policy = policy_payload["tool_policy"]
        elif isinstance(policy_payload, dict) and isinstance(policy_payload.get("route_plan"), dict):
            route_plan = policy_payload["route_plan"]
            tool_policy = route_plan.get("tool_policy") if isinstance(route_plan.get("tool_policy"), dict) else None
        elif isinstance(policy_payload, dict):
            tool_policy = policy_payload
    for raw in args.call_json:
        value = json.loads(raw)
        if isinstance(value, dict):
            calls.append(value)
    payload = execute_tool_batch(calls, role=args.role, max_tool_calls=args.max_tool_calls, tool_policy=tool_policy)
    _emit_json(payload, output=args.output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    previous_provider_config_file = os.environ.get("AXIO_FUSION_PROVIDER_CONFIG_FILE")
    if args.provider_config_file:
        os.environ["AXIO_FUSION_PROVIDER_CONFIG_FILE"] = str(args.provider_config_file)
    try:
        return int(args.func(args) or 0)
    finally:
        if args.provider_config_file:
            if previous_provider_config_file is None:
                os.environ.pop("AXIO_FUSION_PROVIDER_CONFIG_FILE", None)
            else:
                os.environ["AXIO_FUSION_PROVIDER_CONFIG_FILE"] = previous_provider_config_file


def _emit_json(payload: dict, *, output: str | None = None) -> None:
    if output:
        _write_json_atomic(output, payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _write_json_atomic(path: str | Path, payload: dict) -> Path:
    """Publish one complete control-plane artifact or leave the old file intact."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(output)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return output


def _load_run_files(paths: list[str]) -> list[dict]:
    runs = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            runs.extend(row for row in payload if isinstance(row, dict))
        elif isinstance(payload, dict) and isinstance(payload.get("runs"), list):
            runs.extend(row for row in payload["runs"] if isinstance(row, dict))
        elif isinstance(payload, dict):
            runs.append(payload)
    return runs


def _official_case_source_assignments(values: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for raw in values:
        suite_id, separator, path = str(raw or "").partition("=")
        suite_id = suite_id.strip()
        path = path.strip()
        if not separator or not suite_id or not path:
            raise ValueError("--official-case-source must use SUITE_ID=PRIVATE_SOURCE_PATH")
        sources[suite_id] = path
    return sources


def _load_json_object(path: str | None) -> dict:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def _safe_load_json_object(path: str | None) -> dict:
    """Fail closed for policy diagnostics without echoing private file data."""

    try:
        return _load_json_object(path)
    except (OSError, json.JSONDecodeError, SystemExit):
        return {}


def _request_payload_from_args(args: argparse.Namespace) -> dict:
    if getattr(args, "request_file", None):
        payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        raise SystemExit("--request-file must contain a JSON object")
    if getattr(args, "request_json", None):
        payload = json.loads(args.request_json)
        if isinstance(payload, dict):
            return payload
        raise SystemExit("--request-json must be a JSON object")
    if not getattr(args, "prompt", None):
        raise SystemExit("one of --prompt, --request-json, or --request-file is required")
    return {
        "model": args.model,
        "task_type": args.task_type,
        "messages": [{"role": "user", "content": args.prompt}],
    }


if __name__ == "__main__":
    raise SystemExit(main())
