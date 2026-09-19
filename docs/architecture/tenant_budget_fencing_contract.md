# 跨主机租户预算 Fencing 契约

## 目的

`SQLiteTenantBudgetLedger` 只提供单主机多进程原子性，不能用于跨主机多副本的全局预算。
跨主机后端必须额外实现 `FencedTenantBudgetLedger`，用后端原子递增的 fencing epoch
拒绝旧进程在崩溃恢复、网络分区或租约交接后继续写入。

## 核心不变量

1. owner 只以调用方预先计算的 SHA-256 标识进入 receipt；原始进程、主机和 API key
   不持久化。
2. `claim_fencing_epoch(owner_hash)` 在共享后端原子递增 epoch；新 claim 成功后，所有
   更低 epoch 立即失效。epoch 必须单调递增，不能由客户端时钟或随机数决定。
3. `reserve_fenced`、`settle_fenced`、`release_fenced` 和 `recover_fenced` 必须在同一
   后端事务/脚本内验证 owner、epoch、token，再执行预算状态变更；禁止先在客户端验证
   再单独写账本。
4. token 只在进程内短暂存在；`LedgerFencingClaim.safe_receipt()` 只输出 token SHA-256。
   trace、snapshot、异常和 operator receipt 不得包含原始 token。
5. stale claim 必须 fail-closed，并返回固定 `tenant_budget_fencing_stale`、
   `retryable=true`；调用方只能重新 claim 后重试，不能使用旧 reservation 写入。
6. 崩溃恢复不能依赖 TTL 猜测。operator recovery 仍需要显式 recovery key、原因和当前
   有效 fencing claim；租约续期只用于运维回收，不是账本正确性的唯一依据。
7. backend 不可用、epoch 冲突、存储故障和 schema/invariant 错误必须保持可区分的错误
   reason code，并在公共层分别投影为 retryable 503 或 fail-closed invariant 错误。

## 代码契约

- `LedgerFencingClaim`：验证 64 位十六进制 owner hash、正整数 epoch 和非空内存 token。
- `FencedTenantBudgetLedger`：在现有 `TenantBudgetLedger` 的 reserve/settle/release/
  recover 之上增加 claim 获取及四个 `*_fenced` 原子操作。
- 现有 SQLite 和 InMemory ledger 不实现该协议；它们不能通过类型名或 health receipt
  冒充跨主机 fencing backend。

## 放行门禁

跨主机共享预算只有在以下证据全部具备后才能切换 `shared_required`：

- 真实共享后端实现了 epoch/token 原子比较与写入；
- 双副本并发、进程崩溃、网络分区、旧 owner 恢复写入和 epoch 冲突故障演练通过；
- 备份/恢复、磁盘满、锁超时、operator recovery 和错误投影均有 hash-safe receipt；
- 公共部署合同能验证 backend/fencing readiness，失败时 provider/image 不启动；
- 至少一次跨副本外部 smoke 证明 tenant/day/reservation key 幂等和全局预算一致。

在这些证据完成前，SQLite 继续保持单主机边界，公网多副本预算继续 fail-closed，不做
“已支持全局配额”的声明。

