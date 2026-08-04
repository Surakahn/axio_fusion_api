# Offline regression revalidation

## Verification

The complete repository regression was rerun with the project's `src`-layout
entry point:

```text
PYTHONPATH=src python3.11 -m pytest -q
941 passed in 189.23s (0:03:09)
```

The run completed with exit code 0 and made no provider requests. A bare
`pytest -q` invocation was also checked; it fails during collection because
the package is intentionally kept in a `src` layout and the caller did not
provide `PYTHONPATH=src`. That invocation did not execute tests and is an
operator-entry error, not a product regression.

## Boundary

This receipt verifies engineering behavior only. It does not claim provider
baseline readiness, benchmark completion, or Axio superiority. The active r20
screening process remains independent and unchanged.
