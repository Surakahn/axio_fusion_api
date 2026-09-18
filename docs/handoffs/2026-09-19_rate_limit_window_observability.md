# rate-limit 窗口恢复可观测性交接（2026-09-19）

## 本轮目标

继续补齐商业级 admission/observability 闭环。错误响应已经提供 `Retry-After`，但
`/health.runtime.rate_limit_buckets` 只有计数、上限和剩余额度，运维无法从快照判断租户
何时恢复。本轮增加 hash-safe 的窗口恢复提示，不改变限流算法、计数窗口或 provider 行为。

## 实现

- 每个 active rate bucket 新增 `retry_after_seconds`。
- 未达到限额或限流关闭时为 `0`。
- 已达到限额时依据最早窗口时间戳计算下一次可恢复时间，并与错误响应使用同一 60 秒
  窗口语义。
- 快照仍只保存租户 SHA-256、计数和固定安全布尔值，不保存 raw tenant/API key。

## 验证

- L1：修改后的 runtime 与 standalone 测试 `py_compile` 通过。
- L2：关键 runtime/server 导入通过。
- 专项预算/限流/并发回归：`9 passed`。
- 全量回归：`1133 passed`；`git diff --check` 通过。
- 未执行 provider/target 网络请求，未修改 r18 frozen plan/source/registry。

## 发布后状态

代码提交 `1de8fbf` 已推送；已保留回滚副本
`private/axio_server.18900.console.log.pre-1de8fbf`，并以 `setsid/nohup` 受控重启 Axio
18900，当前 PID 为 `2627249`。发布后 `/health=ready`、`runtime_routing=healthy`、
`21/21` runtime eligible、`0` circuit、`21/15` physical/logical、`4` providers、
`auto -> proxy`；Fast/Terra/Pro route-plan 分别为 `fast_direct_cascade`、`terra_direct`、
`pro_panel_judge_escalation`，Pro 保留 Judge/Synthesizer。CPA Plus 未停止、未重启、未修改。
