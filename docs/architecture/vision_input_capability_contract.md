# Vision Input Capability Contract

## Purpose

`supports_vision` is a model/channel prior. It is useful for selecting probe
candidates, but it is not proof that the configured endpoint accepts image
input. A model directory, provider label, or Cherry Studio-style model rule
cannot replace an endpoint-bound request.

Axio therefore treats visual input as a capability receipt with four separate
layers:

1. A text or multimodal profile explicitly declares `supports_vision: true`.
2. The `vision-probe` command sends one fixed in-memory PNG through the exact
   provider protocol: Chat `image_url`, Responses `input_image`, Anthropic
   base64 image content, or Gemini `inlineData`.
3. The request must produce real SSE/NDJSON framing within the 90-second
   ceiling and the exact color marker expected by the probe. A JSON fallback,
   a wrong visual answer, or a missing stream is not a pass.
4. `vision-probe-bind` compares profile, endpoint, protocol, image, and marker
   hashes. Only an exact complete cohort is promoted with
   `vision_probe_status: passed` and
   `vision_capability_source: operational_probe`.

The PNG, prompt, provider output, URL, credentials, and raw response body stay
in process memory. Safe receipts retain only hashes, status, latency, stream
framing, and bounded error classes.

## Status Semantics

`passed` proves only the tested visual-input wire path and a minimal visual
recognition turn. It does not prove OCR accuracy, chart understanding, video,
document parsing, or general model quality. `failed` and `unsupported` are
negative endpoint evidence and override the static prior in routing.
`indeterminate` represents a transient transport, authentication, rate-limit,
timeout, or server failure and is eligible for a later re-probe.

Image generation/editing is a sibling capability lane. Its `image-probe`
registry is deliberately not combined with the text Fusion registry. Visual
input evidence remains on each ordinary text/multimodal profile, which stays
in the Fusion candidate pool and is filtered only when a request has images.

## Reasoning And Vision Are Orthogonal

Reasoning effort is a provider-specific inference control, not a vision flag.
The public logical effort (`low` through `max`) is mapped only when the exact
model/endpoint transport is verified. NVIDIA Chat uses its declared top-level
`reasoning_effort` vocabulary; Responses-compatible gateways use the declared
nested or provider-local Responses spelling. Higher effort may consume more
reasoning/output tokens and latency, so an explicit downgrade is recorded as
an effective native level rather than being presented as native `max`.

## Commands

```bash
axio-fusion-api-standalone \
  --registry <PRIVATE_REGISTRY.json> vision-probe --live \
  --output <PRIVATE_VISION_PROBE.json>

axio-fusion-api-standalone \
  vision-probe-bind \
  --registry-file <PRIVATE_REGISTRY.json> \
  --probe-file <PRIVATE_VISION_PROBE.json> \
  --output-registry <PRIVATE_REGISTRY_WITH_VISION.json> \
  --output <SAFE_BINDING_RECEIPT.json>
```

The probe is diagnostic until its bound text registry is selected for serving.
It never changes benchmark datasets, Fusion prompts, or model-quality scores.
