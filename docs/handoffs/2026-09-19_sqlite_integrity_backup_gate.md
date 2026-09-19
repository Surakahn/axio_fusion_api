# SQLite 账本完整性与备份恢复门禁交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 产品本体的商业级预算闭环。已有 SQLite 账本支持单主机多进程
原子预算、幂等结算、显式 operator recovery 和在线备份，但备份此前主要依据文件存在与
SHA-256 判断，缺少 SQLite 内部一致性和 schema 完整性证据。本轮不执行 provider
screening、target benchmark，不修改 r18 frozen plan/source/registry，也不停止或重启
CPA Plus。

## 实现

- `SQLiteTenantBudgetLedger.integrity_check()` 使用 `PRAGMA integrity_check`，并校验
  `accounts` 与 `reservations` 的必需列集合。
- 正常检查返回 `axio_fusion_api.tenant_budget_ledger_integrity.v1` hash-safe receipt；
  不返回数据库路径、租户标识、reservation 内容或 secret。
- SQLite 页损坏、非数据库文件和必需 schema 缺失均 fail-closed 为
  `tenant_budget_shared_backend_invariant_failed`；锁/暂时数据库不可用保持
  `tenant_budget_shared_backend_unavailable` retryable 语义。
- `backup()` 在源库复制前执行完整性检查，并在目标副本复制完成后再次检查；只有两端
  都通过才生成原有 hash-only backup receipt。

## 验证

- L1：修改后的账本模块和测试通过 `py_compile`。
- L2：关键账本导入通过。
- L3：账本/预算/部署/真实增量流专项 `56 passed`；覆盖正常源库、在线备份重开、缺列
  schema、清理 WAL sidecar 后的损坏文件，以及原有并发/恢复/锁竞争路径。
- L4：全量 Python 3.11 回归 `1171 passed`；`git diff --check` 通过；无 provider/target
  网络调用，r18 frozen 输入和 serving registry 未修改。

## 当前边界

该门禁只证明 SQLite 文件在检查时可读且 schema 完整，不等同于磁盘满/卷丢失演练、自动
fencing/租约恢复或跨主机全局配额。SQLite 仍仅支持单主机共享文件；公网多副本预算不能
据此宣称完成。当前生产 18900 保持 loopback、预算未启用；CPA Plus 8317 保持运行且未
修改。

## 下一步

1. 做有界的磁盘满、只读卷、WAL/备份恢复和锁竞争故障注入，确认 fail-closed、retryable
   分类与运维告警，不污染生产数据。
2. 设计带 fencing token/租约 epoch 的跨主机账本适配器契约；在审计完成前保持
   `shared_required` 的单主机边界声明。
3. 补齐可信 image generation/editing pricing，再由部署方配置真实公共/operator key
   做外部 smoke。
4. 之后严格回到 credential-ready preflight -> r18 screening -> transport admission ->
   ranking -> provider freeze -> Harness/import/convergence -> 21-suite campaign。

