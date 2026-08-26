# Goal 状态交接（2026-08-26）

## 本轮结论

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 仍为 `active`。本轮没有改变 Axio 的
remote-only 产品边界：Fusion 仍通过 prompt 流程、路由、角色编排、Judge、
Synthesizer、fallback、成本/延迟/并发预算和安全可观测性，把远程 provider 组合成
`axio-fast`、`axio-terra`、`axio-pro`；Harness 仍只是评测、控制、恢复和证据链平面。

本轮完成的是一个商业级控制面加固：官方/审计 Harness execution plan 现在必须明确
绑定 provider baseline freeze 和 `formal_top_three_cohort` 身份，不能因为 pin/template
字段完整就把 diagnostic matrix 误报为 `ready_to_execute`。

## 当前真实位置

```text
r18 screening                  preflight_ready，尚未授权 live
transport admission            未完成
complete-pool ranking          未开始
external top-three             未开始
provider baseline freeze       未开始
同 cohort official Harness    未完成
9 类 21 套 target benchmark    未开始
```

唯一合法主路径仍是：

```text
明确授权 r18 live screening
 -> terminal screening
 -> transport admission
 -> complete-pool ranking
 -> external top-three
 -> provider baseline freeze
 -> 同 cohort Harness 重建与 official/audited imports
 -> convergence=ready_for_target_campaign
 -> 9 类 21 套 benchmark
 -> paired/Holm/effect/latency/cost/contamination/final audit
```

在明确授权前没有 provider 或 target 网络调用，不恢复 checkpoint、不使用
`--retry-failed`、不拼接 survivor subset、不降低固定 2% gate，也不修改 frozen
plan/source/registry、生产 router/prompt/weights 或 serving policy。

## Serving registry 身份复核

本轮对 18900 的只读 `/health`、进程环境和 `private/serving_registry.json` 做了身份
核对：正式进程通过 `AXIO_FUSION_REGISTRY_PATH` 绑定 r7 probe-bound registry，当前为
21 个 physical profiles、15 个 logical models、21 个 live-available profiles、4 个
providers；r7 provider probe evidence audit 为 ready。AGENTS 中“r43 当前 10 个文本
physical profiles”的检查项属于历史 r43 阶段，不适用于当前 r7 serving cohort；本轮未
修改 registry、未重启服务，也未把该历史计数当作当前 blocker。

## 本轮实现

### Execution plan formal cohort gate

- `build_benchmark_acquisition_checklist()` 传播 `matrix_mode` 和 formal cohort 摘要。
- `build_official_import_batch_template()` 传播 matrix/cohort、provider selection、
  candidate/run-unit count，保持 hash-only。
- `build_official_harness_execution_plan()` 新增可选
  `provider_baseline_freeze_path`，检查 freeze schema、`final_claim_freeze_ready`、
  外部预注册 top-three、freeze digest 和固定 15 run units。
- 无 freeze 或 diagnostic matrix：状态为 `blocked`，reason code 包含
  `provider_baseline_freeze_required`、`diagnostic_matrix_not_executable`。
- formal cohort 身份、freeze、task/pin/template 合法时：状态为 `ready_to_execute`，并
  显式输出 `execution_authorized=true`；授权范围固定为
  `official_or_audited_harness_work_queue_only`，且 `target_campaign_authorized=false`。
- official import/acquisition 未齐全时不再把执行计划标成 `planned`；改由
  `post_execution_imports_complete=false` 和
  `post_execution_reason_codes=["official_import_acquisition_incomplete"]` 表达后置工作。
- Harness 执行后的 hash-only imports/acquisition、case/source/harness audit 仍必须
  完成，binding/convergence 才能继续向 `ready_for_target_campaign`。
- execution plan digest 绑定 matrix、formal 状态、freeze content digest、任务数和
  reason code；receipt 不保存 provider id、模型 id、原始路径、prompt、输出或 secret。

### 下游 fail-closed 绑定

- CLI `benchmark-official-harness-execution-plan` 接受
  `--provider-baseline-freeze`。
- `prepare_composite_harness.py` 传递 freeze 并把 formal/planning reason 投影到 stage
  receipt。
- `build_composite_harness_binding.py`、`audit_composite_convergence.py`、
  `evaluation.py` 的 readiness/cohort audit 均要求 formal cohort、execution
  authorization 和 freeze path/content digest 绑定；只有 binding/convergence 额外要求
  post-execution imports 完成。

## 新增离线证据

新的 successor 目录：

`private/runs/2026-08-26-composite-cohort-r18-harness-formal-gate/harness_control.successor/`

- pin 仍为 ready；
- execution plan 为 `blocked`，reason 包含
  `provider_baseline_freeze_required`、`diagnostic_matrix_not_executable`、
  `formal_top_three_cohort_incomplete`；
- cohort binding 为 `blocked`；
- convergence audit 为 `blocked`、`next_gate=screening`；
- `target_suite_calls_allowed=false`、`target_suite_calls_performed=false`、
  `provider_calls_performed=false`；
- 所有 safe artifact 的敏感持久化字段均为 `false`。

旧的 `2026-08-21` Harness artifact 没有覆盖或重写；新的目录只记录本轮控制面行为。

## 验证门禁

- L1：`py_compile` 通过，覆盖 evaluation、CLI、Harness scripts 和相关测试。
- L2：`axio_fusion_api.evaluation`、CLI 和 Harness 脚本导入通过。
- L3 专项：formal/diagnostic/invalid freeze、scaffold、binding、convergence 共
  `15 passed`；execution/readiness 相关 standalone 专项 `15 passed`。
- L3 全量：`1096 passed, 7 skipped`。
- `git diff --check` 通过。
- r18 frozen plan SHA-256 仍为
  `58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`；source SHA-256
  仍为 `3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`。

这些是工程/控制面证据，不是 provider 能力、排序、成本、延迟或 superiority 证据。

## 后续离线增量：健康检查物理/逻辑计数（2026-08-26）

在不改变 r18 frozen plan/source、生产 router、prompt、权重或 serving registry 的前提
下，`/health` 的 hash-safe `registry_readiness` 增加了
`available_model_count`、`logical_model_count` 和 `available_logical_model_count`。
其中 `model_count`/`available_model_count` 是物理 provider profile 计数，逻辑计数使用
运行时 canonical identity 规则；available 边界排除 disabled、明确 unavailable 和超过
90 秒 provider latency ceiling 的 profile。新增副本去重和不可用模型测试通过，未发起
provider/target 请求。该计数只支持运维容量和 failover 观察，不改变 ranking、baseline
freeze 或 target gate。

## 下一步

当前不应继续堆叠 benchmark 或静态能力先验。等待 operator 明确授权后，按 r18 原始
preflight 做一次唯一 live screening；只有 terminal 且 transport admission 通过，才
进入 ranking、freeze 和同 cohort Harness。若 transport gate 再次失败，保留完整失败
分母并创建 immutable successor，不恢复旧 partial 结果。
