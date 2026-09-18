# 共享租户预算账本契约交接（2026-09-19）

## 本轮目标

当前 `RuntimeState` 的预算账本是进程内实现，不能作为多副本全局配额。为了让后续真实
共享后端接入有清晰边界，本轮先固化最小协议和离线故障语义，不把测试 fake 当成生产
实现，也不改变当前 serving registry 或 r18 证据。

## 契约

`TenantBudgetLedger` 要求后端提供：

- 原子 `reserve(tenant_hash, day, amount, budget, reservation_key)`；检查与预留必须在同一
  后端事务/脚本中完成。
- `reservation_key` 在 tenant/day 范围内幂等，网络重试不能产生第二个 active lease。
- `settle`、`release` 幂等；未知 reservation、非法金额和状态不变量必须 fail-closed。
- 后端不可用必须返回可识别的 retryable `tenant_budget_shared_backend_unavailable`，不能
  静默放行。
- snapshot 只能输出 hash-only tenant 投影和 reserved/committed 数值。

## 实现与验证

- 新增 `src/axio_fusion_api/tenant_budget_ledger.py`。
- `InMemoryTenantBudgetLedger` 仅用于测试，支持并发原子性、故障注入、恢复、幂等和
  overcommit 观测；不会被环境变量自动发现或接入生产 `RuntimeState`。
- 新增 `tests/test_tenant_budget_ledger.py`，专项 8 项通过；本轮部署契约/预算/图片/流式
  与全量回归合计 `1154 passed`，L1/L2、compileall、`git diff --check` 通过。

## 未完成边界

真实共享实现仍需明确事务/脚本、租约恢复、时钟与 UTC 日界、故障注入、跨副本并发和
降级策略；完成前 `AXIO_FUSION_TENANT_BUDGET_SCOPE=shared_required` 只会 fail-closed，
不能宣称多副本预算已经可用。
