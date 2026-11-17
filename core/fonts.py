"""픽셀 폰트(Galmuri, SIL OFL 1.1) 로딩. 폰트 파일은 assets/fonts 에 포함되어 다른 PC에서도 동일하게 표시된다.

Galmuri11 = 11px 비트맵 격자, Galmuri14 = 14px 격자. 정수 배(×1, ×2 ...) 크기로만 사용하면 픽셀이 깨지지 않는다.
"""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

from .logger import get_logger
from .paths import resource_path

log = get_logger("fonts")

_FAMILY: dict[str, str] = {}
FALLBACK = "Malgun Gothic"


def load_fonts() -> bool:
    ok = True
    for name in ("Galmuri11", "Galmuri14"):
        path = resource_path("assets", "fonts", f"{name}.ttf")
        fid = QFontDatabase.addApplicationFont(str(path)) if path.exists() else -1
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            _FAMILY[name] = fams[0]
        else:
            ok = False
            log.warning("픽셀 폰트 로드 실패: %s (%s) -> 대체 폰트 사용", name, path)
    return ok


def pixel_font(grid: int = 11, scale: int = 1) -> QFont:
    """grid: 11 또는 14 (폰트 격자), scale: 정수 배율."""
    fam = _FAMILY.get(f"Galmuri{grid}", FALLBACK)
    f = QFont(fam)
    f.setPixelSize(grid * max(1, int(scale)))
    f.setStyleStrategy(QFont.StyleStrategy.NoAntialias)   # 픽셀 경계가 흐려지지 않도록
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    f.setKerning(False)
    return f
