# MMLU-Pro screening case identity repair

The full-pool fail-fast cohort `r24` was stopped after a private checkpoint
showed that the MMLU-Pro adapter used `question_id` as a global case
identifier. MMLU-Pro question numbers are only unique within a category, so
the same identifier occurred more than once in the frozen case set. The
checkpoint and all private unit artifacts remain preserved as interrupted
diagnostic evidence. They are not eligible for ranking conversion, baseline
freeze, or target-suite comparison, and no answer, score, or checkpoint is
reused by the successor cohort.

The adapter now derives a deterministic private case identity from the
adapter schema, category, source question identifier, question text, and
option list. The reference answer is intentionally excluded so source
selection remains label-blind, including disjointness audits that change
labels. A common loader gate rejects missing or duplicate identities before a
screening plan can be executed. The new identity gate is included in the
adapter implementation digest, so an old plan cannot silently continue with
different case semantics.

Validation completed before the next cohort was created:

- the current private MMLU-Pro source loaded 12,032 unique cases;
- the current private LiveBench source loaded 440 unique cases;
- the targeted screening and replacement tests passed (`65 passed`);
- the complete Python 3.11 regression passed (`982 passed`).

The next action is to create a fresh source-manifest binding and immutable
full-pool screening plan from the repaired adapter. Only that new digest-bound
cohort may produce provider baseline ranking evidence.

No API key, raw provider identifier, benchmark label, prompt, provider output,
or private dataset path is persisted in this journal.
