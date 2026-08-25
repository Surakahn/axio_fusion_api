# Formal Harness Execution Gate（2026-08-26）

## 目的

本记录描述官方/审计 Harness execution plan 的控制面修复。它解决的是“计划模板可
生成”与“正式 campaign 已获执行授权”之间的语义混淆，不改变 Fusion runtime，也不
把 Harness 变成 Fusion 产品本体。

## 状态机

```text
diagnostic matrix 或缺少 provider freeze
  -> blocked

formal_top_three_cohort 合法，但 official imports/acquisition 未完成
  -> planned

formal cohort + freeze + 任务 + acquisition 全部完成
  -> ready_to_execute + execution_authorized=true
```

Formal cohort 必须是三个 Axio 公共模型的四种 API surface run unit 加三个外部预注册
provider rank，共 15 个 run unit。legacy internal baseline 和 all-provider diagnostic
expansion 不能进入正式 execution plan。

## Hash-only 契约

execution plan 仅保留 task 计数、suite、公共 surface、candidate/run-unit hash、Harness
pin hash、freeze path/content hash、matrix/cohort 状态和 reason code。原始 provider id、
模型 id、URL、prompt、输出、标签、本地原始路径和 secret 均留在 private operator 域，
且 safe receipt 的 `*_persisted` 字段必须为 `false`。

下游 binding/convergence 还会检查：

- execution plan 的 `execution_authorized=true`；
- `matrix_mode=formal_top_three_cohort`；
- formal cohort reason 列表为空；
- freeze path/content digest 与当前输入一致；
- official import acquisition、case/source/harness audit 同 cohort 对齐。

## 当前 r18 证据

离线 successor：

`private/runs/2026-08-26-composite-cohort-r18-harness-formal-gate/harness_control.successor/`

当前 execution plan 被正确标记为 `blocked`，因为 r18 尚未完成 provider baseline freeze；
这不是 screening 失败，也不是 provider 能力结论。convergence 的 `next_gate` 仍为
`screening`，所有网络调用标志为 `false`。

## 验证

本轮完整测试为 `1093 passed, 7 skipped`。测试覆盖 diagnostic 无 freeze、formal
top-three 的 planned/ready 转换、invalid freeze 阻断、freeze path/content binding、
convergence 和 scaffold 的敏感字段约束。

