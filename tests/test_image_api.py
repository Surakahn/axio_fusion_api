from __future__ import annotations

import io
import http.client
import json
import threading
import time
import urllib.error
from pathlib import Path

import pytest

from axio_fusion_api import server
from axio_fusion_api.channel_config import build_runtime_profiles
from axio_fusion_api.image_api import (
    ImagePart,
    ImageProviderClient,
    ImageProviderResult,
    ImageRequestError,
    ImagePromptTransformer,
    ImageRouter,
    _encode_multipart,
    parse_edit_payload,
    parse_generation_payload,
)
from axio_fusion_api.image_probe import (
    build_image_probe_bound_registry,
    probe_image_capabilities,
    redact_image_probe_artifact,
)
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import ProviderExecutionError
from axio_fusion_api.registry import load_image_probe_candidates, load_image_registry
from axio_fusion_api.schemas import ModelProfile


def _image_profile(
    *,
    probe_status: str = "passed",
    capability_status: str = "verified",
    streaming: bool = True,
    max_input_images: int = 1,
    p95_latency_ms: int | None = None,
    runtime_keys: tuple[str, ...] = (),
    transport: str = "images_api",
    api_format: str = "chat/completions",
    parameter_support: dict[str, object] | None = None,
) -> ModelProfile:
    image_capabilities = {
        "status": capability_status,
        "transport": transport,
        "operations": ["generation", "editing"],
        "streaming": streaming,
        "max_input_images": max_input_images,
    }
    if parameter_support is not None:
        image_capabilities["parameter_support"] = parameter_support
    return ModelProfile(
        provider="image-provider",
        model="gpt-image-2",
        api_format=api_format,
        model_kind="image",
        image_probe_status=probe_status,
        image_capabilities=image_capabilities,
        p95_latency_ms=p95_latency_ms,
        runtime_base_url="https://image-provider.invalid/v1",
        runtime_api_keys=runtime_keys,
    )


class _FakeImageClient:
    def __init__(self) -> None:
        self.generate_calls: list[dict] = []
        self.edit_calls: list[tuple[dict, list[ImagePart]]] = []

    def generate(self, profile, payload, *, timeout=None):
        self.generate_calls.append(dict(payload))
        return ImageProviderResult(
            data=({"b64_json": "encoded-image"},),
            created=123,
            stream_events=(
                {"type": "image_generation.partial_image", "b64_json": "partial"},
                {"type": "image_generation.completed", "b64_json": "encoded-image"},
            ) if payload.get("stream") else (),
            stream_protocol="sse" if payload.get("stream") else "",
            event_prefix="image_generation",
        )

    def edit(self, profile, fields, files, *, timeout=None):
        self.edit_calls.append((dict(fields), list(files)))
        return ImageProviderResult(
            data=({"url": "https://images.invalid/result.png"},),
            created=456,
            event_prefix="image_edit",
        )


def test_image_profiles_are_excluded_from_text_and_text_profiles_from_images():
    image = _image_profile()
    text = ModelProfile(provider="text-provider", model="text-model", model_kind="text")

    assert image.text_model_eligible is False
    assert text.text_model_eligible is True
    assert image.image_generation_eligible is True
    assert text.image_generation_eligible is False


def test_discovered_gpt_image_names_enter_unverified_image_lane_only():
    profiles = build_runtime_profiles(
        {
            "providers": [
                {
                    "provider": "image-discovery-channel",
                    "api_format": "chat/completions",
                    "base_url": "https://image-discovery.invalid/v1",
                    "api_key": "fixture-key",
                    "models": ["gpt-image-2", "text-model"],
                }
            ]
        }
    )

    image = next(profile for profile in profiles if profile.model == "gpt-image-2")
    text = next(profile for profile in profiles if profile.model == "text-model")
    assert image.model_kind == "image"
    assert image.text_model_eligible is False
    assert image.image_probe_status == "not_run"
    assert image.image_capabilities["status"] == "candidate"
    assert image.image_generation_eligible is False
    assert text.model_kind == "text"
    assert text.text_model_eligible is True


def test_image_probe_candidate_loader_reads_unpromoted_image_registry(tmp_path):
    profile = _image_profile(probe_status="not_run", capability_status="candidate")
    path = Path(tmp_path) / "image-candidates.json"
    path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.registry.v1",
                "image_capability_registry_ready": False,
                "models": [profile.safe_dict()],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_image_probe_candidates(path, include_disabled=True)

    assert [item.model for item in loaded] == ["gpt-image-2"]
    assert loaded[0].image_generation_eligible is False


def test_image_capability_requires_verified_capability_and_probe():
    assert _image_profile(capability_status="candidate").image_generation_eligible is False
    assert _image_profile(probe_status="not_run").image_generation_eligible is False
    assert _image_profile(probe_status="failed").image_generation_eligible is False


def test_image_parameter_support_is_normalized_as_closed_profile_metadata():
    profile = _image_profile(
        parameter_support={
            "inputFidelity": True,
            "transparentBackground": False,
            "provider_specific": "discarded",
        }
    )

    assert profile.image_capabilities["parameter_support"] == {
        "input_fidelity": "supported",
        "background_transparent": "unsupported",
    }


def test_image_router_rejects_unsupported_image_parameters_before_composition():
    fake = _FakeImageClient()
    profile = _image_profile(
        parameter_support={
            "input_fidelity": "unsupported",
            "background_transparent": "unsupported",
        }
    )
    router = ImageRouter([profile], client=fake)

    with pytest.raises(ImageRequestError) as generation_error:
        router.generate(
            {
                "model": "axio-terra",
                "prompt": "blue square",
                "background": "transparent",
            }
        )
    assert generation_error.value.code == "image_background_not_supported"
    assert fake.generate_calls == []

    with pytest.raises(ImageRequestError) as editing_error:
        router.edit(
            {
                "model": "axio-terra",
                "prompt": "keep the subject",
                "input_fidelity": "high",
            },
            [ImagePart("image", "source.png", "image/png", b"png")],
        )
    assert editing_error.value.code == "image_parameter_unsupported"
    assert fake.edit_calls == []


def test_image_router_forwards_declared_supported_edit_parameter():
    fake = _FakeImageClient()
    profile = _image_profile(
        parameter_support={
            "input_fidelity": "supported",
            "background_transparent": "supported",
        }
    )

    _response, _result, _profile = ImageRouter([profile], client=fake).edit(
        {
            "model": "axio-terra",
            "prompt": "keep the subject",
            "input_fidelity": "high",
        },
        [ImagePart("image", "source.png", "image/png", b"png")],
    )

    assert fake.edit_calls[0][0]["input_fidelity"] == "high"


def test_load_image_registry_requires_promoted_image_only_binding(tmp_path):
    profile = _image_profile()
    registry_path = tmp_path / "image-registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.registry.v1",
                "models": [profile.safe_dict()],
                "image_capability_registry_ready": True,
                "image_probe_binding": {"status": "ready"},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_image_registry(registry_path)

    assert [item.profile_id for item in loaded] == [profile.profile_id]
    assert loaded[0].image_generation_eligible is True


def test_load_image_registry_rejects_unpromoted_or_mixed_profiles(tmp_path):
    image = _image_profile()
    text = ModelProfile(provider="text-provider", model="text-model")

    unpromoted = tmp_path / "unpromoted.json"
    unpromoted.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.registry.v1",
                "models": [image.safe_dict()],
                "image_capability_registry_ready": False,
                "image_probe_binding": {"status": "blocked"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not promoted"):
        load_image_registry(unpromoted)

    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.registry.v1",
                "models": [image.safe_dict(), text.safe_dict()],
                "image_capability_registry_ready": True,
                "image_probe_binding": {"status": "ready"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="text profiles"):
        load_image_registry(mixed)


def test_explicit_image_profiles_are_isolated_from_text_engine():
    profile = _image_profile()
    fake = _FakeImageClient()

    status, _headers, body = server.handle_request(
        method="POST",
        path="/v1/images/generations",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"model": "axio-fast", "prompt": "a red kite"}),
        engine=FusionEngine([profile]),
        image_profiles=[],
        record_runtime=False,
        record_trace=False,
    )

    assert status == 503
    assert json.loads(body)["error"]["code"] == "image_capability_unavailable"
    assert fake.generate_calls == []


def test_health_reports_image_registry_separately_from_text_registry():
    text = ModelProfile(provider="text-provider", model="text-model")
    status, _headers, body = server.handle_request(
        method="GET",
        path="/v1/health",
        engine=FusionEngine([text]),
        image_profiles=[_image_profile()],
        record_runtime=False,
        record_trace=False,
    )

    payload = json.loads(body)
    assert status == 200
    assert payload["image_registry"]["generation_profile_count"] == 1
    assert payload["image_registry"]["editing_profile_count"] == 1
    assert payload["image_registry"]["text_fusion_isolated"] is True


def test_generation_parser_allowlists_fields_and_parses_boolean():
    payload = parse_generation_payload(
        json.dumps(
            {
                "model": "axio-pro",
                "prompt": "a red kite",
                "n": 2,
                "stream": "false",
                "unknown_provider_field": "must not cross boundary",
            }
        )
    )

    assert payload == {"model": "axio-pro", "prompt": "a red kite", "n": 2, "stream": False}
    assert "unknown_provider_field" not in payload


def test_generation_parser_uses_official_partial_image_limit():
    with pytest.raises(ImageRequestError) as error:
        parse_generation_payload(
            json.dumps({"model": "axio-pro", "prompt": "x", "partial_images": 4})
        )
    assert error.value.code == "image_field_invalid"


def test_generation_parser_enforces_request_size_limit(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_IMAGE_MAX_REQUEST_BYTES", "1048576")
    with pytest.raises(ImageRequestError) as error:
        parse_generation_payload(
            json.dumps({"model": "axio-pro", "prompt": "x" * 1_100_000})
        )
    assert error.value.code == "image_request_too_large"
    assert error.value.status == 413


def test_image_provider_rejects_oversized_non_stream_response(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_IMAGE_MAX_RESPONSE_BYTES", "1048576")
    profile = _image_profile(runtime_keys=("image-key",))

    class Response:
        headers = {
            "Content-Type": "application/json",
            "Content-Length": "1048577",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            raise AssertionError("content length must reject before reading")

    monkeypatch.setattr(
        "axio_fusion_api.image_api._open_provider_url",
        lambda request, *, timeout: Response(),
    )

    with pytest.raises(ProviderExecutionError) as error:
        ImageProviderClient().generate(
            profile,
            {"model": "axio-terra", "prompt": "blue square"},
            timeout=5,
        )
    assert error.value.error_code == "image_response_too_large"


class _FakePromptComposerEngine:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.requests = []
        self.profiles = [
            ModelProfile(provider="text-provider", model="text-model", model_kind="text")
        ]

    def complete(self, request, *, live):
        self.requests.append((request, live))
        return type("Response", (), {"text": self.response_text})()


def test_image_prompt_transformer_composes_intent_with_fixed_json_contract():
    engine = _FakePromptComposerEngine(
        '{"prompt":"A precise editorial product photo of a blue ceramic cup on white linen."}'
    )
    transformer = ImagePromptTransformer(engine)

    payload, receipt = transformer.transform(
        {"model": "axio-terra", "prompt": "make my cup photo look clean"},
        operation="editing",
    )

    assert payload["prompt"].startswith("A precise editorial")
    assert receipt.applied is True
    assert receipt.reason == "text_prompt_composed"
    request, live = engine.requests[0]
    assert live is True
    assert "<user_image_intent>" in request.prompt
    assert "make my cup photo look clean" in request.prompt
    assert receipt.safe_dict()["raw_transformed_prompt_persisted"] is False


def test_image_prompt_transformer_falls_back_on_non_json_model_output():
    original = "remove the background and keep the subject unchanged"
    engine = _FakePromptComposerEngine("I would rewrite that as a detailed prompt.")
    transformer = ImagePromptTransformer(engine)

    payload, receipt = transformer.transform(
        {"model": "axio-pro", "prompt": original},
        operation="editing",
    )

    assert payload["prompt"] == original
    assert receipt.applied is False
    assert receipt.reason == "text_prompt_composer_invalid"


def test_edit_parser_supports_mask_and_multiple_image_parts():
    body, content_type = _encode_multipart(
        {"model": "axio-terra", "prompt": "replace the sky", "stream": "false"},
        [
            ImagePart("image", "one.png", "image/png", b"one"),
            ImagePart("image[]", "two.png", "image/png", b"two"),
            ImagePart("mask", "mask.png", "image/png", b"mask"),
        ],
    )

    payload, files = parse_edit_payload(body, content_type)

    assert payload["prompt"] == "replace the sky"
    assert payload["stream"] is False
    assert [part.field_name for part in files] == ["image", "image[]", "mask"]
    assert [part.data for part in files] == [b"one", b"two", b"mask"]


def test_image_router_enforces_streaming_and_input_limits():
    fake = _FakeImageClient()
    profile = _image_profile(streaming=False, max_input_images=1)
    router = ImageRouter([profile], client=fake)

    with pytest.raises(ImageRequestError) as stream_error:
        router.generate({"model": "axio-fast", "prompt": "x", "stream": True})
    assert stream_error.value.code == "image_capability_unavailable"

    two_images = [
        ImagePart("image", "one.png", "image/png", b"one"),
        ImagePart("image", "two.png", "image/png", b"two"),
    ]
    with pytest.raises(ImageRequestError) as limit_error:
        ImageRouter([_image_profile(max_input_images=1)], client=fake).edit(
            {"model": "axio-terra", "prompt": "merge"},
            two_images,
        )
    assert limit_error.value.code == "image_input_limit_exceeded"
    assert not fake.generate_calls
    assert not fake.edit_calls


def test_image_router_returns_one_provider_result_without_text_merging():
    fake = _FakeImageClient()
    response, result, profile = ImageRouter([_image_profile()], client=fake).generate(
        {"model": "axio-pro", "prompt": "a red kite"}
    )

    assert response["model"] == "axio-pro"
    assert response["data"][0]["b64_json"] == "encoded-image"
    assert result.data[0]["b64_json"] == "encoded-image"
    assert profile.model == "gpt-image-2"
    assert len(fake.generate_calls) == 1


def test_image_provider_client_fails_over_to_next_key(monkeypatch):
    profile = _image_profile(runtime_keys=("key-a", "key-b"))
    captured_auth: list[str] = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"created": 1, "data": [{"b64_json": "ok"}]}'

    def fake_open(request, *, timeout):
        captured_auth.append(str(request.headers.get("Authorization") or ""))
        if len(captured_auth) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "unauthorized",
                {},
                io.BytesIO(b"secret upstream body"),
            )
        return Response()

    monkeypatch.setattr("axio_fusion_api.image_api._open_provider_url", fake_open)
    result = ImageProviderClient().generate(
        profile,
        {"model": "axio-fast", "prompt": "x"},
        timeout=5,
    )

    assert result.data == ({"b64_json": "ok"},)
    assert captured_auth == ["Bearer key-a", "Bearer key-b"]


def test_image_router_applies_hard_latency_gate():
    profile = _image_profile(p95_latency_ms=90_001)
    with pytest.raises(ImageRequestError) as error:
        ImageRouter([profile], client=_FakeImageClient()).generate(
            {"model": "axio-terra", "prompt": "x"}
        )
    assert error.value.status == 503
    assert error.value.code == "image_capability_unavailable"


def test_server_dispatches_images_without_invoking_text_fusion(monkeypatch):
    profile = _image_profile()
    fake = _FakeImageClient()
    monkeypatch.setattr(server, "ImageRouter", lambda profiles: ImageRouter(profiles, client=fake))

    status, headers, body = server.handle_request(
        method="POST",
        path="/v1/images/generations",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"model": "axio-fast", "prompt": "a red kite"}),
        engine=FusionEngine([profile]),
        record_runtime=False,
        record_trace=False,
    )

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["data"][0]["b64_json"] == "encoded-image"
    assert len(fake.generate_calls) == 1


def test_server_dispatches_multipart_image_edit(monkeypatch):
    profile = _image_profile()
    fake = _FakeImageClient()
    monkeypatch.setattr(server, "ImageRouter", lambda profiles: ImageRouter(profiles, client=fake))
    request_body, content_type = _encode_multipart(
        {"model": "axio-terra", "prompt": "replace the sky"},
        [ImagePart("image", "source.png", "image/png", b"png")],
    )

    status, headers, body = server.handle_request(
        method="POST",
        path="/v1/images/edits",
        headers={"Content-Type": content_type},
        body=request_body,
        engine=FusionEngine([profile]),
        record_runtime=False,
        record_trace=False,
    )

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["data"][0]["url"].endswith("result.png")
    assert len(fake.edit_calls) == 1
    assert fake.edit_calls[0][1][0].data == b"png"


def test_server_returns_sanitized_image_capability_error_for_unverified_model():
    status, _headers, body = server.handle_request(
        method="POST",
        path="/v1/images/generations",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"model": "axio-pro", "prompt": "a red kite"}),
        engine=FusionEngine([_image_profile(probe_status="not_run")]),
        record_runtime=False,
        record_trace=False,
    )

    payload = json.loads(body)
    assert status == 503
    assert payload["error"]["code"] == "image_capability_unavailable"
    assert payload["metadata"]["text_fusion_invoked"] is False
    assert "Bearer" not in body.decode("utf-8")
    assert "image-provider.invalid" not in body.decode("utf-8")


def test_http_server_delivers_image_event_before_provider_finishes(monkeypatch):
    class SlowImageClient:
        def __init__(self):
            self.first_event_emitted = threading.Event()
            self.release_completion = threading.Event()

        def generate(self, profile, payload, *, timeout=None, stream_observer=None):
            del profile, payload, timeout
            assert stream_observer is not None
            assert stream_observer(
                {"type": "image_generation.partial_image", "b64_json": "partial"}
            ) is True
            self.first_event_emitted.set()
            assert self.release_completion.wait(timeout=3)
            assert stream_observer(
                {"type": "image_generation.completed", "b64_json": "final"}
            ) is True
            return ImageProviderResult(
                data=({"b64_json": "final"},),
                created=1,
                stream_events=(),
                stream_protocol="sse",
            )

    client = SlowImageClient()
    profile = _image_profile()
    monkeypatch.setattr(
        server,
        "ImageRouter",
        lambda profiles: ImageRouter(profiles, client=client),
    )
    gateway = server.create_http_server(
        host="127.0.0.1",
        port=0,
        live=True,
        engine=FusionEngine([profile]),
        record_trace=False,
        record_runtime=False,
    )
    worker = threading.Thread(target=gateway.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        gateway.server_address[1],
        timeout=5,
    )
    observed = bytearray()
    try:
        connection.request(
            "POST",
            "/v1/images/generations",
            body=json.dumps(
                {
                    "model": "axio-fast",
                    "prompt": "a red kite",
                    "stream": True,
                    "partial_images": 1,
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Transfer-Encoding") == "chunked"
        assert response.getheader("Content-Length") is None
        deadline = time.monotonic() + 3
        while b"image_generation.partial_image" not in observed and time.monotonic() < deadline:
            chunk = response.read(1)
            if not chunk:
                break
            observed.extend(chunk)
        assert b"image_generation.partial_image" in observed
        assert client.first_event_emitted.wait(timeout=0.5)
        assert client.release_completion.is_set() is False

        client.release_completion.set()
        observed.extend(response.read())
        stream = observed.decode("utf-8")
        assert "image_generation.completed" in stream
        assert "data: [DONE]" in stream
    finally:
        client.release_completion.set()
        connection.close()
        gateway.shutdown()
        gateway.server_close()
        worker.join(timeout=5)

    assert worker.is_alive() is False


def test_server_returns_image_sse_with_allowlisted_event_types(monkeypatch):
    profile = _image_profile()
    fake = _FakeImageClient()
    monkeypatch.setattr(server, "ImageRouter", lambda profiles: ImageRouter(profiles, client=fake))

    status, headers, body = server.handle_request(
        method="POST",
        path="/v1/images/generations",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"model": "axio-terra", "prompt": "a red kite", "stream": True}),
        engine=FusionEngine([profile]),
        record_runtime=False,
        record_trace=False,
    )

    decoded = body.decode("utf-8")
    assert status == 200
    assert headers["Content-Type"].startswith("text/event-stream")
    assert "event: image_generation.partial_image" in decoded
    assert "event: image_generation.completed" in decoded
    assert "event: done" in decoded
    assert "provider_secret" not in decoded


def test_responses_image_generation_uses_responses_tool_wire_and_parses_output(monkeypatch):
    profile = _image_profile(
        transport="responses_image_generation",
        api_format="responses",
        runtime_keys=("response-key",),
    )
    captured: dict[str, object] = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"created_at": 7, "output": [{"type": "image_generation_call", "result": "encoded"}]}'

    def fake_open(request, *, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("axio_fusion_api.image_api._open_provider_url", fake_open)
    result = ImageProviderClient().generate(
        profile,
        {"model": "axio-pro", "prompt": "blue square"},
        timeout=5,
    )

    assert str(captured["url"]).endswith("/responses")
    wire = captured["body"]
    assert wire["model"] == "gpt-image-2"
    assert wire["input"] == "blue square"
    assert wire["tools"] == [{"type": "image_generation"}]
    assert result.created == 7
    assert result.data == ({"b64_json": "encoded"},)


def test_responses_image_stream_promotes_final_response_completed_event(monkeypatch):
    profile = _image_profile(
        transport="responses_image_generation",
        api_format="responses",
        runtime_keys=("response-key",),
    )

    class Response:
        headers = {"Content-Type": "text/event-stream"}
        lines = iter(
            [
                b'data: {"type":"response.completed","response":{"output":[{"type":"image_generation_call","result":"final-image"}]}}\n',
                b"\n",
                b"data: [DONE]\n",
                b"\n",
            ]
        )

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self):
            return next(self.lines, b"")

    captured: list[dict[str, object]] = []

    def fake_open(request, *, timeout):
        return Response()

    monkeypatch.setattr("axio_fusion_api.image_api._open_provider_url", fake_open)
    result = ImageProviderClient().generate(
        profile,
        {"model": "axio-pro", "prompt": "blue square", "stream": True},
        timeout=5,
        stream_observer=lambda event: captured.append(dict(event)) is None,
    )

    assert result.data == ({"b64_json": "final-image"},)
    assert captured == [{"type": "image_generation.completed", "b64_json": "final-image"}]


class _FakeImageProbeClient:
    def __init__(self):
        self.calls: list[str] = []

    def generate(self, profile, payload, *, timeout=None):
        self.calls.append("generation")
        return ImageProviderResult(
            data=({"b64_json": "generated"},),
            created=1,
            stream_events=({"type": "image_generation.completed", "b64_json": "generated"},)
            if payload.get("stream")
            else (),
            stream_protocol="sse" if payload.get("stream") else "",
            event_prefix="image_generation",
        )

    def edit(self, profile, fields, files, *, timeout=None):
        self.calls.append("editing")
        return ImageProviderResult(
            data=({"b64_json": "edited"},),
            created=2,
            stream_events=({"type": "image_edit.completed", "b64_json": "edited"},)
            if fields.get("stream")
            else (),
            stream_protocol="sse" if fields.get("stream") else "",
            event_prefix="image_edit",
        )


def test_image_probe_requires_live_evidence_and_probes_each_declared_operation():
    profile = _image_profile(capability_status="candidate", probe_status="not_run")
    fake = _FakeImageProbeClient()

    dry_run = probe_image_capabilities([profile], client=fake, live=False)
    assert dry_run["status_counts"] == {"skipped": 1}
    assert fake.calls == []

    live = probe_image_capabilities([profile], client=fake, live=True)
    assert live["status_counts"] == {"passed": 1}
    assert live["probes"][0]["all_declared_operations_passed"] is True
    assert {row["operation"] for row in live["probes"][0]["operation_results"]} == {
        "generation",
        "editing",
    }
    assert fake.calls == ["generation", "editing"]


def test_image_probe_redaction_removes_private_profile_names_and_prompt_text():
    profile = _image_profile(capability_status="candidate", probe_status="not_run")
    payload = probe_image_capabilities([profile], client=_FakeImageProbeClient(), live=True)
    redacted = redact_image_probe_artifact(payload)
    encoded = json.dumps(redacted, ensure_ascii=False)

    assert profile.provider not in encoded
    assert profile.model not in encoded
    assert "Capability control only" not in encoded
    assert redacted["probes"][0]["profile_id_sha256"]
    assert redacted["raw_image_bytes_persisted"] is False


def test_image_probe_bind_promotes_only_matching_endpoint_bound_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIO_TEST_IMAGE_BASE_URL", "https://image-provider.invalid/v1")
    profile = _image_profile(capability_status="candidate", probe_status="not_run")
    profile = ModelProfile(
        **{
            **profile.__dict__,
            "base_url_env": "AXIO_TEST_IMAGE_BASE_URL",
        }
    )
    source_path = Path(tmp_path) / "source.json"
    probe_path = Path(tmp_path) / "probe.json"
    source_path.write_text(
        json.dumps({"schema": "axio_fusion_api.registry.v1", "models": [profile.safe_dict()]}),
        encoding="utf-8",
    )
    probe = probe_image_capabilities([profile], client=_FakeImageProbeClient(), live=True)
    probe_path.write_text(json.dumps(probe), encoding="utf-8")

    bound = build_image_probe_bound_registry(registry_path=source_path, probe_path=probe_path)

    assert bound["status"] == "ready"
    promoted = bound["registry"]["models"][0]
    assert promoted["image_capabilities"]["status"] == "verified"
    assert promoted["image_probe_status"] == "passed"
    assert bound["receipt"]["promoted_profile_count"] == 1
