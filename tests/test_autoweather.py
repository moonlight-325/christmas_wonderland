"""자동 날씨 시스템 테스트 (PySide6 불필요): 명세/검증, 혼합형 알고리즘, 수동 고정, 범위 준수, 프리셋 저장소."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weather import spec
from weather.core import AutoWeatherCore, MAX_DT, reflect01
from weather.presets import PresetStore


def manual_values(**over):
    m = {v: spec.VARS_BY_ID[v]["dmin"] for v in spec.SETTING_VARS}
    m.update(over)
    return m


def run(core, seconds, manual=None, dt=0.1, manual_kind=None, on_step=None):
    manual = manual or manual_values()
    for _ in range(int(seconds / dt)):
        core.step(dt, manual, manual_kind)
        if on_step:
            on_step(core)


class SpecTests(unittest.TestCase):
    def test_settings_ranges_match_defaults_module(self):
        from settings.defaults import DEFAULTS, RANGES
        for v in spec.NUMERIC_VARS:
            if not v["key"]:
                continue
            self.assertEqual(RANGES[v["key"]], (v["lo"], v["hi"]), v["key"])
            sec, key = v["key"].split(".")
            self.assertIn(key, DEFAULTS[sec], v["key"])

    def test_default_config_is_valid_and_stable(self):
        cfg = spec.default_config()
        self.assertEqual(spec.validate_ranges(cfg), [])
        self.assertEqual(spec.clean_config(cfg), cfg)

    def test_builtin_presets_valid(self):
        self.assertEqual(spec.PRESET_NAMES, ["잔잔한 겨울", "포근한 눈 내리는 날", "폭설", "강한 눈보라", "변화무쌍한 겨울"])
        for name, cfg in spec.PRESETS.items():
            self.assertEqual(spec.validate_ranges(cfg), [], name)
            self.assertTrue(spec.enabled_kinds(cfg), name)
            self.assertEqual(spec.clean_config(cfg), cfg, name)

    def test_range_validation(self):
        self.assertIsNone(spec.validate_range("snow_amount", 0, 600))
        self.assertIn("최솟값", spec.validate_range("snow_amount", 700, 600))
        self.assertIn("허용 범위", spec.validate_range("temperature", -50, 0))
        self.assertIn("허용 범위", spec.validate_range("temperature", 0, 99))
        self.assertIn("숫자", spec.validate_range("snow_amount", "a", 5))

    def test_clean_config_repairs_garbage(self):
        bad = {"kinds": {"clear": {"on": "yes", "weight": 999}, "heavy": 5},
               "vars": {"snow_amount": {"auto": 1, "min": 900, "max": 100},
                        "temperature": {"min": -99, "max": 99}, "wind_strength": {"min": 10, "max": 20}},
               "change_speed": 500, "randomness": "x"}
        out = spec.clean_config(bad)
        self.assertEqual(out["kinds"]["clear"]["weight"], 100)
        self.assertTrue(out["kinds"]["clear"]["on"])                       # 잘못된 타입은 기본값
        self.assertEqual((out["vars"]["snow_amount"]["min"], out["vars"]["snow_amount"]["max"]), (0, 600))
        self.assertEqual((out["vars"]["temperature"]["min"], out["vars"]["temperature"]["max"]), (-12, 4))
        self.assertEqual((out["vars"]["wind_strength"]["min"], out["vars"]["wind_strength"]["max"]), (10, 20))
        self.assertEqual(out["change_speed"], 100)
        self.assertEqual(out["randomness"], 50)
        self.assertEqual(spec.validate_ranges(out), [])

    def test_clean_section_disables_unstartable(self):
        raw = spec.default_settings_section()
        raw["enabled"] = True
        for k in spec.KIND_IDS:
            raw["kinds"][k]["on"] = False
        out = spec.clean_section(raw)
        self.assertFalse(out["enabled"])


class CoreTests(unittest.TestCase):
    def test_reflect(self):
        for x in (-3.3, -1.0, -0.2, 0.0, 0.5, 1.0, 1.7, 5.5):
            self.assertTrue(0.0 <= reflect01(x) <= 1.0)

    def test_cannot_start_without_enabled_kind(self):
        cfg = spec.default_config()
        for k in spec.KIND_IDS:
            cfg["kinds"][k]["on"] = False
        core = AutoWeatherCore(cfg, seed=1)
        msg = core.start(manual_values())
        self.assertIn("켜진 날씨", msg)
        self.assertEqual(core.phase, "idle")

    def test_cannot_start_with_bad_range(self):
        cfg = spec.default_config()
        cfg["vars"]["snow_amount"]["min"], cfg["vars"]["snow_amount"]["max"] = 500, 100
        core = AutoWeatherCore.__new__(AutoWeatherCore)
        AutoWeatherCore.__init__(core, None, seed=1)
        core.cfg = cfg                                           # clean_config 를 우회해 잘못된 설정 주입
        self.assertIsNotNone(core.start(manual_values()))

    def test_applied_values_never_leave_user_ranges(self):
        for seed in range(6):
            cfg = spec.default_config()
            cfg["vars"]["snow_amount"].update(min=100, max=300)
            cfg["vars"]["temperature"].update(min=-3, max=2)
            cfg["vars"]["wind_strength"].update(min=40, max=45)
            cfg["change_speed"] = 100
            cfg["randomness"] = 100
            cfg["vars"][spec.DURATION_VAR].update(min=10, max=20)
            core = AutoWeatherCore(cfg, seed=seed)
            core.start(manual_values(snow_amount=200, temperature=0, wind_strength=42))

            def check(c):
                for vid, x in c.applied.items():
                    d = c.cfg["vars"][vid]
                    self.assertTrue(d["min"] - 1e-9 <= x <= d["max"] + 1e-9, (vid, x, d))
                self.assertTrue(10 - 1e-9 <= c.period_len <= 20 + 1e-9)
            run(core, 600, manual_values(snow_amount=200, temperature=0, wind_strength=42), on_step=check)
            self.assertGreater(core.transitions, 10)

    def test_start_value_outside_range_is_clamped(self):
        cfg = spec.default_config()
        cfg["vars"]["snow_amount"].update(min=100, max=200)
        core = AutoWeatherCore(cfg, seed=1)
        core.start(manual_values(snow_amount=900))
        self.assertEqual(core.applied["snow_amount"], 200)

    def test_only_enabled_kinds_are_selected_and_weights_matter(self):
        cfg = spec.default_config()
        for k in spec.KIND_IDS:
            cfg["kinds"][k]["on"] = k in ("clear", "heavy")
        cfg["kinds"]["clear"]["weight"], cfg["kinds"]["heavy"]["weight"] = 90, 10
        cfg["vars"][spec.DURATION_VAR].update(min=10, max=10)
        core = AutoWeatherCore(cfg, seed=4)
        core.start(manual_values())
        seen = []
        for _ in range(400):
            core._begin_period()
            seen.append(core.kind)
        self.assertEqual(set(seen), {"clear", "heavy"})
        self.assertGreater(seen.count("clear"), seen.count("heavy") * 3)
        self.assertEqual(spec.enabled_kinds(cfg), ["clear", "heavy"])

    def test_single_enabled_kind_stays(self):
        cfg = spec.default_config()
        for k in spec.KIND_IDS:
            cfg["kinds"][k]["on"] = k == "snow"
        cfg["vars"][spec.DURATION_VAR].update(min=10, max=12)
        core = AutoWeatherCore(cfg, seed=2)
        core.start(manual_values())
        kinds = set()
        run(core, 300, on_step=lambda c: kinds.update((c.kind, c.next_kind)))
        self.assertEqual(kinds, {"snow"})

    def test_weather_links_variables_but_not_forced(self):
        """맑음은 강설량이 낮고, 폭설/눈보라는 높게 뽑힌다. 모든 변수가 같은 값으로 묶이진 않는다."""
        cfg = spec.default_config()
        cfg["randomness"] = 40
        core = AutoWeatherCore(cfg, seed=7)
        core.start(manual_values())

        def mean(kind, vid, n=300):
            core.kind = kind
            xs = []
            for _ in range(n):
                xs.append(core._sample(vid, kind))
            return sum(xs) / n
        lo, hi = cfg["vars"]["snow_amount"]["min"], cfg["vars"]["snow_amount"]["max"]
        self.assertLess(mean("clear", "snow_amount"), lo + (hi - lo) * 0.2)
        self.assertGreater(mean("heavy", "snow_amount"), lo + (hi - lo) * 0.65)
        self.assertGreater(mean("blizzard", "wind_strength"), mean("snow", "wind_strength"))
        self.assertGreater(mean("blizzard", "gust_strength"), mean("light", "gust_strength"))
        self.assertGreater(mean("heavy", "snow_accum_rate"), mean("light", "snow_accum_rate"))
        # 변수들이 서로 독립적으로 뽑힘 (한 번의 날씨에서도 값 위치가 제각각)
        pos = []
        for vid in ("snow_amount", "snow_size", "temperature", "wind_strength"):
            d = cfg["vars"][vid]
            pos.append(round((core._sample(vid, "snow") - d["min"]) / (d["max"] - d["min"]), 2))
        self.assertGreater(len(set(pos)), 1)

    def test_link_zero_is_uniform_over_range(self):
        cfg = spec.default_config()
        cfg["link"] = 0
        core = AutoWeatherCore(cfg, seed=3)
        core.start(manual_values())
        d = cfg["vars"]["snow_amount"]
        xs = [core._sample("snow_amount", "clear") for _ in range(600)]
        self.assertGreater(sum(xs) / len(xs), d["min"] + (d["max"] - d["min"]) * 0.4)

    def test_manual_vars_are_never_touched(self):
        cfg = spec.default_config()
        cfg["vars"]["snow_amount"]["auto"] = False
        cfg["vars"]["wind_strength"]["auto"] = False
        core = AutoWeatherCore(cfg, seed=5)
        core.start(manual_values(snow_amount=500, wind_strength=33))
        run(core, 300)
        vals = core.values()
        self.assertNotIn("snow_amount", vals)
        self.assertNotIn("wind_strength", vals)
        self.assertIn("temperature", vals)

    def test_switching_var_to_manual_mid_run_keeps_others_auto(self):
        core = AutoWeatherCore(spec.default_config(), seed=9)
        core.start(manual_values())
        run(core, 30)
        before = core.values()["temperature"]
        cfg = copy.deepcopy(core.cfg)
        cfg["vars"]["snow_amount"]["auto"] = False            # 사용자가 강설량을 직접 바꿈 -> 그 변수만 수동
        core.set_config(cfg)
        run(core, 60, manual=manual_values(snow_amount=250))
        vals = core.values()
        self.assertNotIn("snow_amount", vals)
        for vid in ("temperature", "wind_strength", "snow_size", "gust_strength"):
            self.assertIn(vid, vals)
        self.assertNotEqual(vals["temperature"], before)       # 나머지는 계속 변한다

    def test_resume_auto_continues_from_current_manual_value(self):
        cfg = spec.default_config()
        cfg["vars"]["snow_amount"]["auto"] = False
        core = AutoWeatherCore(cfg, seed=5)
        core.start(manual_values(snow_amount=300))
        run(core, 20, manual=manual_values(snow_amount=300))
        cfg2 = copy.deepcopy(core.cfg)
        cfg2["vars"]["snow_amount"]["auto"] = True
        core.set_config(cfg2)
        core.step(0.1, manual_values(snow_amount=300))
        self.assertIn("snow_amount", core.applied)
        self.assertAlmostEqual(core.applied["snow_amount"], 300, delta=15)

    def test_range_shrink_while_running_clamps_immediately(self):
        core = AutoWeatherCore(spec.default_config(), seed=11)
        core.start(manual_values())
        run(core, 120)
        cfg = copy.deepcopy(core.cfg)
        cfg["vars"]["temperature"].update(min=-1, max=0)
        core.set_config(cfg)
        self.assertTrue(-1 <= core.applied["temperature"] <= 0)
        run(core, 60, on_step=lambda c: self.assertTrue(-1 <= c.applied["temperature"] <= 0))

    def test_smooth_no_sudden_jumps(self):
        cfg = spec.default_config()
        cfg["change_speed"] = 100                               # 가장 빠른 설정에서도 초당 변화량 제한
        cfg["vars"][spec.DURATION_VAR].update(min=10, max=10)
        core = AutoWeatherCore(cfg, seed=2)
        core.start(manual_values())
        prev = dict(core.applied)
        worst = 0.0
        for _ in range(3000):
            core.step(0.1, manual_values())
            for vid, x in core.applied.items():
                v = spec.VARS_BY_ID[vid]
                worst = max(worst, abs(x - prev[vid]) / ((v["hi"] - v["lo"]) * 0.1))
            prev = dict(core.applied)
        self.assertLessEqual(worst, 0.0631)                     # 초당 전체 폭의 약 6.3% 이하

    def test_big_dt_is_limited(self):
        core = AutoWeatherCore(spec.default_config(), seed=2)
        core.start(manual_values())
        t0 = core.period_t
        core.step(500.0, manual_values())
        self.assertLessEqual(core.period_t - t0, MAX_DT + 1e-9)

    def test_pause_freezes_and_resume_continues(self):
        core = AutoWeatherCore(spec.default_config(), seed=3)
        core.start(manual_values())
        run(core, 20)
        core.pause()
        snap = (dict(core.applied), core.period_t, core.kind)
        run(core, 60)
        self.assertEqual((dict(core.applied), core.period_t, core.kind), snap)
        core.resume()
        run(core, 20)
        self.assertGreater(core.period_t, snap[1] if core.transitions == 1 else -1)

    def test_transition_happens_once_per_boundary(self):
        cfg = spec.default_config()
        cfg["vars"][spec.DURATION_VAR].update(min=30, max=30)
        core = AutoWeatherCore(cfg, seed=6)
        core.start(manual_values())
        self.assertEqual(core.transitions, 1)
        run(core, 95)
        self.assertEqual(core.transitions, 4)                    # 시작 1회 + 30초마다 1회씩 3회

    def test_next_kind_prediction_matches_next_weather(self):
        cfg = spec.default_config()
        cfg["vars"][spec.DURATION_VAR].update(min=10, max=10)
        core = AutoWeatherCore(cfg, seed=8)
        core.start(manual_values())
        for _ in range(30):
            predicted = core.next_kind
            core._begin_period()
            self.assertEqual(core.kind, predicted)

    def test_manual_kind_fixes_weather_and_changes_targets(self):
        cfg = spec.default_config()
        cfg["vars"][spec.KIND_VAR]["auto"] = False
        cfg["vars"][spec.DURATION_VAR].update(min=10, max=10)
        core = AutoWeatherCore(cfg, seed=3)
        core.start(manual_values(), manual_kind="heavy")
        seen = set()
        run(core, 120, manual_kind="heavy", on_step=lambda c: seen.add((c.kind, c.next_kind)))
        self.assertEqual(seen, {("heavy", "heavy")})
        run(core, 1, manual_kind="clear")
        self.assertEqual(core.kind, "clear")

    def test_manual_duration_is_fixed(self):
        cfg = spec.default_config()
        cfg["vars"][spec.DURATION_VAR].update(auto=False, manual=45)
        core = AutoWeatherCore(cfg, seed=3)
        core.start(manual_values())
        for _ in range(10):
            core._begin_period()
            self.assertEqual(core.period_len, 45)

    def test_duration_frequency_bias_stays_in_range(self):
        for freq in (0, 50, 100):
            cfg = spec.default_config()
            cfg["change_freq"] = freq
            cfg["vars"][spec.DURATION_VAR].update(min=40, max=200)
            core = AutoWeatherCore(cfg, seed=1)
            core.start(manual_values())
            ds = []
            for _ in range(300):
                core._begin_period()
                ds.append(core.period_len)
            self.assertTrue(all(40 <= d <= 200 for d in ds))
            if freq == 100:
                self.assertLess(sum(ds) / len(ds), 100)
            if freq == 0:
                self.assertGreater(sum(ds) / len(ds), 130)

    def test_stop_releases_back_to_manual_smoothly(self):
        core = AutoWeatherCore(spec.default_config(), seed=3)
        man = manual_values(snow_amount=40, temperature=-5)
        core.start(man)
        run(core, 90, manual=man)
        core.stop()
        self.assertEqual(core.phase, "release")
        prev = dict(core.applied)
        for _ in range(int(RELEASE := 150)):
            core.step(0.1, man)
            if core.phase == "idle":
                break
            for vid, x in core.applied.items():
                v = spec.VARS_BY_ID[vid]
                self.assertLessEqual(abs(x - prev[vid]), (v["hi"] - v["lo"]) * 0.0631 + 1e-6)
            prev = dict(core.applied)
        self.assertEqual(core.phase, "idle")
        self.assertEqual(core.values(), {})

    def test_stop_immediate(self):
        core = AutoWeatherCore(spec.default_config(), seed=3)
        core.start(manual_values())
        core.stop(immediate=True)
        self.assertEqual((core.phase, core.values()), ("idle", {}))


class PresetStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PresetStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_builtin_listed_and_immutable(self):
        self.assertEqual(self.store.builtin_names(), spec.PRESET_NAMES)
        ok, msg = self.store.save("폭설", spec.default_config())
        self.assertFalse(ok)
        self.assertIn("기본 제공", msg)
        self.assertFalse(self.store.delete("폭설")[0])
        self.assertFalse(self.store.rename("폭설", "새 이름")[0])

    def test_save_load_roundtrip_includes_everything(self):
        cfg = copy.deepcopy(spec.PRESETS["폭설"])
        cfg["kinds"]["clear"]["on"] = False
        cfg["vars"]["wind_strength"]["auto"] = False
        cfg["vars"]["temperature"].update(min=-7, max=-3)
        cfg["change_speed"], cfg["randomness"] = 12, 77
        self.assertTrue(self.store.save("내 겨울", cfg)[0])
        again = PresetStore(Path(self.tmp.name))               # 재실행 후에도 남아 있음
        self.assertEqual(again.user_names(), ["내 겨울"])
        self.assertEqual(again.get("내 겨울"), cfg)

    def test_name_rules(self):
        cfg = spec.default_config()
        self.assertFalse(self.store.save("   ", cfg)[0])
        self.assertFalse(self.store.save("가" * 40, cfg)[0])
        self.assertTrue(self.store.save("A", cfg)[0])
        self.assertFalse(self.store.save("A", cfg)[0])           # 중복은 거부
        self.assertTrue(self.store.save("A", cfg, overwrite=True)[0])
        self.assertEqual(self.store.user_names(), ["A"])

    def test_rename_and_delete(self):
        cfg = spec.default_config()
        self.store.save("one", cfg)
        self.store.save("two", cfg)
        self.assertFalse(self.store.rename("one", "two")[0])
        self.assertFalse(self.store.rename("one", "폭설")[0])
        self.assertTrue(self.store.rename("one", "uno")[0])
        self.assertEqual(self.store.user_names(), ["uno", "two"])
        self.assertTrue(self.store.delete("uno")[0])
        self.assertFalse(self.store.delete("uno")[0])
        self.assertEqual(self.store.user_names(), ["two"])

    def test_invalid_config_not_saved(self):
        cfg = spec.default_config()
        cfg["vars"]["snow_amount"].update(min=900, max=10)
        ok, msg = self.store.save("bad", cfg)
        self.assertFalse(ok)
        self.assertIn("최솟값", msg)

    def test_corrupt_file_is_recovered(self):
        self.store.save("keep", spec.default_config())
        (Path(self.tmp.name) / "autoweather_presets.json").write_text("{not json", encoding="utf-8")
        again = PresetStore(Path(self.tmp.name))
        self.assertEqual(again.user_names(), [])                 # 손상 -> 빈 목록으로 시작하지만 프로그램은 계속
        self.assertTrue(again.save("new", spec.default_config())[0])

    def test_loaded_preset_is_sanitized(self):
        path = Path(self.tmp.name) / "autoweather_presets.json"
        path.write_text(json.dumps({"version": 1, "presets": [
            {"name": "x", "config": {"vars": {"snow_amount": {"min": 999, "max": 1}}}}, "garbage", {"name": 5}]}),
            encoding="utf-8")
        again = PresetStore(Path(self.tmp.name))
        self.assertEqual(again.user_names(), ["x"])
        self.assertEqual(spec.validate_ranges(again.get("x")), [])


if __name__ == "__main__":
    unittest.main()
