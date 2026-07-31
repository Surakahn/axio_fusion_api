"""Image capability admission, routing, and OpenAI-compatible image transport.

Images are a sibling capability of text Fusion.  They reuse the provider
credential pool, proxy policy, traffic gate, key failover, and 90-second
ceiling, but never enter the text orchestrator or get merged as text.  The
module intentionally uses a small allow-listed request surface because image
providers commonly accept multipart bodies and large binary responses.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import HTTP
from typing import Any, Callable, Mapping, Sequence

from .latency_policy import PROVIDER_MAX_RESPONSE_LATENCY_MS, PROVIDER_MAX_RESPONSE_SECONDS, profile_latency_eligibility
from .providers import (
    ProviderExecutionError,
    _acquire_provider_traffic_gate,
    _advance_provider_key_rotation,
    _apply_auth_headers,
    _auth_scheme,
    _base_url,
    _begin_provider_request_trace,
    _discard_http_error_body,
    _finish_provider_request_trace,
    _iter_stream_events,
    _max_attempts_per_key,
    _open_provider_url,
    _provider_error_retryable,
    _provider_headers,
    _provider_timeout_budget,
    _record_provider_rate_limit,
    _record_provider_request_receipt,
    _release_provider_traffic_gate,
    _remaining_timeout,
    _retry_after_seconds_from_headers,
    _safe_provider_error_message,
    _sleep_before_retry,
    _stream_protocol_from_content_type,
    _rotated_api_key_attempts,
    _url_with_api_key,
    provider_base_url_readiness,
)
from .schemas import ModelProfile, canonical_public_model, sha256_text


IMAGE_GENERATIONS_PATHS = {"/v1/images/generations", "/images/generations"}
IMAGE_EDITS_PATHS = {"/v1/images/edits", "/images/edits"}
IMAGE_STREAM_EVENT_TYPES = {
    "image_generation.partial_image",
    "image_generation.completed",
    "image_edit.partial_image",
    "image_edit.completed",
}
_IMAGE_FIELD_ALLOWLIST = {
    "quality",
    "size",
    "background",
    "moderation",
    "output_format",
    "output_compression",
    "response_format",
    "input_fidelity",
    "user",
    "n",
    "stream",
    "partial_images",
}


class ImageRequestError(ValueError):
    """A safe public image request error with no upstream body attached."""

    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = str(code or "image_request_invalid")
        self.status = int(status)


@dataclass(frozen=True)
class ImagePart:
    field_name: str
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ImageProviderResult:
    data: tuple[Mapping[str, Any], ...]
    created: int
    stream_events: tuple[Mapping[str, Any], ...] = ()
    stream_protocol: str = ""
    event_prefix: str = "image_generation"


def image_route_kind(route: str) -> str:
    normalized = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    if normalized in IMAGE_GENERATIONS_PATHS:
        return "generations"
    if normalized in IMAGE_EDITS_PATHS:
        return "edits"
    return ""


def image_request_max_bytes() -> int:
    raw = os.getenv("AXIO_FUSION_IMAGE_MAX_REQUEST_BYTES", str(32 * 1024 * 1024)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = 32 * 1024 * 1024
    return max(1_048_576, min(128 * 1024 * 1024, value))


def image_request_timeout() -> float:
    raw = os.getenv("AXIO_FUSION_IMAGE_TIMEOUT_SECONDS", str(PROVIDER_MAX_RESPONSE_SECONDS)).strip()
    try:
        value = float(raw)
    except ValueError:
        value = PROVIDER_MAX_RESPONSE_SECONDS
    return max(1.0, min(PROVIDER_MAX_RESPONSE_SECONDS, value))


def parse_generation_payload(body: bytes | str | None) -> dict[str, Any]:
    if body in (None, b"", ""):
        raise ImageRequestError("Image generation request body is required.", code="image_request_body_missing")
    raw = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImageRequestError("Invalid JSON request body.", code="invalid_json") from exc
    if not isinstance(payload, Mapping):
        raise ImageRequestError("Image generation request body must be an object.", code="invalid_json")
    return _normalize_image_fields(payload, require_prompt=True)


def parse_edit_payload(
    body: bytes | str | None,
    content_type: str,
) -> tuple[dict[str, Any], list[ImagePart]]:
    raw = body.encode("utf-8") if isinstance(body, str) else bytes(body or b"")
    if not raw:
        raise ImageRequestError("Image edit request body is required.", code="image_request_body_missing")
    if len(raw) > image_request_max_bytes():
        raise ImageRequestError("Image edit request is too large.", code="image_request_too_large", status=413)
    header = (
        f"Content-Type: {str(content_type or '')}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8")
    try:
        message = BytesParser(policy=HTTP).parsebytes(header + raw)
    except Exception as exc:  # noqa: BLE001 - parser boundary
        raise ImageRequestError("Invalid multipart image request.", code="invalid_multipart") from exc
    if not message.is_multipart():
        raise ImageRequestError("Image edits require multipart/form-data.", code="multipart_required")
    fields: dict[str, Any] = {}
    files: list[ImagePart] = []
    for part in message.iter_parts():
        name = str(part.get_param("name", header="Content-Disposition") or "").strip()
        if not name:
            continue
        filename = str(part.get_filename() or "").strip()
        value = part.get_payload(decode=True) or b""
        if filename or name in {"image", "image[]", "mask"}:
            if name not in {"image", "image[]", "mask"}:
                continue
            if not value:
                raise ImageRequestError("Image file part is empty.", code="image_file_empty")
            files.append(
                ImagePart(
                    field_name=name,
                    filename=_safe_filename(filename),
                    content_type=_safe_image_content_type(part.get_content_type()),
                    data=value,
                )
            )
            continue
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ImageRequestError("Image form field is not valid UTF-8.", code="invalid_form_field") from exc
        fields[name] = text
    if not any(part.field_name in {"image", "image[]"} for part in files):
        raise ImageRequestError("At least one image file is required.", code="image_file_missing")
    prompt = str(fields.get("prompt") or "").strip()
    if not prompt:
        raise ImageRequestError("Image edit prompt is required.", code="image_prompt_missing")
    normalized = _normalize_image_fields(fields, require_prompt=True)
    return normalized, files


def _normalize_image_fields(value: Mapping[str, Any], *, require_prompt: bool) -> dict[str, Any]:
    prompt = str(value.get("prompt") or "").strip()
    if require_prompt and not prompt:
        raise ImageRequestError("Image prompt is required.", code="image_prompt_missing")
    if len(prompt) > 32_000:
        raise ImageRequestError("Image prompt is too long.", code="image_prompt_too_long")
    model = canonical_public_model(str(value.get("model") or "axio-terra"))
    result: dict[str, Any] = {"model": model, "prompt": prompt}
    for key in _IMAGE_FIELD_ALLOWLIST:
        if key not in value:
            continue
        raw = value.get(key)
        if key in {"stream"}:
            result[key] = _coerce_bool(raw)
        elif key in {"n", "partial_images", "output_compression"}:
            try:
                result[key] = int(raw)
            except (TypeError, ValueError) as exc:
                raise ImageRequestError(f"Image field {key} is invalid.", code="image_field_invalid") from exc
        else:
            result[key] = str(raw)
    if result.get("n", 1) < 1 or result.get("n", 1) > 4:
        raise ImageRequestError("Image n must be between 1 and 4.", code="image_field_invalid")
    if result.get("partial_images", 0) < 0 or result.get("partial_images", 0) > 3:
        raise ImageRequestError("partial_images must be between 0 and 3.", code="image_field_invalid")
    if result.get("output_compression", 0) and not 0 <= result["output_compression"] <= 100:
        raise ImageRequestError("output_compression must be between 0 and 100.", code="image_field_invalid")
    result["stream"] = bool(result.get("stream", False))
    return result


def _safe_filename(value: str) -> str:
    name = os.path.basename(str(value or "image.png")).replace("\x00", "")
    return name[:120] or "image.png"


def _safe_image_content_type(value: str) -> str:
    normalized = str(value or "application/octet-stream").split(";", 1)[0].strip().lower()
    return normalized if normalized.startswith("image/") else "application/octet-stream"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return bool(value)


def _responses_image_generation_payload(
    profile: ModelProfile,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the Responses image-generation tool request.

    Responses image generation is a different wire contract from
    ``/images/generations``. Only fields documented by the image-generation
    tool are nested into the tool declaration; the public Axio request remains
    protocol-neutral at the gateway boundary.
    """

    tool: dict[str, Any] = {"type": "image_generation"}
    for key in (
        "background",
        "moderation",
        "output_compression",
        "output_format",
        "quality",
        "size",
        "partial_images",
    ):
        if key in payload:
            tool[key] = payload[key]
    wire: dict[str, Any] = {
        "model": profile.model,
        "input": str(payload.get("prompt") or ""),
        "tools": [tool],
        "stream": bool(payload.get("stream")),
    }
    # ``n`` is an Images API field. Responses image-generation calls produce
    # one tool result, so it is intentionally not forwarded as an invented
    # Responses parameter.
    return wire


class ImageProviderClient:
    """Provider client for the audited OpenAI Images API transport."""

    def generate(
        self,
        profile: ModelProfile,
        payload: Mapping[str, Any],
        *,
        timeout: float | None = None,
        stream_observer: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> ImageProviderResult:
        if profile.image_capabilities.get("transport") == "responses_image_generation":
            wire = _responses_image_generation_payload(profile, payload)
            event_prefix = "image_generation"
        else:
            wire = {key: value for key, value in payload.items() if key != "model"}
            wire["model"] = profile.model
            event_prefix = "image_generation"
        result, events, protocol = self._post(
            profile,
            str(profile.image_capabilities.get("generation_path") or "/images/generations"),
            json.dumps(wire, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
            timeout=timeout,
            stream=bool(wire.get("stream")),
            event_prefix=event_prefix,
            stream_observer=stream_observer,
        )
        return _result_from_payload(result, events, protocol, event_prefix=event_prefix)

    def edit(
        self,
        profile: ModelProfile,
        fields: Mapping[str, Any],
        files: Sequence[ImagePart],
        *,
        timeout: float | None = None,
        stream_observer: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> ImageProviderResult:
        form_fields = {key: value for key, value in fields.items() if key != "model"}
        form_fields["model"] = profile.model
        body, content_type = _encode_multipart(form_fields, files)
        result, events, protocol = self._post(
            profile,
            str(profile.image_capabilities.get("editing_path") or "/images/edits"),
            body,
            content_type=content_type,
            timeout=timeout,
            stream=bool(form_fields.get("stream")),
            event_prefix="image_edit",
            stream_observer=stream_observer,
        )
        return _result_from_payload(result, events, protocol, event_prefix="image_edit")

    def _post(
        self,
        profile: ModelProfile,
        path: str,
        body: bytes,
        *,
        content_type: str,
        timeout: float | None,
        stream: bool,
        event_prefix: str,
        stream_observer: Callable[[Mapping[str, Any]], bool] | None,
    ) -> tuple[Mapping[str, Any], list[Mapping[str, Any]], str]:
        base_url = _base_url(profile)
        readiness = provider_base_url_readiness(base_url)
        if readiness.get("valid") is not True:
            raise ProviderExecutionError(
                "provider base URL is invalid for image transport",
                error_code=str(readiness.get("reason_code") or "base_url_invalid"),
            )
        auth_scheme = _auth_scheme(profile, key_as_query=profile.api_format == "gemini")
        key_attempts = _rotated_api_key_attempts(profile)
        if auth_scheme != "none" and not key_attempts:
            raise ProviderExecutionError("provider API credentials are not configured", error_code="api_key_missing")
        if auth_scheme == "none" and not key_attempts:
            key_attempts = [("", -1)]
        timeout_budget = _provider_timeout_budget(timeout)
        deadline_at = time.monotonic() + timeout_budget
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        attempts = 0
        attempted_keys: set[int] = set()
        last_key_index: int | None = None
        last_error: ProviderExecutionError | None = None
        rate_limit_events = 0
        _begin_provider_request_trace()
        try:
            for key_attempt_index, (api_key, canonical_key_index) in enumerate(key_attempts, start=1):
                request_url = _url_with_api_key(url, api_key, key_as_query=auth_scheme == "query")
                headers = _provider_headers(content_type=False)
                headers["Content-Type"] = content_type
                headers["Accept"] = "text/event-stream, application/x-ndjson, application/json" if stream else "application/json"
                _apply_auth_headers(headers, api_key, auth_scheme=auth_scheme)
                for retry_attempt_index in range(1, _max_attempts_per_key() + 1):
                    lease = None
                    try:
                        lease = _acquire_provider_traffic_gate(
                            profile,
                            base_url=base_url,
                            api_key=api_key,
                            deadline_at=deadline_at,
                            timeout_budget=timeout_budget,
                            fusion_deadline_bound=False,
                        )
                        attempts += 1
                        if canonical_key_index >= 0:
                            attempted_keys.add(canonical_key_index)
                            last_key_index = canonical_key_index
                        request = urllib.request.Request(
                            request_url,
                            data=body,
                            headers=headers,
                            method="POST",
                        )
                        if stream:
                            parsed, events, protocol = _read_image_stream(
                                request,
                                timeout=_remaining_timeout(deadline_at),
                                event_prefix=event_prefix,
                                stream_observer=stream_observer,
                            )
                        else:
                            parsed = _read_image_json(request, timeout=_remaining_timeout(deadline_at))
                            events, protocol = [], ""
                        _advance_provider_key_rotation(profile, canonical_key_index)
                        _record_provider_request_receipt(
                            status="success",
                            key_attempt_count=len(attempted_keys) if auth_scheme != "none" else 0,
                            transport_attempt_count=attempts,
                            retry_attempt_count=max(0, attempts - (len(attempted_keys) if auth_scheme != "none" else 1)),
                            stream_requested=stream,
                            stream_observed=bool(stream and events),
                            stream_fallback_used=False,
                            stream_protocol=protocol,
                            stream_content_type="text/event-stream" if protocol == "sse" else "application/json",
                            stream_frame_count=len(events),
                            strict_streaming_requested=bool(stream),
                            rate_limit_event_count=rate_limit_events,
                        )
                        return parsed, events, protocol
                    except ProviderExecutionError as exc:
                        last_error = exc
                        if exc.http_status == 429 and lease is not None:
                            _record_provider_rate_limit(lease, retry_after_seconds=exc.retry_after_seconds)
                            rate_limit_events += 1
                        retryable = _provider_error_retryable(exc)
                        if retry_attempt_index >= _max_attempts_per_key() or not retryable or time.monotonic() >= deadline_at:
                            break
                        _sleep_before_retry(retry_attempt_index, deadline_at=deadline_at)
                    except urllib.error.HTTPError as exc:
                        _discard_http_error_body(exc)
                        last_error = ProviderExecutionError(
                            _safe_provider_error_message("http_error", http_status=exc.code),
                            error_code="http_error",
                            http_status=int(exc.code),
                            retry_after_seconds=_retry_after_seconds_from_headers(getattr(exc, "headers", None)),
                        )
                        if last_error.http_status == 429 and lease is not None:
                            _record_provider_rate_limit(lease, retry_after_seconds=last_error.retry_after_seconds)
                            rate_limit_events += 1
                        if retry_attempt_index >= _max_attempts_per_key() or not _provider_error_retryable(last_error) or time.monotonic() >= deadline_at:
                            break
                        _sleep_before_retry(retry_attempt_index, deadline_at=deadline_at)
                    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
                        code = "provider_request_timeout" if isinstance(exc, (TimeoutError, socket.timeout)) else type(exc).__name__
                        last_error = ProviderExecutionError(_safe_provider_error_message(code), error_code=code)
                        if retry_attempt_index >= _max_attempts_per_key() or not _provider_error_retryable(last_error) or time.monotonic() >= deadline_at:
                            break
                        _sleep_before_retry(retry_attempt_index, deadline_at=deadline_at)
                    finally:
                        if lease is not None:
                            _release_provider_traffic_gate(lease)
            if last_key_index is not None:
                _advance_provider_key_rotation(profile, last_key_index)
            _record_provider_request_receipt(
                status="failed",
                key_attempt_count=len(attempted_keys) if auth_scheme != "none" else 0,
                transport_attempt_count=attempts,
                retry_attempt_count=max(0, attempts - (len(attempted_keys) if auth_scheme != "none" else min(1, attempts))),
                stream_requested=stream,
                strict_streaming_requested=bool(stream),
                rate_limit_event_count=rate_limit_events,
            )
            raise last_error or ProviderExecutionError("provider image request failed", error_code="provider_request_failed")
        finally:
            _finish_provider_request_trace()


def _read_image_json(request: urllib.request.Request, *, timeout: float) -> Mapping[str, Any]:
    try:
        with _open_provider_url(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError:
        raise
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderExecutionError("provider image request timed out", error_code="provider_request_timeout") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ProviderExecutionError("provider image transport failed", error_code=type(exc).__name__) from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderExecutionError("provider image response was invalid JSON", error_code="invalid_json") from exc
    if not isinstance(value, Mapping):
        raise ProviderExecutionError("provider image response was not an object", error_code="non_object_json")
    return value


def _read_image_stream(
    request: urllib.request.Request,
    *,
    timeout: float,
    event_prefix: str,
    stream_observer: Callable[[Mapping[str, Any]], bool] | None = None,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]], str]:
    deadline_at = time.monotonic() + min(PROVIDER_MAX_RESPONSE_SECONDS, max(0.001, float(timeout)))
    events: list[Mapping[str, Any]] = []
    protocol = ""
    try:
        with _open_provider_url(request, timeout=timeout) as response:
            content_type = str(getattr(response, "headers", {}).get("Content-Type", "") or "").lower()
            protocol = _stream_protocol_from_content_type(content_type)
            for event_name, payload in _iter_stream_events(response, deadline_at, protocol_state={}, timeout_error_code="provider_response_timeout_exceeded_90s"):
                if payload == "[DONE]" or not isinstance(payload, Mapping):
                    continue
                safe = _safe_image_event(event_name, payload, event_prefix=event_prefix)
                if safe:
                    events.append(safe)
                    if stream_observer is not None and stream_observer(safe) is False:
                        raise ProviderExecutionError(
                            "public image stream was cancelled by the downstream client",
                            error_code="public_stream_cancelled",
                        )
    except urllib.error.HTTPError:
        raise
    except ProviderExecutionError:
        raise
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
        raise ProviderExecutionError("provider image stream failed", error_code=type(exc).__name__) from exc
    if protocol not in {"sse", "ndjson"}:
        raise ProviderExecutionError("provider image stream framing is unverified", error_code="stream_framing_unverified")
    if not events:
        raise ProviderExecutionError("provider image stream was empty", error_code="empty_provider_stream")
    return {}, events, protocol


def _safe_image_event(event_name: str, payload: Mapping[str, Any], *, event_prefix: str) -> dict[str, Any]:
    kind = str(event_name or payload.get("type") or "").strip()
    response_kind_map = {
        "response.image_generation_call.partial_image": f"{event_prefix}.partial_image",
        "response.image_generation_call.completed": f"{event_prefix}.completed",
        "response.output_item.done": f"{event_prefix}.completed",
    }
    if kind == "response.completed":
        response = payload.get("response") if isinstance(payload.get("response"), Mapping) else payload
        output = response.get("output") if isinstance(response.get("output"), list) else []
        for item in output:
            if not isinstance(item, Mapping) or str(item.get("type") or "") != "image_generation_call":
                continue
            result = item.get("result")
            if isinstance(result, str) and result:
                return {"type": f"{event_prefix}.completed", "b64_json": result}
        return {}
    kind = response_kind_map.get(kind, kind)
    allowed = {f"{event_prefix}.partial_image", f"{event_prefix}.completed"}
    if kind not in allowed:
        return {}
    result: dict[str, Any] = {"type": kind}
    for key in ("b64_json", "url", "revised_prompt", "partial_image_index", "output_format", "size"):
        if key in payload and payload.get(key) not in (None, ""):
            result[key] = payload[key]
    if isinstance(payload.get("partial_image_b64"), str) and payload.get("partial_image_b64"):
        result["b64_json"] = payload["partial_image_b64"]
    if isinstance(payload.get("result"), str) and payload.get("result"):
        result["b64_json"] = payload["result"]
    return result if len(result) > 1 else {}


def _result_from_payload(
    payload: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    protocol: str,
    *,
    event_prefix: str,
) -> ImageProviderResult:
    rows: list[Mapping[str, Any]] = []
    raw_data = payload.get("data") if isinstance(payload.get("data"), list) else []
    for item in raw_data:
        safe = _safe_image_item(item)
        if safe:
            rows.append(safe)
    if not rows and isinstance(payload.get("output"), list):
        for item in payload["output"]:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("type") or "") != "image_generation_call":
                continue
            result = item.get("result")
            if isinstance(result, str) and result:
                rows.append({"b64_json": result})
    if not rows:
        indexed: dict[int, dict[str, Any]] = {}
        fallback: dict[str, Any] | None = None
        for event in events:
            if not isinstance(event, Mapping):
                continue
            item = _safe_image_item(event)
            if not item:
                continue
            index = event.get("partial_image_index")
            try:
                index_key = int(index)
            except (TypeError, ValueError):
                index_key = 0
            indexed[index_key] = {**indexed.get(index_key, {}), **item}
            fallback = indexed[index_key]
        rows = [indexed[key] for key in sorted(indexed)] if indexed else ([fallback] if fallback else [])
    if not rows:
        raise ProviderExecutionError("provider image response contained no image data", error_code="empty_provider_response")
    created = _safe_created(payload.get("created", payload.get("created_at")))
    return ImageProviderResult(
        tuple(rows),
        created,
        tuple(dict(event) for event in events),
        protocol,
        event_prefix,
    )


def _safe_image_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in ("b64_json", "url", "revised_prompt"):
        raw = value.get(key)
        if raw not in (None, "") and isinstance(raw, str):
            result[key] = raw
    return result


def _safe_created(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(time.time())
    return max(0, parsed)


def _encode_multipart(fields: Mapping[str, Any], files: Sequence[ImagePart]) -> tuple[bytes, str]:
    boundary = f"----AxioImage{sha256_text(str(time.time_ns()))[:24]}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{_safe_form_name(name)}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for item in files:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{_safe_form_name(item.field_name)}"; '
                    f'filename="{_safe_filename(item.filename)}"\r\n'
                ).encode(),
                f"Content-Type: {item.content_type}\r\n\r\n".encode(),
                item.data,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _safe_form_name(value: str) -> str:
    return "".join(ch for ch in str(value or "")[:80] if ch.isalnum() or ch in {"[", "]", "_", "-"}) or "field"


class ImageRouter:
    """Select one verified image profile and fail over to its next replica."""

    def __init__(self, profiles: Sequence[ModelProfile], *, client: ImageProviderClient | None = None) -> None:
        self.profiles = tuple(profile for profile in profiles if isinstance(profile, ModelProfile))
        self.client = client or ImageProviderClient()

    def generate(
        self,
        payload: Mapping[str, Any],
        *,
        timeout: float | None = None,
        stream_observer: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> tuple[dict[str, Any], ImageProviderResult, ModelProfile]:
        public_model = canonical_public_model(str(payload.get("model") or "axio-terra"))
        selected = self._select(
            public_model,
            operation="generation",
            stream_requested=bool(payload.get("stream")),
        )
        if not selected:
            raise ImageRequestError("No verified image generation model is available.", code="image_capability_unavailable", status=503)
        failures: list[ProviderExecutionError] = []
        for profile in selected:
            observed_events = False

            def observe(event: Mapping[str, Any]) -> bool:
                nonlocal observed_events
                observed_events = True
                return stream_observer(event) if stream_observer is not None else True

            try:
                if stream_observer is None:
                    result = self.client.generate(profile, payload, timeout=timeout)
                else:
                    result = self.client.generate(
                        profile,
                        payload,
                        timeout=timeout,
                        stream_observer=observe,
                    )
                return _public_image_response(public_model, result, profile), result, profile
            except ProviderExecutionError as exc:
                if observed_events or exc.error_code == "public_stream_cancelled":
                    raise
                failures.append(exc)
        raise ImageRequestError("All eligible image providers failed.", code="image_provider_unavailable", status=502) from (failures[-1] if failures else None)

    def edit(
        self,
        payload: Mapping[str, Any],
        files: Sequence[ImagePart],
        *,
        timeout: float | None = None,
        stream_observer: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> tuple[dict[str, Any], ImageProviderResult, ModelProfile]:
        public_model = canonical_public_model(str(payload.get("model") or "axio-terra"))
        selected = self._select(
            public_model,
            operation="editing",
            stream_requested=bool(payload.get("stream")),
        )
        if not selected:
            raise ImageRequestError("No verified image editing model is available.", code="image_capability_unavailable", status=503)
        image_count = sum(1 for item in files if item.field_name in {"image", "image[]"})
        if all(
            image_count > int(profile.image_capabilities.get("max_input_images") or 1)
            for profile in selected
        ):
            raise ImageRequestError(
                "The image provider does not accept this many input images.",
                code="image_input_limit_exceeded",
                status=400,
            )
        failures: list[ProviderExecutionError] = []
        for profile in selected:
            max_images = int(profile.image_capabilities.get("max_input_images") or 1)
            if image_count > max_images:
                continue
            observed_events = False

            def observe(event: Mapping[str, Any]) -> bool:
                nonlocal observed_events
                observed_events = True
                return stream_observer(event) if stream_observer is not None else True

            try:
                if stream_observer is None:
                    result = self.client.edit(profile, payload, files, timeout=timeout)
                else:
                    result = self.client.edit(
                        profile,
                        payload,
                        files,
                        timeout=timeout,
                        stream_observer=observe,
                    )
                return _public_image_response(public_model, result, profile), result, profile
            except ProviderExecutionError as exc:
                if observed_events or exc.error_code == "public_stream_cancelled":
                    raise
                failures.append(exc)
        raise ImageRequestError("All eligible image editing providers failed.", code="image_provider_unavailable", status=502) from (failures[-1] if failures else None)

    def _select(
        self,
        public_model: str,
        *,
        operation: str,
        stream_requested: bool = False,
    ) -> list[ModelProfile]:
        eligible = [
            profile
            for profile in self.profiles
            if (
                profile.image_generation_eligible
                if operation == "generation"
                else profile.image_editing_eligible
            )
            and (
                not stream_requested
                or profile.image_capabilities.get("streaming") is True
            )
            and profile_latency_eligibility(profile).get("eligible") is not False
        ]
        def quality(profile: ModelProfile) -> float:
            value = profile.screening_capability_overall
            if value is None:
                axes = [profile.capability(axis) for axis in ("science_knowledge", "structured_output", "critique", "daily_work")]
                value = sum(axes) / max(1, len(axes))
            return max(0.0, min(1.0, float(value)))
        def latency(profile: ModelProfile) -> int:
            return int(profile.p50_latency_ms or profile.p95_latency_ms or PROVIDER_MAX_RESPONSE_LATENCY_MS)
        if public_model == "axio-fast":
            return sorted(eligible, key=lambda profile: (latency(profile), -quality(profile), profile.profile_id))
        if public_model == "axio-pro":
            return sorted(eligible, key=lambda profile: (-quality(profile), latency(profile), profile.profile_id))
        return sorted(eligible, key=lambda profile: (-quality(profile) * 0.65 + latency(profile) / PROVIDER_MAX_RESPONSE_LATENCY_MS * 0.35, latency(profile), profile.profile_id))


def _public_image_response(public_model: str, result: ImageProviderResult, profile: ModelProfile) -> dict[str, Any]:
    return {
        "created": result.created,
        "data": [dict(item) for item in result.data],
        "model": public_model,
        "metadata": {
            "schema": "axio_fusion_api.image_response.v1",
            "image_route": "single_verified_profile_with_same_model_failover",
            "provider_profile_hash": sha256_text(profile.profile_id),
            "provider_model_ids_persisted": False,
            "raw_provider_response_persisted": False,
            "raw_image_prompt_persisted": False,
            "secrets_persisted": False,
        },
    }


def render_image_stream(
    result: ImageProviderResult,
    *,
    public_model: str,
) -> bytes:
    """Render sanitized native image events as an SSE response."""

    events = list(result.stream_events)
    if not events:
        events = [
            {"type": f"{result.event_prefix}.completed", **dict(item)}
            for item in result.data
        ]
    chunks: list[bytes] = []
    for event in events:
        chunks.append(render_image_event(event, public_model=public_model))
    chunks.append(b"event: done\ndata: [DONE]\n\n")
    return b"".join(chunks)


def render_image_event(event: Mapping[str, Any], *, public_model: str) -> bytes:
    """Render one already-sanitized image event for incremental SSE output."""

    payload = dict(event)
    payload.setdefault("model", public_model)
    event_name = str(payload.get("type") or "")
    if event_name not in IMAGE_STREAM_EVENT_TYPES:
        return b""
    return (
        f"event: {event_name}\n".encode("utf-8")
        + f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
    )


def image_router_summary(router: ImageRouter) -> dict[str, Any]:
    generation = [profile for profile in router.profiles if profile.image_generation_eligible]
    editing = [profile for profile in router.profiles if profile.image_editing_eligible]
    return {
        "schema": "axio_fusion_api.image_router_summary.v1",
        "generation_profile_count": len(generation),
        "editing_profile_count": len(editing),
        "generation_profile_hashes": sorted(sha256_text(profile.profile_id) for profile in generation),
        "editing_profile_hashes": sorted(sha256_text(profile.profile_id) for profile in editing),
        "text_fusion_isolated": True,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }
