"""v2.0.0 버전 정렬 검증: 버전 정렬, 삭제된 파일/코드가 다시 생기지 않았는지 (PySide6 불필요)."""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _py_files():
    for p in ROOT.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


class VersionTest(unittest.TestCase):
    def test_version_is_200(self):
        from core import version
        self.assertEqual(version.__version__, "2.0.0")

    def test_readme_title_and_changelog(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Christmas Wonderland v2.0.0"))
        self.assertIn("## v2.0.0", text)

    def test_no_other_current_version_strings(self):
        """실행 코드의 버전 상수는 version.py 한 곳뿐이어야 한다."""
        hits = []
        for p in _py_files():
            if p.name == "version.py" or "tests" in p.parts:
                continue
            if re.search(r"__version__\s*=", p.read_text(encoding="utf-8")):
                hits.append(p.name)
        self.assertEqual(hits, [])


class CleanupTest(unittest.TestCase):
    def test_desktop_package_removed(self):
        self.assertFalse((ROOT / "desktop").exists())

    def test_nothing_imports_desktop(self):
        for p in _py_files():
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                mods = []
                if isinstance(n, ast.Import):
                    mods = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                    mods = [n.module]
                for m in mods:
                    self.assertNotEqual(m.split(".")[0], "desktop", f"{p.name}: {m}")

    def test_removed_dead_code_stays_removed(self):
        gone = {
            "snow/physics.py": ["def height_at", "def _trim_extra"],
            "snowglobe/model.py": ["def ground_contains"],
            "widget/pixel_ui.py": ["def draw_text("],
            "widget/auto_weather_page.py": ["tips = {"],
        }
        for rel, needles in gone.items():
            src = (ROOT / rel).read_text(encoding="utf-8")
            for n in needles:
                self.assertNotIn(n, src, f"{rel}: {n}")

    def test_lock_tooltips_removed(self):
        for rel in ("decor/items.py", "clockface/window.py"):
            self.assertNotIn("(잠김)", (ROOT / rel).read_text(encoding="utf-8"), rel)

    def test_all_modules_compile(self):
        for p in _py_files():
            compile(p.read_text(encoding="utf-8"), str(p), "exec")


if __name__ == "__main__":
    unittest.main()


class LagDiagTest(unittest.TestCase):
    def test_lag_log_splits_calc_time(self):
        src = (ROOT / "snow" / "engine.py").read_text(encoding="utf-8")
        self.assertIn("self._calc_parts", src)
        for key in ('"커서"', '"눈"', '"눈사람"', "sim.perf"):
            self.assertIn(key, src)
