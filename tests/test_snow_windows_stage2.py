"""v1.9.6 Stage 2: 창 독립 시스템 연결 점검 (PySide6 불필요).

v1.4.0 쌓인 눈 물리 위에서 창 이동(빠르게/연속)·크기 변경·닫힘/재열림·음수 좌표(다중 모니터)·눈덩이가
질량 장부(mass_balance)를 깨지 않고, 값이 NaN 이 되지 않으며, 최대 높이(v1.4.0 x 2)를 지키는지 무작위로 확인한다.
"""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import Rect, SnowSim, SurfaceInfo
from snow.matter import is_ground

DT = 1 / 30


def surf(key, left, top, width):
    seg = [(left, left + width)]
    return SurfaceInfo(key, left, top, left + width, seg, seg)


def make(seed, bounds=Rect(-1920, 0, 1920, 1080), **kw):
    sim = SnowSim(seed=seed)
    sim.cell = 3
    sim.set_bounds(bounds)
    base = dict(amount=250, accumulate=60, accumulate_rate=100, temperature=-12, wind_strength=20, cursor_on=False)
    base.update(kw)
    sim.configure(**base)
    return sim


def finite(sim):
    for p in sim.piles.values():
        for h in p.cells:
            if not math.isfinite(h) or h < -1e-9:
                return False
    for f in sim.parcels:
        if not all(math.isfinite(v) for v in (f.x, f.y, f.vx, f.vy, f.carry)):
            return False
    return True


class WindowStress(unittest.TestCase):
    def assertOK(self, sim, msg=""):
        self.assertTrue(finite(sim), msg + " 비정상 값")
        self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=max(1e-6, sim.total_mass() * 1e-9), msg=msg)

    def test_random_window_chaos_multi_monitor(self):
        rng = random.Random(7)
        sim = make(5)
        wins = {f"w{i}": [rng.randint(-1800, 800), rng.randint(150, 800), rng.randint(300, 900)] for i in range(5)}
        for k in range(30 * 90):
            if k % 3 == 0:                                  # 약 10Hz 로 창 상태 갱신
                for key, w in list(wins.items()):
                    r = rng.random()
                    if r < 0.15:                            # 빠른 이동
                        w[0] += rng.randint(-400, 400)
                        w[1] += rng.randint(-200, 200)
                    elif r < 0.25:                          # 크기 변경
                        w[2] = max(200, w[2] + rng.randint(-250, 250))
                    w[0] = max(-1900, min(1500, w[0]))
                    w[1] = max(100, min(950, w[1]))
                live = [surf(key, *w) for key, w in wins.items() if rng.random() > 0.04]   # 가끔 한 프레임 누락(최소화 흉내)
                sim.set_surfaces(live)
            sim.step(DT)
            if k % 90 == 89:
                self.assertOK(sim, f"k={k}")
        self.assertGreater(sim.total_mass(), 20)

    def test_close_reopen_cycles_conserve(self):
        sim = make(2)
        for cycle in range(6):
            sim.set_surfaces([surf("a", 100, 500, 800), surf("b", 300, 300, 800)])
            for _ in range(60):
                sim.step(DT)
            sim.set_surfaces([surf("b", 300, 300, 800)])
            sim.set_surfaces([surf("b", 300, 300, 800)])
            sim.set_surfaces([surf("b", 300, 300, 800)])
            for _ in range(45):
                sim.step(DT)
            self.assertOK(sim, f"cycle {cycle}")
        self.assertNotIn("a", sim.piles)

    def test_continuous_fast_drag_then_rest(self):
        """창을 연속으로 빠르게 끌다 놓으면 눈이 사라지거나 복제되지 않고, 놓은 뒤 다시 쌓인다."""
        sim = make(9, bounds=Rect(0, 0, 1920, 1080))
        sim.set_surfaces([surf("w", 200, 500, 900)])
        for _ in range(30 * 8):
            sim.step(DT)
        m0 = sim.piles["w"].total()
        self.assertGreater(m0, 0)
        x = 200
        for k in range(60):                                  # 2초 동안 매 프레임 60px
            x += 60 if (k // 15) % 2 == 0 else -60
            sim.set_surfaces([surf("w", x, 500, 900)])
            sim.step(DT)
            self.assertOK(sim, f"drag {k}")
        self.assertGreater(len(sim.parcels) + len(sim._reservoir), 0)       # 눈이 창에서 분리되어 월드에 있음
        for _ in range(30 * 20):
            sim.set_surfaces([surf("w", x, 500, 900)])
            sim.step(DT)
        self.assertOK(sim)
        self.assertGreater(sim.piles["w"].total(), 0)         # 이동이 끝난 뒤에도 쌓임

    def test_max_height_is_double_v140_everywhere(self):
        sim = make(4, bounds=Rect(0, 0, 1920, 1080), amount=700, accumulate=50, accumulate_rate=100, temperature=-20)
        sim.set_surfaces([surf("w", 300, 400, 600), surf("x", 1000, 700, 700)])
        for _ in range(30 * 120):
            sim.set_surfaces([surf("w", 300, 400, 600), surf("x", 1000, 700, 700)])
            sim.step(DT)
        cap = (2.0 + 50 / 100.0 * 14.0) * 2
        self.assertAlmostEqual(sim.max_cells, cap)
        for k, p in sim.piles.items():
            self.assertLessEqual(max(p.cells) if p.cells else 0.0, cap + 1.0, k)    # relax 허용 오차 1 cell
        self.assertOK(sim)

    def test_snowball_take_and_push_with_window_motion(self):
        sim = make(6, bounds=Rect(0, 0, 1920, 1080))
        sim.set_surfaces([surf("w", 300, 500, 900)])
        for _ in range(30 * 20):
            sim.step(DT)
        p = sim.piles["w"]
        got = sim.take_snow(p, 10, 40, 0.5)
        sim.push_snow(p, 60, 1.0)
        sim.push_snow(p, 61, -1.0)
        self.assertGreater(got, 0)
        for k in range(1, 12):
            sim.set_surfaces([surf("w", 300 + 80 * k, 500, 900)])
            sim.step(DT)
        self.assertOK(sim)
        sim.melt_external(got * 0.2)
        sim.discard_external(got * 0.3)
        self.assertOK(sim)

    def test_reservoir_and_parcels_stay_bounded_and_drain(self):
        sim = make(8, bounds=Rect(0, 0, 1920, 1080), amount=400)
        sim.set_surfaces([surf(f"w{i}", 100 + 150 * i, 300 + 90 * i, 800) for i in range(6)])
        for _ in range(30 * 30):
            sim.step(DT)
        sim.set_surfaces([])
        sim.set_surfaces([])
        sim.set_surfaces([])
        for _ in range(30 * 40):
            sim.step(DT)
        self.assertOK(sim)
        self.assertLessEqual(len(sim.parcels), 4000)
        self.assertTrue(all(is_ground(k) for k in sim.piles))   # 창 참조 없음


if __name__ == "__main__":
    unittest.main()
