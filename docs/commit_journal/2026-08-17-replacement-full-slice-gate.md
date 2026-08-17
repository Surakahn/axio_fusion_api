# Replacement 完整固定切片门禁

## 背景

r7 将 MMLU-Pro STEM 作为 GPQA 槽位的显式 replacement。该 replacement 通过
screening-disjointness proof，且只保留完整的固定 60 条切片；此前 case-hash
manifest 仍无条件使用全局 100 条门槛，导致一个合规 replacement 被错误阻断。

## 架构约束

- 普通 GPQA spec 继续使用全局 `min_cases_per_suite`，不会因为 replacement
  规则而自动降级。
- 只有 `replacement_active=true` 且携带正整数 `min_cases` 的 spec，才能将其
  声明的完整固定切片作为该槽位的有效门槛。
- case-hash、source template、source binding、source validation、materialization
  status 和 campaign readiness 统一调用同一策略，避免控制面出现不同门槛。
- replacement identity、screening disjointness 和 anti-leakage 字段保持原有
  fail-closed 约束，GPQA 名称不会被用于掩盖 replacement 身份。

## 验证

- `tests/test_benchmark_replacements.py`：9 passed
- Harness 控制面测试：11 passed
- case/source manifest 相关回归：5 passed
- Python 3.11 `py_compile` 与模块导入检查通过

本变更只影响离线控制面策略，不会中断或重启 CPA Plus，也不改变已冻结的 r7
screening plan。
