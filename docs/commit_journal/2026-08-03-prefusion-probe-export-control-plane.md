# Pre-Fusion Probe Export Control Plane

Date: 2026-08-03

## Milestone

The pre-Fusion report already contained the physical strict-stream probe rows,
but they were nested under `streaming_probe`. The provider evidence audit and
registry binding consume the standard `provider_probe.v1` shape. Operators
therefore needed a one-off projection script before the evidence chain could
be checked.

This milestone adds the reusable `prefusion-probe-export` command and the
`build_prefusion_probe_artifact()` API. It is an offline projection boundary:

- accepts only a ready, live-network pre-Fusion screening artifact;
- preserves the original physical probe rows and stream-contract metadata;
- records a digest of the source screening artifact;
- rejects blocked, dry-run, missing, or non-live stream inputs;
- optionally emits the existing provider-identifier-redacted evidence shape;
- performs no provider request and makes no capability or benchmark claim.

## Current r20 Evidence

The command was exercised against the current private r20 cohort. The
resulting 18-row probe projection binds to the 11-model private runtime
registry. The redacted probe, redacted registry evidence, and
`provider-probe-evidence-audit` all agree on the exact profile set and the
audit is `ready` with zero blockers. A fresh external-ranking template is bound
to the same 11-model candidate inventory and remains `template_only`; the
provider baseline freeze correctly remains blocked until complete pre-registered
external evidence exists.

This milestone does not claim that Axio is stronger than any single model. It
only closes the evidence-projection gap before the baseline-freeze gate.

## Verification

- `PYTHONPATH=src python3.11 -m pytest -q`: `939 passed`
- `PYTHONPATH=src python3.11 -m compileall -q src tests`: passed
- `git diff --check`: passed
- Real r20 offline export, registry binding, redaction, and probe-evidence
  audit: passed

No provider key, URL, raw prompt, raw provider output, or model identifier was
added to tracked files. Generated private artifacts remain under the ignored
`private/` directory.
