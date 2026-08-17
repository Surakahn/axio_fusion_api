# Composite r6 Screening 终态与 Transport 门禁（2026-08-17）

## 终态结论

r6 使用独立 operational admission 生成的 immutable screening plan 已自然终态：8
个 serial units 全部 terminal，state 为 `partial`，其中 3 个 completed、5 个
failed/blocked。该 cohort 没有通过 transport admission，不能进入 ranking、provider
baseline freeze、official Harness import 或 target campaign。

本记录只保留控制面状态、digest 和安全计数；原始 provider output、prompt、label、
provider URL、model id 和凭据继续留在 operator-owned private checkpoint，不进入 Git
或 safe receipt。

## 固定输入与完整分母

- registry digest：
  `a98ca935e3b8005b84e26cfc71feb902ad43ecbc3947a4dec6cd7670bc9c17e5`
- source manifest digest：
  `cb52811b4b6cab984d435d5904920b4e9e6a94a7be51416f16b88acd4c388958`
- plan digest：
  `601b8fdd52cfc50fba49e853293754a7d887ab0632fe7a005bd82245c8ccf283`
- campaign digest：
  `886086b319e162d4df0c6130fc7d4b95c671ed807d3920f6891160738ccd7df4`
- plan 文件 SHA-256：
  `2ef50d629685e57ba9ad60d9e82014392b87330d30c38494c3d7d2bf9d566eb5`
- execution schedule digest：
  `71325756b4d1074d39a4ffa97aee56d11492840539acbe35ac2518d6a37a851b`
- unit-set digest：
  `c928691c3351fd9d8556d24e94a90647973619bcacc30a56c0e59ae01ddc42b5`
- screening state 文件 SHA-256：
  `75fd933fc7828222563c4558b4b1ae88aa1bb370240b625526af7612e69bd268`

operational admission 当时报告 10 个 candidate profiles、5 个 production admitted、
4 个 formal baseline eligible；screening 仍保留该完整候选分母和 8 个 serial units，
没有按 completed subset 缩小分母。

## Transport Admission

transport-only receipt 绑定同一 plan、campaign、registry、source manifest 和 state
digest，结果为 `status=blocked`：

- candidate canonical models：4
- terminal units：8
- transport-eligible canonical models：1
- 固定最低要求：3
- blocker：`transport_admission_fewer_than_minimum_models`
- transport receipt SHA-256：
  `d82ebeb12ff4feff353ae1ecba4b3ad0a1e66d87c5fe68ca77b54ac7b4eb079c`

supervisor receipt 为 `status=blocked`、`screening_status=partial`、
`transport_status=blocked`、`ranking_ready=false`，并确认
`target_benchmark_started=false`、`target_suite_calls_performed=false`。因此没有
生成 ranking，也没有把 operational admission 或 completed subset 解释为能力排名。

## Harness 收敛状态

r6 的 watcher 已在 screening 进入终态后原子重建 binding 并退出。最终 convergence
audit 为 `status=blocked`、`next_gate=screening`、
`target_suite_calls_allowed=false`、`final_claim_allowed=false`。Harness pin 和
execution plan 的离线 readiness 不足以打开 target gate；transport、ranking、freeze
和 official import 的 lineage 前置条件仍未满足。

- convergence audit SHA-256：
  `0534a3f5bc33e94609c1d6597c0714f1535bd5dae2416b3b48619d9f9c5bbd36`
- cohort binding SHA-256：
  `beb452bf4b46b6873795976995641baf7592005933a52fd273551890f6dee836`
- audit reason：`transport_admission_fewer_than_minimum_models`
- target-suite 调用：`false`
- raw provider outputs persisted：`false`
- secrets persisted：`false`

## 后续 successor 路线

1. 保留 r6 的 immutable plan、完整 state、transport receipt、supervisor receipt、
   Harness binding 和 convergence audit 为只读证据。
2. 不恢复 r6 checkpoint，不修改 r6 plan，不复用 r6 completed subset、ranking 或
   provider freeze，也不降低固定 3-model transport gate。
3. 先做 bounded non-target transport health check；若 provider transport 已恢复，
   用新的 probe-bound registry 和新的 source-manifest selection seed 创建 r7，重新
   运行完整候选分母 admission/screening；若未恢复，则扩展候选分母后再注册新的
   immutable cohort。
4. 只有 successor 完整通过 transport、external ranking、provider baseline freeze、
   official Harness import 和 lineage convergence，audit 明确返回
   `ready_for_target_campaign` 后，才允许进入 21-suite target campaign。

