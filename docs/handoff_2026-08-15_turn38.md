# Axio Fusion API — Handoff 2026-08-15 (Turn 38)

## 本轮结论

- 原 6 模型 final cohort 在 retry1/retry2/retry3 后仍为 11/12：
  - 11 个单元 completed，`claude-fable-5 / MMLU-Pro` 稳定 3 个 90 秒 timeout。
  - 3 个失败 case 在 retry1/retry2/retry3 中完全一致，不是瞬时网络抖动。
- 直连诊断确认 `claude-fable-5` 对其中 1 个 case 约 85 秒才返回，已逼近 90 秒
  流式/响应硬门禁，因此不能把它作为通过运输门禁的正式 ranking 候选。
- 已按项目既有机制生成 transport-only admission：
  `private/runs/2026-08-14-core-cohort-final/transport_admission.retry3.private.json`
  - status=ready，5/6 模型通过，只有 claude-fable-5 被排除。
  - 该证据不读取分数/标签，只使用 transport failure rate 和 fail-fast 分母。
- 已基于该 transport admission 生成新预注册 5 模型 cohort：
  `private/runs/2026-08-15-core-cohort-transport5/baseline_screening_plan.core.private.json`
  - ready=true，10 tasks，5 models，1070 次预估 provider calls。
  - 不含 claude-fable-5，保留 gpt-5.6-sol/terra/luna、claude-opus-5、claude-sonnet-5。
- 5 模型 live screening 正在后台运行：PID `478163`。
  - 首次启动因漏传 `--transport-availability-file` 被
    `screening_plan_current_inputs_mismatch` 正确拦截；已保留 blocked 诊断文件并补参重跑。
  - 当前首个 MMLU-Pro checkpoint 已写入。

## 当前进度

- 5 模型 transport cohort 尚在运行，state 文件未到首个 finalize。
- 本轮未生成最终 ranking，也没有 superiority claim。

## 下一轮

- 按 15-20 分钟低频探针等待 PID `478163`。
- 全部 10 单元终态后，执行 `baseline-screening-to-ranking`（5 模型 transport cohort）。
- 再进入 provider baseline freeze；随后继续七类十四套正式 campaign 与 claim audit。
- 若后续又有 transport 超门禁模型，继续用 transport-only admission 生成 successor plan，
  不修改冻结 plan，不把 partial cohort 当作正式 ranking。
