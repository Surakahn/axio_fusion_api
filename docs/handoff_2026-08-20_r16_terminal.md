# r16 terminal 交接（2026-08-20）

## 终态结论

r16 的唯一 live non-target screening 已自然终态，三个托管进程均已退出，没有第二套
screening。screening receipt 与 state 均为 `status=partial`，16/16 unit terminal：
2 个 completed、14 个 failed，`ready_for_ranking=false`。safe state SHA-256 为
`c51ee8a8e39f4ac67cdf34249b30da1ed799e4dccecc49bd289314b526658f81`，screening receipt
SHA-256 为 `c5cf1b28fd37508cd6e31033dcb3d42650c24dfb452adf5f3afe5ebc924f302`，campaign
digest 为 `b63b3a231a1f51a8628ea85268cfd304f64a84c0ced416beb062ec739ab1f438`。

完整 unit 分母仍在私有 receipt 中。14 个失败 unit 的 transport 分母为：5 个
`102/102`、4 个 `112/112`、以及 `24/102`、`66/112`、`84/112`、`96/112`、`46/112`；
2 个 completed unit 均为 `102/102` 且 transport failure 为 0。失败原因是固定 2% gate
超限或无分数；这些字段只描述 transport 可用性，不能当作质量分数或能力排序。

screening 绑定没有漂移：

- frozen plan：`private/runs/2026-08-20-composite-cohort-r16/baseline_screening_plan.r16.private.json`，文件 SHA-256 `9582c0fd3045698fddca3c1358e989bbcd83fb28084f64747e3b77fb6d0a9ecd`，digest `23c1b22a1708e38579f2c8f70f82bfe36a1bb7d4bde20e9aa337e289f8e969ad`；
- source manifest：`private/runs/2026-08-20-composite-cohort-r16/source_manifest.successor.r16.private.json`，SHA-256 `cf38effec8b7420dcb2b4726e93835b99342d79164806068ab9a478068511bc4`；
- registry：r7 probe-bound registry，SHA-256 `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- network/target flags：`network_calls_performed=true`、`target_suite_calls_performed=false`。

## Transport admission

同 cohort supervisor 只读等待 screening terminal 后执行 transport admission，没有执行
ranking conversion。transport receipt
`private/runs/2026-08-20-composite-cohort-r16/transport_admission.r16.private.json`
的 SHA-256 为 `9c9bed1793081127f0af4f46f935f134ba437697c25f1ff5b08e205ba5c813d9`，状态为
`blocked`：8 个 candidate canonical 中 0 个通过 transport gate，最低要求为 3，唯一
blocker 为 `transport_admission_fewer_than_minimum_models`。它只使用 failure-rate 字段，
显式忽略 mean score、source score、labels 和 provider output。

supervisor receipt
`private/runs/2026-08-20-composite-cohort-r16/convergence_supervisor.r16.private.json`
的 SHA-256 为 `098c2255190fd126b6cfc3b3403c1fe372c90e5a0d8bee6681d53ca8b6335968`，
`status=blocked`、`transport_return_code=2`、`ranking_file_sha256=""`、
`target_benchmark_started=false`。因此没有 ranking、provider baseline freeze、官方
Harness import 或 target request；不得把任何 private checkpoint 或完成 subset 接入后续
阶段。

## 下一步唯一路径

1. 从 r16 source contract 生成新的 immutable r17 source successor，只修改注册日期和
   selection seed；不读取 r16 分数、transport receipt、checkpoint、survivor subset 或
   ranking。
2. 用 r17 source 重新生成完整 frozen plan，保持两个独立 non-target source families、
   `max_workers=1`、固定 2% fail-fast gate 和完整失败分母；完成 zero-network preflight。
3. 为 r17 离线生成 6/6 pin、execution plan、acquisition/import status、cohort binding 和
   convergence audit；在 screening 前保持 `target_suite_calls_allowed=false`。
4. 只启动一套 r17 live screening。terminal 后由同 cohort supervisor 执行 transport
   admission；只有 admission ready 才可进行完整池 ranking、external top-three 证据和
   provider baseline freeze。
5. freeze 与 official/audited Harness import 同 cohort 且全部 ready 后，才允许 9 类 21
   套 target campaign；之后执行 paired statistics、Holm correction、effect size、四协议
   parity、latency 3x gate、contamination、failure analysis 和最终 completion audit。

在所有 gate 完成前，不做 superiority claim，不改生产 router/prompt/weights，不重启当前
健康的 loopback 服务。r16 全部私有 evidence 保留为 reference-only，r17 不复用任何失败
或成功的 case answer。

