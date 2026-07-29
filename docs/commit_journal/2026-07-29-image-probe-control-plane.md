# Image Probe Control Plane

## Scope

This milestone closes the operational admission loop for the isolated image
lane. It remains independent from text Fusion and does not modify ASciFS.

## Implemented

- Added a real `responses_image_generation` transport for generation through
  `/responses` and the native `image_generation` tool shape.
- Kept multipart editing bound to `images_api`; a Responses image declaration
  cannot issue an unsupported edit request.
- Added the `image-probe` CLI workflow with dry-run/live modes, fixed
  non-benchmark generation and edit controls, strict streaming observation when
  declared, operation-level status, error classification, and the 90-second
  hard timeout.
- Added offline `redact-image-probe` hash-only evidence generation.
- Added `image-probe-bind`, which requires a complete profile cohort, current
  endpoint hashes, matching transport paths, and every declared operation to
  pass before promoting `candidate/not_run` to `verified/passed`.
- Added documentation and focused tests for Responses wire shape, probe
  isolation, redaction, endpoint binding, and promotion.

## Verification

```text
16 image tests passed
769 full repository tests passed
python3.11 compileall passed
```

The bind command writes a new private registry only on a ready cohort. A
partial, stale, failed, transient, or endpoint-mismatched artifact leaves the
source registry unpromoted.

## Data boundary

Probe prompts, source PNG bytes, base64 outputs, raw provider responses,
credentials, and endpoint values are not persisted. Private artifacts retain
only the serving aliases needed for operator binding; safe receipts retain
hashes, timing, statuses, and stream metadata.
