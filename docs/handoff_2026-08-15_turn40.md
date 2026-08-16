# Axio Fusion API — Handoff 2026-08-15 (Turn 40)

## 本轮完成任务

### 1. AGENTS.md 第十章补充完成
- 新增 10.7 章：Luna 与 Terra 工具调用规范、明确指导
- 记录了：
  - 正确配置与症状对照表（Luna/Terra/Sol）
  - 配置位置与验证方法
  - 真实故障案例：Luna 26 次连续失败与根因
  - 结构化 exec_command 的正确参数格式
  - 工具调用最小自检流程
  - 何时调用 Sol vs Luna/Terra 的决策表
- 已验证本机实际配置：
  - `gpt-5.6-luna`: tool_mode = None ✓
  - `gpt-5.6-terra`: tool_mode = None ✓
  - `gpt-5.6-sol`: tool_mode = code_mode_only ✓
- 提交并推送至远程（commit e117136）

### 2. 工具调用规范已完整落地
- 后续模型在 Codex 环境中可直接参考 AGENTS.md 第十章（10.1-10.7 节）
- 避免了之前 Luna 因工具形态不匹配导致的 26 次连续失败

---

## 当前 5 模型 transport cohort 筛选状态

**进程 PID 478163 持续运行中**：

| 指标 | 值 |
|---|---|
| 已运行时间 | 5h 47m |
| 首轮终态 | 6 completed / 3 failed / 1 in_progress |
| ready_for_ranking | False |
| 最新 checkpoint | LiveBench (claude-opus-5)：38/102 cases，35 completed / 3 transport_failed |

**单元终态情况**：
- 6 completed：6ef630255d45、0dddd65e2bc9、41b5218e43d6、4d2f706edd9f、377d7deee58a、a9bcc763e44d
- 3 failed：27dd20afc4fe、9d1eab23ea83、dd107ef2227a
- 1 in_progress：417f663aa2e9（LiveBench，claude-opus-5）

**运输失败特征**：
- 失败原因主要为 transport_failed（90 秒 timeout 或上游 5xx）
- LiveBench 仍为最脆弱来源，尤其对 claude-opus-5

---

## 下一步规划

按 handoff_2026-08-15_turn39 的 post-screening 流程：

1. **继续低频探针**：15-20 分钟间隔，等待 417f663aa2e9  终态
2. **全部终态后**：
   ```bash
   # 执行排名
   PYTHONPATH=src python3.11 -m axio_fusion_api.cli \
     baseline-screening-to-ranking \
     --plan private/runs/2026-08-15-core-cohort-transport5/baseline_screening_plan.core.private.json \
     --campaign-state private/runs/2026-08-15-core-cohort-transport5/screening_state.core.live.full.private.json \
     --source-manifest private/runs/2026-08-14-core-cohort-final/source_manifest.core.private.json \
     --private-root private/runs/2026-08-15-core-cohort-transport5 \
     --private-probe-file private/runs/2026-08-13-core-cohort/provider_probe.core.private.json \
     --transport-availability-file private/runs/2026-08-14-core-cohort-final/transport_admission.retry3.private.json \
     --output private/runs/2026-08-15-core-cohort-transport5/ranking.core.private.json
   ```
3. **Provider baseline freeze**：冻结 5 模型的 baseline 排名
4. **进入七类十四套正式 campaign**

---

## 关键约束提醒

- **不修改冻结 plan**
- **不做 superiority claim**（直到 21-suite 完整 campaign 结束）
- **低频探针期间不发请求**（只检查进程 PID、checkpoint mtime、日志尾部）
- **Git commits 使用中文 message**

---

*最后更新：2026-08-15 22:16 — 补充 AGENTS.md 工具调用规范，继续低频等待 5 模型筛选终态*

---

## 2026-08-16 续接更新：transport5 终态与 baseline freeze

上一节记录的是 2026-08-15 22:16 的中间状态，以下内容以当前工作区和新生成的 hash-only artifact 为准。

### 已完成

- `transport5` 已终态：`screening_state.core.live.full.private.json` 为 `completed`，10/10 units 完成，`ready_for_ranking=true`，未执行 target-suite calls，未持久化 provider output、secret 或 raw credential。
- 保留了首轮 partial、retry2 和 `missing-transport-blocked` 历史 artifact；没有修改冻结的 screening plan，也没有重跑上游探测。
- 修复 baseline freeze 的控制面绑定：新增 `--transport-availability-file`，独立验证 screening transport receipt，不再把它误当成 `operational_admission.v1`。
- transport receipt 只在以下条件同时满足时进入正式 provider pool：`status=ready`、`selection_basis=transport_failure_rate_only`、质量选择字段为空、no-cheat contract 禁止 benchmark/label/output 参与、profile/canonical hash 集合能在当前 registry 中精确重建。
- 对 probe-bound registry 增加源 registry 内容 hash 绑定，并将 transport receipt 纳入 provider baseline freeze digest 与 reload receipt。
- 新 freeze artifact：`private/runs/2026-08-15-core-cohort-transport5/provider_baseline_freeze.transport-bound.core.safe.json`。
  - transport admission：`ready`，6 个 registry profiles 精确过滤为 5 个；`registry_binding_mode=probe_bound_registry`。
  - external ranking：`ready=true`，candidate inventory 为 5/5，identity binding ready，rank 1/2/3 映射有效。
  - freeze digest：匹配；没有 provider admission 或 ranking inventory mismatch。
- 验证结果：全量 `1036 passed, 7 skipped`；新增 transport-bound freeze、registry hash binding 和篡改 fail-closed 回归覆盖。

### 当前阻塞

baseline freeze 仍为 `final_claim_freeze_ready=false`，唯一剩余阻塞为：

- `provider_portfolio_final_claim_not_ready`
- `provider_portfolio_missing_fast_candidate`

该阻塞是真实能力覆盖缺口，不是控制面误判：bound registry 的 6 个 profile 的 `p50_latency_ms` 均高于 1800 ms，且没有显式 fast/mini/flash 等 fast-path 标记，因此 `fast_candidate_count=0`。不能通过降低门槛、修改 frozen registry 或伪造 fast candidate 绕过。

### 未完成与下一步

- 尚未进入 official/audited harness import gate，尚未启动 target benchmark campaign，也不能做三档 Fusion 优于单模型的 superiority claim。
- 需要一个经过真实 provider transport/streaming 门禁、并进入新 registry handoff 的低延迟候选。该候选必须在新的 screening cohort 中完成 admission；不得把历史 registry 或当前 5 模型 transport receipt 改写成 fast candidate。
- 新候选完成后，建立新的 screening plan/cohort，重新生成 transport admission、external ranking、provider probe audit 和 baseline freeze；旧 artifact 全部保留。
- 当前代码、测试和文档改动已使用中文 commit message 提交；私有 artifact 仍保留在本地运行目录，不加入 Git。

*最后更新：2026-08-16 11:09 — transport5、transport-bound baseline freeze 控制面和真实 fast candidate blocker 已记录；未做 benchmark superiority claim。*
