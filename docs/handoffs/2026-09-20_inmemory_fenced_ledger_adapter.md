# 离线 fencing 账本适配器增量交接（2026-09-20）

本轮新增 `InMemoryFencedTenantBudgetLedger`，用于离线双副本、旧 claim、epoch 冲突
和幂等预留测试。实现以进程内锁原子递增 epoch，并在每个 `*_fenced` 操作执行前校验
当前 token/epoch；旧 claim 固定返回 `tenant_budget_fencing_stale`。

该适配器明确标记为 `in_memory_fenced_test_only`，不具备跨进程或跨主机持久性，不能
作为 `shared_required` 的生产后端，也不能替代 Redis/SQL/共识后端的原子 fencing。
跨主机后端审计、网络分区和崩溃恢复演练仍保持未完成状态。

验证：`tests/test_tenant_budget_ledger.py` 26 passed；Python 3.11 编译与导入门禁通过。
