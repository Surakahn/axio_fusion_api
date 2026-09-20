# 2026-09-20 FencedTenantBudgetLedger 后端契约审计

## 本轮完成

新增 `audit_fenced_ledger_backend()` 离线审计。它只读取后端的接口形状，不执行
claim、写入、网络请求或修改任何账本状态，输出固定的
`axio_fusion_api.fenced_ledger_backend_audit.v1` 安全 receipt。

审计要求存在非空 `fencing_backend_name`，以及 `claim_fencing_epoch`、
`reserve_fenced`、`settle_fenced`、`release_fenced`、`recover_fenced` 五个可调用方法。
SQLite 类型会显式以 `sqlite_backend_not_cross_host_fenced` 拒绝，避免把单机账本误报为
跨主机全局 fencing 后端。receipt 不保存后端实例 repr、路径或凭据。

## 验证

- `python3.11 -m py_compile src/axio_fusion_api/tenant_budget_ledger.py tests/test_tenant_budget_ledger.py`
- `python3.11 -m pytest tests/test_tenant_budget_ledger.py -q`：专项通过
- `git diff --check`：通过

本轮未启动 provider/target 网络调用，未修改筛选冻结输入、serving registry、Axio 18900
或 CPA Plus 8317。该审计不代表已有 SQLite 实现具备跨主机能力；真实 Redis/SQL/共识后端
仍需独立实现与网络分区、epoch 冲突、双副本崩溃恢复演练。
