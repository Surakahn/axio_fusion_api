import json
import hashlib
import sys
from pathlib import Path

import pytest


STANDALONE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from axio_fusion_api.baseline_screening import (
    SCREENING_TRANSPORT_ADMISSION_SCHEMA,
    SCREENING_CAMPAIGN_SCHEMA,
    SCREENING_PLAN_SCHEMA,
    ScreeningCase,
    _load_mmlu_pro_cases,
    _load_source_cases,
    _canonical_live_groups,
    _run_screening_case,
    _run_screening_unit,
    _screening_retry_contract_errors,
    _private_resume_case_results,
    _persist_screening_private_checkpoint,
    _screening_adapter_runtime_preflight,
    _screening_checkpoint_path,
    _screening_unit_set_digest,
    _screening_unit_path,
    build_external_ranking_manifest_from_screening,
    build_non_target_screening_plan,
    build_transport_availability_admission,
    build_provider_identity_attestation_receipt,
    run_non_target_screening_campaign,
)
from axio_fusion_api.cli import build_parser
from axio_fusion_api.evaluation import (
    _external_provider_ranking_selection_receipt,
    _provider_baseline_selection_context,
    _provider_registry_receipt,
    build_provider_baseline_freeze_manifest,
    build_external_provider_ranking_template,
)
from axio_fusion_api import providers as provider_module
from axio_fusion_api.operational_admission import (
    redact_operational_admission,
    run_operational_admission,
)
from axio_fusion_api.providers import ProviderCompletion, ProviderExecutionError
from axio_fusion_api.registry import load_registry, normalize_profile
from axio_fusion_api.schemas import sha256_text, stable_json


PRIVATE_SOURCE_MARKER = "PRIVATE_SCREENING_SOURCE_MUST_NOT_LEAK"
PRIVATE_PROVIDER_MARKER = "PRIVATE_SCREENING_PROVIDER_MUST_NOT_LEAK"
PRIVATE_MODEL_MARKER = "PRIVATE_SCREENING_MODEL_MUST_NOT_LEAK"
PRIVATE_OUTPUT_MARKER = "PRIVATE_SCREENING_OUTPUT_MUST_NOT_LEAK"


def test_mmlu_pro_case_identity_namespaces_repeated_question_ids(monkeypatch):
    test_rows = [
        {
            "category": "biology",
            "question_id": 1,
            "question": "Which item belongs to biology?",
            "options": ["cell", "orbit"],
            "answer": "A",
        },
        {
            "category": "physics",
            "question_id": 1,
            "question": "Which item belongs to physics?",
            "options": ["orbit", "cell"],
            "answer": "A",
        },
    ]

    def read_parquet(path):
        return test_rows if path.name == "test.parquet" else []

    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._read_parquet",
        read_parquet,
    )
    source = {
        "dataset_path": "test.parquet",
        "validation_path": "validation.parquet",
        "prompt_protocol": {"shots": 0},
    }

    first = _load_mmlu_pro_cases(source)
    second = _load_mmlu_pro_cases(source)

    assert len(first) == 2
    assert len({case.case_id for case in first}) == 2
    assert first == second
    assert all(case.case_id.startswith("mmlu-pro:") for case in first)
    assert all(len(case.case_id.rsplit(":", 1)[-1]) == 64 for case in first)


def test_source_loader_rejects_duplicate_case_identity(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "id": "duplicate",
                    "question": f"Question {index}",
                    "options": ["A", "B"],
                    "answer": "A",
                }
            )
            for index in range(2)
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="screening_source_case_identity_duplicate"):
        _load_source_cases(
            {
                "adapter": "jsonl_multiple_choice",
                "dataset_path": str(path),
            }
        )


def test_official_scorer_dependency_failure_blocks_before_provider_calls(monkeypatch):
    source = {
        "adapter": "livebench_official",
        "harness_root": "/private/livebench",
    }

    def missing_dependency(_root):
        raise ImportError("optional scorer dependency is unavailable")

    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._livebench_scorers",
        missing_dependency,
    )

    assert _screening_adapter_runtime_preflight(source) == [
        "screening_source_runtime_dependency_missing"
    ]


def test_official_scorer_diagnostics_are_silenced_on_failure(monkeypatch, capsys):
    from axio_fusion_api.baseline_screening import (
        _score_screening_output_silently,
    )

    def noisy_failure(_source, _case, _output):
        print("PRIVATE_SCORER_STDOUT_MARKER")
        print("PRIVATE_SCORER_STDERR_MARKER", file=sys.stderr)
        raise RuntimeError("scorer fixture failure")

    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_livebench_output",
        noisy_failure,
    )

    with pytest.raises(RuntimeError, match="scorer fixture failure"):
        _score_screening_output_silently(
            {"adapter": "livebench_official"},
            ScreeningCase(
                "silent-scorer-case",
                "A pinned scorer fixture.",
                "reference",
                "fixture",
                {"task": "zebra_puzzle"},
            ),
            "provider output",
        )

    captured = capsys.readouterr()
    assert "PRIVATE_SCORER_STDOUT_MARKER" not in captured.out
    assert "PRIVATE_SCORER_STDERR_MARKER" not in captured.err


def _write_json(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rehash_campaign_state(state: dict) -> None:
    units = [row for row in state.get("units", []) if isinstance(row, dict)]
    state["unit_set_digest_sha256"] = sha256_text(
        stable_json(
            sorted(
                (
                    {
                        "task_id": str(row.get("task_id") or ""),
                        "status": str(row.get("status") or ""),
                        "mean_score": row.get("mean_score"),
                        "private_unit_content_sha256": str(
                            row.get("private_unit_content_sha256") or ""
                        ),
                    }
                    for row in units
                ),
                key=lambda row: row["task_id"],
            )
        )
    )
    state["campaign_digest_sha256"] = sha256_text(
        stable_json(
            {
                key: value
                for key, value in state.items()
                if key not in {"campaign_digest_sha256", "elapsed_ms"}
            }
        )
    )


def _write_cases(path: Path, source_prefix: str) -> Path:
    rows = [
        {
            "id": f"{source_prefix}-{index}",
            "question": f"Which fixture option is correct for case {index}?",
            "options": ["correct", "incorrect"],
            "answer": "A",
            "category": "fixture-even" if index % 2 == 0 else "fixture-odd",
        }
        for index in range(4)
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _registry_rows():
    common = {
        "source": "live_probe",
        "health": "available",
        "observed_success_count": 5,
        "capabilities": {
            "logic": 0.8,
            "math": 0.8,
            "science_knowledge": 0.8,
            "code": 0.8,
            "structured_output": 0.8,
        },
    }
    return [
        {
            **common,
            "provider": f"{PRIVATE_PROVIDER_MARKER}_SLOW_REPLICA",
            "model": f"{PRIVATE_MODEL_MARKER}_ONE",
            "canonical_model_id": f"{PRIVATE_MODEL_MARKER}_ONE",
            "p50_latency_ms": 900,
        },
        {
            **common,
            "provider": f"{PRIVATE_PROVIDER_MARKER}_FAST_REPLICA",
            "model": f"{PRIVATE_MODEL_MARKER}_ONE",
            "canonical_model_id": f"{PRIVATE_MODEL_MARKER}_ONE",
            "api_format": "responses",
            "p50_latency_ms": 100,
        },
        {
            **common,
            "provider": f"{PRIVATE_PROVIDER_MARKER}_TWO",
            "model": f"{PRIVATE_MODEL_MARKER}_TWO",
            "canonical_model_id": f"{PRIVATE_MODEL_MARKER}_TWO",
            "p50_latency_ms": 200,
        },
        {
            **common,
            "provider": f"{PRIVATE_PROVIDER_MARKER}_THREE",
            "model": f"{PRIVATE_MODEL_MARKER}_THREE",
            "canonical_model_id": f"{PRIVATE_MODEL_MARKER}_THREE",
            "p50_latency_ms": 300,
        },
    ]


def _screening_fixture(tmp_path: Path):
    registry_path = _write_json(
        tmp_path / "registry.private.json",
        {"schema": "axio_fusion_api.registry.v1", "models": _registry_rows()},
    )
    probe_reports = []
    for row in _registry_rows():
        probe_reports.append(
            {
                "provider": row["provider"],
                "status": "ok",
                "base_url_sha256": sha256_text(f"https://{row['provider']}.invalid/v1"),
                "model_count": 1,
                "model_ids": [row["model"]],
            }
        )
    probe_path = _write_json(
        tmp_path / "provider_probe.private.json",
        {
            "schema": "axio_fusion_api.exposed_provider_model_probe.v1",
            "provider_reports": probe_reports,
        },
    )
    source_paths = [
        _write_cases(tmp_path / "source_alpha.private.jsonl", "alpha"),
        _write_cases(tmp_path / "source_beta.private.jsonl", "beta"),
    ]
    sources = []
    for index, dataset_path in enumerate(source_paths, start=1):
        source_id = f"{PRIVATE_SOURCE_MARKER}_{index}"
        source_family = f"private-independent-family-{index}"
        sources.append(
            {
                "source_id": source_id,
                "source_family": source_family,
                "adapter": "jsonl_multiple_choice",
                "source_type": "independent_evaluation_report",
                "retrieved_on": "2026-07-20",
                "supports_general_capability_ranking": True,
                "uses_target_benchmark_results": False,
                "source_locator": f"https://private-source-{index}.invalid/release",
                "dataset_path": str(dataset_path),
                "minimum_case_count": 4,
                "selection": {
                    "strategy": "stratified_sha256_order",
                    "max_per_stratum": 2,
                    "max_cases": 4,
                },
                "prompt_protocol": {
                    "shots": 0,
                    "answer_extraction": "single_terminal_choice",
                    "official_prompt_family": "fixture-multiple-choice",
                },
                "decoding": {
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_output_tokens": 32,
                    "timeout_seconds": 5.0,
                    "max_exception_attempt_rounds": 1,
                },
                "max_transport_failure_rate": 0.25,
                "official_evidence": {
                    "source_type": "official_release",
                    "source_family": f"official-method-family-{index}",
                    "source_locator": f"https://official-method-{index}.invalid/release",
                    "source_snapshot_sha256": sha256_text(
                        f"official-method-snapshot-{index}"
                    ),
                    "retrieved_on": "2026-07-20",
                    "supports_general_capability_ranking": True,
                    "evidence_role": "benchmark_method_and_release_provenance_only",
                    "does_not_attest_model_identity": True,
                },
            }
        )
    manifest_path = _write_json(
        tmp_path / "source_manifest.private.json",
        {
            "schema": "axio_fusion_api.non_target_screening_source_manifest.v1",
            "pre_registration": {
                "declared_before_target_campaign": True,
                "registered_on": "2026-07-20",
                "selection_seed": "fixed-private-screening-seed",
                "target_benchmark_results_used": False,
                "target_suite_results_used": False,
            },
            "sources": sources,
        },
    )
    return registry_path, probe_path, manifest_path


class _RankedFixtureClient:
    def __init__(self):
        self.calls = []

    def complete(self, profile, request, *, prompt, system, timeout=None):
        self.calls.append(profile.profile_id)
        if profile.model.endswith("_ONE"):
            answer = "A"
        elif profile.model.endswith("_TWO"):
            answer = "A" if "case 0" in prompt or "case 2" in prompt else "B"
        else:
            answer = "B"
        return f"{PRIVATE_OUTPUT_MARKER}\n{answer}"


class _SequenceClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def complete(self, profile, request, *, prompt, system, timeout=None):
        self.calls.append(profile.profile_id)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _AdmissionFixtureClient:
    def __init__(self, *, failed_profile_ids=()):
        self.failed_profile_ids = set(failed_profile_ids)

    def complete_turn(self, profile, request, *, prompt, system, timeout):
        del prompt, system, timeout
        workload_id = str(request.metadata.get("workload_id") or "")
        provider_module._record_provider_request_receipt(
            status="success" if profile.profile_id not in self.failed_profile_ids else "failed",
            key_attempt_count=1,
            transport_attempt_count=1,
            retry_attempt_count=0,
            stream_requested=True,
            stream_observed=True,
            stream_fallback_used=False,
            stream_protocol="sse",
            stream_content_type="text/event-stream",
            stream_frame_count=3,
            strict_streaming_requested=True,
        )
        if profile.profile_id in self.failed_profile_ids:
            raise ProviderExecutionError("fixture admission failure", error_code="provider_request_timeout")
        if workload_id.endswith("structured_output"):
            output = json.dumps({"record_id": "record-01", "owner": "team-a", "priority": 8, "reason": "synthetic"})
        elif workload_id == "bounded_constraint_reasoning":
            output = json.dumps({"decision": "C", "checks": 4, "risk": "review load", "alternative": "A"})
        elif workload_id == "long_form_operational_response":
            output = "A bounded review policy should inspect the state before promotion. " * 24
        else:
            output = "record-63 is the largest open quota and belongs to team-d."
        return ProviderCompletion(output)


def _fixture_admission(tmp_path: Path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    profiles = load_registry(registry_path)
    failed_profile = next(
        profile for profile in profiles if profile.provider.endswith("SLOW_REPLICA")
    )
    report = run_operational_admission(
        profiles,
        live=True,
        max_workers=1,
        client=_AdmissionFixtureClient(failed_profile_ids={failed_profile.profile_id}),
    )
    assert report["status"] == "ready"
    assert report["formal_baseline_eligible_count"] == 3
    admission_path = _write_json(tmp_path / "operational_admission.private.json", report)
    return registry_path, probe_path, manifest_path, admission_path, report


def test_operational_admission_filters_baseline_pool_and_is_carried_into_preflight(tmp_path):
    registry_path, probe_path, manifest_path, admission_path, _ = _fixture_admission(tmp_path)

    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
        operational_admission_path=admission_path,
    )

    assert plan["ready"] is True, plan["blockers"]
    assert plan["operational_admission"]["status"] == "ready"
    assert plan["operational_admission"]["filtered_profile_count"] == 3
    assert plan["canonical_model_group_count"] == 3
    assert plan["replica_profile_count"] == 3

    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    preflight = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        state_path=state_path,
        live=False,
        operational_admission_path=admission_path,
    )

    assert preflight["status"] == "preflight_ready"
    assert preflight["operational_admission"]["content_sha256"] == plan["operational_admission"]["content_sha256"]


def test_provider_baseline_freeze_uses_formal_admission_pool_but_binds_full_registry(tmp_path):
    registry_path, _, _, admission_path, _ = _fixture_admission(tmp_path)
    profiles = load_registry(registry_path)
    slow_replica = next(
        profile for profile in profiles if profile.provider.endswith("SLOW_REPLICA")
    )
    slow_replica_hash = sha256_text(slow_replica.profile_id)

    freeze = build_provider_baseline_freeze_manifest(
        registry_path=registry_path,
        max_provider_baselines=None,
        operational_admission_path=admission_path,
    )

    assert freeze["provider_registry_receipt"]["profile_count"] == len(profiles)
    assert freeze["provider_registry_receipt"]["registry_file_sha256"] == _file_sha256(
        registry_path
    )
    assert freeze["operational_admission_receipt"]["status"] == "ready"
    assert freeze["operational_admission_receipt"]["filtered_profile_count"] == 3
    assert freeze["available_provider_replica_profile_count"] == 3
    assert all(
        slow_replica_hash not in row["replica_profile_id_sha256s"]
        for row in freeze["frozen_candidate_rows"]
    )

    freeze_path = _write_json(tmp_path / "provider_baseline_freeze.safe.json", freeze)
    context = _provider_baseline_selection_context(
        profiles,
        include_provider_baselines=True,
        max_provider_baselines=3,
        provider_baseline_freeze_path=freeze_path,
        registry_path=registry_path,
    )

    assert len(context["provider_profiles"]) == 3
    assert slow_replica_hash not in {
        sha256_text(profile.profile_id) for profile in context["provider_profiles"]
    }
    assert "provider_baseline_freeze_external_profile_not_formally_admitted" not in context["blockers"]


def test_admission_bound_campaign_and_ranking_keep_filtered_candidate_pool(tmp_path):
    registry_path, probe_path, manifest_path, admission_path, _ = _fixture_admission(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
        operational_admission_path=admission_path,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"

    campaign = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=3,
        client=_RankedFixtureClient(),
        operational_admission_path=admission_path,
    )
    assert campaign["ready_for_ranking"] is True, campaign["reason_codes"]

    ranking = build_external_ranking_manifest_from_screening(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        operational_admission_path=admission_path,
    )

    assert ranking["screening_conversion_ready"] is True, ranking.get("blockers")
    assert ranking["candidate_inventory_count"] == 3
    assert len(ranking["candidate_inventory"]) == 3


def test_tampered_operational_admission_blocks_screening_plan(tmp_path):
    registry_path, probe_path, manifest_path, admission_path, _ = _fixture_admission(tmp_path)
    payload = json.loads(admission_path.read_text(encoding="utf-8"))
    payload["formal_baseline_eligible_count"] = 2
    _write_json(admission_path, payload)

    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        operational_admission_path=admission_path,
    )

    assert plan["ready"] is False
    assert "operational_admission_formal_count_mismatch" in plan["blockers"]


def test_incomplete_operational_admission_coverage_blocks_screening_plan(tmp_path):
    registry_path, probe_path, manifest_path, admission_path, _ = _fixture_admission(tmp_path)
    payload = json.loads(admission_path.read_text(encoding="utf-8"))
    payload["profiles"] = payload["profiles"][:-1]
    _write_json(admission_path, payload)

    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        operational_admission_path=admission_path,
    )

    assert plan["ready"] is False
    assert "operational_admission_profile_coverage_incomplete" in plan["blockers"]


def test_redacted_operational_admission_cannot_cross_private_screening_boundary(tmp_path):
    registry_path, probe_path, manifest_path, admission_path, report = _fixture_admission(tmp_path)
    redacted_path = _write_json(
        tmp_path / "operational_admission.safe.json",
        redact_operational_admission(report),
    )

    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        operational_admission_path=redacted_path,
    )

    assert plan["ready"] is False
    assert "operational_admission_profile_coverage_incomplete" in plan["blockers"]


def test_operational_admission_digest_change_invalidates_existing_screening_plan(tmp_path):
    registry_path, probe_path, manifest_path, admission_path, _ = _fixture_admission(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        operational_admission_path=admission_path,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    payload = json.loads(admission_path.read_text(encoding="utf-8"))
    payload["selection_policy"]["operator_annotation"] = "receipt-content-changed"
    _write_json(admission_path, payload)

    blocked = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        state_path=tmp_path / "campaign_state.safe.json",
        live=False,
        operational_admission_path=admission_path,
    )

    assert blocked["status"] == "blocked"
    assert "screening_plan_current_inputs_mismatch" in blocked["reason_codes"]


def test_plan_uses_same_canonical_representatives_as_freeze_and_is_hash_only(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )
    template = build_external_provider_ranking_template(registry_path=registry_path)

    assert plan["schema"] == SCREENING_PLAN_SCHEMA
    assert plan["ready"] is True, plan["blockers"]
    assert plan["canonical_model_group_count"] == 3
    assert plan["replica_profile_count"] == 4
    assert plan["task_count"] == 6
    assert plan["ranking_policy"]["transport_failure_score_policy"] == (
        "exclude_missing_observations_after_pre_registered_rate_gate"
    )
    for source in plan["sources"]:
        retry_policy = source["exception_retry_policy"]
        assert retry_policy["schema"] == (
            "axio_fusion_api.non_target_screening_exception_retry_policy.v1"
        )
        assert retry_policy["max_exception_attempt_rounds"] == 1
        assert retry_policy["backoff_strategy"] == "fixed"
        assert retry_policy["backoff_ms"] == 250.0
        assert retry_policy["retry_on_wrong_answer"] is False
    plan_groups = {
        (
            row["canonical_identity_sha256"],
            row["representative_profile_id_sha256"],
            row["candidate_id_sha256"],
        )
        for row in plan["candidate_groups"]
    }
    template_groups = {
        (
            row["canonical_identity_sha256"],
            row["profile_id_sha256"],
            row["candidate_id_sha256"],
        )
        for row in template["candidate_inventory"]
    }
    assert plan_groups == template_groups
    same_group = next(row for row in plan["candidate_groups"] if row["replica_count"] == 2)
    profiles = load_registry(registry_path)
    expected_representative = next(
        row["representative"]
        for row in _canonical_live_groups(profiles)
        if row["replica_count"] == 2
    )
    assert expected_representative.provider.endswith("FAST_REPLICA")
    assert same_group["representative_profile_id_sha256"] == sha256_text(
        expected_representative.profile_id
    )

    serialized = json.dumps(plan, ensure_ascii=False)
    assert PRIVATE_SOURCE_MARKER not in serialized
    assert PRIVATE_PROVIDER_MARKER not in serialized
    assert PRIVATE_MODEL_MARKER not in serialized
    assert "private-source-1.invalid" not in serialized
    assert str(tmp_path) not in serialized
    assert '"source_id":' not in serialized
    assert '"source_locator":' not in serialized
    assert '"raw_provider_outputs_persisted": true' not in serialized
    assert '"secrets_persisted": true' not in serialized


def test_screening_timeout_is_explicitly_capped_at_shared_provider_limit(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        source["decoding"]["timeout_seconds"] = 600.0
    _write_json(manifest_path, manifest)

    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )

    assert plan["ready"] is True, plan["blockers"]
    assert all(row["configured_timeout_seconds"] == 600.0 for row in plan["sources"])
    assert all(row["effective_timeout_seconds"] == 90.0 for row in plan["sources"])
    assert all(row["timeout_cap_seconds"] == 90.0 for row in plan["sources"])
    assert all(row["timeout_cap_applied"] is True for row in plan["sources"])

    class _TimeoutClient:
        def __init__(self):
            self.timeouts = []

        def complete(self, profile, request, *, prompt, system, timeout=None):
            self.timeouts.append(timeout)
            return "A"

    client = _TimeoutClient()
    result = _run_screening_case(
        case=ScreeningCase(
            case_id="timeout-cap",
            prompt="Choose A or B.",
            reference="A",
            stratum="fixture",
            metadata={},
        ),
        source={"adapter": "jsonl_multiple_choice"},
        replicas=[normalize_profile(_registry_rows()[2])],
        client=client,
        decoding={"timeout_seconds": 600.0, "max_output_tokens": 8},
        system_prompt="fixture",
    )
    assert result["status"] == "completed"
    assert client.timeouts == [90.0]


def test_plan_freezes_seeded_interleaved_counterbalanced_task_schedule(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    first = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )
    second = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )

    assert first["plan_digest_sha256"] == second["plan_digest_sha256"]
    assert first["tasks"] == second["tasks"]
    schedule = first["execution_schedule"]
    assert schedule["strategy"] == "seeded_paired_reverse_source_interleave_v1"
    assert schedule["task_order_frozen_before_provider_calls"] is True
    assert [row["execution_index"] for row in first["tasks"]] == list(range(6))

    source_order = []
    per_source_positions = {}
    for index, task in enumerate(first["tasks"]):
        source_hash = task["source_id_sha256"]
        if source_hash not in source_order:
            source_order.append(source_hash)
        per_source_positions.setdefault(source_hash, {})[
            task["canonical_identity_sha256"]
        ] = index
    assert len(source_order) == 2
    assert [row["source_id_sha256"] for row in first["tasks"]] == source_order * 3
    pair_sums = {
        per_source_positions[source_order[0]][candidate]
        + per_source_positions[source_order[1]][candidate]
        for candidate in per_source_positions[source_order[0]]
    }
    assert len(pair_sums) == 1


def test_plan_digest_binds_frozen_worker_limit(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    serial = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
    )
    parallel = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=2,
    )

    assert serial["ready"] is True, serial["blockers"]
    assert parallel["ready"] is True, parallel["blockers"]
    assert serial["max_workers"] == 1
    assert parallel["max_workers"] == 2
    assert serial["tasks"] == parallel["tasks"]
    assert serial["plan_digest_sha256"] != parallel["plan_digest_sha256"]


def test_fail_fast_transport_gate_is_explicit_and_serial_only(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    serial = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
    )
    fail_fast = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
        fail_fast_transport_failure_gate=True,
    )
    parallel = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=2,
        fail_fast_transport_failure_gate=True,
    )

    assert serial["ready"] is True, serial["blockers"]
    assert fail_fast["ready"] is True, fail_fast["blockers"]
    assert fail_fast["fail_fast_policy"]["enabled"] is True
    assert fail_fast["plan_digest_sha256"] != serial["plan_digest_sha256"]
    assert parallel["ready"] is False
    assert "screening_fail_fast_requires_serial_execution" in parallel["blockers"]


def test_fail_fast_transport_gate_preserves_complete_failure_denominator(tmp_path):
    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "fail-fast-source",
        "adapter": "jsonl_multiple_choice",
        "prompt_protocol": {"system_prompt": ""},
        "decoding": {"max_exception_attempt_rounds": 1, "max_output_tokens": 8},
    }
    cases = [
        ScreeningCase(f"fail-fast-{index}", "Choose A or B.", "A", "fixture", {})
        for index in range(4)
    ]
    profile_hash = sha256_text(profile.profile_id)
    task = {
        "task_id": sha256_text("fail-fast-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
        "source_snapshot_sha256": sha256_text("fail-fast-snapshot"),
        "case_set_digest_sha256": sha256_text("fail-fast-cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("fail-fast-candidate"),
        "representative_profile_id_sha256": profile_hash,
        "replica_profile_id_sha256s": [profile_hash],
    }
    client = _SequenceClient(
        [RuntimeError("transport fixture") for _ in range(3)]
    )

    unit = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt={
            "selected_case_count": 4,
            "max_transport_failure_rate": 0.5,
        },
        cases=cases,
        replicas=[profile],
        private_root=tmp_path / "private-units",
        client=client,
        max_workers=1,
        fail_fast_transport_failure_gate=True,
    )

    assert len(client.calls) == 3
    assert unit["status"] == "failed"
    assert unit["fail_fast_policy_enabled"] is True
    assert unit["fail_fast_triggered"] is True
    assert unit["fail_fast_failure_cutoff"] == 3
    assert unit["fail_fast_unattempted_case_count"] == 1
    assert unit["transport_failure_count"] == 4
    assert unit["transport_failure_rate"] == 1.0
    assert sum(
        row["fail_fast_unattempted"] for row in unit["case_results"]
    ) == 1

    resumed_client = _SequenceClient(
        [RuntimeError("transport fixture") for _ in range(3)]
    )
    resumed = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt={
            "selected_case_count": 4,
            "max_transport_failure_rate": 0.5,
        },
        cases=cases,
        replicas=[profile],
        private_root=tmp_path / "private-units",
        client=resumed_client,
        max_workers=1,
        fail_fast_transport_failure_gate=True,
        previous_unit=unit,
    )
    assert len(resumed_client.calls) == 3
    assert resumed["transport_failure_count"] == 4
    assert resumed["fail_fast_unattempted_case_count"] == 1


def _transport_admission_fixture(tmp_path: Path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    fourth = {
        **_registry_rows()[3],
        "provider": f"{PRIVATE_PROVIDER_MARKER}_FOUR",
        "model": f"{PRIVATE_MODEL_MARKER}_FOUR",
        "canonical_model_id": f"{PRIVATE_MODEL_MARKER}_FOUR",
    }
    registry_payload["models"].append(fourth)
    _write_json(registry_path, registry_payload)
    probe_payload = json.loads(probe_path.read_text(encoding="utf-8"))
    probe_payload["provider_reports"].append(
        {
            "provider": fourth["provider"],
            "status": "ok",
            "base_url_sha256": sha256_text(f"https://{fourth['provider']}.invalid/v1"),
            "model_count": 1,
            "model_ids": [fourth["model"]],
        }
    )
    _write_json(probe_path, probe_payload)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
    )
    assert plan["ready"] is True, plan["blockers"]
    plan_path = _write_json(tmp_path / "transport-source-plan.safe.json", plan)
    failed_canonical = plan["candidate_groups"][0]["canonical_identity_sha256"]
    units = []
    for task in plan["tasks"]:
        failed = task["canonical_identity_sha256"] == failed_canonical
        units.append(
            {
                "task_id": task["task_id"],
                "source_id_sha256": task["source_id_sha256"],
                "canonical_identity_sha256": task["canonical_identity_sha256"],
                "status": "failed" if failed else "completed",
                "transport_failure_count": 2 if failed else 0,
                "transport_failure_rate": 0.5 if failed else 0.0,
                "fail_fast_unattempted_case_count": 0,
                "reason_codes": [],
                "private_unit_content_sha256": sha256_text(task["task_id"]),
            }
        )
    state = {
        "schema": SCREENING_CAMPAIGN_SCHEMA,
        "mode": "live",
        "status": "partial",
        "plan_file_content_sha256": _file_sha256(plan_path),
        "plan_digest_sha256": plan["plan_digest_sha256"],
        "registry_file_sha256": _file_sha256(registry_path),
        "source_manifest_content_sha256": plan["source_manifest_content_sha256"],
        "network_calls_performed": True,
        "target_suite_calls_performed": False,
        "benchmark_outputs_used_for_training": False,
        "benchmark_outputs_used_for_prompt_tuning": False,
        "units": units,
        "elapsed_ms": 1.0,
    }
    _rehash_campaign_state(state)
    state_path = _write_json(tmp_path / "transport-source-campaign.private.json", state)
    return registry_path, probe_path, manifest_path, plan_path, state_path, plan, failed_canonical


def test_transport_availability_admission_filters_only_failed_transport_candidates(tmp_path):
    registry_path, probe_path, manifest_path, plan_path, state_path, plan, failed_canonical = _transport_admission_fixture(tmp_path)

    receipt = build_transport_availability_admission(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        min_canonical_models=3,
    )

    assert receipt["schema"] == SCREENING_TRANSPORT_ADMISSION_SCHEMA
    assert receipt["status"] == "ready", receipt["blockers"]
    assert receipt["eligible_canonical_model_count"] == 3
    assert failed_canonical not in receipt["eligible_canonical_identity_sha256s"]
    assert receipt["quality_fields_used_for_selection"] == []
    assert receipt["no_cheat_contract"]["uses_benchmark_scores"] is False

    receipt_path = _write_json(tmp_path / "transport-admission.private.json", receipt)
    successor = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
        transport_availability_path=receipt_path,
    )

    assert successor["ready"] is True, successor["blockers"]
    assert successor["transport_availability"]["status"] == "ready"
    assert successor["canonical_model_group_count"] == 3
    assert successor["replica_profile_count"] == 4


def test_transport_availability_admission_rejects_quality_selection_or_campaign_tamper(tmp_path):
    registry_path, probe_path, manifest_path, plan_path, state_path, _, _ = _transport_admission_fixture(tmp_path)
    receipt = build_transport_availability_admission(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        min_canonical_models=3,
    )
    receipt["quality_fields_used_for_selection"] = ["mean_score"]
    tampered_receipt_path = _write_json(
        tmp_path / "transport-admission-tampered.private.json", receipt
    )
    # The receipt builder itself remains the trust boundary; a tampered
    # receipt cannot be bound into a successor plan.
    successor = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
        transport_availability_path=tampered_receipt_path,
    )
    assert successor["ready"] is False
    assert "screening_transport_admission_quality_selection_present" in successor["blockers"]


def test_identity_attestation_requires_exact_catalog_alias(tmp_path):
    registry_path, probe_path, _ = _screening_fixture(tmp_path)
    profiles = load_registry(registry_path)
    ready = build_provider_identity_attestation_receipt(
        profiles=profiles,
        private_probe_files=[probe_path],
        attested_on="2026-07-20",
    )
    assert ready["ready"] is True
    assert ready["attested_profile_count"] == 4
    assert (
        ready["provider_identity_normalization"]
        == "casefold_and_replace_underscore_with_hyphen"
    )

    provider_alias_row = dict(_registry_rows()[0])
    provider_alias_row["provider"] = provider_alias_row["provider"].replace(
        "_", "-"
    )
    provider_alias = normalize_profile(provider_alias_row)
    aliased = build_provider_identity_attestation_receipt(
        profiles=[provider_alias],
        private_probe_files=[probe_path],
        attested_on="2026-07-20",
    )
    assert aliased["ready"] is True
    assert aliased["attested_profile_count"] == 1

    renamed = normalize_profile(
        {
            **_registry_rows()[0],
            "canonical_model_id": "different-canonical-model",
        }
    )
    blocked = build_provider_identity_attestation_receipt(
        profiles=[renamed],
        private_probe_files=[probe_path],
        attested_on="2026-07-20",
    )
    assert blocked["ready"] is False
    assert "screening_identity_alias_requires_manual_attestation" in blocked["blockers"]


def test_wrong_answer_is_scored_once_without_replica_retry():
    replicas = [
        normalize_profile(_registry_rows()[0]),
        normalize_profile(_registry_rows()[1]),
    ]
    client = _SequenceClient(["B", "A"])
    result = _run_screening_case(
        case=ScreeningCase(
            case_id="wrong-answer-no-retry",
            prompt="Choose A or B.",
            reference="A",
            stratum="fixture",
            metadata={"adapter": "jsonl_multiple_choice"},
        ),
        source={"adapter": "jsonl_multiple_choice"},
        replicas=replicas,
        client=client,
        decoding={
            "max_exception_attempt_rounds": 2,
            "exception_retry_backoff_ms": 1,
            "max_output_tokens": 8,
        },
        system_prompt="fixture",
    )

    assert result["status"] == "completed"
    assert result["score"] == 0.0
    assert len(client.calls) == 1
    assert len(result["attempts"]) == 1
    assert result["retry_receipts"] == []


def test_provider_rejection_uses_next_replica_without_repeat_round():
    replicas = [
        normalize_profile(_registry_rows()[0]),
        normalize_profile(_registry_rows()[1]),
    ]
    client = _SequenceClient(
        [
            ProviderExecutionError(
                "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST",
                error_code="http_error",
                http_status=400,
            ),
            "A",
        ]
    )
    result = _run_screening_case(
        case=ScreeningCase(
            case_id="transport-failover",
            prompt="Choose A or B.",
            reference="A",
            stratum="fixture",
            metadata={"adapter": "jsonl_multiple_choice"},
        ),
        source={"adapter": "jsonl_multiple_choice"},
        replicas=replicas,
        client=client,
        decoding={
            "max_exception_attempt_rounds": 2,
            "exception_retry_backoff_ms": 1,
            "max_output_tokens": 8,
        },
        system_prompt="fixture",
    )

    assert result["status"] == "completed"
    assert result["score"] == 1.0
    assert len(client.calls) == 2
    assert [row["status"] for row in result["attempts"]] == ["failed", "completed"]
    assert result["attempts"][0]["provider_error_code"] == "http_error"
    assert result["attempts"][0]["http_status"] == 400
    assert result["attempts"][0]["transport_failure_class"] == "provider_http_4xx"
    assert result["attempts"][0]["retryable"] is False
    assert result["retry_receipts"] == []
    assert "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST" not in json.dumps(result)


def test_retryable_failover_success_in_same_round_does_not_require_retry_receipt():
    replicas = [
        normalize_profile(_registry_rows()[0]),
        normalize_profile(_registry_rows()[1]),
    ]
    decoding = {
        "max_exception_attempt_rounds": 2,
        "exception_retry_backoff_ms": 1,
        "max_output_tokens": 8,
    }
    client = _SequenceClient(
        [
            ProviderExecutionError(
                "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST",
                error_code="provider_request_timeout",
            ),
            "A",
        ]
    )

    result = _run_screening_case(
        case=ScreeningCase(
            case_id="retryable-failover-same-round",
            prompt="Choose A or B.",
            reference="A",
            stratum="fixture",
            metadata={"adapter": "jsonl_multiple_choice"},
        ),
        source={"adapter": "jsonl_multiple_choice"},
        replicas=replicas,
        client=client,
        decoding=decoding,
        system_prompt="fixture",
    )

    assert result["status"] == "completed"
    assert [row["round"] for row in result["attempts"]] == [1, 1]
    assert [row["status"] for row in result["attempts"]] == ["failed", "completed"]
    assert result["retry_receipts"] == []
    assert _screening_retry_contract_errors(result, decoding) == []


@pytest.mark.parametrize(
    ("error_code", "http_status", "failure_class"),
    [
        ("http_error", 429, "rate_limited"),
        ("http_error", 503, "provider_http_5xx"),
        ("provider_request_timeout", None, "timeout"),
        ("invalid_stream_json", None, "stream_or_response_protocol"),
    ],
)
def test_retryable_provider_failures_use_fixed_second_round(
    monkeypatch,
    error_code,
    http_status,
    failure_class,
):
    profile = normalize_profile(_registry_rows()[2])
    client = _SequenceClient(
        [
            ProviderExecutionError(
                "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST",
                error_code=error_code,
                http_status=http_status,
            ),
            "A",
        ]
    )
    sleep_calls = []
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    result = _run_screening_case(
        case=ScreeningCase(
            case_id=f"retryable-{error_code}-{http_status}",
            prompt="Choose A or B.",
            reference="A",
            stratum="fixture",
            metadata={"adapter": "jsonl_multiple_choice"},
        ),
        source={"adapter": "jsonl_multiple_choice"},
        replicas=[profile],
        client=client,
        decoding={
            "max_exception_attempt_rounds": 2,
            "exception_retry_backoff_ms": 7,
            "max_output_tokens": 8,
        },
        system_prompt="fixture",
    )

    assert result["status"] == "completed"
    assert result["score"] == 1.0
    assert len(client.calls) == 2
    assert result["attempts"][0]["provider_error_code"] == error_code
    assert result["attempts"][0]["http_status"] == http_status
    assert result["attempts"][0]["transport_failure_class"] == failure_class
    assert result["attempts"][0]["retryable"] is True
    assert result["retry_receipts"] == [
        {
            "after_round": 1,
            "before_round": 2,
            "eligible_profile_count": 1,
            "delay_ms": 7.0,
            "backoff_strategy": "fixed",
            "trigger_failure_classes": [failure_class],
        }
    ]
    assert sleep_calls == [0.007]
    assert "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST" not in json.dumps(result)


def test_retry_contract_rejects_tampered_fixed_backoff(monkeypatch):
    profile = normalize_profile(_registry_rows()[2])
    client = _SequenceClient(
        [
            ProviderExecutionError(
                "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST",
                error_code="http_error",
                http_status=429,
            ),
            "A",
        ]
    )
    monkeypatch.setattr("axio_fusion_api.baseline_screening.time.sleep", lambda _: None)
    decoding = {
        "max_exception_attempt_rounds": 2,
        "exception_retry_backoff_ms": 7,
        "max_output_tokens": 8,
    }
    result = _run_screening_case(
        case=ScreeningCase(
            case_id="retry-contract-tamper",
            prompt="Choose A or B.",
            reference="A",
            stratum="fixture",
            metadata={"adapter": "jsonl_multiple_choice"},
        ),
        source={"adapter": "jsonl_multiple_choice"},
        replicas=[profile],
        client=client,
        decoding=decoding,
        system_prompt="fixture",
    )

    assert _screening_retry_contract_errors(result, decoding) == []
    result["retry_receipts"][0]["delay_ms"] = 8.0
    assert _screening_retry_contract_errors(result, decoding) == [
        "screening_retry_receipt_policy_mismatch"
    ]


def test_safe_unit_projects_attempt_failure_telemetry(tmp_path, monkeypatch):
    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "safe-failure-telemetry-source",
        "adapter": "jsonl_multiple_choice",
        "prompt_protocol": {"system_prompt": ""},
        "decoding": {
            "temperature": 0.0,
            "max_output_tokens": 8,
            "max_exception_attempt_rounds": 2,
            "exception_retry_backoff_ms": 1,
        },
    }
    task = {
        "task_id": sha256_text("safe-failure-telemetry-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
        "source_snapshot_sha256": sha256_text("safe-failure-telemetry-snapshot"),
        "case_set_digest_sha256": sha256_text("safe-failure-telemetry-cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("safe-failure-telemetry-candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    monkeypatch.setattr("axio_fusion_api.baseline_screening.time.sleep", lambda _: None)
    client = _SequenceClient(
        [
            ProviderExecutionError(
                "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST",
                error_code="http_error",
                http_status=429,
            ),
            "A",
        ]
    )

    unit = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt={
            "selected_case_count": 1,
            "max_transport_failure_rate": 0.0,
        },
        cases=[
            ScreeningCase(
                "safe-failure-telemetry-case",
                "Choose A or B.",
                "A",
                "fixture",
                {"adapter": "jsonl_multiple_choice"},
            )
        ],
        replicas=[profile],
        private_root=tmp_path / "private-units",
        client=client,
        max_workers=1,
    )

    telemetry = unit["provider_failure_telemetry"]
    assert telemetry["provider_attempt_count"] == 2
    assert telemetry["provider_failure_attempt_count"] == 1
    assert telemetry["recovered_transport_failure_case_count"] == 1
    assert telemetry["transport_failure_class_counts"] == [
        {"transport_failure_class": "rate_limited", "count": 1}
    ]
    assert telemetry["http_status_counts"] == [{"http_status": 429, "count": 1}]
    case_telemetry = unit["case_results"][0]["failure_telemetry"]
    assert case_telemetry["retry_round_count"] == 1
    serialized = json.dumps(unit)
    assert "PRIVATE_PROVIDER_ERROR_MUST_NOT_PERSIST" not in serialized
    assert PRIVATE_OUTPUT_MARKER not in serialized


def test_transport_failure_is_missing_data_when_within_failure_rate(tmp_path):
    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "transport-missing-data-source",
        "adapter": "jsonl_multiple_choice",
        "prompt_protocol": {"system_prompt": ""},
        "decoding": {
            "temperature": 0.0,
            "max_output_tokens": 8,
            "max_exception_attempt_rounds": 1,
        },
    }
    cases = [
        ScreeningCase(
            "transport-missing-case",
            "Choose A for the missing-data case.",
            "A",
            "fixture",
            {"adapter": "jsonl_multiple_choice"},
        ),
        ScreeningCase(
            "scored-case",
            "Choose A for the scored case.",
            "A",
            "fixture",
            {"adapter": "jsonl_multiple_choice"},
        ),
    ]
    profile_hash = sha256_text(profile.profile_id)
    task = {
        "task_id": sha256_text("transport-missing-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
        "source_snapshot_sha256": sha256_text("transport-missing-snapshot"),
        "case_set_digest_sha256": sha256_text("transport-missing-cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("transport-missing-candidate"),
        "representative_profile_id_sha256": profile_hash,
        "replica_profile_id_sha256s": [profile_hash],
    }
    client = _SequenceClient([RuntimeError("transport fixture"), "A"])

    unit = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt={
            "selected_case_count": 2,
            "max_transport_failure_rate": 0.5,
        },
        cases=cases,
        replicas=[profile],
        private_root=tmp_path / "private-units",
        client=client,
        max_workers=1,
    )

    assert unit["status"] == "completed"
    assert unit["transport_failure_count"] == 1
    assert unit["scored_case_count"] == 1
    assert unit["mean_score"] == 1.0
    assert all(
        row["score"] is None
        for row in unit["case_results"]
        if row["status"] == "transport_failed"
    )


def test_failed_unit_resume_retries_only_unanswered_cases(tmp_path):
    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "private-resume-source",
        "adapter": "jsonl_multiple_choice",
        "prompt_protocol": {"system_prompt": ""},
        "decoding": {
            "temperature": 0.0,
            "max_output_tokens": 8,
            "max_exception_attempt_rounds": 1,
        },
    }
    cases = [
        ScreeningCase("case-wrong", "First case", "A", "fixture", {}),
        ScreeningCase("case-transport", "Second case", "A", "fixture", {}),
    ]
    task = {
        "task_id": sha256_text("resume-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
        "source_snapshot_sha256": sha256_text("source-snapshot"),
        "case_set_digest_sha256": sha256_text("case-set"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    source_receipt = {
        "selected_case_count": 2,
        "max_transport_failure_rate": 0.0,
    }
    first_client = _SequenceClient(["B", RuntimeError("transport fixture")])
    first = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt=source_receipt,
        cases=cases,
        replicas=[profile],
        private_root=tmp_path / "private-units",
        client=first_client,
        max_workers=1,
    )
    assert first["status"] == "failed"
    assert first["mean_score"] == 0.0
    assert len(first_client.calls) == 2

    retry_client = _SequenceClient(["A"])
    resumed = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt=source_receipt,
        cases=cases,
        replicas=[profile],
        private_root=tmp_path / "private-units",
        client=retry_client,
        max_workers=1,
        previous_unit=first,
    )

    assert resumed["status"] == "completed"
    assert resumed["mean_score"] == 0.5
    assert retry_client.calls == [profile.profile_id]
    scores = {
        row["case_id_sha256"]: row["score"] for row in resumed["case_results"]
    }
    assert scores[sha256_text("case-wrong")] == 0.0
    assert scores[sha256_text("case-transport")] == 1.0


def test_scorer_error_resume_reuses_answer_without_provider_call(tmp_path, monkeypatch):
    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "private-scorer-resume-source",
        "adapter": "jsonl_multiple_choice",
    }
    case = ScreeningCase("case-scored-later", "Choose A or B.", "A", "fixture", {})
    task = {
        "task_id": sha256_text("scorer-resume-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
    }
    unit_path = tmp_path / "private" / "unit.private.json"
    output = "A"
    payload = {
        "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
        "task_id": task["task_id"],
        "source_id": source["source_id"],
        "case_results": [
            {
                "case_id": case.case_id,
                "status": "scorer_error",
                "score": None,
                "output": output,
                "output_sha256": sha256_text(output),
                "latency_ms": 123.0,
                "attempts": [{"profile_id_sha256": sha256_text(profile.profile_id)}],
                "selected_replica_profile_id_sha256": sha256_text(profile.profile_id),
                "error_type": "MissingOptionalScorer",
            }
        ],
    }
    unit_path.parent.mkdir(parents=True)
    unit_path.write_text(json.dumps(payload), encoding="utf-8")

    def scorer(_source, _case, _output):
        return 1.0

    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        scorer,
    )
    preserved, error = _private_resume_case_results(
        unit_path=unit_path,
        previous_unit={
            "status": "failed",
            "private_unit_content_sha256": _file_sha256(unit_path),
        },
        task=task,
        source=source,
        cases=[case],
    )

    assert error == ""
    assert list(preserved) == [case.case_id]
    assert preserved[case.case_id]["status"] == "completed"
    assert preserved[case.case_id]["score"] == 1.0
    assert preserved[case.case_id]["output"] == output


def test_inflight_private_checkpoint_resumes_without_safe_unit(tmp_path):
    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "private-inflight-source",
        "adapter": "jsonl_multiple_choice",
    }
    cases = [
        ScreeningCase("inflight-done", "Choose A.", "A", "fixture", {}),
        ScreeningCase("inflight-pending", "Choose A again.", "A", "fixture", {}),
    ]
    task = {
        "task_id": sha256_text("inflight-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("inflight-candidate"),
    }
    private_root = tmp_path / "private-units"
    done_output = "A"
    _persist_screening_private_checkpoint(
        _screening_checkpoint_path(private_root, task),
        task=task,
        private_source_id=source["source_id"],
        case_results=[
            {
                "case_id": cases[0].case_id,
                "status": "completed",
                "score": 1.0,
                "output": done_output,
                "output_sha256": sha256_text(done_output),
                "latency_ms": 10.0,
                "attempts": [],
                "selected_replica_profile_id_sha256": sha256_text(profile.profile_id),
            }
        ],
        expected_case_count=len(cases),
    )

    preserved, error = _private_resume_case_results(
        unit_path=_screening_unit_path(private_root, task),
        previous_unit=None,
        task=task,
        source=source,
        cases=cases,
    )

    assert error == ""
    assert list(preserved) == [cases[0].case_id]
    assert preserved[cases[0].case_id]["score"] == 1.0
    assert cases[1].case_id not in preserved


def test_private_checkpoint_recovery_rebuilds_safe_unit_index(tmp_path, monkeypatch):
    from axio_fusion_api.baseline_screening import _recover_private_checkpoint_state

    profile = normalize_profile(_registry_rows()[2])
    source = {"source_id": "recover-source", "adapter": "jsonl_multiple_choice"}
    case = ScreeningCase("recover-case", "Choose A.", "A", "fixture", {})
    task = {
        "task_id": sha256_text("recover-task"),
        "source_id_sha256": sha256_text(source["source_id"]),
        "source_snapshot_sha256": sha256_text("snapshot"),
        "case_set_digest_sha256": sha256_text("cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    unit_path = tmp_path / "units" / task["source_id_sha256"][:16] / f"{task['task_id']}.private.json"
    unit_path.parent.mkdir(parents=True)
    output = "A"
    unit_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
                "task_id": task["task_id"],
                "source_id": source["source_id"],
                "canonical_identity_sha256": task["canonical_identity_sha256"],
                "candidate_id_sha256": task["candidate_id_sha256"],
                "case_results": [
                    {
                        "case_id": case.case_id,
                        "status": "completed",
                        "score": 1.0,
                        "output": output,
                        "output_sha256": sha256_text(output),
                        "latency_ms": 10.0,
                        "attempts": [],
                        "selected_replica_profile_id_sha256": sha256_text(profile.profile_id),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda *_args: 1.0,
    )
    recovered = _recover_private_checkpoint_state(
        {
            "schema": SCREENING_CAMPAIGN_SCHEMA,
            "status": "blocked",
            "units": [],
        },
        base_state={
            "schema": SCREENING_CAMPAIGN_SCHEMA,
            "mode": "live",
            "planned_task_count": 1,
            "network_calls_performed": False,
        },
        task_rows=[task],
        raw_sources={task["source_id_sha256"]: source},
        selected_cases={task["source_id_sha256"]: [case]},
        source_receipts={
            task["source_id_sha256"]: {
                "max_transport_failure_rate": 0.0,
            }
        },
        private_root=tmp_path / "units",
    )
    assert recovered["status"] == "partial"
    assert recovered["units"][0]["task_id"] == task["task_id"]
    assert recovered["units"][0]["status"] == "completed"
    assert recovered["units"][0]["mean_score"] == 1.0
    assert recovered["reason_codes"] == ["screening_private_checkpoint_recovered"]


def test_private_checkpoint_recovery_keeps_transport_failure_score_null(
    tmp_path,
    monkeypatch,
):
    from axio_fusion_api.baseline_screening import (
        _rebuild_safe_unit_from_private_artifact,
        _verify_screening_unit_private_artifact,
    )

    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "recover-transport-source",
        "adapter": "jsonl_multiple_choice",
    }
    source_hash = sha256_text(source["source_id"])
    cases = [
        ScreeningCase("recover-completed", "Choose A.", "A", "fixture", {}),
        ScreeningCase("recover-transport", "Choose A again.", "A", "fixture", {}),
    ]
    task = {
        "task_id": sha256_text("recover-transport-task"),
        "source_id_sha256": source_hash,
        "source_snapshot_sha256": sha256_text("snapshot"),
        "case_set_digest_sha256": sha256_text("cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    private_root = tmp_path / "units"
    unit_path = _screening_unit_path(private_root, task)
    unit_path.parent.mkdir(parents=True)
    output = "A"
    unit_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
                "task_id": task["task_id"],
                "source_id": source["source_id"],
                "canonical_identity_sha256": task["canonical_identity_sha256"],
                "candidate_id_sha256": task["candidate_id_sha256"],
                "case_results": [
                    {
                        "case_id": cases[0].case_id,
                        "status": "completed",
                        "score": 1.0,
                        "output": output,
                        "output_sha256": sha256_text(output),
                        "latency_ms": 10.0,
                        "attempts": [],
                        "selected_replica_profile_id_sha256": sha256_text(
                            profile.profile_id
                        ),
                    },
                    {
                        "case_id": cases[1].case_id,
                        "status": "transport_failed",
                        "score": None,
                        "output": "",
                        "output_sha256": sha256_text(""),
                        "latency_ms": 20.0,
                        "attempts": [],
                        "selected_replica_profile_id_sha256": "",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda *_args: 1.0,
    )

    rebuilt = _rebuild_safe_unit_from_private_artifact(
        task=task,
        source=source,
        source_receipt={"max_transport_failure_rate": 0.5},
        cases=cases,
        private_root=private_root,
    )

    assert rebuilt is not None
    assert rebuilt["status"] == "completed"
    assert rebuilt["scored_case_count"] == 1
    assert rebuilt["transport_failure_count"] == 1
    assert rebuilt["mean_score"] == 1.0
    failed_case = next(
        row
        for row in rebuilt["case_results"]
        if row["case_id_sha256"] == sha256_text(cases[1].case_id)
    )
    assert failed_case["status"] == "transport_failed"
    assert failed_case["score"] is None
    assert _verify_screening_unit_private_artifact(
        task=task,
        unit=rebuilt,
        source=source,
        cases=cases,
        private_root=private_root,
    ) == []


def test_private_checkpoint_recovery_hashes_existing_and_recovered_units(
    tmp_path,
    monkeypatch,
):
    from axio_fusion_api.baseline_screening import _recover_private_checkpoint_state

    profile = normalize_profile(_registry_rows()[2])
    source = {"source_id": "recover-merged-source", "adapter": "jsonl_multiple_choice"}
    source_hash = sha256_text(source["source_id"])
    case = ScreeningCase("recover-merged-case", "Choose A.", "A", "fixture", {})

    def task_for(label: str) -> dict:
        return {
            "task_id": sha256_text(label),
            "source_id_sha256": source_hash,
            "source_snapshot_sha256": sha256_text("snapshot"),
            "case_set_digest_sha256": sha256_text("cases"),
            "canonical_identity_sha256": profile.canonical_identity_sha256,
            "candidate_id_sha256": sha256_text(label),
            "representative_profile_id_sha256": sha256_text(profile.profile_id),
            "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
        }

    existing_task = task_for("recover-existing-task")
    recovered_task = task_for("recover-new-task")
    unit_path = _screening_unit_path(tmp_path / "units", recovered_task)
    unit_path.parent.mkdir(parents=True)
    output = "A"
    unit_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
                "task_id": recovered_task["task_id"],
                "source_id": source["source_id"],
                "canonical_identity_sha256": recovered_task[
                    "canonical_identity_sha256"
                ],
                "candidate_id_sha256": recovered_task["candidate_id_sha256"],
                "case_results": [
                    {
                        "case_id": case.case_id,
                        "status": "completed",
                        "score": 1.0,
                        "output": output,
                        "output_sha256": sha256_text(output),
                        "latency_ms": 10.0,
                        "attempts": [],
                        "selected_replica_profile_id_sha256": sha256_text(
                            profile.profile_id
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda *_args: 1.0,
    )
    recovered = _recover_private_checkpoint_state(
        {
            "schema": SCREENING_CAMPAIGN_SCHEMA,
            "status": "partial",
            "units": [
                {
                    "task_id": existing_task["task_id"],
                    "status": "failed",
                    "mean_score": None,
                    "private_unit_content_sha256": sha256_text("existing-unit"),
                }
            ],
        },
        base_state={
            "schema": SCREENING_CAMPAIGN_SCHEMA,
            "mode": "live",
            "planned_task_count": 2,
            "network_calls_performed": False,
        },
        task_rows=[existing_task, recovered_task],
        raw_sources={source_hash: source},
        selected_cases={source_hash: [case]},
        source_receipts={source_hash: {"max_transport_failure_rate": 0.0}},
        private_root=tmp_path / "units",
    )

    assert len(recovered["units"]) == 2
    assert recovered["unit_set_digest_sha256"] == _screening_unit_set_digest(
        recovered["units"]
    )


def test_private_checkpoint_recovery_rehydrates_retryable_aggregate_drift(
    tmp_path,
    monkeypatch,
):
    from axio_fusion_api.baseline_screening import (
        _rebuild_safe_unit_from_private_artifact,
        _recover_private_checkpoint_state,
        _screening_resume_state_errors,
        _verify_screening_unit_private_artifact,
    )

    profile = normalize_profile(_registry_rows()[2])
    source = {"source_id": "rehydrate-drift-source", "adapter": "jsonl_multiple_choice"}
    source_hash = sha256_text(source["source_id"])
    cases = [
        ScreeningCase("rehydrate-drift-a", "Choose A or B.", "A", "fixture", {}),
        ScreeningCase("rehydrate-drift-b", "Choose A or B.", "A", "fixture", {}),
    ]
    task = {
        "task_id": sha256_text("rehydrate-drift-task"),
        "source_id_sha256": source_hash,
        "source_snapshot_sha256": sha256_text("snapshot"),
        "case_set_digest_sha256": sha256_text("cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    private_root = tmp_path / "units"
    unit_path = _screening_unit_path(private_root, task)
    unit_path.parent.mkdir(parents=True)
    outputs = {cases[0].case_id: "A", cases[1].case_id: "B"}
    unit_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
                "task_id": task["task_id"],
                "source_id": source["source_id"],
                "canonical_identity_sha256": task["canonical_identity_sha256"],
                "candidate_id_sha256": task["candidate_id_sha256"],
                "case_results": [
                    {
                        "case_id": case.case_id,
                        "status": "completed",
                        "score": 1.0 if outputs[case.case_id] == "A" else 0.0,
                        "output": outputs[case.case_id],
                        "output_sha256": sha256_text(outputs[case.case_id]),
                        "latency_ms": 10.0,
                        "attempts": [],
                        "selected_replica_profile_id_sha256": sha256_text(
                            profile.profile_id
                        ),
                    }
                    for case in cases
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda _source, _case, output: 1.0 if output == "A" else 0.0,
    )
    source_receipt = {"max_transport_failure_rate": 0.0}
    rebuilt = _rebuild_safe_unit_from_private_artifact(
        task=task,
        source=source,
        source_receipt=source_receipt,
        cases=cases,
        private_root=private_root,
    )
    assert rebuilt is not None
    stale = json.loads(json.dumps(rebuilt))
    stale.update(
        {
            "status": "failed",
            "reason_codes": ["screening_unit_scorer_error"],
            "confidence_interval_95_lower": 0.356,
            "confidence_interval_95_upper": 0.525,
        }
    )
    base_state = {
        "schema": SCREENING_CAMPAIGN_SCHEMA,
        "mode": "live",
        "planned_task_count": 1,
        "network_calls_performed": False,
    }

    recovered = _recover_private_checkpoint_state(
        {**base_state, "status": "partial", "units": [stale]},
        base_state=base_state,
        task_rows=[task],
        raw_sources={source_hash: source},
        selected_cases={source_hash: cases},
        source_receipts={source_hash: source_receipt},
        private_root=private_root,
    )

    recovered_unit = recovered["units"][0]
    assert recovered_unit["status"] == "completed"
    assert recovered_unit["confidence_interval_95_lower"] == rebuilt[
        "confidence_interval_95_lower"
    ]
    assert recovered_unit["confidence_interval_95_upper"] == rebuilt[
        "confidence_interval_95_upper"
    ]
    assert _screening_resume_state_errors(recovered, base_state=base_state) == []
    assert _verify_screening_unit_private_artifact(
        task=task,
        unit=recovered_unit,
        source=source,
        cases=cases,
        private_root=private_root,
    ) == []


def test_private_checkpoint_recovery_accepts_final_write_before_safe_state_flush(
    tmp_path,
    monkeypatch,
):
    """A retry may finish its private file before the safe state write."""

    from axio_fusion_api.baseline_screening import _recover_private_checkpoint_state

    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "retry-final-write-source",
        "adapter": "jsonl_multiple_choice",
    }
    source_hash = sha256_text(source["source_id"])
    cases = [
        ScreeningCase("retry-kept-answer", "Choose A.", "A", "fixture", {}),
        ScreeningCase("retry-was-missing", "Choose A again.", "A", "fixture", {}),
    ]
    task = {
        "task_id": sha256_text("retry-final-write-task"),
        "source_id_sha256": source_hash,
        "source_snapshot_sha256": sha256_text("snapshot"),
        "case_set_digest_sha256": sha256_text("cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    private_root = tmp_path / "units"
    unit_path = _screening_unit_path(private_root, task)
    unit_path.parent.mkdir(parents=True)
    output = "A"
    # This is the newer private file written by a retry. The first case was
    # already completed in the old safe row; the previously failed case now
    # has a valid answer and must be allowed to enter the new projection.
    unit_path.write_text(
        json.dumps(
            {
                "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
                "task_id": task["task_id"],
                "source_id": source["source_id"],
                "canonical_identity_sha256": task["canonical_identity_sha256"],
                "candidate_id_sha256": task["candidate_id_sha256"],
                "case_results": [
                    {
                        "case_id": case.case_id,
                        "status": "completed",
                        "score": 1.0,
                        "output": output,
                        "output_sha256": sha256_text(output),
                        "latency_ms": 10.0,
                        "attempts": [],
                        "selected_replica_profile_id_sha256": sha256_text(
                            profile.profile_id
                        ),
                    }
                    for case in cases
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda *_args: 1.0,
    )
    old_safe = {
        "task_id": task["task_id"],
        "status": "failed",
        "candidate_id_sha256": task["candidate_id_sha256"],
        "source_id_sha256": source_hash,
        "canonical_identity_sha256": task["canonical_identity_sha256"],
        "private_unit_content_sha256": sha256_text("stale-private-file"),
        "case_results": [
            {
                "case_id_sha256": sha256_text(cases[0].case_id),
                "status": "completed",
                "output_sha256": sha256_text(output),
                "score": 1.0,
            },
            {
                "case_id_sha256": sha256_text(cases[1].case_id),
                "status": "transport_failed",
                "output_sha256": sha256_text(""),
                "score": None,
            },
        ],
    }

    recovered = _recover_private_checkpoint_state(
        {
            "schema": SCREENING_CAMPAIGN_SCHEMA,
            "status": "partial",
            "units": [old_safe],
        },
        base_state={
            "schema": SCREENING_CAMPAIGN_SCHEMA,
            "mode": "live",
            "planned_task_count": 1,
            "network_calls_performed": False,
        },
        task_rows=[task],
        raw_sources={source_hash: source},
        selected_cases={source_hash: cases},
        source_receipts={source_hash: {"max_transport_failure_rate": 0.0}},
        private_root=private_root,
    )

    recovered_unit = recovered["units"][0]
    assert recovered_unit["status"] == "completed"
    assert recovered_unit["scored_case_count"] == 2
    assert recovered_unit["transport_failure_count"] == 0
    assert recovered_unit["private_unit_content_sha256"] == _file_sha256(unit_path)


def test_private_unit_recovery_preserves_partial_score_bootstrap_order(
    tmp_path,
    monkeypatch,
):
    """Resume must reproduce a partial-credit interval from the first pass."""

    from axio_fusion_api.baseline_screening import (
        _rebuild_safe_unit_from_private_artifact,
        _verify_screening_unit_private_artifact,
    )

    profile = normalize_profile(_registry_rows()[2])
    source = {
        "source_id": "partial-bootstrap-order-source",
        "adapter": "jsonl_multiple_choice",
        "prompt_protocol": {"system_prompt": ""},
        "decoding": {
            "temperature": 0.0,
            "max_output_tokens": 8,
            "max_exception_attempt_rounds": 1,
        },
    }
    source_hash = sha256_text(source["source_id"])
    ordered_ids = sorted(
        [
            "partial-bootstrap-a",
            "partial-bootstrap-b",
            "partial-bootstrap-c",
            "partial-bootstrap-d",
            "partial-bootstrap-e",
        ],
        key=sha256_text,
    )
    values = {
        case_id: value
        for case_id, value in zip(ordered_ids, ("0.02", "0.11", "0.37", "0.68", "0.94"))
    }
    cases = [
        ScreeningCase(
            case_id,
            values[case_id],
            "A",
            "fixture",
            {},
        )
        for case_id in reversed(ordered_ids)
    ]
    assert [case.case_id for case in cases] != ordered_ids
    task = {
        "task_id": sha256_text("partial-bootstrap-order-task"),
        "source_id_sha256": source_hash,
        "source_snapshot_sha256": sha256_text("partial-bootstrap-snapshot"),
        "case_set_digest_sha256": sha256_text("partial-bootstrap-cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("partial-bootstrap-candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }

    class PartialScoreClient:
        def complete(self, _profile, _request, *, prompt, system, timeout=None):
            del system, timeout
            return prompt

    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output",
        lambda _source, _case, output: float(output),
    )
    private_root = tmp_path / "units"
    first = _run_screening_unit(
        task=task,
        private_source_id=source["source_id"],
        source=source,
        source_receipt={
            "selected_case_count": len(cases),
            "max_transport_failure_rate": 0.0,
        },
        cases=cases,
        replicas=[profile],
        private_root=private_root,
        client=PartialScoreClient(),
        max_workers=1,
    )
    rebuilt = _rebuild_safe_unit_from_private_artifact(
        task=task,
        source=source,
        source_receipt={"max_transport_failure_rate": 0.0},
        cases=cases,
        private_root=private_root,
    )

    assert rebuilt is not None
    assert first["confidence_interval_95_lower"] == rebuilt[
        "confidence_interval_95_lower"
    ]
    assert first["confidence_interval_95_upper"] == rebuilt[
        "confidence_interval_95_upper"
    ]
    assert _verify_screening_unit_private_artifact(
        task=task,
        unit=first,
        source=source,
        cases=cases,
        private_root=private_root,
    ) == []


def test_private_checkpoint_recovery_keeps_completed_digest_mismatch_fail_closed(
    tmp_path,
    monkeypatch,
):
    from axio_fusion_api.baseline_screening import (
        _rebuild_safe_unit_from_private_artifact,
        _recover_private_checkpoint_state,
        _verify_screening_unit_private_artifact,
    )

    profile = normalize_profile(_registry_rows()[2])
    source = {"source_id": "completed-digest-source", "adapter": "jsonl_multiple_choice"}
    source_hash = sha256_text(source["source_id"])
    case = ScreeningCase("completed-digest-case", "Choose A or B.", "A", "fixture", {})
    task = {
        "task_id": sha256_text("completed-digest-task"),
        "source_id_sha256": source_hash,
        "source_snapshot_sha256": sha256_text("snapshot"),
        "case_set_digest_sha256": sha256_text("cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    private_root = tmp_path / "units"
    unit_path = _screening_unit_path(private_root, task)
    unit_path.parent.mkdir(parents=True)
    payload = {
        "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
        "task_id": task["task_id"],
        "source_id": source["source_id"],
        "canonical_identity_sha256": task["canonical_identity_sha256"],
        "candidate_id_sha256": task["candidate_id_sha256"],
        "case_results": [
            {
                "case_id": case.case_id,
                "status": "completed",
                "score": 1.0,
                "output": "A",
                "output_sha256": sha256_text("A"),
                "latency_ms": 10.0,
                "attempts": [],
                "selected_replica_profile_id_sha256": sha256_text(profile.profile_id),
            }
        ],
    }
    unit_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda *_args: 1.0,
    )
    unit = _rebuild_safe_unit_from_private_artifact(
        task=task,
        source=source,
        source_receipt={"max_transport_failure_rate": 0.0},
        cases=[case],
        private_root=private_root,
    )
    assert unit is not None
    payload["case_results"][0]["output"] = "B"
    payload["case_results"][0]["output_sha256"] = sha256_text("B")
    unit_path.write_text(json.dumps(payload), encoding="utf-8")
    base_state = {
        "schema": SCREENING_CAMPAIGN_SCHEMA,
        "mode": "live",
        "planned_task_count": 1,
        "network_calls_performed": False,
    }

    recovered = _recover_private_checkpoint_state(
        {**base_state, "status": "completed", "units": [unit]},
        base_state=base_state,
        task_rows=[task],
        raw_sources={source_hash: source},
        selected_cases={source_hash: [case]},
        source_receipts={source_hash: {"max_transport_failure_rate": 0.0}},
        private_root=private_root,
    )

    assert recovered["units"][0]["private_unit_content_sha256"] == unit[
        "private_unit_content_sha256"
    ]
    assert "screening_ranking_private_unit_digest_mismatch" in (
        _verify_screening_unit_private_artifact(
            task=task,
            unit=recovered["units"][0],
            source=source,
            cases=[case],
            private_root=private_root,
        )
    )


def test_private_checkpoint_recovery_rejects_changed_retryable_answer(
    tmp_path,
    monkeypatch,
):
    from axio_fusion_api.baseline_screening import (
        _rebuild_safe_unit_from_private_artifact,
        _recover_private_checkpoint_state,
    )

    profile = normalize_profile(_registry_rows()[2])
    source = {"source_id": "retryable-answer-source", "adapter": "jsonl_multiple_choice"}
    source_hash = sha256_text(source["source_id"])
    case = ScreeningCase("retryable-answer-case", "Choose A or B.", "A", "fixture", {})
    task = {
        "task_id": sha256_text("retryable-answer-task"),
        "source_id_sha256": source_hash,
        "source_snapshot_sha256": sha256_text("snapshot"),
        "case_set_digest_sha256": sha256_text("cases"),
        "canonical_identity_sha256": profile.canonical_identity_sha256,
        "candidate_id_sha256": sha256_text("candidate"),
        "representative_profile_id_sha256": sha256_text(profile.profile_id),
        "replica_profile_id_sha256s": [sha256_text(profile.profile_id)],
    }
    private_root = tmp_path / "units"
    unit_path = _screening_unit_path(private_root, task)
    unit_path.parent.mkdir(parents=True)
    payload = {
        "schema": "axio_fusion_api.non_target_screening_unit_private.v1",
        "task_id": task["task_id"],
        "source_id": source["source_id"],
        "canonical_identity_sha256": task["canonical_identity_sha256"],
        "candidate_id_sha256": task["candidate_id_sha256"],
        "case_results": [
            {
                "case_id": case.case_id,
                "status": "completed",
                "score": 1.0,
                "output": "A",
                "output_sha256": sha256_text("A"),
                "latency_ms": 10.0,
                "attempts": [],
                "selected_replica_profile_id_sha256": sha256_text(profile.profile_id),
            }
        ],
    }
    unit_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "axio_fusion_api.baseline_screening._score_screening_output_silently",
        lambda _source, _case, output: 1.0 if output == "A" else 0.0,
    )
    unit = _rebuild_safe_unit_from_private_artifact(
        task=task,
        source=source,
        source_receipt={"max_transport_failure_rate": 0.0},
        cases=[case],
        private_root=private_root,
    )
    assert unit is not None
    stale = json.loads(json.dumps(unit))
    stale.update({"status": "failed", "reason_codes": ["screening_unit_scorer_error"]})
    payload["case_results"][0]["output"] = "B"
    payload["case_results"][0]["output_sha256"] = sha256_text("B")
    unit_path.write_text(json.dumps(payload), encoding="utf-8")
    stale["private_unit_content_sha256"] = _file_sha256(unit_path)
    base_state = {
        "schema": SCREENING_CAMPAIGN_SCHEMA,
        "mode": "live",
        "planned_task_count": 1,
        "network_calls_performed": False,
    }

    recovered = _recover_private_checkpoint_state(
        {**base_state, "status": "partial", "units": [stale]},
        base_state=base_state,
        task_rows=[task],
        raw_sources={source_hash: source},
        selected_cases={source_hash: [case]},
        source_receipts={source_hash: {"max_transport_failure_rate": 0.0}},
        private_root=private_root,
    )

    assert recovered["units"][0]["case_results"][0]["output_sha256"] == sha256_text("A")


def test_live_preflight_failure_does_not_overwrite_existing_checkpoint(
    tmp_path,
    monkeypatch,
):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=2,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private-units"
    monkeypatch.setenv("FIXTURE_BASE_URL", "https://fixture.invalid/v1")
    before = {
        "schema": SCREENING_CAMPAIGN_SCHEMA,
        "status": "partial",
        "units": [{"task_id": "prior-unit", "status": "completed"}],
    }
    state_path.write_text(json.dumps(before), encoding="utf-8")
    original = state_path.read_bytes()

    blocked = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
    )

    assert blocked["status"] == "blocked"
    assert state_path.read_bytes() == original


def test_campaign_resumes_new_tasks_and_separates_private_outputs(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=2,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    client = _RankedFixtureClient()

    first = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=2,
        max_tasks=1,
        client=client,
    )
    first_calls = len(client.calls)
    second = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=2,
        max_tasks=1,
        client=client,
    )

    assert first["status"] == "partial"
    assert first["completed_unit_count"] == 1
    assert second["status"] == "partial"
    assert second["completed_unit_count"] == 2
    assert len(client.calls) == first_calls * 2
    assert {row["task_id"] for row in first["units"]}.issubset(
        {row["task_id"] for row in second["units"]}
    )

    final = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=2,
        client=client,
    )
    assert final["schema"] == SCREENING_CAMPAIGN_SCHEMA
    assert final["status"] == "completed"
    assert final["ready_for_ranking"] is True
    assert final["completed_unit_count"] == plan["task_count"]

    safe_serialized = state_path.read_text(encoding="utf-8")
    assert PRIVATE_SOURCE_MARKER not in safe_serialized
    assert PRIVATE_PROVIDER_MARKER not in safe_serialized
    assert PRIVATE_MODEL_MARKER not in safe_serialized
    assert PRIVATE_OUTPUT_MARKER not in safe_serialized
    assert str(private_root) not in safe_serialized
    assert '"source_id":' not in safe_serialized
    assert '"raw_provider_outputs_persisted": true' not in safe_serialized
    private_serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in private_root.rglob("*.private.json")
    )
    assert PRIVATE_SOURCE_MARKER in private_serialized
    assert PRIVATE_OUTPUT_MARKER in private_serialized
    assert '"raw_provider_outputs_persisted": true' in private_serialized


def test_live_campaign_blocks_worker_mismatch_before_network_calls(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    client = _RankedFixtureClient()

    blocked = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        live=True,
        max_workers=2,
        client=client,
    )

    assert blocked["status"] == "blocked"
    assert "screening_runtime_max_workers_mismatch" in blocked["reason_codes"]
    assert blocked["network_calls_performed"] is False
    assert client.calls == []


def test_live_campaign_rejects_plan_without_frozen_worker_before_calls(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
    )
    plan.pop("max_workers")
    plan["plan_digest_sha256"] = sha256_text(
        stable_json(
            {
                key: value
                for key, value in plan.items()
                if key not in {"plan_digest_sha256", "ready", "blockers"}
            }
        )
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    client = _RankedFixtureClient()

    blocked = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        live=True,
        max_workers=1,
        client=client,
    )

    assert blocked["status"] == "blocked"
    assert "screening_plan_max_workers_invalid" in blocked["reason_codes"]
    assert blocked["network_calls_performed"] is False
    assert client.calls == []


def test_live_campaign_blocks_resume_worker_binding_mismatch_before_calls(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=2,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    first = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=2,
        max_tasks=1,
        client=_RankedFixtureClient(),
    )
    assert first["status"] == "partial"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["max_workers"] = 1
    _rehash_campaign_state(state)
    _write_json(state_path, state)
    resume_client = _RankedFixtureClient()

    blocked = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=2,
        client=resume_client,
    )

    assert blocked["status"] == "blocked"
    assert "screening_resume_max_workers_mismatch" in blocked["reason_codes"]
    assert blocked["network_calls_performed"] is False
    assert resume_client.calls == []


def test_live_campaign_rejects_preflight_checkpoint_before_network_calls(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    preflight = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=False,
    )
    assert preflight["status"] == "preflight_ready"
    client = _RankedFixtureClient()

    live = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        client=client,
    )

    assert live["status"] == "blocked"
    assert "screening_resume_mode_mismatch" in live["reason_codes"]
    assert client.calls == []
    assert live["network_calls_performed"] is False


def test_live_campaign_rejects_private_root_checkpoint_drift(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    first_client = _RankedFixtureClient()
    first = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units_a",
        state_path=state_path,
        live=True,
        max_tasks=1,
        client=first_client,
    )
    assert first["status"] == "partial"
    resume_client = _RankedFixtureClient()

    resumed = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units_b",
        state_path=state_path,
        live=True,
        client=resume_client,
    )

    assert resumed["status"] == "blocked"
    assert (
        "screening_resume_private_root_sha256_mismatch"
        in resumed["reason_codes"]
    )
    assert resume_client.calls == []
    assert resumed["network_calls_performed"] is False


def test_live_campaign_rejects_transport_mode_checkpoint_drift(
    tmp_path,
    monkeypatch,
):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for index, row in enumerate(registry["models"]):
        row["base_url_env"] = f"FIXTURE_RESUME_BASE_URL_{index}"
        row["api_key_env"] = f"FIXTURE_RESUME_API_KEY_{index}"
        monkeypatch.setenv(
            row["base_url_env"],
            f"https://{row['provider']}.invalid/v1",
        )
        monkeypatch.setenv(row["api_key_env"], f"fixture-key-{index}")
    _write_json(registry_path, registry)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    first = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_tasks=0,
        client=_RankedFixtureClient(),
    )
    assert first["status"] == "partial"

    resumed = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_tasks=0,
    )

    assert resumed["status"] == "blocked"
    assert (
        "screening_resume_live_credential_readiness_digest_sha256_mismatch"
        in resumed["reason_codes"]
    )
    assert resumed["network_calls_performed"] is False


def test_live_campaign_rejects_forged_planned_task_count(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    client = _RankedFixtureClient()
    first = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_tasks=1,
        client=client,
    )
    assert first["status"] == "partial"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["planned_task_count"] = int(state["planned_task_count"]) - 1
    _rehash_campaign_state(state)
    _write_json(state_path, state)
    call_count = len(client.calls)

    resumed = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        client=client,
    )

    assert resumed["status"] == "blocked"
    assert (
        "screening_resume_planned_task_count_mismatch"
        in resumed["reason_codes"]
    )
    assert len(client.calls) == call_count
    assert resumed["network_calls_performed"] is False


def test_campaign_blocks_input_hash_drift_before_network_calls(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    source_path = tmp_path / "source_alpha.private.jsonl"
    source_path.write_text(
        source_path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "id": "drifted-case",
                "question": "Drifted after pre-registration?",
                "options": ["yes", "no"],
                "answer": "A",
                "category": "fixture-drift",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    client = _RankedFixtureClient()

    result = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        live=True,
        client=client,
    )

    assert result["status"] == "blocked"
    assert "screening_plan_current_inputs_mismatch" in result["reason_codes"]
    assert client.calls == []
    assert result["network_calls_performed"] is False


def test_live_campaign_blocks_missing_credentials_before_first_http_call(
    tmp_path,
    monkeypatch,
):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    for name in (
        "AXIO_OPENAI_COMPAT_BASE_URL",
        "AXIO_OPENAI_COMPAT_API_KEY",
        "AXIO_NVIDIA_BASE_URL",
        "AXIO_NVIDIA_API_KEYS",
        "AXIO_NVIDIA_API_KEY",
        "AXIO_CPA_PLUS_BASE_URL",
        "AXIO_CPA_PLUS_API_KEY",
        "AXIO_CPA_PLUS_API_KEYS",
    ):
        monkeypatch.delenv(name, raising=False)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)

    result = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        live=True,
    )

    assert result["status"] == "blocked"
    assert "screening_live_credentials_incomplete" in result["reason_codes"]
    assert "screening_live_base_url_missing" in result["reason_codes"]
    assert "screening_live_api_key_missing" in result["reason_codes"]
    assert result["live_credential_readiness"]["required_profile_count"] == 4
    assert result["live_credential_readiness"]["credential_ready_profile_count"] == 0
    assert result["live_credential_readiness"]["missing_base_url_count"] == 4
    assert result["live_credential_readiness"]["missing_api_key_count"] == 4
    assert result["network_calls_performed"] is False
    serialized = json.dumps(result, ensure_ascii=False)
    assert "AXIO_OPENAI_COMPAT" not in serialized
    assert PRIVATE_PROVIDER_MARKER not in serialized
    assert PRIVATE_MODEL_MARKER not in serialized


def test_live_campaign_binds_http_endpoint_to_catalog_attestation(
    tmp_path,
    monkeypatch,
):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for index, row in enumerate(registry["models"]):
        row["base_url_env"] = f"FIXTURE_SCREENING_BASE_URL_{index}"
        row["api_key_env"] = f"FIXTURE_SCREENING_API_KEY_{index}"
        monkeypatch.setenv(
            row["base_url_env"],
            f"https://{row['provider']}.invalid/v1",
        )
        monkeypatch.setenv(row["api_key_env"], f"fixture-key-{index}")
    _write_json(registry_path, registry)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)

    matching = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "matching_private_units",
        live=True,
        max_tasks=0,
    )
    assert matching["status"] == "partial"
    assert matching["live_credential_readiness"]["ready"] is True
    assert matching["live_credential_readiness"]["credential_ready_profile_count"] == 4
    assert matching["network_calls_performed"] is False

    monkeypatch.setenv(
        registry["models"][0]["base_url_env"],
        "https://different-endpoint.invalid/v1",
    )
    drifted = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "drifted_private_units",
        live=True,
        max_tasks=0,
    )

    assert drifted["status"] == "blocked"
    assert "screening_live_endpoint_attestation_mismatch" in drifted["reason_codes"]
    assert drifted["live_credential_readiness"]["endpoint_binding_mismatch_count"] == 1
    assert drifted["network_calls_performed"] is False
    serialized = json.dumps(drifted, ensure_ascii=False)
    assert "different-endpoint.invalid" not in serialized
    assert "FIXTURE_SCREENING_BASE_URL" not in serialized
    assert "fixture-key" not in serialized


def test_completed_campaign_converts_to_existing_strict_ranking_contract(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    campaign = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        state_path=state_path,
        live=True,
        max_workers=3,
        client=_RankedFixtureClient(),
    )
    assert campaign["ready_for_ranking"] is True, campaign["reason_codes"]

    ranking = build_external_ranking_manifest_from_screening(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
    )
    assert ranking["screening_conversion_ready"] is True, ranking.get("blockers")
    assert ranking["ranking_assignment_present"] is True
    assert [row["rank"] for row in ranking["rankings"]] == [1, 2, 3]
    assert len(ranking["candidate_inventory"]) == 3
    assert all(len(row["screening_evidence"]) == 2 for row in ranking["candidate_inventory"])

    ranking_path = _write_json(tmp_path / "external_ranking.private.json", ranking)
    profiles = load_registry(registry_path)
    receipt = _external_provider_ranking_selection_receipt(
        ranking_path,
        profiles=profiles,
        registry_receipt=_provider_registry_receipt(
            profiles,
            registry_path=registry_path,
        ),
    )
    assert receipt["ready"] is True, receipt["blockers"]
    assert receipt["candidate_inventory_count"] == 3
    assert receipt["replica_profile_count"] == 4
    assert receipt["identity_binding_count"] == 4
    assert receipt["common_independent_source_family_count"] == 2


def test_ranking_conversion_fails_closed_for_empty_partial_evidence(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=1,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.private.json"
    campaign = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
        state_path=state_path,
        live=False,
    )
    assert campaign["status"] == "preflight_ready"
    empty_manifest_path = _write_json(
        tmp_path / "empty_source_manifest.private.json",
        {
            "schema": "axio_fusion_api.non_target_screening_source_manifest.v1",
            "pre_registration": {
                "declared_before_target_campaign": True,
                "registered_on": "2026-07-20",
                "selection_seed": "fixture-seed",
                "target_benchmark_results_used": False,
                "target_suite_results_used": False,
            },
            "sources": [],
        },
    )

    ranking = build_external_ranking_manifest_from_screening(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        source_manifest_path=empty_manifest_path,
        private_probe_files=[probe_path],
        private_root=tmp_path / "private_units",
    )

    assert ranking["screening_conversion_ready"] is False
    assert ranking["template_only"] is True
    assert "screening_ranking_campaign_not_complete" in ranking["blockers"]
    assert "screening_ranking_candidate_evidence_empty" in ranking["blockers"]


def test_ranking_rescores_private_output_after_attacker_rehashes_artifacts(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    campaign = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=3,
        client=_RankedFixtureClient(),
    )
    assert campaign["ready_for_ranking"] is True

    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = state["units"][0]
    unit_path = next(
        private_root.rglob(f"{unit['task_id']}.private.json")
    )
    private_payload = json.loads(unit_path.read_text(encoding="utf-8"))
    row = private_payload["case_results"][0]
    forged_answer = "B" if float(row["score"]) == 1.0 else "A"
    row["output"] = f"{PRIVATE_OUTPUT_MARKER}\n{forged_answer}"
    row["output_sha256"] = sha256_text(row["output"])
    # Keep the original claimed score and also forge every outer content hash.
    _write_json(unit_path, private_payload)
    unit["private_unit_content_sha256"] = _file_sha256(unit_path)
    safe_row = next(
        item
        for item in unit["case_results"]
        if item["case_id_sha256"] == sha256_text(row["case_id"])
    )
    safe_row["output_sha256"] = row["output_sha256"]
    _rehash_campaign_state(state)
    _write_json(state_path, state)

    ranking = build_external_ranking_manifest_from_screening(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
    )

    assert ranking["screening_conversion_ready"] is False
    assert "screening_ranking_private_score_mismatch" in ranking["blockers"]


def test_ranking_rejects_forged_safe_score_even_with_campaign_rehash(tmp_path):
    registry_path, probe_path, manifest_path = _screening_fixture(tmp_path)
    plan = build_non_target_screening_plan(
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        min_cases_per_source=4,
        max_workers=3,
    )
    plan_path = _write_json(tmp_path / "screening_plan.safe.json", plan)
    state_path = tmp_path / "campaign_state.safe.json"
    private_root = tmp_path / "private_units"
    campaign = run_non_target_screening_campaign(
        plan_path=plan_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
        state_path=state_path,
        live=True,
        max_workers=3,
        client=_RankedFixtureClient(),
    )
    assert campaign["ready_for_ranking"] is True

    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = state["units"][0]
    unit["case_results"][0]["score"] = 1.0 - float(
        unit["case_results"][0]["score"]
    )
    _rehash_campaign_state(state)
    _write_json(state_path, state)

    ranking = build_external_ranking_manifest_from_screening(
        plan_path=plan_path,
        campaign_state_path=state_path,
        registry_path=registry_path,
        source_manifest_path=manifest_path,
        private_probe_files=[probe_path],
        private_root=private_root,
    )

    assert ranking["screening_conversion_ready"] is False
    assert "screening_ranking_safe_case_score_mismatch" in ranking["blockers"]


def test_screening_cli_commands_are_registered():
    parser = build_parser()
    base = [
        "--registry",
        "registry.private.json",
    ]
    plan_args = parser.parse_args(
        [
            *base,
            "baseline-screening-plan",
            "--source-manifest",
            "sources.private.json",
            "--private-probe-file",
            "probe.private.json",
            "--output",
            "plan.safe.json",
        ]
    )
    run_args = parser.parse_args(
        [
            *base,
            "baseline-screening-run",
            "--plan",
            "plan.safe.json",
            "--source-manifest",
            "sources.private.json",
            "--private-probe-file",
            "probe.private.json",
            "--private-root",
            "private-units",
            "--state-output",
            "state.safe.json",
        ]
    )
    ranking_args = parser.parse_args(
        [
            *base,
            "baseline-screening-to-ranking",
            "--plan",
            "plan.safe.json",
            "--campaign-state",
            "state.safe.json",
            "--source-manifest",
            "sources.private.json",
            "--private-root",
            "private-units",
            "--private-probe-file",
            "probe.private.json",
            "--output",
            "ranking.private.json",
        ]
    )

    assert plan_args.command == "baseline-screening-plan"
    assert plan_args.max_workers == 1
    assert run_args.command == "baseline-screening-run"
    assert run_args.live is False
    assert run_args.max_workers is None
    assert ranking_args.command == "baseline-screening-to-ranking"
