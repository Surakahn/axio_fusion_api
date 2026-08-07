from __future__ import annotations

import json

import pytest

from axio_fusion_api.compat import canonicalize_payload
from axio_fusion_api.content_contract import (
    ContentContractError,
    render_content_parts,
)
from axio_fusion_api.providers import (
    _anthropic_payload,
    _chat_payload,
    _gemini_payload,
    _responses_text_fallback_preserves_turn,
    _responses_typed_payload,
)
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.router import build_route_plan
from axio_fusion_api.schemas import FusionRequest
from axio_fusion_api.server import (
    _prepare_incremental_stream_request,
    handle_request,
)


IMAGE_URL = "https://example.com/reference.png"
IMAGE_DATA = "aGVsbG8="


def _profile(api_format: str, *, supports_vision: bool = True):
    return normalize_profile(
        {
            "provider": f"fixture-{api_format}",
            "model": f"fixture-{api_format}-model",
            "api_format": api_format,
            "supports_vision": supports_vision,
            "capabilities": {
                "daily_work": 0.95,
                "science_knowledge": 0.90,
                "structured_output": 0.95,
                "critique": 0.90,
            },
        }
    )


def _image_request() -> FusionRequest:
    return FusionRequest(
        model="axio-pro",
        prompt="Inspect the image and summarize it.",
        content_parts=(
            {"type": "text", "text": "Inspect the image and summarize it."},
            {"type": "image", "source": "url", "url": IMAGE_URL, "detail": "high"},
        ),
    )


@pytest.mark.parametrize(
    ("api_format", "payload"),
    [
        (
            "chat/completions",
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Inspect"},
                            {
                                "type": "image_url",
                                "image_url": {"url": IMAGE_URL, "detail": "high"},
                            },
                        ],
                    }
                ]
            },
        ),
        (
            "responses",
            {
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Inspect"},
                            {"type": "input_image", "image_url": IMAGE_URL},
                        ],
                    }
                ]
            },
        ),
        (
            "anthropic",
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Inspect"},
                            {
                                "type": "image",
                                "source": {"type": "url", "url": IMAGE_URL},
                            },
                        ],
                    }
                ]
            },
        ),
        (
            "gemini",
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": "Inspect"},
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": IMAGE_DATA,
                                }
                            },
                        ],
                    }
                ]
            },
        ),
    ],
)
def test_each_public_protocol_preserves_image_content_parts(api_format, payload):
    request = canonicalize_payload(payload, api_format=api_format)

    assert request.has_visual_input is True
    assert [part["type"] for part in request.content_parts] == ["text", "image"]
    assert request.prompt == "Inspect\n[image input]"
    safe = request.prompt_free_dict()
    serialized = json.dumps(safe, ensure_ascii=False)
    assert IMAGE_URL not in serialized
    assert IMAGE_DATA not in serialized
    assert safe["content_parts"]["raw_urls_persisted"] is False
    assert safe["content_parts"]["raw_image_data_persisted"] is False


@pytest.mark.parametrize("api_format", ["chat", "responses", "anthropic", "gemini"])
def test_provider_renderers_reconstruct_the_closed_image_contract(api_format):
    request = _image_request()
    profile = _profile(api_format)

    if api_format == "chat":
        payload = _chat_payload(profile, request, prompt=request.prompt, system="system")
        content = payload["messages"][-1]["content"]
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == IMAGE_URL
    elif api_format == "responses":
        payload = _responses_typed_payload(profile, request, prompt=request.prompt, system="system")
        content = payload["input"][-1]["content"]
        assert content[1] == {
            "type": "input_image",
            "image_url": IMAGE_URL,
            "detail": "high",
        }
    elif api_format == "anthropic":
        payload = _anthropic_payload(profile, request, prompt=request.prompt, system="system")
        content = payload["messages"][-1]["content"]
        assert content[1] == {"type": "image", "source": {"type": "url", "url": IMAGE_URL}}
    else:
        payload = _gemini_payload(profile, request, prompt=request.prompt, system="system")
        content = payload["contents"][-1]["parts"]
        assert content[1] == {"fileData": {"fileUri": IMAGE_URL}}


def test_base64_image_renders_for_all_image_capable_provider_protocols():
    request = FusionRequest(
        model="axio-pro",
        prompt="Inspect",
        content_parts=(
            {"type": "text", "text": "Inspect"},
            {
                "type": "image",
                "source": "base64",
                "media_type": "image/png",
                "data": IMAGE_DATA,
            },
        ),
    )

    chat = render_content_parts(request.content_parts, target_format="chat")
    responses = render_content_parts(request.content_parts, target_format="responses")
    anthropic = render_content_parts(request.content_parts, target_format="anthropic")
    gemini = render_content_parts(request.content_parts, target_format="gemini")
    assert chat[1]["image_url"]["url"] == f"data:image/png;base64,{IMAGE_DATA}"
    assert responses[1]["image_url"] == f"data:image/png;base64,{IMAGE_DATA}"
    assert anthropic[1]["source"]["data"] == IMAGE_DATA
    assert gemini[1]["inlineData"]["data"] == IMAGE_DATA


def test_file_reference_is_rendered_only_by_protocols_that_have_a_file_input():
    parts = ({"type": "text", "text": "Read"}, {"type": "file", "source": "file_id", "file_id": "file-123"})
    responses = render_content_parts(parts, target_format="responses")
    assert responses[1] == {"type": "input_file", "file_id": "file-123"}
    with pytest.raises(ContentContractError, match="not_representable"):
        render_content_parts(parts, target_format="chat")
    with pytest.raises(ContentContractError, match="not_representable"):
        render_content_parts(parts, target_format="anthropic")
    with pytest.raises(ContentContractError, match="gemini_requires"):
        render_content_parts(parts, target_format="gemini")


@pytest.mark.parametrize("api_format", ["chat", "responses", "anthropic", "gemini"])
def test_structured_output_uses_each_protocols_native_wrapper(api_format):
    request = FusionRequest(
        model="axio-pro",
        prompt="Return an object.",
        structured_output={
            "type": "json_schema",
            "name": "answer",
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    )
    profile = _profile(api_format)
    if api_format == "chat":
        payload = _chat_payload(profile, request, prompt=request.prompt, system="system")
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["name"] == "answer"
    elif api_format == "responses":
        payload = _responses_typed_payload(profile, request, prompt=request.prompt, system="system")
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["name"] == "answer"
    elif api_format == "anthropic":
        payload = _anthropic_payload(profile, request, prompt=request.prompt, system="system")
        assert payload["output_config"]["format"]["type"] == "json_schema"
        assert payload["output_config"]["format"]["schema"]["required"] == ["answer"]
    else:
        payload = _gemini_payload(profile, request, prompt=request.prompt, system="system")
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["responseSchema"]["required"] == ["answer"]


def test_responses_text_fallback_cannot_flatten_multimodal_or_file_input():
    assert _responses_text_fallback_preserves_turn(_image_request()) is False


def test_internal_control_prompt_keeps_original_image_when_public_history_does_not():
    from axio_fusion_api.providers import _direct_prompt_content_parts

    request = _image_request()
    parts = _direct_prompt_content_parts(request, "internal role packet")
    assert parts == request.content_parts
    with_history = FusionRequest(
        model=request.model,
        prompt=request.prompt,
        content_parts=request.content_parts,
        history=(
            {
                "role": "user",
                "content": request.prompt,
                "content_parts": list(request.content_parts),
            },
        ),
        metadata={"_axio_current_prompt_in_history": True},
    )
    assert _direct_prompt_content_parts(with_history, "internal role packet") == ()


def test_vision_admission_rejects_profile_without_vision_capability():
    request = _image_request()
    plan = build_route_plan(request, [_profile("chat", supports_vision=False)])
    assert plan["selected_models"] == []
    assert plan["privacy_policy"]["blocked_counts"]["vision_capability_required"] == 1


@pytest.mark.parametrize("probe_status", ["failed", "unsupported", "indeterminate"])
def test_vision_admission_rejects_profile_without_a_passing_endpoint_probe(probe_status):
    request = _image_request()
    profile = _profile("chat")
    profile = normalize_profile(
        {
            **profile.safe_dict(),
            "vision_probe_status": probe_status,
            "vision_capability_source": "operational_probe",
        }
    )

    plan = build_route_plan(request, [profile])

    assert plan["selected_models"] == []
    assert plan["privacy_policy"]["blocked_counts"]["vision_capability_required"] == 1


def test_indeterminate_vision_probe_does_not_remove_text_route_eligibility():
    profile = normalize_profile(
        {
            **_profile("chat").safe_dict(),
            "vision_probe_status": "indeterminate",
            "vision_capability_source": "operational_probe",
        }
    )

    image_plan = build_route_plan(_image_request(), [profile])
    text_plan = build_route_plan(
        FusionRequest(model="axio-pro", prompt="Summarize the meeting notes."),
        [profile],
    )

    assert image_plan["selected_models"] == []
    assert text_plan["selected_models"]


@pytest.mark.parametrize("response_path", ["/v1/chat/completions", "/v1/axio/route-plan"])
def test_invalid_content_contract_is_a_public_400(response_path):
    payload = {
        "model": "axio-fast",
        "messages": [{"role": "user", "content": [{"type": "audio", "audio": {}}]}],
    }
    if response_path.endswith("route-plan"):
        payload = {"api_format": "chat/completions", "request": payload}
    status, _headers, body = handle_request(
        method="POST",
        path=response_path,
        headers={},
        body=json.dumps(payload).encode("utf-8"),
        engine=object(),
        record_trace=False,
        record_runtime=False,
    )
    response = json.loads(body)
    assert status == 400
    assert response["error"]["code"] == "unsupported_content_part"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/v1/chat/completions",
            {
                "model": "axio-fast",
                "messages": [{"role": "user", "content": "hello"}],
                "reasoning_effort": "high",
                "reasoning": {"effort": "low"},
            },
        ),
        (
            "/v1/responses",
            {
                "model": "axio-terra",
                "input": "hello",
                "reasoning_effort": "low",
                "reasoning": {"effort": "medium"},
            },
        ),
    ],
)
def test_conflicting_openai_reasoning_aliases_are_public_400(path, payload):
    status, _headers, body = handle_request(
        method="POST",
        path=path,
        headers={},
        body=json.dumps(payload).encode("utf-8"),
        engine=object(),
        record_trace=False,
        record_runtime=False,
    )

    response = json.loads(body)
    assert status == 400
    assert response["error"]["code"] == "conflicting_reasoning_effort"


def test_invalid_content_contract_is_a_400_before_incremental_stream_headers():
    payload = {
        "model": "axio-fast",
        "stream": True,
        "messages": [{"role": "user", "content": [{"type": "audio"}]}],
    }
    prepared, immediate = _prepare_incremental_stream_request(
        method="POST",
        path="/v1/chat/completions",
        headers={},
        body=json.dumps(payload).encode("utf-8"),
        engine=object(),
        live=False,
        record_runtime=False,
    )
    assert prepared is None
    assert immediate is not None
    status, _headers, body = immediate
    assert status == 400
    assert json.loads(body)["error"]["code"] == "unsupported_content_part"


def test_invalid_structured_output_is_rejected_without_persisting_schema():
    with pytest.raises(ContentContractError, match="unsupported structured output"):
        canonicalize_payload(
            {
                "messages": [{"role": "user", "content": "Return JSON."}],
                "response_format": {"type": "xml", "schema": {"secret": "value"}},
            },
            api_format="chat/completions",
        )


def test_chat_developer_role_keeps_instruction_priority_across_history_normalization():
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "messages": [
                {"role": "developer", "content": "Follow the internal policy."},
                {"role": "user", "content": "Answer the task."},
            ],
        },
        api_format="chat/completions",
    )

    assert request.system == "Follow the internal policy."
    assert request.history[0]["role"] == "system"
    assert request.history[-1]["role"] == "user"


def test_responses_array_instructions_are_text_normalized_not_stringified():
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "instructions": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Use the fixed rubric."}],
                },
                {"type": "input_text", "text": "Cite uncertainty."},
            ],
            "input": "Solve the task.",
        },
        api_format="responses",
    )

    assert request.system == "Use the fixed rubric.\nCite uncertainty."
    assert "input_text" not in request.system
    assert "role': 'developer'" not in request.system


def test_responses_non_text_instruction_is_rejected_before_provider_dispatch():
    with pytest.raises(ContentContractError, match="instructions must contain text only"):
        canonicalize_payload(
            {
                "model": "axio-pro",
                "instructions": [
                    {
                        "type": "input_image",
                        "image_url": "https://example.com/instruction.png",
                    }
                ],
                "input": "Solve the task.",
            },
            api_format="responses",
        )
