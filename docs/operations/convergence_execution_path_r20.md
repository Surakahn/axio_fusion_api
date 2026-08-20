# Convergence Execution Path (Active composite r17)

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

## 当前状态（2026-08-20，composite r17）

- 工程就绪度已完成。本次代码变更后的 Python 3.11 全量回归为 `1074 passed, 7
  skipped`；这是契约和集成证据，不是 provider 排名或 Fusion superiority 证据。
- r17 是唯一活动的 immutable non-target screening cohort。冻结 plan 绑定 r7
  probe-bound registry，包含 16 个串行 unit、2 个 source family、8 个 canonical
  group、9 个 replica、`max_workers=1` 和固定 2% transport fail-fast gate。plan
  SHA-256 为 `336fa9c4f81223622a3f94d21cc249b4d20ba9b392a18a2e1aba54fbc5ba6565`，
  source SHA-256 为 `7ba7fc8816cbd32881b47419e2d26d2fa26f7460d551b4d1c747195f8ae15b56`。
- live screening、同 cohort supervisor 和 lineage watcher 仍是唯一活动的筛选/控制进程。
  safe state 为 `running`，当前 `3 completed / 6 failed_or_blocked`，
  `ready_for_ranking=false`，`target_suite_calls_performed=false`；当前 state
  SHA-256 为 `fdce96ba6a1d35568c2f9f50d1b21ffb5ce10d32de8a1130c9e513ef3e1d425c`。
- 离线 Harness 控制面已有 6 个 hash-only pin 和 ready execution plan，但 acquisition/
  import 尚未完成，同 cohort convergence 仍停留在 `next_gate=screening`，
  `target_suite_calls_allowed=false`，尚未放行 target call。Harness 就绪不授权 target
  call，也不能替代 provider baseline 证据。
- 不恢复 partial checkpoint，不拼接 completed subset，不使用猜测排名或历史 cohort。
  screening terminal 后唯一合法顺序是：transport admission -> complete-pool ranking
  -> external top-three evidence -> provider baseline freeze -> 同 cohort 官方/审计
  Harness -> 9 类 21 套 campaign -> final claim audit。
- 公共 Fusion 产品仍可独立运行：`axio-fast`、`axio-terra`、`axio-pro` 均通过
  Chat Completions、Responses、Anthropic Messages 和 Gemini surface 提供服务。本次
  四协议公共输出边界与 request-local streaming gate 已记录在当前 commit journal，
  没有改动 r17 frozen 输入。

## Historical r44 Screening Registration

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

## 历史 r43 Evidence Handoff

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
official harness-import gate remain independently required. This section is
historical evidence only; it is not the active r17 execution input.

## 当前 Gate 变更政策

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
freeze. The current public-output normalization change does not alter any of
those inputs, which preserves the anti-cheating contract and keeps the r17
result scientifically interpretable.
