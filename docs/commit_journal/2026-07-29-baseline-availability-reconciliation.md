# Baseline Availability Reconciliation

## Decision

The first formal long-request admission receipt was not used as the final
baseline universe by itself. A later non-target screening unit established a
monotonic transport lower bound above the frozen `0.02` failure-rate gate for
one profile. That profile is excluded before provider ranking; its partial
answers and scores are not reused.

## Evidence Boundary

- The exclusion uses only strict-stream transport telemetry from the
  non-target screening workload.
- The observed failure count already exceeded the threshold even if every
  unobserved case had succeeded, so the availability decision is monotonic.
- No target benchmark prompt, label, score, answer, or quality judgment was
  used.
- The reconciled private admission receipt keeps all enabled profiles covered;
  the excluded row remains present and is explicitly marked `ineligible`.

## Re-registration

The first subset-only admission attempt was rejected by the coverage validator
because a private receipt must bind every enabled registry profile. The
reconciled receipt preserves complete coverage and binds the exclusion to the
private screening plan/task hashes and aggregate failure counts. It then
produced a fresh r8 screening plan with 19 formal eligible logical models, 38
source-candidate units, two independent non-target source families, and a
frozen single-worker condition.

## Non-Claims

This gate is an operational availability decision, not a model-quality rank.
It does not select Axio baselines, alter Fusion prompts or routing, or support
a benchmark superiority claim. Ranking conversion remains blocked until the
new r8 campaign reaches a complete terminal state with every unit passing.
