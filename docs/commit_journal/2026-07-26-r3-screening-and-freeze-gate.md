# r3 Screening and Freeze Gate

## Milestone

Completed a new, independently identified provider-stability and non-target
baseline-screening cohort after the r2 refresh. The work stayed inside the
independent evaluation boundary and did not alter production prompts, routing,
registry code, or benchmark target data.

## Evidence

- The strict operational admission covered 45 profiles, 15 attempts per
  profile, three repetitions, strict streaming, and a 90-second hard limit.
- Every profile received the complete 15-attempt workload coverage.
- Eleven profiles passed the formal zero-failure admission gate.
- The new screening plan was pre-registered from 11 canonical candidates, two
  independent source families, 22 units, and 2,420 provider calls.
- All 22 units completed execution and private-artifact digest verification.
- Seven units passed the source transport/scoring gate; 15 were rejected.
- The complete case denominator was 2,420, with 1,613 scored responses and
  807 transport failures. No scorer error was silently converted into a
  wrong answer.
- Exact probe evidence binding passed, including private/safe profile sets,
  source counts, API-format counts, and leakage checks.

## Gate Result

The ranking conversion and provider baseline freeze remain blocked. The
current formally eligible pool does not satisfy the required exact-cohort
portfolio coverage for judge, synthesizer, structured-output, independent
answer-claim verification, and provider/API diversity. The 7 surviving units
were not promoted to a provider top three.

The 9-category, 21-suite target benchmark was not started because its
pre-registered rank-1/rank-2/rank-3 provider baseline is not available. This
preserves the paired-comparison contract and prevents an unsupported Axio
superiority claim.

## Private Receipts

The full receipts remain local under the r3 private campaign directory and
are excluded from Git. Safe documentation records only aggregate counts and
gate outcomes; it does not contain credentials, provider names, model ids,
raw prompts, benchmark labels, or provider outputs.
