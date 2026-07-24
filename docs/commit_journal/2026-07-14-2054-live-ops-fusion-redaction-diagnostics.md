# 2026-07-14 20:54 - Live Ops Fusion Redaction Diagnostics

## Context

Module 1/2 already records prompt-free Fusion redaction receipts in Stage Runtime
Index, project_state, module readiness, and Quality Gate.  The remaining gap was
operator visibility: Agent Harness / Live Ops could see Axio router-learning
campaign evidence, but not the response/review/feedback redaction chain that
proves Fusion outputs were scrubbed before persistence.

## Changes

- Added a shared Live Ops redaction field contract in
  `axio/studio_shell/studio_live_ops.py`.
- Extended `axio_router_learning_diagnostics` with:
  - total Fusion redaction receipts;
  - echo/secret/raw prompt/raw source/reference redaction counts;
  - response, review, and feedback-notes redaction receipt buckets;
  - unsafe persistence count;
  - metadata-only and cross-user-scope guard flags.
- Added `axio_router_learning_fusion_redaction_*` summary fields to
  `live_ops_console.summary`.
- Extended Live Ops markdown so operators can see redaction receipts and unsafe
  persistence without reading raw prompts, source text, papers, provider
  responses, or secrets.
- Extended Quality Gate checks so Live Ops Axio diagnostics must stay aligned
  with `project_state` redaction projections, remain metadata-only, forbid
  private cross-user scope reuse, and never claim raw prompt/source/secret
  persistence.
- Added an operator diagnostics preflight contract to the Agent Harness path:
  handoff packets, harness contracts, backend invocation contracts, and the
  multi-agent runtime summary now point to `studio/live_ops_console.json` and
  enumerate the Axio router-learning / redaction fields that OpenClaw, Hermes,
  and Claw-code must inspect before routing, memory compression, repair, or
  code generation.
- Extended Quality Gate and backend invocation validation to fail stale or
  unsafe operator diagnostics preflight contracts.

## Verification

- `python3 -m py_compile axio/studio_shell/studio_live_ops.py axio/governance/quality_gate.py`
- `nice -n 10 python3 -m pytest -q tests/test_studio_live_ops.py::test_live_ops_console_surfaces_axio_router_learning_campaign_evidence`
- `nice -n 10 python3 -m pytest -q tests/test_quality_gate.py::test_quality_gate_fails_when_live_ops_axio_fusion_redaction_projection_drifts`
- `nice -n 10 python3 -m pytest -q tests/test_studio_live_ops.py::test_live_ops_console_surfaces_axio_router_learning_campaign_evidence tests/test_quality_gate.py::test_quality_gate_fails_when_studio_workbench_or_live_ops_lack_operator_runtime_diagnostics tests/test_quality_gate.py::test_quality_gate_fails_when_live_ops_session_board_attention_preview_is_stale tests/test_quality_gate.py::test_quality_gate_fails_when_live_ops_axio_fusion_redaction_projection_drifts`
- `nice -n 10 python3 -m pytest -q tests/test_stage_runtime_index.py tests/test_studio_state.py tests/test_research_knowledge_harness.py::test_module_readiness_projects_axio_fusion_health_without_blocking_projection_gap tests/test_quality_gate.py::test_quality_gate_fails_when_project_state_axio_readiness_projection_drifts tests/test_quality_gate.py::test_quality_gate_fails_when_project_state_module_1_2_model_fusion_projection_drifts`
- `python3 -m py_compile axio/fabric/agent_harness.py axio/fabric/agent_backend_invocation.py axio/fabric/multi_agent_runtime.py axio/governance/quality_gate.py`
- `nice -n 10 python3 -m pytest -q tests/test_agent_harness.py::test_backend_adapter_and_orchestration_policy_capture_role_split tests/test_agent_backend_invocation.py::test_build_agent_backend_invocation_outputs_dry_run_contracts`
- `nice -n 10 python3 -m pytest -q tests/test_quality_gate.py::test_quality_gate_fails_when_operator_runtime_diagnostics_preflight_is_stale tests/test_agent_backend_invocation.py::test_build_agent_backend_invocation_outputs_dry_run_contracts tests/test_agent_harness.py::test_backend_adapter_and_orchestration_policy_capture_role_split`

## Next

Wire the preflight result into concrete paper search, deep research, RAG, and
repair-loop admission / reroute decisions so blocking attention moves from
operator visibility into task routing behavior.
