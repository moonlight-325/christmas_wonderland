"""v1.9.6: 쌓인 눈 물리 v1.4.0 복원 검증 (PySide6 불필요).

v1.4.0 원본과의 직접 비교는 tools/verify_snow_versions.py (두 원본 폴더 필요). 여기서는 원본 없이 확인 가능한 규칙만 본다.
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import (CAP_SCALE, EDGE_CAP, Pile, Rect, SLOPE, SnowSim, SurfaceInfo, V140_CAP_BASE, V140_CAP_SPAN,
                          melt_rate_for)

DT = 1 / 30


def make(temp=-15.0, amount=0, accumulate=50, **cfg):
    sim = SnowSim(seed=11)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    base = dict(amount=amount, accumulate=accumulate, temperature=temp, wind_strength=0, cursor_on=False)
    base.update(cfg)
    sim.configure(**base)
    sim.set_surfaces([SurfaceInfo("w", 400, 600, 1200, [(400, 1200)], [(400, 1200)])])
    return sim


class MaxHeight(unittest.TestCase):
    def test_cap_is_exactly_double_the_v140_limit(self):
        for acc in (0, 10, 50, 77, 100):
            sim = SnowSim()
            sim.configure(accumulate=acc)
            v140 = 2.0 + acc / 100.0 * 14.0                    # v1.4.0 의 기존 제한식
            self.assertAlmostEqual(sim.max_cells, 2.0 * v140, places=9)
        self.assertEqual((V140_CAP_BASE, V140_CAP_SPAN, CAP_SCALE), (2.0, 14.0, 2.0))

    def test_every_pile_gets_the_cap(self):
        sim = make(accumulate=60)
        sim.set_monitors([(0, 0, 1920, 1080)])
        self.assertTrue(sim.piles)
        for p in sim.piles.values():
            self.assertAlmostEqual(p.maxh, sim.max_cells, places=9)

    def test_cap_follows_setting_changes(self):
        sim = make(accumulate=20)
        sim.configure(accumulate=90)
        self.assertAlmostEqual(sim.piles["w"].maxh, sim.max_cells, places=9)

    def test_long_snowfall_reaches_cap_but_not_beyond(self):
        sim = make(temp=-15, amount=900, accumulate=30, accumulate_rate=100, max_particles=900)
        sim.set_surfaces([SurfaceInfo("w", 700, 600, 760, [(700, 760)], [(700, 760)])])      # 좁은 창: 중앙이 빨리 찬다
        for _ in range(30 * 200):
            sim.step(DT)
        peak = max(sim.piles["w"].cells)
        self.assertLessEqual(peak, sim.max_cells + 1e-9)
        self.assertGreater(peak, 2.0 * (2.0 + 0.3 * 14.0) * 0.5)         # 기존(v1.4.0) 제한 근처를 넘어 2배 영역까지 쌓인다

    def test_removing_the_cap_is_not_possible_through_land(self):
        sim = make()
        p = sim.piles["w"]
        for _ in range(500):
            f = sim._new_flake(False)
            f.amount, f.cols = 3.6, 1
            sim._land(p, 100, f)
        self.assertLessEqual(max(p.cells), sim.max_cells + 1e-9)


class RelaxRules(unittest.TestCase):
    def test_slope_limit(self):
        p = Pile(0, 0, 900, 3)
        p.closed = True
        p.maxh = 100.0
        p.cells[100] = 60.0
        for _ in range(80):
            p.relax_all()
        diffs = [abs(p.cells[i] - p.cells[i + 1]) for i in range(len(p.cells) - 1)]
        self.assertLessEqual(max(diffs), SLOPE + 1e-6)
        self.assertAlmostEqual(sum(p.cells), 60.0, places=6)

    def test_top_excess_is_reported_as_side_zero(self):
        p = Pile(0, 0, 300, 3)
        p.closed = True
        p.cells[50] = 10.0
        spill = p.relax(50, 4.0)
        self.assertIn((0, 6.0), [(s, round(a, 9)) for s, a in spill])
        self.assertEqual(p.cells[50] <= 4.0 + 1e-9, True)

    def test_open_edge_spills_over_edge_cap(self):
        p = Pile(0, 0, 30, 3)
        p.cells[0] = 6.0
        spill = p.relax(0, 99.0)
        self.assertTrue(any(s == -1 for s, _ in spill))
        self.assertLessEqual(p.cells[0], EDGE_CAP + 1e-9)

    def test_closed_edge_is_a_wall(self):
        p = Pile(0, 0, 30, 3)
        p.closed = True
        p.cells[0] = 6.0
        spill = p.relax(0, 99.0)
        self.assertFalse(any(s != 0 for s, _ in spill))


class Melt(unittest.TestCase):
    @staticmethod
    def reference(cells, base, dt):
        out = []
        for v in cells:
            if v > 0.0:
                v -= base * dt * (0.4 + min(v, 6.0) * 0.2)
                v = v if v > 0.02 else 0.0
            out.append(v)
        return out

    def test_matches_v140_formula_at_several_temperatures(self):
        for temp in (-8.0, 0.0, 5.0, 12.0, 25.0):
            sim = make(temp=temp)
            cells = [0.0, 0.01, 0.5, 2.0, 6.0, 9.0, 17.5] * 20
            sim.piles["w"].cells = list(cells[:len(sim.piles["w"].cells)]) + [0.0] * max(0, len(sim.piles["w"].cells) - len(cells))
            sim.piles["w"].cells = sim.piles["w"].cells[:len(sim.piles["w"].cells)]
            before = list(sim.piles["w"].cells)
            exp = before
            for _ in range(6):
                exp = self.reference(exp, melt_rate_for(temp, sim.melt), 0.25)
                sim._melt(0.25)
            self.assertEqual(sim.piles["w"].cells, exp, temp)

    def test_cold_below_minus_10_does_not_melt(self):
        sim = make(temp=-12.0)
        sim.piles["w"].cells[5] = 4.0
        sim.mass_added += 4.0
        for _ in range(300):
            sim.step(DT)
        self.assertEqual(sim.mass_melted, 0.0)
        self.assertEqual(sim.piles["w"].cells[5], 4.0)

    def test_ledger_equals_lost_snow_and_no_water_or_ripeness(self):
        sim = make(temp=10.0)
        p = sim.piles["w"]
        for i in range(len(p.cells)):
            p.cells[i] = 5.0
            sim.mass_added += 5.0
        before = sim.total_mass()
        for _ in range(30 * 40):
            sim.step(DT)
        self.assertAlmostEqual(sim.mass_melted, before - sim.total_mass(), delta=1e-6)
        self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=1e-6)
        self.assertFalse(hasattr(p, "ripe"))                 # v1.9.x 의 숙성도/노출/밀도 용해는 v1.4.0 에 없으므로 사용하지 않는다

    def test_warmer_melts_faster(self):
        amounts = []
        for temp in (0.0, 8.0, 20.0):
            sim = make(temp=temp)
            sim.piles["w"].cells = [4.0] * len(sim.piles["w"].cells)
            sim._melt(0.25)
            amounts.append(sim.mass_melted)
        self.assertLess(amounts[0], amounts[1])
        self.assertLess(amounts[1], amounts[2])


class CursorPlow(unittest.TestCase):
    def run_swipe(self, sim, y=594.0, x0=450.0, vx=420.0, seconds=2.0):
        for k in range(int(seconds / DT)):
            sim.set_cursor((x0 + vx * k * DT, y), DT)
            sim.step(DT)

    def test_swipe_moves_snow_forward_and_scatters_some(self):
        sim = make(cursor_on=True, cursor_strength=1.0, cursor_radius=120.0)
        p = sim.piles["w"]
        for i in range(int(len(p.cells) * 0.3), int(len(p.cells) * 0.5)):
            p.cells[i] = 5.0
            sim.mass_added += 5.0
        c0 = sum(i * h for i, h in enumerate(p.cells)) / sum(p.cells)
        self.run_swipe(sim)
        c1 = sum(i * h for i, h in enumerate(sim.piles["w"].cells)) / sum(sim.piles["w"].cells)
        self.assertGreater(c1, c0 + 2)                                 # 커서 진행 방향으로 눈이 밀린다
        self.assertGreater(sim.mass_lost, 0.0)                         # v1.4.0: 일부는 흩날려 사라진다 (장부 기록)
        self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=1e-6)

    def test_still_cursor_does_nothing_to_pile(self):
        sim = make(cursor_on=True, cursor_strength=1.0)
        p = sim.piles["w"]
        p.cells[100] = 4.0
        snap = list(p.cells)
        for _ in range(60):
            sim.set_cursor((700.0, 594.0), DT)
            sim.step(DT)
        self.assertEqual(sim.piles["w"].cells, snap)

    def test_cursor_off_does_nothing(self):
        sim = make(cursor_on=False, cursor_strength=1.0)
        p = sim.piles["w"]
        for i in range(60, 120):
            p.cells[i] = 4.0
        snap = list(p.cells)
        self.run_swipe(sim, x0=500.0)
        self.assertEqual(sim.piles["w"].cells, snap)

    def test_plowed_pile_never_exceeds_cap(self):
        sim = make(cursor_on=True, cursor_strength=1.0, accumulate=10)
        p = sim.piles["w"]
        for i in range(len(p.cells)):
            p.cells[i] = min(sim.max_cells, 1.5 * min(i, 10, len(p.cells) - i))
        for _ in range(4):
            self.run_swipe(sim, x0=420.0, vx=500.0, seconds=1.6)
        self.assertLessEqual(max(sim.piles["w"].cells), sim.max_cells + 1e-9)


class WindBlow(unittest.TestCase):
    def test_strong_wind_blows_snow_and_ledger_closes(self):
        sim = make(wind_strength=100)
        p = sim.piles["w"]
        for i in range(len(p.cells)):
            p.cells[i] = 4.0
            sim.mass_added += 4.0
        before = sim.total_mass()
        for _ in range(30 * 10):
            sim.step(DT)
        self.assertLess(sim.total_mass(), before)
        self.assertGreater(sim.mass_lost, 0.0)
        self.assertAlmostEqual(sim.mass_balance(), 0.0, delta=1e-6)

    def test_calm_wind_keeps_pile(self):
        sim = make(wind_strength=20)
        sim.piles["w"].cells = [3.0] * len(sim.piles["w"].cells)
        for _ in range(30 * 10):
            sim.step(DT)
        self.assertEqual(sim.mass_lost, 0.0)


class NoFlowLeftovers(unittest.TestCase):
    def test_v150_flow_system_is_gone(self):
        sim = make()
        p = sim.piles["w"]
        for name in ("flow", "flow_active", "ripe", "sync_aux"):
            self.assertFalse(hasattr(p, name), name)
        for name in ("_step_flow", "_add_loft", "_loft_acc"):
            self.assertFalse(hasattr(sim, name), name)

    def test_no_height_limit_leftovers(self):
        src = (Path(__file__).resolve().parent.parent / "snow" / "matter.py").read_text(encoding="utf-8")
        self.assertNotIn("relax(i, INF", src)
        self.assertNotIn("relax(j, INF", src)


if __name__ == "__main__":
    unittest.main()
