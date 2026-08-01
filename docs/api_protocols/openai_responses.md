# OpenAI Responses Contract

## Native Request

`POST /v1/responses` accepts a typed interaction envelope. The important
fields are:

```json
{
  "model": "model-id",
  "instructions": "system text",
  "input": [
    {"role": "user", "content": [{"type": "input_text", "text": "question"}]}
  ],
  "stream": true,
  "max_output_tokens": 2048,
  "temperature": 0.2,
  "top_p": 0.9,
  "tools": [
    {
      "type": "function",
      "name": "lookup",
      "description": "Look up one record.",
      "parameters": {"type": "object", "properties": {}},
      "strict": true
    }
  ],
  "tool_choice": "auto",
  "text": {"format": {"type": "text"}},
  "reasoning": {"effort": "high", "summary": "auto"}
}
```

`input` may be a string or an array of typed messages/items. Image inputs use
`input_image` with an HTTP(S)/data URL or a provider file id. File inputs use
`input_file` with `file_id` or `file_url`; the canonical adapter also accepts
these as standalone input items and as content inside a user message.
Function calls
and tool results are not Chat messages: a function call is an output item with
`type: "function_call"`, and its result is an input item with
`type: "function_call_output"` and a matching `call_id`.

`previous_response_id` can continue a stored Responses conversation. Axio
does not assume the upstream stores data: the public continuation behavior is
backed by the Axio runtime continuation store and is explicitly reported in
metadata.

## Response Shape

The top-level object has `object: "response"`, `id`, `status`, `model`,
`output`, and `usage`. `output` is a typed item list. A text answer is found
in a message item's content block with `type: "output_text"`; `output_text`
is a convenience field and is not a substitute for parsing typed items when
tools or multiple output items are present.

The following item types are relevant to Axio:

- `message` containing `output_text` content;
- `function_call` with `call_id`, `name`, and JSON-string `arguments`;
- reasoning and other provider-specific typed items, which are not copied into
  the public visible answer;
- error or incomplete state represented at the response level.

## Streaming Event Order

Responses streaming uses named SSE events with typed JSON data. A text route
normally emits:

1. `response.created`;
2. `response.in_progress`;
3. `response.output_item.added`;
4. `response.content_part.added`;
5. zero or more `response.output_text.delta`;
6. `response.output_text.done`;
7. `response.content_part.done`;
8. `response.output_item.done`;
9. `response.completed`.

Function calls use `response.function_call_arguments.delta` and
`response.function_call_arguments.done` within the corresponding output item.
Axio attaches monotonic sequence numbers to emitted Responses events and
never forwards the private candidate/Judge/Synthesizer stream.

## Reasoning

The native Responses control is nested under `reasoning`, commonly with
`effort` and optional `summary`. This is not interchangeable with Chat
Completions' top-level `reasoning_effort`. An Axio profile may declare the
standard nested transport or a separately verified compatible top-level
variant. The provider profile, not the public caller's spelling, decides which
wire field is safe.

Reasoning output is private by default. Axio records only bounded, redacted
reasoning summaries and token/latency receipts. It does not stream hidden
reasoning tokens to a caller as visible answer text.

## Tools and Text Formats

Responses function tools are top-level objects with `type`, `name`,
`description`, `parameters`, and optional `strict`. `response_format` from Chat
Completions must not be copied into Responses; the native structured text
shape is `text.format`. The current Axio public renderer emits the stable
subset needed for text, image/file input, JSON schema, and function-call
responses. A gateway that accepts only string `input` may use the compatibility
fallback for text-only turns; it is forbidden for multimodal turns or turns
with tool semantics.

## Axio Adapter Anchor

- Typed payload: `providers._responses_typed_payload`.
- Text compatibility payload: `providers._responses_text_payload`.
- Extraction: `providers._extract_responses_text` and the Responses tool
  normalizer.
- Public rendering and sequence numbers: `compat.IncrementalStreamRenderer`.
- Continuation control plane: `server.py` and runtime response continuation
  state.
