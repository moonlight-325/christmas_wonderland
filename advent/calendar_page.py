"""어드벤트 캘린더 화면: 저해상도 캔버스(QImage)에 픽셀 단위로 24개 선물 상자를 그린 뒤 정수 배로 확대한다."""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QElapsedTimer, QRect, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from core.fonts import pixel_font
from widget.pixel_ui import PAL, PX, draw_ink_centered, pixel_box
from widget.sprites import CHECK_GLYPH, sprite_image
from .fx import FxEngine
from .logic import DAYS, LOCKED, OPENED

S = PX                       # 캔버스 1픽셀 = 화면 PX(2) 픽셀
BOX_W, BOX_H = 44, 40
COLS, ROWS = 6, 4
OPEN_MS = 1100
# (몸통, 테두리, 리본)
GIFT_COLORS = [("#d63a3a", "#6e1520", "#f3c94a"), ("#2f8f4e", "#12422a", "#f5ead0"),
               ("#3d6fa8", "#1b3552", "#f5ead0"), ("#c767d6", "#5e2a6b", "#f3c94a")]
LOCK_COLORS = ("#2b3a40", "#141d21", "#46585f")


def mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t), int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def rect(p: QPainter, x: int, y: int, w: int, h: int, fill: str, edge: str):
    p.fillRect(x, y, w, h, QColor(edge))
    p.fillRect(x + 1, y + 1, w - 2, h - 2, QColor(fill))


class CalendarCanvas(QWidget):
    dayClicked = Signal(int)          # 열 수 있는 상자(개봉 가능/개봉 완료) 클릭
    lockedClicked = Signal(int)       # 잠긴 상자 클릭
    yearStep = Signal(int)            # -1 / +1
    openFinished = Signal(int)        # 개봉 애니메이션 종료

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(300, 200)
        self.f11 = pixel_font(11, 1)
        self.f14 = pixel_font(14, 1)
        # ---- 화면 상태 (window 가 set_view 로 갱신)
        self.year = 2026
        self.statuses: dict[int, str] = {d: LOCKED for d in range(1, DAYS + 1)}
        self.opened_count = 0
        self.can_prev = self.can_next = False
        self.hint_fn = lambda day: ""
        # ---- 상호작용 상태
        self._hover = 0
        self._hover_nav = 0                       # -1 / +1
        self._anim: QVariantAnimation | None = None
        self._anim_day = 0
        self._anim_t = 0.0
        self._burst: FxEngine | None = None
        self._deny_day = 0
        self._deny_clock = QElapsedTimer()
        self._msg = ""
        self._msg_clock = QElapsedTimer()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._t = 0.0
        self._snow = FxEngine("snowfall", 300, 200, duration=0)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ 외부 API
    def set_view(self, year, statuses, opened_count, can_prev, can_next):
        self.year, self.statuses = year, dict(statuses)
        self.opened_count, self.can_prev, self.can_next = opened_count, can_prev, can_next
        self.update()

    @property
    def animating(self) -> bool:
        return self._anim is not None

    def play_open(self, day: int, animate: bool = True):
        if self._anim is not None:
            return
        if not animate:
            self.openFinished.emit(day)
            return
        self._anim_day, self._anim_t = day, 0.0
        r = self._box_rect(day)
        self._burst = FxEngine("sparkle", *self._canvas_size(), duration=1.0)
        self._burst.origin = (r.center().x(), r.y() + 8)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(OPEN_MS)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._on_anim_done)
        self._anim.start()

    def show_message(self, text: str):
        self._msg = text
        self._msg_clock.restart()

    def showEvent(self, e):
        self._clock.restart()
        self._timer.start(33)

    def hideEvent(self, e):
        self._timer.stop()

    # ------------------------------------------------------------------ 기하
    def _canvas_size(self):
        return max(1, self.width() // S), max(1, self.height() // S)

    def _grid(self, cw, ch):
        pad, header = 6, 20
        top = pad + header
        return QRect(pad, top, cw - 2 * pad, ch - top - 16 - pad)

    def _cell_rect(self, day: int, cw=None, ch=None) -> QRect:
        cw, ch = (cw, ch) if cw else self._canvas_size()
        g = self._grid(cw, ch)
        w, h = g.width() // COLS, g.height() // ROWS
        i = day - 1
        return QRect(g.x() + (i % COLS) * w, g.y() + (i // COLS) * h, w, h)

    def _box_rect(self, day: int) -> QRect:
        c = self._cell_rect(day)
        return QRect(c.x() + (c.width() - BOX_W) // 2, c.y() + (c.height() - BOX_H) // 2, BOX_W, BOX_H)

    def _nav_rects(self, cw):
        y = 6
        return {-1: QRect(cw - 130, y, 11, 13), 1: QRect(cw - 80, y, 11, 13)}

    def _day_at(self, cx, cy) -> int:
        cw, ch = self._canvas_size()
        for d in range(1, DAYS + 1):
            if self._cell_rect(d, cw, ch).contains(cx, cy):
                return d
        return 0

    # ------------------------------------------------------------------ 타이머/애니메이션
    def _tick(self):
        dt = self._clock.restart() / 1000.0
        self._t += dt
        cw, ch = self._canvas_size()
        self._snow.resize(cw, ch)
        self._snow.step(dt)
        if self._burst is not None:
            self._burst.step(dt)
        self.update()

    def _on_anim(self, v):
        self._anim_t = float(v)

    def _on_anim_done(self):
        day = self._anim_day
        self._anim = None
        self._anim_t = 0.0
        self._burst = None
        self.openFinished.emit(day)

    # ------------------------------------------------------------------ 입력
    def _pos(self, e):
        pt = e.position()
        return int(pt.x()) // S, int(pt.y()) // S

    def mouseMoveEvent(self, e):
        cx, cy = self._pos(e)
        cw, _ = self._canvas_size()
        nav = 0
        for k, r in self._nav_rects(cw).items():
            if r.contains(cx, cy) and ((k < 0 and self.can_prev) or (k > 0 and self.can_next)):
                nav = k
        day = 0 if nav else self._day_at(cx, cy)
        if (day, nav) != (self._hover, self._hover_nav):
            self._hover, self._hover_nav = day, nav
            self.setCursor(Qt.PointingHandCursor if (day or nav) and not self.animating else Qt.ArrowCursor)

    def leaveEvent(self, e):
        self._hover = self._hover_nav = 0

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self.animating:
            return
        cx, cy = self._pos(e)
        cw, _ = self._canvas_size()
        for k, r in self._nav_rects(cw).items():
            if r.contains(cx, cy):
                if (k < 0 and self.can_prev) or (k > 0 and self.can_next):
                    self.yearStep.emit(k)
                return
        day = self._day_at(cx, cy)
        if not day:
            return
        if self.statuses.get(day) == LOCKED:
            self._deny_day = day
            self._deny_clock.restart()
            self.show_message(self.hint_fn(day))
            self.lockedClicked.emit(day)
        else:
            self.dayClicked.emit(day)

    # ------------------------------------------------------------------ 그리기
    def paintEvent(self, e):
        cw, ch = self._canvas_size()
        img = QImage(cw, ch, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        try:
            self._paint_canvas(p, cw, ch)
        finally:
            p.end()
        q = QPainter(self)
        q.drawImage(QRect(0, 0, cw * S, ch * S), img)
        q.end()

    def _paint_canvas(self, p: QPainter, cw: int, ch: int):
        pixel_box(p, QRect(0, 0, cw, ch), PAL["bg"], PAL["border"], lo=PAL["panel_lo"], u=1)
        for y in range(8, ch - 8, 6):                       # 은은한 점무늬 바탕
            for x in range(4 + (y // 6 % 2) * 3, cw - 4, 6):
                p.fillRect(x, y, 1, 1, QColor("#134032"))
        self._snow.paint(p, 0.55, unit=1)
        self._paint_header(p, cw)
        for d in range(1, DAYS + 1):
            self._paint_box(p, d)
        if self._burst is not None:
            self._burst.paint(p, 1.0, unit=1)
        self._paint_footer(p, cw, ch)

    def _paint_header(self, p, cw):
        g = sprite_image("gift", PAL["border"])
        p.drawImage(8, 7, g)
        p.setFont(self.f14)
        p.setPen(QColor(PAL["gold"]))
        fm = p.fontMetrics()
        p.drawText(8 + g.width() + 4, 6 + fm.ascent(), tr("어드벤트 캘린더"))
        # 연도 이동
        rects = self._nav_rects(cw)
        for k, r in rects.items():
            on = self.can_prev if k < 0 else self.can_next
            hot = self._hover_nav == k
            pixel_box(p, r, PAL["btn_hi"] if hot else (PAL["btn"] if on else PAL["btn_off"]), PAL["border"] if on else PAL["border_dark"], u=1)
            col = QColor(PAL["snow"] if on else PAL["dim"])
            for row in range(5):                         # 3x5 삼각형 (◀ ▶), 11x13 상자의 정중앙
                w = row + 1 if row < 3 else 5 - row
                x = r.x() + 7 - w if k < 0 else r.x() + 4
                p.fillRect(x, r.y() + 4 + row, w, 1, col)
        draw_ink_centered(p, QRect(rects[-1].right() + 1, 6, rects[1].x() - rects[-1].right() - 1, 13),
                          str(self.year), PAL["snow"], self.f14, bold=True)
        p.setFont(self.f11)
        txt = f"{self.opened_count}/{DAYS}"
        p.setPen(QColor(PAL["text"]))
        p.drawText(cw - 8 - p.fontMetrics().horizontalAdvance(txt), 7 + p.fontMetrics().ascent(), txt)
        icon = sprite_image("check", PAL["green"])
        p.drawImage(cw - 8 - p.fontMetrics().horizontalAdvance(txt) - icon.width() - 3, 9, icon)

    def _paint_footer(self, p, cw, ch):
        text = ""
        if self._msg and self._msg_clock.isValid() and self._msg_clock.elapsed() < 2200:
            text, col = self._msg, PAL["gold"]
        elif self._hover:
            text, col = self.hint_fn(self._hover), PAL["text"]
        else:
            col = PAL["dim"]
            text = tr("상자를 눌러 선물을 열어 보세요")
        draw_ink_centered(p, QRect(6, ch - 17, cw - 12, 13), text, col, self.f11)

    # ---- 선물 상자 한 개
    def _paint_box(self, p: QPainter, day: int):
        status = self.statuses.get(day, LOCKED)
        r = self._box_rect(day)
        x, y = r.x(), r.y()
        animating = self._anim is not None and self._anim_day == day
        t = self._anim_t if animating else 0.0
        dx = 0
        if animating and t < 0.3:                                   # 흔들림
            dx = (-2, 2)[int(t * 36) % 2]
        if self._deny_day == day and self._deny_clock.isValid() and self._deny_clock.elapsed() < 350:
            dx = (-1, 1)[int(self._deny_clock.elapsed() / 40) % 2]
        x += dx
        lid_dx = lid_dy = 0
        open_look = status == OPENED
        if animating and t >= 0.3:
            e = min(1.0, (t - 0.3) / 0.3)
            e = 1 - (1 - e) ** 3
            lid_dx, lid_dy, open_look = int(e * 5), -int(e * 12), True
        elif status == OPENED:
            lid_dx, lid_dy = 4, -6

        if status == LOCKED:
            body, edge, rib = LOCK_COLORS
        else:
            body, edge, rib = GIFT_COLORS[(day - 1) % 4]
            if status == OPENED and not animating:
                body, rib = mix(body, "#0b241d", 0.45), mix(rib, "#0b241d", 0.4)
        light = mix(body, "#ffffff", 0.22)

        # 몸통
        rect(p, x + 3, y + 16, 38, 24, body, edge)
        p.fillRect(x + 4, y + 17, 36, 1, QColor(light))
        p.fillRect(x + 4, y + 17, 1, 22, QColor(light))
        p.fillRect(x + 19, y + 17, 6, 22, QColor(rib))
        if open_look:                                               # 열린 틈의 빛
            p.fillRect(x + 4, y + 16, 36, 2, QColor("#fff1a8"))
            if lid_dy <= -6:
                p.fillRect(x + 10, y + 12, 24, 4, QColor(255, 241, 168, 110))
        # 뚜껑 + 리본 매듭
        lx, ly = x + 1 + lid_dx, y + 9 + lid_dy
        rect(p, lx, ly, 42, 8, body, edge)
        p.fillRect(lx + 1, ly + 1, 40, 1, QColor(light))
        p.fillRect(lx + 18, ly + 1, 6, 6, QColor(rib))
        rect(p, lx + 10, ly - 5, 10, 6, rib, edge)
        rect(p, lx + 22, ly - 5, 10, 6, rib, edge)
        rect(p, lx + 18, ly - 3, 6, 5, mix(rib, "#000000", 0.25), edge)
        # 번호표
        plate = QRect(x + 13, y + 22, 18, 12)
        locked = status == LOCKED
        rect(p, plate.x(), plate.y(), plate.width(), plate.height(), "#1d2a2e" if locked else "#f5ead0",
             "#33454b" if locked else "#b9a67a")
        draw_ink_centered(p, plate, str(day), "#6f8580" if locked else "#4a2c18", self.f11)
        # 상태 표식
        if locked:
            p.drawImage(x + 34, y + 1, sprite_image("lock", "#7d9a92"))
        elif status == OPENED and not animating:
            rect(p, x + 33, y, 11, 11, "#2f8f4e", PAL["border"])
            gx, gy = x + 33 + 1 + (9 - 7) // 2, y + 1 + (9 - 5) // 2
            for rr, line in enumerate(CHECK_GLYPH):
                for cc, ch_ in enumerate(line):
                    if ch_ == "#":
                        p.fillRect(gx + cc, gy + rr, 1, 1, QColor(PAL["snow"]))
        elif not animating:                                         # 개봉 가능: 반짝 테두리 + 별빛
            pulse = int(self._t * 2.5) % 2 == 0
            c = QColor("#f3c94a" if pulse else "#fff1a8")
            p.fillRect(x - 1, y + 1, BOX_W + 2, 1, c)
            p.fillRect(x - 1, y + BOX_H + 1, BOX_W + 2, 1, c)
            p.fillRect(x - 1, y + 1, 1, BOX_H + 1, c)
            p.fillRect(x + BOX_W, y + 1, 1, BOX_H + 1, c)
            if int(self._t * 2 + day) % 3 == 0:
                p.drawImage(x + 36, y - 3, sprite_image("sparkle", PAL["gold"]))
        if self._hover == day and not animating:
            c = QColor(PAL["snow"] if not locked else "#a9bfae")
            p.fillRect(x - 2, y, BOX_W + 4, 1, c)
            p.fillRect(x - 2, y + BOX_H + 2, BOX_W + 4, 1, c)
            p.fillRect(x - 2, y, 1, BOX_H + 3, c)
            p.fillRect(x + BOX_W + 1, y, 1, BOX_H + 3, c)
