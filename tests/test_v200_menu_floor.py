"""v2.0.0 오류 수정: 스노우볼 창 글자 잘림 방지 구조, 작업표시줄(자동 숨김 포함) 바닥 기준선. PySide6 없이 실행되는 정적 검사."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class SnowGlobeMenuLayout(unittest.TestCase):
    def test_tabs_are_named_by_what_they_change(self):
        w = src("widget/snowglobe_window.py")
        self.assertIn('("basic", tr("모양")), ("decor", tr("장식")), ("snow", tr("눈")), ("shake", tr("흔들기"))', w)

    def test_desktop_settings_live_in_one_place(self):
        w = src("widget/snowglobe_window.py")
        center = re.search(r"def _build_center\(.*?\n(?=    def )", w, re.S).group(0)
        for name in ("self.chk_vis", "self.chk_lock", "self.sl_size", 'PixelSection(tr("바탕화면"))'):
            self.assertIn(name, center)
        basic = re.search(r"def _page_basic\(.*?\n(?=    # ----)", w, re.S).group(0)
        self.assertNotIn("sl_size", basic)

    def test_no_row_is_wider_than_its_column(self):
        w = src("widget/snowglobe_window.py")
        self.assertIn("setFixedWidth(104 * PX)", w)                  # "스노우볼 추가" 버튼이 잘리지 않는 선반 폭
        self.assertIn("self.lbl_gname.setWordWrap(True)", w)
        self.assertIn('"both": tr("클릭·끌기")', w)                       # 긴 흔들기 방식 이름은 한 줄에 못 들어와 잘렸다
        self.assertIn("520 * PX", w)

    def test_decor_controls_only_when_selected(self):
        w = src("widget/snowglobe_window.py")
        self.assertIn("self._decor_ctl.setVisible(has)", w)


class TaskbarFloor(unittest.TestCase):
    def test_floor_uses_taskbar_even_when_auto_hidden(self):
        a = src("snow/winapi.py")
        self.assertIn("ABM_GETTASKBARPOS", a)
        self.assertIn("ABM_GETSTATE", a)
        self.assertIn("_TB_H", a)
        self.assertIn("def get_floors", a)

    def test_engine_and_bodies_use_floor_at(self):
        self.assertIn("floor_at", src("snowman/world.py"))
        self.assertIn("floor_at", src("snow/matter.py"))
        self.assertIn("set_floors", src("snow/engine.py"))


if __name__ == "__main__":
    unittest.main()


class MusicSeekBar(unittest.TestCase):
    def test_panel_syncs_duration_and_position_when_opened(self):
        m = src("widget/music_panel.py")
        self.assertIn("self._sync_time()", m)                        # 늦게 열려도 재생바 범위/위치를 현재 값으로 맞춘다
        self.assertIn("self.seek.setRange(0, max(int(ms)", m)        # 길이를 못 받았어도 재생바가 멈추지 않는다


class TaskbarFloorStable(unittest.TestCase):
    """바탕화면/작업표시줄을 눌러도 바닥선이 모니터 맨 아래로 튀지 않는다 (순수 계산 검사)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from snow import winapi
        except Exception as exc:            # PySide6 없는 환경에서도 winapi 는 import 되어야 한다
            raise unittest.SkipTest(str(exc))
        cls.h = staticmethod(winapi.taskbar_height)

    MON = (0, 0, 1920, 1080)

    def test_work_area_wins_over_window_rects(self):
        self.assertEqual(self.h(self.MON, (0, 0, 1920, 1032), [], False, 0), 48)

    def test_unreadable_moment_keeps_last_height_without_time_limit(self):
        self.assertEqual(self.h(self.MON, (0, 0, 1920, 1080), [], False, 48), 48)

    def test_taskbar_window_rect_used_when_work_area_full(self):
        self.assertEqual(self.h(self.MON, (0, 0, 1920, 1080), [(0, 1032, 1920, 1080)], True, 0), 48)

    def test_taskbar_moved_to_side_drops_memory(self):
        self.assertEqual(self.h(self.MON, (60, 0, 1920, 1080), [], False, 48), 0)

    def test_no_taskbar_info_at_all_means_monitor_bottom(self):
        self.assertEqual(self.h(self.MON, None, [], False, 0), 0)


class DecorNeverCoversTaskbar(unittest.TestCase):
    def test_decor_windows_are_clipped_by_taskbar_rect(self):
        l = src("decor/layer.py")
        self.assertIn("def clip_to_taskbar", l)
        self.assertIn("clip_all_to_taskbar()", l)
        self.assertIn("def moveEvent", l)


class MusicTitleFixedSize(unittest.TestCase):
    def test_long_title_is_elided_not_wrapped(self):
        m = src("widget/music_panel.py")
        self.assertIn("class ElideLabel", m)
        self.assertIn("self.lbl_title = MarqueeLabel(", m)
        self.assertIn("Qt.ElideRight", m)


class GroundCatchesFallingSnow(unittest.TestCase):
    def test_new_snow_piles_on_taskbar_line(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from snow.matter import is_ground
        from snow.physics import Rect, SnowSim
        s = SnowSim()
        s.cell = 3
        s.set_bounds(Rect(0, 0, 1920, 1080))
        s.set_monitors([(0, 0, 1920, 1080)], [1032.0])
        for _ in range(1200):
            s.step(1 / 30)
        ground = [p for k, p in s.piles.items() if is_ground(k)]
        self.assertGreater(sum(p.total() * p.cell for p in ground), 1500)     # 예전에는 새로 내리는 눈을 바닥이 받지 않아 ~600 에 머물렀다
