# Composite r17 Screening 运行态（2026-08-20）

## 本次复核

本记录只保存 r17 live non-target screening 的安全进度元数据和操作边界，不保存 provider
原文、答案、标签、URL、模型原始标识或密钥。复核时间为 2026-08-20 19:21 CST。

- screening PID：`3739367`，仍在运行；
- convergence supervisor PID：`3741799`，仍在运行；
- lineage watcher PID：`3742593`，仍在运行；
- frozen plan SHA-256：`336fa9c4f81223622a3f94d21cc249b4d20ba9b392a18a2e1aba54fbc5ba6565`；
- plan digest：`14f0a56ad4f22e21dacbb2209a7e3551517942eb0779dbc4158afd489f6d8c01`；
- source manifest SHA-256：`7ba7fc8816cbd32881b47419e2d26d2fa26f7460d551b4d1c747195f8ae15b56`；
- registry SHA-256：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`。

## 当前 gate

safe live state 为 `status=running`，16 个 planned units 中 `0 completed / 1 failed_or_blocked`，
`ready_for_ranking=false`，`network_calls_performed=true`，`target_suite_calls_performed=false`。
state 文件 SHA-256：
`a2d04dc54640a8001e5c471d4ba4e2bd9fae6a99cfb27fa63c06ba1b2aa49480`。

第一个 unit 已达到完整的 `102/102` transport 分母：`15 completed / 87 transport_failed`，
因此被固定 fail-fast transport gate 终止。这里的 `completed` 仅表示请求完成了 transport
层返回，不代表答案正确或模型能力；所有失败仍留在完整分母中，禁止选择性抽取或拼接到
后续 cohort。

第二个 unit 当前私有 checkpoint 为 `checkpoint_status=partial`、`12/112`，SHA-256：
`b56b0d2f28b7b385c73757eadd7ef8efc0a46dc786e42abaa3ae7dcaef8982a5`。checkpoint 含 raw
provider output，只作私有恢复证据，不进入 Git，不读取原文，不作为 score、ranking、freeze
或 completion evidence，也不手工恢复。

## 允许的下一步

screening terminal 前只允许按 10–20 分钟低频读取 PID、命令行 identity、safe state/checkpoint
hash、supervisor/watcher 日志和下游 artifact 是否生成。不得修改 frozen plan/source、不得使用
`--retry-failed`、不得启动第二套 screening、不得调整 router/prompt/weights、不得执行
transport/ranking/freeze/import/target 下游命令，也不得为了检查而重启健康的生产 loopback。

screening 自然终态后，由现有同 cohort supervisor 按单向顺序仅执行 transport admission；只有
完整候选池达到固定 2% gate 且至少 3 个 canonical model eligible，才允许 complete-pool ranking、
external ranking、provider baseline freeze、same-cohort Harness import/convergence，最后才是
21-suite target campaign 和 paired statistical/latency/contamination/API-parity audit。

当前不得作任何 Fusion superiority claim。
