# Composite r12 successor Intake 与 Harness 控制面（2026-08-19）

## 继任边界

r11 已 16/16 unit terminal，但 campaign 为 `partial`（11 completed、5 failed），虽然
transport-only admission 留下 5 个 canonical model，complete-pool ranking 仍因完整
campaign/source coverage 不满足而 blocked。r11 的所有 state、private unit artifact、
transport、ranking、supervisor 和 Harness audit 只读保留，不恢复、不重试、不拼接
completed subset，也不作为 r12 的 ranking/freeze 输入。

r12 从 r11 source successor 创建 immutable source successor，仅改变
`pre_registration.selection_seed` 和新的 registration 事件：

- source manifest：SHA-256 `44bc2c7ec6f9db22fc2724a17cb60036c50abcd5c646ebc2401ccac3fadc05e7`；
- successor receipt：SHA-256 `b85fdd91ecb0faaf0f5b5e4f9e940e24d5cf09fd862348619d288991d302ef59`；
- selection seed hash：`0557b404e7ad918bf19bcb10880dc4aaffa91911a3574eb6ad52959e3b330ed6`；
- registered_on：`2026-08-19`；
- receipt `status=ready`，raw prompt/label/provider output、provider URL 和 secret
  持久化标志均为 `false`。

## Frozen plan 与 preflight

r12 plan 使用当前 r7 probe-bound registry 和 r7 operational admission，重新计算同一
两套 source family 的完整候选分母；不传入 r11 transport/ranking/freeze：

- plan 文件 SHA-256：`58e2a0acd39801a6245082d67e3ef5f93aa543836d28dd8f9a3ca94bba4c6c65`；
- plan digest：`b38052946a726ddb9d03aa6b4a04c19804e021731e508fa1048a63101afacde4`；
- registry SHA-256：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- source count/family count：`2/2`；canonical group/profile count：`8/9`；
- `task_count=16`、`minimum_cases_per_source=100`、`max_workers=1`、fail-fast transport
  gate 已预注册；
- estimated provider calls：`1712`；plan `ready=true`。

zero-network preflight 已通过：

- receipt SHA-256：`06ca721adac5984d153bd84d101655246f40afe460cf019fbe8798ae517061a9`；
- state SHA-256：`353f2c38e7661c6f9da0d79e59afc8cec20fe718af86e16ef5c09187dff4d4af`；
- campaign digest：`741e0c306ebcab33545300c8581467f828db504d1e635d2cc53e07166eb4ca3a`；
- `status=preflight_ready`、`mode=preflight`、`network_calls_performed=false`、
  `target_suite_calls_performed=false`、`reason_codes=[]`。

## Harness 控制面

控制面输出目录为 `private/runs/2026-08-19-composite-cohort-r12/harness_control.successor/`。
它只复用已验证的 hash-only Harness pin 和 21-suite benchmark 定义，不复制原始
checkout、dataset 内容、答案、provider output 或旧 cohort 结果：

- pin：SHA-256 `22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`，
  `6/6 ready`；
- acquisition checklist：SHA-256
  `a6923c000f8b28c1cc047b17ca920705fb33e6e7b27474ea19049206ba3e92dc`，
  `template_ready`；
- acquisition status：SHA-256
  `c3a2097d040436f6e6ca79a56f134a811d0a9bf34cb2f87e1ac2029c2748356a`，等待 official
  imports 和 provider freeze；
- official execution plan：SHA-256
  `19e1cb2f0d42ce0a9d7b9577b584112c0438123200921e654de88a6635e2ce3a`，`ready`；
- official import audit：SHA-256
  `bde2e1098b7459571c7ea6e34677ee5946166ded7e9dd5a00bf151fcaba4d380`，`blocked`；
- initial cohort binding：SHA-256
  `84aea0437d486a2b1f4ca45d3798f1990e7d4397abcc8d578d42cfd52d957ae6`，`blocked`；
- convergence audit：SHA-256
  `59b446f969bdf8b571b54aa3d29d44d62f02e166b5a195ea67992dfc76620d3c`，`blocked`、
  `next_gate=screening`、`target_suite_calls_allowed=false`；
- scaffold：`status=blocked`，`provider_calls_performed=false`、
  `target_suite_calls_performed=false`，敏感字段均为 `false`。

## Live screening 已启动

r12 `baseline-screening-run --live` 已按冻结 plan 启动，并由同一 cohort 的 supervisor
和 lineage watcher 接管；三者均使用 `setsid/nohup`、`max_workers=1`，命令行绑定
r12 plan/source/probe/admission/state/private root。当前现场证据（2026-08-19
13:33 CST）如下：

- screening PID：`4178760`；supervisor PID：`4181633`；watcher PID：`4182263`；
- state：`status=running`、`planned_task_count=16`、`completed_unit_count=0`、
  `failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
- state 文件 SHA-256：`562d7385b87159eacf82ce95977be74983beb27126e986cf134182a5f5dd25a2`；
- `network_calls_performed=true`、`target_suite_calls_performed=false`；
- screening receipt、transport admission 和 ranking 尚未生成，target gate 保持关闭。

screening 终态前不得启动第二套 screening、恢复 r11 checkpoint、修改 frozen plan
或发送 target 请求；后置转换继续由既有 supervisor/watcher 门禁控制。

## Screening 进度快照（2026-08-19 14:45 CST）

r12 仍在唯一 screening gate：state `status=running`、`planned_task_count=16`、
`completed_unit_count=0`、`failed_or_blocked_unit_count=4`、`ready_for_ranking=false`，
state SHA-256 为
`72b7c3877c717f37f4fa2eebb86138dbc45bde467cf7ffd8b37a8f4aa746afd8`。四个已终态
unit 均由冻结的 `max_transport_failure_rate=0.02` 触发失败（失败率分别为约
5.88%、100%、11.61%、43.14%；其中一个同时记录 `screening_unit_no_scores`），
完整失败分母保留在私有 unit artifacts 中。运行器已进入第五个 unit 的 checkpoint：
task `b9d5456f3d18ba9a4f38888d732c7738c096a4908f1d392d2225f479cd2ab55a`，
`mmlu-pro` 已完成 `1/112` case。screening receipt、transport admission、ranking
和 provider freeze 尚未生成；`network_calls_performed=true`、
`target_suite_calls_performed=false`，target gate 继续关闭。

## Screening 进度快照（2026-08-19 15:13 CST）

后续低频检查显示第五个 unit 也已自然终态失败：state 仍为 `status=running`、
`planned_task_count=16`、`completed_unit_count=0`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`，state SHA-256 为
`bab7cf7c9b54875b24267c213e0eb87794d518649484db39a216a58c3bd25dbb`。该 unit 的
transport failure rate 为约 91.07%，仍由冻结 2% gate 拒绝；不修改阈值、不恢复或
拼接任何 completed subset。运行器已进入第六个 `livebench_official_final_text_slice`
unit，checkpoint task 为
`850a79a30e584d817705b7d2fdd06b13411ad129324f81255a72fd119f2a405b`，当前已完成
`77/102` case。screening receipt、transport admission、ranking 和 provider freeze
仍未生成；`target_suite_calls_performed=false`，target gate 保持关闭。

## Screening 进度快照（2026-08-19 15:26 CST）

第六个 `livebench_official_final_text_slice` unit 已成功完成，r12 state 更新为
`status=running`、`planned_task_count=16`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=5`、`ready_for_ranking=false`，state SHA-256 为
`35134f156870a55d1633f16fc019feaacd9879e1454100b4a88551ef101424b7`。运行器已进入
第七个 `mmlu-pro` unit，checkpoint task 为
`eec4029d3c14e766c4365f35615bbe38a5760bfc657747808319989a99712cad`，已完成
`37/112` case。screening receipt、transport admission、ranking 和 provider freeze
仍未生成；`network_calls_performed=true`、`target_suite_calls_performed=false`，
target gate 继续关闭。

## Screening 进度快照（2026-08-19 15:53 CST）

第七个 `mmlu-pro` unit 已成功完成，r12 state 更新为 `status=running`、
`planned_task_count=16`、`completed_unit_count=2`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`，state SHA-256 为
`625b8f84a8d4aeaaaaae0917d071156483cddced03cc2920ae55b235437dd8d3`。运行器已进入
第八个 `livebench_official_final_text_slice` unit，checkpoint task 为
`bd32f49dbc4f9a0af85985b77f8f26901ad2fa7a9c2136faf10e360063200e61`，已完成
`73/102` case。screening receipt、transport admission、ranking 和 provider freeze
仍未生成；`network_calls_performed=true`、`target_suite_calls_performed=false`，
target gate 继续关闭。

## Screening 进度快照（2026-08-19 15:57 CST）

第八个 `livebench_official_final_text_slice` unit 已成功完成，r12 state 更新为
`status=running`、`planned_task_count=16`、`completed_unit_count=3`、
`failed_or_blocked_unit_count=5`、`ready_for_ranking=false`，state SHA-256 为
`4b213bb95f4b7a20745e78ee2b1bff5d968df84079b64768c71ffaccb611df8c`。运行器已进入
第九个 `mmlu-pro` unit，checkpoint task 为
`6f9c3ef80bae3b96e237bbc66d7cbff05573bdc1c3c79bf2439486d79a0a3975`，已完成 `5/112`
case。screening receipt、transport admission、ranking 和 provider freeze 仍未生成；
`network_calls_performed=true`、`target_suite_calls_performed=false`，target gate
继续关闭。

## 失败 telemetry 中间审计（2026-08-19 16:00 CST）

对五个失败 unit 的 hash-only state 与私有 telemetry 做了只读汇总；未读取或写入
prompt、label、原始输出、provider URL 或 credential。所有五项均是冻结的 2% gate
触发 `fail_fast`，因此 `transport_failure_count` 同时包含真实 transport 失败和
`fail_fast_unattempted_case_count`，不能将后者误报为同等数量的真实上游故障：

- `1d69e...`：102 case 中 96 个已评分、6 个失败；3 个真实事件为 2 次 HTTP 503 和
  1 次空输出，随后 3 个未尝试；p95 为约 20.14 秒；
- `44e2fe...`：112 case 中 0 个已评分、112 个失败；3 次 HTTP 500 后，109 个未尝试，
  同时记录 `screening_unit_no_scores`；p95 为约 23.24 秒；
- `a17bf8...`：112 case 中 99 个已评分、13 个失败；2 次 HTTP 503、1 次 timeout 后，
  10 个未尝试；p95 为约 51.74 秒；
- `b9d545...`：112 case 中 10 个已评分、102 个失败；1 次空输出、2 次 timeout 后，
  99 个未尝试；p95 为约 90.08 秒；
- `dc4185...`：102 case 中 58 个已评分、44 个失败；3 次 timeout 后，41 个未尝试；
  p95 为约 80.69 秒。

所有失败 unit 的 `retry_round_count=0`，符合当前 frozen plan 的零重试行为；这只是
当前 cohort 的事实记录。r12 终态前不修改 retry/fail-fast 策略、不重试任何 case，后续
是否需要新的 successor policy 只能在完整 cohort terminal 与 ranking 审计后决定。

## Screening 进度快照（2026-08-19 16:13 CST）

第九个 `mmlu-pro` unit 已成功完成，r12 state 更新为 `status=running`、
`planned_task_count=16`、`completed_unit_count=4`、`failed_or_blocked_unit_count=5`、
`ready_for_ranking=false`，state SHA-256 为
`7f2ceefb3c18ea84bec9903b8067fc18250269374f086a02b9006a5bc9f26889`；campaign digest
已物化为 `eceab7307f81a388bc3e7fc027eec9443d03c72dbe28162e7300705efca2f453`。运行器
已进入第十个 `livebench_official_final_text_slice` unit，checkpoint task 为
`0e9f42b79f925ff407f376defcc6f63df5812f71e25c27fc1778a42fd2cccc6d`，当前已完成
`4/102` case。screening receipt、transport admission、ranking 和 provider freeze
仍未生成；`network_calls_performed=true`、`target_suite_calls_performed=false`，
target gate 继续关闭。

固定顺序为：

```text
r12 live screening -> terminal transport admission
-> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit
-> ready_for_target_campaign -> 21-suite target
```
