"""데스크톱 픽셀 장식: 장식 하나 = 투명한 작은 창 하나. 마우스로 이동/크기 조절, 우클릭 메뉴, 설정에 위치·크기 저장."""
from __future__ import annotations
from core.i18n import tr


import uuid

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QToolTip, QWidget

from core.geometry import clamp_pos, position_text, scale_text
from core.logger import get_logger
from widget.pixel_extra import PixelPopupMenu
from widget.pixel_ui import PAL, PX
from widget.sprites import sprite_image, sprite_pixmap
from .layer import TopBandMixin, apply_layer, show_layered
from .sprites import KIND_SPRITE

log = get_logger("decor")
MIN_SCALE, MAX_SCALE = 1, 14
GRIP = 7



def _screens_union() -> QRect:
    r = QRect()
    for sc in QGuiApplication.screens():
        r = r.united(sc.availableGeometry())
    return r if not r.isNull() else QRect(0, 0, 1280, 720)


class DecorWindow(TopBandMixin, QWidget):
    moved = Signal(str, int, int)          # id, x, y  (드래그 종료 시)
    resized = Signal(str, int)             # id, scale
    delete_requested = Signal(str)
    hide_requested = Signal(str)

    def __init__(self, item: dict, locked: bool, layer: str, parent=None):
        super().__init__(parent)
        self.item_id = item["id"]
        self.kind = item["kind"]
        self.scale = item["scale"]
        self.locked = locked
        self._drag: QPoint | None = None
        self._grip_drag = False
        self._hover = False
        self.dragging = False
        self.setMouseTracking(True)
        apply_layer(self, layer)
        self.set_locked(locked)
        self._fit()
        self.move(item["x"], item["y"])

    def set_locked(self, locked: bool):
        """잠금 상태를 바꾼다. 잠겨 있으면 끌기 커서를 숨긴다."""
        self.locked = bool(locked)
        if self.locked:
            self.unsetCursor()

    def _tip(self, text: str, gpos: QPoint):
        """끄는 동안 커서 옆에 현재 값을 보여 준다 (장식 창이 작아도 글자가 가려지지 않게 툴팁을 쓴다)."""
        QToolTip.showText(gpos + QPoint(16, 20), text, self)

    # ---- 크기
    def sprite_size(self):
        img = sprite_image(KIND_SPRITE[self.kind])
        return img.width(), img.height()

    def _fit(self):
        w, h = self.sprite_size()
        self.setFixedSize(w * self.scale, h * self.scale)

    def set_scale(self, scale: int):
        scale = max(MIN_SCALE, min(MAX_SCALE, int(scale)))
        if scale != self.scale:
            self.scale = scale
            self._fit()
            self.update()

    # ---- 그리기
    def paintEvent(self, e):
        p = QPainter(self)
        pm = sprite_pixmap(KIND_SPRITE[self.kind], self.scale)
        p.drawPixmap(0, 0, pm)          # 장식 메뉴의 눈사람은 온도와 무관하게 절대 녹지 않는다 (v1.7.0)
        if self._hover and not self.locked:
            col = PAL["gold"]
            r = self.rect()
            for rect in (QRect(0, 0, r.width(), PX), QRect(0, r.height() - PX, r.width(), PX),
                         QRect(0, 0, PX, r.height()), QRect(r.width() - PX, 0, PX, r.height())):
                p.fillRect(rect, QColor(col))
            g = self._grip_rect()
            p.fillRect(g, QColor(col))
        p.end()

    def _grip_rect(self) -> QRect:
        g = GRIP * PX
        return QRect(self.width() - g, self.height() - g, g, g)

    # ---- 마우스
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton or self.locked:
            return
        if self._grip_rect().contains(e.position().toPoint()):
            self._grip_drag = True
            self.dragging = True
        else:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.dragging = True

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._grip_drag:
            w, h = self.sprite_size()
            self.set_scale(round(max(pos.x() / w, pos.y() / h)))
            self._tip(scale_text(self.scale, self.width(), self.height()), e.globalPosition().toPoint())
        elif self._drag is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)
            self._tip(position_text(self.x(), self.y()), e.globalPosition().toPoint())
        elif not self.locked:
            self.setCursor(Qt.SizeFDiagCursor if self._grip_rect().contains(pos) else Qt.SizeAllCursor)

    def mouseReleaseEvent(self, e):
        QToolTip.hideText()
        if self._grip_drag:
            self._grip_drag = False
            self.dragging = False
            self.resized.emit(self.item_id, self.scale)
            self.moved.emit(self.item_id, self.x(), self.y())
        elif self._drag is not None:
            self._drag = None
            self.dragging = False
            self.moved.emit(self.item_id, self.x(), self.y())

    def wheelEvent(self, e):
        if self.locked:
            return
        step = 1 if e.angleDelta().y() > 0 else -1
        self._change_scale(step)
        self._tip(scale_text(self.scale, self.width(), self.height()), e.globalPosition().toPoint())

    def _change_scale(self, step: int):
        before = self.scale
        self.set_scale(self.scale + step)
        if self.scale != before:
            self.resized.emit(self.item_id, self.scale)

    def _menu(self, gpos: QPoint):
        items = [
            (tr("크게"), "star", lambda: self._change_scale(1), "flat"),
            (tr("작게"), "minus", lambda: self._change_scale(-1), "flat"),
            (tr("숨기기"), "close", lambda: self.hide_requested.emit(self.item_id), "flat"),
            (tr("삭제"), "trash", lambda: self.delete_requested.emit(self.item_id), "danger"),
        ]
        self._popup = PixelPopupMenu(items)
        self._popup.popup(gpos)


class DecorManager(QObject):
    """설정(decor.*)과 장식 창들을 동기화한다."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.windows: dict[str, DecorWindow] = {}
        settings.changed.connect(self._on_setting)

    def start(self):
        self.sync()

    def shutdown(self):
        for w in self.windows.values():
            w.close()
            w.deleteLater()
        self.windows.clear()

    # ---- 설정 조작 (UI 에서 호출)
    def items(self) -> list:
        return self.s.get("decor.items")

    def add(self, kind: str) -> str:
        items = self.items()
        if len(items) >= 60 or kind not in KIND_SPRITE:
            return ""
        area = _screens_union()
        n = len(items)
        iid = uuid.uuid4().hex[:8]
        items.append({"id": iid, "kind": kind,
                      "x": area.center().x() - 40 + (n % 8) * 28, "y": area.center().y() - 60 + (n % 6) * 24,
                      "scale": 4, "visible": True})
        self.s.set("decor.enabled", True)
        self.s.set("decor.items", items, save=True)
        return iid

    def remove(self, iid: str):
        self.s.set("decor.items", [i for i in self.items() if i["id"] != iid], save=True)

    def set_visible(self, iid: str, on: bool):
        items = self.items()
        for i in items:
            if i["id"] == iid:
                i["visible"] = bool(on)
        self.s.set("decor.items", items, save=True)

    def update_item(self, iid: str, **kw):
        items = self.items()
        for i in items:
            if i["id"] == iid:
                i.update(kw)
        self.s.set("decor.items", items, save=True)

    def clear_all(self):
        self.s.set("decor.items", [], save=True)

    # ---- 동기화
    def _on_setting(self, key: str):
        if key == "*" or key.startswith("decor."):
            self.sync()

    def _on_moved(self, iid: str, x: int, y: int):
        """드래그가 끝났을 때: 화면 밖에 놓였으면 가장 가까운 화면 안으로 되돌리고 알린다.
        (보정하지 않으면 위치가 저장된 채 화면 밖에 남아 찾을 수 없고, 다음 실행 때 갑자기 옮겨진다.)"""
        w = self.windows.get(iid)
        if w is not None:
            nx, ny = clamp_pos(x, y, w.width(), w.height())
            if (nx, ny) != (x, y):
                w.move(nx, ny)
                x, y = nx, ny
                QToolTip.showText(QCursor.pos() + QPoint(16, 20), tr("화면 밖이라 안으로 되돌렸어요"), w)
        self.update_item(iid, x=x, y=y)

    def _clamp(self, x: int, y: int, w: int, h: int):
        area = _screens_union()
        x = max(area.left() - w + 24, min(area.right() - 24, x))
        y = max(area.top() - h + 24, min(area.bottom() - 24, y))
        return x, y

    def sync(self):
        enabled = bool(self.s.get("decor.enabled"))
        locked = bool(self.s.get("decor.locked"))
        layer = self.s.get("decor.layer")
        want = {i["id"]: i for i in self.items()} if enabled else {}
        for iid in [k for k in self.windows if k not in want or not want[k]["visible"]]:
            w = self.windows.pop(iid)
            w.close()
            w.deleteLater()
        for iid, it in want.items():
            if not it["visible"]:
                continue
            w = self.windows.get(iid)
            if w is None:
                x, y = self._clamp(it["x"], it["y"], 40, 40)
                it = dict(it, x=x, y=y)
                w = DecorWindow(it, locked, layer)
                w.moved.connect(self._on_moved)
                w.resized.connect(lambda i, sc: self.update_item(i, scale=sc))
                w.delete_requested.connect(self.remove)
                w.hide_requested.connect(lambda i: self.set_visible(i, False))
                self.windows[iid] = w
                show_layered(w)
            elif not w.dragging:
                w.set_locked(locked)
                apply_layer(w, layer)
                w.set_scale(it["scale"])
                if (w.x(), w.y()) != (it["x"], it["y"]):
                    w.move(it["x"], it["y"])
                if not w.isVisible():
                    show_layered(w)
