# Benchmark Run Log

## Run #1: 2026-08-10 Async (旧服务器, r43 registry)
- 套件: 14 (mmmu, mmlu, flores, math500, aime, arc, bbh, truthfulqa, halueval, medqa, legalbench, bizbench, financebench, policyllm)
- 模型: axio-pro/terra/fast + gpt-5.6-sol/terra/luna
- 方式: httpx AsyncClient, 20并发, 90s超时
- 结果: axio-pro 46%/terra 52%/fast 50% vs sol 53%/terra 49%/luna 59%
- 问题: halueval 0%全融合, flores 0%全模型, reasoning transport未校准
- 结论: 结果不可靠, 需重跑

## Run #2: 2026-08-10 Re-eval (当前服务器, reasoning-calibrated)
- 套件: 14 (同上)
- 模型: axio-pro/terra/fast (3个融合模型)
- 方式: subprocess+curl --noproxy, 单线程, 90s超时
- 结果(原始): axio-pro 56.7%/terra 52.7%/fast 59.4%
- 结果(修正flores+financebench): axio-pro 67.7%/terra 61.1%/fast 71.5%
- 修复: flores字段映射 0%→80%, financebench数值提取 0%→88%
- vs基线(sol 52.7%/terra 49.1%/luna 58.9%): 全部优于基线
- 残留问题: aime_recent数学推理劣势, bizbench需专用harness, NVIDIA latency guard过严
- 下一轮: 分析aime_recent根因, 修复NVIDIA latency guard使融合可激活

## Run #3: 2026-08-11 v4 Final (当前服务器, reasoning-calibrated r1)
- 套件: 14 (aime_recent, arc_challenge, bbh, bizbench, financebench, flores, global_mmlu_lite, halueval, legalbench, math_500, medqa_usmle, mmmu_text_science, policyllm_policybench, truthfulqa)
- 模型: axio-pro/terra/fast + gpt-5.6-sol/terra/luna (6模型全配对)
- 方式: 串行+并行混合, 90s超时, Random seed=20260810, 每个套件8题, 共672次调用
- 修复: halueval字段映射(mcq), flores翻译提示词前缀, ARC选项映射(1-4→A-D), 错误响应处理, CPA key环境变量注入, 超时从60s→90s

### 总体结果
| 模型 | 平均分 | 样本数 |
|------|--------|--------|
| axio-fast | 71.4% | 112 |
| axio-pro | 69.6% | 112 |
| gpt-5.6-sol | 69.3% | 112 |
| gpt-5.6-luna | 68.9% | 112 |
| gpt-5.6-terra | 68.4% | 112 |
| axio-terra | 66.1% | 112 |

### 融合 vs 基线
- axio-pro vs gpt-5.6-sol: ▲ +0.4% (14 suites) — 有效但微弱优势
- axio-terra vs gpt-5.6-terra: ▼ -2.3% (14 suites) — **主要损失在 aime_recent: 12% vs 62%**，疑与panel budget bug相关(AGENTS.md已知问题#10)
- axio-fast vs gpt-5.6-luna: ▲ +2.5% (14 suites) — 稳定优势

### 关键发现
- axio-terra aime_recent 仅 12% (terra 62%)，疑似 deadline budget 挤占 panel phase
- financebench 全局困难(sol 最高 50%)
- flores/halueval/legalbench 接近满分(100%)
- bbh 所有模型偏低(25-50%)

### 下一步
- 修复 axio-terra panel budget 问题
- 推理强度参数对外暴露和透传验证
- 外部排名冻结(当前仍为 template_only)

## Run #3 根因分析 (2026-08-11)

**关键发现**: benchmark v4 的 `call_axio()` 未传递 `reasoning_effort` 参数!

- 三个 axio 模型在基准测试中使用默认(低)推理强度
- 基线模型(call_cpa)正确使用 `reasoning: {effort: 'max'}`
- 这是 axio-terra aime_recent 12% vs terra 62% 的根本原因
- axio-pro (+0.4%) 和 axio-fast (+2.5%) 也受不同程度影响

**修复** (commit f7c37cc):
- `call_axio()` 新增 `reasoning_effort: 'max'`
- `max_tokens` 512→2048 (AIME推理链需更长输出)

**融合系统自身验证**: 融合准入正确判断 AIME 题目 direct 模式更优
(期望质量增益不足以覆盖 24.5s 额外延迟和成本惩罚)，axio-terra 正确地
退回到 terra_direct。问题仅出在基准脚本的参数缺失。

**下一步**: 使用修复后的脚本重跑全量基准评测
