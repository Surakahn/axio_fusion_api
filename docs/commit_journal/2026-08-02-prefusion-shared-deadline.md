# Pre-Fusion Shared Deadline Propagation

Date: 2026-08-02

## Change

The live pre-Fusion workflow now carries one shared monotonic deadline through
reasoning transport probes and strict streaming admission. The deadline is
enforced before each provider request, inside multi-sample and role-probe
loops, and at the isolated process boundary used for live HTTP calls.

When the budget is exhausted, the control plane records a bounded hash-safe
failure/indeterminate receipt and does not issue a late request. A blocked
cohort cannot replace the active registry.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /home/he/.local/bin/python3.11 -m pytest -q tests`
- Result: `863 passed`
- Targeted deadline and protocol suite: `169 passed`
- `python3 -m py_compile src/axio_fusion_api/providers.py src/axio_fusion_api/model_screening.py`
- `git diff --check`

## Boundary

This is a control-plane reliability fix. It changes neither model capability
ranking nor benchmark data, prompts, labels, or evaluation outcomes. It does
not add local model execution and does not persist credentials or provider
output.
