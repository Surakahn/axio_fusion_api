# 2026-07-14 15:44 Axio Fusion bootstrap 默认生成 benchmark run matrix

## 本轮目标

上一轮 bootstrap manifest 已经能汇总 provider inventory 和 capability discovery，但它只在 handoff contract 中提示后续要生成 benchmark run matrix，没有直接生成这个控制面产物。本轮补齐这个闭环：bootstrap 默认生成 prompt-free benchmark run matrix，并把摘要写入 bootstrap 总控 manifest。

## 已完成

1. bootstrap 默认生成 benchmark run matrix
   - `build_axio_fusion_bootstrap_outputs` 新增参数：
     - `write_benchmark_run_matrix`
     - `suite_ids`
     - `include_provider_baselines`
     - `max_provider_baselines`
   - 默认 `write_benchmark_run_matrix=True`。
   - 生成文件：
     - `outputallresult/agent_platform/fusion_benchmark_run_matrix.json`
     - `outputallresult/agent_platform/fusion_benchmark_run_matrix.md`
   - 这个步骤只写 manifest，不下载 benchmark 数据，不调用 provider 模型。

2. bootstrap manifest 增加 run matrix summary
   - 新增 `benchmark_run_matrix_summary`：
     - `enabled`
     - `schema`
     - `status`
     - `suite_count`
     - `run_count`
     - `candidate_counts`
     - `blockers`
     - `raw_prompt_persisted`
     - `secrets_persisted`
   - `handoff_contract.benchmark_run_matrix_generated=true/false`。
   - markdown 摘要显示 run matrix 状态和 run 数。

3. CLI 增加控制开关
   - `axio-fusion-api bootstrap --suite ...`
   - `axio-fusion-api bootstrap --no-benchmark-run-matrix`
   - `axio-fusion-api bootstrap --no-provider-baselines`
   - `axio-fusion-api bootstrap --max-provider-baselines ...`

4. 文档和测试
   - `docs/axio_fusion_api_product.md` 说明 bootstrap 默认写 run matrix，但不下载、不执行、不调用模型。
   - product boundary 测试覆盖 bootstrap parser 的 `--suite` 和默认 run matrix 行为。
   - bootstrap 端到端测试验证：
     - inventory 产物存在；
     - capability discovery 产物存在；
     - model registry 产物存在；
     - benchmark run matrix 产物存在；
     - bootstrap manifest 中包含 run matrix summary。

## 验证结果

编译：

```bash
python3 -m py_compile \
  axio/fusion_api/bootstrap.py \
  axio/fusion_api/cli.py \
  axio/fusion_api/__init__.py \
  axio/fusion_api/capability_discovery.py
```

聚焦测试：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_fusion_provider_inventory.py \
  tests/test_fusion_api_product_boundary.py \
  tests/test_fusion_capability_discovery.py
```

结果：`12 passed in 0.12s`。

真实 CLI dry-run：

```bash
AXIO_NVIDIA_API_KEYS=dummy-nvidia-key \
AXIO_NVIDIA_MODELS='gpt-oss-120b' \
nice -n 10 python3 -m axio.fusion_api.cli bootstrap \
  --provider nvidia \
  --suite gpqa_diamond_science_reasoning \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

确认结果：

- `axio_fusion_bootstrap_manifest.json` schema 正确。
- bootstrap status 为 `ready_for_benchmark_gap_closure`。
- run matrix summary：
  - status: `ready`
  - suite_count: `1`
  - run_count: `3`
  - candidate_counts: `{"axio": 2, "provider": 1}`
- run matrix schema 为 `asci_fs.axio_fusion_benchmark_run_matrix.v1`。
- 对生成物扫描 `dummy-nvidia-key`、`integrate.api.nvidia.com/v1`、`local-cpa-plus`、`nvapi-` 无命中。

Fusion 重点回归：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_architecture.py::test_repository_architecture_validation_accepts_current_layout \
  tests/test_fusion_api_server.py \
  tests/test_fusion_router_eval.py \
  tests/test_fusion_router_learning.py \
  tests/test_fusion_api_product_boundary.py \
  tests/test_fusion_provider_inventory.py \
  tests/test_fusion_capability_discovery.py \
  tests/test_model_fusion.py \
  tests/test_fusion_benchmark.py \
  tests/test_llm.py
```

结果：`110 passed in 1.10s`。

## 已知边界

- run matrix 是 benchmark 执行计划，不是 benchmark 执行结果。
- 还没有下载 benchmark 数据，也没有调用真实 provider 模型。
- Axio-terra/pro 是否优于 provider baseline 仍必须由后续 scorecard 证明。

## 下一步

1. 用真实 provider inventory 生成 bootstrap + run matrix。
2. 根据 run matrix 选择小规模 benchmark dataset receipt。
3. 执行 env-gated benchmark batch，导入 scorecard。
4. 用共同失败率和 provider baseline 对比决定 Axio-pro 是否允许 panel promotion。
