# 2026-07-14 05:48 Module 1/2 模型融合 readiness 的 Project State 与质量门收口

## 本轮完成

- 在 `studio_state.py` 中新增 `module_1_2_model_fusion_readiness` 顶层摘要。
- 将 `research_knowledge_harness/module_readiness_report.json` 中的 Axio readiness、router learning、Stage Runtime model-fusion、Quality Gate health 投影到 Studio Project State。
- 在 `summary` 中新增扁平字段：
  - `module_1_2_model_fusion_ready`
  - `module_1_2_model_fusion_status`
  - `module_1_2_model_fusion_blocker_count`
  - `module_1_2_model_fusion_blocking_ids`
  - `module_1_2_model_fusion_axio_status`
  - `module_1_2_model_fusion_router_learning_status`
  - `module_1_2_model_fusion_advisory_count`
  - `module_1_2_model_fusion_quality_gate_error_count`
- 在 Quality Gate 中新增 Project State 漂移检查，确保 Studio 的模型融合 readiness 与 Module 1/2 `module_readiness_report` 保持一致。
- 保持 metadata-only 边界：不存 raw prompt、raw source text、raw paper text、secrets，不训练新模型权重。

## 测试与验证

- 已通过 `nice -n 10 .venv/bin/python -m py_compile axio/studio_shell/studio_state.py axio/governance/quality_gate.py tests/test_studio_state.py tests/test_quality_gate.py`。
- 已通过 `nice -n 10 .venv/bin/python -m pytest -q tests/test_studio_state.py -k 'aggregates_agent_rag_web_and_execution_contracts'`。
- 已通过 `nice -n 10 .venv/bin/python -m pytest -q tests/test_quality_gate.py -k 'project_state_module_1_2_model_fusion_projection_drifts or project_state_axio_readiness_projection_drifts'`，结果为 `2 passed, 125 deselected`。
- 已通过 `nice -n 10 .venv/bin/python -m pytest -q tests/test_studio_state.py`，结果为 `2 passed`。
- 已通过 `git diff --check`。

## 下一步小范围收口

- 下一步建议只做一个小点：把 `module_1_2_model_fusion_readiness` 暴露到 Studio 前端已有状态面板或 API 响应中，保持不触碰第三部分主线。
- 如果前端已有未提交改动继续存在，应先核对其来源，避免覆盖用户工作。
