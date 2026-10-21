#!/usr/bin/env python3
"""通道敏感度标定（出题方 U 锚点用，不进 workspace）。

流程：
1. 对 N_CAL 张 public 图，用 capture 钩子抓全部 4 个 mask 阶段的 (y_res, scales)，
   并以官方 round 走完基线编解码，记录 recon0 与 DISTS0、bpp0。
2. 把 y 的 C 个通道均分 G 组；逐组施加 +1（再 -1）的整值扰动
   （经 candidate_quantize 接口，与参赛者可用手段完全一致），
   真实熵编码 + 全管线解码，记录 DISTS 增量与 bpp 增量。
3. 敏感度 w_g = 0.5*(|ΔDISTS_{g,+}| + |ΔDISTS_{g,-}|)，跨图取均值，
   归一化 mean(w)=1，写 channel_sens.json。
"""
import os, sys, json
import torch
import numpy as np
from PIL import Image
from torchvision import transforms

REPO_SRC = os.environ.get("ONEDC_REPO_SRC", "/workspace/repo/onedc/src")
sys.path.insert(0, REPO_SRC)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

CHECKPOINT = os.environ.get("ONEDC_CHECKPOINT", "/opt/onedc/weights/lambda4.6")
EVAL_PUBLIC = "/workspace/public_assets/eval_public"
N_CAL = 6
G = 16

from omegaconf import OmegaConf
from inference import Evaluator
from DISTS_pytorch import DISTS

args_conf = OmegaConf.create({
    "config_path": os.path.join(REPO_SRC, "config_inference.yaml"),
    "checkpoint_path": CHECKPOINT,
    "output_path": "/tmp/calib_sens",
    "eval_image_path": EVAL_PUBLIC,
    "decoder_only": False, "decoder_bin_path": "", "decoder_out_path": "",
})
config = OmegaConf.load(os.path.join(REPO_SRC, "config_inference.yaml"))
a = OmegaConf.merge(config, args_conf)
a.unet_ckpt = None
ev = Evaluator(a)
codec = ev.model.codec_model

to_tensor = transforms.ToTensor()
dists_metric = DISTS().cuda()

def load01(p):
    return torch.as_tensor(
        np.array(Image.open(p).convert("RGB")).transpose(2, 0, 1).astype(np.float32) / 255.0
    ).unsqueeze(0).cuda()

images = sorted(f for f in os.listdir(EVAL_PUBLIC) if f.endswith(".png"))[:N_CAL]

captured = []

def make_capture():
    parts = []
    def hook(y_res, scales):
        parts.append((y_res.detach().clone(), scales.detach().clone()))
        return torch.round(y_res)
    hook.parts = parts
    return hook

def run_one(img_path, quant_fn):
    codec.candidate_quantize = quant_fn
    img = (to_tensor(Image.open(img_path).convert("RGB")) * 2 - 1).unsqueeze(0).cuda()
    bs, bpp_dict = ev.model.encode(img)
    recon = ev.model.decode(stream=bs)
    recon01 = (recon.clamp(-1., 1.) * 0.5 + 0.5)
    return recon01, bpp_dict["bpp"]

results = {}
for fn in images:
    name = os.path.splitext(fn)[0]
    path = os.path.join(EVAL_PUBLIC, fn)
    ref = load01(path)

    hook = make_capture()
    recon0, bpp0 = run_one(path, hook)
    d0 = dists_metric(ref, recon0).item()
    C = hook.parts[0][0].shape[1]
    groups = [list(range(i * C // G, (i + 1) * C // G)) for i in range(G)]
    print(f"[calib] {name}: C={C} baseline dists={d0:.5f} bpp={bpp0:.5f}", flush=True)

    sens = np.zeros(G)
    for gi, chs in enumerate(groups):
        deltas = []
        for sign in (+1, -1):
            def make_pert(chs=chs, sign=sign):
                idx = {"k": 0}
                def hook2(y_res, scales):
                    q = torch.round(y_res)
                    q[:, chs] += sign
                    return q
                return hook2
            recon_g, bpp_g = run_one(path, make_pert())
            dg = dists_metric(ref, recon_g).item()
            deltas.append(abs(dg - d0))
        sens[gi] = float(np.mean(deltas))
        print(f"[calib] {name} group{gi}: dDISTS+={deltas[0]:.5f} dDISTS-={deltas[1]:.5f}", flush=True)
    results[name] = {"d0": d0, "bpp0": bpp0, "sens": sens.tolist(), "C": C}

W = np.mean([results[n]["sens"] for n in results], axis=0)
W = W / max(W.mean(), 1e-12)
out = {
    "G": G, "C": C, "images": list(results.keys()),
    "sens_normalized": W.tolist(),
    "per_image": results,
}
with open("/tmp/onedc-research/channel_sens.json", "w") as f:
    json.dump(out, f, indent=2)
print("[calib] DONE w =", np.round(W, 4).tolist())
