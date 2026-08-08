# Image Capability Production Hardening

## Scope

This milestone completes the current CPA Plus image lane without coupling it to
ASciFS or to the text Fusion benchmark path. The change covers the control
plane, provider response safety, prompt composition contracts, and live serving
verification.

## Engineering changes

- Added the non-secret CPA channel declaration for the `gpt-image-2`
  candidate: `images_api`, generation/editing paths, and stream declaration.
- Added `load_image_probe_candidates()` so the image probe can inspect
  unpromoted image candidates without weakening `load_registry()`'s text-model
  auxiliary exclusion.
- Kept `load_image_registry()` fail-closed: only a ready endpoint-bound probe
  binding with verified operations can reach the serving router.
- Bound JSON generation request size, non-stream response size, total streamed
  image bytes, base64 fields, URLs, and revised prompts.
- Added prompt-composer semantic regressions for fixed JSON output and exact
  original-prompt fallback.
- Migrated the operator-only environment names from `AXIO_TOKENAPIS_*` to
  `AXIO_CPA_PLUS_*` and bound the promoted image registry through
  `AXIO_FUSION_IMAGE_REGISTRY_PATH`.

## Live evidence

The 2026-08-09 CPA image probe used only non-benchmark control prompts:

- generation: `stream=true`, SSE observed, passed below 90 seconds;
- editing: `stream=true`, SSE observed, passed below 90 seconds.

A fresh loopback service loaded the verified image registry and current CPA text
profiles. Real HTTP generation and multipart editing both returned
`text/event-stream`, validated partial/completed image events, and `done`.
Image artifacts stayed in process memory and the public stream contained no raw
user prompt.

The final no-upstream `/health` load check also reported one generation and one
editing image profile with `text_fusion_isolated=true`. The overall status was
`usable_with_warnings` because the current text serving registry separately
warns about weak or missing Judge and structured-output candidates; this is a
text-serving readiness issue, not an image-lane failure.

This is image capability and serving evidence only. It does not enter the
provider baseline ranking, alter Fusion prompts, or support any of the
9-category/21-suite model-quality claims.

## Root cause recorded

The first CLI probe attempt returned zero candidates without making a network
call because the command reused the text registry loader, which intentionally
filters `gpt-image-*` auxiliary models. The dedicated probe-only loader repairs
that boundary while preserving text Fusion exclusion and production serving
isolation.

## Verification

- Python compilation and imports passed.
- Focused image/config/provider contract tests passed: `107 passed`.
- Endpoint-bound image probe: generation and editing both passed.
- Promoted image registry loaded with one generation-eligible and one
  editing-eligible profile.
- Real service-level generation and multipart editing passed with streaming
  image events.

The final standalone regression in this worktree completed with `976 passed`
and `18 failed`. The failures are pre-existing, non-image regressions in the
legacy panel/latency expectation set and old provider/registry fixtures; none
are part of the image capability test selection. They remain an explicit
follow-up gate and are not reclassified as passing evidence for this
milestone. The r26 provider screening remains independently terminal
`partial`/`ready_for_ranking=false`, so no provider baseline or 21-suite
superiority claim is made.
