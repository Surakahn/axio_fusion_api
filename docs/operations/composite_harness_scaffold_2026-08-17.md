# Composite Harness Scaffold 操作说明（2026-08-17）

## 目的

`scripts/prepare_composite_harness.py` 是 screening 之后的离线控制面准备器。它
把 checklist、official import template、acquisition status、execution plan、
official import audit、cohort binding 和 convergence audit 固定到同一个 successor
目录，减少人工串接造成的异 cohort 混用。

脚本只读 registry、screening 和已存在的下游 receipt；它不发 provider 请求，不修改
冻结 plan，不恢复 screening，不启动 target Harness。生成文件使用临时文件加原子替换，
所有敏感字段必须显式为 `false`。

## 推荐调用

```bash
env PYTHONPATH=src python3.11 scripts/prepare_composite_harness.py \
  --registry <COHORT_REGISTRY> \
  --plan <COHORT_SCREENING_PLAN> \
  --state <COHORT_SCREENING_STATE> \
  --transport-admission <COHORT_TRANSPORT_RECEIPT> \
  --ranking <COHORT_RANKING_RECEIPT> \
  --provider-baseline-freeze <COHORT_PROVIDER_FREEZE> \
  --output-dir <COHORT_PRIVATE_ROOT> \
  --harness-root <PINNED_HARNESS_ROOT> \
  --raw-root <PRIVATE_RAW_ROOT> \
  --bfcl-harness-root <PINNED_BFCL_ROOT>
```

`--harness-root` 和 `--raw-root` 缺失时，pin manifest 会安全地写成 blocked，
不会用旧 Harness 目录或通用模板冒充当前 cohort。`provider-baseline-freeze`、
ranking 或 screening 尚未 ready 时，cohort binding 和 convergence audit 也会
保持 blocked/running；这不是 target 授权。

## 产物与恢复

默认产物名与 `watch_composite_convergence.py` 的 successor 输入一致：

- `harness_pin_manifest.composite.successor.safe.json`
- `benchmark_acquisition_checklist.composite.successor.safe.json`
- `benchmark_import_batch_template.composite.successor.safe.json`
- `benchmark_acquisition_status.composite.successor.safe.json`
- `official_harness_execution_plan.composite.successor.safe.json`
- `official_import_audit.composite.successor.safe.json`
- `composite_harness_cohort_binding.successor.safe.json`
- `composite_convergence_audit.safe.json`
- `composite_harness_scaffold.safe.json`

如果 screening 仍在运行，可先生成 scaffold；receipt 的 `next_gate` 应为
`screening`，`target_suite_calls_allowed` 必须为 `false`。screening terminal 后，
重新运行同一命令会用最新 safe receipt 原子重建 lineage。只有 convergence audit
返回 `ready_for_target_campaign`，且 supervisor 已完成 ranking、provider freeze、
official import 和同 cohort binding，才允许进入 target campaign。r1 的 pin、plan、
import 或 run 不能隐式复用到 r2。
