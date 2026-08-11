# Axio Fusion API — Turn Status 2026-08-11 (续4)

## 本轮成果

### 1. Fast Light Verify 启发式复杂度检测 (已研究，待集成)
- 实现了 `_fast_message_heuristic_complexity()` 函数
- 通过关键词匹配检测数学/代码/领域复杂度，无需调用模型
- 数学题 heur=0.12 ✅ / 简单问候 heur=0.0 ✅ / 代码题 heur=0.24 ✅
- **发现**: `analysis` dict 的 complexity/uncertainty 字段从未被计算
  - 这意味着 `fast_light_verify` 在实际请求中从不触发
  - 需要更深层的 budget + analysis pipeline 集成
- 已回退到稳定状态，等待后续深度集成

### 2. API 格式全覆盖验证
- Chat/Completions: ✅ (4.4s 数学，2.4s 简单)
- Responses: ✅ (前轮已验证)
- Anthropic Messages: ✅ (35s，可用)
- Gemini: ⚠️ 需 Gemini-native 上游 provider

### 3. Claude 渠道
- 配置已就绪，端点间歇不可用
- 需要正式 provider enrollment 流程

### 4. 测试状态
- 1025 passed, 7 skipped
- 全部绿色

## 关键发现

### fast_light_verify 死代码问题
`_fast_light_verify_requested` 依赖 `analysis` dict 中的 `complexity`/`uncertainty`/`risk`/`quality_target` 字段，
但这些字段在 `_budget_for_request` 调用时始终为 0.0（默认值）。
整个 fast_light_verify 功能在实际请求中**从不触发**，除非用户显式传 `routing_policy.fast_light_verify=true`。

**根因**: `analysis` 只从 routing_policy 配置中提取，没有实际的任务分析步骤。
**影响**: axio-fast 始终使用单模型 direct cascade，无法利用双模型验证提升准确性。
**修复方向**: 需要在 budget 计算中集成启发式复杂度检测（或添加轻量级任务分析）。

### CPA 延迟波动
- 正常时: 2.4-6.4s
- 慢时: 19-46s
- Provider 端排队导致的不稳定

## Git 状态
- 当前 HEAD: `f58ff0a` (已推送)
- 工作区清洁

## 待推进
1. **fast_light_verify 集成** — 将启发式复杂度检测接入 budget pipeline
2. **axio-fast benchmark 重跑** — 验证 domain-aware routing 效果
3. **Claude 正式 enrollment** — 走 provider 发现→预筛选流程
4. **外部排名冻结** — 两个独立源覆盖
5. **21 套件评测** — 排名冻结后执行
