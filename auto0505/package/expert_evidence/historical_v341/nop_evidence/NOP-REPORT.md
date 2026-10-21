# 当前 Task 3.4.1 NOP 验收

必选NOP已经真实通过：官方Harbor 0.23原生builtin nop、独立Verifier、A100完整16张图、每图100 NFE。Task SHA256为90bb7746559319dc6ce29dbbfae946f9a6b00694ef04b25d267f7def8c8249cb。

PSNR为19.528882409499996，reward为0.0；本次0分来自Starter基线锚点，评分已完成，不是OOM。Harbor系统退出0，Trial exception为空，Verifier原始reward与Harbor收集结果一致。Starter与solve源代码保持冻结字节。

actual_v341/中44份原始文件逐项与远端SHA一致，并保留原始NOP manifest、Job/Trial config和result、Verifier reward和日志、完整可信GPU回执、评分指标与运行来源。Root验收材料在本目录；同协议独立Reference原件见optimization_evidence/reference_runs/actual_v341，Reference PSNR20.45734928422148，reward0.46267401782591483。

legacy_v32/另外保留用户最初附的NOP-REPORT.md、CODEX-HANDOFF.md及旧版A10尝试的原始jobs。它们描述的是当时旧版本状态，不代替本次验收。交接文的命令仅作为历史内容保存。

CONTENTS.json列出本目录文件哈希。ZIP打包时强制检查NOP必选路径，并解压逐项核对完整ZIP文件SHA。此报告仅确认NOP和已有配对证据；最终最佳方法、稳定性与全流程验收见各自独立记录。
