"""v1.9.5 Stage 5: 트레이 날씨 상태, 장식/시계 이동 중 위치 표시 + 화면 밖 보정 + 잠금 안내.

PySide6 없이 실행되는 부분: 표시 문구/요약 함수, 화면 밖 보정 시나리오, 소스 연결 정적 검사.
`*Qt` 클래스는 PySide6 가 있을 때만 실행된다 (없으면 건너뜀).
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.geometry import clamp_into_screens, position_text, scale_text
from weather import spec

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class Texts(unittest.TestCase):
    def test_position_and_scale_text(self):
        self.assertEqual(position_text(120, -30), "위치 120, -30")        # 다중 모니터의 음수 좌표
        self.assertEqual(scale_text(5, 80, 64), "크기 5배 (80×64px)")

    def test_status_summary_states(self):
        k = spec.KIND_IDS[0]
        name = spec.KIND_NAME[k]
        self.assertEqual(spec.status_summary({"active": False, "phase": "idle"}), "")
        self.assertEqual(spec.status_summary({}), "")
        self.assertEqual(spec.status_summary({"active": True, "paused": True, "kind": k}), "자동 날씨: 일시정지")
        self.assertEqual(spec.status_summary({"active": False, "phase": "release"}), "자동 날씨: 수동 설정으로 돌아가는 중")
        self.assertEqual(spec.status_summary({"active": True, "paused": False, "kind": k, "remaining": 130}),
                         f"자동 날씨: {name} (약 3분 남음)")

    def test_status_summary_minutes_round_up_and_are_stable(self):
        k = spec.KIND_IDS[0]
        f = lambda r: spec.status_summary({"active": True, "paused": False, "kind": k, "remaining": r})
        self.assertIn("1분 미만", f(59.9))
        self.assertIn("1분 미만", f(0))
        self.assertIn("약 1분", f(60.0))
        self.assertIn("약 2분", f(60.1))
        self.assertEqual(f(61), f(120))                      # 같은 분 안에서는 문구가 같아 툴팁을 다시 설정하지 않는다
        self.assertIn("1분 미만", f(-5))                      # 음수 남은 시간 방어
        self.assertIn("직접 설정", spec.status_summary({"active": True, "paused": False, "kind": "nope", "remaining": 90}))


class OffScreenClamp(unittest.TestCase):
    """장식/시계를 화면 밖으로 끌어다 놓았을 때 쓰는 보정 (core.geometry.clamp_into_screens) 시나리오."""
    ONE = [(0, 0, 1920, 1080)]
    TWO = [(-1920, 0, 0, 1080), (0, 0, 1920, 1080)]

    def test_inside_is_untouched(self):
        self.assertEqual(clamp_into_screens(300, 200, 64, 64, self.ONE), (300, 200))

    def test_far_off_screen_comes_back(self):
        x, y = clamp_into_screens(5000, 4000, 64, 64, self.ONE)
        self.assertEqual((x, y), (1920 - 64, 1080 - 64))
        x, y = clamp_into_screens(-900, -900, 64, 64, self.ONE)
        self.assertEqual((x, y), (0, 0))

    def test_partially_visible_stays(self):
        self.assertEqual(clamp_into_screens(1920 - 60, 500, 64, 64, self.ONE), (1920 - 60, 500))

    def test_multi_monitor_negative_coords(self):
        self.assertEqual(clamp_into_screens(-1000, 300, 64, 64, self.TWO), (-1000, 300))       # 왼쪽 모니터 위: 그대로
        x, y = clamp_into_screens(-5000, 300, 64, 64, self.TWO)
        self.assertEqual((x, y), (-1920, 300))                                                  # 가장 가까운 왼쪽 모니터 안으로


class SourceWiring(unittest.TestCase):
    def test_decor_drag_end_is_clamped_and_saved_once(self):
        t = src("decor/items.py")
        self.assertIn("w.moved.connect(self._on_moved)", t)
        self.assertNotIn("w.moved.connect(lambda", t)
        m = re.search(r"def _on_moved\(.*?\n(?=    def )", t, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("clamp_pos(", body)
        self.assertLess(body.index("clamp_pos("), body.index("self.update_item("))    # 보정한 위치를 저장

    def test_decor_shows_value_while_dragging_and_hides_after(self):
        t = src("decor/items.py")
        self.assertIn("position_text(self.x(), self.y())", t)
        self.assertIn("scale_text(self.scale", t)
        m = re.search(r"def mouseReleaseEvent\(.*?\n(?=    def )", t, re.S)
        self.assertIn("QToolTip.hideText()", m.group(0))

    def test_lock_state_synced_without_tooltip(self):
        t = src("decor/items.py")
        self.assertIn("def set_locked", t)
        self.assertNotIn("(잠김)", t)
        self.assertIn("w.set_locked(locked)", t)               # sync 에서 잠금 변경이 툴팁에도 반영
        self.assertNotIn("w.locked = locked", t)
        c = src("clockface/window.py")
        self.assertNotIn("(잠김)", c)
        self.assertIn("Qt.SizeAllCursor", c)

    def test_clock_drag_end_is_clamped_before_saving(self):
        c = src("clockface/window.py")
        m = re.search(r"def mouseReleaseEvent\(.*?\n(?=    def )", c, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("clamp_pos(", body)
        self.assertLess(body.index("clamp_pos("), body.index('self.s.set("clock.x"'))
        self.assertIn("position_text(", c)

    def test_tray_shows_weather_state(self):
        t = src("widget/tray.py")
        self.assertIn("spec.status_summary(", t)
        self.assertIn("auto_weather.state_changed.connect(self.update_tip)", t)
        m = re.search(r"def update_tip\(.*?\n(?=    def )", t, re.S)
        self.assertIn("if tip != self._tip", m.group(0))        # 값이 바뀔 때만 트레이 API 호출
        self.assertIn("self._tip =", t.split("def update_tip")[0])   # 첫 refresh 전에 초기화


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class DecorQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def test_moved_off_screen_is_pulled_back_and_saved(self):
        from decor.items import DecorManager
        from settings.manager import SettingsManager
        from core.geometry import available_screens
        with tempfile.TemporaryDirectory() as d:
            s = SettingsManager(Path(d))
            m = DecorManager(s)
            try:
                iid = m.add(next(iter(__import__("decor.sprites", fromlist=["KIND_SPRITE"]).KIND_SPRITE)))
                self.assertTrue(iid)
                w = m.windows[iid]
                m._on_moved(iid, 10 ** 6, 10 ** 6)
                item = next(i for i in m.items() if i["id"] == iid)
                self.assertEqual((item["x"], item["y"]), (w.x(), w.y()))
                right = max(r for (_l, _t, r, _b) in available_screens())
                self.assertLess(item["x"], right)                # 화면 밖에 저장되지 않음
            finally:
                m.shutdown()

    def test_lock_has_no_tooltip(self):
        from decor.items import DecorWindow
        from decor.sprites import KIND_SPRITE
        kind = next(iter(KIND_SPRITE))
        w = DecorWindow({"id": "t", "kind": kind, "scale": 2, "x": 10, "y": 10, "visible": True}, True, "normal")
        self.assertEqual(w.toolTip(), "")                     # v1.9.7: 잠김 툴팁 제거 (커서 모양으로 구분)
        w.set_locked(False)
        self.assertEqual(w.toolTip(), "")
        w.close()


if __name__ == "__main__":
    unittest.main()
