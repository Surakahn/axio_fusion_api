# 2026-07-14 15:14 Axio Fusion bootstrap 一键串联 inventory 与 capability discovery

## 本轮目标

上一提交新增了 provider inventory 安全发现链路。本轮把它和 capability discovery 串成一个正式 CLI 入口，减少真实部署时的人为步骤：一条命令完成 provider inventory、能力注册表、能力图谱和 benchmark gap plan 的初始产物生成。

## 已完成

1. 新增 `axio-fusion-api bootstrap`
   - 默认不联网。
   - `--live-inventory` 显式开启后才 list provider `/models` 或 Ollama `/api/tags`。
   - `--probe` 显式开启后才进行模型输出 probe。
   - 支持参数：
     - `--provider`
     - `--cache-root`
     - `--public-evidence`
     - `--benchmark-feedback`
     - `--include-default-profiles`
     - `--timeout`

2. bootstrap 只运行一次 inventory
   - 修改 `build_provider_model_inventory_outputs`，支持传入预构建 `inventory`。
   - 避免 live 模式下重复调用 `/models`。

3. product manifest 和文档同步
   - `deployment.bootstrap_command` 加入产品 manifest。
   - `quality_contract.bootstrap_runs_inventory_and_capability_discovery_once=true`。
   - `docs/axio_fusion_api_product.md` 将 bootstrap 作为推荐入口，同时保留 expanded commands。

4. 测试覆盖
   - CLI parser 覆盖 `bootstrap`。
   - 新增端到端测试：用 dummy env 调用 `fusion_api_main(["bootstrap", ...])`，验证同时写出：
     - `provider_model_inventory.json`
     - `axio_fusion_capability_discovery_workflow.json`
     - `model_capability_registry.json`
   - 验证 dummy key 不进入输出。

## 验证结果

编译：

```bash
python3 -m py_compile \
  axio/fusion_api/provider_inventory.py \
  axio/fusion_api/cli.py \
  axio/fusion_api/product.py
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
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

输出：

- `outputallresult/fusion_api_product/provider_model_inventory.json`
- `outputallresult/fusion_api_product/provider_model_inventory.md`
- `outputallresult/fusion_api_product/axio_fusion_capability_discovery_workflow.json`
- `outputallresult/fusion_api_product/model_capability_registry.json`
- `outputallresult/fusion_api_product/model_capability_graph.json`
- `outputallresult/fusion_api_product/axio_fusion_capability_discovery_workflow.md`

扫描生成物：

- 未命中 `dummy-nvidia-key`
- 未命中 `integrate.api.nvidia.com/v1`
- 未命中 `local-cpa-plus`
- 未命中 `nvapi-`

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

结果：`110 passed in 1.15s`。

## 已知边界

- 本轮仍未使用真实 API key 进行 live inventory 或 probe。
- bootstrap 生成的是控制面和初始能力图谱，不代表 Axio-terra/pro 已经通过真实 benchmark。
- 若环境没有显式模型列表，dry-run bootstrap 可能生成空 inventory；这属于正确的显式配置门禁。

## 下一步

1. 在真实环境中设置 `AXIO_NVIDIA_MODELS`、`AXIO_CPA_PLUS_MODELS` 或使用 `--live-inventory` 生成真实 inventory。
2. 用公开证据和小规模 benchmark feedback 填充 capability coordinates。
3. 对 Axio-terra/pro 与 provider baseline 跑 scorecard，使用共同失败率门控决定是否允许 panel promotion。
