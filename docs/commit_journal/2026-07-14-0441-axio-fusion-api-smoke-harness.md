# 2026-07-14 04:41 Axio Fusion API Smoke 与 Harness 闭环

## 本轮目标

在已经完成 Axio Fusion 路由、Router Eval、Router Learning、Stage Runtime/Studio 状态投影之后，补齐一个更接近真实部署者视角的小闭环：用一次 dry-run smoke 同时验证 Axio-nano、Axio-terra、Axio-pro 三档模型外观，以及 chat/completions、responses、Anthropic messages 三种 API 兼容形态，并让 Agent Harness Eval 自动消费这个结果。

## 已完成内容

1. 新增 Axio Fusion API smoke report。
   - 新增 schema：`asci_fs.axio_fusion_api_smoke.v1`。
   - 新增 `build_fusion_api_smoke_report()`，默认 dry-run，不触发真实 provider 调用。
   - 新增 `build_fusion_api_smoke_outputs()`，写出：
     - `agent_platform/fusion_api_smoke_report.json`
     - `agent_platform/fusion_api_smoke_report.md`
   - smoke case 覆盖：
     - `Axio-pro` + `chat/completions` + `campaign_synthesizer`
     - `Axio-nano` + `responses` + `simple_extraction`
     - `Axio-terra` + `anthropic` + `campaign_reader`

2. 新增 `/v1/smoke` API 端点。
   - 兼容路径：`/v1/smoke`、`/smoke`、`/v1/axio/smoke`。
   - 输出只包含结构化路由、响应形态、安全和计数信息。
   - 不保存 raw prompt、raw source text、secrets、论文全文或模型 API key。

3. 新增 CLI 命令。
   - 命令：`axio fusion-api-smoke`
   - 默认 dry-run。
   - 支持 `--registry` 传入任意模型清单或 Axio registry，验证 Axio 能从任意可用模型集合合成三档外部模型。
   - 支持 `--live`，但默认关闭，避免误触真实 provider 调用。

4. 接入 Agent Harness Eval。
   - `build-agent-harness-eval` 会先生成 `fusion_api_smoke_report`。
   - 新增 eval case：`harness_eval::axio_fusion_api_smoke`。
   - 评估条件包括：
     - 三档 Axio 全覆盖。
     - 三种 API 格式全覆盖。
     - `/models` 只暴露 Axio 外部模型名。
     - 每个 case 都有 selected internal model。
     - 默认不发生 live provider call。
     - 不持久化 raw prompt、raw source text、secrets。

## 用户模拟

已实际运行一次 CLI dry-run 到 `/tmp/axio_fusion_api_smoke_test`：

```bash
rm -rf /tmp/axio_fusion_api_smoke_test
nice -n 10 .venv/bin/python -m axio.cli fusion-api-smoke --output-dir /tmp/axio_fusion_api_smoke_test
```

输出报告确认：

- schema：`asci_fs.axio_fusion_api_smoke.v1`
- status：`passed`
- case_count：`3`
- Axio tiers：`Axio-nano`、`Axio-terra`、`Axio-pro`
- API formats：`anthropic`、`chat/completions`、`responses`

## 验证结果

已运行：

```bash
nice -n 10 .venv/bin/python -m py_compile axio/fusion_api_server.py axio/cli.py axio/fabric/agent_harness_eval.py tests/test_fusion_api_server.py tests/test_cli.py tests/test_agent_harness_eval.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_fusion_api_server.py tests/test_agent_harness_eval.py tests/test_cli.py -k 'fusion_api or fusion_router or agent_harness_eval_writes_cases_backlog_score_and_trace or cli_defaults_keep_agent'
nice -n 10 .venv/bin/python -m pytest -q tests/test_fusion_api_server.py tests/test_model_fusion.py tests/test_agent_harness_eval.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_fusion_api_server.py tests/test_agent_harness_eval.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_cli.py
git diff --check -- axio/fusion_api_server.py axio/cli.py axio/fabric/agent_harness_eval.py tests/test_fusion_api_server.py tests/test_cli.py tests/test_agent_harness_eval.py
```

结果：

- 编译检查通过。
- targeted tests：`11 passed, 32 deselected`。
- Fusion/API/Harness 主链路：`31 passed`。
- Fusion API + Harness Eval：`14 passed`。
- CLI 全量：`29 passed`。
- `git diff --check` 通过。

## Rust 重构判断

本轮实现主要是 API smoke 编排、JSON artifact 汇总和 Harness Eval 消费，不是 CPU 热路径，也不涉及高吞吐网络代理或千篇级图路由计算。因此不做 Rust 重构。

后续更适合 Rust 的候选仍然是：

- 高并发 Axio Fusion API 网关的流式代理、超时和 fallback 调度。
- 千篇级论文 metadata 去重、hash、批量图边构建。
- 图数据库路由中的大规模候选重排和路径评分。

## 当前项目位置

仍处在 PRD 第一、二部分基础设施阶段。这个闭环服务于第二部分的 Agent Harness 和模型融合基础设施，同时会被第一部分论文阅读 Campaign 复用：后续可以在论文 planner/reader/synthesizer 运行前先执行 `fusion-api-smoke` 或读取其报告，确认 Axio 模型融合层健康。

## 下一步建议

下一个不太大的收口点：把 `fusion_api_smoke_report` 投影到 Studio project state 或 Stage Runtime summary，使前端/用户能直接看到 Axio API readiness、三档模型覆盖、三接口覆盖和安全状态。这个点小而直接，能补齐“API 已可用但用户不可见”的观测缺口。
