# Axio Fusion API — Handoff 2026-08-13 (Turn 27)

## 本轮结论

- 完成 TokenAPIs Claude 模型的 `anthropic_thinking` endpoint-bound budget
  probe，并把三个核心 Claude profile 提升为 `verified`。
- 公开 `axio-fast` 的 `low/medium/high/xhigh/max` 五档推理强度均已通过
  live HTTP smoke；低档首轮偶发 502 后连续三次重试均成功，判定为瞬时渠道
  波动，不是字段兼容失败。

## Claude thinking probe

候选契约将五档 Axio reasoning_effort 映射为 Claude `thinking.budget_tokens`：

| Axio effort | budget_tokens |
| --- | --- |
| low | 1024 |
| medium | 4096 |
| high | 8192 |
| xhigh | 16384 |
| max | 32768 |

live probe 结果：

- `claude-fable-5`：verified
- `claude-opus-5`：verified
- `claude-sonnet-5`：verified
- `claude-haiku-4-5-20251001`：indeterminate，保留 candidate，继续 omit

私有证据：

`private/runs/2026-08-13-claude-reasoning-probe/reasoning_probe.private.json`

校正后运行时注册表：

`private/runs/2026-08-13-claude-reasoning-probe/merged_registry.claude-thinking-verified.private.json`

## 服务验证

- `/health`：`ready`，28 个文本 profile，格式分布
  `anthropic=10 / chat=6 / responses=12`
- `axio-fast` live `/v1/chat/completions` 五档 reasoning_effort：
  - low/medium/high/xhigh/max 均返回 `AXIO-OK`
  - low 首轮 502 后重试 3/3 成功，其他档 1/1 成功
- 定向测试：
  - `tests/test_reasoning_transport.py`：31 passed
  - `tests/test_reasoning_reconciliation.py` + `tests/test_provider_enrollment.py`：33 passed
  - `tests/test_provider_http_contracts.py`：57 passed

## 下一轮

- 继续把 Responses/Gemini/NVIDIA 的 verified reasoning 证据与公开四协议
  五档映射补齐为一致的 claim audit。
- 重新探测 `claude-haiku-4-5-20251001` 的控制请求，明确其 thinking 状态。
- 推进九类二十一套基准的基线冻结与独立对照。
