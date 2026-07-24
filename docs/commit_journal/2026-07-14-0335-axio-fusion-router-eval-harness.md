# 2026-07-14 03:35 +0800：Axio Fusion Router Evaluation Harness

## 本轮完成

本轮继续推进 ASciFS 第一、二部分基础设施，在上一轮 Axio Fusion 安全边界之后，补上一个可复用的离线评测闭环：`Axio Fusion Router Evaluation Harness`。目标不是调用真实外部模型，而是用本地 dry-run 方式持续验收 Axio-nano / Axio-terra / Axio-pro 的路由、成本信号、verifier、fallback 和 artifact 安全声明。

1. 新增 `axio/fabric/fusion_router_eval.py`：
   - 生成 `asci_fs.axio_fusion_router_eval.v1` 报告。
   - 默认覆盖 5 个用户 scope。
   - 覆盖 `Axio-nano`、`Axio-terra`、`Axio-pro` 三个对外模型档位。
   - 覆盖 Chat Completions、Responses、Anthropic 三种 API 形态。
   - 覆盖 `simple_extraction`、`campaign_reader`、`campaign_planner`、`campaign_synthesizer`、`campaign_acceptance_reviewer` 五类任务。
   - 对每个 case 检查外部模型名、metadata tier、selected provider/model、fallback、verifier policy、parallel/aggregator policy、dry-run 无 provider call、prompt marker 不持久化、secret/raw source 声明。
   - 输出 JSON、Markdown、SQLite。

2. 新增根兼容入口 `axio/fusion_router_eval.py`。

3. 集成到 `agent_harness_eval`：
   - `build_agent_harness_eval_outputs()` 会先生成 Fusion router 子报告，再把它纳入总 harness evidence。
   - 总 harness 新增 case：`harness_eval::axio_fusion_router_policy`。
   - agent trace outputs/artifacts 增加 Fusion router report/cases/sqlite/markdown 路径。

4. 新增 CLI：
   - `axio build-fusion-router-eval --output-dir ...`
   - 用于单独刷新 Fusion router eval，不必每次跑完整 harness。

5. 更新架构注册表：
   - `axio/fusion_router_eval.py` 登记为 Agent Fabric compatibility surface。
   - `axio/fabric/fusion_router_eval.py` 保持为 canonical package implementation，不登记成薄 wrapper。
   - `axio/sensitive_text.py` 登记为 core allowed root module，修复上一轮遗留的架构 warning。

## 验证

已通过：

```bash
nice -n 10 .venv/bin/python -m py_compile \
  axio/fabric/fusion_router_eval.py \
  axio/fusion_router_eval.py \
  axio/fabric/agent_harness_eval.py \
  axio/cli.py \
  axio/architecture.py \
  tests/test_fusion_router_eval.py \
  tests/test_agent_harness_eval.py \
  tests/test_cli.py
```

```bash
git diff --check -- \
  axio/fabric/fusion_router_eval.py \
  axio/fusion_router_eval.py \
  axio/fabric/agent_harness_eval.py \
  axio/cli.py \
  axio/architecture.py \
  tests/test_fusion_router_eval.py \
  tests/test_agent_harness_eval.py \
  tests/test_cli.py
```

```bash
nice -n 10 .venv/bin/python -m pytest -q \
  tests/test_fusion_router_eval.py \
  tests/test_agent_harness_eval.py \
  tests/test_cli.py \
  tests/test_model_fusion.py \
  tests/test_fusion_api_server.py \
  tests/test_architecture.py
```

结果：`62 passed in 58.82s`。

CLI 冒烟：

```bash
nice -n 10 .venv/bin/python -m axio.cli build-fusion-router-eval --output-dir "$tmpdir/output"
```

产物：

- `agent_harness_eval/fusion_router_eval_report.json`
- `agent_harness_eval/fusion_router_eval_cases.json`
- `agent_harness_eval/fusion_router_eval.md`
- `agent_harness_eval/fusion_router_eval.sqlite`

冒烟摘要：5 cases、5 users、覆盖 Axio-nano/Axio-terra/Axio-pro、failed=0、verifier_required_count=2、aggregator_or_parallel_count=2、raw_prompt_persisted=false。

## Warning 解释

默认报告中会出现若干 warning，主要来自：

1. CPA Plus 本地网关当前没有可证明的市场参考价格，所以 `reference_cost_unknown`。
2. CPA Plus 部分模型没有本地可证明的 context window 测量，所以长上下文任务标记 `context_window_unknown_measure_before_large_prompt`。

这些 warning 不代表路由失败，而是把“价格/窗口未实测”作为后续模型基准库和路由学习的待补证据。失败条件仍然集中在路由错误、tier 错误、verifier/fallback 策略错误、prompt/source/secret 持久化等硬边界。

## 工程判断

本轮仍未引入 Rust。原因是该能力是离线评测和治理产物生成，当前瓶颈不在 CPU 密集计算。等到千篇级路由评分、图遍历或大批量 case 评测出现明确 CPU profile，再考虑 Rust/PyO3 或 sidecar。

## 下一步小收口

下一步建议继续在第一、二部分内推进 `Axio Fusion Router Evaluation -> Router Learning` 的闭环：把 feedback event、Fusion router eval case、Campaign 实际运行的 model invocation receipt 聚合成一个轻量 SQLite learning table，先不训练模型，只用于更新路由权重建议、暴露弱项模型、提示是否需要 verifier 或降级 fallback。
