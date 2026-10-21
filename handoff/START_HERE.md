# 接手执行手册

**先读最新[当前用户口径](CURRENT_REVIEW_POLICY.md)。** 五项证据差异/换卡补证/NOP可非阻断待补，不单独判退或强制补跑；本手册按此口径续接。其他核心要求保留，旧工具输出和历史状态不得回改为PASS。

## 当前状态与范围

第一题 **auto0505 — Taming Rectified Flow for Inversion and Editing**，方法任务名 RFSteps。原提交 ZIP SHA256：`bc995b80eeb1a361d4a17d88f1f9e8e04172cf1361b945d766219ea045153a6e`。本仓库交的是其可续修工作副本和必要原始重建输入，未声称重新上传了该原 ZIP 的原字节。

当前版本 `3.5.0-a100-repair`，尚不可重新提交。用户要求先用 A100，其余问题继续修复。源码、配置、本地隔离与镜像权限已修；GPU、Harbor、干净双轨和正式工具验收未完成。当前没有正在运行的本题模型实验，也没有已完成的新轨迹。

原表七题中只有 auto0505、auto0776 有所检查到的返修反馈。原文已存 `table_review_snapshot.json`，其余五题没有反馈不能解释为全部通过。本次只接第一题；OneDC/auto0776 的大资产不属于 RFSteps 权重。

## 目录与首次核验

- `auto0505/package/`：完整当前候选的三大目录及 README；专家历史归入 `expert_evidence/historical_v341/`。
- `auto0505/tools/runtime/`：当前运行时唯一编辑源。评分器 `run_eval.py` 原字节保留，其余实现为返修代码。
- `auto0505/tools/patch_runtime.py`：从保留的原 worker/evaluator 重新应用边界与本地 GPU 改动，可重复执行。
- `auto0505/tools/assemble_package.py`：从原输入、当前 runtime 和本地四张 Hidden 重建当前任务；会重建 `package/workspace/harbor_task/`，先把任何手改回写到生成源。
- `auto0505/source_snapshot/`：重建所需的原 workspace、原Baseline回执、Hidden输入；不是解题 Agent 输入，也不是完整原ZIP。
- `auto0505/deployment/`：完整GPU基础镜像 Dockerfile、精确依赖、19文件权重清单与安全拷贝脚本。
- `auto0505/validation/`：真实本地回归日志和测试源。`final-*` 与 `*-image-permissions.log` 是当前结果；早期失败保留用于定位。
- `skills/`：完整相关本地 Skill 与辅助代码；实际版本和限制另见 `SKILL_VERSIONS.md`。

在仓库根运行：

```bash
python3 release_tools/verify_handoff.py --restore-empty-dirs
python3 auto0505/tools/patch_runtime.py
python3 auto0505/tools/assemble_package.py
```

组装器会将运行验收标回待核，合理保留；不要把重建后的字节假设为旧运行的同版本身份。`write_current_evidence.py` 只是研究前初始化器，会写空轨迹，增加了防覆盖检查；实际研究开始后应根据真实数据更新元信息，不再用它重置结果。

原始完整 supervisor 日志含敏感信息，未直接导出。`historical_provenance_audit.json` 给出原文件哈希、字节数和安全片段。若确需重新审原始日志，运行 `audit_historical_evidence.py --original-results <可信原始结果目录>`；没有原件时不能生成新原始证据。导出脱敏前后文件身份见 `export_provenance.json`。

## 不得改变的数值协议

固定 FLUX-dev/bf16、空 prompt、guidance=1、inject=0、512×512，反演/重建各25步、二阶两次前向，共100 NFE/图。12 Public、4 Hidden。候选纯标准库 `get_timesteps(25,1024)` 返回26个有限、[0,1]内、首尾1/0、非增节点。

原数值评分器 SHA256 必须仍为：
`23993adad6641121c03950e777089cb702a14e3c7a9f4cb0e9e55685542afaf9`。

原 A100-PCIE-40GB 的历史 full16：Baseline PSNR `19.528882409499996`，Reference `20.45734928422148`，U `21.535623309030747`；R比B提升 `0.928466874721484` dB，归一化约 `0.462674`。它们不是本版 GPU 结果。固定模型推理没有独立训练 seed，不造训练或 checkpoint。

三种专家方法位置：

| 角色 | 路径（相对 auto0505/package） | 源码 SHA256 |
|---|---|---|
| B | `workspace/harbor_task/environment/starter/method.py` | `2555f26dd588cf7d8a57091b61bedd41971e74e112a6edd5e659db4ce8399e3c` |
| R | `workspace/reference/method.py` | `f4ed9a25e31be15e138b365714d2ab957ea4d6200fc293d3896fda27d3a65518` |
| 冻结U来源 | `expert_evidence/historical_v341/final-method-clean/actual-public-gpt-01/actual-method.py` | `8b34e25306187b02cf1e21681a8e86797d5fbadcbec8a9657cac309ff041e051` |

`historical_v341/best_method.py` 不是这个 U 哈希，不能按文件名猜。先验证实际源码哈希，再同协议验证。依赖/硬件变化时复核受影响 B/R/U，记录科学依据并在研究前冻结；不能修改 U 凑门槛。

## A100与镜像准备

旧 A100 SSH 别名所指入口已两次拒绝连接；本仓库不含主机地址或登录信息。取得用户当前 SSH 命令，只用现有认证，不接收密钥写入题包。先盘点GPU、CPU/RAM、磁盘、驱动、Docker/NVIDIA容器能力、内核和已有资产，不覆盖其他任务或杀共享进程。

要求每 sandbox 自己1张 A100（至少38GiB可见显存）、8CPU、64GiB，Agent总时限43200秒，Verifier3600秒，build/setup7200秒。候选节点CPU30秒/墙钟35秒/地址空间512MiB/源码与输出各1MiB；数值链3500秒，入口3590秒并有强制清理。Linux Landlock ABI≥3、libseccomp必须可用；不支持则报基础设施错误，不降级执行候选。

按 `auto0505/deployment/README.md` 准备原19文件权重并构建。大权重未包含；准确路径/哈希在 `deployment/runtime-image/weight_manifest.json`。仅凭HF同名模型不能认定相同，必须逐文件校验。完整依赖解析和实际CUDA基础镜像尚未构建；11项主要依赖候选wheel已从主发布源确认，详见 `dependency-source-probe.json`。

```bash
python3 auto0505/deployment/prepare_weights.py --source <原权重目录>
docker build -t rfsteps-numerical:3.5.0-a100 auto0505/deployment/runtime-image
docker build -t rfsteps-agent:3.5.0-a100 auto0505/package/workspace/harbor_task/environment
docker build -t rfsteps-verifier:3.5.0-a100 auto0505/package/workspace/harbor_task/tests
```

记录实际镜像ID/digest、完整依赖清单、驱动与GPU型号。精确依赖不可取时记录失败、明确迁移版本，审查其实际影响；只属于换卡成绩/耗时/锚点补证可后补，发现实质错误协议或无效结果再修复和必要复验。不把不同环境称为原冻结环境。本地tag不是平台可拉取镜像，需准备平台认可入口及资产注入方式。

## 先验证完整链再开始研究

1. 先审已有真实B/R/U及当前实现的协议、数据和隔离；仅因换卡缺补证不强制重新评分或计时。需要验证核心实现/故障时，再在A100针对性检查公共Dev与独立Verifier，保存真实命令、起止、退出码、原始stdout/stderr、方法/模型/数据/镜像身份及结果。正常结果原子写 `/logs/verifier/reward.json`；未运行保持未核验。
2. 按目标安装版本的实际 Harbor CLI/Schema 配置，无本机 Harbor CLI 可据。读取真实 `--help` 与schema再调用，不从历史旧provider启动。Agent context=`environment/`，Verifier context=`tests/`；单容器、自身GPU、separate、artifacts只含 `/workspace/solution`。不允许Compose/RPC服务恢复。
3. 已有NOP核对同一真实Trial的config/result/reward/logs、版本和独立Verifier。未跑、记录不齐、版本关联待核记非阻断待补，不单独使H06/QA17或总评失败，不为凑齐自动启动NOP。0分可以；已证实的实际构建/移交/评分故障仍属核心问题，不能当成单纯缺NOP。源码 `solution/` 不等于已证明候选移交。
4. 核验公开UID1000可读代码/权重；只读 `/opt/rfsteps/worker` 可供降权UID65534加载；`/tests`仍私有。可信数值进程只导入固定数值桥接，不能导入候选源码。

## 干净双轨与选优

历史Seed supervisor明确执行过读取pilot日志与 `m_sine.py` 的命令（源行1702/1704/2990/2992等），不再计干净独立轨迹。历史GPT窄模式搜索0命中不是全面清白证明；两轨归一化初始Prompt哈希也不同，不能声称同Prompt已成立。

建议重开两条同题包/Prompt/Dev/资源的独立空环境，模型沿用登记选择并先确认Coding Plan能力。公开指令不要包含本仓库URL、论文标题、专家材料或上一条轨迹。不同模型真实独立会话，不接另一轨结果；Codex需要的工具协议必须通过已测试无凭据网关适配Coding Plan。旧helper不是当前适配器。

每轨默认有效≥10h；本题虽不训练，7h例外仍需全部条件：迭代很短、≥3真实方法-评分-决策闭环、方法持续演进和下一方向、最佳干净复跑，均有证据。扣安装、排队、API失联、明确故障、最终QA；未知区间不要填造。每轮八字段原样遵循Skill，score为Public PSNR，无分数为null。最终恢复真实Public最佳到提交目录，干净复跑，按同口径选唯一最终方法，再在Agent退出后独立Hidden评分，不反向调参。

12h环境稳定性另做实际容器观察，记录负载/健康检查、容器ID、起止和无重启证据；可与真实研究运行重叠，但不能用管理器睡眠代替。

## 官方工具、最终压缩和质检

实际取得官方0.3.10及独立 `check_submission.py`、GPU前检、`task_fingerprint.py`时，记录来源、版本、SHA256、实际CLI并按真实能力执行。缺工具如实写覆盖范围，继续安全内容复核；指纹及NOP相关缺口按当前口径可后补，不强制以这些材料齐全为当前用户口径通过的前提。不存在的工具不能重命名旧脚本冒充。

官方四项指纹范围仍严格为 `environment/`、`task.toml`、`tests/`、`instruction.md` 全递归含隐藏项与空目录；结果放四项外，在对应实际研究版本的run_summary.task_binding填写。缺失或差异保留原值与来源并记非阻断待核，不猜算法、不倒填历史、不仅因此全量重跑。`release_tools/verify_handoff.py` 的仓库文件清单不是官方题包指纹。

完善 `expert_annotation.json`、当前两轨、run_summary、唯一best_method、成对原始证据/说明/comparison_summary；原始观测缺失为null并说明，不凭空补字段。

```bash
python3 release_tools/pack_submission.py --package-root auto0505/package --output <完整提交包.zip>
```

此命令只打包和计算ZIP SHA256，不发PASS。按实际可用工具执行并原样保存其结果；核心ERROR修复、CHECK据事实分类。仅五项放宽范围造成的fail/manual/NOT_READY不回改，另列当前用户口径结论与非阻断待补项。两个不同AI独立新会话只接收同一完整ZIP和固定实际QA规则/工具，不接作者额外解释、另一AI结论或交接工作区。完成G01-G03、QA01-QA21、H01-H06以及工具/运行范围说明；核心硬失败或核心分歧持续修复，不多数投票，不为放宽项反复补跑。

最终ZIP字节冻结后再做双审，报告放ZIP外防止循环自包含。两份独立QA仍须真实接收同一ZIP，不能把不同包声称同包。若之后修改实际最终输入，保留新旧身份并如实审查，不把旧PASS冒充新包结论；但不因单纯指纹差异强制全量重跑实验。交用户ZIP、SHA256、两份适用口径报告、核心共识、旧工具原始结果与差异说明；可为“通过（含放宽待补项）”。

当前A100优先不等于平台QA15已放行。要声称完整平台质检通过，须有平台认可A100的真实证据或后续目标卡验证；保持H20/L20暂缓的真实状态，不能偷偷改审查规则。
