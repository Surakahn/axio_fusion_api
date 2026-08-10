# Axio Fusion API — Turn Status 2026-08-10 (Turn 8, Final)

## 本轮核心成果

### Halueval/Medqa重评估 ✅
使用当前reasoning-calibrated服务器重测，旧benchmark结果被证实为stale：
- halueval: 旧0% → 新100% (全融合模型)
- medqa axio-pro: 旧50% → 新100%
- 根因: 旧r43 registry无reasoning transport → 推理参数未传递

### 全量Benchmark重跑 🔄
- 42任务(14套件×3融合模型), subprocess+curl方式, 支持续传
- 已完成: 5/42 (~12%), 预计总耗时~100分钟
- 初步结果: mmmu_text_science 50-62%, global_mmlu_lite 100%

### Reasoning Transport验证 ✅
- GPT-5.6系列5档effort全部正确解析到responses_reasoning
- axio-pro reasoning_effort=max → direct cascade到sol → responses_reasoning/max
- 干运行时完全流通

### 图片模块 ✅
- gpt-image-2 registry已加载(gen+edit各1 profile)
- 端到端测试失败: "All eligible image providers failed"
- 推测CPA渠道不支持images API → 标记为provider限制

## 待完成
- [ ] Benchmark全量完成 + 结果分析
- [ ] NVIDIA模型能力校准
- [ ] 图片模块provider问题调查

## 已知限制
- Python HTTP客户端需 --noproxy 或 trust_env=False
- CPA图片API可能不可用
- 融合因NVIDIA模型高延迟几乎从不激活(直接走direct cascade)
