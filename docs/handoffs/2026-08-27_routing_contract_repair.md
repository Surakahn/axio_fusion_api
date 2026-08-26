# Goal 状态交接：路由契约与回归门禁修复（2026-08-27）

## 当前 Goal 位置

Goal `01a0202d-8062-7832-b894-af9ec8bebd06` 仍为 `active`。Axio 的产品边界不变：
remote-only Fusion API 通过可复用 prompt、路由、角色编排、Judge、Synthesizer、
fallback 以及成本/延迟/并发预算，对外提供 `axio-fast`、`axio-terra`、`axio-pro`。
Harness 仅负责评测、控制、恢复和证据链。本轮是离线运行时契约修复，没有 provider 或
target benchmark 请求，也没有获得 `r18 live screening` 授权。

## 本轮变更

- 收紧 Fast 轻量校验的基础触发条件：`complexity >= 0.40` 且
  `uncertainty >= 0.40` 才能由基础分析值触发。原先 `0.25/0.30` 会把普通短文本
  误扩展为 Fusion，在 `max_total_model_calls=2` 时耗尽 fallback 槽位；显式质量、
  风险、工具、策略和消息特征仍可独立触发校验。
- 在隐私/资格过滤阶段排除 `health=failed` 与 `health=unavailable` 的 profile，
  并记录 `profile_unavailable` blocker count。校准标记失效的副本因此不会继续进入
  候选池；这只影响运行时资格，不修改 registry 文件或冻结 screening 输入。
- 恢复 7 个历史 skip，并将 Fast fallback 回归断言对齐既定
  `fast_deadline_feasibility_then_observed_latency_then_availability_and_role_fit`
  direct-cascade 契约；fallback 不属于 primary panel。

## 验证证据

- L1：`python3.11 -m py_compile src/axio_fusion_api/router.py` 通过。
- L2：router/orchestrator/compat 关键 import 通过。
- L3：恢复的 7 个专项用例 `7 passed`；全量回归 `1113 passed, 0 skipped`。
- L4：`git diff --check` 通过；变更无硬编码凭据、无 raw provider 输出、无新的
  外部依赖；注释和文档遵循中文项目规范。
- 只读服务检查仍为 `/health=status=ready`、`model_count=21`、`provider_count=4`、
  `network=auto -> proxy`。未重启服务，未改变 serving registry。
- 三档 dry-run 仍符合契约：Fast 为 `fast_direct_cascade`，Terra 在简单输入下
  保持 `terra_direct`，Pro 为 `pro_panel_judge_escalation` 并包含 Judge/
  Synthesizer 角色。

## 证据边界与下一步

本轮测试只证明本地路由和回归契约，不证明 provider 能力、排序、成本、延迟或
Fusion superiority。r18 仍是 immutable offline/preflight 状态；在 operator 明确
回复 `授权 r18 live screening` 前，禁止 provider 请求、恢复 checkpoint、使用
`--retry-failed`、拼接 survivor subset、降低固定 2% transport gate 或运行 21-suite
target benchmark。

获得授权后的唯一顺序仍为：

```text
terminal screening
 -> transport admission
 -> complete-pool ranking
 -> external top-three
 -> provider baseline freeze
 -> 同 cohort Harness imports/binding/convergence
 -> 9 类 21 套 benchmark
 -> paired/Holm/effect/latency/cost/contamination/final audit
```

