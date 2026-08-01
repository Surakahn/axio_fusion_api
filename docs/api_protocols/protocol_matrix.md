# Protocol Matrix

This matrix is the compact contract used when adding or reviewing an adapter.
The public gateway first creates a protocol-neutral `FusionRequest`; provider
adapters then create a provider-native payload. The reverse path creates a
`FusionResponse` and renders it in the requested public format.

## Endpoints and Authentication

| Surface | Public route | Native authentication | Native stream framing |
| --- | --- | --- | --- |
| Chat Completions | `/v1/chat/completions` | `Authorization: Bearer <key>` | SSE data frames, terminal `data: [DONE]` |
| Responses | `/v1/responses` | `Authorization: Bearer <key>` | SSE named typed events, terminal response event |
| Anthropic Messages | `/v1/messages` | `x-api-key: <key>` and `anthropic-version` | SSE named typed events |
| Gemini | `/v1beta/models/{model}:generateContent` | `x-goog-api-key` or `?key=` | JSON for non-stream; SSE JSON objects for stream |

Provider manifests may use a custom base URL and path prefix. Axio joins paths
without duplicating `/v1`; Gemini model paths are handled separately because
the model identifier is part of the route.

## Current Adapter Status

| Capability | Chat | Responses | Anthropic | Gemini |
| --- | --- | --- | --- | --- |
| text turns | native | native typed or text input | native blocks | native parts |
| image URL | `image_url` | `input_image.image_url` | image URL source | HTTPS `fileData` |
| base64 image | data URL in `image_url` | data URL in `input_image.image_url` | base64 image source | `inlineData` |
| file reference | unsupported by the closed common contract | `input_file` with `file_id` or `file_url` | unsupported by the closed common contract | `fileData` with `fileUri` |
| JSON object/schema | `response_format` | `text.format` | `output_config.format` | `generationConfig` |

The content contract is deliberately smaller than the union of vendor fields:
`text`, `image`, and `file`, with only URL/base64/file-id/file-URI sources that
can be audited. System instructions are text-only. An image or file is never
flattened into a text marker for a provider payload. If the target protocol or
profile cannot express it, admission rejects the profile or the provider call
returns a bounded content-contract error.

## Canonical Request Mapping

| Canonical field | Chat | Responses | Anthropic | Gemini |
| --- | --- | --- | --- | --- |
| model | `model` | `model` | `model` | route model or `model` convenience field |
| system/developer instruction | system/developer message (developer is normalized to the common system lane) | `instructions` string or text-only instruction items | top-level `system` | `systemInstruction.parts` |
| conversation | `messages` | `input` string or typed items | `messages` | `contents` with `user`/`model` roles |
| current prompt | last user message | final user input item | final user message | final user content |
| max output | `max_tokens` or provider variant | `max_output_tokens` | required `max_tokens` | `generationConfig.maxOutputTokens` |
| temperature | top-level | top-level where supported | top-level | `generationConfig.temperature` |
| top p | `top_p` | `top_p` | `top_p` | `generationConfig.topP` |
| stop | `stop` | `stop` | `stop_sequences` | `generationConfig.stopSequences` |
| tools | `tools` with `function` | top-level function tools | `tools` with `input_schema` | `tools.functionDeclarations` |
| tool choice | `tool_choice` | `tool_choice` | `tool_choice` | `toolConfig.functionCallingConfig` |
| structured output | `response_format` | `text.format` | provider/model-specific | `responseMimeType` and `responseSchema` |
| streaming | `stream: true` | `stream: true` | `stream: true` | stream route, not only a body flag |

Only fields with a native row are forwarded. Axio does not pass arbitrary
unknown fields from a public request into a provider request.

## Canonical Response Mapping

| Canonical result | Chat | Responses | Anthropic | Gemini |
| --- | --- | --- | --- | --- |
| text | `choices[0].message.content` | output message content or `output_text` convenience | text content blocks | candidate content text parts |
| tool call | `message.tool_calls` | `output` item `function_call` | `content` block `tool_use` | `functionCall` part |
| finish | `finish_reason` | response `status` plus typed output | `stop_reason` | `finishReason` |
| usage input | `usage.prompt_tokens` | `usage.input_tokens` | `usage.input_tokens` | `usageMetadata.promptTokenCount` |
| usage output | `usage.completion_tokens` | `usage.output_tokens` | `usage.output_tokens` | `usageMetadata.candidatesTokenCount` |
| request id | `id` | `id` | `id` | `responseId` or provider header |

Responses output is a typed item list. It must never be parsed using the Chat
Completions `choices[0].message` path. Anthropic content is also a typed block
list, and Gemini content is a typed part list.

## Optional Capability Policy

| Capability | Default policy |
| --- | --- |
| tools | Forward only when the provider profile is tool-probe eligible. |
| reasoning control | Forward only through a verified, protocol-matched transport. |
| JSON/schema output | Preserve only when the target adapter has an audited mapping. |
| multimodal input | Preserve typed image/file parts where the adapter supports them; otherwise reject before provider dispatch. |
| response continuation | Responses `previous_response_id` is stored only in the Axio continuation control plane. |
| vendor extensions | Never forward from an untrusted public payload. Add a closed profile capability instead. |

The current reasoning transport registry is intentionally limited to verified
Chat and Responses transports. Anthropic `thinking` and Gemini
`thinkingConfig` are documented in their native protocol files but remain
candidate capabilities until a closed budget mapping and endpoint-bound probe
are implemented. A public `reasoning_effort` value must not silently become a
vendor-specific field.

## Error and Timeout Rules

- HTTP status, body shape, stream framing, and semantic output are separate
  checks.
- A 2xx response with no text and no tool call is not a successful provider
  turn.
- Provider calls are bounded by the 90-second ceiling and by the enclosing
  Fusion deadline.
- Retry is allowed only before public commitment and only for retryable
  transport or provider failures.
- Once public text has been emitted, a provider retry cannot silently replace
  the partial answer.
- Public error bodies are sanitized; provider credentials, raw prompts, raw
  provider output, and private Fusion traffic are never persisted or streamed.
- Invalid modality or structured-output declarations receive a public `400`
  before streaming headers are committed; no provider fallback is attempted.
