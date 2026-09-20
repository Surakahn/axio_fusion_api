# 公共聚合排序证据投影

## 本轮完成

四种公共协议的 `fusion_trace_summary` 现在额外投影最多 16 条匿名排序回执。每条回执只包含
rank、候选 ID SHA-256、profile ID SHA-256、bounded score、校准置信度与 answer-claim
support fraction；候选正文、provider/model 标识、prompt 和 secret 均不会进入响应。

投影优先读取当前 `FusionResponse.judge_result`，兼容没有该字段的旧 trace。所有数值限制在
`[0, 1]`，非法 profile digest 不会原样透传而会从 process-local profile ID 重新计算 hash。
Chat Completions、Responses、Anthropic Messages 和 Gemini 使用同一个 metadata 投影，避免
客户端因协议不同看到不同的聚合证据。

## 验证

- Python 3.11 `py_compile`：通过
- L2 import：通过
- 聚合/兼容/增量流专项：`43 passed`
- 新增跨四协议 parity、边界数值与敏感字段隔离回归
- 未执行 provider、screening 或 target benchmark 网络请求

## 边界

该投影是运行时可观测性，不是 benchmark 质量、统计置信区间、provider 排名或 superiority
证据。完整 21-suite holdout 仍必须使用独立 evaluator 和 paired case-level 统计。
