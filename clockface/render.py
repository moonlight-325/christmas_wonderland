"""픽셀 시계 렌더러: 디지털 3종(LED / 7세그먼트 / 플립 카드) + 아날로그 3종(클래식 / 리스 / 눈꽃).

모든 도형은 u(=시계 크기 설정) 픽셀 격자에 맞춘 사각형으로 그려 픽셀이 번지지 않는다.
size(cfg) 로 필요한 크기를 구하고(시각에 따라 변하지 않도록 최대 폭 기준), paint(...) 로 그린다.
"""
from __future__ import annotations
from core.i18n import tr, weekday_full_names


import math
from datetime import datetime

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter

from core.dday import WEEKDAYS_KO, dday_text
from core.fonts import pixel_font

THEMES = {
    "led": tr("LED 도트"), "segment": tr("7세그먼트"), "card": tr("플립 카드"),
    "analog_classic": tr("아날로그 클래식"), "analog_wreath": tr("아날로그 리스"), "analog_snow": tr("아날로그 눈꽃"),
}
ANALOG = {"analog_classic", "analog_wreath", "analog_snow"}
COLORS = {  # (밝은색, 어두운색)
    "gold": ("#f3c94a", "#b8862a"), "red": ("#ff5a4e", "#8f1f2a"), "green": ("#62c873", "#2f8f4e"),
    "white": ("#ffffff", "#b8c8d8"), "sky": ("#8fd0f5", "#3d6fa8"), "pink": ("#ff9ad5", "#b04a8f"),
}
COLOR_NAMES = {"gold": tr("금색"), "red": tr("빨강"), "green": tr("초록"), "white": tr("하양"), "sky": tr("하늘"), "pink": tr("분홍")}
BGS = {"panel": tr("패널"), "none": tr("없음"), "night": tr("밤하늘"), "snow": tr("눈빛")}
# 배경별 (채움, 테두리, 글자 밝기 반전 여부)
BG_STYLE = {
    "panel": ("#154436", "#f3e6c4", False),
    "night": ("#0b1530", "#8fd0f5", False),
    "snow": ("#e8f3fb", "#6d8fb0", True),
    "none": (None, None, False),
}

# 5 x 7 도트 숫자
_DOT = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
}
# 7세그먼트: a b c d e f g
_SEG = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
        "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg"}


def _c(hexcol, alpha=255) -> QColor:
    c = QColor(hexcol)
    c.setAlpha(alpha)
    return c


class Palette:
    def __init__(self, cfg: dict):
        main, dim = COLORS[cfg["color"]]
        self.fill, self.border, light_bg = BG_STYLE[cfg["bg"]]
        if light_bg:                       # 밝은 배경에서는 어두운 색을 주색으로
            main, dim = dim, COLORS[cfg["color"]][0]
        self.main, self.dim = main, dim
        self.text = "#2b3d52" if light_bg else "#f5ead0"
        self.shadow = "#06150f" if not light_bg else "#c5d6e4"
        self.unlit = _c(dim, 26)


# ------------------------------------------------------------------ 텍스트 줄
def _info_lines(cfg: dict, now: datetime, worst: bool = False) -> list:
    """표시 설정에 따른 보조 줄(날짜+요일 / D-Day)."""
    lines = []
    parts = []
    if cfg["show_date"]:
        parts.append("2026.12.30" if worst else now.strftime("%Y.%m.%d"))
    if cfg["show_weekday"]:
        parts.append(weekday_full_names()[2 if worst else now.weekday()])
    if parts:
        lines.append(" ".join(parts))
    if cfg["show_dday"]:
        lines.append("D-DAY" if worst else dday_text(now.date()))
    return lines


def _font_scale(u: int) -> int:
    return max(1, round(u / 2))


def _text_w(text: str, fs: int) -> int:
    return QFontMetrics(pixel_font(11, fs)).horizontalAdvance(text)


def _draw_text(p: QPainter, pal: Palette, x: int, y: int, w: int, text: str, fs: int, color: str, u: int):
    font = pixel_font(11, fs)
    p.setFont(font)
    r = QRect(x, y, w, 11 * fs)
    p.setPen(QColor(pal.shadow))
    p.drawText(r.translated(max(1, u // 2), max(1, u // 2)), Qt.AlignHCenter | Qt.AlignVCenter, text)
    p.setPen(QColor(color))
    p.drawText(r, Qt.AlignHCenter | Qt.AlignVCenter, text)


# ------------------------------------------------------------------ 디지털 숫자 렌더러
def _time_chars(cfg: dict, now: datetime, worst: bool = False) -> str:
    h = now.hour if cfg["h24"] else (now.hour % 12 or 12)
    hh = f"{h:02d}"
    s = f"{hh}:{now.minute:02d}"
    if cfg["show_seconds"]:
        s += f":{now.second:02d}"
    return s


def _digit_dims(theme: str, u: int):
    """(숫자 폭, 숫자 높이, 콜론 폭, 간격)"""
    if theme == "led":
        c = 2 * u
        return 5 * c - u, 7 * c - u, 2 * c - u, c
    if theme == "segment":
        return 10 * u, 18 * u, 3 * u, 2 * u
    return 14 * u, 20 * u, 4 * u, 2 * u        # card


def _row_width(theme: str, u: int, chars: str) -> int:
    dw, _dh, cw, gap = _digit_dims(theme, u)
    w = 0
    for i, ch in enumerate(chars):
        w += (cw if ch == ":" else dw) + (gap if i < len(chars) - 1 else 0)
    return w


def _draw_led_digit(p, pal, x, y, ch, u, on_col):
    c = 2 * u
    glyph = _DOT[ch]
    for r, line in enumerate(glyph):
        for k, v in enumerate(line):
            col = on_col if v == "1" else pal.unlit
            p.fillRect(x + k * c, y + r * c, c - u, c - u, col)


def _draw_segment_digit(p, pal, x, y, ch, u, on_col):
    t, hl, vl = 2 * u, 6 * u, 6 * u
    segs = {
        "a": QRect(x + t, y, hl, t), "b": QRect(x + t + hl, y + t, t, vl),
        "c": QRect(x + t + hl, y + 2 * t + vl, t, vl), "d": QRect(x + t, y + 2 * t + 2 * vl, hl, t),
        "e": QRect(x, y + 2 * t + vl, t, vl), "f": QRect(x, y + t, t, vl),
        "g": QRect(x + t, y + t + vl, hl, t),
    }
    lit = _SEG[ch]
    for k, r in segs.items():
        p.fillRect(r, on_col if k in lit else pal.unlit)


def _draw_card_digit(p, pal, x, y, ch, u, on_col):
    w, h = 14 * u, 20 * u
    p.fillRect(x, y, w, h, QColor("#0d1f19"))
    for rect in (QRect(x, y, w, u), QRect(x, y + h - u, w, u), QRect(x, y, u, h), QRect(x + w - u, y, u, h)):
        p.fillRect(rect, QColor(pal.dim))
    c = 2 * u
    gx, gy = x + (w - 5 * c) // 2, y + (h - 7 * c) // 2
    for r, line in enumerate(_DOT[ch]):
        for k, v in enumerate(line):
            if v == "1":
                p.fillRect(gx + k * c, gy + r * c, c, c, on_col)
    p.fillRect(x + u, y + h // 2, w - 2 * u, max(1, u // 2), QColor("#06150f"))   # 플립 접힘선


def _draw_colon(p, pal, theme, x, y, u, on_col, h):
    if theme == "led":
        c = 2 * u
        for r in (2, 4):
            p.fillRect(x, y + r * c, c - u, c - u, on_col)
    elif theme == "segment":
        t = 2 * u
        p.fillRect(x + u // 2, y + h // 3 - t // 2, t, t, on_col)
        p.fillRect(x + u // 2, y + 2 * h // 3 - t // 2, t, t, on_col)
    else:
        t = 2 * u
        p.fillRect(x + u, y + h // 3 - t // 2, t, t, on_col)
        p.fillRect(x + u, y + 2 * h // 3 - t // 2, t, t, on_col)


def _draw_digital_time(p, pal, theme, cx_left, y, chars, u, blink_on=True):
    dw, dh, cw, gap = _digit_dims(theme, u)
    x = cx_left
    on = QColor(pal.main)
    for ch in chars:
        if ch == ":":
            _draw_colon(p, pal, theme, x, y, u, on if blink_on else pal.unlit, dh)
            x += cw + gap
            continue
        {"led": _draw_led_digit, "segment": _draw_segment_digit, "card": _draw_card_digit}[theme](p, pal, x, y, ch, u, on)
        x += dw + gap


# ------------------------------------------------------------------ 아날로그
R_CELLS = 14        # 문자판 반지름(칸)


def _line_cells(x0, y0, x1, y1):
    """브레젠험 직선의 칸 좌표들."""
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def _hand(p, ox, oy, u, angle_deg, length, color, thick=1):
    a = math.radians(angle_deg)
    ex, ey = round(math.sin(a) * length), round(-math.cos(a) * length)
    for (cx, cy) in _line_cells(0, 0, ex, ey):
        p.fillRect(ox + cx * u, oy + cy * u, u * thick, u * thick, color)
        if thick > 1 and abs(ex) < abs(ey) * 0.5:
            pass


def _dial(p, pal, theme, ox, oy, u, now):
    """문자판 중심 (ox, oy) 를 기준으로 그린다."""
    R = R_CELLS
    main, dim = QColor(pal.main), QColor(pal.dim)
    if theme == "analog_classic":
        for cy in range(-R, R + 1):
            for cx in range(-R, R + 1):
                d = math.hypot(cx, cy)
                if d <= R + 0.3:
                    col = QColor("#f5ead0") if d < R - 1.2 else (dim if d < R - 0.2 else main)
                    p.fillRect(ox + cx * u, oy + cy * u, u, u, col)
        for k in range(12):
            a = math.radians(k * 30)
            r0, r1 = (R - 4, R - 2) if k % 3 == 0 else (R - 3, R - 2)
            for rr in range(r0, r1 + 1):
                p.fillRect(ox + round(math.sin(a) * rr) * u, oy + round(-math.cos(a) * rr) * u, u, u, QColor("#3a2c1a"))
        hand_col, min_col, sec_col = QColor("#3a2c1a"), QColor("#3a2c1a"), QColor("#d63a3a")
    elif theme == "analog_wreath":
        greens = ("#2f8f4e", "#62c873", "#1d5e3a", "#4fb66b")
        for cy in range(-R, R + 1):
            for cx in range(-R, R + 1):
                d = math.hypot(cx, cy)
                if R - 4.2 <= d <= R + 0.3:
                    p.fillRect(ox + cx * u, oy + cy * u, u, u, QColor(greens[(cx * 3 + cy * 5) % 4]))
                elif d < R - 4.2:
                    p.fillRect(ox + cx * u, oy + cy * u, u, u, QColor("#0f2f26"))
        for (cx, cy) in ((-8, -8), (9, -7), (-11, 3), (11, 4), (-6, 10), (7, 10), (0, -12)):
            p.fillRect(ox + cx * u, oy + cy * u, u, u, QColor("#d63a3a"))
        for k in range(12):                                   # 눈금: 별 모양 점
            a = math.radians(k * 30)
            rr = R - 6
            x, y = ox + round(math.sin(a) * rr) * u, oy + round(-math.cos(a) * rr) * u
            p.fillRect(x, y, u, u, QColor("#f3c94a") if k % 3 == 0 else QColor("#f5ead0"))
        # 12시 방향 빨간 리본
        for cx, cy, col in ((-2, -R - 1, "#d63a3a"), (-1, -R, "#d63a3a"), (1, -R, "#d63a3a"), (2, -R - 1, "#d63a3a"),
                            (0, -R, "#8f1f2a"), (-1, -R - 1, "#d63a3a"), (1, -R - 1, "#d63a3a")):
            p.fillRect(ox + cx * u, oy + cy * u, u, u, QColor(col))
        hand_col, min_col, sec_col = QColor("#f5ead0"), QColor(pal.main), QColor("#ff6a5e")
    else:   # analog_snow
        for cy in range(-R, R + 1):
            for cx in range(-R, R + 1):
                d = math.hypot(cx, cy)
                if d <= R + 0.3:
                    p.fillRect(ox + cx * u, oy + cy * u, u, u,
                               QColor("#dcecf8") if d >= R - 0.8 else QColor("#12284a"))
        for k in range(12):
            a = math.radians(k * 30)
            rr = R - 3
            x, y = round(math.sin(a) * rr), round(-math.cos(a) * rr)
            p.fillRect(ox + x * u, oy + y * u, u, u, QColor("#ffffff"))
            if k % 3 == 0:                                    # 큰 눈꽃 (십자)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p.fillRect(ox + (x + dx) * u, oy + (y + dy) * u, u, u, QColor("#8fd0f5"))
        hand_col, min_col, sec_col = QColor("#ffffff"), QColor("#ffffff"), QColor(pal.main)
    h = now.hour % 12 + now.minute / 60.0
    _hand(p, ox, oy, u, h * 30, 7, hand_col, thick=2)
    _hand(p, ox, oy, u, now.minute * 6 + now.second * 0.1, 11, min_col, thick=1)
    return sec_col


# ------------------------------------------------------------------ 배치/그리기
def _layout(cfg: dict, now: datetime, worst: bool):
    """내용 크기와 줄 구성. 반환: (content_w, content_h, rows)"""
    u = int(cfg["scale"])
    theme = cfg["theme"]
    fs = _font_scale(u)
    gap = 3 * u
    rows = []     # (종류, 높이, 폭, 데이터)
    if cfg["show_time"]:
        if theme in ANALOG:
            side = (2 * R_CELLS + 5) * u
            rows.append(("dial", side, side, None))
        else:
            chars = _time_chars(cfg, now if not worst else datetime(2026, 12, 30, 22, 22, 22))
            rows.append(("time", _digit_dims(theme, u)[1], _row_width(theme, u, chars), chars))
    for line in _info_lines(cfg, now, worst):
        rows.append(("text", 11 * fs, _text_w(line, fs) + 2 * u, line))
    if not rows:
        rows.append(("text", 11 * fs, _text_w(tr("표시 항목 없음"), fs), tr("표시 항목 없음")))
    w = max(r[2] for r in rows)
    h = sum(r[1] for r in rows) + gap * (len(rows) - 1)
    return w, h, rows, gap


def size(cfg: dict) -> QSize:
    u = int(cfg["scale"])
    w, h, _rows, _gap = _layout(cfg, datetime.now(), True)
    pad = 5 * u if cfg["bg"] != "none" else 2 * u
    return QSize(w + 2 * pad, h + 2 * pad)


def paint(p: QPainter, cfg: dict, now: datetime | None = None, rect: QRect | None = None):
    now = now or datetime.now()
    u = int(cfg["scale"])
    pal = Palette(cfg)
    sz = size(cfg)
    rect = rect or QRect(0, 0, sz.width(), sz.height())
    p.save()
    p.translate(rect.x(), rect.y())
    if pal.fill:
        p.fillRect(u, 0, sz.width() - 2 * u, sz.height(), QColor(pal.fill))
        p.fillRect(0, u, sz.width(), sz.height() - 2 * u, QColor(pal.fill))
        b = QColor(pal.border)
        p.fillRect(u, 0, sz.width() - 2 * u, u, b)
        p.fillRect(u, sz.height() - u, sz.width() - 2 * u, u, b)
        p.fillRect(0, u, u, sz.height() - 2 * u, b)
        p.fillRect(sz.width() - u, u, u, sz.height() - 2 * u, b)
    pad = 5 * u if cfg["bg"] != "none" else 2 * u
    w, h, rows, gap = _layout(cfg, now, False)
    full_w = sz.width() - 2 * pad
    y = pad
    fs = _font_scale(u)
    theme = cfg["theme"]
    for kind, rh, rw, data in rows:
        x = pad + (full_w - rw) // 2
        if kind == "time":
            _draw_digital_time(p, pal, theme, x, y, data, u, blink_on=(now.second % 2 == 0 or not cfg["show_seconds"]))
        elif kind == "dial":
            ox, oy = x + rw // 2, y + rh // 2
            sec_col = _dial(p, pal, theme, ox, oy, u, now)
            if cfg["show_seconds"]:
                _hand(p, ox, oy, u, now.second * 6, 12, sec_col, thick=1)
            p.fillRect(ox - u, oy - u, 2 * u, 2 * u, QColor(pal.main))
        else:
            _draw_text(p, pal, pad, y, full_w, data, fs, pal.main if data.startswith("D-") else pal.text, u)
        y += rh + gap
    p.restore()


def render_image(cfg: dict, now: datetime | None = None) -> QImage:
    sz = size(cfg)
    img = QImage(sz, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    paint(p, cfg, now)
    p.end()
    return img
