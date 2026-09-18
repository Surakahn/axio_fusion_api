# 多副本租户预算安全部署边界交接（2026-09-19）

## 本轮目标

此前租户预算已具备进程内原子预留、成功结算和异常释放，但该账本不是跨进程/跨副本的
共享配额系统。本轮不虚构 Redis、数据库或其他共享后端，先把危险部署模式显式化并
fail-closed，避免横向扩展后出现每个副本各自放行、全局预算被突破的问题。

## 实现

- 新增 `AXIO_FUSION_TENANT_BUDGET_SCOPE`：默认 `process_local`；`shared` 或
  `shared_required` 归一化为 `shared_required`。
- 当每日预算启用且 scope 为 `shared_required` 时，`RuntimeState.reserve_budget()` 不
  产生预留，返回 `tenant_budget_shared_backend_required`；公共入口映射为 HTTP 503，
  provider/image 工作不会启动。
- runtime snapshot 增加 `tenant_budget_scope` 和 `tenant_budget_scope_ready`；不保存
  raw tenant、provider、prompt 或 secret。

## 验证与边界

- 预算专项 6 项、图片与真实增量流专项 70 项通过；L1 `py_compile`、L2 导入、
  `git diff --check` 通过。
- 全部测试均为本地 fake/runtime 路径，没有 provider 或 target benchmark 网络调用；
  r18 frozen plan/source/registry 未修改。
- `shared_required` 只是安全部署门，不是共享账本实现；在真实共享后端完成接口、故障
  注入、跨副本一致性和恢复审计前，不得把该模式改为可放行。
