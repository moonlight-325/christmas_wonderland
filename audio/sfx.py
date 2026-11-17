"""크리스마스 효과음(환경음) 시스템.

- 눈 내리는 소리 / 바람 / 눈보라 / 벽난로 / 종소리 5종. 기본 음원은 코드로 합성해 data/sfx 에 WAV 로 저장한다(저작권 문제 없음).
- 사운드마다 켜기/끄기, 볼륨, 사용자 음원(파일) 교체를 지원하고, 전체 효과음 음량과 반복/환경음 연동 설정이 있다.
- 음악 플레이어(AudioManager)와는 별도의 QMediaPlayer/QAudioOutput 으로 재생해 서로의 재생 상태를 건드리지 않으며,
  음악이 재생 중이면(설정 시) 효과음을 자동으로 낮춘다.
"""
from __future__ import annotations
from core.i18n import tr


import array
import math
import random
import threading
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

from core.logger import get_logger
from core.paths import data_dir

log = get_logger("sfx")

SOUNDS = [
    ("snow", tr("눈 내리는 소리")),
    ("wind", tr("바람 소리")),
    ("blizzard", tr("눈보라 소리")),
    ("fire", tr("벽난로 타는 소리")),
    ("bell", tr("크리스마스 종소리")),
]
SOUND_KEYS = [k for k, _ in SOUNDS]
RATE = 16000
GEN_VERSION = 1
PREVIEW_SECONDS = 4.0


# ====================================================================== 합성
def _loop(samples: list, n: int, fade: int) -> list:
    """길이 n+fade 의 샘플을 이음매 없는 길이 n 루프로 만든다."""
    out = samples[:n]
    for i in range(fade):
        w = i / fade
        out[i] = samples[i] * w + samples[n + i] * (1.0 - w)
    return out


def _norm(samples: list, peak: float) -> list:
    m = max(1e-9, max(abs(v) for v in samples))
    k = peak / m
    return [v * k for v in samples]


def gen_snow(seconds: float = 8.0) -> list:
    rng = random.Random(11)
    n, fade = int(RATE * seconds), int(RATE * 0.5)
    y1 = y2 = 0.0
    out = []
    mod = 1.0
    rnd = rng.random
    sin = math.sin
    for i in range(n + fade):
        if i % 200 == 0:
            mod = 0.78 + 0.22 * sin(i / RATE * 0.9) * sin(i / RATE * 0.37 + 1.0)
        x = rnd() * 2 - 1
        y1 += 0.20 * (x - y1)
        y2 += 0.12 * (y1 - y2)
        v = (y2 * 2.2 + (x - y1) * 0.05) * mod
        out.append(v)
    return _norm(_loop(out, n, fade), 0.55)


def gen_wind(seconds: float = 10.0, bright: float = 1.0, whistle: bool = False, gusty: float = 1.0) -> list:
    rng = random.Random(23 if not whistle else 37)
    n, fade = int(RATE * seconds), int(RATE * 0.6)
    y1 = y2 = y3 = 0.0
    out = []
    a = 0.05
    amp = 1.0
    rnd = rng.random
    sin = math.sin
    for i in range(n + fade):
        if i % 64 == 0:
            t = i / RATE
            l1 = 0.5 + 0.5 * sin(t * 0.55 * gusty + 0.3)
            l2 = 0.5 + 0.5 * sin(t * 1.3 * gusty + 2.0)
            a = (0.012 + 0.07 * l1 * l2 + 0.012) * bright
            amp = 0.45 + 0.55 * (0.6 * l1 + 0.4 * l2)
        x = rnd() * 2 - 1
        y1 += a * (x - y1)
        y2 += a * (y1 - y2)
        y3 += a * (y2 - y3)
        v = y3 * amp
        if whistle:
            t = i / RATE
            f = 640.0 + 140.0 * sin(t * 0.7) + 60.0 * sin(t * 2.3)
            v += 0.35 * (y1 - y3) * amp + 0.012 * amp * sin(math.tau * f * t)
        out.append(v)
    return _norm(_loop(out, n, fade), 0.6)


def gen_fire(seconds: float = 8.0) -> list:
    rng = random.Random(41)
    n, fade = int(RATE * seconds), int(RATE * 0.5)
    rnd = rng.random
    y = 0.0
    pops: list = []     # [남은 샘플, 진폭, 감쇠]
    out = []
    prev = 0.0
    for i in range(n + fade):
        x = rnd() * 2 - 1
        y += 0.012 * (x - y)                     # 낮게 으르렁거리는 불꽃 소리
        v = y * 5.0
        if rnd() < 14.0 / RATE:                  # 따닥 소리 (초당 평균 14회)
            pops.append([rng.randint(60, 420), rng.uniform(0.2, 1.0), rng.uniform(0.985, 0.997)])
        s = 0.0
        for pop in pops:
            r = rnd() * 2 - 1
            s += (r - prev) * pop[1] * 0.5
            prev = r
            pop[1] *= pop[2]
            pop[0] -= 1
        pops = [p for p in pops if p[0] > 0]
        out.append(v + s)
    return _norm(_loop(out, n, fade), 0.7)


def gen_bell(seconds: float = 7.0) -> list:
    n = int(RATE * seconds)
    out = [0.0] * n
    ratios = (0.5, 1.0, 1.19, 1.5, 2.0, 2.5, 3.0, 4.07)          # 종 특유의 비정수배 배음
    amps = (0.5, 1.0, 0.55, 0.4, 0.35, 0.2, 0.15, 0.08)
    taus = (2.6, 1.9, 1.5, 1.2, 0.9, 0.6, 0.4, 0.25)
    strikes = [(0.0, 523.25), (0.85, 659.25), (1.7, 783.99), (2.55, 659.25), (3.4, 523.25)]
    sin = math.sin
    for t0, f0 in strikes:
        start = int(t0 * RATE)
        for r, a, tau in zip(ratios, amps, taus):
            w = math.tau * f0 * r / RATE
            k = 1.0 / (tau * RATE)
            for i in range(start, n):
                dt = i - start
                e = math.exp(-dt * k)
                if e < 0.002:
                    break
                out[i] += a * e * sin(w * dt)
        for i in range(start, min(n, start + 90)):                 # 타격음
            out[i] += (random.Random(i).random() * 2 - 1) * 0.5 * (1 - (i - start) / 90.0)
    fade = int(RATE * 0.2)
    for i in range(fade):                                          # 끝을 부드럽게
        out[n - 1 - i] *= i / fade
    return _norm(out, 0.8)


GENERATORS = {
    "snow": gen_snow,
    "wind": gen_wind,
    "blizzard": lambda: gen_wind(10.0, bright=2.4, whistle=True, gusty=2.2),
    "fire": gen_fire,
    "bell": gen_bell,
}


def write_wav(path: Path, samples: list) -> None:
    pcm = array.array("h", (max(-32767, min(32767, int(v * 32767))) for v in samples))
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    tmp.replace(path)


def sfx_dir() -> Path:
    d = data_dir() / "sfx"
    d.mkdir(parents=True, exist_ok=True)
    return d


def generated_path(name: str) -> Path:
    return sfx_dir() / f"{name}_v{GEN_VERSION}.wav"


# ====================================================================== 재생
class _Channel:
    def __init__(self, parent):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        self.QMediaPlayer = QMediaPlayer
        self.player = QMediaPlayer(parent)
        self.out = QAudioOutput(parent)
        self.player.setAudioOutput(self.out)
        self.source = ""
        self.vol = 0.0
        self.out.setVolume(0.0)

    def set_source(self, path: str):
        if path != self.source:
            self.source = path
            self.player.setSource(QUrl.fromLocalFile(path))

    def set_loop(self, loop: bool):
        self.player.setLoops(self.QMediaPlayer.Loops.Infinite if loop else 1)

    def set_volume(self, v: float):
        self.vol = v
        self.out.setVolume(max(0.0, min(1.0, v * v)))

    def playing(self) -> bool:
        return self.player.playbackState() == self.QMediaPlayer.PlaybackState.PlayingState

    def play(self):
        self.player.play()

    def restart(self):
        self.player.setPosition(0)
        self.player.play()

    def stop(self):
        self.player.stop()


class SfxManager(QObject):
    ready = Signal()          # 기본 음원 합성 완료

    def __init__(self, settings, audio=None, engine=None, parent=None):
        super().__init__(parent)
        self.s = settings
        self.audio = audio
        self.engine = engine
        self.channels: dict[str, _Channel] = {}
        self._once_done: set = set()
        self._preview: dict[str, float] = {}
        self._gen_lock = threading.Lock()
        self._gen_running = False
        self._clock = 0.0
        self._bell_due = 0.0
        self._bell_armed = False
        self._bell_pending = False
        self._broken = False
        self.ready.connect(self._tick)
        settings.changed.connect(self._on_setting)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)

    # ---- 수명
    def start(self):
        self._timer.start()
        self._tick()

    def shutdown(self):
        self._timer.stop()
        for ch in self.channels.values():
            try:
                ch.stop()
            except Exception:
                pass

    # ---- 음원 경로
    def source_path(self, name: str) -> str:
        custom = self.s.get(f"sfx.{name}_file")
        if custom and Path(custom).is_file():
            return custom
        p = generated_path(name)
        return str(p) if p.is_file() else ""

    def _ensure_generated(self):
        missing = [k for k in SOUND_KEYS if not generated_path(k).is_file()]
        if not missing or self._gen_running:
            return
        self._gen_running = True

        def work():
            try:
                for k in missing:
                    write_wav(generated_path(k), _norm(GENERATORS[k](), 0.85))
            except Exception:
                log.exception("효과음 합성 실패")
            finally:
                self._gen_running = False
                self.ready.emit()

        threading.Thread(target=work, name="sfx-gen", daemon=True).start()

    # ---- 설정
    def _on_setting(self, key: str):
        if key == "*" or key.startswith("sfx.") or key.startswith("weather.") or key == "snow.enabled":
            if key == "*" or key.endswith("_on") or key.endswith("_file") or key.endswith("bell_interval"):
                self._bell_armed = False
                self._once_done.clear() if key == "*" else None
            self._tick()

    def preview(self, name: str):
        """4초간 미리듣기 (켜짐 여부와 날씨 연동을 무시)."""
        if name not in SOUND_KEYS:
            return
        self._preview[name] = self._clock + PREVIEW_SECONDS
        if name == "bell":
            self._bell_pending = True
        self._tick()

    # ---- 음량 계산
    def _factor(self, name: str) -> float:
        s = self.s
        f = 1.0
        if s.get("sfx.duck") and self.audio is not None and getattr(self.audio, "is_playing", False):
            f *= 0.55
        if s.get("sfx.follow_weather") and self.engine is not None:
            sim = self.engine.sim
            if name == "snow":
                f *= 0.0 if not s.get("snow.enabled") else 0.35 + 0.65 * min(1.0, sim.amount / 400.0)
            elif name == "wind":
                eff = getattr(sim, "_eff_wind", float(sim.wind_strength))
                f *= 0.15 + 0.85 * min(1.0, eff / 100.0)
            elif name == "blizzard":
                f *= 0.0 if sim.blizzard <= 0 else 0.3 + 0.7 * sim.blizzard
        return f

    def _channel(self, name: str):
        ch = self.channels.get(name)
        if ch is None and not self._broken:
            try:
                ch = self.channels[name] = _Channel(self)
            except Exception:
                log.exception("효과음 재생기를 만들 수 없습니다")
                self._broken = True
                return None
        return ch

    # ---- 주기 처리
    def _tick(self):
        if self._broken:
            return
        self._clock += 0.25
        s = self.s
        if not bool(s.get("sfx.enabled")):
            for ch in self.channels.values():
                if ch.playing():
                    ch.stop()
            self._preview.clear()
            self._once_done.clear()
            self._bell_armed = False
            self._bell_pending = False
            return
        master = float(s.get("sfx.master"))
        loop = bool(s.get("sfx.loop"))
        any_wanted = False
        for name in SOUND_KEYS:
            previewing = self._preview.get(name, 0.0) > self._clock
            on = bool(s.get(f"sfx.{name}_on"))
            ch = self.channels.get(name)
            if not (on or previewing):
                if ch and ch.playing():
                    ch.stop()
                self._once_done.discard(name)
                continue
            any_wanted = True
            path = self.source_path(name)
            if not path:
                self._ensure_generated()
                continue
            ch = self._channel(name)
            if ch is None:
                return
            ch.set_source(path)
            base = master * float(s.get(f"sfx.{name}_vol"))
            target = base * (1.0 if previewing else self._factor(name)) if name != "bell" else base * self._factor_duck_only()
            ch.set_volume(ch.vol + (target - ch.vol) * 0.4 if abs(target - ch.vol) > 0.01 else target)
            if name == "bell":
                self._bell_tick(ch, on, previewing, loop)
                continue
            ch.set_loop(loop)
            if target <= 0.001 and not previewing:
                if ch.playing():
                    ch.player.pause()
                continue
            if not ch.playing():
                if loop or previewing or name not in self._once_done:
                    ch.play()
                    if not loop and not previewing:
                        self._once_done.add(name)
        if not any_wanted:
            self._bell_armed = False

    def _factor_duck_only(self) -> float:
        if self.s.get("sfx.duck") and self.audio is not None and getattr(self.audio, "is_playing", False):
            return 0.55
        return 1.0

    def _bell_tick(self, ch: _Channel, on: bool, previewing: bool, loop: bool):
        ch.set_loop(False)
        if self._bell_pending:
            self._bell_pending = False
            ch.restart()
        if previewing and not on:
            return
        interval = float(self.s.get("sfx.bell_interval")) * 60.0
        if not self._bell_armed:
            self._bell_armed = True
            self._bell_due = self._clock          # 켜는 즉시 한 번 울림
        if self._clock >= self._bell_due:
            ch.restart()
            self._bell_due = self._clock + interval if loop else float("inf")
