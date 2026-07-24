# Axio Fusion API Product Boundary

Axio Fusion API is a standalone commercial model facade.  ASciFS can consume it,
but the service is not an ASciFS-internal smoke tool and does not require the
paper metadata database, graph database, Studio UI, or research workflow
artifacts to run.

## Product Shape

- Product id: `axio-fusion-api`
- Public model family: `Axio`
- Public model tiers: `axio-fast`, `axio-terra`, `axio-pro`
- Public protocols:
  - OpenAI legacy Completions: `POST /v1/completions`
  - OpenAI Chat Completions: `POST /v1/chat/completions`
  - OpenAI Responses: `POST /v1/responses`
  - OpenAI Responses compact alias: `POST /v1/responses/compact`
  - Anthropic Messages: `POST /v1/messages`
  - Anthropic token count: `POST /v1/messages/count_tokens`
  - Gemini generateContent: `POST /v1beta/models/{model}:generateContent`
  - Gemini generateContent: `POST /v1/models/{model}:generateContent`
  - Gemini streamGenerateContent: `POST /v1beta/models/{model}:streamGenerateContent`
  - Axio prompt-free route plan: `POST /v1/axio/route-plan`
  - Axio prompt-free feedback: `POST /v1/feedback`
- Runtime control endpoints:
  - `GET /v1/models`
  - `GET /v1/models/{model}`
  - `GET /v1/health`
  - `GET /v1/axio/production-readiness`
  - `GET /v1/smoke`

## Standalone Boundary

The product may share provider adapters, redaction helpers, and the model-fusion
routing core from this repository while it is developed in-tree.  Its runtime
contract is independent:

- No ASciFS research output is required.
- No paper database is required.
- No graph/vector database is required.
- No Studio UI is required.
- No benchmark examples or labels are inserted into prompts.
- No new model weights are trained.
- Prompt/source text and secrets are not persisted by audit logs or readiness
artifacts.
- It can be moved into another project and fed a new provider model inventory
  plus capability evidence; the public facade still emits `axio-fast`,
  `axio-terra`, and `axio-pro`.

## Capability Discovery Workflow

Before `axio-terra`/`axio-pro` are exposed as serious model products, Fusion API runs a
portable pre-fusion workflow:

1. Discover a provider/model inventory from explicit environment configuration
   or an opt-in provider `/models` call.
2. Normalize all supplied model endpoints into a provider/model inventory.
3. Attach public model cards, official benchmark claims, pricing notes, and
   operator observations when available.
4. Probe endpoints only for availability, output shape, latency, and minimal
   sanity when requested.
5. Build a capability graph over language, science, math, code, logic,
   agentic/tool-use, cost, latency, and reliability axes.
6. Select missing or non-comparable axes for benchmark execution from the
   mechanical-disk cache.
7. Measure branch complementarity with per-case agreement and co-failure
   summaries before promoting a multi-model panel.
8. Synthesize `axio-terra`/`axio-pro` from the resulting capability graph.

The command is:

```bash
axio-fusion-api bootstrap \
  --provider cpa-plus \
  --provider nvidia \
  --provider ollama \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

The equivalent expanded commands are:

```bash
axio-fusion-api provider-inventory \
  --provider cpa-plus \
  --provider nvidia \
  --provider ollama \
  --output-dir outputallresult

axio-fusion-api capability-discovery \
  --inventory outputallresult/fusion_api_product/provider_model_inventory.json \
  --public-evidence public_model_evidence.json \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

This workflow is independent from ASciFS research artifacts.  It does not need
the paper database, graph database, Studio UI, or Harness.

## Commands

```bash
axio-fusion-api product-manifest --output-dir outputallresult
axio-fusion-api bootstrap \
  --provider cpa-plus \
  --provider nvidia \
  --provider ollama \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
axio-fusion-api provider-inventory \
  --provider cpa-plus \
  --provider nvidia \
  --provider ollama \
  --output-dir outputallresult
axio-fusion-api capability-discovery \
  --inventory outputallresult/fusion_api_product/provider_model_inventory.json \
  --public-evidence public_model_evidence.json \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
axio-fusion-api openapi --output-dir outputallresult
axio-fusion-api readiness --output-dir outputallresult
axio-fusion-api benchmark-run-matrix \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
axio-fusion-api benchmark-download \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
axio-fusion-api benchmark-live-readiness \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
axio-fusion-api benchmark-dataset-receipt \
  --suite gpqa_diamond_science_reasoning \
  --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/gpqa_diamond_science_reasoning/gpqa.jsonl \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
axio-fusion-api benchmark-runbook \
  --suite gpqa_diamond_science_reasoning \
  --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/gpqa_diamond_science_reasoning/gpqa.jsonl \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
AXIO_FUSION_BENCHMARK_ENABLE_LIVE=1 axio-fusion-api benchmark-run \
  --suite gpqa_diamond_science_reasoning \
  --candidate-id axio-terra \
  --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/gpqa_diamond_science_reasoning/gpqa.jsonl \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --live
AXIO_FUSION_BENCHMARK_ENABLE_LIVE=1 axio-fusion-api benchmark-batch-run \
  --suite gpqa_diamond_science_reasoning \
  --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/gpqa_diamond_science_reasoning/gpqa.jsonl \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --reuse-existing \
  --live
axio-fusion-api serve --host 0.0.0.0 --port 8787 --production
```

The main ASciFS CLI still exposes compatibility commands such as
`axio serve-fusion-api`, but the commercial product boundary should use the
standalone `axio-fusion-api` command.

## Production Environment

- `AXIO_FUSION_MODEL_REGISTRY_PATH`: optional JSON model registry.
- `AXIO_FUSION_API_MODE`: `production`, `live`, or `dry-run`.
- `AXIO_FUSION_API_KEYS`: comma-separated bearer or `x-api-key` tokens for clients.
- `AXIO_FUSION_API_RATE_LIMIT_RPM`: per-principal request limit.
- `AXIO_FUSION_API_MAX_CONCURRENT_REQUESTS`: server-side concurrency cap.
- `AXIO_FUSION_API_MAX_BODY_BYTES`: request body size limit.
- `AXIO_FUSION_API_AUDIT_LOG_PATH`: prompt-free JSONL audit log path.
- `AXIO_CPA_PLUS_BASE_URL` and `AXIO_CPA_PLUS_API_KEY`: CPA Plus Responses API.
- `AXIO_NVIDIA_API_KEYS`: NVIDIA/OpenAI-compatible provider keys.
- `AXIO_FUSION_BENCHMARK_ENABLE_LIVE`: extra live benchmark safety gate.

API keys and provider secrets must stay in environment/configuration systems and
must not be committed.

`provider-inventory` follows the same rule. Dry-run mode reads only explicit
model-list environment variables such as `AXIO_NVIDIA_MODELS`,
`AXIO_CPA_PLUS_MODELS`, and `AXIO_OLLAMA_MODELS`. Live mode is opt-in and may
call configured `/models` endpoints, but its artifact stores only model names,
provider family, interface mode, key counts, and non-secret base URL hashes.
Raw API keys, raw local gateway URLs, and raw provider responses are not
persisted.

`bootstrap` additionally writes a prompt-free benchmark run matrix by default.
This is still only a control-plane artifact: it reserves per-suite/per-candidate
paths under the benchmark cache and records the scorecard contract, but it does
not download benchmark data or call provider models. Use
`--no-benchmark-run-matrix` when a deployment wants inventory/capability
artifacts only.

## Benchmark Gate

`axio-terra` and `axio-pro` benchmark claims are gated by reproducible artifacts, not
by static registry scores.  The run matrix reserves per-suite, per-candidate
`case_results.jsonl` paths under the benchmark cache root for `axio-terra`,
`axio-pro`, and each selected single-model CPA Plus/NVIDIA baseline.  The
scorecard may claim:

- `axio-terra` only after imported official per-case results beat the second
  best available single-model baseline.
- `axio-pro` only after imported official per-case results beat the best
  available single-model baseline.

Benchmark questions, labels, raw prompts, provider secrets, and generated large
case outputs stay outside git.  Only manifests, aggregate metrics, and
anti-cheating receipts are suitable for repository artifacts.

The required benchmark coverage uses two representative suites per area:

- Math: `math_500_competition_math`, `aime_recent_math_reasoning`
- Science knowledge: `gpqa_diamond_science_reasoning`,
  `mmmu_science_multimodal_optional`
- Code: `livecodebench_code_reasoning`, `humaneval_code_generation`
- Logic reasoning: `bbh_logic_reasoning`, `arc_challenge_reasoning`
- Agentic/tool-use: `bfcl_tool_calling`, `tau_bench_agentic_workflow`

Benchmark datasets, external runners, and generated outputs live under the
mechanical-disk benchmark cache such as
`/mnt/storage/ASciFS/axio_benchmarks`.  Repository artifacts only contain
manifests, hashes, aggregate metrics, and path receipts.

`axio-pro` must not assume that “more models” automatically means better output.
The benchmark scorecard must also track per-case agreement, branch diversity,
and co-failure rates.  If the candidate branches tend to fail on the same cases,
the router should prefer the strongest single model plus a verifier instead of
paying for a panel that cannot add information.

The current scorecard consumes prompt-free per-case result rows keyed by
`case_id_hash`.  It reports aggregate accuracy/cost/latency plus co-failure
rate, partial-disagreement rate, candidate-pair disagreement, and a
`panel_promotion_ready` decision.  Missing case overlap, high co-failure, or no
branch disagreement blocks Axio panel promotion even when aggregate rows exist.

## Fusion References

Axio borrows implementation principles, not vendor code, from:

- SakanaAI Fugu: OpenAI-compatible facade over dynamic multi-model and
  multi-agent coordination.
- OpenRouter Fusion: panel-style multiple model calls, judge comparison, and
  final synthesis for hard tasks.
- Operator-provided Fusion analysis:
  `https://blog.csdn.net/weixin_45888077/article/details/161985171`, used as
  product-design guidance around cost, latency, and quality tradeoffs.
- Multi-agent co-failure evaluation:
  `https://arxiv.org/abs/2602.00370`, used as a guardrail that panel fusion
  must prove error complementarity, not merely call more models.

The resulting Axio design rules are:

- Public callers see a small stable model surface: `axio-fast`, `axio-terra`,
  and `axio-pro`. Provider names and branch composition remain internal control
  plane state.
- Easy requests use a cheap/fast route first. Hard requests may fan out to a
  bounded panel, but only when the capability graph predicts complementary
  strengths.
- Panel synthesis is judge-mediated. The judge input is structured branch
  metadata and answers, never benchmark labels or repository-stored raw prompts.
- Recursive fusion is opt-in and bounded. The commercial default avoids nested
  Fusion calls that can amplify latency, cost, and correlated failures.
- Benchmark evidence is promoted through receipts, runbooks, per-case result
  files, aggregate scorecards, and co-failure checks. Static marketing claims or
  registry priors are not enough to claim `axio-terra`/`axio-pro` superiority.

The first live runner is intentionally narrow: it supports GPQA/MMLU-Pro style
multiple-choice JSONL/JSON/CSV slices, defaults to 20 cases, executes serially,
and refuses provider calls unless both `--live` and
`AXIO_FUSION_BENCHMARK_ENABLE_LIVE=1` are set.

Use `benchmark-batch-run` to run the same slice across `axio-terra`, `axio-pro`, and
the configured CPA Plus / NVIDIA provider baselines from the run matrix. It
writes per-candidate JSONL under the cache root, merges them into
`merged_case_results.jsonl`, and emits a scorecard only from the measured
per-case outputs.

Use `benchmark-live-readiness` before a real live run.  It defaults to a static
environment readiness check and records only provider/model names, base URL
hashes, API-key counts, blockers, and optional probe hashes.  It never writes
actual API keys, raw probe prompts, or provider response text.  Add
`--reuse-existing` to live benchmark runs to skip candidates whose cache-root
`case_results.jsonl` already covers the requested case hashes; add `--rerun`
when a measured result must be replaced deliberately.

Use `benchmark-dataset-receipt` before any live benchmark execution.  The
receipt records dataset path, cache-root placement, file size, file hash,
supported format, usable case count, labeled/unlabeled counts, and blockers. It
does not write benchmark questions, options, labels, raw prompts, or secrets
into repository artifacts.

Use `benchmark-runbook` as the commercial operator handoff. It combines the
dataset receipt, run matrix, and live readiness into one status report and emits
the next safe commands for download/materialization, dataset receipt refresh,
dry-run batch, readiness check, and gated live batch. If any blocker remains, the
runbook must not be interpreted as evidence that `axio-terra` or `axio-pro` beat
their baselines; only the live measured scorecard can make that claim.
