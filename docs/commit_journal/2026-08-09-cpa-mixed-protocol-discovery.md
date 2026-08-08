# CPA Mixed-Protocol Discovery Boundary

## Scope

This milestone makes the current CPA Plus channel discovery contract explicit
for a catalog that exposes GPT, Chinese, Claude, and image model entries behind
one base URL. It does not change Fusion ranking, prompt policy, benchmark
decoding, or the image registry.

## Behavior

- An explicit catalog `api_format` or `protocol` field remains authoritative.
- An `owned_by=anthropic` catalog hint selects Anthropic Messages.
- When a catalog has no protocol metadata, `claude-*`, `claude/...`, and
  `anthropic/...` identifiers select `/messages`.
- Other models inherit the channel's configured format; the current CPA
  channel therefore keeps GPT and Chinese model entries on `/responses`.
- Image model names remain a separate candidate image lane and never become
  text Fusion profiles.

The model-name rule is a transport compatibility fallback only. It does not
admit a model, assign a capability score, or replace the complete strict
streaming and 90-second pre-Fusion gates.

## Verification

- Non-benchmark `/models` discovery used the configured `auto` network policy
  and local `10808` proxy path.
- Both current provider reports returned `status=ok`; the process observed 21
  CPA entries and 100 NVIDIA entries.
- Targeted protocol/image/runtime tests: `116 passed`.
- Full Python 3.11 regression: `1005 passed, 0 failed`.
- No benchmark request, baseline request, or live text Fusion request was
  made in this milestone.

All durable receipts and documentation keep the existing secret and raw
provider-output exclusion contract.
