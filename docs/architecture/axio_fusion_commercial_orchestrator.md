# Axio Fusion Commercial Orchestrator

## Product Boundary

Axio Fusion API is a standalone model-fusion service.  ASciFS can consume it
later through model APIs, but the Fusion service itself must not depend on the
ASciFS paper database, graph database, Studio UI, or research workflow outputs.

The public model surface is exactly three lowercase Axio models:

- `axio-fast`
- `axio-terra`
- `axio-pro`

These are treated as three distinct model products with different internal
fusion algorithms, not as one model with a different quality flag.

## Public Protocols

The service exposes one Axio model family through four client-compatible
formats:

- OpenAI Chat Completions: `POST /v1/chat/completions`
- OpenAI Responses: `POST /v1/responses`
- Anthropic Messages: `POST /v1/messages`
- Gemini generateContent: `POST /v1beta/models/{model}:generateContent`

All four formats normalize into the same prompt-free route-plan and
orchestration metadata contracts.  The protocol layer is a facade; provider
model names and provider failures remain internal metadata.

## Three Model Algorithms

`axio-fast` uses `fast_direct_cascade`.

Its target is third-best single-model task capability at lower cost and near
single-model latency.  It starts with one fast, low-cost branch and uses fallback
only for provider failure or missing capability.

`axio-terra` uses `terra_cost_guarded_fusion`.

Its target is second-best single-model task capability at lower cost and near
single-model latency.  It uses selective fusion only when request complexity,
risk, or uncertainty makes the expected gain worth the added cost.  It prefers
parallel fan-out and lightweight judging instead of serial long chains.

`axio-pro` uses `pro_panel_judge_escalation`.

Its target is best single-model task capability at lower cost when possible, or
better reliability at equal cost when the task is hard or high-risk.  It uses a
diverse expert panel, structured judge, targeted escalation for contested
subtasks, and final synthesis from the judge record.

## Cost, Quality, And Latency Contract

Each model carries a target contract:

- `axio-fast`: match the third-best usable single model, cost below that model.
- `axio-terra`: match the second-best usable single model, cost below that model.
- `axio-pro`: match or exceed the best usable single model, cost below that
  model when possible.

Latency must be close to a single model request, not the sum of branch
latencies.  The implementation uses:

- parallel expert fan-out;
- early exit when confidence and coverage are sufficient;
- rank-first candidate compression;
- targeted subtask escalation only;
- provider timeout and circuit breaker controls;
- request-hash cache hooks for reusable intermediate results.

These are target contracts until benchmark scorecards prove them.  Route plans
and static registry priors must not be marketed as evidence that Axio beats a
baseline.  Superiority claims require measured scorecards with per-case results,
co-failure checks, and cost/latency accounting.

## Orchestrator Metadata

Every route plan includes `fusion_orchestration` with:

- request analysis;
- model algorithm identity;
- budget policy;
- fusion activation decision;
- expert panel roles;
- task DAG;
- judge plan;
- targeted escalation plan;
- synthesis plan;
- runtime guards;
- learning trace contract.

This structure stores only metadata, hashes, profile IDs, and control flags.  It
must not persist raw user prompts, raw source text, provider secrets, benchmark
questions, or benchmark labels.
