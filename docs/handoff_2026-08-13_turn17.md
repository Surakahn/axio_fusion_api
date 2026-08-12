# Axio Fusion API — Handoff 2026-08-13 (Turn 17)

## 关键修复: CPA渠道bypass导致超时

### 根因
- CPA Plus内部IP `10.195.91.64:8317` 在 `AXIO_FUSION_PROXY_BYPASS_HOSTS` 中
- 直连时 `/models` 端点正常但 `/chat/completions` 端点TCP连接超时
- 通过代理 `http://127.0.0.1:10808` 后一切正常

### 修复
1. `private/current_channels.env`: 
   - 移除 `10.195.91.64` 从 `AXIO_FUSION_PROXY_BYPASS_HOSTS`
   - CPA URL改为 `https://cpa.co6.click/v1`
2. 服务器重启，bypass数从2→1

### 验证
```
axio-terra: 2+2=? → 4 (6.8s) ✓
axio-terra: Capital of France? → Paris (7.4s) ✓
axio-terra: Is Earth flat? → No (10.6s) ✓
baseline:   Is Earth flat? → No (7.2s) ✓
```

## 渠道状态

| 渠道 | 状态 | 方式 |
|------|------|------|
| CPA Plus | ✅ 正常 | 通过代理 (cpa.co6.click/v1) |
| NVIDIA | ✅ 正常 | 直连 (integrate.api.nvidia.com) |
| Claude | ⚠️ 需代理 | tokenapis.com通过代理可用 |

## 当前状态

- 服务器: 运行中, 32模型, 3Provider
- bypass_hosts: 仅 `integrate.api.nvidia.com`
- Claude能力分: 正确注入 (claude-opus-5 #1)
- 推理强度: 五档完整透传

## 待完成

| 任务 | 状态 |
|------|------|
| 校正后基准评测 | 🔄 脚本就绪，ARC题较长易超时 |
| 全量测试套件 | 待跑 |
| Claude渠道修复 | ⚠️ tokenapis需代理 |
| 外部排名冻结 | 待完成 |
| 图片模块增强 | 基础完成 |

## 关键命令

```bash
# 重启 (新配置)
source private/current_channels.env
setsid python3.11 scripts/run_server_noprefusion.py > /tmp/axio_server.log 2>&1 &

# 快速测试
PYTHONPATH=src python3.11 -c "
from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.schemas import FusionRequest, FusionPolicy
p=load_registry('private/runs/2026-08-11-triple-merge/merged_registry.private.json',require_prefusion=False)
e=FusionEngine(p)
r=e.complete(FusionRequest(model='axio-terra',prompt='2+2=?',reasoning_effort='high',max_output_tokens=5,policy=FusionPolicy()),live=True)
print(r.text)
"
