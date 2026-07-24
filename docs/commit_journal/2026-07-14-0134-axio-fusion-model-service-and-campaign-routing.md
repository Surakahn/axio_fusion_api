# 2026-07-14 01:34 Axio Fusion 模型服务与 Campaign 路由接入

## 本轮完成

1. 建立 ASciFS 的 Axio Fusion 模型服务层：
   - 新增 `axio/fabric/model_fusion.py` 和兼容入口 `axio/model_fusion.py`。
   - 对外模型族固定为 `Axio-nano`、`Axio-terra`、`Axio-pro`。
   - 明确 Axio 不是训练新模型，而是把 CPA Plus、NVIDIA NIM、Ollama 和 deterministic fallback 组织成一个非训练式模型融合/路由服务。
   - 路由因素包括任务类型、能力覆盖、强模型需求、verifier 需求、上下文窗口、速度、参考成本和 fallback 链。

2. 建立模型能力基准库：
   - 覆盖 CPA Plus Responses、NVIDIA Chat Completions、Ollama 本地模型。
   - 纳入 `gpt-oss-120b`、`step-3.7-flash`、`step-3.5-flash`、`nemotron-3-super-120b`、`llama-3.3-nemotron-super-49b`、`qwen3-next-80b-a3b`、`nemotron-mini-4b`、`deepseek-r1:7b` 等候选。
   - 区分官方/公开证据、用户经验、本地探针和假设。
   - 加入 OpenRouter API 当前公开参考价作为市场参考，但明确 `pricing_is_reference_not_gateway_bill=true`，不把它当作 CPA Plus 或 NVIDIA 当前账号的真实账单。

3. 提供 Axio 对外模型 API 服务：
   - 新增 `axio/fusion_api_server.py`。
   - 支持 `/v1/chat/completions`、`/v1/responses`、`/v1/messages` 三种协议形状。
   - 默认 dry-run，不调用外部 provider；显式 `--live` 才真实调用。
   - 支持可选 `AXIO_FUSION_API_KEYS` bearer 鉴权。
   - `/v1/models` 只暴露 `Axio-nano`、`Axio-terra`、`Axio-pro`。

4. 建立反馈闭环：
   - 新增 `build_fusion_feedback_event`。
   - 支持记录 response id、外部模型档位、内部 provider/model、rating、latency、token、参考成本。
   - 明确不保存 prompt、原论文原文或用户私有正文。
   - 明确不训练新模型权重，只更新后续 router policy 的证据。

5. 接入模块一二 Campaign / Harness：
   - `research_model_orchestration` 的每个 operation contract 增加 `axio_fusion_route`。
   - planner / synthesizer / acceptance 默认 `Axio-pro`，reader 默认 `Axio-terra`。
   - 新增 `build_axio_fusion_model_bindings_for_research_operations`，让 `--paper-reading-live-model Axio-pro` 能先展开为内部 provider/model 绑定，再交给 LiveCampaignModelRunner。
   - 保留 `n+2` 逻辑操作预算，不因为 verifier 或 binding 增加隐式 Campaign 操作数。

6. 扩展 LLM 协议兼容：
   - CPA Plus 走 Responses API。
   - NVIDIA NIM 走 Chat Completions API，支持多 key 故障切换和 `AXIO_NVIDIA_CHAT_TEMPLATE_KWARGS`。
   - Ollama 本地 `deepseek-r1:7b` 走 `/api/chat`，可用 `AXIO_OLLAMA_THINK=false` 控制短结构化输出。
   - 不修改 CPA Plus、CCX 或任何外部 Docker/本地项目代码。

7. 文档更新：
   - README 增加 Axio Fusion 快速命令和三协议说明。
   - `docs/system_requirements.md` 增加 Axio Fusion 作为 ASciFS 模型服务要求。
   - `docs/architecture/module_1_2_research_model_orchestration.md` 增加 Axio Fusion 定位、三档模型、成本参考、反馈闭环和 Campaign 接入说明。
   - `docs/ASciFS_Agent工程集成设计.md` 记录 CPA Plus、NVIDIA、Ollama 的协议边界和不落密钥原则。

## 验证结果

已运行：

```bash
nice -n 10 .venv/bin/python -m pytest -q tests/test_model_fusion.py tests/test_fusion_api_server.py tests/test_research_model_orchestration.py tests/test_paper_reading_campaign.py tests/test_llm.py
nice -n 10 .venv/bin/python -m py_compile axio/fabric/model_fusion.py axio/model_fusion.py axio/fusion_api_server.py axio/fabric/research_model_orchestration.py axio/research/paper_reading_campaign.py axio/cli.py
nice -n 10 .venv/bin/python -m axio.cli model-capabilities --output-dir /tmp/axio_fusion_smoke
nice -n 10 .venv/bin/python -m axio.cli model-route --model Axio-pro --task-type campaign_synthesizer --output-dir /tmp/axio_fusion_smoke
nice -n 10 .venv/bin/python -m axio.cli fusion-api --model Axio-nano --api-format responses --prompt ping --output-dir /tmp/axio_fusion_smoke
nice -n 10 .venv/bin/python -m axio.cli fusion-feedback --response /tmp/axio_fusion_smoke/agent_platform/fusion_api_response.json --rating 4.5 --prompt-tokens 100 --completion-tokens 20 --output-dir /tmp/axio_fusion_smoke
git diff --check
```

结果：

- 相关 pytest：`41 passed`
- py_compile：通过
- CLI smoke：通过，`Axio-nano` dry-run 内部选择 `nvidia/stepfun-ai/step-3.5-flash`
- `git diff --check`：通过
- 密钥扫描：未发现真实 API key；仅有文档占位符和已有 redaction 字符串。

## 当前边界和遗留

1. 上一轮记录的 CPA Plus 长任务 session 已无法 attach，当前没有把它当作成功证据。
2. 本轮没有修改 CPA Plus、CCX 或任何外部部署项目，只消费其对外接口约定。
3. `Axio` 当前是工程融合模型服务，不是模型训练产物。
4. 价格是参考市场价格，不是当前账号账单；后续需要真实 benchmark 与实际可用 provider 反馈不断更新 route policy。
5. 工作树里还有此前遗留的 `axio/studio_shell/studio_index.html` 和 `docs/claude_goal_handoff_ai_scientist_2026-06-29.md`，本轮不把它们作为 Fusion 提交的核心成果处理。

## 下一步

1. 把 Axio Fusion 的 route plan 和 feedback event 接入 Studio / Agent Harness 可视化，让用户看到对外 Axio 档位和内部成本/质量路由。
2. 在模块一二继续推进真实 N+2 Campaign：五用户以上 Scope 隔离、graph route reuse、paper metadata-only 存储、source reader 内存边界和 synthesis claim coverage。
3. 建立低 token live benchmark：`Axio-nano`、`Axio-terra`、`Axio-pro` 分别在澄清、reader、synthesizer、verifier 任务上测结构化输出成功率、延迟、失败率和参考成本。
4. 将 benchmark/用户反馈转成 router policy 更新，而不是训练模型权重。
5. 继续完善第一部分和第二部分基础设施，确认搜索、存储、图谱路由、上下文拼接、固定 prompt、质量门和多用户产品定位稳固后，再进入第三部分。

---

## 2026-07-14 追加：动态 Axio Fusion 三档合成收口

### 本轮用户新增要求

用户指出 Axio Fusion 不能写成固定模型名路由器，而应做到：

1. 不管提供哪些模型接口，只要是一组可用模型，Axio 都能自动合成 `Axio-nano`、`Axio-terra`、`Axio-pro` 三档。
2. Axio 对外表现为一个模型族，内部可进行模型路由、并行候选、聚合器、验证器、fallback、成本/延迟/质量平衡。
3. 任何详细实现前都要先查找最佳实践，写清架构计划并落盘，再执行。
4. Fusion 与第一、二部分要互相促进：Module 1/2 的 paper-reading、DeepResearch、图谱构建实践应反哺 prompt scaffold 和路由策略；Fusion 的 route plan 也应服务第一、二部分。

### 执行前调研和计划

新增架构计划文档：

- `docs/architecture/axio_fusion_dynamic_model_orchestration_plan.md`

计划吸收的外部最佳实践：

- OpenRouter provider/model routing：provider fallback、价格/吞吐/延迟排序、最大价格、模型路由、隐藏内部 provider。
- Sakana AI Fugu / AI Scientist：单模型接口背后进行 query-adaptive scaffold、多 Agent/多模型候选、聚合和科学工作流闭环。
- Anthropic effective agents：routing、parallelization、orchestrator-workers、evaluator-optimizer。
- OpenAI Agents SDK：handoff、guardrail、tracing，强调可审计执行轨迹。
- LangGraph workflow/agent 边界：确定性 workflow 与动态 Agent 决策混合。

### 本轮完成内容

1. 动态模型清单归一化：
   - 新增 `build_dynamic_model_capability_registry`。
   - 新增 `normalize_model_profile`。
   - 支持任意 raw model / provider catalog / Axio registry 输入。
   - 缺失能力、价格、上下文窗口、可靠性时保守推断并写入 assumptions。
   - 默认静态 CPA/NVIDIA/Ollama profiles 变成 seed，不再是唯一实现前提。

2. 三档 Axio 自动合成：
   - 新增 `synthesize_axio_tiers`。
   - `Axio-nano` 目标函数偏成本、延迟、结构化安全。
   - `Axio-terra` 目标函数平衡强度、结构化、成本、延迟、可靠性。
   - `Axio-pro` 目标函数偏推理、验证、结构化、上下文、可靠性，并惩罚过高参考成本。
   - 弱模型池仍提供三档，但标注 `capability_degraded`，避免虚假 frontier 声称。

3. Fusion prompt scaffold：
   - 新增 `build_fusion_prompt_scaffold`。
   - 明确 immutable contract、research honesty、structured output、branch instruction、aggregation contract、verification contract。
   - 为后续 Module 1/2 的 planner/reader/synthesizer/verifier prompt 编排提供统一基座。

4. 高级执行策略：
   - `campaign_synthesizer` + `Axio-pro` + hard complexity 触发 `parallel_diverse_candidates_with_aggregator`。
   - branch 候选优先多 provider / 多成本画像。
   - 新增 aggregator prompt 和 system prompt。
   - 新增 request fingerprint，不持久化 raw prompt。
   - live execution receipt 记录 branch、aggregation、latency、provider/model，但不记录密钥或原始 prompt/source text。

5. API / CLI 接入：
   - `handle_fusion_api_request(..., registry=...)` 支持动态 registry 注入。
   - `serve_fusion_api(..., registry=...)` 支持启动时固定 registry。
   - `AXIO_FUSION_MODEL_REGISTRY_PATH` 可从环境变量加载 registry。
   - CLI 增加 `--registry`：
     - `model-capabilities --registry`
     - `model-route --registry`
     - `fusion-api --registry`
     - `serve-fusion-api --registry`
   - `model-capabilities --include-default-profiles` 支持把用户清单和内置 seed 合并。

6. 测试补强：
   - 任意模型清单自动合成三档。
   - 弱模型池 pro 降级标注。
   - prompt scaffold 不持久化 raw prompt。
   - hard research task live mock 触发多分支聚合器。
   - API server registry 注入后能选择动态强模型。

### 追加验证结果

已运行：

```bash
nice -n 10 .venv/bin/python -m pytest -q tests/test_model_fusion.py tests/test_fusion_api_server.py tests/test_research_model_orchestration.py tests/test_paper_reading_campaign.py tests/test_llm.py
nice -n 10 .venv/bin/python -m py_compile axio/fabric/model_fusion.py axio/model_fusion.py axio/fusion_api_server.py axio/fabric/research_model_orchestration.py axio/research/paper_reading_campaign.py axio/cli.py
nice -n 10 .venv/bin/python -m axio.cli model-route --model Axio-pro --task-type campaign_synthesizer --output-dir outputallresult
nice -n 10 .venv/bin/python -m axio.cli fusion-api --model Axio-nano --api-format responses --prompt 'Return Axio readiness.' --output-dir outputallresult
nice -n 10 .venv/bin/python -m axio.cli model-route --model Axio-pro --task-type campaign_synthesizer --registry /tmp/axio-fusion-smoke/registry.json --output-dir /tmp/axio-fusion-smoke
git diff --check
```

结果：

- 相关 pytest：`46 passed`
- py_compile：通过
- `git diff --check`：通过
- 默认 CLI smoke：`Axio-nano` dry-run 选择 `nvidia/stepfun-ai/step-3.5-flash`
- 动态 registry smoke：`Axio-pro` 从外部清单选择 `unit/strong-120b`

### 当前边界

1. 当前完成的是非训练式 Fusion service，不是训练 Axio 权重。
2. 尚未实现 streaming。
3. 尚未把动态 registry UI 化到 Studio。
4. 子代理架构审计仍在后台运行，本轮不等待其阻塞提交；返回后若有关键问题，下一轮合并。
5. 未触碰 CPA Plus、CCX、Docker 项目或外部部署代码。

### 下一步不大的收口功能

下一步切回第一、二部分，收口一个小但关键的功能：

**把 Axio prompt scaffold 和 route plan 正式接入 Module 1/2 的 paper-reading campaign N+2 工作流。**

目标：

1. planner 第一次 Agent 操作使用 Axio-pro/terra route plan 生成“共同考察维度”和“篇间对比维度”。
2. reader 的 n 次操作使用 Axio-terra/nano 按论文类型动态选择 prompt scaffold。
3. final synthesizer 使用 Axio-pro 多分支/聚合/验证模式输出综述草稿、对比视角报告和图谱 delta。
4. 所有 prompt scaffold、route plan、execution receipt 只存 hash/metadata，不存 raw prompt 和论文全文。
5. 至少用 5 个模拟用户问题做 dry-run，检查多用户隔离和 Module 1/2 产物质量。
