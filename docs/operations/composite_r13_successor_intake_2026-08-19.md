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

## r13 screening 进度快照（2026-08-19 18:59 CST）

第四个 `mmlu-pro` unit `e2314df494955a51d8254373eece6ccc4aa518a22f615be36ffac399b8ccfa9e`
已自然终态并完成 `112/112` case，`scored_case_count=112`、transport failure
`0/112`、mean score `0.785714285714`、p95 latency `48656.944ms`，reason codes 为空。
campaign 当前为 `status=running`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`；state 文件 SHA-256 为
`5fdb98d099336d6e45f7e55b6c61d0c9e630efc4c099c946f3d77ec7a9334165`，campaign digest 为
`e0055ba70ba099913433bf9b87289cad65c3f423663e74621c0a5c1548155fdd`。运行器已自动进入
第五个 task `d18c4a89ea4965086cd4c567b86bb24fafb013c5c1b1cb289e7a1d01869172d8`，checkpoint
为 `1/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 19:28 CST）

第五个 task `d18c4a89ea4965086cd4c567b86bb24fafb013c5c1b1cb289e7a1d01869172d8`
已自然终态并完整完成 `102/102` case，`scored_case_count=102`、transport failure
`0/102`、mean score `0.71568627451`、p95 latency `44492.815ms`，reason codes 为空。
campaign 当前为 `status=running`、`completed_unit_count=2`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`；state 文件 SHA-256 为
`a2d3f296ebca5cbdfc810dec965453142fc89da7b0f93fd52e23f6096124f71e`，campaign digest 为
`7c74f960c37434dcb8d6cc5f74e5961fc358eafa37ca604018f5566c6e8168fc`。运行器已自动进入
第六个 task `5f2f5361b9f6d92cdf4ab790d5c7a3c262906180ae298cd325b04c0966d79d49`，checkpoint
为 `0/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 19:36 CST）

第六个 task `5f2f5361b9f6d92cdf4ab790d5c7a3c262906180ae298cd325b04c0966d79d49` 已自然
终态失败：完成 `19/112` case，`scored_case_count=19`、transport failure `93/112`、
failure rate `0.830357142857`，触发冻结 `2%` fail-fast gate，未尝试 case `90`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=2`、`failed_or_blocked_unit_count=4`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`35d350c68aee93a22b1d515e03e9bb3c718f95cde6b4029fa822b2f0c4fa5b53`，campaign digest 为
`ceec8c01f4d5378c63b7bf1c8f4cc771d41648d63773fcc9b188afeb31cd4f38`。运行器已自动进入
第七个 task `e454627f2fc43c1ca1fbd8a277e9eaceed72122beb138f3a13501b5dc492dfb1`，checkpoint
为 `4/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 19:55 CST）

第七个 task `e454627f2fc43c1ca1fbd8a277e9eaceed72122beb138f3a13501b5dc492dfb1` 已自然
终态完成 `102/102` case，`scored_case_count=101`、transport failure `1/102`、failure
rate `0.009803921569`，低于冻结 `2%` gate，未触发 fail-fast，reason codes 为空；mean
score 为 `0.792079207921`，p95 latency 为 `21217.921ms`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=4`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`66002ac4f8738bc45540a12f8f4e36e73e598d32f7bcdd3df22666850580bd24`，campaign digest 为
`f7ae7602d28aef92ec652667983b2abc95590d072169b1afe53e53fa9828c51b`。运行器已自动进入
第八个 task `de836731b675337719ab0b8d539264fbcf753a685f54cbe4680ebd3235fe6c0d`，checkpoint
为 `16/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 20:16 CST）

第八个 task `de836731b675337719ab0b8d539264fbcf753a685f54cbe4680ebd3235fe6c0d` 已自然
终态失败：完成 `95/112` case，`scored_case_count=95`、transport failure `17/112`、
failure rate `0.151785714286`，触发冻结 `2%` fail-fast gate，未尝试 case `14`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`400f0222c1b2d0b6f97d3a6c2c27d9b5f04a5a924c4eb92f1e23a613e5fc4329`，campaign digest 为
`d73e800cf7d35b28b52966635a9edc0826d6c97c8f59ed4b0966e3b3b9b7d40a`。运行器已自动进入
第九个 task `7a79b67ec4705c8a65079c56d0f5c7c103df5674573f8120f9a406fe44865b69`，checkpoint
为 `5/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 20:19 CST）

第九个 task `7a79b67ec4705c8a65079c56d0f5c7c103df5674573f8120f9a406fe44865b69` 已自然
终态失败：完成 `17/102` case，`scored_case_count=17`、transport failure `85/102`、
failure rate `0.833333333333`，触发冻结 `2%` fail-fast gate，未尝试 case `82`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=6`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`9ebf1f6b62fcc2e0336353ffd2cfabc8afa1b58c42dcdee440ae5897e5160c5e`，campaign digest 为
`146f1638961548894c6495ae67ae1f5c9bba7e0daa176f322c7a28971458690b`。运行器已自动进入
第十个 task `f3dc7761386b6884797bf1c35717312f38664954d717b8e7c4f6b35018af6e74`，checkpoint
为 `11/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 20:26 CST）

第十个 task `f3dc7761386b6884797bf1c35717312f38664954d717b8e7c4f6b35018af6e74` 已自然
终态失败：完成 `46/112` case，`scored_case_count=46`、transport failure `66/112`、
failure rate `0.589285714286`，触发冻结 `2%` fail-fast gate，未尝试 case `63`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=7`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`a1cb6e99c0149e75467a1999b13dfa80e0925c63c38fcc8b5eecd3317285d906`，campaign digest 为
`0d41f1c1c80115eaf72dc75458460f5de4f1da1fd87e12a7b868e43e9d272281`。运行器已自动进入
第十一个 task `5f9fade1c7264f69ddf84df791ffcb14e68583cfae09e587188b226460a767f8`，checkpoint
为 `4/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 20:32 CST）

第十一个 task `5f9fade1c7264f69ddf84df791ffcb14e68583cfae09e587188b226460a767f8` 已自然
终态失败：完成 `20/102` case，`scored_case_count=20`、transport failure `82/102`、
failure rate `0.803921568627`，触发冻结 `2%` fail-fast gate，未尝试 case `79`，reason
code 为 `screening_unit_transport_failure_rate_exceeded`。campaign 当前为
`status=running`、`completed_unit_count=3`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`b7645cc24a656413d0b9308bba647cce02f633974212b46b0271d60c62667686`，campaign digest 为
`f901510ca3a6dda7ca28bdbb06aff32b48e0747da9a752dbc143f1465bed077a`。运行器已自动进入
第十二个 task `bdbd40764ece9402d2752a6d981ce7020c7857460e321b5f270c16bc7b99856c`，checkpoint
为 `8/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 21:17 CST）

第十二个 task `bdbd40764ece9402d2752a6d981ce7020c7857460e321b5f270c16bc7b99856c` 已自然
终态完成 `112/112` case，`scored_case_count=112`、transport failure `0/112`、mean
score `0.767857142857`、p95 latency `51575.264ms`，reason codes 为空。campaign 当前为
`status=running`、`completed_unit_count=4`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`c87bfcdd8f758ccb56ce80a2db04ba019051a2eb41297ea9404ff9e73f36ccfc`，campaign digest 为
`cb3be7eebf821474fce222f07313d4cd2aaa8100c324fb8ed409df0a5eb6b8d2`。运行器已自动进入
第十三个 task `eed40af9b25c169eb5ff7b7de83943be78ab5b14d9791308614fecaf2b8854f3`，checkpoint
为 `2/102`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。

## r13 screening 进度快照（2026-08-19 21:54 CST）

第十三个 task `eed40af9b25c169eb5ff7b7de83943be78ab5b14d9791308614fecaf2b8854f3` 已自然
终态完成 `102/102` case，`scored_case_count=102`、transport failure `0/102`、mean
score `0.686274509804`、p95 latency `56237.749ms`，reason codes 为空。campaign 当前为
`status=running`、`completed_unit_count=5`、`failed_or_blocked_unit_count=8`、
`ready_for_ranking=false`；state 文件 SHA-256 为
`67345d30ea83ec80fe5d6dc11bd14c36d0fe43bd06d544c310e9536e9f114acf`，campaign digest 为
`1fda9f13aeb4ae2de310a7d2dab2c67427a726eaff522888a2b9eb4a90d07dd8`。运行器已自动进入
第十四个 task `011b349563db08a3004d4a1411c92a5b4275c46cfddaea18e395701dc5bace3f`，checkpoint
为 `6/112`；不修改 frozen plan、不拼接 completed subset，target gate 继续关闭。
