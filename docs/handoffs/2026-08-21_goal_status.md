# Goal 状态交接（2026-08-21）

## 本轮结论

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 已恢复且仍为 `active`。Axio 的产品边界
没有改变：它是 remote-only 的 Fusion API，通过 prompt、路由、角色、Judge、
Synthesizer、fallback、预算和安全工程统一提供 `axio-fast`、`axio-terra`、
`axio-pro`；Harness 只作为评测、控制、恢复和证据链平面。

本轮完整重读并核对了：

- `docs/axio_fusion_api_product.md`；
- `docs/axio_fusion_benchmark_methodology_21_suites.md`；
- `PLAN.md`、`CHECKLIST.md`、`README.md`；
- 最新 r17 handoff、r17 terminal operation、r18 scout/decision/audit；
- `docs/operations/convergence_execution_path_r20.md`；
- r18 private plan、source、preflight、Harness convergence/import artifacts；
- 当前生产 `/health`、`/v1/models` 和三档离线路由计划。

逐域差距和证据锚点已记录到
`docs/operations/goal_gap_matrix_2026-08-21.md`，并由 `PLAN.md` 顶部链接。

## 当前真实位置

- r17：16/16 unit terminal，6 completed / 10 failed_or_blocked；transport admission
  blocked，仅 1/8 canonical 同时通过两 source family 的固定 2% gate，未生成 ranking、
  provider baseline freeze 或 target 结果。
- r18：immutable successor，2 source families、8 canonical、9 replicas、16 serial
  units、`max_workers=1`、固定 2% gate；preflight 为 `preflight_ready`，没有 provider 或
  target 请求，`ready_for_ranking=false`。
- r18 plan SHA-256：
  `58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`。
- r18 source SHA-256：
  `3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`。
- 当前服务只读状态：`ready`；3 个公共模型；21 个 physical profiles；4 个 provider；
  `auto -> proxy`；当前 serving registry 仍为 r7 probe-bound，没有重启或切换。
- 当前 registry 的 `tool_candidate_count=0`、`pricing_known_count=0`、
  `context_known_count=0`，且 Pro dry-run 的 provider diversity 仍只有一个 provider
  hash。这些是 admission/calibration 缺口，不是可以用静态先验掩盖的能力证据。
- 只读配置审计发现 `private/current_channels.env` 原先仍指向旧的 28-profile Claude
  artifact；已删除旧的重复覆盖声明，并将唯一 registry 声明精确修正为当前正式进程
  使用的 r7 probe-bound 文件。路径与文件 hash 已核对一致，正式 loopback 未重启，CPA
  Plus 未受影响。

## 本轮变更与验证

- 新增 Goal 差距矩阵：`docs/operations/goal_gap_matrix_2026-08-21.md`。
- 新增本交接：`docs/handoffs/2026-08-21_goal_status.md`。
- `PLAN.md` 增加差距矩阵入口。
- 公开 `/health` 投影已增加 hash-safe capability metadata warnings：当工具候选、价格
  或 context window 未校准时分别报告固定 reason code；不改变 `ready` 可服务语义，也不
  参与路由选择。正式 loopback 进程未为此重启，当前仍返回变更前的 `warnings=[]`；下次
  受控发布后才会加载该修复。
- `private/current_channels.env` 的 registry identity 已与正式 r7 serving identity 对齐；
  `registry-diagnostic --require-prefusion` 和 provider 配置摘要均保持零网络，且未打印
  secret 值。该修正只消除未来启动的配置漂移，不改变当前运行进程或 r18 frozen 输入。
- 使用同一 r18 plan/source/r7 registry 和 r7 operational-admission binding，额外生成了
  独立的零网络 credential-ready preflight（不覆盖原始 preflight）：
  `screening_state.r18.credentials-ready-preflight.private.json`、
  `screening.preflight.receipt.r18.credentials-ready.private.json`；两者均为
  `preflight_ready`、9/9 credential ready、`network_calls_performed=false`、
  `target_suite_calls_performed=false`，仅用于后续授权前的 hash/PID 核验。
- `python3.11 -m compileall -q src scripts`：通过。
- 控制面专项回归：20 passed。
- 全量回归：`1075 passed, 7 skipped in 275.11s`。
- 文档安全断言与 `git diff --check`：通过。

## 本轮增量：Terra panel 预算边界复核

在不触碰 r18 frozen plan/source/registry、生产 router/prompt/weights 或 provider 网络的
前提下，新增零网络 fake-provider 回归
`test_terra_high_effort_panel_completes_all_admitted_experts_before_control_stages`。
它绑定 8 个不同 canonical identity、`axio-terra`、`reasoning_effort=high`、6-call 上限，
验证 4 个 expert role 全部完成、12,000ms panel phase 配置成功、Judge/Synthesizer 各 1 次、
无 pending/cancelled future，专项结果为 `5 passed`。

这条证据只说明当前 panel 调度在完整 role pool 下没有确定性预算截断；它不代表真实
provider 能力，也不改变 r7 Terra 的 role-contract admission blocker。后续 live evidence
仍必须把 provider transport、phase deadline、future cancellation 与 role admission 分开
记录；在 baseline freeze 前不放宽 role gate、不改生产路由、不启动 target benchmark。

## 本轮验证复核（全量回归与 r18 身份）

本轮没有新增 provider 或 target 网络调用，完成以下可重复的只读验证：

- `python3.11 -m py_compile tests/test_fusion_core_regressions.py`、
  `python3.11 -m compileall -q src scripts`、`git diff --check` 均通过；
- 全量 `PYTHONPATH=src python3.11 -m pytest tests/ -x -q --tb=short`：
  `1075 passed, 7 skipped in 275.11s`；
- r18 plan/source/serving registry SHA-256 仍分别为
  `58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`、
  `3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`、
  `7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- r18 仍为 16 tasks、2 source families、8 canonical groups、9 replicas、
  `max_workers=1`、`ready_for_ranking=false`；原始 preflight 与独立
  credential-ready preflight 的 `network_calls_performed` 和
  `target_suite_calls_performed` 均为 `false`，后者仅证明 9/9 credential ready；
- 绑定当前 r7 registry 的离线路由复核仍为：Fast `fast_direct_cascade`（因
  `insufficient_independent_models` direct）、Terra `terra_direct`（因
  `screening_role_gate_blocked_judge` 与 `insufficient_independent_models` direct）、
  Pro `pro_panel_judge_escalation`（Fusion active，保留 Judge/Synthesizer）。

## 本轮增量：网关鉴权时序安全

为补齐商业级安全门禁，在不改变 public/operator 鉴权配置语义的前提下，
`server.py` 将 API key 比较从集合交集改为 `hmac.compare_digest`；public key 与
operator key 仍分离，近似/前缀密钥仍拒绝，空配置的现有 loopback 兼容行为保持不变。
该变更不触碰 r18 frozen 输入、provider 网络或生产 serving registry，正式 loopback
未重启。

- L1：`python3.11 -m py_compile src/axio_fusion_api/server.py tests/test_axio_fusion_api_standalone.py`；
- L2：关键 server 导入通过；
- L3：鉴权/CORS/operator 专项 `12 passed`；全量回归 `1076 passed, 7 skipped in 274.87s`；
- `git diff --check` 通过，未在 trace/receipt 中保存密钥。

这些结果只更新工程契约证据，不改变 r18 授权门、provider ranking/freeze 或 21-suite
target gate。

## 本轮 intake 与 convergence 只读审计

按非空 Goal 的 intake-audit 规则重新核对了产品 PRD、当前 handoff、差距矩阵、r18
immutable plan/source、r7 probe-bound registry 和 Harness 控制面。可信锚点仍是 r18
原始 `screening_state.r18.preflight.private.json` 及其已绑定的 Harness artifact；
credentials-ready preflight 只证明 9/9 profile 的凭据可解析，不能替换原始 state，也
不能写入 cohort binding。

使用当前审计器对原始 state 做 hash-only convergence 重审，结果为：

- `status=blocked`，`next_gate=screening`；
- `target_suite_calls_allowed=false`、`final_claim_allowed=false`；
- `plan_mutated=false`，没有 provider 或 target 网络调用；
- Harness pin 与 execution plan 保持 ready，但 transport admission、ranking、provider
  baseline freeze、official import 和 target campaign 仍是未完成或 blocked 阶段。

这次重审只刷新了私有 safe receipt，没有改变 r18 plan/source/registry、路由、prompt、
weights 或生产服务；后续 live 授权前仍必须使用原始 preflight 的 state/path/hash。

## 本轮受控发布与 dry-run 验证

为使已提交的安全与 health 投影代码真正进入 Axio 进程，先优雅停止旧的 18900 进程，
再使用 `private/current_channels.env`、显式 r7 probe-bound registry 和
`setsid/nohup` 启动 `scripts/run_server.py`。新进程 PID 为 `759644`，由 init 托管；日志
确认加载 21 profiles、创建 FusionEngine，未产生 provider 请求。

发布后 `/health` 返回 `status=ready`，公开模型仍为三个 Axio tier，21 physical profiles、
4 providers、网络 `auto -> proxy`。当前 warning 已如实暴露未校准能力：
`some_context_windows_unknown`、`some_model_pricing_unknown`、
`weak_or_missing_tool_candidate`；这三项是 admission/calibration 缺口，不被当作 ready
或 superiority 证据，也没有自动阻断服务。

随后通过本机 `/route-plan` 对 `axio-fast`、`axio-terra`、`axio-pro` 各执行一次 dry-run：
Fast/Terra 因当前 role/admission 容量不足 fail-closed 到 direct，Pro 保留
`pro_panel_judge_escalation` 与 Judge/Synthesizer。route plan 只返回 hash-safe metadata，
没有写入 raw prompt、provider output 或 secret；这次验证没有改变 r18 frozen inputs。

## 下一条合法动作

当前没有新的 live 授权。收到明确的“授权 r18 live screening”后，唯一允许的执行顺序是：

```text
r18 preflight/hash/PID 只读校验
 -> 单一 setsid/nohup live screening
 -> terminal screening
 -> transport admission
 -> complete-pool ranking
 -> external top-three
 -> provider baseline freeze
 -> same-cohort official/audited Harness import/convergence
 -> 9 类 21 套 benchmark
 -> paired statistics / latency / cost / contamination / final audit
```

在授权前不得修改 r18 frozen plan/source/registry，不得恢复 checkpoint、拼接 survivor
subset、降低 2% gate、修改生产 router/prompt/weights 或启动 target benchmark。若
transport 仍 blocked，保留完整分母并创建新的 immutable successor；不得把 partial score
写成能力或 superiority claim。

## 本轮离线增量：自适应渠道指纹

按 Goal 中“渠道变化后只允许通过 shadow/non-target 生成可审计校准建议”的边界，补强
`adaptive_calibration.py` 的渠道指纹：现在只纳入安全白名单中的 provider/model/API
格式、reasoning transport、tool/vision 准入、能力分、上下文、时延/成本元数据；
endpoint/base-url 只保存 SHA-256，`api_key`、`api_key_env` 和其他凭据字段不参与指纹。
因此 endpoint 或能力契约变化会触发校准，而单纯密钥轮换不会制造无意义的 prompt
重校准。新增回归覆盖 capability/transport/endpoint 变化和 credential-only 变化，校准、
CLI、渠道配置专项共 `38 passed`。

该改动没有 provider/target 网络请求，没有修改 r18 plan/source/registry、生产 router、
prompt、weights 或服务进程；它也不把任何分数写回 serving policy。当前 r18 原始
preflight 仍是 `preflight_ready`，`ready_for_ranking=false`、`target_suite_calls_allowed=false`，
下一合法动作仍需 operator 明确回复 `授权 r18 live screening` 后才启动唯一一套
screening。

## 本轮离线增量：自适应校准 receipt 收敛（2026-08-21）

在继续保持 r18 和 target benchmark fail-closed 的前提下，完成了自适应校准第二阶段：
`adaptive_calibration.py` 现在生成 schema 为
`axio_fusion_api.adaptive_calibration_receipt.v1` 的 hash-only 凭证。元提示词只在内存
中生成，产物只保存 `prompt_sha256`、安全决策投影、渠道 fingerprint 和绑定摘要，不保存
prompt 原文、provider 名称/模型 id、provider output、API key 或其他 secret。

校准发布边界已锁定：

- 渠道发生变化但没有 fusion/baseline scores 时为 `blocked`，不能凭配置变化直接形成
  可发布建议；
- 有退化得分但缺少 registry profile set、rollback target、prompt pack、workflow 或
  contamination audit 任一 SHA-256 绑定时仍为 `blocked`；
- 五类绑定和 operational evidence 齐全时最多是 `shadow_candidate`，
  `ready_for_review=true` 但 `activation_ready=false`，且必须人工审查；
- 健康且渠道未变化时为 `not_required`；CLI 不再暴露 `recalibration_prompt` 字段。

验证结果：自适应校准专项 `14 passed`；全量 `1081 passed, 7 skipped in 274.27s`；
`py_compile`、`compileall`、关键包导入和 `git diff --check` 均通过。只读复核确认 r18
plan/source/preflight hash 未变，preflight 仍为 `preflight_ready`、
`ready_for_ranking=false`、provider/target calls 均为 false；Harness convergence 仍
`blocked`，生产 PID `759644` `/health` 仍 `ready`，无重启、无 provider/target 请求。

本轮修改文件为 `adaptive_calibration.py`、`run_adaptive_calibration.py` 及其两份测试，
尚未将任何校准结果写回 serving registry/router。下一合法动作仍需明确
`授权 r18 live screening`；授权前不得恢复 checkpoint、拼接 survivor subset、降低固定
2% transport gate、修改 frozen plan/source/registry 或启动 21-suite target campaign。

## 本轮离线增量：校准 artifact 绑定入口（2026-08-21）

在不触碰 r18 或生产 serving 的前提下，继续完善自适应校准控制面：
`scripts/run_adaptive_calibration.py` 现在支持五类本地绑定 artifact：registry/profile-set、
rollback target、prompt pack、workflow 和 contamination audit。CLI 只在内存读取文件并
计算 SHA-256，五类路径必须成组提供；任何 partial binding 都会在 receipt 生成前拒绝。

完整 binding 加上 fusion/baseline scores 后，专项测试证明 receipt 为
`shadow_candidate`、`ready_for_review=true`，但 `activation_ready=false`，自动激活仍关闭。
无 scores 或缺 binding 的现有行为仍为 `blocked`，无变化渠道仍为 `not_required`。测试只
验证 digest、状态和 redaction，不将 artifact 内容或 provider 输出写入结果。

验证结果：自适应校准专项 `16 passed`；全量 `1083 passed, 7 skipped in 276.34s`；
`py_compile`、`compileall`、关键导入和 `git diff --check` 均通过。没有 provider/target
网络调用，没有修改 r18 plan/source/registry、生产 router/prompt/weights 或服务进程。
当前生产 `/health` 仍为 `ready`，公开模型仍为三个 Axio tier；r18 仍为
`preflight_ready / ready_for_ranking=false`，Harness convergence 仍为
`blocked / next_gate=screening / target_suite_calls_allowed=false`。

下一合法动作仍需明确 `授权 r18 live screening`。授权前不得恢复 checkpoint、拼接 survivor
subset、降低固定 2% transport gate、修改 frozen plan/source/registry 或启动 21-suite target
campaign；本轮 CLI 入口只为未来同 cohort non-target/holdout 证据准备安全绑定路径。

## 本轮只读增量：r17 transport 根因计数复核

在恢复 Goal 后，按当前 PRD、PLAN、CHECKLIST 与 r18 gate 重新做了只读 transport
审计。仅读取 r17 私有 unit 的 hash-safe `status`、fail-fast 标记和 failure telemetry
计数，没有读取 raw provider output、prompt、label、URL 或 secret，也没有发起新的
provider/target 请求。

- 完整分母：1712 case；762 completed、950 transport-failed；916 个是固定前三次
  transport failure 后补入的 fail-fast 未尝试 case。
- 实际 provider attempts：799；失败 attempt：37，其中 timeout 25、HTTP 5xx 8、
  empty provider output 4；HTTP 状态为 500（6 次）和 503（2 次）。
- 两个 source 的计数和 canonical 级分布已记录到
  `docs/scout/transport_root_cause_audit_r17_r18_2026-08-21.md`。结论仍是
  source/profile 相关 transport 不稳定与 90 秒硬上限共同作用，不是已定位的
  router/prompt bug，也不是能力排名证据。

这次复核没有改变 r17/r18 frozen plan/source/registry、生产 router/prompt/weights 或
固定 2% gate。r18 仍是 `preflight_ready`，`ready_for_ranking=false`；Harness 仍为
`next_gate=screening`、`target_suite_calls_allowed=false`。唯一下一动作仍需 operator
明确回复 `授权 r18 live screening`，之后才按 screening -> transport admission ->
ranking -> baseline freeze -> same-cohort Harness -> 21-suite campaign 顺序执行。

## 本轮实现增量：可复用 transport 根因审计入口

为避免每个 cohort 手工读取 private unit，新增 `scripts/audit_screening_transport.py`。
它先按 64 位 hash 文件名 allowlist 发现 unit，再只读取
`non_target_screening_unit_private.v1` 的状态和 failure telemetry allowlist；checkpoint、
日志和其它 private artifact 不会被打开。审计输出通过 atomic replace 写入，包含输入
hash、完整分母、fail-fast、provider attempt/failure、source/canonical 机制分布和
admission 一致性检查；不保存 raw provider output、prompt、label、URL、model id 或 secret。

真实 r17 回归已生成 receipt：
`private/runs/2026-08-20-composite-cohort-r17/transport_root_cause_audit.r17.safe.json`
（SHA-256 `f91f064539dd246ae5836c669e40c0dc931d9f4b15028fb2075cdd0069081b73`）。结果为
16 units、1712 cases、762 completed、950 transport-failed、916 fail-fast、799 provider
attempts、37 failed attempts；provider failure 与 `screening_fail_fast_gate` 单独统计，
`transport_admission_status=blocked` 保持不变。

验证结果：transport audit 专项 `4 passed`，Harness/screening/convergence 相关回归
`88 passed`，全量 `1087 passed, 7 skipped`，L1/L2、compileall、CLI help 和
`git diff --check` 均通过。本轮没有 provider/target 网络调用，没有修改 r18 frozen
plan/source/registry、生产 router/prompt/weights 或服务进程。

## 本轮实现增量：r18 启动前 preflight verifier

为把授权前的最后一次只读核验固定成可复用控制面入口，新增
`scripts/verify_screening_preflight.py` 和 `tests/test_screening_preflight_verifier.py`。
verifier 只读取 frozen plan/source/registry、r7 operational admission、r18 原始与
credential-ready preflight；复用现有网络策略的 secret-free summary，检查 schema、
digest、双 source/2% fail-fast 合同、remote-only/no-cheat 字段、9/9 credential readiness、
`auto -> proxy`、可选 PID 的 `baseline-screening-run --live` 输入绑定以及变体和嵌套
anti-leakage 字段。receipt 只保存文件哈希、状态、reason code 和命令哈希，不保存路径、
命令行、provider 标识、URL、prompt、输出、标签或 secret。

真实 receipt：
`private/runs/2026-08-21-composite-cohort-r18/screening_preflight_verifier.r18.safe.json`，
SHA-256 为 `9e2fed685743449bd88675bed12ad209691a6059f68e2b70892c641330f6a9d8`，状态为
`ready_for_operator_authorization`、`authorization_required=true`、PID 为
`not_started`。这只证明启动前静态输入自洽，不授权 live screening；没有产生 provider
或 target 请求，也没有修改 r18 frozen plan/source/registry、生产 router/prompt/weights
或服务进程。

验证：专项 `5 passed`；`python3.11 -m compileall -q src scripts tests`、关键包和
脚本导入、CLI help、敏感字段扫描、`git diff --check` 通过；全量回归为
`1092 passed, 7 skipped in 278.61s`。r18 plan SHA-256 仍为
`58c1d7d20f3d064252e5551abdbc10ddf26ed075ca0d97e660e62f20fdc1e504`，source SHA-256
仍为 `3844caf2aa53e4e419f4b9a318ec571ed9a3463e1d56d2f7034989209c8ce815`。

下一条合法动作未改变：等待 operator 明确回复 `授权 r18 live screening`；授权后先
复用该 verifier 做最后一次静态核验，再用唯一一套 `setsid/nohup` live screening，并
沿 `screening -> transport admission -> complete-pool ranking -> external top-three ->
provider baseline freeze -> same-cohort Harness -> 21-suite campaign` 单向推进。
