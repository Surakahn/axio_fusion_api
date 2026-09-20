# 2026-09-20 最终 scorecard 审计接入 paired-call 证据

## 本轮完成

修复 benchmark scorecard 与 final completion audit 之间的证据断链。相对调用成本已在
scorecard comparison 行顶层明确暴露：

- `axio_provider_call_count_per_case`
- `baseline_provider_call_count_per_case`
- `relative_call_count_ratio`
- `paired_case_count`
- `paired_case_set_complete`
- `call_cost_claim_status`

最终审计现在要求 candidate/provider tier 有 attempted provider-call per case；Axio 与
对应 baseline comparison 还必须有调用比、正数 paired case count 和完整同 case 集标志。
美元成本仍只做独立诊断，不替代调用次数成本契约。完整同 case 集、质量不低于 baseline、
调用比严格小于 1 才能允许 `cheaper_than_baseline=true`；否则保持 `null/unverified` 或
`false`。

## 验证与边界

修复了合法完整 campaign fixture 因 paired 字段只存在嵌套对象而被 final audit 误判的问题。
L1 通过；scorecard/cost/final-audit 专项 `42 passed`。本轮未执行 provider/target 网络请求，
未修改 r18 frozen plan/source/registry、serving registry 或 CPA Plus 8317。

真实 21-suite campaign 仍必须通过 screening、transport admission、provider baseline freeze、
官方 harness/import、四协议 parity、统计校正、污染检查和最终审计；当前不能宣称质量、成本
或 superiority 已完成。
