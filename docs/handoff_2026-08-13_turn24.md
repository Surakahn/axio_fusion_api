# Axio Fusion API — Handoff 2026-08-13 (Turn 24)

## 本轮结论

- 修复 Hermes feedback deadline 测试失败，`1027 passed, 7 skipped`。
- 根因是并行专家提交循环固定 `time.sleep(0.50)`，在 `max_latency_ms=700`
  这类显式短 deadline 下，先消耗掉剩余执行窗口，导致第二个专家和后续
  Judge 全部被 mandatory-stage reservation 拦截。

## 代码变更

- `orchestrator.py`
  - 新增 `_PARALLEL_STAGGER_DELAY_S = 0.50`
  - 新增 `_PARALLEL_STAGGER_MIN_HEADROOM_PER_ROLE_S = 0.25`
  - 并行专家提交前用 `deadline_budget.timeout_seconds(...)` 计算当前角色
    的可用执行窗口；只有剩余窗口足够吸收 stagger 且每个剩余 role 至少
    保留 250ms headroom 时才延迟提交。
  - 短 deadline 不再因串行化挤出必选 Judge/Synthesizer 窗口，正常长
    deadline 场景仍保留 0.5s 的 CPA 限流保护。

## 验证

- L1：`py_compile` 通过
- L2：完整测试导入通过（由 pytest 全量验证）
- L3：
  - 定向失败测试 `test_hermes_feedback_deadline_budget_blocks_reference_and_rejudge_atomically` 通过
  - `tests/test_hermes_moa.py`：`27 passed`
  - 全量 `tests/`：`1027 passed, 7 skipped in 285.19s`

## 下一轮

- 继续推进推理强度五档参数的透传与映射实现，并复核四协议上游 wire format。
- 继续图片 prompt composer 与 generation/editing 服务路径的生产级收口。
- 在渠道可用时重跑 `axio-fast/terra/pro` 与冻结基线的对照基准。

