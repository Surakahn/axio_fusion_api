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
