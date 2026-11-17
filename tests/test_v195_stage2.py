"""v1.9.5 Stage 2: 공통 UI 규칙 정적 검사 (PySide6 불필요). 화면 표시 자체는 Windows/GUI 에서 확인해야 한다."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "widget" / "pixel_ui.py").read_text(encoding="utf-8")


class PixelUiRules(unittest.TestCase):
    def test_global_stylesheet_has_disabled_rules(self):
        for sel in ("QPushButton:disabled", "QSpinBox:disabled", "QLineEdit:disabled", "QListWidget:disabled",
                    "QMenu::item:disabled"):
            self.assertIn(sel, SRC)

    def test_slider_has_disabled_look_and_repaints_on_change(self):
        a = SRC.index("class PixelSlider")
        b = SRC.index("class PixelTabs")
        body = SRC[a:b]
        self.assertIn("isEnabled()", body)
        self.assertIn("EnabledChange", body)

    def test_palette_tokens_used_exist(self):
        pal = set(re.findall(r'"(\w+)":\s*"#', SRC[SRC.index("PAL = {"):SRC.index("def C(")]))
        used = set(re.findall(r'PAL\["(\w+)"\]', SRC)) | set(re.findall(r'\bC\("(\w+)"', SRC))
        self.assertEqual(sorted(u for u in used if u not in pal and not u.startswith("#")), [])


if __name__ == "__main__":
    unittest.main()
