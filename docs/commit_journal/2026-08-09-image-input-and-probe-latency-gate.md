# Image Input And Probe Latency Gate

## Scope

This stage hardens the already isolated image-generation/editing sibling lane.
It does not change the text Fusion registry, frozen pre-Fusion screening plan,
external baseline ranking, public text prompts, or benchmark campaign inputs.

## Changes

- Require `multipart/form-data` for image editing requests before MIME parsing.
- Require every accepted `image`, `image[]`, or `mask` file part to declare an
  `image/*` content type.
- Reject duplicate masks with a bounded `image_mask_multiple` error.
- Apply the same non-empty and image MIME checks in the provider client defense
  layer for programmatic callers.
- Mark an image generation/editing operation as failed when its measured
  latency is greater than the hard 90-second admission ceiling, even if it
  returned a non-empty image result.

## Verification

- Python 3.11 compile and import checks passed.
- Focused image regression: `36 passed`.
- Full standalone regression: `1013 passed, 0 failed`.
- No provider or benchmark network call was made by this change.
- Existing CPA `gpt-image-2` verified registry and service-level streaming
  evidence remain unchanged and separate from text Fusion quality claims.

## Safety boundary

The prompt composer is still invoked only after a verified image profile has
been selected. If no verified image registry is configured, image routes
continue to return `image_capability_unavailable`; text Fusion is never used
to fabricate an image result.
