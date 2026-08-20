# Composite r17 screening 终态与 r18 successor（2026-08-21）

## r17 终态

r17 唯一 live non-target screening 已自然终态，三个托管进程均已退出；没有第二套
screening、checkpoint 恢复或 target 请求。safe state 与 screening receipt 均为
`status=partial`，16/16 unit terminal：

- `completed_unit_count=6`；
- `failed_or_blocked_unit_count=10`；
- `ready_for_ranking=false`；
- `network_calls_performed=true`；
- `target_suite_calls_performed=false`；
- state SHA-256：`db213575a29935d5e3e89d5248e06c2933af5e1b472f37eb5125625d066afc65`；
- screening receipt SHA-256：`e586b82df9fd244c205603c61c4cf1b62d45591fd88439c4b30335b956a23905`。

失败原因仅为 `screening_unit_no_scores` 与
`screening_unit_transport_failure_rate_exceeded`。完整分母和私有 checkpoint 继续保留
在 operator-owned private root；其中的 raw provider output 不读取、不提交 Git、不转化为
质量、ranking 或 baseline evidence。

## Transport admission

同 cohort transport-only admission 已完成，严格只使用 unit 终态、完整分母和 transport
failure rate，没有读取 mean score、labels、prompt 或 provider output：

- receipt：`private/runs/2026-08-20-composite-cohort-r17/transport_admission.r17.private.json`；
- status：`blocked`；
- `selection_basis=transport_failure_rate_only`；
- candidate canonical：8；
- 两个 source family 均通过固定 2% gate 的 canonical：1；
- 最低要求：3；
- blocker：`transport_admission_fewer_than_minimum_models`；
- receipt SHA-256：`15a194a8a397ee4fab5f6198413f0a1f1aef90a0a64959af7cc79afc46f2e7e6`。

按 canonical/source 的 hash-only 统计，只有一个 canonical 在两个 source family 都低于
2%；其余 canonical 至少有一个 source family 高于门槛，不能抽取“通过的一半”或拼接
survivor subset。该结果描述 transport 可用性，不是模型能力排序，也不授权 ranking。

同 cohort supervisor receipt 为 `blocked`，`transport_return_code=2`，没有 ranking 文件、
provider baseline freeze 或 target benchmark；Harness convergence 仍为
`next_gate=screening`、`target_suite_calls_allowed=false`、`final_claim_allowed=false`。

## r18 离线 successor

r18 只从 r17 source contract 创建 immutable successor，改变注册日期和 selection seed；不
读取 r17 分数、transport receipt、checkpoint 或 survivor subset，也没有重复 provider probe：

- source successor：`private/runs/2026-08-21-composite-cohort-r18/source_manifest.successor.r18.private.json`；
- source SHA-256：`3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`；
- successor receipt：`status=ready`，selection seed hash
  `ad2433e1a3f74e21220669d7a6d56698ef885c2bf42f9339bb732daefaf563e2`；
- frozen plan：`private/runs/2026-08-21-composite-cohort-r18/baseline_screening_plan.r18.private.json`；
- plan SHA-256：`58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`；
- plan digest：`a626b9be599041b03c899880eee0fb10be7b7a7b5f22f2f0ccef95ad204cbf86`；
- 2 source families、8 canonical groups、9 replicas、16 serial units、`max_workers=1`、
  固定 2% fail-fast gate、estimated provider calls `1712`；
- zero-network preflight：`preflight_ready`，campaign digest
  `fdc903a9e90a82e5753c17b49c8dd0f6b732100b8668dc14f576f1669481966d`；
- Harness scaffold 已离线生成，pin `ready`、execution plan `ready`，但 acquisition、
  import、binding 和 convergence 按前置条件保持 blocked。

r18 目前只到“控制面 ready、live screening 未授权”状态。是否启动 r18 live screening，必须
先完成 provider transport 根因复核并由后续明确操作窗口决定；不得把 r18 preflight 当作
screening 结果，也不得改变固定 2% gate。

## 下一条合法路径

`r18 live screening（明确授权后） -> terminal screening -> transport admission ->
complete-pool ranking -> external top-three -> provider baseline freeze -> same-cohort
official/audited Harness -> convergence audit -> 9 类 21 套 campaign -> final claim audit`。

在 provider baseline freeze 前，Fusion router、prompt、panel policy、weights 和
benchmark-driven learning loop 均保持不变；算法研究只能以 shadow/non-target 设计记录存在。
