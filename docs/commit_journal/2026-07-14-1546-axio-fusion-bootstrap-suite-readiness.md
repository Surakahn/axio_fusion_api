# 2026-07-14 15:46 Axio Fusion bootstrap suite readiness

## 本轮完成

- 继续推进独立商业子系统 Axio Fusion API 的 bootstrap 控制面。
- 在 `benchmark_gap_closure_plan` 中为每个 benchmark suite 增加：
  - `status`：区分 `needs_dataset_materialization`、
    `ready_for_live_readiness_check` 和 `ready_for_env_gated_live_batch`。
  - `dataset_receipt_preview`：复用现有 dataset receipt 逻辑或轻量路径检查，
    汇总 dataset 是否存在、是否在 cache root 下、文件 hash、case 数、labeled case 数和 blockers。
  - `live_env_gate_enabled`：只记录 `AXIO_FUSION_BENCHMARK_ENABLE_LIVE` 是否打开，不调用模型。
  - 带 `nice -n 10` 的 `download_or_materialize`、`dataset_receipt`、
    `runbook`、`dry_run_batch`、`live_batch` 命令模板，避免重任务默认打满 CPU。
- 在 closure plan 顶层增加 suite 状态计数、dataset receipt ready/blocked 计数和 live env gate 状态。
- 调整 bootstrap `next_actions`：根据 closure status 分别提示补数据集、跑 runbook/live-readiness，或执行 env-gated benchmark batch。
- 增加测试覆盖：
  - 数据集未 materialize 时，closure plan 必须保持 `ready_for_dataset_materialization`，
    suite 必须是 `needs_dataset_materialization`。
  - 数据集已经位于 cache root 时，receipt preview 必须变为 `ready`，closure plan 必须进入
    `ready_for_live_readiness_check`，并且原题、答案和 dummy key 不得出现在 manifest 中。

## 验证结果

- `python3 -m py_compile axio/fusion_api/bootstrap.py`：通过。
- `nice -n 10 python3 -m pytest -q tests/test_fusion_provider_inventory.py tests/test_fusion_benchmark.py`：
  `32 passed in 0.24s`。
- `nice -n 10 python3 -m pytest -q tests/test_fusion_provider_inventory.py tests/test_fusion_benchmark.py tests/test_fusion_api_product_boundary.py tests/test_fusion_capability_discovery.py`：
  `39 passed in 0.29s`。
- 用最小 GPQA JSONL 样例执行 bootstrap dry-run：
  - closure status 为 `ready_for_live_readiness_check`。
  - dataset receipt ready suite count 为 `1`。
  - next actions 包含 `Run benchmark runbook/live-readiness before enabling env-gated live batch.`。
- 对 dry-run 产物扫描原题、答案、dummy key、真实 key 前缀和 NVIDIA base URL：无命中。
- `git diff --check`：通过。

## 边界说明

- 本轮仍然不下载 benchmark 数据、不调用 provider 模型、不执行 live benchmark。
- bootstrap manifest 只保存控制面 metadata、路径、hash、计数、状态和命令模板。
- benchmark 原题、选项、答案、prompt、provider response、API key、base URL 都不进入 git artifact。
- `axio/studio_shell/studio_index.html` 和
  `docs/claude_goal_handoff_ai_scientist_2026-06-29.md` 是非本轮变更，未纳入 staging。

## 下一步

- 为多 suite closure plan 增加 runbook 批量投影，让 operator 能一键看出 10 类 benchmark 中哪些缺数据、
  哪些只缺 live readiness、哪些已经能进入 env-gated batch。
- 继续完善 Axio Fusion API 的能力图谱与路由策略，使 Axio-terra/pro 的选择能消费实际 scorecard 和
  co-failure 指标。
- Fusion API 控制面稳定后，回到 ASciFS 第一、二部分主线，把 OpenClaw/Hermes/Claw-code 的状态图、
  RAG、论文检索和实验执行 Harness 继续打牢。
