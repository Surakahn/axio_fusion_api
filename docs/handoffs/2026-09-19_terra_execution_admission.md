# Terra 路由准入与运行时模式一致性增量交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 的完整 Terra 产品闭环。此前 Terra 已有 role contract、panel
phase、Judge/Synthesizer reservation 和 direct fallback，但 route-plan 与 runtime 没有一份
专门的 bounded receipt 对账“请求了什么、准入了什么、实际执行了什么”。本轮只做离线代码和
fake-provider 回归，不执行 provider/target 网络，不修改 r18 frozen plan/source/registry，
不停止或重启 CPA Plus，也不发布 Axio 18900。

## 实现

- `router.py` 新增 `terra_execution_admission.v1`：固定输出 `requested_mode`、
  `admitted_mode`、`required_roles`、按 canonical identity 去重的 `role_eligible_count`、
  `missing_roles`、`initial_panel_count`、`provider_stage_required`、`fallback_allowed`、
  `degraded` 和 bounded `reason_codes`。
- 角色合同不足时不静默宣称 Terra Fusion 成功。缺少 independent solver、Judge 或
  Synthesizer 分别记录稳定原因；预算、deadline、provider diversity 和 role contract
  阻塞也有固定分类。低风险 direct policy 仍标记为正常 direct，而不是误报 degraded。
- `orchestrator.py` 新增 `terra_execution_outcome.v1`，在 runtime 完成后对账 route mode、
  实际 runtime mode、panel phase 配置、准入/完成的 panel roles、Judge/Synthesizer 尝试和
  完成、mandatory reservations 是否释放、fallback 和 degradation。角色合同导致的 direct
  fallback 明确为 `runtime_mode=direct_fallback`，不会与正常 direct 混淆。
- `trace_store.py`、`compat.py` 增加 hash-safe 持久化和四协议公共 trace 投影；不输出
  provider/model 原文、prompt 或 secret。非 Terra 请求保持 `applies=false`，不改变既有路由。
- 新增离线回归：完整 role pool 的 provider Judge/Synthesizer 执行与 reservation 释放、
  缺少角色的 direct fallback、public Gemini trace parity 和 safe execution receipt。

## 验证

- L1/L2：涉及的 Python 文件 `py_compile`、关键包导入通过。
- L3：Terra 专项回归通过；全量 `PYTHONPATH=src python3.11 -m pytest tests/ -x -q --tb=short`
  为 `1183 passed`。
- `python3.11 -m compileall -q src scripts tests` 通过，`git diff --check` 通过。
- 未执行 provider screening、transport/ranking、target benchmark 或公网流量；本轮结果不构成
  Terra provider 能力、质量、成本、延迟或 superiority 证据。

## 当前边界与下一步

- 当前 serving registry 仍可能没有满足完整 `independent_solver + judge + synthesizer`
  的真实 role capacity；不能用弱模型补齐缺失角色，也不能把 fake-provider panel 结果写回
  serving policy。
- baseline freeze 后，先以 endpoint-bound role successor 做 non-target/shadow replay，分别
  记录 transport、quality、cost、error-correlation 和 stability，再决定是否激活 Terra
  provider Fusion。
- 若真实运行仍出现 partial panel，优先按本轮 reason taxonomy 分诊 panel deadline、预算
  reservation、provider failure 和 role contract，不降低 admission gate。

