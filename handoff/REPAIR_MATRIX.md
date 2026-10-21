# 返修矩阵

以 `table_review_snapshot.json` 中2026-10-21二次质检为原反馈，以真实执行与源码为验收依据。下表是当前状态，不是PASS报告。

| 项目 | 原问题 / 新发现 | 已做修改 | 接手验收 |
|---|---|---|---|
| QA05 | storage_mb/no-network内场不支持；旧候选可用底层调用越界读文件/建socket | 删除不支持字段；Landlock+seccomp、降权、CPU/AS/输出/文件限额、安全普通文件打开；超时组清理；无隔离时关闭执行 | A100真实镜像内重跑有效候选与越界/超时/失败测试；联网环境题目仍成立 |
| QA15 | 原A100不是教程目标卡，缺目标环境资源依据 | 用户当前指定A100；1GPU/8CPU/64GiB，真实旧卡标签保留 | 实测当前完整B/R/U耗时/内存/数值；平台A100豁免或H20/L20后续证据仍不可假定 |
| QA17/H02/H03 | 两侧Compose、外部GPU RPC、移交/镜像路径依赖旧provider | 单容器各自自身GPU；专用Docker context；separate；artifacts=[/workspace/solution]；公开Dev与私有tests分离 | 目标Harbor真实解析、镜像可用、移交与独立Verifier；同版本同Trial的NOP四件套 |
| 新发现：权限 | 原提取文件模式600，正式/tests私有后降权worker不能加载入口，公开用户也可能不可读 | 公共只读worker独立放/opt/rfsteps/worker；公开材料可读不可写；/tests保持root私有；启动失败归基础设施 | 已用两份实际Dockerfile和CPU基础镜像验证；完整CUDA镜像仍需复验 |
| QA16 | 起止包络不等于扣除故障/安装/队列后的真实有效时长 | 旧用户时间接受保留历史，不转换为当前合格秒数；当前空轨迹/null明确未运行 | 每轨10h，或全部满足7h例外；独立起止/扣除表与真实实验片段 |
| QA18 | 模型/档位/同Prompt/独立起点待核；Seed曾称Reference/pilot | 原始日志审出Seed真实读pilot日志与正弦参考源码；保留原哈希与安全片段 | 补两条干净独立轨，逐轮恰八字段，实际模型/档位/Dev/资源、最终best与干净复验 |
| QA21 | run_summary缺官方四项指纹 | task_binding结构准备，profile已填但hash=null，未猜官方算法 | 用真实task_fingerprint.py计算对应版本；当前不能倒填历史证明 |
| B05 | 固定模型固定图像，没有独立训练seed | 文档明确确定性成对推理，不冒充训练或多seed | 一组成对完整真实记录，确认全16图、100NFE、同协议/资产；必要确定性复验 |
| 原始日志与回执 | 新本地后端需真实GPU链；显卡查询失败可能抛出未分类异常 | 资产hash、协议/桥接身份/归一化/有限性检查，原始stdout/stderr和原子receipt；显卡查询失败明确基础设施错误 | A100完整有效与失败路径均有可审回执，无正常分数时不填0 |
| 终稿 | 当前仍有NOT_RUN、空轨迹、缺官方工具/新NOP/稳定性 | 当前状态明确NOT_READY，旧PASS隔离历史 | 完整三目录ZIP，同一字节哈希双独立PASS及无分歧共识，才作为完成交付 |

本地现有结果：候选9项×root/普通UID各一次，合成评分协议9项，真实Dockerfile的两种权限场景2项，共29次用例执行。使用Linux aarch64 Docker及CPU测试基础镜像，不含FLUX/CUDA评分，不计研究时长或12h稳定性。

编辑入口：`auto0505/tools/runtime/`；生成入口：`patch_runtime.py`、`assemble_package.py`。禁止只改生成副本导致下次重建丢失。`run_eval.py` 保持冻结；如必须迁移数值协议，应明确新版本、同协议B/R/U和所有受影响证据，不能继续宣称原字节等价。
