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

## Refresh Campaign Outcome

The required refresh was registered as a new campaign after the audit above;
the old campaign remains immutable historical evidence and was not retried.
The refresh was bound to a new operational-admission receipt and a new
screening plan. Its safe contract recorded:

- 29 operationally admitted profiles were screened before formal selection.
- 18 canonical candidates were in the complete formal pool.
- 2 independent non-target source families were fixed for every candidate.
- 36 source/candidate units and 3,960 estimated provider calls were registered.
- The runner used bounded concurrency and no retry of failed units.

The refresh reached a terminal `partial` state: 7 units passed and 29 units
failed. The failures were transport-rate or no-score failures, not converted
into wrong answers and not removed from the denominator. Only 3 candidate
groups happened to complete both source units, but that survivor set cannot be
promoted to a provider top-three ranking because the complete-pool contract
was not satisfied. Strict ranking conversion therefore remains blocked.

## Stability Refresh Outcome

A second, independently identified operational cohort was run against the
complete 29-profile registry, using three repetitions per profile, strict
streaming, a 90-second ceiling, and zero tolerated workload failures. All 29
profiles had complete 15-attempt coverage; 11 remained formal baseline
eligible and 18 were excluded by the stability gate. This is an
availability/stability result, not a quality or target-benchmark result.

The resulting new screening plan contained 11 canonical candidates, 2
independent non-target source families, 22 source/candidate units, and 2,420
fixed provider calls. All 22 units were executed and authenticated: 9 passed
and 13 failed because of transport-failure-rate or no-score gates. Only 3
candidate groups completed both source units. The ranking conversion is
therefore template-only with no rank assignment, and the provider baseline
freeze remains correctly blocked by incomplete complete-pool coverage. No
unit from either earlier campaign was retried.

## Required Next Gate

## r3 Refresh Outcome

The next refresh was registered as a separate cohort and used the exact
calibrated registry/probe binding for the current configured channel set. It
did not reuse any r1 or r2 campaign state, failed unit, or survivor list.

The strict operational-admission receipt covered all 45 profiles with three
repetitions of five fixed non-target workloads per profile (675 attempts in
total). Every profile completed all 15 attempts. The receipt recorded 301
passed attempts, 312 ordinary failures, and 62 attempts beyond the 90-second
latency ceiling; 11 profiles satisfied the zero-failure formal eligibility
gate. The receipt was independently validator-ready and made no quality or
target-benchmark claim.

The resulting pre-registered screening plan contained 11 canonical
candidates, two independent non-target source families, 22 source/candidate
units, and 2,420 fixed provider calls. All 22 units completed execution and
private-artifact digest verification. Seven units met the source transport and
scoring contract; 15 were rejected by the transport-failure or no-score gate.
Across the complete denominator there were 2,420 case records, 1,613 scored
responses, 807 transport failures, and no scorer errors. The campaign is
therefore complete as an experiment but remains `partial` for ranking
eligibility.

The r3 screening-to-ranking conversion correctly returned no rank assignment
and no top-three candidate. The exact probe-evidence audit was ready and all
private/safe profile-set, status-count, mode-count, and API-format bindings
matched. The subsequent baseline-freeze audit remained blocked because the
11 formally eligible profiles did not provide the required exact-cohort
portfolio coverage for judge, synthesizer, structured output, and independent
answer-claim verification. In particular, the current stable eligible pool
could not satisfy the required provider/API diversity contract. This is a
serving/freeze gate result, not a model-quality score.

The formal 9-category, 21-suite target benchmark remains **not started**.
No provider rank 1/2/3 baseline was frozen, and no Axio superiority claim was
made. This is the scientifically correct fail-closed result for the current
remote channel availability.

Before provider baseline freeze can proceed, a new independently registered
provider pool must satisfy the complete-pool screening contract. The next
gate requires:

1. authenticate the final state, every unit digest, and complete source
   coverage;
2. convert the private outputs with the pinned scorer into a complete ranking
   input;
3. re-run the provider portfolio and provider-probe evidence audits against
   the exact registry cohort; and
4. freeze exactly ranks 1, 2, and 3 only after every admitted candidate has
   valid coverage from both independent source families.

The previous failed units must not be selectively retried into the existing
campaign. Any refresh is a new, separately identified experiment with its
own registry, plan, schedule, and receipts.

## Current Channel Cohort Outcome

The latest independently registered cohort was completed after this audit's
r3 work. It used a new calibrated registry, a new operational-admission
receipt, and a new screening campaign. No r3 state, failed unit, or survivor
list was reused. The cohort remained strictly separate from the Axio serving
runtime and from target benchmark execution.

The enrollment stage discovered 126 logical model entries and retained 31
profiles after the strict text probe. The operational admission ran 15
streaming attempts per profile (465 attempts total) under the 90-second hard
response ceiling. It recorded 369 passed attempts, 72 ordinary failures, and
24 latency-ineligible attempts; 11 profiles satisfied the formal zero-failure
admission gate. This is an availability result only and is not a model
quality ranking.

The pre-registered screening plan contained 11 canonical candidates, two
independent non-target source families, 22 source/candidate units, and 2,420
fixed provider calls. The campaign reached a terminal `partial` state after
all 22 units received a terminal result: 6 units passed the transport and
scoring contract and 16 were rejected by transport-failure-rate or no-score
gates. The complete case denominator contained 2,420 records, with 1,444
scored responses and 976 transport failures. No scorer error was converted
into a score, and no failed unit was selectively retried into this campaign.

The screening-to-ranking conversion returned `screening_conversion_ready =
false` with no rank assignment. Its blockers included the non-complete
campaign status, failed or incomplete source units, and incomplete candidate
source coverage. The generated ranking artifact is therefore a diagnostic
template only; it cannot be used to freeze provider ranks 1, 2, or 3.

The provider baseline freeze and the formal 9-category, 21-suite target
benchmark remain **not started** for this cohort. No Axio-vs-provider
superiority claim has been made. This preserves the complete-pool,
case-paired, and contamination-controlled evaluation contract even though a
small survivor subset produced usable responses.
