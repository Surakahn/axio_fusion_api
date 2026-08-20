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
- 当前服务只读健康：`ready`，公共模型为三档，四种协议可用，`auto -> proxy`，
  生产 loopback 为 `127.0.0.1:18900`，当前 serving registry 为 r7 probe-bound。
- 当前工程回归：`1076 passed, 7 skipped`；这是代码契约证据，不是能力或质量证据。

## 差距矩阵

| 领域 | 当前状态 | 已完成的可验证内容 | 未完成/阻塞 | 下一条合法动作 |
| --- | --- | --- | --- | --- |
| 产品边界 | **done** | 独立 remote-only 服务；三档公共模型；不加载本地权重；图片 lane 与文本 Fusion 隔离 | 尚未以完整 baseline/target 证据证明质量、成本、延迟目标 | 保持公共合同不变，等待 baseline freeze 后做校准 successor |
| 四协议公共 API | **done/partial** | Chat Completions、Responses、Anthropic Messages、Gemini 的规范化输入、流式输出、错误和 reasoning 公共边界已有回归 | 必须在正式 campaign 对 12 个 tier/surface 单元做同 cohort parity | campaign 放行后运行四面配对 parity 和失败审计 |
| 图片能力 | **done** | verified image registry、generation/editing 探针、multipart/90 秒门禁、text/image 隔离 | 不是文本 Fusion 能力，不得混入 21-suite 文本 claim | 仅按独立 image registry 维护和回归 |
| Fast 工作流 | **partial** | bounded direct cascade、轻量验证开关、replica failover、3x/预算 guard、fail-closed | 当前 r7 role/capability admission 使多数复杂请求退回 direct；实际 pricing/tool metadata 未校准 | baseline freeze 后用 non-target shadow 校准 light-verify 的 VOI/成本阈值 |
| Terra 工作流 | **blocked/partial** | selective fusion、独立性检查、Judge/Synth reservation、正确的 direct fallback；零网络 fake-provider 回归已证明完整 role pool 下 panel phase 可配置并执行全部已准入 expert | 当前 registry 没有同时满足 `independent_solver + judge` 的准入容量；不能用弱模型冒充；fake-provider 结果不构成 live 能力证据 | 完整 screening/ranking/freeze 后做 endpoint-bound role successor，再 shadow replay；若 live 再出现 partial panel，按 safe cause taxonomy 分诊 |
| Pro 工作流 | **partial** | panel -> Judge -> targeted escalation -> acting Synthesizer；角色上下文隔离；公共 reasoning 清理 | 当前 dry-run 只有一个 provider hash，跨 provider 互补不足；质量/成本尚未实测 | baseline freeze 后做 provider diversity/error-correlation/quality shadow 优化 |
| Router/编排算法 | **partial** | query analysis、canonical 去重、角色 gate、deadline/call/cost reservation、fallback、circuit recovery、safe trace | 静态 capability prior 仍未被完整双源 non-target evidence 替换；VOI/portfolio optimizer 未晋级 | 只在 baseline freeze 后使用 non-target/shadow/holdout 设计和审批 successor |
| Judge/Synthesizer | **partial** | 结构化比较 rubric、consensus/contradiction/coverage、独立性 gate、输出归一化 | confidence calibration、abstention/repair 阈值尚无同 cohort 实证；不得以 target label 调参 | baseline freeze 后用 operational non-target cases 校准并绑定 rollback |
| Provider admission | **blocked** | r7 probe-bound registry、四协议 adapter、90 秒 stream gate、健康和安全 receipt；r18 credential-ready 零网络预检 9/9 | r17 transport admission blocked；8 canonical 仅 1 个同时通过两源 2% gate，低于 minimum 3；credential readiness 不等于 transport admission | 明确授权后只启动唯一 r18 frozen live screening |
| Ranking/baseline freeze | **blocked** | ranking conversion、external top-three、freeze 的 fail-closed 控制面已实现 | r18 尚未 terminal，故无完整 pool ranking、rank 1/2/3 或 freeze | r18 terminal -> transport admission -> complete-pool ranking -> external top-three -> freeze |
| Harness 控制面 | **partial/ready offline** | hash-only pin、execution plan、持久化状态、可恢复 supervisor、import audit、convergence gate | r18 acquisition/import/binding/convergence 依赖上游 screening/freeze，当前 `next_gate=screening` | freeze 后绑定同 cohort official/audited runs，再审计放行 target |
| 21-suite 资产 | **partial/blocked** | 9 类 21 套 matrix、case/source/decoding/统计合同；14 套可直接 materialize，6 套需 official import，GPQA 受授权门禁 | 没有完整同 cohort run；GPQA/官方 harness/import 仍不能冒充 ready | 先完成 baseline freeze 和官方/audited imports，再启动 target |
| Benchmark campaign | **blocked** | 独立 evaluator、四面 API、paired statistics、Holm、effect size、3x latency、污染审计的代码/合同已具备 | `target_suite_calls_allowed=false`，无 provider baseline freeze，无 campaign 证据 | convergence 返回 `ready_for_target_campaign` 后再按锁定矩阵运行 |
| 商业级运维 | **partial** | 生产 health ready；PID `759644` 已通过 setsid 受控发布加载最新代码；proxy auto；atomic/safe receipts；secret/raw output 隔离；公开 capability warnings 已实际返回；public/operator key 比较使用 constant-time 语义；`current_channels.env` registry identity 已对齐 r7 serving identity | auth 未启用；pricing/context/tool 能力字段为 unknown；跨 provider diversity 不足 | 按部署策略决定 auth；baseline 后补齐 admission metadata，并以 non-target/shadow 证据校准跨 provider 组合 |
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
