# Four-Protocol Integration Field Guide

This is the implementation-facing companion to the protocol reference files.
It answers one operational question: when a client speaks one of the four
public formats, what can Axio preserve, what must it translate, and what must
it reject before provider dispatch?

The examples use placeholders such as `${AXIO_KEY}` and `model-id`. They are
not credentials and must not be replaced with credentials in versioned
documentation.

## 1. Request Lifecycle

Every request follows the same bounded path:

1. Select the public route and parse its native envelope.
2. Validate content blocks, tools, structured output, continuation, and
   protocol-specific required fields.
3. Convert once into the protocol-neutral `FusionRequest`.
4. Select an admitted logical model and a healthy physical provider replica.
5. Render a provider-native request. Do not pass arbitrary caller fields
   through this boundary.
6. Parse provider events into visible text deltas and complete tool intents.
7. Keep candidate answers, private prompts, reasoning content, and internal
   role traffic inside the Fusion runtime.
8. Render the result in the caller's original protocol.

The public protocol is an edge concern. The orchestrator must not branch on
Chat JSON, Responses event names, Anthropic blocks, or Gemini parts after the
canonical request has been built.

## 2. Route and Authentication Matrix

| Public surface | Route | Request authentication | Streaming form | Terminal marker |
| --- | --- | --- | --- | --- |
| OpenAI Chat Completions | `POST /v1/chat/completions` | `Authorization: Bearer ${AXIO_KEY}` | SSE `data:` JSON chunks | `data: [DONE]` |
| OpenAI Responses | `POST /v1/responses` | `Authorization: Bearer ${AXIO_KEY}` | SSE named typed events | `response.completed` or `response.failed` |
| Anthropic Messages | `POST /v1/messages` | `x-api-key: ${AXIO_KEY}` and `anthropic-version` | SSE named typed events | `message_stop` or typed `error` |
| Gemini GenerateContent | `POST /v1beta/models/{model}:generateContent` | `x-goog-api-key: ${AXIO_KEY}` or the configured query form | JSON | HTTP response |
| Gemini stream GenerateContent | `POST /v1beta/models/{model}:streamGenerateContent?alt=sse` | same as non-stream | SSE JSON objects | final candidate/usage object |

The provider-side route and authentication may be different from the public
route. A profile owns the provider base URL, API format, path policy, and
credential reference. A logical model may have several physical profiles;
credentials are never copied into a public response or a persisted receipt.

## 3. Field Classification

Axio uses four labels when reviewing a field:

- **Native**: the target protocol has the same semantic field.
- **Structured conversion**: the meaning is preserved by an explicit native
  wrapper or shape conversion.
- **Lossy**: the common contract can be represented, but some provider detail
  or fidelity is deliberately discarded and must be visible in an internal
  receipt.
- **Unsupported**: the adapter cannot represent the request safely. Reject it
  before provider dispatch, unless the route explicitly defines a safe omit.

### 3.1 Common Request Fields

| Canonical field | Chat | Responses | Anthropic | Gemini |
| --- | --- | --- | --- | --- |
| `model` | Native body field | Native body field | Native body field | Structured into the URL path |
| system instruction | Structured system message | Native `instructions` | Native top-level `system` | Native `systemInstruction.parts` |
| conversation | Structured `messages` | Native typed `input` items | Native `messages` blocks | Structured `contents` parts |
| text content | Native string or content block | Native `input_text` | Native text block | Native text part |
| image URL/data URL | Structured `image_url` | Structured `input_image` | Structured image source | Structured `fileData` or `inlineData` |
| file URL/file id | Unsupported in closed Chat contract | Native `input_file` | Unsupported in closed contract | Structured `fileData` when URI semantics are valid |
| `max_output_tokens` | Provider policy may use `max_completion_tokens` or `max_tokens` | Native `max_output_tokens` | Structured into required `max_tokens` | Structured into `generationConfig.maxOutputTokens` |
| temperature | Native when admitted | Native when provider supports it | Native | Structured into `generationConfig.temperature` |
| top-p | Native `top_p` | Native `top_p` | Native `top_p` | Structured `generationConfig.topP` |
| stop sequences | Native `stop` | Native provider field when admitted | Structured `stop_sequences` | Structured `generationConfig.stopSequences` |
| tools | Structured nested function declarations | Structured top-level function tools | Structured `input_schema` tools | Structured `functionDeclarations` |
| tool choice | Native/structured common subset | Native/structured common subset | Structured common subset | Structured `toolConfig` |
| JSON object/schema | Native `response_format` | Structured `text.format` | Structured `output_config.format` when profile-admitted | Structured `responseMimeType`/`responseSchema` |
| stream | Native boolean | Native boolean | Native boolean | Structured route selection |
| vendor extensions | Unsupported by default | Unsupported by default | Unsupported by default | Unsupported by default |

Unknown fields are not forwarded. This is intentional: an accepted field
must have a semantic contract, a provider adapter, and a regression fixture.

### 3.2 Conversation and Content Rules

Chat uses `messages` with `system`, `developer`, `user`, `assistant`, and tool
messages. `developer` is normalized to the common system lane and keeps its
instruction priority. Responses uses a string or text-only instruction items
for `instructions`, while its `input` uses typed items. Image/file instruction
parts are rejected before dispatch because the common system lane is text-only.
Anthropic uses
alternating `user` and `assistant` messages whose content is a block array.
Gemini uses `user` and `model` contents with typed parts. The following
conversions are safe only in the common subset:

- system text remains an instruction channel; it is never invented as a user
  turn;
- assistant maps to Gemini `model`, but arbitrary roles are rejected;
- text remains text and is not replaced by a marker for an unsupported file;
- image data remains a typed image input;
- file ids and file URIs are preserved only when the target has the same kind
  of addressable file semantics;
- tool results remain untrusted data and cannot become a system instruction.

For multimodal turns, the adapter must choose the typed payload path. A
string-only provider compatibility fallback is valid only for text-only turns.

## 4. Tools and Structured Output

### 4.1 Function Tool Shape

The common internal declaration is:

```json
{
  "type": "function",
  "name": "lookup",
  "description": "Look up one record.",
  "parameters": {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
  },
  "strict": false
}
```

Wire placement differs:

| Protocol | Declaration | Streaming call arguments | Result |
| --- | --- | --- | --- |
| Chat | `tools[].function` | `delta.tool_calls[].function.arguments` JSON fragments | `role: tool` and `tool_call_id` |
| Responses | top-level `type: function` tool | `response.function_call_arguments.delta` JSON fragments | `function_call_output` item with `call_id` |
| Anthropic | `tools[].input_schema` | `input_json_delta` fragments inside a block | `tool_result` block with `tool_use_id` |
| Gemini | `functionDeclarations[]` | `functionCall.args` parts | `functionResponse.response` part |

Arguments are parsed exactly once at the canonical boundary. A malformed
argument stream is a tool-call failure, not a text answer. Calls are assembled
by stable call id and/or provider index; parallel calls cannot be silently
dropped. Gemini does not guarantee a universal call id, so the runtime keeps
an internal correlation id and matches a result by function/turn policy.

The common `auto` tool-choice behavior is portable. `none`, `required`, and a
named function require a target-specific capability check. A named function
must be present in the declaration set.

### 4.2 Structured Output

The meaning is JSON object or JSON schema, but the wrappers are not portable:

```json
{
  "chat": {"response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": {}}}},
  "responses": {"text": {"format": {"type": "json_schema", "name": "answer", "schema": {}}}},
  "anthropic": {"output_config": {"format": {"type": "json_schema", "schema": {}}}},
  "gemini": {"generationConfig": {"responseMimeType": "application/json", "responseSchema": {}}}
}
```

The example is a shape guide, not a promise that every provider accepts every
keyword. Profile admission and provider probes decide whether a wrapper is
forwarded. Chat `response_format` must never be copied verbatim into
Responses, Anthropic, or Gemini.

## 5. Reasoning Controls

Reasoning is model- and endpoint-scoped. A public caller may request a logical
effort, but the provider payload is selected from a verified profile receipt.

| Protocol | Typical native control | Semantic unit | Axio policy |
| --- | --- | --- | --- |
| Chat | top-level `reasoning_effort` | model-defined effort enum | Forward only after model/endpoint streaming probe |
| Responses | `reasoning: {"effort": "..."}` | model-defined effort enum | Forward only after model/endpoint streaming probe |
| Anthropic | `thinking: {"type":"enabled","budget_tokens":...}` | token budget | No generic effort forwarding until a closed budget map is researched and probed |
| Gemini | `generationConfig.thinkingConfig` | model-generation-specific budget/config | No generic effort forwarding until a model-local map is researched and probed |

The supported set is not universal. A profile may map a public level to a
lower native level only when the mapping is explicitly verified; it may not
invent a missing level or upgrade `low` into `high`. Higher reasoning usually
means more output/reasoning tokens, latency, and cost, but the runtime records
provider evidence rather than assuming a fixed multiplier.

Reasoning content is private by default. Only bounded redacted summaries and
token/latency receipts may leave the control plane. Hidden reasoning, raw
provider event bodies, and internal candidate/Judge/Synthesizer prompts never
enter a public stream.

## 6. Image and File Lane

Image generation and image editing are separate from text Fusion. A text
model's image input is still a multimodal text turn; an image generation or
edit model is admitted to the image lane and is not treated as a text solver.

### Input examples

Chat image content:

```json
{"type":"image_url","image_url":{"url":"data:image/png;base64,<BASE64>"}}
```

Responses image input:

```json
{"type":"input_image","image_url":"https://example.invalid/input.png","detail":"auto"}
```

Anthropic image block:

```json
{"type":"image","source":{"type":"url","url":"https://example.invalid/input.png"}}
```

Gemini inline image part:

```json
{"inlineData":{"mimeType":"image/png","data":"<BASE64>"}}
```

Only the source kinds supported by the target profile are accepted. An opaque
file id must not be guessed into a URL, and an image must not be flattened to
text. Image response data is returned through the image API contract and does
not enter the text stream accumulator.

## 7. Streaming and Event Conversion

### 7.1 Public stream shapes

| Surface | First useful event | Text delta | Tool delta | Completion |
| --- | --- | --- | --- | --- |
| Chat | role delta chunk | `choices[].delta.content` | `delta.tool_calls` | finish chunk, then `[DONE]` |
| Responses | `response.created` and typed additions | `response.output_text.delta` | `response.function_call_arguments.delta` | `response.completed` |
| Anthropic | `message_start`/block start | `text_delta` | `input_json_delta` | `message_delta`, `message_stop` |
| Gemini | first SSE JSON candidate | candidate text part | `functionCall` part | final candidate/usage JSON |

Native provider events are first reduced to visible text deltas and complete
tool intents. A protocol renderer then emits the caller-specific event
sequence. One provider event is not assumed to equal one semantic token or
one complete JSON object.

### 7.2 Streaming invariants

- The stream must actually produce incremental frames; a delayed buffered JSON
  body does not satisfy the streaming contract.
- Zero valid frames or an empty 2xx body is a provider failure.
- Tool arguments may be split across frames and must be assembled before tool
  execution.
- Before the first public delta, retry/failover is allowed for an eligible
  provider error. After commitment, the runtime emits one bounded public
  error and cannot replace the committed prefix with a second answer.
- Chat `[DONE]` is not a universal sentinel. It must not be emitted for
  Responses, Anthropic, or Gemini routes.
- Downstream cancellation must cancel the provider reader and release the
  physical replica.

### 7.3 Example Chat stream

```text
data: {"choices":[{"delta":{"role":"assistant"},"index":0}]}

data: {"choices":[{"delta":{"content":"partial"},"index":0}]}

data: {"choices":[{"delta":{},"finish_reason":"stop","index":0}]}

data: [DONE]
```

Equivalent Responses, Anthropic, and Gemini output must use their native event
names and object shapes. The renderer must not wrap all four protocols in a
Chat-shaped compatibility envelope.

## 8. Errors, Deadlines, and Retry Boundaries

Provider status, body shape, stream framing, and semantic output are separate
checks. The following are failure conditions even when HTTP status is 2xx:

- authentication or rate-limit response;
- malformed JSON or wrong event framing;
- no valid text, tool call, or image result;
- a declared optional capability is silently ignored or rejected;
- first byte or active stream exceeds the configured provider ceiling;
- a model/profile fails any required stability sample.

The production enrollment gate removes a provider/model from the usable list
when its measured streaming response exceeds 90 seconds. The gate is applied
per physical replica and per logical model; another replica of the same
logical model may remain usable. Runtime request deadlines are additionally
bounded by the enclosing Fusion deadline.

Retries are only before public commitment and only for retryable transport,
rate-limit, or provider failures. Do not retry an invalid request, a rejected
capability, or a malformed tool call as another provider call. Do not expose
upstream error bodies, credentials, prompts, internal role text, or raw
provider stream events.

## 9. Adapter Review Checklist

Before adding or changing a protocol/provider adapter, require all of the
following:

1. Native request fixtures for text, multimodal input, tools, structured
   output, and the model's verified reasoning transport.
2. Non-stream extraction fixtures that distinguish text, tool calls, refusal,
   usage, incomplete output, and empty success.
3. True incremental stream fixtures with at least two text fragments, split
   tool arguments, terminal usage, and a late failure.
4. A round-trip or explicit-loss receipt for every conversion in the field
   matrix.
5. Endpoint-bound probes for optional capabilities; documentation alone is not
   admission evidence.
6. Public error tests proving that secrets, raw prompts, and internal Fusion
   traffic are redacted.
7. Full regression execution before changing the profile or renderer.

Relevant code and tests:

- `src/axio_fusion_api/compat.py`: public normalization and rendering;
- `src/axio_fusion_api/providers.py`: provider payloads and stream parsing;
- `src/axio_fusion_api/tool_contract.py`: tool declaration/call conversion;
- `src/axio_fusion_api/image_api.py`: image lane;
- `tests/test_provider_http_contracts.py`: provider wire contracts;
- `tests/test_true_incremental_streaming.py`: actual stream behavior;
- `tests/test_content_contracts.py`: modality and structured-output admission.

## 10. Evidence Boundary

Official documentation defines a candidate wire contract. Public GitHub
gateways provide engineering patterns for route separation, model/channel
identity, account pools, and stream translators. Neither source proves that a
specific third-party endpoint accepts a field today. The pre-Fusion Research
Agent records bounded public evidence, and the endpoint-bound streaming probe
promotes only the exact model/profile/capability combination that passed.

This separation is mandatory for four reasons:

- provider aliases can expose different models under similar names;
- the same logical model may have multiple keys and channels;
- reasoning levels and token cost vary by model and endpoint;
- compatibility success is not evidence of superior model intelligence.
