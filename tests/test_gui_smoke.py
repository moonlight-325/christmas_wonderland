"""GUI 스모크 테스트 (PySide6 필요). 실행: python -m unittest tests.test_gui_smoke -v
오프스크린 플랫폼에서 위젯 생성, 모드 전환, 그리기, 설정 유지, 오디오 재생목록을 점검한다."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class GuiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from audio.manager import AudioManager
        from core.fonts import load_fonts
        load_fonts()
        from widget.main_widget import MainWidget
        from settings.manager import SettingsManager
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = SettingsManager(Path(self.tmp.name))
        self.audio = AudioManager(self.settings)
        self.widget = MainWidget(self.settings, self.audio)

    def tearDown(self):
        self.widget.close()
        self.tmp.cleanup()

    def test_default_tracks_found(self):
        self.assertGreaterEqual(len(self.audio.tracks), 3)

    def test_mode_switch_and_paint(self):
        for mode in ("bottom", "normal", "bottom"):
            self.settings.set("widget.mode", mode)
            self.widget.apply_mode(mode)
            self.assertTrue(self.widget.isVisible())
        img = QImage(self.widget.size(), QImage.Format_ARGB32)
        img.fill(0)
        self.widget.render(img)
        self.assertFalse(img.isNull())

    def test_settings_persist_across_restart(self):
        from settings.manager import SettingsManager
        self.settings.set("snow.amount", 222)
        self.settings.set("widget.mode", "bottom")
        self.settings.save_now()
        again = SettingsManager(Path(self.tmp.name))
        self.assertEqual(again.get("snow.amount"), 222)
        self.assertEqual(again.get("widget.mode"), "bottom")

    def test_repeat_cycle(self):
        seen = [self.audio.cycle_repeat() for _ in range(3)]
        self.assertEqual(sorted(seen), ["all", "off", "one"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class AdventSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_flow(self):
        from datetime import date
        from core.fonts import load_fonts
        load_fonts()
        from advent.window import AdventWindow
        with tempfile.TemporaryDirectory() as d:
            w = AdventWindow(Path(d), today_fn=lambda: date(2026, 12, 5))
            w.show()
            self.assertEqual(sum(v == "available" for v in w.canvas.statuses.values()), 5)
            w._enter_reveal(2026, 3, first=True)
            self.assertEqual(w.store.opened_days(2026), {3})
            w.canvas.grab()
            w.close()
