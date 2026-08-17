# Composite r7 Admission 与 Screening Preflight 终态（2026-08-17）

## Operational admission 终态

r7 probe-bound registry 的固定 non-target operational admission 已自然终态：

- candidate profiles：21；production admitted：15；formal baseline eligible：9；
- `status=ready`、`mode=live`，没有 blocker；
- 固定 workload 合同为 5 个 workload、`repetitions=1`、`max_workers=1`、单次
  `timeout=90` 秒、failure-rate threshold `0.25`、至少 3 个成功 workload；
- `target_benchmark_cases_or_labels_used=false`、`raw_provider_outputs_persisted=false`、
  `secrets_persisted=false`；safe receipt 额外固定 raw provider name/model/url 与
  credential 均未持久化。

private admission receipt 的内容 SHA-256 为
`bf6db0c659b728a6d4c0a8e5d99c1fb9b66e1f70ec96977de048fd393c77af12`；safe receipt
只保留 hash、计数、协议和 latency/error 聚合。r7 registry 与 source manifest 保持
同一 successor lineage，旧 r6 evidence 未读取用于筛选。

## Immutable screening plan

由于 formal eligible canonical 数为 9，已达到固定三模型最低门槛，因此使用 r7
successor source manifest、probe-bound registry 和 private admission receipt 创建新的
immutable screening plan：

- plan schema：`axio_fusion_api.non_target_screening_plan.v3`；
- plan file SHA-256：`41be4597e9d214c688f3ea6b1cd3c5ab5a3a98fe65161360b8768576de65d40f`；
- plan digest：`1ba163ddacacd2ab1c77549789532f930d5cd595e84ed07251bf46a50d586444`；
- 2 个独立 source family、8 个 canonical groups、9 个 physical profiles、16 个
  serial units，预计 1712 次 provider calls；
- `min_cases_per_source=100`、`max_workers=1`、fail-fast transport gate；
- `ready=true`，敏感字段均为 `false`，尚未生成 ranking/freeze。

## Zero-network preflight

首次 preflight 因命令未传 admission receipt，按设计产生
`screening_plan_current_inputs_mismatch` blocked receipt；该失败证据保留为
`screening_preflight.r7.missing-admission.blocked.private.json`，没有网络调用。

补齐与 plan 完全相同的 admission input 后，新的 preflight 已通过：

- state status：`preflight_ready`；
- campaign digest：`5b18225195bcb9516ec0ede94012978b0f45c481874bbd99963c59347cda64d`；
- plan/registry/source/admission binding 一致；
- `network_calls_performed=false`、`target_suite_calls_performed=false`；
- 16/16 task 已 materialize，`raw_provider_outputs_persisted=false`、
  `secrets_persisted=false`。

## 下一门禁

下一步只允许在同一 r7 private root 以该 frozen plan 启动 live screening，并绑定同一
registry、source manifest、probe 与 admission receipt。screening terminal 且通过
transport-only gate 前，不得执行 ranking、provider baseline freeze、prompt tuning 或
target Harness。screening 结束后再按
`transport admission → external ranking → provider freeze → official Harness import →
cohort binding → convergence audit` 单向推进。

