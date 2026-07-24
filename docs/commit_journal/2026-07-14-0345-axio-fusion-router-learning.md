# 2026-07-14 03:45 +0800：Axio Fusion Router Learning

## 本轮完成

本轮继续推进 ASciFS 第一、二部分基础设施，把上一轮的 `Axio Fusion Router Evaluation Harness` 往前推进成一个本地 router-learning 闭环。这个闭环不训练新模型，不调用外部模型，只从本地 artifact 中聚合证据，生成可审计的路由权重建议、弱项模型提示、verifier/fallback 建议。

1. 新增 `axio/fabric/fusion_router_learning.py`：
   - 生成 `asci_fs.axio_fusion_router_learning.v1` 报告。
   - 读取 `agent_platform/fusion_feedback_event.json`。
   - 读取 `agent_harness_eval/fusion_router_eval_report.json` 和 `fusion_router_eval_cases.json`。
   - 扫描 `**/paper_reading_campaign_model_binding_receipt.json`。
   - 标准化为 `router_learning_observations`。
   - 按 `external_model/provider/model/task_type` 聚合 route key。
   - 输出 `keep_route`、`keep_route_but_require_more_evidence`、`increase_route_weight_within_same_tier`、`decrease_route_weight_and_require_verifier`、`decrease_route_weight_and_require_fallback_review` 等建议。
   - 所有 recommendation 均声明 `trains_new_model_weights=false`、`updates_router_policy_only=true`。

2. 新增根兼容入口 `axio/fusion_router_learning.py`。

3. 集成到 `agent_harness_eval`：
   - `build_agent_harness_eval_outputs()` 会在 Fusion router eval 后生成 router learning。
   - 总 harness 新增 case：`harness_eval::axio_fusion_router_learning`。
   - agent trace outputs/artifacts 增加 learning report、recommendations、sqlite、markdown。

4. 新增 CLI：
   - `axio build-fusion-router-learning --output-dir ...`

5. 更新架构注册表：
   - `axio/fusion_router_learning.py` 登记为 Agent Fabric compatibility surface。

6. 新增测试：
   - `tests/test_fusion_router_learning.py` 覆盖 eval + feedback + Campaign receipt 聚合、SQLite 与 JSON 一致、缺证据时生成 collect-more action。
   - `tests/test_agent_harness_eval.py` 覆盖总 harness 中的 learning case 和产物路径。
   - `tests/test_cli.py` 覆盖新命令解析。

## 验证

已通过：

```bash
nice -n 10 .venv/bin/python -m py_compile \
  axio/fabric/fusion_router_learning.py \
  axio/fusion_router_learning.py \
  axio/fabric/agent_harness_eval.py \
  axio/cli.py \
  axio/architecture.py \
  tests/test_fusion_router_learning.py \
  tests/test_agent_harness_eval.py \
  tests/test_cli.py
```

```bash
git diff --check -- \
  axio/fabric/fusion_router_learning.py \
  axio/fusion_router_learning.py \
  axio/fabric/agent_harness_eval.py \
  axio/cli.py \
  axio/architecture.py \
  tests/test_fusion_router_learning.py \
  tests/test_agent_harness_eval.py \
  tests/test_cli.py
```

```bash
nice -n 10 .venv/bin/python -m pytest -q \
  tests/test_fusion_router_learning.py \
  tests/test_fusion_router_eval.py \
  tests/test_agent_harness_eval.py \
  tests/test_cli.py
```

结果：`38 passed in 59.18s`。

补充回归：

```bash
nice -n 10 .venv/bin/python -m pytest -q \
  tests/test_model_fusion.py \
  tests/test_fusion_api_server.py \
  tests/test_architecture.py
```

结果：`27 passed in 0.15s`。

CLI 冒烟：

```bash
nice -n 10 .venv/bin/python -m axio.cli build-fusion-router-eval --output-dir "$tmpdir/output"
nice -n 10 .venv/bin/python -m axio.cli build-fusion-router-learning --output-dir "$tmpdir/output"
```

learning 冒烟摘要：5 observations、5 users、5 route keys、5 recommendations、failed=0、raw_prompt_persisted=false、raw_source_text_persisted=false、trains_new_model_weights=false。

## Warning 解释

learning 报告中的 warning 继承自 router eval：CPA Plus 本地网关价格和 context window 未实测，因此建议是 `keep_route_but_require_more_evidence`，不是降低路由权重。后续可以通过真实 feedback event、Campaign invocation receipt 和模型基准库补证据。

## 工程判断

本轮仍未做 Rust 重构。Router learning 是 JSON/SQLite 聚合和治理建议，当前数据规模很小，不是性能热点。未来如果把千篇级 Campaign、上万 feedback events 和模型 benchmark traces 做大规模增量聚合，再用 profile 判断是否需要 Rust/PyO3。

## 下一步小收口

下一步建议继续在第一、二部分里做 `Router Learning -> Model Invocation Policy Projection`：把 learning recommendations 投影回 `research_model_orchestration` 的只读 advisory 字段中，让 Campaign planner/reader/synthesizer prompt contract 能看到“当前路由为什么选择、哪些证据不足、是否建议 verifier/fallback”，但仍不自动改线上路由权重。
