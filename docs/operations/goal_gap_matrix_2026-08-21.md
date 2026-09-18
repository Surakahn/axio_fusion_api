# Axio Fusion Goal 差距矩阵（2026-08-21）

## 用途与证据边界

这份矩阵是每轮交接前的状态锚点，用来回答三个问题：产品已经真正完成什么、当前
阻塞在哪里、下一步怎样在不污染冻结证据的前提下收敛到最终 Goal。它不是 benchmark
结果、provider 排名或 superiority claim，也不授权任何新的网络请求。

当前 Goal 的产品定义仍是 remote-only Fusion API：通过可复用 prompt、路由、角色
编排、Judge/Synthesizer、fallback、成本/延迟/并发预算、安全和可观测性，把远程
provider 能力组合成 `axio-fast`、`axio-terra`、`axio-pro`。Harness 只负责评测、
控制、恢复和证据链；不得把 benchmark 标签或结果自动写回生产路由。

本矩阵引用的当前锚点：

- Goal：active，thread `01a0202d-8062-7832-b894-af9ec8bebd06`。
- 产品/评价合同：`docs/axio_fusion_api_product.md`、
  `docs/axio_fusion_benchmark_methodology_21_suites.md`。
- 单向 gate：`docs/operations/convergence_execution_path_r20.md`。
- 当前 successor：`private/runs/2026-08-21-composite-cohort-r18/`。
- r18 plan SHA-256：`58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`。
- r18 plan digest：`a626b9be599041b03c899880eee0fb10be7b7a7b5f22f2f0ccef95ad204cbf86`。
- r18 source SHA-256：`3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`。
- r18 preflight：`preflight_ready`，`network_calls_performed=false`，
  `target_suite_calls_performed=false`，`ready_for_ranking=false`。
- 当前 credential-ready 零网络预检已独立生成并与 r18 plan/source/r7 registry hash 绑定；
  9/9 required profiles ready，但它不授权 live screening，也不代表任何 provider 能力。
- 2026-08-26 新增 formal Harness execution gate successor：
  `private/runs/2026-08-26-composite-cohort-r18-harness-formal-gate/`。它只验证控制面
  语义，不覆盖 2026-08-21 旧 artifact；当前 execution plan 因缺少 provider freeze
  明确为 `blocked`。
- 当前服务只读健康：`ready`（提交 `bfae5ac` 发布后 PID `2576971`；运行时代码来自 `4d56422`），公共模型为三档，四种协议可用，`auto -> proxy`，
  生产 loopback 为 `127.0.0.1:18900`，当前 serving registry 为 r7 probe-bound。
- 当前 serving registry 身份已只读复核：21 个 physical profiles、15 个 logical
  models、21 个 live-available profiles、4 个 providers，且与 18900 进程的
  `AXIO_FUSION_REGISTRY_PATH` 绑定一致；AGENTS 中 r43 的 10-profile 数字仅是历史
  阶段检查项，不作为当前 r7 serving blocker。
- 当前工程回归：`1142 passed, 0 skipped`（本轮图片成本计量专项与此前每日预算关闭状态投影、预算窗口恢复可观测性、非正 rate-limit 状态投影、rate-limit 窗口恢复可观测性、多路径错误投影一致性、四协议错误码一致性、流式断开资源释放、显式
  fail-closed 鉴权、租户并发与此前路由/r18 binding/convergence 安全修复均通过）；这是代码
  契约证据，不是能力或质量证据。

2026-09-19 每日预算窗口恢复可观测性增量：runtime budget tenant 快照新增
`retry_after_seconds`，与预算错误响应共享 UTC 日界语义；未超限或关闭配置为 `0`，达到
预算时提供 hash-safe 恢复提示，日界切换清理旧预算行。代码提交 `5047e76`，全量回归
为 `1135 passed`；发布后 Axio PID `2645665` 为 `ready/healthy`、`21/21` eligible、
`0` circuit、`21/15` physical/logical、`4` providers、`auto -> proxy`，三档 route-plan
通过。本增量不改变 provider I/O、r18 frozen inputs、screening、ranking 或 benchmark 授权。

2026-09-19 rate-limit 窗口恢复可观测性增量：runtime bucket 快照新增
`retry_after_seconds`，与错误响应保持同一 60 秒窗口语义；未超限或关闭配置为 `0`，达到
限额时提供 hash-safe 恢复提示。代码提交 `1de8fbf`，全量回归为 `1133 passed`；发布后
Axio PID `2627249` 为 `ready/healthy`、`21/21` eligible、`0` circuit、`21/15`
physical/logical、`4` providers、`auto -> proxy`，三档 route-plan 通过。本增量不改变
provider I/O、r18 frozen inputs、screening、ranking 或 benchmark 授权。

2026-09-19 r18 preflight 可复现复核：加载生产一致环境并显式设置 `PYTHONPATH=src` 后，
verifier 保持 `ready_for_operator_authorization`、`reason_codes=[]`，且 provider/target
调用均为 `false`；重复 receipt 与既有 receipt SHA-256 完全一致。该复核确认 frozen
plan/source/registry 与 credential-ready preflight 未漂移，但不授予 live screening
授权，外部凭据轮换和 operator 授权门仍保持不变。

2026-09-19 商业运维增量：新增显式 `AXIO_FUSION_REQUIRE_AUTH=true` fail-closed 模式。开启
后若没有公共 key，包含 health 在内的公共请求统一返回 401；配置 key 后继续使用
constant-time 精确匹配，health 只输出 `auth_required`/`auth_mode` 等安全投影。当前
18900 保持关闭以兼容既有 loopback 客户端；正式公网切换仍需部署方配置真实公共/operator
key 并完成外部流量验证。本增量不改变 provider I/O、r18 frozen inputs、screening、
 ranking 或 benchmark 授权。

2026-09-19 图片 lane 成本计量增量：修复图片 SSE 成功后硬编码 `0.0`、buffered 图片无
成本观察及 text prompt composer 成本遗漏。新增 profile-bound generation/editing 价格
metadata 与 bounded estimator；可信价格才累计，unknown 保持 `cost_usd=null`，失败/取消
不计成功图片成本。图片专项 `41 passed`；当前 verified image registry 未声明价格，故
生产图片预算仍明确为 unknown，不构成成本优势证据。详见
`docs/handoffs/2026-09-19_image_cost_accounting.md`。

2026-09-19 流式资源生命周期增量：新增真实 HTTP 客户端在首个 SSE delta 后断开的端到端
回归。测试确认 cancellation 传播到 fake provider，后续 delta 不再写入已断开的客户端，
且租户 in-flight lease 在 handler 收尾后归零。流式专项 `23 passed`、全量 `1123 passed`；
这是运行时资源与故障恢复证据，不改变 provider I/O、r18 frozen inputs、screening、
ranking 或 benchmark 授权。

2026-09-19 四协议错误码一致性增量：公共流式错误现在在 Chat/Responses/Anthropic/Gemini
均保留 bounded Axio machine code；Anthropic 放在 `error.code`，Gemini 放在固定 namespace
的 `error.details[].code`，同时保留原生 framing 和 Gemini 数值 HTTP code。专项 `27 passed`，
不改变 provider I/O、r18 frozen inputs、screening、ranking 或 benchmark 授权。

2026-09-19 租户每日预算重置提示增量：预算超限响应现在根据 UTC 日界统一提供
`Retry-After`，buffered 文本、文本 SSE、图片 SSE 都能获得可执行的恢复时间提示；不改变
预算金额、成本累计、租户隔离或 admission 阈值。本增量只证明商业级成本 admission 的
错误恢复契约，不构成 provider 能力、排名、成本优势或 superiority 证据。

2026-09-19 每日预算关闭状态可观测性修复：当 `AXIO_FUSION_TENANT_DAILY_BUDGET_USD=0`
时，runtime snapshot 现在报告 `tenant_budget_enabled=false`，与实际“不限制预算”语义
一致；零值不会触发预算 admission，也不会产生重试等待。本增量只校正运维投影，不改变
provider I/O、r18 frozen inputs、screening、ranking 或 benchmark 授权。

2026-09-19 非正 rate-limit 配置状态可观测性修复：当
`AXIO_FUSION_RATE_LIMIT_PER_MINUTE<=0` 时，runtime snapshot 现在报告
`rate_limit_enabled=false`，与实际不限流语义一致；零值/负值不会触发 rate-limit admission，
也不会产生重试等待。本增量只校正运维投影，不改变 provider I/O、r18 frozen inputs、
screening、ranking 或 benchmark 授权。

发布验证（commit `4d56422`，Axio PID `2576971`）：`/health=ready`、runtime routing
`healthy`、`21/21` eligible、`0` circuit、`21/15` physical/logical、`4` providers、
`auto -> proxy`；Fast/Terra/Pro route-plan 分别为 `fast_direct_cascade`、`terra_direct`、
`pro_panel_judge_escalation`。全量回归 `1131 passed`。CPA Plus 未重启，provider screening、
ranking、baseline freeze 与 target benchmark 仍按授权门禁保持 withheld。

2026-09-19 rate-limit 多路径错误投影增量：buffered 文本、文本 SSE 与图片 SSE 的
`rate_limit_exceeded` 现在统一包含 `metadata.rate_limit`、安全持久化标志和
`Retry-After`，调用方可跨执行路径读取一致的限流窗口与重试信息。专项 parity `2 passed`，
全量工程回归更新为 `1128 passed`。本增量只证明网关 admission/error contract 一致性，
不改变限流计数、租户身份 hash、budget、in-flight admission、provider I/O、r18 frozen
inputs、screening、ranking 或 benchmark 授权。

此前工程回归：`1116 passed, 0 skipped`（2026-08-27 路由、r18 binding 与 convergence
  artifact 安全修复后）；这是代码
  契约证据，不是能力或质量证据。

2026-08-27 离线路由契约增量：Fast 基础轻量校验阈值已收紧，普通短请求不会因为基础
complexity/uncertainty 被误扩展为 Fusion；显式质量、风险、工具、策略和消息特征仍可
独立触发校验。运行时资格过滤同时排除 `health=failed/unavailable` profile，并记录
`profile_unavailable` blocker。恢复的历史回归和三档 dry-run 均通过；详见
`docs/handoffs/2026-08-27_routing_contract_repair.md`。该增量不改变 r18 frozen
plan/source/registry 或 target 授权，也不构成 provider 能力、排序、成本、延迟或
superiority 证据。

2026-08-27 r18 preflight binding 增量：verifier 现在强制校验 operational-admission
内容 hash 与 frozen plan 的 `content_sha256` 一致；safe/private 投影混用会以
`binding_mismatch` fail-closed。真实双路径复核和全量 `1114 passed, 0 skipped` 通过；
该修复不改变 r18 frozen plan/source/registry 或 target 授权。

2026-08-27 convergence artifact 安全增量：所有 stage artifact 统一递归检查敏感持久化
字段；raw provider output/prompt/label/URL/path/key/secret 任一声明为 `true` 即以
`raw_sensitive_fields_persisted` fail-closed。专项与全量 `1116 passed, 0 skipped` 通过；
该修复不改变 r18 frozen inputs 或 target 授权。

2026-08-26 离线可观测性增量：公开 health projection 已补充物理/逻辑模型计数，使用
与运行时一致的 canonical identity 去重，并对 disabled/unavailable/超时 profile 应用
服务可用性边界。该增量只影响 hash-safe 运维投影，不改变 r18 冻结输入、生产路由或
benchmark gate；r18 live screening 仍未授权。

## 差距矩阵

| 领域 | 当前状态 | 已完成的可验证内容 | 未完成/阻塞 | 下一条合法动作 |
| --- | --- | --- | --- | --- |
| 产品边界 | **done** | 独立 remote-only 服务；三档公共模型；不加载本地权重；图片 lane 与文本 Fusion 隔离 | 尚未以完整 baseline/target 证据证明质量、成本、延迟目标 | 保持公共合同不变，等待 baseline freeze 后做校准 successor |
| 四协议公共 API | **done/partial** | Chat Completions、Responses、Anthropic Messages、Gemini 的规范化输入、流式输出、错误和 reasoning 公共边界已有回归 | 必须在正式 campaign 对 12 个 tier/surface 单元做同 cohort parity | campaign 放行后运行四面配对 parity 和失败审计 |
| 图片能力 | **done** | verified image registry、generation/editing 探针、multipart/90 秒门禁、text/image 隔离；buffered/streaming 成本观察和 composer cost observer | 不是文本 Fusion 能力，不得混入 21-suite 文本 claim；当前 verified image profiles 未声明价格，预算成本保持 unknown | 仅按独立 image registry 维护和回归；公网预算启用前补齐价格证据 |
| Fast 工作流 | **partial** | bounded direct cascade、轻量验证开关、replica failover、3x/预算 guard、fail-closed | 当前 r7 role/capability admission 使多数复杂请求退回 direct；实际 pricing/tool metadata 未校准 | baseline freeze 后用 non-target shadow 校准 light-verify 的 VOI/成本阈值 |
| Terra 工作流 | **blocked/partial** | selective fusion、独立性检查、Judge/Synth reservation、正确的 direct fallback；零网络 fake-provider 回归已证明完整 role pool 下 panel phase 可配置并执行全部已准入 expert | 当前 registry 没有同时满足 `independent_solver + judge` 的准入容量；不能用弱模型冒充；fake-provider 结果不构成 live 能力证据 | 完整 screening/ranking/freeze 后做 endpoint-bound role successor，再 shadow replay；若 live 再出现 partial panel，按 safe cause taxonomy 分诊 |
| Pro 工作流 | **partial** | panel -> Judge -> targeted escalation -> acting Synthesizer；角色上下文隔离；公共 reasoning 清理 | 当前 dry-run 只有一个 provider hash，跨 provider 互补不足；质量/成本尚未实测 | baseline freeze 后做 provider diversity/error-correlation/quality shadow 优化 |
| Router/编排算法 | **partial** | query analysis、canonical 去重、角色 gate、deadline/call/cost reservation、fallback、circuit recovery、safe trace | 静态 capability prior 仍未被完整双源 non-target evidence 替换；VOI/portfolio optimizer 未晋级 | 只在 baseline freeze 后使用 non-target/shadow/holdout 设计和审批 successor |
| 自适应渠道校准 | **partial/guarded** | allowlisted channel fingerprint、reasoning/tool/vision/context/latency/cost/endpoint 变化检测；hash-only prompt/decision receipt；CLI 可从五类本地 artifact 读取 SHA-256 并要求成组绑定；无证据或绑定缺失时 fail-closed；完整绑定也只允许 `shadow_candidate` | 尚无 provider baseline freeze 后的 operational calibration evidence；不能自动激活或写回 serving policy | freeze 后以同 cohort non-target/holdout 生成五类绑定，人工审查后再做 shadow replay 和可回滚 successor |
| Judge/Synthesizer | **partial** | 结构化比较 rubric、consensus/contradiction/coverage、独立性 gate、输出归一化 | confidence calibration、abstention/repair 阈值尚无同 cohort 实证；不得以 target label 调参 | baseline freeze 后用 operational non-target cases 校准并绑定 rollback |
| Provider admission | **blocked** | r7 probe-bound registry、四协议 adapter、90 秒 stream gate、健康和安全 receipt；r18 credential-ready 零网络预检 9/9；可复用 transport 审计入口已真实重放 r17 并生成 hash-only receipt；新增 r18 启动前 verifier 已核对 frozen binding、proxy、PID 约束和敏感字段 | r17 transport admission blocked；8 canonical 仅 1 个同时通过两源 2% gate，低于 minimum 3；1712 case 中 916 个为 fail-fast 未尝试、799 次实际 provider attempt 中 37 次失败；credential readiness 和 verifier ready 都不等于 transport admission | 明确授权后只启动唯一 r18 frozen live screening，并沿用完整分母、allowlist 审计与 failure taxonomy |
| Ranking/baseline freeze | **blocked** | ranking conversion、external top-three、freeze 的 fail-closed 控制面已实现 | r18 尚未 terminal，故无完整 pool ranking、rank 1/2/3 或 freeze | r18 terminal -> transport admission -> complete-pool ranking -> external top-three -> freeze |
| Harness 控制面 | **partial/ready offline** | hash-only pin、formal cohort gate、execution plan 状态机（blocked/execution-ready/post-execution-import-ready）、持久化状态、可恢复 supervisor、import audit、convergence gate | r18 provider freeze 尚未完成；新 successor 已正确将 diagnostic execution plan 标为 `blocked`，当前 `next_gate=screening`；即使 formal execution ready，也不会绕过 post-execution imports 或 target gate | freeze 后以同 cohort 15-unit/90-import 形态重建，先执行官方/审计 Harness 并导入，再审计放行 target |
| 21-suite 资产 | **partial/blocked** | 9 类 21 套 matrix、case/source/decoding/统计合同；14 套可直接 materialize，6 套需 official import，GPQA 受授权门禁 | 没有完整同 cohort run；GPQA/官方 harness/import 仍不能冒充 ready | 先完成 baseline freeze 和官方/audited imports，再启动 target |
| Benchmark campaign | **blocked** | 独立 evaluator、四面 API、paired statistics、Holm、effect size、3x latency、污染审计的代码/合同已具备 | `target_suite_calls_allowed=false`，无 provider baseline freeze，无 campaign 证据 | convergence 返回 `ready_for_target_campaign` 后再按锁定矩阵运行 |
| 商业级运维 | **partial** | 生产 health ready；提交 `bfae5ac`（运行时代码 `4d56422`）发布后 PID `2576971` 已通过 setsid 受控发布加载最新代码；proxy auto；atomic/safe receipts；secret/raw output 隔离；公开 capability warnings 已实际返回；public/operator key 比较使用 constant-time 语义；`current_channels.env` registry identity 已对齐 r7 serving identity；显式 auth fail-closed、租户并发 admission、每日预算 UTC reset `Retry-After`、预算/非正 rate-limit 关闭状态可观测性均已实现 | 当前 18900 未启用 auth；正式公网仍需配置真实公共/operator key 并完成外部流量验证；pricing/context/tool 能力字段为 unknown；跨 provider diversity 不足 | 按部署策略在公网切换前启用并验证 auth；baseline 后补齐 admission metadata，并以 non-target/shadow 证据校准跨 provider 组合 |
| 代码质量与冗余 | **partial** | 核心 `src`、测试和控制面回归绿；关键边界有类型/异常/receipt | 历史 benchmark scripts 有重复 runner 与裸 `except`；不能在 baseline gate 前混入重构 | baseline freeze 后拆独立 legacy cleanup，逐文件 L1-L4 验证 |

## 当前必须保持不变的边界

在 provider baseline freeze 之前，不做以下动作：

1. 不修改 r18 frozen plan/source/registry，不恢复 checkpoint，不使用 `--retry-failed`，
   不拼接 completed/survivor subset，不降低固定 2% transport gate。
2. 不把 partial score、transport failure、静态 capability prior 或历史 benchmark 结果
   当作能力排序、baseline 或 superiority 证据。
3. 不修改生产 router、prompt、panel weights 或 benchmark-driven learning loop；算法
   研究只能进入 hash-bound shadow/non-target 设计记录。
4. 不启动任何 target benchmark，也不把 Harness pin/scaffold 的 `ready` 解释为 target
   authorization。

## 终态收敛路径

```text
明确授权 r18 live screening
  -> screening terminal
  -> transport admission（至少 3 个 canonical，双 source 通过固定 2%）
  -> complete-pool ranking
  -> externally evidenced rank 1/2/3
  -> provider baseline freeze
  -> same-cohort official/audited Harness import
  -> convergence = ready_for_target_campaign
  -> 9 类 21 套、四协议、同 case/prompt/decoding campaign
  -> paired statistics / Holm / effect size / latency / cost / contamination
  -> final completion audit
```

如果任一质量、成本、延迟或安全 gate 失败，产物只能标记为 diagnostic，随后注册
immutable policy/prompt successor，在 non-target shadow 和独立 holdout 上验证，再由
显式审批决定是否生成新的 serving registry。不得自动 promotion。

## Harness 设计原则对 Axio 的约束

结合 Harness Engineering 文章中 workflow automation、filesystem persistent state、
backend jobs、context engineering、permission controls、held-out evaluation 和
failure-cause evidence 的原则，Axio 采用以下边界：

- 工作流是显式有向图，角色、依赖、deadline 和预算可审计；不是把所有模型输出拼进
  一个无界 prompt。
- 状态和 receipt 持久化在受控文件中，原始 prompt、provider output、标签和密钥留在
  私有运行域；恢复依赖 digest/PID/plan identity，而不是猜测上下文。
- candidate policy 必须经过 held-in 修复证据与 held-out 回归、shadow replay、
  rollback target 和人工/显式审批；benchmark evaluator 位于生产 router 之外。
- 失败记录必须区分 terminal verifier cause、transport cause、模型行为 cause 和
  abstract mechanism；`timeout` 不能被直接等同于能力失败。
- 允许 bounded fan-out 和有限反馈轮次，但必须保留 canonical/provider 独立性，防止
  MoA/Fusion 的“多次调用同一相关模型”制造虚假共识。

## 本轮交接结论

当前没有新的功能授权或 live screening 授权。最短且证据正确的路线是：等待 operator
明确授权后执行 r18；在授权前仅进行只读核验、文档/离线控制面改进和不改变冻结输入的
测试。下轮首先重新读取本矩阵、最新 handoff、r18 state/receipt、Goal/PRD，再决定是否
进入唯一 live action。

## 运输根因审计增量（2026-08-21）

已对 r17 私有 unit 的 hash-safe transport telemetry 做可复现离线复核，并写入
`docs/scout/transport_root_cause_audit_r17_r18_2026-08-21.md`：完整分母为 1712
case，762 completed、950 transport-failed，其中 916 个由固定前三次失败后的
fail-fast 补入；实际 provider attempts 为 799，失败 attempt 为 37（timeout 25、
HTTP 5xx 8、empty output 4）。该审计没有读取 raw provider output，也没有网络调用，
不改变 r17/r18 任何冻结输入。结论仍是 source/profile 相关 transport 不稳定与
90 秒硬上限共同作用，不能据此调整 router、prompt、权重或 gate。

本轮新增的可复用审计入口已通过真实 r17 artifact 回归，receipt 为
`private/runs/2026-08-20-composite-cohort-r17/transport_root_cause_audit.r17.safe.json`；
其 `status=ready` 仅表示输入 binding/telemetry 自洽，`transport_admission_status=blocked`
仍是正式 admission 结论。它不改变 r18 的授权条件，也不产生 ranking 或 superiority 证据。
