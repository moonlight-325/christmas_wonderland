"""눈과 창/바닥의 연결 + 독립 눈 덩어리 (v1.9.6).

쌓인 눈 자체의 물리(축적·경사·최대 높이·마우스 밀기·바람/돌풍·용해)는 v1.4.0 구현을 복원한 것이며 physics.py / melt.py 에 있다.
이 파일은 v1.9.5 의 '창과 독립된 눈' 연결부만 담는다.

 1) 눈은 창에 종속되지 않는다. 더미 열은 창 표면 위의 '월드 눈'이며, 창이 움직이면 관성으로 뒤처지거나 떨어져
    덩어리(parcel)가 되고, 창이 사라지면(최소화/닫힘) 전부 덩어리로 바뀌어 낙하해 다른 표면/바닥에 쌓인다.
 2) 덩어리(창 이동/닫힘/가장자리 넘침으로 생긴 눈)는 질량이 보존된다: 총량 = 더미 열 합 + 덩어리 + 대기열.
 3) 덩어리가 표면에 닿으면 v1.4.0 의 더미 규칙(경사 제한 / 최대 높이 / 가장자리 낙하)에 편입된다.
 4) v1.4.0 방식의 흩날림(마우스·바람·돌풍)은 눈을 덜어 눈송이로 보내므로 그 양은 장부 `mass_lost` 에 기록한다.
    눈 총량이 줄어드는 경우: 온도 융해(mass_melted) / v1.4.0 흩날림·바닥 최대 높이 초과(mass_lost) / 사용자의 '눈 청소'.
"""
from __future__ import annotations

import math
import time

INF = float("inf")
BUCKET = 64
EDGE_CAP = 3.0               # 창 가장자리에서 이 높이(cell)를 넘는 눈은 가장자리 밖으로 흘러내린다
GRAVITY = 1500.0             # px/s^2 (눈 덩어리)
RESERVOIR_MAX = 3000         # 보관함 항목이 이 수를 넘으면 가까운 것끼리 합친다 (질량·무게중심 보존, 항목 수만 줄임)
RESERVOIR_BIN = 24.0         # 합칠 때 가로 묶음 폭(px)
FLUSH_BUDGET = 0.0015        # 한 프레임에 보관함을 비우는 데 쓰는 최대 시간(초): 느린 PC 에서 프레임을 더 늦추지 않게
MERGE_MAX = 8.0              # 같은 자리에서 같은 프레임에 생긴 덩어리를 합칠 때 한 덩어리의 최대 질량
MAX_PARCELS = 4000           # 동시에 날아다니는 눈 덩어리 수 (넘치면 reservoir 에 보관: 삭제 없음)
MISS_GRACE = 2               # 창이 연속 N회 목록에서 빠져야 '사라졌다'고 판단 (일시적 누락 방지)
GROUND = "ground"            # 바닥 표면 키: ("ground", 모니터 번호)


def is_ground(key) -> bool:
    return isinstance(key, tuple) and len(key) > 0 and key[0] == GROUND


class SnowMatter:
    """SnowSim 에 섞이는 믹스인: 질량 보존 눈 물리."""

    # ------------------------------------------------------------------ 초기화 / 장부
    def _init_matter(self):
        self.parcels: list = []            # 공중의 눈 덩어리 (Flake, carry > 0)
        self._reservoir: list = []         # (x, y, vx, vy, mass) 대기열
        self.pstat: dict = {}              # 렉 진단용: _step_parcels 내부 구간별 시간(ms)/개수
        self.mass_added = 0.0              # 새로 내려 쌓인 눈의 누적량 (장부)
        self.mass_melted = 0.0             # 융해로 사라진 눈의 누적량 (장부)
        self.mass_lost = 0.0               # v1.4.0 방식 흩날림 / 바닥 최대 높이 초과로 월드를 떠난 눈의 누적량 (장부)
        self.monitors: list = []
        self.floors: list = []
        self._pvx = self._pvy = 0.0        # v1.4.0 쟁기(_cursor_plow)용 커서 속도 (px/s)
        self._omega = 0.0                  # 커서 회전 정도 (-1~1, +는 시계 방향): 공중 눈송이 소용돌이용
        self._cur_ang = None
        self._maxpx = 0.0

    def total_mass(self) -> float:
        """월드에 존재하는 눈의 총량(cell)."""
        m = 0.0
        for p in self.piles.values():
            m += sum(p.cells)
        for f in self.parcels:
            m += f.carry
        for r in self._reservoir:
            m += r[4]
        return m

    def mass_balance(self) -> float:
        """총량 - (새로 쌓인 양 - 융해량 - v1.4.0 흩날림/초과량). 0 에 가까워야 한다 (장부에 없는 눈이 늘거나 줄지 않음)."""
        return self.total_mass() + getattr(self, "mass_ext", 0.0) - (self.mass_added - self.mass_melted - self.mass_lost)

    def _refresh_peaks(self):
        mx = 0.0
        for p in self.piles.values():
            pk = max(p.cells) if p.cells else 0.0
            p._peak = pk
            if pk > mx:
                mx = pk
        # 충돌 판정 범위: 가장 높은 더미(최대 높이 이하)와 최대 높이 중 큰 쪽
        self._maxpx = max(mx, self.max_cells) * self.cell

    # ------------------------------------------------------------------ 덩어리
    def _emit_parcel(self, x, y, vx, vy, mass, merge=False):
        if mass <= 1e-9:
            return
        if merge:
            # 더미 가장자리에서 넘친 눈은 매 프레임 '같은 자리' 에서 수천 번 생겨 같은 곳에 떨어졌다 (렉의 주원인: 덩어리 4000개가 전부 충돌).
            # 아직 움직이지 않은 같은 자리의 덩어리가 있으면 질량만 더해 하나로 합친다 (질량 합 그대로, 개수만 줄임).
            sp = self.__dict__.setdefault("_spawned", {})
            key = (x, y)
            g = sp.get(key)
            if g is not None and g.x == x and g.y == y and g.carry + mass <= MERGE_MAX:
                g.carry += mass
                g.tier = 1 if g.carry < 0.5 else (2 if g.carry < 1.2 else (3 if g.carry < 3.0 else 4))
                return
            if len(sp) > 256:
                sp.clear()
        if len(self.parcels) >= MAX_PARCELS:
            self._reservoir.append((x, y, vx, vy, mass))      # 한도 초과: 보관만 한다 (삭제 금지)
            if len(self._reservoir) > RESERVOIR_MAX * 2:
                self._compact_reservoir()
            return
        from .physics import Flake
        f = Flake()
        f.carry = mass
        f.x, f.y, f.vx, f.vy = x, y, vx, vy
        f.collide = True
        f.spin = self.rng.uniform(-6.0, 6.0)
        f.angle = self.rng.uniform(0.0, math.tau)
        f.tier = 1 if mass < 0.5 else (2 if mass < 1.2 else (3 if mass < 3.0 else 4))
        self.parcels.append(f)
        if merge:
            sp[(x, y)] = f

    def _compact_reservoir(self):
        """보관함이 수만 건으로 불어나도 비용이 일정하도록, 가까운 항목끼리 하나로 합친다.
        질량 합은 정확히 같고 위치/속도는 질량 가중 평균이다 (삭제 없음: 장부 그대로)."""
        bins: dict = {}
        for x, y, vx, vy, m in self._reservoir:
            k = int(x // RESERVOIR_BIN)
            b = bins.get(k)
            if b is None:
                bins[k] = [x * m, y * m, vx * m, vy * m, m]
            else:
                b[0] += x * m
                b[1] += y * m
                b[2] += vx * m
                b[3] += vy * m
                b[4] += m
        self._reservoir = [(b[0] / b[4], b[1] / b[4], b[2] / b[4], b[3] / b[4], b[4]) for b in bins.values() if b[4] > 0.0]

    def _flush_reservoir(self):
        pc = time.perf_counter
        deadline = pc() + FLUSH_BUDGET
        n = 0
        while self._reservoir and len(self.parcels) < MAX_PARCELS and n < 60:
            x, y, vx, vy, m = self._reservoir.pop()
            self._emit_parcel(x, y, vx, vy, m)
            n += 1
            if not (n & 7) and pc() > deadline:       # 시간 예산 초과: 나머지는 다음 프레임에 (삭제 아님)
                break
        return n

    def _spill_to_parcels(self, pile, spill):
        """더미에서 넘친 눈 (v1.4.0 relax 결과): 정확히 그 질량의 덩어리가 되어 떨어진다.
        side -1/+1 = 가장자리 밖으로 흘러내림, side 0 = 최대 높이 초과 (v1.4.0 처럼 왼쪽/오른쪽 가장자리 중 한 곳에서 떨어짐).
        바닥(closed)은 가장자리가 벽이고 더 내려갈 곳이 없으므로 최대 높이 초과분은 장부(mass_lost)에 기록하고 버린다."""
        cell = pile.cell
        for side, amount in spill:
            if amount <= 1e-9:
                continue
            if side == 0:
                if pile.closed or amount < 0.3:               # v1.4.0: 0.3 미만의 넘침은 무시
                    self.mass_lost += amount
                    continue
                side = -1 if self.rng.random() < 0.5 else 1
            x = pile.left - cell * 0.5 if side < 0 else pile.right + cell * 0.5
            self._emit_parcel(x, pile.top - EDGE_CAP * cell, side * 40.0 + pile.wvx * 0.5,
                              20.0 + self.rng.uniform(0, 30), amount, merge=True)

    def _deposit(self, pile, c, mass, cols=1):
        """질량 mass 를 c 열 중심으로 cols 개 열에 나눠 더한다 (가장자리 밖은 가장자리 열에 합침: 보존)."""
        n = len(pile.cells)
        cols = max(1, cols)
        c0 = c - (cols - 1) // 2
        per = mass / cols
        idx = []
        for i in range(c0, c0 + cols):
            j = 0 if i < 0 else (n - 1 if i >= n else i)
            pile.cells[j] += per
            idx.append(j)
        spill = []
        for j in idx:
            spill.extend(pile.relax(j, limit=40))
        if spill:
            self._spill_to_parcels(pile, spill)

    # ------------------------------------------------------------------ 눈 덩어리 비행 / 착지
    def _probe(self, x, y0, y1, allow_ground):
        """수직으로 y0->y1 이동하는 점이 부딪히는 더미 (pile, 열) 또는 None."""
        buckets = self._buckets
        if not buckets:
            return None
        for bk in range(int(y0 // BUCKET), int((y1 + self._maxpx) // BUCKET) + 1):
            keys = buckets.get(bk)
            if not keys:
                continue
            for key in keys:
                if not allow_ground and is_ground(key):
                    continue
                pile = self.piles.get(key)
                if pile is None:
                    continue
                c = int((x - pile.left) // pile.cell)
                if c < 0 or c >= len(pile.cells) or not pile.visible_at(x):
                    continue
                top = pile.top - pile.cells[c] * pile.cell
                if y0 <= top <= y1:
                    return pile, c
        return None

    def _step_parcels(self, dt, wx, wy):
        pc = time.perf_counter
        st = self.pstat
        t0 = pc()
        nres = len(self._reservoir)
        nflush = self._flush_reservoir() if nres else 0
        t1 = pc()
        if not self.parcels:
            st.update(flush=(t1 - t0) * 1000.0, loop=0.0, impact=0.0, land=0.0, n=0, nres=nres, nflush=nflush,
                      nimpact=0, nland=0)
            return
        b = self.bounds
        exp = math.exp
        keep = []
        air = exp(-0.12 * dt)
        cur = self.parcels
        n0 = len(cur)
        # 이번 프레임에 새로 생긴 덩어리(착지 중 넘친 눈)는 다음 프레임에 처리한다.
        # 같은 리스트를 돌면서 append 하면 충돌->넘침->새 덩어리->충돌이 한 프레임에 4000번까지 연쇄된다 (진단 로그: nimpact 4000).
        self.parcels = fresh = []
        t_imp = t_land = 0.0
        nimp = nland = 0
        for f in cur:
            m = f.carry
            wf = 1.0 / (1.0 + m * 1.5)                    # 무거운 덩어리는 바람을 덜 탄다
            f.vx += (wx * wf - f.vx) * (1.0 - exp(-0.9 * wf * dt))
            f.vx *= air
            f.vy += GRAVITY * dt
            if f.vy > 2600.0:
                f.vy = 2600.0
            py = f.y
            f.x += f.vx * dt
            f.y += f.vy * dt
            f.angle += f.spin * dt
            if f.x < b.left:                              # 화면 좌우 끝은 벽: 눈을 지우지 않고 튕겨낸다
                f.x = b.left
                f.vx = abs(f.vx) * 0.25
            elif f.x > b.right:
                f.x = b.right
                f.vx = -abs(f.vx) * 0.25
            if f.vy > 0:
                hit = self._probe(f.x, py, f.y, True)
                if hit is not None:
                    ta = pc()
                    self._impact(hit[0], hit[1], f)
                    t_imp += pc() - ta
                    nimp += 1
                    continue
                if f.y >= self.floor_at(f.x) + 4:                   # 어떤 표면도 못 만나고 바닥 아래로: 바닥에 쌓는다
                    ta = pc()
                    self._land_on_ground(f)
                    t_land += pc() - ta
                    nland += 1
                    continue
            keep.append(f)
        keep.extend(fresh)
        self.parcels = keep
        t2 = pc()
        st.update(flush=(t1 - t0) * 1000.0, loop=(t2 - t1 - t_imp - t_land) * 1000.0, impact=t_imp * 1000.0,
                  land=t_land * 1000.0, n=n0, nres=nres, nflush=nflush, nimpact=nimp, nland=nland)

    def _land_on_ground(self, f):
        self._sync_ground_if_needed()
        best = None
        bd = INF
        for key, pile in self.piles.items():
            if not is_ground(key):
                continue
            if pile.left <= f.x <= pile.right:
                best, bd = pile, 0.0
                break
            d = min(abs(f.x - pile.left), abs(f.x - pile.right))
            if d < bd:
                best, bd = pile, d
        if best is None:                                  # 바닥이 아직 없으면 대기열로 (삭제 금지)
            self._reservoir.append((f.x, self.floor_at(f.x) - 8.0, 0.0, 0.0, f.carry))
            return
        c = int((f.x - best.left) // best.cell)
        c = max(0, min(len(best.cells) - 1, c))
        self._impact(best, c, f)

    def _impact(self, pile, c, f):
        """눈 덩어리가 표면에 닿음: 질량 그대로 v1.4.0 더미 규칙(열에 나눠 더하기 + 경사/최대 높이 정리)에 편입한다."""
        m = f.carry
        cols = max(1, min(9, int(math.sqrt(m) * 1.6) + 1))
        self._deposit(pile, c, m, cols)

    # ------------------------------------------------------------------ 커서
    def set_cursor(self, pos, dt: float = 0.0):
        """커서 위치/속도 갱신. (_cvx, _cvy, _omega = 공중 눈송이용 / _pvx, _pvy = 쌓인 눈 밀기용 v1.4.0 속도)"""
        if pos is None or not self.cursor_on:
            self._cur = None
            self._cvx = self._cvy = 0.0
            self._pvx = self._pvy = 0.0
            self._cur_ang = None
            self._omega *= 0.8
            return
        if self._cur is not None and dt > 1e-4:
            pvx = (pos[0] - self._cur[0]) / dt              # v1.4.0 쟁기(쌓인 눈 밀기)용 속도: 그 버전의 추정식 그대로
            pvy = (pos[1] - self._cur[1]) / dt
            psp = math.hypot(pvx, pvy)
            if psp > 6000.0:
                pvx, pvy = pvx * 6000.0 / psp, pvy * 6000.0 / psp
            self._pvx += (pvx - self._pvx) * 0.6
            self._pvy += (pvy - self._pvy) * 0.6
            ivx = (pos[0] - self._cur[0]) / dt
            ivy = (pos[1] - self._cur[1]) / dt
            lim = 6000.0
            ivx = max(-lim, min(lim, ivx))
            ivy = max(-lim, min(lim, ivy))
            k = min(1.0, dt * 14.0)
            self._cvx += (ivx - self._cvx) * k
            self._cvy += (ivy - self._cvy) * k
            sp = math.hypot(self._cvx, self._cvy)
            if sp > 150.0:
                ang = math.atan2(self._cvy, self._cvx)
                if self._cur_ang is not None:
                    d = (ang - self._cur_ang + math.pi) % math.tau - math.pi
                    turn = max(-1.0, min(1.0, d / dt / 6.0))
                    self._omega += (turn - self._omega) * min(1.0, dt * 6.0)
                self._cur_ang = ang
            else:
                self._cur_ang = None
                self._omega *= max(0.0, 1.0 - dt * 4.0)
        self._cur = (float(pos[0]), float(pos[1]))

    def _cursor_push(self, dt):
        """공중의 눈송이/눈 덩어리를 커서가 밀고 휘젓는다 (내리는 눈: v1.9.5 그대로). 덩어리는 무거워서 덜 반응."""
        cx, cy = self._cur
        cvx, cvy = self._cvx, self._cvy
        speed = math.hypot(cvx, cvy)
        r = self.cursor_radius
        if speed < 40.0 and abs(self._omega) < 0.05:
            return
        r2 = r * r
        gain = 1.0 + self.cursor_gain * 2.0 * min(speed, 3000.0) / 1000.0
        k = self.cursor_strength * self.flake_react * 1.7 * min(1.0, dt * 10.0) * gain
        if k <= 0.0:
            return
        swirl = self.swirl * max(-1.0, min(1.0, self._omega * 2.0))
        ax, ay = cvx * 0.9, cvy * 0.9
        for lst, heavy in ((self.flakes, False), (self.parcels, True)):
            for f in lst:
                dx = f.x - cx
                dy = f.y - cy
                d2 = dx * dx + dy * dy
                if d2 > r2:
                    continue
                d = math.sqrt(d2) + 1e-6
                fall = 1.0 - d / r
                inv_m = 1.0 / (1.0 + f.carry * 2.0) if heavy else 1.0 / (0.6 + 0.4 * f.tier)
                push = k * fall * fall * inv_m
                rs = speed * 0.25
                tan = swirl * speed * 0.5
                f.vx += (ax + dx / d * rs - dy / d * tan) * push
                f.vy += (ay + dy / d * rs + dx / d * tan) * push
                f.spin += (cvx * 0.01 + swirl * 4.0) * push
                if f.vx > 3200.0:
                    f.vx = 3200.0
                elif f.vx < -3200.0:
                    f.vx = -3200.0
                if f.vy > 3200.0:
                    f.vy = 3200.0
                elif f.vy < -3200.0:
                    f.vy = -3200.0

    # ------------------------------------------------------------------ 바닥
    def set_monitors(self, rects, floors=None):
        """모니터 사각형 [(l, t, r, b)]: 각 모니터 아래쪽 가장자리가 눈이 쌓이는 바닥이 된다.
        floors: 모니터별 바닥 y (아래쪽 작업표시줄 윗선). 없으면 모니터 아래 가장자리."""
        self.monitors = [tuple(r) for r in rects]
        self.floors = list(floors) if floors else []
        self._sync_ground()

    def set_floors(self, floors) -> bool:
        """작업표시줄 크기/위치/자동 숨김이 바뀌었을 때 바닥만 갱신한다 (눈 데이터는 그대로 유지)."""
        floors = list(floors)
        if floors == list(getattr(self, "floors", [])) or len(floors) != len(self.monitors):
            return False
        self.floors = floors
        self._sync_ground()
        return True

    def _floor_of(self, i):
        fl = getattr(self, "floors", None)
        if fl and i < len(fl) and fl[i] is not None:
            return float(fl[i])
        return float(self.monitors[i][3]) if i < len(self.monitors) else float(self.bounds.bottom)

    def floor_at(self, x) -> float:
        """x 좌표가 속한 모니터의 바닥 y. 모니터가 없으면 전체 영역 아래."""
        if not self.monitors:
            return float(self.bounds.bottom)
        best, bd = 0, INF
        for i, (l, t, r, b) in enumerate(self.monitors):
            if l <= x < r:
                return self._floor_of(i)
            d = min(abs(x - l), abs(x - r))
            if d < bd:
                best, bd = i, d
        return self._floor_of(best)

    def _sync_ground_if_needed(self):
        if not any(is_ground(k) for k in self.piles):
            self._sync_ground()

    def _sync_ground(self):
        from .physics import Pile, SurfaceInfo
        b = self.bounds
        rects = self.monitors or [(b.left, b.top, b.right, b.bottom)]
        want = {}
        for i, (l, t, r, bt) in enumerate(rects):
            if self.monitors:
                bt = self._floor_of(i)
            want[(GROUND, i)] = (float(l), float(bt), float(r))
        cell = self.cell
        for key, (l, bt, r) in want.items():
            info = SurfaceInfo(key, l, bt, r, [(l, r)], [(l, r)], [])
            self.surfaces[key] = info
            n_new = max(1, int((r - l) // cell))
            pile = self.piles.get(key)
            if pile is None:
                pile = Pile(l, bt, r - l, cell)
                pile.closed = True
                pile.t_prev = self._t
                self.piles[key] = pile
            else:
                if pile.cell != cell:
                    self._rescale_pile(pile)
                if n_new < len(pile.cells):               # 바닥이 좁아지면 넘치는 눈은 마지막 열에 합침 (보존)
                    tail = sum(pile.cells[n_new:])
                    pile.cells = pile.cells[:n_new]
                    pile.cells[-1] += tail
                elif n_new > len(pile.cells):
                    add = n_new - len(pile.cells)
                    pile.cells.extend([0.0] * add)
                pile.left, pile.top = l, bt
            pile.segments = [(l, r)]
            pile.draw_segments = [(l, r)]
            pile.occluders = []
        for key in [k for k in self.piles if is_ground(k) and k not in want]:
            self._release_pile(key, self.piles.pop(key))
            self.surfaces.pop(key, None)
        self._rebuild_buckets()

    def _rescale_pile(self, pile):
        """cell 크기(화면 배율)가 바뀌었을 때: 눈의 실제 높이(px)와 위치를 유지하며 열을 다시 나눈다."""
        old_cell, new_cell = pile.cell, self.cell
        if old_cell == new_cell or not pile.cells:
            pile.cell = new_cell
            return
        width = len(pile.cells) * old_cell
        n = max(1, int(width // new_cell))
        on = len(pile.cells)
        ratio = old_cell / new_cell
        pile.cells = [pile.cells[min(on - 1, int(i * new_cell // old_cell))] * ratio for i in range(n)]
        pile.cell = new_cell
        # 단위가 바뀌므로 장부의 기준을 현재 총량에 맞춰 다시 잡는다 (화면 구성 변경 때만 발생)
        self.mass_added = self.total_mass() + getattr(self, "mass_ext", 0.0) + self.mass_melted

    # ------------------------------------------------------------------ 창과 눈의 관계
    def set_surfaces(self, infos):
        from .physics import Pile
        now = self._t
        keep = set()
        for s in infos:
            keep.add(s.key)
            self.surfaces[s.key] = s
            pile = self.piles.get(s.key)
            if pile is None:
                pile = Pile(s.left, s.top, s.width, self.cell)
                pile.t_prev = now
                self.piles[s.key] = pile
            else:
                pile.miss = 0
                if pile.cell != self.cell:
                    self._rescale_pile(pile)
                self._move_pile(pile, s, now)
            pile.segments = s.segments
            pile.draw_segments = s.draw_segments
            pile.occluders = s.occluders
        for key in [k for k in self.piles if k not in keep and not is_ground(k)]:
            pile = self.piles[key]
            pile.miss += 1
            if pile.miss >= MISS_GRACE:                   # 최소화/닫힘: 눈을 지우지 않고 월드 덩어리로 전환
                self._release_pile(key, self.piles.pop(key))
                self.surfaces.pop(key, None)
        self._rebuild_buckets()

    def _move_pile(self, pile, s, now):
        """창 이동/크기 변경: 눈은 관성으로 뒤처지고(미끄러짐), 너무 빠르면 창에서 떨어진다."""
        cell = self.cell
        dt = now - pile.t_prev
        pile.t_prev = now
        old_left = pile.left
        dxl = s.left - old_left
        dyt = s.top - pile.top
        n_old = len(pile.cells)
        n_new = max(1, int(s.width // cell))
        if abs(dxl) < 0.5 and abs(dyt) < 0.5 and n_new == n_old:
            pile.wvx *= 0.5
            pile.wvy *= 0.5
            pile.left, pile.top = s.left, s.top
            return
        dt = max(dt, 1e-3)
        lim = 9000.0
        vx = max(-lim, min(lim, dxl / dt))
        vy = max(-lim, min(lim, dyt / dt))
        pvx, pvy = pile.wvx, pile.wvy                     # 이동 직전의 창 속도 = 눈이 가지고 있던 속도(관성)
        acc = math.hypot(vx - pvx, vy - pvy) / dt
        resize = abs(s.width - n_old * cell) > 2 * cell   # 가장자리를 끌어 크기를 바꾸는 중: 눈은 제자리
        sp = max(abs(vx), abs(vy))
        wf = 0.2 + 1.6 * self.win_fall
        vdrop = 800.0 / wf
        adrop = 30000.0 / wf
        drop = max((sp - vdrop) / (vdrop * 1.2), (acc - adrop) / (adrop * 1.5))
        drop = 0.0 if resize else max(0.0, min(1.0, drop))
        slip = 1.0 if resize else min(1.0, self.win_slip * (0.18 + abs(vx) / 1200.0))
        total = slip * dxl / cell + pile.rem              # 창이 오른쪽으로 가면 눈은 창 기준 왼쪽으로 밀림
        sh = int(total)
        pile.rem = total - sh
        old = pile.cells
        nc = [0.0] * n_new
        follow = 1.0 - slip
        fallen = []
        for i in range(n_old):
            h = old[i]
            if h <= 0.0:
                continue
            k = i - sh
            if 0 <= k < n_new:
                nc[k] += h
            else:                                         # 창 밖으로 밀려난 눈: 그 월드 위치에서 떨어진다
                fallen.append((old_left + i * cell + cell * 0.5 + follow * dxl, h))
        if fallen:
            g = max(1, len(fallen) // 40 + 1)
            for s0 in range(0, len(fallen), g):
                grp = fallen[s0:s0 + g]
                mass = sum(h for _x, h in grp)
                x = sum(xx * h for xx, h in grp) / mass
                self._emit_parcel(x, s.top - EDGE_CAP * cell, pvx * 0.7 + self.rng.uniform(-40, 40),
                                  pvy * 0.7 + self.rng.uniform(-20, 20), mass)
        if drop > 0.0:
            self._shed(nc, s.left, s.top, drop, pvx, pvy)
        pile.cells = nc
        pile.left, pile.top = s.left, s.top
        pile.wvx = pvx + (vx - pvx) * 0.6
        pile.wvy = pvy + (vy - pvy) * 0.6

    def _shed(self, cells, left, top, frac, vx, vy):
        """눈의 frac 비율을 창에서 떼어 덩어리로 만든다 (질량 보존). 이전 속도(vx, vy)를 그대로 가진다."""
        cell = self.cell
        n = len(cells)
        active = [i for i in range(n) if cells[i] > 0.05]
        if not active:
            return
        g = max(1, len(active) // 60 + 1)
        jit = 40.0 + 80.0 * frac
        for s0 in range(0, len(active), g):
            grp = active[s0:s0 + g]
            mass = sx = 0.0
            peak = 0.0
            for i in grp:
                m = cells[i] * frac
                cells[i] -= m
                mass += m
                sx += (left + i * cell + cell * 0.5) * m
                if cells[i] + m > peak:
                    peak = cells[i] + m
            if mass > 1e-9:
                self._emit_parcel(sx / mass, top - peak * cell - cell, vx + self.rng.uniform(-jit, jit),
                                  vy + self.rng.uniform(-jit, jit * 0.5), mass)

    def _release_pile(self, key, pile):
        """창이 사라졌다(최소화/닫힘/표면 상실): 더미 전체를 독립 눈 덩어리로 전환한다. 창 참조는 남지 않는다."""
        self._shed(pile.cells, pile.left, pile.top, 1.0, pile.wvx * 0.9, pile.wvy * 0.9)
        # 남은 아주 작은 잔량도 버리지 않는다
        rest = sum(pile.cells)
        if rest > 1e-9:
            self._emit_parcel(pile.left + len(pile.cells) * self.cell * 0.5, pile.top - self.cell, 0.0, 0.0, rest)
        pile.cells = []
