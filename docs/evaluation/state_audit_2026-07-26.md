# Axio Evaluation State Audit: 2026-07-26

## Scope

This audit records the state of the independent evaluation boundary after the
latest engineering verification pass. It is intentionally safe to publish:
it contains no provider names, model aliases, endpoint values, credentials,
raw prompts, benchmark labels, or model outputs.

The audit covers two separate concerns:

1. standalone software verification for the Axio Fusion runtime; and
2. the non-target provider-baseline screening that must finish before the
   formal 9-category, 21-suite comparison can begin.

The screening result is not a benchmark result for Axio and is not used to
tune production prompts or routing policy.

## Engineering Verification

The declared project runtime is Python 3.10 or newer. Under Python 3.11 the
complete standalone regression suite passed:

```text
678 passed in 135.52s
```

Compilation and whitespace checks also passed:

```text
python3 -m compileall -q src tests
git diff --check
```

The initial invocation with the host Python 3.8 interpreter is not a supported
project run. It exposed three failures caused by Python 3.8 not implementing
the dictionary-union operator used by the codebase; the project declares
`requires-python = ">=3.10"`, so no compatibility layer was added for an
unsupported interpreter.

## Non-target Baseline Screening

The frozen screening plan used two independent non-target source families,
fixed case sets, fixed prompt and decoding contracts, a complete canonical
candidate pool, and a 2% per-unit transport-failure ceiling. The campaign
completed all 30 planned units:

- 7 units met the transport and scoring contract.
- 23 units were rejected because the transport-failure ceiling was exceeded
  or no scorable answer remained.
- 3 canonical candidates happened to pass both source-family units, but this
  does not make them the provider-pool top three.

The strict ranking conversion therefore remains blocked. The external ranking
template is diagnostic only and has no rank assignment. This is the correct
outcome: selecting the three surviving candidates would create a post-hoc
survivor pool and would violate the pre-registered complete-pool contract.

The formal 21-suite benchmark campaign is consequently **not started**. No
Axio-vs-provider superiority claim has been made.

## Required Next Gate

Before provider baseline freeze, the system needs a new, independently
pre-registered provider-pool refresh based only on operational evidence:

1. re-run the bounded streaming availability/admission check with an explicit
   concurrency policy;
2. publish a new hash-bound registry only if the 90-second and strict-stream
   contracts hold;
3. generate a new complete-pool non-target screening plan before any target
   benchmark calls; and
4. freeze exactly ranks 1, 2, and 3 only after every admitted candidate has
   valid coverage from both independent source families.

The previous failed units must not be selectively retried into the existing
campaign. Any refresh is a new, separately identified experiment with its
own registry, plan, schedule, and receipts.

