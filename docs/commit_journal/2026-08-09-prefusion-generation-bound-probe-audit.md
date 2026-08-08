# Generation-bound pre-Fusion probe evidence

Date: 2026-08-09

## Change

The r43 `generate-available-models` result is a ready wrapper around a
pre-Fusion registry. It is not the raw
`pre_fusion_model_screening.v1` schema consumed by the original
`prefusion-probe-export` command. Passing the wrapper to that command is a
correctly rejected schema error, but there was no explicit operator path to
project the already-bound evidence into the standard provider-probe contract.

This milestone adds `prefusion-generation-probe-export` and
`build_prefusion_generation_probe_artifact()`. The new boundary:

- accepts only a ready available-model generation artifact;
- validates the nested ready handoff and pre-Fusion registry;
- requires exact model/profile-binding set equality;
- requires text modality, live strict streaming, SSE/NDJSON framing, non-empty
  output hashes, measured latency at or below 90 seconds, and the complete
  multi-sample stability contract;
- performs no network request and records that fact explicitly;
- supports the existing provider-identifier redaction path;
- preserves the old raw-report export command's fail-closed schema contract.

The projected artifact was bound to a new private r43 registry copy and passed
the hash-only provider-probe evidence audit with zero blockers. No target
benchmark call, prompt tuning, route-policy change, or ranking assignment was
performed.

## Verification

- Python 3.11 generation/probe focused regression: `14 passed`
- Python 3.11 full standalone regression: `1009 passed, 0 failed`
- Python 3.11 compile/import gate: passed
- r43 offline generation-bound projection: 10 available physical profiles
- r43 probe-bound registry: ready, 10 live-available profiles
- provider-probe evidence audit: `ready=true`, zero blockers
- no provider network request during projection or audit
- image generation/editing registry remains a separate capability lane
- no API key, raw URL, prompt, provider output, or image bytes added to Git
