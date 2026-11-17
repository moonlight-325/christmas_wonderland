"""화면 전환/등장 애니메이션 도우미."""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget


def fade_in(widget, delay_ms: int = 0, duration_ms: int = 300):
    """위젯을 투명 -> 불투명으로 부드럽게 나타낸다. 끝나면 효과 객체를 제거해 렌더링 비용을 없앤다."""
    old = getattr(widget, "_fade_anim", None)
    if old is not None:
        old.stop()
    eff = QGraphicsOpacityEffect(widget)
    eff.setOpacity(0.0)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
    widget._fade_anim = anim
    QTimer.singleShot(max(0, delay_ms), anim.start)
    return anim


def clear_fade(widget):
    old = getattr(widget, "_fade_anim", None)
    if old is not None:
        old.stop()
    widget.setGraphicsEffect(None)


class FadeStack(QStackedWidget):
    """페이지 전환 시 새 페이지가 서서히 나타나는 스택."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.animated = True

    def fade_to(self, index: int, ms: int = 280):
        if index == self.currentIndex():
            return
        new = self.widget(index)
        self.setCurrentIndex(index)
        if self.animated:
            fade_in(new, 0, ms)
        else:
            clear_fade(new)
