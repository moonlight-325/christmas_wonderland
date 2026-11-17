"""자동 날씨 명세 (Qt 와 settings 모듈에 의존하지 않는 순수 데이터 + 검증).

- VARS: 자동 조정 대상 변수 (설정 키, 허용 한계, 기본 범위, 표시 단위)
- KINDS: 날씨 종류와 종류별 변수 성향(범위 안에서 어느 쪽 값이 뽑힐지)
- default_config / clean_config / validate_ranges: 저장 데이터 형식과 검증
- PRESETS: 기본 제공 프리셋 5종
"""
from __future__ import annotations
from core.i18n import tr


import copy

KIND_VAR = "kind"
DURATION_VAR = "duration"

# id, 설정 키, 한계(lo, hi), 기본 범위, 정수 여부, 표시 배율(저장값 x 배율 = 표시값), 단위, 표시 소수 자리, 이름
# 설정 키 None: 설정 파일의 수동 값이 아니라 자동 날씨 내부 값(날씨 종류/지속시간)
_NUMERIC = [
    # id,              key,                       lo,    hi,    dmin,  dmax,  int,   scale, suffix,  dec, label
    ("snow_amount",    "snow.amount",             0,     1000,  0,     600,   True,  1,     tr(" 개"),    0, tr("강설량")),
    ("snow_size",      "snow.size",               0.5,   2.5,   0.7,   1.6,   False, 100,   "%",      0, tr("눈송이 크기")),
    ("snow_speed",     "snow.speed",              0.2,   3.0,   0.5,   1.8,   False, 100,   "%",      0, tr("낙하 속도")),
    ("snow_accumulate", "snow.accumulate",        0,     100,   10,    90,    True,  1,     "%",      0, tr("눈 축적량")),
    ("snow_accum_rate", "snow.accumulate_rate",   0,     100,   10,    90,    True,  1,     "%",      0, tr("눈 축적 속도")),
    ("temperature",    "weather.temperature",     -20,   30,    -12,   4,     True,  1,     " ℃",     0, tr("온도")),
    ("wind_direction", "wind.direction",          0,     359,   0,     359,   True,  1,     tr(" 도"),    0, tr("바람 방향")),
    ("wind_strength",  "wind.strength",           0,     100,   0,     60,    True,  1,     "%",      0, tr("바람 세기")),
    ("gust_strength",  "weather.gust_strength",   0,     100,   20,    90,    True,  1,     "%",      0, tr("돌풍 강도")),
    ("gust_interval",  "weather.gust_interval",   5,     180,   15,    90,    True,  1,     tr(" 초"),    0, tr("돌풍 발생 간격 (짧을수록 잦음)")),
    (DURATION_VAR,     None,                      10,    3600,  60,    300,   True,  1,     tr(" 초"),    0, tr("날씨 지속시간")),
]

NUMERIC_VARS = [dict(zip(("id", "key", "lo", "hi", "dmin", "dmax", "int", "scale", "suffix", "dec", "label"), row))
                for row in _NUMERIC]
VARS_BY_ID = {v["id"]: v for v in NUMERIC_VARS}
KEY_TO_VAR = {v["key"]: v["id"] for v in NUMERIC_VARS if v["key"]}
# 수동 값이 설정 파일에 있는 변수 (자동 조정 중에는 설정값 대신 자동 적용값이 쓰인다)
SETTING_VARS = [v["id"] for v in NUMERIC_VARS if v["key"]]
# 전체 변수 표시 순서: 날씨 종류, 지속시간, 눈 효과, 바람
ALL_VAR_IDS = [KIND_VAR, DURATION_VAR] + SETTING_VARS
GROUPS = [
    (tr("날씨"), [KIND_VAR, DURATION_VAR]),
    (tr("눈 효과"), ["snow_amount", "snow_size", "snow_speed", "snow_accumulate", "snow_accum_rate", "temperature"]),
    (tr("바람"), ["wind_direction", "wind_strength", "gust_strength", "gust_interval"]),
]
KIND_LABEL = tr("날씨 종류")

# ---------------------------------------------------------------------------- 날씨 종류
KINDS = [
    ("clear", tr("맑음")), ("cloudy", tr("흐림")), ("light", tr("약한 눈")),
    ("snow", tr("눈")), ("heavy", tr("폭설")), ("blizzard", tr("눈보라")),
]
KIND_IDS = [k for k, _ in KINDS]
KIND_NAME = dict(KINDS)
MANUAL_KIND_CHOICES = ("custom",) + tuple(KIND_IDS)      # weather.kind 허용값 (custom = 직접 설정)

# 종류별 변수 성향: 변수 -> (중심, 폭).  중심/폭은 사용자 범위 [min, max] 를 0~1 로 본 비율.
# 예: 맑음 강설량 (0.0, 0.06) = 범위의 맨 아래 근처가 뽑힐 가능성이 매우 높다.
_ANY = (0.5, 0.6)
PROFILES = {
    "clear": {
        "snow_amount": (0.0, 0.06), "snow_size": (0.5, 0.3), "snow_speed": (0.5, 0.3),
        "snow_accumulate": (0.3, 0.3), "snow_accum_rate": (0.15, 0.15), "temperature": (0.6, 0.25),
        "wind_direction": _ANY, "wind_strength": (0.15, 0.15), "gust_strength": (0.15, 0.15),
        "gust_interval": (0.85, 0.15),
    },
    "cloudy": {
        "snow_amount": (0.06, 0.08), "snow_size": (0.45, 0.3), "snow_speed": (0.4, 0.3),
        "snow_accumulate": (0.35, 0.25), "snow_accum_rate": (0.2, 0.15), "temperature": (0.5, 0.25),
        "wind_direction": _ANY, "wind_strength": (0.25, 0.18), "gust_strength": (0.25, 0.18),
        "gust_interval": (0.75, 0.2),
    },
    "light": {
        "snow_amount": (0.25, 0.15), "snow_size": (0.35, 0.25), "snow_speed": (0.35, 0.2),
        "snow_accumulate": (0.4, 0.25), "snow_accum_rate": (0.3, 0.2), "temperature": (0.55, 0.25),
        "wind_direction": _ANY, "wind_strength": (0.25, 0.15), "gust_strength": (0.25, 0.15),
        "gust_interval": (0.7, 0.2),
    },
    "snow": {
        "snow_amount": (0.5, 0.18), "snow_size": (0.5, 0.25), "snow_speed": (0.5, 0.2),
        "snow_accumulate": (0.5, 0.25), "snow_accum_rate": (0.5, 0.2), "temperature": (0.45, 0.25),
        "wind_direction": _ANY, "wind_strength": (0.35, 0.2), "gust_strength": (0.35, 0.2),
        "gust_interval": (0.6, 0.25),
    },
    "heavy": {
        "snow_amount": (0.88, 0.1), "snow_size": (0.65, 0.2), "snow_speed": (0.65, 0.2),
        "snow_accumulate": (0.75, 0.2), "snow_accum_rate": (0.85, 0.12), "temperature": (0.3, 0.2),
        "wind_direction": _ANY, "wind_strength": (0.5, 0.2), "gust_strength": (0.5, 0.2),
        "gust_interval": (0.5, 0.2),
    },
    "blizzard": {
        "snow_amount": (0.92, 0.08), "snow_size": (0.6, 0.25), "snow_speed": (0.85, 0.12),
        "snow_accumulate": (0.75, 0.2), "snow_accum_rate": (0.8, 0.15), "temperature": (0.1, 0.12),
        "wind_direction": _ANY, "wind_strength": (0.9, 0.1), "gust_strength": (0.88, 0.1),
        "gust_interval": (0.12, 0.1),
    },
}
NEUTRAL_PROFILE = (0.5, 1.0)      # 종류가 '직접'(custom)일 때: 범위 전체에서 고르게

# 수동 날씨 종류 버튼(자동 날씨가 꺼져 있을 때): 눌렀을 때 수동 설정에 한 번 적용되는 대표값
MANUAL_APPLY = {
    "clear":    {"snow.amount": 0,   "snow.speed": 1.0, "snow.accumulate_rate": 20, "wind.strength": 5,
                 "weather.temperature": 2, "weather.blizzard_on": False},
    "cloudy":   {"snow.amount": 40,  "snow.speed": 0.8, "snow.accumulate_rate": 25, "wind.strength": 10,
                 "weather.temperature": 0, "weather.blizzard_on": False},
    "light":    {"snow.amount": 120, "snow.speed": 0.8, "snow.accumulate_rate": 35, "wind.strength": 12,
                 "weather.temperature": -2, "weather.blizzard_on": False},
    "snow":     {"snow.amount": 260, "snow.speed": 1.0, "snow.accumulate_rate": 50, "wind.strength": 20,
                 "weather.temperature": -3, "weather.blizzard_on": False},
    "heavy":    {"snow.amount": 620, "snow.speed": 1.3, "snow.accumulate_rate": 85, "wind.strength": 45,
                 "weather.temperature": -6, "weather.blizzard_on": False},
    "blizzard": {"snow.amount": 800, "snow.speed": 2.0, "snow.accumulate_rate": 80, "wind.strength": 85,
                 "weather.temperature": -12, "weather.blizzard_on": True, "weather.blizzard": 80},
}

# ---------------------------------------------------------------------------- 설정 데이터
PARAMS = {                      # 변화 설정 (0~100)
    "change_speed": (tr("변수 변화 속도"), 50),
    "change_freq": (tr("날씨 변화 빈도"), 50),
    "randomness": (tr("랜덤성"), 50),
    "link": (tr("날씨 연동 강도"), 70),
}
DEFAULT_WEIGHTS = {"clear": 15, "cloudy": 20, "light": 25, "snow": 20, "heavy": 12, "blizzard": 8}


def default_var(vid: str) -> dict:
    if vid == KIND_VAR:
        return {"auto": True}
    v = VARS_BY_ID[vid]
    d = {"auto": True, "min": v["dmin"], "max": v["dmax"]}
    if vid == DURATION_VAR:
        d["manual"] = 120
    return d


def default_config() -> dict:
    """저장되는 자동 날씨 설정(실행 상태 제외). 프리셋은 이 구조를 통째로 담는다."""
    cfg = {
        "kinds": {k: {"on": True, "weight": DEFAULT_WEIGHTS[k]} for k in KIND_IDS},
        "vars": {vid: default_var(vid) for vid in ALL_VAR_IDS},
    }
    for name, (_label, dv) in PARAMS.items():
        cfg[name] = dv
    return cfg


def default_settings_section() -> dict:
    """settings.json 의 autoweather 구역 기본값."""
    sec = default_config()
    sec["enabled"] = False       # 자동 날씨 시작됨
    sec["paused"] = False        # 일시정지 중
    sec["preset"] = ""           # 마지막으로 불러온 프리셋 이름
    return sec


# ---------------------------------------------------------------------------- 검증
def _num(x, default):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or x in (float("inf"), float("-inf")):
        return default
    return x


def clamp_var_value(vid: str, x):
    v = VARS_BY_ID[vid]
    x = max(v["lo"], min(v["hi"], x))
    return int(round(x)) if v["int"] else float(x)


def validate_range(vid: str, lo, hi) -> str | None:
    """오류 메시지 (문제 없으면 None). 한계 밖이거나 최솟값 > 최댓값이면 거부 사유를 돌려준다."""
    v = VARS_BY_ID[vid]
    name = v["label"].split(" (")[0]
    sc = v["scale"]
    lim = f"{_fmt(v['lo'] * sc)}~{_fmt(v['hi'] * sc)}{v['suffix'].strip() and v['suffix']}"
    for x in (lo, hi):
        if _num(x, None) is None:
            return tr("{0}: 숫자만 입력할 수 있어요.").format(name)
        if x < v["lo"] - 1e-9 or x > v["hi"] + 1e-9:
            return tr("{0}: 허용 범위({1})를 벗어났어요.").format(name, lim)
    if lo > hi:
        return tr("{0}: 최솟값이 최댓값보다 높아요. 최솟값을 최댓값 이하로 맞춰 주세요.").format(name)
    return None


def _fmt(x: float) -> str:
    return f"{x:g}"


def validate_ranges(cfg: dict) -> list:
    """설정 전체의 범위 오류 목록 [(변수 id, 메시지)]."""
    out = []
    for vid in SETTING_VARS + [DURATION_VAR]:
        d = cfg["vars"][vid]
        msg = validate_range(vid, d["min"], d["max"])
        if msg:
            out.append((vid, msg))
    return out


def enabled_kinds(cfg: dict) -> list:
    return [k for k in KIND_IDS if cfg["kinds"][k]["on"]]


def clean_config(raw, base: dict | None = None) -> dict:
    """저장 파일/프리셋에서 읽은 데이터를 안전한 설정으로 정리한다. 손상된 항목은 기본값으로 되돌린다."""
    base = base or default_config()
    out = copy.deepcopy(base)
    raw = raw if isinstance(raw, dict) else {}
    kinds = raw.get("kinds") if isinstance(raw.get("kinds"), dict) else {}
    for k in KIND_IDS:
        src = kinds.get(k) if isinstance(kinds.get(k), dict) else {}
        on = src.get("on", out["kinds"][k]["on"])
        out["kinds"][k]["on"] = on if isinstance(on, bool) else out["kinds"][k]["on"]
        w = _num(src.get("weight"), out["kinds"][k]["weight"])
        out["kinds"][k]["weight"] = int(max(0, min(100, round(w))))
    vars_raw = raw.get("vars") if isinstance(raw.get("vars"), dict) else {}
    for vid in ALL_VAR_IDS:
        src = vars_raw.get(vid) if isinstance(vars_raw.get(vid), dict) else {}
        dst = out["vars"][vid]
        a = src.get("auto", dst["auto"])
        dst["auto"] = a if isinstance(a, bool) else dst["auto"]
        if vid == KIND_VAR:
            continue
        v = VARS_BY_ID[vid]
        lo, hi = _num(src.get("min"), dst["min"]), _num(src.get("max"), dst["max"])
        if validate_range(vid, lo, hi):                 # 한계 밖 / 최솟값 > 최댓값이면 그 변수 범위만 기본값
            lo, hi = v["dmin"], v["dmax"]
        dst["min"], dst["max"] = clamp_var_value(vid, lo), clamp_var_value(vid, hi)
        if vid == DURATION_VAR:
            dst["manual"] = clamp_var_value(vid, _num(src.get("manual"), dst["manual"]))
    for name, (_label, dv) in PARAMS.items():
        out[name] = int(max(0, min(100, round(_num(raw.get(name), dv)))))
    return out


def clean_section(raw, base: dict | None = None) -> dict:
    """settings.json 의 autoweather 구역 전체 정리."""
    raw = raw if isinstance(raw, dict) else {}
    out = clean_config(raw, base)
    out["enabled"] = raw.get("enabled") if isinstance(raw.get("enabled"), bool) else False
    out["paused"] = raw.get("paused") if isinstance(raw.get("paused"), bool) else False
    out["preset"] = raw.get("preset") if isinstance(raw.get("preset"), str) else ""
    if out["enabled"] and not enabled_kinds(out):      # 시작할 수 없는 상태로 저장되어 있으면 꺼 둔다
        out["enabled"] = False
        out["paused"] = False
    return out


def config_of(section: dict) -> dict:
    """settings 구역에서 프리셋에 들어갈 설정만 복사."""
    cfg = {k: copy.deepcopy(section[k]) for k in ("kinds", "vars") if k in section}
    for name in PARAMS:
        cfg[name] = section[name]
    return cfg


# ---------------------------------------------------------------------------- 기본 제공 프리셋
def _preset(kinds: dict, ranges: dict, speed: int, freq: int, rnd: int, link: int, auto_off=()) -> dict:
    cfg = default_config()
    for k in KIND_IDS:
        w = kinds.get(k, 0)
        cfg["kinds"][k] = {"on": w > 0, "weight": w if w > 0 else cfg["kinds"][k]["weight"]}
    for vid, (lo, hi) in ranges.items():
        cfg["vars"][vid]["min"], cfg["vars"][vid]["max"] = lo, hi
    for vid in auto_off:
        cfg["vars"][vid]["auto"] = False
    cfg["change_speed"], cfg["change_freq"], cfg["randomness"], cfg["link"] = speed, freq, rnd, link
    return cfg


PRESETS = {
    "잔잔한 겨울": _preset(
        {"clear": 15, "cloudy": 30, "light": 40, "snow": 15},
        {"snow_amount": (20, 260), "snow_size": (0.7, 1.3), "snow_speed": (0.5, 1.0), "snow_accumulate": (30, 70),
         "snow_accum_rate": (15, 50), "temperature": (-8, 0), "wind_direction": (0, 359), "wind_strength": (0, 25),
         "gust_strength": (10, 40), "gust_interval": (40, 120), DURATION_VAR: (120, 420)},
        speed=25, freq=35, rnd=30, link=70),
    "포근한 눈 내리는 날": _preset(
        {"cloudy": 15, "light": 40, "snow": 45},
        {"snow_amount": (80, 350), "snow_size": (1.0, 1.8), "snow_speed": (0.4, 0.9), "snow_accumulate": (30, 70),
         "snow_accum_rate": (25, 60), "temperature": (-2, 4), "wind_direction": (0, 359), "wind_strength": (0, 20),
         "gust_strength": (0, 30), "gust_interval": (60, 150), DURATION_VAR: (120, 360)},
        speed=30, freq=40, rnd=35, link=75),
    "폭설": _preset(
        {"snow": 25, "heavy": 65, "blizzard": 10},
        {"snow_amount": (500, 1000), "snow_size": (0.9, 1.8), "snow_speed": (0.8, 1.6), "snow_accumulate": (60, 100),
         "snow_accum_rate": (70, 100), "temperature": (-12, -2), "wind_direction": (0, 359), "wind_strength": (10, 50),
         "gust_strength": (20, 60), "gust_interval": (25, 90), DURATION_VAR: (90, 300)},
        speed=45, freq=50, rnd=40, link=80),
    "강한 눈보라": _preset(
        {"heavy": 25, "blizzard": 75},
        {"snow_amount": (600, 1000), "snow_size": (0.8, 1.6), "snow_speed": (1.4, 2.6), "snow_accumulate": (60, 100),
         "snow_accum_rate": (60, 100), "temperature": (-20, -8), "wind_direction": (0, 359), "wind_strength": (65, 100),
         "gust_strength": (60, 100), "gust_interval": (5, 30), DURATION_VAR: (60, 240)},
        speed=60, freq=60, rnd=45, link=85),
    "변화무쌍한 겨울": _preset(
        {"clear": 12, "cloudy": 15, "light": 20, "snow": 22, "heavy": 18, "blizzard": 13},
        {"snow_amount": (0, 900), "snow_size": (0.6, 2.0), "snow_speed": (0.4, 2.2), "snow_accumulate": (10, 100),
         "snow_accum_rate": (10, 100), "temperature": (-16, 6), "wind_direction": (0, 359), "wind_strength": (0, 90),
         "gust_strength": (10, 100), "gust_interval": (10, 90), DURATION_VAR: (30, 120)},
        speed=70, freq=75, rnd=85, link=55),
}
PRESET_NAMES = list(PRESETS)


def status_summary(st: dict) -> str:
    """트레이 툴팁용 한 줄 요약. 자동 날씨가 꺼져 있으면 빈 문자열. 남은 시간은 분 단위 올림이라 자주 바뀌지 않는다."""
    if st.get("active") and st.get("paused"):
        return tr("자동 날씨: 일시정지")
    if st.get("active"):
        name = KIND_NAME.get(st.get("kind"), "직접 설정")
        rem = max(0.0, float(st.get("remaining", 0.0) or 0.0))
        left = tr("1분 미만 남음") if rem < 60 else tr("약 {0}분 남음").format(int(-(-rem // 60)))
        return tr("자동 날씨: {0} ({1})").format(name, left)
    if st.get("phase") == "release":
        return tr("자동 날씨: 수동 설정으로 돌아가는 중")
    return ""
