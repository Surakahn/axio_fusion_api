# 显式 fail-closed 鉴权模式交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 的商业级运维闭环。当前差距矩阵显示公共鉴权是可选的；本轮
增加显式部署开关 `AXIO_FUSION_REQUIRE_AUTH`，让正式公网部署可以在 key 漏配时 fail-closed，
但不改变当前 loopback 生产实例的兼容行为。本轮不执行 provider 或 target benchmark 请求，
也不修改 r18 frozen plan/source/registry。

## 实现

- `AXIO_FUSION_REQUIRE_AUTH=true` 且没有 `AXIO_FUSION_API_KEYS` 时，公共 endpoint（包括
  `/health`）统一返回 401 `unauthorized`。
- 配置公共 key 后，现有 constant-time 精确匹配保持不变；operator key 仍与公共 key
  分离，inventory 仍要求显式 operator key。
- `/health` 增加 hash-safe `auth_mode`：`required` 或 `optional`；不输出 key、token 或
  其他敏感值。
- 默认关闭，当前 Axio 18900 继续使用 `auth_required=false` 兼容模式，正式公网切换前
  必须先配置真实 key 并做外部验证。

## 验证状态

- L1：`python3.11 -m compileall -q src scripts tests` 通过。
- L2：带 `PYTHONPATH=src` 的关键导入通过；`git diff --check` 通过。
- L3：全量回归 `1122 passed`；新增无 key fail-closed、配置 key 后授权和敏感值隔离回归通过。
- L4：health/trace 不保存 key，默认兼容模式保持不变；本增量不触碰 provider I/O 与冻结证据。
- 本增量不证明 provider 能力、排名、成本、延迟或 superiority。
- 发布：提交 `77202f6` 已推送到 `origin/main`；Axio 18900 以 `setsid/nohup` 受控重启，当前
  PID `2363163`。发布后 `/health` 为 `ready`，`runtime_routing=healthy`，21/21 runtime
  eligible、0 open circuit、21 physical/15 logical、4 providers、`auto -> proxy`，并确认
  `auth_required=false`、`auth_mode=optional`、`tenant_concurrency_enabled=false`。
- 发布后 `axio-fast`、`axio-terra`、`axio-pro` 三个 `/route-plan` dry-run 均成功；未执行
  provider screening、target benchmark 或 CPA Plus 重启。
- 后续流式客户端断开资源生命周期增量见
  `docs/handoffs/2026-09-19_stream_disconnect_resource_lifecycle.md`；全量回归更新为
  `1123 passed`，不改变本轮鉴权发布事实。

## 下一步

1. 公网切换前由部署方配置真实公共/operator key，开启并外部验证 fail-closed 鉴权；当前
   18900 保持兼容模式，不打开 `AXIO_FUSION_REQUIRE_AUTH`。
2. 外部凭据轮换后仍严格回到 r18 screening -> transport admission -> ranking -> freeze
   -> Harness/import -> 21-suite campaign 单向证据链。
