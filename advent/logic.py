"""어드벤트 캘린더의 해금 판정 (Qt 무관, 순수 Python).

규칙
- 실제 모드: date(year, 12, day) <= 오늘 이면 해금.  (과거 연도는 전부 해금, 미래 연도는 전부 잠금)
- 이미 연 상자는 날짜와 무관하게 'opened' 유지.
"""
from __future__ import annotations
from core.i18n import tr


from dataclasses import dataclass, field
from datetime import date

DAYS = 24
LOCKED, AVAILABLE, OPENED = "locked", "available", "opened"


@dataclass
class ViewContext:
    year: int
    today: date                      # 판정에 쓰는 '오늘'
    opened: set[int] = field(default_factory=set)


def box_date(year: int, day: int) -> date:
    return date(year, 12, day)


def days_until(year: int, day: int, today: date) -> int:
    return (box_date(year, day) - today).days


def box_status(ctx: ViewContext, day: int) -> str:
    if not 1 <= day <= DAYS:
        raise ValueError(f"day out of range: {day}")
    if day in ctx.opened:
        return OPENED
    return AVAILABLE if box_date(ctx.year, day) <= ctx.today else LOCKED


def all_statuses(ctx: ViewContext) -> dict[int, str]:
    return {d: box_status(ctx, d) for d in range(1, DAYS + 1)}


def build_context(store, viewed_year: int, real_today: date) -> ViewContext:
    """저장소의 개봉 기록으로 현재 화면에 쓸 컨텍스트를 만든다."""
    return ViewContext(viewed_year, real_today, store.opened_days(viewed_year))


def default_view_year(real_today: date) -> int:
    return real_today.year


def unlock_message(ctx: ViewContext, day: int) -> str:
    n = days_until(ctx.year, day, ctx.today)
    if n <= 0:
        return tr("{0}년 12월 {1}일 선물").format(ctx.year, day)
    return tr("12월 {0}일에 열 수 있어요 (D-{1})").format(day, n)
