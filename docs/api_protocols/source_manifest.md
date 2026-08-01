# Local Source Manifest

This file is the local index for the public materials used to build the
protocol field guide. It intentionally stores URLs, retrieval date, and the
reviewed revision instead of vendoring third-party HTML or source code into
Axio.

| Area | Source | Retrieved | Revision or anchor |
| --- | --- | --- | --- |
| OpenAI Chat | <https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create/> | 2026-08-01 | Current create method |
| OpenAI Chat streaming | <https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events/> | 2026-08-01 | Current streaming events |
| OpenAI Responses | <https://developers.openai.com/api/reference/resources/responses/methods/create/> | 2026-08-01 | Current create method |
| OpenAI Responses streaming | <https://developers.openai.com/api/reference/resources/responses/streaming-events/> | 2026-08-01 | Current streaming events |
| OpenAI migration | <https://developers.openai.com/api/docs/guides/migrate-to-responses> | 2026-08-01 | Current guide |
| OpenAI tools | <https://developers.openai.com/api/docs/guides/tools> | 2026-08-01 | Current guide |
| OpenAI reasoning | <https://developers.openai.com/api/docs/guides/reasoning> | 2026-08-01 | Current guide |
| OpenAI images | <https://developers.openai.com/api/docs/guides/image-generation/> | 2026-08-01 | Current guide |
| OpenAI images reference | <https://developers.openai.com/api/reference/resources/images/methods/generate/> | 2026-08-01 | Current generate method |
| OpenAI image edits reference | <https://developers.openai.com/api/reference/resources/images/methods/edit/> | 2026-08-01 | Current edit method |
| Anthropic Messages | <https://platform.claude.com/docs/en/api/messages> | 2026-08-01 | Current API page |
| Anthropic streaming | <https://platform.claude.com/docs/en/api/messages-streaming> | 2026-08-01 | Current API page |
| Gemini GenerateContent | <https://ai.google.dev/api/generate-content> | 2026-08-01 | Current API page |
| Gemini function calling | <https://ai.google.dev/gemini-api/docs/function-calling> | 2026-08-01 | Current guide |
| CCX | <https://github.com/BenedictKing/ccx> | 2026-08-01 | `71b842e3e8300d0b9329446af03a39c498580b55` |
| CC Switch | <https://github.com/farion1231/cc-switch> | 2026-08-01 | `ebbf141fc71547a99f669df1be8e345130d1d890` |
| New API | <https://github.com/QuantumNous/new-api> | 2026-08-01 | `cfaba1dd6754d4238e1360247c198a64a313e96c` |
| CLIProxyAPI | <https://github.com/router-for-me/CLIProxyAPI> | 2026-08-01 | `bc71c77f5cc42f3fbe1bf040cf14d4f166894835` |
| Client2API | <https://github.com/Hongtruongbvn/client2api> | 2026-08-01 | default branch `main`; small client translation proxy |

## Local Companion Documents

| Document | Purpose | Boundary |
| --- | --- | --- |
| [`README.md`](README.md) | Reading order, source policy, and code anchors | Orientation only |
| [`protocol_matrix.md`](protocol_matrix.md) | Compact cross-protocol mapping | Contract summary |
| [`parameter_reference.md`](parameter_reference.md) | Official field catalog and forwarding decisions | Closed common contract |
| [`wire_examples.md`](wire_examples.md) | Placeholder-only cURL and native JSON examples | No credentials |
| [`integration_field_guide.md`](integration_field_guide.md) | Field-level implementation and review guide | No live capability proof |
| [`open_source_reference_audit.md`](open_source_reference_audit.md) | Bounded lessons from public gateways | No code or credential reuse |

## Refresh Procedure

When an upstream protocol changes:

1. record the new URL/revision and retrieval date here;
2. update the relevant protocol guide and matrix;
3. add or update a fixture that exercises the changed wire shape;
4. run the four-protocol and full regression suites;
5. only then change the adapter or capability registry.

No live provider request is performed by documentation refresh alone. Capability
promotion remains the responsibility of pre-Fusion screening and strict
endpoint-bound probes.
