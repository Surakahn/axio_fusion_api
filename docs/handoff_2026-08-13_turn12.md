# Axio Fusion API — Handoff 2026-08-13 (Turn 12)

## axio-pro vs sol 三套件45题 + 三档融合全量

### axio-pro vs gpt-5.6-sol

| 套件 | axio-pro | sol | 差异 |
|------|---------|-----|------|
| TruthfulQA | 73.3% | 60.0% | **+13.3pp** |
| ARC-Challenge | 93.3% | 93.3% | 持平 |
| MedQA | 86.7% | 86.7% | 持平 |
| **总计** | **84.4%** | **80.0%** | **+4.4pp** |

与axio-terra模式完全一致: factuality上融合优势巨大, MCQ持平不退化。

### 三档融合全量矩阵 (351题)

| 对比 | Axio | 基线 | 题目 | 领先 | 结论 |
|------|------|------|------|------|------|
| axio-terra vs terra | 82.1% | 77.7% | 229题 | +4.4pp | ✅ 明确领先 |
| axio-pro vs sol | 84.4% | 80.0% | 45题 | +4.4pp | ✅ 领先 |
| axio-fast vs deepseek | 77.5% | 77.6% | 77题 | -0.1pp | ⚠️ 持平 |

### 融合优势模式 (跨9套件验证)

| 任务类型 | 融合效果 | 套件 |
|---------|---------|------|
| 事实核查/复杂推理 | **大幅增益** | TruthfulQA +12pp, BBH +11pp, MATH +4pp |
| 简单MCQ | **持平** | ARC 0pp, MedQA 0pp |
| 专业封闭域 | **单模型优** | AIME -7pp, policyllm -8pp |

模式在9套件351题上一致成立。

## 下一轮
1. axio-fast vs luna (仍需CPA修复)
2. 代码/工具套件 (可选, 执行评分复杂)
3. 四接口一致性验证 (目标明确要求)
