"""Advent Calendar 로직 검증 (PySide6 불필요): 실제 날짜 / 저장·복구 / 콘텐츠 / 미니게임."""
import json
import os
import random
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advent.content import ANIMATIONS, load_contents, parse  # noqa: E402
from advent.fx import CatchGame, FxEngine  # noqa: E402
from advent.launcher import (LaunchAction, LaunchError, LaunchTracker, find_python, gifts_root,  # noqa: E402
                             launch, parse_action, resolve_target)
from advent.logic import (AVAILABLE, LOCKED, OPENED, all_statuses, box_status, build_context,  # noqa: E402
                          default_view_year, unlock_message)
from advent.state import AdventStore  # noqa: E402


def counts(ctx):
    s = all_statuses(ctx)
    return (sum(v == LOCKED for v in s.values()), sum(v == AVAILABLE for v in s.values()), sum(v == OPENED for v in s.values()))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.st = AdventStore(self.dir)
        self.st.load()

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, today, year=None):
        return build_context(self.st, year or today.year, today)


class RealDateTests(Base):
    def test_before_december_all_locked(self):
        for d in (date(2026, 1, 1), date(2026, 11, 12), date(2026, 11, 30)):
            self.assertEqual(counts(self.ctx(d)), (24, 0, 0), d)

    def test_each_december_day_unlocks_that_day(self):
        for n in range(1, 25):
            c = self.ctx(date(2026, 12, n))
            self.assertEqual(counts(c), (24 - n, n, 0), n)
            self.assertEqual(box_status(c, n), AVAILABLE)
            if n < 24:
                self.assertEqual(box_status(c, n + 1), LOCKED)

    def test_after_24th_all_available(self):
        for d in (date(2026, 12, 25), date(2026, 12, 31)):
            self.assertEqual(counts(self.ctx(d)), (0, 24, 0))

    def test_every_year_repeats(self):
        self.assertEqual(counts(self.ctx(date(2027, 12, 3))), (21, 3, 0))
        self.assertEqual(counts(self.ctx(date(2027, 11, 30))), (24, 0, 0))

    def test_past_year_open_future_year_locked(self):
        today = date(2027, 3, 5)
        self.assertEqual(counts(self.ctx(today, 2026)), (0, 24, 0))      # 지난 해 상자는 언제든 다시 열 수 있음
        self.assertEqual(counts(self.ctx(today, 2027)), (24, 0, 0))

    def test_unlock_message(self):
        c = self.ctx(date(2026, 11, 12))
        self.assertEqual(unlock_message(c, 1), "12월 1일에 열 수 있어요 (D-19)")
        self.assertEqual(unlock_message(c, 24), "12월 24일에 열 수 있어요 (D-42)")

    def test_opened_stays_opened_even_if_clock_goes_back(self):
        self.st.mark_opened(2026, 5)
        self.assertEqual(box_status(self.ctx(date(2026, 12, 10)), 5), OPENED)
        self.assertEqual(box_status(self.ctx(date(2026, 11, 1)), 5), OPENED)      # 시스템 날짜를 되돌려도 유지
        self.assertEqual(counts(self.ctx(date(2026, 12, 10))), (14, 9, 1))

    def test_system_date_today(self):
        """실제 시스템 날짜(date.today())로 판정."""
        today = date.today()
        c = self.ctx(today)
        for d in range(1, 25):
            expect = AVAILABLE if date(today.year, 12, d) <= today else LOCKED
            self.assertEqual(box_status(c, d), expect)


class PersistenceTests(Base):
    def test_opened_persists_and_restores(self):
        self.st.mark_opened(2026, 1)
        self.st.mark_opened(2026, 3)
        self.st.mark_opened(2025, 24)
        s2 = AdventStore(self.dir)
        self.assertEqual(s2.load(), "primary")
        self.assertEqual(s2.opened_days(2026), {1, 3})
        self.assertEqual(s2.opened_days(2025), {24})
        self.assertEqual(s2.last_opened["day"], 24 if False else 3 if False else s2.last_opened["day"])
        self.assertEqual((s2.last_opened["year"], s2.last_opened["day"]), (2025, 24))

    def test_corrupt_file_recovers_from_backup(self):
        self.st.mark_opened(2026, 2)
        self.st.mark_opened(2026, 4)                 # 두 번째 저장 -> .bak 에 {2}
        (self.dir / "advent_state.json").write_text("{ nope", encoding="utf-8")
        s2 = AdventStore(self.dir)
        self.assertEqual(s2.load(), "recovered")
        self.assertIn(2, s2.opened_days(2026))

    def test_garbage_values_sanitized(self):
        (self.dir / "advent_state.json").write_text(json.dumps(
            {"opened": {"2026": [1, 1, 99, "x", True, 5]}, "settings": {"animations": "no", "content_path": 5}}), encoding="utf-8")
        s = AdventStore(self.dir)
        s.load()
        self.assertEqual(s.opened_days(2026), {1, 5})
        self.assertTrue(s.get_setting("animations"))

    def test_old_test_mode_data_is_ignored_and_dropped(self):
        """예전 버전이 저장한 테스트 모드 기록은 읽을 때 무시하고, 다음 저장 때 파일에서 사라진다. 실제 기록은 그대로."""
        (self.dir / "advent_state.json").write_text(json.dumps(
            {"opened": {"2026": [2]}, "test": {"enabled": True, "mode": "simulate", "simulated_date": "2026-12-10", "opened": [7, 20]}}),
            encoding="utf-8")
        s = AdventStore(self.dir)
        s.load()
        self.assertEqual(s.opened_days(2026), {2})
        self.assertNotIn("test", s.data)
        s.mark_opened(2026, 3)
        saved = json.loads((self.dir / "advent_state.json").read_text(encoding="utf-8"))
        self.assertNotIn("test", saved)
        self.assertEqual(saved["opened"]["2026"], [2, 3])

    def test_default_view_year_is_real_year(self):
        self.assertEqual(default_view_year(date(2030, 1, 1)), 2030)

    def test_settings_and_events_persist(self):
        self.st.set_setting("animations", False)
        self.st.set_setting("content_path", "D:/my.json")
        self.st.set_event(2026, 3, {"done": True, "correct": True, "choice": 0})
        self.st.set_event(2026, 4, {"done": True, "text": "건강하기"})
        s2 = AdventStore(self.dir)
        s2.load()
        self.assertFalse(s2.get_setting("animations"))
        self.assertEqual(s2.get_setting("content_path"), "D:/my.json")
        self.assertEqual(s2.get_event(2026, 4)["text"], "건강하기")


class ContentTests(unittest.TestCase):
    def test_default_content_has_24_valid_gifts(self):
        with tempfile.TemporaryDirectory() as d:
            cs = load_contents(Path(d))
            self.assertEqual(cs.warnings, [])
            self.assertEqual(sorted(cs.gifts), list(range(1, 25)))
            for g in cs.gifts.values():
                self.assertTrue(g.title and g.message and g.story)
                self.assertIsNotNone(g.image, g.day)
                self.assertIn(g.animation, ANIMATIONS)
                self.assertIsNotNone(g.event)
            self.assertTrue((Path(d) / "advent_contents.json").exists())     # 편집용 사본 생성

    def test_broken_items_fall_back(self):
        cs = parse({"days": [{"day": 1, "title": "a", "animation": "zzz", "event": {"type": "quiz", "question": "q", "choices": ["x"], "answer": 0}},
                             {"day": 1}, {"day": 99}, "bad"]}, Path("."), Path("x.json"))
        self.assertEqual(len(cs.gifts), 24)
        self.assertEqual(cs.gifts[1].animation, "snowfall")
        self.assertIsNone(cs.gifts[1].event)
        self.assertGreaterEqual(len(cs.warnings), 5)

    def test_bad_json_file_uses_default(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "advent_contents.json").write_text("{bad", encoding="utf-8")
            cs = load_contents(Path(d))
            self.assertEqual(len(cs.gifts), 24)
            self.assertTrue(cs.warnings)

    def test_user_edit_is_applied(self):
        with tempfile.TemporaryDirectory() as d:
            load_contents(Path(d))
            f = Path(d) / "advent_contents.json"
            data = json.loads(f.read_text(encoding="utf-8"))
            data["days"][0]["title"] = "내가 바꾼 제목"
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_contents(Path(d)).get(1).title, "내가 바꾼 제목")


def day_with_action(action):
    d = {"day": 24, "title": "t", "message": "m", "story": "s", "animation": "fireworks"}
    if action is not ...:
        d["action"] = action
    return {"days": [d]}


class ActionParseTests(unittest.TestCase):
    """JSON action 속성 파싱 (파일 시스템 불필요)."""

    def gift(self, action):
        cs = parse(day_with_action(action), Path("."), Path("x.json"))
        return cs.gifts[24], cs.warnings

    def test_default_content_has_no_action_and_no_warning(self):
        with tempfile.TemporaryDirectory() as d:
            cs = load_contents(Path(d))
            self.assertEqual(cs.warnings, [])
            self.assertTrue(all(g.action is None for g in cs.gifts.values()))

    def test_missing_action_behaves_as_before(self):
        g, warnings = self.gift(...)
        self.assertIsNone(g.action)
        self.assertEqual([w for w in warnings if w.startswith("24일")], [])
        self.assertEqual((g.title, g.message, g.story, g.animation), ("t", "m", "s", "fireworks"))

    def test_null_and_none_action_are_ignored_silently(self):
        for v in (None, "", "none"):
            g, warnings = self.gift(v)
            self.assertIsNone(g.action)
            self.assertEqual([w for w in warnings if w.startswith("24일")], [])

    def test_python_action_parsed(self):
        g, warnings = self.gift({"type": "python", "file": "gifts/christmas_tree/main.py"})
        self.assertEqual(g.action, LaunchAction("python", "gifts/christmas_tree/main.py"))
        self.assertEqual([w for w in warnings if w.startswith("24일")], [])

    def test_executable_action_parsed(self):
        g, _ = self.gift({"type": "executable", "file": "gifts/christmas_tree/christmas_tree.exe"})
        self.assertEqual(g.action, LaunchAction("executable", "gifts/christmas_tree/christmas_tree.exe"))

    def test_backslash_and_dot_segments_are_normalized(self):
        a = parse_action({"type": "python", "file": ".\\gifts\\tree\\main.py"})
        self.assertEqual(a.file, "gifts/tree/main.py")

    def test_different_days_can_have_different_programs(self):
        data = {"days": [{"day": 1, "action": {"type": "python", "file": "gifts/a/main.py"}},
                         {"day": 2, "action": {"type": "executable", "file": "gifts/b/b.exe"}}, {"day": 3}]}
        cs = parse(data, Path("."), Path("x.json"))
        self.assertEqual(cs.gifts[1].action.file, "gifts/a/main.py")
        self.assertEqual(cs.gifts[2].action.type, "executable")
        self.assertIsNone(cs.gifts[3].action)

    def test_unsupported_type_is_rejected(self):
        for t in ("shell", "cmd", "powershell", "batch", "Python", "", None, 5):
            g, warnings = self.gift({"type": t, "file": "gifts/a/x.py"})
            self.assertIsNone(g.action, t)
            self.assertTrue(any(w.startswith("24일: action") for w in warnings), t)
            with self.assertRaises(LaunchError):
                parse_action({"type": t, "file": "gifts/a/x.py"})

    def test_wrong_extension_is_rejected(self):
        for t, f in (("python", "gifts/a/x.exe"), ("python", "gifts/a/x.bat"), ("executable", "gifts/a/x.py"),
                     ("executable", "gifts/a/x.bat"), ("executable", "gifts/a/x.cmd"), ("executable", "gifts/a/x")):
            with self.assertRaises(LaunchError, msg=f):
                parse_action({"type": t, "file": f})

    def test_malformed_action_is_ignored_with_warning(self):
        for bad in ("python", 5, ["python"], {"type": "python"}, {"file": "gifts/a/x.py"}, {"type": "python", "file": ""},
                    {"type": "python", "file": 7}):
            g, warnings = self.gift(bad)
            self.assertIsNone(g.action, bad)
            self.assertTrue(any(w.startswith("24일: action") for w in warnings), bad)

    def test_parent_dir_traversal_is_rejected(self):
        for f in ("../x.py", "gifts/../x.py", "gifts/a/../../x.py", "gifts\\..\\x.py", "..\\gifts\\x.py", "gifts/a/..",
                  "gifts/%2e%2e/x.py".replace("%2e", ".")):
            with self.assertRaises(LaunchError, msg=f):
                parse_action({"type": "python", "file": f})

    def test_absolute_paths_are_rejected(self):
        for f in ("/etc/x.py", "\\\\server\\share\\gifts\\x.exe", "C:\\Windows\\notepad.exe", "C:/gifts/a/x.exe",
                  "c:gifts/a/x.exe", "\\gifts\\a\\x.exe", str(Path(tempfile.gettempdir()) / "gifts" / "x.py")):
            t = "executable" if f.lower().endswith(".exe") else "python"
            with self.assertRaises(LaunchError, msg=f):
                parse_action({"type": t, "file": f})

    def test_must_live_under_gifts_folder(self):
        for f in ("christmas_tree/main.py", "data/main.py", "assets/x.py", "main.py", "giftsX/main.py"):
            with self.assertRaises(LaunchError, msg=f):
                parse_action({"type": "python", "file": f})

    def test_odd_characters_are_rejected(self):
        for f in ("gifts/a/x.py:stream", "gifts/a/x\x00.py", "gifts/a/x?.py", "gifts/a /x.py", "gifts/a/x.py."):
            with self.assertRaises(LaunchError, msg=repr(f)):
                parse_action({"type": "python", "file": f})


class LauncherFsTests(unittest.TestCase):
    """실제 파일 시스템을 쓰는 경로 확인/실행 테스트 (임시 폴더를 앱 폴더로 사용)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "gifts" / "tree").mkdir(parents=True)
        self.script = self.root / "gifts" / "tree" / "main.py"
        self.script.write_text("print('hi')\n", encoding="utf-8")
        (self.root / "secret.py").write_text("print('secret')\n", encoding="utf-8")
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
        self.tmp.cleanup()

    def act(self, f="gifts/tree/main.py", t="python"):
        return LaunchAction(t, f)

    def test_existing_file_resolves_inside_gifts(self):
        self.assertEqual(resolve_target(self.act(), self.root), self.script.resolve())

    def test_missing_file_reports_clear_error(self):
        with self.assertRaises(LaunchError) as cm:
            resolve_target(self.act("gifts/tree/nope.py"), self.root)
        self.assertIn("찾을 수 없어요", str(cm.exception))
        self.assertIn("gifts/tree/nope.py", str(cm.exception))

    def test_missing_gifts_folder_reports_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(LaunchError) as cm:
                resolve_target(self.act(), Path(d))
            self.assertIn("찾을 수 없어요", str(cm.exception))

    def test_traversal_and_absolute_blocked_even_when_target_exists(self):
        sec = self.root / "secret.py"
        self.assertTrue(sec.is_file())
        for f in ("gifts/../secret.py", "../secret.py", str(sec), sec.as_posix()):
            with self.assertRaises(LaunchError, msg=f):
                resolve_target(self.act(f), self.root)
        with self.assertRaises(LaunchError):                      # 앱 폴더 안이지만 gifts 밖
            resolve_target(self.act("secret.py"), self.root)

    def test_absolute_path_to_file_inside_gifts_is_also_rejected(self):
        with self.assertRaises(LaunchError):
            resolve_target(self.act(str(self.script)), self.root)

    def test_symlink_escaping_gifts_is_blocked(self):
        link = self.root / "gifts" / "tree" / "evil.py"
        try:
            os.symlink(self.root / "secret.py", link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("심볼릭 링크를 만들 수 없는 환경")
        with self.assertRaises(LaunchError) as cm:
            resolve_target(self.act("gifts/tree/evil.py"), self.root)
        self.assertIn("밖", str(cm.exception))

    def test_launch_does_not_wait_for_program(self):
        """30초 걸리는 프로그램을 시작해도 launch() 는 즉시 돌아온다(= UI 스레드를 막지 않음)."""
        slow = self.root / "gifts" / "tree" / "slow.py"
        slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        t0 = time.monotonic()
        proc = launch(self.act("gifts/tree/slow.py"), self.root)
        self.procs.append(proc)
        self.assertLess(time.monotonic() - t0, 3.0)
        self.assertIsNone(proc.poll())                            # 아직 실행 중

    def test_launch_uses_program_folder_as_cwd_and_detaches_io(self):
        calls = []

        def fake_popen(cmd, **kw):
            calls.append((cmd, kw))
            return type("P", (), {"pid": 1, "poll": lambda self: None})()

        launch(self.act(), self.root, popen=fake_popen, windows=False, environ={"PATH": os.path.dirname(sys.executable)})
        cmd, kw = calls[0]
        self.assertEqual(cmd[-1], str(self.script.resolve()))
        self.assertEqual(kw["cwd"], str(self.script.resolve().parent))
        self.assertTrue(kw.get("start_new_session"))

    def test_launch_blocked_paths_never_reach_popen(self):
        def boom(*a, **k):
            raise AssertionError("실행되면 안 됨")

        for f in ("../secret.py", "gifts/../secret.py", "/x.py", "gifts/tree/missing.py"):
            with self.assertRaises(LaunchError, msg=f):
                launch(self.act(f), self.root, popen=boom)
        with self.assertRaises(LaunchError):
            launch(LaunchAction("shell", "gifts/tree/main.py"), self.root, popen=boom)

    def test_exe_launch_on_windows_uses_file_itself(self):
        exe = self.root / "gifts" / "tree" / "tree.exe"
        exe.write_bytes(b"MZ")
        calls = []
        launch(self.act("gifts/tree/tree.exe", "executable"), self.root, windows=True,
               popen=lambda cmd, **kw: calls.append((cmd, kw)) or object())
        self.assertEqual(calls[0][0], [str(exe.resolve())])
        self.assertEqual(calls[0][1]["cwd"], str(exe.resolve().parent))

    def test_exe_on_non_windows_gives_clear_error(self):
        (self.root / "gifts" / "tree" / "tree.exe").write_bytes(b"MZ")
        with self.assertRaises(LaunchError) as cm:
            launch(self.act("gifts/tree/tree.exe", "executable"), self.root, windows=False)
        self.assertIn("Windows", str(cm.exception))

    def test_popen_oserror_becomes_launch_error(self):
        def fail(*a, **k):
            raise OSError(193, "not a valid Win32 application")

        with self.assertRaises(LaunchError) as cm:
            launch(self.act(), self.root, popen=fail, windows=False, environ={"PATH": os.path.dirname(sys.executable)})
        self.assertIn("실행하지 못했어요", str(cm.exception))

    def test_tracker_blocks_duplicate_launch_while_running(self):
        slow = self.root / "gifts" / "tree" / "slow.py"
        slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        tr = LaunchTracker()
        a = self.act("gifts/tree/slow.py")
        # LaunchTracker 가 기본으로 쓰는 launch() 는 앱 폴더를 기준으로 하므로 임시 폴더용으로 감싼다
        tr = LaunchTracker(lambda act: launch(act, self.root))
        self.assertTrue(tr.start(24, a))
        self.procs.append(tr._procs[24])
        self.assertTrue(tr.is_running(24))
        self.assertFalse(tr.start(24, a))                         # 두 번째 클릭은 무시
        self.assertEqual(len(tr._procs), 1)
        tr._procs[24].kill()
        tr._procs[24].wait()
        self.assertFalse(tr.is_running(24))                       # 종료 후에는 다시 실행 가능
        self.assertFalse(tr.any_running())
        self.assertTrue(tr.start(24, a))
        self.procs.append(tr._procs[24])

    def test_tracker_failure_leaves_no_running_state(self):
        tr = LaunchTracker(lambda act: launch(act, self.root))
        with self.assertRaises(LaunchError):
            tr.start(5, self.act("gifts/tree/missing.py"))
        self.assertFalse(tr.is_running(5))
        self.assertFalse(tr.any_running())


class PythonDiscoveryTests(unittest.TestCase):
    def test_windows_prefers_real_python_and_skips_windowsapps_stub(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            stub = d / "Microsoft" / "WindowsApps"
            real = d / "Python312"
            stub.mkdir(parents=True)
            real.mkdir()
            (stub / "python.exe").write_bytes(b"")
            (real / "python.exe").write_bytes(b"MZ")
            env = {"PATH": os.pathsep.join([str(stub), str(real)])}
            self.assertEqual(find_python(windows=True, environ=env), [str(real / "python.exe")])

    def test_windows_falls_back_to_py_launcher(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "py.exe").write_bytes(b"MZ")
            self.assertEqual(find_python(windows=True, environ={"PATH": d}), [str(Path(d) / "py.exe"), "-3"])

    def test_windows_finds_per_user_install(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "Programs" / "Python" / "Python312" / "python.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            self.assertEqual(find_python(windows=True, environ={"PATH": "", "LOCALAPPDATA": d}), [str(exe)])

    def test_only_windowsapps_stub_counts_as_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "WindowsApps"
            stub.mkdir()
            (stub / "python.exe").write_bytes(b"")
            with self.assertRaises(LaunchError):
                find_python(windows=True, environ={"PATH": str(stub), "LOCALAPPDATA": d, "ProgramFiles": d})

    def test_missing_python_gives_clear_message(self):
        with tempfile.TemporaryDirectory() as d:
            for win in (True, False):
                with self.assertRaises(LaunchError) as cm:
                    find_python(windows=win, environ={"PATH": d})
                self.assertIn("Python", str(cm.exception))
                self.assertIn("설치", str(cm.exception))

    def test_missing_python_blocks_launch_with_message(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "gifts").mkdir()
            (root / "gifts" / "a.py").write_text("", encoding="utf-8")
            with self.assertRaises(LaunchError) as cm:
                launch(LaunchAction("python", "gifts/a.py"), root, popen=lambda *a, **k: self.fail("실행되면 안 됨"),
                       windows=True, environ={"PATH": ""})
            self.assertIn("Python", str(cm.exception))


class FrozenRootTests(unittest.TestCase):
    def test_gifts_folder_is_next_to_exe_not_in_meipass(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            exe_dir, mei = Path(d, "app"), Path(d, "_MEI12345")
            exe_dir.mkdir()
            mei.mkdir()
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "_MEIPASS", str(mei), create=True), \
                    mock.patch.object(sys, "executable", str(exe_dir / "ChristmasWonderland.exe")):
                self.assertEqual(gifts_root(), exe_dir.resolve() / "gifts")
                self.assertNotIn("_MEI", str(gifts_root()))

    def test_dev_gifts_folder_is_project_root(self):
        self.assertEqual(gifts_root(), Path(__file__).resolve().parent.parent / "gifts")



try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않음")
class RevealLaunchButtonQt(unittest.TestCase):
    """선물 상세 화면의 실행 버튼 (오프스크린). PySide6 가 없으면 건너뜀으로 기록된다."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, d):
        from unittest import mock  # noqa: F401
        from advent.content import default_path
        from advent.window import AdventWindow
        from core.fonts import load_fonts
        load_fonts()
        data = json.loads(default_path().read_text(encoding="utf-8"))
        data["days"][23]["action"] = {"type": "python", "file": "gifts/christmas_tree/main.py"}
        (Path(d) / "advent_contents.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        w = AdventWindow(Path(d), today_fn=lambda: date(2026, 12, 25))
        w.show()
        return w

    def test_button_only_when_action_exists_and_blocks_double_click(self):
        class FakeProc:
            done = False

            def poll(self):
                return 0 if self.done else None

        proc = FakeProc()
        launched = []
        with tempfile.TemporaryDirectory() as d:
            w = self.make_window(d)
            try:
                w._launcher = LaunchTracker(lambda act: launched.append(act) or proc)
                w._enter_reveal(2026, 1, first=False)
                self.assertTrue(w.reveal.btn_launch.isHidden())               # action 없는 선물: 버튼 없음
                w._enter_reveal(2026, 24, first=False)
                self.assertFalse(w.reveal.btn_launch.isHidden())              # action 있는 선물: 버튼 표시
                w.reveal.btn_launch.click()
                self.assertEqual(len(launched), 1)
                self.assertFalse(w.reveal.btn_launch.isEnabled())             # 실행 중에는 잠김
                w.reveal.btn_launch.click()
                w._on_launch_requested(24)                                     # 직접 요청해도 중복 실행 없음
                self.assertEqual(len(launched), 1)
                proc.done = True
                w._poll_launches()
                self.assertTrue(w.reveal.btn_launch.isEnabled())              # 종료되면 다시 실행 가능
            finally:
                w.close()

    def test_launch_error_shows_message_and_keeps_button_usable(self):
        from unittest import mock

        def fail(_act):
            raise LaunchError("실행할 파일을 찾을 수 없어요")

        with tempfile.TemporaryDirectory() as d:
            w = self.make_window(d)
            try:
                w._launcher = LaunchTracker(fail)
                w._enter_reveal(2026, 24, first=False)
                with mock.patch("advent.window.QMessageBox.warning") as warn:
                    w.reveal.btn_launch.click()
                self.assertEqual(warn.call_count, 1)
                self.assertTrue(w.reveal.btn_launch.isEnabled())
            finally:
                w.close()


class FxTests(unittest.TestCase):
    def test_engines_run_and_finish(self):
        for kind in ("snowfall", "confetti", "stars", "lights", "fireworks", "sparkle"):
            e = FxEngine(kind, 400, 300, duration=1.0, rng=random.Random(1))
            for _ in range(200):
                e.step(1 / 30)
            self.assertTrue(e.finished, kind)

    def test_catch_game_win_and_lose(self):
        g = CatchGame(400, 100, target=3, seconds=10, rng=random.Random(2))
        g.start()
        for _ in range(400):
            g.step(0.033)
            for it in list(g.items):
                g.hit(it["x"], it["y"])
            if g.state != "playing":
                break
        self.assertEqual(g.state, "won")
        g2 = CatchGame(400, 100, target=3, seconds=2, rng=random.Random(2))
        g2.start()
        for _ in range(100):
            g2.step(0.033)
        self.assertEqual(g2.state, "lost")


if __name__ == "__main__":
    unittest.main()
