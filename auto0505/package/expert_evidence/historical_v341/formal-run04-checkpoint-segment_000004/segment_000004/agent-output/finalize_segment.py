"""Finalize this segment using actual artifacts only; no scoring requests."""
from pathlib import Path
import hashlib
import json
import math
import shutil
import re

root=Path('/workspace/agent-output')
rows=[json.loads(line) for line in (root/'trajectory.jsonl').read_text().splitlines()]
keys={'round','policy_name','method_summary','status','score','failure_reason','retained_best','time'}
assert all(set(row)==keys for row in rows)
assert [row['round'] for row in rows]==sorted(row['round'] for row in rows)
assert all(re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',row['time']) for row in rows)
checks=[];jobs=[];node_hashes=[];exploration_seconds=0.0
for row in rows:
    r=root/f"round_{row['round']:06d}"
    source=(r/'method.py').read_bytes()
    digest=hashlib.sha256(source).hexdigest()
    p=json.loads((r/'proposal.json').read_text())
    d=json.loads((r/'decision.json').read_text())
    s=json.loads((r/'evaluation_status.json').read_text())
    assert d['purpose']==p['purpose']
    assert d['method_sha256']==digest
    check={'round':row['round'],'purpose':d['purpose'],'status':row['status'],'method_sha256':digest}
    if row['status']=='ok':
        m=json.loads((r/'metrics.json').read_text());g=json.loads((r/'gpu_receipt.json').read_text())
        assert m['method_sha256']==digest==s['method_sha256']
        assert s['status']=='COMPLETE' and s['evaluation_completed'] is True
        assert g['status']=='COMPLETE' and g['evaluation_completed'] is True
        assert s['gpu_job_id']==g['job_id']
        assert len(m['per_image'])==m['overall']['n']==12
        assert m['num_steps']==25 and m['nfe_per_image']==100
        assert all(r['split']=='public' for r in m['per_image'])
        psnr=m['overall']['psnr']
        assert psnr==row['score']==d['psnr'] and math.isfinite(psnr)
        assert abs(sum(r['psnr'] for r in m['per_image'])/12-psnr)<1e-10
        assert g['receipt']['protocol']['split']=='public' and g['role']=='public'
        jobs.append(g['job_id']);node_hashes.append(g['receipt']['nodes_sha256'])
        check.update(psnr=psnr,gpu_job_id=g['job_id'],nodes_sha256=g['receipt']['nodes_sha256'],scoring_seconds=g['receipt']['scoring_seconds'])
        if d['purpose']=='exploration': exploration_seconds+=g['receipt']['scoring_seconds']
    checks.append(check)
assert len(set(jobs))==len(jobs)
assert len(set(node_hashes))==len(node_hashes)
assert sum(c['purpose']=='exploration' for c in checks)==3
assert sum(c['purpose']=='starter' for c in checks)==1
assert sum(c['purpose']=='clean_rerun' for c in checks)==0
frozen=json.loads((root/'frozen_hashes.json').read_text())
changed=[path for path,h in frozen.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h]
assert not changed,changed
best=json.loads((root/'best.json').read_text())
best_round=root/best['directory']
assert best['psnr']==max(row['score'] for row in rows if row['status']=='ok')
shutil.copyfile(root/'best_method.py','/workspace/solution/method.py')
assert Path('/workspace/solution/method.py').read_bytes()==(best_round/'method.py').read_bytes()
assert hashlib.sha256(Path('/workspace/solution/method.py').read_bytes()).hexdigest()==best['method_sha256']
assert Path('/workspace/solution/solve.sh').is_file()
summary=[]
summary.append('本原生段完成冻结 Starter 校准和恰好 3 个新探索；所有 GPU 请求逐一串行，经冻结公开评分接口执行。每轮保留实际 method.py、metrics.json、gpu_receipt.json、evaluation_status.json 和 decision.json。\n')
summary.append('| 轮次 | 目的 | 方法 | 平均 PSNR (dB) | 开发分数 | 决策 |\n|---|---|---|---:|---:|---|')
for row,check in zip(rows,checks):
    r=root/f"round_{row['round']:06d}"
    d=json.loads((r/'decision.json').read_text())
    if row['status']=='ok':
        m=json.loads((r/'metrics.json').read_text())
        summary.append(f"| {row['round']} | {check['purpose']} | {row['policy_name']} | {row['score']:.9f} | {m['score']:.9f} | {d['decision']} |")
    else: summary.append(f"| {row['round']} | {check['purpose']} | {row['policy_name']} | {row['status']} | 无 | reject |")
summary.append(f"\n当前最佳是第 {best['round']} 轮，PSNR={best['psnr']:.12f} dB，较 Starter 提高 {best['psnr']-rows[0]['score']:.12f} dB；开发分数={best['score']:.12f}。已将该轮实际评测的完整源码逐字节恢复到 /workspace/solution/method.py，并保存 best_method.py 与 best.json。源码 SHA-256：{best['method_sha256']}。")
bm=json.loads((best_round/'metrics.json').read_text())
summary.append(f"\n最佳方案诊断：SSIM={bm['overall']['ssim']:.12f}；pixel MSE={bm['overall']['pixel_mse']:.12f}；latent MSE={bm['overall']['latent_mse']:.12f}。平均 PSNR 是优化指标，诊断项不替代它。")
summary.append('\n研究决策：最初假设低噪声端步长过大；均匀节点真实 PSNR 下降 1.4022703492 dB，11/12 图退化，因此拒绝。自写双峰代理倾向负偏移，但不能预测 FLUX 结果；准备的负偏移没有进行 GPU 评分。随后正偏移 μ=1.20 得到 0.1852407241 dB 的平均提升，第三个探索将密度改为平方余时间并对齐 BF16 时间、中点和步长。所有取舍见各轮 decision.json；逐图变化见 comparison.json。')
summary.append('\n失败记录：本段没有评分失败、门禁违规或基础设施评分错误；均匀节点是合法但较差的结果。记录工具首次使用 ZoneInfo 时因缺少 tzdata 失败，改为明确 UTC+8 后补齐同一轮记录；未篡改评分文件。公开参考 URL 最初返回 404，改正为 RF-Solver-Edit 仓库；第三轮评分期间额外请求公开 layers.py 超时，未取得源码、未用于候选决策或自报分数。未读取其他会话或非公开服务器文件。')
summary.append(f"\n验证：{len(frozen)} 个冻结文件哈希全部不变，冻结 solve.sh 保持原样。{len(jobs)} 个成功公开请求有互不相同的 job_id 和节点哈希，均为 12 张公开图、25 步/方向和 100 NFE/图。3 个探索回执的真实 scoring_seconds 合计 {exploration_seconds:.6f} 秒（不含 Starter、排队或模型装载时间）。这只是原生记录一致性检查，不声称专家评分时间下限门禁已通过。")
summary.append('\n按本段 continuation contract，完成 3 个新探索后返回专家 checkpoint，不追加重复节点评分；本段 clean_rerun 数为 0。最后实际评分的候选和当前最佳的身份均可由上述源码哈希及回执核对。后续原生段应继续真实方法探索，不能把 Starter 或 clean_rerun 计作探索。')
summary.append('\n可继续验证的方向：分别评估未经 BF16 对齐的平方网格和对齐的 logit 网格，以分离密度形状与时间舍入的贡献；测试平方指数附近的 1.5、1.75、2.25 等密度形状；在高噪声端小步长与低噪声端最大区间之间做连续、有界的分配。所有候选仍须在冻结预算下通过实际公开评分，未测试的方向不自报分数。')
(root/'run_summary.md').write_text('\n'.join(summary)+'\n')
report={'checks':checks,'new_exploration_count':3,'starter_count':1,'clean_rerun_count':0,
        'unique_gpu_job_ids':len(set(jobs)),'unique_node_hashes':len(set(node_hashes)),
        'exploration_gpu_scoring_seconds':exploration_seconds,'frozen_files_changed':changed,
        'retained_best':best,'solution_matches_evaluated_bytes':True,
        'expert_lower_bound_gate':'not asserted; expert audit pending'}
(root/'segment_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'best':best,'exploration_gpu_scoring_seconds':exploration_seconds,'new_exploration_count':3,'frozen_files_changed':changed},ensure_ascii=False,indent=2))
