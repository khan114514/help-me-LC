"""Write truthful current-version metadata while keeping old observations intact."""
from pathlib import Path
import hashlib
import json
import shutil

BASE = Path(__file__).resolve().parents[1]
PACKAGE = BASE/'package'
E = PACKAGE/'expert_evidence'
SOURCE = BASE/'source_snapshot'
# This initializer must never overwrite completed/new research evidence.
if (E/'run_summary.json').exists():
    _prior=json.loads((E/'run_summary.json').read_text())
    if _prior.get('best_method') or any(v.get('rounds',0) or v.get('effective_seconds') for v in _prior.get('agent_execution',{}).values()):
        raise SystemExit('Refusing to reset existing current-run research evidence')


def write(name, obj):
    (E/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


public = json.loads((PACKAGE/'workspace/harbor_task/environment/public_eval/anchors.json').read_text())
full = json.loads((PACKAGE/'workspace/harbor_task/tests/anchors.json').read_text())
write('expert_annotation.json',{
    'task_id':'auto0505','task_type':'fixed-model nontraining inference-method optimization',
    'research_direction':'deterministic timestep allocation for inversion and reconstruction',
    'optimization_surface':'get_timesteps(num_steps,image_seq_len) method; frozen model, 100 NFE/image and numerical scorer',
    'metric':'mean PSNR, maximize','task_version':'3.5.0-a100-repair',
    'anchors':{'public':{'B':public['baseline']['public']['psnr'],'U':public['upper_bound']['public']['psnr']},
               'full':{'B':full['baseline']['full']['psnr'],'U':full['upper_bound']['full']['psnr']}},
    'historical_reference':{'PSNR_full':20.45734928422148,'status':'original A100 v3.4.1 result; current deployment rerun pending'},
    'isolation':'public task only to Agent; artifacts only to separate Verifier; no Reference/Hidden/expert evidence in Agent context',
    'new_deployment_scoring':'NOT_RUN'})
write('run_summary.json',{
    'task_id':'auto0505','task_version':'3.5.0-a100-repair','status':'REPAIR_IN_PROGRESS_NOT_READY',
    'hardware_choice':{'actual_requested':'A100','authorization':'User instruction 2026-10-21','H20_L20_validation':'DEFERRED_BY_USER'},
    'agent_execution':{
        'codex':{'model':'gpt-6.1-sol','requested_effort':'xhigh','status':'current isolated run not started','effective_seconds':None,'rounds':0},
        'seed':{'model':'doubao-seed-2-1-turbo-260628','requested_effort':'high','status':'current isolated run not started; historical pilot access confirmed','effective_seconds':None,'rounds':0}},
    'historical_evidence':'historical_v341/; original source ZIP retained outside candidate input',
    'historical_time_acceptance':'User acceptance preserved as history; it is not converted into certified current effective seconds.',
    'research_duration_rule':{'default_per_track_seconds':36000,'nontraining_exception_per_track_seconds':25200,
                              'exception_status':'not yet claimed; all exception conditions require actual run evidence'},
    'task_binding':{'hash_profile':'harbor-task-inputs-v1','task_content_sha256':None,'status':'OFFICIAL_FINGERPRINT_TOOL_PENDING'},
    'best_method':None,'nop':'NOT_RUN_CURRENT_VERSION','GPU_validation':'NOT_RUN_CURRENT_VERSION',
    'stability_12h':'NOT_RUN_CURRENT_VERSION','official_format_and_gpu_checks':'OFFICIAL_TOOLS_PENDING',
    'local_validation':'Linux arm64 container boundary tests; no GPU/model score or research-duration credit'})
for name in ['trajectory_codex.json','trajectory_seed.json']:
    write(name,{'rounds':[]})

runtime=BASE/'tools/runtime'
old=SOURCE/'workspace/harbor_task/tests/run_eval.py'
new=runtime/'run_eval.py'
same=old.read_bytes()==new.read_bytes()
write('numeric_scorer_identity.json',{'unchanged':same,'old_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),
                                   'current_sha256':hashlib.sha256(new.read_bytes()).hexdigest(),
                                   'scope':'Only the deployment and untrusted-node boundary change; actual GPU numerical equivalence still requires rerun.'})
if not same: raise SystemExit('Numerical scorer unexpectedly changed')

validation=E/'repair_validation'; validation.mkdir(exist_ok=True)
for p in (BASE/'validation').iterdir():
    if p.is_file() and (p.suffix in ('.log','.json','.py') or p.name.startswith('Dockerfile')):
        shutil.copy2(p,validation/p.name)
deployment=E/'deployment_source'
if deployment.exists(): shutil.rmtree(deployment)
shutil.copytree(BASE/'deployment',deployment,ignore=shutil.ignore_patterns('weights','__pycache__','*.pyc'))
write('repair_resolution.json',{
    'QA05':{'state':'CODE_REPAIRED_LOCAL_BOUNDARY_TESTS_PASS_TARGET_RUN_PENDING',
             'changes':['single-container local GPU execution','removed unsupported storage/network requests','Landlock+seccomp candidate confinement','bounded output and timeout cleanup','race-resistant regular source opening','classified GPU inventory failures','separate public read-only worker and private verifier permissions']},
    'QA15':{'state':'A100_VALIDATION_PENDING_H20_L20_DEFERRED_BY_USER','resource_request':'1 GPU, 8 CPUs, 64GiB each sandbox','historical_worker_seconds':[392.4930227380246,393.9862480489537]},
    'H02_H03_QA17':{'state':'CONFIG_AND_PATHS_REPAIRED_NATIVE_TRIAL_PENDING','compose_in_execution_contexts':False,'verifier_mode':'separate','artifacts':['/workspace/solution']},
    'QA16':{'state':'NEW_QUALIFYING_TIME_PENDING','note':'Old event bounds and user acceptance are preserved, not relabeled as measured net time.'},
    'QA18':{'state':'HISTORICAL_PROVENANCE_AUDITED_CLEAN_CURRENT_TRAJECTORIES_PENDING','confirmed_issue':'Seed read private pilot log and m_sine.py source in original supervisor log.'},
    'QA21':{'state':'CURRENT_SCHEMA_PREPARED_OFFICIAL_FINGERPRINT_PENDING','note':'No replacement official hash algorithm invented.'},
    'B05':{'state':'DOCUMENTATION_REPAIRED','protocol':'fixed-model deterministic paired inference; no independent training seeds claimed'},
    'local_validation':{'candidate_boundary':'9 cases under root and unprivileged Linux users; current logs in repair_validation',
                        'backend_protocol':'9 synthetic scorer cases; GPU inventory and large assets mocked; no model/GPU score claimed',
                        'dockerfile_permissions':'Both production Dockerfiles built with a CPU fixture base; public UID1000 and formal private-material boundary passed',
                        'old_failure_logs':'Preserved as diagnosis history; latest final-* and *-image-permissions logs record current results'},
    'overall':'NOT_READY_FOR_RESUBMISSION'})

(E/'专家作业说明文档.md').write_text('''# 图像反演时间步分配返修记录

本题固定生成模型、二阶数值更新与每图100 NFE，只开放确定性时间步生成方法。Baseline沿用冻结的默认偏移节点，Reference为原有的正弦节点；原A100成对全16图PSNR分别为19.5288824095与20.4573492842，提升0.9284668747 dB。旧分数、选优及失败记录保留在historical_v341和optimization_evidence，不记作新部署成绩。

本版3.5.0-a100-repair按用户要求先使用A100。移除了正式执行目录中的Compose及外部GPU RPC依赖；Agent和独立Verifier各自在自己的单容器和分配GPU中执行。原数值评分器逐字节不变。可信侧只把受限子进程产生并重新验证的26个节点送入模型进程。

本地Linux容器已经执行候选文件/网络边界、超时回收和评分协议回归。两份实际Dockerfile以轻量CPU基础镜像构建，确认普通Agent用户可执行公开入口、正式降权候选能读可信入口且不能读Verifier私有材料。历史失败日志保留用于定位，当前结果见final-*与*-image-permissions日志。GPU镜像构建、同协议成对复验、当前版本NOP和正式移交仍待可用A100连接；CPU测试不记作GPU验证、研究时长或稳定性证据。

历史Seed日志证实访问了pilot日志和正弦参考候选源码。原记录不删除、不改写；当前接收所需的干净独立轨迹另行运行。历史模型CLI请求档位与上游实收能力分别记录。有效时长依实际起止与排队/安装/故障扣除核算，未知时段不填造秒数；非训练7小时例外只有满足全部条件才使用。

run_summary中的正式四项指纹等待真实task_fingerprint.py。官方0.3.10工具尚未取得，本版不声称官方自检、完整质检或平台验收通过。H20/L20验证按用户决定暂缓。
''')
(PACKAGE/'README.md').write_text('''# auto0505 A100 返修候选

当前版本：3.5.0-a100-repair。当前状态：修复中，尚不可作为全部验收完成的提交包。

代码、配置及本地Linux候选隔离修复已经形成；数值评分器保持原字节。待完成项为当前A100运行/镜像、Harbor移交和NOP、合格独立轨迹与时长、当前稳定性，以及真实官方指纹和格式/GPU自检。H20/L20验收由用户明确暂缓。

历史原件与当前运行分开记录。当前空轨迹和null字段表示尚未执行，不能解释为成功。详见expert_evidence/repair_resolution.json与专家作业说明文档.md。
''')
print('Current metadata written; no runtime or QA PASS fabricated.')
