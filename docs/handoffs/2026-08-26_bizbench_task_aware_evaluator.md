# Goal 状态交接：BizBench 任务感知评测契约（2026-08-26）

## Goal 与边界

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 仍为 `active`。Axio 仍是
remote-only Fusion API：通过 prompt 流程、路由、角色编排、Judge、Synthesizer、
fallback、成本/延迟/并发预算和可观测性，把远程 provider 组合为
`axio-fast`、`axio-terra`、`axio-pro`。Harness 只负责评测、控制、恢复和证据链。
本交接没有 provider/target 网络调用，也没有修改 r18 frozen plan/source、生产路由、
serving registry 或授权门。

## 调查结论

对照官方 `kensho-technologies/benchmarks-pipeline`、BizBench 论文和本地 Parquet
schema，确认 test split 有 4,673 行、8 个任务族：

- `FinKnow`：多选题，gold 是 0-based 选项索引；
- `ConvFinQA`、`TAT-QA`：上下文数值抽取；`SEC-NUM` 对数字标签做数值抽取，对日期/证券标题等开放词汇标签使用原文 span；
- `FinCode`、`CodeFinQA`、`CodeTAT-QA`：程序合成，执行结果与 gold 在 1% 内即正确；
- `FormulaEval`：函数/方法体补全，官方协议为合成单元测试。

因此，原先把全套 BizBench 物化为单一 `exact_match`、且不把选项纳入 prompt 的做法
不满足公平评测契约。

## 已实施变更

`src/axio_fusion_api/evaluation.py` 新增 `bizbench_task_aware_v2`：

- 物化行绑定 `bizbench_task`、`bizbench_output_mode`、`context_type` 和稳定的
  evaluator id；reference program 与 gold 只留在 evaluator 侧；
- 任务感知 prompt：FinKnow 展示选项；上下文任务展示 context/question；程序任务
  要求单一 Python 代码块；FormulaEval 要求仅返回缺失 body；
- 评分器：选项字母/索引归一；数值按论文 1% 相对误差；SEC-NUM 开放词汇使用规范化
  exact span；程序在显式环境开关后运行无 import、无文件/网络访问的临时 Python 进程，
  静态 AST 与最小 builtins 白名单双重约束；FormulaEval 使用 3 组确定性输入
  对比 candidate/gold；
- `evaluator_config_sha256` 将 BizBench evaluator id 与容差绑定，便于 source manifest
  和 case hash 审计；该本地 evaluator 明确不标记为第三方 official Harness。

新增回归文件：`tests/test_bizbench_adapter.py`。

## 验证证据

- L1/L2：`py_compile` 与关键 import 通过；
- 真实本地数据：物化 `4,673/4,673` 行，数据验证、无重复、无标签泄露、prompt
  contract 全部通过；
- gold FormulaEval 自测 `50/50`，CodeTAT-QA 结构化索引执行通过；
- 专项回归：`7 passed`；
- 全量回归：`1104 passed, 7 skipped`；
- `git diff --check` 通过。

以上仅是离线评测工程证据，不是 provider 能力、排序、成本、延迟或 superiority 证据。

## 下一合法动作

当前 r18 仍为 `preflight_ready`、未授权 live。唯一主路径仍为：

```text
明确授权 r18 live screening
 -> terminal screening
 -> transport admission
 -> complete-pool ranking
 -> external top-three
 -> provider baseline freeze
 -> 同 cohort Harness imports/binding/convergence
 -> 9 类 21 套 benchmark
 -> paired/Holm/effect/latency/cost/contamination/final audit
```

在明确授权前不得启动 provider 请求、恢复 checkpoint、使用 `--retry-failed`、拼接
survivor subset、降低固定 2% transport gate 或提前运行 target benchmark。
