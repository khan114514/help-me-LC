# 01 · 论文溯源账本（OneDC）

| 项 | 值 |
|---|---|
| 论文 | One-Step Diffusion-Based Image Compression with Semantic Distillation（OneDC） |
| 发表 | NeurIPS 2025 Main；arXiv:2505.16687（v2, 2025-11-26） |
| 作者 | Naifu Xue, Zhaoyang Jia, Jiahao Li, Bin Li, Yuan Zhang, Yan Lu（中国传媒大学、中国科学技术大学、Microsoft Research Asia；具体机构见官方项目页） |
| 代码 | https://github.com/onedc-codec/onedc（CC BY-NC-SA 4.0，研究用途，包内保留 LICENSE.md 与引用） |
| 权重 | OneDrive 分享（lambda 12.2~0.6 七档 + exlow_bpp0034）；本项目使用 lambda4.6 |
| 项目页 | https://onedc-codec.github.io/ |

## 方法要点（与任务面相关部分）

- 编码：x → latent y（编码器），z = hyper_enc(y) 经 FSQ（7 通道×4 等级，码本 16384）→ ẑ 固定约 0.0034 bpp；
  ŷ 为标量量化（官方 uniform rounding）后经 DCVC 系 C++ rANS 熵编码，熵模型为零均值高斯（逐点 σ，来自超先验+空间先验，四阶段 checkerboard 上下文）。
- 解码：y_hat = ŷ + means_hat；语义 c = h_sem(ẑ) 以跨注意力注入一步 U-Net（SD1.5 经 DMD2 蒸馏）生成重建。
- 关键结构：解码端对 ŷ 仅做整数加法 → 编码端量化规则可在测试时自由替换，解码端与码流格式零改动。
- 训练两阶段（Stage I 重建+语义蒸馏 CE；Stage II 蒸馏+对抗），与本任务无关（冻结权重）。

## 复现锚点（Phase 0，GO/NO-GO 用）

2026-10-04 已核对 [论文 v2 的 Table 5](https://arxiv.org/html/2505.16687v2#A1.T5)，并在新 A10、离线冻结镜像上通过原生 Harbor 独立 verifier 运行官方 `Evaluator.evaluate()`。未挂载候选量化钩子；Kodak 全分辨率 24 张按名称排序，seed=0，官方 uniform rounding、真实 rANS 码流，LPIPS 输入为 [-1,1]。

| 指标 | 论文 Table 5 | 新环境实测 | 相对偏差 |
|---|---:|---:|---:|
| bpp | 0.0245 | 0.02438185 | −0.48% |
| PSNR | 22.220 | 22.18857 | −0.14% |
| MS-SSIM | 0.779 | 0.77989497 | +0.11% |
| LPIPS | 0.154 | 0.15391090 | −0.06% |
| DISTS | 0.097 | 0.09438734 | −2.69% |

五项均在 ±5% 内，Phase 0 = GO。逐图指标见 `optimization_evidence/official-paper-reproduction.json`；耗时 32.52 秒，不计入模型优化有效时长。源码复现使用的排序与任务评分的 public16-then-hidden8 顺序不同，二者分别记录；官方方法的较高码率不改变任务 Baseline 码率上限。论文该表不含 FID，本任务不评 FID。

此前探索环境的旧 GO 不作为正式轨迹时长或最终冻结镜像的验证证明。新评测源码还修复了缺失的 `ev.model.eval()` 和 LPIPS 输入归一化，并重新校准 B/R/U；新校准完成前不沿用旧锚点作最终声明。

## 权重与底座来源（供应链记录）

- lambda4.6：作者 OneDrive（CDP 浏览器通道抓取 download.aspx 直链 + curl 断点续传），
  sha256 见 anchors.json weights 段与 frozen_hashes.txt。
- runwayml/stable-diffusion-v1-5（unet+scheduler 子目录）：hf-mirror.com，commit 451f4fe1。
- stabilityai/stable-diffusion-2-1（vae 子目录）：该仓库已转 gated；
  改用 sd2-community/stable-diffusion-2-1-base（hf-mirror），其 vae safetensors
  sha256=a1d99348… 与 ModelScope AI-ModelScope/stable-diffusion-2-1 完全一致（双源交叉验证）。
- madebyollin/taesd：hf-mirror.com，commit 614f7681。
