# Convergence Execution Path (Active composite r18 control plane)

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

## 当前状态（2026-08-21，composite r18 control plane）

- 工程就绪度已完成。当前 Python 3.11 全量回归为 `1076 passed, 7 skipped`；这是契约
  和集成证据，不是 provider 排名或 Fusion superiority 证据。
- r17 已自然终态并被封存为 reference-only：16/16 unit terminal，`6 completed /
  10 failed_or_blocked`，transport admission 仅 `1/8` canonical 同时通过两个 source
  family 的固定 2% gate，最低要求 3；未生成 ranking 或 baseline freeze。
- 当前唯一可继续的 successor 控制面是 r18。r18 绑定 r7 probe-bound registry，plan
  包含 16 个串行 unit、2 个 source family、8 个 canonical group、9 个 replica、
  `max_workers=1` 和固定 2% fail-fast gate；plan SHA-256 为
  `58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`，source SHA-256
  为 `3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`。
- r18 zero-network preflight 为 `preflight_ready`，`network_calls_performed=false`、
  `target_suite_calls_performed=false`；Harness pin/execution 已离线生成，但 acquisition、
  import、binding 和 convergence 仍未放行，`target_suite_calls_allowed=false`。
- 当前尚未授权 r18 live screening。启动前不能恢复 r17 checkpoint、不能使用
  `--retry-failed`、不能降低 2% gate、不能拼接 survivor subset，也不能把 r18 preflight
  当作 provider evidence。授权后仍必须完整执行 screening -> transport admission ->
  complete-pool ranking -> external top-three -> provider baseline freeze -> 同 cohort
  Harness -> 9 类 21 套 campaign -> final claim audit。
- 公共 Fusion 产品仍可独立运行：`axio-fast`、`axio-terra`、`axio-pro` 均通过四种公共
  协议提供服务；四协议公共输出边界与 request-local streaming gate 已在前一里程碑验证。

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
