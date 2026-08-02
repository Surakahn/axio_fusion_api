# Pre-Fusion independent retry budgets

Date: 2026-08-02

## Problem

The r16 live pre-Fusion run reached a valid public-source phase, but one
candidate-specific research shard was blocked after two different failure
classes occurred in sequence:

1. The primary research profile timed out and the workflow switched to a
   configured fallback profile.
2. The fallback returned a JSON object whose non-candidate reasoning
   declaration still contained a protocol control.

The second failure was repairable, but the old state machine used the global
attempt number to enforce the schema-repair budget. The transport failure made
the fallback's first schema error look like a second schema failure, so the
bounded repair request was never sent.

## Change

`_run_research_agent_batches` now tracks two independent counters:

- `transport_failures`: bounded by the transport retry allowance and used for
  fallback switching and transport recovery.
- `schema_failures`: bounded by the schema repair allowance and used for one
  deterministic contract-repair request.

The combined attempt count remains finite at one initial request plus the two
bounded retry allowances. Every request still receives the remaining shared
pre-Fusion deadline; a failed or incomplete shard still blocks publication of
the complete research ranking and cannot enter the runtime registry.

## Regression coverage

Added a regression that exercises the exact sequence `transport timeout ->
fallback schema failure -> repaired success`. Existing transport retry,
fallback, schema repair, and singleton recovery tests remain unchanged.

Verification:

- Targeted research retry tests: 4 passed.
- Full test suite: 864 passed.
- Python 3.11 `compileall`: passed.
- `git diff --check`: passed.

No provider output, prompt, URL, credential, benchmark label, or raw research
text is persisted by this change.
