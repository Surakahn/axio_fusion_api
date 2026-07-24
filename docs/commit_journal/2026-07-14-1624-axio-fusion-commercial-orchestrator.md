# 2026-07-14 Axio Fusion Commercial Orchestrator

## 目标

将 Axio Fusion API 继续推进为独立商业可用服务内核，而不是 ASciFS
内部的轻量路由工具。本轮聚焦三点：

- 公网模型统一为 `axio-fast`、`axio-terra`、`axio-pro`。
- 三个模型对应不同 fusion 算法，而不是同一个模型的三个参数档位。
- 增加 Gemini generateContent 兼容接口，并纳入 smoke / OpenAPI / 产品合同。

## 实现

- 新增 `axio/fabric/fusion_orchestrator.py`，输出 prompt-free
  `fusion_orchestration` 计划，包含请求分析、预算策略、direct/fusion 激活、
  专家面板、任务 DAG、Judge、局部升级、综合计划、运行护栏和学习 trace 合同。
- `axio-fast` 使用 `fast_direct_cascade`，目标为匹敌第三强单模型但成本更低、
  延迟接近单模型请求。
- `axio-terra` 使用 `terra_cost_guarded_fusion`，目标为匹敌第二强单模型但成本更低、
  延迟接近单模型请求。
- `axio-pro` 使用 `pro_panel_judge_escalation`，目标为匹敌或超过最强单模型，
  成本尽量更低，复杂任务通过 panel + judge + targeted escalation + synthesis
  提升可靠性。
- 将成本、能力、延迟目标写入 tier synthesis、route plan、orchestrator 和产品
  manifest，同时明确这些是 target contract；没有 benchmark scorecard 之前不能
  作为商业胜出宣称。
- Fusion API 服务端新增 Gemini 路由：
  `/v1beta/models/{model}:generateContent`、
  `/v1/models/{model}:generateContent`、
  `/v1beta/models/{model}:streamGenerateContent`。
- Smoke 覆盖 chat/completions、responses、anthropic/messages 和 Gemini 四种协议。
- 独立 Fusion CLI 和 router eval 迁移到小写三模型命名。

## 安全与边界

- 本轮没有调用外部 provider，也没有写入任何 API key。
- Route plan、smoke、audit、orchestrator 均保持 metadata-only，不持久化 raw prompt、
  raw source text、benchmark question、benchmark label 或 secrets。
- 未修改 CPA Plus、CCX 或其他本地部署项目代码。

## 验证

```bash
python3 -m py_compile axio/fabric/model_fusion.py axio/fabric/fusion_orchestrator.py axio/fusion_api_server.py axio/fusion_api/product.py axio/fusion_api/cli.py
nice -n 10 python3 -m pytest -q tests/test_model_fusion.py tests/test_fusion_api_server.py tests/test_fusion_api_product_boundary.py
nice -n 10 python3 -m pytest -q tests/test_fusion_provider_inventory.py tests/test_fusion_benchmark.py tests/test_fusion_api_product_boundary.py tests/test_fusion_capability_discovery.py tests/test_fusion_api_server.py tests/test_fusion_router_eval.py tests/test_fusion_router_learning.py tests/test_model_fusion.py tests/test_llm.py
```

结果：

- Fusion API 核心回归：`52 passed`
- Fusion 聚焦回归：`114 passed`
