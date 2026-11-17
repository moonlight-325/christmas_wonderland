"""파티클 효과 / 미니게임 로직.  step() 은 순수 Python, paint() 만 Qt 를 사용한다."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class P:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: tuple
    shape: str = "dot"       # dot | rect | star
    rot: float = 0.0
    vrot: float = 0.0
    gravity: float = 0.0
    drag: float = 0.0
    twinkle: bool = False


CONFETTI = [(231, 76, 60), (241, 196, 15), (46, 204, 113), (52, 152, 219), (155, 89, 182), (255, 255, 255)]


class FxEngine:
    """kind: snowfall | confetti | stars | lights | fireworks | sparkle"""

    def __init__(self, kind: str, w: int, h: int, duration: float = 6.0, rng: random.Random | None = None):
        self.kind, self.w, self.h = kind, max(1, w), max(1, h)
        self.duration = duration          # 0 이면 무한 (배경 눈)
        self.rng = rng or random.Random()
        self.t = 0.0
        self.ps: list[P] = []
        self._acc = 0.0
        self._burst_done = False
        self.origin: tuple[float, float] | None = None   # sparkle 효과의 시작점(기본: 중앙 위쪽)

    @property
    def finished(self) -> bool:
        return self.duration > 0 and self.t >= self.duration + 1.2      # 페이드 아웃(1.2초)이 끝나면 종료

    def resize(self, w: int, h: int):
        self.w, self.h = max(1, w), max(1, h)

    @property
    def fade(self) -> float:
        """종료 직전 서서히 사라지게 하는 전체 알파 계수."""
        if self.duration <= 0:
            return 1.0
        return max(0.0, min(1.0, (self.duration + 1.2 - self.t) / 1.2)) if self.t > self.duration else 1.0

    # ---- 생성
    def _spawn(self, dt: float):
        r, w, h = self.rng, self.w, self.h
        active = self.duration <= 0 or self.t < self.duration
        if self.kind == "snowfall" and active:
            self._acc += dt * (60 if self.duration > 0 else 40)
            while self._acc >= 1:
                self._acc -= 1
                s = r.uniform(1.5, 4.2)
                self.ps.append(P(r.uniform(0, w), -6, r.uniform(-12, 12), r.uniform(40, 110), 99, 99, s,
                                 (255, 255, 255), gravity=0, twinkle=False))
        elif self.kind == "confetti":
            if not self._burst_done:
                self._burst_done = True
                for _ in range(140):
                    a = r.uniform(math.pi * 1.1, math.pi * 1.9)
                    sp = r.uniform(260, 620)
                    side = r.choice((0.15, 0.85))
                    self.ps.append(P(w * side, h * 0.75, abs(math.cos(a)) * sp * 0.7 * (1 if side < .5 else -1),
                                     math.sin(a) * sp, r.uniform(2.5, 4.5), 4.5, r.uniform(5, 10), r.choice(CONFETTI),
                                     "rect", r.uniform(0, 6.28), r.uniform(-9, 9), 520, 0.6))
            if active and self.t < self.duration * 0.6:
                self._acc += dt * 30
                while self._acc >= 1:
                    self._acc -= 1
                    self.ps.append(P(r.uniform(0, w), -10, r.uniform(-40, 40), r.uniform(80, 160), 5, 5, r.uniform(5, 9),
                                     r.choice(CONFETTI), "rect", r.uniform(0, 6.28), r.uniform(-6, 6), 40, 0.1))
        elif self.kind == "stars" and active:
            self._acc += dt * 14
            while self._acc >= 1:
                self._acc -= 1
                life = r.uniform(1.2, 2.6)
                self.ps.append(P(r.uniform(0, w), r.uniform(0, h * 0.8), 0, 0, life, life, r.uniform(4, 11),
                                 r.choice([(255, 236, 160), (255, 255, 255), (190, 220, 255)]), "star", 0, r.uniform(-1, 1), twinkle=True))
            if r.random() < dt * 0.9:                      # 별똥별
                self.ps.append(P(r.uniform(w * .3, w), r.uniform(0, h * .3), -520, 300, 0.9, 0.9, 3, (255, 255, 230), "dot"))
        elif self.kind == "fireworks" and active:
            self._acc += dt
            if self._acc >= 0.55:
                self._acc = 0
                cx, cy = r.uniform(w * .15, w * .85), r.uniform(h * .12, h * .5)
                col = r.choice(CONFETTI[:5])
                for i in range(46):
                    a = i / 46 * math.tau
                    sp = r.uniform(110, 230)
                    self.ps.append(P(cx, cy, math.cos(a) * sp, math.sin(a) * sp, r.uniform(1.0, 1.7), 1.7, r.uniform(2.5, 4.5),
                                     col, "dot", gravity=120, drag=1.2))
        elif self.kind == "sparkle" and active:
            self._acc += dt * 40
            while self._acc >= 1:
                self._acc -= 1
                a = r.uniform(0, math.tau)
                sp = r.uniform(30, 190)
                ox, oy = self.origin if self.origin else (w / 2, h * 0.42)
                self.ps.append(P(ox, oy, math.cos(a) * sp, math.sin(a) * sp, r.uniform(0.8, 1.6), 1.6, r.uniform(4, 9),
                                 r.choice([(255, 236, 160), (255, 255, 255), (255, 190, 120)]), "star", 0, r.uniform(-3, 3), drag=0.8, twinkle=True))
        # lights 는 그리기에서 처리 (파티클 없음)

    def step(self, dt: float):
        dt = min(dt, 0.1)
        self.t += dt
        self._spawn(dt)
        alive = []
        for p in self.ps:
            p.life -= dt
            if p.life <= 0 and p.max_life < 90:
                continue
            p.vy += p.gravity * dt
            if p.drag:
                k = max(0.0, 1 - p.drag * dt)
                p.vx *= k
                p.vy *= k if p.gravity == 0 else 1
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rot += p.vrot * dt
            if p.y > self.h + 20 or p.x < -40 or p.x > self.w + 40:
                continue
            alive.append(p)
        self.ps = alive

    # ---- 그리기 (Qt) : 픽셀 스타일 (안티앨리어싱 없음, unit 격자에 맞춘 정사각형/십자 모양)
    def paint(self, painter, opacity: float = 1.0, unit: int = 2):
        from PySide6.QtGui import QColor
        painter.save()
        fade = self.fade * opacity
        if self.kind == "lights":
            self._paint_lights(painter, fade, unit)
        for p in self.ps:
            a = 1.0 if p.max_life >= 90 else max(0.0, min(1.0, p.life / p.max_life))
            if p.twinkle:
                a = math.sin(a * math.pi)
            col = QColor(p.color[0], p.color[1], p.color[2], int(255 * a * fade))
            s = max(unit, int(round(p.size / 3.0)) * unit)
            x, y = int(p.x // unit) * unit, int(p.y // unit) * unit
            if p.shape == "star":                       # 십자 반짝임
                arm = s if p.size > 7 else unit
                painter.fillRect(x - arm, y, s + 2 * arm, s, col)
                painter.fillRect(x, y - arm, s, s + 2 * arm, col)
            else:
                painter.fillRect(x, y, s, s, col)
        painter.restore()

    def _paint_lights(self, painter, fade: float, unit: int):
        from PySide6.QtGui import QColor
        n = max(8, self.w // (24 * unit))
        cols = [(214, 58, 58), (243, 201, 74), (79, 182, 107), (143, 208, 245)]
        wire = QColor(8, 30, 22, int(230 * fade))
        pts = []
        for i in range(n + 1):
            x = int(i * self.w / n) // unit * unit
            y = (4 + int(round(5 * abs(math.sin(i / n * math.pi * 2)))) * 1) * unit
            pts.append((x, y))
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            steps = max(1, (x1 - x0) // unit)
            for k in range(steps):
                painter.fillRect(x0 + k * unit, y0 + (y1 - y0) * k // steps // unit * unit, unit, unit, wire)
        for i, (x, y) in enumerate(pts):
            on = math.sin(self.t * 4 + i * 1.3) > -0.3
            c = cols[i % 4]
            if on:
                painter.fillRect(x - unit, y + unit, 4 * unit, 4 * unit, QColor(c[0], c[1], c[2], int(70 * fade)))
            painter.fillRect(x, y + 2 * unit, 2 * unit, 3 * unit, QColor(c[0], c[1], c[2], int((255 if on else 100) * fade)))


class CatchGame:
    """떨어지는 아이템 잡기 (순수 로직)."""

    def __init__(self, w: int, h: int, target: int, seconds: float, rng: random.Random | None = None):
        self.w, self.h, self.target, self.seconds = w, h, target, float(seconds)
        self.rng = rng or random.Random()
        self.items: list[dict] = []
        self.caught = 0
        self.time_left = float(seconds)
        self.state = "ready"          # ready | playing | won | lost
        self._acc = 0.0

    def start(self):
        self.items.clear()
        self.caught = 0
        self.time_left = self.seconds
        self.state = "playing"
        self._acc = 0.0

    def step(self, dt: float):
        if self.state != "playing":
            return
        dt = min(dt, 0.1)
        self.time_left -= dt
        self._acc += dt
        rate = max(0.35, self.seconds / (self.target * 2.2))     # 목표를 채울 만큼 충분히 나오게
        while self._acc >= rate:
            self._acc -= rate
            self.items.append({"x": self.rng.uniform(24, self.w - 24), "y": -16.0,
                               "vy": self.rng.uniform(70, 130), "r": 20.0, "wob": self.rng.uniform(0, 6.28)})
        for it in self.items:
            it["y"] += it["vy"] * dt
        self.items = [it for it in self.items if it["y"] < self.h + 30]
        if self.caught >= self.target:
            self.state = "won"
        elif self.time_left <= 0:
            self.time_left = 0.0
            self.state = "lost"

    def hit(self, x: float, y: float) -> bool:
        if self.state != "playing":
            return False
        for it in reversed(self.items):
            if (it["x"] - x) ** 2 + (it["y"] - y) ** 2 <= (it["r"] + 6) ** 2:
                self.items.remove(it)
                self.caught += 1
                if self.caught >= self.target:
                    self.state = "won"
                return True
        return False
