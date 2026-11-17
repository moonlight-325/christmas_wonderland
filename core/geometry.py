"""화면 좌표 보정 (Qt 없이 테스트 가능한 순수 함수 + Qt 화면 목록 래퍼).

저장된 창 위치가 현재 모니터 구성과 맞지 않을 때(모니터 제거, 해상도/배율 변경) 창이 화면 밖에 남지 않게 한다.
"""
from __future__ import annotations
from core.i18n import tr


MIN_VISIBLE = 48          # 창이 어떤 화면과든 이만큼(px)은 겹쳐야 '보이는' 것으로 본다


def clamp_into_screens(x: int, y: int, w: int, h: int, screens: list, min_visible: int = MIN_VISIBLE):
    """(x, y, w, h) 창이 screens [(l, t, r, b), ...] 중 하나와 충분히 겹치면 그대로, 아니면 가장 가까운 화면 안으로 옮긴 (x, y).

    r, b 는 포함하지 않는 끝 좌표(너비 = r - l). 화면 목록이 비어 있으면 원래 좌표를 돌려준다.
    """
    if not screens:
        return x, y
    mvw, mvh = min(min_visible, w), min(min_visible, h)
    for (l, t, r, b) in screens:
        if min(x + w, r) - max(x, l) >= mvw and min(y + h, b) - max(y, t) >= mvh:
            return x, y
    cx, cy = x + w / 2.0, y + h / 2.0

    def dist(s):
        l, t, r, b = s
        dx = max(l - cx, 0.0, cx - r)
        dy = max(t - cy, 0.0, cy - b)
        return dx * dx + dy * dy
    l, t, r, b = min(screens, key=dist)
    nx = max(l, min(x, r - w)) if w <= r - l else l
    ny = max(t, min(y, b - h)) if h <= b - t else t
    return int(nx), int(ny)


def available_screens() -> list:
    from PySide6.QtGui import QGuiApplication
    out = []
    for sc in QGuiApplication.screens():
        g = sc.availableGeometry()
        out.append((g.left(), g.top(), g.left() + g.width(), g.top() + g.height()))
    return out


def clamp_pos(x: int, y: int, w: int, h: int):
    """현재 모니터 구성 기준으로 보정한 (x, y)."""
    return clamp_into_screens(int(x), int(y), int(w), int(h), available_screens())


# ---- 이동/크기 조절 중 표시 문구 (장식, 시계)
def position_text(x: int, y: int) -> str:
    return tr("위치 {0}, {1}").format(int(x), int(y))


def scale_text(scale: int, w: int, h: int) -> str:
    return tr("크기 {0}배 ({1}×{2}px)").format(int(scale), int(w), int(h))
