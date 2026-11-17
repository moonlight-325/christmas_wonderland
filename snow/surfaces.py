"""창/작업표시줄 목록 -> 눈이 쌓일 표면(SurfaceInfo) 계산 (순수 Python, 테스트 가능).

windows: Z-order 위->아래 순서의 WinEntry 리스트.
가려진 구간: 위에 있는 창이 해당 상단 y 를 덮으면 그 x 구간은 보이지 않는 것으로 처리한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .physics import SurfaceInfo

MIN_W, MIN_H = 140, 60
OCC_REACH = 160        # 더미가 솟을 수 있는 높이(px) - 이 범위에 걸치는 위쪽 창은 가림 대상
TOP_MARGIN = 24        # 모니터 맨 위에 붙은(최대화) 창에는 쌓지 않는다


@dataclass
class WinEntry:
    key: object
    left: int
    top: int
    right: int
    bottom: int
    surface: bool = True      # False: 가리기만 하고 눈은 쌓지 않음
    taskbar: bool = False
    own: bool = False         # 우리 프로그램 창


def _subtract(segs: list, a: float, b: float) -> list:
    out = []
    for s, e in segs:
        if b <= s or a >= e:
            out.append((s, e))
            continue
        if a > s:
            out.append((s, a))
        if b < e:
            out.append((b, e))
    return out


def _floor_for(w, monitors: list, floors) -> float | None:
    """창의 가운데가 속한 모니터의 바닥(작업표시줄 윗선) y. 모르면 None."""
    if not floors or len(floors) != len(monitors):
        return None
    cx = (w.left + w.right) / 2
    for (ml, mt, mr, mb), fl in zip(monitors, floors):
        if ml <= cx < mr:
            return fl
    return None


def subtract_rects(rects: list, cut: tuple) -> list:
    """사각형 목록에서 cut 사각형이 덮는 부분을 뺀다 (l, t, r, b)."""
    cl, ct, cr, cb = cut
    out = []
    for (l, t, r, b) in rects:
        if cr <= l or cl >= r or cb <= t or ct >= b:
            out.append((l, t, r, b))
            continue
        if ct > t:
            out.append((l, t, r, ct))
        if cb < b:
            out.append((l, cb, r, b))
        mt, mb = max(t, ct), min(b, cb)
        if cl > l:
            out.append((l, mt, cl, mb))
        if cr < r:
            out.append((cr, mt, r, mb))
    return out


def visible_decor_rects(rect: tuple, occluders: list) -> list:
    """장식 창 하나(rect)에서, 그 위에 있는 다른 창(occluders)에 가려지지 않은 부분만 사각형 목록으로 돌려준다."""
    parts = [tuple(rect)]
    for o in occluders:
        if not parts:
            break
        parts = subtract_rects(parts, o)
    return [q for q in parts if q[2] > q[0] and q[3] > q[1]]


def compute_surfaces(entries: list, monitors: list, floors=None) -> list:
    """monitors: [(l, t, r, b), ...] 물리 픽셀. floors: 모니터별 바닥 y (작업표시줄 윗선).

    floors 가 있으면 작업표시줄 윗선 아래에 윗면이 있는 일반 창에는 눈을 쌓지 않는다 (작업표시줄 밑에 눈이 쌓이는 것을 막는다).
    """
    infos = []
    for idx, w in enumerate(entries):
        if not w.surface:
            continue
        if (w.right - w.left) < MIN_W or (w.bottom - w.top) < (20 if w.taskbar else MIN_H):
            continue
        y = w.top
        fl = _floor_for(w, monitors, floors)
        if fl is not None:
            if not w.taskbar and y >= fl - 2:
                continue            # 작업표시줄 윗선 아래에는 눈이 쌓이지 않는다
            if w.taskbar and abs(y - fl) <= 4:
                continue            # 아래쪽 작업표시줄의 윗면은 바닥 눈더미가 이미 담당한다 (같은 자리에 눈더미 두 개 -> 다른 창 Z-order 에 따라 깜빡이던 원인)
        segs = []
        ok = False
        for (ml, mt, mr, mb) in monitors:
            if mt + (0 if w.taskbar else TOP_MARGIN) <= y < mb - 2:
                a, b = max(w.left, ml), min(w.right, mr)
                if b > a:
                    segs.append((a, b))
                    ok = True
        if not ok:
            continue
        draw_segs = list(segs)
        occ = []
        for above in entries[:idx]:
            if above.right > w.left and above.left < w.right and above.bottom > y - OCC_REACH and above.top < y + 4:
                occ.append((above.left, above.top, above.right, above.bottom))
            if segs and above.top <= y < above.bottom:
                segs = _subtract(segs, above.left, above.right)
        infos.append(SurfaceInfo(w.key, float(w.left), float(y), float(w.right), segs, draw_segs, occ))
    return infos
