# Axio Fusion API — Turn Status 2026-08-10

## 当前进度位置

### 已完成
1. Fusion API 核心系统：router、orchestrator、registry、providers、compat
2. 服务器运行：127.0.0.1:18900，3 公开模型 + 4 API 格式
3. Benchmark v3 完成：14 suite x 6 model x 8 sample = 84 结果
4. axio-pro 达标：57.6% vs gpt-5.6-sol 57.1% (+0.4%)
5. Deadline 预算优化：FUSION_GUARD 3.0->4.5, FAST_MULTIPLIER 2.5->3.5
6. axio-terra legalbench 单次验证：0err（之前 7/8 err）
7. 四种 API：chat/completions, responses, anthropic, gemini 全部通过

### 未完成
1. axio-terra 达标：需 vs gpt-5.6-terra 改善（当前-13.4%，deadline修复后待重测）
2. axio-fast 达标：需 vs gpt-5.6-luna 改善（当前-16.1%，deadline修复后待重测）
3. 完整 21 基准评测：当前仅 14 suite，缺 code/agentic/general knowledge
4. 推理强度参数透传：代码已有但未端到端测试
5. 自适应渠道接入 prompt recalibration：未实现
6. axio-pro 输出过于冗长：包含内部 JSON reasoning 结构

### 关键文件
- scripts/focused_rerun.py：聚焦重测（6 suite，terra+fast vs 基线）
- scripts/_bench_worker.py：subprocess worker（prompt 通过 stdin）
- scripts/run_benchmark_v3.py：完整 14-suite benchmark
- src/axio_fusion_api/router.py：deadline 常量
- private/bench_results_v3.json：完整 84 结果
- private/runs/2026-08-09-prefusion-cohort-r43/：当前 registry

### 已知限制
1. BBH/MATH500/flores/bizbench 评分对所有模型都低（公平但绝对值低）
2. NVIDIA 渠道模型大多超时（p95=20001ms）
3. CPA 直连 127.0.0.1:8317（需 no_proxy）
4. env 变量需 wrapper 脚本传给服务器

### 下一步
1. 运行 focused_rerun.py 验证 deadline 修复效果
2. 若改善不足：分析路由计划、增加 provider fallback
3. 下载缺失 benchmark（code/agentic 类）
4. 推理强度端到端测试
5. axio-pro 输出后处理优化
