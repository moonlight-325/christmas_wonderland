"""v1.9.6 UI Stage 7: 툴팁 간결화, 스노우볼 점선 제거, 클릭 흔들기 제거 + 자동 주기 흔들기, 포커스 테두리 제거, 줄바꿈 라벨 잘림.

PySide6 없이 실행되는 부분: 소스 정적 검사. `*Qt` 클래스는 PySide6 가 있을 때만 실행된다 (없으면 '건너뜀').
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

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class StaticChecks(unittest.TestCase):
    def test_globe_widget_has_no_selection_outline(self):
        s = src("snowglobe/widget.py")
        self.assertNotIn("DashLine", s)
        self.assertNotIn("#ffd84a", s)

    def test_side_tabs_draw_no_focus_border(self):
        ui = src("widget/pixel_ui.py")
        body = re.search(r"class PixelTabs.*?(?=\nclass )", ui, re.S).group(0)
        self.assertNotIn("hasFocus()", body)
        self.assertIn("keyPressEvent", body)          # 키보드 이동은 그대로

    def test_click_shake_restored_without_glass_wobble(self):
        m = re.search(r"def click\(self, gid.*?(?=\n    def )", src("snowglobe/manager.py"), re.S).group(0)
        self.assertIn("self.shake(", m)                              # 수동(클릭) 흔들기 복구
        ph = src("snowglobe/physics.py")
        self.assertNotIn("env * 1.6", ph)                            # 유리 구체가 흔들리는 변위 계산 없음
        self.assertEqual(len(re.findall(r"self\.jolt = \(0\.0, 0\.0\)", ph)), 3)

    def test_auto_shake_is_an_option(self):
        cat = src("snowglobe/catalog.py")
        self.assertIn("AUTO_SHAKE_DEFAULT_SEC", cat)
        self.assertIn("AUTO_SHAKE_RANGE", cat)
        self.assertIn('"auto_shake"', src("snowglobe/model.py"))
        self.assertIn("chk_auto", src("widget/snowglobe_window.py"))
        self.assertIn("직접 + 클릭", cat)                            # 흔들기 방식 이름은 원래대로

    def test_maker_window_size_never_changes(self):
        w = src("widget/snowglobe_window.py")
        self.assertIn("setSizeConstraint(QLayout.SetNoConstraint)", w)     # 내용이 창 크기를 바꾸지 못함
        self.assertIn("w.setFixedWidth(C.GW * S + 8 * PX)", w)                      # 가운데 칸 폭 고정
        self.assertIn("QSizePolicy.Ignored", w)                            # 오른쪽 칸은 내용 크기를 무시
        self.assertIn("self.setFixedSize(", w)

    def test_lag_diagnostics_present(self):
        e = src("snow/engine.py")
        self.assertIn("렉 진단", e)
        self.assertIn("last_paint_ms", src("snow/overlay.py"))

    def test_maker_uses_picture_tiles(self):
        w = src("widget/snowglobe_window.py")
        self.assertIn("PixelTile", w)
        self.assertNotIn("def _grid(", w)                           # 글자 버튼 격자는 그림 타일로 대체
        self.assertIn("_shelf_caption", w)                          # 스노우볼 선반 캡션
        ex = src("widget/pixel_extra.py")
        self.assertIn("class PixelTile(QAbstractButton)", ex)
        self.assertNotIn("setToolTip", ex)                          # 이름은 툴팁 대신 한 줄 캡션으로

    def test_maker_has_no_scroll_areas(self):
        w = src("widget/snowglobe_window.py")
        self.assertNotIn("QScrollArea", w)                          # 스크롤 영역 자체가 없다
        self.assertNotIn("ScrollBar", w)
        self.assertIn("_fit_height_once", w)                        # 내용 높이에 맞춰 창 높이를 열 때 한 번만 정함
        self.assertIn("26 * PX, 30 * PX", w)                        # 선반 12개가 3열 x 4줄로 들어오는 소형 타일

    def test_wrap_label_breaks_long_paths(self):
        ui = src("widget/pixel_ui.py")
        self.assertIn("u200b", ui)

    def test_removed_tooltips(self):
        self.assertNotIn("setToolTip(tip)", src("widget/settings_window.py"))
        self.assertNotIn("tips[name]", src("widget/auto_weather_page.py"))
        self.assertNotIn("setToolTip", src("widget/music_panel.py"))
        # 툴팁은 아이콘만 있는 버튼 위주로만 남는다
        self.assertNotIn("setToolTip(name +", src("widget/snowglobe_window.py"))

    def test_wrap_label_used_where_wrapping(self):
        for rel in ("widget/settings_window.py", "widget/snowglobe_window.py"):
            s = src(rel)
            self.assertIn("WrapLabel", s)
            self.assertNotRegex(s, r"(?<!Wrap)QLabel\(")
        self.assertIn("class WrapLabel", src("widget/pixel_ui.py"))


class PlowedSnowFlies(unittest.TestCase):
    """커서로 쓸어 튕겨 난 눈송이가 바로 같은 눈더미에 되박혀 사라지지 않고 멀리 날아가는지 (PySide6 불필요)."""

    def _run(self, reconfigure_every=0):
        from snow.physics import Rect, SnowSim, SurfaceInfo
        sim = SnowSim(seed=3)
        sim.cell = 3
        sim.set_bounds(Rect(0, 0, 1920, 1080))
        sim.configure(amount=0, accumulate=60, temperature=-15.0, wind_strength=0, cursor_on=True,
                      cursor_strength=60, cursor_radius=90)
        sim.set_surfaces([SurfaceInfo("w", 400, 600, 1200, [(400, 1200)], [(400, 1200)])])
        sim.set_monitors([(0, 0, 1920, 1080)])
        for i in range(len(sim.piles["w"].cells)):
            sim.piles["w"].cells[i] = min(8.0, sim.max_cells)
        sim._base = sim.mass_balance()                 # 직접 채운 눈은 장부 밖이라 기준값으로 뺀다
        dt, born, life, seen = 1 / 60, {}, [], set()
        for fr in range(240):
            if reconfigure_every and fr % reconfigure_every == 0:
                sim.configure(amount=300, temperature=-15.0)      # 자동 날씨가 약 10Hz 로 설정을 다시 적용하는 상황
            sim.set_cursor((420 + fr * dt / 1.5 * 760, 576), dt)
            sim.step(dt)
            alive = {id(f) for f in sim.flakes if f.temp}
            for k in list(born):
                if k not in alive:
                    life.append(fr - born.pop(k))
            for k in alive - seen:
                born[k] = fr
            seen |= alive
        return sim, life

    def test_plowed_flakes_do_not_vanish_next_frame(self):
        sim, life = self._run()
        self.assertGreater(len(life), 100)
        life.sort()
        self.assertGreater(life[len(life) // 2], 30)               # 중앙값 0.5초 이상 날아감 (수정 전: 1프레임)
        self.assertLess(sum(1 for v in life if v <= 2) / len(life), 0.1)

    def test_settings_reapply_does_not_cull_flying_snow(self):
        """자동 날씨가 설정을 다시 적용(configure)할 때마다 튕겨 난 눈송이가 잘려 나가면 안 된다."""
        sim, life = self._run(reconfigure_every=6)
        life.sort()
        self.assertGreater(len(life), 100)
        self.assertGreater(life[len(life) // 2], 30)

    def test_fit_count_keeps_temp_flakes(self):
        from snow.physics import Rect, SnowSim
        sim = SnowSim(seed=1)
        sim.set_bounds(Rect(0, 0, 1920, 1080))
        sim.configure(enabled=True, amount=100)
        for _ in range(50):
            sim._spawn_temp(500, 500, 100, -100)
        before = sum(1 for f in sim.flakes if f.temp)
        sim.configure(amount=10)                                   # 목표 수를 크게 줄여도
        self.assertEqual(sum(1 for f in sim.flakes if f.temp), before)

    def test_failed_spawn_returns_snow_to_pile(self):
        sim, _ = self._run()
        self.assertAlmostEqual(sim.mass_balance() - sim._base, 0.0, places=3)

    def test_mass_ledger_still_balances(self):
        sim, _ = self._run()
        self.assertAlmostEqual(sim.mass_balance() - sim._base, 0.0, places=3)


@unittest.skipUnless(HAVE_QT, "PySide6 필요")
class AutoShakeQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _mgr(self, d):
        from snowglobe.manager import GlobeManager
        from snowglobe.store import SnowGlobeStore
        m = GlobeManager(SnowGlobeStore(Path(d) / "globes.json"))
        gid = m.add_globe()
        return m, gid

    def test_click_shakes_snow_but_glass_does_not_move(self):
        with tempfile.TemporaryDirectory() as d:
            m, gid = self._mgr(d)
            m.click(gid)
            self.assertTrue(m.physics(gid).shaking)
            for _ in range(60):
                m.physics(gid).step(1 / 30, 0.0, 0.0)
                self.assertEqual(m.physics(gid).jolt, (0.0, 0.0))
            m.shutdown()

    def test_auto_shake_option(self):
        from snowglobe import catalog as C
        with tempfile.TemporaryDirectory() as d:
            m, gid = self._mgr(d)
            g = m.globes[gid]
            g["auto_shake_sec"] = 20
            fired = sum(m._auto_shake_due(gid, 0.05) for _ in range(int(60 / 0.05)))
            self.assertGreaterEqual(fired, 2)                 # 60초 동안 20초 간격이면 2~3번
            g["auto_shake"] = False
            self.assertFalse(any(m._auto_shake_due(gid, 1.0) for _ in range(200)))
            m.shutdown()


if __name__ == "__main__":
    unittest.main()
