# 2026-09-20 Benchmark run 恢复完整性门禁

## 本轮完成

正式 `run_benchmark_campaign` 过去在 `resume=True` 时只读取已有 JSON、归一化 candidate
别名并直接标记 `resumed`。这会让截断的 `case_results`、旧 schema、case 集漂移或 provider
调用总数不一致的 artifact 被误当成完整 run，进而污染 scorecard 与相对调用成本比较。

本轮新增 `benchmark_run_resume_validation.v1` 校验，并同时接入正式 campaign 与
`build_benchmark_campaign_progress_plan`：

- 绑定 suite、candidate、API surface、task format 和 live/dry-run mode；
- 绑定数据集当前 case 数与 case hash 集，检测 partial、重复和 case 漂移；
- 对账 `attempted_count` 与 completed case 数；
- 对账每个 case 的 attempted provider-call receipt 与 run 总 `provider_call_count`，失败、
  重试、Judge、Synthesizer 调用不会从成本证据中消失；
- 绑定 prompt protocol/decoding config hash，并拒绝未知 schema 或 true raw persistence flag；
- 外部 harness import 继续要求其自身的官方 receipt，不能通过恢复门禁绕过 import contract。

校验失败时 progress plan 输出 `invalid`、`repair_required` 和 hash-only reason codes；正式
campaign 不复用该 artifact，而是重新生成并标记 `repaired`。缺失或损坏文件仍为 `missing`/
`invalid`，不会触发 provider 调用。安全 receipt 不保存原始数据集、prompt、标签、provider
model、provider 输出、URL、API key 或 secret。

## 验证

- `python3.11 -m py_compile src/axio_fusion_api/evaluation.py tests/test_benchmark_resume_integrity.py`
- 恢复完整性专项：`3 passed`
- paired-call scorecard、runtime campaign 与恢复专项：`13 passed`
- 既有 campaign/progress fixture：`2 passed`
- `git diff --check`：通过

本轮只使用本地 fixture，没有启动 provider/target 网络调用，没有修改 r18 frozen
screening plan/source/registry、serving registry、CPA Plus 8317 或 Axio 生产进程，也未提交
主分支。下一阶段在获得完整授权与通过所有 preflight 后，才可对 21-suite 同 case 四协议
campaign 进行真实采集；当前不能据此宣称 superiority、质量排名或成本优势。

