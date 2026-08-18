# Composite r8 successor Intake 与 Harness 收敛决策（2026-08-18）

## 目的

本记录把 r7 的 blocked 终态与 r8 successor 的当前运行状态分开，固定本轮
Harness 收敛的证据边界、门禁顺序和恢复策略。它是控制面文档，不是 ranking、
provider baseline freeze 或 superiority claim。

## 当前状态与信任等级

| 资产 | 当前判定 | 可复用范围 |
| --- | --- | --- |
| r7 screening、transport admission、supervisor receipt | `trusted / reference_only` | 只用于解释 transport failure 与 successor 原因；不得拼接到 r8 ranking |
| r8 source successor manifest | `trusted` | 固定 source family、selection seed 和 successor lineage |
| r8 `baseline_screening_plan` | `trusted` | 16 个 serial units、2 个 source family、`max_workers=1`、fail-fast transport gate；冻结后不可修改 |
| r8 preflight/campaign receipt | `trusted` | 证明 preflight 无 network/target call；不证明 provider 可用性或模型能力 |
| r8 live screening state | `usable_with_verification` | 当前仍为 `running`，已完成 1/16；必须等待全部 unit terminal 后才可判断 transport admission |
| 21-suite case manifest 与六套 Harness pin scaffold | `usable_with_verification` | 可在 r8 transport/ranking/freeze 完成后重新绑定；r7 binding 不得跨 cohort 复用 |
| operator-owned raw outputs | `private_only` | 仅供 screening 恢复和离线统计；不得写入 safe receipt、Git、日志或最终报告 |

当前 r8 的关键不可变摘要：

- successor manifest digest：`725cd055e845cfb609667be1c71ebac69de648d570edae333bdaa5031025178a`
- screening plan digest：`5a4b496735ab7553be7046079d3611172ef8d2973bf41c594041058583cd38c6`
- preflight campaign digest：`4922a32716d79fc4d24dbb49e3529f7ab7ba71e05733d57995734c09aec67b5b`
- selection seed：`composite-r8-2026-08-18-transport-successor`

## 收敛架构

Harness 采用两个相互隔离的平面：

1. **执行平面**：screening 或正式 target runner 发起 provider/API 调用，原始响应只
   进入 operator-owned private root；执行状态按 unit checkpoint 原子写入。
2. **证据平面**：只读取冻结输入和安全 receipt，保存内容 hash、计数、错误码、分母、
   版本与门禁状态。证据平面不能反向触发 provider 调用，也不能从旧 cohort 补结果。

两平面之间只有 hash-bound receipt。每个 successor 都必须重新绑定以下链路：

```text
live probe registry
  -> immutable source successor
  -> frozen non-target screening plan
  -> terminal transport admission
  -> full-pool ranking
  -> provider baseline freeze
  -> cohort-bound Harness pin/execution/import
  -> convergence audit
  -> target campaign
  -> paired scorecard/statistical/latency audit
```

门禁是单向且 fail-closed：

- screening 不是 target campaign；`target_suite_calls_performed` 必须保持 `false`；
- partial unit、transport failure rate 超阈值或 canonical 数不足时，只能创建新的
  immutable successor，不能恢复旧 cohort、降低最低 3-model 要求或拼接 completed subset；
- ranking 必须覆盖完整 candidate pool，并绑定两个 source family；
- official Harness import 必须来自 operator-owned 的真实 runner 输出，safe receipt
  只保留 hash/score/count，禁止空文件或模板 receipt 冒充；
- 只有同一 cohort 的 binding 与 convergence audit 同时返回
  `ready_for_target_campaign`，才允许产生 target 请求。

## r8 后续路由

1. 继续低频观察 PID `1069304`（screening）和 PID `1070554`（supervisor），不重启或
   停止它们。
2. screening 终态后读取 state、screening receipt、transport admission、ranking 与
   supervisor receipt；保留所有失败分母和 reason code。
3. 若 canonical transport 少于 3 个，封存 r8 全部证据并仅改变 successor source
   selection seed 创建 r9；不修改 r8 plan。
4. 若 transport ready，执行一次完整 ranking 与 provider baseline freeze，然后在 r8
   独立目录运行 Harness scaffold/materializer，生成 r8-specific pin、execution plan、
   acquisition/import audit、cohort binding 与 convergence audit。
5. 只有 operator 提供六套 official/audited Harness 的真实 import receipt，且所有
   hash、case manifest、freeze digest 和 API-surface contract 一致后，才允许 target
   campaign。
6. target campaign 完成后，分别验证 `axio-fast`、`axio-terra`、`axio-pro` 与三套
   frozen 单模型 baseline 的 paired effect size、显著性、延迟、失败恢复、四种 API
   格式和安全 redaction；在完整证据前不写 superiority claim。

## 运行安全

- CPA Plus 只做读健康检查，不因 Harness 操作停止、重启或重建正式服务。
- 所有 safe receipt 必须保持 `secrets_persisted=false`、
  `raw_provider_outputs_persisted=false`、`raw_provider_url_persisted=false`。
- r7 和 r8 的 plan/state/checkpoint 都是只读历史；任何修复都使用 successor lineage。

## 本阶段结论

当前下一锚点是 **继续 r8 non-target screening**，而不是 baseline ranking、Harness
import 或 target experiment。r8 仍未达到 `transport_admission=ready`，因此不能声称
基线冻结、Harness 已授权或融合模型优于单模型。
