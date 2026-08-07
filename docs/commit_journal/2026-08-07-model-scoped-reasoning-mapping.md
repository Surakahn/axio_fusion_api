# Model-Scoped Reasoning Effort Mapping

## Scope

This milestone hardens the remote-provider reasoning-control boundary. It does
not change Fusion prompts, model ranking, route weights, a frozen screening
plan, benchmark cases, benchmark decoding, or any provider credential.

## Decision

Axio keeps the public logical effort vocabulary independent from the native
subset accepted by each exact provider endpoint. A profile may use a normal
explicit downgrade when the requested level is unavailable. The sole upward
compatibility rule is explicit, model-scoped `xhigh -> max`, for a provider
that has verified native `max` but no native `xhigh`.

The target must be a declared native effort and pass the existing strict,
streaming, endpoint-bound probe before the map can reach a provider payload.
No provider-level, group-wide, chained, or arbitrary upward rewrite is
accepted.

## Implementation

- Added a closed map classifier and model-level resolution receipt to
  `ModelProfile`.
- Preserved the existing `resolve_reasoning_transport()` tuple interface for
  adapters while exposing requested effort, effective effort, map direction,
  map scope, and verification status to audit callers.
- Bound profile scope into the hash-only reasoning transport probe identity and
  its redacted projection.
- Extended benchmark reasoning receipts with map fields so an effective
  provider effort is auditable without exposing provider identifiers, prompt
  text, outputs, endpoints, or secrets.
- Made conflicting OpenAI-compatible `reasoning_effort` and
  `reasoning.effort` values a public `400 conflicting_reasoning_effort`.
  Matching aliases remain accepted. Equivalent conflicts between the generic
  Axio thinking-budget alias and Anthropic/Gemini native budget values also
  fail before provider dispatch.
- Updated the reasoning transport contract, four-protocol parameter reference,
  and source manifest.

## Reference Review

The current `Wei-Shaw/sub2api` `main` revision
`93367b6db43315abe4f9fd9b09cbfc971b1f5ad0` was reviewed as a public
implementation reference. Its explicit one-pass effort mapping followed by a
separate ceiling is useful. Axio intentionally adds model scope, protocol
scope, endpoint-bound proof, and no-silent-conflict handling; Sub2API source
code is neither copied nor used as a dependency.

The official OpenAI reasoning guide was also refreshed on 2026-08-07. It
confirms the Responses nested `reasoning.effort` shape, a model-dependent
effort vocabulary, and the separate cost/latency implications of higher
reasoning settings.

## Verification

Focused regression:

```text
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_reasoning_transport.py \
  tests/test_reasoning_reconciliation.py \
  tests/test_benchmark_policy.py \
  tests/test_content_contracts.py -q
```

Result: `71 passed`.

Full standalone regression:

```text
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

Result: `988 passed in 194.84s`.

Compilation, diff checks, and a staged sensitive-value scan also passed before
this milestone was committed.

## Boundary

Wire acceptance and a correct map do not demonstrate that a higher effort
improves model capability. Only the separate frozen provider screening,
baseline-freeze, and independent 21-suite campaign may establish a model
quality claim.
