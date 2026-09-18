# 图片 lane 成本计量闭环交接（2026-09-19）

## 本轮目标

继续推进 Axio Fusion API 产品本体的商业级预算闭环。审计发现图片增量流成功后曾以
`0.0` 写入租户预算，buffered generation/editing 没有等价成本记录；图片请求还可能先
调用 text prompt composer，但该隐式 Fusion 成本没有进入租户成本观察。本轮不执行
provider screening、target benchmark，不修改 r18 frozen plan/source/registry，也不停止
或重启 CPA Plus。

## 实现

- `schemas._normalize_image_capabilities()` 新增受限 `pricing` 元数据：
  `generation_usd`、`editing_usd`、`unit=request|image`、`source=registry|provider_documented|unknown`。
- 新增 `image_cost_estimate()`，只接受显式可信来源和有限非负数值；缺失、非法或来源
  unknown 时返回 `pricing_known=false`、`cost_usd=null`，不会把 unknown 伪造成免费。
- 图片 buffered、direct stream fallback、HTTP 增量 SSE 均在最终成功 profile 上计量；provider
  failover 只计最终成功 profile，失败、取消和客户端断开不计图片成功成本。
- `ImagePromptTransformer` 通过 tenant observer 报告其 Fusion `actual_cost_usd`，与图片
  profile 成本分别累计；未计价时保持 unknown。
- 公共 image metadata 只包含 bounded image-provider operation/cost/source 状态；租户预算
  内部还会叠加可选 text composer 成本，二者不混淆；继续声明 raw provider
  response/model/prompt/image/secret 不持久化。

## 验证

- L1：修改后的 `schemas.py`、`image_api.py`、`server.py` 和测试 `py_compile` 通过。
- L2：关键导入通过。
- L3：图片专项 `41 passed`，覆盖 generation/editing、buffered/streaming、profile-bound
  pricing、unknown pricing、composer cost 和 HTTP 增量流预算累计。
- L4：`git diff --check` 通过；全量回归 `1140 passed, 0 skipped`；所有异常仍在公共边界被安全收敛；没有 provider/target
  网络请求，没有改变 frozen screening 输入。

## 当前限制与下一步

当前 serving registry 的 verified image profiles 尚未声明 provider-documented image
pricing，因此生产图片成本会明确保持 unknown，不会错误增加或减少每日预算。公网启用
租户预算前，必须先补齐并审查 generation/editing 价格 metadata，再执行同一 fake-provider
回归和受控发布。该限制不影响图片服务本身，也不构成 provider 能力、排名、成本优势或
superiority 证据。
