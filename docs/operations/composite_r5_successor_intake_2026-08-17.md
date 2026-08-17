# Composite r5 Successor Intake（2026-08-17）

## 触发条件

r4 已完整终态但 transport admission blocked：4 个候选 canonical models 中只有 1 个
通过严格 failure-rate 门禁，低于固定最低 3 个。r4 的 plan、state、checkpoint、
transport receipt、Harness binding 和 convergence audit 已全部保留为只读证据；不
恢复 r4、不选 completed subset、不复用 r4 ranking/freeze，也不降低 transport gate。

r4 campaign digest：
`d363897c3cef98a74762d36479ef41bb802e100c660860e06fadf48d5a833012`。

## r5 候选分母阶段

为寻找合规 successor 候选，2026-08-17 通过 `setsid` 启动独立 live
`operational-admission`：

- PID：`2678898`
- registry digest：
  `a98ca935e3b8005b84e26cfc71feb902ad43ecbc3947a4dec6cd7670bc9c17e5`
- timeout：90 秒
- max workers：2
- failure-rate threshold：0.25
- minimum successful workloads：3
- repetitions：1
- max models：10；max models per provider：8
- workload 类型：固定 non-target operational workloads

该阶段只证明 production/transport admission，不读取 benchmark labels、answers 或
scores，也不产生 target-suite calls。结果必须写入 r5 独立 private root；只有
`status=ready` 且 formal baseline eligible canonical model 数至少为 3 时，才允许
基于新 source manifest 创建 immutable screening plan。

## 晋级与恢复规则

1. admission 运行期间只低频检查 PID、日志是否出现参数/导入错误和 safe 状态文件。
2. admission 不足 3 个 formal eligible 时，保留完整失败 receipt，重新设计候选
   分母；不得把 operational admission 当作质量排名。
3. admission 达标后，只改变 successor source manifest 的注册日期和 selection seed，
   生成新的 hash-only receipt；新 plan 必须通过 zero-network preflight，使用
   `max_workers=1` 与 fail-fast transport gate。
4. screening terminal、transport ready、external ranking、provider baseline freeze、
   official Harness import 和 lineage convergence 全部通过前，target calls 与
superiority claim 保持关闭。
