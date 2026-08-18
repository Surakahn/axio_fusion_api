# Composite r10 screening live 运行记录（2026-08-18）

## 启动门禁与绑定

r10 已通过独立 source successor、immutable plan 和 zero-network preflight 后启动
live non-target screening。启动使用全新 r10 live state/private root：

- screening PID：`2281133`，命令行持续包含 `baseline_screening_plan.r10.private.json`；
- supervisor PID：`2283494`，仅等待 terminal 后执行 transport admission/ranking；
- lineage watcher 当前 PID：`2365523`，只重建同 cohort hash-only binding/audit；旧 PID
  `2284301` 已在 audit 修复后退出，screening 与 supervisor 未重启；
- registry：当前 r7 probe-bound registry，文件 hash
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- plan：r10 plan digest
  `f779424f4d6846de97a24da8d5c15ebbce2253c53bca592ccba7ac5b0564cfa8`；
- source manifest：`source_manifest.successor.r10.private.json`；
- private probe：r7 provider probe private artifact，唯一 probe set 与 r10 identity
  attestation 对齐；
- operational admission：r7 `operational_admission.r7.private.json`；
- 执行约束：`max_workers=1`、2 source families、16 serial units、fail-fast transport
  gate；未传 `--retry-failed`，未读取旧 cohort checkpoint。

## 当前进度

启动命令使用 `setsid nohup`，screening 与两个监督进程均已脱离终端托管。首个 serial
已有三个 serial unit 完整执行并安全归档：一个为 112/112 且 0 个 transport failure，
一个为 102/102 且 1 个 transport failure 并完成，另一个为 102/102 且 102 个
transport failure 并以 `screening_unit_no_scores`、
`screening_unit_transport_failure_rate_exceeded` 失败；完整失败分母均已保留。
截至 2026-08-18 23:50（CST），campaign live state 仍为 `running`，
`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`；第四个 serial unit
仍在执行，其活动 checkpoint 已推进至 26/112。checkpoint 只在
operator-owned private root 保存 provider 原始恢复数据，safe receipt 不包含这些内容。
screening 尚未达到 campaign terminal，`ready_for_ranking=false`；当前进度不产生
ranking、provider freeze 或质量结论。

supervisor 当前事件为 `screening_wait_started`，watcher 当前为
`next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。screening 期间禁止 ranking、provider freeze、
official import 和 target campaign。

watcher 已加载 `4d1abd6` 的审计修复；在 state 尚未物化的早期窗口，后续快照不再把
`artifact_missing` 误报为 `screening_target_suite_calls_present`。

## 2026-08-19 00:16（CST）低频进度快照

- 三个后台 PID 仍存活，screening 命令仍绑定 `baseline_screening_plan.r10.private.json`；18900 服务只读健康检查仍为 `ready`。
- campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`。
- 当前活动 checkpoint 为 `0af6bdbc99f0dde29090bf1b0373393cc6f0a8fa488fdffb1e8495db9921aeac`，`expected_case_count=112`，已完成 `71/112`，已完成 case 的 transport failure 为 0；checkpoint 文件 mtime 在本快照前持续更新。
- 已完成 unit 的失败分母不变：`112/112` 且 0 失败、`102/102` 且 1 失败；失败 unit `102/102` 且 102 失败，完整失败证据继续只读保留。
- supervisor 仍只等待 terminal；watcher 的当前 gate 仍为 `screening`，target、ranking、provider freeze 和 official import 均未启动。

## 2026-08-19 00:23（CST）低频进度快照

活动 checkpoint 已自然推进至 `84/112`，其中 84 个 case 均为 completed，当前 checkpoint 未出现 transport failure。campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`；transport admission、ranking、provider freeze 和 screening receipt 仍未生成。

## 2026-08-19 00:29（CST）低频进度快照

活动 checkpoint 已推进至 `94/112`，94 个已完成 case 均为 completed，当前 checkpoint 未出现 transport failure。campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`；supervisor 仍只等待 terminal，所有后置转换保持关闭。

## 后续顺序

保持低频监控，等待 screening 自然终态；随后按固定顺序执行：

```text
terminal screening -> transport admission (至少 3 canonical models)
-> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit
-> target campaign
```

任何 partial/transport-blocked 终态都保留完整失败分母并创建新的 successor，不恢复本
次 checkpoint、不拼接 completed subset、不降低 3-model gate。只有 convergence audit
明确返回 `ready_for_target_campaign` 才允许 target 请求或 superiority claim。
