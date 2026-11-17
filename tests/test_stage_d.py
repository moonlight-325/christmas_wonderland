"""v1.9.4 D단계: 종료 단계 격리, 트레이가 참조하는 컨트롤러 멤버 정적 검사 (PySide6 불필요)."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.steps import run_steps


class RunSteps(unittest.TestCase):
    def test_failure_does_not_skip_later_steps(self):
        done = []

        def boom():
            raise RuntimeError("x")

        failed = run_steps([("a", lambda: done.append("a")), ("b", boom),
                            ("c", lambda: done.append("c")), ("d", boom), ("e", lambda: done.append("e"))])
        self.assertEqual(done, ["a", "c", "e"])
        self.assertEqual(failed, ["b", "d"])

    def test_all_ok(self):
        self.assertEqual(run_steps([("a", lambda: None)]), [])


class TrayReferences(unittest.TestCase):
    """Windows 에서 처음 실행해야 드러나는 오타를 미리 잡기 위해, 트레이가 쓰는 controller.* 이름이 실제로 있는지 본다."""

    def test_controller_members_exist(self):
        ctl = ast.parse((ROOT / "core" / "app_controller.py").read_text(encoding="utf-8"))
        cls = next(n for n in ctl.body if isinstance(n, ast.ClassDef) and n.name == "AppController")
        members = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        for node in ast.walk(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                if isinstance(node.ctx, ast.Store):
                    members.add(node.attr)
        tray = ast.parse((ROOT / "widget" / "tray.py").read_text(encoding="utf-8"))
        used = {n.attr for n in ast.walk(tray) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == "controller"}
        self.assertTrue({"show_snowglobe", "show_music", "show_calendar", "toggle_auto_weather"} <= used)
        self.assertEqual(sorted(used - members), [])


if __name__ == "__main__":
    unittest.main()
