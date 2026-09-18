# 公网部署契约 fail-closed 交接（2026-09-19）

## 本轮目标

当前 Axio loopback 实例允许兼容模式，鉴权可选，预算账本为进程内状态。该组合不适合
直接当作多副本公网生产配置。本轮增加启动前部署契约，不引入未验证的共享后端，也不
改变当前 loopback 流量。

## 实现

- `public_deployment_contract()` 输出 `public_mode`、`ready`、有限 reason codes、鉴权
  配置状态和租户预算 scope；不返回 key/token。
- `AXIO_FUSION_PUBLIC_DEPLOYMENT=true` 时，`scripts/run_server.py` 要求：
  - `AXIO_FUSION_REQUIRE_AUTH=true`
  - 至少一个公共 API key
  - 至少一个 operator API key
  - 若每日预算启用，则 `AXIO_FUSION_TENANT_BUDGET_SCOPE=shared_required`
- 契约不满足时在加载 HTTP 服务前退出，避免“服务已监听但安全配置不完整”。默认
  loopback 模式不受影响，health 增加安全投影便于运维核验。

## 验证与边界

- 部署契约、预算、图片和真实增量流专项 `82 passed`；L1/L2 和 `git diff --check` 通过。
- 本轮未执行 provider/target 网络请求，未修改 r18 frozen plan/source/registry。
- 这只是公网启动安全门，不等同于真实公网发布；真实 key、共享账本、外部流量 smoke
  和 provider baseline/freeze 仍需独立证据。
