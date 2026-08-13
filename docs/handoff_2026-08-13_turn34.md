# Axio Fusion API — Handoff 2026-08-13 (Turn 34)

## 本轮结论

- 六模型核心 screening 已运行约 7 小时，PID `2498355` 仍存活。
- `claude-sonnet-5 / MMLU-Pro` 通过 2% 运输失败门禁：
  110 scored、2 timeout、1.79%，成为第二个 completed unit。
- `gpt-5.6-luna / LiveBench` 终态失败：67 scored、41 timeout、37.96%。
- 当前运行：`gpt-5.6-terra / LiveBench`，17/108，0 失败。

## 已终态 units（8/12）

| unit | status | scored | timeout | rate |
|---|---|---|---|---|
| claude-opus-5 / LiveBench | failed | 97 | 11 | 10.19% |
| gpt-5.6-sol / MMLU-Pro | completed | 112 | 0 | 0.00% |
| claude-fable-5 / LiveBench | failed | 104 | 4 | 3.70% |
| gpt-5.6-terra / MMLU-Pro | failed | 101 | 11 | 9.82% |
| claude-sonnet-5 / LiveBench | failed | 79 | 29 | 26.85% |
| gpt-5.6-luna / MMLU-Pro | failed | 101 | 11 | 9.82% |
| gpt-5.6-luna / LiveBench | failed | 67 | 41 | 37.96% |
| claude-sonnet-5 / MMLU-Pro | completed | 110 | 2 | 1.79% |

## 剩余 units

1. `gpt-5.6-terra / LiveBench`（运行中）
2. `claude-fable-5 / MMLU-Pro`
3. `gpt-5.6-sol / LiveBench`
4. `claude-opus-5 / MMLU-Pro`

## 稳定性观察

- LiveBench 目前 5/5 已终态 unit 全部 failed；MMLU-Pro 2/3 通过或接近
  门禁。LiveBench 是当前 90 秒 ceiling 下最主要的失败源。
- `gpt-5.6-luna / MMLU-Pro` 除 timeout 外还记录到 4 次上游 HTTP 503。
- 未修改冻结 plan 的 retry policy；首轮结束后用 `--retry-failed` 统一
  处理失败 case，再决定是否需要 transport admission 方案。

## 下一轮

- 继续 15 分钟低频探针等待 12 units 首轮终态。
- 完成后执行 `baseline-screening-run --retry-failed`，复用同一 state。
- 对通过门禁的 unit 做 ranking conversion；失败 unit 保持 fail-closed，
  不用 alias-only 或 research prior 替代。
