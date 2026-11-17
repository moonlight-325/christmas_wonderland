import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dday import dday_text, days_until_christmas, date_text  # noqa: E402
from settings.store import SettingsStore, sanitize  # noqa: E402


class DdayTests(unittest.TestCase):
    def test_before(self):
        self.assertEqual(days_until_christmas(date(2026, 11, 12)), 43)
        self.assertEqual(dday_text(date(2026, 11, 12)), "D-43")

    def test_day_of(self):
        self.assertEqual(dday_text(date(2026, 12, 25)), "D-DAY")

    def test_after_rolls_to_next_year(self):
        self.assertEqual(days_until_christmas(date(2026, 12, 26)), 364)
        self.assertEqual(days_until_christmas(date(2027, 12, 26)), 365)  # 2028 윤년

    def test_date_text(self):
        self.assertEqual(date_text(date(2026, 11, 12)), "2026년 11월 12일 목요일")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_when_missing(self):
        s = SettingsStore(self.dir)
        self.assertEqual(s.load(), "defaults")
        self.assertEqual(s.get("widget.mode"), "normal")

    def test_roundtrip_persists(self):
        s = SettingsStore(self.dir); s.load()
        s.set("widget.x", 100); s.set("widget.mode", "bottom")
        s.set("snow.amount", 250); s.set("music.folder", "D:/음악")
        self.assertTrue(s.save())
        s2 = SettingsStore(self.dir)
        self.assertEqual(s2.load(), "primary")
        self.assertEqual(s2.get("widget.x"), 100)
        self.assertEqual(s2.get("widget.mode"), "bottom")
        self.assertEqual(s2.get("snow.amount"), 250)
        self.assertEqual(s2.get("music.folder"), "D:/음악")

    def test_clamp_and_choices(self):
        s = SettingsStore(self.dir); s.load()
        s.set("snow.amount", 99999); s.set("widget.opacity", 0.0); s.set("widget.mode", "top")
        self.assertEqual(s.get("snow.amount"), 1000)
        self.assertEqual(s.get("widget.opacity"), 0.2)
        self.assertEqual(s.get("widget.mode"), "normal")   # 항상 위는 허용하지 않음
        s.set("wind.direction", 500); s.set("wind.strength", -5)
        self.assertEqual((s.get("wind.direction"), s.get("wind.strength")), (359, 0))

    def test_sanitize_bad_types(self):
        d = sanitize({"widget": {"width": "abc", "locked": 1}, "snow": [], "junk": 1})
        self.assertEqual(d["widget"]["width"], 420)
        self.assertFalse(d["widget"]["locked"])
        self.assertNotIn("junk", d)

    def test_corrupt_recovers_from_bak(self):
        s = SettingsStore(self.dir); s.load()
        s.set("snow.amount", 77); s.save()
        s.set("snow.amount", 78); s.save()        # 두 번째 저장 -> .bak 에 77
        (self.dir / "settings.json").write_text("{ broken json", encoding="utf-8")
        s2 = SettingsStore(self.dir)
        self.assertEqual(s2.load(), "recovered")
        self.assertEqual(s2.get("snow.amount"), 77)
        self.assertTrue(list(self.dir.glob("settings.corrupt-*.json")))

    def test_corrupt_recovers_from_rotating_backup(self):
        s = SettingsStore(self.dir); s.load()
        s.set("widget.width", 555); s.save(manual=True)
        (self.dir / "settings.json").write_text("", encoding="utf-8")
        (self.dir / "settings.json.bak").unlink(missing_ok=True)
        s2 = SettingsStore(self.dir)
        self.assertEqual(s2.load(), "recovered")
        self.assertEqual(s2.get("widget.width"), 555)

    def test_no_tmp_left_and_valid_json(self):
        s = SettingsStore(self.dir); s.load(); s.save()
        self.assertFalse((self.dir / "settings.json.tmp").exists())
        json.loads((self.dir / "settings.json").read_text(encoding="utf-8"))

    def test_rotating_backup_limit(self):
        import settings.store as st
        s = SettingsStore(self.dir); s.load(); s.save()
        s.backup_dir.mkdir(exist_ok=True)
        for i in range(10):
            (s.backup_dir / f"settings_2026010{i}_000000.json").write_text("{}")
        s.snapshot_backup()
        self.assertLessEqual(len(list(s.backup_dir.glob("settings_*.json"))), st.MAX_ROTATING_BACKUPS)


if __name__ == "__main__":
    unittest.main()
