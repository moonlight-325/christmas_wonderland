"""스노우볼 내부 눈 물리 (스노우볼마다 독립 인스턴스, 데스크톱 눈 엔진과 완전히 분리, Qt 비의존).

- 눈송이 입자: 중력 + 공기저항(공기 흐름 쪽으로 끌림) + 흔들림 관성 + 난류 + 펄럭임.
- 유리 구체 안쪽 원(WALL_R) 충돌, 장식 윗면(윤곽선 계단) 위에 쌓임, 바닥 타원의 깊이(lane)별 쌓임.
- 눈송이끼리 충돌(격자 이웃 검사), 흔들리면 쌓인 눈이 다시 떠올라 재분산, 멈추면 서서히 가라앉음.
- 좌표는 논리 픽셀(2D). 'lane'은 바닥 위 앞뒤 위치(0=뒤, 1=앞)로 장식과의 앞뒤 겹침 판정에만 쓰인다.
"""
from __future__ import annotations

import math
import random

from . import catalog as C
from . import model as M

# 종류별: (공기저항 k, 종단속도 vt, 관성 반응, 펄럭임 세기, 펄럭임 주파수, 기본 반지름, 반발)
PARAMS = {
    0: (2.2, 11.0, 0.30, 5.0, 2.0, 1.0, 0.25),     # 일반 눈
    1: (1.5, 7.5, 0.18, 9.0, 1.2, 2.0, 0.35),      # 큰 눈송이: 느리고 팔랑거림
    2: (3.4, 6.0, 0.55, 12.0, 5.0, 1.0, 0.50),     # 반짝이: 가볍고 빠르게 반응
}
KIND_INDEX = {k: i for i, k in enumerate(C.SNOW_KINDS)}

ACC_MAX = 1800.0           # 한 번에 받아들이는 최대 가속도 (논리 px/s^2)
RELEASE_ACC = 110.0        # 이 이상 흔들리면 쌓인 눈이 깨어남
ENERGY_TAU = 1.6           # 흔들림 에너지가 줄어드는 시간
ENERGY_REF = 700.0
AIR_TAU = 1.15             # 공기 흐름이 잦아드는 시간
AIR_COUPLE = 0.55          # 유리 움직임이 안쪽 공기를 휘젓는 정도
AIR_MAX = 170.0
PILE_K = 0.8               # 눈 한 개가 쌓였을 때 높아지는 높이(px)
PILE_BINS = 4
PILE_MAX = 9.0
AUTO_DUR = 1.7             # 클릭 자동 흔들기 지속
AUTO_ACC = 820.0
AUTO_COOLDOWN = 0.7        # 끝난 뒤 다시 흔들 수 있기까지 (반복 클릭 과흔들림 방지)
FLAKE_COLLIDE_ENERGY = 0.12
_NEIGHBORS = ((0, 0), (1, 0), (0, 1), (1, 1), (1, -1))      # 격자 이웃 검사 순서 (순서가 결과에 영향을 줌)


class Flake:
    __slots__ = ("x", "y", "vx", "vy", "kind", "lane", "ph", "rest", "surf", "col", "bin")

    def __init__(self, kind: int):
        self.kind = kind
        self.lane = random.random()
        self.bin = min(PILE_BINS - 1, int(self.lane * PILE_BINS))
        self.ph = random.random() * 6.283
        self.x = self.y = self.vx = self.vy = 0.0
        self.rest = False
        self.surf = -1          # -1 = 바닥, 0.. = 장식 번호
        self.col = 0


class Obstacle:
    """장식 하나의 눈 충돌 모양: 윗면 윤곽 + 윗면에 쌓인 눈 높이."""
    __slots__ = ("x0", "x1", "cx", "ay", "depth", "profile", "top", "hh", "hw", "cols")

    def __init__(self, item: dict):
        d = C.DECOR[item["kind"]]
        sc, rot = item["scale"], item["rot"] % 360
        self.cx, self.ay = item["x"], item["y"]
        if rot == 0:
            self.hw = d["w"] * sc / 2.0
            self.hh = d["h"] * sc
            self.profile = d["profile"]
            self.x0, self.x1 = self.cx - self.hw, self.cx + self.hw
            self.top = self.ay - self.hh
        else:                                    # 회전한 장식은 외곽 상자 윗면으로 단순화
            minx, maxx, miny, _maxy = M.item_extent(item["kind"], sc, rot)
            self.x0, self.x1 = self.cx + minx, self.cx + maxx
            self.hw = (self.x1 - self.x0) / 2.0
            self.top = self.ay + miny
            self.hh = self.ay - self.top
            self.profile = None
        self.depth = d["depth"] * max(0.6, sc)
        self.cols = [0.0] * (int(self.x1 - self.x0) + 2)

    def roof(self, x: float) -> float:
        if self.profile is None:
            return self.top
        u = (x - self.cx) / self.hw if self.hw > 0 else 0.0
        return self.ay - C.roof_v(self.profile, u) * self.hh


def land_y(x: float, lane: float) -> float:
    """바닥 위 lane(앞뒤) 위치에서 눈이 닿는 Y. 바닥 타원 가장자리로 갈수록 가운데 선으로 모인다."""
    dx = (x - C.GX) / (C.GRX * 0.96)
    s = math.sqrt(max(0.0, 1.0 - dx * dx))
    return C.GY + (lane * 2.0 - 1.0) * C.GRY * 0.92 * s


class GlobePhysics:
    def __init__(self, snow: dict | None = None, decor: list | None = None):
        self.flakes: list[Flake] = []
        self.obstacles: list[Obstacle] = []
        self.pile = [[0.0] * (C.GW + 2) for _ in range(PILE_BINS)]
        self.air_x = self.air_y = 0.0
        self.energy = 0.0
        self.size = 1.0
        self.speed = 1.0
        self.snow = dict(M.DEFAULT_SNOW)
        self.rest_count = 0
        self._auto_t = 0.0
        self._auto_dir = 1
        self._cool = 0.0
        self.jolt = (0.0, 0.0)           # 클릭 흔들기 중 유리 구체가 흔들리는 시각적 변위 (논리 px)
        self.shake_strength = 1.0
        self.configure(snow or M.DEFAULT_SNOW, initial=True)
        self.set_decor(decor or [], wake=False)

    # ------------------------------------------------------------ 설정
    def configure(self, snow: dict, initial: bool = False):
        snow = M.clean_snow(snow)
        self.snow = snow
        self.size = snow["size"]
        self.speed = snow["speed"]
        target = M.split_counts(snow["amount"], snow)
        buckets = {0: [], 1: [], 2: []}
        for f in self.flakes:
            buckets[f.kind].append(f)
        removed = False
        for name in C.SNOW_KINDS:
            k = KIND_INDEX[name]
            diff = target[name] - len(buckets[k])
            if diff > 0:
                for _ in range(diff):
                    f = Flake(k)
                    if initial:
                        self._spawn_resting(f)
                    else:
                        self._spawn_falling(f)
                    self.flakes.append(f)
            elif diff < 0:
                drop = set(map(id, sorted(buckets[k], key=lambda f: f.rest)[:-diff]))   # 떠 있는 눈부터 제거
                self.flakes = [f for f in self.flakes if id(f) not in drop]
                removed = True
        if removed:
            self._rebuild_piles()
        self._recount()

    def set_decor(self, items: list, wake: bool = True):
        """장식 변경. 장식 위에 쌓였던 눈은 (장식 번호가 바뀔 수 있으므로) 항상 다시 떨어져 새 위치에 쌓인다.
        바닥에 쌓인 눈은 그대로 둔다. wake 인자는 호환용이다."""
        self.obstacles = [Obstacle(it) for it in M.draw_order(items)]
        for f in self.flakes:
            if f.rest and f.surf >= 0:
                f.rest = False
                f.vx = f.vy = 0.0
        self._rebuild_piles()
        self._recount()

    # ------------------------------------------------------------ 생성
    def _spawn_resting(self, f: Flake):
        f.x = C.GX + (random.random() * 2 - 1) * C.GRX * 0.96
        f.y = land_y(f.x, f.lane)
        self._rest_ground(f)

    def _spawn_falling(self, f: Flake):
        a = random.random() * 6.283
        r = math.sqrt(random.random()) * 30.0
        f.x = C.SCX + math.cos(a) * r
        f.y = max(C.SCY - 28.0, C.SCY - 20.0 + math.sin(a) * r * 0.7)
        f.vx = (random.random() - 0.5) * 8
        f.vy = random.random() * 6
        f.rest = False

    def _recount(self):
        self.rest_count = sum(1 for f in self.flakes if f.rest)

    # ------------------------------------------------------------ 쌓임
    def _add_pile(self, arr, col: int, amount: float):
        n = len(arr)
        for off, w in ((-1, 0.25), (0, 0.5), (1, 0.25)):
            i = col + off
            if 0 <= i < n:
                arr[i] = min(PILE_MAX, arr[i] + amount * w)

    def _rest_ground(self, f: Flake):
        col = max(0, min(C.GW, int(f.x)))
        h = self.pile[f.bin][col]
        f.y = land_y(f.x, f.lane) - h
        f.rest, f.surf, f.col = True, -1, col
        f.vx = f.vy = 0.0
        self._add_pile(self.pile[f.bin], col, PILE_K)
        self.rest_count += 1

    def _rest_roof(self, f: Flake, oi: int, ob: Obstacle, ry: float, idx: int):
        f.y = ry - 0.4
        f.rest, f.surf, f.col = True, oi, idx
        f.vx = f.vy = 0.0
        self._add_pile(ob.cols, idx, PILE_K)
        self.rest_count += 1

    def _rebuild_piles(self):
        for arr in self.pile:
            for i in range(len(arr)):
                arr[i] = 0.0
        for ob in self.obstacles:
            for i in range(len(ob.cols)):
                ob.cols[i] = 0.0
        for f in self.flakes:
            if not f.rest:
                continue
            if f.surf < 0:
                self._add_pile(self.pile[f.bin], f.col, PILE_K)
            elif f.surf < len(self.obstacles):
                self._add_pile(self.obstacles[f.surf].cols, f.col, PILE_K)
            else:
                f.rest = False

    # ------------------------------------------------------------ 흔들기
    def auto_shake(self) -> bool:
        """클릭 자동 흔들기. 이미 흔들리는 중이거나 직후 쿨다운이면 무시해 과도한 흔들림을 막는다."""
        if self._auto_t > 0 or self._cool > 0:
            return False
        self._auto_t = AUTO_DUR
        self._auto_dir = random.choice((-1, 1))
        return True

    @property
    def shaking(self) -> bool:
        return self._auto_t > 0

    def _auto_accel(self, dt: float):
        if self._auto_t <= 0:
            self.jolt = (0.0, 0.0)
            return 0.0, 0.0
        u = 1.0 - self._auto_t / AUTO_DUR
        env = math.sin(math.pi * u)
        ph = u * 6.283 * 3.5
        self._auto_t -= dt
        if self._auto_t <= 0:
            self._auto_t = 0.0
            self._cool = AUTO_COOLDOWN
        self.jolt = (0.0, 0.0)           # UI Stage 7: 유리 구체가 흔들리는 애니메이션은 없음 (눈만 휘몰아침)
        return (self._auto_dir * math.sin(ph) * env * AUTO_ACC, math.cos(ph * 0.7) * env * AUTO_ACC * 0.45)

    def _wake(self, mag: float):
        """흔들림이 일정 이상이면 쌓인 눈이 깨어나고, 세기에 따라 위로 떠오른다."""
        s = max(0.15, min(1.0, (mag - RELEASE_ACC) / 1200.0 + 0.15))
        for f in self.flakes:
            if not f.rest:
                continue
            f.rest = False
            if random.random() < s * 1.4:
                f.vy = -(8 + random.random() * 55) * s
                f.vx = (random.random() - 0.5) * 70 * s
            else:
                f.vx = f.vy = 0.0
        self._rebuild_piles()
        self.rest_count = 0

    # ------------------------------------------------------------ 한 걸음
    @property
    def idle(self) -> bool:
        return (self.rest_count >= len(self.flakes) and abs(self.air_x) < 0.8 and abs(self.air_y) < 0.8
                and self.energy < 0.01 and self._auto_t <= 0 and self._cool <= 0)

    def step(self, dt: float, ax: float = 0.0, ay: float = 0.0):
        """dt 초 진행. (ax, ay) = 유리 구체의 가속도(논리 px/s^2). 사용자가 직접 움직이면 창 이동에서 계산해 넣는다."""
        dt = min(max(dt, 0.0), 0.05)
        if dt <= 0:
            return
        if self._cool > 0:
            self._cool = max(0.0, self._cool - dt)
        aax, aay = self._auto_accel(dt)
        strength = max(0.5, min(2.0, float(self.shake_strength)))
        ax = max(-ACC_MAX, min(ACC_MAX, (ax + aax) * strength))
        ay = max(-ACC_MAX, min(ACC_MAX, (ay + aay) * strength))
        mag = math.hypot(ax, ay)
        self.energy = max(self.energy * math.exp(-dt / ENERGY_TAU), min(1.5, mag / ENERGY_REF))
        if self.energy < 0.01 and mag < 1.0:
            self.energy = 0.0
        if mag > RELEASE_ACC and self.rest_count:
            self._wake(mag)
        decay = math.exp(-dt / AIR_TAU)
        self.air_x = max(-AIR_MAX, min(AIR_MAX, (self.air_x - ax * AIR_COUPLE * dt) * decay))
        self.air_y = max(-AIR_MAX, min(AIR_MAX, (self.air_y - ay * AIR_COUPLE * dt) * decay))
        if self.rest_count >= len(self.flakes) and self.energy == 0.0 and abs(self.air_x) < 0.8 and abs(self.air_y) < 0.8:
            self.air_x = self.air_y = 0.0
            return                                   # 모두 가라앉은 상태: 계산하지 않음

        sp, sz, en = self.speed, self.size, self.energy
        scx, scy, wall = C.SCX, C.SCY, C.WALL_R
        active = []
        append = active.append
        rnd = random.random
        sin, sqrt = math.sin, math.sqrt
        airx, airy = self.air_x, self.air_y
        flut_k = 0.5 + sp * 0.5
        noisy = en > 0.02
        obstacles = self.obstacles
        pile = self.pile
        gw, gx, gy = C.GW, C.GX, C.GY
        gx_den, gry = C.GRX * 0.96, C.GRY
        for f in self.flakes:
            if f.rest:
                continue
            kind = f.kind
            k, vt, react, flut, ffreq, r0, rest_c = PARAMS[kind]
            r = r0 * (sz if kind != 2 else 1.0)
            py = f.y
            g = vt * k * sp
            f.vx += ((airx - f.vx) * k - ax * react) * dt
            f.vy += (g + (airy - f.vy) * k - ay * react) * dt
            f.ph += dt * ffreq * (1.0 + en)
            f.vx += sin(f.ph) * flut * dt * flut_k
            if noisy:
                f.vx += (rnd() - 0.5) * en * 140.0 * dt
                f.vy += (rnd() - 0.5) * en * 110.0 * dt
            f.x += f.vx * dt
            f.y += f.vy * dt

            # 유리 구체 안쪽 곡면 충돌
            dx, dy = f.x - scx, f.y - scy
            lim = wall - r
            d2 = dx * dx + dy * dy
            if d2 > lim * lim:
                d = sqrt(d2)
                nx, ny = dx / d, dy / d
                f.x, f.y = scx + nx * lim, scy + ny * lim
                vn = f.vx * nx + f.vy * ny
                if vn > 0:
                    f.vx -= (1.0 + rest_c) * vn * nx
                    f.vy -= (1.0 + rest_c) * vn * ny
                f.vx *= 0.94
                f.vy *= 0.94

            fx = f.x
            ldx = (fx - gx) / gx_den                         # land_y(f.x, f.lane) 를 그대로 펼친 것
            ly = gy + (f.lane * 2.0 - 1.0) * gry * 0.92 * sqrt(max(0.0, 1.0 - ldx * ldx))
            landed = False
            if f.vy >= -2.0 or f.y > ly - 12:
                if obstacles:
                    for oi, ob in enumerate(obstacles):          # 장식 윗면 / 몸통
                        if fx < ob.x0 or fx > ob.x1 or abs(ly - ob.ay) > ob.depth:
                            continue
                        idx = max(0, min(len(ob.cols) - 1, int(fx - ob.x0)))
                        ry = ob.roof(fx) - ob.cols[idx]
                        if f.y >= ry:
                            if py <= ry + 2.0 and f.vy >= 0:
                                self._rest_roof(f, oi, ob, ry, idx)
                                landed = True
                            elif f.y - ry <= 8.0:                      # 옆에서 몸통에 들어온 눈은 윗면으로 밀려 올라감
                                f.y = ry - 0.5
                                f.vy = min(f.vy, 0.0) * 0.3
                                f.vx *= 0.6
                            break
                if not landed:
                    col = max(0, min(gw, int(fx)))
                    if f.y >= ly - pile[f.bin][col]:
                        self._rest_ground(f)
                        landed = True
            if not landed:
                append(f)

        if en > FLAKE_COLLIDE_ENERGY and len(active) > 1:
            self._collide(active)

    def _collide(self, flakes: list):
        """격자 이웃 검사로 눈송이끼리 밀어내고 속도를 일부 주고받는다.

        계산 순서와 수식은 원래와 같다(결과가 비트 단위로 동일). 쌍마다 반복되는 반지름 조회·튜플 비교를 없애고,
        거리가 최대 반지름 합보다 멀면 반지름을 보기 전에 건너뛴다.
        """
        cell = 5.0
        grid: dict = {}
        for f in flakes:
            grid.setdefault((int(f.x // cell), int(f.y // cell)), []).append(f)
        sz = self.size
        rad = tuple(PARAMS[k][5] * (sz if k != 2 else 1.0) for k in (0, 1, 2))
        far = max(rad) + max(rad)
        far2 = far * far                              # 이보다 멀면 어떤 쌍도 겹칠 수 없다
        sqrt = math.sqrt
        get = grid.get
        for (cx, cy), lst in grid.items():
            for ox, oy in _NEIGHBORS:
                other = get((cx + ox, cy + oy))
                if other is None:
                    continue
                same = ox == 0 and oy == 0
                for i, a in enumerate(lst):
                    ax, ay, ka = a.x, a.y, a.kind
                    for b in (other[i + 1:] if same else other):
                        dx, dy = b.x - ax, b.y - ay
                        d2 = dx * dx + dy * dy
                        if d2 >= far2:
                            continue
                        rr = rad[ka] + rad[b.kind]
                        if d2 >= rr * rr or d2 < 1e-6:
                            continue
                        d = sqrt(d2)
                        nx, ny = dx / d, dy / d
                        push = (rr - d) * 0.5
                        a.x -= nx * push
                        a.y -= ny * push
                        b.x += nx * push
                        b.y += ny * push
                        ax, ay = a.x, a.y
                        rv = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                        if rv < 0:
                            imp = -rv * 0.45
                            a.vx -= nx * imp
                            a.vy -= ny * imp
                            b.vx += nx * imp
                            b.vy += ny * imp

    # ------------------------------------------------------------ 렌더링용 스냅샷
    def snapshot(self) -> list:
        """[(x, y, 종류(0/1/2), 위상, 쌓임 여부, 깊이)]  깊이는 장식과의 앞뒤 판정용 (낙하 중이면 착지할 Y)."""
        out = []
        for f in self.flakes:
            if f.rest and 0 <= f.surf < len(self.obstacles):
                depth = self.obstacles[f.surf].ay + 0.5          # 장식 윗면의 눈은 그 장식 앞에 그린다
            else:
                depth = land_y(f.x, f.lane)
            out.append((f.x, f.y, f.kind, f.ph, f.rest, depth))
        return out

    def counts(self) -> dict:
        c = {"normal": 0, "big": 0, "sparkle": 0, "rest": self.rest_count, "total": len(self.flakes)}
        for f in self.flakes:
            c[C.SNOW_KINDS[f.kind]] += 1
        return c
