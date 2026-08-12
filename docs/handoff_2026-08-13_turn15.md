# Axio Fusion API — Handoff 2026-08-13 (Turn 15)

## 本轮完成

### 1. Claude模型能力分先验注入 (CRITICAL)

**问题**: 14个Claude模型能力分全部错误 — claude-fable-5全轴0.35(无先验)，opus/sonnet系列仅0.76(通用模糊匹配)

**根因分析**:
- `_apply_model_name_capability_priors` 中 `"sonnet"`/`"opus"` 关键词匹配到Claude模型，但只给0.76
- `_normalize_capabilities` 中raw overlay使用直接赋值 `caps[axis] = _score01(number)`，当raw JSON硬编码了0.35时覆盖了正确的先验分

**修复**:
1. `registry.py:_apply_model_name_capability_priors` 新增Claude模型家族先验:
   - claude-fable-5 ≈ gpt-5.6-sol: code/math/logic 0.90, science/critique/structured 0.86
   - claude-opus-5 > gpt-5.6-terra: science/math/logic/daily 0.91, structured/critique 0.89
   - claude-sonnet-5 > gpt-5.6-luna: science/daily/multilingual/code 0.89, structured/long/logic 0.87
   - opus-4系列 0.82-0.86, sonnet-4系列 0.78-0.84, haiku 0.66-0.76
2. `_normalize_capabilities` overlay改为 `max(caps[axis], _score01(number))` 保留先验分

**验证**:
```
claude-opus-5           avg=0.824  (top: science 0.91, math 0.91, logic 0.91)
claude-sonnet-5         avg=0.811  (top: science 0.89, multilingual 0.89, code 0.89)
claude-fable-5          avg=0.797  (top: code 0.90, math 0.90, logic 0.90)
gpt-5.6-sol             avg=0.854  (top: code 0.90, math 0.90, logic 0.90)
gpt-5.6-terra           avg=0.862  (top: science 0.90, math 0.90, logic 0.90)
gpt-5.6-luna            avg=0.856  (top: science 0.88, code 0.88, math 0.88)
```

### 2. 代码提交
- Commit: `5b88c55` — Claude模型能力分先验注入 + 修复capability归一化覆盖问题
- 已推送至 `git@github.com:Surakahn/axio_fusion_api.git`
- 新增 `scripts/bench_pair.py` (校正后配对基准评测器)

### 3. 服务器重启
- 旧进程已停止，新进程加载新代码
- 32模型, 3 provider, 4 API格式
- Claude模型14个(anthropic格式), NVIDIA 6个(chat), CPA 12个(chat+responses)

## 服务器状态

```
status: ready
model_count: 32
api_format_counts: {anthropic: 14, chat/completions: 11, responses: 7}
judge_candidates: 19
```

## 已知问题

1. **CPA渠道间歇故障**: provider branches全部失败(非代码问题，CPA端502/限流)
2. **代理依赖**: 所有请求需通过 `http://127.0.0.1:10808` 
3. **推理强度参数**: 实现已完善，四种API格式正确透传
4. **旧基准结果无效**: `run_suite_bench.py` bug导致baseline走Axio API路由回axio-terra
5. **bench_pair.py**: 校正后评测器已创建，结果带正确的provider直连

## 完成审计 (更新)

| 需求 | 状态 | 证据 |
|------|------|------|
| 多供应商多接口 | ✅ | 3 providers, 4 upstream formats |
| 四种对外接口 | ✅ | 12/12跨格式一致性 |
| 三档融合模型 | ✅ | fast/terra/pro全部运行 |
| 核心引擎 | ✅ | Router+Orchestrator+Judge+Synthesizer |
| 供应商探测 | ✅ | pre-fusion + reasoning probe |
| Claude能力分 | ✅ | 14模型按用户评估注入先验 |
| 推理强度透传 | ✅ | 四种格式正确映射 |
| 旧基准结果 | ⚠️ | 校正后结果待跑 |
| 外部排名认证 | ⚠️ | preliminary only |
| 图片模块 | ⚠️ | 基础完成, 需增强 |

**整体完成度: ~90%**

## 下一步

1. **校正后基准评测**: 用 `bench_pair.py` 跑 axio-terra/pro/fast vs 对应基线
2. **CPA稳定性**: 持续监控，添加更健壮的retry
3. **图片模块增强**: prompt composer + editing workflow
4. **外部排名**: 冻结正式排名
5. **完整14套件**: 扩展基准覆盖

## 关键命令

```bash
# 重启服务器
kill $(pgrep -f run_server_noprefusion); sleep 2
source private/current_channels.env
setsid python3.11 scripts/run_server_noprefusion.py > /tmp/axio_server.log 2>&1 &

# 校正后基准 (单套件)
python3.11 scripts/bench_pair.py arc_challenge --n 15 --pairs terra \
  --output /tmp/bench_pair_arc.json

# 运行所有test
PYTHONPATH=src python3.11 -m pytest tests/ -q --tb=short

# 验证
curl -s http://127.0.0.1:18900/health | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'])"
```
