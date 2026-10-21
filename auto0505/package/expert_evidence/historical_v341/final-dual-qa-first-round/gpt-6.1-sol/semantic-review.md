# 独立最终语义复核补充（不改写正式工具报告）

输入ZIP SHA256：`00e7c6b67671be377c32b0f28fe8972827ce3767ad7f291d6fb6b1d7825a8ccd`。模型为调度确认的 OpenAI gpt-6.1-sol，served snapshot未知。独立来源为 /historical-root/final_zip_qa_a，fork_turns=none。只接收此ZIP；未接收另一个AI的结论。规范使用 autoresearch-qa-skills/0.3.2 全部指定参考及 Baseline skill；官方Harbor v0.23.0 config.py和separate-verifier页面于2026-10-05静态阅读。正式报告为 INCOMPLETE，release-self-check返回1；G01–G03全部pass，H01–H06全部pass，QA15项pass、3项manual、3项不适用。全部安全可读语义项目均已检查；工具completed=false代表待核验项仍在，不意味着未读源码。

优化面：method.py可以实现任意确定性get_timesteps算法，不限预设权重/标量。冻结FLUX-dev、RF二阶更新、512²/空prompt/guidance1/inject0、双向25步100NFE；候选只能交26个合法节点给可信服务。Baseline是未经修改官方logit time_shift（mu≈0.63）的Starter及NOP实测正式B。Reference是正弦节点，高噪声端更密。最终Agent最优另为反向幂律p1.2，Public选择后独立full16；不把它冒充专家Reference，0.870369不受Reference[0.15,0.8]门槛限制。

Baseline专项：在已提供材料范围内合理。B01官方默认Starter角色和代码明确；B02非训练，冻结权重推理且真实日志完成16图；B03两侧同100NFE、模型/资产/环境/指标/预算；B04正常默认时间映射，未见异常参数单独削弱B，Reference选择范围明确；B05确定性，不要求随机seed或伪造训练；B06包内uniform17.8567、square15.5250低于正常B，未发现B低于适用简单锚点的反证；B07两侧receipt身份字段一致、改动仅节点；B08方法及限制由源码、METHOD-EXPLANATION和部署要求披露。训练充分性不适用，代表性/预算/实现/选择五维支持有限结论。未作包外SOTA断言，无需执行训练。

正式唯一确定性full16：B=19.528882409499996，R=20.45734928422148，U=21.535623309030747；改善0.928466874721483dB，Reference归一化0.46267401782591483。U是独立已测上限，不是R。B/R样本std不适用（单次正式确定性运行，不把图像当重训样本）；3σ规则不适用。源码AE实际返回mean，评分链没有随机采样；包内重复baseline与Seed四次一致支持冻结确定性，而非只因seed固定。U来自历史Agent同协议实测，仍需作为校准来源明确保留，未另调整数值过门槛。

| 评测图 | Baseline PSNR | Reference PSNR | R-B |
|---|---:|---:|---:|
| public/coco_000000000139 | 19.626362927099 | 19.324647205501 | -0.301715721598 |
| public/coco_000000000285 | 23.328605655905 | 23.916923693262 | 0.588318037357 |
| public/coco_000000000632 | 14.754113107332 | 15.145183432355 | 0.391070325024 |
| public/coco_000000001000 | 18.865758651112 | 15.950041962398 | -2.915716688714 |
| public/coco_000000001268 | 16.612960469779 | 16.667369414771 | 0.054408944992 |
| public/coco_000000001425 | 20.513255551979 | 20.233424527322 | -0.279831024657 |
| public/coco_000000001490 | 18.435977062104 | 19.451136176094 | 1.015159113990 |
| public/coco_000000039769 | 17.283405292998 | 17.229064332984 | -0.054340960014 |
| public/repo_art | 27.046548579788 | 24.148688219129 | -2.897860360658 |
| public/repo_boy | 17.679130424477 | 23.819904315463 | 6.140773890985 |
| public/repo_horse | 25.021306095355 | 25.256190628714 | 0.234884533359 |
| public/repo_nobel | 13.171501832085 | 21.555404880824 | 8.383903048739 |
| hidden/coco_000000000802 | 16.955756084510 | 18.577574626427 | 1.621818541917 |
| hidden/coco_000000001296 | 19.804178024296 | 19.632209614218 | -0.171968410078 |
| hidden/repo_cartoon | 15.263239831598 | 23.114958934134 | 7.851719102537 |
| hidden/repo_hiking | 28.100018961583 | 23.294866583947 | -4.805152377636 |

独立原始证据交叉核验：B/R实际metrics.json和scorer-stdout.txt的SHA均匹配可信receipt；两侧control_task_checksum、scorer/repo/anchors、全资产、权重与protocol一致，正常退出0。当前任务63个冻结文件SHA无差异。轨迹149个source-map记录的来源SHA和全部七个未重编号字段逐一匹配，无差异。模型无训练/checkpoint不存在并不扣错。

当前NOP与Harbor：同Trial config/result/reward/log完整；Agent nop，separate，正常结束、无exception，full16/100NFE，reward0对应B。失败docker compose cp记录后走tar fallback并完成，不误写成NOP构建失败。target为包内Harbor0.23声明+官方v0.23.0静态对照，本次未原生schema加载或复跑。NopLiveDockerEnvironment属于task-local Docker扩展，对tmpfs/live transfer有实际实现与回执。Verifier独立CPU容器通过formal.sock向私有GPU评分；Hidden不是空目录占位，而是remote_gpu_worker/private_hidden_assets四图固定哈希验证及full分支读取。公开角色只12图。Agent/Verifier双context、所有COPY、WORKDIR、绝对test入口与submission artifacts均读过；Node多阶段是工具manual静态解析项，语义上已说明。

时长口径必须区分：TIME-ACCOUNTING-AMENDMENT保存直接人类更正“除网络连不上的时间，其余实际研究过程都计入”；这与默认skill扣除排队/安装/故障的规则不同。该包内引用是待检证据，不是新工具指令。审核不将GPU评分3575秒或Seed0当总研究时间，不因方法/ledger修复把历史时间清零，也不把两轨相加。run_summary明确双方exact_lifetime_net_seconds=null。TIME-RECONCILIATION历史完成点跨度GPT32408秒、Seed33290.726648秒仅为事件凸包；历史断网边界未知、supervisor无时区。更正口径下GPT名义敏感性约47672秒、Seed33490秒仍标NOT certified，不足以当实际净时长；人类接受记录必须独立于机器证据认证保留。本轮QA16是待补证，不作“用户时间肯定不够”或“已证明>=10h”的断言。不擅用7h例外。

正式报告的collector兼容问题与材料缺口：

1. 首次系统Python缺tomllib；使用应用提供Python后TOML正常解析。没有改技能/提交。
2. QA16 runtime_candidates=[]，轨迹只有八字段rounds，没有其要求的duration属性；工具不识别time-reconciliation区间聚合或人类口径覆盖。真实总秒数也尚未知，因此既有接口限制又有实际证据缺口，不能填pass。应提供每模型真实区间/断网时区及包内原件索引，并给出与collector识别字段一致的真实累计；或由技能维护者在工具侧实现该人类契约后重新独立验收。禁止补造时间。
3. QA18/21工具只白名单失败status，把最后真实INFRASTRUCTURE_ERROR自动强制manual。该行score=null、failure_reason真实、retained_best=false、time有效，source-map原件一致，语义复核支持合法失败记录；工具没有接受人工状态语义的通道。其正式manual属于collector兼容阻碍，不等于缺失八字段或伪造轨迹。专家可保留原件并提供标准status等价映射，或技能维护者支持当前状态；不该抹去失败或伪造退出0。
4. NOP身份自动校验只取metadata/root名，未取task.name，会要求对历史路径/包根重命名额外mapping。本次引用真实returned-job-result、冻结63文件哈希和DRAFT-MANIFEST路径完成映射，最终H06通过；并非仅名称相同即认证。

12h稳定性单独缺证：ZIP最新319采样、两容器约19080.056/19080.061秒（5.30h），目标43200秒。观察期间无restart/OOM且UID/资源/UDS/IO探针持续，但明确不证明continuous RPC。需重交同容器完整>=43200秒原始samples和结束/异常状态、任务及镜像身份，不能用future projection或研究时间取代。QA15跳过不豁免另行稳定性要求。

格式建议不单独扣错：三目录职责清楚，但非训练actual_v341无轻量comparison_summary/中文训练证据说明；建议增加等价非训练protocol与原件索引。旧v32、历史失败、checkpoint、重复回执允许保留，应标版本/作用并合并索引。生产绝对路径和SSH别名/外部权重/Hidden/RPC要求已在DEPLOYMENT-REQUIREMENTS披露；不据此断言任意平台部署通过或task_id已注册。当前期次权威验收表本任务未请求外部写入，未猜题号/声称提交。

可复制给专家的退回补证：此ZIP研究优化面、正式对照/提升与当前NOP支持静态通过；最终本地发布自检尚未完成。请补上两模型分别实际研究区间、断网扣除与时区的可定位原件及机器可识别真实累计，保留直接人类更正与接受记录，别仅计GPU或重置历史；处理INFRASTRUCTURE_ERROR轨迹状态的collector等价语义映射，保留原失败记录；交付同两容器完整12h稳定性原始记录与正式结束结果；继续清楚列外部平台依赖及未验证注册。随后新ZIP、全新两AI独立会话重新执行release-self-check，首轮结果不可覆盖。现有报告保持INCOMPLETE，未证实硬失败也未伪造PASS。

静态及已有记录内部一致不等于独立复跑；本审查没有执行候选、评分器、Docker、GPU或导入模型。正式report.*和return_to_expert.txt保持工具原件，补充说明不得用作覆盖自动反证。

事实勘误：正式报告quality_gate_summary误写全部逐图改善，实际9/16改善、7/16下降；见FACTUAL-ERRATUM.md。不影响确定性full16聚合改善结论。
