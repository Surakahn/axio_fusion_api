# Composite r4 Live Screening 里程碑（2026-08-17）

## 目的与边界

r4 是 r3 transport admission blocked 后创建的独立 immutable successor cohort。它
重新使用同一组已验证的 probe-bound registry 输入，但拥有独立的 source manifest、
screening plan、campaign root 和下游收敛 receipt。r3 的 frozen plan、completed
subset、ranking 和 baseline freeze 没有被修改或混入。

本阶段只执行 non-target screening。screening、supervisor 和离线 convergence
watcher 均禁止启动 target-suite 请求；任何 transport failure 只能用于 admission
门禁，不能转化为能力排名或 superiority evidence。

## 固定输入

- canonical groups：4
- serial units：8
- 预计 provider calls：856
- `max_workers`：1
- fail-fast transport gate：启用
- plan digest：
  `3841f86be153e42ab324f9ff7b6a4d5ec97ee714d46633beaea768bbd82a410f`
- registry digest：
  `a98ca935e3b8005b84e26cfc71feb902ad43ecbc3947a4dec6cd7670bc9c17e5`
- source manifest digest：
  `be9faf4426e1a0b376294f6066e1af96fca9491e3cd2b7e1c2979f8ff7975f6c`

zero-network preflight 已确认 `planned_task_count=8`、没有 network calls，且
`target_suite_calls_performed=false`。真实运行前没有修改 frozen plan，也没有重复
上游 provider probe。

## 运行控制面

2026-08-17 14:34（Asia/Shanghai）通过 `setsid` 启动以下三个角色：

- screening：PID `2478857`
- convergence supervisor：PID `2480660`
- hash-only binding/audit watcher：PID `2486660`

supervisor 只观察 screening 的 PID 与 plan identity，在 terminal 后按顺序执行
transport admission 和 screening-to-ranking；watcher 每 300 秒原子重建 cohort
binding 并刷新 convergence audit。两者都不会恢复失败 unit、修改 plan 或启动
target Harness。

## 首个运行快照

记录时 screening 仍为 `running`：8 个 unit 中 1 个已完成、3 个失败或阻塞，其他
unit 尚未终态；`target_suite_calls_performed=false`、`ready_for_ranking=false`。
监督器和 watcher 均存活，收敛审计为 `status=running`、`next_gate=screening`、
`target_suite_calls_allowed=false`。transport、ranking 和 provider freeze 文件在
screening terminal 前仅为 fail-closed 占位 receipt，不能作为 ready 证据。

安全产物只保留 schema、状态、计数、digest 和 reason code。checkpoint 中可能含有
provider 原始内容的私有文件不纳入文档、日志或公共 evidence pack。

## 后续晋级条件

1. 等待 r4 screening 自然进入 terminal，不重启或终止现有进程。
2. 仅当完整 unit set 满足固定最低 3 个 canonical model 且 transport receipt 为
   `ready` 时，才允许 supervisor 生成 external ranking。
3. ranking、独立外部证据和 provider baseline freeze 必须绑定 r4 的 registry、
   plan、transport receipt 与 source manifest；任何缺失或 digest 漂移都保持
   blocked。
4. 重新生成同 cohort Harness pin、official import audit、lineage binding，直到
   convergence audit 明确返回 `ready_for_target_campaign`，之前不得产生 target
   请求或 superiority claim。

