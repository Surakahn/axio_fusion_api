# Goal 状态交接：BizBench evaluator 安全与任务边界加固（2026-08-27）

## 当前 Goal 位置

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 仍为 `active`。Axio 仍是 remote-only
Fusion API，通过 prompt、路由、角色编排、Judge、Synthesizer、fallback、成本/延迟/
并发预算和可观测性提供 `axio-fast`、`axio-terra`、`axio-pro`。本轮只修改离线
BizBench audited-local evaluator，没有 provider/target 网络调用，没有修改 r18 frozen
plan/source、生产路由或 serving registry，也没有获得或假设 `r18 live screening` 授权。

## 本轮加固

- BizBench 物化器现在遍历全部 `test-*.parquet` 分片，并把分片文件名纳入 case hash，
  避免多分片 index 冲突。
- Parquet 缺失值（包括浮点 `NaN`）在 prompt/context 元数据边界归一为空字符串，
  不会把 `nan` 伪造为题目上下文。
- `SEC-NUM` 使用 `numeric_or_span`：纯数字数量按 1% 相对误差，日期、证券标题、
  带单位数量等开放词汇标签按规范化 exact span；提示词明确要求返回 quantity span。
- 程序与 FormulaEval 执行器增加静态 AST 反射/动态执行/I/O 拒绝，并通过 bwrap 隔离
  进程注入最小 builtins 白名单；候选代码不再继承完整 Python builtins。
- BizBench evaluator receipt 的配置摘要绑定 output mode 与 span 规范化规则，确保
  任务协议变化会产生新的 `evaluator_config_sha256`。

## 离线证据

- L1/L2：`py_compile`、`compileall`、关键 import 和 `git diff --check` 通过。
- BizBench 专项回归：`8 passed`。
- 全量回归（含本轮 NaN 归一化）：`1105 passed, 7 skipped`。
- 真实本地 test split：`4,673/4,673`，任务计数为 SEC-NUM 2,000、CodeFinQA 795、
  FinKnow 744、ConvFinQA 629、CodeTAT-QA 288、TAT-QA 120、FormulaEval 50、FinCode 47；
  case id 全部唯一，prompt contract 无标签泄露。
- gold 自测：FinCode `47/47`、CodeFinQA `795/795`、CodeTAT-QA `288/288`、
  FormulaEval `50/50`；SEC-NUM 为 1,977 个数字标签和 23 个开放词汇标签。

这些是 evaluator 的离线工程证据，不是 provider 能力、排序、成本、延迟或
superiority 证据。

## 下一合法主路径

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

在 operator 明确回复 `授权 r18 live screening` 前，不得启动 provider 请求、恢复
checkpoint、使用 `--retry-failed`、拼接 survivor subset、降低固定 2% transport gate
或运行 21-suite target benchmark。
