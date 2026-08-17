# Axio Fusion API Plan

## Composite successor intake（2026-08-17）

当前 r2 frozen screening 已终态但 transport admission blocked（4/10 units
completed、6/10 transport failure，只有 1/5 canonical groups 满足严格门禁），因此
不得生成 ranking、provider freeze 或 target campaign。完整 intake 记录见
`docs/operations/composite_baseline_intake_audit_2026-08-17.md`。

当前唯一允许的 successor 路线是对同一 probe-bound registry 做独立
`operational-admission`，然后在满足至少 3 个 formal baseline eligible canonical
groups 后创建新的 immutable screening plan；r2 plan、completed subset 和历史
ranking/freeze 均不可修改或复用。

该路线已完成 admission 与 preflight：10 profiles 中 7 个 production admitted、4 个
formal baseline eligible（跨 2 providers），r3 plan digest 为
`a8400e203ca37a4eb5ddd8a0d3758dd16c4e992ffcd1ad8dc05449eb1b17e706`，包含 4 个
canonical groups、8 个 serial units、预计 856 calls。r3 live screening 已通过
zero-network preflight 启动，supervisor/watcher 绑定同一 plan；screening terminal
前不生成 ranking、freeze 或 target 请求。

### r3 Harness 调研里程碑（2026-08-17）

已确认六个真实 Harness checkout 与 raw dataset snapshot 均可本地验证，并用同一 r3
control-plane 重新生成 pin：6 suites、6 ready、0 blocked，BFCL 独立绑定 V3 evaluator
且版本 marker 通过。该结果只证明 Harness pin readiness；screening 尚未终态，transport
admission/ranking/provider freeze/official import 均未 ready，convergence audit 仍为
`status=running`、`next_gate=screening`，target calls 必须保持关闭。调研与评估契约见
`docs/scout/composite_r3_harness_framing_2026-08-17.md`。

离线数据控制面随后完成一次 materialization：六个官方 suite 的 stable case hash 均已
解析，显式 MMLU-Pro replacement 后 source manifest validation 为 17/21 ready；官方
import audit 已确认 case-hash binding 6/6，但 imported runs 为 0，仍等待 provider
baseline freeze 后的正式 Harness 执行。GPQA 原始槽位与三个数据质量/来源 blocker 保持
fail-closed，不用历史分数或 completed subset 填充。

## Composite cohort r1 与 Harness 收敛设计（2026-08-16）

本轮在已有 live probe 证据上建立新的 composite cohort，不复用旧
r5/transport5 的 ranking 或 freeze。两个严格 streaming probe artifact 已通过
离线多文件 registry 合并，得到 10 个去重 physical profiles、3 个 provider 和
3 个 fast candidates；新的 non-target plan 已 ready：

- registry：`private/runs/2026-08-16-composite-cohort-r1/registry.composite.from-probe.private.json`
- plan：`private/runs/2026-08-16-composite-cohort-r1/baseline_screening_plan.composite.private.json`
- plan digest：`b53c8196c688220a99e2b3b6091cb35333dcfe5ecc13795d842f380a9c2e3e99`
- 10 个 canonical groups、20 个 serial source-units、预计 2140 次 provider calls

首个未加载私有环境变量的启动在网络调用前按设计 blocked，并单独保留；retry1
使用相同冻结 plan、`max_workers=1` 和 fail-fast transport gate，在独立 private
root 中运行。screening 终态前不得生成 ranking、freeze 或调用 target suite。

Harness 收敛采用 pin manifest → execution plan → zero-network preflight/import →
cohort lineage binding → cohort-bound live campaign → statistical/latency/contamination/API-parity/final
audit 的单向链路。已有旧 Harness template 只能作为结构参考；composite freeze
完成后必须重新绑定 registry、provider freeze digest、source/case hash 和每个
official/audited runner commit。具体 contract 与恢复规则记录在
`docs/architecture/axio_fusion_benchmark_harness_convergence_2026-08-16.md`。

新增的 `scripts/build_composite_harness_binding.py` 是 target 前的离线 lineage gate：
它将 registry、screening、transport、ranking、provider freeze、Harness pin、execution、
acquisition 和 official import audit 绑定为 hash-only `composite_harness_cohort_binding.v1`。
缺少或漂移时 `audit_composite_convergence.py` 不开放 target calls；当前 r1 尚未满足
这些前置条件，绑定器只能输出 blocked receipt。

本阶段已修复多 probe 文件合并时重复 profile 被按 raw row 重复计入 API format
binding 的控制面缺陷。审计现在按唯一 profile hash 统计 available API format，并
对同一 profile 出现多个 API format fail-closed；现有 composite probe evidence audit
已重新生成并为 `ready=true`、0 blocker。Python 3.11 全量回归为 `1037 passed,
7 skipped`。这些是工程门禁里程碑，不等同于 screening、provider freeze 或
superiority claim 完成。

为当前 composite r1 增加了独立的 `scripts/continue_composite_convergence.py`
终态监督器与操作手册。它校验 screening PID 与 frozen plan 身份，等待 terminal
state，只在 `target_suite_calls_performed=false` 且 transport admission ready 时
执行一次 ranking conversion；监督器不会恢复进程、修改 plan、启动 target suite
或伪造 ranking。receipt 只保留 hash、digest、状态和 reason code。
等待期间每个低频轮询周期还输出 hash-only `screening_progress` 事件，记录
terminal 计数和 target-suite 禁止标志，便于长任务恢复时判断进度而不读取答案。
进度事件改动后的最终 Python 3.11 全量回归仍为 `1042 passed, 7 skipped`。
监督器还要求 observed PID 同时包含 `baseline-screening-run` 和 frozen plan 片段，
避免携带同名 plan 的无关进程通过身份校验；该门禁已由专项测试覆盖。

新增 `scripts/audit_composite_convergence.py` 离线收敛审计 Harness：它按
screening → transport admission → ranking → provider freeze → Harness pin/import
→ target campaign → final audit 顺序读取同 cohort artifact，只输出 hash、schema、
计数和安全 reason code。`ready_for_target_campaign` 与最终 `ready` 分离，避免
target gate 自锁；当前 r1 实际审计为 `status=running`、`next_gate=screening`、
`target_suite_calls_allowed=false`，没有产生新的 provider 或 target-suite 请求。
provider freeze gate 还要求固定 schema、预注册外部 top-three、3 个 baseline、
当前 registry hash 和所有敏感字段显式为 false，伪造的 `final_claim_freeze_ready`
不能打开 target gate；若 state 已记录 `target_suite_calls_performed=true`，即使
下游 artifact 看似 ready 也必须整体 blocked。新增 Harness 专项覆盖后，Python
3.11 全量回归为 `1048 passed, 7 skipped`。

新增 `scripts/watch_composite_convergence.py` 作为离线 watcher：每个低频周期先
原子重建 `composite_harness_cohort_binding.v1`，再运行同一组输入的收敛审计，避免
screening state 变化后 binding receipt 过期或 watcher 忘记传入 cohort binding。
它只输出状态、next gate、digest 和安全 reason code；screening 终态后默认退出，
不会自动恢复 frozen plan、创建 successor、调用 provider 或启动 target Harness。

监督器已通过 `setsid` 后台接管当前 composite r1 screening；推送后的 Python 3.11
完整回归为 `1042 passed, 7 skipped`。此结果仍是工程与 Harness 证据，不等于
screening terminal、provider baseline freeze 或 superiority claim。

当前 probe-bound registry 的 L3b dry-run 已重新验证三档 route plan：`axio-fast`
 为 `fast_light_verify`、`axio-terra` 为 `terra_direct`、`axio-pro` 为
 `pro_panel_judge_escalation`，辅助模型未进入 selected panel。Pro 的原始
 Judge/Synthesizer 先按能力最高 profile 选择；随后只因延迟 guard 触发而换成
terra，替代质量门限（Judge 97% / Synthesizer 92%）和 p95 3x guard 均通过。

2026-08-17，composite r1 screening 已自然终态：20 个 source-units 中 8 个
completed、12 个 transport-blocked，state 为 `partial`、`ready_for_ranking=false`。
transport-only admission 只留下 1 个满足两源 failure-rate 门禁的 canonical model，
低于固定最低 3 个，因此 `transport_admission.status=blocked`；supervisor 未生成
ranking、provider freeze 或 target 请求。该 cohort 的完整分母、失败分类和
hash-only binding/audit receipt 均保留，禁止使用 completed subset 做 ranking 或
superiority claim。

为寻找合规 successor 候选，当前运行一次独立 live `operational-admission`：使用
同一 probe-bound registry、固定 90 秒上限、5 个非 target workload/profile、2 个
worker；只有完整 formal baseline eligibility 才能注册新的 immutable screening plan。
这一步不修改 r1 frozen plan，也不把 operational admission 结果当作质量排名。

离线 scaffolding 已生成：六套 pin 全 ready，execution plan 为 108 个 task 且
结构门禁全通过；acquisition status 仍缺 108 个 official import，所以暂不执行
target provider calls，也不把该 plan 当作 final claim evidence。

六套 source/pin preflight 已完成：LiveCodeBench、HumanEval、BFCL、IFEval ready；
MT-Bench 因 comparison/judge 尚未跨 provider 绑定、tau-bench 因 public gateway
与 frozen user simulator 缺失而 blocked。两类 blocker 均为安全的 hash-only receipt，
待 provider freeze 后补齐配置，不降低 Harness 门槛。

tau-bench 的独立 simulator、gateway、两环境和 Python 3.11 configured preflight
现已 ready（尚未绑定最终 freeze）；MT-Bench 仍等待 freeze 后的跨 provider
comparison/judge profile 解析。

## 当前 r5 基线推进记录（2026-08-16）

本轮继续执行 provider baseline 的独立 NVIDIA candidate cohort，不修改
2026-08-15 transport5 freeze、正式 serving registry 或 CPA Plus formal 服务。
当前路线是对 r5 进行 repair：保留旧的失败 screening plan，使用两份 live
`/models` catalog probe 重新建立 identity-attested plan。

- NVIDIA catalog：`private/runs/2026-08-16-nvidia-candidate-cohort-r2/provider_probe.private.json`
- CPA catalog：`private/runs/2026-08-16-nvidia-candidate-cohort-r5/cpa-catalog-enrollment/provider_probe.private.json`
- 当前候选 registry：`private/runs/2026-08-16-nvidia-candidate-cohort-r5/registry.probe-bound.private.json`
- 旧失败 plan：`private/runs/2026-08-16-nvidia-candidate-cohort-r5/baseline_screening_plan.private.json`
- 新 plan：`private/runs/2026-08-16-nvidia-candidate-cohort-r5/baseline_screening_plan.identity-attested.private.json`

新 plan 必须通过 exact catalog identity attestation、保留 `max_workers=1`、
保留 fail-fast transport gate，并在任何 target benchmark 之前完成 non-target
screening。只有 screening terminal、ranking evidence 完整且 operator-owned
external ranking manifest 可验证后，才允许生成 provider baseline freeze。

本路线的主要风险是 catalog identity 不完整、transport failure gate、外部排名
证据不足和 secret/raw provider data 泄露；所有失败均保留在独立 r5 artifact 中，
不复用历史 cohort 的答案、分数、延迟或 survivor subset。

## Objective

Build `axio_fusion_api` as a standalone, ASciFS-decoupled Fusion API service that exposes `axio-fast`, `axio-terra`, and `axio-pro` through Chat Completions, Responses, Anthropic Messages, and Gemini-compatible surfaces.

## Canonical Convergence Path

The current implementation path is frozen to the staged control-plane gates
in [docs/operations/convergence_execution_path_r20.md](docs/operations/convergence_execution_path_r20.md): finish the active immutable full-pool pre-Fusion screening cohort, convert the complete pool into an externally evidenced rank-1/rank-2/rank-3 baseline freeze, close the official/audited harness import gate, then run the independent 9-category/21-suite campaign and claim audit. Until those gates are terminal, do not add new Fusion algorithms or tune prompts against benchmark material. A failed gate is preserved as evidence and repaired in a new cohort.

## Non-Negotiable Constraints

- Do not import or depend on ASciFS runtime modules.
- Keep all Fusion API implementation code in the standalone `axio_fusion_api/` workspace; ASciFS may call it as an external component, but Fusion must not share code paths or runtime state with `axio/`.
- Do not persist API keys, raw provider URLs, raw provider model ids, raw prompts, raw labels, or raw provider outputs in public evidence artifacts.
- Evaluate only through API requests; do not train on, tune against, or leak benchmark labels.
- Compare `axio-pro`, `axio-terra`, and `axio-fast` against the strongest, second strongest, and third strongest provider single-model baselines selected from the complete live-probed configured-provider pool by an externally evidenced, pre-registered provider-pool ranking.
- Keep median and p95 latency within 3x of the corresponding single-model baseline.
- Require practical effect-size gates in addition to paired statistical significance before superiority claims are allowed.
- Use 21 authoritative benchmark suites across 9 categories, with gated datasets recorded as blocked unless licensed access is provided.

## Current Implementation Route

1. Stabilize the 21-suite benchmark contract and standalone tests.
2. Strengthen provider discovery, multi-format input adapters, routing, fusion admission, expert role assignment, judge, targeted escalation, synthesis, and trace safety.
3. Ensure public output compatibility across the four API surfaces.
4. Run smoke tests with fake clients first, then live provider probing only when credentials are available through the environment or an explicit process-local secret resolver.
5. Produce auditable benchmark campaign artifacts: methodology, source manifest, case hashes, dataset readiness, run matrix, provider probe evidence audit, provider baseline freeze manifest, runs, scorecard, claim audit, final audit, and evidence pack.
6. Treat provider input as fully configuration-driven: arbitrary providers and model lists may be supplied with mixed Chat Completions, Responses, Anthropic, or Gemini-compatible transports; current CPA Plus/NVIDIA conventions are optional seeds, not Fusion system dependencies.
7. When claims fail, produce a shadow-only failure analysis and ablation plan that maps evidence/API/score/statistical/latency failures to bounded routing, orchestration, prompt-context, and synthesis knobs without applying benchmark-tuned policy automatically.
8. Audit arbitrary provider portfolios before expensive live campaigns so missing baseline tiers, API-format diversity, Fusion roles, fast-path capacity, pricing/context metadata, and 9-category capability coverage are visible as safe hashes and reason codes.
9. Audit official/audited harness imports before live campaigns so source-manifest, case-hash, harness-pin, prompt, decoding, and imported-run receipts are bound before provider budget is spent.
10. Run formal live campaigns only with strict live preflight enabled, so incomplete system-development readiness, 21-suite readiness, live probe evidence, provider baseline freeze, or registry binding failures produce safe blocked artifacts before any provider/model calls.
11. Verify the four public protocol entrypoints before live campaigns with a dry gateway self-test, then verify benchmark-score parity after live runs with the campaign API-surface parity report.
12. Keep a top-level completion audit after evidence-pack/final-audit generation, mapping every product, provider, API-surface, benchmark, statistical, latency, contamination, and final-claim requirement to concrete hash-only evidence or a precise blocker.
13. Treat system development readiness and LLM benchmark validation as separate phases: engineering readiness is proven by standalone code-test receipts, dry protocol/adapter self-tests, runtime construction, and operator runbook templates; model superiority is proven only later by the separate 9-category 21-suite live benchmark campaign.

## Current Execution Reconciliation (2026-08-09)

The on-disk r26 cohort and its r27 successor are both partial diagnostic
artifacts, not active background jobs: r26 completed one unit and r27
completed two units before their transport-failure gate blocked progress.
Both retain `ready_for_ranking=false`; no screening process is currently
running, and neither partial result may be resumed into a baseline or used to
choose a survivor subset. A new cohort must be registered from the current
provider configuration after the transport cause is understood.

The retained failure telemetry is transport-dominated rather than a scoring
failure: r26 contains 115 provider timeouts, 82 transport/network errors, one
provider 5xx, and two empty outputs; r27 contains 27 provider timeouts and
three empty outputs. This is sufficient to quarantine the cohorts, but not
to infer a model ranking or diagnose a live endpoint from partial evidence.
Before a new cohort, the operator must verify the configured proxy path,
provider deadline behavior, and endpoint health with a bounded non-benchmark
connectivity check.

The replacement r43 cohort is now terminal and ready for runtime admission:
its complete filtered pool contains 10 logical models and 10 eligible physical
profiles with strict three-sample streaming and role-probe evidence. The
generation wrapper, handoff, and registry are bound by their content digests.
The generation-bound probe projection was performed offline from the nested
`eligible_profile_bindings`; its private and redacted artifacts were bound to
a new r43 registry copy, and the hash-only provider-probe evidence audit is
ready with zero blockers. This closes the evidence projection gap but does
not create external rank 1/2/3 evidence, freeze provider baselines, activate
benchmark traffic, or support an Axio superiority claim.

The r43 external-ranking template remains template-only. The next required
action is to obtain two common independent non-target ranking source families
with complete-pool coverage, exact canonical identity attestations, source
snapshots, and population counts. The old `prefusion-probe-export` command
continues to accept only raw screening reports; generation wrappers must use
the explicit `prefusion-generation-probe-export` command.

The current r43 source-coverage audit is recorded in
`docs/external_ranking_source_audit_2026-08-09-r43.md` and its hash-only
private receipt. Fresh LiveBench, Chatbot Arena, and SimpleBench snapshots
were checked through the configured proxy. Their literal identity coverage is
0/10, 1/10, and 1/10 respectively; their diagnostic suffix/namespace
variants do not count as identity coverage. No source covers the complete
10-model pool, so the audit produced zero common complete source families and
the ranking template remains unchanged. The next admissible step is either
two complete, pre-registered external source families or two independent
pre-registered non-target evaluations over the complete pool. No partial union
or manual alias mapping may be promoted.

The r44 successor screening plan is now registered from the unchanged
probe-bound r43 registry plus a fresh, non-target `/models` catalog
revalidation. The catalog revalidation initially exposed a provider-slug
normalization defect (`cpa_plus` versus `cpa-plus`); the control-plane fix
normalizes only provider slugs while retaining exact model-alias matching and
explicitly forbidding fuzzy model identity mapping. The resulting plan is
ready with 10 canonical groups, 10 physical profiles, two independent source
families, 20 serial tasks, 2,200 estimated provider calls, and
`max_workers=1`. Its plan digest is
`149b35317a5bfdfd8450e9d427d7316cfdf12a56b66373fcd8de4ce744b77c67`.
The zero-network preflight is `preflight_ready` with zero provider and target
suite calls. Live screening is running in the isolated r44 private root;
partial checkpoints remain diagnostic until every registered task reaches a
terminal state and the fixed transport-failure gate is evaluated. No ranking,
baseline freeze, target-suite call, or superiority claim is authorized yet.

## Historical Execution Checkpoint (2026-08-05)

The historical serving registry was the fresh, full-pool, strict-stream
registry from the private r22 provider enrollment. Its 22 logical models are
retained as provenance, not as the current production pool. The r24 fail-fast
screening attempt was intentionally interrupted after a private checkpoint
showed a source-contract defect: MMLU-Pro question numbers were not globally
unique. Its 16 completed/partial units and checkpoint remain diagnostic-only;
they cannot be converted into ranking evidence and no target benchmark call
was made from them.

The adapter defect is repaired without changing Fusion prompts, routing, or
model policy. MMLU-Pro case identities now bind category, source question
identity, question content, and options, while excluding the reference answer
to preserve label-blind selection. All screening adapters now fail closed on a
missing or duplicate case identity. The adapter digest therefore changes and
forces a new source-manifest binding and immutable plan.

The engineering gate remains independently ready: the Python 3.11 regression
passes 983 tests, including the new identity, duplicate-source, and
fail-closed ranking conversion tests. Ranking conversion now returns a safe
template when an interrupted campaign has no complete cross-source evidence,
instead of raising while aggregating an empty list. The former r25 full-pool
attempt reached a terminal partial result and its transport-only successor
admission retained no eligible canonical model; it remains diagnostic only.

The historical r26 plan was the fresh configured-provider full-pool cohort from
the 2026-08-06 enrollment. Its zero-network preflight authenticated five
canonical model groups, two independent source families, ten source-model
tasks, serial execution, and plan digest
`81c20ba9d20ede6f062e5f0d26043ac17fddb9935d8b146f9b48f153b241219c`.
The plan binds the existing source-manifest content digest. Its on-disk
partial execution is superseded by the current reconciliation above.
Ranking conversion, provider baseline freeze, official harness import
validation, and the separate 9-category/21-suite target campaign remain
closed. No provider baseline or Axio superiority claim is currently trusted.

The `prefusion-probe-export` command now turns a ready screening artifact into
the standard provider probe contract offline. This removes the last manual
projection step in the current evidence chain and is reusable for future
arbitrary channel configurations. It does not alter Fusion runtime code or
use benchmark data.

## Pre-Fusion Model Generation

The pre-Fusion control plane now generates the handoff in two distinct
artifacts: a complete logical-model research-prior ranking and a latency-
filtered physical admission list. The remote research Agent is invoked in
bounded batches (default 4 candidates, maximum 64), with bounded concurrent
workers. Every batch is validated against its own exact candidate subset. The
local merge is deterministic: `research_quality_score` descending,
`confidence` descending, then `candidate_id` ascending, followed by regenerated
global ranks `1..N`.
Any failed or incomplete batch blocks the whole ranking and therefore prevents
all provider streaming probes. Only after the complete ranking exists do we
probe every physical replica with `stream=true`, require observed SSE/NDJSON,
non-empty output hash, measured latency, and the hard 90-second gate. Fresh
production admission uses three independent samples per physical profile by
default (bounded to five); every sample must pass the strict stream and
90-second conditions. A one-sample production setting blocks admission. The
resulting logical `available_model_list` is the only model list handed to
Fusion; same-canonical replicas remain load-balancing/failover replicas.

The handoff is authenticated again at the registry boundary. The registry
validator binds every physical profile hash to one live probe binding, checks
strict SSE/NDJSON evidence, non-empty output hashes, measured latency at or
below 90 seconds, canonical replica projection, contiguous available ranks,
complete research-candidate coverage, and catalog hashes. The report-level
validator also binds the report list, catalog, counts, and registry digest to
the same handoff. A changed list, binding, latency receipt, or stream receipt
fails closed before Fusion enrollment.

The runtime now consumes this contract through
`build_prefusion_fusion_handoff()`. It is the single extraction boundary for
the complete research ranking, the available-only operational ranking, and
the latency-filtered logical `available_model_list`; callers cannot select a
different report projection and still obtain a ready handoff. Both rankings
and the logical list are content-digested. The private physical registry is
opt-in for file-backed operators, while dynamic enrollment keeps endpoint
credentials in process-local profiles. A safe handoff projection hashes
provider/model identifiers and never includes the private registry. Legacy
single-sample `*_observed_p50_latency_ms` aliases are normalized to explicit
`*_observed_latency_ms` fields at this boundary without treating them as
percentile statistics.

## Post-Image Engineering Re-audit (2026-08-09)

The image capability lane is independently ready: focused image/config/provider
contracts pass `107` tests, the promoted image registry loads one verified
generation/editing profile, and a no-upstream loopback health check confirms
the image lane is isolated from text Fusion. The overall health status remains
`usable_with_warnings` because the current text serving registry reports weak
or missing Judge and structured-output candidates.

The final standalone regression for that image re-audit was `999 passed, 0
failed`, including the image parameter capability contract. The current
standalone regression is `1009 passed, 0 failed`. The earlier
18 legacy panel/latency and provider/registry failures were repaired in the
same engineering re-audit and are retained only in prior receipts for
provenance. A green code regression does not promote the text serving registry
or authorize provider ranking, baseline freeze, target benchmark traffic, or
an Axio superiority claim.

The current runtime image profile declares `input_fidelity` and transparent
background as unsupported for `gpt-image-2`. The gateway validates these
options against profile metadata before prompt composition and provider I/O;
unknown capability declarations fail closed rather than silently dropping
user intent. The r41 serving artifact remains rejected because its
pre-Fusion generation marker and binding block are inconsistent, and r42
remains a candidate artifact until a complete enrollment handoff is produced.

## Registry Admission Diagnostics (2026-08-09)

`registry_load_diagnostic` and the `registry-diagnostic` CLI now expose the
same pre-Fusion validation reason codes used by the production load boundary.
The command is read-only and network-free: it reports only hash-safe artifact
status, row/profile counts, readiness projections, and a registry-path digest.
It returns a blocked exit status for an invalid artifact but never changes the
fail-closed behavior of `load_registry()`. The r41 serving artifact now
produces actionable binding, catalog, probe-binding, and role-coverage
reasons; r42 remains explicitly unpromoted.

The production `scripts/run_server.py` entrypoint no longer selects the
historical 2026-07-28 calibrated registry when the operator has not bound a
current text registry. It requires `AXIO_FUSION_REGISTRY_PATH` and loads it
with `require_prefusion=True`; until a complete cohort is promoted, startup
stops before creating a live engine. Diagnostic and offline test paths remain
available through their explicit non-production flags.

## Image Capability Lane (2026-08-09)

Image generation/editing is a sibling serving capability, not another Fusion
expert role. The current CPA Plus discovery found `gpt-image-2`; the endpoint-
bound probe passed generation and editing independently with streamed SSE
frames under the 90-second ceiling. Its verified private image registry is
loaded only through `AXIO_FUSION_IMAGE_REGISTRY_PATH`.

The image lane has its own candidate loader, probe artifact, redacted binding
receipt, and atomic promotion. The text registry continues to exclude all
`gpt-image-*` names. Prompt composition is bounded and optional: it runs only
after image profile selection, accepts a fixed JSON response, and falls back to
the original user intent on any composition failure. Image output limits,
multipart limits, proxy policy, key rotation, and same-model failover remain
enforced independently of text Fusion.

The 2026-07-22 v6 handoff and 2026-07-23 v9 cohort are historical operational
evidence, not the current serving or benchmark input. They remain available for
migration audits but must not be reused for a new baseline freeze, runtime
activation, or superiority claim. The current r43 generation cohort is the
explicit replacement: it contains 10 profiles after complete discovery,
strict three-sample streaming admission, and role-probe binding, and its
generation-bound provider evidence audit is ready. It is eligible for
runtime-admission follow-up, but it is not an external baseline ranking and
does not authorize benchmark traffic. The stopped 2026-07-23 v8 non-target
baseline campaign remains invalid for ranking because its observed transport-
failure rate exceeded the pre-registered 2% ceiling; it must never be
overwritten, resumed, or used as ranking evidence.

## Baseline Contract

The final claim family always contains exactly three provider single-model baselines. After live probing freezes the complete usable provider pool, the system groups profiles by `canonical_identity_sha256` and treats each group as one model baseline. An operator prepares a private external-ranking manifest that screens every live-probed canonical group with at least two distinct independent non-target ranking sources. Each group retains a hash-only representative plus the complete replica profile hash set, provider/API-format coverage, and identity attestations for every replica. Each rank must include the source's ranked-population count. The system keeps only source families shared by the full pool, requires at least two common families with the same snapshot and population across every candidate, averages the normalized percentile `(rank - 1) / (population - 1)` equally across those families, then uses the candidate hash as a deterministic tie-break. It rejects any submitted rank 1/2/3 rows that differ from that derived order. Each selected rank also requires official identity/capability corroboration, a pre-campaign date, a deterministic tie-break policy, and an explicit declaration that no target-suite material or result was used. The hash-only freeze binds that mapping to the registry, campaign, runs, scorecard, and claim audit. `axio-pro`, `axio-terra`, and `axio-fast` compare only with ranks 1, 2, and 3 respectively.

Legacy all-provider inventories remain useful for operational diagnostics, routing exploration, and diversity audits, but they are never a final-claim baseline selection mode. Axio claims are allowed only when the provider probe evidence audit, external-ranking freeze, paired case-level comparisons, multiple-comparison correction, source/case/prompt/decoding binding, contamination audit, and latency gates all pass.

The superiority gate requires both statistical and practical significance: paired one-sided exact sign tests must pass Holm-Bonferroni familywise correction, each primary score delta must be at least `0.01`, and each paired net win-rate delta must be at least `0.05`; Wilson 95% confidence interval summaries are emitted for audit.

Latency superiority is also claim-gated on two distribution points: both p50 and p95 case latency for each Axio tier must be present and no more than `3x` the corresponding same-suite provider baseline before a final superiority claim can pass.

## Active Baseline Execution (2026-07-29, full cohort r1)

- Dominant phase: `execution`.
- Enrollment gate: the fresh full-cohort enrollment completed with `status=ready`.
  The serving registry contains 35 live-probed text profiles across two providers
  and two upstream formats (`chat` and `responses`); every admitted profile has
  strict SSE/NDJSON evidence within the 90-second ceiling. Probe, registry, and
  redacted evidence profile-set bindings all pass.
- Engineering evidence: the standalone regression is `769 passed`; the dry
  provider-input adapter self-test covers all four upstream input formats, and
  the dry public protocol self-test covers all 3 Axio models x 4 public formats
  (`12/12` requests passed). These are system-readiness evidence only, not model
  quality evidence.
- Frozen screening contract: plan schema v3, 35 canonical candidates, two
  independent non-target source families, 70 source-candidate units, 6,230
  estimated provider calls, and plan-level `max_workers=1`. The plan digest is
  `c6ecb07d000e65563d31dc368ded09ffd6b18501bf9e51ad7811909b7b00c173`.
- Execution path: the complete live campaign is running in the isolated
  `current_channel_enrollment_20260729_full_cohort_r1/screening_r1` private
  root. It began only after the zero-network preflight passed; no old cohort
  checkpoint, answer, score, survivor, or failed unit is reused.
- Verification target: all 70 units must reach terminal authenticated states,
  retain every failure in the denominator, pass private rescoring and the
  pre-registered transport-failure gate, and then produce a complete
  screening-to-ranking conversion before any rank-1/rank-2/rank-3 baseline is
  frozen. No target-suite benchmark call is allowed before that freeze.
- Downstream trust state: `verification_incomplete`. The new registry is
  serving-admissible, but no provider baseline or Axio superiority claim is
  trusted until screening, ranking, freeze, and the separate 21-suite campaign
  complete.

## Active Baseline Execution (2026-07-28, v3 isolated cohort)

- Dominant phase: `execution`.
- Route: `repair`. The former R2 cohort is retained only as a transport
  diagnostic because unregistered same-channel diagnostics and mutable
  per-unit concurrency made it unsuitable for ranking. No R2 answer, score,
  survivor, or failed unit is reused.
- Baseline object: three canonical single-model provider groups derived only
  after complete non-target screening of the newly admitted cohort. These
  become rank 1, rank 2, and rank 3 for comparison with `axio-pro`,
  `axio-terra`, and `axio-fast`, respectively.
- Source contract: the pre-registered two-family non-target source manifest
  used by R2 remains hash-identical and declares no target-suite prompt, label,
  output, or result use. It contributes at least 70 fixed cases per source.
- Setup evidence: fresh `/models` discovery found 126 entries; strict serial
  stream admission produced a 25-profile calibrated registry; fixed five-
  workload operational admission evaluated all 25 profiles with
  `max_workers=1` and a 90-second ceiling, leaving 12 formal-baseline-eligible
  canonical profiles.
- Frozen run contract: screening plan schema v3, 12 canonical candidates, two
  independent source families, 24 source-candidate units, 2,136 estimated
  provider calls, and plan-level `max_workers=1`. The plan digest binds the
  registry, source/case/scorer/transport implementation, operational admission,
  task order, and worker count.
- Execution path: the live campaign runs in the isolated
  `axio-screen-v3-r2` tmux session with a distinct live checkpoint and private
  unit root. No smoke, diagnostic, benchmark, or manual provider request may
  share the channels until it reaches a terminal state.
- Verification target: all 24 units must reach terminal authenticated states,
  every completed unit must pass private-artifact rescoring and the registered
  transport-failure gate, and strict screening-to-ranking conversion must
  produce a complete rank assignment before a top-three freeze is accepted.
  A partial survivor subset is never a baseline.
- Downstream trust state: `verification_incomplete`. No provider baseline is
  currently trusted for target-suite comparison, and the 9-category/21-suite
  campaign remains prohibited until conversion and freeze both pass.

## Revision Log

- 2026-07-23: Completed a new full-pool v9 pre-Fusion cohort from the current
  two-channel configuration. Discovery found 131 physical profiles; the remote
  research workflow completed every candidate record; and the three-sample
  strict-stream gate admitted 34 profiles, excluded 11 at the 90-second ceiling,
  and excluded 86 for stability/protocol failure. No ordinary JSON fallback was
  admitted. Both report and registry handoff validation passed with complete
  solver/Judge/Synthesizer coverage. A separate native-tool operational probe
  then calibrated the same registry: 18 profiles proved native tool calling,
  while text-only, unparseable, transport, and latency outcomes remained
  unproven. This calibration used no benchmark prompt, label, or score. The
  subsequent standalone regression passed 637 tests. Public live protocol and
  complete-Fusion checks remain separate pending evidence, and no capability or
  latency-superiority claim is made.

- 2026-07-23: Replaced one-sample production admission with a bounded
  multi-sample strict-stream stability contract. The default is three samples
  per physical profile, each of which must return framed SSE/NDJSON within 90
  seconds. The contract, aggregate p50/p95/max latency, all-success counts,
  and hash-only sample receipt digest are bound into the private registry and
  validated again at handoff loading. Dynamic gateway enrollment and atomic
  channel refresh now pass the same setting end to end. This is serving
  admission hardening only; it does not use or tune on benchmark data.

- 2026-07-22: Hardened non-target provider screening before live execution.
  Official scorer runtime dependencies are now imported during plan creation;
  a missing dependency produces a stable blocker before any provider request
  is issued, and the source receipt binds the preflight result into its
  snapshot digest. The standalone benchmark extra declares `lxml`, required
  by the pinned LiveBench table-reformat scorer. A real screening attempt
  exposed this missing dependency after 108 calls; the attempt remains
  blocked because its transport-failure rate exceeded the pre-registered 2%
  gate, and it is retained as historical evidence rather than reused as a
  ranking result. The corrected runtime-preflight plan is ready with 34
  canonical groups, two independent sources, and an effective 90-second
  timeout cap.

- 2026-07-22: Re-ran the complete pre-Fusion workflow with the versioned
  capability-evidence mapping prompt contract. The remote Agent first extracts
  candidate-scoped facts, then maps them to axes and roles before ranking; the
  prompt explicitly maps structured output, tool calling, verification, and
  named evaluation families without copying benchmark scores. All 50 research
  batches for the 139-model inventory validated. Strict streaming probes
  admitted 34 profiles and excluded 11 by the 90-second ceiling; stream
  fallback remained zero. The v6 report and private registry both validate,
  `load_registry()` loads 34 profiles, and the required solver/judge/
  synthesizer coverage is ready. Artifacts are
  `private/prefusion_full_live_20260722.capability_axes.v6.report.json`,
  `private/prefusion_full_live_20260722.capability_axes.v6.registry.private.json`,
  and the redacted `.safe.json`. This is serving-admission evidence only.

- 2026-07-22: Completed a fresh live pre-Fusion handoff with the current
  process-injected NVIDIA Chat Completions and TokenAPIs Responses channels.
  Discovery returned 139 physical profiles from two providers. All 139
  profiles were included in the 35-batch research-prior workflow; all 35
  batches passed strict schema validation and deterministic merge. All 139
  physical profiles then received strict streaming probes. 36 profiles passed
  live streaming evidence, non-empty output hashing, measured latency, and the
  hard 90-second gate; 19 exceeded the ceiling, 79 failed transport/semantic
  health checks, and 5 returned unexpected output. The handoff contains 36
  logical models and 36 physical profiles, and the generated registry is
  directly loadable with `binding_status=ready`. Artifacts are
  `private/prefusion_full_live_20260722.operational.v1.safe.json` and
  `private/prefusion_full_live_20260722.operational.v1.registry.private.json`.
  The complete standalone suite passes `581` tests; compilation and diff
  checks pass. This is an operational model inventory/prior and
  serving-admission result only, not benchmark evidence or a model-superiority
  claim. The safe receipt uses explicit hash-only provider/model redaction.

- 2026-07-22: Rebuilt the complete pre-Fusion handoff under the capability-axis
  contract. The configured channels returned 139 physical profiles; all 139
  candidates passed 35 strict research batches with zero capability-axis gate
  failures, and all 139 physical profiles received strict stream probes. 32
  profiles were admitted, 23 exceeded the 90-second ceiling, 80 failed
  transport checks, and 4 returned semantic/unframed output. The v2 report,
  private registry, and hash-safe receipt validate; `load_registry` loads 32
  profiles. This is serving-admission evidence only, not benchmark evidence.

- 2026-07-22: Added the explicit report/registry handoff validation contract.
  `validate_prefusion_handoff()` binds the report to the private registry and
  `validate_prefusion_registry_handoff()` binds physical profiles, streaming
  evidence, latency receipts, logical canonical replicas, contiguous available
  ranks, and the complete research catalog. Runtime enrollment and registry
  loading now fail closed on a tampered or incomplete handoff. Focused
  handoff/enrollment regressions and the full standalone suite pass (`574
  passed`); this remains serving-integrity evidence, not benchmark or
  model-superiority evidence. The current handoff still has non-blocking
  warnings for uncalibrated Judge and structured-output roles.

- 2026-07-22: Reduced the default pre-Fusion research shard to 4 logical
  candidates and bounded each shard to at most one retry. The prompt now
  presents the exact candidate and source IDs for that shard, uses a bounded
  source excerpt, and explicitly requires strict JSON with no prose. Every
  attempt is independently schema-validated; only a fully validated retry can
  be merged, while a second failure or a latency violation blocks the complete
  ranking. Focused model-screening verification is `21 passed`; the full
  standalone regression is pending this change.

- 2026-07-22: Completed the pre-Fusion available-model handoff hardening.
  The remote research Agent still produces only a complete operational-prior
  ranking; serving admission now additionally requires an explicit live probe
  mode, a real measured stream latency, a valid non-empty SHA-256 output digest,
  and the hard 90-second ceiling. The generated logical list now carries both
  the original `research_prior_rank` and a contiguous `available_rank` after
  slow profiles are removed. Registry loading fails closed on missing or
  duplicated profile bindings, invalid probe/output digests, missing latency,
  non-live evidence, or a logical-list/profile-set mismatch. The standalone
  suite passed `571` tests before the current shard/retry change and compilation
  passed. The current shell has no
  process-injected provider credentials, so no live provider list or model
  capability claim is produced by this revision.

- 2026-07-21: Repaired the non-target screening resume digest so a recovered
  state hashes both prior and newly reconstructed units. This prevents an
  interrupted campaign with an existing failed/blocked row from being rejected
  as tampered on its next authenticated resume. The complete standalone suite
  now passes `533` tests in `233.46` seconds. Hash-safe engineering evidence
  was regenerated against the current 42-profile calibrated registry: all
  12 dry public API cells, all four upstream adapters, and the remote API-only
  boundary pass. A local, zero-provider-call recovery audit authenticated 23
  retained screening units (3 complete, 20 retryable transport-failure units)
  and verified that the merged resume state has zero authentication errors.
  The remaining live gates are process-local provider credentials, completion
  of the pre-registered 35-model baseline screen and rank freeze, authorized
  GPQA access, six official/audited harness imports, and the locked 21-suite
  campaign. No model-superiority claim has been made.

- 2026-07-21: Refreshed the standalone regression at `527` passing tests
  after Hermes feedback resource-atomicity coverage and provider operator
  summary hardening. `provider-config-summary` now supports a safe `--output`
  artifact and reports whether process-injected credentials are sufficient to
  start live enrollment, without exposing credentials or provider identity.
  System-development readiness is complete; the separate benchmark stage is
  still blocked by external credentials, gated GPQA access, official model
  outputs, and the pre-registered canonical top-three freeze.

- 2026-07-21: Fixed formal benchmark artifact discovery for the mechanical-
  disk cohort layout. The readiness resolver now accepts the canonical short
  filenames inside an explicit cohort directory, binds all eight artifacts to
  a directory-derived cohort token, and persists only its hash in safe
  receipts. This prevents a valid `14/21` materialization cohort from being
  misreported as `0/21` solely because it does not use historical filename
  suffixes; mixed versioned cohorts remain fail-closed. Added regression
  coverage and refreshed the network-free live-readiness receipt. The full
  standalone regression then passed `521` tests; the four public protocol
  self-test completed `12/12`, all four provider input adapters passed, and
  system-development readiness remained `10/10` without provider calls.

- 2026-07-21: Strengthened non-target screening credential diagnostics. A
  profile missing both its endpoint and API key now contributes to both
  hash-only counters and reason families instead of hiding the key failure
  behind the endpoint failure. Added regression coverage; this changes only
  preflight observability and does not relax the live credential gate.

- 2026-07-21: Re-ran the complete standalone Fusion regression after the
  screening diagnostic change: `521 passed` in `193.13` seconds,
  `compileall` passed, and the refreshed remote-only/system-development
  receipts remain ready without provider calls. The non-target full-pool
  screening preflight remains `preflight_ready` with `45` required profiles,
  `0` credentialed profiles, and no network activity.

- 2026-07-21: Added recoverable per-profile provider circuit breakers. A
  consecutive failure threshold still removes a physical channel from route
  construction and same-canonical replica failover, but the channel is
  re-admitted after a bounded process-local cooldown (30 seconds by default).
  Successful recovery clears the consecutive-failure streak; zero cooldown
  preserves explicit manual recovery. Added hash-only cooldown/recovery
  receipts and regression coverage. The complete standalone regression passes
  517 tests with 3 skips in 125.69 seconds; `compileall`, four-surface
  protocol self-test, four-provider input self-test, and remote-only audit pass
  with zero provider calls. This is runtime reliability evidence only and does
  not establish benchmark superiority.

- 2026-07-21: Re-ran the six official/audited bridge preflights with the
  current pinned harness manifest and hash-only candidate binding. LiveCodeBench,
  HumanEval, BFCL, and IFEval are preflight-ready; tau-bench remains blocked by
  the required Python >=3.9 runtime and a configured public gateway, while
  MT-Bench remains blocked until an externally frozen provider comparison and a
  distinct cross-provider judge are supplied. All six receipts performed zero
  model or evaluator calls and persisted no prompts, labels, provider outputs,
  or credentials.

- 2026-07-21: Provisioned the pinned tau-bench package and declared SDK
  dependencies in a separate mechanical-disk Python 3.11 environment, updated
  the private suite configuration to reference it, and re-ran tau-bench
  preflight successfully. This removes the interpreter/runtime blocker but is
  still only preparation: real tau-bench execution remains gated by provider
  credentials and the externally frozen baseline/campaign contract.

- 2026-07-21: Refreshed the live-readiness preflight against the matching
  operational 45-profile calibrated registry while keeping its safe registry
  projection separate. The cohort now reports 45 live-available profiles and
  39 canonical groups without the false empty-registry blocker; live execution
  remains blocked only by missing process-injected credentials, the unfilled
  externally ranked top-three freeze, gated GPQA access, and incomplete
  official/audited harness imports. The preflight performed zero provider
  network calls and persisted no credentials, URLs, prompts, labels, or model
  outputs.

- 2026-07-21: Re-ran the complete standalone regression after the final
  prompt-contract gate addition: `519 passed` in `169.71` seconds;
  `compileall` passed. Refreshed the hash-only code-test, remote-only
  execution, four-surface protocol, four-provider-input, and system-development
  readiness receipts. The audits performed zero provider network calls, found
  zero forbidden imports and zero local model artifacts, and the engineering
  phase is ready for the separate 9-category/21-suite validation phase. No
  benchmark score, latency result, or model-superiority claim was produced.

- 2026-07-21: Added a format-specific benchmark prompt input contract. The
  built-in runner now projects only public task fields before prompt assembly;
  answers, references, hidden tests, instruction checks, and expected tool
  calls remain evaluator-only even when the source row contains them. Each
  case emits a hash-only prompt-contract receipt, dataset validation reports
  structural projection violations, and the methodology manifest makes the
  contract a global campaign requirement. Added six-format sentinel coverage
  for multiple choice, translation, Python code, tool calls, instruction
  following, and exact match. The complete standalone regression passes 518
  tests in 171.18 seconds; remote-only, four-surface, and four-provider-input
  audits remain network-free, and system development is ready for the separate
  9-category/21-suite live validation phase. No benchmark score or superiority
  claim was produced.

- 2026-07-21: Re-ran the complete standalone regression after adding the
  environment-token replay and manifest-commit rollback cases: `515 passed` in
  `170.02` seconds; `compileall` passed. Refreshed the four-format protocol
  self-test, four-format provider-input adapter self-test, remote-only
  execution audit, code-test receipt, and system-development readiness receipt.
  The current source audit covers 30 files with zero forbidden imports, zero
  local model artifacts, and zero audit network calls. The 2026-07-21
  materialization snapshot remains 14 locally ready, 6 official/audited
  harness-blocked, and 1 GPQA gated; live readiness remains safely blocked by
  external provider credentials, the externally ranked canonical top-three
  freeze, GPQA authorization, and missing official model-output imports. No
  benchmark score, latency result, or superiority claim was produced.

- 2026-07-20: Added a lawful, fixed-revision GPQA Diamond acquisition boundary
  for the final 9-category/21-suite campaign. The command accepts no URL or CLI
  credential, requires explicit no-example-leakage terms acceptance, resolves
  a Hugging Face token only from the process environment or secret resolver,
  supports the existing direct/local-10808 proxy policy, restricts redirects
  to HTTPS Hugging Face origins while removing cross-origin Authorization, and
  pins revision `633f5ee89ab8ad4522a9f850766b73f62147ffdd`, 1,373,492 bytes,
  198 rows, and official Git blob `7589e3e467d69a1dceb126a60c4108d6d4f1d166`.
  Download and manifest writes use private temporary files and fail-closed
  commit/cleanup behavior. Materialization now revalidates the gated terms
  receipt, SHA-256, blob, size, row count, and schema on every entry, so a stale
  `downloaded` flag cannot admit a replaced artifact. Ten synthetic acquisition
  regressions plus the existing deterministic option-order regression pass;
  the complete standalone suite passes 515 tests in 170.02 seconds and
  `compileall` passes. No GPQA example, provider call, benchmark score, or model
  superiority claim was produced; real acquisition still awaits operator terms
  acceptance and process-local `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN` injection.

- 2026-07-20: Added an end-to-end Hermes MoA state-advance regression against
  the pinned upstream `per_iteration` process contract. An identical request
  may replay only a previously completed, non-degraded Hermes result; adding a
  new tool result changes the request state fingerprint, bypasses that cache,
  re-runs every configured reference slot, and exposes the new observation to
  references only through the bounded inert-text projection. Repeating that
  unchanged advanced state then reuses the completed result without another
  provider call. The focused Hermes suite passes 21 tests; the complete
  standalone suite passes 504 tests in 167.69 seconds and `compileall` passes.
  Hash-safe code-test and system-development-readiness receipts were refreshed
  with zero provider calls. This is runtime process evidence only and does not
  imply benchmark superiority.

- 2026-07-20: Corrected process-local mixed-channel credential precedence.
  Model-scoped direct values and named secret references now both override
  channel-scoped defaults, using the explicit order `model direct > model
  named secret > channel direct > channel named secret` for endpoints and key
  pools. This prevents a model-specific endpoint or key resolver from silently
  falling back to another model's channel credential. Resolver exceptions are
  normalized at the configuration boundary so backend details cannot escape.
  Added live local-HTTP coverage for resolver-supplied multi-key failover,
  discovery, enrollment, atomic channel refresh, and safe serialization. The
  complete standalone suite passes 503 tests in 168.34 seconds,
  `compileall` passes, and the refreshed hash-only system-development receipt
  remains ready for the separate 9-category/21-suite validation phase. No
  provider benchmark call or model-superiority claim was made.

- 2026-07-20: Fixed a mixed-provider compatibility defect in all four upstream
  adapters. When the caller did not specify temperature, the adapter previously
  injected `0.2`, contradicting the Hermes provider-default contract and causing
  reasoning-capable Responses gateways that reject temperature to fail. Chat,
  Responses, Anthropic, and Gemini now omit the field unless explicitly set;
  explicit `0.0` is preserved. Added four-format request-body regression
  coverage. The updated standalone suite passes 499 tests and no provider call
  was made.

- 2026-07-20: Re-ran the zero-network formal live preflight against the
  calibrated 45-profile registry and current mechanical-disk manifest
  directory after refreshing engineering readiness. The methodology contract
  remains 9 categories and 21 suites (the first eight categories have two
  suites each; `vertical_domain` has five). `system_development_ready` is true,
  but live readiness remains blocked with zero credentialed providers and no
  provider calls. The remaining blockers include incomplete/gated benchmark
  material, non-cohort official imports, missing external top-three ranking
  freeze, and absent process-injected channel credentials. No benchmark answer,
  score, latency comparison, or superiority claim was produced.

- 2026-07-20: Completed the current standalone Fusion regression after the
  Hermes MoA 2.0 budget/cadence documentation refresh. The 370-test core file
  passed in 197.86 seconds and the remaining 11 modules passed 128 tests in
  7.07 seconds, for 498/498 passing tests; compilation also passed. The
  hash-only code-test receipt and system-development readiness were refreshed
  with `system_development_ready=true`, zero provider calls, and no benchmark
  or superiority claim. The formal live phase remains separately gated by
  provider credentials, external rank-1/2/3 evidence, and benchmark-harness
  prerequisites.

- 2026-07-20: Aligned the Hermes MoA 2.0 process contract with the current
  NousResearch `hermes-agent` source at commit
  `e89bc58a5ba80ec6be19b43beca37cbb03091afd`. Axio now records per-seat,
  protocol-neutral cognitive budgets and role-local output caps; Terra and Pro
  Judge caps are 1,536 and 2,048 tokens respectively, while the acting
  Synthesizer retains the caller/provider output budget. Provider-private
  reasoning fields remain capability-attested opt-ins and are not blindly
  forwarded across mixed transports. Reference fanout is explicitly
  `per_state_iteration`, with cross-request reuse requiring an admitted
  conversation scope. Focused Hermes regression passes 20 tests; the complete
  standalone suite is the next verification gate. This is engineering evidence
  only and does not establish benchmark superiority.

- 2026-07-20: Tightened the public Responses compatibility layer against the
  current documented lifecycle. Non-stream Responses objects now expose public
  `background`, `service_tier`, `text.format`, `truncation`, and token-detail
  fields without exposing prompts, provider identifiers, or continuation
  internals. Responses SSE events now use monotonic 1-based
  `sequence_number` values and preserve `response_id`/`call_id` on function
  argument events; Chat `stream_options.include_usage` is covered at the
  server boundary and remains Chat-only. Verification on Monday, July 20,
  2026: focused protocol regression 6 passed, complete standalone regression
  497 passed in 211.24 seconds, compilation passed, and refreshed hash-only
  code-test, protocol self-test, provider-input self-test, remote-only audit,
  and system-development readiness receipts remain ready without any provider
  network calls. This is engineering-compatibility evidence only and makes no
  benchmark or model-superiority claim.

- 2026-07-20: Revalidated the next two evaluation-control stages after the
  497-test engineering refresh. A fresh non-target screening preflight retained
  the frozen plan-file, plan, and execution-schedule digests for 39 canonical
  groups, 45 replicas, 78 source/model units, and 8,580 estimated remote calls;
  it performed zero network or target-suite calls and remains non-executable
  until all 45 required replicas receive process-local credentials. A formal
  21-suite `--live --strict-live-preflight` then stopped before execution with
  `provider_call_count=0` and `network_calls_performed=false`. The public
  protocol, provider-input, and system-development gates passed. Remaining
  blockers are external top-three baseline freeze evidence, GPQA/source-case
  completeness, official/audited harness outputs, and an explicitly running
  Axio HTTP gateway. No benchmark answer, score, latency comparison, or
  superiority claim was produced.

- 2026-07-20: Added an explicit instruction-authority boundary to the Hermes
  MoA process. Projected tool evidence and reference/candidate packets are now
  marked as untrusted data in reference, Judge, and acting-Synthesizer system
  and task prompts; embedded role changes, policy text, context-exfiltration
  requests, or tool directives cannot override the caller system/original task
  or Axio tool policy. Candidate packets carry machine-readable trust labels,
  and the safe Hermes plan exposes a `context_authority_policy` receipt. Focused
  Hermes/Fusion regression remains 41/41; the complete standalone regression
  passes 492 tests in 182.85 seconds, compilation passes, and refreshed system
  readiness remains true without making a benchmark-superiority claim.

- 2026-07-20: Tightened Hermes MoA process aggregation against the pinned
  upstream runtime contract. Parallel advisor calls now enter Judge and
  synthesis context in configured route-role order rather than socket
  completion order, preventing transport jitter from changing prompt order or
  tie behavior. Solver/reference calls now perform bounded same-canonical-model
  replica failover inside the original role, preserving tool-free advisor
  isolation and treating provider replicas as availability paths rather than
  independent evidence. Every physical attempt remains subject to call, cost,
  deadline, cancellation, and circuit controls; safe candidate receipts expose
  only attempt counts and hashes. A selected replica blocked before the provider
  boundary is not counted as a physical attempt. The focused Hermes/Fusion
  regression passes 41 tests and the complete standalone regression passes 492
  tests in 191.73 seconds.

- 2026-07-20: Rechecked the two external execution gates after the 489-test
  engineering refresh. The frozen non-target screening campaign remains at
  zero live calls because none of its six referenced secret environment values
  is injected, leaving 0/45 replica profiles transport-ready; no partial model
  cohort is permitted. GPQA Diamond revision
  `633f5ee89ab8ad4522a9f850766b73f62147ffdd` remains access-gated: the local
  proxy is reachable, but neither a process token nor a cached Hugging Face
  token is available. Credentials must enter through the environment or a
  process-local secret resolver, and GPQA requires lawful terms acceptance;
  neither blocker may be bypassed with chat-secret replay or substitute data.

- 2026-07-20: Hardened official-harness campaign admission against stale
  exhaustive provider freezes. Live execution and every provider task now
  require the current externally ranked, pre-registered canonical top-three
  semantics, exact 1/2/3 tier mapping, digest validity, and registry binding;
  a legacy ready boolean cannot admit a 41-profile diagnostic matrix. A
  narrowly scoped exception permits only zero-call, Axio-only offline
  preflight before rank freeze. The current real suite configuration passed
  48/48 such cells across LiveCodeBench, HumanEval, BFCL, and IFEval (three
  Axio tiers by four public API formats), covering 182, 164, 2,311, and 541
  cases respectively with zero model or evaluator calls. A live admission
  probe against the historical exhaustive freeze blocked before task
  processing and before network calls. The old 294-task all-provider plan
  remains diagnostic; the formal six-suite plan must be rebuilt after the
  rank-1/2/3 freeze. The legacy four-surface MT-Bench bridge test now constructs
  the same externally ranked top-three freeze instead of mutating a one-model
  ready flag. Campaign admission now re-runs the complete external ranking
  receipt and rank-mapping validator, including common-source derived order,
  canonical/replica identity, frozen rows, selected candidate-set digest,
  registry binding, and tier mapping. Active regressions alter each mapping and
  recompute both inner and outer digests; all remain blocked. The complete
  standalone regression passes 489 tests in 190.45 seconds; compilation, 12/12
  dry public protocol cells, 4/4 provider adapters, the remote-only audit,
  runbook, and system-development readiness pass with zero provider calls. The
  refreshed readiness artifact still makes no benchmark-completion or
  model-superiority claim.

- 2026-07-20: Made the in-memory response cache process-contract aware after
  the Hermes MoA hardening exposed a cross-layer bypass. Direct results now
  require a recorded provider execution; Fusion results require a complete,
  non-degraded admitted finalization; Hermes results additionally require the
  completed Judge/feedback/re-Judge/acting-Synthesizer contract. Cache entries
  carry digest-verified, hash-safe origin receipts and are invalidated when the
  current Direct/Fusion/Hermes route contract changes. Replays explicitly
  report zero current process calls, and safe traces plus shadow-learning
  features attribute quality feedback to the admitted origin process. The
  complete current standalone regression passes 484 tests in 189.33 seconds;
  source/test compilation, 12/12 dry public protocol cells, 4/4 provider input
  adapters, remote-only audit, runbook generation, and system-development
  readiness all pass with zero provider calls.

- 2026-07-20: Closed a Hermes MoA process-receipt false-positive in which an
  initial Judge could require a feedback reference but routing, budget, or
  provider availability could prevent any candidate from being created. The
  runtime now freezes the initial Judge decision independently and records
  feedback requirement, execution presence, successful output, and re-Judge
  completion as separate safe facts across text answers, acting Synthesizer
  tool turns, durable traces, and shadow-learning features. Required feedback
  completes the process only after a successful feedback output, a second
  accepted Judge round, and accepted acting-Synthesizer output. The full
  standalone regression passes 484 tests in 164.24 seconds and the focused
  Hermes suite passes 17 tests.

- 2026-07-20: Refreshed standalone engineering evidence after checkpoint and
  Hermes process-contract hardening. The complete independent regression passes
  480 tests in 167.88 seconds; compilation, all 12 dry public protocol cells,
  all four upstream adapter families, and the remote-only audit pass. Hermes
  high-consensus paths can no longer bypass the one acting Synthesizer; empty
  aggregation and failed feedback without re-Judge are explicit degraded,
  process-incomplete outcomes. The deliberation live smoke now enforces the
  same process receipt instead of accepting a generic early exit.

- 2026-07-20: Implemented the pre-registered full-pool baseline screening
  runtime and regenerated its safe v2 plan after the final MMLU-Pro prompt,
  LiveBench release-filter, scorer, and scheduling changes. The frozen plan
  covers 45 live profiles grouped into 39 canonical models, 112 stratified
  MMLU-Pro cases, 108 pinned LiveBench cases, 78 source/model units, and 8,580
  estimated remote calls. Exact provider catalog identity attestation is
  45/45. Candidate execution is seed-derived, source-interleaved, and paired-
  reverse counterbalanced before the first call. The plan digest is
  `5b206e7eb2439e2ab8deccb34ae62e1d6616f84a71331aefe48bdd4dd07f8c1a`;
  its schedule digest is
  `78ed0c8cc398596fc1ffae176af69dae3d3ed2d3254c8b1bf6662a779f5f1a8a`.
  The exact plan-file content hash is
  `7fd1fa6536c3332992f407b67f7c2a7934751f746b873046537bd80a26771d33`.
  The zero-network preflight is ready with no blockers. No live screening call,
  baseline rank, target-suite result, or superiority claim has been made.

- 2026-07-20: Hardened baseline evidence against retry laundering and artifact
  forgery. Completed and wrong answers cannot be retried; only transport or
  scorer failures can resume. Resume authenticates the campaign digest,
  schedule binding, safe unit aggregates, private unit content, output hashes,
  and official re-score before trusting a checkpoint. Ranking conversion
  independently re-scores all raw outputs and rejects private-output or safe-
  score tampering even when an attacker recomputes outer unit/state digests.
  Resume additionally binds execution mode, exact plan-file content, live
  credential readiness, private-root identity, and planned task count. It
  rejects preflight/live state mixing, endpoint drift, transport-cohort mixing,
  private-root drift, and forged task totals even when an outer digest is
  recomputed. The focused baseline/Hermes regression passes 28 tests and the
  full standalone regression passes 480 tests.

- 2026-07-20: Re-audited Hermes Agent MoA against NousResearch `hermes-agent`
  commit `e89bc58a5ba80ec6be19b43beca37cbb03091afd`. Axio retains parallel
  tool-free references, prompt-tail advisory injection, partial-reference
  tolerance, one acting Synthesizer, full acting-model tool loops, and the
  recursion guard. It now also projects prior tool actions and bounded tool
  result previews as inert text into the next reference wave across all four
  inbound protocols; native tool objects and schemas remain unavailable to
  references. Axio's mandatory Judge, one feedback/re-Judge round, diversity
  gates, provider failover, and 3x latency controls remain deliberate
  extensions rather than claims of source-code equivalence.

- 2026-07-19: Reconciled the post-Hermes evaluation state and moved the
  dominant phase to provider-baseline repair. The current calibrated cohort is
  45 live profiles grouped into 39 canonical models, while the previous
  external-ranking template still counted provider profiles. The template and
  freeze are being rebound to canonical groups so same-model replicas cannot
  inflate the ranking population. Engineering readiness remains trusted;
  baseline rank freeze and all 21-suite superiority claims remain unproven.

- 2026-07-19: Completed the full standalone Fusion regression after the
  Hermes MoA process-round, acting-aggregator tool admission, and bounded
  feedback re-Judge changes. The complete `PYTHONPATH=src ... pytest -q
  tests` suite passed 456 tests in 186.35 seconds; source compilation and
  whitespace checks passed, and the code-test/system-development receipts were
  refreshed. This proves standalone engineering readiness only. The separate
  9-category/21-suite live benchmark campaign, latency comparison, and all
  Axio-versus-single-model superiority claims remain unrun and unclaimed.

- 2026-07-19: Closed the provider-replica counting gap in the benchmark
  control plane. Baseline sorting, external-ranking inventory, freeze/census
  receipts, and formal candidate counts now operate on canonical model groups;
  replica counts and API/provider coverage remain separately auditable. Legacy
  `provider::<profile_hash>` candidate aliases still resolve to the entire
  canonical group. Benchmark provider calls use deterministic case-index
  rotation and bounded same-group failover, with hash-only selected-replica and
  attempt receipts. The current calibrated registry is 45 profiles, 39
  canonical groups, and 6 multi-replica groups. New standalone regression
  coverage is included in a passing 366-test run; this is engineering evidence,
  not a model-capability or superiority claim.

- 2026-07-19: Tightened the Hermes MoA process contract so the advisory wave
  can be enabled only when a Judge and a single Synthesizer are both admitted;
  disabled plans no longer claim that an aggregator owns the final answer.
  The standalone regression suite now passes 448 tests and the refreshed
  engineering readiness receipt remains separate from benchmark claims.
- 2026-07-19: Closed a parity gap between file-backed and process-local
  provider manifests. The dynamic four-protocol loader now resolves
  `models_env`/`modelsEnv` model lists, merges them with static rows using
  stable first-seen ordering, lets later duplicate rows override metadata, and
  accepts sequence-valued key pools from a secret resolver. Added validation
  and leakage regressions. The supplied three-channel portfolio was verified
  through the process-local `/models` path with 12 CPA Plus Responses models,
  119 NVIDIA Chat Completions models, and 9 TokenAPIs Responses models (140
  profiles, 132 canonical groups, 8 two-replica groups). No credentials were
  persisted and discovery is not treated as capability proof.

- 2026-07-19: Refreshed standalone engineering evidence after the dynamic
  manifest parity change: 432 tests passed, full source compilation passed,
  12/12 dry public protocol cells passed, all four provider input adapters
  remained ready, and the remote-only execution audit passed. System
  development remains ready for the separate benchmark-validation phase;
  benchmark scores, latency superiority, and model-superiority claims remain
  unmade.

- 2026-07-19: Added generation-fenced `refresh_runtime_channels` to the
  standalone HTTP runtime. Enrollment now builds a complete candidate with
  the currently active engine client and only atomically activates it after
  readiness validation; exceptions, incomplete candidates, and generation
  conflicts preserve the old engine. Added explicit native-tool capability
  states (`proven`, `unproven`, `failed`) and separate probe status so bounded
  sampling cannot turn absence of evidence into either a false failure or a
  false tool-specialist route. Full standalone verification now passes 430
  tests and compilation passes. This is engineering evidence only.

- 2026-07-19: Ran the latest calibrated private registry through the real
  local gateway with the three supplied channel families injected only into a
  one-shot process environment. Health/models checks were ready, and all 12
  public protocol cells (three Axio tiers x Chat Completions, Responses,
  Anthropic, and Gemini) returned valid response shapes. The result is API
  compatibility and transport evidence only; it is not a benchmark score,
  latency claim, or model-superiority claim.

- 2026-07-19: Added dynamic startup to the long-running CLI service. Operators
  can now select `--discover` or the live-only `--enroll` path with the same
  arbitrary provider manifest used by the process-local factory; enrollment
  admits only text-probed healthy profiles, optionally calibrates native tools,
  rejects unsafe registry mixing, and can write a hash/count-only receipt.
  Added CLI guard and receipt regression coverage. Standalone verification now
  passes 417 tests; no benchmark or model-superiority claim is made.

- 2026-07-19: Added an end-to-end gateway regression for arbitrary four-format
  runtime manifests. The test performs discovery, text health probing, native
  tool calibration, and live HTTP calls through Chat Completions, Responses,
  Anthropic Messages, and Gemini public routes, asserting each response shape
  without persisting endpoint values, credentials, prompts, or provider output.
  Standalone verification now passes 415 tests; this remains protocol and
  engineering evidence only, separate from benchmark capability claims.

- 2026-07-19: Hardened the process-local channel contract for arbitrary
  deployments. Runtime manifests now accept common `baseurl`, `apikey`,
  `protocol`, `channel`, and `model_id` aliases while retaining strict
  four-protocol validation; the shared model-row parser no longer drops
  `model_id` rows. `create_runtime_http_server(..., enroll=True)` now offers a
  bounded discovery -> text health probe -> native-tool probe path and serves
  only healthy in-memory profiles. Added four-protocol enrollment gateway
  coverage and refreshed standalone engineering evidence to 414 passing tests.
  No endpoint, credential, prompt, or provider output is persisted, and this
  remains engineering evidence rather than a benchmark superiority claim.

- 2026-07-19: Added the process-local generic channel configuration path for
  arbitrary base URLs, API keys, model-level overrides, multi-key pools, and
  all four upstream protocols. `FusionEngine.from_runtime_channels` can now
  construct the same runtime from a secret-manager-owned manifest without
  mutating environment variables; direct endpoint/key values remain in memory
  only and are excluded from safe profiles, registries, traces, and artifacts.
  Added four-protocol discovery/probe HTTP fixtures and corrected string
  boolean/privacy-tag parsing in generic model profiles. The three current
  channels were live-discovered in one bounded process: 12 CPA Plus models,
  119 NVIDIA models, and 9 TokenAPIs models, with no credentials persisted.
  A bounded one-model-per-provider text probe then selected three candidates;
  two returned the fixed health response and one failed, so the failure was
  retained as a serving diagnostic rather than promoted as usable evidence.
  Full standalone verification is now 408 passing tests. This is transport and
  engineering evidence only; benchmark superiority remains unclaimed.

- 2026-07-19: Completed the generic upstream authentication contract for
  public remote gateways. `auth_scheme: none` now works consistently through
  manifest validation, model discovery, credential readiness, provider POST
  transport, and all four adapter families without inventing a key or sending
  an authentication header. Bearer, `x-api-key`, `x-goog-api-key`, query-key,
  and multi-key rotation remain unchanged. Standalone verification is now 403
  tests, with system-development readiness refreshed separately from benchmark
  validation and superiority claims.

- 2026-07-19: Fixed a provider-configuration authority boundary. A custom
  manifest with only provider-level endpoint/credential references and no
  static or environment model list now yields an empty blocked registry until
  `/models` enrollment or an explicit calibrated registry is bound; an empty
  explicit registry no longer silently activates the portable development seed.
  Added secret-free CLI status and regression coverage. Full standalone
  verification now passes 399 tests, compilation passes, and refreshed 399
  system-development receipts remain separate from benchmark/superiority
  evidence.
- 2026-07-19: Completed the mechanical-disk acquisition of the official
  LiveBench 2026-06-25 test parquet files and leaderboard answer/judgment
  files, plus a commit-pinned official scorer/harness source archive. The
  snapshot contains 1,436 official test cases and is a non-target preparation
  artifact only; the current provider-pool baseline remains blocked because
  exact identity coverage is incomplete.
- 2026-07-19: Archived the public LMSYS/Chatbot Arena leaderboard as an
  independent human-preference source candidate and checked it with exact
  identity matching. Only 2/37 current canonical identities matched; no alias,
  effort suffix, provider prefix, or partial-name mapping was accepted, so the
  second-source baseline freeze remains correctly blocked.

- 2026-07-19: Bound each logical upstream provider turn to one shared deadline.
  Responses typed-input fallback and HTTP-success semantic empty-response retry
  now consume only the remaining turn budget; arbitrary Gemini channels honor
  their configured authentication scheme, including `x-goog-api-key`. Added a
  network-free `provider-config-summary` operator command and regression
  coverage, so arbitrary four-protocol manifests can be checked without
  printing URLs, aliases, credentials, or secrets.
- 2026-07-19: Downloaded dated LiveBench and SimpleBench non-target source
  snapshots plus the SimpleBench public question file to the mechanical-disk
  benchmark workspace. The source audit records content hashes and explicitly
  blocks baseline freezing because the public SimpleBench file has only 10
  labeled questions and the LiveBench table does not exactly cover all 43 live
  profiles. No fuzzy identity mapping or missing-row imputation was applied.
- 2026-07-19: Hardened the generic upstream response boundary for arbitrary
  provider gateways. Chat content-block lists, Responses output blocks,
  Anthropic content blocks, and Gemini parts now normalize to one protocol-
  neutral text result; HTTP-success responses with neither text nor a native
  tool call receive one bounded semantic retry and then enter the existing
  replica/fallback failure path. Standalone regression reached 393 passing
  tests. A fresh three-channel enrollment produced 43 live-available models,
  and three rounds of the 3-tier x 4-surface public live smoke passed 36/36.
  These are transport and engineering results only; no benchmark or
  superiority claim is made.
- 2026-07-19: Hardened generic provider-channel onboarding. The four upstream
  protocol families now validate strictly in provider manifests, so an unknown
  protocol spelling is rejected instead of silently becoming Chat Completions.
  Added an explicit outbound HTTP(S) proxy policy: operators can select an
  injected proxy or the local system proxy on port 10808 without writing proxy
  values to receipts. The standalone regression suite passes 391 tests; the
  four public protocol dry check remains 12/12 and the four upstream adapter
  check remains 4/4. This is engineering readiness evidence only, not a model
  capability or benchmark-superiority claim.
- 2026-07-19: Tightened external baseline freezing for multi-provider replicas. The rank 1/2/3 receipt now recomputes canonical cognitive-model identity hashes and rejects two provider replicas of the same model occupying different baseline ranks, while runtime routing continues to retain all healthy replicas for load balancing and failover. Standalone regression reached 389 passing tests.
- 2026-07-19: Fixed canonical model identity persistence across probe-generated and calibrated private serving registries. Private registries now retain the declared canonical value needed for same-model replica deduplication, load balancing, and evidence binding; safe registry evidence continues to retain only identity hashes. Added regression coverage and refreshed the standalone engineering receipt to 388 passing tests, with system-development readiness proven separately from benchmark superiority.
- 2026-07-19: Added file-backed provider configuration through `AXIO_FUSION_PROVIDER_CONFIG_FILE`; it loads the same arbitrary four-protocol schema as inline JSON, accepts only environment-variable names for transport and credentials, and projects source validity/counts without exposing paths, aliases, URLs, or secrets.
- 2026-07-19: Performed the first controlled live enrollment of the configured provider portfolio. Three provider directories were reachable, 141 candidates were discovered, and 40 models passed the fixed short health probe (26 Chat and 14 Responses). The private probe/registry artifacts remain operational-only; the aggregate result is not a capability or benchmark claim.
- 2026-07-19: Added bounded latency-constrained panel admission. When a score-first Fusion panel exceeds the hard 3x direct-route p50 guard, the planner holds the actual direct profile fixed, searches only bounded two/three-model panels, preserves Pro's Primary + Independent + Critic minimum, and promotes the highest-quality panel within the guard. If the current portfolio cannot retain provider diversity under that guard, the safe receipt records the relaxation instead of hiding it; no benchmark labels drive this decision.
- 2026-07-19: Revalidated the real 40-profile registry: ordinary Fast remains direct cascade, complex Terra completed the full Expert -> Judge -> Synthesizer shape at 1.57x, and complex Pro completed the five-role shape at 2.37x. These are engineering/orchestration and latency diagnostics only; no superiority claim was made.
- 2026-07-18: Added a hash-safe routing-policy observability and replay loop. Execution traces, feedback receipts, trace reports, learning reports, and shadow buckets now retain an allowlisted policy-version digest plus rule/control counts. `routing-policy-shadow-replay` replays only bounded candidate rule decisions over prompt-free traces and reports coverage, control deltas, and historical guard context. It performs zero provider calls and explicitly blocks any quality, latency, cost, or superiority conclusion without separately executed paired candidate evidence.
- 2026-07-18: Added a controlled remote-provider onboarding control plane and fixed disabled-profile admission at the router boundary. A new profile must remain `enabled: false`, pass protocol/live-probe/calibration/complementarity stages, become a hash-only shadow candidate, receive human approval, and then be activated only by writing a new private registry. Standard serving registry loads keep disabled profiles out, and the router independently excludes them before direct or panel selection. This is remote-API configuration control only, with no local weights, model deployment, or training.

- 2026-07-18: Hardened the Fast serial cascade timeout rule after the live direct-path diagnostics. It now reserves fallback time only when primary p50 plus the quickest distinct fallback p50 plus a 150 ms safety margin can fit in the same deadline; otherwise the primary retains its full bounded timeout and the safe receipt records the skipped reservation. This prevents an impossible fallback from silently reducing the best available direct attempt.
- 2026-07-18: Added a bounded public-live-smoke failure projection. A failed row now retains only allowlisted error-stage counts, profile-hash count, budget/deadline skip counts, strategy, and runtime degradation labels from the already-redacted gateway error summary. It never copies raw error text, provider/model identifiers, URLs, prompts, or provider outputs. The new regression explicitly injects private exception/prompt text and proves neither reaches the artifact.
- 2026-07-18: Refreshed standalone engineering evidence after the Fast timeout and smoke-observability change: 356 tests passed in 146.21 seconds; compilation and diff checks passed; the dry 12-cell public protocol check and four-format provider-input adapter check remained network-free and ready; and `fusion_system_development_readiness_356.safe.json` again proved engineering readiness for the separate 21-suite validation phase. No benchmark model call or superiority claim was made.
- 2026-07-18: Recorded current public live-smoke evidence without retry laundering. With the current four-profile registry, v4 was 11/12 (Fast Chat failure) and v5 was 10/12 (Fast and Terra Chat failures); the bounded Chat-profile diagnostic probe immediately afterward succeeded in 872.336 ms. This points to intermittent upstream availability rather than a confirmed public protocol-shape defect, but it is not a stable-SLO pass and remains an explicit engineering blocker.
- 2026-07-18: Performed a bounded external provider-identity and ranking-source scout before attempting a top-three freeze. OpenAI official model pages, NVIDIA's public organization model record, and the OpenRouter public catalog support plausible canonical identities for the current four profile hashes; Artificial Analysis is one common independent capability-source family. No second common, non-target ranking family with rank/population coverage for all four candidates was recovered, and a channel alias-to-version attestation is still absent. The private ranking template remains intentionally unfilled; no rank was inferred from alias names, registry priors, latency, or target-suite data.
- 2026-07-18: Rebound live-readiness to the current four-profile registry and current probe-evidence audit, proving the registry/probe binding with four live-available profiles while retaining blockers for external top-three ranking, gated access, and official harness outputs. A contention-free combined Terra/Pro smoke then completed Expert -> Judge -> Synthesizer for both tiers; intermittent public Fast surface failures and earlier deadline/contention failures remain preserved as diagnostics rather than being hidden by overwrite or retry.
- 2026-07-18: Corrected the Fusion latency baseline to the actual direct-route profile rather than the Fusion primary role. Added a stricter 2.5x operational headroom pass that may replace slow expert roles only when provider diversity is preserved and quality loss stays within a bounded tolerance, followed by Judge/Synthesizer stage optimization; Terra's admitted initial plans now receive a bounded 15-second network-tail deadline. Live non-benchmark smoke evidence recorded isolated complete paths for Terra and Pro, while back-to-back provider contention remains diagnostic rather than a capability claim.
- 2026-07-18: Replaced incomparable raw-rank averaging in external provider baseline selection with a complete-pool common-source normalized-percentile consensus. Every independent source now records its ranked population; the freeze requires at least two source families shared by every live candidate, stable source snapshot/population bindings, equal per-family weighting, hash-bound normalized summaries, and candidate-hash tie-breaking. Missing populations, inconsistent snapshots, duplicate family evidence, and incomplete common coverage block final-claim freezes.
- 2026-07-18: Made a supplied external top-three freeze an immutable formal-cohort boundary across benchmark matrix, acquisition checklist, and acquisition status generation. The formal cohort is now exactly 15 run units (three Axio tiers across four public API surfaces plus ranks 1/2/3); caller candidate filters and all-provider diagnostic expansion cannot reintroduce legacy internal baselines or expand official-harness imports beyond 90 rows. The standalone regression now has 343 passing tests; dry 12-cell public protocol and four-format provider-adapter checks, compilation, and system-development readiness all pass without network calls.
- 2026-07-17: Tightened the externally evidenced top-three freeze so every pre-registered rank must carry both an official and an independent non-target-benchmark general-capability source. The hash-only receipt now binds the per-rank evidence-class summaries, and final-audit validation rejects an aggregate-only evidence mix.

- 2026-07-17: Replaced the final-claim baseline rule with an externally evidenced, pre-registered configured-provider-pool top-three protocol. The complete live-probed provider pool remains visible only as a hash-bound census; `axio-pro`, `axio-terra`, and `axio-fast` are fixed to provider-pool ranks 1, 2, and 3 before any target-suite run. Historical exhaustive-baseline entries below describe legacy diagnostic artifacts and do not authorize final claims.
- 2026-07-18: Tightened external baseline selection to complete live-pool screening. Every live profile now needs two distinct independent non-target ranking sources with reported ranks; the system rejects manual top-three swaps and records only safe source/rank hashes. Public leaderboard disagreement is treated as a reason to aggregate and date-stamp evidence, not as permission to hard-code a supposedly universal order.
- 2026-07-18: Made formal benchmark artifact discovery cohort-first. Readiness now jointly selects one shared filename cohort across all eight required artifact kinds; when only independently newest files exist, it exposes them for diagnosis but blocks live readiness instead of silently mixing batches. Added regression coverage for multiple complete cohorts and intentionally mixed cohorts.
- 2026-07-18: Closed the benchmark-to-runtime calibration default path. `calibrate-registry` now blocks benchmark-derived capability updates unless `--allow-benchmark-calibration` is explicit, marks such updates exploratory-only, and refuses to write an updated registry on the blocked path. Probe, feedback, and transport telemetry calibration remain available without benchmark labels.
- 2026-07-18: Isolated benchmark scorecards from router learning. `learning-report` now blocks scorecard input unless `--allow-benchmark-diagnostics` is explicit; admitted scorecards remain diagnostic-only and cannot produce operational policy suggestions, registry updates, or automatic routing changes.

- 2026-07-15: Created standalone Fusion implementation and evaluation control plan for the 21-suite benchmark matrix.
- 2026-07-15: Added private benchmark materialization status/materialize commands; tightened the no-cheat route by treating IFEval final scoring as official/audited harness import rather than simplified local checks, and refined answer-leakage detection to avoid BBH false positives from natural answer tokens in problem text.
- 2026-07-15: Added a hard Fusion admission latency guard that blocks known p50 Fusion estimates above 3x the direct single-model route before execution.
- 2026-07-15: Added suite-aware benchmark minimum-case gates so fixed small full-suite benchmarks such as AIME Recent can pass with their complete 30-case slice while larger suites keep the default campaign minimum.
- 2026-07-15: Added Sakana-style hash-only quality-diversity niche archives and OpenRouter-style provider routing policies to route plans, prompt context, and safe traces; adjusted `axio-fast` default cost ceiling to `0.001` USD so enriched safe routing context does not block ordinary low-price single-model calls.
- 2026-07-15: Added `benchmark-harness-pin-manifest` and generated a safe mechanical-disk pin manifest for LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style judging with official repo commits, evaluator hashes, prompt/decoding hashes, and dataset snapshot hashes.
- 2026-07-15: Added `benchmark-source-manifest-prepare`; the real prepared source manifest now validates 13/21 suites, with the remaining 8 blocked only by missing materialized case hashes for GPQA, FLORES, and official/audited import suites.
- 2026-07-15: Extended `benchmark-import-batch-template` to consume harness pin manifests; generated a pinned official import batch template with 144/144 official import rows prefilled for harness identity, dataset snapshot, evaluator, prompt, and decoding hashes.
- 2026-07-15: Added configuration-driven `fusion-live-readiness` preflight and generic live probe defaulting; provider configs now drive arbitrary channel/API-format inputs, while AISZ/CPA Plus/NVIDIA remain optional convenience seeds only.
- 2026-07-15: Extended provider config parsing to support per-model API format, env-var, capability, cost, latency, context, tool, vision, and privacy overrides within arbitrary provider channels.
- 2026-07-15: Extended live `/models` discovery so generated probe registries inherit matching per-model config overrides instead of only provider-level defaults.
- 2026-07-15: Added generic Gemini-compatible convention seed and four-interface live discovery coverage so arbitrary provider inputs can span Chat Completions, Responses, Anthropic Messages, and Gemini.
- 2026-07-15: Normalized Gemini-compatible model resource names so `/models` responses like `models/gemini-*` call `:generateContent` without duplicated `/models/models/` paths.
- 2026-07-15: Added `benchmark-official-harness-execution-plan` and wired it into `fusion-live-readiness`, so the 6 official/audited harness suites now have a hash-only execution work plan before model-output import.
- 2026-07-15: Upgraded Synthesizer candidate selection from plain rank-first top-N compression to rank-first, diversity-aware selection that preserves evidence-backed critic/domain/minority insights while keeping low-ranked noise hash-only.
- 2026-07-15: Connected runtime fallback execution to the hash-only provider routing pool. Default routes now reserve one bounded fallback call when the user has not supplied a tighter call cap, and fallback ordering combines availability, role-fit quality, latency, cost, provider diversity, and API-format diversity.
- 2026-07-15: Added final claim-audit latency gating: even statistically significant Axio score wins are rejected when the relevant Axio tier exceeds 3x the same-suite target provider baseline latency.
- 2026-07-15: Added `benchmark-fusion-failure-analysis`, a safe shadow-only optimization campaign artifact that diagnoses evidence gaps, API-surface parity failures, score/statistical failures, and 3x latency failures, then emits bounded ablation variants without auto-applying benchmark-tuned policy.
- 2026-07-15: Added `provider-portfolio-audit`, a hash-only readiness audit for arbitrary provider/model pools that checks baseline tiers, Fusion role coverage, provider/API diversity, fast-path capacity, metadata completeness, and 9-category capability coverage without depending on any named channel.
- 2026-07-15: Added `fusion-live-runbook`, a safe command-template artifact for provider probing, generated registry creation, portfolio audit, official harness imports, live 21-suite campaign, final audit, evidence pack, and shadow failure analysis while keeping provider details, env names, paths, and secrets out of shareable JSON.
- 2026-07-15: Connected the learning loop to safe provider routing fallback receipts. Router training examples and shadow policy patches now consume fallback availability, routing score, non-panel candidate, API-format diversity, and live-probe refresh signals without persisting provider names, model names, URLs, prompts, or secrets.
- 2026-07-15: Extended trace reports and benchmark failure analysis with aggregate provider fallback health. Failed benchmark campaigns can now emit a shadow-only provider fallback refresh ablation when safe traces show weak availability, poor routing score, insufficient non-panel fallback candidates, or narrow API-format diversity.
- 2026-07-15: Added `benchmark-campaign-progress-plan`, a hash-only resume/repair artifact for long live campaigns. It compares the pre-registered suite/run-unit/API-surface/provider-baseline matrix with existing run files, flags missing or invalid artifacts, and emits safe resume command templates without storing raw run paths, dataset paths, provider model ids, prompts, labels, outputs, or secrets.
- 2026-07-15: Added `benchmark-api-surface-parity`, an operator-facing hash-only report that verifies every Axio suite/model cell has Chat Completions, Responses, Anthropic Messages, and Gemini runs over identical case hashes, prompt protocol hashes, and decoding hashes, with cross-surface score deltas inside tolerance.
- 2026-07-15: Added `benchmark-provider-baseline-freeze`, a hash-only pre-campaign baseline universe lock. Final audit now requires the freeze digest to bind campaign, run, scorecard, and claim artifacts so provider baselines cannot be swapped after the live campaign starts.
- 2026-07-15: Added `provider-probe-evidence-audit`, a hash-only gate that binds private live probe files, the private generated registry, redacted probe evidence, and redacted registry evidence through path hashes, profile-set hashes, source counts, redaction checks, and leakage checks before provider baselines are frozen.
- 2026-07-15: Wired provider probe evidence audit into `benchmark-final-audit` and `benchmark-evidence-pack`; final completion is now blocked when the probe-derived registry hash does not match campaign and freeze registry receipts.
- 2026-07-16: Bound `benchmark-provider-baseline-freeze` itself to `provider-probe-evidence-audit`; the freeze digest now includes the audit receipt and final audit rejects freezes whose embedded probe evidence receipt is absent, unready, or registry-hash mismatched.
- 2026-07-16: Wired `provider-probe-evidence-audit` into `benchmark-campaign`; live campaigns now copy the hash-only safe audit into the campaign directory and generate the campaign-local provider baseline freeze from that same registry-bound evidence chain.
- 2026-07-16: Added bounded `axio-fast` light verification. Simple fast requests still use direct cascade, but high-quality, high-risk, uncertain, or tool-planning fast requests can admit a two-model verify route under the same 3x latency guard, improving the fast tier's chance of beating the third strongest provider baseline without becoming a heavy panel.
- 2026-07-16: Added local Judge answer-claim clustering for provider-judge-skipped paths. Equivalent final answers with different wording now form hash-only support clusters, which boosts independently supported conclusions and reduces false contradiction/escalation decisions without persisting raw candidate text.
- 2026-07-16: Redacted the operator route-plan API into a hash-only safe view so external callers can inspect strategy, budgets, roles, and routing receipts without receiving raw provider names, model ids, profile ids, URLs, prompts, or secrets.
- 2026-07-16: Tightened provider decoding compatibility by forwarding top-p, stop sequences, and max-output limits to Anthropic Messages and Gemini-compatible inputs, aligning provider calls with benchmark decoding controls across API formats.
- 2026-07-16: Fed bounded `axio-fast` light-verify activation and local Judge answer-claim cluster receipts into orchestrator training examples and router-policy shadow patches. Failed fast direct buckets can now propose latency-guarded light verification, and weak/contradictory answer-claim buckets can propose independent claim verification without applying benchmark-tuned policy automatically.
- 2026-07-16: Added `benchmark-official-import-audit`, a hash-only pre-campaign gate for LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style official/audited imports. It reuses final-audit alignment logic to catch missing run units, case-set drift, prompt/decoding mismatch, harness receipt tampering, case-hash source mismatch, and harness-pin mismatch before the live campaign.
- 2026-07-16: Wired `benchmark-official-import-audit` into `fusion-live-readiness` and `fusion-live-runbook`; live campaigns are now blocked until the official/audited import audit artifact is present, valid, hash-only, and ready.
- 2026-07-16: Wired `benchmark-official-import-audit` into `benchmark-final-audit` and `benchmark-evidence-pack`; final claims are now blocked unless the official import audit run-set digest matches the campaign's official/audited harness runs.
- 2026-07-16: Wired `benchmark-api-surface-parity` into `benchmark-final-audit` and `benchmark-evidence-pack`; final claims are now blocked unless the four-surface parity report is bound to the same campaign run set and matches the recomputed parity audit.
- 2026-07-16: Promoted factuality and vertical-domain routing signals into runtime DAG nodes, prompt answer policy, local Judge coverage checks, targeted escalation focus, safe trace coverage summaries, and shadow-only learning patches for source-grounding and domain-guardrail failures.
- 2026-07-16: Removed the last provider endpoint fallback from the HTTP client. Every live provider profile now requires an explicitly configured base-URL environment variable; gateway health, discovery, and evaluation readiness share that rule, and missing configuration is rejected before network access without exposing env names, URLs, or keys.
- 2026-07-16: Added model-scoped arbitrary-provider topology. A configured channel may omit provider-level credentials when each listed model carries its own endpoint, API key environment variable, and input protocol; those models join the static registry and direct probe path without a speculative provider-level `/models` request.
- 2026-07-16: Aligned the initial Fusion latency estimate, call budget, and executor concurrency. The bounded initial expert set now uses up to four concurrent role slots (primary, independent, critic, domain specialist), while Judge and Synthesizer remain sequentially included in the conservative 3x admission estimate. Added a regression proving that a selected but unassigned extreme-cost/extreme-latency spare cannot change initial Fusion cost, latency, utility, or admission.
- 2026-07-16: Aligned initial route-cost admission estimates with runtime output reservations: explicit `max_output_tokens` now governs every initial role, and otherwise expert/Judge/Synthesizer use the same bounded defaults as the executor. Refreshed standalone engineering evidence: 251 standalone tests passed; dry public protocol self-test covered all 3 Axio tiers x 4 API surfaces; dry provider-input self-test covered Chat, Responses, Anthropic, and Gemini; the refreshed system-development readiness receipt is ready for the separate 21-suite benchmark-validation phase and makes no model-superiority claim.
- 2026-07-16: Added `--strict-live-preflight` for formal live benchmark campaigns. When enabled, campaign execution stops before any model calls unless 21-suite readiness, live-probe registry proof, provider probe evidence audit, a valid provider baseline freeze, and its registry receipts are ready; blocked runs still emit safe hash-only campaign artifacts for audit and repair, and unsafe/incorrect probe evidence JSON is not copied into campaign outputs.
- 2026-07-16: Added `api-surface-protocol-self-test`, a dry hash-only gateway self-test for `axio-fast`, `axio-terra`, and `axio-pro` across Chat Completions, Responses, Anthropic Messages, and Gemini-compatible entrypoints. It checks response shapes, public model mapping, usage metadata, and route-summary consistency before the live 21-suite campaign.
- 2026-07-16: Added practical effect-size gates and Wilson 95% confidence interval summaries to benchmark claim audit, methodology, final audit proof contracts, and shadow failure-analysis success criteria so tiny but statistically significant score differences cannot authorize superiority claims.
- 2026-07-16: Upgraded final claim latency gating from a single fallback latency metric to strict p50+p95 case-latency gates. Scorecard, claim audit, final audit, replay signatures, and failure-analysis reason families now all expose and enforce both distribution points while retaining the legacy max latency multiplier field for compatibility.
- 2026-07-16: Added `fusion-completion-audit`, a hash-only top-level completion matrix. It consumes evidence pack, final audit, API-surface protocol self-test, and live runbook artifacts, then proves or blocks each standalone Fusion API goal requirement without storing raw paths, provider identifiers, prompts, labels, outputs, or secrets.
- 2026-07-16: Added `provider-input-adapter-self-test`, a dry hash-only provider-side input conformance check for Chat Completions, Responses, Anthropic Messages, and Gemini-compatible transports. The live runbook now schedules it before formal campaigns, and the top-level completion audit requires the self-test receipt before marking the provider-input layer complete.
- 2026-07-16: Strengthened local Judge answer-claim clustering with exact numeric-equivalence normalization for fractions, decimals, and percentages. Safe traces and learning features now expose only the equivalence type, reducing false contradiction/escalation signals on math and logic tasks when provider Judge calls are skipped by budget.
- 2026-07-16: Connected early-exit decisions to hash-only answer-claim consensus. When the Judge is ready, coverage has no blockers, evidence exists, and multiple candidates support the same normalized claim, Axio can skip a synthesis call even if answer wording has low token overlap; safe traces and learning features record only support counts, support fractions, hashes, and equivalence types.
- 2026-07-16: Added local Judge confidence calibration. Candidate ranking now uses calibrated confidence that discounts unsupported high-confidence answers, missing evidence/reasoning, ungrounded factuality claims, and missing vertical guardrails while safely exposing only numeric calibration receipts to traces and shadow learning.
- 2026-07-16: Routed calibrated confidence into early-exit and quality-target gap decisions. Axio now blocks synthesis skipping or triggers targeted quality repair when the best candidate's safe calibrated confidence falls below the tier threshold, while retaining raw confidence only as an audit field.
- 2026-07-16: Added independence-aware answer-claim consensus. Claim clusters now record hash-only unique profile/provider support, and early-exit requires independent profile support plus cross-provider support whenever the candidate pool spans multiple providers.
- 2026-07-16: Promoted answer-claim independence gaps into local Judge diagnostics. Same-provider or same-profile answer-claim agreement now creates explicit missing coverage, contradiction, and targeted follow-up receipts so Fusion can repair contested consensus instead of merely refusing early-exit.
- 2026-07-16: Routed answer-claim independence gaps into targeted escalation execution. Escalation plans now carry hash-only independence requirements, verifier model selection prefers new-profile/cross-provider support when required, targeted prompts demand evidence-backed verification instead of restatement, synthesis treats same-source consensus as unverified, and shadow learning can distinguish failed independent-verifier routing from generic low consensus.
- 2026-07-16: Added provider-portfolio independent verification capacity audit. Arbitrary provider pools are now checked for hash-only answer-claim verifier candidates, new-profile and cross-provider verifier readiness, live-probe evidence, pricing/context metadata, runbook visibility, and final-claim blocking warnings before expensive live benchmark campaigns.
- 2026-07-16: Promoted provider-portfolio independent verification into registry and live-readiness final-claim gates. Benchmark readiness, strict live preflight, and fusion-live-readiness now block final campaigns when the generated live registry cannot prove cross-provider answer-claim verifier capacity, even if basic registry readiness flags are present.
- 2026-07-16: Bound provider-portfolio independent verification into `benchmark-provider-baseline-freeze` and `benchmark-final-audit`. Baseline freeze digests and receipts now include hash-only portfolio/verifier capacity evidence, and final completion is blocked when the frozen provider universe lacks cross-provider answer-claim verifier readiness.
- 2026-07-16: Promoted provider-portfolio independent verifier capacity into `fusion-completion-audit` as a first-class top-level requirement. The final completion matrix now reports and blocks missing cross-provider verifier readiness directly instead of relying only on the provider baseline freeze gate.
- 2026-07-16: Promoted the 21-suite x 3-tier claim comparison family into `fusion-completion-audit` as an explicit top-level gate. Completion now requires the exact suite-tier comparison count, covered-suite count, Holm-Bonferroni family size, and claim correction family to match before final success can be reported.
- 2026-07-16: Bound `benchmark-evidence-pack` to the current `benchmark-final-audit` inside `fusion-completion-audit`. The top-level completion matrix now rejects stale or mismatched evidence packs whose embedded final-audit summary, final completion flag, readiness level, or missing-requirement digest does not match the final audit being used.
- 2026-07-16: Strengthened `fusion-live-runbook` as an auditable operations contract. Runbooks now declare evidence-pack/final-audit binding, 21-suite x 3-tier claim-family coverage, and cross-provider independent verifier requirements; `fusion-completion-audit` rejects stale runbooks that omit these gates.
- 2026-07-16: Promoted the shadow-only benchmark failure-analysis loop into `fusion-completion-audit`. Completion now requires a safe `benchmark-fusion-failure-analysis` artifact with no automatic policy application, 21-suite success criteria, replay/holdout ablation gates, and clean anti-leakage flags; the live runbook passes it explicitly to the final completion audit.
- 2026-07-22: Closed the pre-Fusion automatic discovery handoff. A configured provider manifest now returns the complete `/models` inventory as process-local profiles for research ranking and strict streaming screening; failed/empty discovery without static fallback blocks both downstream stages. Added hash-only discovery receipts, model-id redaction coverage, and explicit invalidation of pre-operational-ranking historical artifacts.
- 2026-07-22: Retained the historical operational-v1 live pre-Fusion run as
  diagnostics only: 139/139 discovered profiles, 35/35 strict research
  batches validated, 139/139 physical stream probes, 36 admitted, 19 rejected
  by the 90-second ceiling, and 0 ordinary-JSON fallbacks promoted. It is
  superseded by the capability-axis v6 handoff above and cannot be treated as
  the current serving registry.
- 2026-07-16: Reordered `fusion-live-runbook` manifest stages so official/audited import audit runs only after dataset manifest assembly, case-hash manifest generation, and source-manifest case-hash binding, then before benchmark readiness.
- 2026-07-16: Added source-manifest preparation to the live runbook manifest stage. Operators now generate the hash-filled prepared source manifest from the source template, case-hash manifest, and harness pins before binding case hashes and running official import audit.
- 2026-07-16: Extended strict live campaign preflight to require source-manifest validation, case-hash/source digest binding, and official import audit readiness before the campaign run loop can call providers; blocked campaigns now include hash-only receipts for these gates.
- 2026-07-16: Extended strict live campaign preflight to require API-surface protocol and provider-input-adapter self-test receipts before provider calls, so the four public Axio API surfaces and four provider input formats are proven before live benchmark spend.
- 2026-07-16: Strengthened `fusion-completion-audit` to validate live-runbook command templates, not just declared gates. Completion now rejects stale runbooks whose campaign command omits strict preflight/source/case/official-import/protocol/adapter evidence, whose manifest commands are missing or out of order, or whose final completion command omits shadow failure analysis.
- 2026-07-16: Added primary evidence recomputation binding to `fusion-completion-audit`. Formal completion now requires the loaded evidence pack and final audit to match artifacts recomputed from the registry, source manifest, case-hash manifest, provider probe evidence audit, provider baseline freeze, official import audit, API-surface parity report, dataset manifest, and campaign directory; the live runbook now passes those primary evidence paths into the final completion audit command.
- 2026-07-16: Tightened `fusion-completion-audit` provider input conformance so a valid `provider-input-adapter-self-test` artifact is required. Runtime registry inference can generate that artifact, but it can no longer substitute for a persisted hash-only self-test receipt at final completion.
- 2026-07-16: Tightened `fusion-completion-audit` public API protocol conformance with row-level and model-level checks. Completion now rejects tampered or incomplete API-surface protocol artifacts with missing surfaces, incomplete 3-model x 4-surface coverage, failed rows, route inconsistency, missing answer/route digests, or forbidden persistence flags.
- 2026-07-16: Added `fusion-code-test-receipt` and `fusion-system-readiness` as a separate engineering-readiness gate before benchmark validation. This proves standalone code tests, dry public API protocol checks, provider input adapter conformance, runtime construction, and live-runbook templates are ready, while explicitly not claiming benchmark completion or model superiority.
- 2026-07-16: Wired `fusion-system-readiness` into the live operator runbook before the formal 21-suite campaign. The runbook now emits a code-test receipt and system-development readiness artifact after dry protocol/adapter self-tests and before any benchmark campaign execution.
- 2026-07-16: Bound `fusion-system-readiness` into `benchmark-campaign --strict-live-preflight`; formal live campaigns now require a persisted system-development readiness receipt before the run loop can call providers, even if the campaign is launched outside the runbook.
- 2026-07-16: Promoted `fusion-system-readiness` into `fusion-completion-audit` as a final evidence requirement. Completion now requires the persisted engineering-readiness receipt and the live runbook's final completion command must pass it explicitly.
- 2026-07-16: Tightened strict live campaign preflight with explicit provider-portfolio and independent-verifier blockers from the provider baseline freeze receipt. Single-provider baseline universes are now blocked before model calls with precise cross-provider verifier and provider-diversity reason codes.
- 2026-07-16: Bound provider probe live-evidence summaries into provider baseline freeze receipts. Freeze and strict-live preflight now expose and check private-probe live available counts, probe mode counts, and private-registry live-readiness flags instead of relying only on a generic audit-ready boolean.
- 2026-07-16: Moved the standalone regression suite under `axio_fusion_api/tests/` and documented the repository boundary so implementation, tests, package metadata, plans, and operator documentation remain in one ASciFS-decoupled workspace.
- 2026-07-16: Hardened provider probe evidence integrity. The audit digest now covers live-count/mode/profile-set/registry-readiness summaries; freeze receipts recompute and verify that digest; final audit and completion audit require the minimum live probe count, live mode evidence, live profile-set digest, and live registry readiness to remain bound across audit, freeze, campaign, and evidence-pack artifacts.
- 2026-07-16: Added the official FLORES-200 `devtest` materialization adapter with a fixed pre-registered 100-case slice: five English-linked language pairs, both directions, and the first ten aligned sentences per direction. The adapter keeps references out of model prompts and keeps raw text out of safe receipts.
- 2026-07-16: Refined provider baseline freeze gating so verifier pricing/context metadata gaps remain warnings when cross-provider, new-profile, and live-evidence capacity are already ready; only actual verifier-capacity or provider-diversity failures block final-claim freeze. The current v2 freeze selects all 37 live provider baselines.
- 2026-07-16: Rebuilt the 21-suite dataset/case/source evidence chain after FLORES adapter completion: 14 suites are case-hash/source ready, GPQA remains gated, and six official/audited suites remain blocked until their 294 real imported run receipts are supplied.
- 2026-07-16: Refreshed engineering readiness evidence with 225 standalone tests, four public API surface checks, four provider input adapter checks, and a current executable live runbook; benchmark validation remains a separate evidence phase.
- 2026-07-16: Refreshed live provider evidence with the current CPA Plus Responses-compatible channel and NVIDIA Chat Completions-compatible channel. `/models` discovery found 131 exposed models, strict short-prompt probing admitted 37 live provider baselines across 2 providers and 2 input formats, and the v2 provider probe evidence audit plus a legacy exhaustive diagnostic freeze were ready without persisting API keys, raw provider URLs, prompts, labels, or provider outputs. This historical freeze is superseded for final claims by the 2026-07-17 configured-provider-pool top-three protocol.
- 2026-07-16: Re-ran strict live benchmark preflight against the v2 provider registry and freeze. The campaign stayed in `live_preflight_blocked` mode with `provider_call_count=0` and `network_calls_performed=false`; provider evidence, legacy exhaustive diagnostic selection, and cross-provider verifier capacity passed, while final benchmark execution remained blocked by suite readiness, GPQA gated access, and missing official/audited harness imports. This historical result is not valid final-claim evidence under the configured-provider-pool top-three protocol.
- 2026-07-16: Re-ran the standalone Fusion regression after the v2 provider evidence refresh: 225 tests passed, `compileall` passed, `git diff --check` passed for `axio_fusion_api`, and the standalone source tree still has no `import axio` or `from axio` dependency.
- 2026-07-16: Audited the formal v4 acquisition queue against the v2 provider registry and freeze. It is aligned to 40 candidates (3 public Axio tiers plus 37 opaque provider aliases), 49 run units (12 Axio API-surface units plus 37 provider units), 21 suites, and 1,029 campaign cells. All examined safe artifacts are free of API-key-like strings, provider URLs, raw prompts, and legacy internal benchmark baselines; strict preflight remains correctly blocked before provider calls until GPQA access and the 294 official/audited harness receipts exist.
- 2026-07-16: Added stable, hash-only official source parsers for LiveCodeBench code-generation questions, the complete BFCL v3 category set, tau-bench retail/airline test-task indices, and MT-Bench question ids. The parsers read only case identity metadata, retain official harness scoring requirements, and use static AST inspection for tau-bench rather than importing its task source.
- 2026-07-16: Registered MT-Bench's fixed complete 80-question, two-turn corpus as a valid suite-size exception. Rebuilt the mechanical-disk case/source evidence chain: 20/21 suite case hashes and source bindings are ready, including 182 LiveCodeBench, 2,631 BFCL, 165 tau-bench, and 80 MT-Bench cases. GPQA Diamond remains explicitly blocked by authorized dataset access; no live benchmark model calls or official scoring imports were performed.
- 2026-07-16: Re-ran standalone Fusion regression after the official-source binding work: 235 tests passed. The new source parser tests verify category-scoped BFCL ids, LiveCodeBench question-level deduplication, tau-bench AST-only parsing, MT-Bench's fixed-size policy, and hash-only artifact redaction.
- 2026-07-16: Added `api-surface-live-smoke`, an explicitly opt-in bounded service-plumbing check for all three public Axio tiers across Chat Completions, Responses, Anthropic Messages, and Gemini. It uses a credential-filtered private registry, permits one primary call plus at most one bounded direct-cascade fallback, disables cache and durable trace writes, and emits only safe response hashes, timing, status, and redacted route receipts. It is deliberately not a benchmark, does not rank provider baselines, and cannot support a quality or superiority claim.
- 2026-07-16: Corrected Fusion admission p50 latency estimation to include every queued expert wave when the selected panel exceeds the runtime parallel-worker limit. The known-latency 3x guard now blocks a panel before execution when its full expert phase plus Judge and Synthesizer estimate exceeds the direct-route multiplier; a four-expert/two-worker regression covers the behavior.
- 2026-07-16: Added initial Fusion call-budget admission as a separate pre-execution gate. A Fusion route now reserves its minimum independent expert candidates plus Judge and Synthesizer before activation; a caller ceiling below that complete floor falls back to the tier's direct path, while a ceiling that can complete the loop trims optional expert roles before it can remove Judge or Synthesizer. High-quality `axio-pro` requests require three candidate branches plus Judge and Synthesizer, so a four-call ceiling is rejected and a five-call ceiling is the first admissible complete plan. The public four-surface route summary, prompt-safe context, hash-only execution trace, and shadow-learning features carry the same safe budget receipt without provider identity leakage.
- 2026-07-16: Refreshed standalone engineering evidence after the complete-call-budget admission regressions: 256 standalone tests passed, the dry public protocol self-test covered all 12 tier/surface cells, the dry provider-input adapter self-test remained ready for all four provider formats, and the refreshed system-development readiness receipt remains ready only for the separate 21-suite benchmark-validation phase. No provider network calls or model-superiority claims were made by this refresh.
- 2026-07-16: Made the runtime executor honor the initial complete-Fusion reservation contract. Required Judge and Synthesizer slots are now retained through expert execution, while optional repair, fallback, and targeted-escalation work is bounded so it cannot consume those committed calls.
- 2026-07-16: Added explicit, hash-only runtime finalization outcomes for complete Fusion, reduced-panel Fusion, single-candidate degraded responses, deferred native tool-call turns, and provider execution failure before finalization. Zero-candidate recovery now releases impossible reservations before a bounded fallback attempt and never labels recovered output as complete Fusion; early tool returns and total provider failure settle unused reservations safely.
- 2026-07-16: Kept independently produced but text-identical candidates available to the Judge even when synthesis-side answer compression collapses duplicate wording, preserving independent support and arbitration evidence without storing raw candidate text in safe traces.
- 2026-07-16: Refreshed standalone engineering evidence after runtime reservation/finalization hardening: 260 tests passed, all 12 dry public API protocol cells passed, all four dry provider input adapters passed, and refreshed hash-only code-test, runbook, and system-development readiness receipts were generated. This proves engineering readiness only; formal 21-suite benchmark validation and any Axio-versus-single-model superiority claim remain pending authorized GPQA access and official/audited harness outputs.
- 2026-07-16: Added route-time initial Fusion resource admission. Before activating a complete expert/Judge/Synthesizer plan, the router now prices and estimates the p50 latency of the exact assigned initial roles; known cost above `max_cost_usd` or known latency above `max_latency_ms` degrades to the tier's direct path before any provider call. Unknown telemetry remains non-blocking and is recorded for runtime cost/deadline locks rather than fabricated as a rejection. The safe receipt propagates through four public API summaries, operator route-plan output, prompt context, hash-only traces, and shadow-learning features.
- 2026-07-16: Extended the independent regression evidence for initial resource admission: learning-dataset fixtures now verify all six safe cost/latency feasibility features, and the operator route-plan test verifies blocked cost/latency receipts retain only hashes and never expose provider/model identifiers. The upcoming engineering receipt is explicitly limited to code/protocol readiness; it is not a 21-suite result or a model-superiority claim.
- 2026-07-16: Extended the HumanEval/IFEval official-harness bridge to execute frozen single-provider baselines directly from opaque `provider::<sha256>` aliases. Provider runs now require a private registry plus an integrity-checked baseline-freeze manifest, use the provider's native input adapter with deterministic generation controls, and record only hash-safe candidate/protocol bindings. Evaluation rejects candidate, registry, profile, output-token, protocol, metadata, or case-set drift, so Axio and provider samples can be paired through the same private source cases and official scorer without leaking provider identifiers or benchmark content.
- 2026-07-16: Added a dedicated HumanEval/IFEval official-harness import bridge. It promotes a completed private evaluation directory into an `official_harness_import` run without manual transcription of candidate, source, harness, prompt, or decoding fields. Before import it verifies the integrity-bound evaluation receipt, generation binding and metadata, official pin hashes, deterministic protocol, full case-set alignment, per-case output hashes, and provider baseline-freeze binding where applicable; no model or evaluator call is made during import. The bridge is covered for Axio, frozen provider baselines, CLI output, and scored-row drift rejection.
- 2026-07-17: Extended the receipt-bound official bridge to LiveCodeBench code generation. The bridge reads the pinned local `test_generation.parquet`, reproduces the official Generic system/user prompt and last-code-fence extraction protocol, reconstructs official `input_output` records, and invokes the pinned `codegen_metrics`/`testing_util` evaluator only after explicit unsafe-code authorization. Private evaluator results contain only question ids, prediction/output hashes, official pass booleans, and syntax-only compile booleans; normalization binds every hash to generation metadata before importing official `pass@1`, while `compile_rate` remains secondary instrumentation. Regression coverage includes CLI support, subset handling, private-result leakage checks, evaluator-output substitution rejection, scored-row tamper rejection, and the no-ASciFS-import boundary. Real model-output evaluation remains pending and is not implied by these engineering tests.
- 2026-07-17: Added the receipt-bound MT-Bench pairwise bridge. It generates fixed two-turn Axio and provider-native comparison samples privately, includes the first assistant turn before the second user turn, selects the official ordinary/reference-answer judge templates by category, calls the judge in both A/B and B/A positions, scores positional disagreement as a tie, and rejects unparsable judge outputs instead of fabricating scores. Target and comparison generation bindings, pair bindings, judge receipts, scored rows, and imports are cross-validated against the same case set, prompt protocol, deterministic decoding, candidate registry, and harness pin. The bridge is covered across Chat Completions, Responses, Anthropic Messages, and Gemini-compatible public Axio surfaces with tamper and leakage rejection tests.
- 2026-07-17: Corrected Gemini-compatible request canonicalization so `generationConfig.temperature: 0` remains deterministic, and removed falsy-value loss for top-p precedence. The standalone suite now has 285 passing tests and compilation passes. The refreshed mechanical-disk official harness pin has all six official/audited bridge suites ready; the current MT-Bench preflight is ready for 80 cases with two judge calls per case, position balancing, cross-provider judge separation, zero model calls, and hash-only receipts. Real model-output scoring and final superiority claims remain pending the separate live campaign.
- 2026-07-17: Added a resumable official-harness campaign driver. It resolves the frozen Axio/API-surface and provider-profile task matrix only in private process state, checkpoints a hash-only receipt after each task, reuses valid imports on restart, and runs preflight/generation/evaluation/import through the existing six receipt-bound bridges. The driver supports bounded task slices, explicit failed-task retries, isolated code-execution authorization, and deterministic MT-Bench independent comparison/judge selection from configured or frozen profile pools. This adds execution control only; it does not create model-output evidence or change the remaining live-campaign gates.
- 2026-07-17: Hardened the Fast direct cascade after a real four-surface smoke exposed a slow Responses primary and an unreachable fallback window. The router now rejects known p50-slow Fast primaries when a deadline-feasible alternative exists, requires a primary-plus-distinct-fallback p50 plan with a small safety margin when a fallback call is admitted, and reserves part of the primary timeout for that fallback. The live smoke now exercises the same one-primary-plus-one-fallback envelope. Standalone regression reached 290 tests after the added route and timeout regressions; a fresh private 12-cell live smoke passed across all three Axio tiers and all four public API formats. This remains plumbing evidence only, not a benchmark or superiority result.
- 2026-07-17: Rebuilt the formal source-manifest chain against the current six-suite harness pin. The 20 available source/case bindings now validate cleanly; GPQA Diamond remains the only source-access blocker. The formal official-import audit is aligned to 40 logical candidates, 49 run units, and 294 required imports, and reports only the 294 missing real harness receipts rather than stale pin mismatches.
- 2026-07-17: Hardened public metadata and provider compatibility. Gateway canonicalization now strips caller-supplied private `_axio_*` markers, cache keys bind exact stop-sequence and routing-contract hashes, and the Responses text-input fallback refuses turns that would drop native tool declarations or prior tool context. Standalone regression reached 294 passing tests; dry protocol and input-adapter receipts remain engineering evidence only.
- 2026-07-17: Added `fusion-deliberation-live-smoke`, a separate opt-in bounded operator probe for the complete `axio-terra`/`axio-pro` Fusion path. It uses one synthetic non-benchmark task, requires Fusion admission, multiple completed candidate branches, a provider Judge call, and provider finalization; its original generic contract permitted a controlled early exit, while the current Hermes-aware revision requires the acting Synthesizer whenever Hermes is enabled. It disables cache and durable trace writes and emits only hash-safe counts, timing, route digests, and error codes. Fake-client regression also caught and corrected the cross-module public-route-summary boundary. This is orchestration evidence only; no real provider invocation, benchmark score, latency claim, or model-superiority claim is implied.
- 2026-07-17: Separated standalone HTTP server construction from the blocking service loop so integrations and regressions can manage a clean lifecycle. The new loopback regression binds a temporary local socket, verifies all four public protocol families through real HTTP transport without provider network calls, checks metadata redaction, and verifies shutdown; the CLI now exits cleanly on an operator KeyboardInterrupt. Standalone regression reached 298 passing tests. This remains service-engineering evidence only.
- 2026-07-17: Made live credential readiness registry-scoped for arbitrary private operational registries. Preflight now evaluates each enabled registry profile through the same transport-level base-URL and API-key resolution used for live calls, including supported provider key aliases, and publishes only profile/provider hashes, API-format counts, and reason codes. A registry-only credential regression prevents false config-env-only blocks; standalone regression reached 300 passing tests. Refreshed code-test, dry four-surface protocol, provider-input-adapter, runbook, system-development, and formal 21-suite readiness receipts. The formal preflight confirms 8 valid input artifacts and 20/21 source/case bindings, while correctly blocking on authorized GPQA access, 294 real official/audited imports, and externally injected provider credentials with zero network calls. This remains engineering evidence only: it makes no benchmark score, latency, or superiority claim.
- 2026-07-17: Corrected public streaming terminal semantics against the native protocol families. Chat Completions retains its `[DONE]` sentinel; Responses ends at `response.completed`; Anthropic now emits `message_delta` before `message_stop` and streams tool arguments as `input_json_delta`; Gemini emits its final `alt=sse` JSON event with usage metadata and no OpenAI sentinel. Added direct and real loopback coverage across all four surfaces; standalone regression reached 302 passing tests. The change uses only offline test engines and makes no provider call, benchmark, latency, or superiority claim.
- 2026-07-17: Replaced the public health endpoint's internal registry readiness with an identifier-safe projection. `/v1/health` now exposes only public model names, API-format counts, provider/profile-set hashes, and safe reason codes; it cannot disclose provider/model/profile identifiers, endpoints, credential environment names, or keys through the provider-format inventory. Added regression coverage and refreshed standalone engineering verification at 303 passing tests. A local private-registry loopback confirmed `/v1/health` and `/v1/models` expose only the three public Axio models with no provider network calls. This remains service-engineering evidence only, not a benchmark, latency, or superiority claim.
- 2026-07-17: Corrected runtime circuit-health attribution. A local call-budget rejection now remains a local skipped branch rather than incrementing a provider failure counter; circuit state changes only for an attempted provider call that fails before a response arrives. Added a repeated budget-rejection regression plus existing circuit fallback coverage, and refreshed standalone verification at 304 passing tests. This improves constrained-request routing reliability only; it makes no benchmark, latency, or model-superiority claim.
- 2026-07-17: Hardened the raw provider inventory diagnostic endpoint. `/v1/inventory` now fails closed unless an explicit operator key is configured and presented, even when ordinary public API authentication is disabled for local development. The safe public health/models surfaces remain available under their existing policy. Added a private-identifier regression and refreshed standalone verification at 305 passing tests. This is a provider-configuration privacy control, not a benchmark or model-superiority claim.
- 2026-07-17: Added bounded in-memory runtime provider telemetry to the Fusion executor and router. Actual expert, Judge, and Synthesizer transport outcomes now update a per-profile success/failure and latency overlay; after three observations it applies prior-smoothed reliability plus observed p50/p95 to later routing without rewriting the registry or using benchmark labels. Route receipts contain only profile/provider hashes and aggregate telemetry. Regression covers success/failure adaptation, budget-rejection isolation, circuit separation, and identifier redaction; standalone verification reached 306 passing tests. This is adaptive routing engineering evidence only, not a benchmark, latency-superiority, or model-superiority claim.
- 2026-07-17: Completed the telemetry audit path. The runtime telemetry overlay is now reconstructed through a strict field allowlist into public response route summaries, operator-safe route plans, and durable safe execution traces; malformed hashes or unknown health labels are dropped instead of being relayed. The four API formats share the same response metadata summary. Regression retained 306 passing tests. This proves auditable routing instrumentation only, not any benchmark or model-superiority result.
- 2026-07-17: Corrected real upstream control-context delivery. Solver, Judge, and Synthesizer role packets are now explicitly injected through Chat, Responses, Anthropic, and Gemini provider adapters instead of being omitted when the public task is already represented in native history. The adapters preserve tool-turn ordering by merging into existing user tool-result turns for Anthropic/Gemini, and remove only an exact duplicate public-task prefix from the HTTP-local packet while retaining the complete prompt for custom clients. Cross-format regression covers native tool history, context delivery, and duplicate-task avoidance; this is engineering compatibility evidence only, not benchmark or model-superiority evidence.
- 2026-07-17: Hardened native public tool-plan arbitration. The executor now selects one coherent caller-declared plan before panel repair, rejects native calls from roles that never received tool declarations, canonicalizes accepted names to the caller schema, and prioritizes independently supported cross-provider plans over conflicting single-provider plans. Original selected call ids remain available only for the caller's follow-up tool result; execution traces and four-surface metadata retain hash/count-only arbitration receipts. This improves protocol correctness and bounded latency only; it does not establish benchmark or model superiority.
- 2026-07-17: Completed the targeted-escalation native tool-turn path. A valid tool call from the bounded post-Judge escalation branch now returns to the public caller before a second Judge or Synthesizer is attempted. The response retains the completed Judge's safe summary and call count while keeping all tool/provider values out of durable receipts. Regression covers the four public response formats, original call-id continuity, early-return behavior, and trace redaction; this remains engineering evidence only.
- 2026-07-17: Added tenant-isolated Responses `previous_response_id` continuation. Each stored turn is bounded by process-memory TTL, session count, and context size; it inherits omitted model/instructions/tools, preserves native function-call/result ordering across future provider formats, and assigns a fresh ID on cache hits. Unknown, expired, evicted, and cross-tenant IDs share one safe error. Diagnostic protocol/smoke calls disable continuation writes, and snapshots, traces, feedback, and benchmark artifacts retain no raw continuation content. Standalone regression reached 314 passing tests, and refreshed hash-only system-development readiness is ready for the separate benchmark-validation phase with zero network calls. This is API compatibility evidence only, not a benchmark or model-superiority result.
- 2026-07-18: Unified arbitrary-provider base-URL validation across credential readiness, `/models` discovery, and outbound transport. Only explicit HTTP(S) endpoints with optional path prefixes are accepted; embedded user-info, query/fragment components, invalid hosts/ports, non-HTTP schemes, and whitespace are blocked before network access. Added leakage and zero-network regressions for invalid configurations. This is a provider-configuration safety improvement only; it does not create benchmark scores or a model-superiority claim.
- 2026-07-18: Refreshed hash-only engineering evidence after the provider URL change: 331 standalone tests passed, compilation passed, the four-surface public protocol self-test and four-format provider-input self-test stayed network-free and ready, and the refreshed 21-suite live-readiness artifact remains blocked by external dataset/import/probe/credential prerequisites. No benchmark model calls or superiority claim were made.
- 2026-07-18: Added cooperative cancellation to timed-out parallel expert waves. Unstarted roles are cancelled, late responses from already-running custom clients are accounted for but discarded before Judge/synthesis, and safe traces expose only cancellation counts. Regression covers both pre-call cancellation and late-result discard; this protects the 3x latency/cost contract without changing normal or serial routes.
- 2026-07-18: Refreshed hash-only engineering evidence after cooperative parallel cancellation and complete-pool top-three screening hardening: 334 standalone tests passed, compilation passed, four public protocol cells and four provider input adapters remained network-free and ready, and the current live-readiness receipt remained blocked before provider calls by external prerequisites. No benchmark score or superiority claim was made.
- 2026-07-18: Bound the formal scorecard's top-level provider comparison to the frozen configured-provider-pool rank 1 candidate whenever an external ranking manifest is active; suite-observed highest-score providers remain explicitly diagnostic-only. Added regression coverage for this separation and refreshed hash-only engineering evidence at 335 passing tests, compilation passed, four public protocol cells and four provider input adapters network-free and ready. No benchmark score or superiority claim was made.
- 2026-07-18: Verified that GPQA Diamond remains upstream-gated: public metadata advertises CC-BY-4.0 with an explicit no-example-leakage acceptance term, while unauthenticated asset requests return authorization failure. Added a source-authorized-only CSV materializer with a fixed per-case SHA-256 option ordering so a later lawful full-Diamond acquisition cannot inherit the source CSV's correct-answer position. The materializer now fails closed unless the private acquisition manifest explicitly records `downloaded`; synthetic offline regression covers both the gate and deterministic output. Final standalone verification reached 336 passing tests, compilation passed, four public protocol cells and four provider-input adapters stayed network-free, and no GPQA examples, labels, or model calls were downloaded or persisted.
- 2026-07-18: Refreshed standalone engineering verification after cohort-bound formal artifact discovery: 341 tests passed, compilation and diff checks passed, and the mechanical-disk readiness audit correctly remained blocked because the available files have no single complete formal cohort and still describe the legacy exhaustive provider matrix. No provider calls or benchmark claims were made.
- 2026-07-18: Added a network-free remote-API execution-boundary audit and made it a mandatory system-development readiness gate. It checks only the standalone Fusion package for prohibited local-inference imports, declared dependencies, and model-weight artifacts, verifies the live transport guard accepts only HTTP(S), and confirms the four upstream API input adapters. It does not inspect ASciFS, invoke a provider, load model weights, or produce a benchmark claim.
- 2026-07-18: Bound the remote-API execution boundary into strict live campaign preflight. A merely asserted system-readiness flag is insufficient: the persisted readiness receipt must include a proven boundary requirement, a valid audit digest, and explicit no-local-weight/remote-HTTP process contracts before any benchmark provider request can begin.
- 2026-07-19: Added a forced native-tool operational calibration path. `tool-probe` sends one fixed function declaration through Chat Completions, Responses, Anthropic Messages, and Gemini adapters even when a profile's prior tool flag is false; results are classified as native-call success, text-only degradation, invalid native-call contract, protocol failure, or transport failure. Calibration updates only `supports_tools` and the bounded agentic capability signal, never benchmark scores or labels. The current three-channel live enrollment found 141 directory candidates, 43 text-available profiles, and 28 native-tool profiles; the result remains private operational evidence.
- 2026-07-19: Extended current channel convenience aliases to TokenAPIs Responses while preserving arbitrary file-backed provider configuration. A calibrated private registry was exercised through all 12 public tier/surface cells: 11 passed and one Fast/Gemini cell failed intermittently with safe provider-execution diagnostics. Terra and Pro completed expert/Judge calls but missed synthesis before their bounded live deadlines, so the live smoke window remains blocked and no capability or superiority claim is made.
- 2026-07-19: Corrected calibrated-registry evidence continuity. Calibration now preserves the source live-probe generation contract, readiness, source-artifact counts, and profile cohort metadata while changing only operational model signals; the 43-profile calibrated registry and its strict probe-evidence audit now bind successfully. Current dry protocol/adapter/remote-only receipts and the 378-test code receipt prove engineering readiness for the separate benchmark-validation stage, not model superiority.
- 2026-07-19: Adjusted latency-constrained panel selection so, after a fixed quality floor, estimated execution latency is preferred before provider-count diversity. The change retains explicit provider-diversity relaxation receipts and brought the current non-benchmark complete-Fusion deliberation probe to 2/2 full Terra/Pro Expert -> Judge -> Synthesizer completions. Wall-clock timing remains operational diagnostics only; the public 12-cell live surface window is still 11/12 because of intermittent Fast Chat upstream failures, and final p50/p95 3x claims remain benchmark-gated.
- 2026-07-19: Added the generic `enroll-providers` control-plane workflow. It accepts the non-secret arbitrary-provider manifest, discovers and probes live models, writes a probe-bound candidate registry, calibrates native tools from operational evidence, and promotes a calibrated registry only after the enabled stages pass. Added the current three-channel environment contract, safe invalid-row counts, and success/blocking regression coverage. This is provider onboarding and serving readiness evidence only; it does not rank models or create benchmark/superiority claims.
- 2026-07-19: Updated the code-test receipt contract to recognize the complete `PYTHONPATH=src ... pytest -q tests` standalone suite in addition to the legacy single-file command. Refreshed the safe receipt to 382 passing tests and system-development readiness to ready for the separate benchmark-validation stage; no benchmark output or superiority claim was produced.
- 2026-07-22: Closed the remaining live admission bypasses. `complete --live`,
  the production HTTP factory, and the default live request handler now require
  the hash-bound pre-Fusion registry; offline route-plan and explicitly
  injected test engines remain available. The v6 registry was loaded through
  the live factory without provider calls, `/health` was ready, and `/v1/models`
  exposed only the three public Axio tiers.
- 2026-07-22: Full standalone Fusion regression after the admission hardening:
  616 tests passed in 208.64 seconds; compilation passed. The independent
  external evaluator regression passed 18 tests separately. These are code and
  protocol readiness results only, not benchmark scores or superiority claims.
- 2026-08-16：完成 transport5 非目标筛选 cohort，并为 provider baseline
  freeze 增加严格的 transport-only admission 路径。该路径将 receipt 绑定到
  原始 registry hash 或显式 probe-bound 派生物，拒绝 benchmark/质量选择字段，
  并按精确的 profile/canonical hash 集合过滤正式 provider pool。重新生成的
  freeze 已具备 ready 的 external top-three ranking 和匹配 digest，但仍因真实
  的 missing-fast-candidate portfolio 缺口阻塞。全量回归为 1036 passed、7
  skipped；未执行 target benchmark calls，也未做 superiority claim。
