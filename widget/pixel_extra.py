"""새 설정 화면용 픽셀 위젯: 선택 버튼 묶음, 색상 견본, 팝업 메뉴 (기본 Qt 메뉴/콤보를 쓰지 않는다)."""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QVBoxLayout, QWidget

from .pixel_ui import PAL, PX, PixelButton, body_font, pixel_box


class PixelChoice(QWidget):
    """여러 선택지 중 하나를 고르는 가로 버튼 묶음."""
    changed = Signal(str)

    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self._btns: dict[str, PixelButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2 * PX)
        for key, label in items:
            b = PixelButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            lay.addWidget(b)
            self._btns[key] = b
        lay.addStretch(1)
        self._value = None

    def _pick(self, key: str):
        self.set_value(key)
        self.changed.emit(key)

    def set_value(self, key: str):
        self._value = key
        for k, b in self._btns.items():
            b.setChecked(k == key)

    def value(self):
        return self._value


class PixelSwatches(QWidget):
    """색상 견본 줄. colors: {키: '#rrggbb'}"""
    changed = Signal(str)
    CELL = 13 * PX

    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)
        self.colors = colors
        self._value = None
        self._hover = None
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.CELL + PX)
        self.setMinimumWidth(len(colors) * (self.CELL + 2 * PX))

    def set_value(self, key: str):
        self._value = key
        self.update()

    def _rect(self, i: int) -> QRect:
        return QRect(i * (self.CELL + 2 * PX), 0, self.CELL, self.CELL)

    def _index_at(self, pos):
        for i, _k in enumerate(self.colors):
            if self._rect(i).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().toPoint())
        h = list(self.colors)[i] if i >= 0 else None
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        i = self._index_at(e.position().toPoint())
        if i >= 0 and e.button() == Qt.LeftButton:
            key = list(self.colors)[i]
            self.set_value(key)
            self.changed.emit(key)

    def sizeHint(self) -> QSize:
        return QSize(len(self.colors) * (self.CELL + 2 * PX), self.CELL + PX)

    def paintEvent(self, e):
        p = QPainter(self)
        for i, (k, col) in enumerate(self.colors.items()):
            r = self._rect(i)
            sel = k == self._value
            pixel_box(p, r, col, PAL["gold"] if sel else (PAL["border"] if k == self._hover else PAL["border_dark"]))
            if sel:
                p.fillRect(r.center().x() - PX, r.center().y() - PX, 2 * PX, 2 * PX, QColor(PAL["shadow"]))
        p.end()


class PixelPopupMenu(QWidget):
    """우클릭 팝업 메뉴. items: [(라벨, 아이콘 또는 None, 콜백, 종류)]"""

    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(3 * PX, 3 * PX, 3 * PX, 3 * PX)
        lay.setSpacing(PX)
        for label, icon, cb, kind in items:
            b = PixelButton(label, icon, kind=kind or "flat")
            b.clicked.connect(lambda _=False, f=cb: (self.close(), f()))
            lay.addWidget(b)

    def paintEvent(self, e):
        p = QPainter(self)
        pixel_box(p, self.rect(), PAL["bg"], PAL["border"], lo=PAL["panel_lo"])
        p.end()

    def popup(self, global_pos):
        self.adjustSize()
        self.move(global_pos)
        self.show()


class PixelTile(QAbstractButton):
    """그림으로 고르는 타일. 이름은 타일에 쓰지 않고, 마우스를 올리면 hovered(이름)를 보내 바깥의 한 줄 안내가 보여 준다.
    선택됨 = 금색 이중 테두리, 흐리게(dim) = 숨겨 둔 항목. QAbstractButton 이라 checkable / clicked / setChecked 를 그대로 쓴다."""
    hovered = Signal(object)            # 이름 또는 None(마우스가 나감)

    def __init__(self, image: QImage, name: str, w: int, h: int, badge: str = "", dim: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        self._img = image
        self._badge = badge
        self._dim = dim
        self._hover = False
        self._cache = None
        self.setCheckable(True)
        self.setFont(body_font())
        self.setFixedSize(w, h)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)

    def set_image(self, image: QImage, dim: bool | None = None):
        self._img = image
        if dim is not None:
            self._dim = dim
        self._cache = None
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.hovered.emit(self.name)
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.hovered.emit(None)
        self.update()

    def _scaled(self, box: QRect):
        key = (box.width(), box.height())
        if self._cache is None or self._cache[0] != key:
            im = self._img.scaled(box.width(), box.height(), Qt.KeepAspectRatio, Qt.FastTransformation)
            self._cache = (key, im)
        return self._cache[1]

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        on = self.isChecked()
        pixel_box(p, r, PAL["panel_hi"] if on else PAL["panel_lo"],
                  PAL["gold"] if on else (PAL["border"] if (self._hover or self.hasFocus()) else PAL["border_dark"]),
                  lo=None if on else PAL["bg"])
        if on:                                            # 선택됨: 안쪽에 한 겹 더 (색만이 아니라 모양으로도 구분)
            u = PX
            inner = r.adjusted(2 * u, 2 * u, -2 * u, -2 * u)
            p.fillRect(inner.x(), inner.y(), inner.width(), u, QColor(PAL["gold"]))
            p.fillRect(inner.x(), inner.bottom() - u + 1, inner.width(), u, QColor(PAL["gold"]))
            p.fillRect(inner.x(), inner.y(), u, inner.height(), QColor(PAL["gold"]))
            p.fillRect(inner.right() - u + 1, inner.y(), u, inner.height(), QColor(PAL["gold"]))
        box = r.adjusted(4 * PX, 4 * PX, -4 * PX, -4 * PX)
        im = self._scaled(box)
        if self._dim:
            p.setOpacity(0.4)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(box.x() + (box.width() - im.width()) // 2, box.y() + (box.height() - im.height()) // 2, im)
        p.setOpacity(1.0)
        if self._badge:
            f = self.font()
            p.setFont(f)
            tw = self.fontMetrics().horizontalAdvance(self._badge)
            bw, bh = tw + 4 * PX, self.fontMetrics().height() + PX
            pixel_box(p, QRect(2 * PX, 2 * PX, bw, bh), PAL["shadow"], PAL["border_dark"])
            p.setPen(QColor(PAL["gold"] if on else PAL["text"]))
            p.drawText(QRect(2 * PX, 2 * PX, bw, bh), Qt.AlignCenter, self._badge)
        p.end()
