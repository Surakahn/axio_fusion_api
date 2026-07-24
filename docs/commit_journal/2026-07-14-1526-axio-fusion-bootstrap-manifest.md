# 2026-07-14 15:26 Axio Fusion bootstrap 总控 manifest

## 本轮目标

上一提交新增 `axio-fusion-api bootstrap`，但它只是输出多个 artifact 路径。为了让后续 ASciFS Harness、部署脚本或 CI 能可靠消费 bootstrap 结果，本轮将 bootstrap 提升为可审计的产品级总控 manifest。

## 已完成

1. 新增 `axio/fusion_api/bootstrap.py`
   - 新 schema：`asci_fs.axio_fusion.bootstrap_manifest.v1`。
   - 新函数：
     - `build_axio_fusion_bootstrap_outputs`
     - `build_axio_fusion_bootstrap_manifest`
     - `render_axio_fusion_bootstrap_markdown`
   - 输出：
     - `axio_fusion_bootstrap_manifest.json`
     - `axio_fusion_bootstrap_manifest.md`

2. bootstrap 总控 manifest 内容
   - inventory summary：
     - provider count
     - model count
     - provider list
     - secret persistence flag
   - capability summary：
     - registry schema
     - profile count
     - external model family
     - readiness status
     - graph nodes / edges
     - benchmark gap axis count
   - output path map：
     - provider inventory
     - capability workflow
     - model registry
     - model graph
     - bootstrap manifest
   - handoff contract：
     - `model_capability_registry.json` 可喂给 Fusion API server
     - `model_capability_registry.json` 可喂给 benchmark run matrix
     - gap plan 必须通过 benchmark batch 关闭
     - Axio panel promotion 必须等 scorecard
   - privacy：
     - 不保存 API key
     - 不保存 raw base URL
     - 不保存 provider 原始响应
     - 不保存 probe prompt
     - 不保存 benchmark questions

3. 避免重复计算
   - `build_fusion_capability_discovery_outputs` 支持传入预构建 `workflow`。
   - bootstrap 现在只生成一次 inventory、一次 capability discovery，然后复用 payload 写多份 artifact。

4. CLI 和包级 API 调整
   - `cmd_bootstrap` 改为调用 `build_axio_fusion_bootstrap_outputs`。
   - `axio.fusion_api` 导出：
     - `AXIO_FUSION_BOOTSTRAP_MANIFEST_SCHEMA`
     - `build_axio_fusion_bootstrap_outputs`

## 验证结果

编译：

```bash
python3 -m py_compile \
  axio/fusion_api/bootstrap.py \
  axio/fusion_api/capability_discovery.py \
  axio/fusion_api/cli.py \
  axio/fusion_api/__init__.py
```

聚焦测试：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_fusion_provider_inventory.py \
  tests/test_fusion_api_product_boundary.py \
  tests/test_fusion_capability_discovery.py
```

结果：`12 passed in 0.10s`。

真实 CLI dry-run：

```bash
AXIO_NVIDIA_API_KEYS=dummy-nvidia-key \
AXIO_NVIDIA_MODELS='gpt-oss-120b' \
nice -n 10 python3 -m axio.fusion_api.cli bootstrap \
  --provider nvidia \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

输出新增：

- `outputallresult/fusion_api_product/axio_fusion_bootstrap_manifest.json`
- `outputallresult/fusion_api_product/axio_fusion_bootstrap_manifest.md`

抽查：

- schema 为 `asci_fs.axio_fusion.bootstrap_manifest.v1`
- status 为 `ready_for_benchmark_gap_closure`
- inventory model count 为 `1`
- capability profile count 为 `1`
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

结果：`110 passed in 1.18s`。

## 已知边界

- bootstrap manifest 是控制面，不代表真实 benchmark 已完成。
- `ready_for_benchmark_gap_closure` 表示可以进入 benchmark gap closure，不表示 Axio-terra/pro 已经超过 provider baseline。
- 后续真实 live inventory/probe 仍必须显式开启，不默认联网。

## 下一步

1. 用真实 provider inventory 生成 bootstrap manifest。
2. 将 `model_capability_registry.json` 喂给 benchmark run matrix。
3. 用小规模 benchmark batch 填充 scorecard，依据共同失败率决定是否允许 Axio-pro panel promotion。
