"""언어 설정(i18n) 테스트: Qt 없이 돈다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import i18n
from settings.defaults import CHOICES, DEFAULTS


class I18n(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("ko")

    def _dir(self, table):
        d = Path(tempfile.mkdtemp())
        (d / "en.json").write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
        return d

    def test_korean_returns_source(self):
        i18n.set_language("ko")
        self.assertEqual(i18n.tr("눈 효과"), "눈 효과")

    def test_english_and_fallback(self):
        i18n.set_language("en", self._dir({"눈 효과": "Snow"}))
        self.assertEqual(i18n.tr("눈 효과"), "Snow")
        self.assertEqual(i18n.tr("없는 문구"), "없는 문구")

    def test_context_key_wins_then_falls_back(self):
        i18n.set_language("en", self._dir({"눈": "Snow", "eyes|눈": "Eyes"}))
        self.assertEqual(i18n.tr("눈"), "Snow")
        self.assertEqual(i18n.tr("눈", "eyes"), "Eyes")
        self.assertEqual(i18n.tr("눈", "other"), "Snow")

    def test_unknown_language_is_korean(self):
        self.assertEqual(i18n.normalize("fr"), "ko")
        self.assertEqual(i18n.normalize(None), "ko")

    def test_broken_table_is_empty(self):
        d = Path(tempfile.mkdtemp())
        (d / "en.json").write_text("{깨짐", encoding="utf-8")
        i18n.set_language("en", d)
        self.assertEqual(i18n.tr("눈"), "눈")

    def test_init_from_settings_file(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(i18n.init_from_settings_file(d), "ko")
        (d / "settings.json").write_text(json.dumps({"app": {"language": "en"}}), encoding="utf-8")
        self.assertEqual(i18n.init_from_settings_file(d), "en")
        (d / "settings.json").write_text("[1]", encoding="utf-8")
        self.assertEqual(i18n.init_from_settings_file(d), "ko")

    def test_weekdays(self):
        i18n.set_language("en", self._dir({}))
        self.assertEqual(i18n.weekday_names()[0], "Mon")
        self.assertEqual(i18n.weekday_full_names()[6], "Sunday")
        i18n.set_language("ko")
        self.assertEqual(i18n.weekday_full_names()[0], "월요일")

    def test_settings_default_and_choices(self):
        self.assertEqual(DEFAULTS["app"]["language"], "ko")
        self.assertEqual(CHOICES["app.language"], ("ko", "en"))


if __name__ == "__main__":
    unittest.main()
