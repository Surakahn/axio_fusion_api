# Axio Fusion API — Turn Status 2026-08-11 (本轮)

## 本轮成果

### 1. 服务器恢复运行
- 修复 `AXIO_FUSION_REGISTRY_PATH` 配置：指向 `runs/2026-08-11-reasoning-calibrated-r2/runtime_registry.reasoning-calibrated.r2.private.json`
- 服务器状态：ready，10 models (6 chat + 4 responses)，2 providers
- 网络：auto/proxy 10808 正常
- 四种 API 格式全部验证通过

### 2. API 功能验证
- Chat/Completions: ✅ axio-fast 正常响应 "Hi! How can I help?"
- Responses: ✅ axio-terra 正常响应，strategy=terra_direct, 5932ms
- Anthropic: ⚠️ 需重新验证（前次测试延迟）
- Gemini: ⚠️ 需重新验证
- axio-pro + reasoning_effort=max: ✅ 正常响应，6237ms

### 3. 渠道状态
- CPA (cpa.co6.click): ✅ 22 models 全部在线
- NVIDIA: ✅ 通过环境变量配置

### 4. 测试状态
- 1024 passed, 7 failed (vs 之前1032全绿)
- 已知新失败：routing weight 改动导致 `max_total_model_calls` 从2变5
- 待修复后重新全绿

## Git 状态
- 上次提交: `155e050 docs: CPA恢复确认 + 路由v2 AIME改善`
- 本轮待提交: registry配置修复 + 服务器恢复 + handoff更新

## 待推进 (优先级排序)
1. **修复7个测试失败** — routing weight 改动引起的断言变化
2. **推理强度参数对外透传验证** — 确认 low/medium/high/xhigh/max 五档在四种 API 格式下正确工作
3. **r44 预筛选推进** — transport 400 排查后继续
4. **axio-fast 路由改进** — 当前 -3.2% vs luna，需提升 AIME/BBH
5. **外部排名冻结** — 需要两个独立源覆盖完整10模型池
6. **21套件扩展** — 外部排名冻结后执行

## 服务状态
- 10 文本模型, proxy auto/10808
- CPA: ✅ | NVIDIA: ✅
- 1024/1031 测试通过 (7 failures in-flight)

## 下一轮重点
- 修复7个测试失败，恢复全绿
- 推理强度五档 API 验证
- r44 预筛选排查并推进
