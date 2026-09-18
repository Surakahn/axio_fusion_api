# 非正 rate-limit 配置状态可观测性交接（2026-09-19）

## 本轮目标

继续推进商业级 admission/observability 闭环。离线审计发现 rate-limit 配置为零或负值时，
实际限流已关闭，但 runtime snapshot 对负值可能报告启用。本轮只校正安全状态投影，不执行
provider screening、target benchmark，也不修改 r18 frozen plan/source/registry。

## 实现与验证

- `rate_limit_enabled` 仅在正数限流窗口下为 `true`。
- 零值/负值配置仍允许请求，`check_rate_limit()` 返回 `allowed=true`、`Retry-After=0`。
- 预算/限流专项：`6 passed`。
- L1/L2、`git diff --check` 通过；全量回归：`1131 passed`。

## 发布前状态

- 发布前生产 Axio `18900`：`/health.status=ready`，`21/21` runtime eligible，`0` circuit，
  `21` physical / `15` logical，`4` providers，`auto -> proxy`。
- 当前生产环境未启用租户预算与 rate limit，runtime snapshot 均报告 `false`。
- CPA Plus 未停止、未重启、未修改。
