# Bounded Streaming Retry and Fusion Latency Guard

Date: 2026-08-03

## Milestone boundary

This milestone hardens the serving runtime at the provider and mandatory
control-stage boundary. It is an engineering reliability milestone, not a
benchmark result and not a claim that Axio is stronger than any individual
provider model.

The public product boundary remains the three fixed models:

- `axio-fast`
- `axio-terra`
- `axio-pro`

The benchmark runner remains an independent consumer of that public boundary.
It is deliberately not imported into request-time Fusion execution.

## Failure observed in live evidence

Strict provider streaming uses a watchdog to close a response when a hard
deadline is reached. Some HTTP response context managers then surfaced a bare
stdlib `ValueError` while closing the interrupted stream. The exception did
not carry the provider error contract, so the orchestration layer could treat
it as an ordinary application failure.

The runtime could consequently spend the remaining request window on serial
same-model retries. Mandatory Judge and Synthesizer recovery and cross-model
fallback then compounded the delay. A nominal 90-second request could reach
the public deadline without producing a trustworthy complete Fusion result.

## Engineering decisions

### 1. Normalize transport boundary failures

The provider stream reader converts watchdog-close `ValueError` failures into
the same bounded provider error contract used by other transport failures:

- `fusion_request_deadline_exhausted` when the hard deadline was consumed;
- `provider_stream_transport_error` for a non-deadline stream transport
  failure.

Only allowlisted error codes and classes cross the diagnostic boundary. The
exception message, provider URL, model name, prompt, output, and credentials
are never persisted in the receipt.

### 2. Do not repeat a physically exhausted candidate

When a candidate branch has already consumed its hard stream deadline, the
same canonical model is not retried serially inside that branch. The runtime
can still use an independently budgeted cross-model panel repair or mandatory
control-stage failover when its own reservations admit the attempt. This keeps
provider replicas as availability redundancy rather than accidentally turning
one slow model into an unbounded serial panel.

### 3. Enforce the three-times direct-model latency guard at execution time

For a provider Judge/Synthesizer route, the runtime derives a single-model
baseline from the screened direct candidate p95 latency. The effective Fusion
deadline is bounded by:

```text
min(caller_deadline, 3 * direct_candidate_p95)
```

A small transport floor prevents an unrealistically optimistic probe from
creating an unusable sub-second stream window. If no valid direct baseline is
available, the runtime does not invent one and preserves the caller deadline
while recording that the guard could not be applied.

The applied budget is exposed only through a redacted runtime receipt with
bounded numeric fields. A deadline-limited or incomplete control stage cannot
be promoted to a complete Fusion answer or cache entry.

## Verification

The implementation includes regressions for:

- a context-manager `ValueError` at the strict streaming boundary;
- hard-deadline candidate retry suppression;
- the three-times direct-model latency ceiling;
- safe Judge/Synthesizer stage diagnostics and sensitive-field absence.

Expected verification for this milestone:

```text
PYTHONPATH=src pytest -q                         933 passed
PYTHONPATH=src python3 -m compileall -q src tests
git diff --check
```

The real private registry is read only from the ignored `private/` boundary.
No private channel configuration, API key, provider URL, raw prompt, raw
provider output, or local model weight is part of this milestone.

## Remaining gate after this commit

The next gate is controlled live protocol acceptance using the existing
private registry. It must independently exercise Chat Completions, Responses,
Anthropic Messages, and Gemini GenerateContent for all three Axio model names,
checking strict streaming framing, cancellation, public error projection, and
bounded latency. A live failure must remain visible as a failure or explicit
degraded result; it must not be reported as a complete Fusion success.

Only after serving acceptance is complete will the independent 9-category,
21-suite benchmark campaign run. Any unavailable or unauthorized benchmark is
marked gated or replaced with a documented, downloadable alternative. No
superiority claim is made until the same controlled inputs and scoring method
produce comparable results for Axio and the selected single-model baselines.
