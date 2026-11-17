"""다국어(한국어 / English) 지원.  Qt 무관(순수 파이썬).

사용법
    from core.i18n import tr
    tr("눈 효과 사용")                         # 한국어면 그대로, English 면 번역표의 영어
    tr("강설량 {0}개").format(n)               # 값이 들어가는 문구는 {0} {1} 자리표시자 + .format()

원리
- 소스 코드의 문구는 한국어 원문이 곧 키입니다. 한국어 모드에서는 원문을 그대로 돌려줍니다.
- English 모드에서는 assets/lang/en.json (키 = 한국어 원문, 값 = 영어) 에서 찾고, 없으면 원문을 돌려줍니다.
- 언어는 프로그램 시작 시 한 번만 정해집니다(설정의 app.language). 바꾸면 다시 시작해야 적용됩니다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_LANGUAGE = "ko"
LANGUAGES = {"ko": "한국어", "en": "English"}     # 코드 -> 자기 언어로 쓴 이름(언어 선택 칸에 그대로 표시)

_lang = DEFAULT_LANGUAGE
_table: dict[str, str] = {}
_loaded_for: str | None = None


def _lang_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "lang"


def normalize(code) -> str:
    """알 수 없는 값은 기본 언어로."""
    code = str(code or "").strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def load_table(code: str, directory: Path | None = None) -> dict[str, str]:
    """언어 파일을 읽어 사전으로 돌려준다. 파일이 없거나 깨졌으면 빈 사전(= 원문 그대로 표시)."""
    path = (directory or _lang_dir()) / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v != ""}


def set_language(code, directory: Path | None = None) -> str:
    global _lang, _table, _loaded_for
    _lang = normalize(code)
    _table = {} if _lang == DEFAULT_LANGUAGE else load_table(_lang, directory)
    _loaded_for = _lang
    return _lang


def get_language() -> str:
    return _lang


def tr(text: str, ctx: str = "") -> str:
    """한국어 원문 -> 현재 언어의 문구. 번역이 없으면 원문.

    같은 한글이 자리에 따라 뜻이 다르면 ctx 를 붙인다: tr("눈", "eyes") -> 번역표 키 "eyes|눈" 을 먼저 찾고,
    없으면 일반 키 "눈" 으로 돌아간다.
    """
    if _lang == DEFAULT_LANGUAGE:
        return text
    if ctx:
        hit = _table.get(f"{ctx}|{text}")
        if hit is not None:
            return hit
    return _table.get(text, text)


def init_from_settings_file(data_dir: Path) -> str:
    """Qt 와 설정 관리자를 만들기 전에, settings.json 의 app.language 만 먼저 읽어 언어를 정한다.

    파일이 없거나 깨졌으면 한국어. (설정 파일 자체의 복구는 SettingsStore 가 따로 처리한다.)
    """
    code = DEFAULT_LANGUAGE
    try:
        data = json.loads((Path(data_dir) / "settings.json").read_text(encoding="utf-8"))
        code = data.get("app", {}).get("language", DEFAULT_LANGUAGE)
    except (OSError, ValueError, AttributeError):
        pass
    return set_language(code)


def weekday_names() -> list[str]:
    """월~일 (한국어: 월 화 수 ... / English: Mon Tue ...)."""
    if _lang == "en":
        return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return ["월", "화", "수", "목", "금", "토", "일"]


def weekday_full_names() -> list[str]:
    if _lang == "en":
        return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
