# 2026-07-14 04:44 Axio Fusion API Readiness 投影到 Studio 状态

## 本轮目标

上一轮已经新增 `fusion_api_smoke_report`、`fusion-api-smoke` CLI 与 Harness Eval 消费。本轮把这个 smoke 结果投影到 Studio project state，使前端/API 调用者不需要直接打开 artifact 文件，也能看到 Axio Fusion API 的 readiness、三档模型覆盖、三种接口覆盖和安全状态。

## 已完成内容

1. `axio/studio_shell/studio_state.py`
   - 新增读取：`agent_platform/fusion_api_smoke_report.json`。
   - `modules` 新增：`axio_fusion_api_smoke`。
   - 顶层 `summary` 新增核心字段：
     - `axio_fusion_api_smoke_status`
     - `axio_fusion_api_smoke_case_count`
     - `axio_fusion_api_smoke_failed_count`
     - `axio_fusion_api_smoke_selected_model_count`
     - `axio_fusion_api_smoke_provider_call_count`
     - `axio_fusion_api_smoke_safe`
   - 新增专门结构：`axio_fusion_api_summary`，暴露：
     - schema、mode、status。
     - case/pass/fail 计数。
     - API formats 覆盖。
     - Axio-nano/Axio-terra/Axio-pro 覆盖。
     - `/models` 是否只暴露 Axio 外部模型。
     - selected internal model 数量。
     - live provider call 状态。
     - verifier/aggregator 计数。
     - raw prompt/raw source/secrets 持久化状态。
     - strategy_counts 与前 10 个 smoke cases。
     - report/markdown artifact 路径。

2. `tests/test_studio_state.py`
   - 在模拟项目中新增 `fusion_api_smoke_report.json`。
   - 验证 Studio state 能正确聚合 Axio Fusion API smoke 状态、安全状态、三档/三接口覆盖和 strategy_counts。

## 验证结果

已运行：

```bash
nice -n 10 .venv/bin/python -m py_compile axio/studio_shell/studio_state.py tests/test_studio_state.py
nice -n 10 .venv/bin/python -m pytest -q tests/test_studio_state.py -k 'aggregates_agent_rag_web_and_execution_contracts'
nice -n 10 .venv/bin/python -m pytest -q tests/test_studio_state.py
git diff --check -- axio/studio_shell/studio_state.py tests/test_studio_state.py
```

结果：

- 编译检查通过。
- targeted Studio state 测试：`1 passed, 1 deselected`。
- 完整 `tests/test_studio_state.py`：`2 passed`。
- `git diff --check` 通过。

## Rust 重构判断

本轮只做 Studio project state 的 JSON 汇总和字段投影，不属于高并发网关、千篇级去重、图路由或向量重排热路径，不进行 Rust 重构。

## 当前项目位置

仍处在 PRD 第一、二部分基础设施阶段。本轮属于第二部分 Agent Harness/Axio Fusion 可观测性建设，也会支撑第一部分论文阅读 Campaign 在运行前判断模型融合服务是否健康。

## 下一步建议

下一个小范围收口点：让 `research-knowledge-harness` 或 paper-reading campaign 在 dry-run receipt 中引用 `axio_fusion_api_summary`，形成“Studio/API readiness -> Campaign 模型编排 -> Router Learning”的可追踪链路。这样第一部分论文阅读工作流可以在正式运行前明确知道 Axio Fusion 层是否可用、是否降级、是否需要回退。
