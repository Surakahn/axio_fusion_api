# r18 Live Screening 决策包（2026-08-21）

## 决策问题

是否在不修改 r18 immutable plan、不恢复旧 checkpoint、不拼接 survivor subset、不
降低固定 2% transport gate 的前提下，启动唯一一套 r18 remote-only non-target
screening？

这是一次可能产生真实 provider API 调用、延迟和渠道成本的外部执行，因此不能由
离线 preflight 或普通 route-plan dry-run 隐含批准。

## 当前事实

- Goal 仍为 active，产品契约是 remote-only Fusion API，公共模型只有
  `axio-fast`、`axio-terra`、`axio-pro`。
- 工程基线已通过：`1076 passed, 7 skipped`；四协议、图片隔离、safe trace 和
  Harness 控制面已有离线证据。
- r17 已 terminal，但 transport admission blocked：16/16 unit、6 completed、
  10 failed，8 canonical 中只有 1 个通过两个 source family 的 2% gate，minimum
  为 3。r17 没有生成 ranking、baseline freeze 或 target result。
- r18 已 immutable 且 zero-network preflight ready：2 source families、8 canonical、
  9 replicas、16 serial units、`max_workers=1`、固定 2% fail-fast；
  `network_calls_performed=false`、`target_suite_calls_performed=false`、
  `target_suite_calls_allowed=false`。
- r7 probe-bound registry hash 为
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；r18 plan、
  source 和 r7 operational admission 的内容绑定已经通过只读复核。
- 当前网络状态为 `auto -> proxy`，10808 listener 正常，生产 `/health` 为 ready；
  这只是工程健康证据，不是 provider 能力证据。

## 方案比较

| 方案 | verdict/action | 优点 | 代价与风险 |
| --- | --- | --- | --- |
| A. 授权 r18 live screening（推荐） | `neutral / continue` | 获得完整 transport 分母，才能决定 admission、ranking 和 baseline freeze | 产生 provider API 成本；90 秒硬上限和完整分母可能再次导致 blocked |
| B. 暂缓并继续只读复核 | `neutral / request_user_decision` | 零新增网络成本，保持当前可恢复安全状态 | 不会获得新的 transport evidence，Goal 停在 screening gate |
| C. 另注册 transport diagnostic successor | `neutral / branch` | 可单独区分 timeout、5xx、empty output、source workload 交互 | 需要新 plan、额外调用和新的 lineage；不能替代 r18 formal screening |

## 推荐动作与严格边界

推荐方案 A，但只有 operator 明确回复授权后才执行。执行时必须：

1. 启动前再次只读校验 PID/命令行、r18 plan/source/registry/admission hash、proxy
   选择和工作树；使用 `setsid/nohup`，`max_workers=1`。
2. 只启动一套 r18 `baseline-screening-run --live`，不启动第二套，不使用
   `--retry-failed`，不恢复 r17/r18 checkpoint，不修改 frozen plan。
3. screening terminal 前不运行 transport conversion、ranking、provider freeze、
   Harness import 或 target benchmark；supervisor/watcher 始终保持
   `target_suite_calls_allowed=false`。
4. terminal 后只按同一 lineage 执行
   `transport admission -> complete-pool ranking -> external top-three -> provider
   baseline freeze`；任一 gate 失败就保留完整分母并创建 successor，不把 partial
   score 当作能力证据。

## 授权回复格式

请明确回复以下之一：

- `授权 r18 live screening`：接受真实 provider 调用、90 秒 hard ceiling、完整
  2% transport gate 和上述不恢复/不降 gate 边界。
- `暂缓 r18`：继续只读审计，不产生 provider 请求。
- `注册 diagnostic successor`：先设计独立 transport diagnostic plan，不进入
  formal r18 screening。

在收到明确授权前，本决策包的状态为 `target_calls_allowed=false`，Goal 保持 active，
不宣称项目完成或模型 superiority。
