# 四协议流式错误码一致性交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 的商业级公共协议闭环。流式协议文档要求错误包含 bounded
code/message，但审计发现 Anthropic 和 Gemini 的流式错误缺少可跨协议识别的 Axio
machine code；本轮补齐该契约，不执行 provider screening、target benchmark，也不修改
r18 frozen plan/source/registry。

## 实现

- Chat/Responses 保持现有 code 语义。
- Anthropic typed `error` event 增加 bounded `error.code`。
- Gemini SSE error object 保留原生数值 `error.code`，并在
  `error.details[].code` 输出 Axio bounded code，固定 namespace 为
  `type.googleapis.com/axio.fusion.v1.Error`。
- 所有错误仍限制长度和字符集，不输出 provider 原始 body、URL、prompt、secret 或内部
  role 文本。

## 验证

- 流式专项：`27 passed`。
- 四协议 standalone streaming 回归：通过。
- 全量回归：`1127 passed`。
- L1：`python3.11 -m compileall -q src scripts tests` 通过。
- L2：关键 `compat` 导入通过。
- L4：`git diff --check` 通过；本轮零 provider 网络请求。

## 下一步

继续审计预算/并发/速率组合边界和 stream/image 收尾；外部凭据轮换后严格回到
credential-ready preflight -> r18 screening -> transport admission -> ranking -> freeze
-> Harness/import/convergence -> 21-suite campaign。
