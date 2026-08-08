# Image Generation and Editing

Images are a sibling capability lane. They share provider enrollment,
credentials, proxy policy, latency gates, and key failover with text Fusion,
but image artifacts never enter the text candidate/Judge/Synthesizer graph.

## Current CPA Plus Enrollment

The current CPA Plus channel exposes `gpt-image-2` as an image model. Its
model-list protocol is Responses-compatible, but the image operation is bound
to the OpenAI Images-compatible transport:

- generation: `POST /v1/images/generations`;
- editing: `POST /v1/images/edits` with `multipart/form-data`;
- upstream profile: `model_kind=image`, `transport=images_api`;
- public Axio aliases: `axio-fast`, `axio-terra`, and `axio-pro`.

The model is never admitted to the text Fusion registry. A model-list entry
only creates `candidate/not_run` image metadata. The private operator workflow
must run both operation probes before promotion:

```bash
PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  --registry private/runs/<image-cohort>/gpt-image-2.registry.candidate.private.json \
  image-probe --live --max-workers 1 --timeout 90 \
  --output private/runs/<image-cohort>/gpt-image-2.image_probe.private.json

PYTHONPATH=src .venv/bin/python -m axio_fusion_api.cli \
  image-probe-bind \
  --registry-file private/runs/<image-cohort>/gpt-image-2.registry.candidate.private.json \
  --probe-file private/runs/<image-cohort>/gpt-image-2.image_probe.private.json \
  --output-registry private/runs/<image-cohort>/gpt-image-2.registry.verified.private.json \
  --output private/runs/<image-cohort>/gpt-image-2.image_probe_binding.safe.json
```

The 2026-08-09 CPA probe passed generation and editing independently, sent
both with `stream=true`, observed SSE frames for both, and measured each
operation below the hard 90-second provider ceiling. This is capability and
serving-admission evidence only. It is not text-model quality evidence and
does not alter the independent baseline or 21-suite benchmark gates.

## OpenAI Images API

Generation uses `POST /v1/images/generations` with a JSON body such as:

```json
{
  "model": "gpt-image-2",
  "prompt": "A clean technical illustration of a model gateway",
  "n": 1,
  "size": "1024x1024",
  "quality": "high",
  "background": "opaque",
  "output_format": "png",
  "stream": false
}
```

Editing uses `POST /v1/images/edits` as `multipart/form-data`, with one or more
`image` parts, an optional `mask`, and text fields including `prompt`, `model`,
`n`, `size`, `quality`, `input_fidelity`, and output options. The multipart
boundary, file name, content type, and request size must be validated before
forwarding. `input_fidelity` is not a generation parameter; it is forwarded
only when the selected editing profile explicitly declares support.

Image parameter compatibility is profile metadata, not a model-name heuristic:

```json
{
  "parameter_support": {
    "input_fidelity": "unsupported",
    "background_transparent": "unsupported"
  }
}
```

The values are `supported`, `unsupported`, or `unknown`. A requested
`input_fidelity` or transparent background is rejected before prompt
composition and provider I/O unless every selected replica declares the
corresponding parameter as `supported`. An explicit `unsupported` declaration
returns a bounded compatibility error; an omitted declaration fails closed as
`image_parameter_capability_unverified`. This prevents a provider-specific
400 from becoming a late, ambiguous image failure.

For the current CPA Plus `gpt-image-2` profile, `input_fidelity` and
transparent backgrounds are explicitly marked `unsupported`. The gateway
therefore preserves the documented `gpt-image-2` contract and does not send
either option upstream. Other image models can opt into either feature
through their own endpoint-bound capability manifest without changing code.

Responses API image generation is a separate tool transport. It uses an
`image_generation` tool in the Responses request and returns an image
generation call/result item. It is not equivalent to posting the Images API
JSON body to `/responses`.

## Admission Rules

A profile enters the image registry only when it explicitly declares:

- `model_kind: image` or a verified multimodal image capability;
- operation `generation` or `editing`;
- transport `images_api` or `responses_image_generation`;
- the audited route and output form;
- a successful image capability probe within the 90-second ceiling.

Names such as `gpt-image-*` are not enough to admit a model into text Fusion.
Likewise, a text model that can describe an image is not an image generator.

Promotion is atomic at the registry boundary. A missing, failed,
endpoint-mismatched, stale, or partially completed probe cannot replace the
active image registry. `load_image_probe_candidates()` exists only for the
probe control plane; serving calls `load_image_registry()`, which requires a
ready binding and at least one verified operation.

## Streaming and Artifacts

When an upstream supports partial image events, the image lane emits only
validated image events. Base64 payloads are bounded and are never inserted into
text prompts or operational logs. A failed partial image route does not fall
back to text synthesis and claim that an image was created.

Before dispatch, the gateway validates the JSON or multipart request size. The
provider client bounds non-stream response bodies, total SSE/NDJSON bytes, and
image metadata fields. The default response limit is
`AXIO_FUSION_IMAGE_MAX_RESPONSE_BYTES=64 MiB`; it can be lowered by the
operator within the configured safe range. A limit violation is a provider
failure and is eligible for the normal same-model replica/key failover path,
not a partial success.

## Prompt Composition

Only after a verified image profile has been selected does the optional
`ImagePromptTransformer` call a text model. It receives the user's image
intent as data inside a fixed system contract and accepts exactly:

```json
{"prompt":"..."}
```

The composer preserves requested subject, identity, composition, style,
lighting, language, text, and edit constraints; it must not invent important
facts. Invalid JSON, unavailable text profiles, timeout, or provider failure
falls back to the user's original prompt. The original and transformed prompt
remain process-local and are excluded from receipts. If no verified image
profile exists, the router returns `503 image_capability_unavailable` before
the composer is invoked, so a text model cannot pretend to generate an image.

## Security and Limits

- Multipart input has a configured byte limit and allow-listed file fields.
- File names are basename-normalized and content types are constrained.
- Upstream error bodies are sanitized.
- Image outputs are not persisted by the text trace store.
- `n`, partial image count, compression, and request timeouts are bounded.

The implementation lives in `src/axio_fusion_api/image_api.py` and is covered
by `tests/test_image_api.py`.
