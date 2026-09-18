# 多路径 rate-limit 错误投影一致性交接（2026-09-19）

## 本轮目标

继续补齐 Axio Fusion API 的商业级 admission/error contract。发现 buffered 文本、文本
流和图片流对 `rate_limit_exceeded` 的 metadata 投影不一致；本轮统一公共响应构造器，
不执行 provider screening、target benchmark，也不修改 r18 frozen plan/source/registry。

## 实现

- 新增 `_rate_limit_exhausted_response()`，统一生成 HTTP 429、`rate_limit_exceeded`、
  `metadata.rate_limit`、`raw_prompt_persisted=false`、`secrets_persisted=false` 和
  `Retry-After`。
- buffered 文本、文本增量流、图片增量流全部复用该构造器。
- 没有改变计数窗口、租户身份 hash、budget、in-flight admission 或 provider 调用。

## 验证

- parity 专项：`2 passed`。
- 全量回归：`1128 passed`。
- L1：`python3.11 -m compileall -q src scripts tests` 通过。
- L2：关键 server 导入通过。
- L4：`git diff --check` 通过；本轮没有 provider/target 网络请求。

## 下一步

发布后继续核对 health/runtime/route-plan；外部凭据轮换完成后严格回到
credential-ready preflight -> r18 screening -> transport admission -> ranking -> freeze
-> Harness/import/convergence -> 21-suite campaign。
