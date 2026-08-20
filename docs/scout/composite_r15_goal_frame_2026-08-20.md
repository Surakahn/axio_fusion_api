# Composite r15/r16 Goal framing（2026-08-20）

## 当前主线切换：r15 terminal -> r16 successor

r15 已自然终态，16/16 unit terminal，transport admission 为 `blocked`：8 个 candidate
canonical 中 0 个满足固定 2% transport gate，最低要求为 3。r15 不产生 ranking、provider
baseline freeze 或 target 证据；完整 state、screening receipt、transport receipt、supervisor
receipt 和 Harness audit 均保留为 reference-only。当前 goal 已切换到 r16 immutable successor，
不恢复 r15、不拼接 completed subset、不降低 gate、不重复上游 probe。

r16 的 frozen plan、zero-network preflight 和 Harness scaffold 已生成并 hash 绑定：plan
digest `23c1b22a1708e38579f2c8f70f82bfe36a1bb7d4bde20e9aa337e289f8e969ad`，source SHA-256
`cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`，preflight campaign
digest `af9aeed814a6e20940dd8f2a3d497e3ce9115d326ffd9e2e999bef826e2e31dc`。计划为 16 个
serial units、2 source families、8 canonical groups/9 replicas、`max_workers=1` 和 2%
fail-fast；preflight 明确无 network/target call。Harness pin 6/6 ready，但 acquisition、
official import、binding 和 convergence 仍 blocked，`next_gate=screening`。

下一阶段不是再设计未经 baseline 证明的 Fusion 算法，而是获得完整 provider baseline
lineage。只有 r16 terminal 且 transport admission ready，才进入 complete-pool ranking、
external rank 1/2/3、provider freeze、same-cohort official/audited import、21-suite target
campaign 和最终统计审计。

## 结论

当前 goal 的下一锚点是唯一 r16 non-target screening 的自然终态。产品、代码和 Harness
控制面已经有可验证的工程基础；当前缺口是完整 provider baseline evidence lineage，
不是再增加一个未经基线验证的 Fusion 算法。screening terminal 以前不得进入 transport
conversion、ranking、provider freeze、official import 或 target campaign。

## Goal 与 PRD 契约

- Axio 是独立的 remote-only orchestration service，不加载本地权重、不训练模型、不依赖
  ASciFS runtime。
- 对外只暴露 `axio-fast`、`axio-terra`、`axio-pro`，内部接入任意经 registry/admission
  验证的 provider profile；同一 canonical model 的物理 replica 只用于 failover，不能
  增加 Fusion 票数。
- 四种输入/输出协议必须保持同一 normalized route contract：Chat Completions、Responses、
  Anthropic Messages、Gemini GenerateContent。协议差异只在 wire adapter、stream framing、
  auth header 和协议特有字段。
- 三档算法分别是 bounded direct cascade、selective cost-guarded complementary fusion、
  expert panel + Judge + targeted escalation + acting Synthesizer。所有路线都受成本、
  deadline、3x latency、privacy、tool isolation、fallback 和 safe receipt 约束。
- 图片 lane 与 text Fusion 完全隔离；未经 verified image registry 的请求必须受控失败，
  不能把图片能力伪装成文本 Fusion。

## 当前证据位置

当前 r15 已 terminal：16/16 unit terminal，screening receipt 为 `partial`，1 completed、
15 failed；transport admission 为 `blocked`，8 个 candidate canonical 中 0 个满足固定 2%
transport gate，最低要求为 3。state SHA-256 为 `262c2711bf7d5c5e42d21fa7e303e27d7bdc123deb66f0a7ebc3f8af662c919d`，
screening receipt SHA-256 为 `29dff8639fd59596eb66cb5643bfee2f08d82ada96359a983ca54559dc14513`，
transport receipt SHA-256 为 `53c60e97cae40db1094d5e472e2a2ff2688760ec60be7453d1e29dd33388b639`。
唯一 completed unit 为 `112/112`、transport failure `0`；其余失败 unit 的完整 transport
分母均保留，不能解释为质量分数、survivor subset 或 ranking。supervisor 未生成 ranking、
provider freeze 或 target 产物，`target_benchmark_started=false`。工程回归 `1066 passed,
7 skipped` 仍只是代码契约证据。

## 正式评价契约

正式矩阵是 9 类 21 套 benchmark，不使用旧的 7 类 14 套目标文字缩减范围。GPQA Diamond
仍受授权访问门禁；六套 code/tool/pairwise harness（LiveCodeBench、HumanEval、BFCL、
tau-bench、IFEval、MT-Bench work）必须导入官方或审计 run，下载 checkout 不等于 score。
所有 Axio tier 和三档 frozen single-model baseline 使用同一 locked case hashes、prompt/
decoding binding，并跑四个公共 API surface。

最终 claim 还必须同时通过 paired case-level comparison、Holm-Bonferroni、多套 effect-size
门禁、p50/p95 不超过对应单模型 3x、API-surface parity、contamination audit、failure
analysis 和 final completion audit。任何一档失败只能产生 diagnostic/shadow proposal，不能
写成 superiority claim，也不能把 benchmark 输出写入生产 routing learning loop。

## 已实现的算法边界

当前实现已覆盖 query-adaptive request analysis、capability/structured/reliability/
latency/cost scoring、canonical dedup、provider diversity 与 error-correlation 相关
选择、role-scoped panel、共享 deadline/call/cost budget、mandatory Judge/Synthesizer
reservation、一次 bounded Judge feedback wave、replica failover、circuit recovery、tool
authority isolation、Hermes-style deterministic context projection 和 hash-safe trace。
这些控制只使用 provider admission、registry evidence、request-local signal 与运行时反馈，
不能读取 target benchmark label/answer 来调参。

## Baseline freeze 后的必要研究/开发

1. **真实 calibration**：用完整双源 non-target ranking 后的 rank/freeze 证据替换静态
   capability prior；按 task family 建立可靠性、延迟、成本、schema/tool success 和
   error-correlation 的分层后验，并保留置信区间与冷启动 shrinkage。
2. **受约束 panel optimizer**：在质量 floor、独立 canonical、跨 provider verifier、
   预算和 p50/p95 3x 硬约束下，比较 expected utility / value-of-information 与当前
   加权启发式；只在 shadow replay 中评估，获得 approval 后再生成 successor policy。
3. **Judge/Synth calibration**：用非 target operational cases 校准 contradiction、
   evidence coverage、schema validity 和 abstention threshold；禁止以 target score 直接
   改 prompt 或阈值。
4. **reasoning transport closure**：继续用 endpoint-bound probe 验证 Chat/Responses/
   Anthropic/Gemini 的 reasoning effort/budget 映射；未 attested 的 provider 只能记录
   protocol-neutral role budget，不能伪造 native `max`。
5. **商业级遗留清理**：baseline gate 之后处理历史 benchmark 脚本中的裸 `except:`、重复
   runner 和旧 streaming/target 路径；核心 `src` 与当前 convergence 控制面不能被这些
   legacy scripts 混淆，清理必须拆分、逐层测试、逐阶段提交。

## Terminal 后唯一执行路径

`screening terminal -> transport admission -> complete-pool ranking -> external rank 1/2/3
evidence -> provider baseline freeze -> same-cohort official/audited imports -> cohort
binding/convergence audit -> 21-suite target campaign -> paired statistics/latency/API
parity/contamination/final audit`。

如果 r15 终态为 partial 或 transport-blocked，保留完整分母和私有 evidence，注册新的
immutable successor；不恢复 checkpoint、不拼接 completed/survivor subset、不降低 2% gate、
不重复上游 probe。当前 report 是 framing/diagnostic artifact，不授权任何 target request。

## 依据

- `docs/axio_fusion_api_product.md`
- `docs/axio_fusion_benchmark_methodology_21_suites.md`
- `docs/architecture/axio_fusion_benchmark_harness_convergence_2026-08-16.md`
- `docs/architecture/closed_loop_fusion_runtime.md`
- `docs/handoff_2026-08-20_r15_intake.md`
- `docs/operations/composite_r15_successor_intake_2026-08-20.md`
- `PLAN.md`
