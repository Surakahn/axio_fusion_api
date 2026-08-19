# Composite r11 screening live 运行记录（2026-08-19）

## 启动绑定

r11 已在 source successor、immutable plan 和 zero-network preflight 均 ready 后启动
live non-target screening。启动使用 `setsid nohup`，未恢复 r10 checkpoint，未传
`--retry-failed`，未启动 target：

- screening PID：`3316149`；
- convergence supervisor PID：`3321068`；
- lineage watcher PID：`3321069`；
- registry：r7 probe-bound registry，SHA-256
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- plan：r11 plan digest
  `0a81e8629a0fb6948541dc3fec3d2db828b18fa7df808cf509dc5c6e69fd8aef`，文件 SHA-256
  `6bee0935c72f0f0f718bd1fb51bb5708ad245a18a2141707353538e81b81a728`；
- source manifest：SHA-256
  `ab15c0149dd85372682bc00a059096e3f884dcc71b58d1dfe391d601cce97a52`。

三进程命令行均绑定 `baseline_screening_plan.r11.private.json`；supervisor 只执行
terminal 后的 transport/ranking 转换，watcher 只写同 cohort hash-only binding/audit。

## 当前运行态

当前 state 文件 SHA-256：
`1a2de75ec2e0301541b0aaec74c422b4f230e47f290f13bc87afa5ede3fe327f`。

- schema：`axio_fusion_api.non_target_screening_campaign.v3`；
- `status=running`、`planned_task_count=16`、`completed_unit_count=0`、
  `failed_or_blocked_unit_count=1`；
- `network_calls_performed=true`（仅表示 non-target screening provider 流量）；
- `target_suite_calls_performed=false`、`ready_for_ranking=false`；
- state/plan/registry/source digest 绑定保持稳定，safe 控制面不持久化 raw provider
  output、prompt、label 或 secret。

首个 serial unit 已按预注册 fail-fast policy 终态失败：完整分母 112，transport failure
112，failure rate 1.0，3 次上游 HTTP 500 后 fail-fast，109 个未尝试 case 仍计入失败
分母。该 unit 不会恢复、重试或与其他 unit 拼接。

第二个 serial unit 的 private checkpoint 当前已完成 41/102 个 case；checkpoint 仅在
operator-owned private root 保存恢复所需原始数据，safe receipt 不复制这些内容。

lineage watcher 当前 audit SHA-256：
`5c760a206002e2c8ff7c688cf9055a9ca117d9f92b0354ac5cc90972c3e58372`，状态仍为
`running`、`next_gate=screening`、`target_suite_calls_allowed=false`。screening terminal
前不生成 transport admission、ranking、provider baseline freeze、official import 或
target 请求。

## 2026-08-19 06:48（CST）第二个 serial unit 完成

第二个 serial unit 已自然终态：完整分母 `102/102`，transport failure `0`，failure rate
`0.0`，unit 状态为 `completed`。第一个 unit 仍为 `failed`（112/112 transport failure，
109 个 fail-fast 未尝试 case），两者均继续保留完整分母和私有 checkpoint 证据。

campaign state 当前为 `status=running`、`completed_unit_count=1/16`、
`failed_or_blocked_unit_count=1`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 已更新为
`5eceb3f65cf1b432488a38da95295395c209cc5bf26a5861811eb525d758a236`。运行器已进入第三个
112-case serial unit，screening/supervisor/watcher 均仍存活，target gate 不变。

## 2026-08-19 06:57（CST）代码回归门禁

针对本阶段 Harness scaffold 受控 pin 复用入口执行完整本地回归：`1066 passed, 7
skipped`，耗时 289.73 秒；py_compile、导入检查和 composite 控制面专项测试此前均已
通过。该回归不发起 provider 或 target 请求，也不修改 r11 screening state/checkpoint。

## 2026-08-19 07:54（CST）连续 unit 里程碑

r11 继续沿冻结 plan 串行推进，新增两个完整 unit 终态：

- 第三个 unit：`102/102`，transport failure `0`，failure rate `0.0`，状态为
  `completed`；
- 第四个 unit：`112/112`，transport failure `112`，failure rate `1.0`，状态为
  `failed`；完整失败分母和 fail-fast 未尝试 case 均保留在 operator-owned private
  root，不恢复、不重试、不拼接。

campaign state 当前为 `status=running`、`completed_unit_count=2/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；本次 state 文件 SHA-256 为
`516f2ad2f2e612f0b2f23086735dacf7a4eef999416e2ca68ab6397a6eac1d50`，campaign digest
更新为 `68ffc3291b371660786b4ffc9c397a688c583a8e60627a472d9f825a2f2765f3`。

运行器已进入第五个 serial unit；最新私有 checkpoint 仅完成 `16` 个 case，仍为
partial，不能作为完整 unit 或 ranking 输入。transport admission、ranking、provider
baseline freeze、official import 与 target 请求继续不存在。

## 2026-08-19 08:05（CST）第五个 unit 完成

第五个 serial unit 已自然终态：完整分母 `112/112`，transport failure `0`，failure
rate `0.0`，状态为 `completed`。campaign state 随后更新为 `status=running`、
`completed_unit_count=3/16`、`failed_or_blocked_unit_count=2`、
`ready_for_ranking=false`、`target_suite_calls_performed=false`；campaign digest 更新为
`00a8e37f1a5b3fc66260567f19ba0d62b372cfbcd935471a27ec74116c45982e`，state 文件 SHA-256
为 `ca180d7d155abcb0bc591142346cacd97cadafbb93d65abe03a915d28dcef375`。

运行器已进入第六个 serial unit（预期完整分母 `102`），刚开始执行。此前两个失败
unit 的完整失败分母仍保留；本次里程碑不改变 frozen plan，不恢复或重试 checkpoint，
也不授权 transport admission、ranking、provider baseline freeze、official import 或
target 请求。

## 2026-08-19 08:19（CST）第六个 unit 完成

任务哈希前缀为 `83092ece6c4e3502` 的第六个 serial unit 已自然终态：完整分母
`102/102`，transport failure `0`，failure rate `0.0`，状态为 `completed`。campaign
state 当前为 `status=running`、`completed_unit_count=4/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 更新为
`59c8f48c8f3098773e3c7090329abad52c9fd2eb7b2601584689e2b9f9def743`，state 文件
SHA-256 为 `f0fdd5d0438fba828dd52dae6e5cf0c2c580e89d3ee9a1589fcd3fbf05b56782`。

运行器已进入下一个 serial unit（任务哈希前缀 `ddc6e3f3bf176b77`，预期完整分母
`112`），当前 checkpoint 仅有 `2` 个 completed case。r11 仍未 terminal，因而
transport admission、complete-pool ranking、provider baseline freeze、official import
与 target 请求全部保持关闭。

## 2026-08-19 09:11（CST）第七个 unit 完成

第七个 serial unit（任务哈希前缀 `ddc6e3f3bf176b77`）已自然终态：完整分母
`112/112`，其中 `111` 个 case completed、`1` 个 transport failure，failure rate 为
`0.008928571429`，低于预注册的 `0.02` fail-fast 门槛，因此 unit 状态为
`completed`。campaign state 当前为 `status=running`、`completed_unit_count=5/16`、
`failed_or_blocked_unit_count=2`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 更新为
`fd0a6812886f8fe4b102b75fba55d64223af6b702637d88bd99e3f0b2cc0d352`，state 文件
SHA-256 为 `14cc904d0578cdd5c88eb1964dd0f325b675d6ce5c5fe8a119c0c9bd062d8bd5`。

运行器已进入第八个 serial unit（任务哈希前缀 `419f1f94e11175a2`，预期完整分母
`102`），当前 checkpoint 仅完成 `1` 个 case。该 transport failure 只按 unit 完整
分母记录，不改变 ranking 规则；r11 尚未 terminal，所有后置 gate 继续关闭。

## 2026-08-19 09:17（CST）第八个 unit 失败

第八个 serial unit（任务哈希前缀 `419f1f94e11175a2`）已按冻结的 fail-fast 规则自然
终态失败：完整分母 `102/102`，其中 `6` 个 case completed、`96` 个 transport
failure，failure rate 为 `0.941176470588`，reason 为
`screening_unit_transport_failure_rate_exceeded`。未将这部分结果提升为质量排名，也
未恢复或重试该 unit 的 checkpoint。

campaign state 当前为 `status=running`、`completed_unit_count=5/16`、
`failed_or_blocked_unit_count=3`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 更新为
`2e80f8178ef56c08f3a5f5462ef77d2673d57df86f36ea7af3899b65f1ed46df`。

运行器已创建下一个 serial unit 的私有 checkpoint（任务哈希前缀
`fcf6ccd4e1017dc0`），当前为 `0` 个 case 的 partial checkpoint。r11 尚未 terminal，
transport admission、complete-pool ranking、provider baseline freeze、official import
与 target 请求继续关闭。

## 2026-08-19 09:22（CST）第九个 unit 失败

第九个 serial unit（任务哈希前缀 `fcf6ccd4e1017dc0`）已按冻结的 fail-fast 规则自然
终态失败：完整分母 `112/112`，其中 `4` 个 case completed、`108` 个 transport
failure，failure rate 为 `0.964285714286`，reason 为
`screening_unit_transport_failure_rate_exceeded`。该 unit 的完整失败分母已保留，
不恢复、不重试，也不将 partial score 送入 ranking。

campaign state 当前为 `status=running`、`completed_unit_count=5/16`、
`failed_or_blocked_unit_count=4`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 更新为
`ff7882142d41635a617338de706e2b5892fa0cc6b68d78206175f0b53632fa95`，state 文件
SHA-256 为 `1ea682b96905ced1ff003a6ccbb40e8691b4684dbc610874126c3b4dbeaf51d4`。

运行器已继续创建下一个 serial unit 的私有 checkpoint（任务哈希前缀
`ab610273afe7c2e8`），当前尚无 case。r11 尚未 terminal，transport admission、
complete-pool ranking、provider baseline freeze、official import 与 target 请求继续
关闭。

## 2026-08-19 10:08（CST）第十个 unit 完成

第十个 serial unit（任务哈希前缀 `ab610273afe7c2e8`）已自然终态完成：完整分母
`102/102`，transport failure `0`，failure rate `0.0`，状态为 `completed`。完整 unit
artifact 的 SHA-256 为
`194588ff51a01fc26102b963aa8f5255680008fb3a651f2e104f2b78a39bde3a`；raw provider
output 仅保留在 operator-owned private artifact，safe state 仍为
`raw_provider_outputs_persisted=false`、`secrets_persisted=false`。

campaign state 当前为 `status=running`、`completed_unit_count=6/16`、
`failed_or_blocked_unit_count=4`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 更新为
`6120db192fc456363866abc5933031ac75e9212aac006c8ae62ce1320dec92de`，state 文件 SHA-256
为 `d0ff9b3390d0df905e8a29fe613dce9816950d9b6916c50648dc9a13a9823433`。

运行器已进入第十一个 serial unit（任务哈希前缀 `a209fed42927c1f2`，预期完整分母
`112`），当前 checkpoint 仅完成 `3` 个 case，仍为 `partial`。r11 尚未 terminal，因而
transport admission、complete-pool ranking、provider baseline freeze、official import
与 target 请求继续关闭；不恢复或重试历史失败 unit，不拼接 completed subset。

## 2026-08-19 11:09-12:24（CST）第十一个至第十四个 unit 完成

r11 在冻结 plan 下继续以单 worker 串行推进，新增四个完整 unit 终态，均保留完整分母
与 operator-owned private artifact：

- 第十一个 unit（`a209fed42927c1f2`）：`112/112`，transport failure `0`，状态为
  `completed`；unit artifact SHA-256 为
  `ecd2d7620445dc5e712171f0eeaafe6353591bd730d54e18e6e32aedd8a3b171`，对应 state
  文件 SHA-256 为 `34941ea71f8a8e040bb48e50643e528fa43f9320e9386668b64e56bbfb02aed8`。
- 第十二个 unit（`120475a48c00dff3`）：`102/102`，transport failure `0`，状态为
  `completed`；unit artifact SHA-256 为
  `ae1beea116168d9e85c335bf7733056f08a7617932dd7bee57f283460aa851fe`，对应 state
  文件 SHA-256 为 `4bb5b17208391518e0146651094da5c6338f65e05e63d848dff120e861f51959`。
- 第十三个 unit（`ffb0c3e760b979b2`）：`112/112`，其中 `111` 个 case completed、
  `1` 个 transport failure，failure rate 为 `0.008928571429`，低于预注册的 `0.02`
  门槛，状态为 `completed`；unit artifact SHA-256 为
  `b3a7a2d9594c372e9e013d7dabda48602c44bca7deb24a1b1f3ce87b9019a156`，对应 state
  文件 SHA-256 为 `9b918a221f08847c870701a61f4b1d119c9c6bf19ee59f034dcacf6724bea6f6`。
- 第十四个 unit（`fdb63ffeccb10c0f`）：`102/102`，transport failure `0`，状态为
  `completed`；unit artifact SHA-256 为
  `e97208000eea510bb96223cbfc83ffab94b9255533c3c2023e06f49ec08439ce`，对应 state
  文件 SHA-256 为 `2b317dd8499ecff1d6f50c7187ebb0d879553f33f7c2d5b0b88c231e12a10952`。

当前 campaign state 为 `status=running`、`completed_unit_count=10/16`、
`failed_or_blocked_unit_count=4`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；campaign digest 为
`e6ecab5c19644513d1eb82a3f853a2d0da80bef4b220949e3340728bf0e54369`。运行器已进入第
十五个 serial unit（任务哈希前缀 `8377e611e7dea9c5`，预期完整分母 `112`），当前
checkpoint 为 `52/112`、状态为 `partial`。r11 仍未 terminal，所有 post-screening
gate 与 target 请求继续关闭。

## 固定后续顺序

```text
screening terminal -> transport admission (failure-rate only)
-> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit
-> ready_for_target_campaign -> 21-suite target
```

若 r11 仍为 partial 或 complete-pool ranking 被拒绝，保留完整分母并创建新的 immutable
successor；不降低固定 3-model gate，不选择 completed subset，不声明 superiority。
