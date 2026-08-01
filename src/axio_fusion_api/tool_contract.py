from __future__ import annotations

"""Protocol-neutral contracts for declared functions, calls, and results.

The Fusion runtime keeps these objects in memory only.  Durable route and trace
receipts consume hash/count summaries instead, while public API renderers may
return the original function name and arguments to the caller that declared the
tool.  This keeps provider-specific function-call shapes out of routing and
orchestration code without turning tool schemas into operational artifacts.
"""

import json
from typing import Any, Mapping, Sequence

from .content_contract import content_text, normalize_content_parts
from .schemas import sha256_text, stable_json


FUNCTION_TOOL_TYPE = "function"
_NON_FUNCTION_TOOL_TYPES = {
    "fusion",
    "openrouter:fusion",
    "openrouter/fusion",
    "axio_fusion",
    "axio-fusion",
}


def normalize_tool_definitions(
    payload: Mapping[str, Any],
    *,
    api_format: str,
) -> tuple[dict[str, Any], ...]:
    """Normalize public tool declarations to Axio's in-memory function shape."""

    raw_tools = payload.get("tools")
    rows = raw_tools if _is_sequence(raw_tools) else ()
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            continue
        if _is_gemini_declaration_container(raw):
            declarations = raw.get("functionDeclarations")
            for declaration_index, declaration in enumerate(declarations if _is_sequence(declarations) else ()):
                tool = _normalize_function_definition(
                    declaration,
                    api_format=api_format,
                    source_index=index * 1000 + declaration_index,
                    gemini_declaration=True,
                )
                _append_unique_definition(normalized, seen, tool)
            continue
        tool = _normalize_function_definition(raw, api_format=api_format, source_index=index)
        _append_unique_definition(normalized, seen, tool)
    return tuple(normalized)


def normalize_history_events(
    value: Any,
    *,
    api_format: str,
) -> list[dict[str, Any]]:
    """Normalize conversational text, prior calls, and prior tool results.

    The caller can submit the second half of a function-call turn in any of the
    four public formats.  We retain it as private in-memory context so the next
    provider request can use its native representation again.
    """

    if not _is_sequence(value):
        return []
    events: list[dict[str, Any]] = []
    for row_index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        if api_format == "responses":
            events.extend(_responses_history_events(item, row_index=row_index))
        elif api_format == "anthropic":
            events.extend(_anthropic_history_events(item, row_index=row_index))
        elif api_format == "gemini":
            events.extend(_gemini_history_events(item, row_index=row_index))
        else:
            events.extend(_chat_history_events(item, row_index=row_index))
    return _hydrate_tool_result_names(events)


def hydrate_tool_result_names(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Hydrate tool-result names after separately assembled history is merged.

    Responses continuation can combine an earlier assistant function call with
    a later ``function_call_output`` request.  The association must be rebuilt
    after that merge so a subsequent cross-protocol provider turn still has
    the function name it needs.  This operates on request-local memory only.
    """

    return _hydrate_tool_result_names(events)


def provider_tool_declarations(
    tools: Sequence[Mapping[str, Any]],
    *,
    api_format: str,
) -> list[dict[str, Any]]:
    """Render internal function declarations for a provider input protocol."""

    definitions = [tool for tool in tools if is_function_tool(tool)]
    if not definitions:
        return []
    if api_format == "responses":
        return [
            _responses_tool_declaration(tool)
            for tool in definitions
        ]
    if api_format == "anthropic":
        return [
            _anthropic_tool_declaration(tool)
            for tool in definitions
        ]
    if api_format == "gemini":
        return [{"functionDeclarations": [_gemini_function_declaration(tool) for tool in definitions]}]
    return [_chat_tool_declaration(tool) for tool in definitions]


def normalize_provider_tool_calls(result: Mapping[str, Any], *, api_format: str) -> tuple[dict[str, Any], ...]:
    """Extract provider-native tool calls without retaining the full response."""

    rows: list[Mapping[str, Any]] = []
    if api_format == "responses":
        output = result.get("output") if isinstance(result.get("output"), list) else []
        rows.extend(item for item in output if isinstance(item, Mapping) and str(item.get("type") or "") == "function_call")
    elif api_format == "anthropic":
        content = result.get("content") if isinstance(result.get("content"), list) else []
        rows.extend(item for item in content if isinstance(item, Mapping) and str(item.get("type") or "") == "tool_use")
    elif api_format == "gemini":
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        for candidate in candidates[:1]:
            content = candidate.get("content") if isinstance(candidate, Mapping) else {}
            parts = content.get("parts") if isinstance(content, Mapping) and isinstance(content.get("parts"), list) else []
            for part in parts:
                if isinstance(part, Mapping) and isinstance(part.get("functionCall"), Mapping):
                    rows.append(part["functionCall"])
    else:
        choices = result.get("choices") if isinstance(result.get("choices"), list) else []
        message = choices[0].get("message") if choices and isinstance(choices[0], Mapping) and isinstance(choices[0].get("message"), Mapping) else {}
        calls = message.get("tool_calls") if isinstance(message, Mapping) and isinstance(message.get("tool_calls"), list) else []
        rows.extend(item for item in calls if isinstance(item, Mapping))
    return normalize_tool_calls(rows, source_format=api_format)


def normalize_tool_calls(value: Any, *, source_format: str) -> tuple[dict[str, Any], ...]:
    rows = value if _is_sequence(value) else [value] if isinstance(value, Mapping) else []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            continue
        normalized = _normalize_tool_call(item, source_format=source_format, index=index)
        if not normalized:
            continue
        key = (
            str(normalized.get("id") or ""),
            str(normalized.get("name") or ""),
            sha256_text(stable_json(normalized.get("arguments") if isinstance(normalized.get("arguments"), Mapping) else {})),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def normalize_tool_results(value: Any, *, source_format: str) -> tuple[dict[str, Any], ...]:
    rows = value if _is_sequence(value) else [value] if isinstance(value, Mapping) else []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            continue
        result = _normalize_tool_result(item, source_format=source_format, index=index)
        if result:
            normalized.append(result)
    return tuple(normalized)


def tool_call_safe_summary(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [item for item in calls if isinstance(item, Mapping)]
    return {
        "schema": "axio_fusion_api.tool_call_summary.v1",
        "tool_call_count": len(rows),
        "tool_name_sha256s": [sha256_text(str(item.get("name") or "")) for item in rows[:16]],
        "tool_call_id_sha256s": [sha256_text(str(item.get("id") or "")) for item in rows[:16]],
        "argument_sha256s": [
            sha256_text(stable_json(item.get("arguments") if isinstance(item.get("arguments"), Mapping) else {}))
            for item in rows[:16]
        ],
        "source_formats": sorted({str(item.get("source_format") or "") for item in rows if str(item.get("source_format") or "")}),
        "raw_tool_names_persisted": False,
        "raw_tool_arguments_persisted": False,
        "raw_tool_results_persisted": False,
    }


def is_function_tool(tool: Mapping[str, Any]) -> bool:
    tool_type = str(tool.get("type") or FUNCTION_TOOL_TYPE).strip().lower()
    return tool_type == FUNCTION_TOOL_TYPE and bool(tool_name(tool))


def tool_name(tool: Mapping[str, Any]) -> str:
    function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
    return str(tool.get("name") or function.get("name") or "").strip()


def tool_parameters(tool: Mapping[str, Any]) -> dict[str, Any]:
    function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
    value = tool.get("parameters")
    if not isinstance(value, Mapping):
        value = tool.get("input_schema")
    if not isinstance(value, Mapping):
        value = function.get("parameters")
    if not isinstance(value, Mapping):
        value = {"type": "object", "properties": {}}
    return _json_object(value)


def tool_description(tool: Mapping[str, Any]) -> str:
    function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
    return str(tool.get("description") or function.get("description") or "").strip()


def tool_call_to_chat(call: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(call.get("id") or _fallback_call_id(call, index=0)),
        "type": "function",
        "function": {
            "name": str(call.get("name") or ""),
            "arguments": json.dumps(
                call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    }


def tool_call_to_responses(call: Mapping[str, Any]) -> dict[str, Any]:
    call_id = str(call.get("id") or _fallback_call_id(call, index=0))
    return {
        "type": "function_call",
        "id": call_id,
        "call_id": call_id,
        "name": str(call.get("name") or ""),
        "arguments": json.dumps(
            call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "status": "completed",
    }


def tool_call_to_anthropic(call: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_use",
        "id": str(call.get("id") or _fallback_call_id(call, index=0)),
        "name": str(call.get("name") or ""),
        "input": _json_object(call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {}),
    }


def tool_call_to_gemini_part(call: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "functionCall": {
            "name": str(call.get("name") or ""),
            "args": _json_object(call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {}),
        }
    }


def tool_result_to_chat_message(event: Mapping[str, Any]) -> dict[str, Any]:
    result = event.get("tool_result") if isinstance(event.get("tool_result"), Mapping) else event
    return {
        "role": "tool",
        "tool_call_id": str(result.get("call_id") or result.get("id") or ""),
        "content": _tool_result_text(result.get("output")),
    }


def tool_result_to_responses_item(event: Mapping[str, Any]) -> dict[str, Any]:
    result = event.get("tool_result") if isinstance(event.get("tool_result"), Mapping) else event
    return {
        "type": "function_call_output",
        "call_id": str(result.get("call_id") or result.get("id") or ""),
        "output": _tool_result_text(result.get("output")),
    }


def tool_result_to_anthropic_block(event: Mapping[str, Any]) -> dict[str, Any]:
    result = event.get("tool_result") if isinstance(event.get("tool_result"), Mapping) else event
    return {
        "type": "tool_result",
        "tool_use_id": str(result.get("call_id") or result.get("id") or ""),
        "content": _tool_result_text(result.get("output")),
    }


def tool_result_to_gemini_part(event: Mapping[str, Any]) -> dict[str, Any]:
    result = event.get("tool_result") if isinstance(event.get("tool_result"), Mapping) else event
    output = result.get("output")
    response = _json_object(output) if isinstance(output, Mapping) else {"result": _tool_result_text(output)}
    return {
        "functionResponse": {
            "name": str(result.get("name") or "function"),
            "response": response,
        }
    }


def _append_unique_definition(
    target: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    tool: dict[str, Any] | None,
) -> None:
    if not tool:
        return
    key = (str(tool.get("type") or ""), str(tool.get("name") or ""))
    if key in seen:
        return
    seen.add(key)
    target.append(tool)


def _normalize_function_definition(
    raw: Mapping[str, Any],
    *,
    api_format: str,
    source_index: int,
    gemini_declaration: bool = False,
) -> dict[str, Any] | None:
    raw_type = str(raw.get("type") or FUNCTION_TOOL_TYPE).strip().lower()
    function = raw.get("function") if isinstance(raw.get("function"), Mapping) else {}
    if raw_type in _NON_FUNCTION_TOOL_TYPES:
        return None
    name = str(raw.get("name") or function.get("name") or "").strip()
    if not name:
        return None
    parameters = raw.get("parameters")
    if not isinstance(parameters, Mapping):
        parameters = raw.get("input_schema")
    if not isinstance(parameters, Mapping):
        parameters = function.get("parameters")
    if not isinstance(parameters, Mapping) and gemini_declaration:
        parameters = raw.get("parameters")
    strict = raw.get("strict") if "strict" in raw else function.get("strict")
    result: dict[str, Any] = {
        "type": FUNCTION_TOOL_TYPE,
        "name": name,
        "description": str(raw.get("description") or function.get("description") or "").strip(),
        "parameters": _json_object(parameters if isinstance(parameters, Mapping) else {"type": "object", "properties": {}}),
        "_axio_source_format": str(api_format or ""),
        "_axio_source_index": int(source_index),
    }
    if isinstance(strict, bool):
        result["strict"] = strict
    return result


def _chat_history_events(item: Mapping[str, Any], *, row_index: int) -> list[dict[str, Any]]:
    role = str(item.get("role") or "user").strip().lower()
    if role == "tool":
        return [_tool_result_event(item, source_format="chat", index=row_index)]
    calls = normalize_tool_calls(item.get("tool_calls"), source_format="chat") if role == "assistant" else ()
    parts = normalize_content_parts(item.get("content"), source_format="chat")
    return [
        _message_event(
            role=role,
            content=content_text(parts),
            content_parts=parts,
            tool_calls=calls,
        )
    ]


def _responses_history_events(item: Mapping[str, Any], *, row_index: int) -> list[dict[str, Any]]:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "function_call":
        calls = normalize_tool_calls(item, source_format="responses")
        return [_message_event(role="assistant", content="", tool_calls=calls)] if calls else []
    if item_type == "function_call_output":
        return [_tool_result_event(item, source_format="responses", index=row_index)]
    if item_type in {"input_text", "input_image", "input_file"}:
        parts = normalize_content_parts([item], source_format="responses")
        return [_message_event(role="user", content=content_text(parts), content_parts=parts)] if parts else []
    role = str(item.get("role") or "user").strip().lower()
    parts = normalize_content_parts(
        item.get("content") if "content" in item else item.get("input"),
        source_format="responses",
    )
    return [_message_event(role=role, content=content_text(parts), content_parts=parts)]


def _anthropic_history_events(item: Mapping[str, Any], *, row_index: int) -> list[dict[str, Any]]:
    role = str(item.get("role") or "user").strip().lower()
    content = item.get("content")
    parts = normalize_content_parts(content, source_format="anthropic")
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    blocks = content if _is_sequence(content) else []
    for block_index, block in enumerate(blocks):
        if not isinstance(block, Mapping):
            continue
        block_type = str(block.get("type") or "").strip().lower()
        if block_type == "tool_use":
            calls.extend(normalize_tool_calls(block, source_format="anthropic"))
        elif block_type == "tool_result":
            results.append(_tool_result_event(block, source_format="anthropic", index=row_index * 1000 + block_index))
    events = []
    if parts or calls:
        events.append(
            _message_event(
                role=role,
                content=content_text(parts),
                content_parts=parts,
                tool_calls=tuple(calls),
            )
        )
    events.extend(result for result in results if result)
    return events


def _gemini_history_events(item: Mapping[str, Any], *, row_index: int) -> list[dict[str, Any]]:
    raw_role = str(item.get("role") or "user").strip().lower()
    role = "assistant" if raw_role == "model" else raw_role
    parts = item.get("parts") if _is_sequence(item.get("parts")) else item.get("content") if _is_sequence(item.get("content")) else []
    content_parts = normalize_content_parts(parts, source_format="gemini")
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for part_index, part in enumerate(parts):
        if not isinstance(part, Mapping):
            continue
        if isinstance(part.get("functionCall"), Mapping):
            calls.extend(normalize_tool_calls(part["functionCall"], source_format="gemini"))
        elif isinstance(part.get("functionResponse"), Mapping):
            results.append(_tool_result_event(part["functionResponse"], source_format="gemini", index=row_index * 1000 + part_index))
    events = []
    if content_parts or calls:
        events.append(
            _message_event(
                role=role,
                content=content_text(content_parts),
                content_parts=content_parts,
                tool_calls=tuple(calls),
            )
        )
    events.extend(result for result in results if result)
    return events


def _message_event(
    *,
    role: str,
    content: str,
    content_parts: Sequence[Mapping[str, Any]] = (),
    tool_calls: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    normalized_role = str(role or "user").strip().lower()
    # Chat Completions now accepts ``developer`` as a higher-priority
    # instruction role.  The common Fusion contract has one system lane, so
    # preserve its priority by normalizing it to ``system`` instead of
    # silently demoting it to a user turn during cross-protocol conversion.
    if normalized_role == "developer":
        normalized_role = "system"
    event: dict[str, Any] = {
        "role": normalized_role if normalized_role in {"system", "user", "assistant"} else "user",
        "content": content,
    }
    if any(str(part.get("type") or "") != "text" for part in content_parts if isinstance(part, Mapping)):
        event["content_parts"] = [dict(part) for part in content_parts if isinstance(part, Mapping)]
    if tool_calls:
        event["tool_calls"] = [dict(call) for call in tool_calls if isinstance(call, Mapping)]
    return event


def _tool_result_event(item: Mapping[str, Any], *, source_format: str, index: int) -> dict[str, Any]:
    result = _normalize_tool_result(item, source_format=source_format, index=index)
    return {"role": "tool", "content": _tool_result_text(result.get("output")), "tool_result": result}


def _hydrate_tool_result_names(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Recover a result's function name from its earlier normalized call.

    OpenAI-compatible ``role=tool`` messages carry the call id but not the
    function name.  Axio may route the following turn through a different
    provider protocol (for example Gemini), where a function response needs
    that name.  The association remains request-local and is never persisted
    in safe traces.
    """

    call_names: dict[str, str] = {}
    hydrated: list[dict[str, Any]] = []
    for raw_event in events:
        if not isinstance(raw_event, Mapping):
            continue
        event = dict(raw_event)
        calls = event.get("tool_calls") if isinstance(event.get("tool_calls"), list) else []
        for call in calls:
            if not isinstance(call, Mapping):
                continue
            call_id = str(call.get("id") or "").strip()
            name = str(call.get("name") or "").strip()
            if call_id and name:
                call_names[call_id] = name
        result = event.get("tool_result") if isinstance(event.get("tool_result"), Mapping) else None
        if result is not None:
            hydrated_result = dict(result)
            call_id = str(hydrated_result.get("call_id") or "").strip()
            if not str(hydrated_result.get("name") or "").strip() and call_id in call_names:
                hydrated_result["name"] = call_names[call_id]
            event["tool_result"] = hydrated_result
        hydrated.append(event)
    return hydrated


def _normalize_tool_call(item: Mapping[str, Any], *, source_format: str, index: int) -> dict[str, Any] | None:
    function = item.get("function") if isinstance(item.get("function"), Mapping) else {}
    name = str(item.get("name") or function.get("name") or "").strip()
    if not name:
        return None
    raw_arguments = item.get("arguments")
    if raw_arguments is None:
        raw_arguments = item.get("input")
    if raw_arguments is None:
        raw_arguments = item.get("args")
    if raw_arguments is None:
        raw_arguments = function.get("arguments")
    arguments = _parse_arguments(raw_arguments)
    call_id = str(item.get("id") or item.get("call_id") or item.get("tool_use_id") or "").strip()
    result = {
        "id": call_id,
        "type": FUNCTION_TOOL_TYPE,
        "name": name,
        "arguments": arguments,
        "source_format": str(source_format or ""),
    }
    if not result["id"]:
        result["id"] = _fallback_call_id(result, index=index)
    return result


def _normalize_tool_result(item: Mapping[str, Any], *, source_format: str, index: int) -> dict[str, Any]:
    if source_format == "anthropic":
        call_id = str(item.get("tool_use_id") or item.get("id") or "")
        output = item.get("content")
        name = str(item.get("name") or "")
    elif source_format == "gemini":
        call_id = str(item.get("id") or item.get("call_id") or "")
        output = item.get("response") if "response" in item else item.get("output")
        name = str(item.get("name") or "")
    else:
        call_id = str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "")
        output = item.get("output") if "output" in item else item.get("content")
        name = str(item.get("name") or item.get("tool_name") or "")
    result = {
        "call_id": call_id,
        "name": name,
        "output": output,
        "source_format": str(source_format or ""),
    }
    if not result["call_id"]:
        digest_input = {"index": index, "name": name, "output": output}
        result["call_id"] = f"result_{sha256_text(stable_json(digest_input))[:24]}"
    return result


def _chat_tool_declaration(tool: Mapping[str, Any]) -> dict[str, Any]:
    function: dict[str, Any] = {
        "name": tool_name(tool),
        "parameters": tool_parameters(tool),
    }
    description = tool_description(tool)
    if description:
        function["description"] = description
    if isinstance(tool.get("strict"), bool):
        function["strict"] = bool(tool.get("strict"))
    return {"type": "function", "function": function}


def _responses_tool_declaration(tool: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "function",
        "name": tool_name(tool),
        "parameters": tool_parameters(tool),
    }
    description = tool_description(tool)
    if description:
        result["description"] = description
    if isinstance(tool.get("strict"), bool):
        result["strict"] = bool(tool.get("strict"))
    return result


def _anthropic_tool_declaration(tool: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": tool_name(tool),
        "input_schema": tool_parameters(tool),
    }
    description = tool_description(tool)
    if description:
        result["description"] = description
    return result


def _gemini_function_declaration(tool: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": tool_name(tool),
        "parameters": tool_parameters(tool),
    }
    description = tool_description(tool)
    if description:
        result["description"] = description
    return result


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return _json_object(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return _json_object(parsed)
    return {}


def _fallback_call_id(call: Mapping[str, Any], *, index: int) -> str:
    digest_input = {
        "index": index,
        "name": call.get("name"),
        "arguments": call.get("arguments"),
    }
    return f"call_{sha256_text(stable_json(digest_input))[:24]}"


def _tool_result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value or "")


def _content_text(value: Any) -> str:
    return content_text(normalize_content_parts(value, source_format="chat"))


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    # JSON round-tripping avoids retaining arbitrary mapping subclasses while
    # preserving ordinary JSON Schema and function argument structures.
    try:
        parsed = json.loads(json.dumps(dict(value), ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_gemini_declaration_container(value: Mapping[str, Any]) -> bool:
    return isinstance(value.get("functionDeclarations"), Sequence) and not isinstance(value.get("functionDeclarations"), (str, bytes))


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
