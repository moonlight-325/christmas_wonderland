"""눈사람 시스템 테스트 (PySide6 불필요, 순수 물리). 요구된 10개 항목을 코드로 확인한다.

1 생성/굴리기  2 눈 쌓인 곳에서 성장  3 크기별 무게/이동  4 2~3개 조립  5 장식 추가/변경
6 dynamic 온도 상승 시 녹음  7 녹은 눈 -> 물 연동  8 decorative 절대 안 녹음  9 두 종류 공존  10 저장/복원
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import Rect, SnowSim, SurfaceInfo
from snowman import model as M
from snowman.world import SnowmanWorld

DT = 1 / 30


def make(temp=-15, snow=0.0):
    sim = SnowSim(seed=3)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    sim.configure(amount=0, accumulate=50, temperature=temp, wind_strength=0, cursor_on=False,
                  cursor_strength=1.0, cursor_radius=120.0)
    sim.set_surfaces([SurfaceInfo("w", 200, 700, 1700, [(200, 1700)], [(200, 1700)])])
    p = sim.piles["w"]
    if snow > 0:
        for i in range(len(p.cells)):
            p.cells[i] = snow
            sim.mass_added += snow
    w = SnowmanWorld(sim, seed=1)
    sim.bodies = w
    return sim, w


def run(sim, w, sec, cursor_fn=None, down=False):
    for k in range(int(sec / DT)):
        sim.step(DT)
        cur = cursor_fn(k * DT) if cursor_fn else None
        w.step(DT, cur, down)


def mass_ok(sim, tol=1.0):
    return abs(sim.mass_balance()) < tol


class T(unittest.TestCase):
    def test_1_spawn_and_push(self):
        sim, w = make()
        bid = w.spawn_ball(radius=20, x=800, y=300)
        run(sim, w, 2.0)
        b = w.balls[bid]
        self.assertTrue(b.grounded)
        self.assertAlmostEqual(b.y + b.r, 700, delta=2.0)           # 창 윗면에 정착
        x0 = b.x
        # 마우스를 오른쪽으로 빠르게 움직여 밀기 (공 왼쪽에서 오른쪽으로 스친다)
        run(sim, w, 0.6, cursor_fn=lambda t: (x0 - 40 + 500 * t, b.y))
        self.assertGreater(b.x, x0 + 20)

    def test_2_growth_on_snow(self):
        sim, w = make(snow=8.0)
        bid = w.spawn_ball(radius=12, x=600, y=300)
        run(sim, w, 1.0)
        b = w.balls[bid]
        m0 = b.m
        b.vx = 220.0
        run(sim, w, 2.0)
        self.assertGreater(w.balls[bid].m, m0 * 1.5)
        self.assertTrue(mass_ok(sim))                                # 눈 더미에서 실제로 가져온 만큼만 커진다

    def test_2b_no_growth_without_snow(self):
        sim, w = make(snow=0.0)
        bid = w.spawn_ball(radius=12, x=600, y=300)
        run(sim, w, 1.0)
        b = w.balls[bid]
        m0 = b.m
        b.vx = 220.0
        run(sim, w, 2.0)
        self.assertAlmostEqual(w.balls[bid].m, m0, delta=m0 * 0.02)

    def test_2c_trail_left_behind(self):
        sim, w = make(snow=6.0)
        p = sim.piles["w"]
        before = sum(p.cells)
        bid = w.spawn_ball(radius=14, x=600, y=300)
        run(sim, w, 0.8)
        w.balls[bid].vx = 250.0
        run(sim, w, 1.5)
        self.assertLess(sum(p.cells), before)                        # 지나간 자리 눈이 줄었다

    def test_3_weight_differs(self):
        sim, w = make()
        small = w.spawn_ball(radius=10, x=500, y=300)
        big = w.spawn_ball(radius=38, x=1300, y=300)
        run(sim, w, 2.0)
        self.assertLess(w.pmass(w.balls[small]) * 5, w.pmass(w.balls[big]))
        xs, xb = w.balls[small].x, w.balls[big].x
        # 같은 속도의 마우스로 밀면 작은 눈덩이가 더 많이 움직인다
        sweep = lambda x0, y: (lambda t: (x0 - 40 + 400 * t, y))
        for k in range(int(0.5 / DT)):
            sim.step(DT)
            t = k * DT
            w.step(DT, (xs - 40 + 400 * t, w.balls[small].y), False)
        for k in range(int(0.5 / DT)):
            sim.step(DT)
            t = k * DT
            w.step(DT, (xb - 80 + 400 * t, w.balls[big].y), False)
        self.assertGreater(w.balls[small].x - xs, (w.balls[big].x - xb) * 2)

    def _stack(self, w, sim, n=2):
        radii = [34, 24, 15][:n]
        ids = []
        for i, r in enumerate(radii):
            ids.append(w.spawn_ball(radius=r, x=900 + i * 3, y=200 - i * 160))
        return ids

    def test_4_assembly(self):
        sim, w = make()
        a = w.spawn_ball(radius=34, x=900, y=300)
        run(sim, w, 2.0)
        b = w.spawn_ball(radius=24, x=904, y=w.balls[a].y - w.balls[a].r - 30)
        run(sim, w, 1.0)
        self.assertTrue(w.hints or any(s.type == "dynamic" for s in w.snowmen.values()))
        run(sim, w, 2.0)
        sns = [s for s in w.snowmen.values() if s.type == "dynamic"]
        self.assertEqual(len(sns), 1)
        self.assertEqual(sns[0].balls, [a, b])
        c = w.spawn_ball(radius=15, x=902, y=w.balls[b].y - w.balls[b].r - 25)
        run(sim, w, 3.0)
        sn = [s for s in w.snowmen.values() if s.type == "dynamic"][0]
        self.assertEqual(sn.balls, [a, b, c])                        # 큰 것 아래, 작은 것 위

    def test_4b_bigger_cannot_go_on_top(self):
        sim, w = make()
        a = w.spawn_ball(radius=20, x=900, y=300)
        run(sim, w, 2.0)
        w.spawn_ball(radius=30, x=900, y=w.balls[a].y - 60)
        run(sim, w, 2.5)
        self.assertFalse(any(s.type == "dynamic" for s in w.snowmen.values()))

    def _built(self, sim, w):
        a = w.spawn_ball(radius=34, x=900, y=300)
        run(sim, w, 2.0)
        b = w.spawn_ball(radius=24, x=904, y=w.balls[a].y - w.balls[a].r - 30)
        run(sim, w, 3.0)
        sn = [s for s in w.snowmen.values() if s.type == "dynamic"][0]
        return sn

    def test_4c_topple_and_reassemble(self):
        sim, w = make()
        sn = self._built(sim, w)
        sid = sn.id
        base = w.balls[sn.balls[0]]
        base.vx += 900.0                                              # 강한 충격
        run(sim, w, 1.5)
        self.assertNotIn(sid, w.snowmen)                              # 분리됨
        self.assertEqual(len(w.balls), 2)
        run(sim, w, 3.0)                                              # 다시 가까이 두면 재조립 가능한 상태가 된다
        top, bot = sorted(w.balls.values(), key=lambda b: b.m)
        top.x, top.y, top.vx, top.vy = bot.x + 2, bot.y - bot.r - top.r * 0.88 - 5, 0.0, 0.0
        bot.vx = 0.0
        run(sim, w, 2.5)
        self.assertTrue(any(s.type == "dynamic" for s in w.snowmen.values()))

    def test_4d_gentle_push_does_not_topple(self):
        sim, w = make()
        sn = self._built(sim, w)
        base = w.balls[sn.balls[0]]
        base.vx += 60.0
        run(sim, w, 3.0)
        self.assertIn(sn.id, w.snowmen)

    def test_5_decor(self):
        sim, w = make()
        sn = self._built(sim, w)
        for kind in ("hat", "scarf", "eyes", "nose", "mouth", "buttons", "arms", "gloves"):
            self.assertTrue(w.add_decor(sn.id, kind))
        lst = w.decor_list(sn.id)
        self.assertEqual(len(lst), 8)
        hat = [d for _o, d in lst if d["kind"] == "hat"][0]
        w.update_decor(sn.id, hat["id"], color="red", style="santa", dx=10, dy=-5, size=150)
        hat = [d for _o, d in w.decor_list(sn.id) if d["kind"] == "hat"][0]
        self.assertEqual((hat["color"], hat["style"], hat["dx"], hat["size"]), ("red", "santa", 10, 150))
        self.assertTrue(w.remove_decor(sn.id, hat["id"]))
        self.assertEqual(len(w.decor_list(sn.id)), 7)
        # 장식은 눈사람과 함께 이동한다 (눈덩이에 붙어 있다)
        base = w.balls[sn.balls[0]]
        base.vx = 80.0
        run(sim, w, 0.5)
        head = w.balls[sn.balls[-1]]
        self.assertTrue(any(d["kind"] == "eyes" for d in head.decor))

    def test_6_dynamic_melts_with_temperature(self):
        sim, w = make(temp=15)
        sn = self._built(sim, w)
        m0 = [w.balls[i].m for i in sn.balls]
        run(sim, w, 20.0)
        m1 = [w.balls[i].m for i in sn.balls]
        self.assertTrue(all(b < a for a, b in zip(m0, m1)))
        self.assertLess(w.balls[sn.balls[0]].r, 34 * 1.0)             # 크기가 작아짐

    def test_6b_cold_does_not_melt(self):
        sim, w = make(temp=-25)
        sn = self._built(sim, w)
        m0 = [w.balls[i].m for i in sn.balls]
        run(sim, w, 20.0)
        m1 = [w.balls[i].m for i in sn.balls]
        self.assertEqual(m0, m1)

    def test_6c_full_melt_leaves_decor(self):
        sim, w = make(temp=30)
        sn = self._built(sim, w)
        w.add_decor(sn.id, "hat")
        w.add_decor(sn.id, "scarf")
        # 오래 지나면 완전히 녹아 사라지지만 장식은 주변에 남는다
        for ball in w.balls.values():
            ball.m = min(ball.m, 25.0)
        run(sim, w, 160.0)
        self.assertEqual(len(w.balls), 0)
        self.assertEqual(len(w.snowmen), 0)
        self.assertEqual({p["kind"] for p in w.props}, {"hat", "scarf"})
        self.assertTrue(mass_ok(sim))

    def test_7_melting_snowman_makes_no_water(self):
        sim, w = make(temp=20)
        sn = self._built(sim, w)
        for ball in w.balls.values():
            ball.m = min(ball.m, 60.0)
        melted0 = sim.mass_melted
        run(sim, w, 40.0)
        self.assertGreater(sim.mass_melted, melted0 + 0.5)            # 눈덩이는 기존 온도 시스템대로 녹아 장부에 기록된다
        self.assertFalse(hasattr(sim, "water_made"))                  # 물 장부/물 객체가 아예 없다
        self.assertFalse(hasattr(sim, "drops"))
        self.assertTrue(mass_ok(sim))

    def test_8_decorative_never_melts(self):
        sim, w = make(temp=30)
        did = w.add_decorative("classic", x=700, y=700)
        snapshot = (w.snowmen[did].scale, w.snowmen[did].rot, len(w.snowmen[did].decor), w.snowmen[did].x)
        sim.melt = 80.0                                               # 용해 속도 극단값
        run(sim, w, 120.0)
        sn = w.snowmen[did]
        self.assertEqual((sn.scale, sn.rot, len(sn.decor), sn.x), snapshot)
        self.assertEqual(sn.type, "decorative")
        self.assertEqual(len(w.balls), 0)                             # 물리 눈덩이로 바뀌지도 않는다

    def test_9_both_kinds_coexist(self):
        sim, w = make(temp=15)
        did = w.add_decorative("santa", x=1500, y=700)
        sn = self._built(sim, w)
        before = (w.snowmen[did].scale, w.snowmen[did].x, len(w.snowmen[did].decor))
        run(sim, w, 30.0)
        self.assertEqual((w.snowmen[did].scale, w.snowmen[did].x, len(w.snowmen[did].decor)), before)
        self.assertLess(w.balls[sn.balls[0]].m, 100000)
        self.assertEqual(sorted(s.type for s in w.snowmen.values()), ["decorative", "dynamic"])
        w.remove(sn.id)                                               # dynamic 삭제가 decorative 에 영향 없음
        self.assertIn(did, w.snowmen)

    def test_9b_decorative_collision_and_snow_cap(self):
        sim, w = make(temp=-15)
        did = w.add_decorative("classic", x=1200, y=700)
        sim.set_surfaces([SurfaceInfo("w", 200, 700, 1700, [(200, 1700)], [(200, 1700)])] + w.surfaces())
        self.assertIn(("deco", did), sim.piles)                       # 머리 위에 눈이 쌓이는 표면
        b = w.spawn_ball(radius=20, x=1100, y=650)
        w.balls[b].vx = 300.0
        run(sim, w, 1.5)
        self.assertLess(w.balls[b].x, 1200 + 5)                       # 장식용 눈사람을 뚫고 지나가지 않는다

    def test_10_save_and_restore(self):
        sim, w = make(temp=-15)
        sn = self._built(sim, w)
        w.add_decor(sn.id, "hat", "santa", "red")
        loose = w.spawn_ball(radius=12, x=500, y=300)
        did = w.add_decorative("cool", x=1400, y=700)
        w.set_deco(did, scale=1.5, rot=10)
        w.props.append({"id": "p1", "kind": "hat", "style": "tophat", "color": "black", "size": 100,
                        "x": 300.0, "y": 690.0, "r": 20.0})
        run(sim, w, 2.0)
        state = w.to_state()
        import json
        state = json.loads(json.dumps(state))
        sim2, w2 = make(temp=-15)
        w2.load_state(state["items"], state["balls"], state["props"])
        self.assertEqual(sorted(s.type for s in w2.snowmen.values()), sorted(s.type for s in w.snowmen.values()))
        d2 = w2.snowmen[did]
        self.assertEqual((d2.scale, d2.rot, d2.style), (1.5, 10.0, "cool"))
        sn2 = w2.snowmen[sn.id]
        self.assertEqual(sn2.balls, sn.balls)
        for bid in w.balls:
            self.assertAlmostEqual(w2.balls[bid].m, w.balls[bid].m, delta=0.01)
        self.assertEqual([d["kind"] for _o, d in w2.decor_list(sn.id)], [d["kind"] for _o, d in w.decor_list(sn.id)])
        self.assertEqual(len(w2.props), 1)
        self.assertTrue(mass_ok(sim2))

    def test_10b_corrupt_state_is_cleaned(self):
        self.assertEqual(M.clean_items([{"id": 1}, "x", {"id": "a", "type": "zzz"}]), [])
        self.assertEqual(M.clean_balls([{"id": "a", "area": "nan"}])[0]["area"], 800.0)
        self.assertEqual(M.clean_decor([{"id": "d", "kind": "nope"}]), [])

    def test_mass_conservation_overall(self):
        sim, w = make(temp=5, snow=5.0)
        ids = [w.spawn_ball(radius=r, x=400 + i * 200, y=300) for i, r in enumerate((14, 22, 30))]
        for k, bid in enumerate(ids):
            w.balls[bid].vx = 150.0 * (1 if k % 2 == 0 else -1)
        run(sim, w, 20.0)
        self.assertTrue(mass_ok(sim, 1.0), sim.mass_balance())
        w.remove(ids[0])
        self.assertTrue(mass_ok(sim, 1.0), sim.mass_balance())


if __name__ == "__main__":
    unittest.main()
