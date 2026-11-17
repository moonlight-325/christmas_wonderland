"""v1.9.5 Stage 3: 탭 키보드 이동, 트레이. (설정 창의 '기본값과 다른 항목' 표시는 v1.9.6 UI 정리에서 삭제됨)

PySide6 가 필요 없는 부분(탭 이동 계산, 소스 정적 검사)은 어디서나 실행된다.
`*Qt` 클래스는 PySide6 가 있을 때만 실행되고(없으면 건너뜀), 오프스크린 플랫폼에서 실제 위젯을 만들어 확인한다.
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

from core.nav import nav_target
from settings.store import DEFAULTS_LOOKUP as default_of

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

SRC = (ROOT / "widget" / "settings_window.py").read_text(encoding="utf-8")


def keys_in_settings_window():
    keys = set(re.findall(r'self\._(?:check|slider|choice|swatches)\(\s*\w+,\s*(?:tr\("[^"]*"\)|"[^"]*"),\s*"([a-z_0-9]+\.[a-z_0-9]+)"', SRC))
    keys |= {f"physics.{k}" for k in re.findall(r'\bsl\(\s*(?:tr\("[^"]*"\)|"[^"]*"),\s*"([a-z_0-9]+)"', SRC)}
    return keys


class NavTarget(unittest.TestCase):
    def test_moves_and_clamps(self):
        self.assertEqual(nav_target(0, 5, "next"), 1)
        self.assertEqual(nav_target(4, 5, "next"), 4)        # 끝에서 멈춤 (돌아가지 않음)
        self.assertEqual(nav_target(0, 5, "prev"), 0)
        self.assertEqual(nav_target(3, 5, "prev"), 2)
        self.assertEqual(nav_target(3, 5, "first"), 0)
        self.assertEqual(nav_target(1, 5, "last"), 4)

    def test_degenerate(self):
        self.assertIsNone(nav_target(0, 0, "next"))
        self.assertIsNone(nav_target(0, 3, "sideways"))
        self.assertEqual(nav_target(99, 3, "prev"), 1)       # 범위 밖 현재 값은 보정
        self.assertEqual(nav_target(-5, 3, "next"), 1)


class SettingsKeys(unittest.TestCase):
    def test_every_settings_window_key_has_a_default(self):
        keys = keys_in_settings_window()
        self.assertGreater(len(keys), 60)                     # 정규식이 실제로 키를 찾고 있는지
        missing = []
        for k in sorted(keys | {"wind.direction", "wind.strength", "music.volume", "music.repeat"}):
            try:
                default_of(k)
            except KeyError:
                missing.append(k)
        self.assertEqual(missing, [])


class SourceWiring(unittest.TestCase):
    """Qt 없이 확인할 수 있는 연결 검사 (오타·누락 방지). 화면 동작 자체는 아래 Qt 테스트와 Windows 실기에서 확인."""

    def test_row_helpers_pass_key(self):
        for name in ("_slider", "_choice", "_swatches"):
            m = re.search(rf"def {name}\(.*?\n(?=    def )", SRC, re.S)
            self.assertIsNotNone(m, name)
            self.assertRegex(m.group(0), r"self\._row\(lay, label, \w+, key\)", name)

    def test_default_diff_marks_are_gone(self):
        """기본값과 다른 항목 표시/툴팁/맨 아래 안내 줄이 설정 창과 공통 UI 에 남아 있지 않다."""
        ui = (ROOT / "widget" / "pixel_ui.py").read_text(encoding="utf-8")
        for word in ("PixelMark", "set_mark", "set_marked", "_refresh_marks", "_default_text", "lbl_foot", "기본값과 다른"):
            self.assertNotIn(word, SRC, word)
            self.assertNotIn(word, ui, word)
        self.assertFalse((ROOT / "settings" / "diff.py").exists())

    def test_tabs_are_keyboard_reachable(self):
        ui = (ROOT / "widget" / "pixel_ui.py").read_text(encoding="utf-8")
        m = re.search(r"class PixelTabs.*?(?=\nclass )", ui, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("setFocusPolicy(Qt.TabFocus)", body)
        self.assertIn("def keyPressEvent", body)
        self.assertIn("nav_target", body)
        self.assertNotIn("hasFocus()", body)                  # Stage 7: 선택 줄 안쪽 검은 포커스 테두리는 그리지 않음

    def test_tray_checks_availability(self):
        tray = (ROOT / "widget" / "tray.py").read_text(encoding="utf-8")
        self.assertIn("isSystemTrayAvailable", tray)


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class WidgetsQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def test_tabs_keyboard(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from widget.pixel_ui import PixelTabs
        t = PixelTabs([("gear", "a"), ("snow", "b"), ("wind", "c")])
        t.show()
        got = []
        t.currentChanged.connect(got.append)
        self.assertTrue(t.focusPolicy() & Qt.TabFocus)
        QTest.keyClick(t, Qt.Key_Down)
        self.assertEqual(t.current(), 1)
        QTest.keyClick(t, Qt.Key_Down)
        QTest.keyClick(t, Qt.Key_Down)                       # 끝에서 멈춤
        self.assertEqual(t.current(), 2)
        QTest.keyClick(t, Qt.Key_Home)
        self.assertEqual(t.current(), 0)
        QTest.keyClick(t, Qt.Key_Up)                         # 처음에서 멈춤
        self.assertEqual(t.current(), 0)
        QTest.keyClick(t, Qt.Key_End)
        self.assertEqual(t.current(), 2)
        QTest.keyClick(t, Qt.Key_A)                          # 관계없는 키는 무시
        self.assertEqual(t.current(), 2)
        self.assertEqual(got, [1, 2, 0, 2])
        t.grab()


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class StarTabColorQt(unittest.TestCase):
    """장식 탭의 노란 별: 선택하지 않았을 땐 노란색, 선택(눌렀을 때)하면 검은색."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def _star_center(self, t, selected_index):
        from widget.pixel_ui import PX
        t.setCurrent(selected_index)
        img = t.grab().toImage()
        i = 0                                                   # 별 탭은 맨 위(0번)
        x = 2 * PX + 5 * PX + 3 * PX + PX // 2
        y = 2 * PX + i * t.ROW_H + (t.ROW_H - 2 * PX - 7 * PX) // 2 + 3 * PX + PX // 2
        c = img.pixelColor(x, y)
        return c.red(), c.green(), c.blue()

    def test_star_is_yellow_when_idle_and_black_when_selected(self):
        from widget.pixel_ui import PixelTabs
        t = PixelTabs([("star", "장식"), ("gear", "성능")])
        t.resize(t.width(), 120)
        r, g, b = self._star_center(t, 1)                        # 장식 탭이 선택되지 않음
        self.assertGreater(r, 200)                              # 노란색 (#f3c94a 계열)
        self.assertGreater(g, 150)
        self.assertLess(b, 120)
        r, g, b = self._star_center(t, 0)                        # 장식 탭 선택
        self.assertLess(max(r, g, b), 40)                       # 검은색


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class SettingsWindowQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def setUp(self):
        from decor.items import DecorManager
        from settings.manager import SettingsManager
        from widget import settings_window as sw
        self.tmp = tempfile.TemporaryDirectory()
        self.s = SettingsManager(Path(self.tmp.name))
        self.dm = DecorManager(self.s)

        class FakeAudio:
            tracks = []

            def __getattr__(self, n):
                raise AttributeError(n)

        self._orig_music = sw.MusicPanel
        sw.MusicPanel = lambda audio, settings: __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget()
        self.sw = sw
        self.w = sw.SettingsWindow(self.s, FakeAudio(), sfx=None, decor=self.dm)

    def tearDown(self):
        self.sw.MusicPanel = self._orig_music
        self.w.close()
        self.dm.shutdown()
        self.tmp.cleanup()

    def test_every_tab_renders(self):
        for i in range(len(self.w.tabs.items)):
            self.w.tabs.setCurrent(i)
        self.w.show()
        self.w.grab()


if __name__ == "__main__":
    unittest.main()
