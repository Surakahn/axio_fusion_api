# Composite cohort r13 successor intake（2026-08-19）

r12 已完整 terminal，但 campaign 为 `partial`，complete-pool ranking 被拒绝。r12
所有 state、unit、transport、ranking、supervisor、Harness binding 和 convergence audit
均保留在其私有 run root 中，仅作 reference-only 证据；不恢复 checkpoint、不拼接
completed subset、不降低 transport gate。

## r13 immutable intake

r13 只从 r12 source contract 创建新的 source successor，改变 selection seed 和注册事件：

- source manifest 文件 SHA-256：
  `762e4a63d5d36e3996c710b7f77608b494d4507ace314bdf3bcc16acdce43e94`；
- selection seed hash：
  `f8a35d8235338707976f2509d464fb0d35aae44f31d42f780679378d55373012`；
- frozen plan 文件 SHA-256：
  `fde4aa68dd56eb4a724e2bb90fe7a199ed009b5b1a84928b4caa57e0da341d05`；
- plan digest：
  `899f3cb3f7539ec0789458f21a85be7357042e0cb7275a171ba16ea40d030f97`；
- 16 serial units、2 independent source families、8 canonical groups/9 profiles、
  `max_workers=1`、固定 `2%` fail-fast 和最低 `3` canonical models。

## Zero-network preflight

r13 preflight state 文件 SHA-256 为
`2ea7331d352cda4d00e2c9c0e305e7489e477c26a2e9714a489ffd2060cd2fba`，campaign digest
为 `36700ea5b5ab8c1eb781de9f319913c7fc9b127c11f8076dd88c3c9b0d2e1df0`。preflight
状态为 `preflight_ready`，`network_calls_performed=false`、
`target_suite_calls_performed=false`，9/9 operational profiles credential-ready，
无缺失 endpoint binding、无缺失 key/base URL，敏感字段均为 false。

## 推进顺序

```text
r13 live non-target screening
-> terminal transport admission (failure-rate only)
-> complete-pool ranking
-> provider baseline freeze
-> same-cohort official import
-> convergence audit ready_for_target_campaign
-> 21-suite target campaign
```

只有完整 r13 cohort 通过所有前置门禁后才允许 target 请求；在此之前不做 superiority
claim，不选择 completed subset，不修改 frozen plan。

## r13 live screening 启动里程碑（2026-08-19 17:41 CST）

r13 唯一 live non-target screening 已通过 `setsid/nohup` 启动：screening PID
`566502`、supervisor PID `567189`、watcher PID `567994`。三者命令行均绑定同一个
immutable r13 frozen plan。首个 `livebench_official_final_text_slice` checkpoint task
为 `27fed11add78ea40a3dd7bba83f11272bb8a77bf6b48f514b563705dd3a27395`，已完成 `11/102`
case，状态为 `partial`；screening state 尚未完成首个 unit，supervisor/watcher 继续
关闭 transport/ranking/freeze/import 和 target gate。不修改 frozen plan、不重试 case。

## r13 screening 进度快照（2026-08-19 17:53 CST）

r13 首个 `livebench_official_final_text_slice` unit 已自然终态失败：task
`27fed11add78ea40a3dd7bba83f11272bb8a77bf6b48f514b563705dd3a27395` 完成完整 `102/102`
case，transport failure rate 为 `0.676470588235`，按冻结 `2%` fail-fast gate 拒绝。
campaign state 当前为 `status=running`、`completed_unit_count=0`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，state 文件 SHA-256 为
`99a039c53ad97b7a4f33758dfd686420e8a806d39cb431a251d77bbf54b01835`，campaign digest 为
`64c9115a5cd0042cb23e2062f90e1b1cb7852601160acc3fb6d8d6d856d84ff6`。第二个 task
`d7e62dcf7e03031924cdba38ac78d78e5fd094d031e378c4fbeacae7eb383ecf` 已创建 `0/102`
checkpoint；`retry_round_count=0`，不修改 frozen plan、不拼接 completed subset。

## r13 screening 进度快照（2026-08-19 18:50 CST）

r13 已推进至 `0 completed / 3 failed`，campaign 仍为 `status=running`、
`planned_task_count=16`、`ready_for_ranking=false`。前三个 terminal unit 的 transport
failure rate 分别为 `0.676470588235`（102 case）、`1.0`（112 case）和
`0.333333333333`（102 case），均由冻结 `2%` fail-fast gate 拒绝；其中后两个记录
`screening_unit_no_scores`。state 文件 SHA-256 为
`fcb9c806830a59a6a8c11805abf7d9c327490c7db8c0f56a544071a3a611d78a`，campaign digest 已更新为
`9bcb44be4d442a34dffed1066f2a3657c244aaa53e2287f8e7c9dcd3a33c8ae2`。第四个 task
`e2314df494955a51d8254373eece6ccc4aa518a22f615be36ffac399b8ccfa9e`（`mmlu-pro`）当前
checkpoint 为 `87/112`，已完成 case 暂未出现 transport failure；所有 unit
`retry_round_count=0`，不修改 plan、不拼接 completed subset。supervisor 与 watcher
仍保持 `next_gate=screening`、`target_suite_calls_allowed=false`。
