"""눈사람 Qt 연결 테스트 (PySide6 필요, 오프스크린): 엔진 틱 연결, 저장/복원, 패널 조작, 오버레이 그리기, 장식 눈사람 불용해.
실행: python -m unittest tests/test_snowman_qt.py -v"""
import json
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

DT = 1 / 30


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class SnowmanQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def setUp(self):
        from settings.manager import SettingsManager
        from snow.engine import SnowEngine
        from snowman.manager import SnowmanManager
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.s = SettingsManager(self.dir)
        self.eng = SnowEngine(self.s)
        self.mgr = SnowmanManager(self.s, self.eng)
        self.eng.start()
        self.mgr.start()
        self.w = self.mgr.world

    def tearDown(self):
        self.mgr._timer.stop()
        self.eng.shutdown()
        self.tmp.cleanup()

    def _run(self, sec):
        for _ in range(int(sec / DT)):
            self.eng.sim.step(DT)
            self.eng._step_world(DT)

    def test_engine_wiring(self):
        self.assertIs(self.eng.sim.bodies, self.w)
        self.assertIs(self.eng.world, self.w)
        sid = self.w.add_decorative("classic", x=800, y=600)
        self.eng._step_world(DT)                       # 월드가 바뀌면 머리 표면이 눈 표면 목록에 등록된다
        self.assertIn(("deco", sid), self.eng.sim.piles)
        bid = self.w.spawn_ball(radius=16, x=600, y=300)
        self._run(2.0)
        self.assertTrue(self.w.balls[bid].y > 300)     # 엔진 틱으로 월드가 진행된다 (낙하)

    def test_disabled_hides_and_freezes(self):
        bid = self.w.spawn_ball(radius=16, x=600, y=300)
        self.s.set("snowman.enabled", False)
        y0 = self.w.balls[bid].y
        self._run(1.0)
        self.assertEqual(self.w.balls[bid].y, y0)
        self.assertFalse(self.w.visible)
        self.s.set("snowman.enabled", True)
        self.assertTrue(self.w.visible)

    def test_settings_apply(self):
        self.s.set("snowman.growth", 200)
        self.s.set("snowman.push_gain", 50)
        self.s.set("snowman.mouse_push", False)
        self.s.set("snowman.grab", False)
        self.assertEqual((self.w.growth, self.w.push_gain, self.w.mouse_push, self.w.grab_on), (2.0, 0.5, False, False))

    def test_save_restore_across_restart(self):
        from settings.manager import SettingsManager
        from snow.engine import SnowEngine
        from snowman import model as M
        from snowman.manager import SnowmanManager
        a = self.w.spawn_ball(radius=22, x=700, y=300)
        b = self.w.spawn_ball(radius=14, x=700, y=250)
        did = self.w.add_decorative("santa", x=1300, y=700)
        self.w.set_deco(did, scale=1.4, rot=8)
        self.w.add_decor(did, "hat", "beanie", "green")
        self.mgr.flush()
        self.s.save_now()
        s2 = SettingsManager(self.dir)
        eng2 = SnowEngine(s2)
        m2 = SnowmanManager(s2, eng2)
        eng2.start()
        m2.start()
        w2 = m2.world
        self.assertIn(a, w2.balls)
        self.assertIn(b, w2.balls)
        d2 = w2.snowmen[did]
        self.assertEqual((d2.type, d2.style, round(d2.scale, 1), d2.rot), (M.DECORATIVE, "santa", 1.4, 8.0))
        self.assertTrue(any(d["kind"] == "hat" and d["color"] == "green" for d in d2.decor))
        eng2.shutdown()

    def test_corrupt_state_sanitized(self):
        from settings.store import sanitize
        data = sanitize({"snowman": {"state": {"items": [{"id": 1}, "x"], "balls": "bad", "props": [5]},
                                     "growth": 99999}})
        self.assertEqual(data["snowman"]["state"], {"items": [], "balls": [], "props": []})
        self.assertEqual(data["snowman"]["growth"], 300)

    def test_decorative_never_melts_dynamic_does(self):
        from snowman import model as M
        self.s.set("weather.temperature", 30)
        did = self.w.add_decorative("classic", x=900, y=700)
        sn_scale = self.w.snowmen[did].scale
        a = self.w.spawn_ball(radius=24, x=500, y=300)
        m0 = self.w.balls[a].m
        self._run(40.0)
        self.assertIn(did, self.w.snowmen)
        self.assertEqual(self.w.snowmen[did].scale, sn_scale)
        self.assertEqual(self.w.snowmen[did].type, M.DECORATIVE)
        self.assertLess(self.w.balls[a].m, m0)                      # dynamic 계열(눈덩이)은 녹는다

    def test_old_decor_menu_snowman_does_not_melt(self):
        from decor.items import DecorManager
        self.assertFalse(hasattr(DecorManager, "_melt_tick"))
        self.s.set("weather.temperature", 30)
        dm = DecorManager(self.s)
        iid = dm.add("snowman")
        dm.sync()
        w = dm.windows[iid]
        self.assertEqual(w.melt if hasattr(w, "melt") else 0.0, 0.0)
        dm.shutdown()

    def test_overlay_paints_bodies(self):
        self.w.add_decorative("classic", x=800, y=600)
        self.w.spawn_ball(radius=20, x=500, y=500)
        ov = self.eng.overlays[0]
        ov.resize(900, 700)
        img = QImage(ov.size(), QImage.Format_ARGB32)
        img.fill(0)
        ov.render(img)
        self.assertFalse(img.isNull())

    def test_panel_flow(self):
        from snowman.panel import SnowmanPanel
        p = SnowmanPanel(self.mgr)
        p.show()
        p._spawn()
        self.assertEqual(len(self.w.balls), 1)
        p._add_deco("cool")
        sid = self.w.selected
        self.assertEqual(self.w.kind_of(sid), "decorative")
        for i in range(3):
            p.set_page(i)
            p._refresh()
        p.set_page(1)
        p._add_decor("gloves")
        p._refresh()
        self.assertTrue(any(d["kind"] == "gloves" for _o, d in self.w.decor_list(sid)))
        did = p._sel_decor
        p._cycle_style(sid, next(d for _o, d in self.w.decor_list(sid) if d["id"] == did))
        p._set_color(sid, did, "pink")
        p._refresh()
        p._remove_decor(sid, did)
        p.set_page(2)
        p._duplicate()
        self.assertEqual(sum(1 for s in self.w.snowmen.values() if s.type == "decorative"), 2)
        p._delete()
        p._refresh()
        self.assertEqual(sum(1 for s in self.w.snowmen.values() if s.type == "decorative"), 1)
        p.close()


if __name__ == "__main__":
    unittest.main()
