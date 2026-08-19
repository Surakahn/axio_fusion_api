# Composite cohort r14 successor intake（2026-08-19）

## 继任边界

r13 已完整 terminal，但 transport admission blocked：16/16 unit 中只有 7 个通过，8 个
candidate canonical 中只有 2 个同时通过两套独立 source family 的固定 `2%` transport
failure gate，低于预注册的 3-model 最低门槛。r13 的 state、unit、transport、supervisor
和 Harness artifact 全部封存为 reference-only；r14 不读取 r13 score，不复用 r13 transport
receipt，不恢复 checkpoint，也不拼接 survivor subset。

r14 仅从 r13 source contract 创建新的 immutable source successor，改变
`pre_registration.selection_seed` 和新的 registration 事件：

- source manifest SHA-256：`e1a676e3af28f48d9f5b5c374542875c5b5f773bf4053c2cf9cb68ea5e32464c`；
- successor receipt SHA-256：`16e64cbef1dfe7d1bc7f454ae5df44b3c8113921c7b87d52bd3574720ee55785`；
- selection seed hash：`b9e8c86c72d875fdbc32c97b771cb73c6924385f873c37199aca78cc7c0b8bb9`；
- registered_on：`2026-08-19`；receipt `status=ready`，raw prompt/label/provider output、
  provider URL 和 secret 持久化标志均为 `false`。

## Frozen plan 与 zero-network preflight

r14 plan 使用同一 r7 probe-bound registry、同一 r7 operational admission 和完整两套
source family，不传入 r13 transport/ranking/freeze：

- plan 文件 SHA-256：`988c0d793af89b1bdf0d681c200dca297ace43e9ce3d09cbe3f3fa8ad4bdefd0`；
- plan digest：`7937b8b99d71e37fc816915a37a62fe300c74ca3128ce1f83f511b5dc473a2ef`；
- registry SHA-256：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- source count/family count：`2/2`；canonical group/profile count：`8/9`；
- `task_count=16`、`minimum_cases_per_source=100`、`max_workers=1`、fail-fast transport
  gate 已预注册；estimated provider calls：`1712`；plan `ready=true`。

zero-network preflight 已通过：

- state SHA-256：`8b453e782bf8f7d475cca9bc749cf8728b65cdfe5a1317ff243be0fa563a0bd8`；
- receipt SHA-256：`1eb08c69ce811408a60d5e9bfbd06ca7e5bde0d640f48bbb0286c27c5384034c`；
- campaign digest：`19a0ce6375812b654b49891cc1dd9e01618cdb320261cb6192959df66375682a`；
- `status=preflight_ready`、`network_calls_performed=false`、
  `target_suite_calls_performed=false`、`reason_codes=[]`。

## Harness 控制面

控制面输出目录为
`private/runs/2026-08-19-composite-cohort-r14/harness_control.successor/`。它只复用
已验证的 hash-only pin 和 21-suite 定义，不复制旧 cohort 的原始 checkout、数据、答案、
provider output 或质量结果：

- pin SHA-256：`22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`，6/6 ready；
- execution plan SHA-256：`dbb56204c2125eb84fbddba44252381bb0cfa476d11252feaad3e0e2af01c46a`，
  `ready_to_execute`；
- scaffold：`status=blocked`、`provider_calls_performed=false`、
  `target_suite_calls_performed=false`；
- convergence audit SHA-256：`86ff0e2e3c05716d326eb04e5c3d91b4651dadf8d643b6a67f55ad3681387d3e`，
  `status=blocked`、`next_gate=screening`、`target_suite_calls_allowed=false`。

acquisition、official import、provider baseline freeze 和 cohort binding 是后续独立门禁，
不能由 pin 或 execution plan 代替。

## 下一步

只启动一套 r14 `baseline-screening-run --live`，绑定 immutable plan/source/probe/admission，
并由同一 cohort 的 supervisor/watcher 低频审计。screening terminal 前不启动 ranking、
provider freeze、official import 或 target benchmark；terminal 后仍必须按

```text
transport admission -> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit -> 21-suite target campaign
```

单向推进。若 r14 仍 partial 或 transport-blocked，完整保留失败分母并创建新的 immutable
successor，不降低 2% gate、不恢复 checkpoint、不拼接 survivor subset、不做 superiority
claim。

## r14 live screening 启动里程碑（2026-08-19 23:19 CST）

r14 唯一 live non-target screening 已通过 `setsid/nohup` 启动：screening PID
`1300532`、supervisor PID `1301981`、watcher PID `1302805`。三者命令行均绑定
`baseline_screening_plan.r14.private.json`，没有并发第二套 screening。supervisor 已进入
同一 PID/plan identity wait，watcher 初始 convergence audit 为 `blocked`、
`next_gate=screening`、`target_suite_calls_allowed=false`。记录时 screening 仍在首个
provider/preflight 阶段，live state 与 receipt 尚未落盘，尚未完成任何 unit；不修改 frozen
plan、不恢复 r13 checkpoint、不发送 target 请求。

## r14 screening 进度快照（2026-08-19 23:33 CST）

r14 首个 `livebench_official_final_text_slice` unit 已自然终态完成：task
`9f3c65a3400e64e7060275409ecb94735aa388d694a4be002d495605ee218d13`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.813725490196`，p50/p95 latency `7316.760ms/20261.479ms`。
campaign 仍为 `status=running`、`planned_task_count=16`、`completed_unit_count=1`、
`failed_or_blocked_unit_count=0`、`ready_for_ranking=false`；state SHA-256 为
`48c5c55ac7d6273af07ec641b4cd572e5962af424e4fe3cfd888dd99e73dce39`，campaign digest 为
`4d3bf242ae076f34a2cae6d6eab6103f450764f6f4a8dc8f8019535fbb2a395f`。运行器已进入第二个
unit，task `99a42d6882bac42a2b7e465638bbcf57354718054480065a25c0487a3d5adf8c` 的 private
checkpoint 为 `2/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

## r14 screening 进度快照（2026-08-19 23:53 CST）

r14 第二个 `mmlu_pro_official_test_2026_07_20` unit 已自然终态完成：task
`99a42d6882bac42a2b7e465638bbcf57354718054480065a25c0487a3d5adf8c`，完整 `112/112`
case，`scored_case_count=112`、transport failure `0/112`、failure rate `0.0`，reason
codes 为空；mean score `0.848214285714`，p50/p95 latency
`7163.040ms/25988.358ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=2`、`failed_or_blocked_unit_count=0`、`ready_for_ranking=false`；
state SHA-256 为 `2d69d5d847cc29d5df82855ae341e7ea0084895c70d4f5cf21348c6f1ff34cc8`，
campaign digest 为 `432413b2a8312158f1c28d6673ed27c0ebf8ef03299c0bcc6bcc43505744a79a`。
运行器已自动进入第三个 task `8172ac60d181dd7bbdcd78e0481af36cba1d342f38e7ea5aeb3e548177326828`，
private checkpoint 为 `2/102`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

## r14 screening 进度快照（2026-08-20 00:22 CST）

r14 第三个 unit 已自然终态完成：task
`8172ac60d181dd7bbdcd78e0481af36cba1d342f38e7ea5aeb3e548177326828`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.754901960784`，p50/p95 latency
`12490.977ms/35899.950ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=3`、`failed_or_blocked_unit_count=0`、`ready_for_ranking=false`；
state SHA-256 为 `d08873dff6efa3b10f657fcb4aedd306bddf0cc4627ecc8b5c1555a81969e409`，
campaign digest 为 `8b77d0094a34a8c7ed69f9f7a0f1cb54d726ec9e4f08597513406d38ba1673c5`。
运行器已自动进入第四个 task `23042b50a134f1e3f11dc98b2af5100d059723861ebc4990995a2f4d5ff715a`，
private checkpoint 为 `0/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

## r14 screening 进度快照（2026-08-20 00:33 CST）

r14 第四个 unit 已自然终态失败：task
`23042b50a134f1e3f11dc98b2af5100d059723861ebdc4990995a2f4d5ff715a`，完整 `112` case
分母中仅 `scored_case_count=9`，transport failure `103/112`、failure rate
`0.919642857143`，触发冻结的 `2%` fail-fast gate；reason code 为
`screening_unit_transport_failure_rate_exceeded`，p50/p95 latency
`50839.414ms/90087.512ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=3`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
state SHA-256 为 `f5671720569d866782cdf7e0604ab591ad20c0fe1b9b02192f602542eed6d6b1`，
campaign digest 为 `95b172f2cb42852ff7abfeabe838be0e9389655658fdabbd9669920a9af79c4d`。
运行器已自动进入第五个 task `b8ca59ff11f37f3a5ba609e1dba4f9bdf592d60bc3e24b61a1f5bb5530d7acc2`，
private checkpoint 为 `8/102`；失败 unit 保留在完整分母中，不恢复、不拼接、不触发 ranking 或
target benchmark。

## r14 screening 进度快照（2026-08-20 00:50 CST）

r14 第五个 unit 已自然终态完成：task
`b8ca59ff11f37f3a5ba609e1dba4f9bdf592d60bc3e24b61a1f5bb5530d7acc2`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.754901960784`，p50/p95 latency
`10284.959ms/22983.527ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=4`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
state SHA-256 为 `dc14381aa048318fdd6f16adea0d270cf53afbc4286d78a40214cf5c121bba6c`，
campaign digest 为 `376ebe529d128b1a85afbcc18e6127022e3c72c61fb20f49cfa59d0fc1b9ea7e`。
运行器已自动进入第六个 task `c4f5145ed59a6f45b87779da2f7211ed024a6c7fb030845c3f0fd3dc005ef835`，
private checkpoint 为 `1/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

## r14 screening 进度快照（2026-08-20 01:20 CST）

r14 第六个 unit 已自然终态完成：task
`c4f5145ed59a6f45b87779da2f7211ed024a6c7fb030845c3f0fd3dc005ef835`，完整 `112/112`
case，`scored_case_count=111`、transport failure `1/112`、failure rate
`0.008928571429`，低于冻结的 `2%` gate，reason codes 为空；mean score
`0.864864864865`，p50/p95 latency `13592.488ms/30939.008ms`。campaign 仍为
`status=running`、`planned_task_count=16`、`completed_unit_count=5`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；state SHA-256 为
`b5ebfaf7e0900573fe58a1f0befeb93105a270d1df480c6d52dec37107ef508f`，campaign digest 为
`473087a3e4dc1d6bcab4fa151d309d27eb8eb904a6e0968d5f0b3a1fdc5702b1`。运行器已自动进入第七个
task `6eaa0f8c67c41d730c04341f002617100aabe5859980653683e56c5493b04400`，private
checkpoint 为 `1/102`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。

## r14 screening 进度快照（2026-08-20 01:50 CST）

r14 第七个 unit 已自然终态完成：task
`6eaa0f8c67c41d730c04341f002617100aabe5859980653683e56c5493b04400`，完整 `102/102`
case，`scored_case_count=102`、transport failure `0/102`、failure rate `0.0`，reason
codes 为空；mean score `0.745098039216`，p50/p95 latency
`13063.101ms/33250.024ms`。campaign 仍为 `status=running`、`planned_task_count=16`、
`completed_unit_count=6`、`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`；
state SHA-256 为 `88da71b37c84853265d16f0b857b5770b3466d2b5c4ec9d0653ee1bf43da50bb`，
campaign digest 为 `1ef641d774f872f06ebbcb8ca95f79c8fdf80764b0897e358f5b20830a57b366`。
运行器已自动进入第八个 task `c320006a0f407b64da094d08e9029b54020055229f5f0ad69764b2d722a4bf13`，
private checkpoint 为 `2/112`；完整 16-unit 分母、2% gate 和 target 禁止标志不变。
