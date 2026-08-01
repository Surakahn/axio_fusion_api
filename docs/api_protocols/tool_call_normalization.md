# Tool Call Normalization

Tool calls are a semantic contract, not a string substitution problem. Axio
normalizes only the common function subset and preserves the source protocol
in a safe receipt. Provider-specific tool features are not silently flattened
into a generic function.

## Common Internal Shape

The internal tool declaration is equivalent to:

```json
{
  "type": "function",
  "name": "lookup",
  "description": "Look up one record.",
  "parameters": {"type": "object", "properties": {}},
  "strict": false
}
```

An internal call is:

```json
{
  "id": "call-123",
  "name": "lookup",
  "arguments": {"query": "value"}
}
```

The internal representation parses JSON arguments before orchestration. It
must retain a stable call id and must reject malformed arguments rather than
executing an ambiguous tool request.

## Native Shapes

| Protocol | Declaration | Call | Result |
| --- | --- | --- | --- |
| Chat | `tools[].function.parameters` | `message.tool_calls[].function.arguments` JSON string | role `tool`, `tool_call_id` |
| Responses | top-level function tool | output `function_call.arguments` JSON string and `call_id` | `function_call_output` input item |
| Anthropic | `tools[].input_schema` | `content[].tool_use.input` object | `tool_result` block with `tool_use_id` |
| Gemini | `functionDeclarations[].parameters` | content part `functionCall.args` object | content part `functionResponse.response` |

## Conversion Rules

- Function name, description, object properties, required fields, and basic
  JSON Schema types are convertible in the common subset.
- Chat and Responses carry arguments as JSON strings; Anthropic and Gemini
  carry parsed objects. The adapter parses and serializes exactly once.
- A call id is preserved when the target has one. Gemini has no universally
  equivalent call id, so Axio carries an internal id only where the public
  response shape allows it and matches results by function name/turn when
  necessary.
- Parallel calls are preserved as an ordered list. A target that cannot
  represent parallel calls must reject or serialize them through an explicit
  route policy, never silently drop all but the first call.
- Vendor extensions, executable code tools, server-side tools, citations,
  cache controls, and tool-specific annotations are not part of the common
  contract. They require a dedicated capability and probe.
- Tool results are treated as untrusted data. They are inserted into the next
  provider turn as data, not as a new system instruction.

## Tool Choice

`auto`, `none`, `required`, and a named function do not have identical support
across all four protocols. Axio maps the common `auto` behavior and keeps
unsupported modes explicit. A named tool must exist in the declaration set;
the adapter must not forward a caller-selected arbitrary name.

## Streaming Assembly

Arguments may arrive split across many frames. The accumulator keys by call
id and/or provider index, joins fragments in order, and parses the final JSON
object. It tracks frame validity separately from semantic validity. An invalid
argument stream is a tool-call failure and cannot become a normal text answer
by accident.

## Code Anchors

`src/axio_fusion_api/tool_contract.py` owns declaration normalization, native
call rendering, result rendering, and safe tool summaries. Provider parsing is
in `providers._StreamAccumulator` and `normalize_provider_tool_calls`.
