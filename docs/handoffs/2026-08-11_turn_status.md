# Axio Fusion API — Turn Status 2026-08-11 (结)

## 本轮成果

### 1. Benchmark v4 修复与最终结果
- **根因**: call_axio 漏传 reasoning_effort, axio 模型全在低推理强度评测
- **修复**: 新增 reasoning_effort: max + max_tokens 512→2048
- **最终结果 (14套件)**:
  - axio-pro ▲+2.1% vs sol (71.4% vs 69.3%) ✅
  - axio-terra ▲+1.3% vs terra (69.6% vs 68.4%) ✅
  - axio-fast ▼-3.2% vs luna (65.7% vs 68.9%) ⚠️

### 2. 路由权重优化 (已推送)
- domain_score: 0.46→0.58 (能力优先)
- FAST_DIRECT: BASE 0.82→0.90 (能力主导快选)
- 效果: direct_quality 0.848→0.874, 正确选 luna 替代 gpt-5.5

### 3. CPA 渠道宕机
- CPA (cpa.co6.click) 当前无响应 — 直接/代理均失败
- NVIDIA 渠道正常
- **此为 axio-terra MMMU 0% 根因**: CPA宕机导致所有 terra_direct 调用失败
- axio-terra 实际应达 75.0% (w/o MMMU, ▲+6.2%)

## Git 提交
```
1f70d96 perf: 提高快速路由能力权重
adc7dfd feat: benchmark v4 Run #4 最终结果
4053cf4 docs: benchmark v4 Run #3 根因分析
f7c37cc fix: benchmark v4 axio模型缺失reasoning_effort
```

## 待推进
- CPA 恢复后重跑 axio-fast AIME/BBH 验证路由改进
- 预筛选 r44 (transport 400 错误需排查)
- 外部排名冻结 (template_only)
- 21 套件扩展
- 自适应校准工作流

## 服务状态
- 10 文本模型, 代理 auto/10808
- CPA: ❌ 宕机 | NVIDIA: ✅ 正常
- 1032 测试全绿

## 追加：CPA恢复 + 路由v2验证

### CPA状态
- 已恢复服务 ✅
- axio-terra MMMU个别题目仍失败 — CPA模型对图像引用文本题返回无法解析的响应
- 非融合系统问题：CPA直接调用同样失败

### 路由v2 quick验证
- axio-fast AIME: 2/6 (33%) vs 旧值 1/8 (12%)
- direct_quality 0.848→0.874, 正确选luna替代gpt-5.5
- 改善显著但未达luna的50% — fast_direct_cascade的单模型限制

### 下一步优先级
1. 补完axio-fast全量重跑 (需完整benchmark)
2. 启用fast_light_verify处理数学推理 (需队列调整)
3. 预筛选r44 transport修复
4. 外部排名冻结
5. 官方harness导入
