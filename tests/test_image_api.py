from __future__ import annotations

import io
import json
import urllib.error

import pytest

from axio_fusion_api import server
from axio_fusion_api.image_api import (
    ImagePart,
    ImageProviderClient,
    ImageProviderResult,
    ImageRequestError,
    ImageRouter,
    _encode_multipart,
    parse_edit_payload,
    parse_generation_payload,
)
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.schemas import ModelProfile


def _image_profile(
    *,
    probe_status: str = "passed",
    capability_status: str = "verified",
    streaming: bool = True,
    max_input_images: int = 1,
    p95_latency_ms: int | None = None,
    runtime_keys: tuple[str, ...] = (),
) -> ModelProfile:
    return ModelProfile(
        provider="image-provider",
        model="gpt-image-2",
        api_format="chat/completions",
        model_kind="image",
        image_probe_status=probe_status,
        image_capabilities={
            "status": capability_status,
            "transport": "images_api",
            "operations": ["generation", "editing"],
            "streaming": streaming,
            "max_input_images": max_input_images,
        },
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


def test_image_capability_requires_verified_capability_and_probe():
    assert _image_profile(capability_status="candidate").image_generation_eligible is False
    assert _image_profile(probe_status="not_run").image_generation_eligible is False
    assert _image_profile(probe_status="failed").image_generation_eligible is False


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
