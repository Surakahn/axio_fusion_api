from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

from .compat import (
    IncrementalStreamRenderer,
    canonicalize_payload,
    normalize_api_format,
    public_route_summary,
    render_response,
    render_stream_events,
)
from .content_contract import ContentContractError
from .image_api import (
    ImageRequestError,
    ImageRouter,
    image_request_timeout,
    image_route_kind,
    parse_edit_payload,
    parse_generation_payload,
    render_image_event,
    render_image_stream,
)
from .latency_policy import profile_latency_eligibility
from .orchestrator import FusionEngine, FusionExecutionError, PublicStreamInterruptedError
from .network import provider_proxy_runtime_summary
from .providers import (
    HTTPProviderClient,
    discover_provider_inventory,
    ensure_strict_streaming_client,
    profile_credential_readiness,
)
from .registry import load_registry, registry_readiness
from .runtime import ResponseContinuation, runtime_state, tenant_key_from_headers
from .runtime_activation import AtomicFusionRuntime
from .schemas import (
    FusionRequest,
    FusionResponse,
    PUBLIC_MODELS,
    safe_provider_error_class,
    safe_provider_error_code,
    safe_provider_http_status,
    sha256_text,
    stable_json,
)
from .tool_contract import hydrate_tool_result_names
from .trace_store import record_execution_trace
from .tools import execute_tool_batch

API_SURFACE_PROTOCOL_FORMATS = ("chat/completions", "responses", "anthropic", "gemini")
FUSION_DELIBERATION_SMOKE_DEFAULT_MODELS = ("axio-terra", "axio-pro")


@dataclass(frozen=True)
class _PreparedIncrementalStream:
    headers_lc: Mapping[str, str]
    payload: Mapping[str, Any]
    endpoint: str
    request: FusionRequest
    active_engine: FusionEngine
    tenant_key: str
    live: bool


@dataclass(frozen=True)
class _PreparedIncrementalImageStream:
    headers_lc: Mapping[str, str]
    operation: str
    payload: Mapping[str, Any]
    files: tuple[Any, ...]
    router: ImageRouter
    tenant_key: str


def handle_request(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str] | None = None,
    body: bytes | str | None = None,
    engine: FusionEngine | None = None,
    live: bool = False,
    record_trace: bool = True,
    record_runtime: bool = True,
    record_response_continuations: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    headers_lc = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    route = urlparse(path).path.rstrip("/") or "/"
    if method.upper() == "OPTIONS":
        return _cors_preflight_response(headers_lc)

    def respond(response: tuple[int, dict[str, str], bytes]) -> tuple[int, dict[str, str], bytes]:
        return _apply_cors_headers(response, headers_lc)

    if _operator_endpoint(route):
        if not _operator_authorized(
            headers_lc,
            require_explicit_operator_key=_operator_endpoint_requires_explicit_key(route),
        ):
            return respond(_operator_forbidden_response())
    elif not _authorized(headers_lc):
        return respond(_json_response(401, {"error": {"message": "Unauthorized", "code": "unauthorized"}}))
    tenant_key = tenant_key_from_headers(headers_lc)
    if record_runtime:
        rate = runtime_state().check_rate_limit(tenant_key)
        if not rate["allowed"]:
            return respond(
                _json_response(
                    429,
                    {
                        "error": {"message": "Rate limit exceeded", "code": "rate_limit_exceeded"},
                        "metadata": {
                            "rate_limit": rate,
                            "raw_prompt_persisted": False,
                            "secrets_persisted": False,
                        },
                    },
                    extra_headers={"Retry-After": str(rate.get("retry_after_seconds") or 1)},
                )
            )
    # A live request that does not receive an already-admitted in-memory
    # engine must use the hash-bound pre-Fusion registry.  The non-live path
    # remains available for protocol and route-plan diagnostics.
    active_engine = engine or FusionEngine(
        load_registry(require_prefusion=bool(live))
    )
    if method.upper() == "GET" and route in {"/health", "/v1/health"}:
        return respond(_json_response(200, _health(active_engine)))
    if method.upper() == "GET" and route in {"/v1/models", "/models"}:
        return respond(_json_response(200, _models(active_engine)))
    if method.upper() == "GET" and route in {"/v1/axio/runtime", "/runtime"}:
        return respond(_json_response(200, runtime_state().snapshot()))
    if method.upper() != "POST":
        return respond(_json_response(405, {"error": {"message": "Method not allowed", "code": "method_not_allowed"}}))
    image_operation = image_route_kind(route)
    if image_operation:
        if record_runtime:
            budget = runtime_state().check_budget(tenant_key)
            if not budget["allowed"]:
                return respond(_tenant_budget_exhausted_response(budget))
        return respond(
            _handle_image_request(
                operation=image_operation,
                headers=headers_lc,
                body=body,
                profiles=active_engine.profiles,
            )
        )
    try:
        payload = _decode_json(body)
    except ValueError as exc:
        return respond(_json_response(400, {"error": {"message": str(exc), "code": "invalid_json"}}))
    if route in {"/v1/axio/route-plan", "/route-plan"}:
        api_format = normalize_api_format(str(payload.get("api_format") or "chat/completions"))
        try:
            request = canonicalize_payload(
                payload.get("request") if isinstance(payload.get("request"), Mapping) else payload,
                api_format=api_format,
            )
        except ContentContractError as exc:
            return respond(
                _json_response(
                    400,
                    {"error": {"message": str(exc), "code": exc.code}},
                )
            )
        return respond(_json_response(200, _safe_route_plan_response(active_engine.complete(request, live=False).route_plan)))
    if route in {"/v1/inventory", "/inventory"}:
        return respond(_json_response(200, discover_provider_inventory(live=bool(payload.get("live")), timeout=float(payload.get("timeout") or 10.0))))
    if route in {"/v1/axio/feedback", "/feedback"}:
        return respond(_json_response(200, runtime_state().record_feedback(payload, tenant_key)))
    if route in {"/v1/axio/agent-outcome", "/agent-outcome"}:
        feedback_payload = payload if isinstance(payload.get("agent_outcome"), Mapping) else {**payload, "agent_outcome": payload}
        return respond(_json_response(200, runtime_state().record_feedback(feedback_payload, tenant_key)))
    if route in {"/v1/axio/tools/execute", "/tools/execute"}:
        calls = payload.get("calls") if isinstance(payload.get("calls"), list) else []
        if not calls and isinstance(payload.get("call"), Mapping):
            calls = [payload["call"]]
        role = str(payload.get("role") or "primary_solver")
        max_calls = _optional_int(payload.get("max_tool_calls"))
        tool_policy = _tool_policy_from_payload(payload)
        return respond(_json_response(200, execute_tool_batch(calls, role=role, max_tool_calls=max_calls, tool_policy=tool_policy)))
    endpoint = _endpoint_api_format(route)
    if not endpoint:
        return respond(_json_response(404, {"error": {"message": f"Unknown endpoint: {route}", "code": "not_found"}}))
    if record_runtime:
        budget = runtime_state().check_budget(tenant_key)
        if not budget["allowed"]:
            return respond(_tenant_budget_exhausted_response(budget))
    if endpoint == "gemini":
        route_model = _gemini_route_model(route)
        if route_model and "model" not in payload:
            payload = {**payload, "model": route_model}
    continuation: ResponseContinuation | None = None
    if endpoint == "responses" and "previous_response_id" in payload:
        continuation = runtime_state().get_response_continuation(
            tenant_key,
            str(payload.get("previous_response_id") or ""),
        )
        if continuation is None:
            return respond(_previous_response_not_found_response())
        payload = _inherit_responses_continuation_defaults(payload, continuation)
    try:
        request = canonicalize_payload(payload, api_format=endpoint)
    except ContentContractError as exc:
        return respond(
            _json_response(
                400,
                {"error": {"message": str(exc), "code": exc.code}},
            )
        )
    if continuation is not None:
        request = _merge_responses_continuation(request, continuation)
    try:
        response = active_engine.complete(request, live=bool(payload.get("live", live)))
    except FusionExecutionError as exc:
        status = 503 if exc.code == "no_eligible_model" else 502
        return respond(
            _json_response(
                status,
                {
                    "error": {"message": str(exc), "code": exc.code},
                    "metadata": {
                        "trace_summary": _safe_error_trace_summary(exc.trace),
                        "internal_details_redacted": True,
                        "provider_identifiers_redacted": True,
                        "raw_prompt_persisted": False,
                        "raw_provider_names_persisted": False,
                        "raw_provider_model_ids_persisted": False,
                        "raw_profile_ids_persisted": False,
                        "raw_provider_outputs_persisted": False,
                        "secrets_persisted": False,
                    },
                },
            )
        )
    responses_store: bool | None = None
    if endpoint == "responses":
        # Fusion's response cache intentionally reuses compute, not public
        # response identities. Every HTTP Responses result needs an ID that
        # belongs only to this caller's continuation scope.
        response = _fresh_responses_response(response)
        responses_store = False
        if record_response_continuations and _responses_store_requested(payload):
            responses_store = runtime_state().store_response_continuation(
                tenant_key=tenant_key,
                response_id=response.response_id,
                history=_response_continuation_history(request, response),
                model=request.model,
                instructions=request.system,
                tools=request.tools,
            )
    if _stream_requested(route, payload, endpoint):
        include_usage = _stream_usage_requested(payload, endpoint)
        rendered_for_cost = render_response(
            response,
            api_format=endpoint,
            responses_store=responses_store,
        )
        if record_runtime:
            runtime_state().record_cost(tenant_key, _actual_cost_from_rendered_response(rendered_for_cost))
        if record_trace:
            record_execution_trace(response, tenant_key=tenant_key)
        return respond(
            _stream_response(
                200,
                render_stream_events(
                    response,
                    api_format=endpoint,
                    responses_store=responses_store,
                    include_usage=include_usage,
                ),
            )
        )
    rendered = render_response(response, api_format=endpoint, responses_store=responses_store)
    if record_runtime:
        runtime_state().record_cost(tenant_key, _actual_cost_from_rendered_response(rendered))
    if record_trace:
        record_execution_trace(response, tenant_key=tenant_key)
    return respond(_json_response(200, rendered))


def _http_request_asks_for_incremental_stream(
    *,
    method: str,
    path: str,
    body: bytes | str | None,
) -> bool:
    """Identify only well-formed public inference streams before dispatch.

    Invalid JSON and non-inference routes stay on ``handle_request`` so they
    retain the existing buffered error semantics.  Authorization and quota
    checks deliberately happen later in the shared-equivalent preparation
    path, not in this predicate.
    """

    if method.upper() != "POST":
        return False
    route = urlparse(path).path.rstrip("/") or "/"
    endpoint = _endpoint_api_format(route)
    if not endpoint:
        return False
    try:
        payload = _decode_json(body)
    except ValueError:
        return False
    return _stream_requested(route, payload, endpoint)


def _http_request_asks_for_incremental_image_stream(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes | str | None,
) -> bool:
    if method.upper() != "POST":
        return False
    route = urlparse(path).path.rstrip("/") or "/"
    operation = image_route_kind(route)
    if not operation:
        return False
    headers_lc = {str(key).lower(): str(value) for key, value in headers.items()}
    try:
        payload = (
            parse_generation_payload(body)
            if operation == "generations"
            else parse_edit_payload(body, headers_lc.get("content-type", ""))[0]
        )
    except ImageRequestError:
        return False
    return payload.get("stream") is True


def _prepare_incremental_image_stream_request(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str] | None,
    body: bytes | str | None,
    engine: FusionEngine,
    live: bool,
    record_runtime: bool,
) -> tuple[_PreparedIncrementalImageStream | None, tuple[int, dict[str, str], bytes] | None]:
    """Validate image streaming controls before HTTP headers are committed."""

    del method, live
    headers_lc = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    route = urlparse(path).path.rstrip("/") or "/"

    def respond(response: tuple[int, dict[str, str], bytes]) -> tuple[int, dict[str, str], bytes]:
        return _apply_cors_headers(response, headers_lc)

    if not _authorized(headers_lc):
        return None, respond(
            _json_response(401, {"error": {"message": "Unauthorized", "code": "unauthorized"}})
        )
    tenant_key = tenant_key_from_headers(headers_lc)
    if record_runtime:
        rate = runtime_state().check_rate_limit(tenant_key)
        if not rate["allowed"]:
            return None, respond(
                _json_response(
                    429,
                    {"error": {"message": "Rate limit exceeded", "code": "rate_limit_exceeded"}},
                    extra_headers={"Retry-After": str(rate.get("retry_after_seconds") or 1)},
                )
            )
        budget = runtime_state().check_budget(tenant_key)
        if not budget["allowed"]:
            return None, respond(_tenant_budget_exhausted_response(budget))

    operation = image_route_kind(route)
    try:
        if operation == "generations":
            payload = parse_generation_payload(body)
            files: tuple[Any, ...] = ()
        else:
            parsed_payload, parsed_files = parse_edit_payload(
                body,
                headers_lc.get("content-type", ""),
            )
            payload = parsed_payload
            files = tuple(parsed_files)
    except ImageRequestError as exc:
        return None, respond(
            _json_response(exc.status, {"error": {"message": str(exc), "code": exc.code}})
        )
    return (
        _PreparedIncrementalImageStream(
            headers_lc=headers_lc,
            operation=operation,
            payload=payload,
            files=files,
            router=ImageRouter(engine.profiles),
            tenant_key=tenant_key,
        ),
        None,
    )


def _prepare_incremental_stream_request(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str] | None,
    body: bytes | str | None,
    engine: FusionEngine | None,
    live: bool,
    record_runtime: bool,
) -> tuple[_PreparedIncrementalStream | None, tuple[int, dict[str, str], bytes] | None]:
    """Apply the public control plane before an HTTP stream commits headers.

    This mirrors the inference portion of ``handle_request`` because a stream
    cannot call the buffered handler without losing its first-token timing.
    Keep the boundary intentionally narrow: all non-inference routes continue
    through the original synchronous dispatcher.
    """

    headers_lc = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    route = urlparse(path).path.rstrip("/") or "/"

    def respond(response: tuple[int, dict[str, str], bytes]) -> tuple[int, dict[str, str], bytes]:
        return _apply_cors_headers(response, headers_lc)

    if _operator_endpoint(route):
        if not _operator_authorized(
            headers_lc,
            require_explicit_operator_key=_operator_endpoint_requires_explicit_key(route),
        ):
            return None, respond(_operator_forbidden_response())
    elif not _authorized(headers_lc):
        return None, respond(
            _json_response(
                401,
                {"error": {"message": "Unauthorized", "code": "unauthorized"}},
            )
        )
    tenant_key = tenant_key_from_headers(headers_lc)
    if record_runtime:
        rate = runtime_state().check_rate_limit(tenant_key)
        if not rate["allowed"]:
            return None, respond(
                _json_response(
                    429,
                    {
                        "error": {"message": "Rate limit exceeded", "code": "rate_limit_exceeded"},
                        "metadata": {
                            "rate_limit": rate,
                            "raw_prompt_persisted": False,
                            "secrets_persisted": False,
                        },
                    },
                    extra_headers={"Retry-After": str(rate.get("retry_after_seconds") or 1)},
                )
            )
    active_engine = engine or FusionEngine(load_registry(require_prefusion=bool(live)))
    if method.upper() != "POST":
        return None, respond(
            _json_response(
                405,
                {"error": {"message": "Method not allowed", "code": "method_not_allowed"}},
            )
        )
    try:
        payload = _decode_json(body)
    except ValueError as exc:
        return None, respond(
            _json_response(400, {"error": {"message": str(exc), "code": "invalid_json"}})
        )
    endpoint = _endpoint_api_format(route)
    if not endpoint:
        return None, respond(
            _json_response(
                404,
                {"error": {"message": f"Unknown endpoint: {route}", "code": "not_found"}},
            )
        )
    if not _stream_requested(route, payload, endpoint):
        return None, respond(
            _json_response(
                400,
                {"error": {"message": "Streaming was not requested.", "code": "stream_not_requested"}},
            )
        )
    if record_runtime:
        budget = runtime_state().check_budget(tenant_key)
        if not budget["allowed"]:
            return None, respond(_tenant_budget_exhausted_response(budget))
    if endpoint == "gemini":
        route_model = _gemini_route_model(route)
        if route_model and "model" not in payload:
            payload = {**payload, "model": route_model}
    continuation: ResponseContinuation | None = None
    if endpoint == "responses" and "previous_response_id" in payload:
        continuation = runtime_state().get_response_continuation(
            tenant_key,
            str(payload.get("previous_response_id") or ""),
        )
        if continuation is None:
            return None, respond(_previous_response_not_found_response())
        payload = _inherit_responses_continuation_defaults(payload, continuation)
    try:
        request = canonicalize_payload(payload, api_format=endpoint)
    except ContentContractError as exc:
        return None, respond(
            _json_response(
                400,
                {"error": {"message": str(exc), "code": exc.code}},
            )
        )
    if continuation is not None:
        request = _merge_responses_continuation(request, continuation)
    return (
        _PreparedIncrementalStream(
            headers_lc=headers_lc,
            payload=payload,
            endpoint=endpoint,
            request=request,
            active_engine=active_engine,
            tenant_key=tenant_key,
            live=bool(payload.get("live", live)),
        ),
        None,
    )


def _finalize_incremental_stream_response(
    prepared: _PreparedIncrementalStream,
    response: FusionResponse,
    *,
    record_trace: bool,
    record_runtime: bool,
    record_response_continuations: bool,
) -> tuple[FusionResponse, bool | None]:
    """Apply the same post-completion accounting as the buffered dispatcher."""

    responses_store: bool | None = None
    if prepared.endpoint == "responses":
        responses_store = False
        if record_response_continuations and _responses_store_requested(prepared.payload):
            responses_store = runtime_state().store_response_continuation(
                tenant_key=prepared.tenant_key,
                response_id=response.response_id,
                history=_response_continuation_history(prepared.request, response),
                model=prepared.request.model,
                instructions=prepared.request.system,
                tools=prepared.request.tools,
            )
    rendered = render_response(
        response,
        api_format=prepared.endpoint,
        responses_store=responses_store,
    )
    if record_runtime:
        runtime_state().record_cost(
            prepared.tenant_key,
            _actual_cost_from_rendered_response(rendered),
        )
    if record_trace:
        record_execution_trace(response, tenant_key=prepared.tenant_key)
    return response, responses_store


def _incremental_stream_headers() -> dict[str, str]:
    return {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
    }


def _previous_response_not_found_response() -> tuple[int, dict[str, str], bytes]:
    """Use one public error for unknown, expired, and foreign response IDs."""

    return _json_response(
        404,
        {
            "error": {
                "message": "The previous response is unavailable.",
                "code": "previous_response_not_found",
            },
            "metadata": {
                "response_continuation": {
                    "available": False,
                    "storage_scope": "process_memory",
                    "durable": False,
                    "raw_session_ids_persisted": False,
                    "raw_response_context_persisted": False,
                },
                "raw_prompt_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            },
        },
    )


def _inherit_responses_continuation_defaults(
    payload: Mapping[str, Any],
    continuation: ResponseContinuation,
) -> dict[str, Any]:
    """Apply the prior public configuration only when the client omitted it."""

    effective = dict(payload)
    if not str(effective.get("model") or "").strip():
        effective["model"] = continuation.model
    if "instructions" not in effective:
        effective["instructions"] = continuation.instructions
    if "tools" not in effective:
        effective["tools"] = [dict(item) for item in continuation.tools]
    return effective


def _merge_responses_continuation(
    request: FusionRequest,
    continuation: ResponseContinuation,
) -> FusionRequest:
    """Join a stored Responses turn with new protocol-neutral input events."""

    prior = [dict(item) for item in continuation.history if isinstance(item, Mapping)]
    incoming = _response_input_events_from_request(request)
    merged = hydrate_tool_result_names(_append_response_history_without_duplicates(prior, incoming))
    metadata = dict(request.metadata)
    metadata["_axio_current_prompt_in_history"] = _history_contains_prompt(merged, request.prompt)
    return replace(request, history=tuple(merged), metadata=metadata)


def _response_input_events_from_request(request: FusionRequest) -> list[dict[str, Any]]:
    events = [dict(item) for item in request.history if isinstance(item, Mapping)]
    current_prompt_in_history = bool(request.metadata.get("_axio_current_prompt_in_history"))
    if request.prompt and not current_prompt_in_history:
        events.append({"role": "user", "content": request.prompt})
    return events


def _append_response_history_without_duplicates(
    prior: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Accept clients that resend complete history without doubling context."""

    result = [dict(item) for item in prior if isinstance(item, Mapping)]
    additions = [dict(item) for item in incoming if isinstance(item, Mapping)]
    if not result or not additions:
        return [*result, *additions]
    if _history_prefix_matches(additions, result):
        additions = additions[len(result):]
    else:
        overlap_limit = min(len(result), len(additions))
        for overlap in range(overlap_limit, 0, -1):
            if _history_rows_match(result[-overlap:], additions[:overlap]):
                additions = additions[overlap:]
                break
    return [*result, *additions]


def _history_prefix_matches(rows: Sequence[Mapping[str, Any]], prefix: Sequence[Mapping[str, Any]]) -> bool:
    return len(rows) >= len(prefix) and _history_rows_match(rows[:len(prefix)], prefix)


def _history_rows_match(left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]) -> bool:
    if len(left) != len(right):
        return False
    return all(stable_json(dict(a)) == stable_json(dict(b)) for a, b in zip(left, right))


def _history_contains_prompt(history: Sequence[Mapping[str, Any]], prompt: str) -> bool:
    if not prompt:
        return False
    last_user = next(
        (
            item
            for item in reversed(history)
            if isinstance(item, Mapping) and str(item.get("role") or "") == "user"
        ),
        None,
    )
    return bool(last_user is not None and str(last_user.get("content") or "") == prompt)


def _response_continuation_history(
    request: FusionRequest,
    response: FusionResponse,
) -> tuple[dict[str, Any], ...]:
    """Capture the completed public turn in private, protocol-neutral memory."""

    history = _response_input_events_from_request(request)
    tool_calls = [dict(call) for call in response.tool_calls if isinstance(call, Mapping)]
    if response.text or tool_calls:
        assistant: dict[str, Any] = {"role": "assistant", "content": str(response.text or "")}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        history.append(assistant)
    return tuple(hydrate_tool_result_names(history))


def _responses_store_requested(payload: Mapping[str, Any]) -> bool:
    return payload.get("store") is not False


def _fresh_responses_response(response: FusionResponse) -> FusionResponse:
    return replace(
        response,
        response_id=f"fusion-{uuid.uuid4().hex}",
        created=int(time.time()),
    )


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8789,
    *,
    live: bool = False,
    engine: FusionEngine | None = None,
    record_trace: bool = True,
    record_runtime: bool = True,
) -> ThreadingHTTPServer:
    """Build the standalone HTTP server without entering its blocking loop.

    Keeping construction separate from ``serve`` gives operator integrations and
    loopback tests a controlled lifecycle while preserving the production
    handler, authorization, and protocol behavior in one place.
    """

    active_engine = engine or FusionEngine(
        load_registry(require_prefusion=bool(live)),
        client=HTTPProviderClient(require_streaming=True),
    )
    runtime_handle = AtomicFusionRuntime(active_engine)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AxioFusionStandalone/0.1"
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._dispatch()

        def log_message(self, format: str, *args: Any) -> None:
            if os.getenv("AXIO_FUSION_ACCESS_LOG", "").lower() in {"1", "true", "yes"}:
                super().log_message(format, *args)

        def _dispatch(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            request_engine, _generation = runtime_handle.snapshot()
            if _http_request_asks_for_incremental_image_stream(
                method=self.command,
                path=self.path,
                headers=dict(self.headers),
                body=body,
            ):
                prepared, immediate = _prepare_incremental_image_stream_request(
                    method=self.command,
                    path=self.path,
                    headers=dict(self.headers),
                    body=body,
                    engine=request_engine,
                    live=live,
                    record_runtime=record_runtime,
                )
                if prepared is not None:
                    self._dispatch_incremental_image_stream(
                        prepared,
                        record_runtime=record_runtime,
                    )
                    return
                assert immediate is not None
                self._write_buffered_response(*immediate)
                return
            if _http_request_asks_for_incremental_stream(
                method=self.command,
                path=self.path,
                body=body,
            ):
                prepared, immediate = _prepare_incremental_stream_request(
                    method=self.command,
                    path=self.path,
                    headers=dict(self.headers),
                    body=body,
                    engine=request_engine,
                    live=live,
                    record_runtime=record_runtime,
                )
                if prepared is not None:
                    self._dispatch_incremental_stream(
                        prepared,
                        record_trace=record_trace,
                        record_runtime=record_runtime,
                    )
                    return
                assert immediate is not None
                self._write_buffered_response(*immediate)
                return
            status, response_headers, response_body = handle_request(
                method=self.command,
                path=self.path,
                headers=dict(self.headers),
                body=body,
                engine=request_engine,
                live=live,
                record_trace=record_trace,
                record_runtime=record_runtime,
            )
            self._write_buffered_response(status, response_headers, response_body)

        def _dispatch_incremental_image_stream(
            self,
            prepared: _PreparedIncrementalImageStream,
            *,
            record_runtime: bool,
        ) -> None:
            cancellation_event = threading.Event()
            public_model = str(prepared.payload.get("model") or "axio-terra")
            emitted_events = 0
            response_headers = _apply_cors_headers(
                (200, _incremental_stream_headers(), b""),
                prepared.headers_lc,
            )[1]
            self.send_response(200)
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.end_headers()

            def on_event(event: Mapping[str, Any]) -> bool:
                nonlocal emitted_events
                chunk = render_image_event(event, public_model=public_model)
                if not chunk:
                    return True
                emitted_events += 1
                return self._write_stream_chunk(chunk, cancellation_event)

            try:
                if prepared.operation == "generations":
                    _response, result, _profile = prepared.router.generate(
                        prepared.payload,
                        timeout=image_request_timeout(),
                        stream_observer=on_event,
                    )
                else:
                    _response, result, _profile = prepared.router.edit(
                        prepared.payload,
                        prepared.files,
                        timeout=image_request_timeout(),
                        stream_observer=on_event,
                    )
                if not cancellation_event.is_set():
                    if emitted_events == 0:
                        self._write_stream_chunk(
                            render_image_stream(result, public_model=public_model),
                            cancellation_event,
                        )
                    else:
                        self._write_stream_chunk(
                            b"event: done\ndata: [DONE]\n\n",
                            cancellation_event,
                        )
                    if record_runtime:
                        runtime_state().record_cost(prepared.tenant_key, 0.0)
            except ImageRequestError as exc:
                if not cancellation_event.is_set():
                    self._write_stream_chunk(
                        _render_image_stream_error(exc.code),
                        cancellation_event,
                    )
            except Exception:  # noqa: BLE001 - streaming HTTP boundary
                if not cancellation_event.is_set():
                    self._write_stream_chunk(
                        _render_image_stream_error("image_provider_unavailable"),
                        cancellation_event,
                    )
            finally:
                self._finish_stream(cancellation_event)

        def _write_buffered_response(
            self,
            status: int,
            response_headers: Mapping[str, str],
            response_body: bytes,
        ) -> None:
            self.send_response(status)
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response_body)

        def _dispatch_incremental_stream(
            self,
            prepared: _PreparedIncrementalStream,
            *,
            record_trace: bool,
            record_runtime: bool,
        ) -> None:
            cancellation_event = threading.Event()
            response_id = f"fusion-{uuid.uuid4().hex}"
            created = int(time.time())
            renderer = IncrementalStreamRenderer(
                prepared.request,
                api_format=prepared.endpoint,
                response_id=response_id,
                created=created,
                include_usage=_stream_usage_requested(
                    prepared.payload,
                    prepared.endpoint,
                ),
            )
            response_headers = _apply_cors_headers(
                (200, _incremental_stream_headers(), b""),
                prepared.headers_lc,
            )[1]
            self.send_response(200)
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.end_headers()
            if not self._write_stream_chunk(renderer.start(), cancellation_event):
                return

            def on_text_delta(text: str) -> bool:
                return self._write_stream_chunk(
                    renderer.text_delta(text),
                    cancellation_event,
                )

            try:
                response = prepared.active_engine.complete_stream(
                    prepared.request,
                    on_text_delta=on_text_delta,
                    live=prepared.live,
                    cancellation_event=cancellation_event,
                    response_id=response_id,
                    created=created,
                )
                if not cancellation_event.is_set():
                    response, responses_store = _finalize_incremental_stream_response(
                        prepared,
                        response,
                        record_trace=record_trace,
                        record_runtime=record_runtime,
                        record_response_continuations=True,
                    )
                    renderer.responses_store = responses_store
                    self._write_stream_chunk(renderer.complete(response), cancellation_event)
            except PublicStreamInterruptedError as exc:
                if not cancellation_event.is_set() and not exc.client_cancelled:
                    self._write_stream_chunk(
                        renderer.error(code=exc.code),
                        cancellation_event,
                    )
            except FusionExecutionError:
                if not cancellation_event.is_set():
                    self._write_stream_chunk(
                        renderer.error(code="stream_failed"),
                        cancellation_event,
                    )
            except Exception:  # noqa: BLE001 - HTTP boundary must not leak provider details
                if not cancellation_event.is_set():
                    self._write_stream_chunk(
                        renderer.error(code="stream_failed"),
                        cancellation_event,
                    )
            finally:
                self._finish_stream(cancellation_event)

        def _write_stream_chunk(
            self,
            payload: bytes,
            cancellation_event: threading.Event,
        ) -> bool:
            if cancellation_event.is_set():
                return False
            if not payload:
                return True
            try:
                self.wfile.write(f"{len(payload):X}\r\n".encode("ascii"))
                self.wfile.write(payload)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                cancellation_event.set()
                return False

        def _finish_stream(self, cancellation_event: threading.Event) -> None:
            if cancellation_event.is_set():
                return
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                cancellation_event.set()

    server = ThreadingHTTPServer((host, int(port)), Handler)
    server.daemon_threads = True
    server.runtime_engine_handle = runtime_handle
    server.axio_engine = active_engine

    def swap_engine(
        candidate: FusionEngine,
        *,
        expected_generation: int | None = None,
        reason: str = "runtime_refresh",
    ) -> dict[str, Any]:
        receipt = runtime_handle.swap(
            candidate,
            expected_generation=expected_generation,
            reason=reason,
        )
        if receipt.get("status") == "ready":
            server.axio_engine = candidate
        return receipt

    def rollback_engine(
        *,
        expected_generation: int | None = None,
        reason: str = "runtime_rollback",
    ) -> dict[str, Any]:
        receipt = runtime_handle.rollback(
            expected_generation=expected_generation,
            reason=reason,
        )
        if receipt.get("status") == "ready":
            current, _ = runtime_handle.snapshot()
            server.axio_engine = current
        return receipt

    server.swap_engine = swap_engine
    server.rollback_engine = rollback_engine
    server.runtime_engine_snapshot = runtime_handle.safe_snapshot
    _attach_runtime_refresh(server, runtime_handle)
    return server


def _attach_runtime_refresh(
    server: ThreadingHTTPServer,
    runtime_handle: AtomicFusionRuntime,
) -> None:
    """Attach the generic live-channel refresh operation to every server."""

    def refresh_runtime_channels(
        refresh_manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        expected_generation: int | None = None,
        reason: str = "runtime_refresh",
        live: bool = True,
        discovery_timeout: float = 15.0,
        enrollment_max_workers: int = 8,
        enrollment_max_models: int | None = None,
        enrollment_max_models_per_provider: int | None = None,
        enrollment_tool_probe_timeout: float | None = None,
        enrollment_tool_probe_max_models: int | None = None,
        enrollment_tool_probe_max_models_per_provider: int | None = None,
        enrollment_reasoning_probe_timeout: float | None = None,
        enrollment_reasoning_probe_max_models: int | None = None,
        enrollment_reasoning_probe_max_models_per_provider: int | None = None,
        enrollment_min_available_models: int = 1,
        enrollment_calibrate_tools: bool = True,
        enrollment_calibrate_reasoning: bool = True,
        environment: Mapping[str, Any] | None = None,
        secret_resolver: Any | None = None,
        client: HTTPProviderClient | None = None,
        engine_kwargs: Mapping[str, Any] | None = None,
        require_prefusion: bool | None = None,
        diagnostic_only: bool | None = None,
        focus_manifest: Mapping[str, Any] | str | Path | None = None,
        source_manifest: Mapping[str, Any] | str | Path | None = None,
        research_agent_config: Mapping[str, Any] | str | Path | None = None,
        research_output: Mapping[str, Any] | str | Path | None = None,
        prefusion_max_models: int | None = None,
        prefusion_research_batch_size: int | None = None,
        prefusion_research_max_workers: int | None = None,
        prefusion_stream_probe_samples: int | None = None,
        prefusion_total_budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Enroll a new channel portfolio and activate it as one generation.

        Discovery, text health, and tool calibration happen outside the
        activation lock. The active engine is therefore available throughout
        the potentially slow network phase. The generation captured before
        enrollment is passed to the final swap, so a concurrent operator
        change cannot be overwritten by a stale candidate.
        """

        current_engine, current_generation = runtime_handle.snapshot()
        if expected_generation is not None and int(expected_generation) != current_generation:
            return _runtime_refresh_blocked_receipt(
                reason_codes=["runtime_generation_conflict"],
                active_snapshot=runtime_handle.safe_snapshot(),
            )
        if not live:
            return _runtime_refresh_blocked_receipt(
                reason_codes=["live_flag_required_for_runtime_refresh"],
                active_snapshot=runtime_handle.safe_snapshot(),
            )

        from .provider_enrollment import enroll_runtime_channels

        effective_client = client or current_engine.client
        options = dict(engine_kwargs or {})
        options.setdefault("cache_enabled", current_engine.cache_enabled)
        options.setdefault("circuit_breaker_threshold", current_engine.circuit_breaker_threshold)
        runtime_requires_prefusion = bool(
            getattr(server, "runtime_prefusion_required", False)
        )
        effective_diagnostic_only = (
            False
            if runtime_requires_prefusion
            else (
                bool(diagnostic_only)
                if diagnostic_only is not None
                else bool(getattr(server, "runtime_diagnostic_only", False))
            )
        )
        effective_require_prefusion = (
            True
            if runtime_requires_prefusion
            else (
                bool(require_prefusion)
                if require_prefusion is not None
                else False
            )
        )
        try:
            enrollment = enroll_runtime_channels(
                refresh_manifest,
                environment=environment,
                secret_resolver=secret_resolver,
                timeout=discovery_timeout,
                max_workers=enrollment_max_workers,
                max_models=enrollment_max_models,
                max_models_per_provider=enrollment_max_models_per_provider,
                tool_probe_timeout=enrollment_tool_probe_timeout,
                tool_probe_max_models=enrollment_tool_probe_max_models,
                tool_probe_max_models_per_provider=enrollment_tool_probe_max_models_per_provider,
                reasoning_probe_timeout=enrollment_reasoning_probe_timeout,
                reasoning_probe_max_models=enrollment_reasoning_probe_max_models,
                reasoning_probe_max_models_per_provider=enrollment_reasoning_probe_max_models_per_provider,
                min_available_models=enrollment_min_available_models,
                calibrate_tools=enrollment_calibrate_tools,
                calibrate_reasoning=enrollment_calibrate_reasoning,
                live=live,
                client=effective_client,
                engine_kwargs=options,
                require_prefusion=effective_require_prefusion,
                diagnostic_only=effective_diagnostic_only,
                focus_manifest=focus_manifest,
                source_manifest=source_manifest,
                research_agent_config=research_agent_config,
                research_output=research_output,
                prefusion_max_models=prefusion_max_models,
                prefusion_research_batch_size=prefusion_research_batch_size,
                prefusion_research_max_workers=prefusion_research_max_workers,
                prefusion_stream_probe_samples=prefusion_stream_probe_samples,
                prefusion_total_budget_seconds=prefusion_total_budget_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - preserve the active service
            return _runtime_refresh_blocked_receipt(
                reason_codes=["runtime_enrollment_exception"],
                active_snapshot=runtime_handle.safe_snapshot(),
                exception_type=type(exc).__name__,
            )

        candidate = enrollment.get("engine") if isinstance(enrollment, Mapping) else None
        enrollment_receipt = (
            enrollment.get("receipt")
            if isinstance(enrollment, Mapping) and isinstance(enrollment.get("receipt"), Mapping)
            else {}
        )
        if not isinstance(candidate, FusionEngine):
            reason_codes = ["runtime_enrollment_produced_no_candidate_engine"]
            if isinstance(enrollment_receipt.get("reason_codes"), list):
                reason_codes.extend(
                    str(item) for item in enrollment_receipt["reason_codes"] if str(item)
                )
            return _runtime_refresh_blocked_receipt(
                reason_codes=reason_codes,
                active_snapshot=runtime_handle.safe_snapshot(),
                enrollment_receipt=enrollment_receipt,
            )

        activation = server.swap_engine(
            candidate,
            expected_generation=current_generation,
            reason=reason,
        )
        safe_enrollment = _safe_runtime_refresh_enrollment_receipt(enrollment_receipt)
        result = {
            "schema": "axio_fusion_api.runtime_refresh.v1",
            "status": "ready" if activation.get("status") == "ready" else "blocked",
            "operation": "refresh_runtime_channels",
            "activation": activation,
            "enrollment": safe_enrollment,
            "active": server.runtime_engine_snapshot(),
            "old_engine_preserved": True,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_prompts_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        }
        if activation.get("status") == "ready":
            server.runtime_channel_enrollment_receipt = dict(enrollment_receipt)
        server.runtime_channel_last_refresh_receipt = result
        return result

    server.refresh_runtime_channels = refresh_runtime_channels
    server.runtime_channel_last_refresh_receipt = {}


def create_runtime_http_server(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    host: str = "127.0.0.1",
    port: int = 8789,
    *,
    live: bool = True,
    discover: bool = False,
    enroll: bool = False,
    discovery_timeout: float = 15.0,
    enrollment_max_workers: int = 8,
    enrollment_max_models: int | None = None,
    enrollment_max_models_per_provider: int | None = None,
    enrollment_tool_probe_timeout: float | None = None,
    enrollment_tool_probe_max_models: int | None = None,
    enrollment_tool_probe_max_models_per_provider: int | None = None,
    enrollment_reasoning_probe_timeout: float | None = None,
    enrollment_reasoning_probe_max_models: int | None = None,
    enrollment_reasoning_probe_max_models_per_provider: int | None = None,
    enrollment_min_available_models: int = 1,
    enrollment_calibrate_tools: bool = True,
    enrollment_calibrate_reasoning: bool = True,
    environment: Mapping[str, Any] | None = None,
    secret_resolver: Any | None = None,
    client: HTTPProviderClient | None = None,
    record_trace: bool = True,
    record_runtime: bool = True,
    require_prefusion: bool = False,
    diagnostic_only: bool = False,
    focus_manifest: Mapping[str, Any] | str | Path | None = None,
    source_manifest: Mapping[str, Any] | str | Path | None = None,
    research_agent_config: Mapping[str, Any] | str | Path | None = None,
    research_output: Mapping[str, Any] | str | Path | None = None,
    prefusion_max_models: int | None = None,
    prefusion_research_batch_size: int | None = None,
    prefusion_research_max_workers: int | None = None,
    prefusion_stream_probe_samples: int | None = None,
    prefusion_total_budget_seconds: float | None = None,
    **engine_kwargs: Any,
) -> ThreadingHTTPServer:
    """Build a gateway directly from an in-memory arbitrary channel manifest.

    This is the programmatic deployment boundary for callers that receive
    endpoint/key values from a secret manager.  ``discover=True`` performs
    bounded ``/models`` discovery, but inventory discovery is not a production
    admission path.  It is rejected unless ``diagnostic_only=True`` is
    explicit.  ``enroll=True`` is the production dynamic path and therefore
    requires the pre-Fusion research ranking plus strict streaming/latency
    admission, unless the caller explicitly opts into ``diagnostic_only=True``
    for an operational fixture or compatibility diagnostic.  With
    ``require_prefusion=True``, the same gate is required even when the
    manifest does not carry a ``prefusion`` block.
    ``enroll`` implies discovery and is the recommended live path for a
    dynamic manifest.
    Otherwise the manifest's explicit model rows are used.  No manifest values
    are copied to registry or trace artifacts by this factory.
    """

    prefusion_configured = bool(
        isinstance(manifest, Mapping)
        and any(key in manifest for key in ("prefusion", "pre_fusion", "preFusion"))
    )
    # Dynamic enrollment creates a serving Engine. It must not silently
    # promote a provider inventory or an ordinary JSON health probe into
    # production. The explicit diagnostic escape hatch is for fixtures and
    # legacy operational inspection only.
    prefusion_required = bool(
        require_prefusion
        or prefusion_configured
        or (enroll and not diagnostic_only)
    )
    if prefusion_required and not enroll:
        raise ValueError(
            "runtime pre-Fusion screening requires enroll=True; "
            "discovery or static manifest loading cannot bypass the gate"
        )
    if discover and not live:
        raise ValueError(
            "runtime model discovery requires live=True because it performs network requests"
        )
    if discover and not enroll and not diagnostic_only:
        raise ValueError(
            "runtime model discovery is inventory-only; use enroll=True for "
            "pre-Fusion production admission or diagnostic_only=True for diagnostics"
        )
    if not enroll and not discover and not diagnostic_only:
        raise ValueError(
            "runtime channel serving requires enroll=True or a validated pre-Fusion registry; "
            "use diagnostic_only=True for static compatibility diagnostics"
        )

    from .channel_config import build_runtime_profiles, discover_runtime_profiles
    from .provider_enrollment import enroll_runtime_channels

    enrollment_receipt: Mapping[str, Any] = {}
    if enroll:
        enrollment = enroll_runtime_channels(
            manifest,
            environment=environment,
            secret_resolver=secret_resolver,
            timeout=discovery_timeout,
            max_workers=enrollment_max_workers,
            max_models=enrollment_max_models,
            max_models_per_provider=enrollment_max_models_per_provider,
            tool_probe_timeout=enrollment_tool_probe_timeout,
            tool_probe_max_models=enrollment_tool_probe_max_models,
            tool_probe_max_models_per_provider=enrollment_tool_probe_max_models_per_provider,
            reasoning_probe_timeout=enrollment_reasoning_probe_timeout,
            reasoning_probe_max_models=enrollment_reasoning_probe_max_models,
            reasoning_probe_max_models_per_provider=enrollment_reasoning_probe_max_models_per_provider,
            min_available_models=enrollment_min_available_models,
            calibrate_tools=enrollment_calibrate_tools,
            calibrate_reasoning=enrollment_calibrate_reasoning,
            live=live,
            client=client,
            engine_kwargs=engine_kwargs,
            require_prefusion=prefusion_required,
            diagnostic_only=diagnostic_only,
            focus_manifest=focus_manifest,
            source_manifest=source_manifest,
            research_agent_config=research_agent_config,
            research_output=research_output,
            prefusion_max_models=prefusion_max_models,
            prefusion_research_batch_size=prefusion_research_batch_size,
            prefusion_research_max_workers=prefusion_research_max_workers,
            prefusion_stream_probe_samples=prefusion_stream_probe_samples,
            prefusion_total_budget_seconds=prefusion_total_budget_seconds,
        )
        engine = enrollment.get("engine")
        enrollment_receipt = (
            enrollment.get("receipt")
            if isinstance(enrollment.get("receipt"), Mapping)
            else {}
        )
        if not isinstance(engine, FusionEngine):
            reason_codes = enrollment_receipt.get("reason_codes")
            detail = ", ".join(str(item) for item in reason_codes or [] if str(item))
            raise ValueError(
                "runtime channel enrollment produced no serving profiles"
                + (f": {detail}" if detail else "")
            )
    elif discover:
        discovery = discover_runtime_profiles(
            manifest,
            environment=environment,
            secret_resolver=secret_resolver,
            timeout=discovery_timeout,
        )
        profiles = list(discovery.get("profiles") or [])
    else:
        profiles = build_runtime_profiles(
            manifest,
            environment=environment,
            secret_resolver=secret_resolver,
        )
    if not enroll and not profiles:
        raise ValueError("runtime channel manifest produced no serving profiles")
    if not enroll:
        if diagnostic_only:
            active_client = client or HTTPProviderClient()
        else:
            active_client = ensure_strict_streaming_client(client)
        engine = FusionEngine(profiles, client=active_client, **engine_kwargs)
    server = create_http_server(
        host=host,
        port=port,
        live=live,
        engine=engine,
        record_trace=record_trace,
        record_runtime=record_runtime,
    )
    # The attached values are operator-only and safe: credentials stay in the
    # engine's process-local profiles, while the receipt contains status,
    # counts, and hashes only.
    server.axio_engine = engine
    server.runtime_prefusion_configured = prefusion_configured
    server.runtime_prefusion_required = prefusion_required
    server.runtime_diagnostic_only = bool(diagnostic_only)
    server.runtime_channel_enrollment_receipt = dict(enrollment_receipt)
    return server


def _runtime_refresh_blocked_receipt(
    *,
    reason_codes: Sequence[str],
    active_snapshot: Mapping[str, Any],
    enrollment_receipt: Mapping[str, Any] | None = None,
    exception_type: str = "",
) -> dict[str, Any]:
    result = {
        "schema": "axio_fusion_api.runtime_refresh.v1",
        "status": "blocked",
        "operation": "refresh_runtime_channels",
        "reason_codes": sorted({str(item)[:120] for item in reason_codes if str(item)}),
        "exception_type": str(exception_type)[:80] if exception_type else "",
        "enrollment": _safe_runtime_refresh_enrollment_receipt(enrollment_receipt or {}),
        "active": dict(active_snapshot),
        "old_engine_preserved": True,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_prompts_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    return result


def _safe_runtime_refresh_enrollment_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project enrollment status without trusting arbitrary nested payloads."""

    if not isinstance(value, Mapping):
        return {"status": "unknown"}
    prefusion = value.get("prefusion")
    prefusion = prefusion if isinstance(prefusion, Mapping) else {}
    safe_prefusion = {
        "schema": str(
            prefusion.get("schema")
            or "axio_fusion_api.runtime_prefusion_receipt.v1"
        )[:120],
        "required": prefusion.get("required") is True,
        "status": str(prefusion.get("status") or "unknown")[:40],
        "candidate_logical_model_count": _safe_nonnegative_int(
            prefusion.get("candidate_logical_model_count")
        ),
        "ranked_logical_model_count": _safe_nonnegative_int(
            prefusion.get("ranked_logical_model_count")
        ),
        "available_logical_model_count": _safe_nonnegative_int(
            prefusion.get("available_logical_model_count")
        ),
        "eligible_physical_profile_count": _safe_nonnegative_int(
            prefusion.get("eligible_physical_profile_count")
        ),
        "available_model_list_sha256": str(
            prefusion.get("available_model_list_sha256") or ""
        )[:128],
        "registry_content_sha256": str(
            prefusion.get("registry_content_sha256") or ""
        )[:128],
        "research_status": str(prefusion.get("research_status") or "unknown")[:40],
        "research_output_sha256": str(
            prefusion.get("research_output_sha256") or ""
        )[:128],
        "stream_request_count": _safe_nonnegative_int(
            prefusion.get("stream_request_count")
        ),
        "stream_observed_count": _safe_nonnegative_int(
            prefusion.get("stream_observed_count")
        ),
        "stream_fallback_count": _safe_nonnegative_int(
            prefusion.get("stream_fallback_count")
        ),
        "latency_ceiling_ms": _safe_nonnegative_int(
            prefusion.get("latency_ceiling_ms") or 90_000
        ),
        "ranking_prior_only": prefusion.get("ranking_prior_only") is True,
        "live_stream_gate_required": prefusion.get("live_stream_gate_required") is True,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }
    result: dict[str, Any] = {
        "schema": str(value.get("schema") or "axio_fusion_api.runtime_channel_enrollment.v1")[:120],
        "status": str(value.get("status") or "unknown")[:40],
        "admission_mode": str(value.get("admission_mode") or "unknown")[:40],
        "production_admission": value.get("production_admission") is True,
        "diagnostic_only": value.get("diagnostic_only") is True,
        "reason_codes": [str(item)[:120] for item in value.get("reason_codes", []) if str(item)]
        if isinstance(value.get("reason_codes"), list)
        else [],
        "warning_codes": [str(item)[:120] for item in value.get("warning_codes", []) if str(item)]
        if isinstance(value.get("warning_codes"), list)
        else [],
        "network_calls_performed": value.get("network_calls_performed") is True,
        "discovery_provider_count": _safe_nonnegative_int(value.get("discovery_provider_count")),
        "discovery_failed_provider_count": _safe_nonnegative_int(value.get("discovery_failed_provider_count")),
        "discovery_skipped_provider_count": _safe_nonnegative_int(value.get("discovery_skipped_provider_count")),
        "discovered_profile_count": _safe_nonnegative_int(value.get("discovered_profile_count")),
        "probed_profile_count": _safe_nonnegative_int(value.get("probed_profile_count")),
        "available_profile_count": _safe_nonnegative_int(value.get("available_profile_count")),
        "available_logical_model_count": _safe_nonnegative_int(
            value.get("available_logical_model_count")
        ),
        "unavailable_profile_count": _safe_nonnegative_int(value.get("unavailable_profile_count")),
        "latency_ceiling_ms": _safe_nonnegative_int(
            prefusion.get("latency_ceiling_ms") or 90_000
        ),
        "prefusion_status": str(prefusion.get("status") or "unknown")[:40],
        "prefusion_candidate_logical_model_count": _safe_nonnegative_int(
            prefusion.get("candidate_logical_model_count")
        ),
        "prefusion_ranked_logical_model_count": _safe_nonnegative_int(
            prefusion.get("ranked_logical_model_count")
        ),
        "prefusion_available_logical_model_count": _safe_nonnegative_int(
            prefusion.get("available_logical_model_count")
        ),
        "prefusion_eligible_physical_profile_count": _safe_nonnegative_int(
            prefusion.get("eligible_physical_profile_count")
        ),
        "prefusion_stream_request_count": _safe_nonnegative_int(
            prefusion.get("stream_request_count")
        ),
        "prefusion_stream_observed_count": _safe_nonnegative_int(
            prefusion.get("stream_observed_count")
        ),
        "prefusion_stream_fallback_count": _safe_nonnegative_int(
            prefusion.get("stream_fallback_count")
        ),
        "prefusion_available_model_list_sha256": str(
            prefusion.get("available_model_list_sha256") or ""
        )[:128],
        "prefusion_registry_content_sha256": str(
            prefusion.get("registry_content_sha256") or ""
        )[:128],
        "prefusion": safe_prefusion,
        "tool_probe_selected_model_count": _safe_nonnegative_int(value.get("tool_probe_selected_model_count")),
        "tool_probe_supported_count": _safe_nonnegative_int(value.get("tool_probe_supported_count")),
        "tool_probe_text_only_count": _safe_nonnegative_int(value.get("tool_probe_text_only_count")),
        "tool_probe_failure_count": _safe_nonnegative_int(value.get("tool_probe_failure_count")),
        "reasoning_probe_selected_model_count": _safe_nonnegative_int(value.get("reasoning_probe_selected_model_count")),
        "reasoning_probe_verified_count": _safe_nonnegative_int(value.get("reasoning_probe_verified_count")),
        "reasoning_probe_rejected_count": _safe_nonnegative_int(value.get("reasoning_probe_rejected_count")),
        "reasoning_probe_indeterminate_count": _safe_nonnegative_int(value.get("reasoning_probe_indeterminate_count")),
        "elapsed_ms": _safe_nonnegative_int(value.get("elapsed_ms")),
        "profile_set_sha256": str(value.get("profile_set_sha256") or "")[:128],
    }
    for key in (
        "raw_provider_names_persisted",
        "raw_provider_model_ids_persisted",
        "raw_provider_urls_persisted",
        "raw_provider_outputs_persisted",
        "raw_probe_prompts_persisted",
        "raw_api_keys_persisted",
        "secrets_persisted",
    ):
        result[key] = False
    return result


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def serve(host: str = "127.0.0.1", port: int = 8789, *, live: bool = False) -> None:
    profiles = load_registry(require_prefusion=True)
    if not profiles:
        raise ValueError("production pre-Fusion registry contains no enabled profiles")
    server = create_http_server(
        host=host,
        port=port,
        live=live,
        engine=FusionEngine(profiles, client=HTTPProviderClient(require_streaming=True)),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


def build_api_surface_protocol_self_test(
    *,
    registry_path: str | None = None,
    models: Sequence[str] = (),
    prompt: str | None = None,
    task_type: str = "api_surface_protocol_self_test",
) -> dict[str, Any]:
    """Exercise the public protocol adapters without storing prompt or output text."""

    selected_models = _selected_api_surface_models(models)
    test_prompt = prompt or "Confirm Axio API surface protocol readiness in one short sentence."
    engine = FusionEngine(
        load_registry(registry_path),
        client=HTTPProviderClient(require_streaming=True),
    )
    rows = []
    for model in selected_models:
        for api_format in API_SURFACE_PROTOCOL_FORMATS:
            endpoint, payload = _api_surface_self_test_payload(
                model=model,
                api_format=api_format,
                prompt=test_prompt,
                task_type=task_type,
            )
            status, response_headers, response_body = handle_request(
                method="POST",
                path=endpoint,
                headers=_api_surface_self_test_headers(),
                body=json.dumps(payload, ensure_ascii=False),
                engine=engine,
                live=False,
                record_response_continuations=False,
            )
            rows.append(
                _api_surface_self_test_row(
                    model=model,
                    api_format=api_format,
                    status=status,
                    response_headers=response_headers,
                    response_body=response_body,
                )
            )
    per_model = _api_surface_self_test_model_summary(rows)
    digest_input = {
        "schema": "axio_fusion_api.api_surface_protocol_self_test_digest.v1",
        "models": selected_models,
        "api_formats": list(API_SURFACE_PROTOCOL_FORMATS),
        "rows": [
            {
                "public_model": row["public_model"],
                "api_format": row["api_format"],
                "status_code": row["status_code"],
                "protocol_passed": row["protocol_passed"],
                "response_model_matches_request": row["response_model_matches_request"],
                "response_shape_ok": row["response_shape_ok"],
                "route_summary_digest_sha256": row["route_summary_digest_sha256"],
                "answer_sha256": row["answer_sha256"],
            }
            for row in rows
        ],
    }
    all_rows_passed = bool(rows) and all(row["protocol_passed"] is True for row in rows)
    route_consistent = bool(per_model) and all(row["route_consistent_across_surfaces"] is True for row in per_model)
    return {
        "schema": "axio_fusion_api.api_surface_protocol_self_test.v1",
        "mode": "dry_gateway_protocol_self_test",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "public_model_count": len(selected_models),
        "public_models": selected_models,
        "api_surface_count": len(API_SURFACE_PROTOCOL_FORMATS),
        "api_surfaces": list(API_SURFACE_PROTOCOL_FORMATS),
        "expected_request_count": len(selected_models) * len(API_SURFACE_PROTOCOL_FORMATS),
        "completed_request_count": len(rows),
        "passed_request_count": sum(1 for row in rows if row["protocol_passed"] is True),
        "failed_request_count": sum(1 for row in rows if row["protocol_passed"] is not True),
        "all_required_protocols_ready": all_rows_passed,
        "all_models_route_consistent_across_surfaces": route_consistent,
        "ready_for_live_api_surface_benchmarking": all_rows_passed and route_consistent,
        "prompt_fingerprint_sha256": sha256_text(test_prompt),
        "task_type": str(task_type or ""),
        "per_model": per_model,
        "rows": rows,
        "protocol_self_test_digest_sha256": sha256_text(stable_json(digest_input)),
        "anti_leakage_contract": {
            "network_calls_performed": False,
            "raw_prompt_persisted": False,
            "raw_response_text_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "secrets_persisted": False,
        },
        "network_calls_performed": False,
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }


def build_api_surface_live_smoke(
    *,
    registry_path: str | None = None,
    models: Sequence[str] = (),
    prompt: str | None = None,
    task_type: str = "api_surface_live_smoke",
    max_latency_ms: int = 12_000,
    max_output_tokens: int = 48,
    live: bool = False,
    client: Any | None = None,
    require_live_credentials: bool = True,
) -> dict[str, Any]:
    """Run a bounded, hash-only public API smoke test when explicitly enabled.

    This validates that each public Axio protocol can reach the configured
    provider pool through the same in-process gateway used by the service. It
    is intentionally much smaller than a Fusion-quality or benchmark run: each
    request permits one primary call plus at most one bounded provider fallback,
    and no benchmark content is used.
    """

    selected_models = _selected_api_surface_models(models)
    test_prompt = prompt or "Return one concise readiness sentence."
    profiles = load_registry(registry_path)
    readiness = registry_readiness(profiles)
    credentialed_profiles = [profile for profile in profiles if _profile_has_live_credentials(profile)]
    active_profiles = credentialed_profiles if require_live_credentials else list(profiles)
    active_client = ensure_strict_streaming_client(client)
    bounded_latency_ms = max(1_000, min(60_000, int(max_latency_ms or 12_000)))
    bounded_output_tokens = max(1, min(256, int(max_output_tokens or 48)))
    # A live surface check must exercise the same direct-cascade recovery that
    # production Fast routes advertise.  Two calls are still a fixed, bounded
    # smoke envelope and are not evidence of Fusion quality or latency gains.
    bounded_call_count = 2
    preflight_reason_codes: list[str] = []
    if not live:
        preflight_reason_codes.append("live_flag_required")
    if not profiles:
        preflight_reason_codes.append("empty_registry")
    if readiness.get("ready") is not True:
        preflight_reason_codes.append("registry_not_ready")
    if require_live_credentials and not credentialed_profiles:
        preflight_reason_codes.append("live_provider_credentials_required")
    if not active_profiles and not (require_live_credentials and not credentialed_profiles):
        preflight_reason_codes.append("no_eligible_live_provider_profiles")
    preflight_ready = not preflight_reason_codes
    rows: list[dict[str, Any]] = []
    if preflight_ready:
        for model in selected_models:
            for api_format in API_SURFACE_PROTOCOL_FORMATS:
                endpoint, payload = _api_surface_live_smoke_payload(
                    model=model,
                    api_format=api_format,
                    prompt=test_prompt,
                    task_type=task_type,
                    max_latency_ms=bounded_latency_ms,
                    max_output_tokens=bounded_output_tokens,
                    max_total_model_calls=bounded_call_count,
                )
                # Each row uses a fresh engine so cache and circuit state from
                # one protocol cannot mask an incompatibility in another.
                engine = FusionEngine(active_profiles, client=active_client, cache_enabled=False)
                started = time.monotonic()
                status, response_headers, response_body = handle_request(
                    method="POST",
                    path=endpoint,
                    headers=_api_surface_self_test_headers(),
                    body=json.dumps(payload, ensure_ascii=False),
                    engine=engine,
                    live=True,
                    record_trace=False,
                    record_runtime=False,
                    record_response_continuations=False,
                )
                rows.append(
                    _api_surface_live_smoke_row(
                        model=model,
                        api_format=api_format,
                        status=status,
                        response_headers=response_headers,
                        response_body=response_body,
                        end_to_end_latency_ms=(time.monotonic() - started) * 1000,
                    )
                )
    per_model = _api_surface_live_smoke_model_summary(rows)
    all_rows_passed = bool(rows) and all(row["live_smoke_passed"] is True for row in rows)
    route_consistent = bool(per_model) and all(row["route_consistent_across_surfaces"] is True for row in per_model)
    network_transport_attempted = bool(live and rows and isinstance(active_client, HTTPProviderClient))
    digest_input = {
        "schema": "axio_fusion_api.api_surface_live_smoke_digest.v1",
        "public_models": selected_models,
        "api_surfaces": list(API_SURFACE_PROTOCOL_FORMATS),
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
        "rows": [
            {
                "public_model": row["public_model"],
                "api_format": row["api_format"],
                "status_code": row["status_code"],
                "live_smoke_passed": row["live_smoke_passed"],
                "live_provider_call_observed": row["live_provider_call_observed"],
                "route_summary_digest_sha256": row["route_summary_digest_sha256"],
                "answer_sha256": row["answer_sha256"],
                "error_code": row["error_code"],
            }
            for row in rows
        ],
    }
    return {
        "schema": "axio_fusion_api.api_surface_live_smoke.v1",
        "mode": "live_public_api_smoke" if live else "dry_run_requires_live_flag",
        "status": "passed" if preflight_ready and all_rows_passed and route_consistent else "failed" if preflight_ready else "blocked",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "live_requested": bool(live),
        "preflight_ready": preflight_ready,
        "preflight_reason_codes": sorted(set(preflight_reason_codes)),
        "public_model_count": len(selected_models),
        "public_models": selected_models,
        "api_surface_count": len(API_SURFACE_PROTOCOL_FORMATS),
        "api_surfaces": list(API_SURFACE_PROTOCOL_FORMATS),
        "expected_request_count": len(selected_models) * len(API_SURFACE_PROTOCOL_FORMATS),
        "attempted_request_count": len(rows),
        "passed_request_count": sum(1 for row in rows if row["live_smoke_passed"] is True),
        "failed_request_count": sum(1 for row in rows if row["live_smoke_passed"] is not True),
        "all_required_public_api_surfaces_live": all_rows_passed,
        "all_models_route_consistent_across_surfaces": route_consistent,
        "provider_call_observed_request_count": sum(1 for row in rows if row["live_provider_call_observed"] is True),
        "network_transport_attempted": network_transport_attempted,
        "network_calls_performed": network_transport_attempted,
        "prompt_fingerprint_sha256": sha256_text(test_prompt),
        "task_type": str(task_type or ""),
        "bounded_call_policy": {
            "max_models": 1,
            "max_depth": 0,
            "max_total_model_calls": bounded_call_count,
            "max_latency_ms": bounded_latency_ms,
            "max_output_tokens": bounded_output_tokens,
            "cache_disabled": True,
            "execution_traces_written": False,
            "runtime_budget_accounting_written": False,
            "not_a_benchmark": True,
            "does_not_prove_fusion_quality": True,
            "does_not_prove_latency_superiority": True,
        },
        "registry_summary": {
            "registry_ready": readiness.get("ready") is True,
            "registry_status": str(readiness.get("status") or ""),
            "registry_profile_count": len(profiles),
            "registry_profile_set_sha256": _profile_set_sha256(profiles),
            "credentialed_profile_count": len(credentialed_profiles),
            "credentialed_profile_set_sha256": _profile_set_sha256(credentialed_profiles),
            "eligible_profile_count": len(active_profiles),
            "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_key_env_names_persisted": False,
            "raw_api_keys_persisted": False,
            "secrets_persisted": False,
        },
        "per_model": per_model,
        "rows": rows,
        "live_smoke_digest_sha256": sha256_text(stable_json(digest_input)),
        "no_cheat_contract": {
            "benchmark_questions_used": False,
            "benchmark_labels_used": False,
            "benchmark_scores_emitted": False,
            "model_superiority_claimed": False,
            "provider_baseline_ranking_changed": False,
        },
        "anti_leakage_contract": {
            "raw_prompt_persisted": False,
            "raw_response_text_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def build_api_surface_stream_live_smoke(
    *,
    registry_path: str | None = None,
    models: Sequence[str] = (),
    prompt: str | None = None,
    task_type: str = "api_surface_stream_live_smoke",
    max_latency_ms: int = 12_000,
    max_output_tokens: int = 48,
    live: bool = False,
    client: Any | None = None,
    require_live_credentials: bool = True,
) -> dict[str, Any]:
    """Exercise all public streaming protocols through the live gateway.

    The regular API smoke validates JSON response compatibility. This companion
    check validates the streaming contract actually exposed to callers: a
    framed SSE response, the protocol-native terminal sequence, a response
    model matching the requested Axio tier, visible generated text, and an
    observed upstream provider call. It is deliberately a small operational
    check, not a quality or latency-superiority experiment.
    """

    selected_models = _selected_api_surface_models(models)
    test_prompt = prompt or "Return one concise streaming readiness sentence."
    profiles = load_registry(registry_path)
    readiness = registry_readiness(profiles)
    credentialed_profiles = [
        profile for profile in profiles if _profile_has_live_credentials(profile)
    ]
    active_profiles = credentialed_profiles if require_live_credentials else list(profiles)
    active_client = ensure_strict_streaming_client(client)
    bounded_latency_ms = max(1_000, min(60_000, int(max_latency_ms or 12_000)))
    bounded_output_tokens = max(1, min(256, int(max_output_tokens or 48)))
    bounded_call_count = 2
    preflight_reason_codes: list[str] = []
    if not live:
        preflight_reason_codes.append("live_flag_required")
    if not profiles:
        preflight_reason_codes.append("empty_registry")
    if readiness.get("ready") is not True:
        preflight_reason_codes.append("registry_not_ready")
    if require_live_credentials and not credentialed_profiles:
        preflight_reason_codes.append("live_provider_credentials_required")
    if not active_profiles and not (
        require_live_credentials and not credentialed_profiles
    ):
        preflight_reason_codes.append("no_eligible_live_provider_profiles")
    preflight_ready = not preflight_reason_codes
    rows: list[dict[str, Any]] = []
    if preflight_ready:
        for model in selected_models:
            for api_format in API_SURFACE_PROTOCOL_FORMATS:
                endpoint, payload = _api_surface_stream_live_smoke_payload(
                    model=model,
                    api_format=api_format,
                    prompt=test_prompt,
                    task_type=task_type,
                    max_latency_ms=bounded_latency_ms,
                    max_output_tokens=bounded_output_tokens,
                    max_total_model_calls=bounded_call_count,
                )
                # Fresh engines keep a prior API surface's cache or circuit
                # state from hiding a protocol-specific streaming defect.
                engine = FusionEngine(
                    active_profiles,
                    client=active_client,
                    cache_enabled=False,
                )
                started = time.monotonic()
                status, response_headers, response_body = handle_request(
                    method="POST",
                    path=endpoint,
                    headers=_api_surface_self_test_headers(),
                    body=json.dumps(payload, ensure_ascii=False),
                    engine=engine,
                    live=True,
                    record_trace=False,
                    record_runtime=False,
                    record_response_continuations=False,
                )
                rows.append(
                    _api_surface_stream_live_smoke_row(
                        model=model,
                        api_format=api_format,
                        status=status,
                        response_headers=response_headers,
                        response_body=response_body,
                        end_to_end_latency_ms=(time.monotonic() - started) * 1000,
                    )
                )
    per_model = _api_surface_stream_live_smoke_model_summary(
        rows,
        models=selected_models,
    )
    all_rows_passed = bool(rows) and all(
        row["stream_live_smoke_passed"] is True for row in rows
    )
    all_models_complete = bool(per_model) and all(
        row["all_required_stream_surfaces_live"] is True for row in per_model
    )
    network_transport_attempted = bool(
        live and rows and isinstance(active_client, HTTPProviderClient)
    )
    digest_input = {
        "schema": "axio_fusion_api.api_surface_stream_live_smoke_digest.v1",
        "public_models": selected_models,
        "api_surfaces": list(API_SURFACE_PROTOCOL_FORMATS),
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
        "rows": [
            {
                "public_model": row["public_model"],
                "api_format": row["api_format"],
                "status_code": row["status_code"],
                "stream_live_smoke_passed": row["stream_live_smoke_passed"],
                "stream_terminal_semantics_ok": row["stream_terminal_semantics_ok"],
                "live_provider_call_observed": row["live_provider_call_observed"],
                "stream_body_sha256": row["stream_body_sha256"],
                "error_code": row["error_code"],
            }
            for row in rows
        ],
    }
    return {
        "schema": "axio_fusion_api.api_surface_stream_live_smoke.v1",
        "mode": "live_public_api_stream_smoke"
        if live
        else "dry_run_requires_live_flag",
        "status": "passed"
        if preflight_ready and all_rows_passed and all_models_complete
        else "failed"
        if preflight_ready
        else "blocked",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "live_requested": bool(live),
        "preflight_ready": preflight_ready,
        "preflight_reason_codes": sorted(set(preflight_reason_codes)),
        "public_model_count": len(selected_models),
        "public_models": selected_models,
        "api_surface_count": len(API_SURFACE_PROTOCOL_FORMATS),
        "api_surfaces": list(API_SURFACE_PROTOCOL_FORMATS),
        "expected_request_count": len(selected_models) * len(API_SURFACE_PROTOCOL_FORMATS),
        "attempted_request_count": len(rows),
        "passed_request_count": sum(
            1 for row in rows if row["stream_live_smoke_passed"] is True
        ),
        "failed_request_count": sum(
            1 for row in rows if row["stream_live_smoke_passed"] is not True
        ),
        "all_required_public_streaming_surfaces_live": all_rows_passed,
        "all_models_streaming_complete_across_surfaces": all_models_complete,
        "provider_call_observed_request_count": sum(
            1 for row in rows if row["live_provider_call_observed"] is True
        ),
        "network_transport_attempted": network_transport_attempted,
        "network_calls_performed": network_transport_attempted,
        "prompt_fingerprint_sha256": sha256_text(test_prompt),
        "task_type": str(task_type or ""),
        "bounded_call_policy": {
            "max_models": 1,
            "max_depth": 0,
            "max_total_model_calls": bounded_call_count,
            "max_latency_ms": bounded_latency_ms,
            "max_output_tokens": bounded_output_tokens,
            "cache_disabled": True,
            "execution_traces_written": False,
            "runtime_budget_accounting_written": False,
            "strict_upstream_streaming_required": True,
            "not_a_benchmark": True,
            "does_not_prove_fusion_quality": True,
            "does_not_prove_latency_superiority": True,
        },
        "registry_summary": {
            "registry_ready": readiness.get("ready") is True,
            "registry_status": str(readiness.get("status") or ""),
            "registry_profile_count": len(profiles),
            "registry_profile_set_sha256": _profile_set_sha256(profiles),
            "credentialed_profile_count": len(credentialed_profiles),
            "credentialed_profile_set_sha256": _profile_set_sha256(
                credentialed_profiles
            ),
            "eligible_profile_count": len(active_profiles),
            "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_key_env_names_persisted": False,
            "raw_api_keys_persisted": False,
            "secrets_persisted": False,
        },
        "per_model": per_model,
        "rows": rows,
        "live_stream_smoke_digest_sha256": sha256_text(stable_json(digest_input)),
        "no_cheat_contract": {
            "benchmark_questions_used": False,
            "benchmark_labels_used": False,
            "benchmark_scores_emitted": False,
            "model_superiority_claimed": False,
            "provider_baseline_ranking_changed": False,
        },
        "anti_leakage_contract": {
            "raw_prompt_persisted": False,
            "raw_response_text_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def build_fast_path_live_diagnostic(
    *,
    registry_path: str | None = None,
    api_format: str = "chat/completions",
    prompt: str | None = None,
    task_type: str = "fast_path_live_diagnostic",
    max_latency_ms: int = 12_000,
    max_output_tokens: int = 48,
    live: bool = False,
    client: Any | None = None,
    require_live_credentials: bool = True,
) -> dict[str, Any]:
    """Run one bounded streaming request against ``axio-fast``.

    This is an operator diagnostic rather than a smoke matrix: it isolates a
    single public protocol and allows exactly one upstream model call.  The
    response body remains in memory only long enough to derive hashes and the
    existing redacted stream/error receipt.
    """

    requested_api_format = normalize_api_format(str(api_format or "chat/completions"))
    test_prompt = prompt or "Return one concise Fast-path diagnostic sentence."
    profiles = load_registry(registry_path)
    readiness = registry_readiness(profiles)
    credentialed_profiles = [
        profile for profile in profiles if _profile_has_live_credentials(profile)
    ]
    active_profiles = credentialed_profiles if require_live_credentials else list(profiles)
    active_client = ensure_strict_streaming_client(client)
    bounded_latency_ms = max(1_000, min(60_000, int(max_latency_ms or 12_000)))
    bounded_output_tokens = max(1, min(256, int(max_output_tokens or 48)))
    preflight_reason_codes: list[str] = []
    if requested_api_format not in API_SURFACE_PROTOCOL_FORMATS:
        preflight_reason_codes.append("api_format_invalid")
    if not live:
        preflight_reason_codes.append("live_flag_required")
    if not profiles:
        preflight_reason_codes.append("empty_registry")
    if readiness.get("ready") is not True:
        preflight_reason_codes.append("registry_not_ready")
    if require_live_credentials and not credentialed_profiles:
        preflight_reason_codes.append("live_provider_credentials_required")
    if not active_profiles and not (
        require_live_credentials and not credentialed_profiles
    ):
        preflight_reason_codes.append("no_eligible_live_provider_profiles")
    preflight_ready = not preflight_reason_codes
    row: dict[str, Any] = {}
    response_body = b""
    response_status: int | None = None
    response_headers: Mapping[str, str] = {}
    end_to_end_latency_ms = 0.0
    if preflight_ready:
        endpoint, payload = _api_surface_stream_live_smoke_payload(
            model="axio-fast",
            api_format=requested_api_format,
            prompt=test_prompt,
            task_type=task_type,
            max_latency_ms=bounded_latency_ms,
            max_output_tokens=bounded_output_tokens,
            max_total_model_calls=1,
        )
        engine = FusionEngine(
            active_profiles,
            client=active_client,
            cache_enabled=False,
        )
        started = time.monotonic()
        response_status, response_headers, response_body = handle_request(
            method="POST",
            path=endpoint,
            headers=_api_surface_self_test_headers(),
            body=json.dumps(payload, ensure_ascii=False),
            engine=engine,
            live=True,
            record_trace=False,
            record_runtime=False,
            record_response_continuations=False,
        )
        end_to_end_latency_ms = (time.monotonic() - started) * 1000
        row = _api_surface_stream_live_smoke_row(
            model="axio-fast",
            api_format=requested_api_format,
            status=response_status,
            response_headers=response_headers,
            response_body=response_body,
            end_to_end_latency_ms=end_to_end_latency_ms,
        )
    response_body_sha256 = sha256_text(
        response_body.decode("utf-8", errors="replace")
    ) if response_body else ""
    error_trace_summary = (
        row.get("error_trace_summary")
        if isinstance(row.get("error_trace_summary"), Mapping)
        else {"present": False, "raw_trace_persisted": False}
    )
    selected_profile_hashes = [
        str(item)
        for item in error_trace_summary.get("selected_profile_hashes", [])
        if isinstance(item, str)
        and len(item) == 64
        and all(character in "0123456789abcdef" for character in item.lower())
    ][:24] if isinstance(error_trace_summary.get("selected_profile_hashes"), list) else []
    row_passed = row.get("stream_live_smoke_passed") is True
    network_transport_attempted = bool(
        live and row and isinstance(active_client, HTTPProviderClient)
    )
    diagnostic_input = {
        "schema": "axio_fusion_api.fast_path_live_diagnostic_digest.v1",
        "public_model": "axio-fast",
        "api_format": requested_api_format,
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
        "status_code": response_status,
        "stream_live_smoke_passed": row_passed,
        "live_provider_call_observed": row.get("live_provider_call_observed") is True,
        "response_body_sha256": response_body_sha256,
        "selected_profile_hashes": selected_profile_hashes,
        "error_code": str(row.get("error_code") or ""),
    }
    return {
        "schema": "axio_fusion_api.fast_path_live_diagnostic.v1",
        "mode": "live_fast_path_diagnostic" if live else "dry_run_requires_live_flag",
        "status": "passed" if preflight_ready and row_passed else "failed" if preflight_ready else "blocked",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "live_requested": bool(live),
        "preflight_ready": preflight_ready,
        "preflight_reason_codes": sorted(set(preflight_reason_codes)),
        "public_model": "axio-fast",
        "api_format": requested_api_format,
        "attempted_request_count": 1 if row else 0,
        "response_status_code": response_status,
        "response_body_sha256": response_body_sha256,
        "response_body_byte_count": len(response_body),
        "end_to_end_latency_ms": round(max(0.0, float(end_to_end_latency_ms)), 3),
        "live_provider_call_observed": row.get("live_provider_call_observed") is True,
        "selected_profile_hashes": selected_profile_hashes,
        "error_code": str(row.get("error_code") or ""),
        "error_trace_summary": error_trace_summary,
        "row": row,
        "provider_call_observed_request_count": 1 if row.get("live_provider_call_observed") is True else 0,
        "network_transport_attempted": network_transport_attempted,
        "network_calls_performed": network_transport_attempted,
        "prompt_fingerprint_sha256": sha256_text(test_prompt),
        "task_type": str(task_type or ""),
        "bounded_call_policy": {
            "max_models": 1,
            "max_depth": 0,
            "max_total_model_calls": 1,
            "max_latency_ms": bounded_latency_ms,
            "max_output_tokens": bounded_output_tokens,
            "cache_disabled": True,
            "execution_traces_written": False,
            "runtime_budget_accounting_written": False,
            "strict_upstream_streaming_required": True,
            "single_request_only": True,
            "fallback_disabled": True,
            "not_a_benchmark": True,
            "does_not_prove_fusion_quality": True,
            "does_not_prove_latency_superiority": True,
        },
        "registry_summary": {
            "registry_ready": readiness.get("ready") is True,
            "registry_status": str(readiness.get("status") or ""),
            "registry_profile_count": len(profiles),
            "registry_profile_set_sha256": _profile_set_sha256(profiles),
            "credentialed_profile_count": len(credentialed_profiles),
            "credentialed_profile_set_sha256": _profile_set_sha256(credentialed_profiles),
            "eligible_profile_count": len(active_profiles),
            "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_key_env_names_persisted": False,
            "raw_api_keys_persisted": False,
            "secrets_persisted": False,
        },
        "diagnostic_digest_sha256": sha256_text(stable_json(diagnostic_input)),
        "no_cheat_contract": {
            "benchmark_questions_used": False,
            "benchmark_labels_used": False,
            "benchmark_scores_emitted": False,
            "model_superiority_claimed": False,
            "provider_baseline_ranking_changed": False,
        },
        "anti_leakage_contract": {
            "raw_prompt_persisted": False,
            "raw_response_text_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def build_fusion_deliberation_live_smoke(
    *,
    registry_path: str | None = None,
    models: Sequence[str] = (),
    prompt: str | None = None,
    task_type: str = "fusion_deliberation_live_smoke",
    max_latency_ms: int = 30_000,
    max_output_tokens: int = 128,
    max_total_model_calls: int = 6,
    max_cost_usd: float = 0.02,
    live: bool = False,
    client: Any | None = None,
    require_live_credentials: bool = True,
) -> dict[str, Any]:
    """Exercise a bounded, complete Fusion path without using benchmark data.

    The public API smoke intentionally uses a direct cascade, so it cannot
    prove that the expert panel, Judge, and Synthesizer can work together
    against a live mixed-provider registry. This separate operator probe uses
    a synthetic non-benchmark task, keeps all response content in memory, and
    emits only counts, hashes, timing, and public route summaries.
    """

    selected_models = _selected_fusion_deliberation_models(models)
    test_prompt = prompt or (
        "Assess a bounded synthetic scientific code decision, compare plausible "
        "approaches, state uncertainty, and give one concise risk-aware recommendation."
    )
    profiles = load_registry(registry_path)
    readiness = registry_readiness(profiles)
    credentialed_profiles = [profile for profile in profiles if _profile_has_live_credentials(profile)]
    active_profiles = credentialed_profiles if require_live_credentials else list(profiles)
    active_client = ensure_strict_streaming_client(client)
    # Keep the operator smoke aligned with the runtime's hard 90-second
    # provider eligibility ceiling. A lower caller-supplied bound remains
    # respected, while a compliant near-ceiling chain is not cut off by the
    # diagnostic wrapper itself.
    bounded_latency_ms = max(3_000, min(90_000, int(max_latency_ms or 30_000)))
    bounded_output_tokens = max(32, min(256, int(max_output_tokens or 128)))
    # A complete three-branch Fusion pass may need two bounded panel repairs
    # plus one same-request cross-model fallback for each mandatory control
    # stage. Keep the diagnostic ceiling high enough to exercise that admitted
    # recovery shape while the runtime's global call budget remains authoritative.
    bounded_call_count = max(4, min(10, int(max_total_model_calls or 6)))
    bounded_cost_usd = max(0.0001, min(0.05, float(max_cost_usd or 0.02)))
    preflight_reason_codes: list[str] = []
    if not live:
        preflight_reason_codes.append("live_flag_required")
    if not profiles:
        preflight_reason_codes.append("empty_registry")
    if readiness.get("ready") is not True:
        preflight_reason_codes.append("registry_not_ready")
    if require_live_credentials and not credentialed_profiles:
        preflight_reason_codes.append("live_provider_credentials_required")
    if not active_profiles and not (require_live_credentials and not credentialed_profiles):
        preflight_reason_codes.append("no_eligible_live_provider_profiles")
    preflight_ready = not preflight_reason_codes
    rows: list[dict[str, Any]] = []
    if preflight_ready:
        for model in selected_models:
            request = canonicalize_payload(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": test_prompt}],
                    "task_type": task_type,
                    "quality_target": 0.90,
                    "max_models": 3,
                    "max_depth": 1,
                    "max_latency_ms": bounded_latency_ms,
                    "max_output_tokens": bounded_output_tokens,
                    "max_total_model_calls": bounded_call_count,
                    "max_cost_usd": bounded_cost_usd,
                },
                api_format="chat/completions",
            )
            engine = FusionEngine(active_profiles, client=active_client, cache_enabled=False)
            started = time.monotonic()
            try:
                response = engine.complete(request, live=True)
                rows.append(
                    _fusion_deliberation_live_smoke_row(
                        model=model,
                        response=response,
                        end_to_end_latency_ms=(time.monotonic() - started) * 1000,
                        max_total_model_calls=bounded_call_count,
                    )
                )
            except FusionExecutionError as exc:
                rows.append(
                    _fusion_deliberation_live_smoke_failure_row(
                        model=model,
                        error_code=_safe_fusion_smoke_error_code(exc.code),
                        end_to_end_latency_ms=(time.monotonic() - started) * 1000,
                    )
                )
            except Exception as exc:  # noqa: PERF203 - operator probe boundary
                rows.append(
                    _fusion_deliberation_live_smoke_failure_row(
                        model=model,
                        error_code=_safe_fusion_smoke_error_code(type(exc).__name__),
                        end_to_end_latency_ms=(time.monotonic() - started) * 1000,
                    )
                )
    all_rows_passed = bool(rows) and all(row["deliberation_smoke_passed"] is True for row in rows)
    network_transport_attempted = bool(live and rows and isinstance(active_client, HTTPProviderClient))
    digest_input = {
        "schema": "axio_fusion_api.fusion_deliberation_live_smoke_digest.v1",
        "public_models": selected_models,
        "registry_profile_set_sha256": _profile_set_sha256(profiles),
        "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
        "rows": [
            {
                "public_model": row["public_model"],
                "deliberation_smoke_passed": row["deliberation_smoke_passed"],
                "fusion_activated": row["fusion_activated"],
                "complete_admitted_fusion_finalized": row["complete_admitted_fusion_finalized"],
                "judge_output_accepted": row["judge_output_accepted"],
                "synthesis_output_accepted": row["synthesis_output_accepted"],
                "hermes_process_contract_required": row[
                    "hermes_process_contract_required"
                ],
                "hermes_process_contract_completed": row[
                    "hermes_process_contract_completed"
                ],
                "hermes_aggregator_output_accepted": row[
                    "hermes_aggregator_output_accepted"
                ],
                "judge_provider_call_count": row["judge_provider_call_count"],
                "synthesis_provider_call_count": row["synthesis_provider_call_count"],
                "judge_stage": row["judge_stage"],
                "synthesizer_stage": row["synthesizer_stage"],
                "early_exit_triggered": row["early_exit_triggered"],
                "provider_call_count": row["provider_call_count"],
                "answer_sha256": row["answer_sha256"],
                "error_code": row["error_code"],
            }
            for row in rows
        ],
    }
    return {
        "schema": "axio_fusion_api.fusion_deliberation_live_smoke.v1",
        "mode": "live_fusion_deliberation_smoke" if live else "dry_run_requires_live_flag",
        "status": "passed" if preflight_ready and all_rows_passed else "failed" if preflight_ready else "blocked",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "live_requested": bool(live),
        "preflight_ready": preflight_ready,
        "preflight_reason_codes": sorted(set(preflight_reason_codes)),
        "public_model_count": len(selected_models),
        "public_models": selected_models,
        "expected_request_count": len(selected_models),
        "attempted_request_count": len(rows),
        "passed_request_count": sum(1 for row in rows if row["deliberation_smoke_passed"] is True),
        "failed_request_count": sum(1 for row in rows if row["deliberation_smoke_passed"] is not True),
        "all_required_fusion_deliberation_paths_live": all_rows_passed,
        "network_transport_attempted": network_transport_attempted,
        "network_calls_performed": network_transport_attempted,
        "prompt_fingerprint_sha256": sha256_text(test_prompt),
        "task_type": str(task_type or ""),
        "bounded_execution_policy": {
            "quality_target": 0.90,
            "max_models": 3,
            "max_depth": 1,
            "max_total_model_calls": bounded_call_count,
            "max_latency_ms": bounded_latency_ms,
            "max_output_tokens": bounded_output_tokens,
            "max_cost_usd": round(bounded_cost_usd, 8),
            "cache_disabled": True,
            "execution_traces_written": False,
            "runtime_budget_accounting_written": False,
            "not_a_benchmark": True,
            "does_not_prove_fusion_quality": True,
            "does_not_prove_latency_superiority": True,
        },
        "completion_contract": {
            "process_receipt_contract_version": 2,
            "requires_fusion_admission": True,
            "requires_multiple_completed_candidate_branches": True,
            "requires_provider_judge_call": True,
            "requires_provider_judge_call_for_provider_stage_fusion": True,
            "allows_local_consensus_finalization": True,
            # Retained for readers of the v1 additive schema. The explicit
            # fields below narrow controlled early exit to non-Hermes routes.
            "requires_synthesizer_call_or_controlled_early_exit": True,
            "requires_synthesizer_call_or_controlled_early_exit_for_non_hermes_routes": True,
            "requires_hermes_acting_synthesizer_when_hermes_enabled": True,
            "requires_hermes_process_contract_completion_when_enabled": True,
            "requires_complete_admitted_fusion_finalization": True,
        },
        "registry_summary": {
            "registry_ready": readiness.get("ready") is True,
            "registry_status": str(readiness.get("status") or ""),
            "registry_profile_count": len(profiles),
            "registry_profile_set_sha256": _profile_set_sha256(profiles),
            "credentialed_profile_count": len(credentialed_profiles),
            "credentialed_profile_set_sha256": _profile_set_sha256(credentialed_profiles),
            "eligible_profile_count": len(active_profiles),
            "eligible_profile_set_sha256": _profile_set_sha256(active_profiles),
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_key_env_names_persisted": False,
            "raw_api_keys_persisted": False,
            "secrets_persisted": False,
        },
        "rows": rows,
        "deliberation_smoke_digest_sha256": sha256_text(stable_json(digest_input)),
        "no_cheat_contract": {
            "benchmark_questions_used": False,
            "benchmark_labels_used": False,
            "benchmark_scores_emitted": False,
            "model_superiority_claimed": False,
            "provider_baseline_ranking_changed": False,
        },
        "anti_leakage_contract": {
            "raw_prompt_persisted": False,
            "raw_response_text_persisted": False,
            "raw_candidate_text_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _selected_fusion_deliberation_models(models: Sequence[str]) -> list[str]:
    selected = [str(model) for model in models if str(model) in PUBLIC_MODELS]
    return list(dict.fromkeys(selected)) or list(FUSION_DELIBERATION_SMOKE_DEFAULT_MODELS)


def _fusion_deliberation_live_smoke_row(
    *,
    model: str,
    response: Any,
    end_to_end_latency_ms: float,
    max_total_model_calls: int,
) -> dict[str, Any]:
    route_plan = response.route_plan if isinstance(response.route_plan, Mapping) else {}
    trace = response.trace if isinstance(response.trace, Mapping) else {}
    admission = route_plan.get("fusion_admission") if isinstance(route_plan.get("fusion_admission"), Mapping) else {}
    runtime_outcome = trace.get("runtime_fusion_stage_outcome") if isinstance(trace.get("runtime_fusion_stage_outcome"), Mapping) else {}
    early_exit = trace.get("early_exit") if isinstance(trace.get("early_exit"), Mapping) else {}
    hermes_plan = route_plan.get("hermes_moa") if isinstance(route_plan.get("hermes_moa"), Mapping) else {}
    hermes_execution = trace.get("hermes_moa_execution") if isinstance(trace.get("hermes_moa_execution"), Mapping) else {}
    feedback_stage_admission = (
        trace.get("feedback_stage_admission")
        if isinstance(trace.get("feedback_stage_admission"), Mapping)
        else {}
    )
    budget = route_plan.get("budget") if isinstance(route_plan.get("budget"), Mapping) else {}
    finalization_mode = str(
        route_plan.get("fusion_finalization_mode")
        or budget.get("fusion_finalization_mode")
        or admission.get("fusion_finalization_mode")
        or "direct"
    )
    local_consensus_finalized = bool(
        finalization_mode == "local_consensus"
        and runtime_outcome.get("local_consensus_finalized") is True
    )
    fusion_activated = admission.get("activated") is True
    completed_candidate_count = max(0, _optional_int(runtime_outcome.get("completed_candidate_count")) or 0)
    judge_provider_call_count = max(0, _optional_int(trace.get("judge_provider_call_count")) or 0)
    synthesis_provider_call_count = max(0, _optional_int(trace.get("synthesis_provider_call_count")) or 0)
    provider_call_count = max(0, _optional_int(trace.get("provider_call_count")) or 0)
    early_exit_triggered = early_exit.get("triggered") is True
    complete_finalized = runtime_outcome.get("complete_admitted_fusion_finalized") is True
    hermes_process_contract_required = bool(
        hermes_plan.get("enabled") is True
        or runtime_outcome.get("hermes_process_contract_required") is True
    )
    hermes_execution_enabled = hermes_execution.get("enabled") is True
    hermes_process_contract_completed = bool(
        hermes_process_contract_required
        and hermes_execution.get("process_contract_completed") is True
        and runtime_outcome.get("hermes_process_contract_completed") is True
    )
    judge_output_accepted = runtime_outcome.get("judge_output_accepted") is True
    synthesis_output_accepted = runtime_outcome.get("synthesis_output_accepted") is True
    hermes_reference_completed_count = max(
        0,
        _optional_int(runtime_outcome.get("hermes_reference_completed_count")) or 0,
    )
    hermes_feedback_reference_required = (
        hermes_execution.get("feedback_reference_required") is True
    )
    hermes_feedback_reference_completed = (
        hermes_execution.get("feedback_reference_completed") is True
    )
    hermes_rejudge_after_feedback_completed = (
        hermes_execution.get("rejudge_after_feedback_completed") is True
    )
    hermes_aggregator_output_accepted = bool(
        hermes_execution.get("aggregator_output_accepted") is True
    )
    synthesis_compression = (
        trace.get("synthesis_compression")
        if isinstance(trace.get("synthesis_compression"), Mapping)
        else {}
    )
    synthesis_replica_routing = (
        synthesis_compression.get("synthesizer_replica_routing")
        if isinstance(synthesis_compression.get("synthesizer_replica_routing"), Mapping)
        else {}
    )
    judge_result = (
        trace.get("judge_result")
        if isinstance(trace.get("judge_result"), Mapping)
        else {}
    )
    judge_replica_routing = (
        judge_result.get("judge_replica_routing")
        if isinstance(judge_result.get("judge_replica_routing"), Mapping)
        else {}
    )
    judge_stage = _safe_stage_attempt_summary(judge_replica_routing)
    synthesizer_stage = _safe_stage_attempt_summary(synthesis_replica_routing)
    synthesis_attempt_receipts = [
        row
        for row in synthesis_replica_routing.get("stage_attempt_receipts", [])
        if isinstance(row, Mapping)
    ]
    synthesis_attempt_status_counts: dict[str, int] = {}
    synthesis_http_status_counts: dict[str, int] = {}
    for attempt in synthesis_attempt_receipts:
        status = str(attempt.get("status") or "unknown")[:40]
        synthesis_attempt_status_counts[status] = (
            synthesis_attempt_status_counts.get(status, 0) + 1
        )
        http_status = _optional_int(attempt.get("http_status"))
        if http_status is not None and 100 <= http_status <= 599:
            key = str(http_status)
            synthesis_http_status_counts[key] = (
                synthesis_http_status_counts.get(key, 0) + 1
            )
    synthesis_stage_failure_count = synthesis_attempt_status_counts.get("failed", 0)
    synthesis_stage_empty_count = synthesis_attempt_status_counts.get("empty", 0)
    synthesis_stage_skipped_count = synthesis_attempt_status_counts.get("skipped", 0)
    if synthesis_output_accepted:
        synthesis_terminal_category = "completed"
    elif synthesis_replica_routing.get("terminal_reason") == "max_total_model_calls_exhausted":
        synthesis_terminal_category = "call_budget_exhausted"
    elif synthesis_replica_routing.get("terminal_reason") == "max_latency_ms_exhausted":
        synthesis_terminal_category = "deadline_exhausted"
    elif synthesis_replica_routing.get("terminal_reason") == "max_cost_usd_exhausted":
        synthesis_terminal_category = "cost_budget_exhausted"
    elif any(
        500 <= (_optional_int(attempt.get("http_status")) or 0) <= 599
        for attempt in synthesis_attempt_receipts
        if attempt.get("status") == "failed"
    ):
        synthesis_terminal_category = "provider_http_error_5xx"
    elif synthesis_stage_failure_count:
        synthesis_terminal_category = "provider_error"
    elif synthesis_stage_empty_count:
        synthesis_terminal_category = "empty_provider_output"
    elif synthesis_stage_skipped_count:
        synthesis_terminal_category = "stage_attempt_skipped"
    elif synthesis_provider_call_count <= 0:
        synthesis_terminal_category = "not_attempted"
    else:
        synthesis_terminal_category = "unknown"
    reason_codes: list[str] = []
    if not str(response.text or "").strip():
        reason_codes.append("response_text_missing")
    if response.provider_calls_recorded is not True or provider_call_count <= 0:
        reason_codes.append("live_provider_call_not_recorded")
    if not fusion_activated:
        reason_codes.append("fusion_not_activated")
    if completed_candidate_count < 2:
        reason_codes.append("insufficient_completed_candidate_branches")
    if finalization_mode == "local_consensus":
        if not local_consensus_finalized:
            reason_codes.append("local_consensus_not_finalized")
    elif judge_provider_call_count < 1:
        reason_codes.append("provider_judge_not_executed")
    elif not judge_output_accepted:
        reason_codes.append("provider_judge_output_not_accepted")
    if hermes_process_contract_required and not hermes_execution_enabled:
        reason_codes.append("hermes_process_execution_missing")
    if hermes_process_contract_required and synthesis_provider_call_count < 1:
        reason_codes.append("hermes_acting_synthesizer_not_executed")
    if hermes_process_contract_required and early_exit_triggered:
        reason_codes.append("hermes_acting_synthesizer_bypassed_by_early_exit")
    if hermes_process_contract_required and not hermes_aggregator_output_accepted:
        reason_codes.append("hermes_acting_synthesizer_output_not_accepted")
    if hermes_process_contract_required and not hermes_process_contract_completed:
        reason_codes.append("hermes_process_contract_incomplete")
    if (
        finalization_mode != "local_consensus"
        and not hermes_process_contract_required
        and synthesis_provider_call_count < 1
        and not early_exit_triggered
    ):
        reason_codes.append("synthesizer_or_controlled_early_exit_missing")
    if not complete_finalized:
        reason_codes.append("complete_admitted_fusion_not_finalized")
    if provider_call_count > max(1, int(max_total_model_calls)):
        reason_codes.append("provider_call_budget_exceeded")
    public_route = public_route_summary(route_plan)
    # Keep the live operator probe actionable without widening its privacy
    # boundary.  The regular public error projection already reduces candidate
    # receipts to allowlisted error classes/codes, hashes, and bounded counts;
    # reuse that exact projection here so a successful-but-degraded Fusion run
    # exposes why a panel or control stage did not complete.
    error_trace_summary = _safe_error_trace_summary(trace)
    return {
        "schema": "axio_fusion_api.fusion_deliberation_live_smoke_row.v1",
        "public_model": str(model),
        "deliberation_smoke_passed": not reason_codes,
        "fusion_activated": fusion_activated,
        "complete_admitted_fusion_finalized": complete_finalized,
        "completed_candidate_count": completed_candidate_count,
        "fusion_finalization_mode": finalization_mode,
        "local_consensus_finalized": local_consensus_finalized,
        "judge_output_accepted": judge_output_accepted,
        "synthesis_output_accepted": synthesis_output_accepted,
        "judge_parse_failed": bool(
            (trace.get("judge_result") or {}).get("judge_parse_failed") is True
            if isinstance(trace.get("judge_result"), Mapping)
            else False
        ),
        "hermes_reference_completed_count": hermes_reference_completed_count,
        "hermes_feedback_reference_required": hermes_feedback_reference_required,
        "hermes_feedback_reference_completed": hermes_feedback_reference_completed,
        "hermes_rejudge_after_feedback_completed": hermes_rejudge_after_feedback_completed,
        "hermes_process_contract_required": hermes_process_contract_required,
        "hermes_execution_enabled": hermes_execution_enabled,
        "hermes_process_contract_completed": hermes_process_contract_completed,
        "hermes_aggregator_output_accepted": hermes_aggregator_output_accepted,
        "synthesis_provider_output_accepted": bool(
            synthesis_compression.get("provider_synthesis_output_accepted") is True
        ),
        "synthesis_provider_fallback_used": bool(
            synthesis_compression.get("provider_synthesis_fallback_used") is True
        ),
        "synthesis_terminal_reason": str(
            synthesis_replica_routing.get("terminal_reason") or ""
        )[:120],
        "synthesis_terminal_category": synthesis_terminal_category,
        "synthesis_stage_attempt_count": max(
            0,
            _optional_int(synthesis_replica_routing.get("stage_attempt_count"))
            or len(synthesis_attempt_receipts),
        ),
        "synthesis_stage_failure_count": synthesis_stage_failure_count,
        "synthesis_stage_empty_count": synthesis_stage_empty_count,
        "synthesis_stage_skipped_count": synthesis_stage_skipped_count,
        "synthesis_stage_attempt_status_counts": dict(
            sorted(synthesis_attempt_status_counts.items())
        ),
        "synthesis_http_status_counts": dict(
            sorted(synthesis_http_status_counts.items())
        ),
        "judge_stage": judge_stage,
        "synthesizer_stage": synthesizer_stage,
        "synthesis_cross_model_failover_attempted": bool(
            synthesis_replica_routing.get("cross_model_failover_attempted") is True
        ),
        "synthesis_cross_model_failover_used": bool(
            synthesis_replica_routing.get("cross_model_failover_used") is True
        ),
        "synthesis_fallback_reservation_admission_attempted": bool(
            feedback_stage_admission.get("synthesizer_fallback_admission_attempted")
            is True
        ),
        "synthesis_fallback_reservation_admitted": bool(
            feedback_stage_admission.get("synthesizer_fallback_reservation_admitted")
            is True
        ),
        "judge_provider_call_count": judge_provider_call_count,
        "synthesis_provider_call_count": synthesis_provider_call_count,
        "early_exit_triggered": early_exit_triggered,
        "provider_call_count": provider_call_count,
        "end_to_end_latency_ms": round(max(0.0, float(end_to_end_latency_ms)), 3),
        "answer_sha256": sha256_text(str(response.text or "")),
        "answer_char_count": len(str(response.text or "")),
        "route_summary_digest_sha256": sha256_text(stable_json(_api_surface_route_digest_input(public_route))),
        "error_trace_summary": error_trace_summary,
        "error_code": "",
        "reason_codes": sorted(set(reason_codes)),
        "raw_response_text_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _fusion_deliberation_live_smoke_failure_row(
    *,
    model: str,
    error_code: str,
    end_to_end_latency_ms: float,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.fusion_deliberation_live_smoke_row.v1",
        "public_model": str(model),
        "deliberation_smoke_passed": False,
        "fusion_activated": False,
        "complete_admitted_fusion_finalized": False,
        "completed_candidate_count": 0,
        "hermes_process_contract_required": False,
        "hermes_execution_enabled": False,
        "hermes_process_contract_completed": False,
        "hermes_aggregator_output_accepted": False,
        "judge_provider_call_count": 0,
        "synthesis_provider_call_count": 0,
        "early_exit_triggered": False,
        "provider_call_count": 0,
        "synthesis_terminal_reason": "",
        "synthesis_terminal_category": "not_attempted",
        "synthesis_stage_attempt_count": 0,
        "synthesis_stage_failure_count": 0,
        "synthesis_stage_empty_count": 0,
        "synthesis_stage_skipped_count": 0,
        "synthesis_stage_attempt_status_counts": {},
        "synthesis_http_status_counts": {},
        "judge_stage": _safe_stage_attempt_summary({}),
        "synthesizer_stage": _safe_stage_attempt_summary({}),
        "synthesis_cross_model_failover_attempted": False,
        "synthesis_cross_model_failover_used": False,
        "synthesis_fallback_reservation_admission_attempted": False,
        "synthesis_fallback_reservation_admitted": False,
        "end_to_end_latency_ms": round(max(0.0, float(end_to_end_latency_ms)), 3),
        "answer_sha256": "",
        "answer_char_count": 0,
        "route_summary_digest_sha256": "",
        "error_trace_summary": {
            "present": False,
            "raw_trace_persisted": False,
        },
        "error_code": error_code,
        "reason_codes": ["fusion_execution_failed"],
        "raw_response_text_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _safe_fusion_smoke_error_code(value: Any) -> str:
    code = str(value or "")[:120]
    if code and all(character.isalnum() or character in {"_", "-", ":"} for character in code):
        return code
    return "fusion_execution_error"


def _safe_stage_attempt_summary(routing: Mapping[str, Any]) -> dict[str, Any]:
    """Project one internal control-stage receipt into safe bounded counts."""

    attempts = (
        routing.get("stage_attempt_receipts")
        if isinstance(routing.get("stage_attempt_receipts"), list)
        else []
    )
    status_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    error_code_counts: dict[str, int] = {}
    error_class_counts: dict[str, int] = {}
    http_status_counts: dict[str, int] = {}
    for attempt in attempts[:24]:
        if not isinstance(attempt, Mapping):
            continue
        status = str(attempt.get("status") or "unknown")[:40]
        status_counts[status] = status_counts.get(status, 0) + 1
        reason = str(attempt.get("reason") or "")[:80]
        if reason and all(
            character.isalnum() or character in {"_", "-", ":"}
            for character in reason
        ):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        http_status = safe_provider_http_status(attempt.get("http_status"))
        if http_status is not None:
            key = str(http_status)
            http_status_counts[key] = http_status_counts.get(key, 0) + 1
        safe_code = safe_provider_error_code(attempt.get("error_code"))
        if safe_code:
            error_code_counts[safe_code] = error_code_counts.get(safe_code, 0) + 1
            error_class = safe_provider_error_class(safe_code, http_status)
            if error_class:
                error_class_counts[error_class] = error_class_counts.get(error_class, 0) + 1
    return {
        "schema": "axio_fusion_api.safe_stage_attempt_summary.v1",
        "attempt_count": len(attempts[:24]),
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "error_code_counts": dict(sorted(error_code_counts.items())),
        "error_class_counts": dict(sorted(error_class_counts.items())),
        "http_status_counts": dict(sorted(http_status_counts.items())),
        "provider_attempt_count": max(
            0,
            _optional_int(routing.get("stage_attempt_count")) or len(attempts[:24]),
        ),
        "terminal_reason": (
            _safe_fusion_smoke_error_code(routing.get("terminal_reason"))
            if routing.get("terminal_reason")
            else ""
        ),
        "cross_model_failover_attempted": routing.get("cross_model_failover_attempted") is True,
        "cross_model_failover_used": routing.get("cross_model_failover_used") is True,
        "same_canonical_retry_admission_count": max(
            0,
            _optional_int(routing.get("same_canonical_retry_admission_count")) or 0,
        ),
        "raw_stage_output_persisted": False,
        "raw_provider_identifiers_persisted": False,
        "secrets_persisted": False,
    }


def _selected_api_surface_models(models: Sequence[str]) -> list[str]:
    selected = [str(model) for model in (models or PUBLIC_MODELS) if str(model) in PUBLIC_MODELS]
    return list(dict.fromkeys(selected)) or list(PUBLIC_MODELS)


def _api_surface_live_smoke_payload(
    *,
    model: str,
    api_format: str,
    prompt: str,
    task_type: str,
    max_latency_ms: int,
    max_output_tokens: int,
    max_total_model_calls: int,
) -> tuple[str, dict[str, Any]]:
    endpoint, payload = _api_surface_self_test_payload(
        model=model,
        api_format=api_format,
        prompt=prompt,
        task_type=task_type,
    )
    result = dict(payload)
    result.update(
        {
            "live": True,
            "max_models": 1,
            "max_depth": 0,
            "max_total_model_calls": max_total_model_calls,
        }
    )
    # ``max_latency_ms`` is the operator probe's outer acceptance budget.  It
    # must not become an explicit caller deadline: doing so disables the
    # production Fast p95 deadline adaptation and can make a calibrated
    # fallback unreachable behind the default 2.5s direct budget.
    if api_format == "gemini":
        config = dict(result.get("generationConfig") if isinstance(result.get("generationConfig"), Mapping) else {})
        config["maxOutputTokens"] = max_output_tokens
        result["generationConfig"] = config
    elif api_format == "responses":
        result["max_output_tokens"] = max_output_tokens
    else:
        result["max_tokens"] = max_output_tokens
    return endpoint, result


def _api_surface_stream_live_smoke_payload(
    *,
    model: str,
    api_format: str,
    prompt: str,
    task_type: str,
    max_latency_ms: int,
    max_output_tokens: int,
    max_total_model_calls: int,
) -> tuple[str, dict[str, Any]]:
    """Build one protocol-native public streaming request."""

    endpoint, payload = _api_surface_live_smoke_payload(
        model=model,
        api_format=api_format,
        prompt=prompt,
        task_type=task_type,
        max_latency_ms=max_latency_ms,
        max_output_tokens=max_output_tokens,
        max_total_model_calls=max_total_model_calls,
    )
    if api_format == "gemini":
        return endpoint.replace(":generateContent", ":streamGenerateContent") + "?alt=sse", payload
    payload["stream"] = True
    if api_format == "chat/completions":
        payload["stream_options"] = {"include_usage": True}
    return endpoint, payload


def _api_surface_stream_live_smoke_row(
    *,
    model: str,
    api_format: str,
    status: int,
    response_headers: Mapping[str, str],
    response_body: bytes,
    end_to_end_latency_ms: float,
) -> dict[str, Any]:
    """Validate one public SSE response without retaining generated content."""

    records = _parse_sse_records(response_body)
    evidence = _api_surface_stream_evidence(records, api_format=api_format)
    content_type = str(
        response_headers.get("Content-Type")
        or response_headers.get("content-type")
        or ""
    )
    reason_codes: list[str] = []
    if status != 200:
        reason_codes.append("status_not_200")
    if "text/event-stream" not in content_type.lower():
        reason_codes.append("content_type_not_event_stream")
    if evidence["event_count"] < 1:
        reason_codes.append("stream_events_missing")
    if evidence["invalid_json_event_count"]:
        reason_codes.append("stream_event_json_invalid")
    if evidence["response_model"] != model:
        reason_codes.append("response_model_mismatch")
    if evidence["response_text_present"] is not True:
        reason_codes.append("stream_response_text_missing")
    if evidence["terminal_semantics_ok"] is not True:
        reason_codes.append("stream_terminal_semantics_invalid")
    if evidence["live_provider_call_observed"] is not True:
        reason_codes.append("live_provider_call_not_recorded")
    return {
        "schema": "axio_fusion_api.api_surface_stream_live_smoke_row.v1",
        "public_model": model,
        "api_format": api_format,
        "status_code": int(status),
        "content_type_event_stream": "text/event-stream" in content_type.lower(),
        "stream_event_count": evidence["event_count"],
        "stream_json_event_count": evidence["json_event_count"],
        "stream_invalid_json_event_count": evidence["invalid_json_event_count"],
        "stream_event_type_counts": evidence["event_type_counts"],
        "stream_terminal_semantics_ok": evidence["terminal_semantics_ok"],
        "stream_done_sentinel_observed": evidence["done_sentinel_observed"],
        "response_model": evidence["response_model"],
        "response_model_matches_request": evidence["response_model"] == model,
        "response_text_present": evidence["response_text_present"],
        "live_provider_call_observed": evidence["live_provider_call_observed"],
        "end_to_end_latency_ms": round(
            max(0.0, float(end_to_end_latency_ms)), 3
        ),
        "stream_body_sha256": sha256_text(
            response_body.decode("utf-8", errors="replace")
        ),
        "stream_body_byte_count": len(response_body),
        "error_code": _api_surface_smoke_error_code(response_body),
        "error_trace_summary": _api_surface_smoke_error_trace_summary(response_body),
        "stream_live_smoke_passed": not reason_codes,
        "reason_codes": sorted(set(reason_codes)),
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _parse_sse_records(body: bytes) -> list[dict[str, Any]]:
    """Parse the small bounded SSE response generated by the local gateway."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return []
    records: list[dict[str, Any]] = []
    event_name = ""
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = ""
            return
        data_text = "\n".join(data_lines)
        if data_text == "[DONE]":
            records.append(
                {
                    "event": event_name,
                    "done_sentinel": True,
                    "json": None,
                    "json_valid": True,
                }
            )
        else:
            try:
                payload = json.loads(data_text)
            except json.JSONDecodeError:
                payload = None
            records.append(
                {
                    "event": event_name,
                    "done_sentinel": False,
                    "json": payload if isinstance(payload, Mapping) else None,
                    "json_valid": isinstance(payload, Mapping),
                }
            )
        event_name = ""
        data_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            flush()
        elif line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
    flush()
    return records


def _api_surface_stream_evidence(
    records: Sequence[Mapping[str, Any]],
    *,
    api_format: str,
) -> dict[str, Any]:
    """Project protocol-native stream evidence into fixed, content-free fields."""

    payloads = [
        record.get("json")
        for record in records
        if isinstance(record.get("json"), Mapping)
    ]
    done_sentinel_observed = any(
        record.get("done_sentinel") is True for record in records
    )
    event_type_counts: dict[str, int] = {}
    for record in records:
        label = _api_surface_stream_event_label(record, api_format=api_format)
        if label:
            event_type_counts[label] = event_type_counts.get(label, 0) + 1
    response_model = _api_surface_stream_response_model(
        payloads,
        api_format=api_format,
    )
    response_text_present = _api_surface_stream_text_present(
        payloads,
        api_format=api_format,
    )
    terminal_semantics_ok = _api_surface_stream_terminal_semantics_ok(
        records,
        payloads,
        api_format=api_format,
        done_sentinel_observed=done_sentinel_observed,
    )
    metadata_rows = _api_surface_stream_metadata_rows(payloads)
    return {
        "event_count": len(records),
        "json_event_count": len(payloads),
        "invalid_json_event_count": sum(
            1
            for record in records
            if record.get("done_sentinel") is not True
            and record.get("json_valid") is not True
        ),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "done_sentinel_observed": done_sentinel_observed,
        "response_model": response_model,
        "response_text_present": response_text_present,
        "terminal_semantics_ok": terminal_semantics_ok,
        "live_provider_call_observed": any(
            metadata.get("provider_calls_recorded") is True
            for metadata in metadata_rows
        ),
    }


def _api_surface_stream_event_label(
    record: Mapping[str, Any],
    *,
    api_format: str,
) -> str:
    if record.get("done_sentinel") is True:
        return "done"
    payload = record.get("json")
    payload = payload if isinstance(payload, Mapping) else {}
    named = str(record.get("event") or "").strip()
    payload_type = str(payload.get("type") or "").strip()
    if api_format == "chat/completions":
        return "chat.completion.chunk" if payload.get("object") == "chat.completion.chunk" else ""
    if api_format == "responses":
        return payload_type if payload_type.startswith("response.") else named
    if api_format == "anthropic":
        allowed = {
            "message_start",
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        }
        return payload_type if payload_type in allowed else named
    if api_format == "gemini":
        return "gemini.generate_content" if payload else ""
    return ""


def _api_surface_stream_response_model(
    payloads: Sequence[Mapping[str, Any]],
    *,
    api_format: str,
) -> str:
    for payload in payloads:
        if api_format == "responses":
            response = payload.get("response")
            value = response.get("model") if isinstance(response, Mapping) else ""
        elif api_format == "anthropic":
            message = payload.get("message")
            value = message.get("model") if isinstance(message, Mapping) else ""
        elif api_format == "gemini":
            value = payload.get("modelVersion")
        else:
            value = payload.get("model")
        if str(value or ""):
            return str(value)
    return ""


def _api_surface_stream_text_present(
    payloads: Sequence[Mapping[str, Any]],
    *,
    api_format: str,
) -> bool:
    for payload in payloads:
        if api_format == "responses":
            if str(payload.get("delta") or ""):
                return True
        elif api_format == "anthropic":
            delta = payload.get("delta")
            if isinstance(delta, Mapping) and str(delta.get("text") or ""):
                return True
        elif api_format == "gemini":
            candidates = payload.get("candidates")
            for candidate in candidates if isinstance(candidates, list) else []:
                content = candidate.get("content") if isinstance(candidate, Mapping) else {}
                parts = content.get("parts") if isinstance(content, Mapping) else []
                if isinstance(parts, list) and any(
                    isinstance(part, Mapping) and str(part.get("text") or "")
                    for part in parts
                ):
                    return True
        else:
            choices = payload.get("choices")
            for choice in choices if isinstance(choices, list) else []:
                delta = choice.get("delta") if isinstance(choice, Mapping) else {}
                if isinstance(delta, Mapping) and str(delta.get("content") or ""):
                    return True
    return False


def _api_surface_stream_terminal_semantics_ok(
    records: Sequence[Mapping[str, Any]],
    payloads: Sequence[Mapping[str, Any]],
    *,
    api_format: str,
    done_sentinel_observed: bool,
) -> bool:
    if api_format == "chat/completions":
        finish_seen = any(
            isinstance(choice, Mapping)
            and str(choice.get("finish_reason") or "") in {"stop", "tool_calls"}
            for payload in payloads
            for choice in (
                payload.get("choices") if isinstance(payload.get("choices"), list) else []
            )
        )
        return done_sentinel_observed and finish_seen
    if api_format == "responses":
        return any(
            str(record.get("event") or "") == "response.completed"
            and isinstance(record.get("json"), Mapping)
            and record["json"].get("type") == "response.completed"
            for record in records
        )
    if api_format == "anthropic":
        return any(
            str(record.get("event") or "") == "message_stop"
            and isinstance(record.get("json"), Mapping)
            and record["json"].get("type") == "message_stop"
            for record in records
        )
    if api_format == "gemini":
        return any(
            isinstance(candidate, Mapping)
            and str(candidate.get("finishReason") or "") == "STOP"
            and isinstance(payload.get("usageMetadata"), Mapping)
            for payload in payloads
            for candidate in (
                payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
            )
        )
    return False


def _api_surface_stream_metadata_rows(
    payloads: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for payload in payloads:
        for value in (
            payload.get("metadata"),
            payload.get("response", {}).get("metadata")
            if isinstance(payload.get("response"), Mapping)
            else None,
            payload.get("message", {}).get("metadata")
            if isinstance(payload.get("message"), Mapping)
            else None,
        ):
            if isinstance(value, Mapping):
                rows.append(value)
    return rows


def _api_surface_stream_live_smoke_model_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    models: Sequence[str],
) -> list[dict[str, Any]]:
    summaries = []
    for model in models:
        model_rows = [
            row for row in rows if str(row.get("public_model") or "") == model
        ]
        if not model_rows:
            continue
        passed_count = sum(
            1 for row in model_rows if row.get("stream_live_smoke_passed") is True
        )
        provider_count = sum(
            1 for row in model_rows if row.get("live_provider_call_observed") is True
        )
        summaries.append(
            {
                "public_model": model,
                "stream_surface_count": len(model_rows),
                "passed_stream_surface_count": passed_count,
                "live_provider_call_observed_surface_count": provider_count,
                "all_required_stream_surfaces_live": len(model_rows)
                == len(API_SURFACE_PROTOCOL_FORMATS)
                and passed_count == len(API_SURFACE_PROTOCOL_FORMATS),
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }
        )
    return summaries


def _api_surface_live_smoke_row(
    *,
    model: str,
    api_format: str,
    status: int,
    response_headers: Mapping[str, str],
    response_body: bytes,
    end_to_end_latency_ms: float,
) -> dict[str, Any]:
    row = _api_surface_self_test_row(
        model=model,
        api_format=api_format,
        status=status,
        response_headers=response_headers,
        response_body=response_body,
    )
    reason_codes = list(row.get("reason_codes") or [])
    live_provider_call_observed = int(row.get("provider_calls_recorded") or 0) > 0
    if not row.get("response_text_present"):
        reason_codes.append("response_text_missing")
    if not live_provider_call_observed:
        reason_codes.append("live_provider_call_not_recorded")
    error_trace_summary = _api_surface_smoke_error_trace_summary(response_body)
    row.update(
        {
            "schema": "axio_fusion_api.api_surface_live_smoke_row.v1",
            "end_to_end_latency_ms": round(max(0.0, float(end_to_end_latency_ms)), 3),
            "live_provider_call_observed": live_provider_call_observed,
            "error_code": _api_surface_smoke_error_code(response_body),
            "error_trace_summary": error_trace_summary,
            "live_smoke_passed": not reason_codes,
            "protocol_passed": not reason_codes,
            "reason_codes": sorted(set(str(code) for code in reason_codes if str(code))),
            "raw_response_text_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        }
    )
    return row


def _api_surface_smoke_error_code(response_body: bytes) -> str:
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    error = payload.get("error") if isinstance(payload, Mapping) else {}
    value = str(error.get("code") or "") if isinstance(error, Mapping) else ""
    if not value or len(value) > 120:
        return ""
    return value if all(character.isalnum() or character in {"_", "-", ":"} for character in value) else ""


def _api_surface_smoke_error_trace_summary(response_body: bytes) -> dict[str, Any]:
    """Project an existing public error receipt into a bounded smoke diagnostic.

    The public gateway already returns a redacted trace summary for failed
    provider execution.  The live-smoke artifact needs enough of that summary
    to distinguish an upstream exhaustion from a local budget/deadline gate,
    but it must not copy an arbitrary error object or provider text.
    """

    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    metadata = payload.get("metadata") if isinstance(payload, Mapping) else {}
    trace = metadata.get("trace_summary") if isinstance(metadata, Mapping) else {}
    if not isinstance(trace, Mapping):
        return {
            "present": False,
            "raw_trace_persisted": False,
        }
    selected_hashes = trace.get("selected_profile_hashes")
    safe_selected_hashes = [
        str(item)
        for item in selected_hashes
        if isinstance(item, str)
        and len(item) == 64
        and all(character in "0123456789abcdef" for character in item.lower())
    ][:24] if isinstance(selected_hashes, list) else []
    return {
        "present": True,
        "schema": str(trace.get("schema") or "")[:120],
        "strategy": str(trace.get("strategy") or "")[:120],
        "selected_profile_hashes": safe_selected_hashes,
        "candidate_count": max(0, _optional_int(trace.get("candidate_count")) or 0),
        "candidate_status_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_status_counts")
        ),
        "candidate_error_type_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_error_type_counts")
        ),
        "candidate_provider_error_code_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_provider_error_code_counts")
        ),
        "candidate_provider_error_class_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_provider_error_class_counts")
        ),
        "candidate_provider_http_status_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_provider_http_status_counts")
        ),
        "candidate_replica_error_code_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_replica_error_code_counts")
        ),
        "candidate_replica_error_class_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_replica_error_class_counts")
        ),
        "candidate_replica_http_status_counts": _api_surface_smoke_safe_count_map(
            trace.get("candidate_replica_http_status_counts")
        ),
        "candidate_provider_error_observed_count": max(
            0,
            _optional_int(trace.get("candidate_provider_error_observed_count")) or 0,
        ),
        "candidate_replica_error_observed_count": max(
            0,
            _optional_int(trace.get("candidate_replica_error_observed_count")) or 0,
        ),
        "selected_profile_hash_count": len(
            [
                item
                for item in selected_hashes
                if isinstance(item, str)
                and len(item) == 64
                and all(character in "0123456789abcdef" for character in item.lower())
            ]
        )
        if isinstance(selected_hashes, list)
        else 0,
        "budget_lock_skipped_call_count": max(
            0,
            _optional_int(trace.get("budget_lock_skipped_call_count")) or 0,
        ),
        "deadline_budget_skipped_call_count": max(
            0,
            _optional_int(trace.get("deadline_budget_skipped_call_count")) or 0,
        ),
        "runtime_fusion_execution_mode": str(
            trace.get("runtime_fusion_execution_mode") or ""
        )[:120],
        "runtime_fusion_degraded": trace.get("runtime_fusion_degraded") is True,
        "runtime_fusion_degradation_reason": str(
            trace.get("runtime_fusion_degradation_reason") or ""
        )[:120],
        "raw_trace_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_prompt_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _api_surface_smoke_safe_count_map(value: Any) -> dict[str, int]:
    """Keep only bounded closed-form diagnostic labels and non-negative counts."""

    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for raw_key, raw_count in sorted(value.items(), key=lambda item: str(item[0]))[:24]:
        key = str(raw_key or "").strip()[:120]
        if not key or not all(character.isalnum() or character in {"_", "-", ":", "."} for character in key):
            continue
        count = _optional_int(raw_count)
        if count is None or count < 0:
            continue
        result[key] = count
    return result


def _api_surface_live_smoke_model_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries = _api_surface_self_test_model_summary(rows)
    for summary in summaries:
        model = str(summary.get("public_model") or "")
        model_rows = [row for row in rows if str(row.get("public_model") or "") == model]
        passed_count = sum(1 for row in model_rows if row.get("live_smoke_passed") is True)
        observed_count = sum(1 for row in model_rows if row.get("live_provider_call_observed") is True)
        summary.update(
            {
                "live_smoke_passed": bool(model_rows) and passed_count == len(API_SURFACE_PROTOCOL_FORMATS),
                "live_provider_call_observed_surface_count": observed_count,
                "live_provider_call_observed_across_surfaces": observed_count == len(API_SURFACE_PROTOCOL_FORMATS),
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            }
        )
    return summaries


def _profile_set_sha256(profiles: Sequence[Any]) -> str:
    hashes = sorted({sha256_text(str(getattr(profile, "profile_id", "") or "")) for profile in profiles if getattr(profile, "profile_id", "")})
    return sha256_text(stable_json(hashes))


def _api_surface_self_test_headers() -> dict[str, str]:
    keys = sorted(_server_keys())
    if keys:
        return {"x-api-key": keys[0]}
    return {}


def _api_surface_self_test_payload(
    *,
    model: str,
    api_format: str,
    prompt: str,
    task_type: str,
) -> tuple[str, dict[str, Any]]:
    if api_format == "responses":
        return (
            "/v1/responses",
            {
                "model": model,
                "input": prompt,
                "instructions": "Answer briefly and avoid hidden reasoning.",
                "task_type": task_type,
                "temperature": 0,
                "max_output_tokens": 96,
            },
        )
    if api_format == "anthropic":
        return (
            "/v1/messages",
            {
                "model": model,
                "system": "Answer briefly and avoid hidden reasoning.",
                "messages": [{"role": "user", "content": prompt}],
                "task_type": task_type,
                "temperature": 0,
                "max_tokens": 96,
            },
        )
    if api_format == "gemini":
        return (
            f"/v1beta/models/{model}:generateContent",
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "task_type": task_type,
                "generationConfig": {"temperature": 0, "maxOutputTokens": 96},
            },
        )
    return (
        "/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "task_type": task_type,
            "temperature": 0,
            "max_tokens": 96,
        },
    )


def _api_surface_self_test_row(
    *,
    model: str,
    api_format: str,
    status: int,
    response_headers: Mapping[str, str],
    response_body: bytes,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    valid_json = False
    try:
        decoded = json.loads(response_body.decode("utf-8"))
        if isinstance(decoded, dict):
            payload = decoded
            valid_json = True
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    route_summary = metadata.get("route_summary") if isinstance(metadata.get("route_summary"), Mapping) else {}
    answer_text = _api_surface_response_text(payload, api_format)
    response_model = _api_surface_response_model(payload, api_format)
    usage = _api_surface_usage(payload, api_format)
    response_shape_ok = _api_surface_response_shape_ok(payload, api_format)
    content_type = str(response_headers.get("Content-Type") or response_headers.get("content-type") or "")
    reason_codes = []
    if status != 200:
        reason_codes.append("status_not_200")
    if not valid_json:
        reason_codes.append("response_not_valid_json_object")
    if "json" not in content_type.lower():
        reason_codes.append("content_type_not_json")
    if response_shape_ok is not True:
        reason_codes.append("response_shape_invalid")
    if response_model != model:
        reason_codes.append("response_model_mismatch")
    if not route_summary:
        reason_codes.append("missing_route_summary")
    route_digest_input = _api_surface_route_digest_input(route_summary)
    return {
        "schema": "axio_fusion_api.api_surface_protocol_self_test_row.v1",
        "public_model": model,
        "api_format": api_format,
        "status_code": int(status),
        "content_type_json": "json" in content_type.lower(),
        "valid_json_object": valid_json,
        "response_shape_ok": response_shape_ok,
        "response_model": response_model,
        "response_model_matches_request": response_model == model,
        "response_text_present": bool(answer_text),
        "answer_sha256": sha256_text(answer_text),
        "answer_char_count": len(answer_text),
        "usage": usage,
        "metadata_schema": str(metadata.get("schema") or ""),
        "route_summary_present": bool(route_summary),
        "route_summary_digest_sha256": sha256_text(stable_json(route_digest_input)) if route_summary else "",
        "route_strategy": str(route_summary.get("strategy") or ""),
        "selected_model_count": _optional_int(route_summary.get("selected_model_count")) or 0,
        "fusion_activated": route_summary.get("fusion_activated") is True,
        "provider_calls_recorded": _optional_int(metadata.get("provider_calls_recorded")) or 0,
        "protocol_passed": not reason_codes,
        "reason_codes": sorted(set(reason_codes)),
        "raw_prompt_persisted": False,
        "raw_response_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }


def _api_surface_route_digest_input(route_summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.api_surface_route_digest_input.v1",
        "public_model": str(route_summary.get("public_model") or ""),
        "strategy": str(route_summary.get("strategy") or ""),
        "selected_model_count": _optional_int(route_summary.get("selected_model_count")) or 0,
        "selected_profile_hashes": [
            str(item)
            for item in route_summary.get("selected_profile_hashes", [])
            if str(item)
        ] if isinstance(route_summary.get("selected_profile_hashes"), list) else [],
        "role_count": _optional_int(route_summary.get("role_count")) or 0,
        "stage_profile_reuse": route_summary.get("stage_profile_reuse")
        if isinstance(route_summary.get("stage_profile_reuse"), Mapping)
        else {},
        "fusion_activated": route_summary.get("fusion_activated") is True,
        "task_dag_node_count": _optional_int(route_summary.get("task_dag_node_count")),
        "task_dag_checkpoint_count": _optional_int(route_summary.get("task_dag_checkpoint_count")),
        "max_total_model_calls": _optional_int(route_summary.get("max_total_model_calls")),
        "max_cost_usd": _optional_float(route_summary.get("max_cost_usd")),
        "max_latency_ms": _optional_int(route_summary.get("max_latency_ms")),
        "quality_target": _optional_float(route_summary.get("quality_target")),
        "provider_fallback_enabled": route_summary.get("provider_fallback_enabled") is True,
        "candidate_deduplication_enabled": route_summary.get("candidate_deduplication_enabled") is True,
    }


def _api_surface_self_test_model_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(str(row.get("public_model") or ""), []).append(row)
    summaries = []
    for model, model_rows in sorted(by_model.items()):
        route_digests = sorted({
            str(row.get("route_summary_digest_sha256") or "")
            for row in model_rows
            if str(row.get("route_summary_digest_sha256") or "")
        })
        answer_digests = sorted({
            str(row.get("answer_sha256") or "")
            for row in model_rows
            if str(row.get("answer_sha256") or "")
        })
        passed = [row for row in model_rows if row.get("protocol_passed") is True]
        summaries.append(
            {
                "public_model": model,
                "surface_count": len(model_rows),
                "passed_surface_count": len(passed),
                "failed_surface_count": len(model_rows) - len(passed),
                "route_summary_digest_count": len(route_digests),
                "route_summary_digest_set_sha256": sha256_text(stable_json(route_digests)),
                "route_consistent_across_surfaces": len(route_digests) == 1 and len(model_rows) == len(API_SURFACE_PROTOCOL_FORMATS),
                "answer_digest_count": len(answer_digests),
                "answer_digest_set_sha256": sha256_text(stable_json(answer_digests)),
                "api_formats": sorted(str(row.get("api_format") or "") for row in model_rows),
                "raw_response_text_persisted": False,
                "raw_provider_model_ids_persisted": False,
                "secrets_persisted": False,
            }
        )
    return summaries


def _api_surface_response_model(payload: Mapping[str, Any], api_format: str) -> str:
    if api_format == "gemini":
        return str(payload.get("modelVersion") or "")
    return str(payload.get("model") or "")


def _api_surface_response_text(payload: Mapping[str, Any], api_format: str) -> str:
    if api_format == "responses":
        return str(payload.get("output_text") or "")
    if api_format == "anthropic":
        content = payload.get("content") if isinstance(payload.get("content"), list) else []
        return "\n".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, Mapping) and str(item.get("type") or "") == "text"
        )
    if api_format == "gemini":
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        parts: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            content = candidate.get("content") if isinstance(candidate.get("content"), Mapping) else {}
            for part in content.get("parts", []) if isinstance(content.get("parts"), list) else []:
                if isinstance(part, Mapping) and str(part.get("text") or ""):
                    parts.append(str(part.get("text")))
        return "\n".join(parts)
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    if not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message") if isinstance(choices[0].get("message"), Mapping) else {}
    return str(message.get("content") or "")


def _api_surface_usage(payload: Mapping[str, Any], api_format: str) -> dict[str, Any]:
    if api_format == "gemini":
        usage = payload.get("usageMetadata") if isinstance(payload.get("usageMetadata"), Mapping) else {}
        prompt_tokens = _optional_int(usage.get("promptTokenCount")) or 0
        completion_tokens = _optional_int(usage.get("candidatesTokenCount")) or 0
        total_tokens = _optional_int(usage.get("totalTokenCount")) or 0
    elif api_format == "anthropic":
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        prompt_tokens = _optional_int(usage.get("input_tokens")) or 0
        completion_tokens = _optional_int(usage.get("output_tokens")) or 0
        total_tokens = prompt_tokens + completion_tokens
    elif api_format == "responses":
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        prompt_tokens = _optional_int(usage.get("input_tokens")) or 0
        completion_tokens = _optional_int(usage.get("output_tokens")) or 0
        total_tokens = _optional_int(usage.get("total_tokens")) or prompt_tokens + completion_tokens
    else:
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        prompt_tokens = _optional_int(usage.get("prompt_tokens")) or 0
        completion_tokens = _optional_int(usage.get("completion_tokens")) or 0
        total_tokens = _optional_int(usage.get("total_tokens")) or prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _api_surface_response_shape_ok(payload: Mapping[str, Any], api_format: str) -> bool:
    if api_format == "responses":
        output = payload.get("output") if isinstance(payload.get("output"), list) else []
        return (
            str(payload.get("object") or "") == "response"
            and isinstance(payload.get("output_text"), str)
            and bool(output)
        )
    if api_format == "anthropic":
        content = payload.get("content") if isinstance(payload.get("content"), list) else []
        return str(payload.get("type") or "") == "message" and bool(content)
    if api_format == "gemini":
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        return bool(candidates and isinstance(candidates[0], Mapping))
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    return str(payload.get("object") or "") == "chat.completion" and bool(choices)


def _cors_preflight_response(headers: Mapping[str, str]) -> tuple[int, dict[str, str], bytes]:
    origin = str(headers.get("origin") or "").strip()
    cors_headers = _cors_headers(headers, preflight=True)
    if origin and _cors_allowlist() and not cors_headers:
        return _json_response(
            403,
            {
                "error": {"message": "CORS origin not allowed", "code": "cors_origin_not_allowed"},
                "metadata": {
                    "origin_sha256": sha256_text(origin),
                    "raw_origin_persisted": False,
                    "raw_api_keys_persisted": False,
                    "secrets_persisted": False,
                },
            },
            extra_headers={"Vary": "Origin, Access-Control-Request-Headers"},
        )
    return 204, {"Content-Length": "0", **cors_headers}, b""


def _apply_cors_headers(
    response: tuple[int, dict[str, str], bytes],
    request_headers: Mapping[str, str],
) -> tuple[int, dict[str, str], bytes]:
    cors_headers = _cors_headers(request_headers, preflight=False)
    if not cors_headers:
        return response
    status, response_headers, body = response
    merged = {**response_headers}
    vary = merged.get("Vary")
    merged.update({key: value for key, value in cors_headers.items() if key.lower() != "vary"})
    merged["Vary"] = _merge_vary(vary, "Origin")
    return status, merged, body


def _cors_headers(headers: Mapping[str, str], *, preflight: bool) -> dict[str, str]:
    origin = str(headers.get("origin") or "").strip()
    allowed_origin = _allowed_cors_origin(origin)
    if not allowed_origin:
        return {}
    result = {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Expose-Headers": "x-request-id",
        "Vary": "Origin",
    }
    if _cors_allow_credentials() and allowed_origin != "*":
        result["Access-Control-Allow-Credentials"] = "true"
    if preflight:
        result.update(
            {
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": _allowed_cors_request_headers(
                    str(headers.get("access-control-request-headers") or "")
                ),
                "Access-Control-Max-Age": str(_cors_max_age_seconds()),
                "Vary": "Origin, Access-Control-Request-Headers",
            }
        )
    return result


def _allowed_cors_origin(origin: str) -> str:
    if not origin:
        return ""
    allowlist = _cors_allowlist()
    if not allowlist:
        return ""
    if "*" in allowlist:
        return "*"
    return origin if origin in allowlist else ""


def _cors_allowlist() -> set[str]:
    raw = os.getenv("AXIO_FUSION_CORS_ALLOW_ORIGINS", "")
    return {item.strip().rstrip("/") for item in raw.replace(";", ",").replace("\n", ",").split(",") if item.strip()}


def _allowed_cors_request_headers(requested: str) -> str:
    defaults = {
        "authorization",
        "content-type",
        "x-api-key",
        "x-axio-operator-key",
        "x-axio-tenant",
    }
    requested_headers = {
        item.strip().lower()
        for item in requested.split(",")
        if item.strip() and _safe_http_header_name(item.strip())
    }
    return ", ".join(sorted(defaults | requested_headers))


def _safe_http_header_name(value: str) -> bool:
    if not value:
        return False
    return all(ch.isalnum() or ch in "!#$%&'*+-.^_`|~" for ch in value)


def _cors_allow_credentials() -> bool:
    return os.getenv("AXIO_FUSION_CORS_ALLOW_CREDENTIALS", "").strip().lower() in {"1", "true", "yes"}


def _cors_max_age_seconds() -> int:
    raw = os.getenv("AXIO_FUSION_CORS_MAX_AGE_SECONDS", "600").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 600
    return max(0, min(86400, value))


def _merge_vary(existing: str | None, *items: str) -> str:
    values = [item.strip() for item in str(existing or "").split(",") if item.strip()]
    seen = {item.lower() for item in values}
    for item in items:
        if item.lower() not in seen:
            values.append(item)
            seen.add(item.lower())
    return ", ".join(values)


def _models(engine: FusionEngine) -> dict[str, Any]:
    readiness = registry_readiness(engine.profiles)
    profile_hashes = sorted({sha256_text(profile.profile_id) for profile in engine.profiles})
    provider_hashes = sorted({sha256_text(profile.provider) for profile in engine.profiles})
    provider_baseline_hashes = sorted(
        {
            sha256_text(profile.profile_id)
            for profile in engine.profiles
            if (
                profile.enabled
                and profile.health != "unavailable"
                and profile_latency_eligibility(profile).get("eligible") is not False
            )
        }
    )
    registry_ready = readiness.get("ready") is True and bool(provider_baseline_hashes)
    live_credentials = _live_provider_credential_summary(engine.profiles)
    live_usable = registry_ready and live_credentials["credentialed_provider_profile_count"] > 0
    common_metadata = {
        "registry_ready": registry_ready,
        "registry_status": "ready" if registry_ready else "blocked",
        "live_usable": live_usable,
        "live_credential_ready": live_credentials["credential_ready"],
        "credentialed_provider_profile_hash_count": live_credentials["credentialed_provider_profile_count"],
        "credentialed_provider_profile_set_sha256": live_credentials["credentialed_provider_profile_set_sha256"],
        "provider_profile_hash_count": len(provider_baseline_hashes),
        "provider_profile_set_sha256": sha256_text(stable_json(provider_baseline_hashes)),
        "raw_provider_model_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "Axio Fusion",
                "permission": [],
                "root": model,
                "parent": None,
                "usable": registry_ready,
                "live_usable": live_usable,
                "status": "ready" if registry_ready else "blocked",
                "live_status": "ready" if live_usable else "credentials_required",
                "metadata": {
                    **common_metadata,
                    "public_model": model,
                    "fusion_policy": _public_model_policy(model),
                },
            }
            for model in PUBLIC_MODELS
        ],
        "registry_summary": {
            "schema": "axio_fusion_api.public_models_registry_summary.v1",
            "ready": registry_ready,
            "status": "ready" if registry_ready else "blocked",
            "readiness_blockers": list(readiness.get("blockers") or []),
            "readiness_warnings": list(readiness.get("warnings") or []),
            "provider_hash_count": len(provider_hashes),
            "profile_hash_count": len(profile_hashes),
            "provider_profile_hash_count": len(provider_baseline_hashes),
            "profile_set_sha256": sha256_text(stable_json(profile_hashes)),
            "provider_profile_set_sha256": sha256_text(stable_json(provider_baseline_hashes)),
            "all_listed_models_usable": registry_ready,
            "all_listed_models_live_usable": live_usable,
            "live_credential_summary": live_credentials,
            "raw_provider_model_ids_persisted": False,
            "raw_provider_names_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_provider_model_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _live_provider_credential_summary(profiles: Sequence[Any]) -> dict[str, Any]:
    eligible_hashes = sorted(
        {
            sha256_text(profile.profile_id)
            for profile in profiles
            if (
                profile.enabled
                and profile.health != "unavailable"
                and profile_latency_eligibility(profile).get("eligible") is not False
            )
        }
    )
    credentialed_hashes = sorted(
        {
            sha256_text(profile.profile_id)
            for profile in profiles
            if profile.enabled
            and profile.health != "unavailable"
            and profile_latency_eligibility(profile).get("eligible") is not False
            and _profile_has_live_credentials(profile)
        }
    )
    return {
        "schema": "axio_fusion_api.live_provider_credential_summary.v1",
        "credential_ready": bool(credentialed_hashes),
        "eligible_provider_profile_count": len(eligible_hashes),
        "credentialed_provider_profile_count": len(credentialed_hashes),
        "eligible_provider_profile_set_sha256": sha256_text(stable_json(eligible_hashes)),
        "credentialed_provider_profile_set_sha256": sha256_text(stable_json(credentialed_hashes)),
        "raw_provider_model_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_key_env_names_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }


def _profile_has_live_credentials(profile: Any) -> bool:
    return profile_credential_readiness(profile).get("credential_ready") is True


def _public_model_policy(model: str) -> dict[str, Any]:
    if model == "axio-fast":
        return {
            "tier": "fast",
            "default_strategy": "fast_direct_cascade",
            "latency_priority": "highest",
        }
    if model == "axio-pro":
        return {
            "tier": "pro",
            "default_strategy": "pro_panel_judge_escalation",
            "quality_priority": "highest",
        }
    return {
        "tier": "terra",
        "default_strategy": "terra_cost_guarded_fusion",
        "cost_quality_balance": "balanced",
    }


def _health(engine: FusionEngine) -> dict[str, Any]:
    readiness = _public_registry_readiness(engine.profiles)
    return {
        "schema": "axio_fusion_api.health.v1",
        "status": readiness["status"],
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "public_models": list(PUBLIC_MODELS),
        "supported_api_formats": ["chat/completions", "responses", "anthropic", "gemini"],
        "registry_readiness": readiness,
        "network": provider_proxy_runtime_summary(),
        "runtime": runtime_state().snapshot(),
        "auth_required": bool(_server_keys()),
        "operator_auth_configured": bool(_operator_keys()),
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }


def _public_registry_readiness(profiles: Sequence[Any]) -> dict[str, Any]:
    """Project registry health into a public, identifier-safe API receipt."""

    internal = registry_readiness(profiles)
    api_format_counts: dict[str, int] = {}
    provider_format_hash_counts: dict[str, int] = {}
    profile_hashes = set()
    provider_hashes = set()
    for profile in profiles:
        api_format = normalize_api_format(str(getattr(profile, "api_format", "chat/completions")))
        provider_hash = sha256_text(str(getattr(profile, "provider", "")))
        profile_hashes.add(sha256_text(str(getattr(profile, "profile_id", ""))))
        provider_hashes.add(provider_hash)
        api_format_counts[api_format] = api_format_counts.get(api_format, 0) + 1
        provider_format_key = f"{provider_hash}::{api_format}"
        provider_format_hash_counts[provider_format_key] = provider_format_hash_counts.get(provider_format_key, 0) + 1
    return {
        "schema": "axio_fusion_api.public_registry_readiness.v1",
        "ready": internal.get("ready") is True,
        "status": str(internal.get("status") or "blocked"),
        "blockers": [str(item)[:120] for item in internal.get("blockers", []) if str(item)],
        "warnings": [str(item)[:120] for item in internal.get("warnings", []) if str(item)],
        "model_count": len(profile_hashes),
        "provider_count": len(provider_hashes),
        "provider_hash_count": len(provider_hashes),
        "profile_set_sha256": sha256_text(stable_json(sorted(profile_hashes))),
        "api_format_counts": dict(sorted(api_format_counts.items())),
        "provider_format_hash_counts": dict(sorted(provider_format_hash_counts.items())),
        "judge_candidate_count": _optional_int(internal.get("judge_candidate_count")) or 0,
        "structured_candidate_count": _optional_int(internal.get("structured_candidate_count")) or 0,
        "fast_candidate_count": _optional_int(internal.get("fast_candidate_count")) or 0,
        "tool_candidate_count": _optional_int(internal.get("tool_candidate_count")) or 0,
        "pricing_known_count": _optional_int(internal.get("pricing_known_count")) or 0,
        "context_known_count": _optional_int(internal.get("context_known_count")) or 0,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_api_key_env_names_persisted": False,
        "raw_api_keys_persisted": False,
        "secrets_persisted": False,
    }


def _endpoint_api_format(route: str) -> str:
    if route in {"/v1/chat/completions", "/chat/completions"}:
        return "chat/completions"
    if route in {"/v1/responses", "/responses"}:
        return "responses"
    if route in {"/v1/messages", "/messages", "/anthropic/v1/messages"}:
        return "anthropic"
    if ":generateContent" in route or ":streamGenerateContent" in route:
        return "gemini"
    return ""


def _handle_image_request(
    *,
    operation: str,
    headers: Mapping[str, str],
    body: bytes | str | None,
    profiles: Sequence[Any],
) -> tuple[int, dict[str, str], bytes]:
    """Dispatch the Images API outside the text Fusion protocol adapters.

    Image outputs are opaque binary/base64 artifacts, so they do not pass
    through ``FusionResponse``, text cost accounting, or any of the four text
    renderers.  Only the request parser and the verified image capability
    router are shared with the public gateway boundary.
    """

    try:
        if operation == "generations":
            payload = parse_generation_payload(body)
            response, result, _profile = ImageRouter(profiles).generate(
                payload,
                timeout=image_request_timeout(),
            )
        else:
            payload, files = parse_edit_payload(
                body,
                headers.get("content-type", ""),
            )
            response, result, _profile = ImageRouter(profiles).edit(
                payload,
                files,
                timeout=image_request_timeout(),
            )
        if payload.get("stream") is True:
            return _stream_response(
                200,
                render_image_stream(
                    result,
                    public_model=str(response.get("model") or "axio-terra"),
                ),
            )
        return _json_response(200, response)
    except ImageRequestError as exc:
        return _json_response(
            exc.status,
            {
                "error": {
                    "message": str(exc),
                    "code": exc.code,
                },
                "metadata": {
                    "image_router": True,
                    "text_fusion_invoked": False,
                    "raw_prompt_persisted": False,
                    "raw_provider_response_persisted": False,
                    "raw_provider_model_ids_persisted": False,
                    "secrets_persisted": False,
                },
            },
        )
    except Exception:  # noqa: BLE001 - public HTTP boundary must not leak provider details
        return _json_response(
            502,
            {
                "error": {
                    "message": "Image provider request failed.",
                    "code": "image_provider_unavailable",
                },
                "metadata": {
                    "image_router": True,
                    "text_fusion_invoked": False,
                    "internal_details_redacted": True,
                    "raw_provider_response_persisted": False,
                    "raw_provider_model_ids_persisted": False,
                    "secrets_persisted": False,
                },
            },
        )


def _stream_requested(route: str, payload: Mapping[str, Any], endpoint: str) -> bool:
    if endpoint == "gemini" and ":streamGenerateContent" in route:
        return True
    return bool(payload.get("stream"))


def _stream_usage_requested(payload: Mapping[str, Any], endpoint: str) -> bool:
    """Honor the OpenAI usage trailer without leaking it into other protocols."""

    if endpoint != "chat/completions":
        return False
    options = payload.get("stream_options")
    return isinstance(options, Mapping) and bool(options.get("include_usage"))


def _gemini_route_model(route: str) -> str:
    marker = "/models/"
    if marker not in route:
        return ""
    tail = route.split(marker, 1)[1]
    suffix = ":streamGenerateContent" if tail.endswith(":streamGenerateContent") else ":generateContent"
    return unquote(tail[: -len(suffix)]) if tail.endswith(suffix) else ""


def _decode_json(body: bytes | str | None) -> dict[str, Any]:
    if body in (None, b"", ""):
        return {}
    text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON request body") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON request body must be an object")
    return value


def _tool_policy_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if isinstance(payload.get("tool_policy"), Mapping):
        return payload["tool_policy"]
    route_plan = payload.get("route_plan") if isinstance(payload.get("route_plan"), Mapping) else {}
    if isinstance(route_plan.get("tool_policy"), Mapping):
        return route_plan["tool_policy"]
    return None


def _json_response(
    status: int,
    payload: Mapping[str, Any],
    *,
    extra_headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    response_headers = {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body))}
    if extra_headers:
        response_headers.update({str(key): str(value) for key, value in extra_headers.items()})
    return status, response_headers, body


def _stream_response(status: int, body: bytes) -> tuple[int, dict[str, str], bytes]:
    return (
        status,
        {
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Length": str(len(body)),
        },
        body,
    )


def _render_image_stream_error(code: str) -> bytes:
    payload = {
        "error": {
            "message": "Image provider request failed.",
            "code": str(code or "image_provider_unavailable")[:80],
        }
    }
    return (
        b"event: error\n"
        + f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
        + b"event: done\ndata: [DONE]\n\n"
    )


def _authorized(headers: Mapping[str, str]) -> bool:
    keys = _server_keys()
    if not keys:
        return True
    return bool(_presented_auth_values(headers) & keys)


def _server_keys() -> set[str]:
    raw = os.getenv("AXIO_FUSION_API_KEYS", "")
    return {item.strip() for item in raw.replace(";", ",").replace("\n", ",").split(",") if item.strip()}


def _operator_authorized(
    headers: Mapping[str, str],
    *,
    require_explicit_operator_key: bool = False,
) -> bool:
    keys = _operator_keys()
    if not keys:
        if require_explicit_operator_key:
            return False
        return _authorized(headers)
    return bool(_presented_auth_values(headers, include_operator_key=True) & keys)


def _operator_keys() -> set[str]:
    raw = os.getenv("AXIO_FUSION_OPERATOR_API_KEYS", "")
    return {item.strip() for item in raw.replace(";", ",").replace("\n", ",").split(",") if item.strip()}


def _presented_auth_values(headers: Mapping[str, str], *, include_operator_key: bool = False) -> set[str]:
    values = set()
    bearer = str(headers.get("authorization") or "")
    if bearer.lower().startswith("bearer "):
        values.add(bearer.split(" ", 1)[1].strip())
    values.add(str(headers.get("x-api-key") or "").strip())
    # ``x-goog-api-key`` is the normal Gemini-compatible header.  It is
    # accepted only as an alternative public gateway credential, never copied
    # into a trace or response artifact.
    values.add(str(headers.get("x-goog-api-key") or "").strip())
    if include_operator_key:
        values.add(str(headers.get("x-axio-operator-key") or "").strip())
    return {value for value in values if value}


def _operator_endpoint(route: str) -> bool:
    return route in {
        "/v1/axio/route-plan",
        "/route-plan",
        "/v1/inventory",
        "/inventory",
        "/v1/axio/runtime",
        "/runtime",
        "/v1/axio/feedback",
        "/feedback",
        "/v1/axio/agent-outcome",
        "/agent-outcome",
        "/v1/axio/tools/execute",
        "/tools/execute",
    }


def _operator_endpoint_requires_explicit_key(route: str) -> bool:
    """Fail closed for endpoints that can enumerate private provider inventory."""

    return route in {"/v1/inventory", "/inventory"}


def _operator_forbidden_response() -> tuple[int, dict[str, str], bytes]:
    return _json_response(
        403,
        {
            "error": {"message": "Operator authorization required", "code": "operator_authorization_required"},
            "metadata": {
                "operator_endpoint": True,
                "operator_auth_configured": bool(_operator_keys()),
                "raw_api_keys_persisted": False,
                "secrets_persisted": False,
            },
        },
    )


def _tenant_budget_exhausted_response(budget: Mapping[str, Any]) -> tuple[int, dict[str, str], bytes]:
    return _json_response(
        402,
        {
            "error": {"message": "Tenant budget exhausted", "code": "tenant_budget_exhausted"},
            "metadata": {
                "budget": budget,
                "raw_prompt_persisted": False,
                "secrets_persisted": False,
            },
        },
    )


def _safe_route_plan_response(route_plan: Mapping[str, Any]) -> dict[str, Any]:
    selected = route_plan.get("selected_models") if isinstance(route_plan.get("selected_models"), list) else []
    ranked = route_plan.get("ranked_candidates") if isinstance(route_plan.get("ranked_candidates"), list) else []
    roles = route_plan.get("roles") if isinstance(route_plan.get("roles"), list) else []
    targeted = route_plan.get("targeted_escalation") if isinstance(route_plan.get("targeted_escalation"), Mapping) else {}
    candidate_pool = targeted.get("candidate_pool") if isinstance(targeted.get("candidate_pool"), list) else []
    request = route_plan.get("request") if isinstance(route_plan.get("request"), Mapping) else {}
    public_summary = public_route_summary(route_plan)
    return {
        "schema": "axio_fusion_api.safe_route_plan.v1",
        "internal_route_plan_schema": str(route_plan.get("schema") or "")[:120],
        "public_model": str(route_plan.get("public_model") or "")[:80],
        "strategy": str(route_plan.get("strategy") or "")[:120],
        "request": request,
        "request_analysis": route_plan.get("request_analysis") if isinstance(route_plan.get("request_analysis"), Mapping) else {},
        "budget": route_plan.get("budget") if isinstance(route_plan.get("budget"), Mapping) else {},
        "fusion_admission": route_plan.get("fusion_admission") if isinstance(route_plan.get("fusion_admission"), Mapping) else {},
        "model_selection_policy": route_plan.get("model_selection_policy") if isinstance(route_plan.get("model_selection_policy"), Mapping) else {},
        "quality_diversity_archive": route_plan.get("quality_diversity_archive") if isinstance(route_plan.get("quality_diversity_archive"), Mapping) else {},
        "provider_routing_policy": route_plan.get("provider_routing_policy") if isinstance(route_plan.get("provider_routing_policy"), Mapping) else {},
        "plugin_policy": route_plan.get("plugin_policy") if isinstance(route_plan.get("plugin_policy"), Mapping) else {},
        "tool_policy": route_plan.get("tool_policy") if isinstance(route_plan.get("tool_policy"), Mapping) else {},
        "runtime_guards": route_plan.get("runtime_guards") if isinstance(route_plan.get("runtime_guards"), Mapping) else {},
        "runtime_provider_telemetry": public_summary.get("runtime_provider_telemetry")
        if isinstance(public_summary.get("runtime_provider_telemetry"), Mapping)
        else {},
        "orchestration_scaffold": route_plan.get("orchestration_scaffold") if isinstance(route_plan.get("orchestration_scaffold"), Mapping) else {},
        "task_dag": route_plan.get("task_dag") if isinstance(route_plan.get("task_dag"), Mapping) else {},
        "stage_profile_reuse": public_summary.get("stage_profile_reuse")
        if isinstance(public_summary.get("stage_profile_reuse"), Mapping)
        else {},
        "judge_contract": route_plan.get("judge_contract") if isinstance(route_plan.get("judge_contract"), Mapping) else {},
        "selected_model_count": len(selected),
        "selected_profile_hashes": _hashes_from_rows(selected, "profile_id"),
        "selected_provider_hashes": _hashes_from_rows(selected, "provider"),
        "selected_models": [_safe_route_model_row(row) for row in selected[:24] if isinstance(row, Mapping)],
        "ranked_candidates": [_safe_ranked_candidate_row(row) for row in ranked[:24] if isinstance(row, Mapping)],
        "roles": [_safe_route_role_row(row) for row in roles[:24] if isinstance(row, Mapping)],
        "targeted_escalation": {
            "enabled": bool(targeted.get("enabled")),
            "scope": str(targeted.get("scope") or "")[:160],
            "max_rounds": _optional_int(targeted.get("max_rounds")) or 0,
            "candidate_pool_count": len(candidate_pool),
            "candidate_pool_hashes": _hashes_from_rows(candidate_pool, "profile_id"),
            "candidate_pool_source": str(targeted.get("candidate_pool_source") or "")[:160],
            "raw_candidate_pool_persisted": False,
        },
        "redaction_contract": {
            "raw_provider_names_persisted": False,
            "raw_provider_model_ids_persisted": False,
            "raw_profile_ids_persisted": False,
            "raw_provider_urls_persisted": False,
            "raw_api_keys_persisted": False,
            "raw_prompts_persisted": False,
            "raw_provider_outputs_persisted": False,
            "secrets_persisted": False,
        },
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_profile_ids_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_prompts_persisted": False,
        "secrets_persisted": False,
    }


def _safe_route_model_row(row: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(row.get("profile_id") or "")
    provider = str(row.get("provider") or "")
    model = str(row.get("model") or "")
    capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), Mapping) else {}
    return {
        "profile_id_sha256": sha256_text(profile_id) if profile_id else "",
        "provider_sha256": sha256_text(provider) if provider else "",
        "model_sha256": sha256_text(model) if model else "",
        "runtime_canonical_identity_sha256": str(
            row.get("runtime_canonical_identity_sha256") or ""
        ),
        "api_format": str(row.get("api_format") or "")[:80],
        "health": str(row.get("health") or "")[:80],
        "capability_summary_sha256": sha256_text(stable_json(capabilities)),
        "capability_count": len(capabilities),
        "supports_tools": row.get("supports_tools") is True,
        "tool_capability": str(row.get("tool_capability") or "")[:40],
        "tool_capability_source": str(row.get("tool_capability_source") or "")[:80],
        "tool_probe_status": str(row.get("tool_probe_status") or "not_run")[:80],
        "tool_calling_eligible": row.get("tool_calling_eligible") is True,
        "supports_vision": row.get("supports_vision") is True,
        "pricing_known": row.get("input_cost_per_million") is not None and row.get("output_cost_per_million") is not None,
        "p50_latency_ms": _optional_int(row.get("p50_latency_ms")),
        "p95_latency_ms": _optional_int(row.get("p95_latency_ms")),
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_provider_url_persisted": False,
    }


def _safe_ranked_candidate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(row.get("profile_id") or "")
    return {
        "profile_id_sha256": sha256_text(profile_id) if profile_id else str(row.get("profile_id_sha256") or ""),
        "score": _optional_float(row.get("score")),
        "raw_profile_id_persisted": False,
    }


def _safe_route_role_row(row: Mapping[str, Any]) -> dict[str, Any]:
    model = row.get("model") if isinstance(row.get("model"), Mapping) else {}
    return {
        "role": str(row.get("role") or "")[:80],
        "assignment": str(row.get("assignment") or "")[:160],
        "model_profile_id_sha256": sha256_text(str(model.get("profile_id") or "")) if model else "",
        "model_provider_sha256": sha256_text(str(model.get("provider") or "")) if model else "",
        "model_runtime_canonical_identity_sha256": str(
            model.get("runtime_canonical_identity_sha256") or ""
        )
        if model
        else "",
        "model_api_format": str(model.get("api_format") or "")[:80] if model else "",
        "raw_model_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_profile_id_persisted": False,
    }


def _safe_error_trace_summary(trace: Mapping[str, Any] | None) -> dict[str, Any]:
    value = trace if isinstance(trace, Mapping) else {}
    route_plan = value.get("route_plan") if isinstance(value.get("route_plan"), Mapping) else value
    selected = route_plan.get("selected_models") if isinstance(route_plan.get("selected_models"), list) else []
    candidates = value.get("candidate_receipts") if isinstance(value.get("candidate_receipts"), list) else []
    budget_lock = value.get("budget_lock") if isinstance(value.get("budget_lock"), Mapping) else {}
    cost_budget = value.get("cost_budget") if isinstance(value.get("cost_budget"), Mapping) else {}
    deadline_budget = value.get("deadline_budget") if isinstance(value.get("deadline_budget"), Mapping) else {}
    fusion_stage_outcome = (
        value.get("runtime_fusion_stage_outcome")
        if isinstance(value.get("runtime_fusion_stage_outcome"), Mapping)
        else {}
    )
    circuit_filter = route_plan.get("runtime_circuit_filter") if isinstance(route_plan.get("runtime_circuit_filter"), Mapping) else {}
    return {
        "schema": "axio_fusion_api.public_error_trace_summary.v1",
        "trace_schema": str(value.get("schema") or route_plan.get("schema") or "")[:120],
        "public_model": str(route_plan.get("public_model") or "")[:80],
        "strategy": str(route_plan.get("strategy") or "")[:120],
        "selected_model_count": len(selected),
        "selected_profile_hashes": _hashes_from_rows(selected, "profile_id"),
        "selected_provider_hashes": _hashes_from_rows(selected, "provider"),
        "candidate_count": len(candidates),
        "candidate_status_counts": _count_string_field(candidates, "status"),
        "candidate_error_type_counts": _count_string_field(candidates, "error_type"),
        **_safe_candidate_provider_failure_summary(candidates),
        "candidate_profile_hashes": _hashes_from_rows(candidates, "profile_id"),
        "budget_lock_skipped_call_count": _optional_int(budget_lock.get("skipped_call_count")) or 0,
        "mandatory_stage_reservation_enabled": budget_lock.get("mandatory_stage_reservation_enabled") is True,
        "mandatory_stage_reservation_released_call_count": _optional_int(
            budget_lock.get("released_mandatory_stage_call_count")
        ) or 0,
        "cost_budget_skipped_call_count": _optional_int(cost_budget.get("skipped_call_count")) or 0,
        "deadline_budget_skipped_call_count": _optional_int(deadline_budget.get("skipped_call_count")) or 0,
        "runtime_fusion_execution_mode": str(
            fusion_stage_outcome.get("execution_mode") or ""
        )[:120],
        "runtime_fusion_degraded": fusion_stage_outcome.get("runtime_degraded") is True,
        "runtime_fusion_degradation_reason": str(
            fusion_stage_outcome.get("degradation_reason") or ""
        )[:120],
        "runtime_circuit_excluded_profile_count": _optional_int(circuit_filter.get("excluded_profile_count")) or 0,
        "raw_prompt_persisted": False,
        "raw_candidate_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_profile_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _hashes_from_rows(rows: Sequence[Any], field: str) -> list[str]:
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        raw = str(row.get(field) or "")
        if raw:
            result.append(sha256_text(raw))
    return list(dict.fromkeys(result))[:24]


def _count_string_field(rows: Sequence[Any], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        raw = str(row.get(field) or "").strip()[:120] or "unknown"
        counts[raw] = counts.get(raw, 0) + 1
    return counts


def _safe_candidate_provider_failure_summary(
    candidates: Sequence[Any],
) -> dict[str, Any]:
    """Aggregate only closed-form upstream diagnostics from safe candidates."""

    terminal_code_counts: dict[str, int] = {}
    terminal_class_counts: dict[str, int] = {}
    terminal_status_counts: dict[str, int] = {}
    replica_code_counts: dict[str, int] = {}
    replica_class_counts: dict[str, int] = {}
    replica_status_counts: dict[str, int] = {}
    terminal_observed_count = 0
    replica_observed_count = 0

    def add(
        code_counts: dict[str, int],
        class_counts: dict[str, int],
        status_counts: dict[str, int],
        *,
        raw_code: Any,
        raw_status: Any,
        count: int = 1,
    ) -> bool:
        safe_code = safe_provider_error_code(raw_code)
        safe_status = safe_provider_http_status(raw_status)
        if not safe_code and safe_status is None:
            return False
        bounded_count = max(1, min(64, int(count)))
        if safe_code:
            code_counts[safe_code] = code_counts.get(safe_code, 0) + bounded_count
        safe_class = safe_provider_error_class(safe_code, safe_status)
        if safe_class:
            class_counts[safe_class] = class_counts.get(safe_class, 0) + bounded_count
        if safe_status is not None:
            key = str(safe_status)
            status_counts[key] = status_counts.get(key, 0) + bounded_count
        return True

    for candidate in candidates[:24]:
        if not isinstance(candidate, Mapping):
            continue
        task_execution = (
            candidate.get("task_execution")
            if isinstance(candidate.get("task_execution"), Mapping)
            else {}
        )
        if add(
            terminal_code_counts,
            terminal_class_counts,
            terminal_status_counts,
            raw_code=task_execution.get("provider_error_code"),
            raw_status=task_execution.get("provider_http_status"),
        ):
            terminal_observed_count += 1
        replica_routing = (
            task_execution.get("replica_routing")
            if isinstance(task_execution.get("replica_routing"), Mapping)
            else {}
        )
        replica_codes = (
            replica_routing.get("stage_error_code_counts")
            if isinstance(replica_routing.get("stage_error_code_counts"), Mapping)
            else {}
        )
        replica_statuses = (
            replica_routing.get("stage_http_status_counts")
            if isinstance(replica_routing.get("stage_http_status_counts"), Mapping)
            else {}
        )
        replica_keys = set(replica_codes) | set(replica_statuses)
        for key in sorted(replica_keys, key=str)[:24]:
            raw_count = replica_codes.get(key, replica_statuses.get(key, 1))
            try:
                count = max(1, int(raw_count))
            except (TypeError, ValueError):
                count = 1
            raw_code = key if key in replica_codes else ""
            raw_status = key if key in replica_statuses else None
            if add(
                replica_code_counts,
                replica_class_counts,
                replica_status_counts,
                raw_code=raw_code,
                raw_status=raw_status,
                count=count,
            ):
                replica_observed_count += count
    return {
        "provider_failure_summary_schema": "axio_fusion_api.safe_provider_failure_summary.v1",
        "candidate_provider_error_observed_count": terminal_observed_count,
        "candidate_provider_error_code_counts": dict(sorted(terminal_code_counts.items())),
        "candidate_provider_error_class_counts": dict(sorted(terminal_class_counts.items())),
        "candidate_provider_http_status_counts": dict(sorted(terminal_status_counts.items())),
        "candidate_replica_error_observed_count": replica_observed_count,
        "candidate_replica_error_code_counts": dict(sorted(replica_code_counts.items())),
        "candidate_replica_error_class_counts": dict(sorted(replica_class_counts.items())),
        "candidate_replica_http_status_counts": dict(sorted(replica_status_counts.items())),
        "provider_error_codes_allowlisted": True,
        "raw_provider_error_messages_persisted": False,
    }


def _actual_cost_from_rendered_response(payload: Mapping[str, Any]) -> float | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    for key in ("fusion_trace", "fusion_trace_summary"):
        trace = metadata.get(key) if isinstance(metadata.get(key), Mapping) else {}
        value = trace.get("actual_cost_usd")
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _optional_int(value: Any) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None
