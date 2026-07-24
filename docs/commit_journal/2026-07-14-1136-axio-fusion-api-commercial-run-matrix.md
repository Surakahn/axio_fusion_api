# 2026-07-14 11:36 Axio Fusion API 商业产品边界与基准运行矩阵

## 本轮完成

1. 将 Axio Fusion API 继续按独立商业产品收口。
   - 保留 `Axio-nano`、`Axio-terra`、`Axio-pro` 三个外部模型层级。
   - 继续保持 ASciFS 主流程解耦：Fusion API 不依赖论文库、图数据库、Studio UI 或研究工作流产物即可提供服务。
   - Standalone CLI `axio-fusion-api` 新增 `benchmark-run-matrix`，与 `serve`、`readiness`、`openapi`、`product-manifest` 一起构成产品级入口。

2. 加强 benchmark 控制面，避免虚假宣称基准胜出。
   - 新增 `fusion_benchmark_run_matrix`，为每个 benchmark suite 生成 Axio-terra、Axio-pro 和单模型 provider baseline 的运行矩阵。
   - 每个 run row 固定 `case_results.jsonl`、`aggregate_result.json`、audit log 路径，全部落到 benchmark cache root，默认 `/mnt/storage/ASciFS/axio_benchmarks`。
   - 明确 `Axio-terra` 目标是超过第二好的单模型 baseline，`Axio-pro` 目标是超过最好的单模型 baseline。
   - 继续坚持反作弊边界：benchmark 题目、标签、原始 prompt、provider secrets、大型 per-case 输出不进 git；scorecard 只能读取官方 runner 或等价 runner 的 per-case JSONL。

3. 修复 Module 1/2 model fusion readiness 的质量门禁漂移。
   - `quality_gate` 复用 Studio 的 `build_module_1_2_model_fusion_readiness` 作为 projection 期望来源，避免治理层和 UI 层双写字段逻辑后漂移。
   - 修正测试夹具中 PRD coverage 后的 Studio final pass，使完整 fixture 更接近真实 workflow 的 seed/final Studio 生成节奏。
   - 保留 stale-drift 负例测试，确认质量门禁没有被放松。

4. 生成产品 artifacts。
   - `outputallresult/fusion_api_product/axio_fusion_api_product_manifest.json`
   - `outputallresult/fusion_api_product/axio_fusion_api_openapi.json`
   - `outputallresult/agent_platform/fusion_benchmark_run_matrix.json`
   - `outputallresult/agent_platform/fusion_benchmark_eval_plan.json`

## 验证结果

- `nice -n 10 python3 -m py_compile axio/governance/quality_gate.py axio/studio_shell/studio_state.py axio/fabric/fusion_benchmark.py axio/cli.py axio/fusion_api/cli.py tests/test_quality_gate.py tests/test_fusion_benchmark.py tests/test_cli.py`
- `nice -n 10 python3 -m pytest -q tests/test_fusion_api_server.py tests/test_fusion_api_product_boundary.py tests/test_fusion_benchmark.py tests/test_cli.py`
  - 结果：66 passed。
- `nice -n 10 python3 -m pytest -q tests/test_quality_gate.py::test_quality_gate_accepts_multi_agent_governor_when_manifest_points_to_it tests/test_quality_gate.py::test_quality_gate_passes_complete_agent_rag_closure tests/test_quality_gate.py::test_quality_gate_fails_when_project_state_module_1_2_model_fusion_projection_drifts`
  - 结果：3 passed。

## 当前边界

- Axio Fusion API 的商业服务边界、协议兼容层、生产 readiness、benchmark run matrix、eval plan、scorecard 导入门禁已经具备。
- 还不能声称 `Axio-terra` 或 `Axio-pro` 已经真实超过 CPA Plus/NVIDIA 中的第二好或最好单模型；目前完成的是防作弊评估控制面，还缺真实官方 benchmark runner 执行和 per-case 结果导入。
- 当前 streaming 是 SSE-compatible wrapper，不是 provider token-level streaming；readiness 中已经显式标明 `provider_token_streaming: False`。
- 不使用 CCX 模型接口，不修改 CPA Plus、CCX 或任何本地 Docker 项目；CCX 仅作为协议形态参考。

## 下一步

1. 为 `fusion_benchmark_run_matrix` 接入小规模 env-gated live runner：
   - 先只做 GPQA/MMLU-Pro 这类可控 JSONL 多选类 runner；
   - 仅在显式传入 live/env 时调用 CPA Plus/NVIDIA；
   - per-case 结果写入 `/mnt/storage/ASciFS/axio_benchmarks/runs/.../case_results.jsonl`。
2. 在小规模真实 runner 稳定后，再接 LiveCodeBench/BFCL/tau-bench/SWE-bench Verified 官方 runner adapter。
3. 完成真实 scorecard 后，才允许声明 `Axio-terra`/`Axio-pro` 是否达到用户要求的 benchmark 目标。
4. Fusion API 收口后，回到 ASciFS 第一部分、第二部分基础设施：论文 metadata-only 搜索存储、图谱路由、Agent Harness prompt/context 拼接、用户上传/RAG/多用户隔离。
