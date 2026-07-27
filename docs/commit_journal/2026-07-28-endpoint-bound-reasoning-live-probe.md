# Endpoint-Bound Reasoning Transport Live Probe

## Scope

Ran the first complete live reasoning-transport probe after endpoint binding
became a hard control-plane requirement. The probe used the current private
candidate registry and the configured remote API channels. It is an
operational wire-capability check only: it did not use benchmark cases,
labels, scores, prompts, or Fusion learning data.

## Result

- The selection was unbounded and covered all 28 candidate profiles.
- Every selected row carried a valid endpoint, protocol, canonical-identity,
  authentication-scheme, and transport-contract binding captured before its
  first provider request.
- The strict streamed probe produced 23 `verified`, 2 `unsupported`, and 3
  `candidate` outcomes. Indeterminate transport outcomes were retained as
  candidates rather than being misclassified as unsupported.
- `calibrate-registry` accepted the new endpoint-bound evidence without
  benchmark-derived inputs.
- `reconcile-reasoning-transport` validated the exact 28-profile source,
  calibration, and probe cohort, then wrote a distinct private registry.
  Its safe receipt has no blockers and records 25 status changes only.

## Safety Boundary

The resulting registry remains an operational candidate artifact. It does not
carry a valid pre-Fusion screening handoff and therefore cannot serve as the
formal 9-category/21-suite baseline registry. The reconciliation contract
explicitly forbids changes to model ranking, capability scores, role admission,
single-model baseline selection, and benchmark results.

Raw provider aliases, endpoint values, API credentials, request bodies, and
model outputs remain in ignored private artifacts. The safe probe,
calibration, and reconciliation receipts were checked to contain neither a
configured credential nor a raw channel URL.
