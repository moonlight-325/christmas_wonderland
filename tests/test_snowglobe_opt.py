"""스노우볼 물리 최적화 검증 (PySide6 불필요).

_collide 는 최적화 전 구현(아래 reference_collide)과 결과가 비트 단위로 같아야 한다.
이 함수는 사칙연산과 sqrt 만 쓰므로 플랫폼이 달라도 결과가 같다.
"""
import copy
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import snowglobe.model as M  # noqa: E402
from snowglobe import catalog as C  # noqa: E402
from snowglobe import physics as P  # noqa: E402


def reference_collide(self, flakes):
    """최적화 전의 원래 구현 (그대로 보존)."""
    cell = 5.0
    grid = {}
    for f in flakes:
        grid.setdefault((int(f.x // cell), int(f.y // cell)), []).append(f)
    sz = self.size
    for (cx, cy), lst in grid.items():
        for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (1, -1)):
            other = grid.get((cx + ox, cy + oy))
            if other is None:
                continue
            for i, a in enumerate(lst):
                for j, b in enumerate(other):
                    if (ox, oy) == (0, 0) and j <= i:
                        continue
                    ra = P.PARAMS[a.kind][5] * (sz if a.kind != 2 else 1.0)
                    rb = P.PARAMS[b.kind][5] * (sz if b.kind != 2 else 1.0)
                    dx, dy = b.x - a.x, b.y - a.y
                    rr = ra + rb
                    d2 = dx * dx + dy * dy
                    if d2 >= rr * rr or d2 < 1e-6:
                        continue
                    d = math.sqrt(d2)
                    nx, ny = dx / d, dy / d
                    push = (rr - d) * 0.5
                    a.x -= nx * push
                    a.y -= ny * push
                    b.x += nx * push
                    b.y += ny * push
                    rv = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                    if rv < 0:
                        imp = -rv * 0.45
                        a.vx -= nx * imp
                        a.vy -= ny * imp
                        b.vx += nx * imp
                        b.vy += ny * imp


def make_flakes(n, seed, spread):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        f = P.Flake(rnd.choice((0, 0, 1, 2)))
        f.x, f.y = C.SCX + rnd.uniform(-spread, spread), C.SCY + rnd.uniform(-spread, spread)
        f.vx, f.vy = rnd.uniform(-30, 30), rnd.uniform(-30, 30)
        out.append(f)
    return out


def snap(flakes):
    return [(f.x, f.y, f.vx, f.vy) for f in flakes]


class CollideEquivalence(unittest.TestCase):
    def test_matches_reference_bit_for_bit(self):
        for seed in range(6):
            for n, spread in ((40, 20), (150, 25), (400, 30), (600, 35)):
                for size in (0.6, 1.0, 2.0):
                    flakes_a = make_flakes(n, seed, spread)
                    flakes_b = copy.deepcopy(flakes_a)
                    g = P.GlobePhysics()
                    g.size = size
                    for _ in range(3):                      # 여러 번 이어서 적용해도 같아야 한다
                        reference_collide(g, flakes_a)
                        g._collide(flakes_b)
                    self.assertEqual(snap(flakes_a), snap(flakes_b), (seed, n, size))

    def test_empty_and_single(self):
        g = P.GlobePhysics()
        g._collide([])
        f = make_flakes(1, 1, 5)
        before = snap(f)
        g._collide(f)
        self.assertEqual(snap(f), before)


class StepSanity(unittest.TestCase):
    def test_flakes_stay_inside_glass_and_settle(self):
        random.seed(7)
        kinds = list(C.DECOR)[:3]
        decor = [M.new_item(k, C.GX + dx, C.GY) for k, dx in zip(kinds, (-50, 0, 50))]
        g = P.GlobePhysics(dict(M.DEFAULT_SNOW, amount=300), decor)
        for i in range(120):
            g.step(1 / 30, 900 if (i // 5) % 2 else -900, 0.0) if i < 60 else g.step(1 / 30)
            for f in g.flakes:
                # 눈송이끼리 밀어내는 충돌은 유리벽 보정 뒤에 적용되므로 원래 구현도 벽을 조금 넘을 수 있다(최적화 전과 동일)
                self.assertLessEqual(math.hypot(f.x - C.SCX, f.y - C.SCY), C.WALL_R + 8.0)
        for _ in range(600):
            g.step(1 / 30)
        self.assertEqual(g.rest_count, sum(1 for f in g.flakes if f.rest))
        self.assertGreater(g.rest_count, len(g.flakes) * 0.9)          # 흔들림이 멈추면 대부분 가라앉는다


if __name__ == "__main__":
    unittest.main()
