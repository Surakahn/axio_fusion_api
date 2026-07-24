# Fusion Evaluation State Audit (2026-07-19)

## Intake Summary

- Launch mode: continue the existing standalone Fusion system and evaluation
  campaign; do not restart from a blank implementation.
- User intent: prove, through remote APIs and a pre-registered 9-category,
  21-suite campaign, that `axio-fast`, `axio-terra`, and `axio-pro` exceed the
  corresponding third-, second-, and first-ranked single-model baselines while
  remaining within the p50 and p95 3x latency limits.
- Current dominant phase: baseline repair and verification.
- Recommended next anchor: freeze a canonical-model baseline universe, then
  execute the official/audited benchmark imports and paired live campaign.

## Asset Matrix

| Area | Current asset | Trust level | Why | Missing proof | Recommended action |
| --- | --- | --- | --- | --- | --- |
| Standalone system | `src/axio_fusion_api/` | trusted for engineering readiness | 456 standalone tests pass; compilation, four public protocol dry checks, four provider input adapters, remote-only execution audit, and system-development readiness pass | No capability-superiority evidence | Reuse without rerunning unrelated setup |
| Provider enrollment | current calibrated private/safe registry and probe-evidence audit | trusted for the recorded live-probe cohort | 45 available profiles from three providers are probe-bound; the safe audit is ready | Live availability can drift; prices and context windows remain incomplete | Re-probe only before a formal campaign freeze |
| Canonical identity | 39 canonical groups containing 45 provider profiles | usable with verification | Runtime grouping and replica failover are implemented and regression-covered | External identity attestations are not complete for every replica | Bind all replica aliases before rank freeze |
| External ranking | private operator template and source audit | stale or conflicting before this audit | The old template counted 45 profiles although the current ranking unit is 39 canonical groups | Two common independent non-target rankings and complete identity attestations are missing | Regenerate the template by canonical group, then run a pre-registered full-pool non-target screen or obtain complete external evidence |
| Benchmark sources | mechanical-disk 21-suite cohort | usable with verification | 14 of 21 source/materialization bindings are ready and hash-bound | GPQA authorization and six official/audited harness outputs are absent | Keep gated suites blocked; complete official imports through pinned harnesses |
| Benchmark results | campaign/readiness artifacts | missing context for claims | The control plane, matrix, statistical gates, and completion audit exist | No formal target-suite provider/Axio run set; official import count is zero | Execute only after baseline freeze and strict live preflight pass |
| Running service | loopback service on port 8789 | reference only | Health and model endpoints respond and expose only the three Axio models | It is an older 37-profile, two-provider, credential-unavailable process and does not match the current 45-profile registry | Do not use it for the formal campaign; launch a cohort-bound service when credentials are injected |
| Git/worktree | top-level `axio_fusion_api/` standalone workspace | usable with verification | Fusion code remains outside the ASciFS package and imports no ASciFS runtime | The parent repository currently ignores the whole standalone directory | Preserve the boundary; source-control policy remains an operator decision |

## Reusable Assets

- The routing, orchestration, Judge, targeted feedback, Hermes MoA acting
  aggregator, replica failover, four public API surfaces, and safe trace
  contracts are reusable as the candidate system.
- The 21-suite methodology, source/case hash contracts, paired comparison
  matrix, Holm-Bonferroni correction, practical effect-size gates, Wilson
  intervals, contamination checks, and p50/p95 latency gates are reusable.
- Existing live probes are operational evidence only. They are not capability
  scores and cannot determine the top-three baseline order.

## Conflicts And Unknowns

- The running loopback service does not represent the latest registry cohort.
- The previous external-ranking template used provider profiles as ranking
  rows. The required ranking unit is the canonical model group; replicas are
  availability providers, not independent cognitive models.
- Public LiveBench, SimpleBench, and Arena snapshots do not exactly cover the
  complete current model pool. Missing rows must not be imputed from model
  names or registry priors.
- `GPQA Diamond` remains gated. No substitute dataset may be relabeled as
  GPQA, and no final 21-suite claim can omit it silently.

## Baseline Comparability Contract

- Baseline universe: every live-probed canonical model group in the frozen
  registry; all replicas remain attached to their group.
- Selection timing: before any target-suite model calls.
- Selection data: at least two independent non-target general-capability
  source families with fixed snapshots and population counts, or two pinned
  non-target official evaluations over the complete canonical pool.
- Final mapping: `axio-pro` versus rank 1, `axio-terra` versus rank 2, and
  `axio-fast` versus rank 3.
- Target-suite scores and labels cannot alter the ranking or serving policy.
- Downstream trust state: `partially_verified` until the rank freeze passes;
  current provider models are operational but not yet comparable as formal
  top-three baselines.

## Route Recommendation

1. Regenerate the external-ranking template from the current calibrated
   registry so it contains 39 canonical groups and 45 replica profiles.
2. Re-run the baseline freeze to produce a current, precise blocked receipt.
3. Complete the missing identity attestations and two-source non-target
   screening contract; do not infer ranks from aliases.
4. Re-probe and freeze the provider cohort, launch a cohort-bound gateway, and
   run strict official-harness preflight.
5. Execute paired target-suite runs only after the baseline and dataset gates
   are ready.

The intake audit does not accept or waive the baseline gate. It routes the next
work to baseline repair because all downstream superiority claims depend on a
comparable, immutable rank-1/rank-2/rank-3 reference.
