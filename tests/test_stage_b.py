"""v1.9.4 B단계: 눈사람 복원 경계 조건 + 스노우볼 모델/물리/독립성 (PySide6 불필요)."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snow.physics import Rect, SnowSim, SurfaceInfo
from snowman import model as SM
from snowman.world import SnowmanWorld
from snowglobe import catalog as C
from snowglobe import model as GM
from snowglobe.physics import GlobePhysics

DT = 1 / 30


def make_world(temp=-15):
    sim = SnowSim(seed=3)
    sim.cell = 3
    sim.set_bounds(Rect(0, 0, 1920, 1080))
    sim.configure(amount=0, accumulate=50, temperature=temp, wind_strength=0, cursor_on=False,
                  cursor_strength=1.0, cursor_radius=120.0)
    sim.set_surfaces([SurfaceInfo("w", 200, 700, 1700, [(200, 1700)], [(200, 1700)])])
    w = SnowmanWorld(sim, seed=1)
    sim.bodies = w
    return sim, w


def run(sim, w, sec):
    for _ in range(int(sec / DT)):
        sim.step(DT)
        w.step(DT, None, False)


class SnowmanRestoreEdges(unittest.TestCase):
    def _state(self):
        sim, w = make_world()
        a = w.spawn_ball(radius=24, x=800, y=300)
        b = w.spawn_ball(radius=16, x=800, y=250)
        w.spawn_ball(radius=12, x=500, y=300)
        w.add_decorative("classic", x=1400, y=700)
        run(sim, w, 1.0)
        return json.loads(json.dumps(w.to_state())), (a, b)

    def test_reload_into_same_world_keeps_mass_balance(self):
        sim, w = make_world()
        for i in range(3):
            w.spawn_ball(radius=14 + i * 4, x=400 + i * 200, y=300)
        run(sim, w, 1.0)
        st = json.loads(json.dumps(w.to_state()))
        for _ in range(3):                                         # 설정 초기화/백업 복원이 반복돼도 눈의 양이 새지 않아야 한다
            w.load_state(st["items"], st["balls"], st["props"])
        self.assertLess(abs(sim.mass_balance()), 1.0)
        self.assertEqual(len(w.balls), 3)

    def test_snowman_with_missing_or_single_ball_is_dropped_but_balls_survive(self):
        st, (a, b) = self._state()
        items = [{"id": "s1", "type": "dynamic", "balls": [a, "ghost"]}]
        sim, w = make_world()
        w.load_state(items, st["balls"], st["props"])
        self.assertNotIn("s1", w.snowmen)                           # 공이 2개 미만이면 눈사람을 만들지 않는다
        self.assertIn(a, w.balls)
        self.assertIsNone(w.balls[a].sid)                           # 남은 공은 낱개 눈덩이로 복원
        self.assertLess(abs(sim.mass_balance()), 1.0)

    def test_ball_claimed_by_two_snowmen_goes_to_first_only(self):
        st, (a, b) = self._state()
        items = [{"id": "s1", "type": "dynamic", "balls": [a, b]},
                 {"id": "s2", "type": "dynamic", "balls": [a, b]}]
        sim, w = make_world()
        w.load_state(items, st["balls"], st["props"])
        self.assertEqual(w.snowmen["s1"].balls, [a, b])
        self.assertNotIn("s2", w.snowmen)
        self.assertEqual(w.balls[a].sid, "s1")

    def test_garbage_state_does_not_raise(self):
        sim, w = make_world()
        for items, balls, props in (
                (None, None, None), ("x", 5, {}), ([None, 3, "a"], [None, {"id": 1}], [[], 7]),
                ([{"type": "decorative", "x": "nan", "y": float("inf"), "scale": -5, "rot": "q"}], [], [])):
            w.load_state(items, balls, props)
        self.assertLess(abs(sim.mass_balance()), 1.0)

    def test_decorative_never_melts_after_restore_in_heat(self):
        st, _ = self._state()
        sim, w = make_world(temp=30)
        w.load_state(st["items"], st["balls"], st["props"])
        deco = [s for s in w.snowmen.values() if s.type == SM.DECORATIVE]
        self.assertTrue(deco)
        before = [(s.scale, s.x, s.y) for s in deco]
        run(sim, w, 20.0)
        after = [(s.scale, s.x, s.y) for s in w.snowmen.values() if s.type == SM.DECORATIVE]
        self.assertEqual(before, after)

    def test_dynamic_snowman_melts_in_heat_after_restore(self):
        sim, w = make_world(temp=-15)
        a = w.spawn_ball(radius=24, x=800, y=300)
        run(sim, w, 1.0)
        st = json.loads(json.dumps(w.to_state()))
        sim2, w2 = make_world(temp=25)
        w2.load_state(st["items"], st["balls"], st["props"])
        m0 = sum(b.m for b in w2.balls.values())
        run(sim2, w2, 15.0)
        m1 = sum(b.m for b in w2.balls.values())
        self.assertLess(m1, m0)
        self.assertLess(abs(sim2.mass_balance()), 1.0)


class GlobeModel(unittest.TestCase):
    def test_garbage_globe_is_sanitized_or_rejected(self):
        for raw in (None, 5, "x", [], {"decor": "zzz"}, {"x": "nan", "y": float("inf"), "size": 999, "snow": 7},
                    {"decor": [None, {"kind": "nope"}, {"kind": "gift", "x": "q", "scale": 1e9}]}):
            g = GM.clean_globe(raw)
            if g is None:
                continue
            self.assertTrue(C.GLOBE_SIZE_MIN <= g["size"] <= C.GLOBE_SIZE_MAX)
            self.assertEqual(g["snow"]["normal"] + g["snow"]["big"] + g["snow"]["sparkle"], 100)
            for it in g["decor"]:
                self.assertTrue(C.SCALE_MIN <= it["scale"] <= C.SCALE_MAX)

    def test_decor_count_is_capped(self):
        raw = {"decor": [{"kind": "gift", "x": 48, "y": 72} for _ in range(C.MAX_DECOR + 25)]}
        self.assertEqual(len(GM.clean_globe(raw)["decor"]), C.MAX_DECOR)

    def test_duplicate_decor_ids_get_unique_ids(self):
        raw = {"decor": [{"id": "same", "kind": "gift", "x": 48, "y": 72}, {"id": "same", "kind": "gift", "x": 40, "y": 72}]}
        ids = [it["id"] for it in GM.clean_globe(raw)["decor"]]
        self.assertEqual(len(set(ids)), 2)

    def test_clone_is_independent(self):
        g = GM.new_globe(10, 20)
        c = GM.clone_globe(g)
        self.assertNotEqual(g["id"], c["id"])
        self.assertFalse({i["id"] for i in g["decor"]} & {i["id"] for i in c["decor"]})
        c["decor"][0]["x"] = 1.0
        c["snow"]["amount"] = 7
        self.assertNotEqual(g["decor"][0]["x"], 1.0)
        self.assertNotEqual(g["snow"]["amount"], 7)

    def test_ratio_always_sums_to_100(self):
        snow = dict(GM.DEFAULT_SNOW)
        for key in C.SNOW_KINDS:
            for v in (0, 1, 33, 50, 99, 100):
                GM.set_ratio(snow, key, v)
                self.assertEqual(sum(snow[k] for k in C.SNOW_KINDS), 100)
                self.assertEqual(snow[key], v)

    def test_split_counts_sums_to_amount(self):
        for amount in (0, 1, 7, 100, 333, 1000):
            self.assertEqual(sum(GM.split_counts(amount, GM.DEFAULT_SNOW).values()), amount)


class GlobeIndependence(unittest.TestCase):
    def test_stepping_one_globe_does_not_change_another(self):
        g1, g2 = GM.new_globe(), GM.new_globe()
        p1, p2 = GlobePhysics(g1["snow"], g1["decor"]), GlobePhysics(g2["snow"], g2["decor"])
        for _ in range(60):                                         # 두 눈이 모두 가라앉도록
            p1.step(0.03, 0.0, 0.0)
            p2.step(0.03, 0.0, 0.0)
        snap2 = copy.deepcopy(p2.snapshot())
        counts2 = dict(p2.counts())
        for _ in range(40):                                         # 1번만 세게 흔든다
            p1.step(0.03, 900.0, -400.0)
        self.assertEqual(p2.snapshot(), snap2)
        self.assertEqual(p2.counts(), counts2)
        self.assertIsNot(p1.pile, p2.pile)
        self.assertIsNot(p1.flakes, p2.flakes)

    def test_flake_count_matches_amount_and_reconfigure(self):
        g = GM.new_globe()
        p = GlobePhysics(g["snow"], g["decor"])
        self.assertEqual(len(p.flakes), g["snow"]["amount"])
        snow = dict(g["snow"], amount=50)
        p.configure(snow)
        self.assertEqual(len(p.flakes), 50)
        p.configure(dict(snow, amount=200))
        self.assertEqual(len(p.flakes), 200)

    def test_physics_survives_extreme_input(self):
        g = GM.new_globe()
        p = GlobePhysics(g["snow"], g["decor"])
        for ax, ay in ((1e6, 1e6), (-1e6, 1e6), (0, 0)):
            p.step(0.05, ax, ay)
        for f in p.flakes:
            self.assertTrue(abs(f.x) < 1e4 and abs(f.y) < 1e4)



class SnowmanStaleSelection(unittest.TestCase):
    def test_stale_selection_and_grab_cleared_on_load(self):
        sim, w = make_world()
        a = w.spawn_ball(radius=20, x=800, y=300)
        w.selected = a
        w._grab = {"id": a, "ox": 0.0, "oy": 0.0, "kind": "body", "base": a}
        w.load_state([], [], [])                                   # 저장된 상태에 그 공이 없다
        self.assertIsNone(w.selected)
        self.assertIsNone(w._grab)

    def test_valid_selection_is_kept(self):
        sim, w = make_world()
        a = w.spawn_ball(radius=20, x=800, y=300)
        st = json.loads(json.dumps(w.to_state()))
        w.selected = a
        w.load_state(st["items"], st["balls"], st["props"])
        self.assertEqual(w.selected, a)


if __name__ == "__main__":
    unittest.main()
