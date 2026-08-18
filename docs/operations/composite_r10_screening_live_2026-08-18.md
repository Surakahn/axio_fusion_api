# Composite r10 screening live 运行记录（2026-08-18）

## 启动门禁与绑定

r10 已通过独立 source successor、immutable plan 和 zero-network preflight 后启动
live non-target screening。启动使用全新 r10 live state/private root：

- screening PID：`2281133`，命令行持续包含 `baseline_screening_plan.r10.private.json`；
- supervisor PID：`2283494`，仅等待 terminal 后执行 transport admission/ranking；
- lineage watcher 当前 PID：`2365523`，只重建同 cohort hash-only binding/audit；旧 PID
  `2284301` 已在 audit 修复后退出，screening 与 supervisor 未重启；
- registry：当前 r7 probe-bound registry，文件 hash
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- plan：r10 plan digest
  `f779424f4d6846de97a24da8d5c15ebbce2253c53bca592ccba7ac5b0564cfa8`；
- source manifest：`source_manifest.successor.r10.private.json`；
- private probe：r7 provider probe private artifact，唯一 probe set 与 r10 identity
  attestation 对齐；
- operational admission：r7 `operational_admission.r7.private.json`；
- 执行约束：`max_workers=1`、2 source families、16 serial units、fail-fast transport
  gate；未传 `--retry-failed`，未读取旧 cohort checkpoint。

## 当前进度

启动命令使用 `setsid nohup`，screening 与两个监督进程均已脱离终端托管。首个 serial
已有三个 serial unit 完整执行并安全归档：一个为 112/112 且 0 个 transport failure，
一个为 102/102 且 1 个 transport failure 并完成，另一个为 102/102 且 102 个
transport failure 并以 `screening_unit_no_scores`、
`screening_unit_transport_failure_rate_exceeded` 失败；完整失败分母均已保留。
截至 2026-08-18 23:50（CST），campaign live state 仍为 `running`，
`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`；第四个 serial unit
仍在执行，其活动 checkpoint 已推进至 26/112。checkpoint 只在
operator-owned private root 保存 provider 原始恢复数据，safe receipt 不包含这些内容。
screening 尚未达到 campaign terminal，`ready_for_ranking=false`；当前进度不产生
ranking、provider freeze 或质量结论。

supervisor 当前事件为 `screening_wait_started`，watcher 当前为
`next_gate=screening`、`target_suite_calls_allowed=false`、
`target_suite_calls_performed=false`。screening 期间禁止 ranking、provider freeze、
official import 和 target campaign。

watcher 已加载 `4d1abd6` 的审计修复；在 state 尚未物化的早期窗口，后续快照不再把
`artifact_missing` 误报为 `screening_target_suite_calls_present`。

## 2026-08-19 00:16（CST）低频进度快照

- 三个后台 PID 仍存活，screening 命令仍绑定 `baseline_screening_plan.r10.private.json`；18900 服务只读健康检查仍为 `ready`。
- campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`。
- 当前活动 checkpoint 为 `0af6bdbc99f0dde29090bf1b0373393cc6f0a8fa488fdffb1e8495db9921aeac`，`expected_case_count=112`，已完成 `71/112`，已完成 case 的 transport failure 为 0；checkpoint 文件 mtime 在本快照前持续更新。
- 已完成 unit 的失败分母不变：`112/112` 且 0 失败、`102/102` 且 1 失败；失败 unit `102/102` 且 102 失败，完整失败证据继续只读保留。
- supervisor 仍只等待 terminal；watcher 的当前 gate 仍为 `screening`，target、ranking、provider freeze 和 official import 均未启动。

## 2026-08-19 00:23（CST）低频进度快照

活动 checkpoint 已自然推进至 `84/112`，其中 84 个 case 均为 completed，当前 checkpoint 未出现 transport failure。campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`；transport admission、ranking、provider freeze 和 screening receipt 仍未生成。

## 2026-08-19 00:29（CST）低频进度快照

活动 checkpoint 已推进至 `94/112`，94 个已完成 case 均为 completed，当前 checkpoint 未出现 transport failure。campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`；supervisor 仍只等待 terminal，所有后置转换保持关闭。

## 2026-08-19 00:32（CST）低频进度快照

活动 checkpoint 已推进至 `100/112`，100 个已完成 case 均为 completed，当前 checkpoint 未出现 transport failure。campaign state 仍为 `running`、`completed_unit_count=2/16`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`，`target_suite_calls_performed=false`；transport admission、ranking 和 supervisor terminal receipt 仍未生成。

## 2026-08-19 00:39（CST）serial unit 完成里程碑

原活动 `mmlu-pro` serial unit 已完整终态：`112/112`、`scored_case_count=112`、`transport_failure_count=0`、`status=completed`。campaign state 已更新为 `completed_unit_count=3/16`、`failed_or_blocked_unit_count=1`，仍为 `running`、`ready_for_ranking=false`、`target_suite_calls_performed=false`。

运行器已按 frozen schedule 进入下一 serial unit `livebench_official_final_text_slice_2026_08_14`，其活动 checkpoint 当前为 `3/102`；因此完整 screening 尚未 terminal，transport admission、ranking、provider freeze 和 target 继续关闭。

## 2026-08-19 00:53（CST）第五个 serial unit 完成里程碑

第五个 serial unit 已自然终态：`102/102`，`scored_case_count=101`，
`transport_failure_count=1`，failure rate 为 `0.009803921569`，低于预注册的
`0.02` transport gate，unit 状态为 `completed`。完整 102-case 分母和失败遥测继续保留
在 operator-owned private root，safe receipt 不包含原始 provider 输出。

campaign state 更新为 `completed_unit_count=4/16`、`failed_or_blocked_unit_count=1`，
仍为 `running`、`ready_for_ranking=false`、`target_suite_calls_performed=false`。
运行器已按 frozen schedule 进入第六个 serial unit（`1/112`）；supervisor、lineage
watcher 和正式 Fusion 服务均保持存活，transport admission、ranking、provider freeze、
official import 与 target campaign 继续关闭。

## 2026-08-19 01:01（CST）第六个 serial unit transport 阻断里程碑

第六个 serial unit 已自然终态但未通过 transport gate：完整分母为 `112/112`，其中
`scored_case_count=6`、`transport_failure_count=106`，unit 状态为 `failed`，唯一
reason 为 `screening_unit_transport_failure_rate_exceeded`。该失败 unit 的全部
unattempted/failed 分母和分类遥测永久保留在 operator-owned private root；不恢复
checkpoint、不传 `--retry-failed`、不把 6 个 scored case 作为可排名结果。

campaign state 更新为 `completed_unit_count=4/16`、`failed_or_blocked_unit_count=2`，
仍为 `running`、`ready_for_ranking=false`、`target_suite_calls_performed=false`。
运行器已按 frozen schedule 进入下一个 serial unit；supervisor 仍只等待 campaign
terminal，transport admission、ranking、provider freeze、official import 与 target
campaign 继续关闭。

## 2026-08-19 01:16（CST）运行态审计与第七单元快照

本次 continuation 对 r10 进行了只读 intake audit：screening PID `2281133`、
convergence supervisor PID `2283494`、lineage watcher PID `2365523` 均存活，命令行仍
绑定同一 r10 immutable plan；正式 `18900/health` 返回 `ready`，`model_count=21`、
公开模型为 `axio-fast/axio-terra/axio-pro`，网络仍为 `auto -> proxy`，敏感字段继续
全部为 `false`。当前状态仍为 `running`、`completed_unit_count=4/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。

当前活动 `livebench_official_final_text_slice_2026_08_14` checkpoint 已推进到
`35/102`，已完成 case 暂无 transport failure；该 checkpoint 仍属于 private recovery
root，不能作为排名或分数证据。已有 6 个终态 unit 的完整分母、失败分类遥测和 content
digest 保持只读；失败 unit 不恢复、不重试、不拼接进 ranking。

控制面回归同时完成：Harness scaffold/binding、convergence supervisor、official
campaign 相关测试 `19 passed`，`prepare_composite_harness.py`、binding/audit/watcher
等 5 个脚本通过 Python 3.11 `py_compile`。这只确认控制面结构可执行，不改变
`target_suite_calls_allowed=false`。

## 研究与推进闸门

当前可信锚点为 r10 的 immutable plan、registry/source digest、private screening
证据和 6/6 Harness pin/execution plan；transport admission、完整候选池 ranking、
provider baseline freeze、同 cohort official import 和 convergence audit 仍未完成，
历史 r8/r9 结果只能作 reference-only。后续严格按以下顺序推进：

```text
screening terminal
  -> transport-only admission（至少 3 个 canonical models）
  -> complete-pool ranking
  -> provider baseline freeze
  -> 同 cohort official import/audit
  -> convergence audit = ready_for_target_campaign
  -> 21-suite target、四格式 parity、统计/延迟/污染审计
  -> completion audit
```

在 screening terminal 之前不做 target 请求、不修改 frozen plan、不复用旧 cohort，
也不对当前 partial evidence 作 superiority claim。

## 2026-08-19 01:22（CST）terminal 后 freeze handoff 契约审计

已复核 `scripts/continue_composite_convergence.py` 与 CLI 契约：supervisor 在
screening terminal 后只自动执行 transport-only admission 和
`baseline-screening-to-ranking`，不会自动生成 provider baseline freeze，也不会
读取历史 ranking。ranking 输出必须是同一 r10 的完整候选池、两个 source family、
固定 tie-break 和 identity binding 生成的 strict ranking v3 manifest；若任一 unit
不是完整 `completed`，转换必须保持 blocked。

terminal 后唯一允许的 freeze handoff 为：

```text
benchmark-provider-baseline-freeze
  --registry <r10 probe-bound registry>
  --transport-availability-file <r10 transport_admission>
  --operational-admission-file <r7 operational_admission>
  --provider-probe-evidence-audit <r7 provider_probe_evidence_audit>
  --external-ranking-manifest <r10 ranking>
  --max-provider-baselines 3
```

freeze 只有在 `final_claim_freeze_ready=true`、恰好 3 个非穷举 provider baseline、
external top-three 预注册与 r10 registry/transport/ranking digest 全部一致时才可
写入同 cohort 控制面；否则保留 blocked safe receipt，不降低门槛、不切换旧
`external_provider_ranking.current.private.json`。freeze 成功后才重新运行
`scripts/prepare_composite_harness.py`，再由同 cohort binding/convergence audit
决定是否开放 target calls。

## 2026-08-19 01:44（CST）第七 serial unit 完成里程碑

`livebench_official_final_text_slice_2026_08_14` 已自然终态：完整分母 `102/102`，
`scored_case_count=101`、`transport_failure_count=1`、failure rate
`0.009803921569`，unit 状态为 `completed`，mean score `0.80198019802`。该 unit 的
完整分母和失败分类遥测已写入 r10 private evidence；它可在 campaign terminal 后
参与完整候选池转换，但当前仍不能单独触发 ranking 或 superiority claim。

campaign state 随之更新为 `status=running`、`completed_unit_count=5/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已按 frozen schedule 进入下一个
`mmlu_pro_official_test_2026_07_20` serial unit，活动 checkpoint 为 `1/112`；
supervisor、watcher、transport admission、ranking、provider freeze 和 target
继续保持关闭。

## 2026-08-19 02:39（CST）第八 serial unit 完成里程碑

`mmlu_pro_official_test_2026_07_20` 已自然终态：完整分母 `112/112`，
`scored_case_count=110`、`transport_failure_count=2`、failure rate
`0.017857142857`，低于预注册的 `0.02` transport gate，因此 unit 状态为
`completed`，`fail_fast_unattempted_case_count=0`。两个 timeout 的失败分类和完整
分母继续保留在 operator-owned private root；不读取其答案内容作为 transport admission
依据。

campaign state 更新为 `status=running`、`completed_unit_count=6/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已进入第九个 serial unit
`livebench_official_final_text_slice_2026_08_14`，活动 checkpoint 当前为 `1/102`。
screening、supervisor、lineage watcher 与正式 Fusion 服务均保持存活；transport
admission、ranking、provider freeze、official import 和 target campaign 仍关闭。

## 2026-08-19 03:26（CST）第九 serial unit 完成里程碑

`livebench_official_final_text_slice_2026_08_14` 已自然终态：完整分母 `102/102`，
`scored_case_count=102`、`transport_failure_count=0`、failure rate `0.0`，unit
状态为 `completed`，mean score `0.813725490196`。该 unit 的完整分母和 safe
content digest 已写入 r10 state，仍只可在 campaign terminal 后参与完整候选池转换，
不能单独触发 ranking 或 superiority claim。

campaign state 更新为 `status=running`、`completed_unit_count=7/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已进入下一个
`mmlu_pro_official_test_2026_07_20` serial unit，活动 checkpoint 当前为 `3/112`。
screening、supervisor、lineage watcher 与正式 Fusion 服务均保持存活；transport
admission、ranking、provider freeze、official import 和 target campaign 仍关闭。

## 2026-08-19 04:19（CST）第十 serial unit 完成里程碑

`mmlu_pro_official_test_2026_07_20` 已自然终态：完整分母 `112/112`，
`scored_case_count=112`、`transport_failure_count=0`、failure rate `0.0`，unit
状态为 `completed`，mean score `0.901785714286`。该 unit 的完整分母和 safe content
digest 已写入 r10 state；它仍只能在整个 campaign terminal 后参与完整候选池转换，不能
单独触发 ranking 或 superiority claim。

campaign state 更新为 `status=running`、`completed_unit_count=8/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已进入下一个
`livebench_official_final_text_slice_2026_08_14` serial unit，活动 checkpoint 当前为
`4/102`。screening、supervisor、lineage watcher 与正式 Fusion 服务均保持存活；
transport admission、ranking、provider freeze、official import 和 target campaign
仍关闭。

## 2026-08-19 04:30（CST）持续运行 intake audit

screening PID `2281133`、convergence supervisor PID `2283494`、lineage watcher PID
`2365523` 均仍存活，命令行继续绑定同一 frozen r10 plan；正式 `18900/health` 返回
`ready`，`model_count=21`、网络为 `auto -> proxy`，敏感字段仍全部为 `false`。

campaign state 仍为 `status=running`、`completed_unit_count=8/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。当前 `livebench_official_final_text_slice_2026_08_14`
活动 checkpoint 已自然推进至 `66/102`，已完成 case 暂无新增 transport failure；该
checkpoint 仍只属于 operator-owned private recovery root，不可提前转换为 ranking 或
质量结论。

本轮只读审计确认控制面没有 plan/registry/source digest 漂移，也没有重复启动、恢复
失败 unit 或 target 请求。supervisor 仍只等待 screening terminal；transport admission、
ranking、provider freeze、official import 和 target campaign 继续保持关闭。

## 2026-08-19 04:36（CST）第十一个 serial unit 完成里程碑

`livebench_official_final_text_slice_2026_08_14` 已再次自然终态：完整分母 `102/102`，
`scored_case_count=101`、`transport_failure_count=1`、failure rate `0.009803921569`，
低于预注册的 `0.02` transport gate，unit 状态为 `completed`，mean score
`0.80198019802`。失败分类和完整分母继续保留在 r10 operator-owned private evidence，
不把单个 unit 提前解释为排名或 superiority 证据。

campaign state 已更新为 `status=running`、`completed_unit_count=9/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已进入新的
`mmlu_pro_official_test_2026_07_20` serial unit，当前 checkpoint 为 `10/112`；
screening、supervisor、lineage watcher 与正式 Fusion 服务均保持存活，transport
admission、ranking、provider freeze、official import 和 target campaign 继续关闭。

## 2026-08-19 04:42（CST）第十二个 serial unit 完成里程碑

`mmlu_pro_official_test_2026_07_20` 已自然终态：完整分母 `112/112`，
`scored_case_count=112`、`transport_failure_count=0`、failure rate `0.0`，unit 状态为
`completed`，mean score `0.8125`。该 unit 的完整分母与 safe content digest 已写入
r10 state；它仍只能在完整 campaign terminal 后参与候选池转换，不能单独触发 ranking
或 superiority claim。

campaign state 已更新为 `status=running`、`completed_unit_count=10/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已进入新的
`livebench_official_final_text_slice_2026_08_14` serial unit，当前 checkpoint 为
`2/102`；screening、supervisor、lineage watcher 与正式 Fusion 服务均保持存活，
transport admission、ranking、provider freeze、official import 和 target campaign
继续关闭。

## 2026-08-19 04:44（CST）终态转换契约审计

已对 `baseline_screening.py`、`continue_composite_convergence.py` 及对应回归测试做
离线契约核对：任一 unit 为 `failed/blocked` 时，campaign 必须以 `partial` 终态封存；
transport admission 仍可在完整 terminal 分母上只做失败率筛选，但 ranking conversion
严格要求 `status=completed`、所有 source/candidate unit 完整且双 source family 覆盖。
因此 r10 现有两个 failed unit 不会被 completed subset 掩盖，terminal 后若进入
`partial`，supervisor 产生的 transport/ranking receipt 只能作为封存证据，不能进入
provider freeze 或 Harness target。

后续 successor 路线已明确：保留 r10 的 state、checkpoint、transport/ranking receipt
和 digest 作为 reference-only；不恢复或拼接 r10 subset，使用新的 selection seed 创建
immutable successor source manifest，重新执行 admission、完整 screening 和同 cohort
Harness binding。三模型 transport gate 与 final-claim gate均不降低。

## 2026-08-19 04:54（CST）续接运行态审计

续接时重新核对 `AGENTS.md`、handoff、`PLAN.md`、r10 state 与控制面：screening PID
`2281133`、supervisor PID `2283494`、lineage watcher PID `2365523` 均存活，命令行仍
绑定同一个 frozen r10 plan；正式 `18900/health` 仍为 `ready`，公开模型为
`axio-fast/axio-terra/axio-pro`，四种 API 格式和 `auto -> proxy` 网络均正常。

campaign state 当前为 `status=running`、`completed_unit_count=10/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。活动 `livebench_official_final_text_slice_2026_08_14`
checkpoint 已推进至 `23/102`，当前暂无 transport failure；campaign/unit digest 与
plan/registry/source 绑定保持稳定，全部私有输出和凭据隔离不变。

本次只读控制面复核还确认 Harness 为 `6/6 pin ready` 但 cohort 仍 blocked；脚本
`py_compile` 与实际公开符号导入检查通过。没有恢复 checkpoint、修改 frozen plan、
重复启动 screening 或发起 target 调用。

## 2026-08-19 05:31（CST）新增 serial unit 完成里程碑

活动 `livebench_official_final_text_slice_2026_08_14` serial unit 已自然终态：完整
分母 `102/102`，`scored_case_count=102`、`transport_failure_count=0`、failure rate
`0.0`，unit 状态为 `completed`，mean score `0.833333333333`，p50/p95 latency
分别为 `26179.461/42171.016 ms`。完整分母、失败遥测和 safe content digest 已写入
r10 private state；该结果仍只能在整个 campaign terminal 后参与完整候选池转换，不能
单独触发 ranking 或 superiority claim。

campaign state 已更新为 `status=running`、`completed_unit_count=11/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`。运行器已进入新的
`mmlu_pro_official_test_2026_07_20` serial unit；当前 checkpoint 为 `0/112`。
screening、supervisor、lineage watcher 与正式 Fusion 服务均保持存活，transport
admission、ranking、provider freeze、official import 和 target campaign 继续关闭。

## 后续顺序

保持低频监控，等待 screening 自然终态；随后按固定顺序执行：

```text
terminal screening -> transport admission (至少 3 canonical models)
-> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit
-> target campaign
```

任何 partial/transport-blocked 终态都保留完整失败分母并创建新的 successor，不恢复本
次 checkpoint、不拼接 completed subset、不降低 3-model gate。只有 convergence audit
明确返回 `ready_for_target_campaign` 才允许 target 请求或 superiority claim。
