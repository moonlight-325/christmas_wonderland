"""눈덩이/눈사람 물리 월드 (순수 Python, Qt 없음).

 - Ball: 화면 월드 좌표의 독립 물리 오브젝트. 질량 m 은 기존 눈 데이터 단위(cell)이며, 굴러가며 `sim.take_snow` 로
   눈 더미에서 실제 눈을 가져와 커지고, 녹을 때는 같은 양이 기존 물 시스템으로 돌아간다.
 - Snowman(type="dynamic"): 눈덩이 2~3개를 쌓은 묶음. 아래 공이 물리 본체, 위 공은 기울기(tilt)로 따라간다. 온도에 녹는다.
 - Snowman(type="decorative"): 장식용 완성형. 물리적으로 자유 배치되며 온도/자동 날씨/용해 계산을 절대 받지 않는다.
 두 유형은 type 필드와 저장 구조가 다르고, 용해 처리는 self.balls (= dynamic 전용) 에만 적용된다.
"""
from __future__ import annotations
from core.i18n import tr


import math
import time
import random
import uuid


from . import model as M

GRAV = 1500.0
PACK = 1.6               # 눈이 뭉쳐지며 줄어드는 비율 (눈덩이 면적 = 눈 면적 / PACK)
MIN_M = 2.5              # 이보다 작아지면 마저 녹아 사라짐
SNAP_HOLD = 0.7          # 조립 가능 상태가 이만큼 유지되면 결합
MAX_R_UNITS = 38.0       # 최대 눈덩이 반지름 (unit = cell/3 px)
DECO_R = (30.0, 22.0, 16.0)   # 장식용 눈사람 구 반지름 (unit 기준, scale 곱)


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class Ball:
    __slots__ = ("id", "x", "y", "vx", "vy", "m", "r", "ang", "w", "sid", "decor", "grounded")

    def __init__(self, bid, x, y, m, r):
        self.id = bid
        self.x, self.y, self.vx, self.vy = float(x), float(y), 0.0, 0.0
        self.m = m
        self.r = r
        self.ang = 0.0
        self.w = 0.0
        self.sid = None
        self.decor: list = []
        self.grounded = False


class Snowman:
    """type 으로 두 종류를 구분한다: "dynamic"(직접 제작) / "decorative"(장식용)."""

    def __init__(self, sid, typ):
        self.id = sid
        self.type = typ
        self.balls: list = []        # dynamic: 공 id (아래 -> 위)
        self.tilt = 0.0
        self.tw = 0.0
        self.prev_vx = 0.0
        self.L = 30.0
        self.dists: list = [0.0]
        self.x = self.y = 0.0        # decorative: 바닥 중심
        self.scale = 1.0
        self.rot = 0.0
        self.style = "classic"
        self.decor: list = []        # decorative: 장식 (role 로 구의 위치 결정)


class SnowmanWorld:
    def __init__(self, sim, seed=None):
        self.sim = sim
        self.rng = random.Random(seed)
        self.balls: dict = {}
        self.snowmen: dict = {}
        self.props: list = []
        self.selected = None
        self.selected_at = 0.0
        self.on_select = None
        self.mouse_push = True
        self.grab_on = True
        self.growth = 1.0
        self.push_gain = 1.0
        self.hints: list = []              # [(아래 공 id, 위 공 id, 진행률 0~1)]
        self._hold: dict = {}
        self.obstacles: list = []
        self._plist: list = []
        self._cur = None
        self._cur_prev = None
        self._dt = 1.0 / 30.0
        self._cv = (0.0, 0.0)
        self._mdown = False
        self._press = None
        self._grab = None
        self.t = 0.0
        self.dirty = False
        self.counter = 0                   # 상태가 바뀔 때마다 증가 (저장/UI 갱신 판단용)

    # ------------------------------------------------------------ 단위/크기
    @property
    def unit(self) -> float:
        return self.sim.cell / 3.0

    def radius_of(self, m: float) -> float:
        cell = self.sim.cell
        return max(2.0, cell * math.sqrt(max(m, 0.0) / (math.pi * PACK)))

    def mass_for_radius(self, r: float) -> float:
        cell = self.sim.cell
        return math.pi * PACK * (r / cell) ** 2

    def pmass(self, b: Ball) -> float:
        """물리 질량(무게). 크기에 따라 가볍거나 무겁다."""
        return max(0.4, math.pi * b.r * b.r / 200.0)

    def group_mass(self, sn: Snowman) -> float:
        return sum(self.pmass(self.balls[i]) for i in sn.balls if i in self.balls)

    @staticmethod
    def _id() -> str:
        return uuid.uuid4().hex[:8]

    def _touch(self):
        self.counter += 1
        self.dirty = True

    # ------------------------------------------------------------ 생성/삭제
    def _default_pos(self):
        b = self.sim.bounds
        return (b.left + b.right) / 2 + self.rng.uniform(-80, 80), b.top + 80

    def spawn_ball(self, radius=None, x=None, y=None, decor=None) -> str:
        if len(self.balls) >= M.LIMITS["balls"]:
            return ""
        u = self.unit
        r = (radius if radius is not None else 24.0) * u
        m = self.mass_for_radius(r)
        if x is None or y is None:
            x, y = self._default_pos()
        b = Ball(self._id(), x, y, m, self.radius_of(m))
        if decor:
            b.decor = [dict(d) for d in decor]
        self.balls[b.id] = b
        self.sim.spawn_external(m)
        self._touch()
        return b.id

    def add_decorative(self, preset="classic", x=None, y=None) -> str:
        if sum(1 for s in self.snowmen.values() if s.type == M.DECORATIVE) >= 20:
            return ""
        sn = Snowman(self._id(), M.DECORATIVE)
        sn.style = preset if preset in M.PRESETS else "classic"
        if x is None or y is None:
            b = self.sim.bounds
            x = (b.left + b.right) / 2 + self.rng.uniform(-120, 120)
            y = self.sim.floor_at(x) - 90
        sn.x, sn.y = x, y
        sn.scale = 1.0
        for kind, style, color in M.PRESETS[sn.style][1]:
            sn.decor.append(M.make_decor(self._id(), kind, style, color))
        self.snowmen[sn.id] = sn
        self._touch()
        return sn.id

    def duplicate(self, eid) -> str:
        ent = self.snowmen.get(eid)
        if ent is not None and ent.type == M.DECORATIVE:
            n = Snowman(self._id(), M.DECORATIVE)
            n.style, n.scale, n.rot = ent.style, ent.scale, ent.rot
            n.x, n.y = ent.x + 70 * ent.scale * self.unit, ent.y
            n.decor = [dict(d, id=self._id()) for d in ent.decor]
            self.snowmen[n.id] = n
            self._touch()
            return n.id
        if ent is not None:
            ids = []
            for bid in ent.balls:
                b = self.balls.get(bid)
                if b is None:
                    return ""
                nb = self.spawn_ball(radius=b.r / self.unit, x=b.x + 2 * b.r + 30, y=b.y,
                                     decor=[dict(d, id=self._id()) for d in b.decor])
                if not nb:
                    return ""
                self.balls[nb].m = b.m
                self.balls[nb].r = b.r
                ids.append(nb)
            # 복제된 눈덩이는 원본과 같은 양의 눈을 가진다 (spawn 이 다른 크기로 장부를 올렸으므로 차이를 정정)
            self._fix_ledger_after_clone(ent, ids)
            n = Snowman(self._id(), M.DYNAMIC)
            n.balls = ids
            for bid in ids:
                self.balls[bid].sid = n.id
            self.snowmen[n.id] = n
            self._sync_stack(n)
            n.prev_vx = 0.0
            self._touch()
            return n.id
        b = self.balls.get(eid)
        if b is not None:
            nb = self.spawn_ball(radius=b.r / self.unit, x=b.x + 2 * b.r + 30, y=b.y,
                                 decor=[dict(d, id=self._id()) for d in b.decor])
            if nb:
                self._fix_ledger_after_clone(None, [nb], [b])
            return nb
        return ""

    def _fix_ledger_after_clone(self, sn, new_ids, src=None):
        srcs = [self.balls[i] for i in sn.balls] if sn is not None else (src or [])
        for nid, s in zip(new_ids, srcs):
            nb = self.balls[nid]
            diff = s.m - nb.m
            nb.m = s.m
            nb.r = self.radius_of(nb.m)
            self.sim.mass_ext += diff
            self.sim.mass_added += diff

    def remove(self, eid):
        sn = self.snowmen.get(eid)
        if sn is not None:
            if sn.type == M.DYNAMIC:
                for bid in list(sn.balls):
                    self._delete_ball(bid)
            self.snowmen.pop(eid, None)
        elif eid in self.balls:
            self._delete_ball(eid)
        if self.selected == eid:
            self.select(None)
        self._touch()

    def _delete_ball(self, bid):
        b = self.balls.pop(bid, None)
        if b is None:
            return
        self.sim.discard_external(b.m)           # 사용자 삭제: 눈 청소처럼 명시적 삭제 (융해와 구분)
        sn = self.snowmen.get(b.sid) if b.sid else None
        if sn is not None and bid in sn.balls:
            sn.balls.remove(bid)
            self._after_member_loss(sn)

    def disassemble(self, sid):
        sn = self.snowmen.get(sid)
        if sn is None or sn.type != M.DYNAMIC:
            return
        self._release_members(sn, 0.0, 30.0)
        self.snowmen.pop(sid, None)
        if self.selected == sid:
            self.select(sn.balls[0] if sn.balls else None)
        self._touch()

    def _release_members(self, sn, tilt_w, kick):
        base = self.balls.get(sn.balls[0]) if sn.balls else None
        for i, bid in enumerate(sn.balls):
            b = self.balls.get(bid)
            if b is None:
                continue
            b.sid = None
            b.grounded = False
            if i > 0 and base is not None:
                d = sn.dists[i] if i < len(sn.dists) else 0.0
                b.vx = base.vx + tilt_w * d * math.cos(sn.tilt) + (kick if sn.tilt >= 0 else -kick) * i
                b.vy = base.vy + tilt_w * d * math.sin(sn.tilt) - 60.0

    def _after_member_loss(self, sn):
        """공이 녹아 사라지거나 삭제된 뒤 눈사람 묶음을 정리한다."""
        sn.balls = [i for i in sn.balls if i in self.balls]
        if len(sn.balls) < 2:
            for i in sn.balls:
                self.balls[i].sid = None
            self.snowmen.pop(sn.id, None)
            if self.selected == sn.id:
                self.select(sn.balls[0] if sn.balls else None)
        else:
            self._sync_stack(sn)

    # ------------------------------------------------------------ 선택
    def select(self, eid):
        self.selected = eid
        self.selected_at = time.monotonic() if eid is not None else 0.0
        if self.on_select is not None:
            try:
                self.on_select(eid)
            except Exception:
                pass

    def kind_of(self, eid):
        """'dynamic' / 'decorative' / 'ball' / None"""
        sn = self.snowmen.get(eid)
        if sn is not None:
            return sn.type
        return "ball" if eid in self.balls else None

    # ------------------------------------------------------------ 장식
    def _role_owner(self, eid, role):
        """장식이 붙을 대상 (decorative: 눈사람 자신, dynamic: 해당 위치의 공)."""
        sn = self.snowmen.get(eid)
        if sn is None:
            return None
        if sn.type == M.DECORATIVE:
            return sn
        if not sn.balls:
            return None
        if role == "body":
            idx = 1 if len(sn.balls) >= 3 else 0
        else:
            idx = len(sn.balls) - 1
        return self.balls.get(sn.balls[idx])

    def add_decor(self, eid, kind, style=None, color=None) -> str:
        if kind not in M.KINDS:
            return ""
        owner = self._role_owner(eid, M.role_of(kind))
        if owner is None or len(owner.decor) >= M.LIMITS["decor"]:
            return ""
        d = M.make_decor(self._id(), kind, style, color)
        owner.decor.append(d)
        self._touch()
        return d["id"]

    def decor_list(self, eid) -> list:
        """선택한 눈사람의 모든 장식 [(소유자, 장식)]."""
        sn = self.snowmen.get(eid)
        if sn is None:
            return []
        if sn.type == M.DECORATIVE:
            return [(sn, d) for d in sn.decor]
        out = []
        for bid in sn.balls:
            b = self.balls.get(bid)
            if b is not None:
                out.extend((b, d) for d in b.decor)
        return out

    def update_decor(self, eid, did, **kw):
        for _o, d in self.decor_list(eid):
            if d["id"] == did:
                if "kind" in kw:
                    kw.pop("kind")
                if "dx" in kw:
                    kw["dx"] = int(_clamp(kw["dx"], -60, 60))
                if "dy" in kw:
                    kw["dy"] = int(_clamp(kw["dy"], -60, 60))
                if "size" in kw:
                    kw["size"] = int(_clamp(kw["size"], 40, 220))
                if "color" in kw and kw["color"] not in M.COLORS:
                    kw.pop("color")
                d.update(kw)
                self._touch()
                return True
        return False

    def remove_decor(self, eid, did):
        for o, d in self.decor_list(eid):
            if d["id"] == did:
                o.decor.remove(d)
                self._touch()
                return True
        return False

    def set_deco(self, eid, scale=None, rot=None):
        sn = self.snowmen.get(eid)
        if sn is None or sn.type != M.DECORATIVE:
            return
        if scale is not None:
            sn.scale = _clamp(float(scale), 0.4, 3.0)
        if rot is not None:
            sn.rot = _clamp(float(rot), -60.0, 60.0)
        self._touch()

    def clear_props(self):
        self.props.clear()
        self._touch()

    # ------------------------------------------------------------ 장식용 눈사람 형상
    def deco_parts(self, sn) -> list:
        """장식용 눈사람의 구 [(cx, cy, r, ang, role들)] 아래 -> 위. (x, y) = 바닥 중심, rot 는 바닥을 축으로 한 기울기."""
        u = self.unit * sn.scale
        radii = [DECO_R[0] * u, DECO_R[1] * u, DECO_R[2] * u]
        th = math.radians(sn.rot)
        ax, ay = math.sin(th), -math.cos(th)
        cx, cy = sn.x + ax * radii[0], sn.y + ay * radii[0]
        out = [(cx, cy, radii[0], th)]
        dist = radii[0]
        for i in (1, 2):
            dist += (radii[i - 1] + radii[i]) * 0.88 if i == 1 else (radii[1] + radii[2]) * 0.88
            out.append((sn.x + ax * dist, sn.y + ay * dist, radii[i], th))
        return out

    # ------------------------------------------------------------ 엔진 연동
    def set_obstacles(self, rects):
        b = self.sim.bounds
        w, h = b.width, b.height
        keep = []
        for (l, t, r, bt) in rects:
            if (r - l) >= 0.9 * w and (bt - t) >= 0.85 * h:     # 최대화/전체화면 창은 장애물로 보지 않는다
                continue
            keep.append((l, t, r, bt))
        self.obstacles = keep

    def surfaces(self) -> list:
        """장식용 눈사람의 머리(모자) 꼭대기를 눈이 쌓이는 표면으로 등록한다 -> 기존 눈 물리와 충돌/축적."""
        from snow.physics import SurfaceInfo
        out = []
        for sn in self.snowmen.values():
            if sn.type != M.DECORATIVE:
                continue
            cx, cy, r, _a = self.deco_parts(sn)[2]
            top = cy - r * 0.95
            if any(d["kind"] == "hat" for d in sn.decor):
                top -= r * 0.95 * 0.8
            half = max(r * 0.55, self.sim.cell * 3.0)
            seg = [(cx - half, cx + half)]
            out.append(SurfaceInfo(("deco", sn.id), cx - half, top, cx + half, list(seg), list(seg), []))
        return out

    # ------------------------------------------------------------ 저장/복원
    def to_state(self) -> dict:
        cell2 = float(self.sim.cell) ** 2
        items, balls = [], []
        for sn in self.snowmen.values():
            if sn.type == M.DYNAMIC:
                items.append({"id": sn.id, "type": M.DYNAMIC, "balls": list(sn.balls)})
            else:
                items.append({"id": sn.id, "type": M.DECORATIVE, "x": round(sn.x, 1), "y": round(sn.y, 1),
                              "scale": round(sn.scale, 3), "rot": round(sn.rot, 1), "style": sn.style,
                              "decor": [dict(d) for d in sn.decor]})
        for b in self.balls.values():
            balls.append({"id": b.id, "x": round(b.x, 1), "y": round(b.y, 1), "area": round(b.m * cell2, 1),
                          "decor": [dict(d) for d in b.decor], "sid": b.sid})
        props = [dict(p) for p in self.props]
        return {"items": items, "balls": balls, "props": props}

    def load_state(self, items, balls, props):
        items, balls, props = M.clean_items(items), M.clean_balls(balls), M.clean_props(props)
        cell2 = float(self.sim.cell) ** 2
        for old in self.balls.values():
            self.sim.discard_external(old.m)
        self.balls.clear()
        self.snowmen.clear()
        self.props = props
        for rec in balls:
            m = rec["area"] / cell2
            b = Ball(rec["id"], rec["x"], rec["y"], m, self.radius_of(m))
            b.decor = rec["decor"]
            self.balls[b.id] = b
            self.sim.spawn_external(m)
        for it in items:
            sn = Snowman(it["id"], it["type"])
            if it["type"] == M.DYNAMIC:
                sn.balls = [i for i in it["balls"] if i in self.balls and self.balls[i].sid in (None, sn.id)]
                if len(sn.balls) < 2:
                    continue
                for i in sn.balls:
                    self.balls[i].sid = sn.id
                self._sync_stack(sn)
                sn.prev_vx = 0.0
            else:
                sn.x, sn.y, sn.scale, sn.rot = it["x"], it["y"], it["scale"], it["rot"]
                sn.style = it["style"] if it["style"] in M.PRESETS else "classic"
                sn.decor = it["decor"]
            self.snowmen[sn.id] = sn
        for b in self.balls.values():
            b.sid = None if b.sid not in self.snowmen else b.sid
        # 복원 전에 잡고 있던/선택했던 대상이 사라졌다면 상태를 정리한다 (설정 초기화나 백업 복원 직후 남는 유령 선택/잡기 방지)
        if self._grab is not None and self._grab.get("id") not in self.snowmen and self._grab.get("id") not in self.balls:
            self._grab = None
            self._press = None
        if self.selected is not None and self.selected not in self.snowmen and self.selected not in self.balls:
            self.selected = None
        self._touch()

    # ================================================================ 시뮬레이션
    def step(self, dt, cursor=None, mouse_down=False):
        if dt <= 0.0:
            return
        dt = min(dt, 0.05)
        self._dt = dt
        self._refresh_support()
        self._update_cursor(cursor, dt)
        self._mouse(cursor, mouse_down)
        n = max(1, int(math.ceil(dt / (1.0 / 90.0))))
        h = dt / n
        for _ in range(n):
            self._integrate(h)
        self._cursor_push()
        self._ball_collisions()
        self._assembly(dt)
        self._melt(dt)
        self._props_step(dt)
        self.t += dt
        if self.balls or self._grab:
            self.dirty = True

    # ------------------------------------------------------------ 지지면
    def _refresh_support(self):
        pl = []
        for key, p in self.sim.piles.items():
            if isinstance(key, tuple) and key and key[0] == "deco":
                continue
            if p.cells:
                pl.append((p, p.left, p.right, p.top, p.cell))
        self._plist = pl

    @staticmethod
    def _surf_y(p, sx):
        c = int((sx - p.left) // p.cell)
        if c < 0 or c >= len(p.cells) or not p.visible_at(sx):
            return None
        return p.top - p.cells[c] * p.cell

    def _support(self, b):
        r = b.r
        x = b.x
        best = None
        bp = None
        lo, hi = x - r, x + r
        for p, l, rr, _top, _cell in self._plist:
            if rr < lo or l > hi:
                continue
            for k in (-0.8, -0.4, 0.0, 0.4, 0.8):
                ys = self._surf_y(p, x + k * r)
                if ys is None or ys < b.y - 0.5 * r:
                    continue
                cy = ys - math.sqrt(max(0.0, r * r * (1.0 - k * k)))
                if best is None or cy < best:
                    best, bp = cy, p
        return best, bp

    def _slope(self, p, x, r):
        if p is None:
            return 0.0
        a = self._surf_y(p, x - 0.6 * r)
        c = self._surf_y(p, x + 0.6 * r)
        if a is None or c is None:
            return 0.0
        return _clamp((c - a) / (1.2 * r), -1.2, 1.2)

    def _point_support(self, x, y):
        best = None
        for p, _l, _r, _t, _c in self._plist:
            ys = self._surf_y(p, x)
            if ys is not None and ys >= y - 2 and (best is None or ys < best):
                best = ys
        for (l, t, r, bt) in self.obstacles:
            if l <= x <= r and t >= y - 2 and (best is None or t < best):
                best = t
        fl = self.sim.floor_at(x)
        return fl if best is None or best > fl else best

    # ------------------------------------------------------------ 커서/마우스
    def _update_cursor(self, cur, dt):
        self._cur_prev = self._cur
        if cur is None:
            self._cv = (0.0, 0.0)
            self._cur = None
            return
        if self._cur is not None:
            vx = (cur[0] - self._cur[0]) / dt
            vy = (cur[1] - self._cur[1]) / dt
            self._cv = (self._cv[0] * 0.5 + vx * 0.5, self._cv[1] * 0.5 + vy * 0.5)
        self._cur = (cur[0], cur[1])

    def _covered(self, pt) -> bool:
        x, y = pt
        for (l, t, r, b) in self.obstacles:
            if l <= x <= r and t <= y <= b:
                return True
        return False

    def _parts_of(self, sn):
        if sn.type == M.DECORATIVE:
            return [(c[0], c[1], c[2]) for c in self.deco_parts(sn)]
        return [(self.balls[i].x, self.balls[i].y, self.balls[i].r) for i in sn.balls if i in self.balls]

    def pick(self, pt):
        """pt 아래의 객체: ('snowman'|'ball', id) 또는 None. 가장 위(작은 y) 객체 우선."""
        best = None
        for sn in self.snowmen.values():
            for (cx, cy, r) in self._parts_of(sn):
                d = math.hypot(pt[0] - cx, pt[1] - cy)
                if d <= r + 3 and (best is None or cy < best[0]):
                    best = (cy, sn.id)
        for b in self.balls.values():
            if b.sid:
                continue
            if math.hypot(pt[0] - b.x, pt[1] - b.y) <= b.r + 3 and (best is None or b.y < best[0]):
                best = (b.y, b.id)
        return best[1] if best else None

    def _mouse(self, cur, down):
        if cur is None:
            down = False
        if down and not self._mdown:
            self._mdown = True
            self._press = (cur[0], cur[1], self.t) if cur else None
            if cur is not None and self.grab_on and not self._covered(cur):
                eid = self.pick(cur)
                if eid:
                    self._begin_grab(eid, cur)
        elif self._mdown and not down:
            self._mdown = False
            g, self._grab = self._grab, None
            if g is not None and self._press is not None and cur is not None:
                moved = math.hypot(cur[0] - self._press[0], cur[1] - self._press[1])
                if moved < 10 and self.t - self._press[2] < 0.45:
                    self.select(g["id"])
            self._press = None
        if self._grab is not None and cur is not None:
            sn = self.snowmen.get(self._grab["id"])
            if sn is not None and sn.type == M.DECORATIVE:
                b = self.sim.bounds
                sn.x = _clamp(cur[0] - self._grab["ox"], b.left, b.right)
                sn.y = _clamp(cur[1] - self._grab["oy"], b.top + 20, self.sim.floor_at(sn.x) + 10)
                self._touch()

    def _begin_grab(self, eid, cur):
        sn = self.snowmen.get(eid)
        if sn is not None and sn.type == M.DECORATIVE:
            self._grab = {"id": eid, "ox": cur[0] - sn.x, "oy": cur[1] - sn.y, "kind": "deco"}
            return
        if sn is not None:
            base = self.balls.get(sn.balls[0]) if sn.balls else None
        else:
            base = self.balls.get(eid)
        if base is None:
            return
        self._grab = {"id": eid, "ox": cur[0] - base.x, "oy": cur[1] - base.y, "kind": "body", "base": base.id}
        self.select(eid)

    def _grab_accel(self, b, h):
        g = self._grab
        if g is None or g["kind"] != "body" or g["base"] != b.id or self._cur is None:
            return
        sn = self.snowmen.get(b.sid) if b.sid else None
        mp = self.group_mass(sn) if sn is not None else self.pmass(b)
        tx, ty = self._cur[0] - g["ox"], self._cur[1] - g["oy"]
        ax = (tx - b.x) * 45.0 - b.vx * 9.0
        ay = (ty - b.y) * 45.0 - b.vy * 9.0
        amax = 60000.0 / mp                    # 무거울수록 잡아 끌기 어렵다 (마우스 힘 한계)
        mag = math.hypot(ax, ay)
        if mag > amax:
            ax, ay = ax * amax / mag, ay * amax / mag
        b.vx += ax * h
        b.vy += ay * h

    def _cursor_push(self):
        """마우스를 움직여 눈덩이를 밀거나 굴린다 (클릭 불필요). 무거울수록 같은 힘으로 덜 움직인다."""
        if not self.mouse_push or self._cur is None or self._grab is not None:
            return
        cvx, cvy = self._cv
        sp = math.hypot(cvx, cvy)
        if sp < 40.0 or self._covered(self._cur):
            return
        cx, cy = self._cur
        px, py = self._cur_prev if self._cur_prev is not None else self._cur
        sx, sy = cx - px, cy - py
        seg2 = sx * sx + sy * sy
        for b in list(self.balls.values()):
            # 커서가 한 프레임에 지나간 선분과 눈덩이의 최근접점 (빠르게 휘둘러도 놓치지 않는다)
            t = 0.0 if seg2 < 1e-9 else _clamp(((b.x - px) * sx + (b.y - py) * sy) / seg2, 0.0, 1.0)
            qx, qy = px + sx * t, py + sy * t
            dx, dy = b.x - qx, b.y - qy
            d = math.hypot(dx, dy)
            if d > b.r + 6:
                continue
            nx, ny = cvx / sp, cvy / sp                                # 마우스가 미는 방향
            sn = self.snowmen.get(b.sid) if b.sid else None
            mp = self.group_mass(sn) if sn is not None else self.pmass(b)
            base = self.balls[sn.balls[0]] if sn is not None else b
            rel = (cvx - base.vx) * nx + (cvy - base.vy) * ny
            if rel <= 0:
                continue
            k = _clamp(0.65 * self.push_gain / (1.0 + mp / 5.0), 0.0, 0.9)
            dv = min(rel * k, 14000.0 * self.push_gain / mp * self._dt)      # 무거울수록 같은 마우스 힘으로 덜 움직임
            base.vx += nx * dv
            base.vy += min(0.0, ny * dv) * 0.6
            if sn is not None:
                i = sn.balls.index(b.id)
                L = max(sn.L, 12.0)
                rel_h = (sn.dists[i] / L) if i < len(sn.dists) else 1.0
                sn.tw += -(nx * dv) / L * 0.85 * max(0.3, rel_h)

    # ------------------------------------------------------------ 적분
    def _integrate(self, h):
        for b in self.balls.values():
            b.r = self.radius_of(b.m)
        for sn in list(self.snowmen.values()):
            if sn.type == M.DYNAMIC and sn.balls and sn.balls[0] in self.balls:
                self._move_ball(self.balls[sn.balls[0]], h, locked=True)
                self._sync_stack(sn)
                self._tilt_step(sn, h)
        for b in list(self.balls.values()):
            if b.sid is None:
                self._move_ball(b, h, locked=False)

    def _move_ball(self, b, h, locked):
        sim = self.sim
        r = b.r
        b.vy += GRAV * h
        self._grab_accel(b, h)
        b.x += b.vx * h
        b.y += b.vy * h
        bd = sim.bounds
        if b.x - r < bd.left:
            b.x = bd.left + r
            b.vx = abs(b.vx) * 0.3
        elif b.x + r > bd.right:
            b.x = bd.right - r
            b.vx = -abs(b.vx) * 0.3
        cy, bp = self._support(b)
        b.grounded = False
        if cy is not None and b.y >= cy - 0.5:
            if b.y > cy:
                b.y = cy
            if b.vy > 0:
                b.vy = -b.vy * 0.22 if b.vy > 140 else 0.0
            b.grounded = True
            slope = self._slope(bp, b.x, r)
            b.vx += GRAV * slope * (0.35 if locked else 0.6) * h      # 경사면에서는 중력으로 굴러간다
            b.vx *= math.exp(-(2.2 if locked else 0.45) * h)           # 마찰/눈 위 구름 저항
            if not locked and abs(b.vx) < 30.0 and abs(slope) < 0.4:
                b.vx *= math.exp(-5.0 * h)                             # 느리면 멈춰 정착한다
            if locked:
                b.w = 0.0
            else:
                b.w = b.vx / r
                if abs(b.vx) > 12.0 and bp is not None and self.growth > 0.0:
                    self._absorb(b, bp, h)
        else:
            b.w *= math.exp(-0.2 * h)
        b.ang += b.w * h
        self._rect_collide(b)
        self._static_collide(b)
        floor = sim.floor_at(b.x)
        if b.y + r > floor + 2:
            b.y = floor - r
            b.vy = 0.0
            b.grounded = True

    def _absorb(self, b, pile, h):
        """굴러가는 눈덩이가 앞쪽 눈을 실제 눈 더미에서 가져간다. 눈이 많을수록 빨리, 적으면 거의 못 자란다."""
        r = b.r
        if r >= MAX_R_UNITS * self.unit:
            return
        dx = b.vx * h
        d = 1 if dx > 0 else -1
        a, c = b.x + d * 0.15 * r, b.x + d * 0.75 * r
        lo, hi = (a, c) if a < c else (c, a)
        w = max(hi - lo, 1.0)
        f = min(1.0, abs(dx) / w) * self.growth
        cell = pile.cell
        c0 = int((lo - pile.left) // cell)
        c1 = int((hi - pile.left) // cell)
        taken = self.sim.take_snow(pile, c0, c1, f)
        if taken > 0.0:
            old = b.m
            b.m += taken
            b.vx *= math.sqrt(old / b.m)                               # 눈을 모으면 무거워져 조금 느려진다 (운동량)
            self.sim.push_snow(pile, c1 + d, d * min(abs(b.vx), 400.0) * 0.002)      # 주변 눈이 앞으로 밀려 재배치
            self._touch()

    def _rect_collide(self, b):
        r = b.r
        for (l, t, rr, bt) in self.obstacles:
            if b.x + r < l or b.x - r > rr or b.y + r < t or b.y - r > bt:
                continue
            qx = _clamp(b.x, l, rr)
            qy = _clamp(b.y, t, bt)
            dx, dy = b.x - qx, b.y - qy
            d2 = dx * dx + dy * dy
            if d2 >= r * r:
                continue
            if d2 > 1e-6:
                d = math.sqrt(d2)
                nx, ny, pen = dx / d, dy / d, r - d
            else:
                gaps = ((b.x - l, -1, 0), (rr - b.x, 1, 0), (b.y - t, 0, -1), (bt - b.y, 0, 1))
                g = min(gaps, key=lambda e: e[0])
                nx, ny, pen = g[1], g[2], g[0] + r
            b.x += nx * pen
            b.y += ny * pen
            vn = b.vx * nx + b.vy * ny
            if vn < 0:
                b.vx -= 1.3 * vn * nx
                b.vy -= 1.3 * vn * ny
                if ny < -0.7 and abs(b.vy) < 100:
                    b.vy = 0.0
                    b.grounded = True

    def _static_collide(self, b):
        """장식용 눈사람은 움직이지 않는 장애물: 눈덩이가 부딪히면 튕겨 나간다."""
        for sn in self.snowmen.values():
            if sn.type != M.DECORATIVE:
                continue
            for (cx, cy, cr, _a) in self.deco_parts(sn):
                dx, dy = b.x - cx, b.y - cy
                d = math.hypot(dx, dy)
                rs = b.r + cr
                if d >= rs or d < 1e-6:
                    continue
                nx, ny = dx / d, dy / d
                b.x += nx * (rs - d)
                b.y += ny * (rs - d)
                vn = b.vx * nx + b.vy * ny
                if vn < 0:
                    b.vx -= 1.3 * vn * nx
                    b.vy -= 1.3 * vn * ny

    # ------------------------------------------------------------ 눈사람 쌓기/기울기
    def _sync_stack(self, sn):
        """아래 공을 기준으로 위 공들의 위치를 기울기(tilt)에 맞춰 배치한다."""
        bs = [self.balls[i] for i in sn.balls if i in self.balls]
        if not bs:
            return
        b0 = bs[0]
        ax, ay = math.sin(sn.tilt), -math.cos(sn.tilt)
        dists = [0.0]
        for i in range(1, len(bs)):
            dists.append(dists[-1] + (bs[i - 1].r + bs[i].r) * 0.9)
        tm = sum(self.pmass(b) for b in bs)
        sn.L = max(12.0, sum(self.pmass(b) * d for b, d in zip(bs, dists)) / max(tm, 1e-6))
        sn.dists = dists
        for b, d in zip(bs, dists):
            if b is b0:
                continue
            b.x = b0.x + ax * d
            b.y = b0.y + ay * d
            b.vx = b0.vx + sn.tw * d * math.cos(sn.tilt)
            b.vy = b0.vy + sn.tw * d * math.sin(sn.tilt)
            b.ang = sn.tilt
            b.w = 0.0
            b.grounded = False
        b0.ang = 0.0

    def _tilt_step(self, sn, h):
        b0 = self.balls[sn.balls[0]]
        dvx = b0.vx - sn.prev_vx
        sn.prev_vx = b0.vx
        L = max(sn.L, 12.0)
        w0sq = _clamp(GRAV * b0.r / (L * L) * 0.9, 20.0, 120.0)
        w0 = math.sqrt(w0sq)
        sn.tw += (-w0sq * sn.tilt - 2.0 * 0.28 * w0 * sn.tw) * h - dvx / L * 0.85
        sn.tilt += sn.tw * h
        tc = _clamp(0.55 * b0.r / (L + 0.2 * b0.r), 0.28, 0.7)
        if abs(sn.tilt) > tc:
            self._topple(sn)
            return
        if abs(sn.tilt) < 0.004 and abs(sn.tw) < 0.03:
            sn.tilt = sn.tw = 0.0

    def _topple(self, sn):
        """충격으로 넘어짐: 눈덩이들이 분리된다. 장식은 각 눈덩이에 남아 다시 조립하면 그대로 이어진다."""
        self._sync_stack(sn)
        self._release_members(sn, sn.tw, 40.0)
        self.snowmen.pop(sn.id, None)
        if self.selected == sn.id:
            self.select(sn.balls[0] if sn.balls else None)
        self._touch()

    # ------------------------------------------------------------ 충돌
    def _ball_collisions(self):
        bs = list(self.balls.values())
        for i in range(len(bs)):
            a = bs[i]
            for j in range(i + 1, len(bs)):
                b = bs[j]
                if a.sid is not None and a.sid == b.sid:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                rs = a.r + b.r
                if dx > rs or dx < -rs or dy > rs or dy < -rs:
                    continue
                if dx * dx + dy * dy >= rs * rs:
                    continue
                self._resolve_pair(a, b)

    def _resolve_pair(self, a, b):
        dx, dy = b.x - a.x, b.y - a.y
        d = math.hypot(dx, dy)
        rs = a.r + b.r
        if d < 1e-6:
            nx, ny, d = 0.0, -1.0, 0.0
        else:
            nx, ny = dx / d, dy / d
        pen = rs - d
        sa = self.snowmen.get(a.sid) if a.sid else None
        sb = self.snowmen.get(b.sid) if b.sid else None
        ba = self.balls[sa.balls[0]] if sa else a
        bb = self.balls[sb.balls[0]] if sb else b
        ma = self.group_mass(sa) if sa else self.pmass(a)
        mb = self.group_mass(sb) if sb else self.pmass(b)
        ia, ib = 1.0 / ma, 1.0 / mb
        tot = ia + ib
        corr = pen * 0.8 / tot
        ba.x -= nx * corr * ia
        bb.x += nx * corr * ib
        if not sa:
            ba.y -= ny * corr * ia
        if not sb:
            bb.y += ny * corr * ib
        vn = (bb.vx - ba.vx) * nx + (bb.vy - ba.vy) * ny
        if vn < 0:
            j = -1.35 * vn / tot
            ba.vx -= j * ia * nx
            bb.vx += j * ib * nx
            if not sa:
                ba.vy -= j * ia * ny
            if not sb:
                bb.vy += j * ib * ny
            if sa:
                self._kick(sa, a, -j * ia * nx)
            if sb:
                self._kick(sb, b, j * ib * nx)
        for sn in (sa, sb):
            if sn is not None:
                self._sync_stack(sn)

    def _kick(self, sn, ball, dvx):
        """충격을 받은 눈사람은 기울어진다 (맞은 공이 높을수록 많이)."""
        L = max(sn.L, 12.0)
        i = sn.balls.index(ball.id)
        rel = (sn.dists[i] / L) if i < len(sn.dists) else 1.0
        sn.tw += -dvx / L * 0.85 * max(0.3, rel)

    # ------------------------------------------------------------ 조립
    def _assembly(self, dt):
        hints = []
        seen = set()
        lowers = []
        for b in self.balls.values():
            if b.sid is None:
                lowers.append((b, None))
        for sn in self.snowmen.values():
            if sn.type == M.DYNAMIC and 2 <= len(sn.balls) < 3 and sn.balls[-1] in self.balls:
                lowers.append((self.balls[sn.balls[-1]], sn))
        for lower, sn in lowers:
            for B in self.balls.values():
                if B is lower or B.sid is not None or B.m >= lower.m * 0.9:
                    continue
                if sn is not None and B.id in sn.balls:
                    continue
                if abs(B.x - lower.x) > 0.45 * lower.r + 4 or B.y >= lower.y:
                    continue
                target = (lower.r + B.r) * 0.88
                gap = (lower.y - B.y) - target
                if gap < -0.35 * B.r or gap > 0.9 * B.r + 6:
                    continue
                if abs(B.vx - lower.vx) > 140 or abs(B.vy - lower.vy) > 220:
                    continue
                if sn is not None:
                    if abs(sn.tilt) > 0.08:
                        continue
                elif not lower.grounded or abs(lower.vx) > 60:
                    continue
                key = (lower.id, B.id)
                seen.add(key)
                hold = self._hold.get(key, 0.0) + dt
                self._hold[key] = hold
                hints.append((lower.id, B.id, min(1.0, hold / SNAP_HOLD)))
                grabbed = self._grab is not None and self._grab.get("base") == B.id
                if not grabbed:
                    tx, ty = lower.x, lower.y - target
                    B.vx += ((tx - B.x) * 14.0 - B.vx * 5.0) * dt
                    B.vy += ((ty - B.y) * 14.0 - B.vy * 5.0) * dt - GRAV * dt * 0.9
                if hold >= SNAP_HOLD:
                    self._bind(lower, sn, B)
                    self._hold.clear()
                    self.hints = []
                    return
        for k in [k for k in self._hold if k not in seen]:
            self._hold.pop(k, None)
        self.hints = hints

    def _bind(self, lower, sn, B):
        if sn is None:
            sn = Snowman(self._id(), M.DYNAMIC)
            sn.balls = [lower.id]
            lower.sid = sn.id
            self.snowmen[sn.id] = sn
        sn.balls.append(B.id)
        B.sid = sn.id
        B.vx = B.vy = 0.0
        if self._grab is not None and self._grab.get("base") == B.id:
            self._grab = None
        base = self.balls[sn.balls[0]]
        sn.prev_vx = base.vx
        sn.tilt = sn.tw = 0.0
        self._sync_stack(sn)
        self.select(sn.id)
        self._touch()

    # ------------------------------------------------------------ 융해 (dynamic 전용)
    def _melt(self, dt):
        """직접 제작한 눈덩이/눈사람만 녹는다 (self.balls 는 dynamic 전용; 장식용 눈사람은 이 경로에 없다).
        기존 온도 시스템의 용해율(sim.melt_rate)을 그대로 쓰고, 눈 더미 용해와는 별개의 객체라 중복 적용되지 않는다."""
        if not self.balls:
            return
        rate = self.sim.melt_rate()
        if rate <= 0.0:
            return
        cell = self.sim.cell
        gone = []
        for b in list(self.balls.values()):
            dm = min(b.m, rate * (math.pi * b.r / cell) * 0.6 * dt)
            if b.m - dm < MIN_M:
                dm = b.m
            b.m -= dm
            self.sim.melt_external(dm)
            if b.m <= 1e-9:
                gone.append(b.id)
            b.r = self.radius_of(b.m)
        self._touch()
        for bid in gone:
            self._finish_melt(bid)

    def _finish_melt(self, bid):
        """눈덩이가 완전히 녹음: 장식품은 사라지지 않고 그 자리에 떨어져 남는다."""
        b = self.balls.pop(bid, None)
        if b is None:
            return
        for d in b.decor:
            self.props.append({"id": d["id"], "kind": d["kind"], "style": d["style"], "color": d["color"],
                               "size": d["size"], "x": b.x + self.rng.uniform(-0.6, 0.6) * max(b.r, 6.0) + 6.0,
                               "y": b.y, "r": 20.0, "vy": 0.0, "rest": False})
        self.props = self.props[-M.LIMITS["props"]:]
        sn = self.snowmen.get(b.sid) if b.sid else None
        if sn is not None and bid in sn.balls:
            was_base = sn.balls[0] == bid
            sn.balls.remove(bid)
            if was_base:
                for i in sn.balls:
                    self.balls[i].sid = None
                self.snowmen.pop(sn.id, None)
                if self.selected == sn.id:
                    self.select(None)
            else:
                self._after_member_loss(sn)
        elif self.selected == bid:
            self.select(None)

    def _props_step(self, dt):
        for p in self.props:
            if p.get("rest"):
                continue
            p["vy"] = p.get("vy", 0.0) + GRAV * dt
            p["y"] += p["vy"] * dt
            sy = self._point_support(p["x"], p["y"] - 6.0)
            if p["y"] >= sy - 3.0:
                p["y"] = sy - 3.0
                p["rest"] = True
                p["vy"] = 0.0
                self._touch()

    # ------------------------------------------------------------ 상태 설명 (UI)
    def status_text(self) -> str:
        if self.hints:
            lo, up, pr = max(self.hints, key=lambda h: h[2])
            return tr("조립 가능! 그대로 두면 쌓여요 ({0}%)").format(int(pr * 100))
        n_dyn = sum(1 for s in self.snowmen.values() if s.type == M.DYNAMIC)
        n_dec = sum(1 for s in self.snowmen.values() if s.type == M.DECORATIVE)
        loose = sum(1 for b in self.balls.values() if b.sid is None)
        return tr("직접 제작 {0} · 장식용 {1} · 눈덩이 {2}").format(n_dyn, n_dec, loose)
