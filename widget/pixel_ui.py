"""픽셀 디자인 시스템: 팔레트, 픽셀 프레임, 버튼/체크/슬라이더/탭/창 프레임, 전역 스타일시트.

모든 도형은 PX(=2) 픽셀 단위의 정수 격자에 맞춰 그리며, 둥근 모서리 대신 계단식(notch) 모서리를 쓴다.
텍스트는 Galmuri11 의 정수 배(22px)로 그려 픽셀이 흐려지지 않는다.
"""
from __future__ import annotations
from core.i18n import tr


import time

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QKeyEvent, QPainter
from PySide6.QtWidgets import QAbstractButton, QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.confirm import TwoStep
from core.fonts import pixel_font
from core.nav import nav_target
from .sprites import CHECK_GLYPH, sprite_pixmap

PX = 2

PAL = {
    "bg": "#0f2f26", "panel": "#154436", "panel_hi": "#1d5a47", "panel_lo": "#0b241d",
    "border": "#f3e6c4", "border_dark": "#b9a67a", "text": "#f5ead0", "dim": "#a9bfae",
    "gold": "#f3c94a", "red": "#d63a3a", "red_dark": "#8f1f2a", "sky": "#8fd0f5",
    "snow": "#ffffff", "green": "#4fb66b", "shadow": "#06150f",
    "btn": "#1f6b50", "btn_hi": "#2e8a68", "btn_down": "#16513c", "btn_off": "#25382f",
}


def C(name: str) -> QColor:
    return QColor(PAL.get(name, name))


def body_font(scale: int = 2):
    return pixel_font(11, scale)


def head_font(scale: int = 2):
    return pixel_font(14, scale)


def pixel_box(p: QPainter, r: QRect, fill, border, hi=None, lo=None, u: int = PX):
    """모서리가 계단식인 픽셀 상자. border 는 u 두께, hi/lo 는 안쪽 밝은/어두운 1단 베벨."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    if w < 4 * u or h < 4 * u:
        p.fillRect(r, QColor(fill))
        return
    p.fillRect(x + u, y + u, w - 2 * u, h - 2 * u, QColor(fill))
    b = QColor(border)
    p.fillRect(x + u, y, w - 2 * u, u, b)
    p.fillRect(x + u, y + h - u, w - 2 * u, u, b)
    p.fillRect(x, y + u, u, h - 2 * u, b)
    p.fillRect(x + w - u, y + u, u, h - 2 * u, b)
    if hi is not None:
        p.fillRect(x + u, y + u, w - 2 * u, u, QColor(hi))
        p.fillRect(x + u, y + u, u, h - 2 * u, QColor(hi))
    if lo is not None:
        p.fillRect(x + u, y + h - 2 * u, w - 2 * u, u, QColor(lo))
        p.fillRect(x + w - 2 * u, y + u, u, h - 2 * u, QColor(lo))


_INK_CACHE: dict = {}


def ink_rect(font, text: str, bold: bool = False) -> QRect:
    """글자가 실제로 칠해지는 픽셀 영역. _text(x, y, ...) 의 (x, y) 기준 상대 좌표로 돌려준다.

    폰트의 ascent/advance 는 글자 잉크와 어긋날 수 있어(좌우 베어링, 아래 여백 등),
    상자 안 중앙 정렬은 폰트 지표 대신 실제로 그려 본 결과로 계산한다.
    """
    key = (font.family(), font.pixelSize(), text, bold)
    hit = _INK_CACHE.get(key)
    if hit is not None:
        return hit
    fm = QFontMetrics(font)
    pad = 4
    w, h = fm.horizontalAdvance(text) + 2 * pad + 2, fm.height() + 2 * pad
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(0)
    q = QPainter(img)
    q.setFont(font)
    q.setPen(QColor(255, 255, 255))
    base = pad + fm.ascent()
    q.drawText(pad, base, text)
    if bold:
        q.drawText(pad + 1, base, text)
    q.end()
    x0, y0, x1, y1 = w, h, -1, -1
    for yy in range(h):
        for xx in range(w):
            if img.pixelColor(xx, yy).alpha() > 0:
                x0, y0, x1, y1 = min(x0, xx), min(y0, yy), max(x1, xx), max(y1, yy)
    rect = QRect(x0 - pad, y0 - pad, x1 - x0 + 1, y1 - y0 + 1) if x1 >= 0 else QRect(0, 0, fm.horizontalAdvance(text), fm.height())
    _INK_CACHE[key] = rect
    return rect




def draw_ink_centered(p: QPainter, rect: QRect, text: str, color, font, bold: bool = False):
    """글자의 실제 잉크 영역을 rect 한가운데에 맞춰 그린다 (폰트 지표 오차 없이 상자 안 중앙 정렬)."""
    ink = ink_rect(font, text, bold)
    fm = QFontMetrics(font)
    tx = rect.x() + (rect.width() - ink.width()) // 2 - ink.x()
    ty = rect.y() + (rect.height() - ink.height()) // 2 - ink.y()
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(tx, ty + fm.ascent(), text)
    if bold:
        p.drawText(tx + 1, ty + fm.ascent(), text)


# ====================================================================== 버튼
class PixelButton(QAbstractButton):
    def __init__(self, text: str = "", icon: str | None = None, parent=None, kind: str = "normal"):
        super().__init__(parent)
        self.setText(text)
        self._icon = icon
        self._kind = kind          # normal | accent | danger | flat
        self.setFont(body_font())
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._hover = False

    def set_icon(self, name: str | None):
        self._icon = name
        self.update()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(self.text()) + 12 * PX
        if self._icon:
            w += 9 * PX + (3 * PX if self.text() else 0)
        return QSize(max(w, 14 * PX), 17 * PX)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()        # 레이아웃이 글자 폭보다 좁게 줄이지 못하게 해 글자 잘림 방지

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        down = self.isDown() or self.isChecked()
        if not self.isEnabled():
            fill, hi, lo, txt = "btn_off", None, None, "dim"
        elif self._kind == "danger":
            fill, hi, lo, txt = ("red_dark" if down else "red"), "#ff7a6e", "#5e1119", "snow"
        elif self._kind == "accent":
            fill, hi, lo, txt = ("y" if down else "gold"), "#fff1a8", "#b8862a", "shadow"
        elif self._kind == "flat":
            fill, hi, lo, txt = ("btn_down" if down else ("btn_hi" if self._hover else "panel")), None, None, "text"
        else:
            fill = "btn_down" if down else ("btn_hi" if self._hover else "btn")
            hi, lo, txt = ("#3aa57f" if not down else None), "#0f3f2e", "text"
        fillc = PAL.get(fill, fill)
        pixel_box(p, r, fillc, PAL["border"] if self.hasFocus() or self._hover else PAL["border_dark"],
                  hi=None if down else hi, lo=lo)
        off = PX if down else 0
        content = r.adjusted(0, off, 0, off)
        p.setFont(self.font())
        x = r.x()
        tw = self.fontMetrics().horizontalAdvance(self.text())
        iw = 9 * PX if self._icon else 0
        total = tw + iw + (3 * PX if (self._icon and self.text()) else 0)
        x = r.x() + (r.width() - total) // 2
        if self._icon:
            main = PAL[txt] if txt in PAL else txt
            pm = sprite_pixmap(self._icon, PX, main=main)
            p.drawPixmap(x, r.y() + (r.height() - pm.height()) // 2 + off, pm)
            x += iw + 3 * PX
        if self.text():
            p.setPen(C(txt))
            p.drawText(QRect(x, content.y(), tw + 2, content.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()



class ConfirmButton(PixelButton):
    """되돌릴 수 없는 삭제용 버튼: 첫 클릭은 글자가 '정말 삭제?' 로 바뀌며 대기, 제한 시간 안에 같은 대상으로 한 번 더 누르면 `confirmed`.

    key_fn: 현재 대상(선택한 항목)을 돌려주는 함수. 대기 중에 대상이 바뀌면 두 번째 클릭은 새 대상의 첫 클릭으로 취급한다.
    글자 폭이 달라져도 좁은 칸에서 잘리지 않도록 확인 글자는 짧게 둔다.
    """
    confirmed = Signal()

    def __init__(self, text: str = "", icon: str | None = None, parent=None, kind: str = "danger",
                 confirm_text: str = tr("정말 삭제?"), timeout: float = 3.0, key_fn=None):
        super().__init__(text, icon, parent, kind)
        self._text0 = text
        self._confirm_text = confirm_text
        self._key_fn = key_fn
        self._step = TwoStep(timeout)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.disarm)
        self.clicked.connect(self._on_click)

    def _key(self):
        return self._key_fn() if self._key_fn else None

    def _on_click(self):
        if self._step.press(self._key(), time.monotonic()):
            self.disarm()
            self.confirmed.emit()
        else:
            self.setText(self._confirm_text)
            self._timer.start(int(self._step.window * 1000))

    def is_armed(self) -> bool:
        return self._step.is_armed(self._key(), time.monotonic())

    def disarm(self):
        """대기 상태 해제 (대상이 바뀌었거나 창이 닫히거나 시간이 지났을 때)."""
        self._step.reset()
        self._timer.stop()
        if self.text() != self._text0:
            self.setText(self._text0)

    def hideEvent(self, e):
        self.disarm()
        super().hideEvent(e)

    def changeEvent(self, e):
        if e.type() == QEvent.EnabledChange and not self.isEnabled():
            self.disarm()
        super().changeEvent(e)

# ====================================================================== 체크박스
class PixelCheck(QAbstractButton):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setFont(body_font())
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._hover = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        text_width = max(24, width - 16 * PX)
        bounds = self.fontMetrics().boundingRect(QRect(0, 0, text_width, 10000), Qt.TextWordWrap, self.text())
        return max(14 * PX, bounds.height() + 2 * PX)

    def sizeHint(self) -> QSize:
        width = 12 * PX + 4 * PX + self.fontMetrics().horizontalAdvance(self.text()) + PX
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return QSize(80 * PX, 14 * PX)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        box = QRect(0, (self.height() - 11 * PX) // 2, 11 * PX, 11 * PX)
        pixel_box(p, box, PAL["btn_hi"] if self.isChecked() else PAL["panel_lo"],
                  PAL["border"] if (self._hover or self.hasFocus()) else PAL["border_dark"])
        if self.isChecked():
            # 박스 안쪽 9x9(PX 단위) 한가운데에 7x5 체크 글리프를 칸 단위로 그린다 (좌우·상하 여백 동일)
            gw, gh = len(CHECK_GLYPH[0]), len(CHECK_GLYPH)
            gx = box.x() + PX + ((9 - gw) // 2) * PX
            gy = box.y() + PX + ((9 - gh) // 2) * PX
            gold = C("gold")
            for r, line in enumerate(CHECK_GLYPH):
                for c, ch in enumerate(line):
                    if ch == "#":
                        p.fillRect(gx + c * PX, gy + r * PX, PX, PX, gold)
        p.setFont(self.font())
        p.setPen(C("text" if self.isEnabled() else "dim"))
        p.drawText(QRect(14 * PX, 0, max(1, self.width() - 16 * PX), self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.text())
        p.end()


# ====================================================================== 슬라이더
class PixelSlider(QWidget):
    valueChanged = Signal(float)      # 값이 바뀔 때마다 (드래그 중 포함)
    released = Signal()               # 드래그 종료

    def __init__(self, lo: float, hi: float, step: float = 1, suffix: str = "", show_value: bool = True,
                 value_width: int = 64, parent=None):
        super().__init__(parent)
        self.lo, self.hi, self.step, self.suffix = lo, hi, step, suffix
        self._v = lo
        self._down = False
        self._show = show_value
        self._vw = value_width
        self.setFont(body_font())
        self.setFixedHeight(16 * PX)
        self.setMinimumWidth(120)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)

    # ---- 값
    def value(self) -> float:
        return self._v

    def setRange(self, lo: float, hi: float):
        self.lo, self.hi = lo, hi
        self._v = max(lo, min(hi, self._v))
        self.update()

    def _value_w(self) -> int:
        """값 글자 영역 폭. 지정한 폭과, 이 슬라이더가 표시할 수 있는 가장 긴 글자 폭 중 큰 쪽 (글자 잘림 방지)."""
        if not self._show:
            return 0
        fm = QFontMetrics(self.font())
        mid = (self.lo + self.hi) / 2
        need = max(fm.horizontalAdvance(self.format(v)) for v in (self.lo, self.hi, mid))
        return max(self._vw, need + 3 * PX)

    def setValue(self, v: float, emit: bool = False):
        v = max(self.lo, min(self.hi, round(v / self.step) * self.step))
        if v != self._v:
            self._v = v
            self.update()
            if emit:
                self.valueChanged.emit(v)

    def isDown(self) -> bool:
        return self._down

    def format(self, v: float) -> str:
        return f"{v:g}{self.suffix}"

    # ---- 기하
    def _track(self) -> QRect:
        right = self.width() - self._value_w()
        return QRect(4 * PX, 0, max(10, right - 8 * PX), self.height())

    def _pos_to_value(self, x: int) -> float:
        t = self._track()
        f = (x - t.x()) / max(1, t.width())
        return self.lo + max(0.0, min(1.0, f)) * (self.hi - self.lo)

    # ---- 이벤트
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._down = True
            self.setFocus(Qt.MouseFocusReason)
            self.setValue(self._pos_to_value(int(e.position().x())), emit=True)

    def mouseMoveEvent(self, e):
        if self._down:
            self.setValue(self._pos_to_value(int(e.position().x())), emit=True)

    def mouseReleaseEvent(self, e):
        if self._down:
            self._down = False
            self.update()
            self.released.emit()

    def wheelEvent(self, e):
        if not self.hasFocus():              # 포커스 없는 슬라이더는 휠을 넘겨서 페이지 스크롤이 되게 함
            e.ignore()
            return
        d = 1 if e.angleDelta().y() > 0 else -1
        self.setValue(self._v + d * self.step, emit=True)
        self.released.emit()
        e.accept()

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_Down):
            self.setValue(self._v - self.step, emit=True)
            self.released.emit()
        elif k in (Qt.Key_Right, Qt.Key_Up):
            self.setValue(self._v + self.step, emit=True)
            self.released.emit()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        en = self.isEnabled()                    # 비활성: 채움/손잡이/값 글자를 흐리게 (조작 불가임을 한눈에 구분)
        t = self._track()
        cy = self.height() // 2
        bar = QRect(t.x(), cy - 3 * PX, t.width(), 6 * PX)
        pixel_box(p, bar, PAL["panel_lo"], PAL["border_dark"] if en else PAL["btn_off"])
        frac = 0 if self.hi == self.lo else (self._v - self.lo) / (self.hi - self.lo)
        fw = int(frac * (t.width() - 4 * PX))
        if fw > 0:
            p.fillRect(bar.x() + 2 * PX, bar.y() + 2 * PX, fw, 2 * PX, C("green" if en else "btn_off"))
            if en:
                p.fillRect(bar.x() + 2 * PX, bar.y() + 2 * PX, fw, PX, C("#7fe08f"))
        hx = bar.x() + 2 * PX + fw - 3 * PX
        hr = QRect(hx, cy - 7 * PX, 6 * PX, 14 * PX)
        if en:
            pixel_box(p, hr, PAL["gold"] if (self._down or self.hasFocus()) else PAL["border"],
                      PAL["border_dark"], hi="#ffffff")
        else:
            pixel_box(p, hr, PAL["btn_off"], PAL["dim"])
        if self._show:
            p.setFont(self.font())
            p.setPen(C("gold" if en else "dim"))
            vw = self._value_w()
            p.drawText(QRect(self.width() - vw, 0, vw - PX, self.height()),
                       Qt.AlignVCenter | Qt.AlignRight, self.format(self._v))
        p.end()

    def changeEvent(self, e):
        if e.type() == QEvent.EnabledChange:      # 활성/비활성이 바뀌면 즉시 다시 그림
            self.update()
        super().changeEvent(e)


# ====================================================================== 세로 탭
class PixelTabs(QWidget):
    currentChanged = Signal(int)

    ROW_H = 24 * PX

    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.items = items          # [(icon, text), ...]
        self._cur = 0
        self._hover = -1
        self.setFont(body_font())
        self.setMouseTracking(True)
        self.setFixedWidth(100 * PX)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)   # Tab 키로 들어오면 위/아래 화살표로 탭을 옮긴다

    def current(self) -> int:
        return self._cur

    def key_target(self, key) -> int | None:
        """키 입력에 해당하는 이동 대상 탭 번호 (이동하지 않는 키는 None). PixelSlider 와 같은 == 비교를 쓴다."""
        if key in (Qt.Key_Down, Qt.Key_PageDown):
            action = "next"
        elif key in (Qt.Key_Up, Qt.Key_PageUp):
            action = "prev"
        elif key == Qt.Key_Home:
            action = "first"
        elif key == Qt.Key_End:
            action = "last"
        else:
            return None
        return nav_target(self._cur, len(self.items), action)

    def keyPressEvent(self, e: QKeyEvent):
        t = self.key_target(e.key())
        if t is None:
            super().keyPressEvent(e)
            return
        self.setCurrent(t)
        e.accept()

    def focusInEvent(self, e):
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.update()
        super().focusOutEvent(e)

    def setCurrent(self, i: int):
        if 0 <= i < len(self.items) and i != self._cur:
            self._cur = i
            self.update()
            self.currentChanged.emit(i)

    def _row_at(self, y: int) -> int:
        i = (y - 2 * PX) // self.ROW_H
        return int(i) if 0 <= i < len(self.items) else -1

    def mouseMoveEvent(self, e):
        h = self._row_at(int(e.position().y()))
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._row_at(int(e.position().y()))
        if i >= 0:
            self.setCurrent(i)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        for i, (icon, text) in enumerate(self.items):
            r = QRect(2 * PX, 2 * PX + i * self.ROW_H, self.width() - 4 * PX, self.ROW_H - 2 * PX)
            sel = i == self._cur
            fill = PAL["gold"] if sel else (PAL["btn_hi"] if i == self._hover else PAL["panel"])
            pixel_box(p, r, fill, PAL["border"] if sel else PAL["border_dark"],
                      hi="#fff1a8" if sel else None, lo="#b8862a" if sel else PAL["panel_lo"])
            col = PAL["shadow"] if sel else PAL["text"]
            pm = sprite_pixmap("star_mono", PX, main="#000000") if (sel and icon == "star") else sprite_pixmap(icon, PX, main=col)   # 선택된 탭의 노란 별은 검은색으로
            p.drawPixmap(r.x() + 5 * PX, r.y() + (r.height() - pm.height()) // 2, pm)
            p.setPen(QColor(col))
            tr_rect = QRect(r.x() + 17 * PX, r.y(), r.width() - 18 * PX, r.height())
            p.setFont(self._fitted_font(text, tr_rect.width()))
            p.drawText(tr_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
            p.setFont(self.font())
        p.end()

    def _fitted_font(self, text: str, width: int):
        """탭 이름이 칸보다 길면(영어) 폭에 맞을 때까지 글자 크기를 줄인다. 탭 폭·창 크기는 바뀌지 않는다."""
        font = QFont(self.font())
        if QFontMetrics(font).horizontalAdvance(text) <= width:
            return font
        px = font.pixelSize()
        use_px = px > 0
        size = px if use_px else font.pointSizeF()
        floor = max(6.0, size * 0.6)
        while size > floor:
            size -= 1
            if use_px:
                font.setPixelSize(int(size))
            else:
                font.setPointSizeF(size)
            if QFontMetrics(font).horizontalAdvance(text) <= width:
                break
        return font


# ====================================================================== 줄바꿈 라벨
class WrapLabel(QLabel):
    """줄바꿈(setWordWrap) 라벨이 스크롤 페이지 안에서 아랫부분이 잘리지 않게, 폭에 맞춘 높이를 최소 높이로 잡는다.
    줄바꿈을 쓰지 않는 라벨은 QLabel 과 똑같이 동작한다."""

    _BREAK_AFTER = ("\\", "/")

    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        if text:
            self.setText(text)

    @classmethod
    def breakable(cls, t: str) -> str:
        """공백이 없는 긴 경로(C:\\Users\\...)는 줄바꿈 지점이 없어 오른쪽이 잘리므로, 폴더 구분자 뒤에 보이지 않는 줄바꿈 지점을 넣는다."""
        for ch in cls._BREAK_AFTER:
            t = t.replace(ch + "\u200b", ch).replace(ch, ch + "\u200b")
        return t

    def _fit_height(self):
        if not self.wordWrap() or self.width() <= 0:
            return
        h = self.heightForWidth(self.width())
        if h > 0 and h != self.minimumHeight():
            self.setMinimumHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_height()

    def setText(self, t):
        super().setText(self.breakable(t) if self.wordWrap() else t)
        self._fit_height()

    def setWordWrap(self, on):
        super().setWordWrap(on)
        if on:
            super().setText(self.breakable(self.text()))
        self._fit_height()


# ====================================================================== 구분선 / 패널
class PixelSection(QWidget):
    """금색 제목 + 점선 구분선."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFont(body_font())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        text_width = max(24, width - 12 * PX)
        bounds = self.fontMetrics().boundingRect(QRect(0, 0, text_width, 10000), Qt.TextWordWrap, self.text)
        return max(18 * PX, bounds.height() + 4 * PX)

    def sizeHint(self) -> QSize:
        return QSize(300 * PX, self.heightForWidth(300 * PX))

    def minimumSizeHint(self) -> QSize:
        return QSize(80 * PX, 18 * PX)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(C("gold"))
        text_rect = QRect(0, 0, max(1, self.width() - 12 * PX), self.height() - 2 * PX)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.text)
        bounds = self.fontMetrics().boundingRect(QRect(0, 0, text_rect.width(), 10000), Qt.TextWordWrap, self.text)
        if bounds.height() <= self.height() - 4 * PX:      # 한 줄일 때만 점선 구분선
            x = min(self.width() - 2 * PX, bounds.width() + 6 * PX)
            y = max(PX, (self.height() - 2 * PX) // 2)
            while x < self.width() - 2 * PX:
                p.fillRect(x, y, 2 * PX, PX, C("border_dark"))
                x += 4 * PX
        p.end()


class PixelPanel(QWidget):
    """우묵한 패널 (안쪽 배경)."""

    def __init__(self, parent=None, fill: str = "panel"):
        super().__init__(parent)
        self._fill = fill

    def paintEvent(self, e):
        p = QPainter(self)
        pixel_box(p, self.rect(), PAL[self._fill], PAL["border_dark"], lo=PAL["panel_lo"])
        p.end()


# ====================================================================== 창 프레임
class PixelWindow(QWidget):
    """프레임 없는 픽셀 스타일 창. 제목 표시줄 드래그로 이동, 닫기 버튼, Esc 로 닫기."""

    TITLE_H = 22 * PX

    def __init__(self, title: str, icon: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(title)
        self._title = title
        self._icon = icon
        self._drag: QPoint | None = None
        self._close_hover = False
        self.setMouseTracking(True)
        self.setFont(body_font())
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(3 * PX, self.TITLE_H + PX, 3 * PX, 3 * PX)
        self._root.setSpacing(0)
        self.body = QWidget(self)
        self._root.addWidget(self.body)

    def _close_rect(self) -> QRect:
        return QRect(self.width() - 3 * PX - 16 * PX, 3 * PX, 16 * PX, 16 * PX)

    def paintEvent(self, e):
        p = QPainter(self)
        pixel_box(p, self.rect(), PAL["bg"], PAL["border"], lo=PAL["panel_lo"])
        bar = QRect(2 * PX, 2 * PX, self.width() - 4 * PX, self.TITLE_H - 2 * PX)
        p.fillRect(bar, C("panel_hi"))
        p.fillRect(bar.x(), bar.bottom() - PX + 1, bar.width(), PX, C("panel_lo"))
        x = bar.x() + 4 * PX
        if self._icon:
            pm = sprite_pixmap(self._icon, PX, main=PAL["gold"])
            p.drawPixmap(x, bar.y() + (bar.height() - pm.height()) // 2, pm)
            x += pm.width() + 4 * PX
        p.setFont(self.font())
        p.setPen(C("gold"))
        p.drawText(QRect(x, bar.y(), bar.width() - x, bar.height()), Qt.AlignVCenter | Qt.AlignLeft, self._title)
        cr = self._close_rect()
        pixel_box(p, cr, PAL["red"] if self._close_hover else PAL["red_dark"], PAL["border"])
        pm = sprite_pixmap("close", PX, main=PAL["snow"])
        p.drawPixmap(cr.x() + (cr.width() - pm.width()) // 2, cr.y() + (cr.height() - pm.height()) // 2, pm)
        p.end()

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if e.button() == Qt.LeftButton:
            if self._close_rect().contains(pos):
                self.close()
            elif pos.y() < self.TITLE_H:
                self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        hov = self._close_rect().contains(pos)
        if hov != self._close_hover:
            self._close_hover = hov
            self.update()
        if self._drag is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def leaveEvent(self, e):
        if self._close_hover:
            self._close_hover = False
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)


# ====================================================================== 전역 스타일시트
def app_stylesheet() -> str:
    p = PAL
    return f"""
* {{ outline: 0; }}
QToolTip {{ background:{p['panel_lo']}; color:{p['text']}; border:{PX}px solid {p['border']}; padding:{2*PX}px; }}
QMenu {{ background:{p['panel']}; color:{p['text']}; border:{PX}px solid {p['border']}; padding:{2*PX}px; }}
QMenu::item {{ padding:{3*PX}px {10*PX}px {3*PX}px {6*PX}px; border:0; }}
QMenu::item:selected {{ background:{p['btn_hi']}; color:#ffffff; }}
QMenu::item:disabled {{ color:{p['dim']}; }}
QMenu::separator {{ height:{PX}px; background:{p['panel_lo']}; margin:{2*PX}px {PX}px; }}
QMenu::icon {{ padding-left:{3*PX}px; }}
QLabel {{ color:{p['text']}; background:transparent; }}
QListWidget {{ background:{p['panel_lo']}; color:{p['text']}; border:{PX}px solid {p['border_dark']}; padding:{PX}px; }}
QListWidget::item {{ padding:{2*PX}px {3*PX}px; }}
QListWidget::item:selected {{ background:{p['btn_hi']}; color:#ffffff; }}
QListWidget::item:hover {{ background:{p['panel_hi']}; }}
QListWidget:disabled {{ color:{p['dim']}; border-color:{p['btn_off']}; }}
QScrollBar:vertical {{ background:{p['panel_lo']}; width:{8*PX}px; margin:0; border:0; }}
QScrollBar::handle:vertical {{ background:{p['border_dark']}; min-height:{12*PX}px; border:{PX}px solid {p['panel_lo']}; }}
QScrollBar::handle:vertical:hover {{ background:{p['border']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QScrollBar:horizontal {{ background:{p['panel_lo']}; height:{8*PX}px; border:0; }}
QScrollBar::handle:horizontal {{ background:{p['border_dark']}; min-width:{12*PX}px; border:{PX}px solid {p['panel_lo']}; }}
QDoubleSpinBox, QSpinBox, QLineEdit {{ background:{p['panel_lo']}; color:{p['text']}; border:{PX}px solid {p['border_dark']}; padding:{PX}px {2*PX}px; selection-background-color:{p['gold']}; selection-color:{p['shadow']}; }}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color:{p['border']}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled, QLineEdit:disabled {{ color:{p['dim']}; border-color:{p['btn_off']}; }}
QDoubleSpinBox::up-button, QSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::down-button {{ width:{8*PX}px; background:{p['btn']}; border:0; }}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{ background:{p['btn_hi']}; }}
QMessageBox, QDialog {{ background:{p['bg']}; color:{p['text']}; }}
QPushButton {{ background:{p['btn']}; color:{p['text']}; border:{PX}px solid {p['border_dark']}; padding:{3*PX}px {8*PX}px; min-width:{30*PX}px; }}
QPushButton:hover {{ background:{p['btn_hi']}; border-color:{p['border']}; }}
QPushButton:pressed {{ background:{p['btn_down']}; }}
QPushButton:disabled {{ background:{p['btn_off']}; color:{p['dim']}; border-color:{p['btn_off']}; }}
QCalendarWidget QWidget {{ background:{p['panel']}; color:{p['text']}; }}
QCalendarWidget QToolButton {{ background:{p['btn']}; color:{p['text']}; border:{PX}px solid {p['border_dark']}; padding:{2*PX}px; }}
QCalendarWidget QToolButton:hover {{ background:{p['btn_hi']}; }}
QCalendarWidget QMenu {{ background:{p['panel']}; }}
QCalendarWidget QSpinBox {{ background:{p['panel_lo']}; color:{p['text']}; border:{PX}px solid {p['border_dark']}; }}
QCalendarWidget QAbstractItemView {{ background:{p['panel_lo']}; color:{p['text']}; selection-background-color:{p['gold']}; selection-color:{p['shadow']}; border:{PX}px solid {p['border_dark']}; }}
QCalendarWidget QAbstractItemView:disabled {{ color:{p['dim']}; }}
"""
