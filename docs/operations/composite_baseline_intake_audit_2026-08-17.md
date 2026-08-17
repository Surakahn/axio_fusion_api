# Composite 基线 Intake Audit（2026-08-17）

## 审计范围

本记录对应 continuation goal 的当前 composite 线路，审计对象是
`2026-08-17-composite-cohort-r2` 及其 successor admission，不读取或传播 raw
provider output、prompt、label、API key 或原始 provider URL。

## 当前可信状态

| 资产 | 可信级别 | 结论 |
| --- | --- | --- |
| r2 frozen registry/plan | trusted | digest 与 screening state 绑定；禁止修改 |
| r2 screening state | trusted | 10/10 unit terminal，4 completed、6 transport failure，完整分母保留 |
| r2 transport admission | trusted-but-blocked | 仅 1/5 canonical groups 通过严格 transport，低于固定 3-model minimum |
| r2 ranking/freeze | missing-by-design | transport 未通过，因此没有 ranking 或 provider freeze |
| r2 Harness scaffold/binding/audit | trusted-but-blocked | 只生成控制面，不授权 target calls |
| 历史 r1/r5 ranking/freeze | reference-only | 不与 r2 混 cohort，不作为 successor 输入 |
| r3 smoke admission | trusted diagnostic | 单 profile 5/5 workload 返回上游 404，profile 被标记为 ineligible |

## 不可接受的捷径

- 不使用 r2 的 4 个 completed subset 做 ranking 或 superiority claim。
- 不降低 `min_canonical_models=3` 或 transport failure-rate 门禁。
- 不把 smoke 或旧 operational admission 当作新的 formal baseline freeze。
- 不修改 r2 frozen plan，不通过 retry flag 恢复旧 screening，不启动 target Harness。
- 不把缺失的 Harness root、官方 import 或数据 case hash 写成 ready。

## 当前 successor 路线

正在对同一 probe-bound registry 执行一次独立的、非 benchmark 的完整
`operational-admission`。它使用固定 synthetic workload、90 秒 response ceiling、
3 workers、10 profiles，并仅输出 hash-only admission receipt。

### admission ready 分支

1. 校验 `formal_baseline_eligible_count >= 3`、敏感字段均为 `false`，并记录新的
   admission digest。
2. 用该 receipt 创建新的 immutable r3 screening plan；r2 plan 不变。
3. 按 screening → transport admission → external ranking → provider baseline
   freeze 顺序推进，所有 receipt 绑定 r3 registry/plan/state digest。
4. 重新运行 composite Harness scaffold，补齐真实 pinned Harness root、raw root、
   official import 和同 cohort execution plan；convergence audit 未返回
   `ready_for_target_campaign` 前保持禁止 target calls。

### admission blocked 分支

1. 保留完整 admission receipt 与 reason codes，不将部分可用 profile 扩大为 baseline。
2. 以新的 probe/registry successor 重新评估 endpoint、协议和 provider 覆盖，创建
   新 cohort；不编辑或复用 r2 frozen plan。
3. 若连续三轮相同外部 transport blocker，才在 goal 层记录 blocked；单次失败不改变
   goal 状态，继续寻找可验证的 successor。

## 证据边界

本审计只证明控制面路线和当前门禁状态，不证明任何模型质量优越性。最终 goal 仍需
完成同一 cohort 的 21-suite target campaign、三档单模型 baseline、paired statistics、
latency、contamination、四种 API parity、failure analysis 与 final audit。

