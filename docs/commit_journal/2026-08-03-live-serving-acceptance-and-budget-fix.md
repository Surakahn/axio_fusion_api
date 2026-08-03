# Live Serving Acceptance and Initial Fusion Budget Fix

Date: 2026-08-03

## Scope

This milestone validates the public streaming boundary against the current
private provider registry and fixes two serving-runtime defects found while
doing that validation. It is not a benchmark run and it does not establish a
quality or model-superiority claim.

## Public protocol evidence

The offline protocol self-test passed for all public surfaces. The first
strict live matrix exercised all 12 cells (three Axio model names multiplied
by Chat Completions, Responses, Anthropic Messages, and Gemini GenerateContent)
and passed 10/12. The two failures were provider execution timeouts, not
protocol framing or conversion errors.

The failures were then isolated with one model at a time:

- `axio-fast`: 4/4 strict streaming surfaces passed;
- `axio-terra`: 4/4 strict streaming surfaces passed in the initial matrix;
- `axio-pro`: 4/4 strict streaming surfaces passed on an isolated retry.

Each isolated success observed a real upstream provider call, HTTP 200, an
event-stream content type, non-empty streamed text, and the surface-native
terminal event. The initial two transient failures remain recorded as
operational evidence; they are not erased by the retries. No raw response,
prompt, provider identifier, URL, or credential is in the safe receipts.

## Runtime defects found and fixed

### Failure receipt schema drift

When a live Fusion call failed before finalization, the operator receipt row
did not contain all fields required by its own digest projection. The CLI then
raised `KeyError` while reporting a provider failure. The failure row now
matches the success row's stable field contract with explicit false/zero
defaults, so provider errors remain safe, inspectable failures.

### Optional control-stage reservation consumed the initial panel

The live deliberation probe explicitly supplied six total calls. The router
correctly represented this as a complete five-call initial plan (three
experts, Judge, Synthesizer) with zero optional fallback allowance. The
runtime nevertheless reserved two cross-model control-stage fallback slots.
Those dynamic reservations reduced the expert phase to an unusable window and
caused the initial panel to fail before a candidate could complete.

The runtime now checks the route's explicit `fallback_call_allowance` before
reserving cross-model stage failover. With no optional allowance, it preserves
the initial Fusion shape and its mandatory Judge/Synthesizer reservations.
Optional stage failover remains available when the route explicitly admits
the required capacity.

## Complete Fusion gate result

The current provider cohort has not yet produced a complete live
`provider_judge_synthesis` result:

- with six calls, `axio-terra` and `axio-pro` reached only partial candidate
  recovery and correctly skipped finalization;
- with ten calls, `axio-terra` reached three candidates and attempted Judge,
  but both same-model and cross-model Judge attempts failed within the bounded
  latency window;
- the corresponding `axio-pro` attempt had insufficient surviving candidates
  and did not enter Judge.

These are explicit serving-readiness blockers, not benchmark scores. The
runtime returned degraded or incomplete receipts and never promoted them to a
complete Fusion result. `axio-fast` is validated through its bounded direct
cascade and four public streaming surfaces; the complete Judge/Synthesizer
deliberation smoke is intentionally scoped to the Terra and Pro tiers.

## Verification

This change includes regressions for the complete failure-row digest contract
and for preserving an explicit initial Fusion call shape when optional stage
fallback capacity is zero. The full regression suite must pass before this
milestone is committed.

The next engineering gate is a fresh provider health/ranking decision or a
controlled retry against the current cohort that produces a complete Judge and
Synthesizer result within the three-times direct-model latency ceiling. Only
after that serving gate passes should the independent 9-category, 21-suite
benchmark campaign begin.

All live evidence remains under the ignored `private/` directory. No API key,
token, provider URL, raw prompt, raw provider output, or local model weight is
added to the repository.
