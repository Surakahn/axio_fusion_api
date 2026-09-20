# reasoning_effort 执行证据契约交接

## 本轮完成

本轮新增 `axio_fusion_api.reasoning_execution_receipt.v1`。它把公共请求中的逻辑
`reasoning_effort`（`none/minimal/low/medium/high/xhigh/max`）及 Anthropic/Gemini
token budget 与选中 `ModelProfile` 的已声明 transport 绑定，输出以下安全字段：

- requested/effective effort 与 budget；
- provider API format 与 reasoning transport；
- transport status、是否已验证、映射方向与映射 scope；
- `native_reasoning_effort_verified` 三态（`true`、`false`、`null`）和 native budget 状态；
- `native`、`mapped`、`unverified_passthrough`、`not_forwarded` 的 wire mode。

orchestrator 在每个候选 role 生成该 receipt，写入内存中的 `task_execution`，随后由
`CandidateResult.safe_dict()` 的安全投影保留。投影只保留 bounded logical metadata，并
固定声明 provider/model 原文、URL、prompt、secret 未持久化。

## 关键语义

- `unknown` Chat/Responses profile 可以沿用已有兼容透传，但 receipt 状态为
  `unverified_effort_passthrough`，`transport_verified=false`、native effort 为 `null`。
- `candidate`、`unsupported` 或协议不匹配的 profile 不被 receipt 升级为已验证。
- 已验证的 `max -> high` 等映射会记录 `verified_effort_mapping`，native effort 为
  `false`，因此不能用于 native max benchmark claim。
- 只有 endpoint-bound probe 已把该 profile 的 native target 标记为 verified，且没有
  映射时，才会输出 `native_reasoning_effort_verified=true`。
- 已验证 Anthropic/Gemini thinking budget 使用 `native_verified`；未验证 budget 显式
  标记 `unverified_or_unsupported`，不会进入 provider payload。

## 验证与限制

`python3 -m py_compile` 通过，`tests/test_reasoning_transport.py` 为 `35 passed`，
`git diff --check` 通过。未执行 provider screening、target benchmark 网络请求，未重启
Axio/CPA 服务。本轮证明的是本地归一化、映射和安全 receipt 语义，不是任何 provider 的
live 能力、延迟、质量或 native max 证据；后续需要在明确授权的 endpoint-bound probe 和
完整 21-suite paired campaign 中填充实测证据。

## 工作区注意事项

本交接与 `schemas.py`、`orchestrator.py`、`tests/test_reasoning_transport.py` 的增量
属于本轮 reasoning effort 工作；工作区同时存在父任务的 evaluation/scorecard 增量，提交
时应按文件/功能边界审阅和分组，避免覆盖或回退其他工作。
