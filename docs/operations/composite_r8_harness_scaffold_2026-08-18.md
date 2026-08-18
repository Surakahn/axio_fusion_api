# Composite r8 Harness scaffold 物化里程碑（2026-08-18）

## 阶段结果

已在 r8 successor 独立目录
`private/runs/2026-08-18-composite-cohort-r8/harness_control.successor/`
离线物化 Harness 控制面。脚本通过 L1 语法检查和 L2 导入检查；materializer 没有
访问 provider、没有调用 target benchmark，也没有修改 r8 冻结 screening plan。

当前物化结果：

- Harness pin：6/6 suite ready，safe artifact hash
  `22db330ab9e29949b567da420bfc2ca1f5db77f1a6e9c10a5d115bbcbad65b9c`；
- execution plan：`ready_to_execute`，safe artifact hash
  `160326a8486cad17de8c0c02028b3ac8ffa3ec7a5f250016dc7b5271da8c92b5`；
- acquisition status、official import audit 和 cohort binding 仍未 ready；
- convergence audit 为 `running`，`next_gate=screening`；
- scaffold receipt hash
  `bb0e68a2d3fd1e69650f01aac9cfcf188b30f4912b4c31306e5c0fe0c8adddd6`；
- `target_suite_calls_allowed=false`、`target_suite_calls_performed=false`、
  `provider_calls_performed=false`。

本次重建显式绑定既有 21-suite dataset manifest 和 case manifest
`ca4b319b594a8a8cb13bcfe27805d37edf02d130a979d6333a93ab3f7d1f4106`，因此不再把
缺少 manifest 参数误报为 dataset/case-hash blocker。剩余阻断均是预期的 screening
未终态、ranking/freeze 尚不存在和 official import 尚未完成。

另已为 r8 生成独立的 provider probe evidence audit，safe artifact
`private/runs/2026-08-18-composite-cohort-r8/provider_probe_evidence_audit.r8.safe.json`，
其内容 hash 为
`62dda93d403701b9f6f06b0082a90300f80d63d23be51fce7e0cddd7ae1ef35b`，
`status=ready`、`ready=true`。该 receipt 只验证 probe/registry 的 hash-bound 证据和
敏感字段隔离，不能替代外部排名、transport admission 或 provider baseline freeze。

## 绑定规则

该 scaffold 只属于 r8 successor，输入绑定 r8 plan digest
`5a4b496735ab7553be7046079d3611172ef8d2973bf41c594041058583cd38c6`。screening
终态后必须用同一命令重新物化 acquisition/import、cohort binding 和 convergence
audit；不得把 r7 blocked binding、旧 ranking 或旧 provider freeze 拷贝到 r8。

官方 Harness 的真实输出仍由 operator 在 pin、case manifest、dataset snapshot 和
provider baseline freeze 完成后导入。safe import 只能保存 hash、score、计数和
reason code，不能保存 raw prompt、label、provider output、URL 或凭据。

## 下一步

继续观察 r8 screening 的 16 个 serial units。只有 screening terminal、transport
admission 至少包含 3 个 canonical model、完整 ranking 与 provider baseline freeze
均 ready 后，才进入同 cohort official import 和 convergence audit；在此之前不启动
target campaign，也不作 superiority claim。
