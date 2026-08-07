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
- [ ] `model_count` 符合预期（当前 29，不含辅助模型）
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
- **TokenAPIs → CPA** (responses)：`https://cpa.co6.click/v1`，1 个 API key
- 注册表路径：`AXIO_FUSION_REGISTRY_PATH=private/current_channel_enrollment_20260728_combined_r1/runtime_registry.calibrated.private.json`

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
