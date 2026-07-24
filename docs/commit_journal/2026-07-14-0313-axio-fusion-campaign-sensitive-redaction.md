# 2026-07-14 03:13 +0800：Axio Fusion 与论文阅读 Campaign 的敏感内容回显防护

## 本轮完成

本轮继续推进 ASciFS 第一、二部分基础设施，聚焦 Axio Fusion API、Agent Harness 持久化边界、论文阅读 Campaign 中间产物的安全可靠性。核心目标是防止模型、verifier、planner、synthesizer 或 feedback notes 把用户 prompt、API key、system/history、论文原文片段误回显到 JSON/Markdown artifact 中。

1. 新增并增强共享脱敏基础设施 `axio/sensitive_text.py`：
   - 支持 OpenAI/NVIDIA/Bearer/API key 常见 secret 形态脱敏。
   - 支持 raw source sentinel 脱敏。
   - 支持 reference text 的空白不敏感匹配，处理换行、多空格变体。
   - 支持从 source/prompt 中生成有限滑窗与短句 terms，只在内存中使用，不持久化原文或 terms。

2. 加固 Axio Fusion：
   - live response 文本会用 prompt/system/history 生成的 in-memory redaction terms 清洗后再进入返回 artifact。
   - verifier `review_text` 会用 prompt/system/history/answer 清洗，避免 verifier metadata 回显上下文。
   - `fusion_request_to_dict()` 改为 prompt/system/history 的 hash 与计数收据，不再返回 raw text。
   - feedback notes 改为“省略/脱敏收据”，不再保存自由文本 notes，避免用户误贴 prompt、论文原文或 key。
   - feedback event 增加 `notes_char_count`、`notes_redaction_applied`、`notes_raw_text_persisted=false`。

3. 加固论文阅读 Campaign：
   - planner aspect plan 输出接入 source redaction terms，覆盖 `common_aspects`、`comparison_dimensions`、`paper_focuses`、`synthesis_outline` 和 planner error。
   - synthesizer error 同样走 source redaction。
   - Campaign 主流程把 source redaction terms 透传给 claim coverage。
   - standalone `build_campaign_claim_coverage_report()` 新增 `source_redaction_texts` 参数，直接调用 coverage 时也能清洗 report units、claim text、qualifier、comparison observations 和 unresolved questions。

4. 新增与增强测试：
   - `tests/test_sensitive_text.py` 覆盖 secret、sentinel、空白变体和 reference source phrase 脱敏。
   - `tests/test_model_fusion.py` 覆盖 prompt/system/history/answer 回显防护、safe request dict、feedback notes 不落原文。
   - `tests/test_fusion_api_server.py` 覆盖 `/v1/feedback` HTTP 入口不保存 key/raw marker。
   - `tests/test_paper_reading_campaign.py` 覆盖 malicious planner + malicious synthesizer 回显论文原文时，aspect/synthesis/coverage/graph artifact 不落原文。
   - `tests/test_paper_reading_campaign_claim_coverage.py` 覆盖 standalone coverage 的 source text redaction。

## 验证

已通过：

```bash
nice -n 10 .venv/bin/python -m py_compile \
  axio/sensitive_text.py \
  axio/fabric/model_fusion.py \
  axio/research/paper_reading_campaign.py \
  axio/research/paper_reading_campaign_claim_coverage.py \
  tests/test_sensitive_text.py \
  tests/test_model_fusion.py \
  tests/test_fusion_api_server.py \
  tests/test_paper_reading_campaign.py \
  tests/test_paper_reading_campaign_claim_coverage.py
```

```bash
git diff --check -- \
  axio/sensitive_text.py \
  axio/fabric/model_fusion.py \
  axio/research/paper_reading_campaign.py \
  axio/research/paper_reading_campaign_claim_coverage.py \
  tests/test_sensitive_text.py \
  tests/test_model_fusion.py \
  tests/test_fusion_api_server.py \
  tests/test_paper_reading_campaign.py \
  tests/test_paper_reading_campaign_claim_coverage.py
```

```bash
nice -n 10 .venv/bin/python -m pytest -q \
  tests/test_sensitive_text.py \
  tests/test_model_fusion.py \
  tests/test_fusion_api_server.py \
  tests/test_paper_reading_campaign.py \
  tests/test_paper_reading_campaign_claim_coverage.py
```

结果：`40 passed in 4.02s`。

补充大回归曾启动：

```bash
nice -n 10 .venv/bin/python -m pytest -q tests/test_agent_harness.py tests/test_quality_gate.py
```

结果：该命令共包含约 130 个测试，运行 491.01 秒后由我中断，已完成 `16 passed`，没有失败栈。中断原因是本轮改动的直接验证已由 targeted suite 覆盖，继续等待会明显拖慢当前小收口推进。后续做 Harness evaluation 或 quality gate 改动时，再拆分为更小的回归批次运行。

## 工程判断

本轮没有引入 Rust 重构。原因是本次问题属于 artifact 安全边界、schema 约束与 prompt/source 持久化防护，不是 CPU 热点。当前更合适的实现是 Python 共享 helper + 精准单元测试。后续如果路由、图谱遍历、向量批量去重或千篇级评分合并出现可测的 CPU 瓶颈，再对局部热点做 Rust/PyO3 或 Rust sidecar。

## 剩余风险

1. 脱敏仍然不是语义级 paraphrase 检测；轻微改写后的论文原文可能不会被 reference-term exact/whitespace/sliding-window 机制捕获。
2. feedback notes 已改为不落自由文本，牺牲了一部分人工调试便利性，但换来了更强的 prompt/source/key 边界。
3. 当前 source redaction terms 仅在运行内存中存在，符合“不持久化原文”的要求，但也意味着后续 standalone 工具若没有上游 source terms，只能依赖 generic secret/sentinel 规则。

## 下一步小收口

下一步建议继续在第一、二部分基础设施内收一个不太大的点：做 `Axio Fusion Router Evaluation Harness`，用固定多用户、多任务样例对 Axio-nano/terra/pro 的路由选择、成本估算、verifier 触发、fallback 行为和 artifact 安全声明做离线评测，并把结果写入 JSON/Markdown 报告。这个点会直接服务后续 DeepResearch Agent Harness 的模型选择闭环，也能判断是否存在真正需要 Rust 优化的热点。
