# Current-state documentation reconciliation

Date: 2026-08-09

## Change

Align the operator-facing status documents with the completed r43 cohort and
the final standalone regression. The current text pre-Fusion registry is
explicitly described as 10 physical profiles with three public Axio models;
the older 29-profile, v9, r26, and r27 references remain historical rather
than being presented as active serving inputs. The image lane remains
independent, with its verified CPA image profile and separate generation/edit
registry.

The current evidence chain now reads consistently:

```text
r43 ready generation
  -> generation-bound offline probe projection
  -> probe-bound registry
  -> zero-blocker provider evidence audit
  -> external ranking and baseline-freeze gate still pending
```

No code behavior, provider configuration, benchmark data, prompt, route policy,
or serving registry was changed in this documentation-only update.
