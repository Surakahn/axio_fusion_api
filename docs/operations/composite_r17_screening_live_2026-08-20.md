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

## 20:11 CST 低频复核

本次复核仍只读取安全 state、进程身份、checkpoint 元数据和控制面产物；没有读取
checkpoint 中的 provider 原文，也没有发送新的 provider/target 请求。

- screening PID `3739367`、convergence supervisor PID `3741799`、lineage watcher PID
  `3742593` 均仍由 init 托管，命令行 identity 未漂移；生产 loopback 未重启。
- frozen plan/source/registry 的 SHA-256 仍分别为
  `336fa9c4f81223622a3f94d21cc249b4d20ba9b392a18a2e1aba54fbc5ba6565`、
  `7ba7fc8816cbd32881b47419e2d26d2fa26f7460d551b4d1c747195f8ae15b56`、
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`。
- safe live state 仍为 `status=running`，16 个 planned units 中 `0 completed / 1
  failed_or_blocked`，`ready_for_ranking=false`，`network_calls_performed=true`，
  `target_suite_calls_performed=false`；state hash 仍为
  `a2d04dc54640a8001e5c471d4ba4e2bd9fae6a99cfb27fa63c06ba1b2aa49480`。
- 当前 MMLU-Pro unit 的私有 checkpoint 仍为 `partial`，预期 112 个 case，已写入 111
  个 case-result 元数据；checkpoint SHA-256 为
  `d69ef3c23cee241f72dcd94c40e4ef00181d4758f71715ab1a391ddd69e8c20c`，
  `raw_provider_outputs_persisted=true` 仅表示私有恢复证据存在，不能转化为 score、
  ranking、baseline 或 completion evidence。
- 同 cohort Harness binding 仍为 `blocked`，convergence audit 仍为 `running` 且
  `next_gate=screening`；`target_suite_calls_allowed=false`、
  `target_suite_calls_performed=false`。没有 transport admission、ranking 或 provider
  baseline freeze 产物。

### Screening 后的收敛设计边界

screening terminal 后只允许按既定单向 gate 推进：

```text
terminal screening
  -> transport admission（完整分母、仅 transport 字段）
  -> complete-pool ranking（两源 non-target calibration）
  -> external top-three evidence
  -> provider baseline freeze（fast candidate + cross-provider verifier）
  -> same-cohort Harness import/convergence
  -> 21-suite target campaign
  -> paired statistics / latency / parity / contamination / final audit
```

只有 baseline freeze 完成后，才进入以下可审计算法工作流：

1. **受约束 portfolio/router 优化**：以 non-target calibration 的质量后验、p50/p95
   latency、成本和 provider/profile 独立性作为输入，在硬预算、角色资格、跨 provider
   verifier 和 3x latency 约束下选择 panel；候选策略必须先 shadow replay，再用独立
   holdout 运行，不能读取 21-suite target labels。
2. **Judge/Synthesizer 校准**：按 suite/category/难度桶校准 confidence 与 claim
   equivalence，单独测量 unsupported-high-confidence、同源共识和跨 provider verifier
   缺口；任何早停策略必须保留 process-completion receipt，不能把 degraded answer 当成
   完整 Fusion。
3. **自适应学习闭环**：只允许 allowlisted policy controls（panel size、independence
   threshold、escalation eligibility、compression preference）进入候选 policy；采用
   contamination audit、decision replay、paired shadow evidence、rollback target 和
   显式 approval record，禁止自动 benchmark-driven promotion。
4. **最终统计与质量门禁**：对同 case hash 的 Axio/冻结 baseline 做 paired comparison，
   以预注册的 Holm-Bonferroni family（21 suites x 3 tiers）控制多重比较，并同时检查
   effect size、p50/p95 latency <= 3x、四协议 parity、tool/schema 稳定性和污染审计。

 在上述阶段完成前，任何新增算法只能作为研究设计或 shadow candidate，不得修改生产
 router/prompt/weights，也不得宣称 superiority。

## 20:20 CST 第二个 unit 终态

最新安全 state 已进入 `1 completed / 1 failed_or_blocked`，但整个 16-unit screening 仍为
`status=running`、`ready_for_ranking=false`；`network_calls_performed=true`、
`target_suite_calls_performed=false`。第二个 112-case unit 的 completed 只代表 transport
终态，不代表答案质量、ranking 或 baseline evidence，也不允许抽取 survivor subset。

筛选器随后按 frozen serial schedule 进入第三个 102-case unit。其私有 checkpoint 为
`checkpoint_status=partial`、`3/102`，SHA-256 为
`71fc050c8aa1364211ff1310d5457e2c65f93f26c50345f12c946d43f95af6d6`；文件含 raw provider
output，仅供私有恢复证据使用，不读取原文、不进入 Git、不手工恢复。

transport admission、ranking、provider baseline freeze 和 target campaign 仍不存在；
lineage watcher 的 `next_gate=screening` 与 target-call 禁止标志未改变。继续按 10–20
分钟低频只读核对，不修改 frozen 输入、不启动第二套 screening、不重启生产 loopback。

## 20:29 CST 第三个 unit 低频进度

三个托管进程仍存活且命令行 identity 未漂移。safe state 仍为 `status=running`，
`1 completed / 1 failed_or_blocked`，`ready_for_ranking=false`，
`target_suite_calls_performed=false`。第三个 102-case unit 的私有 checkpoint 已推进到
`31/102`，状态为 `partial`，SHA-256 为
`d68e2327a3e458858da92789e1cbf02d005a9a4b503faed4a42dfa25f06a5077`；其 raw provider
output 仅供私有恢复证据使用，不读取、不提交、不解释为质量或排名证据。

下游 transport admission、ranking、provider freeze、Harness import 与 target campaign
仍不存在。继续低频读取 PID/state/checkpoint hash 和 supervisor/watcher 日志，保持
`next_gate=screening` 与 target-call fail-closed 边界。

## 20:41 CST 第三个 unit 增量复核

本次仍只读取安全元数据、进程 identity、checkpoint 元数据和控制面日志，没有读取
checkpoint raw provider output，也没有发送新的 provider/target 请求。screening PID
`3739367`、convergence supervisor PID `3741799`、lineage watcher PID `3742593` 均存活，
命令行 identity 与 r17 frozen plan/source、r7 probe-bound registry 绑定未漂移；生产
loopback 未重启。

safe live state 仍为 `status=running`、16 个 planned units 中 `1 completed / 1
failed_or_blocked`，`ready_for_ranking=false`、`network_calls_performed=true`、
`target_suite_calls_performed=false`；state SHA-256 为
`0cddbd887aea6115205e33acd14d3333e2c09de398972a253501d3f51fd55d42`。第三个 102-case
unit 的私有 checkpoint 仍为 `partial`，当前已有 `44/102` 个 case-result 元数据，SHA-256
为 `3c4284f56b9c949e42c55cdffc180397213e93985a32df0e551ddc961bf1a29f`；其中
`raw_provider_outputs_persisted=true` 只代表私有恢复证据存在，不作为 score、ranking、
freeze 或 completion evidence。

transport admission、ranking、provider baseline freeze、Harness import 和 target campaign
仍未生成。继续按 10–20 分钟低频策略核验 PID、safe state/checkpoint hash、supervisor/watcher
日志及下游 artifact，保持 `next_gate=screening` 与 target-call fail-closed 边界；不恢复
checkpoint、不使用 `--retry-failed`、不启动第二套 screening、不修改 frozen 输入或生产
router，不重启健康服务。

## 20:51 CST 工程回归验证

本轮用当前工作树执行 `python3.11 -m pytest tests/ -x -q --tb=short`，退出码为 `0`，
得到 `1066 passed, 7 skipped in 273.89s`。这是代码与协议回归证据，不是 provider 质量、
benchmark 排名、baseline freeze 或 Fusion superiority claim；本轮没有修改 Python 核心
代码、生产 registry 或 r17 frozen screening plan。

回归期间 r17 后台 screening/supervisor/watcher 身份未漂移，safe state 仍为 `running`、
`1 completed / 1 failed_or_blocked`、`ready_for_ranking=false`、
`target_suite_calls_performed=false`；活动第三个 unit 的私有 checkpoint 只以安全计数
`70/102` 记录，raw provider output 未读取。下游 transport admission、ranking、freeze、
Harness import 和 target campaign 仍未启动。

## 20:58 CST 第三个 unit 终态与第四个 unit 启动

screening 按冻结的 serial schedule 完成第三个 102-case unit，并安全计入
`2 completed / 1 failed_or_blocked`；完整 16-unit campaign 仍为 `status=running`、
`ready_for_ranking=false`、`network_calls_performed=true`、`target_suite_calls_performed=false`。
safe state SHA-256 为 `bd5333cc4789c133f41485ecd2f86626efc497f22b61305c3e0754d9650019fd`。

筛选器随后进入第四个 112-case serial unit。其私有 checkpoint 为 `partial`、`0/112`，
SHA-256 为 `d4ca62df881c011cde06132ada864d20e8308832117a858a1b6de523c7048a88`；
`raw_provider_outputs_persisted=true` 仅表示私有恢复证据存在，不读取、不提交、不解释为
质量、ranking、freeze 或 completion evidence。

下游 transport admission、ranking、provider baseline freeze、Harness import 和 target
campaign 仍不存在；继续保持 `next_gate=screening` 与 target-call fail-closed，禁止恢复
checkpoint、使用 `--retry-failed`、启动第二套 screening、修改 frozen 输入或重启健康服务。
