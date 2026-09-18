# 租户每日预算重置提示一致性交接（2026-09-19）

## 本轮目标

继续补齐 Axio Fusion API 的商业级成本 admission 闭环。发现租户每日预算超限返回
HTTP 402 和安全预算 metadata，但缺少 `Retry-After`，调用方无法获知 UTC 日界重置时间。
本轮不执行 provider screening、target benchmark，也不修改 r18 frozen plan/source/registry。

## 实现

- `RuntimeState.check_budget()` 计算下一个 UTC 日界的有界秒数；预算未超限时返回 0。
- `tenant_budget_exhausted` 在 buffered 文本、文本增量流、图片增量流三条路径统一返回
  `Retry-After`，保留 402、错误码和安全 `metadata.budget`。
- 不改变每日预算金额、成本累计、租户身份 hash、in-flight admission 或 provider 调用。

## 验证

- 预算/限流专项：`3 passed`。
- L1：runtime/server/standalone 测试 `py_compile` 通过。
- L2：关键 runtime/server 导入通过。
- L4：`git diff --check` 通过；本轮没有 provider/target 网络请求。

## 发布验证

- 提交 `aea56c0` 已推送到 `origin/main`；仅受控重启 Axio 18900，保留旧 console log
  备份 `private/axio_server.18900.console.log.pre-aea56c0`，未停止或重启 CPA Plus。
- 新进程 PID `2524992` 通过 `/health`：`status=ready`、`runtime_routing=healthy`、
  `21/21` runtime eligible、`0` open circuit、`21` physical/`15` logical、`4` providers、
  `auto -> proxy`、`auth_required=false`、`auth_mode=optional`。
- `axio-fast`、`axio-terra`、`axio-pro` 三个 route-plan dry-run 分别返回
  `fast_direct_cascade`、`terra_direct`、`pro_panel_judge_escalation`。

## 下一步

全量回归和受控发布后继续核对 health/runtime/route-plan；外部凭据轮换完成后严格回到
credential-ready preflight -> r18 screening -> transport admission -> ranking -> freeze
-> Harness/import/convergence -> 21-suite campaign。
