# Goal 状态交接：r18 operational-admission hash binding gate（2026-08-27）

## 当前 Goal 位置

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 仍为 `active`。Axio 继续保持
remote-only Fusion 产品边界，Harness 只负责安全评测、控制与证据链。本轮只加固
r18 启动前 verifier 的离线 artifact binding，没有 provider/target 网络调用，也没有
改变生产路由、serving registry 或任何 frozen screening 输入。

## 根因与修复

`verify_screening_preflight.py` 过去只比较 operational-admission 的状态和 eligible
profile 数量，没有校验文件内容 hash 是否等于 r18 frozen plan 的
`operational_admission.content_sha256`。因此 private artifact 与 safe 投影虽然都为
`ready`，错误混用时仍可能生成 ready receipt。

现在 verifier 要求：

- `operational_admission.content_sha256 == sha256(--operational-admission)`；
- 不匹配时返回 `status=blocked`、`reason_codes=["binding_mismatch"]`、退出码 `2`；
- 正确的 canonical private artifact 继续返回 `ready_for_operator_authorization`。

这保持 hash-only 和 fail-closed 语义，不把路径、provider 标识、prompt、输出或 secret
写入 receipt。

## 验证证据

- 新增 verifier 回归覆盖：正确绑定通过，内容 hash 不匹配阻断。
- verifier 专项回归：`6 passed`；全量 Python 3.11 回归：`1114 passed, 0 skipped`。
- 真实 r18 双路径复核：
  - `operational_admission.r7.private.json` -> `ready_for_operator_authorization`、
    exit `0`；
  - `operational_admission.r7.safe.json` -> `blocked/binding_mismatch`、exit `2`。
- `py_compile`、关键 import、`compileall` 和 `git diff --check` 通过。

## 当前门禁与下一步

r18 preflight 仍为 `preflight_ready`，verifier 仍要求 operator 明确授权；
`provider_calls_performed=false`、`target_suite_calls_performed=false`。在明确回复
`授权 r18 live screening` 前，不得启动 provider 请求、恢复 checkpoint、使用
`--retry-failed`、拼接 survivor subset、降低固定 2% transport gate 或运行 21-suite
target benchmark。

授权后的顺序不变：terminal screening -> transport admission -> complete-pool ranking
-> provider baseline freeze -> 同 cohort Harness imports/binding/convergence ->
9 类 21 套 benchmark -> paired/statistical/latency/cost/contamination/final audit。

