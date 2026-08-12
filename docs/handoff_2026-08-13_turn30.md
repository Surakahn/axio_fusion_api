# Axio Fusion API — Handoff 2026-08-13 (Turn 30)

## 本轮结论

- 用户再次明确的模型层级事实已核对并确认已固化在
  `src/axio_fusion_api/registry.py`：
  - `claude-fable-5` 与 `gpt-5.6-sol` 同属最高档；
  - `claude-opus-5` 略强于 `gpt-5.6-terra`；
  - `claude-sonnet-5` 强于 `gpt-5.6-luna`。
- 能力分自检结果：
  - `claude-fable-5 avg=0.7727`，`gpt-5.6-sol avg=0.7873`；
  - `claude-opus-5 avg=0.7773 > gpt-5.6-terra avg=0.7718`；
  - `claude-sonnet-5 avg=0.7664 > gpt-5.6-luna avg=0.7564`。
- 服务 `GET /health` 为 `ready`，28 models / 3 providers / 3 public models，
  图片模块仍为独立 `gpt-image-2` generation/editing lane。

## 未改代码的原因

该事实在上一轮已经写入 registry 能力先验和
`docs/provider_api_format_spec.md`，本轮只做一致性核验，不需要重复改代码，
避免引入无效 diff。

## 下一轮

- 仍以正式 provider baseline freeze 为首要 blocker，不伪造 alias-only 排名。
- 继续准备 21-suite 官方 harness 的 provider freeze manifest 与统计门禁。
- 若继续修改路由或评测，按 L1→L4 门禁验证并提交。
