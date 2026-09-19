# 2026-09-19 公开模型名称与相对调用成本契约

## 本轮目标

将公开模型从旧名称 `axio-fast`、`axio-terra`、`axio-pro` 收敛为三个独立产品：

| 公开号 | 原内部算法 | 智力顺序 | 调用成本顺序 | 对应 provider 基线 |
|---|---|---:|---:|---|
| `axio-luna` | `fast_direct_cascade` | 3 | 1 | 外部排名第 3 |
| `axio-terra` | `terra_selective_fusion` | 2 | 2 | 外部排名第 2 |
| `axio-sol` | `pro_panel_judge_synthesis` | 1 | 3 | 外部排名第 1 |

这里的三个名称代表三套不同的算法和演化策略，不是一个模型的 reasoning tier。
算法行为、角色合同、预算和故障降级策略保持原有语义；只更换公开 canonical identity，
让产品命名表达 `sol > terra > luna` 的智能关系和 `luna < terra < sol` 的调用成本关系。

## 兼容边界

- `PUBLIC_MODELS` 只包含 `axio-luna`、`axio-terra`、`axio-sol`。
- `/v1/models`、health、route-plan、四种协议响应的 canonical model 和 benchmark
  candidate 只使用新名称。
- `axio-fast -> axio-luna`、`axio-pro -> axio-sol` 保留为输入兼容别名，不再作为公开
  产品主名称。
- 历史 handoff/commit journal 中的旧名称保留为历史事实，不把旧名写回新的 route 或
  benchmark 结论。

## 相对调用成本

新增 `axio_fusion_api.product_call_cost_contract.v1` 与
`axio_fusion_api.provider_call_cost_receipt.v1`。

- 成本单位是同一 case 的 provider 尝试次数，而不是美元。
- 尝试次数包含成功、失败、重试、Judge 和 Synthesizer；不能只统计成功调用。
- 单模型 provider baseline 的 `baseline_call_count_per_case` 固定为 1。
- `relative_call_count_ratio = axio_attempted_calls / baseline_attempted_calls`。
- 质量/调用效率只有 paired benchmark 同时提供质量分数时才计算。
- `cheaper_than_baseline` 在没有同 case 质量门禁和完整统计证据时保持 `null`；运行时不
  宣称“更便宜”。
- receipt 继续不持久化 provider/model 原文、URL、prompt、secret 或 provider USD 价格。

## 验证

- L1/L2：新模块、路由、兼容层、trace store、server 和测试通过 `py_compile`、导入和
  `compileall`。
- L3：名称契约与成本契约专项通过；Terra 既有专项通过；全量 Python 3.11 回归
  `1188 passed`。
- `git diff --check` 通过。
- 未执行 provider screening、target benchmark 或公网流量；本轮不构成 provider 能力、
  superiority 或成本优势证据。

## 后续门禁

完整 21-suite paired campaign 需要为每个新模型与对应 provider 基线收集相同 case、四种
API surface parity、质量、失败、重试、p50/p95 延迟和 attempted-call receipt，再决定
调用效率是否支持成本优势声明。任一 provider 不可用时继续保留产品和 failover 路由，不
因为单渠道不可用而停止整个系统迭代。

`880ffff` 是本轮之前 Terra execution admission 独立提交；本名称与成本增量尚未发布到
生产 Axio，也未触碰 CPA Plus 8317、r18 frozen screening 输入或 serving registry。
