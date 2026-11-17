"""눈사람 데이터 모델: 장식 목록, 프리셋, 저장 데이터 정리(sanitize). 순수 Python.

내부 유형(type): "dynamic" = 직접 제작(온도에 녹음), "decorative" = 장식용 완성형(절대 녹지 않음).
저장 구조 (settings.json 의 snowman 섹션)
 - items: [{id, type, ...}]  dynamic 은 {balls:[공 id, 아래->위]}, decorative 는 {x,y,scale,rot,style,decor}
 - balls: [{id, x, y, area, decor, sid}]  모든 눈덩이 (눈사람에 속한 것 포함, area = 눈 면적 px^2)
 - props: [{id, kind, style, color, size, x, y}]  눈사람이 녹으며 남긴 장식
"""
from __future__ import annotations
from core.i18n import tr


DYNAMIC = "dynamic"
DECORATIVE = "decorative"

# 장식 종류: kind -> (표시 이름, 스타일 [(키, 이름)], 기본 색, 붙는 위치)
KINDS = {
    "hat": (tr("모자"), [("tophat", tr("신사모")), ("santa", tr("산타모")), ("beanie", tr("털모자"))], "black", "head"),
    "scarf": (tr("목도리"), [("plain", tr("기본", "plain")), ("stripe", tr("줄무늬"))], "red", "neck"),
    "eyes": (tr("눈", "eyes"), [("dots", tr("점")), ("happy", tr("웃는"))], "black", "head"),
    "nose": (tr("코"), [("carrot", tr("당근")), ("button", tr("단추"))], "orange", "head"),
    "mouth": (tr("입"), [("smile", tr("미소")), ("round", tr("동그란"))], "black", "head"),
    "buttons": (tr("단추"), [("three", tr("세 개")), ("two", tr("두 개"))], "black", "body"),
    "arms": (tr("팔"), [("stick", tr("나뭇가지")), ("wave", tr("만세"))], "brown", "body"),
    "gloves": (tr("장갑"), [("mitten", tr("벙어리")), ("round", tr("동그란"))], "blue", "body"),
}
KIND_ORDER = ["hat", "scarf", "eyes", "nose", "mouth", "buttons", "arms", "gloves"]
COLORS = {
    "red": "#d63a3a", "green": "#3f9d5a", "blue": "#4a7bd6", "black": "#2a2a33", "orange": "#f08a2c",
    "yellow": "#f3c94a", "purple": "#8f5ad6", "white": "#ffffff", "brown": "#7a4a2a", "pink": "#f08ac0",
}
ROLES = ("head", "neck", "body")

# 장식용 눈사람 프리셋 (장식용 눈사람 선택 메뉴)
PRESETS = {
    "classic": (tr("기본 눈사람"), [("hat", "tophat", "black"), ("scarf", "stripe", "red"), ("eyes", "dots", "black"),
                             ("nose", "carrot", "orange"), ("mouth", "smile", "black"), ("buttons", "three", "black"),
                             ("arms", "stick", "brown")]),
    "santa": (tr("산타 눈사람"), [("hat", "santa", "red"), ("scarf", "plain", "white"), ("eyes", "happy", "black"),
                           ("nose", "button", "red"), ("mouth", "round", "black"), ("buttons", "two", "red"),
                           ("gloves", "mitten", "red")]),
    "cool": (tr("멋쟁이 눈사람"), [("hat", "beanie", "blue"), ("scarf", "stripe", "blue"), ("eyes", "dots", "black"),
                            ("nose", "carrot", "orange"), ("mouth", "smile", "black"), ("gloves", "round", "green")]),
}

LIMITS = {"balls": 40, "items": 30, "props": 60, "decor": 24}


def default_color(kind: str) -> str:
    return KINDS[kind][2]


def role_of(kind: str) -> str:
    return KINDS[kind][3]


def make_decor(did: str, kind: str, style: str | None = None, color: str | None = None,
               dx: int = 0, dy: int = 0, size: int = 100) -> dict:
    if kind not in KINDS:
        raise ValueError(kind)
    styles = [k for k, _ in KINDS[kind][1]]
    if style not in styles:
        style = styles[0]
    if color not in COLORS:
        color = default_color(kind)
    return {"id": did, "kind": kind, "style": style, "color": color,
            "dx": int(dx), "dy": int(dy), "size": int(size)}


def clean_decor(lst) -> list:
    out, seen = [], set()
    for d in lst if isinstance(lst, list) else []:
        if not isinstance(d, dict) or len(out) >= LIMITS["decor"]:
            continue
        try:
            did = str(d["id"])
            if did in seen:
                continue
            c = make_decor(did, str(d["kind"]), d.get("style"), d.get("color"),
                           max(-60, min(60, int(d.get("dx", 0)))), max(-60, min(60, int(d.get("dy", 0)))),
                           max(40, min(220, int(d.get("size", 100)))))
        except (KeyError, TypeError, ValueError):
            continue
        seen.add(did)
        out.append(c)
    return out


def _num(v, default=0.0, lo=-1e7, hi=1e7) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:
        return default
    return max(lo, min(hi, f))


def clean_balls(lst) -> list:
    out, seen = [], set()
    for b in lst if isinstance(lst, list) else []:
        if not isinstance(b, dict) or len(out) >= LIMITS["balls"]:
            continue
        try:
            bid = str(b["id"])
        except (KeyError, TypeError):
            continue
        if bid in seen:
            continue
        seen.add(bid)
        out.append({"id": bid, "x": _num(b.get("x")), "y": _num(b.get("y")),
                    "area": _num(b.get("area"), 800.0, 30.0, 400000.0),
                    "decor": clean_decor(b.get("decor")), "sid": str(b["sid"]) if b.get("sid") else None})
    return out


def clean_items(lst) -> list:
    out, seen = [], set()
    for it in lst if isinstance(lst, list) else []:
        if not isinstance(it, dict) or len(out) >= LIMITS["items"]:
            continue
        try:
            iid = str(it["id"])
            typ = str(it["type"])
        except (KeyError, TypeError):
            continue
        if iid in seen or typ not in (DYNAMIC, DECORATIVE):
            continue
        seen.add(iid)
        if typ == DYNAMIC:
            balls = [str(b) for b in it.get("balls", []) if isinstance(b, (str, int))][:3]
            if len(balls) >= 2:
                out.append({"id": iid, "type": typ, "balls": balls})
        else:
            out.append({"id": iid, "type": typ, "x": _num(it.get("x")), "y": _num(it.get("y")),
                        "scale": _num(it.get("scale"), 1.0, 0.4, 3.0), "rot": _num(it.get("rot"), 0.0, -60.0, 60.0),
                        "style": str(it.get("style", "classic")), "decor": clean_decor(it.get("decor"))})
    return out


def clean_props(lst) -> list:
    out = []
    for p in lst if isinstance(lst, list) else []:
        if not isinstance(p, dict) or len(out) >= LIMITS["props"]:
            continue
        try:
            kind = str(p["kind"])
            if kind not in KINDS:
                continue
            out.append({"id": str(p.get("id", len(out))), "kind": kind, "style": str(p.get("style", "")),
                        "color": str(p.get("color", "red")), "size": _num(p.get("size"), 100.0, 40.0, 220.0),
                        "x": _num(p.get("x")), "y": _num(p.get("y")), "r": _num(p.get("r"), 20.0, 4.0, 200.0)})
        except (KeyError, TypeError):
            continue
    return out
