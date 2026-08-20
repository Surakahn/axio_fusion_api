# r16 intake 交接（2026-08-20）

## r15 封存结论

r15 已自然终态，16/16 unit terminal，screening receipt 为 `partial`，1 completed、15
failed。transport admission 为 `blocked`：8 个 candidate canonical 中 0 个满足固定 2%
transport gate，最低要求为 3，blocker 为 `transport_admission_fewer_than_minimum_models`。
完整失败分母保留在 r15 私有 state/receipt，不能抽取 survivor subset、恢复 checkpoint、使用
`--retry-failed`、拼接 completed unit 或降低 gate。r15 没有 ranking、provider baseline
freeze、official import 或 target request。

关键 r15 证据：

- screening receipt：`private/runs/2026-08-20-composite-cohort-r15/screening.live.receipt.r15.private.json`，SHA-256 `29dff8639fd59596eb66cb5643bfee2f08d82ada96359a983ca54559dc14513`；
- transport admission：`private/runs/2026-08-20-composite-cohort-r15/transport_admission.r15.private.json`，SHA-256 `53c60e97cae40db1094d5e472e2a2ff2688760ec60be7453d1e29dd33388b639`；
- supervisor：`private/runs/2026-08-20-composite-cohort-r15/convergence_supervisor.r15.private.json`，`status=blocked`、`transport_return_code=2`、`target_benchmark_started=false`。

## r16 immutable successor

r16 只从 r15 source contract 创建新的 source successor，只改变 pre-registration 日期和
selection seed；不读取 r15 score、transport receipt、ranking、checkpoint 或 survivor subset：

- run root：`private/runs/2026-08-20-composite-cohort-r16/`；
- source manifest：`source_manifest.successor.r16.private.json`，SHA-256 `cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`；
- successor receipt：`source_manifest_successor_receipt.r16.private.json`，SHA-256 `f0cbfa13788314f85bb4e4abf889a9a522a5df4cafcb65efeda6fed0457c1ede`；
- selection seed：`composite-r16-2026-08-20-transport-successor`，hash `0f05adcba97d02c23fecdb36d2be6029ed73cf0e9d46a8aef2321441b0125134`；
- plan：`baseline_screening_plan.r16.private.json`，SHA-256 `9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`，digest `23c1b22a1708e38579f2c8f70f82bfe36a1bb7d4bde20e9aa337e289f8e969ad`；
- plan binding：2 source families、8 canonical groups/9 replicas、16 serial units、`max_workers=1`、2% fail-fast、estimated calls `1712`、`ready=true`。

## Zero-network preflight 与 Harness

- preflight state：`screening_state.r16.preflight.private.json`，SHA-256 `3f7b5b367d8ad6d0887f1bd566d61f7d9463fc54adbfd5208090a3dfaf482310`；
- preflight receipt：`screening.preflight.receipt.r16.private.json`，SHA-256 `b61c75dd01902b80d1ba6e2b6ac2359aff49765fbc66ceb9ffd78531ea2bf9fd`；
- campaign digest：`af9aeed814a6e20940dd8f2a3d497e3ce9115d326ffd9e2e999bef826e2e31dc`；
- `status=preflight_ready`、`network_calls_performed=false`、`target_suite_calls_performed=false`；
- Harness 目录：`harness_control.successor/`；pin 6/6 ready、execution plan `ready_to_execute`，convergence `blocked/next_gate=screening`；所有 provider/target call 标志均为 false。

## 唯一后续路径

启动前只做一次只读核验：r16 plan/source/probe/admission hash、无同名 live screening、命令
行 identity、preflight flags 和工作树状态。随后用 `setsid/nohup` 启动一套 `baseline-screening-run --live`，绑定 r16 frozen inputs；screening terminal 前不执行 transport conversion、ranking、freeze、official import 或 target campaign。

terminal 后严格执行：

```text
transport admission -> complete-pool ranking -> external rank 1/2/3 evidence
-> provider baseline freeze -> same-cohort official/audited import
-> cohort binding/convergence audit -> 21-suite target campaign
-> paired statistics/latency/API parity/contamination/final audit
```

所有文档、receipt、commit message 使用中文；private evidence 不进入 Git，不写入 secrets、
raw prompt、label、provider URL、raw output。未完成完整证据前不做 superiority claim。

## r16 live screening 启动里程碑（2026-08-20 15:07 CST）

r16 唯一 live non-target screening 已通过 `setsid/nohup` 启动：screening PID `3231684`、
convergence supervisor PID `3231745`、lineage watcher PID `3231746`。三者命令行均绑定
r16 frozen plan/source 与 r7 probe-bound registry/probe/admission；PID、命令行 identity、
supervisor wait 和 watcher 初始 convergence snapshot 均通过核验。当前没有 safe live state、
checkpoint、screening receipt、transport admission、ranking、provider freeze、official import
或 target campaign。supervisor/watcher 保持 `next_gate=screening`、
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。

后续只做低频只读检查，不恢复 checkpoint、不使用 `--retry-failed`、不修改 frozen plan、不启动
第二套 screening；screening terminal 后才执行同 cohort transport admission。

## r16 低频进度复核（2026-08-20 15:15 CST）

三项进程仍存活且均绑定 r16 frozen plan/source 与 r7 probe-bound registry/probe/admission。
当前活动 unit 的私有 checkpoint 为 `16/102`、`partial`，SHA-256 为
`4e746fe5901b3b1ee2d4a82d0dfd326e7852d66ef371d0b920a3419dbe1bd95f`。checkpoint 仅是私有
恢复证据，raw provider output 未进入 Git，不能作为 unit 完成、质量分数或 ranking 依据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 仍为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
本轮只读审计确认历史 benchmark runner 的裸 `except:`/重复路径属于 baseline freeze 后的
独立清理项，当前不改动它们，不改变 frozen plan 或任何 routing/prompt/panel policy。

## r16 低频进度复核（2026-08-20 15:24 CST）

三项进程仍由 init 托管且命令行 identity 未改变。当前活动 unit 的私有 checkpoint 已推进到
`31/102`、`partial`，SHA-256 为
`779e5b887cbe275e236dae269741e28b02446711976b8de86b236d10fac4fb62`。checkpoint 仅是私有
恢复证据，不能作为 unit 完成、质量分数、ranking 或 baseline freeze 依据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
生产 loopback `/health` 只读检查返回 `ready`，公开模型仍为三个 Axio tier，network transport
为 configured proxy；这些只证明服务工程健康，不证明 provider 能力或 superiority。

## r16 低频进度复核（2026-08-20 15:29 CST）

提交后的只读复核确认三项进程仍由 init 托管且命令行 identity 未变。当前活动 unit 的私有
checkpoint 已推进到 `41/102`、`partial`，SHA-256 为
`eb886b1d5bea0358b281fadba690fd54d0dc6451938c9ee03abd05696ba046a1`。checkpoint 仅是私有
恢复证据，不能作为 unit 完成、质量分数、ranking 或 baseline freeze 依据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续仍只低频检查，screening terminal 前不恢复 checkpoint、不使用 `--retry-failed`、不修改
frozen plan、不启动第二套 screening，也不执行任何下游 gate。

## r16 首个 unit 终态与第二个 unit 启动（2026-08-20 15:58 CST）

r16 safe live state 已首次生成，SHA-256 为
`fa223d6f6fc9ba7a1fc1805bb45ffeb0cbeaf856dd528b29f1878cf6f4b4a3e9`；campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 1 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。首个 unit
`3b166a5e9721a833999066b5886263c93b055691dfb2890267e380f9a3ef1d26` 已自然终态失败：
`78/102` scored、`24/102` transport failures、failure rate `0.235294117647`，reason code
为 `screening_unit_transport_failure_rate_exceeded`。完整分母保留为 provider evidence，不能
解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第二个 unit；启动时 checkpoint 为 `1/112`。截至
`16:00 CST` 的低频复核，当前私有 checkpoint 已推进到 `14/112`、状态 `partial`，SHA-256
为 `cf9a0bacb5ed3fd57993cf7263bbd90a77986067735d55bfb3304200340911a2`。该 checkpoint 仅为
私有恢复证据，不能作为 unit 完成或 transport admission 依据。screening receipt、transport admission、
ranking、provider baseline freeze、official import 与 target campaign 仍未生成；supervisor/
watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复 checkpoint、不得使用 `--retry-failed`、不得
修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 第二个 unit 终态与第三个 unit 启动（2026-08-20 16:14 CST）

safe live state 更新为 SHA-256
`8840155fc4dded6d02361c9d4ab70b495c89885eb7fa62ca5692a269c4bd41d2`；campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 2 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。第二个 unit
`f60834dbf975d0c2b0bb12ccb3422197853d504046b1df1d923b56e188958179` 已自然终态失败：
`66/112` scored、`46/112` transport failures、failure rate `0.410714285714`，reason code
为 `screening_unit_transport_failure_rate_exceeded`。完整分母继续保留为 provider transport
evidence，不能解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第三个 unit，当前 checkpoint 属于新的 `102`-case
unit、状态 `partial`；该中间 checkpoint 仅是私有恢复证据。screening receipt、transport
admission、ranking、provider baseline freeze、official import 与 target campaign 仍未生成；
supervisor/watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复任一 checkpoint、不得使用 `--retry-failed`、
不得修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 第三个 unit 终态与第四个 unit 启动（2026-08-20 16:18 CST）

safe live state 更新为 SHA-256
`f0e37f0ed5bcb83197a00364492a5bd7803f03e0caf5eec58bbc269f6533d01a`，campaign digest 为
`f2619ac4c1dcfe6189884a71da44adb306a18543bfbc8c82c460bed430f80577`；campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 3 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。第三个 unit
`e84723db16da485150045f926a0e0a2540250ceedc1009d811c9d11f0b8cc1a5` 已自然终态失败：
`0/102` scored、`102/102` transport failures、failure rate `1.0`，reason codes 为
`screening_unit_no_scores` 与 `screening_unit_transport_failure_rate_exceeded`。完整失败分母
继续保留为 provider transport evidence，不能解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第四个 unit，当前 checkpoint 属于新的 `112`-case
unit、状态 `partial`；该中间 checkpoint 仅是私有恢复证据。screening receipt、transport
admission、ranking、provider baseline freeze、official import 与 target campaign 仍未生成；
supervisor/watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复任一 checkpoint、不得使用 `--retry-failed`、
不得修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 第四个 unit 终态与第五个 unit 启动（2026-08-20 16:54 CST）

r16 safe live state 更新为 SHA-256
`a27ee4a15e2c1ebe892f9ddfcf29d421ca20cf97cf9423541dc56a4f64b3496d`；campaign digest 为
`ea29512ad166c949aa412310cc0fe5dd32cdb7c2d838648d18f82eb175a2c896`。campaign 仍为
`status=running`，16 个 planned units 中 `0 completed / 4 failed`，`ready_for_ranking=false`，
`network_calls_performed=true`、`target_suite_calls_performed=false`。第四个 unit
`69efb856ac5b893e75548c5d92ed500b1c8e6deac0e8d93b672e7196aa91236a` 已自然终态失败：
`46/112` scored、`66/112` transport failures、failure rate `0.589285714286`，reason code
为 `screening_unit_transport_failure_rate_exceeded`。完整失败分母继续保留为 provider
transport evidence，不能解释为质量分数、survivor subset 或 ranking。

筛选器已按 frozen serial schedule 进入第五个 unit；当前私有 checkpoint 属于新的 `102`-case
unit，`0/102`、状态 `partial`，checkpoint SHA-256 为
`9fd45ccb2b29a1f060d5cbbadb6563ce93773af5e4daf1a0383aa2469fde5250`。该 checkpoint 仅是
私有恢复证据，不能作为 unit 完成、transport admission 或 ranking 依据。screening receipt、
transport admission、ranking、provider baseline freeze、official import 与 target campaign
仍未生成；supervisor/watcher 继续保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。不得恢复任一 checkpoint、不得使用 `--retry-failed`、
不得修改 frozen plan、不得拼接 completed/survivor subset、不得启动第二套 screening。

## r16 低频进度复核（2026-08-20 15:50 CST）

三项进程仍由 init 托管且 command-line identity 未变。当前活动 unit 的私有 checkpoint 已
推进到 `79/102`、`partial`，SHA-256 为
`d8371b7c7a84f04c0bdb0b6c1ff922d340f797f83b3c21f3359c0eff20ba69d7`。checkpoint 仅是私有
恢复证据，不能作为 unit 完成、质量分数、ranking 或 baseline freeze 依据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续仍只低频检查，screening terminal 前不恢复 checkpoint、不使用 `--retry-failed`、不修改
frozen plan、不启动第二套 screening，也不执行任何下游 gate。

## r16 过半进度复核（2026-08-20 15:35 CST）

三项进程仍由 init 托管且命令行 identity 未变。当前活动 unit 的私有 checkpoint 已推进到
`50/102`、`partial`，SHA-256 为
`173ce7cd96c6789f2d330458c7ff5c51973b814226c660a61fc166d90d58852e`。checkpoint 仅是私有
恢复证据，不能作为 unit 完成、质量分数、ranking 或 baseline freeze 依据。

本次只读 hash 核验确认 r16 plan/source/preflight 输入均未漂移，分别保持既有
`9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`、
`cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`、
`3f7b5b367d8ad6d0887f1bd566d61f7d9463fc54adbfd5208090a3dfaf482310` 和
`b61c75dd01902b80d1ba6e2b6ac2359aff49765fbc66ceb9ffd78531ea2bf9fd`。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续只低频检查，screening terminal 前不执行任何下游 gate。

## r16 低频进度复核（2026-08-20 15:43 CST）

三项进程仍由 init 托管且命令行 identity 未变。当前活动 unit 的私有 checkpoint 已推进到
`63/102`、`partial`，SHA-256 为
`a030b9b77c7b5372b99e1adc71678825d93b24aa3f00fe936108cf17ab451bee`。checkpoint 仅是私有
恢复证据，不能作为 unit 完成、质量分数、ranking 或 baseline freeze 依据。

safe live state、screening receipt、transport admission、ranking、provider baseline freeze、
official import 与 target campaign 仍未生成；supervisor/watcher 继续为
`next_gate=screening`、`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
后续只低频检查，screening terminal 前不恢复 checkpoint、不使用 `--retry-failed`、不修改
frozen plan、不启动第二套 screening，也不执行下游 gate。
