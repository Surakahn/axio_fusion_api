# Axio Fusion API — Handoff 2026-08-13 (Turn 22)

## 本轮关键修复

### 1. GPT/Claude 能力分分层修正 (registry.py)
**问题**: gpt-5.6-sol/terra/luna 能力分完全相同(0.88)，claude-opus-5反而最高(0.91)
**修复**:
- gpt-5.6-sol: 0.90 (top)
- gpt-5.6-terra: 0.88 (second)
- gpt-5.6-luna: 0.86 (third/fast)
- claude-fable-5 ≈ sol: 0.90
- claude-opus-5 > terra: 0.89
- claude-sonnet-5 > luna: 0.87
- 移除冲突的遗留terra/sol/luna块

### 2. Fast/Terra路由能力上限 (router.py)
**问题**: axio-fast/terra 都选了 sol-tier 的 claude-opus-5
**修复**:
- FAST_DIRECT_CAPABILITY_CEILING = 0.875
- TERRA_DIRECT_CAPABILITY_CEILING = 0.895
- 新增 `_apply_tier_capability_band()` 函数

**路由结果**:
- axio-fast → claude-sonnet-5 (luna band) ✓
- axio-terra → claude-opus-5 (terra band) ✓
- axio-pro → gpt-5.6-sol + claude-opus-5 + claude-fable-5 (sol band) ✓

### 3. 推理强度透传修复 (providers.py)
**问题**: 所有reasoning_transport.status='unknown'，reasoning_effort被静默丢弃
**修复**:
- chat格式: 未验证时直接透传request.reasoning_effort
- responses格式: 未验证时使用reasoning.effort结构
- 只对status=""或"unknown"生效，不影响candidate/verified状态

### 4. 测试
- test_reasoning_transport.py: 31 passed (含新透传测试)
- test_fusion_core_regressions.py: 117 passed

## 基准评测状态

### 新基准未能完成
CPA/Claude 渠道在本轮不可用（超时/空响应），所有三个基准均卡在第一个问题。

### 历史基准 (Turn 21):
- axio-terra vs gpt-5.6-terra: 8/15 vs 8/15 (持平, CPA不稳定)
- axio-fast vs gpt-5.6-luna: 0/15 vs 7/15 (旧路由，已修复)
- axio-pro: 全部 provider failure

## 项目完成度: ~88%

### 本轮新增
- ✅ 修正能力分三层分层
- ✅ Fast/Terra路由能力上限
- ✅ 推理强度透传修复
- ✅ 代码提交推送 (commit b3235b0)

### 待完成
- ⏳ 基准评测需在渠道可用时重跑
- ⏳ axio-pro 的 provider 容错需要增强
- ⏳ 14套件标准基准
- ⏳ 外部排名冻结
- ⏳ 图片模块 prompt composer 增强

## 关键文件
- src/axio_fusion_api/registry.py — 能力分先验
- src/axio_fusion_api/router.py — 路由策略 + 能力上限
- src/axio_fusion_api/providers.py — reasoning_effort透传
- tests/test_reasoning_transport.py — 31测试全通过
