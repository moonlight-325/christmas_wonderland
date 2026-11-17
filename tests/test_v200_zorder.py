"""v2.0.0 Z-order: 눈 오버레이(top) > 항상 위 장식 창. 작업표시줄은 순서가 아니라 '윗선 크기 맞춤 + 장식 가리기' 로 처리한다.

PySide6/Windows 없이 실행되는 순수 계산 + 정적 검사.
"""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snow import winapi as real_winapi  # noqa: E402

plan_topband = real_winapi.plan_topband


def src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def apply_plan(z: list, plan: list) -> list:
    """계획대로 오버레이를 맨 위(TOPMOST 층의 맨 앞)로 올린다."""
    z = list(z)
    for _role, h in plan:
        z.remove(h)
        z.insert(0, h)
    return z


class PlanTopband(unittest.TestCase):
    def test_correct_order_needs_no_move(self):
        self.assertEqual(plan_topband({1: 0, 2: 1}, {3: 2, 4: 3}), [])

    def test_overlay_below_decor_is_raised(self):
        self.assertEqual(plan_topband({1: 3}, {2: 0, 3: 1}), [("overlay", 1)])

    def test_no_decor_means_nothing_to_do(self):
        self.assertEqual(plan_topband({1: 5}, {}), [])

    def test_no_overlay_means_nothing_to_do(self):
        self.assertEqual(plan_topband({}, {1: 0}), [])

    def test_random_orders_converge_and_second_pass_is_empty(self):
        rnd = random.Random(7)
        for _ in range(200):
            ovs = list(range(1, rnd.randint(1, 3) + 1))
            dcs = list(range(10, 10 + rnd.randint(0, 4)))
            z = ovs + dcs
            rnd.shuffle(z)
            plan = plan_topband({h: z.index(h) for h in ovs}, {h: z.index(h) for h in dcs})
            z2 = apply_plan(z, plan)
            if dcs:
                self.assertLess(max(z2.index(h) for h in ovs), min(z2.index(h) for h in dcs))
            self.assertEqual(plan_topband({h: z2.index(h) for h in ovs}, {h: z2.index(h) for h in dcs}), [])

    def test_already_valid_orders_are_never_touched(self):
        for n_ov in (1, 2, 3):
            for n_dc in (0, 1, 4):
                z = list(range(1, n_ov + 1)) + list(range(10, 10 + n_dc))
                self.assertEqual(plan_topband({h: z.index(h) for h in range(1, n_ov + 1)},
                                              {h: z.index(h) for h in range(10, 10 + n_dc)}), [])


class StructureChecks(unittest.TestCase):
    def test_no_zorder_work_per_snow_frame(self):
        e = src("snow/engine.py")
        a = e.index("    def _decor_tick(self):")
        b = e.index("    def _lag_check(self")
        body = e[a:b]
        for token in ("keep_top", "settle", "SetWindowPos", "keep_bottom"):
            self.assertNotIn(token, body, "눈 프레임마다 Z-order 를 검사/변경하면 안 된다: " + token)
        a = e.index("    def _tick(self):")
        self.assertNotIn("settle", e[a:e.index("    def _decor_tick(self):")])

    def test_top_overlay_rect_fix_does_not_raise_window(self):
        w = src("snow/winapi.py")
        body = w[w.index("def set_window_rect("):]
        self.assertIn("SWP_NOZORDER", body.split("return keep_bottom")[0])
        self.assertNotIn("HWND_TOPMOST, rect[0]", body)

    def test_kept_features_exist(self):
        w = src("snow/winapi.py")
        for token in ("def keep_top", "def make_top_overlay", "def keep_bottom", "def plan_topband",
                      "def keep_decor_below_overlay", "def floors_for_rects", "def taskbar_height"):
            self.assertIn(token, w)

    def test_taskbar_order_machinery_is_gone(self):
        w = src("snow/winapi.py") + src("decor/layer.py") + src("snow/engine.py")
        for token in ("_topmost_taskbars", "topband_report", "recent_repeats", "zorder_report",
                      "keep_decor_below_taskbar", "_REPEAT_TIMES", "_after_settle"):
            self.assertNotIn(token, w)

    def test_taskbar_is_handled_by_size_and_clip(self):
        e = src("snow/engine.py")
        self.assertIn("def _fit_overlays", e)
        d = src("decor/layer.py")
        for token in ("def clip_to_taskbar", "clip_all_to_taskbar()", "def request_settle", "install_foreground_hook(_on_foreground)",
                      "NET_INTERVAL_MS = 1000", "keep_decor_below_overlay"):
            self.assertIn(token, d)

    def test_foreground_hook_supports_several_listeners(self):
        w = src("snow/winapi.py")
        self.assertIn("_FG_LISTENERS", w)

    def test_top_layer_decor_windows_use_mixin(self):
        for rel, cls in (("decor/items.py", "class DecorWindow(TopBandMixin, QWidget)"),
                         ("decor/lights.py", "class LightsWindow(TopBandMixin, QWidget)"),
                         ("clockface/window.py", "class ClockWindow(TopBandMixin, QWidget)")):
            self.assertIn(cls, src(rel))

    def test_snow_stays_below_normal_windows(self):
        w = src("snow/winapi.py")
        self.assertIn("def make_overlay_window", w)       # 기본 오버레이는 일반 창 뒤(바탕화면 위)
        o = src("snow/overlay.py")
        self.assertIn("setClipRegion(clip)", o)           # top 오버레이는 장식 창이 보이는 부분에만 그린다


if __name__ == "__main__":
    unittest.main()
