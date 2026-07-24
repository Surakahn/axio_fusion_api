# 2026-07-14 04:54 Axio Fusion API Readiness 接入 Research Knowledge Harness

## 本轮目标

上一轮已经完成 Axio Fusion API smoke、Harness Eval 和 Studio project state 投影。本轮把这个 readiness 继续接入第一、二部分主链路：`research-knowledge-harness` 自动生成并读取 Axio Fusion API dry-run smoke，把模型服务健康状态写入 harness manifest、agent contract，并作为 metadata-only derived context 传给 paper-reading Campaign。

## 已完成内容

1. 新增 Axio Fusion API readiness resolver 与摘要。
   - 新增 schema：`asci_fs.research_knowledge_harness.axio_fusion_api_readiness.v1`。
   - 新增 `resolve_axio_fusion_api_smoke_report()`。
   - 新增 `summarize_axio_fusion_api_readiness()`。
   - 摘要只保留：
     - smoke status、case/failed/selected model/provider call 计数。
     - Axio-nano/Axio-terra/Axio-pro 覆盖。
     - chat/completions、responses、anthropic 覆盖。
     - `/models` 是否只暴露 Axio 外部模型。
     - verifier/aggregator 计数和 strategy_counts。
     - raw prompt/raw source/secrets 安全布尔值。
   - 明确不训练新模型权重，只更新/引用路由策略与 readiness metadata。

2. `run_research_knowledge_harness_outputs()` 自动生成 dry-run smoke。
   - 调用 `build_fusion_api_smoke_outputs(output)`。
   - 将输出加入 `stage_artifacts`：
     - `agent_platform/fusion_api_smoke_report.json`
     - `agent_platform/fusion_api_smoke_report.md`
   - harness manifest summary 新增：
     - `axio_fusion_api_smoke_status`
     - `axio_fusion_api_ready_for_campaign_model_orchestration`
     - `axio_fusion_api_case_count`
     - `axio_fusion_api_failed_count`
     - `axio_fusion_api_selected_model_count`
     - `axio_fusion_api_provider_call_count`
     - `axio_fusion_api_readiness`

3. Research Knowledge Agent Contract 接入 readiness。
   - `build_research_knowledge_agent_contract()` 新增 `axio_fusion_api_readiness`。
   - contract 中新增 `axio_fusion_api_readiness` 节点。
   - acceptance checks 新增 `axio_fusion_api_readiness_recorded`。

4. Paper-reading Campaign 上下文接入 readiness。
   - 当 `execute_paper_reading=True` 且非 dry-run 时，把 readiness 作为 `machine_readable_context` 注入 Campaign context。
   - 该 context 是 `system_promoted` metadata-only derived context。
   - 不包含 raw paper text、raw prompt、source text、secrets 或 API key。
   - 后续 planner/reader/synthesizer 可以在上下文规划中消费这一 readiness，用于判断 Axio 模型融合层是否可用、是否需要回退或降级。

## 验证结果

已运行：

```bash
nice -n 10 .venv/bin/python -m py_compile axio/research_knowledge_harness.py tests/test_research_knowledge_harness.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_research_knowledge_harness.py -k 'axio_fusion_api_smoke_resolver or research_knowledge_harness_runs_prd_module_1_and_2_locally'
nice -n 10 .venv/bin/python -m pytest -q tests/test_research_knowledge_harness.py -k 'agent_contract_embeds_core_agent_projection or router_learning_report_resolver or idea_generation_admission_contract_requires_module_1_2_readiness or axio_fusion_api_smoke_resolver'
nice -n 10 .venv/bin/python -m pytest -q tests/test_research_knowledge_harness.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_fusion_api_server.py tests/test_studio_state.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_paper_reading_campaign.py -k 'router_learning_advisory or prompt_scaffold or live_model'
git diff --check -- axio/research_knowledge_harness.py tests/test_research_knowledge_harness.py
```

结果：

- 编译检查通过。
- targeted helper/full-chain：`2 passed, 25 deselected`。
- agent contract/router/admission/helper：`4 passed, 23 deselected`。
- 完整 `tests/test_research_knowledge_harness.py`：`27 passed`。
- Fusion API + Studio state：`11 passed`。
- Paper-reading Campaign 相邻链路：`2 passed, 8 deselected`。
- `git diff --check` 通过。

## Rust 重构判断

本轮仍是 readiness artifact 汇总、manifest/contract 投影和 metadata-only context 注入，不是高吞吐 API 网关、千篇级论文 metadata 去重、图路由候选重排或向量相似度热路径。因此不做 Rust 重构。

## 当前项目位置

仍处于 PRD 第一、二部分基础设施阶段。本轮完成的是“Axio Fusion API readiness -> Research Knowledge Harness -> Paper-reading Campaign context”的链路，使第一部分论文检索/阅读和第二部分 Agent Harness/模型融合开始真正互相促进。

## 下一步建议

下一个小范围收口点：让 paper-reading Campaign 的 `model_binding_receipt` 或最终 campaign `model_orchestration` 直接投影 `axio_fusion_api_readiness` 摘要，使每次 N+2 论文阅读产物都能证明它运行时看到的 Axio Fusion API 健康状态，而不只是通过上游 harness 间接推断。
