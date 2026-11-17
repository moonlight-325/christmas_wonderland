"""경로 헬퍼: 개발 환경과 PyInstaller 배포 환경을 모두 지원한다."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ChristmasWonderland"


def app_root() -> Path:
    """실행 파일(배포) 또는 프로젝트 루트(개발) 경로."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """읽기 전용 리소스(assets 등). PyInstaller 의 _MEIPASS 를 우선 사용."""
    base = Path(getattr(sys, "_MEIPASS", app_root()))
    return base.joinpath(*parts)


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


_DATA_DIR: Path | None = None


def data_dir() -> Path:
    """설정·로그·백업 저장 폴더. 쓰기 불가 시 %APPDATA% 로 대체."""
    global _DATA_DIR
    if _DATA_DIR is None:
        candidate = app_root() / "data"
        if not _writable(candidate):
            fallback = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME / "data"
            fallback.mkdir(parents=True, exist_ok=True)
            candidate = fallback
        _DATA_DIR = candidate
    return _DATA_DIR
