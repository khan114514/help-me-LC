#!/usr/bin/env python3
"""onedc-quant 可信评测器（冻结，参赛者只读）。协议 v1（对齐 rfsteps v3 评分范式）。

任务面：OneDC 测试时量化决策。冻结 λ4.6 全部权重与解码端，
加载候选 method.py 的 quantize(y_res, scales, ctx)，
用真实 rANS 熵编码产出 bpp（拒绝估计比特），逐图编解码 Kodak，
计算 DISTS / LPIPS / PSNR / MS-SSIM，聚合写 metrics.json（原子写）。

用法：
  python run_eval.py --method <method.py> --out <输出目录> [--split public|hidden|full]

协议冻结项（改任何一项即视为无效轮）：
  checkpoint=lambda4.6（model.safetensors=一步 U-Net, model_1.safetensors=codec）
  图像 Kodak-24 全分辨率 PNG，评测集来自 $ONEDC_EVAL/<split>
  码率硬门：平均 bpp ≤ Baseline 同 split 码率 × bpp_cap_ratio（见 anchors.json）
  熵模型 σ（高斯, 零均值）冻结；解码端 y_hat = y_q + means_hat 冻结

归一化：score 为**未裁剪** (B - p) / (B - U)，DISTS 越低越好；
  B = naive dead-zone Baseline 锚点，U = 独立上限锚点
  （见 anchors.json upper_bound）；score_clipped 为裁剪到 [0,1] 的展示分。
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
import stat
import sys
import time
from pathlib import Path
from candidate_client import CandidateClient, CandidateError
from score import score_metrics, ContractError

class InfrastructureError(RuntimeError):
    pass

class HardGateViolation(ValueError):
    pass

REPO_SRC = os.environ.get("ONEDC_REPO_SRC", "/workspace/repo/onedc/src")
CHECKPOINT = os.environ.get("ONEDC_CHECKPOINT", "/opt/onedc/weights/lambda4.6")
EVAL_ROOT = os.environ.get("ONEDC_EVAL", "/tmp/onedc_eval")
ANCHORS = os.environ.get("ONEDC_ANCHORS", "/opt/onedc/grader/public_anchors.json")
LOCK_PATH = os.environ.get("ONEDC_LOCK", "/opt/onedc/locks/gpu.lock")
FROZEN_HASHES = os.environ.get("ONEDC_FROZEN_HASHES", "/opt/onedc/grader/frozen_hashes.txt")

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, REPO_SRC)

import numpy as np
import torch


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


def check_frozen():
    """冻结资产哈希校验（frozen_hashes.txt: "<sha256>  <relpath或绝对路径>"）。"""
    if not os.path.exists(FROZEN_HASHES):
        raise InfrastructureError("Frozen asset manifest is missing")
    bad = []
    with open(FROZEN_HASHES) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            want, path = line.split(None, 1)
            path = path.strip()
            if not os.path.exists(path):
                bad.append((path, "missing"))
                continue
            got = sha256_file(path)
            if got != want:
                bad.append((path, f"sha256 {got[:12]}.. != {want[:12]}.."))
    if bad:
        raise InfrastructureError(f"Frozen asset check failed: {bad}")
    return bad


def load_method(path):
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > (4 << 20):
        raise CandidateError("method.py must be a regular Python file of at most 4 MiB")
    return CandidateClient(candidate, device="cuda")


def make_hook(fn):
    """Double-check every tensor call and recheck repeated input fingerprints."""
    seen = {}

    def hook(y_res, scales):
        ctx = {"shape": tuple(y_res.shape), "device": str(y_res.device), "dtype": str(y_res.dtype)}
        outputs = [fn(y_res.clone(), scales.clone(), dict(ctx)) for _ in range(2)]
        converted = []
        for out in outputs:
            if not torch.is_tensor(out):
                out = torch.as_tensor(out)
            out = out.to(device=y_res.device, dtype=y_res.dtype)
            if tuple(out.shape) != tuple(y_res.shape) or not torch.isfinite(out).all():
                raise CandidateError("Candidate output has an invalid shape or nonfinite values")
            if not torch.equal(out, torch.round(out)):
                raise CandidateError("Candidate output must have integer values")
            converted.append(out)
        if not torch.equal(converted[0], converted[1]):
            raise HardGateViolation("Repeated same-input quantization produced different outputs")
        identity = hashlib.sha256(str((tuple(y_res.shape), str(y_res.dtype), str(scales.dtype))).encode()
            + y_res.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()
            + scales.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()
        result_hash = hashlib.sha256(converted[0].detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()
        if identity in seen and seen[identity] != result_hash:
            raise HardGateViolation("A previously observed input changed its quantization result")
        seen[identity] = result_hash
        return converted[0]
    return hook


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="public", choices=["public", "hidden", "full"])
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    t_start = time.time()

    check_frozen()
    if not os.path.isfile(ANCHORS):
        raise InfrastructureError("Scoring anchors are missing")

    quantize_fn = None

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
    expected_counts = {"public": 16, "hidden": 8}
    manifest_path = Path(__file__).with_name("data_manifest.json")
    manifests = json.loads(manifest_path.read_text())
    if "hidden" in splits:
        hidden_path = Path(os.environ.get("ONEDC_HIDDEN_MANIFEST", "/tests/hidden_assets/manifest.json"))
        if not hidden_path.is_file():
            raise InfrastructureError("Full evaluation requires an externally injected hidden manifest")
        manifests["hidden"] = json.loads(hidden_path.read_text())["hidden"]
    for sp in splits:
        selected = [p for split, p in images if split == sp]
        expected = manifests[sp]
        if len(selected) != expected_counts[sp] or {Path(p).name for p in selected} != set(expected):
            raise InfrastructureError("Evaluation split is missing or has unexpected images")
        if any(sha256_file(p) != expected[Path(p).name] for p in selected):
            raise InfrastructureError("Evaluation image fingerprint mismatch")

    # 单 GPU 串行：两条轨迹的评测排队
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    inherited_lease = os.environ.get('ONEDC_LEASE_FD')
    parent_queue = 0.0
    if inherited_lease is not None:
        descriptor = int(inherited_lease)
        info, expected = os.fstat(descriptor), os.stat(LOCK_PATH, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077
                or (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino)):
            raise InfrastructureError('Inherited GPU lease identity mismatch')
        parent_queue = float(os.environ['ONEDC_LEASE_QUEUE_SEC'])
        if not math.isfinite(parent_queue) or not 0 <= parent_queue <= 3600:
            raise InfrastructureError('Invalid trusted queue duration')
        lock_fd = os.fdopen(os.dup(descriptor), 'r+')
    else:
        lock_fd = open(LOCK_PATH, "w")
    print(f"[run_eval] waiting gpu lock ({LOCK_PATH}) ...", flush=True)
    queue_start = time.monotonic()
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    own_queue = time.monotonic() - queue_start
    queue_elapsed = parent_queue + own_queue
    print("[run_eval] gpu lock acquired", flush=True)

    try:
        quantize_fn = load_method(args.method)
        method_sha = quantize_fn.method_sha256
        from omegaconf import OmegaConf
        from inference import Evaluator

        args_conf = OmegaConf.create({
            "config_path": os.path.join(REPO_SRC, "config_inference.yaml"),
            "checkpoint_path": CHECKPOINT,
            "output_path": os.path.join(args.out, "pipeline"),
            "eval_image_path": os.path.join(EVAL_ROOT, splits[0]),
            "decoder_only": False,
            "decoder_bin_path": "",
            "decoder_out_path": "",
        })
        config = OmegaConf.load(os.path.join(REPO_SRC, "config_inference.yaml"))
        model_args = OmegaConf.merge(config, args_conf)
        model_args.unet_ckpt = None

        t_load = time.time()
        ev = Evaluator(model_args)
        ev.model.eval()
        print(f"[run_eval] model loaded in {time.time() - t_load:.1f}s", flush=True)

        # 注入候选量化决策（冻结钩子点：CompressionModel.process_with_mask）
        codec = ev.model.codec_model
        codec.candidate_quantize = make_hook(quantize_fn)

        from torchvision import transforms
        from torchvision.utils import save_image
        from PIL import Image
        import pandas as pd

        to_tensor = transforms.ToTensor()
        split_of = {os.path.splitext(os.path.basename(p))[0]: sp for sp, p in images}

        detail = []
        streams_dir = os.path.join(args.out, "stream")
        recon_dir = os.path.join(args.out, "recon")
        os.makedirs(streams_dir, exist_ok=True)
        os.makedirs(recon_dir, exist_ok=True)

        for sp, path in images:
            name = os.path.splitext(os.path.basename(path))[0]
            # 与官方 data/evalset.py 完全相同的预处理：ToTensor 后 [0,1]→[-1,1]
            image = (to_tensor(Image.open(path).convert("RGB")) * 2 - 1).unsqueeze(0).cuda()

            stream_file = os.path.join(streams_dir, f"{name}.bin")
            _, bpp_dict = ev.model.encode(image, fp=stream_file)
            recon = ev.model.decode(fp=stream_file)
            recon_norm = recon.clamp(-1., 1.) * 0.5 + 0.5
            save_image(recon_norm, os.path.join(recon_dir, f"{name}.png"))
            bpp_dict["image_name"] = name
            bpp_dict["split"] = split_of.get(name, splits[0])
            detail.append(bpp_dict)
            print(f"[run_eval] {name}: bpp={bpp_dict['bpp']:.5f}", flush=True)

        detail_df = pd.DataFrame(detail)
        detail_df.to_csv(os.path.join(args.out, "detail_bpp.csv"))
        bpp_mean = float(detail_df["bpp"].mean())

        # 质量指标（与官方 test_quality.py 同构造：LPIPS-alex / DISTS / PSNR / MS-SSIM）
        import lpips as lpips_lib
        from DISTS_pytorch import DISTS
        from pytorch_msssim import ms_ssim
        from PIL import Image

        lpips_metric = lpips_lib.LPIPS(net='alex').cuda()
        dists_metric = DISTS().cuda()

        def load01(path):
            a = np.array(Image.open(path).convert("RGB")).transpose(2, 0, 1)
            return torch.as_tensor(a.astype(np.float32) / 255.0).unsqueeze(0).cuda()

        per_image = []
        for d in detail:
            name = d["image_name"]
            ref_path = dict((os.path.splitext(os.path.basename(p))[0], p) for _, p in images)[name]
            ref = load01(ref_path)
            rec = load01(os.path.join(recon_dir, f"{name}.png"))
            mse = torch.mean((ref - rec) ** 2).item()
            per_image.append({
                "image": name,
                "split": d["split"],
                "bpp": float(d["bpp"]),
                "psnr": float(10 * np.log10(1.0 / max(mse, 1e-12))),
                "msssim": float(ms_ssim(ref, rec, data_range=1.0).item()),
                "lpips": float(lpips_metric(ref * 2 - 1, rec * 2 - 1).item()),
                "dists": float(dists_metric(ref, rec).item()),
            })

        def agg(rows, key):
            return float(np.mean([r[key] for r in rows]))

        metrics = {
            "split": args.split,
            "method_sha256": method_sha,
            "bpp_mean": bpp_mean,
            "bpp_per_image": {d["image_name"]: d["bpp"] for d in detail},
            "dists": agg(per_image, "dists"),
            "lpips": agg(per_image, "lpips"),
            "psnr": agg(per_image, "psnr"),
            "msssim": agg(per_image, "msssim"),
            "per_image": per_image,
            "elapsed_sec": time.time() - t_start + parent_queue,
            "queue_elapsed_sec": queue_elapsed,
            "evaluation_elapsed_sec": time.time() - t_start - own_queue,
        }
        if args.split == "full":
            for sp in ["public", "hidden"]:
                rows = [r for r in per_image if split_of.get(r["image"]) == sp]
                drows = [d for d in detail if d["split"] == sp]
                metrics[sp] = {
                    "dists": agg(rows, "dists"), "lpips": agg(rows, "lpips"),
                    "psnr": agg(rows, "psnr"), "msssim": agg(rows, "msssim"),
                    "bpp_mean": float(np.mean([d["bpp"] for d in drows])),
                    "n": len(rows),
                }

        with open(ANCHORS) as f:
            anchors = json.load(f)
        metrics.update(score_metrics(metrics, anchors, args.split))
        check_frozen()

        write_json_atomic(os.path.join(args.out, "metrics.json"), metrics)
        print(f"[run_eval] DONE bpp={bpp_mean:.5f} dists={metrics['dists']:.5f} "
              f"lpips={metrics['lpips']:.5f} score={metrics.get('score')} "
              f"elapsed={metrics['elapsed_sec']:.0f}s", flush=True)
    finally:
        try:
            if quantize_fn is not None:
                quantize_fn.close()
        finally:
            # Never unlock an inherited open-file description: its root parent
            # owns the lease until this GPU process has fully exited.
            if inherited_lease is None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        if isinstance(exc, HardGateViolation):
            failure, rc, invalid_score = "hard_gate", 0, -1.0
        elif isinstance(exc, CandidateError):
            failure, rc, invalid_score = "format_error", 2, None
        elif isinstance(exc, TimeoutError):
            failure, rc, invalid_score = "timeout", 124, None
        elif isinstance(exc, torch.cuda.OutOfMemoryError):
            failure, rc, invalid_score = "resource_limit", 137, None
        else:
            failure, rc, invalid_score = "infrastructure_error", 3, None
        if "--out" in sys.argv and sys.argv.index("--out") + 1 < len(sys.argv):
            out = sys.argv[sys.argv.index("--out") + 1]
            os.makedirs(out, exist_ok=True)
            write_json_atomic(os.path.join(out, "metrics.json"), {
                "status": failure, "valid": False, "failure_type": failure,
                "score": invalid_score, "error": type(exc).__name__ + ": " + str(exc)[:500],
            })
        print("[run_eval] " + failure + ": " + str(exc)[:500], file=sys.stderr)
        raise SystemExit(rc)
