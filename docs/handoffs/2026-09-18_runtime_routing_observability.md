# 运行时渠道降级与产品闭环交接（2026-09-18）

## 本轮目标

继续推进独立、remote-only、商业级 Axio Fusion API 产品本体。provider 渠道暂时不可用
只应影响候选池和证据门，不应让产品运行时、fallback、健康观测和四协议公共合同停止
迭代。本轮不进行 provider 或 target benchmark 请求。

## 状态核对

- Goal 仍为 active；产品/PRD 仍要求 `axio-fast`、`axio-terra`、`axio-pro`、四种公共
  协议、受预算约束的路由/编排、Judge/Synthesizer、fallback、安全与可观测闭环。
- r18 frozen plan/source/registry 未修改；不恢复 checkpoint、不拼接 survivor subset、不
  降低固定 2% transport gate。
- r18 live screening 仍因历史暴露的 NVIDIA 5-key pool 尚无轮换证据而 withheld。用户已
  授权 screening，但凭据轮换仍是安全前置条件；本轮不把该条件扩张成产品停工。
- 发布前发现旧交接中的 18900 PID 已不存在且端口拒绝连接；没有活跃 screening、ranking、
  Harness 或 benchmark 进程。

## 本轮实现

新增 `FusionEngine.public_runtime_routing_snapshot()`，并在 `/health` 增加
`runtime_routing`。该投影只返回哈希安全的计数和状态：

- `healthy`：注册池存在且运行时有可用 profile；
- `degraded`：profile 被熔断或标记不可用，但产品仍保留运行时 fallback 语义；
- `blocked`：没有登记 profile，或无可用 profile 且没有熔断恢复状态。

它与 `registry_readiness` 分离，避免把“某一接入渠道不可用”误报为整个产品不可用，
同时给运维提供当前进程实际路由状态。所有 `raw_*_persisted` 与 `secrets_persisted`
安全标志均为 false。

新增 standalone 回归覆盖全部 profile 被熔断时的 `degraded` 语义、计数和敏感标识符
隔离。没有修改 router、prompt、weights、provider ranking 或 benchmark policy。

## 验证证据

- L1：`py_compile` 通过；L2：关键 orchestrator/server 导入通过；
- L3：standalone `392 passed`；全量 `1118 passed in 285.65s`；
- L4：`compileall -q src scripts`、`git diff --check` 通过，代码仅涉及产品健康投影和
  对应回归。
- 受控 Axio 18900 最终发布 PID `2250370`，日志确认加载 21 profiles、创建 Engine；
  `/health` 返回 `status=ready`、`runtime_routing.status=healthy`、21/21 runtime
  eligible、0 open circuit、4 providers、`auto -> proxy`。
- `axio-fast`、`axio-terra`、`axio-pro` 三个 `/route-plan` 离线 dry-run 通过；期间没有
  provider/target 请求，亦无 screening/benchmark 后台任务。

## 仍未完成与下一步

当前产品工程增量已提交并推送到 `main`（最终提交 `cbddb04`），但最终 Goal 仍未完成。
缺口仍按一向的单向门顺序：

```text
NVIDIA key pool 轮换
 -> credential-ready preflight/verifier
 -> 唯一 r18 live screening
 -> transport admission
 -> complete-pool ranking / external top-three
 -> provider baseline freeze
 -> same-cohort Harness/import/convergence
 -> 9 类 21 套 benchmark
 -> API parity / paired statistics / latency / cost / contamination / final audit
```

轮换之前保持 provider I/O withheld；轮换完成后不能复用旧 partial screening，也不能将本
轮健康投影或历史工程测试解释为 provider 能力、成本、延迟或 superiority 证据。下一轮
开始仍需重新阅读 Goal、PRD、PLAN、CHECKLIST、本交接和当前运行时状态。
