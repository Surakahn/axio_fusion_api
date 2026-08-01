# Streaming Event Normalization

Streaming is part of the product contract. Axio never buffers an entire
provider answer merely to make a format conversion possible when the public
route can emit a safe incremental result. At the same time, internal Fusion
traffic must never be exposed as a public stream.

## Internal Boundary

Provider adapters reduce native events to two internal values:

- visible assistant text deltas;
- complete provider tool-call intents after arguments are assembled.

Reasoning tokens, raw provider event bodies, internal prompts, candidate
answers, Judge messages, and Synthesizer instructions stay inside the
orchestrator. `ProviderStreamObserver` may receive only visible text. Once it
has emitted public text, retry cannot replace the committed prefix.

## Public Event Sequences

### Chat Completions

```text
role chunk
  -> zero or more content/tool argument chunks
  -> terminal finish_reason chunk
  -> optional usage chunk
  -> data: [DONE]
```

### Responses

```text
response.created
  -> response.in_progress
  -> output_item/content_part added
  -> output_text delta or function_call_arguments delta
  -> corresponding done events
  -> response.completed (or response.failed)
```

Every typed Responses event emitted by Axio has a monotonic sequence number.

### Anthropic

```text
message_start
  -> content_block_start
  -> content_block_delta (text or input JSON)
  -> content_block_stop
  -> message_delta
  -> message_stop
```

Errors use a typed `error` event. A public Anthropic stream is not converted
into Chat-style `[DONE]` framing.

### Gemini

```text
SSE JSON candidate fragments
  -> final candidate/usage object
```

Gemini does not use named Anthropic/Responses events. Axio preserves JSON SSE
objects with the Gemini candidate shape.

## Framing Rules

- SSE lines are UTF-8 and use `data:` fields; a named event is optional for
  Chat and Gemini but required by typed Responses/Anthropic events.
- A frame can split a JSON string or tool argument; parsers accumulate by
  semantic id/index.
- `[DONE]` is a Chat sentinel only. It is not valid as a universal sentinel.
- A provider may return `application/x-ndjson`; the strict provider parser
  accepts only the protocol framing declared by the route/probe policy.
- A successful HTTP response with zero valid frames is a failed semantic
  response, not an empty successful answer.
- Read deadlines are refreshed for active frames but bounded by the provider
  ceiling and the enclosing Fusion deadline.

## Error Semantics

Before the first public delta, Axio may retry a retryable provider failure or
fail over to a replica. After commitment, Axio emits one safe public stream
error and closes the stream; it does not expose the upstream body or start a
second answer. The error contains a bounded code/message and never includes a
credential, raw prompt, or internal role text.

## Testing Requirements

Every protocol adapter must have tests for:

1. first-frame timing and actual streaming, not only a JSON response;
2. multiple text fragments and whitespace preservation;
3. split tool-call argument fragments;
4. provider reasoning fields being excluded from visible text;
5. a late failure after partial output;
6. malformed/empty 2xx streams;
7. usage and terminal event behavior;
8. cancellation when the downstream client disconnects.

Current executable coverage is in `test_provider_http_contracts.py`,
`test_true_incremental_streaming.py`, and the stream-related portions of
`test_fusion_core_regressions.py`.
