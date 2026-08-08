# External Ranking Source Audit: r43

This is a source-coverage and identity audit for the current r43 provider
cohort. It is not a ranking assignment, a baseline freeze, or a model-quality
claim. No target-suite request was made during this audit.

## Scope

The audit is bound to the current r43 registry and its complete live-probed
candidate inventory:

- registry digest (probe-bound serving candidate):
  `b13069373f8880a5f5960c0b0f076146904c395101f77c158976f20b45f85885`
- candidate inventory digest:
  `945912b3f0ac07546d7ccdc7cc9d064fc3001ab7739b9d9ec10a1999e2d047c5`
- logical canonical groups: `10`
- eligible physical profiles: `10`
- retrieval date: `2026-08-09`
- network policy: `auto`, proxy `127.0.0.1:10808`

Candidate identities are represented by their private candidate hashes in the
safe audit receipt. The audit uses literal case-insensitive identity matching
only. Provider prefixes, effort suffixes, precision suffixes, and punctuation
changes are diagnostic variants, not accepted identity mappings.

## Snapshots

The snapshots are stored outside the repository on the mechanical disk:

`/mnt/storage/axio_fusion_benchmarks/non_target_ranking_sources/r43_2026_08_09/`

| Source family | Type | Source snapshot | Ranked population | Snapshot SHA-256 |
| --- | --- | --- | ---: | --- |
| LiveBench | independent leaderboard | `table_2026_06_25.csv` | 39 | `5d0b4484897677e60f2a0b1801fe20ad038ab60d74f80dfb0c7676de5370d448` |
| Chatbot Arena | independent human-preference leaderboard | `arena_leaderboard.html` | 384 | `def6eb563b2568b595548c7be0c83072b402bfbfbd2e08ff221c54ba741e28ff` |
| SimpleBench | independent general-reasoning leaderboard | `leaderboard-data.js` | 93 | `d3b351934c64938307903be926d920e91819613a98765b2170e5068ca86e1d7a` |

The source locator hashes are:

- LiveBench: `e70f40005b36b4c8a560a2be1d4b089aa891a86d8db04a6bcb6a276562b0ede4`
- Chatbot Arena: `f1a01fbf34b0e3d7d7be56aa7d40118d3cf2e60403043a8539027d47de713bd2`
- SimpleBench: `8a4303eb39421d263474efd10e38d11d209df0ad1e457813f453ec299fd63e0f`

The Arena HTML contains 678 table rows, of which 384 have a numeric overall
rank. The SimpleBench snapshot contains 95 rows, of which 93 are ranked model
rows. These ranked populations, rather than unranked duplicate rows, are the
population counts recorded for any future source evidence.

## Coverage Result

| Source family | Literal exact candidate coverage | Diagnostic variant coverage | Complete r43 pool |
| --- | ---: | ---: | --- |
| LiveBench | 0/10 | 5/10 | No |
| Chatbot Arena | 1/10 | 7/10 | No |
| SimpleBench | 1/10 | 3/10 | No |

The diagnostic variants include the following classes of mismatch:

- GPT entries expose reasoning-effort suffixes such as `-max` or `-xhigh`.
- GLM entries may omit the provider namespace or add an effort suffix.
- NVIDIA entries may use hyphens instead of the configured slash namespace or
  add a precision suffix such as `-bf16`.
- SimpleBench uses display names rather than the configured channel model
  identifiers.

These variants may be considered only after a dated, source-backed
channel-alias-to-canonical-identity attestation has been independently
verified and bound before pre-registration. They are not imported by this
audit, and they cannot increase exact coverage.

## Decision

The r43 ranking template remains intentionally unchanged:

```text
template_only=true
ranking_assignment_present=false
```

No source family currently covers all 10 canonical groups. Consequently there
are no two common independent source families, no complete-pool normalized
rank aggregation, and no legal rank-1/rank-2/rank-3 baseline freeze.

The following blockers remain active:

- `external_ranking_source_complete_pool_coverage_missing`
- `external_ranking_common_source_family_coverage_below_minimum`
- `external_ranking_exact_identity_attestation_missing`
- `external_ranking_source_pre_registration_not_ready`
- `external_ranking_official_identity_evidence_incomplete`

No rank is inferred from a model-name suffix, provider convention, latency,
capability prior, partial leaderboard, or the ordering suggested in user
examples. No target benchmark result is used to fill missing rows.

## Required Next Evidence

1. Obtain at least two independent, common, non-target general-capability
   ranking families that each cover all 10 exact canonical groups, with stable
   snapshots and population counts.
2. Bind every configured channel alias and every observed source alias to its
   canonical identity using dated official model-card/release evidence or a
   provider attestation. The binding must exist before pre-registration.
3. Record an explicit declaration that the source ranking did not use the
   21-suite target material or target results.
4. Run the ranking validator against the complete r43 inventory. Only its
   deterministic normalized-percentile aggregation may select ranks 1, 2, and
   3.

If the public sources cannot satisfy these conditions, the admissible
alternative is two pre-registered, independent, non-target evaluations run
over the complete live-probed pool with the same identity and source
attestation requirements. A partial source union is not sufficient.
