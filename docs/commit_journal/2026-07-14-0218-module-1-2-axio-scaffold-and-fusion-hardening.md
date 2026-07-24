# 2026-07-14 02:18 Module 1/2 Axio Scaffold 接入与 Fusion P0 加固

## 本轮目标

在完成 Axio 动态 Fusion 三档合成之后，切回第一、二部分基础设施，把 Fusion 的 prompt scaffold 和 route plan 接入 paper-reading campaign 的 N+2 工作流。同时吸收子代理架构审计反馈，修复会阻碍第一、二部分可靠使用 Fusion 的 P0/P1 问题。

## 执行前计划

新增计划文档：

- `docs/architecture/module_1_2_axio_prompt_scaffold_integration_plan.md`

计划依据：

- OpenRouter provider/model routing：内部路由要可审计，外部模型名保持 Axio。
- Sakana Fugu / AI Scientist：单模型接口背后动态组合 scaffold、worker、aggregator。
- Anthropic effective agents：固定 workflow + 并行/编排/验证器适合复杂研究任务。
- OpenAI Agents SDK：handoff、guardrail、tracing 应显式记录。
- LangGraph workflow/agent：固定流程和动态决策分层。

## 完成内容

1. Module 1/2 prompt scaffold 接入：
   - `build_campaign_planner_prompt_contract` 增加 `axio_prompt_scaffold`。
   - `reader_prompt_contract` 增加 `axio_prompt_scaffold`。
   - `build_campaign_synthesis_prompt_contract` 增加 `axio_prompt_scaffold`。
   - scaffold 只保存固定合同、策略 id、任务类型和安全标记，不保存论文原文。

2. Reader task context 接入：
   - `paper_reading_executor` 将 reader scaffold 注入每个 `campaign_focus`。
   - reader prompt 渲染时加入 immutable contract、research honesty、structured output、branch instruction、verification contract。

3. Live Campaign Runner 接入：
   - planner/reader/synthesizer 的 live prompt payload 记录安全 scaffold metadata。
   - system prompt 拼接 Axio scaffold sections，确保 live model 真正消费 Fusion prompt scaffold。

4. Fusion 执行加固：
   - live 模式空 registry / 无 eligible model 时不调用默认环境模型。
   - API server 将 no eligible model 映射为 `503 no_eligible_model`。
   - serial strategy 真正执行 fallback chain。
   - Axio-pro 聚合后仍执行 verifier，而不是 aggregator 和 verifier 二选一。

5. CLI 修复：
   - `fusion-api --api-format responses` 现在生成 Responses payload。
   - `fusion-api --api-format anthropic` 现在生成 Anthropic Messages payload。

6. 架构注册：
   - `axio/model_fusion.py` 登记为 Agent Fabric compatibility module。
   - `axio/fusion_api_server.py` 登记为 Agent Fabric allowed root module。
   - `tests/test_architecture.py` 已恢复通过。

7. Rust 性能边界：
   - 本轮没有盲目引入 Rust。
   - 当前改动的主要风险是路由正确性、prompt 合同、API 错误映射和 Module 1/2 衔接，不是已量化 CPU 热点。
   - 后续只有图谱路由、相似度、去重、canonical hash、大规模 JSON/SQLite 合并等底层纯函数在 5 用户以上 dry-run 或千篇级任务中被量化为瓶颈，才做 Rust 可选加速器。
   - Rust 模块必须保持 Python fallback，不破坏现有安装、测试和部署；Agent 策略、prompt、业务编排仍留在 Python。

## 验证

已运行：

```bash
nice -n 10 .venv/bin/python -m py_compile axio/fabric/model_fusion.py axio/fusion_api_server.py axio/research/paper_reading_campaign.py axio/research/paper_reading_executor.py axio/research/paper_reading_llm.py axio/fabric/research_model_orchestration.py axio/architecture.py axio/cli.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_model_fusion.py tests/test_fusion_api_server.py tests/test_paper_reading_campaign.py tests/test_architecture.py
```

结果：

- py_compile：通过
- 定向 pytest：`28 passed`

## 子代理审计吸收情况

已立即处理：

- 架构注册表缺项。
- 空 registry live 隐式调用默认模型。
- fallback chain 未进入执行。
- pro 聚合后不做最终 verifier。
- CLI responses/anthropic payload 生成不准确。

尚未在本小步处理，后续排入 Fusion benchmark / API hardening：

- streaming。
- tool calls / multimodal / content blocks。
- provider binding 与 model profile 拆分。
- 完整成本 deadline 执行预算。
- verifier JSON 结果解析并驱动 repair/reroute。
- 官方 SDK golden compatibility tests。

## 下一步

继续第一、二部分，不进入第三部分。下一个小范围收口：

1. 使用至少 5 个模拟用户和跨领域 prompt 做 paper-reading campaign dry-run。
2. 检查 planner -> reader -> synthesizer 的 scaffold、route plan、scope、图谱 delta、claim coverage 是否完整衔接。
3. 将 dry-run 反馈反哺 Axio Fusion 的 task complexity、branch role 和 verifier prompt。
4. 不保存 raw paper text，不写 API key，不修改 CPA Plus/CCX/Docker。
5. 记录性能指标；若图谱/向量/哈希/合并成为热点，再开 Rust 可选加速器小步。
