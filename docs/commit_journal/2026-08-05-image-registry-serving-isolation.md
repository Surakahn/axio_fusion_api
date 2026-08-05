# Image Registry Serving Isolation

## Scope

This milestone completes the serving boundary for provider image models. Image
generation and editing are a sibling capability lane; they are not text Fusion
profiles and must not enter Axio deliberation, ranking, or text benchmark
calibration.

## Change

- Added a separately promoted image registry loader with a closed admission
  contract: image-only profiles, a ready image-probe binding, and at least one
  verified operation are required.
- Added explicit image registry wiring to standalone and runtime service
  startup, including `--image-registry` and
  `AXIO_FUSION_IMAGE_REGISTRY_PATH`.
- Kept image routing, provider failover, proxy policy, and the 90-second
  deadline available without allowing image profiles to replace or downgrade
  the text pre-Fusion registry.
- Added health output that reports the image lane independently from text
  registry readiness.
- Added TokenAPIs `gpt-image-2` as a candidate image profile in the public
  configuration template. It remains non-serving until the private verified
  image registry is explicitly promoted.

## Verification

- Full standalone regression: `959 passed in 197.60s`.
- Image and registry isolation tests pass, including promotion, mixed-profile
  rejection, health reporting, and unavailable-capability behavior.
- `git diff --check` passes.
- Sensitive-value scan over the repository source and documentation surface
  found no API keys, private keys, or credentials.

## Boundary

The image lane does not claim that a provider's model listing proves image
capability. Only the endpoint-bound image probe can promote an image operation.
The independent benchmark/evaluation control plane remains separate from both
text serving and image serving.
