"""선물 콘텐츠 로더 (JSON).  Qt 무관.

파일 위치
- 기본본: assets/advent/contents.default.json   (배포물, 수정하지 않음)
- 사용자본: data/advent_contents.json           (처음 실행 시 기본본을 복사, 이 파일을 편집)
- 설정에서 다른 JSON 경로를 지정할 수도 있다.
이미지 경로는 JSON 이 있는 폴더 기준 -> 없으면 assets/advent/ 기준으로 찾는다.
어떤 오류가 있어도 항상 24개 선물을 돌려준다(누락/오류 항목은 대체 콘텐츠 + 경고).
"""
from __future__ import annotations
from core.i18n import get_language, tr


import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core.logger import get_logger
from core.paths import resource_path
from .launcher import LaunchAction, LaunchError, parse_action
from .logic import DAYS

log = get_logger("advent.content")

ANIMATIONS = ("snowfall", "confetti", "stars", "lights", "fireworks", "sparkle")
EVENT_TYPES = ("quiz", "wish", "catch")
CATCH_ITEMS = ("star", "snowflake", "candy", "bell", "gift")
USER_FILE = "advent_contents.json"


@dataclass
class Gift:
    day: int
    title: str
    message: str
    story: str
    image: Path | None
    animation: str
    event: dict | None
    action: LaunchAction | None = None        # 선택: 선물 상세 화면에서 실행할 외부 프로그램


@dataclass
class ContentSet:
    gifts: dict[int, Gift]
    source: Path
    warnings: list[str] = field(default_factory=list)
    title: str = "Advent Calendar"

    def get(self, day: int) -> Gift:
        return self.gifts[day]


def ko_default_path() -> Path:
    return resource_path("assets", "advent", "contents.default.json")


def default_path() -> Path:
    """현재 언어의 기본 콘텐츠. English 파일이 없으면 한국어 원본."""
    if get_language() == "en":
        en = resource_path("assets", "advent", "contents.default.en.json")
        if en.exists():
            return en
    return ko_default_path()


def ensure_user_copy(directory: Path) -> Path:
    dest = Path(directory) / USER_FILE
    if not dest.exists():
        try:
            shutil.copyfile(default_path(), dest)
        except OSError as exc:
            log.warning("사용자 콘텐츠 복사 실패: %s", exc)
    return dest


def _s(v, default="", limit=4000) -> str:
    return v.strip()[:limit] if isinstance(v, str) else default


def resolve_image(value, base_dir: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    p = Path(value.strip())
    candidates = [p] if p.is_absolute() else [base_dir / p, resource_path("assets", "advent") / p]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            pass
    return None


def _event(raw, day: int, warnings: list[str]):
    if raw in (None, "", "none"):
        return None
    if not isinstance(raw, dict):
        warnings.append(tr("{0}일: event 형식 오류(무시)").format(day))
        return None
    t = raw.get("type")
    if t == "none":
        return None
    if t not in EVENT_TYPES:
        warnings.append(tr("{0}일: 알 수 없는 event.type '{1}' (무시)").format(day, t))
        return None
    if t == "quiz":
        choices = raw.get("choices")
        if not (isinstance(choices, list) and 2 <= len(choices) <= 6 and all(isinstance(c, str) and c.strip() for c in choices)):
            warnings.append(tr("{0}일: quiz.choices 는 2~6개의 문자열이어야 함 (이벤트 무시)").format(day))
            return None
        ans = raw.get("answer")
        if not (isinstance(ans, int) and not isinstance(ans, bool) and 0 <= ans < len(choices)):
            warnings.append(tr("{0}일: quiz.answer 범위 오류 (이벤트 무시)").format(day))
            return None
        q = _s(raw.get("question"))
        if not q:
            warnings.append(tr("{0}일: quiz.question 없음 (이벤트 무시)").format(day))
            return None
        return {"type": "quiz", "question": q, "choices": [c.strip() for c in choices], "answer": ans,
                "success": _s(raw.get("success"), tr("정답이에요! 🎉")), "fail": _s(raw.get("fail"), tr("아쉬워요, 다음엔 맞힐 수 있을 거예요!"))}
    if t == "wish":
        return {"type": "wish", "prompt": _s(raw.get("prompt"), tr("올해의 소원을 적어 별에게 보내 보세요.")),
                "success": _s(raw.get("success"), tr("소원이 별에게 전해졌어요 ⭐"))}
    target = raw.get("target", 5)
    seconds = raw.get("seconds", 12)
    item = raw.get("item", "star")
    if not (isinstance(target, int) and not isinstance(target, bool)):
        target = 5
    if not (isinstance(seconds, (int, float)) and not isinstance(seconds, bool)):
        seconds = 12
    return {"type": "catch", "target": max(1, min(50, target)), "seconds": int(max(5, min(60, seconds))),
            "item": item if item in CATCH_ITEMS else "star",
            "prompt": _s(raw.get("prompt"), tr("떨어지는 것을 클릭해서 잡아 보세요!")),
            "success": _s(raw.get("success"), tr("모두 잡았어요! ✨")), "fail": _s(raw.get("fail"), tr("조금 모자랐어요. 다시 도전해 보세요!"))}


def _action(raw, day: int, warnings: list[str]) -> LaunchAction | None:
    """action 은 선택 속성. 없으면 None, 잘못되면 경고만 남기고 무시한다(버튼 없음)."""
    if raw in (None, "", "none"):
        return None
    try:
        return parse_action(raw)
    except LaunchError as exc:
        warnings.append(tr("{0}일: action 무시 - {1}").format(day, str(exc).splitlines()[0]))
        return None


def _fallback(day: int) -> Gift:
    return Gift(day, tr("12월 {0}일의 선물").format(day), tr("메리 크리스마스! 오늘도 따뜻한 하루 보내세요."),
                tr("이 선물의 내용은 아직 준비되지 않았어요. advent_contents.json 에서 직접 채워 보세요."),
                None, "snowfall", None)


def parse(data, base_dir: Path, source: Path) -> ContentSet:
    warnings: list[str] = []
    items = data.get("days") if isinstance(data, dict) else data
    title = _s(data.get("title"), "Advent Calendar", 80) if isinstance(data, dict) else "Advent Calendar"
    if not isinstance(items, list):
        warnings.append(tr("최상위에 'days' 배열이 없습니다. 기본 콘텐츠로 대체합니다."))
        items = []
    gifts: dict[int, Gift] = {}
    for raw in items:
        if not isinstance(raw, dict):
            warnings.append(tr("days 항목이 객체가 아님(무시)"))
            continue
        d = raw.get("day")
        if not (isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= DAYS):
            warnings.append(tr("잘못된 day 값 '{0}' (1~24만 허용, 무시)").format(d))
            continue
        if d in gifts:
            warnings.append(tr("{0}일이 중복되어 첫 항목만 사용").format(d))
            continue
        anim = raw.get("animation", "snowfall")
        if anim not in ANIMATIONS:
            warnings.append(tr("{0}일: 알 수 없는 animation '{1}' → snowfall").format(d, anim))
            anim = "snowfall"
        img_val = raw.get("image")
        img = resolve_image(img_val, base_dir)
        if img_val and img is None:
            warnings.append(tr("{0}일: 이미지를 찾을 수 없음 '{1}'").format(d, img_val))
        fb = _fallback(d)
        gifts[d] = Gift(d, _s(raw.get("title"), fb.title, 80), _s(raw.get("message"), fb.message, 500),
                        _s(raw.get("story"), fb.story, 3000), img, anim, _event(raw.get("event"), d, warnings),
                        _action(raw.get("action"), d, warnings))
    for d in range(1, DAYS + 1):
        if d not in gifts:
            warnings.append(tr("{0}일 콘텐츠 누락 → 대체 콘텐츠 사용").format(d))
            gifts[d] = _fallback(d)
    return ContentSet(gifts, source, warnings, title)


def load_file(path: Path) -> ContentSet | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("콘텐츠 JSON 읽기 실패 %s: %s", path, exc)
        return None
    return parse(data, path.parent, path)


def _is_untouched_ko_copy(user: Path) -> bool:
    if get_language() != "en":
        return False
    try:
        return user.read_bytes() == ko_default_path().read_bytes()
    except OSError:
        return False


def load_contents(directory: Path, custom_path: str = "") -> ContentSet:
    """custom_path -> data/advent_contents.json -> 기본본 순으로 시도."""
    notes: list[str] = []
    candidates: list[Path] = []
    if custom_path:
        candidates.append(Path(custom_path))
    user = ensure_user_copy(directory)
    if not _is_untouched_ko_copy(user):          # 한국어 기본본을 그대로 복사해 둔 파일이면 English 모드에서는 쓰지 않는다
        candidates.append(user)
    candidates.append(default_path())
    for i, c in enumerate(candidates):
        cs = load_file(c) if c.exists() else None
        if cs is not None:
            cs.warnings = notes + cs.warnings
            return cs
        notes.append(tr("콘텐츠 파일을 읽을 수 없어 다음 파일로 대체: {0}").format(c))
    cs = parse({"days": []}, default_path().parent, default_path())
    cs.warnings = notes + cs.warnings
    return cs
