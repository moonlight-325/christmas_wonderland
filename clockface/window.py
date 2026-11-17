"""시계 창(바탕화면에 떠 있는 시계)과 설정 화면용 미리보기 위젯."""
from __future__ import annotations
from core.i18n import tr


from datetime import datetime

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import QToolTip, QWidget

from core.geometry import clamp_pos, position_text
from decor.layer import TopBandMixin, apply_layer, show_layered
from widget.pixel_ui import PAL, PX, pixel_box
from . import render

CFG_KEYS = ("theme", "scale", "color", "bg", "opacity", "show_time", "show_seconds", "h24",
            "show_date", "show_weekday", "show_dday")


def read_cfg(settings) -> dict:
    return {k: settings.get(f"clock.{k}") for k in CFG_KEYS}


class ClockWindow(TopBandMixin, QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self._drag: QPoint | None = None
        self.cfg = read_cfg(settings)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.update)
        settings.changed.connect(self._on_setting)
        self.reconfigure()

    def _on_setting(self, key: str):
        if key == "*" or key.startswith("clock."):
            self.reconfigure()

    def reconfigure(self):
        s = self.s
        if not s.get("clock.enabled"):
            self._timer.stop()
            self.hide()
            return
        self.cfg = read_cfg(s)
        apply_layer(self, s.get("clock.layer"))
        self.setFixedSize(render.size(self.cfg))
        self.setWindowOpacity(int(s.get("clock.opacity")) / 100.0)
        locked = bool(s.get("clock.locked"))                  # 풀려 있을 때만 끌 수 있는 커서를 보여 준다
        self.setCursor(Qt.ArrowCursor if locked else Qt.SizeAllCursor)
        if self._drag is None and not self.isVisible():
            from core.geometry import clamp_pos           # 모니터 구성이 바뀌어 화면 밖이 된 위치 보정
            self.move(*clamp_pos(int(s.get("clock.x")), int(s.get("clock.y")), self.width(), self.height()))
        if not self.isVisible():
            show_layered(self)
        self._timer.start()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        render.paint(p, self.cfg, datetime.now())
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.s.get("clock.locked"):
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)
            QToolTip.showText(e.globalPosition().toPoint() + QPoint(16, 20), position_text(self.x(), self.y()), self)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            QToolTip.hideText()
            nx, ny = clamp_pos(self.x(), self.y(), self.width(), self.height())    # 화면 밖에 놓았으면 안으로 되돌린다
            if (nx, ny) != (self.x(), self.y()):
                self.move(nx, ny)
                QToolTip.showText(QCursor.pos() + QPoint(16, 20), tr("화면 밖이라 안으로 되돌렸어요"), self)
            self.s.set("clock.x", self.x())
            self.s.set("clock.y", self.y(), save=True)

    def shutdown(self):
        self._timer.stop()
        self.close()


class ClockPreview(QWidget):
    """설정 변경이 즉시 반영되는 미리보기. 현재 설정 그대로 그리되, 미리보기 칸보다 크면 정수 배로 축소해 맞춘다."""

    def __init__(self, settings, height: int = 120 * PX, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setMinimumHeight(height)
        settings.changed.connect(lambda k: self.update() if k == "*" or k.startswith("clock.") else None)
        self._t = QTimer(self)
        self._t.setInterval(500)
        self._t.timeout.connect(self.update)
        self._t.start()

    def paintEvent(self, e):
        p = QPainter(self)
        pixel_box(p, self.rect(), "#2a3b34", PAL["border_dark"], lo=PAL["panel_lo"])
        cell = 6 * PX                                           # 체크무늬로 투명도 확인
        for y in range(PX * 2, self.height() - PX * 2, cell):
            for x in range(PX * 2, self.width() - PX * 2, cell):
                if ((x // cell) + (y // cell)) % 2 == 0:
                    p.fillRect(x, y, min(cell, self.width() - PX * 2 - x), min(cell, self.height() - PX * 2 - y), QColor("#31453d"))
        cfg = read_cfg(self.s)
        img = render.render_image(cfg, datetime.now())
        area = self.rect().adjusted(4 * PX, 4 * PX, -4 * PX, -4 * PX)
        if img.width() > area.width() or img.height() > area.height():
            img = img.scaled(area.size(), Qt.KeepAspectRatio, Qt.FastTransformation)   # 최근접
        p.setOpacity(int(cfg["opacity"]) / 100.0)
        p.drawImage(area.x() + (area.width() - img.width()) // 2, area.y() + (area.height() - img.height()) // 2, img)
        p.end()
