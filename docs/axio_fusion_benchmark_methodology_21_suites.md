# Axio Fusion 21-Suite Benchmark Methodology

## Scope

This document defines the evaluation contract for the Axio Fusion API system.
The benchmark matrix contains 9 categories and 21 suites:

- Science knowledge: `gpqa_diamond`, `mmmu_text_science`
- Multilingual: `global_mmlu_lite`, `flores_translation_instruction`
- Code: `livecodebench`, `humaneval`
- Math: `math_500`, `aime_recent`
- Logic reasoning: `bbh`, `arc_challenge`
- Agentic tool calling: `bfcl`, `tau_bench`
- Daily work skills: `ifeval`, `mt_bench_work`
- Hallucination and factuality: `truthfulqa`, `halueval`
- Vertical domains: `medqa_usmle`, `financebench`, `legalbench`, `bizbench`, `policyllm_policybench`

The mechanical-disk asset manifest is:

- `/mnt/storage/axio_fusion_benchmarks/manifests/benchmark_download_manifest_v3_21_suites.json`
- `/mnt/storage/axio_fusion_benchmarks/manifests/benchmark_sha256sums_v3_21_suites.txt`

The current materialization receipt has 14 suites ready for direct scoring. Six
suites (`livecodebench`, `humaneval`, `bfcl`, `tau_bench`, `ifeval`, and
`mt_bench_work`) are downloaded but remain blocked until their official or
audited harness runs are imported. `gpqa_diamond` remains blocked by gated
access. FLORES is currently materialized and ready. A blocked suite must never
be replaced with an unofficial mirror or silently removed from the declared
21-suite matrix.

## Frozen Evaluation Policy

The current formal policy records GPQA Diamond as `skipped` because authorized
access is unavailable. The GPQA slot may use the pinned `mmlu_pro_stem`
replacement only when its screening-disjointness receipt and source hashes are
valid. That result must be reported as **MMLU-Pro STEM**, explicitly not as
GPQA; the replacement identity cannot be hidden in an aggregate score.

The formal reasoning target is `max`, with the ordered capability scale
`low -> medium -> high -> xhigh -> max`. A provider `max -> high` mapping,
an unverified transport, or a recent rate-limit failure is recorded as a
downgrade or unavailable native capability. It cannot be silently promoted to
native `max`, and a superiority claim is blocked until the provider receipt
proves native `max` for the compared baseline. The Axio public adapters carry
the same logical `max` request through their protocol-specific fields, while
the public boundary receipt does not itself prove the upstream provider's
native implementation.

The pre-registered comparison roster is `gpt-5.6-sol` for `axio-pro`,
`gpt-5.6-terra` for `axio-terra`, and `gpt-5.6-luna` for `axio-fast`. This is a
target mapping, not a completed live result: the final claim still requires a
hash-bound provider freeze, live evidence, paired runs, statistical gates, and
the latency limit below.

## Candidate Matrix

All model answers must be produced through API calls, never by local shortcuts or direct evaluator injection.

Axio public candidates:

- `axio-fast`
- `axio-terra`
- `axio-pro`

Each Axio candidate must be evaluated through all four public API surfaces:

- OpenAI-compatible `chat/completions`
- OpenAI-compatible `responses`
- Anthropic-compatible messages API
- Google Gemini-compatible API

Provider single-model baselines:

- strongest available single model
- second strongest available single model
- third strongest available single model

The primary superiority claims are:

- `axio-pro` versus strongest available single model
- `axio-terra` versus second strongest available single model
- `axio-fast` versus third strongest available single model

The four Axio API-surface rows test both engineering compatibility and model-behavior invariance. The canonical ability comparison for each Axio tier is computed from the same locked case set and then audited across all four surfaces; a surface-specific failure blocks release even if one surface scores well.

## Anti-Cheating Rules

Benchmark data must never be used to train, fine-tune, optimize prompts, tune router weights, calibrate judge thresholds, create exemplars, or select per-suite model routes.

The following are forbidden:

- Putting gold labels, reference answers, official scoring scripts' hidden answers, or evaluator hints into model prompts.
- Using benchmark test cases as few-shot demonstrations.
- Manually editing model outputs before scoring.
- Selecting the best response among repeated samples after reading gold labels.
- Dropping failed, slow, refused, or malformed cases except under a predeclared evaluator-invalid rule.
- Replacing gated datasets with leaked mirrors.
- Comparing Axio and provider baselines on different case subsets.
- Using different decoding settings for Axio and baseline models unless the official harness requires it and the deviation is recorded.

Allowed inputs are the case prompt, public instructions, permitted tools for tool-use tasks, and benchmark-provided context that is part of the official question.

## Dataset Locking

Every suite run must bind:

- suite id
- official source URL
- local dataset path
- file sha256 or git commit
- case id hash
- prompt protocol hash
- decoding config hash
- evaluator version or official harness commit

For continuous or versioned datasets, such as LiveCodeBench, the version tag and time window must be locked before any model call. Different release windows must not be merged into one headline score.

For gated suites, the manifest remains `blocked_gated` until the user provides an authorized token or accepts the dataset terms. They are excluded from live claims only with an explicit blocked-suite note; the final 21-suite goal is not complete until they are legally available or explicitly waived.

## Prompt and Decoding Protocol

For each suite, create one canonical prompt builder that is shared by all candidates.

Default decoding:

- temperature: `0`
- top_p: `1`
- max output tokens: fixed by suite and large enough to avoid artificial truncation
- n: `1`
- no hidden chain-of-thought requirement

For code and math, models may produce concise reasoning if they choose, but only final answer / executable code is scored. For external-judge tasks, use position-balanced judging and a fixed judge model/protocol that is not one of the compared candidates unless the official benchmark requires otherwise.

## Metrics

Primary metrics by suite type:

- Multiple choice: exact option accuracy.
- Exact-answer math and logic: normalized exact match.
- Code: pass@1 with official tests or official harness import.
- Translation: chrF or official FLORES protocol once authorized.
- Tool calling: AST/function-call match and execution success where available.
- Agentic tasks: task success rate, tool error rate, and invalid-action rate.
- Instruction following: strict prompt-level and instruction-level accuracy.
- Pairwise work-skill judging: position-balanced win rate and judge score.
- Hallucination/factuality: truthfulness, informativeness where applicable, hallucination detection accuracy/F1.
- Vertical domains: official task metric where available; otherwise exact/normalized answer accuracy with domain-specific extraction rules.

All runs must also record:

- latency median and p95
- timeout rate
- invalid response rate
- refusal rate
- cost
- token counts

Latency gate:

- For each tier and suite, Axio median and p95 latency should not exceed 3x the corresponding single-model baseline.
- A tier cannot claim production-ready superiority if it wins accuracy but violates the 3x latency gate without an explicit suite-level waiver and evidence.

## Statistical Test

Use paired case-level comparisons.

For binary or pass/fail metrics:

- Use a one-sided exact sign test per suite and tier.
- Null hypothesis: Axio is not better than the corresponding single-model baseline.
- Alternative hypothesis: Axio is better.

For continuous judge scores:

- Prefer paired bootstrap confidence intervals and a paired permutation test.
- Report effect size and confidence interval, not only p-value.

Multiple comparisons:

- Family: all required suite-tier superiority claims.
- Size: `21 suites x 3 tiers = 63` once all gated suites are available.
- Correction: Holm-Bonferroni family-wise error-rate control.

A category-level win is not enough. The final claim requires suite-level evidence, corrected significance where statistically feasible, and no systematic regression in safety/format/latency gates.

## API-Surface Stability

For each Axio tier, run the same case hashes through:

- `axio-tier@chat/completions`
- `axio-tier@responses`
- `axio-tier@anthropic`
- `axio-tier@gemini`

Surface invariance checks:

- same model tier and fusion policy id
- same normalized prompt hash
- same decoding config hash
- no materially different score caused only by API adapter
- no systematic schema/streaming/tool-call incompatibility

Surface instability blocks completion of the Fusion API goal even if one API path scores well.

## Baseline Ranking

Before final evaluation, probe all usable supplier models from all configured providers.

Ranking must be based on a calibration set that is not part of the final benchmark case set. The ranking process may use:

- public model metadata
- provider-advertised model class
- a small non-benchmark calibration set
- previous sealed internal runs that do not include final benchmark labels

It must not use the final benchmark test labels to choose strongest, second strongest, or third strongest single-model baselines.

Once the three provider baselines are frozen, they remain fixed for the final campaign.

## Failure and Iteration Rule

If any Axio tier fails to beat its corresponding baseline, or violates the 3x latency gate, the system is not complete.

The next iteration must:

- run error analysis by category, suite, and failure mode
- identify whether failures are due to routing, candidate selection, judge synthesis, context assembly, prompt protocol, tool orchestration, or latency fan-out
- review current Sakana AI, OpenRouter, mixture-of-agents, router, verifier, debate, and model-selection methods from primary sources or official engineering references
- add only auditable algorithmic changes
- rerun affected smoke tests and then the full locked benchmark matrix

No final capability claim may be made until the locked 21-suite comparison supports it.
