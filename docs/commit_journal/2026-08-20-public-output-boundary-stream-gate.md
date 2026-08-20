# 公共输出边界与四协议流式闸门（2026-08-20）

## 里程碑

本阶段沿 Axio Fusion API 主产品线完成一次兼容层收敛：把 Fusion 内部
Synthesizer 控制信封与四种公共协议的 acting answer 明确隔离，同时保持普通业务
JSON 和调用方显式 JSON 输出契约不变。该改动不读取 benchmark label，不修改
r17 frozen screening、路由权重、prompt、provider registry 或 Harness gate。

## 实现边界

- `compat.py` 提供保守的公共文本归一化：只有完整 JSON/control envelope 命中
  `reasoning`、`ranked_candidates`、`ready_for_synthesis` 等强内部字段时，才提取
  `answer` 或 `final_answer`；显式 `json_object`/`json_schema` 请求保持原文。
- Chat Completions、Responses、Anthropic Messages、Gemini 和 buffered/streaming
  渲染器共用同一归一化结果，完成后的 usage 按公共文本重新计算。
- `orchestrator.py` 增加 request-local JSON-like stream gate。普通文本仍增量输出；
  疑似内部信封只在请求内存中暂存，直到 acting answer 确认后再释放，内部片段不写入
  receipt 或日志。
- safe metadata 只记录应用状态、字符数与 SHA-256；`raw_output_persisted` 和
  `secrets_persisted` 均保持 `false`。

## 验证

- L1：修改文件 `py_compile` 通过。
- L2：`compat`、`orchestrator` 公共符号导入通过。
- L3 专项：`494 passed, 7 skipped`。
- L3 全量：`1074 passed, 7 skipped`，退出码为 0。
- 18900 健康检查保持 `status=ready`；公开模型为三档 Fusion，四协议均可用，网络
  选择为 `proxy`，secrets 未持久化。
- r17 唯一 screening 仍为 `running`，当前 `3 completed / 6 failed_or_blocked`，
  `ready_for_ranking=false`；Harness `next_gate=screening` 且
  `target_suite_calls_allowed=false`。

## 证据边界

本里程碑证明的是公共 API 输出契约和工程回归，不是 provider 能力排序、baseline
freeze、21-suite benchmark 结果或 Fusion superiority。screening terminal 后仍必须
按 `transport admission -> complete-pool ranking -> external top-three -> provider
baseline freeze -> same-cohort Harness -> 21-suite campaign -> final audit` 顺序推进。
