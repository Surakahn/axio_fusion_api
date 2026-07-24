# Axio Fusion 动态模型编排实现计划

更新时间：2026-07-14

本文是 ASciFS 中 Axio Fusion 的执行前架构计划。后续实现必须先对照本文推进，避免把 Axio 写成固定模型名路由器。Axio 不是训练新模型，而是把任意一组可用模型接口归一化、评分、路由、并行编排和验证聚合后，对外表现为 `axio-fast`、`axio-terra`、`axio-pro` 三个模型等级。

## 1. 外部最佳实践调研结论

### 1.1 OpenRouter 路由实践

参考：
- https://openrouter.ai/docs/features/provider-routing
- https://openrouter.ai/docs/features/model-routing
- https://openrouter.ai/docs/api-reference/overview

可借鉴点：
- Provider routing 应支持显式 provider 顺序、允许/禁用 fallback、按价格/吞吐/延迟排序、最大价格、参数能力过滤、数据策略过滤。
- 默认路由不应只按质量最大化；OpenRouter 会把价格、近期可用性和 fallback 链组合起来。
- Auto Router 会基于 prompt complexity、task type、model capabilities 选模型，并把实际使用模型写入响应 metadata。
- 多模型 fallback 和 provider fallback 应分层：模型候选解决“能力选择”，provider 候选解决“同模型/同任务的可用性与成本”。
- session stickiness 对多轮 Agent 很重要：同一会话应可固定上次成功模型/提供商，提升一致性与缓存命中。

### 1.2 Sakana Fugu / AI Scientist 实践

参考：
- https://sakana.ai/fugu/
- https://arxiv.org/html/2606.21228v1
- https://sakana.ai/ai-scientist/
- https://github.com/sakanaai/ai-scientist

可借鉴点：
- Fugu 的关键不是“一个更大模型”，而是通过单一模型接口隐藏内部多 Agent、多模型协作。
- 技术报告强调 query-adaptive scaffold：根据用户请求动态决定使用哪些 worker、角色、指令、如何组合/验证中间输出、何时综合最终答案。
- Fugu 与 Fugu Ultra 的差异可以映射到 Axio 的质量-延迟分层：常规任务走低延迟编排，复杂高风险任务使用更深的多分支/验证/聚合。
- AI Scientist 的科学工作流强调 literature search、experiment planning、iteration、write-up、review feedback loop；Axio Fusion 的 pro 路由应优先服务这些高价值环节，而不是把所有请求都交给最贵模型。

### 1.3 Anthropic Agent 模式

参考：
- https://www.anthropic.com/engineering/building-effective-agents

可借鉴点：
- 简单任务优先使用明确 workflow，而不是过度自治 Agent。
- 复杂但可拆分任务使用 orchestrator-workers：中央 LLM 拆解任务、分发给 worker、再综合结果。
- 需要质量提升时使用 evaluator-optimizer：一个模型产出，另一个模型检查并给出修正信号。
- 并行化适合互相独立的候选答案、证据阅读、对比视角；不适合强依赖的串行代码修改。

### 1.4 OpenAI Agents SDK 实践

参考：
- https://openai.github.io/openai-agents-python/
- https://openai.github.io/openai-agents-python/handoffs/
- https://openai.github.io/openai-agents-python/guardrails/
- https://openai.github.io/openai-agents-python/tracing/

可借鉴点：
- 最小核心原语：Agent、handoff、guardrail、tracing。Axio 不应堆叠过多不可解释抽象。
- Handoff 适合专精能力转交；Axio 内部可以把 reader、planner、verifier、aggregator 看作逻辑角色。
- Guardrail 必须进入路由执行：输入预算、输出 schema、引用诚实性、隐私/数据策略都应可检查。
- Tracing 对生产调试必要，但 ASciFS 当前约束是不持久化 raw prompt/source text，只存 hash、路由、成本、延迟、质量事件。

### 1.5 LangGraph 工作流边界

参考：
- https://docs.langchain.com/oss/python/langgraph/workflows-agents

可借鉴点：
- Workflow 是预定义路径，Agent 是动态决策路径。Axio Fusion 应采取混合式：路由/预算/安全是确定性 workflow，复杂任务的分支角色和 prompt scaffold 可动态生成。
- 持久化、调试、部署是 Agent Harness 的核心能力；Axio 的 route plan、execution receipt、feedback event 必须可审计。

## 2. Axio Fusion 架构原则

1. 任意模型清单可用：用户只要提供一组可调用模型接口，Axio 必须归一化为 capability registry。
2. 三档永远暴露：即使模型池很弱，也必须提供 `axio-fast`、`axio-terra`、`axio-pro`，但弱池要标注 `capability_degraded`，不能伪装 frontier。
3. 静态模型库只是默认 seed：内置 CPA Plus/NVIDIA/Ollama 能力表用于开箱可用，不能成为实现前提。
4. 单模型外观，多模型内部：对外 API 始终是 Axio 模型名；内部 provider/model 进入 metadata 与审计 receipt。
5. 成本、延迟、质量共同优化：不允许“所有任务都上最强模型”；也不允许“便宜模型无验证地承担高风险综合”。
6. Prompt scaffold 是一等产物：branch、aggregator、verifier 的系统提示和上下文拼接规则必须可生成、可测试、可复用。
7. 不持久化敏感内容：路由日志和反馈事件不能保存 API key、raw prompt、raw source text、论文全文。
8. 可接入 Module 1/2：文献阅读、综述生成、图谱扩展应能调用 `axio-pro`、`axio-terra`、`axio-fast`，并复用 route plan 与 execution receipt。

## 3. 核心数据结构

### 3.1 ModelProfile

字段：
- `profile_id`
- `provider`
- `model`
- `api_mode`: `chat` / `responses` / `anthropic` / `ollama`
- `endpoint_family`
- `capabilities`
- `scores`: reasoning、structured_output、scientific_synthesis、evidence_extraction、verification、speed、cost_efficiency
- `context_window_tokens`
- `pricing.current_gateway`
- `pricing.market_reference`
- `observed_latency_ms`
- `observed_reliability`
- `recommended_roles`
- `evidence`
- `secrets_persisted=false`

缺失字段策略：
- 缺 cost：用显式 unknown，不把未知当免费。
- 缺 context：路由大上下文任务时给 warning。
- 缺 capability：按模型名和分数保守推断，写入 assumptions。
- 缺 reliability：默认中性，后续由 feedback 覆盖。

### 3.2 AxioTierSynthesis

三档目标：
- `axio-fast`: 快、便宜、schema/抽取安全；优先本地/小模型/低成本模型。
- `axio-terra`: 综合能力、成本、延迟、可靠性平衡；适合常规科研规划、阅读和草稿。
- `axio-pro`: 高推理、高综合、高验证；复杂研究报告、跨文献对比、最终 acceptance review 使用多分支/聚合/验证。

每档输出：
- `selected_profile`
- `candidate_order`
- `fallback_chain`
- `capability_degraded`
- `degradation_reason`
- `routing_contract`

## 4. 动态合成算法

### 4.1 归一化

输入可以是：
- Axio registry JSON。
- OpenAI-compatible `/models` 输出。
- 手写模型清单。
- 本地 Ollama 清单。
- CPA Plus Responses API 可用模型清单。
- 后续 benchmark feedback artifact。

处理：
1. 解析 provider/model/api_mode/base capability。
2. 合并市场参考价格和本地 gateway 价格。
3. 合并 benchmark feedback 的成功率、延迟、schema pass rate、人工评分。
4. 去重：优先 `profile_id`，其次 provider/model。
5. 生成 prompt-free capability registry artifact。

### 4.2 评分

基础分：
- `strength_score = reasoning + scientific_synthesis + verification`
- `structured_score = structured_output + schema_adherence proxy`
- `cost_score = market/local cost efficiency`
- `latency_score = speed + observed_latency`
- `reliability_score = observed success rate`
- `context_score = context window fit`

三档目标函数：
- nano: `0.35 cost + 0.30 latency + 0.20 structured + 0.10 reliability + 0.05 strength`
- terra: `0.25 strength + 0.20 structured + 0.20 cost + 0.20 latency + 0.15 reliability`
- pro: `0.42 strength + 0.22 verification + 0.16 structured + 0.10 context + 0.10 reliability - excessive_cost_penalty`

弱池降级：
- pro 的 strength 或 verification 不达阈值时仍选最佳模型，但 route plan 加 warning。
- 无 verifier 时 pro 使用 primary 自检 prompt，metadata 标注 `missing_independent_verifier`。

### 4.3 请求路由

请求级信号：
- `task_type`
- requested capabilities
- `max_input_tokens`
- response format / JSON schema / tools
- user quality model: nano/terra/pro
- session id / request fingerprint
- privacy/data policy

策略选择：
- `single_call_with_fallback`: 简单任务，nano 默认。
- `cascade_with_selective_verifier`: 中等任务，terra 默认；主模型失败或质量高风险时 verifier。
- `parallel_diverse_candidates_with_aggregator`: hard + pro，选择不同 provider/成本/能力画像的 2-3 个分支并行，再由 aggregator 综合。
- `verifier_only_guardrail`: 对已有答案做 acceptance review。

### 4.4 Prompt Scaffold

每次执行组合：
1. immutable system contract：身份、隐私、不可编造、输出契约。
2. task contract：任务类型、成功标准、schema、证据要求。
3. branch role：primary / diverse candidate / cheap extractor / strict verifier。
4. context pack：用户输入、历史、上游 artifact 摘要、不可持久化标识。
5. output contract：最终格式、引用诚实性、不确定性。
6. receipt contract：不返回给用户但进入 metadata 的执行信息。

聚合器 prompt：
- 输入候选答案摘要。
- 比较 coverage、contradiction、unsupported claims、schema fit、actionability。
- 输出最终答案，不暴露内部模型争论细节。

验证器 prompt：
- 严格 JSON。
- 检查 unsupported claims、missing evidence、schema drift、是否需要重新路由。

## 5. API 设计

必须支持：
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- `POST /v1/feedback`

动态 registry 入口：
- CLI: `--registry path`
- Server env: `AXIO_FUSION_MODEL_REGISTRY_PATH`
- Python API: `registry=...`

响应要求：
- `model` 对外只显示 Axio tier。
- metadata 包含 route plan、selected provider/model、fusion strategy、execution receipt、request fingerprint。
- 默认 dry-run；`--live` 才真实调用模型。

## 6. 边界情况

必须测试：
- 只有一个模型：三档都能返回同一最佳模型，但 terra/pro 标降级。
- 只有弱小模型：pro 不报错，但 `capability_degraded=true`。
- 缺价格：成本评分保守，不当成免费。
- 缺 context：大输入任务 warning。
- primary 失败：fallback 继续，receipt 记录失败类型，不保存 prompt。
- aggregator 失败：返回最佳 branch 输出并标注 aggregation failed。
- verifier 缺失：标注缺独立验证。
- JSON/schema 任务：过滤或惩罚结构化能力低的模型。
- Anthropic/OpenAI Responses/Chat 三种输入都能 canonicalize。
- 多用户并发：不同 request fingerprint/session id 不互相污染。

## 7. 本轮实现范围

先完成 Axio Fusion 核心，不扩散到第三部分：
1. `axio/fabric/model_fusion.py`
   - 动态 `build_dynamic_model_capability_registry`
   - `normalize_model_profile`
   - `synthesize_axio_tiers`
   - `build_fusion_prompt_scaffold`
   - 请求 fingerprint
   - aggregator/verifier prompt 与 live execution receipt
2. `axio/fusion_api_server.py`
   - 加载 `AXIO_FUSION_MODEL_REGISTRY_PATH`
   - handler 支持传入 registry
3. `axio/cli.py`
   - `model-capabilities --registry`
   - `model-route --registry`
   - `fusion-api --registry`
   - `serve-fusion-api --registry`
4. tests
   - 动态模型清单自动合成三档
   - 弱池降级
   - pro hard task 多分支策略
   - live mock aggregator 路径
   - API server registry 注入

## 8. 暂不做

- 不训练 Axio 新权重。
- 不写入任何 API key。
- 不修改 CPA Plus、CCX 或 Docker 项目。
- 不做 streaming。
- 不实现完整在线 benchmark runner，只预留 feedback schema。
- 不重构 Module 1/2 主工作流，只把 Axio Fusion 接口做成可被其调用。
