# Goal 状态交接：r18 preflight 身份复核（2026-08-27）

## 复核范围

本轮只读复核 r18 immutable screening 的 preflight verifier、r7 operational-admission
绑定、当前 serving registry 和服务状态。没有 provider/target 请求，没有恢复 checkpoint，
没有修改 r18 frozen plan/source/registry，也没有获得 live screening 授权。

## 发现与结论

- 首次复核使用了不存在的 `.../composite-cohort-r7-admission/` 路径，verifier 正确
  fail-closed 为 `blocked` / `artifact_missing`；这不是 provider 失败或 screening 结果。
- 改用 canonical private artifact
  `private/runs/2026-08-17-composite-cohort-r7/operational_admission.r7.private.json`
  后，verifier 恢复为 `ready_for_operator_authorization`，`reason_codes=[]`，且与已
  保存的 r18 receipt 字段完全一致。
- private operational-admission 文件 hash 为
  `bf6db0c659b728a6d4c0a8e5d99c1fb9b66e1f70ec96977de048fd393c77af12`；对应的 safe
  投影 hash 为 `214cdb99c47014a888b83cbcc47a2fa19d2ab2680fe884de4d33f6600ce2b656`。
  两者状态均为 `ready`，但不是同一文件，不能混用；r18 历史 verifier 绑定的是
  private hash。

## 当前可信状态

- r18 preflight：`preflight_ready`；credential-ready preflight：`preflight_ready`。
- verifier：`ready_for_operator_authorization`，`authorization_required=true`。
- `network_calls_performed=false`、`provider_calls_performed=false`、
  `target_suite_calls_performed=false`。
- 重新执行 verifier 的 receipt hash 为
  `9e2fed685743449bd88675bed12ad209691a6059f68e2b70892c641330f6a9d8`，与已保存
  receipt 一致。

这些证据只证明控制面输入自洽和授权前安全状态，不证明 transport admission、模型能力、
排序、成本、延迟或 Fusion superiority。

## 下一条合法动作

在 operator 明确回复 `授权 r18 live screening` 前，继续保持 provider/target fail-closed，
不得恢复 checkpoint、使用 `--retry-failed`、拼接 survivor subset、降低固定 2% gate 或
运行 21-suite target benchmark。获得授权后仍按 screening -> transport admission ->
complete-pool ranking -> provider baseline freeze -> 同 cohort Harness convergence ->
21-suite campaign -> final audit 顺序执行。

