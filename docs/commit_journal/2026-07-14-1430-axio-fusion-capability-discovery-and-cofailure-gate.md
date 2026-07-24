# 2026-07-14 14:30 Axio Fusion API 能力发现与共同失败率门控

## 本轮目标

先收敛独立商业产品定位的 Axio Fusion API，不推进 ASciFS 第一、二部分的新业务功能。Fusion API 必须能与主项目解耦：输入任意 provider/model inventory、公开能力证据、可选 probe、可选 benchmark feedback，输出统一的 Axio-terra / Axio-pro 能力注册表、能力图谱和 OpenAI/Responses/Anthropic 兼容服务边界。

本轮继续参考并固化以下外部思路：

- SakanaAI Fugu：对外表现为 OpenAI-compatible 模型接口，内部动态组织多模型/多 agent。
- OpenRouter Fusion：困难任务用多模型 panel、judge 和最终 synthesis，而不是单一路由。
- 用户提供的 CSDN Fusion 分析：把 fusion 当作成本、延迟、质量三者之间的系统工程。
- 多 agent 共同失败率研究：不能假设“更多模型一定更好”，必须看不同候选模型是否在同一批样本上共同失败。

## 已完成

1. 修复架构注册表遗漏
   - 将 `axio/fusion_benchmark.py` 登记为 `agent_fabric` 的根级兼容包装。
   - 该文件只有 3 行，实际实现仍在 `axio/fabric/fusion_benchmark.py`，符合“根级 wrapper 必须薄”的架构约束。
   - 修复了全量测试中 `tests/test_architecture.py::test_repository_architecture_validation_accepts_current_layout` 报出的 `unregistered_root_module` warning。

2. 强化独立 Fusion API 产品 manifest
   - `axio/fusion_api/product.py` 继续声明 `axio-fusion-api` 是独立商业产品，非 ASciFS 内部耦合模块。
   - 明确输入是 provider model inventory + capability evidence，输出是 Axio-terra / Axio-pro facade。
   - 增加 `capability-discovery` 命令入口说明。
   - 增加 Fusion 参考源：SakanaAI Fugu、OpenRouter Fusion、用户提供 CSDN 分析、共同失败率评估研究。

3. 建立共同失败率和 branch diversity 门控
   - 在 `quality_contract` 中加入：
     - `per_case_agreement_metrics_required=true`
     - `co_failure_rate_must_gate_panel_promotion=true`
     - `diverse_branches_required_for_pro_panel=true`
     - `fallback_to_best_single_model_when_errors_are_highly_correlated=true`
   - 在 capability discovery workflow 中增加 `co_failure_and_diversity_gate` stage。
   - 在 benchmark gap plan 中增加 `panel_promotion_policy`：
     - 必须记录 per-case agreement metrics；
     - 必须记录 co-failure rate；
     - 必须记录 branch diversity summary；
     - 如果候选分支在同一批 case 上高度共同失败，则回退为 `best_single_model_plus_verifier`。
   - 这保证 Axio-pro 不是盲目堆模型，而是只有在错误互补性成立时才值得走多分支 panel。

4. 能力发现 workflow 已经可生成真实 artifact
   - `python3 -m axio.fusion_api.cli capability-discovery` 能生成：
     - `outputallresult/fusion_api_product/axio_fusion_capability_discovery_workflow.json`
     - `outputallresult/fusion_api_product/model_capability_registry.json`
     - `outputallresult/fusion_api_product/model_capability_graph.json`
     - `outputallresult/fusion_api_product/axio_fusion_capability_discovery_workflow.md`
   - 这些 artifact 只包含 metadata、hash、路径、策略，不保存 raw prompt、benchmark 原题、标签或 provider secret。

5. Benchmark 控制面继续保持机械硬盘缓存策略
   - benchmark download manifest 继续指向 `/mnt/storage/ASciFS/axio_benchmarks`。
   - 仓库只保存 manifest/path/hash/聚合指标，不保存 benchmark 题集、标签、raw case output。
   - 每类核心能力保持两个代表性 benchmark 覆盖：数学、科学知识、代码、逻辑推理、Agentic/tool-use。

## 验证结果

已运行并通过：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_architecture.py::test_repository_architecture_validation_accepts_current_layout \
  tests/test_fusion_api_server.py \
  tests/test_fusion_router_eval.py \
  tests/test_fusion_router_learning.py \
  tests/test_fusion_api_product_boundary.py \
  tests/test_fusion_capability_discovery.py \
  tests/test_model_fusion.py \
  tests/test_fusion_benchmark.py \
  tests/test_llm.py
```

结果：`104 passed in 1.02s`。

已运行并通过：

```bash
python3 -m py_compile \
  axio/architecture.py \
  axio/fusion_api/capability_discovery.py \
  axio/fusion_api/product.py \
  axio/fusion_api/cli.py \
  axio/fabric/model_fusion.py \
  axio/fabric/fusion_benchmark.py \
  axio/core/llm.py
```

CLI dry-run 已运行并能生成 artifact：

```bash
nice -n 10 python3 -m axio.fusion_api.cli capability-discovery \
  --include-default-profiles \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult

nice -n 10 python3 -m axio.fusion_api.cli product-manifest --output-dir outputallresult

nice -n 10 python3 -m axio.fusion_api.cli benchmark-download \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult

nice -n 10 python3 -m axio.fusion_api.cli readiness --output-dir outputallresult
```

抽查结果：

- `panel_promotion_policy.requires_co_failure_rate=true`
- `fusion_algorithm_contract.co_failure_rate_gates_multi_branch_fusion=true`
- product manifest 中包含 SakanaAI Fugu、OpenRouter Fusion、Operator-provided Fusion analysis、Multi-agent co-failure evaluation。
- 对生成 artifact 扫描 `nvapi-`、`sk-...`、`USER_PROMPT_SECRET`、`AXIO_PROBE_OK` 无命中。

## 已知问题和边界

1. 上一轮全量 `pytest -q` 曾在 34 分 38 秒后中断，当时已看到 `595 passed`、`3 failed`、`2 skipped`、`4 warnings`。
2. 本轮已修复其中 architecture warning 对应的问题。
3. 另外两个失败看起来不属于本轮 Fusion API：
   - `tests/test_paper_metadata_store.py::test_base_paper_metadata_store_lists_route_scope_records_for_reuse_preview`
   - `tests/test_quality_gate.py::test_quality_gate_research_acceptance_passes_with_mira_researching_packet`
4. 本轮没有重新跑完整测试套件，原因是全量套件耗时较长且用户要求不要打满 CPU；已使用 `nice -n 10` 跑核心回归。
5. 目前还不能声称 Axio-terra/pro 在真实数学、科学、代码、逻辑、Agentic benchmark 上已经超过最强 provider 单模型；现在完成的是商业可用架构控制面、dry-run 产物链路和防作弊评估约束。真实 claims 必须等官方/等价 runner 的 per-case 结果导入后再说。

## 下一步

1. 接入真实 provider inventory：
   - 从 CPA Plus Responses-compatible 模型清单和 NVIDIA OpenAI-compatible 模型清单生成 `provider_models.json`；
   - 不修改 CPA Plus、CCX、Docker 或其他本地部署项目；
   - API key 只走环境变量，不写入仓库。
2. 完成 live capability discovery：
   - 对可用模型做轻量 probe，只记录 availability、latency、output hash，不记录 probe prompt/output。
   - 对公开资料无法比较的能力轴安排 benchmark gap plan。
3. 完成真实 benchmark runner 串联：
   - 优先从机械硬盘缓存读取 benchmark；
   - 跑 Axio-terra、Axio-pro 和 provider baseline；
   - 导入 aggregate score、per-case correctness hash/agreement/co-failure summary；
   - 不把原题、标签、raw prompt、raw answer 写入仓库。
4. 当 Fusion API 的真实 scorecard 达到可比水平后，再把 Axio-terra/pro 接回 ASciFS Agent Harness，用它支持第一、二部分基础设施继续打磨。
