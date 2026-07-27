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

Source: <https://developers.openai.com/api/docs/guides/reasoning>

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

- `transport` may only be `chat_reasoning_effort` or `responses_reasoning`.
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

## Fusion Budget Rule

Hermes defines role-local cognitive budgets for advisor, critic, Judge, and
synthesizer stages. The public request can lower, but never raise, that role
budget. Direct `axio-fast` cascades retain the public request value. The
logical result is passed to the selected profile, which still omits it unless
the profile's verified transport accepts the effective level.

This is a control-plane and serving-quality feature only. It does not use
benchmark prompts, labels, or evaluation outcomes, and a successful wire
parameter probe is not evidence of a model-quality improvement.
