"""눈 시뮬레이션과 '눈덩이/눈사람 물리 오브젝트' 사이의 연결 (v1.7.0).

눈덩이는 기존 눈 더미 데이터(`Pile.cells`)에서 눈을 실제로 가져가 성장하고(take_snow),
녹을 때는 눈덩이의 눈이 줄어들 뿐 물은 만들지 않는다.
양 장부: mass_ext = 눈덩이가 품고 있는 눈. 총량 검사는 total_mass + mass_ext - (mass_added - mass_melted) = 0.
"""
from __future__ import annotations


class SnowBodies:
    def _init_bodies(self):
        self.mass_ext = 0.0       # 눈덩이 안에 들어 있는 눈의 양 (cell 단위, 장부)
        self.bodies = None        # snowman.world.SnowmanWorld (engine 이 연결)

    def take_snow(self, pile, c0: int, c1: int, frac: float, min_h: float = 0.3) -> float:
        """pile 의 열 [c0, c1] 에서 각 열 높이의 frac 만큼 눈을 가져간다 (실제 눈 데이터 감소). 가져간 양을 반환."""
        n = len(pile.cells)
        if n == 0 or frac <= 0.0:
            return 0.0
        c0 = max(0, c0)
        c1 = min(n - 1, c1)
        frac = min(1.0, frac)
        taken = 0.0
        cells = pile.cells
        for c in range(c0, c1 + 1):
            h = cells[c]
            if h < min_h:
                continue
            t = h * frac
            cells[c] = h - t
            taken += t
        if taken > 0.0:
            self.mass_ext += taken
            spill = []
            for c in (c0 - 1, c0, c1, c1 + 1):
                if 0 <= c < n:
                    spill.extend(pile.relax(c, limit=8))
            if spill:
                self._spill_to_parcels(pile, spill)
        return taken

    def push_snow(self, pile, c: int, amount: float):
        """눈덩이가 앞으로 밀어내는 눈: 열 c 의 눈 일부를 amount 부호 방향의 옆 열로 옮긴다 (v1.4.0 쟁기와 같은 방식, 질량 보존)."""
        n = len(pile.cells)
        if not (0 <= c < n) or amount == 0.0:
            return
        j = c + (1 if amount > 0 else -1)
        if not (0 <= j < n):
            return
        m = pile.cells[c] * min(0.35, abs(amount) * 0.3)
        if m <= 0.0:
            return
        pile.cells[c] -= m
        pile.cells[j] += m
        spill = []
        for k in (c, j):
            spill.extend(pile.relax(k, limit=8))
        if spill:
            self._spill_to_parcels(pile, spill)

    def spawn_external(self, mass: float):
        """새 눈덩이를 만들 때: 눈이 새로 생긴 것으로 장부에 기록 (눈 내림과 같은 취급)."""
        self.mass_ext += mass
        self.mass_added += mass

    def discard_external(self, mass: float):
        """사용자가 눈덩이/눈사람을 삭제: 눈 청소처럼 명시적인 삭제 (융해와 구분)."""
        self.mass_ext -= mass
        self.mass_added -= mass

    def melt_external(self, dm: float):
        """눈덩이가 dm 만큼 녹음: 장부상 융해로 기록 (물은 만들지 않는다)."""
        self.mass_ext -= dm
        self.mass_melted += dm
