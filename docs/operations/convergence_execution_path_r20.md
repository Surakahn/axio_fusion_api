# Convergence Execution Path (Active r43)

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

1. **Pre-Fusion screening:** complete the active immutable full-pool plan for
   all admitted logical models, both independent non-target source families,
   and every registered source-model unit. The plan fixes serial execution
   (`max_workers=1`), request budget, scorer, source snapshot, and failure
   denominator.
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

## Current State (2026-08-09, r43)

- Engineering readiness is complete: the Python 3.11 regression passes `1009`
  tests, the four provider-input adapters pass dry checks, and all 12
  Axio/public-surface cells pass the network-free protocol self-test.
- The fresh r43 pre-Fusion generation cohort is terminal and ready. It
  contains the complete discovered pool after candidate filtering, strict
  three-sample streaming admission, and role-probe binding. Its private
  generation, handoff, and runtime registry artifacts contain 10 logical
  models and 10 eligible physical profiles. This is availability and
  orchestration evidence only, not a model-quality or baseline-ranking claim.
- The old `prefusion-probe-export` command intentionally accepts only the raw
  `pre_fusion_model_screening.v1` schema. Passing the r43 generation wrapper to
  it is a schema error, not a failed provider run. The explicit
  `prefusion-generation-probe-export` command now projects the nested,
  endpoint-bound `eligible_profile_bindings` into `provider_probe.v1` after
  revalidating the complete one-to-one profile set and all strict-stream
  multi-sample fields. The projection is offline and records
  `projection_network_calls_performed=false`.
- The r43 projected probe was bound to a new private copy of the r43 runtime
  registry with `registry-bind-probe`. Its redacted registry evidence and the
  generation-bound private/redacted probe artifacts passed
  `provider-probe-evidence-audit` with zero blockers. This closes the
  provider-probe evidence projection gap; it does not freeze rank 1/2/3.
- The r43 external ranking artifact remains `template_only=true` with no rank
  assignment. The complete live pool still needs two independent common
  non-target ranking source families, exact identity attestations, population
  counts, and stable source snapshots before a baseline freeze is legal.
- The r24 full-pool fail-fast attempt was stopped after a private checkpoint
  exposed duplicate MMLU-Pro case identities. Its private artifacts are
  preserved as interrupted diagnostic evidence only; no unit answer or score
  may be reused for ranking.
- The MMLU-Pro adapter now binds category, source question identity, question
  content, and options, excludes labels from identity, and rejects duplicate
  or missing case IDs before plan execution. This changes the adapter digest,
  so the next screening plan must be regenerated from a new source-manifest
  binding.
- The r25 cohort reached a terminal partial result and its transport-only
  admission receipt retained zero eligible canonical models. It is preserved
  as diagnostic evidence and cannot supply a provider baseline, a survivor
  subset, or any later cohort input.
- The r26 and r27 cohorts are retained as transport-only diagnostic evidence.
  They are not resumable, rankable, or mergeable into r43. Their partial
  answers, scores, failures, and survivor subsets remain excluded.
- Ranking conversion is fail-closed for an interrupted campaign with no
  complete cross-source candidate: it emits a template-only blocker receipt
  rather than raising or deriving a partial rank.
- The assembled 21-suite dataset and official harness manifests remain
  provenance inputs only. They do not authorize target benchmark requests
  while provider baseline screening is incomplete.

## r44 Screening Registration

The next cohort is registered at
`private/runs/2026-08-09-prefusion-cohort-r44/`. It keeps the r43
probe-bound registry immutable and uses a new source-manifest selection seed.
The provider catalog is revalidated independently through the configured
network policy. Provider slugs are normalized only for provider identity
comparison; model aliases still require an exact catalog match.

The immutable r44 plan is ready with 10 canonical groups, 10 physical
profiles, two independent non-target source families, 20 serial tasks, and
2,200 estimated provider calls. The zero-network preflight completed with
zero provider and target-suite calls. The live campaign is running serially
under the registered 90-second request ceiling and fail-fast transport
denominator. Its private checkpoints are diagnostic until every task is
terminal. No partial score, survivor subset, rank assignment, baseline
freeze, or target benchmark request may be reused or promoted.

## r43 Evidence Handoff

The r43 screening process has already exited. Use the exact private generation
artifact and do not start a provider request for this handoff:

```bash
PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  prefusion-generation-probe-export \
  --generation-file private/runs/2026-08-09-prefusion-cohort-r43/available_model_generation.r43.private.json \
  --output private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.private.json

PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  prefusion-generation-probe-export \
  --generation-file private/runs/2026-08-09-prefusion-cohort-r43/available_model_generation.r43.private.json \
  --redact-provider-identifiers \
  --output private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.safe.json

PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  registry-from-probe \
  --probe-file private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.private.json \
  --min-available-models 3 \
  --output private/runs/2026-08-09-prefusion-cohort-r43/registry.from-generation-probe.r43.private.json

PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  registry-from-probe \
  --probe-file private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.private.json \
  --min-available-models 3 \
  --redact-provider-identifiers \
  --output private/runs/2026-08-09-prefusion-cohort-r43/registry.from-generation-probe.r43.safe.json

PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  registry-bind-probe \
  --registry-file private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.r43.private.json \
  --probe-file private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.private.json \
  --min-available-models 3 \
  --output private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.probe-bound.r43.private.json

PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  provider-probe-evidence-audit \
  --private-probe-file private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.private.json \
  --private-registry-file private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.probe-bound.r43.private.json \
  --redacted-probe-file private/runs/2026-08-09-prefusion-cohort-r43/provider_probe.from-generation.r43.safe.json \
  --redacted-registry-evidence-file private/runs/2026-08-09-prefusion-cohort-r43/registry.from-generation-probe.r43.safe.json \
  --min-available-models 3 \
  --output private/runs/2026-08-09-prefusion-cohort-r43/provider_probe_evidence_audit.from-generation.r43.safe.json
```

The generated probe is a projection of already-bound evidence, not a new
probe and not a ranking input. `provider-probe-evidence-audit` must be read
before any baseline-freeze command. The r43 audit passing permits the
provider-evidence gate to advance, but the external ranking template and
official harness-import gate remain independently required.

## Change Policy Until the Gate

Only these changes are permitted before the baseline-freeze gate:

- offline manifest/harness binding and hash validation;
- documentation and operator receipts;
- isolated, tested control-plane fixes that preserve the digest of a currently
  frozen plan when their optional policy is disabled;
- isolated regression fixes proven by tests and unrelated to the active
  campaign's frozen plan or prompts;
- read-only inspection of completed private artifacts.

Do not tune fusion prompts, route weights, model tiers, screening cases,
scorers, concurrency, or benchmark decoding settings before the baseline
freeze. The r43 generation-bound projection does not alter any of those
inputs, which preserves the anti-cheating contract and keeps the next result
scientifically interpretable.
