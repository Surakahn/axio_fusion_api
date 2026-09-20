# 2026-09-20 最终 claim campaign 终态门禁

## 本轮完成

最终 benchmark audit 过去只验证 campaign 为 live、运行数和 claim 摘要，未验证 campaign
自身的终态。`partial` 或 `blocked` artifact 在运行数被补齐/篡改后可能继续进入后续
cross-artifact claim 审计。

本轮在 `evaluation.py::_final_campaign_summary` 增加 fail-closed 约束：最终 claim 只接受
`status=live_complete`；缺失、`partial`、`blocked` 或其他状态统一产生
`campaign_not_live_complete`，并在安全 summary 中保留 bounded status。该门禁只读取本地
JSON artifact，不执行 provider/target 网络，也不修改任何 screening artifact。

## 验证

- `python3.11 -m py_compile src/axio_fusion_api/evaluation.py tests/test_final_campaign_state_contract.py`
- `python3.11 -m pytest tests/test_final_campaign_state_contract.py -q`
- `git diff --check`

该增量不改变已有 `partial`/`blocked` 诊断含义，也不把 transport 失败转化为排名或质量
结论；只有真实 live campaign 完成全部任务并写出 `live_complete` 才能继续最终 claim 审计。
