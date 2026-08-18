# Composite r11 successor Intake 与 Harness 控制面（2026-08-19）

## 继任边界

r11 是 r10 partial/ranking-blocked 终态之后注册的全新 immutable successor。只从 r10
source manifest 复制 source contract，改变 pre-registration 的日期和 selection seed；
不恢复 r10 checkpoint，不拼接 r10 completed subset，不复用 r10 transport/ranking/freeze
或 cohort binding，也没有发起 provider/target 请求。

source successor receipt：

- successor manifest SHA-256：`ab15c0149dd85372682bc00a059096e3f884dcc71b58d1dfe391d601cce97a52`；
- receipt SHA-256：`9ca697c620286c519a6ae5b1c33585e3761b5f046c3c3abf582ec637f6d83dc6`；
- selection seed 只保存 hash：`1f104714240625a7d462c94936ee4d0d1c94e773900db0f35f765b985b2c5a5f`；
- registration date：`2026-08-19`；
- `status=ready`，敏感字段和 raw prompt/label/provider output 均未持久化。

## Frozen plan 与 zero-network preflight

r11 plan 使用当前 r7 probe-bound registry、同一 r7 operational admission、两套独立
source family、`max_workers=1`、fail-fast transport policy 和完整 16 个 serial unit：

- plan SHA-256：`6bee0935c72f0f0f718bd1fb51bb5708ad245a18a2141707353538e81b81a728`；
- plan digest：`0a81e8629a0fb6948541dc3fec3d2db828b18fa7df808cf509dc5c6e69fd8aef`；
- registry digest：`7d0a9b78a06ea7445c43b7c03e15d6bbedb3112ecf8fb7d1ad041301678c1ad8`；
- source manifest digest：`ab15c0149dd85372682bc00a059096e3f884dcc71b58d1dfe391d601cce97a52`；
- 预注册 provider call 数：`1712`。

zero-network preflight：

- receipt SHA-256：`b934458818785ca5e5133fcc3c745ae81fd8aefff8aefc667fab36357e1191c4`；
- state SHA-256：`4453527ffc009787fe419bce88d6922773110a1aec628d370ee8462fe4152bd9`；
- campaign digest：`66e22dcbb836c7592921dbf6128799e98f5c7fa19287ab8ee8a81bdaea4e93da`；
- `status=preflight_ready`、`network_calls_performed=false`、
  `target_suite_calls_performed=false`、`reason_codes=[]`。

## Harness 控制面

本机当前没有可重新扫描的 pinned checkout 原目录；r7/r10 的 6-suite pin 内容完全一致，
且只含 hash-only metadata。为保持 provenance，scaffold 新增了显式
`--harness-pin-manifest` 入口：仅允许复用完整 schema、所有 suite `ready=true`、
`blocked_suite_count=0`、`all_paths_hashed_only=true` 且敏感字段不为 `true` 的既有 pin。
该入口不复制原始路径、数据、答案、provider 输出或质量结果；r11 的下游 stage 仍按
自己的 output path 重新生成。

r11 scaffold 输出目录为：
`private/runs/2026-08-19-composite-cohort-r11/harness_control.successor/`。

- Harness pin：SHA-256 `22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`，
  6/6 ready、0 blocked；
- acquisition checklist：SHA-256 `af1ad4767d93a09148c577a7bae50a519b46ea0f43c7a54d8bc174a5a0c08e97`，
  `template_ready`；
- official execution plan：SHA-256 `760e2e3438779daa7d8d2bbfa0fd7fc481bae811542bd6147261e7e9d5fab4be`，
  ready to execute；
- acquisition status：SHA-256 `87de4260c7c200f12680f1165625ef4fe666644750e885bf3321a934f5b0a5b8`，
  等待 official import；
- official import audit：SHA-256 `dc069d2809fbbac5f0ef4408c630355911d9eff52388bdb6ff5222df712f3385`，
  尚未 ready；
- scaffold receipt：SHA-256 `9fc5b2f6a4117fde8cadbf9b409264690c3db91a956b1853cbeb56410e6616e8`；
- 初始 cohort binding SHA-256 `25be318399351d22874dd4275fc0cf7a1b4c262e698bb2c2a6d15b931fa173b4`，
  convergence audit SHA-256 `e9f425f27fadfd1966790b7398dcd1264ed4bd2b2e46cc94fd32baebb038cc51`；
- `status=blocked`、`next_gate=screening`、`target_suite_calls_allowed=false`、
  `target_suite_calls_performed=false`、`provider_calls_performed=false`。

blocked 原因均为合法的前置门禁缺失：screening 尚未 terminal，transport/ranking/freeze
和 official import 尚不存在或未 ready。pin ready 不代表质量排名或 target 授权。

## 下一步

完成本阶段提交后，只启动一个 r11 `baseline-screening-run --live`，并用 setsid/nohup
记录 PID、console log、state 和 private checkpoint。screening 期间 supervisor 只等待
terminal，watcher 只做同 cohort hash-only audit；不得启动 ranking、provider freeze、
official import 或 target。完整顺序保持：

```text
terminal screening -> transport admission -> complete-pool ranking
-> provider baseline freeze -> same-cohort official import
-> convergence audit ready_for_target_campaign -> 21-suite target
```

