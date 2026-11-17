"""v1.9.5 Stage 4: 눈사람 공방 / 스노우볼 창 피드백 (삭제 확인, 한도 안내, 결과 알림, 모드 표시).

PySide6 없이 실행되는 부분: 두 번 눌러 확인 상태(TwoStep), 소스 연결 정적 검사.
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

from core.confirm import TwoStep

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

PANEL = (ROOT / "snowman" / "panel.py").read_text(encoding="utf-8")
GLOBE = (ROOT / "widget" / "snowglobe_window.py").read_text(encoding="utf-8")


class TwoStepLogic(unittest.TestCase):
    def test_first_press_arms_second_confirms(self):
        t = TwoStep(3.0)
        self.assertFalse(t.press("a", 10.0))
        self.assertTrue(t.is_armed("a", 11.0))
        self.assertTrue(t.press("a", 11.0))
        self.assertFalse(t.is_armed("a", 11.1))            # 실행 뒤에는 다시 첫 클릭부터
        self.assertFalse(t.press("a", 11.2))

    def test_timeout_rearms_instead_of_confirming(self):
        t = TwoStep(3.0)
        t.press("a", 0.0)
        self.assertTrue(t.is_armed("a", 3.0))              # 경계 포함
        self.assertFalse(t.is_armed("a", 3.01))
        self.assertFalse(t.press("a", 5.0))                # 시간이 지난 두 번째 클릭은 새 첫 클릭
        self.assertTrue(t.press("a", 6.0))

    def test_target_change_never_confirms_other_target(self):
        t = TwoStep(3.0)
        t.press("A", 0.0)
        self.assertFalse(t.press("B", 1.0))                # A 를 대기시킨 뒤 B 를 눌러도 B 는 지워지지 않는다
        self.assertFalse(t.is_armed("A", 1.5))
        self.assertTrue(t.press("B", 2.0))

    def test_reset_and_none_key(self):
        t = TwoStep(3.0)
        t.press(None, 0.0)
        self.assertTrue(t.is_armed(None, 1.0))
        t.reset()
        self.assertFalse(t.is_armed(None, 1.0))
        self.assertFalse(t.press(None, 2.0))

    def test_clock_going_backwards_is_not_a_confirm(self):
        t = TwoStep(3.0)
        t.press("a", 10.0)
        self.assertFalse(t.is_armed("a", 5.0))


class SourceWiring(unittest.TestCase):
    """화면 없이 확인할 수 있는 연결 검사. 실제 동작은 아래 Qt 테스트와 Windows 실기에서 확인."""

    def test_snowman_delete_needs_confirmation(self):
        self.assertRegex(PANEL, r'ConfirmButton\(tr\("삭제"\),.*key_fn=self\._sel\)')
        self.assertIn("dele.confirmed.connect(self._delete)", PANEL)
        self.assertNotIn("dele.clicked.connect(self._delete)", PANEL)

    def test_snowman_actions_give_feedback(self):
        for name in ("_add_decor", "_remove_decor", "_delete"):
            m = re.search(rf"    def {name}\(.*?\n(?=    def |\Z)", PANEL, re.S)
            self.assertIsNotNone(m, name)
            self.assertIn("self.flash(", m.group(0), name)

    def test_snowman_limit_text_uses_real_limit(self):
        self.assertIn("M.LIMITS['decor']", PANEL)
        self.assertNotIn("너무 많아요", PANEL)               # 숫자 없는 모호한 문구 제거

    def test_globe_delete_needs_confirmation_and_disarms_on_selection(self):
        self.assertRegex(GLOBE, r"self\.btn_del = ConfirmButton\(")
        self.assertIn("self.btn_del.confirmed.connect(self._del_globe)", GLOBE)
        m = re.search(r"def _on_structure\(.*?\n(?=    def )", GLOBE, re.S)
        self.assertIn("self.btn_del.disarm()", m.group(0))

    def test_globe_actions_give_feedback(self):
        for name in ("_add_globe", "_dup_globe", "_del_globe", "_dup_item", "_del_item"):
            m = re.search(rf"    def {name}\(.*?\n(?=    def |\Z)", GLOBE, re.S)
            self.assertIsNotNone(m, name)
            self.assertIn("self._flash(", m.group(0), name)

    def test_globe_limits_come_from_constants(self):
        self.assertIn("MAX_GLOBES", GLOBE)
        self.assertIn("C.MAX_DECOR", GLOBE)
        self.assertNotRegex(GLOBE, r"최대 (12|40)개")        # 숫자를 문구에 직접 쓰지 않는다

    def test_canvas_reports_failed_placement(self):
        self.assertIn("place_failed = Signal(str)", GLOBE)
        self.assertIn('self.place_failed.emit("full")', GLOBE)
        self.assertIn("self.canvas.place_failed.connect", GLOBE)

    def test_mode_is_named_in_hint(self):
        self.assertIn("장식을 고르고 점선 안을 클릭해 놓아요", GLOBE)         # 꾸미기 모드 안내 (v1.9.7: 낡은 '[모드]' 접두어 검사를 현재 문구로 정렬)
        self.assertIn("클릭하면 흔들리고, 끌면 직접 흔들어요", GLOBE)           # 보기 모드 안내
        self.assertIn("'스노우볼 추가'로 만들어 보세요.", GLOBE)            # 빈 상태 안내

    def test_confirm_button_is_defined_once_and_safe(self):
        ui = (ROOT / "widget" / "pixel_ui.py").read_text(encoding="utf-8")
        m = re.search(r"class ConfirmButton.*?(?=\n# ={10,})", ui, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        for needle in ("TwoStep", "def disarm", "def hideEvent", "EnabledChange", "confirmed = Signal()"):
            self.assertIn(needle, body)


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class ConfirmButtonQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def test_two_clicks_confirm(self):
        from widget.pixel_ui import ConfirmButton
        b = ConfirmButton("삭제", "trash", key_fn=lambda: "x")
        got = []
        b.confirmed.connect(lambda: got.append(1))
        b.click()
        self.assertEqual(got, [])
        self.assertEqual(b.text(), "정말 삭제?")
        self.assertTrue(b.is_armed())
        b.click()
        self.assertEqual(got, [1])
        self.assertEqual(b.text(), "삭제")

    def test_target_change_does_not_confirm(self):
        from widget.pixel_ui import ConfirmButton
        cur = ["A"]
        b = ConfirmButton("삭제", key_fn=lambda: cur[0])
        got = []
        b.confirmed.connect(lambda: got.append(cur[0]))
        b.click()
        cur[0] = "B"
        b.click()
        self.assertEqual(got, [])
        b.click()
        self.assertEqual(got, ["B"])

    def test_disarm_on_disable_and_hide(self):
        from widget.pixel_ui import ConfirmButton
        b = ConfirmButton("삭제", key_fn=lambda: 1)
        b.click()
        b.setEnabled(False)
        self.assertEqual(b.text(), "삭제")
        b.setEnabled(True)
        b.click()
        b.show()
        b.hide()
        self.assertEqual(b.text(), "삭제")


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class WindowsQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def test_globe_window_feedback_flow(self):
        from snowglobe.manager import GlobeManager
        from snowglobe.store import MAX_GLOBES, SnowGlobeStore
        from widget.snowglobe_window import SnowGlobeWindow
        with tempfile.TemporaryDirectory() as d:
            mgr = GlobeManager(SnowGlobeStore(Path(d) / "globes.json"))
            win = SnowGlobeWindow(mgr)
            try:
                while mgr.count() < MAX_GLOBES:
                    win._add_globe()
                self.assertFalse(win.btn_add.isEnabled())
                self.assertIn(str(MAX_GLOBES), win.lbl_gcount.text())      # 툴팁 대신 "12 / 12" 로 알림
                win._add_globe()
                self.assertIn("최대", win.note.text())
                win._dup_globe()
                self.assertIn("최대", win.note.text())
                n = mgr.count()
                win.btn_del.click()                              # 첫 클릭: 대기, 지워지지 않음
                self.assertEqual(mgr.count(), n)
                self.assertEqual(win.btn_del.text(), "정말 삭제?")
                win.btn_del.click()                              # 두 번째 클릭: 삭제
                self.assertEqual(mgr.count(), n - 1)
                self.assertIn("삭제했어요", win.note.text())
                self.assertEqual(win.btn_del.text(), "삭제")
            finally:
                win.close()


if __name__ == "__main__":
    unittest.main()
