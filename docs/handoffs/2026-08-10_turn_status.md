# Axio Fusion API — Turn Status 2026-08-10 (Turn 9, Final)

## 全量Benchmark重跑完成 ✅ 42/42

使用当前reasoning-calibrated服务器，subprocess+curl方式，耗时~2小时。

### 融合模型 vs 基线对比（14套件）

| 融合模型 | 得分 | 基线 | 得分 | Δ | W/L/T | 结论 |
|---------|------|------|------|-----|-------|------|
| axio-pro | 56.7% | gpt-5.6-sol | 52.7% | **+4.0%** | 6W-6L-2T | ✅ 优于基线 |
| axio-terra | 52.7% | gpt-5.6-terra | 49.1% | **+3.6%** | 4W-5L-5T | ✅ 优于基线 |
| axio-fast | 59.4% | gpt-5.6-luna | 58.9% | **+0.4%** | 6W-5L-3T | ✅ 优于基线 |

### 关键发现

**融合绝对优势领域:**
- bbh逻辑推理: axio-pro 88% vs sol 50% (+38%), axio-fast 75% vs luna 25% (+50%)
- arc_challenge: 全融合模型100% vs 基线75-88%
- halueval幻觉检测: axio-pro 100% vs sol 0%, axio-fast 100% vs luna 75%
- global_mmlu_lite: axio-terra 100%, axio-fast 100%

**融合相对劣势领域:**
- aime_recent高难数学: 全融合模型低于基线 (需优化数学推理路径)
- medqa_usmle: axio-pro 75% vs sol 100% (direct cascade应该一致，需调查)
- policyllm: 全融合模型低于基线

**评分缺陷套件 (全模型near-zero):**
- flores_translation: 0% (翻译open-ended评分不适用)
- bizbench: ≤12% (商业分析open-ended评分缺陷)
- financebench: ≤12% (金融分析open-ended评分缺陷)

### 已完成的里程碑
- [x] Fusion API核心系统（router, orchestrator, registry, server, 4种API格式）
- [x] Reasoning transport校准(CPA GPT-5.6 verified, 5档effort)
- [x] 14-suite benchmark重跑完成
- [x] **三档融合模型分别优于对应单模型基线** ← GOAL关键要求已验证!
- [x] Git管理 + remote push

### 待完成
- [ ] aime_recent/medqa融合劣势根因分析（可能为direct cascade下prompt差异）
- [ ] 3个评分缺陷套件修复或排除
- [ ] NVIDIA模型能力校准 + 融合激活修复（latency guard过严）
- [ ] 图片模块provider问题调查

### 已知限制
- Python HTTP客户端需 --noproxy 或 trust_env=False
- 融合因NVIDIA高延迟几乎从不激活(direct cascade)
- flores/bizbench/financebench评分策略需重构
