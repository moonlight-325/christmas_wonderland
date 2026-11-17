"""'한 번 더 누르면 실행' 확인 상태 (Qt 와 무관, 단독 테스트 가능).

되돌릴 수 없는 삭제 버튼용. 첫 클릭은 '대기' 상태로 만들고, 같은 대상에 대해 제한 시간 안에 한 번 더 누르면 실행한다.
대기 중에 대상(선택한 눈사람/스노우볼)이 바뀌면 두 번째 클릭은 확인이 아니라 새 대상에 대한 첫 클릭이다
- 그래서 A 에서 대기시킨 뒤 B 를 골라 누르면 B 가 바로 지워지는 사고가 나지 않는다.
"""
from __future__ import annotations


class TwoStep:
    def __init__(self, window: float = 3.0):
        self.window = float(window)
        self._armed = False
        self._key = None
        self._t = 0.0

    def press(self, key, now: float) -> bool:
        """클릭 처리. 확인되어 실행해야 하면 True, 대기 상태가 되었으면 False."""
        if self.is_armed(key, now):
            self.reset()
            return True
        self._armed, self._key, self._t = True, key, float(now)
        return False

    def is_armed(self, key, now: float) -> bool:
        return self._armed and self._key == key and 0.0 <= now - self._t <= self.window

    def reset(self) -> None:
        self._armed, self._key = False, None
