# 流式客户端断开与租户资源释放交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 产品本体的商业级运行时闭环。上一轮已实现租户级 in-flight
admission，但缺少真实 HTTP 客户端断开后的端到端证据；本轮补齐该证据，不执行 provider
screening、target benchmark，也不修改 r18 frozen plan/source/registry。

## 实现与验证

- 新增 `tests/test_true_incremental_streaming.py` 的端到端回归：客户端在收到首个公开
  SSE delta 后断开，fake provider 观察到 cancellation，第二个 delta 不再发送给客户端。
- 断开后 handler 的 `finally` 必须释放租户 in-flight lease；测试以有界等待确认
  `in_flight_tenant_count` 最终归零，防止真实生产连接断开造成租户槽位泄漏。
- 流式专项：`23 passed`；当时全量回归：`1123 passed`；随后四协议错误码增量完成综合
  全量回归 `1127 passed`。
- L1：`python3.11 -m compileall -q src scripts tests` 通过。
- L2：关键导入通过；`git diff --check` 通过。
- 本轮仅新增测试与证据文档，不改变 serving registry、router、prompt、weights 或
  provider admission policy。

## 当前发布边界

本轮没有生产代码行为变更，因此当时不需要重启 Axio 18900；随后错误码契约发布使用同一
受控服务流程，当前 PID 已更新为 `2420815`，health/runtime 与三档 dry-run 均通过。
没有停止或重启 CPA Plus，没有执行 provider screening、target benchmark 或任何新的
provider 网络请求。

## 下一步

继续审计公共多协议错误一致性、预算/并发/速率组合边界和 stream/image 资源释放；外部
凭据轮换完成后仍严格回到：credential-ready preflight -> 唯一 r18 screening -> transport
admission -> ranking -> baseline freeze -> Harness/import/convergence -> 21-suite campaign。

本轮证据只证明流式资源生命周期安全，不证明 provider 能力、排名、成本、延迟或
superiority。
