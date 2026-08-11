# Axio Fusion API — Handoff 2026-08-12 (Turn 4)

## 本轮关键发现

### CPA 模型映射异常
- **gpt-5.6-luna → deepseek-v4-pro**：CPA网关将luna请求映射到deepseek-v4-pro
- gpt-5.6-terra → gpt-5.6-terra ✅
- gpt-5.6-sol → gpt-5.6-sol ✅
- gpt-5.5/gpt-5.4 正常 ✅

**影响**: 之前所有以luna为基线的对比实际是vs deepseek-v4-pro。需修正基线策略。

### axio-terra vs gpt-5.6-terra 对比

| 套件 | axio-terra | gpt-5.6-terra |
|------|-----------|---------------|
| ARC-Challenge | 2/2 | 2/2 |
| MedQA USMLE | 2/2 | 2/2 |
| BBH | 1/2 | 1/2 |
| **总计** | **5/6 (83%)** | **5/6 (83%)** |

打平。需更多样本才能区分。

### 累计基准数据 (axio-terra)

| 套件 | 得分 | 样本 |
|------|------|------|
| ARC-Challenge | 100% | 5题 |
| TruthfulQA | 100% | 5题 |
| BBH | ~80% | 5题 |
| MedQA USMLE | 100% | 5题 |
| Global MMLU | 100% | 3题 |
| MATH500 | 60% | 5题 |
| **综合** | **~87%** | 28题 |

### axio-fast 延迟分析
- 单次简单问答: 27.8秒, 5次provider调用
- fast_light_verify模式触发双模型验证，增加延迟
- 不适用于实时benchmark，需批量异步评测

### axio-pro 状态
- 首次调用成功，后续受CPA限流影响
- max_in_flight=2尝试导致panel phase超时（已回退）
- 需要重试退避 + min_request_interval策略配合

## 服务器状态
- ✅ 18900端口, 24模型, 正常运行
- ✅ 推理强度五档管线通
- ✅ 四种API格式兼容

## 待完成
1. 用gpt-5.6-sol替代luna作为最强基线
2. axio-pro稳定化后完整评测
3. axio-fast批量异步评测
4. 外部排名冻结
5. 14套件 × 更多样本的完整基准

