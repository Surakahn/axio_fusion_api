# R20 Convergence Execution Path

This document is the canonical execution path for the current Axio Fusion
milestone. It is intentionally short and operational. New provider channels,
new fusion algorithms, and benchmark-driven prompt changes are out of scope
until this path reaches a terminal gate.

## Product Boundary

Axio is a remote-API orchestration service. It loads no local model weights and
does not train a model. The active product surface remains:

- `axio-fast`: direct or bounded light verification under the latency guard.
- `axio-terra`: selective complementary references with bounded consensus.
- `axio-pro`: expert references, Judge, targeted verification, and
  Synthesizer when the deadline and cost budget permit.

The provider plane may contain arbitrary channels and any of the four supported
wire formats. Provider replicas with the same canonical model identity are one
logical model and are used for load balancing and failover only.

## One-Way Gates

The following order is the only path to a formal quality claim:

1. **Pre-Fusion screening:** complete the immutable r20 plan for all 11
   admitted logical models, both independent non-target source families, and
   all 22 units. The plan fixes serial execution (`max_workers=1`), request
   budget, scorer, source snapshot, and failure denominator.
2. **Ranking conversion:** after the process reaches a terminal state, run
   `baseline-screening-to-ranking` once against the exact plan, state, source
   manifest, and private probe binding. Every failure stays in the denominator.
3. **Baseline freeze:** accept only a complete, externally evidenced,
   registry-bound rank 1/2/3 mapping. The mapping is derived from the complete
   screened pool; it is never manually replaced with a guessed leaderboard or
   with the user's expected model order.
4. **Official harness gate:** use the assembled dataset manifest and the pinned
   six-harness manifest. A file or repository checkout is not a score import;
   LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench require the
   corresponding audited run imports with identical case hashes and decoding
   bindings. GPQA remains blocked without authorized access and is reported as
   the declared replacement/blocker, never relabelled.
5. **Independent live campaign:** run exactly the frozen Axio/baseline matrix
   through all four public streaming surfaces. The evaluator is a separate
   consumer of the Axio gateway; it is not part of the Fusion runtime and does
   not feed prompts, labels, scores, or routing updates back into production.
6. **Claim audit:** require API-surface parity, paired case-level statistics
   with multiplicity correction, practical effect thresholds, contamination
   checks, and p50/p95 latency no more than `3x` the corresponding single-model
   baseline. If any gate fails, publish a diagnostic result and a bounded
   shadow-only improvement proposal; do not claim superiority.

## Current State (2026-08-05)

- Engineering readiness is complete: the Python 3.11 regression passes `982`
  tests, the four provider-input adapters pass dry checks, and all 12
  Axio/public-surface cells pass the network-free protocol self-test.
- The r24 full-pool fail-fast attempt was stopped after a private checkpoint
  exposed duplicate MMLU-Pro case identities. Its private artifacts are
  preserved as interrupted diagnostic evidence only; no unit answer or score
  may be reused for ranking.
- The MMLU-Pro adapter now binds category, source question identity, question
  content, and options, excludes labels from identity, and rejects duplicate
  or missing case IDs before plan execution. This changes the adapter digest,
  so the next screening plan must be regenerated from a new source-manifest
  binding.
- The next cohort must use the same full-pool registry and source families
  only after a zero-network preflight authenticates the new plan, schedule,
  task order, and adapter digest. It remains the only route to provider
  baseline ranking and freeze.
- The assembled 21-suite dataset and official harness manifests remain
  provenance inputs only. They do not authorize target benchmark requests
  while provider baseline screening is incomplete.

## Terminal Action

When the screening process exits, inspect the state and run the following
command with no retry or overwrite flag:

```bash
PYTHONPATH=src python3.11 -m axio_fusion_api.cli \
  --registry private/runs/2026-08-02-prefusion-cohort-r20/fusion-runtime-registry.exported-bound.private.json \
  baseline-screening-to-ranking \
  --plan private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening_plan.r20.safe.json \
  --campaign-state private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening_state.private.json \
  --source-manifest /mnt/storage/axio_fusion_benchmarks/non_target_ranking_campaigns/full_pool_2026-07-20/source_manifest.private.json \
  --private-root private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening.private \
  --private-probe-file private/runs/2026-08-02-prefusion-cohort-r20/provider_probe.exported.private.json \
  --output private/runs/2026-08-02-prefusion-cohort-r20/external_provider_ranking.r20.screened.private.json
```

`screening_conversion_ready=false` is a valid terminal blocker, not a partial
baseline. In that case preserve the complete evidence, repair the provider
availability or screening contract in a new cohort, and keep the benchmark
campaign closed. `screening_conversion_ready=true` permits baseline-freeze
validation, but still does not bypass the official harness-import gate.

## Change Policy Until the Gate

Only these changes are permitted before the r20 terminal action:

- offline manifest/harness binding and hash validation;
- documentation and operator receipts;
- isolated, tested control-plane fixes that preserve the digest of a currently
  frozen plan when their optional policy is disabled;
- isolated regression fixes proven by tests and unrelated to the active
  campaign's frozen plan or prompts;
- read-only monitoring of the active process.

Do not tune fusion prompts, route weights, model tiers, screening cases,
scorers, concurrency, or benchmark decoding settings while this campaign is
running. That separation preserves the anti-cheating contract and keeps the
next result scientifically interpretable.
