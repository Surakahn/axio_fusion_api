from __future__ import annotations

import http.client
import json
import sys
import threading
import time
from pathlib import Path

import pytest


STANDALONE_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_SRC = STANDALONE_ROOT / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.compat import (
    IncrementalStreamRenderer,
    canonicalize_payload,
    normalize_public_output_text,
    render_response,
    render_stream_events,
)
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api import providers as provider_module
from axio_fusion_api.providers import (
    HTTPProviderClient,
    ProviderCompletion,
    ProviderExecutionError,
    ProviderStreamObserver,
)
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.schemas import FusionResponse
from axio_fusion_api.server import create_http_server


@pytest.mark.parametrize(
    ("api_format", "start_marker", "delta_marker", "terminal_marker"),
    [
        ("chat/completions", "chat.completion.chunk", '"content":"visible"', "[DONE]"),
        ("responses", "response.created", "response.output_text.delta", "response.completed"),
        ("anthropic", "message_start", "content_block_delta", "message_stop"),
        ("gemini", "", '"text":"visible"', "usageMetadata"),
    ],
)
def test_incremental_renderer_preserves_native_terminal_shapes(
    api_format: str,
    start_marker: str,
    delta_marker: str,
    terminal_marker: str,
) -> None:
    request = canonicalize_payload(
        {
            "model": "axio-fast",
            "messages": [{"role": "user", "content": "private request text"}],
        },
        api_format=api_format,
    )
    response = FusionResponse(
        text="visible",
        request=request,
        route_plan={},
        response_id="fusion-incremental-test",
        created=1_700_000_000,
    )
    renderer = IncrementalStreamRenderer(
        request,
        api_format=api_format,
        response_id=response.response_id,
        created=response.created,
        include_usage=True,
    )

    start = renderer.start().decode("utf-8")
    delta = renderer.text_delta("visible").decode("utf-8")
    terminal = renderer.complete(response).decode("utf-8")

    assert start_marker in start
    assert delta_marker in delta
    assert terminal_marker in terminal
    assert "private request text" not in start + delta + terminal


def test_public_output_normalization_extracts_internal_answer_envelope():
    internal = json.dumps(
        {
            "answer": "最终面向用户的答案",
            "reasoning_summary": ["内部推理不应出现在公共文本"],
            "confidence": 0.93,
        },
        ensure_ascii=False,
    )

    assert normalize_public_output_text(internal) == "最终面向用户的答案"
    assert normalize_public_output_text("```json\n" + internal + "\n```") == "最终面向用户的答案"
    assert normalize_public_output_text("  plain text with spacing  ") == "  plain text with spacing  "


def test_public_output_normalization_preserves_ordinary_and_explicit_json():
    ordinary = '{"answer": "用户要求的 JSON", "kind": "public"}'
    explicit_request = canonicalize_payload(
        {
            "model": "axio-pro",
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": "return JSON"}],
        }
    )

    assert normalize_public_output_text(ordinary) == ordinary
    assert (
        normalize_public_output_text(
            '{"answer": "保留完整 JSON", "reasoning": ["private"]}',
            structured_output=explicit_request.structured_output,
        )
        == '{"answer": "保留完整 JSON", "reasoning": ["private"]}'
    )


@pytest.mark.parametrize("api_format", ["chat/completions", "responses", "anthropic", "gemini"])
def test_all_public_protocols_hide_internal_synthesizer_json(api_format: str):
    internal = json.dumps(
        {
            "final_answer": "跨协议一致的公共答案",
            "analysis": "provider-specific internal analysis",
            "ranked_candidates": [{"candidate_id": "primary_solver", "score": 0.9}],
        },
        ensure_ascii=False,
    )
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "messages": [{"role": "user", "content": "check"}],
        },
        api_format=api_format,
    )
    response = FusionResponse(
        text=internal,
        request=request,
        route_plan={},
        response_id="fusion-normalization-test",
        created=1_700_000_000,
    )

    rendered = render_response(response, api_format=api_format)
    serialized = json.dumps(rendered, ensure_ascii=False)
    assert "跨协议一致的公共答案" in serialized
    assert "provider-specific internal analysis" not in serialized
    assert rendered["metadata"]["output_text_normalization"]["applied"] is True

    stream = render_stream_events(response, api_format=api_format).decode("utf-8")
    assert "跨协议一致的公共答案" in stream
    assert "provider-specific internal analysis" not in stream


def test_incremental_renderer_normalizes_final_internal_json_before_terminal_events():
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "messages": [{"role": "user", "content": "check"}],
        }
    )
    response = FusionResponse(
        text='{"answer":"incremental public answer","reasoning":"private"}',
        request=request,
        route_plan={},
        response_id="fusion-incremental-normalization-test",
        created=1_700_000_000,
    )
    renderer = IncrementalStreamRenderer(
        request,
        api_format="chat/completions",
        response_id=response.response_id,
        created=response.created,
    )

    stream = renderer.complete(response).decode("utf-8")

    assert "incremental public answer" in stream
    assert '"reasoning":"private"' not in stream


def test_complete_stream_buffers_json_like_synthesizer_deltas_before_public_release():
    class JsonSynthesisStreamingClient:
        def complete(
            self,
            profile,
            request,
            *,
            prompt,
            system,
            timeout=None,
        ):
            return self.complete_turn(
                profile,
                request,
                prompt=prompt,
                system=system,
                timeout=timeout,
            ).text

        def complete_turn(
            self,
            profile,
            request,
            *,
            prompt,
            system,
            timeout=None,
            stream_observer=None,
            cancellation_event=None,
        ):
            del profile, request, system, timeout, cancellation_event
            if "Compare these Axio Fusion candidate answers" in prompt:
                return ProviderCompletion(
                    json.dumps(
                        {
                            "ranked_candidates": [
                                {"candidate_id": "primary_solver", "score": 0.91},
                                {"candidate_id": "independent_solver", "score": 0.87},
                            ],
                            "ready_for_synthesis": True,
                        }
                    )
                )
            if "Synthesize one final answer" in prompt:
                assert stream_observer is not None
                assert stream_observer.emit_text_delta('{"final_answer":"') is True
                assert stream_observer.emit_text_delta("buffered answer") is True
                assert stream_observer.emit_text_delta('","reasoning":"private"}') is True
                return ProviderCompletion(
                    '{"final_answer":"buffered answer","reasoning":"private"}'
                )
            return ProviderCompletion(
                json.dumps(
                    {
                        "answer": "private candidate answer",
                        "confidence": 0.82,
                        "evidence": [{"claim": "fixture", "source": "unit"}],
                    }
                )
            )

    profiles = [
        normalize_profile(
            {
                "provider": "buffered-alpha",
                "model": "reasoner-a",
                "capabilities": {"science_knowledge": 0.92, "structured_output": 0.88},
            }
        ),
        normalize_profile(
            {
                "provider": "buffered-beta",
                "model": "reasoner-b",
                "capabilities": {"science_knowledge": 0.84, "structured_output": 0.88},
            }
        ),
    ]
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "task_type": "science_research",
            "messages": [{"role": "user", "content": "buffer this"}],
        }
    )
    visible_deltas: list[str] = []

    response = FusionEngine(
        profiles,
        client=JsonSynthesisStreamingClient(),
        cache_enabled=False,
    ).complete_stream(request, on_text_delta=visible_deltas.append, live=True)

    assert response.text == "buffered answer"
    assert "".join(visible_deltas) == "buffered answer"
    assert all("reasoning" not in delta for delta in visible_deltas)


@pytest.mark.parametrize(
    ("path", "payload", "first_delta_marker", "terminal_marker"),
    [
        (
            "/v1/chat/completions",
            {
                "model": "axio-fast",
                "stream": True,
                "messages": [{"role": "user", "content": "private caller prompt"}],
            },
            b'"content":"first "',
            "data: [DONE]",
        ),
        (
            "/v1/responses",
            {"model": "axio-fast", "stream": True, "input": "private caller prompt"},
            b'"delta":"first "',
            "event: response.completed",
        ),
        (
            "/v1/messages",
            {
                "model": "axio-fast",
                "stream": True,
                "messages": [{"role": "user", "content": "private caller prompt"}],
            },
            b'"text":"first "',
            "event: message_stop",
        ),
        (
            "/v1beta/models/axio-fast:streamGenerateContent?alt=sse",
            {
                "contents": [
                    {"role": "user", "parts": [{"text": "private caller prompt"}]}
                ]
            },
            b'"text":"first "',
            "usageMetadata",
        ),
    ],
)
def test_http_server_delivers_a_public_delta_before_the_provider_finishes(
    path: str,
    payload: dict,
    first_delta_marker: bytes,
    terminal_marker: str,
) -> None:
    class SlowStreamingClient:
        def __init__(self) -> None:
            self.first_delta_emitted = threading.Event()
            self.release_completion = threading.Event()
            self.finished = threading.Event()
            self.calls = 0

        def complete_turn(
            self,
            profile,
            request,
            *,
            prompt,
            system,
            timeout=None,
            stream_observer=None,
            cancellation_event=None,
        ):
            del profile, request, prompt, system, timeout, cancellation_event
            self.calls += 1
            assert stream_observer is not None
            assert stream_observer.emit_text_delta("first ") is True
            self.first_delta_emitted.set()
            assert self.release_completion.wait(timeout=3)
            assert stream_observer.emit_text_delta("second") is True
            self.finished.set()
            return ProviderCompletion("first second")

    client = SlowStreamingClient()
    engine = FusionEngine(
        [normalize_profile({"provider": "stream-fixture", "model": "fast-model"})],
        client=client,
        cache_enabled=False,
    )
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        live=True,
        engine=engine,
        record_trace=False,
        record_runtime=False,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Transfer-Encoding") == "chunked"
        assert response.getheader("Content-Length") is None

        observed = bytearray()
        first_delta_deadline = time.monotonic() + 3
        while first_delta_marker not in observed and time.monotonic() < first_delta_deadline:
            chunk = response.read(1)
            if not chunk:
                break
            observed.extend(chunk)

        assert first_delta_marker in observed
        assert client.first_delta_emitted.wait(timeout=0.5)
        assert client.finished.is_set() is False
        assert b"private caller prompt" not in observed

        client.release_completion.set()
        observed.extend(response.read())
        stream = observed.decode("utf-8")
        assert '"text":"second"' in stream or '"content":"second"' in stream or '"delta":"second"' in stream
        assert terminal_marker in stream
        assert client.finished.is_set()
        assert client.calls == 1
    finally:
        client.release_completion.set()
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert worker.is_alive() is False


def test_http_provider_stream_observer_preserves_visible_whitespace_and_ignores_reasoning(
    monkeypatch,
) -> None:
    class FakeStreamResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __init__(self) -> None:
            self._lines = iter(
                [
                    b'data: {"choices":[{"delta":{"reasoning_content":"private reasoning","content":"first "}}]}\n',
                    b"\n",
                    b'data: {"choices":[{"delta":{"content":"second"}}]}\n',
                    b"\n",
                    b"data: [DONE]\n",
                    b"\n",
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            del exc_type, exc_value, traceback
            return False

        def readline(self):
            return next(self._lines, b"")

    opens = []

    class FakeOpener:
        def open(self, request, timeout=None):
            opens.append({"url": request.full_url, "timeout": timeout})
            return FakeStreamResponse()

    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "off")
    monkeypatch.setenv("STREAM_OBSERVER_BASE_URL", "https://stream.fixture/v1")
    monkeypatch.setenv("STREAM_OBSERVER_KEY", "fixture-key")
    monkeypatch.setattr(provider_module.urllib.request, "build_opener", lambda *_handlers: FakeOpener())
    profile = normalize_profile(
        {
            "provider": "stream-observer-fixture",
            "model": "stream-model",
            "api_format": "chat",
            "base_url_env": "STREAM_OBSERVER_BASE_URL",
            "api_key_env": "STREAM_OBSERVER_KEY",
        }
    )
    request = canonicalize_payload(
        {"model": "axio-fast", "messages": [{"role": "user", "content": "hello"}]}
    )
    visible_deltas: list[str] = []
    observer = ProviderStreamObserver(visible_deltas.append)

    completion = HTTPProviderClient(require_streaming=True).complete_turn(
        profile,
        request,
        prompt=request.prompt,
        system=request.system,
        timeout=2,
        stream_observer=observer,
    )

    assert completion.text == "first second"
    assert visible_deltas == ["first ", "second"]
    assert "private reasoning" not in "".join(visible_deltas)
    assert observer.emitted_text is True
    assert len(opens) == 1


def test_http_provider_stops_after_downstream_stream_cancellation(monkeypatch) -> None:
    class FakeStreamResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __init__(self) -> None:
            self._lines = iter(
                [
                    b'data: {"choices":[{"delta":{"content":"first"}}]}\n',
                    b"\n",
                    b'data: {"choices":[{"delta":{"content":"second"}}]}\n',
                    b"\n",
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            del exc_type, exc_value, traceback
            return False

        def readline(self):
            return next(self._lines, b"")

    opens = 0

    class FakeOpener:
        def open(self, request, timeout=None):
            nonlocal opens
            del request, timeout
            opens += 1
            return FakeStreamResponse()

    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "off")
    monkeypatch.setenv("STREAM_CANCEL_BASE_URL", "https://cancel.fixture/v1")
    monkeypatch.setenv("STREAM_CANCEL_KEY", "fixture-key")
    monkeypatch.setattr(provider_module.urllib.request, "build_opener", lambda *_handlers: FakeOpener())
    profile = normalize_profile(
        {
            "provider": "stream-cancel-fixture",
            "model": "stream-model",
            "api_format": "chat",
            "base_url_env": "STREAM_CANCEL_BASE_URL",
            "api_key_env": "STREAM_CANCEL_KEY",
        }
    )
    request = canonicalize_payload(
        {"model": "axio-fast", "messages": [{"role": "user", "content": "hello"}]}
    )
    cancellation_event = threading.Event()
    observer = ProviderStreamObserver(lambda _text: False, cancellation_event=cancellation_event)

    with pytest.raises(ProviderExecutionError) as exc_info:
        HTTPProviderClient(require_streaming=True).complete_turn(
            profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=2,
            stream_observer=observer,
            cancellation_event=cancellation_event,
        )

    assert exc_info.value.error_code == "public_stream_cancelled"
    assert cancellation_event.is_set()
    assert opens == 1


def test_http_server_emits_a_terminal_error_without_fallback_after_public_text() -> None:
    class FailAfterFirstDeltaClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete_turn(
            self,
            profile,
            request,
            *,
            prompt,
            system,
            timeout=None,
            stream_observer=None,
            cancellation_event=None,
        ):
            del profile, request, prompt, system, timeout, cancellation_event
            self.calls += 1
            assert stream_observer is not None
            assert stream_observer.emit_text_delta("partial ") is True
            raise ProviderExecutionError("private provider failure", error_code="fixture_failure")

    client = FailAfterFirstDeltaClient()
    engine = FusionEngine(
        [normalize_profile({"provider": "stream-failure", "model": "fast-model"})],
        client=client,
        cache_enabled=False,
    )
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        live=True,
        engine=engine,
        record_trace=False,
        record_runtime=False,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps(
                {
                    "model": "axio-fast",
                    "stream": True,
                    "messages": [{"role": "user", "content": "private failure request"}],
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        stream = response.read().decode("utf-8")
        assert response.status == 200
        assert '"content":"partial "' in stream
        assert '"code":"public_stream_interrupted"' in stream
        assert "data: [DONE]" in stream
        assert "private provider failure" not in stream
        assert client.calls == 1
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert worker.is_alive() is False


def test_pro_direct_fallback_route_streams_its_public_acting_solver() -> None:
    class DirectProClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete_turn(
            self,
            profile,
            request,
            *,
            prompt,
            system,
            timeout=None,
            stream_observer=None,
            cancellation_event=None,
        ):
            del profile, request, prompt, system, timeout, cancellation_event
            self.calls += 1
            assert stream_observer is not None
            assert stream_observer.emit_text_delta("direct pro ") is True
            assert stream_observer.emit_text_delta("answer") is True
            return ProviderCompletion("direct pro answer")

    profile = normalize_profile(
        {
            "provider": "pro-direct-stream",
            "model": "pro-direct-model",
            "capabilities": {"daily_work": 0.9, "structured_output": 0.9},
        }
    )
    client = DirectProClient()
    request = canonicalize_payload(
        {
            "model": "axio-pro",
            "messages": [{"role": "user", "content": "say hello"}],
        }
    )
    engine = FusionEngine([profile], client=client, cache_enabled=False)
    assert engine.complete(request, live=False).route_plan["strategy"] == "pro_direct_with_verifier_gap"
    visible_deltas: list[str] = []

    response = engine.complete_stream(
        request,
        on_text_delta=visible_deltas.append,
        live=True,
    )

    assert response.text == "direct pro answer"
    assert "".join(visible_deltas) == "direct pro answer"
    assert client.calls == 1


@pytest.mark.parametrize("public_model", ["axio-terra", "axio-pro"])
def test_public_stream_exposes_only_the_final_acting_role(
    public_model: str,
) -> None:
    class SynthesisStreamingClient:
        def __init__(self) -> None:
            self.non_final_observer_count = 0
            self.final_actor_observer_count = 0

        def complete(self, profile, request, *, prompt, system, timeout=None):
            return self.complete_turn(
                profile,
                request,
                prompt=prompt,
                system=system,
                timeout=timeout,
            ).text

        def complete_turn(
            self,
            profile,
            request,
            *,
            prompt,
            system,
            timeout=None,
            stream_observer=None,
            cancellation_event=None,
        ):
            del profile, timeout, cancellation_event
            if "Compare these Axio Fusion candidate answers" in prompt:
                assert stream_observer is None
                return ProviderCompletion(
                    json.dumps(
                        {
                            "consensus": [],
                            "contradictions": [],
                            "unique_insights": [],
                            "missing_coverage": [],
                            "collective_blind_spots": [],
                            "ranked_candidates": [
                                {"candidate_id": "primary_solver", "score": 0.91},
                                {"candidate_id": "independent_solver", "score": 0.87},
                            ],
                            "follow_up_tasks": [],
                            "ready_for_synthesis": True,
                        }
                    )
                )
            if "Synthesize one final answer" in prompt or "fusion synthesizer" in system.lower():
                assert stream_observer is not None
                self.final_actor_observer_count += 1
                assert stream_observer.emit_text_delta("published ") is True
                assert stream_observer.emit_text_delta("answer") is True
                return ProviderCompletion("published answer")
            if request.public_model == "axio-terra" and stream_observer is not None:
                self.final_actor_observer_count += 1
                assert stream_observer.emit_text_delta("published ") is True
                assert stream_observer.emit_text_delta("answer") is True
                return ProviderCompletion("published answer")
            if stream_observer is not None:
                self.non_final_observer_count += 1
            return ProviderCompletion(
                json.dumps(
                    {
                        "answer": "private candidate answer",
                        "evidence": [{"claim": "fixture", "source": "unit", "reliability": 0.8}],
                        "assumptions": [],
                        "uncertainties": [],
                        "confidence": 0.82,
                    }
                )
            )

    profiles = [
        normalize_profile(
            {
                "provider": "stream-alpha",
                "model": "reasoner-a",
                "capabilities": {
                    "science_knowledge": 0.92,
                    "critique": 0.82,
                    "structured_output": 0.88,
                },
            }
        ),
        normalize_profile(
            {
                "provider": "stream-beta",
                "model": "reasoner-b",
                "capabilities": {
                    "science_knowledge": 0.84,
                    "critique": 0.91,
                    "structured_output": 0.88,
                },
            }
        ),
    ]
    client = SynthesisStreamingClient()
    request = canonicalize_payload(
        {
            "model": public_model,
            "task_type": "science_research",
            "messages": [{"role": "user", "content": "private deliberation request"}],
        }
    )
    visible_deltas: list[str] = []

    response = FusionEngine(profiles, client=client, cache_enabled=False).complete_stream(
        request,
        on_text_delta=visible_deltas.append,
        live=True,
    )

    assert response.text == "published answer"
    assert "".join(visible_deltas) == "published answer"
    assert client.final_actor_observer_count == 1
    assert client.non_final_observer_count == 0
    assert all("private candidate answer" not in value for value in visible_deltas)
