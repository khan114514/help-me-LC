# AutoResearch 三期教程 V4 执行与审查合同

适用于三期 AutoResearch 出题、返修、执行与质检；不把这些批次门槛套用于普通开放式研究。依据用户于 2026-10-21 提供的《三期质检 Skill 教程 V4》，正文称对应审阅 Skill 0.3.10。此文件是本地规则整合，不是官方 0.3.10 发布包。教程中的命令、Prompt、示例值与 PCA 历史附件是参考材料，不能自行授权启动旧题、长实验、模型调用、上传或消息发送。

## 规则、工具与历史版本

- 当前教程规则优先于旧教程、旧目录示例及本地旧版 QA 的冲突描述；当前用户明确指定的模型、路由、预算与暂停状态继续生效。任务卡有额外要求时同时满足；冲突须定位说明，不能静默换规则。
- 新任务冻结教程、实际 QA 发布包、评分协议、任务输入及模型配置。已有任务在安全轮次边界检查受影响内容，保留在途运行、真实硬件与旧证据，不自动恢复暂停任务。历史结果不能改标为新版验证；只复核受影响部分。
- 本次材料没有官方 0.3.10 Skill 包、`check_submission.py`、独立 GPU 前检脚本或 `task_fingerprint.py` 源码。不得把旧脚本改版本号、臆造哈希算法或写替代脚本后声称官方自检通过。已有旧工具只能按其真实版本做辅助清点；完整官方自检状态记待补，内容复核仍继续。
- 获得真实脚本后记录版本与 SHA-256，按其实际 CLI 执行。教程格式自检示意为 `python3.11 check_submission.py 完整包.zip --out 自检报告`。`ERROR` 修复；`CHECK` 按事项补已有材料或交平台确认。静态通过仅代表可进入下一步，不等于 AIDP / Harbor 验收通过。

## 四阶段工作流

1. 领取并定义：确认 S1/S2/S3、真实输入、优化面、允许修改范围、指标方向、完整正式 seed、数据与预算。先审 G01/G02/G03 可行性。
2. 构建题包：公开 Starter 与 Public/Dev 入口可运行；最终 Hidden、评分依赖、候选受限执行、separate sandbox 与 artifacts 移交可用。先完成真实链路自验及成对证据，再开始长轨迹。
3. 独立自迭代：两组实际模型使用同 Prompt、同题包、同 Public/Dev 协议和资源，分别从空输出目录开始；不能互看另一轨、Reference、Hidden 或汇总专家证据。每轮公开评分，运行结束后才正式 Hidden 评分。
4. 选优交付：以同一 Public/Dev 口径的质量门和归一化聚合值选唯一最终方法，干净快照复跑；补齐同版本 NOP、四项指纹与格式/GPU 检查，重新交完整 ZIP，记录 ZIP SHA-256。

## G01/G02/G03 与评分

- **G01**：题面、parser/guard 和实际调用链允许目标、采样/更新规则、模型模块或推理策略等方法更新。只有学习率、轮数、loss/ridge 权重等数字搜索不接收。接口开放而 Reference 只调参时，补非纯调参方向与空间证据，不能仅凭 diff 判整题失败。
- **G02**：默认 Baseline 为可执行的未改 Starter；Scaffold 可不给 method，但专家侧须另交合理朴素 Baseline、源码/入口及 B 锚点映射。检查实际 steps/tokens/样本量、曲线、停止原因、checkpoint、选择与调参机会、数据/资源和全部 seed。简单、经典、年代较旧或未完全收敛不能单独判退。已批准 debug 题须有健康对照，不能把已知故障分差当一般方法收益。
- 训练效率研究按同计算、时间或 token 预算比较；epochs、容量或架构若为合法研究变量，不机械要求相等。只有直接证据证明不公平削弱或无代表性差对照才不通过；判断旧方法不合理须有任务适配、预算可行、可核验的更强常用锚点。
- **G03**：全部正式成对运行有效、质量门通过、真实正向改善；声明的 Public/Dev 自验协议上 Reference 归一化分数在 `[0.15,0.8]`，正式 Hidden 由平台复核。确定性评估不套统一 5% 或重复训练要求，仍满足全部正式成对协议及预先声明容差。
- 随机评估使用 Baseline 的 `n−1` 样本标准差 `σ_B`。Maximize 要求 `mean(R)−mean(B) ≥ 3σ_B`；minimize 要求 `mean(B)−mean(R) ≥ 3σ_B`。3–5σ 可接受并建议复核，≥5σ 为强证据；到 U 的剩余空间原则上也 ≥3σ。未规定重复数时至少各 3 次，高波动至少 5 次；正式 seed 五个就交五组，不抽样或挑最好一次。
- 同一方法跨 seed 除种子外代码与配置不变；声明种子必须进入实际随机过程，不能被硬编码覆盖。重复训练需每次真实参数更新；固定模型随机评测可复用同一训练后模型，但不能冒充独立训练。候选与 B/R 使用同 seed 集、重复数和聚合规则。
- B/R 使用同协议全部有效正式运行的聚合值；B 不能另设弱锚点。Maximize：`(x−B)/(U−B)`；minimize：`(B−x)/(B−U)`。U 为有依据的预计可达上限，无可靠估计时才用数学 ceiling，且 U≠B。连续、单调、不裁剪，不在 R 处改斜率，不用调整 U 制造达标；超过 U 可 >1。
- 成功保留有限标量及原始指标。非作弊 Hard Gate 为 −1，只表示无效，不参与正常排序；格式、超时、资源超限和基础设施错误分别分类，未出分为 null，不统一伪装成 0 或 −1。Hidden 访问、评分篡改或伪造反映隔离失败，须返修环境。

## Harbor 目录与公开/私有边界

```text
workspace/
  harbor_task/
    instruction.md
    task.toml
    environment/           # Agent 构建 context；公开 Starter、Dev 与依赖
    tests/                 # 私有评分；入口 test.sh，内部模块按题需要组织
  reference/               # 专家参考解，Agent 不可见
expert_evidence/
  专家作业说明文档.md
  expert_annotation.json
  run_summary.json
  trajectory_codex.json
  trajectory_seed.json
  best_method/             # 唯一最终方法源码、入口与必要配置
optimization_evidence/
  训练证据说明.md
  baseline_runs/seed_<真实seed>/{result.json,run.log}
  reference_runs/seed_<真实seed>/{result.json,run.log}
  comparison_summary.json
```

- 标准任务根为 `workspace/harbor_task/`。不把完整根目录、专家包或优化证据整体 COPY/挂载给 Agent。源码 Starter 放 `environment/starter/`，初始化只读 `/workspace/starter` 和可写 `/workspace/solution`；仓库根 `solution/` 可为 Harbor Oracle，非必交起点。
- Agent 每轮必须有可见、可调用的 Public/Dev 数据与评分入口。若旧 `tests/` 混放公开迭代评分，先拆公开部分到 `environment/public_eval/` 或等价公开位置；不能笼统禁止 Agent 接触一切评分实现。公开 Dev 不用于训练；允许训练的数据另行声明。
- `starter/`、`public_eval/`、`hidden_assets/`、`method.py + solve.sh` 是内部布局示例；可按真实优化面采用等价目录、入口或多文件接口，不造无用途的 train/model 目录或 submission JSON。明确标准运行入口及禁令仍必须遵守。
- 题面覆盖 Goal、Task Setting、Objective and Metrics、Allowed Scope、Hard Boundaries、Submission Instructions、Workflow & Iteration、Completion Criteria 八部分或语义等价内容。写真实接口、文件/Schema、命令、约束执行、种子规则及有效提升阈值。无须统一强写重复次数或 Agent 总时长；禁止论文标题、arXiv ID、解法仓库、参考方法或本机路径泄露，除非题目明确允许。

## 独立 Verifier 与候选移交

- `[verifier] environment_mode = "separate"`，Solver 与 Verifier 必须不同 sandbox。**可以复用 Solver 镜像，不强制双镜像或双 Dockerfile。** 按目标 Harbor 实际版本核对镜像选择：显式 Verifier 镜像 → `tests/Dockerfile` → Solver 镜像/构建。
- Agent Docker context 是 `environment/`。专用 Verifier 构建 context 是 `tests/`，私有预置 `/tests/test.sh`、grader、资产与依赖；复用 Solver 镜像时由 Harbor 向新的 Verifier sandbox 上传 `tests/`，评分依赖须预装在复用镜像。不可继承 Agent 临时装包、缓存或未移交文件；禁止越界 COPY。
- 统一示例为顶层 `artifacts = ["/workspace/solution"]`。可采用真实任务合同的等价路径，须同步题面、配置、构建、入口与移交。只传候选代码、必需 checkpoint 和配置，不传 `/logs`、reward、评分器、Reference 或整个工作区。可信侧核验符号链接、大小及冻结面。
- 每轮：改方法 → Agent 环境 Public/Dev 评分 → 保留/回退 → 下一轮。结束前把经复测最佳候选和评分必需产物完整恢复到提交目录。只备份 best_method 不够。
- Agent 结束后由 Harbor 移交候选到 Verifier 同一绝对路径，执行 `bash /tests/test.sh`。Verifier 运行可信评分和受限候选，不启动第二个 Coding Agent；不要求每轮独立容器或评分服务。
- Hidden 对训练与非训练题都必需；目录名不限，可授权预置、按固定私有规则生成或安全注入。查实际材料、准备方式与调用链，空目录或一句“平台注入”不算完成。
- 候选在 Verifier 内仍不可信。可信 grader 可读私有数据；候选仅接收允许输入，不可读标签/私有 Reference，不可改评分原始参照、`/tests` 或 reward。只分两个容器、或直接将候选 import 到高权限 grader，不能证明隔离。冻结面校验/恢复，清理候选预写结果，由可信侧原子写最终分数。
- reward 必须写到 `/logs/verifier/reward.txt` 的单个有限数值，或 `reward.json` 的数值键值对象（如 `{"reward": 0.2}`），不能只 stdout/pytest。记录目标版本实跑命令与平台结果位置。最终 Hidden 不反馈给本次 Agent 调参，也不回填每轮 Hidden 分数。

## 内场配置、GPU 与时间（QA05/QA15/QA17）

- GPU 题实际内场仅用 H20（prefer）或 L20；CPU 题保持 0 GPU。`gpu_types` 已允许 H20/L20 时，不因同时列出其他候选卡型而退回；核对实际调度卡型与日志，不能只看列表。
- 完整单轮 ≤7200 秒、≤8 张 H20/L20、≤64 核 CPU，覆盖必要训练、重载、评分。专家说明引用现有日志，注明计时范围、实测设备和目标资源估算依据。示例 16 CPU/64GB/1GPU/10MiB 非全题固定配置。
- 换卡先调整题目、镜像和配置，复核受影响分数、耗时、B/R 与评分锚点，保留真实新旧硬件；旧卡成绩不得改标为新卡实测，仅重跑受影响部分。不能满足单轮目标时提交原因和判据供平台复核，不能静默增资源。
- 当前内场不声明 `storage_mb`、禁网或网络白名单；本批不接收以磁盘限额为研究/评分必要条件的题。warning 后继续或联网降级不算约束生效。需按实际联网条件调整题面、环境和评分；普通依赖下载不自动违规。
- Agent、Verifier 每个 sandbox 各用单容器，直接使用本 sandbox 分配的 GPU。正式执行不依赖 Compose；`environment/` 与 `tests/` 直属禁止 `docker-compose.yaml`、`docker-compose.yml`、`compose.yaml`、`compose.yml`，已有 Dockerfile 或预构建镜像也不例外。
- Agent 不得申请/调度额外 GPU sandbox、工作容器或远程计算服务；禁止 DinD、宿主 Docker socket 启同级容器及换工具绕过。独立 Verifier 由框架在最终评分阶段创建并直接评分，不再转交额外工作容器。普通进程/子进程编译、训练、推理、调试正常允许。
- 镜像构建、sandbox 创建和资源分配是平台准备阶段；Agent 解题不是部署阶段。普通 AutoDL 容器实例无 Docker 能力，可算法开发与公开 Dev，但不能冒充完整 Harbor 自验。
- 分别记录并落实 Agent 总时限、Verifier 阶段时限、单次候选程序时限，以及 build/setup 超时和完整单轮预算。超时机制应能中断受限工作，不能阻塞返回后才检查。容器稳定 ≥12h 为独立环境目标，不替代双轨有效时长；静态质检不能声称压力测试完成。

## 双轨、八字段与证据（QA16/QA18）

- 两组模型可调整，模型名称不是固定判退项；用户指定模型继续遵守，不擅自替换。记录实际 runtime/model/推理配置，默认各模型支持的最高档，用户已有明确档位则遵守。文件名可沿用 codex/seed，也接受可追溯等价命名，不绑定具体模型，更不能将 Seed 模型名称与训练 seed 混淆。
- 各自有效迭代 ≥10h，不相加。各 ≥7h 仅当完全不训练/微调、迭代很短、各 ≥3 轮真实方法→评分→决策闭环、方法持续演进且有下一方向、最佳方法干净复跑成功，并在专家说明/run_summary 写完整例外依据。失败方法可计真实闭环；只排环境故障不算。不恢复旧的“12h 且 >15轮”门槛，也不自创单轮分钟阈值。
- 有效时长按起止与扣除区间核算；正常训练和分析可计，排队、安装、明确故障、API 失联与长阻塞扣除，重叠只计一次，最终复验另列。已有记录足够时不另强制独立计时器或全量原始调用日志。
- 每轮恰用八字段：`round`、`policy_name`、`method_summary`、`status`、`score`、`failure_reason`、`retained_best`、`time`。round 从 1 递增；摘要 1–3 句忠实于生效改动及结果；成功 status 为 ok、failure_reason 为 null；失败按实际类型、score 未出分为 null；最佳标记布尔；完成时间 `YYYY-MM-DD HH:mm:ss`，说明时区。
- score 记录对应 Public/Dev 评分器真实输出的原始指标/已声明代理指标，不混最终 Hidden；选优按质量门与归一化聚合值。JSONL 整理为 `{"rounds":[...]}`。模型与有效时长写 run_summary/专家说明，不加每轮命令、seed、模型哈希等必填项。
- 轨迹审方法、分数、失败和最佳标记；sessions 提供则一并审，无 sessions 不单独退回。逐证据区分违规、评分故障与待核问题，并定位轮次/分数。未生效修改不算实验，多因素变化不能把全部收益归单因素，细小/少量重复差值不能证明普遍更优。
- `best_method/` 只含唯一最终方法代码、入口与必要配置，无历史快照、checkpoint 或私有证据。训练型评分所需模型按候选提交合同移交；超限走平台认可不可变资产并记录加载方式。正式 B/R 模型仍放 optimization_evidence 对应记录中。

## 成对证据与摘要

- 必需：`训练证据说明.md`、全部正式 seed 两组 `result.json`/原始 `run.log`、`comparison_summary.json`。result 记录真实状态、角色、seed、方法/依赖哈希、协议、训练设置、命令/时间/退出码、指标/质量门、产物索引；未观察字段 null 并解释，不能反推编造。保留 warning、失败和差结果，不把日志改成摘要。
- 训练型保存每个协议要求训练的真实 checkpoint、`model/artifact.json`（格式/大小/SHA-256/来源/重载结论）和独立干净进程重载复评分的 `reload.log`；固定模型随机评测明确共用模型。非训练不造训练或空 model/，标 NOT_APPLICABLE。大模型/受限数据走平台认可不可变资产/安全入口，列提供者、准确入口、操作、版本、大小和哈希。
- 汇总逐 seed 值、两组均值和 n−1 样本标准差、方向、显著性、质量门、模型完整性及相对提交包根目录的源路径。不再硬性要求 data_manifest.json、experiment_plan.json、surface_validation.json、surface_diff.patch、integrity_manifest.json、train_config.yaml、ablation/ 或额外 runs/ 层；必要指纹可留公开 manifest/result。可选消融不能替成对主证据。
- `expert_annotation.json` 仅题目类型/研究方向/优化面/指标方向、同 split 同协议的 B/R/U 和基本隔离声明；不塞运行日志、审核通过或官方 Hidden 结论。`run_summary.json` 记实际模型、有效时长、轮数与节奏、例外、自验状态和 task_binding，未完成不能填 true。

## 四项指纹、NOP 与完整包（QA21）

- `run_summary.json.task_binding` 必有 `hash_profile`、`task_content_sha256`。教程示例 profile 为 `harbor-task-inputs-v1`；用真实发布脚本计算，不凭名称猜算法。范围严格为 `environment/`、`task.toml`、`tests/`、`instruction.md`，目录全量递归，包括隐藏文件、空目录及其中任何模型/缓存/输出，不按类型排除。
- 指纹计算结果/报告放四项之外，避免自包含。各轨可记录实际哈希；缺字段待补，哈希不一致先核版本。源码/配置/数据/设备/评分与对应结果可追溯，不给历史结果补造当前哈希。题包指纹与最终 ZIP SHA-256 是不同对象。
- 最终版本、separate 配置在目标 Harbor 执行一次 Agent 类型 nop 的 Trial，确认 Trial 正常结束、候选移交和独立 Verifier 实际运行、有效 reward。构建/移交/评分故障修复后重做；NOP 的 0 分本身不是失败。
- 提交**同一次 Trial** 的 `config.json`、`result.json`、reward.txt/json 与运行日志到 expert_evidence，并在专家说明关联任务版本、命令、结果。已有平台同版本完整记录可引用，无须重跑；不额外强制 NOP 哈希字段。
- 返修先做无需模型的格式/GPU 自检，再上传包含三大顶层目录的完整包，不只补丁/改动文件。Dockerfile 不是完全缺环境定义，但入 AIDP 前须有平台可用镜像；不强制双 Dockerfile。
- 最终待上传 ZIP 再查一次，保存报告中 SHA-256，上传同一版本。脚本不上传、不确认云端权限；分享/平台保存结果需实际核对。大模型与受限资产继续不可变安全入口，不因完整包要求违规内嵌。

## 报告边界与 PCA 教学例

报告顺序：优化面 → Baseline 方法 → Reference 方法和全部正式成对跑分 → G01/G02/G03 → 两轨、格式和既有 21 项。每个问题写“事实及文件位置 → 不满足原因 → 具体修改 → 重交验收材料”。QA07/08 查题面泄露；QA15 查有依据资源估算；QA18 查轨迹及已交 sessions；QA21 查四项指纹，不能混作八字段检查。

文件存在、脚本成功和静态一致不能替代内容复核或目标环境运行。正式 Hidden、物理隔离、镜像/GPU/移交/reward 与平台稳定性由目标环境验证；专家不伪造平台日志或审核通过。既有双 AI 独立新会话、同 ZIP 与共识规则继续遵守，报告必须标实际工具版本，不将旧版 PASS 冒充 0.3.10。

PCA 附件仅教目录、公开 Dev 与结束后独立评分：沿用 pca CLI、CPU 0 GPU、私有参考副本均可。其旧 network/storage 配置、评分截断/分段、快速参考锚点与失败=0 不符合当前统一要求；需改造重标定。空轨迹、NOT_RUN、待补 best_method 与仅本机 smoke 均不是正式成对、长程、Docker/Harbor/Hidden 验收。不要复制这些缺口为模板，亦不为技能更新而自动运行或修改该教学包。

所有 Doubao/Ark/Seed 调用遵守用户 Coding Plan：可信主控从 `${LOCAL_HOME}/.config/ark/current.json` 安全读取最新凭据，base_url 为 `https://ark.cn-beijing.volces.com/api/coding/v3`、Chat Completions 为 `/chat/completions`；不回退按量 `/api/v3`，不将 key 放日志、包、仓库或 Actor。Codex 所需协议通过已验证无凭据网关适配；套餐不支持指定模型先报告，不用普通聊天冒充 Coding Agent 轨迹。
