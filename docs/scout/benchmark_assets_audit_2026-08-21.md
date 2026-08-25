# 21-suite 控制面资产审计（2026-08-21）

## 审计边界

本轮只做零网络、hash-only 的 benchmark readiness 审计。审计读取安全 manifest 的
schema、计数、reason code 和 digest，不读取题目、答案、标签、prompt、provider 输出、
凭证或原始本地路径；没有发起 provider/target 请求，也没有修改 r18 frozen
plan/source/registry。该审计只回答“控制面资产是否自洽、缺口属于哪一层”，不授权
screening 或 21-suite campaign。

审计输出：

`private/runs/2026-08-21-composite-cohort-r18/benchmark_assets_readiness.r18.preflight.safe.json`

receipt SHA-256：
`6e287ce81b97a3d39e35774c8dde3133499dcd622f1c270ef4b6c5d0d397ea7e`

结果 `status=blocked`、`ready_for_21_suite_campaign=false`、
`ready_for_final_claims=false`、`network_calls_performed=false`。

## 发现

### 已自洽的控制面资产

- 21-suite dataset manifest 存在，`suite_count=21`，内容 hash 为
  `c5de4aa31b8cae32f9cbed6953801bcd485f215ddf8d65e8eac56478968ebeef`。
- 六个 official/audited harness 的 hash-only pin 为 `6/6 ready`；pin hash 为
  `7e87f3f9e5f46fbc4ca272a52f8e0da5cd3f9a780206d44ea194362055b10b3c`。
- historical execution plan 的 294 个 task 与 import template digest 自洽；这只证明
  模板结构完整，不证明已经有任何模型输出。
- r18 successor 自身的 pin/execution scaffold 也保持 ready；其 binding/convergence
  仍由上游 screening 和 freeze gate 正确阻断。

### 真实缺口

- 历史物化状态为 `14/21 ready`，7 套阻塞：GPQA Diamond 受授权门禁，另外
  LiveCodeBench、HumanEval、BFCL、tau-bench、IFEval、MT-Bench Work 需要官方或审计
  harness import。
- historical case-hash manifest 为 `20/21 ready`，唯一缺口是 GPQA；对应 source
  validation 也是 `20/21 ready`，不能把缺少授权 artifact 的 GPQA 标成 ready。
- historical official import audit 为 `0/6 ready`、`loaded_run_count=0`，六套均缺
  `missing_suite_runs` 与 `official_import_expected_runs_missing`。因此不能把执行计划
  或 import template 当成真实导入结果。
- r18 当前 scaffold 的 acquisition status 报告 `2` 个本地 suite ready、`126` 个
  official import 缺失。这是 screening/freeze 前的 successor 控制面快照；它不是最终
  top-three import 数，也不能从历史 294-task exhaustive 矩阵补齐。baseline freeze 后
  必须在同一 r18 lineage 重新生成 candidate/run-unit contract。
- GPQA 的正式 acquisition 仍须满足固定 revision、terms acceptance、过程内凭证和
  artifact hash 校验；没有授权时只能保持 blocked，不能使用 synthetic 或历史样本替代
  最终 GPQA 证据。

## 结论与下一步

当前 21-suite 阶段的阻塞是可定位的控制面/外部授权缺口，不是代码可以绕过的 gate：

```text
r18 live screening（需明确授权）
 -> transport admission
 -> complete-pool ranking / external top-three
 -> provider baseline freeze
 -> 以 r18 freeze digest 重建同 cohort case/source/import binding
 -> official/audited import 完整后 convergence
 -> 9 类 21 套 target campaign
```

不得复用旧 cohort 的 ranking、provider freeze、case subset 或 import receipts；不得降低
2% transport gate；不得在 freeze 前把历史 14-suite 或 20/21 hash 资产写入 serving policy。
