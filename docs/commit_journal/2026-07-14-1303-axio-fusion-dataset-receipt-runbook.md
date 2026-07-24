# 2026-07-14 13:03 Axio Fusion 基准数据凭证与运行手册闭环

## 本轮完成

1. 增加 Axio Fusion Benchmark Dataset Receipt。
   - 新增 schema：`asci_fs.axio_fusion_benchmark_dataset_receipt.v1`。
   - 新增核心函数：`build_fusion_benchmark_dataset_receipt` 和 `build_fusion_benchmark_dataset_receipt_outputs`。
   - receipt 会检查数据集是否存在、是否为文件、是否位于 benchmark cache root 下、是否为 JSONL/JSON/CSV、文件大小、文件 SHA256、可解析 raw row 数、可用 multiple-choice case 数、labeled/unlabeled case 数、limit 后 case 数和 blocker。
   - receipt 明确不写入 benchmark question、options、correct label、raw prompt、source text 或任何 provider secrets。

2. 增加 Axio Fusion Benchmark Runbook。
   - 新增 schema：`asci_fs.axio_fusion_benchmark_runbook.v1`。
   - 新增核心函数：`build_fusion_benchmark_runbook` 和 `build_fusion_benchmark_runbook_outputs`。
   - runbook 汇总 dataset receipt、run matrix、live readiness，并生成可执行的下一步命令：
     - `benchmark-download`
     - `benchmark-dataset-receipt`
     - `benchmark-run-matrix`
     - `benchmark-live-readiness`
     - dry-run `benchmark-batch-run`
     - gated live `benchmark-batch-run`
   - runbook 只有在数据集、运行矩阵、live readiness 全部 ready 时才标记 `ready_for_live_batch`；否则标记 `blocked_or_dry_run_only`，不能作为 Axio-terra/pro 超越基线的证据。

3. 完善独立商业产品入口 `axio-fusion-api`。
   - 新增 standalone CLI：`benchmark-download`。
   - 新增 standalone CLI：`benchmark-dataset-receipt`。
   - 新增 standalone CLI：`benchmark-runbook`。
   - 主项目 CLI 同步新增兼容入口：
     - `axio fusion-benchmark-dataset-receipt`
     - `axio fusion-benchmark-runbook`

4. 更新产品边界文档与 manifest。
   - `axio/fusion_api/product.py` 增加 benchmark download、dataset receipt、runbook 命令声明。
   - `docs/axio_fusion_api_product.md` 增加 benchmark-dataset-receipt 与 benchmark-runbook 的使用说明和反作弊边界。
   - 文档再次明确：Axio-terra/pro 的优势声明必须来自真实 live measured scorecard，不能来自静态 registry 或 runbook。

5. 补充回归测试。
   - Dataset receipt 解析样例数据但不泄露原始题面/选项/答案。
   - 缺失数据集会给出 blocker。
   - Dataset receipt outputs 写 JSON/Markdown。
   - Runbook 汇总 dataset/readiness blocker，并输出下一步命令。
   - Runbook outputs 写 JSON/Markdown 且不泄露原始题面。
   - 主 CLI 与 standalone CLI 解析器覆盖新增命令。
   - Product manifest 测试覆盖新增商业操作命令。

## 验证记录

1. 编译检查：
   - `nice -n 10 python3 -m py_compile axio/fabric/fusion_benchmark.py axio/cli.py axio/fusion_api/cli.py axio/fusion_api/product.py tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：通过。

2. Focused pytest：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_benchmark.py tests/test_cli.py tests/test_fusion_api_product_boundary.py`
   - 结果：`57 passed in 36.43s`。

3. Fusion API 相关完整回归：
   - `nice -n 10 python3 -m pytest -q tests/test_fusion_api_server.py tests/test_fusion_api_product_boundary.py tests/test_fusion_benchmark.py tests/test_cli.py`
   - 结果：`80 passed in 36.75s`。

4. 真实 CLI dry-run 验证：
   - `nice -n 10 python3 -m axio fusion-benchmark-dataset-receipt ...`
   - `nice -n 10 python3 -m axio fusion-benchmark-runbook ...`
   - `nice -n 10 python3 -m axio.fusion_api.cli benchmark-dataset-receipt ...`
   - `nice -n 10 python3 -m axio.fusion_api.cli benchmark-runbook ...`
   - `nice -n 10 python3 -m axio.fusion_api.cli benchmark-download ... --no-symlink`
   - `nice -n 10 python3 -m axio.fusion_api.cli product-manifest ...`
   - 结果：均能正常生成 outputallresult 下的 JSON/Markdown 产物。

5. 泄露扫描：
   - 对 `fusion_benchmark_dataset_receipt.json/.md` 与 `fusion_benchmark_runbook.json/.md` 扫描样例题面、样例选项、样例答案和 `nvapi-` 片段。
   - 结果：未命中。

## 当前状态

- Axio Fusion API 已经具备独立商业项目产品边界：
  - 独立 console script：`axio-fusion-api`。
  - 兼容 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages。
  - 对外暴露 Axio-nano、Axio-terra、Axio-pro。
  - 有生产 readiness、health/smoke、run matrix、live readiness、dataset receipt、runbook、batch benchmark 和 scorecard 控制面。
- 当前不能宣称 Axio-terra/pro 已经超过 CPA Plus/NVIDIA 中最佳模型，因为本机本轮没有配置 live provider 环境变量，也没有运行真实 live measured scorecard。
- 本轮生成的 runbook 当前状态是 `blocked_or_dry_run_only`，主要 blocker 来自 live readiness 缺少 provider credentials；dataset receipt 和 run matrix 本身已 ready。

## 遇到的问题

1. 本机当前 shell 未提供 live provider 环境变量，因此只能完成静态 readiness 和 dry-run 产物验证。
2. 真实 benchmark 数据集的大规模下载/官方 runner 执行还没有启动；当前只使用机械盘下已有的小样例验证链路。
3. Benchmark download 命令默认仍是 plan-only；真实下载需要显式 `--download`，这是为了避免误拉大数据、误打满磁盘或 CPU。

## 下一步

1. 在安全 shell 中配置 CPA Plus / NVIDIA provider 环境变量后，先运行：
   - `nice -n 10 axio-fusion-api benchmark-live-readiness --cache-root /mnt/storage/ASciFS/axio_benchmarks --output-dir outputallresult --probe`
2. 选择一个真实 small-to-medium benchmark slice，先生成 dataset receipt 和 runbook：
   - `nice -n 10 axio-fusion-api benchmark-dataset-receipt ...`
   - `nice -n 10 axio-fusion-api benchmark-runbook ...`
3. live readiness ready 后运行 gated live batch：
   - `AXIO_FUSION_BENCHMARK_ENABLE_LIVE=1 nice -n 10 axio-fusion-api benchmark-batch-run ... --reuse-existing --live`
4. 得到真实 measured scorecard 后，再判断 Axio-terra 是否超过第二好的单模型、Axio-pro 是否超过当前最好的单模型。
5. 如果真实 scorecard 未达目标，下一轮应优先改进 fusion routing/verifier/ensemble 策略，而不是修改 benchmark 或手工调结果。
