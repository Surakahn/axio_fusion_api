# Axio Fusion API Product Boundary

Axio Fusion API is a standalone, remote-only model composition service. It
turns a changing set of provider endpoints into one stable public model family:
`axio-fast`, `axio-terra`, and `axio-pro`.

The service does not train weights, run a local model, or require ASciFS. ASciFS
or any other application may consume Axio over HTTP, but Axio is developed,
configured, tested, and operated from this repository as an independent
component.

## Product Contract

Axio accepts provider model profiles through a configuration-driven registry.
Each profile may use one of four upstream formats:

- OpenAI Chat Completions
- OpenAI Responses
- Anthropic Messages
- Google Gemini GenerateContent

Physical replicas that expose the same canonical model identity are one logical
model. Replicas are used for load balancing and failover; they are never counted
as independent Fusion votes.

The public model family is deliberately small:

- `axio-fast`: the smallest bounded route that meets the task and latency
  budget.
- `axio-terra`: selective independent solving, verification, or critique when
  a second view is likely to add information.
- `axio-pro`: a bounded expert panel, Judge, targeted repair, and acting
  Synthesizer for difficult or high-risk work.

The public gateway exposes all four streaming protocol surfaces:

| Surface | Endpoint |
| --- | --- |
| Chat Completions | `POST /v1/chat/completions` |
| Responses | `POST /v1/responses` |
| Anthropic Messages | `POST /v1/messages` |
| Gemini GenerateContent | `POST /v1beta/models/{model}:generateContent` or `POST /v1/models/{model}:generateContent` |

The same normalized request contract drives each surface. The adapters only
change wire representation, event framing, authentication headers, and the
protocol-specific reasoning/tool fields. The Fusion route is not reselected
merely because a caller used a different public protocol.

The image lane is separate from text Fusion. Profiles marked as image models
may serve image generation and editing through the dedicated Images routes;
image artifacts are not passed into text candidate, Judge, or Synthesizer
stages as if they were language-model answers.

For the current CPA Plus enrollment, `gpt-image-2` is discovered from the
Responses-compatible channel but is routed through its separately verified
OpenAI Images-compatible generation/editing paths. The image registry is
promoted only after independent streamed generation and multipart-edit probes
pass the 90-second ceiling. Prompt composition is an optional text-model
preparation step performed after image capability admission; it cannot run when
the image lane is unavailable and it never turns an image request into a text
Fusion answer.

## Composition Runtime

The runtime is a bounded orchestration graph:

```text
public streaming request
        -> protocol normalization and admission
        -> task analysis, tier policy, deadline and call budget
        -> canonical-model routing and replica failover
        -> role-scoped references and specialist work
        -> Judge / verifier when admitted
        -> acting Synthesizer when required
        -> protocol-specific incremental stream
```

Role prompts and context assembly are explicit configuration artifacts. A
candidate receives only the context needed for its role; provider errors,
internal identifiers, prompts, secrets, and raw outputs do not appear in public
receipts. The finite Harness building blocks can be recomposed by reviewed
configuration, while the runtime code that enforces isolation, deadlines,
streaming, and safety cannot rewrite itself.

The implementation borrows principles from Fugu, OpenRouter-style Fusion, and
Hermes/MoA systems: complementary roles, bounded fan-out, evidence-aware
selection, structured adjudication, and a single acting answer owner. It does
not assume that more requests imply better intelligence. Complementarity,
co-failure, cost, reliability, and latency are measured before a route is
promoted.

## Provider Onboarding

Use a non-secret provider manifest. Base URLs, API keys, and optional model
lists are referenced by environment-variable names; values are resolved only
in process memory. The example manifests are:

- `config/provider_configs.example.json` for arbitrary providers and all four
  formats.
- `config/current_channels.example.json` for the current NVIDIA Chat
  Completions and CPA Plus Responses/Anthropic channel shapes, including the
  candidate `gpt-image-2` image lane.
- `config/research_agent.example.json` for the pre-Fusion research-ranking
  agent.

The recommended sequence is:

1. Discover the configured inventory.
2. Research and rank formal language models using public, non-target evidence.
3. Probe strict streaming behavior with multiple samples.
4. Exclude profiles whose observed stream cannot satisfy the 90-second limit.
5. Bind the resulting evidence to a private runtime registry.
6. Activate the registry only after provider and operational admission gates.

Use the standalone CLI from the repository root:

```bash
PYTHONPATH=src python3.11 -m axio_fusion_api.cli \
  --provider-config-file config/current_channels.example.json \
  pre-fusion-screen --live \
  --focus-manifest config/nvidia_focus_models.json \
  --source-manifest config/public_model_sources.example.json \
  --research-agent-config config/research_agent.example.json \
  --output private/prefusion.screened.private.json \
  --registry-output private/fusion-runtime-registry.private.json
```

For production serving, use a registry produced by the pre-Fusion handoff and
require live admission:

```bash
PYTHONPATH=src python3.11 -m axio_fusion_api.cli \
  --registry private/fusion-runtime-registry.private.json \
  serve --host 127.0.0.1 --port 8789 --live
```

The default network policy is `auto` with proxy
`http://127.0.0.1:10808`: a listening local proxy is used, otherwise direct
connection is used. `on` requires the configured proxy and `off` forces a
direct connection. Provider streaming calls have a 90-second admission
ceiling; a profile that exceeds it is not eligible for the Fusion serving
list.

The optional image registry is configured independently through
`AXIO_FUSION_IMAGE_REGISTRY_PATH`. It must be produced by `image-probe-bind`;
an unverified or mixed text/image registry is rejected at startup. Without
that variable, image endpoints remain available as a stable 503 capability
response and do not invoke text Fusion.

## Runtime Safety

The following are product invariants:

- no local weight inference or training;
- no import from ASciFS runtime packages;
- no API key, raw prompt, benchmark label, raw provider output, or raw image
  content in repository evidence artifacts;
- provider replicas do not inflate logical model vote counts;
- call budgets and shared deadlines protect mandatory Judge/Synthesizer stages;
- public protocol errors are normalized and internal provider details are
  redacted;
- benchmark evaluation is an external client of the HTTP gateway, not an
  input to production routing or prompt tuning.

## Independent Evaluation Boundary

Benchmark execution is intentionally separate from the Fusion runtime. The
evaluator loads the Axio base URL, client key, and one of the four public
protocols just like any other client. It does not inject labels into prompts,
does not alter route policy, and does not feed scores back into the live
service.

The current locked matrix contains 9 categories and 21 suites:

- science knowledge: GPQA Diamond, MMMU text science;
- multilingual: Global-MMLU Lite, FLORES translation;
- code: LiveCodeBench, HumanEval;
- mathematics: MATH-500, recent AIME;
- logic: BBH, ARC-Challenge;
- agentic tool calling: BFCL, tau-bench;
- daily work: IFEval, MT-Bench work;
- hallucination/factuality: TruthfulQA, HaluEval;
- vertical domains: MedQA-USMLE, FinanceBench, LegalBench, BizBench, and
  PolicyBench.

The asset root is `/mnt/storage/axio_fusion_benchmarks`, outside the source
tree. The evaluation contract requires fixed case hashes, identical decoding
and prompts for paired candidates, official or audited harness imports for
code/tool/pairwise suites, paired case-level statistics, Holm correction,
practical effect sizes, contamination checks, four-surface parity, and p50/p95
latency no more than three times the corresponding single-model baseline.

GPQA remains explicitly gated when authorized access is unavailable. A
replacement is reported by its real identity and never relabeled as GPQA.
Likewise, downloading a harness repository is not treated as a scored harness
run: the pinned six-suite official/audited import gate must be satisfied before
those suites enter a claim.

No superiority claim is valid until the complete provider candidate pool has
been screened, rank 1/2/3 baselines have been externally evidenced and frozen,
all permitted suite gates have passed, and the independent paired campaign
supports the claim.

## Operational Evidence

Safe evidence is written below `private/` or the mechanical-disk benchmark
root. It contains hashes, counts, status, reason codes, and audit receipts;
private runtime files may contain process-local credentials and raw provider
responses but are ignored by Git and must never be published.

The primary operating documents are:

- `PLAN.md` for the frozen convergence path;
- `docs/operations/convergence_execution_path_r20.md` for the current gate
  order;
- `docs/operations/prefusion_convergence_supervisor.md` for low-frequency
  screening continuation;
- `docs/pre_fusion_model_screening.md` for provider research and admission;
- `docs/axio_fusion_benchmark_methodology_21_suites.md` for the independent
  benchmark protocol.

The repository's engineering tests are the first gate. They prove contracts,
not model superiority. Live provider evidence and the independent benchmark
campaign are required for any quality claim.
