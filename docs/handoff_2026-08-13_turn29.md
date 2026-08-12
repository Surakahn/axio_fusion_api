# Axio Fusion API — Handoff 2026-08-13 (Turn 29)

## 本轮结论

- 修复 `axio-pro` 高推理强度 HTTP 长文本请求 502：原短 prompt 的 screened
  p95 被同时用于 Fusion 外层 deadline 和单专家超时，导致 `claude-fable-5`/
  `claude-opus-5` 在 7.9-9.4 秒被提前判定 `fusion_request_deadline_exhausted`，
  上游实际上需要 15-33 秒。
- 新增高推理强度运行时保护：`high/xhigh/max` 保留调用方 deadline，不再被
  4.5x 短 prompt p95 压缩到 22 秒；专家超时在普通 p95 cap 之上增加
  reasoning-aware floor。
- HTTP 实测同一长 prompt 从 502 恢复为 200，耗时约 55 秒并返回完整实现。

## 关键修改

文件：[orchestrator.py](/home/he/axio_fusion_api/src/axio_fusion_api/orchestrator.py)

- `_runtime_fusion_latency_budget()` 增加可选 `request` 参数。
- 对 `reasoning_effort` 为 `high`、`xhigh`、`max` 的 provider-Judge Fusion
  路由，不应用 `target_max_vs_single_model` 压缩，保留调用方最大延迟。
- `_timeout_for_role()` 在 screened p95 cap 上增加 reasoning-aware floor：
  `high=30s`、`xhigh=45s`、`max=45s`，再受 outer deadline 约束。
- 新增回归测试覆盖高推理强度 deadline 保留和专家 timeout floor。

## 验证

- `python3.11 -m py_compile src/axio_fusion_api/orchestrator.py`
- `PYTHONPATH=src python3.11 -m pytest tests/test_fusion_core_regressions.py -q --tb=short`
  `91 passed, 1 skipped`
- `PYTHONPATH=src python3.11 -m pytest tests/test_reasoning_transport.py -q --tb=short`
  `31 passed`
- `git diff --check` 通过
- 服务已用 `setsid` 重启并监听 `127.0.0.1:18900`，`/health` 返回 ready。
- 实测 `POST /v1/chat/completions` `axio-pro` 长代码任务 `reasoning_effort=max`
  返回 200，响应约 29 KB。

## 下一轮

- 继续验证 `axio-fast`、`axio-terra` 在低/中推理强度下未回归。
- 推进九类二十一套标准评测的 provider baseline freeze 与独立对照。
- 保持不提交 `private/` 和 `*.private.json`。
