"""바람 컨트롤러: 360도 원형 다이얼 + 길이로 풍속을 정하는 화살표.

 - 화살표 방향 = 바람이 향하는 방향 (0도 북, 90도 동, 180도 남, 270도 서)
 - 화살표 끝을 끌어서 회전하고 길이를 조절한다. 길이 0 = 무풍, 최대 길이 = 100%
저해상도 캔버스(75x75)에 그린 뒤 4배 최근접 확대하여 픽셀을 유지한다.
"""
from __future__ import annotations
from core.i18n import tr


import math

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QWidget

from .pixel_ui import PAL

CANVAS = 75
UNIT = 4                # 기본 확대 배율 (작은 창에서는 3)
CENTER = CANVAS // 2
RING_R = 33
ARROW_MAX = 29

GLYPHS = {
    "N": ["#.#", "###", "###", "#.#", "#.#"],
    "E": ["###", "#..", "##.", "#..", "###"],
    "S": ["###", "#..", "###", "..#", "###"],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
}
NAMES = [tr("북"), tr("북동"), tr("동"), tr("남동"), tr("남"), tr("남서"), tr("서"), tr("북서")]


def direction_name(deg: float) -> str:
    return NAMES[int(((deg % 360) + 22.5) // 45) % 8]


class WindDial(QWidget):
    changed = Signal(int, int)        # (방향 0~359, 풍속 0~100) 드래그 중
    released = Signal()               # 드래그 종료 (저장 시점)

    def __init__(self, parent=None, unit: int = UNIT, crop: int = 0):
        super().__init__(parent)
        self.unit = unit
        self.crop = crop                # 바깥 빈 여백 중 잘라낼 캔버스 픽셀 수 (좁은 창용)
        self._angle = 90
        self._pct = 15
        self._down = False
        side = (CANVAS - 2 * crop) * unit
        self.setFixedSize(side, side)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.TabFocus)

    def sizeHint(self) -> QSize:
        return self.size()

    # ---- 값
    def set_wind(self, angle: int, pct: int):
        if (angle, pct) != (self._angle, self._pct):
            self._angle, self._pct = int(angle) % 360, max(0, min(100, int(pct)))
            self.update()

    def angle(self) -> int:
        return self._angle

    def pct(self) -> int:
        return self._pct

    # ---- 마우스
    def _apply(self, pos: QPoint):
        dx = pos.x() / self.unit + self.crop - CENTER
        dy = pos.y() / self.unit + self.crop - CENTER
        length = math.hypot(dx, dy)
        if length >= 2.5:
            self._angle = int(round(math.degrees(math.atan2(dx, -dy)))) % 360
        self._pct = int(round(min(1.0, length / ARROW_MAX) * 100))
        if length < 2.5:
            self._pct = 0
        self.update()
        self.changed.emit(self._angle, self._pct)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._down = True
            self._apply(e.position().toPoint())

    def mouseMoveEvent(self, e):
        if self._down:
            self._apply(e.position().toPoint())

    def mouseReleaseEvent(self, e):
        if self._down:
            self._down = False
            self.released.emit()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_Right):
            self._angle = (self._angle + (5 if k == Qt.Key_Right else -5)) % 360
        elif k in (Qt.Key_Up, Qt.Key_Down):
            self._pct = max(0, min(100, self._pct + (5 if k == Qt.Key_Up else -5)))
        else:
            super().keyPressEvent(e)
            return
        self.update()
        self.changed.emit(self._angle, self._pct)
        self.released.emit()

    # ---- 그리기
    def _polar(self, deg: float, r: float):
        th = math.radians(deg)
        return CENTER + math.sin(th) * r, CENTER - math.cos(th) * r

    def paintEvent(self, e):
        img = QImage(CANVAS, CANVAS, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, False)
        try:
            self._paint(p)
        finally:
            p.end()
        q = QPainter(self)
        off = -self.crop * self.unit
        q.drawImage(QRect(off, off, CANVAS * self.unit, CANVAS * self.unit), img)
        q.end()                               # 포커스 노란 테두리는 그리지 않음

    def _paint(self, p: QPainter):
        # 바깥 링과 바탕
        p.setPen(QPen(QColor(PAL["border"]), 1))
        p.setBrush(QColor(PAL["panel_lo"]))
        p.drawEllipse(QPoint(CENTER, CENTER), RING_R, RING_R)
        p.setPen(QPen(QColor(PAL["border_dark"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPoint(CENTER, CENTER), RING_R - 2, RING_R - 2)
        # 풍속 눈금 링 (25/50/75%) - 점선
        for frac in (0.25, 0.5, 0.75):
            r = ARROW_MAX * frac
            for k in range(0, 360, 12 if frac > 0.4 else 20):
                x, y = self._polar(k, r)
                p.fillRect(int(round(x)), int(round(y)), 1, 1, QColor("#2c6f58"))
        # 방위 눈금 (45도마다) 과 N/E/S/W 글자
        for k in range(0, 360, 15):
            major = k % 45 == 0
            r0, r1 = (RING_R - 6, RING_R - 3) if major else (RING_R - 4, RING_R - 3)
            x0, y0 = self._polar(k, r0)
            x1, y1 = self._polar(k, r1)
            p.setPen(QColor(PAL["gold"] if k % 90 == 0 else PAL["border_dark"]))
            p.drawLine(int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
        for k, ch in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
            g = GLYPHS[ch]
            gw, gh = len(g[0]), len(g)
            x, y = self._polar(k, RING_R - 11)
            ox, oy = int(round(x)) - gw // 2, int(round(y)) - gh // 2
            col = QColor(PAL["snow"] if ch == "N" else PAL["text"])
            for ry, row in enumerate(g):
                for rx, c in enumerate(row):
                    if c == "#":
                        p.fillRect(ox + rx, oy + ry, 1, 1, col)
        # 화살표
        length = ARROW_MAX * self._pct / 100.0
        tx, ty = self._polar(self._angle, length)
        if self._pct > 0:
            p.setPen(QPen(QColor(PAL["sky"]), 2, Qt.SolidLine, Qt.FlatCap))
            p.drawLine(CENTER, CENTER, int(round(tx)), int(round(ty)))
            if length >= 7:
                a = self._angle
                hx, hy = self._polar(a, length - 6)
                lx, ly = self._polar(a - 90, 3.2)
                dx, dy = lx - CENTER, ly - CENTER
                poly = QPolygon([QPoint(int(round(tx)), int(round(ty))),
                                 QPoint(int(round(hx + dx)), int(round(hy + dy))),
                                 QPoint(int(round(hx - dx)), int(round(hy - dy)))])
                p.setPen(QPen(QColor(PAL["sky"]), 1))
                p.setBrush(QColor(PAL["sky"]))
                p.drawPolygon(poly)
        # 중심 허브와 끝 손잡이
        p.fillRect(CENTER - 2, CENTER - 2, 5, 5, QColor(PAL["border"]))
        p.fillRect(CENTER - 1, CENTER - 1, 3, 3, QColor(PAL["red"]))
        hx, hy = int(round(tx)), int(round(ty))
        p.setPen(QPen(QColor(PAL["shadow"]), 1))
        p.setBrush(QColor(PAL["gold"]))
        p.drawRect(hx - 2, hy - 2, 4, 4)
