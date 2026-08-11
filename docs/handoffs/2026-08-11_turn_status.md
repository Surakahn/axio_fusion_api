# Axio Fusion API — Turn Status 2026-08-11 (续2)

## 本轮成果

### 1. Fast 路由 Domain-Aware 选模 (已提交)
- 新增 `FAST_DIRECT_DOMAIN_WEIGHT = 0.10`
- `_fast_direct_candidate_order` 现在接受 `analysis` 参数
- `sort_key` 中引入 `_domain_average(profile, _domain_axes)` 评分
- 有 domain 信息时，BASE 权重从 0.90 让出 0.10 给 domain
- 无 domain 信息时行为不变（向后兼容）
- 效果：数学/逻辑/编程等任务自动优先选对应能力强的模型

### 2. Claude 渠道接入
- 新增渠道：`https://tokenapis.com/v1/messages` (Anthropic 格式)
- 10 个 Claude 模型可用：opus-5, opus-4-8/4-7/4-6, sonnet-5/4-6, haiku-4-5, fable-5
- 当前状态：账号池不足 ("No available accounts")，首次请求成功后续限流
- 已配置环境变量供后续使用

### 3. CPA 渠道修复
- 外部 URL (cpa.co6.click) 返回 404 → 切换内部 URL (10.195.91.64:8317)
- 添加内部地址到 proxy bypass

### 4. 测试状态
- 1025 passed, 7 skipped — 稳定

## Git 提交 (本轮)
```
e7ed409 feat: fast路由domain-aware选模 + Claude渠道配置
7d31f1d fix: CPA URL 切换至内部地址 + 推理强度验证
d0d4016 test: routing-weight v2 测试适配 — 1025 passed, 7 skipped
0421302 feat: 服务器恢复 + fast_light_verify 阈值调低
```

## 服务状态
- 10 文本模型, proxy auto/10808
- CPA 内部: ✅ | NVIDIA 代理: ✅ | Claude: ⚠️ 账号池不足
- axio-fast 数学验证：✅ 正确解二次方程 (7.3s, domain-aware)

## 待推进
1. **Claude 渠道恢复后接入** — 10 个模型可极大增强融合池
2. **r44 预筛选重跑** — CPA URL 修复后 transport 应恢复正常
3. **外部排名冻结** — 需两个独立源覆盖完整模型池
4. **axio-fast benchmark 重跑** — 验证 domain-aware routing 效果
5. **推理强度五档全格式验证** — Responses/Anthropic 格式

## 下一轮重点
- Claude 渠道恢复监测
- 如需，可重跑快速 benchmark 验证 domain-aware 效果
- r44 预筛选状态检查（transport 修复后）
