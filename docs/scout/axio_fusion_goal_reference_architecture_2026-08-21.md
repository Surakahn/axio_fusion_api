# Axio Fusion Goal 参考架构与收敛路径（2026-08-21）

## 结论先行

Axio 的产品不是一套新训练出来的模型，也不是本地模型推理服务。它是一个
remote-only Fusion API：把多个供应商通过 API 提供的模型能力，放进可复用、可
审计、可限时的 prompt 流程和工程控制面中，按请求选择合适的远程模型、角色和
协作拓扑，再把结果归并为三个稳定的公共模型名：`axio-fast`、`axio-terra`、
`axio-pro`。

因此，Fusion 的“模型”是一个受预算约束的工作流契约：

```text
公共请求
  -> 规范化与任务分析
  -> 按 tier 选择工作流和角色
  -> 远程专家并行/级联
  -> Judge、定向修复、Synthesizer
  -> 故障降级、公共输出清理、协议渲染
```

Harness 是评测与控制平面，不是产品本体。它负责把渠道探测、baseline 选择、
官方评测、恢复、证据、权限和 claim gate 固定下来；它不能把 benchmark 标签写回
生产 router，也不能把自己变成一个无限自我改进代理。

## 已确认的产品与非目标

### 产品目标

- 只向外提供 `axio-fast`、`axio-terra`、`axio-pro` 三个公共模型名称。
- 允许内部接入多个 provider 和四种上游协议：Chat Completions、Responses、
  Anthropic Messages、Gemini GenerateContent。
- 用 prompt、角色分配、上下文投影、并行 fan-out、验证、综合、fallback、成本、
  延迟、并发、可靠性和安全边界，将不一定最强的模型组合成更强的有效工作流。
- 质量目标是接近或超过相应最强单模型，成本和延迟必须有明确预算；没有通过
  统计、实用效果和延迟门禁时，不作 superiority claim。
- 供应商替换只需要更新受 admission 约束的 registry 和 prompt/policy 版本，
  不改变公共 API 合同。

### 明确非目标

- 不训练、微调或合并本地权重。
- 不要求本地部署任何 LLM；所有候选、Judge、Synthesizer 都是远程 API 调用。
- 不把同一 canonical model 的物理 replica 当成多个独立投票者。
- 不把 Harness 的 shadow policy、评测得分或 benchmark 标签自动写入生产路由。
- 不把图片模型放入文本 Fusion 池；图片 lane 只能使用独立 verified image
  registry。

## 三档 Fusion 契约

三档不是三个隐藏 provider alias，而是三种不同的“质量/成本/延迟”工作流。
每次请求先进行任务复杂度、风险、工具需求、预算和可分解性分析，再决定是否
启用多模型；简单请求不应因为 Fusion 名称而被固定 fan-out。

| 公共模型 | 默认工作流 | 允许的质量控制 | 成本/延迟原则 |
| --- | --- | --- | --- |
| `axio-fast` | direct primary + 有条件的轻量验证/replica failover | 只在风险、收益和剩余预算都足够时启用一次验证 | 低 fan-out，优先 p50/p95 和可用性 |
| `axio-terra` | 选择性互补专家，必要时一次独立检查 | 根据 expected utility 选择第二视角、verifier 或 domain seat | 质量提升必须值得额外调用，保留硬 deadline |
| `axio-pro` | bounded expert panel -> Judge -> targeted repair -> acting Synthesizer | 结构化比较共识、矛盾、覆盖、盲点和证据，最多一轮定向反馈 | 允许更高预算，但不突破 call/cost/deadline/3x guard |

所有 tier 共用以下不变量：canonical 去重、provider/correlation-aware 选席、
role-scoped context、共享 deadline/call/cost budget、mandatory stage reservation、
replica failover、circuit recovery、工具权限隔离、safe trace，以及四种公共协议
的一致 normalized route contract。

## 参考实现的吸收边界

### Sakana AI Fugu / TRINITY / Conductor

可复用的核心思想是把模型池当成黑盒能力池，由一个控制器针对 query 选择 worker、
子任务、通信拓扑和上下文可见性。Fugu 的低延迟路线提醒我们：能单模型完成的
请求不要无条件多调用；Fugu-Ultra 的动态 workflow 提醒我们：复杂任务需要显式
的子任务和状态，而不是把所有模型输出简单拼接。

Axio 的落地方式是：每个 worker 都是隔离的远程 API seat，拥有角色、模型、输入
上下文、输出上限和 deadline；Conductor 类决策只能生成受 schema 约束的 route
plan，不能获得工具权限或写入生产配置。共享记忆只通过哈希绑定的安全中间状态
传递，不能把 raw provider output、密钥或 benchmark 标签写入 receipt。

### OpenRouter Fusion

可复用的核心流程是“panel 并行回答 -> Judge 结构化比较 -> 一个最终模型负责公共
答案”。Judge 输入至少要区分 consensus、contradictions、partial coverage、
unique insights 和 blind spots；最终答案所有权只属于 acting Synthesizer。Fusion
是按任务价值选择性启用的能力，不是对每个请求固定执行全 panel。

Axio 额外加上 canonical/replica 约束、跨 provider 可靠性和错误相关性、预算
reservation、工具隔离、streaming boundary 和 fail-closed receipt，使该流程可在
商业 API 中稳定运行。

### Harness Engineering for Self-Improvement

Harness 只吸收其工程原则：工作流自动化、文件系统持久化状态、可恢复后台任务、
上下文工程、权限控制、评测和证据链。它对应 Axio 的控制平面：

```text
provider probe
  -> immutable non-target screening
  -> transport admission
  -> complete-pool ranking
  -> external top-three
  -> provider baseline freeze
  -> same-cohort Harness pin/import
  -> convergence audit
  -> 9 类 21 套 target benchmark
  -> statistics / latency / contamination / final audit
```

Harness 的 policy candidate 只能先在 zero-network preflight 或 shadow replay 中
验证，再经显式批准生成新的 runtime policy。生产 Fusion 的自适应只使用
provider admission、request-local signal 和受限运行时 telemetry，不能读取 target
答案或标签。

## 当前证据与真实缺口

- r17 已自然终态：16/16 serial unit terminal，`6 completed / 10 failed_or_blocked`，
  `ready_for_ranking=false`。
- r17 transport admission 使用完整 transport 分母，8 个 canonical 中只有 1 个
  同时通过两个 source family 的固定 2% gate，最低要求 3，因此结果为 blocked。
- r17 没有 ranking、provider baseline freeze、official import 或 target request；
  partial score 和 completed unit 只能作为 transport/diagnostic evidence。
- r18 已完成 immutable successor 的离线控制面：2 source family、8 canonical、9
  replica、16 serial unit、`max_workers=1`、固定 2% fail-fast；zero-network
  preflight 为 `preflight_ready`，`target_suite_calls_allowed=false`。
- 当前主要工程问题是 transport failure 的 source/model 分布、90 秒 provider
  硬上限、代理/配置和 fail-fast 对可观测分母的影响。它们尚未足以支持修改 router
  或 prompt，也不能被误读成模型质量失败。

## 最终 21-suite 评价合同

正式目标是 9 类 21 套，而不是历史 README 中的 7 类/14 套叙述：

1. 科学知识：GPQA Diamond、MMMU text science
2. 多语言：Global-MMLU Lite、FLORES translation instruction
3. 代码：LiveCodeBench、HumanEval
4. 数学：MATH-500、recent AIME
5. 逻辑推理：BBH、ARC Challenge
6. Agent 工具调用：BFCL、tau-bench
7. 日常工作技能：IFEval、MT-Bench work
8. 幻觉与事实性：TruthfulQA、HaluEval
9. 垂直领域：MedQA-USMLE、FinanceBench、LegalBench、BizBench、
   PolicyBench/PolicyLLM PolicyBench

每个候选必须使用同一 locked case hashes、prompt/decoding/evaluator binding，并
通过四个公共 API surface 运行。六套需要官方或审计 Harness import；GPQA 的授权
访问未满足时只能显式报告 blocked 或合法的 MMLU-Pro STEM replacement，不能把
替代结果改名为 GPQA。

最终 claim 同时需要：provider baseline freeze、完整 candidate 分母、paired
case-level statistics、Holm-Bonferroni、多项实用 effect-size、p50/p95 不超过对应
baseline 3x、四协议 parity、contamination/failure audit 和 final completion audit。
任何一档失败都只产生诊断和下一轮 successor proposal，不把局部胜利写成项目完成。

## 当前至完成的执行顺序

1. 只读审计 r17/r18 transport 根因：按 source family、canonical model、HTTP
   timeout、proxy/listener、registry/admission 和 plan digest 汇总 safe evidence。
2. 根因明确且环境稳定后，才由 operator 明确授权一次 r18 live screening；不改
   frozen plan、不恢复 checkpoint、不降低 2% gate、不拼 survivor subset。
3. screening terminal 后执行同 cohort transport admission；只有通过才做 complete-pool
   ranking 和 external top-three，随后冻结三档对应 provider baseline。
4. 绑定同 cohort Harness pin、官方/审计 import、execution plan 和 convergence audit；
   audit 未返回 `ready_for_target_campaign` 时 target calls 必须为零。
5. 对 axio-fast/terra/pro 与 frozen single-model baseline 执行 9 类 21 套矩阵，
   做统计、延迟、成本、协议、污染和失败分析。
6. 若未达质量/成本/延迟目标，创建新的 policy/prompt successor，在 non-target
   shadow 上比较并重新走门禁；只有最终 audit 通过才可发布 claim。

这份报告是 scout/framing artifact，不授权网络调用，也不替代任何 screening、
ranking、freeze 或 benchmark receipt。

