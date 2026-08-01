# Four-Protocol Parameter Reference

This is Axio's local implementation reference, refreshed on 2026-08-01 from
the official protocol pages and the public SDK/schema sources listed in
[`source_manifest.md`](source_manifest.md). It is a decision table, not a
promise that every vendor-specific option is transparently relayed.

## Three Separate Questions

Every field is evaluated at three boundaries:

1. **Parse**: can the public adapter read the native field without losing the
   meaning of the request?
2. **Canonicalize**: can it be represented in the closed `FusionRequest`
   contract without carrying an arbitrary vendor object through Fusion?
3. **Forward**: has the selected physical provider/model passed an
   endpoint-bound probe for the target wire field and stream shape?

Parsing a field is not permission to forward it. The public adapter rejects
ambiguous content and structured-output declarations before provider dispatch;
optional provider controls are omitted unless the profile is explicitly
verified. Raw caller fields are never copied into an upstream JSON body.

## Endpoint And Authentication Matrix

| Public format | Route | Auth header | Streaming transport | Terminal semantics |
| --- | --- | --- | --- | --- |
| OpenAI Chat Completions | `POST /v1/chat/completions` | `Authorization: Bearer` | SSE `data:` JSON chunks | `data: [DONE]` |
| OpenAI Responses | `POST /v1/responses` | `Authorization: Bearer` | named SSE events with JSON data | `response.completed` or failure event |
| Anthropic Messages | `POST /v1/messages` | `x-api-key` and `anthropic-version` | named SSE events with JSON data | `message_stop` or typed error |
| Gemini GenerateContent | `POST /v1beta/models/{model}:generateContent` | `x-goog-api-key` or provider-configured query key | JSON | HTTP response |
| Gemini StreamGenerateContent | `POST /v1beta/models/{model}:streamGenerateContent?alt=sse` | same as unary | SSE JSON objects | final candidate/usage object |

The public Axio key is unrelated to the upstream key. A provider profile owns
its base URL, authentication scheme, model alias, and key pool. A profile may
use `bearer`, `x-api-key`, `x-goog-api-key`, `query`, or `none`; the selected
scheme is recorded as a safe enum and the secret is never persisted.

## OpenAI Chat Completions

### Request fields

| Field | Public status | Canonical mapping | Forwarding rule |
| --- | --- | --- | --- |
| `model` | required | public model identity | provider model is selected from the registry |
| `messages` | required | typed history/content parts | text/image common subset only |
| `stream` | supported | stream route selection | Axio always uses a strict upstream stream internally |
| `stream_options.include_usage` | supported | public stream rendering | usage trailer is emitted only on Chat output |
| `max_completion_tokens` | parsed | `max_output_tokens` | provider profile decides `max_tokens` vs `max_completion_tokens`; no blind aliasing |
| `max_tokens` | compatibility alias | `max_output_tokens` | accepted for compatible gateways; deprecated-model behavior is probe-bound |
| `temperature`, `top_p`, `stop` | supported | canonical sampling fields | forwarded only in the closed native shape |
| `tools`, `tool_choice` | supported common function subset | canonical tools | native tool capability must be proven |
| `response_format` | supported JSON/text subset | canonical structured output | mapped to the target's native wrapper |
| `reasoning_effort` | model-specific | canonical logical effort | sent only as verified top-level `reasoning_effort` |
| `frequency_penalty`, `presence_penalty`, `logit_bias`, `logprobs`, `n`, audio, prediction, vendor extensions | not in closed contract | none | reject or omit by route policy; never pass through |

The modern OpenAI schema distinguishes `max_completion_tokens` from the older
`max_tokens`. A channel may continue to require the older spelling. That is a
provider profile fact, not something inferred from the public model name.

### Stream shape

The adapter accepts only JSON SSE chunks and extracts visible
`choices[].delta.content`. It separately assembles
`choices[].delta.tool_calls[].function.arguments`, ignores
`reasoning_content`/thought fields in the public text projection, and treats
`finish_reason` and the optional usage trailer as control data. `[DONE]` is a
Chat-only sentinel.

## OpenAI Responses

### Request fields

| Field | Public status | Canonical mapping | Forwarding rule |
| --- | --- | --- | --- |
| `model` | required | public model identity | provider registry selection |
| `input` string or typed items | supported common subset | history/content parts | typed input is preferred |
| `instructions` | supported string or text-only instruction items | system instruction | remains separate from user content; image/file items are rejected |
| `stream` | supported | strict stream route | named event parser required |
| `max_output_tokens`, `temperature`, `top_p` | supported | canonical fields | native Responses names |
| `text.format` | supported JSON/text subset | structured output | never replaced with Chat `response_format` |
| function `tools`, `tool_choice`, `parallel_tool_calls` | supported common function subset | canonical tools | tool capability must be proven |
| `reasoning.effort` | model-specific | canonical logical effort | nested field only for verified Responses transport |
| `previous_response_id` | supported by Axio control plane | continuation history | process-local, tenant-scoped, non-durable by default |
| `store`, `metadata` | bounded public behavior | continuation/receipt controls | Axio does not claim upstream storage semantics |
| built-in tools, computer use, hosted MCP, background mode, encrypted reasoning items | outside closed contract | none | require a dedicated adapter and probe |

Responses `instructions` may be a string or an array of instruction messages,
but Axio's common system lane is text-only. Typed image/file instruction parts
are rejected before provider dispatch instead of being stringified. Responses
output is a typed item list. Text is read from message content
blocks of type `output_text`; function calls are output items with
`type=function_call` and JSON-string `arguments`; results return as
`function_call_output` input items with the same `call_id`.

### Stream shape

Axio emits the stable sequence
`response.created`, `response.in_progress`, output item/content part events,
text or function-argument deltas, corresponding done events, and
`response.completed`. It assigns monotonic sequence numbers to public
Responses events. A provider's raw event stream is never forwarded.

## Anthropic Messages

### Request fields

| Field | Public status | Canonical mapping | Forwarding rule |
| --- | --- | --- | --- |
| `model`, `messages`, `max_tokens` | required | model, history, max output | `max_tokens` remains native Anthropic |
| `system` | supported text subset | system instruction | system is top-level; no fake `system` message |
| `stream` | supported | strict stream route | named SSE parser required |
| `temperature`, `top_p`, `stop_sequences` | supported | canonical fields | native names |
| `tools`, `tool_choice` | supported common function subset | canonical tools | `input_schema` mapping and tool probe |
| `thinking` | parsed as a reasoning budget | canonical reasoning budget | upstream forwarding requires verified model-local budget transport |
| `output_config.format` | supported JSON-schema subset | structured output | only when the provider profile is admitted |
| `top_k`, cache control, container, service tier, metadata | parsed only where semantics are safe | no arbitrary pass-through | dedicated capability required before forwarding |

Anthropic extended thinking is not an effort enum. Its budget must be a
positive integer, and the native enabled form is for example:

```json
{"thinking": {"type": "enabled", "budget_tokens": 2048}}
```

The budget counts toward the request's `max_tokens` limit and model-specific
minimums apply. Axio therefore never turns `low`/`medium`/`high` into an
Anthropic budget by guesswork. A future/optional profile may declare a closed
`anthropic_thinking` transport with exact budget levels and pass a strict
streaming probe; otherwise the field remains a parsed request hint and no
unverified upstream field is emitted.

### Stream shape

The native event order is `message_start`, one or more
`content_block_start`/`content_block_delta`/`content_block_stop` groups,
`message_delta`, and `message_stop`. `text_delta` is visible text;
`input_json_delta` is tool arguments. Thinking blocks are private and are not
included in Axio's public text stream.

## Gemini GenerateContent

### Request fields

| Field | Public status | Canonical mapping | Forwarding rule |
| --- | --- | --- | --- |
| URL model path | required | public model to selected provider model | route is constructed, never copied from caller URL |
| `systemInstruction` | supported text subset | system instruction | separate typed content |
| `contents` | supported common turns | user/model history | assistant becomes `role=model` |
| `generationConfig.temperature`, `topP`, `maxOutputTokens`, `stopSequences` | supported | canonical sampling fields | native camelCase wrapper |
| `tools.functionDeclarations` | supported common function subset | canonical tools | native tool capability must be proven |
| `toolConfig.functionCallingConfig` | bounded common choice | tool choice | named modes require capability proof |
| `responseMimeType`, `responseSchema` | supported JSON/text subset | structured output | mapped from the closed output contract |
| `thinkingConfig.thinkingBudget` | parsed as a positive integer reasoning budget | canonical reasoning budget | exact model-local range and strict stream probe required |
| `responseJsonSchema`, safety settings, cached content, audio, grounding, code execution | outside closed contract | none | dedicated adapter/probe required |

The current Gemini REST schema includes a model-specific thinking budget and
`usageMetadata.thoughtsTokenCount`. It does not use OpenAI's
`reasoning_effort` field. A verified `gemini_thinking_config` profile may
forward a closed object such as:

```json
{"generationConfig": {"thinkingConfig": {"thinkingBudget": 2048}}}
```

Absent that profile evidence, Axio omits thinking controls rather than
pretending the gateway accepted them.

### Stream shape

The `streamGenerateContent?alt=sse` route returns SSE frames whose data are
ordinary Gemini response objects. A frame may contain only part of a
candidate. Axio concatenates text parts and assembles function-call arguments
by turn/index; it does not treat one JSON object as a semantic completion.

## Cross-Protocol Conversion Rules

| Canonical value | Chat | Responses | Anthropic | Gemini |
| --- | --- | --- | --- | --- |
| system/developer instruction | system/developer message (developer is normalized to the common system lane) | `instructions` text | top-level `system` | `systemInstruction.parts` |
| user text | message content | `input_text` | text block | text part |
| image URL/data | `image_url` | `input_image` | image source | `fileData`/`inlineData` |
| max output | `max_tokens` or profile alias | `max_output_tokens` | `max_tokens` | `generationConfig.maxOutputTokens` |
| tools | nested `function` | top-level function tool | `input_schema` | `functionDeclarations` |
| JSON schema | `response_format` | `text.format` | `output_config.format` | `responseMimeType` + schema |
| reasoning | top-level `reasoning_effort` | `reasoning.effort` | `thinking.budget_tokens` | `thinkingConfig.thinkingBudget` |

The conversion is deliberately not a universal superset. An unsupported file,
tool mode, server-side tool, reasoning shape, or modality is rejected before
provider dispatch when flattening it would change the user's meaning.

## Error, Retry, And Timeout Rules

- A 2xx status without a valid framed stream or usable text/tool output is not
  a successful provider turn.
- All provider stream reads are bounded by the 90-second ceiling and the
  enclosing Fusion deadline.
- Retries/failover occur only before public text commitment. After a visible
  delta, Axio emits one safe terminal error and cannot silently replace the
  prefix with another model's answer.
- 401/403/408/429/5xx, timeouts, malformed frames, and parameter rejection
  have different evidence classes. A transient failure cannot be recorded as
  proof that a field is unsupported.
- Provider error bodies, prompts, outputs, thinking blocks, credentials, and
  endpoint values are excluded from durable safe receipts.

## Code And Test Anchors

- Public parsing/rendering: `src/axio_fusion_api/compat.py`
- Provider payloads, auth, retries, and stream parsers:
  `src/axio_fusion_api/providers.py`
- Profile-local capability gate: `src/axio_fusion_api/schemas.py`
- Tool conversion: `src/axio_fusion_api/tool_contract.py`
- Public HTTP routes and Responses continuation:
  `src/axio_fusion_api/server.py`
- Wire fixtures: `tests/test_provider_http_contracts.py`,
  `tests/test_true_incremental_streaming.py`, and
  `tests/test_content_contracts.py`
