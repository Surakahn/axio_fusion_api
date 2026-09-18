# 租户预算并发预留与结算交接（2026-09-19）

## 本轮目标

继续补齐商业级成本闭环。此前每日预算只在请求开始和完成后检查/累计，多个并发已知成本
请求可能同时通过 admission，完成后超过租户预算。本轮增加进程内原子预留、成功结算和
失败/取消释放，不执行 provider screening、target benchmark，不修改 r18 frozen 输入。

## 实现

- `RuntimeState.reserve_budget()` 在同一锁内读取当日已结算与 in-flight 预留，已知成本不足
  时 fail-closed；`TenantBudgetLease` 提供线程安全、幂等 `observe/settle`。
- buffered 文本、文本增量流、buffered 图片和图片增量流在 provider 工作前预留；最终
  成功交付后结算实际成本，provider 异常、客户端断开、并发拒绝和取消释放预留。
- 图片 generation/editing 预留采用所有兼容 failover 副本中的保守最大可信价格；text
  prompt composer 的已知成本与最终图片成本在同一 lease 中合并。
- unknown pricing 不伪造为零；预算启用时默认 `tenant_budget_pricing_unknown` fail-closed，
  仅显式设置 `AXIO_FUSION_TENANT_BUDGET_UNKNOWN_PRICING=allow` 才进入观测模式。
- runtime snapshot 增加 `reserved_usd`、`committed_plus_reserved_usd`、预留租户数、
  overcommit 计数和 unknown-pricing policy，全部为 hash-safe；UTC 日界清理旧预留。
- 修复 `_CostBudget.acquire()` 中位于 `return None` 后的死代码，使单请求 priced reservation
  真正增加 `reserved_cost_usd`。

## 验证

- L1/L2：runtime/server/image/orchestrator/test 文件 `py_compile` 与关键导入通过。
- L3：新增并发竞态、幂等 release、unknown pricing、UTC rollover 专项 3 项通过；图片/流式
  回归 73 项通过；全量 `1145 passed, 0 skipped`。
- L4：`git diff --check` 通过；租户 key、provider 标识、prompt、输出和 secret 未进入
  snapshot/receipt。该增量不构成 provider 能力、排名、成本优势或 superiority 证据。

## 当前限制与下一步

当前生产每日预算仍未启用，因此本轮没有变更 live 流量语义，也未重启 CPA Plus。公网启用
预算前需先明确 image registry 价格证据，并使用同一 fake-provider/真实边界回归后受控发布。
预算预留仍是单进程控制；多副本部署必须在后续架构中接入共享原子账本，不能把本地 snapshot
当成全局配额证据。
