# Composite r11 screening live 运行记录（2026-08-19）

## 启动绑定

r11 已在 source successor、immutable plan 和 zero-network preflight 均 ready 后启动
live non-target screening。启动使用 `setsid nohup`，未恢复 r10 checkpoint，未传
`--retry-failed`，未启动 target：

- screening PID：`3316149`；
- convergence supervisor PID：`3321068`；
- lineage watcher PID：`3321069`；
- registry：r7 probe-bound registry，SHA-256
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- plan：r11 plan digest
  `0a81e8629a0fb6948541dc3fec3d2db828b18fa7df808cf509dc5c6e69fd8aef`，文件 SHA-256
  `6bee0935c72f0f0f718bd1fb51bb5708ad245a18a2141707353538e81b81a728`；
- source manifest：SHA-256
  `ab15c0149dd85372682bc00a059096e3f884dcc71b58d1dfe391d601cce97a52`。

三进程命令行均绑定 `baseline_screening_plan.r11.private.json`；supervisor 只执行
terminal 后的 transport/ranking 转换，watcher 只写同 cohort hash-only binding/audit。

## 当前运行态

当前 state 文件 SHA-256：
`1a2de75ec2e0301541b0aaec74c422b4f230e47f290f13bc87afa5ede3fe327f`。

- schema：`axio_fusion_api.non_target_screening_campaign.v3`；
- `status=running`、`planned_task_count=16`、`completed_unit_count=0`、
  `failed_or_blocked_unit_count=1`；
- `network_calls_performed=true`（仅表示 non-target screening provider 流量）；
- `target_suite_calls_performed=false`、`ready_for_ranking=false`；
- state/plan/registry/source digest 绑定保持稳定，safe 控制面不持久化 raw provider
  output、prompt、label 或 secret。

首个 serial unit 已按预注册 fail-fast policy 终态失败：完整分母 112，transport failure
112，failure rate 1.0，3 次上游 HTTP 500 后 fail-fast，109 个未尝试 case 仍计入失败
分母。该 unit 不会恢复、重试或与其他 unit 拼接。

第二个 serial unit 的 private checkpoint 当前已完成 41/102 个 case；checkpoint 仅在
operator-owned private root 保存恢复所需原始数据，safe receipt 不复制这些内容。

lineage watcher 当前 audit SHA-256：
`5c760a206002e2c8ff7c688cf9055a9ca117d9f92b0354ac5cc90972c3e58372`，状态仍为
`running`、`next_gate=screening`、`target_suite_calls_allowed=false`。screening terminal
前不生成 transport admission、ranking、provider baseline freeze、official import 或
target 请求。

## 2026-08-19 06:48（CST）第二个 serial unit 完成

第二个 serial unit 已自然终态：完整分母 `102/102`，transport failure `0`，failure rate
`0.0`，unit 状态为 `completed`。第一个 unit 仍为 `failed`（112/112 transport failure，
109 个 fail-fast 未尝试 case），两者均继续保留完整分母和私有 checkpoint 证据。

campaign state 当前为 `status=running`、`completed_unit_count=1/16`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 已更新为
`5eceb3f65cf1b432488a38da95295395c209cc5bf26a5861811eb525d758a236`。运行器已进入第三个
112-case serial unit，screening/supervisor/watcher 均仍存活，target gate 不变。

## 固定后续顺序

```text
screening terminal -> transport admission (failure-rate only)
-> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit
-> ready_for_target_campaign -> 21-suite target
```

若 r11 仍为 partial 或 complete-pool ranking 被拒绝，保留完整分母并创建新的 immutable
successor；不降低固定 3-model gate，不选择 completed subset，不声明 superiority。
