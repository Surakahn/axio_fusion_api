# r44 catalog attestation and screening plan

## Scope

This stage repairs the evidence boundary between pre-Fusion generation and
non-target provider baseline screening. It does not alter Fusion prompts,
router weights, capability priors, screening cases, scorers, decoding, or
benchmark policy.

## Control-plane changes

- Available-model generation now carries an allowlisted provider catalog
  attestation. The private form retains only provider/model aliases needed for
  exact identity checks, status/count fields, and endpoint hashes; response
  bodies, raw URLs, credentials, and output content remain excluded.
- Generation-bound probe projection carries that attestation forward. A
  historical generation artifact without the field remains projectable, but
  cannot satisfy the later exact catalog identity gate by inference.
- Provider identity matching normalizes only provider slugs by case-folding and
  replacing underscores with hyphens. Model aliases remain literal exact
  matches; suffix, namespace, display-name, and fuzzy model mappings remain
  prohibited.

## r44 evidence

- The unchanged r43 probe-bound registry remains the serving/screening input.
- A fresh non-target `/models` revalidation covers the current provider
  catalogs and binds a private r44 catalog-bound probe artifact. Identity
  validation covers all 10/10 r43 physical profiles after provider-slug
  normalization.
- The r44 plan binds the registry, catalog-bound probe, source manifest,
  adapter/scorer/transport implementation, selection seed, task order, and
  serial worker count. It contains 10 canonical groups, 10 physical profiles,
  two source families, 20 tasks, and 2,200 estimated provider calls.
- Zero-network preflight completed with `status=preflight_ready`,
  `max_workers=1`, and zero provider/target-suite calls.
- Live screening is isolated under the r44 private root. Partial checkpoint
  data is not ranking evidence and cannot be merged with any prior cohort.

## Verification

- Focused control-plane tests: 66 passed.
- Full standalone regression: 1,013 passed.
- Python 3.11 compilation and `git diff --check`: passed.

The campaign remains incomplete. External rank 1/2/3 baseline freeze,
official/audited harness imports, the independent 9-category/21-suite
campaign, latency gates, and all superiority claims remain closed.
