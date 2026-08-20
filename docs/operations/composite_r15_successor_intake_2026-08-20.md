# Composite cohort r15 successor intake（2026-08-20）

## 继任边界

r14 已自然终态为 `partial`：16/16 unit terminal，10 completed、6 failed，ranking
conversion fail-closed。r14 的 state、完整失败分母、transport admission、ranking、
supervisor 和 Harness 控制面全部保留为 reference-only；r15 不读取 r14 score、
transport receipt、ranking、checkpoint 或 survivor subset，不修改 r14 frozen plan，
也不重复 r14 的 provider probe。

r15 只从 r14 source contract 创建 immutable source successor，仅改变注册事件和
selection seed：

- source manifest：`private/runs/2026-08-20-composite-cohort-r15/source_manifest.successor.r15.private.json`；
- source manifest SHA-256：`745312def06231f320c7c9a48dcbd81e6742ee67800d8ecfc9d4d3309d620aec`；
- successor receipt：`private/runs/2026-08-20-composite-cohort-r15/source_manifest_successor_receipt.r15.private.json`；
- successor receipt SHA-256：`d6225343c606035c23175e9c347d48615181fef8397109cb97196f478dac6b82`；
- selection seed：`composite-r15-2026-08-20-transport-successor`；
- selection seed hash：`2ef0171a0d384ca558c6113d72d373d48e3d0f018b7023bc60e8f438511cc29e`；
- registered_on：`2026-08-20`；receipt `status=ready`，raw prompt/label/provider output、
  provider URL 和 secret 持久化标志均为 `false`。

## Frozen plan 与 zero-network preflight

r15 重新生成了完整计划，绑定同一 r7 probe-bound registry 和 r7 operational admission，
没有传入 r14 transport/ranking/freeze：

- plan 文件：`private/runs/2026-08-20-composite-cohort-r15/baseline_screening_plan.r15.private.json`；
- plan 文件 SHA-256：`555350be7d681bd777094804b1936f65f1d05890fe33e87ec56bd6930eb846c3`；
- plan digest：`d41becf244fcf5234d622a95ea95e8898ef94bd9a40d88e2ebef2e0ecaf3b038`；
- registry SHA-256：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- source count/family count：`2/2`；canonical group/profile count：`8/9`；
- `task_count=16`、`minimum_cases_per_source=100`、`max_workers=1`、固定 `2%`
  fail-fast gate、estimated provider calls `1712`；plan `ready=true`。

zero-network preflight 已通过：

- state：`private/runs/2026-08-20-composite-cohort-r15/screening_state.r15.preflight.private.json`；
- state SHA-256：`a83fe140d9e1c5034ce33fa97a3197e3dfa27d3e41bc1e20f7d320f9261e9fd2`；
- receipt：`private/runs/2026-08-20-composite-cohort-r15/screening.preflight.receipt.r15.private.json`；
- receipt SHA-256：`9567866eff71f2e647495587f0ef367e0a7fe561b5724ae0dea8dbbcbcbab5bb`；
- campaign digest：`f9a9d6ebd1bdb9d7e5e271a6f3aaf18a58322e4e29b5f00411f5c1bcbbc44abc`；
- `status=preflight_ready`、`network_calls_performed=false`、
  `target_suite_calls_performed=false`、`reason_codes=[]`。

## Harness 控制面

已在 `private/runs/2026-08-20-composite-cohort-r15/harness_control.successor/` 离线生成
同一 cohort 的控制面。只复用 r14 已验证的 hash-only Harness pin 和 21-suite 定义，
没有复制旧 cohort 的原始 checkout、数据、答案、provider output 或质量结果：

- pin：`22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`，6/6 ready；
- execution plan：`fa5daf29d58136bc473b2fa202739eaf996de2bd8380b48166711ee9a7a8f4a0`，
  `ready_to_execute`；
- acquisition checklist：`ced8636b2b065be9e1bd5c1d07d008c362c4c6d6a41439acc77994f6fd968471`，
  `template_ready`；
- acquisition status：`976c3ae7f155eaa6945e3c6e1b1d146ce28ecd905e69e44d8fde9772e8746011`，
  blocked；
- official import audit：`7fb8996b53b4c783b14f9554a6ac4608c950fa73910159fc2b9331d8d0d4e6bf`，
  blocked；
- cohort binding：`f55655946e11f61e5f6f908fbb23fe4997ea1318a0f7623249dcd96a8e7fe3c4`，
  blocked；
- convergence audit：`37cc50e0704cd9f62b646d4d957b648eb05f56ac368af8cdfcd161823fc3b226`，
  `status=blocked`、`next_gate=screening`；
- scaffold receipt：`5cd3c55e82fe54ad19c560e9a75463c92810c007992ebaaf2b3f336a8368dc72`，
  `target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。

blocked 是预期结果：screening 尚未 terminal，且 transport admission、完整-pool ranking、
provider baseline freeze、official imports 和 same-cohort binding 尚未具备。Harness
命令因此返回控制面的约定 blocked code，但所有 safe artifact 均已原子写入；这不是
provider 或 target benchmark 失败，也不是授权 target 请求。

## 唯一允许的 live 推进

只启动一套 r15 `baseline-screening-run --live`，绑定以下不可变输入：r15 frozen plan、
r15 source successor、r7 probe-bound registry、r7 operational admission 和 r7 private
probe。启动必须使用 `setsid/nohup`、`PYTHONPATH=src`、`max_workers=1`，并在启动后核验
PID、命令行 plan identity、日志和 state 增长；不得使用 `--retry-failed`，不得启动第二
套 screening。screening terminal 前禁止 transport conversion、ranking、freeze、official
import 和 target campaign。

terminal 后严格执行：

```text
transport admission -> complete-pool ranking -> external rank 1/2/3 evidence
-> provider baseline freeze -> same-cohort official/audited import
-> convergence audit -> 21-suite target campaign
-> paired statistics/latency/API parity/contamination/final audit
```

任何 gate 失败都保留完整分母并注册新的 immutable successor；不选择 completed subset，
不降低 2% gate，不将 benchmark 输出写入生产路由学习闭环，在全部证据完成前不做
superiority claim。

## r15 live screening 启动里程碑（2026-08-20 12:12 CST）

r15 唯一 live non-target screening 已通过 `setsid/nohup` 启动：screening PID
`2871629`、convergence supervisor PID `2880595`、lineage watcher PID `2881730`。三者
均由 init 托管，screening 命令行持续绑定 r15 frozen plan、r15 source successor、r7
probe-bound registry、r7 provider probe 和 r7 operational admission，没有并发第二套
screening。

启动后的低频核验确认：

- screening 进程存活，已进入首个 serial unit 的真实 provider 调用；
- private checkpoint 已出现并从 `9/112` 推进到 `21/112`，safe terminal state 尚未写出；
- supervisor 仍在同一 PID/plan identity wait，watcher 已生成 `status=blocked`、
  `next_gate=screening`、`target_suite_calls_allowed=false` 的初始 audit；
- transport admission、ranking、provider freeze、official import 和 target campaign
  均未启动，当前没有任何 superiority evidence。

screening 仍在运行时不恢复 checkpoint、不使用 `--retry-failed`、不修改 frozen plan、不
启动第二套 screening。后续状态只按 10-20 分钟低频检查；首个 unit terminal 后才记录
准确的 completed/failed 分母并允许 supervisor 执行离线 transport admission 和完整池
ranking。
