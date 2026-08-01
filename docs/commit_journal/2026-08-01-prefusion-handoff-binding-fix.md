# Pre-Fusion Handoff Binding Fix

## Scope

Corrected two control-plane joins exposed by the first complete live
pre-Fusion screening run. The change does not alter model quality ranking,
Fusion prompts, routing heuristics, benchmark data, or provider credentials.

## Reasoning Probe Cohort

The reasoning transport probe now persists sorted SHA-256 profile hashes for
both the complete candidate cohort and the exact selected cohort, plus a digest
for each set. The selection policy carries the same values. Handoff validation
checks the set digests, candidate-to-selected subset relation, research
inventory binding, counts, duplicate rows, and live evidence before allowing a
reasoning contract to be required. This prevents a research Agent's
`status=unknown` from masking a model-local candidate declaration that was
correctly sent to the real endpoint probe.

## Operational Role Probe

When the strict role probe has no target for a profile, the profile now gets a
hash-safe empty receipt with `skipped_no_role_targets`. The receipt is an
explicit coverage statement, not a capability pass; it cannot grant Critic,
Judge, or Synthesizer access. Registry validation can therefore distinguish a
legitimate non-target from missing or tampered evidence.

## Verification

- Focused screening, reasoning transport, reconciliation, and enrollment:
  `136 passed`.
- Full Python 3.11 regression: `842 passed in 179.07s`.
- `git diff --check` passed.
- Historical private r7 artifacts were not modified; they remain diagnostic
  evidence generated before this contract and require a fresh screening run.

No benchmark superiority claim is made by this control-plane fix.
