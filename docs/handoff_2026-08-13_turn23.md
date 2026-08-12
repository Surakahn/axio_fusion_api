# Axio Fusion API — Handoff 2026-08-13 (Turn 23)

## 本轮结论

- 确认并固化 Claude/GPT 能力分层：
  - `claude-fable-5 ≈ gpt-5.6-sol`
  - `claude-opus-5 > gpt-5.6-terra`
  - `claude-sonnet-5 > gpt-5.6-luna`
- 修复 Fast/Terra 能力带只有上限、没有下限的问题。此前 `axio-terra` 在
  `claude-sonnet-5` 低延迟优势下会错误降级到 Fast 同层模型。

## 代码变更

- `router.py`
  - 新增 `FAST_DIRECT_CAPABILITY_FLOOR = 0.850`
  - 新增 `TERRA_DIRECT_CAPABILITY_FLOOR = 0.876`
  - `TERRA_DIRECT_CAPABILITY_CEILING` 从 `0.895` 调至 `0.890`
  - `_apply_tier_capability_band` 改为闭区间过滤，且保留无候选时的全池 fallback
- `tests/test_fusion_core_regressions.py`
  - 新增能力带上下限回归测试
- `tests/test_axio_fusion_api_standalone.py`
  - 更新 Terra 能力先验断言以匹配 0.88 分层

## 验证

- L1/L2：`router.py` 编译与导入通过
- L3 定向回归：`119 passed, 1 skipped`
- dry-run 路由复核：
  - `axio-fast -> claude-sonnet-5`
  - `axio-terra -> claude-opus-5 + gpt-5.6-terra`
- 全量测试：`1026 passed, 7 skipped, 1 failed`
  - 失败项：`test_hermes_feedback_deadline_budget_blocks_reference_and_rejudge_atomically`
  - 该失败发生在 Hermes 截止时间预算路径，与本轮能力带改动无调用链交集。
  - 需要下一轮单独诊断，不将本轮能力分层修复混入该 deadline 根因。

## 下一轮

- 诊断并修复 Hermes feedback deadline 测试失败。
- 重新跑三个 Fusion 模型对照基准。
- 继续推进推理强度参数五档透传和图片 prompt composer。
