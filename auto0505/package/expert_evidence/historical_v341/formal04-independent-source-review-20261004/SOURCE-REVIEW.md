正式 04 的专家源码可放行，尚待实际 installed 前置检查。独立纯 CPU 静态审计 41 项全部通过；没有编辑生产 Source、Task、历史记录或 Root 当前状态 JSON，没有执行模型、GPU、RPC、候选程序或容器。

42 个冻结文件的 SHA、长度和清单逐项一致，源 MANIFEST SHA 为 b282cd50306ff561593fddd43538eeaf6a8f2bae02ea7950a7a61d0a7b272425。Driver SHA 为 8d9e51d137c5ec2de61eee9f494986c9084690f576827ed71a355a3bcfde64c2；剔除 CONTINUATION_TEMPLATE 常量后的完整 AST 与正式 03 相同。模板精确只添加 7 行本地 functions.exec / await tools.exec_command 调用格式及真实输出要求，没有加入候选方法指导。差异保存于 CONTINUATION-TEMPLATE-DIFF.patch。

完整新指令精确等于冻结 base instruction 字节加新 template；base SHA 为 a253ba99c1cbc50d5679e6ab75642d8197617adffa1386a72347749c7934be46，共同完整 prompt 为 fc748766095e76608aa29eecf033e07b2aca3d6ce38c7e13584a3d3411638b53。policy、launch contract、runtime source 和 source summary 的哈希全部与实际文件一致。formal_preflight 仅更新 fresh root、job 名及 prompt 常量；其余运行代码字节不变。两角色 job 除 03→04 新路径外相同，模型/effort、资源、隔离、评分及 ledger f795 不变。

10 组专家私有 known 向量与上一版相同，全部 26 节点合法且原 SHA 精确重算相符；近重复阈值仍为固定 1e-12。公开资产白名单及声明 SHA 未改变，本次没有读取 Hidden 像素，也没有重新全量重哈希 Task 的 63 个文件。双方初始轨迹均为 {"rounds":[]}，bindings v1/tracks 均无 round，正式起时 null，信用 0，门禁 false。旧 02/03、前测及回放不转入新 04。

保留的正式 04 CPU suite 日志为 76 测试全部通过；首次旧 harness SHA fixture 失败日志原字节也保留，修正只更新新 Driver/job 身份。本审计执行的是独立 AST/hash/JSON 检查，没有重复运行冻结生产模块或该 suite。

旧正式 03 的 91 个本地保全文件逐 SHA 对齐 Root 保存的远端哈希映射。其真实 owned exit=-9、stop_requested=true、harbor_wait_completed=true、research_credit_seconds=0；这不是成功关闭资格循环。该次工具循环的根因不在本审计中重新推断，原记录保持独立历史。

启动前仍须真实验证 installed source/Task/gateway PID/start-tick/UDS inode 和权限，并通过有界 keyless numeric501/model405 GET；静态哈希不证明实时连接可达。新模板也不证明下一次 Native 必定执行 shell。正式研究信用仍要求真实原生工具、逐轮 source/receipt/metrics/decision 闭环及唯一或非近重复的合法评分单调秒数；每角色至少 36000 秒且完整 full16 verifier 结束后，才可完成资格/串行后续门禁。此审计授时 0，不宣称全流程完成。

证据明细、范围和待验事项见 SOURCE-REVIEW.json；完整文件核验见 MANIFEST-VERIFICATION.json。audit_formal04.py 只解析 AST、JSON 和哈希，不导入生产或候选模块。
