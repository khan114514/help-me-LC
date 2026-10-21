# 论文与选题来源（当前工作版本）

来源为 Jiangshan Wang 等的 [Taming Rectified Flow for Inversion and Editing](https://proceedings.mlr.press/v267/wang25ce.html)，ICML 2025，PMLR 267:64044–64058；发布页链接的[作者代码](https://github.com/wangjiangshan0725/RF-Solver-Edit)与现有冻结实现相对应。2026-10-04 已重新核对这两个一手来源。论文提出通过高阶 ODE 近似改善反演精度，无需额外训练。

本任务以现有 RF-Solver 二阶实现为固定骨干，研究时间步分配。当前协议使用 flux-dev bf16，非早期 schnell 假设；具体计算与数据协议以冻结 Task 为准。论文背景不等于本任务的完整论文复现结论。

实际资源可行性由当前 A100 完整 Baseline/Reference 评分及真实 Harbor/Docker NOP 证明。模型轨道和12小时稳定性仍未完成。尚未接入权威题库查重接口，查重状态保留 UNKNOWN；平台 task_id 保留 null。

旧选题稿原字节和哈希留在专家私有审计目录，研究时长信用为0；当前位置的旧稿不再用于定义当前评分、轨迹或环境。
