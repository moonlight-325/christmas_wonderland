"""눈 물리/표면 계산 테스트 (PySide6 불필요). 실행: python -m unittest tests.test_snow -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import Rect, SnowSim, SurfaceInfo  # noqa: E402
from snow.surfaces import WinEntry, compute_surfaces  # noqa: E402

MON = [(0, 0, 1920, 1080)]


class SurfaceTests(unittest.TestCase):
    def test_window_top_becomes_surface(self):
        s = compute_surfaces([WinEntry(1, 400, 300, 1200, 800)], MON)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0].segments, [(400, 1200)])

    def test_maximized_window_skipped(self):
        self.assertEqual(compute_surfaces([WinEntry(1, 0, 0, 1920, 1040)], MON), [])

    def test_occlusion_splits_segments(self):
        top = WinEntry(2, 600, 200, 800, 700, surface=False)      # 위에 있는 창이 일부를 가림
        under = WinEntry(1, 400, 300, 1200, 800)
        s = compute_surfaces([top, under], MON)
        self.assertEqual(s[0].segments, [(400, 600), (800, 1200)])


    def test_surface_records_occluders_and_draw_segments(self):
        top = WinEntry(2, 600, 200, 800, 700, surface=False)
        under = WinEntry(1, 400, 300, 1200, 800)
        s = compute_surfaces([top, under], MON)[0]
        self.assertEqual(s.draw_segments, [(400, 1200)])      # 그리기는 전체, 가림은 occluders 로 처리
        self.assertEqual(s.occluders, [(600, 200, 800, 700)])


class PhysicsTests(unittest.TestCase):
    def make(self):
        sim = SnowSim(seed=3)
        sim.set_bounds(Rect(0, 0, 1920, 1080))
        sim.configure(amount=300, accumulate=50, melt=0, wind_strength=0)
        sim.set_surfaces([SurfaceInfo("w", 400, 500, 1200, [(400, 1200)])])
        return sim

    def test_snow_accumulates(self):
        sim = self.make()
        for _ in range(30 * 60):
            sim.step(1 / 30)
        self.assertGreater(sim.piles["w"].total(), 20)
        self.assertLessEqual(max(sim.piles["w"].cells), sim.max_cells + 1e-6)

    def test_pile_follows_window_move_and_resize(self):
        sim = self.make()
        for _ in range(30 * 40):
            sim.step(1 / 30)
        before = sim.piles["w"].total()
        sim.set_surfaces([SurfaceInfo("w", 700, 450, 1700, [(700, 1700)])])
        self.assertEqual(sim.piles["w"].left, 700)
        self.assertGreater(sim.piles["w"].total(), before * 0.5)

    def test_closed_window_drops_pile(self):
        sim = self.make()
        for _ in range(30 * 40):
            sim.step(1 / 30)
        total = sim.total_mass()
        sim.set_surfaces([])
        self.assertIn("w", sim.piles)              # 일시적 누락 보호: 한 번 빠진 것만으로는 사라진 것으로 보지 않음
        sim.set_surfaces([])
        self.assertNotIn("w", sim.piles)
        self.assertAlmostEqual(sim.total_mass(), total, places=6)     # 눈은 사라지지 않고 덩어리가 된다
        self.assertGreater(len(sim.parcels), 0)

    def test_wind_direction_and_strong_wind_blows_snow(self):
        sim = self.make()
        sim.configure(wind_dir=90, wind_strength=50)
        self.assertGreater(sim.wind_vector()[0], 0)
        sim.configure(wind_dir=270)
        self.assertLess(sim.wind_vector()[0], 0)
        sim.configure(wind_dir=90, wind_strength=0)
        for _ in range(30 * 60):
            sim.step(1 / 30)
        before = sim.piles["w"].total()
        sim.configure(wind_strength=100)
        for _ in range(30 * 15):
            sim.step(1 / 30)
        self.assertLess(sim.piles["w"].total(), before)

    def test_clear_and_reset(self):
        sim = self.make()
        for _ in range(30 * 30):
            sim.step(1 / 30)
        sim.clear_piles()
        self.assertEqual(sim.piles["w"].total(), 0)

    def test_particle_cap(self):
        sim = self.make()
        sim.configure(amount=1000, max_particles=100)
        self.assertLessEqual(len(sim.flakes), 100)


if __name__ == "__main__":
    unittest.main()
