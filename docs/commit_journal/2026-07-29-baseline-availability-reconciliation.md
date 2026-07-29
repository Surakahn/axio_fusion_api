# Baseline Availability Reconciliation

## Decision

The first formal long-request admission receipt was not used as the final
baseline universe by itself. Later non-target screening units established
monotonic transport lower bounds above the frozen `0.02` failure-rate gate for
three profiles. Those profiles are excluded before provider ranking; their
partial answers and scores are not reused.

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

The subset-only admission attempt was rejected by the coverage validator
because a private receipt must bind every enabled registry profile. Each
reconciled receipt therefore preserves complete coverage and binds the
exclusion to private screening plan/task hashes and aggregate failure counts.
After three such transport-only exclusions, the current r10 plan contains 17
formal eligible logical models, 34 source-candidate units, two independent
non-target source families, and a frozen single-worker condition.

## Non-Claims

This gate is an operational availability decision, not a model-quality rank.
It does not select Axio baselines, alter Fusion prompts or routing, or support
a benchmark superiority claim. Ranking conversion remains blocked until the
new r8 campaign reaches a complete terminal state with every unit passing.
