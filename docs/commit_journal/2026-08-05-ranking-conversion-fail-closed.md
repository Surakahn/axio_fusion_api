# Ranking conversion fail-closed repair

An offline conversion attempt against the interrupted r24 diagnostic exposed
a control-plane edge case: when a partial campaign has no candidate with
complete evidence from every registered source, ranking aggregation could
divide an empty normalized-rank list before returning its existing blocker
template. This did not create ranking evidence, but it made an expected
quality-gate failure look like an operator crash.

The conversion path now records `screening_ranking_candidate_evidence_empty`
and returns the hash-safe template-only receipt. It never invents a rank,
selects a survivor, or turns incomplete units into baseline evidence. A
regression fixture covers an empty source manifest with a preflight-only
campaign, and the existing completed-campaign and artifact-integrity tests
remain unchanged.

The r25 screening plan digest was recomputed after this change and remained
identical (`ad5311a433c13995f9c9de34ec6b50813068e2d861cc2b9a421a0b239b78e740`),
because ranking conversion is downstream of the frozen screening adapter
contract. The full Python 3.11 regression passed `983` tests. No provider,
target-suite, credential, prompt, label, or raw output was used by this repair.
