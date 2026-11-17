"""v1.9.1: 바닥 눈 디자인(v1.5.0 픽셀 블록) 복원 + 물 생성 제거 검증 (PySide6 불필요)."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snow import physics
from snow.physics import Pile, Rect, SLOPE, SnowSim, SurfaceInfo, melt_rate_for


def make(temp=-15.0, amount=0):
    sim = SnowSim(seed=1)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    sim.configure(amount=amount, accumulate=80, temperature=temp, wind_strength=0, cursor_on=False)
    sim.set_surfaces([SurfaceInfo("w", 400, 600, 1000, [(400, 1000)], [(400, 1000)])])
    return sim


class PileDesign(unittest.TestCase):
    def test_v150_constants(self):
        self.assertEqual(SLOPE, 1.5)
        self.assertEqual(SnowSim().cell, 3)

    def test_overlay_colors_and_no_water_drawing(self):
        src = (ROOT / "snow" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn("PILE_BODY = QColor(230, 240, 249)", src)       # #E6F0F9
        self.assertIn("PILE_TOP = QColor(255, 255, 255)", src)        # #FFFFFF
        self.assertIn("PILE_BASE = QColor(196, 218, 238)", src)       # #C4DAEE
        for banned in ("QPainterPath", "Antialiasing", "WATER_", "PILE_HARD", "_paint_water", "_paint_drops", "_paint_mound"):
            self.assertNotIn(banned, src, banned)

    def test_relax_uses_constant_slope(self):
        p = Pile(0, 600, 300, 3)
        p.closed = True
        p.cells[50] = 60.0
        p.relax_all()
        for _ in range(60):
            p.relax_all()
        diffs = [abs(p.cells[i] - p.cells[i + 1]) for i in range(len(p.cells) - 1)]
        self.assertLessEqual(max(diffs), SLOPE + 1e-6)
        self.assertAlmostEqual(sum(p.cells), 60.0, places=6)


class NoWater(unittest.TestCase):
    def test_no_water_attributes(self):
        sim = make()
        p = sim.piles["w"]
        for name in ("wat", "wflux", "drops", "pend", "wactive", "comp"):
            self.assertFalse(hasattr(p, name), name)
        for name in ("water_made", "total_water", "water_balance", "drops", "_make_meltwater", "water_drops"):
            self.assertFalse(hasattr(sim, name), name)
        self.assertFalse((ROOT / "snow" / "water.py").exists())

    def test_melting_only_lowers_snow_and_keeps_ledger(self):
        sim = make(temp=10.0)
        p = sim.piles["w"]
        for i in range(len(p.cells)):
            p.cells[i] = 6.0
            sim.mass_added += 6.0
        before = sim.total_mass()
        for _ in range(int(60 / (1 / 30))):
            sim.step(1 / 30)
        self.assertLess(sim.total_mass(), before)
        self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=1e-6)
        self.assertAlmostEqual(sim.mass_melted, before - sim.total_mass(), delta=1e-6)   # 줄어든 만큼 정확히 용해로 기록
        self.assertEqual(sum(1 for _ in sim.parcels), 0)                                  # 녹은 눈이 다른 입자로 바뀌지 않음

    def test_melt_rate_formula_unchanged(self):
        self.assertAlmostEqual(melt_rate_for(8.0), 25.0 / 100.0 * 0.06 + 8.0 / 30.0 * 0.10, places=9)
        self.assertAlmostEqual(melt_rate_for(-15.0), 0.0, places=9)
        sim = make(temp=5.0)
        self.assertAlmostEqual(sim.melt_rate(), melt_rate_for(5.0, sim.melt), places=9)

    def test_cold_does_not_melt(self):
        sim = make(temp=-15.0)
        p = sim.piles["w"]
        p.cells[10] = 5.0
        sim.mass_added += 5.0
        for _ in range(300):
            sim.step(1 / 30)
        self.assertEqual(sim.mass_melted, 0.0)


if __name__ == "__main__":
    unittest.main()
