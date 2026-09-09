# 工程控制面证据刷新（2026-09-09）

本轮继承既有 Axio Fusion API Goal，只做零 provider/target 网络的工程与证据刷新。
没有修改 r18 frozen plan/source/registry，没有恢复 checkpoint、拼接 survivor subset、
降低 transport gate，也没有启动 live screening。

## 已验证结果

- 全量 standalone 回归：`1116 passed in 272.24s`；`compileall`、包导入和
  `git diff --check` 通过。
- 四协议 gateway self-test：12/12 请求完成且通过，3 个 public model × 4 个
  surface 的 route 一致，`network_calls_performed=false`。
- provider input adapter self-test：4/4 格式通过（chat、responses、anthropic、
  gemini），`network_calls_performed=false`。
- system development readiness：10/10 requirement proven，状态为
  `ready_for_benchmark_validation`；benchmark validation 仍保持独立未执行。
- 顶层 completion audit：9/24 requirement proven，状态为 `incomplete`；首个
  blocker 是 `evidence_pack_final_audit_binding`。其余阻塞项仍属于 live screening
  后的 provider baseline、Harness/import、21-suite campaign、parity、统计和污染
  审计链路。
- live-readiness：本地 operator 环境下 `credential_ready=true`、21 个 registry
  profile 已具备 credential projection；21-suite campaign 仍为 `blocked`，36 个
  blocker 均属于 benchmark/Harness/baseline artifact 链路。
- 对本地 benchmark cache 的只读盘点显示：21 个 suite 中 14 个本地 materialization
  ready；GPQA 受 gated source 阻塞，6 个 suite 需要 official/audited Harness import。
  这只是资产诊断，不把历史 cohort 提升为当前 target 证据。

## 不可变 artifact lineage

以下文件位于 `private/runs/2026-09-09-engineering-control-refresh/`，只保存
hash-safe receipt 字段；历史 artifact 没有被覆盖：

| artifact | SHA-256 |
| --- | --- |
| `code_test_receipt.safe.json` | `b4edce525f2514d7154b7ff5ef96600230fd33441b616ad51bd9c132bdd76eff` |
| `api_surface_protocol.safe.json` | `e8a9210973adf85882677b176d8810060f5d0189a5c336b005ce433206502c96` |
| `provider_input_adapter.safe.json` | `2cff200834487512fbc1c65bb8fcaf91fe793d7d0c13c9368eb3bcf2f3cf61f0` |
| `fusion_live_runbook.safe.json` | `dca395b2424904dbeb671ce26bc7f66340c5386a44861c7707db836e220a353b` |
| `system_development_readiness.safe.json` | `5479da202bec275c2b3d3c2c2c9c02627eb23ea0ec9814f8dde5ea34f2519f4c` |
| `fusion_completion_audit.safe.json` | `04a2c8293e8b71b0addda760ca4f2ec6a434336527626151ee95d04eba790f2d` |
| `fusion_live_readiness.safe.json` | `852424f143b752fad829c892ac7ee1ed375f44841673924ce73ce32b51ec9efb` |
| `fusion_live_readiness.cohort-assets.safe.json` | `8ae3e023649f8d653a07a047d8ed6901d3e33f2565a79f4a0838cabdbc5cd3f1` |
| `benchmark_materialization_status.safe.json` | `8bf33ceca2949252e36f425c73194b6eea072a3d7b1c5dfcbfa0a888eb3d191c` |
| `benchmark_acquisition_status.safe.json` | `27345660539bcded83e497e33e5d7c71aaf38c030320cfed8613dbd61b5253c4` |

## 当前门禁

r18 preflight verifier 仍为 `ready_for_operator_authorization`，并且
`authorization_required=true`。在 operator 明确授权前，不能执行会产生真实 provider
调用和渠道成本的 `baseline-screening-run --live`。授权后的唯一合法顺序仍为：

`screening -> transport admission -> complete-pool ranking -> external top-three -> provider baseline freeze -> same-cohort Harness/import/convergence -> 9 类 21 套 benchmark -> final audit`。

本轮没有 superiority、能力、成本或延迟 claim。

## 追加的独立收敛审计修复

在后续只读审计中发现，`audit_composite_convergence.py` 原先会校验当前 artifact
与 `stage_bindings` 的内容 hash，却没有确认 `binding_digest_input` 实际覆盖这些
stage digest。手工构造的 digest 输入因此可能绕过独立校验。现已加入最小 fail-closed
修复：重新比对 digest input 与 stage bindings/declarations，并在不一致时阻塞；新增
回归测试覆盖该漂移路径。修复后全量回归为 `1117 passed in 269.73s`；上方
`code_test_receipt.safe.json` 的 `1116 passed` 是此前不可变工程刷新 receipt，未被覆盖。
该修复没有网络副作用，也没有改变 r18 frozen 输入。
