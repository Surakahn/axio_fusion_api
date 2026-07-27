# Endpoint-Bound Reasoning Reconciliation

## Milestone

Added an auditable control-plane boundary for carrying per-model reasoning
transport calibration into a new private Axio serving registry. This is a
runtime capability change, not a model-quality, routing-rank, or benchmark
change.

## Problem Addressed

A provider/model alias can remain stable while an operator changes the channel
endpoint behind its environment variable. Reusing a prior `reasoning_effort`
or `reasoning.effort` probe merely because aliases match could send a
provider-specific request field to a different implementation.

## Design

- Each new reasoning probe now carries a hash-only binding over the profile,
  canonical identity, API protocol, resolved endpoint, auth scheme, and
  declared reasoning transport contract. The binding is frozen before its
  first provider request, so a later channel retarget cannot relabel live
  evidence.
- Runtime enrollment and local registry calibration independently validate the
  binding before accepting a probe row. They retain `candidate` when an
  endpoint changed or a legacy artifact has no binding.
- `reconcile-reasoning-transport` requires an exact source/calibration profile
  set, one complete unbounded live probe row per candidate, matching endpoint
  binding, and strict streaming probe evidence before it writes a new private
  registry.
- The operation is atomic, forbids in-place source registry replacement, and
  changes only reasoning transport status. It preserves existing ranking,
  capability, role-admission, and benchmark boundaries.
- If the source is a valid pre-Fusion registry, the output must remain valid
  under the pre-Fusion handoff validator.
- The operator receipt contains only hashes, counts, status classes, and safe
  reason codes. It contains no endpoint values, model identifiers, raw prompts,
  provider outputs, or credentials.

## Verification

- New reconciliation, endpoint-retargeting, legacy-artifact rejection,
  nonpositive-timeout rejection, atomic output, local-calibration protection,
  pre-Fusion handoff preservation, and CLI coverage were added.
- Focused reasoning transport, reconciliation, calibration, and pre-Fusion
  regression: `27 passed`.
- Full standalone regression: `714 passed in 136.05s` under Python 3.11.
- Python 3.11 compile check, CLI command discovery, and `git diff --check`
  passed.

## Deliberate Boundary

The existing historical reasoning-probe cohort predates endpoint bindings. It
is retained as diagnostic evidence but cannot be reconciled into a different
registry. A future live probe is required after this change. No provider
baseline was frozen and no performance or superiority claim was made.
