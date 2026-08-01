# Reasoning Transport Contract

## Purpose

Axio is an API-only Fusion runtime. It does not train a model or assume that
all upstream gateways implement the same inference controls. This contract
separates a public, protocol-neutral `reasoning_effort` request value from the
provider-specific request field that may eventually carry it.

The design avoids two failure modes:

1. Sending a Responses object to a Chat Completions gateway, or vice versa.
2. Treating a model directory listing or a vendor claim as proof that a
   reasoning setting is accepted by the exact channel and model being served.

## Research Prior Versus Wire Evidence

The remote pre-Fusion Research Agent emits a model-local
`reasoning_capability` object in
`axio_fusion_api.prefusion_research_agent_output.v2`. It is an evidence-bound
prior, not permission to write a provider field:

```json
{
  "status": "candidate",
  "transport": "responses_reasoning",
  "native_efforts": ["low", "medium", "high"],
  "effort_map": {"xhigh": "high", "max": "high"},
  "evidence_ids": ["source_official"],
  "confidence": 0.9,
  "token_cost_model": "provider_documented",
  "latency_cost_model": "monotonic_effort_policy",
  "cost_evidence_ids": ["source_official"]
}
```

The serving profile stores that prior as `screening_reasoning_capability` and
stores the independent endpoint probe as `reasoning_transport`. Only the
latter can be `verified`. A model that declares only `medium` does not acquire
`low`, `high`, `xhigh`, or `max` by interpolation. An `effort_map` is accepted
only when it is explicit, maps to a declared native level, and does not raise
the caller's requested intensity. The research evidence must be visible to
the same candidate; a source attached to another model cannot be reused.

An evidence gap is represented as `status: "unknown"`, with no transport,
native effort, cost claim, or reasoning evidence forwarded. This is a bounded
uncertainty state, not permission to guess and not a reason to discard an
otherwise valid model ranking. The endpoint-bound probe remains the only path
that can promote a reasoning declaration; `candidate` and `unsupported`
claims still require candidate-scoped evidence and remain strict when that
evidence is missing or mis-scoped.

Chat Completions, Responses, Anthropic Messages, and Gemini are separate
transport contracts. A Chat `reasoning_effort` claim cannot authorize a
Responses `reasoning` object, and neither OpenAI field is inferred for
Anthropic or Gemini. The protocol adapter therefore omits unverified controls
instead of guessing a vendor-specific field.

## Verified Wire Shapes

### NVIDIA NIM Chat Completions

NVIDIA's NIM reference for GPT-OSS documents a top-level field:

```json
{
  "model": "openai/gpt-oss-120b",
  "messages": [{"role": "user", "content": "..."}],
  "stream": true,
  "reasoning_effort": "high"
}
```

The documented values are `low`, `medium`, and `high` for reasoning-capable
models. Axio represents this as `chat_reasoning_effort`; it can only be
enabled on a profile whose upstream API format is Chat Completions.

The current NVIDIA candidate declaration therefore probes only that documented
three-level subset. Once the exact model/channel passes the probe, its explicit
non-escalating map may route Axio's logical `xhigh` and `max` roles to NVIDIA's
highest verified native value, `high`. It must never send `xhigh` or `max` to
NVIDIA merely because Axio understands those logical values.

Source: <https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-120b-infer>

### OpenAI-Compatible Responses Gateways

The Responses API documents a nested object:

```json
{
  "model": "provider-model-alias",
  "input": "...",
  "stream": true,
  "reasoning": {"effort": "high"}
}
```

The standard level vocabulary varies by model and can include `none`,
`minimal`, `low`, `medium`, `high`, `xhigh`, and `max`. Axio represents this
as `responses_reasoning`; the profile's verified subset remains authoritative.
`reasoning.mode` and `reasoning.summary` are intentionally outside this first
transport contract. They require separate per-model verification and product
approval because they are not portable inference-strength controls.

The current TokenAPIs declaration begins with only `low`, `medium`, and `high`
as candidates. A verified `high` may receive an explicit logical downgrade
from Axio `xhigh` or `max`, but native Responses levels above `high` are never
assumed from the compatibility label alone. They require a new model-local
candidate declaration and a successful strict probe.

Source: <https://developers.openai.com/api/docs/guides/reasoning>

### Current TokenAPIs Evidence Boundary

The public TokenAPIs setup guide documents a separate OpenAI-compatible
**Chat Completions** configuration for Grok CLI: the example names
`api_backend = "chat_completions"`, enables `reasoning_effort`, and lists
`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max` as client-facing
choices. That guide alone does **not** state the request-body contract for
TokenAPIs' `/responses` endpoint, and therefore does not establish either
`reasoning: {"effort": ...}` or top-level `reasoning_effort` for that endpoint.

For this reason the checked-in TokenAPIs template remains a `candidate`
Responses declaration. It becomes `verified` only through the exact
endpoint-bound strict streaming probe, never through the provider name or the
Chat Completions documentation. The current private two-channel enrollment
completed that probe on 2026-07-28: all seven selected TokenAPIs Responses
profiles accepted the nested `reasoning: {"effort": ...}` shape for `low`,
`medium`, and `high` while preserving the strict stream contract. That is wire
capability evidence only; it neither proves a semantic quality gain at each
level nor authorizes `none`, `minimal`, `xhigh`, or `max` on the Responses
endpoint.

A later operator may explicitly declare `responses_reasoning_effort` for a
particular model only when that alternate top-level spelling is supported by
channel documentation or an independently controlled integration contract.
Axio never falls back from one spelling to the other after a parameter
rejection.

Source: <https://tokenapis.com/docs/guide.html?id=grok>

### NVIDIA NIM Responses Variant

NVIDIA's NIM GPT-OSS reference also exposes a Responses endpoint, but its
documented request examples retain the top-level spelling instead of the
standard nested object:

```json
{
  "model": "openai/gpt-oss-120b",
  "input": [{"role": "user", "content": "..."}],
  "stream": true,
  "reasoning_effort": "high"
}
```

Axio represents this provider-local Responses variant as
`responses_reasoning_effort`. It is deliberately distinct from
`responses_reasoning`: a Responses profile can select one spelling only after
an explicit candidate declaration and a successful live probe against that
exact endpoint and model. It is not enabled merely because a channel is named
NVIDIA, and it does not change the currently configured NVIDIA Chat or
TokenAPIs Responses transports.

Source: <https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-120b-infer>

### Current Two-Channel Wire Matrix

The current channels are intentionally different at the request boundary:

| Channel profile | Upstream API | Exact parameter | Verified native levels | Current evidence rule |
| --- | --- | --- | --- | --- |
| NVIDIA | Chat Completions | `reasoning_effort: "<level>"` | `low`, `medium`, `high` | Profile-local strict stream probe; 16 of 21 selected profiles verified in the 2026-07-28 enrollment, two explicitly rejected, and three remained indeterminate. |
| TokenAPIs | Responses | `reasoning: {"effort": "<level>"}` | `low`, `medium`, `high` | Profile-local strict stream probe; all seven selected profiles verified in the same enrollment. |

The NVIDIA reference documents `medium` as its default for reasoning-capable
models. Consequently, Axio must not treat an omitted parameter as equivalent
to native `none`: the omission means only that no verified wire control was
sent. A client that requires an exact non-default level must use a route whose
selected profiles carry a matching verified declaration. Likewise, the
operator's `xhigh -> high` and `max -> high` mappings are explicit logical
downgrades, not claims that either current endpoint accepts those native
values.

The private evidence records only endpoint hashes, profile/model bindings,
timing, stream framing, status classes, and output hashes. It never persists a
credential, endpoint value, raw prompt, visible output, or hidden reasoning.

## Axio Configuration Gate

The profile-level declaration is deliberately closed:

```json
{
  "reasoning_transport": {
    "status": "verified",
    "transport": "chat_reasoning_effort",
    "supported_efforts": ["low", "medium", "high"],
    "effort_map": {"xhigh": "high"}
  }
}
```

- `transport` may only be `chat_reasoning_effort`, `responses_reasoning`, or
  `responses_reasoning_effort`.
- `status` must be `verified` before the adapter writes a wire field.
- The declared transport must match the profile API format.
- An unsupported requested level is omitted unless `effort_map` explicitly
  maps it to a declared supported level of equal or lower intensity.
- No configuration field can inject arbitrary upstream request-body keys.

## Verification And Failure Semantics

The operational verification sequence uses a fixed, non-benchmark short
streaming prompt:

1. Send a control request without a reasoning parameter.
2. Send one request for each candidate effort using the protocol-specific
   field.
3. Record only timing, HTTP status classification, stream framing, and output
   hashes. Never retain provider output, hidden reasoning, endpoint values, or
   credentials in a safe receipt.

If the control succeeds and a parameterized request returns an explicit 4xx,
the profile remains unverified for that transport. A timeout, 5xx, or network
failure is not evidence that the parameter itself was rejected. Serving never
removes a reasoning field and retries the same request merely to make a 4xx
disappear; that would silently change the caller's requested semantics.

## Operational Capability Probe

`reasoning-probe` is the operational control-plane command for turning a
model-local `candidate` declaration into a serving-capable declaration. It is
deliberately narrower than a quality benchmark:

1. It selects only profiles explicitly marked `candidate`, with one of the
   audited transports and at least one declared level.
2. It sends a fixed non-benchmark control request with no reasoning field.
3. It sends one request per declared level with the protocol-local wire shape.
4. Every request requires actual SSE or NDJSON framing, a visible fixed marker,
   and completion within the 90-second provider ceiling.
5. A successful control plus every successful declared level promotes only
   that exact profile to `verified`.

The Responses probe disables the textual-input compatibility fallback. A
parameterized 4xx is therefore visible as a rejection rather than being hidden
by a second request with a different body. Explicit non-transient 4xx values
mark the declared transport `unsupported`; 401, 403, 408, 429, 5xx, timeouts,
network errors, malformed streams, and marker failures remain `candidate` for
later re-probe because they do not prove the field is unsupported.

The private probe receipt contains operational aliases for registry binding.
Its safe projection, produced by `redact-reasoning-probe`, replaces profile,
provider, and model identifiers with hashes and retains only status, level,
latency, status code class, stream framing, and output hashes. Neither form
stores endpoint values, credentials, raw prompts, raw outputs, or hidden
reasoning.

The live probe also records two sorted, hash-only profile sets: the complete
candidate set considered before selection and the exact selected set that
received probe rows. Each set has its own SHA-256 digest, and the selected set
must be a subset of the candidate set. Handoff validation uses these sets for
the probe counts and required-contract flag, so a real selection limit or
provider-fair selection cannot be confused with a missing research declaration.
The probe selection policy repeats the same sets and digests, binding the
selection decision to the evidence without retaining provider responses.

The operational role probe covers the complete admitted profile cohort for its
requested high-impact roles. A profile with no admitted target receives an
explicit empty receipt with `skipped_no_role_targets`; that receipt records no
role capability and cannot promote Critic, Judge, or Synthesizer admission.

The endpoint binding is captured immediately before the probe's first network
request. This prevents a long-running probe from being attributed to a channel
target that an operator configured only after the request began. Local
registry calibration also verifies that binding against the endpoint currently
resolved for the profile; a stale or legacy probe cannot promote a transport
after a gateway retarget. That local check does not replace the full-cohort
cross-registry reconciliation below.

The live pre-Fusion workflow requires a complete candidate cohort. If one
researched candidate has no probe row, or a row has a malformed count/status,
the screening handoff is blocked. `verified`, `rejected`, and `indeterminate`
are distinct outcomes: a non-transient parameter 4xx can produce
`unsupported`, while a timeout, 5xx, malformed stream, or missing row remains
unverified and is never forwarded to a provider.

## Endpoint-Bound Reconciliation

A provider/model alias is not sufficient to reuse a prior wire-capability
result. An operator can retarget a channel environment variable to a different
gateway while retaining the same provider label and model alias. Each newly
generated reasoning probe therefore carries a hash-only binding over the
profile identity, canonical identity, upstream API format, resolved endpoint
hash, authentication scheme, and declared reasoning transport contract.

`reconcile-reasoning-transport` is the only cross-registry promotion path. It
accepts a source serving registry, the calibrated registry emitted from the
same enrollment, and the private reasoning-probe artifact. Before writing a
new private registry it requires all of the following:

1. The source and calibration registries contain the exact same physical
   profile set.
2. Every candidate profile appears exactly once in a full, unbounded live
   probe cohort.
3. The probe binding matches the current endpoint, model, protocol, and
   declared transport contract.
4. The calibration status is independently justified by strict probe evidence.
5. The output path differs from the source path and, for a pre-Fusion source,
   the resulting handoff still validates.

The operation changes only a candidate profile's reasoning transport status to
`verified`, `unsupported`, or retained `candidate`. It never changes model
ranking, capability scores, role admission, benchmark baselines, or benchmark
results. Legacy probe artifacts without the endpoint binding remain useful
diagnostics but are intentionally ineligible for this operation; rerun a live
probe after upgrading the control plane.

## Fusion Budget Rule

Hermes defines role-local cognitive budgets for advisor, critic, Judge, and
synthesizer stages. The public request can lower, but never raise, that role
budget. Direct `axio-fast` cascades retain the public request value. The
logical result is passed to the selected profile, which still omits it unless
the profile's verified transport accepts the effective level.

This is a control-plane and serving-quality feature only. It does not use
benchmark prompts, labels, or evaluation outcomes, and a successful wire
parameter probe is not evidence of a model-quality improvement.
