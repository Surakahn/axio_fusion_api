# Axio Fusion API 交接：四协议兼容契约增量

日期：2026-09-20

## 本轮范围

本轮只修改兼容层、HTTP server、兼容回归和项目进度文档；没有修改 router、orchestrator、
ranking，也没有改动 r18 frozen plan/source/registry。没有执行 provider 或 target 网络调用。

## 已修复边界

### Responses continuation

服务端原先可以按 `previous_response_id` 找到并合并 request-local 历史，但所有公共
Responses response object 都把 `previous_response_id` 固定返回为 `null`。这会让遵循原生
Responses 生命周期的客户端无法确认当前结果属于哪条续接链，也使 buffered 与 SSE 的
生命周期字段不一致。

现在 `_merge_responses_continuation()` 只在成功解析并取得租户隔离的 continuation 后，向
request-local metadata 写入 bounded previous response ID。兼容层统一从这个内部标记投影到：

- buffered `render_response()`；
- `IncrementalStreamRenderer` 的 `response.created`、`response.in_progress` 和失败对象；
- `render_stream_events()` 的 Responses SSE created/in-progress/completed 对象。

caller metadata 经过既有 `_public_metadata()` 过滤，不能伪造 `_axio_*` 标记；历史、prompt、
tool output 和 secret 仍不进入公共 metadata 或持久化 receipt。

### Gemini URL/body model binding

Gemini 路由之前只在 body 没有 `model` 时使用 URL 模型，因此
`/v1beta/models/axio-luna:generateContent` 搭配 body `model=axio-sol` 会错误地运行 Sol；
未知模型路径还会被 `canonical_public_model()` 的默认策略静默降级为 Terra。这违反 URL
模型是 Gemini 原生 endpoint 资源绑定的契约。

现在 `_bind_gemini_route_model()` 对 buffered 和 incremental stream preparation 共用以下门禁：

- 只接受 `/v1beta/models/`、`/v1/models/`、`/models/` 路径；
- 支持 canonical public model 与已登记的公开兼容别名；
- body 没有模型时注入 URL 的 canonical model；
- body 有模型时要求与 URL canonical model 相同；
- 未知路径/模型、URL/body mismatch 使用 bounded 400 错误码
  `gemini_model_path_invalid`、`gemini_model_unsupported`、`gemini_model_path_mismatch`。

不改变四协议内部路由算法，不向 provider 发送额外请求。

## 验证

- L1：`python3.11 -m py_compile src/axio_fusion_api/compat.py src/axio_fusion_api/server.py`
- L2：`PYTHONPATH=src python3.11` 关键导入通过。
- 兼容专项：`PYTHONPATH=src python3.11 -m pytest -q tests/test_compat_api_contracts.py tests/test_true_incremental_streaming.py tests/test_reasoning_transport.py --tb=short`，`68 passed`。
- 公共契约回归：`tests/test_public_model_contracts.py tests/test_content_contracts.py tests/test_fusion_core_regressions.py`，`132 passed`。
- standalone 关键兼容筛选：`6 passed`。
- `git diff --check` 通过。

## 风险与后续

本轮证明的是本地协议归一化、响应字段和错误门禁，不证明任何 provider 的 live transport、
native reasoning、质量、延迟或调用成本。凭据/代理恢复后仍需执行四协议 endpoint-bound
live smoke、Responses continuation 跨协议 parity，以及正式 paired benchmark。

工作树可能同时包含其他 agent 的 orchestrator/trace_store/aggregation 增量；提交时必须
按文件边界审阅，不能覆盖或回退那些改动。生产发布前沿既有流程保留唯一 rollback backup，
并执行 health、三模型 route-plan、四协议 smoke 和 CPA Plus 可用性检查。

