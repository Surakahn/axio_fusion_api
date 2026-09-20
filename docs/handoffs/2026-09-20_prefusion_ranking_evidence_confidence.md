# Pre-Fusion 排名证据可信度增量

## 本轮完成

- 在 `prefusion_ranking.py` 增加 `prefusion_operational_evidence_confidence.v1` 安全投影。
- 每个可服务 logical candidate 现在同时记录 research prior confidence、严格流式成功率、
  physical replica coverage、保守 operational confidence 与 unresolved uncertainty。
- operational confidence 取三项证据的最小值，避免高研究先验掩盖失败/缺失 replica；该值
  仅描述当前 serving evidence，不是统计置信区间、模型质量分或 benchmark 结果。
- 排名仍以固定 operational score 为主，仅在 score、research quality、stream reliability
  和延迟完全相同时用 operational confidence 做稳定 tie-break；没有修改 r18 frozen plan、
  source、registry 输入或 provider 调用路径。
- 新增离线回归覆盖保守取值、非法 replica 计数 fail-closed 和稳定 tie-break。

## 验证

```text
python3.11 -m py_compile src/axio_fusion_api/prefusion_ranking.py tests/test_prefusion_ranking.py
PYTHONPATH=src python3.11 -c "from axio_fusion_api.prefusion_ranking import operational_evidence_confidence"
PYTHONPATH=src python3.11 -m pytest tests/test_prefusion_ranking.py tests/test_model_screening.py -q --tb=short
104 passed
```

## 未完成与边界

- 尚未获得 live screening 的双源 non-target evidence；本增量不替代 r18 credential/preflight
  gate、transport admission、complete-pool ranking 或 provider baseline freeze。
- operational uncertainty 不得用于宣称 Axio 或任何 provider 的质量、superiority、成本优势
  或统计显著性；完整 21-suite paired campaign 仍是最终结论唯一入口。
- 多 replica 的 coverage 仍依赖当前 pre-Fusion strict-stream probe；跨主机健康、故障相关性
  和长期稳定性需要独立 endpoint-bound 证据。
