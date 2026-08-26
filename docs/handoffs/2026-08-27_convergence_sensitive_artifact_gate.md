# Goal 状态交接：convergence artifact 敏感字段门禁（2026-08-27）

## 当前 Goal 位置

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 仍为 `active`。Axio 仍是 remote-only
Fusion API，Harness 仅负责评测、控制与证据链。本轮只加固离线 convergence audit 的
artifact 安全边界，没有 provider/target 网络调用，也没有修改 r18 frozen plan/source/
registry 或生产服务。

## 根因与修复

`audit_composite_convergence.py` 的统一 stage helper 过去只根据各阶段的 `ready` 条件
决定状态，transport/ranking 等 artifact 即使声明 `raw_provider_outputs_persisted=true`
或嵌套 `raw_prompts_persisted=true`，仍可能被标记为 ready。现在 `_artifact_stage` 对
所有 stage 递归检查敏感持久化字段；任一字段为 `true` 即返回
`raw_sensitive_fields_persisted` 并 fail-closed。缺失字段继续保持兼容，避免把历史
hash-only artifact 因字段未声明误判为失败。

## 验证证据

- 新增 transport 顶层敏感字段和 ranking 嵌套敏感字段回归。
- convergence/scaffold 专项回归：`15 passed`。
- 全量 Python 3.11 回归：`1116 passed, 0 skipped`。
- `py_compile`、关键导入、`compileall` 和 `git diff --check` 通过。
- r18 preflight 仍为 `ready_for_operator_authorization`，未产生 provider/target 请求。

本轮仅证明控制面安全不变量，不构成 provider 能力、排序、成本、延迟或 Fusion
superiority 证据。

## 下一条合法动作

在 operator 明确回复 `授权 r18 live screening` 前，继续保持 provider/target fail-closed，
不得恢复 checkpoint、使用 `--retry-failed`、拼接 survivor subset、降低固定 2% transport
gate 或运行 21-suite target benchmark。授权后仍按 screening -> transport admission ->
complete-pool ranking -> provider baseline freeze -> 同 cohort Harness convergence ->
21-suite campaign -> final audit 顺序执行。

