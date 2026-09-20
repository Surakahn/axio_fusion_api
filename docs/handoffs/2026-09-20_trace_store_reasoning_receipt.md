# Axio Fusion API 交接：trace_store 推理执行证据闭环

日期：2026-09-20

## 本轮完成

`schemas.py` 已经为每个候选的 `task_execution` 生成
`axio_fusion_api.reasoning_execution_receipt.v1`。本轮补齐了 `trace_store.py` 的独立
安全投影：

- 空 task receipt 输出固定 bounded 默认值，状态为 `not_recorded`；
- native、mapped、unverified passthrough 均保留 requested/effective effort；
- requested/effective thinking budget、API format、reasoning transport、transport
  status、mapping direction/scope 和 native 验证状态均保留；
- provider/model 原文、URL、prompt、API key 与其他 secret 不接受持久化；
- `CandidateResult.safe_dict()` 产生的 receipt 与最终 `safe_execution_trace()` 投影
  使用同一安全语义，避免内存中有证据、落盘后丢字段。

## 验证

- L1：`py_compile` 通过；
- L2：`PYTHONPATH=src` 导入通过；
- L3：`tests/test_trace_store_reasoning_receipt.py` 与
  `tests/test_reasoning_transport.py` 共 `37 passed`；
- 融合核心、公共模型契约与 Hermes 回归共 `129 passed`；
- `git diff --check` 通过；
- 未执行 provider/target 网络请求，未修改 CPA Plus 8317，未改变 r18 frozen 输入。

## 尚未完成

该改动只闭合执行证据的安全观测链路，不证明上游 provider 原生支持任何 reasoning
effort。仍需在 operator 授权的 endpoint-bound probe 中验证 native effort/budget，
并在完整 21-suite、四协议、同 case paired campaign 中收集质量、attempted provider
calls、失败/重试、Judge/Synthesizer 调用和 p50/p95 延迟，之后才能进行成本优势或
superiority claim 审批。

## 下一步

1. 完成真实 endpoint-bound reasoning probe 的严格 admission 与 hash-safe artifact；
2. 恢复/执行官方 harness 的 21-suite paired campaign，保留中断恢复完整性证据；
3. 运行四协议 parity、Holm correction、effect size 与 contamination audit；
4. 通过 final audit 后再更新三模型的生产能力与相对调用成本结论。

