# OpenAI Chat Completions Contract

## Native Request

`POST /v1/chat/completions` uses a JSON object. The core fields are:

```json
{
  "model": "model-id",
  "messages": [
    {"role": "system", "content": "system text"},
    {"role": "user", "content": "question"}
  ],
  "stream": true,
  "max_tokens": 1024,
  "temperature": 0.2,
  "top_p": 0.9,
  "stop": ["<END>"],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "lookup",
        "description": "Look up one record.",
        "parameters": {"type": "object", "properties": {}}
      }
    }
  ],
  "tool_choice": "auto",
  "response_format": {"type": "json_object"}
}
```

`max_completion_tokens` is preferred by current OpenAI models that distinguish
completion and reasoning tokens; older compatible gateways may accept
`max_tokens`. Axio's provider adapter uses the profile's audited payload
policy and does not blindly copy both fields.

Messages may contain text and image content blocks. The current Chat contract
also accepts the OpenAI `developer` role; it is normalized into Axio's single
system-instruction lane so a cross-protocol adapter cannot demote it to a user
turn. Multiple system/developer instructions are joined in request order.
Axio accepts HTTP(S) image
URLs and base64 data URLs, rebuilding them as `image_url` blocks for a Chat
provider. A file reference is not silently converted to an image and is
rejected when Chat is the selected provider protocol. System content is
text-only. Assistant messages
may contain `tool_calls`; tool results use role `tool` and a matching
`tool_call_id`. A function call's arguments are a JSON string on the wire,
not an already parsed object.

## Response

The non-stream response has `object: "chat.completion"`, an `id`, `model`, a
`choices` array, and optional `usage`. A text choice is read from
`choices[0].message.content`; a tool choice is read from
`choices[0].message.tool_calls`. `finish_reason` commonly reports `stop`,
`length`, `tool_calls`, or a refusal-related reason.

The response may contain `refusal` or content parts instead of a plain string.
The adapter must preserve a refusal as safe visible text and must not treat an
empty message with a 2xx status as success.

## Streaming

With `stream: true`, the server emits SSE data frames. Each data value is a
JSON chat completion chunk. The normal sequence is:

1. an initial chunk with the assistant role;
2. one or more `choices[0].delta.content` fragments;
3. optional `delta.tool_calls` fragments whose function arguments may be split
   across frames;
4. a final chunk with `finish_reason`;
5. `data: [DONE]`.

Some providers add usage in a final empty-choice chunk. Axio accepts this only
as usage metadata and never exposes provider reasoning or private event bodies
as user-visible text.

## Reasoning

OpenAI-compatible gateways use different names. The native Chat Completions
field is generally top-level `reasoning_effort`; it is not the Responses
`reasoning: {"effort": ...}` object. The accepted values are model-specific.
Axio therefore stores an explicit profile transport such as:

```json
{
  "status": "verified",
  "transport": "chat_reasoning_effort",
  "supported_efforts": ["low", "medium", "high"],
  "effort_map": {"xhigh": "high", "max": "high"}
}
```

The map may only reduce effort. It cannot turn `low` into `high`, invent a
missing level, or cross an API format boundary. A candidate or mismatched
transport is omitted from the provider payload.

## Tools and Structured Output

Chat function declarations use `tools[].function.name`, `description`, and
JSON Schema `parameters`. Tool call argument fragments are assembled by call
id/index before being exposed to the orchestrator. Structured output uses
`response_format` (`json_object` or `json_schema`). The provider renderer maps
the closed Axio schema declaration into the nested Chat wrapper; Responses uses
a different `text.format` field, and the two must not be copied across adapters.

## Axio Adapter Anchor

- Request builder: `providers._chat_payload`.
- Non-stream extraction: `HTTPProviderClient._chat_turn`.
- Stream extraction: `_iter_stream_events` and the Chat branch of the stream
  accumulator.
- Public rendering: `compat.IncrementalStreamRenderer`.
- Contract tests: `tests/test_provider_http_contracts.py` and
  `tests/test_true_incremental_streaming.py`.
