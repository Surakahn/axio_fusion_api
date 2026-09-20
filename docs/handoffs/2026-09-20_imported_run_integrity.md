# Official imported run 完整性门禁交接（2026-09-20）

## 本轮目标

在不停止或重试 r19 screening、不触碰 frozen plan/source/registry、不执行新的 provider 或
target 网络请求的前提下，补齐 official/audited Harness imported run 的离线生产级完整性
门禁。该增量只决定一个 imported artifact 是否可进入现有 readiness/alignment 链路，不对
模型质量、排名、成本或 superiority 作结论。

## 已完成

- `src/axio_fusion_api/evaluation.py`
  - 新增 `axio_fusion_api.imported_run_integrity.v1` receipt。
  - 校验 `case_count == len(case_results)`，case hash 必须存在且不得重复。
  - 校验 `attempted_count == completed_case_count`。
  - 校验每个 case 的非负 `provider_call_count` 与顶层总数一致。
  - 校验顶层 prompt/decoding SHA-256 与 Harness receipt 一致；若存在
    `import_receipt.imported_case_count`，必须与 case 数一致。
  - 将所有失败 reason code 接入既有 `_validate_imported_runs()`，统一计入
    `invalid_import_count`，空 JSON 等不可解析语义 fail-closed。
  - receipt 仅保留计数、摘要 hash、布尔匹配结果和安全旗标，不保存原始 case、prompt、
    provider output、路径、模型身份或 secret。
- `tests/test_imported_run_integrity.py`
  - 完整 imported run 通过。
  - 截断 case、重复 case hash、attempted/provider-call 不一致被拒绝。
  - prompt 绑定冲突与 unsafe persistence 被拒绝。
  - 空 JSON 对象不再被误判为有效 imported run。

## 验证证据

- L1：`python3.11 -m py_compile src/axio_fusion_api/evaluation.py tests/test_imported_run_integrity.py` 通过。
- L2：`from axio_fusion_api.evaluation import _imported_run_integrity_receipt, _validate_imported_runs` 通过。
- L3：新增完整性 + benchmark resume/acquisition/execution/v4 Harness/official campaign：`32 passed`。
- 额外 standalone imported/readiness/alignment 筛选：`9 passed, 395 deselected`。
- `git diff --check` 通过；全量 Python 3.11 回归：`1228 passed in 292.59s`。

## 当前边界与下一步

- r19 screening PID `1972921` 继续运行，命令行和私有 state/checkpoint 绑定不变；不得停止、
  重试或启动第二套 screening。只读查看 state/checkpoint，不读取 raw provider output。
- 本轮没有 provider/target 网络调用，没有修改 r19 frozen plan/source/registry、serving
  registry、router/prompt/weights 或生产服务。
- imported integrity 通过不等于 Harness source-manifest/case-manifest 完整，也不等于
  transport admission、provider freeze、四协议 live parity 或 21-suite campaign ready。
- 合法主线仍为：r19 screening terminal → transport admission → complete-pool ranking →
  external top-three/freeze → official Harness/import convergence → 21-suite paired
  campaign → statistical/latency/call-cost/contamination/final audit。
