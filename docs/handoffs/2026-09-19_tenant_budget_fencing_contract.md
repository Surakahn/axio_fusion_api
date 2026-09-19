# 跨主机租户预算 fencing/epoch 契约交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 的商业级多副本预算边界。SQLite 已完成单主机事务、完整性、
备份和存储故障语义，但没有跨主机 fencing；本轮固化可实现、可审计的 epoch/token 契约，
不把 SQLite 或测试 fake 冒充分布式后端，不执行 provider screening/target benchmark，
不修改 r18 frozen plan/source/registry，也不停止或修改 CPA Plus。

## 契约实现

- `LedgerFencingClaim` 验证 SHA-256 owner、正整数 epoch 和非空内存 token；safe receipt
  只保存 token SHA-256，原始 token 不进入 trace、snapshot 或 artifact。
- `FencedTenantBudgetLedger` 扩展 `TenantBudgetLedger`，要求后端原子实现
  `claim_fencing_epoch`、`reserve_fenced`、`settle_fenced`、`release_fenced` 和
  `recover_fenced`。
- 新 epoch 必须立即使旧 claim 失效；所有写操作必须在同一事务/脚本比较 owner、epoch、
  token，不能依赖客户端本地比较、TTL 或墙钟。
- 旧 claim 固定返回 `tenant_budget_fencing_stale` 且 `retryable=true`；调用方必须重新
  claim 后再尝试，不能用旧 reservation 继续写入。
- SQLite 和 InMemory ledger 明确不实现该协议；`shared_required` 仍不代表跨主机能力。

## 验证

- L1/L2：账本模块、测试和关键导入通过。
- L3：fencing/账本/预算/部署专项 `33 passed`；全量 Python 3.11 回归 `1175 passed`。
- L4：`compileall`、`git diff --check` 通过；没有 provider/target 网络调用或 frozen
  输入修改。

## 受控发布

- 提交 `5ad5389` 已推送到 `origin/main`。
- Axio 18900 以同一 r7 probe-bound registry、同一 image registry 和 `setsid/nohup`
  受控恢复，当前 PID `3139688`。
- 发布后 `/health=ready`，registry 为 21/21 physical、15/15 logical、4 providers，
  runtime routing `healthy`、0 open circuit、网络 `auto -> proxy`；Fast/Terra/Pro
  route-plan 仍分别为 `fast_direct_cascade`、`terra_direct`、
  `pro_panel_judge_escalation`。
- 已删除旧的 `pre-0af0c4d` 回滚副本，仅保留
  `private/axio_server.18900.console.log.pre-5ad5389`。8317 CPA Plus 仍监听，未停止、
  未重启、未修改。

## 未完成边界

本轮是架构契约与离线语义证据，不是跨主机后端实现。仍需选择并审计真实 Redis/SQL/共识
后端，完成双副本并发、网络分区、进程崩溃、旧 owner 恢复写入、epoch 冲突、备份恢复和
跨副本外部 smoke；完成前继续保持公网 shared budget fail-closed。

