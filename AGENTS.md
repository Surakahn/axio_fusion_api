# Axio Fusion API — Development Standards & Testing Discipline

## 一、代码质量分层体系

本项目采用**四层代码质量门禁**，每一层都必须在提交前通过，缺一不可：

### L1: 语法正确性 (Syntax)
- **要求**：代码能通过 Python `py_compile` 编译，无 `SyntaxError`
- **验证**：`python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`
- **触发**：每次文件保存/修改后立即验证

### L2: 编译与导入正确性 (Compilation & Import)
- **要求**：整个模块包能成功导入，无 `ImportError`、循环导入、缺失依赖
- **验证**：`python3 -c "from axio_fusion_api.<module> import <key_symbols>"`
- **触发**：每次修改模块依赖或新增 import 后

### L3: 功能正确性 (Functional Correctness)
- **要求**：核心功能的端到端测试通过，包括：
  - Dry-run 路由计划生成（`engine.complete(req, live=False)`）
  - Route plan 角色分配正确性验证
  - 模型筛选逻辑验证（辅助模型正确排除、能力分正确计算）
  - API 格式兼容性验证（chat/completions、responses、anthropic、gemini）
- **验证**：通过专用测试脚本或 pytest 断言
- **触发**：每次修改路由、编排、注册表逻辑后

### L4: 语义与生产级质量标准 (Semantic & Production-Grade Quality)
- **要求**：代码满足以下全部条件：
  1. **单一职责**：每个函数只做一件事，函数体不超过 80 行（复杂编排除外）
  2. **命名规范**：函数/变量名自解释，不使用缩写（除业界通用如 `req`/`resp`/`ctx`）
  3. **错误处理**：所有外部调用（网络、文件 I/O、provider 调用）有明确的异常处理路径
  4. **类型安全**：关键函数有类型注解，公共接口使用 `Mapping[str, Any]` 而非裸 `dict`
  5. **无死代码**：无注释掉的代码块、无 `pass` 占位、无未使用的 import
  6. **无硬编码**：配置值、阈值、超时时间通过常量或环境变量注入
  7. **安全性**：API key、密码、token 绝不硬编码，不写入日志/trace/receipt
  8. **幂等性**：核心函数重复调用产生一致结果
  9. **可观测性**：关键路径有结构化 trace/receipt 输出（已通过 `safe_dict()` 实现）
  10. **优雅降级**：provider 不可用时能 fallback 到替代模型，而不是崩溃
- **验证**：人工 review + 专项测试

---

## 二、测试分层策略

| 层级 | 测试类型 | 覆盖范围 | 执行频率 | 工具/方法 |
|------|---------|---------|---------|----------|
| L1 | 语法检查 | 每个 .py 文件 | 每次保存 | `py_compile` |
| L2 | 导入检查 | 整个模块 | 每次修改 import | `python -c "import ..."` |
| L3a | 单元/集成测试 | 路由、编排、注册表 | 每次修改核心逻辑 | `pytest` / 专用脚本 |
| L3b | Dry-run 路由计划 | Route Plan 生成 | 每次修改 router | `engine.complete(live=False)` |
| L3c | Provider 连通性 | 实际 API 调用 | 每次修改 providers | 30s 超时探测 |
| L4a | 融合质量验证 | 端到端评测 | 重大版本/渠道变更 | 9大类21基准评测 |
| L4b | API 格式兼容 | 四种对外格式 | 每次修改 compat | Smoke test（每个格式1个请求） |
| L4c | 压力/边界测试 | 超时、并发、错误恢复 | 里程碑节点 | 并发请求 + 模拟故障 |

---

## 三、开发工作流与门禁

### 3.1 修改前
1. 阅读相关代码上下文（至少前后 50 行）
2. 理解现有架构模式（不引入新抽象除非必要）
3. 确认修改影响范围（grep 所有引用点）

### 3.2 修改中
1. **最小化变更**：每次只改与目标直接相关的代码
2. **保持一致性**：遵循已有命名、结构、错误处理模式
3. **不引入新依赖**：除非绝对必要且有充分理由
4. **写注释**：复杂逻辑必须有解释性注释（"为什么"，不是"做了什么"）

### 3.3 修改后 — 递进门禁
```
修改完成
  ↓
L1: 语法检查 ← 必须通过，否则回退
  ↓
L2: 导入检查 ← 必须通过，否则回退
  ↓
L3: 功能测试 ← 核心逻辑必须通过
  ↓
服务器重启 & 健康检查
  ↓
L4: 手动 review ← 检查代码质量标准
  ↓
Git commit + push
```

### 3.4 服务器重启检查清单
- [ ] `curl http://127.0.0.1:18900/health` 返回 `status: ready`
- [ ] `model_count` 与明确绑定的当前 pre-Fusion registry 一致（r43 当前为
  10 个文本 physical profiles；公开模型仍为 3 个）
- [ ] `network.mode` 正确（当前 auto）
- [ ] `network.selected_transport` 为 `proxy` 或 `direct`
- [ ] 至少一个模型的 dry-run route plan 生成成功

---

## 四、当前项目关键质量约束

### 4.1 辅助模型黑名单
以下模型**永远不能**进入融合池：
- `codex-auto-review`（内部审查工具，非通用 LLM）
- `gpt-image-1`, `gpt-image-1.5`, `gpt-image-2`（生图模型，非文本 LLM）
- 过滤位置：`registry.py:_is_auxiliary_model()` + `load_registry()`

这不表示图片能力被系统永久禁用。`gpt-image-*` 只能进入独立的
image registry，必须经过 generation/editing 的端点绑定探针和 90 秒流式
门禁；生产服务通过 `load_image_registry()` 加载已提升 registry。未提升时
图片请求必须返回 `image_capability_unavailable`，不得调用文本 Fusion 伪造
图片结果。

### 4.2 能力分注入
- GPT-5.6 系列：0.88-0.90（各维度）
- GPT-5.5 系列：0.84
- GPT-5.4 系列：0.80
- NVIDIA nemotron-3-super-120b：0.76
- 其他 NVIDIA 模型：0.35（中性默认值，表示无校准数据）
- 注入位置：`registry.py:_apply_model_name_capability_priors()`

### 4.3 路由质量约束（已修复）
- **Judge 选择**：`eligible_judge_all_profiles` 优先于 `eligible_judge_operational_unassigned_profiles`
  - 原因：避免弱模型因"未被使用"而被选为 Judge
- **Synthesizer 选择**：同理
- **延迟优化质量门禁**：替换 Judge/Synthesizer 时，替代模型能力分不得低于原模型的 97%（judge）/ 92%（synthesizer）

### 4.4 网络配置
- 模式：`auto`（检测代理监听端口，有则走代理，无则直连）
- 代理：`http://127.0.0.1:10808`
- 配置文件：`private/current_channels.env`（Git 忽略）

### 4.5 渠道配置
- **NVIDIA** (chat/completions)：`https://integrate.api.nvidia.com/v1`，5 个 API key
- **CPA Plus** (Responses/Anthropic per-model binding)：`https://cpa.co6.click/v1`，1 个 API key
- **CPA Plus image lane**：`gpt-image-2` 使用 `images_api` generation/editing
  路径；仅 verified image registry 可服务
- 生产注册表：必须显式设置 `AXIO_FUSION_REGISTRY_PATH` 指向当前通过
  pre-Fusion handoff 的私有 registry；历史 `20260728` artifact 不能作为
  默认或隐式 serving registry。

### 4.6 混合渠道协议绑定
- CPA Plus 的 `/models` 目录若返回显式 `api_format`/`protocol`，以该字段为准。
- 没有显式协议时，`claude-*`、`claude/...`、`anthropic/...` 模型使用
  Anthropic `/messages`；GPT 和中国模型继续继承 CPA Plus 的 Responses
  transport。
- 该规则只解决上游 wire protocol 选择，不是能力排序先验，也不等同于
  流式可用性；每个物理 profile 仍必须通过完整 pre-Fusion 严格流式门禁。

---

## 五、代码审查要点 (Code Review Checklist)

每个 commit 前必须确认：

### 正确性
- [ ] 路由生成的 judge/synthesizer 是能力最强的模型（不是延迟最低的）
- [ ] 没有辅助模型混入融合池
- [ ] 能力分与实际模型匹配（gpt-5.6 系列 > 0.85）
- [ ] 错误传播路径完整（provider 失败 → fallback → 最终错误信息）

### 安全性
- [ ] 无 API key 硬编码
- [ ] Trace/receipt/log 中 `secrets_persisted: false`
- [ ] `raw_provider_url_persisted: false`
- [ ] `raw_api_keys_persisted: false`

### 性能
- [ ] 无不必要的同步阻塞调用
- [ ] Provider 调用使用异步/并行（parallel wave）
- [ ] 超时设置合理（不短于 provider 实际响应时间）

### 可维护性
- [ ] 新代码遵循现有模式
- [ ] 函数签名清晰（参数不超过 5 个，或使用 keyword-only）
- [ ] 无"魔术数字"（常量已命名）
- [ ] 边界条件已处理（空列表、None 值、超时）

---

## 六、禁止事项

1. **禁止**：在未通过 L1/L2 的情况下进行 L3 测试
2. **禁止**：跳过 dry-run 直接进行 live 测试
3. **禁止**：在 .py 文件中硬编码 API key、密码、token
4. **禁止**：使用 `except:` 裸捕获（必须指定异常类型）
5. **禁止**：提交包含 `print()` 调试语句的代码
6. **禁止**：引入超过 3 个新文件而不更新项目结构文档
7. **禁止**：修改路由核心逻辑后不验证 route plan 正确性
8. **禁止**：让弱模型（能力分 < 0.85 的 gpt-5.6 替代品）担任 Judge 或 Synthesizer

---

*最后更新：2026-08-07 — 随项目演进持续更新*

---

## 七、测试执行规范 (Test Execution Discipline) — 2026-08-08 更新

### 7.1 递进门禁不可跳过
每次修改核心代码后，必须按顺序通过所有层级。任何一层失败即停止，修复后重新开始。

```
L1: 语法 → L2: 导入 → L3a: 单元测试 → L3b: Dry-run → L3c: 连通性 → L4: Review → Commit
```

### 7.2 L3 功能测试实施细则

#### L3a: 单元/集成测试
- 目标：路由逻辑、注册表加载、模型筛选、能力分计算、延迟预算
- 工具：pytest（`tests/` 目录下的专用测试）
- 最低要求：router.py、registry.py、orchestrator.py 的核心路径必须覆盖
- 执行命令：`python3 -m pytest tests/ -x -q --tb=short`

#### L3b: Dry-run Route Plan 验证
- 目标：验证三个 Axio 模型的 route plan 生成正确
- 检查项：
  - strategy 匹配（fast → direct/fast_light, terra → terra_panel, pro → pro_panel_judge_escalation）
  - Judge/Synthesizer 选择为最高能力分模型
  - 辅助模型被正确排除
  - 延迟预算在合理范围内（不超过 3x baseline p95）
- 执行命令：通过 `/route-plan` API 端点验证

#### L3c: Provider 连通性探测
- 目标：验证 provider 可正常响应流式请求
- 约束：30秒超时，必须走系统代理（如有配置）
- 检查项：HTTP 200、非空响应、stream 帧验证
- 失败处理：标记为 unavailable，不影响其他 provider

### 7.3 L4 语义与生产级质量标准（详细）

除原有 10 条标准外，新增以下检查：

11. **超时预算的合理性**：所有 `_DeadlineBudget` 超时计算必须考虑：
    - Proxy/SSL 握手时间（最少 2-3 秒）
    - Provider 实际 p95 延迟
    - Mandatory stage reservations（judge/synthesizer）
    - Panel phase 最低窗口（5000ms）
12. **Phase 生命周期完整性**：每个 phase（如 `fusion_panel`）必须：
    - 在 `configure_phase` 成功后才允许 acquire
    - `timeout_seconds` 调用必须传递正确的 `phase` 参数
    - 动态 reservation 不能挤占核心 phase 预算
13. **错误传播透明性**：provider 调用失败时，trace 必须包含：
    - 错误代码（error_code）
    - HTTP 状态码（如适用）
    - 延迟预算状态（skipped/released）
    - 不得泄露 API key 或原始 provider URL
14. **并发安全性**：`_DeadlineBudget` 的所有公共方法必须在 `self._lock` 下操作共享状态
15. **资源释放**：stage 完成后必须调用 `release_pending_stage_reservations` 归还预算
16. **图片能力隔离**：图片请求必须先命中 verified image profile，再允许
    prompt composer 和上游图片调用；generation/editing 的 multipart、响应体、
    SSE 总字节数和 base64 字段都必须经过边界校验，任何失败不得回退为文本
    Fusion 的伪图片结果。

### 7.4 修复验证模板

发现 Bug 后的修复流程：
1. **复现**：编写最小复现脚本（dry-run 或 live）
2. **根因分析**：添加 debug 日志定位精确故障点
3. **修复**：最小化代码变更
4. **验证**：
   - Dry-run 验证（L3b）
   - Live 验证（L3c，如涉及 provider 调用）
   - 回归验证（确保 axio-fast/terra/pro 全部通过）
5. **记录**：将根因和修复方案写入 commit message

---

## 八、已知问题与修复记录

### 2026-08-08: axio-pro panel phase 配置失败

**症状**：axio-pro 所有 candidate 被 `DeadlineExceeded` 跳过，`timeout_seconds` 返回 ~127ms

**根因**：`_reserve_initial_stage_failover_deadline_headroom` 添加的 dynamic failover reservations 使 `pending_stage_reservation_ms()` 膨胀，导致 `_configure_fusion_panel_phase` 计算出 `panel_phase_budget < 5000ms`（最低窗口），panel phase 未配置，experts 在 acquire 时 protected 未被清零，可用时间仅 127ms。

**修复**（commit: 待提交）：
1. 新增 `_DeadlineBudget.initial_stage_reservation_ms()` 方法，仅统计 initial mandatory reservations
2. `_configure_fusion_panel_phase` 改用 `initial_stage_reservation_ms()` 计算 control window
3. Dynamic failover headroom 不再挤占 expert panel phase 预算

**验证**：axio-pro live 请求 5.8 秒返回正确结果

---

*最后更新：2026-08-08 — 随项目演进持续更新*

---

## 九、当前里程碑状态 (2026-08-08)

### 已完成
- [x] Fusion API核心系统实现（router, orchestrator, registry, server）
- [x] axio-fast/terra/pro 三模型全部正常响应
- [x] Panel phase预算bug修复（dynamic failover挤占expert预算）
- [x] axio-fast路由权重修复（BASE_SCORE 0.35→0.55, LATENCY 0.50→0.30）
- [x] Responses API格式验证通过
- [x] Chat/Completions格式完整支持
- [x] 2个provider渠道接入（NVIDIA chat + CPA responses）
- [x] 29个模型profiles加载
- [x] 辅助模型过滤（codex-auto-review, gpt-image-*）
- [x] 网络代理配置（auto模式，10808端口）
- [x] 延迟预算guard（3.0x multiplier, operational target 2.5x）
- [x] 快速评测：axio-pro/terra/fast在科学/数学/逻辑题上正确
- [x] Git管理，已推送至 github.com:Surakahn/axio_fusion_api
- [x] 图片能力独立模块：gpt-image-2 已通过 generation/editing
  endpoint-bound 流式探针，并在 verified image registry 下完成真实服务级
  generation 与 multipart editing 验证
- [x] 图片参数兼容性：`input_fidelity` 和 `background: transparent` 现为
  profile-driven capability metadata，`gpt-image-2` 已声明 `unsupported`
- [x] 本阶段完整回归：`1005 passed, 0 failed`；18 个历史非图片失败已修复
- [x] 注册表诊断命令复用 pre-Fusion validator，r41 marker/binding mismatch
  只读输出 hash-only reason codes，不能绕过 fail-closed 加载
- [x] 生产 `scripts/run_server.py` 不再默认加载历史 registry；必须显式提供
  当前 `AXIO_FUSION_REGISTRY_PATH` 且通过 `require_prefusion=True`

### 待完成
- [ ] Anthropic和Gemini API格式的完整验证
- [ ] 综合benchmark评测（9大类20+基准）vs 单模型基线
- [ ] axio-pro输出过于冗长的问题（包含完整JSON reasoning结构）
- [ ] NVIDIA渠道模型实际能力校准（许多模型的能力分为注入prior，非实测）
- [ ] 推理强度参数(reasoning_effort)的透传支持
- [ ] 自适应渠道接入时的prompt recalibration机制

### 已知限制
1. axio-pro输出包含完整内部推理结构（JSON格式），需在compat层做后处理
2. NVIDIA渠道许多模型p95延迟=20001ms（超时标记），实际可用模型有限
3. CPA渠道通过代理访问，额外延迟~1-2秒（SSL握手）
4. Python 3.8不兼容部分测试（需3.11+）
5. 评测脚本直接HTTP调用较脆弱，建议改用FusionEngine直接调用
6. 图片参数的未知能力状态返回受控错误，不静默丢弃不兼容字段
7. r41 serving artifact 的 marker/binding 不一致使其继续 fail-closed，不用于生产
8. r26/r27 screening artifacts 均为 partial 且当前无后台进程；失败以 timeout/
   network/empty-output 为主，不恢复部分结果
9. baseline freeze 和 21-suite campaign 尚未完成，不做 superiority claim

---

*最后更新：2026-08-09 — 图片参数兼容性强化与门禁同步*
