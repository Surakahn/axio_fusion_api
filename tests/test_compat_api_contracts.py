from __future__ import annotations

import json
from dataclasses import replace

import pytest

from axio_fusion_api.compat import canonicalize_payload, render_response, render_stream_events
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.registry import normalize_profile
from axio_fusion_api.schemas import FusionResponse
from axio_fusion_api.server import (
    _prepare_incremental_stream_request,
    handle_request,
)
from axio_fusion_api.runtime import reset_runtime_state_for_tests


def _offline_engine() -> FusionEngine:
    return FusionEngine(
        [normalize_profile({"provider": "compat-fixture", "model": "compat-model"})],
        cache_enabled=False,
    )


def test_responses_continuation_exposes_previous_response_id_without_persisting_context():
    reset_runtime_state_for_tests()
    headers = {"x-api-key": "compat-continuation-tenant"}
    engine = _offline_engine()

    first_status, _, first_body = handle_request(
        method="POST",
        path="/v1/responses",
        headers=headers,
        body=json.dumps({"model": "axio-luna", "input": "first turn"}),
        engine=engine,
        record_trace=False,
        record_runtime=False,
    )
    first = json.loads(first_body.decode("utf-8"))
    second_status, _, second_body = handle_request(
        method="POST",
        path="/v1/responses",
        headers=headers,
        body=json.dumps(
            {
                "previous_response_id": first["id"],
                "input": "second turn",
            }
        ),
        engine=engine,
        record_trace=False,
        record_runtime=False,
    )
    second = json.loads(second_body.decode("utf-8"))
    serialized = json.dumps(second, ensure_ascii=False)

    assert first_status == 200
    assert second_status == 200
    assert first["previous_response_id"] is None
    assert second["previous_response_id"] == first["id"]
    assert "first turn" not in serialized
    assert "second turn" not in serialized
    assert second["metadata"]["response_continuation"]["available"] is True


def test_responses_stream_lifecycle_repeats_previous_response_id_from_internal_request_marker():
    request = canonicalize_payload(
        {
            "model": "axio-terra",
            "input": "follow-up",
        },
        api_format="responses",
    )
    request = replace(
        request,
        metadata={"_axio_previous_response_id": "fusion-prior-response"},
    )
    response = FusionResponse(
        text="done",
        request=request,
        route_plan={},
        response_id="fusion-current-response",
        created=1_700_000_000,
    )

    rendered = render_response(response, api_format="responses", responses_store=True)
    stream = render_stream_events(
        response,
        api_format="responses",
        responses_store=True,
    ).decode("utf-8")

    assert rendered["previous_response_id"] == "fusion-prior-response"
    assert '"previous_response_id":"fusion-prior-response"' in stream


def test_gemini_url_model_is_authoritative_and_body_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AXIO_FUSION_API_KEYS", raising=False)
    monkeypatch.delenv("AXIO_FUSION_REQUIRE_AUTH", raising=False)
    status, _, body = handle_request(
        method="POST",
        path="/v1beta/models/axio-luna:generateContent",
        body=json.dumps(
            {
                "model": "axio-sol",
                "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
            }
        ),
        engine=_offline_engine(),
        record_trace=False,
        record_runtime=False,
    )

    payload = json.loads(body.decode("utf-8"))
    assert status == 400
    assert payload["error"]["code"] == "gemini_model_path_mismatch"


def test_gemini_unknown_model_and_non_gemini_path_are_not_silently_downgraded():
    engine = _offline_engine()
    cases = [
        ("/v1beta/models/unknown-model:generateContent", "gemini_model_path_invalid"),
        ("/internal/models/axio-luna:generateContent", "gemini_model_path_invalid"),
    ]
    for path, expected_code in cases:
        status, _, body = handle_request(
            method="POST",
            path=path,
            body=json.dumps(
                {"contents": [{"role": "user", "parts": [{"text": "hello"}]}]}
            ),
            engine=engine,
            record_trace=False,
            record_runtime=False,
        )
        payload = json.loads(body.decode("utf-8"))
        assert status == 400
        assert payload["error"]["code"] == expected_code


def test_gemini_stream_preparation_applies_the_same_model_binding_contract():
    prepared, immediate = _prepare_incremental_stream_request(
        method="POST",
        path="/v1beta/models/axio-luna:streamGenerateContent",
        headers={},
        body=json.dumps(
            {
                "model": "axio-sol",
                "stream": True,
                "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
            }
        ),
        engine=_offline_engine(),
        live=False,
        record_runtime=False,
    )

    assert prepared is None
    assert immediate is not None
    status, _, body = immediate
    assert status == 400
    assert json.loads(body.decode("utf-8"))["error"]["code"] == "gemini_model_path_mismatch"
