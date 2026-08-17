# Composite r4 Screening 终态与 Transport 门禁（2026-08-17）

## 终态判定

r4 immutable successor screening 已在不修改 frozen plan、不恢复 checkpoint 的前提下
自然终态：8 个 serial units 全部 terminal，state 为 `partial`，其中 3 个
completed、5 个 failed/blocked，`ready_for_ranking=false`。screening state 和
screening run 的 campaign digest 均为
`d363897c3cef98a74762d36479ef41bb802e100c660860e06fadf48d5a833012`。

该结果只描述 non-target transport screening。`target_suite_calls_performed=false`，
没有将 case 输出、label、分数或 completed subset 用于排名、提示调优或训练。
screening 记录的 transport failure reason 为 `screening_unit_no_scores` 与
`screening_unit_transport_failure_rate_exceeded`；原始 provider 内容继续留在
私有 checkpoint，不进入公共文档或 safe receipt。

## Cohort 绑定

- plan digest：
  `3841f86be153e42ab324f9ff7b6a4d5ec97ee714d46633beaea768bbd82a410f`
- registry digest：
  `a98ca935e3b8005b84e26cfc71feb902ad43ecbc3947a4dec6cd7670bc9c17e5`
- source manifest digest：
  `be9faf4426e1a0b376294f6066e1af96fca9491e3cd2b7e1c2979f8ff7975f6c`
- execution schedule digest：
  `71088128bc871261b1e92b9e068f6cffd4f81ed4f3478589b653c5fefc25a785`
- unit-set digest：
  `a2c13c570fc196c74c375a0e59b8a15d6cc8f03e579d5b020f956abc98363800`

supervisor 已校验 PID 与 plan identity，并在 screening terminal 后只运行一次
transport-only admission。transport receipt 与 screening 绑定到同一 campaign、
plan、registry、source manifest 和 state digest。

## Transport Admission 结果

transport receipt 为 `status=blocked`：

- candidate canonical models：4
- terminal units：8
- 通过严格 failure-rate 门禁的 canonical models：1
- 固定最低要求：3
- blocker：`transport_admission_fewer_than_minimum_models`

由于固定 3-model minimum 未满足，supervisor 没有执行
`baseline-screening-to-ranking`，没有生成可用 external ranking，也没有进入
provider baseline freeze。r4 的 external ranking 与 provider freeze 文件均保持
fail-closed / template-only 状态，不能被解释为排名或基线证据。

## Harness 收敛状态

同 cohort watcher 已完成最终原子 binding 与 convergence audit，随后因 screening
terminal 正常退出。最终 audit 为 `status=blocked`、`target_suite_calls_allowed=false`、
`final_claim_allowed=false`；binding 仍因 transport、ranking、provider freeze 和
official import 前置条件未满足而 blocked。`next_gate=screening` 是控制面当前的
fail-closed 状态，不表示可以重跑 r4。

本 cohort 的正确后续动作是保留 r4 全部私有证据，基于新的候选分母创建下一个
immutable successor；不得修改 r4 plan、恢复 r4 completed subset、降低 3-model
门禁、复用 r4 ranking/freeze 或启动 target Harness。只有 successor 完整通过
transport admission、外部排名注册、provider baseline freeze、官方 Harness import
和 lineage convergence 后，才允许进入 21-suite target campaign。
