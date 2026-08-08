# Provider API Format Specification

## Current Provider Channels

### 1. CPA Plus (多格式渠道)
- **Base URL**: `https://cpa.co6.click/v1` (or `http://10.195.91.64:8317/v1`)
- **API Key**: `<REDACTED>`
- **API Formats by Model**:
  - `v1/responses` → gpt-* models, Chinese models (deepseek, glm, kimi, minimax, stepfun, etc.)
  - `v1/chat/completions` → some models
  - `v1/messages` → claude-* models (Anthropic format)
- **Key Point**: Single base URL, THREE different API formats. Per-model format MUST be resolved.

### 2. NVIDIA NIM
- **Base URL**: `https://integrate.api.nvidia.com/v1`
- **API Keys**: 5 keys (<REDACTED>)
- **API Format**: `v1/chat/completions` only

## Reasoning Effort Specification

### Five Standard Levels
| Level | Description |
|-------|-------------|
| `low` | Minimal reasoning |
| `medium` | Moderate reasoning |
| `high` | Strong reasoning |
| `xhigh` | Very strong reasoning |
| `max` | Maximum reasoning (gpt-5.6-* only) |

### Per-Format Wire Fields
| API Format | Wire Field | Notes |
|------------|-----------|-------|
| Chat Completions | `reasoning_effort` (top-level) | Some models only support subset of levels |
| Responses | `reasoning.effort` (nested) | gpt-5.6-* supports all 5 levels |
| Anthropic Messages | `thinking` object with `budget_tokens` | Different mechanism |
| Gemini | `thinkingConfig` in `generationConfig` | Different mechanism |

### Cross-Model Mapping Rules
When a model doesn't support a specific reasoning level:
- `xhigh` → map to `max` if max is supported, else `high`
- `high` → map to `medium` if only low/medium supported
- `max` → map to `xhigh` if max not supported
- Always prefer mapping to a HIGHER available level, not lower
- Unknown/unsupported models default to no reasoning parameter

## Reference Open-Source Projects
For API format adaptation, compatibility, and best practices:
- **cliproxyapi**: Multi-format API proxy
- **newapi**: Next-gen API gateway with multi-format support
- **sub2api**: Subscription to API conversion
- **ccx**: Cross-channel exchange
- **ccswitch**: Channel switch/router
- **OpenAI official docs**: https://platform.openai.com/docs/
- **Anthropic official docs**: https://docs.anthropic.com/

## Development Requirements
1. All code must be production-grade, not MVP/demo quality
2. Every function must have proper error handling
3. API format adaptation must follow official specs exactly
4. Reasoning effort mapping must be bidirectional and verified
5. Multi-format per-channel must work seamlessly
6. Refer to open-source projects before implementing novel solutions

## Current Channel Models (CPA Plus)
- gpt-5.6-sol (best, max reasoning) → Responses API
- gpt-5.6-terra (2nd best, max reasoning) → Responses API
- gpt-5.6-luna (3rd best, max reasoning) → Responses API
- gpt-5.5 → Responses API
- gpt-5.4 → Responses API
- deepseek-v4-flash → Responses API
- glm-5.2 → Responses API
- kimi-k2.6 → Responses API
- claude-* → Messages API (Anthropic format)
- Other Chinese models → Responses or Chat API

## Current Channel Models (NVIDIA NIM)
- openai/gpt-oss-120b → Chat Completions
- nvidia/nemotron-3-super-120b-a12b → Chat Completions
- deepseek-ai/deepseek-v4-flash → Chat Completions
- deepseek-ai/deepseek-v4-pro → Chat Completions
- minimaxai/minimax-m2.7 → Chat Completions
- mistralai/mistral-large-3-675b-instruct-2512 → Chat Completions
- stepfun-ai/step-3.5-flash → Chat Completions
- minimaxai/minimax-m3 → Chat Completions
- z-ai/glm-5.2 → Chat Completions
- stepfun-ai/step-3.7-flash → Chat Completions
- openai/gpt-oss-20b → Chat Completions

## CPA Plus Model Inventory (2026-08-09)

### Models by API Format (from `/models` owned_by field)

**Responses API (owned_by=openai)**:
gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, gpt-5.5, gpt-5.4,
deepseek-v4-flash, glm-5.2, kimi-k2.5, kimi-k2.6, kimi-k2.7-code,
minimax-m2.5, minimax-m2.7, mimo-v2.5-pro, qwen3.8-max,
gpt-5.4-openai-compact, gpt-5.5-openai-compact,
gpt-5.6-luna-openai-compact, gpt-5.6-sol-openai-compact,
gpt-5.6-terra-openai-compact

**Messages API (owned_by=anthropic)**:
claude-fable-5, claude-haiku-4-5-20251001, claude-opus-4-8,
claude-opus-5, claude-sonnet-4-6, claude-sonnet-5

**Auxiliary/Non-text (exclude from Fusion)**:
codex-auto-review (internal tool), gpt-image-2 (image generation)

### Format Resolution Rule
The `/models` endpoint returns `owned_by` field:
- `owned_by=openai` → `responses` API format
- `owned_by=anthropic` → `anthropic` API format
- Unknown → channel default format

## Image Generation & Editing Module Requirements

### Overview
独立图片生成与编辑模块。当用户请求中包含图片生成或编辑意图时，Fusion系统
单独路由到图片模型（gpt-image-2），不经过文本Fusion管道。

### Core Workflow
1. **意图理解**: 接收用户原始prompt（可能是模糊/不精确的描述）
2. **Prompt转换**: 使用LLM将模糊意图转化为适合图片模型的精确prompt
3. **模型调用**: 调用gpt-image-2的Images API进行生成/编辑
4. **结果返回**: 返回生成的图片（base64或URL）

### Key Design Points
- 图片模块完全独立于文本Fusion管道
- 有图片模型时自动启用，无图片模型时返回明确提示
- Prompt转换器使用可用LLM（不消耗图片模型token预算）
- 支持流式输出（如适用）

### API Endpoints
- `POST /v1/images/generations` — 文生图
- `POST /v1/images/edits` — 图片编辑（上传+修改）
