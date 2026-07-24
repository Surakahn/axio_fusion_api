# 2026-07-14 15:58 Axio Fusion multisuite runbook projection

## 本轮完成

- 继续推进独立商业子系统 Axio Fusion API 的 benchmark 控制面。
- 在 bootstrap `benchmark_gap_closure_plan` 中增加 suite 级 `runbook_projection`：
  - 根据 dataset receipt preview 判断下一条安全命令。
  - 数据集缺失时，下一步是 `download_or_materialize`。
  - 数据集已经 ready 时，下一步是 `runbook`，而不是直接 live batch。
  - 明确 live batch 仍需 runbook/live-readiness 和 scorecard，不因为 env gate 或 dataset ready 就直接放行。
- 增加 `benchmark-live-readiness` 命令模板，并继续让所有重命令带 `nice -n 10`。
- 增加顶层 `runbook_projection_summary`：
  - suite 总数。
  - ready for runbook 数。
  - blocked projection 数。
  - 下一步安全命令类型计数。
  - 每个 suite 的第一条安全命令字符串。
- 更新 bootstrap Markdown，让 operator 不打开 JSON 也能看到：
  - 每个 suite 的状态。
  - 下一步安全命令类型。
  - runbook projection 汇总。
- 增加多 suite 测试：GPQA 已 materialize、BBH 缺数据集时，bootstrap 必须同时投影
  `runbook` 和 `download_or_materialize` 两种下一步。

## 验证结果

- `python3 -m py_compile axio/fusion_api/bootstrap.py`：通过。
- `nice -n 10 python3 -m pytest -q tests/test_fusion_provider_inventory.py tests/test_fusion_benchmark.py`：
  `33 passed in 0.26s`。
- Fusion 聚焦回归：
  `nice -n 10 python3 -m pytest -q tests/test_fusion_provider_inventory.py tests/test_fusion_benchmark.py tests/test_fusion_api_product_boundary.py tests/test_fusion_capability_discovery.py tests/test_fusion_api_server.py tests/test_fusion_router_eval.py tests/test_fusion_router_learning.py tests/test_model_fusion.py tests/test_llm.py`
  结果：`111 passed in 1.08s`。
- 架构和 Fusion 子集回归：
  `41 passed in 0.29s`。
- 多 suite dry-run bootstrap：
  - `suite_count = 2`。
  - `dataset_ready = 1`。
  - `dataset_blocked = 1`。
  - GPQA 的下一步为 `runbook`。
  - BBH 的下一步为 `download_or_materialize`。
  - Markdown 成功显示 runbook projection summary。
- 对 dry-run 产物扫描原题、答案、dummy key、`nvapi-` 和 NVIDIA base URL：无命中。
- `git diff --check`：通过。

## 边界说明

- 本轮仍然不下载 benchmark、不调用模型、不执行 live benchmark。
- bootstrap 只写控制面 metadata、路径、hash、计数、状态和命令模板。
- benchmark 原题、选项、答案、prompt、provider response、API key、base URL 都不进入 git artifact。
- `axio/studio_shell/studio_index.html` 和
  `docs/claude_goal_handoff_ai_scientist_2026-06-29.md` 是非本轮变更，未纳入 staging。

## 下一步

- 将 runbook projection 与 scorecard/co-failure 反馈进一步连接，让 Axio Fusion 路由策略能消费真实 benchmark 结果。
- 为 benchmark suite 批量 materialization 增加更明确的 cache receipt 总览，继续保持大文件在机械盘、仓库只存 manifest。
- Fusion API 控制面稳定后，回到 ASciFS 第一、二部分主线，继续把 OpenClaw/Hermes/Claw-code Harness 和 RAG/论文检索/实验执行链路打牢。
