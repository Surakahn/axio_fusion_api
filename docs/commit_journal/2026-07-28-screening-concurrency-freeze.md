# Screening Concurrency Freeze

## Finding

The non-target provider screening plan froze task order and transport
implementation, but it did not freeze the per-unit case fanout. A resumed or
new invocation could therefore execute the same hash-bound task matrix with a
different `max_workers` value. That changes upstream queueing, rate-limit
pressure, and response timing, so it is an experimental-condition change, not
an operational-only setting.

## Control

The screening plan and campaign schemas now use v3. Each plan carries a
bounded `max_workers` value, included in `plan_digest_sha256`; the default is
one worker and the accepted range is one through sixteen. The live runner
uses the planned value when no override is supplied and rejects any invalid or
different override before provider I/O. Campaign checkpoints bind that value
on resume, and ranking conversion rebuilds the current plan with the same
frozen value before accepting a completed campaign.

Earlier plans without the field are not compatible with v3 and fail closed.
They must be replaced with a newly registered plan; their partial results are
not merged into a new cohort.

## Verification

Regression coverage verifies that changing the worker limit changes the plan
digest, a runtime mismatch performs zero provider calls, a rehashed checkpoint
with a changed worker limit is rejected, a missing plan field is rejected, and
a fixed-concurrency completed campaign still converts through the strict
ranking contract.
