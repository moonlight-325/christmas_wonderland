"""스노우볼 렌더러: 96x112 논리 픽셀 이미지로 합성한다 (화면에는 정수 배 최근접 확대).

계층: [배경 + 바닥 (캐시)] -> [장식 스프라이트 와 눈송이를 깊이(Y)순으로 합성] -> [유리 + 받침대 (캐시)]
 - 배경/유리는 배경·외형이 바뀔 때만 다시 그리고, 프레임마다 그리는 것은 장식 이미지와 눈송이뿐이다.
 - 물리와 렌더링은 분리: 이 모듈은 physics.snapshot() 결과만 읽는다.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from . import catalog as C
from . import model as M
from .sprites import ell, make_sprite, mix, poly, qc, rect, shade

SPARK_COLORS = ("#fff6b0", "#ffd0f0", "#c8f0ff", "#ffffff")
_HZ = 60                                  # 배경 지평선 Y


def _new() -> tuple[QImage, QPainter]:
    img = QImage(C.GW, C.GH, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, False)
    return img, p


# ====================================================================== 배경
def _mini_house(p, x, y, w, h, wall, roof, lit=True):
    rect(p, x, y - h, w, h, wall)
    poly(p, [(x - 1, y - h), (x + w / 2.0, y - h - w * .45), (x + w + 1, y - h)], roof)
    poly(p, [(x + w / 2.0 - w * .2, y - h - w * .45 + w * .18), (x + w / 2.0, y - h - w * .45),
             (x + w / 2.0 + w * .2, y - h - w * .45 + w * .18)], "#ffffff")
    if lit:
        rect(p, x + w * .3, y - h * .65, max(1, w * .28), max(1, w * .28), "#ffe27a")


def _pine(p, x, y, h, col):
    for i in range(3):
        top = y - h + i * h * .26
        hw = h * (.16 + i * .1)
        poly(p, [(x, top), (x + hw, top + h * .36), (x - hw, top + h * .36)], col)
        poly(p, [(x, top), (x + hw * .5, top + h * .16), (x - hw * .5, top + h * .16)], "#ffffff")
    rect(p, x - 1, y - h * .1, 2, max(1, h * .1), "#4d3220")


def _scene(p, key):
    rng = random.Random(key)
    if key == "village":
        for x, w, h, wall in ((12, 11, 8, "#c98a5a"), (26, 9, 7, "#d9b27a"), (60, 10, 9, "#b86a5a"), (74, 11, 7, "#c9a06a")):
            _mini_house(p, x, _HZ + 2, w, h, wall, "#6a3a3a")
        rect(p, 46, _HZ - 12, 5, 14, "#a89080")
        poly(p, [(45, _HZ - 12), (48.5, _HZ - 22), (52, _HZ - 12)], "#6a3a3a")
        rect(p, 47.5, _HZ - 8, 2, 2, "#ffe27a")
    elif key == "forest":
        for i, x in enumerate(range(6, 96, 9)):
            _pine(p, x + rng.randint(-2, 2), _HZ + 2, 20 + rng.randint(0, 6), "#1b4f3a")
        for x in range(10, 96, 14):
            _pine(p, x + rng.randint(-3, 3), _HZ + 6, 14 + rng.randint(0, 4), "#2a6a4c")
    elif key == "plaza":
        for x, w, h, c in ((8, 12, 22, "#4a3a6e"), (22, 10, 28, "#3e2f60"), (36, 9, 18, "#5a4a7e"), (58, 10, 24, "#4a3a6e"),
                           (70, 12, 30, "#3e2f60"), (84, 10, 20, "#5a4a7e")):
            rect(p, x, _HZ + 2 - h, w, h, c)
            for wy in range(int(_HZ + 4 - h), _HZ - 2, 5):
                for wx in range(int(x + 2), int(x + w - 2), 4):
                    if rng.random() < .6:
                        rect(p, wx, wy, 2, 2, "#ffe27a")
        for x in (30, 66):
            rect(p, x, _HZ - 8, 1, 12, "#2a2a3a")
            ell(p, x + .5, _HZ - 9, 2.5, 2.5, (255, 230, 140, 140))
    elif key == "mountain":
        poly(p, [(0, _HZ + 4), (22, _HZ - 28), (40, _HZ + 4)], "#5a7a9a")
        poly(p, [(30, _HZ + 4), (60, _HZ - 36), (96, _HZ + 4)], "#4a6a8a")
        poly(p, [(60, _HZ - 36), (66, _HZ - 24), (60, _HZ - 27), (55, _HZ - 22), (52, _HZ - 28)], "#ffffff")
        poly(p, [(22, _HZ - 28), (27, _HZ - 19), (22, _HZ - 21), (17, _HZ - 16), (16, _HZ - 20)], "#ffffff")
        poly(p, [(0, _HZ + 6), (20, _HZ - 4), (46, _HZ + 6)], "#dbe8f5")
        poly(p, [(40, _HZ + 6), (72, _HZ - 6), (96, _HZ + 6)], "#e8f1fa")
    elif key == "cabin":
        for x in (10, 20, 78, 88):
            _pine(p, x, _HZ + 3, 18 + rng.randint(0, 4), "#1b4f3a")
        _mini_house(p, 34, _HZ + 3, 26, 14, "#7a5233", "#8a3b2a")
        rect(p, 52, _HZ - 24, 4, 8, "#6a4a3a")
        for i, (dx, dy) in enumerate(((0, 0), (2, -4), (0, -8), (3, -12))):
            ell(p, 54 + dx, _HZ - 26 + dy, 2 + i * .4, 1.6 + i * .3, (235, 240, 250, 150 - i * 25))
        rect(p, 40, _HZ - 5, 5, 7, "#4d3220")
    else:                                                    # xmas_town
        cols = (("#c43a3a", "#2f7a4a"), ("#2f7a4a", "#c43a3a"), ("#3a5ab8", "#c43a3a"), ("#c9a030", "#3a5ab8"),
                ("#c43a3a", "#2f7a4a"))
        for i, x in enumerate((6, 21, 36, 54, 70)):
            _mini_house(p, x, _HZ + 3, 12, 9 + (i % 2) * 3, cols[i][0], cols[i][1])
        for i in range(0, 96, 4):
            y = _HZ - 16 + int(5 * math.sin(i / 96.0 * math.pi * 3))
            rect(p, i, y, 2, 2, ("#e84a4a", "#ffd84a", "#4ae884")[(i // 4) % 3])
        poly(p, [(84, _HZ - 20), (86, _HZ - 24), (88, _HZ - 20), (92, _HZ - 19), (89, _HZ - 16), (90, _HZ - 12), (86, _HZ - 14),
                 (82, _HZ - 12), (83, _HZ - 16), (80, _HZ - 19)], "#ffd84a")


def draw_background(key: str) -> QImage:
    """배경 + 바닥. 유리 안쪽 원으로 잘라 그린다."""
    bg = C.BACKGROUNDS.get(key) or C.BACKGROUNDS[C.DEFAULT_BACKGROUND]
    img, p = _new()
    clip = QPainterPath()
    clip.addEllipse(QPointF(C.SCX, C.SCY), C.SR - 0.5, C.SR - 0.5)
    p.setClipPath(clip)
    top, bot = bg["sky"]
    y0 = int(C.SCY - C.SR)
    for y in range(y0, int(C.SCY + C.SR) + 2):
        rect(p, 0, y, C.GW, 1, mix(top, bot, min(1.0, (y - y0) / (2.0 * C.SR * 0.62))))
    rng = random.Random(key + "stars")
    for _ in range(28):
        x, y = rng.randint(10, 86), rng.randint(y0 + 2, _HZ - 14)
        rect(p, x, y, 1, 1, (255, 255, 255, rng.randint(90, 230)))
    _scene(p, key)
    g0, g1 = bg["ground"]
    rect(p, 0, _HZ + 3, C.GW, C.GH - _HZ, mix(g1, g0, 0.35))                    # 지평선 아래 눈밭
    for y in range(_HZ + 3, _HZ + 9):
        rect(p, 0, y, C.GW, 1, mix(g0, g1, (y - _HZ - 3) / 8.0 * .5))
    ell(p, C.GX, C.GY + 3, C.GRX + 1.5, C.GRY + 1, shade(g1, .78))                # 바닥 원판의 두께
    ell(p, C.GX, C.GY, C.GRX, C.GRY, g0, shade(g1, .9))
    ell(p, C.GX - 4, C.GY - 2, C.GRX * .55, C.GRY * .5, (255, 255, 255, 90))
    p.end()
    return img


# ====================================================================== 유리 + 받침대
def _base(p, d: dict):
    pal = d["pal"]
    main, hi, lo, trim = pal["main"], pal["hi"], pal["lo"], pal["trim"]
    kind = d["base"]
    ell(p, 48, 108, 36, 3, (0, 0, 0, 60))
    if kind == "round":
        ell(p, 48, 101, 33, 7, lo)
        poly(p, [(20, 84), (76, 84), (82, 101), (14, 101)], main)
        poly(p, [(20, 84), (28, 84), (23, 101), (14, 101)], hi)
        poly(p, [(68, 84), (76, 84), (82, 101), (74, 101)], lo)
        rect(p, 17, 91, 62, 2, trim)
        ell(p, 48, 101, 33, 6, main)
        rect(p, 15, 100, 66, 1, trim)
        ell(p, 48, 83, 28, 6, trim)
        ell(p, 48, 83, 25, 4.5, lo)
    elif kind == "soft":
        ell(p, 48, 96, 37, 13, lo)
        ell(p, 48, 95, 36, 12, main)
        ell(p, 38, 91, 22, 6, hi)
        for x in range(14, 83, 8):
            ell(p, x, 105, 4, 3, trim)
        ell(p, 48, 83, 28, 6, hi)
        ell(p, 48, 83, 25, 4.5, lo)
    elif kind == "log":
        ell(p, 48, 106, 31, 4, lo)
        rect(p, 18, 84, 60, 22, main)
        for y in (89, 94, 99, 104):
            rect(p, 18, y, 60, 1, lo)
        for x in (28, 38, 48, 58, 68):
            rect(p, x, 84, 1, 22, shade(main, .85))
        rect(p, 18, 84, 3, 22, hi)
        rect(p, 75, 84, 3, 22, lo)
        ell(p, 48, 83, 31, 6, "#ffffff")
        ell(p, 48, 83, 27, 5, trim)
        ell(p, 48, 83, 24, 4, lo)
    elif kind == "block":
        rect(p, 24, 82, 48, 4, trim)
        rect(p, 24, 86, 48, 4, hi)
        rect(p, 17, 90, 62, 9, main)
        rect(p, 17, 90, 62, 1, hi)
        rect(p, 10, 99, 76, 10, lo)
        rect(p, 10, 99, 76, 1, main)
        for x in range(21, 76, 9):
            rect(p, x, 94, 3, 3, trim)
        for x in range(14, 82, 12):
            rect(p, x, 103, 6, 2, shade(lo, 1.4))
    else:                                                    # gold
        ell(p, 48, 105, 40, 5, lo)
        ell(p, 48, 99, 38, 6, main)
        ell(p, 48, 91, 31, 6, hi)
        ell(p, 48, 83, 27, 5, trim)
        ell(p, 48, 83, 24, 4, lo)
        poly(p, [(48, 93), (51, 97), (48, 101), (45, 97)], trim)
        for x in (22, 74):
            ell(p, x, 99, 2, 2, trim)
        pen = QPen(qc(hi), 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(C.SCX, C.SCY), C.SR + 2.5, C.SR + 2.5)             # 장식 프레임: 금빛 고리
        for ang in (0, 90, 180, 270):
            ell(p, C.SCX + math.cos(math.radians(ang)) * (C.SR + 2.5), C.SCY + math.sin(math.radians(ang)) * (C.SR + 2.5),
                2, 2, trim)


def _rim(p, d: dict):
    """유리와 받침이 만나는 테두리 장식."""
    pal = d["pal"]
    kind = d["rim"]
    if kind == "wave":
        for x in range(26, 71, 6):
            ell(p, x, 86, 3, 2, pal["trim"])
    elif kind == "stud":
        for x in range(26, 71, 8):
            rect(p, x, 85, 2, 2, pal["trim"])
    elif kind == "plank":
        for x in range(26, 71, 7):
            rect(p, x, 85, 1, 3, pal["lo"])
    elif kind == "arch":
        for x in (30, 48, 66):
            ell(p, x, 87, 3, 2, pal["trim"])


def draw_front(design: str) -> QImage:
    d = C.DESIGNS.get(design) or C.DESIGNS[C.DEFAULT_DESIGN]
    img, p = _new()
    r, g, b, a = d["glass"]
    # 유리 색조와 가장자리 어둡힘 (구형 입체감)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(r, g, b, a))
    p.drawEllipse(QPointF(C.SCX, C.SCY), C.SR - 0.5, C.SR - 0.5)
    for i, al in enumerate((46, 30, 16)):
        p.setPen(QPen(QColor(10, 20, 50, al), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(C.SCX, C.SCY), C.SR - 1.5 - i, C.SR - 1.5 - i)
    # 외곽선
    p.setPen(QPen(qc(d["line"], 210), 1))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(C.SCX, C.SCY), C.SR, C.SR)
    # 빛 반사: 왼쪽 위 큰 호, 작은 호, 오른쪽 아래 옅은 호, 반짝임
    def arc(a0, a1, rad, alpha, col=(255, 255, 255), thick=2):
        for deg in range(a0, a1):
            t = math.radians(deg)
            x, y = C.SCX + math.cos(t) * rad, C.SCY + math.sin(t) * rad
            p.fillRect(int(round(x)), int(round(y)), thick, 1 if thick == 2 and 225 < deg < 255 else thick,
                       QColor(col[0], col[1], col[2], alpha))
    arc(198, 262, C.SR - 5, 190)
    arc(272, 292, C.SR - 5, 120, thick=1)
    arc(16, 58, C.SR - 4, 70, (210, 235, 255), 1)
    for (x, y, w, al) in ((C.SCX - 24, C.SCY - 22, 2, 230), (C.SCX - 18, C.SCY - 29, 1, 200), (C.SCX + 18, C.SCY - 27, 1, 140)):
        p.fillRect(int(x), int(y), w, w, QColor(255, 255, 255, al))
    _rim(p, d)
    p.end()
    return img


def draw_base(design: str) -> QImage:
    """받침대만 별도 레이어로 그린다. 스노우볼 구체보다 먼저 합성해 뒤쪽에 배치한다."""
    d = C.DESIGNS.get(design) or C.DESIGNS[C.DEFAULT_DESIGN]
    img, p = _new()
    _base(p, d)
    p.end()
    return img


# ====================================================================== 합성
class GlobeRenderer:
    """공유 캐시를 가진 렌더러. 모든 스노우볼이 같은 인스턴스를 써도 상태(스노우볼별 물리)는 섞이지 않는다."""

    def __init__(self):
        self._back: dict[str, QImage] = {}
        self._front: dict[str, QImage] = {}
        self._base: dict[str, QImage] = {}
        self._spr: dict[tuple, QImage] = {}

    def sprite(self, kind: str, scale: float) -> QImage:
        key = (kind, round(scale, 2))
        im = self._spr.get(key)
        if im is None:
            if len(self._spr) > 400:
                self._spr.clear()
            im = self._spr[key] = make_sprite(kind, scale)
        return im

    def back(self, bg: str) -> QImage:
        im = self._back.get(bg)
        if im is None:
            im = self._back[bg] = draw_background(bg)
        return im

    def base(self, design: str) -> QImage:
        im = self._base.get(design)
        if im is None:
            im = self._base[design] = draw_base(design)
        return im

    def front(self, design: str) -> QImage:
        im = self._front.get(design)
        if im is None:
            im = self._front[design] = draw_front(design)
        return im

    def render(self, state: dict, snapshot: list) -> QImage:
        img = QImage(C.GW, C.GH, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(0, 0, self.back(state["background"]))
        p.drawImage(0, 0, self.base(state["design"]))  # 받침을 구체 뒤 레이어에 먼저 그림

        clip = QPainterPath()
        clip.addEllipse(QPointF(C.SCX, C.SCY), C.SR - 1.0, C.SR - 1.0)
        p.setClipPath(clip)
        size = state["snow"]["size"]
        # 장식(앵커 Y)과 눈송이(깊이)를 한 목록으로 합쳐 뒤쪽부터 그린다 (깊이 Z 없이 겹침 처리)
        order = []
        for it in M.draw_order(state["decor"]):
            order.append((it["y"], 0, it))
        for fl in snapshot:
            order.append((fl[5], 1, fl))
        order.sort(key=lambda t: (t[0], t[1]))
        for _d, typ, obj in order:
            if typ == 0:
                self._draw_item(p, obj)
            else:
                self._draw_flake(p, obj, size)
        p.setClipping(False)
        p.drawImage(0, 0, self.front(state["design"]))
        p.end()
        return img

    def _draw_item(self, p: QPainter, it: dict):
        im = self.sprite(it["kind"], it["scale"])
        rot = it["rot"] % 360
        if rot == 0:
            p.drawImage(int(round(it["x"] - im.width() / 2.0)), int(round(it["y"] - im.height())), im)
            return
        p.save()
        p.translate(it["x"], it["y"])
        p.rotate(rot)
        p.drawImage(int(round(-im.width() / 2.0)), -im.height(), im)
        p.restore()

    def _draw_flake(self, p: QPainter, f: tuple, size: float):
        x, y, kind, ph, rest, _d = f
        ix, iy = int(x), int(y)
        if kind == 0:
            s = max(1, int(round(size)))
            p.fillRect(ix, iy, s, s, QColor(255, 255, 255, 235))
        elif kind == 1:
            s = max(1, int(round(size * 1.0)))
            arm = QColor(215, 235, 255, 230)
            p.fillRect(ix - s, iy, 3 * s, s, arm)
            p.fillRect(ix, iy - s, s, 3 * s, arm)
            p.fillRect(ix, iy, s, s, QColor(255, 255, 255, 255))
        else:
            tw = (math.sin(ph * 1.7) + 1.0) * 0.5
            col = QColor(SPARK_COLORS[int(ph) % 4])
            col.setAlpha(int(110 + 145 * tw))
            p.fillRect(ix, iy, 1, 1, col)
            if tw > 0.72:
                col.setAlpha(150)
                p.fillRect(ix - 1, iy, 3, 1, col)
                p.fillRect(ix, iy - 1, 1, 3, col)
