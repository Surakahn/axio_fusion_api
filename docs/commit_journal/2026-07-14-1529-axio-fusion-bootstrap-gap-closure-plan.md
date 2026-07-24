# 2026-07-14 15:29 Axio Fusion bootstrap benchmark gap closure plan

## 本轮完成

- 在 `axio/fusion_api/bootstrap.py` 的 bootstrap manifest 中新增
  `benchmark_gap_closure_plan`，把已经生成的 benchmark run matrix 转换成
  可执行的后续闭环计划。
- gap closure plan 按 suite 聚合候选模型，输出：
  - benchmark family、capability area、dataset reference。
  - Axio-terra、Axio-pro 和 provider baseline 的 candidate id 列表。
  - 机械硬盘 benchmark cache 下的数据集目录和 dataset placeholder。
  - `benchmark-dataset-receipt`、`benchmark-runbook`、
    `benchmark-batch-run` dry-run 和环境门控 live batch 命令模板。
- 明确保持控制面安全边界：bootstrap 不下载 benchmark、不调用模型、不写原题、
  不写标签、不写 prompt、不写 provider secret。
- 更新 `docs/axio_fusion_api_product.md`，把 SakanaAI Fugu、OpenRouter
  Fusion 和用户提供的中文 Fusion 分析沉淀成 Axio 的实现规则：
  对外稳定 Axio 模型面，对内按难度路由、必要时 bounded panel、judge-mediated
  synthesis、递归受控，并用 receipts/runbooks/scorecards/co-failure gate 才能
  声称 Axio-terra/pro 优于单模型 baseline。
- 更新 `tests/test_fusion_provider_inventory.py`，覆盖 bootstrap manifest 中
  closure plan 的 suite 数、候选模型、命令模板和隐私字段。

## 验证结果

- `python3 -m py_compile axio/fusion_api/bootstrap.py`：通过。
- `nice -n 10 python3 -m pytest -q tests/test_fusion_provider_inventory.py tests/test_fusion_capability_discovery.py tests/test_fusion_benchmark.py tests/test_fusion_api_product_boundary.py`：
  `38 passed in 0.27s`。
- `nice -n 10 python3 -m pytest -q tests/test_fusion_api_server.py tests/test_model_fusion.py tests/test_llm.py`：
  `64 passed in 0.29s`。
- `nice -n 10 python3 -m pytest -q tests/test_architecture.py::test_repository_architecture_validation_accepts_current_layout tests/test_fusion_router_eval.py tests/test_fusion_router_learning.py`：
  `8 passed in 0.62s`。
- dry-run bootstrap 命令通过，生成：
  - `outputallresult/fusion_api_product/provider_model_inventory.json`
  - `outputallresult/fusion_api_product/axio_fusion_capability_discovery_workflow.json`
  - `outputallresult/fusion_api_product/model_capability_registry.json`
  - `outputallresult/agent_platform/fusion_benchmark_run_matrix.json`
  - `outputallresult/fusion_api_product/axio_fusion_bootstrap_manifest.json`
- dry-run manifest 中 closure plan 状态为
  `ready_for_dataset_materialization`，suite 数为 `1`，run 数为 `3`，
  候选为 `Axio-terra`、`Axio-pro`、`provider::nvidia/gpt-oss-120b`。
- 对 dry-run 产物扫描 `dummy-nvidia-key`、`nvapi-`、NVIDIA base URL、
  local CPA Plus URL：真实产物未命中。

## 遇到的问题

- 本机未安装 `jq`，因此 manifest 摘要读取改用 Python 只读 JSON 字段；没有写入
  任何额外文件。
- 工作区仍存在非本轮改动：
  - `axio/studio_shell/studio_index.html`
  - `docs/claude_goal_handoff_ai_scientist_2026-06-29.md`
  这些文件未纳入本轮 staging。

## 下一步

- 继续把 benchmark gap closure 从“命令模板”推进到“数据集 materialization
  receipt 总控”：为每个 suite 生成 dataset receipt 检查入口和缺失数据集下载/透传
  操作清单，但仍不把原题、标签或大文件写入 git。
- 在 closure plan 上增加 per-suite readiness 聚合，使 bootstrap manifest 能直接告诉
  operator 哪些 suite 已经可 live batch，哪些仍缺 dataset 或 env gate。
- closure plan 稳定后，继续完善 Axio Fusion API 的能力图谱和路由策略，再回到
  ASciFS 第一、二部分基础设施主线。
