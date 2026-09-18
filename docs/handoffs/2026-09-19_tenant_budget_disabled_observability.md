# 每日预算关闭状态可观测性交接（2026-09-19）

## 本轮目标

继续推进商业级运行时闭环。离线审计发现每日预算配置为 `0` 时实际 admission 已关闭，
但 runtime snapshot 错误报告启用。本轮只校正安全状态投影，不执行 provider screening、
target benchmark，也不修改 r18 frozen plan/source/registry。

## 实现与验证

- `tenant_budget_enabled` 仅在正数预算阈值下为 `true`。
- 零值配置仍允许请求，`check_budget()` 返回无预算、`Retry-After=0`。
- 专项预算/限流回归：`4 passed`。
- L1/L2、`git diff --check` 通过；全量回归待本轮门禁完成。

## 发布验证

- 提交 `5609b81` 已推送到 `origin/main`；仅受控重启 Axio 18900，保留旧 console log
  备份 `private/axio_server.18900.console.log.pre-5609b81`，未停止或重启 CPA Plus。
- 新进程 PID `2553994` 通过 `/health`：`status=ready`、`runtime_routing=healthy`、
  `21/21` runtime eligible、`0` open circuit、`21` physical/`15` logical、`4` providers、
  `auto -> proxy`、`tenant_budget_enabled=false`、`auth_mode=optional`。
- 三档 route-plan dry-run 分别返回 `fast_direct_cascade`、`terra_direct`、
  `pro_panel_judge_escalation`。
- 全量回归：`1129 passed`。
