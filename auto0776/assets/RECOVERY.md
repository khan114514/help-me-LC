# 百度网盘大文件恢复

2026-10-21 已通过用户桌面百度网盘客户端看到下列目录/文件，并打开资产目录的归档清单。网页Computer Use受限不代表桌面客户端不能访问；此处没有提供Cookie、登录态或带签名下载URL。

| 网盘文件路径 | 界面大小 | 字节 / SHA-256 |
|---|---:|---|
| `/电脑大文件归档_OneDC资产_20261010_203405/WorkBuddy/2026-10-03-21-07-06/private-recovery/onedc-assets.tar.gz` | 8.56GB | 9193898241 / `adf37d23103580414fe4df8f51d6e8ca642b79af717d758717b21d2b316a3a1d` |
| `/电脑大文件归档_OneDC旧环境_20261012_103401/WorkBuddy/2026-10-03-21-07-06/private-recovery/onedc-env-v8.tar.gz` | 14.08GB | 15121763292 / `8470df4b64f402bc52037df280bbe2b90ba3c20b2ea8be40a0d7f52fc7da037e` |
| 旧环境目录中另有 `onedc-env-v5-preflight.tar.gz`（搜索结果所在目录private-recovery） | 14.00GB | 本次未核具体字节/SHA，不能编造；优先v8 |

资产包的完整云端相对路径由已打开的归档清单确认。v8/v5文件名、大小和所在private-recovery已在客户端搜索结果看到；旧环境的完整嵌套路径按归档目录结构推定，恢复时以客户端实际位置为准，不将推定当实测路径。v8 SHA/字节来自既有本地独立备份回执，**本轮未重新下载云端14GB做SHA**；下载后必须校验。

同资产根目录有 `归档清单.json`，其中status=STAGED_NOT_QUEUED是当时暂存快照，不能覆盖本次云端文件可见事实，也不证明下载文件未损坏。先下载所需一个包，不必下载所有旧版本。

## 已知资产内容

本地既有 deep audit（assets/onedc_assets_deep_audit.json，作者home字段已投影）核过全部16成员：asset_manifest.json、lambda4.6两份safetensors、Stable Diffusion/TAESD模型与配置/refs、LPIPS/DISTS所需公共模型缓存。15个模型/配置成员均可对原manifest校验。该资产包是权重/配置，不能假定包含研究日志或τ扫描。

v8是旧A10环境镜像归档，对应 image ID `sha256:40875d7a85a1923dbd2041239f7d1ffa367e20e95e1aa31546cfe2dffa08a2c5`。它可作恢复/依赖参考，**不等于已适配H20/L20的平台镜像**。进入平台需按新单容器方案审计/重建或登记可用镜像。

下载后使用 sha256sum/shasum 校验上述精确值，检查足够空间（同时考虑压缩包、解压权重和镜像层）；不要照搬旧任务的磁盘限额到task.toml。权重只在可信准备区处理，遵守第三方模型许可，最终平台采用其认可的不可变资产入口。

## 八张Hidden图

source包含Public16图，Hidden像素不在仓库或Agent镜像。历史校准原归档含私有输入，但146MB完整归档未放Git。接手在可信Verifier准备区恢复准确8图，按旧原始manifest（source/onedc_v9/optimization_evidence/native_calibration_v8/original_records/task-manifest.json）中的SHA核验；不要用重编码图片替代，不可将Hidden复制到environment/。

这些是公开Kodak图像的私有评测划分。若从原始公共来源重新取得，逐文件SHA必须匹配既有输入，保留来源/版本/下载回执；这属于可信准备，不把Hidden或其指标交给研究Actor。尚未取得时标待补，不能声称平台会自动注入。

## 仍待用户/平台提供

新H20/L20服务器SSH、目标Harbor/平台镜像与隔离能力、可信模型主控配置、官方0.3.10及独立脚本。不复用历史主机IP/PID、代理隧道或旧GPU lease，也不把认证配置放仓库。
