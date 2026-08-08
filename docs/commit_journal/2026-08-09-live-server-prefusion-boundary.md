# Live Server Pre-Fusion Boundary

## Finding

The historical `scripts/run_server.py` wrapper supplied a default
2026-07-28 calibrated registry and loaded it with `require_prefusion=False`.
That path could start a live HTTP engine from a legacy pool even though the
current r26/r27 baseline cohorts are partial and no current rank freeze is
trusted.

## Change

The wrapper now requires the operator to set
`AXIO_FUSION_REGISTRY_PATH` explicitly and loads that artifact with
`require_prefusion=True`. A missing, partial, stale, or binding-invalid
registry stops startup before the live engine is constructed. Diagnostic and
offline test paths remain available through explicit non-production APIs.

## Verification

- Python compilation passed for the updated entrypoint.
- The r26 and r27 artifacts were read offline and both reported partial
  transport-failure gates with `ready_for_ranking=false`.
- No screening process was running at reconciliation time; neither partial
  cohort is resumed or promoted.
- Offline telemetry shows r26 is dominated by provider timeout and transport
  errors with a small 5xx/empty-output tail; r27 is dominated by timeout and
  empty-output failures. This is treated as a transport gate lesson, not a
  quality or ranking signal.
- No provider or benchmark request was made.
- Full benchmark execution remains blocked until a complete provider cohort,
  external baseline freeze, and official/audited harness imports exist.

## Security

The change removes an implicit serving path. It does not persist or print
credentials, provider URLs, prompts, or provider outputs.
