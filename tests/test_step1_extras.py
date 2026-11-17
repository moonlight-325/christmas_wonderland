"""Step 1 추가 기능(전구/장식/시계/사운드/날씨/설정 화면) 테스트. 오프스크린 Qt. 오디오 재생기는 만들지 않는다."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402
    HAVE_QT = True
except ImportError:                                  # PySide6 가 없으면 실패가 아니라 '건너뜀'으로 기록한다
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않아 건너뜀")
class Extras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def setUp(self):
        from settings.manager import SettingsManager
        self.tmp = tempfile.TemporaryDirectory()
        self.s = SettingsManager(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_settings_roundtrip(self):
        from settings.manager import SettingsManager
        self.s.set("weather.temperature", 99)
        self.assertEqual(self.s.get("weather.temperature"), 30)
        self.s.set("clock.theme", "nope")
        self.assertEqual(self.s.get("clock.theme"), "led")
        self.s.set("clock.theme", "analog_wreath")
        self.s.save_now()
        s2 = SettingsManager(Path(self.tmp.name))
        self.assertEqual(s2.get("clock.theme"), "analog_wreath")

    def test_decor_persist(self):
        from decor.items import DecorManager
        import decor.sprites  # noqa: F401
        m = DecorManager(self.s)
        iid = m.add("snowman")
        self.assertIn(iid, m.windows)
        m.update_item(iid, x=321, y=222, scale=6)
        self.assertEqual((m.windows[iid].x(), m.windows[iid].y(), m.windows[iid].scale), (321, 222, 6))
        m.set_visible(iid, False)
        self.assertNotIn(iid, m.windows)
        m.set_visible(iid, True)
        self.s.save_now()
        from settings.manager import SettingsManager
        s2 = SettingsManager(Path(self.tmp.name))
        it = s2.get("decor.items")[0]
        self.assertEqual((it["x"], it["y"], it["scale"], it["kind"]), (321, 222, 6, "snowman"))
        m.remove(iid)
        self.assertEqual(self.s.get("decor.items"), [])
        m.shutdown()

    def test_clock_all_themes(self):
        from clockface import render
        from clockface.window import read_cfg
        for th in render.THEMES:
            for bg in render.BGS:
                self.s.set("clock.theme", th)
                self.s.set("clock.bg", bg)
                img = render.render_image(read_cfg(self.s))
                self.assertGreater(img.width(), 20)
        self.s.set("clock.show_time", False)
        for k in ("show_date", "show_weekday", "show_dday"):
            self.s.set(f"clock.{k}", False)
        self.assertGreater(render.size(read_cfg(self.s)).width(), 0)

    def test_lights(self):
        from decor.lights import LightsWindow, LEVELS, bulb_levels
        self.s.set("lights.enabled", True)
        for pos in ("top", "bottom", "left", "right", "custom"):
            self.s.set("lights.position", pos)
            w = LightsWindow(self.s)
            self.assertTrue(w.isVisible())
            self.assertGreater(w._n, 0)
            w.grab()
            w.shutdown()
        lv = bulb_levels("chase", 12, 1.0, 1.0, [0] * 12)
        self.assertTrue(all(0 <= v < LEVELS for v in lv))
        self.assertGreater(len(set(lv)), 1)

    def test_settings_window(self):
        from audio.sfx import SfxManager
        from decor.items import DecorManager
        from widget.settings_window import SettingsWindow
        dm = DecorManager(self.s)
        dm.add("star")
        w = SettingsWindow(self.s, audio=None, sfx=None, decor=dm) if False else None
        # AudioManager 가 QtMultimedia 를 만들므로 가짜 audio 로 대체
        class FakeAudio:
            tracks = []
            def __getattr__(self, n):
                raise AttributeError(n)
        try:
            from widget import settings_window as sw
            sw.MusicPanel = lambda audio, settings: __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget()
            w = SettingsWindow(self.s, FakeAudio(), sfx=None, decor=dm)
        finally:
            pass
        for i in range(w.tabs.items.__len__()):
            w.tabs.setCurrentIndex = None if False else w.tabs.setCurrent
            w.tabs.setCurrent(i)
            w.stack.setCurrentIndex(i)
            w.show()
            w.grab()
        dm.shutdown()


class Physics(unittest.TestCase):
    def _sim(self):
        from snow.physics import SnowSim, SurfaceInfo
        s = SnowSim(seed=3)
        s.configure(amount=300, accumulate=80, max_particles=1500)
        s.set_surfaces([SurfaceInfo("w", 100, 500, 900, [(100, 900)], [(100, 900)], [])])
        for _ in range(500):
            s.step(1 / 30)
        return s

    def test_temperature(self):
        s = self._sim()
        s.configure(enabled=True, amount=0)
        s.flakes.clear()
        s.configure(temperature=-15)
        a = sum(s.piles["w"].cells)
        for _ in range(300):
            s.step(1 / 30)
        self.assertAlmostEqual(a, sum(s.piles["w"].cells), places=3)      # 영하에서는 유지
        s.configure(temperature=10)
        for _ in range(300):
            s.step(1 / 30)
        b10 = sum(s.piles["w"].cells)
        self.assertLess(b10, a)
        s2 = self._sim(); s2.configure(amount=0); s2.flakes.clear(); s2.configure(temperature=28)
        for _ in range(300):
            s2.step(1 / 30)
        self.assertLess(sum(s2.piles["w"].cells), a - (a - b10))             # 더 높은 온도 = 더 빨리 녹음

    def test_gust_pushes_snow(self):
        s = self._sim()
        s.configure(amount=0)
        s.flakes.clear()
        s.configure(gust_on=False)
        s.piles["w"].cells = [4.0] * len(s.piles["w"].cells)
        s.trigger_gust(1.0, 90)
        left = sum(s.piles["w"].cells[:20])
        for _ in range(90):
            s.step(1 / 30)
        self.assertLess(sum(s.piles["w"].cells), 4.0 * len(s.piles["w"].cells))
        self.assertGreater(s.piles["w"].cells[0], -1)

    def test_blizzard_more_flakes_and_wind(self):
        s = self._sim()
        n0 = s.target_count()
        s.configure(blizzard=1.0)
        self.assertGreater(s.target_count(), n0)
        xs = sum(f.x for f in s.flakes) / len(s.flakes)
        for _ in range(60):
            s.step(1 / 30)
        self.assertGreater(sum(f.vx for f in s.flakes) / len(s.flakes), 100)

    def test_cursor_scatters(self):
        s = self._sim()
        s.configure(cursor_on=True, cursor_strength=1.0, cursor_radius=150)
        near = [f for f in s.flakes if abs(f.x - 500) < 100 and abs(f.y - 400) < 100]
        self.assertTrue(near)
        for i in range(10):
            s.set_cursor((300 + i * 40, 400), 1 / 30)
            s.step(1 / 30)
        fast = max(abs(f.vx) for f in near)
        self.assertGreater(fast, 200)

    def test_cursor_off_no_effect(self):
        s = self._sim()
        s.configure(cursor_on=False)
        for i in range(10):
            s.set_cursor((300 + i * 40, 400), 1 / 30)
            s.step(1 / 30)
        self.assertLess(max(abs(f.vx) for f in s.flakes), 700)


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않아 건너뜀 (audio.sfx 가 Qt 를 import 함)")
class Sfx(unittest.TestCase):
    def test_generation(self):
        from audio import sfx
        with tempfile.TemporaryDirectory() as d:
            for k in ("snow", "wind", "fire"):
                p = Path(d) / f"{k}.wav"
                sfx.write_wav(p, sfx._norm(sfx.GENERATORS[k](), 0.8))
                self.assertGreater(p.stat().st_size, 100000)


if __name__ == "__main__":
    unittest.main()
