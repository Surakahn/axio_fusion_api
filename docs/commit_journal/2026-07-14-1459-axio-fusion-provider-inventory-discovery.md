# 2026-07-14 14:59 Axio Fusion provider inventory 安全发现链路

## 本轮目标

继续推进独立商业产品 Axio Fusion API。上一轮已经完成 capability discovery、benchmark gap plan 和 scorecard 共同失败率门控；本轮补齐前置链路：Fusion API 应能自己从已配置的 provider 环境中生成安全的 model inventory，再交给 capability discovery，而不是要求人工手写 `provider_models.json`。

## 已完成

1. 新增 `axio/fusion_api/provider_inventory.py`
   - 新 schema：`asci_fs.axio_fusion.provider_model_inventory.v1`。
   - 支持 provider：
     - `cpa-plus`
     - `nvidia`
     - `ollama`
     - generic `openai-compatible`
   - dry-run 默认只读显式模型列表环境变量：
     - `AXIO_CPA_PLUS_MODELS`
     - `AXIO_NVIDIA_MODELS`
     - `AXIO_OLLAMA_MODELS`
   - live 模式必须显式开启，才调用：
     - OpenAI-compatible `/models`
     - Ollama `/api/tags`
   - 输出只保存模型名、provider、api_mode、endpoint_family、key 数量、base_url hash 和安全策略。
   - 不保存 API key，不保存本地 base URL 原文，不保存 provider 原始响应。

2. 新增 CLI 命令
   - `axio-fusion-api provider-inventory`
   - 示例：

```bash
axio-fusion-api provider-inventory \
  --provider cpa-plus \
  --provider nvidia \
  --provider ollama \
  --output-dir outputallresult
```

3. 打通 provider inventory 到 capability discovery
   - `provider-inventory` 生成：
     - `outputallresult/fusion_api_product/provider_model_inventory.json`
     - `outputallresult/fusion_api_product/provider_model_inventory.md`
   - `capability-discovery` 可以直接读取这个 JSON：

```bash
axio-fusion-api capability-discovery \
  --inventory outputallresult/fusion_api_product/provider_model_inventory.json \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

4. 更新产品 manifest 和文档
   - `provider_inventory_command` 加入 product manifest。
   - `quality_contract` 增加：
     - `provider_inventory_precedes_capability_discovery=true`
     - `provider_inventory_does_not_persist_keys_or_raw_base_urls=true`
   - `docs/axio_fusion_api_product.md` 记录 inventory -> capability discovery -> benchmark scorecard 的链路。

5. 包级 API 导出
   - `axio.fusion_api.PROVIDER_MODEL_INVENTORY_SCHEMA`
   - `axio.fusion_api.build_provider_model_inventory`
   - `axio.fusion_api.build_provider_model_inventory_outputs`

## 验证结果

新增测试：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_fusion_provider_inventory.py \
  tests/test_fusion_api_product_boundary.py
```

结果：`8 passed in 0.10s`。

provider inventory / capability discovery / product boundary 组合测试：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_fusion_provider_inventory.py \
  tests/test_fusion_capability_discovery.py \
  tests/test_fusion_api_product_boundary.py
```

结果：`11 passed in 0.08s`。

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

结果：`109 passed in 1.08s`。

CLI dry-run 链路：

```bash
AXIO_NVIDIA_API_KEYS=dummy-nvidia-key \
AXIO_NVIDIA_MODELS='gpt-oss-120b,step-3.7-flash' \
AXIO_CPA_PLUS_BASE_URL='http://local-cpa-plus.test/v1' \
AXIO_CPA_PLUS_API_KEY='dummy-cpa-key' \
AXIO_CPA_PLUS_MODELS='gpt-5.4-pro' \
nice -n 10 python3 -m axio.fusion_api.cli provider-inventory \
  --provider nvidia \
  --provider cpa-plus \
  --output-dir outputallresult

nice -n 10 python3 -m axio.fusion_api.cli capability-discovery \
  --inventory outputallresult/fusion_api_product/provider_model_inventory.json \
  --cache-root /mnt/storage/ASciFS/axio_benchmarks \
  --output-dir outputallresult
```

生成物检查：

- `provider_model_inventory.json` schema 正确。
- inventory 生成 3 个模型。
- capability discovery 消费 inventory 后生成 3 个 normalized profiles。
- 对生成物扫描 `dummy-nvidia-key`、`dummy-cpa-key`、`local-cpa-plus.test`、`integrate.api.nvidia.com/v1` 无命中。

## 已知边界

- 本轮没有调用真实 provider；live list-models 只在测试中用 fake opener 验证解析逻辑。
- dry-run 依赖显式模型列表环境变量；如果用户没有配置 `AXIO_*_MODELS`，inventory 可能只有 provider 配置状态而没有模型。
- inventory 只证明“模型可列出/可配置”，不证明模型能力强弱。能力坐标仍需要公开 evidence、probe 或 benchmark feedback 补证据。

## 下一步

1. 用真实环境变量生成 CPA Plus / NVIDIA / Ollama inventory，但仍不把 key 或本地 URL 写入仓库。
2. 用 inventory 运行 capability discovery，生成真实的 Axio-terra/pro tier synthesis。
3. 对公开 evidence 缺失的能力轴，启动小规模 benchmark batch，导入 scorecard 的 per-case agreement 与 co-failure summary。
