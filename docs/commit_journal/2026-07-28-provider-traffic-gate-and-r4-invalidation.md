# Provider Traffic Gate And Screening Re-Freeze

## Decision

The fourth retry-telemetry baseline-screening attempt is retained only as a
private failed-run audit. Its rate-limited unit exceeded the pre-registered
transport-failure threshold, so none of its answers, scores, or partial ranks
may enter provider ranking, baseline freeze, or the independent benchmark
campaign.

The failure was operational rather than a model-quality observation: a channel
with multiple credentials received repeated HTTP `429` responses while the
previous transport implementation could move rapidly through its key pool.
Changing that behavior changes which observations a screening campaign can
collect. A new plan must therefore be frozen after this change; prior plans
cannot be resumed or patched with replacement responses.

## Transport Contract

- `traffic_control` is a closed per-profile or per-channel local scheduling
  contract. It cannot inject provider payload fields, endpoints, headers, or
  credentials.
- A standard numeric or HTTP-date `Retry-After` is parsed as a bounded number.
  Missing or malformed headers use the configured fallback cooldown.
- `rate_limit_key_pool: "shared"` stops the current logical call after its
  first `429`; it does not sweep the remaining keys. The scope becomes serial
  by default after that observation and uses a post-limit spacing interval.
- `rate_limit_key_pool: "independent"` keeps the existing cross-key failover
  behavior for an explicitly attested independent quota.
- Every gate wait is part of the existing 90-second provider deadline. A wait
  that cannot fit returns the closed `rate_limit_cooldown_exceeded` code.
- Safe receipts retain only aggregate wait time, event count, and the
  shared-pool short-circuit flag. Provider bodies, URLs, headers, and keys
  remain excluded.

## Reproducibility Binding

The non-target screening source snapshot now records a digest of the upstream
transport implementation in addition to its scorer adapter digest. Campaign
validation recomputes both digests. Any edit to streaming, retry, key-pool,
rate-limit, or cooldown code blocks an old plan and forces a new freeze.

## Verification Scope

The deterministic tests cover shared-pool short-circuiting, independent-key
failover, channel-scoped cooldown, numeric and HTTP-date `Retry-After`,
deadline-safe cooldown rejection, runtime configuration inheritance, safe
trace redaction, and the screening transport-binding digest. Existing provider
protocol, baseline-screening, runtime-channel, and operational-admission tests
also run before the change is committed.
