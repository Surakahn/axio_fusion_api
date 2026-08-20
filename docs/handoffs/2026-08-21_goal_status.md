# Goal 状态交接（2026-08-21）

## 本轮结论

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 已恢复且仍为 `active`。Axio 的产品边界
没有改变：它是 remote-only 的 Fusion API，通过 prompt、路由、角色、Judge、
Synthesizer、fallback、预算和安全工程统一提供 `axio-fast`、`axio-terra`、
`axio-pro`；Harness 只作为评测、控制、恢复和证据链平面。

本轮完整重读并核对了：

- `docs/axio_fusion_api_product.md`；
- `docs/axio_fusion_benchmark_methodology_21_suites.md`；
- `PLAN.md`、`CHECKLIST.md`、`README.md`；
- 最新 r17 handoff、r17 terminal operation、r18 scout/decision/audit；
- `docs/operations/convergence_execution_path_r20.md`；
- r18 private plan、source、preflight、Harness convergence/import artifacts；
- 当前生产 `/health`、`/v1/models` 和三档离线路由计划。

逐域差距和证据锚点已记录到
`docs/operations/goal_gap_matrix_2026-08-21.md`，并由 `PLAN.md` 顶部链接。

## 当前真实位置

- r17：16/16 unit terminal，6 completed / 10 failed_or_blocked；transport admission
  blocked，仅 1/8 canonical 同时通过两 source family 的固定 2% gate，未生成 ranking、
  provider baseline freeze 或 target 结果。
- r18：immutable successor，2 source families、8 canonical、9 replicas、16 serial
  units、`max_workers=1`、固定 2% gate；preflight 为 `preflight_ready`，没有 provider 或
  target 请求，`ready_for_ranking=false`。
- r18 plan SHA-256：
  `58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`。
- r18 source SHA-256：
  `3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`。
- 当前服务只读状态：`ready`；3 个公共模型；21 个 physical profiles；4 个 provider；
  `auto -> proxy`；当前 serving registry 仍为 r7 probe-bound，没有重启或切换。
- 当前 registry 的 `tool_candidate_count=0`、`pricing_known_count=0`、
  `context_known_count=0`，且 Pro dry-run 的 provider diversity 仍只有一个 provider
  hash。这些是 admission/calibration 缺口，不是可以用静态先验掩盖的能力证据。
- 只读配置审计发现 `private/current_channels.env` 原先仍指向旧的 28-profile Claude
  artifact；已删除旧的重复覆盖声明，并将唯一 registry 声明精确修正为当前正式进程
  使用的 r7 probe-bound 文件。路径与文件 hash 已核对一致，正式 loopback 未重启，CPA
  Plus 未受影响。

## 本轮变更与验证

- 新增 Goal 差距矩阵：`docs/operations/goal_gap_matrix_2026-08-21.md`。
- 新增本交接：`docs/handoffs/2026-08-21_goal_status.md`。
- `PLAN.md` 增加差距矩阵入口。
- 公开 `/health` 投影已增加 hash-safe capability metadata warnings：当工具候选、价格
  或 context window 未校准时分别报告固定 reason code；不改变 `ready` 可服务语义，也不
  参与路由选择。正式 loopback 进程未为此重启，当前仍返回变更前的 `warnings=[]`；下次
  受控发布后才会加载该修复。
- `private/current_channels.env` 的 registry identity 已与正式 r7 serving identity 对齐；
  `registry-diagnostic --require-prefusion` 和 provider 配置摘要均保持零网络，且未打印
  secret 值。该修正只消除未来启动的配置漂移，不改变当前运行进程或 r18 frozen 输入。
- 使用同一 r18 plan/source/r7 registry 和 r7 operational-admission binding，额外生成了
  独立的零网络 credential-ready preflight（不覆盖原始 preflight）：
  `screening_state.r18.credentials-ready-preflight.private.json`、
  `screening.preflight.receipt.r18.credentials-ready.private.json`；两者均为
  `preflight_ready`、9/9 credential ready、`network_calls_performed=false`、
  `target_suite_calls_performed=false`，仅用于后续授权前的 hash/PID 核验。
- `python3.11 -m compileall -q src scripts`：通过。
- 控制面专项回归：20 passed。
- 全量回归：`1074 passed, 7 skipped in 272.24s`。
- 文档安全断言与 `git diff --check`：通过。

## 下一条合法动作

当前没有新的 live 授权。收到明确的“授权 r18 live screening”后，唯一允许的执行顺序是：

```text
r18 preflight/hash/PID 只读校验
 -> 单一 setsid/nohup live screening
 -> terminal screening
 -> transport admission
 -> complete-pool ranking
 -> external top-three
 -> provider baseline freeze
 -> same-cohort official/audited Harness import/convergence
 -> 9 类 21 套 benchmark
 -> paired statistics / latency / cost / contamination / final audit
```

在授权前不得修改 r18 frozen plan/source/registry，不得恢复 checkpoint、拼接 survivor
subset、降低 2% gate、修改生产 router/prompt/weights 或启动 target benchmark。若
transport 仍 blocked，保留完整分母并创建新的 immutable successor；不得把 partial score
写成能力或 superiority claim。
