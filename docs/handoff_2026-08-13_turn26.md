# Axio Fusion API — Handoff 2026-08-13 (Turn 26)

## 本轮结论

- 确认并持久化 Claude/GPT 能力分层：
  - `claude-fable-5 ≈ gpt-5.6-sol`
  - `claude-opus-5 > gpt-5.6-terra`
  - `claude-sonnet-5 > gpt-5.6-luna`
- 修复当前私有运行时注册表的 Claude canonical identity 折叠问题。
- 重新核对 TokenAPIs Anthropic 渠道模型，移除 4 个实际不支持的别名。

## 修复内容

1. 当前 `2026-08-13-protocol-corrected-merge` 注册表中，从
   `claude-sonnet-5` 开始的多条 profile 被错误写成
   `canonical_model_id = claude-opus-4-5-20251101`。这会让多个不同 Claude
   模型共享同一个运行时 canonical identity，破坏逻辑模型去重与角色选择。
   本轮将错误的 canonical id 恢复为各自真实 `model` 值，共 10 条。

2. 通过 TokenAPIs `/v1/models` 和 `/v1/messages` 实测：
   - 当前渠道实际支持 12 个 Claude 模型；
   - `claude-opus-4-1-20250805`、`claude-opus-4-20250514`、
     `claude-haiku-4-5`、`claude-sonnet-4-20250514` 返回
     `model_not_found`，已从当前运行时注册表移除。

## 当前运行时状态

- 服务：`python3.11 scripts/run_server_noprefusion.py`，监听
  `127.0.0.1:18900`
- 私有注册表：`private/runs/2026-08-13-protocol-corrected-merge/merged_registry.private.json`
- `/health`：`ready`，文本 profile 总数从 32 收敛到 28
- API 格式计数：`anthropic=10`、`chat/completions=6`、`responses=12`
- 私有 env `AXIO_ANTHROPIC_MODELS` 已更新为 12 个实际支持模型

## 验证

- dry-run route plan：
  - `axio-fast -> claude-sonnet-5`（Luna 带）
  - `axio-terra -> claude-opus-5 + gpt-5.6-luna`
  - `axio-pro -> claude-opus-5/claude-fable-5 + gpt-5.6-sol/terra`
- `axio-fast` live `/v1/chat/completions` 请求返回 `OK`，6.4 秒完成。

## 下一轮

- 继续推进 Claude `anthropic_thinking` endpoint-bound budget probe。
- 为 12 个 TokenAPIs 支持模型补全 pre-Fusion 严格流式与 reasoning 证据。
- 推进九类二十一套基准的基线冻结与独立对照。
