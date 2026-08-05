# Full-pool screening successor: r23 to r24

This milestone records a control-plane correction made before provider
baseline ranking. It does not change Fusion prompts, routing weights, model
tier policy, benchmark cases, or public API behavior.

## Evidence

- The first full-pool plan used one coherent 22-canonical-model registry and
  the same live probe source throughout.
- Its immutable plan had 44 source-model units, two independent non-target
  source families, serial execution, and a complete failure denominator.
- The first model unit finished with 105 scored cases and 3 transport failures
  out of 108. The next unit reached 3 completed cases and 4 repeated 90-second
  transport timeouts in its first 7 cases.
- The no-fail-fast run was stopped after its private checkpoint was preserved.
  Its interrupted receipt remains diagnostic evidence and is not eligible for
  ranking, baseline freeze, or benchmark comparison.

## Successor contract

The r24 successor was generated from the same private registry, live probe
source, source manifest, candidate pool, source-selection seed, task order,
and serial worker bound. It does not reuse any r23 answer, score, checkpoint,
or provider output.

The only policy change is pre-registered transport fail-fast: after the
registered 2% transport-failure rate becomes impossible to pass, pending cases
are represented as transport failures in the complete denominator. This
reduces avoidable 90-second requests while preserving an unbiased exclusion
receipt. Quality scores and answer content are not used by this gate.

## Gate

The r24 plan and zero-network preflight passed before its live process was
started. It remains closed to provider baseline freeze until every planned
unit reaches a terminal state and the resulting pool is converted through the
existing ranking, identity, and probe-evidence gates.

No target benchmark call was made by either cohort. The formal `cli-proxy-api-plus`
service was not stopped, restarted, or modified.
