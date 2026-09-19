# SQLite 共享租户预算账本增量交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 的商业级预算闭环，解决此前 `shared_required` 只有协议和
测试 fake、无法在多进程部署中实际执行原子租户预算的问题。本轮不执行 provider
screening、target benchmark，不修改 r18 frozen plan/source/registry，也不停止或重启
CPA Plus。

## 实现

- 新增 `SQLiteTenantBudgetLedger`，仅依赖 Python 标准库 `sqlite3`。
- 每次 reserve/settle/release 使用 `BEGIN IMMEDIATE`，在同一事务中完成预算检查、
  reservation 写入、reserved/committed 更新和状态终结。
- `(tenant_hash, day, reservation_key)` 唯一约束提供网络重试幂等；settle/release 对
  已终结 reservation 返回固定终态快照，不因后续消费改变历史结果。
- WAL、`busy_timeout` 和 `synchronous=FULL` 用于同一主机多进程的锁竞争与落盘安全。
- 增加显式 `recover` operator 操作：进程退出后 active reservation 默认继续占用预算，只有
  提供 recovery key 和不少于 8 个字符的原因才允许释放；恢复结果带固定
  `tenant_budget_reservation_recovered` reason code 且可幂等回放，避免 TTL 猜测式释放仍在
  执行的请求。
- RuntimeState 在显式 `AXIO_FUSION_TENANT_BUDGET_SQLITE_PATH` 下接入该账本；预算 scope
  为 `shared_required` 且未配置/不可用时仍返回 503 对应错误，不启动 provider/image 工作。
- 共享路径使用 tenant hash 定向查询，避免 snapshot 受租户数量排序/截断影响。
- runtime snapshot 增加 backend 名称和错误计数，仍只保留 hash-safe 字段。
- 公网部署合同在启用每日预算和 `shared_required` 时额外要求 SQLite ledger path；缺失
  时启动门继续 fail-closed。

在线备份使用 SQLite backup API 生成一致副本，receipt 只包含字节数和 SHA-256；备份文件
可以重新打开继续读取账本，目标路径必须独立且父目录已存在。

## 验证

- L1：`tenant_budget_ledger.py`、`runtime.py`、`server.py` 及测试通过 `py_compile`。
- L2：关键模块导入通过。
- L3：账本/预算专项 `24 passed`；覆盖两个 RuntimeState 共享同一文件的并发预留、幂等
  结算/释放、跨实例预算耗尽、hash-only snapshot，以及真实子进程退出后重新打开数据库
  再执行显式 recovery、SQLite 锁竞争 retryable 错误和在线备份恢复。此前相关部署契约、
  图片和真实增量流专项共 `94 passed`。
- L4：`git diff --check` 通过；没有新增 provider/target 网络调用，r18 frozen 输入与
  serving registry 未改动；全量 Python 3.11 回归 `1169 passed`。

## 当前边界

SQLite 适用于单主机多进程共享文件，不等同于跨主机 Redis/SQL 集群。活动 reservation
在进程崩溃后不会自动猜测释放，避免把仍在执行的请求误判为失效；当前通过显式 operator
recovery 提供安全人工恢复路径，但还没有自动 fencing/租约恢复。后续必须审计备份/恢复、
文件卷可靠性、锁超时告警和跨主机原子后端，再扩大公网部署范围。
当前生产 18900 仍是 loopback、预算未启用；恢复语义代码提交 `132daa9` 已推送并以
`setsid/nohup` 受控发布至 PID `2993494`。发布后 `/health=ready`、runtime routing
`healthy`、21/15 physical/logical、4 providers、`auto -> proxy`，Fast/Terra/Pro
dry-run 均通过。CPA Plus 8317 监听保持不变且未重启；旧 Axio 回滚日志已清理，只保留
`private/axio_server.18900.console.log.pre-132daa9`。

## 下一步

1. 对 SQLite 做进程崩溃/磁盘满/锁竞争/备份恢复故障注入，确认 fail-closed 与运维告警。
2. 设计带 fencing/租约恢复语义的跨主机后端适配器；未完成审计前保持 SQLite 单主机边界。
3. 补齐可信 image generation/editing pricing 后，再以真实 public/operator key 做外部 smoke。
4. provider 凭据轮换和 operator 授权后，严格回到 r18 screening -> ranking -> freeze ->
   Harness/import -> 21-suite campaign 单向门禁。
