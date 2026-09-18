# r18 preflight 可复现复核交接（2026-09-19）

## 本轮目的

在继续推进产品运行时迭代的同时，对 r18 唯一 live screening 前置门禁做一次零网络、
hash-only 复核。该动作不启动 provider/target 请求，不修改 frozen plan/source/registry，
不恢复 checkpoint，也不改变固定 2% transport gate。

## 复核命令边界

- 使用当前正式 r7 probe-bound registry、r18 plan/source、r7 operational admission、
  原始 preflight 与 credential-ready preflight。
- 复用生产启动所需的 `private/current_channels.env`，并显式设置 `PYTHONPATH=src`，
  确保 verifier 使用与服务相同的网络策略实现。
- 输出写入私有 ignored artifact（本轮最新）：
  `private/runs/2026-08-21-composite-cohort-r18/screening_preflight_verifier.r18.repeat-20260919b.safe.json`。

## 结果

- `status=ready_for_operator_authorization`。
- `ready_for_operator_authorization=true`、`authorization_required=true`。
- `reason_codes=[]`。
- `network_calls_performed=false`、`provider_calls_performed=false`、
  `target_suite_calls_performed=false`。
- 网络投影为 `auto -> proxy`，策略有效，监听器已检测。
- 重复 receipt SHA-256：
  `9e2fed685743449bd88675bed12ad209691a6059f68e2b70892c641330f6a9d8`，与既有
  `screening_preflight_verifier.r18.safe.json` 完全一致。

本轮继续以生产一致环境重跑 verifier，输出
`screening_preflight_verifier.r18.repeat-20260919b.safe.json`；其文件 SHA-256 仍为
`9e2fed685743449bd88675bed12ad209691a6059f68e2b70892c641330f6a9d8`，状态仍为
`ready_for_operator_authorization`、`reason_codes=[]`，且 provider/target/network calls
均为 `false`。该重复证据确认 frozen 输入和网络策略没有漂移，不构成 live screening 授权。

## 结论与下一动作

控制面输入当前自洽，但该状态仍不等同于 live screening 授权。唯一合法下一步仍是外部
凭据轮换完成后，由 operator 明确授权，再按 `screening -> transport admission ->
complete-pool ranking -> external top-three -> provider freeze -> same-cohort Harness`
单向门禁推进。当前不执行 provider I/O，也不提前启动 21-suite target campaign。
