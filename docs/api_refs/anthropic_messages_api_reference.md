# Anthropic Messages API 完整参考

## 端点

```
POST /v1/messages
```

## 认证

```
x-api-key: sk-...
anthropic-version: 2023-06-01
```

## 请求参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | 模型 ID (claude-sonnet-5, claude-opus-5 等) |
| `messages` | array | ✅ | 消息列表，每个消息有 `role` (user/assistant) 和 `content` (string 或 content block 数组) |
| `max_tokens` | int | ✅ | 最大生成 token 数 |
| `system` | string/array | ❌ | 系统提示词 (顶层参数，非 messages 中的 role) |
| `temperature` | float | ❌ | 0.0-1.0，默认 1.0 |
| `stop_sequences` | array | ❌ | 停止序列 |
| `stream` | bool | ❌ | 是否流式，默认 false |
| `thinking` | object | ❌ | 扩展思考配置 |
| `tools` | array | ❌ | 工具定义列表 |
| `tool_choice` | object | ❌ | 工具选择策略 |
| `top_p` | float | ❌ | nucleus sampling |
| `top_k` | int | ❌ | top-k sampling |

## Thinking 配置 (Claude 推理强度)

```json
// 启用扩展思考
{
  "thinking": {
    "type": "enabled",
    "budget_tokens": 4096
  }
}

// 禁用扩展思考
{
  "thinking": {
    "type": "disabled"
  }
}
```

- `budget_tokens`: ≥1024 且 < max_tokens
- 当 type 为 "enabled" 时，Claude 会在响应中包含 thinking content blocks

## Content Block 类型

### 请求 (输入)
| type | 说明 |
|------|------|
| `text` | 文本内容 |
| `image` | 图片 (base64, 支持 jpeg/png/gif/webp) |
| `document` | 文档 (PDF) |
| `tool_result` | 工具调用结果 |
| `tool_use` | (仅 assistant role) |

### 响应 (输出)
| type | 说明 |
|------|------|
| `text` | 文本输出 |
| `thinking` | 思考过程 |
| `tool_use` | 工具调用请求 |
| `redacted_thinking` | 被编辑的思考过程 |

## 流式响应 (SSE)

```
event: message_start
event: ping
event: content_block_start
event: content_block_delta
event: content_block_stop
event: message_delta
event: message_stop
```

每个事件都是 `data: {JSON}\n\n` 格式。

## tokenapis 适配

tokenapis.com 上的 Claude 模型**必须**使用原生 `/v1/messages` 端点：
- 认证头：`x-api-key` (非 `Authorization: Bearer`)
- 不需要 `anthropic-beta` 头 (tokenapis 自动处理)
- 不需要 `anthropic-dangerous-direct-browser-access` 头
- `anthropic-version: 2023-06-01` 需要

## 推理强度映射 (Claude → Axio)

| Axio reasoning_effort | Claude thinking budget_tokens |
|-----------------------|------------------------------|
| low | 1024 |
| medium | 4096 |
| high | 8192 |
| xhigh | 16384 |
| max | 32768 |

注意：Claude 的 thinking 是递增式的 (budget_tokens 越多推理越深)，与 GPT 的 reasoning_effort 档位概念不同。

## 视觉输入

Claude 通过 content block 中的 `image` 类型支持图片输入：
```json
{
  "role": "user",
  "content": [
    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}},
    {"type": "text", "text": "Describe this image"}
  ]
}
```

视觉输入不是独立能力层，而是内置于 text+image content blocks 中。

## Python SDK 官方参数验证 (anthropic 0.72.0)

通过 `inspect.signature(anthropic.resources.messages.Messages.create)` 验证。

### 必需参数
| 参数 | 类型 | SDK默认 |
|------|------|--------|
| `model` | str | (必需) |
| `messages` | list | (必需) |
| `max_tokens` | int | (必需) |

### 可选参数
| 参数 | 类型 | SDK默认 | 说明 |
|------|------|--------|------|
| `system` | str/array | Omit | 系统提示词 |
| `temperature` | float | Omit | 0.0-1.0 |
| `thinking` | object | Omit | 推理思考配置 |
| `tools` | list | Omit | 工具定义 |
| `tool_choice` | object | Omit | 工具选择策略 |
| `stop_sequences` | list | Omit | 停止序列 |
| `top_p` | float | Omit | nucleus sampling |
| `top_k` | int | Omit | top-k sampling |
| `metadata` | object | Omit | 用户元数据 |
| `service_tier` | str | Omit | 服务等级 |
| `stream` | bool | Omit | 流式开关 |

### Axio Fusion 覆盖状态
| SDK参数 | 覆盖 | 位置 |
|---------|------|------|
| model | ✅ | `_anthropic_payload` |
| messages | ✅ | `_anthropic_history_messages` |
| max_tokens | ✅ | `request.max_output_tokens` |
| system | ✅ | 直接映射 |
| temperature | ✅ | `request.temperature` |
| thinking | ✅ | `reasoning_effort→budget_tokens`映射 |
| tools | ✅ | `provider_tool_declarations(api_format="anthropic")` |
| stop_sequences | ✅ | `request.stop` |
| top_p | ✅ | `request.top_p` |
| top_k | ✅ (2026-08-12) | `request.top_k` |
| metadata | ⬜ 未使用 | 可选，非关键 |
| tool_choice | ⬜ 未显式设置 | 由provider默认处理 |
| service_tier | ⬜ 未使用 | 可选，非关键 |

## 推理强度映射详解 (Claude thinking → Axio reasoning_effort)

Claude的thinking机制不同于GPT的reasoning_effort档位概念。Claude通过
`thinking.budget_tokens` 控制推理深度，budget越大推理越深。

| Axio reasoning_effort | Claude budget_tokens | 说明 |
|-----------------------|---------------------|------|
| `low` | 1024 | 最小推理 |
| `medium` | 4096 | 中等推理 |
| `high` | 8192 | 深度推理 |
| `xhigh` | 16384 | 非常深度 |
| `max` | 32768 | 最大推理 |

### Thinking 响应处理
当thinking启用时，Claude响应中会包含 `thinking` content blocks
（在text之前）。adapter在流式处理中正确跳过thinking块，只提取text。

```json
// 请求
{"thinking": {"type": "enabled", "budget_tokens": 4096}}

// 响应 (content blocks)
[
  {"type": "thinking", "thinking": "...", "signature": "..."},
  {"type": "text", "text": "..."}
]
```

### 视觉输入 (Vision)
Claude通过content block支持图片输入，不是独立能力层：

```json
{
  "role": "user",
  "content": [
    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}},
    {"type": "text", "text": "描述这张图片"}
  ]
}
```

## tokenapis.com 特定适配

- 认证: `x-api-key` 头
- 版本头: `anthropic-version: 2023-06-01`
- 不需要 `anthropic-beta` 头
- 不需要 `anthropic-dangerous-direct-browser-access` 头
- 端点: `/v1/messages`

## 最新验证 (2026-08-12)

### Claude快速基准 (4 MCQ题)

| 模型 | 得分 | 平均延迟 |
|------|------|---------|
| claude-opus-5 | 4/4 (100%) | 4.3s |
| claude-sonnet-5 | 4/4 (100%) | 4.8s |
| claude-haiku-4-5 | 4/4 (100%) | 4.9s |

延迟极低，通过代理访问tokenapis渠道稳定。
