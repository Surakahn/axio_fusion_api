# Google Gemini GenerateContent Contract

## Native Routes and Authentication

The Gemini Developer API places the model in the route:

- non-stream: `POST /v1beta/models/{model}:generateContent`
- stream: `POST /v1beta/models/{model}:streamGenerateContent?alt=sse`

Authentication may use `x-goog-api-key` or the `key` query parameter depending
on the client and gateway. Axio keeps the key handling profile-specific and
does not put credentials in persisted receipts.

## Native Request

```json
{
  "systemInstruction": {
    "parts": [{"text": "system text"}]
  },
  "contents": [
    {"role": "user", "parts": [{"text": "question"}]}
  ],
  "tools": [
    {
      "functionDeclarations": [
        {
          "name": "lookup",
          "description": "Look up one record.",
          "parameters": {"type": "object", "properties": {}}
        }
      ]
    }
  ],
  "toolConfig": {
    "functionCallingConfig": {"mode": "AUTO"}
  },
  "generationConfig": {
    "temperature": 0.2,
    "topP": 0.9,
    "maxOutputTokens": 2048,
    "stopSequences": ["<END>"],
    "responseMimeType": "text/plain"
  }
}
```

`contents` uses `role: "user"` and `role: "model"`; the latter corresponds to
the canonical assistant role. Each content contains typed `parts`: text,
inline image data, file data, function calls, or function responses. Axio maps
base64 images to `inlineData` and HTTP(S)/`gs://` remote references to
`fileData.fileUri`; an opaque provider file id cannot be invented as a Gemini
URI. `systemInstruction`
is a separate typed field and must not be placed into `contents` as a fake user
message. Axio keeps system instructions text-only.

## Response and Usage

The response has `candidates`, each with `content.parts`, `finishReason`, and
optional safety metadata. Text is found in text parts. A model tool call is a
`functionCall` part; the caller sends the result back as a `functionResponse`
part with the function name and response object. Usage is reported under
`usageMetadata`, with prompt, candidate, total, and sometimes cached/thoughts
token counts.

## Streaming

The stream route returns a sequence of JSON response objects framed as SSE
when `alt=sse` is requested. Each object may contain only a fragment of the
candidate content. The adapter must concatenate text parts and assemble tool
call arguments by function-call identity. A JSON object boundary is not a
semantic turn boundary.

## Function Calling and Structured Output

Gemini declarations use `functionDeclarations`; this is structurally similar
to a function tool but not wire-compatible with Chat or Responses. Structured
output is configured with `generationConfig.responseMimeType` and, where
supported, `responseSchema`. Axio only forwards this through a closed adapter
mapping. It does not copy Chat `response_format` or Responses `text.format`
verbatim. `json_object` maps to `application/json`; `json_schema` additionally
maps the schema to `responseSchema`.

## Thinking and Reasoning Boundary

Gemini model families expose model-specific thinking controls under
`generationConfig.thinkingConfig`, commonly including a thinking budget and an
option to include thought summaries. The accepted fields and ranges vary by
model generation. They are not the OpenAI effort vocabulary.

Axio currently treats Gemini thinking as a documented future capability. It
does not forward a generic public effort value until the model screening Agent
has produced a model-local budget declaration and a strict streaming probe has
verified that exact route/model pair. This prevents a nominally compatible
Gemini gateway from silently ignoring or rejecting a reasoning control.

## Axio Adapter Anchor

- Route construction: `providers._gemini_generate_content_endpoint`.
- Request builder: `providers._gemini_payload`.
- Extraction: candidate content and `tool_contract` Gemini conversion.
- Public renderer: Gemini branch of `compat.IncrementalStreamRenderer`.
- Contract tests: `tests/test_provider_http_contracts.py` and
  `tests/test_true_incremental_streaming.py`.
