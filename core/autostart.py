"""Windows 로그인 시 앱 자동 실행 설정."""
from __future__ import annotations
from core.i18n import tr


import os
import sys
from pathlib import Path

from .paths import APP_NAME, app_root

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return f'"{executable}"'
    # python 콘솔 창이 뜨지 않도록 pythonw가 있으면 사용한다.
    if os.name == "nt" and executable.name.lower() == "python.exe":
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            executable = candidate
    script = app_root() / "main.py"
    return f'"{executable}" "{script}"'


def is_enabled() -> bool:
    """현재 사용자(HKCU)의 Windows 시작 프로그램 등록 여부."""
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, APP_NAME)
        return str(value) == _command()
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool) -> None:
    """현재 사용자 로그인 시작 항목을 등록하거나 제거한다."""
    if os.name != "nt":
        raise OSError(tr("Windows에서만 자동 실행을 설정할 수 있습니다."))
    import winreg
    access = winreg.KEY_SET_VALUE
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
