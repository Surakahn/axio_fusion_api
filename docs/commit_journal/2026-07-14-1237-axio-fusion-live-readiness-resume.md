# 2026-07-14 12:37 Axio Fusion Live Readiness 与断点复用

## 本轮完成

1. 新增 live benchmark readiness 能力：
   - 主项目入口：`axio fusion-benchmark-live-readiness`
   - 独立商业入口：`axio-fusion-api benchmark-live-readiness`
   - 默认只做静态环境检查，不调用任何模型。
   - 可选 `--probe` 才会做极小 live probe。
   - readiness 报告覆盖 Axio-terra、Axio-pro 和 run matrix 中的 provider baselines。

2. readiness 的安全边界：
   - 不打印、不保存真实 API key。
   - 不保存 raw probe prompt。
   - 不保存 provider response text。
   - 只保存 provider/model、endpoint family、base URL 是否配置、base URL hash、API-key count、blockers、probe hash 和错误类型。
   - Axio-tier readiness 不再伪装成某个单一 provider key，而是检查 CPA Plus / NVIDIA backing provider group 是否有可用凭据。

3. 新增 live benchmark 断点复用：
   - 单候选 runner 增加 `reuse_existing` / `rerun`。
   - CLI 增加 `--reuse-existing` 和 `--rerun`。
   - 当 cache-root `case_results.jsonl` 已覆盖本次数据切片的 `case_id_hash` 时，`--reuse-existing` 会跳过模型调用并复用已有结果。
   - `--rerun` 可显式忽略旧结果，重新跑候选。
   - batch-run 复用同一套单候选逻辑，避免恢复逻辑分叉。

4. 产品文档和 manifest 更新：
   - `axio/fusion_api/product.py` 增加 `benchmark_live_readiness_command`。
   - batch-run 示例默认加入 `--reuse-existing`。
   - `docs/axio_fusion_api_product.md` 说明 live-readiness、probe 安全边界、reuse/rerun 使用方式。

## 验证命令和结果

1. 静态编译：
   - `nice -n 10 python3 -m py_compile axio/fabric/fusion_benchmark.py axio/cli.py axio/fusion_api/cli.py axio/fusion_api/product.py tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：通过。

2. 聚焦回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：`52 passed`。

3. 完整 Fusion API 相关回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_api_server.py tests/test_fusion_api_product_boundary.py tests/test_fusion_benchmark.py tests/test_cli.py`
   - 结果：`75 passed`。

4. 主 CLI readiness dry-run：
   - `nice -n 10 python3 -m axio fusion-benchmark-live-readiness --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --candidate-id Axio-pro --candidate-id provider::nvidia/nemotron-mini-4b --cache-root /mnt/storage/ASciFS/axio_benchmarks --output-dir outputallresult`
   - 当前机器未设置 live provider 凭据，报告正确给出 blockers：Axio backing provider credentials 缺失，NVIDIA API key 缺失。

5. 主 CLI / 独立商业 CLI batch dry-run：
   - `nice -n 10 python3 -m axio fusion-benchmark-batch-run --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --candidate-id Axio-pro --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/mmlu_pro_general_reasoning/mmlu_sample.jsonl --cache-root /mnt/storage/ASciFS/axio_benchmarks --reuse-existing --output-dir outputallresult`
   - `nice -n 10 python3 -m axio.fusion_api.cli benchmark-batch-run --suite mmlu_pro_general_reasoning --candidate-id Axio-terra --candidate-id Axio-pro --dataset /mnt/storage/ASciFS/axio_benchmarks/datasets/mmlu_pro_general_reasoning/mmlu_sample.jsonl --cache-root /mnt/storage/ASciFS/axio_benchmarks --reuse-existing --output-dir outputallresult`
   - 结果：两条入口均生成 batch report 和 Markdown。

6. 输出泄露检查：
   - 检查 readiness/batch 报告中是否包含 `2+2`、`Final answer`、`Correct Answer`、`options`、`answer`、测试 secret、`nvapi-` 等敏感或样本文本。
   - 结果：未发现真实密钥、样本题目正文或答案正文。

## 当前状态判断

Axio Fusion API 的 benchmark 闭环现在具备三层防线：

1. `run-matrix` 决定同题比较哪些候选。
2. `live-readiness` 在真实调用前检查候选是否可跑，并明确缺失的环境条件。
3. `batch-run --reuse-existing` 允许复用已有 case results，避免重复消耗模型额度。

这仍然不是 Axio-terra/pro 的真实胜利证明。当前机器没有 live provider 凭据环境，因此 readiness 正确阻塞了真实 live benchmark。

## 仍未完成的问题

1. 需要在安全的本地 shell 环境中设置 CPA Plus / NVIDIA API key 环境变量后，再跑 `benchmark-live-readiness --probe`。
2. 需要下载真实 GPQA / MMLU-Pro 数据集到 `/mnt/storage/ASciFS/axio_benchmarks`。
3. 需要用真实数据和真实 provider baselines 跑小样本 live batch，然后生成第一份真实 scorecard。
4. LiveCodeBench、BFCL、tau-bench、SWE-bench Verified 仍需官方 runner / importer 适配。

## 下一步收口范围

下一步先不要扩大到全 PRD，继续做一个小闭环：

1. 给 benchmark download/import 增加更清晰的 dataset materialization receipt：
   - 记录数据集目录、文件 hash、case count、是否含 label、是否进入 git。
   - 仍不把 benchmark payload 纳入 git。

2. 增加 `fusion-benchmark-runbook`：
   - 根据 readiness 状态、dataset 状态、run matrix 自动生成下一步命令。
   - 明确什么时候可以跑 live、什么时候只能 dry-run、什么时候需要先补 env/dataset。

3. 完成后再尝试真实小样本 live scorecard；真实 scorecard 可用后，再把 Axio Fusion 的成果反馈回 ASciFS 第一/二部分 Agent Harness 与文献基础设施。
