from __future__ import annotations

import json
from dataclasses import replace
import urllib.error

import pytest

from axio_fusion_api import model_screening
from axio_fusion_api import providers as provider_module
from axio_fusion_api.calibration import build_registry_calibration
from axio_fusion_api.cli import main as fusion_cli_main
from axio_fusion_api.model_screening import (
    ModelScreeningError,
    build_prefusion_fusion_handoff,
    build_fusion_registry_from_screening,
    load_prefusion_research_agent_config,
    run_prefusion_model_screening,
    validate_prefusion_handoff,
    validate_prefusion_research_output,
)
from axio_fusion_api.providers import ProviderCompletion
from axio_fusion_api.providers import (
    discover_provider_profiles,
    reasoning_transport_probe_binding,
)
from axio_fusion_api.reasoning_reconciliation import (
    apply_reasoning_transport_reconciliation,
    build_reasoning_transport_reconciliation,
)
from axio_fusion_api.prefusion_ranking import (
    capability_axis_coverage,
    research_quality_score,
)
from axio_fusion_api.registry import (
    build_probe_bound_registry,
    build_registry_from_probe_artifacts,
    load_registry,
    normalize_profile,
    validate_prefusion_registry_handoff,
)
from axio_fusion_api.schemas import CAPABILITY_AXES, sha256_text


def _profile(provider: str, model: str, canonical: str, *, p50: int | None = 200) :
    return normalize_profile(
        {
            "provider": provider,
            "model": model,
            "canonical_model_id": canonical,
            "api_format": "chat",
            "base_url_env": f"{provider.upper().replace('-', '_')}_BASE_URL",
            "api_key_env": f"{provider.upper().replace('-', '_')}_API_KEY",
            "p50_latency_ms": p50,
            "p95_latency_ms": p50,
            "capabilities": {axis: 0.8 for axis in CAPABILITY_AXES},
            "health": "available",
            "enabled": True,
        }
    )


def _source_manifest() -> dict:
    return {
        "schema": model_screening.PREFUSION_SOURCE_MANIFEST_SCHEMA,
        "sources": [
            {
                "source_slot": "source_official",
                "content": "Official model documentation and an independent comparison snapshot.",
            }
        ],
    }


def _stream_evidence() -> dict:
    return {
        "stream_requested": True,
        "stream_observed": True,
        "stream_fallback_used": False,
        "stream_protocol": "sse",
        "stream_frame_count": 2,
        "strict_streaming_requested": True,
    }


def _stability_contract(samples: int = 3) -> dict:
    return {
        "schema": "axio_fusion_api.provider_probe_stability_contract.v1",
        "samples_per_profile": samples,
        "requires_all_samples_success": True,
        "requires_each_sample_latency_at_or_below_90_seconds": True,
        "requires_each_sample_strict_streaming": True,
    }


def _multi_sample_stability_evidence(samples: int = 3) -> dict:
    return {
        "stability_sample_count": samples,
        "stability_completed_sample_count": samples,
        "stability_success_count": samples,
        "stability_failure_count": 0,
        "stability_success_rate": 1.0,
        "all_samples_eligible": True,
        "sample_receipts_sha256": sha256_text(f"fixture-stability:{samples}"),
    }


class _FakeSourceResponse:
    def __init__(self, body: str, *, headers: dict[str, str] | None = None, url: str = ""):
        self._body = body.encode("utf-8")
        self.headers = headers or {}
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, _limit: int):
        return self._body

    def geturl(self):
        return self._url


class _FakeSourceOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_public_source_prefers_same_origin_markdown_alternate(monkeypatch):
    opener = _FakeSourceOpener(
        [
            _FakeSourceResponse(
                "<html><script>ignore this</script><body>navigation only</body></html>",
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Link": '</models/card.md>; rel="alternate"; type="text/markdown"',
                },
                url="https://example.test/models/card",
            ),
            _FakeSourceResponse(
                "# Model Card\n\nreasoning, agentic tasks, structured outputs",
                headers={"Content-Type": "text/markdown"},
                url="https://example.test/models/card.md",
            ),
        ]
    )
    monkeypatch.setattr(model_screening, "build_network_opener", lambda: opener)

    content, receipt = model_screening._fetch_public_source_document(
        "https://example.test/models/card",
        timeout=5,
    )

    assert "reasoning" in content
    assert "navigation only" not in content
    assert receipt["source_representation"] == "markdown_alternate"
    assert receipt["alternate_fetch_used"] is True
    assert receipt["alternate_fetch_status"] == "used"
    assert len(opener.requests) == 2
    assert opener.requests[1][0].full_url == "https://example.test/models/card.md"


def test_public_source_rejects_cross_origin_markdown_alternate(monkeypatch):
    opener = _FakeSourceOpener(
        [
            _FakeSourceResponse(
                "<body>safe initial evidence</body>",
                headers={
                    "Content-Type": "text/html",
                    "Link": '<https://other.test/card.md>; rel="alternate"; type="text/markdown"',
                },
                url="https://example.test/models/card",
            )
        ]
    )
    monkeypatch.setattr(model_screening, "build_network_opener", lambda: opener)

    content, receipt = model_screening._fetch_public_source_document(
        "https://example.test/models/card",
        timeout=5,
    )

    assert content == "safe initial evidence"
    assert receipt["source_representation"] == "html"
    assert receipt["alternate_fetch_attempted"] is True
    assert receipt["alternate_fetch_used"] is False
    assert receipt["alternate_fetch_status"] == "rejected"
    assert receipt["alternate_fetch_error_code"] == "prefusion_source_alternate_not_same_origin"
    assert len(opener.requests) == 1
    assert "other.test" not in opener.requests[0][0].full_url


def test_public_source_falls_back_to_html_when_markdown_alternate_fails(monkeypatch):
    opener = _FakeSourceOpener(
        [
            _FakeSourceResponse(
                "<body>fallback evidence</body>",
                headers={
                    "Content-Type": "text/html",
                    "Link": '</models/card.md>; rel="alternate"; type="text/markdown"',
                },
                url="https://example.test/models/card",
            ),
            urllib.error.URLError("alternate unavailable"),
        ]
    )
    monkeypatch.setattr(model_screening, "build_network_opener", lambda: opener)

    content, receipt = model_screening._fetch_public_source_document(
        "https://example.test/models/card",
        timeout=5,
    )

    assert content == "fallback evidence"
    assert receipt["source_representation"] == "html"
    assert receipt["alternate_fetch_attempted"] is True
    assert receipt["alternate_fetch_used"] is False
    assert receipt["alternate_fetch_status"] == "failed"
    assert receipt["alternate_fetch_error_code"] == "URLError"
    assert len(opener.requests) == 2


def test_public_source_accepts_direct_markdown_without_alternate(monkeypatch):
    opener = _FakeSourceOpener(
        [
            _FakeSourceResponse(
                "# Direct Card\n\nstructured outputs",
                headers={"Content-Type": "text/markdown; charset=utf-8"},
                url="https://example.test/models/card.md",
            )
        ]
    )
    monkeypatch.setattr(model_screening, "build_network_opener", lambda: opener)

    content, receipt = model_screening._fetch_public_source_document(
        "https://example.test/models/card.md",
        timeout=5,
    )

    assert content == "# Direct Card structured outputs"
    assert receipt["source_representation"] == "markdown"
    assert receipt["alternate_fetch_status"] == "not_needed"
    assert len(opener.requests) == 1


def _research_output(candidate_ids: list[str], *, confidence: float = 0.9, overall: float = 0.85) -> dict:
    rows = []
    for rank, candidate_id in enumerate(candidate_ids, start=1):
        rows.append(
            {
                "candidate_id": candidate_id,
                "rank": rank,
                "capability_summary": {
                    "overall": overall,
                    "axes": {axis: overall for axis in CAPABILITY_AXES},
                    "strengths": ["evidence-backed general capability"],
                    "limitations": ["remote channel latency can vary"],
                },
                "allowed_roles": [
                    "primary_solver",
                    "independent_solver",
                    "critic",
                    "judge",
                    "synthesizer",
                    "structured_extraction",
                ],
                "disallowed_roles": [],
                "confidence": confidence,
                "source_evidence_ids": ["source_official"],
                "rationale": "The public evidence supports this operational prior; it is not a benchmark claim.",
            }
        )
    return {
        "schema": model_screening.PREFUSION_RESEARCH_OUTPUT_SCHEMA,
        "ordered_models": rows,
    }


def _groups(profiles):
    focus = model_screening.load_prefusion_focus_manifest()
    return model_screening._build_candidate_groups(profiles, focus)


def test_research_json_parser_allows_only_one_outer_json_fence():
    payload = {"schema": "ok", "ordered_models": []}
    encoded = json.dumps(payload)
    assert model_screening._parse_strict_json_object(encoded) == payload
    assert model_screening._parse_strict_json_object(f"```json\n{encoded}\n```") == payload
    with pytest.raises(ModelScreeningError):
        model_screening._parse_strict_json_object(f"Here is the result:\n```json\n{encoded}\n```")
    with pytest.raises(ModelScreeningError):
        model_screening._parse_strict_json_object(f"{encoded}\nThanks")


def test_research_prompt_pins_standard_roles_and_repairs_invalid_role_names():
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    prompt = model_screening._build_research_prompt(
        groups,
        {
            "evidence": [
                {
                    "source_slot": "source_official",
                    "evidence_hash": sha256_text("source"),
                    "excerpt": "public model evidence",
                }
            ]
        },
        batch_index=1,
        batch_count=1,
        attempt=2,
        repair_reason="prefusion_research_output_role_invalid",
    )

    for role in model_screening._ROLE_NAMES_ORDERED:
        assert role in prompt
    assert "tool_worker" in prompt
    assert "fallback_solver" in prompt
    assert "replace it with one of the exact standard role names" in prompt
    assert "never invent a new role name" in prompt


def test_research_prompt_requires_fact_extraction_before_axis_and_role_mapping():
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    prompt = model_screening._build_research_prompt(
        groups,
        {
            "evidence": [
                {
                    "source_slot": "source_official",
                    "evidence_hash": sha256_text("source"),
                    "excerpt": (
                        "supports structured output, function calling, reasoning, "
                        "CritPt evaluation, and a 1M-token context window"
                    ),
                }
            ]
        },
    )

    assert model_screening.PREFUSION_RESEARCH_PROMPT_CONTRACT in prompt
    assert "(1) extract candidate-scoped public facts" in prompt
    assert "(2) map each fact" in prompt
    assert "Unreported is not the same as contradicted" in prompt
    assert "Tool calling is a structured-action signal" in prompt
    assert "CritPt" in prompt
    assert "Parameter count, GPU requirements, price" in prompt


def test_research_prompt_scopes_candidate_specific_source_evidence():
    profiles = [
        _profile("provider-a", "alpha", "alpha"),
        _profile("provider-b", "beta", "beta"),
    ]
    groups = _groups(profiles)
    source_pack = {
        "evidence": [
            {
                "source_slot": "source_shared",
                "evidence_hash": sha256_text("shared"),
                "model_references": [],
                "excerpt": "shared provider comparison evidence",
            },
            {
                "source_slot": "source_alpha",
                "evidence_hash": sha256_text("alpha"),
                "model_references": ["alpha"],
                "excerpt": "alpha-only model card evidence",
            },
            {
                "source_slot": "source_beta",
                "evidence_hash": sha256_text("beta"),
                "model_references": ["beta"],
                "excerpt": "beta-only model card evidence",
            },
        ]
    }

    prompt = model_screening._build_research_prompt(groups, source_pack)
    inventory_text = prompt.split("AUTHORITATIVE_CANDIDATE_INVENTORY\n", 1)[1]
    inventory_text, source_text = inventory_text.split(
        "\n\nUNTRUSTED_SOURCE_DATA\n", 1
    )
    inventory = json.loads(inventory_text)
    source_data = json.loads(source_text)
    rows = {row["model"]: row for row in inventory}

    assert [
        row["source_slot"] for row in rows["alpha"]["candidate_source_evidence"]
    ] == ["source_shared", "source_alpha"]
    assert [
        row["source_slot"] for row in rows["beta"]["candidate_source_evidence"]
    ] == ["source_shared", "source_beta"]

    packets = {
        row["candidate_id"]: [
            evidence["source_slot"] for evidence in row["evidence"]
        ]
        for row in source_data["candidate_source_evidence"]
    }
    assert packets[rows["alpha"]["candidate_id"]] == ["source_alpha"]
    assert packets[rows["beta"]["candidate_id"]] == ["source_beta"]
    assert [
        row["source_slot"] for row in source_data["shared_source_evidence"]
    ] == ["source_shared"]


def test_source_manifest_merges_focus_locators_without_persisting_secrets():
    focus = model_screening.load_prefusion_focus_manifest(
        {
            "schema": model_screening.PREFUSION_FOCUS_MANIFEST_SCHEMA,
            "ranking_prior_forbidden": True,
            "candidates": [
                {
                    "provider": "provider-a",
                    "model": "alpha",
                    "canonical_model_id": "alpha",
                    "source_locators": [
                        {
                            "url": "https://example.test/models/alpha",
                            "title": "Alpha card",
                        }
                    ],
                }
            ],
        }
    )
    manifest = model_screening.load_prefusion_source_manifest(
        {
            "schema": model_screening.PREFUSION_SOURCE_MANIFEST_SCHEMA,
            "sources": [
                {
                    "source_slot": "shared",
                    "content": "shared evidence",
                }
            ],
        },
        focus_manifest=focus,
    )
    locators = {
        row["url"]: row
        for row in manifest["sources"]
        if row.get("url")
    }
    assert "https://example.test/models/alpha" in locators
    assert locators["https://example.test/models/alpha"]["models"] == [
        "alpha"
    ]
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert "api_key" not in serialized
    assert "sk-test" not in serialized


def test_research_batches_isolate_candidate_specific_evidence():
    profiles = [
        _profile("provider-a", "alpha", "alpha"),
        _profile("provider-b", "beta", "beta"),
        _profile("provider-c", "gamma", "gamma"),
    ]
    groups = _groups(profiles)
    source_pack = {
        "evidence": [
            {
                "source_slot": "shared",
                "evidence_hash": sha256_text("shared"),
                "model_references": [],
                "excerpt": "shared evidence",
            },
            {
                "source_slot": "alpha_card",
                "evidence_hash": sha256_text("alpha"),
                "model_references": ["alpha"],
                "excerpt": "alpha card",
            },
            {
                "source_slot": "gamma_card",
                "evidence_hash": sha256_text("gamma"),
                "model_references": ["gamma"],
                "excerpt": "gamma card",
            },
        ]
    }
    batches = model_screening._build_research_batches(
        groups, source_pack=source_pack, batch_size=2
    )
    assert [[row["model"] for row in batch] for batch in batches] == [
        ["alpha"],
        ["beta"],
        ["gamma"],
    ]
    for batch in batches:
        projection = model_screening._research_source_projection(batch, source_pack)
        candidate_id = batch[0]["candidate_id"]
        visible_slots = {
            row["source_slot"] for row in projection["by_candidate"][candidate_id]
        }
        if batch[0]["model"] == "alpha":
            assert visible_slots == {"shared", "alpha_card"}
        elif batch[0]["model"] == "gamma":
            assert visible_slots == {"shared", "gamma_card"}
        else:
            assert visible_slots == {"shared"}


def test_empty_agent_role_lists_are_inferred_from_capability_evidence():
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    output = _research_output([str(groups[0]["candidate_id"])])
    output["ordered_models"][0]["allowed_roles"] = []
    output["ordered_models"][0]["disallowed_roles"] = []

    normalized = validate_prefusion_research_output(
        output,
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("evidence")},
    )
    row = normalized["ordered_models"][0]
    assert {
        "primary_solver",
        "independent_solver",
        "critic",
        "judge",
        "synthesizer",
    }.issubset(set(row["allowed_roles"]))
    assert row["disallowed_roles"] == []


def test_high_capability_prior_can_cover_fusion_roles_but_low_confidence_cannot():
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    high = validate_prefusion_research_output(
        _research_output([str(groups[0]["candidate_id"])], confidence=0.90, overall=0.85),
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("evidence")},
    )["ordered_models"][0]
    assert "primary_solver" in high["allowed_roles"]
    assert "judge" in high["allowed_roles"]
    assert "synthesizer" in high["allowed_roles"]

    low = validate_prefusion_research_output(
        _research_output([str(groups[0]["candidate_id"])], confidence=0.60, overall=0.85),
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("evidence")},
    )["ordered_models"][0]
    assert "primary_solver" not in low["allowed_roles"]
    assert "structured_extraction" in low["allowed_roles"]
    assert "judge" not in low["allowed_roles"]
    assert "synthesizer" not in low["allowed_roles"]
    assert "judge" in low["disallowed_roles"]
    assert "synthesizer" in low["disallowed_roles"]


def test_capability_admission_recovers_required_roles_from_conservative_agent_deny_list():
    """A conservative Agent contract must not block evidence-backed serving roles."""

    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    output = _research_output(
        [str(groups[0]["candidate_id"])], confidence=0.85, overall=0.64
    )
    row = output["ordered_models"][0]
    row["allowed_roles"] = ["domain_specialist", "short_verification"]
    row["disallowed_roles"] = [
        "critic",
        "independent_solver",
        "judge",
        "primary_solver",
        "structured_extraction",
        "synthesizer",
    ]
    row["capability_summary"]["axes"] = {
        axis: 0.80 for axis in CAPABILITY_AXES
    }

    normalized = validate_prefusion_research_output(
        output,
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("evidence")},
    )
    admitted = normalized["ordered_models"][0]
    assert {
        "primary_solver",
        "judge",
        "synthesizer",
    }.issubset(set(admitted["allowed_roles"]))
    assert admitted["disallowed_roles"] == []
    audit = admitted["role_admission"]
    assert audit["agent_role_lists_are_advisory"] is True
    assert audit["operator_focus_constraints_are_hard"] is True
    assert {
        "primary_solver",
        "judge",
        "synthesizer",
    }.issubset(set(audit["promoted_against_agent_deny"]))
    assert audit["agent_disallowed_roles"] == sorted(row["disallowed_roles"])


def test_operator_role_allowlist_and_denylist_are_hard_constraints():
    profile = _profile("provider-a", "alpha", "alpha")
    focus = model_screening.load_prefusion_focus_manifest(
        {
            "schema": model_screening.PREFUSION_FOCUS_MANIFEST_SCHEMA,
            "ranking_prior_forbidden": True,
            "candidates": [
                {
                    "provider": "provider-a",
                    "model": "alpha",
                    "canonical_model_id": "alpha",
                    "allowed_roles": ["primary_solver", "judge", "synthesizer"],
                    "disallowed_roles": ["critic"],
                }
            ],
        }
    )
    groups = model_screening._build_candidate_groups([profile], focus)
    normalized = validate_prefusion_research_output(
        _research_output([str(groups[0]["candidate_id"])], confidence=0.90, overall=0.85),
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("evidence")},
        focus_manifest=focus,
    )["ordered_models"][0]
    assert normalized["allowed_roles"] == ["judge", "primary_solver", "synthesizer"]
    assert "critic" in normalized["disallowed_roles"]


def _role_probe_row(
    profile,
    role: str,
    *,
    status: str = "available",
    http_status: int | None = None,
    output_sha256: str | None = None,
) -> dict:
    return {
        "schema": "axio_fusion_api.provider_role_probe.v1",
        "contract": "axio_fusion_api.provider_role_probe.fixed_control_packet.v1",
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "api_format": profile.api_format,
        "role": role,
        "status": status,
        "latency_ms": 120,
        "output_sha256": output_sha256 or sha256_text(f"role:{profile.profile_id}:{role}"),
        "role_output_contract_valid": status == "available",
        "role_streaming_contract_valid": status == "available",
        "error_type": "" if status == "available" else "ProviderExecutionError",
        "error_code": "" if status == "available" else "http_error",
        "http_status": http_status,
        "probe_mode": "live_role_control_packet",
        "live_probe_evidence": True,
        "stream_requested": status == "available",
        "stream_observed": status == "available",
        "stream_fallback_used": False,
        "stream_protocol": "sse" if status == "available" else "",
        "stream_frame_count": 2 if status == "available" else 0,
        "strict_streaming_requested": True,
        "latency_eligibility": {"eligible": status == "available"},
        "provider_request_count": 1,
        "provider_request_success_count": 1 if status == "available" else 0,
        "provider_request_failure_count": 0 if status == "available" else 1,
        "key_attempt_count": 1,
        "transport_attempt_count": 1,
        "retry_attempt_count": 0,
    }


def _role_profile(profile, *, allowed_roles=None, denied_roles=()):
    allowed = tuple(
        allowed_roles
        or ("critic", "judge", "synthesizer", "primary_solver")
    )
    admission = {
        "schema": "axio_fusion_api.prefusion_role_admission.v1",
        "effective_allowed_roles": list(allowed),
        "effective_disallowed_roles": list(denied_roles),
    }
    return replace(
        profile,
        screening_allowed_roles=allowed,
        screening_disallowed_roles=tuple(denied_roles),
        screening_role_admission=admission,
    )


def test_operational_role_probe_http_400_removes_only_critic_role():
    profile = _role_profile(_profile("provider-a", "alpha", "alpha"))
    role_probe = {
        "schema": "axio_fusion_api.provider_role_probe.v1",
        "contract": "axio_fusion_api.provider_role_probe.fixed_control_packet.v1",
        "status": "ready",
        "requested_roles": ["critic", "judge", "synthesizer"],
        "probes": [
            _role_probe_row(profile, "critic", status="failed", http_status=400),
            _role_probe_row(profile, "judge"),
            _role_probe_row(profile, "synthesizer"),
        ],
    }
    updated = model_screening._apply_operational_role_probe_metadata(
        [profile], role_probe
    )[0]
    assert "critic" not in updated.screening_allowed_roles
    assert "critic" in updated.screening_disallowed_roles
    assert {"judge", "synthesizer"}.issubset(
        set(updated.screening_allowed_roles)
    )
    receipt = updated.screening_role_admission["operational_role_probe"]
    assert receipt["failed_roles"] == ["critic"]
    assert receipt["passed_roles"] == ["judge", "synthesizer"]


def test_operational_role_probe_binds_profiles_without_role_targets():
    profile = _role_profile(
        _profile("provider-a", "narrow", "narrow"),
        allowed_roles=("structured_extraction",),
        denied_roles=("critic", "judge", "synthesizer"),
    )
    role_probe = {
        "schema": "axio_fusion_api.provider_role_probe.v1",
        "contract": "axio_fusion_api.provider_role_probe.fixed_control_packet.v1",
        "status": "ready",
        "requested_roles": ["critic", "judge", "synthesizer"],
        "probes": [],
    }

    updated = model_screening._apply_operational_role_probe_metadata(
        [profile], role_probe
    )[0]
    receipt = updated.screening_role_admission["operational_role_probe"]

    assert receipt["status"] == "ready"
    assert receipt["requested_roles"] == ["critic", "judge", "synthesizer"]
    assert receipt["tested_roles"] == []
    assert receipt["missing_roles"] == []
    assert receipt["probe_count"] == 0
    assert receipt["streaming_contract_verified"] is True


def test_prefusion_registry_binds_empty_role_receipts_for_unprobed_profiles(
    monkeypatch,
):
    profiles = [
        _profile("provider-a", "broad", "broad"),
        _profile("provider-b", "narrow", "narrow"),
    ]
    groups = _groups(profiles)
    research = _research_output([str(row["candidate_id"]) for row in groups])
    narrow_row = research["ordered_models"][1]
    narrow_row["capability_summary"] = {
        "overall": 0.30,
        "axes": {
            axis: 0.0 for axis in CAPABILITY_AXES
        },
        "strengths": ["narrow structured extraction evidence"],
        "limitations": ["insufficient evidence for high-impact roles"],
    }
    narrow_row["capability_summary"]["axes"]["structured_output"] = 0.60
    narrow_row["allowed_roles"] = ["structured_extraction"]
    narrow_row["disallowed_roles"] = [
        "critic",
        "judge",
        "synthesizer",
        "primary_solver",
        "independent_solver",
    ]
    narrow_row["confidence"] = 0.60
    requested_roles = ["critic", "judge", "synthesizer"]

    def fake_probe(probe_profiles, **_kwargs):
        physical_rows = [
            {
                "profile_id": item.profile_id,
                "provider": item.provider,
                "model": item.model,
                "status": "available",
                "latency_ms": 100,
                "output_sha256": sha256_text(f"physical:{item.profile_id}"),
                "probe_mode": "live",
                "live_probe_evidence": True,
                **_stream_evidence(),
                **_multi_sample_stability_evidence(3),
            }
            for item in probe_profiles
        ]
        role_rows = [
            _role_probe_row(item, role)
            for item in probe_profiles
            for role in requested_roles
            if role in item.screening_allowed_roles
        ]
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": physical_rows,
            "role_probe": {
                "schema": "axio_fusion_api.provider_role_probe.v1",
                "contract": "axio_fusion_api.provider_role_probe.fixed_control_packet.v1",
                "status": "ready",
                "requested_roles": requested_roles,
                "probes": role_rows,
                "benchmark_cases_or_labels_used": False,
            },
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "ready"
    registry = report["fusion_registry"]
    assert validate_prefusion_registry_handoff(registry, require_ready=True)[
        "valid"
    ] is True
    narrow_model = next(
        row for row in registry["models"] if row["model"] == "narrow"
    )
    assert (
        narrow_model["screening_role_admission"]["operational_role_probe"][
            "probe_count"
        ]
        == 0
    )


def test_logical_model_role_projection_unions_healthy_replicas():
    failed_replica = _role_profile(
        _profile("provider-a", "shared", "canonical-shared"),
        allowed_roles=("primary_solver", "judge"),
        denied_roles=("critic", "synthesizer"),
    )
    healthy_replica = _role_profile(
        _profile("provider-b", "shared", "canonical-shared"),
        allowed_roles=("primary_solver", "critic", "synthesizer"),
        denied_roles=("judge",),
    )
    logical = model_screening._available_logical_model_list(
        [failed_replica, healthy_replica]
    )
    assert len(logical) == 1
    assert {"critic", "judge", "synthesizer"}.issubset(
        set(logical[0]["allowed_roles"])
    )
    assert not set(logical[0]["allowed_roles"]).intersection(
        logical[0]["disallowed_roles"]
    )


def test_role_probe_redaction_drops_raw_control_text_and_provider_output():
    payload = {
        "role_probe": {
            "requested_roles": ["critic"],
            "probes": [
                {
                    "profile_id": "provider-a/alpha",
                    "provider": "provider-a",
                    "model": "alpha",
                    "role": "critic",
                    "status": "available",
                    "prompt": "UNIQUE_ROLE_PROMPT",
                    "output": "UNIQUE_ROLE_OUTPUT",
                    "output_sha256": sha256_text("UNIQUE_ROLE_OUTPUT"),
                    "stream_requested": True,
                    "stream_observed": True,
                    "stream_fallback_used": False,
                    "stream_protocol": "sse",
                    "stream_frame_count": 2,
                    "strict_streaming_requested": True,
                }
            ],
        }
    }
    redacted = provider_module.redact_provider_probe_artifact(payload)
    serialized = json.dumps(redacted, ensure_ascii=False)
    assert "UNIQUE_ROLE_PROMPT" not in serialized
    assert "UNIQUE_ROLE_OUTPUT" not in serialized
    assert "provider-a" not in serialized
    assert redacted["role_probe"]["raw_role_probe_prompt_persisted"] is False


def test_role_probe_binding_is_hash_bound_and_rejects_manual_role_promotion(monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    research = _research_output([str(groups[0]["candidate_id"])])
    requested_roles = ["critic", "judge", "synthesizer"]

    def fake_probe(probe_profiles, **_kwargs):
        physical_rows = [
            {
                "profile_id": item.profile_id,
                "provider": item.provider,
                "model": item.model,
                "status": "available",
                "latency_ms": 100,
                "output_sha256": sha256_text("physical-probe"),
                "probe_mode": "live",
                "live_probe_evidence": True,
                **_stream_evidence(),
                **_multi_sample_stability_evidence(3),
            }
            for item in probe_profiles
        ]
        role_rows = []
        for item in probe_profiles:
            role_rows.extend(
                [
                    _role_probe_row(item, "critic", status="failed", http_status=400),
                    _role_probe_row(item, "judge"),
                    _role_probe_row(item, "synthesizer"),
                ]
            )
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": physical_rows,
            "role_probe": {
                "schema": "axio_fusion_api.provider_role_probe.v1",
                "contract": "axio_fusion_api.provider_role_probe.fixed_control_packet.v1",
                "status": "ready",
                "requested_roles": requested_roles,
                "probes": role_rows,
                "benchmark_cases_or_labels_used": False,
            },
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )
    assert report["status"] == "ready"
    registry = report["fusion_registry"]
    assert registry["prefusion_screening"]["role_probe_required"] is True
    assert validate_prefusion_registry_handoff(
        registry, require_ready=True
    )["valid"] is True

    tampered = json.loads(json.dumps(registry))
    tampered["models"][0]["screening_allowed_roles"].append("critic")
    validation = validate_prefusion_registry_handoff(tampered, require_ready=True)
    assert validation["valid"] is False
    assert "prefusion_registry_role_probe_allowed_roles_mismatch" in validation[
        "reason_codes"
    ]


class _FakeClient:
    def __init__(self, output: str = ""):
        self.output = output
        self.probe_calls: list[str] = []
        self.research_calls = 0

    def complete_turn(self, profile, request, *, prompt, system, timeout):
        self.research_calls += 1
        return ProviderCompletion(self.output)

    def complete(self, profile, request, *, prompt, system, timeout):
        self.probe_calls.append(profile.profile_id)
        return "AXIO_PROBE_OK"


class _BatchResearchClient:
    """Return a strict ranking for the candidate ids embedded in each prompt."""

    def __init__(self, *, fail_on_call: int | None = None):
        self.calls: list[dict[str, object]] = []
        self.fail_on_call = fail_on_call

    def complete_turn(self, profile, request, *, prompt, system, timeout):
        del profile, request, system, timeout
        self.calls.append({"prompt": prompt})
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            return ProviderCompletion("not-json")
        marker = "AUTHORITATIVE_CANDIDATE_INVENTORY\n"
        inventory = prompt.split(marker, 1)[1].split("\n\nUNTRUSTED_SOURCE_DATA", 1)[0]
        rows = json.loads(inventory)
        candidate_ids = [str(row["candidate_id"]) for row in rows]
        return ProviderCompletion(json.dumps(_research_output(candidate_ids)))


class _RetryingBatchResearchClient(_BatchResearchClient):
    """Emit one malformed response, then satisfy the strict contract."""

    def __init__(self):
        super().__init__()
        self.failed_candidate_sets: set[str] = set()

    def complete_turn(self, profile, request, *, prompt, system, timeout):
        marker = "AUTHORITATIVE_CANDIDATE_INVENTORY\n"
        inventory = prompt.split(marker, 1)[1].split("\n\nUNTRUSTED_SOURCE_DATA", 1)[0]
        rows = json.loads(inventory)
        candidate_ids = [str(row["candidate_id"]) for row in rows]
        key = ",".join(candidate_ids)
        self.calls.append({"prompt": prompt})
        if key not in self.failed_candidate_sets:
            self.failed_candidate_sets.add(key)
            return ProviderCompletion("not-json")
        return ProviderCompletion(json.dumps(_research_output(candidate_ids)))


def test_research_output_requires_complete_contiguous_ranking_and_real_evidence():
    profiles = [_profile("provider-a", "alpha", "alpha"), _profile("provider-b", "beta", "beta")]
    groups = _groups(profiles)
    candidate_ids = [str(row["candidate_id"]) for row in groups]
    valid = _research_output(candidate_ids)

    normalized = validate_prefusion_research_output(
        valid,
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("actual-evidence")},
    )
    assert normalized["ordered_models"][0]["source_evidence_hashes"] == [
        sha256_text("actual-evidence")
    ]

    cases = []
    missing = _research_output(candidate_ids[:-1])
    cases.append(missing)
    duplicate = _research_output(candidate_ids)
    duplicate["ordered_models"][1]["candidate_id"] = candidate_ids[0]
    cases.append(duplicate)
    unknown = _research_output(candidate_ids)
    unknown["ordered_models"][0]["candidate_id"] = "candidate_unknown"
    cases.append(unknown)
    non_contiguous = _research_output(candidate_ids)
    non_contiguous["ordered_models"][0]["rank"] = 2
    cases.append(non_contiguous)
    extra_key = _research_output(candidate_ids)
    extra_key["unexpected"] = True
    cases.append(extra_key)

    for invalid in cases:
        with pytest.raises(ModelScreeningError):
            validate_prefusion_research_output(
                invalid,
                groups=groups,
                source_slots=["source_official"],
                source_evidence={"source_official": sha256_text("actual-evidence")},
            )


def test_research_output_requires_capability_axis_coverage_for_broad_priors():
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    candidate_id = str(groups[0]["candidate_id"])

    no_axes = _research_output([candidate_id], overall=0.85)
    no_axes["ordered_models"][0]["capability_summary"]["axes"] = {
        axis: 0.0 for axis in CAPABILITY_AXES
    }
    no_axes_coverage = capability_axis_coverage(
        no_axes["ordered_models"][0]["capability_summary"]
    )
    assert no_axes_coverage["eligible"] is False
    assert no_axes_coverage["required_nonzero_axis_count"] == 3
    with pytest.raises(ModelScreeningError, match="capability_axis_coverage"):
        validate_prefusion_research_output(
            no_axes,
            groups=groups,
            source_slots=["source_official"],
            source_evidence={"source_official": sha256_text("actual-evidence")},
        )

    one_axis = _research_output([candidate_id], overall=0.80)
    one_axis["ordered_models"][0]["capability_summary"]["axes"] = {
        axis: (0.80 if axis == "code" else 0.0) for axis in CAPABILITY_AXES
    }
    coverage = capability_axis_coverage(
        one_axis["ordered_models"][0]["capability_summary"]
    )
    assert coverage["eligible"] is False
    assert coverage["reason_code"] == "prefusion_broad_capability_axis_coverage_insufficient"
    assert coverage["required_nonzero_axis_count"] == 3
    with pytest.raises(ModelScreeningError, match="capability_axis_coverage"):
        validate_prefusion_research_output(
            one_axis,
            groups=groups,
            source_slots=["source_official"],
            source_evidence={"source_official": sha256_text("actual-evidence")},
        )

    two_axes = _research_output([candidate_id], overall=0.80)
    two_axes["ordered_models"][0]["capability_summary"]["axes"] = {
        axis: (0.80 if axis in {"code", "math"} else 0.0)
        for axis in CAPABILITY_AXES
    }
    coverage = capability_axis_coverage(
        two_axes["ordered_models"][0]["capability_summary"]
    )
    assert coverage["eligible"] is False
    assert coverage["required_nonzero_axis_count"] == 3

    three_axes = _research_output([candidate_id], overall=0.80)
    three_axes["ordered_models"][0]["capability_summary"]["axes"] = {
        axis: (0.80 if axis in {"code", "math", "logic"} else 0.0)
        for axis in CAPABILITY_AXES
    }
    coverage = capability_axis_coverage(
        three_axes["ordered_models"][0]["capability_summary"]
    )
    assert coverage["eligible"] is True
    assert coverage["required_nonzero_axis_count"] == 3


def test_narrow_research_prior_can_pass_with_one_axis_and_is_role_limited():
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    candidate_id = str(groups[0]["candidate_id"])
    narrow = _research_output([candidate_id], overall=0.50)
    narrow["ordered_models"][0]["capability_summary"]["axes"] = {
        axis: (0.75 if axis == "code" else 0.0) for axis in CAPABILITY_AXES
    }

    normalized = validate_prefusion_research_output(
        narrow,
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": sha256_text("actual-evidence")},
    )
    row = normalized["ordered_models"][0]
    assert row["capability_axis_coverage"]["eligible"] is True
    assert row["capability_axis_coverage"]["nonzero_axis_count"] == 1
    assert "judge" in row["disallowed_roles"]
    assert "synthesizer" in row["disallowed_roles"]


def test_research_batch_merge_uses_quality_score_not_overall_only():
    profiles = [
        _profile("provider-a", "alpha", "alpha"),
        _profile("provider-b", "beta", "beta"),
    ]
    groups = _groups(profiles)

    class QualityAwareClient(_BatchResearchClient):
        def complete_turn(self, profile, request, *, prompt, system, timeout):
            del profile, request, system, timeout
            self.calls.append({"prompt": prompt})
            marker = "AUTHORITATIVE_CANDIDATE_INVENTORY\n"
            inventory = prompt.split(marker, 1)[1].split(
                "\n\nUNTRUSTED_SOURCE_DATA", 1
            )[0]
            candidate_ids = [
                str(row["candidate_id"]) for row in json.loads(inventory)
            ]
            rows = []
            for rank, candidate_id in enumerate(candidate_ids, start=1):
                # Beta has a slightly lower overall prior but broader, stronger
                # evidence. It must win the deterministic quality merge.
                overall = 0.80 if candidate_id == "candidate_0001" else 0.79
                axis_value = 0.80 if candidate_id == "candidate_0001" else 1.0
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "rank": rank,
                        "capability_summary": {
                            "overall": overall,
                            "axes": {axis: axis_value for axis in CAPABILITY_AXES},
                            "strengths": ["evidence-backed capability"],
                            "limitations": ["prior is not benchmark evidence"],
                        },
                        "allowed_roles": ["primary_solver"],
                        "disallowed_roles": ["judge", "synthesizer"],
                        "confidence": 0.90,
                        "source_evidence_ids": ["source_official"],
                        "rationale": "The public evidence supports this operational prior.",
                    }
                )
            return ProviderCompletion(
                json.dumps(
                    {
                        "schema": model_screening.PREFUSION_RESEARCH_OUTPUT_SCHEMA,
                        "ordered_models": rows,
                    }
                )
            )

    ranking, receipt = model_screening._run_research_agent_batches(
        _profile("nvidia", "researcher", "researcher"),
        groups=groups,
        source_pack={
            "receipts": [
                {
                    "source_slot": "source_official",
                    "status": "inline_source_ready",
                    "evidence_hash": sha256_text("source"),
                }
            ],
            "evidence": [],
        },
        timeout=10.0,
        client=QualityAwareClient(),
        focus_manifest=model_screening.load_prefusion_focus_manifest(),
        batch_size=2,
        max_workers=1,
        merge_strategy=model_screening._RESEARCH_MERGE_STRATEGY,
    )

    assert receipt["status"] == "validated"
    assert [row["candidate_id"] for row in ranking["ordered_models"]] == [
        "candidate_0002",
        "candidate_0001",
    ]
    assert research_quality_score(
        ranking["ordered_models"][0]["capability_summary"]
    ) > research_quality_score(ranking["ordered_models"][1]["capability_summary"])


def test_research_batches_cover_full_inventory_and_merge_deterministically():
    profiles = [
        _profile("provider-a", f"model-{index:02d}", f"model-{index:02d}")
        for index in range(5)
    ]
    groups = _groups(profiles)
    client = _BatchResearchClient()
    ranking, receipt = model_screening._run_research_agent_batches(
        _profile("nvidia", "researcher", "researcher"),
        groups=groups,
        source_pack={
            "receipts": [
                {
                    "source_slot": "source_official",
                    "status": "inline_source_ready",
                    "evidence_hash": sha256_text("source"),
                }
            ],
            "evidence": [],
        },
        timeout=10.0,
        client=client,
        focus_manifest=model_screening.load_prefusion_focus_manifest(),
        batch_size=2,
        max_workers=2,
        merge_strategy=model_screening._RESEARCH_MERGE_STRATEGY,
    )
    assert len(client.calls) == 3
    assert receipt["status"] == "validated"
    assert receipt["batch_count"] == 3
    assert [row["candidate_id"] for row in ranking["ordered_models"]] == [
        f"candidate_{index:04d}" for index in range(1, 6)
    ]
    assert [row["rank"] for row in ranking["ordered_models"]] == list(range(1, 6))
    assert all(item["status"] == "validated" for item in receipt["batch_results"])
    assert receipt["aggregate_output_sha256"]


def test_research_batch_retries_once_then_merges_only_validated_output():
    profiles = [
        _profile("provider-a", f"model-{index:02d}", f"model-{index:02d}")
        for index in range(3)
    ]
    groups = _groups(profiles)
    client = _RetryingBatchResearchClient()
    ranking, receipt = model_screening._run_research_agent_batches(
        _profile("nvidia", "researcher", "researcher"),
        groups=groups,
        source_pack={
            "receipts": [
                {
                    "source_slot": "source_official",
                    "status": "inline_source_ready",
                    "evidence_hash": sha256_text("source"),
                }
            ],
            "evidence": [],
        },
        timeout=10.0,
        client=client,
        focus_manifest=model_screening.load_prefusion_focus_manifest(),
        batch_size=2,
        max_workers=2,
        merge_strategy=model_screening._RESEARCH_MERGE_STRATEGY,
    )
    assert len(client.calls) == 4
    assert receipt["status"] == "validated"
    assert all(item["status"] == "validated" for item in receipt["batch_results"])
    assert all(item["retry_used"] is True for item in receipt["batch_results"])
    assert all(len(item["attempts"]) == 2 for item in receipt["batch_results"])
    assert [row["rank"] for row in ranking["ordered_models"]] == [1, 2, 3]


def test_any_failed_research_batch_blocks_before_provider_probe(monkeypatch):
    profiles = [
        _profile("provider-a", f"model-{index:02d}", f"model-{index:02d}")
        for index in range(4)
    ]
    research_profile = _profile(
        "nvidia", "openai/gpt-oss-120b", "openai/gpt-oss-120b"
    )
    class AlwaysMalformedClient(_BatchResearchClient):
        def complete_turn(self, profile, request, *, prompt, system, timeout):
            self.calls.append({"prompt": prompt})
            return ProviderCompletion("not-json")

    client = AlwaysMalformedClient()
    probe_called = False

    def unexpected_probe(*_args, **_kwargs):
        nonlocal probe_called
        probe_called = True
        raise AssertionError("failed research shard must block provider probing")

    monkeypatch.setattr(model_screening, "probe_provider_models", unexpected_probe)
    monkeypatch.setenv("NVIDIA_API_KEY", "fixture-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://nvidia.example/v1")
    report = run_prefusion_model_screening(
        profiles=[*profiles, research_profile],
        source_manifest=_source_manifest(),
        live=True,
        research_client=client,
        provider_client=client,
        research_batch_size=2,
        research_max_workers=2,
        min_available_models=1,
    )
    assert report["status"] == "blocked"
    assert report["research_ranking"]["status"] == "blocked"
    assert report["research_ranking"]["research_receipt"]["batch_count"] == 3
    assert any(
        item["status"] == "failed"
        for item in report["research_ranking"]["research_receipt"]["batch_results"]
    )
    assert any(
        item.get("attempt_count") == 2
        and item.get("retry_used") is True
        for item in report["research_ranking"]["research_receipt"]["batch_results"]
    )
    assert probe_called is False


def test_configured_provider_discovery_returns_process_local_profiles(monkeypatch):
    """The discovery inventory must be handed to screening without persistence."""

    profile_seed = _profile("provider-a", "probe-seed", "probe-seed")

    def fake_list_models(profile, *, timeout):
        del timeout
        return {
            "provider": profile.provider,
            "status": "ok",
            "network_calls_performed": True,
            "model_ids": ["discovered-alpha", "discovered-beta"],
        }

    monkeypatch.setattr("axio_fusion_api.providers._provider_seed_profiles", lambda selected: [profile_seed])
    monkeypatch.setattr("axio_fusion_api.providers.provider_discovery_priors_from_env", lambda selected: {})
    monkeypatch.setattr("axio_fusion_api.providers.provider_configured_profiles_from_env", lambda selected: [])
    monkeypatch.setattr("axio_fusion_api.providers._safe_list_models", fake_list_models)

    discovery = discover_provider_profiles(providers=["provider-a"], live=True)

    assert discovery["status"] == "ready"
    assert discovery["discovery_complete"] is True
    assert [profile.model for profile in discovery["profiles"]] == [
        "discovered-alpha",
        "discovered-beta",
    ]
    assert discovery["profile_count"] == 2
    assert discovery["provider_reports"][0]["model_ids"] == [
        "discovered-alpha",
        "discovered-beta",
    ]


def test_incomplete_provider_discovery_blocks_research_and_stream_probe(monkeypatch):
    profile = _profile("provider-a", "discovered-alpha", "discovered-alpha")
    research_calls = 0
    probe_calls = 0

    def unexpected_research(*args, **kwargs):
        nonlocal research_calls
        research_calls += 1
        raise AssertionError("incomplete discovery must block the research Agent")

    def unexpected_probe(*args, **kwargs):
        nonlocal probe_calls
        probe_calls += 1
        raise AssertionError("incomplete discovery must block streaming probes")

    monkeypatch.setattr(model_screening, "_auto_discovery_configuration_present", lambda: True)
    monkeypatch.setattr(
        model_screening,
        "discover_provider_profiles",
        lambda **kwargs: {
            "schema": "axio_fusion_api.prefusion_provider_discovery.v1",
            "status": "blocked",
            "mode": "live",
            "discovery_complete": False,
            "blockers": ["prefusion_provider_model_discovery_failed"],
            "profiles": [profile],
            "provider_reports": [],
        },
    )
    monkeypatch.setattr(model_screening, "_run_research_agent_batches", unexpected_research)
    monkeypatch.setattr(model_screening, "probe_provider_models", unexpected_probe)

    report = run_prefusion_model_screening(
        source_manifest=_source_manifest(),
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "blocked"
    assert "prefusion_provider_model_discovery_failed" in report["blockers"]
    assert report["research_ranking"]["research_receipt"]["status"] == "not_run"
    assert report["streaming_probe"]["network_calls_performed"] is False
    assert research_calls == 0
    assert probe_calls == 0


def test_redacted_prefusion_discovery_hashes_model_ids(monkeypatch):
    profile = _profile("provider-a", "secret-model", "secret-model")
    monkeypatch.setattr(model_screening, "_auto_discovery_configuration_present", lambda: True)
    monkeypatch.setattr(
        model_screening,
        "discover_provider_profiles",
        lambda **kwargs: {
            "schema": "axio_fusion_api.prefusion_provider_discovery.v1",
            "status": "blocked",
            "mode": "live",
            "discovery_complete": False,
            "blockers": ["prefusion_provider_model_discovery_failed"],
            "profiles": [profile],
            "provider_reports": [
                {
                    "provider": "private-provider",
                    "status": "ok",
                    "model_ids": ["secret-model"],
                }
            ],
        },
    )

    report = run_prefusion_model_screening(
        source_manifest=_source_manifest(),
        live=True,
        redact_provider_identifiers=True,
    )
    serialized = json.dumps(report, ensure_ascii=False)

    assert "private-provider" not in serialized
    assert "secret-model" not in serialized
    assert report["provider_identifier_redaction"]["mode"] == "sha256_aliases"
    assert report["raw_provider_model_ids_persisted"] is False
    provider_report = report["provider_discovery"]["provider_reports"][0]
    assert provider_report["model_ids"] == [f"sha256:{sha256_text('secret-model')}" ]
    assert provider_report["raw_provider_model_ids_persisted"] is False


def test_same_canonical_model_is_one_rank_but_keeps_physical_replicas():
    profiles = [
        _profile("provider-a", "shared-alias", "canonical-shared"),
        _profile("provider-b", "shared-alias", "canonical-shared"),
        _profile("provider-c", "other", "canonical-other"),
    ]
    groups = _groups(profiles)
    shared = next(row for row in groups if row["canonical_model_id"] == "canonical-shared")
    assert len(groups) == 2
    assert len(shared["replicas"]) == 2
    output = _research_output([str(row["candidate_id"]) for row in groups])
    normalized = validate_prefusion_research_output(
        output,
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": "evidence-hash"},
    )
    shared_rank = next(
        row for row in normalized["ordered_models"] if row["canonical_model_id"] == "canonical-shared"
    )
    assert shared_rank["replica_count"] == 2


def test_screening_binds_capability_prior_and_logical_available_model_list(monkeypatch, tmp_path):
    profiles = [
        _profile("provider-a", "shared-alias", "canonical-shared", p50=220),
        _profile("provider-b", "shared-alias", "canonical-shared", p50=310),
        _profile("provider-c", "other", "canonical-other", p50=480),
    ]
    groups = _groups(profiles)
    research = _research_output([str(row["candidate_id"]) for row in groups])
    shared_candidate = next(
        row
        for row in groups
        if row["canonical_model_id"] == "canonical-shared"
    )["candidate_id"]
    shared_row = next(
        row for row in research["ordered_models"] if row["candidate_id"] == shared_candidate
    )
    shared_row["capability_summary"] = {
        "overall": 0.93,
        "axes": {axis: 0.93 for axis in CAPABILITY_AXES},
        "strengths": ["independent public evidence supports a strong operational prior"],
        "limitations": ["the prior is not a benchmark result"],
    }
    for env in (
        "PROVIDER_A_API_KEY",
        "PROVIDER_B_API_KEY",
        "PROVIDER_C_API_KEY",
    ):
        monkeypatch.setenv(env, "fixture-key")
    for provider in ("provider-a", "provider-b", "provider-c"):
        monkeypatch.setenv(
            f"{provider.upper().replace('-', '_')}_BASE_URL",
            f"https://{provider}.example/v1",
        )

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profile.profile_id,
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": "available",
                    "latency_ms": profile.p50_latency_ms,
                        "output_sha256": sha256_text(f"probe:{profile.profile_id}"),
                        "probe_mode": "live",
                        "live_probe_evidence": True,
                        **_stream_evidence(),
                }
                for profile in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "ready"
    shared_profiles = [
        row
        for row in report["fusion_registry"]["models"]
        if row["canonical_model_id"] == "canonical-shared"
    ]
    assert len(shared_profiles) == 2
    assert all(row["screening_capability_overall"] == 0.93 for row in shared_profiles)
    assert all(
        row["screening_capability_axes"]["math"] == 0.93
        for row in shared_profiles
    )

    logical = report["fusion_registry"]["prefusion_screening"]["available_model_list"]
    assert report["fusion_registry"]["available_logical_model_count"] == 2
    assert len(logical) == 2
    shared_logical = next(
        row for row in logical if row["canonical_model_id"] == "canonical-shared"
    )
    expected_shared_rank = next(
        row["rank"]
        for row in research["ordered_models"]
        if row["candidate_id"] == shared_candidate
    )
    assert shared_logical["rank"] == expected_shared_rank
    assert shared_logical["replica_count"] == 2
    assert len(shared_logical["replica_profile_id_sha256s"]) == 2
    assert shared_logical["replicas_are_failover_not_independent_votes"] is True

    catalog = report["model_catalog"]
    assert catalog["schema"] == model_screening.PREFUSION_MODEL_CATALOG_SCHEMA
    assert catalog["status"] == "ready"
    assert catalog["inventory"]["complete"] is True
    assert catalog["inventory"]["ranking_complete"] is True
    assert catalog["inventory"]["logical_candidate_count"] == 2
    assert len(catalog["ranking"]["ordered_models"]) == 2
    assert catalog["available_model_list"] == logical

    registry_path = tmp_path / "generated-registry.json"
    registry_path.write_text(
        json.dumps(report["fusion_registry"]),
        encoding="utf-8",
    )
    loaded = [
        profile
        for profile in model_screening.load_registry(registry_path)
        if profile.canonical_model_id == "canonical-shared"
    ]
    assert len(loaded) == 2
    assert all(profile.screening_capability("science_knowledge") == 0.93 for profile in loaded)


def test_prefusion_calibration_preserves_loadable_handoff_and_updates_tool_metadata(
    monkeypatch,
    tmp_path,
):
    profile = _profile("provider-a", "alpha", "alpha", p50=220)
    groups = _groups([profile])
    research = _research_output([str(groups[0]["candidate_id"])])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 220,
                    "output_sha256": sha256_text(f"prefusion:{item.profile_id}"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )
    assert report["status"] == "ready"
    source_registry = report["fusion_registry"]
    assert validate_prefusion_registry_handoff(source_registry)["valid"] is True

    source_path = tmp_path / "prefusion-registry.json"
    source_path.write_text(json.dumps(source_registry), encoding="utf-8")
    calibration_probe_path = tmp_path / "calibration-probe.json"
    calibration_probe_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_probe.v1",
                "probes": [
                    {
                        "profile_id": profile.profile_id,
                        "provider": profile.provider,
                        "model": profile.model,
                        "status": "failed",
                        "latency_ms": 95000,
                    },
                    {
                        "profile_id": profile.profile_id,
                        "provider": profile.provider,
                        "model": profile.model,
                        "probe_kind": "tool_call",
                        "status": "tool_call_supported",
                        "latency_ms": 120,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    calibration = build_registry_calibration(
        registry_path=source_path,
        probe_paths=[calibration_probe_path],
    )
    updated = calibration["updated_registry"]
    updated_model = updated["models"][0]

    assert calibration["source_registry_is_prefusion"] is True
    assert calibration["source_prefusion_handoff_validation"]["valid"] is True
    assert calibration["application_contract"]["safe_to_write_registry"] is True
    assert updated["generated_from_prefusion_screening"] is True
    assert updated["binding_status"] == source_registry["binding_status"]
    assert updated["prefusion_screening"] == source_registry["prefusion_screening"]
    assert updated["prefusion_model_catalog"] == source_registry["prefusion_model_catalog"]
    assert updated["research_ranking"] == source_registry["research_ranking"]
    assert updated["operational_ranking"] == source_registry["operational_ranking"]
    # A later failed observation cannot rewrite the hash-bound serving state;
    # the successful native tool probe is still reflected in model metadata.
    assert updated_model["health"] == "available"
    assert updated_model["supports_tools"] is True
    assert updated_model["tool_capability"] == "proven"
    assert updated["generation_contract"][
        "calibration_does_not_rewrite_prefusion_stream_admission"
    ] is True
    assert validate_prefusion_registry_handoff(updated)["valid"] is True

    updated_path = tmp_path / "calibrated-prefusion-registry.json"
    updated_path.write_text(json.dumps(updated), encoding="utf-8")
    loaded = load_registry(updated_path, require_prefusion=True)
    assert len(loaded) == 1
    assert loaded[0].supports_tools is True


def test_reasoning_reconciliation_preserves_loadable_prefusion_handoff(monkeypatch, tmp_path):
    profile = replace(
        _profile("provider-a", "alpha", "alpha", p50=220),
        reasoning_transport={
            "status": "candidate",
            "transport": "chat_reasoning_effort",
            "supported_efforts": ["low"],
        },
    )
    monkeypatch.setenv("PROVIDER_A_BASE_URL", "https://provider-a.example/v1")
    monkeypatch.setenv("PROVIDER_A_API_KEY", "fixture-key")
    groups = _groups([profile])
    research = _research_output([str(groups[0]["candidate_id"])])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 220,
                    "output_sha256": sha256_text(f"prefusion:{item.profile_id}"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )
    source_registry = report["fusion_registry"]
    assert report["status"] == "ready"
    assert validate_prefusion_registry_handoff(source_registry)["valid"] is True

    source_path = tmp_path / "prefusion-source.private.json"
    calibration_path = tmp_path / "prefusion-calibration.private.json"
    probe_path = tmp_path / "prefusion-reasoning.private.json"
    output_path = tmp_path / "prefusion-reconciled.private.json"
    source_path.write_text(json.dumps(source_registry), encoding="utf-8")
    calibration_registry = json.loads(json.dumps(source_registry))
    calibration_registry["models"][0]["reasoning_transport"]["status"] = "verified"
    calibration_path.write_text(json.dumps(calibration_registry), encoding="utf-8")
    source_profile = normalize_profile(source_registry["models"][0])
    accepted = {
        "status": "accepted",
        "marker_observed": True,
        "strict_streaming_contract_valid": True,
        "stream_requested": True,
        "strict_streaming_requested": True,
        "stream_observed": True,
        "stream_fallback_used": False,
        "stream_protocol": "sse",
        "stream_frame_count": 2,
        "latency_ms": 12,
    }
    probe_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_reasoning_probe.v1",
                "probe_kind": "reasoning_transport",
                "mode": "live",
                "network_calls_performed": True,
                "timeout_seconds": 20,
                "candidate_model_count_before_selection": 1,
                "model_count": 1,
                "selection_policy": {
                    "profile_hash_filter_enabled": False,
                    "max_models": None,
                    "max_models_per_provider": None,
                    "selected_model_count": 1,
                },
                "probes": [
                    {
                        "profile_id": source_profile.profile_id,
                        "provider": source_profile.provider,
                        "model": source_profile.model,
                        "api_format": source_profile.api_format,
                        "probe_kind": "reasoning_transport",
                        "probe_mode": "live",
                        "live_probe_evidence": True,
                        "status": "verified",
                        "strict_wire_shape_preserved": True,
                        "all_declared_efforts_strict_streaming": True,
                        "transport": "chat_reasoning_effort",
                        "declared_efforts": ["low"],
                        "control": accepted,
                        "effort_results": [{"effort": "low", **accepted}],
                        "reasoning_transport_binding": reasoning_transport_probe_binding(
                            source_profile
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    reconciliation = build_reasoning_transport_reconciliation(
        source_registry_path=source_path,
        calibration_registry_path=calibration_path,
        reasoning_probe_path=probe_path,
    )
    receipt = apply_reasoning_transport_reconciliation(
        reconciliation,
        source_registry_path=source_path,
        output_registry_path=output_path,
    )

    assert receipt["status"] == "ready"
    assert receipt["registry_output_written"] is True
    updated = json.loads(output_path.read_text(encoding="utf-8"))
    assert updated["models"][0]["reasoning_transport"]["status"] == "verified"
    assert updated["prefusion_screening"] == source_registry["prefusion_screening"]
    assert updated["prefusion_model_catalog"] == source_registry["prefusion_model_catalog"]
    assert validate_prefusion_registry_handoff(updated)["valid"] is True
    assert len(load_registry(output_path, require_prefusion=True)) == 1


def test_live_prefusion_binds_multi_sample_stability_evidence_and_rejects_tampering(
    monkeypatch,
):
    profile = _profile("provider-a", "alpha", "alpha", p50=200)
    groups = _groups([profile])
    research = _research_output([str(groups[0]["candidate_id"])])

    def fake_probe(probe_profiles, **kwargs):
        samples = kwargs["samples_per_profile"]
        assert samples == 3
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "stability_contract": _stability_contract(samples),
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 200,
                    "output_sha256": sha256_text(f"stable:{item.profile_id}"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                    **_multi_sample_stability_evidence(samples),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
        stream_probe_samples=3,
    )

    assert report["status"] == "ready"
    registry = report["fusion_registry"]
    binding = registry["prefusion_screening"]["eligible_profile_bindings"][0]
    assert registry["prefusion_screening"]["multi_sample_stream_stability_required"] is True
    assert binding["stability_sample_count"] == 3
    assert binding["sample_receipts_sha256"]
    assert validate_prefusion_registry_handoff(registry)["valid"] is True

    tampered = json.loads(json.dumps(registry))
    tampered["prefusion_screening"]["eligible_profile_bindings"][0][
        "sample_receipts_sha256"
    ] = ""
    validation = validate_prefusion_registry_handoff(tampered)
    assert validation["valid"] is False
    assert "prefusion_registry_stream_stability_evidence_invalid" in validation[
        "reason_codes"
    ]


def test_live_prefusion_rejects_single_sample_admission_before_provider_probe(monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha", p50=200)
    groups = _groups([profile])

    def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("single-sample production admission must not probe providers")

    monkeypatch.setattr(model_screening, "probe_provider_models", unexpected_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output([str(groups[0]["candidate_id"])]),
        live=True,
        min_available_models=1,
        stream_probe_samples=1,
    )

    assert report["status"] == "blocked"
    assert "prefusion_stream_probe_multi_sample_required" in report["blockers"]
    assert report["streaming_probe"]["network_calls_performed"] is False


def test_operational_ranking_reorders_available_models_without_overwriting_research_rank(
    monkeypatch,
):
    profiles = [
        _profile("provider-a", "alpha", "alpha", p50=200),
        _profile("provider-b", "beta", "beta", p50=200),
    ]
    groups = _groups(profiles)
    research = _research_output([str(row["candidate_id"]) for row in groups])
    # Keep the research prior slightly in alpha's favor, then make beta much
    # faster. The fixed operational weights should make the serving order
    # differ while preserving alpha's original research rank.
    research["ordered_models"][0]["capability_summary"]["overall"] = 0.80
    research["ordered_models"][0]["capability_summary"]["axes"] = {
        axis: 0.80 for axis in CAPABILITY_AXES
    }
    research["ordered_models"][1]["capability_summary"]["overall"] = 0.79
    research["ordered_models"][1]["capability_summary"]["axes"] = {
        axis: 0.79 for axis in CAPABILITY_AXES
    }

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profile.profile_id,
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": "available",
                    "latency_ms": 80_000 if profile.model == "alpha" else 100,
                    "output_sha256": sha256_text(f"operational:{profile.profile_id}"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for profile in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "ready"
    assert validate_prefusion_handoff(report)["valid"] is True
    research_order = [
        row["canonical_model_id"] for row in report["research_ranking"]["ordered_models"]
    ]
    operational_order = [
        row["canonical_model_id"]
        for row in report["operational_ranking"]["ordered_models"]
    ]
    assert research_order == ["alpha", "beta"]
    assert operational_order == ["beta", "alpha"]

    available = report["available_model_list"]
    assert [row["canonical_model_id"] for row in available] == ["beta", "alpha"]
    beta = available[0]
    alpha = available[1]
    assert beta["available_rank"] == beta["operational_rank"] == 1
    assert alpha["available_rank"] == alpha["operational_rank"] == 2
    assert beta["research_prior_rank"] == 2
    assert alpha["research_prior_rank"] == 1
    assert beta["fastest_observed_latency_ms"] == 100
    assert beta["fastest_observed_p50_latency_ms"] == 100
    assert report["model_catalog"]["available_model_list"] == available
    assert report["fusion_registry"]["prefusion_screening"]["available_model_list"] == available


def test_prefusion_fusion_handoff_is_the_only_validated_available_model_boundary(
    monkeypatch,
):
    profiles = [
        _profile("provider-a", "shared", "shared", p50=120),
        _profile("provider-b", "shared", "shared", p50=180),
        _profile("provider-c", "other", "other", p50=240),
    ]
    groups = _groups(profiles)

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profile.profile_id,
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": "available",
                    "latency_ms": profile.p50_latency_ms,
                    "output_sha256": sha256_text(f"handoff:{profile.profile_id}"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for profile in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=_research_output([str(row["candidate_id"]) for row in groups]),
        live=True,
        min_available_models=1,
    )

    handoff = build_prefusion_fusion_handoff(report)
    assert handoff["status"] == "ready"
    assert handoff["logical_model_count"] == 2
    assert handoff["physical_profile_count"] == 3
    assert handoff["ranking_complete"] is True
    assert (
        handoff["research_ranking"]["schema"]
        == "axio_fusion_api.prefusion_research_ranking_registry.v1"
    )
    assert handoff["research_ranking"]["candidate_count"] == 2
    assert handoff["research_ranking"]["ranking_prior_only"] is True
    assert (
        handoff["research_ranking"]["ordered_models"]
        == report["model_catalog"]["ranking"]["ordered_models"]
    )
    assert (
        handoff["operational_ranking"]["ordered_models"]
        == report["model_catalog"]["operational_ranking"]["ordered_models"]
    )
    assert handoff["research_ranking_content_sha256"] == sha256_text(
        model_screening.stable_json(handoff["research_ranking"])
    )
    assert handoff["operational_ranking_content_sha256"] == sha256_text(
        model_screening.stable_json(handoff["operational_ranking"])
    )
    assert len(handoff["available_model_list"]) == 2
    assert "fusion_registry" not in handoff
    assert handoff["private_registry_included"] is False
    assert handoff["available_model_list_sha256"] == sha256_text(
        model_screening.stable_json(handoff["available_model_list"])
    )

    private_handoff = build_prefusion_fusion_handoff(
        report,
        include_private_registry=True,
    )
    assert private_handoff["private_registry_included"] is True
    assert private_handoff["fusion_registry"]["binding_status"] == "ready"
    assert private_handoff["fusion_registry"]["available_logical_model_count"] == 2

    tampered = json.loads(json.dumps(report))
    tampered["available_model_list"].append(
        {"canonical_model_id": "unprobed-model", "available_rank": 3}
    )
    blocked = build_prefusion_fusion_handoff(tampered)
    assert blocked["status"] == "blocked"
    assert blocked["available_model_list"] == []
    assert "prefusion_report_available_list_mismatch" in blocked["validation"]["reason_codes"]

    redacted = build_prefusion_fusion_handoff(
        report,
        include_private_registry=True,
        redact_provider_identifiers=True,
    )
    serialized = json.dumps(redacted, ensure_ascii=False)
    assert redacted["status"] == "ready"
    assert redacted["private_registry_included"] is False
    assert "fusion_registry" not in redacted
    assert "provider-a" not in serialized
    assert "provider-b" not in serialized
    assert "shared" not in serialized


def test_operational_score_tampering_is_rejected_by_prefusion_handoff_validator(
    monkeypatch,
):
    profiles = [
        _profile("provider-a", "alpha", "alpha", p50=200),
        _profile("provider-b", "beta", "beta", p50=200),
    ]
    groups = _groups(profiles)

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profile.profile_id,
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text(f"tamper:{profile.profile_id}"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for profile in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=_research_output([str(row["candidate_id"]) for row in groups]),
        live=True,
        min_available_models=1,
    )
    assert report["status"] == "ready"

    tampered = json.loads(json.dumps(report["fusion_registry"]))
    tampered["prefusion_model_catalog"]["operational_ranking"]["ordered_models"][0][
        "operational_score"
    ] = 0.0
    validation = validate_prefusion_registry_handoff(tampered)
    assert validation["valid"] is False
    assert "prefusion_registry_operational_score_mismatch" in validation["reason_codes"]


def test_top_level_operational_ranking_tampering_is_rejected(monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha", p50=100)

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("top-level-tamper"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output(["candidate_0001"]),
        live=True,
        min_available_models=1,
    )
    assert report["status"] == "ready"
    tampered = json.loads(json.dumps(report))
    tampered["operational_ranking"]["ordered_models"][0]["operational_score"] = 0.0
    validation = validate_prefusion_handoff(tampered)
    assert validation["valid"] is False
    assert "prefusion_report_operational_ranking_mismatch" in validation["reason_codes"]


def test_partial_replica_failure_keeps_only_live_replica_in_serving_projection(
    monkeypatch,
):
    profiles = [
        _profile("provider-a", "shared", "shared", p50=100),
        _profile("provider-b", "shared", "shared", p50=100),
    ]
    groups = _groups(profiles)

    def fake_probe(probe_profiles, **_kwargs):
        rows = []
        for item in probe_profiles:
            live = item.provider == "provider-a"
            rows.append(
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available" if live else "error",
                    "latency_ms": 100 if live else 1000,
                    "output_sha256": sha256_text("partial:" + item.profile_id)
                    if live
                    else "",
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
            )
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": rows,
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=_research_output([str(groups[0]["candidate_id"])]),
        live=True,
        min_available_models=1,
    )
    assert report["status"] == "ready"
    logical = report["available_model_list"]
    assert len(logical) == 1
    assert logical[0]["replica_count"] == 1
    assert logical[0]["physical_replica_count"] == 2
    assert logical[0]["failed_replica_count"] == 1
    assert logical[0]["providers"] == ["provider-a"]
    op = report["operational_ranking"]["ordered_models"][0]
    assert op["stream_reliability_score"] == 0.5
    assert op["replica_count"] == 1
    assert validate_prefusion_handoff(report)["valid"] is True


def test_live_screening_excludes_slow_empty_and_non_live_probe_rows(monkeypatch):
    profiles = [
        _profile("provider-a", "fast", "fast"),
        _profile("provider-b", "slow", "slow"),
        _profile("provider-c", "empty", "empty"),
    ]
    groups = _groups(profiles)
    research = _research_output([str(row["candidate_id"]) for row in groups])
    fake_research = _FakeClient(json.dumps(research))
    for env in ("PROVIDER_A_API_KEY", "PROVIDER_B_API_KEY", "PROVIDER_C_API_KEY"):
        monkeypatch.setenv(env, "fixture-key")
    monkeypatch.setenv("PROVIDER_A_BASE_URL", "https://provider-a.example/v1")
    monkeypatch.setenv("PROVIDER_B_BASE_URL", "https://provider-b.example/v1")
    monkeypatch.setenv("PROVIDER_C_BASE_URL", "https://provider-c.example/v1")

    def fake_probe(probe_profiles, **_kwargs):
        rows = []
        for profile in probe_profiles:
            if profile.model == "fast":
                rows.append(
                    {
                        "profile_id": profile.profile_id,
                        "provider": profile.provider,
                        "model": profile.model,
                        "status": "available",
                        "latency_ms": 250,
                            "output_sha256": sha256_text("probe-output"),
                            "probe_mode": "live",
                            "live_probe_evidence": True,
                            **_stream_evidence(),
                    }
                )
            elif profile.model == "slow":
                rows.append(
                    {
                        "profile_id": profile.profile_id,
                        "provider": profile.provider,
                        "model": profile.model,
                        "status": "available",
                        "latency_ms": 90_001,
                            "output_sha256": sha256_text("slow-output"),
                            "probe_mode": "live",
                            "live_probe_evidence": True,
                            **_stream_evidence(),
                    }
                )
            else:
                rows.append(
                    {
                        "profile_id": profile.profile_id,
                        "provider": profile.provider,
                        "model": profile.model,
                        "status": "available",
                        "latency_ms": 100,
                            "output_sha256": "",
                            "probe_mode": "live",
                            "live_probe_evidence": True,
                            **_stream_evidence(),
                    }
                )
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": rows,
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
        provider_client=fake_research,
    )
    assert report["status"] == "ready"
    assert [row["model"] for row in report["fusion_eligible_models"]] == ["fast"]
    assert [row["model"] for row in report["fusion_registry"]["models"]] == ["fast"]
    assert all(row["model"] != "slow" for row in report["fusion_registry"]["models"])

    def non_live_probe(_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "dry_run",
            "network_calls_performed": False,
            "probes": [
                {
                    "profile_id": profiles[0].profile_id,
                    "status": "available",
                    "latency_ms": 1,
                    "output_sha256": sha256_text("fake"),
                }
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", non_live_probe)
    blocked = run_prefusion_model_screening(
        profiles=profiles[:1],
        source_manifest=_source_manifest(),
        research_output=_research_output(["candidate_0001"]),
        live=True,
        min_available_models=1,
    )
    assert blocked["status"] == "blocked"
    assert blocked["fusion_registry"]["models"] == []


def test_probe_without_exact_physical_profile_id_cannot_admit_provider_alias(
    monkeypatch,
):
    profile = _profile("provider-a", "alias", "alias")

    def alias_only_probe(_probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("alias-only-probe"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", alias_only_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output(["candidate_0001"]),
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "blocked"
    assert "prefusion_insufficient_streaming_eligible_models" in report["blockers"]
    assert report["fusion_registry"]["models"] == []


def test_cli_rejects_registry_and_provider_manifest_for_prefusion():
    with pytest.raises(SystemExit, match="cannot combine --registry"):
        fusion_cli_main(
            [
                "--provider-config-file",
                "/private/provider-manifest.json",
                "pre-fusion-screen",
                "--registry",
                "/private/old-registry.json",
            ]
        )


def test_partial_candidate_limit_blocks_delivery_and_does_not_probe(monkeypatch):
    profiles = [
        _profile("provider-a", "alpha", "alpha"),
        _profile("provider-b", "beta", "beta"),
    ]
    groups = _groups(profiles)
    research = _research_output([str(row["candidate_id"]) for row in groups])
    probe_called = False

    def unexpected_probe(*_args, **_kwargs):
        nonlocal probe_called
        probe_called = True
        raise AssertionError("a partial candidate pool must not reach live probing")

    monkeypatch.setattr(model_screening, "probe_provider_models", unexpected_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        max_models=1,
        min_available_models=1,
    )

    assert report["status"] == "blocked"
    assert "prefusion_complete_inventory_required" in report["blockers"]
    assert probe_called is False
    assert report["workflow"]["candidate_count_before_limit"] == 2
    assert report["workflow"]["candidate_count"] == 2
    assert report["workflow"]["candidate_inventory_complete"] is False
    assert report["model_catalog"]["status"] == "blocked"
    assert report["model_catalog"]["inventory"]["complete"] is False
    assert report["fusion_handoff"]["status"] == "blocked"


def test_generated_catalog_is_required_when_loading_a_ready_registry(tmp_path, monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha")
    groups = _groups([profile])
    research = _research_output([str(groups[0]["candidate_id"])])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("catalog-probe"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "ready"
    path = tmp_path / "catalog-registry.json"
    path.write_text(json.dumps(report["fusion_registry"]), encoding="utf-8")
    assert len(load_registry(path)) == 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("prefusion_model_catalog")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_registry(path) == []


def test_prefusion_handoff_contract_binds_report_registry_and_catalog(tmp_path, monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha", p50=100)
    groups = _groups([profile])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("handoff-stream"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output([str(groups[0]["candidate_id"])]),
        live=True,
        min_available_models=1,
    )
    assert report["status"] == "ready"
    assert validate_prefusion_handoff(report)["valid"] is True
    registry = report["fusion_registry"]
    assert validate_prefusion_registry_handoff(registry)["valid"] is True

    tampered_report = json.loads(json.dumps(report))
    tampered_report["available_model_list"] = []
    invalid_report = validate_prefusion_handoff(tampered_report)
    assert invalid_report["valid"] is False
    assert "prefusion_report_available_list_mismatch" in invalid_report["reason_codes"]

    tampered_registry = json.loads(json.dumps(registry))
    tampered_registry["prefusion_screening"]["available_model_list"] = []
    invalid_registry = validate_prefusion_registry_handoff(tampered_registry)
    assert invalid_registry["valid"] is False
    assert "prefusion_registry_catalog_available_list_mismatch" in invalid_registry["reason_codes"]

    tampered_role_coverage = json.loads(json.dumps(registry))
    tampered_role_coverage["prefusion_screening"]["role_coverage"]["roles"][0][
        "candidate_count"
    ] += 1
    invalid_role_coverage = validate_prefusion_registry_handoff(tampered_role_coverage)
    assert invalid_role_coverage["valid"] is False
    assert "prefusion_registry_role_coverage_projection_mismatch" in invalid_role_coverage[
        "reason_codes"
    ]

    tampered_role_name = json.loads(json.dumps(registry))
    tampered_role_name["prefusion_screening"]["available_model_list"][0][
        "allowed_roles"
    ].append("tool_worker")
    invalid_role_name = validate_prefusion_registry_handoff(tampered_role_name)
    assert invalid_role_name["valid"] is False
    assert "prefusion_registry_role_name_invalid" in invalid_role_name["reason_codes"]

    path = tmp_path / "tampered-prefusion-registry.json"
    path.write_text(json.dumps(tampered_registry), encoding="utf-8")
    assert load_registry(path) == []


def test_registry_capability_axis_tampering_fails_closed(tmp_path, monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha", p50=100)
    groups = _groups([profile])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("axis-gate-probe"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output([str(groups[0]["candidate_id"])]),
        live=True,
        min_available_models=1,
    )
    registry = json.loads(json.dumps(report["fusion_registry"]))
    catalog_row = registry["prefusion_model_catalog"]["ranking"]["ordered_models"][0]
    catalog_row["capability_overall"] = 0.85
    catalog_row["capability_axes"] = {axis: 0.0 for axis in CAPABILITY_AXES}

    validation = validate_prefusion_registry_handoff(registry)
    assert validation["valid"] is False
    assert "prefusion_registry_capability_axis_coverage_invalid" in validation[
        "reason_codes"
    ]

    path = tmp_path / "axis-tampered-registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    assert load_registry(path) == []


def test_registry_research_projection_capability_axis_tampering_fails_closed(
    monkeypatch,
):
    profile = _profile("provider-a", "alpha", "alpha", p50=100)
    groups = _groups([profile])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("research-axis-gate-probe"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output([str(groups[0]["candidate_id"])]),
        live=True,
        min_available_models=1,
    )
    registry = json.loads(json.dumps(report["fusion_registry"]))
    research_row = registry["research_ranking"]["ordered_models"][0]
    research_row["capability_overall"] = 0.80
    research_row["capability_axes"] = {axis: 0.0 for axis in CAPABILITY_AXES}

    validation = validate_prefusion_registry_handoff(registry)
    assert validation["valid"] is False
    assert "prefusion_registry_capability_axis_coverage_invalid" in validation[
        "reason_codes"
    ]


def test_prefusion_handoff_rejects_latency_or_stream_evidence_tampering(tmp_path, monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha", p50=100)
    groups = _groups([profile])

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("handoff-stream-2"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output([str(groups[0]["candidate_id"])]),
        live=True,
        min_available_models=1,
    )
    registry = json.loads(json.dumps(report["fusion_registry"]))
    binding = registry["prefusion_screening"]["eligible_profile_bindings"][0]
    binding["latency_ms"] = 90_001
    assert validate_prefusion_registry_handoff(registry)["valid"] is False
    assert "prefusion_registry_stream_latency_invalid" in validate_prefusion_registry_handoff(
        registry
    )["reason_codes"]

    stream_registry = json.loads(json.dumps(report["fusion_registry"]))
    stream_binding = stream_registry["prefusion_screening"]["eligible_profile_bindings"][0]
    stream_binding["stream_observed"] = False
    assert validate_prefusion_registry_handoff(stream_registry)["valid"] is False
    assert "prefusion_registry_stream_evidence_invalid" in validate_prefusion_registry_handoff(
        stream_registry
    )["reason_codes"]

    path = tmp_path / "tampered-latency-registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    assert load_registry(path) == []


def test_research_agent_binds_to_runtime_profile_credentials(monkeypatch):
    profile = _profile("nvidia", "openai/gpt-oss-120b", "openai/gpt-oss-120b")
    runtime_profile = profile.__class__(
        **{
            **profile.__dict__,
            "runtime_base_url": "https://runtime.example/v1",
            "runtime_api_keys": ("runtime-secret",),
        }
    )
    config = {
        "provider": "nvidia",
        "model": "openai/gpt-oss-120b",
        "api_format": "chat",
        "base_url_env": "AXIO_NVIDIA_BASE_URL",
        "api_key_env": "AXIO_NVIDIA_API_KEYS",
        "ranking_prior_forbidden": True,
    }
    resolved = model_screening._resolve_research_agent_profile(
        config,
        [runtime_profile],
    )
    assert resolved.profile_id == runtime_profile.profile_id
    assert resolved.runtime_base_url == "https://runtime.example/v1"
    assert resolved.runtime_api_keys == ("runtime-secret",)
    assert model_screening.profile_credential_readiness(resolved)["credential_ready"] is True


def test_latency_ineligible_profiles_are_absent_from_logical_available_list(monkeypatch):
    profiles = [
        _profile("provider-a", "fast", "fast", p50=200),
        _profile("provider-b", "slow", "slow", p50=200),
    ]
    groups = _groups(profiles)
    research = _research_output([str(row["candidate_id"]) for row in groups])
    for env in ("PROVIDER_A_API_KEY", "PROVIDER_B_API_KEY"):
        monkeypatch.setenv(env, "fixture-key")
    monkeypatch.setenv("PROVIDER_A_BASE_URL", "https://provider-a.example/v1")
    monkeypatch.setenv("PROVIDER_B_BASE_URL", "https://provider-b.example/v1")

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profile.profile_id,
                    "status": "available",
                    "latency_ms": 100 if profile.model == "fast" else 90_001,
                        "output_sha256": sha256_text(profile.model),
                        "probe_mode": "live",
                        "live_probe_evidence": True,
                        **_stream_evidence(),
                }
                for profile in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )
    logical = report["fusion_registry"]["prefusion_screening"]["available_model_list"]
    assert [row["provider_model"] for row in logical] == ["fast"]
    assert all(row["provider_model"] != "slow" for row in logical)


def test_prefusion_latency_ceiling_is_inclusive_at_exactly_90_seconds(monkeypatch):
    profiles = [
        _profile("provider-a", "at-ceiling", "at-ceiling", p50=90_000),
        _profile("provider-b", "over-ceiling", "over-ceiling", p50=90_001),
    ]
    research = _research_output(["candidate_0001", "candidate_0002"])

    monkeypatch.setenv("PROVIDER_A_API_KEY", "fixture-key")
    monkeypatch.setenv("PROVIDER_B_API_KEY", "fixture-key")
    monkeypatch.setenv("PROVIDER_A_BASE_URL", "https://provider-a.example/v1")
    monkeypatch.setenv("PROVIDER_B_BASE_URL", "https://provider-b.example/v1")

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profile.profile_id,
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": "available",
                    "latency_ms": 90_000,
                    "output_sha256": sha256_text(profile.model),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
                for profile in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=profiles,
        source_manifest=_source_manifest(),
        research_output=research,
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "ready"
    assert [row["provider_model"] for row in report["available_model_list"]] == [
        "at-ceiling"
    ]
    assert report["streaming_probe"]["latency_ineligible_count"] == 1


def test_streaming_fallback_is_not_prefusion_serving_evidence(monkeypatch):
    profile = _profile("provider-a", "fallback", "fallback", p50=200)

    def fake_probe(probe_profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": item.profile_id,
                    "provider": item.provider,
                    "model": item.model,
                    "status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("ordinary-json-fallback"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    "stream_requested": True,
                    "stream_observed": False,
                    "stream_fallback_used": True,
                }
                for item in probe_profiles
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output(["candidate_0001"]),
        live=True,
        min_available_models=1,
    )

    assert report["status"] == "blocked"
    assert report["fusion_registry"]["models"] == []
    assert report["available_model_list"] == []


def test_redacted_screening_report_hashes_logical_model_identifiers():
    profile = _profile("provider-a", "alpha", "alpha")
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest=_source_manifest(),
        research_output=_research_output(["candidate_0001"]),
        live=False,
        redact_provider_identifiers=True,
    )
    serialized = json.dumps(report)
    assert "provider-a" not in serialized
    assert '"provider_model": "alpha"' not in serialized


def test_registry_binding_requires_exact_live_eligible_rows_and_profiles():
    profile = _profile("provider-a", "alpha", "alpha")
    screening = {
        "status": "ready",
        "fusion_eligible_models": [
            {
                "profile_id_sha256": sha256_text(profile.profile_id),
                    "streaming_status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("probe"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
            }
        ],
    }
    registry = build_fusion_registry_from_screening(screening, profiles=[profile])
    assert registry["models"][0]["model"] == "alpha"
    assert build_fusion_registry_from_screening(screening)["models"] == []

    non_live = dict(screening)
    non_live["fusion_eligible_models"] = [
        {**screening["fusion_eligible_models"][0], "live_probe_evidence": False}
    ]
    assert build_fusion_registry_from_screening(non_live, profiles=[profile])["models"] == []


def test_registry_binding_requires_measured_latency_and_sha256_output():
    profile = _profile("provider-a", "alpha", "alpha")
    base_row = {
        "profile_id_sha256": sha256_text(profile.profile_id),
        "streaming_status": "available",
        "probe_mode": "live",
        "live_probe_evidence": True,
        **_stream_evidence(),
    }
    missing_latency = {
        **base_row,
        "output_sha256": sha256_text("probe"),
    }
    assert build_fusion_registry_from_screening(
        {"status": "ready", "fusion_eligible_models": [missing_latency]},
        profiles=[profile],
    )["models"] == []

    invalid_output_hash = {
        **base_row,
        "latency_ms": 100,
        "output_sha256": "probe-output",
    }
    assert build_fusion_registry_from_screening(
        {"status": "ready", "fusion_eligible_models": [invalid_output_hash]},
        profiles=[profile],
    )["models"] == []


def test_probe_bound_registry_preserves_prefusion_runtime_metadata_and_provenance(tmp_path):
    profile = _profile("provider-a", "alpha", "alpha")
    probe_row = {
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "api_format": profile.api_format,
        "status": "available",
        "latency_ms": 100,
        "output_sha256": sha256_text("probe-alpha"),
        "probe_mode": "live",
        "live_probe_evidence": True,
        **_stream_evidence(),
    }
    probe_path = tmp_path / "provider-probe.private.json"
    probe_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_probe.v1",
                "mode": "live",
                "network_calls_performed": True,
                "probes": [probe_row],
            }
        ),
        encoding="utf-8",
    )
    registry = build_fusion_registry_from_screening(
        {
            "status": "ready",
            "fusion_eligible_models": [
                {
                    "profile_id_sha256": sha256_text(profile.profile_id),
                    "provider": profile.provider,
                    "model": profile.model,
                    "canonical_model_id": profile.canonical_model_id,
                    "streaming_status": "available",
                    "latency_ms": 100,
                    "output_sha256": sha256_text("probe-alpha"),
                    "probe_mode": "live",
                    "live_probe_evidence": True,
                    **_stream_evidence(),
                }
            ],
            "research_ranking": {"ordered_models": []},
        },
        profiles=[profile],
    )
    registry_path = tmp_path / "runtime-registry.private.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    bound = build_probe_bound_registry(
        registry_path=registry_path,
        probe_paths=[probe_path],
        min_available_models=1,
    )

    assert bound["binding_status"] == "ready"
    assert bound["generated_from_probe"] is True
    assert bound["readiness"]["live_probe_proven"] is True
    assert bound["readiness"]["final_claim_registry_ready"] is True
    assert bound["source_artifacts"]["probe_file_count"] == 1
    assert bound["probe_evidence_binding"]["profile_set_matches"] is True
    assert bound["probe_evidence_binding"]["blockers"] == []
    assert build_registry_from_probe_artifacts(
        probe_paths=[probe_path],
        min_available_models=1,
    )["live_available_model_count"] == 1


def test_probe_bound_registry_rejects_profile_set_drift(tmp_path):
    profile = _profile("provider-a", "alpha", "alpha")
    registry = build_registry_from_probe_artifacts(
        probe_paths=[],
        min_available_models=1,
    )
    registry.update(
        {
            "generated_from_prefusion_screening": True,
            "binding_status": "ready",
            "models": [profile.safe_dict()],
            "model_count": 1,
        }
    )
    registry_path = tmp_path / "runtime-registry.private.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    other = _profile("provider-b", "beta", "beta")
    probe_path = tmp_path / "provider-probe.private.json"
    probe_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.provider_probe.v1",
                "mode": "live",
                "network_calls_performed": True,
                "probes": [
                    {
                        "profile_id": other.profile_id,
                        "provider": other.provider,
                        "model": other.model,
                        "api_format": other.api_format,
                        "status": "available",
                        "latency_ms": 100,
                        "output_sha256": sha256_text("probe-beta"),
                        "probe_mode": "live",
                        "live_probe_evidence": True,
                        **_stream_evidence(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    blocked = build_probe_bound_registry(
        registry_path=registry_path,
        probe_paths=[probe_path],
        min_available_models=1,
    )

    assert blocked["binding_status"] == "blocked"
    assert blocked["generated_from_probe"] is False
    assert "probe_bound_registry_profile_set_mismatch" in blocked["probe_evidence_binding"]["blockers"]
    assert blocked["readiness"]["final_claim_registry_ready"] is False


def test_config_rejects_secrets_and_low_confidence_cannot_promote_judge():
    with pytest.raises(ModelScreeningError):
        load_prefusion_research_agent_config({"apiKey": "secret"})
    with pytest.raises(ModelScreeningError):
        load_prefusion_research_agent_config({"base_url": "https://secret.example/v1"})

    profiles = [_profile("provider-a", "alpha", "alpha")]
    groups = _groups(profiles)
    output = _research_output([str(groups[0]["candidate_id"])], confidence=0.4, overall=0.4)
    normalized = validate_prefusion_research_output(
        output,
        groups=groups,
        source_slots=["source_official"],
        source_evidence={"source_official": "evidence-hash"},
    )
    row = normalized["ordered_models"][0]
    assert "judge" in row["disallowed_roles"]
    assert "synthesizer" in row["disallowed_roles"]
    assert "judge" not in row["allowed_roles"]
    assert "synthesizer" not in row["allowed_roles"]


def test_dry_run_report_does_not_persist_source_or_research_text():
    profile = _profile("provider-a", "alpha", "alpha")
    research = _research_output(["candidate_0001"])
    report = run_prefusion_model_screening(
        profiles=[profile],
        source_manifest={
            "schema": model_screening.PREFUSION_SOURCE_MANIFEST_SCHEMA,
            "sources": [
                {
                    "source_slot": "source_secret",
                    "content": "UNIQUE_PRIVATE_SOURCE_TEXT",
                }
            ],
        },
        research_output=research,
        live=False,
    )
    serialized = json.dumps(report, ensure_ascii=False)
    assert "UNIQUE_PRIVATE_SOURCE_TEXT" not in serialized
    assert report["raw_source_content_persisted"] is False
    assert report["raw_research_output_persisted"] is False


def test_pre_fusion_cli_writes_only_the_screened_registry(tmp_path, monkeypatch):
    profile = _profile("provider-a", "alpha", "alpha")
    candidate_registry = tmp_path / "candidate-registry.json"
    candidate_registry.write_text(
        json.dumps({"models": [profile.safe_dict()]}),
        encoding="utf-8",
    )
    focus_path = tmp_path / "focus.json"
    focus_path.write_text(
        json.dumps(
            {
                "schema": model_screening.PREFUSION_FOCUS_MANIFEST_SCHEMA,
                "ranking_prior_forbidden": True,
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "sources.json"
    source_path.write_text(json.dumps(_source_manifest()), encoding="utf-8")
    research_path = tmp_path / "research.json"
    research_path.write_text(
        json.dumps(_research_output(["candidate_0001"])),
        encoding="utf-8",
    )
    report_path = tmp_path / "screening.json"
    registry_path = tmp_path / "fusion-registry.json"
    monkeypatch.setenv("PROVIDER_A_BASE_URL", "https://provider-a.example/v1")
    monkeypatch.setenv("PROVIDER_A_API_KEY", "fixture-key")

    def fake_probe(profiles, **_kwargs):
        return {
            "schema": "axio_fusion_api.provider_probe.v1",
            "mode": "live",
            "network_calls_performed": True,
            "probes": [
                {
                    "profile_id": profiles[0].profile_id,
                    "provider": profiles[0].provider,
                    "model": profiles[0].model,
                    "status": "available",
                    "latency_ms": 50,
                        "output_sha256": sha256_text("probe"),
                        "probe_mode": "live",
                        "live_probe_evidence": True,
                        **_stream_evidence(),
                }
            ],
        }

    monkeypatch.setattr(model_screening, "probe_provider_models", fake_probe)
    assert fusion_cli_main(
        [
            "pre-fusion-screen",
            "--registry",
            str(candidate_registry),
            "--focus-manifest",
            str(focus_path),
            "--source-manifest",
            str(source_path),
            "--research-output",
            str(research_path),
            "--live",
            "--min-available-models",
            "1",
            "--output",
            str(report_path),
            "--registry-output",
            str(registry_path),
        ]
    ) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    generated = json.loads(registry_path.read_text(encoding="utf-8"))
    assert report["status"] == "ready"
    assert generated["generated_from_prefusion_screening"] is True
    assert [row["model"] for row in generated["models"]] == ["alpha"]


def test_screening_registry_load_fails_closed_when_probe_binding_is_removed(tmp_path):
    profile = _profile("provider-a", "alpha", "alpha")
    screening = {
        "status": "ready",
        "fusion_eligible_models": [
            {
                "profile_id_sha256": sha256_text(profile.profile_id),
                "streaming_status": "available",
                "latency_ms": 100,
                "output_sha256": sha256_text("probe"),
                "probe_mode": "live",
                "live_probe_evidence": True,
                **_stream_evidence(),
            }
        ],
        "research_ranking": {"ordered_models": []},
    }
    generated = model_screening.build_fusion_registry_from_screening(
        screening,
        profiles=[profile],
    )
    path = tmp_path / "screened-registry.json"
    path.write_text(json.dumps(generated), encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["prefusion_screening"].pop("eligible_profile_bindings")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert model_screening.load_registry(path) == []


def test_blocked_screening_registry_cannot_become_routable_by_editing_models(tmp_path):
    profile = _profile("provider-a", "alpha", "alpha")
    payload = {
        "schema": "axio_fusion_api.registry.v1",
        "generated_from_prefusion_screening": True,
        "binding_status": "blocked",
        "models": [profile.safe_dict()],
        "prefusion_screening": {"eligible_profile_bindings": []},
    }
    path = tmp_path / "blocked-registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert model_screening.load_registry(path) == []
