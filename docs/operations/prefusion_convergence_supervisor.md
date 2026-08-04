# Pre-Fusion Convergence Supervisor

The production Fusion runtime and the benchmark evaluator remain separate.
This utility only closes the current provider-screening handoff:

```text
r20 live screening
  -> one ranking conversion
  -> r21 fail-fast successor only when conversion is not ready
  -> one r21 ranking conversion
  -> operator baseline-freeze and official-harness gates
```

It does not change a frozen plan, retry a completed case, alter prompts, tune
router weights, or start target benchmark traffic. It reads the operator
credential file into the child process environment and never writes credential
values, provider outputs, or raw prompts to a repository artifact. Runtime logs
and state belong below `private/`.

## Current cohort

Start it only once, using the PID of the already running r20 process:

```bash
cd /home/he/axio_fusion_api
PYTHONPATH=src nohup setsid python3.11 \
  scripts/continue_prefusion_convergence.py \
  --r20-pid 3460559 \
  --r20-state private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening_state.private.json \
  --r20-plan private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening_plan.r20.safe.json \
  --r20-registry private/runs/2026-08-02-prefusion-cohort-r20/fusion-runtime-registry.exported-bound.private.json \
  --source-manifest /mnt/storage/axio_fusion_benchmarks/non_target_ranking_campaigns/full_pool_2026-07-20/source_manifest.private.json \
  --r20-private-root private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening.private \
  --r20-private-probe-file private/runs/2026-08-02-prefusion-cohort-r20/provider_probe.exported.private.json \
  --r20-output private/runs/2026-08-02-prefusion-cohort-r20/baseline_screening.safe.json \
  --r20-ranking-output private/runs/2026-08-02-prefusion-cohort-r20/external_provider_ranking.r20.screened.private.json \
  --r21-plan private/runs/2026-08-04-prefusion-cohort-r21/baseline_screening_plan.r21.failfast.safe.json \
  --r21-private-root private/runs/2026-08-04-prefusion-cohort-r21/baseline_screening.private \
  --r21-state private/runs/2026-08-04-prefusion-cohort-r21/baseline_screening_state.private.json \
  --r21-output private/runs/2026-08-04-prefusion-cohort-r21/baseline_screening.safe.json \
  --r21-ranking-output private/runs/2026-08-04-prefusion-cohort-r21/external_provider_ranking.r21.screened.private.json \
  --lock-file private/runs/prefusion-convergence-supervisor.lock \
  --max-r20-recoveries 1 \
  --interval-seconds 300 \
  >>private/runs/prefusion-convergence-supervisor.console.log 2>&1 &
echo $! > private/runs/prefusion-convergence-supervisor.pid
```

The script validates that the supplied PID still contains the r20 plan
fragment. A changed or reused PID aborts without starting a successor. The
lock prevents duplicate supervisors. `baseline-screening-to-ranking` returns
exit code `2` for a valid but blocked conversion; the supervisor intentionally
reads the generated safe manifest and uses its
`screening_conversion_ready` field instead of treating that return code as a
process error.

If the bound r20 process exits while its state is still non-terminal, the
supervisor uses the same plan, state, private root, and checkpoint once to
resume the campaign. It never adds `--retry-failed`; after the configured
recovery budget is exhausted it fails closed for operator review.

When the conversion is ready, the supervisor stops at the baseline-freeze
gate. It does not select the top three models automatically. The next action
is the documented provider-freeze validation followed by the official harness
gate. If conversion is not ready, r21 is started with its immutable,
pre-registered serial fail-fast plan; cancelled cases remain in the complete
failure denominator.
