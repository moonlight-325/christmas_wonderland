"""실시간 로그 보기 검증 (PySide6 불필요). PowerShell 스크립트 자체의 실행은 Windows 에서만 확인 가능."""
import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logviewer import CREATE_NEW_CONSOLE, LogViewerError, build_script, encode_command, open_log_console  # noqa: E402


class LogViewerTests(unittest.TestCase):
    def test_script_contains_path_and_escapes_quotes(self):
        s = build_script(Path("C:/Users/O'Neil/app/data/app.log"))
        self.assertIn("O''Neil", s)
        self.assertIn("ReadWrite,Delete", s)               # 로그 회전을 막지 않도록 삭제 공유 허용
        self.assertIn("Christmas Wonderland - Live Log", s)
        self.assertIn("Log file: $p", s)
        self.assertIn("Closing this window will not exit Christmas Wonderland", s)
        self.assertIn("Start-Sleep", s)

    def test_script_braces_are_balanced(self):
        s = build_script(Path("C:/x/app.log"))
        self.assertEqual(s.count("{"), s.count("}"))

    def test_encoded_command_round_trips(self):
        s = build_script(Path("C:/x/app.log"))
        self.assertEqual(base64.b64decode(encode_command(s)).decode("utf-16-le"), s)

    def test_opens_separate_console_without_waiting(self):
        calls = []

        class P:
            def poll(self):
                return None

        def fake(cmd, **kw):
            calls.append((cmd, kw))
            return P()

        with tempfile.TemporaryDirectory() as d:
            proc = open_log_console(Path(d) / "app.log", popen=fake, windows=True)
        cmd, kw = calls[0]
        self.assertIsNotNone(proc)
        self.assertEqual(cmd[0], "powershell.exe")
        self.assertIn("-EncodedCommand", cmd)
        self.assertTrue(kw["creationflags"] & CREATE_NEW_CONSOLE)       # 앱과 분리된 새 콘솔
        self.assertNotIn("stdout", kw)                                  # 새 콘솔의 표준 출력 유지
        self.assertNotIn("stderr", kw)                                  # 새 콘솔의 오류 출력 유지
        self.assertNotIn("shell", kw)

    def test_non_windows_gives_clear_error(self):
        with self.assertRaises(LogViewerError) as cm:
            open_log_console(popen=lambda *a, **k: self.fail("실행되면 안 됨"), windows=False)
        self.assertIn("Windows", str(cm.exception))

    def test_missing_powershell_and_oserror_become_messages(self):
        def missing(*a, **k):
            raise FileNotFoundError()

        def broken(*a, **k):
            raise OSError(5, "denied")

        with self.assertRaises(LogViewerError) as cm:
            open_log_console(Path("x/app.log"), popen=missing, windows=True)
        self.assertIn("PowerShell", str(cm.exception))
        with self.assertRaises(LogViewerError):
            open_log_console(Path("x/app.log"), popen=broken, windows=True)


if __name__ == "__main__":
    unittest.main()
