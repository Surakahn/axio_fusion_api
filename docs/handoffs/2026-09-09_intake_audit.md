# Goal Intake Audit（2026-09-09）

## Intake Summary

- 启动模式：继续已有非空工作区；不从零重跑历史 cohort。
- 用户意图：持续推进完整 remote-only Axio Fusion API Goal，直到逐项证据满足产品、provider、Harness、21 套 benchmark 和最终审计要求。
- 当前推荐锚点：`r18 live screening`；但必须先收到精确 operator 授权短语 `授权 r18 live screening`。
- 当前状态：Goal 仍为 active；没有把 screening、历史 benchmark 或工程 readiness 误报为完成。

## Asset Matrix

| 领域 | 当前资产 | 信任等级 | 依据 | 缺失证明 | 推荐动作 |
| --- | --- | --- | --- | --- | --- |
| Provider baseline | r18 immutable plan/source、r7 probe-bound registry、两套 zero-network preflight、启动前 verifier | 可复用但未获 live 授权 | frozen 内容哈希稳定，verifier 为 `ready_for_operator_authorization`，没有 provider/target 调用 | 尚无 r18 terminal screening、transport admission、完整池排名和外部 top-three | 获授权后只启动唯一 r18 live screening |
| Main experiment | 当前 r18 target campaign 尚未启动 | 缺失 | strict gate 保持 `target_suite_calls_allowed=false` | 无同 cohort provider baseline 和 21-suite run | 先完成 screening → admission → ranking → freeze |
| Analysis | 2026-09-09 工程控制刷新、收敛审计加固、1117-test 回归 | trusted（仅工程范围） | 代码、编译、导入、收敛安全回归通过 | 不证明 provider 能力、成本、延迟或 superiority | 作为工程 evidence 保留，不用于 claim |
| Benchmark assets | 21 套定义；本地 materialization 14/21；6 套需 official/audited Harness，GPQA 受 gated source 约束 | reference / partial | 只读 materialization status 与 acquisition status | 缺 GPQA 授权、官方输出 receipts、同 cohort import audit | freeze 后按同 cohort 补齐 Harness/import |
| Terra route | 当前 r7 dry-run 正确 fail-closed 为 `terra_direct` | trusted diagnostic | role admission 显示 `independent_solver/judge` 容量不足；fake-provider panel 回归通过 | 新 endpoint-bound role probe 和 provider freeze 前不能晋级 | 不放宽 role gate；freeze 后生成 successor |
| Git / service | `main` 与 `origin/main` 一致；18900 PID `759644` health ready | trusted current | 工作树干净，服务 3 个公开模型、21 physical profiles、4 providers | live screening 尚未授权 | 保持服务和 serving registry 不变 |

## 可复用资产

- 工程证据：`private/runs/2026-09-09-engineering-control-refresh/` 下的 code-test、四协议 self-test、provider adapter、system readiness、live readiness 和 completion audit receipts。
- Screening 控制面：r18 plan/source/preflight/verifier；r17 partial/transport 结果只作 reference-only，不能拼接或恢复。
- Benchmark 控制面：现有 hash-only harness pin、execution plan、acquisition/materialization status；这些不等于官方 model-output import。
- 运行时：当前 r7 probe-bound serving registry；不切换到历史 artifact，不把静态 capability prior 当作 baseline 排名。

## 冲突与未知

- r18 verifier 的 `ready_for_operator_authorization` 不是 live authorization；没有精确授权前不得调用 provider。
- 当前 14/21 本地 suite ready 不能替代 GPQA 授权和 6 套 official/audited import。
- 工程 readiness 已通过，但 provider baseline、统计显著性、多重比较、污染审计和最终 claim 证据仍缺失。
- Terra 的历史“部分 panel candidate”现象当前被证实为 role-capacity gate，不是可凭静态放宽修复的 deadline bug。

## 路由建议

- 下一锚点：收到 `授权 r18 live screening` 后，重新执行一次只读 verifier，再启动唯一的 `baseline-screening-run --live`（`max_workers=1`、`setsid/nohup`）。
- 原因：r18 是当前唯一完整、不可变、hash-bound 的 provider baseline 入口；此前所有后置阶段都依赖其 terminal 结果。
- 不应重复：不重跑或修改冻结 plan，不恢复 checkpoint，不使用 `--retry-failed`，不拼接 survivor subset，不降低固定 2% transport gate，不提前运行 target benchmark。
- 仍需验证：screening terminal、transport admission（至少 3 个 canonical 且双 source 通过）、complete-pool ranking、外部 top-three、provider freeze、同 cohort Harness/import/convergence、四协议 parity、9 类 21 套 benchmark、统计/成本/延迟/污染审计和 final completion audit。
- 用户输入：需要精确 operator 授权；若先轮换已暴露的 NVIDIA key pool，则应重新生成 credential-ready preflight 并再次核对 verifier。
