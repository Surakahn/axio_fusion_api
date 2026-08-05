# Endpoint-Bound Vision Input On Text Profiles

## Scope

This milestone completes the correction that visual input is a capability of
ordinary text or multimodal models. It is not a separate Fusion model pool or
an image registry. Image generation and image editing remain the only image
operations with a separate serving lane.

## Change

- Added an endpoint-bound visual-input probe for Chat Completions, Responses,
  Anthropic Messages, and Gemini GenerateContent.
- The probe sends one in-memory PNG using each protocol's native image shape,
  requires strict SSE or NDJSON framing, checks an exact marker, and applies
  the shared 90-second response ceiling.
- Promoted visual evidence is stored on the ordinary text/multimodal profile
  as `vision_probe_status` and `vision_capability_source`; it does not affect
  capability axes, ranking, quality priors, or benchmark scores.
- Failed, unsupported, indeterminate, stale-endpoint, non-framed, fallback,
  zero-frame, and slow visual probes are closed against image-input routing.
  A profile with indeterminate visual evidence remains eligible for ordinary
  text requests.
- Added calibration, dynamic enrollment, file enrollment, atomic runtime
  refresh, standalone CLI, and production service CLI propagation for visual
  probe controls and safe receipts.
- Kept raw image bytes, probe prompts, provider outputs, endpoints, model
  identifiers, and credentials out of safe artifacts and repository changes.

## Verification

- Full standalone regression: `980 passed in 204.33s`.
- Visual/enrollment/runtime focused regression: `94 passed in 4.01s`.
- `python3 -m py_compile src/axio_fusion_api/*.py` passes.
- `git diff --check` passes.
- The changed diff contains no credential or private-key pattern. The only
  tracked-tree pattern match is the intentional sensitive-file rule in
  `.gitignore`.

## Boundary And Limits

The probe proves only the tested endpoint's minimal image-input wire path and
does not claim OCR, chart understanding, document parsing, video, or general
model quality. No live supplier probing or external benchmark traffic is
started by this milestone. Those remain separate follow-up gates after the
Fusion runtime is committed and pushed.
