# Image Parameter Compatibility And Regression Gate

## Scope

This stage hardens the already isolated image-generation/editing lane. It does
not add image profiles to text Fusion, change the text router, use benchmark
material, or select a provider baseline.

## Decision

Image option support is declared per verified image profile through a closed
`image_capabilities.parameter_support` map:

- `input_fidelity`
- `background_transparent`

Each value is `supported`, `unsupported`, or `unknown`. The gateway validates
the requested operation against the selected profile before prompt composition
and before provider I/O. `input_fidelity` is editing-only. A declared
unsupported option returns a bounded compatibility error; an unknown
declaration fails closed instead of silently dropping user intent.

The current CPA Plus `gpt-image-2` private image registry records both options
as unsupported, matching its audited image contract. The capability is
metadata-driven so another image provider can declare a different contract
without a model-name branch in the request path.

## Verification

- Image API regression: `32 passed`.
- Image, runtime-channel, provider-enrollment, and pre-Fusion admission
  regression: `89 passed`.
- Full standalone regression before the registry diagnostic stage:
  `997 passed, 0 failed` in 197.45 seconds.
- No provider or benchmark network request was made by the code regression.
- Existing image generation/editing service evidence remains separate and
  unchanged.

## Registry Safety

The r41 serving artifact remains fail-closed because its pre-Fusion generation
marker does not agree with its binding/catalog contract. The r42 candidate
registry is not promoted without a complete enrollment handoff. Neither
artifact is used as benchmark baseline evidence.

## Security

No credential, raw provider URL, raw prompt, image bytes, or raw provider
output is added to public source, tests, or this journal.
