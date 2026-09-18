# 租户级并发 admission 交接（2026-09-18）

## 本轮目标

继续推进独立、remote-only、商业级 Axio Fusion API 产品本体。发现已有每分钟速率限制
和每日成本预算，但缺少统一的租户级 in-flight admission；本轮补齐运行时资源控制，不
因 r18 provider 凭据安全门而停止产品工程迭代。本轮没有 provider 或 target benchmark
请求，也没有修改 r18 frozen plan/source/registry。

## 实现

- `RuntimeState.acquire_in_flight()` 在 `AXIO_FUSION_TENANT_MAX_IN_FLIGHT` 大于零时于
  同一锁内原子计数；默认值 `0` 保持既有行为。
- `InFlightLease.release()` 幂等，避免正常完成、异常处理和客户端断开重复归还或泄漏。
- `server.py` 在进入 provider/image 工作前统一 admission；buffered 文本、文本流、
  buffered 图片、图片流均覆盖。超限公共错误为 HTTP 429、`tenant_concurrency_exhausted`
  和受控 `Retry-After`。
- `record_runtime=False` 的协议/离线测试不消耗租户槽位；运行时快照只保留计数、上限和
  tenant SHA-256，禁止 raw tenant、API key、prompt、provider output 和 secret 持久化。

## 验证状态

- L1：`py_compile` 通过；L2：`axio_fusion_api.runtime`、`server` 导入通过。
- L3：专项并发回归 3/3 通过；standalone 全量 `395 passed`。
- L4：standalone `395 passed`、全量 `1121 passed`；`compileall`、`git diff --check`
  和关键导入均通过。受控服务发布后的 health/runtime 核对与最终 review 尚待完成。

## 当前未完成

r18 live screening 仍因历史暴露的 NVIDIA 5-key pool 没有可信轮换证据而 withheld。凭据
轮换前保持 provider I/O withheld；轮换后只能按既定顺序重新执行 credential-ready
preflight、唯一 r18 screening、transport admission、complete-pool ranking、baseline
freeze、同 cohort Harness/import/convergence、21-suite benchmark、parity/statistics 与
最终 audit。并发 admission 的工程回归不构成 provider 能力、排名、成本、延迟或
superiority 证据。

## 下一步

1. 完成全量门禁与服务只读 health 核对；如服务发布需要变更，仅做最小受控 Axio 操作，
   不重启 CPA Plus。
2. 继续从产品闭环寻找离线可验证的缺口（尤其流式生命周期、fallback 资源释放和公开
   错误契约），并保持每轮同步 Goal/PRD/PLAN/CHECKLIST/handoff。
3. 外部凭据轮换完成后，回到冻结的 r18 单向证据链，不复用历史 partial 结果。
