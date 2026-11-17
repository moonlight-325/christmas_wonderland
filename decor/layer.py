"""장식/전구/시계 창의 층(항상 위 / 일반 / 항상 아래) 공통 처리.

- 항상 위 층: top 눈 오버레이 > 항상 위 장식 창 순서를 유지한다 (장식 위에 눈이 보이도록).
- 작업표시줄: 순서로 해결하지 않는다. 눈 오버레이는 작업표시줄 윗선까지만 덮고, 장식 창은 그 선 아래를 창 모양에서 뺀다 (clip_to_taskbar).
Z-order 는 매 프레임 밀어 올리지 않고, 장식 창이 보여질 때 / 층이 바뀔 때 / 전경 창이 바뀔 때 / 화면 구성이 바뀔 때 / 느린 안전망(1초)에서만
확인한다 (이미 맞으면 SetWindowPos 를 부르지 않는다).
"""
from __future__ import annotations

import time
import weakref

from PySide6.QtCore import QCoreApplication, QRect, QTimer, Qt
from PySide6.QtGui import QRegion

from core.logger import get_logger
from snow import winapi

log = get_logger("zorder")

_DECOR = weakref.WeakSet()       # 눈이 항상 위에 덮여야 하는 장식 창들 (전구·장식·시계·스노우볼)

NET_INTERVAL_MS = 1000           # 안전망 점검 주기 (이벤트가 놓친 경우만 잡는다; 이미 맞으면 아무것도 하지 않음)
BURST_MS = (0, 40, 150, 400)     # 전경 창이 바뀐 뒤 셸이 Z-order 를 다 바꿀 때까지 몇 번 확인

_st = {"pending": None, "gen": 0, "net": None}


def decor_windows() -> list:
    """지금 화면에 보이는 장식 창 목록."""
    out = []
    for w in list(_DECOR):
        try:
            if w.isVisible():
                out.append(w)
        except RuntimeError:                  # 이미 삭제된 창
            pass
    return out


def topband_decor_hwnds() -> list:
    """'항상 위' 층에 있고 보이는 장식 창의 HWND (Z-order 관리 대상)."""
    out = []
    for w in list(_DECOR):
        try:
            if getattr(w, "_layer_key", ("",))[0] == "top" and w.isVisible():
                out.append(int(w.winId()))
        except RuntimeError:
            pass
    return out


winapi.set_decor_provider(topband_decor_hwnds)


# ---------------------------------------------------------------- 층 적용
def apply_layer(w, layer: str, click_through: bool = False) -> None:
    _DECOR.add(w)
    flags = Qt.FramelessWindowHint | Qt.Tool
    if layer == "top":
        flags |= Qt.WindowStaysOnTopHint
    elif layer == "bottom" and not winapi.IS_WINDOWS:
        flags |= Qt.WindowStaysOnBottomHint
    if click_through:
        flags |= Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
    key = (layer, click_through)
    if getattr(w, "_layer_key", None) == key:
        return
    w._layer_key = key
    geo = w.geometry()
    visible = w.isVisible()
    w.setWindowFlags(flags)
    w.setAttribute(Qt.WA_TranslucentBackground, True)
    w.setAttribute(Qt.WA_ShowWithoutActivating, True)
    w.setAttribute(Qt.WA_TransparentForMouseEvents, click_through)
    w.setGeometry(geo)
    timer = getattr(w, "_z_timer", None)
    if timer is None:
        timer = QTimer(w)
        timer.setInterval(500)
        timer.timeout.connect(lambda: _keep(w))
        w._z_timer = timer
    if layer == "bottom" and winapi.IS_WINDOWS:
        timer.start()
    else:
        timer.stop()
    if winapi.IS_WINDOWS:
        _ensure_net()
    if visible:
        w.show()
        _keep(w)


def _keep(w) -> None:
    layer = getattr(w, "_layer_key", ("",))[0]
    if layer == "bottom" and w.isVisible():
        winapi.keep_bottom(int(w.winId()))
    elif layer == "top" and w.isVisible():
        request_settle("decor-shown")


def show_layered(w) -> None:
    w.show()
    _keep(w)
    clip_to_taskbar(w)


class TopBandMixin:
    """항상 위 장식 창(전구·장식·시계)의 부모 클래스에 함께 넣는다 (QWidget 앞에).
    창이 클릭 활성화나 Qt 의 TOPMOST 재지정으로 눈 오버레이 앞까지 올라오려는 순간에 삽입 위치를 바로잡는다."""

    def nativeEvent(self, eventType, message):
        if winapi.IS_WINDOWS and getattr(self, "_layer_key", ("",))[0] == "top":
            try:
                if bytes(eventType) == b"windows_generic_MSG":
                    winapi.keep_decor_below_overlay(message)
            except Exception:
                pass
        return False, 0

    def moveEvent(self, e):
        super().moveEvent(e)
        if winapi.IS_WINDOWS:
            clip_to_taskbar(self)                 # 끌어서 작업표시줄 쪽으로 가져가도 작업표시줄을 덮지 않는다


# ---------------------------------------------------------------- 작업표시줄 가림 방지 (Z-order 와 별개로 눈에 보이는 결과를 보장)
# Z-order 만으로는 셸/다른 프로그램이 순서를 바꾸는 순간에 장식이 작업표시줄을 덮을 수 있다. 그래서 항상 위 장식 창은
# 작업표시줄과 겹치는 부분을 창 모양(mask)에서 아예 빼 둔다 -> 순서가 어떻게 되든 작업표시줄은 장식에 가려지지 않는다.
_TB_CACHE = {"t": 0.0, "rects": []}


def _bars(max_age: float = 0.25) -> list:
    now = time.monotonic()
    if now - _TB_CACHE["t"] > max_age:
        _TB_CACHE["t"] = now
        try:
            rects = [tuple(r) for r in winapi.taskbar_rects()]
            mons = list(winapi.get_monitors().values())
            for (ml, mt, mr, mb), fl in zip(mons, winapi.floors_for_rects(mons)):
                if mt + 200 < fl < mb:                 # 작업표시줄 윗선 아래는 전부 가린다 (창을 찾지 못해도 높이 기억값으로)
                    rects.append((ml, int(fl), mr, mb))
            _TB_CACHE["rects"] = rects
        except Exception:
            _TB_CACHE["rects"] = []
    return _TB_CACHE["rects"]


def clip_to_taskbar(w) -> None:
    """항상 위 장식 창 w 에서 작업표시줄과 겹치는 부분을 보이지/눌리지 않게 뺀다. 겹침이 같으면 아무것도 다시 하지 않는다."""
    try:
        if not winapi.IS_WINDOWS or not w.isVisible():
            return
        wr = winapi.window_rect(int(w.winId()))
        if wr is None or w.width() <= 0 or w.height() <= 0:
            return
        hits = []
        for (l, t, r, b) in _bars():
            if r > wr[0] and l < wr[2] and b > wr[1] and t < wr[3] and (r - l) >= 3 * (b - t) and (b - t) >= 8:
                hits.append((max(l, wr[0]), max(t, wr[1]), min(r, wr[2]), min(b, wr[3])))
        key = (tuple(wr), tuple(hits), w.width(), w.height())
        if getattr(w, "_tb_clip_key", None) == key:
            return
        w._tb_clip_key = key
        if not hits:
            if getattr(w, "_tb_clipped", False):
                w.clearMask()
                w._tb_clipped = False
            return
        sx = (wr[2] - wr[0]) / float(w.width())
        sy = (wr[3] - wr[1]) / float(w.height())
        region = QRegion(0, 0, w.width(), w.height())
        for (l, t, r, b) in hits:
            x0, y0 = int((l - wr[0]) / sx), int((t - wr[1]) / sy)
            x1, y1 = int(-(-(r - wr[0]) // sx)), int(-(-(b - wr[1]) // sy))
            region = region.subtracted(QRegion(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))))
        w.setMask(region)
        w._tb_clipped = True
    except Exception:
        log.exception("작업표시줄 가림 방지 오류")


def clip_all_to_taskbar() -> None:
    _TB_CACHE["t"] = 0.0                           # 이벤트(전경 창 변경 등) 직후에는 사각형을 새로 읽는다
    for w in decor_windows():
        clip_to_taskbar(w)                          # 층과 상관없이 선 아래로 넘은 부분은 보이지 않게


# ---------------------------------------------------------------- 항상 위 층 점검 (이벤트 / 안전망)
def request_settle(reason: str) -> None:
    """다음 이벤트 루프 턴에 항상 위 층 Z-order 를 한 번만 점검한다. 같은 턴의 여러 요청은 하나로 합쳐진다."""
    if not winapi.IS_WINDOWS:
        return
    pend = _st["pending"]
    if pend is not None:
        pend.add(reason)
        return
    _st["pending"] = {reason}
    QTimer.singleShot(0, _run_pending)


def _run_pending() -> None:
    reasons = _st["pending"] or {"?"}
    _st["pending"] = None
    settle_now("+".join(sorted(reasons)))


def settle_now(reason: str) -> None:
    if not winapi.IS_WINDOWS:
        return
    winapi.settle_topband(reason)
    clip_all_to_taskbar()


def _on_foreground() -> None:
    """전경 창이 바뀜. 셸이 Z-order 를 다 바꾼 뒤까지 몇 번 확인하되, 새 알림이 오면 이전 확인은 취소한다 (중복 실행 방지)."""
    _st["gen"] += 1
    gen = _st["gen"]
    for ms in BURST_MS:
        QTimer.singleShot(ms, lambda g=gen: settle_now("foreground") if g == _st["gen"] else None)


def _ensure_net() -> None:
    """전경 창 후크와 느린 안전망 타이머를 한 번만 만든다."""
    if _st["net"] is not None:
        return
    app = QCoreApplication.instance()
    t = QTimer(app)
    t.setInterval(NET_INTERVAL_MS)
    t.timeout.connect(lambda: settle_now("safety-net"))
    _st["net"] = t
    winapi.install_foreground_hook(_on_foreground)
    t.start()
