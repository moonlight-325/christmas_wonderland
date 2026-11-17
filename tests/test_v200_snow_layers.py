"""작업표시줄 아래 눈 제거 + 장식 위 눈 오버레이 (PySide6/Windows 없이 실행되는 순수 로직·정적 검사)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snow.surfaces import WinEntry, compute_surfaces, subtract_rects, visible_decor_rects  # noqa: E402


def src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class NoSnowUnderTaskbar(unittest.TestCase):
    MON = [(0, 0, 1920, 1080)]
    FLOORS = [1040.0]

    def test_window_below_floor_gets_no_pile(self):
        entries = [WinEntry(1, 100, 1050, 600, 1200)]            # 윗면이 작업표시줄 안
        self.assertEqual(compute_surfaces(entries, self.MON, self.FLOORS), [])

    def test_window_above_floor_still_gets_pile(self):
        entries = [WinEntry(1, 100, 300, 600, 700)]
        self.assertEqual(len(compute_surfaces(entries, self.MON, self.FLOORS)), 1)

    def test_bottom_taskbar_surface_skipped_because_floor_covers_it(self):
        entries = [WinEntry(("tb", 1), 0, 1040, 1920, 1080, taskbar=True)]
        self.assertEqual(compute_surfaces(entries, self.MON, self.FLOORS), [])

    def test_taskbar_surface_kept_when_not_at_floor(self):
        entries = [WinEntry(("tb", 1), 0, 500, 1920, 560, taskbar=True)]
        self.assertEqual(len(compute_surfaces(entries, self.MON, self.FLOORS)), 1)

    def test_taskbar_surface_kept_without_floors(self):
        entries = [WinEntry(("tb", 1), 0, 1040, 1920, 1080, taskbar=True)]
        self.assertEqual(len(compute_surfaces(entries, self.MON)), 1)

    def test_without_floors_behaviour_unchanged(self):
        entries = [WinEntry(1, 100, 1050, 600, 1200)]
        self.assertEqual(len(compute_surfaces(entries, self.MON)), 1)

    def test_overlay_erases_below_floor_and_taskbar(self):
        o = src("snow/overlay.py")
        self.assertIn("def _erase_cuts", o)
        self.assertIn("self._erase_cuts(p, pl, pt, pr, pb)", o)
        self.assertIn("self.sim.floor_at", o)
        self.assertIn("self._cut_rects", src("snow/engine.py"))


class DecorRects(unittest.TestCase):
    def test_subtract(self):
        self.assertEqual(subtract_rects([(0, 0, 10, 10)], (20, 20, 30, 30)), [(0, 0, 10, 10)])
        self.assertEqual(subtract_rects([(0, 0, 10, 10)], (-5, -5, 20, 20)), [])
        parts = subtract_rects([(0, 0, 10, 10)], (4, 4, 6, 6))
        self.assertEqual(sum((r - l) * (b - t) for l, t, r, b in parts), 100 - 4)

    def test_visible_decor_rects_cut_by_app_windows(self):
        vis = visible_decor_rects((100, 100, 200, 200), [(150, 0, 400, 400)])
        self.assertEqual(vis, [(100, 100, 150, 200)])
        self.assertEqual(visible_decor_rects((100, 100, 200, 200), [(0, 0, 400, 400)]), [])
        self.assertEqual(visible_decor_rects((100, 100, 200, 200), []), [(100, 100, 200, 200)])


class SnowAboveDecor(unittest.TestCase):
    def test_decor_windows_are_registered_and_top_overlay_exists(self):
        self.assertIn("_DECOR.add(w)", src("decor/layer.py"))
        e = src("snow/engine.py")
        for token in ("top_overlays", "_decor_tick", "visible_decor_rects"):
            self.assertIn(token, e)
        self.assertNotIn("keep_top", e)          # 프레임마다 Z-order 를 검사하던 호출은 이벤트 기반(decor.layer.request_settle)으로 대체됨
        self.assertIn("def request_settle", src("decor/layer.py"))
        self.assertIn("top=True", e)
        a = src("snow/winapi.py")
        for token in ("def make_top_overlay", "def keep_top", "def occluders_above", "HWND_TOPMOST"):
            self.assertIn(token, a)

    def test_version_unchanged(self):
        self.assertIn('__version__ = "2.0.0"', src("core/version.py"))


if __name__ == "__main__":
    unittest.main()


class DesktopClickAndMerge(unittest.TestCase):
    def test_keep_bottom_reraises_when_desktop_window_comes_up(self):
        a = src("snow/winapi.py")
        self.assertIn("def _desktop_above", a)
        self.assertIn("def _above_desktop_target", a)
        self.assertIn("and not _desktop_above(hwnd)", a)

    def test_same_spot_parcels_merge_and_conserve_mass(self):
        from snow.physics import Rect, SnowSim
        sim = SnowSim(seed=1)
        sim.cell = 3
        sim.set_bounds(Rect(0, 0, 800, 600))
        before = len(sim.parcels)
        for _ in range(200):
            sim._emit_parcel(100.0, 50.0, 40.0, 20.0, 0.05, merge=True)
        total = sum(f.carry for f in sim.parcels)
        self.assertAlmostEqual(total, 10.0, places=6)
        self.assertLess(len(sim.parcels) - before, 10)           # 200개가 몇 개로 합쳐진다
        for f in sim.parcels:
            self.assertLessEqual(f.carry, 8.0 + 1e-9)


class FloorFromTaskbarRect(unittest.TestCase):
    def test_floor_is_matched_by_rect_not_device_name(self):
        e = src("snow/engine.py")
        self.assertIn("winapi.floors_for_rects(list(rects))", e)
        a = src("snow/winapi.py")
        self.assertIn("def floors_for_rects", a)
        self.assertIn("mb - h", a)
