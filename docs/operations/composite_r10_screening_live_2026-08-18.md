# Composite r10 screening live 运行记录（2026-08-18）

## 启动门禁与绑定

r10 已通过独立 source successor、immutable plan 和 zero-network preflight 后启动
live non-target screening。启动使用全新 r10 live state/private root：

- screening PID：`2281133`，命令行持续包含 `baseline_screening_plan.r10.private.json`；
- supervisor PID：`2283494`，仅等待 terminal 后执行 transport admission/ranking；
- lineage watcher PID：`2284301`，只重建同 cohort hash-only binding/audit；
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
unit 已完整执行并安全归档：102/102 个 case 中 101 个正常完成、1 个 transport
failure，完整失败分母已保留。campaign live state 已物化为 `running`，当前
`completed_unit_count=1/16`、`failed_or_blocked_unit_count=0`；第二个 serial unit
已启动并进入 provider 调用，其活动 checkpoint 当前为 1/112。checkpoint 只在
operator-owned private root 保存 provider 原始恢复数据，safe receipt 不包含这些内容。
screening 尚未达到 campaign terminal，`ready_for_ranking=false`；当前进度不产生
ranking、provider freeze 或质量结论。

supervisor 当前事件为 `screening_wait_started`，watcher 当前为
`next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。screening 期间禁止 ranking、provider freeze、
official import 和 target campaign。

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
