# 2026-07-14 12:11 Axio Fusion 多选基准运行器收口

## 本轮完成

1. 在 Axio Fusion API 的独立商业产品边界内，新增了可执行的多选基准 runner：
   - 主项目入口：`axio fusion-benchmark-run`
   - 独立商业入口：`axio-fusion-api benchmark-run`
   - 支持 GPQA / MMLU-Pro 风格的 JSONL、JSON、CSV 数据形态。
   - 默认是 dry-run，只解析和验证数据集，不调用外部模型。
   - live 调用必须同时满足 `--live` 和 `AXIO_FUSION_BENCHMARK_ENABLE_LIVE=1`，测试可通过 mock factory 关闭该额外 gate。

2. 完善了反作弊和数据存储边界：
   - 题目、选项、正确标签、原始 prompt 不写入 git 管理产物。
   - live 的 per-case 结果只写入 benchmark cache root，默认机械硬盘路径为 `/mnt/storage/ASciFS/axio_benchmarks`。
   - 报告只记录 schema、状态、case 数、聚合指标、路径、反作弊合同和 prompt-free 路由摘要。
   - 不训练 Axio 或任何 provider 模型权重，只允许聚合指标后续反馈到 router policy。

3. 修正基准任务路由语义：
   - GPQA、MMLU-Pro 不再以 `simple_extraction` 路由。
   - 多选基准会注入 `campaign_acceptance_reviewer` 和 `scientific_reasoning`、`math_reasoning`、`verification` 等能力标签。
   - live case 结果会保存 prompt-free 的 `benchmark_task_type`、`requested_capabilities`、`selected_provider`、`selected_model`、`fusion_strategy_id`、`provider_calls_recorded`，便于后续解释 Axio-terra/pro 的融合决策。

4. 扩展产品文档和产品 manifest：
   - `docs/axio_fusion_api_product.md` 增加 benchmark-run 命令和 live gate 说明。
   - `axio/fusion_api/product.py` 的产品 manifest 增加 `benchmark_run_command` 和 benchmark live 环境变量契约。

5. 增加测试覆盖：
   - dry-run 解析数据集且不调用模型。
   - live 模式缺少环境 gate 时阻塞。
   - mock live 能写入 cache-root per-case 结果，且不含原题正文。
   - GPQA CSV 形态可解析。
   - 主 CLI 和独立 `axio-fusion-api` CLI 的 benchmark-run 默认参数被固定到测试。

## 验证命令和结果

1. 静态编译：
   - `nice -n 10 python3 -m py_compile axio/fusion_api_server.py axio/fabric/model_fusion.py axio/fabric/fusion_benchmark.py axio/cli.py axio/fusion_api/cli.py axio/fusion_api/product.py`
   - 结果：通过。

2. 聚焦回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：`47 passed`。

3. Fusion API 完整相关回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_api_server.py tests/test_fusion_api_product_boundary.py tests/test_fusion_benchmark.py tests/test_cli.py`
   - 结果：`70 passed`。

4. 真实 CLI dry-run：
   - `nice -n 10 python3 -m axio fusion-benchmark-run --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/mmlu_pro_general_reasoning/mmlu_sample.jsonl --cache-root /mnt/storage/ASciFS/axio_benchmarks --output-dir outputallresult`
   - `nice -n 10 python3 -m axio.fusion_api.cli benchmark-run --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/mmlu_pro_general_reasoning/mmlu_sample.jsonl --cache-root /mnt/storage/ASciFS/axio_benchmarks --output-dir outputallresult`
   - 结果：两条入口均生成 `outputallresult/agent_platform/fusion_benchmark_multiple_choice_run.json` 和 Markdown 报告。

5. 干跑产物泄露检查：
   - 检查 `2+2`、`Final answer`、`Correct Answer`、`options`、`answer` 等题目/答案特征。
   - 结果：报告不包含原题正文、选项或标签。

## 当前状态判断

Axio Fusion API 已经具备更清晰的商业产品边界：它可以作为独立模型融合服务对外提供 API，并且拥有独立 benchmark control plane。当前新增的是 GPQA/MMLU-Pro 这种多选基准的第一条可执行 runner，不是最终 benchmark 胜利声明。Axio-terra 是否超过第二好模型、Axio-pro 是否超过最好模型，必须等真实 provider/Axio 同题 live case results 和 scorecard 生成后才能声明。

## 仍未完成的问题

1. 尚未跑真实 CPA Plus / NVIDIA live 基准，因此不能声称 terra/pro 已经达到用户要求的胜出目标。
2. LiveCodeBench、BFCL、tau-bench、SWE-bench Verified 仍是 run matrix 和外部 runner 预留状态，尚未接入各自官方 runner。
3. 当前多选 runner 是串行执行，适合安全验收；后续需要在不打满 CPU 的前提下加入可配置小并发、断点续跑和 per-candidate merge。
4. 当前只生成单 candidate 报告；后续需要加一个批量运行器，自动按 run matrix 跑 Axio-terra、Axio-pro、以及 CPA Plus/NVIDIA 可用单模型基线，再汇总 scorecard。

## 下一步收口范围

下一步不扩大到 ASciFS 第一/二部分全量功能，先把 Axio Fusion benchmark 闭环再收一口：

1. 增加 `fusion-benchmark-batch-run`：
   - 输入 run matrix、suite、dataset、candidate 列表。
   - 串行或小并发跑 Axio-terra、Axio-pro、provider baselines。
   - 每个 candidate 的 per-case JSONL 仍写入 cache root。
   - 自动生成 merged case results。

2. 增加 `fusion-benchmark-eval --case-results merged.jsonl` 的实测联动：
   - 自动生成 scorecard。
   - 明确 terra 是否超过第二好 provider，pro 是否超过最好 provider。
   - 未达标时把失败原因反馈到 router learning，而不是硬编码胜利。

3. 完成该闭环后，再把注意力切回 ASciFS 第一部分和第二部分基础设施：
   - 文献搜索/metadata 存储/图谱路由/Agent Harness 上下文拼接。
   - 多用户上传、知识库、RAG 消费链路。
   - 研究工作台与 Axio Fusion 的内部调用衔接。
