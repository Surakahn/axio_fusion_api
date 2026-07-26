# Current Cohort Screening Gate

## Milestone

Completed the current independently registered provider-baseline screening
campaign and ran its strict screening-to-ranking conversion. The work stayed
inside the independent evaluation boundary. It did not alter production
prompts, routing logic, serving registries, or target benchmark data.

## Evidence

- Enrollment discovered 126 logical model entries and retained 31 profiles
  after the strict text probe.
- Operational admission covered 31 profiles with 15 streaming attempts each,
  for 465 attempts under the hard 90-second response ceiling.
- The admission receipt recorded 369 passed attempts, 72 ordinary failures,
  and 24 latency-ineligible attempts; 11 profiles passed the formal
  zero-failure gate.
- The fixed screening plan contained 11 canonical candidates, two independent
  source families, 22 units, and 2,420 provider calls.
- All 22 screening units reached a terminal result: 6 passed and 16 were
  rejected by transport-failure-rate or no-score gates.
- The complete case denominator was 2,420, with 1,444 scored responses and
  976 transport failures. No scorer error was silently converted into a
  score.
- The campaign used bounded concurrency and did not use `--retry-failed`.

## Gate Result

The campaign ended in `partial` state and the ranking conversion returned
`screening_conversion_ready = false`. The blockers include non-complete
campaign eligibility, failed or incomplete source units, and incomplete
candidate source coverage. The artifact is template-only and contains no
provider rank assignment.

The provider baseline freeze was not attempted, and the formal 9-category,
21-suite target benchmark was not started. No Axio superiority claim was
made. Selecting the six passing units as a post-hoc top-three pool would
violate the complete-pool contract, so those units remain evidence of the
current channel's screening behavior rather than a ranking.

## Next Gate

A new independently identified provider cohort is required before ranking can
be frozen. It must satisfy complete candidate coverage across both source
families, the exact registry/probe binding, the portfolio and independent
verifier requirements, and the provider/API diversity contract. Only after
that freeze may the paired Axio-vs-rank-1/2/3 21-suite campaign start.

## Private Receipts

Raw campaign state, prompts, outputs, provider identifiers, and credentials
remain local under the current cohort's private directory and are excluded
from Git. This journal records aggregate gate evidence only.
