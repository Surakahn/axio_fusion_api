# Four-Protocol Reasoning Transport Contracts

## Scope

This milestone completes the protocol-bound reasoning transport layer for the
API-only Axio Fusion runtime. It covers the four public/provider-compatible
families currently in scope: OpenAI Chat Completions, OpenAI Responses,
Anthropic Messages, and Gemini GenerateContent.

## Change

- Added a closed, protocol-neutral reasoning request contract with separate
  logical effort and native thinking-budget fields.
- Added model-local declarations for exact native effort values and exact
  positive integer budgets, including effort-to-budget maps for Anthropic and
  Gemini.
- Added provider payload construction that forwards a reasoning field only
  after the matching model/endpoint transport is verified. OpenAI effort fields
  are never guessed for Anthropic or Gemini.
- Added strict streaming probes for every declared effort or budget. A
  parameter rejection, malformed stream, or incomplete control cohort cannot
  promote a profile to `verified`.
- Bound all budget values to positive integers within the runtime maximum;
  `0`, negative values, booleans, and out-of-range values are discarded at the
  normalization boundary.
- Propagated the caller's reasoning budget through judge, synthesizer, and
  targeted escalation `FusionRequest` construction.
- Added endpoint-bound reconciliation and safe redaction fields without
  persisting provider URLs, model outputs, prompts, or credentials.
- Added the four-protocol parameter/wire reference and an audit of the CCX,
  cc-switch, NewAPI, CLIProxyAPI, and Client2API implementation patterns used
  as compatibility references.

## Verification

- Targeted reasoning, pre-Fusion screening, and reconciliation tests:
  `127 passed`.
- Full standalone regression under the supported Python 3.11 runtime:
  `858 passed in 183.50s`.
- `compileall` passed for `src`.
- `git diff --check` passed.
- Sensitive-value scan over the staged source/documentation surface found no
  API keys, private keys, or credentials.

## Boundary

This milestone changes transport capability handling only. It does not claim
that a larger reasoning budget improves model quality, and it does not mix
the independent benchmark/evaluation control plane into the serving runtime.
Quality claims remain subject to the separate benchmark campaign after the
provider model inventory is freshly screened and frozen.
