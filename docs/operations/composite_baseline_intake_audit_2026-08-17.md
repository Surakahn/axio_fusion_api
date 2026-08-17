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
| r3 full operational admission | trusted | 10 profiles、7 production admitted、4 formal baseline eligible，2 providers，敏感字段均为 `false` |
| r3 screening plan | trusted | 4 canonical groups、4 profiles、2 source families、8 serial units、856 calls，digest `a8400e203ca37a4eb5ddd8a0d3758dd16c4e992ffcd1ad8dc05449eb1b17e706` |
| r3 live screening/supervisor | running | zero-network preflight 已通过；live PID、supervisor、watcher 已绑定同一 plan，target calls 关闭 |

## 不可接受的捷径

- 不使用 r2 的 4 个 completed subset 做 ranking 或 superiority claim。
- 不降低 `min_canonical_models=3` 或 transport failure-rate 门禁。
- 不把 smoke 或旧 operational admission 当作新的 formal baseline freeze。
- 不修改 r2 frozen plan，不通过 retry flag 恢复旧 screening，不启动 target Harness。
- 不把缺失的 Harness root、官方 import 或数据 case hash 写成 ready。

## 当前 successor 路线

同一 probe-bound registry 的独立、非 benchmark `operational-admission` 已完成。它使用
固定 synthetic workload、90 秒 response ceiling、3 workers、10 profiles；safe receipt
只保留 hash-only 诊断，private receipt 仅供严格 profile 绑定，不进入 Git。

### admission ready 分支

1. 已校验 `formal_baseline_eligible_count=4`、敏感字段均为 `false`，并记录新的
   admission digest。
2. 已用该 receipt 创建新的 immutable r3 screening plan；r2 plan 不变。
3. 当前按 screening → transport admission → external ranking → provider baseline
   freeze 顺序推进，所有 receipt 绑定 r3 registry/plan/state digest。
4. r3 composite Harness scaffold 已重新生成；待 screening terminal 后补齐真实 pinned Harness root、raw root、
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
