# Registry Admission Diagnostic

## Scope

Add operator visibility for the pre-Fusion registry boundary without changing
the serving admission rule. Invalid or stale serving artifacts must continue
to produce zero routable profiles.

## Change

Added `registry_load_diagnostic()` and the network-free
`registry-diagnostic` CLI command. The diagnostic reuses
`validate_prefusion_registry_handoff()` and the same generated-registry
normalization path as `load_registry()`. It reports:

- stable validator reason codes;
- raw row and effective profile counts;
- hash-only profile-set and registry-path bindings;
- safe readiness and pre-Fusion validation projections;
- explicit secret/raw-provider-output persistence flags.

The CLI exits non-zero for blocked artifacts and writes the safe receipt
without exposing the registry path or provider/model identifiers. It cannot
promote, rewrite, or bypass a registry.

## Evidence

- A synthetic invalid pre-Fusion registry reports
  `prefusion_registry_binding_not_ready` and role-coverage reasons while
  retaining `effective_profile_count=0`.
- The actual r41 serving artifact reports its binding, catalog, probe-binding,
  and role-coverage mismatches with a blocked exit status.
- The r42 candidate artifact also remains blocked when
  `--require-prefusion` is requested.
- The full standalone regression after this change is `999 passed, 0 failed`.
- No provider or benchmark network request was made.

## Security

No API key, raw endpoint, model alias, prompt, or provider output is written
to the diagnostic receipt or this journal.
