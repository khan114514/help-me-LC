# 当前题包验收与交付

## 交付前完成表

所有“通过”必须有真实路径、版本、时间、命令/退出、原始证据和可复算关联。模板、配置意图、源码静态存在或旧A10结果均不能替代目标环境实测。

| 项 | 通过所需材料 |
|---|---|
| 原六评分日志 | B/R各3次原始run.log、result/metrics、实际seed0、方法/镜像关联、逐图24与两个split码率门、进程/退出依据 |
| Baseline选择 | τ=0.6来源、既有扫描原件/实际选择集/双方预算；缺失如实说明，新增检查独立日期 |
| 目标部署 | Agent/Verifier各单容器H20/L20、实际GPU日志、无不支持的Compose/存储/网络依赖、候选受限执行与实际移交 |
| 资源/可比性 | 完整单轮时间/CPU/RAM/显存、码率cap余量、数值容差、B/R/U同split比较及真实硬件标签 |
| 两轨研究 | 原指定模型/档位、独立Public闭环、每轨审定有效时间≥10h或完整7h例外、失败/缺号实录 |
| 轨迹 | 每轮恰八字段；本轮真实Public指标；无分null；CLI失败与评分回执分开解释；审计字段旁表 |
| 唯一最终方法 | Public质量门和归一化选择依据，best_method仅最终代码/入口/必要配置，方法SHA，目标环境干净Public复验 |
| expert_annotation | 题型/方向/优化面/指标方向、同split同协议B/R/U、基本隔离声明；不塞日志和自称官方PASS |
| 四项任务指纹 | 使用真实发布脚本；hash_profile、task_content_sha256；environment/、task.toml、tests/、instruction.md全递归；历史完整快照与新版本分别绑定 |
| 当前NOP | 最终版本、separate模式，同一次Trial的config.json/result.json/reward/log，实际候选移交和Verifier出分 |
| 稳定性 | 目标环境真实≥12h健康记录和实际负载/检查；研究时长分开 |
| 官方前检 | 真实0.3.10包及独立格式/GPU脚本版本SHA，ERROR修复，CHECK补证/平台确认；未取得就待补 |
| 独立双AI | 两种AI、不同干净会话、同一完整ZIP SHA、两份真实PASS、无未闭环分歧的共识 |

官方四项指纹包含目录里的隐藏文件、空目录、模型/缓存/输出，不能按类型跳过。计算结果放四项之外。Git提交SHA、单文件SHA、历史PACKAGE_FILE_MANIFEST、Harbor原task_checksum和最终ZIP SHA均不是该官方指纹的替代品。没有原历史完整输入快照就无法补造历史官方绑定；明确缺口及可恢复范围，必要时对新版本完成合法研究与证据，不能把旧结果改标。

## 完整task ZIP布局

```text
workspace/
  harbor_task/
    instruction.md
    task.toml
    environment/
    tests/
  reference/
expert_evidence/
  专家作业说明文档.md
  expert_annotation.json
  run_summary.json
  trajectory_codex.json
  trajectory_seed.json
  best_method/
  ...必要复验/NOP/版本/时间/稳定性证据
optimization_evidence/
  训练证据说明.md
  baseline_runs/.../{result.json,run.log}
  reference_runs/.../{result.json,run.log}
  comparison_summary.json
```

本题为固定模型推理量化优化，训练材料标NOT_APPLICABLE，不造训练/空checkpoint目录。超大权重按平台认可不可变资产/安全入口交付，列准确来源、版本、大小、哈希和加载步骤；“在作者电脑/网盘里”不能冒充平台可加载资产。

先用 `tools/package_task.py --root <最终三目录父目录> --out <新的task.zip>` 生成完整候选。此工具只做结构/路径/JSON/八字段等基础检查与压缩；它不生成官方指纹、不运行GPU、不宣称QA通过。

冻结task ZIP后再做两个独立QA。QA报告自身不用塞进已审ZIP造成自包含重打包；用户交付可以是：

```text
delivery/
  auto0776_task.zip          # 与两份QA审过的文件字节相同
  auto0776_task.zip.sha256
  qa_a/                     # 全报告和原始独立会话依据
  qa_b/
  qa_consensus.json
  CHANGELOG.md
```

如压成delivery.zip，另列其SHA；task.zip的SHA不变。用户直接收到完整task.zip与可读报告，不能只给补丁、交接仓库或路径。

## 失败处理与结论

每项问题写“事实/定位→不满足原因→实际修复→复验材料”。任何硬失败、未支持的必需工具、目标环境未验或两QA分歧未闭环都保持NOT READY；继续可做的修复。不要修改QA阈值/版本字符串、弱化Baseline/cap/U、补造时长/日志、用Hidden迭代、仅把失败字段改成true。

当前source的score_clipped、旧PASS字样、旧time_policy、旧schema/collect/网络注释等均须按实际调用判断并修正文档/新实现；不因为出现某个字段就无依据判错，也不能忽视真正生效的违规行为。

隐私检查覆盖最终task ZIP、QA附件、轨迹、交接和manifest；不传凭据、作者home/SSH端点、签名下载URL或内部访问令牌。保留原始证据的私有备份；对确需投影的文字字段给原始/导出SHA及变更清单，不把日志改写摘要。
