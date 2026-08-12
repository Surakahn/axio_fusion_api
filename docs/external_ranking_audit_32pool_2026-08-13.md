# External Ranking Audit: 32-Model Pool (2026-08-13)

## Source Families

| Source | Snapshot | Ranked Population | Date |
|--------|---------|------------------|------|
| Chatbot Arena | arena_leaderboard.html | 678 rows (384 ranked) | 2026-07-19 |
| LiveBench | livebench_table_2026_06_25.csv | 39 models | 2026-06-25 |
| SimpleBench | simplebench_leaderboard-data.js | 93 models | 2026-07-19 |

## Coverage Matrix (32-Model Pool)

### Exact Identity Matches: 6/32
- deepseek-v4-flash, gpt-5.4, gpt-5.5, kimi-k2.6, minimax-m2.7, qwen3.8-max

### Fuzzy/Alias Matches with Known Naming Conventions: 26/32
The remaining 26 models are covered under documented alias conventions only.
Key discrepancies:

| Convention | External Source | Canonical |
|-----------|----------------|-----------|
| anthropic prefix | anthropicclaude-opus-5 | claude-opus-5 |
| nvidia namespace | nvidia-nemotron-3-super-120b-a12b | nvidia/nemotron-3-super-120b-a12b |
| effort suffix | gpt-5.6-sol-xhigh | gpt-5.6-sol |
| thinking suffix | claude-sonnet-5-thinking-32k | claude-sonnet-5 |
| provider prefix | z-ai/glm-5.2 | glm-5.2 |

### Combined Coverage

| Source | Exact | Alias | Total |
|--------|-------|-------|-------|
| Chatbot Arena | 6/32 | 21/32 | 27/32 |
| LiveBench | 6/32 | 14/32 | 20/32 |
| SimpleBench | TBD | TBD | TBD |

## Blockers (same as r43 audit)

1. `external_ranking_source_complete_pool_coverage_missing` — No single source covers all 32 models
2. `external_ranking_common_source_family_coverage_below_minimum` — Less than 2 common complete coverages
3. `external_ranking_exact_identity_attestation_missing` — Only alias mappings, not official model card attestations
4. `external_ranking_source_pre_registration_not_ready` — Sources not pre-registered

## Status

```text
template_only=true
ranking_assignment_present=false
```

No rank-1/rank-2/rank-3 baseline freeze is possible under current constraints.
The alias attestation document provides preliminary mappings but does not
constitute an official identity attestation.

## Alternative Path (recommended)

Run two independent, pre-registered, non-target evaluations over the complete
live-probed pool. The Axio Fusion project's own 351-question benchmark across
8 suites already provides one such evaluation. A second independent evaluation
from the 14-suite material or an external collaboration would satisfy the
dual-source requirement.
