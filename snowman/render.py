"""눈덩이/눈사람 픽셀아트 그리기 (QPainter). 물리 좌표(전역 물리 픽셀)에 그대로 그린다 - 눈 오버레이가 호출한다."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen

from . import model as M

BODY = QColor(242, 248, 255)
SHADE = QColor(196, 218, 238)
SHADE2 = QColor(168, 198, 226)
HILITE = QColor(255, 255, 255)
OUTLINE = QColor(122, 160, 198)
GOLD = QColor("#f3c94a")
SKY = QColor("#8fd0f5")
_COLS: dict = {}


def _col(name: str) -> QColor:
    c = _COLS.get(name)
    if c is None:
        c = QColor(M.COLORS.get(name, "#d63a3a"))
        _COLS[name] = c
    return c


def _snap(v: float, u: int) -> float:
    return round(v / u) * u


def draw_ball(p, x: float, y: float, r: float, u: int, ang: float = 0.0, marks: bool = False):
    """픽셀 격자로 그린 눈덩이: 윤곽 + 몸통 + 아래쪽 그림자 + 왼쪽 위 하이라이트. marks=True 면 굴러가는 무늬를 그린다."""
    n = max(1, int(r // u))
    top = y - n * u
    fill = p.fillRect
    rows = 2 * n
    for k in range(rows + 1):
        yy = (k - n) * u + u / 2.0
        if abs(yy) > r + u:
            continue
        half = math.sqrt(max(0.0, (r + u) * (r + u) - yy * yy))
        w = max(u, int(half / u + 0.5) * u * 2)
        fill(QRectF(x - w / 2.0, top + k * u, w, u), OUTLINE)
    for k in range(rows + 1):
        yy = (k - n) * u + u / 2.0
        if abs(yy) > r:
            continue
        half = math.sqrt(max(0.0, r * r - yy * yy))
        w = max(u, int(half / u + 0.5) * u * 2)
        left = x - w / 2.0
        ry = top + k * u
        fill(QRectF(left, ry, w, u), BODY)
        if yy > -r * 0.15:
            sw = max(u, int(w * (0.22 + 0.35 * (yy + r * 0.15) / (r * 1.15)) / u) * u)
            fill(QRectF(left + w - sw, ry, sw, u), SHADE)
            if yy > r * 0.55:
                fill(QRectF(left + w - sw, ry, sw, u), SHADE2)
        if k <= max(2, n // 3) and k >= 1:
            hw = max(u, int(w * 0.28 / u) * u)
            fill(QRectF(left + w * 0.18, ry, hw, u), HILITE)
    if marks and r > 3 * u:
        for i in range(3):
            a = ang + i * 2.1
            mx = x + math.cos(a) * r * 0.55
            my = y + math.sin(a) * r * 0.55
            if math.sin(a * 0.5 + 0.3) > -0.2:
                fill(QRectF(_snap(mx, u), _snap(my, u), u, u), SHADE2)


# ---------------------------------------------------------------- 장식 그리기
def draw_decor(p, d: dict, cx: float, cy: float, r: float, u: int, ang: float = 0.0):
    """구 하나(중심 cx,cy 반지름 r)에 붙은 장식 하나. 구의 기울기(ang)와 함께 회전한다."""
    kind, style = d["kind"], d["style"]
    s = r * d["size"] / 100.0
    ox, oy = r * d["dx"] / 100.0, r * d["dy"] / 100.0
    col = _col(d["color"])
    dark = col.darker(150)
    light = col.lighter(150)
    white = HILITE
    black = _col("black")
    p.save()
    p.translate(cx, cy)
    if ang:
        p.rotate(math.degrees(ang))

    def R(x, y, w, h, c):
        x0 = _snap(ox + x * s, u)
        y0 = _snap(oy + y * s, u)
        w0 = max(u, _snap(w * s, u))
        h0 = max(u, _snap(h * s, u))
        p.fillRect(QRectF(x0, y0, w0, h0), c)

    def L(x1, y1, x2, y2, c, wd=0.11):
        pen = QPen(c, max(u, _snap(wd * s, u)))
        pen.setCapStyle(Qt.SquareCap)
        p.setPen(pen)
        p.drawLine(QPointF(_snap(ox + x1 * s, u), _snap(oy + y1 * s, u)),
                   QPointF(_snap(ox + x2 * s, u), _snap(oy + y2 * s, u)))
        p.setPen(Qt.NoPen)

    p.setPen(Qt.NoPen)
    if kind == "hat":
        if style == "tophat":
            R(-0.74, -0.96, 1.48, 0.16, dark)
            R(-0.46, -1.68, 0.92, 0.76, col)
            R(-0.46, -1.06, 0.92, 0.14, light if d["color"] == "black" else dark)
        elif style == "santa":
            R(-0.78, -0.96, 1.56, 0.22, white)
            R(-0.66, -1.16, 1.32, 0.22, col)
            R(-0.52, -1.36, 1.04, 0.22, col)
            R(-0.38, -1.56, 0.76, 0.22, col)
            R(-0.1, -1.76, 0.6, 0.22, col)
            R(0.3, -1.66, 0.26, 0.26, white)
        else:
            R(-0.7, -0.96, 1.4, 0.22, dark)
            R(-0.6, -1.16, 1.2, 0.22, col)
            R(-0.46, -1.36, 0.92, 0.22, col)
            R(-0.28, -1.54, 0.56, 0.2, col)
            R(-0.14, -1.72, 0.28, 0.2, white)
    elif kind == "scarf":
        if style == "stripe":
            for i in range(7):
                R(-0.98 + i * 0.28, 0.52 + abs(i - 3) * 0.04, 0.28, 0.34, col if i % 2 == 0 else white)
            R(0.42, 0.8, 0.3, 0.74, col)
            R(0.42, 1.1, 0.3, 0.14, white)
        else:
            R(-0.98, 0.52, 1.96, 0.36, col)
            R(0.42, 0.8, 0.3, 0.74, col)
            R(-0.98, 0.78, 1.96, 0.1, dark)
    elif kind == "eyes":
        if style == "happy":
            for ex in (-0.46, 0.26):
                R(ex, -0.36, 0.2, 0.07, black)
                R(ex - 0.06, -0.29, 0.07, 0.12, black)
                R(ex + 0.19, -0.29, 0.07, 0.12, black)
        else:
            R(-0.42, -0.34, 0.16, 0.16, black)
            R(0.26, -0.34, 0.16, 0.16, black)
    elif kind == "nose":
        if style == "button":
            R(-0.1, -0.08, 0.2, 0.2, col)
            R(-0.1, -0.08, 0.1, 0.1, light)
        else:
            R(0.0, -0.1, 0.34, 0.12, col)
            R(0.34, -0.08, 0.24, 0.1, col)
            R(0.58, -0.06, 0.16, 0.07, dark)
    elif kind == "mouth":
        if style == "round":
            R(-0.1, 0.3, 0.22, 0.22, col)
        else:
            for mx, my in ((-0.38, 0.26), (-0.24, 0.36), (-0.06, 0.4), (0.12, 0.36), (0.26, 0.26)):
                R(mx, my, 0.12, 0.12, col)
    elif kind == "buttons":
        ys = (-0.42, 0.0, 0.42) if style == "three" else (-0.2, 0.26)
        for by in ys:
            R(-0.09, by, 0.18, 0.18, col)
    elif kind == "arms":
        up = style == "wave"
        for sg in (-1, 1):
            tx, ty = (1.5, -1.0) if up else (1.8, -0.55)
            L(sg * 0.8, -0.1, sg * tx, ty, col, 0.1)
            L(sg * (0.8 + (tx - 0.8) * 0.55), -0.1 + (ty + 0.1) * 0.55,
              sg * (0.8 + (tx - 0.8) * 0.55 + 0.3), -0.1 + (ty + 0.1) * 0.55 - 0.28, col, 0.07)
    elif kind == "gloves":
        up = False
        for sg in (-1, 1):
            gx, gy = sg * 1.72, -0.5
            if style == "round":
                R(gx - 0.2, gy - 0.2, 0.4, 0.4, col)
                R(gx - 0.2, gy - 0.2, 0.2, 0.2, light)
            else:
                R(gx - 0.18, gy - 0.22, 0.36, 0.44, col)
                R(gx - 0.18 + (0.0 if sg < 0 else 0.0), gy - 0.32, 0.18, 0.14, col)
                R(gx - 0.18, gy + 0.12, 0.36, 0.1, dark)
    p.restore()


_PROP_DY = {"hat": 1.2, "scarf": -0.7, "eyes": 0.3, "nose": 0.1, "mouth": -0.2, "buttons": 0.1, "arms": 0.5, "gloves": 0.5}


# ---------------------------------------------------------------- 전체 그리기
def _bbox(parts):
    x0 = min(c[0] - c[2] for c in parts)
    x1 = max(c[0] + c[2] for c in parts)
    y0 = min(c[1] - c[2] for c in parts)
    y1 = max(c[1] + c[2] for c in parts)
    return x0, y0, x1, y1


def _brackets(p, box, u, color, tag):
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = x0 - 3 * u, y0 - 3 * u, x1 + 3 * u, y1 + 3 * u
    ln = max(6 * u, int((x1 - x0) * 0.2))
    for (cx, cy, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        p.fillRect(QRectF(min(cx, cx + dx * ln), cy if dy > 0 else cy - u, ln, u), color)
        p.fillRect(QRectF(cx if dx > 0 else cx - u, min(cy, cy + dy * ln), u, ln), color)
    p.fillRect(QRectF(x0, y0 - 5 * u, 4 * u, 4 * u), tag)          # 종류 표시 (파랑 = 직접 제작 / 금색 = 장식용)


def paint_world(p, world, pl, pt, pr, pb):
    sim = world.sim
    u = max(1, int(sim.cell))
    drawables = []
    for sn in world.snowmen.values():
        if sn.type == M.DECORATIVE:
            parts = world.deco_parts(sn)
            drawables.append((parts[0][1] + parts[0][2], "deco", sn, parts))
        else:
            bs = [world.balls[i] for i in sn.balls if i in world.balls]
            if bs:
                drawables.append((bs[0].y + bs[0].r, "dyn", sn, bs))
    for b in world.balls.values():
        if b.sid is None:
            drawables.append((b.y + b.r, "ball", b, [b]))
    drawables.sort(key=lambda t: t[0])
    for _y, kind, ent, parts in drawables:
        if kind == "deco":
            if not _visible(parts, pl, pt, pr, pb):
                continue
            for i, (cx, cy, r, a) in enumerate(parts):
                draw_ball(p, cx, cy, r, u)
            for d in ent.decor:
                idx = 1 if M.role_of(d["kind"]) == "body" else 2
                cx, cy, r, a = parts[idx]
                draw_decor(p, d, cx, cy, r, u, a)
            box = _bbox(parts)
            tag = GOLD
        elif kind == "dyn":
            if not _visible([(b.x, b.y, b.r, 0) for b in parts], pl, pt, pr, pb):
                continue
            for b in parts:
                draw_ball(p, b.x, b.y, b.r, u)
                for d in b.decor:
                    draw_decor(p, d, b.x, b.y, b.r, u, ent.tilt)
            box = _bbox([(b.x, b.y, b.r) for b in parts])
            tag = SKY
        else:
            b = ent
            if not _visible([(b.x, b.y, b.r, 0)], pl, pt, pr, pb):
                continue
            draw_ball(p, b.x, b.y, b.r, u, b.ang, marks=True)
            for d in b.decor:
                draw_decor(p, d, b.x, b.y, b.r, u, b.ang)
            box = _bbox([(b.x, b.y, b.r)])
            tag = SKY
        if world.selected == ent.id:
            # 직접 제작(dynamic) 눈사람의 선택 테두리는 10초간만 표시한다.
            show_selection = (world.kind_of(ent.id) != M.DYNAMIC
                              or time.monotonic() - getattr(world, "selected_at", 0.0) < 10.0)
            if show_selection:
                _brackets(p, box, u, GOLD, tag)
    for pr_ in world.props:
        x, y = pr_["x"], pr_["y"]
        if x < pl - 60 or x > pr + 60 or y < pt - 60 or y > pb + 60:
            continue
        s = pr_.get("r", 20.0)
        d = {"kind": pr_["kind"], "style": pr_["style"], "color": pr_["color"], "dx": 0,
             "dy": 0, "size": int(pr_.get("size", 100))}
        draw_decor(p, d, x, y - _PROP_DY.get(pr_["kind"], 0.0) * s * 0.0 + _PROP_DY.get(pr_["kind"], 0.0) * s * 0.9,
                   s, u)
    # 조립 가능 표시: 위에 올릴 눈덩이 둘레에 점선 고리 + 진행 막대
    for lo, up, prog in world.hints:
        B = world.balls.get(up)
        A = world.balls.get(lo)
        if B is None or A is None:
            continue
        pen = QPen(GOLD, max(1, u - 1), Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(B.x, B.y), B.r + 3 * u, B.r + 3 * u)
        p.setPen(Qt.NoPen)
        bw = max(8 * u, int(2 * A.r * 0.8))
        bx = A.x - bw / 2.0
        by = A.y - A.r - 4 * u
        p.fillRect(QRectF(bx, by, bw, u * 2), QColor(15, 47, 38, 200))
        p.fillRect(QRectF(bx, by, bw * prog, u * 2), GOLD)


def _visible(parts, pl, pt, pr, pb) -> bool:
    for c in parts:
        x, y, r = c[0], c[1], c[2]
        if x + r >= pl - 80 and x - r <= pr + 80 and y + r >= pt - 200 and y - r <= pb + 80:
            return True
    return False
