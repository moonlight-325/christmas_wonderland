"""v1.9.4 C단계: 날씨 프리셋 손상/저장 실패, 어드벤트 저장 실패 기록, 음악 폴더 탐색, 자동 날씨 코어 퍼징 (PySide6 불필요)."""
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advent.state import AdventStore
from audio.scan import AUDIO_EXTS, scan_folder
from weather import spec
from weather.core import AutoWeatherCore
from weather.presets import PresetStore


def _store_with(body: str):
    d = Path(tempfile.mkdtemp())
    (d / "autoweather_presets.json").write_text(body, encoding="utf-8")
    return d, PresetStore(d)


class PresetCorruption(unittest.TestCase):
    def test_presets_not_a_list_does_not_crash_and_file_is_kept(self):
        for body in ('{"presets": 5}', '{"presets": {"a": 1}}', '[1, 2]', 'not json'):
            with self.subTest(body=body):
                d, s = _store_with(body)
                self.assertEqual(s.user_names(), [])
                names = [p.name for p in d.iterdir()]
                self.assertTrue(any(n.startswith("autoweather_presets.corrupt-") for n in names), names)

    def test_missing_presets_key_is_just_empty(self):
        d, s = _store_with("{}")
        self.assertEqual(s.user_names(), [])
        self.assertFalse(any("corrupt" in p.name for p in d.iterdir()))

    def test_bad_entries_are_skipped_or_cleaned(self):
        d, s = _store_with(json.dumps({"presets": [1, {"name": 3}, {"name": "ok", "config": "garbage"}]}))
        self.assertEqual(s.user_names(), ["ok"])
        self.assertEqual(spec.validate_ranges(s.get("ok")), [])


class PresetSaveFailureRollsBack(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.s = PresetStore(self.d)
        ok, _ = self.s.save("기존", spec.default_config())
        self.assertTrue(ok)
        os.mkdir(self.d / "autoweather_presets.tmp")      # 임시 파일 위치를 폴더로 막아 저장을 실패시킴

    def test_save_failure_keeps_memory_and_file_consistent(self):
        ok, msg = self.s.save("새것", spec.default_config())
        self.assertFalse(ok)
        self.assertTrue(msg)
        self.assertEqual(self.s.user_names(), ["기존"])

    def test_overwrite_failure_restores_old_config(self):
        cfg = spec.default_config()
        cfg["vars"]["temperature"]["auto"] = not cfg["vars"]["temperature"]["auto"]
        before = self.s.get("기존")
        ok, _ = self.s.save("기존", cfg, overwrite=True)
        self.assertFalse(ok)
        self.assertEqual(self.s.get("기존"), before)

    def test_rename_and_delete_failure_roll_back(self):
        self.assertFalse(self.s.rename("기존", "바뀜")[0])
        self.assertEqual(self.s.user_names(), ["기존"])
        self.assertFalse(self.s.delete("기존")[0])
        self.assertEqual(self.s.user_names(), ["기존"])


class AdventSaveFailureFlag(unittest.TestCase):
    def test_flag_set_on_failure_and_cleared_on_success(self):
        d = Path(tempfile.mkdtemp())
        st = AdventStore(d)
        st.load()
        self.assertFalse(st.save_failed)
        os.mkdir(d / "advent_state.json.tmp")
        st.mark_opened(2026, 3)
        self.assertTrue(st.save_failed)
        self.assertEqual(st.opened_days(2026), {3})          # 메모리에는 남아 있어 같은 실행 중에는 유지
        os.rmdir(d / "advent_state.json.tmp")
        st.mark_opened(2026, 4)
        self.assertFalse(st.save_failed)
        st2 = AdventStore(d)
        st2.load()
        self.assertEqual(st2.opened_days(2026), {3, 4})


class MusicFolderScan(unittest.TestCase):
    def test_limit_stops_walk_and_ignores_non_audio(self):
        root = Path(tempfile.mkdtemp())
        for i in range(5):
            sub = root / f"d{i}"
            sub.mkdir()
            for j in range(4):
                (sub / f"t{j}.mp3").write_bytes(b"x")
            (sub / "note.txt").write_text("x")
        got = scan_folder(root, limit=7)
        self.assertEqual(len(got), 7)
        self.assertTrue(all(p.suffix.lower() in AUDIO_EXTS for p in got))
        self.assertEqual(len(scan_folder(root, limit=500)), 20)
        self.assertEqual(scan_folder(root, limit=0), [])

    def test_missing_folder_is_empty(self):
        self.assertEqual(scan_folder(Path(tempfile.mkdtemp()) / "none"), [])


class AutoWeatherCoreFuzz(unittest.TestCase):
    def test_values_stay_in_range_under_random_operations(self):
        rnd = random.Random(11)

        def manual():
            return {v: rnd.uniform(spec.VARS_BY_ID[v]["lo"], spec.VARS_BY_ID[v]["hi"]) for v in spec.SETTING_VARS}

        started = 0
        for trial in range(120):
            cfg = spec.default_config()
            for v in spec.ALL_VAR_IDS:
                cfg["vars"][v]["auto"] = rnd.random() < 0.7
            for k in cfg["kinds"]:
                cfg["kinds"][k]["on"] = rnd.random() < 0.6
            core = AutoWeatherCore(spec.clean_config(cfg), seed=trial)
            m = manual()
            if core.start(m, None):
                continue
            started += 1
            for _ in range(300):
                op = rnd.random()
                if op < 0.02:
                    core.pause()
                elif op < 0.04:
                    core.resume()
                elif op < 0.05:
                    m = manual()
                core.step(rnd.choice([0, 0.1, 0.5, 5.0]), m, None)
                for vid, val in core.values().items():
                    v = spec.VARS_BY_ID[vid]
                    self.assertEqual(val, val)
                    self.assertTrue(v["lo"] - 1e-6 <= val <= v["hi"] + 1e-6, (trial, vid, val))
                if core.phase == "idle":
                    break
        self.assertGreater(started, 50)


if __name__ == "__main__":
    unittest.main()
