"""스노우볼 데이터 모델: 기본값, 검증/복구, 장식 배치 규칙, 눈 비율 (Qt 비의존).

상태는 JSON 으로 저장 가능한 dict 이다.
 globe = {id, name, x, y, size, design, background, shake_mode, visible,
          snow: {normal, big, sparkle, amount, size, speed}, decor: [item]}
 item  = {id, kind, x, y, scale, rot}      # (x, y) = 장식 앵커(아래 가운데), 2D 좌표만 사용
"""
from __future__ import annotations
from core.i18n import tr


import copy
import math
import uuid

from . import catalog as C

DEFAULT_SNOW = {"normal": 60, "big": 25, "sparkle": 15, "amount": 200, "size": 1.0, "speed": 1.0}
AMOUNT_RANGE = (20, 600)
SNOW_SIZE_RANGE = (0.6, 2.0)
SPEED_RANGE = (0.3, 3.0)


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def _num(v, default, lo, hi, cast=float):
    try:
        x = cast(float(v))
    except (TypeError, ValueError, OverflowError):
        return default
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return default
    return max(lo, min(hi, x))


# ------------------------------------------------------------------ 눈 비율 (합계 항상 100)
def normalize_ratios(n, b, s) -> tuple[int, int, int]:
    vals = [max(0.0, float(n)), max(0.0, float(b)), max(0.0, float(s))]
    total = sum(vals)
    if total <= 0:
        return 60, 25, 15
    raw = [v * 100.0 / total for v in vals]
    base = [int(r) for r in raw]
    rest = 100 - sum(base)
    for i in sorted(range(3), key=lambda i: raw[i] - base[i], reverse=True)[:rest]:
        base[i] += 1
    return base[0], base[1], base[2]


def set_ratio(snow: dict, key: str, value) -> dict:
    """key 비율을 value 로 바꾸고 나머지 둘을 기존 비율대로 나눠 합계를 100 으로 유지한다. snow 를 제자리에서 수정."""
    if key not in C.SNOW_KINDS:
        return snow
    value = int(max(0, min(100, round(float(value)))))
    others = [k for k in C.SNOW_KINDS if k != key]
    old = [max(0.0, float(snow.get(k, 0))) for k in others]
    rest = 100 - value
    if sum(old) <= 0:
        old = [1.0, 1.0]
    tot = sum(old)
    raw = [rest * o / tot for o in old]
    part = [int(r) for r in raw]
    for i in sorted(range(2), key=lambda i: raw[i] - part[i], reverse=True)[:rest - sum(part)]:
        part[i] += 1
    snow[key] = value
    for k, p in zip(others, part):
        snow[k] = p
    return snow


def split_counts(amount: int, snow: dict) -> dict:
    """전체 눈 개수를 비율대로 나눈다 (합계 = amount)."""
    n, b, s = (max(0, int(snow.get(k, 0))) for k in C.SNOW_KINDS)
    tot = (n + b + s) or 100
    raw = [amount * v / tot for v in (n, b, s)]
    base = [int(r) for r in raw]
    for i in sorted(range(3), key=lambda i: raw[i] - base[i], reverse=True)[:amount - sum(base)]:
        base[i] += 1
    return dict(zip(C.SNOW_KINDS, base))


def clean_snow(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    n, b, s = normalize_ratios(raw.get("normal", DEFAULT_SNOW["normal"]), raw.get("big", DEFAULT_SNOW["big"]),
                               raw.get("sparkle", DEFAULT_SNOW["sparkle"]))
    return {"normal": n, "big": b, "sparkle": s,
            "amount": _num(raw.get("amount"), DEFAULT_SNOW["amount"], *AMOUNT_RANGE, cast=int),
            "size": round(_num(raw.get("size"), 1.0, *SNOW_SIZE_RANGE), 2),
            "speed": round(_num(raw.get("speed"), 1.0, *SPEED_RANGE), 2)}


# ------------------------------------------------------------------ 장식 배치 규칙 (2D 좌표 + 렌더링 순서)
def item_extent(kind: str, scale: float, rot: float):
    """앵커 기준 회전된 외곽 상자 (minx, maxx, miny, maxy). y 가 음수면 위쪽."""
    d = C.DECOR[kind]
    w, h = d["w"] * scale, d["h"] * scale
    th = math.radians(rot)
    c, s = math.cos(th), math.sin(th)
    xs, ys = [], []
    for px, py in ((-w / 2, 0.0), (w / 2, 0.0), (-w / 2, -h), (w / 2, -h)):
        xs.append(px * c - py * s)
        ys.append(px * s + py * c)
    return min(xs), max(xs), min(ys), max(ys)


def clamp_to_ground(x: float, y: float) -> tuple[float, float]:
    """앵커를 바닥 타원 안으로 끌어 넣는다 (유리 구체의 형태를 고려한 배치 가능 영역)."""
    dx, dy = (x - C.GX) / C.GRX, (y - C.GY) / C.GRY
    d = math.hypot(dx, dy)
    if d > 0.98:
        dx, dy = dx / d * 0.98, dy / d * 0.98
    return C.GX + dx * C.GRX, C.GY + dy * C.GRY


def fits_in_sphere(x: float, y: float, kind: str, scale: float, rot: float) -> bool:
    d = C.DECOR[kind]
    w, h = d["w"] * scale, d["h"] * scale
    th = math.radians(rot)
    c, s = math.cos(th), math.sin(th)
    lim = C.WALL_R - 1.5
    for px, py in ((-w / 2, 0.0), (w / 2, 0.0), (-w / 2, -h), (w / 2, -h)):
        cx, cy = x + px * c - py * s, y + px * s + py * c
        if math.hypot(cx - C.SCX, cy - C.SCY) > lim:
            return False
    return True


def max_scale(kind: str, x: float, y: float, rot: float = 0.0) -> float:
    s = C.SCALE_MAX
    while s > C.SCALE_MIN and not fits_in_sphere(x, y, kind, s, rot):
        s = round(s - 0.05, 2)
    return s


def fit_item(item: dict) -> dict:
    """장식을 배치 가능 영역(바닥 타원 + 유리 안쪽)에 맞춘다. 제자리 수정 후 반환."""
    x, y = clamp_to_ground(float(item["x"]), float(item["y"]))
    scale = round(max(C.SCALE_MIN, min(C.SCALE_MAX, float(item["scale"]))), 2)
    rot = float(item["rot"]) % 360.0
    kind = item["kind"]
    scale = min(scale, max_scale(kind, x, y, rot))
    if not fits_in_sphere(x, y, kind, scale, rot) and rot:
        rot = 0.0
        scale = min(scale, max_scale(kind, x, y, rot))
    item.update(x=round(x, 2), y=round(y, 2), scale=round(max(C.SCALE_MIN, scale), 2), rot=int(round(rot)) % 360)
    return item


def new_item(kind: str, x: float = C.GX, y: float = C.GY, scale: float = 1.0, rot: float = 0.0) -> dict:
    return fit_item({"id": new_id(), "kind": kind, "x": x, "y": y, "scale": scale, "rot": rot})


def clean_item(raw):
    if not isinstance(raw, dict) or raw.get("kind") not in C.DECOR:
        return None
    return fit_item({"id": str(raw.get("id") or new_id())[:16], "kind": raw["kind"],
                     "x": _num(raw.get("x"), C.GX, 0, C.GW), "y": _num(raw.get("y"), C.GY, 0, C.GH),
                     "scale": _num(raw.get("scale"), 1.0, C.SCALE_MIN, C.SCALE_MAX),
                     "rot": _num(raw.get("rot"), 0, -3600, 3600)})


def draw_order(items: list) -> list:
    """렌더링 순서: 앵커 Y 가 작은(뒤쪽) 것부터. 깊이 Z 는 없다."""
    return sorted(items, key=lambda it: (it["y"], it["x"]))


# ------------------------------------------------------------------ 스노우볼 한 개
def new_globe(x: int = 240, y: int = 240, design: str = C.DEFAULT_DESIGN,
              background: str = C.DEFAULT_BACKGROUND, with_demo: bool = True) -> dict:
    decor = []
    if with_demo:
        decor = [new_item("small_tree", 36, 68, 1.2), new_item("snowman", 58, 76, 1.1),
                 new_item("gift", 47, 80, 0.9)]
    return {"id": new_id(), "name": "", "x": int(x), "y": int(y), "size": 2, "design": design,
            "background": background, "shake_mode": "both", "shake_strength": 1.0, "position_locked": False, "visible": True,
            "auto_shake": True, "auto_shake_sec": C.AUTO_SHAKE_DEFAULT_SEC,
            "snow": dict(DEFAULT_SNOW), "decor": decor}


def clean_globe(raw):
    """저장된 dict 를 검증하고 빠진 값을 기본값으로 채운다. 쓸 수 없으면 None."""
    if not isinstance(raw, dict):
        return None
    design = raw.get("design") if raw.get("design") in C.DESIGNS else C.DEFAULT_DESIGN
    bg = raw.get("background") if raw.get("background") in C.BACKGROUNDS else C.DEFAULT_BACKGROUND
    decor = []
    seen = set()
    for r in (raw.get("decor") if isinstance(raw.get("decor"), list) else [])[:C.MAX_DECOR]:
        it = clean_item(r)
        if it is None:
            continue
        if it["id"] in seen:
            it["id"] = new_id()
        seen.add(it["id"])
        decor.append(it)
    return {"id": str(raw.get("id") or new_id())[:16], "name": str(raw.get("name") or "")[:20],
            "x": _num(raw.get("x"), 240, -20000, 20000, cast=int), "y": _num(raw.get("y"), 240, -20000, 20000, cast=int),
            "size": _num(raw.get("size"), 2, C.GLOBE_SIZE_MIN, C.GLOBE_SIZE_MAX, cast=int),
            "design": design, "background": bg,
            "shake_mode": raw.get("shake_mode") if raw.get("shake_mode") in C.SHAKE_MODES else "both",
            "shake_strength": round(_num(raw.get("shake_strength"), 1.0, 0.5, 2.0), 2),
            "position_locked": bool(raw.get("position_locked", False)),
            "visible": bool(raw.get("visible", True)),
            "auto_shake": bool(raw.get("auto_shake", True)),
            "auto_shake_sec": _num(raw.get("auto_shake_sec"), C.AUTO_SHAKE_DEFAULT_SEC, C.AUTO_SHAKE_RANGE[0], C.AUTO_SHAKE_RANGE[1], cast=int),
            "snow": clean_snow(raw.get("snow")), "decor": decor}


def clone_globe(g: dict, dx: int = 40, dy: int = 40) -> dict:
    """복제: 새 id 와 (장식 포함) 새 장식 id 를 부여하고 위치를 조금 옮긴다."""
    c = clean_globe(copy.deepcopy(g))
    c["id"] = new_id()
    c["x"] += dx
    c["y"] += dy
    c["name"] = (c["name"] + tr(" 복사"))[:20] if c["name"] else ""
    for it in c["decor"]:
        it["id"] = new_id()
    return c
