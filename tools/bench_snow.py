"""눈 시뮬레이션 성능 측정 (PySide6 불필요). 사용: python tools/bench_snow.py [--profile 시나리오이름]

시나리오마다 SnowSim.step() 한 번의 처리 시간(ms)을 재고, 눈더미를 그릴 때 필요한 그리기 호출 수(Qt 없이 추정)와
질량 보존 오차를 함께 출력한다. 실제 화면 그리기 시간은 Qt 가 있어야 측정되므로 호출 수로 대신 비교한다.
"""
from __future__ import annotations

import cProfile
import pstats
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import Rect, SnowSim, SurfaceInfo

DT = 1 / 30


def make(windows=12, amount=220, temp=-15.0, seed=3, fill_h=0.0, wind=15):
    sim = SnowSim(seed=seed)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    sim.configure(amount=amount, accumulate=80, temperature=temp, wind_strength=wind,
                  cursor_on=False, cursor_strength=1.0, cursor_radius=120.0)
    surfs = []
    for k in range(windows):
        l, t = 60 + (k % 6) * 300, 80 + (k // 6) * 420
        surfs.append(SurfaceInfo(f"w{k}", l, t, l + 280, [(l, l + 280)], [(l, l + 280)]))
    sim.set_surfaces(surfs)
    if fill_h:
        for p in sim.piles.values():
            for i in range(len(p.cells)):
                p.cells[i] = fill_h
                sim.mass_added += fill_h
    return sim


def paint_calls(sim) -> int:
    """_paint_piles 가 호출하는 fillRect 수 (같은 높이의 연속 열은 한 번에 묶는 v1.5.0 방식과 동일하게 센다)."""
    n = 0
    for pile in sim.piles.values():
        cells = pile.cells
        i = 0
        L = len(cells)
        while i < L:
            h = int(cells[i] + 0.5)
            j = i + 1
            while j < L and int(cells[j] + 0.5) == h:
                j += 1
            if h > 0:
                n += 3 if h > 1 else 2
            i = j
    return n


SCENARIOS = {
    "눈이 내리며 쌓이는 중": dict(kw=dict(temp=-15.0), secs=20, prefill=0.0),
    "눈이 많이 쌓인 상태(정지)": dict(kw=dict(temp=-15.0, amount=0), secs=10, prefill=14.0),
    "눈이 녹는 중(8도)": dict(kw=dict(temp=8.0, amount=0), secs=20, prefill=14.0),
    "눈이 녹는 중 + 눈 내림(2도)": dict(kw=dict(temp=2.0, amount=220), secs=20, prefill=8.0),
    "눈이 움직이는 중(강풍)": dict(kw=dict(temp=-15.0, amount=300, wind=80), secs=15, prefill=6.0),
}


def run(name, cfg, profile=False):
    sim = make(**cfg["kw"], fill_h=cfg["prefill"])
    for _ in range(int(2 / DT)):                 # 준비 운동
        sim.step(DT)
    times = []
    prof = cProfile.Profile() if profile else None
    for _ in range(int(cfg["secs"] / DT)):                 # 시간 측정 구간: tracemalloc 을 켜면 몇 배로 느려져 따로 잰다
        t0 = time.perf_counter()
        if prof:
            prof.enable()
        sim.step(DT)
        if prof:
            prof.disable()
        times.append((time.perf_counter() - t0) * 1000.0)
    tracemalloc.start()                                      # 메모리 측정 구간 (시간 수치에는 반영하지 않음)
    for _ in range(int(5 / DT)):
        sim.step(DT)
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cols = sum(len(p.cells) for p in sim.piles.values())
    times.sort()
    print(f"[{name}] 열 {cols}개 / 눈송이 {len(sim.flakes)}개")
    print(f"   step 평균 {statistics.mean(times):6.2f} ms | p95 {times[int(len(times) * .95)]:6.2f} ms | 최대 {times[-1]:6.2f} ms"
          f" | 가능 FPS {1000.0 / max(1e-9, statistics.mean(times)):7.0f} | 그리기 호출 {paint_calls(sim):5d}"
          f" | 메모리 증가 {peak / 1024:7.0f} KB | 질량오차 {sim.mass_balance():+.2e}")
    if prof:
        pstats.Stats(prof).sort_stats("cumulative").print_stats(14)


if __name__ == "__main__":
    only = None
    if "--profile" in sys.argv:
        i = sys.argv.index("--profile")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    for nm, cfg in SCENARIOS.items():
        if only and only not in nm:
            continue
        run(nm, cfg, profile=bool(only))
