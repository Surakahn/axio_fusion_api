# Composite r6 Admission Retry（2026-08-17）

## 触发与边界

r5 对完整 10-profile registry 的 live operational admission 只有 1 个 formal
baseline eligible，未达到固定 3-model minimum，因此没有创建 screening plan。r5
receipt 和所有历史 cohort 继续只读保存；本次 r6 是新的 independent admission，
不复用任何历史排名、分数、completed subset 或 baseline freeze。

## 当前运行

2026-08-17 通过 `setsid` 启动完整候选分母的 live admission：

- PID：`2715833`
- registry digest：
  `a98ca935e3b8005b84e26cfc71feb902ad43ecbc3947a4dec6cd7670bc9c17e5`
- candidate profiles：10
- timeout：90 秒
- max workers：1
- failure-rate threshold：0.25
- minimum successful workloads：3
- repetitions：1
- workload：固定 non-target operational workloads

单 worker 用于降低同一上游 channel 的并发竞争，同时保持完整候选分母；该阶段不
调用 benchmark、不生成 screening/ranking、不启动 Harness target。输出写入 r6
独立 private root，只有全部 profile/workload 完成后才原子生成 receipt。

## 晋级门禁

只有 r6 receipt 为 `status=ready` 且 formal baseline eligible canonical model 数至少
为 3，才会生成新的 successor source manifest、baseline screening plan 和
zero-network preflight。若仍不足 3，保留失败 receipt 并转向新的 probe-bound
candidate registry；不得放宽 threshold 或把 admission 结果解释为质量排名。
