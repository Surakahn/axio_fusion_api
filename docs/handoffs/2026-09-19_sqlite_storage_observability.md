# SQLite 账本存储卷故障与可重试错误交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 产品本体的商业级租户预算闭环。完整性和备份副本门禁已经完成，
本轮补齐账本承载卷的只读、不可写、空间不足及磁盘 I/O 故障语义；不执行 provider
screening、target benchmark，不修改 r18 frozen plan/source/registry，也不停止或重启
CPA Plus。

## 实现

- `SQLiteTenantBudgetLedger.storage_status()` 使用 `statvfs` 和卷只读标志生成 hash-safe
  storage receipt，包含 `ready`、`writable`、`read_only`、`free_bytes` 和
  `required_bytes`，不返回原始路径或 secret。
- `backup()` 在复制前检查目标父卷的可写性和至少能容纳源库大小的剩余空间；复制过程中
  SQLite `disk full`、只读和磁盘 I/O 错误统一抛出
  `tenant_budget_shared_backend_storage_unavailable`，并保持 `retryable=true`。
- Runtime snapshot 增加 `tenant_budget_ledger_storage` 安全投影；后端状态读取失败时
  返回 bounded `unavailable` 状态，不泄露异常原文。
- 公共预算 admission 对明确的 shared-backend unavailable/storage reason 返回 HTTP 503；
  storage failure 带 `Retry-After`，配置缺失的 `shared_backend_required` 保留原有无重试头
  的启动配置错误语义。

## 验证

- L1：账本、runtime、server 和新增测试通过 `py_compile`。
- L2：关键模块导入通过。
- L3：预算/账本/部署专项 `31 passed`；覆盖正常 storage receipt、只读/零空间故障注入、
  backup 空间门禁、Runtime snapshot 投影和公共 503 错误契约。
- L4：全量 Python 3.11 回归 `1173 passed`；`compileall`/`git diff --check` 通过；无
  provider/target 网络调用，r18 frozen plan/source/registry 未修改。

## 受控发布

- 提交 `0af0c4d` 已推送到 `origin/main`。
- Axio 18900 先保留当前 console log 为唯一回滚副本
  `private/axio_server.18900.console.log.pre-0af0c4d`，随后以同一 r7 probe-bound
  registry、同一 image registry 和 `setsid/nohup` 受控恢复；当前 PID `3112847`。
- 发布后 `/health` 为 `ready`，registry 为 `21/21` physical/available、`15/15`
  logical/available、4 providers；runtime routing `healthy`、0 open circuit，网络
  `auto -> proxy`；Fast/Terra/Pro route-plan 分别为
  `fast_direct_cascade`、`terra_direct`、`pro_panel_judge_escalation`。
- 已删除旧的 `pre-eebb9ea` 回滚副本，仅保留上述最新副本。8317 CPA Plus 仍监听，未停止、
  未重启、未修改。

## 当前边界与下一步

该实现是预检查和错误分类，不等同于真实生产卷只读/磁盘满演练；空间检查与实际复制之间
仍存在并发耗尽窗口，因此 backup 仍必须处理 SQLite I/O 失败。SQLite 仍仅覆盖单主机共享
文件，没有自动 fencing/租约 epoch、跨主机一致性或全局配额证据。下一步是使用临时隔离
卷做有界故障演练；本轮已将 fencing token/epoch 设计固化为
`docs/architecture/tenant_budget_fencing_contract.md` 与 `FencedTenantBudgetLedger` 协议，
但尚未接入真实跨主机后端。后续再在可信 image pricing、
真实公共/operator key 和 provider credential rotation 完成后进行外部 smoke。
