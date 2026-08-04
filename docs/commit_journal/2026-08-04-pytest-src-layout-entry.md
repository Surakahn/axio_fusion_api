# Standard pytest entrypoint

## Change

Added the standard pytest `pythonpath` configuration to `pyproject.toml` so a
fresh checkout can run `python3.11 -m pytest -q` without relying on an
operator-exported `PYTHONPATH` or an editable install.

## Verification

The unqualified project entrypoint now completes successfully:

```text
python3.11 -m pytest -q
941 passed in 188.36s (0:03:08)
```

This is a test-runner ergonomics fix only. It does not change provider
transport, runtime routing, prompts, benchmark data, or the active r20 live
screening process.
