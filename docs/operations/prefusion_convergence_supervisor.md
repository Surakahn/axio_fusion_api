# Pre-Fusion Convergence Supervisor (r43)

The production Fusion runtime and the benchmark evaluator remain separate.
This document describes the operator handoff for the completed r43 full-pool
generation cohort. It is intentionally fail-closed:

```text
r43 completed generation and strict probe binding
  -> generation-bound provider-probe evidence audit
  -> complete external ranking evidence
  -> operator baseline-freeze and official-harness gates
```

The supervisor never changes a frozen plan, retries a completed case, alters
prompts, tunes router weights, or starts target benchmark traffic. It never
selects a top-three baseline from a partial pool. Runtime logs and state belong
below `private/`; public receipts contain hashes, counts, and reason codes only.

## Current cohort

The completed cohort is
`private/runs/2026-08-09-prefusion-cohort-r43/`.

- generation artifact: `available_model_generation.r43.private.json`
- handoff artifact: `fusion_handoff.r43.private.json`
- serving registry: `runtime_registry.r43.private.json`
- external ranking template: `external_ranking_template.r43.private.json`
- generation-bound probe, bound registry, and safe audit artifacts are
  derived offline from the exact nested registry bindings

r43 contains 10 logical models and 10 eligible physical profiles after the
90-second strict-streaming and role-probe gates. It is availability and
orchestration evidence, not an external top-three ranking. The old r26/r27
cohorts are transport-only diagnostics and must not be resumed or merged.

## Evidence handoff

The r43 process has exited. Verify the offline provider evidence audit:

```bash
cd /home/he/axio_fusion_api
PYTHONPATH=src .venv/bin/python - <<'PY'
import json
from pathlib import Path

path = Path("private/runs/2026-08-09-prefusion-cohort-r43/"
            "provider_probe_evidence_audit.from-generation.r43.safe.json")
audit = json.loads(path.read_text(encoding="utf-8"))
print(audit.get("status"), audit.get("ready"), len(audit.get("blockers") or []))
PY
```

If the audit is blocked, preserve r43 and create a new private artifact after
repair; do not rewrite the r43 registry. If it is ready, stop at the external
baseline-ranking gate. The operator still needs two independent common
non-target ranking source families, exact identity attestations, source
snapshots, population counts, and a complete rank-1/rank-2/rank-3 assignment.
No target benchmark request is authorized merely because provider evidence is
ready.

The `prefusion-generation-probe-export` command is required for a generation
wrapper. The older `prefusion-probe-export` command remains restricted to raw
`pre_fusion_model_screening.v1` input and must continue to reject the wrapper.
