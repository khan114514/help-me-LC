# rfsteps NOP 收尾 · Codex 交接（2026-10-04 11:20）

> 一句话状态：NOP Trial 已在官方 harbor v0.23.0 全链路实跑完成，发现并已修复提交包 3 个依赖缺陷（v3.2）；最终 reward=0.0 系 A10 显存物理不足（基础设施障碍，非题目缺陷）。**剩余工作：把 v3.2 与 NOP 证据同步到 GitHub 提交仓库、重建提交 zip、写 QA 附录、更新 handoff。**

## 1. 权威身份

| 项 | 值 |
|---|---|
| 任务 | AutoResearch 第 1 题 rfsteps（RF-Solver 时间步 schedule 优化，arXiv:2411.04746） |
| 提交仓库 | REDACTED:khan114514/Taming-Rectified-Flow-for-Inversion-and-Editing.git（公开，HEAD 曾验证 b38a6d0） |
| Mac 工作区 | ${AUTHOR_HOME}/WorkBuddy/2026-10-03-00-43-02/ |
| 提交包 | rfsteps-package/workspace/harbor_task（**已是 v3.2**：requirements.txt + invisible-watermark/requests；Dockerfile + libgl1 libglib2.0-0 libxcb1） |
| NOP 证据 | rfsteps-nop/NOP-REPORT.md + rfsteps-nop/evidence/jobs/（7 个 job，关键 run5=2026-10-04__11-06-57） |
| QA 报告 | rfsteps-qa-report/（v2 全 PASS，H06=not_run 待 NOP 证据补录） |
| GPU VM | 腾讯云 ins-lz0iv9re，118.195.251.134，A10 22GiB，Ubuntu 22.04，150G 盘，`ssh root@118.195.251.134`（Mac 密钥已授权） |
| fj02b | `ssh gpuhome-fj02b`（gpuhome A100 实例，权重源 /historical-root/rivermind-data/weights/） |

## 2. NOP 已验证结论（详见 rfsteps-nop/NOP-REPORT.md）

- 官方 harbor v0.23.0 + run-side 三件套（rfsteps-nop/{gpu-overlay.yaml, gpu_docker_env.py}）跑通：构建→nop agent→tests 上传→test.sh→run_eval.py→reward.json 原子写→harness 收集。task.toml 未做任何修改。
- run5 trial `harbor_task__KZSk6k2`：exception_info=null、finished_at 完整、verifier_result.rewards 与 reward.json 一致（{"reward":0.0}）、verifier_environment_mode="shared"。
- 0 分原因：flux-dev 加载需 22.2GiB > A10 可用 22.06GiB，OOM 于 load_sft。任务声明 gpu_types=A100/H100，A10 不在其列 → 纯基础设施障碍。**用户已决策：接受 A10 证据，不开 A100 重跑。**
- NOP 顺带修复的 v3.2：①requirements +invisible-watermark（上游 import imwatermark）②+requests ③Dockerfile apt +libgl1 libglib2.0-0 libxcb1（cv2 需要 libxcb.so.1）。

## 3. 剩余步骤（按序执行）

1. **GitHub 同步 v3.2 + NOP 证据**（进行中）：
   - `/tmp/rfsteps-gh` 浅克隆（depth 3）可能仍在下载；若失败重跑 `git clone --depth 3 REDACTED:khan114514/Taming-Rectified-Flow-for-Inversion-and-Editing.git /tmp/rfsteps-gh`
   - 用 rfsteps-package/workspace/harbor_task/environment/{requirements.txt, Dockerfile} 覆盖仓库根对应文件（仓库根 = harbor_task 内容）
   - 新增 `nop_evidence/`：放入 NOP-REPORT.md + evidence/jobs/（248K）
   - commit：`v3.2: fix missing deps (invisible-watermark/requests/cv2 syslibs) found by NOP trial + NOP evidence` → push（Mac SSH key 已绑 GitHub；境外走 https_proxy=127.0.0.1:7892 或 SSH 直连）
2. **重建提交 zip**：rfsteps-package/ 重打包为 rfsteps-package.zip（排除 .git/__pycache__），重新记 sha256。
3. **QA 附录**：rfsteps-qa-report/ 增补 NOP 部分——H05/H06 由 not_run 更新为「已有 Trial 运行证据一致（静态+已有证据），完整评分受 A10 基础设施限制未验证」，evidence 指向 nop_evidence 路径；runtime_status 按实写。**不要把静态通过写成已实跑通过。**
4. **更新 rfsteps-handoff.md**：加 NOP 章节 + v3.2 哈希。
5. **表单/平台**：如平台要求补交 NOP 材料，提交 nop_evidence/（或仓库链接 + commit）。
6. **清理**：fj02b 上 /historical-root/.ssh/authorized_keys 删掉 `fj02_pull`（VM 临时公钥 root@VM-16-4-ubuntu 那行）；VM 用户自留（他另有任务），别动。

## 4. 关键命令（VM 上重跑 NOP 的完整形态，备查）

```bash
cd /historical-root/rfsteps-nop && PYTHONPATH=. /opt/miniconda3/bin/harbor run \
  -p /historical-root/rfsteps-nop/harbor_task -a nop \
  -e gpu_docker_env:GpuDockerEnvironment \
  --extra-docker-compose /historical-root/rfsteps-nop/gpu-overlay.yaml \
  --mounts '[{"type":"bind","source":"/opt/rfsteps/weights","target":"/opt/rfsteps/weights","read_only":true}]' \
  --ve PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  --verifier-timeout-multiplier 2 -o /historical-root/rfsteps-nop/jobs --no-delete -y --debug
```

## 5. 坑（都踩过了，别再踩）

- **pkill/pgrep 自杀**：远程命令串里出现与 pkill 模式相同的子串会杀了自己。用 `"[h]arbor"` 字符类或变量拼接（A="dock";B="er bui"）。
- **harbor 内核探测镜像**：alpine:3.23.4@sha256:5b10f432... 需预拉，否则 30s 超时误判不支持 no-network。
- **harbor v0.23 需 Python≥3.12**；VM 用 /opt/miniconda3（py3.14）。官方 pip 装 harbor 用清华镜像。
- **PyPI 直连极慢**（~200KB/s）：VM 侧 Dockerfile 副本加了 `ENV PIP_INDEX_URL=清华`；**提交版 Dockerfile 不含此行**，同步仓库时别把 VM 副本原样覆盖（用 Mac 本地版 + 注意 Mac 版无 PIP 行）。
- harbor 官方本地 docker provider：capabilities.gpus=False（需自定义 env 类声明）、构建上下文=environment/（需 overlay 改任务根）。
- 腾讯 Ubuntu 镜像默认禁 root SSH：需 sed PermitRootLogin + ubuntu 用户 sudo 过渡。

## 6. 另一条线（第 2 题）

OneDC（NeurIPS 2025 一步扩散图像压缩）规划已完成：onedc-handoff.md（优化面 A 测试时量化/码率分配 + Phase 0 GO/NO-GO）。新窗口从那里开工，与本线互不依赖。
