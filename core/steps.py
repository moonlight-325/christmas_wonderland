"""단계 실행 도우미 (Qt 무관): 한 단계가 예외를 내도 나머지 단계를 계속 실행한다."""
from __future__ import annotations

from typing import Callable, Iterable


def run_steps(steps: Iterable[tuple[str, Callable[[], object]]], log=None) -> list[str]:
    """(이름, 함수) 목록을 순서대로 실행하고, 실패한 단계 이름 목록을 돌려준다."""
    failed: list[str] = []
    for name, fn in steps:
        try:
            fn()
        except Exception:
            failed.append(name)
            if log is not None:
                log.exception("종료 단계 '%s' 실패 - 다음 단계를 계속합니다", name)
    return failed
