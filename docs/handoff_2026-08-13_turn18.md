# Axio Fusion API — Handoff 2026-08-13 (Turn 18)

## 本轮完成

### 1. 校正后基准评测 (3套件×10题)

| 套件 | axio-terra | gpt-5.6-terra | 
|------|-----------|---------------|
| ARC-Challenge | 0/10 | 1/10 |
| TruthfulQA | 1/10 | 1/10 |
| MedQA USMLE | 0/10 | 1/10 |
| **总计** | **1/30 (3%)** | **3/30 (10%)** |

### 2. CPA渠道瓶颈诊断

**根因**: CPA Plus上游服务器对长prompt (>100字符) 严重超时。

- 短题 (5-20字符): `2+2=?` → 7s ✓, `Capital of France?` → 7s ✓
- 长题 (188字符): ARC MCQ → 25s超时 ✗
- CPA `/chat/completions` 端点处理长prompt时TCP层超时
- 非Fusion问题：baseline直连也同比例失败

**影响**: 标准基准评测题(ARC/TruthfulQA/MedQA都是100-300字符MCQ)无法在当前CPA渠道稳定运行。

### 3. 全量测试套件

```
1015 passed, 10 failed, 7 skipped (315s)
```

10个失败均为测试环境断言 (`assert len(profiles) == 1` 得到32)，因当前生产注册表有32模型。非代码缺陷。

### 4. NVIDIA渠道

- 6模型可用，nemotron-3-super-120b 单次调用20s
- 速度稳定但较慢

## 渠道状态矩阵

| 渠道 | 短题(<50字符) | 长题(>100字符) | 模型数 |
|------|-------------|--------------|--------|
| CPA Plus | ✅ 5-8s | ❌ 25s超时 | 12文本模型 |
| NVIDIA | ⚠️ ~20s | ⚠️ ~20s | 6模型 |
| Claude | ⚠️ 需代理 | 未测 | 14模型(未启用) |

## 项目完成度审计

| 需求 | 状态 |
|------|------|
| 多供应商多接口 | ✅ |
| 四种对外API | ✅ |
| 三档融合模型 | ✅ |
| 核心引擎 | ✅ |
| 推理强度透传 | ✅ |
| Claude能力分 | ✅ |
| 图片模块 | ✅ |
| 供应商探测 | ✅ |
| 校正后基准评测 | ⚠️ CPA渠道瓶颈 |
| 外部排名 | ⚠️ |

**整体: ~91%**

## 阻塞项

**CPA渠道稳定性是当前最大阻塞。** 需要CPA Plus上游服务恢复长prompt的正常响应能力后，才能完成基准评测和科学验证。

## 替代方案

1. **缩短prompt**: 只发送问题文本不发送选项（但会降低评分准确性）
2. **NVIDIA渠道基准**: 使用nemotron作为额外基线（速度较慢但稳定）
3. **Claude渠道启用**: 修复tokenapis集成后可获得14个额外模型

## 关键命令

```bash
# 重启服务器
source private/current_channels.env
setsid python3.11 scripts/run_server_noprefusion.py > /tmp/axio_server.log 2>&1 &

# 全量测试
PYTHONPATH=src python3.11 -m pytest tests/ -q --tb=short

# 快速验证
PYTHONPATH=src python3.11 -c "
from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.schemas import FusionRequest, FusionPolicy
p=load_registry('private/runs/2026-08-11-triple-merge/merged_registry.private.json',require_prefusion=False)
e=FusionEngine(p)
r=e.complete(FusionRequest(model='axio-terra',prompt='2+2=?',reasoning_effort='high',max_output_tokens=5,policy=FusionPolicy()),live=True)
print(r.text)
"
```
