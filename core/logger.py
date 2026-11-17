from core.i18n import tr

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from .paths import data_dir

# 로거 이름 -> 콘솔에 보여 줄 짧은 한글 이름
_NAMES = {
    "app": "앱", "snow": "눈", "overlay": "눈", "zorder": "층", "lights": "전구", "decor": "장식",
    "snowglobe": "스노우볼", "snowman": "눈사람", "audio": "음악", "sfx": "효과음", "settings": "설정",
    "autoweather": "날씨", "advent": "어드벤트", "widget": "위젯", "tray": "트레이", "fonts": "폰트",
}
_LEVELS = {
    logging.DEBUG: ("DEBUG", "90"), logging.INFO: ("INFO ", "36"), logging.WARNING: ("WARN ", "33"),
    logging.ERROR: ("ERROR", "31"), logging.CRITICAL: ("FATAL", "1;31"),
}


def _enable_ansi() -> bool:
    """콘솔이 색 글자를 지원하는지 (터미널이고 Windows 에서는 가상 터미널 모드를 켤 수 있을 때만)."""
    try:
        if sys.stderr is None or not sys.stderr.isatty() or os.environ.get("NO_COLOR"):
            return False
        if os.name != "nt":
            return True
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-12)                      # STD_ERROR_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))     # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        return False


class PrettyFormatter(logging.Formatter):
    """콘솔용: `14:32:05  INFO   눈      메시지`. 여러 줄 메시지는 두 번째 줄부터 메시지 시작 위치에 맞춰 들여쓴다."""

    def __init__(self, color: bool):
        super().__init__(datefmt="%H:%M:%S")
        self.color = color

    def _paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def format(self, record: logging.LogRecord) -> str:
        tag, code = _LEVELS.get(record.levelno, (record.levelname[:5].ljust(5), "0"))
        short = record.name[3:] if record.name.startswith("cw.") else record.name
        name = _NAMES.get(short, _NAMES.get(short.split(".")[0], short))
        pad = " " * max(0, 8 - sum(2 if ord(c) > 0x2E7F else 1 for c in name))
        head = (f"{self._paint(self.formatTime(record, self.datefmt), '90')}  {self._paint(tag, code)}  "
                f"{self._paint(name, '35')}{pad}")
        indent = " " * (8 + 2 + 5 + 2 + 8 + 2)
        lines = record.getMessage().splitlines() or [""]
        body = ("\n" + indent).join(self._paint(ln, code) if record.levelno >= logging.WARNING else ln for ln in lines)
        out = f"{head}  {body}"
        if record.exc_info:
            trace = self.formatException(record.exc_info)
            out += "\n" + "\n".join(indent + ln for ln in trace.splitlines())
        return out


class _EnglishLogFilter(logging.Filter):
    """Translate log message templates when English is selected."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = tr(record.msg)
        return True


def setup_logging() -> logging.Logger:
    log = logging.getLogger("cw")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        fh = RotatingFileHandler(data_dir() / "app.log", maxBytes=512 * 1024,
                                 backupCount=2, encoding="utf-8")
        fh.setFormatter(file_fmt)
        fh.addFilter(_EnglishLogFilter())
        log.addHandler(fh)
    except OSError:
        pass
    if sys.stderr is not None:  # windowed(PyInstaller) 빌드에서는 None
        sh = logging.StreamHandler()
        sh.setFormatter(PrettyFormatter(_enable_ansi()))
        sh.addFilter(_EnglishLogFilter())
        log.addHandler(sh)
    return log


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger("cw." + name)
