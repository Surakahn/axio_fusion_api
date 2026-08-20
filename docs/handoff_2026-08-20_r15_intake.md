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
