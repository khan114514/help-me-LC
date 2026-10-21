# 持久化运行合同

## 教程与执行器版本边界

三期新要求见 [V4 合同](phase3-v4-contract.md)。本文件记录现有 **0.3.4 执行器**的机器接口，不是官方 0.3.10 规范。当前 `manager.py` 的 `validate_plan`、QA容器和聚合器仍绑定随附0.3.4资产；不得只把 qa_version 改成0.3.10或改旧manifest冒充升级。正式新合同须先取得真实0.3.10发布包及独立前检/指纹脚本，再核对并适配实际报告协议；缺工具时内容准备继续，完整新版验收保持待补。旧计划、暂停和在途任务保持原状态，不自动迁移。

V4 内容要求：两镜像不是必需，Solver/Verifier 是不同sandbox；每轮公开Dev，结束后只移交候选再Hidden；每个sandbox单容器，无Compose/额外工作环境；GPU实际H20优先或L20，CPU不加GPU；QA15有日志资源估算，QA21四项指纹；格式/GPU检查后重交完整三目录ZIP，保留最终ZIP SHA256。旧计时JSON是此执行器适配接口，并非教程额外要求每个专家实现独立计时器。

## 当前用户放宽口径与旧执行器

用户2026-10-21的[优先级调整](phase3-v4-contract.md#当前优先级调整用户授权2026-10-21)适用于当前内容审查：指定的指纹/哈希差异、换卡分数/耗时补证和NOP可非阻断待补。本文件下列固定stage、receipt和源码哈希要求仅描述旧0.3.4执行器，不覆盖用户的新口径；不得仅为这些缺口启动其强制NOP/repair循环。原始工具结论与用户口径结论分列，保留旧计划、在途和暂停状态，不伪造receipt、PASS或历史证据。

## Plan

主控专用JSON，不得进入题包。schema_version=1；task_root是绝对作者任务目录；goal是用户目标。contract包含qa_version=0.3.4、effective_seconds_per_track=36000、stability_seconds=43200。reviewers为两个不同身份对象，各有provider/model/version，必须使用用户指定模型与最新路由，不自动替换。

drivers是这些key对应的非空argv数组：prepare、br、preflight_nop、dual_a、dual_b、finalize、nop、stability、package、qa_a、qa_b、repair。所有真实命令须先实测。调度器自动追加 `--request /absolute/job/request.json`，不使用shell拼接。可选retry_seconds默认60；job_timeout_seconds默认172800。deadline_utc仅在用户有授权预算边界时填写，过期进入NEEDS_INPUT，不标DONE。不设修复轮数上限。

7h例外需contract.seven_hour_exception含nontraining、short_iterations、continuing_directions三个全真字段；完整例外证据仍由QA核验。doctor拒绝缺driver、重复reviewer、QA版本错误、过低时长、run-dir嵌入task和不存在命令。

## Request与receipt

job为唯一UUID、新目录。request包含stage/revision/task_root/task_sha256/contract_sha256/contract/goal/receipt_path。repair收到failures（指向旧QA/运行记录）；非QA专家阶段收到upstream证据。candidate只应收到公开冻结任务，由专用sandbox/Harbor driver转译，不能继承管理request和私有路径。

driver写receipt.json：status为PASS/FAIL/RETRY/NEEDS_INPUT，revision与contract_sha256匹配，evidence为本job内非空文件的相对路径，无软链接越界，details为对象。失败附reason。真实exit code非0或缺receipt不能PASS。主控记录实际执行起止/退出和每个证据hash，不回显任意driver reason/stdout。凭据不进入driver环境；请求模型经可信网关。

各阶段details额外合同：

- dual_a/b：effective_seconds与duration_evidence。计时JSON含effective_seconds、intervals，每项start_epoch/end_epoch/kind；只计research，不重叠、不超过主控观测运行时间。适配已有格式须保留原始计时证据，不捏造。证据还需由正式QA核验。
- finalize：final_validations恰好a、b，各含method_sha256、contract_sha256和evidence；每轨自己的原始复验JSON含相同字段及status=PASS。不能互代结果，不改已冻结作者任务输入；选择/装配产物写到本job目录供package读取。
- nop/preflight_nop：trial_evidence至少含真实config、result、reward、log四类文件；原版QA负责语义核验。
- stability：observation为stability_worker产物；同容器持续健康至少合同秒数，无重启，无过大观测间隙。
- package：artifact为本job的完整ZIP。主控复制成immutable副本并重算SHA，QA只读该副本。
- qa_a/b：report和session_evidence必须在evidence。内置qa_container保存launch.json和events.jsonl实际来源。QA report只能由审查会话形成，不能主控补字段。
- repair：实质修改作者产物，主控比较repair开始/结束的作者目录hash，拒绝无改动回执。成功后新revision，清空当前阶段引用，保留历史。失败继续以新job修复，禁止改QA/contract或直接改报告PASS。

## 恢复与内置driver

state原子写；调度锁避免双重派发；每job wrapper独立锁、started/heartbeat/exit记录。先落盘再启动detached wrapper。主控重启接回既有任务，不重复运行在途job；已记录但尚未启动的intent用同job锁安全续派。wrapper清除凭据环境，持续heartbeat，超时终止自己启动的进程组。缺失/改写的旧证据进入repair，旧证据失效不阻止新revision生成。每轮核验固定QA源码hash。

管理agent每个阶段从request/upstream/failures和磁盘产物重新建立上下文，stage/repair不继承旧会话历史。双轨driver必须把长研究实现为同一模型、同一冻结公开任务下的有界会话，检查点与有效计时落盘；换会话只续自身lane，不可读取另一lane或私有作者材料。后台管理程序不需要在长实验期间持续占用模型上下文。stage发生上下文/CLI失败时保留已写产物，下次由新会话修复并重新验证，不把失败会话计作完成。

`agent_stage.py --model MODEL [--gateway-url URL] [--reasoning-effort EFFORT] --request FILE`：专家侧prepare/repair等使用新Codex会话和固定回执schema。无网关时使用已有本机登录，不复制认证文件。它不是候选隔离边界或QA runner。

`qa_container.py --image CLEAN_IMAGE --network ISOLATED_MODEL_NETWORK --gateway-url http://trusted-gateway/v1 --request FILE`：image预装Linux Codex/Python3/git，无作者配置或任务历史；网络仅能访问指定可信网关。全新容器只挂input ZIP、QA skills、空out，不传凭据。gateway验证并记录指定模型/推理支持，不回退按量。

`stability_worker.py --container ACTUAL_CONTAINER_ID [--interval 30] [--health-argv-json JSON_ARRAY] --request FILE`：检查专用测试容器。无health命令时必须有Docker HEALTHCHECK且healthy。任务driver需另保存容器build/inspect与冻结任务绑定依据。

框架测试使用明确标注模拟实验和模型，仅验证管理行为。正式题目必须有真实driver、指定模型路由、Harbor版本和12h运行；尚未指定任务时不启动旧题，不宣称正式两个PASS。
