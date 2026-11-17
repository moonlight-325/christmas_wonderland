"""기본 크리스마스 음악 생성기.

곡 자체가 퍼블릭 도메인(전통 캐럴)이고, 음원은 이 스크립트가 직접 합성하므로
제3자 저작권 문제가 없다. 결과물: assets/music/*.wav (22.05kHz, 16bit, mono)

사용: python tools/generate_default_music.py
"""
import array
import math
import wave
from pathlib import Path

SR = 22050
NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def freq(name: str) -> float:
    midi = 12 * (int(name[1]) + 1) + NOTES[name[0]]
    return 440.0 * 2 ** ((midi - 69) / 12)


def render(events, bpm, repeat=1):
    beat = 60.0 / bpm
    seq = events * repeat
    total = sum(b for _, b in seq) * beat + 3.0
    buf = [0.0] * int(total * SR)
    t0 = 0.0
    for note, beats in seq:
        dur = beats * beat
        if note:
            for octave_shift, gain in ((1.0, 1.0), (0.5, 0.3)):   # 멜로디 + 한 옥타브 아래
                f = freq(note) * octave_shift
                n = int((dur + 0.9) * SR)
                start = int(t0 * SR)
                for i in range(n):
                    t = i / SR
                    env = min(1.0, t / 0.006) * math.exp(-t * (2.6 if dur > 0.7 else 3.6))
                    if t > dur:                       # 음 길이가 끝나면 빠르게 감쇠
                        env *= math.exp(-(t - dur) * 5.0)
                    s = (math.sin(2 * math.pi * f * t)
                         + 0.35 * math.sin(4 * math.pi * f * t)
                         + 0.12 * math.sin(6 * math.pi * f * t))
                    if start + i < len(buf):
                        buf[start + i] += gain * env * s * 0.3
        t0 += dur
    # 에코(간단한 잔향)
    out = buf[:]
    for delay, g in ((0.28, 0.32), (0.56, 0.16)):
        d = int(delay * SR)
        for i in range(d, len(out)):
            out[i] += buf[i - d] * g
    peak = max(1e-9, max(abs(x) for x in out))
    fade = int(0.8 * SR)
    pcm = array.array("h")
    for i, x in enumerate(out):
        x = x / peak * 0.85
        if i > len(out) - fade:
            x *= (len(out) - i) / fade
        pcm.append(int(x * 32767))
    return pcm


def write_wav(path: Path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def N(spec):
    """'E4:1 G4:.5 R:1' -> [(note|None, beats)]"""
    out = []
    for tok in spec.split():
        name, b = tok.split(":")
        out.append((None if name == "R" else name, float(b)))
    return out


JINGLE = N("""E4:1 E4:1 E4:2  E4:1 E4:1 E4:2  E4:1 G4:1 C4:1.5 D4:.5  E4:4
F4:1 F4:1 F4:1.5 F4:.5  F4:1 E4:1 E4:1 E4:.5 E4:.5  E4:1 D4:1 D4:1 E4:1  D4:2 G4:2""")

SILENT = N("""G4:1.5 A4:.5 G4:1 E4:3  G4:1.5 A4:.5 G4:1 E4:3  D5:2 D5:1 B4:3  C5:2 C5:1 G4:3
A4:2 A4:1 C5:1.5 B4:.5 A4:1  G4:1.5 A4:.5 G4:1 E4:3  A4:2 A4:1 C5:1.5 B4:.5 A4:1  G4:1.5 A4:.5 G4:1 E4:3
D5:2 D5:1 F5:1.5 D5:.5 B4:1  C5:3 E5:3  C5:1 G4:1 E4:1  G4:1.5 F4:.5 D4:1  C4:3""")

WISH = N("""G4:1  C5:1 C5:.5 D5:.5 C5:.5 B4:.5  A4:1 A4:1 A4:1  D5:1 D5:.5 E5:.5 D5:.5 C5:.5
B4:1 G4:1 G4:1  E5:1 E5:.5 F5:.5 E5:.5 D5:.5  C5:1 A4:1 G4:.5 G4:.5  A4:1 D5:1 B4:1  C5:3""")

TRACKS = [
    ("01_jingle_bells.wav", JINGLE, 132, 2),
    ("02_silent_night.wav", SILENT, 66, 1),
    ("03_we_wish_you_a_merry_christmas.wav", WISH, 118, 2),
]

if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent / "assets" / "music"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, ev, bpm, rep in TRACKS:
        pcm = render(ev, bpm, rep)
        write_wav(out_dir / name, pcm)
        print(f"{name}: {len(pcm) / SR:.1f}s")
