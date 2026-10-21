"""One-budget exchange with a upper-part-biased split of the final interval.

The reference time embedding multiplies a BF16 time by 1000 before FP32
conversion.  Nodes on a 1/125 grid and their 1/250 midpoints survive that
scaled conversion exactly.  Enforce one grid cell per interval.
"""


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    raw = [1.0 - (i / num_steps) ** 2 for i in range(num_steps + 1)]
    resolution = 125
    if num_steps <= resolution:
        bins = [resolution]
        for i in range(1, num_steps):
            target = round(resolution * raw[i])
            target = max(num_steps - i, min(bins[-1] - 1, target))
            bins.append(target)
        bins.append(0)
        nodes = [k / resolution for k in bins]
    else:
        nodes = raw
    if 4 <= num_steps <= resolution:
        # Preserve the first endpoint interval and merge the smallest interior pair.
        remove = min(range(2, len(nodes) - 1),
                     key=lambda i: (nodes[i - 1] - nodes[i + 1], i))
        nodes.pop(remove)
        # Spend the recovered interval on the largest splittable grid gap.
        candidates = [i for i in range(len(nodes) - 1)
                      if round(resolution * (nodes[i] - nodes[i + 1])) >= 2]
        if candidates:
            split = max(candidates, key=lambda i: (nodes[i] - nodes[i + 1], i))
            upper = round(resolution * nodes[split])
            lower = round(resolution * nodes[split + 1])
            middle = max(lower + 1, min(upper - 1, round((upper + lower) / 2)))
            nodes.insert(split + 1, middle / resolution)
        else:
            nodes = [1.0 - (i / num_steps) ** 2 for i in range(num_steps + 1)]
    if 2 <= num_steps <= resolution:
        upper = round(resolution * nodes[-3])
        if upper >= 2:
            low_time = max(1, min(upper - 1, round(0.6 * upper)))
            nodes[-2] = low_time / resolution
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes
