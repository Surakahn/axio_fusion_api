# Axio Fusion 基线与 Benchmark Harness 收敛架构（2026-08-16）

## 目标与边界

本设计把“provider baseline 选择”“官方 Harness 执行”和“Fusion superiority claim”分成三个不可互相替代的证据边界。任何一层未完成，下一层只能生成只读 preflight 或 blocked receipt，不能用旧 cohort、先验分数或手工映射补齐证据。

当前 composite cohort 使用已经完成严格 streaming/role probe 的两份 live probe artifact，离线合并为新的 10-profile registry，再从该 registry 重新注册两源 non-target screening。旧的 r5、transport5 plan、ranking 和 freeze 继续作为不可变历史证据，不进入 composite 结果。

## 分层架构

### 1. Evidence ingress

- 输入是 prompt-free 的 live probe artifacts；每个 profile 必须有严格 SSE/NDJSON、三样本稳定性和 90 秒时延证据。
- `registry-from-probe --probe-file ...` 可以接收多份 probe，按精确 `provider/model` profile identity 去重；不做模糊 alias 合并。
- 输出分为 private registry 和 redacted evidence。private 文件只供 operator 恢复，safe 文件只保留 hash、计数、reason code 和 contract。
- 当前 composite registry：
  `private/runs/2026-08-16-composite-cohort-r1/registry.composite.from-probe.private.json`
  （10 个去重 profile、3 个 provider、3 个 fast candidate）。

### 2. Non-target screening

- `baseline-screening-plan` 在任何 target benchmark 前冻结 source manifest、selection seed、candidate group、task order、worker 数和 fail-fast transport gate。
- 每个 canonical model 是一个 candidate；同 canonical 的 replicas 只能作为 failover，不能增加独立票数。
- `baseline-screening-run` 只调用 provider API，不调用 Fusion target suite；原始答案可以暂存在 operator-owned private root 供恢复，但永不进入 safe artifact 或 Git。
- transport admission 只看每个 source-unit 的 transport failure rate、terminal status 和完整分母；不读取答案、标签或得分。

### 3. Ranking 与 baseline freeze

- 只有所有 source-unit terminal 且通过 transport gate，才允许 `baseline-screening-to-ranking`。
- ranking 必须覆盖完整 candidate pool，并绑定两个独立 non-target source family；不允许用旧 ranking、模板或手工 top-three 替换。
- `benchmark-provider-baseline-freeze` 同时绑定 registry content hash、probe-evidence audit、transport receipt、screening ranking 和 external evidence。最终 claim 还要求跨 provider verifier capacity 与 fast candidate。
- `final_claim_freeze_ready=false` 时，Harness 只能做离线 pin/preflight，不得启动正式 target provider calls。

### 4. Official/Audited Harness

Harness 由四个独立 contract 组成：

1. **Pin manifest**：固定 runner commit、数据快照、evaluator、prompt protocol、decoding 和 evaluator 文件 hash。路径只存在于 private config，safe receipt 只保存 hash。
2. **Execution plan**：把每个 suite、candidate、API surface 映射为不可变 execution task；要求 source template、pin 和 position-balance contract 完整。
3. **Preflight/import**：验证 dataset、runner、输出格式和 freeze digest；失败时 provider call count 必须为零。官方 runner 原始 JSONL 只能在 private import root，safe import 只保存 per-run hash/score/count。
4. **Campaign/claim audit**：执行固定 task，生成 scorecard、paired statistical/latency/contamination audit、API-surface parity 和 final completion audit。claim audit 只能读取已绑定的 run/scorecard/freeze receipt。

当前仓库已经实现上述控制面（`official_harness.py`、`evaluation.py` 以及对应 CLI），但 `private/official_harness_execution_plan.current.safe.json` 属于通用旧模板，不能直接冒充 composite freeze 的 Harness。composite freeze 完成后必须重新生成 cohort-bound pin、execution plan 和 import receipts。

composite r1 已完成离线 Harness scaffolding：六套 pin 均 ready，execution plan
包含 108 个结构化 task，所有 task 的 pin/template contract 均通过；当前
acquisition status 仍缺少 108 个 official import，因此该 plan 只证明 Harness
结构可执行，不证明任何模型结果。对应产物为：

- `private/runs/2026-08-16-composite-cohort-r1/harness_pin_manifest.composite.safe.json`
- `private/runs/2026-08-16-composite-cohort-r1/benchmark_acquisition_checklist.composite.safe.json`
- `private/runs/2026-08-16-composite-cohort-r1/official_harness_execution_plan.composite.safe.json`

## Cohort r1 执行契约

- registry：`registry.composite.from-probe.private.json`
- plan：`baseline_screening_plan.composite.private.json`
- plan digest：`b53c8196c688220a99e2b3b6091cb35333dcfe5ecc13795d842f380a9c2e3e99`
- candidate：10 canonical / 10 physical profiles
- source：2 个独立 source family，2140 个预估 provider calls
- execution：`max_workers=1`、fail-fast transport gate
- 初次未加载私有环境变量的 preflight 已单独记录为 blocked，网络调用数为 0；retry1 使用同一冻结 plan、显式加载 `private/current_channels.env`，写入独立 private root。

## 状态机与恢复

```text
probe evidence ready
  -> composite registry ready
  -> screening plan ready
  -> screening running
  -> terminal screening
  -> transport admission ready
  -> ranking ready
  -> provider baseline freeze
  -> official harness pin/preflight
  -> live campaign
  -> claim/final audit
```

任何 `partial`、transport-blocked、identity mismatch 或 freeze blocker 都会在同 cohort 内停止晋级。修复必须创建 successor cohort，保留旧 plan/state/checkpoint；不覆盖、不选择性拼接、不降低阈值。CPA Plus formal service 只做读健康检查，日常配置不触发重启。

## 收敛完成定义

只有同时满足以下条件才允许宣称收敛：

- composite screening 完整 terminal，transport/ranking/freeze receipt 全部 hash 一致；
- provider baseline freeze 的 `final_claim_freeze_ready=true`，并证明跨 provider independent verifier 与 fast candidate；
- 六套 official/audited Harness 的 pin、execution、import 均 ready 且绑定同一 freeze；
- 21-suite target campaign 的 run、scorecard、统计、延迟、污染、API parity 和 final audit 全部 complete；
- 三档 Axio claim 通过预注册的 paired effect-size、显著性和延迟门禁。

在这些条件之前，所有输出都必须标记为 readiness、diagnostic 或 blocked evidence，不得写成 superiority claim。
