# Pre-Fusion Convergence Supervisor

The production Fusion runtime and the benchmark evaluator remain separate.
This document describes the operator handoff for the active full-pool screening
cohort. It is intentionally fail-closed:

```text
r25 live screening
  -> one ranking conversion after terminal state
  -> transport-only successor admission if conversion is blocked
  -> a newly generated immutable cohort, if enough canonical models remain
  -> operator baseline-freeze and official-harness gates
```

The supervisor never changes a frozen plan, retries a completed case, alters
prompts, tunes router weights, or starts target benchmark traffic. It never
selects a top-three baseline from a partial pool. Runtime logs and state belong
below `private/`; public receipts contain hashes, counts, and reason codes only.

## Active cohort

The current cohort is
`private/runs/2026-08-05-prefusion-cohort-r25-full-pool-failfast/`.
It has an existing live process and watcher:

- screening PID: `screening.pid`
- screening state: `baseline_screening_state.live.private.json`
- watcher log: `ranking-watcher.private.log`
- ranking output: `external_provider_ranking.r25.screened.private.json`

Do not start another supervisor, run a manual provider request, or launch a
successor while this PID is alive. The watcher performs exactly one ranking
conversion after the process reaches a terminal state. A valid but blocked
conversion is expected to return a non-zero command status; the authoritative
decision is its `screening_conversion_ready` field, not the shell exit code.

## Terminal handoff

After the live PID exits, verify the state and read the ranking receipt before
any downstream action:

```bash
cd /home/he/axio_fusion_api
python3 - <<'PY'
import json
from pathlib import Path

path = Path(
    "private/runs/2026-08-05-prefusion-cohort-r25-full-pool-failfast/"
    "baseline_screening_state.live.private.json"
)
state = json.loads(path.read_text(encoding="utf-8"))
print(state.get("status"), state.get("ready_for_ranking"))
PY
```

The ranking conversion must be bound to the exact r25 plan, source manifest,
registry, private probe, and private unit root. The canonical command is kept
in [convergence_execution_path_r20.md](convergence_execution_path_r20.md)
and must not be run while the PID is still alive.

If `screening_conversion_ready=true`, stop at the baseline-freeze gate. The
operator must still validate the externally evidenced rank mapping, provider
probe audit, identity attestations, and official/audited harness imports.
No benchmark request is authorized merely because ranking conversion passed.

If `screening_conversion_ready=false`, preserve the complete r25 evidence and
run the transport-only admission command once, after terminal state:

```bash
PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  --registry <r25-bound-registry> \
  baseline-screening-transport-admission \
  --plan private/runs/2026-08-05-prefusion-cohort-r25-full-pool-failfast/baseline_screening_plan.safe.json \
  --campaign-state private/runs/2026-08-05-prefusion-cohort-r25-full-pool-failfast/baseline_screening_state.live.private.json \
  --max-transport-failure-rate 0.02 \
  --min-canonical-models 3 \
  --output <transport-admission-receipt>
```

This command may use only transport terminal evidence. It must not read scores,
answers, labels, or benchmark outputs to select eligible profiles. A ready
receipt is only an input to a newly generated plan; it does not resume r25 and
does not establish provider ranking. If fewer than three canonical models
remain, the provider configuration or live availability must be repaired and a
fresh full-pool plan generated before ranking can reopen.
