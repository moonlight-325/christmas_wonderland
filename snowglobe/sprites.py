"""스노우볼 픽셀아트 스프라이트: 장식 10종 (QPainter 로 정수 격자에 직접 그림, 안티앨리어싱 없음).

각 함수는 (p, w, h) 크기의 빈 이미지에 그린다. 앵커 = 아래 가운데. 박스는 사선(오블리크) 투영으로
앞면 / 윗면 / 옆면을 따로 칠해 아이소메트릭 느낌을 낸다.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygon

from . import catalog as C


# ------------------------------------------------------------------ 그리기 도우미
def qc(c, a: int = 255) -> QColor:
    q = QColor(c) if isinstance(c, str) else QColor(*c)
    if not isinstance(c, str) and len(c) == 4:
        return q
    q.setAlpha(a)
    return q


def shade(c, f: float) -> QColor:
    q = QColor(c)
    return QColor(max(0, min(255, int(q.red() * f))), max(0, min(255, int(q.green() * f))),
                  max(0, min(255, int(q.blue() * f))), q.alpha())


def mix(c0, c1, t: float) -> QColor:
    a, b = QColor(c0), QColor(c1)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def rect(p: QPainter, x, y, w, h, c):
    p.fillRect(int(round(x)), int(round(y)), max(1, int(round(w))), max(1, int(round(h))), qc(c) if isinstance(c, (str, tuple)) else c)


def poly(p: QPainter, pts, c):
    p.setPen(Qt.NoPen)
    p.setBrush(qc(c) if isinstance(c, (str, tuple)) else c)
    p.drawPolygon(QPolygon([QPoint(int(round(x)), int(round(y))) for x, y in pts]))


def ell(p: QPainter, cx, cy, rx, ry, c, outline=None):
    if outline is not None:
        p.setPen(qc(outline) if isinstance(outline, (str, tuple)) else outline)
    else:
        p.setPen(Qt.NoPen)
    p.setBrush(qc(c) if isinstance(c, (str, tuple)) else c)
    p.drawEllipse(QPointF(cx, cy), max(0.5, rx), max(0.5, ry))


def obox(p, x0, yb, W, Hh, d, cf, ct=None, cs=None):
    """사선 투영 박스. 앞면(W x Hh) + 윗면(평행사변형) + 옆면. (x0, yb) = 앞면 왼쪽 아래."""
    ct = ct if ct is not None else shade(cf, 1.25)
    cs = cs if cs is not None else shade(cf, 0.72)
    d2 = d / 2.0
    poly(p, [(x0 + W, yb - Hh), (x0 + W + d, yb - Hh - d2), (x0 + W + d, yb - d2), (x0 + W, yb)], cs)
    poly(p, [(x0, yb - Hh), (x0 + W, yb - Hh), (x0 + W + d, yb - Hh - d2), (x0 + d, yb - Hh - d2)], ct)
    rect(p, x0, yb - Hh, W, Hh, cf)


def shadow(p, w, h):
    ell(p, w / 2.0, h - 1, w * 0.46, max(1.0, h * 0.06), (0, 0, 0, 55))


SNOW, SNOW_SH = "#ffffff", "#d6e6f5"


# ------------------------------------------------------------------ 장식 스프라이트
def tree_small(p, w, h):
    shadow(p, w, h)
    tw = max(2, w * 0.16)
    rect(p, (w - tw) / 2, h * 0.80, tw, h * 0.18, "#6b4425")
    for (ay, by, hw), col in zip(((.02, .40, .30), (.20, .62, .40), (.40, .84, .50)), ("#2a7a48", "#34905a", "#3fa468")):
        poly(p, [(w / 2, ay * h), (w / 2 + hw * w, by * h), (w / 2 - hw * w, by * h)], col)
        k = 0.42
        poly(p, [(w / 2, ay * h), (w / 2 + hw * w * k, (ay + (by - ay) * k) * h), (w / 2 - hw * w * k, (ay + (by - ay) * k) * h)], SNOW)


def tree_xmas(p, w, h):
    shadow(p, w, h)
    tw = max(2, w * 0.14)
    rect(p, (w - tw) / 2, h * 0.86, tw, h * 0.13, "#6b4425")
    tiers = ((.10, .38, .26), (.26, .56, .36), (.42, .74, .45), (.58, .90, .52))
    cols = ("#1f6b3e", "#27804a", "#2f955a", "#38a968")
    for (ay, by, hw), col in zip(tiers, cols):
        poly(p, [(w / 2, ay * h), (w / 2 + hw * w, by * h), (w / 2 - hw * w, by * h)], col)
        poly(p, [(w / 2, ay * h), (w / 2 + hw * w * .4, (ay + (by - ay) * .4) * h), (w / 2 - hw * w * .4, (ay + (by - ay) * .4) * h)], SNOW)
    star = max(2, w * 0.2)
    rect(p, w / 2 - star / 2, 0, star, star, "#ffd84a")
    rect(p, w / 2 - star / 6, -0 if star < 3 else 0, max(1, star / 3), max(1, star), "#fff3a0")
    for fx, fy, c in ((.44, .30, "#e84a4a"), (.58, .44, "#f3d34a"), (.36, .52, "#4a8fe8"), (.62, .62, "#e84a4a"),
                      (.30, .74, "#f3d34a"), (.50, .70, "#e86ad0"), (.70, .80, "#4a8fe8"), (.42, .86, "#e84a4a")):
        rect(p, fx * w, fy * h, max(1, w * .08), max(1, w * .08), c)


def snowman(p, w, h):
    shadow(p, w, h)
    ol = "#b4c9e2"
    ell(p, w / 2, h * .78, w * .42, h * .20, SNOW, ol)
    ell(p, w / 2, h * .50, w * .32, h * .16, SNOW, ol)
    hr = w * .24
    ell(p, w / 2, h * .25, hr, hr * 1.05, SNOW, ol)
    rect(p, w / 2 - hr * .95, h * .25 - hr * 1.0 - max(1, h * .02), hr * 1.9, max(1, h * .05), "#222733")
    rect(p, w / 2 - hr * .6, h * .25 - hr * 1.0 - max(2, h * .1), hr * 1.2, max(2, h * .10), "#2e3442")
    rect(p, w / 2 - hr * .45, h * .22, max(1, w * .07), max(1, w * .07), "#222733")
    rect(p, w / 2 + hr * .2, h * .22, max(1, w * .07), max(1, w * .07), "#222733")
    rect(p, w / 2 - 0, h * .27, max(2, w * .20), max(1, h * .05), "#f08a2a")
    rect(p, w / 2 - hr * 1.0, h * .36, hr * 2.0, max(1, h * .06), "#d63a3a")
    rect(p, w / 2 + hr * .5, h * .36, max(1, w * .1), max(2, h * .14), "#d63a3a")
    for fy in (.48, .56):
        rect(p, w / 2 - 0, fy * h, max(1, w * .07), max(1, w * .07), "#222733")


def lamp(p, w, h):
    shadow(p, w, h)
    rect(p, w / 2 - max(1, w * .12), h * .18, max(2, w * .24), h * .78, "#343a46")
    obox(p, w * .22, h, max(3, w * .45), max(2, h * .07), max(2, w * .2), "#2c313b")
    hw = w * .6
    ell(p, w / 2, h * .12, w * .7, h * .10, (255, 230, 120, 70))
    obox(p, w / 2 - hw / 2 - 1, h * .20, hw, max(3, h * .13), max(2, w * .22), "#ffe27a", "#fff6c0", "#e0b840")
    poly(p, [(w / 2 - hw / 2 - 1, h * .07), (w / 2 + hw / 2 + 1, h * .07), (w / 2 + hw / 2, h * .075 + 2), (w / 2 - hw / 2, h * .075 + 2)], "#343a46")
    rect(p, w / 2 - hw / 2, h * .04, hw, max(1, h * .04), SNOW)


def gift(p, w, h):
    shadow(p, w, h)
    d = max(2, round(w * .3))
    W, Hh = w - d, h - d / 2.0 - 2
    obox(p, 0, h - 1, W, Hh, d, "#d63a3a", "#f06a5a", "#9a2530")
    rect(p, W / 2 - max(1, W * .11), h - 1 - Hh, max(1, W * .22), Hh, "#f3c94a")
    poly(p, [(W / 2 - 1, h - 1 - Hh), (W / 2 + 1 + W * .0, h - 1 - Hh), (W / 2 + 1 + d, h - 1 - Hh - d / 2), (W / 2 - 1 + d, h - 1 - Hh - d / 2)], "#f3c94a")
    bw = max(2, w * .22)
    ell(p, W / 2 - bw * .6 + d / 2, h - 1 - Hh - d / 2 - 1, bw * .55, bw * .4, "#f3c94a")
    ell(p, W / 2 + bw * .6 + d / 2, h - 1 - Hh - d / 2 - 1, bw * .55, bw * .4, "#f3c94a")
    rect(p, W * .15 + d / 2, h - 1 - Hh - d / 2 - 1, max(2, W * .5), 1, SNOW)


def bench(p, w, h):
    shadow(p, w, h)
    d = max(2, round(h * .4))
    wood, dark = "#a0724a", "#6d4a2e"
    lw = max(1, w * .08)
    rect(p, w * .08, h * .5, lw, h * .46, dark)
    rect(p, w - d - w * .08 - lw, h * .5, lw, h * .46, dark)
    rect(p, d + w * .06, h * .5 - d / 2, lw, h * .3, dark)
    rect(p, w - w * .06 - lw, h * .5 - d / 2, lw, h * .3, dark)
    bh = max(2, h * .34)
    rect(p, d + 1, h * .5 - d / 2 - bh - 1, w - d - 2, bh, shade(wood, .9))
    rect(p, d + 1, h * .5 - d / 2 - bh - 1, w - d - 2, max(1, bh * .3), SNOW)
    sh = max(2, h * .16)
    obox(p, 0, h * .5 + sh - 1, w - d, sh, d, wood)
    rect(p, 1 + d / 2, h * .5 - sh / 2 - d / 2 - 1, w - d - 2, 1, SNOW)


def fence(p, w, h):
    shadow(p, w, h)
    wood, dark = "#b08556", "#76552f"
    pw = max(2, w * .09)
    rect(p, 0, h * .30, w, max(1, h * .11), dark)
    rect(p, 0, h * .58, w, max(1, h * .11), wood)
    for fx in (0.02, .34, .66, .90):
        x = fx * (w - pw)
        rect(p, x, h * .12, pw, h * .84, wood)
        rect(p, x - 0.5, h * .06, pw + 1, max(1, h * .12), SNOW)


def house(p, w, h):
    shadow(p, w, h)
    d = max(3, round(w * .26))
    W = w - d
    wall_h = h * .50
    yb = h - 1
    wall, roof, roof_dk = "#e8d2a6", "#b43a3a", "#7e2430"
    x0 = 0
    ytop = yb - wall_h
    ap = (x0 + W / 2.0, h * .02)
    # 옆면 벽, 지붕 옆면(경사), 앞면 벽, 앞 박공
    poly(p, [(x0 + W, ytop), (x0 + W + d, ytop - d / 2), (x0 + W + d, yb - d / 2), (x0 + W, yb)], shade(wall, .72))
    poly(p, [(ap[0], ap[1]), (x0 + W + 1, ytop), (x0 + W + d, ytop - d / 2), (ap[0] + d, ap[1] - d / 2 + 0)], roof_dk)
    rect(p, x0, ytop, W, wall_h, wall)
    poly(p, [(x0 - 1, ytop), (ap[0], ap[1]), (x0 + W + 1, ytop)], roof)
    poly(p, [(ap[0], ap[1]), (ap[0] + (W / 2 + 1) * .42, ap[1] + (ytop - ap[1]) * .42), (ap[0] - (W / 2 + 1) * .42, ap[1] + (ytop - ap[1]) * .42)], SNOW)
    cw = max(2, W * .16)
    rect(p, x0 + W * .72, h * .06, cw, h * .22, "#8a4a3a")
    rect(p, x0 + W * .72 - 0.5, h * .04, cw + 1, max(1, h * .05), SNOW)
    rect(p, x0 + W * .18, yb - wall_h * .62, max(3, W * .22), wall_h * .62, "#6d4a2e")
    ww = max(3, W * .24)
    rect(p, x0 + W * .56, ytop + wall_h * .22, ww, ww, "#ffe27a")
    rect(p, x0 + W * .56 + ww / 2 - .5, ytop + wall_h * .22, 1, ww, "#b98a2a")
    rect(p, x0 + W * .56, ytop + wall_h * .22 + ww / 2 - .5, ww, 1, "#b98a2a")


def rock(p, w, h):
    shadow(p, w, h)
    poly(p, [(0, h - 1), (w * .08, h * .52), (w * .32, h * .12), (w * .66, h * .06), (w * .92, h * .46), (w, h - 1)], "#7d8a9c")
    poly(p, [(w * .5, h * .06), (w * .66, h * .06), (w * .92, h * .46), (w, h - 1), (w * .72, h - 1), (w * .66, h * .5)], "#66727f")
    poly(p, [(w * .06, h * .55), (w * .32, h * .12), (w * .66, h * .06), (w * .88, h * .40), (w * .66, h * .34), (w * .5, h * .42), (w * .3, h * .36)], SNOW)


def ornament(p, w, h):
    shadow(p, w, h)
    r = min(w, h) * .40
    cy = h * .60
    ell(p, w / 2, cy, r, r, "#d63a3a", "#8f1f2a")
    ell(p, w / 2 - r * .35, cy - r * .35, max(1, r * .28), max(1, r * .22), (255, 255, 255, 200))
    rect(p, w / 2 - max(1, r * .3), cy - r - max(1, h * .05), max(2, r * .6), max(1, h * .07), "#f3c94a")
    rect(p, w / 2 - .5, cy - r - max(2, h * .12), 1, max(1, h * .07), "#f3c94a")
    rect(p, w / 2 - r * .9, cy + r * .05, r * 1.8, max(1, r * .22), "#f3c94a")
    ell(p, w / 2 - r * .5, cy - r - 0.5, max(1, r * .35), max(1, r * .25), "#3fa468")
    ell(p, w / 2 + r * .5, cy - r - 0.5, max(1, r * .35), max(1, r * .25), "#3fa468")


DRAW = {"small_tree": tree_small, "xmas_tree": tree_xmas, "snowman": snowman, "lamp": lamp, "gift": gift,
        "bench": bench, "fence": fence, "house": house, "rock": rock, "ornament": ornament}


def make_sprite(kind: str, scale: float) -> QImage:
    d = C.DECOR[kind]
    w, h = max(3, int(round(d["w"] * scale))), max(3, int(round(d["h"] * scale)))
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, False)
    try:
        DRAW[kind](p, float(w), float(h))
    finally:
        p.end()
    return img
