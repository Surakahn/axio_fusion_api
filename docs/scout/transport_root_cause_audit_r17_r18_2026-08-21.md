# r17/r18 Transport 根因审计（2026-08-21）

## 审计范围

本轮只读取 r17 safe campaign state、transport admission、r17/r18 frozen plan 的
非敏感字段、当前 provider transport/network 实现和生产 health。没有读取 raw
checkpoint、private provider output、原始 prompt、标签或密钥，没有重试 r17 case，
没有启动 r18 provider 请求。

## 事实证据

### r17 终态

- plan digest：`14f0a56ad4f22e21dacbb2209a7e3551517942eb0779dbc4158afd489f6d8c01`。
- state 为 `partial`，16/16 unit terminal，6 completed、10 failed，
  `ready_for_ranking=false`，`target_suite_calls_performed=false`。
- 每个 unit 的固定 fail-fast cutoff 为 3；失败 unit 在前三次 transport failure 后
  停止剩余 case，剩余 case 保留在完整 transport 分母中。
- 8 个 canonical 中只有 1 个同时通过两源固定 2% gate；minimum 为 3，因此
  transport admission 为 `blocked`。没有 ranking、provider baseline freeze 或
  target benchmark 结果。

### source/profile 组合分布

以下只使用 safe hash 映射到当前 r7 probe-bound registry 的公开 profile 身份；表中
的 failure rate 是 transport 失败率，不是能力分数。

| source adapter | provider/profile | unit 结果 | 主要 transport 类别 |
| --- | --- | --- | --- |
| `mmlu_pro` | CPA Plus `gpt-5.6-luna` | 0.893 失败、0.020 通过 | empty output、timeout |
| `mmlu_pro` | CPA Plus `gpt-5.5` | 0.000 通过 | 无失败 |
| `mmlu_pro` | CPA Plus `gpt-5.6-sol` | 0.009 通过 | 单次 timeout |
| `mmlu_pro` | CPA Plus `gpt-5.6-terra` | 0.000 通过 | 无失败 |
| `mmlu_pro` | Anthropic `claude-opus-4-6` | 0.000 通过 | 无失败 |
| `mmlu_pro` | Anthropic `claude-opus-4-8` | 1.000 失败 | timeout |
| `mmlu_pro` | Anthropic `claude-sonnet-5` | 0.786 失败 | timeout |
| `mmlu_pro` | NVIDIA `llama-3.1-nemotron-nano-vl-8b-v1` | 1.000 失败 | HTTP 500 |
| `livebench_official` | CPA Plus `gpt-5.6-terra` | 0.010 通过 | 单次 timeout |
| `livebench_official` | CPA Plus `gpt-5.6-luna` | 0.020 通过 | empty output、timeout |
| `livebench_official` | CPA Plus `gpt-5.6-sol` | 0.755 失败 | timeout |
| `livebench_official` | CPA Plus `gpt-5.5` | 0.853 失败 | HTTP 503、timeout |
| `livebench_official` | Anthropic `claude-opus-4-6` | 1.000 失败 | timeout |
| `livebench_official` | Anthropic `claude-opus-4-8` | 0.814 失败 | timeout |
| `livebench_official` | Anthropic `claude-sonnet-5` | 0.814 失败 | timeout |
| `livebench_official` | NVIDIA `llama-3.1-nemotron-nano-vl-8b-v1` | 1.000 失败 | HTTP 500 |

这说明失败不是全局网络断开：同一 source 下存在完整通过的 profile，同一 canonical
在两个 source 上也可能表现不同；同时 500/503、超时和 empty output 需要分开诊断。
由于 fail-fast 只观察前三次失败，任何 profile 的高 failure rate 只能作为 transport
admission evidence，不能解释成模型质量或 ranking evidence。

## 代码与运行时检查

1. source manifest 可声明 600 秒，但 `baseline_screening._safe_decoding_receipt()`
   将 `effective_timeout_seconds` 固定裁剪到 `PROVIDER_MAX_RESPONSE_SECONDS=90.0`。
2. `HTTPProviderClient.complete_turn()` 为一次逻辑 turn 建立单一 deadline；
   `_open_json_request()` 和 `_open_stream_json_request()` 又对 response socket、
   watchdog 和每帧读取应用剩余 deadline。因此 90 秒硬上限确实贯穿连接、body、
   SSE/NDJSON 读取，不能被 source 配置放大。
3. 当前 screening exception policy 是有限重试；失败 case 只有在 retryable 且仍
   有预算时才尝试其它 replica/round，不会因为错误答案重试。r17 safe telemetry
   未显示任何 recovered transport failure，说明本轮失败没有被 retry 恢复。
4. provider network policy 的实时只读结果为 `mode=auto`、`valid=true`、
   `listener_detected=true`、`selected_transport=proxy`；127.0.0.1:10808 由 xray
   监听。生产 `/health` 返回 `status=ready`、三档 public models、四种 API format。
   当前服务进程实际绑定 r7 probe-bound registry，公开 health 的 physical model
   count 为 21；本轮不切换 registry、不重启服务。

## 根因判定

当前最可信的判定是“source/profile 相关的 provider transport 不稳定 + 90 秒硬
ceiling + 固定 2% fail-fast 放大了失败可见性”，而不是一个已经定位的单一代码 bug：

- 有完整通过 unit，排除代理/服务全局不可用；
- timeout 与 HTTP 5xx/empty output 同时存在，排除单一错误类别；
- 同一 profile 在不同 source 上显著不同，提示请求负载、协议适配或 provider
  状态的交互效应；
- r17 的 partial 分母不足以区分 provider 瞬时故障、上游限流、长响应、协议/空体
  行为或 source-specific workload。

因此本轮不修改 `router.py`、Fusion prompt、capability prior、2% gate 或冻结 plan。
若要进一步区分上述假设，需要 operator 明确授权新的、独立且 immutable 的 transport
diagnostic/probe 计划；它必须保持 remote-only、同一 network policy、hash-only receipt，
并与正式 screening/target cohort 分开。

## r18 决策门

r18 当前证据仍为：2 source families、8 canonical、9 replicas、16 serial units、
`max_workers=1`、固定 2% fail-fast，zero-network preflight `preflight_ready`，
`target_suite_calls_allowed=false`。本审计只满足“可以请求 operator 决策”的条件，不等于
live screening 授权。

只有以下条件同时满足，才建议授权 r18 live screening：

- transport diagnostic 的结论和可接受的 failure classification 已写入 successor
  decision receipt；
- provider credentials、proxy/listener、registry/admission 和 plan digest 经过一次
  只读复核；
- operator 明确接受 90 秒 hard ceiling 与完整分母 fail-fast 语义；
- 仍保留“不恢复 checkpoint、不拼 survivor subset、不降低 2% gate”的约束。

在此之前，下一合法动作仍是只读复核或等待 operator 授权，而不是执行 provider call。

