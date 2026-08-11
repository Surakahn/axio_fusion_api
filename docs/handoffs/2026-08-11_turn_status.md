# Axio Fusion API — Turn Status 2026-08-11 (深夜续)

## 本轮成果

### 1. CPA渠道重新注册 ✅（重大进展）
- 从原来4个CPA模型扩展到20个发现/12个可用
- 新纳入：deepseek-v4-flash, kimi-k2.6, kimi-k2.7-code, glm-5.2, qwen3.8-max, minimax-m2.7, gpt-5.4
- 过滤掉辅助模型 codex-auto-review

### 2. CPA API格式修复 ✅
- **关键发现**：GPT-5.6系列在CPA的responses API失败（NoneType），但在chat/completions成功
- 修复：gpt-5.6-sol/terra/luna, gpt-5.5, gpt-5.4 → api_format改为chat
- 中国模型(kimi/glm/qwen/minimax/deepseek)保持responses格式

### 3. 三渠道合并注册表 ✅
- 22个模型，3个Provider（CPA 12 + NVIDIA 6 + Anthropic 4）
- API格式：chat/completions(15) + responses(7)
- 服务正常运行

### 4. axio模型验证
- axio-fast: ✅ 正确回答 "4" (2+2)，fast_light_verify/2m策略
- axio-terra: ✅ 正确，terra_direct/2m
- axio-pro: ⚠️ 部分provider分支失败（responses格式模型不稳定）

## 服务状态
- 22模型，3Provider
- 图片模块：独立运行

## 关键文件
- `private/runs/2026-08-11-cpa-reenrollment/` - CPA重新注册产物
- `private/runs/2026-08-11-triple-merge/merged_registry.private.json` - 三渠道合并注册表
- `src/axio_fusion_api/providers.py` - CPA GPT模型chat格式修复

## 待推进
1. axio-pro responses模型稳定性修复
2. 全量benchmark重跑（验证22模型池效果）
3. 外部排名冻结
4. Claude顶级模型门禁放宽
