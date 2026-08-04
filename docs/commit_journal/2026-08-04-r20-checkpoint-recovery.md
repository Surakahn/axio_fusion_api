# r20 checkpoint recovery after interrupted process

## Incident

The original r20 screening process exited before writing a terminal campaign
state. Its safe state remained `status=running`, with six already failed units
and the active private unit checkpoint at 102 of 108 cases. No ranking manifest,
r21 state, or target benchmark request existed at that point.

The interruption was not treated as a successful screening result. The old
handoff supervisor was stopped because it was bound to the exited PID and
would otherwise wait forever on a non-terminal state.

## Recovery contract

The same immutable r20 plan, registry binding, source manifest, state path, and
private root were reused. The runner's checkpoint recovery path was used with
`--retry-failed` omitted:

- completed provider answers in the in-flight private checkpoint remain bound
  and are not sampled again;
- transport failures remain eligible for the normal registered retry path;
- the six existing failed units remain in the campaign denominator;
- no plan, prompt, scorer, concurrency, or benchmark input changed;
- r21 remained closed until a terminal r20 ranking conversion.

The first local wrapper attempt failed before importing the package because its
environment lacked `PYTHONPATH=src`. It made no provider request and changed no
private artifact. The corrected wrapper started the same r20 command with
`PYTHONPATH=src`; the resumed checkpoint then advanced to a later unit. A new
PID-bound supervisor was attached after the process was verified live.

## Current boundary

This recovery receipt proves continuity of the screening process only. It is
not a provider ranking, baseline freeze, benchmark score, or Axio superiority
claim. The next permitted transition remains:

```text
r20 terminal state -> one ranking conversion -> r21 only if conversion blocked
```
