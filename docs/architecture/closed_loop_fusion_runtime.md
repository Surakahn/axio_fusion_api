# Closed-Loop Fusion Runtime

## Purpose

Axio Fusion API is a remote-model orchestration system. It does not train,
download, load, or serve model weights. Its only model execution mechanism is
an explicitly configured remote HTTP(S) provider API using Chat Completions,
Responses, Anthropic Messages, or Gemini-compatible transport.

The product accepts a changing portfolio of provider model APIs and compiles a
versioned Fusion policy that exposes the stable public products `axio-fast`,
`axio-terra`, and `axio-pro`. A new provider is not assumed to improve a tier
just because it is reachable. It must pass protocol, capability, diversity,
cost, latency, and shadow-policy gates before it participates in a promoted
Fusion configuration.

## Runtime Planes

1. Provider plane: protocol adapters, credentials, health, model inventory,
   canonical identity declarations, and private channel attestations.
2. Policy plane: versioned routing/context/workflow policy candidates,
   approval, activation, rollback, and registry binding.
3. Inference plane: request analysis, structured context assembly, direct
   cascade, complementary expert panel, Judge, targeted escalation,
   Synthesizer, tool-call arbitration, budgets, deadlines, and fallbacks.
4. Learning plane: prompt-free feedback and trace aggregation, shadow-policy
   proposals, decision replay, holdout checks, and human-approved promotion.
5. Evaluation plane: independent, frozen 21-suite benchmark execution and
   claim audit. It is never an online router-training source.

The planes communicate through schema-versioned, hash-safe artifacts. The
inference plane may keep request-local prompt and candidate content in memory,
but it must not persist them in the other planes.

## Provider Onboarding Lifecycle

Each provider portfolio revision follows this state machine:

`configured -> protocol_validated -> live_probed -> capability_calibrated ->
shadow_candidate -> approved -> active -> retired`

`configured` records a private provider registry with an explicit API format,
remote base URL environment variable, credential environment variable, and
model aliases. `protocol_validated` proves request/response adaptation without
claiming model quality. `live_probed` establishes bounded availability and
latency evidence. `capability_calibrated` records non-target operational
evidence, complementary-error hypotheses, costs, context limits, and tool
support. `shadow_candidate` produces a routing/context/workflow policy that is
evaluated without changing production behavior. Only an approved candidate may
become active, and every activation is bound to the exact registry hash.

When the registry changes, the active policy is not silently transferred to
unknown models. A compatible policy may continue in a conservative direct
route mode, but new panel roles, prompt packs, and tier behavior require a new
onboarding and policy-promotion record.

The executable onboarding control plane makes this boundary concrete. A newly
configured remote profile remains `enabled: false` in the private registry;
normal serving loads omit it, and the router independently filters disabled
profiles before ranking, direct fallback, or panel construction. Onboarding is
the only path allowed to inspect such a profile: it consumes safe live-probe
and calibration evidence, emits a hash-only `shadow_candidate`, records human
approval, and writes a *new* explicitly named private registry when activated.
No onboarding artifact can select a hidden provider for a role, mutate the
source registry in place, or make an unapproved profile eligible for Terra or
Pro Fusion.

### Shared Control-Plane Deadline

Pre-Fusion admission uses one monotonic wall-clock deadline for discovery,
public-source collection, Research Agent batches, model-scoped reasoning
controls, and multi-sample streaming admission. The deadline is propagated
through three boundaries: the stage call, each provider request, and the
killable process used for live HTTP control-plane work. A provider request
receives only the remaining budget after a small process-reporting reserve;
profile-level sample and role loops recompute that remainder before every
request. Once the deadline is exhausted, the workflow emits a hash-safe
indeterminate/failed receipt without starting another network call.

This prevents a cohort with many declared reasoning levels, stability samples,
or role probes from multiplying the nominal 90-second provider ceiling into an
unbounded refresh. It also prevents partially probed candidates from entering
the active registry: budget exhaustion is a blocking publication condition,
and the last known-good registry remains untouched.

## Tier Contracts

- `axio-fast`: bounded direct cascade with optional light verification only
  when risk, uncertainty, quality target, cost, and the hard latency guard
  permit it.
- `axio-terra`: selective complementary panel whose size and role graph are
  justified by expected utility rather than a fixed number of calls.
- `axio-pro`: expert panel, structured Judge, targeted verification, and
  final Synthesizer for complex, high-risk, or decomposable tasks.

All tiers use the same request/context contract. Their difference is a
budgeted workflow choice, not a different local model or a hidden provider
alias.

## Latency-Constrained Panel Admission

Panel selection begins with capability, reliability, provider diversity, and
error-correlation scores, but score-first selection is not allowed to violate
the runtime latency contract. The route planner first assigns the actual direct
profile that would answer the request alone. If the planned Expert/Judge/
Synthesizer schedule is already within the operational headroom, it remains
unchanged. If it exceeds the hard 3x p50 guard, a bounded candidate-panel
search holds that direct profile fixed and evaluates the exact initial role
scheduler against a small pool of live-probed profiles.

The repair search preserves canonical-model uniqueness and never treats a
channel replica as an independent expert. For `axio-pro`, the minimum repair
shape is Primary + Independent + Critic; optional domain-specialist work may be
trimmed, but a missing Critic is not silently converted into a direct answer.
Only panels that meet the hard 3x guard and a bounded quality floor are
eligible. Provider diversity is a soft objective in this latency contingency:
when the current portfolio has fast independent models in one channel but
cross-channel profiles are too slow, the receipt exposes that relaxation and
the final claim/evaluation plane still requires independent cross-provider
evidence. If no eligible panel exists, Fusion is blocked and the direct route
is used.

This admission search is operational policy, not benchmark optimization. It
uses only live transport latency, registry capability priors, canonical
identity, and request-local budgets; benchmark prompts, labels, scorecards, and
target-suite outcomes cannot change it automatically.

## Harness Principles Applied

The design borrows the applicable parts of the harness engineering pattern
described in Lilian Weng's 2026-07-04 article:

- Workflow automation becomes an explicit bounded task graph, not an
  unbounded self-refinement loop.
- Persistent memory becomes versioned configuration, safe traces, feedback,
  policy candidates, approvals, and evaluation artifacts rather than a raw
  transcript appended to every prompt.
- Subagents become role-scoped remote API calls with independent budgets,
  cancellation, and merge receipts.
- Context engineering becomes a structured context playbook assembled from
  request analysis, role requirements, tool constraints, evidence standards,
  and compression policy.
- Harness optimization becomes controlled policy evolution. It optimizes the
  machinery for combining remote APIs, not model weights and not benchmark
  answers.

## Hermes MoA 2.0 Process Alignment

Axio adopts the process-level parts of Hermes MoA 2.0, rather than treating
Mixture of Agents as an opaque model alias:

- The reference wave is a bounded parallel fan-out of short, tool-free
  advisory turns. Each turn receives a deterministic user/assistant-only
  projection of conversation history; system instructions, native tool
  schemas, and executable tool-call/result objects are removed. Prior tool
  actions and at most 4,000 characters of each result are rendered as inert
  head/tail text, preserving evidence for the next advisory wave without
  granting tool authority or creating orphan native tool messages. Results are
  restored to configured route-role order after parallel completion, so
  transport timing cannot perturb Judge input order or deterministic tie
  behavior.
- The provider Judge is a required stage between references and the one
  acting Synthesizer. If the Judge reports a bounded coverage, contradiction,
  evidence, or quality gap, Axio may issue at most one targeted feedback
  reference call and then re-Judge. This is a process feedback wave, not an
  unbounded self-refinement loop. A route cannot advertise Hermes aggregation
  when either mandatory stage is absent, and only the Synthesizer is allowed
  to own the user-visible final answer.
- Reference guidance is injected at the tail of the aggregator's current
  provider user turn. The stable conversation prefix remains in place,
  preserving provider prompt-cache opportunities. When the synthesizer has a
  separately proven native-tool capability, it receives the caller's normal
  tool schema and its tool turn is returned as the acting public turn;
  references and Judge never receive that schema.
- A failed reference is recorded as partial advisory context and does not
  abort the turn. The route still obeys the normal quorum, deadline, cost,
  circuit, and hard latency gates; if no usable reference survives, the
  aggregator is skipped rather than being reported as completed. Before a
  reference seat is declared failed, Axio may make a bounded availability retry
  through another provider replica of the same canonical model. The retry keeps
  the original advisor role and tool-free projection, consumes its own call,
  cost, and deadline budget, and still counts as one cognitive reference rather
  than independent support.
- All projected tool evidence and all reference/candidate packets are explicitly
  untrusted data with zero instruction authority. Candidate-authored role
  changes, policy text, fake delimiters, context-exfiltration requests, and tool
  directives cannot override the caller system message, original task, Judge
  contract, or acting Synthesizer contract. The provider Judge receives this
  boundary in both system and task prompts; only its normalized closed-vocabulary
  control record reaches synthesis. The acting Synthesizer receives the same
  boundary and decides tool calls only from the authoritative original request.
  The hash-safe Hermes plan exposes this as `context_authority_policy` so the
  guarantee is auditable rather than implicit prompt prose.
- High agreement cannot take the generic early-exit path when Hermes is
  enabled. The acting Synthesizer must be called and its output must be accepted
  for the process contract to complete. An empty Synthesizer output may degrade
  to the best surviving reference answer. A Judge-required feedback reference
  that cannot be scheduled, or one that fails, may still permit a bounded
  answer, but these outcomes remain explicitly process-incomplete unless a
  successful feedback output, the required re-Judge, and acting finalization
  all occurred. `feedback_reference_required`,
  `feedback_reference_execution_present`, and
  `feedback_reference_completed` are separate receipt facts; process
  completion never infers Judge intent from candidate existence.
- On the next public tool iteration, the same process is rebuilt from the
  updated conversation. The acting model therefore keeps the normal tool
  loop and full untrimmed transcript, while the next reference wave receives
  only the deterministic bounded text projection.
- Recursive MoA is blocked at request metadata and route planning boundaries.
  Axio's Judge, diversity-aware candidate selection, targeted escalation, and
  safety/evidence gates remain outside the reference fan-out, so Hermes does
  not replace the rest of the Fusion policy.

### Cognitive budgets and fanout cadence

Each Hermes seat has a protocol-neutral cognitive budget contract recorded in
the hash-safe plan. Advisor seats use bounded `low`/`medium`/`high` contracts;
the Critic and targeted feedback verifier may receive a higher contract than a
normal advisor; and Pro's Judge and acting Synthesizer use the highest available
contract in the tier policy. These labels shape prompt instructions and local
admission/accounting only. Axio does not forward a provider-private
`reasoning_effort` or equivalent wire field unless that exact capability has
been independently attested for the selected provider profile. This prevents a
mixed Chat/Responses/Anthropic/Gemini portfolio from failing on an unsupported
parameter while preserving the intended role budget.

The same protocol-neutral rule applies to decoding controls. A temperature is
forwarded only when the caller or frozen evaluation protocol explicitly sets
one; otherwise every upstream adapter omits it and uses the provider default.
Explicit `0.0` remains meaningful and is never dropped by truthiness checks.
This is important for reasoning-capable Responses gateways that reject a
temperature field even though ordinary completion models accept it.

Reference fanout is rebuilt on every `per_state_iteration`. A new public tool
result, conversation turn, or route-state change therefore creates a fresh
bounded reference wave. Cross-request `user_turn` reuse is disabled unless the
caller explicitly supplies a conversation scope that has been admitted for that
policy; an implicit global advisor cache is never used. Reference and feedback
output caps are role-local, and the Judge cap is tiered (Terra 1,536 tokens,
Pro 2,048 tokens) and additionally bounded by the caller's smaller limit. The
acting Synthesizer is not incorrectly constrained by the advisor cap; it uses
the caller's output limit or the selected provider default.

These invariants are covered by `tests/test_hermes_moa.py` and the four-format
provider control-packet regressions. The receipt records process state and
hashes only; reference text, provider output, prompts, credentials, and raw
tool arguments are never persisted.

This alignment was checked against NousResearch `hermes-agent` commit
`e89bc58a5ba80ec6be19b43beca37cbb03091afd`, especially
`website/docs/user-guide/features/mixture-of-agents.md`, `agent/moa_loop.py`,
and its cache, cost-slot, recursion, streaming, and trace tests. Axio preserves
the Hermes acting-aggregator and prompt-tail principles, then adds a mandatory
Judge, one bounded Judge-triggered feedback wave, quality-diversity panel
selection, provider failover, and the 3x latency admission/claim gates.

### Process-aware response caching

Caching is downstream of the process contract, never an alternate path around
it. The cache admission gate accepts only successful direct text finals or
fully finalized Fusion text finals. For Hermes routes, the runtime and Hermes
receipts must independently prove accepted Judge output, accepted acting
Synthesizer output, final-answer ownership, and a completed process contract;
required feedback must also have completed its feedback output and re-Judge.
Any degraded runtime, incomplete panel, missing mandatory stage, tool turn, or
failed/unscheduled feedback path remains uncached.

### Provider circuit recovery

Provider failures are tracked per physical profile, not per canonical model, so
one broken channel does not poison another replica of the same model. Reaching
the configured consecutive-failure threshold removes that profile from route
construction and same-model failover. The process-local circuit then has a
bounded cooldown (30 seconds by default, configurable through
`AXIO_FUSION_CIRCUIT_BREAKER_COOLDOWN_SECONDS` or the `FusionEngine` constructor)
after which the profile is admitted for recovery traffic again. A successful
turn clears the consecutive-failure streak; another failure starts a fresh
cooldown. A zero cooldown keeps the explicit manual-recovery behavior. Circuit
receipts expose only threshold, cooldown, profile hashes, and counts, so this
recovery loop does not weaken the secret/provider-output boundary.

Each cache entry carries a hash-safe origin-completion receipt and is bound to
the Direct/Fusion/Hermes route-contract shape. Replay validates the answer hash,
receipt digest, and current route contract before returning text. Its execution
trace records zero current provider calls and a distinct replay receipt, while
safe traces and shadow-learning features recover process attributes only from
the admitted origin receipt. This preserves outcome attribution without
pretending that Judge, feedback, or acting synthesis executed again.

## Policy Promotion Contract

A policy candidate may change only allowlisted routing and context controls,
such as tier-specific quality thresholds, bounded panel size, independence
requirements, escalation eligibility, and compression preference. It may not
name a hidden provider/model in public policy, bypass privacy/tenant limits,
relax hard cost or latency ceilings, or use target-suite data.

Promotion requires all of the following:

1. A registry-bound candidate with a deterministic policy digest.
2. Sufficient operational feedback and trace evidence for every affected
   bucket.
3. A contamination audit proving the candidate did not learn from the target
   benchmark package.
4. A shadow decision-replay result and a separate approval record.
5. A rollback target and an activation record that can be inspected without
   disclosing prompts, provider outputs, endpoints, or secrets.

An active policy remains an engineering configuration. It does not authorize a
capability-superiority claim. Those claims require a new frozen baseline,
official or audited harness receipts, paired 21-suite runs, corrected
statistics, effect-size gates, and p50/p95 latency gates.

The decision replay is deliberately limited to prompt-free historical routing
receipts. It can show candidate rule coverage, bounded-control deltas, and the
historical hard-budget context of affected requests. It never runs a candidate
model call, synthesizes a counterfactual answer, or attributes historical
feedback, latency, cost, or quality to the candidate policy. Promotion still
requires separately executed paired candidate outputs and independent outcome
evidence.

## Non-Goals

- No local model deployment, local weight inference, fine-tuning, or model
  weight mutation.
- A network-free execution-boundary audit is part of system-development
  readiness. It rejects local-inference imports, declared local-model runtime
  dependencies, and model-weight artifacts in the standalone Fusion package,
  while verifying HTTP(S)-only provider transport and all four upstream input
  adapters.
- No automatic benchmark-driven policy mutation.
- No automatic production promotion from a single feedback bucket.
- No assumption that more model calls are better than a direct route.
