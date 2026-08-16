# Composite r1 收敛监督器

`scripts/continue_composite_convergence.py` 是 composite r1 screening 的终态
监督器。它只连接已经冻结的 screening plan、当前运行进程和两个离线质量门：

```text
running screening
  -> PID/plan identity check
  -> terminal state
  -> transport admission
  -> screening-to-ranking (仅 admission ready)
```

它不是新的 screening runner，也不是 benchmark runner。监督器不会修改 frozen
plan，不会重试已完成 case，不会创建 successor plan，不会读取或输出答案/标签，
也不会启动 target-suite provider 请求。任何 `partial`、`blocked`、`failed` 或
transport gate 不通过的结果都保留为阻塞 receipt，由后续人工创建新的 immutable
cohort；旧 cohort 不得直接恢复或混入新 cohort。

## 当前 r1 启动模板

在 `/home/he/axio_fusion_api` 下运行。`--private-probe-file` 必须与 frozen plan
使用的所有 probe 文件完全一致；不要把历史 cohort 的 probe 追加进来。

```bash
setsid nohup env PYTHONPATH=src python3.11 \
  scripts/continue_composite_convergence.py \
  --pid 103071 \
  --registry private/runs/2026-08-16-composite-cohort-r1/registry.composite.from-probe.private.json \
  --plan private/runs/2026-08-16-composite-cohort-r1/baseline_screening_plan.composite.private.json \
  --source-manifest private/runs/2026-08-14-core-cohort-final/source_manifest.core.private.json \
  --private-probe-file private/runs/2026-08-13-core-cohort/provider_probe.core.private.json \
  --private-probe-file private/runs/2026-08-16-nvidia-candidate-cohort-r5/provider_probe.prefusion.private.json \
  --private-root private/runs/2026-08-16-composite-cohort-r1/screening_campaign/retry1 \
  --state private/runs/2026-08-16-composite-cohort-r1/screening_state.composite.retry1.live.private.json \
  --screening-output private/runs/2026-08-16-composite-cohort-r1/screening_run.composite.retry1.live.private.json \
  --transport-admission-output private/runs/2026-08-16-composite-cohort-r1/transport_admission.composite.retry1.private.json \
  --ranking-output private/runs/2026-08-16-composite-cohort-r1/external_ranking.composite.retry1.private.json \
  --receipt-output private/runs/2026-08-16-composite-cohort-r1/composite_convergence_supervisor.safe.json \
  --lock-file private/runs/2026-08-16-composite-cohort-r1/composite_convergence_supervisor.lock \
  > private/runs/2026-08-16-composite-cohort-r1/composite_convergence_supervisor.console.log 2>&1 &
printf 'PID=%s\n' "$!"
```

启动后只检查监督器 PID、console 日志的事件名和 hash-only receipt。若 screening
进程意外退出但 state 仍是 `running`，监督器会 fail-closed；不得直接使用
`--retry-failed` 恢复同一个 frozen plan。应先保存现有私有 checkpoint，再创建
新的 successor plan 并重新走 zero-network preflight。

## 终态判定

- `transport_admission.status=ready`：才允许执行一次
  `baseline-screening-to-ranking`，并将 transport receipt 绑定进去。
- admission 非 ready：不执行 ranking，receipt 中记录 blocker；当前 cohort 的
  transport 证据只能用于决定 successor candidate population。
- ranking conversion 非 ready：不生成 baseline freeze，不启动 Harness target
  campaign。
- ranking ready 也只表示完整 screening 已转为外部 ranking 输入；仍需独立排名
  证据、provider baseline freeze、官方 Harness imports、API parity、统计和 final
  audit，不能据此宣称 superiority。

监督器 receipt 仅保存文件内容 hash、digest、状态、reason code 和禁止事项标志；
不会保存原始 provider URL、API key、prompt、label、answer、output 或私有路径。
