"""픽셀 전구 장식: 화면 가장자리(위/아래/왼쪽/오른쪽) 또는 원하는 위치(직접 배치)에 걸리는 전구 줄.

전구 줄은 가로 방향 로컬 좌표(u: 길이 방향, v: 깊이 방향)로 그리고, 가장자리에 따라 변환(회전/반전)한다.
정적인 전선은 QPixmap 으로 캐시하고, 전구 밝기가 바뀔 때만 다시 그린다.
"""
from __future__ import annotations
from core.i18n import tr


import math
import random

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from core.logger import get_logger
from .layer import TopBandMixin, apply_layer, show_layered

log = get_logger("lights")

PALETTES = {
    "multi": ["#ff4d4d", "#ffd23f", "#4dd36b", "#4da6ff", "#ff7ad9", "#ff9a3c"],
    "classic": ["#ff4d4d", "#4dd36b"],
    "warm": ["#ffd9a0", "#ffc067", "#ff9a3c"],
    "ice": ["#ffffff", "#8fd0f5", "#5aa7e8"],
    "candy": ["#ff7ad9", "#fff0f6", "#c767d6", "#8fd0f5"],
}
PALETTE_NAMES = {"multi": tr("알록달록"), "classic": tr("빨강/초록"), "warm": tr("따뜻한 빛"), "ice": tr("얼음빛"), "candy": tr("캔디")}
ANIM_NAMES = {"twinkle": tr("은은한 깜빡임"), "chase": tr("순차 점등"), "blink": tr("번갈아 점멸"), "steady": tr("항상 켜짐")}

# 전구 스프라이트 (5 x 8). 'S' 소켓, 'G' 유리(색), 'h' 하이라이트
BULB = [
    ".SSS.",
    ".SSS.",
    ".GGG.",
    "GGhGG",
    "GGGGG",
    "GGGGG",
    ".GGG.",
    "..G..",
]
BW, BH = 5, 8
LEVELS = 6
CORD = 2          # 전선에서 전구 소켓까지 줄 길이 (u)
SAG = 3           # 전선 처짐 (u)
SEG_BULBS = 10    # 고정 고리 간격 (전구 수)
WIRE_COLOR = "#1d3b2c"
SOCKET_COLOR = "#2a2f2a"


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def bulb_levels(anim: str, n: int, t: float, speed: float, phases: list) -> list:
    """전구 i 의 밝기(0~1)를 LEVELS 단계로 양자화해 돌려준다."""
    out = []
    sp = max(0.1, speed)
    if anim == "steady":
        return [LEVELS - 1] * n
    for i in range(n):
        if anim == "twinkle":
            v = 0.62 + 0.38 * math.sin(t * sp * 1.6 + i * 1.7 + phases[i])
        elif anim == "chase":
            pos = (t * sp * 5.0) % 6.0                        # 앞에서 뒤로 흐르는 점등
            d = ((i - pos) % 6.0)
            v = 1.0 if d < 2.0 else (0.45 if d < 3.0 else 0.15)
        else:   # blink
            v = 1.0 if (i + int(t * sp * 1.6)) % 2 == 0 else 0.12
        out.append(max(0, min(LEVELS - 1, int(v * (LEVELS - 1) + 0.5))))
    return out


class LightsWindow(TopBandMixin, QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self._t = 0.0
        self._n = 0
        self._phases: list = []
        self._last: tuple = ()
        self._static: QPixmap | None = None
        self._bulb_cache: dict = {}
        self._cfg_key = None
        self._drag: QPoint | None = None
        self._horizontal = True
        self._edge = "top"
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.CoarseTimer)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self.setMouseTracking(False)
        s = self.s
        s.changed.connect(self._on_setting)
        QGuiApplication.instance().screenAdded.connect(lambda _s: self.reconfigure())
        QGuiApplication.instance().screenRemoved.connect(lambda _s: self.reconfigure())
        self.reconfigure()

    # ------------------------------------------------------------ 설정
    def _on_setting(self, key: str):
        if key == "*" or key.startswith("lights."):
            self.reconfigure()

    @property
    def unit(self) -> int:
        return int(self.s.get("lights.size"))

    def _geometry(self) -> QRect:
        s, u = self.s, self.unit
        thick = (BH + CORD + SAG + 2) * u
        pos = s.get("lights.position")
        self._edge = pos
        if pos == "custom":
            vertical = bool(s.get("lights.custom_vertical"))
            length = int(s.get("lights.custom_length"))
            x, y = int(s.get("lights.custom_x")), int(s.get("lights.custom_y"))
            self._horizontal = not vertical
            rw, rh = (thick, length) if vertical else (length, thick)
            from core.geometry import clamp_pos           # 화면 밖에 남은 직접 배치 전구 보정
            x, y = clamp_pos(x, y, rw, rh)
            return QRect(x, y, rw, rh)
        screens = QGuiApplication.screens()
        sc = screens[min(int(s.get("lights.monitor")), len(screens) - 1)] if screens else QGuiApplication.primaryScreen()
        a = sc.availableGeometry()
        if pos == "top":
            self._horizontal = True
            return QRect(a.left(), a.top(), a.width(), thick)
        if pos == "bottom":
            self._horizontal = True
            return QRect(a.left(), a.bottom() + 1 - thick, a.width(), thick)
        self._horizontal = False
        if pos == "left":
            return QRect(a.left(), a.top(), thick, a.height())
        return QRect(a.right() + 1 - thick, a.top(), thick, a.height())

    def reconfigure(self):
        s = self.s
        if not s.get("lights.enabled"):
            self._timer.stop()
            self.hide()
            return
        click_through = not (s.get("lights.position") == "custom" and not s.get("lights.locked"))
        apply_layer(self, s.get("lights.layer"), click_through=click_through)
        if self._drag is None:
            geo = self._geometry()
            if geo != self.geometry():
                self.setGeometry(geo)
        self._invalidate()
        if not self.isVisible():
            show_layered(self)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _invalidate(self):
        self._static = None
        self._bulb_cache.clear()
        self._last = ()
        L = self.width() if self._horizontal else self.height()
        step = (BW + int(self.s.get("lights.spacing"))) * self.unit
        self._n = max(1, (L - 2 * self.unit) // step)
        rng = random.Random(7)
        self._phases = [rng.uniform(0, math.tau) for _ in range(self._n)]

    def resizeEvent(self, e):
        self._invalidate()

    # ------------------------------------------------------------ 애니메이션
    def _tick(self):
        if not self.isVisible():
            return
        self._t += 0.05
        levels = tuple(bulb_levels(self.s.get("lights.anim"), self._n, self._t,
                                   int(self.s.get("lights.speed")) / 100.0, self._phases))
        if levels != self._last:
            self._last = levels
            self.update()

    # ------------------------------------------------------------ 그리기
    def _bulb_pixmap(self, color_idx: int, level: int) -> QPixmap:
        key = (color_idx, level, self.unit, int(self.s.get("lights.brightness")), self.s.get("lights.palette"))
        pm = self._bulb_cache.get(key)
        if pm is not None:
            return pm
        u = self.unit
        pal = PALETTES[self.s.get("lights.palette")]
        base = QColor(pal[color_idx % len(pal)])
        bri = int(self.s.get("lights.brightness")) / 100.0
        t = (level / (LEVELS - 1)) * bri
        glass = _mix(QColor("#2a3a34"), base, 0.22 + 0.78 * t)
        hi = _mix(glass, QColor("#ffffff"), 0.5 * t + 0.1)
        m = 2                                              # 빛 번짐 여백 (u)
        pm = QPixmap((BW + 2 * m) * u, (BH + 2 * m) * u)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        if t > 0.3:                                        # 빛 번짐: 전구 주변 반투명 사각
            gc = QColor(base)
            for ring, alpha in ((2, 38), (1, 70)):
                gc.setAlpha(int(alpha * t))
                p.fillRect((m - ring) * u, (m + 2 - ring) * u, (BW + 2 * ring) * u, (BH - 2 + 2 * ring) * u, gc)
        for y, line in enumerate(BULB):
            for x, ch in enumerate(line):
                if ch == ".":
                    continue
                col = QColor(SOCKET_COLOR) if ch == "S" else (hi if ch == "h" else glass)
                p.fillRect((m + x) * u, (m + y) * u, u, u, col)
        p.end()
        self._bulb_cache[key] = pm
        return pm

    def _wire_pixmap(self) -> QPixmap:
        """전선과 걸이용 고리(로컬 가로 좌표)를 한 번만 그려 캐시한다."""
        u = self.unit
        L = self.width() if self._horizontal else self.height()
        thick = (BH + CORD + SAG + 2) * u
        pm = QPixmap(L, thick)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        wire = QColor(WIRE_COLOR)
        step = (BW + int(self.s.get("lights.spacing"))) * u
        seg = SEG_BULBS * step
        for x in range(0, L, u):
            ph = (x % seg) / seg
            sag = int(SAG * 4 * ph * (1 - ph) + 0.5)       # 고리 사이에서 늘어짐
            p.fillRect(x, sag * u, u, u, wire)
        for x in range(0, L, seg):                          # 고리 (핀)
            p.fillRect(x, 0, u, 2 * u, QColor("#c9b88e"))
        p.end()
        return pm

    def paintEvent(self, e):
        if self._n <= 0:
            return
        u = self.unit
        p = QPainter(self)
        L = self.width() if self._horizontal else self.height()
        edge = self._edge
        # 로컬(가로, 위에서 아래로 걸림) -> 위젯 좌표 변환
        if self._horizontal:
            if edge == "bottom":
                p.setTransform(QTransform(1, 0, 0, -1, 0, self.height()))
        else:
            if edge == "right":
                p.setTransform(QTransform(0, 1, -1, 0, self.width(), 0))
            else:
                p.setTransform(QTransform(0, 1, 1, 0, 0, 0))
        if self._static is None or self._static.width() != L:
            self._static = self._wire_pixmap()
        p.drawPixmap(0, 0, self._static)
        step = (BW + int(self.s.get("lights.spacing"))) * u
        seg = SEG_BULBS * step
        levels = self._last or tuple([LEVELS - 1] * self._n)
        m = 2
        for i in range(self._n):
            x = u + i * step
            ph = (x % seg) / seg
            sag = int(SAG * 4 * ph * (1 - ph) + 0.5)
            cx = x
            # 전선에서 소켓까지 줄
            p.fillRect(cx + (BW // 2) * u, (sag + 1) * u, u, CORD * u, QColor(WIRE_COLOR))
            pm = self._bulb_pixmap(i, levels[i] if i < len(levels) else LEVELS - 1)
            p.drawPixmap(cx - m * u, (sag + 1 + CORD - m) * u, pm)
        p.end()

    # ------------------------------------------------------------ 직접 배치 이동
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.s.get("lights.position") == "custom" and not self.s.get("lights.locked"):
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.s.set("lights.custom_x", self.x())
            self.s.set("lights.custom_y", self.y(), save=True)

    def shutdown(self):
        self._timer.stop()
        self.close()
