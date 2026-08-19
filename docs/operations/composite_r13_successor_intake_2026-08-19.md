# Composite cohort r13 successor intake（2026-08-19）

r12 已完整 terminal，但 campaign 为 `partial`，complete-pool ranking 被拒绝。r12
所有 state、unit、transport、ranking、supervisor、Harness binding 和 convergence audit
均保留在其私有 run root 中，仅作 reference-only 证据；不恢复 checkpoint、不拼接
completed subset、不降低 transport gate。

## r13 immutable intake

r13 只从 r12 source contract 创建新的 source successor，改变 selection seed 和注册事件：

- source manifest 文件 SHA-256：
  `762e4a63d5d36e3996c710b7f77608b494d4507ace314bdf3bcc16acdce43e94`；
- selection seed hash：
  `f8a35d8235338707976f2509d464fb0d35aae44f31d42f780679378d55373012`；
- frozen plan 文件 SHA-256：
  `fde4aa68dd56eb4a724e2bb90fe7a199ed009b5b1a84928b4caa57e0da341d05`；
- plan digest：
  `899f3cb3f7539ec0789458f21a85be7357042e0cb7275a171ba16ea40d030f97`；
- 16 serial units、2 independent source families、8 canonical groups/9 profiles、
  `max_workers=1`、固定 `2%` fail-fast 和最低 `3` canonical models。

## Zero-network preflight

r13 preflight state 文件 SHA-256 为
`2ea7331d352cda4d00e2c9c0e305e7489e477c26a2e9714a489ffd2060cd2fba`，campaign digest
为 `36700ea5b5ab8c1eb781de9f319913c7fc9b127c11f8076dd88c3c9b0d2e1df0`。preflight
状态为 `preflight_ready`，`network_calls_performed=false`、
`target_suite_calls_performed=false`，9/9 operational profiles credential-ready，
无缺失 endpoint binding、无缺失 key/base URL，敏感字段均为 false。

## 推进顺序

```text
r13 live non-target screening
-> terminal transport admission (failure-rate only)
-> complete-pool ranking
-> provider baseline freeze
-> same-cohort official import
-> convergence audit ready_for_target_campaign
-> 21-suite target campaign
```

只有完整 r13 cohort 通过所有前置门禁后才允许 target 请求；在此之前不做 superiority
claim，不选择 completed subset，不修改 frozen plan。
