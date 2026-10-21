"""候选 R2：正弦 schedule，t = sin(s*pi/2)，s 均匀 1→0。

步长在高 t 端（噪声端）更密、低 t 端更疏。
"""

import math


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    ts = [math.sin((1.0 - i / num_steps) * math.pi / 2) for i in range(num_steps + 1)]
    ts[0] = 1.0
    ts[-1] = 0.0
    return ts
