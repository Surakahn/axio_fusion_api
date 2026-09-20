# 聚合决策 Receipt 与公共 Trace 投影

## 本轮目标

把 Axio Fusion 的多个最终化路径统一成一个有界、可审计的聚合决策 receipt，覆盖
provider Synthesizer、进程内 local consensus、early exit、降级最佳候选和弃答建议。
该 receipt 同时进入内部安全 trace 和四种公共协议的 `fusion_trace_summary`，便于运营、
客户端和离线评测对账，不改变三个公开模型的算法契约。

## 完成内容

- `orchestrator.py` 新增 `aggregation_decision.v1`：记录最终决策、质量目标、校准置信度、
  quality gap、Judge 就绪状态、定向修复状态、Synthesizer 调用/接受状态和 advisory
  `abstention_recommended`。
- `trace_store.py` 增加 bounded projection；只保留哈希、枚举、计数和固定 reason code，
  不保留 prompt、候选正文、provider 原始输出、provider 标识或 secret。
- `compat.py` 的公共 `fusion_trace_summary` 暴露同一 receipt 的安全子集，四种协议保持
  一致；未完成最终聚合的 tool-call turn 返回 `not_recorded`，不把中间态伪装成最终结论。
- 新增 `tests/test_aggregation_decision_receipt.py`，覆盖 synthesis 通过、质量缺口、
  degraded synthesis、无候选弃答、安全 trace 和公共 trace 隔离。

## 语义边界

`abstention_recommended` 是运营/客户端可读的 advisory 信号。本轮为了保持既有兼容性，
质量缺口存在时仍返回原有 bounded fallback 文本；该字段不会自动改写响应为错误，也不构成
质量 superiority 结论。Synthesizer 能输出不等于 quality gate 通过，receipt 会明确记录
`quality_gate_status=degraded`。

## 验证与未完成项

- Python 3.11 `py_compile` 与模块导入通过。
- 聚合、推理 receipt、Hermes MoA、compat 合同专项共 `40 passed`。
- 本轮未执行 provider、代理或 benchmark 网络请求，没有修改 r18 frozen plan/source/registry，
  没有重启生产服务，也没有发布 serving registry。
- 仍需在获授权的 endpoint-bound probe 和完整 21-suite holdout campaign 中校准质量目标、
  置信度阈值、弃答比例、调用成本和延迟；离线 fixture 不能证明 provider 能力或 superiority。

