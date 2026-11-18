"""실시간 로그 보기: 새 콘솔 창에서 data/app.log 를 계속 읽어 보여 준다.  Qt 무관.

- 앱은 콘솔이 없는 창 모드 프로그램이므로, 로그 창은 앱과 완전히 별개의 프로세스(별도 콘솔)로 띄운다.
  그래서 이 콘솔 창을 닫아도 Christmas Wonderland 는 종료되지 않는다(앱 쪽에는 이 창에 연결된 것이 없다).
- 로그 파일은 읽기 전용으로 잠깐씩만 열고(삭제 공유 허용) 바로 닫으므로, 로그 회전(app.log -> app.log.1)을 막지 않는다.
- PowerShell 을 -EncodedCommand 로 실행해 따옴표/실행 정책 문제를 피한다. Windows 전용.
- Popen 에 stdin/stdout/stderr 를 넘기지 않는다: 하나라도 넘기면 STARTF_USESTDHANDLES 가 켜져서,
  창 모드 EXE(표준 핸들 없음)에서는 새 콘솔에 잘못된 핸들이 상속되어 출력이 안 보일 수 있다.
"""
from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

from core.i18n import tr

from .logger import get_logger
from .paths import data_dir

log = get_logger("app")

CREATE_NEW_CONSOLE = 0x00000010
_TAIL_BYTES = 8192            # 창을 열 때 먼저 보여 줄 최근 로그 분량


class LogViewerError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 메시지."""


def log_file() -> Path:
    return data_dir() / "app.log"


_SCRIPT_TEMPLATE = r"""
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$p = '__PATH__'
try { $Host.UI.RawUI.WindowTitle = 'Christmas Wonderland - Live Log' } catch { }
Write-Host "Log file: $p"
Write-Host 'Closing this window will not exit Christmas Wonderland. (Press Ctrl+C to stop)'
Write-Host ''
$pos = 0
$first = $true
$lastErr = ''
$waitShown = $false
try {
  if (Test-Path -LiteralPath $p) { $pos = [Math]::Max(0, (Get-Item -LiteralPath $p).Length - __TAIL__) }
} catch { Write-Host "[log viewer] $($_.Exception.Message)" -ForegroundColor Yellow }
while ($true) {
  try {
    if (-not (Test-Path -LiteralPath $p)) {
      if (-not $waitShown) { Write-Host '[log viewer] Waiting for the log file...' -ForegroundColor DarkGray; $waitShown = $true }
    } else {
      $fs = [IO.File]::Open($p, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite,Delete')
      try {
        if ($fs.Length -lt $pos) { $pos = 0 }
        if ($fs.Length -gt $pos) {
          $null = $fs.Seek($pos, 'Begin')
          $buf = New-Object byte[] ($fs.Length - $pos)
          $n = $fs.Read($buf, 0, $buf.Length)
          $last = if ($n -gt 0) { [Array]::LastIndexOf($buf, [byte]10, $n - 1) } else { -1 }
          if ($last -ge 0) {
            $skip = 0
            if ($first -and $pos -gt 0) { $skip = [Array]::IndexOf($buf, [byte]10) + 1 }
            if ($last + 1 -gt $skip) { [Console]::Out.Write([Text.Encoding]::UTF8.GetString($buf, $skip, $last + 1 - $skip)) }
            $pos += $last + 1
          }
        }
        $first = $false
        $lastErr = ''
      } finally { $fs.Dispose() }
    }
  } catch {
    $msg = $_.Exception.Message
    if ($msg -ne $lastErr) { Write-Host "[log viewer] $msg" -ForegroundColor Yellow; $lastErr = $msg }
  }
  Start-Sleep -Milliseconds 500
}
"""


def build_script(path: Path) -> str:
    """로그 파일을 0.5초마다 확인해 새로 늘어난 줄만 출력하는 PowerShell 스크립트."""
    lit = str(path).replace("'", "''")                     # PowerShell 작은따옴표 문자열 이스케이프
    return _SCRIPT_TEMPLATE.replace("__PATH__", lit).replace("__TAIL__", str(_TAIL_BYTES))


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
        # stdin/stdout/stderr 를 지정하지 않는다 (STARTF_USESTDHANDLES 방지). 새 콘솔이 자기 핸들을 쓴다.
        return popen(cmd, creationflags=CREATE_NEW_CONSOLE, close_fds=True)
    except FileNotFoundError:
        raise LogViewerError(tr("PowerShell 을 찾을 수 없어 로그 창을 열지 못했어요.\n로그 파일을 직접 열어 보세요:\n{0}").format(target)) from None
    except OSError as exc:
        raise LogViewerError(tr("로그 창을 열지 못했어요.\n({0})\n로그 파일: {1}").format(exc, target)) from None
