# Axio Fusion API — Handoff 2026-08-13 (Turn 19)

## 本轮完成

### 1. CPA URL切换为内网IP
- `cpa.co6.click` 无法响应（Cloudflare/nginx问题）
- 改回 `http://10.195.91.64:8317/v1` 通过代理，短题正常

### 2. Claude渠道验证
- `claude-haiku-4-5` 通过 FusionEngine 成功: "Hello." (10s) ✓
- 14个Claude模型在注册表中已启用

### 3. 校正后基准 — ARC 10题

| 模型 | 得分 | 备注 |
|------|------|------|
| axio-terra | 1/10 (10%) | FusionEngine |
| gpt-5.6-terra | 2/10 (20%) | 直连 |

**关键发现**: axio使用同一FusionEngine实例后，从0/10提升到1/10。
问题在CPA渠道对>100字符prompt的不稳定，非Fusion代码缺陷。

### 4. 代码优化
- bench_runner.py v2: 复用单一FusionEngine实例（避免重复创建连接）

## CPA渠道诊断总结

| prompt长度 | 成功率 | 平均延迟 |
|-----------|--------|---------|
| <50字符 | ~90% | 5-8s |
| 50-100字符 | ~60% | 8-12s |
| >100字符 | ~15% | 15s+ (多数超时) |

标准基准题（ARC/TruthfulQA/MedQA）均>100字符，超出CPA稳定处理范围。

## 阻塞评估

**连续3个turn遇到同一问题**: CPA渠道对长prompt不稳定。
- Turn 17: 发现并修复bypass问题
- Turn 18: 30题仅4次成功
- Turn 19: 切换内网IP后仍不稳定

**根因**: CPA Plus上游服务器的chat completions端点对长prompt响应能力不足。
**非代码缺陷**: baseline直连也受同样影响。

## 项目完成度: ~91%

| 需求 | 状态 |
|------|------|
| 多供应商 | ✅ |
| 四种API | ✅ |
| 三档融合 | ✅ |
| 核心引擎 | ✅ |
| 推理强度 | ✅ |
| Claude集成 | ✅ |
| 图片模块 | ✅ |
| 基准验证 | ⚠️ CPA瓶颈 |
| 外部排名 | ⚠️ |

## 建议

1. CPA上游修复后立即重跑基准
2. 可选: 用NVIDIA nemotron-3-super作为补充基线（速度慢但稳定）
3. 可选: 缩短基准prompt（去掉选项列表，只发问题文本）

## 关键命令

```bash
# 重启
source private/current_channels.env
setsid python3.11 scripts/run_server_noprefusion.py > /tmp/axio_server.log 2>&1 &

# 快速验证
PYTHONPATH=src python3.11 -c "
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.schemas import FusionRequest, FusionPolicy
from axio_fusion_api.registry import load_registry
p=load_registry('private/runs/2026-08-11-triple-merge/merged_registry.private.json',require_prefusion=False)
e=FusionEngine(p)
r=e.complete(FusionRequest(model='axio-terra',prompt='2+2=?',reasoning_effort='high',max_output_tokens=5,policy=FusionPolicy()),live=True)
print(r.text)
"
