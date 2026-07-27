"""Production-only command line for the standalone Fusion gateway.

This entry point intentionally excludes the benchmark control plane.  It is
safe to install beside an external evaluator because importing it never pulls
benchmark datasets, scorers, or campaign code into the serving process.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from .compat import canonicalize_payload, render_response
from .execution_boundary import build_remote_api_execution_audit
from .orchestrator import FusionEngine
from .providers import HTTPProviderClient
from .provider_enrollment import enroll_provider_channels
from .providers import discover_provider_inventory
from .registry import load_registry
from .server import (
    build_api_surface_live_smoke,
    build_api_surface_protocol_self_test,
    build_fusion_deliberation_live_smoke,
    create_runtime_http_server,
    serve,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axio-fusion-api-service")
    parser.add_argument("--registry", default=None)
    parser.add_argument(
        "--provider-config-file",
        default=None,
        help="Non-secret provider manifest. Credentials are resolved from process environment variables.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8789)
    serve_cmd.add_argument("--live", action="store_true")
    serve_cmd.add_argument("--discover", action="store_true")
    serve_cmd.add_argument("--enroll", action="store_true")
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
    serve_cmd.add_argument("--enrollment-tool-probe-timeout", type=float, default=None)
    serve_cmd.add_argument("--enrollment-tool-probe-max-models", type=int, default=None)
    serve_cmd.add_argument("--enrollment-tool-probe-max-models-per-provider", type=int, default=None)
    serve_cmd.add_argument("--enrollment-reasoning-probe-timeout", type=float, default=None)
    serve_cmd.add_argument("--enrollment-reasoning-probe-max-models", type=int, default=None)
    serve_cmd.add_argument("--enrollment-reasoning-probe-max-models-per-provider", type=int, default=None)
    serve_cmd.add_argument("--enrollment-min-available-models", type=int, default=1)
    serve_cmd.add_argument("--no-tool-calibration", action="store_true")
    serve_cmd.add_argument("--no-reasoning-calibration", action="store_true")
    serve_cmd.add_argument("--prefusion-focus-manifest", default=None)
    serve_cmd.add_argument("--prefusion-source-manifest", default=None)
    serve_cmd.add_argument("--prefusion-research-agent-config", default=None)
    serve_cmd.add_argument("--prefusion-research-output", default=None)
    serve_cmd.add_argument("--prefusion-max-models", type=int, default=None)
    serve_cmd.add_argument("--prefusion-research-batch-size", type=int, default=None)
    serve_cmd.add_argument("--prefusion-research-max-workers", type=int, default=None)
    serve_cmd.add_argument(
        "--prefusion-stream-probe-samples",
        type=int,
        default=None,
        help="Strict streaming health samples per physical profile; production requires at least two.",
    )
    serve_cmd.add_argument("--enrollment-receipt-output", default=None)
    serve_cmd.set_defaults(func=cmd_serve)

    complete = sub.add_parser("complete")
    complete.add_argument("--api-format", default="chat/completions")
    complete.add_argument("--model", default="axio-terra")
    complete.add_argument("--prompt", default=None)
    complete.add_argument("--request-json", default=None)
    complete.add_argument("--request-file", default=None)
    complete.add_argument("--live", action="store_true")
    complete.set_defaults(func=cmd_complete)

    route = sub.add_parser("route-plan")
    route.add_argument("--api-format", default="chat/completions")
    route.add_argument("--model", default="axio-terra")
    route.add_argument("--prompt", default=None)
    route.add_argument("--request-json", default=None)
    route.add_argument("--request-file", default=None)
    route.set_defaults(func=cmd_route_plan)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--live", action="store_true")
    inventory.add_argument("--timeout", type=float, default=10.0)
    inventory.set_defaults(func=cmd_inventory)

    enroll = sub.add_parser("enroll-providers")
    enroll.add_argument("--config-file", default=None)
    enroll.add_argument("--provider", action="append", default=[])
    enroll.add_argument("--timeout", type=float, default=60.0)
    enroll.add_argument("--max-models", type=int, default=None)
    enroll.add_argument("--max-models-per-provider", type=int, default=None)
    enroll.add_argument("--tool-probe-timeout", type=float, default=None)
    enroll.add_argument("--tool-probe-max-models", type=int, default=None)
    enroll.add_argument("--tool-probe-max-models-per-provider", type=int, default=None)
    enroll.add_argument("--reasoning-probe-timeout", type=float, default=None)
    enroll.add_argument("--reasoning-probe-max-models", type=int, default=None)
    enroll.add_argument("--reasoning-probe-max-models-per-provider", type=int, default=None)
    enroll.add_argument("--max-workers", type=int, default=4)
    enroll.add_argument("--min-available-models", type=int, default=1)
    enroll.add_argument("--include-unavailable", action="store_true")
    enroll.add_argument("--no-tool-calibration", action="store_true")
    enroll.add_argument("--no-reasoning-calibration", action="store_true")
    enroll.add_argument("--redact-provider-identifiers", action="store_true")
    enroll.add_argument("--live", action="store_true")
    enroll.add_argument("--output-dir", required=True)
    enroll.set_defaults(func=cmd_enroll_providers)

    protocol = sub.add_parser("api-surface-protocol-self-test")
    protocol.add_argument("--model", action="append", default=[])
    protocol.add_argument("--prompt", default=None)
    protocol.add_argument("--task-type", default="api_surface_protocol_self_test")
    protocol.add_argument("--output", default=None)
    protocol.set_defaults(func=cmd_api_surface_protocol_self_test)

    live_smoke = sub.add_parser("api-surface-live-smoke")
    live_smoke.add_argument("--model", action="append", default=[])
    live_smoke.add_argument("--prompt", default=None)
    live_smoke.add_argument("--task-type", default="api_surface_live_smoke")
    live_smoke.add_argument("--max-latency-ms", type=int, default=12000)
    live_smoke.add_argument("--max-output-tokens", type=int, default=48)
    live_smoke.add_argument("--live", action="store_true")
    live_smoke.add_argument("--output", default=None)
    live_smoke.set_defaults(func=cmd_api_surface_live_smoke)

    deliberation = sub.add_parser("fusion-deliberation-live-smoke")
    deliberation.add_argument("--model", action="append", default=[])
    deliberation.add_argument("--prompt", default=None)
    deliberation.add_argument("--task-type", default="fusion_deliberation_live_smoke")
    deliberation.add_argument("--max-latency-ms", type=int, default=30000)
    deliberation.add_argument("--max-output-tokens", type=int, default=128)
    deliberation.add_argument("--max-total-model-calls", type=int, default=6)
    deliberation.add_argument("--max-cost-usd", type=float, default=0.02)
    deliberation.add_argument("--live", action="store_true")
    deliberation.add_argument("--output", default=None)
    deliberation.set_defaults(func=cmd_fusion_deliberation_live_smoke)

    audit = sub.add_parser("remote-api-execution-audit")
    audit.add_argument("--output", default=None)
    audit.set_defaults(func=cmd_remote_api_execution_audit)
    return parser


def cmd_serve(args: argparse.Namespace) -> int:
    dynamic_manifest_mode = bool(args.discover or args.enroll)
    configured_path = str(
        args.provider_config_file or os.getenv("AXIO_FUSION_PROVIDER_CONFIG_FILE") or ""
    ).strip()
    if dynamic_manifest_mode and not configured_path:
        raise SystemExit("--discover/--enroll requires --provider-config-file")
    if (args.discover or args.enroll) and not args.live:
        raise SystemExit("--discover/--enroll requires --live")
    if args.discover and not args.enroll and not args.diagnostic_only:
        raise SystemExit(
            "--discover is inventory-only; use --enroll for production pre-Fusion admission "
            "or add --diagnostic-only for diagnostics"
        )
    if args.registry and dynamic_manifest_mode:
        raise SystemExit("--registry cannot be combined with --discover/--enroll")
    if not dynamic_manifest_mode:
        if args.registry:
            os.environ["AXIO_FUSION_REGISTRY_PATH"] = str(args.registry)
        print(f"Serving standalone Axio Fusion API on http://{args.host}:{args.port}", file=sys.stderr)
        try:
            serve(host=args.host, port=args.port, live=bool(args.live))
        except KeyboardInterrupt:
            return 0
        return 0

    manifest = _load_json_object(configured_path)
    print(f"Serving standalone Axio Fusion API on http://{args.host}:{args.port}", file=sys.stderr)
    server = create_runtime_http_server(
        manifest,
        host=args.host,
        port=args.port,
        live=True,
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
        enrollment_reasoning_probe_timeout=args.enrollment_reasoning_probe_timeout,
        enrollment_reasoning_probe_max_models=args.enrollment_reasoning_probe_max_models,
        enrollment_reasoning_probe_max_models_per_provider=args.enrollment_reasoning_probe_max_models_per_provider,
        enrollment_min_available_models=args.enrollment_min_available_models,
        enrollment_calibrate_tools=not bool(args.no_tool_calibration),
        enrollment_calibrate_reasoning=not bool(args.no_reasoning_calibration),
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
    if args.enrollment_receipt_output and isinstance(receipt, Mapping):
        _write_json(args.enrollment_receipt_output, receipt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    request = canonicalize_payload(
        _request_payload_from_args(args), api_format=str(args.api_format)
    )
    engine = FusionEngine(
        load_registry(args.registry, require_prefusion=bool(args.live)),
        client=(HTTPProviderClient(require_streaming=True) if args.live else None),
    )
    response = engine.complete(
        request, live=bool(args.live)
    )
    print(json.dumps(render_response(response, api_format=args.api_format), ensure_ascii=False, indent=2))
    return 0


def cmd_route_plan(args: argparse.Namespace) -> int:
    request = canonicalize_payload(
        _request_payload_from_args(args), api_format=str(args.api_format)
    )
    response = FusionEngine(load_registry(args.registry)).complete(request, live=False)
    print(json.dumps(response.route_plan, ensure_ascii=False, indent=2))
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            discover_provider_inventory(live=bool(args.live), timeout=args.timeout),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_enroll_providers(args: argparse.Namespace) -> int:
    payload = enroll_provider_channels(
        config_path=args.config_file or args.provider_config_file,
        output_dir=args.output_dir,
        providers=args.provider,
        live=bool(args.live),
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
        calibrate_reasoning=not bool(args.no_reasoning_calibration),
        reasoning_probe_timeout=args.reasoning_probe_timeout,
        reasoning_probe_max_models=args.reasoning_probe_max_models,
        reasoning_probe_max_models_per_provider=args.reasoning_probe_max_models_per_provider,
        redact_provider_identifiers=bool(args.redact_provider_identifiers),
    )
    _emit_json(payload)
    return 0 if payload.get("status") == "ready" else 2


def cmd_api_surface_protocol_self_test(args: argparse.Namespace) -> int:
    _emit_json(
        build_api_surface_protocol_self_test(
            registry_path=args.registry,
            models=args.model,
            prompt=args.prompt,
            task_type=args.task_type,
        ),
        output=args.output,
    )
    return 0


def cmd_api_surface_live_smoke(args: argparse.Namespace) -> int:
    _emit_json(
        build_api_surface_live_smoke(
            registry_path=args.registry,
            models=args.model,
            prompt=args.prompt,
            task_type=args.task_type,
            max_latency_ms=args.max_latency_ms,
            max_output_tokens=args.max_output_tokens,
            live=bool(args.live),
        ),
        output=args.output,
    )
    return 0


def cmd_fusion_deliberation_live_smoke(args: argparse.Namespace) -> int:
    _emit_json(
        build_fusion_deliberation_live_smoke(
            registry_path=args.registry,
            models=args.model,
            prompt=args.prompt,
            task_type=args.task_type,
            max_latency_ms=args.max_latency_ms,
            max_output_tokens=args.max_output_tokens,
            max_total_model_calls=args.max_total_model_calls,
            max_cost_usd=args.max_cost_usd,
            live=bool(args.live),
        ),
        output=args.output,
    )
    return 0


def cmd_remote_api_execution_audit(args: argparse.Namespace) -> int:
    payload = build_remote_api_execution_audit()
    _emit_json(payload, output=args.output)
    return 0 if payload.get("ready") is True else 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    previous_config_path = os.environ.get("AXIO_FUSION_PROVIDER_CONFIG_FILE")
    if args.provider_config_file:
        os.environ["AXIO_FUSION_PROVIDER_CONFIG_FILE"] = str(args.provider_config_file)
    try:
        return int(args.func(args) or 0)
    finally:
        if args.provider_config_file:
            if previous_config_path is None:
                os.environ.pop("AXIO_FUSION_PROVIDER_CONFIG_FILE", None)
            else:
                os.environ["AXIO_FUSION_PROVIDER_CONFIG_FILE"] = previous_config_path


def _request_payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.request_json:
        value = json.loads(str(args.request_json))
    elif args.request_file:
        value = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
    elif args.prompt is not None:
        value = {
            "model": args.model,
            "messages": [{"role": "user", "content": str(args.prompt)}],
        }
    else:
        raise SystemExit("one of --prompt, --request-json, or --request-file is required")
    if not isinstance(value, Mapping):
        raise SystemExit("request payload must be a JSON object")
    return dict(value)


def _load_json_object(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("provider config file is unreadable") from exc
    if not isinstance(value, Mapping):
        raise SystemExit("provider config file must contain a JSON object")
    return dict(value)


def _emit_json(payload: Mapping[str, Any], *, output: str | None = None) -> None:
    if output:
        _write_json(output, payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
