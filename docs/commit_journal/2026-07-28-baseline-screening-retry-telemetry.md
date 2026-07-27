# Baseline Screening Retry Telemetry

## Purpose

The independent provider-baseline screening campaign must distinguish a wrong
answer from an unavailable or malformed provider response. This change makes
that distinction observable without allowing retries to select a better answer
after scoring.

## Frozen Contract

- A source may use no more than two total exception-attempt rounds: the
  initial attempt and one eligible retry round.
- Every canonical model begins with its fixed, rotated replica order. A failed
  replica may fail over to another replica in that first round, but replicas
  remain availability paths rather than independent votes.
- A second round includes only replicas that returned a classified recoverable
  failure: timeout, network transport, rate limit, provider 5xx, empty output,
  or stream/protocol failure. Client-side request rejection such as HTTP 400
  may still fall through to another replica, but cannot repeat on the same
  replica.
- The inter-round delay is fixed by the source manifest. There is no jitter,
  answer-dependent delay, score-dependent retry, or retry after a valid answer.
- A scorer failure can be resumed only by rescoring the already stored private
  output. It never causes a second provider request for that answered case.

## Evidence Boundary

Private attempt rows retain only hashed profile identity, round number, latency,
a closed failure class, a whitelisted provider error code, and a valid HTTP
status. Safe case and unit receipts aggregate those fields, retry-round counts,
and recovered transport failures. They do not retain provider error messages,
URLs, credentials, raw prompts, labels, or outputs.

The source ranking metric is explicitly conditional on the pre-registered
transport-failure gate: terminal missing observations block a unit when their
rate exceeds the threshold and are excluded from the scored-answer denominator.
They are not silently converted into zero-valued answers.

## Verification

The targeted tests cover HTTP 400, rate limiting, HTTP 5xx, timeout, stream
protocol failure, fixed backoff receipts, replica failover, safe telemetry, and
the rule that a wrong answer is requested exactly once. The full project suite
also runs before this change is committed. Plan generation and preflight remain
zero-network operations; no provider baseline rank or Axio superiority claim is
created by this work.
