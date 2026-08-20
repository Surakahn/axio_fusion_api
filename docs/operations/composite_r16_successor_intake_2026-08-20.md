# Composite cohort r16 successor intake（2026-08-20）

## r15 terminal decision

r15 16/16 unit 已 terminal，screening 为 `partial`，transport admission 为 `blocked`。
8 个 candidate canonical 中 0 个通过完整两源 2% transport gate，最低要求为 3；supervisor
未启动 ranking，`target_benchmark_started=false`。r15 全部 state、完整分母、私有 case evidence、
transport receipt 和控制面只作 reference-only，不能作为 r16 的候选子集或质量依据。

## r16 successor registration

r16 只复制 r15 source contract，重新生成 immutable successor：

- source successor SHA-256：`cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`；
- successor receipt SHA-256：`f0cbfa13788314f85bb4e4abf889a9a522a5df4cafcb65efeda6fed0457c1ede`；
- selection seed：`composite-r16-2026-08-20-transport-successor`；
- plan SHA-256：`9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`；plan digest：
  `23c1b22a1708e38579f2c8f70f82bfe36a1bb7d4bde20e9aa337e289f8e969ad`；
- registry/admission 仍绑定 r7 probe-bound inputs，未重复 provider probe。

计划核验结果：`ready=true`、2 source families、8 canonical groups/9 replicas、16 serial
units、`max_workers=1`、固定 2% fail-fast、estimated provider calls `1712`。所有敏感字段和
raw output flags 为 false。

## Preflight 与 Harness 控制面

r16 zero-network preflight 为 `preflight_ready`，campaign digest
`af9aeed814a6e20940dd8f2a3d497e3ce9115d326ffd9e2e999bef826e2e31dc`；network/target calls
均为 false。Harness scaffold 已在 `harness_control.successor/` 原子生成：pin 6/6 ready、
execution plan `ready_to_execute`，acquisition/import/binding/convergence 仍 blocked，
`next_gate=screening`、`target_suite_calls_allowed=false`。

## 启动约束

只允许一套 r16 live screening，使用 `setsid/nohup`、`PYTHONPATH=src`、`max_workers=1`，
命令行必须绑定 r16 plan/source、r7 registry/probe/admission。启动后立即核验 PID、命令行、
日志首尾和 state 增长。不得恢复 r15 checkpoint、不得使用 `--retry-failed`、不得修改 frozen
plan、不得启动第二套 screening。

screening terminal 后由同 cohort supervisor 执行 transport admission；仅当完整候选池达到
最低 3 个 canonical 且每个 pre-registered source unit 满足 2% gate，才允许 complete-pool
ranking。任何失败都封存完整分母并注册下一个 immutable successor，不降低 gate、不拼接
survivor、不提前触发 target。

## 研究边界

当前缺口仍是 provider evidence lineage，而不是增加未经 baseline 证明的新 Fusion 算法。
baseline freeze 前不改 router 权重、prompt、panel 规则或 benchmark-driven policy。freeze 后
才进入真实 calibration、受约束 panel optimizer、Judge/Synth calibration、reasoning transport
closure 和历史 benchmark runner 清理；每项都必须以 shadow/non-target evidence 为先，并按
L1 -> L2 -> L3 -> L4 -> commit/push 逐阶段落地。

## r16 过半进度复核（2026-08-20 15:35 CST）

r16 唯一 live screening、convergence supervisor、lineage watcher 仍由 init 托管，命令行
仍绑定 frozen plan/source 与 r7 probe-bound registry/probe/admission。当前活动 unit 的私有
checkpoint 为 `50/102`、`partial`，SHA-256 为
`173ce7cd96c6789f2d330458c7ff5c51973b814226c660a61fc166d90d58852e`；该文件含 raw provider
output，仅作私有恢复证据，不是完成、质量、ranking 或 freeze 证据。

只读 hash 核验确认 r16 plan/source/preflight 输入未漂移；safe live state、screening receipt、
transport admission、ranking、provider freeze、official import 和 target campaign 仍不存在。
supervisor/watcher 保持 `next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。继续遵守不恢复 checkpoint、不使用 `--retry-failed`、
不修改 frozen plan、不启动第二套 screening 的约束。

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
