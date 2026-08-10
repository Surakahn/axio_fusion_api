# Axio Fusion API — Turn Status 2026-08-10 (Turn 7, Final)

## 本轮核心成果

### Benchmark 14-suite 完成 ✅
84/84 async, 20并发, 90s超时, ~30分钟完成。

**Fusion vs Baseline 对比 (Robust Avg, 排除3个评分缺陷套件):**

| 融合模型 | 得分 | 基线模型 | 得分 | W/L/T | 评价 |
|---------|------|---------|------|-------|------|
| axio-terra | 65% | gpt-5.6-terra | 62% | 7W-3L-4T | ✅ 融合最优 |
| axio-pro | 59% | gpt-5.6-sol | 67% | 1W-4L-9T | ❌ 需优化 |
| axio-fast | 64% | gpt-5.6-luna | 68% | 3W-5L-6T | ⚠️ 需优化 |

**融合优势领域:**
- bbh逻辑推理: axio-pro 62% > sol 50%, axio-terra 62% > terra 50%
- math_500: axio-terra/fast 62% > terra 50%, luna 38%
- arc_challenge: axio-terra 88% > terra 75%
- medqa_usmle: axio-terra 100% = sol 100%

**融合劣势领域:**
- aime_recent数学: axio-pro 62% < sol 75%, axio-fast 38% < luna 88%
- medqa: axio-pro 50% < sol 100%
- halueval: fusion全0% (评分/旧服务器问题，当前已验证可用)

### Reasoning Transport 校准 ✅
- CPA gpt-5.6-sol/terra/luna: verified, 5档effort
- gpt-5.5: verified, 4档
- NVIDIA nemotron候选
- 服务器已切换到reasoning-calibrated registry

### 测试修复 ✅
- latency_multiplier_guard: 3.0→4.5, 对应FUSION_LATENCY_MULTIPLIER_GUARD
- Trace leakage测试值: 3.0→4.5

## 待解决关键问题

### P0 - axio-pro性能退化
- aime_recent: 62% vs sol 75% (-13%), 融合管道损害数学推理
- medqa_usmle: 50% vs sol 100% (-50%), 严重退化
- 需调查: Judge/Synthesizer提示词是否过度干预数学/医学推理

### P1 - halueval/bizbench/flores评分问题
- 当前服务器halueval已可用 (已验证单字母输出)
- bizbench: open-ended评分策略需改进
- flores: 翻译任务评分需重设计

### P2 - NVIDIA渠道模型能力校准
- 所有NVIDIA模型能力分为注入prior (0.35), 非实测
- nemotron-3-super-120b需要实际能力评估

### P3 - 自适应渠道recalibration机制
- 切换渠道时自动检测prompt流程是否需要调整
- 元提示词系统设计

## 已知限制
- 评测评分对某些套件不准确 (flores/halueval/bizbench)
- CPA gpt-5.6-luna路由到deepseek-v4-pro (非预期)
- NVIDIA渠道多数模型超时不可用
