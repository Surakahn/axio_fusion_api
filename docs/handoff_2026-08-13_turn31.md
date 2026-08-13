# Axio Fusion API — Handoff 2026-08-13 (Turn 31)

## 本轮结论

- 再次核对用户给定的模型层级事实并保持不写反：
  - `claude-fable-5 ≈ gpt-5.6-sol`
  - `claude-opus-5 > gpt-5.6-terra`
  - `claude-sonnet-5 > gpt-5.6-luna`
- 路由先验已固化在 `registry.py`，协议说明已固化在
  `docs/provider_api_format_spec.md`；正式六模型候选配置已入库。
- 修复普通 JSON provider 响应缺少 deadline watchdog 的阻塞风险，并提交远程
  `github.com:Surakahn/axio_fusion_api`。

## 正式六模型核心 cohort

- 候选固定为 `claude-fable-5`、`claude-opus-5`、`claude-sonnet-5`、
  `gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-5.6-luna`。
- 六个物理 profile 均通过严格流式 3/3 证据和 90 秒门禁。
- 12 个非目标 screening units 已启动，完整首轮仍在后台运行。
- 当前 checkpoint 和 private artifacts 位于：
  `private/runs/2026-08-13-core-cohort/`，未提交到 Git。

## screening 当前状态

- `claude-opus-5 / LiveBench`：failed，mean 0.8095，97 scored，
  11 timeout，10.19%。
- `gpt-5.6-sol / MMLU-Pro`：completed，mean 0.875，112/112。
- `claude-fable-5 / LiveBench`：failed，mean 0.8833，104 scored，
  4 timeout，3.70%。
- 当前运行：`gpt-5.6-terra / MMLU-Pro`。
- 失败均为 90 秒 timeout；unit 按 2% 预注册门禁判定，不伪造可用性。

## 下一轮

- 继续 15 分钟低频探针，不主动停止首轮 campaign。
- 首轮 12 units 全部终态后，使用 `--retry-failed` 仅重试失败 case。
- 对高 timeout profile 做延迟审计；不放松 90 秒硬门禁。
- terminal campaign 后依次执行 ranking conversion 和 baseline freeze。
- 在最终排名生成前，不把 remote research prior 或 alias-only 数据当作
  正式证据；用户给定层级仅作为路由先验。
