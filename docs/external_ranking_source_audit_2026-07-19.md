# External Ranking Source Audit (2026-07-19)

This note records the source audit for the current private 43-profile live
registry. It is a pre-campaign evidence note, not a baseline freeze and not a
model-quality claim.

## Sources Checked

- Artificial Analysis model leaderboard:
  `https://artificialanalysis.ai/leaderboards/models`
  It exposes a broad Intelligence Index and model identity metadata, but the
  page includes target-suite signals such as GPQA Diamond and Humanity's Last
  Exam in its model records. It is therefore not admissible as a non-target
  ranking source for this campaign.
- LiveBench latest release:
  `https://livebench.ai/table_2026_06_25.csv`
  This is an independent, contamination-aware benchmark leaderboard and is a
  valid source candidate only for the model identities it actually ranks. It
  does not cover the complete current provider pool.
- SimpleBench public leaderboard:
  `https://simple-bench.com/static/js/leaderboard-data.js`
  This is an independent general-reasoning leaderboard and is outside the 21
  target suites. It also covers only a subset of the current provider pool.
- OpenRouter model catalog:
  `https://openrouter.ai/api/v1/models`
  This is useful for public model identity and availability metadata, but its
  catalog and ranking pages do not provide an independent general-capability
  rank for every configured profile.
- LMSYS/Chatbot Arena endpoints were checked as a second broad ranking
  candidate. The public Arena leaderboard is reachable through the configured
  proxy and is a human-preference ranking source independent of LiveBench, but
  its current embedded model table does not exactly identify the complete
  provider pool, so no Arena rank was imported.

## Decision

The external ranking template remains intentionally unfilled. The current
registry cannot yet satisfy the final-claim contract requiring two independent
non-target ranking source families for every live-probed profile, a stable
population count per source, and a channel-to-canonical-model attestation.

No rank is inferred from model names, provider aliases, latency, price,
capability priors, Artificial Analysis target-suite fields, or partial-source
coverage. In particular, the illustrative ordering
`gpt-5.6-sol > gpt-5.5 > gpt-5.6-terra` is not recorded as a freeze until the
complete-pool evidence contract is satisfied.

## Required Next Evidence

1. Obtain a second independent non-target capability ranking that covers all
   37 canonical models represented by the 43 live profiles, or run two pinned
   non-target official evaluations over the complete canonical pool. The
   source must expose a dated rank and population for every candidate without
   imputing unranked models.
2. Bind each provider alias to a canonical model identity with a dated official
   model card/release or provider attestation.
3. Fill the private ranking template before any target-suite provider calls and
   run `benchmark-provider-baseline-freeze` plus its evidence audit.

Until those conditions hold, benchmark execution may only be planned or
diagnosed; no final Axio-vs-single-model superiority claim is authorized.

## Mechanical-Disk Acquisition Receipt

On 2026-07-19 the non-target source snapshots were downloaded outside the
repository under
`/mnt/storage/axio_fusion_benchmarks/non_target_ranking_sources/`:

- LiveBench table snapshot `table_2026_06_25.csv`: SHA-256
  `9294ea8dbe836f7268976b160acd35fa27f1f7c1ce47e46691022d6c6e48dd5c`.
- SimpleBench leaderboard `leaderboard-data.js`: SHA-256
  `823c935abed0309f0fd3d65ec47e659142b13ac5373498094da8d402c1702506`.
- SimpleBench public question file `simple_bench_public.json`: SHA-256
  `4ea0bb96b35f61c97dbf5a7dc059986398441f0cbb17fa709ae2b0e9ba4f76e4`.
- SimpleBench repository README: SHA-256
  `866c1a9692c04713953e5853c9e898f2a60fbaab21e11485415db954d06a1`.
- Arena leaderboard HTML snapshot `chatbot_arena_2026_07_19/leaderboard.html`:
  SHA-256 `93313652fd2b510d70491ae8e1259d6018e9a25e51e96eef232200816ad38059`.

The downloaded SimpleBench public file contains only 10 labeled questions;
it is therefore an acquisition/source audit artifact, not a sufficiently
powered full-pool ranking run. The public LiveBench table contains 40 listed
model rows, but exact identity coverage does not match all 43 live provider
profiles. These facts preserve the baseline blocker: no fuzzy model-name
mapping, hidden-answer inference, or missing-row imputation is admissible.

The Arena snapshot was checked with exact case-insensitive model-identity
matching only: 2 of the 37 current canonical model identities occur exactly in
the embedded model/name fields. Variants such as effort suffixes, provider
prefixes, or renamed aliases were not silently mapped. Arena is therefore a
useful independent source candidate, but it does not currently satisfy the
complete-pool requirement.

## Official LiveBench Snapshot

To make the next non-target screening step reproducible, the official
LiveBench dataset repositories and scorer source were also fetched through the
configured system proxy on 2026-07-19. The snapshot is kept outside this
repository at
`/mnt/storage/axio_fusion_benchmarks/non_target_ranking_sources/`.

- Official scorer/harness source archive: `livebench_repo_2026_07_19_complete/livebench_4bf3d6f4.tar`, from commit `4bf3d6f4cb37fa8dc3967dd1b124fef5d4099635`, SHA-256
  `78955f58ada65946f81a8a59234a14e61335b56c9dbf2a5a81d9a8273e19814e`.
- Official test parquet row counts: reasoning 200, math 368, coding 128, data analysis 150, instruction following 400, and language 190; total 1,436 cases.
- Official leaderboard answer/judgment parquet row counts: model answer 93,715 and model judgment 60,372.
- Each repository tree response, parquet file, and source archive has a SHA-256 recorded alongside the acquisition directory; the source commit and Hugging Face tree metadata are retained for later case/source binding.

This acquisition is preparation evidence only. It does not rank the current
provider pool and no target-benchmark prompt, answer, or label was used to
select a provider baseline. The next valid operation is a pre-registered
full-pool run using the pinned official scorer, with exact model identity and
provider-replica attestations recorded before any target-suite campaign.
