# Local Source Manifest

This file is the local index for the public materials used to build the
protocol field guide. It intentionally stores URLs, retrieval date, and the
reviewed revision instead of vendoring third-party HTML or source code into
Axio.

| Area | Source | Retrieved | Revision or anchor |
| --- | --- | --- | --- |
| OpenAI Chat | <https://developers.openai.com/api/reference/chat> | 2026-08-01 | Current reference page |
| OpenAI Responses | <https://developers.openai.com/api/reference/responses> | 2026-08-01 | Current reference page |
| OpenAI migration | <https://developers.openai.com/api/docs/guides/migrate-to-responses> | 2026-08-01 | Current guide |
| OpenAI tools | <https://developers.openai.com/api/docs/guides/tools> | 2026-08-01 | Current guide |
| OpenAI reasoning | <https://developers.openai.com/api/docs/guides/reasoning> | 2026-08-01 | Current guide |
| OpenAI images | <https://developers.openai.com/api/docs/guides/image-generation> | 2026-08-01 | Current guide |
| Anthropic Messages | <https://docs.anthropic.com/en/api/messages> | 2026-08-01 | Current API page |
| Anthropic streaming | <https://docs.anthropic.com/en/api/messages-streaming> | 2026-08-01 | Current API page |
| Gemini GenerateContent | <https://ai.google.dev/api/generate-content> | 2026-08-01 | Current API page |
| Gemini function calling | <https://ai.google.dev/gemini-api/docs/function-calling> | 2026-08-01 | Current guide |
| CCX | <https://github.com/BenedictKing/ccx> | 2026-08-01 | `71b842e3e8300d0b9329446af03a39c498580b55` |
| CC Switch | <https://github.com/farion1231/cc-switch> | 2026-08-01 | `ebbf141fc71547a99f669df1be8e345130d1d890` |
| New API | <https://github.com/QuantumNous/new-api> | 2026-08-01 | `cfaba1dd6754d4238e1360247c198a64a313e96c` |
| CLIProxyAPI | <https://github.com/router-for-me/CLIProxyAPI> | 2026-08-01 | `bc71c77f5cc42f3fbe1bf040cf14d4f166894835` |
| Client2API | <https://github.com/Hongtruongbvn/client2api> | 2026-08-01 | default branch `main` |

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
