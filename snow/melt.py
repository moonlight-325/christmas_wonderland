"""눈 용해 (v1.4.0 복원): 온도 -> 용해 속도, 눈더미 열(column)별 용해.

기준 용해 속도(cell/s)는 온도 시스템(`SnowSim.melt_rate()` = `physics.melt_rate_for`, 자동 날씨 적용값 포함)이 정하고,
v1.4.0 처럼 열 높이가 높을수록 조금 더 많이 줄어든다: `v -= base * dt * (0.4 + min(v, 6) * 0.2)`.
v1.9.x 의 열별 노출 면적/두께/밀도/숙성도 보정은 v1.4.0 에 없으므로 사용하지 않는다.
녹은 눈은 사라질 뿐 물이 되지 않으며, 줄어든 양은 `mass_melted` 장부에 기록된다.
"""
from __future__ import annotations

MELT_TICK = 0.25         # 용해 계산 간격 (초) - v1.4.0 과 같음


class SnowMelt:
    """SnowSim 에 섞이는 믹스인: 열별 용해."""

    def _melt(self, dt: float):
        base = self.melt_rate()
        if base <= 0:
            return
        amount = base * dt
        melted = 0.0
        for pile in self.piles.values():
            cells = pile.cells
            for i, v in enumerate(cells):
                if v > 0.0:
                    nv = v - amount * (0.4 + min(v, 6.0) * 0.2)
                    if nv <= 0.02:                        # v1.4.0: 아주 얇게 남은 눈은 마저 녹는다
                        nv = 0.0
                    cells[i] = nv
                    melted += v - nv
        if melted > 0.0:
            self.mass_melted += melted
