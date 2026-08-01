"""Closed protocol-neutral contracts for multimodal input and output formats.

The public API accepts four wire protocols, but the Fusion core must not carry
their vendor-specific block names into routing or orchestration.  This module
owns the small common subset that can be translated without silently losing
meaning: text, image URLs, base64 image data, and file references.

Raw content is intentionally kept usable in request-local memory.  Callers
that persist receipts must use the summary helpers below, which expose only
counts and digests.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


CONTENT_PART_TYPES = ("text", "image", "file")
STRUCTURED_OUTPUT_TYPES = ("text", "json_object", "json_schema")
_DETAIL_LEVELS = frozenset({"auto", "low", "medium", "high"})
# ``_normalize_part`` removes underscores before looking up a type. Keep this
# set in the same canonical spelling so tool/reasoning blocks in historical
# turns are ignored as non-content instead of rejected as unknown input.
_NON_CONTENT_TYPES = frozenset(
    item.casefold().replace("_", "")
    for item in (
        "tool_use",
        "tool_result",
        "function_call",
        "function_call_output",
        "function_response",
        "thinking",
        "redacted_thinking",
        "reasoning",
        "refusal",
    )
)
_IMAGE_MEDIA_PREFIX = "image/"
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class ContentContractError(ValueError):
    """A caller payload cannot be represented by the closed common contract."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code or "invalid_content_contract")[:120]
        super().__init__((message or self.code)[:240])


def normalize_content_parts(
    value: Any,
    *,
    source_format: str = "chat",
) -> tuple[dict[str, Any], ...]:
    """Normalize one native content value into closed Axio content parts."""

    source = _normalize_format(source_format)
    if value is None:
        return ()
    if isinstance(value, str):
        return _text_part(value)
    if isinstance(value, Mapping):
        if "parts" in value and _is_sequence(value.get("parts")):
            return normalize_content_parts(value.get("parts"), source_format=source)
        part = _normalize_part(value, source_format=source)
        return () if part is None else (part,)
    if _is_sequence(value):
        parts: list[dict[str, Any]] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                parts.extend(_text_part(item))
                continue
            if not isinstance(item, Mapping):
                raise ContentContractError(
                    "invalid_content_part",
                    "content parts must be strings or objects",
                )
            part = _normalize_part(item, source_format=source)
            if part is not None:
                parts.append(part)
        return tuple(parts)
    raise ContentContractError(
        "invalid_content_part",
        "content must be a string, object, or array of content parts",
    )


def content_text(parts: Sequence[Mapping[str, Any]] | Any) -> str:
    """Return a routing-safe text projection, with bounded modality markers."""

    rows = _part_rows(parts)
    output: list[str] = []
    for part in rows:
        kind = str(part.get("type") or "")
        if kind == "text":
            text = str(part.get("text") or "")
            if text:
                output.append(text)
        elif kind == "image":
            output.append("[image input]")
        elif kind == "file":
            output.append("[file input]")
    return "\n".join(output).strip()


def has_visual_content(parts: Sequence[Mapping[str, Any]] | Any) -> bool:
    return any(str(part.get("type") or "") == "image" for part in _part_rows(parts))


def has_non_text_content(parts: Sequence[Mapping[str, Any]] | Any) -> bool:
    return any(str(part.get("type") or "") != "text" for part in _part_rows(parts))


def content_parts_safe_summary(parts: Sequence[Mapping[str, Any]] | Any) -> dict[str, Any]:
    """Return a persistence-safe modality summary without URLs or image data."""

    rows = _part_rows(parts)
    type_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    digests: list[str] = []
    for part in rows[:64]:
        kind = str(part.get("type") or "unknown")
        source = str(part.get("source") or "")
        type_counts[kind] = type_counts.get(kind, 0) + 1
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        digest_value = {
            "type": kind,
            "source": source,
            "text": part.get("text") if kind == "text" else None,
            "url": part.get("url") if source == "url" else None,
            "file_id": part.get("file_id") if source == "file_id" else None,
            "file_uri": part.get("file_uri") if source == "file_uri" else None,
            "media_type": part.get("media_type"),
            "data": part.get("data") if source == "base64" else None,
        }
        digests.append(_sha256(_stable_json(digest_value)))
    return {
        "part_count": len(rows),
        "type_counts": dict(sorted(type_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "content_sha256": _sha256(_stable_json(digests)),
        "raw_urls_persisted": False,
        "raw_image_data_persisted": False,
        "raw_file_references_persisted": False,
    }


def render_content_parts(
    parts: Sequence[Mapping[str, Any]] | Any,
    *,
    target_format: str,
) -> Any:
    """Render closed parts for one provider input protocol.

    A ``ContentContractError`` is raised when a source cannot be represented by
    the target protocol.  This is deliberately preferable to dropping an image
    or file reference and sending a semantically different request.
    """

    rows = _part_rows(parts)
    target = _normalize_format(target_format)
    if target == "chat":
        return _render_chat(rows)
    if target == "responses":
        return _render_responses(rows)
    if target == "anthropic":
        return _render_anthropic(rows)
    if target == "gemini":
        return _render_gemini(rows)
    raise ContentContractError("unsupported_target_content_format")


def content_parts_supported_by_format(
    parts: Sequence[Mapping[str, Any]] | Any,
    *,
    target_format: str,
) -> bool:
    try:
        render_content_parts(parts, target_format=target_format)
    except (ContentContractError, TypeError, ValueError):
        return False
    return True


def normalize_structured_output(
    value: Any,
    *,
    api_format: str = "chat",
) -> dict[str, Any]:
    """Normalize one native structured-output declaration.

    The outer contract intentionally contains only three modes.  The JSON
    Schema body is copied as JSON data because schema keywords are extensible,
    but no provider-specific wrapper is retained.
    """

    if value is None or value == "" or (isinstance(value, Mapping) and not value):
        return {}
    if not isinstance(value, Mapping):
        raise ContentContractError(
            "invalid_structured_output",
            "structured output format must be an object",
        )
    raw = dict(value)
    output_type = str(raw.get("type") or "").strip().casefold()
    if output_type not in STRUCTURED_OUTPUT_TYPES:
        raise ContentContractError(
            "unsupported_structured_output_type",
            f"unsupported structured output type: {output_type or 'missing'}",
        )
    if output_type in {"text", "json_object"}:
        return {"type": output_type}

    wrapper = raw.get("json_schema") if isinstance(raw.get("json_schema"), Mapping) else raw
    schema = wrapper.get("schema") if isinstance(wrapper, Mapping) else None
    if not isinstance(schema, Mapping):
        raise ContentContractError(
            "invalid_structured_output_schema",
            "json_schema requires an object schema",
        )
    name = str(wrapper.get("name") or "axio_output").strip()
    if not _NAME_PATTERN.fullmatch(name):
        raise ContentContractError(
            "invalid_structured_output_name",
            "json_schema name must contain only letters, digits, '.', '_' or '-' "
            "and start with an alphanumeric character",
        )
    normalized: dict[str, Any] = {
        "type": "json_schema",
        "name": name,
        "schema": _json_value(schema),
    }
    if "description" in wrapper and wrapper.get("description") not in (None, ""):
        normalized["description"] = str(wrapper.get("description"))[:4096]
    if isinstance(wrapper.get("strict"), bool):
        normalized["strict"] = bool(wrapper.get("strict"))
    normalized["source_api_format"] = _normalize_format(api_format)
    return normalized


def structured_output_from_payload(
    payload: Mapping[str, Any],
    *,
    api_format: str,
) -> dict[str, Any]:
    """Read the native structured-output field from a public request."""

    api = _normalize_format(api_format)
    if api == "chat":
        return normalize_structured_output(payload.get("response_format"), api_format=api) if "response_format" in payload else {}
    if api == "responses":
        text = payload.get("text")
        if isinstance(text, Mapping) and "format" in text:
            return normalize_structured_output(text.get("format"), api_format=api)
        return {}
    if api == "anthropic":
        output_config = payload.get("output_config")
        if isinstance(output_config, Mapping) and "format" in output_config:
            return normalize_structured_output(output_config.get("format"), api_format=api)
        return {}
    if api == "gemini":
        generation = payload.get("generationConfig")
        if not isinstance(generation, Mapping):
            return {}
        mime = str(generation.get("responseMimeType") or "").strip().casefold()
        schema = generation.get("responseSchema")
        if not mime and schema is None:
            return {}
        if mime in {"text/plain", "text"} and schema is None:
            return {"type": "text", "source_api_format": api}
        if mime not in {"application/json", "json"}:
            raise ContentContractError(
                "unsupported_structured_output_mime_type",
                f"unsupported Gemini responseMimeType: {mime or 'missing'}",
            )
        if schema is None:
            return {"type": "json_object", "source_api_format": api}
        return normalize_structured_output(
            {"type": "json_schema", "schema": schema},
            api_format=api,
        )
    return {}


def structured_output_safe_summary(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    output_type = str(raw.get("type") or "")
    schema = raw.get("schema") if isinstance(raw.get("schema"), Mapping) else None
    return {
        "requested": bool(output_type),
        "type": output_type if output_type in STRUCTURED_OUTPUT_TYPES else "",
        "name_sha256": _sha256(str(raw.get("name") or "")) if raw.get("name") else "",
        "schema_sha256": _sha256(_stable_json(schema)) if schema is not None else "",
        "strict": raw.get("strict") if isinstance(raw.get("strict"), bool) else None,
        "raw_schema_persisted": False,
        "raw_provider_wrapper_persisted": False,
    }


def structured_output_wire_fields(
    value: Mapping[str, Any] | Any,
    *,
    target_format: str,
) -> dict[str, Any]:
    """Return only the native wrapper for one provider payload builder."""

    raw = normalize_structured_output(value, api_format=target_format) if value else {}
    if not raw:
        return {}
    output_type = str(raw.get("type") or "")
    if target_format in {"chat", "chat/completions"}:
        if output_type == "json_schema":
            nested = {
                "name": raw["name"],
                "schema": raw["schema"],
            }
            for key in ("description", "strict"):
                if key in raw:
                    nested[key] = raw[key]
            return {"response_format": {"type": "json_schema", "json_schema": nested}}
        return {"response_format": {"type": output_type}}
    if target_format == "responses":
        if output_type == "json_schema":
            native = {
                "type": "json_schema",
                "name": raw["name"],
                "schema": raw["schema"],
            }
            for key in ("description", "strict"):
                if key in raw:
                    native[key] = raw[key]
        else:
            native = {"type": output_type}
        return {"text": {"format": native}}
    if target_format == "anthropic":
        if output_type == "text":
            return {}
        schema = raw.get("schema")
        if output_type == "json_object":
            schema = {"type": "object"}
        native = {"type": "json_schema", "schema": schema}
        return {"output_config": {"format": native}}
    if target_format == "gemini":
        generation: dict[str, Any] = {
            "responseMimeType": "application/json"
            if output_type in {"json_object", "json_schema"}
            else "text/plain"
        }
        if output_type == "json_schema":
            generation["responseSchema"] = raw["schema"]
        return {"generationConfig": generation}
    raise ContentContractError("unsupported_target_structured_output_format")


def _normalize_part(value: Mapping[str, Any], *, source_format: str) -> dict[str, Any] | None:
    raw_type = str(value.get("type") or "").strip().casefold().replace("_", "")
    if raw_type in _NON_CONTENT_TYPES:
        return None
    if source_format == "gemini":
        if any(
            isinstance(value.get(key), Mapping)
            for key in ("functionCall", "function_call", "functionResponse", "function_response")
        ):
            return None
        if isinstance(value.get("inlineData"), Mapping) or isinstance(value.get("inline_data"), Mapping):
            return _image_data_part(value.get("inlineData") or value.get("inline_data") or {})
        if isinstance(value.get("fileData"), Mapping) or isinstance(value.get("file_data"), Mapping):
            return _file_part(value.get("fileData") or value.get("file_data") or {})
        if "text" in value and not raw_type:
            return _text_part(str(value.get("text") or ""))[0] if str(value.get("text") or "") else None
    if raw_type in {"text", "inputtext", "outputtext"} or (not raw_type and "text" in value):
        text = value.get("text")
        if text is None:
            text = value.get("input_text", value.get("output_text", ""))
        return _text_part(str(text or ""))[0] if str(text or "") else None
    if raw_type in {"imageurl", "inputimage"} or "image_url" in value:
        image_url = value.get("image_url")
        detail = value.get("detail")
        file_id = value.get("file_id")
        if isinstance(image_url, Mapping):
            detail = image_url.get("detail", detail)
            image_url = image_url.get("url")
        if file_id not in (None, ""):
            return _file_part({"file_id": file_id, "media_type": value.get("media_type")})
        if image_url in (None, ""):
            raise ContentContractError("invalid_image_part", "image part is missing image_url")
        return _image_url_or_data(str(image_url), detail=detail)
    if raw_type == "image":
        source_value = value.get("source")
        source = source_value if isinstance(source_value, Mapping) else None
        source_type = (
            str(source.get("type") or "url").strip().casefold()
            if isinstance(source, Mapping)
            else str(source_value or "url").strip().casefold()
        )
        if source_type in {"base64", "data"}:
            return _image_data_part(source if isinstance(source, Mapping) else value)
        if source_type == "url":
            url = source.get("url") if isinstance(source, Mapping) else value.get("url")
            return _image_url_or_data(str(url or ""), detail=value.get("detail"))
        raise ContentContractError("unsupported_image_source", f"unsupported image source: {source_type}")
    if raw_type in {"inlineData".casefold().replace("_", ""), "inline_data".replace("_", "")}:
        return _image_data_part(value)
    if raw_type in {"fileData".casefold().replace("_", ""), "file_data".replace("_", "")}:
        return _file_part(value)
    if raw_type in {"inputfile", "file"}:
        return _file_part(value)
    if not raw_type and any(key in value for key in ("fileUri", "file_uri", "file_id", "fileId")):
        return _file_part(value)
    if raw_type:
        raise ContentContractError(
            "unsupported_content_part",
            f"unsupported content part type: {value.get('type')}",
        )
    raise ContentContractError("unsupported_content_part", "content part type is missing")


def _text_part(text: str) -> tuple[dict[str, Any], ...]:
    return ({"type": "text", "text": str(text)},) if text != "" else ()


def _image_url_or_data(value: str, *, detail: Any = None) -> dict[str, Any]:
    url = str(value or "").strip()
    if not url:
        raise ContentContractError("invalid_image_url", "image URL must not be empty")
    if url.startswith("data:"):
        header, separator, data = url.partition(",")
        if separator and ";base64" in header.casefold():
            media_type = header[5:].split(";", 1)[0] or "image/png"
            return _image_data_part({"media_type": media_type, "data": data})
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ContentContractError(
            "invalid_image_url",
            "image URL must be an absolute http or https URL, or a base64 data URL",
        )
    part: dict[str, Any] = {"type": "image", "source": "url", "url": url}
    normalized_detail = str(detail or "").strip().casefold()
    if normalized_detail in _DETAIL_LEVELS:
        part["detail"] = normalized_detail
    return part


def _image_data_part(value: Mapping[str, Any]) -> dict[str, Any]:
    media_type = str(
        value.get("media_type")
        or value.get("mediaType")
        or value.get("mimeType")
        or "image/png"
    ).strip().lower()
    data = str(value.get("data") or "").strip()
    if not media_type.startswith(_IMAGE_MEDIA_PREFIX) or not data:
        raise ContentContractError("invalid_image_data", "image data requires media type and base64 data")
    try:
        base64.b64decode(data.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise ContentContractError("invalid_image_data", "image data is not valid base64") from None
    return {"type": "image", "source": "base64", "media_type": media_type, "data": data}


def _file_part(value: Mapping[str, Any]) -> dict[str, Any]:
    file_id = str(value.get("file_id") or value.get("fileId") or "").strip()
    file_uri = str(
        value.get("file_uri")
        or value.get("fileUri")
        or value.get("uri")
        or value.get("file_url")
        or value.get("fileUrl")
        or ""
    ).strip()
    if not file_id and not file_uri:
        raise ContentContractError("invalid_file_reference", "file reference requires file_id or file_uri")
    media_type = str(
        value.get("media_type")
        or value.get("mediaType")
        or value.get("mimeType")
        or ""
    ).strip().lower()
    result: dict[str, Any] = {"type": "file", "source": "file_id" if file_id else "file_uri"}
    if file_id:
        result["file_id"] = file_id
    if file_uri:
        result["file_uri"] = file_uri
    if media_type:
        result["media_type"] = media_type
    return result


def _render_chat(rows: Sequence[Mapping[str, Any]]) -> Any:
    if not has_non_text_content(rows):
        return content_text(rows)
    rendered: list[dict[str, Any]] = []
    for part in rows:
        kind = str(part.get("type") or "")
        if kind == "text":
            rendered.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        if kind == "image":
            if part.get("source") == "base64":
                url = _data_url(part)
            elif part.get("source") == "url":
                url = str(part.get("url") or "")
            else:
                raise ContentContractError("content_not_representable_for_chat")
            image_url: dict[str, Any] = {"url": url}
            if part.get("detail"):
                image_url["detail"] = part["detail"]
            rendered.append({"type": "image_url", "image_url": image_url})
            continue
        raise ContentContractError("content_not_representable_for_chat")
    return rendered


def _render_responses(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for part in rows:
        kind = str(part.get("type") or "")
        if kind == "text":
            rendered.append({"type": "input_text", "text": str(part.get("text") or "")})
        elif kind == "image":
            image: dict[str, Any] = {"type": "input_image"}
            if part.get("source") == "file_id":
                image["file_id"] = str(part.get("file_id") or "")
            else:
                image["image_url"] = _data_url(part) if part.get("source") == "base64" else str(part.get("url") or "")
            if part.get("detail"):
                image["detail"] = part["detail"]
            rendered.append(image)
        elif kind == "file":
            item: dict[str, Any] = {"type": "input_file"}
            if part.get("source") == "file_id":
                item["file_id"] = str(part.get("file_id") or "")
            else:
                item["file_url"] = str(part.get("file_uri") or "")
            rendered.append(item)
        else:
            raise ContentContractError("content_not_representable_for_responses")
    return rendered


def _render_anthropic(rows: Sequence[Mapping[str, Any]]) -> Any:
    if not has_non_text_content(rows):
        return content_text(rows)
    rendered: list[dict[str, Any]] = []
    for part in rows:
        kind = str(part.get("type") or "")
        if kind == "text":
            rendered.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        if kind != "image":
            raise ContentContractError("content_not_representable_for_anthropic")
        if part.get("source") == "base64":
            source = {
                "type": "base64",
                "media_type": str(part.get("media_type") or "image/png"),
                "data": str(part.get("data") or ""),
            }
        else:
            source = {"type": "url", "url": str(part.get("url") or "")}
        rendered.append({"type": "image", "source": source})
    return rendered


def _render_gemini(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for part in rows:
        kind = str(part.get("type") or "")
        if kind == "text":
            rendered.append({"text": str(part.get("text") or "")})
        elif kind == "image" and part.get("source") == "base64":
            rendered.append(
                {
                    "inlineData": {
                        "mimeType": str(part.get("media_type") or "image/png"),
                        "data": str(part.get("data") or ""),
                    }
                }
            )
        elif kind == "image" and part.get("source") == "url":
            _append_gemini_file_data(rendered, part.get("url"), part.get("media_type"))
        elif kind == "file":
            _append_gemini_file_data(rendered, part.get("file_uri"), part.get("media_type"))
        else:
            raise ContentContractError("content_not_representable_for_gemini")
    return rendered


def _append_gemini_file_data(target: list[dict[str, Any]], uri: Any, media_type: Any) -> None:
    value = str(uri or "").strip()
    parsed = urlsplit(value)
    if not value or (parsed.scheme not in {"gs", "https"}):
        raise ContentContractError("gemini_requires_file_uri_for_remote_image")
    item: dict[str, Any] = {"fileUri": value}
    if media_type:
        item["mimeType"] = str(media_type)
    target.append({"fileData": item})


def _data_url(part: Mapping[str, Any]) -> str:
    return f"data:{str(part.get('media_type') or 'image/png')};base64,{str(part.get('data') or '')}"


def _part_rows(value: Any) -> list[Mapping[str, Any]]:
    if not _is_sequence(value):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _normalize_format(value: Any) -> str:
    raw = str(value or "chat").strip().casefold().replace("_", "-")
    aliases = {
        "chat": "chat",
        "chat/completions": "chat",
        "chat-completions": "chat",
        "openai": "chat",
        "responses": "responses",
        "response": "responses",
        "anthropic": "anthropic",
        "messages": "anthropic",
        "anthropic/messages": "anthropic",
        "gemini": "gemini",
        "google": "gemini",
        "google-gemini": "gemini",
    }
    return aliases.get(raw, raw)


def _json_value(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        raise ContentContractError("invalid_structured_output_schema", "schema must contain JSON values") from None


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
