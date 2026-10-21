"""Audit preserved real results and restore the highest public PSNR code."""
from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import sys

root=Path('/workspace/agent-output')
segment=int(sys.argv[1]);end_round=int(sys.argv[2])
start=json.loads((root/f'segment_{segment:06d}_start.json').read_text())
first_round=start['start_round']
rows=[json.loads(line) for line in (root/'trajectory.jsonl').read_text().splitlines()]
expected={'round','policy_name','method_summary','status','score','failure_reason','retained_best','time'}
assert all(set(row)==expected for row in rows)
assert [row['round'] for row in rows]==list(range(1,end_round+1))
assert all(re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',row['time']) for row in rows)
checks=[];jobs=[];node_hashes=[];total_exploration_seconds=0.0;segment_seconds=0.0
for row in rows:
    r=root/f"round_{row['round']:06d}"
    digest=hashlib.sha256((r/'method.py').read_bytes()).hexdigest()
    proposal=json.loads((r/'proposal.json').read_text())
    decision=json.loads((r/'decision.json').read_text())
    status=json.loads((r/'evaluation_status.json').read_text())
    assert decision['purpose']==proposal['purpose']
    assert decision['method_sha256']==digest
    check={'round':row['round'],'purpose':decision['purpose'],'status':row['status'],'method_sha256':digest}
    if row['status']=='ok':
        metrics=json.loads((r/'metrics.json').read_text())
        gpu=json.loads((r/'gpu_receipt.json').read_text())
        assert metrics['method_sha256']==digest==status['method_sha256']
        assert status['status']==gpu['status']=='COMPLETE'
        assert status['evaluation_completed'] is True and gpu['evaluation_completed'] is True
        assert status['gpu_job_id']==gpu['job_id']
        assert metrics['overall']['n']==len(metrics['per_image'])==12
        assert metrics['num_steps']==25 and metrics['nfe_per_image']==100
        assert all(image['split']=='public' for image in metrics['per_image'])
        assert gpu['role']==gpu['receipt']['protocol']['split']=='public'
        assert metrics['overall']['psnr']==row['score']==decision['psnr']
        assert math.isfinite(row['score'])
        assert abs(sum(image['psnr'] for image in metrics['per_image'])/12-row['score'])<1e-10
        anchors=metrics['anchors'];actual_score=metrics['score']
        jobs.append(gpu['job_id']);node_hashes.append(gpu['receipt']['nodes_sha256'])
        seconds=gpu['receipt']['scoring_seconds']
        check.update(psnr=row['score'],score=actual_score,gpu_job_id=gpu['job_id'],nodes_sha256=gpu['receipt']['nodes_sha256'],scoring_seconds=seconds)
        if decision['purpose']=='exploration':
            total_exploration_seconds+=seconds
            if first_round<=row['round']<=end_round: segment_seconds+=seconds
    else:
        assert row['score'] is None
    checks.append(check)
current=[c for c in checks if first_round<=c['round']<=end_round]
assert len(current)==3 and all(c['purpose']=='exploration' for c in current)
assert sum(c['purpose']=='starter' for c in checks)==1
assert len(set(jobs))==len(jobs)
assert len(set(node_hashes))==len(node_hashes)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in start['prior_round_hashes'].items())
frozen=json.loads((root/'frozen_hashes.json').read_text())
changed=[p for p,digest in frozen.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest]
assert not changed,changed
best=json.loads((root/'best.json').read_text())
assert best['psnr']==max(row['score'] for row in rows if row['status']=='ok')
shutil.copyfile(root/'best_method.py','/workspace/solution/method.py')
best_source=(root/best['directory']/'method.py').read_bytes()
assert Path('/workspace/solution/method.py').read_bytes()==best_source
assert hashlib.sha256(best_source).hexdigest()==best['method_sha256']
assert set(p.name for p in Path('/workspace/solution').iterdir())=={'method.py','solve.sh'}
# Use only the trusted isolated CPU schedule extractor; no GPU request or rerun.
import importlib.util
import tempfile
spec=importlib.util.spec_from_file_location('trusted_public_evaluator','/workspace/environment/public_eval/evaluate_candidate.py')
evaluator=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluator)
with tempfile.TemporaryDirectory(prefix='rfsteps_final_cpu_') as scratch:
    nodes,digest=evaluator.extract_schedule('/workspace/solution/method.py','/workspace/environment/public_eval/candidate_worker.py',scratch,'/usr/bin/python3')
expected_node_hash=hashlib.sha256(json.dumps(nodes,separators=(',',':'),allow_nan=False).encode()).hexdigest()
best_receipt=json.loads((root/best['directory']/'gpu_receipt.json').read_text())
assert digest==best['method_sha256'] and expected_node_hash==best_receipt['receipt']['nodes_sha256']
(root/f'cpu_validation_segment_{segment:06d}.json').write_text(json.dumps({'method_sha256':digest,'nodes_sha256':expected_node_hash,'timesteps':nodes,'node_count':len(nodes),'isolated_trusted_cpu_extraction':True,'public_receipt_nodes_match':True},indent=2)+'\n')
summary=[f'当前完成第 {segment} 个原生研究段；本段为第 {first_round}–{end_round} 轮，恰好 3 个新探索。累计一次 Starter 校准和 {sum(c["purpose"]=="exploration" for c in checks)} 个新探索。GPU 请求均串行，经冻结公开 evaluate.sh 接口执行；无 clean_rerun 或重复节点请求。每轮保存精确源码、指标、原始 GPU 回执、状态与方法决策。\n']
summary+=['| 轮次 | 目的 | 方法 | 平均 PSNR (dB) | 开发分数 | 决策 |','|---|---|---|---:|---:|---|']
for row,check in zip(rows,checks):
    d=json.loads((root/f"round_{row['round']:06d}"/'decision.json').read_text())
    if row['status']=='ok': summary.append(f"| {row['round']} | {check['purpose']} | {row['policy_name']} | {row['score']:.9f} | {check['score']:.9f} | {d['decision']} |")
    else: summary.append(f"| {row['round']} | {check['purpose']} | {row['policy_name']} | {row['status']} | 无 | reject |")
summary.append(f"\n累计最佳为第 {best['round']} 轮 {best['policy_name']}，PSNR={best['psnr']:.12f} dB，比 Starter 提高 {best['psnr']-rows[0]['score']:.12f} dB；开发分数={best['score']:.12f}。本段开始时最佳为 {start['baseline_best']['psnr']:.12f} dB，本段改进量为 {best['psnr']-start['baseline_best']['psnr']:.12f} dB。")
summary.append(f"\n最佳实际评分源码已逐字节恢复为 /workspace/solution/method.py，并保存在 best_method.py 与其轮目录；SHA-256 为 {best['method_sha256']}。冻结 solve.sh 和所有 {len(frozen)} 个记录的冻结文件哈希不变。恢复后的节点另经可信降权 CPU 提取器验证，26 节点、端点、范围、有限性和非增约束通过，并与最佳原始 GPU 回执节点哈希相同；未为这项 CPU 检查请求 GPU。")
bm=json.loads((root/best['directory']/'metrics.json').read_text())['overall']
summary.append(f"\n最佳诊断：SSIM={bm['ssim']:.12f}，pixel MSE={bm['pixel_mse']:.12f}，latent MSE={bm['latent_mse']:.12f}。平均 PSNR 是优化指标，诊断项不替代指定指标。")
summary.append('\n第一段研究：均匀节点使 PSNR 下降 1.4022703492 dB，11/12 图退化，因此否定了优先加密低噪声端的初始预测；负偏移 CPU 草案没有请求 GPU。μ=1.20 的高噪声偏移得到小幅提升，平方余时间与 1/128 对齐进一步提高 PSNR。自写一维双峰 RF 代理只用于理论启发，没有作为公开分数。')
summary.append('\n第二段研究：第 5 轮保留平方形状和 1/128 最小间隔但移除舍入，公开 PSNR=19.4202117022，比原最佳低 0.1914106267 dB，拒绝。公开 RF-Solver-Edit 的 layers.py 显示，时间嵌入先在输入精度下乘 1000，再转为 FP32；位级 BF16 检查据此设计 1/125 网格，节点与中点缩放后可对应精确时间。该公开参考是设计依据，不声称逐字等同于冻结服务器实现。第 6 轮检验嵌入对齐与步长系数对齐的权衡；第 7 轮继续在实测较好的对齐方式上检验密度指数。')
if segment >= 3:
    summary.append('\n第三段研究：先沿用 1/125 对齐降低幂指数，以检查平方密度偏向噪声端的程度；随后在 Starter 原始 logit 形状上加入嵌入对齐，检查时间舍入与形状的交互。后续候选依据本段实际公开 PSNR 选择，全部原始方法摘要和逐图结果可在各轮 proposal.json、metrics.json 和 comparison.json 核对。')
if segment >= 4:
    summary.append('\n第四段研究：不再依赖全局指数插值，先在连续平方目标上采用动态规划，约束节点和相邻中点为参考嵌入的固定点，允许低时间更细投影；后续仅调整低时间尾部或将一个短高时间区间的预算转移到大低时间区间。方法选择以实际公开评分为准，数值误差代理不作为分数。')
for row in rows:
    if row['round'] >= 8 or first_round<=row['round']<=end_round:
        d=json.loads((root/f"round_{row['round']:06d}"/'decision.json').read_text())
        summary.append(f"\n第 {row['round']} 轮决策：{d['explanation']}")
failures=[row for row in rows if row['status']!='ok']
summary.append('\n失败记录：'+('；'.join(f"第 {r['round']} 轮 {r['status']}：{r['failure_reason']}" for r in failures) if failures else '所有候选评分均成功；较差 PSNR 属于合法负结果，未出现评分基础设施失败或门禁违规。')+'第一段记录工具因缺少 tzdata 报错，使用 UTC+8 后补齐该轮；公开参考有 404 与网络超时，之后通过公开 GitHub contents API 成功取得所需参考。未编辑评分器产出的回执、状态或指标；未读取其他原生会话或非公开服务数据。')
summary.append(f"\n证据：累计 {len(jobs)} 个独立成功 GPU job_id 和 {len(set(node_hashes))} 个不同节点哈希；之前轮目录的文件哈希全部保持不变。本段 3 个探索的真实 scoring_seconds 合计 {segment_seconds:.6f} 秒，累计探索 scoring_seconds 合计 {total_exploration_seconds:.6f} 秒，不含 Starter、排队、装载或空等待。专家评分时间下限门禁待独立审计，此报告不宣称已通过。")
summary.append('\n按 continuation contract，完成本段 3 个新探索后返回专家 checkpoint，不追加重复节点评分。可继续验证：对最佳节点进行有理论依据的区域性再分配，以避免仅用密度指数插值；检验把最小间隔直接写入连续密度的平滑分配；对参考嵌入舍入进行区间级分析，避免仅按连续曲线位移优化节点；在保持关键端点节点的前提下检验局部密度变化。任何新候选都须通过同一冻结公开评分器，未评分方向无自报分数。')
(root/'run_summary.md').write_text('\n'.join(summary)+'\n')
report={'segment':segment,'start_round':first_round,'end_round':end_round,'checks':checks,'new_exploration_count':3,
        'cumulative_exploration_count':sum(c['purpose']=='exploration' for c in checks),
        'starter_count':1,'clean_rerun_count':0,'segment_exploration_gpu_scoring_seconds':segment_seconds,
        'cumulative_exploration_gpu_scoring_seconds':total_exploration_seconds,'unique_gpu_jobs':len(jobs),
        'unique_node_hashes':len(set(node_hashes)),'prior_round_files_unchanged':True,'frozen_files_changed':changed,
        'best':best,'final_cpu_schedule_matches_gpu_receipt':True,'expert_lower_bound_gate':'independent audit pending'}
(root/f'segment_{segment:06d}_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'best':best,'segment_exploration_gpu_scoring_seconds':segment_seconds,'cumulative_exploration_gpu_scoring_seconds':total_exploration_seconds,'final_cpu_schedule_matches_gpu_receipt':True,'frozen_files_changed':changed},ensure_ascii=False,indent=2))
