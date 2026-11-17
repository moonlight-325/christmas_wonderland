from __future__ import annotations
from core.i18n import tr, weekday_full_names, weekday_names


from datetime import date

WEEKDAYS_KO = weekday_names()          # 이름은 그대로, 내용은 현재 언어(한국어: 월 화 ... / English: Mon Tue ...)


def next_christmas(today: date | None = None) -> date:
    today = today or date.today()
    xmas = date(today.year, 12, 25)
    return xmas if today <= xmas else date(today.year + 1, 12, 25)


def days_until_christmas(today: date | None = None) -> int:
    today = today or date.today()
    return (next_christmas(today) - today).days


def dday_text(today: date | None = None) -> str:
    n = days_until_christmas(today)
    return "D-DAY" if n == 0 else f"D-{n}"


def date_text(d: date | None = None) -> str:
    d = d or date.today()
    return tr("{0}년 {1}월 {2}일 {3}").format(d.year, d.month, d.day, weekday_full_names()[d.weekday()])
