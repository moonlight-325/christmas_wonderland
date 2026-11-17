"""렉 진단 로그 형식과 창 추적 최적화(소스 구조) 점검. Qt/Windows 없이 돈다."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def width(text):
    return sum(2 if ord(c) > 0x2E7F else 1 for c in text)


def lag_template():
    """engine._lag_check 의 [렉 진단] 로그 템플릿을 소스에서 그대로 꺼낸다."""
    e = src("snow/engine.py")
    a = e.index('log.warning("[렉 진단]')
    b = e.index("gap_ms, want, step_ms", a)
    body = e[a + len("log.warning("):b]
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
    return "".join(parts).replace("\\n", "\n")


class LagLogFormat(unittest.TestCase):
    def test_lines_and_labels(self):
        lines = lag_template().split("\n")
        self.assertEqual(lines[0], "[렉 진단] 프레임 간격 %.1fms (목표 %.1fms)")
        labels = ["계산", "장식 영역", "그리기 요청", "일반 오버레이", "장식 오버레이", "창 추적", "개수", "눈 구간", "셀", "눈더미 캐시"]
        self.assertEqual(len(lines), 1 + len(labels))
        for label, line in zip(labels, lines[1:]):
            self.assertTrue(line.startswith(label), (label, line))
        self.assertIn("(paint 합계)", lines[4])
        self.assertIn("(paint 합계)", lines[5])
        self.assertIn("(GUI 처리) / 수집", lines[6])
        self.assertIn("오버레이 일반 %d/장식 %d", lines[7])
        self.assertIn("적중 %d · 재생성 %d", lines[10])

    def test_value_column_is_aligned_by_display_width(self):
        for line in lag_template().split("\n")[1:]:
            label = re.match(r"^(\S+(?: \S+)?)", line).group(1)
            rest = line[len(label):]
            gap = len(rest) - len(rest.lstrip(" "))
            self.assertEqual(width(label) + gap if width(label) < 12 else 12, 12, line)

    def test_english_template_matches_placeholders(self):
        ko = lag_template()
        en = json.loads(src("assets/lang/en.json"))[ko]
        self.assertEqual(re.findall(r"%[-\d.]*[sdf]", ko), re.findall(r"%[-\d.]*[sdf]", en))
        self.assertEqual(ko.count("\n"), en.count("\n"))

    def test_log_args_match_template(self):
        e = src("snow/engine.py")
        a = e.index("gap_ms, want, step_ms")
        b = e.index("hits, builds)", a)
        args = e[a:b]
        self.assertIn("self._decor_ms", args)
        self.assertIn("self._update_ms", args)
        self.assertIn("paint_top", args)
        self.assertIn("self._collect_ms", args)


class TrackingOptimisation(unittest.TestCase):
    def test_snapshot_caches_static_window_info(self):
        w = src("snow/winapi.py")
        self.assertIn("def _static_info", w)
        # Z-order 를 만지는 함수들은 캐시를 쓰지 않는다 (기존 창 동작 보존)
        for name in ("_taskbar_rects", "_desktop_above", "_above_desktop_target"):
            a = w.index("def " + name)
            b = w.index("\ndef ", a + 1)
            body = w[a:b]
            self.assertNotIn("_class_name(", body, name)
            self.assertNotIn("_pid(", body, name)

    def test_track_tick_skips_only_when_unchanged(self):
        e = src("snow/engine.py")
        a = e.index("    def _track_tick(self):")
        b = e.index("    def _check_fullscreen(self):")
        body = e[a:b]
        self.assertIn("TRACK_FULL_EVERY", body)              # 안전망: 가끔은 전부 다시 계산
        self.assertIn("self._check_fullscreen()", body)      # 전체화면 확인은 매번
        self.assertIn("self._collect_ms", body)
        self.assertIn("self.world.set_obstacles", body)
        self.assertIn("self._track_sig = None", e)           # 추적을 껐다 켜면 처음부터 계산

    def test_decor_tick_keeps_fallback_and_has_no_zorder_calls(self):
        e = src("snow/engine.py")
        a = e.index("    def _decor_tick(self):")
        b = e.index("    def _lag_check(self")
        body = e[a:b]
        self.assertIn("DECOR_OCC_EVERY", body)               # 창 추적이 꺼져 있을 때는 예전 주기 그대로
        self.assertIn("DECOR_OCC_IDLE_EVERY", body)
        for token in ("keep_top", "settle", "SetWindowPos", "keep_bottom"):
            self.assertNotIn(token, body)

    def test_overlay_counts_pile_cache(self):
        o = src("snow/overlay.py")
        self.assertIn("self.cache_hits += 1", o)
        self.assertIn("self.cache_builds += 1", o)


if __name__ == "__main__":
    unittest.main()
