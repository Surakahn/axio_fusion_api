# Axio Fusion API — Handoff 2026-08-13 (Turn 25)

## 本轮结论

- 校正当前运行时注册表的多协议绑定，修复 CPA GPT 模型被错误绑定为
  Chat Completions、并丢失已验证 Responses reasoning 能力的问题。
- 当前服务已重启并加载校正后的 32 模型注册表。

## 运行时注册表校正

原 `2026-08-11-triple-merge` 注册表把 `gpt-5.4/5.5/5.6-*` 绑定成 `chat`，
且 reasoning 全部为 `unknown`；这与 CPA Plus 的 `owned_by=openai -> responses`
规则和已完成的 endpoint-bound reasoning probe 不一致。

本轮从现有私有证据重建：

- CPA 文本模型统一采用 `responses`
- `gpt-5.6-sol/terra/luna` 恢复 verified `responses_reasoning`，五档为
  `low/medium/high/xhigh/max`
- `gpt-5.5` 恢复 verified `responses_reasoning`，四档为
  `low/medium/high/xhigh`
- NVIDIA 保持 `chat`
- Claude 保持 `anthropic`；已有 candidate `anthropic_thinking` 的
  `claude-opus-5`、`claude-sonnet-5`、`claude-haiku-4-5-20251001` 保留
  candidate 状态，不做未经验证的 budget 提升

新私有注册表：

`private/runs/2026-08-13-protocol-corrected-merge/merged_registry.private.json`

`private/current_channels.env` 的 `AXIO_FUSION_REGISTRY_PATH` 已原子切换到
该文件，旧 env 备份为：

`private/current_channels.env.bak-20260813-protocol-corrected-merge`

## 服务验证

- 原 `run_server_noprefusion.py` 进程优雅停止
- 使用 `setsid` 重启，监听 `127.0.0.1:18900`
- `/health` 返回 `ready/ready/32`
- API 格式统计：`anthropic=14`、`chat/completions=6`、`responses=12`
- `/route-plan` dry-run 验证：
  - `axio-pro` 策略 `pro_panel_judge_escalation`
  - Judge/Synthesizer 选择 verified Responses GPT profile
  - `axio-terra` 使用 `claude-opus-5 + gpt-5.6-luna`

## 下一轮

- 对 Claude `anthropic_thinking` candidate profile 补充 endpoint-bound
  budget probe，使 `axio-fast/terra` 的 Claude direct route 能安全携带
  经证实的 thinking budget；未验证前继续保持 omit。
- 继续推进九类二十一套标准评测的基线冻结与独立对照。

