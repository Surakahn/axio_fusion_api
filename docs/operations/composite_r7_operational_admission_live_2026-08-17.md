# Composite r7 Operational Admission 运行态（2026-08-17）

## 当前阶段

r7 已完成 fresh enrollment、完整 pre-Fusion inventory、严格流式 probe、probe-bound
registry 和 successor source manifest 注册。当前只运行新的 non-target
`operational-admission`，用于验证长上下文、结构化输出、受限推理和长文本 transport；它
不读取 benchmark case、label 或 target prompt，也不参与质量排名。

当前活动进程绑定如下：

- registry：`private/runs/2026-08-17-composite-cohort-r7-prefusion-full/runtime_registry.probe-bound.r7.private.json`
- private receipt：`private/runs/2026-08-17-composite-cohort-r7/operational_admission.r7.private.json`
- console：`private/runs/2026-08-17-composite-cohort-r7/operational_admission.console.log`
- execution：`timeout=90`、`max_workers=1`、`repetitions=1`、失败率门槛 `0.25`、至少 `3` 个成功 workload

进程必须自然终态；不得重复启动、手工终止或修改 r7 probe-bound registry。CPA Plus
正式服务保持在线，当前阶段不需要服务重启或配置替换。

## 证据与信任边界

可信输入为 r7 probe-bound registry 与 r7 successor source manifest。admission receipt
只用于验证 exact profile identity、strict streaming evidence、90 秒延迟和固定 workload
合同。它不是 external ranking、provider baseline freeze，也不是 target Harness 授权。

private receipt 可以供后续 screening handoff 做精确 profile 绑定；公共文档和 safe receipt
只能保留状态、计数、digest、schema 与 reason code。provider 原始输出、prompt、label、URL、
model identity 和 credential 不得进入 Git 或 safe artifact。

## 终态分支

### 至少三个 formal eligible canonical models

1. 只读读取 admission safe/private 字段，校验 `status=ready`、workload contract、完整
   profile 覆盖和敏感字段均为 `false`。
2. 使用 r7 successor source manifest、r7 probe 文件和 private admission receipt 创建新的
   immutable screening plan；固定 `min_cases_per_source=100`、`max_workers=1`、fail-fast
   transport gate，并执行 zero-network preflight。
3. screening terminal 前只生成/刷新同 cohort 的 Harness scaffold；target calls、ranking、
   provider freeze、prompt tuning 和 superiority claim 继续关闭。
4. screening terminal 后按 `transport admission → external ranking → provider baseline
   freeze → official Harness import → cohort binding → convergence audit` 顺序推进。

### 少于三个 formal eligible canonical models

保留完整 admission receipt 与 reason code，新增 r7 admission terminal 记录；不创建
screening plan，不生成 ranking/freeze，不调用 target Harness。后续只能刷新 provider
transport/probe successor，不能从部分成功模型拼接分母，也不能降低固定三模型门槛。

## 收敛判定

只有同一 r7 cohort 的 screening、transport admission、external ranking、provider freeze、
official Harness pin/import、cohort binding 和 convergence audit 全部一致且 ready，才可
打开 9 类 21 套 target campaign。此前所有结果均标记为 readiness、diagnostic 或 blocked
evidence，不构成三档 Fusion 优越性声明。

