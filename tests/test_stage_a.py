"""v1.9.4 A단계: 화면 좌표 보정 / 저장 실패 처리 / 손상 데이터 복구 (PySide6 불필요)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.geometry import clamp_into_screens
from settings.store import SettingsStore
from snowglobe import model as GM
from snowglobe.store import MAX_GLOBES, SnowGlobeStore

ONE = [(0, 0, 1920, 1080)]
TWO = [(0, 0, 1920, 1080), (1920, 0, 3840, 1080)]


class GeometryClamp(unittest.TestCase):
    def test_visible_window_is_untouched(self):
        self.assertEqual(clamp_into_screens(100, 100, 300, 200, ONE), (100, 100))
        self.assertEqual(clamp_into_screens(2000, 50, 300, 200, TWO), (2000, 50))

    def test_window_across_two_monitors_is_untouched(self):
        self.assertEqual(clamp_into_screens(1800, 100, 400, 200, TWO), (1800, 100))

    def test_removed_monitor_moves_window_back(self):
        x, y = clamp_into_screens(2500, 100, 300, 200, ONE)      # 두 번째 모니터가 사라짐
        self.assertEqual((x, y), (1620, 100))

    def test_far_negative_and_below(self):
        self.assertEqual(clamp_into_screens(-5000, -5000, 300, 200, ONE), (0, 0))
        self.assertEqual(clamp_into_screens(100, 9000, 300, 200, ONE), (100, 880))

    def test_barely_peeking_window_is_pulled_in(self):
        x, y = clamp_into_screens(1910, 100, 300, 200, ONE)      # 10px 만 보임
        self.assertEqual(x, 1620)

    def test_window_larger_than_screen_aligns_to_origin(self):
        self.assertEqual(clamp_into_screens(5000, 5000, 4000, 3000, ONE), (0, 0))

    def test_no_screens_returns_input(self):
        self.assertEqual(clamp_into_screens(-9, 77, 10, 10, []), (-9, 77))

    def test_picks_nearest_screen(self):
        self.assertEqual(clamp_into_screens(4500, 100, 300, 200, TWO), (3540, 100))


class SettingsSaveFailure(unittest.TestCase):
    def test_save_failure_returns_false_and_keeps_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            st = SettingsStore(Path(d))
            st.load()
            self.assertTrue(st.save())
            before = st.path.read_text(encoding="utf-8")
            st.tmp.mkdir()                                       # 임시 파일 자리를 폴더로 막아 쓰기 실패를 만든다
            st.set("snow.amount", 123)
            self.assertFalse(st.save())
            self.assertEqual(st.path.read_text(encoding="utf-8"), before)

    def test_corrupt_main_file_recovers_from_backup(self):
        with tempfile.TemporaryDirectory() as d:
            st = SettingsStore(Path(d))
            st.load()
            st.set("snow.amount", 321)
            self.assertTrue(st.save())
            st.set("snow.amount", 322)
            self.assertTrue(st.save())
            st.path.write_text("{ not json", encoding="utf-8")
            st2 = SettingsStore(Path(d))
            self.assertEqual(st2.load(), "recovered")
            self.assertIn(st2.get("snow.amount"), (321, 322))
            self.assertTrue(list(Path(d).glob("settings.corrupt-*.json")))   # 손상 파일은 보존


class GlobeStoreRobustness(unittest.TestCase):
    def test_max_globes_is_twelve(self):
        self.assertEqual(MAX_GLOBES, 12)

    def test_corrupt_file_without_backup_gives_empty(self):
        with tempfile.TemporaryDirectory() as d:
            st = SnowGlobeStore(Path(d) / "snowglobes.json")
            st.path.write_text("garbage", encoding="utf-8")
            data = st.load()
            self.assertEqual(data["globes"], [])
            self.assertEqual(st.load_result, "failed")

    def test_corrupt_file_recovers_from_backup(self):
        with tempfile.TemporaryDirectory() as d:
            st = SnowGlobeStore(Path(d) / "snowglobes.json")
            g = GM.new_globe(10, 20, "classic", "night") if "classic" else None
            self.assertTrue(st.save([g], g["id"]))
            self.assertTrue(st.save([g], g["id"]))               # 두 번 저장해야 .bak 이 생긴다
            st.path.write_text("garbage", encoding="utf-8")
            data = SnowGlobeStore(st.path).load()
            self.assertEqual(len(data["globes"]), 1)

    def test_save_failure_returns_false(self):
        with tempfile.TemporaryDirectory() as d:
            st = SnowGlobeStore(Path(d) / "snowglobes.json")
            st.path.with_suffix(".json.tmp").mkdir()
            self.assertFalse(st.save([], None))


if __name__ == "__main__":
    unittest.main()
