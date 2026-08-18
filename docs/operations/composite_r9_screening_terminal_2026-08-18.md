# Composite r9 screening 终态与 r10 successor 决策（2026-08-18）

## 终态结论

r9 immutable screening 已自然终态，完整执行 16/16 个 serial source units，state
为 `partial`：3 个 unit `completed`、13 个 unit `failed`。所有计划 task id 均已
出现且为 terminal，`ready_for_ranking=false`，`target_suite_calls_performed=false`。
失败分母、fail-fast 未尝试 case 数和私有 checkpoint 均保留在 operator-owned private
root；不恢复、不重试、不从 completed subset 选择 survivor。

screening receipt 的关键安全事实：

- schema：`axio_fusion_api.non_target_screening_campaign.v3`；
- state 内容 SHA-256：`5e4c804936e09b35dfb66074adbd18d4b7af8c23d43ef4261f2e5e6d0b94cb27`；
- campaign digest：`454c86d7932d3479f9f52ff36f25bc1804a1c21eda4af470b489dd375ad038b3`；
- plan digest：`9ad83ca335d1e3eaf15f28d1c8c842a5249a5e6a996b3d68156411af905a1399`；
- registry 内容 SHA-256：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- `network_calls_performed=true`，`target_suite_calls_performed=false`；
- `raw_provider_outputs_persisted=false`，`raw_private_root_persisted=false`，
  `secrets_persisted=false`。

安全 screening receipt 文件内容 SHA-256 为
`c48cdc1d5a0a398ed82b3210939d7d0d1382c8b0d825939a98ebb13ffb4e981c`。

## Transport admission

同 cohort supervisor 在 screening terminal 后唯一执行了 transport-only admission，
没有执行 ranking conversion。transport 只按 failure rate 判定，不读取质量分、答案
内容或 target 结果：

- transport receipt：`status=blocked`；
- receipt 内容 SHA-256：`b54f91b31937721f50c3ea006881c3cef7c8452ee7e5a039479fc21820883bda`；
- 候选 canonical pool：8；
- 跨两套独立 source family 通过 transport gate：1；
- 固定最低要求：3；
- blocker：`transport_admission_fewer_than_minimum_models`；
- selection basis：`transport_failure_rate_only`；
- `quality_fields_used_for_selection=[]`。

supervisor receipt 内容 SHA-256 为
`abf148820d6aaf30994a453d48306d30bfda63a5f78ef0da4c3ee54acd1a407f`，其状态为
`blocked`、`error_code=transport_admission_blocked`、`ranking_ready=false`，并确认
`target_benchmark_started=false`、`plan_mutated=false`。由于 transport 未达到固定
3-model gate，r9 没有 ranking、provider baseline freeze、official import 或 target
请求。

## Harness lineage 结果

r9 Harness 控制面仍按预期 fail-closed。screening terminal 后 lineage watcher 已完成
最终 hash-only binding/audit：

- cohort binding：`status=blocked`，digest
  `da056df0c135ecb971a932f677528ad4827dab3214c4b28f0c7a4ede4d5245d4`；
- convergence audit：`status=blocked`、`next_gate=screening`；
- audit 内容 SHA-256：`a49a11de99aff21dd901745f9621510b4eb0f114c656f8c7c7ee9dae5c6f49f9`；
- `target_suite_calls_allowed=false`、`final_claim_allowed=false`；
- 缺失 ranking/freeze/import 的原因均保留为安全 reason code，不以模板或旧 cohort
  artifact 填充。

6/6 Harness pin ready、BFCL V3 marker 和 official execution plan 的离线 readiness
仍然只是控制面准备度，不构成 target 授权或模型质量结论。

## Successor 路由

r9 作为只读失败 cohort 封存。下一步只允许注册新的 immutable r10 source successor，
仅改变 predecessor lineage 的 selection seed/registration date；r9 plan、checkpoint、
completed subset、transport receipt、空 ranking 槽位和 binding 不得复制为 r10 结果。
r10 必须重新完成：

```text
r10 source successor -> frozen screening plan -> zero-network preflight
-> live non-target screening -> terminal transport admission
-> (至少 3 个 canonical models 时) complete-pool ranking
-> provider baseline freeze -> official Harness import -> convergence audit
```

若 r10 仍不能达到 3-model transport gate，应保留完整分母并继续创建新的 successor；
不能降低 gate、恢复 r9、拼接 partial subset 或启动 target。只有同 cohort convergence
audit 明确返回 `ready_for_target_campaign`，才允许 21-suite target campaign、四种
API parity、paired statistical/latency/contamination audit 和最终 superiority claim。

正式 18900 Fusion serving 保持 `scripts/run_server.py`、21 profiles、4 providers、
`auto/proxy` 和 `ready`；本次终态转换未停止或重启正式 CPA Plus 服务。
