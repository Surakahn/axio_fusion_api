# Pre-Fusion Role-Probe Contract Migration

Date: 2026-08-03

## Problem

The latest role-specific latency calibration added the `primary_solver` role
and repeated strict-streaming samples with role-level p50/p95 telemetry. The
existing r20 private registry was generated immediately before that change:
it used seven operational roles and one role-probe request per targeted role.
The registry contained valid physical streaming evidence and valid model and
catalog projections, but the loader rejected it because the role list had
changed. The runtime therefore failed closed before entering Fusion routing.

## Change

The registry validator now recognizes three explicit role-probe generations:

- the current eight-role repeated-sample contract;
- the r20 seven-role single-sample contract;
- the earlier three-role single-sample contract.

The two historical shapes are migration/rollback inputs only. They retain the
original strict stream, output hash, latency ceiling, profile binding, role
admission, catalog, logical replica, and digest checks. They do not satisfy the
current role-level stability contract and are not silently upgraded in memory.

The current eight-role shape must declare two to five samples per role,
require every sample to succeed within 90 seconds with strict framed streaming,
and provide a sample receipt hash plus p50/p95 latency for every targeted role
result. Removing those fields makes the registry invalid.

## Verification

- The real private r20 registry passes `validate_prefusion_registry_handoff`.
- The real private r20 registry loads 11 profiles through `load_registry`.
- Targeted role-contract regression: 3 passed.
- Full Python 3.11 regression suite: 897 passed in 185.08 seconds.
- `python3.11 -m py_compile src/axio_fusion_api/registry.py` passed.
- `git diff --check` passed.

No provider request, benchmark case, benchmark label, raw prompt, raw
provider output, URL, credential, or local model weight is added to the
repository by this change. Private runtime evidence remains under the ignored
`private/` directory.
