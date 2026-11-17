from __future__ import annotations
from core.i18n import tr


import math
from datetime import datetime

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QMenu, QWidget

from core.dday import date_text, days_until_christmas, dday_text, next_christmas
from core.fonts import pixel_font
from core.logger import get_logger
from . import winz
from .pixel_ui import PAL, ink_rect, pixel_box
from .sprites import sprite_icon, sprite_image

log = get_logger("widget")

MIN_W, MIN_H = 260, 300
BTN = 13                 # 캔버스 픽셀 단위 버튼 크기
HEADER_H = 18
LIGHT_COLORS = ("#d63a3a", "#f3c94a", "#4fb66b", "#8fd0f5")


def _col(name: str) -> QColor:
    return QColor(PAL.get(name, name))


class MainWidget(QWidget):
    """저해상도 캔버스(QImage)에 픽셀 단위로 그린 뒤 정수 배로 최근접 확대해서 표시한다."""

    open_settings = Signal()
    open_calendar = Signal()
    open_advent = Signal()
    open_snowglobe = Signal()
    open_music = Signal()
    open_wind = Signal()
    open_snowman = Signal()
    request_quit = Signal()
    clean_snow = Signal()
    reset_snow = Signal()

    def __init__(self, settings, audio):
        super().__init__(None)
        self.settings = settings
        self.audio = audio
        self._drag_offset: QPoint | None = None
        self._resize_start = None
        self._hover = False
        self._menu_open = False
        self._applying = False
        self._mode = None
        self._hover_btn = -1
        self._press_btn = -1
        self._t = 0.0
        self.f11 = pixel_font(11)
        self.f14 = pixel_font(14)

        self.setWindowTitle("Christmas Wonderland")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(MIN_W, MIN_H)
        self.setMouseTracking(True)

        self._clock = QElapsedTimer()
        self._clock.start()
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(66)

        self._keeper = QTimer(self)
        self._keeper.setInterval(3000)
        self._keeper.timeout.connect(lambda: winz.send_to_bottom(self))

        self._geom_timer = QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.setInterval(400)
        self._geom_timer.timeout.connect(self._store_geometry)

        self._load_geometry()
        self.settings.changed.connect(self._on_setting)

    # ------------------------------------------------------------------ 기하
    def _scale(self) -> int:
        return max(1, min(round(self.width() / 140), round(self.height() / 160)))

    def _screens_rect(self) -> list[QRect]:
        return [s.availableGeometry() for s in QGuiApplication.screens()]

    def _load_geometry(self):
        w = int(self.settings.get("widget.width"))
        h = int(self.settings.get("widget.height"))
        x, y = self.settings.get("widget.x"), self.settings.get("widget.y")
        rect = QRect(int(x) if x is not None else 0, int(y) if y is not None else 0, w, h)
        visible = x is not None and y is not None and any(
            (r.intersected(rect).width() >= 100 and r.intersected(rect).height() >= 60)
            for r in self._screens_rect())
        if not visible:
            primary = QGuiApplication.primaryScreen().availableGeometry()
            w, h = min(w, primary.width() - 40), min(h, primary.height() - 40)
            rect = QRect(primary.right() - w - 40, primary.top() + 60, w, h)
        self.setGeometry(rect)

    def center_on_screen(self):
        primary = QGuiApplication.primaryScreen().availableGeometry()
        self.move(primary.center() - QPoint(self.width() // 2, self.height() // 2))
        self._store_geometry()

    # ------------------------------------------------------------------ 창 모드
    def apply_mode(self, mode: str | None = None):
        mode = mode or self.settings.get("widget.mode")
        geo = self.geometry()
        self._applying = True
        self._mode = mode
        was_visible = self.isVisible()

        flags = Qt.FramelessWindowHint
        # 창 유형은 항상 Qt.Window 로 유지한다. 작업표시줄 버튼만 Win32 확장 스타일로 제어해
        # Qt.Tool 전환에 따른 Z-order / 창 동작 변화를 피한다.
        flags |= Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint
        if mode == "bottom" and not winz.IS_WINDOWS:
            flags |= Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, mode == "bottom")
        self.setGeometry(geo)
        self.show()
        winz.set_taskbar_visible(self, bool(self.settings.get("app.show_taskbar")))
        if mode == "bottom":
            winz.send_to_bottom(self)
            if winz.IS_WINDOWS:
                self._keeper.start()
        else:
            self._keeper.stop()
            if not was_visible:
                self.activateWindow()
        self._applying = False
        log.info("창 모드: %s", mode)

    def nativeEvent(self, eventType, message):
        if self._mode == "bottom" and winz.IS_WINDOWS:
            try:
                if bytes(eventType) == b"windows_generic_MSG":
                    winz.force_bottom_on_message(message)
            except Exception:
                pass
        return False, 0

    def show_from_tray(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        if self._mode == "bottom":
            winz.send_to_bottom(self)
        else:
            self.raise_()
            self.activateWindow()

    # ------------------------------------------------------------------ 설정 반응
    def _on_setting(self, key: str):
        if key == "*":
            self._load_geometry()
            self.apply_mode()
            return
        if key == "widget.mode":
            if self.settings.get("widget.mode") != self._mode:
                self.apply_mode()
        elif key == "app.show_taskbar":
            self.apply_mode()
        elif key in ("widget.width", "widget.height"):
            w, h = int(self.settings.get("widget.width")), int(self.settings.get("widget.height"))
            if (w, h) != (self.width(), self.height()):
                self.resize(w, h)
        self.update()

    def _tick(self):
        dt = self._clock.restart() / 1000.0
        if self.isMinimized() or not self.isVisible():
            return
        self._t += dt
        self.update()

    # ------------------------------------------------------------------ 이벤트
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._hover_btn = -1
        self.update()

    def resizeEvent(self, e):
        if not self._applying:
            self._geom_timer.start()

    def moveEvent(self, e):
        if not self._applying:
            self._geom_timer.start()

    def _store_geometry(self):
        if self._applying or self.isMinimized() or not self.isVisible():
            return
        g = self.geometry()
        s = self.settings
        s.set("widget.x", g.x())
        s.set("widget.y", g.y())
        s.set("widget.width", g.width())
        s.set("widget.height", g.height())

    # ---- 버튼 / 그립 히트 테스트 (캔버스 좌표)
    def _buttons(self, cw: int) -> list:
        items = [("menu", "menu")]
        if self._mode != "bottom":
            items.append(("min", "minus"))
        items.append(("close", "close"))
        x = cw - 3 - BTN
        out = []
        for name, icon in reversed(items):
            out.append((name, icon, QRect(x, 3, BTN, BTN)))
            x -= BTN + 2
        return out

    def _grip_rect(self, cw: int, ch: int) -> QRect:
        return QRect(cw - 11, ch - 11, 9, 9)

    def _canvas_pos(self, e) -> QPoint:
        s = self._scale()
        pt = e.position().toPoint()
        return QPoint(pt.x() // s, pt.y() // s)

    def _button_at(self, cp: QPoint) -> int:
        if not (self._hover or self._menu_open):
            return -1
        cw = self.width() // self._scale()
        for i, (_n, _i, r) in enumerate(self._buttons(cw)):
            if r.contains(cp):
                return i
        return -1

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            super().mousePressEvent(e)
            return
        cp = self._canvas_pos(e)
        s = self._scale()
        cw, ch = self.width() // s, self.height() // s
        b = self._button_at(cp)
        if b >= 0:
            self._press_btn = b
            e.accept()
            return
        locked = bool(self.settings.get("widget.locked"))
        if not locked and self._hover and self._grip_rect(cw, ch).contains(cp):
            self._resize_start = (e.globalPosition().toPoint(), self.size())
            e.accept()
            return
        if not locked:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._resize_start is not None and (e.buttons() & Qt.LeftButton):
            start, size = self._resize_start
            d = e.globalPosition().toPoint() - start
            self.resize(max(MIN_W, size.width() + d.x()), max(MIN_H, size.height() + d.y()))
            e.accept()
            return
        if self._drag_offset is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()
            return
        cp = self._canvas_pos(e)
        s = self._scale()
        cw, ch = self.width() // s, self.height() // s
        hb = self._button_at(cp)
        if hb != self._hover_btn:
            self._hover_btn = hb
            self.update()
        locked = bool(self.settings.get("widget.locked"))
        if hb >= 0:
            self.setCursor(Qt.PointingHandCursor)
        elif not locked and self._hover and self._grip_rect(cw, ch).contains(cp):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor if locked else Qt.SizeAllCursor)

    def mouseReleaseEvent(self, e):
        if self._press_btn >= 0:
            cp = self._canvas_pos(e)
            hit = self._button_at(cp)
            pressed, self._press_btn = self._press_btn, -1
            if hit == pressed:
                self._run_button(pressed)
            e.accept()
            return
        if self._drag_offset is not None or self._resize_start is not None:
            self._drag_offset = None
            self._resize_start = None
            self._geom_timer.stop()
            self._store_geometry()
            self.settings.save_now()
            e.accept()

    def _run_button(self, idx: int):
        cw = self.width() // self._scale()
        name = self._buttons(cw)[idx][0]
        if name == "menu":
            self._popup_menu(self.mapToGlobal(QPoint(self.width() - 20, 60)))
        elif name == "min":
            self.showMinimized()
        elif name == "close":
            self.request_quit.emit()

    def contextMenuEvent(self, e):
        self._popup_menu(e.globalPos())

    def closeEvent(self, e):
        e.accept()
        self.request_quit.emit()

    # ------------------------------------------------------------------ 빠른 메뉴
    def _popup_menu(self, pos):
        menu = self.build_menu()
        self._menu_open = True
        self.update()
        menu.exec(pos)
        self._menu_open = False
        self.update()

    def build_menu(self) -> QMenu:
        s = self.settings
        menu = QMenu(self)

        m_music = menu.addMenu(sprite_icon("note"), tr("음악"))
        m_music.addAction(sprite_icon("pause" if self.audio.is_playing else "play"),
                          tr("일시정지") if self.audio.is_playing else tr("재생"), self.audio.toggle)
        m_music.addAction(sprite_icon("prev"), tr("이전 곡"), self.audio.prev)
        m_music.addAction(sprite_icon("next"), tr("다음 곡"), self.audio.next)
        m_music.addSeparator()
        m_music.addAction(tr("음악 플레이어 열기"), self.open_music.emit)
        title = self.audio.current_title()
        if title:
            t = m_music.addAction(tr("현재: {0}").format(title))
            t.setEnabled(False)

        m_snow = menu.addMenu(sprite_icon("snow"), tr("눈"))
        self._check(m_snow, tr("눈 효과 사용"), "snow.enabled", save=True)
        m_snow.addAction(sprite_icon("wind"), tr("바람 조절 창"), self.open_wind.emit)
        m_snow.addAction(sprite_icon("snow"), tr("눈사람 공방 (눈덩이/눈사람)"), self.open_snowman.emit)
        m_snow.addAction(sprite_icon("wind"), tr("무풍"), lambda: self._calm())
        m_snow.addAction(sprite_icon("trash"), tr("쌓인 눈 청소"), self.clean_snow.emit)
        m_snow.addAction(sprite_icon("reset"), tr("눈 시뮬레이션 초기화"), self.reset_snow.emit)

        m_show = menu.addMenu(sprite_icon("clock"), tr("표시 요소"))
        self._check(m_show, tr("시계"), "widget.show_clock")
        self._check(m_show, tr("날짜"), "widget.show_date")
        self._check(m_show, tr("크리스마스 D-Day"), "widget.show_dday")
        self._check(m_show, tr("트리"), "widget.show_tree")
        self._check(m_show, tr("선물 상자"), "widget.show_gift")
        self._check(m_show, tr("별과 반짝임"), "widget.show_sparkle")

        m_op = menu.addMenu(tr("투명도"))
        grp = QActionGroup(m_op)
        cur = round(float(s.get("widget.opacity")) * 100)
        for pct in (100, 80, 60, 40):
            a = m_op.addAction(f"{pct}%")
            a.setCheckable(True)
            a.setChecked(abs(cur - pct) < 5)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, p=pct: s.set("widget.opacity", p / 100.0))

        m_mode = menu.addMenu(tr("창 표시 모드"))
        grp2 = QActionGroup(m_mode)
        for value, label in (("normal", tr("일반 창")), ("bottom", tr("항상 아래 창"))):
            a = m_mode.addAction(label)
            a.setCheckable(True)
            a.setChecked(s.get("widget.mode") == value)
            grp2.addAction(a)
            a.triggered.connect(lambda _=False, v=value: s.set("widget.mode", v, save=True))

        self._check(menu, tr("위젯 잠금"), "widget.locked", save=True, icon="lock")
        menu.addSeparator()
        menu.addAction(sprite_icon("gift"), tr("어드벤트 캘린더"), self.open_advent.emit)
        menu.addAction(sprite_icon("calendar"), tr("캘린더 열기"), self.open_calendar.emit)
        menu.addAction(sprite_icon("globe"), tr("스노우볼 열기"), self.open_snowglobe.emit)
        menu.addAction(sprite_icon("gear"), tr("설정"), self.open_settings.emit)
        menu.addAction(sprite_icon("save"), tr("지금 저장"), lambda: s.save_now(manual=True))
        menu.addSeparator()
        if self._mode != "bottom":
            menu.addAction(sprite_icon("minus"), tr("최소화"), self.showMinimized)
        menu.addAction(sprite_icon("close"), tr("종료"), self.request_quit.emit)
        return menu

    def _calm(self):
        self.settings.set("wind.strength", 0, save=True)

    def _check(self, menu, label, key, save=False, icon=None):
        on = bool(self.settings.get(key))
        a = menu.addAction(sprite_icon(icon or ("check" if on else "box")), label)
        if icon:
            a.setText(f"{label}  ({tr('켜짐') if on else tr('꺼짐')})")
        a.triggered.connect(lambda _=False, k=key, v=not on: self.settings.set(k, v, save=save))

    # ------------------------------------------------------------------ 그리기
    def paintEvent(self, e):
        s = self._scale()
        cw, ch = max(1, self.width() // s), max(1, self.height() // s)
        img = QImage(cw, ch, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        try:
            self._paint_canvas(p, cw, ch, datetime.now())
        finally:
            p.end()
        q = QPainter(self)
        q.setOpacity(float(self.settings.get("widget.opacity")))
        q.drawImage(QRect(0, 0, cw * s, ch * s), img)         # 최근접 확대 (스무딩 없음)
        q.end()

    def _text(self, p, x, y, text, color, font, shadow="#06150f", bold=False, outline=None):
        p.setFont(font)
        fm = p.fontMetrics()
        base = y + fm.ascent()
        if outline:
            p.setPen(QColor(outline))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                p.drawText(x + dx, base + dy, text)
                if bold:
                    p.drawText(x + dx + 1, base + dy, text)
        if shadow:
            p.setPen(QColor(shadow))
            p.drawText(x + 1, base + 1, text)
            if bold:
                p.drawText(x + 2, base + 1, text)
        p.setPen(QColor(color))
        p.drawText(x, base, text)
        if bold:
            p.drawText(x + 1, base, text)

    def _centered(self, p, cw, y, text, color, font, **kw):
        p.setFont(font)
        w = p.fontMetrics().horizontalAdvance(text) + (1 if kw.get("bold") else 0)
        self._text(p, (cw - w) // 2, y, text, color, font, **kw)
        return w

    def _paint_canvas(self, p, cw, ch, now):
        s = self.settings
        t = self._t
        # ---- 카드 바탕
        pixel_box(p, QRect(0, 0, cw, ch), PAL["panel"], PAL["border"], u=1)
        p.fillRect(1, 1, cw - 2, 1, _col("#2a6b55"))
        p.fillRect(1, 2, 1, ch - 4, _col("#1d5a47"))
        p.fillRect(2, ch - 3, cw - 4, 1, _col("panel_lo"))
        p.fillRect(cw - 3, 2, 1, ch - 4, _col("panel_lo"))
        for y in range(HEADER_H + 6, ch - 12, 6):          # 은은한 점무늬 (벽지)
            for x in range(4 + (y // 6 % 2) * 3, cw - 4, 6):
                p.fillRect(x, y, 1, 1, _col("#1a5040"))
        self._paint_snow_cap(p, cw)
        self._paint_garland(p, cw, t)

        sparkle = bool(s.get("widget.show_sparkle"))
        has_deco = bool(s.get("widget.show_tree") or s.get("widget.show_gift"))
        bottom_reserve = 36 if has_deco else 10
        self._paint_hill(p, cw, ch)
        if sparkle:
            self._paint_sparkles(p, cw, ch, t)

        # ---- 콘텐츠 블록
        blocks = []
        if s.get("widget.show_clock"):
            blocks.append(("clock", 16))
        if s.get("widget.show_date"):
            blocks.append(("date", 12))
        if s.get("widget.show_dday"):
            blocks.append(("dday", 47))
        if blocks:
            gap = 8
            total = sum(b[1] for b in blocks) + gap * (len(blocks) - 1)
            top, bottom = HEADER_H + 2, ch - bottom_reserve
            y = top + max(0, (bottom - top - total) // 2)
            for kind, bh in blocks:
                if kind == "clock":
                    self._paint_clock(p, cw, y, now)
                elif kind == "date":
                    self._paint_date(p, cw, y, now)
                else:
                    self._paint_dday(p, cw, y, now)
                y += bh + gap

        # ---- 장식
        self._paint_decor(p, cw, ch, t)
        if sparkle:
            self._paint_flakes(p, cw, ch, t)
        self._paint_controls(p, cw, ch)

    # ---- 카드 장식 요소
    def _paint_snow_cap(self, p, cw):
        for x in range(1, cw - 1):
            h = 1 + (1 if (x * 7 + x // 5) % 9 < 4 else 0) + (1 if (x // 3) % 7 == 0 else 0)
            p.fillRect(x, 0, 1, h, _col("snow"))

    def _paint_garland(self, p, cw, t):
        period = 28.0
        for x in range(3, cw - 3):
            y = 6 + int(round(2.4 * math.sin((x % period) / period * math.pi)))
            p.fillRect(x, y, 1, 1, _col("#0b241d"))
        for i, x in enumerate(range(8, cw - 8, 14)):
            y = 6 + int(round(2.4 * math.sin(((x % period) / period) * math.pi)))
            color = QColor(LIGHT_COLORS[i % 4])
            on = (int(t * 2.2) + i) % 3 != 0
            if not on:
                color = color.darker(190)
            p.fillRect(x, y + 1, 2, 1, _col("#0b241d"))
            p.fillRect(x - 1, y + 2, 4, 3, color)
            p.fillRect(x, y + 5, 2, 1, color)
            if on:
                p.fillRect(x, y + 2, 1, 1, QColor(255, 255, 255, 190))

    def _paint_hill(self, p, cw, ch):
        for x in range(2, cw - 2):
            y = ch - 7 + int(round(1.5 * math.sin(x * 0.17) + 1.2 * math.sin(x * 0.41 + 1)))
            p.fillRect(x, y, 1, ch - 3 - y, _col("snow"))
            p.fillRect(x, y + 2, 1, 1, _col("#dcecf8"))
            if y + 4 < ch - 3:
                p.fillRect(x, ch - 4, 1, 1, _col("#b9d3ea"))

    def _paint_sparkles(self, p, cw, ch, t):
        pts = ((9, 30), (cw - 12, 38), (12, 78), (cw - 10, 92), (cw // 2 + 28, 24), (7, 120), (cw - 14, 128))
        for i, (x, y) in enumerate(pts):
            if y > ch - 40:
                continue
            ph = int(t * 1.6 + i * 1.3) % 4
            if ph == 0:
                continue
            img = sprite_image("sparkle" if ph != 2 else "star")
            if ph == 1:
                p.fillRect(x, y, 1, 1, _col("gold"))
            else:
                p.drawImage(x - img.width() // 2, y - img.height() // 2, img)

    def _paint_flakes(self, p, cw, ch, t):
        """카드 안쪽의 작은 장식용 눈송이 (데스크톱 눈과는 별개)."""
        n = 16
        for i in range(n):
            seed = i * 37.17
            speed = 5 + (i % 4) * 2
            x = (seed * 3.1 + math.sin(t * 0.8 + i) * 4 + (i * 17) % (cw - 6)) % (cw - 6) + 3
            y = ((t * speed + seed * 5.0) % (ch - 16)) + 9
            size = 2 if i % 5 == 0 else 1
            p.fillRect(int(x), int(y), size, size, QColor(255, 255, 255, 200 if size == 2 else 140))

    def _paint_decor(self, p, cw, ch, t):
        s = self.settings
        if s.get("widget.show_tree"):
            tree = sprite_image("tree")
            tx = 8 if s.get("widget.show_gift") else (cw - tree.width()) // 2
            p.drawImage(tx, ch - 6 - tree.height(), tree)
        if s.get("widget.show_gift"):
            g1, g2 = sprite_image("gift_red"), sprite_image("gift_blue")
            gx = cw - 8 - g1.width()
            p.drawImage(gx, ch - 5 - g1.height(), g1)
            p.drawImage(gx - g2.width() - 3, ch - 5 - g2.height() + 2, g2)

    # ---- 텍스트 블록
    def _paint_clock(self, p, cw, y, now):
        s = self.settings
        p.setFont(self.f14)
        fm = p.fontMetrics()
        adv = max(fm.horizontalAdvance(c) for c in "0123456789") + 1      # 숫자 고정 폭
        colon = fm.horizontalAdvance(":") + 1
        h24 = bool(s.get("widget.clock_24h"))
        hour = now.hour if h24 else (now.hour % 12 or 12)
        chars = f"{hour:02d}:{now.minute:02d}" + (f":{now.second:02d}" if s.get("widget.show_seconds") else "")
        width = sum(colon if c == ":" else adv for c in chars)
        suffix = "" if h24 else (tr("오전") if now.hour < 12 else tr("오후"))
        sw = 0
        if suffix:
            p.setFont(self.f11)
            sw = p.fontMetrics().horizontalAdvance(suffix) + 3
        x = (cw - width - sw) // 2 + sw
        if suffix:
            self._text(p, x - sw, y + 4, suffix, PAL["gold"], self.f11)
        for c in chars:
            w = colon if c == ":" else adv
            self._text(p, x + (w - fm.horizontalAdvance(c) - 1) // 2, y, c, PAL["snow"], self.f14, bold=True)
            x += w

    def _paint_date(self, p, cw, y, now):
        text = date_text(now.date())
        p.setFont(self.f11)
        if p.fontMetrics().horizontalAdvance(text) > cw - 10:
            text = tr("{0}월 {1}일 {2}").format(now.month, now.day, text[-3:])
        self._centered(p, cw, y, text, PAL["text"], self.f11)

    def _paint_dday(self, p, cw, y, now):
        n = days_until_christmas(now.date())
        label = tr("메리 크리스마스!") if n == 0 else tr("크리스마스까지")
        self._centered(p, cw, y, label, PAL["gold"], self.f11)
        text = dday_text(now.date())
        ink = ink_rect(self.f14, text, bold=True)
        bh = max(21, ink.height() + 8)
        bw = max(ink.width() + 16, 52)
        if (cw - bw) % 2:                         # 카드 좌우 여백이 같도록 폭을 짝수 맞춤
            bw += 1
        box = QRect((cw - bw) // 2, y + 14, bw, bh)
        pixel_box(p, box, PAL["red_dark"], PAL["gold"], hi="#c0343f", lo="#5e1119", u=1)
        inner = box.adjusted(2, 2, -2, -2)        # 테두리 1px + 베벨 1px 을 뺀 실제 채움 영역
        tx = inner.x() + (inner.width() - ink.width()) // 2 - ink.x()
        ty = inner.y() + (inner.height() - ink.height()) // 2 - ink.y()
        self._text(p, tx, ty, text, PAL["snow"], self.f14, shadow="#3b0a10", bold=True)
        xm = next_christmas(now.date())
        self._centered(p, cw, y + 14 + bh + 3, tr("{0}년 12월 25일").format(xm.year), PAL["dim"], self.f11)

    # ---- 호버 컨트롤
    def _paint_controls(self, p, cw, ch):
        show = self._hover or self._menu_open
        if not show:
            return
        for i, (_name, icon, r) in enumerate(self._buttons(cw)):
            hot = i == self._hover_btn
            danger = _name == "close"
            fill = (PAL["red"] if danger else PAL["btn_hi"]) if hot else ("#5e1119" if danger else PAL["btn"])
            pixel_box(p, r, fill, PAL["border"], u=1)
            img = sprite_image(icon, PAL["snow"])
            p.drawImage(r.x() + (r.width() - img.width()) // 2, r.y() + (r.height() - img.height()) // 2, img)
        locked = bool(self.settings.get("widget.locked"))
        if locked:
            img = sprite_image("lock", PAL["gold"])
            p.drawImage(4, 4, img)
        else:
            g = self._grip_rect(cw, ch)
            p.drawImage(g.x(), g.y(), sprite_image("grip", PAL["border"]))
