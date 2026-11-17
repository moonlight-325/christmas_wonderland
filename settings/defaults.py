from weather import spec as _aw

SCHEMA_VERSION = 4

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "widget": {
        "x": None,
        "y": None,
        "width": 420,
        "height": 520,
        "mode": "normal",        # normal | bottom
        "locked": False,
        "opacity": 1.0,
        "show_clock": True,
        "show_seconds": True,
        "clock_24h": True,
        "show_date": True,
        "show_dday": True,
        "show_tree": True,       # 크리스마스 트리
        "show_gift": True,       # 선물 상자
        "show_sparkle": True,    # 별·반짝임·작은 눈송이
    },
    "snow": {
        "enabled": True,
        "amount": 220,           # 1920x1080 기준 눈송이 수 (여러 모니터는 면적에 비례)
        "speed": 1.0,
        "size": 1.0,
        "accumulate": 50,        # 눈 축적량 0(끔)~100
        "accumulate_rate": 50,   # 눈 축적 속도 0~100 (50 = 기존과 동일)
        "max_height": 100,       # 눈 쌓이는 최대 높이 25~300 % (100 = 기존 최대 높이)
    },
    "wind": {
        "direction": 90,         # 0=북 90=동 180=남 270=서 (바람이 향하는 방향)
        "strength": 15,          # 0~100 %
    },
    "music": {
        "volume": 0.5,
        "repeat": "all",         # off | one | all
        "folder": "",
        "user_files": [],
        "use_default": True,
        "autoplay": False,
        "last_track": "",
    },
    "weather": {
        "blizzard_on": False,    # 눈보라
        "blizzard": 70,          # 눈보라 강도 0~100
        "gust_on": True,         # 불규칙한 돌풍 자동 발생
        "gust_strength": 70,     # 돌풍 세기 0~100
        "gust_interval": 25,     # 평균 발생 간격(초)
        "temperature": 0,        # 온도 -20~30 (℃). 눈/눈사람 용해 속도를 결정 (눈 효과 탭에서 설정)
        "kind": "custom",        # 수동 날씨 종류 (custom = 직접 설정)
        "cursor_on": True,       # 마우스 커서와 눈의 상호작용
        "cursor_strength": 60,   # 0~100
        "cursor_radius": 120,    # 영향 반경(px)
    },
    "lights": {
        "enabled": False,
        "position": "top",       # top | bottom | left | right | custom
        "monitor": 0,            # 가장자리 배치 모니터 번호
        "anim": "twinkle",       # steady | twinkle | chase | blink
        "palette": "multi",      # multi | classic | warm | ice | candy
        "brightness": 80,        # 20~100 %
        "speed": 100,            # 점멸 속도 20~300 %
        "size": 3,               # 전구 크기(픽셀 배율) 2~6
        "spacing": 5,            # 전구 간격(전구 폭 배수) 3~10
        "wire": True,            # 전선 표시
        "layer": "top",          # top | normal | bottom
        "custom_x": 200,
        "custom_y": 100,
        "custom_length": 600,
        "custom_vertical": False,
        "locked": True,          # 직접 배치 모드에서 이동 잠금
    },
    "decor": {
        "enabled": True,
        "locked": False,         # 이동/크기 조절 잠금
        "layer": "normal",       # top | normal | bottom
        "items": [],             # [{id, kind, x, y, scale, visible}]
    },
    "clock": {
        "enabled": False,
        "theme": "led",          # led | segment | card | analog_classic | analog_wreath | analog_snow
        "scale": 3,              # 1~8
        "color": "gold",         # gold | red | green | white | sky | pink
        "bg": "panel",           # none | panel | night | snow
        "opacity": 100,          # 20~100 %
        "x": 80,
        "y": 80,
        "show_time": True,
        "show_seconds": True,
        "h24": True,
        "show_date": True,
        "show_weekday": True,
        "show_dday": True,
        "layer": "normal",       # top | normal | bottom
        "locked": False,
    },
    "sfx": {
        "enabled": True,           # 전체 효과음 사용
        "master": 0.8,
        "duck": True,            # 음악 재생 중 효과음을 조금 낮춤
        "loop": True,            # 환경음 반복 재생 (끄면 한 번만 재생)
        "follow_weather": True,  # 바람/눈보라/돌풍 상태에 따라 소리 크기 연동
        "bell_interval": 10,     # 종소리 간격(분)
        "snow_on": False, "snow_vol": 0.5, "snow_file": "",
        "wind_on": False, "wind_vol": 0.5, "wind_file": "",
        "blizzard_on": False, "blizzard_vol": 0.5, "blizzard_file": "",
        "fire_on": False, "fire_vol": 0.5, "fire_file": "",
        "bell_on": False, "bell_vol": 0.5, "bell_file": "",
    },
    "physics": {                 # v1.5.0 눈 물리 (모두 0~100)
        "cursor_gain": 50,       # 커서 속도에 따른 힘 증가량
        "flake_react": 60,       # 눈송이 반응 강도
        "pile_react": 60,        # 눈더미 반응 강도
        "inertia": 60,           # 관성
        "friction": 50,          # 마찰력
        "collision": 50,         # 충돌 강도
        "swirl": 50,             # 회전력
        "chain": 50,             # 연쇄 충돌 강도
        "spread": 50,            # 눈의 압축 및 퍼짐 정도
        "win_slip": 50,          # 창 이동 시 눈의 미끄러짐
        "win_fall": 50,          # 창 이동 시 눈이 떨어지는 민감도
        "wrap": True,            # 화면 좌우 끝으로 나간 눈송이가 반대편에서 다시 나옴 (끄면 사라지고 위에서 새로 내림)
    },
    "snowman": {                 # v1.7.0 눈덩이/눈사람 (저장 구조는 snowman/model.py 참고)
        "enabled": True,         # 눈덩이/눈사람 기능 전체 (끄면 숨기고 멈춤, 데이터는 유지)
        "mouse_push": True,      # 마우스를 스치기만 해도 눈덩이를 밀기
        "grab": True,            # 클릭하고 끌어서 잡기/선택
        "growth": 100,           # 눈 흡수(성장) 속도 %
        "push_gain": 100,        # 마우스로 미는 힘 %
        "state": {               # 눈사람 월드 저장 상태: dynamic/decorative 구분, 눈덩이, 남겨진 장식
            "items": [],
            "balls": [],
            "props": [],
        },
    },
    "autoweather": _aw.default_settings_section(),
    "performance": {
        "fps": 30,
        "max_particles": 1500,
        "track_windows": True,   # 창/작업표시줄 위에 눈 쌓기
        "pause_fullscreen": True,
    },
    "app": {
        "show_tray": True,          # 시스템 트레이 아이콘 표시
        "show_taskbar": True,       # 작업표시줄 창 버튼 표시
        "autosave": True,
        "autosave_interval": 30,  # 초
        "last_saved": "",
        "language": "ko",         # ko | en  (바꾸면 다시 시작해야 적용)
    },
}

# dotted key -> (min, max)
RANGES = {
    "widget.width": (260, 4000),
    "widget.height": (300, 4000),
    "widget.opacity": (0.2, 1.0),
    "snow.amount": (0, 1000),
    "snow.speed": (0.2, 3.0),
    "snow.size": (0.5, 2.5),
    "snow.accumulate": (0, 100),
    "snow.accumulate_rate": (0, 100),
    "snow.max_height": (25, 300),
    **{f"physics.{k}": (0, 100) for k in ("cursor_gain", "flake_react", "pile_react", "inertia", "friction",
                                         "collision", "swirl", "chain", "spread", "win_slip", "win_fall")},
    "snowman.growth": (0, 300),
    "snowman.push_gain": (20, 300),
    "wind.direction": (0, 359),
    "wind.strength": (0, 100),
    "music.volume": (0.0, 1.0),
    "weather.blizzard": (0, 100),
    "weather.gust_strength": (0, 100),
    "weather.gust_interval": (5, 180),
    "weather.temperature": (-20, 30),
    "weather.cursor_strength": (0, 100),
    "weather.cursor_radius": (40, 400),
    "lights.monitor": (0, 15),
    "lights.brightness": (20, 100),
    "lights.speed": (20, 300),
    "lights.size": (2, 6),
    "lights.spacing": (3, 10),
    "lights.custom_length": (120, 4000),
    "clock.scale": (1, 8),
    "clock.opacity": (20, 100),
    "sfx.master": (0.0, 1.0),
    "sfx.bell_interval": (1, 60),
    "sfx.snow_vol": (0.0, 1.0), "sfx.wind_vol": (0.0, 1.0), "sfx.blizzard_vol": (0.0, 1.0),
    "sfx.fire_vol": (0.0, 1.0), "sfx.bell_vol": (0.0, 1.0),
    "performance.fps": (10, 60),
    "performance.max_particles": (100, 3000),
    "app.autosave_interval": (5, 600),
}

CHOICES = {
    "app.language": ("ko", "en"),
    "weather.kind": _aw.MANUAL_KIND_CHOICES,
    "widget.mode": ("normal", "bottom"),
    "music.repeat": ("off", "one", "all"),
    "lights.position": ("top", "bottom", "left", "right", "custom"),
    "lights.anim": ("twinkle", "steady", "chase", "blink"),
    "lights.palette": ("multi", "classic", "warm", "ice", "candy"),
    "lights.layer": ("top", "normal", "bottom"),
    "decor.layer": ("normal", "top", "bottom"),
    "clock.theme": ("led", "segment", "card", "analog_classic", "analog_wreath", "analog_snow"),
    "clock.color": ("gold", "red", "green", "white", "sky", "pink"),
    "clock.bg": ("panel", "none", "night", "snow"),
    "clock.layer": ("normal", "top", "bottom"),
}
