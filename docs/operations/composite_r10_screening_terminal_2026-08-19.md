# Composite r10 screening 终态与 r11 successor 决策（2026-08-19）

## 终态结论

r10 immutable non-target screening 已自然终态，16/16 个 serial unit 均已到 terminal：
13 个 `completed`、3 个 `failed`，campaign `status=partial`，
`ready_for_ranking=false`，`target_suite_calls_performed=false`。失败 unit 的完整分母、
fail-fast 未尝试 case 数和 provider transport 分类继续保留在 operator-owned private
root；不恢复 checkpoint、不重试失败 unit、不从 completed subset 选择 survivor。

核心安全字段与 artifact digest：

- state schema：`axio_fusion_api.non_target_screening_campaign.v3`；
- state 文件 SHA-256：`674d2fccc86b7b723c2a8e9feeb072e77fcffaf6a2bad1db777c1222282c6ccf`；
- screening receipt SHA-256：`6a8857b236a20c608a087a015a15d29224c757eff7dc83f2b601e3883f047bf6`；
- campaign digest：`139962ba7175cddfa868088bea8bca1b783dfd8f6d807e8ee32488dcade37a33`；
- plan digest：`f779424f4d6846de97a24da8d5c15ebbce2253c53bca592ccba7ac5b0564cfa8`；
- registry digest：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- source manifest digest：`a9b557766aa07eb6175c4bb1e258e03ca12787d9bef486daeeff70f9448ccd07`；
- `raw_provider_outputs_persisted=false`、`raw_private_root_persisted=false`、
  `secrets_persisted=false`。

三个失败 unit 的 transport-only 摘要如下：

| 完整分母 | transport failure | failure rate | fail-fast 未尝试 | 终态 |
|---:|---:|---:|---:|---|
| 112 | 106 | 0.946428571429 | 103 | failed |
| 102 | 102 | 1.0 | 99 | failed |
| 112 | 112 | 1.0 | 109 | failed |

## Transport 与 ranking 判定

同 cohort supervisor 在 terminal 后只执行了 transport admission 和 ranking conversion，
没有启动 provider baseline freeze、official import 或 target Harness。

transport receipt：

- 文件 SHA-256：`4efd0f94139d3af657e3a45cde57c62622ac9ac789bccf0c5a8d21b03da51bbb`；
- `status=ready`，候选 canonical pool 为 8，transport-eligible 为 6；
- 固定最低要求为 3，且 `selection_basis=transport_failure_rate_only`；
- `quality_fields_used_for_selection=[]`，质量分、label、answer 与 provider output 未参与；
- receipt 绑定 r10 state、plan、registry、source manifest 和完整 16-unit 分母。

transport ready 只表示可用性门禁通过，不表示 campaign 已具备完整 ranking 资格。

ranking receipt：

- 文件 SHA-256：`490cdd7b39dbca4bd79fdda115977884c1e073a4778642451a33cbc1ea9eaf4e`；
- `screening_conversion_ready=false`；
- blockers：`screening_ranking_campaign_not_complete`、
  `screening_ranking_campaign_unit_not_completed`、
  `screening_ranking_candidate_source_coverage_incomplete`、
  `screening_ranking_current_inputs_mismatch`、
  `screening_ranking_source_has_incomplete_unit`、
  `screening_ranking_template_candidate_count_mismatch`。

supervisor receipt：

- 文件 SHA-256：`eaea2260a3b90c0a49ae4274845ec0ab0cac56d5d1330520e47dc3bbd86e8514`；
- `status=blocked`、`error_code=screening_ranking_conversion_blocked`；
- `ranking_ready=false`、`target_benchmark_started=false`、`plan_mutated=false`。

因此 r10 的 transport receipt 和空 ranking 槽位均为 `reference_only`，不得进入 external
ranking、provider baseline freeze、official import 或 Harness binding。

## Harness 收敛结果

lineage watcher 已在 screening terminal 后完成同 cohort 的 hash-only 重建：

- cohort binding SHA-256：`ba5539974d34963fef6503add6f8edeee35b98646aa3875bd5905d0988cb9390`；
- convergence audit SHA-256：`38d3af8203dc878fbe18378933f9e2502f9e400d7c26092f86dc7145d7494da8`；
- binding 与 audit 均为 `status=blocked`；
- `next_gate=screening`、`target_suite_calls_allowed=false`、
  `final_claim_allowed=false`、`target_suite_calls_performed=false`。

6/6 Harness pin ready 与 official execution plan 只证明离线控制面可用，不能绕过完整池
ranking 和同 cohort freeze/import 门禁。

## r11 successor 路由

r10 作为只读 partial cohort 封存。下一步只允许从 r10 source manifest 创建新的 immutable
r11 successor，仅改变 pre-registration 的 selection seed 和 registration date：

```text
r11 source successor -> frozen screening plan -> zero-network preflight
-> live non-target screening -> terminal transport admission
-> complete-pool ranking -> provider baseline freeze
-> same-cohort official import -> convergence audit
-> 21-suite target campaign
```

不得修改 r10 frozen plan、恢复 r10 checkpoint、拼接 r10 completed subset、复用 r10
transport/ranking/freeze/binding，或降低固定 3-model transport gate。r11 仍需完整执行
16 个 serial unit；只有同 cohort convergence audit 明确返回
`ready_for_target_campaign`，才允许 target 请求和后续 superiority audit。

