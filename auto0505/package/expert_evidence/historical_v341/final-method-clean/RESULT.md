# 最终方法选优与清洁验收

**当前Task3.4.1（SHA90bb）清洁选优与独立full16验收通过。12小时稳定性仍另行pending，不是全流程已完成。**

| 候选 | 当前Public mean PSNR | 当前未裁剪归一化score | 来源 |
|---|---:|---:|---|
| Seed reverse power law p=1.2 | 21.66197823479546 | 1.237995577324134 | fresh clean02，真实GPU |
| GPT embedding-aware soft sine DP | 21.21974298189495 | 1.0 | fresh clean01，真实GPU |
| formal04封存round13最佳 | 20.65104213455171 | 0.693945053904085 | 原当前协议完整回执，后续封存段最佳未变 |

以当前同12图/25步/100NFE的mean PSNR选择Seed；其同锚点未裁剪score排序一致。选择于2026-10-04T17:30:19UTC冻结，在full16之前完成。两个历史记录的旧scorer不同且score都clipped1，未直接用它们排名。两个fresh clean指标各精确复现其历史overall/per-image值；原历史协议身份仍保留原标签。

所选源码SHA **df41c5a4726df6debb31dd57abc38f1b9418dd20b085bdc7c15eece61a5e0805**，26节点SHA **88b4ddc7ade3ad425a3fa660db6683dcc001c3367695d9b4de74106d728b5679**。独立原生Harbor Job/Trial在2026-10-04T17:41:50UTC通过：full16 PSNR **21.27548763952123**，SSIM **0.7167758922645703**，reward **0.8703690797499839**，每图100NFE。相对同Task实际NOP提升 **1.7466052300212347dB**，相对独立Reference提升 **0.8181383552997517dB**。Full16的Public12逐图指标及12个recon PNG哈希与fresh Public完全相等；仅读取哈希，未复制PNG像素。Full分数按full锚点归一化，与Publicscore属于不同split。

Public clean使用真实Harbor Trial构造与exact own Actor DockerEnvironment.start/exec/stop、当前原guard/Public UDS，不进行模型Agent setup/run或假称NOP。Full16使用原生builtin nop作机械Actor和已验证的官方最小Verifier扩展；Actor保持Starter，只有其已停止后唯一分离Verifier的method.py被专家替换。固定solve.sh、exact2边界、live传输前后/Host哈希、真实source/26节点/wholetrustedRPC、原生test退出0/exception null及当前63Task复核通过。readonly Compose cp的原生tar fallback警告和chmod1原样保留，真正native test退出为0。

Seed01因先发请求未满足服务Public role串行而被BUSY拒绝：guardexit2、无分数；10个原文件保留。GPT实际完成并清理后，唯一fresh Seed02通过。未重启服务、未盲重试、未修改Task/评分器/生产轨道。Full16 Public选择不依赖Hidden再选。5个精确自有容器最终已移除；新的模型调用0，三次完成GPU验收均purpose=clean_rerun，新增研究循环信用0。

复核入口：SELECTION.json、ACCEPTANCE.json、EVIDENCE-VERIFICATION.json、verify_final_evidence.py。原始目录actual-public-gpt-01（20文件）、actual-public-seed-02（20）、failed-public-seed-01（10）、actual-full16（19）、native-harbor-job（17）；另外三个gpu-*目录各5份worker原文件+copy record。runtime/runtime-public-v2/runtime-full-selected保留全部冻结脚本与pin；selected-method保留所选exact method和solve。总MF以MANIFEST.json为准。

原生结果：native-harbor-job/rfsteps-v341-build-check-2026100__xPBzff9/result.json。实际reward：native-harbor-job/rfsteps-v341-build-check-2026100__xPBzff9/verifier/reward.json。GPUjob：b448cf6c-f09a-4ff0-b278-b643082565d6；可信原字节SHA：6274be278cead0e26430c39568d709345fc7235f405bb44dd5000e62f65cab5f。
