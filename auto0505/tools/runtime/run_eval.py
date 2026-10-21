#!/usr/bin/env python3
"""rfsteps 可信评测器（冻结，参赛者只读）。协议 v3。

固定 NFE 下评测 RF-Solver 反演-重建误差：
  加载候选 method.py 的 get_timesteps(num_steps, image_seq_len)，
  用同一份 schedule 做 inversion（inverse=True）与 reconstruction（inverse=False），
  逐图计算 PSNR / SSIM / 像素 MSE / latent MSE，聚合写 metrics.json（原子写）。

用法：
  python run_eval.py --method <method.py> --out <输出目录> [--split public|hidden|full]

协议冻结项（改任何一项即视为无效轮）：
  num_steps=25（26 个时间点，双向各 50 NFE，每图共 100 NFE）
  模型 flux-dev（bf16），prompt=""（双向），guidance=1，inject=0
  图像 512x512 PNG，评测集来自 $RFSTEPS_EVAL/<split>

归一化（v3 起）：score 为**未裁剪** (psnr - B) / (U - B)，
  B = 官方 Baseline 锚点，U = 独立上限锚点（双轨实测最强 schedule，
  见 anchors.json upper_bound）；score_clipped 为裁剪到 [0,1] 的展示分。
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import sys
import time

REPO_SRC = os.environ.get("RFSTEPS_REPO_SRC", "/workspace/repo/RF-Solver-Edit/FLUX_Image_Edit/src")
WEIGHTS = os.environ.get("RFSTEPS_WEIGHTS", "/opt/rfsteps/weights")
EVAL_ROOT = os.environ.get("RFSTEPS_EVAL", "/tmp/rfsteps_eval")
ANCHORS = os.environ.get("RFSTEPS_ANCHORS", "/workspace/tests/anchors.json")
LOCK_PATH = os.environ.get("RFSTEPS_LOCK", "/tmp/rfsteps_gpu_eval.lock")
NUM_STEPS = 25

# configs 在 import flux.util 时读取 env，必须先设
os.environ.setdefault("FLUX_DEV", f"{WEIGHTS}/flux-dev/flux1-dev.safetensors")
os.environ.setdefault("AE", f"{WEIGHTS}/flux-schnell/ae.safetensors")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, REPO_SRC)

import numpy as np
import torch
from einops import rearrange, repeat
from PIL import Image

from flux.sampling import denoise, unpack
from flux.util import load_ae, load_flow_model
from flux.modules.conditioner import HFEmbedder


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path, obj):
    """先写同目录临时文件再 os.replace 原子替换，避免半截结果文件。"""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def validate_schedule(ts, num_steps=NUM_STEPS):
    """schedule 合法性：长度 num_steps+1、端点 1→0、单调不增、取值 [0,1]、有限。"""
    if not isinstance(ts, (list, tuple)):
        raise ValueError("schedule 必须是 list/tuple")
    ts = [float(x) for x in ts]
    if len(ts) != num_steps + 1:
        raise ValueError(f"schedule 长度必须等于 num_steps+1={num_steps + 1}，实际 {len(ts)}（NFE 冻结）")
    if not all(np.isfinite(ts)):
        raise ValueError("schedule 含非有限值")
    if abs(ts[0] - 1.0) > 1e-6 or abs(ts[-1] - 0.0) > 1e-6:
        raise ValueError(f"端点必须为 1.0 → 0.0，实际 {ts[0]} → {ts[-1]}")
    if any(t < -1e-9 or t > 1 + 1e-9 for t in ts):
        raise ValueError("schedule 取值必须在 [0,1]")
    if any(ts[i] < ts[i + 1] - 1e-12 for i in range(len(ts) - 1)):
        raise ValueError("schedule 必须单调不增（从 1 到 0）")
    if all(ts[i] == ts[i + 1] for i in range(len(ts) - 1)):
        raise ValueError("schedule 退化为常数")
    return ts


def load_method(path):
    spec = importlib.util.spec_from_file_location("candidate_method", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    fn = getattr(m, "get_timesteps", None)
    if not callable(fn):
        raise ValueError("method.py 必须提供可调用函数 get_timesteps(num_steps, image_seq_len)")
    return fn


@torch.inference_mode()
def encode_image(img_np, ae, device):
    x = torch.from_numpy(img_np).permute(2, 0, 1).float() / 127.5 - 1
    x = x.unsqueeze(0).to(device)
    return ae.encode(x).to(torch.bfloat16)


@torch.inference_mode()
def decode_latent(x, ae, height, width):
    batch = unpack(x.float(), height, width)
    with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        out = ae.decode(batch)
    out = out.clamp(-1, 1)
    return (127.5 * (out[0].permute(1, 2, 0).float().cpu().numpy() + 1.0)).clip(0, 255).astype(np.uint8)


def psnr(a, b):
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    if mse <= 1e-12:
        return 99.0
    return 10 * np.log10(255.0 ** 2 / mse)


def ssim(a, b):
    from skimage.metrics import structural_similarity
    return float(structural_similarity(a, b, channel_axis=2, data_range=255))


@torch.inference_mode()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="public", choices=["public", "hidden", "full"])
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    t_start = time.time()

    get_timesteps = load_method(args.method)
    method_sha = sha256_file(args.method)

    if args.split == "full":
        splits = ["public", "hidden"]
    else:
        splits = [args.split]
    images = []
    for sp in splits:
        d = os.path.join(EVAL_ROOT, sp)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".png"):
                images.append((sp, os.path.join(d, fn)))
    if not images:
        raise SystemExit(f"评测集为空: {args.split}")

    # 单 GPU 串行：两条轨迹的评测排队
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock_fd = open(LOCK_PATH, "w")
    print(f"[run_eval] waiting gpu lock ({LOCK_PATH}) ...", flush=True)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    print("[run_eval] gpu lock acquired", flush=True)

    device = "cuda"
    try:
        t_load = time.time()
        # prompt 恒为 ""：文本嵌入只算一次，随后把 T5/CLIP 挪回 CPU（A100-40G 显存硬约束）
        t5 = HFEmbedder(f"{WEIGHTS}/t5-encoder-bf16", max_length=512, is_clip=False,
                        torch_dtype=torch.bfloat16).to(device)
        clip = HFEmbedder(f"{WEIGHTS}/clip-vit-l14", max_length=77, is_clip=True,
                          torch_dtype=torch.bfloat16).to(device)
        txt = t5([""])
        vec = clip([""])
        txt_ids = torch.zeros(1, txt.shape[1], 3, device=device)
        t5, clip = t5.cpu(), clip.cpu()
        del t5, clip
        torch.cuda.empty_cache()

        model = load_flow_model("flux-dev", device=device)
        ae = load_ae("flux-dev", device=device)
        print(f"[run_eval] models loaded in {time.time() - t_load:.1f}s "
              f"(TEs offloaded, prompt cached)", flush=True)

        def prepare_cached(img):
            # 与 flux.sampling.prepare 等价，但复用缓存的空 prompt 文本嵌入
            bs = img.shape[0]
            h, w = img.shape[2] // 2, img.shape[3] // 2
            img = rearrange(img, "b c (h ph) (w pw) -> b (h w) (c ph pw)", ph=2, pw=2)
            img_ids = torch.zeros(h, w, 3)
            img_ids[..., 1] += torch.arange(h)[:, None]
            img_ids[..., 2] += torch.arange(w)[None, :]
            img_ids = repeat(img_ids, "h w c -> b (h w) c", b=bs)
            return {"img": img, "img_ids": img_ids.to(img.device),
                    "txt": txt, "txt_ids": txt_ids, "vec": vec}

        seq_len = (512 // 16) ** 2  # 1024
        raw_ts = get_timesteps(NUM_STEPS, seq_len)
        timesteps = validate_schedule(list(raw_ts))
        write_json_atomic(os.path.join(args.out, "schedule.json"),
                          {"num_steps": NUM_STEPS, "timesteps": timesteps})

        info = {"feature_path": os.path.join(args.out, "feature"),
                "feature": {}, "inject_step": 0}
        os.makedirs(info["feature_path"], exist_ok=True)

        per_image = []
        for sp, path in images:
            name = os.path.splitext(os.path.basename(path))[0]
            img_np = np.array(Image.open(path).convert("RGB"))
            init = encode_image(img_np, ae, device)

            inp = prepare_cached(init)
            z, _ = denoise(model, **inp, timesteps=timesteps, guidance=1,
                           inverse=True, info=info)
            inp_t = prepare_cached(init)
            inp_t["img"] = z
            x, _ = denoise(model, **inp_t, timesteps=timesteps, guidance=1,
                           inverse=False, info=info)

            recon = decode_latent(x, ae, 512, 512)
            latent_mse = float(torch.mean((unpack(x.float(), 512, 512) - init.float()) ** 2).item())

            Image.fromarray(recon).save(os.path.join(args.out, f"recon_{name}.png"))
            rec = {
                "split": sp, "image": name,
                "psnr": psnr(img_np, recon),
                "ssim": ssim(img_np, recon),
                "pixel_mse": float(np.mean((img_np.astype(np.float64) - recon.astype(np.float64)) ** 2)),
                "latent_mse": latent_mse,
            }
            per_image.append(rec)
            print(f"[run_eval] {sp}/{name}: psnr={rec['psnr']:.3f} ssim={rec['ssim']:.4f}", flush=True)

        def agg(rows):
            return {
                "psnr": float(np.mean([r["psnr"] for r in rows])),
                "ssim": float(np.mean([r["ssim"] for r in rows])),
                "pixel_mse": float(np.mean([r["pixel_mse"] for r in rows])),
                "latent_mse": float(np.mean([r["latent_mse"] for r in rows])),
                "n": len(rows),
            }

        metrics = {
            "split": args.split,
            "num_steps": NUM_STEPS,
            "nfe_per_image": NUM_STEPS * 2 * 2,
            "method_sha256": method_sha,
            "overall": agg(per_image),
            "public": agg([r for r in per_image if r["split"] == "public"]) if args.split == "full" else None,
            "hidden": agg([r for r in per_image if r["split"] == "hidden"]) if args.split == "full" else None,
            "per_image": per_image,
            "elapsed_sec": time.time() - t_start,
        }

        # 锚点归一化（v3：独立上限 U；score 未裁剪，score_clipped 为展示分）
        if os.path.exists(ANCHORS):
            with open(ANCHORS) as f:
                anchors = json.load(f)
            key = args.split if args.split != "full" else "full"
            b = anchors.get("baseline", {}).get(key, {}).get("psnr")
            u = anchors.get("upper_bound", {}).get(key, {}).get("psnr")
            if u is None:  # 兼容 v2 锚点（U≡Reference）
                u = anchors.get("reference", {}).get(key, {}).get("psnr")
            if b is not None and u is not None and u > b:
                p = metrics["overall"]["psnr"]
                score = (p - b) / (u - b)
                metrics["score"] = score
                metrics["score_clipped"] = max(0.0, min(1.0, score))
                metrics["anchors"] = {"baseline_psnr": b, "upper_bound_psnr": u}

        write_json_atomic(os.path.join(args.out, "metrics.json"), metrics)
        print(f"[run_eval] DONE psnr={metrics['overall']['psnr']:.4f} "
              f"ssim={metrics['overall']['ssim']:.4f} "
              f"score={metrics.get('score')} elapsed={metrics['elapsed_sec']:.0f}s", flush=True)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    main()
