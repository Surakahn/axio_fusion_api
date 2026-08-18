# Composite r10 Harness successor 控制面（2026-08-18）

## 目的与边界

r10 是 r9 transport admission blocked 后注册的全新 immutable successor。本阶段只
建立与 r10 plan/state 对齐的离线 Harness 控制面，不恢复 r9，不拼接 r9 completed
subset、ranking、freeze 或 binding，也不发 provider/target 请求。Harness pin ready
只表示 checkout、dataset snapshot 和 evaluator 可以被 hash-only 验证，不表示质量
排名、provider freeze 或 target campaign 已获授权。

## r10 输入

- screening plan digest：`f779424f4d6846de97a24da8d5c15ebbce2253c53bca592ccba7ac5b0564cfa8`；
  8 个 canonical groups、2 个 source families、16 个 serial units、`max_workers=1`。
- zero-network preflight campaign digest：`6ff8b0c6399d6ee76489f2b14e093e146be43730b249770314e02fa795563d8f`；
  `network_calls_performed=false`、`target_suite_calls_performed=false`。
- 当前 r7 probe-bound registry hash：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`。
- Harness 使用已验证的本地 pinned checkout、raw snapshot 和 BFCL V3 checkout；r7 的
  21-suite dataset/source/case manifest 只作为不可变基础输入，不携带 r7/r9 的
  screening、ranking 或 provider 结果。

## 物化结果

输出目录为 `private/runs/2026-08-18-composite-cohort-r10/harness_control.successor/`，
所有输出均为 safe/hash-only receipt：

- `harness_pin_manifest.composite.successor.safe.json`：6/6 suite ready、0 blocked、
  BFCL V3 marker 通过；sha256
  `22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`。
- `benchmark_acquisition_checklist.composite.successor.safe.json`：`template_ready`；
  sha256 `650e3dbb33f0977441cd3a8bb690e504a72c29675e4cb2a2429755bab0977fa3`。
- `benchmark_import_batch_template.composite.successor.safe.json`：等待 operator-owned
  official import receipt；sha256
  `a819a4cb9acf539c054ac161ca30964e38215aee440d1cf48465107ac60beb7e`。
- `benchmark_acquisition_status.composite.successor.safe.json`：尚未达到可组装条件；
  sha256 `3d6bedb50ccc6d72c265773819a1ede7968ab0eddacf92419a12ab9e23ed905f`。
- `official_harness_execution_plan.composite.successor.safe.json`：`ready_to_execute`；
  sha256 `8b8b68fb99c89149dd42c05a1618a83930a6c15b7e6d8e17075cffdcff8a8974`。
- `official_import_audit.composite.successor.safe.json`：等待同 cohort freeze/import；
  sha256 `1761a3888b970b7fff6e24ca18008fd3fbff880300f3f26c4d67991279da6cc8`。
- `composite_harness_cohort_binding.successor.safe.json`：因 screening、transport、
  ranking 和 freeze 尚未 ready 而 blocked；sha256
  `0c080bf99a096d15bf78135debfc28c4d62151cac52e660de4fa766f74deeb3e`。
- `composite_convergence_audit.safe.json`：`status=blocked`、`next_gate=screening`；
  sha256 `de7aa8379e3869b3c25a377fc52d57154d74694411d1240c91101aa8d1f7bf99`。
- scaffold receipt：sha256
  `92a843f45f8ebd3ab0220cacdd41dee4305eda60b831e9ce7040add0255b4390`，
  `target_suite_calls_allowed=false`、`target_suite_calls_performed=false`、
  `provider_calls_performed=false`。

所有 safe receipt 的 `secrets_persisted`、raw prompt/label/provider output 等敏感字段
均为 `false`。执行命令与实际 pinned root 只保留在同一 r10 private console log，
避免将原始本地路径写入公开控制面 artifact。

## 门禁结论与下一步

当前 Harness 控制面是“pin 可用、cohort 未收敛”的 blocked 状态。r10 live non-target
screening 必须先自然 terminal；随后只有 transport admission 达到固定至少 3 个
canonical models，才允许完整候选池 ranking、provider baseline freeze 和 official
import。只有同 cohort convergence audit 返回 `ready_for_target_campaign`，才可启动
21-suite target campaign、四种 API parity 与统计/延迟/污染审计。

本阶段没有修改冻结 plan、没有恢复旧进程、没有启动 target，也没有停止或重启正式
CPA Plus 服务。
