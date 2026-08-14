# Axio Fusion API — Handoff 2026-08-14 (Turn 36)

## 本轮结论

- 旧 `2026-08-13-core-cohort` 三轮 retry 后仍为 9/12 completed、3 failed，
  因此不能进入 ranking conversion。
- 根因不是 provider 整体不可用，而是 LiveBench 108 题中包含
  `plot_unscrambling` 图像题和 `zebra_puzzle`/`spatial`/`tablejoin`
  在 90 秒文本通路上的高延迟/空输出题。
- 不修改旧冻结 plan，改为新建预注册文本兼容 LiveBench 切片 cohort。

## 新 cohort

- 目录：`private/runs/2026-08-14-core-cohort-text-compatible/`
- LiveBench 官方 source family 保留，任务切片为：
  `web_of_lies_v2`, `cta`, `tablereformat`, `connections`, `typos`
- 100 题 = 5 tasks × 20 cases；MMLU-Pro 仍 112 题。
- 新 plan：12 tasks、1272 预估 calls、`ready=true`、90 秒 cap 生效。
- live 首轮运行中，首个 MMLU-Pro checkpoint 55/112。

## 下一轮

- 继续 20 分钟低频探针等待 12 units 首轮终态。
- 若仍有超门禁 unit，仅执行 `--retry-failed`，不修改 plan。
- 全部通过后执行 `baseline-screening-to-ranking`。
- 旧 partial cohort 仅作诊断证据，不混入最终 ranking。
