# Composite cohort r15 successor intake（2026-08-20）

## r15 最终终态与 successor 路由

r15 已在 14:42 CST 自然终态：16/16 unit terminal，screening receipt 为 `partial`，1
completed、15 failed；14:47 CST supervisor 完成 transport admission，结果为 `blocked`，
`eligible_canonical_model_count=0`、最低要求为 3，唯一 blocker 为
`transport_admission_fewer_than_minimum_models`。ranking、provider baseline freeze 和
target benchmark 均未启动，完整失败分母保留为 reference-only。

正确动作是注册新的 immutable r16 successor，而不是恢复或拼接 r15。r16 生成、preflight
与 Harness 控制面见 [r16 successor intake](</home/he/axio_fusion_api/docs/operations/composite_r16_successor_intake_2026-08-20.md>)。

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

## r15 live screening 进度快照（2026-08-20 12:25 CST）

screening PID `2871629`、supervisor PID `2880595`、watcher PID `2881730` 仍然存活，命令
行 plan identity 未改变。首个 serial unit 的 private checkpoint 已推进到 `27/112`，
checkpoint 状态仍为 `partial`；safe `screening_state.r15.live.private.json` 尚未写出，
因此 completed/failed unit 计数仍不可宣告。transport admission、ranking、freeze、official
import 和 target campaign 产物均不存在，supervisor/watcher 继续保持
`next_gate=screening` 与 `target_suite_calls_allowed=false`。

## r15 live screening 进度快照（2026-08-20 12:35 CST）

低频只读核验显示三个 init 托管进程仍存活且 plan identity 未改变。首个 serial unit 的
private checkpoint 为 `48/112`、`checkpoint_status=partial`，checkpoint SHA-256 为
`803226be75520e912374c14e0e622a63292f623a9e0ca530d94dc982edb49016`；safe live state 尚未
写出，不能提前填写完整 16-unit 分母或 ranking readiness。transport/ranking/freeze/import/
target 产物继续缺失，watcher 的 `next_gate=screening`、`target_suite_calls_allowed=false`
不变。本次没有恢复 checkpoint、使用 `--retry-failed`、修改 frozen plan 或并发启动新的
screening。

## r15 safe state 阶段性复核（2026-08-20 13:34 CST）

r15 已写出 safe live state，但仍处于 screening gate：`status=running`、16 个计划 unit 中
`1 completed / 2 failed`，`ready_for_ranking=false`。两个 failed unit 的完整 transport
分母分别为 `80/102` 和 `112/112`，均因超过固定 `2%` gate 失败；这只是 transport 证据，
不能解释为能力分数或 ranking 结果。当前活动 checkpoint 为 `42/102`、状态 `partial`，
screening receipt、transport admission、ranking、freeze/import/target 产物均不存在。
state 的 r15 plan/source 与 r7 registry/probe hash binding 未改变，
`target_suite_calls_performed=false` 保持不变。本次没有恢复 checkpoint、重试失败 case、
修改 frozen plan 或启动第二套 screening。

## r15 live screening 进度快照（2026-08-20 13:37 CST）

safe state 最新为 `running`：16 个 planned unit 中 `1 completed / 3 failed`，
`ready_for_ranking=false`，state SHA-256 为
`698ce13d3b1cf3e8f57c22c074da3be554cdd3e99e7bdd792d8182ce2f2114a5`。
新增 failed unit 保留 `42/102` scored/transport 分母，即 `60/102` transport failures、
failure rate `0.588235294118`，触发固定 `2%` gate；不解释为质量或 ranking 结果。当前
活动 checkpoint 为新的 `0/112`、状态 `partial`，screening receipt、transport admission、
ranking、freeze/import/target 产物均不存在，`target_suite_calls_performed=false` 继续为
false。本次没有恢复 checkpoint、使用 `--retry-failed`、修改 frozen plan 或启动第二套
screening。

## r15 live screening 进度快照（2026-08-20 12:45 CST）

低频只读核验确认三个 init 托管进程仍存活且 plan identity 未改变。首个 serial unit 的
private checkpoint 为 `68/112`、`checkpoint_status=partial`，checkpoint SHA-256 为
`3aafaf214d732dfa72b0f323a9087a347284dad5fce0afd0b4855ae8e81beef6`；safe live state
尚未写出，不能填写完整 16-unit 分母或 ranking readiness。transport/ranking/freeze/import/
target 产物继续缺失，`next_gate=screening`、`target_suite_calls_allowed=false` 不变。
本次没有恢复 checkpoint、使用 `--retry-failed`、修改 frozen plan 或并发启动新的 screening。

## r15 live screening 进度快照（2026-08-20 13:48 CST）

13:48 CST 只读复核确认 screening PID `2871629`、convergence supervisor PID `2880595` 和
lineage watcher PID `2881730` 仍存活，命令行继续绑定 r15 frozen plan/source 与 r7
probe-bound registry/admission。safe state 为 `running`，16 个 planned unit 中已有
`1 completed / 7 failed`，8/16 unit 已写入 state，state SHA-256 为
`b27bee06ab1e75a97ce7f34b087bf570dad7105497cfca7dfedf88cbf55b6eea`。新增 failed unit 的
完整分母为 `102/102` transport failures；此前各 failed unit 的完整分母全部保留，均因
固定 `2%` gate fail-fast。以上是 transport evidence，不得当作质量分数或排名。

当前进入第 9 个 serial unit：task
`23d2aad8799078241760998a00ba2db1e3852b2503cfbe087bcde2c1e4cbe154`，checkpoint 为
`0/112`、`partial`，SHA-256 为
`41f510d86b234361e7543d56668e00735f1312c239426ebe2888fc3bc2bcdbb0`。screening receipt、
transport admission、ranking、provider freeze、official import 和 target campaign
仍不存在；supervisor/watcher 继续保持 `next_gate=screening`、
`target_suite_calls_allowed=false`。后续仍只做 10-20 分钟低频检查，不恢复 checkpoint、
不使用 `--retry-failed`、不修改 frozen plan、不启动第二套 screening。

## r15 live screening 与工程回归里程碑（2026-08-20 14:00 CST）

14:00 CST 只读复核确认三个 init 托管进程仍存活，r15 plan/source 与 r7 probe-bound
registry/admission 的命令行绑定未改变。safe state SHA-256 为
`94a127931d3825b413e5c208b3a795dc6eb76c9026ef549eb46322805501a7ea`，campaign 仍为
`running`：16 planned unit 中 `1 completed / 10 failed`，11/16 已写入 state，剩余 5 个
未 terminal，`ready_for_ranking=false`、`target_suite_calls_performed=false`。唯一 completed
unit 是 `112/112`、transport failure `0`；failed 分母为 `112/112 ×5`、`102/102 ×2`、
`101/102`、`80/102`、`60/102`，均触发固定 `2%` gate，不能用于质量或排名。

当前 task `13c5304ac5ef6a492ac6f5a023842224fb2fd64386f68a32465b3d97027eea3a` 的 private
checkpoint 为 `6/102`、`partial`，SHA-256 为
`0aba0016052153885e3562b789fc917c6dd8a10e6b8b0eefb721c2fb8e7e85d1`。screening receipt、
transport admission、ranking、provider freeze、official import 和 target campaign 仍不
存在，`next_gate=screening`、`target_suite_calls_allowed=false` 不变。

同阶段的工程回归命令 `python3.11 -m pytest tests/ -x -q --tb=short` 已通过
`1066 passed, 7 skipped`。该回归仅证明代码契约，没有授权任何 target request 或
superiority claim。
## r15 live screening 进度快照（2026-08-20 14:04 CST）

14:04:57 CST 只读核验确认 screening/supervisor/watcher 三个 PID 仍存活，命令行仍绑定
r15 frozen plan/source 与 r7 registry/probe/admission。safe state SHA-256 为
`3b0e4a3001423a964b1f5fb907acca2e30b2e48b10cb6798d26a0fe12a022096`；16 planned unit 中
`1 completed / 11 failed`，12/16 已记录，剩余 4 个，`ready_for_ranking=false`、
`target_suite_calls_performed=false`。唯一 completed unit 为 `112/112`、transport failure
`0`；failed 分母为 `112/112 ×5`、`102/102 ×2`、`101/102`、`92/102`、`80/102`、
`60/102`，全部触发固定 `2%` gate，不能转成质量或排名证据。

当前 task `dd6e3d631867c96b5417ca5860af672e9de80961eae4f317e6c17e96fac9559a` 的 checkpoint
为 `2/112`、`partial`，SHA-256 为
`0a75d69049abf3da03e37f9def47833f600ff8d49f937ee374bfdc5c37e915a8`。screening receipt、
transport admission、ranking、provider freeze、official import 和 target campaign 仍不
存在，`next_gate=screening`、`target_suite_calls_allowed=false` 不变。

## r15 live screening 进度快照（2026-08-20 14:17 CST）

14:17:37 CST 只读核验确认三个 init 托管进程仍存活，命令行继续绑定同一 r15 frozen
plan/source 与 r7 probe-bound registry/admission。safe state SHA-256 为
`e4fbe624e2a0d8e7692dc6eaa7698f9197d27afea77650b8ad74ebb5a10d557d`；16 planned unit 中
`1 completed / 12 failed`，13/16 已写入 state，剩余 3 个，`ready_for_ranking=false`、
`target_suite_calls_performed=false`。新增 failed unit 的分母是 `102/112` transport
failures；完整 failed 分母为 `112/112 ×5`、`102/112`、`102/102 ×2`、`101/102`、
`92/102`、`80/102`、`60/102`，均触发固定 `2%` gate，不能用于质量或排名。

当前 task `fce71276a5c3344d9a534c42a84b5f75fdee4d97b7f9660bb9af3796f8ec5166` 的 checkpoint
为 `6/102`、`partial`，SHA-256 为
`2c4aa0ad9ed3c423ec599412781f87e3d124f347c8b63fec2555007d8eac570a`。screening receipt、
transport admission、ranking、provider freeze、official import 和 target campaign 仍不
存在，`next_gate=screening`、`target_suite_calls_allowed=false` 不变。
