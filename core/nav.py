"""목록형 컨트롤(세로 탭 등)의 키보드 이동 계산 (Qt 와 무관, 단독 테스트 가능)."""
from __future__ import annotations


def nav_target(cur: int, n: int, action: str) -> int | None:
    """action: next | prev | first | last. 이동할 번호를 돌려준다.

    끝에서는 반대쪽으로 돌아가지 않고 멈춘다 (설정 탭처럼 순서가 있는 목록에서 길을 잃지 않도록).
    항목이 없거나 알 수 없는 action 이면 None.
    """
    if n <= 0:
        return None
    cur = max(0, min(n - 1, cur))
    if action == "next":
        return min(n - 1, cur + 1)
    if action == "prev":
        return max(0, cur - 1)
    if action == "first":
        return 0
    if action == "last":
        return n - 1
    return None
