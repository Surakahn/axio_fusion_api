# Axio Fusion API — Turn Status 2026-08-11 (续3)

## 本轮成果

### 1. Claude 渠道接入准备
- 端点 `https://tokenapis.com/v1/messages` (Anthropic 格式)，10+模型
- 配置已就绪：`AXIO_ANTHROPIC_BASE_URL/API_KEY/MODELS`
- 状态：间歇性可用（首次请求通过，后续"No available accounts"）
- 需正式 provider enrollment 流程才能加入 Fusion 池

### 2. Fast 路由 Domain-Aware 选模
- 新增 `FAST_DIRECT_DOMAIN_WEIGHT = 0.10`，任务类型匹配优先
- 数学/逻辑/编程任务自动优先选对应能力强的模型
- 向后兼容：无 domain 信息时行为不变

### 3. API 格式全覆盖验证
- Chat/Completions: ✅ axio-fast "Hi!" 
- Responses: ✅ axio-terra "Hi"
- Anthropic Messages: ✅ axio-fast "Hi" (35s, 较慢但可用)
- Gemini: ⚠️ 需 Gemini-native 上游 provider
- 推理强度: xhigh/max 已验证透传

### 4. 渠道状态
- CPA 内部 (10.195.91.64:8317): /models 即时，推理请求 46s（极慢，provider 端问题）
- NVIDIA: 代理正常
- Claude: 间歇可用

### 5. 测试
- 1025 passed, 7 skipped — 全绿

## Git 提交 (本轮)
```
284537b docs: handoff更新 — domain-aware routing + Claude渠道
e7ed409 feat: fast路由domain-aware选模 + Claude渠道配置
```

## 目标达成度评估

| 需求 | 状态 |
|------|------|
| 多供应商多接口 | ✅ NVIDIA+CPA+Claude(pending) |
| Chat/Completions 对外 | ✅ |
| Responses 对外 | ✅ |
| Anthropic 对外 | ✅ (35s) |
| Gemini 对外 | ⚠️ 需上游 |
| axio-pro/terra/fast | ✅ 三档全部正常 |
| 路由/编排/裁判/综合 | ✅ |
| axio-pro > sol | ✅ +2.1% |
| axio-terra > terra | ✅ +1.3% |
| axio-fast > luna | ❌ -3.2% (domain-aware改进中) |
| 评测矩阵 | ⚠️ 原始数据需修复 |
| 外部排名冻结 | ❌ 待源覆盖 |

## 待推进
1. **Claude 正式接入** — 需 provider enrollment + pre-Fusion 流程
2. **axio-fast benchmark 重跑** — 验证 domain-aware 效果
3. **r44 预筛选** — transport 修复后重跑
4. **外部排名冻结** — 两个独立源
5. **CPA 延迟排查** — 46s 推理请求需优化

## 下一轮重点
- CPA 延迟问题调查（可能是 provider 端排队）
- Claude 渠道恢复后正式 enrollment
- axio-fast benchmark 验证 domain-aware routing
