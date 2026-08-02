# Hermes Advisory Repair Budget Gate

## Scope

This milestone closes a production runtime tail-latency issue in the
standalone Axio Fusion orchestrator. The issue was not provider availability:
after the initial expert wave had already produced a viable Fusion quorum and
at least one usable Hermes reference, the runtime could still spend another
provider call trying to fill a named advisory reference seat. That optional
call competed with the mandatory Judge and acting Synthesizer stages.

## Change

- Treat a completed Hermes reference as sufficient for the acting aggregator's
  minimum reference contract.
- Skip optional Hermes enrichment when the Fusion evidence quorum is already
  met and a reference output exists.
- Preserve panel repair when the evidence quorum is missing, when a required
  role is missing, or when no reference output exists and bounded recovery is
  still meaningful.
- Preserve the mandatory Judge/Synthesizer reservations, stage-local
  deadlines, Hermes fail-closed completion contract, and provider replica
  failover behavior.
- Record `optional_hermes_enrichment_skipped` and its reason in both the
  in-memory trace and the redacted execution receipt, including remaining
  advisory reference gaps.

## Verification

```text
PYTHONPATH=src uv run pytest -q
900 passed in 198.98s
```

The targeted panel and Hermes regression set also passed after the change.
The next operational step is a fresh live streaming smoke against the current
private registry. This milestone makes no benchmark-quality or
single-model-superiority claim; those remain gated behind the independent
official benchmark campaign and frozen external baseline comparison.

## Security Boundary

No endpoint, API key, provider credential, raw prompt, raw provider output, or
private registry content is stored in this journal or the Git commit.
