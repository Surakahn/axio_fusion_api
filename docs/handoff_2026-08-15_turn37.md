# Axio Fusion API — Handoff 2026-08-15 (Turn 37)

## 本轮结论

- 已确认当前 Codex 工具通道恢复：真实 `functions.exec_command` 可返回 `date/pwd/python3.11 --version` 输出。
- 已把工具调用正确方式、失败根因、`gpt-5.6-luna`/`gpt-5.6-terra` 关闭 `code_mode_only` 的规避要求写入根目录 `AGENTS.md` 第十章。
- 旧伪工具调用没有启动 shell；真正的 retry1 是 PID `122257`，使用 `env PYTHONPATH=src` 后正常运行。

## 当前 pre-Fusion screening 状态

- 目录：`private/runs/2026-08-14-core-cohort-final/`。
- 命令：`baseline-screening-run --live --max-workers 1 --retry-failed`。
- 进程：PID `122257` 仍在运行。
- 当前 state：`status=running`，`ready_for_ranking=false`；已观测到 retry 单元至少 `6 completed / 0 failed`，后续任务仍在写 checkpoint。
- 已知启动失误：第一次后台命令漏 `PYTHONPATH=src`，失败日志保留为 `screening_retry1.console.bad-pypath.log`；第二次启动已修正。

## 下一轮

- 按 10-20 分钟低频探针等待 PID `122257` 退出，不频繁请求。
- 若 retry1 结束且 `ready_for_ranking=true`，立即执行 `baseline-screening-to-ranking`。
- 若 retry1 仍为 partial，仅针对 transport failures 继续 retry2；不要修改冻结 plan，不使用 survivor subset。
- ranking 后进入 provider baseline freeze，再继续七类十四套正式 campaign 和 superiority claim audit。
