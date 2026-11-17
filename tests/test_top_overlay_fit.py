"""장식 위 눈 오버레이: 창을 모니터 전체 대신 장식이 보이는 영역 크기로 여는 계산 점검 (PySide6 없어도 돈다)."""
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import PySide6.QtWidgets  # noqa: F401
except Exception:                       # 가짜 Qt: 계산 함수만 검사한다
    def _mod(name, **kw):
        m = types.ModuleType(name)
        m.__dict__.update(kw)
        sys.modules[name] = m
    _mod("PySide6")
    _mod("PySide6.QtCore", QRect=object, Qt=SimpleNamespace())
    _mod("PySide6.QtGui", QColor=lambda *a: a, QPainter=object, QPixmap=object, QRegion=object)
    _mod("PySide6.QtWidgets", QWidget=object)
    _mod("core")
    _mod("core.i18n", tr=lambda s: s)
    _mod("core.logger", get_logger=lambda n: SimpleNamespace())

from snow import overlay
from snow.overlay import FIT_PAD, SnowOverlay

MON = (0, 0, 2560, 1392)


def fake(fit=None):
    return SimpleNamespace(native_rect=MON, _fit=fit)


def plan(o, rects):
    return SnowOverlay._plan_fit(o, rects)


class FitPlan(unittest.TestCase):
    def test_small_decor_gets_small_window(self):
        r = plan(fake(), [(1000, 600, 1300, 800)])
        self.assertEqual(r, (1000 - FIT_PAD, 600 - FIT_PAD, 1300 + FIT_PAD, 800 + FIT_PAD))
        self.assertLess((r[2] - r[0]) * (r[3] - r[1]), 0.1 * 2560 * 1392)

    def test_clamped_to_monitor(self):
        r = plan(fake(), [(0, 0, 2560, 60)])
        self.assertEqual((r[0], r[1], r[2]), (0, 0, 2560))
        self.assertTrue(0 <= r[1] and r[3] <= 1392)

    def test_small_move_keeps_window(self):
        o = fake()
        first = plan(o, [(1000, 600, 1300, 800)])
        o._fit = first
        self.assertEqual(plan(o, [(1020, 610, 1320, 810)]), first)        # 조금 움직임: 창 그대로

    def test_big_move_resizes(self):
        o = fake()
        o._fit = plan(o, [(1000, 600, 1300, 800)])
        self.assertNotEqual(plan(o, [(1900, 900, 2200, 1100)]), o._fit)   # 밖으로 나감: 새로 연다

    def test_shrinks_when_decor_gets_much_smaller(self):
        o = fake((0, 0, 2560, 1392))
        r = plan(o, [(1000, 600, 1100, 650)])
        self.assertLess((r[2] - r[0]) * (r[3] - r[1]), 0.1 * 2560 * 1392)

    def test_window_always_covers_rects(self):
        o = fake()
        for rects in ([(10, 10, 100, 100)], [(5, 5, 2555, 70), (2000, 1300, 2500, 1390)], [(1200, 700, 1250, 760)]):
            r = plan(o, rects)
            o._fit = r
            for (l, t, rr, b) in rects:
                self.assertTrue(r[0] <= l and r[1] <= t and r[2] >= rr and r[3] >= b, (r, rects))


if __name__ == "__main__":
    unittest.main()
