"""최소화/닫힌 창 위의 눈이 곧바로 떨어지는지 점검 (PySide6 불필요)."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snow.physics import Rect, SnowSim, SurfaceInfo


def make():
    sim = SnowSim(seed=3)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    sim.configure(amount=0, accumulate=80, temperature=-15.0, wind_strength=0, cursor_on=False)
    sim.set_surfaces([SurfaceInfo("w", 400, 600, 1000, [(400, 1000)], [(400, 1000)])])
    for i in range(20, 150):
        sim.piles["w"].cells[i] = 6.0
    return sim


class Release(unittest.TestCase):
    def test_two_consecutive_misses_release_snow(self):
        sim = make()
        total = sum(sim.piles["w"].cells)
        sim.set_surfaces([])
        self.assertIn("w", sim.piles)                  # 첫 번째: 아직 확인 중
        self.assertEqual(sim.piles["w"].miss, 1)
        sim.set_surfaces([])
        self.assertNotIn("w", sim.piles)               # 두 번째: 떨어뜨림
        self.assertGreater(len(sim.parcels) + len(sim._reservoir), 0)

    def test_engine_keeps_pushing_while_miss_pending(self):
        src = (ROOT / "snow" / "engine.py").read_text(encoding="utf-8")
        self.assertIn("def _miss_pending", src)
        self.assertIn("or self._miss_pending()", src)
        self.assertGreaterEqual(len(re.findall(r"_miss_pending\(\)", src)), 3)
        self.assertIn("MISS_CONFIRM_MS", src)


if __name__ == "__main__":
    unittest.main()
