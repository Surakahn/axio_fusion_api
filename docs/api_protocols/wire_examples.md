# Four-Protocol Wire Examples

All values below are placeholders. They are safe examples for local contract
tests and are not executable credentials. The public Axio model is always one
of `axio-fast`, `axio-terra`, or `axio-pro`.

## Chat Completions

```bash
curl -N "$AXIO_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $AXIO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "axio-terra",
    "messages": [{"role": "user", "content": "Solve this carefully."}],
    "stream": true,
    "stream_options": {"include_usage": true},
    "max_completion_tokens": 1024,
    "reasoning_effort": "high"
  }'
```

The public adapter accepts the legacy `max_tokens` spelling too. The selected
upstream profile decides which native spelling is safe.

## Responses

```bash
curl -N "$AXIO_BASE_URL/v1/responses" \
  -H "Authorization: Bearer $AXIO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "axio-pro",
    "instructions": "Be precise and show only the useful conclusion.",
    "input": [{
      "role": "user",
      "content": [{"type": "input_text", "text": "Compare two designs."}]
    }],
    "stream": true,
    "reasoning": {"effort": "xhigh"},
    "text": {"format": {"type": "text"}}
  }'
```

For a continuation, send `previous_response_id` returned by Axio. The current
implementation stores only a bounded, process-local continuation and reports
that storage scope in response metadata.

## Anthropic Messages

```bash
curl -N "$AXIO_BASE_URL/v1/messages" \
  -H "x-api-key: $AXIO_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "axio-terra",
    "max_tokens": 2048,
    "system": "Be precise.",
    "messages": [{"role": "user", "content": "Solve this carefully."}],
    "stream": true,
    "thinking": {"type": "enabled", "budget_tokens": 2048}
  }'
```

`thinking` is a native token budget, not a universal effort enum. Axio parses
the request but only a profile with an exact, endpoint-bound thinking
capability may send a corresponding upstream field.

## Gemini GenerateContent

```bash
curl -N "$AXIO_BASE_URL/v1beta/models/axio-fast:streamGenerateContent?alt=sse" \
  -H "x-goog-api-key: $AXIO_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "systemInstruction": {"parts": [{"text": "Be precise."}]},
    "contents": [{"role": "user", "parts": [{"text": "Solve this carefully."}]}],
    "generationConfig": {
      "maxOutputTokens": 1024,
      "responseMimeType": "text/plain",
      "thinkingConfig": {"thinkingBudget": 2048}
    }
  }'
```

The route model is parsed by the public server and replaced with the selected
provider model internally. A Gemini stream is SSE-framed JSON, not a sequence
of named Responses events.

## Common Function Tool

The public common subset is declared once per request and translated at the
provider boundary:

```json
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Look up one record.",
    "parameters": {
      "type": "object",
      "properties": {"query": {"type": "string"}},
      "required": ["query"]
    }
  }
}
```

The corresponding native declarations are Chat `tools[].function`,
Responses top-level function tools, Anthropic `input_schema`, and Gemini
`functionDeclarations`. Arguments are accumulated across stream frames and
parsed once; malformed arguments never become an executable tool call.

## Images Are A Separate Lane

Text Fusion does not turn `gpt-image-*` into a text candidate. Verified image
profiles use the dedicated generation/editing routes described in
[`image_generation_editing.md`](image_generation_editing.md). The public
image request is either JSON generation or validated multipart editing, and
image artifacts do not enter Judge/Synthesizer prompts.

## Provider-Side Reasoning Examples

These are reference shapes, not permission to forward them:

```json
{
  "chat/completions": {"reasoning_effort": "high"},
  "responses": {"reasoning": {"effort": "high"}},
  "anthropic": {"thinking": {"type": "enabled", "budget_tokens": 2048}},
  "gemini": {"generationConfig": {"thinkingConfig": {"thinkingBudget": 2048}}}
}
```

NVIDIA's GPT-OSS Chat contract and TokenAPIs' current Responses contract are
different and are represented by different profile transports. The model
screening Agent must record the exact native levels and token/latency evidence;
the runtime never assumes that `max` exists just because Axio's logical enum
contains it.
