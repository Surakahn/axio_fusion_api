# Harness replacement-aware acquisition status

## 问题

Composite Harness 的 acquisition status 原先只按
`<dataset-dir>/<suite-id>.jsonl` 查找数据。r7 的 GPQA 槽位使用显式
MMLU-Pro STEM replacement，真实路径和 suite id 不同，因此即使 case-hash
manifest 与 source manifest 已通过，控制面仍会错误报告 `dataset_file_missing`。

## 修复

- `build_benchmark_acquisition_status` 新增可选 `dataset_manifest_path`。
- 提供 manifest 时，suite path、task format、replacement identity 和动态完整
  固定切片门槛均来自同一 normalized spec。
- 未提供 manifest 时保留原有 `dataset_dir/<suite-id>.jsonl` 行为，兼容旧调用者。
- CLI 与 `prepare_composite_harness.py` 传递 replacement-aware manifest，并只在
  receipt 中保存路径和内容 hash，不保存原始数据路径或内容。

## r7 现场验证

- local dataset suites：15/15 ready
- GPQA 槽位：MMLU-Pro STEM replacement，60/60，effective minimum=60
- official import suites：6 个仍等待 operator-owned import receipts
- target suite calls：仍为 `false`；screening 尚未终态时不授权 target campaign

验证通过：Python 3.11 语法/导入、replacement tests 10 passed、Harness control
tests 11 passed、acquisition status 相关 standalone tests 3 passed。
