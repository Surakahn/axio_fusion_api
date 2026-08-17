# Composite r3 Harness 调研与评估契约（2026-08-17）

## 结论

r3 的下一锚点已经明确为“等待 screening 终态后继续同 cohort admission/ranking”，而不是
重跑旧 cohort 或提前执行 target Harness。真实官方/审计 Harness checkout 与数据快照已在
本机找到并完成离线 pin；pin readiness 不等于 provider baseline readiness，也不等于模型
superiority。

## 调研范围与证据

本轮只检查了仓库现有控制面、六个 Harness checkout 的 Git 元数据、所需 evaluator 文件和
raw dataset 快照。保留的证据入口如下：

- r3 immutable screening plan：digest `a8400e203ca37a4eb5ddd8a0d3758dd16c4e992ffcd1ad8dc05449eb1b17e706`。
- r3 Harness pin：`harness_pin_manifest.composite.successor.safe.json`，6 suites、6 ready、0 blocked，所有路径仅以 hash receipt 表示。
- r3 convergence audit：`status=running`、`next_gate=screening`，`target_suite_calls_allowed=false`、`target_suite_calls_performed=false`。
- 六个 pinned suite：LiveCodeBench、HumanEval、BFCL V3、tau-bench、IFEval、MT-Bench。
- BFCL 使用独立 V3 checkout 绑定，并通过 `VERSION_PREFIX = "BFCL_v3"` 兼容性门禁；不能将 BFCL V3 数据交给 V4 evaluator。
- 离线 case-hash 预备已完成：六个官方 suite 的 stable-case-id 解析全部通过；显式
  MMLU-Pro replacement 资产通过既有 disjointness contract，source manifest validation
  当前为 17/21 ready。其余 GPQA 槽位和三个本地数据 suite 仍保留 blocked，不以历史结果
  或手工 alias 补齐。

本轮没有进行 provider 请求、target-suite 请求、官方输出导入或结果排名；screening 进程由
原有 supervisor/watcher 继续管理。

`official_import_audit` 已读取同一 r3 case-hash/source manifest：官方 suite 的 case-hash
binding 为 6/6，但 imported run 为 0；因此 audit 仍 blocked，不能被解释为 Harness
campaign ready。

## 架构契约

控制面采用单向、可恢复的证据链：

```text
probe-bound registry
  -> immutable non-target screening
  -> terminal transport admission
  -> complete-pool external ranking
  -> provider baseline freeze
  -> Harness pin / execution / import audit
  -> cohort binding
  -> target campaign
  -> statistics / latency / contamination / API parity / final audit
```

每个阶段只消费同一 cohort 的上游 digest；失败必须保留完整分母并创建 successor，不能修改
frozen plan、挑选 completed subset、降低 3-model minimum，或用 generic template 冒充 ready。
`prepare_composite_harness.py` 是离线 stage materializer，不是 target authorization；唯一的
授权状态仍是同 cohort convergence audit 返回 `ready_for_target_campaign`。

## 评估契约

- **对象**：`axio-fast`、`axio-terra`、`axio-pro` 与完整 live-probed provider pool 的 rank-1/2/3 单模型基线。
- **范围**：9 类 21 suites；需要官方 Harness 的 suite 必须有 pinned runner、dataset snapshot、prompt/decoding/evaluator hash 以及每个 candidate 的 safe import receipt。
- **主要指标**：按 suite 注册的 accuracy/pass@k/tool-call/instruction-following 或 pairwise judge 指标；所有分数必须来自同一 case-hash 集合。
- **辅助指标**：median/p95 latency、transport failure rate、API surface parity、污染/泄漏检查和 paired effect-size/significance。
- **公平性**：同 cohort、同 prompt/decoding protocol、完整 candidate 分母、固定 API surface；target campaign 前禁止 benchmark tuning。
- **声明门禁**：三档 claim 只有在 provider freeze、21-suite run、配对统计和不超过 3x baseline latency 门禁全部通过后才可审计为 superiority；否则只写 readiness/diagnostic/blocked。

## 下一步

1. 低频等待 r3 screening terminal；不读取 checkpoint raw 内容。
2. 由 supervisor 执行 transport admission；只有通过固定 minimum 才允许同 cohort ranking conversion。
3. ranking ready 后生成 external top-three evidence 与 provider baseline freeze，并重新运行同目录 Harness binding。
4. 完成官方 import 后运行 acquisition/import audit；只有 convergence audit 放行才启动 target campaign。

本记录是 scout 阶段的 durable framing，不替代 screening、ranking、freeze 或最终审计证据。
