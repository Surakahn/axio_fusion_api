# Axio Fusion API — Handoff 2026-08-12 (Turn 2)

## 本轮完成

### 1. Provider韧性增强
- `AXIO_FUSION_PROVIDER_RETRY_BACKOFF_MS=1000` — 指数退避重试 (1s/2s/4s/8s)
- `AXIO_FUSION_PROVIDER_MAX_ATTEMPTS_PER_KEY=3` — 每次key最多3次尝试（允许2次重试）
- 502/503/500等HTTP错误现已retryable（代码中已支持，env启用退避）

### 2. 推理强度管线验证
- **Chat格式**: `reasoning_effort` → 顶层参数 `payload["reasoning_effort"]=max`
- **Anthropic格式**: `reasoning.effort` → `thinking: {type:"enabled", budget_tokens:N}`
  - low→1024, medium→4096, high→8192, xhigh→16384, max→32768
- **Responses格式**: `reasoning.effort` → 嵌套 `reasoning: {effort: "max"}`
- **映射规则**: xhigh→max唯一允许的向上映射
- 验证: axio-terra + reasoning_effort=max → "Hi. What are you working on?" ✅

### 3. 稳定性测试
- axio-terra: ✅ 稳定 (多次调用均正确)
- axio-fast: ⚠️ 偶发失败 (CPA间歇502)
- axio-pro: ⚠️ 首次调用成功，后续因CPA限流失败

### 4. 文档更新
- Anthropic Messages API完整参考 (docs/api_refs/)
- 推理强度管线文档化
- 基准测试日志更新

## 当前服务器
- 24模型, 3 Provider, 4 API格式
- Port 18900, 状态 ready
- 推理强度: low/medium/high/xhigh/max 五档全支持

## 阻塞项
1. **CPA不稳定**: 间歇502+限流 → 阻塞完整benchmark
2. **外部排名冻结**: 需要2个独立排名来源
3. **axio-pro并行执行**: CPA限流导致panel phase频繁失败

## 下一步
- 继续等待CPA恢复稳定后跑完整benchmark
- 准备简化版本地benchmark（不依赖外部provider）
- 外部排名来源调研

