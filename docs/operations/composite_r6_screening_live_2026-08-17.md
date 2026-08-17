# Composite r6 Live Screening 里程碑（2026-08-17）

## 固定输入

r6 使用 r6 独立 operational admission 生成新的 immutable screening plan，不修改
r4/r5 plan，也不复用历史 ranking/freeze：

- registry digest：
  `a98ca935e3b8005b84e26cfc71feb902ad43ecbc3947a4dec6cd7670bc9c17e5`
- source manifest digest：
  `cb52811b4b6cab984d435d5904920b4e9e6a94a7be51416f16b88acd4c388958`
- plan digest：
  `601b8fdd52cfc50fba49e853293754a7d887ab0632fe7a005bd82245c8ccf283`
- canonical groups：4
- serial units：8
- 预计 provider calls：856
- `max_workers`：1
- minimum cases per source：100
- fail-fast transport gate：启用
- operational admission receipt digest：
  `34982c68d02cc709df4fd1c68d99fa9421db0ac0488d661c4d69e68eb9b3c0c9`

zero-network preflight 已通过：`status=preflight_ready`、8 个 planned tasks、
`network_calls_performed=false`、`target_suite_calls_performed=false`。

## 运行控制面

2026-08-17 通过 `setsid` 启动三个同 cohort 角色：

- screening：PID `2778713`
- convergence supervisor：PID `2781215`
- hash-only binding/audit watcher：PID `2786116`

screening 只执行 non-target provider screening；supervisor 等待 terminal 后按顺序
执行 transport admission 和 ranking conversion；watcher 每 300 秒重建 binding 并
运行 convergence audit。三者都不会恢复旧 cohort、修改 frozen plan 或启动 target
Harness。

## Harness 控制面

r6 已从本地已验证的 official Harness roots 离线生成独立 pin、acquisition
checklist、import template、execution plan 和 official import audit。首轮 audit 因
screening 尚未 terminal、ranking/freeze/import 缺失而 blocked；`target_suite_calls_allowed`
保持 `false`。这些 control artifacts 只保存 schema、计数、digest 和 reason code，
不包含 raw dataset、prompt、label、provider output 或凭据。

## 后续门禁

screening 必须完整 terminal 且 transport admission 至少保留 3 个 canonical models，
之后才允许 ranking、provider baseline freeze、official Harness import 和 lineage
convergence；在 audit 返回 `ready_for_target_campaign` 之前不得产生 target 请求或
superiority claim。
