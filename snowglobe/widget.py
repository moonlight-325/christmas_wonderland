"""바탕화면 스노우볼 위젯: 스노우볼 한 개 = 투명한 창 한 개. 그리기만 담당하고 물리는 매니저가 돌린다.

조작: 왼쪽 버튼으로 잡아 끌면 창이 움직이며 그 가속도가 내부 눈에 전해진다(직접 흔들기).
      Ctrl/Alt 를 누르고 끌면 눈을 건드리지 않고 조용히 옮긴다. 가볍게 클릭하면 자동 흔들기(유리는 움직이지 않고 눈만 휘몰아친다). 오른쪽 클릭 = 메뉴.
"""
from __future__ import annotations
from core.i18n import tr


import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from decor.layer import apply_layer

from . import catalog as C


class GlobeWidget(QWidget):
    CLICK_SLOP = 4

    def __init__(self, mgr, gid: str):
        super().__init__()
        self.mgr = mgr
        self.gid = gid
        self.selected = False
        self._frame: QImage | None = None
        self._jolt = (0.0, 0.0)
        self._press: QPoint | None = None
        self._win0 = QPoint()
        self._moved = False
        self._quiet = False
        self._holding = False
        self._tail = 0.0
        self._last_pos: QPoint | None = None
        self._vel = (0.0, 0.0)
        self._acc = (0.0, 0.0)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.apply_size()
        apply_layer(self, "normal")

    # ------------------------------------------------------------ 크기 / 그리기
    def scale_px(self) -> int:
        return max(1, int(self.mgr.get(self.gid)["size"]))

    def apply_size(self):
        s = self.scale_px()
        self.setFixedSize(C.GW * s, C.GH * s)
        self.update()

    def set_frame(self, img: QImage, jolt=(0.0, 0.0)):
        self._frame = img
        self._jolt = jolt
        self.update()

    def paintEvent(self, e):
        if self._frame is None:
            return
        s = self.scale_px()
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)       # 픽셀아트: 최근접 확대
        p.drawImage(QRect(int(self._jolt[0] * s), int(self._jolt[1] * s), C.GW * s, C.GH * s), self._frame)
        p.end()

    # ------------------------------------------------------------ 직접 흔들기: 창 이동 -> 가속도
    def sample_accel(self, dt: float):
        """창이 움직인 만큼을 논리 픽셀 가속도로 바꿔 돌려준다 (잡고 있는 동안과 놓은 직후만)."""
        pos = self.pos()
        active = self._holding or self._tail > 0
        if self._tail > 0:
            self._tail = max(0.0, self._tail - dt)
        if not active or self._last_pos is None or dt <= 0:
            self._last_pos = pos
            self._vel = (0.0, 0.0)
            self._acc = (0.0, 0.0)
            return 0.0, 0.0
        s = self.scale_px()
        vx = (pos.x() - self._last_pos.x()) / dt / s
        vy = (pos.y() - self._last_pos.y()) / dt / s
        ax, ay = (vx - self._vel[0]) / dt, (vy - self._vel[1]) / dt
        self._acc = (self._acc[0] * 0.5 + ax * 0.5, self._acc[1] * 0.5 + ay * 0.5)
        self._vel = (vx, vy)
        self._last_pos = pos
        if self._quiet or math.hypot(*self._acc) < 60.0:             # 조용히 옮기기 / 미세한 떨림은 무시
            return 0.0, 0.0
        return self._acc

    # ------------------------------------------------------------ 마우스
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._win0 = self.pos()
            self._moved = False
            self._quiet = bool(e.modifiers() & (Qt.ControlModifier | Qt.AltModifier))
            self._holding = True
            self._last_pos = self.pos()
            self._vel = (0.0, 0.0)
            self._acc = (0.0, 0.0)
            self.mgr.select(self.gid)
            e.accept()
        elif e.button() == Qt.RightButton:
            self.mgr.select(self.gid)
            self._menu(e.globalPosition().toPoint())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        d = e.globalPosition().toPoint() - self._press
        if not self._moved and abs(d.x()) + abs(d.y()) < self.CLICK_SLOP:
            return
        self._moved = True
        if not self.mgr.get(self.gid).get("position_locked", False):
            self.move(self._win0 + d)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press is None:
            return
        self._press = None
        self._holding = False
        self._tail = 0.12                       # 놓는 순간의 급정지 가속도까지 눈에 전달
        if self._moved:
            if not self.mgr.get(self.gid).get("position_locked", False):
                self.mgr.moved(self.gid, self.x(), self.y())
        else:
            self.mgr.click(self.gid)
        self._moved = False

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.mgr.resize_step(self.gid, 1 if e.angleDelta().y() > 0 else -1)
            e.accept()
        else:
            e.ignore()

    def _menu(self, gpos: QPoint):
        from widget.pixel_extra import PixelPopupMenu            # 지연 import (패키지 간 순환 방지)
        m, gid = self.mgr, self.gid
        items = [
            (tr("흔들기"), "sparkle", lambda: m.shake(gid), "flat"),
            (tr("설정 / 꾸미기"), "gear", lambda: m.open_requested.emit(gid), "flat"),
            (tr("크게"), "star", lambda: m.resize_step(gid, 1), "flat"),
            (tr("작게"), "minus", lambda: m.resize_step(gid, -1), "flat"),
            (tr("복제"), "box", lambda: m.duplicate(gid), "flat"),
            (tr("숨기기"), "close", lambda: m.update(gid, visible=False), "flat"),
            (tr("삭제"), "trash", lambda: m.remove(gid), "danger"),
        ]
        self._popup = PixelPopupMenu(items)
        self._popup.popup(gpos)
