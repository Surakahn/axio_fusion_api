# Pre-Fusion Catalog Binding Fix

Date: 2026-08-03

## Problem

The first reusable `prefusion-probe-export` projection carried the exact
physical stream rows but omitted the provider `/models` catalog reports nested
in the screening report. The provider baseline screening plan consequently
could not create exact channel/model identity attestations for the current
cohort and correctly blocked with an incomplete identity set.

## Change

The projection now preserves the discovery provider reports in the private
standard probe artifact. The existing provider redactor turns their provider
and model aliases into hashes in the safe projection. No catalog response body,
credential, URL, prompt, or provider output is copied.

This allows `build_provider_identity_attestation_receipt()` to verify the
exact channel catalog alias against each live-probed profile while retaining
the strict requirement that renamed aliases still need an explicit operator
attestation.

## Current r20 result

After regeneration, the provider-probe evidence audit remains ready with zero
blockers, and the fresh r20 non-target screening plan is ready with 11
canonical groups, two independent source families, 22 units, 2,420 fixed
provider calls, and a frozen serial worker count of one. The live screening has
started in a new private root. No result from an older cohort is reused.

## Verification

- Targeted export and baseline-screening regression: `55 passed`
- Python 3.11 compilation: passed
- Safe provider/model redaction and exact catalog binding: passed

The live screening remains a separate non-target ranking operation; it is not a
21-suite benchmark result and cannot by itself establish an Axio superiority
claim.
