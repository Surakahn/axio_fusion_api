# Operator 账本诊断 CLI 交接（2026-09-19）

## 本轮目标

把 SQLite 租户预算账本的完整性、承载卷状态和在线备份检查收敛为可重复的 operator CLI，
不创建不存在的账本，不泄露路径、租户、token、API key 或 secret。本轮不执行 provider
screening/target benchmark，不修改 r18 frozen plan/source/registry，也不停止或修改 CPA Plus。

## 实现

- 新增命令：

  ```text
  PYTHONPATH=src python3.11 -m axio_fusion_api.cli \
    tenant-budget-ledger-diagnostic \
    --path <ledger.db> [--backup <backup.db>] \
    [--required-free-bytes N] [--output <receipt.json>]
  ```

- 执行账本 `integrity_check()`、`storage_status()` 和可选 `backup()`，输出固定
  `axio_fusion_api.tenant_budget_ledger_diagnostic.v1`。
- 缺失源文件直接返回
  `tenant_budget_shared_backend_invariant_failed`，不会调用 SQLite 初始化创建新账本。
- 损坏/缺列 schema 保持不可重试 invariant；只读、空间不足和 I/O 保持
  `tenant_budget_shared_backend_storage_unavailable` 与 `retryable=true`。
- 成功、错误和输出文件均使用原有原子 JSON 发布与安全持久化标志；异常文本不进入 receipt。

## 验证

- L1：CLI、账本模块和测试 `py_compile` 通过。
- L2：CLI 与账本关键符号导入通过。
- L3：账本/预算/公网部署专项 `36 passed`，覆盖成功备份、缺失源不创建、空间门禁和
  敏感字段隔离。
- L4：全量 Python 3.11 回归 `1178 passed`；`compileall` 与 `git diff --check` 通过。
- 本轮没有 provider/target 网络调用，没有改变 r18 frozen 输入或 serving registry。

## 当前边界与下一步

这是单主机 SQLite 的运维闭环，不代表跨主机全局预算。真实卷只读/磁盘满演练、跨主机
`FencedTenantBudgetLedger` 后端、双副本网络分区/崩溃恢复和外部 smoke 仍未完成；在这些
证据完成前继续保持公网 `shared_required` fail-closed。

