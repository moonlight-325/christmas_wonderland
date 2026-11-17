"""v1.9.6 UI Stage 6: 소원 입력 피드백(글자 수·빈 칸 오류 표시), 음악 현재 곡·반복 표시. 어드벤트 테스트 모드 삭제 확인.

PySide6 없이 실행되는 부분: 문구 함수, 소스 정적 검사. `*Qt` 클래스는 PySide6 가 있을 때만 실행된다.
"""
import os
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


class AdventTestModeRemoved(unittest.TestCase):
    def test_no_test_mode_in_advent_sources(self):
        for f in sorted((ROOT / "advent").glob("*.py")):
            text = f.read_text(encoding="utf-8")
            for word in ("test_enabled", "set_test_", "mark_test_opened", "reset_test_records", "MODE_FORCE_ALL",
                         "MODE_SIMULATE", "btn_test", "tag_test", "_paint_banner", "테스트 모드", "테스트 기록 지우기"):
                self.assertNotIn(word, text, f"{f.name}: {word}")

    def test_default_state_has_no_test_section(self):
        from advent.state import DEFAULTS, sanitize
        self.assertNotIn("test", DEFAULTS)
        self.assertNotIn("test", sanitize({"test": {"enabled": True}}))


class MusicTexts(unittest.TestCase):
    def test_now_text(self):
        from widget.music_panel import now_text
        self.assertEqual(now_text(-1, 5, "", False), "재생 중인 곡 없음")
        self.assertEqual(now_text(0, 0, "x", True), "재생 중인 곡 없음")
        self.assertEqual(now_text(2, 12, "Jingle", True), "3/12  Jingle  (재생 중)")
        self.assertEqual(now_text(0, 1, "Jingle", False), "1/1  Jingle  (일시정지)")

    def test_list_text_marks_only_current(self):
        from widget.music_panel import list_text
        self.assertTrue(list_text("a", "기본", True).startswith("> "))
        self.assertTrue(list_text("a", "기본", False).startswith("  "))
        self.assertTrue(list_text("a", "기본", False).endswith("[기본]"))

    def test_repeat_texts_cover_all_modes(self):
        from widget.music_panel import REPEAT_LABEL, REPEAT_TIP
        self.assertEqual(set(REPEAT_LABEL), {"all", "one", "off"})
        self.assertEqual(set(REPEAT_TIP), set(REPEAT_LABEL))


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class WishEventQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def make(self, prev=None):
        from advent.events import WishEvent
        return WishEvent({"type": "wish", "prompt": "p", "success": "ok"}, prev)

    def test_counter_follows_text(self):
        w = self.make()
        self.assertEqual(w.count.text(), "0/60")
        w.edit.setText("건강하기")
        self.assertEqual(w.count.text(), "4/60")
        w.edit.setText("가" * 80)                                  # 최대 글자 수에서 잘림
        self.assertEqual(w.count.text(), "60/60")

    def test_empty_send_shows_error_and_typing_clears_it(self):
        from advent.events import LINE_STYLE, LINE_STYLE_ERR
        w = self.make()
        got = []
        w.done.connect(got.append)
        w._send()
        self.assertEqual(got, [])                                  # 빈 소원은 저장하지 않음
        self.assertIn("한 줄", w.note.text())
        self.assertEqual(w.edit.styleSheet(), LINE_STYLE_ERR)
        w.edit.setText("a")
        self.assertEqual(w.edit.styleSheet(), LINE_STYLE)
        self.assertEqual(w.note.text(), "")

    def test_send_lock_and_rewrite(self):
        w = self.make()
        got = []
        w.done.connect(got.append)
        w.edit.setText("  행복  ")
        w._send()
        self.assertEqual(got, [{"done": True, "text": "행복"}])
        self.assertFalse(w.edit.isEnabled())
        self.assertEqual(w.btn.text(), "다시 쓰기")
        w._send()                                                  # 다시 쓰기
        self.assertTrue(w.edit.isEnabled())
        self.assertEqual(w.btn.text(), "별에게 보내기")
        self.assertEqual(w.count.text(), "2/60")
        w.grab()

    def test_previous_wish_is_restored_locked(self):
        w = self.make({"done": True, "text": "예전 소원"})
        self.assertEqual(w.edit.text(), "예전 소원")
        self.assertFalse(w.edit.isEnabled())


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class MusicPanelQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from core.fonts import load_fonts
        load_fonts()

    def setUp(self):
        from PySide6.QtCore import QObject, Signal
        from settings.manager import SettingsManager

        class Track:
            def __init__(self, title, source="default"):
                self.title, self.source, self.path = title, source, f"/x/{title}.mp3"

        class FakeAudio(QObject):
            playlistChanged = Signal()
            trackChanged = Signal(int, str)
            playingChanged = Signal(bool)
            positionChanged = Signal(int)
            durationChanged = Signal(int)
            message = Signal(str)

            def __init__(self):
                super().__init__()
                self.tracks = [Track("A"), Track("B", "folder"), Track("C", "user")]
                self.index = 0
                self.is_playing = False

            def current_title(self):
                return self.tracks[self.index].title if 0 <= self.index < len(self.tracks) else ""

            def cycle_repeat(self):
                pass

            def __getattr__(self, n):
                return lambda *a, **k: None

        from widget.music_panel import MusicPanel
        self.tmp = tempfile.TemporaryDirectory()
        self.s = SettingsManager(Path(self.tmp.name))
        self.audio = FakeAudio()
        self.p = MusicPanel(self.audio, self.s)

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def test_current_track_and_play_state_shown(self):
        self.assertEqual(self.p.lbl_title.text(), "1/3  A  (일시정지)")
        self.audio.is_playing = True
        self.audio.playingChanged.emit(True)
        self.assertEqual(self.p.lbl_title.text(), "1/3  A  (재생 중)")
        self.audio.index = 2
        self.audio.trackChanged.emit(2, "C")
        self.assertEqual(self.p.lbl_title.text(), "3/3  C  (재생 중)")

    def test_list_marks_only_the_current_track(self):
        marks = [self.p.list.item(i).text().startswith("> ") for i in range(3)]
        self.assertEqual(marks, [True, False, False])
        self.audio.index = 1
        self.audio.trackChanged.emit(1, "B")
        marks = [self.p.list.item(i).text().startswith("> ") for i in range(3)]
        self.assertEqual(marks, [False, True, False])

    def test_no_track_message(self):
        self.audio.tracks = []
        self.audio.index = -1
        self.audio.trackChanged.emit(-1, "")
        self.assertEqual(self.p.lbl_title.text(), "재생 중인 곡 없음")

    def test_repeat_button_text_tip_and_emphasis(self):
        from widget.music_panel import REPEAT_LABEL
        for mode in ("all", "one", "off"):
            self.s.set("music.repeat", mode)
            self.assertEqual(self.p.btn_repeat.text(), REPEAT_LABEL[mode])
            self.assertEqual(self.p.btn_repeat.toolTip(), "")     # Stage 7: 설명 툴팁 삭제 (버튼 글자가 방식을 보여 줌)
            self.assertEqual(self.p.btn_repeat._kind, "normal" if mode == "off" else "accent")
        self.p.grab()


if __name__ == "__main__":
    unittest.main()
