# 独立只读复核附记

输入仅为 `rfsteps-package-v3.4.1-preview-20261005T015301.zip`；SHA256 `00e7c6b67671be377c32b0f28fe8972827ce3767ad7f291d6fb6b1d7825a8ccd`。本会话配置模型为 OpenAI `gpt-6-sol`，底层不可变 snapshot 未提供，记录为 `unknown-snapshot`；真实子会话身份 `/historical-root/final_zip_qa_b`。没有执行提交代码、Docker、GPU 或安装脚本；ZIP 内说明、旧验收与日志均作为待核材料。

## 三门及原始值

- G01：题面和 `tests/candidate_worker.py` 允许提交 `get_timesteps` 的确定性算法，guard限制输出节点与安全边界。固定25步/方向、100 NFE、冻结模型；Baseline 是 `environment/starter/method.py` 的 FLUX time_shift，Reference 是 `workspace/reference/method.py` 的正弦分配。算法接口可表达密度/分段/节点交换等策略，非纯常量搜索。
- G02：非训练任务。B01官方默认方法有任务适用性；B02 NOP 正常得到16图PSNR；B03 双方同16图、25步及100 NFE；B04 参数固定没有只对B施加异常配置的直接证据；B05 当前正式确定性单pair、无筛差seed证据；B06 anchors 同时列 uniform 等 sanity 值，其中正式B高于 uniform；B07 当前B/R Trial的任务哈希、GPU、评分器及预算一致；B08 专家材料披露角色与来源。这八项在**已交材料范围内**支持合理Baseline，不等于独立复跑。
- G03：从 `optimization_evidence/baseline_runs/actual_v341/harbor-job/.../result.json` 与对应 Reference result/reward 复算，B=19.528882409499996，R=20.45734928422148，Δ=0.928466874721483 dB。`tests/anchors.json` 的 U=21.535623309030747，归一化 0.46267401782591483，位于 [0.15,0.8]。一个固定full16协议配对，样本标准差不适用。anchors 注明 U 是较早模型候选实测、v3事后修订锚点；当前 v3.4.1 NOP/Reference 已按此冻结版本新跑，报告不把较早测量说成当前版本新跑。

## 时间、人类更正与 collector

`expert_evidence/TIME-ACCOUNTING-AMENDMENT.json` 引述直接人类更正：实际研究过程只扣网络不可连接时段，历史工作不因修复/迁移清零。此口径不同于包内 `02-optimization-surface.md` 的旧“仅GPU有效评分秒数≥36000”声明，也不同于技能默认的两条各10h、特例各7h及排除其他阻塞的条款。作为本ZIP证据，该更正支持不以GPU评分秒数单独判时长失败；它不能推导出精确净秒数。`time-reconciliation/TIME-RECONCILIATION.json` 的两条 `exact_lifetime_net_seconds` 均为 null，Oct3旧时区和断网扣除不闭环；Seed 9.2474h首末完成跨度与Oct4 200.01秒之和是算术参考，不能直接当最终有效时长。collector 的 `runtime_candidates=[]`，现版QA16强制引用候选的 `duration_evidence`。语义未确认时长与 collector 输入不兼容共同使 QA16 保持 manual；不把人类“时间肯定够”改写成伪造的 PASS。

## Harbor与格式兼容

当前 `task.toml` 为 `[task] name="autoresearch/rfsteps"`、`version="3.4.1"` 且显式 separate，双Dockerfile和绝对 `/tests/test.sh`、`/workspace/solution/method.py`、顶层 artifacts 源路径相互对齐。当前 NOP Trial 的 `config.json` 为 agent nop，`result.json` 为 separate、无异常、有结束时间和 reward 0；同目录 reward.json 与之相同。正式 worker 在私有宿主验证四张 Hidden 图像哈希并仅为 formal 建立 private split，现有 NOP/Reference记录均报告16图；ZIP未携带私有图像字节，迁移需外部注入与UDS/provider部署。

collector 的 H06 身份函数只取 TOML 顶层 `name` 与 `metadata.name`，遗漏了实际的 `[task].name`。因此它把 Trial `task_name="autoresearch/rfsteps"` 和运行时目录名误作“different task”；包内未找到同时显式写三个名称的映射文本。本次将 H06 记为 manual，并明确这是工具兼容性问题，不是原始NOP失败。目标Harbor原生版本亦未锁定，包内 `runtime_support/DEPLOYMENT-REQUIREMENTS.md` 说明外部平台部署及 task_id 尚未验证；H02/H03/QA17因此不能给可移植性PASS。

两条规范轨迹各102/47轮且八字段齐全；Codex末轮 `status="INFRASTRUCTURE_ERROR"`、`score=null`、`retained_best=false`，`failure_reason` 说明SSH/RPC失败，语义是失败轮。collector只认识常用状态，将此自定义状态自动降 QA18/QA21 为 manual；需要加状态映射或将其明确映射为 failed，同时保留原始错误码/原因。`trajectory-source-map.json` 是来源映射，不是第三条轨迹；Seed formal04 原始文件空也不等于当前规范Seed轨迹为空。

12h 容器稳定性为独立平台要求，不替代两轨研究时间。`stability-existing-samples-20261004T173039Z.json` 两容器最大可核约19080秒，`FINAL-ACCEPTANCE.json` 明写 `container_12h_passed=false`；因此截至该ZIP版本，12h证据未完成。

## 修复与验收材料

1. 时间：按人类更正口径，提供ZIP内可解析的两条逐区间时间、重叠去重、网络中断扣除和时区依据，得出精确净秒数；让collector能生成并引用各轨迹原始 `runtime_candidates[].evidence`。若完整账本仍无法重建，保留未完成而非补造数值。
2. Collector：在任务身份判定读取 `[task].name`；允许将 `INFRASTRUCTURE_ERROR` 作为有null分数与失败原因的失败状态；不要用旧格式检查器把来源映射文件当轨迹。修复后用**相同ZIP**重生成新的自检目录核对H06/QA18/QA21，不回改本首轮报告。
3. 部署：固定Harbor/provider版本及外部A100、公开/正式UDS、私有Hidden注入和模型权重的注册/挂载方式；交目标平台双镜像构建、移交与NOP/独立Verifier原始记录。若发布验收含12h稳定性，补完整两容器≥43200秒的同一身份连续样本与异常状态记录。
