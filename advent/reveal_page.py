"""선물 공개 화면: 이미지 커튼 공개 -> 메시지 -> 이야기 -> 이벤트 순서로 부드럽게 나타난다."""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from widget.pixel_ui import PAL, PX, PixelButton, PixelPanel, draw_ink_centered, head_font, pixel_box
from widget.sprites import sprite_pixmap
from .anim import clear_fade, fade_in
from .events import build_event
from .fx import FxEngine

IMG_W, IMG_H = 96 * 3, 54 * 3          # 이미지 표시 영역 (96x54 원본 x3, 최근접 확대)
TAG_DONE = (f"QLabel{{background:#2f8f4e;color:#ffffff;border:{PX}px solid {PAL['border']};padding:{PX}px {4 * PX}px;}}")


class RevealImage(QWidget):
    """픽셀 액자 + 가운데에서 양옆으로 열리는 커튼 공개 효과."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm: QPixmap | None = None
        self._p = 1.0
        self._anim: QVariantAnimation | None = None
        self.setFixedSize(IMG_W + 6 * PX, IMG_H + 6 * PX)
        self._font = head_font(1)

    def set_image(self, path):
        pm = QPixmap(str(path)) if path else QPixmap()
        if pm.isNull():
            self._pm = None
        else:
            self._pm = pm.scaled(IMG_W, IMG_H, Qt.KeepAspectRatio, Qt.FastTransformation)   # 최근접 확대
        self.update()

    def reveal(self, animate: bool = True):
        if self._anim is not None:
            self._anim.stop()
        if not animate:
            self._p = 1.0
            self.update()
            return
        self._p = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(900)
        self._anim.valueChanged.connect(self._set_p)
        self._anim.start()

    def _set_p(self, v):
        self._p = float(v)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        pixel_box(p, self.rect(), PAL["panel_lo"], PAL["border"], lo="#06150f")
        inner = QRect(3 * PX, 3 * PX, IMG_W, IMG_H)
        p.fillRect(inner, QColor("#06150f"))
        if self._pm is None:
            gp = sprite_pixmap("gift_red", 8)
            p.drawPixmap(inner.center().x() - gp.width() // 2, inner.center().y() - gp.height() // 2 - 12, gp)
            draw_ink_centered(p, QRect(inner.x(), inner.bottom() - 40, inner.width(), 24), tr("이미지 없음"), PAL["dim"], self._font)
            return
        vis = int(self._p * inner.width()) // (4 * PX) * (4 * PX) if self._p < 1.0 else inner.width()
        x0 = inner.center().x() - vis // 2
        p.setClipRect(QRect(x0, inner.y(), vis, inner.height()))
        p.drawPixmap(inner.x() + (inner.width() - self._pm.width()) // 2, inner.y() + (inner.height() - self._pm.height()) // 2, self._pm)
        p.setClipping(False)
        if self._p < 1.0:                                        # 열리는 커튼 가장자리
            for x in (x0 - PX, x0 + vis):
                p.fillRect(x, inner.y(), PX, inner.height(), QColor(PAL["gold"]))


class FxOverlay(QWidget):
    """마우스를 통과시키는 투명 효과 레이어 (파티클 + 번쩍임)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.engines: list[FxEngine] = []
        self.flash = 0.0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def _begin(self):
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._clock.restart()
        self._timer.start(33)

    def play(self, kind: str, flash: bool = True):
        self._begin()
        self.engines = [FxEngine(kind, self.width(), self.height(), duration=5.0)]
        self.flash = 1.0 if flash else 0.0

    def wish(self, origin: QPoint):
        self._begin()
        eng = FxEngine("sparkle", self.width(), self.height(), duration=1.6)
        eng.origin = (origin.x(), origin.y())
        self.engines.append(eng)

    def stop(self):
        self._timer.stop()
        self.engines.clear()
        self.flash = 0.0
        self.hide()

    def _tick(self):
        dt = self._clock.restart() / 1000.0
        for e in self.engines:
            e.step(dt)
        self.flash = max(0.0, self.flash - dt / 0.45)
        self.engines = [e for e in self.engines if not e.finished]
        if not self.engines and self.flash <= 0:
            self.stop()
            return
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        if self.flash > 0:
            step = int(self.flash * 4) / 4.0                    # 단계적으로 사라지는 번쩍임 (픽셀 느낌)
            p.fillRect(self.rect(), QColor(255, 255, 255, int(150 * step)))
        for eng in self.engines:
            eng.paint(p, 1.0, unit=PX)


class RevealPage(QWidget):
    back = Signal()
    eventResult = Signal(int, dict)
    launchRequested = Signal(int)          # 선물 실행 버튼 (day)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gift = None
        self._event = None
        self._anim_on = True
        root = QVBoxLayout(self)
        root.setContentsMargins(2 * PX, 2 * PX, 2 * PX, 2 * PX)
        root.setSpacing(4 * PX)

        top = QHBoxLayout()
        top.setSpacing(3 * PX)
        self.btn_back = PixelButton(tr("캘린더"), "prev")
        self.btn_back.clicked.connect(self.back.emit)
        top.addWidget(self.btn_back)
        self.title = QLabel()
        self.title.setFont(head_font(2))
        self.title.setStyleSheet(f"color:{PAL['gold']};")
        top.addWidget(self.title, 1)
        self.tag_done = QLabel(tr("개봉 완료"))
        self.tag_done.setStyleSheet(TAG_DONE)
        top.addWidget(self.tag_done)
        root.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(4 * PX)
        self.image = RevealImage()
        row.addWidget(self.image)
        self.msg_panel = PixelPanel()
        ml = QVBoxLayout(self.msg_panel)
        ml.setContentsMargins(6 * PX, 5 * PX, 6 * PX, 5 * PX)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.message.setStyleSheet(f"color:{PAL['gold']};")
        ml.addWidget(self.message)
        row.addWidget(self.msg_panel, 1)
        root.addLayout(row)

        self.story_panel = PixelPanel(fill="panel_lo")
        sl = QVBoxLayout(self.story_panel)
        sl.setContentsMargins(3 * PX, 3 * PX, 3 * PX, 3 * PX)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:0;} QScrollArea > QWidget > QWidget{background:transparent;}")
        self.story = QLabel()
        self.story.setWordWrap(True)
        self.story.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.story.setContentsMargins(3 * PX, 2 * PX, 3 * PX, 2 * PX)
        self.scroll.setWidget(self.story)
        sl.addWidget(self.scroll)
        self.story_panel.setFixedHeight(64 * PX)
        root.addWidget(self.story_panel)

        self.event_panel = PixelPanel()
        self.event_lay = QVBoxLayout(self.event_panel)
        self.event_lay.setContentsMargins(5 * PX, 4 * PX, 5 * PX, 4 * PX)
        root.addWidget(self.event_panel, 1)

        bottom = QHBoxLayout()
        self.btn_replay = PixelButton(tr("효과 다시 보기"), "sparkle")
        self.btn_replay.clicked.connect(self.replay)
        bottom.addWidget(self.btn_replay)
        bottom.addStretch(1)
        self.btn_launch = PixelButton(tr("선물 실행"), "play", kind="accent")
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        self.btn_launch.setVisible(False)                 # action 이 있는 선물에서만 표시
        bottom.addWidget(self.btn_launch)
        root.addLayout(bottom)

        self.overlay = FxOverlay(self)

    def resizeEvent(self, e):
        self.overlay.setGeometry(self.rect())

    def hideEvent(self, e):
        self.overlay.stop()

    # ------------------------------------------------------------------ 표시
    def show_gift(self, gift, *, first: bool, prev_event, animations: bool, events_enabled: bool,
                  launch_running: bool = False):
        self._gift = gift
        self._anim_on = animations
        self.overlay.stop()
        for w in (self.title, self.image, self.msg_panel, self.story_panel, self.event_panel):
            clear_fade(w)
        self.title.setText(tr("12월 {0}일  {1}").format(gift.day, gift.title))
        self.tag_done.setText(tr("방금 열었어요") if first else tr("개봉 완료"))
        self.image.set_image(gift.image)
        self.message.setText(gift.message)
        self.story.setText(gift.story)
        self.scroll.verticalScrollBar().setValue(0)

        if self._event is not None:
            self.event_lay.removeWidget(self._event)
            self._event.deleteLater()
            self._event = None
        ev = build_event(gift.event, prev_event) if events_enabled else None
        if ev is not None:
            ev.done.connect(lambda r, d=gift.day: self.eventResult.emit(d, r))
            if hasattr(ev, "wishSent"):
                ev.wishSent.connect(self._on_wish)
            self.event_lay.addWidget(ev)
            self._event = ev
        self.event_panel.setVisible(ev is not None)
        self.btn_launch.setVisible(getattr(gift, "action", None) is not None)
        self.set_launch_running(launch_running)

        if animations:
            self.image.reveal(True)
            fade_in(self.title, 0, 300)
            fade_in(self.msg_panel, 700, 400)
            fade_in(self.story_panel, 1100, 400)
            if ev is not None:
                fade_in(self.event_panel, 1500, 400)
            QTimer.singleShot(0, lambda: self.overlay.play(gift.animation, flash=True))
        else:
            self.image.reveal(False)

    def _on_launch_clicked(self):
        if self._gift is not None and getattr(self._gift, "action", None) is not None:
            self.launchRequested.emit(self._gift.day)

    def set_launch_running(self, running: bool):
        """실행 중에는 버튼을 잠가 같은 프로그램이 중복 실행되지 않게 한다."""
        self.btn_launch.setEnabled(not running)
        self.btn_launch.setText(tr("실행 중") if running else tr("선물 실행"))

    @property
    def current_day(self) -> int | None:
        return self._gift.day if self._gift is not None else None

    def replay(self):
        if self._gift is not None:
            self.overlay.play(self._gift.animation, flash=False)

    def _on_wish(self, _text: str):
        if self._event is not None and self._anim_on:
            origin = self.overlay.mapFromGlobal(self._event.mapToGlobal(QPoint(self._event.width() // 2, 8)))
            self.overlay.wish(origin)
