"""RF-Solver 最优时间步分配：反向幂律 (reverse power law)。

t(i) = 1 - (i/N)^p，其中 p = 1.2

核心发现：
- 步长减速增长（decelerating growth）形状最优
- 最优浓度比约 2.3x（首步:末步 ≈ 1:2.3）
- 比官方 time_shift baseline (+2.3dB)、参考 sine schedule (+1.4dB) 均显著提升
- 形状效应 > 浓度比效应：相同浓度比下，减速增长（rev_power）比 S 型（time_shift）好 1.3dB，
  比加速增长（几何级数）好 1.2dB

理论解释：RF-Solver 二阶 Taylor 方法的局部截断误差在 t≈1（高噪声端）较高，
向 t≈0 方向逐渐降低。反向幂律的步长分布（先快增后慢增）与误差密度
匹配最佳，实现了近似的误差等分布。
"""

import math


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    """Reverse power law schedule: t(i) = 1 - (i/N)^p.

    步长单调递增（t≈1 处最小，t≈0 处最大），增长率递减（减速增长）。
    p=1.2 时浓度比约 2.3x，为实验最优值。

    Args:
        num_steps: 步数（固定 25）
        image_seq_len: 图像 token 序列长度（512×512 对应 1024）

    Returns:
        长度为 num_steps+1 的时间点列表，从 1.0 单调不降到 0.0
    """
    p = 1.2
    ts = []
    for i in range(num_steps + 1):
        t = 1.0 - (i / num_steps) ** p
        ts.append(max(0.0, min(1.0, t)))
    ts[0] = 1.0
    ts[-1] = 0.0
    return ts
