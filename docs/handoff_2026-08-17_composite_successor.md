# Composite successor r2 交接（2026-08-17）

## 已完成

- composite r1 已终态：`partial`，8/20 source-units completed，12/20
  transport-blocked；transport admission 只有 1 个 canonical model，通过不了固定
  的 3-model 最低门槛。r1 没有生成 ranking、provider freeze 或 target 请求。
- 独立 live `operational-admission` 已完成：10 个候选中 7 个
  `production_admitted`、5 个 `formal_baseline_eligible`，receipt 为 ready。该
  receipt 只作为 successor 可用性门禁，不是质量排名。
- 新 successor plan 已从零注册，未复用 r1 的 score、state 或 blocked transport
  receipt：
  - plan：`private/runs/2026-08-17-composite-cohort-r2/baseline_screening_plan.composite.successor.private.json`
  - digest：`47db05cbc07aa8f9a18c67ed44bc361423c066d322424e94d3b3f58c91ae3e29`
  - 5 canonical groups、10 serial source-units、预计 1070 次 provider calls
  - operational admission binding 为 ready；transport availability 明确为
    `not_required`
- successor live screening 已由 PID `904733` 启动，supervisor 为 `911605`，离线
  binding/audit watcher 为 `912737`。当前 state 为 `running`，0 completed、1
  failed/blocked、10 planned；`ready_for_ranking=false`。
- r2 watcher 使用独立 downstream artifact 路径；当前 binding 为 blocked，target
  calls 始终关闭。旧 r1 Harness pin/execution/acquisition 不会被隐式复用。

## 门禁与后续

1. 等 r2 screening 进入 terminal；supervisor 只在 transport admission ready 时
   执行一次 ranking conversion，并透传同一 operational admission receipt。
2. 如果 r2 仍 transport-blocked，保留完整分母，重新评估 provider/registry
   successor；不得使用 survivor subset 或降低 3-model 门槛。
3. ranking ready 后，仍需独立 external top-three ranking、provider baseline freeze、
   108 个 official import、cohort binding、target campaign、统计/延迟/污染/API
   parity 和 final audit；在这些完成前不做 superiority claim。

## 验证

- 本次 successor lineage 参数修复专项回归：`18 passed`。
- Python 3.11 全量回归：`1055 passed, 7 skipped`。
- 代码里程碑均已提交并推送；当前分支 `main` 与 `origin/main` 一致。
