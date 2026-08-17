# Composite r7 Successor Intake 设计（2026-08-17）

## 触发条件

r6 已完整终态但 transport admission 只有 1/4 个 canonical models 通过固定门槛，
因此 r6 不生成 ranking、provider baseline freeze 或 target Harness。r6 的 plan、
state、完整分母和失败 telemetry 只读保留；本路线不恢复 r6、不选择 completed subset，
也不降低 3-model minimum 或 transport failure gate。

## r7 控制面架构

r7 采用四段单向 lineage，所有阶段都生成独立 digest，后段不能反向修改前段：

1. **Fresh enrollment**：从当前配置的 NVIDIA、CPA Plus 和 Anthropic channel 重新做
   `/models` discovery 与严格 streaming probe，输出新的 private probe-bound candidate
   registry。该阶段只使用固定 non-target probe，不读取 benchmark case/label/answer。
2. **Operational admission**：对新的完整候选分母执行固定 90 秒 non-target workloads，
   `max_workers=1`、failure threshold `0.25`、至少 3 个 successful workloads；该
   receipt 只决定 production/transport eligibility，不参与质量排序。
3. **Immutable screening successor**：仅当 admission 的 formal baseline eligible
   canonical model 数达到至少 3，才使用新的 source-manifest selection seed 生成 r7
   manifest、zero-network preflight 和 `max_workers=1` fail-fast screening plan；每个
   source/candidate 从零开始，禁止拼接 r6 结果。
4. **Harness lineage**：重建六套 official pin、execution plan、acquisition/import
   audit、cohort binding 和 convergence audit。`ready_for_target_campaign` 以前，
   target calls、prompt tuning、ranking/freeze 和 superiority claim 全部关闭。

## 为什么不直接重跑 r6

r6 的失败以 rate limit、上游 5xx、timeout 和网络策略错误为主，且失败分布在同一
provider channel；旧 screening plan 已经冻结并完成完整分母执行。直接 retry 会混淆
transport 时间点、破坏 plan immutability，并可能把旧 completed subset 变成隐含 survivor。
Fresh enrollment 先刷新 endpoint/protocol/streaming evidence，admission 再确认当前
transport，只有两道门都通过才注册新的 screening cohort。

## 安全边界

provider raw output、prompt、label、raw URL、model id 和 credential 仅可进入
operator-owned private checkpoint；公共文档和 safe receipt 只允许 schema、计数、digest
和 reason code。r7 不修改正式 `cli-proxy-api-plus` 服务，不停止或重启 CPA Plus，不改变
生产 registry；只有经完整 pre-Fusion handoff 的新 registry 才可作为 screening 输入。

## 当前动作

先执行零网络 provider-config preflight，确认当前环境变量与非 secret manifest 可用；随后
以 `setsid` 后台运行 fresh enrollment，低频检查 PID、safe receipt 和输出文件是否增长。
enrollment 未完成前不创建 screening plan，不运行 target Harness；失败则保留完整 receipt
并继续扩展/刷新候选分母，而不是降低固定门禁。

## Fresh enrollment 首轮结果

首轮 enrollment 已自然终态，receipt 为 `status=ready`：

- 运行约 64 秒，`max_workers=1`、90 秒单请求上限；
- discovery/text probe ready，12 个 selected profiles 中 6 个严格流式可用；
- candidate registry：6 个 profile、2 个协议 provider 投影，`generated_from_probe=true`；
- candidate registry SHA-256：
  `c4e590d6bb191147ebab840eb1d0dca03071ffdfd6df03c113d84f65b597dffe`；
- enrollment receipt SHA-256：
  `0f314b27701915dc3ddb9becc872a2ed5a21c88e1d38a8a08961f4e0a30e3286`；
- tool/reasoning/vision calibration：按本轮 admission 设计跳过；
- `secrets_persisted=false`、raw provider output/url 未进入 safe receipt。

对 candidate registry 执行 `registry-diagnostic --require-prefusion` 后，安全结果为
`blocked`，reason 包括 generation marker、catalog/physical projection、role
coverage 和 probe binding 不完整；另有 `weak_or_missing_fast_candidate` warning。
因此该 registry 不能直接成为 r7 screening 输入。该 blocked 结果保留为新鲜 enrollment
的完整证据，下一步必须补齐 NVIDIA focus 候选并重新做 probe-bound merge，不能绕过
pre-Fusion handoff。

## Pre-Fusion 首次尝试与修复

首次 `pre-fusion-screen` 使用了当前 shell 中的 `AXIO_FUSION_REGISTRY_PATH`，导致
命令把生产环境 registry 当作 inventory 输入，`provider_discovery_performed=false`、
`candidate_inventory_complete=false`，在研究 prerequisite 阶段 fail-closed：

- 输出 schema：`axio_fusion_api.pre_fusion_model_screening.v1`；
- 输出 SHA-256：
  `1cb770d2824063cabb74e214ec3a43be1bdb932412f1b361198d8de1276078a`；
- status：`blocked`；
- blockers：`prefusion_complete_inventory_required`、
  `prefusion_research_prerequisite_failed`；
- streaming/reasoning probe：均未执行 provider calls；
- target-suite calls：未执行。

该结果确认了环境 registry 与候选 enrollment 必须显式解耦。修复只限于新的进程环境：
取消 `AXIO_FUSION_REGISTRY_PATH`，保留同一 non-secret provider manifest、focus/source
manifest、研究契约和 90 秒/三样本门禁；不修改生产环境变量、不修改正式服务、不把该
blocked 输出当作 screening 证据。
