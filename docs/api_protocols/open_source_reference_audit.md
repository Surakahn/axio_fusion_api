# Open Source Reference Audit

This audit records public repositories inspected for adapter and gateway
engineering patterns. The repositories are references only. Axio does not
copy their code, credentials, model claims, licensing assumptions, or upstream
service behavior.

The repository state below was checked on 2026-08-01. Commit hashes are the
review anchors; upstream projects continue to change.

## CCX

- Repository: <https://github.com/BenedictKing/ccx>
- HEAD reviewed: `71b842e3e8300d0b9329446af03a39c498580b55`
- License shown by GitHub: MIT
- Relevant public surface: one server exposing `/v1/messages`,
  `/v1/chat/completions`, `/v1/responses`, `/v1/images/*`, and
  `/v1beta/models/*`.
- Useful lesson: protocol routing should be explicit at the endpoint boundary;
  model mapping, per-channel keys, health checks, failover, and Responses
  session tracking are separate concerns.
- File anchors reviewed: `backend-go/internal/autopilot/newapi_adapter.go`,
  `backend-go/internal/autopilot/provider_quality_probe.go`,
  `backend-go/internal/config/config_chat.go`,
  `backend-go/internal/config/config_responses.go`, and
  `backend-go/internal/config/config_gemini.go`.
- Axio adoption: `server.py` selects the input protocol before canonicalizing;
  `providers.py` keeps provider payload construction separate from public
  rendering; image traffic has its own module.
- Deliberately not adopted: opaque model fallback, unverified parameter
  forwarding, or treating endpoint availability as capability proof.

## CC Switch

- Repository: <https://github.com/farion1231/cc-switch>
- HEAD reviewed: `ebbf141fc71547a99f669df1be8e345130d1d890`
- License shown by GitHub: MIT
- Relevant public surface: provider configuration and switching for Claude,
  Codex, Gemini, OpenCode, OpenClaw, and Hermes-oriented clients.
- Useful lesson: provider configuration needs explicit per-client format,
  model mapping, endpoint overrides, and a user-visible switching boundary.
- File anchors reviewed: `src-tauri/src/proxy/providers/adapter.rs`,
  `src-tauri/src/proxy/providers/streaming.rs`,
  `src-tauri/src/proxy/providers/reasoning_bridge.rs`,
  `src-tauri/src/proxy/providers/transform_responses.rs`, and
  `src-tauri/src/proxy/providers/transform_gemini.rs`.
- Axio adoption: provider profiles include API format, model identity, base URL
  indirection, key pools, traffic control, and reasoning capability metadata.
- Deliberately not adopted: desktop state as a serving registry, implicit
  client-specific assumptions, or OAuth/account behavior outside Axio's
  remote API scope.

## New API

- Repository: <https://github.com/QuantumNous/new-api>
- HEAD reviewed: `cfaba1dd6754d4238e1360247c198a64a313e96c`
- License shown by GitHub: check the repository license before redistribution.
- Relevant public surface: unified model hub, channel management, model
  aliases, quota/billing, retries, and OpenAI/Claude/Gemini-compatible
  distribution.
- Useful lesson: physical channel replicas and logical model aliases are
  different entities; routing and accounting need a stable model identity.
- File anchors reviewed: `relay/channel/adapter.go`,
  `relay/channel/openai/relay_responses.go`,
  `relay/channel/openai/responses_via_chat.go`,
  `relay/channel/gemini/adaptor.go`, and `model/channel.go`.
- Axio adoption: `canonical_model_id` de-duplicates the same model exposed by
  multiple channels while retaining provider replicas for health-aware
  failover. Evaluation baselines bind to logical identity rather than a key.
- Deliberately not adopted: billing semantics, user quotas, or claims that a
  relay's alias is evidence of model quality.

## CLIProxyAPI / CPA

- Repository: <https://github.com/router-for-me/CLIProxyAPI>
- HEAD reviewed: `bc71c77f5cc42f3fbe1bf040cf14d4f166894835`
- License shown by GitHub: check the repository license before redistribution.
- Relevant public surface: OpenAI, Gemini, Claude, and Codex-compatible
  endpoints, streaming/non-streaming paths, tools, multimodal input,
  multi-account round-robin, and provider-specific translators.
- Useful lesson: protocol translation must be divided into provider-specific
  request/response translators and stream bridges; account pools need health
  and retry state; protocol paths and auth headers are not interchangeable.
- File anchors reviewed: `internal/translator/` and
  `internal/relay/` translator/stream packages, plus the public
  `examples/plugin/request-translator` and
  `examples/plugin/response-translator` extension contracts.
- Axio adoption: the adapter split in `providers.py`, native stream parsers,
  explicit route normalization, key rotation, bounded retry, and separate
  protocol renderers.
- Deliberately not adopted: subscription/OAuth credential extraction, service
  cloaking, or any behavior that would make a provider response appear to be a
  different model without a measurement receipt.

## Sub2API

- Repository: <https://github.com/Wei-Shaw/sub2api>
- HEAD reviewed: `93367b6db43315abe4f9fd9b09cbfc971b1f5ad0`
- License shown by GitHub: LGPL-3.0
- Relevant public surface: subscription-backed OpenAI, Claude, Gemini, and
  compatible request gateways with model mappings, streaming bridges, and
  OpenAI/Codex reasoning-effort controls.
- Useful lesson: normalize an explicitly enumerated reasoning map once, then
  apply a separate ceiling. This avoids chained rewrites and keeps omitted
  values under the upstream default.
- File anchors reviewed:
  `backend/internal/domain/reasoning_effort.go`,
  `backend/internal/service/openai_reasoning_effort_policy.go`, and
  `backend/internal/pkg/apicompat/chatcompletions_anthropic_bridge_test.go`.
- Axio adoption: `ModelProfile` now resolves a closed, one-step logical to
  native mapping and emits a mapping receipt. Axio is stricter: an upward
  mapping is limited to explicit model-scoped `xhigh -> max`, and its target
  must be verified by a strict stream probe against the active endpoint.
- Deliberately not adopted: group-wide arbitrary rewrites, cross-protocol
  field mutation without a model capability record, and opaque account or
  subscription behavior.

## Client2API

- Repository: <https://github.com/Hongtruongbvn/client2api>
- HEAD reviewed: repository default branch `main`; inspect the current commit
  before using any implementation detail.
- Relevant public surface: small client-facing translation proxy pattern.
- Useful lesson: keep client compatibility concerns at the edge and convert
  once into an internal request, rather than spreading protocol checks through
  every business operation.
- File anchors reviewed: the repository's client adapter and request/response
  conversion modules on the `main` branch. The project is intentionally kept
  as a small reference rather than a dependency because its implementation
  surface changes quickly.
- Axio adoption: `compat.canonicalize_payload` and
  `compat.render_response` are the only public conversion boundary; the
  orchestrator consumes `FusionRequest` and knows no wire JSON layout.
- Deliberately not adopted: unknown protocol extensions, unbounded passthrough
  JSON, and client-specific behavior without a regression fixture.

## Cross-Reference Conclusions

The common engineering pattern across these projects is a gateway with
explicit protocol routes, model/channel separation, health-aware fallback, and
provider-specific stream translators. None of them proves that a prompt-level
fusion system improves model intelligence. Axio therefore keeps two boundaries
that are easy to conflate:

1. **Compatibility boundary:** make one remote model portfolio callable through
   four public protocols with correct streaming and tool semantics.
2. **Fusion/evaluation boundary:** compose bounded remote roles and measure the
   result through an independent benchmark client.

The first can be tested with fixtures and wire-contract checks. The second
requires live provider evidence and the separately governed 21-suite
evaluation campaign.
