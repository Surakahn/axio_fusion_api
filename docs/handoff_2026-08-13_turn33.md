# Axio Fusion API — Handoff 2026-08-13 (Turn 33)

## 本轮结论

- 六模型核心 screening 继续后台运行，PID `2498355`，已超过 3.5 小时。
- `claude-sonnet-5 / LiveBench` 已终态：79 scored、29 timeout、
  transport failure rate 26.85%，failed。
- 当前运行：`gpt-5.6-luna / MMLU-Pro`，2/112 完成。
- 推理强度参数确认已完整实现（7 档、chat/responses 双格式、effort_map
  映射、Anthropic/Gemini thinking budget），不是 blocker。

## 已终态 units 汇总（5/12）

| unit | status | scored | mean | timeout | rate |
|---|---|---|---|---|---|
| claude-opus-5 / LiveBench | failed | 97 | 0.8095 | 11 | 10.19% |
| gpt-5.6-sol / MMLU-Pro | completed | 112 | 0.8750 | 0 | 0.00% |
| claude-fable-5 / LiveBench | failed | 104 | 0.8833 | 4 | 3.70% |
| gpt-5.6-terra / MMLU-Pro | failed | 101 | 0.8416 | 11 | 9.82% |
| claude-sonnet-5 / LiveBench | failed | 79 | - | 29 | 26.85% |

## 运行中

| unit | status | scored | timeout |
|---|---|---|---|
| gpt-5.6-luna / MMLU-Pro | running | 2/112 | - |

## 待运行（6/12）

5. `gpt-5.6-luna / LiveBench`
6. `claude-sonnet-5 / MMLU-Pro`
7. `gpt-5.6-terra / LiveBench`
8. `claude-fable-5 / MMLU-Pro`
9. `gpt-5.6-sol / LiveBench`
10. `claude-opus-5 / MMLU-Pro`

## 关键观察

- LiveBench 全部 3/3 已终态 unit 失败（10.19%~26.85%），
  MMLU-Pro 1/2 完成、1/2 失败。
- 失败原因全部为 90 秒 provider timeout，无 5xx 或流式协议错误。
- 预计剩余 7 个 unit 需数小时；将跨夜运行。

## 下一轮

- 继续 15 分钟低频探针等待全部 12 units 终态。
- 首轮终态后用 `--retry-failed` 仅重试失败 case。
- 如果 MMLU-Pro 有足够通过门禁的 unit，可尝试 screening-to-ranking。
- LiveBench 全部失败可能影响 ranking 覆盖率；需要评估是否需要
  transport admission 方案。
