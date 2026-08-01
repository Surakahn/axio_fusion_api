# Four-Protocol Instruction Priority Boundary

## Scope

This stage hardens the public request normalization boundary. It does not
change provider ranking, Fusion role allocation, benchmark datasets, model
selection, or the private channel credential store.

## Decision

- OpenAI Chat Completions `developer` messages are normalized to Axio's common
  system-instruction lane. They must not become ordinary `user` history when a
  request crosses into Responses, Anthropic, or Gemini providers.
- Multiple system/developer instruction texts are preserved in request order.
- OpenAI Responses `instructions` accepts a string or an array of text-only
  instruction messages/input-text items. Typed image/file instructions fail
  closed with `system_content_not_supported` before provider dispatch.
- Typed instruction objects are never converted with `str(...)`; this avoids
  sending Python representation text to a remote model.

## Implementation Anchors

- `src/axio_fusion_api/compat.py`: Responses instruction parsing and combined
  system-lane construction.
- `src/axio_fusion_api/tool_contract.py`: developer-role history mapping.
- `tests/test_content_contracts.py`: priority preservation, typed instruction
  normalization, and non-text rejection.
- `docs/api_protocols/`: protocol matrix, parameter reference, and integration
  guide updated to match the executable contract.

## Verification

```text
PYTHONPATH=src /home/he/.local/bin/python3.11 -m pytest -q
861 passed in 185.63s
compileall: passed
git diff --check: passed
tracked credential scan: no provider credential or private-key material added
```

The production serving registry remains hash-bound to the pre-Fusion admission
receipts. This change therefore cannot promote an unprobed provider or alter
the benchmark claim boundary.
