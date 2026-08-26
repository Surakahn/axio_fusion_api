# Axio Fusion API Checklist

## 2026-08-26 Health observability contract

- [x] `/health` 的 registry readiness 同时暴露 physical profile 与 logical canonical
  model 计数；available 计数沿用 enabled/health/90 秒 latency 服务边界。
- [x] 副本去重与 unavailable profile 的 health 契约测试通过；投影仍只保存 hash-safe
  计数，不改变 router、prompt、registry 或 benchmark gate。
- [x] 本轮 L1/L2/L3 回归：全量 `1097 passed, 7 skipped`，`compileall` 和
  `git diff --check` 通过；r18 frozen plan/source hash 未变化。
- [ ] r18 live screening 仍需明确授权；health 计数不等价于 provider admission、ranking
  或 21-suite target authorization。

## 2026-08-26 Formal Harness execution gate

- [x] execution plan 显式绑定 provider baseline freeze、formal top-three cohort 和固定
  15 run units；无 freeze 的 diagnostic matrix fail-closed 为 `blocked`。
- [x] formal cohort 合法且 task/pin/template 完整时直接输出
  `ready_to_execute` 与 `execution_authorized=true`，授权范围固定为官方/审计 Harness
  work queue；official import/acquisition 未完成只记录在
  `post_execution_reason_codes`，不会阻塞已准备好的执行队列。
- [x] post-execution imports/acquisition 仍由 binding、convergence 和最终 benchmark
  readiness 独立校验；execution plan 的授权不会开放 target campaign。
- [x] CLI、composite scaffold、binding、convergence 和 artifact readiness 均消费同一
  formal gate；freeze path/content digest 与 execution plan 绑定。
- [x] 新增离线 successor
  `private/runs/2026-08-26-composite-cohort-r18-harness-formal-gate/`，无 provider/target
  请求，execution plan/convergence 均正确 blocked。
- [x] L1/L2、专项 `15 passed`（另有 standalone execution/readiness `15 passed`）、
  全量 `1096 passed, 7 skipped`、`git diff --check` 通过。
- [ ] 明确授权 r18 live screening；在 screening terminal、transport admission、ranking
  和 provider freeze 之前，不执行 formal Harness imports 或 21-suite target campaign。

## 当前 r17 终态、r18 successor 与公共输出边界（2026-08-21）

- [x] 重新核对 Goal/PRD：产品仍是独立 remote-only Fusion API，只公开
  `axio-fast`、`axio-terra`、`axio-pro`，统一支持 Chat Completions、Responses、
  Anthropic Messages、Gemini；图片 lane 与文本 Fusion 隔离。
- [x] 完成公共输出归一化：只有完整内部 JSON/control envelope 才提取
  `answer`/`final_answer`；普通 JSON 与显式 `json_object`/`json_schema` 保持原样。
- [x] 四协议 buffered/streaming 渲染器统一使用公共文本；request-local stream gate
  在 acting answer 确认前暂存 JSON-like 片段，safe metadata 不保存原文或 secrets。
- [x] L1/L2 通过；兼容、流式和融合核心专项回归 `494 passed, 7 skipped`；全量回归
  `1092 passed, 7 skipped`。
- [x] public/operator 网关鉴权使用 `hmac.compare_digest` 做精确密钥匹配，保留
  operator 控制面隔离；鉴权、CORS 和控制面专项回归通过。
- [x] 18900 health 为 `ready`；三档公开模型、四种协议、代理选择与 secrets-safe
  约束通过；三个 tier 的 dry-run route plan 已核验，Pro 保留 Judge/Synthesizer。
- [x] r17 唯一 live non-target screening 已自然终态：`6 completed / 10 failed_or_blocked`，
  `ready_for_ranking=false`，`target_suite_calls_performed=false`；完整失败分母和 frozen
  plan/source hash 均已保留。
- [x] r17 transport-only admission 已执行：8 个 canonical 中仅 1 个同时通过两个 source
  family 的固定 2% gate，最低要求 3，receipt 为 `blocked`；未执行 ranking、provider
  freeze、official import 或 target 请求。
- [x] canonical convergence 文档已同步到 composite r17；旧 r43/r44 记录明确标为历史，
  当前 authoritative benchmark 范围仍为 9 类 21 套。
- [x] 注册 r18 immutable source successor，只改变 registration date/selection seed；完成
  16-unit frozen plan 与 zero-network preflight，未重复 provider probe。
- [x] r18 Harness 控制面离线生成：pin/execution ready，acquisition/import/binding/
  convergence 保持 blocked，`target_suite_calls_allowed=false`。
- [x] 新增可复用 `scripts/audit_screening_transport.py`：先按 64 位 hash unit 文件名
  allowlist 发现输入，再只读取 unit 的 failure telemetry；checkpoint、日志和其它
  private artifact 不会被打开；输出为 atomic、hash-only root-cause receipt。
- [x] 真实 r17 receipt 回归通过：16 units、1712 cases、762 completed、950
  transport-failed、916 fail-fast、799 provider attempts、37 failed attempts；真实
  failure class 与 fail-fast reason 分开统计，receipt hash 为
  `f91f064539dd246ae5836c669e40c0dc931d9f4b15028fb2075cdd0069081b73`。
- [x] L1/L2/L3/L4 控制面验证通过：专项 transport audit `4 passed`，Harness/screening/
  convergence 相关回归 `88 passed`，全量 `1087 passed, 7 skipped`，compileall、导入、
  CLI help 和 `git diff --check` 通过；没有 provider/target 网络调用。
- [x] 用零网络 fake-provider 回归复核 Terra panel budget：完整 4-role expert pool 在
  `reasoning_effort=high` 下均完成，12,000ms panel phase 配置成功，Judge/Synthesizer
  各执行 1 次；该结果仅区分调度预算与 r7 role-admission blocker，不作为 live 能力证据。
- [x] 新增并真实执行 `scripts/verify_screening_preflight.py`：hash 校验 r18 frozen
  plan/source/r7 registry 与 operational admission，核对原始及 credential-ready
  preflight、`auto -> proxy`、PID 命令绑定和敏感字段 fail-closed；receipt 状态为
  `ready_for_operator_authorization`，明确 `authorization_required=true`，不发起
  provider/target 请求，也不自动授权 screening；专项 `5 passed`，全量回归
  `1092 passed, 7 skipped`。
- [ ] 明确授权并启动 r18 live screening；启动前必须完成 transport 根因复核，不能恢复
  r17 checkpoint、使用 `--retry-failed`、降低 2% gate 或拼接 survivor subset。
- [ ] r18 terminal 后严格按 `transport admission -> complete-pool ranking -> external
  top-three -> provider baseline freeze -> same-cohort Harness -> 21-suite campaign
  -> final audit` 收敛；任何 gate 失败均创建 successor，不降低阈值。

## Composite cohort r9 terminal / r10 successor（2026-08-18）

- [x] 保留 r8 全部只读终态证据；不恢复 r8 plan、checkpoint、completed subset、
  ranking 或 Harness binding。
- [x] 注册 r9 source successor，使用新的 selection seed；source receipt 与 plan
  digest 独立绑定。
- [x] 生成 r9 immutable screening plan：8 canonical groups、9 physical profiles、
  2 source families、16 serial units、`max_workers=1`；zero-network preflight
  为 `preflight_ready`，provider/target calls 均为 0。
- [x] 以 `setsid` 启动 r9 live non-target screening（PID `1772237`），并以 600 秒
  低频间隔启动 convergence supervisor（PID `1877375`）；未修改 frozen plan。
- [x] 独立物化 r9 Harness pin、acquisition checklist、official execution plan、
  import audit 和 cohort binding；6/6 pin ready，BFCL V3 marker 通过。
- [x] 启动 r9 lineage watcher（PID `1891818`），只写 hash-only binding/audit，
  `target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
- [x] 对 r9 Harness 控制面执行 L1/L2 和专项回归：五个脚本通过 `py_compile` 与
  导入检查，Harness/绑定/审计/监督器测试 `21 passed`。
- [x] 只读核对 18900 serving 身份：发现历史 `run_server_noprefusion.py` 与旧
  28-profile registry；该 registry 在 `require_prefusion=true` 下 fail-closed，
  不作为正式 serving 或 baseline 输入。
- [x] 在备用 18901 端口验证 r7 probe-bound registry 的 pre-Fusion 加载与 health
  200/ready（21 profiles、4 providers、5 fast candidates），随后停止 staging；
  一次超时 live smoke 仅保留诊断日志，不计入 benchmark/API 成功证据。
- [x] 使用显式当前 pre-Fusion registry 通过 `scripts/run_server.py` 完成正式
  serving 切换（PID `1950874`）；切换前后只读 health、四格式 route-plan 和三个
  公开模型 dry-run 均通过，18900 加载 21 profiles/4 providers，标准
  `private/serving_registry.json` 已原子指向同一 r7 artifact，未停止 CPA Plus。
- [x] 等待 screening 自然终态；r9 已完成 16/16 units，3 completed、13 failed，
  `partial`，`ready_for_ranking=false`，完整失败分母和 target=false 均已核对。
- [x] 运行同 cohort transport-only admission：8 个 canonical candidates 中 1 个
  跨两 source family 通过，低于固定 3-model gate；receipt 为 `blocked`，未执行
  ranking、provider freeze 或 target 请求。
- [x] 完成 r9 supervisor receipt 与 lineage watcher 最终 hash-only audit；
  `target_suite_calls_allowed=false`、`final_claim_allowed=false`。
- [x] 创建新的 r10 source successor，仅改变 selection seed/registration date；不恢复
  r9、不拼接 completed subset。
- [x] 完成 r10 zero-network preflight：8 canonical groups、2 source families、16
  serial units、`max_workers=1`，provider/target calls 均为 0。
- [x] 还原并验证真实 pinned Harness/raw/BFCL V3 roots；独立物化 r10 pin、acquisition
  checklist、execution plan、import audit、cohort binding 和 convergence audit。
  6/6 pin ready，BFCL V3 marker 通过；控制面保持 `target_suite_calls_allowed=false`。
- [x] 对 r10 Harness 控制面执行 L1/L2 与专项回归；safe artifacts 不持久化 raw
  prompt、label、provider output、凭据或原始本地路径。
- [x] 以 `setsid` 启动 r10 live non-target screening（PID `2281133`），并立即绑定
  supervisor（PID `2283494`）与 lineage watcher（当前 PID `2365523`；旧 PID
  `2284301` 在审计修复后退出）；命令行、日志和
  首个私有 checkpoint 已核对，保持单 worker 与 fail-fast transport gate。
- [x] r10 已有三个 serial unit 完整终态：一个 112/112 且 0 个 transport failure，
  一个 102/102 且 1 个 transport failure 并完成，另一个 102/102 且 102 个
  transport failure 并失败（`screening_unit_no_scores`、
  `screening_unit_transport_failure_rate_exceeded`）；完整失败分母已保留，campaign
  state 为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`。
  第四个 unit 当前 4/112；`ready_for_ranking=false`、
  `target_suite_calls_performed=false`。
- [ ] 等待 r10 screening 自然 terminal；完整失败分母、target=false 和 state digest
  必须在 terminal 后核对，期间不得恢复 checkpoint 或启动 ranking。
- [ ] r10 transport admission 至少通过 3 个 canonical models 后，才执行完整-pool
  ranking；否则封存 r10 并继续 successor 路径。
- [ ] ranking ready 后生成当前 registry 绑定的 provider baseline freeze，并完成
  21-suite official/audited import receipts。
- [ ] convergence audit 返回 `ready_for_target_campaign` 后，才运行正式 target
  campaign、四种 API parity、paired statistical/latency/contamination audit，
  并检查三档 Fusion 对应单模型基线的优越性。

## Composite successor intake（2026-08-17）

- [x] 读取当前 handoff、计划、Git、服务健康和 r2 screening state；确认工作树与
  `origin/main` 一致，CPA Plus 保持运行。
- [x] r2 screening 终态完整保留 10-unit 分母：4 completed、6 transport failure，
  `ready_for_ranking=false`；未使用 survivor subset。
- [x] r2 supervisor 完成 transport-only conversion；由于 canonical eligible
  少于固定 3 个，ranking conversion 被跳过，target calls 保持关闭。
- [x] 生成 hash-only intake audit，明确 trusted、reference-only、blocked 和
  successor 分支，记录于
  `docs/operations/composite_baseline_intake_audit_2026-08-17.md`。
- [x] 完成单 profile operational-admission smoke；5/5 synthetic workloads 返回
  404，profile 被标记为 ineligible，未修改 r2 plan。
- [x] 完成同一 probe-bound registry 的全量 operational-admission：10 profiles 中
  7 个 production admitted、4 个 formal baseline eligible，跨 2 providers，且
  `raw_prompts_persisted`、`raw_provider_outputs_persisted`、`secrets_persisted` 均为
  `false`；safe/private receipt 分层保留。
- [x] 创建 immutable r3 screening plan：4 canonical groups、8 serial units、2
  source families、预计 856 calls；zero-network preflight 为 `preflight_ready`。
- [x] 启动 r3 live screening，并绑定 fail-closed convergence supervisor/watcher；
  screening terminal 前 target calls 保持关闭。
- [ ] r3 通过 screening、transport、ranking、provider freeze 后，重新绑定真实
  Harness pin/import/execution plan；在 convergence audit 放行前不得 target calls。

## Composite cohort r1 与 Harness Gate（2026-08-16）

- [x] 从两份已完成 strict streaming/role probe 的 live artifact 离线合并新的
  composite registry；精确 identity 去重后为 10 profiles、3 providers。
- [x] 生成并验证 composite non-target plan：10 canonical groups、2 source
  families、20 serial units、`max_workers=1`、fail-fast transport gate、plan
  digest 已冻结。
- [x] 首次未加载 `private/current_channels.env` 的启动在网络调用前 blocked，
  失败 state 单独保留；不得把它当作 screening 结果。
- [ ] retry1 screening 完整 terminal，所有 source-unit 通过 transport gate。
- [ ] 从 retry1 生成 transport admission、完整 pool ranking 和新的 external
  evidence；不得拼接 r5/transport5 ranking。
- [ ] 生成并验证 `final_claim_freeze_ready=true` 的 composite provider freeze，
  同时满足跨 provider verifier 与 fast-candidate 门禁。
- [x] 完成 Harness 分层设计：pin manifest、execution plan、zero-network
  preflight/import、cohort-bound campaign/final audit；设计记录见
  `docs/architecture/axio_fusion_benchmark_harness_convergence_2026-08-16.md`。
- [x] 生成 composite r1 的六套 Harness pin、acquisition checklist 和 108-task
  execution plan；所有 task 的 pin/template contract 通过，safe artifact 不含
  原始路径、数据、prompt、label 或 secret。
- [x] 完成六套 source/pin preflight 且 provider call 数为 0；LiveCodeBench、
  HumanEval、BFCL、IFEval ready。
- [x] Harness contract 专项回归通过：`16 passed, 370 deselected`，覆盖 pin、
  import template、execution plan 和 official bridge 校验。
- [x] tau-bench configured preflight ready：public gateway、独立 provider user
  simulator、retail/airline 两环境和 Python 3.11 均通过；仍待最终 freeze 绑定。
- [x] 修复多 probe 文件重复 profile 导致的 API format 审计假 blocker；唯一
  profile 计数与 registry source counts 已重新绑定，composite audit 为
  `ready=true`、0 blocker，并对跨 format 同 profile 保持 fail-closed。
- [x] 代码与 Harness 回归通过：`1037 passed, 7 skipped`（Python 3.11）。
- [x] 为 composite r1 增加 fail-closed 终态监督器
  `scripts/continue_composite_convergence.py`；PID、frozen plan、target-suite
  禁止标志、transport admission 和 ranking conversion 均有专项测试，操作手册
  见 `docs/operations/composite_convergence_supervisor_2026-08-16.md`。
- [x] 为长 screening 增加低频 hash-only `screening_progress` 事件；事件只记录
  terminal 计数、target-suite 禁止标志和 state digest，不增加 provider 调用。
- [x] 进度事件版本完成最终全量回归：`1042 passed, 7 skipped`。
- [x] 加固监督器 PID 身份校验，必须同时匹配 `baseline-screening-run` 子命令与
  frozen plan 片段；专项 Harness 回归为 36 passed。
- [x] 新增纯离线 `scripts/audit_composite_convergence.py` 收敛审计 Harness；
  同 cohort 的每一层 gate 都输出 hash-only 状态，区分 `running`、
  `ready_for_target_campaign` 与最终 `ready`，且不会启动 provider/target 请求。
- [x] 收敛审计 Harness 专项与完整回归通过：`11 passed`，`1048 passed, 7 skipped`。
- [x] 收敛审计的 provider freeze gate 已 fail-closed 绑定 schema、外部预注册
  top-three、registry hash、数量和敏感字段；仅设置 ready flag 的伪造 artifact
  不得开放 target calls。
- [x] 若 screening state 已记录 target 调用，审计强制关闭 target 与 final claim
  gate，禁止用事后 artifact 覆盖顺序违规。
- [x] 当前真实 r1 audit receipt 为 `running`、`next_gate=screening`、
  `target_suite_calls_allowed=false`；screening 仍由原 frozen plan 单 worker 推进。
- [x] 推送监督器 commit 后重新执行完整回归：`1042 passed, 7 skipped`；当前
  screening 仍由同一 frozen plan 单 worker 运行，监督器只等待 terminal state。
- [x] 用当前 composite registry 完成三档 L3b dry-run route plan；strategy、角色
  分配、辅助模型排除和 Pro 的 Judge/Synthesizer 延迟替换质量门限均通过，未发起
  provider 或 target-suite 请求。
- [ ] 在 freeze 后修复 MT-Bench 的跨 provider comparison/judge 绑定；旧 blocked
  reason code 保留，不使用先验或临时 profile。
- [ ] 补齐 108 个 official/audited import，并在 provider freeze digest 绑定后
  重新生成 cohort-bound execution/import receipts。
- [ ] freeze 后重新生成六套 official/audited Harness 的 cohort-bound pin、
  execution/import receipts；旧 `official_harness_execution_plan.current.safe.json`
  仅作模板，不得直接用于 final claim。
- [ ] 完成 21-suite target campaign、paired statistical/latency/contamination
  audit、四种 API surface parity 和 final completion audit。

## 当前 r5 Baseline Repair Gate（2026-08-16）

- [x] 完成独立 NVIDIA candidate cohort 的 strict streaming、role probe 和
  probe-bound registry；7 个物理 profile、2 个 provider、3 个 operational
  role coverage 均已通过。
- [x] 完成 CPA `/models` catalog enrollment，并保留 hash-only receipt；
  provider probe 未持久化 secrets、raw URL、raw prompt 或 raw output。
- [x] 保留第一次因 identity attestation 不完整而失败的
  `baseline_screening_plan.private.json`，不覆盖其诊断证据。
- [x] 用 NVIDIA r2 catalog 与 CPA r5 catalog 共同生成
  `baseline_screening_plan.identity-attested.private.json`。
- [x] 验证新 plan 的 exact identity attestation、完整 profile set、2 个
  source families、`max_workers=1` 和零网络 preflight。
- [x] 审计 screening checkpoint 的隐私边界；operator-owned private root 可
  暂存原始答案用于恢复，但 safe state/公开 evidence 不包含原文；第一次
  中断尝试单独保留在 `screening.identity-attested`，不并入正式结果。
- [ ] 仅在新 plan ready 后启动 non-target `baseline-screening-run`；运行时
  必须传入与 plan 完全相同的两份 private catalog probe，并使用 `setsid
  nohup`、单 worker。
- [ ] 完成 terminal screening、transport admission 和 screening-to-ranking；
  partial 或 transport-blocked 结果不得用于 ranking。
- [ ] 完成 operator-owned external ranking manifest；不得用模板或内部
  screening 分数伪造外部排名。
- [ ] 仅在 `final_claim_freeze_ready=true` 后运行 provider baseline freeze，
  并继续 official/audited harness import 与正式 benchmark campaign。

## Current r44 Screening Gate (2026-08-09)

- [x] Preserve the r43 probe-bound registry as immutable input and register a
  new r44 source-manifest/selection-seed boundary.
- [x] Revalidate the current provider `/models` catalogs through the configured
  network policy; bind a private catalog receipt without credentials or raw
  response bodies.
- [x] Repair provider-slug identity normalization while keeping model aliases
  exact; the regression suite covers underscore/hyphen provider aliases and
  rejects renamed model aliases.
- [x] Generate the r44 immutable plan: 10 canonical groups, 10 physical
  profiles, two independent sources, 20 serial tasks, 2,200 estimated calls,
  and `max_workers=1`.
- [x] Complete zero-network preflight with zero provider and target-suite
  calls; persist the plan/campaign digests and private root binding.
- [ ] Complete all 20 live screening tasks in the isolated r44 root. Preserve
  every transport failure in the denominator and do not reuse r26/r27/r43
  answers, scores, checkpoints, or survivor subsets.
- [ ] Convert only a terminal complete campaign into the external ranking
  artifact; keep rank assignment and baseline freeze closed until all
  identity, source, population, and evidence gates pass.

## Current r43 Evidence Gate (2026-08-09)

- [x] Complete the r43 provider discovery, research-prior, strict streaming,
  multi-sample, role-probe, and registry handoff generation without benchmark
  traffic; retain 10 logical/10 physical eligible profiles.
- [x] Keep the raw `prefusion-probe-export` schema boundary fail-closed; a
  generation wrapper is not accepted as a raw screening report.
- [x] Add and test the explicit `prefusion-generation-probe-export` offline
  projection from nested, endpoint-bound `eligible_profile_bindings`.
- [x] Revalidate profile identity, strict SSE/NDJSON evidence, three-sample
  success, measured latency, and text-only modality before projection.
- [x] Bind the projected probe to a new private copy of the r43 registry and
  pass the hash-only provider-probe evidence audit with zero blockers.
- [x] Fetch and hash current non-target ranking snapshots through the `10808`
  proxy and store them on the mechanical disk outside the repository.
- [x] Audit exact identity coverage against all 10 r43 canonical groups and
  preserve the zero-common-complete-source result as a fail-closed receipt.
- [ ] Complete two independent common non-target ranking source families,
  exact model identity attestations, population counts, stable snapshots, and
  derive the complete rank-1/rank-2/rank-3 provider baseline freeze.
- [ ] Activate and live-verify all three Axio tiers across Chat Completions,
  Responses, Anthropic Messages, and Gemini streaming surfaces.
- [ ] Run the independent 9-category/21-suite campaign only after baseline
  freeze and official/audited harness imports are ready.

## Current Image Capability Gate (2026-08-09)

- [x] Discover current CPA Plus `/models` through the configured `auto`
  network policy and classify `gpt-image-2` as image-only
  `candidate/not_run`; keep it out of text Fusion.
- [x] Keep the image probe control plane separate from text
  `load_registry()` so auxiliary image names are probeable without becoming
  text candidates.
- [x] Probe generation and editing as separate operations with `stream=true`;
  both returned validated SSE frames within the 90-second ceiling.
- [x] Bind the exact candidate/profile/endpoint set and promote the private
  verified image registry atomically; safe binding receipt contains no
  credentials, prompts, image bytes, or raw provider output.
- [x] Configure `AXIO_FUSION_IMAGE_REGISTRY_PATH` for the operator runtime.
- [x] Run new service-level live generation and multipart-edit requests after
  the serving process loads this verified registry; both returned
  `text/event-stream` responses with validated image partial/completed events
  and no raw prompt in the public stream.
- [x] Keep image capability evidence separate from the provider baseline freeze,
  Axio quality claim, and independent 9-category/21-suite benchmark campaign.

## Post-Image Regression Gate (2026-08-09)

- [x] Run L1/L2 checks and focused image/config/provider contracts (`107 passed`).
- [x] Load the verified image registry into a temporary HTTP service and verify
  `/health` reports one generation and one editing profile with
  `text_fusion_isolated=true`.
- [x] Repair and revalidate the 18 pre-existing non-image regression failures;
  the current full standalone regression is `1013 passed, 0 failed`.
- [x] Add profile-driven image parameter compatibility checks for
  `input_fidelity` and transparent backgrounds; unsupported or unknown options
  fail before prompt composition/provider I/O.
- [x] Require `multipart/form-data` editing requests, `image/*` file parts,
  and at most one mask before provider I/O.
- [x] Make the image admission probe reject any individual generation/editing
  operation whose measured latency exceeds the hard 90-second ceiling.
- [x] Add a read-only hash-only `registry-diagnostic` command that exposes
  precise pre-Fusion marker/binding/catalog reason codes while keeping
  `load_registry()` fail-closed.
- [x] Remove the live server's historical registry fallback; startup now
  requires an explicit current pre-Fusion serving registry.
- [ ] Re-audit text Judge and structured-output role coverage; the current
  health result is `usable_with_warnings`.

## Mixed-Protocol Channel Gate (2026-08-09)

- [x] Verify both configured provider `/models` endpoints through the
  process-local `auto` network policy and `10808` proxy path; both returned
  `status=ok` without benchmark traffic.
- [x] Confirm the current discovery census is 21 CPA profiles and 100 NVIDIA
  profiles; CPA's image entry remains `model_kind=image` and is excluded from
  text candidates.
- [x] Preserve explicit catalog protocol metadata as the first decision.
- [x] Route Claude/Anthropic model-id aliases to Anthropic Messages and keep
  all other CPA catalog entries on Responses when metadata is absent.
- [x] Add regression coverage for `claude-*`, `claude/...`, `anthropic/...`,
  GPT, Chinese-model aliases, and explicit protocol override.
- [x] Run the complete local regression after the transport-boundary change:
  `1005 passed, 0 failed`; no benchmark request was made.

## Historical Execution Gate (2026-08-06, r26; reconciled 2026-08-09)

- [x] Preserve r25 as terminal diagnostic evidence: its ranking conversion was
  template-only and transport-only successor admission retained zero eligible
  canonical models; no r25 answer, score, failure, or checkpoint is reusable.
- [x] Enroll the current configured provider pool and freeze the r26 plan:
  five canonical model groups, two independent non-target source families,
  ten serial tasks, fixed task order, 90-second per-request ceiling, and a 2%
  transport-failure gate.
- [x] Reconcile the on-disk r26 and r27 artifacts: both are partial,
  `ready_for_ranking=false`, and no screening process is currently running.
- [x] Record the transport-only lesson: r26 has timeout/network/5xx/empty
  output failures and r27 has timeout/empty-output failures; no score or
  ranking inference is permitted.
- [x] Quarantine the partial r26/r27 executions: retain their transport
  failures and `ready_for_ranking=false`; do not resume, merge, or rank them.
- [ ] Register a fresh full-pool cohort after the transport cause is
  understood, with a new immutable plan and complete denominator.
- [ ] Run exactly one screening-to-ranking conversion only after that new
  cohort is terminal; accept only a complete evidence-derived ranking and
  never a partial survivor subset.
- [ ] Freeze the derived rank-1/rank-2/rank-3 provider baselines, activate and
  live-verify all Axio tiers across four public streaming API formats, then
  execute the independent 9-category/21-suite campaign.

## Current Execution Gate (2026-08-03, r20)

- [x] Validate the active r20 pre-Fusion report: 18 physical candidates and 11
  logical models admitted after three strict streaming samples and the 90-second
  latency gate.
- [x] Refresh r20 engineering readiness independently of benchmark execution:
  `939 passed`, four public protocol self-test, provider input adapter
  self-test, remote-only boundary, and live runbook binding all pass.
- [x] Confirm the system-development gate is ready for the separate benchmark
  phase; this receipt contains no provider baseline ranking or quality claim.
- [x] Export the nested pre-Fusion stream evidence through the reusable
  `prefusion-probe-export` command; no network call is performed by the export.
- [x] Bind the exported probe to the current private registry and pass the
  hash-only provider-probe evidence audit with matching profile, status, mode,
  API-format, and path bindings.
- [x] Generate a new ranking template from the exact r20 registry candidate
  set; it has 11 candidates and remains explicitly `template_only`.
- [x] Generate a fresh r20 non-target screening plan from the same bound
  registry and probe catalog: 11 canonical groups, 2 independent source
  families, 22 units, 2,420 fixed calls, and `max_workers=1`.
- [x] Assemble the mechanical-disk dataset manifest against the real
  standardized cohort and generate the six-suite official/audited harness pin
  manifest; paths, evaluator files, dataset snapshots, and prompt/decoding
  bindings are hash-only in the pin artifact.
- [x] Record the single canonical convergence path and terminal command in
  `docs/operations/convergence_execution_path_r20.md`.
- [x] Add an opt-in, serial, pre-registered transport-failure fail-fast gate
  for future screening cohorts; preserve complete failure denominators,
  resumable checkpoints, and r20 plan-digest compatibility.
- [ ] Complete all 22 r20 screening units; retain every timeout or transport
  failure in the denominator and do not reuse an older cohort checkpoint.
- [ ] Complete and freeze the pre-registered external ranking for the complete
  11-model pool using at least two common independent source families, exact
  population counts, stable snapshots, and identity attestations.
- [ ] Run the independent 9-category/21-suite campaign only after the provider
  baseline freeze and all official/audited harness imports are ready.

## Current Live Gate (2026-07-29, full cohort r1)

- [x] Complete fresh full-cohort enrollment: 35 strict-streaming text profiles
  across two providers and two upstream formats; probe, calibrated registry,
  and redacted evidence bindings all pass the 90-second gate.
- [x] Complete zero-network screening preflight: 35 canonical candidates, two
  independent source families, 70 source-candidate units, 6,230 estimated
  provider calls, and frozen `max_workers=1`; no live or target-suite call was
  made by preflight.
- [x] Record engineering evidence for the cohort: 769 standalone tests pass,
  all four provider input adapters pass, and all 12 dry public protocol cells
  pass across the three Axio models and four public API formats.
- [ ] Complete all 70 fresh live screening units in the isolated r1 private
  root. Do not reuse any v3/R2 answer, score, survivor, failure, or checkpoint;
  preserve every new failure in the denominator.
- [ ] Verify terminal checkpoints and convert the complete campaign to a
  deterministic external ranking; partial results cannot select a baseline.
- [ ] Freeze exactly rank 1, rank 2, and rank 3 canonical baseline groups,
  including all replica and provider-probe bindings.
- [ ] Activate and live-verify `axio-fast`, `axio-terra`, and `axio-pro` on
  Chat Completions, Responses, Anthropic Messages, and Gemini streaming
  surfaces, then run the separate 9-category/21-suite campaign.

## Current Live Gate (2026-07-28, v3 isolated cohort)

- [x] Quarantine the terminal R2 screening as diagnostic-only evidence: 30
  planned units, 17 completed, 13 failed, `ready_for_ranking=false`; do not
  reuse its answers, scores, failures, or survivor subset.
- [x] Freeze screening concurrency in plan/campaign schema v3. Bind
  `max_workers` into the plan digest, live runtime validation, checkpoint
  resume, and ranking conversion; reject missing or mismatched values before
  provider I/O.
- [x] Re-enroll the current two-channel portfolio in an isolated, serial live
  run: discover 126 entries, admit 25 strict-streaming profiles, calibrate 14
  native-tool profiles and 16 reasoning-transport profiles, and retain the
  complete private registry without benchmark material.
- [x] Run fixed long-request operational admission over all 25 profiles with
  five non-target workloads, `max_workers=1`, one repetition, and a 90-second
  ceiling: 13 production-admitted profiles and 12 formal-baseline-eligible
  profiles; handoff validation is ready with no raw prompt/output persistence.
- [x] Build the hash-bound v3 non-target screening plan from the formal cohort:
  12 canonical candidates, two independent source families, 24 units, 2,136
  estimated calls, and frozen `max_workers=1`; zero-network preflight passes.
- [ ] Complete all 24 v3 live screening units in the isolated
  `axio-screen-v3-r2` session without any concurrent smoke, diagnostics, target
  benchmark, or manual provider calls. Preserve every failed unit in the
  denominator and never rank an interim survivor subset.
- [ ] Verify the terminal campaign by authenticating every checkpoint/private
  artifact and rerunning the pinned scorers; require strict
  screening-to-ranking conversion to produce a complete assignment.
- [ ] Freeze exactly the derived rank-1/rank-2/rank-3 canonical groups, bind
  all replica identities and provider-probe evidence, and reject any manual
  reorder or substitution.
- [ ] Activate the cohort-bound Axio service and obtain current strict live
  evidence for all three public models across Chat Completions, Responses,
  Anthropic Messages, and Gemini-compatible streaming surfaces.
- [ ] Execute the separate 9-category/21-suite paired campaign, official or
  audited harness imports, contamination audit, Holm-Bonferroni family,
  practical-effect gates, and p50/p95 3x latency gates before any superiority
  claim.

The following 2026-07-27 block is historical evidence. Its completed work
remains useful, but its unchecked cohort-registration item is superseded by
the v3 isolated cohort above.

## Current Live Gate (2026-07-27, current cohort)

- [x] Discover the current configured remote pool and retain 31 profiles from
  126 logical entries after the strict text probe.
- [x] Complete strict operational admission for all 31 profiles: 465
  streaming attempts, 369 passed attempts, 72 ordinary failures, 24
  latency-ineligible attempts, and 11 formal eligible profiles.
- [x] Execute the new pre-registered screening plan across 11 canonical
  candidates, two independent source families, 22 units, and 2,420 fixed
  provider calls without `--retry-failed`.
- [x] Reach a terminal result for all 22 units: 6 passed the transport and
  scoring contract and 16 were rejected by transport-failure-rate or no-score
  gates; retain all 2,420 case records, 1,444 scored responses, and 976
  transport failures in private evidence.
- [x] Run screening-to-ranking conversion; it correctly remains
  `screening_conversion_ready = false` with no rank assignment.
- [x] Re-run engineering readiness against the current registry: 678 Python
  3.11 tests passed, all 12 public protocol cells passed, all four provider
  input adapters passed, and the system-development receipt is ready for a
  separate benchmark-validation stage.
- [x] Build and validate the screening-disjoint `mmlu_pro_stem` v2 replacement
  for the unavailable gated GPQA slot: pinned source revision, six STEM
  categories, 600 deterministic cases, a pre-registered 112-row non-target
  screening exclusion set, zero selected-row overlap, prompt/label separation,
  receipt-to-dataset hash/count binding, and a 21-slot manifest that records
  the replacement identity without relabelling it as GPQA. Historical v1 is
  retained only for diagnostic inspection and is fail-closed for formal use.
- [x] Add endpoint-bound reasoning-transport reconciliation: a reasoning probe
  now freezes its model/protocol/transport contract and resolved channel
  endpoint hash before the first request; both local calibration and the
  full matching source/calibration/probe reconciliation path reject stale
  endpoint evidence before a status-only capability change.
- [x] Run a new endpoint-bound live reasoning probe after this control-plane
  upgrade: the complete unbounded 28-profile candidate set was covered, with
  23 `verified`, 2 `unsupported`, and 3 `candidate` outcomes. The subsequent
  reconciliation validated every endpoint binding and wrote a distinct private
  operational registry; historical unbound probes remain diagnostic only.
- [x] Keep provider baseline freeze and the 9-category/21-suite target
  campaign fail-closed because the complete-pool rank-1/rank-2/rank-3
  evidence is unavailable.
- [ ] Register a new independent provider cohort that satisfies complete
  source-family coverage, portfolio/verifier capacity, and provider/API
  diversity; never select a top three from the current survivor subset.
- [ ] After the provider baseline freeze is valid, run the independent
  9-category/21-suite campaign with four Axio public API surfaces, paired
  statistics, contamination audit, and 3x latency gates.

The following v9 block is historical evidence and is retained for provenance;
its unchecked items are not the current cohort's execution plan.

## Historical v9 Live Gate (2026-07-23)

- [x] Preserve former v6 and stopped v8 evidence as historical diagnostics;
  neither is a current serving input or a baseline-ranking source.
- [x] Revalidate Research Agent capability-axis coverage and deterministic
  `research_quality_score` merge ordering at registry load; edited or legacy
  broad all-zero-axis rows fail closed.
- [x] Discover and research-rank the complete v9 two-channel pool: 131/131
  candidate records completed without using benchmark prompts, labels, or
  scores.
- [x] Run three independent strict streaming samples for all 131 profiles: 34
  admitted, 11 rejected by the 90-second gate, 86 rejected for
  stream/protocol stability, and zero ordinary JSON fallbacks admitted.
- [x] Generate and validate the v9 private registry and safe receipt: 34
  logical/physical serving profiles, exactly three successful strict-stream
  samples for every admitted profile, report and registry validation `true`,
  and `load_registry()` loads all 34 profiles.
- [x] Verify required `primary_solver`, `judge`, and `synthesizer` role
  coverage in the latency-filtered logical list.
- [x] Run the separate native-tool operational calibration without benchmark
  data: preserve all 34 text-admitted profiles and mark 18 as tool-call
  eligible; source and updated registry handoff validation both pass.
- [x] Make the v9 calibrated registry the current Fusion runtime input for
  offline load validation; the handoff contains no benchmark score or
  superiority claim.
- [x] Make the single Fusion handoff carry the complete research-prior
  ranking, the available-only operational ranking, their content digests, and
  the latency-filtered logical model list; normalize legacy single-sample
  latency aliases to explicit observed-latency names at that boundary.
- [x] Add the dedicated `available_model_generation` control-plane wrapper and
  `generate-available-models` CLI command. It revalidates the report/registry,
  emits a fixed handoff artifact, and atomically publishes only a ready
  latency-filtered registry; blocked refreshes cannot replace the active one.
- [x] Bind the generation artifact's handoff digest, registry digest, and
  logical-model count at publication; support optional atomic `--handoff-output`
  publication alongside the private runtime registry.
- [x] Add strict `api-surface-stream-live-smoke` coverage for all 12 public
  tier/surface cells, including native SSE terminal semantics and fail-closed
  credential/live guards; mock protocol regression passes.
- [x] Refresh full standalone Fusion verification after the stream-smoke
  implementation: `637 passed in 203.83s`.
- [ ] Run one new, non-overwriting v9 public API live-smoke receipt and one
  strict v9 stream-live-smoke receipt. Existing historical public smokes cannot
  satisfy this gate.
- [ ] Run one new v9 `fusion-deliberation-live-smoke` receipt for complete
  Terra/Pro orchestration. Existing historical deliberation evidence is
  diagnostic only.
- [ ] Run the separate benchmark phase only after the code/test and current
  public-protocol gates are complete. This handoff alone is not benchmark
  evidence.

- [x] Require the v9 pre-Fusion registry for every live registry-loading
  production entry: `complete --live`, the live HTTP factory, and the default
  live request handler reject legacy or edited registries before provider
  execution. Offline diagnostics and explicitly injected test engines remain
  available.
- [x] Load the v9 registry through the live HTTP factory without network calls;
  verify `/health` is ready and `/v1/models` exposes exactly
  `axio-fast`, `axio-terra`, and `axio-pro`.
- [x] Run the complete independent evaluator contract suite separately:
  `18 passed`; benchmark datasets, labels, API keys, and raw outputs remain
  outside Fusion and are not persisted by the evaluator.

- [x] Refresh hash-safe system-development readiness against the current
  34-profile v9 calibrated registry. The remote API-only boundary, four
  upstream input adapters, dry public protocol cells, and strict stream smoke
  regression are ready.
- [x] Repair and regress-test baseline-screening recovery so the resume digest
  covers both pre-existing and newly reconstructed private units.
- [x] Authenticate the retained full-pool screening results without provider
  calls: 23 units can resume under the frozen 35-canonical-model plan; 3 are
  complete and 20 are retryable only for recorded transport failures.
- [ ] Build a new pre-registered non-target screening plan from the complete
  v9 canonical model pool; do not resume or merge the failed v8 campaign.
- [ ] Convert the completed v9 screening campaign into the externally evidenced
  canonical rank-1/rank-2/rank-3 baseline freeze.
- [ ] Obtain authorized GPQA Diamond access and import the six required
  official/audited harness result sets before the strict 21-suite campaign.
- [ ] Run the locked live matrix, four-public-protocol parity, paired
  statistics, 3x p50/p95 latency gates, contamination audit, and completion
  audit. Do not claim superiority until every required gate passes.

- [x] Keep `axio_fusion_api` in a standalone package outside the ASciFS `axio/` package.
- [x] Keep standalone Fusion implementation, tests, package metadata, plans, and operator documentation under `axio_fusion_api/`.
- [x] Define public models: `axio-fast`, `axio-terra`, `axio-pro`.
- [x] Define public API surfaces: Chat Completions, Responses, Anthropic Messages, Gemini.
- [x] Expand benchmark methodology to 21 suites across 9 categories.
- [x] Download or record authorized blockers for the benchmark datasets on `/mnt/storage`.
- [x] Remove stale 14-suite and 9-local-suite test assumptions.
- [x] Verify benchmark acquisition, readiness, source manifest, scorecard, claim audit, and final audit tests.
- [x] Add bounded deliberative search policy to routing, prompt assembly, and runtime guards.
- [x] Re-read and strengthen provider routing, compatibility, and trace-safety implementation.
- [x] Run standalone Fusion API targeted regression.
- [x] Run full standalone Fusion API regression.
- [x] Add focused tests for any new routing or fusion behavior.
- [x] Add recoverable per-profile circuit breakers with a bounded cooldown,
  successful recovery reset, hash-only recovery receipts, and regression
  coverage; preserve zero-cooldown manual recovery semantics.
- [x] Discover formal benchmark artifacts from canonical short filenames inside
  an explicit mechanical-disk cohort directory while retaining hash-only
  cohort binding and fail-closed mixed-cohort behavior.
- [x] Report missing provider endpoints and missing provider keys independently
  in non-target screening preflight while retaining fail-closed live admission.
- [x] Add private benchmark materialization status/materialize CLI and hash-only receipts.
- [x] Keep IFEval final scoring on an official/audited harness-import path instead of simplified local checks.
- [x] Refine materialized dataset leakage detection so BBH natural answer tokens in prompts are not false blockers.
- [x] Enforce a hard known-latency Fusion admission guard at 3x direct single-model p50.
- [x] Enforce final benchmark claim-audit latency gate at 3x the corresponding provider baseline.
- [x] Materialize and validate all 13 then-authorized local benchmark JSONL files on `/mnt/storage`; GPQA Diamond remains separately gated until an operator accepts its upstream terms.
- [x] Add a reproducible official FLORES-200 adapter for the fixed 100-case, 10-direction `devtest` slice without reference leakage.
- [x] Add suite-aware min-case gates so AIME Recent's complete 30-case slice is not blocked by the default 100-case campaign threshold.
- [x] Add quality-diversity niche archives and OpenRouter-style provider routing policy to route plans, prompts, and safe traces.
- [x] Preserve evidence-backed minority/critic/domain insights during synthesis candidate compression.
- [x] Keep `axio-fast` single-model calls inside a realistic low default cost ceiling after enriched routing context is added.
- [x] Route runtime fallback through the hash-only provider routing pool with health, latency, cost, and diversity ordering.
- [x] Pin official/audited harness commits and dataset/evaluator hashes for LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style judging.
- [x] Generate official import batch template with 144/144 rows prefilled from harness pins.
- [x] Prepare and validate source manifest hashes for the 13 suites with materialized case hashes.
- [x] Add configuration-driven live readiness preflight for arbitrary providers/API formats without making AISZ/CPA Plus/NVIDIA structural dependencies.
- [x] Support per-model API format and metadata overrides inside arbitrary provider configs.
- [x] Inherit matching per-model provider config overrides during live `/models` discovery and generated registry creation.
- [x] Add generic Gemini-compatible provider convention and test four-interface provider discovery coverage.
- [x] Normalize prefixed Gemini model resource names when calling `:generateContent`.
- [x] Add hash-only official harness execution plan before importing LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style outputs.
- [x] Add shadow-only fusion failure analysis and ablation planning for score, statistics, API-surface, evidence, and 3x latency failures.
- [x] Propagate hash-safe routing-policy version/application summaries through execution traces, feedback receipts, trace reports, and learning buckets without persisting policy paths, prompts, provider identifiers, or arbitrary policy text.
- [x] Add a bounded `routing-policy-shadow-replay` command that compares historical and candidate rule decisions while explicitly withholding counterfactual quality, cost, latency, and superiority conclusions until paired candidate evidence exists.
- [x] Add a remote-provider onboarding lifecycle (`configured -> protocol_validated -> live_probed -> capability_calibrated -> shadow_candidate -> approved -> active`) with hash-only candidate/review/activation/apply artifacts and CLI control points.
- [x] Keep onboarding candidates disabled until explicit approval writes a new private registry; enforce disabled-profile exclusion before every direct or panel route selection.
- [x] Make the remote-API-only boundary a system-readiness gate with a network-free static audit for local-inference imports/dependencies/artifacts, HTTP(S) transport enforcement, and four upstream input adapters.
- [x] Add hash-only provider portfolio audit for arbitrary provider pools, baseline tiers, Fusion role coverage, API-format diversity, and 9-category capability coverage.
- [x] Prepare live provider probing and benchmark campaign command runbook without persisting secrets or coupling to named channels.
- [x] Feed safe provider routing fallback receipts into router-learning examples and shadow-only policy recommendations.
- [x] Include aggregate provider fallback health in trace reports and benchmark failure-analysis ablations.
- [x] Add hash-only benchmark campaign progress and resume/repair planning for interrupted 21-suite live runs.
- [x] Add hash-only API surface parity report for the four Axio public API formats in benchmark campaigns.
- [x] Add hash-only provider baseline freeze manifest and final-audit binding so the single-model baseline universe cannot drift after campaign start.
- [x] Require complete live provider-pool external screening with two distinct independent non-target ranking sources per profile; derive the pool top three deterministically and reject manually swapped rank rows.
- [x] Normalize external ranks by source population and aggregate only two or more source families common to every live candidate; bind source snapshots/populations and reject missing, duplicate, or inconsistent common-source evidence.
- [x] Make a supplied external top-three freeze force the exact 15-unit formal cohort in benchmark matrices and acquisition artifacts; ignore candidate filters and all-provider diagnostic expansion on that path; refresh 343-test, 12-surface, four-adapter, and system-readiness engineering evidence without network calls.
- [x] Make formal benchmark artifact auto-discovery cohort-first; select one shared batch across all eight artifact kinds and block independently newest mixed batches, with regression coverage for both complete and mixed cohorts.
- [x] Block benchmark-derived registry calibration by default; require explicit exploratory opt-in and prevent a blocked calibration from writing an updated registry.
- [x] Keep benchmark scorecards diagnostic-only in learning reports; require explicit opt-in and prevent scorecard-derived router or registry changes.
- [x] Add hash-only provider probe evidence audit binding private live probe, generated registry, redacted probe, and redacted registry evidence before baseline freeze.
- [x] Require provider probe evidence audit in final-audit and evidence-pack proof gates.
- [x] Bind provider baseline freeze digest to the provider probe evidence audit receipt.
- [x] Add bounded `axio-fast` light verification for high-quality/high-risk/tool-planning requests under the 3x latency guard.
- [x] Add hash-only local Judge answer-claim clustering for equivalent final answers when provider Judge calls are skipped.
- [x] Return hash-only safe route-plan views from the operator API instead of raw provider/model/profile internals.
- [x] Forward decoding controls consistently through Chat, Responses, Anthropic, and Gemini provider input adapters.
- [x] Feed `axio-fast` light-verify and answer-claim cluster receipts into safe learning examples and shadow-only router ablation suggestions.
- [x] Add hash-only official import audit preflight for official/audited harness receipts before campaign/final audit.
- [x] Require official import audit readiness in `fusion-live-readiness` and the live runbook before 21-suite campaigns.
- [x] Bind official import audit run-set digests into final audit and evidence pack proof gates.
- [x] Bind API surface parity run-set and audit digests into final audit and evidence pack proof gates.
- [x] Promote factuality and vertical-domain signals into runtime DAG nodes, prompt policy, local Judge coverage, targeted escalation, safe trace summaries, and shadow-only learning patches.
- [x] Add strict live campaign preflight so formal live runs block before provider calls unless readiness, live probe evidence, an externally ranked top-three provider baseline freeze, and registry bindings are all ready.
- [x] Add dry hash-only API surface protocol self-test for Chat Completions, Responses, Anthropic Messages, and Gemini before live campaigns.
- [x] Add practical effect-size gates and Wilson confidence interval summaries to claim audit and final proof contracts.
- [x] Enforce final benchmark claim-audit p50 and p95 latency gates at 3x the corresponding provider baseline.
- [x] Add top-level hash-only Fusion completion audit tying evidence pack, final audit, API-surface protocol self-test, live runbook, and remaining blockers into one requirement matrix.
- [x] Add hash-only provider input adapter self-test for Chat Completions, Responses, Anthropic Messages, and Gemini provider-side inputs before live campaigns.
- [x] Normalize common upstream text-block response variants across all four provider adapters and reject HTTP-success semantic empty responses with one bounded retry before replica/fallback recovery.
- [x] Add numeric-equivalence answer-claim clustering for local Judge and safe learning features so fraction, decimal, and percent answers do not become false contradictions when provider Judge calls are skipped.
- [x] Let early-exit use hash-only answer-claim consensus when equivalent answers have low surface-form similarity, reducing unnecessary synthesis calls under latency budgets.
- [x] Add local Judge confidence calibration and safe learning features for unsupported high-confidence, missing-evidence, factuality, and vertical-guardrail risks.
- [x] Apply calibrated confidence to early-exit and quality-target gap gates so unsupported high-confidence candidates cannot skip synthesis or avoid repair.
- [x] Require independent profile/provider support for answer-claim consensus before early-exit can skip synthesis.
- [x] Escalate answer-claim independence gaps through local Judge missing coverage, contradictions, and follow-up tasks.
- [x] Route answer-claim independence gaps to targeted new-profile/cross-provider verifier selection, verifier prompts, synthesis uncertainty labeling, and shadow-only learning patches.
- [x] Audit provider portfolios for independent answer-claim verifier capacity before live benchmark/final-claim runs.
- [x] Block live readiness and final-claim preflight when a live registry lacks cross-provider independent verifier capacity.
- [x] Bind provider portfolio independent verifier capacity into provider baseline freeze receipts and final audit gates.
- [x] Expose provider portfolio independent verifier capacity as a first-class Fusion completion audit requirement.
- [x] Expose the 21-suite x 3-tier claim comparison family as a first-class Fusion completion audit requirement.
- [x] Bind evidence-pack final-audit summaries to the current final audit in Fusion completion audit.
- [x] Require live runbooks to advertise every top-level completion gate before completion audit can pass.
- [x] Require a safe shadow-only benchmark failure-analysis artifact before Fusion completion audit can pass.
- [x] Order official import audit after dataset/case/source manifest binding in the live runbook.
- [x] Add source-manifest preparation before source-manifest case-hash binding in the live runbook.
- [x] Require source/case/official-import evidence in strict live campaign preflight before provider calls.
- [x] Require API-surface protocol and provider-input-adapter self-tests in strict live campaign preflight.
- [x] Require Fusion completion audit to validate live-runbook command templates, including strict campaign preflight flags, manifest command order, and final shadow failure-analysis wiring.
- [x] Require Fusion completion audit to recompute evidence pack and final audit from primary safe artifacts before completion can pass.
- [x] Require Fusion completion audit to load a persisted provider-input-adapter self-test artifact instead of inferring provider input conformance from the registry.
- [x] Require Fusion completion audit to validate API-surface protocol self-test row/model coverage, route consistency, and leakage flags before completion can pass.
- [x] Add a separate Fusion system-development readiness audit for standalone code tests, dry API/protocol/adapter self-tests, runtime construction, and runbook templates before 21-suite benchmark validation.
- [x] Run system-development readiness as an explicit live-runbook stage before the formal 21-suite benchmark campaign.
- [x] Require a persisted system-development readiness receipt in strict live benchmark-campaign preflight before provider calls.
- [x] Require the persisted system-development readiness receipt in Fusion completion audit before final completion can pass.
- [x] Require strict live campaign preflight to block provider baseline freezes without cross-provider independent verifier capacity.
- [x] Bind provider probe live available counts, probe mode counts, and registry live-readiness flags into baseline freeze receipts.
- [x] Recompute provider probe evidence digests over live summaries and require live count/mode/profile-set/registry readiness across final audit and completion evidence.
- [x] Add the FLORES case hash and bound source-manifest evidence after official materialization becomes ready.
- [x] Freeze the externally evidenced, pre-registered configured-provider-pool top three from the complete live provider census with probe evidence audit binding.
- [x] Refresh 225-test code receipt, four-surface API self-test, provider input adapter self-test, and system-development readiness.
- [x] Preserve the historical CPA Plus plus NVIDIA live provider evidence as a diagnostic census: 131 `/models` entries discovered, 37 strict short-prompt live baselines admitted, v2 probe evidence audit ready, and no secrets/raw provider outputs persisted in safe artifacts. Its exhaustive v2 freeze is diagnostic only; final claims require the externally evidenced configured-provider-pool top-three freeze.
- [x] Re-run strict live benchmark preflight with the v2 provider registry and baseline freeze; confirm it blocks before any provider calls only because 21-suite source/case/official-import readiness remains incomplete.
- [x] Re-run standalone engineering regression after the v2 evidence refresh: 225 tests passed, `compileall` passed, `git diff --check` passed, and no Fusion source imports ASciFS `axio`.
- [x] Audit the v4 acquisition queue against the v2 registry/freeze: 40 candidates, 49 run units, 21 suites, 1,029 campaign cells, 37 opaque provider aliases, 12 Axio API-surface units, and no unsafe evidence leakage or legacy internal baseline rows.
- [x] Bind official source/case manifests for LiveCodeBench, BFCL, tau-bench, and MT-Bench using stable identifiers only; preserve official harness scoring as a separate requirement.
- [x] Treat the complete fixed 80-question MT-Bench corpus as a valid source-manifest case-set exception to the global 100-case minimum.
- [x] Rebuild mechanical-disk hash-only case/source manifests at 20/21 ready suites, with no raw prompts, labels, tests, provider outputs, provider URLs, or secrets in the new artifacts.
- [x] Add an explicitly opt-in, bounded, hash-only live smoke for all three Axio tiers across the four public API surfaces; keep it separate from benchmark and superiority evidence.
- [x] Add and fake-client regression-test an explicitly opt-in complete-Fusion deliberation smoke for `axio-terra` and `axio-pro`; require multi-branch admission and provider Judge, allow controlled early exit only for non-Hermes routes, and require an accepted acting Synthesizer plus a complete process receipt for Hermes routes while emitting only hash-safe orchestration receipts.
- [x] Remove provider endpoint hard-coded fallbacks; require explicit base-URL configuration before live network access and keep credential errors identifier-safe.
- [x] Support fully model-scoped arbitrary provider configurations, including direct multi-protocol probing without a provider-level `/models` endpoint.
- [x] Align initial Fusion latency/cost/utility admission estimates with runtime-assigned roles, including every queued expert wave and the initial Judge/Synthesizer calls.
- [x] Add generation-fenced `refresh_runtime_channels` with complete enrollment,
  active-client reuse, candidate readiness validation, atomic swap, and old
  engine preservation on enrollment failure or generation conflict.
- [x] Separate native-tool capability state (`proven`, `unproven`, `failed`)
  from the compatibility boolean and prevent unproven/failed profiles from
  entering tool-specialist routing; preserve explicit external attestations
  across negative bounded probes.
- [x] Re-run the complete standalone Fusion regression after runtime refresh
  and capability-state changes: 430 tests passed and source compilation passed.
- [x] Exercise the latest calibrated registry through the real public gateway:
  health/models readiness passed and all 12 Axio-tier/public-protocol cells
  returned valid response shapes; keep this separate from benchmark evidence.
- [x] Reserve initial Judge and Synthesizer call budget for `axio-fast` light verification so the verified path can complete before bounded fallback.
- [x] Run all bounded initial expert roles concurrently (up to primary, independent, critic, and domain specialist) so the 3x latency gate reflects executable runtime parallelism rather than avoidable serial scheduling.
- [x] Prove by regression that a selected but unassigned extreme-cost/extreme-latency spare model cannot alter initial Fusion estimate, utility, or admission.
- [x] Align initial route-cost admission estimates with runtime output reservations, both for explicit `max_output_tokens` and role-specific defaults.
- [x] Refresh standalone engineering receipts after role-schedule/cost alignment: 251 tests passed, 12/12 dry public protocol cells passed, four provider input adapters passed, and system development is ready for separate 21-suite benchmark validation without any superiority claim.
- [x] Enforce initial complete-Fusion call-budget admission: reserve the required independent experts, Judge, and Synthesizer before activation; reject undersized caller ceilings and trim optional experts only after the complete-loop floor is protected.
- [x] Cover `axio-fast` light-verify 3/4-call and high-quality `axio-pro` 4/5-call boundaries, plus four-surface public summaries and hash-only trace propagation without provider/model/prompt leakage.
- [x] Refresh standalone engineering receipts after complete-call-budget admission: 256 tests passed, 12/12 dry public protocol cells passed, four provider input adapters passed, and system development remains ready only for separate 21-suite benchmark validation without a superiority claim.
- [x] Enforce runtime preservation of initially committed Judge and Synthesizer calls so optional repair, fallback, and targeted escalation cannot consume the complete-Fusion budget floor.
- [x] Add safe runtime finalization receipts for complete Fusion, reduced-panel Fusion, single-candidate degradation, deferred native tool-call turns, and provider failure before finalization; settle or release unused reservations on every early/failure path.
- [x] Preserve independently produced identical candidates for Judge arbitration while allowing synthesis-side duplicate-answer compression.
- [x] Refresh standalone engineering receipts after runtime reservation/finalization hardening: 260 tests passed, 12/12 dry public protocol cells passed, four provider input adapters passed, and system development remains ready only for the separate 21-suite benchmark-validation phase without a superiority claim.
- [x] Enforce route-time initial complete-Fusion resource admission using the actual assigned expert, Judge, and Synthesizer roles; block known request-cost or p50-deadline overruns before provider execution while leaving unknown telemetry to runtime locks.
- [x] Propagate the hash-only initial-resource admission receipt through all four public API summaries, operator route-plan output, prompt context, execution traces, and shadow-learning features without provider/model/prompt leakage.
- [x] Cover cost-limit rejection, deadline rejection, unknown-telemetry non-rejection, four-surface trace propagation, operator route-plan redaction, and training-feature extraction for the initial-resource admission receipt.
- [x] Extend the HumanEval/IFEval official-harness bridge to run frozen `provider::<sha256>` baseline aliases through their native adapters with private-registry and baseline-freeze binding.
- [x] Bind official-harness sample generation to candidate, registry/profile, deterministic protocol, output budget, metadata, and case-set digests before evaluator import.
- [x] Reject official-harness provider evaluation when a sample directory, candidate alias, registry/profile, generation protocol, or case set drifts; cover the paired provider path with hash-safe regression tests.
- [x] Add a receipt-bound official-harness import bridge for HumanEval/IFEval so completed private scoring runs cannot be manually misbound during benchmark import.
- [x] Extend the receipt-bound official-harness bridge to LiveCodeBench with pinned Parquet parsing, official Generic prompting/extraction, official `codegen_metrics`, explicit isolated-code-execution authorization, generation-output hash binding, and secondary `compile_rate` import.
- [x] Add a receipt-bound MT-Bench pairwise bridge with fixed two-turn dialogue context, official category-scoped judge templates, A/B plus B/A position balancing, conservative disagreement-as-tie scoring, and unparsable-judge failure handling.
- [x] Bind MT-Bench target/comparison generation, pair, judge, scored-row, and import receipts to the same case set, deterministic decoding, candidate registry, provider freeze, and harness pin; reject tampering and raw-content leakage.
- [x] Exercise the MT-Bench bridge across Chat Completions, Responses, Anthropic Messages, and Gemini-compatible Axio surfaces, including multi-turn history ordering and public-surface invocation receipts.
- [x] Preserve Gemini `generationConfig.temperature: 0` during canonicalization and preserve explicit falsy numeric precedence without using truthiness-based fallback.
- [x] Refresh the mechanical-disk official harness pin and MT-Bench offline preflight: six official/audited bridge suites ready, 80 MT-Bench cases, two judge calls per case, cross-provider judge separation, no model calls, and hash-only receipts.
- [x] Refresh standalone engineering verification after the MT-Bench bridge: 285 tests passed and Python compilation passed; no benchmark superiority claim was made.
- [x] Add a resumable hash-bound official-harness campaign driver that executes existing bridge stages, checkpoints after each task, reuses valid imports, preserves private paths/configuration, and supports explicit retry/code-execution gates.
- [x] Rebind the formal source/case manifest to the current official harness pin and regenerate the formal import audit without stale pin-mismatch blockers.
- [x] Bind the formal official-import audit to 40 candidates, 49 run units, and 294 required imports; retain the missing real model-output receipts as explicit blockers.
- [x] Prevent public metadata from setting private Axio execution markers and isolate response-cache entries by exact stop sequences and routing-relevant privacy/tool metadata.
- [x] Prevent Responses text fallback from silently removing native tool declarations or prior tool-turn context.
- [x] Refresh standalone engineering receipts after metadata/cache/tool-compatibility hardening: 294 tests passed, Python compilation passed, dry public protocol and provider-input adapter checks passed, and system development remains separate from 21-suite superiority validation.
- [x] Refresh standalone engineering verification after complete-Fusion smoke and HTTP lifecycle coverage: 298 tests passed, Python compilation passed, the 12-cell dry public protocol check and four provider-input adapters passed, and the refreshed system-development receipt remains engineering evidence only.
- [x] Make live credential preflight recognize arbitrary private registry profiles through the same transport credential resolution as execution, including provider key aliases, without persisting registry paths, env names, endpoints, keys, or model identifiers.
- [x] Add registry-only credential and transport-alias regressions; refresh standalone engineering evidence at 300 passing tests, 12 dry public protocol cells, four provider-input adapters, and a ready system-development receipt without making any model-capability claim.
- [x] Re-run formal 21-suite readiness with the current hash-only source, case, harness, import, and acquisition artifacts; retain its blocked state until authorized GPQA access, 294 real official/audited imports, and externally injected provider credentials are available, with zero provider network calls during preflight.
- [x] Align four public SSE terminal sequences with native Chat Completions, Responses, Anthropic Messages, and Gemini-compatible behavior; cover Anthropic streamed tool JSON input and real local HTTP loopback without persisting prompts or invoking a provider.
- [x] Refresh standalone engineering evidence at 302 passing tests after streaming compatibility hardening; retain the distinction between protocol readiness and benchmark/model-capability validation.
- [x] Project private registry readiness to public health using only safe reason codes, API-format counts, and provider/profile hashes; prevent public health from exposing provider/model/profile identifiers, endpoints, credential environment names, or keys.
- [x] Refresh standalone engineering verification at 303 passing tests and validate the private-registry local health/models loopback with zero provider network calls; retain the distinction between service readiness and 21-suite model-capability validation.
- [x] Attribute circuit failures only to attempted provider calls that fail before a response; ensure local runtime call-budget rejection cannot poison later provider routing or open a circuit.
- [x] Refresh standalone engineering verification at 304 passing tests after circuit-health attribution hardening; retain the distinction between engineering readiness and 21-suite model-capability validation.
- [x] Require an explicit configured operator credential for the raw provider inventory diagnostic endpoint, including when ordinary public API authentication is intentionally absent in local development.
- [x] Refresh standalone engineering verification at 305 passing tests after inventory fail-closed hardening; retain the distinction between engineering readiness and 21-suite model-capability validation.
- [x] Add a bounded in-memory provider telemetry overlay that uses only real transport success/failure and latency observations to calibrate later routing without modifying the registry or using benchmark labels.
- [x] Propagate only hash-safe runtime telemetry summaries into route receipts; prove success/failure adaptation, budget-rejection isolation, circuit separation, and provider/model identifier redaction by regression.
- [x] Refresh standalone engineering verification at 306 passing tests after runtime telemetry routing hardening; retain the distinction between engineering readiness and 21-suite model-capability validation.
- [x] Reconstruct runtime telemetry through strict safe projections for public response route summaries, operator-safe route plans, and durable execution traces; reject malformed profile/provider hashes and unknown health labels rather than relaying them.
- [x] Re-run all standalone verification at 306 passing tests after telemetry receipt propagation; retain the distinction between telemetry observability and benchmark/model-capability validation.
- [x] Preserve assembled expert/Judge/Synthesizer control context across real Chat, Responses, Anthropic, and Gemini provider payloads, including protocol-valid tool-result continuations and exact duplicate-task removal only when native history already carries that task.
- [x] Arbitrate native public tool calls as complete plans before panel repair, reject calls from roles without public tool declarations, preserve the selected original call id, canonicalize to caller-declared schema names, return valid targeted-escalation tool turns before redundant Judge/Synthesizer work, and expose only hash/count arbitration receipts across all four public API formats.
- [x] Support tenant-isolated Responses `previous_response_id` continuation with bounded process-memory TTL/session/context controls, omitted model/instruction/tool inheritance, native tool-call/result ordering, cache-hit ID renewal, `store:false`, uniform unavailable-ID errors, and no continuation data in traces, artifacts, or runtime snapshots.
- [x] Re-run standalone Fusion verification after Responses continuation support: 314 tests passed and compilation passed; refreshed hash-only system-development readiness is ready for the separate benchmark-validation phase with zero network calls. No benchmark score, latency claim, or model-superiority claim was made.
- [x] Validate arbitrary provider base URLs before readiness, discovery, or transport; reject unsafe URL components without persisting the value.
- [x] Refresh standalone engineering evidence after provider URL validation and external top-three screening hardening: 335 tests passed, compilation passed, four public protocol cells and four provider input adapters remain dry-ready, and live readiness remains explicitly blocked only by external benchmark/probe prerequisites.
- [x] Add cooperative cancellation for timed-out parallel expert waves; discard late provider results from Judge/synthesis while retaining hash/count-only deadline receipts.
- [x] Cover pre-call cancellation and late-result discard in the standalone regression suite.
- [x] Bind formal scorecard top-level provider comparison to the frozen configured-provider-pool rank 1 candidate; keep suite-observed highest-score provider data diagnostic-only when external ranking is active.
- [x] Add an authorized-source-only GPQA Diamond CSV materialization adapter with fixed per-case option ordering, avoiding source answer-position bias while preserving identical option maps across candidates.
- [x] Require the GPQA materializer to fail closed unless the private acquisition manifest explicitly marks the authorized official CSV as downloaded; refresh standalone verification at 336 passing tests, compilation, four-surface protocol, and four-format provider-adapter checks with zero provider calls.
- [x] Refresh standalone verification after formal artifact cohort binding: 341 tests passed, compilation and diff checks passed, and current mechanical-disk readiness correctly blocks the legacy mixed/exhaustive artifact set.
- [x] Correct Fusion stage latency comparison to use the actual direct-route baseline; add provider-diversity-preserving expert replacement with a 2.5x operational headroom target, bounded quality tolerance, and hash-safe public/trace receipts.
- [x] Refresh the private live cohort after excluding the current failed provider profile; run isolated complete-Fusion deliberation smoke for both Terra and Pro with bounded operator credentials. Terra and isolated Pro completed Expert -> Judge -> Synthesizer; a back-to-back two-tier run showed provider contention and remains diagnostic only.
- [x] Run one contention-free combined complete-Fusion deliberation smoke against the current private live registry; `fusion_deliberation_live_smoke_terra_pro_combined_v3_2026-07-18.safe.json` passed both Terra and Pro through Expert -> Judge -> Synthesizer. Earlier contention/deadline failures remain preserved as diagnostics; this is orchestration evidence only, never a benchmark or superiority result.
- [x] Preserve the full bounded Fast primary timeout when observed serial fallback p50 plus a 150 ms safety margin cannot fit in the same request deadline; expose only hash-safe cascade headroom, projected latency, and reservation-skip receipts.
- [x] Add bounded, redacted failed-public-smoke diagnostics that distinguish provider recovery exhaustion from budget/deadline gating without persisting raw error text, provider identifiers, URLs, prompts, outputs, or secrets.
- [x] Refresh standalone engineering verification after the Fast headroom and smoke-diagnostic hardening: 356 tests passed, compilation and diff checks passed, all 12 dry public protocol cells and all four provider-input adapter families passed with zero network calls, and `fusion_system_development_readiness_356.safe.json` is ready for the separate 21-suite validation stage. No benchmark score, latency-superiority, or model-superiority claim was made.
- [x] Preserve current bounded public live-smoke evidence without retry laundering: the current-registry v4 run was 11/12 and v5 was 10/12, with transient Chat provider execution failures; a separate one-profile, one-attempt-per-key Chat health probe later succeeded in 872.336 ms. These are operational diagnostics only and do not establish stable public API availability or benchmark capability.
- [x] Perform a bounded external provider-identity and ranking-source scout. Official/canonical identity evidence and one common independent capability source were found, but no second common rank source covering all four live candidates; preserve the unfilled external-ranking template and do not infer a top-three order from aliases, registry priors, or target-suite data.
- [x] Add file-backed arbitrary provider configuration through `AXIO_FUSION_PROVIDER_CONFIG_FILE`, with environment-variable-name validation and hash-only readiness projection.
- [x] Run controlled live enrollment against the current three-channel portfolio: 141 directory candidates discovered, 40 fixed short probes available, 26 Chat profiles and 14 Responses profiles admitted to a private runtime registry; no benchmark prompt or label was used.
- [x] Add bounded latency-constrained panel search with a fixed direct baseline, Pro's three-expert minimum, quality tolerance, hard 3x guard, and explicit provider-diversity-relaxation receipt.
- [x] Re-run the full standalone regression after latency panel admission: 361 tests passed, compilation passed, and the real 40-profile registry completed bounded Terra/Pro orchestration replay within the recorded p50 guard.
- [x] Add a forced native-tool operational probe that reuses all four upstream adapters, classifies native calls/text-only/protocol/transport outcomes, and never uses benchmark cases or labels.
- [x] Add hash-only tool-probe redaction, CLI commands, and registry calibration that updates `supports_tools` only from operational tool evidence while keeping benchmark calibration blocked by default.
- [x] Extend the explicit convenience configuration aliases to the current TokenAPIs Responses channel while retaining arbitrary file-backed provider configuration.
- [x] Enroll the current three-channel portfolio from live `/models` directories: 141 candidates, 43 text-available profiles, 28 native-tool profiles, and 15 text-only/non-tool profiles in the calibrated private registry.
- [x] Run the current calibrated registry through the four-surface live public smoke and complete Fusion deliberation probe; preserve the 11/12 surface result as an operational stability blocker, while the latency-prioritized panel now completes Terra/Pro Expert -> Judge -> Synthesizer (2/2) without making a benchmark claim.
- [x] Refresh focused regression verification after tool calibration: 118 selected tests passed, full standalone suite remains covered by the prior 378-pass run, and compilation passes.
- [x] Preserve live-probe generation/readiness/source metadata when writing a calibrated serving registry; the calibrated 43-profile registry now passes the strict probe-evidence audit with 28 operational tool-capable profiles.
- [x] Refresh current engineering receipts: 378 standalone tests, 12/12 dry public protocol cells, four provider input adapters, remote-only execution audit, and system-development readiness for the separate 9-category/21-suite validation phase.
- [x] Reorder latency-constrained panel tie-breaking to prefer lower estimated execution latency before provider-count diversity once the quality floor is fixed; preserve an explicit diversity-relaxation receipt and verify the change with regression.
- [x] Add generic `enroll-providers` control-plane orchestration for arbitrary four-protocol channel manifests, including discovery, text probe, registry generation, native-tool calibration, and no-partial-promotion behavior.
- [x] Add a non-secret current-channel environment contract for CPA Plus Responses, NVIDIA Chat Completions, and TokenAPIs Responses; keep all endpoint/key values process-injected and absent from source/artifacts.
- [x] Count provider configuration rows rejected by environment-name/transport safety validation instead of reporting them as usable channel configuration.
- [x] Cover enrollment blocking, successful operational calibration, environment restoration, invalid-row redaction, CLI registration, and full standalone regression.
- [x] Accept the actual full standalone `PYTHONPATH=src ... pytest -q tests` command in code-test readiness receipts and refresh the persisted receipt/readiness at 382 passing tests.
- [x] Normalize common four-protocol manifest aliases, accept string and object forms from compatible `/models` directories, and expose a first-class `--provider-config-file` CLI input without weakening secret-value rejection.
- [x] Add local HTTP contract tests for all four upstream protocols, model discovery, protocol-specific auth/response parsing, and multi-key transport rotation; refresh standalone verification at 386 passing tests.
- [x] Bound Responses typed fallback and semantic empty-response retry to one logical provider-turn deadline; cover remaining-time behavior and configurable Gemini authentication headers.
- [x] Add a network-free `provider-config-summary` command for arbitrary four-protocol manifests; keep its output hash/count-only and secret-free.
- [x] Add long-running CLI dynamic manifest startup with explicit discovery/enrollment modes, live-only enrollment guard, healthy-profile admission, and optional hash-only enrollment receipt output.
- [x] Make the documented `auth_scheme: none` transport path truly generic: allow a no-key manifest, preserve no-auth headers through model discovery and POST requests, and expose key-required readiness without changing authenticated channel rotation.
- [x] Download and hash the current non-target LiveBench/SimpleBench source snapshots on the mechanical disk; preserve the incomplete coverage blocker instead of inferring baseline ranks.
- [x] Make a supplied provider manifest authoritative: provider-level configuration without discovered/static models no longer falls back to the portable default registry; add blocked-readiness, summary, and secret-leak regressions.
- [x] Refresh standalone engineering receipts at 399 passing tests, compile the full source tree, revalidate 12/12 public dry protocol cells and 4/4 provider input adapters, and refresh current hash-safe readiness pointers.
- [x] Acquire the official LiveBench 2026-06-25 test/leaderboard parquet snapshots and commit-pinned scorer source on the mechanical disk; record 1,436 official test cases without using target-suite labels or provider results.
- [x] Acquire and exact-match audit a dated LMSYS/Chatbot Arena leaderboard snapshot as an independent source candidate; preserve the 2/37 canonical identity coverage result and do not infer aliases.
- [x] Add the process-local generic runtime channel loader for arbitrary base URLs, API keys, model-level endpoint/key overrides, multi-key pools, and strict Chat Completions/Responses/Anthropic/Gemini protocol resolution; keep direct credentials out of safe profiles and persisted artifacts.
- [x] Add `FusionEngine.from_runtime_channels` and direct `/models` discovery for secret-manager-owned manifests without mutating process environment; cover four-protocol discovery, auth headers/query parameters, response parsing, and text probe through a real local HTTP fixture.
- [x] Validate the current CPA Plus, NVIDIA, and TokenAPIs channels through the process-local runtime path: 12, 119, and 9 models were discovered respectively, with 140 candidates and no persisted credentials; discovery is not treated as proof that every candidate has passed a serving probe.
- [x] Run a bounded one-model-per-provider live text probe through the same runtime profiles: 3 candidates were selected, 2 returned the fixed health response, and 1 failed; the failed candidate remains excluded from promotion and is available only as a transport diagnostic.
- [x] Refresh standalone engineering receipts after generic runtime channel integration: 408 tests passed in 152.30 seconds and source compilation passed; no benchmark or model-superiority claim was made.
- [x] Refresh standalone engineering receipts after the end-to-end four-protocol gateway and dynamic CLI startup regression: 417 tests passed, compilation passed, 12/12 public protocol cells and 4/4 provider input adapters remained ready, and no benchmark/superiority claim was made.
- [ ] Complete a full-pool, pre-registered non-target ranking campaign with at least two common independent source families and exact channel-to-canonical identity attestations before freezing ranks 1/2/3. The 8,580-call plan and zero-call preflight are frozen, but the current process has 0/6 referenced secret environment values and therefore 0/45 live-ready replica profiles; do not replay credentials from chat or start a partial cohort.
- [x] Implement the GPQA gated acquisition boundary: fixed official revision,
  byte count, row count, and Git blob; explicit no-example-leakage acceptance;
  environment/secret-resolver-only token access; HTTPS Hugging Face redirect
  allowlist with cross-origin Authorization removal; local-10808 proxy support;
  private atomic artifact/manifest commit; content-free failure receipts; and
  per-materialization authorization/hash/blob/schema revalidation. Ten focused
  synthetic regressions and the existing deterministic option-order regression
  pass; complete standalone verification is 515 passed in 170.02 seconds.
- [x] Refresh the 2026-07-21 engineering evidence after the transaction
  rollback regression: 515 standalone tests passed, compilation passed, all
  12 dry public protocol cells and all four provider input adapter families
  passed without provider calls, and the remote-only audit reports 30 source
  files, zero forbidden imports, zero local model artifacts, and zero audit
  network calls. Keep this separate from live model evaluation and superiority
  claims.
- [ ] Obtain authorized GPQA Diamond access and bind its official source/case manifest by running `benchmark-acquire-gpqa-diamond` after the operator accepts the current upstream terms and injects `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN`. Do not substitute a non-GPQA dataset or use an older public archive to bypass the gate. Revision `633f5ee89ab8ad4522a9f850766b73f62147ffdd` remains access-gated in the current process.
- [ ] Run or import official/audited model-output receipts for LiveCodeBench, HumanEval, BFCL, tau-bench, IFEval, and MT-Bench-style judging.
- [ ] Complete a pre-registered stable bounded public API live-smoke window against the current private live registry. The dry 12-cell protocol check passes, but current live evidence is v4=11/12 and v5=10/12 with intermittent Fast/Terra Chat provider execution failures; neither result may be represented as a stable protocol-shape pass. Failure artifacts contain no raw URLs or API-key-like strings; this is engineering evidence only, not a benchmark or superiority claim.
- [ ] Execute 21-suite benchmark campaign when provider credentials and gated dataset access are ready.
- [ ] Iterate Fusion algorithms if Axio tiers do not beat corresponding single-model baselines or exceed 3x latency.
- [x] Close process-local/file-backed provider manifest parity: resolve
  `models_env`/`modelsEnv` model lists, merge static and environment model rows
  deterministically, and accept sequence-valued key pools from secret
  resolvers without persisting credentials.
- [x] Verify the supplied three-channel runtime portfolio through direct
  process-local discovery: CPA Plus Responses 12 models, NVIDIA Chat
  Completions 119 models, TokenAPIs Responses 9 models; 140 profiles and 132
  canonical groups, including 8 two-replica groups. This is discovery and
  routing-input evidence only, not a capability benchmark.
- [x] Refresh standalone engineering verification at 432 passing tests,
  source compilation passed, 12/12 dry public protocol cells passed, four
  provider input adapters passed, and remote-only execution audit passed.
- [x] Complete the full standalone Fusion regression after Hermes MoA process
  aggregation changes: 456 tests passed in 186.35 seconds; source compilation
  and diff checks passed; code-test and system-development receipts were
  refreshed. This is engineering evidence only and does not claim benchmark
  superiority.
- [x] Audit and reconcile the current baseline state: 45 live provider
  profiles represent 39 canonical model groups; mark the stale profile-counted
  ranking template for regeneration and preserve the baseline gate as
  partially verified rather than accepted.
- [x] Implement the executable `baseline-screening-plan`,
  `baseline-screening-run`, and `baseline-screening-to-ranking` workflow with
  canonical replica deduplication, exact `/models` identity attestation,
  private raw-output units, hash-only checkpoints, wrong-answer no-retry,
  transport failover, deterministic confidence intervals, and official raw-
  output re-scoring before ranking conversion.
- [x] Freeze a seed-derived, source-interleaved, paired-reverse task schedule
  before provider calls and bind its digest into plan, resume, and ranking
  conversion so a long campaign cannot silently use source-major model order.
- [x] Add active tamper regressions that forge private outputs or safe scores
  and recompute outer digests; require the official re-score/private aggregate
  checks to reject both attacks.
- [x] Regenerate the current full-pool screening v2 plan and zero-network
  preflight: 39 canonical groups, 45 replicas, 45/45 exact catalog bindings,
  112 MMLU-Pro plus 108 LiveBench cases, 78 units, and 8,580 estimated calls;
  plan digest
  `5b206e7eb2439e2ab8deccb34ae62e1d6616f84a71331aefe48bdd4dd07f8c1a`,
  schedule digest
  `78ed0c8cc398596fc1ffae176af69dae3d3ed2d3254c8b1bf6662a779f5f1a8a`,
  and exact plan-file hash
  `7fd1fa6536c3332992f407b67f7c2a7934751f746b873046537bd80a26771d33`.
- [x] Bind baseline-screening resume state to mode, exact plan-file content,
  live credential readiness, private-root identity, endpoint identity, client
  transport cohort, and planned task count; reject preflight/live state mixing
  and forged checkpoints before the first resumed provider call.
- [x] Re-audit Hermes MoA process aggregation against NousResearch
  `hermes-agent` commit `e89bc58a5ba80ec6be19b43beca37cbb03091afd` and carry
  prior tool actions plus bounded result previews into reference waves as
  inert text across all four inbound protocols, while preserving tool-schema
  isolation and the acting Synthesizer's complete transcript.
- [x] Refresh the complete standalone Fusion regression and compilation after
  baseline-screening v2 and Hermes process hardening: 480 tests passed in
  167.88 seconds; compilation, 12/12 dry public protocol cells, 4/4 upstream
  adapters, remote-only audit, runbook generation, and system-development
  readiness all passed.
- [x] Require the Hermes acting Synthesizer even under high reference
  consensus; preserve a bounded best-reference fallback for empty synthesis
  while marking the process degraded, and mark failed feedback without a
  re-Judge as process-incomplete in runtime, trace, learning, and smoke receipts.
- [x] Separate the initial Judge's feedback requirement from feedback candidate
  existence and successful output. A required but unscheduled feedback call is
  process-incomplete across text, acting-tool, safe-trace, and learning paths;
  a required feedback path completes only after successful output, re-Judge,
  and accepted acting synthesis. Focused Hermes regression: 17 passed; full
  standalone regression: 484 passed in 164.24 seconds.
- [x] Make response caching fail closed on Fusion and Hermes process receipts:
  admit only successful direct finals or complete non-degraded Fusion finals,
  require a completed Hermes process contract when enabled, reject degraded
  feedback/Synthesizer/tool turns, bind replay to the current route-contract
  shape, and preserve a hash-safe origin receipt in trace and learning paths.
  Current verification: 484 tests passed in 189.33 seconds; compilation,
  12/12 public dry protocol cells, 4/4 provider adapters, remote-only audit,
  runbook, and system-development readiness passed without network calls.
- [x] Harden official-campaign admission around the externally ranked top-three
  freeze: reject the stale 41-profile exhaustive diagnostic freeze, permit only
  Axio-only zero-model-call preflight before a valid freeze exists, and require
  a validated canonical rank-1/rank-2/rank-3 freeze for every live or provider
  candidate task. The real official-harness preflight prepared 48/48 Axio cells
  across LiveCodeBench, HumanEval, BFCL v3, and IFEval with zero model calls;
  the stale-freeze live guard blocked at zero processed tasks and zero network
  calls. The legacy four-surface MT-Bench fixture was upgraded to the same
  externally ranked top-three contract. Official admission now recomputes the
  complete external-ranking mapping and rejects frozen-row, selected-set, or
  external-receipt substitution even when inner and outer digests are
  recomputed. The complete standalone regression now passes 489 tests in
  190.45 seconds. Compilation, 12/12 dry public protocol cells, 4/4 provider
  adapters, the remote-only audit, runbook, and refreshed system-development
  readiness all pass without network calls.
- [x] Preserve configured reference-slot order across parallel completion and
  perform bounded same-canonical replica failover inside the original Hermes
  advisor role. Replica retries remain tool-free, consume independent runtime
  budget, and never count as additional cognitive evidence; a replica blocked
  before provider execution is not counted as an attempt. Focused
  Hermes/Fusion regression: 41 passed; complete standalone regression: 492
  passed in 191.73 seconds.
- [x] Treat projected tool evidence and every Hermes reference/candidate packet
  as untrusted data with no instruction authority. Enforce the boundary in
  reference, Judge, and acting-Synthesizer prompts; emit machine-readable packet
  trust labels and a safe `context_authority_policy` receipt. Focused
  Hermes/Fusion regression remains 41/41; complete standalone regression passes
  492 tests in 182.85 seconds, compilation and system-development readiness pass.
- [x] Tighten Responses public compatibility around the current protocol
  contract: non-stream Responses objects now expose public `background`,
  `service_tier`, `text.format`, `truncation`, and token-detail fields; the
  Responses SSE lifecycle now carries monotonic 1-based `sequence_number`
  values plus `response_id`/`call_id` on function-argument events; the Chat
  `stream_options.include_usage` trailer is covered at the server boundary and
  remains Chat-only. Verification on Monday, July 20, 2026: targeted protocol
  regression 6 passed, complete standalone regression 497 passed in 211.24
  seconds, `compileall` passed, and refreshed hash-only code-test plus
  system-development-readiness receipts were regenerated with zero provider
  network calls.
- [x] Re-run the pre-registered non-target full-pool screening preflight and
  the formal 21-suite strict campaign preflight after the 497-test engineering
  refresh. The screening plan remains digest-stable at 39 canonical groups,
  45 replicas, 78 source/model units, and 8,580 estimated calls; fresh
  preflight is `preflight_ready` with zero network/target-suite calls and 0/45
  process-injected credential-ready replicas. The formal campaign remains
  `live_preflight_blocked` with `provider_call_count=0`; protocol, provider
  input, and system-development receipts pass, while execution is correctly
  blocked by the unfinished external top-three freeze, GPQA/source-case
  completeness, official harness imports, and a missing public Axio gateway.
- [x] Align Hermes MoA 2.0 with the current upstream source commit
  `e89bc58a5ba80ec6be19b43beca37cbb03091afd`: add per-seat cognitive-budget
  contracts, bounded Terra/Pro Judge output caps, acting-Synthesizer budget
  preservation, `per_state_iteration` fanout receipts, and capability-attested
  forwarding for provider-private reasoning fields. Focused Hermes regression:
  20 passed before the complete-suite refresh. This remains engineering
  evidence only; no benchmark or superiority claim is implied.
- [x] Lock the Hermes state-advance rule with an end-to-end cache regression:
  identical completed state replays without provider calls, while a newly
  appended tool result changes the state fingerprint, re-runs every reference
  slot, and reaches advisors only as bounded inert text. Focused Hermes
  regression: 21 passed; complete standalone regression: 504 passed in 167.69
  seconds; compilation and refreshed system-development readiness pass.
- [x] Complete the standalone regression after the Hermes refresh: the core
  file passed 370 tests and the remaining modules passed 128 tests, for
  498/498 passing tests; compilation passed, the hash-only code-test receipt
  was refreshed, and system-development readiness remains true with zero
  provider calls. This is engineering evidence only.
- [x] Re-run the formal zero-network live preflight after the 498-test refresh:
  the 9-category/21-suite methodology contract is satisfied, but readiness
  correctly remains blocked by zero process-injected credentials, incomplete
  benchmark/official-import artifacts, and the missing externally ranked
  canonical top-three freeze. Provider call count remains zero.
- [x] Make provider decoding protocol-neutral when temperature is omitted:
  Chat, Responses, Anthropic, and Gemini adapters no longer inject an
  unsupported default `0.2`; explicit `0.0` remains forwarded. Add request-body
  regressions for all four formats and refresh the standalone engineering
  receipt at 499 passing tests.
- [x] Enforce model-scoped runtime credential precedence over channel defaults
  for both direct values and secret-resolver references. Verify resolver-backed
  endpoint selection, sequence-valued key pools, same-turn key failover,
  discovery, enrollment, atomic refresh, exception redaction, and safe
  serialization through a real local HTTP fixture. Complete standalone
  verification: 503 tests passed in 168.34 seconds; `compileall` passed and the
  system-development readiness receipt was refreshed without provider calls
  or a benchmark-superiority claim.
- [ ] Freeze the externally evidenced rank-1/rank-2/rank-3 canonical model
  groups before any target-suite provider calls.

- [x] Refresh the standalone engineering evidence after the Hermes budget
  regressions and operator-summary hardening: `527` tests passed in the
  complete `axio_fusion_api` suite, source compilation passed, the remote-only
  audit remains clean, and the system-development readiness receipt remains
  `10/10`. The provider configuration summary now emits a safe persisted
  readiness artifact with credential/profile counts and protocol counts, while
  retaining zero secret, URL, model-id, prompt, and provider-output
  persistence.
- [x] Enforce a task-format-specific benchmark prompt projection so scoring
  fields never enter built-in model prompts; emit hash-only prompt contracts,
  validate structural violations, and cover all six built-in prompt formats
  with unique sentinel regression cases.
- [x] Refresh engineering evidence after the prompt-contract hardening:
  519/519 standalone tests passed, compilation and remote-only/four-format
  audits passed with zero network calls, and system development is ready for
  the separate 9-category/21-suite benchmark validation phase.
- [x] Re-run the six official/audited bridge preflights against the current
  pinned harness manifest: LiveCodeBench, HumanEval, BFCL, and IFEval are
  preflight-ready; tau-bench and MT-Bench remain explicitly blocked by their
  independent runtime/gateway or comparison/judge prerequisites. All six
  preflights performed zero model/evaluator calls and produced no scores.
- [x] Complete the pre-Fusion available-model handoff: preserve the full
  research-prior ranking, require measured live streaming latency and a valid
  output digest, exclude profiles over 90 seconds (or without a measurement),
  emit contiguous available ranks plus same-canonical replica bindings, and
  fail closed on binding/logical-list tampering. Standalone verification:
  `557` tests passed and compilation passed; no live provider call was made.
- [x] Replace the single oversized pre-Fusion research request with bounded
  candidate batches, deterministic full-pool merge, hash-only per-batch
  receipts, and fail-closed batch coverage. Expose batch size/concurrency in
  non-secret config, CLI, service startup, and runtime enrollment. Focused
  screening verification: 21 passing tests, with exact per-shard candidate
  prompts, a bounded one-retry recovery path, and no provider probe after a
  retry-exhausted research batch. The default shard size is 4.
- [x] Repair and verify the live streaming-evidence projection from provider
  transport receipts into pre-Fusion probe rows. The latest live run observed
  SSE for all 39 admitted profiles and generated a ready private registry;
  no ordinary JSON fallback was promoted.
- [x] Make configuration-driven `/models` discovery return process-local
  profiles to the pre-Fusion workflow, require a complete provider inventory
  before Research Agent or stream-probe execution, and block partial/empty
  discovery without explicit static models.
- [x] Harden pre-Fusion safe artifacts so discovered `model_ids` and
  provider/model aliases are hashed or removed, with regression coverage for
  discovery inventory handoff, downstream fail-closed behavior, and redaction
  markers.
- [x] Run the complete configured-provider pre-Fusion v2 handoff: 139/139
  `/models` profiles discovered, 35/35 research batches validated with the
  capability-axis gate, 139/139 strict live probes executed, 32 profiles
  admitted, 23 profiles excluded by the 90-second gate, no JSON fallback
  promoted, and the operational registry/catalog/report validators plus
  `load_registry` all passed.
- [x] Add the single `build_prefusion_fusion_handoff()` boundary used by
  runtime enrollment to extract the validated latency-filtered logical model
  list; reject edited or incomplete reports, keep same-model replicas as
  failover-only, and provide a hash-only redacted projection. Standalone
  regression now passes 608 tests.
- [x] Replace one-sample production stream admission with a bounded
  multi-sample stability contract: default three strict SSE/NDJSON samples per
  physical profile, all within 90 seconds; bind hash-only sample receipts and
  aggregate p50/p95/max latency into the registry; reject a single-sample
  production configuration; and propagate the setting through CLI, dynamic
  enrollment, and atomic refresh. The stopped v8 baseline campaign remains
  historical and cannot supply ranking or capability evidence.
- [x] Harden adaptive channel recalibration fingerprints: include only
  allowlisted model capability, reasoning/tool/vision, latency/cost and
  endpoint-binding hashes; ignore API-key rotation; add regressions for
  capability/transport/endpoint changes and credential-only changes. This
  remains an offline shadow calibration signal and never auto-modifies the
  production router or benchmark policy.
- [x] 将自适应渠道校准提升为 hash-only receipt 契约：渠道变化没有 operational
  scores 时固定 `blocked`；有 scores 但缺少 registry/workflow/rollback/prompt-pack/
  contamination 任一绑定时仍 `blocked`；完整绑定最多 `shadow_candidate`，保持
  `activation_ready=false`、人工审批和自动激活关闭。CLI 不再持久化
  `recalibration_prompt` 原文，只写 prompt/decision/channel digest。
- [x] 为 receipt/CLI 增加 14 条回归（blocked、not_required、digest mismatch、完整
  binding shadow candidate 与 raw prompt/provider/secret redaction）；本轮全量回归
  `1081 passed, 7 skipped`，`py_compile`、`compileall`、导入和 `git diff --check`
  均通过。没有 provider/target 网络调用，也没有修改 r18 frozen 输入。
- [x] 为校准 CLI 增加五类本地 artifact 绑定入口（registry/profile-set、rollback、
  prompt-pack、workflow、contamination-audit）：只读取 SHA-256，要求五类成组提供，
  部分绑定 fail-fast；完整绑定和得分证据可生成 `shadow_candidate`，仍禁止自动激活。
  新增回归覆盖真实 artifact digest 比对与 partial-binding rejection；全量回归
  `1083 passed, 7 skipped`，没有 provider/target 网络调用。
