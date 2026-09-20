# Provider fallback 错误可观测性增量

## 本轮完成

provider request-local trace 现在在不保存原始 provider 响应、URL 或密钥的前提下，记录
bounded 的 `provider_error_code_counts` 与 `provider_http_status_counts`。最终失败和
“先失败后由重试/密钥轮换恢复成功”两种路径都保留错误计数，因此可以区分协议错误、限流、
空响应和传输失败对 fallback 的触发影响。

错误码和 HTTP 状态均来自受控的内部异常字段，数值限制在合法 HTTP 范围，字符串截断为
有限长度；这些字段只描述运行时尝试，不代表 provider 能力、模型质量、排名、价格或
benchmark superiority 证据。

## 验证

- `python3.11 -m py_compile src/axio_fusion_api/providers.py`
- `PYTHONPATH=src python3.11 -m pytest tests/test_provider_traffic_control.py -q --tb=short`
- 结果：`6 passed`

测试使用本地 fake opener，未执行 provider/target 网络调用，未修改 frozen screening、
serving registry 或生产服务。

## 边界

该增量不改变 retry/failover 判定、不扩展调用预算，也不把失败恢复自动转化为能力结论。
公共协议仍只接收既有安全投影；原始 provider error body、endpoint、prompt、模型名和
secret 不进入 trace。
