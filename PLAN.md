# Axio Fusion API Plan

## 本轮离线增量：路由契约与回归门禁修复（2026-08-27）

本轮依据现有 PRD 与 remote-only Fusion 边界，只修复运行时路由契约，不触碰任何
provider、target benchmark 或冻结 screening 输入：

- Fast 轻量校验的基础复杂度/不确定性阈值由 `0.25/0.30` 收紧为 `0.40/0.40`。
  普通短文本的基础分析值不再被误判为 Fusion；显式质量、风险、工具、策略和消息
  特征仍可独立触发校验。
- 路由隐私/资格过滤阶段排除 `health=failed` 或 `health=unavailable` 的 profile，
  并在 blocker receipt 中记录 `profile_unavailable`，避免校准后的失效副本继续被选中。
- 恢复并对齐 7 个历史跳过用例（Fast direct cascade/headroom、canonical replica
  failover、prompt-free trace、registry calibration、cache isolation），全量回归
  为 `1113 passed, 0 skipped`。

本轮 L1/L2、专项回归和 `git diff --check` 均通过；没有 provider/target 网络调用，未
恢复 checkpoint、未使用 `--retry-failed`、未拼接 survivor subset、未降低 r18 固定
2% transport gate，也没有重启服务或改变 serving registry。该增量不构成能力、成本、
延迟或 superiority 证据；r18 live screening 仍需 operator 明确授权。

## 用户确认的核心理念与最终收敛（2026-08-21）

Axio 的 Fusion 本质是 remote-only 的模型能力组合服务：不是训练一套本地模型，
也不是把某个 provider alias 重新命名，而是用可复用的 prompt 流程、路由、编排、
角色分配、Judge/Synthesizer、fallback、成本/延迟/并发预算和安全/可观测工程，
把多个远程渠道提供的能力融合成三个稳定的公共模型名：`axio-fast`、`axio-terra`、
`axio-pro`。Harness 只负责评测、控制、恢复和证据链，不是 Fusion 产品本体；它
只能在 shadow/non-target 阶段推动 policy successor，不能把 benchmark 标签或结果
写回生产路由。

参考边界已经固定：吸收 Sakana AI Fugu/TRINITY/Conductor 的黑盒模型池、动态
workflow、worker 隔离和显式上下文拓扑；吸收 OpenRouter Fusion 的 panel 并行、
Judge 结构化比较和单一最终 Synthesizer；吸收 Harness Engineering 的 workflow
automation、持久化状态、可恢复后台任务、context engineering、权限、评测和证据
链。完整映射和非目标见
`docs/scout/axio_fusion_goal_reference_architecture_2026-08-21.md`。

三档公共模型代表三种受预算约束的工作流，而非三个隐藏单模型：Fast 是 bounded
direct cascade，Terra 是选择性互补融合，Pro 是 expert panel -> Judge -> targeted
repair -> acting Synthesizer。简单任务可不启用多模型；复杂任务也必须服从
deadline、call/cost、canonical 去重、replica failover、工具隔离、streaming 和
3x latency guard。

当前工程主线已经完成 runtime、四协议适配、图片隔离和 Harness 离线控制面；真正
尚未完成的是完整 provider baseline lineage 和最终 21-suite 质量证据。r17 已
terminal/transport-blocked，r18 仅到 zero-network preflight ready。不得把历史
14-suite 结果、partial screening score 或静态 capability prior 写成 superiority。

每轮交接前的逐域差距、证据锚点和下一条合法动作见
`docs/operations/goal_gap_matrix_2026-08-21.md`；该矩阵只记录 hash-safe 状态，不改变
任何冻结 screening 输入或生产路由。

本轮最新交接（2026-08-26）见
`docs/handoffs/2026-08-26_formal_harness_execution_gate.md`；本轮新增的控制面 successor
位于 `private/runs/2026-08-26-composite-cohort-r18-harness-formal-gate/`，只用于证明
execution plan 已按 provider baseline freeze 和 formal top-three cohort fail-closed，
不替代 r18 frozen plan/source，也不授权 screening 或 target benchmark。

本轮后续校正了 execution gate 的状态语义：formal freeze/cohort/task/pin/template 完整
时，execution plan 的 `ready_to_execute` 仅授权官方/审计 Harness work queue；imports
尚未完成通过 `post_execution_imports_complete=false` 和 reason code 表达，不再伪装成
`planned` 或阻塞已准备好的执行队列。只有 hash-only imports、acquisition、case/source/
harness audit 全部同 cohort 完成，binding/convergence 才能继续到 target gate；
`target_campaign_authorized` 在 execution plan 中固定为 `false`。

本轮最新交接（2026-08-27）见
`docs/handoffs/2026-08-27_bizbench_evaluator_hardening.md`：BizBench evaluator 已支持
多 parquet 分片、SEC-NUM 数字或开放词汇 span 评分，并将程序执行收紧为 AST + 最小
builtins 白名单 + bwrap 隔离；真实 4,673 行离线审计、专项回归和全量
`1106 passed, 7 skipped` 均通过。该增量仍不改变 r18 live screening 授权门。

本轮最新交接（2026-08-27）另见
`docs/handoffs/2026-08-27_routing_contract_repair.md`：Fast 路由触发条件和不可用
profile 资格过滤完成离线修复，恢复历史回归后全量为 `1113 passed, 0 skipped`；不
改变 r18 frozen inputs、serving registry 或 target 授权。

## 本轮离线增量：BizBench 任务感知 audited evaluator（2026-08-26）

只读核对官方 `kensho-technologies/benchmarks-pipeline`、BizBench 论文和本地
Parquet 后，确认测试集 4,673 行包含 8 个任务族，不能继续使用单一
`exact_match` 提示/评分。新增 `bizbench_task_aware_v2` 契约：FinKnow 仅向模型展示
选项并按索引评分；ConvFinQA/TAT-QA 使用数值抽取，SEC-NUM 对数字标签使用数值抽取、
对开放词汇标签使用规范化 exact span；FinCode、CodeFinQA、
CodeTAT-QA 在显式 opt-in 后执行无 import、无文件/网络访问的候选程序并按论文 1%
相对误差比较；FormulaEval 以确定性合成输入同时运行候选与 gold 函数体。reference
program、answer 和 raw output 仍被 prompt projection 与 safe receipt 隔离；该模块是
可审计本地 evaluator，不伪造独立第三方 official Harness，也不改变 r18 frozen 输入、
生产路由或 target 授权。

验证：真实 BizBench 物化 `4673/4673` 行通过数据与 prompt contract 检查；gold
FormulaEval 自测 `50/50`；BizBench 专项回归 `9 passed`；全量回归
`1106 passed, 7 skipped`。下一条合法主路径仍是等待 operator 明确授权
`r18 live screening`，不得因该离线 evaluator 就提前运行 provider 或 21-suite target。

本轮只读复核还确认 18900 当前绑定的是 r7 probe-bound serving registry：21 个 physical
profiles、15 个 logical models、21 个 live-available profiles、4 个 providers。AGENTS
中 r43 的 10-profile 检查属于历史阶段，不应覆盖当前 r7 serving 身份；未修改 registry
或重启服务。

最终唯一合法路径：

```text
transport 根因复核
 -> 明确授权 r18 live screening
 -> terminal screening
 -> transport admission
 -> complete-pool ranking
 -> external top-three
 -> provider baseline freeze
 -> same-cohort Harness pin/import/convergence
 -> 9 类 21 套 benchmark
 -> paired statistics / latency / cost / contamination / final audit
```

在每个功能拆解前，先回到产品/PRD 契约确认真实意图；当未知会改变后续 gate 时，
先做本地证据和一手参考调研，再开始架构或代码变更。不得修改冻结 screening
plan、恢复 checkpoint、拼接 survivor subset、降低固定 2% transport gate 或提前
target benchmark。

## 本轮离线增量：健康检查物理/逻辑模型计数（2026-08-26）

公开 `/health` 的 `registry_readiness` 现在同时提供物理 profile 与逻辑模型计数：
`model_count`/`available_model_count` 统计去重后的 provider profile，
`logical_model_count`/`available_logical_model_count` 使用与运行时相同的 canonical
identity 规则统计模型。可用计数排除 disabled、明确 unavailable 或超过 90 秒 provider
响应上限的 profile。该投影保持 hash-only，不暴露 provider/model 标识，也不改变路由、
prompt、权重、registry 或任何冻结 screening 输入；计数只用于运维容量和副本/故障转移
观察，不构成排名、能力或 benchmark 证据。

## 本轮离线增量：r18 启动前 preflight verifier（2026-08-21）

新增 `scripts/verify_screening_preflight.py` 和专项测试，用于在任何 operator
授权前对 r18 的 frozen plan/source/registry、r7 operational admission、原始
preflight、credential-ready preflight、代理策略和可选 PID 做零网络、hash-only
核验。它校验 schema、digest、2% fail-fast/双 source 合同、remote-only/no-cheat
边界、9/9 credential readiness、`auto -> proxy` 选择以及 live 命令的
`baseline-screening-run --live` 与三个输入绑定；receipt 不保存路径、命令行、
provider 标识、URL、prompt、输出、标签或 secret。

真实 r18 核验 receipt：
`private/runs/2026-08-21-composite-cohort-r18/screening_preflight_verifier.r18.safe.json`，
状态为 `ready_for_operator_authorization`，receipt SHA-256 为
`9e2fed685743449bd88675bed12ad209691a6059f68e2b70892c641330f6a9d8`。该状态明确
`authorization_required=true`，不启动进程、不产生 provider/target 请求，也不等价于
`授权 r18 live screening`。验证专项为 `5 passed`，本轮全量回归为 `1096 passed, 7
skipped`；r18 plan/source digest 未变。

## 本轮只读增量：r17 transport 根因计数复核（2026-08-21）

已完成 r17 私有 unit 的 hash-safe transport telemetry 复核，结果写入
`docs/scout/transport_root_cause_audit_r17_r18_2026-08-21.md`。1712 个 case 中
762 个 completed、950 个 transport-failed，916 个为固定 fail-fast 补齐的未尝试
分母；实际 provider attempts 为 799，37 次失败 attempt 分为 timeout 25、HTTP
5xx 8、empty output 4。没有读取 raw provider output、prompt、label、URL 或 secret，
没有进行 provider/target 请求，也没有修改 r17/r18 plan/source/registry、生产
router/prompt/weights 或 gate。该结果只支持“source/profile 相关 transport 不稳定 +
90 秒硬上限”的诊断，不是能力或排名证据；下一条合法动作仍是等待明确的
`授权 r18 live screening`。

## 本轮离线增量：可复用 transport 根因审计入口（2026-08-21）

新增 `scripts/audit_screening_transport.py` 及其零网络测试。该工具把已终态
screening 的 private unit telemetry 转换为 hash-only receipt，校验 plan/state/
transport binding、完整 case 分母、fail-fast、provider attempt/failure 分类和
unit admission 一致性；不读取或输出 raw provider output、prompt、label、URL、model
id 或 secret，不修改 frozen plan，不恢复 checkpoint，不触发 provider/target 请求。
`status=ready` 只表示审计输入自洽，`transport_admission_status` 单独表达 admission
结果，避免将 blocked 误报成成功。后续 r18 terminal 后优先复用该入口生成正式
transport diagnosis，再进入 ranking gate。

真实 r17 复核已生成
`private/runs/2026-08-20-composite-cohort-r17/transport_root_cause_audit.r17.safe.json`，
SHA-256 为 `f91f064539dd246ae5836c669e40c0dc931d9f4b15028fb2075cdd0069081b73`；
输出重现 16 units/1712 cases/762 completed/950 failed/916 fail-fast/799 attempts/
37 failed attempts，且 `transport_admission_status=blocked` 保持不变。全量回归为
`1087 passed, 7 skipped`。该 receipt 只证明审计输入自洽，不授权 r18 live screening。

## 本轮离线增量：自适应校准 receipt 发布边界（2026-08-21）

本轮继续沿“Fusion 负责能力组合、Harness 负责评测与证据链”的产品边界，补齐
`adaptive_calibration.py` 的商业级校准凭证。渠道变化或融合退化只能在内存中生成元
提示词，持久化产物只保存 prompt/决策/渠道绑定的 SHA-256 与 hash-safe 投影，不保存
元提示词原文、provider 名称/模型 id、provider 输出或任何 secret。

新增 `axio_fusion_api.adaptive_calibration_receipt.v1`：

- 没有得分证据的渠道变化固定为 `blocked`，不能仅凭配置变化发布 prompt 建议；
- 有融合/基线得分但缺少 registry profile set、workflow、rollback target、prompt
  pack 或 contamination audit 任一绑定时仍为 `blocked`；
- 五类绑定和 operational evidence 齐全时最多进入 `shadow_candidate`，
  `activation_ready=false`、`automatic_activation_allowed=false`，必须人工审查；
- 健康且未发生渠道变化的运行返回 `not_required`；CLI 不再输出或写入
  `recalibration_prompt` 原文，只输出 `prompt_sha256`。

本轮没有 provider/target 网络调用，没有修改 r18 frozen plan/source/registry、生产
router/prompt/weights 或服务进程。专项校准/CLI 回归为 `14 passed`，全量回归为
`1081 passed, 7 skipped`，`py_compile`、`compileall`、包导入和 `git diff --check`
均通过。下一合法动作仍是等待明确的 `授权 r18 live screening`，然后严格按
`screening -> transport admission -> complete-pool ranking -> baseline freeze ->
same-cohort Harness -> 21-suite campaign` 顺序推进。

## 本轮离线增量：校准 artifact 绑定入口（2026-08-21）

为使校准凭证能够在真实 non-target/holdout 证据形成后使用，CLI 新增五类本地 artifact
参数：registry/profile-set、rollback target、prompt pack、workflow、contamination
audit。CLI 只读取每个文件的 SHA-256，不读取内容进入 prompt 或 receipt；五类路径必须
全部提供或全部省略，部分绑定会在参数层 fail-fast。完整绑定加上 fusion/baseline
scores 时，receipt 才能从 `blocked` 进入 `shadow_candidate`，但仍保持
`activation_ready=false`、人工审查必需、`automatic_activation_allowed=false`。

本轮专项回归 `16 passed`，全量回归 `1083 passed, 7 skipped`；L1/L2、`compileall`、
导入和 `git diff --check` 均通过。该入口仍是离线控制面能力，没有读取 provider、没有
改变 r18 frozen 输入、没有写入 serving policy，也没有授权 target benchmark。

## Terra panel 调度边界复核（2026-08-21）

针对 AGENTS.md 记录的 Terra “部分 panel candidate”风险，本轮先做了零网络受控复现，
没有把未经授权的 live screening 当成调试手段。完整角色池下，当前运行时能够保留高推理
请求的外层 deadline、配置最小 panel phase，并完成全部已准入 expert 后进入 Judge/
Synthesizer；专项回归结果为 `5 passed`。因此目前没有足够证据修改 `_DeadlineBudget`、
panel phase 公式或 Terra deadline。

工程结论是双重 gate：

1. 调度代码的 panel 预算/执行循环以 fake-provider 回归锁定，后续 live trace 必须按
   transport、phase deadline、future cancellation 和 role admission 分类；
2. r7 正式 Terra 仍因 `independent_solver`/`judge` role capacity 不足而正确
   fail-closed，只有新的 endpoint-bound role probe、complete-pool ranking 和 provider
   freeze 才能生成 Terra role successor。

这条复核不改变 r18 immutable 输入、2% transport gate 或 target benchmark gate；它只
   减少错误修复和把弱模型提升为 Judge 的风险。

## 网关鉴权时序安全加固（2026-08-21）

当前 public/operator 鉴权的配置契约保持不变：public key 仍由
`AXIO_FUSION_API_KEYS` 注入，operator 控制面仍由
`AXIO_FUSION_OPERATOR_API_KEYS` 单独保护；本次只将密钥比较从集合交集改为
`hmac.compare_digest`，避免按前缀/字符逐步比较造成不必要的时序信号。空配置仍保持
现有 loopback 兼容语义，没有擅自开启生产鉴权，也没有重启服务。

新增回归覆盖 public/operator 精确匹配、近似密钥拒绝和 compare-digest 调用；该改动
不读取 provider、不修改 r18 frozen plan/source/registry、router、prompt、weights 或
benchmark policy。

## r17 终态、transport gate 与 r18 离线 successor（2026-08-21 00:09 CST）

r17 唯一 live non-target screening 已自然终态，16/16 unit terminal，safe state 为
`partial`：`6 completed / 10 failed_or_blocked`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。同 cohort transport-only admission 已执行且严格只
使用完整 transport 分母：8 个 canonical 中只有 1 个同时通过两个 source family 的固定
2% gate，最低要求为 3，receipt 为 `blocked`，唯一 blocker 为
`transport_admission_fewer_than_minimum_models`。没有 ranking、provider baseline freeze、
official import 或 target 请求，不能把 completed unit 或 partial score 当作能力证据。

r17 的 state/receipt/transport/supervisor/Harness 证据全部保留为 reference-only；不读取或
恢复 raw checkpoint，不拼接 survivor subset，不修改 r17 frozen plan/source/registry。当前
工作区已离线注册 r18 immutable successor，只改变 source contract 的注册日期和 selection
seed，没有重复 provider probe：

- r18 source SHA-256：`3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`；
- r18 plan SHA-256：`58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`；
- plan digest：`a626b9be599041b03c899880eee0fb10be7b7a7b5f22f2f0ccef95ad204cbf86`；
- 2 source families、8 canonical groups、9 replicas、16 serial units、`max_workers=1`、
  固定 2% fail-fast gate；
- r18 zero-network preflight 为 `preflight_ready`，campaign digest
  `fdc903a9e90a82e5753c17b49c8dd0f6b732100b8668dc14f576f1669481966d`；
- r18 Harness 仅离线生成 pin/execution/scaffold，acquisition/import/binding/convergence
  仍保持 blocked，`target_suite_calls_allowed=false`。

r18 当前只到控制面 ready，尚未授权 live screening。后续必须先完成 transport 根因复核，
再明确授权 r18 live screening；不得降低 2% gate。合法路径仍为
`screening -> transport admission -> complete-pool ranking -> external top-three ->
provider baseline freeze -> same-cohort Harness -> 9 类 21 套 campaign -> final audit`。

## 公共输出边界与四协议流式收敛（2026-08-20 22:32 CST）

本阶段继续沿完整 Fusion API 产品主线推进，没有把 r17 screening 当成项目本体，也没有
修改 r17 frozen plan/source/registry、生产 router/prompt/weights 或发送新的 benchmark
target 请求。针对产品待办中“axio-pro 最终输出可能携带内部 JSON reasoning 结构”的缺口，
在协议兼容层完成商业级公共文本边界收敛：

- `compat.py` 新增保守的 `normalize_public_output_text()`，只在完整 JSON/control envelope
  命中强内部字段（`reasoning_summary`、`ranked_candidates`、`ready_for_synthesis` 等）时
  提取 `answer`/`final_answer`；普通业务 JSON 和调用方显式请求的 `json_object`/
  `json_schema` 始终原样保留；
- Chat Completions、Responses、Anthropic Messages、Gemini 以及 buffered/streaming 渲染器
  统一使用同一归一化契约，usage 按实际公共文本重新计算；safe metadata 只记录应用标志、
  长度和 SHA-256，不保存原文、provider 输出或密钥；
- `orchestrator.py` 增加 request-local JSON-like stream gate。普通文本保持增量转发，疑似
  Synthesizer JSON envelope 在最终输出确定后才释放公共 answer，避免 terminal event 之前
  泄漏内部 reasoning；闸门不持久化原始内容。

验证门禁：L1/L2 通过；兼容、流式和融合核心专项回归 `494 passed, 7 skipped`；全量
`python3.11 -m pytest tests/ -x -q --tb=short` 为 `1075 passed, 7 skipped`
（退出码 0）。该结果是工程回归证据，不是 provider 质量、baseline freeze、21-suite
superiority 或最终完成证据。

r17 仍是唯一活动 screening：PID `3739367`、supervisor `3741799`、watcher `3742593` 未
漂移；safe state 仍 `running`、`ready_for_ranking=false`、`target_suite_calls_performed=false`，
当前安全计数为 `3 completed / 6 failed_or_blocked`；Harness convergence 的
`next_gate=screening`、`target_suite_calls_allowed=false` 保持 fail-closed。后续仍按
`screening terminal -> transport admission -> complete-pool ranking -> external top-three ->
provider baseline freeze -> same-cohort Harness -> 21-suite campaign -> final audit` 单向推进，
在证据链完整前不作 superiority claim。

## r17 immutable successor 与 preflight（2026-08-20 18:58 CST）

r16 transport admission blocked 后，已从 r16 source contract 注册新的 immutable r17 successor。
source successor 只改变 `pre_registration.registered_on` 和 `selection_seed`，没有读取 r16
score、transport receipt、ranking、checkpoint 或 survivor subset：

- source manifest：`private/runs/2026-08-20-composite-cohort-r17/source_manifest.successor.r17.private.json`，SHA-256 `7ba7fc8816cbd32881b47419e2d26d2fa26f7460d551b4d1c747195f8ae15b56`；
- successor receipt：`source_manifest_successor_receipt.r17.private.json`，SHA-256 `5103b24978c39aa2e5318601c9c6377b74948856bcee9c9c78dd7a68114ff640`；
- selection seed：`composite-r17-2026-08-20-transport-successor`，hash `33d47ab09c2b0ac4b18297ad67ce10c730bbd65c3f1d2bb218f067bccc0c90e9`；
- source contract 的 raw prompt、label、provider output、provider URL 和 secret 持久化标志均为 `false`。

r17 frozen plan 已通过离线生成并绑定 r7 probe-bound registry、r7 private probe 与 r7
operational admission：plan 文件 SHA-256 为
`336fa9c4f81223622a3f94d21cc249b4d20ba9b392a18a2e1aba54fbc5ba6565`，plan digest 为
`14f0a56ad4f22e21dacbb2209a7e3551517942eb0779dbc4158afd489f6d8c01`；2 个独立 source
families、8 个 canonical groups、9 个 replicas、16 个 serial units、`max_workers=1`、
固定 2% fail-fast gate、估算 provider calls `1712`，`ready=true`。r16 transport receipt
没有作为 r17 的 transport-availability 输入。

zero-network preflight 已完成：state SHA-256 为
`ba2868a0842d804a38b22df876782c68a579f33fcd0d69600f01fad127b5f108`，receipt SHA-256 为
`68c4bd646418f21b2877896c09fe21bcaa44937036b0e59acc1a920c386d3ee1`，campaign digest 为
`0f92d77ddf0a67d2c5e7dc0eb39ea2ba71cbb4203075b51312de0658b08793a9`；状态为
`preflight_ready`，`network_calls_performed=false`、`target_suite_calls_performed=false`，
没有 provider/target 请求。

同 cohort Harness 控制面已离线生成，使用已验证的 6/6 hash-only pin（SHA-256
`22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`）、r7 dataset/source/
case-hash manifests 和默认 `data/benchmarks` 控制路径：execution plan SHA-256
`3593437c083c780c09da784411ea7952c16f73913a68f8770a1fad757d2598ec`，acquisition status
SHA-256 `87de4260c7c200f12680f1165625ef4fe666644750e885bf3321a934f5b0a5b8`，official import
audit SHA-256 `b7474cddc260bdaf2a356ddcfa531620438d50f38761a54818c00dfad9c7dd7e`。目前 6 个
official/audited suite imports 仍未提供，cohort binding/convergence audit 为 blocked，
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`；
这只是预期的控制面状态，不是 target benchmark 失败。

下一步只启动一套绑定 r17 plan/source、r7 registry/probe/admission 的 live non-target
screening。screening terminal 前不执行 transport/ranking/freeze/import/target；terminal 后
仍严格沿 transport admission → complete-pool ranking → external top-three → provider
baseline freeze → same-cohort Harness → convergence → 21-suite campaign 单向推进。

## r17 live screening 启动（2026-08-20 19:02 CST）

r17 只启动了一套 live non-target screening，真实 Python PID 为 `3739367`，由 init 托管；
命令行绑定 r17 frozen plan/source、r7 probe-bound registry、r7 private probe 和
operational admission。screening console 初始为空且尚未写 safe live state，表示仍在首个
provider/preflight 阶段，不提前填写 unit 分母或 ranking readiness。

同 cohort convergence supervisor PID `3741799`、lineage watcher PID `3742593` 均由 init 托管，
命令行使用同一 r17 plan fragment。watcher 初始 snapshot 为 `status=blocked`、
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`；
supervisor 已进入同一 PID/plan identity wait。transport admission、ranking、provider freeze、
official import 与 target campaign 均尚未启动。

启动前一次未 source channel env 的参数级尝试已改名保留为
`screening_state.r17.live.bad-credentials.private.json` 与对应 receipt/log；它的 state SHA-256
为 `df0f8bef44bdd7db485e8e782d19378eb928316b1fc3ec6af8aea361c95c6109`，receipt SHA-256 为
`37135e43adaddbca18253d65f0311b8a6f8855cf337002ab29797c4831f389ee`，
`network_calls_performed=false`，唯一原因是 live credential readiness 缺失，没有 provider
request、case answer 或 target call，未进入 r17 lineage。随后使用进程环境 source
`private/current_channels.env` 重启同一 frozen plan，未使用 `--retry-failed`、未恢复 checkpoint、
未启动第二套 screening。

后续只按 10–20 分钟低频核对三个 PID、plan/source/registry hash、safe state/checkpoint mtime
和 hash、supervisor/watcher 日志及下游 artifact；screening terminal 前不修改 plan、不调整
router/prompt/weights、不重启生产 loopback 服务。

## r17 首个 serial unit checkpoint（2026-08-20 19:07 CST）

低频只读检查确认 screening PID `3739367`、supervisor PID `3741799`、watcher PID `3742593`
仍由 init 托管，命令行仍绑定 r17 frozen plan/source 与 r7 registry/probe/admission。首个
serial unit 已生成私有 checkpoint：`checkpoint_status=partial`、`9/102`，文件 SHA-256 为
`1c026cc71b94babb9aa90a5a48f9fa4edc371751cdc5ae185ad7a88221b87e30`。checkpoint 属于私有
恢复证据，标记 `raw_provider_outputs_persisted=true`，不进入 Git、不解释为 unit 完成、质量
分数或 ranking，也不允许手工恢复或拼接。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 和 target campaign 仍不存在；supervisor 继续等待 terminal，watcher 继续
保持 `next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。

## r17 screening 进入第二个 unit（2026-08-20 19:21 CST）

低频只读复核确认唯一 screening PID `3739367`、同 cohort supervisor PID `3741799` 和
lineage watcher PID `3742593` 均仍存活，命令行继续绑定同一 r17 frozen plan/source、r7
probe-bound registry/probe/admission；frozen plan、source manifest 和 registry hash 未漂移。

当前 safe live state 为 `status=running`、16 个 planned units 中 `0 completed / 1 failed_or_blocked`、
`ready_for_ranking=false`，文件 SHA-256 为
`a2d04dc54640a8001e5c471d4ba4e2bd9fae6a99cfb27fa63c06ba1b2aa49480`。第一个 unit 的私有
终态 artifact 保留完整 `102/102` 分母，其中 `15 completed / 87 transport_failed`；它只说明
transport 层的失败分母，不是答案质量、排名或 baseline evidence，不能抽取 survivor subset。

screening 已按冻结的 serial schedule 进入第二个 unit。最新私有 checkpoint 为
`checkpoint_status=partial`、`12/112`，文件 SHA-256 为
`b56b0d2f28b7b385c73757eadd7ef8efc0a46dc786e42abaa3ae7dcaef8982a5`；该文件包含 raw provider
output，只作为私有恢复证据，不进入 Git、不读取原文、不解释为质量分数或 ranking，也不手工
恢复 checkpoint。

screening receipt、transport admission、ranking、provider baseline freeze 和 target campaign
仍未生成；Harness cohort binding/convergence audit 继续为 blocked，watcher 的
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`
保持不变。screening terminal 前不修改 frozen plan、不使用 `--retry-failed`、不启动第二套
screening、不调整 router/prompt/weights，也不重启健康的生产 loopback 服务。

## r17 20:11 CST 低频复核与后续收敛设计

本次复核确认 r17 仍在唯一 live non-target screening 中，没有启动任何下游 gate。三个托管
进程的 PID 和命令行 identity 未漂移；frozen plan/source/registry hash 仍分别为
`336fa9c4f81223622a3f94d21cc249b4d20ba9b392a18a2e1aba54fbc5ba6565`、
`7ba7fc8816cbd32881b47419e2d26d2fa26f7460d551b4d1c747195f8ae15b56`、
`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`。

safe state 仍为 `running`，16 个 planned units 中 `0 completed / 1 failed_or_blocked`，
`ready_for_ranking=false`，`network_calls_performed=true`，`target_suite_calls_performed=false`；
state hash 为 `a2d04dc54640a8001e5c471d4ba4e2bd9fae6a99cfb27fa63c06ba1b2aa49480`。第二个
MMLU-Pro unit 的私有 checkpoint 为 `partial`，预期 112 个 case，当前仅记录 111 个
case-result 元数据，checkpoint hash 为
`d69ef3c23cee241f72dcd94c40e4ef00181d4758f71715ab1a391ddd69e8c20c`；其中的 raw provider
output 只能作为私有恢复证据，绝不能变成 score、ranking、freeze 或 completion evidence。

当前研究与实现顺序已经固定为：

1. screening terminal 后仅执行 transport admission；通过固定 2% gate 且至少 3 个
   canonical model eligible 后，才执行 complete-pool ranking、external top-three 和
   provider baseline freeze。
2. baseline freeze 后才调研并实现受约束 portfolio/router optimizer：联合质量后验、
   p50/p95 latency、成本、角色资格和跨 provider 独立性，使用 shadow replay 与独立
   holdout，不允许读取 target labels。
3. 同阶段设计 Judge/Synthesizer confidence calibration 与 independence-aware verifier
   allocation；任何 early-exit 必须证明 process completion，不得把 degraded answer
   伪装成完整 Fusion。
4. 学习闭环只允许 allowlisted policy controls，必须经过 contamination audit、decision
   replay、paired shadow evidence、rollback target 和显式 approval；禁止自动 benchmark-
   driven promotion。
5. 同 cohort Harness 放行后才执行 21-suite target campaign；最终以 paired comparison、
   Holm-Bonferroni（21 x 3 claim family）、effect size、p50/p95 <= 3x、四协议 parity、
   tool/schema 稳定性和污染审计共同决定完成状态。

 在 screening 期间不修改 router、prompt、weights、registry 或生产服务；所有算法调研结果
 先作为可审计设计和 shadow candidate，直到上游 evidence gate 完成。

## r17 第二个 unit 终态与第三个 unit 启动（2026-08-20 20:20 CST）

低频只读复核确认 r17 仍只有一套 screening、同 cohort supervisor 和 lineage watcher，三者
命令行 identity 未漂移。safe state 已更新为 `status=running`、16 个 planned units 中
`1 completed / 1 failed_or_blocked`，`ready_for_ranking=false`，`network_calls_performed=true`、
`target_suite_calls_performed=false`；state SHA-256 为
`0cddbd887aea6115205e33acd14d3333e2c09de398972a253501d3f51fd55d42`，campaign digest 为
`b19c7e4ea9632d95c804d2fc4bd75729d5e80948af56d7958983a2b51045bc6f`。

第二个 112-case unit 已进入 safe state 的 completed 计数，但该 completed 只表示该 unit
满足 transport 层终态，不能解释为质量分数、外部排名或 baseline 证据；不抽取 survivor subset，
不读取其私有 raw provider output。筛选器已按 frozen serial schedule 启动第三个 102-case
unit，最新私有 checkpoint 为 `partial`、`3/102`，SHA-256 为
`71fc050c8aa1364211ff1310d5457e2c65f93f26c50345f12c946d43f95af6d6`；该 checkpoint 仍只
作私有恢复证据，`raw_provider_outputs_persisted=true`，不进入 Git。

transport admission、ranking、provider baseline freeze、official import 和 target campaign
仍未生成，watcher 仍保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。继续低频只读观察，screening terminal 前不修改 frozen
plan/source、router/prompt/weights/registry，不使用 `--retry-failed`，不启动第二套 screening，
不重启健康生产服务。

## r17 第三个 unit 低频进度（2026-08-20 20:29 CST）

本次只读取 safe state、进程 identity、checkpoint 元数据和控制面日志。screening PID
`3739367`、convergence supervisor PID `3741799`、lineage watcher PID `3742593` 仍存活，
命令行继续绑定同一 r17 frozen plan/source 与 r7 probe-bound registry。

safe state 仍为 `status=running`、16 个 planned units 中 `1 completed / 1 failed_or_blocked`，
`ready_for_ranking=false`、`network_calls_performed=true`、`target_suite_calls_performed=false`；
state SHA-256 仍为
`0cddbd887aea6115205e33acd14d3333e2c09de398972a253501d3f51fd55d42`。第三个 102-case unit
的私有 checkpoint 为 `partial`，当前已有 `31/102` 个 case-result 元数据，SHA-256 为
`d68e2327a3e458858da92789e1cbf02d005a9a4b503faed4a42dfa25f06a5077`；其中 raw provider
output 仍只作私有恢复证据，不读原文、不进入 Git、不作为 score/ranking/freeze 证据。

transport admission、ranking、provider baseline freeze、Harness import 和 target campaign
仍未生成；继续按既定 10–20 分钟低频策略观察，不恢复 checkpoint、不使用 `--retry-failed`、
不修改 frozen 输入或生产 router，不重启健康服务。

## r17 第三个 unit 增量复核（2026-08-20 20:41 CST）

本次仍只读取安全元数据和控制面日志。screening PID `3739367`、convergence supervisor
PID `3741799`、lineage watcher PID `3742593` 均存活，命令行继续绑定同一 r17 frozen
plan/source 与 r7 probe-bound registry；生产 loopback 未重启。

safe live state 仍为 `status=running`、16 个 planned units 中 `1 completed / 1
failed_or_blocked`，`ready_for_ranking=false`、`network_calls_performed=true`、
`target_suite_calls_performed=false`；state SHA-256 仍为
`0cddbd887aea6115205e33acd14d3333e2c09de398972a253501d3f51fd55d42`。第三个 102-case
unit 的 checkpoint 仍为 `partial`，本次只核验到 `44/102` 个 case-result 元数据，文件
SHA-256 为 `3c4284f56b9c949e42c55cdffc180397213e93985a32df0e551ddc961bf1a29f`；该私有文件
的 `raw_provider_outputs_persisted=true` 仅表示可恢复证据存在，不读原文、不提交 Git、
不转化为质量、ranking、freeze 或 completion evidence。

下游 transport admission、ranking、provider baseline freeze、Harness import 和 target
campaign 仍不存在；supervisor/watcher 继续保持 `next_gate=screening`、
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。继续 10–20 分钟
低频只读观察，禁止恢复 checkpoint、使用 `--retry-failed`、启动第二套 screening、修改
frozen plan/source、调整 router/prompt/weights 或重启健康生产服务。

## 工程回归验证（2026-08-20 20:51 CST）

使用当前工作树执行 `python3.11 -m pytest tests/ -x -q --tb=short`，进程退出码为 `0`，
结果为 `1066 passed, 7 skipped in 273.89s`。本次没有修改 Python 核心代码、生产 registry
或活动 screening plan；该结果只证明现有工程回归门禁通过，不是 provider 质量、benchmark
排名、baseline freeze 或 Fusion superiority evidence。

r17 仍处于唯一 live non-target screening：safe state 为 `status=running`、
`1 completed / 1 failed_or_blocked`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；第三个 102-case unit 的私有 checkpoint 仍为
`partial`，当时安全元数据为 `70/102`，raw provider output 仍不读取、不提交、不转化为
质量证据。supervisor/watcher 继续保持 `next_gate=screening` 和 target-call fail-closed。

## r17 第三个 unit 终态与第四个 unit 启动（2026-08-20 20:58 CST）

screening 按 frozen serial schedule 完成第三个 102-case unit，并安全计入
`completed_unit_count=2`；完整 campaign 仍为 `status=running`、16 个 planned units 中
`2 completed / 1 failed_or_blocked`，`ready_for_ranking=false`、
`network_calls_performed=true`、`target_suite_calls_performed=false`。safe state SHA-256
为 `bd5333cc4789c133f41485ecd2f86626efc497f22b61305c3e0754d9650019fd`。

筛选器已进入第四个 112-case serial unit。最新私有 checkpoint 为
`checkpoint_status=partial`、`0/112`，文件 SHA-256 为
`d4ca62df881c011cde06132ada864d20e8308832117a858a1b6de523c7048a88`；该文件含
`raw_provider_outputs_persisted=true`，只作为私有恢复证据，不读取原文、不进入 Git、不
解释为质量、ranking、freeze 或 completion evidence。

下游 transport admission、ranking、provider baseline freeze、Harness import 和 target
campaign 仍不存在；supervisor/watcher 继续保持 `next_gate=screening`、
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。本次未恢复 checkpoint、
未使用 `--retry-failed`、未启动第二套 screening、未修改 frozen plan/source、router/prompt/
weights 或生产服务。

## r16 screening 与 transport 终态（2026-08-20 18:37 CST）

r16 唯一 live non-target screening 已自然终态。screening receipt 与 safe state 均为
`status=partial`：16/16 unit terminal，其中 2 个 `completed`、14 个 `failed`，
`ready_for_ranking=false`，`network_calls_performed=true`，`target_suite_calls_performed=false`。
screening state SHA-256 为
`c51ee8a8e39f4ac67cdf34249b30da1ed799e4dccecc49bd289314b526658f81`，receipt SHA-256 为
`c5cf1b28fd37508cd6e31033dcb3d42650c24dfb452adf5f3afe5ebc924f302`，campaign digest 为
`b63b3a231a1f51a8628ea85268cfd304f64a84c0ced416beb062ec739ab1f438`。

完整失败分母保留在私有 receipt：5 个 `102/102`、4 个 `112/112` 的全量 transport
failure，另有 `24/102`、`66/112`、`84/112`、`96/112`、`46/112` 的失败分母；仅有
两个 `102/102` unit 为零 transport failure。以上是 transport evidence，不是质量分数、
ranking 或 baseline freeze 证据；不得抽取成功 unit、拼接旧 cohort 或恢复 checkpoint。

同 cohort supervisor 已只执行允许的 transport admission：receipt SHA-256 为
`9c9bed1793081127f0af4f46f935f134ba437697c25f1ff5b08e205ba5c813d9`，绑定 r16 plan
SHA-256 `9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`、plan digest
`23c1b22a1708e38579f2c8f70f82bfe36a1bb7d4bde20e9aa337e289f8e969ad`、source manifest
SHA-256 `cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4` 和 r7
probe-bound registry SHA-256 `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`。
结果为 `status=blocked`、`eligible_canonical_model_count=0`、最低要求 3，唯一 blocker
为 `transport_admission_fewer_than_minimum_models`；ranking conversion、provider
baseline freeze、official import 与 target campaign 均未启动。supervisor receipt
`status=blocked`，`transport_return_code=2`，`target_benchmark_started=false`。

因此 r16 已封存为 reference-only。下一步只能从 r16 source contract 创建新的 immutable
r17 successor，只改变 `pre_registration.registered_on` 与新的 `selection_seed`，再离线
生成新的 frozen plan、zero-network preflight 和同 cohort Harness 控制面；不得读取 r16
score、transport 结果、checkpoint、survivor subset 或 ranking，不降低 2% gate，不提前
发送 target 请求。生产 loopback 继续保持只读健康状态，不切换 registry、不重启服务。

## r16 生产 loopback registry 只读核验（2026-08-20 17:16 CST）

生产 loopback `127.0.0.1:18900/health` 返回 `status=ready`，服务仍为独立
remote-only 产品，公开模型为三个 Axio tier，四种 API format 均在服务面声明，网络为
`auto -> proxy`，敏感字段和原始 provider 标识均未暴露。服务 PID `1950874` 的
`AXIO_FUSION_REGISTRY_PATH` 明确指向
`private/runs/2026-08-17-composite-cohort-r7-prefusion-full/runtime_registry.probe-bound.r7.private.json`，
该 registry SHA-256 为 `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`，
公开健康投影报告 `model_count=21`、`provider_count=4`、profile-set SHA-256
`e330997565bc0a19f3df2353ff7db24dfdfc68591adb2521a88e5a6a5f38dcce`。

这与当前 r16 frozen plan 一致：r16 screening、supervisor 和生产服务均绑定 r7
probe-bound registry；因此不能把 21 profiles 误判为未通过 r43 的 10-profile serving
基线，也不能在 live screening 期间切换 registry 或重启服务。AGENTS.md 中 r43 的 10-profile
检查项保留为历史阶段约束；r16 terminal 后若进入新的生产 serving 里程碑，再单独审计并
决定 registry 是否需要 successor 切换。本次仅记录健康和绑定证据，不产生 provider 能力或
superiority claim。

## Composite cohort r15 terminal 与 r16 当前锚点（2026-08-20 14:55 CST）

r15 已自然终态并完成同 cohort 的 transport admission。最终 screening receipt
`private/runs/2026-08-20-composite-cohort-r15/screening.live.receipt.r15.private.json`
为 `status=partial`，16/16 unit terminal，其中 1 completed、15 failed；campaign digest
为 `61a02eaecfcfa17b1e9458c8384ffcff47a4addef63af89aa0efed1c5aee67d7`，state SHA-256 为
`262c2711bf7d5c5e42d21fa7e303e27d7bdc123deb66f0a7ebc3f8af662c919d`。唯一 completed unit
为 `112/112`、transport failure `0`；失败分母完整保留为
`112/112 ×5`、`104/112`、`102/102 ×2`、`102/112`、`101/102`、`98/102`、`93/102`、
`92/102`、`80/102`、`60/102`，均超过固定 `2%` transport gate，唯一 `112/112` completed
unit 除外。以上是完整 transport 分母，不是质量分数或 ranking。

transport admission receipt
`private/runs/2026-08-20-composite-cohort-r15/transport_admission.r15.private.json`
为 `blocked`：8 个 candidate canonical 中 `eligible_canonical_model_count=0`，最低要求
为 3，唯一 blocker 为 `transport_admission_fewer_than_minimum_models`。supervisor 返回
`transport_return_code=2`、`ranking_file_sha256=""`、`target_benchmark_started=false`；
没有 ranking、provider baseline freeze 或 target request，所有完整失败 evidence 保留为
reference-only。

r16 已从 r15 source contract 创建新的 immutable successor，只改变 registered_on 与
selection seed，不读取 r15 score、transport、checkpoint、survivor subset 或 ranking：

- source manifest SHA-256：`cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`；
  successor receipt SHA-256：`f0cbfa13788314f85bb4e4abf889a9a522a5df4cafcb65efeda6fed0457c1ede`；
- selection seed：`composite-r16-2026-08-20-transport-successor`；selection seed hash：
  `0f05adcba97d02c23fecdb36d2be6029ed73cf0e9d46a8aef2321441b0125134`；
- frozen plan SHA-256：`9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`；
  plan digest：`23c1b22a1708e38579f2c8f70f82bfe36a1bb7d4bde20e9aa337e289f8e969ad`；
- plan 为 `ready=true`，2 source families、8 canonical groups/9 replicas、16 serial units、
  `max_workers=1`、固定 `2%` fail-fast、estimated provider calls `1712`；
- zero-network preflight 为 `preflight_ready`，state SHA-256
  `3f7b5b367d8ad6d0887f1bd566d61f7d9463fc54adbfd5208090a3dfaf482310`，receipt SHA-256
  `b61c75dd01902b80d1ba6e2b6ac2359aff49765fbc66ceb9ffd78531ea2bf9fd`，campaign digest
  `af9aeed814a6e20940dd8f2a3d497e3ce9115d326ffd9e2e999bef826e2e31dc`，
  `network_calls_performed=false`、`target_suite_calls_performed=false`；
- r16 Harness 控制面已离线生成，pin 6/6 ready、execution plan `ready_to_execute`，
  convergence audit `blocked/next_gate=screening`，target calls 与 provider calls 均为 false。

当前唯一下一步是启动一套绑定 r16 plan/source、r7 probe-bound registry/admission 的
live non-target screening；启动前必须再做命令行 identity、PID、日志和 preflight hash 核验。
不得恢复 r15、不得使用 `--retry-failed`、不得启动第二套 screening；terminal 后才可由
同 cohort supervisor 执行 transport admission，只有 admission ready 才可进入完整池 ranking。

## r16 live screening 启动里程碑（2026-08-20 15:07 CST）

r16 唯一 live non-target screening 已使用 `setsid/nohup` 启动：screening PID `3231684`、
convergence supervisor PID `3231745`、lineage watcher PID `3231746`。三者命令行均绑定
r16 frozen plan/source 与 r7 probe-bound registry、provider probe、operational admission；
没有第二套 screening。启动后 PID、命令行 plan identity、supervisor 初始 wait 事件和 watcher
初始 convergence snapshot 均通过核验，未发现参数解析或 `ModuleNotFoundError`。

当前 screening 尚未产生 safe live state 或 checkpoint；screening receipt、transport admission、
ranking、provider freeze、official import 和 target campaign 均不存在。supervisor 正等待
screening terminal，watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。后续只做 10-20 分钟低频 PID/state/checkpoint/log 检查，
不得恢复 r15/r16 checkpoint、不得使用 `--retry-failed`、不得修改 frozen plan、不得启动第二套
screening；screening terminal 后才由同 cohort supervisor 执行 transport admission。

## r16 低频进度复核（2026-08-20 15:24 CST）

低频只读复核确认 r16 唯一 screening、convergence supervisor、lineage watcher 仍由 init
托管，三者命令行仍绑定 r16 frozen plan/source 与 r7 probe-bound registry/probe/admission。
当前活动 unit 的私有 checkpoint 已推进到 `31/102`，状态为 `partial`，checkpoint SHA-256 为
`779e5b887cbe275e236dae269741e28b02446711976b8de86b236d10fac4fb62`。该 checkpoint 仅是
私有恢复证据，包含 raw provider output，不能解释为 unit 完成、质量分数或 ranking 证据。

safe live state、screening receipt、transport admission、ranking、provider freeze、official
import 和 target campaign 仍未生成；supervisor/watcher 继续保持 `next_gate=screening`、
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。生产 loopback
`/health` 已只读核验为 `ready`，公开模型仍仅为三个 Axio tier，服务网络选择为 configured
proxy；这属于工程健康证据，不是 provider 能力或 superiority 证据。后续继续低频检查，
screening terminal 前不得执行下游 gate。

## r16 低频进度复核（2026-08-20 15:29 CST）

提交后的只读复核确认 r16 唯一 screening、convergence supervisor、lineage watcher 仍由 init
托管且命令行 identity 未变。当前活动 unit 的私有 checkpoint 已推进到 `41/102`，状态为
`partial`，checkpoint SHA-256 为
`eb886b1d5bea0358b281fadba690fd54d0dc6451938c9ee03abd05696ba046a1`。该 checkpoint 属于
私有恢复证据，不能解释为 unit 完成、质量分数、ranking 或 baseline freeze 证据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续保持
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续仍只做低频检查，screening terminal 前不执行任何下游 gate，不恢复 checkpoint、不使用
`--retry-failed`、不修改 frozen plan、不启动第二套 screening。

## r16 过半进度复核（2026-08-20 15:35 CST）

低频只读复核确认 r16 唯一 screening、convergence supervisor、lineage watcher 仍由 init
托管，命令行仍绑定 r16 frozen plan/source 与 r7 probe-bound registry/probe/admission。
当前活动 unit 的私有 checkpoint 已推进到 `50/102`，状态为 `partial`，checkpoint SHA-256 为
`173ce7cd96c6789f2d330458c7ff5c51973b814226c660a61fc166d90d58852e`。该 checkpoint 仅是
私有恢复证据，不能解释为 unit 完成、质量分数、ranking 或 baseline freeze 证据。

本次同时重新核验 frozen inputs 未漂移：r16 plan SHA-256 仍为
`9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`，source SHA-256 仍为
`cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`，zero-network preflight
state/receipt SHA-256 仍分别为 `3f7b5b367d8ad6d0887f1bd566d61f7d9463fc54adbfd5208090a3dfaf482310`
和 `b61c75dd01902b80d1ba6e2b6ac2359aff49765fbc66ceb9ffd78531ea2bf9fd`。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续仍只低频检查，screening terminal 前不执行任何下游 gate。

## r16 低频进度复核（2026-08-20 15:43 CST）

低频只读复核确认 r16 唯一 screening、convergence supervisor、lineage watcher 仍由 init
托管，三者仍绑定 r16 frozen plan/source 与 r7 probe-bound registry/probe/admission。当前活动
unit 的私有 checkpoint 已推进到 `63/102`，状态为 `partial`，checkpoint SHA-256 为
`a030b9b77c7b5372b99e1adc71678825d93b24aa3f00fe936108cf17ab451bee`。该 checkpoint 仍是
私有恢复证据，不能解释为 unit 完成、质量分数、ranking 或 baseline freeze 证据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续保持
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
screening terminal 前继续只做低频 PID/state/checkpoint/log 检查，不恢复 checkpoint、不使用
`--retry-failed`、不修改 frozen plan、不启动第二套 screening，也不执行下游 gate。

## r16 低频进度复核（2026-08-20 15:50 CST）

低频只读复核确认 r16 唯一 screening、convergence supervisor、lineage watcher 仍由 init
托管且 command-line identity 未变。当前活动 unit 的私有 checkpoint 已推进到 `79/102`，
状态为 `partial`，checkpoint SHA-256 为
`d8371b7c7a84f04c0bdb0b6c1ff922d340f797f83b3c21f3359c0eff20ba69d7`。该 checkpoint 仅是
私有恢复证据，不能解释为 unit 完成、质量分数、ranking 或 baseline freeze 证据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续保持
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续仍只低频检查，screening terminal 前不恢复 checkpoint、不使用 `--retry-failed`、不修改
frozen plan、不启动第二套 screening，也不执行任何下游 gate。

## r16 首个 unit 终态与第二个 unit 启动（2026-08-20 15:58 CST）

r16 safe live state 已首次生成，SHA-256 为
`fa223d6f6fc9ba7a1fc1805bb45ffeb0cbeaf856dd528b29f1878cf6f4b4a3e9`；campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 1 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。首个 unit
`3b166a5e9721a833999066b5886263c93b055691dfb2890267e380f9a3ef1d26` 已自然终态失败：
`78/102` scored、`24/102` transport failures、failure rate `0.235294117647`，reason code
为 `screening_unit_transport_failure_rate_exceeded`。完整分母保留为 provider evidence，不能
解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第二个 unit；启动时 checkpoint 为 `1/112`。截至
`16:00 CST` 的低频复核，当前私有 checkpoint 已推进到 `14/112`、状态 `partial`，SHA-256
为 `cf9a0bacb5ed3fd57993cf7263bbd90a77986067735d55bfb3304200340911a2`。该 checkpoint 仅为
私有恢复证据，不能作为 unit 完成或 transport admission 依据。screening receipt、transport
admission、ranking、provider baseline freeze、official import 与 target campaign 仍未生成；
supervisor/watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复 checkpoint、不得使用 `--retry-failed`、不得
修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 第二个 unit 终态与第三个 unit 启动（2026-08-20 16:14 CST）

safe live state 更新为 SHA-256
`8840155fc4dded6d02361c9d4ab70b495c89885eb7fa62ca5692a269c4bd41d2`；campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 2 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。第二个 unit
`f60834dbf975d0c2b0bb12ccb3422197853d504046b1df1d923b56e188958179` 已自然终态失败：
`66/112` scored、`46/112` transport failures、failure rate `0.410714285714`，reason code
为 `screening_unit_transport_failure_rate_exceeded`。该完整分母继续作为 provider transport
evidence 保留，不能解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第三个 unit，当前 checkpoint 属于新的 `102`-case
unit、状态 `partial`；该中间 checkpoint 仅是私有恢复证据。screening receipt、transport
admission、ranking、provider baseline freeze、official import 与 target campaign 仍未生成；
supervisor/watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复任一 checkpoint、不得使用 `--retry-failed`、
不得修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 第三个 unit 终态与第四个 unit 启动（2026-08-20 16:18 CST）

safe live state 更新为 SHA-256
`f0e37f0ed5bcb83197a00364492a5bd7803f03e0caf5eec58bbc269f6533d01a`，campaign digest 为
`f2619ac4c1dcfe6189884a71da44adb306a18543bfbc8c82c460bed430f80577`；campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 3 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。第三个 unit
`e84723db16da485150045f926a0e0a2540250ceedc1009d811c9d11f0b8cc1a5` 已自然终态失败：
`0/102` scored、`102/102` transport failures、failure rate `1.0`，reason codes 为
`screening_unit_no_scores` 与 `screening_unit_transport_failure_rate_exceeded`。完整失败分母
继续保留为 provider transport evidence，不能解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第四个 unit，当前 checkpoint 属于新的 `112`-case
unit、状态 `partial`；该中间 checkpoint 仅是私有恢复证据。screening receipt、transport
admission、ranking、provider baseline freeze、official import 与 target campaign 仍未生成；
supervisor/watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复任一 checkpoint、不得使用 `--retry-failed`、
不得修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 第四个 unit 终态与第五个 unit 启动（2026-08-20 16:54 CST）

r16 safe live state 更新为 SHA-256
`a27ee4a15e2c1ebe892f9ddfcf29d421ca20cf97cf9423541dc56a4f64b3496d`；campaign digest 为
`ea29512ad166c949aa412310cc0fe5dd32cdb7c2d838648d18f82eb175a2c896`。campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 4 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。第四个 unit
`69efb856ac5b893e75548c5d92ed500b1c8e6deac0e8d93b672e7196aa91236a` 已自然终态失败：
`46/112` scored、`66/112` transport failures、failure rate `0.589285714286`，reason code
为 `screening_unit_transport_failure_rate_exceeded`。完整失败分母继续保留为 provider
transport evidence，不能解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第五个 unit；当前私有 checkpoint 属于新的 `102`-case
unit，`0/102`、状态 `partial`，checkpoint SHA-256 为
`9fd45ccb2b29a1f060d5cbbadb6563ce93773af5e4daf1a0383aa2469fde5250`。该 checkpoint 仅是
私有恢复证据，不能作为 unit 完成、transport admission 或 ranking 依据。screening receipt、
transport admission、ranking、provider baseline freeze、official import 与 target campaign
仍未生成；supervisor/watcher 继续保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复任一 checkpoint、不得使用 `--retry-failed`、
不得修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 低频进度复核（2026-08-20 15:15 CST）

低频只读复核确认 r16 唯一 screening、convergence supervisor、lineage watcher 仍由 init
托管且命令行 identity 未改变。当前活动 unit 的私有 checkpoint 已推进到 `16/102`，状态为
`partial`，checkpoint SHA-256 为
`4e746fe5901b3b1ee2d4a82d0dfd326e7852d66ef371d0b920a3419dbe1bd95f`；该文件属于私有恢复
证据，含 raw provider output，不能解释为 unit 完成、质量分数或 ranking 证据。safe live state
仍未生成，完整 screening 分母、transport admission、ranking、provider freeze、official
import 和 target campaign 均不存在；supervisor/watcher 继续保持 `next_gate=screening`、
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。

本次只读工程审计发现的历史 benchmark runner 裸 `except:` 与重复路径，已在 Goal framing 中
列为 baseline freeze 后的独立遗留清理工作；本轮不修改这些脚本，不改变 r16 frozen plan、
provider registry、router 权重、prompt、panel policy 或任何 benchmark-driven routing，避免
把工程清理混入当前 provider evidence lineage。后续仍只按低频检查推进，screening terminal
前不得执行下游 gate。

## Composite cohort r15 当前主线快照（2026-08-20 13:48 CST）

r15 是当前唯一允许的 live non-target screening。冻结输入保持不变：plan 文件 SHA-256
`555350be7d681bd777094804b1936f65f1d05890fe33e87ec56bd6930eb846c3`、plan digest
`d41becf244fcf5234d622a95ea95e8898ef94bd9a40d88e2ebef2e0ecaf3b038`、source SHA-256
`745312def06231f320c7c9a48dcbd81e6742ee67800d8ecfc9d4d3309d620aec`、r7 probe-bound
registry SHA-256 `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`，
`max_workers=1`、固定 `2%` transport fail-fast gate。唯一 screening PID 为 `2871629`，
同 cohort supervisor/watcher PID 为 `2880595`/`2881730`。

截至 13:48:48，safe state SHA-256 为
`b27bee06ab1e75a97ce7f34b087bf570dad7105497cfca7dfedf88cbf55b6eea`，campaign 仍为
`status=running`、16 planned unit 中 `1 completed / 7 failed`、`ready_for_ranking=false`；
8/16 unit 已 terminal，9/16 unit 正在执行。completed/failed 的每个完整 transport 分母
均已保留，不能抽取 completed subset、恢复 checkpoint、使用 `--retry-failed` 或启动
第二套 screening。当前 task
`23d2aad8799078241760998a00ba2db1e3852b2503cfbe087bcde2c1e4cbe154` 的 checkpoint 为
`0/112`、SHA-256 `41f510d86b234361e7543d56668e00735f1312c239426ebe2888fc3bc2bcdbb0`。

screening terminal 前 transport conversion/ranking/provider freeze/official import/target
campaign 全部禁止；`target_suite_calls_performed=false`、`next_gate=screening`、
`target_suite_calls_allowed=false` 仍成立。terminal 后只允许同 cohort 的完整分母
transport admission -> complete-pool ranking -> external rank evidence -> provider
baseline freeze -> official/audited Harness import -> convergence audit -> 21-suite
campaign -> paired statistics/latency/API parity/contamination/final audit。

### r15 14:00 工程与 live 进度增量

14:00 CST safe state SHA-256 为
`94a127931d3825b413e5c208b3a795dc6eb76c9026ef549eb46322805501a7ea`，r15 仍在
`screening` gate：16 planned unit 中 `1 completed / 10 failed`，11/16 已写入 state，剩余
5 个未 terminal，`ready_for_ranking=false`。failed transport 分母完整保留为
`112/112 ×5`、`102/102 ×2`、`101/102`、`80/102`、`60/102`，不能抽取 survivor subset，
不能恢复 checkpoint、使用 `--retry-failed` 或降低 `2%` gate。当前活动 task 为
`13c5304ac5ef6a492ac6f5a023842224fb2fd64386f68a32465b3d97027eea3a`，checkpoint `6/102`，
SHA-256 `0aba0016052153885e3562b789fc917c6dd8a10e6b8b0eefb721c2fb8e7e85d1`。

工程回归已完成：`python3.11 -m pytest tests/ -x -q --tb=short` 为 `1066 passed,
7 skipped`。这是代码基线证据，不是 provider ranking 或 Fusion superiority 证据；
screening terminal 前仍禁止 transport conversion、ranking、freeze、official import 与
target campaign。

### r15 14:04 live screening 增量

截至 14:04:57，safe state SHA-256 为
`3b0e4a3001423a964b1f5fb907acca2e30b2e48b10cb6798d26a0fe12a022096`，r15 仍为
`status=running`：16 planned unit 中 `1 completed / 11 failed`，12/16 已写入 state，剩余
4 个未 terminal。failed 完整 transport 分母保留为 `112/112 ×5`、`102/102 ×2`、
`101/102`、`92/102`、`80/102`、`60/102`，不允许抽取 survivor subset、恢复 checkpoint、
使用 `--retry-failed` 或降低 `2%` gate。当前 task
`dd6e3d631867c96b5417ca5860af672e9de80961eae4f317e6c17e96fac9559a` 的 checkpoint 为
`2/112`，SHA-256 `0a75d69049abf3da03e37f9def47833f600ff8d49f937ee374bfdc5c37e915a8`。

screening terminal 前后置 gate 仍全部关闭：`target_suite_calls_performed=false`、
`next_gate=screening`、`target_suite_calls_allowed=false`；terminal 后才可由同 cohort
supervisor 执行 transport admission 与完整池 ranking。

### r15 14:17 live screening 增量

截至 14:17:37，safe state SHA-256 为
`e4fbe624e2a0d8e7692dc6eaa7698f9197d27afea77650b8ad74ebb5a10d557d`，r15 仍为
`status=running`：16 planned unit 中 `1 completed / 12 failed`，13/16 已写入 state，剩余
3 个未 terminal。新增 failed unit 为 `102/112` transport failures；完整 failed 分母保留
为 `112/112 ×5`、`102/112`、`102/102 ×2`、`101/102`、`92/102`、`80/102`、`60/102`，
不允许恢复 checkpoint、使用 `--retry-failed`、拼接 survivor subset 或降低 `2%` gate。
当前活动 task 为 `fce71276a5c3344d9a534c42a84b5f75fdee4d97b7f9660bb9af3796f8ec5166`，checkpoint
`6/102`，SHA-256 `2c4aa0ad9ed3c423ec599412781f87e3d124f347c8b63fec2555007d8eac570a`。

`target_suite_calls_performed=false`、`next_gate=screening`、`target_suite_calls_allowed=false`
继续成立；screening terminal 前禁止 transport conversion、ranking、freeze、official import
与 target campaign。

## Composite cohort r14 successor intake（2026-08-19）

r13 已完整 terminal 但 transport admission blocked：16/16 unit 中只有 7 个通过，8 个
candidate canonical 中只有 2 个同时通过两套独立 source family 的 `2%` transport gate，
低于固定的 3-model 最低门槛。r13 的 state、unit、transport、supervisor 和 Harness
artifact 全部保留为 reference-only；r14 不读取 r13 score，不复用 r13 transport receipt，
不恢复 checkpoint，也不拼接 survivor subset。

r14 仅从 r13 source contract 创建新的 immutable successor，改变 selection seed 和注册事件：

- source manifest：文件 SHA-256
  `e1a676e3af28f48d9f5b5c374542875c5b5f773bf4053c2cf9cb68ea5e32464c`；successor receipt
  SHA-256 `16e64cbef1dfe7d1bc7f454ae5df44b3c8113921c7b87d52bd3574720ee55785`；selection
  seed hash `b9e8c86c72d875fdbc32c97b771cb73c6924385f873c37199aca78cc7c0b8bb9`；
- frozen plan：文件 SHA-256
  `988c0d793af89b1bdf0d681c200dca297ace43e9ce3d09cbe3f3fa8ad4bdefd0`，plan digest
  `7937b8b99d71e37fc816915a37a62fe300c74ca3128ce1f83f511b5dc473a2ef`，8 canonical
  groups/9 profiles、2 source families、16 serial units、`max_workers=1`、fail-fast
  transport gate、预注册 provider calls `1712`；
- zero-network preflight：state 文件 SHA-256
  `8b453e782bf8f7d475cca9bc749cf8728b65cdfe5a1317ff243be0fa563a0bd8`，receipt SHA-256
  `1eb08c69ce811408a60d5e9bfbd06ca7e5bde0d640f48bbb0286c27c5384034c`，campaign digest
  `19a0ce6375812b654b49891cc1dd9e01618cdb320261cb6192959df66375682a`，
  `status=preflight_ready`、`network_calls_performed=false`、
  `target_suite_calls_performed=false`、`reason_codes=[]`。

r14 Harness 控制面已离线生成于
`private/runs/2026-08-19-composite-cohort-r14/harness_control.successor/`：pin SHA-256
`22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`（6/6 ready）、
execution plan SHA-256 `dbb56204c2125eb84fbddba44252381bb0cfa476d11252feaad3e0e2af01c46a`
（ready to execute）；acquisition、official import、provider freeze 与 cohort binding
缺失，convergence audit SHA-256
`86ff0e2e3c05716d326eb04e5c3d91b4651dadf8d643b6a67f55ad3681387d3e` 为 blocked，
`next_gate=screening`、`target_suite_calls_allowed=false`。Harness scaffold 只证明控制面
结构，不授权 target benchmark。

r14 的下一步是只启动一套 `baseline-screening-run --live`，绑定上述 frozen plan、r7
probe-bound registry 和 r7 operational admission；screening terminal 后由同 cohort
supervisor 依次执行 transport admission 和完整 pool ranking。任何 partial/transport
blocked 结果继续创建新的 immutable successor，不降低 gate，不做 superiority claim。

### r14 live screening 启动里程碑（2026-08-19 23:19 CST）

r14 唯一 live non-target screening 已通过 `setsid/nohup` 启动，screening PID 为
`1300532`，supervisor PID 为 `1301981`，watcher PID 为 `1302805`；三者命令行均绑定
`baseline_screening_plan.r14.private.json`，没有并发第二套 screening。supervisor 已进入
同一 PID/plan identity wait，watcher 初始 convergence audit 为 `blocked`、
`next_gate=screening`、`target_suite_calls_allowed=false`。记录时 screening 仍在首个
provider/preflight 阶段，live state 与 receipt 尚未落盘，尚未完成任何 unit；不修改 frozen
plan、不恢复 r13 checkpoint、不发送 target 请求。

### r14 screening 进度快照（2026-08-19 23:33 CST）

r14 首个 `livebench_official_final_text_slice` unit 已自然终态完成：task
`9f3c65a3400e64e7060275409ecb94735aa388d694a4be002d495605ee218d13`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.813725490196`，p50/p95 latency `7316.760ms/20261.479ms`。
campaign 仍为 `status=running`、`planned_task_count=16`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=0`、`ready_for_ranking=false`；state SHA-256 为
`48c5c55ac7d6273af07ec641b4cd572e5962af424e4fe3cfd888dd99e73dce39`，campaign digest 为
`4d3bf242ae076f34a2cae6d6eab6103f450764f6f4a8dc8f8019535fbb2a395f`。运行器已进入第二个
unit，task `99a42d6882bac42a2b7e465638bbcf57354718054480065a25c0487a3d5adf8c` 的 private
checkpoint 为 `2/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

### r14 screening 进度快照（2026-08-19 23:53 CST）

r14 第二个 `mmlu_pro_official_test_2026_07_20` unit 已自然终态完成：task
`99a42d6882bac42a2b7e465638bbcf57354718054480065a25c0487a3d5adf8c`，完整 `112/112`
case，`scored_case_count=112`、transport failure `0/112`、failure rate `0.0`，reason
codes 为空；mean score `0.848214285714`，p50/p95 latency
`7163.040ms/25988.358ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=2`、`failed_or_blocked_unit_count=0`、`ready_for_ranking=false`；
state SHA-256 为 `2d69d5d847cc29d5df82855ae341e7ea0084895c70d4f5cf21348c6f1ff34cc8`，
campaign digest 为 `432413b2a8312158f1c28d6673ed27c0ebf8ef03299c0bcc6bcc43505744a79a`。
运行器已进入第三个 task `8172ac60d181dd7bbdcd78e0481af36cba1d342f38e7ea5aeb3e548177326828`，
private checkpoint 为 `2/102`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

### r14 screening 进度快照（2026-08-20 00:22 CST）

r14 第三个 unit 已自然终态完成：task
`8172ac60d181dd7bbdcd78e0481af36cba1d342f38e7ea5aeb3e548177326828`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.754901960784`，p50/p95 latency
`12490.977ms/35899.950ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=3`、`failed_or_blocked_unit_count=0`、`ready_for_ranking=false`；
state SHA-256 为 `d08873dff6efa3b10f657fcb4aedd306bddf0cc4627ecc8b5c1555a81969e409`，
campaign digest 为 `8b77d0094a34a8c7ed69f9f7a0f1cb54d726ec9e4f08597513406d38ba1673c5`。
运行器已进入第四个 task `23042b50a134f1e3f11dc98b2af5100d059723861ebc4990995a2f4d5ff715a`，
private checkpoint 为 `0/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

### r14 screening 进度快照（2026-08-20 00:33 CST）

r14 第四个 unit 已自然终态失败：task
`23042b50a134f1e3f11dc98b2af5100d059723861ebdc4990995a2f4d5ff715a`，完整 `112` case
分母中仅 `scored_case_count=9`，transport failure `103/112`、failure rate
`0.919642857143`，触发冻结的 `2%` fail-fast gate；reason code 为
`screening_unit_transport_failure_rate_exceeded`，p50/p95 latency
`50839.414ms/90087.512ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=3`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
state SHA-256 为 `f5671720569d866782cdf7e0604ab591ad20c0fe1b9b02192f602542eed6d6b1`，
campaign digest 为 `95b172f2cb42852ff7abfeabe838be0e9389655658fdabbd9669920a9af79c4d`。
运行器已进入第五个 task `b8ca59ff11f37f3a5ba609e1dba4f9bdf592d60bc3e24b61a1f5bb5530d7acc2`，
private checkpoint 为 `8/102`；失败 unit 保留在完整分母中，不恢复、不拼接、不触发 ranking 或
target benchmark。

### r14 screening 进度快照（2026-08-20 00:50 CST）

r14 第五个 unit 已自然终态完成：task
`b8ca59ff11f37f3a5ba609e1dba4f9bdf592d60bc3e24b61a1f5bb5530d7acc2`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.754901960784`，p50/p95 latency
`10284.959ms/22983.527ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=4`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
state SHA-256 为 `dc14381aa048318fdd6f16adea0d270cf53afbc4286d78a40214cf5c121bba6c`，
campaign digest 为 `376ebe529d128b1a85afbcc18e6127022e3c72c61fb20f49cfa59d0fc1b9ea7e`。
运行器已进入第六个 task `c4f5145ed59a6f45b87779da2f7211ed024a6c7fb030845c3f0fd3dc005ef835`，
private checkpoint 为 `1/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

### r14 screening 进度快照（2026-08-20 01:20 CST）

r14 第六个 unit 已自然终态完成：task
`c4f5145ed59a6f45b87779da2f7211ed024a6c7fb030845c3f0fd3dc005ef835`，完整 `112/112`
case，`scored_case_count=111`、transport failure `1/112`、failure rate
`0.008928571429`，低于冻结的 `2%` gate，reason codes 为空；mean score
`0.864864864865`，p50/p95 latency `13592.488ms/30939.008ms`。campaign 仍为
`status=running`、`planned_task_count=16`、`completed_unit_count=5`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；state SHA-256 为
`b5ebfaf7e0900573fe58a1f0befeb93105a270d1df480c6d52dec37107ef508f`，campaign digest 为
`473087a3e4dc1d6bcab4fa151d309d27eb8eb904a6e0968d5f0b3a1fdc5702b1`。运行器已进入第七个
task `6eaa0f8c67c41d730c04341f002617100aabe5859980653683e56c5493b04400`，private
checkpoint 为 `1/102`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

### r14 screening 进度快照（2026-08-20 01:50 CST）

r14 第七个 unit 已自然终态完成：task
`6eaa0f8c67c41d730c04341f002617100aabe5859980653683e56c5493b04400`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.745098039216`，p50/p95 latency
`13063.101ms/33250.024ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=6`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
state SHA-256 为 `88da71b37c84853265d16f0b857b5770b3466d2b5c4ec9d0653ee1bf43da50bb`，
campaign digest 为 `1ef641d774f872f06ebbcb8ca95f79c8fdf80764b0897e358f5b20830a57b366`。
运行器已进入第八个 task `c320006a0f407b64da094d08e9029b54020055229f5f0ad69764b2d722a4bf13`，
private checkpoint 为 `2/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

### r14 screening 进度快照（2026-08-20 01:54 CST）

r14 第八、九个 unit 已连续自然终态失败，完整失败分母均已保留：

- task `c320006a0f407b64da094d08e9029b54020055229f5f0ad69764b2d722a4bf13` 完成
  `112/112` case，transport failure `112/112`、failure rate `1.0`，未产生 score；p50/p95
  latency `38215.424ms/40156.998ms`，reason codes 为
  `screening_unit_no_scores`、`screening_unit_transport_failure_rate_exceeded`；
- task `7c6cc2b7f8344701be39eb07d1194f7baa95ae5b873a0acd4225f2b7cb02db2b` 完成
  `102/102` case，transport failure `102/102`、failure rate `1.0`，未产生 score；p50/p95
  latency `38159.141ms/73895.950ms`，reason codes 同上。

campaign 仍为 `status=running`、`planned_task_count=16`、`completed_unit_count=6`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`；state SHA-256 为
`0732913290fa2d054d85b8f2e8409734ce58215643808fe7fd0bf40c89214401`，campaign digest 为
`e29630b18bced05b23409f9bc513da74360cc56510fd12e4a532ebbfce08d7dd`。运行器已进入第十个
task `27e9f2ffb5dee02a405ac17d06af581220f82c191a70999d0a0a227e0483fb44`，private checkpoint
为 `0/112`；不恢复失败 unit、不拼接 survivor subset、不触发 ranking 或 target benchmark。

### r14 screening 进度快照（2026-08-20 02:34 CST）

r14 第十个 unit 已自然终态完成：task
`27e9f2ffb5dee02a405ac17d06af581220f82c191a70999d0a0a227e0483fb44`，完整 `112/112`
case，`scored_case_count=111`、transport failure `1/112`、failure rate
`0.008928571429`，低于冻结的 `2%` gate，reason codes 为空；mean score
`0.873873873874`，p50/p95 latency `19156.567ms/35920.312ms`。campaign 仍为
`status=running`、`planned_task_count=16`、`completed_unit_count=7`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`；state SHA-256 为
`c6bc4961893103a648b4ddf4c97f1ebb9813b7a26bc81400c21e224781ac6676`，campaign digest 为
`1cc59aaa048a5a956e326f1340fdb7bc01281007366c50add76a87c0b89674eb`。运行器已进入第十一个
task `22108aa291aa151c6dc679344e62e5809d149b5455f7f26573bd6409d758f784`，private checkpoint
为 `5/102`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

## Composite cohort r12 successor intake（2026-08-19）

r11 已完成 16/16 个 serial unit，但 campaign 为 `partial`（11 completed、5 failed）。
其 transport-only admission 为 `ready`（5/8 canonical eligible），但 complete-pool
ranking 被完整 campaign/source coverage 门禁拒绝；r11 已封存为 `reference_only`，不得
复用 transport、candidate inventory、completed subset、ranking 槽位或任何旧 cohort
freeze/binding。终态证据见
`docs/operations/composite_r11_screening_live_2026-08-19.md`。

当前主线已切换为新的 immutable r12 successor。r12 只从 r11 source successor 复制
source contract，改变 selection seed 和新的 successor registration 事件；不恢复或拼接
r11 checkpoint，不修改 r11 frozen plan，不重复上游探测：

- source successor：文件 SHA-256
  `44bc2c7ec6f9db22fc2724a17cb60036c50abcd5c646ebc2401ccac3fadc05e7`，receipt SHA-256
  `b85fdd91ecb0faaf0f5b5e4f9e940e24d5cf09fd862348619d288991d302ef59`，selection seed
  hash `0557b404e7ad918bf19bcb10880dc4aaffa91911a3574eb6ad52959e3b330ed6`，状态为
  `ready`；
- frozen plan：文件 SHA-256
  `58e2a0acd39801a6245082d67e3ef5f93aa543836d28dd8f9a3ca94bba4c6c65`，plan digest
  `b38052946a726ddb9d03aa6b4a04c19804e021731e508fa1048a63101afacde4`，16 个 serial
  unit、2 个独立 source family、8 个 canonical groups/9 个 profiles、`max_workers=1`；
- registry 仍绑定 r7 probe-bound registry SHA-256
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`，只复用同一
  r7 operational admission，不输入 r11 transport receipt；
- zero-network preflight：receipt SHA-256
  `06ca721adac5984d153bd84d101655246f40afe460cf019fbe8798ae517061a9`，state SHA-256
  `353f2c38e7661c6f9da0d79e59afc8cec20fe718af86e16ef5c09187dff4d4af`，campaign digest
  `741e0c306ebcab33545300c8581467f828db504d1e635d2cc53e07166eb4ca3a`，
  `status=preflight_ready`、`network_calls_performed=false`、`target_suite_calls_performed=false`。

r12 Harness 控制面已按 r12 output path 离线重建：复用 6/6 hash-only pin（pin SHA-256
`22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`）以及已验证的
21-suite dataset/case-hash 定义，不复制原始 checkout、数据内容、答案、provider output
或旧 run。execution plan 为 `ready`（SHA-256
`19e1cb2f0d42ce0a9d7b9577b584112c0438123200921e654de88a6635e2ce3a`）；acquisition、
official import、cohort binding 和 convergence audit 均按前置缺失保持 `blocked`，
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。

固定推进顺序：

```text
r12 live non-target screening
-> terminal transport admission (failure-rate only)
-> complete-pool ranking
-> provider baseline freeze
-> same-cohort official import
-> convergence audit ready_for_target_campaign
-> 21-suite target campaign
```

只有 r12 的 complete-pool ranking、provider freeze、official import 和 convergence audit
全部同 cohort ready，才允许 target calls；不做 superiority claim，不选择 completed
subset，不降低固定 3-model transport gate。

## Composite cohort r13 successor intake（2026-08-19）

r12 已完整 terminal，但 campaign 为 `partial`，complete-pool ranking 被拒绝；r12
transport/ranking/supervisor/binding/audit 全部保留为 reference-only，不恢复 checkpoint、
不拼接 completed subset。当前已创建新的 immutable r13 successor：

- source manifest：文件 SHA-256
  `762e4a63d5d36e3996c710b7f77608b494d4507ace314bdf3bcc16acdce43e94`，selection seed
  hash `f8a35d8235338707976f2509d464fb0d35aae44f31d42f780679378d55373012`；
- frozen plan：文件 SHA-256
  `fde4aa68dd56eb4a724e2bb90fe7a199ed009b5b1a84928b4caa57e0da341d05`，plan digest
  `899f3cb3f7539ec0789458f21a85be7357042e0cb7275a171ba16ea40d030f97`，16 serial units、
  8 canonical groups/9 profiles、`max_workers=1`；
- r13 zero-network preflight：state SHA-256
  `2ea7331d352cda4d00e2c9c0e305e7489e477c26a2e9714a489ffd2060cd2fba`，campaign digest
  `36700ea5b5ab8c1eb781de9f319913c7fc9b127c11f8076dd88c3c9b0d2e1df0`，
  `status=preflight_ready`、`network_calls_performed=false`、
  `target_suite_calls_performed=false`、9/9 operational profiles ready。

r13 仍遵循 `2% transport fail-fast`、最低 `3 canonical models`、完整 16-unit 分母和
同 cohort ranking/freeze/import/audit 约束；target gate 继续关闭。

### r13 live screening 启动里程碑（2026-08-19 17:41 CST）

r13 唯一 live non-target screening 已通过 `setsid/nohup` 启动，screening PID 为
`566502`，supervisor PID 为 `567189`，watcher PID 为 `567994`；三者命令行均绑定
`baseline_screening_plan.r13.private.json`，未重复启动其他 screening。首个
`livebench_official_final_text_slice` checkpoint task 为
`27fed11add78ea40a3dd7bba83f11272bb8a77bf6b48f514b563705dd3a27395`，已完成 `11/102`
case，checkpoint 状态为 `partial`。live campaign state 尚未完成首个 unit，target gate
仍由 supervisor/watcher 关闭；不修改 frozen plan、不重试 case、不启动 target benchmark。

### r13 screening 进度快照（2026-08-19 17:53 CST）

r13 首个 `livebench_official_final_text_slice` unit 已自然终态失败：task
`27fed11add78ea40a3dd7bba83f11272bb8a77bf6b48f514b563705dd3a27395` 完成完整 `102/102`
case，transport failure rate 为 `0.676470588235`，按冻结 `2%` fail-fast gate 拒绝。
campaign state 当前为 `status=running`、`completed_unit_count=0`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，state 文件 SHA-256 为
`99a039c53ad97b7a4f33758dfd686420e8a806d39cb431a251d77bbf54b01835`，campaign digest 为
`64c9115a5cd0042cb23e2062f90e1b1cb7852601160acc3fb6d8d6d856d84ff6`。第二个 task
`d7e62dcf7e03031924cdba38ac78d78e5fd094d031e378c4fbeacae7eb383ecf` 已创建 `0/102`
checkpoint；`retry_round_count=0`，不修改 frozen plan、不拼接 completed subset。

### r13 screening 进度快照（2026-08-19 18:50 CST）

r13 已推进至 `0 completed / 3 failed`，campaign 仍为 `status=running`、
`planned_task_count=16`、`ready_for_ranking=false`。前三个 terminal unit 的 transport
failure rate 分别为 `0.676470588235`（102 case）、`1.0`（112 case）和
`0.333333333333`（102 case），均由冻结 `2%` fail-fast gate 拒绝；其中后两个记录
`screening_unit_no_scores`。state 文件 SHA-256 为
`fcb9c806830a59a6a8c11805abf7d9c327490c7db8c0f56a544071a3a611d78a`，campaign digest 已更新为
`9bcb44be4d442a34dffed1066f2a3657c244aaa53e2287f8e7c9dcd3a33c8ae2`。第四个 task
`e2314df494955a51d8254373eece6ccc4aa518a22f615be36ffac399b8ccfa9e`（`mmlu-pro`）当前
checkpoint 为 `87/112`，已完成 case 暂未出现 transport failure；所有 unit
`retry_round_count=0`，不修改 plan、不拼接 completed subset。supervisor 与 watcher
仍保持 `next_gate=screening`、`target_suite_calls_allowed=false`。

### r13 screening 进度快照（2026-08-19 18:59 CST）

第四个 `mmlu-pro` unit `e2314df494955a51d8254373eece6ccc4aa518a22f615be36ffac399b8ccfa9e`
已自然终态并完成 `112/112` case，`scored_case_count=112`、transport failure
`0/112`、mean score `0.785714285714`、p95 latency `48656.944ms`，reason codes 为空。
campaign 当前为 `status=running`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`；state 文件 SHA-256 为
`5fdb98d099336d6e45f7e55b6c61d0c9e630efc4c099c946f3d77ec7a9334165`，campaign digest 为
`e0055ba70ba099913433bf9b87289cad65c3f423663e74621c0a5c1548155fdd`。运行器已自动进入
第五个 task `d18c4a89ea4965086cd4c567b86bb24fafb013c5c1b1cb289e7a1d01869172d8`，checkpoint
为 `1/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 19:28 CST）

第五个 task `d18c4a89ea4965086cd4c567b86bb24fafb013c5c1b1cb289e7a1d01869172d8`
已自然终态并完整完成 `102/102` case，`scored_case_count=102`、transport failure
`0/102`、mean score `0.71568627451`、p95 latency `44492.815ms`，reason codes 为空。
campaign 当前为 `status=running`、`completed_unit_count=2`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`；state 文件 SHA-256 为
`a2d3f296ebca5cbdfc810dec965453142fc89da7b0f93fd52e23f6096124f71e`，campaign digest 为
`7c74f960c37434dcb8d6cc5f74e5961fc358eafa37ca604018f5566c6e8168fc`。运行器已自动进入
第六个 task `5f2f5361b9f6d92cdf4ab790d5c7a3c262906180ae298cd325b04c0966d79d49`，checkpoint
为 `0/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 19:36 CST）

第六个 task `5f2f5361b9f6d92cdf4ab790d5c7a3c262906180ae298cd325b04c0966d79d49` 已自然
终态失败：完成 `19/112` case，`scored_case_count=19`、transport failure `93/112`、
failure rate `0.830357142857`，触发冻结 `2%` fail-fast gate，未尝试 case `90`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=2`、`failed_or_blocked_unit_count=4`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`35d350c68aee93a22b1d515e03e9bb3c718f95cde6b4029fa822b2f0c4fa5b53`，campaign digest 为
`ceec8c01f4d5378c63b7bf1c8f4cc771d41648d63773fcc9b188afeb31cd4f38`。运行器已自动进入
第七个 task `e454627f2fc43c1ca1fbd8a277e9eaceed72122beb138f3a13501b5dc492dfb1`，checkpoint
为 `4/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 19:55 CST）

第七个 task `e454627f2fc43c1ca1fbd8a277e9eaceed72122beb138f3a13501b5dc492dfb1` 已自然
终态完成 `102/102` case，`scored_case_count=101`、transport failure `1/102`、failure
rate `0.009803921569`，低于冻结 `2%` gate，未触发 fail-fast，reason codes 为空；mean
score 为 `0.792079207921`，p95 latency 为 `21217.921ms`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=4`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`66002ac4f8738bc45540a12f8f4e36e73e598d32f7bcdd3df22666850580bd24`，campaign digest 为
`f7ae7602d28aef92ec652667983b2abc95590d072169b1afe53e53fa9828c51b`。运行器已自动进入
第八个 task `de836731b675337719ab0b8d539264fbcf753a685f54cbe4680ebd3235fe6c0d`，checkpoint
为 `16/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 20:16 CST）

第八个 task `de836731b675337719ab0b8d539264fbcf753a685f54cbe4680ebd3235fe6c0d` 已自然
终态失败：完成 `95/112` case，`scored_case_count=95`、transport failure `17/112`、
failure rate `0.151785714286`，触发冻结 `2%` fail-fast gate，未尝试 case `14`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`400f0222c1b2d0b6f97d3a6c2c27d9b5f04a5a924c4eb92f1e23a613e5fc4329`，campaign digest 为
`d73e800cf7d35b28b52966635a9edc0826d6c97c8f59ed4b0966e3b3b9b7d40a`。运行器已自动进入
第九个 task `7a79b67ec4705c8a65079c56d0f5c7c103df5674573f8120f9a406fe44865b69`，checkpoint
为 `5/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 20:19 CST）

第九个 task `7a79b67ec4705c8a65079c56d0f5c7c103df5674573f8120f9a406fe44865b69` 已自然
终态失败：完成 `17/102` case，`scored_case_count=17`、transport failure `85/102`、
failure rate `0.833333333333`，触发冻结 `2%` fail-fast gate，未尝试 case `82`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=6`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`9ebf1f6b62fcc2e0336353ffd2cfabc8afa1b58c42dcdee440ae5897e5160c5e`，campaign digest 为
`146f1638961548894c6495ae67ae1f5c9bba7e0daa176f322c7a28971458690b`。运行器已自动进入
第十个 task `f3dc7761386b6884797bf1c35717312f38664954d717b8e7c4f6b35018af6e74`，checkpoint
为 `11/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 20:26 CST）

第十个 task `f3dc7761386b6884797bf1c35717312f38664954d717b8e7c4f6b35018af6e74` 已自然
终态失败：完成 `46/112` case，`scored_case_count=46`、transport failure `66/112`、
failure rate `0.589285714286`，触发冻结 `2%` fail-fast gate，未尝试 case `63`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=7`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`a1cb6e99c0149e75467a1999b13dfa80e0925c63c38fcc8b5eecd3317285d906`，campaign digest 为
`0d41f1c1c80115eaf72dc75458460f5de4f1da1fd87e12a7b868e43e9d272281`。运行器已自动进入
第十一个 task `5f9fade1c7264f69ddf84df791ffcb14e68583cfae09e587188b226460a767f8`，checkpoint
为 `4/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 20:32 CST）

第十一个 task `5f9fade1c7264f69ddf84df791ffcb14e68583cfae09e587188b226460a767f8` 已自然
终态失败：完成 `20/102` case，`scored_case_count=20`、transport failure `82/102`、
failure rate `0.803921568627`，触发冻结 `2%` fail-fast gate，未尝试 case `79`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`b7645cc24a656413d0b9308bba647cce02f633974212b46b0271d60c62667686`，campaign digest 为
`f901510ca3a6dda7ca28bdbb06aff32b48e0747da9a752dbc143f1465bed077a`。运行器已自动进入
第十二个 task `bdbd40764ece9402d2752a6d981ce7020c7857460e321b5f270c16bc7b99856c`，checkpoint
为 `8/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 21:17 CST）

第十二个 task `bdbd40764ece9402d2752a6d981ce7020c7857460e321b5f270c16bc7b99856c` 已自然
终态完成 `112/112` case，`scored_case_count=112`、transport failure `0/112`、mean
score `0.767857142857`、p95 latency `51575.264ms`，reason codes 为空。campaign 当前为
`status=running`、`completed_unit_count=4`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`c87bfcdd8f758ccb56ce80a2db04ba019051a2eb41297ea9404ff9e73f36ccfc`，campaign digest 为
`cb3be7eebf821474fce222f07313d4cd2aaa8100c324fb8ed409df0a5eb6b8d2`。运行器已自动进入
第十三个 task `eed40af9b25c169eb5ff7b7de83943be78ab5b14d9791308614fecaf2b8854f3`，checkpoint
为 `2/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 21:54 CST）

第十三个 task `eed40af9b25c169eb5ff7b7de83943be78ab5b14d9791308614fecaf2b8854f3` 已自然
终态完成 `102/102` case，`scored_case_count=102`、transport failure `0/102`、mean
score `0.686274509804`、p95 latency `56237.749ms`，reason codes 为空。campaign 当前为
`status=running`、`completed_unit_count=5`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`67345d30ea83ec80fe5d6dc11bd14c36d0fe43bd06d544c310e9536e9f114acf`，campaign digest 为
`1fda9f13aeb4ae2de310a7d2dab2c67427a726eaff522888a2b9eb4a90d07dd8`。运行器已自动进入
第十四个 task `011b349563db08a3004d4a1411c92a5b4275c46cfddaea18e395701dc5bace3f`，checkpoint
为 `6/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 22:17 CST）

第十四个 task `011b349563db08a3004d4a1411c92a5b4275c46cfddaea18e395701dc5bace3f` 已自然
终态完成 `112/112` case，`scored_case_count=111`、transport failure `1/112`、failure
rate `0.008928571429`，低于冻结 `2%` gate，未触发 fail-fast，reason codes 为空；mean
score 为 `0.801801801802`，p95 latency 为 `38835.769ms`。campaign 当前为
`status=running`、`completed_unit_count=6`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`12f5b6052562dfb4ae0571ef73552b013732a33ab82a878cfb86d9d1475ef1c2`，campaign digest 为
`b2adf744008f0673ccf75fdfc800b580bae25c69ad11284b866d3dd66972ba01`。运行器已自动进入
第十五个 task `68ae177700c0a95d14cdd103ff8ab4f1116fa6b8116addc4ab3cec529dc6e4ec`，checkpoint
为 `1/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 进度快照（2026-08-19 22:21 CST）

第十五个 task `68ae177700c0a95d14cdd103ff8ab4f1116fa6b8116addc4ab3cec529dc6e4ec` 已自然
终态失败：完成 `0/102` case，`scored_case_count=0`、transport failure `102/102`、
failure rate `1.0`，触发冻结 `2%` fail-fast gate，未尝试 case `99`，reason codes 为
`screening_unit_no_scores` 与 `screening_unit_transport_failure_rate_exceeded`。campaign
当前为 `status=running`、`completed_unit_count=6`、`failed_or_blocked_unit_count=9`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`0ad89e898baae0eb410fc1766e3d45e0e66f5267535b4fb25865563aa32540ba`，campaign digest 为
`293f704f651f84b73b4df7fea4c16ecff3f3f7c7a26fc88d2daa00a8318601a2`。运行器已自动进入
最后第十六个 task `ee6379a028056fea4cb5291381b7b9989a36664769598152b18b7a399c022101`，checkpoint
为 `6/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

### r13 screening 终态（2026-08-19 23:00 CST）

r13 的最后第十六个 `mmlu-pro` unit 已自然终态完成完整 `112/112` case：
`scored_case_count=111`、transport failure `1/112`、failure rate
`0.008928571429`，低于冻结的 `2%` gate，`fail_fast_triggered=false`，reason codes 为空；
unit mean score 为 `0.810810810811`，p50/p95 latency 为 `19945.019ms/36101.205ms`。
完整 campaign 当前为 `status=partial`、`planned_task_count=16`、
`completed_unit_count=7`、`failed_or_blocked_unit_count=9`、`ready_for_ranking=false`。
最终 state 文件 SHA-256 为
`81c327fb5c43efc93b9531b12434f98a5244c4b5ead45fbbf8c5edf0a389a256`，screening receipt
SHA-256 为 `031cd6b43206e24e0e778078f9918094eccd00670ce30591176ace3366b91563`，campaign
digest 为 `5dc080cbefa0de102256058a1ae12dc28cb8b0c53a4d5362f6afe7cb1522fe22`。16/16
unit 的完整失败分母已经封存；不恢复 checkpoint、不重试 case、不拼接 completed subset，
不降低 transport gate。screening 主进程已退出，现有 supervisor/watcher 只等待其
低频终态审计；transport admission、ranking、provider freeze、official import、cohort
binding 与 target campaign 均尚未 ready，`target_suite_calls_performed=false`。

### r13 transport admission 终态（2026-08-19 23:08 CST）

既有 supervisor 在 screening terminal 后按冻结顺序完成 transport-only admission，未执行
target 或 ranking 请求。transport receipt SHA-256 为
`35db945c7b9aefdf08f627d5ebc32bda309c3609c0b3be5e81966b5cbdbe62d8`，supervisor receipt
SHA-256 为 `b9dd703b2fe235fce3e1fd02833c8e64dcc9cc13abbb09c7c11dd046c2768a95`；两者均绑定
r13 plan digest `899f3cb3f7539ec0789458f21a85be7357042e0cb7275a171ba16ea40d030f97`、campaign
digest `5dc080cbefa0de102256058a1ae12dc28cb8b0c53a4d5362f6afe7cb1522fe22` 和最终 state
SHA-256 `81c327fb5c43efc93b9531b12434f98a5244c4b5ead45fbbf8c5edf0a389a256`。
admission 状态为 `blocked`：8 个 candidate canonical 中仅 2 个在两独立 source family
都通过 `2%` transport failure gate，低于预注册的 `3` 模型最低门槛；唯一 blocker 为
`transport_admission_fewer_than_minimum_models`。receipt 明确记录
`selection_basis=transport_failure_rate_only`、`quality_fields_used_for_selection=[]`，
没有使用分数、标签或 provider output。ranking 文件未生成，provider baseline freeze、
official import、cohort binding 与 target campaign 继续关闭；r13 全部证据转为
reference-only，下一次推进必须创建新的 immutable successor（例如 r14），不得恢复或拼接
r13 survivor subset。

### r12 live screening 启动里程碑（2026-08-19 13:33 CST）

r12 唯一 live non-target screening 已通过 `setsid/nohup` 启动，supervisor 与 lineage
watcher 均绑定同一个 immutable r12 plan；当前不重复启动、不恢复 r11 checkpoint，且
target gate 仍关闭。现场进程为 screening `4178760`、supervisor `4181633`、watcher
`4182263`；state `status=running`、`planned_task_count=16`、`completed_unit_count=0`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，state SHA-256 为
`562d7385b87159eacf82ce95977be74983beb27126e986cf134182a5f5dd25a2`，并确认
`network_calls_performed=true`、`target_suite_calls_performed=false`。screening receipt、
transport admission 与 ranking 产物尚未出现；下一检查只做低频只读状态审计。

### r12 screening 进度快照（2026-08-19 14:45 CST）

r12 仍处于 screening gate：`status=running`、`planned_task_count=16`、
`completed_unit_count=0`、`failed_or_blocked_unit_count=4`、`ready_for_ranking=false`。
当前 state SHA-256 为
`72b7c3877c717f37f4fa2eebb86138dbc45bde467cf7ffd8b37a8f4aa746afd8`。四个已终态
unit 均按冻结的 2% transport failure-rate gate 失败，失败率约为 5.88%、100%、
11.61%、43.14%，其中一项额外记录 `screening_unit_no_scores`；不调低阈值、不拼接
completed subset。运行器已进入第五个 `mmlu-pro` unit，checkpoint task 为
`b9d5456f3d18ba9a4f38888d732c7738c096a4908f1d392d2225f479cd2ab55a`，当前 `1/112`
case；target gate 仍由 supervisor/watcher 关闭。

### r12 screening 进度快照（2026-08-19 15:13 CST）

第五个 unit 已自然终态失败，当前 state 为 `status=running`、`planned_task_count=16`、
`completed_unit_count=0`、`failed_or_blocked_unit_count=5`、`ready_for_ranking=false`，
state SHA-256 为
`bab7cf7c9b54875b24267c213e0eb87794d518649484db39a216a58c3bd25dbb`。该 unit 的
transport failure rate 约 91.07%，仍按冻结的 2% gate 拒绝。第六个
`livebench_official_final_text_slice` unit checkpoint task 为
`850a79a30e584d817705b7d2fdd06b13411ad129324f81255a72fd119f2a405b`，已完成 `77/102`
case。screening terminal 前不生成 ranking/freeze/import，也不打开 target gate。

### r12 screening 进度快照（2026-08-19 15:26 CST）

第六个 `livebench_official_final_text_slice` unit 已完成。当前 state 为
`status=running`、`planned_task_count=16`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=5`、`ready_for_ranking=false`，state SHA-256 为
`35134f156870a55d1633f16fc019feaacd9879e1454100b4a88551ef101424b7`。第七个
`mmlu-pro` unit checkpoint task 为
`eec4029d3c14e766c4365f35615bbe38a5760bfc657747808319989a99712cad`，已完成 `37/112`
case。screening terminal 前仍不生成 transport/ranking/freeze/import，也不打开 target
gate。

### r12 screening 进度快照（2026-08-19 15:53 CST）

第七个 `mmlu-pro` unit 已完成。当前 state 为 `status=running`、
`planned_task_count=16`、`completed_unit_count=2`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`，state SHA-256 为
`625b8f84a8d4aeaaaaae0917d071156483cddced03cc2920ae55b235437dd8d3`。第八个
`livebench_official_final_text_slice` unit checkpoint task 为
`bd32f49dbc4f9a0af85985b77f8f26901ad2fa7a9c2136faf10e360063200e61`，已完成 `73/102`
case。screening terminal 前继续关闭 transport/ranking/freeze/import 以及 target gate。

### r12 screening 进度快照（2026-08-19 15:57 CST）

第八个 `livebench_official_final_text_slice` unit 已完成。当前 state 为
`status=running`、`planned_task_count=16`、`completed_unit_count=3`、
`failed_or_blocked_unit_count=5`、`ready_for_ranking=false`，state SHA-256 为
`4b213bb95f4b7a20745e78ee2b1bff5d968df84079b64768c71ffaccb611df8c`。第九个
`mmlu-pro` unit checkpoint task 为
`6f9c3ef80bae3b96e237bbc66d7cbff05573bdc1c3c79bf2439486d79a0a3975`，当前 `5/112`
case。screening terminal 前继续关闭 transport/ranking/freeze/import 与 target gate。

### r12 失败 telemetry 中间审计（2026-08-19 16:00 CST）

五个失败 unit 均由冻结 2% gate 的 fail-fast 触发，失败分母包含真实 transport 事件和
未尝试 case，不能把两者混同。已观测到的真实信号为 HTTP 500/503、timeout 与空输出；
直接故障后分别有 3、109、10、99、41 个未尝试 case，p95 分别约为 20.14、23.24、
51.74、90.08、80.69 秒。当前计划各失败 unit 的 `retry_round_count=0`，不在 r12 内
修改 retry 或阈值；只在完整 terminal/ranking 审计后决定是否需要新的 successor policy。

### r12 screening 进度快照（2026-08-19 17:04 CST）

r12 当前已写入 13 个 unit artifact，累计 `6 completed / 7 failed`，但 state 仍为
`status=running`，完整 16-unit terminal gate 尚未满足。state SHA-256 为
`1efbaf99b9902f1ae371ef97a3951e82dc1b894ef8f4e6d172ee8eba603c4462`，campaign digest 为
`1914db0beca1c7f15dd58f5edd24995c6bfff777573b28a3273c693f5e01f5cf`，
`ready_for_ranking=false`、`target_suite_calls_performed=false`。第十三个 `mmlu-pro`
unit 已按冻结 2% gate 失败（transport failure rate 87.5%）；第十四个
`livebench_official_final_text_slice` unit active checkpoint task 为
`646a38b21932ed4fa5e68bf85d6a78299be5528c62b0c444b4d859ebbb368177`，当前 `6/102`
case；screening terminal 前继续关闭 transport/ranking/freeze/import 与 target gate。

### r12 screening terminal 快照（2026-08-19 17:24 CST）

r12 已完成完整 `16/16` 个 unit，campaign 进入 `status=partial`，累计
`6 completed / 10 failed`，`ready_for_ranking=false`。state 文件 SHA-256 为
`fc5d5201e14f1dd2d4cb2c06c997cbc410c2bcb023459cb2cd7192115125443b`，campaign digest
为 `c78f4eb5ade227d959c2a035c772aa0a4a25bbbc049723e8329f326e2feeef77`；
`network_calls_performed=true`、`target_suite_calls_performed=false`。第十四个
`livebench_official_final_text_slice` unit 的 transport failure rate 为 10.78%，
第十五和第十六个 `mmlu-pro` unit 均因无有效输出触发冻结 2% gate。screening receipt
已生成，transport admission、ranking 和 provider freeze 尚未生成；supervisor/watcher
正在等待 terminal state 后处理离线门禁，target gate 继续关闭。

### r12 terminal / conversion 审计（2026-08-19 17:30 CST）

r12 已自然终态并完成全部 `16/16` unit：`6 completed / 10 failed`，campaign 为
`partial`，`ready_for_ranking=false`。screening state 文件 SHA-256 为
`fc5d5201e14f1dd2d4cb2c06c997cbc410c2bcb023459cb2cd7192115125443b`，campaign digest 为
`c78f4eb5ade227d959c2a035c772aa0a4a25bbbc049723e8329f326e2feeef77`。

同 cohort supervisor 已完成离线转换：transport admission 为 `ready`，候选池 8 个
canonical model 中有 3 个通过固定 2% failure-rate gate，完整 16-unit 分母和 2 个
source family 均已绑定；`selection_basis=transport_failure_rate_only`、
`quality_fields_used_for_selection=[]`。transport receipt SHA-256 为
`6a397f1d34feaed413d4bfd0b3499a2381e8410331f8bb24fc259fe69d0b1556`。

complete-pool ranking 明确 `screening_conversion_ready=false`，没有产生任何有效 rank；
blockers 包括 campaign incomplete、source/unit coverage incomplete、
`screening_ranking_current_inputs_mismatch` 和 candidate pool mismatch。ranking receipt
SHA-256 为 `c03c3fbe0f628fae7ab132799e53a3f543ddb0f78255758316998b9fcdb3e91b`，supervisor
receipt 为 `blocked`（SHA-256 `812d00ad91d1f0266a9f46307b8537fec6544b638c1acb98db7580577b2f58a9`）。
lineage watcher 的同 cohort binding/audit 均为 `blocked`，`next_gate=screening`、
`target_suite_calls_allowed=false`、`final_claim_allowed=false`；没有 provider freeze、
official import 或 target 请求。r12 全部证据封存为 reference-only，不恢复或拼接
completed subset，下一步创建新的 immutable r13 source successor。

### r12 screening 进度快照（2026-08-19 16:13 CST）

第九个 `mmlu-pro` unit 已完成。当前 state 为 `status=running`、
`planned_task_count=16`、`completed_unit_count=4`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`，state SHA-256 为
`7f2ceefb3c18ea84bec9903b8067fc18250269374f086a02b9006a5bc9f26889`，campaign digest
为 `eceab7307f81a388bc3e7fc027eec9443d03c72dbe28162e7300705efca2f453`。第十个
`livebench_official_final_text_slice` unit checkpoint task 为
`0e9f42b79f925ff407f376defcc6f63df5812f71e25c27fc1778a42fd2cccc6d`，当前 `4/102`
case。screening terminal 前继续关闭 transport/ranking/freeze/import 与 target gate。

## Composite cohort r10 终态与 r11 successor（2026-08-19）

r10 已自然终态：16/16 unit terminal、13 completed、3 failed，campaign 为 `partial`。
transport-only admission 通过（6/8 canonical eligible，严格使用
`transport_failure_rate_only`），但 complete-pool ranking 被不完整 unit/source coverage
门禁拒绝；因此 r10 不产生 ranking、provider freeze、official import 或 target 授权。详细
digest 与失败分母见
`docs/operations/composite_r10_screening_terminal_2026-08-19.md`。

当前主线已切换为全新的 immutable r11 successor：仅改变 source manifest 的 selection
seed 和 registration date，不恢复或拼接 r10 checkpoint/completed subset，也不复用 r10
transport/ranking/binding。固定顺序为：

```text
r11 source successor -> frozen screening plan -> zero-network preflight
-> live non-target screening -> transport admission -> complete-pool ranking
-> provider baseline freeze -> same-cohort official import -> convergence audit
-> 21-suite target campaign
```

在 r11 convergence audit 返回 `ready_for_target_campaign` 前，target calls、provider
baseline freeze、official import 和 superiority claim 均保持关闭。

r11 intake 已完成：source successor、frozen plan 和 zero-network preflight 均 ready；
Harness 控制面已按同一 r11 output path 重新生成，复用的只是已验证 6/6 hash-only pin，
没有复制原始 checkout、数据、答案或旧 cohort 结果。当前 r11 scaffold 为
`status=blocked`、`next_gate=screening`，等待唯一 live non-target screening 启动；详细
证据见 `docs/operations/composite_r11_successor_intake_2026-08-19.md`。

## Composite cohort r10 当前主线（2026-08-18）

### 2026-08-19 00:16 现场快照

r10 live screening 仍在唯一主线的 screening gate：`status=running`、
`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、
`ready_for_ranking=false`、`target_suite_calls_performed=false`。活动 unit 的
checkpoint 已推进至 `71/112`，当前已完成 case 未出现 transport failure；三个后台
进程仍存活且命令行绑定 frozen r10 plan。该快照只记录进度，不改变 plan、checkpoint、
失败分母或任何后置 artifact。

00:23（CST）复核时活动 checkpoint 已推进至 `84/112`，仍为 screening gate，未生成
transport admission、ranking 或 target 证据；本次只追加进度记录，不改变任何冻结输入。

00:29（CST）复核时活动 checkpoint 已推进至 `94/112`，仍未发现 transport failure；
screening 尚未 terminal，后置转换继续由既有 supervisor 门禁控制。

00:32（CST）复核时活动 checkpoint 已推进至 `100/112`，仍为 screening gate，未生成
transport admission、ranking 或 target 证据。

00:39（CST）原活动 `mmlu-pro` unit 已完成 `112/112` 且 0 transport failure，state 更新
为 `completed_unit_count=3/16`；运行器已进入下一 102-case unit，screening 仍未 terminal。

### 已冻结的 route

r8 与 r9 均已封存为只读证据，不能进入 ranking；r9 的 16 个 unit 已全部 terminal，
3 个 completed、13 个 failed，transport admission 仅保留 1 个 canonical model，低于
固定 3-model gate。r9 的 plan、checkpoint、completed subset、transport、ranking 槽位
和 Harness binding 均不得复用。当前唯一主线是新的 r10 immutable successor：

```text
r10 source successor -> frozen screening plan -> zero-network preflight
-> live non-target screening -> transport admission -> complete-pool ranking
-> provider baseline freeze -> official Harness import -> convergence audit
-> target campaign
```

r10 必须重新绑定当前 probe-bound registry、r7 operational admission 和新的 selection
seed，保留两套独立 source family、`max_workers=1`、fail-fast transport gate 和完整
失败分母。r9 的 plan digest 为
`9ad83ca335d1e3eaf15f28d1c8c842a5249a5e6a996b3d68156411af905a1399`，不能作为 r10
输入；r9 终态与 successor 决策见
`docs/operations/composite_r9_screening_terminal_2026-08-18.md`。

r10 Harness 控制面已独立物化：6/6 pin ready、BFCL V3 marker 通过，official execution
plan 为 `ready_to_execute`；acquisition/import audit、cohort binding 和 convergence
audit 仍按 screening/freeze/import 门禁保持 blocked，scaffold 的
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`、
`provider_calls_performed=false`。本阶段使用已验证的 r7 21-suite dataset/source/case
manifest 作为不可变基础输入，但不复用任何 r9 binding 或质量结果。详细证据见
`docs/operations/composite_r10_harness_successor_2026-08-18.md`。

r10 live screening 已由 `setsid` 启动：screening PID `2281133`，supervisor PID
`2283494`，lineage watcher 当前 PID `2365523`（旧 watcher 在审计修复后退出）。三者均
绑定 r10 plan；已有三个 serial unit 终态（112/112 且 0 transport failure；102/102
且 1 transport failure并完成；102/102 且 102 transport failure并失败，reason 为
`screening_unit_no_scores` 与 `screening_unit_transport_failure_rate_exceeded`）。
截至 2026-08-18 23:50（CST），campaign state 仍为 `running`、
`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`；第四个 unit 的活动
checkpoint 已推进至 26/112。当前仍处于 screening gate，不能转换
transport/ranking/freeze/import 或 target。启动与监控记录见
`docs/operations/composite_r10_screening_live_2026-08-18.md`。

### 当前执行与 Harness gate

r9 live screening（PID `1772237`）已自然退出；同 cohort supervisor 和 lineage watcher
已完成 terminal transport/audit 后退出。r10 启动前不恢复 r9 进程、不修改 r9 frozen
plan、不启动 target。

r9 独立 Harness 控制面已物化：6/6 pin ready、BFCL V3 marker 通过、official
execution plan ready；最终 convergence audit 为 `status=blocked`、`next_gate=screening`，
`target_suite_calls_allowed=false`。r10 必须重新生成同 cohort 的 Harness binding，不能
跨 cohort 复用 r9 binding。

正式 18900 serving 已从历史 noprefusion 进程切换为显式 r7 probe-bound pre-Fusion
registry：当前 `scripts/run_server.py` PID 为 `1950874`，health 200/ready，21
profiles、4 providers，network `auto`/`proxy`；标准入口
`private/serving_registry.json` 也已原子指向同一 r7 artifact，四种 API route-plan
dry-run 与三档模型角色分配已复核。该切换只影响本地 Fusion 网关，不停止 CPA Plus
正式服务，也不改变 r9 screening 的 registry/plan 输入。

### 路由与验证规则

screening 必须完整 terminal 且 `ready_for_ranking=true` 才能转换 ranking；transport
receipt 必须满足固定至少 3 个 canonical models，ranking 必须覆盖完整候选分母和
独立 source families。provider freeze 还必须绑定当前 registry、probe evidence、
transport receipt 和 operator-owned external top-three，不能用 prior、latency 或
target score 填充。只有 convergence audit 明确返回 `ready_for_target_campaign`，
才执行 21-suite official/audited Harness campaign，并分别比较 axio-fast/terra/pro
与 rank 3/2/1 单模型 baseline。

### 接续决策

- r9 已终态 blocked/partial：保留完整失败分母，生成 r10 source successor，不恢复 r9
  或拼接 completed subset；
- ranking ready 但 freeze/import 不完整：继续当前 successor cohort 离线修复 binding，
  仍不发送 target 请求；
- convergence audit ready：才进入正式 target campaign、四种 API parity、paired
  statistical/latency/contamination audit 和最终 completion audit。

详细 hash、Harness stage 和运行路径见
`docs/operations/composite_r10_harness_successor_2026-08-18.md`；r9 控制面历史记录仍见
`docs/operations/composite_r9_harness_successor_2026-08-18.md`。

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
解析，且从 r3 实际 screening source digest 重建的显式 MMLU-Pro replacement 使 target
case-hash/source manifest validation 达到 21/21 ready。官方 import audit 已确认
case-hash binding 6/6，但 imported runs 为 0，仍等待 provider baseline freeze 后的正式
Harness 执行。GPQA 原始槽位仍明确标记为 replacement，不用历史分数或 completed subset
填充。

### r3 screening 终态与 transport 门禁（2026-08-17）

r3 frozen plan 已完整执行并自然终态：8 个 serial units 中 1 个 completed、7 个
transport-blocked，state 为 `partial`，`ready_for_ranking=false`，
`target_suite_calls_performed=false`。同 cohort supervisor 随后运行 transport-only
admission，安全 receipt 为 `status=blocked`，reason 为固定最低 canonical model 数不足。
因此没有生成 external ranking、provider baseline freeze 或任何 target-suite 请求；
convergence audit 仍保持 `target_suite_calls_allowed=false`。完整分母、失败分类、
plan/campaign digest 和 hash-only receipts 保留在 r3 private root，不将 completed
subset 选为 survivor，也不把该结果写成能力排名或 superiority evidence。终态记录见
`docs/operations/composite_r3_screening_terminal_2026-08-17.md`。

下一步只允许创建新的 successor cohort：保留 r3 只读证据，重新生成 immutable
screening plan，并重新跑完整 source/candidate 分母。不得修改 r3 plan、恢复 r3
checkpoint、复用 r3 completed subset、复用历史 ranking/freeze，或降低 3-model
transport gate；Harness pin、目标 case-hash 和 replacement 槽位可以继续作为离线
控制面输入，但在 successor 的 transport/ranking/freeze 未 ready 前仍禁止 target
calls。

### r4 screening 终态与 transport 门禁（2026-08-17）

r4 successor 已完整终态：8 个 serial units 中 3 个 completed、5 个
failed/blocked，state 为 `partial`，`ready_for_ranking=false`，且
`target_suite_calls_performed=false`。transport-only admission 绑定同一 campaign、
plan、registry、source manifest 和 state digest，4 个候选 canonical models 中只有
1 个通过严格 failure-rate 门禁，低于固定最低 3 个，因此 receipt 为
`status=blocked`、reason 为 `transport_admission_fewer_than_minimum_models`。

supervisor 没有执行 ranking conversion；external ranking、provider baseline freeze
和 target campaign 均未开启。watcher 最终 audit 为 `status=blocked`、
`target_suite_calls_allowed=false`、`final_claim_allowed=false`。r4 的完整分母、
失败分类、digest 和 hash-only receipts 记录于
`docs/operations/composite_r4_screening_terminal_2026-08-17.md`；不得将 completed
subset 当作 survivor、能力排名或 superiority evidence。下一步必须创建新的
immutable successor，重新建立至少 3 个 formal transport-eligible canonical models，
并保留 r4 全部证据。

### r5 successor operational admission 终态（2026-08-17）

r5 intake 对同一 probe-bound registry 执行了独立、非 benchmark 的 live
`operational-admission`，10 个候选中只有 2 个 production admitted、1 个 formal
baseline eligible；固定最低要求为 3 个。receipt 虽为 `status=ready`，但候选分母
不足以创建 screening plan，因此没有启动新的 screening、ranking、provider freeze
或 target Harness。完整 hash-only 记录见
`docs/operations/composite_r5_admission_terminal_2026-08-17.md`。

该结果是当前供应商 transport 可用性证据，不是质量排名。下一步必须扩展或刷新
候选分母并重新执行独立 admission；不得降低 3-model gate、复用 r4/r5 completed
subset、复用历史 ranking/freeze，或在 gate 前发起 target calls。

### r6 screening 终态与 Harness 收敛（2026-08-17）

r6 使用独立 operational admission 生成的完整候选分母已自然终态：8 个 serial
units 全部 terminal，3 个 completed、5 个 failed/blocked，state 为 `partial`。
transport-only admission 只留下 1 个 eligible canonical model（候选 4 个，固定最低
3 个），因此 receipt 为 `status=blocked`、reason 为
`transport_admission_fewer_than_minimum_models`。r6 的完整分母、digest、supervisor
和 Harness audit 记录见
`docs/operations/composite_r6_screening_terminal_2026-08-17.md`。

supervisor 没有执行 ranking conversion，watcher 已完成最终原子 binding/audit 后
退出；`target_suite_calls_performed=false`、`target_suite_calls_allowed=false`、
`final_claim_allowed=false`。Harness 离线 pin/execution plan readiness 不得被解释
为 target readiness，也不能用 operational admission 或 completed subset 补齐
transport gate。

下一步只允许基于新的 bounded transport health check 和新的 probe-bound candidate
registry 创建 immutable r7 successor。r6 plan、checkpoint、completed subset、ranking
和 freeze 全部只读；新的 r7 必须重新保留完整 source/candidate 分母、使用新的
selection seed，并继续使用 `max_workers=1`、fail-fast transport gate 和固定至少 3
个 formal transport-eligible canonical models 的门槛。在 successor 的 transport、
external ranking、provider baseline freeze、official Harness import 和 lineage
convergence 全部 ready 前，target calls 与 superiority claim 保持关闭。

### r7 successor intake 架构（2026-08-17）

r7 不直接重跑 r6，而是采用 fresh enrollment → operational admission → immutable
screening successor → Harness lineage 的四段单向控制面。fresh enrollment 重新验证当前
provider `/models`、协议和严格流式 transport，operational admission 使用固定 90 秒
non-target workloads 确认当前可用性；只有至少 3 个 formal baseline eligible canonical
models 才能注册新的 source manifest、screening plan 和 zero-network preflight。
具体设计与失败边界见
`docs/operations/composite_r7_successor_intake_2026-08-17.md`。

r7 仍禁止复用 r6 plan、checkpoint、completed subset、ranking/freeze 或 target 输出，
继续固定 `max_workers=1`、fail-fast transport gate 和至少 3-model minimum。所有 Harness
pin、execution、acquisition/import、cohort binding 和 convergence receipt 必须绑定 r7
registry/plan/state digest；audit 明确返回 `ready_for_target_campaign` 前不得发起
target calls 或 superiority claim。

r7 fresh enrollment 首轮已完成但未通过正式 pre-Fusion diagnostic：6 个严格流式可用
profile 均来自 Anthropic 协议投影，缺少 fast candidate 和完整 catalog/role binding，
因此不作为 screening 输入。下一步只允许用 focus manifest 刷新 NVIDIA 候选并重新绑定
probe evidence；不能把该首轮 candidate registry 当作 ready 或降低 fast/3-model 门槛。

首次 pre-Fusion 尝试还发现进程环境中的 `AXIO_FUSION_REGISTRY_PATH` 会让 discovery
被跳过，产生 `prefusion_complete_inventory_required` 阻断；该输出不包含 provider
stream/reasoning screening 结果。后续 retry 必须在显式取消该环境 registry 的独立进程
中运行完整 discovery/research/strict-stream chain，正式服务环境保持不变。

第二次 retry 虽已完成 discovery，仍因 `max_models=16` 截断了 27 个 logical/35 个
physical 候选而 fail-closed。第三次 retry 必须覆盖完整 discovery 分母后才允许研究与
stream probe；不得通过降低候选、复用 partial pool 或跳过 candidate inventory gate。

第三次 retry 已完成正式 Pre-Fusion handoff：27 logical/35 physical 完整发现、21 个
strict-stream available、15 logical models role coverage ready，probe-bound registry
为 21 models/4 providers/5 fast candidates，provider evidence audit ready。该 registry
只打开 r7 operational admission，不打开 ranking/freeze/target gate；下一步必须以新
source seed 执行固定 90 秒 admission 并重新绑定所有后续 digest。

r7 source manifest successor 已注册，保持 r6 source contract 但使用新的 selection seed
并绑定新的 predecessor digest；该文件只打开 r7 admission/screening 的 source identity，
不包含 target 结果，也不改变 r6 冻结证据。admission 未达到至少 3 个 formal eligible
canonical models 前，screening plan 与 Harness target gate 继续关闭。

### r7 admission 与 immutable screening preflight 终态（2026-08-17）

r7 operational admission 已自然终态：21 个 candidate profiles 中 15 个 production
admitted、9 个 formal baseline eligible，`status=ready`，固定 90 秒 non-target workload
合同通过，敏感字段均为 `false`。private receipt content digest 为
`bf6db0c659b728a6d4c0a8e5d99c1fb9b66e1f70ec96977de048fd393c77af12`；safe receipt 不含
provider 原始输出、prompt、URL、model id 或 credential。

达到三模型最低门槛后，已用新的 r7 source manifest、probe-bound registry 和 admission
receipt 创建 immutable screening plan：8 个 canonical groups、9 个 physical profiles、
2 个独立 source family、16 个 serial units、预计 1712 calls，plan digest 为
`1ba163ddacacd2ab1c77549789532f930d5cd595e84ed07251bf46a50d586444`。首次漏传 admission
的 preflight 以 `screening_plan_current_inputs_mismatch` blocked receipt 保留；补齐同一
admission input 后 zero-network preflight 已 `preflight_ready`，16/16 task materialize，
`target_suite_calls_performed=false`。

当前只允许启动该 r7 frozen plan 的 live screening；screening terminal、transport gate、
external ranking、provider freeze 和同 cohort Harness lineage 完成前，target calls 与
superiority claim 继续关闭。操作记录见
`docs/operations/composite_r7_admission_terminal_2026-08-17.md`。

### r7 live screening 启动（2026-08-17）

r7 live screening 已以 `setsid` 后台启动，固定 `max_workers=1`、fail-fast transport gate，
并绑定同一 registry、source manifest、private probe 与 operational admission。第一次
启动因复用 preflight state 的 mode/readiness digest 不匹配而在 provider 调用前
fail-closed；该 receipt 独立保留。随后从全新 live state 启动成功，当前只允许低频检查
PID、state、完整分母和 safe flags。screening terminal 前继续关闭 ranking、provider
freeze、Harness target calls 和 superiority claim。详细记录见
`docs/operations/composite_r7_screening_live_2026-08-17.md`。

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

- 2026-08-21：补强自适应渠道校准的 hash-only 指纹。旧指纹只比较 provider、model 和
  api_format，无法捕获 reasoning transport、工具/视觉准入、能力/时延/成本元数据或
  endpoint binding 的变化；现在通过安全白名单纳入这些校准相关字段，endpoint 仅保留
  SHA-256，API key/env 轮换明确忽略。新增 4 条回归并通过校准、CLI、渠道配置专项
  `38 passed`；该信号只生成 shadow recalibration 建议，不改生产 router、r18 frozen
  plan/source/registry，也不触发 provider 或 target 请求。r18 仍为
  `preflight_ready`、`next_gate=screening`，等待明确 live screening 授权。
- 2026-08-16：完成 transport5 非目标筛选 cohort，并为 provider baseline
  freeze 增加严格的 transport-only admission 路径。该路径将 receipt 绑定到
  原始 registry hash 或显式 probe-bound 派生物，拒绝 benchmark/质量选择字段，
  并按精确的 profile/canonical hash 集合过滤正式 provider pool。重新生成的
  freeze 已具备 ready 的 external top-three ranking 和匹配 digest，但仍因真实
  的 missing-fast-candidate portfolio 缺口阻塞。全量回归为 1036 passed、7
  skipped；未执行 target benchmark calls，也未做 superiority claim。
- 2026-08-20：r14 composite screening 已自然终态，16/16 source units terminal，
  10 completed、6 failed；最终 state 为 `partial`，transport-only admission 为
  `ready`（4 个 eligible canonical，最低门槛 3），但完整-pool ranking conversion
  因 partial campaign fail-closed，supervisor 为 `screening_ranking_conversion_blocked`。
  r14 没有 provider baseline freeze、official/audited Harness import 或 target-suite
  请求；保留完整失败分母，禁止恢复 checkpoint、拼接 survivor subset 或降低 2% gate。
  下一步只注册新的 immutable r15 source successor，重新生成 plan/preflight 后再启动
  一套 live screening，并严格沿 transport → ranking → external top-three → freeze →
  Harness → convergence audit → 21-suite campaign 链路推进；在全部证据完成前不做
  superiority claim。
- 2026-08-20：r15 immutable successor 已完成注册、冻结计划和 zero-network preflight。
  source successor receipt 为 ready；plan 为 `ready=true`（16 serial units、2 source
  families、8 canonical groups/9 profiles、`max_workers=1`、2% fail-fast gate），preflight
  为 `preflight_ready` 且 network/target calls 均为 false。r15 Harness 控制面已离线生成：
  6/6 hash-only pin 和 execution plan ready，acquisition/import/binding/convergence audit
  按预期 blocked，`next_gate=screening`、`target_suite_calls_allowed=false`。下一步只启动
  一套绑定 r15 plan/source 与 r7 probe/admission 的 live screening，terminal 后再按
  transport → complete-pool ranking → external top-three → freeze → same-cohort Harness
  → convergence → 21-suite campaign 推进；旧 r14 结果、checkpoint 和 survivor subset 不得复用。
- 2026-08-20：r15 唯一 live non-target screening 已用 `setsid/nohup` 启动，screening、
  convergence supervisor、lineage watcher 三个 PID 均绑定同一 frozen plan/source/probe/
  admission；首个 serial unit 已进入 provider 调用，private checkpoint 从 9/112 推进到
  21/112，campaign 尚未产生 terminal state。supervisor/watcher 保持
  `next_gate=screening`、`target_suite_calls_allowed=false`，transport/ranking/freeze/
  official import/target 均未启动；持续低频检查，禁止恢复 checkpoint、重试失败 case、
  修改 plan 或启动第二套 screening。
- 2026-08-20 12:25：r15 screening 仍在唯一首个 serial unit，private checkpoint 已到
  27/112、状态 `partial`；safe live state 尚未 terminal，因此 completed/failed unit
  计数仍未生成。三个托管进程存活且 plan identity 未变，supervisor/watcher 保持
  `next_gate=screening`、`target_suite_calls_allowed=false`，下游 transport/ranking/
  freeze/import/target 产物均不存在。
- 2026-08-20 12:45：低频只读复核确认 r15 唯一 screening、supervisor、lineage watcher
  仍由 init 托管且 plan identity 未改变。首个 serial unit private checkpoint 推进至
  68/112，状态仍为 `partial`，checkpoint SHA-256 为
  `3aafaf214d732dfa72b0f323a9087a347284dad5fce0afd0b4855ae8e81beef6`；safe live state
  仍未生成，完整 campaign 分母、transport admission、ranking、provider freeze、official
  import 和 target campaign 均不可宣告。`next_gate=screening`、
  `target_suite_calls_allowed=false` 保持不变；本次未恢复 checkpoint、未重试 case、未修改
  frozen plan、未启动第二套 screening。
- 2026-08-20 13:34：r15 safe live state 首次写出，但 campaign 仍为 `running`，并非
  terminal：16 个 planned unit 中 `1 completed / 2 failed`，`ready_for_ranking=false`。
  两个失败 unit 的完整 transport 分母分别为 `80/102` 与 `112/112`，均触发固定 `2%`
  fail-fast gate；这不是质量排名结果。当前活动 unit checkpoint 为 `42/102`、状态
  `partial`，screening receipt、transport admission、ranking、provider freeze、official
  import 与 target campaign 均不存在。state 继续绑定 r15 plan/source 与 r7 registry/probe
  hash，`network_calls_performed=true`、`target_suite_calls_performed=false`；本次未恢复
  checkpoint、未重试失败 case、未修改 frozen plan、未启动第二套 screening。
- 2026-08-20 13:37：r15 safe live state 更新为 `status=running`、16 个 planned unit 中
  `1 completed / 3 failed`、`ready_for_ranking=false`，state SHA-256 为
  `698ce13d3b1cf3e8f57c22c074da3be554cdd3e99e7bdd792d8182ce2f2114a5`。新增 failed unit
  的完整分母为 `42/102` scored/transport split，即 `60/102` transport failures、failure
  rate `0.588235294118`，触发固定 `2%` fail-fast；旧失败分母和 completed unit 均保留。
  当前 checkpoint 已切换到新的 112-case unit，`0/112`、状态 `partial`；screening receipt、
  transport admission、ranking、provider freeze、official import 与 target campaign 均不
  存在，`target_suite_calls_performed=false` 保持不变。本次未恢复 checkpoint、未重试失败
  case、未修改 frozen plan、未启动第二套 screening。
- 2026-08-20 12:35：低频只读复核确认 r15 唯一 screening、supervisor、lineage watcher
  仍由 init 托管且 plan identity 未改变。首个 serial unit private checkpoint 推进至
  48/112，状态仍为 `partial`，checkpoint SHA-256 为
  `803226be75520e912374c14e0e622a63292f623a9e0ca530d94dc982edb49016`；safe live state
  尚未生成，完整 campaign 分母、transport admission、ranking、provider freeze、official
  import 和 target campaign 均不可宣告。`next_gate=screening`、
  `target_suite_calls_allowed=false` 保持不变；本次未恢复 checkpoint、未重试 case、未修改
  frozen plan、未启动第二套 screening。
