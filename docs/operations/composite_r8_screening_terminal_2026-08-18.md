# Composite r8 screening 终态与 successor 决策（2026-08-18）

## 终态

r8 successor 已自然退出，screening receipt 为 `partial`：16/16 source units 已到
terminal，9 个 completed、7 个 failed，`ready_for_ranking=false`，
`target_suite_calls_performed=false`。所有 safe receipt 均保持 raw provider output、
raw prompt、raw label 和 secret 隔离。

关键 artifact hash：

- screening receipt：
  `93d80a6af2c49b6e02518a01a035ebaaa7788ba87cbbdae77c60ca39d088e181`；
- transport admission：
  `04fc24ef1e9c52c2a87b3a59b31a40da0179819d66a920bab053b0c013c35523`；
- ranking conversion receipt：
  `4c17b32f8675a40549c66d91b8221de70dea767596434efe07f5a14f998fa9cb`；
- convergence supervisor：
  `5b03dfbfe054bfeef26dcee4fde4212141db8e376b4caefae7cdb8a28344b477`。

## Transport 与 Ranking 判定

transport admission 的选择依据严格为 `transport_failure_rate_only`，没有读取质量
分数。8 个 canonical candidate 中仅 3 个通过两个 source family 的严格 transport
门禁，恰好达到固定最低 `minimum_canonical_model_count=3`；因此 transport receipt
为 `ready`，但不表示完整 screening 或 baseline ranking 已完成。

screening-to-ranking 仍被拒绝，原因包括：

- `screening_ranking_campaign_not_complete`；
- `screening_ranking_campaign_unit_not_completed`；
- `screening_ranking_candidate_source_coverage_incomplete`；
- `screening_ranking_current_inputs_mismatch`。

supervisor 最终为 `status=blocked`、`error_code=screening_ranking_conversion_blocked`。
r8 ranking 文件只保留 3 个 eligible candidate inventory 和空的 rank/evidence 槽位，
不能作为 external ranking、provider baseline freeze 或 Harness binding 输入。

失败 unit 的安全摘要显示两类可观测 transport 问题：部分 candidate/source 组合
出现 provider HTTP 500；另一些出现 HTTP 429 rate limit 与 provider request timeout，
均在 transport failure rate 超过 0.02 后按 frozen fail-fast policy 结束。失败 unit
和未尝试 case 分母全部保留，不恢复、不重试、不与 completed subset 拼接。

## Successor 决策

r8 不能晋级 ranking/freeze/Harness authorization。按 immutable cohort 规则，下一步
只能创建新的 r9 source successor：保留 r8 全部 state、checkpoint、transport、ranking
和 supervisor 证据，只改变 successor selection seed；r8 plan、Harness scaffold、
completed subset 和任何 partial score 不得复制为 r9 结果。

r9 仍必须经过完整的：

```text
source successor -> frozen screening plan -> terminal transport admission
-> complete-pool ranking -> provider baseline freeze -> cohort-bound Harness
```

在 r9 convergence audit 返回 `ready_for_target_campaign` 前，target benchmark 调用
继续保持禁止，不能声明任何 Fusion superiority。
