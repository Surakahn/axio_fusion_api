# MMLU-Pro Screening-Disjoint Replacement Gate

## Scope

This change repairs the evaluation boundary, not the Fusion runtime. A historic
non-target provider-ranking campaign selected rows from the same pinned
MMLU-Pro snapshot later used as the fallback for the unavailable GPQA Diamond
slot. Reusing an overlapping row in a target comparison could leak model
selection evidence into the formal evaluation set.

## Decision

`mmlu-pro-stem-v1` remains readable as a diagnostic artifact but is rejected
for a formal campaign. `mmlu-pro-stem-v2-screening-disjoint` is the only
accepted replacement version. It is valid only when it carries a verified,
hash-bound exclusion proof generated from the pre-registered non-target source
manifest and uses the identical raw MMLU-Pro snapshot.

## Implementation

- Reconstruct the selected historic MMLU-Pro source-row identities from the
  private source manifest without loading prompts, labels, provider outputs, or
  rank results into any safe artifact.
- Produce a private exclusion manifest plus a public-safe count-and-hash
  receipt. The safe receipt never includes source-row IDs.
- Exclude those identities before deterministic category-stratified selection.
  Gold answers cannot influence exclusion, selection, or ordering.
- Bind the replacement receipt to the exact standardized JSONL digest and case
  count, then bind the manifest row to the same receipt facts.
- Fail readiness closed for an old version, absent/malformed proof, source
  snapshot mismatch, non-zero overlap, or a dataset hash/count mismatch.

## Mechanical-Disk Evidence

The v2 asset lives under
`/mnt/storage/axio_fusion_benchmarks/replacements/mmlu_pro_stem_screening_disjoint_20260727/`.
It contains 600 target rows, an exclusion count of 112, and a selected-overlap
count of zero. Dataset validation reports 600 valid rows, no duplicates, no
label-leakage suspicion, and no prompt-contract violation. These files stay
outside Git; only this method and code are versioned.

## Verification

- The replacement unit suite verifies v1 rejection, v2 normalization,
  label-blind selection, exclusion-manifest tamper rejection, snapshot mismatch
  rejection, and replacement JSONL hash tamper rejection.
- The readiness projection recognizes the v2 GPQA slot replacement as valid;
  the campaign remains blocked only by independent baseline, source, and
  official-harness gates.

## Non-Claims

This does not authorize GPQA access, select provider baselines, execute a
benchmark model call, change Fusion prompts or routing, or establish any Axio
quality or latency claim.
