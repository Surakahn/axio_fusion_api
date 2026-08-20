# r15 intake 交接（2026-08-20）

## 已完成

- r14 已封存为 `partial`，不再恢复或补跑。
- r15 source successor、frozen screening plan、zero-network preflight 和 Harness scaffold
  已生成并 hash 绑定。
- r15 preflight 明确 `network_calls_performed=false`、`target_suite_calls_performed=false`；
  Harness 明确 `next_gate=screening`、`target_suite_calls_allowed=false`。

## 当前锚点

- r15 run root：`private/runs/2026-08-20-composite-cohort-r15/`
- plan：`baseline_screening_plan.r15.private.json`，文件 SHA-256
  `555350be7d681bd777094804b1936f65f1d05890fe33e87ec56bd6930eb846c3`，digest
  `d41becf244fcf5234d622a95ea95e8898ef94bd9a40d88e2ebef2e0ecaf3b038`
- source：`source_manifest.successor.r15.private.json`，SHA-256
  `745312def06231f320c7c9a48dcbd81e6742ee67800d8ecfc9d4d3309d620aec`
- preflight state SHA-256：
  `a83fe140d9e1c5034ce33fa97a3197e3dfa27d3e41bc1e20f7d320f9261e9fd2`
- probe-bound registry SHA-256：
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`
- operational admission SHA-256：
  `bf6db0c659b728a6d4c0a8e5d99c1fb9b66e1f70ec96977de048fd393c77af12`

## 当前运行

唯一 r15 `baseline-screening-run --live` 已启动并由 `setsid/nohup` 托管：screening PID
`2871629`、supervisor PID `2880595`、lineage watcher PID `2881730`。三者命令行持续绑定
r15 plan/source 与 r7 registry/probe/admission，没有第二套 screening。

截至 2026-08-20 12:25 CST，首个 serial unit checkpoint 为 `27/112`、状态 `partial`；safe
live state 尚未到 terminal，故不能填写 completed/failed unit 计数。supervisor 仍等待
terminal，watcher 的 convergence audit 为 `blocked`、`next_gate=screening`、
`target_suite_calls_allowed=false`。transport admission、ranking、provider freeze、
official import 和 target campaign 均未启动。

## 12:35 CST 低频进度复核

截至 2026-08-20 12:35:08，screening PID `2871629`、supervisor PID `2880595`、lineage
watcher PID `2881730` 均存活，命令行仍绑定同一 r15 frozen plan/source 与 r7
registry/probe/admission。首个 serial unit 的 private checkpoint 已推进到 `48/112`，
`checkpoint_status=partial`，文件 SHA-256 为
`803226be75520e912374c14e0e622a63292f623a9e0ca530d94dc982edb49016`；safe
`screening_state.r15.live.private.json` 仍不存在，因此完整 campaign 的
`completed_unit_count`、`failed_or_blocked_unit_count` 和 `ready_for_ranking` 仍不可宣告。
transport admission、ranking、provider freeze、official import 与 target campaign 产物均
不存在，后置 gate 保持关闭。本次只追加状态记录，没有恢复 checkpoint、重试 case、修改
frozen plan 或启动第二套 screening。

后续仅做 10-20 分钟低频 PID/state/log 检查，不重试失败 case、不恢复 checkpoint、不修改
frozen plan。screening terminal 后由同 cohort supervisor 执行 transport admission 和
完整-pool ranking；只有 ranking ready 才能继续 external rank 1/2/3、provider freeze、
official import、convergence audit 和 target campaign。任何未通过都必须注册下一个
successor，不能宣称 Fusion superiority。

## 13:34 CST 阶段性终态分母复核

截至 2026-08-20 13:34:09，r15 safe live state 已首次写出，但 campaign 仍为
`status=running`，不是 screening terminal：`planned_task_count=16`、
`completed_unit_count=1`、`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`。
已完成的两个失败 unit 保留完整分母：一个为 `80/102` transport failures（failure rate
`0.78431372549`），另一个为 `112/112` transport failures（failure rate `1.0`）；两者均
触发冻结的 `2%` fail-fast gate。当前已进入下一个 102-case unit，private checkpoint 为
`42/102`、状态 `partial`，尚无 `screening.live.receipt.r15.private.json`、transport
admission 或 ranking 产物。state 的 plan/source/registry hash 继续绑定 r15 frozen
plan/source 与 r7 probe-bound registry，`network_calls_performed=true`、
`target_suite_calls_performed=false`，后置 gate 继续关闭。

## 13:37 CST 低频进度复核

截至 2026-08-20 13:37:17，r15 safe live state 已更新为 `status=running`、
`planned_task_count=16`、`completed_unit_count=1`、`failed_or_blocked_unit_count=3`、
`ready_for_ranking=false`；state SHA-256 为
`698ce13d3b1cf3e8f57c22c074da3be554cdd3e99e7bdd792d8182ce2f2114a5`。新增 failed unit 的
完整分母为 `42/102` scored/transport split，即 `60/102` transport failures、failure rate
`0.588235294118`，同样触发固定 `2%` fail-fast；先前 `80/102`、`112/112` 失败分母和
唯一 `112/112` completed unit 均保留。当前 checkpoint 已切换到新的 112-case unit，
`0/112`、状态 `partial`；screening receipt、transport admission、ranking、freeze/import/
target 产物仍不存在，`target_suite_calls_performed=false` 不变。三个 init 托管进程仍存活，
本次未恢复 checkpoint、未重试失败 case、未修改 frozen plan、未启动第二套 screening。

## 12:45 CST 低频进度复核

截至 2026-08-20 12:45:18，r15 screening PID `2871629`、supervisor PID `2880595` 和
lineage watcher PID `2881730` 仍存活，命令行 plan identity 未改变。首个 serial unit 的
private checkpoint 已推进到 `68/112`，`checkpoint_status=partial`，文件 SHA-256 为
`3aafaf214d732dfa72b0f323a9087a347284dad5fce0afd0b4855ae8e81beef6`；safe live state
仍不存在，完整 campaign 分母和 `ready_for_ranking` 仍不可宣告。transport admission、
ranking、provider freeze、official import 与 target campaign 产物均不存在，
`next_gate=screening`、`target_suite_calls_allowed=false` 保持不变。本次没有恢复
checkpoint、重试 case、修改 frozen plan 或启动第二套 screening。

## 13:48 CST 低频进度复核

截至 2026-08-20 13:48:48，三个 init 托管进程仍存活，r15 命令行绑定未改变。safe live
state 仍为 `status=running`、`planned_task_count=16`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=7`、`ready_for_ranking=false`；state SHA-256 为
`b27bee06ab1e75a97ce7f34b087bf570dad7105497cfca7dfedf88cbf55b6eea`。当前已有 8/16
unit 写入 state：唯一 completed unit 保留 `112/112`、transport failure `0`；7 个 failed
unit 的完整分母均保留，具体为 `112/112`（3 个）、`102/102`（2 个）、`80/102` 和
`60/102`，全部超过冻结的 `2%` transport fail-fast gate。它们只属于 transport evidence，不是能力
分数、survivor subset 或 ranking 结果。

screening 已进入第 9 个 serial unit，task 为
`23d2aad8799078241760998a00ba2db1e3852b2503cfbe087bcde2c1e4cbe154`，private checkpoint
当前 `0/112`、`checkpoint_status=partial`，checkpoint SHA-256 为
`41f510d86b234361e7543d56668e00735f1312c239426ebe2888fc3bc2bcdbb0`。尚无
`screening.live.receipt.r15.private.json`、transport admission 或 ranking 产物；
`target_suite_calls_performed=false`、`next_gate=screening` 和
`target_suite_calls_allowed=false` 继续成立。此次只追加只读进度记录，没有恢复
checkpoint、重试失败 case、修改 frozen plan 或启动第二套 screening。
