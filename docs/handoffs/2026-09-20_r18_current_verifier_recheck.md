# Axio Fusion API 交接：r18 当前零网络 verifier 复核

日期：2026-09-20

## 复核范围

只读加载当前生产 registry、r18 immutable plan/source、r7 private operational
admission、r18 普通 preflight 与 credential-ready preflight，执行
`scripts/verify_screening_preflight.py`。没有启动 provider、target benchmark 或
screening，也没有恢复 checkpoint、使用 `--retry-failed`、拼接 survivor subset 或修改
任何 frozen artifact。

## 结果

- 第一次误把 Axio 18900 服务 PID 作为 screening PID 传入，verifier 正确返回
  `blocked/pid_not_matching`；服务 PID 不符合 `baseline-screening-run --live` 绑定合同；
- 去掉 `--pid` 后返回 `status=ready_for_operator_authorization`、
  `ready_for_operator_authorization=true`、`authorization_required=true`、
  `reason_codes=[]`；
- `pid.status=not_started`；
- network mode 为 `auto`，selected transport 为 `proxy`，listener detected 且 policy
  valid；
- `network_calls_performed=false`、`provider_calls_performed=false`、
  `target_suite_calls_performed=false`；
- safe receipt SHA-256：
  `9e2fed685743449bd88675bed12ad209691a6059f68e2b70892c641330f6a9d8`。

## 边界

`ready_for_operator_authorization` 只表示 frozen 输入、绑定、敏感字段和网络策略在
启动前自洽，不等同于 live screening 授权，也不代表 transport admission、provider
能力、排名、baseline freeze、成本、延迟或 benchmark superiority。获得明确 gate 后，
仍只能按 screening -> transport admission -> complete-pool ranking -> provider
baseline freeze -> same-cohort Harness/import/convergence -> 21-suite campaign ->
final audit 顺序推进。

