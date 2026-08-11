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
