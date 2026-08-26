# Axio Fusion API

> **模型融合即服务** — 将任意渠道的异构大模型自动编排为稳定、高性能的三档融合模型家族

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![GitHub](https://img.shields.io/badge/GitHub-Surakahn/axio__fusion__api-green.svg)](https://github.com/Surakahn/axio_fusion_api)

## 愿景

今天，大语言模型（LLM）的竞争格局瞬息万变：每周都有新模型发布，供应商不断调整定价与能力，企业级应用面临"模型锁定"和"渠道脆弱性"两大挑战。

**Axio Fusion API** 给出了根本性的解决方案：**不依赖任何单一模型，而是动态融合多个异构模型的能力**。无论底层接入的是 NVIDIA NIM、OpenAI Responses、Anthropic Messages 还是 Google Gemini——Axio 始终对外暴露稳定的三档融合模型：

| 模型 | 定位 | 融合策略 |
|------|------|----------|
| **axio-fast** | 高性价比快速响应 | 直接级联 + 智能降级 |
| **axio-terra** | 平衡智能与成本 | 选择性融合 + 独立验证 |
| **axio-pro** | 最高智能深度推理 | 专家面板 + 裁判 + 定向纠错 + 综合作答 |

### 核心创新

1. **渠道无关性**：切换底层模型供应商只需更新配置，无需修改任何业务代码
2. **异构协议归一**：同时接入 Chat/Completions、Responses、Anthropic、Gemini 四种原生协议，统一对外暴露
3. **实时能力编排**：基于实测延迟、推理强度、工具能力等维度动态分配融合角色
4. **闭环质量监控**：28 题校准任务集定期检测融合模型能力水平，渠道切换时自动触发适配
5. **生产级安全**：API key 零持久化、provider 故障自动降级、结构化审计追踪

### 应用前景

- **企业 AI 中台**：对接内部知识库与工具链，享受始终最优的模型能力而不锁定单一供应商
- **AI-Native 产品**：SaaS/CRM/ERP 等工具型产品通过 Axio 获得稳定、可预期的模型行为
- **评测与基准平台**：作为标准化模型接入层，公平比较不同供应商模型的融合效果
- **研究机构**：探索模型融合（MoA、Fugu-style）的新算法与策略

## 当前状态（2026-08-27）

### 已完成
- ✅ axio-fast / axio-terra / axio-pro 三档融合模型全部正常响应
- ✅ Chat/Completions、Responses、Anthropic、Gemini 四种对外 API 格式
- ✅ 多供应商接入（NVIDIA Chat + CPA Plus Responses/Anthropic）
- ✅ 推理强度五档参数（low/medium/high/xhigh/max）透传
- ✅ 图像生成/编辑独立模块（gpt-image-2）
- ✅ 1000+ 自动化测试
- ✅ 生产工程回归、四协议兼容、图片 lane 隔离和 Harness 控制面已具备可审计证据
- ✅ `/health` 同时报告物理 provider profile 与 canonical logical model 计数，支持副本和
  failover 容量观察
- ✅ BizBench 任务感知 audited evaluator：8 个任务按多选、数值/开放词汇抽取、程序合成和
  FormulaEval 分流，使用 1% 数值容差、SEC-NUM exact span 与隔离合成测试；不冒充第三方 official harness
- ✅ 路由契约回归修复：Fast 普通短请求不会误触发轻量校验；`health=unavailable/failed`
  的 profile 不再进入候选池；恢复 7 个历史跳过用例后全量回归为 `1114 passed, 0 skipped`
- ✅ r18 preflight artifact 强绑定：operational-admission 内容 hash 必须匹配 frozen
  plan，safe/private 混用会 fail-closed 为 `binding_mismatch`
- ✅ Harness convergence artifact 敏感字段门禁：各 stage 递归拒绝 raw prompt/output、
  label、URL、路径和 secret 持久化声明
- ⏳ provider baseline screening/ranking/freeze 与完整 21 套 benchmark 仍在门禁流程中

### 评价证据边界

正式目标是 9 类 21 套 benchmark。历史 14 套结果属于旧 cohort，不能作为当前
provider baseline freeze、同 case 对比或 superiority 证据；在完整 screening、
transport admission、complete-pool ranking、baseline freeze、同 cohort Harness
binding 和最终统计审计完成前，不声明三档 Fusion 优于对应单模型。

### 待推进
- r18 live screening（仍需 operator 明确授权）以及后续 transport admission、完整池排名和 baseline freeze
- 自适应渠道接入元提示词系统
- provider baseline screening/ranking/freeze
- 9 类 21 套件完整基准评测与 final audit

## 快速开始

```bash
# 1. 配置渠道
cp config/current_channels.example.json private/current_channels.json
# 编辑填入 API key

# 2. 启动服务
PYTHONPATH=src python3 scripts/run_server.py

# 3. 调用融合模型
curl http://127.0.0.1:18900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "axio-pro",
    "messages": [{"role": "user", "content": "解释量子纠缠"}],
    "reasoning_effort": "max",
    "stream": true
  }'
```

## 架构

```
公共 HTTP API (4 种格式)
        │
   ┌────▼────┐
   │  Compat │  协议归一化 + 推理强度提取
   └────┬────┘
   ┌────▼────────┐
   │  Router     │  任务分析 + 三档策略选择 + 专家角色分配
   └────┬────────┘
   ┌────▼───────────┐
   │  Orchestrator  │  并行专家面板 + 裁判 + 定向纠错 + 综合作答
   └────┬───────────┘
   ┌────▼───────┐
   │ Providers  │  异构协议适配 + 流式透传 + 故障降级
   └────────────┘
```

## 参考与致意

本项目融合策略借鉴了以下前沿工作：
- **Fugu** (Sakana AI) — 能力感知的模型融合
- **MoA / Hermes** — 多智能体混合架构
- **OpenRouter Fusion** — 成本与质量的自动平衡

## 许可证

GPL-3.0 License
