# Axio Fusion API 交接：缓冲响应客户端断开边界

日期：2026-09-20

## 问题与修复

本轮生产四协议 smoke 在上游等待超过客户端 20 秒窗口后，18900 日志出现
`BrokenPipeError`。进程和 health 没有受影响，但该堆栈会污染运维告警，也说明缓冲
响应路径没有复用流式断开的生命周期语义。

`server.py` 现将 `_write_buffered_response` 的状态行、headers、body 和 flush 统一放在
`BrokenPipeError`、`ConnectionResetError`、`OSError` 保护中。客户端 socket 已关闭时，
handler 只标记 `close_connection=True` 并返回；不会泄露 provider 细节，也不会改变
正常响应、错误码、路由、预算或 trace 行为。

## 验证

- L1：`py_compile` 通过；
- L3：流式/断流、runtime activation、部署契约、benchmark runtime、公共模型契约共
  `51 passed`；
- 新增 buffered boundary 回归覆盖客户端在响应写入阶段关闭连接；
- 全量 Python 3.11 回归：`1204 passed in 291.35s`；
- `compileall` 与 `git diff --check` 通过；
- 未修改 r18 frozen plan/source/registry，未启动 screening 或 target benchmark。

## 发布边界

本修复只处理本地 HTTP 客户端断开。provider/代理仍可能在当前环境超时，超时结果只能
记录为受控连通性失败；待凭据/代理/上游恢复后，需重新执行四协议 live smoke，不能
用 timeout 结果宣称 parity、native reasoning 或模型质量。

## 生产发布

- 提交 `8ae4015` 已推送到 `origin/main`；
- Axio 18900 以 `setsid/nohup` 受控恢复至 PID `1382464`；
- 发布后 `/health=ready`、21/21 runtime eligible、0 open circuits，三模型 route-plan
  和 CPA Plus 8317 根端点 HTTP 200 均通过；
- CPA Plus 未停止、未重启、未修改；
- 当前唯一 Axio 回滚副本为 `private/axio_server.18900.console.log.pre-8ae4015`，
  更旧的 `pre-3e50c7b` 已移除。
