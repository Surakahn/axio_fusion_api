# Pre-Fusion Model Screening

`model_screening.py` is the control-plane gate between provider enrollment and
the Fusion runtime. It does not call local model weights and it is not part of
the independent 21-suite benchmark evaluator.

The public wrapper for this gate is
`axio_fusion_api.available_model_generation.generate_available_model_set()`. It
is the single available-model generation operation: it invokes the complete
screening workflow, validates the report and private registry again, and
returns one artifact containing the full research ranking, the available-only
operational ranking, and the logical model list that Fusion may consume. The
wrapper does not invent a second ranking algorithm and does not use benchmark
cases or labels.

## Contract

The workflow has five ordered stages:

1. Build the complete physical inventory. When a provider configuration is
   present and no explicit `--registry`/`profiles` input is supplied, the
   workflow calls each configured provider's `/models` endpoint first. The
   response is held only in process memory, converted into `ModelProfile`
   objects, and merged with explicitly configured model rows. A failed or
   empty discovery without an explicit static model list blocks the run. This
   prevents the research Agent from ranking an accidentally partial provider
   pool. Profiles with the same `canonical_model_id` are one logical model and
   their provider/API combinations remain physical replicas.
2. Give bounded public-source excerpts to the configured remote research Agent.
   Candidate-specific model-card evidence is transport-isolated into a
   singleton candidate request. Candidates with only shared evidence may be
   combined into bounded batches (default 4, configurable up to 64). Each
   request must return
   `axio_fusion_api.prefusion_research_agent_output.v1` for every candidate in
   that batch, with contiguous local ranks, bounded capability axes, explicit
   role limits, and source evidence IDs. All batches are required; a missing,
   failed, slow, or invalid batch blocks the complete ranking.
3. Merge validated batches locally with the fixed deterministic policy
   `research_quality_score` descending, `confidence` descending, then
   `candidate_id` ascending, and regenerate global ranks `1..N`. The quality
   score is a bounded combination of the remote Agent's overall prior and its
   capability-axis vector; it is still only a research prior. The merge receipt
   stores only batch counts, candidate-set/output hashes, statuses, and
   latency.
4. Run independent real streaming health probes for every ranked physical
   profile. Fresh production runs use three samples by default, reject a
   requested count below two, and bound the count to five. A profile is
   eligible only when every sample is live, strict streaming transport was
   requested, the request carried the protocol's streaming flag, the response
   was actually consumed as SSE or NDJSON, at least one framed event was
   parsed, no ordinary-JSON compatibility fallback was used, the response
   contains a valid SHA-256 output hash, the status is `available`, an actual
   measured latency is present, and the latency is at most 90 seconds. A
   static p50/p95 value above the ceiling is also blocked. The aggregate stores
   hash-only per-sample receipts plus measured p50, p95, and maximum latency;
   missing or failed samples are not treated as fast.
5. Bind only the eligible profile hashes to a private loadable registry. A
   blocked screening run never produces enabled serving profiles.

## Long-Request Operational Admission

The short health probe is intentionally not treated as evidence that a model
will survive a realistic Fusion branch. A separate control-plane command runs
five fixed, synthetic workloads against each selected profile:

1. long-context input with a short answer;
2. long-context input with a JSON output contract;
3. bounded synthetic constraint reasoning with a JSON output contract; and
4. a longer operational memo request; and
5. a long-context, multi-option reasoning request with a substantial output
   budget, which catches providers whose short probes pass but whose realistic
   reasoning turn exceeds the 90-second serving ceiling.

These workloads contain no benchmark questions, labels, reference answers, or
provider ranking material. Their prompts are generated in memory and the
receipt keeps only workload/prompt hashes, output lengths, strict SSE/NDJSON
evidence, bounded error classes, and the p50/p95/maximum latency across every
attempt. A timeout or transport failure remains a failure even when another
attempt succeeds; successful answers are never substituted for missing ones.

The two resulting decisions are deliberately different:

- `production_admitted` allows the configured bounded failure rate and is a
  supplemental serving signal for a model that can still do useful bounded
  work;
- `formal_baseline_eligible` requires every fixed workload repetition to pass
  its output contract, strict streaming evidence, and the inclusive 90-second
  response ceiling. Only this decision may be used to form the non-target
  baseline cohort.

Run it against a private registry before creating or refreshing a baseline
screening plan:

```bash
PYTHONPATH=src python3 -m axio_fusion_api.cli \
  --registry <PRIVATE_REGISTRY.json> operational-admission --live \
  --timeout 90 --max-workers 4 \
  --output <PRIVATE_WORK_DIR>/operational_admission.private.json
```

The command returns a blocked status when no profile is formally eligible. A
redacted report can be requested with `--redact-provider-identifiers`; it is
for diagnostics and cannot be loaded as a serving registry. This gate is
independent from both the production short-probe admission and the later
21-suite evaluator. It does not make a capability or superiority claim.

The independent non-target baseline-screening control plane applies the same
fail-closed discipline before it spends provider budget: pinned official
scorer imports are checked while the screening plan is created, and the
runtime-preflight result is included in the source snapshot digest. Missing
optional dependencies such as `lxml` for LiveBench table scoring therefore
block the plan before the first remote answer rather than becoming a late
model-scoring error. Every provider request in that campaign is also bounded
by the shared 90-second effective timeout even when a source manifest declares
a larger timeout.

The screening manifest also freezes a narrow exception-only retry policy:
`max_exception_attempt_rounds` is capped at two total rounds (the initial
attempt plus at most one eligible retry round), with a fixed per-source
inter-round backoff. A failed physical replica may hand off immediately to a
different replica of the same canonical model in the initial round. A second
round includes only replicas that produced a classified recoverable transport
failure: timeout, network transport, rate limit, 5xx, empty provider output,
or stream/protocol failure. A `400` or another non-recoverable 4xx is recorded
and may fall through to a different replica, but it does not trigger a second
request to the same replica. Wrong answers, parser outcomes, labels, and
scores never trigger a retry. Every failed attempt records only a closed error
class, a whitelisted provider error code, and an ordinary HTTP status; raw
provider error text, URLs, and bodies are excluded from the safe evidence.
If a later same-round replica returns a visible answer, that case ends
immediately: an earlier recoverable failover remains transport telemetry, but
does not create a second-round replay requirement.

The provider transport's local `traffic_control` contract is also part of the
frozen screening implementation binding. A shared upstream key pool treats a
429 as a channel/profile cooldown rather than permission to sweep every key;
the standard `Retry-After` header is honored only within the configured
cooldown cap, and a missing or malformed header uses the fixed fallback. Gate
waiting consumes the same per-request 90-second ceiling. A change to transport
rate-limit, key-pool, streaming, or retry implementation invalidates an
existing plan and requires a fresh freeze; previously collected scores are not
merged into that new campaign.

The generated private registry exposes two deliberately separate projections:

- `models` contains each eligible physical profile because the provider and
  model alias, API format, and environment-variable references are needed to
  send a request;
- `prefusion_screening.available_model_list` contains one row per canonical
  logical model, its research rank, prior capability axes, and the hashes of
  all eligible channel replicas. Replica rows improve availability and
  failover; they are not independent votes or additional cognitive models.
  `available_rank` is the contiguous rank after slow/unavailable models are
  removed, while `research_prior_rank` preserves the original complete
  research ordering for audit.
- `prefusion_screening.eligible_profile_bindings` binds every serving profile
  to a live probe mode, strict-streaming, stream-request/stream-observed,
  protocol/frame-count evidence, non-empty output hash, observed latency, and
  eligibility decision. Fresh multi-sample bindings additionally record the
  required count, completed/success/failure counts, all-samples decision, and
  a hash-only receipt digest. `load_registry` rejects a screening-generated
  registry when this binding is missing, incomplete, tampered, or marked
  blocked.
- A logical row records `fastest_observed_latency_ms` and
  `slowest_observed_latency_ms` across its eligible physical replicas. These
  names describe the available probe samples only. They are not p50/p95
  statistics unless a separate multi-sample calibration artifact explicitly
  supplies those percentiles.

The research capability axes are copied to `screening_capability_*` fields as
an operational prior only. They never overwrite calibrated `capabilities`,
never bypass the streaming gate, and never support a benchmark superiority
claim. Fresh research output must contain at least one nonzero capability axis
when `overall > 0`; a broad prior with `overall >= 0.70` must contain at least
three nonzero axes. A lower-confidence/narrow prior may cover one axis, but
the role gate keeps it away from `judge` and `synthesizer`. The same coverage
rule is rechecked from both persisted research projections at registry load,
so an old or edited all-zero-axis broad artifact cannot become routable. A
profile whose observed response exceeds 90 seconds is absent from both the
physical serving registry and the logical available model list.

The report's top-level `available_model_list` and `fusion_handoff` are the
explicit handoff projection. Fusion consumes the private `fusion_registry`
only when `fusion_handoff.status=ready`; a blocked or partially generated
registry cannot be activated.

## Available-Model Generation Entry Point

For an operator-facing run, use the dedicated command:

```bash
PYTHONPATH=src python -m axio_fusion_api.cli \
  --provider-config-file config/provider_configs.example.json \
  generate-available-models --live \
  --source-manifest <public-source-manifest> \
  --research-agent-config <research-agent-config> \
  --output <generation-artifact.json> \
  --registry-output <runtime-registry.json> \
  --handoff-output <available-model-handoff.json>
```

The endpoint and credentials are resolved only from configured environment
variables. A ready run publishes the private registry atomically; a blocked
run may be saved as a diagnostic artifact but never replaces the existing
runtime registry. When `--handoff-output` is supplied, the same ready
generation is atomically written as the private audit/handoff artifact; it
cannot be used without the corresponding registry publication. The returned
artifact has a fixed
`axio_fusion_api.available_model_generation.v1` schema. It is a private
control-plane file because its ready handoff contains non-secret provider/model
aliases; use the redacted report path for public diagnostics. Programmatic
callers can use:

```python
from axio_fusion_api import (
    generate_available_model_set,
    publish_available_model_set,
)

artifact = generate_available_model_set(live=True)
if artifact["status"] != "ready":
    raise RuntimeError(artifact["blockers"])
publish_available_model_set(
    artifact,
    registry_path="private/runtime-registry.json",
)
```

`research_ranking` is the complete capability-research prior. The
`operational_ranking` and `available_model_list` are the post-probe serving
projections. The latter contains one row per canonical model; duplicate
provider replicas remain inside the private registry solely for balancing and
same-model failover.

The research prompt uses the fixed contract
`axio_fusion_api.prefusion_research_prompt.capability_evidence_mapping.v2`.
For each candidate it requires the remote Agent to extract facts before
scoring axes, distinguish an unreported capability from an explicitly
unsupported capability, and map equivalent public terms such as function
calling to structured output and `CritPt`/verification evidence to critique.
Named benchmark results may establish that a source discusses a task family,
but their numeric scores cannot be copied into the ranking. This prevents a
hard-to-parse source page from silently turning a documented capability into a
zero while keeping the ranking separate from the independent benchmark
evaluator.

## Configuration-Driven Discovery

The preferred dynamic path is a non-secret provider manifest selected with
`--provider-config-file`. The manifest contains protocol names, environment
variable names, and optional static model overrides; endpoint and credential
values are injected into the process only at execution time. For every
provider with discovery enabled, `/models` is the source of truth for the
candidate inventory. The `provider_discovery` receipt records status, counts,
profile hashes, and safe error metadata, but never raw model ids, URLs,
response bodies, or credentials.

Discovery is a prerequisite, not a best-effort hint:

- A failed provider with no explicit static models adds a blocking reason.
- An empty successful inventory with no explicit static models adds a blocking
  reason.
- A partial provider inventory is never passed to the research Agent or the
  streaming probe.
- A requested `--max-models` smaller than the complete logical inventory is
  rejected for serving; the full pool must be ranked before latency filtering.
- Profiles returned by discovery are process-local. Safe report generation
  removes them and hashes diagnostic model-id lists before persistence.

This boundary makes the module reusable across arbitrary channel portfolios:
the provider manifest, the configured remote research Agent, and the same
strict stream probe are the only deployment-specific inputs. No local model
weights are loaded.

## Handoff Validation

The handoff has an explicit validation boundary in addition to the individual
research and probe validators:

```python
from axio_fusion_api import (
    validate_prefusion_handoff,
    validate_prefusion_registry_handoff,
)

assert validate_prefusion_handoff(screening_report)["valid"] is True
assert validate_prefusion_registry_handoff(
    screening_report["fusion_registry"]
)["valid"] is True
```

The runtime must not choose a model projection from the report itself. Use the
single Fusion handoff boundary to extract the latency-filtered logical list;
it validates the complete report first and returns an empty list with
`blocked` status when the contract fails:

```python
from axio_fusion_api import build_prefusion_fusion_handoff

handoff = build_prefusion_fusion_handoff(screening_report)
if handoff["status"] != "ready":
    raise RuntimeError(handoff["validation"]["reason_codes"])
research_ranking = handoff["research_ranking"]
operational_ranking = handoff["operational_ranking"]
available_model_list = handoff["available_model_list"]
```

The handoff carries two distinct, hash-bound ranking projections.  The
`research_ranking` is the complete candidate ordering produced by the remote
research workflow and remains an operational prior.  The
`operational_ranking` joins that prior with strict live-stream reliability and
latency evidence and contains only models admitted to serving.  Their content
digests are exposed as `research_ranking_content_sha256` and
`operational_ranking_content_sha256`; neither projection is benchmark
evidence.  Fusion should consume these fields from the handoff rather than
reaching back into the larger screening report.

`available_model_list` has one row per canonical model. Multiple provider
replicas remain only in the private physical registry for load balancing and
failover. A file-backed operator must explicitly pass
`include_private_registry=True`. A safe receipt uses
`redact_provider_identifiers=True` and keeps only the source digest and hashes;
the handoff remains a serving control-plane prior, not benchmark evidence.

The registry validator binds every physical `profile_id` hash to exactly one
live probe binding, requires strict SSE/NDJSON evidence and a measured latency
at or below 90 seconds, verifies the logical canonical-replica projection and
contiguous `available_rank`, checks the complete research-candidate rank and
catalog hashes, and revalidates capability-axis coverage in both research
projections. The report validator additionally binds the report-level
available list, catalog, counts, and registry digest to that same registry.
Any missing, duplicated, reordered, edited, or all-zero-axis broad projection
fails closed before Fusion receives a profile. These validators provide
serving-integrity evidence; they do not convert the research prior into
benchmark evidence or role calibration.

The research ranking is an operational prior. It is never benchmark evidence,
never a baseline score, and cannot bypass the live probe or the latency gate.
The report and registry do not persist API keys, base URLs, source bodies,
research prompts, research output, or provider response bodies.

## Production Stream Boundary

The low-level `HTTPProviderClient` retains an explicit
`require_streaming=False` compatibility mode for isolated fixtures and
operator diagnostics. The production boundaries do not use that default:
dynamic enrollment normalizes an injected HTTP client to strict mode, and an
production server constructs/injects a strict client. Therefore the same
framed SSE/NDJSON contract applies to the pre-Fusion text
probe, tool-capability probe, and subsequent Fusion stages. A non-streaming
JSON response is a transport failure and cannot be promoted into the serving
pool. The exception is the explicitly named `diagnostic_only` path, which is
never a production admission or registry handoff. Direct construction of
`FusionEngine` remains an operator/test extension point; production callers
must use `create_http_server`, `create_runtime_http_server(..., enroll=True)`,
or `enroll_runtime_channels` so this transport boundary is applied.

## Role-Aware Panel Handoff

The runtime consumes the screening role contract as a control-plane constraint,
not as a benchmark claim. If Pro initially has only one general primary-capable
profile but the handoff contains a different canonical profile explicitly
allowed only for `domain_specialist`, the router may add that profile as a
second evidence seat. The role remains `domain_specialist`; it is never
renamed to `independent_solver`, and a same-canonical replica cannot become a
second vote. Judge and Synthesizer may reuse a role-qualified general profile
only as an explicitly recorded capacity fallback. The panel search still has
to pass the request cost/deadline checks and the hard 3x latency guard. Legacy
profiles without an explicit screening role contract retain the prior neutral
portfolio behavior.

Candidate evidence isolation is a transport property, not only a prompt rule:
when a source manifest binds a model card to one canonical candidate, that
candidate is placed in a singleton research request. A different candidate
cannot receive the model-card excerpt or cite its source slot. Shared public
leaderboards remain eligible for bounded multi-candidate batches. This keeps
the ranking complete while preventing cross-candidate evidence contamination.

## Current Live Handoff

The current r3 handoff was completed on 2026-07-25 after rediscovering the
configured channels and reranking the complete inventory. `/models` discovery
produced 136 physical profiles and 136 logical candidates, all with a
validated research-prior record. Three strict streaming samples admitted 29
profiles, 8 were rejected by the measured 90-second latency ceiling, and 99
were rejected by stream/protocol stability. Forty-seven profiles observed at
least one real SSE/NDJSON stream; the 29 admitted profiles each completed all
three samples, for 87 successful samples. The slowest admitted sample was
86,712.071 ms. Ordinary JSON fallback was never admitted.

The serving projection contains 29 physical profiles and 29 logical models.
The required `primary_solver`, `judge`, and `synthesizer` role capacities are
all present, and the report handoff validator, registry handoff validator, and
`load_registry(..., require_prefusion=True)` all pass. The public health
projection carries a `single_provider_model_pool` warning for this cohort;
channel availability must be re-screened before a formal comparison campaign.
The ranking is still an operational prior, not benchmark evidence or a
superiority claim.

The active r3 artifacts are:

```text
private/prefusion_live_20260725_r3/prefusion_screening.safe.json
private/prefusion_live_20260725_r3/fusion-runtime-registry.private.json
```

The r3 registry uses the unambiguous latency fields and binds each admitted
profile to its three-sample receipt. Native tool calibration was not part of
this handoff, so tool capability remains unproven until a separate bounded
probe is run. Earlier v2, v5, v6, v9, and operational-v1 artifacts remain
historical diagnostics and cannot replace r3 without a fresh screening gate.

## Historical Live Handoff: v2

The v2 live run was completed on 2026-07-22 with the configured NVIDIA
Chat Completions and TokenAPIs Responses channels. Complete `/models`
discovery produced 139 physical profiles. The full logical inventory was split
into 35 batches of at most 4 candidates; all 35 research batches passed strict
validation, including the capability-axis coverage gate, and were merged with
the deterministic `research_quality_score` policy.

The subsequent probe covered all 139 physical profiles. It admitted 32
profiles, excluded 23 for the hard 90-second latency ceiling, recorded 80
transport failures, and recorded 4 semantic/unframed responses. Every
admitted profile has strict SSE evidence, a non-empty output digest, and a
measured latency at or below 90 seconds; no ordinary JSON fallback was
promoted. The resulting serving projection has 32 logical available models
and 32 physical profiles. The fastest single observed sample was 1,125.057 ms
and the slowest single observed sample was 33,723.964 ms. These values were
not p50 estimates.

Those v2 artifacts are historical diagnostics only:

```text
private/prefusion_full_live_20260722.capability_axes.v2.report.json
private/prefusion_full_live_20260722.capability_axes.v2.registry.private.json
private/prefusion_full_live_20260722.capability_axes.v2.safe.json
```

The v6 handoff supersedes these artifacts. They remain useful for audit only
and must not be activated merely because they passed an older contract. This
is serving-admission evidence, not a benchmark evaluation and not a
superiority claim.

## Historical Live Handoff: operational-v1

The previous operational-v1 run is retained as historical diagnostics and is
no longer activatable under the current capability-axis contract:

```text
private/prefusion_full_live_20260722.operational.v1.registry.private.json
```

The accompanying historical safe screening receipt is:

```text
private/prefusion_full_live_20260722.operational.v1.safe.json
```

The earlier report and registry pass the previous handoff contract but fail the
current validator when a broad research row has insufficient nonzero
capability axes. They must not be activated. The historical run is
serving-admission diagnostic evidence, not a benchmark evaluation and not a
superiority claim.

The older `private/prefusion_full_live_20260722.batched.*` files predate the
operational-ranking binding and remain historical diagnostics only. They must
not be activated without passing the current handoff validators.

## Operator Flow

First enroll or load a non-secret provider registry. The provider credentials
are supplied only through the environment variables named by that registry.
Then run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m axio_fusion_api.cli \
  --provider-config-file config/current_channels.example.json \
  pre-fusion-screen \
  --focus-manifest config/nvidia_focus_models.json \
  --source-manifest config/public_model_sources.example.json \
  --research-agent-config config/research_agent.example.json \
  --research-batch-size 4 \
  --research-max-workers 4 \
  --live \
  --min-available-models 3 \
  --output <prefusion-screening.safe.json> \
  --registry-output <fusion-runtime-registry.private.json>
```

`--registry-output` is a private operational artifact because the provider and
model aliases are needed on the wire. It still contains only environment
variable references, never credential values. The default network policy is
`auto` with the local system proxy configured as `http://127.0.0.1:10808`; use
the runtime network environment variables to select `on` or `off`.

When `--provider-config-file` is used, do not also pass `--registry` for the
same run. The file-backed manifest activates automatic complete `/models`
discovery. A blocked run still emits a safe diagnostic report but never
writes or replaces `--registry-output`; an existing serving registry is left
untouched.

The example source manifest is intentionally only a template. Operators must
review source availability and snapshot dates before a live run. Failed or
empty source collection fails closed when no valid research output is supplied.

For a long-running dynamic gateway, the same gate is part of startup admission.
Put the non-secret paths in the manifest's `prefusion` object (the supplied
`config/current_channels.example.json` shows the shape), or pass the equivalent
`--prefusion-*` options to `serve --enroll`. The service performs `/models`
discovery first, then runs this workflow against the discovered profiles. It
does not activate the in-memory Fusion engine from discovery or a plain health
probe alone. A missing source manifest, missing research-agent credentials, an
incomplete ranking, an ordinary JSON response advertised as streaming, or a
latency measurement over 90 seconds leaves startup blocked.

The runtime enrollment receipt contains only counts and hashes for the
pre-Fusion handoff. The raw `available_model_list` remains in the private
operator registry/report, while Fusion receives the physical profile objects
bound by their exact profile hashes. The logical list is therefore the source
of ranking and role metadata; physical rows are only transport replicas for
load balancing and failover.

For dynamic `serve --enroll`, the same settings can be placed in the manifest
`prefusion` object as `candidate_batch_size`, `research_max_workers`, and
`merge_strategy`, or supplied with `--prefusion-research-batch-size` and
`--prefusion-research-max-workers`. The merge strategy is fixed and cannot be
replaced by a caller-controlled ranking rule.
