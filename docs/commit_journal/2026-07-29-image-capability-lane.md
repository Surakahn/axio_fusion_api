# Image Capability Lane

## Scope

This milestone adds an explicitly isolated image capability lane to the
standalone Axio Fusion API. It does not change ASciFS and it does not make
image outputs part of text Fusion.

## Implemented

- Added explicit `model_kind`, `image_capabilities`, and
  `image_probe_status` fields to the model profile contract.
- Excluded image-only profiles from pre-Fusion text screening, Judge,
  Synthesizer, and text benchmark paths.
- Added OpenAI Images-compatible generation and multipart edit routes:
  `/v1/images/generations` and `/v1/images/edits`.
- Added allow-listed image request fields, prompt and multipart size bounds,
  mask and multi-image parsing, sanitized image output, and image-native SSE
  event rendering.
- Reused the provider proxy policy, traffic gate, credential key rotation,
  same-model replica failover, and hard 90-second provider response ceiling.
- Added configuration and operator documentation with a fail-closed
  `candidate`/`not_run` image example.

## Verification

The image test suite and the complete repository regression suite passed in the
local no-proxy test environment:

```text
765 passed in 176.92s
```

The checked-in example intentionally remains unverified. An image model is
not eligible for serving until an endpoint-bound probe promotes the private
registry evidence; the next milestone supplies that operator workflow.

## Security and isolation

No API keys, provider URLs, raw prompts, raw provider responses, or image
artifacts are persisted by the new public response metadata. Image requests
never invoke `FusionEngine.complete()` and image model names never become text
candidate evidence.
