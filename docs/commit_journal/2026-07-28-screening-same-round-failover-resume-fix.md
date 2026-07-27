# Screening Same-Round Failover Resume Fix

## Finding

The first bounded live unit of the frozen non-target screening campaign
completed all selected cases and recorded several recoverable transport
failures that were resolved by another replica in the same initial round. A
subsequent no-network resume check correctly preserved the checkpoint but
incorrectly rejected that unit with retry-contract errors.

The execution behavior was valid. The verifier treated every retryable failed
attempt as requiring a later retry round, even when a later replica in the
same round had already returned a visible answer. That would make a legitimate
same-canonical failover impossible to resume or convert into ranking evidence.

## Correction

`_screening_retry_contract_errors` now distinguishes two cases:

1. A visible same-round completion terminates the case. Earlier retryable
   failures remain in telemetry and do not require a retry receipt.
2. A real subsequent round must still contain exactly the retryable failed
   replicas from the preceding unanswered round, with its fixed-backoff
   receipt. A missing required retry remains invalid.

A focused regression test covers a retryable first-replica failure followed by
a successful second-replica response in round one. Existing fixed-second-round
and tampered-backoff tests remain in force.

## Evidence And Campaign Consequence

The repaired verifier revalidated the already-written private pilot unit with
no errors using a no-network diagnostic that emitted only aggregate error
codes. It did not print prompts, labels, outputs, model identifiers, endpoint
values, or credentials.

The screening plan binds its adapter implementation hash to both execution and
retry-contract verification code. Therefore the prior `r3` plan and its pilot
unit are retained only as private audit evidence and are not eligible for
ranking or baseline freeze after this correction. The next live campaign must
be freshly frozen from the unchanged pre-registered source manifest and run
without reusing the old score.

## Verification

```text
PYTHONPATH=src python3.11 -m pytest -q tests/test_baseline_screening.py
47 passed
```
