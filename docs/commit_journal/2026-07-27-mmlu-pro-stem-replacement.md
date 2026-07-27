# MMLU-Pro STEM Replacement Control-Plane Milestone

## Scope

The current provider cohort remains unable to freeze the required external
rank-1/rank-2/rank-3 baselines. GPQA Diamond also remains gated. This milestone
therefore adds only an explicitly labelled, deterministic downloadable
replacement asset; it does not alter serving prompts, routing, model weights,
provider admission, or benchmark claim thresholds.

## Implementation

- Added `benchmark_replacements.py` with pinned MMLU-Pro source metadata.
- Added a deterministic STEM selector with six categories and 100 cases per
  category.
- Enforced the pinned raw snapshot SHA-256 and byte count at the CLI boundary.
- Wrote private standardized JSONL and hash-only control-plane receipts with
  atomic publication and restrictive file permissions.
- Added explicit 21-suite manifest replacement semantics. A valid replacement
  retains the canonical science slot for paired accounting but carries its own
  dataset identity; an implicit or malformed substitution fails closed.
- Preserved prompt projection and label separation through the existing
  benchmark validator.

## Verification

- Real MMLU-Pro snapshot: 12,032 rows, 4,144,185 bytes, pinned SHA-256 verified.
- Standardized output: 600 rows, six categories balanced at 100 each.
- Dataset validator: 600 valid, zero invalid, zero duplicate case hashes, zero
  suspected label leakage, zero prompt-contract violations.
- Replacement manifest: 21 slots, one explicit `mmlu_pro_stem` replacement for
  `gpqa_diamond`.
- Targeted regression: `22 passed`.
- Manifest and benchmark regression selection: `2 passed, 374 deselected`.
- Python compilation and `git diff --check`: passed.

## Gate State

The benchmark readiness artifact recognizes the replacement as a ready
science-slot dataset and reports 15 ready suites instead of 14. Six remaining
official/audited harness assets and the provider baseline freeze continue to
block formal live evaluation. No benchmark model calls or superiority claim
were made in this milestone.
