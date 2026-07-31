# Pre-Fusion Source Read Deadline

## Scope

The pre-Fusion research control plane fetches public model evidence before it
asks the configured research Agent to produce a fixed ranking. A provider or
public source must never be able to leave that control plane worker blocked
indefinitely.

## Change

- Added a per-source response watchdog that closes the response and reachable
  socket wrappers when the source read deadline expires.
- Extended socket-timeout propagation across the standard `urllib` response
  wrapper chain instead of relying on one response implementation shape.
- Normalized `socket.timeout`, `TimeoutError`, and `OSError` at the source
  boundary to the stable `prefusion_source_read_timeout` blocker.
- Added a blocking-response regression fixture proving that the watchdog
  wakes the reader and closes the response.

## Operational Finding

The failed `r15` live cohort is retained only as a transport diagnostic. It
did not produce a complete research ranking or registry and therefore cannot
be used for serving, baseline selection, or benchmark comparison. A short
control request after that run showed the currently configured TokenAPIs and
NVIDIA channels were not providing a stable research response within the
observed control windows. No registry was published as a workaround.

## Verification

- `compileall` passed for `src` and `tests`.
- Full standalone regression: `799 passed`.
- No provider names, model ids, URLs, prompts, outputs, or credentials were
  persisted by the new source deadline path.
