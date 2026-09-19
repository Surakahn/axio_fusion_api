# Pro 跨 provider 角色多样性修复交接（2026-09-19）

## 本轮目标

修复 Pro 路由在存在多个可用 provider 时仍可能形成单一 provider panel 的算法缺口。目标
是保持最高质量 primary 与 mandatory stage 合同，同时在角色可执行且质量足够接近时引入
不同 provider；不能把未通过 role contract 的 provider 当成可用多样性，也不能为了满足
target 强行晋升弱模型。

## 实现边界

- `_select_panel()` 的 provider diversity target 现在只统计至少有一个当前 panel role 可执行
  profile 的 provider。
- `_best_panel_profile_for_role()` 在需要新 provider 的非 primary 角色上，优先选择角色适配
  分不低于当前最佳 `90%` 的跨 provider 候选；没有质量安全候选时保留原质量排序。
- model-selection policy 与 safe trace 增加 role-eligible provider 数、相对质量下限和稳定的
  `provider_diversity_relaxed_reason`（`quality_floor`/`role_contract`）。所有标识仍为 hash-safe
  或固定 reason code。

## 验证证据

- L1：`router.py`、`trace_store.py`、新增回归通过 `py_compile`。
- L2：关键 router/trace 导入通过。
- L3：路由/角色/延迟专项 `72 passed`；多样性与 trace 专项 `17 passed`；全量
  `1181 passed`。
- L4：`compileall -q src scripts tests`、`git diff --check` 通过；无 provider/target 网络调用，
  无 r18 frozen 输入变化。
- r7 serving registry 离线 dry-run：
  - Fast：`fast_direct_cascade`，role admission 不足时 direct；
  - Terra：`terra_direct`，保留 judge gate blocker；
  - Pro：4 个 selected profile、2 个 role-eligible provider、target=2、diversity 满足，
    `pro_panel_judge_escalation` + `provider_judge_synthesis`。

## 发布与后续

里程碑提交 `6cf29c0` 已推送并完成生产发布：先保留
`private/axio_server.18900.console.log.pre-6cf29c0`，再以 `setsid/nohup` 切换至 PID
`3429473`。发布后 `/health=ready`、21/21 runtime eligible、0 open circuits、三档
route-plan 通过；旧 `pre-b128137` 已删除，当前仅保留上述最新回滚副本。不停止/重启/修改
CPA Plus 8317。

该修复不提供 provider 能力、排名或 superiority 证据。r18 screening、transport admission、
ranking、provider freeze、Harness/import 和 21-suite benchmark 仍按单向 gate 等待授权与
完整证据；当前没有新的 live provider 或 target benchmark 请求。
