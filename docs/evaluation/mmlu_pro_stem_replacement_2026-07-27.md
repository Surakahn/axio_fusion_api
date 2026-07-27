# MMLU-Pro STEM Replacement Asset: 2026-07-27

## Decision

The current GPQA Diamond artifact is still unavailable under its gated access
contract. The user-approved fallback is therefore prepared as an explicit
replacement for the `gpqa_diamond` science slot. It is not GPQA, its results
must never be reported as GPQA results, and it does not relax the provider
baseline or final-claim gates.

The replacement keeps the 21-slot evaluation matrix structurally complete while
preserving the dataset identity in every readiness and campaign artifact.

## Pinned Source

- Dataset: `TIGER-Lab/MMLU-Pro`
- Source: `https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro`
- Split: `test`
- Snapshot commit: `b189ec765aa7ed75c8acfea42df31fdae71f97be`
- Raw file: `test-00000-of-00001.parquet`
- Raw bytes: `4,144,185`
- Raw SHA-256: `0e24a191921c2f453518a537a8b2117bd137e7714d4ef1565e9ba06c1ecb9ad8`

The raw and standardized benchmark files live only on the mechanical-disk
benchmark workspace, outside this Git repository.

## Replacement Versions

The initial `mmlu-pro-stem-v1` asset remains a historical diagnostic asset
only. It is useful for debugging the replacement pipeline, but it cannot be
used in a formal campaign: a previous non-target provider-ranking exercise
selected MMLU-Pro rows, and v1 did not prove that its target cases were
disjoint from those screening rows.

The only formal-campaign candidate is now `mmlu_pro_stem` version
`mmlu-pro-stem-v2-screening-disjoint`:

- biology: 100 cases
- chemistry: 100 cases
- computer science: 100 cases
- engineering: 100 cases
- math: 100 cases
- physics: 100 cases

The 600 cases are selected by deterministic SHA-256 ordering over the public
category, question, options, source-row identity, pinned source revision, and
the fixed seed `axio-mmlu-pro-stem-v2-screening-disjoint-20260727`. Before
selection, the builder deterministically reconstructs the pre-registered
non-target screening selection from its private source manifest and excludes
all selected MMLU-Pro source rows. Gold answers are not used for exclusion,
selection, or ordering. The standardized rows retain the gold option letter
only for the evaluator-owned scoring boundary. MMLU-Pro permits variable option
counts; the adapter accepts three through ten options and validates the answer
letter against that row's option count.

The v2 receipt binds the screening manifest digest, the common raw snapshot
digest, excluded and selected source-row-set digests, selected count, and a
zero-overlap assertion. It exposes no source-row IDs, questions, labels, model
outputs, credentials, or endpoints. Readiness fails closed if any of these
bindings is missing, if the raw snapshots differ, if overlap is non-zero, or if
the evaluated JSONL hash/case count does not match the receipt.

## Mechanical-Disk Artifacts

The historical v1 diagnostic cohort is:

`/mnt/storage/axio_fusion_benchmarks/replacements/mmlu_pro_stem_20260727/`

It must not be used for a formal campaign.

The screening-disjoint v2 cohort is:

`/mnt/storage/axio_fusion_benchmarks/replacements/mmlu_pro_stem_screening_disjoint_20260727/`

Important v2 files:

- `mmlu_pro_stem.jsonl`: 600-case private standardized dataset
- `mmlu_pro_stem_replacement.safe.json`: source, selection, output hash, and
  screening-disjointness receipt
- `mmlu_pro_screening_exclusion.private.json`: private source-row exclusion
  manifest, never a campaign artifact
- `mmlu_pro_screening_exclusion.safe.json`: count-and-hash-only exclusion receipt
- `validation.safe.json`: validator result
- `dataset_manifest.replacement.json`: 21-suite manifest with an explicit replacement row
- `case_hash_manifest.safe.json`: hash-only case-set binding for the replacement
- `source_manifest.template.json`, `source_manifest.prepared.safe.json`, and
  `source_manifest.bound.safe.json`: replacement-aware source bindings
- `source_manifest.bound.validation.safe.json`: source-manifest validation
- `readiness.safe.json`: diagnostic readiness projection; its remaining
  campaign blockers are unrelated to v2 disjointness

Observed validation:

- rows: 600
- valid cases: 600
- invalid cases: 0
- duplicate case hashes: 0
- suspected label leakage: 0
- prompt contract violations: 0
- ready for scoring: true

The screening exclusion set contains 112 source rows. The v2 selected set has
zero overlap with it. The target JSONL has no source-row identity field.

The standardized dataset SHA-256 is recorded in the private receipt. No raw
questions, labels, model outputs, credentials, or endpoints are present in the
Git change.

## Control-Plane Semantics

The replacement manifest contains a row with:

- `suite_id`: `mmlu_pro_stem`
- `replaces_suite_id`: `gpqa_diamond`
- `benchmark_slot_id`: `gpqa_diamond`
- `explicitly_not_gpqa`: `true`

The evaluation control plane normalizes this row to the canonical GPQA slot
for paired case accounting, while retaining `benchmark_dataset_id=mmlu_pro_stem`
and the replacement disclosure in readiness, methodology, run, and campaign
artifacts. An implicit or malformed substitution remains unnormalized and
fails readiness closed.

## Current Gate

This closes the screening-disjoint replacement preparation only. It does not
start the live 21-suite campaign. The campaign remains blocked until the
complete provider pool has an externally pre-registered rank 1/2/3 freeze and
the remaining official or audited harness imports are present. No Axio
superiority claim is made from this replacement asset or from the current
provider survivors.
