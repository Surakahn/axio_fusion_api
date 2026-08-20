# Composite r15 Goal framing（2026-08-20）

## 结论

当前 goal 的下一锚点是继续等待唯一 r15 non-target screening 自然终态。产品、代码和
Harness 控制面已经有可验证的工程基础；当前缺口是完整 provider baseline evidence
lineage，不是再增加一个未经基线验证的 Fusion 算法。screening terminal 以前不得进入
transport conversion、ranking、provider freeze、official import 或 target campaign。

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

截至 2026-08-20 14:04:57，r15 safe state 为 `running`，16 planned unit 中
`1 completed / 11 failed`，12/16 已写入 state，剩余 4 个；state SHA-256 为
`3b0e4a3001423a964b1f5fb907acca2e30b2e48b10cb6798d26a0fe12a022096`。唯一通过 unit 为
`112/112`、transport failure `0`；失败分母完整保留为 `112/112 x5`、`102/102 x2`、
`101/102`、`92/102`、`80/102`、`60/102`，原因均属于 transport fail-fast evidence，
不是能力分数或 ranking。当前活动 checkpoint 是 `dd6e3d631867c96b5417ca5860af672e9de80961eae4f317e6c17e96fac9559a`
的 `2/102` partial，SHA-256 为
`0a75d69049abf3da03e37f9def47833f600ff8d49f937ee374bfdc5c37e915a8`。

三项进程仍由 init 托管：screening `2871629`、supervisor `2880595`、watcher `2881730`。
`target_suite_calls_performed=false`、`ready_for_ranking=false`，screening receipt、
transport admission、ranking、provider freeze 和 target 产物均不存在。全量工程回归
`python3.11 -m pytest tests/ -x -q --tb=short` 已为 `1066 passed, 7 skipped`；这只是
代码契约证据，不是 provider 能力或 superiority 证据。

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
