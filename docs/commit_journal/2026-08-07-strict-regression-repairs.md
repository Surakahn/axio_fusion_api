# Strict Regression Repairs

## Scope

This record captures two full-suite regressions found while validating the
model-scoped reasoning transport milestone. Neither change alters Fusion
prompts, routing policy, provider enrollment, benchmark data, or a live
screening plan.

## Repairs

- The direct-profile deadline adapter now respects the latency budget already
  selected by the router. It still raises an implicit deadline when the
  calibrated direct profile requires it, but it no longer silently replaces a
  smaller computed route budget with the generic Fast default before applying
  the measured allowance.
- The pre-Fusion research Agent JSON parser now accepts exactly one JSON
  object, optionally inside one complete outer JSON fence. It no longer
  extracts an embedded fence from prose or accepts trailing commentary. This
  preserves the fixed output contract used before the research ranking merge.

## Verification

```text
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_fusion_core_regressions.py::test_implicit_fast_deadline_adapts_to_observed_direct_profile_latency \
  tests/test_model_screening.py::test_research_json_parser_allows_only_one_outer_json_fence \
  tests/test_reasoning_transport.py \
  tests/test_reasoning_reconciliation.py \
  tests/test_benchmark_policy.py \
  tests/test_content_contracts.py -q
```

Result: `73 passed`.

The complete standalone regression also passed with `988 passed in 194.84s`.
