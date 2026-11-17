"""선물 외부 프로그램 실행기.  Qt 무관.

JSON 의 ``action`` 속성으로 지정한 프로그램을 Christmas Wonderland 와 독립된 프로세스로 실행한다.

    "action": {"type": "python",     "file": "gifts/christmas_tree/main.py"}
    "action": {"type": "executable", "file": "gifts/christmas_tree/christmas_tree.exe"}

규칙
- 경로는 Christmas Wonderland 실행 파일이 있는 폴더(app_root, PyInstaller 의 _MEIPASS 가 아님) 기준 상대 경로.
- 실행 가능한 위치는 그 폴더의 ``gifts/`` 안으로만 제한한다.
  절대 경로·드라이브·UNC·``..`` 는 거부하고, 심볼릭 링크/정션으로 gifts 밖을 가리키는 경우도 거부한다.
- 실행 유형은 python(.py) / executable(.exe) 두 가지뿐이다. 그 외 유형·확장자는 거부한다.
- 실행은 Popen 으로 시작만 하고 기다리지 않는다. 대기하는 코드는 없다.
"""
from __future__ import annotations
from core.i18n import tr


import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.logger import get_logger
from core.paths import app_root

log = get_logger("advent.launcher")

GIFTS_DIR = "gifts"
TYPE_PYTHON = "python"
TYPE_EXECUTABLE = "executable"
ACTION_TYPES = (TYPE_PYTHON, TYPE_EXECUTABLE)
_EXTENSIONS = {TYPE_PYTHON: (".py",), TYPE_EXECUTABLE: (".exe",)}
_MAX_PATH_TEXT = 500
_BAD_CHARS = re.compile(r'[\x00-\x1f<>:"|?*]')       # ':' 는 드라이브 문자·NTFS 대체 스트림 차단용
_SPLIT = re.compile(r"[\\/]+")


class LaunchError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 한국어 메시지를 담은 실행 오류."""


@dataclass(frozen=True)
class LaunchAction:
    type: str          # "python" | "executable"
    file: str          # JSON 에 적힌 상대 경로 (앱 폴더 기준)


# ---------------------------------------------------------------------- 검증 (파일 시스템 접근 없음)
def _clean_parts(file: str) -> list[str]:
    """경로 문자열을 검증하고 구성 요소 목록을 돌려준다. 문제가 있으면 LaunchError."""
    if not isinstance(file, str) or not file.strip():
        raise LaunchError(tr("action.file 에 실행할 파일 경로를 적어 주세요. (예: gifts/christmas_tree/main.py)"))
    text = file.strip()
    if len(text) > _MAX_PATH_TEXT:
        raise LaunchError(tr("action.file 경로가 너무 길어요."))
    if text.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", text):      # 루트 상대(/x), UNC(\\server\x), 드라이브(C:)
        raise LaunchError(tr("절대 경로는 사용할 수 없어요. gifts 폴더 기준 상대 경로로 적어 주세요: {0}").format(text))
    if _BAD_CHARS.search(text):
        raise LaunchError(tr("action.file 경로에 사용할 수 없는 문자가 있어요: {0}").format(text))
    parts = [p for p in _SPLIT.split(text) if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise LaunchError(tr("상위 폴더(..)는 사용할 수 없어요. gifts 폴더 안의 경로만 허용돼요: {0}").format(text))
    if not parts:
        raise LaunchError(tr("action.file 에 실행할 파일 경로를 적어 주세요. (예: gifts/christmas_tree/main.py)"))
    if any(p.endswith((" ", ".")) for p in parts):      # Windows 가 끝의 공백/점을 지워 다른 이름이 되는 것을 방지
        raise LaunchError(tr("파일·폴더 이름이 공백이나 점으로 끝날 수 없어요: {0}").format(text))
    return parts


def parse_action(raw) -> LaunchAction:
    """JSON 의 action 객체를 검증해 LaunchAction 으로 만든다. 잘못되면 LaunchError."""
    if not isinstance(raw, dict):
        raise LaunchError(tr("action 은 {\"type\": ..., \"file\": ...} 형태의 객체여야 해요."))
    t = raw.get("type")
    if t not in ACTION_TYPES:
        raise LaunchError(tr("지원하지 않는 실행 유형이에요: '{0}' ({1} 만 사용할 수 있어요)").format(t, ', '.join(ACTION_TYPES)))
    file = raw.get("file")
    parts = _clean_parts(file)
    if not parts[-1].lower().endswith(_EXTENSIONS[t]):
        raise LaunchError(tr("'{0}' 유형은 {1} 파일만 실행할 수 있어요: {2}").format(t, '/'.join(_EXTENSIONS[t]), file.strip()))
    if parts[0].lower() != GIFTS_DIR:
        raise LaunchError(tr("{0} 폴더 안의 파일만 실행할 수 있어요. (예: gifts/christmas_tree/main.py): {1}").format(GIFTS_DIR, file.strip()))
    return LaunchAction(t, "/".join(parts))


# ---------------------------------------------------------------------- 경로 해석 (파일 시스템 접근)
def gifts_root(root: Path | None = None) -> Path:
    """외부 선물을 둘 폴더. 실행 파일(또는 개발 시 프로젝트 루트) 옆의 gifts/."""
    return Path(root if root is not None else app_root()) / GIFTS_DIR


def resolve_target(action: LaunchAction, root: Path | None = None) -> Path:
    """action 이 가리키는 실제 파일 경로를 확인해 돌려준다. 범위 밖이거나 없으면 LaunchError."""
    action = parse_action({"type": action.type, "file": action.file})       # 직접 만든 객체도 다시 검증
    base = Path(root if root is not None else app_root())
    allowed = gifts_root(base).resolve()
    target = base.joinpath(*action.file.split("/")).resolve()                # 심볼릭 링크/정션을 따라간 실제 위치
    try:
        target.relative_to(allowed)
    except ValueError:
        raise LaunchError(tr("{0} 폴더 밖의 파일은 실행할 수 없어요: {1}").format(GIFTS_DIR, action.file)) from None
    if not target.is_file():
        raise LaunchError(tr("실행할 파일을 찾을 수 없어요:\n{0}\n프로그램 폴더의 {1} 안에 파일이 있는지 확인해 주세요.").format(action.file, GIFTS_DIR))
    return target


# ---------------------------------------------------------------------- Python 인터프리터 탐색
def _is_windows() -> bool:
    return os.name == "nt"


def _search_path(names, environ) -> Path | None:
    """PATH 를 직접 훑는다. Windows 의 WindowsApps 별칭(스토어 안내용 가짜 python.exe)은 건너뛴다."""
    for folder in str(environ.get("PATH", "")).split(os.pathsep):
        if not folder.strip() or Path(folder).name.lower() == "windowsapps":
            continue
        for name in names:
            cand = Path(folder) / name
            try:
                if cand.is_file():
                    return cand
            except OSError:
                pass
    return None


def _known_windows_pythons(environ) -> list[Path]:
    roots = []
    if environ.get("LOCALAPPDATA"):
        roots.append(Path(environ["LOCALAPPDATA"]) / "Programs" / "Python")
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        if environ.get(key):
            roots.append(Path(environ[key]))
    roots.append(Path("C:/"))
    found: list[Path] = []
    for r in roots:
        try:
            found += sorted(r.glob("Python3*/python.exe"), reverse=True)        # 새 버전 우선
        except OSError:
            pass
    return found


def find_python(*, windows: bool | None = None, environ=None) -> list[str]:
    """설치된 Python 을 실행하는 명령 접두부(예: ['C:\\...\\python.exe'] 또는 ['C:\\Windows\\py.exe', '-3']).

    프로그램이 PyInstaller 로 묶여 있으면 sys.executable 은 Christmas Wonderland 자신이므로 쓰지 않는다.
    """
    windows = _is_windows() if windows is None else windows
    env = os.environ if environ is None else environ
    if windows:
        hit = _search_path(("python.exe",), env)
        if hit:
            return [str(hit)]
        py = _search_path(("py.exe",), env)
        if py:
            return [str(py), "-3"]
        for cand in _known_windows_pythons(env):
            return [str(cand)]
    else:
        hit = _search_path(("python3", "python"), env)
        if hit:
            return [str(hit)]
    raise LaunchError(tr("Python 을 찾을 수 없어요.\n"
                      "Python 3 을 설치하고('Add python.exe to PATH' 선택) 다시 시도해 주세요. (python.org)"))


# ---------------------------------------------------------------------- 실행
def _popen_options(windows: bool) -> dict:
    """독립 프로세스 + 부모를 기다리지 않는 설정."""
    opts: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                  "close_fds": True}
    if windows:
        opts["creationflags"] = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                                 | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    else:
        opts["start_new_session"] = True
    return opts


def launch(action: LaunchAction, root: Path | None = None, *, popen=subprocess.Popen,
           windows: bool | None = None, environ=None):
    """프로그램을 시작하고 바로 Popen 을 돌려준다(종료를 기다리지 않음). 실패하면 LaunchError."""
    windows = _is_windows() if windows is None else windows
    target = resolve_target(action, root)
    if action.type == TYPE_PYTHON:
        cmd = find_python(windows=windows, environ=environ) + [str(target)]
    else:
        if not windows:
            raise LaunchError(tr(".exe 프로그램은 Windows 에서만 실행할 수 있어요."))
        cmd = [str(target)]
    try:
        proc = popen(cmd, cwd=str(target.parent), **_popen_options(windows))
    except PermissionError:
        raise LaunchError(tr("실행 권한이 없어요(보안 프로그램이 막았을 수 있어요):\n{0}").format(action.file)) from None
    except OSError as exc:
        raise LaunchError(tr("프로그램을 실행하지 못했어요:\n{0}\n({1})").format(action.file, exc)) from None
    log.info("선물 프로그램 실행: %s (pid %s)", action.file, getattr(proc, "pid", "?"))
    return proc


class LaunchTracker:
    """실행한 프로그램을 키(날짜)별로 기억해 같은 선물을 중복 실행하지 않게 한다. Qt 무관."""

    def __init__(self, launch_fn=launch):
        self._launch = launch_fn
        self._procs: dict = {}

    def is_running(self, key) -> bool:
        proc = self._procs.get(key)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        del self._procs[key]
        return False

    def any_running(self) -> bool:
        return any([self.is_running(k) for k in list(self._procs)])

    def start(self, key, action: LaunchAction) -> bool:
        """시작했으면 True, 이미 실행 중이라 무시했으면 False. 실행 실패는 LaunchError."""
        if self.is_running(key):
            return False
        self._procs[key] = self._launch(action)
        return True
