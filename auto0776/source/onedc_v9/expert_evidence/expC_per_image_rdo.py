#!/usr/bin/env python3
"""面 C 最小实验 v2：per-image 潜变量 RDO（近似 RD 点，GO/NO-GO 用）。

基线与优化走同一条可微解码近似链（固定上下文），对比公平；
bpp 用冻结 σ 模型预测（Phase 0 已验证预测≈真实 rANS 到 1e-6）。
"""
import os, sys, math, json, argparse
import torch
import numpy as np
from PIL import Image
from torchvision import transforms

REPO_SRC = os.environ.get("ONEDC_REPO_SRC", "/workspace/repo/onedc/src")
sys.path.insert(0, REPO_SRC)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ap = argparse.ArgumentParser()
ap.add_argument("--image", required=True)
ap.add_argument("--lams", default="0.03,0.1,0.3")
ap.add_argument("--iters", type=int, default=300)
ap.add_argument("--lr", type=float, default=0.005)
ap.add_argument("--out", default="/tmp/onedc-research/expC")
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

from omegaconf import OmegaConf
from einops import rearrange
from inference import Evaluator
from DISTS_pytorch import DISTS
from modules.dmd.utils import get_x0_from_noise
from modules.entropy.utils import get_padding_size
import modules.entropy.compression_model as CM

CHECKPOINT = "/opt/onedc/weights/lambda4.6"
args_conf = OmegaConf.create({
    "config_path": os.path.join(REPO_SRC, "config_inference.yaml"),
    "checkpoint_path": CHECKPOINT,
    "output_path": os.path.join(args.out, "pipeline"),
    "eval_image_path": os.path.dirname(args.image),
    "decoder_only": False, "decoder_bin_path": "", "decoder_out_path": "",
})
config = OmegaConf.load(os.path.join(REPO_SRC, "config_inference.yaml"))
a = OmegaConf.merge(config, args_conf)
a.unet_ckpt = None
ev = Evaluator(a)
model = ev.model
codec = model.codec_model

to_tensor = transforms.ToTensor()
dists_metric = DISTS().cuda()
name = os.path.splitext(os.path.basename(args.image))[0]
ref01 = torch.as_tensor(
    np.array(Image.open(args.image).convert("RGB")).transpose(2, 0, 1).astype(np.float32) / 255.0
).unsqueeze(0).cuda()
img_m11 = ref01 * 2 - 1
_, _, H, W = img_m11.shape
pix_num = H * W

# ---- 抓取 4 个 mask 阶段 ----
captured = []
orig_pwm = CM.CompressionModel.process_with_mask
def capture_pwm(self, y, scales, means, mask):
    scales_hat = scales * mask
    means_hat = means * mask
    y_res = (y - means_hat) * mask
    y_q = self.quant(y_res)
    captured.append({"scales": scales_hat.detach().clone(), "means": means_hat.detach().clone(),
                     "y_res": y_res.detach().clone(), "y_q": y_q.detach().clone()})
    y_hat = y_q + means_hat
    return y_res, y_q, y_hat, scales_hat
CM.CompressionModel.process_with_mask = capture_pwm

with torch.no_grad():
    pl, pr, pt, pb = get_padding_size(H, W, p=codec.ds)
    img_pad = torch.nn.functional.pad(img_m11, (pl, pr, pt, pb), mode="replicate")
    x_latent = model.vae_encode_image(img_pad)
    stream0, bpp0 = codec.encode(img_pad.float(), x_latent.float(), W, H)
CM.CompressionModel.process_with_mask = orig_pwm
assert len(captured) == 4, f"parts={len(captured)}"

with torch.no_grad():
    y_enc, sem = codec.enc(img_pad.float(), x_latent.float())
    z = codec.hyper_enc(y_enc, sem)
    z_hat, z_idx = codec.z_vq(z)
    params, z_semantic = codec.hyper_dec(z_hat)
    y_semantic = codec.semantic_adaptor(z_semantic)

def decode_image_from_q(q_parts):
    y_hat = sum(q + p["means"] for q, p in zip(q_parts, captured))
    x_hat = codec.dec(y_hat, y_semantic)
    sem_seq = rearrange(y_semantic, 'b c h w -> b (h w) c').contiguous()
    ts = torch.ones(1, device=y_hat.device, dtype=torch.long) * model.conditioning_timestep
    sample, dummy_noise = model.feedforward_model(
        sample=x_hat, timestep=ts.long(),
        encoder_hidden_states=sem_seq, added_cond_kwargs=None)
    x0 = get_x0_from_noise(dummy_noise.double(), sample.double(),
                           model.alphas_cumprod.double(), ts).float()
    pred = model.vae_decode_image(x0)
    return torch.nn.functional.pad(pred, (-pl, -pr, -pt, -pb))

def bits_of(q, sigma):
    sigma = sigma.clamp(1e-5, 1e10)
    norm = torch.distributions.normal.Normal(torch.zeros_like(sigma), sigma)
    p = norm.cdf(q + 0.5) - norm.cdf(q - 0.5)
    return -torch.log(p + 1e-10) / math.log(2.0)

def pred_bpp(q_parts):
    return sum(bits_of(q, p["scales"]).sum() for q, p in zip(q_parts, captured)).item() / pix_num

# ---- 基线（同一近似链）----
with torch.no_grad():
    recon0 = decode_image_from_q([p["y_q"] for p in captured])
d0 = dists_metric(ref01, (recon0.clamp(-1., 1.) * 0.5 + 0.5)).item()
bpp_y0 = pred_bpp([p["y_q"] for p in captured])
print(f"[expC] {name} baseline(approx-chain): bpp_y={bpp_y0:.5f} (real {bpp0['bpp']:.5f}) dists={d0:.5f}", flush=True)

results = {"image": name, "baseline": {"bpp_y": bpp_y0, "bpp_real": bpp0["bpp"], "dists": d0}, "runs": []}
for lam in [float(x) for x in args.lams.split(",")]:
    deltas = [torch.zeros_like(p["y_q"]).requires_grad_(True) for p in captured]
    opt = torch.optim.Adam(deltas, lr=args.lr)
    for it in range(args.iters):
        opt.zero_grad()
        q_st = []
        for p, d in zip(captured, deltas):
            q = p["y_q"] + d
            q_st.append(q + (torch.round(q) - q).detach())
        pred = decode_image_from_q(q_st)
        pred01 = pred.clamp(-1., 1.) * 0.5 + 0.5
        d_loss = dists_metric(ref01, pred01)
        b_loss = sum(bits_of(q, p["scales"]).sum() for q, p in zip(q_st, captured)) / pix_num
        loss = d_loss + lam * b_loss
        loss.backward()
        opt.step()
    with torch.no_grad():
        q_final = [torch.round(p["y_q"] + d) for p, d in zip(captured, deltas)]
        recon1 = decode_image_from_q(q_final)
        d1 = dists_metric(ref01, (recon1.clamp(-1., 1.) * 0.5 + 0.5)).item()
        bpp1 = pred_bpp(q_final)
        dchg = sum((qf - p["y_q"]).abs().gt(0).float().mean().item() for qf, p in zip(q_final, captured)) / 4
    print(f"[expC] {name} lam={lam}: bpp_pred={bpp1:.5f} dists={d1:.5f} changed={dchg:.3f}", flush=True)
    results["runs"].append({"lam": lam, "bpp_pred": bpp1, "dists": d1, "frac_changed": dchg})

outj = os.path.join(args.out, f"expC_{name}.json")
with open(outj, "w") as f:
    json.dump(results, f, indent=2)
print("[expC] wrote", outj)
