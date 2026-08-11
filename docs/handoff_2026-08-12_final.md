# Axio Fusion API — Handoff 2026-08-12 (最终)

## 整体进度

### ✅ 已完成
| 模块 | 状态 | 详情 |
|------|------|------|
| 服务器 | ✅ | 18900端口, 24模型, 3 Provider |
| 四种API格式 | ✅ | Chat/Responses/Anthropic/Gemini |
| 三档融合模型 | ✅ | axio-fast/terra/pro |
| 推理强度五档 | ✅ | low→max, 三种wire格式透传 |
| 图片模块 | ✅ | gpt-image-2 gen+edit, 隔离于文本Fusion |
| Claude渠道 | ✅ | tokenapis, /v1/messages原生格式 |
| 重试退避 | ✅ | 指数退避 1s/2s/4s/8s |
| 流量控制 | ✅ | min_request_interval + stagger |
| L1语法 | ✅ | 48文件 0失败 |
| L2导入 | ✅ | 8核心模块全部OK |
| L3测试 | ✅ | 463 passed, 1 known issue |
| axio-terra评测 | ✅ | 43题 ~88% 正确率 |

### ⚠️ 进行中
| 项目 | 状态 |
|------|------|
| axio-fast评测 | 历史13/15(87%), 需批量异步评测 |
| axio-pro评测 | 首次成功, 后续需CPA稳定 |
| 单模型基线对比 | terra vs terra打平83%, 样本不足 |

### ❌ 阻塞
| 项目 | 原因 |
|------|------|
| 完整14套件基准 | CPA间歇502/限流 |
| 外部排名冻结 | 需2个独立排名来源覆盖完整池 |
| 科学验证优越性 | 依赖外部排名 + 完整基准 |

## 架构总结

```
axio_fusion_api/
├── src/axio_fusion_api/
│   ├── server.py          # HTTP服务器 (4种API格式)
│   ├── registry.py        # 模型注册表 + 能力分
│   ├── router.py          # 路由规划 + 延迟预算
│   ├── orchestrator.py    # Fusion引擎 + 并行执行
│   ├── providers.py       # Provider客户端 + 重试/流量控制
│   ├── schemas.py         # 推理强度 + 数据契约
│   ├── compat.py          # API格式兼容层
│   └── calibration.py     # 能力校准 + 推理传输探测
├── scripts/               # 启动/评测脚本
├── docs/                  # 规划/审计/API参考/handoff
├── private/               # 凭证/注册表 (git忽略)
└── tests/                 # 463 tests
```

## 关键设计决策
1. **Claude渠道**: 使用原生/v1/messages（非chat），支持thinking推理
2. **推理强度**: 五档low→max，xhigh→max唯一向上兼容
3. **流量控制**: 100ms间隔+重试退避，避免CPA限流
4. **图片隔离**: gpt-image-2独立于文本Fusion
5. **辅助模型过滤**: codex-auto-review, gpt-image-*被排除

## 收敛路径状态
| 门禁 | 状态 |
|------|------|
| Pre-Fusion筛查 | r43终端(10模型), r44注册(部分) |
| 排名转换 | 阻塞(无完整覆盖源) |
| 基线冻结 | 阻塞 |
| 官方工具导入 | 阻塞 |
| 独立live campaign | 阻塞 |
| Claim审计 | 阻塞 |

