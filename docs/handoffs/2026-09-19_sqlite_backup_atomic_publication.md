# SQLite 备份原子发布与旧副本保护交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 的商业级账本恢复闭环。在线备份不能因为复制中断、磁盘 I/O 或
目标替换失败而留下半成品或覆盖最后一个可恢复副本。本轮不执行 provider screening、
target benchmark，不修改 r18 frozen plan/source/registry，也不停止或修改 CPA Plus。

## 实现

- `SQLiteTenantBudgetLedger.backup()` 在目标同一卷创建带进程/随机后缀的临时文件。
- 源账本完整性检查、在线复制和临时副本完整性检查全部成功后，使用 `os.replace()` 原子
  发布到目标路径。
- SQLite、I/O、空间、只读或目标替换失败都会清理临时文件；已有目标副本直到原子发布
  成功前保持不变。
- 备份 receipt 继续只包含 schema、字节数、SHA-256 和安全持久化标志，不泄露路径、租户、
  token、API key、原始 provider 或 secret。

## 验证

- L1/L2：账本模块、测试和关键符号导入通过。
- L3：账本专项 `23 passed`；预算/部署/真实增量流专项 `41 passed`，覆盖成功发布、替换
  失败、旧副本保留、临时文件清理和恢复后重开。
- L4：全量 Python 3.11 回归 `1179 passed`，`compileall` 与 `git diff --check` 通过；本轮
  没有 provider screening 或 target benchmark 调用，没有 frozen 输入或 serving registry
  变化。

## 受控发布

- 提交 `b128137` 已推送到 `origin/main`。
- Axio 18900 先保留 `private/axio_server.18900.console.log.pre-b128137`，再以
  `setsid/nohup` 恢复至 PID `3355306`。
- 发布后 `/health=ready`，registry 为 21/15 physical/logical、4 providers、21/21
  runtime eligible，0 open circuits，网络 `auto -> proxy`；Fast/Terra/Pro route-plan
  保持 `fast_direct_cascade`、`terra_direct`、`pro_panel_judge_escalation`。
- 8317 CPA Plus 返回 HTTP 200，未停止、未重启、未修改；旧 `pre-5ad5389` 已在验证成功后
  删除，当前仅保留上述最新 Axio 回滚副本。

## 当前边界与下一步

该修复强化单主机 SQLite 备份的故障安全性，不等同于真实卷磁盘满/只读和进程崩溃恢复演练，
也不实现跨主机 fencing/全局预算。下一步先完成隔离卷有界故障演练，再选择并审计真实跨主机
后端；公网 `shared_required` 在此之前继续 fail-closed。
