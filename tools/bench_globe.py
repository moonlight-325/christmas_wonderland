"""스노우볼 내부 눈 물리 성능 측정 (PySide6 불필요). 사용: python tools/bench_globe.py [--p]

12개 스노우볼을 동시에 흔든 직후(눈이 가장 많이 움직이는 때)의 step() 시간(ms)을 잰다. --p 는 프로파일 출력.
"""
from __future__ import annotations

import cProfile
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import snowglobe.model as M
from snowglobe.physics import GlobePhysics


def run(label, amount, n=12, shake_s=1.5, secs=8, prof=False):
    snow = dict(M.DEFAULT_SNOW)
    snow["amount"] = amount
    globes = [GlobePhysics(snow, []) for _ in range(n)]
    dt = 1 / 30
    times = []
    pr = cProfile.Profile() if prof else None
    for i in range(int((shake_s + secs) / dt)):
        ax = (900 * (1 if int(i * dt * 6) % 2 else -1)) if i * dt < shake_s else 0
        t0 = time.perf_counter()
        if pr:
            pr.enable()
        for g in globes:
            g.step(dt, ax, 0)
        if pr:
            pr.disable()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    print(f"{label}: 스노우볼 {n}개 / 개당 눈송이 {len(globes[0].flakes)}개 | 평균 {statistics.mean(times):.2f} ms"
          f" | p95 {times[int(len(times) * .95)]:.2f} ms | 최대 {times[-1]:.2f} ms")
    if pr:
        pstats.Stats(pr).sort_stats("tottime").print_stats(7)


if __name__ == "__main__":
    for amt in (200, 600):
        run(f"흔든 뒤 눈 {amt}", amt, prof="--p" in sys.argv)
