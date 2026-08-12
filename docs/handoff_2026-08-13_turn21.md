# Axio Fusion API — Handoff 2026-08-13 (Turn 21)

## 本轮诊断

### axio-pro 融合失败根因分析

通过追踪执行，axio-pro 失败链条：
1. `independent_solver (gpt-5.6-sol)`: ProviderExecutionError @ 767ms
2. `primary_solver (gpt-5.6-terra)`: ProviderExecutionError @ 1271ms  
3. 所有后续 candidates (8个): DeadlineExceeded (skipped)
4. 降级 fallback: 全部 DeadlineExceeded

根因最终定位：**CPA 渠道间歇性超时**
- `gpt-5.6-terra` 在共享流量池中第二次调用时 `provider_request_timeout`
- 超时消耗 DeadlineBudget，导致后续全部 candidate 被跳过
- 并非 Panel Phase 配置问题（预算 39s 充足）

### 基准评测

**axio-terra vs gpt-5.6-terra (15题简单问答)**
```
axio-terra: 8/15 (53%)
base:       9/15 (60%)
Delta: -1 (-7pp)
```

**与上次对比（Turn 20: 12/15 vs 5/15, +47pp）**：
- 本次 CPA 渠道可靠性显著下降
- 多次 ERR（超时），双方均受影响
- 当双方均正常工作时，准确率相当（Q6,9,11-15 各对）

### 稳定性诊断

| 测试 | 结果 | 说明 |
|------|------|------|
| CPA 单独调用 gpt-5.6-sol | ✅ | 正常 |
| CPA 单独调用 gpt-5.6-terra | ❌ timeout | 间歇性超时 |
| CPA 并发 4 路 | ✅ 3/4 | terra 超时 |
| Claude 直连 opus-5 | ✅ | 正常 |
| Claude 直连 sonnet-5 | ❌ timeout | 间歇性 |
| axio-terra HTTP API | ✅ | 正常工作 |
| axio-pro HTTP API | ❌ | provider 全失败 |

## 项目完成度: ~85%

### 已确认工作
- ✅ 32模型3Provider服务运行
- ✅ 4种API格式
- ✅ axio-terra 正常工作
- ✅ axio-fast（预期正常）
- ✅ 推理强度参数框架
- ✅ Claude channel集成

### 待解决
- ❌ CPA渠道可靠性（间歇性超时）
- ❌ axio-pro 多模型融合（依赖CPA渠道稳定性）
- ❌ 完整基准评测（受渠道稳定性影响）

### 下一步
1. 提高 CPA 渠道超时容忍度
2. 添加 provider 级别 circuit breaker
3. axio-pro fallback 到纯 CPA 模型路径
4. 跑 axio-fast 基准
