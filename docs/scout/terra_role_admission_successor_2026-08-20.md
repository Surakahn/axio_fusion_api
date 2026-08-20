# axio-terra 角色准入 Successor 调查（2026-08-20）

## 调查边界

本调查只读取当前 r7 probe-bound registry 和本地 `FusionEngine.complete(...,
live=False)` dry-run，不发送 provider 请求，不读取 screening checkpoint 原文，不修改
r17 frozen plan、registry、router、prompt、weights 或生产服务。结论只用于 screening
terminal、transport admission 和 provider baseline freeze 之后的 successor policy 设计。

## 证据锚点

当前生产/筛选绑定的 registry 为
`private/runs/2026-08-17-composite-cohort-r7-prefusion-full/runtime_registry.probe-bound.r7.private.json`，
SHA-256：
`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`。

离线加载得到 21 个 physical profiles、4 个 provider，registry readiness 为 ready，且
没有改变任何 raw provider/secret 持久化边界。按 hash-bound `screening_allowed_roles` 汇总：

| 角色 | 允许 profile 数 | 明确拒绝 profile 数 | 说明 |
|---|---:|---:|---|
| `primary_solver` | 4 | 17 | 具备主求解角色的 profile 很少 |
| `independent_solver` | 1 | 20 | Terra 独立证据容量不足 |
| `critic` | 2 | 19 | Pro 可使用，Terra 不应伪造替代 |
| `domain_specialist` | 3 | 18 | 只能覆盖明确领域目标 |
| `short_verification` | 3 | 18 | 其中 1 个 operational probe 失败 |
| `judge` | 2 | 19 | Terra 当前没有可用 Judge 候选 |
| `synthesizer` | 3 | 18 | Synthesizer 容量存在，但不能单独解除 Judge 缺口 |

这个矩阵是 capability/role admission evidence，不是质量分数，也不代表任何 provider
ranking 或 superiority claim。

## 当前 dry-run 复现

使用相同 r7 registry、`require_prefusion=True` 和 high-complexity prompt 得到：

| tier | strategy | provider-fusion gate | local-consensus gate | 结论 |
|---|---|---|---|---|
| `axio-fast` | `fast_direct_cascade` | 通过轻量 direct contract | 不作为完整 Fusion | 符合 Fast 低延迟契约 |
| `axio-terra` | `terra_direct` | 缺少 `judge` | 缺少 `independent_solver` | 正确 fail-closed 回退，不是 deadline 证据 |
| `axio-pro` | `pro_panel_judge_escalation` | `primary_solver`、`independent_solver`、`critic`、`judge`、`synthesizer` 均覆盖 | 通过 | 当前完整 panel 仍可构建 |

`router.py` 的 `_screening_role_allowed()` 对显式 allow/deny 和 operational role-probe
失败采取 fail-closed；`_provider_fusion_required_roles()` 对 Terra/Pro 要求 Judge 与
Synthesizer，并在有验证分支时要求独立证据角色。当前行为保护了生产质量边界，不能用
“换一个未使用的弱模型”来解除准入；这也避免了将 stage-only profile 冒充 evidence
profile。

## 根因判断

当前已证实的是 **r7 role-contract coverage 不足**，而不是 `_DeadlineBudget` 或 panel
phase budget bug：

1. 同一 registry 下 Pro 的完整 panel/Judge/Synthesizer dry-run 可以通过，说明全局
   stage 预算和角色编排代码并非普遍失效。
2. Terra 的 `provider_fusion` receipt 明确 `judge` candidate count 为 0，local
   consensus receipt 明确 `independent_solver` candidate count 为 0；失败发生在
   role admission 之前，而不是 provider call deadline 消耗之后。
3. 当前 screening 仍在 r17，不能通过修改 registry 或放宽 role gate 来“修复”此现象；
   任何手工角色提升都会破坏 probe-bound lineage 和后续 baseline 公平性。

## Baseline gate 之后的 successor 设计

### 1. 角色容量先验改为显式 contract

新 successor 不能按模型名或 provider alias 推断 Judge/solver 能力，而应由同一批严格
streaming、role-probe 和 transport evidence 生成 `role_capacity_matrix`：

- 每个 physical profile 绑定 `allowed_roles`、`failed_roles`、样本数、稳定性和证据
  digest；
- `independent_solver` 必须要求不同 canonical identity，跨 provider verifier 要求
  不同 provider；
- Judge/Synthesizer 角色必须同时满足 structured-output、critique/aggregation 和
  streaming evidence；
- narrow role（`domain_specialist`、`short_verification`）永远不能被重命名为
  `independent_solver`。

### 2. Terra 的最小可交付 route contract

只有在以下条件全部满足时，Terra 才能启用 panel route：

```text
primary_solver >= 1
independent_solver >= 1（不同 canonical identity）
judge >= 1
synthesizer >= 1
cross-provider verifier capacity >= 1（最终 claim 需要）
```

若条件不满足，`terra_direct` 是正确的商业级降级路径；receipt 必须保留缺失角色和
预算状态，不能报告为完成 Fusion。若通过受约束 panel optimizer 选出 narrow verifier，
必须显式记录它的窄角色，不得清除独立性缺口。

### 3. Successor 生成与晋级顺序

1. r17 screening terminal 后先做 transport admission，不能使用当前 partial unit 或
   survivor subset。
2. 只有完整候选池达到 minimum gate，才做 complete-pool ranking 和 provider baseline
   freeze；role capacity 只能消费 non-target evidence。
3. 冻结后对符合 transport 的完整候选运行新一轮 endpoint-bound role probe，生成新的
   immutable registry successor；不改写 r7 registry。
4. 在 target campaign 前执行 shadow route replay、独立 holdout 和 API-surface parity
   smoke；所有 policy candidate 绑定 registry hash、policy digest、rollback target 和
   contamination audit。
5. 只有 successor 的 role capacity、provider diversity、fast candidate、Harness import
   和 convergence audit 全 ready，才允许正式 21-suite campaign。

## 当前未完成项

- r17 screening 尚未 terminal，transport admission 尚未生成；
- 尚无完整 candidate-pool ranking、external top-three 或 provider baseline freeze；
- Terra role successor 尚未进行真实 endpoint-bound probe，不能声称已修复；
- 当前 dry-run 仅证明编排和 fail-closed 行为，不证明三档模型质量优于单模型基线；
- 不能在此阶段修改生产 router/weights 或启动任何 target benchmark 请求。

本调查结论是后续 successor 的设计输入，不是生产变更，也不是最终能力声明。

## 2026-08-21 零网络 panel budget 复现

为区分历史“Terra 只完成部分 panel candidate”现象的预算根因与 role admission 根因，
新增了一个完全使用 fake provider 的回归场景：8 个不同 canonical identity 的高能力
profile、`axio-terra`、`quality_target=0.95`、`reasoning_effort=high`、6-call 上限。
该场景不读取真实 provider 输出、不访问网络，也不改变 r18 或生产 registry。

受控结果：

- 4 个已准入 expert role（`primary_solver`、`independent_solver`、`critic`、
  `domain_specialist`）均完成；没有 pending/cancelled future；
- panel phase 外层预算为 15,000ms，成功配置 12,000ms 的最小 panel window；
- Judge 与 Synthesizer 各完成 1 次，共 6 次 fake provider call；
- targeted regression：`5 passed`（包含 runtime latency budget 相关断言）。

因此，当前调度循环在完整角色池和高推理强度下没有复现确定性的“1-6/10 budget
截断”。这不是 live provider 能力证据，也不能解除 r7 的 Terra role-contract blocker：
r7 仍缺少同时可用的 `independent_solver`/`judge` capacity，正式路径仍必须
`terra_direct` fail-closed，直到新的 endpoint-bound role probe 和 provider freeze
完成。若未来 live trace 再出现部分 candidate，必须优先按 safe receipt 区分
`fusion_panel_phase_deadline_exhausted`、provider transport failure、future cancellation
和 role admission，再决定是否注册 successor。
