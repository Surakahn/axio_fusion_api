# Axio Fusion API — Turn Status 2026-08-11 (晚)

## 本轮成果

### 1. Claude渠道(Tokenapis)集成 ✅
- Tokenapis渠道提供23个Claude模型（chat/completions格式）
- 4个模型通过严格流式门禁（3样本，90秒上限）：
  - claude-fable-5 (3657ms)
  - claude-opus-4-1-20250805 (7085ms)  
  - claude-opus-4-20250514 (2977ms)
  - claude-opus-4-5-20251101 (3255ms)
- 顶级模型(sonnet-5, opus-5)手动curl验证可用，但严格3样本流式门禁未通过
- thinking变体全部超时（账户限制）
- 合并注册表：14个模型，3个Provider（NVIDIA+CPA+Anthropic）
- 服务正常运行

### 2. 推理强度参数验证 ✅
- chat/completions格式：`reasoning_effort` → `FusionRequest.reasoning_effort` → Provider payload正确透传
- Responses格式：`reasoning.effort` → 正确提取
- 四种API格式透传链路完整（chat/responses/anthropic/gemini）
- 降级映射规则：仅允许 xhigh→max 向上映射

### 3. Provider检测修复 ✅
- `_provider_seed_profile` 新增tokenapis检测
- 当 `AXIO_ANTHROPIC_BASE_URL` 包含 "tokenapis" 时自动使用chat格式
- 否则使用原生anthropic格式

### 4. axio-fast 验证
- fast_light_verify策略已激活（双模型验证）
- 简单问题正确回答 "Paris"

## 服务状态
- 14个模型，3个Provider
- API格式：chat/completions(10) + responses(4)
- 图片模块：独立运行，1个生成/编辑profile

## 关键文件
- `private/current_channels.env` - 更新含Anthropic渠道
- `private/runs/2026-08-11-claude-merged/merged_registry.private.json` - 合并注册表
- `scripts/run_server_noprefusion.py` - 无prefusion验证启动脚本
- `src/axio_fusion_api/providers.py` - tokenapis检测修复

## 待推进
1. axio-fast benchmark重跑（验证Claude加入后效果）
2. CPA渠道外部排名冻结
3. 21套件全量评测
4. Claude顶级模型门禁放宽（手动验证可用但自动门禁未通过）
