"""[프레임 요약] 진단 수집기 점검 (Qt 불필요)."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snow.diag import FrameDiag


def stat(n=40, ms=5.0):
    return {"n": n, "sum_ms": n * ms, "max_ms": ms * 3, "sum_wait": n * 2.0, "max_wait": 9.0, "sum_int": n * 70.0,
            "n_int": n, "flakes": n * 100, "size": "1920x1040", "hits": 30, "builds": 5}


def fake_sim():
    return SimpleNamespace(flakes=[0] * 100, parcels=[], piles={"a": SimpleNamespace(cells=[0.0] * 10)})


class FrameDiagTest(unittest.TestCase):
    def feed(self, d, gap, n=50):
        for _ in range(n):
            d.on_tick(gap, 33.0, 1.5, 1.0, 0.3, 0.1)
        d.on_track(3.0, 1.0, 0.5, 0.2, 0.4, True, True)
        d.on_track(1.0, 0.8, 0, 0, 0.2, False, False)

    def test_report_slow(self):
        d = FrameDiag(33.3)
        self.feed(d, 75.0)
        txt = d.build([("일반#0", stat()), ("장식#0", {"n": 0})], fake_sim(), {"모니터": "1개"})
        for key in ("[프레임 요약]", "프레임 간격", "타이머 지연", "틱 안쪽", "CPU / GC", "오버레이", "창 추적", "눈 상태", "판정"):
            self.assertIn(key, txt)
        self.assertIn("느림", txt)
        self.assertIn("그려지지 않음", txt)
        self.assertEqual(len(d.gaps), 0)                      # 보고 뒤 초기화

    def test_report_ok(self):
        d = FrameDiag(33.3)
        self.feed(d, 33.4)
        self.assertIn("정상", d.build([("일반#0", stat())], None))

    def test_due_needs_samples(self):
        d = FrameDiag()
        d.t0 -= 10
        self.assertFalse(d.due())
        self.feed(d, 33.0, 5)
        self.assertTrue(d.due())

    def test_gc_hook(self):
        import gc
        d = FrameDiag()
        d.start_gc()
        gc.collect()
        d.stop_gc()
        self.assertGreaterEqual(d.gc_n[2], 1)
        self.assertNotIn(d._gc_cb, gc.callbacks)


if __name__ == "__main__":
    unittest.main()
