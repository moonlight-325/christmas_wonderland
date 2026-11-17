"""눈 물리 테스트 (PySide6 불필요): 장부 일치, 눈더미 이동, 창 관성/최소화/닫힘(독립 눈 덩어리), 바닥, 대량 안정성.

v1.9.6: 쌓인 눈 물리는 v1.4.0 이다. v1.4.0 의 마우스/바람/돌풍 흩날림은 눈을 덜어 눈송이로 보내므로 그 양을 장부(mass_lost)에 기록하고,
mass_balance() = 총량 - (새로 내린 양 - 융해량 - mass_lost) 가 0 이어야 한다 (장부에 없는 눈이 늘거나 줄지 않음).
창 이동/닫힘/가장자리 넘침으로 생긴 눈 덩어리는 여전히 질량이 정확히 보존된다 (WindowDynamics).
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import Rect, SnowSim, SurfaceInfo
from snow.matter import is_ground

DT = 1 / 30


def make(width=1000, cursor=False, seed=1):
    sim = SnowSim(seed=seed)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    sim.configure(amount=0, accumulate=50, temperature=-15, wind_strength=0, cursor_on=cursor,
                  cursor_strength=1.0, cursor_radius=120.0)
    sim.set_surfaces([SurfaceInfo("w", 400, 600, 400 + width, [(400, 400 + width)], [(400, 400 + width)])])
    return sim


def fill(sim, key="w", height=8.0, a=0.2, b=0.8):
    """눈을 직접 쌓아 두고 장부에 반영 (테스트용 초기 상태)."""
    p = sim.piles[key]
    n = len(p.cells)
    for i in range(int(n * a), int(n * b)):
        p.cells[i] = height
        sim.mass_added += height
    return p


def run(sim, seconds, cursor_path=None):
    steps = int(seconds / DT)
    for k in range(steps):
        if cursor_path is not None:
            sim.set_cursor(cursor_path(k * DT), DT)
        sim.step(DT)


class MassConservation(unittest.TestCase):
    def assertConserved(self, sim, msg=""):
        self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=max(1e-6, sim.total_mass() * 1e-9), msg=msg)

    def test_thin_pile_pushed_by_cursor(self):
        sim = make(cursor=True)
        fill(sim, height=1.0)
        before = sim.total_mass()
        run(sim, 3, lambda t: (500 + t * 300, 600 - 3))
        self.assertConserved(sim)

    def test_thick_pile_pushed_by_cursor(self):
        sim = make(cursor=True)
        fill(sim, height=40.0)
        before = sim.total_mass()
        run(sim, 4, lambda t: (450 + t * 400, 600 - 60))
        self.assertConserved(sim)

    def test_pile_above_cap_is_trimmed_to_cap_and_excess_is_world_snow(self):
        """최대 높이(v1.4.0 기존 제한의 2배)를 넘는 열은 눈이 닿을 때 그 높이로 정리되고, 넘친 눈은 덩어리로 떨어지거나 장부에 기록된다."""
        sim = make()
        p = sim.piles["w"]
        p.cells[100] = 60.0
        sim.mass_added += 60.0
        f = sim._new_flake(anywhere=False)
        sim._land(p, 100, f)
        self.assertLessEqual(p.cells[100], sim.max_cells + 1e-6)
        self.assertGreater(len(sim.parcels), 0)                   # 넘친 눈은 독립 눈 덩어리가 되어 떨어진다
        self.assertConserved(sim)

    def test_fast_swipe_and_repeat(self):
        sim = make(cursor=True)
        fill(sim, height=12.0)
        before = sim.total_mass()
        for rep in range(6):
            run(sim, 1.0, lambda t, r=rep: (420 + (t * 1500) % 900, 600 - 20))
        self.assertConserved(sim)

    def test_circular_motion_swirl(self):
        sim = make(cursor=True)
        fill(sim, height=15.0)
        before = sim.total_mass()
        run(sim, 6, lambda t: (700 + 90 * math.cos(t * 7), 580 + 60 * math.sin(t * 7)))
        self.assertConserved(sim)
        self.assertGreater(sim._cvx ** 2 + sim._cvy ** 2, 0.0)

    def test_pushed_snow_actually_moves_and_leaves_hollow(self):
        sim = make(cursor=True)
        p = fill(sim, height=6.0, a=0.3, b=0.5)
        cells0 = list(p.cells)
        centroid0 = sum(i * h for i, h in enumerate(cells0)) / sum(cells0)
        run(sim, 3, lambda t: (560 + t * 500, 600 - 8))              # 오른쪽으로 훑는다
        run(sim, 2)                                                  # 관성으로 계속 이동 후 정지
        cells1 = sim.piles["w"].cells
        centroid1 = sum(i * h for i, h in enumerate(cells1)) / sum(cells1)
        self.assertGreater(centroid1, centroid0 + 3)                 # 눈의 분포가 실제로 오른쪽으로 이동
        self.assertLess(min(cells1[int(len(cells1) * 0.3): int(len(cells1) * 0.32)]), cells0[int(len(cells0) * 0.3)])
        self.assertConserved(sim)

    def test_repeated_plowing_changes_shape_progressively(self):
        sim = make(cursor=True)
        fill(sim, height=10.0, a=0.4, b=0.6)
        shapes = []
        for rep in range(4):
            run(sim, 1.2, lambda t: (480 + t * 600, 600 - 10))
            shapes.append(tuple(round(c, 1) for c in sim.piles["w"].cells[::10]))
        self.assertEqual(len(set(shapes)), 4)
        self.assertConserved(sim)

    def test_heavier_pile_needs_more_force(self):
        light, heavy = make(cursor=True), make(cursor=True)
        fill(light, height=1.5, a=0.4, b=0.5)
        fill(heavy, height=60.0, a=0.4, b=0.5)
        for sim in (light, heavy):
            run(sim, 1.0, lambda t: (520 + t * 400, 600 - 4))
        def moved(sim, h0):
            p = sim.piles["w"]
            return sum(abs(c - h0) for c in p.cells) / h0 / max(1, sum(1 for c in p.cells if c > 0))
        self.assertGreater(moved(light, 1.5), moved(heavy, 60.0))

    def test_melt_is_ledgered(self):
        sim = make()
        sim.configure(temperature=12)
        fill(sim, height=3.0)
        run(sim, 20)
        self.assertGreater(sim.mass_melted, 0.0)
        self.assertConserved(sim)

    def test_wind_and_gust_blow_close_the_ledger(self):
        sim = make()
        sim.configure(wind_strength=95, gust_on=True, gust_strength=1.0)
        fill(sim, height=5.0)
        sim.trigger_gust(1.0, 90)
        before = sim.total_mass()
        run(sim, 8)
        self.assertConserved(sim)


class WindowDynamics(unittest.TestCase):
    def snap(self, sim, left, top=600, width=1000, key="w"):
        sim.set_surfaces([SurfaceInfo(key, left, top, left + width, [(left, left + width)], [(left, left + width)])])

    def test_slow_move_lags_and_keeps_mass(self):
        sim = make()
        fill(sim, height=6.0)
        before = sim.total_mass()
        for k in range(1, 21):                       # 80ms 마다 5px: 약 60px/s
            run(sim, 0.08)
            self.snap(sim, 400 + 5 * k)
        run(sim, 3)
        self.assertAlmostEqual(sim.total_mass(), before, places=6)
        self.assertEqual(sim.piles["w"].left, 500)

    def test_fast_move_drops_snow_into_parcels(self):
        sim = make()
        fill(sim, height=6.0)
        before = sim.total_mass()
        pile_before = sim.piles["w"].total()
        for k in range(1, 8):                        # 80ms 마다 160px = 2000px/s
            run(sim, 0.08)
            self.snap(sim, 400 + 160 * k)
        self.assertLess(sim.piles["w"].total(), pile_before * 0.7)      # 창에서 떨어져 나감
        self.assertGreater(len(sim.parcels), 0)
        self.assertAlmostEqual(sim.total_mass(), before, places=6)

    def test_snow_is_not_bound_to_window(self):
        """창이 빠르게 사라진 뒤에도 눈의 월드 위치/속도가 보존되고 바닥에 쌓인다."""
        sim = make()
        fill(sim, height=6.0)
        before = sim.total_mass()
        sim.set_surfaces([])
        sim.set_surfaces([])
        self.assertNotIn("w", sim.piles)
        run(sim, 12)
        ground = sum(sum(p.cells) for k, p in sim.piles.items() if is_ground(k))
        self.assertAlmostEqual(sim.total_mass(), before, places=6)
        self.assertGreater(ground, before * 0.9)
        self.assertEqual(len(sim.parcels), 0)
        self.assertEqual(len(sim._reservoir), 0)

    def test_minimize_then_restore_does_not_duplicate_snow(self):
        sim = make()
        fill(sim, height=6.0)
        before = sim.total_mass()
        sim.set_surfaces([])
        sim.set_surfaces([])                         # 최소화
        run(sim, 0.5)
        self.snap(sim, 400)                          # 복원
        self.assertAlmostEqual(sim.piles["w"].total(), 0.0, places=9)    # 새 빈 창: 눈이 복제되지 않음
        run(sim, 10)
        self.assertAlmostEqual(sim.total_mass(), before, places=6)

    def test_single_missing_snapshot_is_tolerated(self):
        sim = make()
        fill(sim, height=6.0)
        before = sim.piles["w"].total()
        sim.set_surfaces([])
        self.snap(sim, 400)
        self.assertAlmostEqual(sim.piles["w"].total(), before, places=9)
        self.assertEqual(len(sim.parcels), 0)

    def test_fallen_snow_lands_on_other_window(self):
        sim = make()
        sim.set_surfaces([
            SurfaceInfo("w", 400, 300, 1400, [(400, 1400)], [(400, 1400)]),
            SurfaceInfo("low", 300, 800, 1500, [(300, 1500)], [(300, 1500)]),
        ])
        fill(sim, height=6.0)
        before = sim.total_mass()
        sim.set_surfaces([SurfaceInfo("low", 300, 800, 1500, [(300, 1500)], [(300, 1500)])])
        sim.set_surfaces([SurfaceInfo("low", 300, 800, 1500, [(300, 1500)], [(300, 1500)])])
        run(sim, 8)
        self.assertGreater(sim.piles["low"].total(), before * 0.5)
        self.assertAlmostEqual(sim.total_mass(), before, places=6)

    def test_resize_keeps_snow_in_world_and_conserves(self):
        sim = make()
        fill(sim, height=5.0)
        before = sim.total_mass()
        self.snap(sim, 400, width=500)               # 오른쪽 가장자리를 줄임
        run(sim, 8)
        self.assertAlmostEqual(sim.total_mass(), before, places=6)

    def test_no_references_remain_after_close(self):
        sim = make()
        fill(sim, height=4.0)
        sim.set_surfaces([])
        sim.set_surfaces([])
        self.assertNotIn("w", sim.surfaces)
        self.assertTrue(all(not isinstance(k, str) for k in sim.piles))


class Stability(unittest.TestCase):
    def test_massive_accumulation_long_run(self):
        sim = SnowSim(seed=3)
        sim.set_bounds(Rect(0, 0, 1920, 1080))
        sim.configure(amount=900, accumulate=100, accumulate_rate=100, temperature=-20, wind_strength=30,
                      cursor_on=True, cursor_strength=1.0, max_particles=800)
        sim.set_surfaces([SurfaceInfo(f"w{i}", 100 + i * 300, 300 + 120 * i, 100 + i * 300 + 700,
                                      [(100 + i * 300, 100 + i * 300 + 700)], [(100 + i * 300, 100 + i * 300 + 700)])
                          for i in range(4)])
        for k in range(30 * 120):
            sim.set_cursor((300 + 600 * math.sin(k * 0.01), 500 + 200 * math.cos(k * 0.013)), DT)
            sim.step(DT)
            if k % 600 == 599:
                self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=max(1e-6, sim.total_mass() * 1e-9))
        self.assertGreater(sim.total_mass(), 50)
        self.assertLessEqual(len(sim.parcels), 4000)

    def test_cursor_off_and_zero_strength_do_nothing(self):
        sim = make(cursor=True)
        sim.configure(cursor_strength=0.0)
        p = fill(sim, height=5.0)
        snap = list(p.cells)
        run(sim, 2, lambda t: (600 + t * 400, 600 - 5))
        self.assertEqual(sim.piles["w"].cells, snap)

    def test_clear_piles_is_explicit_removal(self):
        sim = make()
        fill(sim, height=5.0)
        sim.set_surfaces([])
        sim.set_surfaces([])
        sim.clear_piles()
        self.assertEqual(sim.total_mass(), 0.0)
        self.assertEqual(len(sim.parcels), 0)


if __name__ == "__main__":
    unittest.main()
