# Image Generation and Editing

Images are a sibling capability lane. They share provider enrollment,
credentials, proxy policy, latency gates, and key failover with text Fusion,
but image artifacts never enter the text candidate/Judge/Synthesizer graph.

## OpenAI Images API

Generation uses `POST /v1/images/generations` with a JSON body such as:

```json
{
  "model": "gpt-image-1",
  "prompt": "A clean technical illustration of a model gateway",
  "n": 1,
  "size": "1024x1024",
  "quality": "high",
  "background": "transparent",
  "output_format": "png",
  "stream": false
}
```

Editing uses `POST /v1/images/edits` as `multipart/form-data`, with one or more
`image` parts, an optional `mask`, and text fields including `prompt`, `model`,
`n`, `size`, `quality`, `input_fidelity`, and output options. The multipart
boundary, file name, content type, and request size must be validated before
forwarding.

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

## Streaming and Artifacts

When an upstream supports partial image events, the image lane emits only
validated image events. Base64 payloads are bounded and are never inserted into
text prompts or operational logs. A failed partial image route does not fall
back to text synthesis and claim that an image was created.

## Security and Limits

- Multipart input has a configured byte limit and allow-listed file fields.
- File names are basename-normalized and content types are constrained.
- Upstream error bodies are sanitized.
- Image outputs are not persisted by the text trace store.
- `n`, partial image count, compression, and request timeouts are bounded.

The implementation lives in `src/axio_fusion_api/image_api.py` and is covered
by `tests/test_image_api.py`.
