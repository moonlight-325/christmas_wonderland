"""데스크톱 눈 물리 시뮬레이션 (Qt/Windows 와 무관한 순수 Python).

좌표계: 가상 데스크톱 물리 픽셀 (Win32 좌표와 동일).
 - 눈송이(Flake): 중력 + 공기저항 + 바람 + 난류 + 회전. 크기/무게에 따라 반응이 다르다.
 - 표면(Surface): 창 상단 / 작업표시줄 상단. 가려진 구간(visible)에서만 충돌한다.
 - 더미(Pile): 표면별 열(column) 높이 지도. 쌓임 / 경사 흘러내림 / 가장자리 낙하 / 바람에 날림 / 융해.
"""
from __future__ import annotations

import math
import time
import random
from dataclasses import dataclass, field

from .matter import BUCKET, EDGE_CAP, INF, SnowMatter, is_ground
from .bodies import SnowBodies
from .melt import MELT_TICK, SnowMelt

REF_AREA = 1920 * 1080
SLOPE = 1.5                 # 인접 열 최대 높이 차 (cell)
# 더미 최대 높이 (v1.9.6): v1.4.0 의 기존 제한 `2.0 + accumulate/100 * 14.0` (cell) 의 정확히 2배.
V140_CAP_BASE = 2.0         # v1.4.0 기존 값: 눈 축적량 0 일 때 최대 높이 (cell)
V140_CAP_SPAN = 14.0        # v1.4.0 기존 값: 눈 축적량 100 일 때 추가되는 높이 (cell)
CAP_SCALE = 2.0             # 이번 작업의 요구: 최대 축적 높이 = v1.4.0 기존 제한 x 2
WIND_MAX_PX = 520.0         # 풍속 100% 의 수평 속도 (px/s)
TIER_WEIGHTS = (0.50, 0.30, 0.15, 0.05)
TEMP_GRAVITY = 500.0      # 튕겨 난 일시 눈송이의 중력 (px/s^2)
TEMP_DRAG = 0.8           # 튕겨 난 일시 눈송이의 공기저항 (1/s) — 작을수록 멀리 날아감
TEMP_MAX = 700           # 튕겨 난 일시 눈송이 동시 최대 수 (내리는 눈송이 수와 따로 센다)
TEMP_GRACE = 0.25         # 튕겨 난 직후 이 시간(초) 동안은 자기가 떠나온 눈더미에 다시 달라붙지 않음
# tier 별 (낙하 종단속도 범위, 항력, 누적량 cell, 분배 열 수)
TIER_PARAMS = {
    1: ((45.0, 75.0), 2.6, 0.5, 1),
    2: ((70.0, 100.0), 1.9, 1.0, 2),
    3: ((95.0, 130.0), 1.4, 2.0, 3),
    4: ((120.0, 160.0), 1.0, 3.6, 4),
}


@dataclass
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


class Flake:
    __slots__ = ("x", "y", "vx", "vy", "tier", "drag", "term", "phase", "freq", "sway",
                 "spin", "angle", "alpha", "collide", "amount", "cols", "temp", "carry", "age")

    def __init__(self):
        self.x = self.y = self.vx = self.vy = 0.0
        self.tier = 1
        self.drag = 2.0
        self.term = 60.0
        self.phase = self.freq = self.sway = self.spin = self.angle = 0.0
        self.alpha = 2
        self.collide = True
        self.amount = 0.5
        self.cols = 1
        self.temp = False          # True: 바람/커서가 만든 일시 눈송이 (v1.4.0 방식, 화면 밖/착지 시 제거)
        self.age = 0.0             # 일시 눈송이가 생성된 뒤 흐른 시간(초)
        self.carry = 0.0           # > 0: 질량이 보존되는 눈 덩어리 (착지하면 정확히 그만큼 더미에 더해짐)


@dataclass
class SurfaceInfo:
    """추적기가 만든 한 프레임의 표면 정보."""
    key: object
    left: float
    top: float
    right: float
    segments: list = field(default_factory=list)    # 눈이 닿을 수 있는(가려지지 않은) x 구간 [(x1, x2), ...]
    draw_segments: list = field(default_factory=list)   # 모니터에 걸친 전체 구간 (그리기용, 가림은 occluders 로 처리)
    occluders: list = field(default_factory=list)       # Z-order 상 이 표면보다 위에 있는 창 사각형 [(l,t,r,b), ...]

    @property
    def width(self) -> float:
        return self.right - self.left


class Pile:
    """표면 하나에 쌓인 눈. cells[i] = i 번째 열의 높이(cell 단위)."""

    def __init__(self, left: float, top: float, width: float, cell: int):
        self.left = left
        self.top = top
        self.cell = cell
        n = max(1, int(width // cell))
        self.cells = [0.0] * n
        self.segments: list = []
        self.draw_segments: list = []
        self.occluders: list = []
        self.closed = False              # True: 가장자리가 벽 (바닥)
        self.wvx = self.wvy = 0.0        # 창(표면) 속도 추정 (px/s)
        self.t_prev = 0.0                # 마지막 표면 갱신 시각 (시뮬 시간)
        self.rem = 0.0                   # 미끄러짐의 소수 열 잔량
        self.miss = 0                    # 연속으로 표면 목록에서 빠진 횟수
        self._peak = 0.0
        self.maxh = INF                  # 최대 높이 (cell). SnowSim 이 max_cells 로 맞춘다 (단독 사용 시 제한 없음)
        self.phase = (hash((round(left), round(top))) % 628) / 100.0     # 더미마다 다른 높이 굴곡 위상 (항상 같은 값)

    def resize(self, width: float, cell: int) -> bool:
        n = max(1, int(width // cell))
        self.cell = cell
        if n == len(self.cells):
            return False
        old = self.cells
        on = len(old)
        self.cells = [old[min(on - 1, i * on // n)] for i in range(n)]
        return True

    @property
    def right(self) -> float:
        return self.left + len(self.cells) * self.cell

    def total(self) -> float:
        return sum(self.cells)

    def col_at(self, x: float) -> int:
        return int((x - self.left) // self.cell)

    def visible_at(self, x: float) -> bool:
        for a, b in self.segments:
            if a <= x < b:
                return True
        return False

    def relax(self, start: int, maxh: float | None = None, limit: int = 60):
        """v1.4.0 의 경사 제한 / 최대 높이 / 가장자리 낙하. 넘친 양 [(side, amount)] 반환
        (side -1 왼쪽, +1 오른쪽, 0 위쪽 초과).  maxh 를 생략하면 이 더미의 최대 높이(`self.maxh`)를 쓴다."""
        if maxh is None:
            maxh = self.maxh
        h = self.cells
        n = len(h)
        spill: list = []
        stack = [start]
        it = 0
        while stack and it < limit:
            it += 1
            i = stack.pop()
            if i < 0 or i >= n:
                continue
            if h[i] > maxh:
                spill.append((0, h[i] - maxh))
                h[i] = maxh
            for d in (-1, 1):
                j = i + d
                if 0 <= j < n:
                    diff = h[i] - h[j]
                    if diff > SLOPE:
                        m = (diff - SLOPE) * 0.5
                        h[i] -= m
                        h[j] += m
                        stack.append(j)
                elif h[i] > EDGE_CAP and not self.closed:       # 바닥(closed)은 가장자리가 벽
                    spill.append((d, h[i] - EDGE_CAP))
                    h[i] = EDGE_CAP
        return spill

    def relax_all(self, maxh: float | None = None):
        spill = []
        for _ in range(3):
            for i in range(len(self.cells)):
                spill.extend(self.relax(i, maxh, limit=8))
        return spill


def melt_rate_for(temperature: float, melt: float = 25.0) -> float:
    """온도(℃) -> 초당 융해량. 눈 더미와 눈사람 장식이 같은 식을 쓴다."""
    cold = max(0.0, min(1.0, (temperature + 10.0) / 10.0))
    return melt / 100.0 * 0.06 * cold + max(0.0, temperature) / 30.0 * 0.10


class SnowSim(SnowMatter, SnowMelt, SnowBodies):
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.bounds = Rect(0, 0, 1920, 1080)
        self.cell = 3
        self.enabled = True
        self.amount = 220
        self.speed = 1.0
        self.size = 1.0
        self.accumulate = 50
        self.melt = 25                   # 내부 기본값(고정): 용해 속도는 이제 온도로만 결정된다
        self.accumulate_rate = 50        # 눈 축적 속도 0~100 (50 = 기존과 동일)
        self.max_height = 100            # 눈 쌓이는 최대 높이 배율 25~300 % (100 = 기존 최대 높이)
        self.wrap = True                 # 화면 좌우 끝으로 나간 눈송이가 반대편에서 다시 나오는지
        self._wx_now = 0.0               # 이번 프레임의 수평 바람 속도 (px/s, 눈보라 포함) - 눈 쌓임이 바람을 반영하는 데 쓴다
        self.wind_dir = 90
        self.wind_strength = 15
        self.max_particles = 1500
        self.flakes: list[Flake] = []
        self.surfaces: dict = {}
        self.piles: dict = {}
        self._buckets: dict = {}
        self._t = 0.0
        self._melt_acc = 0.0
        self._wind_cache = (0.0, 0.0)
        # 날씨 확장: 눈보라 / 돌풍 / 온도 / 커서
        self.blizzard = 0.0              # 0(끔)~1 (눈보라 강도)
        self.gust_on = False
        self.gust_strength = 0.7         # 0~1
        self.gust_interval = 25.0        # 초 (평균)
        self.perf: dict = {}             # 렉 진단용: step() 구간별 시간(ms)
        self.temperature = 0.0           # ℃
        self.cursor_on = False
        self.cursor_strength = 0.6       # 0~1
        self.cursor_radius = 120.0
        self.gust_listeners: list = []
        self._gust = None                # (시작 t, 지속, 세기, ux, uy)
        self._gust_next = None
        self._cur = None                 # (x, y)
        self._ntemp = 0                  # 지금 날고 있는 일시 눈송이 수 (step 마다 다시 센다)
        self._cvx = self._cvy = 0.0
        # v1.5.0 눈 물리 튜닝 (0~1). 기본값은 설정창 기본값과 같다
        self.cursor_gain = 0.5           # 커서 속도에 따른 힘 증가량
        self.flake_react = 0.6           # 눈송이 반응 강도
        self.pile_react = 0.6            # 눈더미 반응 강도
        self.inertia = 0.6               # 관성
        self.friction = 0.5              # 마찰력
        self.collision = 0.5             # 충돌 강도
        self.swirl = 0.5                 # 회전력
        self.chain = 0.5                 # 연쇄 충돌 강도
        self.spread = 0.5                # 압축/퍼짐 정도
        self.win_slip = 0.5              # 창 이동 시 눈의 미끄러짐
        self.win_fall = 0.5              # 창 이동 시 눈이 떨어지는 민감도
        self._init_matter()
        self._init_bodies()
        self._sync_ground()

    # ------------------------------------------------------------------ 설정
    def configure(self, **kw):
        for k, v in kw.items():
            if not hasattr(self, k):
                raise AttributeError(k)
            setattr(self, k, v)
        self._fit_count()
        self._rebuild_buckets()

    def set_bounds(self, rect: Rect):
        self.bounds = rect
        if not self.monitors:
            self._sync_ground()
        self._fit_count()

    @property
    def max_cells(self) -> float:
        """더미 최대 높이 (cell) = v1.4.0 기존 제한(2.0 + 눈 축적량/100 x 14.0)의 2배 x '최대 높이' 설정 배율."""
        return (V140_CAP_BASE + self.accumulate / 100.0 * V140_CAP_SPAN) * CAP_SCALE * (self.max_height / 100.0)

    def target_count(self) -> int:
        if not self.enabled:
            return 0
        area = max(1.0, self.bounds.width * self.bounds.height)
        base = self.amount
        if self.blizzard > 0:
            base = max(base, 150) * (1.0 + 1.3 * self.blizzard)
        return max(0, min(int(self.max_particles), int(base * area / REF_AREA)))

    # ------------------------------------------------------------------ 바람
    def wind_vector(self):
        """(wx, wy) px/s. 방향: 0=북(위) 90=동(오른쪽) 180=남 270=서."""
        th = math.radians(self.wind_dir)
        s = self.wind_strength / 100.0
        mag = s * WIND_MAX_PX
        return math.sin(th) * mag, -math.cos(th) * mag * 0.6

    def _dir_vec(self, deg: float):
        th = math.radians(deg)
        return math.sin(th), -math.cos(th) * 0.6

    # ---- 돌풍
    def trigger_gust(self, strength: float | None = None, direction: float | None = None) -> float:
        """순간적인 강풍. strength 0~1, direction 도(0=북 90=동). 세기(0~1) 반환."""
        amp = self.gust_strength * self.rng.uniform(0.85, 1.1) if strength is None else strength
        amp = max(0.05, min(1.0, amp))
        if direction is None:
            direction = self.wind_dir + self.rng.uniform(-35, 35)
        ux, uy = self._dir_vec(direction)
        dur = self.rng.uniform(2.2, 3.6) * (0.8 + 0.5 * amp)
        self._gust = (self._t, dur, amp, ux, uy)
        for cb in list(self.gust_listeners):
            try:
                cb(amp, direction)
            except Exception:
                pass
        return amp

    def gust_envelope(self) -> float:
        g = self._gust
        if g is None:
            return 0.0
        u = (self._t - g[0]) / g[1]
        if u >= 1.0:
            self._gust = None
            return 0.0
        return math.sin(math.pi * u ** 0.6) ** 2 * g[2]

    # ---- 커서
    # ------------------------------------------------------------------ 눈송이
    def _new_flake(self, anywhere: bool) -> Flake:
        r = self.rng
        f = Flake()
        x = r.random()
        pick = r.random()
        acc = 0.0
        tier = 1
        for i, w in enumerate(TIER_WEIGHTS, start=1):
            acc += w
            if pick <= acc:
                tier = i
                break
        (lo, hi), drag, amount, cols = TIER_PARAMS[tier]
        f.tier = tier
        f.term = r.uniform(lo, hi)
        f.drag = drag * r.uniform(0.85, 1.15)
        f.amount = amount
        f.cols = cols
        f.alpha = 0 if tier == 1 else (1 if tier == 2 else 2)
        f.collide = True if tier > 1 else (r.random() < 0.3)     # 멀리 있는 작은 눈은 대부분 통과
        f.phase = r.uniform(0, math.tau)
        f.freq = r.uniform(0.6, 1.8)
        f.sway = r.uniform(8, 26) / (0.6 + 0.4 * tier)
        f.spin = r.uniform(-2.2, 2.2) / (0.5 + 0.5 * tier)
        f.angle = r.uniform(0, math.tau)
        b = self.bounds
        f.x = b.left + x * b.width
        f.y = r.uniform(b.top, b.bottom) if anywhere else b.top - r.uniform(4, 60)
        f.vy = f.term * 0.8
        f.vx = 0.0
        return f

    def _fit_count(self):
        """내리는 눈송이 수를 목표에 맞춘다. 커서/바람에 튕겨 난 일시 눈송이(temp)는 세지도 지우지도 않는다
        (예전에는 설정이 다시 적용될 때마다 -- 자동 날씨는 약 10Hz -- 꼬리쪽 일시 눈송이가 통째로 잘려 나가 튕긴 눈이 사라졌다)."""
        target = self.target_count()
        flakes = self.flakes
        normal = sum(1 for f in flakes if not f.temp)
        while normal < target:
            flakes.append(self._new_flake(anywhere=True))
            normal += 1
        if normal > target:
            drop = normal - target
            keep = []
            for f in reversed(flakes):                 # 뒤쪽(최근) 일반 눈송이부터 제거
                if drop > 0 and not f.temp:
                    drop -= 1
                    continue
                keep.append(f)
            keep.reverse()
            self.flakes[:] = keep

    def reset(self):
        self.flakes.clear()
        self.piles.clear()
        self.parcels.clear()
        self._reservoir.clear()
        self.mass_added, self.mass_melted, self.mass_lost = self.mass_ext, 0.0, 0.0     # 눈덩이 안의 눈은 장부에 그대로 남는다
        for s in list(self.surfaces.values()):
            if is_ground(s.key):
                self.surfaces.pop(s.key, None)
            else:
                self.piles[s.key] = Pile(s.left, s.top, s.width, self.cell)
        self._sync_ground()
        self._fit_count()

    def clear_piles(self):
        """사용자가 직접 누르는 '눈 청소': 쌓인 눈과 공중의 눈 덩어리를 모두 지운다."""
        for p in self.piles.values():
            p.cells = [0.0] * len(p.cells)
        self.parcels.clear()
        self._reservoir.clear()
        self.mass_added, self.mass_melted, self.mass_lost = self.mass_ext, 0.0, 0.0     # 눈덩이 안의 눈은 장부에 그대로 남는다

    # ------------------------------------------------------------------ 표면
    def _rebuild_buckets(self):
        cap = self.max_cells
        for pile in self.piles.values():                  # 표면 생성/이동/설정 변경 때마다 최대 높이를 맞춘다 (충돌·이동·재배치 공통)
            pile.maxh = cap
        self._buckets = {}
        if self.accumulate <= 0:
            return
        for key, s in self.surfaces.items():
            self._buckets.setdefault(int(s.top // BUCKET), []).append(key)

    # ------------------------------------------------------------------ 한 프레임
    def step(self, dt: float):
        if not self.enabled or dt <= 0:
            return
        dt = min(dt, 0.1)
        self._ntemp = sum(1 for f in self.flakes if f.temp)
        self._t += dt
        t = self._t
        b = self.bounds
        wx, wy = self.wind_vector()
        gust = 1.0 + 0.30 * math.sin(t * 0.7) + 0.18 * math.sin(t * 1.9 + 1.3)
        wx *= gust
        wy *= gust
        bz = self.blizzard
        if bz > 0:                                   # 눈보라: 풍향으로 강하게 휘몰아침
            bux, buy = self._dir_vec(self.wind_dir)
            wx += bux * bz * 720.0
            wy += buy * bz * 720.0
        # 돌풍 (자동 발생 + 진행 중인 돌풍의 세기)
        if self.gust_on:
            if self._gust_next is None:
                self._gust_next = t + self.rng.uniform(3.0, max(4.0, self.gust_interval))
            elif t >= self._gust_next and self._gust is None:
                self.trigger_gust()
                iv = max(5.0, self.gust_interval)
                self._gust_next = t + max(iv * 0.4, min(iv * 2.5, self.rng.expovariate(1.0 / iv)))
        genv = self.gust_envelope()
        if genv > 0 and self._gust:
            gmag = genv * 1700.0
            gx, gy = self._gust[3] * gmag, self._gust[4] * gmag
            wx += gx
            wy += gy
        else:
            gx = gy = 0.0
        eff = min(100.0, self.wind_strength + bz * 60.0 + genv * 45.0)
        self._eff_wind = eff
        sp = self.speed * (1.0 + 1.6 * bz)
        turb = 70.0 * bz
        self._wx_now = wx
        w_span = b.width + 120.0
        h_span = b.height + 120.0
        acc_on = self.accumulate > 0 and bool(self._buckets)
        _pc = time.perf_counter
        _t0 = _pc()
        self._refresh_peaks()
        _t1 = _pc()
        maxpx = self._maxpx
        sin = math.sin
        exp = math.exp
        flakes = self.flakes
        buckets = self._buckets
        piles = self.piles
        calm = 1.0 - 0.5 * eff / 100.0
        dead: list = []
        if self.cursor_on and self._cur is not None:
            self._cursor_push(dt)
            self._cursor_plow(dt)

        temp_d = exp(-TEMP_DRAG * dt)
        for f in flakes:
            if f.temp:
                # 커서/바람에 튕겨 난 눈송이: 일반 눈송이의 강한 공기저항(밀어낸 속도를 금방 잃음)을 쓰지 않고
                # 중력 + 약한 공기저항으로 포물선을 그리며 멀리 날아간다 (UI Stage 7)
                f.age += dt
                f.vy += TEMP_GRAVITY * dt
                f.vx = wx + (f.vx - wx) * temp_d
                f.vy = wy + (f.vy - wy) * temp_d
            else:
                d = exp(-f.drag * dt)
                f.vy += f.term * f.drag * sp * dt
                tx = wx + sin(t * f.freq + f.phase) * f.sway * calm
                if turb:
                    tx += sin(t * f.freq * 3.1 + f.phase * 2.0) * turb
                f.vx = tx + (f.vx - tx) * d
                f.vy = wy + (f.vy - wy) * d
            if f.vx > 1400.0:
                f.vx = 1400.0
            elif f.vx < -1400.0:
                f.vx = -1400.0
            py = f.y
            f.x += f.vx * dt
            f.y += f.vy * dt
            f.angle += f.spin * dt

            landed = False
            if acc_on and f.collide and f.vy > 0 and (not f.temp or f.age > TEMP_GRACE):
                for bk in range(int(py // BUCKET), int((f.y + maxpx) // BUCKET) + 1):
                    keys = buckets.get(bk)
                    if not keys:
                        continue
                    for key in keys:
                        pile = piles[key]
                        c = int((f.x - pile.left) // pile.cell)
                        if c < 0 or c >= len(pile.cells) or not pile.visible_at(f.x):
                            continue
                        top = pile.top - pile.cells[c] * pile.cell
                        if py <= top <= f.y:
                            self._land(pile, c, f)
                            landed = True
                            break
                    if landed:
                        break
            if landed:
                if f.temp:
                    dead.append(f)
                else:
                    self._respawn(f)
                continue

            # 경계 처리: 좌우는 순환, 아래로 벗어나면 위에서 재생성, 위로 벗어나면 아래에서 재생성
            if f.x < b.left - 60 or f.x > b.right + 60:
                if self.wrap:
                    f.x += w_span if f.x < b.left - 60 else -w_span
                elif f.temp:
                    dead.append(f)
                    continue
                else:
                    self._respawn(f)
                    continue
            if f.y > self.floor_at(f.x) + 20:
                if f.temp:
                    dead.append(f)
                else:
                    self._respawn(f)
            elif f.y < b.top - 80:
                if f.temp:
                    dead.append(f)
                else:
                    f.y += h_span

        if dead:
            gone = set(map(id, dead))
            self.flakes = [f for f in self.flakes if id(f) not in gone]
        _t2 = _pc()
        self._wind_blow(dt, wx, wy)
        if genv > 0.05 and self._gust:
            self._gust_blow(dt, genv, gx, gy)
        _t3 = _pc()
        self._step_parcels(dt, wx, wy)
        _t4 = _pc()
        self._melt_acc += dt
        if self._melt_acc >= MELT_TICK:
            self._melt(self._melt_acc)
            self._melt_acc = 0.0
        _t5 = _pc()
        self.perf = {"peaks": (_t1 - _t0) * 1000.0, "flakes": (_t2 - _t1) * 1000.0, "blow": (_t3 - _t2) * 1000.0,
                     "parcels": (_t4 - _t3) * 1000.0, "melt": (_t5 - _t4) * 1000.0}

    def _respawn(self, f: Flake):
        b = self.bounds
        f.x = b.left + self.rng.random() * b.width
        f.y = b.top - self.rng.uniform(2, 50)
        if not self.wrap:                      # 순환을 끄면 바람 불어오는 쪽이 비지 않도록 그쪽 옆면에서도 눈이 들어온다
            wn = min(1.0, abs(self._wx_now) / WIND_MAX_PX)
            if wn > 0.1 and self.rng.random() < 0.6 * wn:
                f.x = b.left - self.rng.uniform(2, 50) if self._wx_now > 0 else b.right + self.rng.uniform(2, 50)
                f.y = b.top + self.rng.random() * b.height
        f.vx = 0.0
        f.vy = f.term * 0.8
        f.collide = True if f.tier > 1 else (self.rng.random() < 0.3)

    def _soft_cap(self, pile: Pile, i: int, maxh: float) -> float:
        """열마다 조금씩 다른 '여기까지만 쌓이는 높이' (최대 높이의 82~100%). 꼭대기가 평평한 판이 되지 않게 완만한 굴곡을 준다."""
        wave = 0.5 + 0.25 * math.sin(i * 0.05 + pile.phase) + 0.25 * math.sin(i * 0.17 + pile.phase * 1.7)
        cap = maxh * (0.82 + 0.18 * wave)
        if not pile.closed:                            # 창 가장자리: 끝으로 갈수록 완만하게 낮아지는 둥근 어깨 (끝에서 갑자기 잘리거나 흘러내리지 않게)
            edge = min(i, len(pile.cells) - 1 - i)
            cap = min(cap, EDGE_CAP + 0.8 * edge)
        return cap

    def _deposit_soft(self, pile: Pile, i: int, amount: float, maxh: float, spill: list):
        """열 하나에 눈을 더한다. 최대 높이에 가까울수록 천천히 쌓이고, 가득 차면 더 쌓이지 않는다 (잘라내서 판처럼 되지 않게)."""
        h = pile.cells[i]
        cap = self._soft_cap(pile, i, maxh)
        if h >= cap:
            if h > maxh:                               # 최대 높이를 넘은 열은 예전처럼 정리해서 넘친 눈을 덩어리로 내보낸다
                spill.extend(pile.relax(i, maxh))
            return
        add = amount * (1.0 - (h / cap) ** 4)
        pile.cells[i] = h + add
        self.mass_added += add
        spill.extend(pile.relax(i, maxh))

    def _land(self, pile: Pile, c: int, f: Flake):
        """새로 내리는 눈 착지: 눈송이 크기별 양을 인접 열에 나눠 더하고 경사/최대 높이를 맞춘다.
        - 최대 높이에 가까울수록 덜 쌓인다 (soft cap)
        - 바람이 강하면 덜 쌓이고, 쌓이는 눈 일부가 바람 방향(풍하) 쪽 몇 칸 옆에 쌓인다
        - 착지 주변은 이웃 열과 높이를 조금 평균 내서 톱니 모양이 생기지 않게 한다 (눈의 총량은 그대로)
        넘친 눈은 v1.4.0 처럼 가장자리 밖으로 흘러내리되, 사라지지 않고 독립 눈 덩어리가 되어 떨어진다."""
        rate = (0.5 + self.accumulate / 50.0) * (self.accumulate_rate / 50.0)
        if self.temperature > 5:                       # 따뜻하면 젖은 눈이라 덜 쌓임
            rate *= 1.0 - 0.6 * min(1.0, (self.temperature - 5.0) / 25.0)
        wx = self._wx_now
        wn = min(1.0, abs(wx) / WIND_MAX_PX)
        rate *= 1.0 - 0.3 * wn                         # 강풍: 쌓이는 양 감소
        drift = 0.35 * wn                              # 쌓일 눈 중 바람에 실려 풍하 쪽에 쌓이는 비율
        total = f.amount * rate
        cols = f.cols
        per = total * (1.0 - drift) / cols
        n = len(pile.cells)
        c0 = c - (cols - 1) // 2
        maxh = self.max_cells
        spill: list = []
        for i in range(c0, c0 + cols):
            if 0 <= i < n:
                self._deposit_soft(pile, i, per, maxh, spill)
        if drift > 0.0:
            j = c + (1 if wx >= 0 else -1) * self.rng.randint(1 + cols // 2, 3 + cols // 2)
            if 0 <= j < n:
                self._deposit_soft(pile, j, total * drift, maxh, spill)
        h = pile.cells
        for j in range(max(0, c0 - 2), min(n - 1, c0 + cols + 2)):      # 이웃 열과 높이 차를 조금 줄임 (한 쌍씩 주고받으므로 총량 보존)
            d = h[j] - h[j + 1]
            if d > 0.4 or d < -0.4:
                m = d * 0.2
                h[j] -= m
                h[j + 1] += m
        if spill:
            self._spill_to_parcels(pile, spill)

    # ------------------------------------------------------------------ 바람에 날림 / 융해
    def _wind_blow(self, dt: float, wx: float, wy: float):
        """강풍이 쌓인 눈을 날려 보냄 (v1.4.0): 열에서 눈을 덜어내고(장부에 기록) 날아가는 눈송이를 만든다."""
        s = getattr(self, "_eff_wind", self.wind_strength)
        if s <= 55 or not self.piles:
            return
        rate = ((s - 55) / 45.0) ** 1.5
        keys = [k for k in self.piles if not is_ground(k)]
        if not keys:
            return
        count = int(rate * dt * 90 + self.rng.random())
        maxh = self.max_cells
        for _ in range(count):
            pile = self.piles[self.rng.choice(keys)]
            n = len(pile.cells)
            if n == 0:
                continue
            i = self.rng.randrange(n)
            if pile.cells[i] < 0.6:
                continue
            x = pile.left + i * pile.cell
            if not pile.visible_at(x):
                continue
            take = min(pile.cells[i], self.rng.uniform(0.6, 1.4))
            pile.cells[i] -= take
            self.mass_lost += take
            spill = pile.relax(i, maxh, limit=8)
            if spill:
                self._spill_to_parcels(pile, spill)
            if len(self.flakes) < self.max_particles * 1.1 + 50:
                f = self._new_flake(anywhere=False)
                f.tier = self.rng.choice((1, 2, 2, 3))
                f.collide = False
                f.x = x
                f.y = pile.top - pile.cells[i] * pile.cell - self.cell
                f.vx = wx * 1.2
                f.vy = -50.0 + wy * 0.3
                self.flakes.append(f)

    def melt_rate(self) -> float:
        """초당 기본 융해량(cell). 온도로만 결정: -10℃ 이하 = 녹지 않음, 0℃ = 느리게, 이후 온도에 비례해 증가."""
        return melt_rate_for(self.temperature, self.melt)

    # ------------------------------------------------------------------ 돌풍 / 커서 상호작용
    def _spawn_temp(self, x: float, y: float, vx: float, vy: float, tier: int = 2) -> bool:
        """바람/커서가 만든 일시 눈송이 (v1.4.0). 착지하면 눈송이 양만큼 쌓이고 사라진다."""
        if self._ntemp >= TEMP_MAX:
            return False
        self._ntemp += 1
        f = self._new_flake(anywhere=False)
        f.tier = tier
        f.alpha = 1 if tier == 2 else 0
        f.collide = True
        f.temp = True
        f.x, f.y, f.vx, f.vy = x, y, vx, vy
        self.flakes.append(f)
        return True

    def _gust_blow(self, dt: float, env: float, gx: float, gy: float):
        """돌풍 (v1.4.0): 쌓인 눈을 풍향으로 밀어내고(옆 칸으로 이동), 일부는 눈송이가 되어 날아간다."""
        if not self.piles:
            return
        keys = [k for k in self.piles if not is_ground(k)]
        if not keys:
            return
        sgn = 1 if gx >= 0 else -1
        maxh = self.max_cells
        count = int(env * dt * 420 + self.rng.random())
        for _ in range(count):
            pile = self.piles[self.rng.choice(keys)]
            n = len(pile.cells)
            if n == 0:
                continue
            i = self.rng.randrange(n)
            h = pile.cells[i]
            if h < 0.4:
                continue
            x = pile.left + i * pile.cell
            if not pile.visible_at(x):
                continue
            take = min(h, self.rng.uniform(0.5, 1.6) * (0.5 + env))
            pile.cells[i] -= take
            if self.rng.random() < 0.55:
                j = i + sgn * self.rng.randint(1, 6)
                if 0 <= j < n:
                    pile.cells[j] += take * 0.8
                    self.mass_lost += take * 0.2
                    spill = pile.relax(j, maxh, limit=10)
                    if spill:
                        self._spill_to_parcels(pile, spill)
                    continue
            self.mass_lost += take
            y = pile.top - pile.cells[i] * pile.cell - self.cell
            if not self._spawn_temp(x, y, gx * self.rng.uniform(0.8, 1.3), gy * 0.3 - self.rng.uniform(20, 90),
                                    self.rng.choice((1, 2, 2, 3))):
                pile.cells[i] += take                  # 일시 눈송이를 더 못 만들면 눈은 그 자리에 그대로 둔다
                self.mass_lost -= take

    def _cursor_plow(self, dt: float):
        """커서로 쌓인 눈을 훑으면 눈이 옆으로 밀리고 일부는 흩날린다 (v1.4.0 그대로).
        눈이 옆 열로 간 몫을 뺀 나머지(rest)는 흩날리는 눈송이가 되어 장부(mass_lost)에 기록된다."""
        if not self.piles:
            return
        cvx, cvy = self._pvx, self._pvy
        speed = math.hypot(cvx, cvy)
        if speed < 60.0:
            return
        cx, cy = self._cur
        r = self.cursor_radius
        k = min(1.0, dt * 10.0)
        strength = self.cursor_strength
        sf = min(speed, 3000.0) / 1000.0
        sgn = 1 if cvx >= 0 else -1
        maxh = self.max_cells
        maxpx = maxh * self.cell
        spawned = 0
        for pile in self.piles.values():
            if cx < pile.left - r or cx > pile.right + r or cy < pile.top - maxpx - r or cy > pile.top + r:
                continue
            cell = pile.cell
            cells = pile.cells
            n = len(cells)
            c0 = max(0, int((cx - r - pile.left) // cell))
            c1 = min(n - 1, int((cx + r - pile.left) // cell))
            for i in range(c0, c1 + 1):
                h = cells[i]
                if h < 0.3:
                    continue
                x = pile.left + i * cell + cell * 0.5
                if not pile.visible_at(x):
                    continue
                ytop = pile.top - h * cell
                dx, dy = x - cx, (ytop + h * cell * 0.5) - cy
                d = math.hypot(dx, dy)
                if d > r:
                    continue
                fall = (1.0 - d / r) ** 2
                take = min(h, fall * strength * (0.6 + 0.8 * sf) * k * 3.0)
                if take < 0.05:
                    continue
                cells[i] = h - take
                rest = take
                if self.rng.random() < 0.6:                  # 커서 진행 방향으로 쌓인 눈이 밀림 (쟁기 효과)
                    j = i + sgn * self.rng.randint(1, 3)
                    if 0 <= j < n:
                        cells[j] += take * 0.5
                        rest -= take * 0.5
                        spill = pile.relax(j, maxh, limit=10)
                        if spill:
                            self._spill_to_parcels(pile, spill)
                self.mass_lost += rest
                if rest > 0.2 and spawned < 14:
                    ux, uy = (dx / d, dy / d) if d > 0.5 else (0.0, -1.0)
                    # 눈더미 안쪽으로 향하는 속도는 위쪽으로 돌려, 튕겨 난 눈이 바로 같은 더미에 되박혀 사라지지 않게 한다
                    fvy = min(cvy * 0.5 + uy * speed * 0.4 - 60.0, -60.0 - 0.12 * speed)
                    if self._spawn_temp(x, ytop - self.cell, cvx * 0.5 + ux * speed * 0.4,
                                        fvy, self.rng.choice((1, 2, 2))):
                        spawned += 1
                    else:                                    # 더 못 만들면 눈이 사라지지 않게 제자리에 되돌린다
                        cells[i] += rest
                        self.mass_lost -= rest
                spill = pile.relax(i, maxh, limit=8)
                if spill:
                    self._spill_to_parcels(pile, spill)
