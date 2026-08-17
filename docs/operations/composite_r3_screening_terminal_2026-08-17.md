# Composite r3 Screening 终态记录（2026-08-17）

## 结论

r3 的 immutable screening plan 已自然终态，但没有通过 transport admission。该 cohort
只提供失败边界和完整分母证据，不提供 provider strength ranking、baseline freeze、
Harness target 结果或 Axio superiority 证据。

## 安全状态

- screening state：`partial`
- serial units：8 planned，1 completed，7 transport-blocked
- `ready_for_ranking`：`false`
- `target_suite_calls_performed`：`false`
- transport admission：`blocked`
- blocking reason：固定最低 canonical model 数不足
- ranking artifact：未生成
- provider baseline freeze：未生成
- target suite calls：0（gate 保持关闭）

控制面 receipt 位于：

`private/runs/2026-08-17-composite-cohort-r3/`

其中只在本地 operator-owned private root 保存恢复所需的 checkpoint；Git、safe
receipt 和本记录不包含 raw provider output、prompt、label、API key 或 raw URL。

## 证据边界

transport admission 只依据完整 screening 分母、unit 终态和 transport failure rate，
不读取答案质量，不将 partial completed subset 当作排名，不将 operational admission
当作质量证据。由于 transport gate 未通过，ranking conversion、provider baseline
freeze、official Harness import 和 target campaign 均不可执行；r3 的 Harness pin
ready 只表示离线 runner/data 控制面可验证。

## Successor 路线

1. 保留 r3 plan、state、checkpoint、transport receipt 和收敛审计作为只读历史。
2. 基于同一经过 probe-bound 的 registry 重新生成 successor immutable plan；新 plan
   使用完整 source/candidate 分母，不恢复或拼接 r3 unit。
3. successor 仍使用 `max_workers=1`、fail-fast transport gate 和至少 3 个 formal
   baseline eligible canonical groups 的门槛。
4. successor terminal 且 transport ready 后，才在同一 cohort 内做 external ranking、
   provider baseline freeze、official import 和 lineage audit。
5. 在 `ready_for_target_campaign` 之前，所有 target calls 必须保持关闭。

## 验证

离线 Harness 控制面专项回归：`31 passed`。本终态只读检查确认 screening、supervisor
和 watcher 已退出，CPA Plus 服务未停止或重启，工作区提交在下一步里程碑完成。
