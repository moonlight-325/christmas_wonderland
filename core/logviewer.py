"""실시간 로그 보기: 새 콘솔 창에서 data/app.log 를 계속 읽어 보여 준다.  Qt 무관.

- 앱은 콘솔이 없는 창 모드 프로그램이므로, 로그 창은 앱과 완전히 별개의 프로세스(별도 콘솔)로 띄운다.
  그래서 이 콘솔 창을 닫아도 Christmas Wonderland 는 종료되지 않는다(앱 쪽에는 이 창에 연결된 것이 없다).
- 로그 파일은 읽기 전용으로 잠깐씩만 열고(삭제 공유 허용) 바로 닫으므로, 로그 회전(app.log -> app.log.1)을 막지 않는다.
- PowerShell 을 -EncodedCommand 로 실행해 따옴표/실행 정책 문제를 피한다. Windows 전용.
"""
from __future__ import annotations
from core.i18n import tr


import base64
import os
import subprocess
from pathlib import Path

from .logger import get_logger
from .paths import data_dir

log = get_logger("app")

CREATE_NEW_CONSOLE = 0x00000010
_TAIL_BYTES = 8192            # 창을 열 때 먼저 보여 줄 최근 로그 분량


class LogViewerError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 메시지."""


def log_file() -> Path:
    return data_dir() / "app.log"


def build_script(path: Path) -> str:
    """로그 파일을 0.5초마다 확인해 새로 늘어난 줄만 출력하는 PowerShell 스크립트."""
    lit = str(path).replace("'", "''")                     # PowerShell 작은따옴표 문자열 이스케이프
    return ("$ErrorActionPreference = 'SilentlyContinue'\n[Console]::OutputEncoding = [Text.Encoding]::UTF8\n$p = '{0}'\n$Host.UI.RawUI.WindowTitle = 'Christmas Wonderland - Live Log'\nWrite-Host \"Log file: $p\"\nWrite-Host 'Closing this window will not exit Christmas Wonderland. (Press Ctrl+C to stop)'\nWrite-Host ''\n$pos = 0\n$first = $true\nif (Test-Path -LiteralPath $p) {{ $pos = [Math]::Max(0, (Get-Item -LiteralPath $p).Length - {1}) }}\nwhile ($true) {{\n  try {{\n    $fs = [IO.File]::Open($p, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite,Delete')\n    try {{\n      if ($fs.Length -lt $pos) {{ $pos = 0 }}\n      if ($fs.Length -gt $pos) {{\n        $null = $fs.Seek($pos, 'Begin')\n        $buf = New-Object byte[] ($fs.Length - $pos)\n        $n = $fs.Read($buf, 0, $buf.Length)\n        $last = if ($n -gt 0) {{ [Array]::LastIndexOf($buf, [byte]10, $n - 1) }} else {{ -1 }}\n        if ($last -ge 0) {{\n          $skip = 0\n          if ($first -and $pos -gt 0) {{ $skip = [Array]::IndexOf($buf, [byte]10) + 1 }}\n          if ($last + 1 -gt $skip) {{ [Console]::Out.Write([Text.Encoding]::UTF8.GetString($buf, $skip, $last + 1 - $skip)) }}\n          $pos += $last + 1\n        }}\n      }}\n      $first = $false\n    }} finally {{ $fs.Dispose() }}\n  }} catch {{ }}\n  Start-Sleep -Milliseconds 500\n}}\n").format(lit, _TAIL_BYTES)


def encode_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def open_log_console(path: Path | None = None, *, popen=subprocess.Popen, windows: bool | None = None):
    """새 콘솔 창에서 실시간 로그를 시작하고 Popen 을 돌려준다(기다리지 않음). 실패하면 LogViewerError."""
    windows = (os.name == "nt") if windows is None else windows
    if not windows:
        raise LogViewerError(tr("실시간 로그 창은 Windows 에서만 열 수 있어요."))
    target = Path(path) if path is not None else log_file()
    cmd = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-EncodedCommand", encode_command(build_script(target))]
    try:
        return popen(cmd, creationflags=CREATE_NEW_CONSOLE, close_fds=True,
                     stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise LogViewerError(tr("PowerShell 을 찾을 수 없어 로그 창을 열지 못했어요.\n로그 파일을 직접 열어 보세요:\n{0}").format(target)) from None
    except OSError as exc:
        raise LogViewerError(tr("로그 창을 열지 못했어요.\n({0})\n로그 파일: {1}").format(exc, target)) from None
