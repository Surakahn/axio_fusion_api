# Channel-Specific Reasoning Effort Contract

## Question

The current Fusion cohort has two different upstream APIs. The question was
whether their reasoning-strength control can share one request-body field.

## Sources And Observations

- NVIDIA NIM's GPT-OSS reference documents the Chat Completions field
  `reasoning_effort` with `low`, `medium`, and `high`; `medium` is the
  documented default for reasoning-capable models. Its documented Responses
  example also uses top-level `reasoning_effort`, rather than the standard
  nested object.
- TokenAPIs' public Grok CLI example is a separate Chat Completions setup. It
  exposes `reasoning_effort` and a larger client-facing vocabulary, but does
  not document the body contract for the configured `/responses` endpoint.
- The current endpoint-bound strict streaming enrollment is the operational
  proof for the configured private endpoints. It found the NVIDIA Chat
  transport verified for 16 of 21 selected profiles, rejected for two, and
  indeterminate for three. All seven selected TokenAPIs Responses profiles
  verified the nested `reasoning: {"effort": ...}` transport for `low`,
  `medium`, and `high`.

These results are transport evidence only. A parameter's acceptance does not
measure a quality delta, prove hidden-reasoning behavior, or authorize a level
that was not directly probed.

## Decision

Axio retains one protocol-neutral logical `reasoning_effort`, but emits it only
through a profile-local, endpoint-bound `reasoning_transport` declaration:

| Upstream adapter | Wire field | Verified current native subset |
| --- | --- | --- |
| NVIDIA Chat Completions | `reasoning_effort` | `low`, `medium`, `high` |
| TokenAPIs Responses | `reasoning.effort` | `low`, `medium`, `high` |

The generic channel template remains `candidate`. A copied configuration must
run its own strict streaming probe and cannot inherit a prior endpoint's
verified status. `xhigh` and `max` may be explicitly mapped down to a verified
`high`; no channel receives a made-up native value. An omitted NVIDIA field is
not equivalent to `none`, because the documented native default is `medium`.

## Regression Coverage

`tests/test_runtime_channel_config.py` now loads the checked-in current-channel
template with fixture-only environment values and asserts that the NVIDIA
profile is a `chat_reasoning_effort` candidate while the TokenAPIs profile is a
`responses_reasoning` candidate. This protects the protocol boundary without
putting a provider endpoint, model output, or credential in a test artifact.

Focused verification completed with:

```text
PYTHONPATH=src python3.11 -m pytest -q \
  tests/test_reasoning_transport.py tests/test_runtime_channel_config.py
```

Result: `43 passed`.
