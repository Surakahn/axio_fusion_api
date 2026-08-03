# Mandatory Stage Attempt Budget Contract

## Scope

This milestone hardens the provider Judge and Synthesizer execution boundary.
It does not change the public Axio API, provider ranking, prompt policy, or
benchmark evaluator.

## Change

Every same-canonical physical retry of a mandatory stage now needs its own
bounded runtime admission:

- one dynamic model-call slot;
- one latency reservation derived from that replica's screened p95/p50;
- a redacted routing receipt showing whether both reservations were admitted.

If the retry cannot be admitted, the provider is not called. The runtime
records a skipped attempt and preserves the already reserved Synthesizer or
cross-model fallback window. A failed retry cannot release unrelated dynamic
reservations belonging to the same role; bounded release supports an exact
slot count.

## Contract

The execution order is now explicit:

1. initial mandatory stage attempt consumes its initial reservation;
2. same-model channel retry obtains an independent call/deadline slot;
3. an admitted cross-model fallback retains its own previously reserved slot;
4. an unadmitted physical attempt is skipped fail-closed;
5. a successful stage releases only still-pending failover headroom.

This keeps same-model provider replicas as availability redundancy rather than
additional cognitive panel members, while ensuring every physical request is
included in call, cost, and latency accounting.

## Verification

- `PYTHONPATH=src /home/he/.local/bin/pytest -q`: `929 passed`.
- `PYTHONPATH=src /home/he/.local/bin/pytest -q tests/test_fusion_core_regressions.py -k 'stage_same_canonical or stage_cross_model_failover_gets_a_new_bounded_deadline_window'`: `3 passed`.
- `./.venv/bin/python -m compileall -q src/axio_fusion_api/orchestrator.py`: passed.
- `git diff --check`: passed.

The live Fusion smoke remains a separate operational gate. A failed live
Judge/Synthesizer call must remain visibly incomplete and must not be promoted
to a complete Fusion result or cache entry.
