# Bounded Pre-Fusion Research Agent Fallbacks

## Scope

The pre-Fusion screening Agent is a configurable API caller. Its model is not
part of the Axio quality claim; it produces the evidence-scoped, fixed-format
operational prior that must be complete before streaming admission begins.

## Change

- Added an allow-listed ordered fallback chain to the research Agent config.
- Bound each fallback to provider/model/API-format identity and environment
  variable references; nested secrets and arbitrary transport fields are
  rejected.
- Switch to the next profile only for provider/transport failures. Invalid
  JSON, missing candidates, invalid evidence scope, role-contract failures,
  and latency-ineligible research responses still fail closed.
- Record only profile hashes, API formats, attempt status, and the bounded
  fallback-switch count in research receipts.
- Configured the example chain as TokenAPIs `gpt-5.6-sol` primary, then
  `gpt-5.6-terra`, `gpt-5.6-luna`, and NVIDIA `openai/gpt-oss-120b` fallback
  profiles. The chain is operational resilience, not a ranking signal.

## Verification

- Config secret-rejection and fallback-switch fixtures pass.
- The full standalone suite remains required before push; no live registry is
  published while the configured channels fail transport or response checks.
