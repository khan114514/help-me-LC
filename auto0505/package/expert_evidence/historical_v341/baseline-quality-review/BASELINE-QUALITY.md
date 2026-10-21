# Baseline 合理性检查

总评：**在已提供材料范围内合理**。本节审查正式 Baseline 和本次配对条件；完整交付仍为 INCOMPLETE。

Starter、正式 Baseline 和主评分 B 均绑定未改的 `time_shift(mu)` 方法（源码 SHA `2555f26d…99e3c`）。新原生 Harbor NOP 得到 B=19.528882409499996。Reference 为本次冻结前已确定的 sine（`f4ed9a25…65518`），仅在独立 Verifier 的私有 live solution 中替换；模型 Actor 和冻结 Task 保持 Starter。

| 条件 | Baseline | Reference |
|---|---|---|
| 实际评分 | full16，Public12+Hidden4 | 相同资产哈希 |
| 协议 | flux-dev、bf16、512×512、空 prompt、guidance1、inject0 | 精确相同 |
| 预算 | 25 steps，双向每步两次调用，100 NFE/图 | 精确相同 |
| 实际 scoring_seconds | 308.06073663569987 | 309.2353660771623 |
| PSNR | 19.528882409499996 | 20.45734928422148 |
| 未裁剪 reward | 0 | 0.46267401782591483 |
| 训练/checkpoint | 无训练，冻结预训练权重 | 相同权重哈希 |

| 项目 | 状态 | 证据与理由 |
|---|---|---|
| B01 代表性 | 通过 | Starter 公式与冻结 Repo `sampling.py:46–72` 的默认形式一致，限定于声明协议；未观察到以弱化实现制造差距。 |
| B02 实现与训练健全 | 通过 | 这是确定性推理任务。NOP 实际完整运行成功，固定权重、worker、scorer、环境均核准，没有把故障或少训练冒充 Baseline。 |
| B03 公平预算 | 通过 | 两份原始回执的协议、资产、权重、环境、CPU affinity、Repo、anchors、评分程序和 A100 UUID 逐项一致。 |
| B04 配置与搜索公平 | 通过 | Baseline 采用固定的序列长 mu 公式，没有仅作用于 Baseline 的异常参数；Reference 在本次实跑前已固定。本次没有追加选择试验。历史 pilot 全部选择过程未重新认证。 |
| B05 随机性公平 | 不适用 | 无训练 seed；本次是单组真实配对，不将重复 checkpoint 表述为多个 seed。 |
| B06 基本锚点 | 通过 | 实际未改 Starter 就是正式 B，实跑值与冻结 B 精确一致。历史 uniform 等 sanity 不冒充本次独立运行。 |
| B07 改进归因 | 通过 | 仅节点分配从 time_shift 改为 sine，其他控制项原始回执完全一致。正式模型研究收益仍待两轨与最终选优。 |
| B08 选择披露 | 通过 | 源码和本节披露角色、公式、预算、无训练、精度与场景限制；历史 Reference 选择未经本次重新认证。 |

主张 → 实际完整评分差 0.928466874721483 dB → 相同冻结条件的两份原始回执 → 当前配对提升成立。此数是 dB 差，不把 dB 的相对百分比当作像素误差下降。

关键红旗：未发现直接红旗。专家退回说明：两轨各 ≥10h、12h 稳定性、最终 Public 选优、清洁重跑和 full16、最终 QA/ZIP 仍待完成；Baseline 合理不能使整包通过。

边界：本任务冻结 Python float 节点列表，不宣称与原 Torch FP32 `get_schedule` 逐 bit 等价。历史 Reference pilot 的全部选择过程未重新认证，不能宣称本次证明其没有历史 Hidden 选优。评分使用未裁剪值，`score_clipped` 仅展示。

证据：`../root-paired-full16-acceptance.json` 和两份 actual manifest。Root 独立复验 NOP 44 文件与 Reference 49 文件；本节只读，没有新增模型、容器或 GPU 运行。
