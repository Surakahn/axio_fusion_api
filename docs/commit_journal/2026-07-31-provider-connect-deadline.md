# Provider Connect-Stage Deadline

## Diagnosis

The first fallback-enabled live cohort (`r16`) was stopped after a low-
frequency probe found one research worker holding an established connection
to the configured local proxy for more than twenty minutes without producing
an artifact. The response-read watchdog was not reached: the block occurred
inside the stdlib HTTPS connection setup, while proxy CONNECT/TLS was still
being established.

The entire `r16` directory remains diagnostic-only and contains no accepted
ranking or registry. No partial result was reused.

## Change

- Added a deadline watchdog around `HTTPConnection.connect()` so a proxy socket
  is closed even if the CONNECT reader ignores its socket timeout.
- Applied only the remaining connect budget before and after TLS wrapping;
  CONNECT and TLS cannot silently restart a fresh timeout.
- Added a regression fixture for a proxy socket that blocks inside connection
  setup and must be closed within the configured deadline.

## Verification

- Real TokenAPIs control request returned `provider_request_timeout` at
  `5.005s` with a 5-second budget instead of hanging.
- Network/provider/screening regression: `124 passed`.
- Full standalone regression: `802 passed`.
- No credentials, raw provider bodies, prompts, or source content were
  persisted.
