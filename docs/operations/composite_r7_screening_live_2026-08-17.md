# Composite r7 Screening Live 运行记录（2026-08-17）

## 启动门禁

r7 admission 与 zero-network preflight 已通过后，使用同一 immutable plan 启动 live
non-target screening。当前唯一活动 screening 进程为：

- PID：`3531095`（必须通过 `baseline-screening-run` 与 r7 plan fragment 身份检查）；
- registry：`private/runs/2026-08-17-composite-cohort-r7-prefusion-full/runtime_registry.probe-bound.r7.private.json`；
- plan：`private/runs/2026-08-17-composite-cohort-r7/baseline_screening_plan.r7.private.json`；
- source manifest：`private/runs/2026-08-17-composite-cohort-r7/source_manifest.successor.r7.private.json`；
- private probe：r7 pre-Fusion provider probe artifact；
- admission：`private/runs/2026-08-17-composite-cohort-r7/operational_admission.r7.private.json`；
- execution：`max_workers=1`、frozen fail-fast transport gate、2 source families、16 serial units；
- state/receipt/log 均位于 `private/runs/2026-08-17-composite-cohort-r7/`。

当前仍禁止 target-suite calls、prompt tuning、ranking、provider freeze 和 superiority
claim；原始 provider output 仅允许在 operator-owned private root 内存/恢复使用。

## 启动失败证据

第一次启动读取了 preflight state，因 `mode=preflight` 与 live credential readiness
digest 不一致而 fail-closed，receipt 保留为
`screening_start.r7.credential-mismatch.blocked.private.json`。该次
`network_calls_performed=false`，没有 provider traffic。

修复方式是保留 preflight state 为独立证据并从全新 live state 启动；没有修改 plan、
重用 completed subset 或拼接任何结果。第二次 live 进程已通过 9/9 credential readiness
检查并进入 provider screening。

## 后续终态处理

低频 watcher 只读取 PID、state 的 status/unit 计数、campaign digest 和 safe flags。进程
自然终态后，先验证完整分母与 transport gate；若 `ready_for_ranking=false`，写入 r7
screening terminal 文档并创建 successor；若 transport ready，才允许独立生成 ranking
receipt。任何情况下均不修改本 plan 或恢复另一 cohort 的 checkpoint。

