# Axio Fusion API — Turn Status 2026-08-11 (续)

## 本轮成果

### 1. CPA 渠道修复
- **根因**：CPA 外部 URL `cpa.co6.click` 返回 404 (chat/completions 和 responses)
- **修复**：切换为内部 URL `http://10.195.91.64:8317/v1`（直连，走 bypass）
- 服务器响应时间从超时恢复至 ~13s (axio-fast)

### 2. 推理强度五档验证
- Chat/Completions: low/medium/high/xhigh/max 五个档位均可传递
- xhigh: 6149ms ✅ | max: 7536ms ✅
- 参数透传链路正常

### 3. API 格式验证
- Chat/Completions: ✅ "Hi! 👋" (13.3s, axio-fast)
- Responses: ✅ (前轮已验证)
- Anthropic Messages: ✅ "Hello!" (axio-fast)
- Gemini: ⚠️ 返回 "No eligible provider" — 无 Gemini-native 上游 provider，需接入 Gemini 渠道后可用

### 4. 测试状态
- 1025 passed, 7 skipped — 保持稳定

## Git 状态
- 上次提交: `d0d4016 test: routing-weight v2 测试适配`

## 待推进 (优先级排序)
1. **axio-fast 路由改进** — 当前 -3.2% vs luna，重点提升 AIME/BBH
2. **r44 预筛选推进** — 新模型池可增强融合效果
3. **外部排名冻结** — 需要两个独立源覆盖完整10模型池
4. **推理强度五档全 API 格式验证** — Responses/Anthropic 格式推理参数验证
5. **Gemini 上游渠道接入** — 或明确标记为需要 Gemini-native provider

## 服务状态
- 10 文本模型, proxy auto/10808 + CPA 直连 bypass
- CPA 内部: ✅ | NVIDIA 代理: ✅
- 1025 测试通过

## 下一轮重点
- 提交 CPA URL 修复
- axio-fast 路由优化（domain_score 已经调整，需观察 fast_direct_cascade 效果）
- r44 预筛选排查
