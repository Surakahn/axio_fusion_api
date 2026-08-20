# r17 intake 交接（2026-08-20）

## 继任边界

r16 已完成 16/16 unit terminal，但 transport admission 为 blocked，0 个 canonical model
满足固定 2% gate，不能进入 ranking。因此 r17 只从 r16 的 source contract 创建 immutable
successor，只改变注册日期和 selection seed；不读取 r16 score、transport receipt、ranking、
checkpoint、survivor subset 或 provider output。

- run root：`private/runs/2026-08-20-composite-cohort-r17/`；
- source manifest：`source_manifest.successor.r17.private.json`，SHA-256 `7ba7fc8816cbd32881b47419e2d26d2fa26f7460d551b4d1c747195f8ae15b56`；
- successor receipt：`source_manifest_successor_receipt.r17.private.json`，SHA-256 `5103b24978c39aa2e5318601c9c6377b74948856bcee9c9c78dd7a68114ff640`；
- selection seed：`composite-r17-2026-08-20-transport-successor`，hash `33d47ab09c2b0ac4b18297ad67ce10c730bbd65c3f1d2bb218f067bccc0c90e9`；
- source successor receipt 为 `ready`，敏感信息、raw prompt/label/provider output/provider URL 均未持久化。

## Frozen plan 与 preflight

r17 plan 绑定 r7 probe-bound registry（SHA-256
`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`）、r7 provider probe 和
r7 operational admission，没有传入 r16 transport availability：

- plan：`baseline_screening_plan.r17.private.json`，SHA-256 `336fa9c4f81223622a3f94d21cc249b4d20ba9b392a18a2e1aba54fbc5ba6565`；
- plan digest：`14f0a56ad4f22e21dacbb2209a7e3551517942eb0779dbc4158afd489f6d8c01`；
- binding：2 source families、8 canonical groups/9 replicas、16 serial units、`max_workers=1`、固定 2% fail-fast、estimated provider calls `1712`、`ready=true`。

zero-network preflight 已通过：

- state：`screening_state.r17.preflight.private.json`，SHA-256 `ba2868a0842d804a38b22df876782c68a579f33fcd0d69600f01fad127b5f108`；
- receipt：`screening.preflight.receipt.r17.private.json`，SHA-256 `68c4bd646418f21b2877896c09fe21bcaa44937036b0e59acc1a920c386d3ee1`；
- campaign digest：`0f92d77ddf0a67d2c5e7dc0eb39ea2ba71cbb4203075b51312de0658b08793a9`；
- `status=preflight_ready`、`network_calls_performed=false`、`target_suite_calls_performed=false`、reason codes 为空。

## Harness 控制面

`harness_control.successor/` 已离线生成，使用 r7 已验证的 benchmark control manifests，
没有复制原始 benchmark 数据、答案或 provider output：

- hash-only pin：6/6 ready，SHA-256 `22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`；
- execution plan：`ready_to_execute`，SHA-256 `3593437c083c780c09da784411ea7952c16f73913a68f8770a1fad757d2598ec`；
- acquisition status：SHA-256 `87de4260c7c200f12680f1165625ef4fe666644750e885bf3321a934f5b0a5b8`，6 个 official imports 缺失；
- official import audit：SHA-256 `b7474cddc260bdaf2a356ddcfa531620438d50f38761a54818c00dfad9c7dd7e`，阻断原因为 6 个 suite 的 `missing_suite_runs` 与 `official_import_expected_runs_missing`；
- convergence audit：SHA-256 `a9912294d04e84bd15fb57c892d59a683b2939464f71ba42e3bb8fa206e75b70`，`status=blocked`、`next_gate=screening`、`target_suite_calls_allowed=false`；
- scaffold：SHA-256 `d213b979425a275d4665ecaa57c5b74629bcc4e9db9b8e91b98fbf87d75d7502`，`provider_calls_performed=false`、`target_suite_calls_performed=false`。

这些 blocked 是 screening/ranking/freeze/import 尚未完成的正常控制面结果，不授权任何
target 请求。

## 唯一 live 推进

启动前只读核验 r17 plan/source/probe/admission hash、没有同名活动 screening、preflight flags
和生产 loopback 健康状态。随后只用 `setsid/nohup` 启动一套 r17 `baseline-screening-run
--live`，不使用 `--retry-failed`，不修改 plan，不恢复 r16/r17 checkpoint，不启动第二套
screening。

screening terminal 后由同 cohort supervisor 先执行 transport admission；只有至少 3 个
canonical model 通过固定 2% gate 才能继续 complete-pool ranking、external top-three、
provider baseline freeze 和 Harness convergence。全部 gate ready 后才允许 9 类 21 套
target campaign，并执行 paired statistics、Holm correction、effect size、四协议 parity、
latency 3x、contamination、failure analysis 和 final completion audit。此前不做
superiority claim，不改 production router/prompt/weights。

