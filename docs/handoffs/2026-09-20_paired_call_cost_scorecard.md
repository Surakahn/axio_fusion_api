# 2026-09-20 相对调用成本 scorecard paired case 门禁

## 本轮完成

将 benchmark scorecard 的调用成本比较从“有总调用数和总质量即可计算”收紧为可审计的
paired case 合同。Axio 与对应 provider baseline 现在必须满足：

- 两次 run 都有正数 case 数和非负 attempted provider-call 计数；
- `case_results[].case_id` 集完整重合，且与两次 run 的 case_count 一致；
- 两次 run 都有可比较的主质量分；
- 调用比为 Axio attempted calls per case / baseline attempted calls per case；
- 只有质量不低于 baseline 且调用比严格小于 1，才返回 `cheaper_than_baseline=true`、
  `cheaper_claim_status=proven`。

调用次数仍然是唯一的相对成本测量单位，必须包含成功、失败、重试、Judge 和 Synthesizer。
Provider USD 字段保留为独立观测，不进入便宜判断。部分重叠 case、不同分母、缺失质量、
负调用数、质量较低或调用比不低于 1 时，结果保持 `null/unverified` 或 `false`，不做价格
优势推断。

## 验证与边界

新增 `tests/test_benchmark_call_cost_scorecard.py`，覆盖完整 paired case、部分重叠 case、
质量/调用门禁、缺失质量和负调用数；名称/公共契约及 scorecard 相关回归通过（本轮专项
结果记录在提交说明中）。本轮未执行 provider/target 网络请求，未修改 r18 frozen 输入、
serving registry 或 CPA Plus 8317；生产发布前仍需按 L1→L4 完整回归和 Axio loopback
health/route-plan 验证。

## 后续门禁

完整 21-suite campaign 仍需为 `axio-luna`、`axio-terra`、`axio-sol` 及对应 provider
baseline 采集同一 case 集、四种 API surface、质量、失败/重试、p50/p95 延迟和安全 receipt，
并通过冻结的统计、Holm 校正、污染检查和最终审计后，才能允许任何商业成本或 superiority
claim。渠道不可用时继续维护三套产品和 fallback，不因单一 provider 失败而停止系统迭代。
