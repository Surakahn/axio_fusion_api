# 租户预算请求级上界预留交接（2026-09-19）

## 发现

`server._estimate_request_cost()` 原先只读取 route 的
`initial_fusion_resource_admission.cost.estimated_total_cost_usd`。该 receipt 明确
`optional_repair_or_escalation_included=false`，因此同 canonical retry、跨模型 failover、
panel repair 和 bounded escalation 可能在初始预留之外发生，租户预算只能在成功结算时
被动发现超额。

## 修复

当初始 pricing 与 execution pricing 均已知时，估价改为：

```text
tenant_reservation = max(initial_estimated_cost, route_budget.max_cost_usd)
```

`route_budget.max_cost_usd` 是同一请求 `_CostBudget` 的硬上限，能够覆盖允许发生的可选
分支；未知初始 pricing 仍返回 `None`，由既有 unknown-pricing policy 决定 fail-closed 或
观测模式。该修复只扩大租户预留，不改变请求内成本锁或实际结算值。

## 图片 lane 适配

图片 buffered 与真实增量流的预留现在把 verified image operation 估价与可选
`ImagePromptTransformer` 的 `axio-fast` composer hard cap 相加；composer 没有可用 text
profile 时成本为零，存在 profile 但 pricing unknown 时整体估价保持 unknown 并按既有
预算策略 fail-closed。成功结算仍只提交实际观察到的 image/composer 成本，不把未调用的
上界永久记为消费。

## 验证与剩余边界

- 新增初始估价低于/高于 hard cap 的回归；预算专项 9 项通过，相关图片/真实增量流专项
  仍通过，L1/L2 和 `git diff --check` 通过。
- 无 provider/target 网络调用，r18 frozen plan/source/registry 未修改。
- 该上界是请求级保守预算，不是供应商真实账单；真实 usage receipt 仍优先用于结算，
  失败/取消/客户端断开继续释放预留。
