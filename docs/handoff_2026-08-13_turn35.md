# Axio Fusion API — Handoff 2026-08-13 (Turn 35)

## 本轮结论

- 六模型核心 screening 首轮进度 10/12 终态：3 completed，7 failed。
- PID `2498355` 仍稳定运行，冻结 plan 未修改，90 秒硬上限和 2% 运输
  失败门禁均未放宽。
- 当前运行 `gpt-5.6-sol / LiveBench`，checkpoint 48/108、0 失败。
- `claude-opus-5 / MMLU-Pro` 仍在排队。

## 模型能力层级事实

- `claude-fable-5` 与 `gpt-5.6-sol` 同级别。
- `claude-opus-5` 略强于 `gpt-5.6-terra`。
- `claude-sonnet-5` 强于 `gpt-5.6-luna`。
- 该约束已由 `tests/test_formal_core_model_prior.py` 固化。

## 已终态 units

| unit | status | scored | timeout | rate |
|---|---|---|---|---|
| claude-fable-5 / MMLU-Pro | completed | 112 | 0 | 0.00% |
| claude-sonnet-5 / MMLU-Pro | completed | 110 | 2 | 1.79% |
| gpt-5.6-sol / MMLU-Pro | completed | 112 | 0 | 0.00% |
| claude-opus-5 / LiveBench | failed | 97 | 11 | 10.19% |
| claude-fable-5 / LiveBench | failed | 104 | 4 | 3.70% |
| claude-sonnet-5 / LiveBench | failed | 79 | 29 | 26.85% |
| gpt-5.6-terra / MMLU-Pro | failed | 101 | 11 | 9.82% |
| gpt-5.6-luna / MMLU-Pro | failed | 101 | 11 | 9.82% |
| gpt-5.6-terra / LiveBench | failed | 105 | 3 | 2.78% |
| gpt-5.6-luna / LiveBench | failed | 67 | 41 | 37.96% |

## 下一轮

- 继续 15 分钟低频探针，等待剩余 2 个 unit 首轮终态。
- 首轮结束后复用同一 state 执行 `--retry-failed`，只重试 transport failed
  case，不修改已完成 score。
- retry 后重点复核 `gpt-5.6-terra / LiveBench` 和
  `claude-fable-5 / LiveBench` 能否进入 2% 门禁。
- 不生成 ranking，不做 superiority claim，直到 terminal campaign 完成。
