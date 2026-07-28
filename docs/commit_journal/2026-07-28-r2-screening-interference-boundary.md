# R2 Screening Interference Boundary

## Decision

The `current_channel_enrollment_20260728_full_cohort_r2` non-target
provider-screening run is retained as a private engineering and transport
diagnostic only. It is not eligible to create an external ranking manifest,
a rank-1/rank-2/rank-3 provider-baseline freeze, or an Axio capability claim.

## Why The Boundary Changed

While the run was active, an operator performed unregistered protocol
diagnostics against the same remote channel to classify recurring HTTP 400
responses. The diagnostics used fixed generic text and one already-selected
non-target screening prompt. They did not use target-suite prompts, labels,
scores, or outputs, and no raw diagnostic payload, response, endpoint, model
identifier, or credential was written to this repository.

Those calls can still alter a shared upstream channel's short-term queue,
rate-limit state, or latency. Their exact effect cannot be separated from the
pre-registered screening transport observations after the fact. Treating the
run as formal ranking evidence would therefore overstate what it proves.

## What Remains Valid

- The frozen R2 plan and all completed private unit receipts remain useful for
  diagnosing protocol compatibility, failure classes, latency, and admission
  behavior.
- Failed, blocked, and completed units remain in the private denominator; no
  result may be removed or converted into a successful score.
- The incident does not transfer target benchmark material into Fusion routing,
  prompts, calibration, or learning.

## Required Next Cohort

Before a formal provider-baseline freeze:

1. Correct or explicitly calibrate the observed provider transport behavior.
2. Generate a new pre-registered plan after the transport/configuration
   change; R2 answers and scores cannot be reused.
3. Run the full candidate pool in an isolated collection window. Apart from
   the plan's own calls, no diagnostic, smoke, benchmark, or manual provider
   requests may share the configured channel.
4. Preserve the complete terminal denominator, verify all source-family
   coverage, and run the strict screening-to-ranking conversion before any
   top-three assignment.

This is an evidence-boundary correction, not a statement about model quality
or a mechanism for selecting survivors.

## Terminal Diagnostic Snapshot

R2 reached its terminal state with its original v2 contract: 30 planned
units, 17 completed units, and 13 failed units. The safe aggregate recorded
transport-failure-rate excess for 13 units and no scoreable response for four
units; those reason counts are not mutually exclusive. `ready_for_ranking`
remained false.

This terminal denominator is retained only for protocol and transport failure
analysis. It does not select surviving candidates, establish a capability
ordering, or contribute any score to a later cohort. The replacement formal
cohort must use the v3 plan contract with a newly frozen worker limit and an
isolated provider-traffic window.
