# Composite r9 Harness successor 设计与当前状态（2026-08-18）

## 目标与边界

r9 是在 r8 screening 终态失败后创建的全新 immutable successor。它的目标是把
供应商 transport 证据、完整候选池 ranking、provider baseline freeze 和官方
Harness 评测绑定到同一条可审计 lineage，最终为三档 Fusion 模型的正式比较打开
target gate。本阶段不做无谓实验，也不把 r8 的 partial 结果、completed subset、
ranking 或 Harness binding 当作 r9 输入。

控制面固定为单向状态机：

```text
source successor
  -> frozen screening plan
  -> zero-network preflight
  -> live non-target screening
  -> transport admission
  -> complete-pool external ranking
  -> provider baseline freeze
  -> official Harness import
  -> cohort convergence audit
  -> target benchmark campaign
```

每一步只接受上一步的内容 hash、schema 和敏感字段安全声明。缺文件、digest 漂移、
候选分母不完整或 target 标志异常时，控制面必须 fail-closed；不得恢复旧 checkpoint、
拼接 partial subset 或降低三模型最低门槛。

## r9 输入冻结

- source manifest 内容 hash：
  `eda2c45d9a72cf3b0033aa7f9360c6575e91d56738b27202bb0b3e5c28bcd2f5`；
  successor receipt hash：
  `02e9ae1d9c9938c4227756884a2aeb2ea4dc633505e1e132cc84d4687668a7d7`。
- screening plan 文件 hash：
  `4f963fc8e7ce7696182a21d9da28711b944e784bf082d9c211f8d12fe6d453fb`；声明的
  plan digest：
  `9ad83ca335d1e3eaf15f28d1c8c842a5249a5e6a996b3d68156411af905a1399`。
- plan 为 `ready=true`，包含 8 个 canonical groups、9 个 physical profiles、
  2 个 source families、16 个 serial units，`max_workers=1`，预计 1712 次
  non-target provider calls。
- zero-network preflight receipt hash：
  `b8513f56cf73a96863c39bd8fbfadfa96a9ffb1c043ab504bb3463b1d569cb0a`；状态为
  `preflight_ready`，`network_calls_performed=false`、`target_suite_calls_performed=false`。

live screening 只使用 r7 通过 pre-Fusion handoff 的 probe-bound registry、r7
provider probe 和 r7 operational admission 作为 transport 输入；这些输入只验证
当前候选可调用性，不提供质量分或 ranking 结论。

## 运行监督

- screening PID：`1772237`，由 `setsid` 托管，命令行持续绑定
  `baseline_screening_plan.r9.private.json`。
- convergence supervisor PID：`1877375`，间隔 600 秒，只等待 screening terminal，
  然后依次执行 transport admission 和 ranking conversion；它不会恢复进程、修改
  frozen plan 或启动 target campaign。
- lineage watcher PID：`1891818`，间隔 600 秒重建同一 cohort 的 hash-only binding
  和 convergence audit；screening 运行期间只输出安全快照，终态后输出一次最终
  快照并退出，不执行 provider 或 target 请求。
- 当前 live state 文件 hash：
  `7a5f6d313b80a17f641493f1a2d77467b77d82d3af2f0af356f27af0dc8cf68f`；状态为
  `running`，尚未允许 ranking，`target_suite_calls_performed=false`。

## r9 Harness 控制面物化

Harness 使用既有 21-suite dataset/case manifest 和本地 pinned checkout 重新生成，
并在 r9 独立目录
`private/runs/2026-08-18-composite-cohort-r9/harness_control.successor/` 写出：

- pin manifest：6/6 suite ready，文件 hash
  `22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`；BFCL 使用
  独立 V3 checkout，版本 marker 通过；
- acquisition checklist：模板已生成，等待 provider baseline freeze；
- official execution plan：`ready_to_execute`，文件 hash
  `ab729b043e6c2fba85f62475fa09ef9c8e35af4c4f8a7620ff0d9a9013e2bb49`；
- acquisition status、official import audit：当前 blocked，原因是 freeze 和
  operator-owned official receipts 尚不存在；
- cohort binding：文件 hash
  `9053482e5845dad464233af51a6e4b6403ca02e35c57697994cc04a72a2d105d`，明确拒绝
  缺失的 ranking/transport/freeze 输入；
- convergence audit：文件 hash
  `8e8dc78bc49b83f88b6d874ac9d163fc7bec89038e96aa2fe925902e3c2b1635`，当前为
  `status=running`、`next_gate=screening`；
- scaffold receipt：文件 hash
  `c8aea21a21d5aeef4eb83dd15fa7663c23c90d6288a57cad0501d8d978ba12b8`，明确记录
  `target_suite_calls_allowed=false`、`target_suite_calls_performed=false`、
  `provider_calls_performed=false`。

虽然 pinned checkout 内容可能与前一 cohort 相同，r9 的输出路径、输入 plan/state
digest 和 cohort binding 都是独立生成的；因此 Harness 不能通过复制 r8 binding
获得授权。所有 safe artifact 均不持久化 raw prompt、label、provider output、URL、
credential 或 API key。

## Serving registry 核对

本轮只读 health 检查还发现正式 18900 进程仍为历史
`scripts/run_server_noprefusion.py`，其 registry 文件 hash 为
`09f79d3a869f81aec67036504b90ca091005dbf03d41f3b38e4db184b5268723`，加载 28 个
profile；同一文件在 `require_prefusion=true` 下会被拒绝。这是已有 serving 漂移，
不是 r9 Harness 写入造成的，因此当前 health 的 `ready` 不能替代正式 pre-Fusion
serving gate。

作为不打断 18900 的只读 staging 核验，r7 probe-bound registry
（文件 hash `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`）在
备用 18901 端口通过 `require_prefusion=true` 加载，21 profiles、4 providers、5
fast candidates，health 返回 200/ready；staging 随后已停止。一次客户端 live chat
smoke 因 10 秒超时而断开，服务日志仅留下 BrokenPipe，不能当作质量或 API 成功证据，
也没有进入 target benchmark。

正式切换已完成：保留旧 registry 文件及其 hash 作为回滚参照，优雅停止历史
`run_server_noprefusion.py`，以 `setsid` 和显式 `AXIO_FUSION_REGISTRY_PATH` 启动
`scripts/run_server.py`（当前 PID `1950874`）。切换后 health 为 HTTP 200/`ready`，
加载 21 profiles、4 providers，network 为 `auto`/`proxy`；`/v1/models` 仍只暴露
`axio-fast`、`axio-terra`、`axio-pro`。Chat/Completions、Responses、Anthropic、
Gemini 四种入口的 route-plan dry-run 均通过，三个公开模型的 strategy/role plan
与 r7 registry 一致。切换未停止 CPA Plus 正式服务，也未将旧 28-profile serving
结果带入 baseline freeze 或 superiority claim；此次验证不包含 provider live smoke
或 target-suite 请求。

## 后续决策路径

1. screening 自然终态后，监督器生成 r9 transport receipt；只有 `status=ready` 且
   至少 3 个 canonical models 通过固定 transport failure-rate gate，才执行完整
   ranking conversion。
2. 若 screening/ranking 任一完整性条件失败，保留 r9 全部分母和失败分类，写入终态
   记录，并创建新的 r10 source successor；不选 survivor、不生成 freeze、不运行
   target。
3. 若 ranking ready，先生成与当前 registry、screening state、transport receipt
   和 external top-three 证据完全绑定的 provider baseline freeze；随后重新物化
   r9 Harness binding 和 official import audit。
4. 只有 convergence audit 明确返回 `ready_for_target_campaign`，且所有 21 个
   suite 的 case/source/harness hash 和官方 import receipts 完整一致，才允许启动
   target campaign。target 产生的结果必须与 Fusion 三档及其对应单模型 baseline
   共享同一数据切片、协议和统计审计，才能进入最终 superiority claim。

本记录只描述当前控制面事实和条件路径，不把 screening 进行中或 Harness pin
readiness 误写成质量排名或商业级 superiority 结论。
