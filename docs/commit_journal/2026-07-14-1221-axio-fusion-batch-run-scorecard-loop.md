# 2026-07-14 12:21 Axio Fusion 批量基准与 Scorecard 闭环

## 本轮完成

1. 新增多候选 batch-run 能力：
   - 主项目入口：`axio fusion-benchmark-batch-run`
   - 独立商业入口：`axio-fusion-api benchmark-batch-run`
   - 输入同一个 suite 和 dataset，可一次跑 Axio-terra、Axio-pro 以及 run matrix 中的 provider baselines。
   - `--candidate-id` 可重复指定；不指定时使用 run matrix 选出的候选集合。
   - `--no-provider-baselines` 可只跑 Axio 两档。

2. 打通 merged case results 与 scorecard：
   - batch-run 复用单候选 `run_fusion_benchmark_multiple_choice`，避免两套判分逻辑漂移。
   - live 模式下读取每个候选的 cache-root `case_results.jsonl`。
   - 合并到 cache root 下的 `runs/<suite>/merged_case_results.jsonl`。
   - 自动调用 `build_fusion_benchmark_scorecard`，输出 scorecard。
   - scorecard 会严格检查 Axio-terra 是否超过第二好 provider、Axio-pro 是否超过最好 provider；如果没有实测胜出就给出 blocker，不会硬编码胜利。

3. 保持存储和反作弊边界：
   - dry-run 不调用模型，不生成 per-case 输出。
   - live per-case 和 merged JSONL 都只写入 `/mnt/storage/ASciFS/axio_benchmarks` 等 benchmark cache root。
   - repo 输出只保存 batch report、Markdown 和聚合 scorecard。
   - 不写入题目、选项、正确答案、原始 prompt 或 provider secret。

4. 产品和文档同步：
   - `axio/fusion_api/product.py` 增加 `benchmark_batch_run_command`。
   - `docs/axio_fusion_api_product.md` 增加 batch-run 的商业部署命令和说明。
   - 主 CLI 和独立 CLI 都固定了默认参数测试。

## 验证命令和结果

1. 静态编译：
   - `nice -n 10 python3 -m py_compile axio/fabric/fusion_benchmark.py axio/cli.py axio/fusion_api/cli.py axio/fusion_api/product.py tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：通过。

2. 聚焦回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：`49 passed`。

3. 完整 Fusion API 相关回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_api_server.py tests/test_fusion_api_product_boundary.py tests/test_fusion_benchmark.py tests/test_cli.py`
   - 结果：`72 passed`。

4. 主 CLI batch dry-run：
   - `nice -n 10 python3 -m axio fusion-benchmark-batch-run --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --candidate-id Axio-pro --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/mmlu_pro_general_reasoning/mmlu_sample.jsonl --cache-root /mnt/storage/ASciFS/axio_benchmarks --output-dir outputallresult`
   - 结果：生成 `outputallresult/agent_platform/fusion_benchmark_multiple_choice_batch_run.json` 和 Markdown。

5. 独立商业 CLI batch dry-run：
   - `nice -n 10 python3 -m axio.fusion_api.cli benchmark-batch-run --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --candidate-id Axio-pro --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/mmlu_pro_general_reasoning/mmlu_sample.jsonl --cache-root /mnt/storage/ASciFS/axio_benchmarks --output-dir outputallresult`
   - 结果：同样生成 batch report 和 Markdown。

6. 干跑产物泄露检查：
   - 检查 `2+2`、`Final answer`、`Correct Answer`、`options`、`answer` 等题目/答案特征。
   - 结果：batch report 和 Markdown 不包含原题正文、选项或标签。

## 当前状态判断

Axio Fusion API 的商业基准链路已经从“单候选 runner”推进到“同题多候选 batch-run + merged JSONL + scorecard”。这完成了验证 terra/pro 与 provider baselines 的工程闭环，但仍然没有真实 live 基准结果，因此不能声称 Axio-terra/pro 已达到用户设定的胜出目标。

## 仍未完成的问题

1. 尚未使用真实 CPA Plus 和 NVIDIA 可用模型跑 live batch。
2. 尚未下载真实 GPQA / MMLU-Pro 数据集，只用了机械硬盘 cache 下的最小样本验证工程路径。
3. 当前 batch-run 是串行执行；后续可加入保守小并发、断点续跑、失败候选重试和 per-candidate skip logic。
4. LiveCodeBench、BFCL、tau-bench、SWE-bench Verified 仍需要接官方 runner 或稳定导入适配器。

## 下一步收口范围

下一步继续保持范围小而实：

1. 增加 `fusion-benchmark-live-readiness` 或等价能力：
   - 检查 CPA Plus Responses API 和 NVIDIA OpenAI-compatible API 的环境变量是否齐全。
   - 不打印、不保存真实 key。
   - 调用 `/v1/models` 或轻量 probe，确认候选模型是否可用。

2. 增加 batch-run 的 resume / skip 逻辑：
   - 如果候选的 `case_results.jsonl` 已存在且 case 数匹配，可跳过。
   - 支持 `--rerun` 强制重跑。
   - 避免真实 live 基准重复消耗调用额度。

3. 通过 readiness 后，再用小样本真实 live batch 验证 Axio-terra/pro/provider baselines 的完整 scorecard。

完成这些之后，Axio Fusion API 就更接近“可商业使用的独立模型融合服务”；之后再回到 ASciFS 第一部分/第二部分基础设施主线。
