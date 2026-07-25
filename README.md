# Axio Fusion API

> **Make model capability composable, portable, and measurable.**

Axio Fusion API is a remote-only model-fusion operating layer. Its purpose is
to turn a changing portfolio of provider APIs into one dependable intelligence
product: `axio-fast`, `axio-terra`, and `axio-pro`. It does not train a new set
of model weights and it does not depend on local GPU inference. It composes the
capabilities that already exist behind remote APIs through explicit prompts,
bounded Harness stages, routing policy, evidence handling, and a stable public
service contract.

## North Star: Capability Fusion As Product Infrastructure

The central idea is that a useful model product does not have to be identical
to any single model behind it. A portfolio can contain different kinds of
strength: one model may solve a difficult problem independently, another may
find counterexamples, a smaller model may reliably extract fields or validate
a tool argument, and an acting model may turn the surviving evidence into a
clear final response. Axio gives each capability a narrow job, assembles the
context deliberately, and exposes the result as one model family that an
application can trust.

This is a product and infrastructure thesis, not a claim that more requests
automatically produce more intelligence. The value is in the reusable
composition layer: provider capabilities become replaceable resources, while
the public product keeps its identity, protocols, quality gates, and operating
envelope. When a provider changes, a model is duplicated across channels, or a
new frontier model appears, the intended change is a controlled capability
enrollment and Harness reconfiguration rather than a rewrite of every client
integration.

The long-term goal is to make high-quality remote intelligence available in a
way that is more portable than a single-provider endpoint and more economical
than sending every task to the strongest model. Easy work can take a fast,
narrow route. Ambiguous or high-risk work can purchase independent evidence.
The system can fail over a physical provider replica without pretending that a
replica is a second independent mind. Every such trade-off must remain visible
through latency, cost, reliability, and evaluation receipts.

### The Product Horizon

`axio-fast`, `axio-terra`, and `axio-pro` are one capability ladder, not three
unrelated assistants:

- **Axio Fast** is the responsive path for everyday knowledge work, extraction,
  classification, concise coding help, and small tool steps. It uses the
  smallest bounded composition that can do the job well.
- **Axio Terra** adds selective independent solving, verification, or critique
  when a second view is likely to improve the answer without making latency
  unreasonable.
- **Axio Pro** is the deep path for difficult, high-risk, or high-value work:
  a bounded expert panel, structured adjudication, targeted repair, and an
  acting synthesis stage produce one answer under explicit deadlines.

The intended outcome is cost-aware quality that can approach or exceed the
capability of a single strong model on the tasks where composition genuinely
helps, while remaining useful when a channel is slow or unavailable. That
superiority is a hypothesis to be tested, never a marketing assumption: only
an independent, preregistered benchmark campaign can establish it.

### Why This Matters

Model progress is arriving faster than most software systems can safely change
their integration layer. Axio is meant to be the stable middle layer for
enterprise copilots, scientific and multilingual assistants, software
engineering and code review, document operations, agentic tool execution, and
regulated workflows in medicine, finance, law, consulting, and public policy.
Teams can keep one authenticated endpoint and one model family while the
operator changes the remote capability portfolio behind it.

The significance is practical: it reduces provider lock-in, creates a place to
encode expertise about model roles, makes graceful degradation a first-class
behavior, and turns prompt/context design into an inspectable engineering
artifact. It also creates a disciplined path to lower cost and better
availability without quietly lowering the quality bar. Providers supply model
capability; Axio owns the semantic contracts, context assembly, role isolation,
tool boundaries, evidence checks, streaming compatibility, and operational
receipts that make a mixed portfolio usable.

### The Guarded Improvement Loop

Axio is designed to improve through controlled configuration, not by rewriting
its own runtime code:

```text
configure remote channels
        -> research and screen model capabilities
        -> admit only measured streaming profiles
        -> compose bounded role prompts and Harness stages
        -> observe safe operational receipts
        -> calibrate with sealed hard-task checks
        -> promote only reviewed policy changes
```

Prompt fragments, role contracts, routing preferences, and finite Harness
building blocks are the intended adjustment surface. The runtime foundation
stays protected. A future channel can therefore be adapted by changing a
small, reviewable set of model profiles and composition policies, without
granting the service permission to alter the code that keeps it running.
Benchmark cases and labels remain outside this loop: the evaluation harness
consumes the public Axio APIs as an independent client and cannot become a
hidden source of routing instructions.

The result we are building is a model product layer with one public model
family, four industry-standard streaming API surfaces, provider-aware
routing, bounded deliberation, structured evidence handling, and a measurable
path from remote capability to dependable application behavior.

## The Product Idea

The central Axio thesis is simple:

```text
remote model capabilities
        + canonical identity and replica routing
        + role-scoped prompt and Harness composition
        + bounded independent deliberation
        + Judge / Synthesizer quality gates
        + protocol-compatible streaming gateway
        = one dependable Axio model family
```

This turns model diversity into an operational asset. A fast model can handle
classification or a narrowly defined tool step; a stronger model can provide
an independent solution; a critic can search for counterexamples and safety
risks; and an acting synthesizer can produce the single user-facing answer.
The system keeps these responsibilities explicit instead of pretending that a
large number of provider calls automatically means better intelligence.

## Why Axio Is Different

| Capability | Engineering value |
| --- | --- |
| **Remote-only execution** | Uses provider APIs as the model substrate. No local weights, hidden training loop, or GPU deployment assumption. |
| **Three product tiers** | `axio-fast` protects responsiveness, `axio-terra` spends bounded effort selectively, and `axio-pro` admits a deeper evidence panel only when it is justified. |
| **Canonical model identity** | Multiple channels exposing the same model count as one cognitive model, while remaining available as health-aware replicas. Redundancy improves availability without inflating intelligence. |
| **Hermes-style constrained MoA** | Reference models receive bounded, role-specific evidence tasks. Judge and acting Synthesizer stages remain explicit, budgeted, and auditable. |
| **Harness as configuration** | Prompt fragments, role contracts, DAG composition, and policy preferences are the adjustable Lego pieces. Runtime Python remains immutable and outside the self-improvement surface. |
| **Four protocol surfaces** | Chat Completions, Responses, Anthropic Messages, and Gemini GenerateContent can reach the same public Axio tiers through streaming-compatible adapters. |
| **Hard operational guardrails** | Provider calls have a 90-second ceiling, Fusion routes carry a 3x single-model latency guard, and budget/deadline reservations prevent an incomplete pipeline from being reported as complete. |
| **Evaluation boundary** | Benchmark execution is an external consumer of Axio, not a hidden routing input. Test labels, answers, and benchmark scores cannot steer production prompts or provider selection. |

## Architecture At A Glance

```text
                         public streaming APIs
          Chat / Responses / Anthropic / Gemini
                                  |
                        protocol-neutral request
                                  |
             +--------------------v--------------------+
             |              Axio Gateway                |
             | auth, normalization, streaming contract  |
             +--------------------+--------------------+
                                  |
             +--------------------v--------------------+
             |      Admission + Routing + Budgeting     |
             | task analysis, tier policy, 3x guard      |
             +--------------------+--------------------+
                                  |
             +--------------------v--------------------+
             |      Canonical Expert Panel Scheduler    |
             | identity de-dup, replica failover, roles  |
             +--------------------+--------------------+
                                  |
             +--------------------v--------------------+
             |       Hermes constrained deliberation    |
             | references -> Judge -> feedback -> act   |
             |             Synthesizer                  |
             +--------------------+--------------------+
                                  |
                 one coherent Axio response + safe receipt

   provider A / chat      provider B / responses      provider C / other
        model replicas          model replicas             model replicas
```

## Current Project Situation

The repository has been fully separated from the ASciFS project and is managed
as an independent Git repository. Fusion code, tests, plans, architecture
documents, provider configuration templates, screening workflows, and
evaluation-control code live here. ASciFS may consume Axio as an external HTTP
service or package boundary, but Axio does not import ASciFS runtime code.

The implementation already includes the protocol adapters, provider enrollment
and pre-Fusion screening path, streaming health probes, canonical replica
routing, model-role assignment, bounded panel repair, Hermes process receipts,
tool-call safety boundaries, response caching rules, and hash-safe operational
traces. The current engineering milestone is the live end-to-end deliberation
gate for Terra and Pro under the configured remote channels. The formal
21-suite, 9-category benchmark campaign is intentionally downstream of that
gate and is not represented here as a completed result.

That distinction is deliberate: passing unit tests proves software behavior;
it does not prove that a live Fusion pipeline is useful. Axio treats the live
Fusion gate, then the independent benchmark campaign, as separate claims that
must each earn their own evidence.

## Application Outlook

Axio is designed for environments where model choice changes faster than the
product interface: enterprise copilots, coding and review workflows, research
assistants, multilingual knowledge work, agentic tool execution, and regulated
decision support. Organizations can add or replace remote channels without
rewriting their public application integration. The provider-specific details
stay behind the enrollment and routing boundary; the product surface remains
the stable Axio model family.

The commercial promise is not “more calls at any cost.” It is **capability
composition with a measurable operating envelope**: stronger answers when
independent evidence is valuable, fast direct execution when fusion would not
pay for itself, bounded recovery when a channel fails, and receipts that make
every quality or latency claim inspectable.

## Standalone Boundary

Axio Fusion API is intentionally kept outside the ASciFS `axio` package. ASciFS
may call it over HTTP or install it as an external package, but the Fusion
service does not import ASciFS research workflow, paper database, graph
database, Studio UI, or memory code.

## Remote API Only

Axio is an API-only orchestration runtime. It does not download, load, train,
or serve local model weights. Every solver, Judge, Synthesizer, and tool-plan
review uses a configured remote HTTP(S) provider API. The local HTTP server is
only the public Fusion gateway; a loopback upstream is valid solely as a
development proxy or integration-test endpoint, never as a local-model
requirement.

`remote-api-execution-audit` makes this an engineering gate rather than a
documentation-only statement. It performs a network-free audit of the Fusion
package itself: forbidden local-inference imports and dependencies, local model
weight artifacts, remote URL-scheme enforcement, and the four provider input
adapters. It stores only counts, fixed reason codes, and digests.
The same audit is embedded in `fusion-system-readiness` and revalidated by the
strict live-campaign preflight before any benchmark provider call is allowed.

```bash
axio-fusion-api-standalone remote-api-execution-audit \
  --output <SAFE_WORK_DIR>/remote_api_execution_audit.safe.json
```

## Repository Boundary

All Fusion implementation, standalone tests, package metadata, plans, and
operator documentation live under this `axio_fusion_api/` directory:

- `src/axio_fusion_api/`: service implementation.
- `tests/`: standalone regression suite.
- `pyproject.toml`: independent package and console-script definition.
- `PLAN.md` and `CHECKLIST.md`: Fusion-only engineering and evaluation state.

The main ASciFS `axio/` package is a consumer boundary only.  New Fusion
algorithms, provider adapters, orchestration, routing, prompt assembly,
evaluation control, and public protocol behavior must not be implemented there.

## Public Surface

The service exposes one model family with three public tiers:

- `axio-fast`: direct fast cascade for simple, low-risk work, with a bounded
  light-verify route for high-quality, high-risk, uncertain, or tool-planning
  requests when the 3x latency guard allows it.
- `axio-terra`: cost-guarded selective fusion for balanced work.
- `axio-pro`: expert panel, structured judge, targeted escalation, and final
  synthesis for complex or high-risk work.

For admitted Terra/Pro provider-fusion routes, Axio also uses a Hermes MoA 2.0
process contract. A bounded parallel reference wave receives only a
deterministic user/assistant text projection and never receives the system
prompt, native tool schema, or executable tool-call/result objects. On later
tool iterations, prior tool actions and bounded result previews are rendered
as inert text so advisors can reason from observed evidence without gaining
tool authority. Parallel responses are restored to configured role-slot order
before Judge assembly, so network completion timing cannot change candidate
ordering or tie breaks. A failed physical channel is retried only against a
bounded replica of the same canonical model while retaining the same advisor
role and tool-free request; replicas never become extra independent evidence.
Reference projections, candidate packets, and normalized Judge packets also
have an explicit context-authority contract: they are untrusted data with no
instruction authority. Embedded role changes, policy claims, delimiters,
context-exfiltration requests, and tool directives cannot override the caller's
system message, original task, Axio tool policy, or acting-model contract. The
Judge assesses such content only as claims, and the Synthesizer independently
decides whether the authoritative original task warrants a tool call.
The Judge can request at
most one focused feedback-reference wave, after which the candidates are
re-judged and one acting Synthesizer owns the user-visible answer. Reference
failures are partial guidance rather than fatal errors, while budget, deadline,
replica, and 3x latency guards remain authoritative.

Hermes seats also carry explicit role-local cognitive and output budgets. The
budget is a protocol-neutral prompt and accounting contract: advisor output is
bounded, Terra and Pro Judge output is capped at 1,536 and 2,048 tokens before
the caller's smaller limit is applied, and the acting Synthesizer retains the
caller's output limit or provider default. Provider-private reasoning fields
are forwarded only after capability attestation, so adding a mixed-protocol
channel cannot introduce an unsupported request parameter. Reference fanout is
rebuilt per state iteration; cross-request user-turn reuse requires an explicit
admitted conversation scope.

High candidate agreement never bypasses that acting Synthesizer when Hermes is
enabled. An empty Synthesizer output falls back to the best surviving reference
answer but is explicitly marked as degraded and process-incomplete. Likewise,
a required feedback reference that cannot be scheduled, or one that fails
without the required re-Judge, may still yield a bounded answer, but it cannot
be reported as a completed Hermes process. The receipt records the Judge's
feedback requirement separately from feedback execution and successful output,
so a routing, budget, deadline, or provider gate cannot turn missing work into
an apparent no-feedback success.

When the Synthesizer's native tool capability has been proven by the separate
operational tool probe, the public tool schema is forwarded only to that acting
aggregator. Its native tool call is returned to the caller so the normal next
conversation iteration can carry the tool result through a fresh Hermes
process. Unproven tool capability disables Hermes aggregation for that tool
request and preserves the conservative existing tool-turn path. Recursive MoA
is always blocked.

The response cache is process-contract aware. A direct text answer is admitted
only after a recorded successful provider execution; a Fusion answer is
admitted only when `complete_admitted_fusion_finalized=true`; and a
Hermes-enabled answer additionally requires a completed Hermes process
contract. Degraded text, incomplete feedback/re-Judge paths, empty
Synthesizer fallbacks, and tool-call turns are never cached. A cache hit emits
a separate hash-safe origin-completion and replay receipt: the current request
still reports zero provider, Judge, and Synthesizer calls and never claims that
the Hermes process ran again. A changed Direct/Fusion/Hermes route contract
invalidates the cached entry before replay.

Compatible endpoints:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- `POST /v1beta/models/{model}:generateContent`
- `POST /v1beta/models/{model}:streamGenerateContent`

Public compatible responses expose only the Axio tier name and hash-only
metadata summaries.  Internal provider/model names stay in private operational
registries and operator-only debug surfaces; public response metadata, trace
receipts, probe evidence, and benchmark artifacts do not persist raw provider
names, provider model ids, provider URLs, API keys, prompts, labels, or provider
outputs.

`GET /v1/health` and `GET /v1/models` follow the same boundary.  Health reports
only a public registry-readiness projection: public model names, API-format
counts, provider/profile-set hashes, and safe readiness reason codes.  It never
returns an internal provider-format inventory, provider name, provider model id,
profile id, endpoint, credential environment name, or API key.  `/v1/models`
always lists only `axio-fast`, `axio-terra`, and `axio-pro`; it does not function
as a provider inventory endpoint.

The raw provider inventory endpoint is an operator-only diagnostic surface.  It
requires an explicitly configured `AXIO_FUSION_OPERATOR_API_KEYS` credential
even when ordinary public API authentication is intentionally disabled for a
local development server.  This prevents a permissive development default from
turning private provider/model configuration into a public discovery response.

## Provider Configuration

Before activating Fusion, run the pre-Fusion screening gate. It combines a
strict remote research-agent ranking with real streaming probes and emits the
only model list that may be activated by the runtime. See
[`docs/pre_fusion_model_screening.md`](docs/pre_fusion_model_screening.md),
`config/nvidia_focus_models.json`, and the non-secret research/source manifest
templates. A public-source rank remains an operational prior and is never a
benchmark result.

The dedicated control-plane command is `generate-available-models`. It emits
the fixed available-model generation artifact and can atomically publish the
validated private registry with `--registry-output`; `--handoff-output` can
write the matching private handoff artifact in the same publication step.
`pre-fusion-screen`
remains available as the lower-level diagnostic/report command; production
Fusion should consume only the ready handoff produced by the new wrapper.

Fresh production admission uses three independent strict-stream health samples
per physical profile by default. Configure `prefusion.stream_probe_samples` in
the non-secret channel manifest or pass `--prefusion-stream-probe-samples` to
the dynamic service command. A production setting below two is blocked; the
sample count is bounded to five. Every sample must produce a real SSE/NDJSON
frame, avoid the JSON fallback, contain a non-empty output digest, and finish
within 90 seconds. The registry binds the count, all-success receipt hash, and
observed p50/p95/max latency summary, so one lucky response cannot admit a
slow or intermittent channel.

The latest 2026-07-25 r3 serving cohort was rediscovered from the configured
channels and fully reranked before admission. It contains 136
physical/logical candidates, all with a completed research-prior record. Three
strict streaming samples admitted 29 profiles; 8 were rejected by the
90-second ceiling and 99 by stream/protocol stability. Forty-seven profiles
observed at least one real stream, while every admitted profile has exactly
three successful strict-stream samples; the slowest admitted sample was
86,712.071 ms. The ready handoff has complete `primary_solver`, `judge`, and
`synthesizer` role coverage. The public health projection reports a
`single_provider_model_pool` warning for this cohort, so channel availability
must be re-screened before a formal comparison campaign. This is an
operational eligibility cohort only: the research ranking remains forbidden as
benchmark evidence and does not determine the final provider top-three.

Research output is accepted only when its capability vector has evidence
coverage: a positive overall prior needs at least one nonzero capability axis,
and a broad prior (`overall >= 0.70`) needs at least three. Narrow, lower-score
models may remain available for a bounded specialist role, but are not
promoted to Judge or Synthesizer. This rule is checked again when the private
registry is loaded, so a legacy or edited all-zero-axis ranking cannot enter
the serving pool.

The gate hands Fusion both physical and logical views. The private `models`
array keeps every live-eligible channel profile for provider-aware routing and
same-model failover. `prefusion_screening.available_model_list` collapses
profiles sharing `canonical_model_id` into one ranked logical model and lists
its eligible replica hashes, role limits, observed latency summary, and
research capability prior. A profile over the 90-second response ceiling is
excluded from both views; a profile without an actual measured streaming
latency or a valid output digest is also excluded. The logical list exposes a
contiguous `available_rank` after this filter and keeps the complete-research
`research_prior_rank` separately. A channel replica is never counted as an
independent model vote. Fusion refuses to load this generated registry if any
profile binding is missing, duplicated, tampered, non-live, or inconsistent
with the logical list.

The logical latency summary uses `fastest_observed_latency_ms` and
`slowest_observed_latency_ms` across eligible replicas. A physical profile
admitted by the current multi-sample gate also carries measured p50, p95, and
maximum latency from its bounded probe samples. Historical one-sample receipts
remain readable only for migration and audit; they cannot be used to start a
new baseline-ranking or superiority campaign. In particular, the stopped v8
baseline-screening campaign is not model-comparison evidence because its
transport-failure rate exceeded the pre-registered limit.

Upstream channels are configuration-driven and support arbitrary remote
HTTP(S) base URLs through environment-variable references. The supported input
protocols are Chat Completions, Responses, Anthropic Messages, and
Gemini-compatible GenerateContent. See
[`docs/provider_configuration.md`](docs/provider_configuration.md),
[`config/provider_configs.example.json`](config/provider_configs.example.json),
and [`config/current_channels.example.json`](config/current_channels.example.json).

If several channels expose the same real model, assign them the same
`canonical_model_id`. Axio then treats them as one cognitive model with
multiple availability replicas: a Fusion panel includes at most one of them,
runtime routing prefers healthy low-latency replicas and balances comparable
ones, and failure recovery tries another same-model channel before crossing to
a different model. The service never stores actual endpoints or credentials in
the registry, route receipts, traces, templates, or source code.

The benchmark control plane applies the same identity rule. External baseline
ranking and final top-three freezes count canonical model groups, not provider
profiles. Hash-only replica sets, provider/API-format coverage, and per-replica
identity attestations remain bound to the group for audit. A legacy
`provider::<profile_hash>` benchmark alias still resolves to that model's full
replica pool; cases rotate deterministically across replicas and fail over only
within the same group before being marked unavailable. This prevents channel
redundancy from inflating the baseline population or silently changing which
model is being compared.

Caller-supplied `metadata` may carry public request policy such as privacy
classification and tool-call limits, but reserved `_axio_*` execution markers
are ignored at the gateway boundary. They are created only for private,
request-local orchestration turns. Response-cache keys also bind the complete
stop sequence and routing-relevant metadata, so a cache entry cannot cross a
privacy routing contract or a different generation stop condition.

Every expert branch is normalized into the same candidate contract before judge
or synthesis: `answer`, `reasoning_summary`, `evidence`, `assumptions`,
`uncertainties`, and `confidence`.  The live judge/synthesizer may receive
bounded in-memory candidate excerpts, but durable traces store only
standardization receipts such as parse mode, field counts, hashes, truncation
state, and missing-field labels; raw candidate text and raw reasoning summaries
are not persisted.

For decomposable Fusion runs, the router emits a role-scoped task DAG and the
executor records hash-safe task execution receipts per candidate.  These
receipts show which DAG nodes, dependencies, verification nodes, and checkpoints
each role covered, including domain-specialist subtask probes, without storing
the raw prompt or raw candidate text.

Panel selection is correlation-aware.  The router scores role fit, provider
diversity, API-format diversity, capability coverage, and capability
complementarity, then estimates panel error correlation from provider overlap,
API-format overlap, and capability-vector similarity.  Fusion admission gives
complementary panels a utility credit and applies a bounded penalty to highly
correlated panels, so Axio does not simply stack several near-identical models
when a smaller, more independent expert set is available.

The router also builds a hash-only quality-diversity archive for each request.
This Sakana-style niche map groups selected profiles by dominant capability
axis, API format, provider hash, and assigned role, then exposes only safe
quality/novelty estimates to runtime prompts and traces.  The corresponding
provider routing policy follows an OpenRouter-style local sort/fallback model:
availability, privacy eligibility, role fit, provider/API diversity, latency,
and cost determine the primary and fallback pool, while raw provider/model names
and URLs remain out of public artifacts.

Provider circuit health is likewise transport-specific: only an attempted
provider call that fails before a response is received increments its failure
counter.  Local call-budget, cost-budget, deadline, or routing-policy rejections
do not mark a provider unhealthy, so a constrained request cannot accidentally
open a circuit for later independent requests.

Within a running service, the router also maintains a bounded, in-memory
provider telemetry overlay.  After at least three real logical calls for a
profile, it smooths observed transport success and uses bounded p50/p95 latency
samples for subsequent routing.  The overlay never rewrites the operational
registry, never uses benchmark labels, resets on process restart, and exposes
only profile/provider hashes, counts, and aggregate values in safe route or
trace receipts.

When a complete Fusion plan approaches the latency contract, routing uses a
stricter 2.5x operating target as headroom: it may replace a slow expert or
mandatory stage only when the replacement meets the role capability floor,
stays within a bounded quality tolerance, and does not reduce provider
diversity. The final admission gate remains the hard 3x comparison against the
actual direct-route profile. This keeps the quality/latency tradeoff explicit;
it does not turn a slow or failed provider into a successful result.

Runtime prompts receive a safe routing-context packet in addition to the raw user
task: request analysis, quality target, risk and uncertainty, Fusion admission
utility, panel diversity, quality-diversity archive, provider routing policy,
budget policy, privacy/tool policy, and answer policy.
Expert, Judge, and Synthesizer calls can therefore adapt evidence standards,
uncertainty labeling, stop behavior, and synthesis depth without persisting raw
prompts, provider identifiers, model identifiers, provider URLs, or secrets in
durable traces.

The provider adapters preserve that assembled control packet on real HTTP calls.
When the public current user turn is already present in protocol-native history,
the Chat, Responses, Anthropic, and Gemini adapters inject the role, DAG, Judge,
or synthesis context into a valid current turn instead of silently dropping it.
Anthropic and Gemini merge it into an existing user tool-result turn when needed
to preserve native message ordering. The exact public task prefix is omitted
only from the provider-local duplicate packet when the same task is already in
history; custom in-process provider clients still receive the complete prompt.

### Responses continuation

`POST /v1/responses` supports standard `previous_response_id` continuation.
By default, each Responses result creates a tenant-isolated, process-memory
continuation keyed by its returned response ID. A later Responses request may
send only new `input` plus `previous_response_id`; omitted `model`,
`instructions`, and `tools` inherit from that prior turn. Function-call and
function-call-output events are retained in protocol-neutral order so a later
route can safely cross provider input formats.

Set `"store": false` to prevent creation of a new continuation. A retained
previous response can still be consumed by such a request, but its result is
not retained. Unknown, expired, evicted, and cross-tenant response IDs all
return the same `previous_response_not_found` error. Continuation data is never
written to trace receipts, feedback artifacts, benchmark artifacts, or runtime
snapshots; snapshots expose only aggregate counts and configuration bounds.
Responses cache hits receive a fresh public response ID, so each returned ID is
scoped to the caller's own continuation entry rather than to a cached compute
result.

For public native function calls, Axio arbitrates complete plans rather than
unioning calls from a Fusion panel. Only roles that received the caller's
function declarations may contribute a plan. Independent agreement across
providers takes precedence over a conflicting primary plan; otherwise the
primary plan wins. The selected provider call id is retained for the caller's
next tool-result turn, while the function name is normalized back to the exact
caller-declared schema name. The deferred tool turn returns before panel repair,
Judge, or synthesis can add unnecessary provider work. Trace and response
metadata expose only counts, roles, and hashes for this arbitration, never raw
tool names, arguments, call ids, or provider identities.
The same behavior applies when a targeted escalation discovers that a tool is
needed after an initial Judge: Axio returns the native call before a second
Judge or synthesis, while preserving the already-completed Judge's safe public
summary and call count.

When the provider Judge is skipped by budget, latency, or circuit guards, the
local Judge still builds hash-only answer-claim clusters.  It recognizes common
final-answer forms such as `final answer`, `answer is`, single choice letters,
and numeric conclusions, rewards independently supported claim clusters, and
suppresses false conflict reports when candidates phrase the same final answer
different ways.  Safe traces persist only claim hashes, support counts, and
support fractions.

The operator route-plan endpoint returns a `safe_route_plan` view rather than
the internal route object.  It keeps public model, strategy, request analysis,
budgets, Fusion admission, routing policy, role names, and selected-model
hashes, while redacting raw provider names, model ids, profile ids, URLs,
prompts, and secrets.

When Judge output reports missing coverage, contradictions, blind spots, or a
quality-target gap, the Orchestrator builds a bounded targeted-escalation plan
instead of rerunning the whole panel.  The plan selects at most the configured
escalation depth of local subtasks, records hash-safe focus labels and DAG node
receipts, and sends only that focused verification payload to the escalation
model.

## Quick Start

Axio Fusion requires Python 3.10 or newer. Use an isolated virtual
environment so an older system Python or a distribution-managed `pip` cannot
silently select an unsupported interpreter or fail to install the
`pyproject.toml` package in editable mode:

```bash
cd axio_fusion_api
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m axio_fusion_api.cli --help
axio-fusion-api-standalone serve --host 127.0.0.1 --port 8789
```

Official LiveCodeBench case-set binding reads the upstream Parquet metadata but
keeps questions and tests private. Install the optional evaluation dependency
before preparing that source manifest:

```bash
python -m pip install -e ".[dev,benchmark]"
```

Standalone regression:

```bash
cd axio_fusion_api
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/test_axio_fusion_api_standalone.py
```

Dry-run completion:

```bash
axio-fusion-api-standalone complete \
  --api-format chat/completions \
  --model axio-pro \
  --prompt "Design a safe model routing policy"
```

The four public surfaces have three separate protocol checks. The first is
fully offline and checks request/response compatibility. The second is an
explicitly opt-in, bounded non-streaming live smoke that uses the private
operational registry, disables response caching and durable execution traces,
and records only status, latency, output hashes, and redacted route receipts.
It does not use benchmark questions or make a quality/superiority claim. Each
request permits one primary provider call and at most one bounded direct-cascade
fallback, so the production recovery path is exercised without turning the
check into a Fusion-quality evaluation.

`api-surface-stream-live-smoke` is the stricter live counterpart. It executes
all three public Axio tiers through all four public API surfaces with streaming
requested, requires a real upstream provider call, checks SSE content type and
surface-native terminal events, and requires a non-empty streamed text result.
Chat Completions requires a finish chunk followed by `[DONE]`; Responses
requires `response.completed`; Anthropic requires `message_stop`; and Gemini
requires `finishReason=STOP` with `usageMetadata`. It stores only hashes,
counts, timing, and safe error codes. It verifies protocol plumbing and strict
upstream streaming, not first-token streaming latency, answer quality, or model
superiority.

`fusion-deliberation-live-smoke` is a separate, opt-in operator check for the
actual Fusion loop. It sends one synthetic non-benchmark task to `axio-terra`
or `axio-pro`, requires Fusion admission, multiple completed candidate branches,
a provider Judge call, and complete finalization. For a non-Hermes route this
means either a Synthesizer call or a controlled early exit. For a Hermes-enabled
route it requires the execution receipt to show an accepted acting Synthesizer
output and a completed Judge/feedback/re-Judge process contract; early exit is
not accepted as success.
It bounds total calls, time, output tokens, and cost; disables cache and durable
trace writes; and emits only hashes, counters, timing, and redacted public route
summaries. It verifies orchestration health only. It cannot establish answer
quality, benchmark superiority, or latency superiority.

```bash
axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  api-surface-protocol-self-test \
  --output <SAFE_WORK_DIR>/api_surface_protocol.safe.json

axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  api-surface-live-smoke \
  --live \
  --max-latency-ms 12000 \
  --max-output-tokens 48 \
  --output <SAFE_WORK_DIR>/api_surface_live_smoke.safe.json

axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  api-surface-stream-live-smoke \
  --live \
  --max-latency-ms 12000 \
  --max-output-tokens 48 \
  --output <SAFE_WORK_DIR>/api_surface_stream_live_smoke.safe.json

axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  fusion-deliberation-live-smoke \
  --live \
  --model axio-pro \
  --max-latency-ms 30000 \
  --max-output-tokens 128 \
  --max-total-model-calls 6 \
  --max-cost-usd 0.02 \
  --output <SAFE_WORK_DIR>/fusion_deliberation_live_smoke.safe.json
```

Without `--live`, either live-smoke command returns a safe blocked receipt and
makes no provider request. A live receipt verifies public API plumbing, strict
stream terminal semantics, or Fusion-loop orchestration only; the separate
21-suite campaign, official/audited harnesses, paired statistics, and 3x
p50/p95 latency gates remain required for any capability claim.

For the built-in official bridge covering LiveCodeBench, HumanEval, IFEval, and
MT-Bench, run
every Axio surface and every frozen single-provider baseline against separate,
empty private run directories. Provider baselines use their opaque
`provider::<sha256>` alias, an explicit private registry, and the exact
pre-campaign baseline-freeze manifest. The bridge rejects raw provider/model
identifiers, unbound aliases, changed registries, changed generation settings,
mixed candidate samples, and result case-set drift before a safe score receipt
can be produced.

LiveCodeBench uses the pinned local `test_generation.parquet` snapshot, the
official Generic prompt/system-message protocol, the official last-code-fence
extraction rule, and the pinned `codegen_metrics`/`testing_util` evaluator. Its
primary metric is official `pass@1`. `compile_rate` is a secondary syntax-only
instrumentation metric and never replaces or modifies official functional
correctness. The bridge persists only question hashes, prediction hashes,
booleans, timing, cost, and binding receipts outside the private run directory.

```bash
axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  benchmark-official-harness-generate \
  --suite-id ifeval \
  --dataset <PRIVATE_IFEVAL_SOURCE.jsonl> \
  --harness-root <PRIVATE_IFEVAL_HARNESS_ROOT> \
  --private-run-dir <PRIVATE_PROVIDER_RUN_DIR> \
  --candidate-id 'provider::<FROZEN_PROFILE_SHA256>' \
  --provider-baseline-freeze-manifest <SAFE_FREEZE.json> \
  --harness-pin-manifest <SAFE_HARNESS_PINS.json> \
  --max-output-tokens 512 \
  --live \
  --output <SAFE_WORK_DIR>/ifeval_provider_generation.safe.json

axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  benchmark-official-harness-evaluate \
  --suite-id ifeval \
  --dataset <PRIVATE_IFEVAL_SOURCE.jsonl> \
  --harness-root <PRIVATE_IFEVAL_HARNESS_ROOT> \
  --private-run-dir <PRIVATE_PROVIDER_RUN_DIR> \
  --candidate-id 'provider::<FROZEN_PROFILE_SHA256>' \
  --provider-baseline-freeze-manifest <SAFE_FREEZE.json> \
  --harness-pin-manifest <SAFE_HARNESS_PINS.json> \
  --max-output-tokens 512 \
  --output <SAFE_WORK_DIR>/ifeval_provider_evaluation.safe.json
```

These commands may invoke a provider only with `--live`; HumanEval and
LiveCodeBench evaluation also require `--allow-unsafe-code-execution` in a
disposable isolated worker or container with network and filesystem controls.
The upstream reliability guards are not security sandboxes. These commands
generate and score samples only. Promote a completed bridge
run with the dedicated import command rather than manually retyping any
candidate, source, harness, prompt, or decoding fields:

```bash
axio-fusion-api-standalone \
  benchmark-official-harness-import \
  --private-run-dir <PRIVATE_PROVIDER_RUN_DIR> \
  --output <SAFE_OFFICIAL_IMPORT_DIR>/ifeval_provider.safe.json
```

The import bridge verifies the evaluation receipt digest, generation binding,
full case-set digest, per-case output hashes, official harness pin hashes, and
deterministic generation protocol before creating an `official_harness_import`
run. For a frozen provider alias it also rechecks the baseline-freeze binding.
It makes no model or evaluator call and emits only safe hashes, counts, and
reason codes. Feed the resulting safe run into the dataset manifest before any
claim audit.

### MT-Bench pairwise bridge

`mt_bench_work` uses the pinned FastChat MT-Bench source and its pairwise
judge-template fields. It generates the two fixed dialogue turns privately for
both the requested Axio candidate and a frozen provider-native comparison
candidate. The first assistant turn is included before the second user turn.
For every case the judge sees both `A/B` and `B/A` positions. A positional
disagreement is conservatively scored as a tie; an unparsable judge result is a
failed case, never a fabricated tie.

Pre-register one public Axio surface as the primary paired comparison surface
(normally `chat/completions`), then run the same fixed case set through
Responses, Anthropic Messages, and Gemini-compatible surfaces as independent
API compatibility and intelligence-parity checks. Do not select the best of
the four surfaces after seeing scores. The candidate/comparison pair, frozen
baseline registry, FastChat checkout, judge candidate, decoding settings, and
case set must remain unchanged across those runs.

Generation requires `--live`; pairwise judge evaluation also requires `--live`.
Their latencies are recorded separately, so judge overhead cannot be used to
inflate the candidate's 3x latency comparison. The commands below use only
private locations for raw questions, answers, and judge outputs; their emitted
receipts contain hashes, counts, and status only.

```bash
axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  benchmark-official-harness-generate \
  --suite-id mt_bench_work \
  --dataset <PRIVATE_FASTCHAT_ROOT>/fastchat/llm_judge/data/mt_bench/question.jsonl \
  --harness-root <PRIVATE_FASTCHAT_ROOT> \
  --private-run-dir <EMPTY_PRIVATE_MT_RUN_DIR> \
  --candidate-id axio-pro \
  --api-format chat/completions \
  --mt-comparison-candidate-id 'provider::<FROZEN_PROFILE_SHA256>' \
  --mt-judge-candidate-id 'provider::<FROZEN_JUDGE_PROFILE_SHA256>' \
  --mt-judge-registry <PRIVATE_JUDGE_REGISTRY.json> \
  --provider-baseline-freeze-manifest <SAFE_FREEZE.json> \
  --harness-pin-manifest <SAFE_HARNESS_PINS.json> \
  --max-output-tokens 1024 \
  --live \
  --output <SAFE_WORK_DIR>/mt_bench_generation.safe.json

axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  benchmark-official-harness-evaluate \
  --suite-id mt_bench_work \
  --dataset <PRIVATE_FASTCHAT_ROOT>/fastchat/llm_judge/data/mt_bench/question.jsonl \
  --harness-root <PRIVATE_FASTCHAT_ROOT> \
  --private-run-dir <PRIVATE_MT_RUN_DIR> \
  --candidate-id axio-pro \
  --api-format chat/completions \
  --mt-comparison-candidate-id 'provider::<FROZEN_PROFILE_SHA256>' \
  --mt-judge-candidate-id 'provider::<FROZEN_JUDGE_PROFILE_SHA256>' \
  --mt-judge-registry <PRIVATE_JUDGE_REGISTRY.json> \
  --provider-baseline-freeze-manifest <SAFE_FREEZE.json> \
  --harness-pin-manifest <SAFE_HARNESS_PINS.json> \
  --max-output-tokens 1024 \
  --live \
  --output <SAFE_WORK_DIR>/mt_bench_evaluation.safe.json

axio-fusion-api-standalone \
  benchmark-official-harness-import \
  --private-run-dir <PRIVATE_MT_RUN_DIR> \
  --mt-side target \
  --output <SAFE_IMPORT_DIR>/mt_bench_axio.safe.json

axio-fusion-api-standalone \
  benchmark-official-harness-import \
  --private-run-dir <PRIVATE_MT_RUN_DIR> \
  --mt-side comparison \
  --output <SAFE_IMPORT_DIR>/mt_bench_comparison.safe.json
```

For LiveCodeBench, use the pinned Parquet snapshot as `--dataset` and the fixed
official repository checkout as `--harness-root`:

```bash
axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  benchmark-official-harness-generate \
  --suite-id livecodebench \
  --dataset <PRIVATE_LCB_ROOT>/test_generation.parquet \
  --harness-root <PRIVATE_LCB_HARNESS_ROOT> \
  --private-run-dir <EMPTY_PRIVATE_RUN_DIR> \
  --candidate-id axio-pro \
  --api-format responses \
  --harness-pin-manifest <SAFE_HARNESS_PINS.json> \
  --live \
  --output <SAFE_WORK_DIR>/livecodebench_generation.safe.json

axio-fusion-api-standalone \
  benchmark-official-harness-evaluate \
  --suite-id livecodebench \
  --dataset <PRIVATE_LCB_ROOT>/test_generation.parquet \
  --harness-root <PRIVATE_LCB_HARNESS_ROOT> \
  --private-run-dir <EMPTY_PRIVATE_RUN_DIR> \
  --candidate-id axio-pro \
  --api-format responses \
  --harness-pin-manifest <SAFE_HARNESS_PINS.json> \
  --allow-unsafe-code-execution \
  --output <SAFE_WORK_DIR>/livecodebench_evaluation.safe.json
```

OpenRouter-style Fusion plugin routing:

```json
{
  "model": "axio-terra",
  "messages": [{"role": "user", "content": "Review this architecture note"}],
  "tools": [{"type": "openrouter:fusion"}]
}
```

The OpenRouter-style top-level `plugins` array is also accepted:

```json
{
  "model": "axio-terra",
  "messages": [{"role": "user", "content": "Review this architecture note"}],
  "plugins": [{"id": "fusion", "preset": "quality"}]
}
```

The `fusion` tool is a route-control signal.  It can force the Orchestrator to
use the Fusion panel when budget, privacy policy, recursion depth, and model
pool availability allow it.  It is not executed through the tool gateway.
`model: "openrouter/fusion"` is also accepted as a compatibility alias for
`axio-terra`.  OpenRouter-style fields such as `analysis_models`, `model`, and
`preset` are treated as prompt-free routing hints: they can increase the
requested panel size and are recorded only as hashes, counts, and sanitized
preset ids.  They do not bypass Axio's local registry ranking, privacy filters,
budget locks, or provider health checks, and raw third-party model ids are not
persisted.

Provider inventory without live calls:

```bash
AXIO_NVIDIA_MODELS="openai/gpt-oss-120b,stepfun-ai/step-3.7-flash" \
axio-fusion-api-standalone inventory
```

Built-in provider seeds are optional convenience conventions, not architectural
dependencies.  The Fusion system is configuration-driven: operators can provide
any number of providers through `AXIO_FUSION_PROVIDER_CONFIGS`, and each provider
can use Chat Completions, Responses, Anthropic Messages, or Gemini-compatible
transport independently from the public Axio output surface.

The manifest validates the four upstream protocol families strictly. Use
`chat/completions`, `responses`, `anthropic`, or `gemini` (plus the documented
aliases); an unknown protocol spelling rejects the provider row rather than
silently sending it as Chat Completions. For outbound network control, set
`AXIO_FUSION_NETWORK_MODE` to `auto`, `on`, or `off`. The default is `auto`
with `AXIO_FUSION_SYSTEM_PROXY=http://127.0.0.1:10808`: Fusion probes whether
that proxy port is listening and uses it only when available, otherwise it uses
a no-proxy opener. `on` requires the proxy and fails closed when unavailable;
`off` explicitly bypasses inherited `HTTP_PROXY`, `HTTPS_PROXY`, and
`ALL_PROXY` variables. `AXIO_FUSION_HTTP_PROXY` and
`AXIO_FUSION_USE_SYSTEM_PROXY=1` remain compatibility settings when the new
mode is absent. Proxy credentials, query strings, fragments, and non-root paths
are rejected, and proxy values are never written to receipts.

The current convenience seeds keep common channel formats separate. The current
deployment manifest contains only these two channels:

- `tokenapis`: Responses API compatible; configure it through
  `AXIO_TOKENAPIS_BASE_URL`, `AXIO_TOKENAPIS_API_KEY`, and optionally
  `AXIO_TOKENAPIS_MODELS`.
- `nvidia`: Chat Completions compatible, discovered/probed through `/v1/models`
  and `/v1/chat/completions`.

`aisz` and `cpa-plus` remain supported generic Responses-compatible provider
labels for future manifests, but they are not part of the current runtime pool
unless explicitly configured and successfully enrolled.
- `openai-compatible`: generic Chat Completions-compatible gateway convention.
- `anthropic-compatible`: generic Anthropic Messages-compatible gateway
  convention.
- `gemini-compatible`: generic Gemini-compatible gateway convention using
  query-key auth.

Additional providers can be supplied without code changes:

```bash
export AXIO_FUSION_PROVIDER_CONFIGS='{
  "providers": [
    {
      "provider": "custom-responses",
      "api_format": "responses",
      "base_url_env": "CUSTOM_RESPONSES_BASE_URL",
      "api_key_env": "CUSTOM_RESPONSES_API_KEY",
      "capabilities": {"critique": 0.82, "structured_output": 0.84},
      "input_cost_per_million": 0.10,
      "output_cost_per_million": 0.40,
      "context_tokens": 64000,
      "supports_tools": true,
      "privacy_tags": ["external_provider"]
    }
  ]
}'
```

Native tool support is calibrated separately from ordinary text availability.
The probe sends one fixed, non-benchmark function declaration through every
configured upstream protocol, including profiles whose prior `supports_tools`
value is false. It records only status, latency, counts, and hashes; it must
not be confused with BFCL, tau-bench, or any other capability benchmark:

```bash
axio-fusion-api-standalone \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  tool-probe --live --output <PRIVATE_TOOL_PROBE.json>

axio-fusion-api-standalone \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  calibrate-registry \
  --probe-file <PRIVATE_TEXT_PROBE.json> \
  --probe-file <PRIVATE_TOOL_PROBE.json> \
  --output <PRIVATE_CALIBRATION.json> \
  --updated-registry-output <PRIVATE_CALIBRATED_REGISTRY.json>
```

Only an operational tool-probe result or an explicit external attestation can
make `supports_tools` true; benchmark labels and benchmark scores are blocked
from the default registry-calibration path. The registry also records
`tool_capability` (`proven`, `unproven`, or `failed`) and the latest probe
status. Unselected profiles remain unproven rather than being treated as
failures, and failed probes do not erase a separate external attestation.
Native-tool routing requires a proven capability state.

The latest r3 screening run does not silently infer tool capability from model
cards or benchmark labels. Native tool calibration was not part of this
handoff, so tool candidates remain unproven and the public health projection
reports no tool-eligible profiles. A later bounded tool-probe campaign may
produce a separate calibration artifact, but it must not revise text stream
admission, research ranking, or any benchmark policy without its own gate.

Provider configs may also specify model objects when one channel exposes models
with different transport formats or per-model metadata:

```json
{
  "providers": [
    {
      "provider": "mixed-channel",
      "api_format": "chat/completions",
      "base_url_env": "MIXED_DEFAULT_BASE_URL",
      "api_key_env": "MIXED_DEFAULT_API_KEY",
      "models": [
        {"model": "chat-solver", "capabilities": {"code": 0.9}},
        {
          "model": "responses-critic",
          "api_format": "responses",
          "base_url_env": "MIXED_RESPONSES_BASE_URL",
          "api_key_env": "MIXED_RESPONSES_API_KEY",
          "capabilities": {"critique": 0.92},
          "context_tokens": 128000
        },
        {"model": "anthropic-judge", "api_format": "anthropic"},
        {
          "model": "gemini-worker",
          "api_format": "gemini",
          "base_url_env": "MIXED_GEMINI_BASE_URL",
          "api_key_env": "MIXED_GEMINI_API_KEY"
        }
      ]
    }
  ]
}
```

A provider-level `base_url_env` and `api_key_env` are required only when Axio is
expected to enumerate that channel through `/models`. A channel may instead be
fully model-scoped: omit those two provider-level fields and give every model
object its own `base_url_env`, `api_key_env`, and `api_format`. Those explicitly
listed models become pre-Fusion inventory rows and are strictly stream-probed
before production admission; Axio does not guess a shared endpoint or issue a
provider-level `/models` request for them.

When live `/models` discovery finds exposed model ids for such a provider, the
generated operational registry inherits provider defaults first and then applies
exact per-model overrides when a discovered model id matches a configured model
object.  The inherited fields include API format, auth scheme, env-var names,
capability priors, cost hints, context window, tool or vision flags, and privacy
tags.  Live latency and availability are then added from the short probe.
Redacted evidence keeps only counts, hashes, and safe census fields.
Gemini-compatible discovery accepts both bare model ids such as
`gemini-worker` and provider-returned resource names such as
`models/gemini-worker`; the live call path normalizes these without generating a
duplicated `/models/models/...` endpoint.

Live provider probing is opt-in.  With `AXIO_FUSION_PROVIDER_CONFIGS` set, the
probe command discovers and probes those configured providers by default.  If no
custom providers are configured, it falls back to the convenience seeds whose
env vars are present, then to the built-in discovery seeds for operator
diagnostics.

For the two currently supplied channels, use the non-secret manifest and enrollment
command below. The environment contract intentionally contains placeholders;
inject the real endpoint/key values through a secret manager or the process
environment at launch time.

```bash
axio-fusion-api-standalone enroll-providers \
  --config-file config/current_channels.example.json \
  --live \
  --output-dir <PRIVATE_WORK_DIR>/current_channel_enrollment
```

`enroll-providers` is a legacy operational/diagnostic workflow. It discovers
provider model directories, performs the fixed non-benchmark text probe,
calibrates native tool support, and writes a hash-only receipt. Its generated
probe registry is not a production Fusion admission artifact. Production must
use `pre-fusion-screen` or `serve --enroll`, which additionally requires the
complete research ranking, strict observed streaming, output hashing, and the
90-second latency gate. A blocked or partial pre-Fusion run is never promoted
as the serving registry.

The same manifest can be selected directly for dry-run commands or the gateway
process without exporting `AXIO_FUSION_PROVIDER_CONFIG_FILE`; the option must
appear before the subcommand:

```bash
axio-fusion-api-standalone \
  --provider-config-file config/current_channels.example.json \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  serve --host 127.0.0.1 --port 8789 --live
```

The current validated handoff generated by the configured-channel screening
run is `private/prefusion_live_20260725_r3/fusion-runtime-registry.private.json`.
Its safe control-plane report is
`private/prefusion_live_20260725_r3/prefusion_screening.safe.json`; it contains
29 strictly stream-verified physical profiles and 29 logical model entries for
runtime loading. All 87 admitted samples, the registry handoff validator, and
`load_registry(..., require_prefusion=True)` pass. The required
`primary_solver`, `judge`, and `synthesizer` role capacities are present. The
research ranking is still an operational prior, not benchmark evidence or a
superiority claim. Earlier v2, v5, v6, v9, and operational-v1 artifacts remain
diagnostic history and must not replace the r3 registry without a fresh gate.

The manifest is still only a channel schema. Provider-level `/models`
discovery must be enrolled into a private runtime registry before serving
unknown dynamic model ids. Static model rows may be served directly when their
environment-injected endpoint and credentials are ready.

For a long-running CLI process that should build its in-memory serving pool
from the manifest at startup, use dynamic enrollment mode. It performs
`/models` discovery, bounded text health probes, and native tool calibration;
only healthy profiles are admitted to the process-local Fusion engine. The
`--enroll` path requires `--live` and cannot be combined with `--registry`:

```bash
axio-fusion-api-standalone \
  --provider-config-file config/current_channels.example.json \
  serve --host 127.0.0.1 --port 8789 --live --enroll \
  --enrollment-receipt-output <PRIVATE_WORK_DIR>/enrollment_receipt.safe.json
```

In production, `serve --enroll` is the pre-Fusion admission boundary. It first
builds the candidate inventory from provider `/models` responses, then runs the
configured remote research agent to produce one complete, fixed-schema
capability ranking, and finally performs a real streaming probe for every
ranked physical provider/model profile. A profile is admitted only when the
probe observed SSE or NDJSON, produced non-empty output with a SHA-256 digest,
returned `status=available`, and completed within the hard 90-second ceiling.
Ordinary JSON fallback, missing public-source evidence, an incomplete ranking,
or a missing research-agent result blocks the admission run; none of those
signals is silently converted into serving health.

The physical binding carries the fresh probe latency in its compatibility
field `latency_ms`, while `latency_eligibility.observed_latency_ms` is the
explicit semantic observation. One such measurement is an observed sample,
not p50 or p95. Fusion receives only the latency-filtered logical
`available_model_list` plus the exact physical replica bindings; it never
receives a model merely because a research prior ranked it highly.

The pre-Fusion output has two deliberate levels. `available_model_list` is the
logical list consumed by Fusion and contains one entry per canonical model
identity. Multiple provider/key replicas for the same canonical model remain
physical failover and load-balancing candidates, not additional model votes.
The private physical registry carries the exact profile bindings and live
stream evidence needed by the runtime. The enrollment receipt exposes only
counts, reason codes, latency-gate counters, and hashes.

The example channel manifest enables this gate with its `prefusion` block. The
CLI flags `--prefusion-focus-manifest`, `--prefusion-source-manifest`,
`--prefusion-research-agent-config`, `--prefusion-research-output`, and
`--prefusion-max-models`, `--prefusion-research-batch-size`, and
`--prefusion-research-max-workers` override the corresponding non-secret manifest values
for a controlled run. Missing source/research inputs or a blocked screening
report make startup fail closed. A previously captured strict research JSON
may be supplied for a reproducible run, but it is still validated against the
current candidate inventory and source hashes; it cannot add, remove, or
reorder candidates outside the fixed schema.

The programmatic production path is equivalently:

```python
enrollment = enroll_runtime_channels(
    runtime_manifest,
    secret_resolver=secret_manager.get,
    live=True,
    require_prefusion=True,
)
if enrollment["status"] != "ready":
    raise RuntimeError(enrollment["receipt"]["reason_codes"])
engine = enrollment["engine"]
```

Direct calls to `enroll_runtime_channels(...)` also require the pre-Fusion
configuration by default. The explicit `diagnostic_only=True` ordinary-probe
compatibility path is reserved for fixtures and operator diagnostics. The
production `create_runtime_http_server(..., enroll=True)` boundary always
forces `require_prefusion=True`; it cannot promote a discovered inventory or a
non-streaming health response into Fusion.

The receipt is optional and contains only status, counts, reason codes, and
hashes. It never contains base URLs, API keys, raw model responses, prompts,
or provider output. `--discover` is an inventory-only compatibility startup and
must be paired with `--diagnostic-only`; it does not establish health and must
not replace `--enroll` for an unknown dynamic model inventory.

For hosts that receive endpoint/key values directly from a secret manager, use
the process-local API instead of writing a credential-bearing manifest:

```python
from axio_fusion_api import FusionEngine
from axio_fusion_api.server import create_http_server, create_runtime_http_server

engine = FusionEngine.from_runtime_channels(
    runtime_manifest,
    secret_resolver=secret_manager.get,
    discover=True,
    diagnostic_only=True,
)
server = create_runtime_http_server(
    runtime_manifest,
    secret_resolver=secret_manager.get,
    discover=True,
    live=True,
    diagnostic_only=True,
)
```

The two calls above are diagnostic inventory compatibility examples only. A
production caller must use the pre-Fusion enrollment boundary and pass its
resulting engine to the gateway (or load the validated private registry):

```python
enrollment = enroll_runtime_channels(
    runtime_manifest,
    secret_resolver=secret_manager.get,
    live=True,
    require_prefusion=True,
)
if enrollment["status"] != "ready":
    raise RuntimeError(enrollment["receipt"]["reason_codes"])
server = create_http_server(engine=enrollment["engine"], live=True)
```

`run_runtime_benchmark_campaign(...)` accepts the same in-memory engine for a
resumable, hash-only diagnostic campaign across the four public Axio API
surfaces. Its output is always marked `diagnostic_only` and
`final_claims_allowed: false`; the formal 21-suite campaign still requires the
pinned registry, frozen provider top-three, and official harness gates.

`enroll_runtime_channels(...)` is the live admission path for this deployment
mode. It performs `/models` discovery, bounded text health probes, optional
native-tool probes, filters unavailable profiles, annotates measured latency,
and returns a serving `FusionEngine` plus a safe hash/count receipt. The
credential-bearing profiles never enter a registry or artifact unless the
caller explicitly creates a separate operator-controlled deployment boundary.

```bash
AXIO_FUSION_PROBE_LIVE=1 axio-fusion-api-standalone probe \
  --discover-live-models \
  --timeout 60 \
  --output outputallresult/fusion_api_product/provider_probe.json
axio-fusion-api-standalone registry-from-probe \
  --probe-file outputallresult/fusion_api_product/provider_probe.json \
  --min-available-models 3 \
  --output outputallresult/fusion_api_product/generated_registry.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  provider-portfolio-audit \
  --output outputallresult/fusion_api_product/provider_portfolio.safe.json
```

The raw probe and generated registry above are private operational files because
they must contain provider/model identifiers needed for live calls.  For
shareable evidence packs, emit hash-only artifacts instead:

```bash
AXIO_FUSION_PROBE_LIVE=1 axio-fusion-api-standalone probe \
  --discover-live-models \
  --provider <configured-provider-name> \
  --timeout 60 \
  --redact-provider-identifiers \
  --output outputallresult/fusion_api_product/provider_probe.safe.json
axio-fusion-api-standalone registry-from-probe \
  --probe-file outputallresult/fusion_api_product/provider_probe.json \
  --min-available-models 3 \
  --redact-provider-identifiers \
  --output outputallresult/fusion_api_product/generated_registry.evidence.json
axio-fusion-api-standalone provider-probe-evidence-audit \
  --private-probe-file outputallresult/fusion_api_product/provider_probe.json \
  --private-registry-file outputallresult/fusion_api_product/generated_registry.json \
  --redacted-probe-file outputallresult/fusion_api_product/provider_probe.safe.json \
  --redacted-registry-evidence-file outputallresult/fusion_api_product/generated_registry.evidence.json \
  --min-available-models 3 \
  --output outputallresult/fusion_api_product/provider_probe_evidence_audit.safe.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-external-ranking-template \
  --output outputallresult/fusion_api_product/private_external_provider_ranking.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-provider-baseline-freeze \
  --external-ranking-manifest outputallresult/fusion_api_product/private_external_provider_ranking.json \
  --provider-probe-evidence-audit outputallresult/fusion_api_product/provider_probe_evidence_audit.safe.json \
  --output outputallresult/fusion_api_product/provider_baseline_freeze.safe.json
```

Redacted evidence artifacts preserve counts, status, latency, capability priors,
and provider/model/profile hashes, but not raw provider names, provider model
ids, provider URLs, API keys, or raw provider outputs.

### Controlled Provider Onboarding

New remote API profiles must first be present in the private registry with
`"enabled": false`. Normal serving registry loads omit them, and the router
also rejects disabled profiles before direct fallback or panel selection. The
onboarding control plane can inspect disabled profiles only to build a
hash-safe lifecycle record:

`configured -> protocol_validated -> live_probed -> capability_calibrated ->
shadow_candidate -> approved -> active`

It requires explicit live probe evidence and calibration input, then emits a
shadow candidate that is ineligible for `axio-terra` and `axio-pro` panels. A
human review and a separate, explicitly named private registry output are
required to enable it. The source registry is never modified in place.

```bash
axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  provider-onboarding-candidate \
  --candidate-profile-hash <PROFILE_SHA256> \
  --probe-file <REDACTED_LIVE_PROBE.json> \
  --calibration-file <PRIVATE_CALIBRATION.json> \
  --output <SAFE_WORK_DIR>/provider_onboarding_candidate.safe.json

axio-fusion-api-standalone --registry <PRIVATE_REGISTRY.json> \
  provider-onboarding-review \
  --candidate <SAFE_WORK_DIR>/provider_onboarding_candidate.safe.json \
  --approve \
  --output <SAFE_WORK_DIR>/provider_onboarding_review.safe.json

axio-fusion-api-standalone provider-onboarding-apply \
  --candidate <SAFE_WORK_DIR>/provider_onboarding_candidate.safe.json \
  --review <SAFE_WORK_DIR>/provider_onboarding_review.safe.json \
  --source-registry <PRIVATE_REGISTRY.json> \
  --output-registry <PRIVATE_REGISTRY_AFTER_APPROVAL.json>
```

All model execution remains through configured remote HTTP(S) APIs. The
onboarding commands do not download, load, train, or serve local weights, and
candidate, review, activation, and apply receipts contain hashes and safe
counts rather than provider identifiers, endpoints, credentials, prompts, or
model outputs.

`provider-probe-evidence-audit` binds the private live probe, private generated
registry, redacted probe, and redacted registry evidence through path hashes,
profile-set hashes, source counts, redaction contracts, and leakage checks.  It
must pass before `benchmark-provider-baseline-freeze` is treated as final-claim
evidence.

`provider-portfolio-audit` is hash-only by default.  It checks whether an
arbitrary configured provider/model pool has enough usable models for the three
provider baseline tiers, enough judge/structured/synthesis/fast-path role
coverage for Fusion, enough provider/API diversity to reduce correlated errors,
and enough category capability coverage for the 9 benchmark categories.  It
separates `ready_for_serving`, `ready_for_diverse_fusion`, and
`ready_for_final_claim_registry_profile`; the last one still requires live-probe
evidence and does not replace the real 21-suite benchmark campaign.
`benchmark-provider-baseline-freeze` then freezes the hash-only provider
baseline candidate universe before the live campaign.  Its manifest must carry
a `provider_probe_evidence_audit_receipt` whose registry content hash matches
the generated registry receipt, plus a private external-ranking input that
screens the complete set of live-probed configured-provider models and derives
exactly one pool rank 1, rank 2, and rank 3 model.  Each screened profile must
have at least two independent non-target ranking sources, each with a reported
external rank and the total ranked population.  The deterministic aggregation
keeps only source families shared by every live-probed candidate, checks that
each shared family has one stable snapshot and population, averages
`(rank - 1) / (population - 1)` equally across those families, and then uses
the candidate hash as the tie-break.  At least two common independent source
families are required.  The selected top three must match the derived pool
order.  The private input may contain source locators, but the safe freeze
stores only hashes, source classes, dates, ranks, population counts,
normalized percentiles, evidence counts, and snapshot hashes.  The target
21-suite results must not choose, reorder, or substitute those three baselines.

When readiness discovers artifacts from a directory, it selects a complete
set by one shared cohort token across materialization, case hashes, source
validation, harness pins, import template, execution plan, acquisition, and
official-import audit. It never combines the independently newest file of each
kind. If no common cohort exists, individually newest files may appear in the
diagnostic projection, but readiness is blocked until one explicitly bound
cohort is supplied. This prevents an old all-provider import queue or an
unrelated registry snapshot from becoming formal top-three evidence.

`benchmark-external-ranking-template` creates that private input skeleton from
the complete live-probed registry.  It contains only profile/candidate hashes,
empty screening ranks, source locators, snapshot hashes, dates, and tie-break
decisions.  The public sources used for the ranking must be recorded privately
with stable snapshots.  An official source is required for identity/capability
corroboration on each selected rank, while two distinct independent source
families are required for every screened profile's reported rank.  Every
independent rank must state its candidate-population count, and the full pool
must share at least two source families with a stable snapshot and population.
Do not use any result, material, or label from the target 21-suite campaign.
A template passed to the freeze command without complete pool screening or
with manually selected rows that differ from the derived top three is rejected.

The executable replacement is the three-command baseline-screening workflow:
`baseline-screening-plan` builds a hash-only, complete canonical-pool matrix;
`baseline-screening-run` performs either a zero-network preflight or an
explicit `--live` campaign with private raw-output units and a separate safe
checkpoint; and `baseline-screening-to-ranking` re-scores every private output
with the pinned scorer before producing the strict ranking input. The plan
binds prompt, reference, case-contract, adapter implementation, provider
catalog identity, and a seed-derived execution order. Adjacent independent
sources use reversed candidate order and execute one source per round to
counterbalance long-campaign time drift. Wrong answers are never retried;
only transport or scorer failures may resume. Resume authenticates the safe
checkpoint and every existing private unit, while conversion rejects forged
scores even if outer content digests have been recomputed.
Transport failures are missing observations rather than wrong answers: they
contribute to the pre-registered transport-failure rate and can block a unit,
but they are excluded from that unit's score denominator and confidence
interval. Only successfully scored completed responses contribute to the
capability mean; scorer/internal errors remain unit failures.

There is no permanent universal top-three ordering across public leaderboards.
For example, the current general text ranking at
<https://lmarena.ai/leaderboard/text> and the current intelligence index at
<https://artificialanalysis.ai/leaderboards/models> expose different leaders
and different ordering.  The system therefore does not hard-code illustrative
names or trust one page's headline.  It uses the frozen, date-stamped,
non-target evidence to rank only models that are actually present and live in
the configured provider pool.  A disagreement is represented by the
pre-registered mean-rank aggregation; a missing or untraceable source blocks
the freeze rather than being silently filled from a model prior.

Before live probing or the full benchmark campaign, run the safe system preflight
without touching any provider:

```bash
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  fusion-live-readiness \
  --benchmark-manifest-dir /mnt/storage/axio_fusion_benchmarks/manifests \
  --output outputallresult/fusion_api_product/fusion_live_readiness.safe.json
```

This preflight only records credential presence, API-format counts, safe
benchmark artifact status, official harness execution-plan readiness,
official import audit readiness, live-registry proof status, and blocker reason
codes. It does not persist raw provider names, model ids, base URLs, API keys,
local paths, prompts, labels, or provider outputs.

To prepare the live probe, registry, 21-suite campaign, final audit, and
shadow-only failure analysis as one safe operator sequence, emit a runbook:

```bash
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  fusion-live-runbook \
  --benchmark-manifest-dir /mnt/storage/axio_fusion_benchmarks/manifests \
  --output outputallresult/fusion_api_product/fusion_live_runbook.safe.json
```

The runbook is a command template artifact, not a live execution step.  It does
not call providers and it records only hashes, counts, placeholders, stage
gates, and blocker reason codes; raw provider names, model ids, endpoint URLs,
API keys, env-var names, local paths, prompts, labels, and provider outputs stay
out of the safe JSON.  Its registry stage includes
`provider-probe-evidence-audit`, so the private probe, generated registry,
redacted probe, and redacted registry evidence are bound before provider
baselines are frozen.

Safe tool execution gateway:

```bash
axio-fusion-api-standalone tool-execute \
  --role primary_solver \
  --call-json '{"name":"math_eval","arguments":{"expression":"2+2"}}'
```

Benchmark planning and scorecards:

```bash
axio-fusion-api-standalone benchmarks
axio-fusion-api-standalone benchmark-methodology \
  --output outputallresult/fusion_api_product/methodology.json
axio-fusion-api-standalone benchmark-dataset-template \
  --base-dir data/benchmarks \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/dataset_manifest.template.json
axio-fusion-api-standalone benchmark-source-manifest-template \
  --base-dir data/benchmarks \
  --import-dir outputallresult/fusion_api_product/imports \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/benchmark_source_manifest.template.json
axio-fusion-api-standalone benchmark-source-manifest-validate \
  --source-manifest outputallresult/fusion_api_product/benchmark_source_manifest.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/benchmark_source_manifest_validation.json
axio-fusion-api-standalone benchmark-source-manifest-prepare \
  --template outputallresult/fusion_api_product/benchmark_source_manifest.template.json \
  --case-hash-manifest outputallresult/fusion_api_product/benchmark_case_hash_manifest.json \
  --harness-pin-manifest outputallresult/fusion_api_product/harness_pin_manifest.safe.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/benchmark_source_manifest.prepared.json
axio-fusion-api-standalone benchmark-matrix \
  --suite-id arc_challenge \
  --output outputallresult/fusion_api_product/benchmark_matrix.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-acquisition-checklist \
  --base-dir data/benchmarks \
  --import-dir outputallresult/fusion_api_product/imports \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/acquisition_checklist.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-acquisition-status \
  --dataset-dir data/benchmarks \
  --import-dir outputallresult/fusion_api_product/imports \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/acquisition_status.json
axio-fusion-api-standalone benchmark-run \
  --suite-id arc_challenge \
  --dataset path/to/local_multiple_choice.jsonl \
  --candidate-id axio-pro \
  --task-format auto \
  --limit 50 \
  --output outputallresult/fusion_api_product/axio_pro_arc_run.json
axio-fusion-api-standalone benchmark-validate-dataset \
  --suite-id math_500 \
  --dataset data/math_500.jsonl \
  --task-format exact_match \
  --output outputallresult/fusion_api_product/math_500_validation.json
axio-fusion-api-standalone benchmark-import-official-run \
  --suite-id livecodebench \
  --candidate-id axio-pro \
  --source official_harness_outputs/livecodebench_axio_pro.jsonl \
  --task-format python_code \
  --harness-name "LiveCodeBench official" \
  --harness-version "commit-or-release-id" \
  --dataset-snapshot "pinned-dataset-snapshot-id" \
  --evaluator-config "deterministic-evaluator-config-id" \
  --decoding-config "<DETERMINISTIC_DECODING_CONFIG_SHA256>" \
  --output outputallresult/fusion_api_product/imports/livecodebench_axio_pro.safe.json
axio-fusion-api-standalone benchmark-import-batch-template \
  --acquisition-checklist outputallresult/fusion_api_product/acquisition_checklist.json \
  --harness-pin-manifest outputallresult/fusion_api_product/harness_pin_manifest.safe.json \
  --output outputallresult/fusion_api_product/import_batch.template.json
axio-fusion-api-standalone benchmark-official-harness-execution-plan \
  --import-batch-template outputallresult/fusion_api_product/import_batch.template.json \
  --acquisition-status outputallresult/fusion_api_product/acquisition_status.json \
  --harness-pin-manifest outputallresult/fusion_api_product/harness_pin_manifest.safe.json \
  --output outputallresult/fusion_api_product/official_harness_execution_plan.safe.json
axio-fusion-api-standalone benchmark-harness-pin-manifest \
  --harness-root /mnt/storage/axio_fusion_benchmarks/harness \
  --raw-root /mnt/storage/axio_fusion_benchmarks/raw \
  --output outputallresult/fusion_api_product/harness_pin_manifest.safe.json
axio-fusion-api-standalone benchmark-import-official-batch \
  --batch-file official_harness_outputs/import_batch.json \
  --output-dir outputallresult/fusion_api_product/imports \
  --output outputallresult/fusion_api_product/import_batch_receipt.json
axio-fusion-api-standalone benchmark-assemble-manifest \
  --template outputallresult/fusion_api_product/dataset_manifest.template.json \
  --dataset-dir data/benchmarks \
  --import-dir outputallresult/fusion_api_product/imports \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/dataset_manifest.json
axio-fusion-api-standalone benchmark-case-hash-manifest \
  --dataset-manifest outputallresult/fusion_api_product/dataset_manifest.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/benchmark_case_hash_manifest.json
axio-fusion-api-standalone benchmark-source-manifest-bind-case-hashes \
  --source-manifest outputallresult/fusion_api_product/benchmark_source_manifest.json \
  --case-hash-manifest outputallresult/fusion_api_product/benchmark_case_hash_manifest.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/benchmark_source_manifest.bound.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-official-import-audit \
  --dataset-manifest outputallresult/fusion_api_product/dataset_manifest.json \
  --source-manifest outputallresult/fusion_api_product/benchmark_source_manifest.bound.json \
  --case-hash-manifest outputallresult/fusion_api_product/benchmark_case_hash_manifest.json \
  --harness-pin-manifest outputallresult/fusion_api_product/harness_pin_manifest.safe.json \
  --import-dir outputallresult/fusion_api_product/imports \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/official_import_audit.safe.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-readiness \
  --dataset-manifest outputallresult/fusion_api_product/dataset_manifest.json \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/readiness.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-provider-baseline-freeze \
  --external-ranking-manifest outputallresult/fusion_api_product/private_external_provider_ranking.json \
  --provider-probe-evidence-audit outputallresult/fusion_api_product/provider_probe_evidence_audit.safe.json \
  --output outputallresult/fusion_api_product/provider_baseline_freeze.safe.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-campaign \
  --dataset-manifest outputallresult/fusion_api_product/dataset_manifest.json \
  --output-dir outputallresult/fusion_api_product/full_campaign \
  --live \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --provider-probe-evidence-audit outputallresult/fusion_api_product/provider_probe_evidence_audit.safe.json \
  --min-cases-per-suite 100
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-campaign-progress-plan \
  --dataset-manifest outputallresult/fusion_api_product/dataset_manifest.json \
  --output-dir outputallresult/fusion_api_product/full_campaign \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --min-cases-per-suite 100 \
  --output outputallresult/fusion_api_product/campaign_progress.safe.json
axio-fusion-api-standalone benchmark-api-surface-parity \
  --run-file outputallresult/fusion_api_product/full_campaign/runs.json \
  --output outputallresult/fusion_api_product/api_surface_parity.safe.json
axio-fusion-api-standalone benchmark-final-audit \
  --campaign-dir outputallresult/fusion_api_product/full_campaign \
  --source-manifest outputallresult/fusion_api_product/benchmark_source_manifest.bound.json \
  --case-hash-manifest outputallresult/fusion_api_product/benchmark_case_hash_manifest.json \
  --provider-probe-evidence-audit outputallresult/fusion_api_product/provider_probe_evidence_audit.safe.json \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --official-import-audit outputallresult/fusion_api_product/official_import_audit.safe.json \
  --api-surface-parity outputallresult/fusion_api_product/api_surface_parity.safe.json \
  --training-contamination-audit-file outputallresult/fusion_api_product/full_campaign/training_contamination_audit.json \
  --min-cases-per-suite 100 \
  --alpha 0.05 \
  --output outputallresult/fusion_api_product/final_audit.json
axio-fusion-api-standalone --registry outputallresult/fusion_api_product/generated_registry.json \
  benchmark-evidence-pack \
  --source-manifest outputallresult/fusion_api_product/benchmark_source_manifest.bound.json \
  --case-hash-manifest outputallresult/fusion_api_product/benchmark_case_hash_manifest.json \
  --provider-probe-evidence-audit outputallresult/fusion_api_product/provider_probe_evidence_audit.safe.json \
  --provider-baseline-freeze outputallresult/fusion_api_product/provider_baseline_freeze.safe.json \
  --official-import-audit outputallresult/fusion_api_product/official_import_audit.safe.json \
  --api-surface-parity outputallresult/fusion_api_product/api_surface_parity.safe.json \
  --dataset-manifest outputallresult/fusion_api_product/dataset_manifest.json \
  --campaign-dir outputallresult/fusion_api_product/full_campaign \
  --min-cases-per-suite 100 \
  --alpha 0.05 \
  --output outputallresult/fusion_api_product/full_campaign/evidence_pack.json
axio-fusion-api-standalone benchmark-scorecard \
  --run-file outputallresult/fusion_api_product/axio_pro_arc_run.json \
  --output outputallresult/fusion_api_product/scorecard.json
axio-fusion-api-standalone benchmark-claim-audit \
  --run-file outputallresult/fusion_api_product/all_required_runs.json \
  --min-cases-per-suite 100 \
  --alpha 0.05 \
  --output outputallresult/fusion_api_product/claim_audit.json
axio-fusion-api-standalone benchmark-fusion-failure-analysis \
  --scorecard-file outputallresult/fusion_api_product/scorecard.json \
  --claim-audit-file outputallresult/fusion_api_product/claim_audit.json \
  --readiness-file outputallresult/fusion_api_product/fusion_live_readiness.safe.json \
  --trace-report-file outputallresult/fusion_api_product/trace_report.json \
  --output outputallresult/fusion_api_product/fusion_failure_analysis.safe.json
axio-fusion-api-standalone learning-report \
  --feedback-file outputallresult/fusion_api_product/feedback.jsonl \
  --scorecard-file outputallresult/fusion_api_product/scorecard.json \
  --output outputallresult/fusion_api_product/learning_report.json
axio-fusion-api-standalone router-policy-shadow-patch \
  --feedback-file outputallresult/fusion_api_product/feedback.jsonl \
  --trace-file outputallresult/fusion_api_product/execution_traces.jsonl \
  --min-examples 20 \
  --output outputallresult/fusion_api_product/router_policy_shadow_patch.json
axio-fusion-api-standalone routing-policy-shadow-replay \
  --candidate outputallresult/fusion_api_product/routing_policy_candidate.safe.json \
  --trace-file outputallresult/fusion_api_product/execution_traces.jsonl \
  --feedback-file outputallresult/fusion_api_product/feedback.jsonl \
  --output outputallresult/fusion_api_product/routing_policy_shadow_replay.safe.json
axio-fusion-api-standalone training-contamination-audit \
  --benchmark-file outputallresult/fusion_api_product/full_campaign/runs.json \
  --learning-report-file outputallresult/fusion_api_product/learning_report.json \
  --calibration-file outputallresult/fusion_api_product/registry_calibration.json \
  --feedback-file outputallresult/fusion_api_product/feedback.jsonl \
  --trace-file outputallresult/fusion_api_product/execution_traces.jsonl \
  --output outputallresult/fusion_api_product/full_campaign/training_contamination_audit.json
axio-fusion-api-standalone trace-report \
  --trace-file outputallresult/fusion_api_product/execution_traces.jsonl \
  --output outputallresult/fusion_api_product/trace_report.json
axio-fusion-api-standalone calibrate-registry \
  --probe-file outputallresult/fusion_api_product/provider_probe.json \
  --benchmark-file outputallresult/fusion_api_product/axio_pro_arc_run.json \
  --allow-benchmark-calibration \
  --feedback-file outputallresult/fusion_api_product/feedback.jsonl \
  --trace-file outputallresult/fusion_api_product/execution_traces.jsonl \
  --output outputallresult/fusion_api_product/registry_calibration.json \
  --updated-registry-output outputallresult/fusion_api_product/calibrated_registry.json
```

Benchmark run artifacts store hashes, counts, accuracy, latency, and policy
metadata.  They do not persist raw benchmark questions, options, answer labels,
provider outputs, or secrets.

`benchmark-fusion-failure-analysis` consumes safe scorecard, claim-audit,
readiness, and trace-report artifacts and emits a shadow-only optimization plan.
Trace reports include aggregate provider fallback health signals such as
fallback pool size, top availability, top routing score, non-panel candidate
coverage, and API-format diversity without provider names, model names, URLs,
prompts, or outputs.
It separates evidence gaps, API-surface parity failures, score failures,
statistical failures, and 3x latency-gate failures, then maps them to bounded
routing/orchestration knobs such as adaptive panel size, early exit,
targeted escalation, provider/API diversity, provider fallback refresh,
quality-diversity archive use, and diversity-aware synthesis.  The plan is
explicitly not applied to serving policy and cannot be used as a benchmark-label
tuning shortcut; every suggested change still requires a fresh no-cheat replay
and final audit.

`benchmark-methodology` emits the machine-readable method contract for all 21
required suites.  It records official/audited source expectations, snapshot
policy, prompt policy, scoring policy, harness/import requirements, and
anti-leakage controls without storing benchmark content.

`benchmark-dataset-template` emits both per-suite JSONL/import schemas and a
`dataset_acquisition_plan`.  The plan separates the fifteen local deterministic
runner suites from the six official or separately audited import suites, and
adds safe validate/import command templates for each suite.  Official-harness
and pairwise-judge suites remain final-claim eligible only after hash-only
`benchmark-import-official-run` receipts exist for every campaign run unit.
The default campaign minimum remains 100 cases per suite, but fixed small
full-suite benchmarks can declare a stricter suite-aware effective minimum;
for example, AIME Recent uses its complete 30-case public slice instead of
being falsely blocked by the global default.

`benchmark-source-manifest-template` emits a safe source, snapshot, license, and
materialization manifest template for all 21 suites.  Operators fill it with
hashes of pinned dataset snapshots, source revisions, adapter versions, fixed
case-selection protocols, prompt/template protocols, deterministic decoding
configs, materialized case-hash manifests, evaluator configs, and official
harness versions, plus a license or usage policy id.  The companion
`benchmark-source-manifest-validate` command checks that every required suite is
pinned without reading or storing raw benchmark questions, labels, local paths,
official harness output paths, provider outputs, or secrets.

`benchmark-acquisition-checklist` expands that plan against the current run
matrix.  It emits a safe work queue for every local JSONL dataset and every
official/audited import receipt required by the pre-registered candidates,
including Axio tiers, ablation baselines, and provider single-model baselines.
Provider model ids and dataset paths are represented as hashes and placeholders;
the artifact is meant for acquisition tracking and readiness reconciliation,
not for storing benchmark content or provider outputs.

`benchmark-acquisition-status` scans the current pinned dataset directory and
safe official-import directories before a manifest exists.  It reports which
local JSONL suites validate, which official/audited import receipts are present,
valid, missing, or invalid for the same run-matrix candidates, and whether it is
safe to proceed to `benchmark-assemble-manifest`.  Like the checklist, it stores
only hashes, counts, reason codes, and placeholders.  Optional repeated
`--candidate-id` values can scope a partial operator check, but final claim
readiness still requires the complete pre-registered run matrix.

`benchmark-import-batch-template` converts the safe acquisition checklist into a
fillable `benchmark-import-official-batch` manifest.  It carries suite ids,
task formats, candidate placeholders, source placeholders, pinned harness
metadata placeholders, deterministic decoding config placeholders, and
position-balancing flags; operator-side tooling must
replace those placeholders with real candidate ids and official/audited harness
output paths before importing.  The template stores candidate hashes and counts
for reconciliation, but not raw provider model ids, source paths, benchmark
content, provider outputs, API keys, or provider URLs.

`benchmark-import-official-batch` converts many official or separately audited
harness outputs into safe Axio benchmark run artifacts in one pass.  The batch
file may be a JSON list or an object with `imports`, `runs`, `items`, or
`entries`; each row supplies `suite_id`, `candidate_id`, `source`, `task_format`,
and harness snapshot/evaluator metadata, with optional top-level `defaults`.
The batch receipt stores only hashes, counts, status codes, and safe output
receipts.  It does not persist raw source paths, raw batch paths, benchmark
content, provider outputs, API keys, or provider URLs.

`benchmark-case-hash-manifest` materializes the fixed case set from the assembled
dataset manifest into a hash-only receipt.  Local deterministic suites
contribute case-set digests from pinned JSONL rows; official/audited harness
suites contribute digests from safe imported run `case_results` and are blocked
unless all imported candidates use the same case hash set.
`benchmark-source-manifest-bind-case-hashes` copies those per-suite digests into
a bound source manifest with a hash-only binding receipt before final audit.
The artifacts store case-set digests, counts, and reason codes only, not raw
case hashes, prompts, labels, dataset paths, import paths, provider outputs, API
keys, or provider URLs.

`benchmark-official-import-audit` is the pre-campaign gate for official or
separately audited harness suites.  It checks that the expected run units are
covered, every imported run uses the same case hash set, prompt protocol,
deterministic decoding config, official harness identity, dataset snapshot, and
evaluator config, and that those hashes match the source manifest, case-hash
manifest, and harness-pin manifest.  The report is hash-only and blocks on
missing imports, invalid harness receipts, source-manifest mismatches, case-set
mismatches, and unbound harness pins before the expensive live campaign starts.

`benchmark-official-harness-campaign` is the resumable control plane for the
six official/audited bridge suites. It consumes the already frozen hash-only
execution plan, resolves actual candidates only in process from the private
registry, runs `preflight -> generate -> evaluate -> import` one task at a
time, and writes campaign state atomically after every task. A valid existing
safe import is reused on restart; a failed task is retried only with explicit
`--retry-failed`, and LiveCodeBench/HumanEval execution remains blocked unless
`--allow-unsafe-code-execution` is explicitly supplied in an isolated runtime.

The command needs a private suite-config JSON whose paths and simulator values
are never copied into the campaign state. Its `defaults` optionally supplies
shared settings, and each `suites` row supplies a `suite_id`, `dataset_path`,
and `harness_root` plus suite-specific controls such as tau-bench simulator or
MT-Bench auxiliary candidate pools. The persisted state contains only hashes,
counts, suite ids, stage statuses, and reason codes.

```bash
axio-fusion-api-standalone --registry <PRIVATE_REGISTRY_JSON> \
  benchmark-official-harness-campaign \
  --execution-plan <SAFE_EXECUTION_PLAN_JSON> \
  --suite-config <PRIVATE_SUITE_CONFIG_JSON> \
  --provider-baseline-freeze-manifest <SAFE_PROVIDER_FREEZE_JSON> \
  --harness-pin-manifest <SAFE_HARNESS_PIN_JSON> \
  --private-root <PRIVATE_RUN_ROOT> \
  --safe-import-root <SAFE_OFFICIAL_IMPORT_ROOT> \
  --live --retry-failed --allow-unsafe-code-execution \
  --output <SAFE_CAMPAIGN_STATE_JSON>
```

Before a full campaign, the same command without `--live` provides a
zero-model-call preflight over a selected suite/task/candidate-hash slice.
The driver never turns this preflight into a claim of benchmark superiority.
An Axio-only offline slice may run before the provider rank freeze so dataset,
harness, and four-surface bindings can be repaired without spending model
calls. The safe campaign receipt marks this explicitly as
`unfrozen_axio_preflight_only`. Any `--live` run, and any slice containing a
provider candidate, still requires a digest-valid, externally ranked,
pre-registered canonical top-three freeze with exactly ranks 1/2/3 and the
`axio-pro`/`axio-terra`/`axio-fast` tier mapping. A historical exhaustive
provider freeze is diagnostic only even when an older artifact carries a
legacy ready flag.

Admission does not trust the freeze's outer digest or embedded ready booleans
alone. It revalidates the external-ranking receipt digest and common-source
derived order, then requires its rank rows, canonical/replica identities,
frozen candidate rows, selected candidate-set digest, registry binding, and
tier mapping to describe the same rank-1/rank-2/rank-3 assignment. Recomputing
an outer freeze digest after changing any one of those mappings remains a
blocked condition before task processing or provider calls.

Execution plans created before the top-three freeze must not be used for the
formal live campaign when they contain every provider profile. After the
non-target screening campaign freezes the three canonical baseline groups,
regenerate the official-harness execution plan so its provider tasks contain
only those three groups and their declared same-model replicas.

`benchmark-evidence-pack` emits a compact, safe readiness bundle for operators.
It summarizes the registry, methodology, source manifest validation, dataset
acquisition plan, run matrix, readiness audit, final audit, blocking reason
counts, next command templates, and an `execution_guidance` section with the
current stage, primary blocker, next command-template step, and priority
checklist.  The acquisition summary lists per-suite input modes, import
requirements, the campaign candidate count, and the required hash-only official
import receipt counts without real dataset paths or candidate ids.
It stores hashes, counts, reason codes, and placeholders only: no raw dataset
content, raw benchmark labels, raw prompts, provider outputs, provider URLs, or
secrets.  It is an operations receipt, not a substitute for the required live
campaign and final audit.

`registry-from-probe` converts prompt-free live probe artifacts into a standard
registry.  By default it keeps only models that answered the short health probe
successfully, records latency and health metadata, and persists only environment
variable names for API configuration.  It does not write API keys, raw provider
responses, raw probe prompts, raw provider URLs, or raw error details.  Responses
API compatible channels can be added with environment variables such as
`AXIO_CPA_PLUS_BASE_URL` / `AXIO_CPA_PLUS_API_KEY` or
`AXIO_AISZ_BASE_URL` / `AXIO_AISZ_API_KEY`; those optional channels are not
enabled by the current deployment manifest.

Generated registries also seed conservative model-name capability priors, such
as code/review strengths for `codex-*` models and stronger balanced priors for
`gpt-5.6-terra`.  These priors are only initial routing hints; benchmark,
feedback, trace, and calibration artifacts are expected to overwrite them as
real evidence accumulates.

Final benchmark claim gate:

- The required public claims are strict: `axio-pro` must beat the externally
  pre-registered configured-provider-pool rank 1 provider baseline,
  `axio-terra` the fixed configured-provider-pool rank 2 baseline, and
  `axio-fast` the fixed configured-provider-pool rank 3 baseline on every
  required suite. The three ranks are derived once from the full live-probed
  configured-provider pool before target-suite execution.
- Fusion admission has a hard known-latency guard: when p50 estimates are
  available, a Fusion route whose estimated latency exceeds 3x the direct
  single-model route is blocked before execution, even if a pro/quality policy
  would otherwise force independent verification.
- `axio-fast` remains direct by default, but can admit a two-model
  `fast_light_verify` route for high-quality targets, high-risk or uncertain
  tasks, and tool-planning checks.  It keeps `max_depth=0`, bounded call
  budgets, and the same 3x latency guard so the fast tier can improve accuracy
  without becoming a heavy panel.
- Required coverage is two suites in each of the first eight categories and
  five suites in the vertical-domain category:
  science knowledge, multilingual use, static code challenge writing, math,
  logic reasoning, agentic tool use, daily work skills, hallucination /
  factuality, and vertical-domain skills.
- The claim audit uses the immutable pre-registered rank mapping and paired
  case-level comparisons on hashed case ids.  Target-suite scores may evaluate
  the mapping but may not select, reorder, or replace it.
- The claim audit also rechecks the real run latency gate: each Axio tier must
  stay within 3x the same-suite target provider baseline latency, preferring
  `p95_case_latency_ms` and falling back to average or total run latency.  A
  score win with latency above 3x cannot authorize a superiority claim.
- Final public superiority claims require a `benchmark-provider-baseline-freeze`
  artifact created with `--external-ranking-manifest`. The private ranking input
  must screen the complete set of live-probed configured-provider models; its
  selected ranks 1/2/3 must equal the deterministic top three derived from that
  full pool and include both official and independent non-target-benchmark
  evidence. `--all-provider-baselines` is a diagnostic option only and can
  never authorize a final claim.
- Final audit requires the campaign's hash-only provider baseline census to be
  marked `externally_ranked_top_three_pre_registered`, to select exactly three
  candidates, and to bind its full available-provider census plus the fixed
  rank mapping to campaign runs, scorecards, and claim comparisons.  This
  prevents a campaign from silently omitting, substituting, or reranking a
  final comparison baseline.
- Suites that require an official or separately audited harness, including
  LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style pairwise
  judging, must be imported with a hash-only `harness_receipt`.  The built-in
  local runners are useful for smoke tests and pilots, but they are marked
  `pilot_only` for those suites and cannot authorize final superiority claims.
- Use `benchmark-import-official-run` to convert official or audited harness
  JSON/JSONL outputs into safe run artifacts.  It hashes case identities,
  predictions, references, harness identity, dataset snapshot, and evaluator
  configuration; it does not persist raw benchmark prompts, labels, references,
  provider outputs, source paths, or secrets.  For pairwise judge imports, pass
  `--position-balanced`.
- Provider single-model candidates are persisted as `provider::<sha256>` hash
  aliases.  Legacy provider/profile candidate ids are accepted only as
  operator input or lookup compatibility; import, run, campaign, scorecard, and
  claim artifacts canonicalize raw provider/model-shaped ids before writing
  safe outputs.
- Use `benchmark-import-batch-template` after `benchmark-acquisition-checklist`
  to produce the fillable batch manifest for all required official/audited
  imports.  The filled batch should be imported with
  `benchmark-import-official-batch` before assembling the dataset manifest.  If a
  harness pin manifest is supplied, the batch template pre-fills official
  harness names, commits, dataset snapshots, evaluator config hashes,
  prompt-protocol hashes, and deterministic decoding hashes for every official
  import row.
- Use `benchmark-harness-pin-manifest` to bind official/audited harness commits,
  evaluator file hashes, prompt/decoding hashes, and dataset snapshot hashes for
  LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style judging.
  The manifest stores local path hashes only, not local paths, prompts, labels,
  provider outputs, or secrets.
- Use `benchmark-source-manifest-prepare` to convert the source manifest template
  into a hash-bound source manifest using the case-hash manifest and harness pin
  manifest.  This fills dataset snapshot, source revision, case-selection,
  prompt, decoding, adapter, data-usage, evaluator, official harness, and license
  review fields without persisting local paths or raw benchmark content.
- Axio run units are expanded to `axio-fast`, `axio-terra`, and `axio-pro`
  across Chat Completions, Responses, Anthropic Messages, and Gemini-compatible
  API surfaces.  Only the primary Chat Completions surface participates in the
  intelligence superiority claim; the other three surfaces are engineering
  stability and equivalence gates that must use the same cases, prompt protocol,
  and deterministic decoding config.
- Aggregate-only scorecards are not enough for a superiority claim.  A suite
  claim requires enough paired cases, higher Axio primary score, latency within
  3x of the target provider baseline, and a one-sided exact sign-test p-value at
  or below the configured alpha.  Final public claims also require
  Holm-Bonferroni family-wise correction across the full pre-registered set of
  63 suite-by-tier comparisons.
- The final audit also verifies that every candidate run within each suite uses
  the identical case hash set.  A comparison with enough overlapping cases can
  still be rejected if any Axio, ablation, or provider run used a different
  case set.
- The final audit also requires every candidate run within each suite to carry
  the same prompt/template/protocol hash.  The artifact stores only
  `prompt_protocol_sha256`-style hashes, never raw prompt templates.
- The final audit also requires every candidate run within each suite to carry
  the same deterministic decoding configuration hash.  The artifact stores only
  `decoding_config_sha256`-style hashes, never raw prompts or provider outputs.
- For official or separately audited harness suites, final audit also binds
  every imported run's harness identity, pinned dataset snapshot, and evaluator
  configuration hashes to the pre-registered source manifest.  A run imported
  from a different harness version, dataset snapshot, or evaluator config is
  rejected even if its case, prompt, and decoding hashes otherwise align.
- Run `benchmark-official-import-audit` after official imports and source/case
  binding, before the live campaign.  It uses the same hash-only alignment
  checks as final audit for official/audited suites, so missing or tampered
  imports are caught before provider budget is spent.
- Final audit requires the official import audit artifact to be bound to the
  same campaign official/audited run set by run-set digest.  A ready import
  audit from an older candidate set or stale official harness output batch is
  rejected.
- Final audit requires the API-surface parity report to be bound to the same
  campaign run set by run-set digest, and to match the recomputed four-surface
  parity audit.  A stale or mismatched parity report cannot authorize final
  claims.
- Final audit requires a validated `benchmark_source_manifest.json` with pinned
  dataset snapshots, source revisions, case-selection protocol hashes,
  prompt/template/protocol hashes, deterministic decoding configuration hashes,
  materialized case-hash manifest hashes, evaluator config hashes, license or
  usage policy ids, and official/audited harness hashes where required.
- Final audit also requires `benchmark_case_hash_manifest.json`; its per-suite
  materialized case-set digests must match the corresponding
  `source_record.materialized_case_hash_manifest_sha256` values in the source
  manifest.
- The source manifest used for final audit must be the bound output from
  `benchmark-source-manifest-bind-case-hashes`; matching digest fields alone are
  not enough unless the manifest also carries a valid case-hash binding receipt
  for the current case-hash manifest artifact.
- `runs.json`, `scorecard.json`, and `claim_audit.json` are bound by a
  hash-only run-set digest.  The digest is recomputed from safe run receipts
  during final audit, so a scorecard or claim audit generated from a different
  set of candidate runs is rejected even when aggregate run counts still match.
- Final audit also requires a provider baseline freeze manifest generated before
  the campaign.  The freeze manifest binds the all-available provider candidate
  set, registry receipt, and Axio tier target policy with hashes only, and final
  audit rejects campaign, run, scorecard, or claim artifacts whose provider
  candidate set no longer matches that frozen universe.
- If any suite, category, provider tier, Axio run, exact case/prompt/decoding
  alignment, paired case overlap, or statistical gate is missing,
  `all_final_claims_allowed` is false.

Recommended campaign preparation order:

1. Run live provider probing, generate `generated_registry.json`, emit redacted
   probe/registry evidence, and pass `provider-probe-evidence-audit`.
2. Search and record non-target-suite public evidence, then freeze the
   configured-provider-pool top three with `benchmark-provider-baseline-freeze
   --external-ranking-manifest <PRIVATE_WORK_DIR>/external_provider_ranking.json
   --provider-probe-evidence-audit
   <WORK_DIR>/provider_probe_evidence_audit.safe.json`.  The input must be
   created after the live provider inventory and before any target-suite run.
3. Generate `methodology.json` with `benchmark-methodology`.
4. Generate `dataset_manifest.template.json` and
   `benchmark_source_manifest.template.json` with `benchmark-dataset-template`
   and `benchmark-source-manifest-template`.
5. Fill and validate `benchmark_source_manifest.json` with
   `benchmark-source-manifest-validate`.
6. Generate `acquisition_checklist.json` and `import_batch.template.json` with
   `benchmark-acquisition-checklist` and `benchmark-import-batch-template`.
7. After the operator has accepted the current GPQA gated terms in the official
   Hugging Face account, inject `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` through
   the process environment or secret manager and run the fixed-revision
   `benchmark-acquire-gpqa-diamond` command below. Do not pass a token as a CLI
   argument and do not use an older public archive to bypass the current gate.
8. Fill the `dataset` paths for suites handled by the local deterministic
   runner, and fill/import official-harness suites such as LiveCodeBench,
   HumanEval, BFCL, tau-bench, and MT-Bench with the batch template.
9. Use `benchmark-import-official-run` or `benchmark-import-official-batch` for
   official/audited harness outputs and `benchmark-assemble-manifest` to build
   `dataset_manifest.json` from local JSONL datasets plus safe imported run
   artifacts.
10. Run `benchmark-case-hash-manifest` from `dataset_manifest.json`, then run
   `benchmark-source-manifest-bind-case-hashes` to produce
   `benchmark_source_manifest.bound.json`, and rerun
   `benchmark-source-manifest-validate` on the bound source manifest.
11. Run `benchmark-official-import-audit` with the dataset manifest, bound source
    manifest, case-hash manifest, harness-pin manifest, and import directory.
12. Run `benchmark-validate-dataset` for each local deterministic-runner JSONL.
13. Run `benchmark-readiness` with the generated registry and fix every reported
   reason code.
14. Run the live `benchmark-campaign` with the same generated registry,
    `--provider-baseline-freeze <WORK_DIR>/provider_baseline_freeze.safe.json`,
    and `--provider-probe-evidence-audit
    <WORK_DIR>/provider_probe_evidence_audit.safe.json` so the campaign is
    bound to the live-probe evidence and immutable configured-provider-pool
    top-three mapping.
15. Run `benchmark-final-audit` on the campaign directory with
    `--source-manifest <WORK_DIR>/benchmark_source_manifest.bound.json` and
    `--case-hash-manifest <WORK_DIR>/benchmark_case_hash_manifest.json`,
    `--provider-probe-evidence-audit <WORK_DIR>/provider_probe_evidence_audit.safe.json`, and
    `--provider-baseline-freeze <WORK_DIR>/provider_baseline_freeze.safe.json`,
    `--official-import-audit <WORK_DIR>/official_import_audit.safe.json`, and
    `--api-surface-parity <WORK_DIR>/api_surface_parity.safe.json`.
16. Inspect `final_audit.json`; it must report `final_completion_allowed: true`
   before the final `axio-fast` / `axio-terra` / `axio-pro` superiority claims
   are allowed.

Benchmark runner formats:

- `multiple_choice`: GPQA, MMMU text slices, Global-MMLU slices, ARC-style rows.
  GPQA Diamond remains blocked until an authorized operator accepts its upstream
  access terms. `benchmark-acquire-gpqa-diamond` fixes dataset id, revision,
  official Git blob identity, byte count, and row count; streams to a mode-0600
  temporary file; validates the CSV; and atomically installs the artifact and
  authorization receipt without persisting the token, download URL, examples,
  or answers. Every later materialization rechecks the authorization contract,
  SHA-256, Git blob, size, row count, and CSV schema rather than trusting only a
  `status=downloaded` flag. The adapter then creates one fixed per-case
  SHA-256-derived option order before the campaign, so no candidate sees the
  source CSV's answer-position bias and every compared run receives the same
  option map.

Authorized GPQA acquisition:

```bash
# HF_TOKEN or HUGGING_FACE_HUB_TOKEN must already be injected by the process
# environment or secret manager. Add AXIO_FUSION_USE_SYSTEM_PROXY=1 only when
# the local 127.0.0.1:10808 proxy is required.
PYTHONPATH=src python3 -m axio_fusion_api.cli \
  benchmark-acquire-gpqa-diamond \
  --accept-no-example-leakage-terms \
  --output private/gpqa_acquisition_receipt.safe.json

PYTHONPATH=src python3 -m axio_fusion_api.cli \
  benchmark-materialize-datasets \
  --suite-id gpqa_diamond \
  --output private/gpqa_materialization_receipt.safe.json
```

The acquisition command has no token argument. Missing terms acceptance,
missing credentials, 401/403, untrusted redirects, proxy errors, size/blob/hash
  mismatch, malformed CSV, and manifest commit failures all fail closed with a
  content-free reason-code receipt. A local CSV without the matching current
  authorization receipt is never promoted into the evaluation corpus.

- `exact_match`: MATH-500, AIME, BBH-style final-answer rows.  The runner uses
  the pre-registered `final_answer_text_v1` parser to extract common final-answer
  wrappers such as `####`, `Final answer:`, and `\boxed{...}` before normalized
  exact match; each case artifact records the parser id without storing raw
  model output or reference text.
- `translation_chrf`: FLORES-style source/reference rows scored with chrF.
- `python_code`: HumanEval/LiveCodeBench-style Python prompt plus unit tests.
  Code execution is disabled unless `AXIO_FUSION_ALLOW_BENCHMARK_CODE_EXEC=1`.
- `tool_call_ast`: BFCL/tau-bench-style tool-call JSON AST matching.
- `instruction_checks`: simplified deterministic checks such as required
  substrings, forbidden substrings, regexes, JSON requirement, and word limits.
  These are pilot-only for IFEval; final IFEval claims require the official
  Google Research checker or an audited equivalent imported as safe receipts.
- `external_pairwise_judge`: MT-Bench-style pairwise judge results should be
  imported as safe run artifacts from an official or separately audited judge
  harness; the local runner will not fabricate judge scores.

Benchmark campaign manifest:

```json
{
  "suites": [
    {"suite_id": "gpqa_diamond", "dataset": "data/gpqa_diamond.jsonl", "task_format": "multiple_choice"},
    {"suite_id": "math_500", "dataset": "data/math_500.jsonl", "task_format": "exact_match"},
    {"suite_id": "humaneval", "dataset": "data/humaneval.jsonl", "task_format": "python_code"}
  ]
}
```

`benchmark-campaign` runs `axio-fast`, `axio-terra`, `axio-pro`, and the top
provider baselines selected from the registry.  It writes `runs/*.json`,
`runs.json`, `scorecard.json`, `claim_audit.json`, `methodology.json`, and
`provider_baseline_freeze.safe.json`, and `campaign.json`.
Campaign summaries persist dataset path hashes and safe run receipts, not raw
dataset contents, raw labels, raw prompts, or provider outputs.  Existing run
files are resumed by default so long campaigns can continue after interruption.
`benchmark-campaign-progress-plan` audits a partially completed campaign and
emits a hash-only resume/repair queue for missing or invalid run artifacts,
including API-surface and provider-baseline coverage counts, without storing raw
run paths, dataset paths, provider model ids, prompts, labels, or outputs.
`benchmark-api-surface-parity` separately checks whether every Axio
suite/model cell has Chat Completions, Responses, Anthropic Messages, and Gemini
runs over identical case hashes, prompt-protocol hashes, and decoding hashes,
and whether the cross-surface score delta stays within tolerance.
Before running, the campaign records a hash-only readiness preflight receipt for
the same dataset manifest, candidate set, provider-baseline policy, and minimum
case count.  Final audit requires that receipt to show all required suites ready
and claim-audit possible, so incomplete acquisition cannot be laundered into a
final superiority claim.
Campaign summaries also include a provider baseline census with provider
candidate id hashes, provider profile hashes, available-pool set digests, and
the externally pre-registered top-three receipt digest.  Final public claims
require exactly those three frozen candidates, while the available-pool digest
proves that the ranking was chosen against the complete live provider pool.

When `benchmark-matrix`, `benchmark-acquisition-checklist`, or
`benchmark-acquisition-status` receives `--provider-baseline-freeze`, it enters
the formal top-three cohort automatically. That cohort is fixed at 15 run
units: three Axio models across four public API surfaces plus the three frozen
single-provider baselines. Any `--candidate-id` filter and
`--all-provider-baselines` diagnostic request are ignored for that formal
cohort, so a later import or campaign command cannot quietly omit a tier or
expand the official comparison set. Without a freeze these commands remain
diagnostic and may include legacy baselines or an all-provider inventory, but
their output cannot support a final superiority claim.

Campaign summaries also include a provider baseline freeze receipt.  Final audit
requires the freeze digest to match the campaign receipt and requires the frozen
provider candidate set to match campaign, run, scorecard, and claim artifacts.
Campaign summaries also include a hash-only provider registry receipt.  Final
audit requires the census's available provider profile set digest to match that
registry receipt, so the configured-provider-pool top-three ranking cannot be
authorized from an unbound or hand-edited provider pool.
Campaign summaries also include a hash-only methodology receipt.  Final audit
recomputes it from `methodology.json` and requires it to match the campaign, so
the scientific method contract cannot be swapped after the run.
`runs.json` also carries a `run_set_digest_sha256`; `scorecard.json` and
`claim_audit.json` carry `source_run_set_digest_sha256`.  These values are
computed from hash-only run receipts, not raw prompts, labels, provider outputs,
or provider URLs.

Run `benchmark-readiness` before the live campaign.  It checks that all 21
required suites are present, dataset files exist, enough cases are available,
dataset rows satisfy the expected task-format schema, duplicate case hashes are
absent, obvious answer-in-prompt leakage is not detected, at least three provider
baselines will be evaluated, and external-judge suites have imported run
artifacts for every run unit.  For official-harness suites it emits hash-only
import coverage counts: expected, provided, valid, missing, and invalid receipts,
without persisting raw candidate ids or import paths.
Its `will_claim_audit_be_possible` flag is stricter than dataset readiness:
because final superiority claims require the externally evidenced
configured-provider-pool top three to be pre-registered from the full available
registry, that flag is false unless the run uses a valid
`--provider-baseline-freeze` artifact.

`benchmark-validate-dataset` can validate one JSONL before adding it to a
campaign.  Validation receipts contain only counts, reason codes, case hashes,
and path hashes; they do not persist raw questions, references, labels, prompts,
or dataset paths.

Run `benchmark-final-audit` after the live campaign.  It reads only the safe
campaign artifacts plus the validated source and case-hash manifests, and blocks final
completion unless the campaign is live, all 21 required suites and three
provider baselines per suite are present, all three Axio tier claims pass the
paired case-hash sign-test gate with Holm-Bonferroni family-wise correction, the
source manifest pins every dataset snapshot/source/materialization/evaluator
receipt required for final claims, the materialized case-set digests match
between the source manifest and case-hash manifest, the official import audit
run-set digest matches the campaign's official/audited harness runs, the API
surface parity report run-set digest matches the campaign runs, and no artifact
claims that
raw prompts, labels, provider outputs, dataset content, or secrets were
persisted.  It also emits hash/count/reason-code receipts for every candidate
run and case-result row, and blocks final completion if any run reports
benchmark labels used for training or a raw-content persistence flag.  It also
recursively scans safe campaign artifacts for raw
provider-candidate ids and blocks final completion if a provider candidate
looks like a provider/model identifier instead of a hash alias; the finding
receipt stores only artifact names, paths, and hashes, not the raw id.  It also
requires the campaign's `methodology.json` to cover all 21 suites and the global controls
for fixed snapshots, train/eval isolation, same cases/prompts across candidates,
deterministic decoding, paired case-hash claims, fixed configured-provider-pool rank mapping,
Holm-Bonferroni family-wise multiple-comparison correction, and
position-balanced external judging.
For every suite, the final gate also rejects runs whose prompt/template/protocol
hashes are missing, internally conflicting, or not identical across Axio,
ablation, and provider candidates, or whose shared hash does not match the
pre-registered `source_record.prompt_protocol_sha256` in the source manifest.
It applies the same alignment and source-manifest binding check to
`decoding_config_sha256`, so final comparisons cannot mix temperature, sampling,
seed, or official deterministic-default policies across candidates.
The final gate cross-checks safe artifact counts as well: campaign expected and
completed run counts, `runs.json` actual run count, scorecard run count, and
claim-audit run count must agree, and the campaign claim summary must match the
claim-audit artifact.  It also recomputes the run-set digest from `runs.json`
and requires `scorecard.json` and `claim_audit.json` to be bound to that same
digest.  The provider baseline census must also be bound to the campaign's
provider registry receipt through matching provider-profile hash sets and set
digests.

External judge import example:

```json
{
  "suites": [
    {
      "suite_id": "mt_bench_work",
      "task_format": "external_pairwise_judge",
      "imported_runs": {
        "axio-pro@chat_completions": "official_judge_runs/axio_pro_chat_mt_bench.safe.json",
        "axio-pro@responses": "official_judge_runs/axio_pro_responses_mt_bench.safe.json",
        "axio-pro@anthropic": "official_judge_runs/axio_pro_anthropic_mt_bench.safe.json",
        "axio-pro@gemini": "official_judge_runs/axio_pro_gemini_mt_bench.safe.json",
        "provider::<profile-hash-alias>": "official_judge_runs/vendor_model_a_mt_bench.json"
      }
    }
  ]
}
```

Imported runs must already be safe Axio benchmark run artifacts or equivalent
prompt-free receipts.  The campaign copies their safe metrics into its run
directory and does not persist raw judge prompts, raw answers, or raw labels.
Legacy raw provider identifiers are accepted only as compatibility input for
imported-run lookup; generated campaign artifacts use hash aliases instead of
raw provider/model names.

Runtime controls:

- `AXIO_FUSION_API_KEYS`: optional comma-separated gateway API keys for public
  generation endpoints and general gateway access.
- `AXIO_FUSION_OPERATOR_API_KEYS`: optional comma-separated operator API keys.
  When configured, control-plane endpoints require one of these keys via a
  bearer authorization header, `x-api-key`, or `x-axio-operator-key`.  When it is
  unset, those endpoints keep the legacy behavior and use `AXIO_FUSION_API_KEYS`
  if ordinary gateway auth is configured.
- `AXIO_FUSION_RATE_LIMIT_PER_MINUTE`: optional per-tenant in-memory rate limit.
- `AXIO_FUSION_TENANT_DAILY_BUDGET_USD`: optional per-tenant in-memory daily cost cap.
- `AXIO_FUSION_RESPONSE_CACHE=1`: enable in-memory response cache by request fingerprint.
- `AXIO_FUSION_RESPONSE_SESSION_TTL_SECONDS`: in-memory Responses continuation
  lifetime, default `1800`, capped at `86400` seconds.
- `AXIO_FUSION_RESPONSE_SESSION_MAX_SESSIONS`: process-wide continuation cap,
  default `1000`; set `0` to disable new continuation storage.
- `AXIO_FUSION_RESPONSE_SESSION_MAX_CONTEXT_CHARS`: maximum retained
  continuation context size, default `98304`, capped at `4194304`.
- `AXIO_FUSION_CIRCUIT_BREAKER_FAILURES`: provider failure count before temporary circuit-open behavior.
- `AXIO_FUSION_ARTIFACT_DIR` or `AXIO_FUSION_FEEDBACK_LOG`: enable sanitized feedback JSONL.
- `AXIO_FUSION_TRACE_LOG`: optional explicit sanitized execution trace JSONL path.
- `AXIO_FUSION_TOOL_LOG`: optional explicit sanitized tool execution JSONL path.
- `AXIO_FUSION_CORS_ALLOW_ORIGINS`: optional comma-separated browser origin
  allowlist.  When unset, CORS response headers are not emitted.  When set,
  `OPTIONS` preflight requests can complete without an API key, but the actual
  public and operator requests still require the normal gateway/operator auth.
- `AXIO_FUSION_CORS_ALLOW_CREDENTIALS=1`: optionally emit
  `Access-Control-Allow-Credentials: true` for allowlisted non-wildcard origins.
- `AXIO_FUSION_CORS_MAX_AGE_SECONDS`: optional preflight cache duration,
  default `600`, capped at `86400`.
- `AXIO_FUSION_MAX_TOOL_CALLS`: default maximum tool calls per batch.
- `AXIO_FUSION_ALLOW_NETWORK_TOOLS=1`: opt in to network-search tools.
- `AXIO_FUSION_ALLOW_DESTRUCTIVE_TOOLS=1`: opt in to externally approved destructive/write tools.
- `AXIO_FUSION_PROVIDER_MAX_ATTEMPTS_PER_KEY`: bounded transient provider retry
  attempts per key, default `2`, capped at `4`.
- `AXIO_FUSION_PROVIDER_RETRY_BACKOFF_MS`: optional deterministic per-key retry
  backoff base in milliseconds, default `0`.
- `AXIO_FUSION_PROVIDER_EMPTY_RESPONSE_RETRIES`: bounded semantic retry when a
  provider returns HTTP success but neither visible text nor a native tool call,
  default `1`, capped at `1`; after exhaustion the normal replica/fallback
  policy takes over.

Per-request policy fields such as `max_total_model_calls`,
`max_latency_ms`, `quality_target`, `max_models`, and `max_depth` are
canonicalized from every compatible API shape.  `quality_target` is interpreted
as a 0-1 quality pressure signal, with percentage-like values such as `90`
normalized to `0.90`.  For `axio-terra` and `axio-pro`, high targets can force
cost-guarded Fusion even on otherwise simple requests, expand the expert panel,
raise the minimum independent candidates required before Judge comparison,
tighten early-exit thresholds, and trigger targeted escalation when the Judge
marks an answer ready but its ranked score, confidence, or explicit evidence is
below the requested quality floor.  For `axio-fast`, the same signal can only
open a bounded two-model `fast_light_verify` route with no recursive depth.
These controls remain bounded by explicit cost, latency, depth, and model-call
limits.
Provider input adapters also forward decoding controls consistently: Chat,
Responses, Anthropic Messages, and Gemini-compatible calls carry the applicable
temperature, top-p, stop-sequence, and max-output settings when the caller
explicitly supplies them, so benchmark runs can keep decoding protocols aligned
across mixed upstream API formats. Unspecified temperature is omitted and the
upstream provider default is used; this avoids sending unsupported temperature
fields to reasoning models while preserving explicit deterministic `0.0`.
Before a request starts a Fusion panel, Axio also emits a
`fusion_admission` receipt.  This estimates direct-model quality, panel quality,
expected quality gain, risk-reduction credit, extra cost, extra latency, and a
utility score.  Explicit safety or quality policies can still force Fusion, and
depth, latency, budget, and model-pool blockers can still prevent it, but
ordinary terra requests are admitted only when the expected gain beats cost and
latency penalties.  The receipt stores profile/provider hashes, scores, reason
codes, and cost/latency estimates only; it does not persist prompts, provider
outputs, API keys, or raw provider ids in safe traces.
`max_total_model_calls` is enforced by a runtime call budget lock across expert
candidates, provider fallback, structured judge, targeted escalation, and
synthesizer calls.  `max_cost_usd` is enforced by a runtime cost budget lock
over the same stages using registry token prices and prompt/output token
estimates; when the remaining estimated budget is too small, later optional
calls fall back to deterministic local ranking or the best completed candidate.
`axio-fast` keeps a single-model default route with a small default internal
cost ceiling of `0.001` USD per request so the richer safe routing context still
fits ordinary low-price provider calls; caller-supplied `max_cost_usd` remains a
stricter override.  Cost receipts store estimated cost, reservations, skipped
stage counts, reason codes, and profile hashes only.
`max_latency_ms` is also enforced as an overall live-run deadline budget across
the same stages.  Provider calls receive the remaining deadline as their timeout
where possible, and late optional judge, escalation, or synthesis calls are
skipped instead of extending the request.  Deadline receipts store elapsed time,
remaining time, skipped-stage counts, reason codes, and profile hashes only.
For the bounded parallel expert wave, a deadline timeout also sets a
cooperative cancellation event. Tasks that have not started are cancelled;
provider responses that arrive after cancellation are charged to the local
runtime accounting and discarded instead of entering Judge or synthesis. The
trace records only pending/cancelled/late-result counts, so a slow custom client
cannot silently turn a post-deadline answer into Fusion evidence.
When `rank_first_candidate_compression` is enabled in the route budget, Axio
uses rank-first, diversity-aware synthesis selection.  The highest Judge-ranked
candidate is kept, then the remaining full-text slots prefer candidates that are
still above the quality floor while adding evidence-backed novelty, critic or
domain-specialist coverage, tool support, or targeted-escalation closure.  Very
low ranked noise remains compressed to hash/count receipts.  This preserves
useful minority insights without letting model count or disagreement masquerade
as truth, and durable traces still do not persist raw candidate text.
Every live provider call also runs through a context-window budget when the
selected registry profile declares `context_tokens` or `context_window_tokens`.
Axio reserves output tokens, accounts for protocol overhead, and deterministically
truncates oversized expert, Judge, targeted-escalation, or synthesis prompts
before sending them to the provider.  Oversized candidate packets include
bounded excerpts plus answer hashes, character counts, and token estimates.
Prompt-budget receipts record hashes, lengths, token estimates, context limits,
and truncation flags only; raw budgeted prompts and raw candidate text are not
persisted.
When `early_exit_enabled` is active on a non-Hermes Fusion route, Axio can skip
the Synthesizer after the Judge if multiple candidates have high pairwise
agreement, explicit evidence, no reported contradictions or coverage gaps, and
a high-ranked top candidate. The final answer is then the Judge-selected
candidate, and the trace stores only the early-exit reason, agreement score,
and answer hash. Hermes-enabled routes instead record
`hermes_acting_aggregator_required` and continue to their one acting
Synthesizer.
For fusion routes that require a structured Judge, Axio also enforces a minimum
independent-candidate panel before judging.  If one provider branch fails,
times out, trips a circuit breaker, or is blocked by a runtime guard while fewer
than two completed candidates remain, the orchestrator attempts a same-capability
replacement from the unused, privacy-filtered selected model pool.  If no safe
replacement is available, it continues in degraded mode and records only
profile/provider hashes, counts, status codes, and reason labels.

Provider reliability:

- Provider API key variables may contain a comma, semicolon, or newline
  separated key list.  The provider client tries keys in order for both
  completion calls and `/models` discovery, then falls through to the next key
  if a gateway returns HTTP, transport, timeout, or invalid-JSON errors.
- Within each key, the provider client retries bounded transient failures inside
  the caller's timeout budget.  Retryable failures are network/timeout errors
  and HTTP `408`, `409`, `425`, `500`, `502`, `503`, and `504`.  HTTP `401`,
  `403`, and `429` are not retried on the same key; they rotate to the next key
  when one exists or surface to the orchestrator for circuit breaking, fallback,
  panel repair, or degraded-mode handling.
- Gemini-compatible providers use the same rotation policy with `key=` query
  parameters; OpenAI/Responses/Anthropic-compatible providers use a
  bearer-style `Authorization` header.
- Any configured Responses-compatible channel is retained only when `/models`
  and short live probes show usable models; unavailable models are excluded from
  generated live registries instead of hard-coding the whole channel as failed.
- Failure messages and probe/readiness artifacts record only safe attempt
  counts, error classes, and HTTP status codes.  They do not persist API keys,
  bearer headers, query URLs, raw provider error bodies, or provider outputs.

Operational endpoints:

- `GET /v1/health`
- `GET /v1/models`
- `GET /v1/benchmarks`
- `GET /v1/axio/runtime`
- `POST /v1/axio/route-plan`

`GET /v1/axio/runtime`, `POST /v1/axio/route-plan`, `POST /v1/inventory`,
`POST /v1/axio/feedback`, `POST /v1/axio/agent-outcome`, and
`POST /v1/axio/tools/execute` are operator/control-plane endpoints.  If
`AXIO_FUSION_OPERATOR_API_KEYS` is configured, public gateway keys alone cannot
use them.  The four compatible public generation endpoints do not echo the full
internal `route_plan`,
`fusion_trace`, or `judge_result`; their `metadata` contains hash-only summaries
for cost, latency, routing strategy, judge readiness, and provider call counts.

`GET /v1/models` exposes only the public Axio model ids
`axio-fast`, `axio-terra`, and `axio-pro`.  It includes per-model usability
metadata and a hash-only `registry_summary`; it does not return the underlying
provider registry, raw provider model ids, provider URLs, API key env names, or
provider outputs.  `usable` means the registry can route the tier, while
`live_usable` means the configured provider credentials are actually ready; the
live credential summary is hash-only and still does not persist secrets, env
values, or provider URLs.
- `POST /v1/axio/feedback`
- `POST /v1/axio/agent-outcome`
- `POST /v1/axio/tools/execute`

Streaming is supported for all four public API families through SSE-compatible
response bodies.  For Chat Completions, Responses, and Anthropic-compatible
Messages, set `"stream": true`; for Gemini-compatible calls use
`:streamGenerateContent`.
Terminal events remain protocol-native: only Chat Completions emits
`data: [DONE]`; Responses ends with `response.completed`, Anthropic ends with
`message_stop` after `message_delta`, and Gemini-compatible streaming follows
the `alt=sse` response stream without an OpenAI-style sentinel.
Responses streaming also keeps the public lifecycle explicit: `response.created`
and `response.in_progress`, item/content add and done events, output-text
delta/done events, and function-call-argument delta/done events all carry a
monotonic 1-based `sequence_number`. Function argument events preserve both
`response_id` and `call_id`, and the completed Responses object exposes the
current public `background`, `service_tier`, `text.format`, `truncation`, and
token-detail fields without exposing prompts, provider identifiers, or
continuation internals. The Chat `stream_options.include_usage` trailer remains
Chat-only and does not leak into Responses streaming.

Privacy and tool isolation:

- Set `metadata.privacy_level` to `public`, `internal`, or `confidential`.
- `public` may use external providers; `internal` requires tags such as
  `contracted_provider`, `data_agreement`, `internal_approved`, `local`, or
  `private_deployment`; `confidential` requires `local`, `on_prem`,
  `private_deployment`, or `confidential_approved`.
- Tool schemas are never persisted in route plans.  The router stores only tool
  hashes, categories, and per-role permission decisions.
- OpenRouter-style `{"type": "fusion"}` tool entries are treated as
  prompt-free route-control plugins.  Top-level `plugins: [{"id": "fusion"}]`
  entries are normalized into the same route-control path.  Route plans record
  only hashed plugin receipts and activation status.
- Destructive/write/execution tools are default-denied and require external
  approval outside the model call path.
- `POST /v1/axio/tools/execute` and `tool-execute` execute only safe built-ins
  by default: `math_eval`, `json_get`, and `text_search`.
- Tool execution receipts include tool-name hashes, argument hashes, result
  hashes, status, latency, and policy flags.  They do not persist raw tool
  arguments, raw tool results, prompts, provider outputs, or secrets.
- `judge` and `synthesizer` roles are read-only at the tool gateway.  Destructive,
  write, shell, deployment, and network-capable tools are blocked unless the
  runtime policy explicitly allows the category and the call has external
  approval where required.

Tool execution endpoint shape:

```json
{
  "role": "primary_solver",
  "max_tool_calls": 3,
  "calls": [
    {"name": "math_eval", "arguments": {"expression": "2 + 3 * 4"}},
    {"name": "json_get", "arguments": {"document": {"a": [10]}, "path": "a.0"}},
    {"name": "text_search", "arguments": {"text": "alpha beta alpha", "query": "alpha"}}
  ]
}
```

Learning loop:

`POST /v1/axio/feedback` accepts response ids, request fingerprints, scores,
acceptance flags, route plans, trace metrics, and external verification results
from systems such as an agent harness or repair loop.  `POST
/v1/axio/agent-outcome` is a convenience alias for structured agent-loop
results: task success, step counts, tool-call counts, tool failures, repair-loop
counts, intervention flags, cost, latency, and outcome scores.  This is a
generic HTTP contract that ASciFS or any other Agent Harness may call, while the
Fusion package itself imports no ASciFS code.  Verification statuses such as
`passed` and `failed`, plus optional numeric scores, are converted into safe
router-learning and registry-calibration signals.  Feedback receipts and
`learning-report` artifacts are designed for future supervised, preference, or
reward-model training of the Orchestrator, but they only contain safe route
features, Fusion admission utilities, panel diversity metrics, prompt-budget
compression counts, candidate-standardization receipts, provider fallback
availability/routing/diversity aggregates, bounded `axio-fast` light-verify
activation flags, local Judge answer-claim cluster support counts, hashes, costs,
latencies, status labels, and outcome scores.  Raw verification details, source
names, task text, agent traces, and tool outputs are hashed or counted, not
persisted as text.

`router-policy-shadow-patch` converts feedback, agent outcomes, and safe
execution traces into auditable router policy recommendations grouped by
`public_model`, strategy, and task type.  It can suggest lower Fusion activation
thresholds for weak direct routes, higher quality targets or targeted
escalation for weak Fusion routes, stronger agentic tool verification when
tool failures or repair loops rise, more provider/API-format diversity when
error-correlation estimates are high, rank-first prompt compression when
context truncation hurts quality, live-probe refresh or wider cross-provider
fallback pools when safe fallback receipts show weak availability, bounded
`axio-fast` light verification when uncertain fast direct routes underperform,
independent answer-claim verification when local Judge clusters show weak
support or contradictions, or fewer model calls/earlier exits when quality is
already strong but cost or latency is high.  The artifact is always
`shadow_only` and `safe_to_apply_automatically: false`; it changes no production
policy and is meant for offline replay, ablations, and human review before any
router update.

Benchmark scorecards are a separate evidence stream. `learning-report` rejects
scorecard input by default; `--allow-benchmark-diagnostics` admits it only as a
diagnostic summary. Admitted benchmark scores never enter router-learning
features, production policy suggestions, registry calibration, or automatic
policy application. The final benchmark claim still requires the independent
training-contamination audit.

If an external harness has a precomputed held-out case hash, it may pass fields
such as `benchmark_case_hash` or `case_hashes`; these hashes are preserved only
as hashes so `training-contamination-audit` can block benchmark-derived learning
signals before any final superiority claim.

`benchmark-campaign` writes a default `training_contamination_audit.json` for
pure benchmark campaigns with no learning, feedback, trace, or calibration
inputs.  `training-contamination-audit` is the held-out benchmark guardrail for
nontrivial learning loops.  Before making final public superiority claims after
any policy learning or registry calibration, run it across benchmark runs,
learning datasets, learning reports, registry calibration reports, feedback,
and traces, writing the result to the campaign directory so
`benchmark-final-audit` can enforce it.  It blocks the claim package if
benchmark case hashes overlap with learning artifacts, if a training dataset
says benchmark labels were used, or if final benchmark results were used for
registry calibration without an explicit separate calibration policy.

Execution traces:

When `AXIO_FUSION_TRACE_LOG` or `AXIO_FUSION_ARTIFACT_DIR` is configured, the
gateway appends prompt-free execution receipts to JSONL.  Trace receipts include
request feature hashes, task DAG summaries, selected profile hashes, candidate
hash/count receipts, judge summary counts, final-answer hash, cost, latency, and
runtime guard state.  They deliberately exclude raw prompts, raw candidate text,
raw provider output, secrets, and raw provider/model names.

Task DAG:

Route plans include a domain-aware DAG with checkpoints.  Code/security tasks
add boundary, authorization, injection, leakage, and failure-path validation
nodes; science tasks add claim extraction, evidence mapping, hypothesis
comparison, and gap analysis; math/logic tasks add formalization,
counterexample, and verification nodes; agentic tasks add tool-use planning,
permission checks, and dry-run tool sequence nodes.

Registry calibration:

`calibrate-registry` turns safe operational artifacts into an updated model
registry. By default it reads provider probe reports, feedback receipts, and
execution traces, then updates dynamic profile fields
such as `health`, `availability`, `recent_success_rate`,
`observed_success_count`, `observed_failure_count`, `p50_latency_ms`,
and `p95_latency_ms`. The router uses
these reliability signals when ranking models, so failing or degraded providers
can be pushed down without changing the public API.  External verification
failures also count as negative feedback for selected profiles when no explicit
human score is supplied.  Calibration artifacts do not persist raw prompts, raw
feedback text, raw verification details, raw benchmark labels, provider outputs,
or secrets.

Benchmark-derived capability calibration is deliberately blocked by default. It
requires `calibrate-registry --allow-benchmark-calibration` and is exploratory
only; the resulting registry must be treated as ineligible for a final
superiority claim until a separate held-out calibration policy and
`training-contamination-audit` pass are recorded. Benchmark results must never
silently change the registry used by the final Axio-versus-baseline campaign.

## Provider Environment

Optional CPA Plus / Responses-compatible:

- `AXIO_CPA_PLUS_BASE_URL`
- `AXIO_CPA_PLUS_API_KEY` or `AXIO_CPA_PLUS_API_KEYS`
- `AXIO_CPA_PLUS_MODELS`

Optional AISZ / Responses-compatible:

- `AXIO_AISZ_BASE_URL`
- `AXIO_AISZ_API_KEY` or `AXIO_AISZ_API_KEYS`
- `AXIO_AISZ_MODELS`

AISZ is treated as a Responses-compatible input channel.

NVIDIA / OpenAI Chat Completions-compatible:

- `AXIO_NVIDIA_BASE_URL` (required; Fusion has no hard-coded provider endpoint fallback)
- `AXIO_NVIDIA_API_KEYS` or `AXIO_NVIDIA_API_KEY`
- `AXIO_NVIDIA_MODELS`

NVIDIA is treated as an OpenAI Chat Completions-compatible input channel.

Generic OpenAI-compatible:

- `AXIO_OPENAI_COMPAT_BASE_URL`
- `AXIO_OPENAI_COMPAT_API_KEY`
- `AXIO_OPENAI_COMPAT_MODELS`

Generic Anthropic Messages-compatible:

- `AXIO_ANTHROPIC_BASE_URL`
- `AXIO_ANTHROPIC_API_KEY`
- `AXIO_ANTHROPIC_MODELS`

Arbitrary multi-provider input can be declared with a non-secret JSON file via
`AXIO_FUSION_PROVIDER_CONFIG_FILE`, or for ephemeral deployments with
`AXIO_FUSION_PROVIDER_CONFIGS` or `AXIO_FUSION_PROVIDERS_JSON`. The JSON has a
`providers` array. Each provider declares only environment-variable names and
model ids, never raw endpoints or secrets. File configuration is loaded first;
an inline configuration may then override the same provider/model profile for
one process:

```json
{
  "providers": [
    {
      "provider": "vendor-chat",
      "api_format": "chat/completions",
      "base_url_env": "VENDOR_CHAT_BASE_URL",
      "api_key_env": "VENDOR_CHAT_API_KEY",
      "models": ["model-a", "model-b"]
    },
    {
      "provider": "vendor-responses",
      "api_format": "responses",
      "base_url_env": "VENDOR_RESPONSES_BASE_URL",
      "api_key_env": "VENDOR_RESPONSES_API_KEY",
      "models_env": "VENDOR_RESPONSES_MODELS"
    },
    {
      "provider": "vendor-anthropic",
      "api_format": "anthropic",
      "base_url_env": "VENDOR_ANTHROPIC_BASE_URL",
      "api_key_env": "VENDOR_ANTHROPIC_API_KEY",
      "models": ["model-c"]
    }
  ]
}
```

All configured models enter the same privacy-filtered registry.  Fusion then
selects a complementary panel across providers and input API formats based on
task domain, cost, latency, role fit, reliability, and health-probe evidence.

Every configured provider base URL must be an explicit HTTP(S) URL with an
optional path prefix such as `/v1`. Fusion rejects non-HTTP(S) schemes,
embedded user-info, query strings, fragments, missing hosts, invalid ports, and
whitespace before credential readiness or network access is granted. This keeps
API keys in headers or the provider's explicitly supported query mode and
prevents malformed endpoint configuration from being mistaken for a usable
model. Loopback HTTP endpoints remain valid for development proxies and
offline/loopback integration tests; they are not a local-model execution mode.

## Design Notes

Axio Fusion uses deterministic request analysis and budget gates first.  Only
when expected quality gain justifies cost/latency does it expand into multiple
experts.  Expert outputs are standardized, judged by a structured rubric, and
only disputed or missing subparts can trigger targeted escalation.  Benchmark
scorecards are required before making superiority claims over single-model
baselines.

For live fusion runs with multiple deduplicated candidates, the service first
asks the selected judge model for a structured comparison.  That provider-backed
judge can change candidate ranking, synthesis readiness, and targeted
follow-up decisions.  If the judge call fails or returns malformed JSON, Axio
falls back to the deterministic local rubric.  Judge artifacts sanitize all
free-form judge text into hashes or counts, so raw candidate answers and raw
judge output are not persisted.

References used as product ideas, not vendored code:

- OpenRouter Fusion and routing concepts: https://openrouter.ai/docs
- Sakana AI Fugu model-interface idea: https://sakana.ai/fugu/
- NousResearch Hermes Agent MoA process (audited at commit `e89bc58a5ba80ec6be19b43beca37cbb03091afd`): https://github.com/NousResearch/hermes-agent
- Harness Engineering for Self-Improvement: https://lilianweng.github.io/posts/2026-07-04-harness/
- Anthropic effective agents patterns: https://www.anthropic.com/engineering/building-effective-agents
