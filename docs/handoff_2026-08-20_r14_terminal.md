# r14 terminal 与 r15 successor 交接（2026-08-20）

## 当前真实位置

- Git 分支 `main` 与 `origin/main` 在本交接前同步，r14 证据位于
  `private/runs/2026-08-19-composite-cohort-r14/`，均为私有、不可发布 artifact。
- r14 screening 已自然终态：`status=partial`、16/16 unit terminal、10 completed、
  6 failed、`ready_for_ranking=false`。
- transport admission 为 `ready`（4 个 eligible canonical，最低门槛 3），但只证明
  transport 可用性，不证明能力质量或排名。
- ranking conversion 为 fail-closed，supervisor 为 `blocked`；没有 provider baseline
  freeze、official/audited Harness import、target benchmark call 或 superiority claim。

## 不可变证据

- r14 state SHA-256：
  `c93bf49127608543b1e65ac411468e5e58371199c2bc67583a0ffb24c7ecf4c8`
- r14 campaign digest：
  `c47b5dff5fea2730aa60da7097a3952d8043ae9560b0255f5fc785cc86a4715e`
- r14 plan SHA-256：
  `988c0d793af89b1bdf0d681c200dca297ace43e9ce3d09cbe3f3fa8ad4bdefd0`
- r14 source manifest SHA-256：
  `e1a676e3af28f48d9f5b5c374542875c5b5f773bf4053c2cf9cb68ea5e32464c`
- r14 probe-bound registry SHA-256：
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`

## 下一阶段

创建 r15 immutable successor 时仅改变 source successor 的注册日期和 selection seed，
随后重新生成 frozen plan 与 zero-network preflight。r15 live screening 只能启动一套，
绑定同一份已验证 probe-bound registry、operational admission、source contract 和新
frozen plan；不得恢复 r14 checkpoint、拼接 completed subset 或重复 provider probe。

r15 terminal 后的收敛顺序固定为：transport admission、完整候选池 ranking、独立外部
rank 1/2/3 证据、provider baseline freeze、六套 official/audited Harness import、
same-cohort binding/convergence audit、21-suite target campaign，以及 paired statistics、
latency、四协议 parity、污染审计和 final audit。任何 gate 失败都只生成诊断证据并注册
新的 successor，不能宣称 Fusion superiority。

## 质量与安全边界

本交接不改变生产路由、注册表或冻结计划；不将 benchmark 输出写入运行时学习闭环；不
持久化 API key、原始 provider URL、prompt、label 或 provider output。代码变更仍必须
通过 L1 语法、L2 导入、L3 功能/dry-run、L4 review 后再提交并推送。
