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
