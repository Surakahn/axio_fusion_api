# Axio Fusion API — 基准评测汇总 (2026-08-12)

## 评测环境
- 服务器: axio_fusion_api @ 18900 端口, 24模型, 3 Provider
- 推理强度: max (全部评测)
- 超额时: 90s
- 代理: http://127.0.0.1:10808

## axio-terra 累计结果

| 套件 | 类别 | 题目数 | 正确 | 得分 | 备注 |
|------|------|--------|------|------|------|
| ARC-Challenge | 逻辑推理 | 8 | 8 | **100%** | 科学推理满分 |
| TruthfulQA | 幻觉抵抗 | 8 | 8 | **100%** | 事实准确性满分 |
| BBH | 综合推理 | 7 | ~5 | **~71%** | 开放式复杂推理 |
| MedQA USMLE | 医学垂直 | 7 | 7 | **100%** | 医学知识满分 |
| Global MMLU Lite | 多语言 | 5 | 5 | **100%** | 多语知识满分 |
| MATH500 | 数学 | 8 | ~5 | **~63%** | LaTeX评分改进后 |
| **总计** | | **43** | **~38** | **~88%** | |

## axio-terra vs 基线对比

| 对比 | 题目数 | axio-terra | 基线 | 差异 |
|------|--------|------------|------|------|
| vs gpt-5.6-terra | 14 | 83% | 83% | 0% |
| vs gpt-5.6-sol | 2 | 100% | 100% | 0% |

注: 样本量较小，统计学上不显著。需更大样本量区分。

## axio-fast 快速评测 (历史)

| 对比 | 题目数 | axio-fast | 基线 | 差异 |
|------|--------|-----------|------|------|
| vs deepseek-v4-pro (标注为luna) | 15 | 86.7% | 100% | -13.3% |

注: 基线实为deepseek-v4-pro（CPA映射异常），非真正gpt-5.6-luna。
axio-fast延迟约28s/请求（fast_light_verify 5次provider调用）。

## axio-pro 状态

- 首次调用成功 (2/2正确)
- 后续调用因CPA限流失败
- panel phase需要重试退避+流量控制配合

## CPA 模型映射异常

| 请求模型 | 实际服务模型 | 状态 |
|---------|-------------|------|
| gpt-5.6-luna | deepseek-v4-pro | ⚠️ 映射异常 |
| gpt-5.6-terra | gpt-5.6-terra | ✅ 正常 |
| gpt-5.6-sol | gpt-5.6-sol | ✅ 正常 |
| gpt-5.5 | gpt-5.5 | ✅ 正常 |
| gpt-5.4 | gpt-5.4 | ✅ 正常 |

**影响**: luna基线不可用，需用sol/terra作为替代基线。

## 渠道模型能力

| 渠道 | 模型数 | 类型 | 最强模型 |
|------|--------|------|---------|
| CPA | 13文本+1生图 | chat/responses | gpt-5.6-sol, gpt-5.6-terra |
| NVIDIA | 6 | chat | nemotron-3-super-120b |
| tokenapis (Claude) | 23 | anthropic | claude-opus-5, claude-sonnet-5 |

## 已知限制
1. CPA间歇性不稳定 (502/限流) → 阻塞大规模自动化评测
2. MATH500评分需进一步改进 (LaTeX格式匹配)
3. axio-fast评测需批量异步模式 (单次28s太慢)
4. axio-pro需CPA稳定后才能完整评测
5. 外部排名冻结需2个独立来源 → 当前缺失

