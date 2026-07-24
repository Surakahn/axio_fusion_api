# Provider Identity Scout: 2026-07-18

## Decision

Do not fill the private external top-three ranking manifest yet. The current
four live profile hashes have plausible public model identities, but the
evidence found does not provide two independent, non-target-suite general
capability ranking source families that cover every candidate. A single
leaderboard or a provider catalog cannot satisfy the pre-registered baseline
contract.

This is a baseline-freeze decision, not a service availability or benchmark
result. No target-suite item, label, score, or provider output was used.

## Current Frame

The Fusion service is engineering-ready for the separate 21-suite validation
phase. Its live provider pool currently has four live-probed profile hashes.
Before any target-suite call, Axio must freeze exactly three single-model
baselines from that complete pool. The freeze requires:

- a channel-side attestation that each routed alias maps to the claimed public
  model/version;
- at least two independent non-target general-capability ranking source
  families shared by every live candidate;
- an external rank and ranked population count for each candidate/source pair;
- source snapshots and retrieval dates; and
- deterministic normalized-percentile aggregation before the target campaign.

## Evidence Ledger

| Evidence class | Source | Result | Allowed use |
| --- | --- | --- | --- |
| Official model identity | [OpenAI GPT-5.5 model docs](https://developers.openai.com/api/docs/models/gpt-5.5) | Public official model page found. | Candidate identity corroboration after channel attestation. |
| Official model identity | [OpenAI GPT-5.6 Terra model docs](https://developers.openai.com/api/docs/models/gpt-5.6-terra) | Public official model page found. | Candidate identity corroboration after channel attestation. |
| Official model identity | [OpenAI GPT-5.6 announcement](https://openai.com/index/gpt-5-6/) and [Sol preview](https://openai.com/index/previewing-gpt-5-6-sol/) | Official search results identify the Sol tier. | Candidate identity corroboration after channel attestation. |
| Official model identity | [NVIDIA Hugging Face model API](https://huggingface.co/api/models/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16) | Public `nvidia` organization record returned the matching Nemotron family and a pinned revision. | Candidate identity corroboration after channel attestation. |
| Independent catalog identity | [OpenRouter public model catalog](https://openrouter.ai/api/v1/models) | One catalog response listed all four canonical model ids, including the exact Nemotron API id. | Cross-check identity/configuration only; not a rank source. |
| Independent capability source | [Artificial Analysis GPT-5.6 Sol](https://artificialanalysis.ai/models/gpt-5-6-sol), [Terra](https://artificialanalysis.ai/models/gpt-5-6-terra), [GPT-5.5](https://artificialanalysis.ai/models/gpt-5-5), and [Nemotron](https://artificialanalysis.ai/models/nvidia-nemotron-3-super-120b-a12b) | All four public model pages resolved on the scout date. | One candidate common ranking-source family, subject to later archived snapshot/rank/population extraction. |
| Disconfirming search | LMArena and LiveBench exact-name searches | No authoritative common ranking table covering all four candidates was recovered. | Reject as a common source family for this freeze. |

Search-engine result pages are discovery aids only. They are not evidence rows
for the private ranking manifest. Every retained source must be fetched and
snapshotted directly when the operator prepares that manifest.

## Why The Freeze Remains Blocked

The public catalog and official pages support a plausible canonical identity,
but they do not prove that a third-party channel alias executes that exact
model/version. The channel operator must provide an attestation or other
verifiable mapping for each live profile hash. In addition, Artificial Analysis
is only one common independent capability-ranking family. The contract requires
two common families with stable snapshots and population counts; substituting
marketing claims, a catalog listing, latency, or target-suite outcomes would
contaminate the comparison.

## Next Anchor

Use the existing `benchmark-external-ranking-template` as the private operator
input after obtaining channel identity attestations and a second qualifying
common source family. Then run `benchmark-provider-baseline-freeze` and verify
that it derives, rather than accepts, ranks 1/2/3. Until that succeeds, retain
the current strict campaign preflight block and do not run any target-suite
benchmark as a final-comparison campaign.
