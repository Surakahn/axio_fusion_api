from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any, Mapping, Sequence

from .content_contract import (
    ContentContractError,
    content_text,
    has_non_text_content,
    normalize_content_parts,
    structured_output_from_payload,
    structured_output_wire_fields,
)
from .schemas import (
    FusionPolicy,
    FusionRequest,
    FusionResponse,
    canonical_public_model,
    normalize_reasoning_budget_tokens,
    normalize_reasoning_effort,
    rough_token_count,
    sha256_text,
    stable_json,
)
from .tool_contract import (
    normalize_history_events,
    normalize_tool_definitions,
    tool_call_to_anthropic,
    tool_call_to_chat,
    tool_call_to_gemini_part,
    tool_call_to_responses,
)


class CompatibilityError(ValueError):
    """A public protocol request has incompatible closed-control fields."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code or "invalid_protocol_parameter")[:120]
        super().__init__((message or self.code)[:240])


# 部分 Synthesizer 会把内部控制包而不是 acting answer 返回给调用方。字段集合保持收敛：
# 只有同时呈现典型的 answer/reasoning 内部信封时才改写，普通 JSON 答案保持不变。
_PUBLIC_ANSWER_FIELDS = ("answer", "final_answer", "output", "response", "content")
_STRONG_INTERNAL_ENVELOPE_FIELDS = frozenset(
    {
        "reasoning",
        "reasoning_summary",
        "analysis",
        "consensus",
        "contradictions",
        "missing_coverage",
        "ranked_candidates",
        "ready_for_synthesis",
    }
)


def normalize_public_output_text(
    value: Any,
    *,
    structured_output: Mapping[str, Any] | None = None,
) -> str:
    """在不泄漏内部 JSON 信封的前提下返回公共文本。

    这是一个保守的兼容性修复：只有完整 JSON 对象或 JSON 代码围栏同时命中内部控制字段
    时才提取字符串答案；调用方显式声明 JSON 输出契约时始终保留原始文本。
    """

    raw_text = str(value or "")
    text = raw_text.strip()
    requested_type = str(
        structured_output.get("type") if isinstance(structured_output, Mapping) else ""
    ).strip().casefold()
    if not text or requested_type in {"json_object", "json_schema"}:
        return raw_text
    parsed = _parse_complete_public_json(text)
    if not isinstance(parsed, Mapping):
        return raw_text
    fields = {str(key).strip().casefold() for key in parsed}
    if not fields.intersection(_STRONG_INTERNAL_ENVELOPE_FIELDS):
        return raw_text
    for field in _PUBLIC_ANSWER_FIELDS:
        candidate = parsed.get(field)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return raw_text


def _parse_complete_public_json(text: str) -> Any | None:
    candidate = text.strip()
    if candidate.casefold().startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    elif candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate[3:-3].strip()
    if not candidate.startswith(("{", "[")) or not candidate.endswith(("}", "]")):
        return None
    try:
        return json.loads(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _public_output_normalization_receipt(
    original: Any,
    normalized: str,
    *,
    structured_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    original_text = str(original or "")
    requested_type = str(
        structured_output.get("type") if isinstance(structured_output, Mapping) else ""
    ).strip().casefold()
    applied = original_text != normalized
    return {
        "schema": "axio_fusion_api.public_output_normalization.v1",
        "applied": applied,
        "reason": (
            "internal_json_answer_extracted"
            if applied
            else "explicit_structured_output_preserved"
            if requested_type in {"json_object", "json_schema"}
            else "unchanged"
        ),
        "original_char_count": len(original_text),
        "public_char_count": len(normalized),
        "original_sha256": sha256_text(original_text),
        "public_sha256": sha256_text(normalized),
        "structured_output_type": requested_type,
        "raw_output_persisted": False,
        "secrets_persisted": False,
    }


def _public_text_and_normalization(
    response: FusionResponse,
) -> tuple[str, dict[str, Any]]:
    public_text = normalize_public_output_text(
        response.text,
        structured_output=response.request.structured_output,
    )
    return public_text, _public_output_normalization_receipt(
        response.text,
        public_text,
        structured_output=response.request.structured_output,
    )


def _public_usage(response: FusionResponse, public_text: str) -> dict[str, int]:
    usage = response.usage()
    if public_text == response.text:
        return usage
    completion_tokens = rough_token_count(public_text)
    return {
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": completion_tokens,
        "total_tokens": usage["prompt_tokens"] + completion_tokens,
    }


def canonicalize_payload(payload: Mapping[str, Any], *, api_format: str = "chat/completions") -> FusionRequest:
    normalized = normalize_api_format(api_format)
    model = str(payload.get("model") or _model_from_gemini_payload(payload) or "axio-terra")
    metadata = _public_metadata(payload.get("metadata"))
    if _is_openrouter_fusion_alias(model):
        metadata["openrouter_fusion_model_alias"] = True
    task_type = str(payload.get("task_type") or payload.get("axio_task_type") or metadata.get("task_type") or "auto")
    requested = tuple(
        str(item)
        for item in payload.get("requested_capabilities", [])
        if str(item).strip()
    ) if isinstance(payload.get("requested_capabilities"), Sequence) and not isinstance(payload.get("requested_capabilities"), (str, bytes)) else ()
    policy = _policy_from_payload(payload)
    generation_config = _generation_config(payload)
    temperature = _optional_float(payload.get("temperature"))
    if temperature is None:
        temperature = _optional_float(generation_config.get("temperature"))
    top_p_value = payload.get("top_p")
    if top_p_value in (None, ""):
        top_p_value = generation_config.get("topP")
    top_p = _optional_float(top_p_value)
    reasoning_effort = _reasoning_effort_from_payload(payload, api_format=normalized)
    reasoning_budget_tokens = _reasoning_budget_from_payload(
        payload,
        api_format=normalized,
    )
    structured_output = structured_output_from_payload(payload, api_format=normalized)
    history_events: list[dict[str, Any]] = []
    if normalized == "responses":
        system = _responses_instructions_to_text(payload.get("instructions"))
        messages = _responses_input_to_messages(payload.get("input"))
        history_events = normalize_history_events(payload.get("input"), api_format="responses")
    elif normalized == "anthropic":
        system = _text_only_content(payload.get("system"), source_format="anthropic")
        messages = _message_rows(payload.get("messages"), source_format="anthropic")
        history_events = normalize_history_events(payload.get("messages"), api_format="anthropic")
    elif normalized == "gemini":
        system = _gemini_system_to_text(payload.get("systemInstruction") or payload.get("system_instruction"))
        messages = _gemini_contents_to_messages(payload.get("contents"))
        history_events = normalize_history_events(payload.get("contents"), api_format="gemini")
    else:
        system = ""
        messages = _message_rows(payload.get("messages"), source_format="chat")
        history_events = normalize_history_events(payload.get("messages"), api_format="chat")
        if not messages and payload.get("prompt"):
            prompt_parts = normalize_content_parts(payload.get("prompt"), source_format="chat")
            messages = [{"role": "user", "content": content_text(prompt_parts), "content_parts": prompt_parts}]
    msg_system, history, prompt, current_content_parts = _messages_to_parts(messages)
    tools = _tools_from_payload(payload, api_format=normalized)
    request_history = _request_history_with_protocol_events(history, history_events, prompt=prompt)
    if _current_prompt_is_in_history(
        history_events,
        prompt=prompt,
        content_parts=current_content_parts,
    ):
        metadata["_axio_current_prompt_in_history"] = True
    system_text = "\n".join(
        part.strip()
        for part in (system, msg_system)
        if str(part or "").strip()
    )
    return FusionRequest(
        model=canonical_public_model(model),
        prompt=prompt,
        system=system_text or "You are Axio Fusion, a careful and evidence-aware assistant.",
        content_parts=tuple(current_content_parts),
        history=tuple(request_history),
        api_format=normalized,
        task_type=task_type,
        requested_capabilities=requested,
        reasoning_effort=reasoning_effort,
        reasoning_budget_tokens=reasoning_budget_tokens,
        structured_output=structured_output,
        temperature=temperature,
        top_p=top_p,
        max_output_tokens=_max_output_tokens(payload, normalized),
        stop=_stop_sequences(payload, normalized),
        tools=tuple(item for item in tools if isinstance(item, Mapping)),
        metadata=dict(metadata),
        policy=policy,
    )


def _reasoning_effort_from_payload(
    payload: Mapping[str, Any],
    *,
    api_format: str,
) -> str:
    """Read the native reasoning field before a compatibility fallback.

    Chat Completions carries ``reasoning_effort`` at the top level while
    Responses carries ``reasoning.effort``.  Accepting the other spelling as a
    fallback makes the public gateway tolerant of clients that share one
    request builder. A duplicated field is accepted only when both normalized
    values agree; a conflict is a visible 4xx rather than a silent native-field
    preference. No raw vendor object is preserved in the internal request.
    """

    nested = payload.get("reasoning")
    nested_effort = (
        normalize_reasoning_effort(nested.get("effort"))
        if isinstance(nested, Mapping)
        else ""
    )
    top_level_effort = normalize_reasoning_effort(payload.get("reasoning_effort"))
    if top_level_effort and nested_effort and top_level_effort != nested_effort:
        raise CompatibilityError(
            "conflicting_reasoning_effort",
            "reasoning_effort conflicts with reasoning.effort",
        )
    if api_format == "responses":
        return nested_effort or top_level_effort
    if api_format in {"chat", "chat/completions"}:
        return top_level_effort or nested_effort
    return top_level_effort


def _reasoning_budget_from_payload(
    payload: Mapping[str, Any],
    *,
    api_format: str,
) -> int | None:
    """Parse native budget controls into the closed request contract.

    The native field wins over the generic compatibility alias. Parsing does
    not authorize forwarding; the selected provider profile must verify the
    exact budget and streaming endpoint first.
    """

    generic = normalize_reasoning_budget_tokens(
        payload.get("reasoning_budget_tokens", payload.get("reasoningBudgetTokens"))
    )
    if api_format == "anthropic":
        thinking = payload.get("thinking")
        if isinstance(thinking, Mapping):
            thinking_type = str(thinking.get("type") or "").strip().casefold()
            if thinking_type == "disabled":
                if generic is not None:
                    raise CompatibilityError(
                        "conflicting_reasoning_budget",
                        "reasoning_budget_tokens conflicts with disabled thinking",
                    )
                return None
            native = normalize_reasoning_budget_tokens(
                thinking.get("budget_tokens", thinking.get("budgetTokens"))
            )
            if native is not None:
                if generic is not None and generic != native:
                    raise CompatibilityError(
                        "conflicting_reasoning_budget",
                        "reasoning_budget_tokens conflicts with thinking.budget_tokens",
                    )
                return native
    if api_format == "gemini":
        config = _generation_config(payload)
        thinking_config = config.get("thinkingConfig")
        if not isinstance(thinking_config, Mapping):
            thinking_config = config.get("thinking_config")
        if isinstance(thinking_config, Mapping):
            native = normalize_reasoning_budget_tokens(
                thinking_config.get(
                    "thinkingBudget",
                    thinking_config.get("thinking_budget"),
                )
            )
            if native is not None:
                if generic is not None and generic != native:
                    raise CompatibilityError(
                        "conflicting_reasoning_budget",
                        "reasoning_budget_tokens conflicts with thinkingConfig.thinkingBudget",
                    )
                return native
    return generic


def _public_metadata(value: Any) -> dict[str, Any]:
    """Keep caller metadata separate from Axio's private execution markers.

    Internal ``_axio_*`` fields are added only while the orchestrator assembles
    a provider-local turn.  Letting an API caller supply them could suppress a
    role prompt or cause adapters to omit the current user turn.  The
    OpenRouter-alias marker is likewise derived from the requested model name,
    not caller metadata.
    """

    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if not str(key).startswith("_axio_")
        and str(key) != "openrouter_fusion_model_alias"
    }


def render_response(
    response: FusionResponse,
    *,
    api_format: str | None = None,
    responses_store: bool | None = None,
) -> dict[str, Any]:
    normalized = normalize_api_format(api_format or response.request.api_format)
    public_text, normalization_receipt = _public_text_and_normalization(response)
    usage = _public_usage(response, public_text)
    metadata = _response_metadata(response, normalization_receipt=normalization_receipt)
    if normalized == "responses" and responses_store is not None:
        metadata = _responses_continuation_metadata(metadata, stored=responses_store)
    tool_calls = tuple(call for call in response.tool_calls if isinstance(call, Mapping))
    if normalized == "responses":
        output = []
        if public_text:
            output.append(
                {
                    "type": "message",
                    "id": f"{response.response_id}-message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "annotations": [],
                            "text": public_text,
                        }
                    ],
                }
            )
        output.extend(tool_call_to_responses(call) for call in tool_calls)
        if not output:
            output.append(
                {
                    "type": "message",
                    "id": f"{response.response_id}-message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [],
                }
            )
        rendered = {
            "id": response.response_id,
            "object": "response",
            "created_at": response.created,
            "background": False,
            "model": response.request.public_model,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "completed_at": response.created,
            "max_output_tokens": response.request.max_output_tokens,
            "max_tool_calls": None,
            "parallel_tool_calls": len(tool_calls) > 1,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "service_tier": "default",
            "text": {
                "format": (
                    structured_output_wire_fields(
                        response.request.structured_output,
                        target_format="responses",
                    ).get("text", {}).get("format")
                    or {"type": "text"}
                )
            },
            "temperature": response.request.temperature,
            "tool_choice": "auto",
            "tools": [],
            "top_p": response.request.top_p,
            "truncation": "disabled",
            "user": None,
            "output_text": public_text,
            "output": output,
            "usage": _responses_usage_payload(usage),
            "metadata": metadata,
        }
        if responses_store is not None:
            rendered["store"] = bool(responses_store)
        return rendered
    if normalized == "anthropic":
        content = []
        if public_text:
            content.append({"type": "text", "text": public_text})
        content.extend(tool_call_to_anthropic(call) for call in tool_calls)
        if not content:
            content.append({"type": "text", "text": ""})
        return {
            "id": response.response_id,
            "type": "message",
            "role": "assistant",
            "model": response.request.public_model,
            "content": content,
            "stop_reason": "tool_use" if tool_calls else "end_turn",
            "usage": {
                "input_tokens": usage["prompt_tokens"],
                "output_tokens": usage["completion_tokens"],
            },
            "metadata": metadata,
        }
    if normalized == "gemini":
        parts = []
        if public_text:
            parts.append({"text": public_text})
        parts.extend(tool_call_to_gemini_part(call) for call in tool_calls)
        return {
            "responseId": response.response_id,
            "modelVersion": response.request.public_model,
            "candidates": [
                {
                    "index": 0,
                    "content": {"role": "model", "parts": parts},
                    "finishReason": "STOP" if not tool_calls else "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": usage["prompt_tokens"],
                "candidatesTokenCount": usage["completion_tokens"],
                "totalTokenCount": usage["total_tokens"],
            },
            "metadata": metadata,
        }
    message: dict[str, Any] = {"role": "assistant", "content": public_text or None}
    if tool_calls:
        message["tool_calls"] = [tool_call_to_chat(call) for call in tool_calls]
    return {
        "id": response.response_id,
        "object": "chat.completion",
        "created": int(response.created or time.time()),
        "model": response.request.public_model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": usage,
        "metadata": metadata,
    }


class IncrementalStreamRenderer:
    """Render one public response as protocol-native incremental events.

    The renderer accepts only final visible text deltas.  It does not know
    about provider events or Fusion's internal candidate/Judge traffic, which
    makes it impossible for those private messages to leak through the public
    API stream by accident.
    """

    def __init__(
        self,
        request: FusionRequest,
        *,
        api_format: str | None = None,
        response_id: str,
        created: int | None = None,
        responses_store: bool | None = None,
        include_usage: bool = False,
    ) -> None:
        self.request = request
        self.api_format = normalize_api_format(api_format or request.api_format)
        self.response_id = str(response_id)
        self.created = int(created if created is not None else time.time())
        self.responses_store = responses_store
        self.include_usage = bool(include_usage)
        self._started = False
        self._completed = False
        self._text_started = False
        self._emitted_text_characters = 0
        self._responses_sequence_number = 0
        self._anthropic_next_content_index = 0

    def start(self) -> bytes:
        if self._started:
            return b""
        self._started = True
        if self.api_format == "responses":
            response = self._responses_in_progress_object()
            return self._responses_events(
                [
                    (
                        "response.created",
                        {"type": "response.created", "response": response},
                    ),
                    (
                        "response.in_progress",
                        {"type": "response.in_progress", "response": response},
                    ),
                ]
            )
        if self.api_format == "anthropic":
            return _sse_bytes(
                [
                    (
                        "message_start",
                        {
                            "type": "message_start",
                            "message": {
                                "id": self.response_id,
                                "type": "message",
                                "role": "assistant",
                                "model": self.request.public_model,
                                "content": [],
                                "stop_reason": None,
                                "stop_sequence": None,
                                "usage": {"input_tokens": 0, "output_tokens": 0},
                                "metadata": self._pending_metadata(),
                            },
                        },
                    )
                ]
            )
        if self.api_format == "chat/completions":
            return _sse_bytes(
                [
                    (
                        None,
                        {
                            "id": self.response_id,
                            "object": "chat.completion.chunk",
                            "created": self.created,
                            "model": self.request.public_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant"},
                                    "finish_reason": None,
                                }
                            ],
                            "metadata": self._pending_metadata(),
                        },
                    )
                ]
            )
        return b""

    def text_delta(self, value: Any) -> bytes:
        text = str(value or "")
        if not text or self._completed:
            return b""
        prefix = self.start()
        self._text_started = True
        self._emitted_text_characters += len(text)
        if self.api_format == "responses":
            events: list[tuple[str | None, Mapping[str, Any] | str]] = []
            if self._emitted_text_characters == len(text):
                events.extend(self._responses_text_start_events())
            events.append(
                (
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": self._responses_message_item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "logprobs": [],
                        "delta": text,
                    },
                )
            )
            return prefix + self._responses_events(events)
        if self.api_format == "anthropic":
            events = []
            if self._emitted_text_characters == len(text):
                events.append(
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": self._anthropic_next_content_index,
                            "content_block": {"type": "text", "text": ""},
                        },
                    )
                )
            events.append(
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": self._anthropic_next_content_index,
                        "delta": {"type": "text_delta", "text": text},
                    },
                )
            )
            return prefix + _sse_bytes(events)
        if self.api_format == "gemini":
            return prefix + _sse_bytes(
                [
                    (
                        None,
                        {
                            "responseId": self.response_id,
                            "modelVersion": self.request.public_model,
                            "candidates": [
                                {
                                    "index": 0,
                                    "content": {"role": "model", "parts": [{"text": text}]},
                                }
                            ],
                        },
                    )
                ]
            )
        return prefix + _sse_bytes(
            [
                (
                    None,
                    {
                        "id": self.response_id,
                        "object": "chat.completion.chunk",
                        "created": self.created,
                        "model": self.request.public_model,
                        "choices": [
                            {"index": 0, "delta": {"content": text}, "finish_reason": None}
                        ],
                    },
                )
            ]
        )

    def complete(self, response: FusionResponse) -> bytes:
        if self._completed:
            return b""
        self._completed = True
        public_text = normalize_public_output_text(
            response.text,
            structured_output=response.request.structured_output,
        )
        public_response = (
            response
            if public_text == response.text
            else replace(response, text=public_text)
        )
        body = self.start()
        remaining_text = self._remaining_final_text(public_text)
        if remaining_text:
            self._completed = False
            body += self.text_delta(remaining_text)
            self._completed = True
        tool_calls = tuple(call for call in public_response.tool_calls if isinstance(call, Mapping))
        if self.api_format == "responses":
            body += self._complete_responses(public_response, tool_calls)
        elif self.api_format == "anthropic":
            body += self._complete_anthropic(public_response, tool_calls)
        elif self.api_format == "gemini":
            body += self._complete_gemini(public_response, tool_calls)
        else:
            body += self._complete_chat(public_response, tool_calls)
        return body

    def error(self, *, code: str = "stream_interrupted", message: str = "The response stream ended before completion.") -> bytes:
        if self._completed:
            return b""
        self._completed = True
        body = self.start()
        safe_message = str(message or "The response stream ended before completion.")[:240]
        safe_code = str(code or "stream_interrupted")[:80]
        if self.api_format == "responses":
            failed = {
                **self._responses_in_progress_object(),
                "status": "failed",
                "error": {"code": safe_code, "message": safe_message},
                "completed_at": int(time.time()),
            }
            return body + self._responses_events(
                [
                    (
                        "response.failed",
                        {"type": "response.failed", "response": failed},
                    )
                ]
            )
        if self.api_format == "anthropic":
            return body + _sse_bytes(
                [
                    (
                        "error",
                        {
                            "type": "error",
                            "error": {"type": "api_error", "message": safe_message},
                        },
                    )
                ]
            )
        if self.api_format == "gemini":
            return body + _sse_bytes(
                [
                    (
                        None,
                        {
                            "error": {
                                "code": 502,
                                "status": "UNKNOWN",
                                "message": safe_message,
                            }
                        },
                    )
                ]
            )
        return body + _sse_bytes(
            [
                (
                    None,
                    {"error": {"message": safe_message, "code": safe_code}},
                ),
                (None, "[DONE]"),
            ]
        )

    @property
    def _responses_message_item_id(self) -> str:
        return f"{self.response_id}-message"

    def _pending_metadata(self) -> dict[str, Any]:
        return {
            "schema": "axio_fusion_api.stream_metadata.v1",
            "external_model_name": self.request.public_model,
            "provider_calls_recorded": False,
            "request_fingerprint": self.request.request_fingerprint,
            "raw_prompt_persisted": False,
            "raw_source_text_persisted": False,
            "secrets_persisted": False,
        }

    def _remaining_final_text(self, text: Any) -> str:
        final_text = str(text or "")
        if not self._text_started:
            return final_text
        if len(final_text) > self._emitted_text_characters:
            return final_text[self._emitted_text_characters :]
        return ""

    def _responses_in_progress_object(self) -> dict[str, Any]:
        metadata = self._pending_metadata()
        if self.responses_store is not None:
            metadata = _responses_continuation_metadata(
                metadata,
                stored=bool(self.responses_store),
            )
        response = {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created,
            "background": False,
            "model": self.request.public_model,
            "status": "in_progress",
            "error": None,
            "incomplete_details": None,
            "completed_at": None,
            "max_output_tokens": self.request.max_output_tokens,
            "max_tool_calls": None,
            "parallel_tool_calls": False,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "service_tier": "default",
            "text": {"format": {"type": "text"}},
            "temperature": self.request.temperature,
            "tool_choice": "auto",
            "tools": [],
            "top_p": self.request.top_p,
            "truncation": "disabled",
            "user": None,
            "output": [],
            "output_text": "",
            "usage": None,
            "metadata": metadata,
        }
        if self.responses_store is not None:
            response["store"] = bool(self.responses_store)
        return response

    def _responses_events(
        self,
        events: Sequence[tuple[str | None, Mapping[str, Any] | str]],
    ) -> bytes:
        numbered: list[tuple[str | None, Mapping[str, Any] | str]] = []
        for event_name, payload in events:
            if isinstance(payload, Mapping):
                self._responses_sequence_number += 1
                payload = {
                    **payload,
                    **({"response_id": self.response_id} if "response_id" not in payload else {}),
                    "sequence_number": self._responses_sequence_number,
                }
            numbered.append((event_name, payload))
        return _sse_bytes(numbered)

    def _responses_text_start_events(self) -> list[tuple[str | None, Mapping[str, Any] | str]]:
        return [
            (
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "type": "message",
                        "id": self._responses_message_item_id,
                        "status": "in_progress",
                        "role": "assistant",
                        "content": [],
                    },
                },
            ),
            (
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "item_id": self._responses_message_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "annotations": [], "text": ""},
                },
            ),
        ]

    def _complete_responses(
        self,
        response: FusionResponse,
        tool_calls: Sequence[Mapping[str, Any]],
    ) -> bytes:
        events: list[tuple[str | None, Mapping[str, Any] | str]] = []
        if self._text_started or not tool_calls:
            if not self._text_started:
                events.extend(self._responses_text_start_events())
                self._text_started = True
            final_text = str(response.text or "")
            text_part = {"type": "output_text", "annotations": [], "text": final_text}
            text_item = {
                "type": "message",
                "id": self._responses_message_item_id,
                "status": "completed",
                "role": "assistant",
                "content": [text_part],
            }
            events.extend(
                [
                    (
                        "response.output_text.done",
                        {
                            "type": "response.output_text.done",
                            "item_id": self._responses_message_item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "logprobs": [],
                            "text": final_text,
                        },
                    ),
                    (
                        "response.content_part.done",
                        {
                            "type": "response.content_part.done",
                            "item_id": self._responses_message_item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "part": text_part,
                        },
                    ),
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": text_item,
                        },
                    ),
                ]
            )
        output_index = 1 if self._text_started else 0
        for call in tool_calls:
            call_item = tool_call_to_responses(call)
            arguments = str(call_item.get("arguments") or "{}")
            item_id = str(call_item.get("id") or "")
            events.extend(
                [
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "output_index": output_index,
                            "item": {**call_item, "status": "in_progress", "arguments": ""},
                        },
                    ),
                    (
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "item_id": item_id,
                            "call_id": str(call_item.get("call_id") or item_id),
                            "output_index": output_index,
                            "delta": arguments,
                        },
                    ),
                    (
                        "response.function_call_arguments.done",
                        {
                            "type": "response.function_call_arguments.done",
                            "item_id": item_id,
                            "call_id": str(call_item.get("call_id") or item_id),
                            "output_index": output_index,
                            "name": str(call_item.get("name") or ""),
                            "arguments": arguments,
                        },
                    ),
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": output_index,
                            "item": call_item,
                        },
                    ),
                ]
            )
            output_index += 1
        events.append(
            (
                "response.completed",
                {
                    "type": "response.completed",
                    "response": render_response(
                        response,
                        api_format="responses",
                        responses_store=self.responses_store,
                    ),
                },
            )
        )
        return self._responses_events(events)

    def _complete_anthropic(
        self,
        response: FusionResponse,
        tool_calls: Sequence[Mapping[str, Any]],
    ) -> bytes:
        events: list[tuple[str | None, Mapping[str, Any] | str]] = []
        if self._text_started or not tool_calls:
            if not self._text_started:
                events.append(
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": self._anthropic_next_content_index,
                            "content_block": {"type": "text", "text": ""},
                        },
                    )
                )
                self._text_started = True
            events.append(
                (
                    "content_block_stop",
                    {"type": "content_block_stop", "index": self._anthropic_next_content_index},
                )
            )
            self._anthropic_next_content_index += 1
        for call in tool_calls:
            rendered_call = tool_call_to_anthropic(call)
            tool_input = rendered_call.get("input") if isinstance(rendered_call.get("input"), Mapping) else {}
            events.extend(
                [
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": self._anthropic_next_content_index,
                            "content_block": {**rendered_call, "input": {}},
                        },
                    ),
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": self._anthropic_next_content_index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(tool_input, ensure_ascii=False, separators=(",", ":")),
                            },
                        },
                    ),
                    (
                        "content_block_stop",
                        {"type": "content_block_stop", "index": self._anthropic_next_content_index},
                    ),
                ]
            )
            self._anthropic_next_content_index += 1
        usage = response.usage()
        events.extend(
            [
                (
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "tool_use" if tool_calls else "end_turn", "stop_sequence": None},
                        "usage": {"output_tokens": usage["completion_tokens"]},
                    },
                ),
                ("message_stop", {"type": "message_stop"}),
            ]
        )
        return _sse_bytes(events)

    def _complete_gemini(
        self,
        response: FusionResponse,
        tool_calls: Sequence[Mapping[str, Any]],
    ) -> bytes:
        usage = response.usage()
        return _sse_bytes(
            [
                (
                    None,
                    {
                        "responseId": self.response_id,
                        "modelVersion": self.request.public_model,
                        "candidates": [
                            {
                                "index": 0,
                                "content": {
                                    "role": "model",
                                    "parts": [tool_call_to_gemini_part(call) for call in tool_calls],
                                },
                                "finishReason": "STOP",
                            }
                        ],
                        "usageMetadata": {
                            "promptTokenCount": usage["prompt_tokens"],
                            "candidatesTokenCount": usage["completion_tokens"],
                            "totalTokenCount": usage["total_tokens"],
                        },
                        "metadata": _stream_metadata(response),
                    },
                )
            ]
        )

    def _complete_chat(
        self,
        response: FusionResponse,
        tool_calls: Sequence[Mapping[str, Any]],
    ) -> bytes:
        events: list[tuple[str | None, Mapping[str, Any] | str]] = []
        for index, call in enumerate(tool_calls):
            rendered_call = tool_call_to_chat(call)
            events.extend(
                [
                    (
                        None,
                        {
                            "id": self.response_id,
                            "object": "chat.completion.chunk",
                            "created": self.created,
                            "model": self.request.public_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": index,
                                                "id": rendered_call["id"],
                                                "type": "function",
                                                "function": {"name": rendered_call["function"]["name"], "arguments": ""},
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        },
                    ),
                    (
                        None,
                        {
                            "id": self.response_id,
                            "object": "chat.completion.chunk",
                            "created": self.created,
                            "model": self.request.public_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": index,
                                                "function": {"arguments": rendered_call["function"]["arguments"]},
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        },
                    ),
                ]
            )
        events.append(
            (
                None,
                {
                    "id": self.response_id,
                    "object": "chat.completion.chunk",
                    "created": self.created,
                    "model": self.request.public_model,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "tool_calls" if tool_calls else "stop"}
                    ],
                },
            )
        )
        if self.include_usage:
            events.append(
                (
                    None,
                    {
                        "id": self.response_id,
                        "object": "chat.completion.chunk",
                        "created": self.created,
                        "model": self.request.public_model,
                        "choices": [],
                        "usage": response.usage(),
                    },
                )
            )
        events.append((None, "[DONE]"))
        return _sse_bytes(events)


def render_stream_events(
    response: FusionResponse,
    *,
    api_format: str | None = None,
    responses_store: bool | None = None,
    include_usage: bool = False,
) -> bytes:
    normalized = normalize_api_format(api_format or response.request.api_format)
    public_text, normalization_receipt = _public_text_and_normalization(response)
    tool_calls = tuple(call for call in response.tool_calls if isinstance(call, Mapping))
    if normalized == "responses":
        message_item_id = f"{response.response_id}-message"
        created_response: dict[str, Any] = {
            "id": response.response_id,
            "object": "response",
            "created_at": response.created,
            "background": False,
            "model": response.request.public_model,
            "status": "in_progress",
            "error": None,
            "incomplete_details": None,
            "completed_at": None,
            "max_output_tokens": response.request.max_output_tokens,
            "max_tool_calls": None,
            "parallel_tool_calls": len(tool_calls) > 1,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "service_tier": "default",
            "text": {"format": {"type": "text"}},
            "temperature": response.request.temperature,
            "tool_choice": "auto",
            "tools": [],
            "top_p": response.request.top_p,
            "truncation": "disabled",
            "user": None,
            "output": [],
            "output_text": "",
            "usage": None,
            "metadata": _stream_metadata(response, normalization_receipt=normalization_receipt),
        }
        if responses_store is not None:
            created_response["store"] = bool(responses_store)
            created_response["metadata"] = _responses_continuation_metadata(
                created_response["metadata"],
                stored=responses_store,
            )
        events = [
            (
                "response.created",
                {
                    "type": "response.created",
                    "response": created_response,
                },
            ),
            (
                "response.in_progress",
                {
                    "type": "response.in_progress",
                    "response": created_response,
                },
            ),
        ]
        output_index = 0
        if public_text or not tool_calls:
            text_item = {
                "type": "message",
                "id": message_item_id,
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            }
            text_part = {
                "type": "output_text",
                "annotations": [],
                "text": "",
            }
            events.extend(
                [
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "output_index": output_index,
                            "item": text_item,
                        },
                    ),
                    (
                        "response.content_part.added",
                        {
                            "type": "response.content_part.added",
                            "item_id": message_item_id,
                            "output_index": output_index,
                            "content_index": 0,
                            "part": text_part,
                        },
                    ),
                    (
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": message_item_id,
                            "output_index": output_index,
                            "content_index": 0,
                            "logprobs": [],
                            "delta": public_text,
                        },
                    ),
                    (
                        "response.output_text.done",
                        {
                            "type": "response.output_text.done",
                            "item_id": message_item_id,
                            "output_index": output_index,
                            "content_index": 0,
                            "logprobs": [],
                            "text": public_text,
                        },
                    ),
                    (
                        "response.content_part.done",
                        {
                            "type": "response.content_part.done",
                            "item_id": message_item_id,
                            "output_index": output_index,
                            "content_index": 0,
                            "part": {**text_part, "text": public_text},
                        },
                    ),
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": output_index,
                            "item": {
                                **text_item,
                                "status": "completed",
                                "content": [{**text_part, "text": public_text}],
                            },
                        },
                    ),
                ]
            )
            output_index += 1
        for call in tool_calls:
            call_item = tool_call_to_responses(call)
            arguments = str(call_item.get("arguments") or "{}")
            call_item_in_progress = {
                **call_item,
                "status": "in_progress",
                "arguments": "",
            }
            item_id = str(call_item.get("id") or "")
            events.extend(
                [
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "output_index": output_index,
                            "item": call_item_in_progress,
                        },
                    ),
                    (
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "item_id": item_id,
                            "call_id": str(call_item.get("call_id") or item_id),
                            "output_index": output_index,
                            "delta": arguments,
                        },
                    ),
                    (
                        "response.function_call_arguments.done",
                        {
                            "type": "response.function_call_arguments.done",
                            "item_id": item_id,
                            "call_id": str(call_item.get("call_id") or item_id),
                            "output_index": output_index,
                            "name": str(call_item.get("name") or ""),
                            "arguments": arguments,
                        },
                    ),
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": output_index,
                            "item": call_item,
                        },
                    ),
                ]
            )
            output_index += 1
        events.extend(
            [
                (
                    "response.completed",
                    {
                        "type": "response.completed",
                        "response": render_response(
                            response,
                            api_format="responses",
                            responses_store=responses_store,
                        ),
                    },
                ),
            ]
        )
        return _sse_bytes(_with_response_sequence_numbers(events, response_id=response.response_id))
    if normalized == "anthropic":
        usage = _public_usage(response, public_text)
        events = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": response.response_id,
                        "type": "message",
                        "role": "assistant",
                        "model": response.request.public_model,
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {
                            "input_tokens": usage["prompt_tokens"],
                            "output_tokens": 0,
                        },
                        "metadata": _stream_metadata(response, normalization_receipt=normalization_receipt),
                    },
                },
            ),
        ]
        index = 0
        if public_text or not tool_calls:
            events.extend(
                [
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": {"type": "text", "text": ""},
                        },
                    ),
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": public_text},
                        },
                    ),
                    (
                        "content_block_stop",
                        {"type": "content_block_stop", "index": index},
                    ),
                ]
            )
            index += 1
        for call in tool_calls:
            rendered_call = tool_call_to_anthropic(call)
            tool_input = rendered_call.get("input") if isinstance(rendered_call.get("input"), Mapping) else {}
            started_call = {**rendered_call, "input": {}}
            events.extend(
                [
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": started_call,
                        },
                    ),
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(
                                    tool_input,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                        },
                    ),
                    (
                        "content_block_stop",
                        {"type": "content_block_stop", "index": index},
                    ),
                ]
            )
            index += 1
        events.extend(
            [
                (
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {
                            "stop_reason": "tool_use" if tool_calls else "end_turn",
                            "stop_sequence": None,
                        },
                        "usage": {"output_tokens": usage["completion_tokens"]},
                    },
                ),
                ("message_stop", {"type": "message_stop"}),
            ]
        )
        return _sse_bytes(events)
    if normalized == "gemini":
        usage = _public_usage(response, public_text)
        events = [
            (
                None,
                {
                    "responseId": response.response_id,
                    "modelVersion": response.request.public_model,
                    "candidates": [
                        {
                            "index": 0,
                            "content": {
                                "role": "model",
                                "parts": [
                                    *([{"text": public_text}] if public_text else []),
                                    *(tool_call_to_gemini_part(call) for call in tool_calls),
                                ],
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": usage["prompt_tokens"],
                        "candidatesTokenCount": usage["completion_tokens"],
                        "totalTokenCount": usage["total_tokens"],
                    },
                    "metadata": _stream_metadata(response, normalization_receipt=normalization_receipt),
                },
            )
        ]
        return _sse_bytes(events)
    events: list[tuple[str | None, Mapping[str, Any] | str]] = [
        (
            None,
            {
                "id": response.response_id,
                "object": "chat.completion.chunk",
                "created": response.created,
                "model": response.request.public_model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                "metadata": _stream_metadata(response, normalization_receipt=normalization_receipt),
            },
        )
    ]
    if public_text:
        events.append(
            (
                None,
                {
                    "id": response.response_id,
                    "object": "chat.completion.chunk",
                    "created": response.created,
                    "model": response.request.public_model,
                    "choices": [{"index": 0, "delta": {"content": public_text}, "finish_reason": None}],
                },
            )
        )
    if tool_calls:
        for index, call in enumerate(tool_calls):
            rendered_call = tool_call_to_chat(call)
            events.extend(
                [
                    (
                        None,
                        {
                            "id": response.response_id,
                            "object": "chat.completion.chunk",
                            "created": response.created,
                            "model": response.request.public_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": index,
                                                "id": rendered_call["id"],
                                                "type": "function",
                                                "function": {
                                                    "name": rendered_call["function"]["name"],
                                                    "arguments": "",
                                                },
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        },
                    ),
                    (
                        None,
                        {
                            "id": response.response_id,
                            "object": "chat.completion.chunk",
                            "created": response.created,
                            "model": response.request.public_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": index,
                                                "function": {
                                                    "arguments": rendered_call["function"]["arguments"],
                                                },
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        },
                    ),
                ]
            )
    events.append(
        (
            None,
            {
                "id": response.response_id,
                "object": "chat.completion.chunk",
                "created": response.created,
                "model": response.request.public_model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if tool_calls else "stop"}],
            },
        )
    )
    if include_usage:
        events.append(
            (
                None,
                {
                    "id": response.response_id,
                    "object": "chat.completion.chunk",
                    "created": response.created,
                    "model": response.request.public_model,
                    "choices": [],
                    "usage": _public_usage(response, public_text),
                },
            )
        )
    events.append((None, "[DONE]"))
    return _sse_bytes(events)


def normalize_api_format(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"responses", "response"}:
        return "responses"
    if normalized in {"anthropic", "messages", "anthropic/messages"}:
        return "anthropic"
    if normalized in {
        "gemini",
        "google",
        "generatecontent",
        "generate_content",
        "gemini/generatecontent",
        "gemini/generate_content",
        "gemini/generate-content",
        "google/generatecontent",
        "google/generate_content",
        "google/generate-content",
        "google/generativeai",
    }:
        return "gemini"
    return "chat/completions"


def _is_openrouter_fusion_alias(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"openrouter/fusion", "openrouter:fusion"}


def _tools_from_payload(payload: Mapping[str, Any], *, api_format: str) -> tuple[Mapping[str, Any], ...]:
    rows = list(normalize_tool_definitions(payload, api_format=api_format))
    raw_tools = payload.get("tools") if isinstance(payload.get("tools"), Sequence) and not isinstance(payload.get("tools"), (str, bytes)) else ()
    rows.extend(dict(item) for item in raw_tools if isinstance(item, Mapping) and _is_fusion_plugin(item))
    rows.extend(_plugin_tools_from_payload(payload))
    return tuple(rows)


def _plugin_tools_from_payload(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    plugins = (
        payload.get("plugins")
        if isinstance(payload.get("plugins"), Sequence) and not isinstance(payload.get("plugins"), (str, bytes))
        else ()
    )
    result: list[Mapping[str, Any]] = []
    for plugin in plugins:
        if not isinstance(plugin, Mapping) or not _is_fusion_plugin(plugin):
            continue
        config = _plugin_config(plugin)
        result.append(
            {
                "type": "openrouter:fusion",
                "name": "openrouter:fusion",
                "parameters": config,
                "_axio_source": "plugin",
            }
        )
    return result


def _is_fusion_plugin(plugin: Mapping[str, Any]) -> bool:
    plugin_id = str(plugin.get("id") or plugin.get("type") or plugin.get("name") or "").strip().lower()
    if plugin_id in {"fusion", "openrouter:fusion", "openrouter/fusion", "axio_fusion", "axio-fusion"}:
        return True
    return False


def _plugin_config(plugin: Mapping[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for key in ("parameters", "config", "fusion"):
        value = plugin.get(key)
        if isinstance(value, Mapping):
            config.update(dict(value))
    for key in (
        "analysis_models",
        "analysisModels",
        "models",
        "model",
        "synthesis_model",
        "synthesisModel",
        "preset",
        "enabled",
    ):
        if key in plugin:
            config[key] = plugin[key]
    if "models" in config and "analysis_models" not in config and "analysisModels" not in config:
        config["analysis_models"] = config["models"]
    return config


def _stream_metadata(
    response: FusionResponse,
    *,
    normalization_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _, derived_receipt = _public_text_and_normalization(response)
    return {
        "schema": "axio_fusion_api.stream_metadata.v1",
        "external_model_name": response.request.public_model,
        "provider_calls_recorded": response.provider_calls_recorded,
        "request_fingerprint": response.request.request_fingerprint,
        "output_text_normalization": dict(normalization_receipt or derived_receipt),
        "raw_prompt_persisted": False,
        "raw_source_text_persisted": False,
        "secrets_persisted": False,
    }


def _response_metadata(
    response: FusionResponse,
    *,
    normalization_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _, derived_receipt = _public_text_and_normalization(response)
    return {
        "schema": "axio_fusion_api.response_metadata.v1",
        "external_model_name": response.request.public_model,
        "route_summary": public_route_summary(response.route_plan),
        "judge_summary": _public_judge_summary(response.judge_result),
        "fusion_trace_summary": _public_trace_summary(response.trace),
        "provider_calls_recorded": response.provider_calls_recorded,
        "request_fingerprint": response.request.request_fingerprint,
        "output_text_normalization": dict(normalization_receipt or derived_receipt),
        "internal_details_redacted": True,
        "provider_identifiers_redacted": True,
        "raw_prompt_persisted": False,
        "raw_source_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_profile_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _responses_continuation_metadata(metadata: Mapping[str, Any], *, stored: bool) -> dict[str, Any]:
    """Expose only the lifecycle of a Responses continuation, never its data."""

    return {
        **dict(metadata),
        "response_continuation": {
            "available": bool(stored),
            "storage_scope": "process_memory",
            "durable": False,
            "raw_session_ids_persisted": False,
            "raw_response_context_persisted": False,
            "raw_tool_outputs_persisted": False,
        },
    }


def public_route_summary(route_plan: Mapping[str, Any]) -> dict[str, Any]:
    selected = route_plan.get("selected_models") if isinstance(route_plan.get("selected_models"), list) else []
    roles = route_plan.get("roles") if isinstance(route_plan.get("roles"), list) else []
    budget = route_plan.get("budget") if isinstance(route_plan.get("budget"), Mapping) else {}
    guards = route_plan.get("runtime_guards") if isinstance(route_plan.get("runtime_guards"), Mapping) else {}
    admission = route_plan.get("fusion_admission") if isinstance(route_plan.get("fusion_admission"), Mapping) else {}
    initial_call_plan = admission.get("initial_fusion_call_plan") if isinstance(admission.get("initial_fusion_call_plan"), Mapping) else {}
    initial_resource_admission = (
        admission.get("initial_fusion_resource_admission")
        if isinstance(admission.get("initial_fusion_resource_admission"), Mapping)
        else budget.get("initial_fusion_resource_admission")
        if isinstance(budget.get("initial_fusion_resource_admission"), Mapping)
        else {}
    )
    judge_contract = route_plan.get("judge_contract") if isinstance(route_plan.get("judge_contract"), Mapping) else {}
    task_dag = route_plan.get("task_dag") if isinstance(route_plan.get("task_dag"), Mapping) else {}
    finalization_mode = str(
        guards.get("fusion_finalization_mode")
        or budget.get("fusion_finalization_mode")
        or admission.get("fusion_finalization_mode")
        or judge_contract.get("finalization_mode")
        or "direct"
    )[:80]
    local_plan = (
        budget.get("local_consensus_plan")
        if isinstance(budget.get("local_consensus_plan"), Mapping)
        else admission.get("local_consensus_plan")
        if isinstance(admission.get("local_consensus_plan"), Mapping)
        else {}
    )
    stage_profile_reuse = _stage_profile_reuse_from_roles(roles)
    circuit_filter = (
        route_plan.get("runtime_circuit_filter")
        if isinstance(route_plan.get("runtime_circuit_filter"), Mapping)
        else {}
    )
    runtime_telemetry = (
        circuit_filter.get("runtime_provider_telemetry")
        if isinstance(circuit_filter.get("runtime_provider_telemetry"), Mapping)
        else {}
    )
    return {
        "schema": "axio_fusion_api.public_route_summary.v1",
        "public_model": str(route_plan.get("public_model") or ""),
        "strategy": str(route_plan.get("strategy") or ""),
        "selected_model_count": len(selected),
        "selected_profile_hashes": [
            sha256_text(str(row.get("profile_id") or ""))
            for row in selected[:24]
            if isinstance(row, Mapping) and row.get("profile_id")
        ],
        "role_count": len(roles),
        "stage_profile_reuse": _public_stage_profile_reuse(stage_profile_reuse),
        "fusion_activated": bool(judge_contract.get("required")),
        "fusion_finalization_mode": finalization_mode,
        "local_consensus_enabled": finalization_mode == "local_consensus",
        "provider_stage_calls_reserved": bool(
            guards.get("provider_stage_calls_reserved")
            if "provider_stage_calls_reserved" in guards
            else finalization_mode == "provider_judge_synthesis"
        ),
        "local_consensus_panel_size": _optional_int(
            local_plan.get("panel_size")
        ),
        "local_consensus_panel_profile_hashes": [
            str(item)
            for item in local_plan.get("panel_profile_hashes", [])
            if str(item)
        ][:24]
        if isinstance(local_plan.get("panel_profile_hashes"), list)
        else [],
        "local_consensus_panel_provider_hashes": [
            str(item)
            for item in local_plan.get("panel_provider_hashes", [])
            if str(item)
        ][:24]
        if isinstance(local_plan.get("panel_provider_hashes"), list)
        else [],
        "task_dag_node_count": _optional_int(task_dag.get("node_count")),
        "task_dag_checkpoint_count": _optional_int(task_dag.get("checkpoint_count")),
        "max_total_model_calls": _optional_int(guards.get("max_total_model_calls") or budget.get("max_total_model_calls")),
        "initial_fusion_minimum_call_count": _optional_int(
            guards.get("initial_fusion_minimum_call_count") or budget.get("initial_fusion_minimum_call_count")
        ),
        "initial_fusion_planned_call_count": _optional_int(
            guards.get("initial_fusion_planned_call_count") or budget.get("initial_fusion_planned_call_count")
        ),
        "initial_fusion_call_budget_sufficient": bool(
            guards.get("initial_fusion_call_budget_sufficient")
            if "initial_fusion_call_budget_sufficient" in guards
            else initial_call_plan.get("complete_fusion_feasible")
        ),
        "initial_fusion_role_budget_constrained": bool(
            guards.get("initial_fusion_role_budget_constrained")
            if "initial_fusion_role_budget_constrained" in guards
            else initial_call_plan.get("role_budget_constrained")
        ),
        "initial_fusion_resource_budget_checked": bool(
            guards.get("initial_fusion_resource_budget_checked")
            if "initial_fusion_resource_budget_checked" in guards
            else budget.get("initial_fusion_resource_budget_checked")
        ),
        "initial_fusion_resource_budget_applicable": bool(
            guards.get("initial_fusion_resource_budget_applicable")
            if "initial_fusion_resource_budget_applicable" in guards
            else initial_resource_admission.get("applicable")
        ),
        "initial_fusion_resource_budget_blocked": bool(
            guards.get("initial_fusion_resource_budget_blocked")
            if "initial_fusion_resource_budget_blocked" in guards
            else initial_resource_admission.get("blocked")
        ),
        "initial_fusion_resource_admission": _public_initial_fusion_resource_admission(
            initial_resource_admission
        ),
        "mandatory_fusion_stage_call_reservation_enabled": bool(
            guards.get("mandatory_fusion_stage_call_reservation_enabled")
        ),
        "mandatory_fusion_stage_reservation_roles": [
            str(role)[:80]
            for role in guards.get("mandatory_fusion_stage_reservation_roles", [])
            if str(role)
        ][:4] if isinstance(guards.get("mandatory_fusion_stage_reservation_roles"), list) else [],
        "max_cost_usd": _optional_float(guards.get("max_cost_usd") or budget.get("max_cost_usd")),
        "max_latency_ms": _optional_int(guards.get("max_latency_ms") or budget.get("max_latency_ms")),
        "quality_target": _optional_float(guards.get("quality_target") or budget.get("quality_target")),
        "provider_fallback_enabled": bool(guards.get("provider_fallback_enabled")),
        "candidate_deduplication_enabled": bool(guards.get("candidate_deduplication_enabled")),
        "runtime_provider_telemetry": _public_runtime_provider_telemetry(runtime_telemetry),
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_profile_ids_persisted": False,
    }


def _stage_profile_reuse_from_roles(roles: Sequence[Any]) -> Mapping[str, Any]:
    for row in roles:
        if not isinstance(row, Mapping):
            continue
        value = row.get("stage_profile_reuse")
        if isinstance(value, Mapping):
            return value
    return {}


def _public_stage_profile_reuse(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.public_stage_profile_reuse.v1",
        "expert_profile_count": _bounded_nonnegative_int(value.get("expert_profile_count")),
        "unassigned_profile_count": _bounded_nonnegative_int(value.get("unassigned_profile_count")),
        "eligible_unassigned_judge_profile_count": _bounded_nonnegative_int(
            value.get("eligible_unassigned_judge_profile_count")
        ),
        "eligible_unassigned_synthesizer_profile_count": _bounded_nonnegative_int(
            value.get("eligible_unassigned_synthesizer_profile_count")
        ),
        "rejected_unassigned_profile_count": _bounded_nonnegative_int(
            value.get("rejected_unassigned_profile_count")
        ),
        "judge_reuses_expert_profile": value.get("judge_reuses_expert_profile") is True,
        "synthesizer_reuses_expert_profile": value.get("synthesizer_reuses_expert_profile") is True,
        "judge_and_synthesizer_share_profile": value.get("judge_and_synthesizer_share_profile") is True,
        "independent_stage_selection_enabled": value.get("independent_stage_selection_enabled") is True,
        "reuse_is_capacity_fallback": value.get("reuse_is_capacity_fallback") is True,
        "selection_policy": str(value.get("selection_policy") or "")[:120],
        "expert_latency_optimization": _public_latency_optimization(
            value.get("expert_latency_optimization")
            if isinstance(value.get("expert_latency_optimization"), Mapping)
            else {}
        ),
        "latency_optimization": _public_latency_optimization(
            value.get("latency_optimization")
            if isinstance(value.get("latency_optimization"), Mapping)
            else {}
        ),
        "raw_profile_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_model_names_persisted": False,
    }


def _public_latency_optimization(value: Mapping[str, Any]) -> dict[str, Any]:
    schema = str(value.get("schema") or "")
    allowed_schemas = {
        "axio_fusion_api.expert_latency_optimization.v1",
        "axio_fusion_api.stage_latency_optimization.v1",
    }
    return {
        "schema": schema if schema in allowed_schemas else "axio_fusion_api.latency_optimization.v1",
        "enabled": value.get("enabled") is True,
        "applied": value.get("applied") is True,
        "reason": str(value.get("reason") or "")[:120],
        "direct_profile_latency_ms": _optional_float(value.get("direct_profile_latency_ms")),
        "original_expert_phase_latency_ms": _optional_float(value.get("original_expert_phase_latency_ms")),
        "optimized_expert_phase_latency_ms": _optional_float(value.get("optimized_expert_phase_latency_ms")),
        "original_estimated_latency_ms": _optional_float(value.get("original_estimated_latency_ms")),
        "optimized_estimated_latency_ms": _optional_float(value.get("optimized_estimated_latency_ms")),
        "original_latency_multiplier_vs_direct": _optional_float(value.get("original_latency_multiplier_vs_direct")),
        "optimized_latency_multiplier_vs_direct": _optional_float(value.get("optimized_latency_multiplier_vs_direct")),
        "target_latency_multiplier": _optional_float(value.get("target_latency_multiplier")),
        "operational_target_multiplier": _optional_float(value.get("operational_target_multiplier")),
        "replaced_role_count": _bounded_nonnegative_int(value.get("replaced_role_count")),
        "raw_profile_ids_persisted": False,
        "raw_model_names_persisted": False,
    }


def _public_runtime_provider_telemetry(value: Mapping[str, Any]) -> dict[str, Any]:
    profiles = value.get("profiles") if isinstance(value.get("profiles"), list) else []
    safe_profiles = []
    for row in profiles[:128]:
        if not isinstance(row, Mapping):
            continue
        profile_hash = _sha256_or_empty(row.get("profile_id_sha256"))
        provider_hash = _sha256_or_empty(row.get("provider_sha256"))
        if not profile_hash or not provider_hash:
            continue
        health = str(row.get("effective_health") or "unknown")
        if health not in {"unknown", "observed", "available", "degraded", "unavailable"}:
            health = "unknown"
        safe_profiles.append(
            {
                "profile_id_sha256": profile_hash,
                "provider_sha256": provider_hash,
                "observation_count": _bounded_nonnegative_int(row.get("observation_count")),
                "success_count": _bounded_nonnegative_int(row.get("success_count")),
                "failure_count": _bounded_nonnegative_int(row.get("failure_count")),
                "latency_sample_count": _bounded_nonnegative_int(row.get("latency_sample_count")),
                "observed_success_rate": _bounded_unit_float(row.get("observed_success_rate")),
                "effective_availability": _bounded_unit_float(row.get("effective_availability")),
                "effective_recent_success_rate": _bounded_unit_float(row.get("effective_recent_success_rate")),
                "effective_p50_latency_ms": _bounded_nonnegative_int(row.get("effective_p50_latency_ms")),
                "effective_p95_latency_ms": _bounded_nonnegative_int(row.get("effective_p95_latency_ms")),
                "effective_health": health,
                "calibration_applied": row.get("calibration_applied") is True,
                "latency_calibration_applied": row.get("latency_calibration_applied") is True,
                "raw_profile_id_persisted": False,
                "raw_provider_name_persisted": False,
                "raw_model_name_persisted": False,
            }
        )
    safe_profiles.sort(key=lambda row: row["profile_id_sha256"])
    return {
        "schema": "axio_fusion_api.public_runtime_provider_telemetry.v1",
        "enabled": value.get("enabled") is True,
        "minimum_observation_count": _bounded_nonnegative_int(value.get("minimum_observation_count")),
        "latency_sample_limit_per_profile": _bounded_nonnegative_int(value.get("latency_sample_limit_per_profile")),
        "observed_profile_count": _bounded_nonnegative_int(value.get("observed_profile_count")),
        "observed_provider_hash_count": _bounded_nonnegative_int(value.get("observed_provider_hash_count")),
        "adapted_profile_count": _bounded_nonnegative_int(value.get("adapted_profile_count")),
        "profiles": safe_profiles,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
        "raw_model_name_persisted": False,
        "raw_provider_output_persisted": False,
        "secrets_persisted": False,
    }


def _sha256_or_empty(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if len(text) == 64 and all(char in "0123456789abcdef" for char in text) else ""


def _bounded_nonnegative_int(value: Any) -> int:
    return max(0, min(1_000_000, _optional_int(value) or 0))


def _bounded_unit_float(value: Any) -> float | None:
    parsed = _optional_float(value)
    return None if parsed is None else max(0.0, min(1.0, parsed))


def _public_initial_fusion_resource_admission(value: Mapping[str, Any]) -> dict[str, Any]:
    cost = value.get("cost") if isinstance(value.get("cost"), Mapping) else {}
    latency = value.get("latency") if isinstance(value.get("latency"), Mapping) else {}
    return {
        "schema": str(value.get("schema") or "axio_fusion_api.initial_fusion_resource_admission.v1")[:120],
        "applicable": bool(value.get("applicable")),
        "complete_initial_fusion_shape": bool(value.get("complete_initial_fusion_shape")),
        "planned_initial_role_count": _optional_int(value.get("planned_initial_role_count")),
        "planned_initial_profile_count": _optional_int(value.get("planned_initial_profile_count")),
        "cost": {
            "known": bool(cost.get("known")),
            "estimated_total_cost_usd": _optional_float(cost.get("estimated_total_cost_usd")),
            "request_max_cost_usd": _optional_float(cost.get("request_max_cost_usd")),
            "within_request_budget": _optional_bool(cost.get("within_request_budget")),
            "blocked": bool(cost.get("blocked")),
        },
        "latency": {
            "known": bool(latency.get("known")),
            "estimated_total_latency_ms": _optional_float(latency.get("estimated_total_latency_ms")),
            "request_max_latency_ms": _optional_int(latency.get("request_max_latency_ms")),
            "within_request_deadline": _optional_bool(latency.get("within_request_deadline")),
            "blocked": bool(latency.get("blocked")),
        },
        "blocked": bool(value.get("blocked")),
        "blocked_reasons": [
            str(item)[:160]
            for item in value.get("blocked_reasons", [])
            if str(item)
        ][:8] if isinstance(value.get("blocked_reasons"), list) else [],
        "optional_repair_or_escalation_included": bool(
            value.get("optional_repair_or_escalation_included")
        ),
        "raw_profile_ids_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "secrets_persisted": False,
    }


def _public_judge_summary(judge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.public_judge_summary.v1",
        "ready_for_synthesis": judge.get("ready_for_synthesis") is True,
        "not_majority_vote": judge.get("not_majority_vote") is True,
        "judge_provider_call": judge.get("judge_provider_call") is True,
        "judge_provider_call_skipped": judge.get("judge_provider_call_skipped") is True,
        "judge_skip_reason": str(judge.get("judge_skip_reason") or "")[:120],
        "provider_judge_sanitized": judge.get("provider_judge_sanitized") is True,
        "consensus_count": len(judge.get("consensus", [])) if isinstance(judge.get("consensus"), list) else 0,
        "contradiction_count": len(judge.get("contradictions", [])) if isinstance(judge.get("contradictions"), list) else 0,
        "missing_coverage_count": len(judge.get("missing_coverage", [])) if isinstance(judge.get("missing_coverage"), list) else 0,
        "ranked_candidate_count": len(judge.get("ranked_candidates", [])) if isinstance(judge.get("ranked_candidates"), list) else 0,
        "raw_candidate_text_persisted": False,
        "raw_provider_outputs_persisted": False,
    }


def _public_trace_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    early_exit = trace.get("early_exit") if isinstance(trace.get("early_exit"), Mapping) else {}
    panel_repair = trace.get("panel_repair") if isinstance(trace.get("panel_repair"), Mapping) else {}
    synthesis_compression = trace.get("synthesis_compression") if isinstance(trace.get("synthesis_compression"), Mapping) else {}
    fusion_stage_outcome = (
        trace.get("runtime_fusion_stage_outcome")
        if isinstance(trace.get("runtime_fusion_stage_outcome"), Mapping)
        else {}
    )
    budget_lock = trace.get("budget_lock") if isinstance(trace.get("budget_lock"), Mapping) else {}
    cost_budget = trace.get("cost_budget") if isinstance(trace.get("cost_budget"), Mapping) else {}
    deadline_budget = trace.get("deadline_budget") if isinstance(trace.get("deadline_budget"), Mapping) else {}
    circuit_breakers = trace.get("circuit_breakers") if isinstance(trace.get("circuit_breakers"), Mapping) else {}
    candidate_receipts = trace.get("candidate_receipts") if isinstance(trace.get("candidate_receipts"), list) else []
    tool_call_arbitration = trace.get("tool_call_arbitration") if isinstance(trace.get("tool_call_arbitration"), Mapping) else {}
    cache_replay = trace.get("cache_replay") if isinstance(trace.get("cache_replay"), Mapping) else {}
    cache_origin = trace.get("cache_origin_completion") if isinstance(trace.get("cache_origin_completion"), Mapping) else {}
    return {
        "schema": "axio_fusion_api.public_trace_summary.v1",
        "actual_cost_usd": _optional_float(trace.get("actual_cost_usd")),
        "latency_ms": _optional_float(trace.get("latency_ms")),
        "provider_call_count": _optional_int(trace.get("provider_call_count")),
        "judge_provider_call_count": _optional_int(trace.get("judge_provider_call_count")),
        "synthesis_provider_call_count": _optional_int(trace.get("synthesis_provider_call_count")),
        "fusion_finalization_mode": str(
            fusion_stage_outcome.get("fusion_finalization_mode") or "direct"
        )[:80],
        "local_consensus_enabled": fusion_stage_outcome.get("local_consensus_enabled") is True,
        "local_consensus_finalized": fusion_stage_outcome.get("local_consensus_finalized") is True,
        "provider_judge_required": fusion_stage_outcome.get("provider_judge_required") is True,
        "provider_synthesizer_required": fusion_stage_outcome.get("provider_synthesizer_required") is True,
        "candidate_count": len(candidate_receipts),
        "cache_hit": bool(trace.get("cache_hit")),
        "cache_replay": cache_replay.get("replayed") is True,
        "cache_process_executed_this_request": cache_replay.get(
            "process_executed_this_request"
        ) is True,
        "cache_origin_eligible": cache_origin.get("cache_eligible") is True,
        "cache_origin_completion_kind": str(
            cache_origin.get("completion_kind") or ""
        )[:80],
        "cache_origin_fusion_requested": cache_origin.get("fusion_requested") is True,
        "cache_origin_complete_admitted_finalized": cache_origin.get(
            "complete_admitted_fusion_finalized"
        ) is True,
        "cache_origin_hermes_contract_required": cache_origin.get(
            "hermes_process_contract_required"
        ) is True,
        "cache_origin_hermes_contract_completed": cache_origin.get(
            "hermes_process_contract_completed"
        ) is True,
        "early_exit_triggered": early_exit.get("triggered") is True,
        "early_exit_reason": str(early_exit.get("reason") or "")[:120],
        "panel_repair_attempted": panel_repair.get("attempted") is True,
        "panel_repair_success": panel_repair.get("success") is True,
        "synthesis_compression_enabled": synthesis_compression.get("enabled") is True,
        "runtime_fusion_execution_mode": str(
            fusion_stage_outcome.get("execution_mode") or ""
        )[:120],
        "runtime_fusion_degraded": fusion_stage_outcome.get("runtime_degraded") is True,
        "runtime_fusion_degradation_reason": str(
            fusion_stage_outcome.get("degradation_reason") or ""
        )[:120],
        "runtime_fusion_complete_admitted_finalized": fusion_stage_outcome.get(
            "complete_admitted_fusion_finalized"
        ) is True,
        "budget_lock_skipped_call_count": _optional_int(budget_lock.get("skipped_call_count")) or 0,
        "mandatory_stage_reservation_enabled": budget_lock.get("mandatory_stage_reservation_enabled") is True,
        "mandatory_stage_reservation_skip_count": _optional_int(budget_lock.get("mandatory_stage_reservation_skip_count")) or 0,
        "cost_budget_skipped_call_count": _optional_int(cost_budget.get("skipped_call_count")) or 0,
        "deadline_budget_skipped_call_count": _optional_int(deadline_budget.get("skipped_call_count")) or 0,
        "mandatory_stage_deadline_reservation_enabled": deadline_budget.get(
            "mandatory_stage_deadline_reservation_enabled"
        ) is True,
        "mandatory_stage_deadline_pending_ms": _optional_int(
            deadline_budget.get("mandatory_stage_deadline_pending_ms")
        ) or 0,
        "mandatory_stage_deadline_consumed_ms": _optional_int(
            deadline_budget.get("mandatory_stage_deadline_consumed_ms")
        ) or 0,
        "mandatory_stage_deadline_reservation_skip_count": _optional_int(
            deadline_budget.get("mandatory_stage_deadline_reservation_skip_count")
        ) or 0,
        "open_circuit_profile_count": _optional_int(circuit_breakers.get("open_profile_count")) or 0,
        "tool_call_arbitration": _public_tool_call_arbitration(tool_call_arbitration),
        "raw_candidate_text_persisted": False,
        "raw_provider_names_persisted": False,
        "raw_provider_model_ids_persisted": False,
        "raw_profile_ids_persisted": False,
        "raw_provider_outputs_persisted": False,
    }


def _public_tool_call_arbitration(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed_reasons = {
        "no_declared_native_tool_plan",
        "all_completed_tool_candidates_agree",
        "independent_provider_tool_plan_consensus",
        "primary_solver_tool_plan_preferred_without_independent_consensus",
        "best_available_tool_plan_without_independent_consensus",
    }
    reason = str(value.get("selection_reason") or "")
    return {
        "schema": "axio_fusion_api.public_native_tool_call_arbitration.v1",
        "enabled": value.get("enabled") is True,
        "selected": value.get("selected") is True,
        "selection_reason": reason if reason in allowed_reasons else "",
        "candidate_with_native_tool_call_count": _bounded_nonnegative_int(
            value.get("candidate_with_native_tool_call_count")
        ),
        "eligible_candidate_plan_count": _bounded_nonnegative_int(
            value.get("eligible_candidate_plan_count")
        ),
        "unique_tool_plan_count": _bounded_nonnegative_int(value.get("unique_tool_plan_count")),
        "rejected_undeclared_tool_call_count": _bounded_nonnegative_int(
            value.get("rejected_undeclared_tool_call_count")
        ),
        "rejected_ineligible_role_tool_call_count": _bounded_nonnegative_int(
            value.get("rejected_ineligible_role_tool_call_count")
        ),
        "selected_tool_plan_sha256": _sha256_or_empty(value.get("selected_tool_plan_sha256")),
        "selected_role": str(value.get("selected_role") or "")[:80],
        "selected_profile_sha256": _sha256_or_empty(value.get("selected_profile_sha256")),
        "selected_provider_sha256": _sha256_or_empty(value.get("selected_provider_sha256")),
        "selected_tool_call_count": _bounded_nonnegative_int(value.get("selected_tool_call_count")),
        "raw_tool_names_persisted": False,
        "raw_tool_arguments_persisted": False,
        "raw_tool_plan_persisted": False,
        "raw_profile_id_persisted": False,
        "raw_provider_name_persisted": False,
    }


def _sse_bytes(events: Sequence[tuple[str | None, Mapping[str, Any] | str]]) -> bytes:
    lines = []
    for event_name, payload in events:
        if event_name:
            lines.append(f"event: {event_name}")
        if isinstance(payload, str):
            data = payload
        else:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        for line in data.splitlines() or [""]:
            lines.append(f"data: {line}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _with_response_sequence_numbers(
    events: Sequence[tuple[str | None, Mapping[str, Any] | str]],
    *,
    response_id: str = "",
) -> list[tuple[str | None, Mapping[str, Any] | str]]:
    """Attach the mandatory monotonic sequence to Responses stream events."""

    numbered: list[tuple[str | None, Mapping[str, Any] | str]] = []
    for sequence_number, (event_name, payload) in enumerate(events, start=1):
        if isinstance(payload, Mapping):
            payload = {
                **payload,
                **({"response_id": response_id} if response_id and "response_id" not in payload else {}),
                "sequence_number": sequence_number,
            }
        numbered.append((event_name, payload))
    return numbered


def _responses_usage_payload(usage: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "input_tokens": _optional_int(usage.get("prompt_tokens")) or 0,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": _optional_int(usage.get("completion_tokens")) or 0,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": _optional_int(usage.get("total_tokens")) or 0,
    }


def _messages_to_parts(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]], str, tuple[Mapping[str, Any], ...]]:
    system_parts: list[str] = []
    conversational: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip()
        content = str(message.get("content") or "").strip()
        raw_parts = message.get("content_parts")
        parts = tuple(
            dict(item)
            for item in raw_parts
            if isinstance(item, Mapping)
        ) if isinstance(raw_parts, Sequence) and not isinstance(raw_parts, (str, bytes)) else ()
        if not content and not parts:
            continue
        if role in {"system", "developer"}:
            if has_non_text_content(parts):
                raise ContentContractError(
                    "system_content_not_supported",
                    "system content must contain text only",
                )
            system_parts.append(content)
        elif role in {"user", "assistant"}:
            row: dict[str, Any] = {"role": role, "content": content}
            if parts and has_non_text_content(parts):
                row["content_parts"] = list(parts)
            conversational.append(row)
    last_user = -1
    for index, message in enumerate(conversational):
        if message["role"] == "user":
            last_user = index
    if last_user < 0:
        return "\n".join(system_parts), conversational, "", ()
    current = conversational[last_user]
    current_parts = tuple(
        dict(item)
        for item in current.get("content_parts", ())
        if isinstance(item, Mapping)
    )
    if not current_parts and current.get("content"):
        current_parts = normalize_content_parts(current["content"], source_format="chat")
    return "\n".join(system_parts), conversational[:last_user], current["content"], current_parts


def _request_history_with_protocol_events(
    text_history: Sequence[Mapping[str, str]],
    history_events: Sequence[Mapping[str, Any]],
    *,
    prompt: str,
) -> list[dict[str, Any]]:
    """Prefer rich protocol events while avoiding a duplicate current prompt."""

    rich_events = [dict(item) for item in history_events if isinstance(item, Mapping)]
    if rich_events:
        return rich_events
    return [dict(item) for item in text_history if isinstance(item, Mapping)]


def _current_prompt_is_in_history(
    history_events: Sequence[Mapping[str, Any]],
    *,
    prompt: str,
    content_parts: Sequence[Mapping[str, Any]] = (),
) -> bool:
    if not prompt and not content_parts:
        return False
    last_user_index = max(
        (index for index, item in enumerate(history_events) if str(item.get("role") or "") == "user"),
        default=-1,
    )
    if last_user_index < 0:
        return False
    current = history_events[last_user_index]
    if prompt and str(current.get("content") or "") == prompt:
        return True
    event_parts = current.get("content_parts")
    return bool(
        content_parts
        and isinstance(event_parts, Sequence)
        and not isinstance(event_parts, (str, bytes))
        and stable_json(list(event_parts)) == stable_json(list(content_parts))
    )


def _message_rows(
    value: Any,
    *,
    source_format: str = "chat",
) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "user")
        parts = normalize_content_parts(item.get("content"), source_format=source_format)
        content = content_text(parts)
        if content or parts:
            row: dict[str, Any] = {"role": role, "content": content}
            if has_non_text_content(parts):
                row["content_parts"] = parts
            rows.append(row)
    return rows


def _responses_input_to_messages(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        item_type = str(item.get("type") or "").strip().casefold()
        if item_type in {"input_text", "input_image", "input_file"}:
            parts = normalize_content_parts([item], source_format="responses")
            if parts:
                rows.append({"role": "user", "content": content_text(parts), "content_parts": parts})
            continue
        if item_type in {"function_call", "function_call_output"}:
            continue
        content = item.get("content") if "content" in item else item.get("input")
        parts = normalize_content_parts(content, source_format="responses")
        text = content_text(parts)
        if text or parts:
            row: dict[str, Any] = {"role": str(item.get("role") or "user"), "content": text}
            if has_non_text_content(parts):
                row["content_parts"] = parts
            rows.append(row)
    return rows


def _responses_instructions_to_text(value: Any) -> str:
    """Normalize Responses instructions without stringifying typed messages.

    The Responses API accepts either a string or an array of instruction
    messages/content parts.  Axio's common system contract is text-only, so
    typed image/file instructions are rejected instead of being flattened or
    silently discarded.
    """

    if value in (None, ""):
        return ""
    if isinstance(value, Mapping):
        if "content" in value:
            value = value.get("content")
        elif "input" in value:
            value = value.get("input")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        text_parts: list[Mapping[str, Any]] = []
        for item in value:
            candidate = item
            if isinstance(item, Mapping) and ("content" in item or "input" in item):
                candidate = item.get("content") if "content" in item else item.get("input")
            parts = normalize_content_parts(candidate, source_format="responses")
            if has_non_text_content(parts):
                raise ContentContractError(
                    "system_content_not_supported",
                    "Responses instructions must contain text only",
                )
            text_parts.extend(parts)
        return content_text(text_parts)
    return _text_only_content(value, source_format="responses")


def _gemini_contents_to_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "user")
        if role == "model":
            role = "assistant"
        parts = normalize_content_parts(item.get("parts") or item.get("content"), source_format="gemini")
        content = content_text(parts)
        if content or parts:
            row: dict[str, Any] = {"role": role, "content": content}
            if has_non_text_content(parts):
                row["content_parts"] = parts
            rows.append(row)
    return rows


def _content_to_text(value: Any, *, source_format: str = "chat") -> str:
    return content_text(normalize_content_parts(value, source_format=source_format))


def _text_only_content(value: Any, *, source_format: str) -> str:
    parts = normalize_content_parts(value, source_format=source_format)
    if has_non_text_content(parts):
        raise ContentContractError(
            "system_content_not_supported",
            "system content must contain text only",
        )
    return content_text(parts)


def _gemini_system_to_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text_only_content(
            value.get("parts") or value.get("content"),
            source_format="gemini",
        )
    return _text_only_content(value, source_format="gemini")


def _generation_config(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return payload.get("generationConfig") if isinstance(payload.get("generationConfig"), Mapping) else {}


def _max_output_tokens(payload: Mapping[str, Any], api_format: str) -> int | None:
    config = _generation_config(payload)
    value = (
        payload.get("max_output_tokens")
        or payload.get("max_completion_tokens")
        or payload.get("max_tokens")
        or config.get("maxOutputTokens")
    )
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _stop_sequences(payload: Mapping[str, Any], api_format: str) -> tuple[str, ...]:
    config = _generation_config(payload)
    value = payload.get("stop_sequences") if api_format == "anthropic" else payload.get("stop")
    if value in (None, ""):
        value = config.get("stopSequences")
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _policy_from_payload(payload: Mapping[str, Any]) -> FusionPolicy:
    return FusionPolicy(
        max_cost_usd=_optional_float(payload.get("max_cost_usd")),
        max_latency_ms=_optional_int(payload.get("max_latency_ms")),
        quality_target=_optional_float(payload.get("quality_target")),
        max_models=_optional_int(payload.get("max_models")),
        max_depth=_optional_int(payload.get("max_depth")),
        max_total_model_calls=_optional_int(payload.get("max_total_model_calls")),
        fusion_depth=_optional_int(payload.get("fusion_depth")) or 0,
        max_fusion_depth=_optional_int(payload.get("max_fusion_depth")) or 2,
        live=bool(payload.get("live") or payload.get("axio_live")),
    )


def _model_from_gemini_payload(payload: Mapping[str, Any]) -> str:
    return str(payload.get("model") or "")


def _optional_float(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
