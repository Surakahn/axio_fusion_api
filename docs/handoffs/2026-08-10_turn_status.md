# Axio Fusion API — Turn Status 2026-08-10 (Turn 8)

## 本轮核心成果

### Benchmark 重新评估 ✅
使用当前reasoning-calibrated服务器重测halueval和medqa（旧benchmark因旧服务器配置不准确）：

| Suite | axio-fast | axio-terra | axio-pro | 旧结果 |
|-------|-----------|------------|----------|--------|
| halueval | 100% (4/4) | 100% (4/4) | 100% (4/4) | 旧: 0%全模型 |
| medqa_usmle | 75% (3/4) | 50% (2/4)* | 100% (4/4) | 旧: pro 50% |

*axio-terra有2个timeout (45s超时)

### 关键发现
- **halueval**: 旧0%是完全stale的artifact，当前服务器融合模型全部100%
- **medqa axio-pro**: 旧50%→新100%，大幅改善
- **融合管道**: axio-pro对简单MCQ走direct cascade到sol，性能应与sol一致
- **代理干扰**: Python HTTP客户端需 `trust_env=False` 或 `--noproxy` 才能访问本地axio服务器

### 根本原因分析
旧benchmark服务器(r43 registry)与当前服务器(reasoning-calibrated)的关键差异：
1. Reasoning transport全为unknown → 推理参数无法传递给上游provider
2. 可能不同的系统提示词注入
3. 导致响应质量下降

### 待完成
- [ ] 全量benchmark用当前服务器重跑 (14 suites, 所有模型)
- [ ] NVIDIA nemotron-3-super实际能力校准
- [ ] 图片模块端到端验证
- [ ] 推理强度参数对外API文档

### 已知限制
- Python HTTP库需特殊处理代理 (trust_env=False/noproxy)
- axio-terra在medqa有偶发timeout
- 旧benchmark结果不可靠，需全量重跑
