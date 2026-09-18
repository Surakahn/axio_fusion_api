# 每日预算窗口恢复可观测性交接（2026-09-19）

## 本轮目标

继续补齐商业级成本 admission/observability 闭环。预算超限错误已经提供基于 UTC 日界的
`Retry-After`，但 `/health.runtime.budget_tenants` 快照没有恢复时间。本轮补齐
`retry_after_seconds`，不改变预算累计、租户隔离、UTC 日界或 provider 行为。

## 实现与验证

- 每个预算 tenant snapshot 新增 `retry_after_seconds`。
- 未超限或预算关闭时为 `0`。
- 已达到每日预算时，按下一个 UTC 日界计算恢复秒数。
- 日界切换时旧 day 的预算行按既有 prune 规则移除。
- 快照继续只保存 tenant/day SHA-256 与安全布尔值，不保存 raw tenant/API key。
- L1/L2、`git diff --check` 通过；专项预算/限流/并发 `9 passed`；全量回归
  `1135 passed`。
- 未执行 provider/target 网络请求，未修改 r18 frozen plan/source/registry。

## 发布后验证

代码提交 `5047e76` 已推送；已保留回滚副本
`private/axio_server.18900.console.log.pre-5047e76`，并以 `setsid/nohup` 受控重启 Axio
18900，当前 PID 为 `2645665`。发布后 `/health=ready`、`runtime_routing=healthy`、
`21/21` runtime eligible、`0` circuit、`21/15` physical/logical、`4` providers、
`auto -> proxy`；Fast/Terra/Pro route-plan 分别为 `fast_direct_cascade`、`terra_direct`、
`pro_panel_judge_escalation`，Pro 保留 Judge/Synthesizer。当前生产预算和 rate-limit 均未
启用，snapshot 的 bucket/tenant 计数为 0。CPA Plus 未停止、未重启、未修改。
