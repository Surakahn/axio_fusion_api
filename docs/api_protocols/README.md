# Axio API Protocol Field Guide

This directory is the local, versioned protocol reference for the Axio
gateway. It records the public wire contracts that Axio accepts and emits,
the provider-side adapters that Axio can use, and the evidence boundary for
format conversion. It is intentionally an operational guide, not a copy of
any vendor's documentation.

The four public protocol surfaces are:

- OpenAI Chat Completions: `POST /v1/chat/completions`
- OpenAI Responses: `POST /v1/responses`
- Anthropic Messages: `POST /v1/messages`
- Google Gemini GenerateContent: `POST /v1beta/models/{model}:generateContent`
  and `:streamGenerateContent?alt=sse`

`GET /health` and `GET /v1/health` return a hash-safe registry projection.
`model_count`/`available_model_count` describe physical provider profiles,
while `logical_model_count`/`available_logical_model_count` describe unique
canonical models after replica deduplication. The latter counts are useful for
capacity and failover inspection only; they do not imply model quality or
benchmark admission.

## Reading Order

1. [`protocol_matrix.md`](protocol_matrix.md) defines the cross-protocol
   canonical field mapping and compatibility levels.
2. [`openai_chat_completions.md`](openai_chat_completions.md),
   [`openai_responses.md`](openai_responses.md),
   [`anthropic_messages.md`](anthropic_messages.md), and
   [`google_gemini_generate_content.md`](google_gemini_generate_content.md)
   describe each native request, response, stream, tool, reasoning, and error
   contract.
3. [`parameter_reference.md`](parameter_reference.md) is the compact field
   catalog and decision table. It distinguishes a public field that Axio can
   parse from an upstream field that Axio may forward only after capability
   proof.
4. [`wire_examples.md`](wire_examples.md) contains placeholder-only cURL and
   JSON examples for the four public surfaces, native provider shapes,
   reasoning controls, tool round trips, and image routes.
5. [`streaming_event_normalization.md`](streaming_event_normalization.md)
   describes how incremental output is normalized without leaking private
   Fusion traffic.
6. [`tool_call_normalization.md`](tool_call_normalization.md) defines the
   lossless and lossy portions of function/tool conversion.
7. [`image_generation_editing.md`](image_generation_editing.md) documents the
   separate image lane and why image models never enter text Fusion.
8. [`open_source_reference_audit.md`](open_source_reference_audit.md) records
   the public GitHub implementations inspected and the bounded lessons
   adopted by Axio.
9. [`integration_field_guide.md`](integration_field_guide.md) is the field-level
   implementation checklist for request parameters, conversions, streaming,
   tools, structured output, reasoning, images, errors, and retries.

## Source Policy

The source list below was checked through 2026-08-07 via the configured HTTP
proxy. Vendor behavior can change, so every live provider enrollment still
requires a streaming probe and an endpoint-bound capability receipt. A web
page or README is a design input, never runtime proof.

Official protocol references:

- OpenAI Chat Completions reference:
  <https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create/>
- OpenAI Responses reference:
  <https://developers.openai.com/api/reference/resources/responses/methods/create/>
- OpenAI Chat Completions streaming events:
  <https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events/>
- OpenAI Responses streaming events:
  <https://developers.openai.com/api/reference/resources/responses/streaming-events/>
- OpenAI Responses migration guide:
  <https://developers.openai.com/api/docs/guides/migrate-to-responses>
- OpenAI tools guide:
  <https://developers.openai.com/api/docs/guides/tools>
- OpenAI reasoning guide:
  <https://developers.openai.com/api/docs/guides/reasoning>
- OpenAI image generation guide:
  <https://developers.openai.com/api/docs/guides/image-generation/>
- Anthropic Messages API:
  <https://platform.claude.com/docs/en/api/messages>
- Anthropic Messages streaming:
  <https://platform.claude.com/docs/en/api/messages-streaming>
- Google Gemini GenerateContent:
  <https://ai.google.dev/api/generate-content>
- Google Gemini function calling:
  <https://ai.google.dev/gemini-api/docs/function-calling>

## Code Anchors

The reference is tied to the implementation rather than being a detached
design essay:

- `src/axio_fusion_api/compat.py` owns public request normalization and public
  response/stream rendering.
- `src/axio_fusion_api/providers.py` owns provider wire payloads, streaming
  parsing, endpoint paths, authentication, retries, and provider receipts.
- `src/axio_fusion_api/tool_contract.py` owns tool declaration and tool result
  conversion.
- `src/axio_fusion_api/image_api.py` owns the separate image generation/edit
  transport.
- `tests/test_provider_http_contracts.py`,
  `tests/test_true_incremental_streaming.py`, and
  `tests/test_image_api.py` are executable examples of the current contract.
  `tests/test_content_contracts.py` covers protocol-neutral multimodal and
  structured-output conversion, fail-closed admission, and public 400 errors.

The field guide is explanatory and versioned with the code. It does not replace
the official protocol sources or the provider-specific live capability probe.

## Compatibility Vocabulary

- **Native**: the field or event exists in the target protocol with the same
  meaning.
- **Structured conversion**: Axio maps the value to a different native shape
  without inventing an unsupported provider field.
- **Lossy conversion**: semantics or fidelity are deliberately reduced and
  the adapter must record the limitation.
- **Unsupported**: the request cannot be represented safely; the gateway must
  reject it or omit the field according to the route policy.
- **Verified**: a provider-specific optional capability was declared and then
  confirmed by a strict, streaming, endpoint-bound probe.

Axio never treats a successful HTTP status as proof that an optional field,
tool call, reasoning control, or stream format worked.
