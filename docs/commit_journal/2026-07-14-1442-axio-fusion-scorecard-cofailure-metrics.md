# 2026-07-14 14:42 Axio Fusion scorecard 共同失败率实际计算

## 本轮目标

上一提交已经把共同失败率、per-case agreement 和 branch diversity 写进 Fusion API 产品契约。这个小提交继续把契约推进到可执行 scorecard：只要 benchmark batch run 或 imported JSONL 提供 `case_id_hash`，Axio 就能按同一 case 对齐不同候选模型，计算共同失败率和候选分支互补性。

## 已完成

1. 在 `build_fusion_benchmark_scorecard` 中加入 `case_agreement_metrics`
   - 按 `case_id_hash` 聚合不同候选模型的 per-case 结果。
   - 输出：
     - `candidate_count`
     - `case_identity_count`
     - `comparable_case_count`
     - `unanimous_success_count`
     - `unanimous_failure_count`
     - `partial_disagreement_count`
     - `co_failure_rate`
     - `disagreement_rate`
     - `candidate_pair_metrics`
     - `panel_promotion_ready`
     - `panel_promotion_blocker`
   - 只保存聚合指标和候选对指标，不保存原始题面、选项、标签或逐 case 明细。

2. 加入 panel promotion 阻断条件
   - 如果没有 case identity overlap，阻断：`missing_case_identity_overlap_for_panel_promotion`。
   - 如果共同失败率大于等于 `0.5`，阻断：`panel_promotion_blocked_by_high_co_failure_rate`。
   - 如果候选对没有任何 disagreement，阻断：`panel_promotion_blocked_by_no_branch_disagreement`。
   - 这使 Axio-pro 只有在候选模型错误具有互补性时才适合走 panel fusion，否则应回退为 `best_single_model_plus_verifier`。

3. 更新测试
   - 将原来的 scorecard 优胜测试改成真实 per-case 对齐格式。
   - 增加共同失败负例：所有候选在同一批 case 上一起错时，scorecard 必须阻断 panel promotion。
   - eval JSONL 导入测试也改成带 `case_id_hash` 的 per-case rows。

4. 更新文档
   - `docs/axio_fusion_api_product.md` 说明 scorecard 已经实际计算 co-failure rate、partial-disagreement rate、candidate-pair disagreement 和 `panel_promotion_ready`。

## 验证结果

已运行并通过：

```bash
python3 -m py_compile axio/fabric/fusion_benchmark.py
```

已运行并通过：

```bash
nice -n 10 python3 -m pytest -q tests/test_fusion_benchmark.py
```

结果：`26 passed in 0.23s`。

已运行并通过：

```bash
nice -n 10 python3 -m pytest -q \
  tests/test_architecture.py::test_repository_architecture_validation_accepts_current_layout \
  tests/test_fusion_api_server.py \
  tests/test_fusion_router_eval.py \
  tests/test_fusion_router_learning.py \
  tests/test_fusion_api_product_boundary.py \
  tests/test_fusion_capability_discovery.py \
  tests/test_model_fusion.py \
  tests/test_fusion_benchmark.py \
  tests/test_llm.py
```

结果：`105 passed in 1.10s`。

## 已知边界

- 当前共同失败率阈值是工程默认值 `0.5`，后续应通过真实 benchmark scorecard 和模型组合实验校准。
- scorecard 仍然不保存 raw case 内容；如果上游没有提供 `case_id_hash`，Axio 会阻断 panel promotion，而不是允许只有 aggregate score 的优胜声明。
- 本轮仍未运行大规模真实 benchmark，也没有声称 Axio-terra/pro 已经超过最强 provider 单模型。

## 下一步

1. 接入真实 provider inventory 和公开模型证据，生成可执行的 Axio-terra/pro candidate matrix。
2. 用机械硬盘 benchmark cache 跑小规模 live batch，导入 per-case correctness hash 和共同失败率 summary。
3. 用真实 scorecard 校准 `co_failure_rate_block_threshold`、candidate-pair diversity 和 verifier escalation 策略。
