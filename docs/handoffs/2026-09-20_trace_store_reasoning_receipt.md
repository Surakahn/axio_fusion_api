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
- 全量 Python 3.11 回归：`1203 passed in 294.14s`；
- `compileall` 与 `git diff --check` 通过；
- 提交 `3e50c7b` 已推送到 `origin/main`。

## 发布后状态

- Axio 18900 已以 `setsid/nohup` 受控恢复，当前 PID `1382464`；
- `/health` 为 `ready`，21/21 physical profiles runtime eligible，公开模型为
  `axio-luna`、`axio-terra`、`axio-sol`，网络为 `auto -> proxy`；
- 三个模型 route-plan 均生成成功：Luna `fast_direct_cascade`、Terra `terra_direct`、
  Sol 在单调用上受预算保护为 `pro_direct_with_verifier_gap`；
- CPA Plus 8317 未停止、未重启、未修改，根端点 HTTP 200；
- 四种 live API smoke 在 20 秒上游等待窗口内均未返回，服务只记录客户端超时后的
  `BrokenPipe`，进程和 health 未受影响。这是 provider/代理连通性失败，不是协议路由
  或产品开发失败，未将其计入 native reasoning 或质量证据；
- 当前唯一 Axio 回滚副本为 `private/axio_server.18900.console.log.pre-8ae4015`。

离线验证和生产发布均未改变 r18 frozen 输入；本轮 provider smoke 的受控失败仍需在
凭据、代理和上游恢复后重新执行，不能用超时结果宣称四协议 live parity。

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
