# Axio Fusion API — Handoff 2026-08-13 (Turn 32)

## 本轮结论

- 六模型能力层级已用独立回归测试固化并推送：
  `claude-fable-5 ≈ gpt-5.6-sol`、`claude-opus-5 > gpt-5.6-terra`、
  `claude-sonnet-5 > gpt-5.6-luna`。
- 正式核心 screening 继续后台运行，PID `2498355`，没有 5xx 或流式协议
  异常，当前失败模式仍是 90 秒 provider timeout。
- 未放松 90 秒硬门禁和 2% transport-failure 门禁。

## 已完成的本地收口

- 新测试 `tests/test_formal_core_model_prior.py` 通过：`1 passed`。
- 提交并推送到 `github.com:Surakahn/axio_fusion_api`：
  `16c8fd9 test: 固化六模型正式能力层级先验回归测试`。
- 已确认 `--retry-failed` 只重试 transport failed case，已完成答案不会
  重新采样，失败仍按完整预期 case 数计入门禁。

## screening 当前状态（2026-08-13 16:05）

| unit | status | scored | mean | timeout | rate |
|---|---|---|---|---|---|
| claude-opus-5 / LiveBench | failed | 97 | 0.8095 | 11 | 10.19% |
| gpt-5.6-sol / MMLU-Pro | completed | 112 | 0.8750 | 0 | 0.00% |
| claude-fable-5 / LiveBench | failed | 104 | 0.8833 | 4 | 3.70% |
| gpt-5.6-terra / MMLU-Pro | failed | 101 | 0.8416 | 11 | 9.82% |
| claude-sonnet-5 / LiveBench | running | 60/108 | - | 16 | - |

- checkpoint 目录：
  `private/runs/2026-08-13-core-cohort/16483559903cac2b/`
- 下一次低频探针窗口：16:20；只检查进程、state 和 checkpoint，不主动
  发起 provider 请求。

## 下一轮

- 等待全部 12 units 首轮终态，不主动中断当前串行任务。
- 首轮 terminal 后运行 `baseline-screening-run --retry-failed`，复用同一
  state 文件，仅重试失败 case。
- 若最终仍有超过 2% 门禁的 unit，不将其计入正式 ranking；不要用
  alias-only 或 research prior 替代真实 screening 证据。
- 通过门禁后再执行 `baseline-screening-to-ranking` 和
  `benchmark-provider-baseline-freeze`，然后才能开始 21-suite target
  campaign。
