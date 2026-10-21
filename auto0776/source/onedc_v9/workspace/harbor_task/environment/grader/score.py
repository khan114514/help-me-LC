"""Pure scoring contract; invalid methods are excluded from valid ranking."""
import math


class ContractError(ValueError):
    pass


def score_metrics(metrics, anchors, split):
    try:
        b = float(anchors["baseline"][split]["dists"])
        u = float(anchors["upper_bound"][split]["dists"])
        ratio = float(anchors["bpp_cap_ratio"])
        if not all(math.isfinite(x) for x in (b, u, ratio)) or b <= u or ratio <= 0:
            raise ContractError("Invalid scoring anchors")
        splits = ("public", "hidden") if split == "full" else (split,)
        caps = {}
        for sp in splits:
            cap = float(anchors["baseline_bpp"][sp]) * ratio
            measured = float(metrics[sp]["bpp_mean"] if split == "full" else metrics["bpp_mean"])
            if not math.isfinite(cap) or not math.isfinite(measured) or cap <= 0 or measured < 0:
                raise ContractError("Invalid measured bitrate")
            caps[sp] = cap
        p = float(metrics["dists"])
        if not math.isfinite(p):
            raise ContractError("Nonfinite distortion")
        passed = all(float(metrics[sp]["bpp_mean"] if split == "full" else metrics["bpp_mean"]) <= caps[sp] for sp in splits)
        raw_score = (b - p) / (b - u)
        return {
            "status": "ok" if passed else "hard_gate",
            "valid": passed,
            "failure_type": None if passed else "hard_gate",
            "score": raw_score if passed else -1.0,
            "score_clipped": max(0.0, min(1.0, raw_score)) if passed else None,
            "bpp_in_window": passed,
            "bpp_cap": caps if split == "full" else caps[split],
            "anchors": {"baseline_dists": b, "upper_bound_dists": u},
            "violation": None if passed else "Mean bitrate exceeds the frozen split cap",
        }
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("Missing or malformed scoring input") from exc
