# Pre-Fusion profile-chain transport recovery

Date: 2026-08-02

## r17 evidence

The independent retry-budget fix allowed the r17 research workflow to validate
13 of 15 candidate-specific shards. Two shards remained incomplete because the
remote research profiles returned a sequence of transport failures including
timeouts, HTTP errors, and URL errors. The strict complete-ranking gate
correctly refused to publish a partial ranking, so no reasoning or streaming
probe ran and no registry was activated.

The failure exposed a second control-plane issue: the configured research
profile chain contains four profiles, while the historical per-shard transport
allowance permitted only two retries after the initial request. The final
fallback therefore could not receive a request even when the earlier profiles
had already failed.

## Change

The per-shard transport retry limit is now the greater of the historical
minimum and the number of configured fallback transitions. This allows a
bounded walk through the complete current profile chain while preserving:

- one finite combined attempt budget per shard;
- the independent schema-repair allowance;
- the shared total pre-Fusion deadline;
- the 90-second provider response ceiling;
- fail-closed publication when any shard remains incomplete.

The receipt records the effective retry limit so an operator can distinguish a
two-profile run from a four-profile run without exposing provider identities or
credentials.

## Regression coverage

Added a four-profile fixture where the first three transport attempts fail and
the fourth profile returns a valid ranking row. Existing two-retry, fallback,
schema-repair, and singleton recovery tests remain in place.

Verification:

- Targeted transport tests: 4 passed.
- Full test suite: 865 passed.
- Python 3.11 `compileall`: pending for this commit and run before push.
- `git diff --check`: pending for this commit and run before push.

No benchmark cases, benchmark labels, raw provider output, prompt, URL,
credential, or local model weights are used or persisted by this change.
