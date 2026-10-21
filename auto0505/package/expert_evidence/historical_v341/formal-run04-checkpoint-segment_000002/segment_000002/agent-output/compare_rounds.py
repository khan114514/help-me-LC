"""Summarize completed public evaluations, including per-image changes."""
from pathlib import Path
import json

root=Path('/workspace/agent-output')
base=json.loads((root/'round_000001/metrics.json').read_text())
base_images={r['image']:r for r in base['per_image']}
results=[]
for path in sorted(root.glob('round_*/metrics.json')):
    m=json.loads(path.read_text())
    proposal=json.loads((path.parent/'proposal.json').read_text())
    g=json.loads((path.parent/'gpu_receipt.json').read_text())
    deltas=[r['psnr']-base_images[r['image']]['psnr'] for r in m['per_image']]
    row={'round':path.parent.name,'policy_name':proposal['policy_name'],'purpose':proposal['purpose'],
         'psnr':m['overall']['psnr'],'score':m['score'],'ssim':m['overall']['ssim'],
         'latent_mse':m['overall']['latent_mse'],'pixel_mse':m['overall']['pixel_mse'],
         'mean_psnr_delta':sum(deltas)/len(deltas),'improved_images':sum(d>0 for d in deltas),
         'worst_psnr_delta':min(deltas),'best_psnr_delta':max(deltas),
         'gpu_scoring_seconds':g['receipt']['scoring_seconds'],'gpu_job_id':g['job_id'],
         'per_image_delta':{r['image']:r['psnr']-base_images[r['image']]['psnr'] for r in m['per_image']}}
    results.append(row)
root.joinpath('comparison.json').write_text(json.dumps(results,indent=2)+'\n')
for row in results:
    print(json.dumps({k:v for k,v in row.items() if k!='per_image_delta'},ensure_ascii=False))
