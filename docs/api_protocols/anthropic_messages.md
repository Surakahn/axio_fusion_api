# Anthropic Messages Contract

## Native Request

`POST /v1/messages` requires `model`, `max_tokens`, and `messages`. The
request uses `x-api-key` authentication, `anthropic-version` (currently the
adapter sends `2023-06-01`), and `Content-Type: application/json`.

```json
{
  "model": "claude-model-id",
  "max_tokens": 2048,
  "system": "system text",
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "question"}]}
  ],
  "stream": true,
  "temperature": 0.2,
  "top_p": 0.9,
  "top_k": 40,
  "stop_sequences": ["<END>"],
  "tools": [
    {
      "name": "lookup",
      "description": "Look up one record.",
      "input_schema": {"type": "object", "properties": {}}
    }
  ],
  "tool_choice": {"type": "auto"}
}
```

Anthropic content is a block array. Text blocks use `type: "text"`; images
use an image URL or base64 source block; assistant tool calls use `tool_use`;
tool results are user messages with `tool_result`. The same conversation
alternates user and assistant roles; a provider adapter must not invent
unsupported roles. The closed common contract does not map arbitrary file
references into Anthropic image blocks, and system content is text-only.

## Response and Stop Reasons

The response has `type: "message"`, `id`, `role: "assistant"`, `model`, a
typed `content` array, `stop_reason`, and `usage`. Text is extracted only from
text blocks. A tool response uses a `tool_use` content block and normally has
`stop_reason: "tool_use"`; ordinary completion uses `end_turn` or another
provider stop reason.

## Streaming

With `stream: true`, the native SSE sequence is typed and named:

1. `message_start` with an incomplete message envelope;
2. `content_block_start` for each text or tool block;
3. `content_block_delta`, including `text_delta` or `input_json_delta`;
4. `content_block_stop`;
5. `message_delta` with stop reason and final usage;
6. `message_stop`.

`ping` and `error` events are also valid. Tool JSON is incremental and must be
assembled per content block index. A client must not assume one event equals
one complete JSON object.

## Thinking and Reasoning Boundary

Anthropic's native extended thinking control is a structured `thinking` object
such as `{"type":"enabled","budget_tokens":...}`. Its budget is a token
quantity, not the OpenAI `low`/`medium`/`high` effort vocabulary. Thinking may
also introduce thinking content blocks and changes to minimum token rules.

Axio documents this distinction but does not currently forward a generic
public `reasoning_effort` into Anthropic. A future adapter must add a closed
profile mapping from logical effort to audited token budgets, validate the
model's minimum/maximum limits, probe the exact endpoint in strict streaming
mode, and report the extra token and latency cost. Until then the field is
omitted rather than guessed.

## Tools, Images, Structured Output, and Errors

Tool definitions use `input_schema`, not Chat's nested `function.parameters`.
The converter can map a common JSON Schema subset, but provider-specific
schema keywords and block annotations are not promised lossless. For a JSON
schema request, Axio uses the native `output_config.format` wrapper when the
profile is admitted for structured output. A plain text request needs no
output wrapper. Anthropic errors are typed objects with categories such as
invalid request,
authentication, rate limit, or API error; Axio maps them to safe public errors
while retaining only code/status/latency receipts.

## Axio Adapter Anchor

- Request builder: `providers._anthropic_payload`.
- Required version header: `providers._anthropic_turn`.
- Extraction: typed content blocks and `tool_contract`.
- Public stream rendering: Anthropic branch of
  `compat.IncrementalStreamRenderer`.
- Contract assertions: `tests/test_provider_http_contracts.py` and
  `tests/test_true_incremental_streaming.py`.
