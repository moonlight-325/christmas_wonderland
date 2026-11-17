"""v2.0.0 일반 설정 개편 회귀 테스트 (PySide6 불필요)."""
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DisplaySettingsPersistence(unittest.TestCase):
    def test_new_display_options_default_to_enabled(self):
        from settings.store import SettingsStore
        with tempfile.TemporaryDirectory() as td:
            store = SettingsStore(Path(td))
            store.load()
            self.assertTrue(store.get("app.show_tray"))
            self.assertTrue(store.get("app.show_taskbar"))

    def test_sanitize_keeps_one_display_entry_point_enabled(self):
        from settings.store import sanitize
        clean = sanitize({"app": {"show_tray": False, "show_taskbar": False}})
        self.assertTrue(clean["app"]["show_tray"])
        self.assertFalse(clean["app"]["show_taskbar"])

    def test_display_options_round_trip(self):
        from settings.store import SettingsStore
        with tempfile.TemporaryDirectory() as td:
            store = SettingsStore(Path(td))
            store.load()
            store.set("app.show_tray", False)
            store.set("app.show_taskbar", True)
            self.assertTrue(store.save())
            loaded = SettingsStore(Path(td))
            loaded.load()
            self.assertFalse(loaded.get("app.show_tray"))
            self.assertTrue(loaded.get("app.show_taskbar"))


class GeneralSettingsUI(unittest.TestCase):
    def test_language_and_performance_controls_are_in_general_page(self):
        src = (ROOT / "widget/settings_window.py").read_text(encoding="utf-8")
        self.assertIn('("gear", tr("일반", "settings_tab"))', src)
        self.assertIn('self._page_window, self._page_general', src)
        general = src.split("def _page_general(self):", 1)[1]
        self.assertIn('self._choice(lay, tr("언어"), "app.language"', general)
        self.assertIn('"performance.fps"', general)
        window = src.split("def _page_window(self):", 1)[1].split("def _set_display_option", 1)[0]
        self.assertNotIn('"app.language"', window)

    def test_display_controls_have_at_least_one_enabled_guard(self):
        src = (ROOT / "widget/settings_window.py").read_text(encoding="utf-8")
        self.assertIn('if not enabled and not self.s.get(other_key):', src)
        self.assertIn('"app.show_tray"', src)
        self.assertIn('"app.show_taskbar"', src)

    def test_taskbar_and_tray_visibility_are_applied(self):
        main = (ROOT / "widget/main_widget.py").read_text(encoding="utf-8")
        tray = (ROOT / "widget/tray.py").read_text(encoding="utf-8")
        winz = (ROOT / "widget/winz.py").read_text(encoding="utf-8")
        self.assertIn('flags |= Qt.Window', main)
        self.assertIn('winz.set_taskbar_visible(self', main)
        self.assertIn('WS_EX_TOOLWINDOW', winz)
        self.assertIn('WS_EX_APPWINDOW', winz)
        self.assertIn('self.icon.setVisible(visible)', tray)

    def test_english_labels_exist(self):
        translations = json.loads((ROOT / "assets/lang/en.json").read_text(encoding="utf-8"))
        self.assertEqual(translations["일반"], "Normal")
        self.assertEqual(translations["settings_tab|일반"], "General")
        self.assertEqual(translations["프로그램 표시 방식"], "Program visibility")
        self.assertEqual(translations["시스템 트레이에 표시"], "Show in system tray")
        self.assertEqual(translations["작업표시줄에 표시"], "Show on taskbar")


if __name__ == "__main__":
    unittest.main()
