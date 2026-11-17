"""스노우볼 카탈로그: 기하 상수와 외형 / 배경 / 장식 정의 (Qt 비의존).

모든 좌표는 '논리 픽셀' (GW x GH 격자) 이다. 화면에는 정수 배(size)로 확대해 그린다.
배치 좌표는 2D (X, Y) 뿐이다. 깊이(Z)는 없고, 앞뒤 겹침은 앵커 Y 순서로 처리한다.
"""
from __future__ import annotations
from core.i18n import tr


# ------------------------------------------------------------------ 기하 (논리 픽셀)
GW, GH = 96, 112                    # 스노우볼 한 개의 캔버스
SCX, SCY = 48.0, 46.0               # 유리 구체 중심
SR = 40.0                           # 유리 구체 반지름
WALL_R = 38.0                       # 눈이 움직일 수 있는 안쪽 반지름
GX, GY = 48.0, 72.0                 # 바닥(눈 쌓이는 원판) 타원 중심
GRX, GRY = 25.0, 11.0               # 바닥 타원 반지름 (아이소메트릭 원판 = 납작한 타원)
BASE_TOP = 80                       # 받침대 시작 Y

SCALE_MIN, SCALE_MAX = 0.5, 2.5     # 장식 크기 범위
GLOBE_SIZE_MIN, GLOBE_SIZE_MAX = 1, 5   # 화면 확대 배율 (96x112 기준)
MAX_DECOR = 40                      # 스노우볼 하나당 장식 최대 개수

# ------------------------------------------------------------------ 외형 (프레임 / 받침 / 유리 형태가 서로 다름)
# base: 받침 모양, rim: 유리와 받침이 만나는 테두리 모양, glass: 유리 색조(rgba), pal: 받침 색상
DESIGNS = {
    "classic": {"name": tr("클래식 유리"), "base": "round", "rim": "ring",
                "glass": (190, 225, 255, 38), "line": "#dff3ff",
                "pal": {"main": "#8a3b2a", "hi": "#b9573c", "lo": "#5a2418", "trim": "#f3c94a"}},
    "pastel": {"name": tr("파스텔"), "base": "soft", "rim": "wave",
               "glass": (255, 214, 240, 46), "line": "#fff0fa",
               "pal": {"main": "#f4b6d2", "hi": "#ffd7e8", "lo": "#d58fb0", "trim": "#ffffff"}},
    "cabin": {"name": tr("겨울 오두막"), "base": "log", "rim": "plank",
              "glass": (200, 235, 255, 34), "line": "#e9f6ff",
              "pal": {"main": "#7a5233", "hi": "#a0724a", "lo": "#4d3220", "trim": "#d9c7a0"}},
    "pixel": {"name": tr("픽셀아트"), "base": "block", "rim": "stud",
              "glass": (170, 255, 235, 44), "line": "#e6fff8",
              "pal": {"main": "#3a4a7a", "hi": "#5a72b8", "lo": "#222c4d", "trim": "#8fd0f5"}},
    "frame": {"name": tr("장식 프레임"), "base": "gold", "rim": "arch",
              "glass": (255, 240, 200, 36), "line": "#fff7da",
              "pal": {"main": "#c99a2e", "hi": "#f3d36b", "lo": "#8a661a", "trim": "#d63a3a"}},
}
DESIGN_IDS = list(DESIGNS)
DEFAULT_DESIGN = "classic"

# ------------------------------------------------------------------ 내부 배경 (sky: 위 -> 아래 색, ground: 바닥 눈 색)
BACKGROUNDS = {
    "village": {"name": tr("겨울 마을"), "sky": ("#16294f", "#4a6aa5"), "ground": ("#eef6ff", "#c4d8ee")},
    "forest": {"name": tr("눈 덮인 숲"), "sky": ("#10303a", "#3f7a82"), "ground": ("#f0f8ff", "#bcd6e6")},
    "plaza": {"name": tr("겨울 광장"), "sky": ("#2a1f4f", "#8a6aa8"), "ground": ("#f6f2fa", "#d2c4e2")},
    "mountain": {"name": tr("눈 덮인 산과 언덕"), "sky": ("#1a3a6a", "#9ccbe8"), "ground": ("#ffffff", "#cfe3f3")},
    "cabin": {"name": tr("작은 오두막"), "sky": ("#0f2236", "#365a7a"), "ground": ("#eaf3fb", "#b8cfe2")},
    "xmas_town": {"name": tr("크리스마스 마을"), "sky": ("#2a0f2e", "#b0505a"), "ground": ("#fff4f0", "#e8c8c8")},
}
BACKGROUND_IDS = list(BACKGROUNDS)
DEFAULT_BACKGROUND = "village"

# ------------------------------------------------------------------ 눈 종류
SNOW_KINDS = ("normal", "big", "sparkle")
SNOW_NAMES = {"normal": tr("일반 눈"), "big": tr("큰 눈송이"), "sparkle": tr("반짝이 입자")}

SHAKE_MODES = {"both": tr("직접 + 클릭"), "drag": tr("직접 흔들기만"), "click": tr("클릭 흔들기만")}
AUTO_SHAKE_DEFAULT_SEC = 30          # 자동 흔들기(옵션): 일정 시간마다 저절로 흔들림
AUTO_SHAKE_RANGE = (10, 120)         # 간격(초). 스노우볼마다 시작 시점이 달라 한꺼번에 흔들리지 않음

# ------------------------------------------------------------------ 장식 오브젝트
# w, h: scale 1 에서의 논리 픽셀 크기 (앵커 = 아래 가운데). depth: 눈이 이 장식과 부딪히는 앞뒤 허용 폭.
# profile: 윗면 윤곽 [(u, v)]  u = -1..1 (좌우), v = 0..1 (높이 비율). 계단 모양이면 눈이 턱에 쌓인다.
_BOX = [(-1, 1), (1, 1)]
DECOR = {
    "small_tree": {"name": tr("작은 나무"), "w": 12, "h": 18, "depth": 4,
                   "profile": [(-1, .3), (-.6, .3), (-.6, .62), (-.3, .62), (-.3, .88), (0, 1), (.3, .88),
                               (.3, .62), (.6, .62), (.6, .3), (1, .3)]},
    "xmas_tree": {"name": tr("크리스마스트리"), "w": 16, "h": 28, "depth": 5,
                  "profile": [(-1, .24), (-.7, .24), (-.7, .5), (-.45, .5), (-.45, .72), (-.22, .72), (-.22, .92),
                              (0, 1), (.22, .92), (.22, .72), (.45, .72), (.45, .5), (.7, .5), (.7, .24), (1, .24)]},
    "snowman": {"name": tr("눈사람"), "w": 12, "h": 18, "depth": 3,
                "profile": [(-1, .1), (-.75, .45), (-.5, .55), (-.55, .85), (-.3, .98), (0, 1), (.3, .98),
                            (.55, .85), (.5, .55), (.75, .45), (1, .1)]},
    "lamp": {"name": tr("가로등"), "w": 8, "h": 26, "depth": 2, "profile": _BOX},
    "gift": {"name": tr("선물 상자"), "w": 10, "h": 9, "depth": 3, "profile": _BOX},
    "bench": {"name": tr("벤치"), "w": 18, "h": 10, "depth": 3, "profile": [(-1, .5), (-.85, .5), (-.85, 1), (.85, 1), (.85, .5), (1, .5)]},
    "fence": {"name": tr("울타리"), "w": 20, "h": 9, "depth": 2, "profile": [(-1, .8), (1, .8)]},
    "house": {"name": tr("집"), "w": 26, "h": 24, "depth": 7, "profile": [(-1, .5), (0, 1), (1, .5)]},
    "rock": {"name": tr("눈 덮인 바위"), "w": 14, "h": 9, "depth": 4,
             "profile": [(-1, 0), (-.6, .7), (0, 1), (.6, .7), (1, 0)]},
    "ornament": {"name": tr("크리스마스 장식"), "w": 9, "h": 11, "depth": 3,
                 "profile": [(-1, .2), (-.6, .7), (0, 1), (.6, .7), (1, .2)]},
}
DECOR_IDS = list(DECOR)


def roof_v(profile, u: float) -> float:
    """윤곽선에서 u(-1..1) 위치의 높이 비율 v(0..1). 계단 모서리에서는 높은 쪽을 쓴다."""
    u = -1.0 if u < -1.0 else 1.0 if u > 1.0 else u
    best = 0.0
    for (u0, v0), (u1, v1) in zip(profile, profile[1:]):
        if u1 <= u0:
            continue
        if u0 <= u <= u1:
            v = v0 + (v1 - v0) * (u - u0) / (u1 - u0)
            if v > best:
                best = v
    return best
