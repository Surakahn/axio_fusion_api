# r7 Composite Harness successor 里程碑（2026-08-17）

## 已完成的离线控制面

- Harness pin：6/6 official checkout ready，BFCL 使用独立 V3 checkout，并通过
  `VERSION_PREFIX = "BFCL_v3"` 兼容性门禁。
- hash-only case manifest：21/21 ready，manifest digest
  `ca4b319b594a8a8cb13bcfe27805d37edf02d130a979d6333a93ab3f7d1f4106`。
- GPQA 槽位明确记录为 MMLU-Pro STEM replacement，60 条完整 disjoint 固定切片，
  effective minimum 为 60；不得在报告中写成 GPQA 原始结果。
- source manifest prepared/bound/validation：21/21 ready，source validation
  的 `all_required_sources_ready=true`。
- replacement-aware acquisition status：15/15 本地 suite ready；6 个 official
  suite 等待 operator-owned import receipts，共 108 个预期 receipt。

## 当前状态

控制面目录：
`private/runs/2026-08-17-composite-cohort-r7/harness_control.successor/`

当前 scaffold 为 `status=running`、`next_gate=screening`。r7 screening 仍由既有
setsid 进程运行，当前 16 个 serial unit 已完成 1 个；未启动 target Harness，且
`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。本阶段没有
停止或重启 CPA Plus。

## 后续门禁顺序

1. 等待 screening 自然终态，由 supervisor 生成 transport admission。
2. transport 至少满足 3 个 canonical model 后才允许 external ranking 和 provider
   baseline freeze；否则保留 terminal blocked evidence。
3. operator 完成 6 个 official suite 的 hash-only import receipts，并通过同一
   Harness pin、case manifest、source manifest 和 cohort binding 校验。
4. 只有 convergence audit 返回 `ready_for_target_campaign` 后，才允许启动 9 类
   21 套 target campaign；任何更早的 target 调用都必须保持禁止。

所有安全 receipt 均显式声明 `raw_provider_outputs_persisted=false`、
`raw_dataset_content_persisted=false`、`secrets_persisted=false`。
