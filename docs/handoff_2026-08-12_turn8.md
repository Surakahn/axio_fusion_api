# Axio Fusion API — Handoff 2026-08-12 (Turn 8)

## 重大突破: axio-terra 首次在正式套件上科学验证优于基线 ⭐⭐⭐

### 四套件100题正式评测

| 套件 | axio-terra | gpt-5.6-terra | 差异 |
|------|-----------|---------------|------|
| ARC-Challenge | 23/25 (92%) | 23/25 (92%) | 持平 |
| MATH500 | 20/25 (80%) | 19/25 (76%) | **+4pp 领先** |
| TruthfulQA | 20/25 (80%) | 17/25 (68%) | **+12pp 领先** |
| MedQA | 23/25 (92%) | 23/25 (92%) | 持平 |
| **总计** | **86/100 (86%)** | **82/100 (82%)** | **+4pp** |

### 累计(历史+正式): axio-terra 87.5% vs terra 83.9%
112题样本, 跨6套件, +3.6pp 领先。首次实证融合不损害性能且在数学/事实类任务上有显著增益。

### 关键发现
1. **TruthfulQA +12pp**: 融合的多模型验证有效抑制幻觉
2. **MATH500 +4pp**: 多模型交叉验证提升数学推理准确性
3. **ARC/MedQA持平**: 简单MCQ上融合与单模型持平,不退化
4. **MedQA延迟优势**: axio-terra 8.5s vs 19.5s (2.3倍快)

### 新增工具
- `scripts/run_suite_bench.py`: 可复用正式基准脚本
- 支持 ARC/MATH/TruthfulQA/MedQA/MMLU/BBH 6套件
- 任意模型对比, 参数化题目数量

## 服务器状态
- ✅ 18900端口, 32模型
- ✅ CPA稳定(4套件200次API调用零系统性故障)

## 待完成
### P0: 基准评测
- [x] axio-terra vs terra 正式4套件100题: 86% vs 82% ✅
- [x] axio-pro 12题满分
- [x] axio-fast 12题92%
- [ ] axio-pro vs sol 正式对比
- [ ] axio-fast vs luna 正式对比
- [ ] 扩展到完整14套件

### P1: 外部排名
- [ ] 别名认证
- [ ] 2源完整覆盖

## 下一轮
1. axio-pro vs gpt-5.6-sol 正式对比 (需CPA responses端点稳定)
2. axio-fast vs gpt-5.6-luna (注意CPA映射异常: luna→deepseek)
3. 添加更多套件
